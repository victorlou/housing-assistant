# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 silver layer
# MAGIC
# MAGIC - `census_field_dictionary` — ArcGIS field aliases from the bronze volume landing.
# MAGIC - `census_sa2_area` — latest SA2 snapshot with centroid H3 cell.
# MAGIC - `census_sa2_metric` — long-format census counts/medians unpivoted from `VAR_*`.

# COMMAND ----------

from pathlib import Path

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType
from pyspark.sql.window import Window

BRONZE = "housing.bronze"
VOLUME_ROOT = "/Volumes/housing/bronze/census_files"

_DATASET_SUBDIRS = (
    ("census_2023_households_sa2", "households_sa2"),
    ("census_2023_dwellings_sa2", "dwellings_sa2"),
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
        path = _latest_field_dictionary_path(subdir)
        df = spark.read.option("header", True).csv(str(path)).withColumn("dataset", F.lit(name))
        frames.append(df)
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


def _latest_bronze(table_name: str):
    """Keep the latest landing per SA2 code."""
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


@dlt.table(
    name="census_sa2_area",
    comment="SA2 areas from the latest households bronze landing with H3 centroid cell.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def census_sa2_area():
    hh = _latest_bronze("census_households_sa2")
    return hh.select(
        F.col("sa2_code"),
        F.col("sa2_name"),
        F.col("sa2_name_ascii"),
        F.coalesce(F.col("land_area_sq_km"), F.col("AREA_SQ_KM")).alias("land_area_sq_km"),
        F.col("_run_date").alias("source_run_date"),
        F.expr(
            "h3_longlatash3("
            "cast(ST_X(ST_Centroid(ST_GeomFromGeoJSON(geometry_json))) as double), "
            "cast(ST_Y(ST_Centroid(ST_GeomFromGeoJSON(geometry_json))) as double), "
            "8)"
        ).alias("h3_cell_res8"),
    )


def _unpivot_metrics(bronze_table: str, dataset: str):
    df = _latest_bronze(bronze_table)
    var_cols = [c for c in df.columns if c.startswith("VAR_")]
    if not var_cols:
        raise ValueError(f"No VAR_* columns found in {bronze_table}")

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
    hh = _unpivot_metrics("census_households_sa2", "households_sa2")
    dw = _unpivot_metrics("census_dwellings_sa2", "dwellings_sa2")
    metrics = hh.unionByName(dw)
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
