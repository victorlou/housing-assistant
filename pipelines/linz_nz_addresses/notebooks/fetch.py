# Databricks notebook source
# MAGIC %md
# MAGIC # LINZ NZ Addresses WFS fetch
# MAGIC
# MAGIC Scheduled job: pages LINZ LDS WFS (NZ Addresses), writes JSONL under the
# MAGIC `addresses_files` bronze volume (date-stamped folder), skips when
# MAGIC `content_hash` matches the last successful run, prunes landings older than
# MAGIC retention, and logs to `housing.bronze.ingest_runs`.
# MAGIC
# MAGIC Same operational pattern as `gtfs_auckland_transport/notebooks/fetch.py`.
# MAGIC API key: Databricks secret (widgets) or `LINZ_API_KEY` env on the cluster.

# COMMAND ----------

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
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

import __main__ as _databricks_main

dbutils = getattr(_databricks_main, "dbutils", None)
spark = getattr(_databricks_main, "spark", None)
if dbutils is None or spark is None:
    try:
        from databricks.sdk.runtime import dbutils as _dbu
        from databricks.sdk.runtime import spark as _spk
    except ImportError as exc:
        raise RuntimeError(
            "dbutils/spark not on __main__ and databricks-sdk.runtime unavailable; "
            "run this notebook on Databricks."
        ) from exc
    dbutils = _dbu
    spark = _spk

# COMMAND ----------
# Resolve sibling module (bundle deploys `pipelines/linz_nz_addresses/` as a folder).

_bundle_root = Path(__file__).resolve().parent.parent
if str(_bundle_root) not in sys.path:
    sys.path.insert(0, str(_bundle_root))

from linz_fetch_wfs import fetch_to_jsonl_hashed

# COMMAND ----------
# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

SOURCE_NAME = "linz_nz_addresses"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"
SOURCE_SUBDIR = "linz_nz_addresses"
OUTPUT_FILENAME = "linz_nz_addresses.jsonl"

dbutils.widgets.text("catalog", "housing", "UC catalog (must match Terraform catalog_name)")
dbutils.widgets.text("retention_days", "90", "Retention (days) for date-stamped landings")
dbutils.widgets.text("secret_scope", "", "Secret scope for LINZ API key (optional if env set)")
dbutils.widgets.text("secret_key", "linz_api_key", "Secret key name")
dbutils.widgets.text("wfs_version", "2.0.0", "WFS VERSION")
dbutils.widgets.text("type_names", "layer-105689", "WFS TYPENAMES")
dbutils.widgets.text("output_format", "application/json", "OUTPUTFORMAT")
dbutils.widgets.text("srs_name", "EPSG:4326", "SRSNAME (empty to omit)")
dbutils.widgets.text("page_size", "2000", "COUNT / page size")
dbutils.widgets.text("request_timeout_seconds", "120", "HTTP timeout (s)")
dbutils.widgets.text("max_retries", "5", "Retries per page")
dbutils.widgets.text("retry_backoff_seconds", "3.0", "Backoff base (s)")

catalog = dbutils.widgets.get("catalog")
retention_days = int(dbutils.widgets.get("retention_days"))
secret_scope = (dbutils.widgets.get("secret_scope") or "").strip()
secret_key = (dbutils.widgets.get("secret_key") or "linz_api_key").strip()
wfs_version = dbutils.widgets.get("wfs_version")
type_names = dbutils.widgets.get("type_names")
output_format = dbutils.widgets.get("output_format")
srs_name = (dbutils.widgets.get("srs_name") or "").strip()
page_size = int(dbutils.widgets.get("page_size"))
request_timeout_seconds = float(dbutils.widgets.get("request_timeout_seconds"))
max_retries = int(dbutils.widgets.get("max_retries"))
retry_backoff_seconds = float(dbutils.widgets.get("retry_backoff_seconds"))

BRONZE_VOLUME = f"/Volumes/{catalog}/bronze/addresses_files"

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
    if secret_scope:
        return dbutils.secrets.get(secret_scope, secret_key)
    got = os.environ.get("LINZ_API_KEY")
    if got:
        return got
    raise RuntimeError(
        "LINZ API key not configured: set widgets secret_scope + secret_key, "
        "or set LINZ_API_KEY on the cluster/job."
    )


def build_cfg(api_key: str) -> dict:
    wfs = {
        "base_url": f"https://data.linz.govt.nz/services;key={api_key}/wfs",
        "version": wfs_version,
        "type_names": type_names,
        "output_format": output_format,
        "page_size": page_size,
        "max_pages": None,
        "request_timeout_seconds": request_timeout_seconds,
        "max_retries": max_retries,
        "retry_backoff_seconds": retry_backoff_seconds,
        "extra_query_params": {},
    }
    if srs_name:
        wfs["srs_name"] = srs_name
    return {"wfs": wfs, "landing": {"file_stem": "linz_nz_addresses"}}


def redacted_source_url(cfg: dict) -> str:
    return str(cfg["wfs"]["base_url"]).split("/services")[0] + "/services;key=***/wfs"


def cleanup_old_landings(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    base = Path(f"{BRONZE_VOLUME}/{SOURCE_SUBDIR}")
    if not base.exists():
        return 0

    removed = 0
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            run_date = datetime.strptime(child.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
started_at = datetime.now(timezone.utc)
t0 = time.time()
source_url_log = f"wfs://{type_names}@{catalog}"

try:
    api_key = resolve_linz_api_key()
    cfg = build_cfg(api_key)
    redacted_url = redacted_source_url(cfg)

    print(f"[{run_id}] Fetching WFS type={type_names} page_size={page_size}")
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
