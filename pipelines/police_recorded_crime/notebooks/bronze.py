# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — bronze layer
# MAGIC
# MAGIC Auto Loader over manually uploaded Tableau CSV exports at
# MAGIC `/Volumes/housing/bronze/crime_files/police_recorded_crime/<date>/anzsoc_victimisations.csv`.
# MAGIC
# MAGIC - `police_recorded_crime_anzsoc_victimisations_raw` — CSV headers preserved (column mapping).
# MAGIC - `police_recorded_crime_anzsoc_victimisations` — typed columns + `report_month`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/crime_files/police_recorded_crime"


def _strip_column_names(df):
    for name in df.columns:
        stripped = name.strip()
        if name != stripped:
            df = df.withColumnRenamed(name, stripped)
    return df


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
    comment=(
        "Typed NZ Police ANZSOC victimisations by area unit, offence subdivision, and report month."
    ),
    table_properties={
        "quality": "bronze",
        "project": "housing-assistant",
    },
)
@dlt.expect("has_report_month", "report_month IS NOT NULL")
@dlt.expect("has_area_unit", "area_unit IS NOT NULL")
@dlt.expect("positive_victimisations", "victimisations >= 0")
def police_recorded_crime_anzsoc_victimisations():
    raw = _strip_column_names(
        dlt.read_stream("police_recorded_crime_anzsoc_victimisations_raw")
    )
    return raw.select(
        F.trim(F.col("Year Month")).alias("year_month"),
        F.trim(F.regexp_replace(F.col("Territorial Authority"), r"\.$", "")).alias(
            "territorial_authority"
        ),
        F.trim(F.regexp_replace(F.col("Area Unit"), r"\.$", "")).alias("area_unit"),
        F.trim(F.col("Month Year")).alias("month_year"),
        F.col("Victimisations").cast("int").alias("victimisations"),
        F.trim(F.col("ANZSOC Division")).alias("anzsoc_division"),
        F.trim(F.col("ANZSOC Group")).alias("anzsoc_group"),
        F.trim(F.col("ANZSOC Subdivision")).alias("anzsoc_subdivision"),
        F.to_date(
            F.concat(F.lit("01 "), F.trim(F.col("Year Month"))), "dd MMMM yyyy"
        ).alias("report_month"),
        F.col("_source_file"),
        F.col("_ingested_at"),
    ).filter(F.col("area_unit") != "999999")
