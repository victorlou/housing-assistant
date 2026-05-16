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
        "One row per (feed_source, stop_id)."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
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
        "One row per (feed_source, route_id)."
    ),
    table_properties={"quality": "gold", "project": "housing-assistant"},
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
