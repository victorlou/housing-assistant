# Databricks notebook source
# MAGIC %md
# MAGIC # prices gold layer
# MAGIC
# MAGIC The contract table consumers (Genie, the agent, the consumer view)
# MAGIC join against:
# MAGIC
# MAGIC - `housing.gold.region__quarter` — RBNZ M10
# MAGIC   indicators plus a derived year-on-year HPI % change computed via a
# MAGIC   4-quarter `LAG` window per region.
# MAGIC
# MAGIC Today every row has `region = "New Zealand"` (M10 is NZ-aggregate).
# MAGIC When a regional source lands, this table fills with proper region
# MAGIC names without schema change, and joins to `gold.suburb` start
# MAGIC returning useful per-region values for any suburb.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `gold`). Reads from the silver
# MAGIC pipeline via `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql import Window

SILVER = "housing.silver"


# COMMAND ----------


@dlt.table(
    name="region__quarter",
    comment=(
        "Time-series fact at NZ-region + quarter grain. One row per (region, "
        "quarter). Today every row carries region = 'New Zealand' because "
        "the only source — RBNZ M10 Housing — publishes at country-aggregate "
        "level only. When a regional source lands (REINZ, Stats NZ property "
        "transfers), this table fills with proper region values without "
        "schema change. Joins to housing.gold.suburb on region. HPI YoY % "
        "change is derived in-table via a 4-quarter LAG window per region. "
        "Naming: follows the <spatial_dim>__<time_grain> convention — see "
        "docs/conventions.md."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["region"],
    schema="""
        region STRING NOT NULL COMMENT 'NZ region name, Stats-NZ-aligned (e.g. "Auckland Region"), or the synthetic value "New Zealand" for the country-wide rollup. Joins to gold.suburb.region.',
        quarter DATE NOT NULL COMMENT 'First day of the quarter (e.g. 2024-01-01 = Q1 2024).',
        quarter_label STRING NOT NULL COMMENT 'Human-readable quarter label, e.g. "2024-Q1".',
        hpi DOUBLE COMMENT 'House Price Index (relative; base ≈ 1000 at Q4 2003).',
        hpi_yoy_pct DOUBLE COMMENT 'Year-on-year % change in HPI (4-quarter LAG window per region). Null for the first year of each region.',
        sales_count INT COMMENT 'Number of residential property transactions settled in the quarter.',
        total_value_nzdm DOUBLE COMMENT 'Total value of NZ housing stock in NZD millions (nominal).',
        residential_investment_nzdm_real DOUBLE COMMENT 'Real residential investment component of GDP, NZD millions (chain-volume).',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_region", "region IS NOT NULL")
@dlt.expect_or_drop("has_quarter", "quarter IS NOT NULL")
def region__quarter():
    silver = spark.read.table(f"{SILVER}.house_price_index")

    # YoY: lag 4 quarters within each region, compute % delta against the
    # earlier value. Null for rows where there's no 4-quarter-ago observation
    # (the first year of each region).
    yoy_window = Window.partitionBy("region").orderBy("quarter")
    hpi_lag = F.lag("hpi", 4).over(yoy_window)
    hpi_yoy_pct = F.when(
        hpi_lag.isNotNull() & (hpi_lag != 0),
        F.round((F.col("hpi") - hpi_lag) / hpi_lag * 100, 2),
    )

    return silver.select(
        F.col("region"),
        F.col("quarter"),
        F.col("quarter_label"),
        F.col("hpi"),
        hpi_yoy_pct.alias("hpi_yoy_pct"),
        F.col("sales_count"),
        F.col("total_value_nzdm"),
        F.col("residential_investment_nzdm_real"),
        F.current_timestamp().alias("_updated_at"),
    )
