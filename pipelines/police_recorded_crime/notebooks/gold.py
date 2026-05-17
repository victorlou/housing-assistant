# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — gold layer
# MAGIC
# MAGIC One wide-at-grain table following `docs/conventions.md`
# MAGIC (`<spatial_dim>__<time_grain>`):
# MAGIC
# MAGIC - `housing.gold.area_unit__month` — total victimisations per Stats NZ
# MAGIC   area unit per month. One row per (report_month, area_unit).
# MAGIC
# MAGIC The earlier `crime__month__area_unit` shape kept a long-format breakdown
# MAGIC by ANZSOC subdivision (~250 categories) and was named after the metric
# MAGIC family rather than the grain. The breakdown escape hatch stays as
# MAGIC `housing.silver.crime_victimisation_monthly` for any question that
# MAGIC needs offence-level detail; gold is wide and consumer-facing.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"

# COMMAND ----------


@dlt.table(
    name="area_unit__month",
    comment=(
        "Time-series fact at Stats NZ area unit + month grain. One row per "
        "(report_month, area_unit). `total_victimisations` is the sum of "
        "recorded victimisations across all ANZSOC subdivisions for that "
        "area unit in that month. JOINS: territorial_authority is a "
        "derived attribute (area units nest within TAs); for SA2-level "
        "rollups, use a place-name lookup to map area_unit → SA2 (TODO). "
        "For ANZSOC division / group / subdivision breakdowns, hit "
        "housing.silver.crime_victimisation_monthly directly — it stays "
        "in silver as the long-format escape hatch per the conventions doc."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        report_month DATE NOT NULL COMMENT 'First day of the reporting month.',
        area_unit STRING NOT NULL COMMENT 'Stats NZ area unit label as published by Police.',
        territorial_authority STRING COMMENT 'Containing TA label. Derived from area_unit (area units nest within TAs).',
        total_victimisations BIGINT COMMENT 'Sum of recorded victimisations across all ANZSOC subdivisions for this (area_unit, month).',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_report_month", "report_month IS NOT NULL")
@dlt.expect_or_drop("has_area_unit", "area_unit IS NOT NULL")
def area_unit__month():
    return (
        spark.read.table(f"{SILVER}.crime_victimisation_monthly")
        .groupBy("report_month", "area_unit", "territorial_authority")
        .agg(F.sum("victimisation_count").alias("total_victimisations"))
        .withColumn("_updated_at", F.current_timestamp())
        .select(
            "report_month",
            "area_unit",
            "territorial_authority",
            "total_victimisations",
            "_updated_at",
        )
    )
