# Databricks notebook source
# MAGIC %md
# MAGIC # places silver layer
# MAGIC
# MAGIC Conformed table produced from the bronze raw layer:
# MAGIC
# MAGIC - `sa2_polygon` — one row per Stats NZ Statistical Area 2 (2023). The
# MAGIC   geometry is converted from raw GeoJSON to WKB binary so every
# MAGIC   Databricks spatial function downstream can ingest it directly.
# MAGIC
# MAGIC Property names follow the Stats NZ convention as documented on
# MAGIC DataFinder for layer 111218. Verify against the real payload on first
# MAGIC run; if names differ, this is the only place to update.
# MAGIC
# MAGIC When the census follow-up lands, this notebook gets a sibling
# MAGIC `sa2_census` table and gold joins them on `sa2_code`.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `silver`). Reads from the bronze
# MAGIC pipeline's tables via plain `spark.read.table` because they live in a
# MAGIC different pipeline.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"


# COMMAND ----------


@dlt.table(
    name="sa2_polygon",
    comment=(
        "Stats NZ Statistical Area 2 (2023, generalised) polygons. "
        "One row per SA2; geometry stored as WKB. The names roughly correspond "
        "to NZ suburbs, sometimes split (e.g. 'Onehunga West' + 'Onehunga East')."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        _source STRING COMMENT 'Upstream dataset family ("stats_nz").',
        sa2_code STRING COMMENT 'Stats NZ SA2 2023 code, 6 digits. Logical PK.',
        sa2_name STRING COMMENT 'SA2 2023 name as published, e.g. "Onehunga West".',
        ta_code STRING COMMENT 'Territorial authority code containing this SA2.',
        territorial_authority STRING COMMENT 'Territorial authority name, e.g. "Auckland".',
        region_code STRING COMMENT 'Region code containing this SA2.',
        region STRING COMMENT 'Region name, e.g. "Auckland Region".',
        land_area_km2 DOUBLE COMMENT 'Land area in square kilometres, from Stats NZ pre-computed LAND_AREA_SQ_KM. Excludes water surfaces.',
        geometry BINARY COMMENT 'WKB form of the SA2 polygon, parsed from bronze geometry struct via st_geomfromgeojson. The shape every Databricks spatial function accepts.',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect_or_drop("has_geometry", "geometry IS NOT NULL")
@dlt.expect_or_drop("has_sa2_code", "sa2_code IS NOT NULL")
def sa2_polygon():
    raw = spark.read.table(f"{BRONZE}.places_sa2_polygon_raw")

    # SA2 2023 Higher Geographies property names per Stats NZ DataFinder
    # layer 111218. Verify on first live run by inspecting one row of bronze —
    # if the names differ this is the only spot to adjust.
    #
    # Geometry handling: bronze stores it as a deeply-nested STRUCT (Auto
    # Loader's JSON inference). We round-trip it through to_json →
    # st_geomfromgeojson → st_asbinary to produce WKB once per row. The raw
    # GeoJSON lives in bronze + the .geojson audit file on the volume.
    #
    # Area: Stats NZ pre-computes LAND_AREA_SQ_KM, so we skip a per-row
    # st_area on the 1.5MB geometries.
    return raw.select(
        F.col("_source"),
        F.col("properties.SA22023_V1_00").cast("string").alias("sa2_code"),
        F.col("properties.SA22023_V1_00_NAME").cast("string").alias("sa2_name"),
        F.col("properties.TA2023_V1_00").cast("string").alias("ta_code"),
        F.col("properties.TA2023_V1_00_NAME").cast("string").alias("territorial_authority"),
        F.col("properties.REGC2023_V1_00").cast("string").alias("region_code"),
        F.col("properties.REGC2023_V1_00_NAME").cast("string").alias("region"),
        F.col("properties.LAND_AREA_SQ_KM").cast("double").alias("land_area_km2"),
        F.expr("st_asbinary(st_geomfromgeojson(to_json(geometry)))").alias("geometry"),
        F.col("_ingested_at"),
    )
