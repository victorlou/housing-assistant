# Databricks notebook source
# MAGIC %md
# MAGIC # Auckland Transport GTFS fetch
# MAGIC
# MAGIC Weekly job: downloads the AT GTFS zip, writes both the raw zip and the
# MAGIC extracted `.txt` files to `housing.bronze.gtfs_files`, skips when the
# MAGIC `feed_version` hasn't changed, cleans up landings older than the retention
# MAGIC window, and logs every run to `housing.bronze.ingest_runs`.
# MAGIC
# MAGIC Runs as the `sp-housing-jobs` service principal. Triggered by the
# MAGIC Databricks Asset Bundle in `../databricks.yml`.

# COMMAND ----------

import hashlib
import io
import os
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
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

SOURCE_NAME = "gtfs_auckland_transport"
BRONZE_VOLUME = "/Volumes/housing/bronze/gtfs_files"
SOURCE_SUBDIR = "auckland_transport"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"

# Job parameters (overridable via DAB base_parameters or in the workspace UI).
dbutils.widgets.text(
    "source_url",
    "https://gtfs.at.govt.nz/gtfs.zip",
    "GTFS source URL",
)
dbutils.widgets.text("retention_days", "90", "Retention (days)")

source_url = dbutils.widgets.get("source_url")
retention_days = int(dbutils.widgets.get("retention_days"))

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

# `content_hash` is the universal "did this change?" signal. Works for any
# source (CSV, JSON, zip) because every source has bytes. `feed_version` is
# kept for human inspection but isn't used for dedup, so non-GTFS sources can
# leave it null without affecting the pattern.
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
    # mergeSchema lets the table pick up the new content_hash column on
    # first write even if the table was created before this code shipped.
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


def download(url: str) -> bytes:
    """Download the file at `url` with a 5-minute timeout."""
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def read_feed_version(zip_bytes: bytes) -> str | None:
    """Read `feed_version` from feed_info.txt inside the zip. None if absent."""
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
    """Write the raw zip and extracted .txt files. Returns (target_dir, file_count, bytes_written)."""
    target_dir = f"{BRONZE_VOLUME}/{SOURCE_SUBDIR}/{run_date}"
    os.makedirs(target_dir, exist_ok=True)

    zip_path = f"{target_dir}/gtfs.zip"
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)

    file_count = 1
    bytes_written = len(zip_bytes)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            zf.extract(info, target_dir)
            file_count += 1
            bytes_written += info.file_size

    return target_dir, file_count, bytes_written


def cleanup_old_landings(retention_days: int) -> int:
    """Delete date-stamped subfolders older than retention_days. Returns count removed."""
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
            # not a date-named folder, leave it alone
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

try:
    print(f"[{run_id}] Downloading from {source_url}")
    zip_bytes = download(source_url)
    content_hash = hashlib.sha256(zip_bytes).hexdigest()
    feed_version = read_feed_version(zip_bytes)
    print(
        f"[{run_id}] bytes={len(zip_bytes):,} "
        f"content_hash={content_hash[:12]}… feed_version={feed_version}"
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
