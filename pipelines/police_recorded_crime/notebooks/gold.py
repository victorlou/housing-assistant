# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — gold layer
# MAGIC
# MAGIC Genie-ready semantic marts from silver.
# MAGIC
# MAGIC - `crime__month__anzsoc_subdivision` — national counts (current data).
# MAGIC
# MAGIC Target `crime__month__area_unit` is blocked until a geographic Police export
# MAGIC is landed and conformed in silver.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"

# COMMAND ----------


@dlt.table(
    name="crime__month__anzsoc_subdivision",
    comment=(
        "Recorded crime victimisations by month and ANZSOC subdivision (national). "
        "Genie-ready. For area-unit breakdowns, use a future geographic landing."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        report_month DATE COMMENT 'First day of the reporting month.',
        anzsoc_division STRING COMMENT 'ANZSOC division label.',
        anzsoc_division_cd INT COMMENT 'ANZSOC division code.',
        anzsoc_group_cd INT COMMENT 'ANZSOC group code.',
        anzsoc_subdivision_cd INT COMMENT 'ANZSOC subdivision code.',
        victimisation_count BIGINT COMMENT 'Victimisations in this month for this offence subdivision.'
    """,
)
def crime__month__anzsoc_subdivision():
    return spark.read.table(f"{SILVER}.crime_victimisation_monthly").select(
        F.col("report_month"),
        F.col("anzsoc_division"),
        F.col("anzsoc_division_cd"),
        F.col("anzsoc_group_cd"),
        F.col("anzsoc_subdivision_cd"),
        F.col("victimisation_count"),
    )
