# Databricks notebook source
# MAGIC %md
# MAGIC # places fetch — GeoJSON datasets
# MAGIC
# MAGIC Downloads one GeoJSON-format dataset and lands it on the bronze
# MAGIC volume in two forms:
# MAGIC
# MAGIC - `_geojson/<dataset>/<date>.geojson` — raw audit copy.
# MAGIC - `<dataset>/<date>.jsonl` — one feature per line, Auto-Loader friendly.
# MAGIC
# MAGIC The bundle invokes this per GeoJSON dataset (today: SA2 polygons from
# MAGIC Stats NZ DataFinder; future: school zones, amenity points, etc.).
# MAGIC
# MAGIC CSV datasets use the sibling `fetch_csv.py` notebook instead.
# MAGIC
# MAGIC Auth modes (most public Stats NZ / DataFinder layers need none):
# MAGIC
# MAGIC - `auth_inject_mode = "none"` (default): no auth, public source.
# MAGIC - `auth_inject_mode = "url_placeholder"`: substitute the secret into
# MAGIC   `auth_url_placeholder` in the URL itself (e.g. LINZ Data Service style).
# MAGIC - `auth_inject_mode = "header"`: send the secret as an HTTP header
# MAGIC   named `auth_header_name`.
# MAGIC
# MAGIC If a secret is required but not configured, the run is logged as
# MAGIC `skipped` and the task exits cleanly so downstream pipelines aren't
# MAGIC blocked.

# COMMAND ----------

import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

BRONZE_VOLUME = "/Volumes/housing/bronze/places_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"
# Files are laid out as:
#   /Volumes/housing/bronze/places_files/_geojson/<dataset>/<date>.geojson  (audit)
#   /Volumes/housing/bronze/places_files/<dataset>/<date>.jsonl             (Auto Loader input)
RAW_SUBDIR = "_geojson"

dbutils.widgets.text("dataset", "sa2_polygons", "Dataset identifier")
dbutils.widgets.text(
    "source_url",
    "https://example.invalid/replace-me",
    "GeoJSON source URL (may contain {api_key} placeholder)",
)
dbutils.widgets.text("retention_days", "180", "Retention (days)")
dbutils.widgets.text("auth_secret_scope", "", "Auth secret scope (optional)")
dbutils.widgets.text("auth_secret_key", "", "Auth secret key (optional)")
dbutils.widgets.dropdown(
    "auth_inject_mode",
    "none",
    ["none", "url_placeholder", "header"],
    "How to inject the secret",
)
dbutils.widgets.text("auth_url_placeholder", "{api_key}", "URL placeholder to substitute")
dbutils.widgets.text("auth_header_name", "Authorization", "HTTP header name")

dataset = dbutils.widgets.get("dataset").strip()
source_url = dbutils.widgets.get("source_url").strip()
retention_days = int(dbutils.widgets.get("retention_days"))
auth_secret_scope = dbutils.widgets.get("auth_secret_scope").strip()
auth_secret_key = dbutils.widgets.get("auth_secret_key").strip()
auth_inject_mode = dbutils.widgets.get("auth_inject_mode").strip()
auth_url_placeholder = dbutils.widgets.get("auth_url_placeholder").strip()
auth_header_name = dbutils.widgets.get("auth_header_name").strip()

# `source` column in ingest_runs — namespaces the run log per place dataset.
SOURCE_NAME = f"places_{dataset}"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Ensure the run-log table exists
# MAGIC
# MAGIC Shared table with the GTFS fetch — same shape. Created idempotently.

# COMMAND ----------

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {INGEST_RUNS_TABLE} (
      run_id            STRING,
      source            STRING,
      source_url        STRING,
      content_hash      STRING,
      feed_version      STRING,
      status            STRING,
      fetched_at        TIMESTAMP,
      duration_seconds  DOUBLE,
      file_count        INT,
      bytes_written     BIGINT,
      target_path       STRING,
      error_message     STRING,
      notes             STRING
    ) USING DELTA
    """
)

INGEST_RUNS_SCHEMA = StructType(
    [
        StructField("run_id", StringType(), True),
        StructField("source", StringType(), True),
        StructField("source_url", StringType(), True),
        StructField("content_hash", StringType(), True),
        StructField("feed_version", StringType(), True),
        StructField("status", StringType(), True),
        StructField("fetched_at", TimestampType(), True),
        StructField("duration_seconds", DoubleType(), True),
        StructField("file_count", IntegerType(), True),
        StructField("bytes_written", LongType(), True),
        StructField("target_path", StringType(), True),
        StructField("error_message", StringType(), True),
        StructField("notes", StringType(), True),
    ]
)


def log_run(run_id: str, status: str, **fields) -> None:
    row = (
        run_id,
        SOURCE_NAME,
        # Don't store the literal URL with key substituted in — that's a leak risk.
        # Keep the placeholder form so the log is safe to share.
        source_url,
        fields.get("content_hash"),
        fields.get("feed_version"),
        status,
        fields.get("fetched_at"),
        fields.get("duration_seconds"),
        fields.get("file_count"),
        fields.get("bytes_written"),
        fields.get("target_path"),
        fields.get("error_message"),
        fields.get("notes"),
    )
    df = spark.createDataFrame([row], schema=INGEST_RUNS_SCHEMA)
    df.write.mode("append").option("mergeSchema", "true").saveAsTable(INGEST_RUNS_TABLE)


def last_successful_content_hash() -> str | None:
    result = spark.sql(
        f"""
        SELECT content_hash
        FROM {INGEST_RUNS_TABLE}
        WHERE source = '{SOURCE_NAME}' AND status = 'succeeded'
        ORDER BY fetched_at DESC
        LIMIT 1
        """
    ).collect()
    if not result:
        return None
    return result[0].content_hash


# COMMAND ----------
# MAGIC %md
# MAGIC ## Resolve auth (if required)

# COMMAND ----------

run_id = str(uuid.uuid4())
started_at = datetime.now(UTC)
t0 = time.time()

resolved_url = source_url
auth_headers: dict[str, str] | None = None

if auth_inject_mode in ("url_placeholder", "header") and auth_secret_scope and auth_secret_key:
    try:
        token = dbutils.secrets.get(scope=auth_secret_scope, key=auth_secret_key)
    except Exception as exc:
        err_str = str(exc)
        if "Secret does not exist" in err_str:
            short_notes = f"auth secret `{auth_secret_scope}/{auth_secret_key}` not configured yet"
        else:
            short_notes = (
                f"failed to read auth secret "
                f"`{auth_secret_scope}/{auth_secret_key}`: {err_str[:200]}"
            )
        log_run(
            run_id,
            "skipped",
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes=short_notes,
        )
        print(f"[{run_id}] Skipped: {short_notes}")
        dbutils.notebook.exit("auth secret not configured")

    if auth_inject_mode == "url_placeholder":
        if auth_url_placeholder not in source_url:
            raise ValueError(
                f"auth_url_placeholder `{auth_url_placeholder}` not found in source_url"
            )
        resolved_url = source_url.replace(auth_url_placeholder, token)
        print(f"[{run_id}] Substituted `{auth_url_placeholder}` into source URL")
    else:  # header
        auth_headers = {auth_header_name: token}
        print(f"[{run_id}] Using auth header `{auth_header_name}`")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Helpers

# COMMAND ----------


def download(url: str, headers: dict | None = None) -> bytes:
    response = requests.get(url, timeout=300, headers=headers)
    response.raise_for_status()
    return response.content


def write_to_volume(geojson_bytes: bytes, run_date: str) -> tuple[str, int, int]:
    """
    Write the raw GeoJSON + a JSONL form (one feature per line).

    Layout:
      /Volumes/housing/bronze/places_files/_geojson/<dataset>/<date>.geojson  (audit)
      /Volumes/housing/bronze/places_files/<dataset>/<date>.jsonl             (Auto Loader)
    """
    raw_dir = f"{BRONZE_VOLUME}/{RAW_SUBDIR}/{dataset}"
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = f"{raw_dir}/{run_date}.geojson"
    with open(raw_path, "wb") as f:
        f.write(geojson_bytes)

    bytes_written = len(geojson_bytes)
    file_count = 1

    # Convert the FeatureCollection into JSONL — one feature per line. Each
    # line is a standalone JSON object that Auto Loader can stream as a row.
    payload = json.loads(geojson_bytes.decode("utf-8"))
    if payload.get("type") != "FeatureCollection" or "features" not in payload:
        raise ValueError(f"Expected a GeoJSON FeatureCollection, got type={payload.get('type')!r}")

    jsonl_dir = f"{BRONZE_VOLUME}/{dataset}"
    os.makedirs(jsonl_dir, exist_ok=True)
    jsonl_path = f"{jsonl_dir}/{run_date}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as out:
        for feature in payload["features"]:
            out.write(json.dumps(feature, ensure_ascii=False))
            out.write("\n")

    bytes_written += os.path.getsize(jsonl_path)
    file_count += 1
    feature_count = len(payload["features"])
    print(f"[{run_id}] Wrote {feature_count:,} features → {jsonl_path}")

    return raw_path, file_count, bytes_written


def cleanup_old_landings(retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    base = Path(BRONZE_VOLUME)
    if not base.exists():
        return 0

    removed = 0
    # Only clean this dataset's landings; other datasets clean themselves.
    candidates = [
        base / RAW_SUBDIR / dataset,
        base / dataset,
    ]
    for dir_path in candidates:
        if not dir_path.exists():
            continue
        for landing in dir_path.iterdir():
            if not landing.is_file():
                continue
            try:
                run_date = datetime.strptime(landing.stem, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                continue
            if run_date < cutoff:
                landing.unlink()
                removed += 1
    return removed


# COMMAND ----------
# MAGIC %md
# MAGIC ## Run

# COMMAND ----------

run_date = datetime.now(UTC).strftime("%Y-%m-%d")

try:
    print(f"[{run_id}] Downloading {dataset}")
    geojson_bytes = download(resolved_url, headers=auth_headers)
    content_hash = hashlib.sha256(geojson_bytes).hexdigest()
    print(f"[{run_id}] dataset={dataset} bytes={len(geojson_bytes):,} hash={content_hash[:12]}…")

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        log_run(
            run_id,
            "skipped",
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        target_path, file_count, bytes_written = write_to_volume(geojson_bytes, run_date)
        removed = cleanup_old_landings(retention_days)
        log_run(
            run_id,
            "succeeded",
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            file_count=file_count,
            bytes_written=bytes_written,
            target_path=target_path,
            notes=f"cleaned up {removed} landing(s) older than {retention_days} days",
        )
        print(
            f"[{run_id}] Succeeded: {file_count} files, "
            f"{bytes_written:,} bytes at {target_path} "
            f"(cleaned {removed} old landing(s))"
        )

except Exception as exc:
    log_run(
        run_id,
        "failed",
        fetched_at=started_at,
        duration_seconds=time.time() - t0,
        error_message=str(exc),
    )
    print(f"[{run_id}] Failed: {exc}")
    raise
