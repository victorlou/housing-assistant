# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — silver layer
# MAGIC
# MAGIC Conformed victimisation counts at a stable grain:
# MAGIC `(report_month, ANZSOC subdivision)`.
# MAGIC
# MAGIC Bronze mixes event-level rows (`victimisations = 1`) with pre-aggregated
# MAGIC groups; silver rolls up with `SUM(victimisations)`.
# MAGIC
# MAGIC **Note:** Current landings have no geography. Area-unit crime marts need a
# MAGIC separate *Victimisation Time and Place* export later.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"

# COMMAND ----------


@dlt.table(
    name="crime_victimisation_monthly",
    comment=(
        "National victimisation counts by report month and ANZSOC subdivision. "
        "One row per (report_month, anzsoc_subdivision_cd)."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        report_month DATE COMMENT 'First day of the reporting month.',
        anzsoc_division STRING COMMENT 'ANZSOC division label, e.g. Theft, Assault.',
        anzsoc_division_cd INT COMMENT 'ANZSOC division code.',
        anzsoc_group_cd INT COMMENT 'ANZSOC group code.',
        anzsoc_subdivision_cd INT COMMENT 'ANZSOC subdivision code.',
        victimisation_count BIGINT COMMENT 'Sum of victimisations for this month and offence subdivision.',
        _ingested_at TIMESTAMP COMMENT 'Latest bronze ingest timestamp contributing to this row.'
    """,
)
@dlt.expect("has_subdivision", "anzsoc_subdivision_cd IS NOT NULL")
@dlt.expect("positive_count", "victimisation_count > 0")
def crime_victimisation_monthly():
    bronze = spark.read.table(f"{BRONZE}.police_recorded_crime_anzsoc_victimisations")
    return bronze.groupBy(
        "report_month",
        "anzsoc_division",
        "anzsoc_division_cd",
        "anzsoc_group_cd",
        "anzsoc_subdivision_cd",
    ).agg(
        F.sum("victimisations").alias("victimisation_count"),
        F.max("_ingested_at").alias("_ingested_at"),
    )
