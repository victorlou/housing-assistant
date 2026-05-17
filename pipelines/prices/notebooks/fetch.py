# Databricks notebook source
# MAGIC %pip install openpyxl

# COMMAND ----------

# Databricks serverless ships pandas but not openpyxl (its Excel backend),
# so we install at the top of this notebook and restart Python so the import
# takes effect for the rest of the run. Local to this notebook rather than
# pinned at the bundle/environment level — keeps the dependency next to the
# code that needs it.
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md
# MAGIC # prices fetch — RBNZ M10 Housing XLSX (volume-read, wide-format)
# MAGIC
# MAGIC Reads the most recent RBNZ M10 Housing XLSX from the bronze volume
# MAGIC and writes a tidy wide CSV alongside it for Auto Loader to stream:
# MAGIC
# MAGIC - input:  `_xlsx/<dataset>/<date>.xlsx`  (manually uploaded by an operator)
# MAGIC - output: `<dataset>/<date>.csv`         (one row per quarter, columns per metric)
# MAGIC
# MAGIC ## What M10 actually contains
# MAGIC
# MAGIC M10 publishes four **NZ-aggregate** indicators per quarter:
# MAGIC
# MAGIC | Column | Series | Unit | Notes |
# MAGIC |---|---|---|---|
# MAGIC | House sales | QVB.Q.MR0H01.na | count | Transactions that settled in the quarter |
# MAGIC | House price index (HPI) | HPI.Q.H01T0.ia | index | Base 1000 ≈ Q4 2003 |
# MAGIC | Total value of housing stock | HHAL.QC1 | NZD millions | One quarter lag |
# MAGIC | Residential investment (GDP) | GDE.Q.EI24.RA | NZD millions, real | GDP component |
# MAGIC
# MAGIC There's **no regional split** — every row is the whole country. The gold
# MAGIC table keeps `region` as a discriminator and pins it to `"New Zealand"`
# MAGIC so a future regional source (REINZ PDF / paid feed) drops in additively
# MAGIC without a schema change.
# MAGIC
# MAGIC ## Why volume-read instead of URL fetch?
# MAGIC
# MAGIC RBNZ's CDN sits behind Cloudflare Bot Management — automated download
# MAGIC from any Python HTTP client 403s on the JS challenge. Manual quarterly
# MAGIC upload is the path of least resistance. See README → "Refreshing the
# MAGIC RBNZ XLSX".

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

BRONZE_VOLUME = "/Volumes/housing/bronze/prices_files"
INGEST_RUNS_TABLE = "housing.bronze.ingest_runs"
RAW_SUBDIR = "_xlsx"

# RBNZ M10 sheet name + the canonical column titles we expect to find in
# the header row. If RBNZ rename a column, this is the spot to update.
M10_SHEET = "Data"
M10_HEADER_ROW = 0   # row index (0-based) where the column titles live
M10_DATA_START = 5   # row index where the actual quarterly rows begin

# Maps the RBNZ column title → output column name. Any title not in this
# map is silently skipped, so RBNZ adding new metrics doesn't break us.
M10_METRIC_COLUMNS = {
    "House sales": "sales_count",
    "House price index (HPI)": "hpi",
    "Total value of housing stock": "total_value_nzdm",
    "Residential investment (GDP)": "residential_investment_nzdm_real",
}

# Synthetic region for NZ-aggregate rows. When regional sources land
# (REINZ PDF, Stats NZ Property Transfers), they emit rows with proper
# region names like "Auckland Region".
NATIONAL_REGION = "New Zealand"

dbutils.widgets.text("dataset", "rbnz_hpi", "Dataset identifier")
dbutils.widgets.text("retention_days", "365", "Retention (days) for parsed CSV outputs")

dataset = dbutils.widgets.get("dataset").strip()
retention_days = int(dbutils.widgets.get("retention_days"))

SOURCE_NAME = f"prices_{dataset}"

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
# MAGIC ## Parse M10 XLSX

# COMMAND ----------


def _quarter_first_day(end_of_quarter_dt: pd.Timestamp) -> str:
    """RBNZ uses end-of-quarter dates (2026-03-31 = Q1). Normalise to first-of-quarter."""
    q = (end_of_quarter_dt.month - 1) // 3 + 1
    month = {1: 1, 2: 4, 3: 7, 4: 10}[q]
    return f"{end_of_quarter_dt.year:04d}-{month:02d}-01"


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_m10(xlsx_path: Path) -> pd.DataFrame:
    """
    Parse the M10 Data sheet into wide format. Returns columns:
      region, quarter, sales_count, hpi, total_value_nzdm,
      residential_investment_nzdm_real
    """
    df = pd.read_excel(
        xlsx_path,
        sheet_name=M10_SHEET,
        header=None,
        dtype=str,
        engine="openpyxl",
    )

    if len(df) <= M10_DATA_START:
        raise ValueError(
            f"M10 sheet {M10_SHEET!r} has only {len(df)} rows; expected the "
            f"data section to start at row {M10_DATA_START}. "
            "Has RBNZ restructured the file?"
        )

    titles = df.iloc[M10_HEADER_ROW].fillna("").astype(str).str.strip().tolist()
    # The first column is unlabelled in row 0 — it's the date column.
    date_col_idx = 0

    # Map RBNZ column index → output column name, dropping anything we don't know about.
    metric_col_indices: dict[int, str] = {}
    for idx, title in enumerate(titles):
        if idx == date_col_idx:
            continue
        out_name = M10_METRIC_COLUMNS.get(title)
        if out_name:
            metric_col_indices[idx] = out_name

    if not metric_col_indices:
        raise ValueError(
            "None of the expected M10 columns matched the header row "
            f"{titles!r}. Either RBNZ renamed columns or the header_row "
            "constant is wrong."
        )

    body = df.iloc[M10_DATA_START:].reset_index(drop=True)
    rows = []
    for _, raw in body.iterrows():
        date_raw = raw.iloc[date_col_idx]
        if pd.isna(date_raw):
            continue
        try:
            dt = pd.to_datetime(date_raw, errors="raise")
        except (ValueError, TypeError):
            continue
        record = {
            "region": NATIONAL_REGION,
            "quarter": _quarter_first_day(dt),
        }
        for col_idx, out_name in metric_col_indices.items():
            record[out_name] = _to_float(raw.iloc[col_idx])
        # Drop rows where every metric is null (footers, blank lines).
        if all(record.get(c) is None for c in metric_col_indices.values()):
            continue
        rows.append(record)

    if not rows:
        raise ValueError(
            f"Parsed 0 quarterly rows from {xlsx_path.name}. "
            f"Data start row is {M10_DATA_START} — adjust if RBNZ changed it."
        )
    return pd.DataFrame(rows)


# COMMAND ----------
# MAGIC %md
# MAGIC ## Locate the latest manually-uploaded XLSX

# COMMAND ----------


def latest_xlsx_path() -> Path:
    upload_dir = Path(BRONZE_VOLUME) / RAW_SUBDIR / dataset
    if not upload_dir.exists():
        raise FileNotFoundError(
            f"Upload directory {upload_dir} does not exist yet. "
            "Manually upload the RBNZ M10 XLSX first — see README."
        )
    candidates = sorted(
        (p for p in upload_dir.iterdir() if p.suffix.lower() == ".xlsx"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No .xlsx files in {upload_dir}. "
            "Manually upload the RBNZ M10 XLSX first — see README."
        )
    return candidates[-1]


def write_csv(wide_df: pd.DataFrame, source_xlsx: Path) -> tuple[str, int]:
    csv_dir = Path(BRONZE_VOLUME) / dataset
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / f"{source_xlsx.stem}.csv"
    wide_df.to_csv(csv_path, index=False)
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
        wide_df = parse_m10(xlsx_path)
        print(
            f"[{run_id}] Parsed {len(wide_df):,} quarters "
            f"(first {wide_df['quarter'].min()}, last {wide_df['quarter'].max()}), "
            f"columns: {[c for c in wide_df.columns if c not in ('region', 'quarter')]}"
        )

        csv_path, csv_size = write_csv(wide_df, xlsx_path)
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
                f"parsed {len(wide_df):,} quarters from {xlsx_path.name}; "
                f"cleaned up {removed} old CSV(s) >{retention_days} days"
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
