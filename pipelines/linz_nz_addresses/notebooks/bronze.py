# Databricks notebook source
# MAGIC %md
# MAGIC # LINZ NZ Addresses — bronze layer
# MAGIC
# MAGIC Auto Loader over JSONL landings at
# MAGIC `/Volumes/housing/bronze/linz_nz_addresses_files/nz_addresses/<run_date>/linz_nz_addresses.jsonl`.
# MAGIC
# MAGIC - `linz_nz_addresses_raw` — GeoJSON Feature rows as landed.
# MAGIC - `linz_nz_addresses` — flattened address attributes with provenance.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/linz_nz_addresses_files/nz_addresses"

# COMMAND ----------


@dlt.table(
    name="linz_nz_addresses_raw",
    comment="Raw LINZ NZ address GeoJSON features landed as JSONL (WFS via scheduled fetch job).",
    table_properties={"quality": "bronze", "project": "housing-assistant"},
)
def linz_nz_addresses_raw():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(VOLUME_ROOT)
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"),
                r"/nz_addresses/([0-9]{4}-[0-9]{2}-[0-9]{2})/",
                1,
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


# COMMAND ----------


@dlt.table(
    name="linz_nz_addresses",
    comment="LINZ NZ addresses as typed bronze Delta (flattened GeoJSON Feature properties).",
    table_properties={
        "quality": "bronze",
        "project": "housing-assistant",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
    },
)
@dlt.expect("has_address_id", "address_id IS NOT NULL")
def linz_nz_addresses():
    rf = dlt.read_stream("linz_nz_addresses_raw")
    return rf.select(
        F.col("id").alias("feature_id"),
        F.col("geometry_name").alias("source_geometry_name"),
        F.col("geometry.type").alias("geometry_type"),
        F.element_at(F.col("geometry.coordinates"), 1).cast("double").alias("longitude"),
        F.element_at(F.col("geometry.coordinates"), 2).cast("double").alias("latitude"),
        F.col("properties.address_id").alias("address_id"),
        F.col("properties.source_dataset").alias("source_dataset"),
        F.col("properties.change_id").alias("change_id"),
        F.col("properties.full_address_number").alias("full_address_number"),
        F.col("properties.full_road_name").alias("full_road_name"),
        F.col("properties.full_address").alias("full_address"),
        F.col("properties.territorial_authority").alias("territorial_authority"),
        F.col("properties.unit_type").alias("unit_type"),
        F.col("properties.unit_value").alias("unit_value"),
        F.col("properties.level_type").alias("level_type"),
        F.col("properties.level_value").alias("level_value"),
        F.col("properties.address_number_prefix").alias("address_number_prefix"),
        F.col("properties.address_number").alias("address_number"),
        F.col("properties.address_number_suffix").alias("address_number_suffix"),
        F.col("properties.address_number_high").alias("address_number_high"),
        F.col("properties.road_name_prefix").alias("road_name_prefix"),
        F.col("properties.road_name").alias("road_name"),
        F.col("properties.road_type_name").alias("road_type_name"),
        F.col("properties.road_suffix").alias("road_suffix"),
        F.col("properties.water_name").alias("water_name"),
        F.col("properties.water_body_name").alias("water_body_name"),
        F.col("properties.suburb_locality").alias("suburb_locality"),
        F.col("properties.town_city").alias("town_city"),
        F.col("properties.address_class").alias("address_class"),
        F.col("properties.address_lifecycle").alias("address_lifecycle"),
        F.col("properties.gd2000_xcoord").alias("gd2000_xcoord"),
        F.col("properties.gd2000_ycoord").alias("gd2000_ycoord"),
        F.col("properties.road_name_ascii").alias("road_name_ascii"),
        F.col("properties.water_name_ascii").alias("water_name_ascii"),
        F.col("properties.water_body_name_ascii").alias("water_body_name_ascii"),
        F.col("properties.suburb_locality_ascii").alias("suburb_locality_ascii"),
        F.col("properties.town_city_ascii").alias("town_city_ascii"),
        F.col("properties.full_road_name_ascii").alias("full_road_name_ascii"),
        F.col("properties.full_address_ascii").alias("full_address_ascii"),
        F.col("geometry").alias("geojson_geometry_struct"),
        F.col("_run_date"),
        F.col("_ingested_at"),
        F.col("_source_file"),
    )
