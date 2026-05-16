# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 gold layer
# MAGIC
# MAGIC Genie-ready marts:
# MAGIC
# MAGIC - `income__year__suburb` — 2023 median household income by SA2 (suburb mapping via `place_lookup` later).
# MAGIC - `suburb` — SA2 demographic snapshot for the housing assistant (partial; NZDep still separate).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"


def _metric_value(dataset: str, field_name: str):
    return F.max(
        F.when(
            (F.col("dataset") == dataset) & (F.col("field_name") == field_name),
            F.col("value"),
        )
    )


@dlt.table(
    name="income__year__suburb",
    comment="Median household income from 2023 Census by SA2. Suburb concordance is a follow-up via place_lookup.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        census_year INT COMMENT 'Census reference year (2023).',
        sa2_code STRING COMMENT 'Stats NZ SA2 2023 code. Join key until suburb concordance exists.',
        sa2_name STRING COMMENT 'Official SA2 name.',
        median_household_income DOUBLE COMMENT 'Median total household income ($, before tax, year ended 31 March 2023).',
        households_total INT COMMENT 'Households in occupied private dwellings.',
        households_income_stated INT COMMENT 'Households with stated income (denominator for band shares).'
    """,
)
def income__year__suburb():
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric").filter("dataset = 'households_sa2'")

    return (
        metrics.groupBy("sa2_code", "sa2_name")
        .agg(
            _metric_value("households_sa2", "VAR_4_225").alias("median_household_income"),
            _metric_value("households_sa2", "VAR_4_3").cast("int").alias("households_total"),
            _metric_value("households_sa2", "VAR_4_224")
            .cast("int")
            .alias("households_income_stated"),
        )
        .select(
            F.lit(2023).alias("census_year"),
            F.col("sa2_code"),
            F.col("sa2_name"),
            F.col("median_household_income"),
            F.col("households_total"),
            F.col("households_income_stated"),
        )
    )


@dlt.table(
    name="suburb",
    comment="SA2-level demographic snapshot from 2023 Census (canonical suburb mapping TBD).",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        sa2_code STRING COMMENT 'Stats NZ SA2 2023 code.',
        sa2_name STRING COMMENT 'Official SA2 name.',
        h3_cell BIGINT COMMENT 'H3 cell at resolution 8 for the SA2 centroid.',
        land_area_sq_km DOUBLE COMMENT 'Land area in square kilometres.',
        census_year INT COMMENT 'Census reference year.',
        household_count INT COMMENT 'Households in occupied private dwellings (2023).',
        median_household_income DOUBLE COMMENT 'Median total household income ($).',
        tenure_owned_or_partly_owned INT COMMENT 'Households in dwellings owned or partly owned (2023).',
        tenure_not_owned INT COMMENT 'Households in dwellings not owned and not in a family trust (2023).',
        tenure_total_stated INT COMMENT 'Households with stated tenure (2023).'
    """,
)
def suburb():
    area = spark.read.table(f"{SILVER}.census_sa2_area")
    metrics = spark.read.table(f"{SILVER}.census_sa2_metric").filter("dataset = 'households_sa2'")

    stats = metrics.groupBy("sa2_code").agg(
        _metric_value("households_sa2", "VAR_4_3").cast("int").alias("household_count"),
        _metric_value("households_sa2", "VAR_4_225").alias("median_household_income"),
        _metric_value("households_sa2", "VAR_4_184")
        .cast("int")
        .alias("tenure_owned_or_partly_owned"),
        _metric_value("households_sa2", "VAR_4_185").cast("int").alias("tenure_not_owned"),
        _metric_value("households_sa2", "VAR_4_189").cast("int").alias("tenure_total_stated"),
    )

    return area.join(stats, on="sa2_code", how="left").select(
        F.col("sa2_code"),
        F.col("sa2_name"),
        F.col("h3_cell_res8").alias("h3_cell"),
        F.col("land_area_sq_km"),
        F.lit(2023).alias("census_year"),
        F.col("household_count"),
        F.col("median_household_income"),
        F.col("tenure_owned_or_partly_owned"),
        F.col("tenure_not_owned"),
        F.col("tenure_total_stated"),
    )
