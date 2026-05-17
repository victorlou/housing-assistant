# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — silver layer
# MAGIC
# MAGIC Conformed victimisation counts at grain:
# MAGIC `(report_month, territorial_authority, area_unit, ANZSOC subdivision)`.
# MAGIC
# MAGIC Bronze may mix event-level rows (`victimisations = 1`) with pre-aggregated groups;
# MAGIC silver rolls up with `SUM(victimisations)`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"

# COMMAND ----------


@dlt.table(
    name="crime_victimisation_monthly",
    comment=(
        "Victimisation counts by report month, area unit, and ANZSOC offence hierarchy. "
        "One row per (report_month, territorial_authority, area_unit, anzsoc_subdivision)."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        report_month DATE COMMENT 'First day of the reporting month.',
        territorial_authority STRING COMMENT 'Territorial authority label from Police export.',
        area_unit STRING COMMENT 'Stats NZ area unit label from Police export.',
        anzsoc_division STRING COMMENT 'ANZSOC division label, e.g. Theft, Assault.',
        anzsoc_group STRING COMMENT 'ANZSOC group label.',
        anzsoc_subdivision STRING COMMENT 'ANZSOC subdivision label.',
        victimisation_count BIGINT COMMENT 'Sum of victimisations for this grain.',
        _ingested_at TIMESTAMP COMMENT 'Latest bronze ingest timestamp contributing to this row.'
    """,
)
@dlt.expect("has_subdivision", "anzsoc_subdivision IS NOT NULL")
@dlt.expect("positive_count", "victimisation_count > 0")
def crime_victimisation_monthly():
    bronze = spark.read.table(f"{BRONZE}.police_recorded_crime_anzsoc_victimisations")
    return bronze.groupBy(
        "report_month",
        "territorial_authority",
        "area_unit",
        "anzsoc_division",
        "anzsoc_group",
        "anzsoc_subdivision",
    ).agg(
        F.sum("victimisations").alias("victimisation_count"),
        F.max("_ingested_at").alias("_ingested_at"),
    )
