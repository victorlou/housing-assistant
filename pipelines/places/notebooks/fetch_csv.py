# Databricks notebook source
# MAGIC %md
# MAGIC # places fetch — CSV datasets (volume-read)
# MAGIC
# MAGIC Reads the most recent CSV dataset uploaded to the bronze volume and
# MAGIC passes it through unchanged for Auto Loader to stream:
# MAGIC
# MAGIC - input:  `<dataset>/<date>.csv`  (manually uploaded by an operator)
# MAGIC - output: `<dataset>/<date>.csv`  (in place; bronze Auto Loader picks it up)
# MAGIC
# MAGIC Currently used by the SA2 census task. Same hash-dedup + retention +
# MAGIC ingest_runs logging pattern as `fetch.py` (GeoJSON) — the
# MAGIC functional difference is that CSV needs no conversion, just validation.
# MAGIC
# MAGIC ## Why volume-read for census
# MAGIC
# MAGIC Stats NZ DataFinder publishes census tables as web-UI exports rather
# MAGIC than via WFS like the spatial layers. The Koordinates Tables API
# MAGIC exists but is awkward to use programmatically (export-job-then-poll
# MAGIC pattern). Manual quarterly upload is the simpler path for a dataset
# MAGIC that refreshes every 5 years anyway.

# COMMAND ----------

import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta
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

# COMMAND ----------
# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

BRONZE_VOLUME = "/Volumes/housing/bronze/places_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"

# Sanity floor — refuse to claim success on a suspiciously-tiny file.
# 2023 census by SA2 has 2,400 rows × many columns; the CSV is hundreds of KB.
MIN_EXPECTED_BYTES = 50_000

dbutils.widgets.text("dataset", "sa2_census", "Dataset identifier")
dbutils.widgets.text("retention_days", "365", "Retention (days) for the CSV landings")

dataset = dbutils.widgets.get("dataset").strip()
retention_days = int(dbutils.widgets.get("retention_days"))

SOURCE_NAME = f"places_{dataset}"

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


def log_run(run_id: str, status: str, source_url_repr: str, **fields) -> None:
    row = (
        run_id,
        SOURCE_NAME,
        source_url_repr,
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
# MAGIC ## Locate the latest manually-uploaded CSV

# COMMAND ----------


def latest_csv_path() -> Path:
    upload_dir = Path(BRONZE_VOLUME) / dataset
    if not upload_dir.exists():
        raise FileNotFoundError(
            f"Upload directory {upload_dir} does not exist yet. "
            "Manually upload the CSV first — see README."
        )
    candidates = sorted(
        (p for p in upload_dir.iterdir() if p.suffix.lower() == ".csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No .csv files in {upload_dir}. "
            "Manually upload the CSV first — see README."
        )
    return candidates[-1]


def cleanup_old_csvs(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    csv_dir = Path(BRONZE_VOLUME) / dataset
    if not csv_dir.exists():
        return 0
    removed = 0
    for landing in csv_dir.iterdir():
        if not landing.is_file() or landing.suffix.lower() != ".csv":
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

run_id = str(uuid.uuid4())
started_at = datetime.now(timezone.utc)
t0 = time.time()

try:
    csv_path = latest_csv_path()
    print(f"[{run_id}] Validating {csv_path.name} from {csv_path.parent}")

    csv_bytes = csv_path.read_bytes()
    if len(csv_bytes) < MIN_EXPECTED_BYTES:
        raise ValueError(
            f"CSV {csv_path.name} is only {len(csv_bytes):,} bytes; "
            f"expected at least {MIN_EXPECTED_BYTES:,}. Suspect a broken upload."
        )

    content_hash = hashlib.sha256(csv_bytes).hexdigest()
    print(
        f"[{run_id}] dataset={dataset} bytes={len(csv_bytes):,} "
        f"hash={content_hash[:12]}…"
    )

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        log_run(
            run_id,
            "skipped",
            source_url_repr=str(csv_path),
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        # No transformation needed — bronze Auto Loader streams the CSV in place.
        removed = cleanup_old_csvs(retention_days)
        log_run(
            run_id,
            "succeeded",
            source_url_repr=str(csv_path),
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            file_count=1,
            bytes_written=len(csv_bytes),
            target_path=str(csv_path),
            notes=f"validated {csv_path.name}; cleaned up {removed} old CSV(s) >{retention_days} days",
        )
        print(
            f"[{run_id}] Succeeded: {len(csv_bytes):,} bytes at {csv_path} "
            f"(cleaned {removed} old CSV(s))"
        )

except Exception as exc:
    log_run(
        run_id,
        "failed",
        source_url_repr="(volume-read; no URL)",
        fetched_at=started_at,
        duration_seconds=time.time() - t0,
        error_message=str(exc),
    )
    print(f"[{run_id}] Failed: {exc}")
    raise
