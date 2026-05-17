# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — bronze layer
# MAGIC
# MAGIC Auto Loader over manually uploaded Tableau CSV exports at
# MAGIC `/Volumes/housing/bronze/police_recorded_crime_files/anzsoc_victimisations/<date>/anzsoc_victimisations.csv`.
# MAGIC
# MAGIC - `police_recorded_crime_anzsoc_victimisations_raw` — CSV headers preserved (column mapping).
# MAGIC - `police_recorded_crime_anzsoc_victimisations` — typed columns + `report_month`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/police_recorded_crime_files/anzsoc_victimisations"

# COMMAND ----------


@dlt.table(
    name="police_recorded_crime_anzsoc_victimisations_raw",
    comment="Raw NZ Police ANZSOC victimisation CSV rows (manual Tableau export).",
    table_properties={
        "quality": "bronze",
        "project": "housing-assistant",
        "delta.columnMapping.mode": "name",
    },
)
def police_recorded_crime_anzsoc_victimisations_raw():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .load(VOLUME_ROOT)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )


# COMMAND ----------


@dlt.table(
    name="police_recorded_crime_anzsoc_victimisations",
    comment="Typed NZ Police ANZSOC victimisations by offence subdivision and report month.",
    table_properties={
        "quality": "bronze",
        "project": "housing-assistant",
    },
)
@dlt.expect("has_report_month", "report_month IS NOT NULL")
@dlt.expect("positive_victimisations", "victimisations >= 0")
def police_recorded_crime_anzsoc_victimisations():
    raw = dlt.read_stream("police_recorded_crime_anzsoc_victimisations_raw")
    return raw.select(
        F.trim(F.col("ANZSOC Division")).alias("anzsoc_division"),
        F.trim(F.col("Year Month")).alias("year_month"),
        F.col("ANZSOC_DIVISION_CD").cast("int").alias("anzsoc_division_cd"),
        F.col("ANZSOC_GROUP_CD").cast("int").alias("anzsoc_group_cd"),
        F.col("ANZSOC_SUBDIVISION_CD").cast("int").alias("anzsoc_subdivision_cd"),
        F.col("Victimisations").cast("int").alias("victimisations"),
        F.to_date(F.concat(F.lit("01 "), F.trim(F.col("Year Month"))), "dd MMMM yyyy").alias(
            "report_month"
        ),
        F.col("_source_file"),
        F.col("_ingested_at"),
    )
