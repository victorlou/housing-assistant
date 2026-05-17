# Databricks notebook source
# MAGIC %md
# MAGIC # Police recorded crime — silver layer
# MAGIC
# MAGIC Two tables:
# MAGIC
# MAGIC - `crime_victimisation_monthly` — long-format breakdown at grain
# MAGIC   `(report_month, territorial_authority, area_unit, ANZSOC subdivision)`.
# MAGIC   The escape hatch for any "show me theft vs assault" question.
# MAGIC - `crime_at_suburb_year` — annual SA22023-level rollup, allocated via
# MAGIC   the AU2013→SA22023 meshblock-weighted bridge in
# MAGIC   `housing.silver.area_unit_to_suburb` (built one-off by
# MAGIC   `local/build_area_unit_to_suburb.py`). This is what consumers join
# MAGIC   into `gold.suburb__year` — no SA2 vintage gap.
# MAGIC
# MAGIC Bronze may mix event-level rows (`victimisations = 1`) with
# MAGIC pre-aggregated groups; silver rolls up with `SUM(victimisations)`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

BRONZE = "housing.bronze"
SILVER = "housing.silver"

# COMMAND ----------


@dlt.table(
    name="crime_victimisation_monthly",
    comment=(
        "Victimisation counts by report month, area unit, and ANZSOC offence hierarchy. "
        "One row per (report_month, territorial_authority, area_unit, anzsoc_subdivision). "
        "Long-format breakdown — for SA2-level totals, prefer crime_at_suburb_year."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        report_month DATE COMMENT 'First day of the reporting month.',
        territorial_authority STRING COMMENT 'Territorial authority label from Police export.',
        area_unit STRING COMMENT 'Stats NZ area unit label from Police export.',
        anzsoc_division STRING COMMENT 'ANZSOC division label, e.g. Theft, Assault.',
        anzsoc_group STRING COMMENT 'ANZSOC group label.',
        anzsoc_subdivision STRING COMMENT 'ANZSOC subdivision label.',
        victimisation_count BIGINT COMMENT 'Sum of victimisations for this grain.',
        _ingested_at TIMESTAMP COMMENT 'Latest bronze ingest timestamp contributing to this row.'
    """,
)
@dlt.expect("has_subdivision", "anzsoc_subdivision IS NOT NULL")
@dlt.expect("positive_count", "victimisation_count > 0")
def crime_victimisation_monthly():
    bronze = spark.read.table(f"{BRONZE}.police_recorded_crime_anzsoc_victimisations")
    return bronze.groupBy(
        "report_month",
        "territorial_authority",
        "area_unit",
        "anzsoc_division",
        "anzsoc_group",
        "anzsoc_subdivision",
    ).agg(
        F.sum("victimisations").alias("victimisation_count"),
        F.max("_ingested_at").alias("_ingested_at"),
    )


# COMMAND ----------


@dlt.table(
    name="crime_at_suburb_year",
    comment=(
        "Annual recorded victimisations at NZ suburb (SA22023) grain, allocated "
        "from AU2013-keyed police data through the meshblock-weighted "
        "concordance in housing.silver.area_unit_to_suburb (derived from "
        "Stats NZ's Geographic Areas Table 2023). One row per (suburb_id, "
        "crime_year). Allocation rule: each AU's annual victimisations are "
        "distributed across overlapping SA22023s by au_share (proportion of "
        "the AU's 2023 meshblocks landing in each SA2). Rounded to int. "
        "Consumed by census_2023.gold.suburb__year to surface a single crime "
        "column alongside census demographics."
    ),
    table_properties={"quality": "silver", "project": "housing-assistant"},
    schema="""
        suburb_id STRING NOT NULL COMMENT 'Stats NZ SA22023 code. Joins to housing.gold.suburb.suburb_id directly (no vintage gap).',
        crime_year INT NOT NULL COMMENT 'Calendar year of report_month.',
        total_victimisations INT NOT NULL COMMENT 'Sum of victimisations for this (suburb, year), allocated by AU meshblock share.',
        _updated_at TIMESTAMP NOT NULL COMMENT 'When this row was last refreshed.'
    """,
)
@dlt.expect_or_drop("has_suburb_id", "suburb_id IS NOT NULL")
@dlt.expect_or_drop("positive_total", "total_victimisations > 0")
def crime_at_suburb_year():
    bridge = spark.read.table(f"{SILVER}.area_unit_to_suburb").select(
        "area_unit", "suburb_id", "au_share"
    )

    monthly = dlt.read("crime_victimisation_monthly")
    annual_au = (
        monthly.withColumn("crime_year", F.year("report_month"))
        .groupBy("crime_year", "area_unit")
        .agg(F.sum("victimisation_count").alias("au_total"))
    )

    # Inner join drops AUs with no bridge row (rare boundary edits). Allocation
    # rounds at the end so a 1k-victimisation AU split 30/70 across two SA2s
    # lands 300 + 700, not 299.7 + 700.3.
    return (
        annual_au.join(bridge, on="area_unit", how="inner")
        .withColumn("allocated", F.col("au_total") * F.col("au_share"))
        .groupBy("suburb_id", "crime_year")
        .agg(F.sum("allocated").alias("total_victimisations_raw"))
        .select(
            F.col("suburb_id"),
            F.col("crime_year").cast("int"),
            F.round("total_victimisations_raw", 0)
            .cast("int")
            .alias("total_victimisations"),
            F.current_timestamp().alias("_updated_at"),
        )
    )
