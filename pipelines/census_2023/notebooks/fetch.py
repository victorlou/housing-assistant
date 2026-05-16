# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 ArcGIS fetch
# MAGIC
# MAGIC Fetches one Stats NZ "totals by topic" SA2 layer (households or dwellings),
# MAGIC writes GeoJSON JSONL to the census bronze volume, skips unchanged content,
# MAGIC prunes old landings, and logs to `housing.bronze.ingest_runs`.

# COMMAND ----------

import os
import shutil
import sys
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


def _bundle_files_root() -> Path:
    try:
        return Path(__file__).resolve().parent.parent
    except NameError:
        nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        return Path("/Workspace" + nb).resolve().parent.parent


_bundle_root = _bundle_files_root()
if str(_bundle_root) not in sys.path:
    sys.path.insert(0, str(_bundle_root))

from census_fetch_arcgis import (
    LAYERS,
    fetch_layer_field_dictionary_csv,
    fetch_layer_to_jsonl_hashed,
)

# COMMAND ----------

BRONZE_VOLUME = "/Volumes/housing/bronze/census_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"

dbutils.widgets.dropdown(
    "layer_key",
    "households_sa2",
    list(LAYERS.keys()),
    "ArcGIS layer preset",
)
dbutils.widgets.text("retention_days", "365", "Retention (days)")

layer_key = dbutils.widgets.get("layer_key").strip()
retention_days = int(dbutils.widgets.get("retention_days"))
spec = LAYERS[layer_key]
SOURCE_NAME = spec["file_stem"]
SOURCE_SUBDIR = spec["file_stem"]
OUTPUT_FILENAME = f"{spec['file_stem']}.jsonl"
SOURCE_URL = f"arcgis://{spec['service']}/FeatureServer/{spec['layer_id']}"

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


ensure_columns(INGEST_RUNS_TABLE, INGEST_RUNS_SCHEMA)


def log_run(run_id: str, status: str, **fields) -> None:
    row = (
        run_id,
        SOURCE_NAME,
        SOURCE_URL,
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


FIELD_DICTIONARY_FILENAME = f"{SOURCE_NAME}_field_dictionary.csv"


def publish_landing(tmp_path: Path, tmp_dict_path: Path, run_date: str) -> str:
    target_dir = f"{BRONZE_VOLUME}/{SOURCE_SUBDIR}/{run_date}"
    os.makedirs(target_dir, exist_ok=True)
    target_path = f"{target_dir}/{OUTPUT_FILENAME}"
    shutil.move(str(tmp_path), target_path)
    shutil.move(str(tmp_dict_path), f"{target_dir}/{FIELD_DICTIONARY_FILENAME}")
    return target_path


def cleanup_old_landings(retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    base = Path(BRONZE_VOLUME) / SOURCE_SUBDIR
    if not base.exists():
        return 0
    removed = 0
    for landing_dir in base.iterdir():
        if not landing_dir.is_dir():
            continue
        try:
            run_date = datetime.strptime(landing_dir.name, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        if run_date < cutoff:
            shutil.rmtree(landing_dir)
            removed += 1
    return removed


# COMMAND ----------

run_id = str(uuid.uuid4())
run_date = datetime.now(UTC).strftime("%Y-%m-%d")
started_at = datetime.now(UTC)
t0 = time.time()

try:
    print(f"[{run_id}] Fetching {layer_key} from ArcGIS")
    tmp_path = Path(tempfile.gettempdir()) / f"{SOURCE_NAME}_{run_id}.jsonl"
    tmp_dict_path = Path(tempfile.gettempdir()) / f"{FIELD_DICTIONARY_FILENAME}_{run_id}"
    try:
        feature_count, content_hash = fetch_layer_to_jsonl_hashed(layer_key, tmp_path)
        field_count = fetch_layer_field_dictionary_csv(layer_key, tmp_dict_path)
        print(f"[{run_id}] staged field dictionary ({field_count} fields)")
    except Exception:
        if tmp_path.is_file():
            tmp_path.unlink()
        tmp_dict_path.unlink(missing_ok=True)
        raise

    bytes_written = tmp_path.stat().st_size
    print(
        f"[{run_id}] staged {feature_count:,} features "
        f"hash={content_hash[:12]}… bytes={bytes_written:,}"
    )

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        tmp_path.unlink(missing_ok=True)
        tmp_dict_path.unlink(missing_ok=True)
        log_run(
            run_id,
            "skipped",
            content_hash=content_hash,
            feed_version="2023",
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        target_path = publish_landing(tmp_path, tmp_dict_path, run_date)
        removed = cleanup_old_landings(retention_days)
        log_run(
            run_id,
            "succeeded",
            content_hash=content_hash,
            feed_version="2023",
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            file_count=1,
            bytes_written=bytes_written,
            target_path=target_path,
            notes=f"cleaned {removed} landing folder(s) older than {retention_days} days",
        )
        print(f"[{run_id}] Succeeded: {target_path} (cleaned {removed} old folder(s))")

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
