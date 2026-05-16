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
    schema="""
        _feed_source STRING COMMENT 'Source GTFS feed identifier (e.g. "auckland_transport"). Derived from the file path.',
        stop_id STRING COMMENT 'Stop identifier as published by the operator. Unique within (_feed_source).',
        stop_name STRING COMMENT 'Public-facing stop name, e.g. "Britomart Train Station".',
        stop_code STRING COMMENT 'Short code shown to riders on signage and apps. Optional in GTFS.',
        stop_desc STRING COMMENT 'Free-text description of the stop. Often blank.',
        stop_lat DOUBLE COMMENT 'Latitude in WGS84 decimal degrees.',
        stop_lon DOUBLE COMMENT 'Longitude in WGS84 decimal degrees.',
        zone_id STRING COMMENT 'Fare zone the stop belongs to.',
        parent_station STRING COMMENT 'stop_id of the parent station, when this stop is a platform or boarding area of a larger station. Null otherwise.',
        h3_cell_res8 BIGINT COMMENT 'H3 spatial index cell at resolution 8 (~0.7 km² hexagons). Use for spatial joins to suburbs and isochrones.',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect_or_drop("has_coordinates", "stop_lat IS NOT NULL AND stop_lon IS NOT NULL")
@dlt.expect("plausible_nz_latitude", "stop_lat BETWEEN -47.5 AND -34.0")
@dlt.expect("plausible_nz_longitude", "stop_lon BETWEEN 166.0 AND 179.0")
def transit_stop():
    stops = spark.read.table(f"{BRONZE}.gtfs_stops")

    # Cast ID-style columns to STRING explicitly. GTFS IDs are conceptually
    # identifiers, not numbers (leading zeros and alphanumeric values are
    # legal). Auto Loader may have inferred them as INT if the sample
    # happened to be all-digits.
    return stops.select(
        F.col("_feed_source"),
        F.col("stop_id").cast("string").alias("stop_id"),
        F.col("stop_name").cast("string").alias("stop_name"),
        F.col("stop_code").cast("string").alias("stop_code"),
        F.col("stop_desc").cast("string").alias("stop_desc"),
        F.col("stop_lat").cast("double").alias("stop_lat"),
        F.col("stop_lon").cast("double").alias("stop_lon"),
        F.col("zone_id").cast("string").alias("zone_id"),
        F.col("parent_station").cast("string").alias("parent_station"),
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
    schema="""
        _feed_source STRING COMMENT 'Source GTFS feed identifier.',
        route_id STRING COMMENT 'Route identifier as published. Unique within (_feed_source).',
        agency_id STRING COMMENT 'Operator agency identifier.',
        agency_name STRING COMMENT 'Human-readable operator name, e.g. "AT Metro Bus" or "Fullers360".',
        route_short_name STRING COMMENT 'Short route name shown to riders, e.g. "74" or "WEST".',
        route_long_name STRING COMMENT 'Long route description, e.g. "Britomart - Glen Innes".',
        route_desc STRING COMMENT 'Free-text description of the route. Often blank.',
        route_type INT COMMENT 'GTFS route type code (0=tram, 1=subway, 2=rail, 3=bus, 4=ferry, 5=cable_tram, 6=aerial_lift, 7=funicular, 11=trolleybus, 12=monorail).',
        route_type_label STRING COMMENT 'Human-readable route type derived from route_type (bus, rail, ferry, ...).',
        route_color STRING COMMENT 'Hex color without # used to identify the route on maps and signage.',
        route_text_color STRING COMMENT 'Hex color without # for text rendered over route_color.',
        _ingested_at TIMESTAMP COMMENT 'When this row was written to silver.'
    """,
)
@dlt.expect("has_route_id", "route_id IS NOT NULL")
def transit_route():
    # Cast agency_id on both sides of the join to STRING so the join key
    # types are guaranteed to align regardless of what bronze inferred.
    routes = spark.read.table(f"{BRONZE}.gtfs_routes").withColumn(
        "agency_id", F.col("agency_id").cast("string")
    )
    agency = (
        spark.read.table(f"{BRONZE}.gtfs_agency")
        .withColumn("agency_id", F.col("agency_id").cast("string"))
        .select(
            F.col("_feed_source"),
            F.col("agency_id"),
            F.col("agency_name").cast("string").alias("agency_name"),
        )
    )

    return routes.join(agency, on=["_feed_source", "agency_id"], how="left").select(
        F.col("_feed_source"),
        F.col("route_id").cast("string").alias("route_id"),
        F.col("agency_id"),
        F.col("agency_name"),
        F.col("route_short_name").cast("string").alias("route_short_name"),
        F.col("route_long_name").cast("string").alias("route_long_name"),
        F.col("route_desc").cast("string").alias("route_desc"),
        F.col("route_type").cast("int").alias("route_type"),
        _ROUTE_TYPE_LABEL.alias("route_type_label"),
        F.col("route_color").cast("string").alias("route_color"),
        F.col("route_text_color").cast("string").alias("route_text_color"),
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
    schema="""
        _feed_source STRING COMMENT 'Source GTFS feed identifier.',
        service_id STRING COMMENT 'Service pattern identifier. A service is a collection of dates on which trips run; trips reference services to determine when they operate.',
        service_date DATE COMMENT 'Calendar date on which this service is active.'
    """,
)
def transit_service_day():
    calendar = spark.read.table(f"{BRONZE}.gtfs_calendar").select(
        F.col("_feed_source"),
        F.col("service_id").cast("string").alias("service_id"),
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
        F.col("service_id").cast("string").alias("service_id"),
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
