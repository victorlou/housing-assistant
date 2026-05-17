# Databricks notebook source
# MAGIC %md
# MAGIC # prices bronze layer
# MAGIC
# MAGIC One streaming DLT table per dataset under `prices_files/`:
# MAGIC
# MAGIC - `prices_rbnz_hpi_raw` — Auto Loader over the long-format CSVs written
# MAGIC   by `fetch.py` after parsing the RBNZ M10 Housing XLSX. One row per
# MAGIC   (region, quarter).
# MAGIC
# MAGIC Future datasets (Stats NZ property transfers, REINZ TA-level when we
# MAGIC have it) land here as additional entries in `CSV_DATASETS` without
# MAGIC changing the notebook body.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

PRICES_VOLUME_ROOT = "/Volumes/housing/bronze/prices_files"

CSV_DATASETS = [
    {
        "table": "prices_rbnz_hpi_raw",
        "source": "rbnz",
        "path": f"{PRICES_VOLUME_ROOT}/rbnz_hpi",
        "comment": (
            "Raw RBNZ M10 Housing HPI in long format (one row per "
            "region-quarter pair). Parsed from the original XLSX by fetch.py."
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
