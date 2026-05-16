# Databricks notebook source
# MAGIC %md
# MAGIC # GTFS bronze layer
# MAGIC
# MAGIC Streaming Auto Loader tables, one per GTFS entity. Files land at
# MAGIC `/Volumes/housing/bronze/gtfs_files/<feed_source>/<run_date>/<file>.txt`;
# MAGIC each Auto Loader stream picks up the file type it watches and appends
# MAGIC rows with provenance columns (`_feed_source`, `_run_date`,
# MAGIC `_ingested_at`, `_source_file`).
# MAGIC
# MAGIC When we add the Metlink or ECan feeds later, they drop into the same
# MAGIC tables with a different `_feed_source` — no schema change.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/gtfs_files"

# All GTFS files we currently see in the Auckland Transport feed. Adding a
# new file type later (e.g. `levels.txt`) just means appending here.
GTFS_FILES = [
    "agency",
    "calendar",
    "calendar_dates",
    "fare_attributes",
    "fare_rules",
    "feed_info",
    "frequencies",
    "routes",
    "shapes",
    "stop_times",
    "stops",
    "transfers",
    "trips",
]

# COMMAND ----------


def _stream_gtfs_file(file_name: str):
    """
    Auto Loader stream over every `<file_name>/<feed>/<date>.txt` under the
    bronze gtfs_files volume. The file-type-first layout lets schema inference
    find samples directly without traversing past the load path.
    """
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .load(f"{VOLUME_ROOT}/{file_name}")
        .withColumn(
            "_feed_source",
            F.regexp_extract(F.col("_metadata.file_path"), rf"/{file_name}/([^/]+)/", 1),
        )
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"), r"/([0-9]{4}-[0-9]{2}-[0-9]{2})\.txt$", 1
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


def _make_bronze_table(file_name: str) -> None:
    """Register a streaming bronze DLT table for one GTFS file type."""

    @dlt.table(
        name=f"gtfs_{file_name}",
        comment=f"GTFS `{file_name}.txt` from all feeds. Raw columns with provenance metadata.",
        table_properties={
            "quality": "bronze",
            "project": "housing-assistant",
        },
    )
    def _bronze_table():
        return _stream_gtfs_file(file_name)


# Register a DLT table for each GTFS file. The factory function captures
# `file_name` per call, avoiding the classic Python closure-in-loop pitfall.
for _f in GTFS_FILES:
    _make_bronze_table(_f)
