# Databricks notebook source
# MAGIC %md
# MAGIC # Flood hazard gold layer
# MAGIC
# MAGIC `hazard` — one row per H3 res-8 cell with boolean flags for Genie and the agent.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SILVER = "housing.silver"


from flood_layer_meta import (
    COASTAL_1_AEP_SOURCES,
    COASTAL_100YR_SOURCES,
    FLOOD_PLAIN_SOURCES,
    FLOOD_PRONE_SOURCES,
    FLOOD_SENSITIVE_SOURCES,
    REGIONAL_FLOOD_SOURCES,
)

# COMMAND ----------


@dlt.table(
    name="hazard",
    comment="Flood and coastal hazard flags per H3 cell (resolution 8). Genie-ready.",
    table_properties={"quality": "gold", "project": "housing-assistant"},
    schema="""
        h3_cell BIGINT NOT NULL COMMENT 'H3 spatial index at resolution 8.',
        in_flood_plain BOOLEAN COMMENT 'Modelled flood plain or 1% AEP river flood extent.',
        in_flood_prone_area BOOLEAN COMMENT 'Catchment-level flood prone area (Auckland).',
        in_flood_sensitive_area BOOLEAN COMMENT 'Flood-sensitive planning overlay.',
        in_coastal_inundation_1_aep BOOLEAN COMMENT 'Coastal inundation 1% AEP.',
        in_coastal_inundation_100yr BOOLEAN COMMENT 'Coastal inundation 100-year return.',
        in_regional_flood_zone BOOLEAN COMMENT 'Other regional council flood hazard polygons.',
        hazard_sources ARRAY<STRING> COMMENT 'Layer ids contributing hazard at this cell.',
        max_rainfall_event INT COMMENT 'Largest rainfall ARI code when present (e.g. 100).',
        sample_report_url STRING COMMENT 'Link to a source model report when available.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
def hazard():
    h3 = spark.read.table(f"{SILVER}.flood_hazard_h3")

    def _flag(source_set):
        return F.max(
            F.when(F.col("hazard_source").isin(*sorted(source_set)), F.lit(True)).otherwise(
                F.lit(False)
            )
        )

    agg = h3.groupBy("h3_cell").agg(
        _flag(FLOOD_PLAIN_SOURCES).alias("in_flood_plain"),
        _flag(FLOOD_PRONE_SOURCES).alias("in_flood_prone_area"),
        _flag(FLOOD_SENSITIVE_SOURCES).alias("in_flood_sensitive_area"),
        _flag(COASTAL_1_AEP_SOURCES).alias("in_coastal_inundation_1_aep"),
        _flag(COASTAL_100YR_SOURCES).alias("in_coastal_inundation_100yr"),
        _flag(REGIONAL_FLOOD_SOURCES).alias("in_regional_flood_zone"),
        F.collect_set("hazard_source").alias("hazard_sources"),
        F.max("rainfall_event").alias("max_rainfall_event"),
        F.first("report_url", ignorenulls=True).alias("sample_report_url"),
    )

    return agg.select(
        "h3_cell",
        F.coalesce("in_flood_plain", F.lit(False)).alias("in_flood_plain"),
        F.coalesce("in_flood_prone_area", F.lit(False)).alias("in_flood_prone_area"),
        F.coalesce("in_flood_sensitive_area", F.lit(False)).alias("in_flood_sensitive_area"),
        F.coalesce("in_coastal_inundation_1_aep", F.lit(False)).alias(
            "in_coastal_inundation_1_aep"
        ),
        F.coalesce("in_coastal_inundation_100yr", F.lit(False)).alias(
            "in_coastal_inundation_100yr"
        ),
        F.coalesce("in_regional_flood_zone", F.lit(False)).alias("in_regional_flood_zone"),
        "hazard_sources",
        "max_rainfall_event",
        "sample_report_url",
        F.current_timestamp().alias("_updated_at"),
    )
