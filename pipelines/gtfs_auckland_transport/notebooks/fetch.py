# Databricks notebook source
# MAGIC %md
# MAGIC # GTFS fetch (multi-feed)
# MAGIC
# MAGIC Weekly job task that downloads one GTFS zip per feed and lands it on the
# MAGIC bronze volume in a file-type-first layout. One run of this notebook
# MAGIC handles a single feed (auckland_transport, metlink, metroinfo, ...);
# MAGIC the bundle invokes it once per feed in parallel.
# MAGIC
# MAGIC Optional auth: if `auth_secret_scope` and `auth_secret_key` are set,
# MAGIC the notebook reads the secret and passes it as an HTTP header named
# MAGIC `auth_header_name` (default `Ocp-Apim-Subscription-Key`). If the secret
# MAGIC isn't configured yet, the run is logged as `skipped` and the task
# MAGIC exits cleanly so downstream pipelines aren't blocked.

# COMMAND ----------

import hashlib
import io
import os
import time
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
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

BRONZE_VOLUME = "/Volumes/housing/bronze/gtfs_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"
# Files are laid out as:
#   /Volumes/housing/bronze/gtfs_files/_zip/<feed>/<date>.zip   (audit)
#   /Volumes/housing/bronze/gtfs_files/<file_name>/<feed>/<date>.txt
ZIP_SUBDIR = "_zip"

# Job parameters. Defaults pointed at Auckland Transport so the notebook is
# runnable interactively; the bundle's `base_parameters` override these per
# feed task.
dbutils.widgets.text("feed_source", "auckland_transport", "Feed source name")
dbutils.widgets.text(
    "source_url",
    "https://gtfs.at.govt.nz/gtfs.zip",
    "GTFS source URL",
)
dbutils.widgets.text("retention_days", "90", "Retention (days)")
dbutils.widgets.text("auth_secret_scope", "", "Auth secret scope (optional)")
dbutils.widgets.text("auth_secret_key", "", "Auth secret key (optional)")
dbutils.widgets.text(
    "auth_header_name",
    "Ocp-Apim-Subscription-Key",
    "Auth HTTP header name",
)

feed_source = dbutils.widgets.get("feed_source").strip()
source_url = dbutils.widgets.get("source_url").strip()
retention_days = int(dbutils.widgets.get("retention_days"))
auth_secret_scope = dbutils.widgets.get("auth_secret_scope").strip()
auth_secret_key = dbutils.widgets.get("auth_secret_key").strip()
auth_header_name = dbutils.widgets.get("auth_header_name").strip()

# `source` column in ingest_runs — namespaces the run log per feed family.
SOURCE_NAME = f"gtfs_{feed_source}"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Ensure the run-log table exists

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


def ensure_columns(table_name: str, schema: StructType) -> None:
    existing = {f.name for f in spark.table(table_name).schema.fields}
    for field in schema.fields:
        if field.name in existing:
            continue
        dtype = field.dataType.simpleString().upper()
        spark.sql(f"ALTER TABLE {table_name} ADD COLUMNS ({field.name} {dtype})")
        print(f"Schema migration: added column {field.name} {dtype}")


ensure_columns(INGEST_RUNS_TABLE, INGEST_RUNS_SCHEMA)


def log_run(run_id: str, status: str, **fields) -> None:
    row = (
        run_id,
        SOURCE_NAME,
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
    df.write.mode("append").option("mergeSchema", "true").saveAsTable(
        INGEST_RUNS_TABLE
    )


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
# MAGIC
# MAGIC If `auth_secret_scope` and `auth_secret_key` are set, read the secret
# MAGIC and prepare an HTTP header. If the secret isn't configured (typical for
# MAGIC feeds we don't have access to yet), log a `skipped` run and exit.

# COMMAND ----------

run_id = str(uuid.uuid4())
started_at = datetime.now(timezone.utc)
t0 = time.time()

auth_headers: dict[str, str] | None = None
if auth_secret_scope and auth_secret_key:
    try:
        token = dbutils.secrets.get(scope=auth_secret_scope, key=auth_secret_key)
        auth_headers = {auth_header_name: token}
        print(
            f"[{run_id}] Using auth header `{auth_header_name}` from "
            f"`{auth_secret_scope}/{auth_secret_key}`"
        )
    except Exception as exc:
        log_run(
            run_id,
            "skipped",
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes=(
                f"auth secret `{auth_secret_scope}/{auth_secret_key}` not configured: "
                f"{exc}"
            ),
        )
        print(
            f"[{run_id}] Skipped: auth secret "
            f"`{auth_secret_scope}/{auth_secret_key}` not configured"
        )
        dbutils.notebook.exit("auth secret not configured")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Helpers

# COMMAND ----------


def download(url: str, headers: dict | None = None) -> bytes:
    response = requests.get(url, timeout=300, headers=headers)
    response.raise_for_status()
    return response.content


def read_feed_version(zip_bytes: bytes) -> str | None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        if "feed_info.txt" not in zf.namelist():
            return None
        with zf.open("feed_info.txt") as f:
            header = f.readline().decode("utf-8").strip().split(",")
            row = f.readline().decode("utf-8").strip().split(",")
        if "feed_version" not in header:
            return None
        return row[header.index("feed_version")].strip().strip('"')


def write_to_volume(zip_bytes: bytes, run_date: str) -> tuple[str, int, int]:
    """
    Write the raw zip and each extracted .txt under a file-type-first layout:

      /Volumes/housing/bronze/gtfs_files/_zip/<feed>/<date>.zip
      /Volumes/housing/bronze/gtfs_files/<file_name>/<feed>/<date>.txt
    """
    zip_dir = f"{BRONZE_VOLUME}/{ZIP_SUBDIR}/{feed_source}"
    os.makedirs(zip_dir, exist_ok=True)
    zip_path = f"{zip_dir}/{run_date}.zip"
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)

    file_count = 1
    bytes_written = len(zip_bytes)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".txt"):
                continue
            file_name_stem = info.filename[: -len(".txt")]
            target_dir = f"{BRONZE_VOLUME}/{file_name_stem}/{feed_source}"
            os.makedirs(target_dir, exist_ok=True)
            target_path = f"{target_dir}/{run_date}.txt"
            with zf.open(info.filename) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
            file_count += 1
            bytes_written += info.file_size

    return zip_path, file_count, bytes_written


def cleanup_old_landings(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    base = Path(BRONZE_VOLUME)
    if not base.exists():
        return 0

    removed = 0
    for type_dir in base.iterdir():
        if not type_dir.is_dir():
            continue
        for feed_dir in type_dir.iterdir():
            if not feed_dir.is_dir():
                continue
            if feed_dir.name != feed_source:
                # Only clean this run's feed_source; other feeds clean themselves.
                continue
            for landing in feed_dir.iterdir():
                if not landing.is_file():
                    continue
                try:
                    run_date = datetime.strptime(landing.stem, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
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

run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

try:
    print(f"[{run_id}] Downloading {feed_source} from {source_url}")
    zip_bytes = download(source_url, headers=auth_headers)
    content_hash = hashlib.sha256(zip_bytes).hexdigest()
    feed_version = read_feed_version(zip_bytes)
    print(
        f"[{run_id}] feed={feed_source} bytes={len(zip_bytes):,} "
        f"hash={content_hash[:12]}… feed_version={feed_version}"
    )

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        log_run(
            run_id,
            "skipped",
            content_hash=content_hash,
            feed_version=feed_version,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        target_path, file_count, bytes_written = write_to_volume(zip_bytes, run_date)
        removed = cleanup_old_landings(retention_days)
        log_run(
            run_id,
            "succeeded",
            content_hash=content_hash,
            feed_version=feed_version,
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
