# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 gold layer
# MAGIC
# MAGIC Genie-ready SA2 marts (suburb grain = SA2). Canonical geography lives in
# MAGIC `housing.gold.suburb` (places pipeline); enrich that dim via
# MAGIC `housing.silver.census_sa2_features`.

# COMMAND ----------

import sys
from pathlib import Path

import dlt
from pyspark.sql import functions as F


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
    metric_specs,
    pivot_manifest_metrics,
)

SILVER = "housing.silver"
_MANIFEST = load_gold_manifest()
_CENSUS_YEAR = census_year(_MANIFEST)


def _with_census_year(df):
    return df.select(F.lit(_CENSUS_YEAR).alias("census_year"), "*")


@dlt.table(
    name="income__year__suburb",
    comment="Median household income from 2023 Census by SA2.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT COMMENT 'Census reference year (2023).',
        sa2_code STRING COMMENT 'Stats NZ SA2 2023 code. Join to gold.suburb.suburb_id.',
        sa2_name STRING COMMENT 'Official SA2 name.',
        median_household_income DOUBLE COMMENT 'Median total household income ($, before tax).',
        households_total INT COMMENT 'Households in occupied private dwellings.',
        households_income_stated INT COMMENT 'Households with stated income.'
    """,
)
def income__year__suburb():
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric")
    keys = _MANIFEST["marts"]["income__year__suburb"]
    wide = pivot_manifest_metrics(metrics, keys, _MANIFEST)
    return _with_census_year(
        wide.select(
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("median_household_income"),
            F.col("households_total").cast("int"),
            F.col("households_income_stated").cast("int"),
        )
    )


@dlt.table(
    name="tenure__year__suburb",
    comment="2023 Census tenure counts and owner-occupier share by SA2.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT,
        sa2_code STRING,
        sa2_name STRING,
        tenure_owned INT COMMENT 'Households in dwellings owned or partly owned.',
        tenure_not_owned INT COMMENT 'Households in dwellings not owned and not in a family trust.',
        tenure_total_stated INT,
        owner_occupier_pct DOUBLE COMMENT 'tenure_owned / tenure_total_stated when stated > 0.'
    """,
)
def tenure__year__suburb():
    features = spark.read.table(f"{SILVER}.census_sa2_features")
    return _with_census_year(
        features.select(
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("tenure_owned").cast("int"),
            F.col("tenure_not_owned").cast("int"),
            F.col("tenure_total_stated").cast("int"),
            F.col("owner_occupier_pct"),
        )
    )


@dlt.table(
    name="rent__year__suburb",
    comment="2023 Census median weekly rent for renting households by SA2.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT,
        sa2_code STRING,
        sa2_name STRING,
        median_weekly_rent DOUBLE COMMENT 'Median weekly rent ($) for renting households.',
        renting_households_total INT,
        renting_households_stated INT
    """,
)
def rent__year__suburb():
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric")
    keys = _MANIFEST["marts"]["rent__year__suburb"]
    wide = pivot_manifest_metrics(metrics, keys, _MANIFEST)
    return _with_census_year(
        wide.select(
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("median_weekly_rent"),
            F.col("renting_households_total").cast("int"),
            F.col("renting_households_stated").cast("int"),
        )
    )


@dlt.table(
    name="dwelling__year__suburb",
    comment="2023 Census dwelling quality and household crowding by SA2.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT,
        sa2_code STRING,
        sa2_name STRING,
        households_crowded INT,
        households_crowding_total_stated INT,
        percent_crowded DOUBLE COMMENT 'households_crowded / households_crowding_total_stated.',
        dwellings_always_damp INT,
        dwellings_sometimes_damp INT,
        dwellings_damp_total_stated INT,
        dwellings_mould_a4_always INT,
        dwellings_mould_total_stated INT,
        dwellings_no_heating INT,
        dwellings_mean_rooms DOUBLE
    """,
)
def dwelling__year__suburb():
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric")
    keys = _MANIFEST["marts"]["dwelling__year__suburb"]
    wide = pivot_manifest_metrics(metrics, keys, _MANIFEST)
    crowding = spark.read.table(f"{SILVER}.census_sa2_features").select(
        F.col("sa2_code"),
        F.col("households_crowded").cast("int"),
        F.col("households_crowding_total_stated").cast("int"),
        F.col("percent_crowded"),
    )
    return _with_census_year(
        wide.join(crowding, on="sa2_code", how="left").select(
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("households_crowded"),
            F.col("households_crowding_total_stated"),
            F.col("percent_crowded"),
            F.col("dwellings_always_damp").cast("int"),
            F.col("dwellings_sometimes_damp").cast("int"),
            F.col("dwellings_damp_total_stated").cast("int"),
            F.col("dwellings_mould_a4_always").cast("int"),
            F.col("dwellings_mould_total_stated").cast("int"),
            F.col("dwellings_no_heating").cast("int"),
            F.col("dwellings_mean_rooms"),
        )
    )


@dlt.table(
    name="census_metric__year__sa2",
    comment="Long-format curated 2023 Census metrics by SA2 for open-ended Genie queries.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["topic"],
    schema="""
        census_year INT,
        sa2_code STRING,
        sa2_name STRING,
        topic STRING COMMENT 'High-level topic from field dictionary variable_l1.',
        measure STRING,
        category STRING,
        field_name STRING,
        value DOUBLE,
        _updated_at TIMESTAMP
    """,
)
def census_metric__year__sa2():
    specs = metric_specs(_MANIFEST)
    keys = [
        (specs[k]["dataset"], specs[k]["field_name"]) for k in all_feature_export_keys(_MANIFEST)
    ]
    keys_df = spark.createDataFrame(keys, ["dataset", "field_name"])
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric")
    return metrics.join(keys_df, on=["dataset", "field_name"], how="inner").select(
        F.lit(_CENSUS_YEAR).alias("census_year"),
        F.col("sa2_code"),
        F.col("sa2_name"),
        F.trim(F.col("variable_l1")).alias("topic"),
        F.col("measure"),
        F.col("category"),
        F.col("field_name"),
        F.col("value"),
        F.current_timestamp().alias("_updated_at"),
    )
