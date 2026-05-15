"""
Seed workspace.test.* tables with synthetic NZ housing data for agent development.

Usage:
    uv run python scripts/generate_test_data.py [--write] [--reset] [--profile NAME]
    uv run python scripts/generate_test_data.py --write --serverless
    uv run python scripts/generate_test_data.py --write --cluster-id CLUSTER_ID

Flags:
    --write       Actually write to Databricks (default: dry-run only — prints row counts)
    --reset       Drop workspace.test schema before seeding (requires --write)
    --profile     Databricks config profile (default: DATABRICKS_CONFIG_PROFILE env var, then "DEFAULT")
    --cluster-id  Databricks cluster ID for Databricks Connect (or DATABRICKS_CLUSTER_ID)
    --serverless  Use Databricks serverless compute for Databricks Connect (or DATABRICKS_SERVERLESS=true)

IMPORTANT:
    This script writes to workspace.test.* ONLY — never to production tables.
    Without --write the script runs in dry-run mode: generates data, prints what it
    would write, then exits without touching any remote resource.

Requires:
    - .env with DATABRICKS_CONFIG_PROFILE (or DATABRICKS_HOST + DATABRICKS_TOKEN)
    - For --write: provide --cluster-id, --serverless, DATABRICKS_CLUSTER_ID,
      DATABRICKS_SERVERLESS=true, or a Databricks profile with compute configured
    - databricks-connect installed: uv add databricks-connect
    - SP must have CREATE SCHEMA + CREATE TABLE on workspace.test
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

# ---------------------------------------------------------------------------
# Parse args first so --write flag controls all remote side-effects
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--write", action="store_true", help="Write data to Databricks (default: dry-run)")
parser.add_argument("--reset", action="store_true", help="Drop and recreate workspace.test before seeding")
parser.add_argument("--profile", default=None, help="Databricks config profile name")
parser.add_argument("--cluster-id", default=None, help="Databricks cluster ID for Databricks Connect")
parser.add_argument("--serverless", action="store_true", help="Use Databricks serverless compute")
args = parser.parse_args()

DRY_RUN = not args.write

# ---------------------------------------------------------------------------
# Load .env before resolving Databricks config or importing Databricks SDK
# ---------------------------------------------------------------------------
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

PROFILE = args.profile or os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
CLUSTER_ID = args.cluster_id or os.getenv("DATABRICKS_CLUSTER_ID")
SERVERLESS = args.serverless or os.getenv("DATABRICKS_SERVERLESS", "").strip().lower() in {"1", "true", "yes", "y", "on"}
TARGET_CATALOG = "workspace"
TARGET_SCHEMA = "test"
TARGET_NAMESPACE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"

if args.reset and DRY_RUN:
    parser.error("--reset requires --write")

if CLUSTER_ID and SERVERLESS:
    parser.error("choose either --cluster-id/DATABRICKS_CLUSTER_ID or --serverless/DATABRICKS_SERVERLESS, not both")

if DRY_RUN:
    print("[generate_test_data] DRY RUN — no data will be written.")
    print("[generate_test_data] Pass --write to actually seed the tables.\n")


def _utc_now() -> datetime.datetime:
    """Return a naive UTC timestamp without using deprecated utcnow()."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

# ---------------------------------------------------------------------------
# Synthetic data constants — Auckland suburbs, realistic NZ figures
# ---------------------------------------------------------------------------

SUBURBS = [
    # (suburb_name, territorial_authority, region, h3_centroid, area_km2, population_2021, median_age)
    ("Onehunga",      "Auckland City",     "Auckland Region", "8928308291bfffff", 3.2,  21000, 34.2),
    ("Mt Albert",     "Auckland City",     "Auckland Region", "892830808cbffff",  4.1,  18500, 35.8),
    ("Sandringham",   "Auckland City",     "Auckland Region", "892830808d3ffff",  2.9,  15200, 33.5),
    ("Newton",        "Auckland City",     "Auckland Region", "89283080dcbffff",  1.8,   8300, 29.4),
    ("Grey Lynn",     "Auckland City",     "Auckland Region", "89283080dd3ffff",  2.4,  12100, 32.1),
    ("Pt Chevalier",  "Auckland City",     "Auckland Region", "89283080c37ffff",  3.0,  11800, 36.2),
    ("Avondale",      "Auckland City",     "Auckland Region", "89283080c2bffff",  5.5,  19600, 34.7),
    ("Blockhouse Bay","Auckland City",     "Auckland Region", "89283080c0fffff",  6.2,  14300, 37.9),
    ("Glen Eden",     "Waitākere Ranges",  "Auckland Region", "8928308065bffff",  8.9,  22400, 36.5),
    ("Henderson",     "Waitākere Ranges",  "Auckland Region", "89283080617ffff",  7.3,  28700, 33.8),
    ("New Lynn",      "Waitākere Ranges",  "Auckland Region", "89283080637ffff",  4.6,  20100, 34.1),
    ("Papakura",      "Papakura",          "Auckland Region", "8928308521bffff",  9.4,  24200, 35.2),
    ("Takanini",      "Papakura",          "Auckland Region", "892830852cbffff",  5.8,  16400, 34.6),
    ("Manurewa",      "Manurewa-Papakura", "Auckland Region", "892830853cbffff",  7.1,  35600, 33.0),
    ("Mangere",       "Mangere-Otāhuhu",   "Auckland Region", "892830854abffff",  8.3,  31900, 32.5),
]

# H3 cells per suburb (simplified: centroid + 2-3 adjacent cells)
# In production these come from LINZ meshblocks ↔ H3 intersection
SUBURB_H3_CELLS = {name: [centroid, centroid[:-6] + "3ffff", centroid[:-6] + "7ffff"]
                   for name, _, _, centroid, *_ in SUBURBS}

# Hazard levels by suburb (rough approximation for test data)
HAZARD_CONFIG = {
    "Onehunga":      {"flood_risk": "medium", "coastal_risk": "low",    "liquefaction_risk": "medium"},
    "Mt Albert":     {"flood_risk": "low",    "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Sandringham":   {"flood_risk": "low",    "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Newton":        {"flood_risk": "low",    "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Grey Lynn":     {"flood_risk": "low",    "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Pt Chevalier":  {"flood_risk": "medium", "coastal_risk": "medium", "liquefaction_risk": "low"},
    "Avondale":      {"flood_risk": "medium", "coastal_risk": "low",    "liquefaction_risk": "medium"},
    "Blockhouse Bay":{"flood_risk": "low",    "coastal_risk": "medium", "liquefaction_risk": "low"},
    "Glen Eden":     {"flood_risk": "medium", "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Henderson":     {"flood_risk": "high",   "coastal_risk": "low",    "liquefaction_risk": "medium"},
    "New Lynn":      {"flood_risk": "high",   "coastal_risk": "low",    "liquefaction_risk": "medium"},
    "Papakura":      {"flood_risk": "medium", "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Takanini":      {"flood_risk": "high",   "coastal_risk": "low",    "liquefaction_risk": "medium"},
    "Manurewa":      {"flood_risk": "medium", "coastal_risk": "low",    "liquefaction_risk": "low"},
    "Mangere":       {"flood_risk": "medium", "coastal_risk": "medium", "liquefaction_risk": "medium"},
}

# Median weekly rent by suburb (NZD, approximate 2024 figures)
RENT_BY_SUBURB = {
    "Onehunga":      710,
    "Mt Albert":     760,
    "Sandringham":   720,
    "Newton":        850,
    "Grey Lynn":     830,
    "Pt Chevalier":  745,
    "Avondale":      680,
    "Blockhouse Bay":670,
    "Glen Eden":     620,
    "Henderson":     630,
    "New Lynn":      650,
    "Papakura":      590,
    "Takanini":      580,
    "Manurewa":      600,
    "Mangere":       610,
}

# Annual household income by suburb (NZD)
INCOME_BY_SUBURB = {
    "Onehunga":      82000,
    "Mt Albert":     92000,
    "Sandringham":   88000,
    "Newton":        110000,
    "Grey Lynn":     105000,
    "Pt Chevalier":  95000,
    "Avondale":      78000,
    "Blockhouse Bay":80000,
    "Glen Eden":     72000,
    "Henderson":     74000,
    "New Lynn":      76000,
    "Papakura":      68000,
    "Takanini":      66000,
    "Manurewa":      64000,
    "Mangere":       62000,
}

# Income decile (1=lowest, 10=highest)
INCOME_DECILE = {
    "Newton": 9, "Grey Lynn": 8, "Pt Chevalier": 7,
    "Mt Albert": 7, "Sandringham": 6, "Onehunga": 5,
    "Avondale": 5, "Blockhouse Bay": 5, "Henderson": 4,
    "New Lynn": 4, "Glen Eden": 4, "Papakura": 3,
    "Takanini": 3, "Manurewa": 2, "Mangere": 2,
}

# Schools per suburb (name, type, year_levels, EQI)
SCHOOLS = [
    ("Royal Oak Primary",        "Onehunga",      "Auckland City", "primary",     "1-6",  423, 380),
    ("Onehunga High School",     "Onehunga",      "Auckland City", "secondary",   "9-13", 471, 1180),
    ("Edendale School",          "Mt Albert",     "Auckland City", "primary",     "1-6",  405, 350),
    ("Mt Albert Grammar School", "Mt Albert",     "Auckland City", "secondary",   "9-13", 481, 2800),
    ("Sandringham School",       "Sandringham",   "Auckland City", "primary",     "1-6",  441, 290),
    ("Newton Central School",    "Newton",        "Auckland City", "primary",     "1-6",  537, 210),
    ("Grey Lynn School",         "Grey Lynn",     "Auckland City", "primary",     "1-6",  508, 260),
    ("Pt Chevalier School",      "Pt Chevalier",  "Auckland City", "primary",     "1-6",  489, 310),
    ("Avondale Primary",         "Avondale",      "Auckland City", "primary",     "1-6",  399, 420),
    ("Avondale College",         "Avondale",      "Auckland City", "secondary",   "9-13", 431, 1950),
    ("Glen Eden Intermediate",   "Glen Eden",     "Waitākere Ranges", "intermediate","7-8",410, 580),
    ("Henderson High School",    "Henderson",     "Waitākere Ranges", "secondary","9-13", 419, 1400),
    ("New Lynn School",          "New Lynn",      "Waitākere Ranges", "primary",  "1-6",  385, 360),
    ("Papakura Normal School",   "Papakura",      "Papakura",      "primary",     "1-6",  367, 290),
    ("Manurewa High School",     "Manurewa",      "Manurewa-Papakura","secondary","9-13", 358, 1600),
]

# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def _gen_suburb_rows() -> list[dict]:
    rows = []
    now = _utc_now()
    for name, ta, region, centroid, area, pop, median_age in SUBURBS:
        h3_cells = SUBURB_H3_CELLS[name]
        rows.append({
            "suburb_name": name,
            "territorial_authority": ta,
            "region": region,
            "h3_cells": h3_cells,
            "h3_centroid": centroid,
            "area_km2": area,
            "population_2021": pop,
            "median_age": median_age,
            "_updated_at": now,
        })
    return rows


def _gen_hazard_rows() -> list[dict]:
    rows = []
    now = _utc_now()
    for name, _, _, centroid, *_ in SUBURBS:
        cfg = HAZARD_CONFIG[name]
        for h3_cell in SUBURB_H3_CELLS[name]:
            rows.append({
                "h3_cell": h3_cell,
                "flood_risk": cfg["flood_risk"],
                "coastal_risk": cfg["coastal_risk"],
                "liquefaction_risk": cfg["liquefaction_risk"],
                "flood_zone_name": "100yr floodplain" if cfg["flood_risk"] in ("high", "medium") else None,
                "source": "Auckland Council GIS (synthetic test data)",
                "effective_date": datetime.date(2024, 1, 1),
                "_updated_at": now,
            })
    return rows


def _gen_isochrone_rows() -> list[dict]:
    """Synthetic isochrone: more cells reachable at higher minute buckets."""
    rows = []
    now = _utc_now()
    modes = ["transit", "drive", "walk"]
    buckets = [10, 20, 30, 45, 60]
    # Cells reachable roughly scales with bucket: use simple formula for test data
    for name, _, _, centroid, *_ in SUBURBS:
        for mode in modes:
            reachable = []
            for bucket in buckets:
                # Add progressively more cells from the full pool
                pool = [h3 for n, _, _, c, *_ in SUBURBS for h3 in SUBURB_H3_CELLS[n]]
                # Transit is slower than drive, walk is slowest
                multiplier = {"transit": 1.0, "drive": 1.8, "walk": 0.4}[mode]
                count = max(1, int(bucket * multiplier / 5))
                reachable_set = pool[:count]
                rows.append({
                    "h3_origin": centroid,
                    "mode": mode,
                    "minutes_bucket": bucket,
                    "h3_destinations": reachable_set,
                    "destination_count": len(reachable_set),
                    "_updated_at": now,
                })
    return rows


def _gen_rent_rows() -> list[dict]:
    """24 months of rent data, 4 dwelling types."""
    rows = []
    now = _utc_now()
    dwelling_types = ["all", "house", "apartment", "townhouse"]
    type_multiplier = {"all": 1.0, "house": 1.12, "apartment": 0.82, "townhouse": 0.95}

    for name, ta, *_ in SUBURBS:
        base_rent = RENT_BY_SUBURB[name]
        for month_offset in range(24):
            month = datetime.date(2023, 1, 1) + datetime.timedelta(days=30 * month_offset)
            month = month.replace(day=1)
            trend = 1 + (month_offset * 0.003)   # ~3% annual increase
            for dtype in dwelling_types:
                weekly = int(base_rent * type_multiplier[dtype] * trend)
                rows.append({
                    "suburb_name": name,
                    "territorial_authority": ta,
                    "month": month,
                    "dwelling_type": dtype,
                    "median_rent_weekly": weekly,
                    "p25_rent_weekly": int(weekly * 0.85),
                    "p75_rent_weekly": int(weekly * 1.15),
                    "sample_size": 45 + (hash(name + str(month)) % 60),
                    "_updated_at": now,
                })
    return rows


def _gen_income_rows() -> list[dict]:
    rows = []
    now = _utc_now()
    for name, ta, *_ in SUBURBS:
        base_income = INCOME_BY_SUBURB[name]
        for year, growth in [(2023, 1.0), (2024, 1.035)]:
            rows.append({
                "suburb_name": name,
                "territorial_authority": ta,
                "year": year,
                "median_household_income_annual": int(base_income * growth),
                "income_decile": INCOME_DECILE[name],
                "sample_size": 200 + (hash(name) % 300),
                "_updated_at": now,
            })
    return rows


def _gen_school_rows() -> list[dict]:
    rows = []
    now = _utc_now()
    for i, (school_name, suburb_name, ta, school_type, year_levels, eqi, roll) in enumerate(SCHOOLS, start=1):
        centroid = next((c for n, _, _, c, *_ in SUBURBS if n == suburb_name), None)
        rows.append({
            "school_id": f"SYNTH{i:04d}",
            "school_name": school_name,
            "suburb_name": suburb_name,
            "territorial_authority": ta,
            "h3_cell": centroid,
            "school_type": school_type,
            "year_levels": year_levels,
            "eqi_score": eqi,
            "roll_2023": roll,
            "latitude": None,
            "longitude": None,
            "_updated_at": now,
        })
    return rows


# ---------------------------------------------------------------------------
# Spark write helpers
# ---------------------------------------------------------------------------

def _create_databricks_session():
    """Create a Databricks Connect Spark session with explicit compute, if set."""
    from databricks.connect import DatabricksSession

    builder = DatabricksSession.builder.profile(PROFILE)
    compute_description = f"profile={PROFILE}"

    if SERVERLESS:
        builder = builder.serverless(True)
        compute_description += ", compute=serverless"
    elif CLUSTER_ID:
        builder = builder.clusterId(CLUSTER_ID)
        compute_description += f", cluster_id={CLUSTER_ID}"

    print(f"[generate_test_data] connecting to Databricks ({compute_description}) …")

    try:
        return builder.getOrCreate()
    except Exception as exc:
        if "Cluster id or serverless" in str(exc):
            raise SystemExit(
                "[generate_test_data] Databricks Connect requires compute for --write. "
                "Rerun with --serverless, rerun with --cluster-id CLUSTER_ID, set "
                "DATABRICKS_SERVERLESS=true, set DATABRICKS_CLUSTER_ID, or add "
                f"cluster_id/serverless to your Databricks profile ({PROFILE})."
            ) from None
        raise


def _write_table(spark, rows: list[dict], table: str) -> None:
    """Write rows to a Delta table, overwriting any existing data."""
    import pandas as pd
    from pyspark.sql import functions as F

    df = spark.createDataFrame(pd.DataFrame(rows))
    # Coerce list columns to ArrayType (pandas doesn't do this automatically)
    if "h3_cells" in rows[0]:
        df = df.withColumn("h3_cells", F.col("h3_cells").cast("array<string>"))
    if "h3_destinations" in rows[0]:
        df = df.withColumn("h3_destinations", F.col("h3_destinations").cast("array<string>"))

    df.write.format("delta").mode("overwrite").saveAsTable(table)
    print(f"[generate_test_data] wrote {len(rows):,} rows → {table}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    datasets = {
        "suburb":                         _gen_suburb_rows(),
        "hazard":                         _gen_hazard_rows(),
        "isochrone":                       _gen_isochrone_rows(),
        "rent__month__suburb":            _gen_rent_rows(),
        "income__year__suburb":           _gen_income_rows(),
        "school":                         _gen_school_rows(),
    }

    if DRY_RUN:
        # Dry-run mode is intentionally local-only: no Databricks connection required.
        print(f"[generate_test_data] Would write the following to {TARGET_NAMESPACE}.*:\n")
        for table, rows in datasets.items():
            print(f"  {TARGET_NAMESPACE}.{table:<40} {len(rows):>6,} rows")
        print("\n[generate_test_data] Re-run with --write to execute.")
        return

    # --- WRITE MODE: touches remote Databricks ---
    spark = _create_databricks_session()

    if args.reset:
        print(f"[generate_test_data] dropping {TARGET_NAMESPACE} schema (--reset) …")
        spark.sql(f"DROP SCHEMA IF EXISTS {TARGET_NAMESPACE} CASCADE")

    print(f"[generate_test_data] ensuring {TARGET_NAMESPACE} schema exists …")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {TARGET_NAMESPACE}")

    for table_name, rows in datasets.items():
        full_name = f"{TARGET_NAMESPACE}.{table_name}"
        _write_table(spark, rows, full_name)

    print("\n[generate_test_data] done ✓")
    print("Verify in Databricks UI: Catalog → workspace → test")


if __name__ == "__main__":
    main()
