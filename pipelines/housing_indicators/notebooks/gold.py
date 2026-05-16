# Databricks notebook source
# MAGIC %md
# MAGIC # housing_indicators gold layer
# MAGIC
# MAGIC Four contract tables consumers join against:
# MAGIC
# MAGIC 1. `housing.gold.housing_indicator__month__ta` — the long-format fact,
# MAGIC    one row per (date, area, theme, series, ethnicity). Source of truth.
# MAGIC 2. `housing.gold.house_price__month__ta` — Sales theme pivoted wide.
# MAGIC 3. `housing.gold.rent_price__month__ta` — Bonds theme pivoted wide.
# MAGIC 4. `housing.gold.affordability__quarter__ta` — Affordability theme
# MAGIC    pivoted wide (quarterly time series back to 2001).
# MAGIC
# MAGIC All four join to `gold.suburb` on `ta_name = suburb.territorial_authority`
# MAGIC for per-suburb roll-ups of housing indicators.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `gold`). Reads from the silver
# MAGIC pipeline via `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"


# COMMAND ----------
# MAGIC %md
# MAGIC ## Long-format fact

# COMMAND ----------


@dlt.table(
    name="housing_indicator__month__ta",
    comment=(
        "Long-format NZ housing indicators by area + date + theme + series. "
        "Source of truth from HUD Local Housing Statistics; pivoted views in "
        "this schema materialise common cuts. area_type is 'TA' for the 67 "
        "territorial authorities or 'NZ' for the country-wide rollup."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["theme"],
    schema="""
        ta_name STRING NOT NULL COMMENT 'Area name. For TAs, matches gold.suburb.territorial_authority. "New Zealand" for the country-wide rollup.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        area_type STRING COMMENT '"TA" for territorial authority, "NZ" for country-wide rollup.',
        date DATE NOT NULL COMMENT 'End-of-period for this observation. Cadence varies by theme.',
        theme STRING NOT NULL COMMENT 'Top-level grouping (Affordability, MSD, Sales, Bonds, etc.).',
        series STRING NOT NULL COMMENT 'Specific metric within the theme.',
        ethnicity STRING COMMENT 'Demographic cut. Mostly null.',
        value DOUBLE COMMENT 'The metric value.',
        value_type STRING COMMENT 'Unit hint: "index", "NZD", "percent", "count", "ratio", etc.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_ta_name", "ta_name IS NOT NULL")
@dlt.expect_or_drop("has_date", "date IS NOT NULL")
def housing_indicator__month__ta():
    silver = spark.read.table(f"{SILVER}.housing_indicator")
    return silver.select(
        F.col("area_name").alias("ta_name"),
        F.col("area_id").alias("ta_code"),
        F.col("area_type"),
        F.col("date"),
        F.col("theme"),
        F.col("series"),
        F.col("ethnicity"),
        F.col("value"),
        F.col("value_type"),
        F.current_timestamp().alias("_updated_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## Pivoted helper
# MAGIC
# MAGIC Each of the three pivoted tables follows the same pattern: filter the
# MAGIC long-format silver to a single theme, drop demographic cuts
# MAGIC (`ethnicity IS NULL`), then collapse the `series` dimension into named
# MAGIC output columns.
# MAGIC
# MAGIC We use **conditional aggregation** rather than `GroupedData.pivot()`:
# MAGIC DLT bans `pivot()` inside `@dlt.table` functions because it forces a
# MAGIC materialised eager evaluation. `F.first(F.when(cond, value))` does
# MAGIC the same job purely declaratively.

# COMMAND ----------


def _pivot_theme(theme: str, series_to_column: dict[str, str]):
    """
    Collapse the `series` dimension into wide named columns for one theme.

    `series_to_column` maps the exact HUD series name → the output column
    name. Any series not in the map is dropped.
    """
    src = (
        spark.read.table(f"{SILVER}.housing_indicator")
        .filter(F.col("theme") == theme)
        .filter(F.col("ethnicity").isNull())  # drop demographic cuts
        .filter(F.col("series").isin(list(series_to_column.keys())))
    )

    return src.groupBy("area_name", "area_id", "area_type", "date").agg(
        *[
            F.first(
                F.when(F.col("series") == raw_name, F.col("value")),
                ignorenulls=True,
            ).alias(out_name)
            for raw_name, out_name in series_to_column.items()
        ]
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## house_price__month__ta (Sales theme)

# COMMAND ----------


HOUSE_PRICE_SERIES = {
    "Current House Price Index": "current_hpi",
    "Current Annual Median Sales Price": "current_annual_median_sales_nzd",
    "Current Annual Lower Quartile Sales Price": "current_annual_lower_q_sales_nzd",
    "Current number of Annual Sales volume": "annual_sales_volume",
}


@dlt.table(
    name="house_price__month__ta",
    comment=(
        "TA-level NZ house-price snapshot from HUD's Sales theme. Each row is "
        "the snapshot as of `date` for one TA (or 'New Zealand'). The values "
        "are rolling-annual aggregates published by HUD. To build a time "
        "series, ingest this table across multiple refreshes."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        ta_name STRING NOT NULL COMMENT 'TA name (or "New Zealand"). Joins to gold.suburb.territorial_authority.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        date DATE NOT NULL COMMENT 'Snapshot date when HUD published these aggregates.',
        current_hpi DOUBLE COMMENT 'House Price Index, current value.',
        current_annual_median_sales_nzd DOUBLE COMMENT 'Median residential sale price (NZD) over the trailing 12 months.',
        current_annual_lower_q_sales_nzd DOUBLE COMMENT 'Lower-quartile residential sale price (NZD) over the trailing 12 months.',
        annual_sales_volume INT COMMENT 'Count of residential sales over the trailing 12 months.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
def house_price__month__ta():
    pivoted = _pivot_theme("Sales", HOUSE_PRICE_SERIES)
    return pivoted.select(
        F.col("area_name").alias("ta_name"),
        F.col("area_id").alias("ta_code"),
        F.col("date"),
        F.col("current_hpi").cast("double"),
        F.col("current_annual_median_sales_nzd").cast("double"),
        F.col("current_annual_lower_q_sales_nzd").cast("double"),
        F.col("annual_sales_volume").cast("int"),
        F.current_timestamp().alias("_updated_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## rent_price__month__ta (Bonds theme)

# COMMAND ----------


RENT_PRICE_SERIES = {
    "Median Rent Price": "median_rent_nzd",
    "Average Rent Price": "average_rent_nzd",
    "Lower Quartile Rent Price": "lower_quartile_rent_nzd",
}


@dlt.table(
    name="rent_price__month__ta",
    comment=(
        "TA-level NZ rent-price snapshot from HUD's Bonds theme (sourced "
        "from MBIE rental bond lodgements). Rolling-annual aggregates per "
        "snapshot date — accumulate across refreshes for a time series."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        ta_name STRING NOT NULL COMMENT 'TA name (or "New Zealand"). Joins to gold.suburb.territorial_authority.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        date DATE NOT NULL COMMENT 'Snapshot date when HUD published these aggregates.',
        median_rent_nzd DOUBLE COMMENT 'Weekly median rent price (NZD) over the trailing 12 months.',
        average_rent_nzd DOUBLE COMMENT 'Weekly average rent price (NZD) over the trailing 12 months.',
        lower_quartile_rent_nzd DOUBLE COMMENT 'Weekly lower-quartile rent price (NZD) over the trailing 12 months.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
def rent_price__month__ta():
    pivoted = _pivot_theme("Bonds", RENT_PRICE_SERIES)
    return pivoted.select(
        F.col("area_name").alias("ta_name"),
        F.col("area_id").alias("ta_code"),
        F.col("date"),
        F.col("median_rent_nzd").cast("double"),
        F.col("average_rent_nzd").cast("double"),
        F.col("lower_quartile_rent_nzd").cast("double"),
        F.current_timestamp().alias("_updated_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## affordability__quarter__ta (Affordability theme)
# MAGIC
# MAGIC The longest real time series in HUD — quarterly going back to 2001.

# COMMAND ----------


AFFORDABILITY_SERIES = {
    "Deposit affordability index": "deposit_affordability_index",
    "Mortgage affordability index": "mortgage_affordability_index",
    "Rent affordability index": "rent_affordability_index",
    "Timeseries Median-Median ratio": "median_to_median_ratio",
}


@dlt.table(
    name="affordability__quarter__ta",
    comment=(
        "TA-level quarterly affordability indices from HUD: deposit, "
        "mortgage, and rent affordability indices (ratios of housing cost "
        "to household income) plus the median-house-price-to-median-income "
        "ratio. Quarterly time series back to 2001."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        ta_name STRING NOT NULL COMMENT 'TA name (or "New Zealand"). Joins to gold.suburb.territorial_authority.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        quarter DATE NOT NULL COMMENT 'First day of the quarter (e.g. 2024-01-01 = Q1 2024).',
        quarter_label STRING NOT NULL COMMENT 'Human-readable quarter label, e.g. "2024-Q1".',
        deposit_affordability_index DOUBLE COMMENT 'Ratio of deposit required vs household income capacity. Higher = less affordable.',
        mortgage_affordability_index DOUBLE COMMENT 'Ratio of mortgage servicing cost vs household income. Higher = less affordable.',
        rent_affordability_index DOUBLE COMMENT 'Ratio of median rent vs household income. Higher = less affordable.',
        median_to_median_ratio DOUBLE COMMENT 'Median house price divided by median household income.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
def affordability__quarter__ta():
    pivoted = _pivot_theme("Affordability", AFFORDABILITY_SERIES)

    # HUD publishes Affordability at end-of-quarter dates (2024-03-31, etc.).
    # `trunc(date, 'quarter')` returns the first day of the containing quarter
    # as a DATE — no float-vs-int arithmetic, no NULLs, matches the
    # quarter-start convention used elsewhere (e.g. prices).
    return pivoted.selectExpr(
        "area_name AS ta_name",
        "area_id AS ta_code",
        "trunc(date, 'quarter') AS quarter",
        # "2024-Q1" form. quarter() returns 1..4 for any date in the quarter.
        "concat(year(date), '-Q', quarter(date)) AS quarter_label",
        "cast(deposit_affordability_index AS DOUBLE) AS deposit_affordability_index",
        "cast(mortgage_affordability_index AS DOUBLE) AS mortgage_affordability_index",
        "cast(rent_affordability_index AS DOUBLE) AS rent_affordability_index",
        "cast(median_to_median_ratio AS DOUBLE) AS median_to_median_ratio",
        "current_timestamp() AS _updated_at",
    )
