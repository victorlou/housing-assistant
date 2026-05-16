# Databricks notebook source
# MAGIC %md
# MAGIC # housing_indicators silver layer
# MAGIC
# MAGIC Typed long-format housing indicator observations from HUD LHS. One
# MAGIC table — `housing_indicator` — preserves the source's tidy shape:
# MAGIC one row per (date, area, theme, series, ethnicity). Gold materialises
# MAGIC pivoted convenience views from this table.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `silver`). Reads from the bronze
# MAGIC pipeline via plain `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"


# COMMAND ----------


@dlt.table(
    name="housing_indicator",
    comment=(
        "HUD Local Housing Statistics observations, typed. Long format — "
        "one row per (date, area, theme, series, ethnicity). Covers 67 NZ "
        "TAs plus the NZ rollup; cadences vary by theme (Affordability "
        "quarterly back to 2001; MSD monthly back to 2017; Sales/Bonds/RPI "
        "as snapshots updated monthly; census series infrequent)."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        _source STRING COMMENT 'Upstream dataset family ("hud").',
        date DATE COMMENT 'End-of-period date for this observation. Cadence depends on the theme/series.',
        area_type STRING COMMENT 'Geographic level: "TA" for territorial authority, "NZ" for the country-wide rollup.',
        area_id STRING COMMENT 'HUDs stable numeric area identifier.',
        area_name STRING COMMENT 'Human-readable area name. For TAs, matches gold.suburb.territorial_authority exactly.',
        theme STRING COMMENT 'Top-level grouping: Affordability, MSD, Sales, Bonds, RPI, Building Consents, Census Tenure, Census Crowding, Census Housing Deprivation, Rent Proportion, population.',
        series STRING COMMENT 'The specific metric within the theme, e.g. "Current Annual Median Sales Price", "Deposit affordability index", "Housing Register".',
        ethnicity STRING COMMENT 'Demographic cut. Mostly null; set for some census series like "Maori Crowding Rank".',
        value DOUBLE COMMENT 'The metric value, cast to DOUBLE. May be null where HUD suppressed for privacy reasons.',
        value_type STRING COMMENT 'Unit hint from HUD: "index", "NZD", "percent", "count", "ratio", etc.',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect_or_drop("has_date", "date IS NOT NULL")
@dlt.expect_or_drop("has_area", "area_name IS NOT NULL")
@dlt.expect_or_drop("has_theme", "theme IS NOT NULL")
@dlt.expect_or_drop("has_series", "series IS NOT NULL")
def housing_indicator():
    raw = spark.read.table(f"{BRONZE}.housing_indicators_hud_lhs_raw")

    return raw.selectExpr(
        "_source",
        "to_date(cast(date AS STRING), 'yyyy-MM-dd') AS date",
        "cast(area_type AS STRING) AS area_type",
        "cast(area_id AS STRING) AS area_id",
        "cast(area_name AS STRING) AS area_name",
        "cast(theme AS STRING) AS theme",
        "cast(series AS STRING) AS series",
        "cast(ethnicity AS STRING) AS ethnicity",
        "cast(value AS DOUBLE) AS value",
        "cast(value_type AS STRING) AS value_type",
        "_ingested_at",
    )
