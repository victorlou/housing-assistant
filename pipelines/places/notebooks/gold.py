# Databricks notebook source
# MAGIC %md
# MAGIC # places gold layer
# MAGIC
# MAGIC The two contract tables every consumer joins against:
# MAGIC
# MAGIC - `housing.gold.suburb` — one row per SA2 (Stats NZ Statistical Area 2,
# MAGIC   2023). Human-facing dim with name, TA, region, centroid, area.
# MAGIC   `population_2023` and `median_age_2023` are reserved nullable columns
# MAGIC   on the schema; they populate in a follow-up PR that wires up Stats NZ
# MAGIC   census 2023 (DataFinder layers 120897 + 120898) via manual CSV upload.
# MAGIC - `housing.gold.h3_cell` — one row per H3 res-8 cell covering an SA2,
# MAGIC   with the owning `suburb_id`. The workhorse — every fact table joins
# MAGIC   here on `h3_cell`, then `h3_cell.suburb_id → gold.suburb` is a flat
# MAGIC   lookup.
# MAGIC
# MAGIC We keep the table name `suburb` even though the underlying grain is
# MAGIC SA2 — the column shape and consumer contract are what matter, and
# MAGIC "suburb" is the language Genie and the agent will use. The `suburb_id`
# MAGIC value happens to be the SA2 code.
# MAGIC
# MAGIC Cell-to-suburb assignment uses `h3_polyfillash3` with center-based
# MAGIC polyfill semantics — Databricks' implementation emits cells whose
# MAGIC *centre* falls inside the polygon, so each cell maps to at most one
# MAGIC SA2 and we don't need a boundary tie-break. (Edge case: cells whose
# MAGIC centre lies on an exact boundary may appear under multiple SA2s; we
# MAGIC dedupe by `h3_cell` to pick one.)
# MAGIC
# MAGIC Note: Databricks' `h3_*` functions take WKB (BINARY) or WKT (STRING),
# MAGIC not the newer GEOMETRY type, so we pass silver's WKB column directly
# MAGIC and only convert to GEOMETRY for ST_* ops that need it.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `gold`). Reads from the silver
# MAGIC pipeline via `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"
H3_RESOLUTION = 8


# COMMAND ----------
# MAGIC %md
# MAGIC ## housing.gold.suburb
# MAGIC
# MAGIC One row per SA2. Geometry-derived attributes (centroid cell, area)
# MAGIC are materialised once. Demographic columns (population_2023,
# MAGIC median_age_2023) stay null until the census follow-up.

# COMMAND ----------


@dlt.table(
    name="suburb",
    comment=(
        "Canonical NZ suburb dimension. One row per Stats NZ Statistical "
        "Area 2 (SA2) — the smallest official geography Stats NZ publishes. "
        "SA2 names roughly correspond to colloquial NZ suburbs (e.g. "
        "'Newmarket', 'Hataitai South') but are sometimes finer than common "
        "usage ('Onehunga' splits into 'Onehunga West' + 'Onehunga East' + "
        "'Onehunga Central'). The table also contains non-residential "
        "polygons — harbour surfaces, inland water (lakes), ocean EEZ cells, "
        "airport runway zones — which have population_2023 near zero. "
        "FILTERING GUIDANCE: for residential 'where should I live' queries, "
        "filter `population_2023 > 500` (or `> 0` more strictly) to exclude "
        "those non-residential polygons; for exhaustive geographic queries, "
        "keep them. JOINS: connects to housing.gold.h3_cell via suburb_id "
        "(the spatial bridge from any H3-keyed fact); connects to "
        "housing.gold.ta__month and housing.gold.ta__quarter via "
        "territorial_authority = ta_name (Stats NZ canonical names); "
        "connects to housing.gold.region__quarter via region."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    partition_cols=["region"],
    schema="""
        suburb_id STRING NOT NULL COMMENT 'Stats NZ SA2 2023 code (6 digits). Stable logical PK.',
        suburb_name STRING NOT NULL COMMENT 'SA2 2023 name as published by Stats NZ, e.g. "Onehunga West". Close to colloquial NZ suburb usage, sometimes split.',
        territorial_authority STRING COMMENT 'Containing TA, e.g. "Auckland".',
        region STRING COMMENT 'Containing region, e.g. "Auckland Region".',
        centroid_h3 BIGINT COMMENT 'H3 cell at the SA2 polygon centroid (resolution 8). Use as a single-point handle for spatial queries.',
        land_area_km2 DOUBLE COMMENT 'Land area in square kilometres (Stats NZ LAND_AREA_SQ_KM, excludes water surfaces).',
        population_2023 INT COMMENT 'Total usually-resident population from Stats NZ 2023 census (source: VAR_1_3, -999 sentinel replaced with NULL). Doubles as a residential-vs-non-residential proxy — SA2s with population near zero (e.g. harbour, inland water, EEZ) are not places people live. Filter > 500 for Sarah-style residential queries.',
        median_age_2023 DOUBLE COMMENT 'Median age (years) of usually-resident population from Stats NZ 2023 census (source: VAR_1_69, -999 sentinel replaced with NULL). NULL on SA2s with no residents.',
        geometry BINARY COMMENT 'SA2 polygon as WKB. Carried through from silver for downstream spatial work.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_centroid", "centroid_h3 IS NOT NULL")
def suburb():
    polygons = spark.read.table(f"{SILVER}.sa2_polygon")
    census = spark.read.table(f"{SILVER}.sa2_census")

    # Centroid: GEOMETRY → WKB roundtrip because h3_pointash3 needs BINARY.
    # The path is: WKB (silver) → GEOMETRY (st_geomfromwkb) → centroid
    # (st_centroid, still GEOMETRY) → WKB (st_asbinary) → H3 cell.
    #
    # LEFT JOIN census: if a census row doesn't exist for a given SA2 (e.g.
    # population was suppressed for privacy, or the census CSV missed an SA2),
    # the demographic columns land null. Spatial attributes are always set.
    return polygons.join(census, on="sa2_code", how="left").select(
        F.col("sa2_code").alias("suburb_id"),
        F.col("sa2_name").alias("suburb_name"),
        F.col("territorial_authority"),
        F.col("region"),
        F.expr(
            f"h3_pointash3(st_asbinary(st_centroid(st_geomfromwkb(geometry))), {H3_RESOLUTION})"
        ).alias("centroid_h3"),
        F.col("land_area_km2"),
        F.col("population_2023"),
        F.col("median_age_2023"),
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
        suburb_id STRING COMMENT 'FK to housing.gold.suburb.suburb_id (= SA2 code). Null only on the unlikely boundary tie that survived dropDuplicates.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_h3_cell", "h3_cell IS NOT NULL")
def h3_cell():
    polygons = spark.read.table(f"{SILVER}.sa2_polygon")

    # Pass silver.geometry (WKB) straight to h3_polyfillash3 — no
    # st_geomfromwkb wrap; the function wants BINARY/STRING, not GEOMETRY.
    # Center-based semantics mean we usually emit each cell at most once;
    # dropDuplicates handles the rare tie where a cell's centre lands on
    # an exact SA2 boundary line.
    return (
        polygons.selectExpr(
            "sa2_code AS suburb_id",
            f"explode(h3_polyfillash3(geometry, {H3_RESOLUTION})) AS h3_cell",
        )
        .select(
            F.col("h3_cell"),
            F.col("suburb_id"),
            F.current_timestamp().alias("_updated_at"),
        )
        .dropDuplicates(["h3_cell"])
    )
