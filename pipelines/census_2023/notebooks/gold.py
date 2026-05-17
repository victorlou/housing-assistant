# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 gold layer
# MAGIC
# MAGIC One wide time-series fact at SA2 + census-year grain following the
# MAGIC `<spatial_dim>__<time_grain>` convention (see `docs/conventions.md`):
# MAGIC
# MAGIC - `housing.gold.suburb__year` — every curated 2023 Census metric per SA2
# MAGIC   in a single row: income, tenure, rent, dwelling quality, demographics.
# MAGIC
# MAGIC The earlier shape split this across four per-metric-family tables
# MAGIC (`income__year__suburb`, `tenure__year__suburb`, `rent__year__suburb`,
# MAGIC `dwelling__year__suburb`) plus a long-format `census_metric__year__sa2`.
# MAGIC Those are retired in favour of the wide-at-grain convention; the
# MAGIC long-format escape hatch stays in `housing.silver.census_sa2_metric`
# MAGIC for power users who want unpivoted access.
# MAGIC
# MAGIC `housing.gold.suburb` (places pipeline) is the canonical SA2 *dim* and
# MAGIC carries the same 2023 census columns as a current-snapshot subset;
# MAGIC `suburb__year` is the time-series form (will carry future census years
# MAGIC alongside 2023 as Stats NZ publishes them).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F


from census_gold_lib import (
    census_year,
    load_gold_manifest,
)

SILVER = "housing.silver"
_MANIFEST = load_gold_manifest()
_CENSUS_YEAR = census_year(_MANIFEST)


# COMMAND ----------
# MAGIC %md
# MAGIC ## suburb__year
# MAGIC
# MAGIC One row per (suburb_id, census_year). All curated metrics live as
# MAGIC named columns; the wide-at-grain shape lets the agent and Genie
# MAGIC pull "everything we know about this SA2 in 2023" via a single SELECT.

# COMMAND ----------


@dlt.table(
    name="suburb__year",
    comment=(
        "Time-series fact at NZ suburb (SA2) + census year grain. One row per "
        "(suburb_id, census_year). Carries every curated census metric for "
        "that SA2: income, tenure, rent, dwelling quality, crowding, and "
        "demographics. Sourced from housing.silver.census_sa2_features, which "
        "materialises the metric manifest at pipelines/census_2023/"
        "census_2023_gold.yml. JOINS: suburb_id = housing.gold.suburb.suburb_id "
        "for static-dim attributes (TA, region, centroid, area, geometry). "
        "For long-format / open-ended Genie queries, hit "
        "housing.silver.census_sa2_metric instead."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT NOT NULL COMMENT 'Census reference year. Currently 2023; will carry 2028 etc. as Stats NZ publishes them.',
        suburb_id STRING NOT NULL COMMENT 'Stats NZ SA2 2023 code (6 digits). Joins to housing.gold.suburb.suburb_id.',
        suburb_name STRING COMMENT 'Official SA2 name as published by Stats NZ.',
        median_household_income DOUBLE COMMENT 'Median total household income ($, before tax) for the SA2.',
        households_total INT COMMENT 'Households in occupied private dwellings.',
        households_income_stated INT COMMENT 'Households whose income was stated (denominator for median income).',
        tenure_owned INT COMMENT 'Households in dwellings owned or partly owned by usual residents.',
        tenure_not_owned INT COMMENT 'Households in dwellings not owned and not in a family trust.',
        tenure_total_stated INT COMMENT 'Households with stated tenure (denominator for owner_occupier_pct).',
        owner_occupier_pct DOUBLE COMMENT 'tenure_owned / tenure_total_stated when stated > 0.',
        median_weekly_rent DOUBLE COMMENT 'Median weekly rent ($) for renting households.',
        renting_households_total INT COMMENT 'Renting households in occupied private dwellings.',
        renting_households_stated INT COMMENT 'Renting households whose rent was stated (denominator for median rent).',
        households_crowded INT COMMENT 'Households classified as crowded (Canadian National Occupancy Standard).',
        households_crowding_total_stated INT COMMENT 'Households with stated crowding status (denominator for percent_crowded).',
        percent_crowded DOUBLE COMMENT 'households_crowded / households_crowding_total_stated when stated > 0.',
        dwellings_always_damp INT COMMENT 'Dwellings reported as always damp in the 2023 Census housing-quality questions.',
        dwellings_sometimes_damp INT COMMENT 'Dwellings reported as sometimes damp.',
        dwellings_damp_total_stated INT COMMENT 'Dwellings with stated damp status.',
        dwellings_mould_a4_always INT COMMENT 'Dwellings reported as having A4-sized-or-larger mould always present.',
        dwellings_mould_total_stated INT COMMENT 'Dwellings with stated mould status.',
        dwellings_no_heating INT COMMENT 'Dwellings reporting no heating in any room.',
        dwellings_mean_rooms DOUBLE COMMENT 'Mean number of rooms per dwelling.',
        population_total INT COMMENT 'Usually-resident population count for the SA2.',
        median_age DOUBLE COMMENT 'Median age (years) of usually-resident population.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_suburb_id", "suburb_id IS NOT NULL")
@dlt.expect_or_drop("has_census_year", "census_year IS NOT NULL")
def suburb__year():
    features = spark.read.table(f"{SILVER}.census_sa2_features")
    return features.select(
        F.col("census_year").cast("int"),
        F.col("sa2_code").alias("suburb_id"),
        F.col("sa2_name").alias("suburb_name"),
        # Income
        F.col("median_household_income").cast("double"),
        F.col("households_total").cast("int"),
        F.col("households_income_stated").cast("int"),
        # Tenure
        F.col("tenure_owned").cast("int"),
        F.col("tenure_not_owned").cast("int"),
        F.col("tenure_total_stated").cast("int"),
        F.col("owner_occupier_pct").cast("double"),
        # Rent
        F.col("median_weekly_rent").cast("double"),
        F.col("renting_households_total").cast("int"),
        F.col("renting_households_stated").cast("int"),
        # Crowding
        F.col("households_crowded").cast("int"),
        F.col("households_crowding_total_stated").cast("int"),
        F.col("percent_crowded").cast("double"),
        # Dwelling quality
        F.col("dwellings_always_damp").cast("int"),
        F.col("dwellings_sometimes_damp").cast("int"),
        F.col("dwellings_damp_total_stated").cast("int"),
        F.col("dwellings_mould_a4_always").cast("int"),
        F.col("dwellings_mould_total_stated").cast("int"),
        F.col("dwellings_no_heating").cast("int"),
        F.col("dwellings_mean_rooms").cast("double"),
        # Demographics
        F.col("population_total").cast("int"),
        F.col("median_age").cast("double"),
        F.current_timestamp().alias("_updated_at"),
    )
