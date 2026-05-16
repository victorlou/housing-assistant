# Databricks notebook source
# MAGIC %md
# MAGIC # GTFS gold layer
# MAGIC
# MAGIC Dimension tables for downstream consumers (Genie, the agent, the
# MAGIC dashboard). Two tables today; both are Genie-ready.
# MAGIC
# MAGIC - `transit_stop` — public-transit stops keyed by H3 cell.
# MAGIC - `transit_route` — routes with agency and a human-readable type label.
# MAGIC
# MAGIC The big one — `isochrone` (origin H3 → reachable H3s by mode and minute
# MAGIC bucket) — needs a routing engine (r5py or similar) and is a follow-up.
# MAGIC
# MAGIC Deployed as its own pipeline (target = `gold`). Reads from the silver
# MAGIC pipeline's materialized tables via plain `spark.read.table`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"


# COMMAND ----------


@dlt.table(
    name="transit_stop",
    comment=(
        "Public-transit stops with H3 cell at resolution 8. "
        "One row per (feed_source, stop_id). Genie-ready."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        feed_source STRING COMMENT 'Source GTFS feed identifier, e.g. "auckland_transport".',
        stop_id STRING COMMENT 'Stop identifier as published by the operator. Unique within (feed_source).',
        stop_name STRING COMMENT 'Public-facing stop name, e.g. "Britomart Train Station".',
        stop_code STRING COMMENT 'Short code shown to riders on signage and apps.',
        stop_lat DOUBLE COMMENT 'Latitude in WGS84 decimal degrees.',
        stop_lon DOUBLE COMMENT 'Longitude in WGS84 decimal degrees.',
        h3_cell BIGINT COMMENT 'H3 spatial index cell at resolution 8 (~0.7 km² hexagons). Join key for spatial queries against suburbs and isochrones.'
    """,
)
def transit_stop():
    return spark.read.table(f"{SILVER}.transit_stop").select(
        F.col("_feed_source").alias("feed_source"),
        F.col("stop_id"),
        F.col("stop_name"),
        F.col("stop_code"),
        F.col("stop_lat"),
        F.col("stop_lon"),
        F.col("h3_cell_res8").alias("h3_cell"),
    )


# COMMAND ----------


@dlt.table(
    name="transit_route",
    comment=(
        "Transit routes with agency and route-type labels. "
        "One row per (feed_source, route_id). Genie-ready."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        feed_source STRING COMMENT 'Source GTFS feed identifier, e.g. "auckland_transport".',
        route_id STRING COMMENT 'Route identifier as published. Unique within (feed_source).',
        agency_id STRING COMMENT 'Operator agency identifier.',
        agency_name STRING COMMENT 'Human-readable operator name, e.g. "AT Metro Bus", "Fullers360".',
        route_short_name STRING COMMENT 'Short route name shown to riders, e.g. "74", "WEST".',
        route_long_name STRING COMMENT 'Long route description, e.g. "Britomart - Glen Innes".',
        route_type INT COMMENT 'GTFS route type code (0=tram, 1=subway, 2=rail, 3=bus, 4=ferry, 5=cable_tram, 6=aerial_lift, 7=funicular, 11=trolleybus, 12=monorail).',
        route_type_label STRING COMMENT 'Human-readable route type derived from route_type ("bus", "rail", "ferry", ...).'
    """,
)
def transit_route():
    return spark.read.table(f"{SILVER}.transit_route").select(
        F.col("_feed_source").alias("feed_source"),
        F.col("route_id"),
        F.col("agency_id"),
        F.col("agency_name"),
        F.col("route_short_name"),
        F.col("route_long_name"),
        F.col("route_type"),
        F.col("route_type_label"),
    )
