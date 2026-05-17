# Databricks notebook source
# MAGIC %md
# MAGIC # places silver layer
# MAGIC
# MAGIC Two conformed tables produced from the bronze raw layer:
# MAGIC
# MAGIC - `sa2_polygon` — one row per Stats NZ Statistical Area 2 (2023). The
# MAGIC   geometry is converted from raw GeoJSON to WKB binary so every
# MAGIC   Databricks spatial function downstream can ingest it directly.
# MAGIC - `sa2_census` — one row per SA2 with demographic columns gold uses
# MAGIC   (population, median age). Stats NZ ships the census as a wide CSV
# MAGIC   with hundreds of columns; this silver table projects just what we
# MAGIC   need today and leaves the rest in bronze for future expansion.
# MAGIC
# MAGIC Property/column names follow Stats NZ DataFinder conventions. Verify
# MAGIC against the real payload on first run — the most likely break point is
# MAGIC the census CSV column names, which Stats NZ revises occasionally.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `silver`). Reads from the bronze
# MAGIC pipeline's tables via plain `spark.read.table` because they live in a
# MAGIC different pipeline.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"


def _latest_snapshot(table_name: str):
    """
    Filter a streaming-bronze table to its most recent `_run_date` snapshot.

    Why: each `fetch_*` run lands a new date-stamped file under the volume
    and Auto Loader streams every file into bronze, so bronze accumulates
    one full snapshot per run. Without this filter, silver would join on
    duplicated rows and gold counts multiply by the number of accumulated
    snapshots.
    """
    raw = spark.read.table(table_name)
    max_run_date = raw.agg(F.max("_run_date")).collect()[0][0]
    return raw.filter(F.col("_run_date") == max_run_date)


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
    raw = _latest_snapshot(f"{BRONZE}.places_sa2_polygon_raw")

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


# COMMAND ----------
# MAGIC %md
# MAGIC ## sa2_census
# MAGIC
# MAGIC Stats NZ 2023 Census aggregates per SA2. Projects just the two
# MAGIC columns gold needs today (population, median age) from the very wide
# MAGIC source table (~530 columns named `VAR_1_N`). The lookup CSV in the
# MAGIC source zip maps codes to descriptions; here are the ones we use:
# MAGIC
# MAGIC | Column     | Meaning                                                       |
# MAGIC |------------|---------------------------------------------------------------|
# MAGIC | `VAR_1_3`  | 2023 Census usually resident population count (Total)         |
# MAGIC | `VAR_1_69` | 2023 Median age (Median measure, Variable1 = Age, Total)      |
# MAGIC
# MAGIC Stats NZ uses `-999` as the suppression / not-applicable sentinel
# MAGIC (e.g. for the "Inland water" SA2s that contain only lake surface —
# MAGIC population is 0, median age can't be calculated). `nullif(...)`
# MAGIC turns those into proper SQL NULLs before they reach gold.
# MAGIC
# MAGIC To add more demographic columns later, look up the right VAR_N code
# MAGIC in the lookup table and add it to this projection.

# COMMAND ----------


@dlt.table(
    name="sa2_census",
    comment=(
        "Stats NZ 2023 Census aggregates by SA2 — narrow projection with just "
        "the demographic columns gold.suburb uses today (population, median "
        "age). Bronze keeps the wide raw form (~530 columns) for future "
        "expansion. -999 sentinel values are replaced with NULL."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        _source STRING COMMENT 'Upstream dataset family ("stats_nz").',
        sa2_code STRING COMMENT 'Stats NZ SA2 2023 code, 6 digits. Joins to sa2_polygon.sa2_code.',
        population_2023 INT COMMENT '2023 census usually resident population count for this SA2 (source: VAR_1_3). NULL where Stats NZ suppressed the value (-999 sentinel).',
        median_age_2023 DOUBLE COMMENT '2023 census median age (years) of usually-resident population (source: VAR_1_69). NULL where Stats NZ suppressed the value (-999 sentinel).',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect_or_drop("has_sa2_code", "sa2_code IS NOT NULL")
def sa2_census():
    raw = _latest_snapshot(f"{BRONZE}.places_sa2_census_raw")

    return raw.selectExpr(
        "_source",
        "cast(SA22023_V1_00 AS STRING) AS sa2_code",
        "cast(nullif(VAR_1_3, -999) AS INT) AS population_2023",
        "cast(nullif(VAR_1_69, -999) AS DOUBLE) AS median_age_2023",
        "_ingested_at",
    )
