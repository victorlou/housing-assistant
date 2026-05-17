# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — gold layer
# MAGIC
# MAGIC Genie-ready semantic mart from silver.
# MAGIC
# MAGIC - `crime__month__area_unit` — counts by month, area unit, and ANZSOC subdivision.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"

# COMMAND ----------


@dlt.table(
    name="crime__month__area_unit",
    comment=(
        "Recorded crime victimisations by month, area unit, and ANZSOC subdivision. Genie-ready."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        report_month DATE COMMENT 'First day of the reporting month.',
        territorial_authority STRING COMMENT 'Territorial authority label.',
        area_unit STRING COMMENT 'Stats NZ area unit label.',
        anzsoc_division STRING COMMENT 'ANZSOC division label.',
        anzsoc_group STRING COMMENT 'ANZSOC group label.',
        anzsoc_subdivision STRING COMMENT 'ANZSOC subdivision label.',
        victimisation_count BIGINT COMMENT 'Victimisations in this month for this area unit and offence subdivision.'
    """,
)
def crime__month__area_unit():
    return spark.read.table(f"{SILVER}.crime_victimisation_monthly").select(
        F.col("report_month"),
        F.col("territorial_authority"),
        F.col("area_unit"),
        F.col("anzsoc_division"),
        F.col("anzsoc_group"),
        F.col("anzsoc_subdivision"),
        F.col("victimisation_count"),
    )
