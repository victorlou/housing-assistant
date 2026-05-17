# Databricks notebook source
# MAGIC %pip install openpyxl

# COMMAND ----------

# Databricks serverless ships pandas but not openpyxl (its Excel backend).
# Install + restart so the rest of the notebook can `pd.read_excel(...)`.
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md
# MAGIC # housing_indicators fetch — HUD LHS XLSX (volume-read)
# MAGIC
# MAGIC Reads the most recent HUD Local Housing Statistics XLSX from the
# MAGIC bronze volume and writes a CSV alongside for Auto Loader to stream:
# MAGIC
# MAGIC - input:  `_xlsx/<dataset>/<date>.xlsx`  (manually uploaded by an operator)
# MAGIC - output: `<dataset>/<date>.csv`         (already tidy long format)
# MAGIC
# MAGIC ## What the HUD file looks like
# MAGIC
# MAGIC Two sheets: `Instructions` (boilerplate) and `Metrics`. We only care
# MAGIC about `Metrics`, which is already in tidy long format with columns:
# MAGIC `date / area_type / area_id / area_name / theme / series / ethnicity
# MAGIC / value / value_type`. Each row is one observation. Beautifully
# MAGIC ingestible — no pivot, no header gymnastics, just read and write.
# MAGIC
# MAGIC ## Why volume-read
# MAGIC
# MAGIC Same pattern as `pipelines/prices/`. HUD doesn't appear to have
# MAGIC Cloudflare protection on the file (browser downloads work cleanly),
# MAGIC so a follow-up PR could attempt automated URL fetch. For now, manual
# MAGIC monthly upload — the dashboard refreshes monthly and the file URL
# MAGIC carries a month-stamp anyway, so the manual touch is once a month.

# COMMAND ----------

import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
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

BRONZE_VOLUME = "/Volumes/housing/bronze/housing_indicators_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"
RAW_SUBDIR = "_xlsx"

# HUD LHS sheet name. The header is row 0, data starts at row 1. We expect
# columns: date, area_type, area_id, area_name, theme, series, ethnicity,
# value, value_type. Anything missing or extra is handled defensively below.
LHS_SHEET = "Metrics"

# Sanity floor — if HUD ever ships a release with implausibly few rows
# (e.g. broken upstream extract), fail loudly rather than silently
# replacing decent data.
MIN_EXPECTED_ROWS = 1_000

dbutils.widgets.text("dataset", "hud_lhs", "Dataset identifier")
dbutils.widgets.text("retention_days", "365", "Retention (days) for parsed CSV outputs")

dataset = dbutils.widgets.get("dataset").strip()
retention_days = int(dbutils.widgets.get("retention_days"))

SOURCE_NAME = f"housing_indicators_{dataset}"

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
# MAGIC ## Parse HUD LHS XLSX
# MAGIC
# MAGIC HUD's `Metrics` sheet is already tidy long format. We read with
# MAGIC `header=0`, normalize column names, and write straight to CSV.

# COMMAND ----------

# Expected columns in the Metrics sheet — used to validate the file shape
# on every run so a HUD restructure fails the fetch loudly rather than
# silently corrupting downstream.
EXPECTED_COLUMNS = {
    "date",
    "area_type",
    "area_id",
    "area_name",
    "theme",
    "series",
    "ethnicity",
    "value",
    "value_type",
}


def parse_lhs(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(
        xlsx_path,
        sheet_name=LHS_SHEET,
        header=0,
        dtype=str,
        engine="openpyxl",
    )

    # Normalise: lowercase column names, strip whitespace.
    df.columns = [str(c).strip() for c in df.columns]
    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"HUD LHS sheet {LHS_SHEET!r} is missing expected columns "
            f"{sorted(missing)}. Got {sorted(df.columns)}. "
            "Has HUD restructured the file?"
        )

    if len(df) < MIN_EXPECTED_ROWS:
        raise ValueError(
            f"HUD LHS sheet {LHS_SHEET!r} only has {len(df):,} rows; "
            f"expected at least {MIN_EXPECTED_ROWS:,}. Suspect a broken extract."
        )

    # Drop rows without a date or an area; everything else passes through
    # to silver, which applies the heavier expectations.
    df = df[df["date"].notna() & df["area_name"].notna()].copy()

    # Normalize the date format to YYYY-MM-DD so bronze Auto Loader infers
    # it correctly. HUD ships datetime cells which excel writes as strings
    # like "2024-03-31 00:00:00" — keep just the date portion.
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["date"].notna()]

    return df[
        [
            "date",
            "area_type",
            "area_id",
            "area_name",
            "theme",
            "series",
            "ethnicity",
            "value",
            "value_type",
        ]
    ]


# COMMAND ----------
# MAGIC %md
# MAGIC ## Locate the latest manually-uploaded XLSX

# COMMAND ----------


def latest_xlsx_path() -> Path:
    upload_dir = Path(BRONZE_VOLUME) / RAW_SUBDIR / dataset
    if not upload_dir.exists():
        raise FileNotFoundError(
            f"Upload directory {upload_dir} does not exist yet. "
            "Manually upload the HUD LHS XLSX first — see README."
        )
    candidates = sorted(
        (p for p in upload_dir.iterdir() if p.suffix.lower() == ".xlsx"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No .xlsx files in {upload_dir}. "
            "Manually upload the HUD LHS XLSX first — see README."
        )
    return candidates[-1]


def write_csv(long_df: pd.DataFrame, source_xlsx: Path) -> tuple[str, int]:
    csv_dir = Path(BRONZE_VOLUME) / dataset
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / f"{source_xlsx.stem}.csv"
    long_df.to_csv(csv_path, index=False)
    return str(csv_path), csv_path.stat().st_size


def cleanup_old_parsed_csvs(retention_days: int) -> int:
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
    xlsx_path = latest_xlsx_path()
    print(f"[{run_id}] Parsing {xlsx_path.name} from {xlsx_path.parent}")

    xlsx_bytes = xlsx_path.read_bytes()
    content_hash = hashlib.sha256(xlsx_bytes).hexdigest()
    print(
        f"[{run_id}] dataset={dataset} bytes={len(xlsx_bytes):,} "
        f"hash={content_hash[:12]}…"
    )

    last_hash = last_successful_content_hash()
    if last_hash and content_hash == last_hash:
        log_run(
            run_id,
            "skipped",
            source_url_repr=str(xlsx_path),
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            notes="content unchanged (hash matches last successful run)",
        )
        print(f"[{run_id}] Skipped: content_hash matches last run")
    else:
        long_df = parse_lhs(xlsx_path)
        n_tas = long_df[long_df["area_type"] == "TA"]["area_name"].nunique()
        n_themes = long_df["theme"].nunique()
        print(
            f"[{run_id}] Parsed {len(long_df):,} rows · {n_tas} TAs · "
            f"{n_themes} themes · dates {long_df['date'].min()} → {long_df['date'].max()}"
        )

        csv_path, csv_size = write_csv(long_df, xlsx_path)
        removed = cleanup_old_parsed_csvs(retention_days)

        log_run(
            run_id,
            "succeeded",
            source_url_repr=str(xlsx_path),
            content_hash=content_hash,
            fetched_at=started_at,
            duration_seconds=time.time() - t0,
            file_count=1,
            bytes_written=csv_size,
            target_path=csv_path,
            notes=(
                f"parsed {len(long_df):,} rows · {n_tas} TAs · {n_themes} themes "
                f"from {xlsx_path.name}; cleaned up {removed} old CSV(s) "
                f">{retention_days} days"
            ),
        )
        print(
            f"[{run_id}] Succeeded: {csv_size:,} bytes at {csv_path} "
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
