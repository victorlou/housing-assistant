# Databricks notebook source
# MAGIC %md
# MAGIC # LINZ NZ Addresses — gold layer
# MAGIC
# MAGIC Genie-ready NZ street addresses. Current lifecycle only (excludes
# MAGIC proposed addresses). Reads from the silver pipeline.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"

# COMMAND ----------


@dlt.table(
    name="nz_address",
    comment=(
        "Current NZ street addresses with H3 cell at resolution 8. "
        "One row per address_id. Genie-ready."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        address_id STRING COMMENT 'LINZ address identifier.',
        full_address STRING COMMENT 'Formatted address string.',
        suburb_locality STRING COMMENT 'Suburb or locality name.',
        town_city STRING COMMENT 'Town or city name.',
        territorial_authority STRING COMMENT 'Territorial authority (council) name.',
        address_class STRING COMMENT 'LINZ address class.',
        longitude DOUBLE COMMENT 'Longitude in WGS84 decimal degrees.',
        latitude DOUBLE COMMENT 'Latitude in WGS84 decimal degrees.',
        h3_cell BIGINT COMMENT 'H3 spatial index cell at resolution 8. Join key for spatial queries.'
    """,
)
def nz_address():
    return (
        spark.read.table(f"{SILVER}.nz_address")
        .filter(F.col("address_lifecycle") == "Current")
        .select(
            F.col("address_id"),
            F.col("full_address"),
            F.col("suburb_locality"),
            F.col("town_city"),
            F.col("territorial_authority"),
            F.col("address_class"),
            F.col("longitude"),
            F.col("latitude"),
            F.col("h3_cell_res8").alias("h3_cell"),
        )
    )
