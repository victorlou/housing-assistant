# Databricks notebook source
# MAGIC %md
# MAGIC # prices silver layer
# MAGIC
# MAGIC Typed quarterly NZ housing-market observations. One table:
# MAGIC `house_price_index` — wide format, one row per (region, quarter) with
# MAGIC four metrics as columns.
# MAGIC
# MAGIC Today every row has `region = "New Zealand"` because RBNZ M10 is
# MAGIC NZ-aggregate only. When a regional source lands (REINZ PDF, paid
# MAGIC feed) it emits rows with proper region names additively — no schema
# MAGIC change.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `silver`). Reads from the bronze
# MAGIC pipeline's tables via plain `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"


# COMMAND ----------


@dlt.table(
    name="house_price_index",
    comment=(
        "RBNZ M10 Housing observations, typed. Wide format — one row per "
        "(region, quarter) with four NZ-aggregate indicators as columns. "
        "Region is currently always 'New Zealand'; future regional sources "
        "drop in additively."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        _source STRING COMMENT 'Upstream dataset family ("rbnz").',
        region STRING COMMENT 'NZ region or "New Zealand" for national rollup. Joins to gold.suburb.region when regional sources land.',
        quarter DATE COMMENT 'First day of the quarter (2024-01-01 = Q1 2024). RBNZ publishes end-of-quarter dates; fetch.py normalises to first-of-quarter.',
        quarter_label STRING COMMENT 'Human-readable quarter label, e.g. "2024-Q1".',
        sales_count INT COMMENT 'Number of residential property transactions settled in the quarter (RBNZ series QVB.Q.MR0H01.na).',
        hpi DOUBLE COMMENT 'House Price Index. Relative; base ≈ 1000 at Q4 2003 (RBNZ series HPI.Q.H01T0.ia).',
        total_value_nzdm DOUBLE COMMENT 'Total value of NZ housing stock in NZD millions, nominal (RBNZ series HHAL.QC1). One-quarter lag from the reference period.',
        residential_investment_nzdm_real DOUBLE COMMENT 'Real residential investment component of GDP, NZD millions in chain-volume terms (RBNZ series GDE.Q.EI24.RA).',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect_or_drop("has_region", "region IS NOT NULL")
@dlt.expect_or_drop("has_quarter", "quarter IS NOT NULL")
@dlt.expect("non_negative_hpi", "hpi IS NULL OR hpi >= 0")
def house_price_index():
    raw = spark.read.table(f"{BRONZE}.prices_rbnz_hpi_raw")

    return raw.selectExpr(
        "_source",
        "cast(region AS STRING) AS region",
        "to_date(cast(quarter AS STRING), 'yyyy-MM-dd') AS quarter",
        # "2024-Q1" form for human display.
        "concat(year(to_date(cast(quarter AS STRING), 'yyyy-MM-dd')), '-Q', "
        "cast((month(to_date(cast(quarter AS STRING), 'yyyy-MM-dd')) - 1) / 3 + 1 AS INT)) AS quarter_label",
        "cast(sales_count AS INT) AS sales_count",
        "cast(hpi AS DOUBLE) AS hpi",
        "cast(total_value_nzdm AS DOUBLE) AS total_value_nzdm",
        "cast(residential_investment_nzdm_real AS DOUBLE) AS residential_investment_nzdm_real",
        "_ingested_at",
    )
