# Databricks notebook source
# MAGIC %md
# MAGIC # LINZ NZ Addresses WFS fetch
# MAGIC
# MAGIC Scheduled job: pages LINZ LDS WFS (NZ Addresses), writes JSONL under the
# MAGIC `linz_nz_addresses_files` bronze volume (date-stamped folder), skips when
# MAGIC `content_hash` matches the last successful run, prunes landings older than
# MAGIC retention, and logs to `housing.bronze.ingest_runs`.
# MAGIC
# MAGIC Same operational pattern as `pipelines/gtfs/notebooks/fetch.py`.
# MAGIC API key: Databricks secret (widgets) or `LINZ_API_KEY` env on the cluster.

# COMMAND ----------

import os
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


from linz_fetch_wfs import fetch_to_jsonl_hashed

# COMMAND ----------
# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

BRONZE_VOLUME = "/Volumes/housing/bronze/linz_nz_addresses_files"
OUTPUT_FILENAME = "linz_nz_addresses.jsonl"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"

# WFS defaults (same as `linz_nz_addresses.yml`; change in code if LINZ updates the layer).
WFS_VERSION = "2.0.0"
WFS_TYPE_NAMES = "layer-105689"
WFS_OUTPUT_FORMAT = "application/json"
WFS_SRS_NAME = "EPSG:4326"
WFS_PAGE_SIZE = 2000
WFS_REQUEST_TIMEOUT_SECONDS = 120.0
WFS_MAX_RETRIES = 5
WFS_RETRY_BACKOFF_SECONDS = 3.0

# Job parameters (overridable via DAB base_parameters or in the workspace UI), same idea as GTFS widgets.
dbutils.widgets.text("feed_source", "nz_addresses", "Feed source name")
dbutils.widgets.text("retention_days", "90", "Retention (days)")
dbutils.widgets.text("auth_secret_scope", "", "Auth secret scope (optional)")
dbutils.widgets.text("auth_secret_key", "linz_api_key", "Auth secret key (optional)")

feed_source = dbutils.widgets.get("feed_source").strip()
retention_days = int(dbutils.widgets.get("retention_days"))
auth_secret_scope = (dbutils.widgets.get("auth_secret_scope") or "").strip()
auth_secret_key = (dbutils.widgets.get("auth_secret_key") or "linz_api_key").strip()

SOURCE_NAME = f"linz_nz_addresses_{feed_source}"
SOURCE_SUBDIR = feed_source

# COMMAND ----------
# MAGIC %md
# MAGIC ## Ensure the run-log table exists
# MAGIC
# MAGIC Idempotent. The `bronze` schema and write grant for the jobs SP are both
# MAGIC provisioned by Terraform; we just make sure the table is here.

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
    """
    Add any columns from `schema` that aren't already on `table_name`.

    Idempotent. Lets us evolve the table schema in code without a separate
    migration step. CREATE TABLE IF NOT EXISTS handles brand-new tables; this
    handles tables that pre-date the latest schema version.
    """
    existing = {f.name for f in spark.table(table_name).schema.fields}
    for field in schema.fields:
        if field.name in existing:
            continue
        dtype = field.dataType.simpleString().upper()
        spark.sql(f"ALTER TABLE {table_name} ADD COLUMNS ({field.name} {dtype})")
        print(f"Schema migration: added column {field.name} {dtype}")


ensure_columns(INGEST_RUNS_TABLE, INGEST_RUNS_SCHEMA)


def log_run(run_id: str, status: str, **fields) -> None:
    """Append a row to the ingest_runs table."""
    row = (
        run_id,
        SOURCE_NAME,
        fields.get("source_url"),
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
    """Return the content_hash from the most recent successful run, or None."""
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
# MAGIC ## Helpers

# COMMAND ----------


def resolve_linz_api_key() -> str:
    if auth_secret_scope:
        return dbutils.secrets.get(auth_secret_scope, auth_secret_key).strip()
    got = os.environ.get("LINZ_API_KEY")
    if got:
        return got.strip()
    raise RuntimeError(
        "LINZ API key not configured: set widgets auth_secret_scope + auth_secret_key, "
        "or set LINZ_API_KEY on the cluster/job."
    )


def build_cfg(api_key: str) -> dict:
    wfs = {
        "base_url": f"https://data.linz.govt.nz/services;key={api_key}/wfs",
        "version": WFS_VERSION,
        "type_names": WFS_TYPE_NAMES,
        "output_format": WFS_OUTPUT_FORMAT,
        "page_size": WFS_PAGE_SIZE,
        "max_pages": None,
        "request_timeout_seconds": WFS_REQUEST_TIMEOUT_SECONDS,
        "max_retries": WFS_MAX_RETRIES,
        "retry_backoff_seconds": WFS_RETRY_BACKOFF_SECONDS,
        "extra_query_params": {},
    }
    if WFS_SRS_NAME:
        wfs["srs_name"] = WFS_SRS_NAME
    return {"wfs": wfs, "landing": {"file_stem": "linz_nz_addresses"}}


def redacted_source_url(cfg: dict) -> str:
    return str(cfg["wfs"]["base_url"]).split("/services")[0] + "/services;key=***/wfs"


def cleanup_old_landings(retention_days: int) -> int:
    """Delete date-stamped subfolders older than retention_days. Returns count removed."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    base = Path(f"{BRONZE_VOLUME}/{SOURCE_SUBDIR}")
    if not base.exists():
        return 0

    removed = 0
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            run_date = datetime.strptime(child.name, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        if run_date < cutoff:
            for path in sorted(child.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            child.rmdir()
            removed += 1
    return removed


# COMMAND ----------
# MAGIC %md
# MAGIC ## Run

# COMMAND ----------

run_id = str(uuid.uuid4())
run_date = datetime.now(UTC).strftime("%Y-%m-%d")
started_at = datetime.now(UTC)
t0 = time.time()
source_url_log = f"wfs://{WFS_TYPE_NAMES}@housing"

try:
    api_key = resolve_linz_api_key()
    cfg = build_cfg(api_key)
    redacted_url = redacted_source_url(cfg)

    print(f"[{run_id}] Fetching WFS type={WFS_TYPE_NAMES} page_size={WFS_PAGE_SIZE}")
    tmp_path = Path(tempfile.gettempdir()) / f"linz_nz_addresses_{run_id}.jsonl"
    try:
        feature_count, content_hash = fetch_to_jsonl_hashed(cfg, output_path=tmp_path)
    except Exception:
        if tmp_path.is_file():
            tmp_path.unlink()
        raise

    bytes_written = tmp_path.stat().st_size
    print(
        f"[{run_id}] staged {feature_count:,} features "
        f"content_hash={content_hash[:12]}… bytes={bytes_written:,}"
    )

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        tmp_path.unlink(missing_ok=True)
        log_run(
            run_id,
            "skipped",
            source_url=redacted_url,
            content_hash=content_hash,
            feed_version=None,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        target_dir = f"{BRONZE_VOLUME}/{SOURCE_SUBDIR}/{run_date}"
        os.makedirs(target_dir, exist_ok=True)
        dest = Path(target_dir) / OUTPUT_FILENAME
        shutil.move(str(tmp_path), str(dest))
        removed = cleanup_old_landings(retention_days)
        log_run(
            run_id,
            "succeeded",
            source_url=redacted_url,
            content_hash=content_hash,
            feed_version=str(feature_count),
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            file_count=1,
            bytes_written=bytes_written,
            target_path=target_dir,
            notes=(
                f"feature_rows={feature_count}; cleaned {removed} landing(s) "
                f"older than {retention_days} days"
            ),
        )
        print(
            f"[{run_id}] Succeeded: {feature_count:,} features, "
            f"{bytes_written:,} bytes at {target_dir} "
            f"(cleaned {removed} old landing(s))"
        )

except Exception as exc:
    tmp_cleanup = Path(tempfile.gettempdir()) / f"linz_nz_addresses_{run_id}.jsonl"
    tmp_cleanup.unlink(missing_ok=True)
    log_run(
        run_id,
        "failed",
        source_url=source_url_log,
        fetched_at=started_at,
        duration_seconds=time.time() - t0,
        error_message=str(exc),
    )
    print(f"[{run_id}] Failed: {exc}")
    raise
