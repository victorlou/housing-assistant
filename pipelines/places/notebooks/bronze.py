# Databricks notebook source
# MAGIC %md
# MAGIC # places bronze layer
# MAGIC
# MAGIC One streaming DLT table per dataset under `places_files/`:
# MAGIC
# MAGIC - `places_sa2_polygon_raw` — Auto Loader over the JSONL features
# MAGIC   written by `fetch.py` for the SA2 2023 polygon layer.
# MAGIC
# MAGIC Each table picks up new <date>-stamped landings on every pipeline run.
# MAGIC Provenance columns (`_source`, `_run_date`, `_ingested_at`,
# MAGIC `_source_file`) are attached identically across all bronze tables here.
# MAGIC
# MAGIC Future datasets (census, school zones, amenity points) land here as
# MAGIC additional entries in `GEOJSON_DATASETS` (or new `CSV_DATASETS`)
# MAGIC without changing this notebook's body.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

PLACES_VOLUME_ROOT = "/Volumes/housing/bronze/places_files"

GEOJSON_DATASETS = [
    {
        "table": "places_sa2_polygon_raw",
        "source": "stats_nz",
        "path": f"{PLACES_VOLUME_ROOT}/sa2_polygons",
        "comment": (
            "Raw Stats NZ Statistical Area 2 (2023, generalised) polygons "
            "from DataFinder layer 111218 (Higher Geographies — SA2 polygons "
            "with TA and region attributes pre-joined). One row per GeoJSON Feature."
        ),
    },
]

# COMMAND ----------


def _stream_jsonl(path: str, source_tag: str):
    """Auto Loader stream over one-feature-per-line JSONL."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("multiline", "false")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source", F.lit(source_tag))
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"),
                r"/([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl$",
                1,
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


def _make_geojson_table(spec: dict) -> None:
    @dlt.table(
        name=spec["table"],
        comment=spec["comment"],
        table_properties={"quality": "bronze", "project": "housing-assistant"},
    )
    def _bronze_table():
        return _stream_jsonl(spec["path"], spec["source"])


for _spec in GEOJSON_DATASETS:
    _make_geojson_table(_spec)
