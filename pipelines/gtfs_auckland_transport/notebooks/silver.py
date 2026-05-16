# Databricks notebook source
# MAGIC %md
# MAGIC # GTFS silver layer
# MAGIC
# MAGIC Conformed transit entities. Bronze is raw GTFS; silver is the shape
# MAGIC downstream code wants:
# MAGIC
# MAGIC - `transit_stop` — stops with typed coordinates, H3 cell at resolution 8.
# MAGIC - `transit_route` — routes with agency, route-type label, readable
# MAGIC   description.
# MAGIC - `transit_service_day` — calendar.txt + calendar_dates.txt expanded
# MAGIC   into one row per `(feed_source, service_id, service_date)`.
# MAGIC
# MAGIC `stop_times` is deliberately not in silver yet. It's the heaviest table
# MAGIC and the right shape depends on what gold/isochrone needs.
# MAGIC
# MAGIC This notebook is deployed as its own pipeline (target = `silver`),
# MAGIC reading from the bronze pipeline's materialized tables via plain
# MAGIC `spark.read.table` rather than `dlt.read` (since the upstream tables
# MAGIC live in a different pipeline).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"


# COMMAND ----------
# MAGIC %md
# MAGIC ## transit_stop

# COMMAND ----------


@dlt.table(
    name="transit_stop",
    comment=(
        "Stops with typed coordinates and H3 cell at resolution 8. "
        "One row per (feed_source, stop_id)."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
@dlt.expect_or_drop("has_coordinates", "stop_lat IS NOT NULL AND stop_lon IS NOT NULL")
@dlt.expect("plausible_nz_latitude", "stop_lat BETWEEN -47.5 AND -34.0")
@dlt.expect("plausible_nz_longitude", "stop_lon BETWEEN 166.0 AND 179.0")
def transit_stop():
    stops = spark.read.table(f"{BRONZE}.gtfs_stops")

    return stops.select(
        F.col("_feed_source"),
        F.col("stop_id"),
        F.col("stop_name"),
        F.col("stop_code"),
        F.col("stop_desc"),
        F.col("stop_lat").cast("double").alias("stop_lat"),
        F.col("stop_lon").cast("double").alias("stop_lon"),
        F.col("zone_id"),
        F.col("parent_station"),
        F.expr("h3_longlatash3(stop_lon, stop_lat, 8)").alias("h3_cell_res8"),
        F.col("_ingested_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## transit_route

# COMMAND ----------


_ROUTE_TYPE_LABEL = F.expr(
    """
    CASE CAST(route_type AS INT)
      WHEN 0 THEN 'tram'
      WHEN 1 THEN 'subway'
      WHEN 2 THEN 'rail'
      WHEN 3 THEN 'bus'
      WHEN 4 THEN 'ferry'
      WHEN 5 THEN 'cable_tram'
      WHEN 6 THEN 'aerial_lift'
      WHEN 7 THEN 'funicular'
      WHEN 11 THEN 'trolleybus'
      WHEN 12 THEN 'monorail'
      ELSE 'unknown'
    END
    """
)


@dlt.table(
    name="transit_route",
    comment="Routes joined with agency, plus a readable route-type label. One row per (feed_source, route_id).",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
@dlt.expect("has_route_id", "route_id IS NOT NULL")
def transit_route():
    routes = spark.read.table(f"{BRONZE}.gtfs_routes")
    agency = spark.read.table(f"{BRONZE}.gtfs_agency").select(
        F.col("_feed_source"),
        F.col("agency_id"),
        F.col("agency_name"),
    )

    return routes.join(agency, on=["_feed_source", "agency_id"], how="left").select(
        F.col("_feed_source"),
        F.col("route_id"),
        F.col("agency_id"),
        F.col("agency_name"),
        F.col("route_short_name"),
        F.col("route_long_name"),
        F.col("route_desc"),
        F.col("route_type").cast("int").alias("route_type"),
        _ROUTE_TYPE_LABEL.alias("route_type_label"),
        F.col("route_color"),
        F.col("route_text_color"),
        F.col("_ingested_at"),
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## transit_service_day
# MAGIC
# MAGIC Expand `calendar.txt` (weekday flags + start/end dates) into one row
# MAGIC per (service_id, date), then apply `calendar_dates.txt` exceptions
# MAGIC (exception_type=1 adds a service date, 2 removes one).

# COMMAND ----------


@dlt.table(
    name="transit_service_day",
    comment="One row per (feed_source, service_id, service_date). Combines calendar.txt weekday rules with calendar_dates.txt overrides.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def transit_service_day():
    calendar = spark.read.table(f"{BRONZE}.gtfs_calendar").select(
        F.col("_feed_source"),
        F.col("service_id"),
        F.col("monday").cast("int").alias("monday"),
        F.col("tuesday").cast("int").alias("tuesday"),
        F.col("wednesday").cast("int").alias("wednesday"),
        F.col("thursday").cast("int").alias("thursday"),
        F.col("friday").cast("int").alias("friday"),
        F.col("saturday").cast("int").alias("saturday"),
        F.col("sunday").cast("int").alias("sunday"),
        F.to_date(F.col("start_date").cast("string"), "yyyyMMdd").alias("start_date"),
        F.to_date(F.col("end_date").cast("string"), "yyyyMMdd").alias("end_date"),
    )

    days = calendar.select(
        F.col("_feed_source"),
        F.col("service_id"),
        F.explode(F.sequence(F.col("start_date"), F.col("end_date"))).alias(
            "service_date"
        ),
        F.col("monday"),
        F.col("tuesday"),
        F.col("wednesday"),
        F.col("thursday"),
        F.col("friday"),
        F.col("saturday"),
        F.col("sunday"),
    )

    runs = days.withColumn(
        "weekday", F.date_format("service_date", "E")
    ).filter(
        (F.col("weekday") == "Mon") & (F.col("monday") == 1)
        | (F.col("weekday") == "Tue") & (F.col("tuesday") == 1)
        | (F.col("weekday") == "Wed") & (F.col("wednesday") == 1)
        | (F.col("weekday") == "Thu") & (F.col("thursday") == 1)
        | (F.col("weekday") == "Fri") & (F.col("friday") == 1)
        | (F.col("weekday") == "Sat") & (F.col("saturday") == 1)
        | (F.col("weekday") == "Sun") & (F.col("sunday") == 1)
    ).select("_feed_source", "service_id", "service_date")

    exceptions = spark.read.table(f"{BRONZE}.gtfs_calendar_dates").select(
        F.col("_feed_source"),
        F.col("service_id"),
        F.to_date(F.col("date").cast("string"), "yyyyMMdd").alias("service_date"),
        F.col("exception_type").cast("int").alias("exception_type"),
    )

    additions = exceptions.filter("exception_type = 1").drop("exception_type")
    removals = exceptions.filter("exception_type = 2").drop("exception_type")

    return (
        runs.unionByName(additions)
        .join(
            removals,
            on=["_feed_source", "service_id", "service_date"],
            how="left_anti",
        )
        .dropDuplicates(["_feed_source", "service_id", "service_date"])
    )
