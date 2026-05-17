# Databricks notebook source
# MAGIC %md
# MAGIC # Flood hazard bronze layer
# MAGIC
# MAGIC Auto Loader stream over GeoJSON Feature JSONL landed at
# MAGIC `/Volumes/housing/bronze/flood_files/<file_stem>/<run_date>/features.jsonl`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/flood_files"


@dlt.table(
    name="flood_hazard_feature",
    comment="Raw flood hazard GeoJSON features from all regional ArcGIS layers.",
    table_properties={
        "quality": "bronze",
        "project": "housing-assistant",
    },
)
def flood_hazard_feature():
    raw = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"{VOLUME_ROOT}/*")
    )
    return (
        raw.withColumn(
            "_hazard_source",
            F.regexp_extract(F.col("_metadata.file_path"), r"/flood_files/([^/]+)/", 1),
        )
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"), r"/([0-9]{4}-[0-9]{2}-[0-9]{2})/", 1
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("geometry_json", F.to_json(F.col("geometry")))
        .withColumn("properties_json", F.to_json(F.col("properties")))
        .drop("properties", "type")
    )
