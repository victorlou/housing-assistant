# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 silver layer
# MAGIC
# MAGIC - `census_field_dictionary` — ArcGIS field aliases from the bronze volume landing.
# MAGIC - `census_sa2_area` — latest SA2 snapshot with centroid H3 cell (census QA only).
# MAGIC - `census_sa2_metric` — long-format census counts/medians unpivoted from `VAR_*`.
# MAGIC - `census_sa2_features` — wide curated metrics from `census_2023_gold.yml`.

# COMMAND ----------

import contextlib
import sys
from pathlib import Path

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType
from pyspark.sql.window import Window


def _bundle_files_root() -> Path:
    try:
        return Path(__file__).resolve().parent.parent
    except NameError:
        nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        return Path("/Workspace" + nb).resolve().parent.parent


_bundle_root = _bundle_files_root()
if str(_bundle_root) not in sys.path:
    sys.path.insert(0, str(_bundle_root))

from census_gold_lib import (
    all_feature_export_keys,
    census_year,
    load_gold_manifest,
    pivot_manifest_metrics,
)

BRONZE = "housing.bronze"
VOLUME_ROOT = "/Volumes/housing/bronze/census_2023_files"
_MANIFEST = load_gold_manifest()
_CENSUS_YEAR = census_year(_MANIFEST)

_DATASET_SUBDIRS = (
    ("census_2023_households_sa2", "households_sa2"),
    ("census_2023_dwellings_sa2", "dwellings_sa2"),
    ("census_2023_individuals_sa2", "individuals_sa2"),
)


def _latest_field_dictionary_path(dataset_subdir: str) -> Path:
    csv_name = f"{dataset_subdir}_field_dictionary.csv"
    candidates = sorted(
        Path(VOLUME_ROOT, dataset_subdir).glob(f"*/{csv_name}"),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No {csv_name} under {VOLUME_ROOT}/{dataset_subdir}/<run_date>/; "
            "run the census fetch job first."
        )
    return candidates[0]


def _load_field_dictionary():
    frames = []
    for subdir, name in _DATASET_SUBDIRS:
        try:
            path = _latest_field_dictionary_path(subdir)
        except FileNotFoundError:
            continue
        df = spark.read.option("header", True).csv(str(path)).withColumn("dataset", F.lit(name))
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No census field dictionary CSVs under census_2023_files volume")
    combined = frames[0]
    for df in frames[1:]:
        combined = combined.unionByName(df)
    return (
        combined.withColumn(
            "census_year",
            F.regexp_extract("alias", r"Year:\s*(\d{4})", 1).cast(IntegerType()),
        )
        .withColumn(
            "measure",
            F.regexp_extract("alias", r"Measure:\s*([^,]+)", 1),
        )
        .withColumn(
            "variable_l1",
            F.regexp_extract("alias", r"Var1:\s*([^(]+)", 1),
        )
        .withColumn(
            "variable_l2",
            F.regexp_extract("alias", r"Var2:\s*([^(]+)", 1),
        )
        .withColumn(
            "category",
            F.regexp_extract("alias", r"\(([^)]+)\)\s*$", 1),
        )
    )


@dlt.table(
    name="census_field_dictionary",
    comment="Stats NZ ArcGIS field aliases for census SA2 wide tables.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def census_field_dictionary():
    return _load_field_dictionary()


def _resolve_bronze_table(dataset: str) -> str:
    """Prefer census_2023_* tables; fall back to legacy census_* names in UC."""
    for name in (f"census_2023_{dataset}", f"census_{dataset}"):
        try:
            spark.read.table(f"{BRONZE}.{name}").limit(0).collect()
            return name
        except Exception:
            continue
    raise ValueError(
        f"No bronze census table for {dataset!r}; "
        f"expected census_2023_{dataset} or census_{dataset} in {BRONZE}"
    )


def _latest_bronze(dataset: str):
    """Keep the latest landing per SA2 code."""
    table_name = _resolve_bronze_table(dataset)
    df = spark.read.table(f"{BRONZE}.{table_name}")
    return (
        df.withColumn("_run_date", F.col("_run_date").cast("date"))
        .withColumn(
            "_rank",
            F.row_number().over(Window.partitionBy("sa2_code").orderBy(F.col("_run_date").desc())),
        )
        .filter(F.col("_rank") == 1)
        .drop("_rank")
    )


def _land_area_sq_km(df):
    """Bronze may expose land area under different names depending on deploy/schema evolution."""
    candidates = [
        c for c in ("land_area_sq_km", "LAND_AREA_SQ_KM", "AREA_SQ_KM") if c in df.columns
    ]
    if not candidates:
        return F.lit(None).cast(DoubleType()).alias("land_area_sq_km")
    return F.coalesce(*[F.col(c) for c in candidates]).alias("land_area_sq_km")


@dlt.table(
    name="census_sa2_area",
    comment="SA2 areas from the latest households bronze landing with H3 centroid cell.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def census_sa2_area():
    hh = _latest_bronze("households_sa2")
    return hh.select(
        F.col("sa2_code"),
        F.col("sa2_name"),
        F.col("sa2_name_ascii"),
        _land_area_sq_km(hh),
        F.col("_run_date").alias("source_run_date"),
        # H3 from GeoJSON is deferred: geometry_json from Auto Loader is not always
        # valid GeoJSON for ST_GeomFromGeoJSON on this runtime. Join SA2 boundaries later.
        F.lit(None).cast("long").alias("h3_cell_res8"),
    )


def _unpivot_metrics(dataset: str):
    df = _latest_bronze(dataset)
    var_cols = [c for c in df.columns if c.startswith("VAR_")]
    if not var_cols:
        raise ValueError(f"No VAR_* columns found in {dataset}")

    stack_parts = []
    for col in var_cols:
        stack_parts.append(f"'{col}'")
        stack_parts.append(f"CAST(`{col}` AS DOUBLE)")
    stack_expr = f"stack({len(var_cols)}, {', '.join(stack_parts)})"

    return (
        df.select(
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("_run_date").alias("source_run_date"),
            F.expr(stack_expr).alias("field_name", "value_raw"),
        )
        .withColumn("dataset", F.lit(dataset))
        .withColumn(
            "value",
            F.when(F.col("value_raw") < 0, F.lit(None).cast(DoubleType())).otherwise(
                F.col("value_raw")
            ),
        )
        .drop("value_raw")
    )


@dlt.table(
    name="census_sa2_metric",
    comment="Long-format census metrics by SA2 with parsed field metadata.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def census_sa2_metric():
    parts = [
        _unpivot_metrics("households_sa2"),
        _unpivot_metrics("dwellings_sa2"),
    ]
    with contextlib.suppress(Exception):
        parts.append(_unpivot_metrics("individuals_sa2"))
    metrics = parts[0]
    for part in parts[1:]:
        metrics = metrics.unionByName(part)
    dictionary = dlt.read("census_field_dictionary")
    return metrics.join(
        dictionary.select(
            "dataset",
            "field_name",
            "alias",
            "census_year",
            "measure",
            "variable_l1",
            "variable_l2",
            "category",
        ),
        on=["dataset", "field_name"],
        how="left",
    )


@dlt.table(
    name="census_sa2_features",
    comment="Wide curated 2023 Census metrics per SA2 from census_2023_gold.yml.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def census_sa2_features():
    metrics = dlt.read("census_sa2_metric")
    wide = pivot_manifest_metrics(metrics, all_feature_export_keys(_MANIFEST), _MANIFEST)
    return (
        wide.withColumn("census_year", F.lit(_CENSUS_YEAR))
        .withColumn(
            "owner_occupier_pct",
            F.when(
                F.col("tenure_total_stated") > 0,
                F.col("tenure_owned") / F.col("tenure_total_stated"),
            ),
        )
        .withColumn(
            "percent_crowded",
            F.when(
                F.col("households_crowding_total_stated") > 0,
                F.col("households_crowded") / F.col("households_crowding_total_stated"),
            ),
        )
        .withColumn("_updated_at", F.current_timestamp())
    )
