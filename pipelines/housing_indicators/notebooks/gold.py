# Databricks notebook source
# MAGIC %md
# MAGIC # housing_indicators gold layer
# MAGIC
# MAGIC Two time-series tables at NZ territorial-authority grain, named on the
# MAGIC `<spatial_dim>__<time_grain>` convention so any consumer (Genie, the
# MAGIC agent, ad-hoc SQL) gets *every* metric we know about that TA at that
# MAGIC cadence in a single SELECT:
# MAGIC
# MAGIC - `housing.gold.ta__month` - monthly TA metrics (HUD Sales snapshots,
# MAGIC   HUD Bonds snapshots, MSD Housing Register time series).
# MAGIC - `housing.gold.ta__quarter` - quarterly TA metrics (HUD Affordability
# MAGIC   indices, the deep ~25-year time series back to 2001).
# MAGIC
# MAGIC The long-format raw stays as `housing.silver.housing_indicator` for
# MAGIC anyone who wants the unpivoted shape; gold collapses themes/series
# MAGIC into named columns so consumers don't have to know HUD's internal
# MAGIC theme/series taxonomy.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"


# -- Pivot helper ----------------------------------------------------


def _first_where(series_name: str, alias: str, cast_type: str):
    """
    Conditional-aggregation pivot: per group, take the first non-null
    `value` whose `series` column matches `series_name`. Equivalent to
    `GroupedData.pivot(...).agg(F.first(...))` but doesn't trip DLT's
    pivot-not-supported guard.
    """
    return (
        F.first(
            F.when(F.col("series") == series_name, F.col("value")),
            ignorenulls=True,
        )
        .cast(cast_type)
        .alias(alias)
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## ta__month
# MAGIC
# MAGIC One row per (ta_name, date). Sparse by design - Sales/Bonds metrics
# MAGIC are snapshot-cadence (HUD publishes a rolling-annual value on
# MAGIC irregular dates), while MSD is a true monthly time series back to 2017.
# MAGIC For "current state" questions: `WHERE ta_name = X ORDER BY date DESC
# MAGIC LIMIT 1`. For time-series questions: just ORDER BY date.

# COMMAND ----------


# (series_name in HUD, output column, cast type)
# Deliberate column alignment; ruff would squish the contents below.
# fmt: off
TA_MONTH_METRICS = [
    # Sales theme - HUD ships these as snapshot rows (rolling 12-month values).
    ("Current House Price Index",                 "current_hpi",                      "double"),
    ("Current Annual Median Sales Price",         "current_annual_median_sales_nzd",  "double"),
    ("Current Annual Lower Quartile Sales Price", "current_annual_lower_q_sales_nzd", "double"),
    ("Current number of Annual Sales volume",     "annual_sales_volume",              "int"),
    # Bonds theme - rolling-annual rent stats, snapshot cadence.
    ("Median Rent Price",                         "median_rent_nzd",                  "double"),
    ("Average Rent Price",                        "average_rent_nzd",                 "double"),
    ("Lower Quartile Rent Price",                 "lower_quartile_rent_nzd",          "double"),
    # MSD theme - monthly time series back to 2017.
    ("Housing Register",                          "housing_register",                 "int"),
    ("Housing Register per 10k population",       "housing_register_per_10k_pop",     "double"),
]
# fmt: on


@dlt.table(
    name="ta__month",
    comment=(
        "Time-series fact at NZ territorial-authority + month grain. One row "
        "per (ta_name, date). Columns are HUD-derived metrics that update at "
        "monthly cadence: house-price snapshots (current rolling-annual HPI + "
        "median + lower-quartile sale price + sales volume), rent snapshots "
        "(median / average / lower-quartile weekly rent), and MSD housing-"
        "register counts. Sparse by design - Sales/Bonds rows only appear on "
        "snapshot dates HUD published; MSD rows appear monthly. For 'current "
        "state' queries: ORDER BY date DESC LIMIT 1 per ta_name. Joins to "
        "housing.gold.suburb on ta_name = territorial_authority. The "
        "long-format source-of-truth (with every HUD series including ones "
        "not pivoted here) is housing.silver.housing_indicator."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["ta_name"],
    schema="""
        ta_name STRING NOT NULL COMMENT 'TA name (Stats NZ canonical NZGB form, e.g. "Auckland", "Wellington City", "Queenstown-Lakes District") or the synthetic "New Zealand" rollup. Joins to gold.suburb.territorial_authority.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        date DATE NOT NULL COMMENT 'End-of-period date for this observation. MSD rows: end of the calendar month. Sales/Bonds rows: snapshot date HUD published.',
        current_hpi DOUBLE COMMENT 'House Price Index at this snapshot. NULL on rows without a Sales snapshot (i.e. most MSD-only months).',
        current_annual_median_sales_nzd DOUBLE COMMENT 'Median residential sale price (NZD) over the trailing 12 months at this snapshot date.',
        current_annual_lower_q_sales_nzd DOUBLE COMMENT 'Lower-quartile residential sale price (NZD) over the trailing 12 months.',
        annual_sales_volume INT COMMENT 'Count of residential sales over the trailing 12 months.',
        median_rent_nzd DOUBLE COMMENT 'Weekly median rent (NZD) over the trailing 12 months. From HUD Bonds theme, MBIE rental-bonds upstream.',
        average_rent_nzd DOUBLE COMMENT 'Weekly average rent (NZD) over the trailing 12 months.',
        lower_quartile_rent_nzd DOUBLE COMMENT 'Weekly lower-quartile rent (NZD) over the trailing 12 months.',
        housing_register INT COMMENT 'Number of households on the MSD social-housing register at month-end. Monthly cadence back to 2017.',
        housing_register_per_10k_pop DOUBLE COMMENT 'MSD housing-register count per 10,000 TA population. Useful for cross-TA comparison normalising for size.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_ta_name", "ta_name IS NOT NULL")
@dlt.expect_or_drop("has_date", "date IS NOT NULL")
def ta__month():
    src = (
        spark.read.table(f"{SILVER}.housing_indicator")
        # Include national rollup (area_name='New Zealand', area_type='NZ')
        # alongside the 67 TAs.
        .filter(F.col("area_type").isin("TA", "NZ"))
        .filter(F.col("ethnicity").isNull())
        .filter(F.col("series").isin([m[0] for m in TA_MONTH_METRICS]))
    )

    grouped = src.groupBy("area_name", "area_id", "date").agg(
        *[_first_where(s, a, t) for (s, a, t) in TA_MONTH_METRICS]
    )

    return grouped.select(
        F.col("area_name").alias("ta_name"),
        F.col("area_id").alias("ta_code"),
        F.col("date"),
        *[F.col(a) for (_, a, _) in TA_MONTH_METRICS],
        F.current_timestamp().alias("_updated_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## ta__quarter
# MAGIC
# MAGIC Quarterly TA-level affordability indices from HUD. 25-year time series
# MAGIC back to 2001 - the deepest time series in the lakehouse.

# COMMAND ----------


# Deliberate column alignment; ruff would squish the contents below.
# fmt: off
TA_QUARTER_METRICS = [
    ("Deposit affordability index",    "deposit_affordability_index",  "double"),
    ("Mortgage affordability index",   "mortgage_affordability_index", "double"),
    ("Rent affordability index",       "rent_affordability_index",     "double"),
    ("Timeseries Median-Median ratio", "median_to_median_ratio",       "double"),
]
# fmt: on


@dlt.table(
    name="ta__quarter",
    comment=(
        "Time-series fact at NZ territorial-authority + quarter grain. One "
        "row per (ta_name, quarter). Carries HUD's four affordability "
        "indices - quarterly back to 2001-Q1 (the deepest time series in "
        "the lakehouse). Joins to housing.gold.suburb on ta_name = "
        "territorial_authority."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["ta_name"],
    schema="""
        ta_name STRING NOT NULL COMMENT 'TA name (Stats NZ canonical) or "New Zealand". Joins to gold.suburb.territorial_authority.',
        ta_code STRING COMMENT 'HUDs stable numeric area_id.',
        quarter DATE NOT NULL COMMENT 'First day of the quarter (2024-01-01 = Q1 2024).',
        quarter_label STRING NOT NULL COMMENT 'Human-readable quarter label, e.g. "2024-Q1".',
        deposit_affordability_index DOUBLE COMMENT 'Ratio of deposit required vs household income capacity. Higher = less affordable.',
        mortgage_affordability_index DOUBLE COMMENT 'Ratio of mortgage servicing cost vs household income. Higher = less affordable.',
        rent_affordability_index DOUBLE COMMENT 'Ratio of median rent vs household income. Higher = less affordable.',
        median_to_median_ratio DOUBLE COMMENT 'Median house price / median household income. Auckland peaked at ~10x in 2021.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_ta_name", "ta_name IS NOT NULL")
@dlt.expect_or_drop("has_quarter", "quarter IS NOT NULL")
def ta__quarter():
    src = (
        spark.read.table(f"{SILVER}.housing_indicator")
        .filter(F.col("area_type").isin("TA", "NZ"))
        .filter(F.col("theme") == "Affordability")
        .filter(F.col("ethnicity").isNull())
        .filter(F.col("series").isin([m[0] for m in TA_QUARTER_METRICS]))
    )

    pivoted = src.groupBy("area_name", "area_id", "date").agg(
        *[_first_where(s, a, t) for (s, a, t) in TA_QUARTER_METRICS]
    )

    return pivoted.selectExpr(
        "area_name AS ta_name",
        "area_id AS ta_code",
        "trunc(date, 'quarter') AS quarter",
        "concat(year(date), '-Q', quarter(date)) AS quarter_label",
        *[f"cast({a} AS {t}) AS {a}" for (_, a, t) in TA_QUARTER_METRICS],
        "current_timestamp() AS _updated_at",
    )
