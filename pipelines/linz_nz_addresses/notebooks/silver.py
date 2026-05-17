# Databricks notebook source
# MAGIC %md
# MAGIC # LINZ NZ Addresses — silver layer
# MAGIC
# MAGIC Conformed NZ street addresses with typed coordinates and H3 cell at
# MAGIC resolution 8. One row per `address_id`.
# MAGIC
# MAGIC Reads from the bronze pipeline via `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"

# COMMAND ----------


@dlt.table(
    name="nz_address",
    comment=(
        "NZ street addresses from LINZ with WGS84 coordinates and H3 cell at "
        "resolution 8. One row per address_id."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        address_id STRING COMMENT 'LINZ address identifier. Unique within this dataset.',
        full_address STRING COMMENT 'Formatted address string, e.g. "19 Graeme Avenue, Māngere East, Auckland".',
        full_address_ascii STRING COMMENT 'ASCII-normalised full address for search and matching.',
        suburb_locality STRING COMMENT 'Suburb or locality name.',
        town_city STRING COMMENT 'Town or city name.',
        territorial_authority STRING COMMENT 'Territorial authority (council) name.',
        address_class STRING COMMENT 'LINZ address class (e.g. Thoroughfare, Water).',
        address_lifecycle STRING COMMENT 'Lifecycle state from LINZ, e.g. Current or Proposed.',
        longitude DOUBLE COMMENT 'Longitude in WGS84 decimal degrees.',
        latitude DOUBLE COMMENT 'Latitude in WGS84 decimal degrees.',
        h3_cell_res8 BIGINT COMMENT 'H3 spatial index cell at resolution 8 (~0.7 km² hexagons).',
        gd2000_xcoord DOUBLE COMMENT 'NZGD2000 easting from LINZ.',
        gd2000_ycoord DOUBLE COMMENT 'NZGD2000 northing from LINZ.',
        _run_date STRING COMMENT 'Landing date folder (YYYY-MM-DD) from the ingest job.',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to bronze.'
    """,
)
@dlt.expect_or_drop("has_coordinates", "longitude IS NOT NULL AND latitude IS NOT NULL")
@dlt.expect("plausible_nz_latitude", "latitude BETWEEN -47.5 AND -34.0")
@dlt.expect("plausible_nz_longitude", "longitude BETWEEN 166.0 AND 179.0")
@dlt.expect("has_address_id", "address_id IS NOT NULL")
def nz_address():
    bronze = spark.read.table(f"{BRONZE}.linz_nz_addresses")
    return bronze.select(
        F.col("address_id").cast("string").alias("address_id"),
        F.col("full_address").cast("string").alias("full_address"),
        F.col("full_address_ascii").cast("string").alias("full_address_ascii"),
        F.col("suburb_locality").cast("string").alias("suburb_locality"),
        F.col("town_city").cast("string").alias("town_city"),
        F.col("territorial_authority").cast("string").alias("territorial_authority"),
        F.col("address_class").cast("string").alias("address_class"),
        F.col("address_lifecycle").cast("string").alias("address_lifecycle"),
        F.col("longitude").cast("double").alias("longitude"),
        F.col("latitude").cast("double").alias("latitude"),
        F.expr("h3_longlatash3(longitude, latitude, 8)").alias("h3_cell_res8"),
        F.col("gd2000_xcoord").cast("double").alias("gd2000_xcoord"),
        F.col("gd2000_ycoord").cast("double").alias("gd2000_ycoord"),
        F.col("_run_date"),
        F.col("_ingested_at"),
    )
