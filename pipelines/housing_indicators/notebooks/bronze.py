# Databricks notebook source
# MAGIC %md
# MAGIC # housing_indicators bronze layer
# MAGIC
# MAGIC One streaming DLT table per dataset under `housing_indicators_files/`:
# MAGIC
# MAGIC - `housing_indicators_hud_lhs_raw` — Auto Loader over the long-format
# MAGIC   CSV written by `fetch.py` from the HUD Local Housing Statistics XLSX.
# MAGIC   One row per (date, area, theme, series) observation.
# MAGIC
# MAGIC Future datasets (Stats NZ Property Transfer Stats if/when it returns,
# MAGIC additional MBIE feeds, etc.) land here as additional entries in
# MAGIC `CSV_DATASETS` without changing the notebook body.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

HOUSING_INDICATORS_VOLUME_ROOT = "/Volumes/housing/bronze/housing_indicators_files"

CSV_DATASETS = [
    {
        "table": "housing_indicators_hud_lhs_raw",
        "source": "hud",
        "path": f"{HOUSING_INDICATORS_VOLUME_ROOT}/hud_lhs",
        "comment": (
            "Raw HUD Local Housing Statistics — TA-level monthly NZ housing "
            "indicators (prices, rents, affordability, MSD waiting list, "
            "census tenure/crowding). Long format: one row per "
            "(date, area_name, theme, series, ethnicity). "
            "Sourced from hud.govt.nz/stats-and-insights/local-housing-statistics."
        ),
    },
]

# COMMAND ----------


def _stream_csv(path: str, source_tag: str):
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .load(path)
        .withColumn("_source", F.lit(source_tag))
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"),
                r"/([0-9]{4}-[0-9]{2}-[0-9]{2})\.csv$",
                1,
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )


def _make_csv_table(spec: dict) -> None:
    @dlt.table(
        name=spec["table"],
        comment=spec["comment"],
        table_properties={"quality": "bronze", "project": "housing-assistant"},
    )
    def _bronze_table():
        return _stream_csv(spec["path"], spec["source"])


for _spec in CSV_DATASETS:
    _make_csv_table(_spec)
