# Databricks notebook source
# MAGIC %md
# MAGIC # places gold layer
# MAGIC
# MAGIC The two contract tables every consumer joins against:
# MAGIC
# MAGIC - `housing.gold.suburb` — one row per SA2 (Stats NZ Statistical Area 2,
# MAGIC   2023). Human-facing dim with name, TA, region, centroid, area, and
# MAGIC   2023 Census demographics from `housing.silver.census_sa2_features`.
# MAGIC - `housing.gold.h3_cell` — one row per H3 res-8 cell covering an SA2,
# MAGIC   with the owning `suburb_id`. The workhorse — every fact table joins
# MAGIC   here on `h3_cell`, then `h3_cell.suburb_id → gold.suburb` is a flat
# MAGIC   lookup.
# MAGIC
# MAGIC Run `census_2023_ingest` before refreshing this gold pipeline so
# MAGIC `census_sa2_features` exists.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"
CENSUS_FEATURES = f"{SILVER}.census_sa2_features"
H3_RESOLUTION = 8


def _census_features_df():
    if not spark.catalog.tableExists(CENSUS_FEATURES):
        return None
    return spark.read.table(CENSUS_FEATURES).select(
        F.col("sa2_code"),
        F.col("population_total").cast("int").alias("population_2023"),
        F.col("median_age").alias("median_age_2023"),
        F.col("median_household_income").alias("median_household_income_2023"),
        F.col("households_total").cast("int").alias("household_count_2023"),
        F.col("owner_occupier_pct").alias("owner_occupier_pct_2023"),
        F.col("median_weekly_rent").alias("median_weekly_rent_2023"),
        F.col("percent_crowded").alias("percent_crowded_2023"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## housing.gold.suburb

# COMMAND ----------


@dlt.table(
    name="suburb",
    comment=(
        "Canonical NZ suburb dimension, keyed by Stats NZ SA2 2023 code. "
        "One row per Statistical Area 2 — the smallest official geography "
        "Stats NZ publishes. SA2 names roughly correspond to colloquial NZ "
        "suburbs but are sometimes finer than common usage. Non-residential "
        "polygons (harbour, inland water, EEZ) have population_2023 near zero; "
        "filter population_2023 > 500 for residential queries. "
        "2023 Census columns from housing.silver.census_sa2_features when "
        "available. Joins: gold.h3_cell via suburb_id; TA-level facts via "
        "territorial_authority; region-level facts via region."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["region"],
    schema="""
        suburb_id STRING NOT NULL COMMENT 'Stats NZ SA2 2023 code (6 digits). Stable logical PK.',
        suburb_name STRING NOT NULL COMMENT 'SA2 2023 name as published by Stats NZ.',
        territorial_authority STRING COMMENT 'Containing TA, e.g. "Auckland".',
        region STRING COMMENT 'Containing region, e.g. "Auckland Region".',
        centroid_h3 BIGINT COMMENT 'H3 cell at the SA2 polygon centroid (resolution 8). Use as a single-point handle for spatial queries.',
        land_area_km2 DOUBLE COMMENT 'Land area in square kilometres (Stats NZ LAND_AREA_SQ_KM, excludes water surfaces).',
        population_2023 INT COMMENT 'Total usual residents (2023 Census). Filter > 500 for residential queries.',
        median_age_2023 DOUBLE COMMENT 'Median age of usual residents (2023 Census).',
        median_household_income_2023 DOUBLE COMMENT 'Median total household income ($, 2023 Census).',
        household_count_2023 INT COMMENT 'Households in occupied private dwellings (2023).',
        owner_occupier_pct_2023 DOUBLE COMMENT 'Share of households that own or partly own their dwelling.',
        median_weekly_rent_2023 DOUBLE COMMENT 'Median weekly rent for renting households ($, 2023).',
        percent_crowded_2023 DOUBLE COMMENT 'Share of households that are crowded (2023).',
        geometry BINARY COMMENT 'SA2 polygon as WKB. Carried through from silver for downstream spatial work.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_centroid", "centroid_h3 IS NOT NULL")
def suburb():
    polygons = spark.read.table(f"{SILVER}.sa2_polygon")
    base = polygons.select(
        F.col("sa2_code").alias("suburb_id"),
        F.col("sa2_name").alias("suburb_name"),
        F.col("territorial_authority"),
        F.col("region"),
        F.expr(
            f"h3_pointash3(st_asbinary(st_centroid(st_geomfromwkb(geometry))), {H3_RESOLUTION})"
        ).alias("centroid_h3"),
        F.col("land_area_km2"),
        F.col("geometry"),
    )

    census = _census_features_df()
    if census is None:
        return base.select(
            F.col("suburb_id"),
            F.col("suburb_name"),
            F.col("territorial_authority"),
            F.col("region"),
            F.col("centroid_h3"),
            F.col("land_area_km2"),
            F.lit(None).cast("int").alias("population_2023"),
            F.lit(None).cast("double").alias("median_age_2023"),
            F.lit(None).cast("double").alias("median_household_income_2023"),
            F.lit(None).cast("int").alias("household_count_2023"),
            F.lit(None).cast("double").alias("owner_occupier_pct_2023"),
            F.lit(None).cast("double").alias("median_weekly_rent_2023"),
            F.lit(None).cast("double").alias("percent_crowded_2023"),
            F.col("geometry"),
            F.current_timestamp().alias("_updated_at"),
        )

    return base.join(census, base.suburb_id == census.sa2_code, how="left").select(
        F.col("suburb_id"),
        F.col("suburb_name"),
        F.col("territorial_authority"),
        F.col("region"),
        F.col("centroid_h3"),
        F.col("land_area_km2"),
        F.col("population_2023"),
        F.col("median_age_2023"),
        F.col("median_household_income_2023"),
        F.col("household_count_2023"),
        F.col("owner_occupier_pct_2023"),
        F.col("median_weekly_rent_2023"),
        F.col("percent_crowded_2023"),
        F.col("geometry"),
        F.current_timestamp().alias("_updated_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## housing.gold.h3_cell

# COMMAND ----------


@dlt.table(
    name="h3_cell",
    comment=(
        "Every H3 cell (resolution 8, ~0.7 km² hexagon) whose centre falls "
        "inside an NZ SA2, mapped to that SA2's suburb_id. This is the "
        "spine for spatial joins across the lakehouse: any fact keyed by "
        "H3 cell (gold.transit_stop.h3_cell, gold.isochrone.destination_h3 "
        "/.origin_h3, gold.amenity__h3.h3_cell, future listings) "
        "reaches its suburb name through this bridge. Standard pattern: "
        "`JOIN gold.h3_cell USING (h3_cell)` then `JOIN gold.suburb ON "
        "suburb_id`. Built via Databricks' centre-based h3_polyfillash3, "
        "so each cell maps to at most one SA2 (cells whose centres fall "
        "in water/EEZ get assigned to harbour-style SA2s — filter on "
        "gold.suburb.population_2023 > 0 to exclude those if querying "
        "for residential context)."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        h3_cell BIGINT NOT NULL COMMENT 'H3 cell at resolution 8. Logical PK.',
        suburb_id STRING COMMENT 'FK to housing.gold.suburb.suburb_id (= SA2 code).',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_h3_cell", "h3_cell IS NOT NULL")
def h3_cell():
    polygons = spark.read.table(f"{SILVER}.sa2_polygon")

    return polygons.selectExpr(
        "sa2_code AS suburb_id",
        f"explode(h3_polyfillash3(geometry, {H3_RESOLUTION})) AS h3_cell",
    ).select(
        F.col("h3_cell"),
        F.col("suburb_id"),
        F.current_timestamp().alias("_updated_at"),
    ).dropDuplicates(["h3_cell"])
