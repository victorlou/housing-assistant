# Databricks notebook source
# MAGIC %md
# MAGIC # Census 2023 bronze layer
# MAGIC
# MAGIC Auto Loader streams over GeoJSON Feature JSONL landed at
# MAGIC `/Volumes/housing/bronze/census_2023_files/<dataset>/<run_date>/*.jsonl`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# COMMAND ----------

VOLUME_ROOT = "/Volumes/housing/bronze/census_2023_files"


def _stream_census_jsonl(dataset_subdir: str, dataset_name: str):
    raw = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"{VOLUME_ROOT}/{dataset_subdir}")
    )
    return (
        raw.withColumn("_dataset", F.lit(dataset_name))
        .withColumn(
            "_run_date",
            F.regexp_extract(
                F.col("_metadata.file_path"), r"/([0-9]{4}-[0-9]{2}-[0-9]{2})/", 1
            ),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("geometry_json", F.to_json(F.col("geometry")))
        .select(
            "_dataset",
            "_run_date",
            "_ingested_at",
            "_source_file",
            "geometry_json",
            F.col("properties.SA22023_V1_00").cast("string").alias("sa2_code"),
            F.col("properties.SA22023_V1_00_NAME").cast("string").alias("sa2_name"),
            F.col("properties.SA22023_V1_00_NAME_ASCII")
            .cast("string")
            .alias("sa2_name_ascii"),
            F.coalesce(
                F.col("properties.LAND_AREA_SQ_KM"),
                F.col("properties.AREA_SQ_KM"),
            )
            .cast("double")
            .alias("land_area_sq_km"),
            F.col("properties.*"),
        )
        .drop(
            "SA22023_V1_00",
            "SA22023_V1_00_NAME",
            "SA22023_V1_00_NAME_ASCII",
            "LAND_AREA_SQ_KM",
            "AREA_SQ_KM",
        )
    )


def _make_bronze_table(table_name: str, dataset_subdir: str, dataset_name: str) -> None:
    @dlt.table(
        name=table_name,
        comment=f"Raw 2023 Census SA2 GeoJSON features ({dataset_name}) with wide VAR_* columns.",
        table_properties={
            "quality": "bronze",
            "project": "housing-assistant",
        },
    )
    def _bronze_table():
        return _stream_census_jsonl(dataset_subdir, dataset_name)


for _table, _subdir, _dataset in [
    ("census_2023_households_sa2", "census_2023_households_sa2", "households_sa2"),
    ("census_2023_dwellings_sa2", "census_2023_dwellings_sa2", "dwellings_sa2"),
    ("census_2023_individuals_sa2", "census_2023_individuals_sa2", "individuals_sa2"),
]:
    _make_bronze_table(_table, _subdir, _dataset)
