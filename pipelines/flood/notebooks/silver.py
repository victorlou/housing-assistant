# Databricks notebook source
# MAGIC %md
# MAGIC # Flood hazard silver layer
# MAGIC
# MAGIC - `flood_hazard_zone` — latest polygon per source with conformed attributes.
# MAGIC - `flood_hazard_h3` — H3 res-8 cells overlapping each hazard polygon.

# COMMAND ----------

import json

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType
from pyspark.sql.window import Window

H3_RESOLUTION = 8
BRONZE = "housing.bronze"


from flood_layer_meta import layer_metadata_rows

# COMMAND ----------


def _layer_metadata_df():
    schema = StructType(
        [
            StructField("hazard_source", StringType(), True),
            StructField("file_stem", StringType(), True),
            StructField("publisher", StringType(), True),
            StructField("region_name", StringType(), True),
            StructField("return_period", StringType(), True),
            StructField("aep", StringType(), True),
            StructField("hazard_category", StringType(), True),
        ]
    )
    return spark.createDataFrame(layer_metadata_rows(), schema=schema)


def _prop(field: str):
    return F.get_json_object(F.col("properties_json"), f"$.{field}")


def _polygon_wkt_from_geojson(geojson_str: str) -> str | None:
    try:
        geom = json.loads(geojson_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if geom.get("type") != "Polygon":
        return None
    rings = geom.get("coordinates") or []
    if not rings:
        return None
    ring = list(rings[0])
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        return None
    coords = ", ".join(f"{float(x)} {float(y)}" for x, y in ring)
    return f"POLYGON(({coords}))"


@F.udf(StringType())
def _safe_polygon_wkt(geojson_str: str) -> str | None:
    if not geojson_str:
        return None
    return _polygon_wkt_from_geojson(geojson_str)


def _latest_bronze_features():
    bronze = spark.read.table(f"{BRONZE}.flood_hazard_feature")
    w = Window.partitionBy("_hazard_source", "source_object_id").orderBy(F.col("_run_date").desc())
    return (
        bronze.withColumn(
            "source_object_id",
            F.coalesce(
                _prop("OBJECTID"),
                _prop("objectid"),
                _prop("id"),
                _prop("GlobalID"),
            ),
        )
        .withColumn("row_num", F.row_number().over(w))
        .filter(F.col("row_num") == 1)
        .drop("row_num")
    )


def _conformed_features(df):
    meta = _layer_metadata_df()
    joined = df.join(meta, df["_hazard_source"] == meta["file_stem"], how="left")
    return (
        joined.withColumn("geom_wkt", _safe_polygon_wkt(F.col("geometry_json")))
        .filter(F.col("geom_wkt").isNotNull())
        .withColumn("geom", F.expr("ST_GeomFromWKT(geom_wkt)"))
        .filter(F.expr("ST_IsValid(geom)"))
        .filter(
            (F.expr("ST_Y(ST_Centroid(geom))").between(-47.5, -33.5))
            & (F.expr("ST_X(ST_Centroid(geom))").between(165.0, 179.5))
        )
        .withColumn(
            "hazard_label",
            F.coalesce(_prop("Hazard"), _prop("Label"), _prop("Title")),
        )
        .withColumn(
            "rainfall_event",
            F.coalesce(_prop("RAINFALL_EVENT"), _prop("rainfall_event")).cast("int"),
        )
        .withColumn(
            "climate_change_adjusted",
            F.coalesce(_prop("CLIMATE_CHANGE_ADJUSTED"), _prop("Climate_Change_Adjusted")),
        )
        .withColumn(
            "year_produced",
            F.coalesce(_prop("YEAR_PRODUCED"), _prop("Year_Produced")),
        )
        .withColumn(
            "report_url",
            F.coalesce(_prop("PDF_Link"), _prop("Weblink"), _prop("weblink")),
        )
        .withColumn("title", F.coalesce(_prop("Title"), _prop("title")))
        .withColumn(
            "description",
            F.coalesce(_prop("Description"), _prop("description")),
        )
        .select(
            F.col("hazard_source"),
            F.col("file_stem"),
            F.col("publisher"),
            F.col("region_name"),
            F.col("return_period"),
            F.col("aep"),
            F.col("hazard_category"),
            F.col("source_object_id"),
            F.col("hazard_label"),
            F.col("rainfall_event"),
            F.col("climate_change_adjusted"),
            F.col("year_produced"),
            F.col("title"),
            F.col("description"),
            F.col("report_url"),
            F.expr("st_asbinary(geom)").alias("geometry"),
            F.col("_run_date"),
            F.col("_ingested_at"),
            F.col("_source_file"),
        )
        .drop("geom_wkt")
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## flood_hazard_zone

# COMMAND ----------


@dlt.table(
    name="flood_hazard_zone",
    comment="Conformed flood hazard polygons, one row per (hazard_source, source_object_id).",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
@dlt.expect_or_drop("has_geometry", "geometry IS NOT NULL")
def flood_hazard_zone():
    return _conformed_features(_latest_bronze_features())


# COMMAND ----------
# MAGIC %md
# MAGIC ## flood_hazard_h3

# COMMAND ----------


@dlt.table(
    name="flood_hazard_h3",
    comment="H3 res-8 cells overlapping flood hazard polygons.",
    table_properties={"quality": "silver", "project": "housing-assistant"},
)
def flood_hazard_h3():
    zones = spark.read.table("LIVE.flood_hazard_zone")
    # Small polygons often return empty polyfill; centroid H3 covers point lookup.
    return (
        zones.selectExpr(
            "hazard_source",
            "hazard_category",
            "region_name",
            "rainfall_event",
            "report_url",
            f"h3_longlatash3("
            f"ST_X(ST_Centroid(ST_GeomFromWKB(geometry))), "
            f"ST_Y(ST_Centroid(ST_GeomFromWKB(geometry))), "
            f"{H3_RESOLUTION}) AS h3_cell",
        )
        .select(
            "hazard_source",
            "hazard_category",
            "region_name",
            "h3_cell",
            F.col("rainfall_event"),
            F.col("report_url"),
            F.current_timestamp().alias("_ingested_at"),
        )
        .distinct()
    )
