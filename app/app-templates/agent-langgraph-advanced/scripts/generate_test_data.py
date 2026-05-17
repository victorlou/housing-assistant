"""
Seed workspace.test.* tables with synthetic NZ housing data for agent development.

Mirrors the real housing.gold.* schemas documented in
docs/lakehouse-gold-schema.md so tool code can switch between
workspace.test.* and housing.gold.* via one env-var change
(HOUSING_CATALOG, HOUSING_SCHEMA).

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
    - h3-py installed: uv add h3       (computes real H3 res-8 cells from lat/lon
                                          so they match h3_longlatash3() in Spark)
    - SP must have CREATE SCHEMA + CREATE TABLE on workspace.test
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CLI parsing first so --write controls all remote side-effects
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--write", action="store_true", help="Write data to Databricks (default: dry-run)")
parser.add_argument("--reset", action="store_true", help="Drop and recreate workspace.test before seeding")
parser.add_argument("--profile", default=None, help="Databricks config profile name")
parser.add_argument("--cluster-id", default=None, help="Databricks cluster ID for Databricks Connect")
parser.add_argument("--serverless", action="store_true", help="Use Databricks serverless compute")
args = parser.parse_args()

DRY_RUN = not args.write

# ---------------------------------------------------------------------------
# Load .env before resolving Databricks config
# ---------------------------------------------------------------------------
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

PROFILE = args.profile or os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
CLUSTER_ID = args.cluster_id or os.getenv("DATABRICKS_CLUSTER_ID")
SERVERLESS = args.serverless or os.getenv("DATABRICKS_SERVERLESS", "").strip().lower() in {
    "1", "true", "yes", "y", "on",
}
TARGET_CATALOG = "workspace"
TARGET_SCHEMA = "test"
TARGET_NAMESPACE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"

if args.reset and DRY_RUN:
    parser.error("--reset requires --write")

if CLUSTER_ID and SERVERLESS:
    parser.error("choose either --cluster-id/DATABRICKS_CLUSTER_ID or --serverless/DATABRICKS_SERVERLESS, not both")

# h3 is required for both dry-run and write modes so test data uses the same
# H3 cells the production `h3_longlatash3()` SQL function would compute.
try:
    import h3.api.basic_int as h3
except ImportError:
    sys.exit(
        "[generate_test_data] h3 required. Install with: uv add h3\n"
        "  h3-py 4.x ships the int-based API at h3.api.basic_int."
    )

if DRY_RUN:
    print("[generate_test_data] DRY RUN — no data will be written.")
    print("[generate_test_data] Pass --write to actually seed the tables.\n")


def _utc_now() -> datetime.datetime:
    """Naive UTC timestamp. Uses `datetime.timezone.utc` for Python 3.10 compat."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _h3_cell(lat: float, lon: float) -> int:
    """Real H3 res-8 cell as int — matches Databricks `h3_longlatash3(lon, lat, 8)`."""
    return int(h3.latlng_to_cell(lat, lon, 8))


# ---------------------------------------------------------------------------
# Synthetic data: 10 Auckland SA2s + 4 TAs + national region.
# Coords are approximate suburb centroids — accurate enough for the SQL
# function to produce a stable, reasonable H3 cell for testing.
# ---------------------------------------------------------------------------

# (suburb_id, suburb_name, territorial_authority, region, lat, lon)
SUBURBS: list[tuple[str, str, str, str, float, float]] = [
    ("134800", "Onehunga North East",      "Auckland", "Auckland Region", -36.9197, 174.7898),
    ("134700", "Onehunga North West",      "Auckland", "Auckland Region", -36.9244, 174.7795),
    ("133400", "Mt Eden South",            "Auckland", "Auckland Region", -36.8800, 174.7565),
    ("132700", "Newmarket",                "Auckland", "Auckland Region", -36.8703, 174.7765),
    ("131700", "Ponsonby West",            "Auckland", "Auckland Region", -36.8550, 174.7350),
    ("136200", "Mt Albert South",          "Auckland", "Auckland Region", -36.8950, 174.7100),
    ("135700", "Sandringham North",        "Auckland", "Auckland Region", -36.8920, 174.7300),
    ("141900", "New Lynn Central",         "Waitākere Ranges", "Auckland Region", -36.9115, 174.6850),
    ("141100", "Henderson Central",        "Waitākere Ranges", "Auckland Region", -36.8770, 174.6280),
    ("163200", "Papakura Central",         "Papakura", "Auckland Region", -37.0625, 174.9430),
]

# Headline NZ TAs we want represented in ta__month / ta__quarter.
# "New Zealand" is the synthetic rollup row HUD ships.
TAS = ["Auckland", "Waitākere Ranges", "Papakura", "Wellington City", "Christchurch City", "New Zealand"]

# Per-suburb baseline census + crime numbers (loosely calibrated).
SUBURB_STATS = {
    "134800": dict(pop=2664, age=33.4, income=104400, hh=900,  rent=620, crowded_pct=0.082, crime=308),
    "134700": dict(pop=2424, age=37.1, income= 96200, hh=861,  rent=580, crowded_pct=0.070, crime=261),
    "133400": dict(pop=3171, age=36.8, income=125000, hh=1206, rent=720, crowded_pct=0.061, crime=180),
    "132700": dict(pop=2613, age=34.9, income=104700, hh=1080, rent=750, crowded_pct=0.137, crime=152),
    "131700": dict(pop=2154, age=35.6, income=177200, hh=894,  rent=545, crowded_pct=0.043, crime=192),
    "136200": dict(pop=2727, age=36.2, income=105400, hh=1110, rent=680, crowded_pct=0.074, crime=110),
    "135700": dict(pop=3441, age=34.5, income=132300, hh=1395, rent=700, crowded_pct=0.083, crime=128),
    "141900": dict(pop=3294, age=35.0, income= 86400, hh=1257, rent=590, crowded_pct=0.119, crime=1295),
    "141100": dict(pop=2802, age=34.1, income= 73900, hh=1029, rent=550, crowded_pct=0.155, crime=178),
    "163200": dict(pop=3684, age=33.7, income= 72200, hh=1326, rent=560, crowded_pct=0.117, crime=955),
}

# Eight amenity types matching the real gold.amenity__h3 taxonomy.
AMENITY_TYPES = ["supermarket", "school", "early_childhood", "hospital", "pharmacy", "gp_clinic", "park", "library"]


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def _gen_suburb_rows() -> list[dict]:
    now = _utc_now()
    rows = []
    for suburb_id, name, ta, region, lat, lon in SUBURBS:
        stats = SUBURB_STATS[suburb_id]
        rows.append(
            {
                "suburb_id": suburb_id,
                "suburb_name": name,
                "territorial_authority": ta,
                "region": region,
                "centroid_h3": _h3_cell(lat, lon),
                "land_area_km2": 2.5 + (hash(suburb_id) % 100) / 25.0,  # 2.5..6.5
                "population_2023": stats["pop"],
                "median_age_2023": stats["age"],
                "geometry": None,  # WKB not synthesised — agent tools don't query it
                "_updated_at": now,
            }
        )
    return rows


def _gen_h3_cell_rows() -> list[dict]:
    """For each suburb, the centroid cell + its 6 ring-1 neighbours."""
    now = _utc_now()
    rows = []
    seen: set[int] = set()
    for suburb_id, _, _, _, lat, lon in SUBURBS:
        centroid = _h3_cell(lat, lon)
        ring = h3.grid_disk(centroid, 1)  # centroid + 6 neighbours
        for cell in ring:
            cell_int = int(cell)
            if cell_int in seen:
                continue
            seen.add(cell_int)
            rows.append({"h3_cell": cell_int, "suburb_id": suburb_id, "_updated_at": now})
    return rows


def _gen_suburb_year_rows() -> list[dict]:
    now = _utc_now()
    rows = []
    for suburb_id, name, *_ in SUBURBS:
        s = SUBURB_STATS[suburb_id]
        rows.append(
            {
                "census_year": 2023,
                "suburb_id": suburb_id,
                "suburb_name": name,
                "median_household_income": float(s["income"]),
                "households_total": s["hh"],
                "households_income_stated": int(s["hh"] * 0.85),
                "tenure_owned": int(s["hh"] * 0.55),
                "tenure_not_owned": int(s["hh"] * 0.40),
                "tenure_total_stated": int(s["hh"] * 0.95),
                "owner_occupier_pct": 0.55 / 0.95,
                "median_weekly_rent": float(s["rent"]),
                "renting_households_total": int(s["hh"] * 0.40),
                "renting_households_stated": int(s["hh"] * 0.38),
                "households_crowded": int(s["hh"] * s["crowded_pct"]),
                "households_crowding_total_stated": int(s["hh"] * 0.90),
                "percent_crowded": s["crowded_pct"],
                "dwellings_always_damp": int(s["hh"] * 0.05),
                "dwellings_sometimes_damp": int(s["hh"] * 0.15),
                "dwellings_damp_total_stated": int(s["hh"] * 0.85),
                "dwellings_mould_a4_always": int(s["hh"] * 0.04),
                "dwellings_mould_total_stated": int(s["hh"] * 0.85),
                "dwellings_no_heating": int(s["hh"] * 0.06),
                "dwellings_mean_rooms": 4.5 + (hash(suburb_id) % 10) / 10.0,
                "population_total": s["pop"],
                "median_age": s["age"],
                "total_victimisations_2023": s["crime"],
                "_updated_at": now,
            }
        )
    return rows


def _gen_ta_month_rows() -> list[dict]:
    """24 months × 6 TAs. Sparse Sales/Bonds columns; MSD populated every month."""
    now = _utc_now()
    rows = []
    base = datetime.date(2024, 1, 1)
    for ta in TAS:
        hpi_base = {"Auckland": 1320, "Wellington City": 1180, "Christchurch City": 980,
                    "Waitākere Ranges": 1290, "Papakura": 1050}.get(ta, 1200)
        rent_base = {"Auckland": 670, "Wellington City": 650, "Christchurch City": 540,
                     "Waitākere Ranges": 600, "Papakura": 590}.get(ta, 600)
        register_base = {"Auckland": 8400, "Wellington City": 920, "Christchurch City": 540,
                         "Waitākere Ranges": 1400, "Papakura": 380}.get(ta, 12000)
        for m in range(24):
            month_date = datetime.date(base.year + (base.month - 1 + m) // 12,
                                       (base.month - 1 + m) % 12 + 1, 1)
            is_quarterly_snapshot = month_date.month in (3, 6, 9, 12)
            trend = 1 + m * 0.002
            rows.append(
                {
                    "ta_name": ta,
                    "ta_code": f"0{TAS.index(ta):02d}",
                    "date": month_date,
                    "current_hpi": (hpi_base * trend) if is_quarterly_snapshot else None,
                    "current_annual_median_sales_nzd": (1_000_000 * trend) if is_quarterly_snapshot else None,
                    "current_annual_lower_q_sales_nzd": (780_000 * trend) if is_quarterly_snapshot else None,
                    "annual_sales_volume": int(2400 * trend) if is_quarterly_snapshot else None,
                    "median_rent_nzd": (rent_base * trend) if is_quarterly_snapshot else None,
                    "average_rent_nzd": (rent_base * 1.05 * trend) if is_quarterly_snapshot else None,
                    "lower_quartile_rent_nzd": (rent_base * 0.82 * trend) if is_quarterly_snapshot else None,
                    "housing_register": int(register_base * trend),
                    "housing_register_per_10k_pop": round(register_base * trend / 35.0, 1),
                    "_updated_at": now,
                }
            )
    return rows


def _gen_ta_quarter_rows() -> list[dict]:
    """8 quarters × 6 TAs. Carries the four affordability indices."""
    now = _utc_now()
    rows = []
    quarters: list[tuple[datetime.date, str]] = []
    for year in (2023, 2024):
        for q in (1, 2, 3, 4):
            quarters.append((datetime.date(year, (q - 1) * 3 + 1, 1), f"{year}-Q{q}"))
    for ta in TAS:
        dep_base = {"Auckland": 1.95, "Wellington City": 1.55, "Christchurch City": 1.20,
                    "Waitākere Ranges": 1.80, "Papakura": 1.40}.get(ta, 1.50)
        for (qdate, qlabel) in quarters:
            t = (qdate.year - 2023) + (qdate.month - 1) / 12.0
            trend = 1 + t * 0.04
            rows.append(
                {
                    "ta_name": ta,
                    "ta_code": f"0{TAS.index(ta):02d}",
                    "quarter": qdate,
                    "quarter_label": qlabel,
                    "deposit_affordability_index": round(dep_base * trend, 3),
                    "mortgage_affordability_index": round(dep_base * 0.85 * trend, 3),
                    "rent_affordability_index": round(dep_base * 0.70 * trend, 3),
                    "median_to_median_ratio": round(dep_base * 4.5 * trend, 2),
                    "_updated_at": now,
                }
            )
    return rows


def _gen_region_quarter_rows() -> list[dict]:
    """RBNZ M10 is country-aggregate today: single 'New Zealand' region."""
    now = _utc_now()
    rows = []
    quarters: list[tuple[datetime.date, str]] = []
    for year in (2023, 2024):
        for q in (1, 2, 3, 4):
            quarters.append((datetime.date(year, (q - 1) * 3 + 1, 1), f"{year}-Q{q}"))
    for i, (qdate, qlabel) in enumerate(quarters):
        hpi = 1250 + i * 12
        yoy = None
        if i >= 4:
            prev = 1250 + (i - 4) * 12
            yoy = round((hpi - prev) / prev * 100, 2)
        rows.append(
            {
                "region": "New Zealand",
                "quarter": qdate,
                "quarter_label": qlabel,
                "hpi": float(hpi),
                "hpi_yoy_pct": yoy,
                "sales_count": 18000 + i * 200,
                "total_value_nzdm": round(1_700_000.0 + i * 12_000.0, 1),
                "residential_investment_nzdm_real": round(4_200.0 + i * 35.0, 1),
                "_updated_at": now,
            }
        )
    return rows


def _gen_isochrone_rows() -> list[dict]:
    """
    Synthetic symmetric travel-time matrix over the test suburb cells.
    Self-reach = 0 min; same TA = 15; cross-TA = 25.
    Matches the real gold.isochrone schema (one row per cell pair).
    """
    now = _utc_now()
    cells = [(suburb_id, ta, _h3_cell(lat, lon))
             for suburb_id, _, ta, _, lat, lon in SUBURBS]
    rows = []
    for origin_sid, origin_ta, origin_cell in cells:
        for dest_sid, dest_ta, dest_cell in cells:
            if origin_cell == dest_cell:
                minutes = 0
            elif origin_ta == dest_ta:
                minutes = 15
            else:
                minutes = 25
            rows.append(
                {
                    "origin_h3": origin_cell,
                    "destination_h3": dest_cell,
                    "mode": "transit",
                    "travel_minutes": minutes,
                    "feed_source": "auckland_transport",
                    "departure_time": "08:30",
                    "service_date": datetime.date(2026, 5, 20),
                    "computed_at": now,
                    "computation_version": "r5py-v2-test",
                }
            )
    return rows


def _gen_amenity_h3_rows() -> list[dict]:
    """Three amenities per suburb across rotating types."""
    now = _utc_now()
    rows = []
    counter = 0
    for suburb_id, name, _, _, lat, lon in SUBURBS:
        cell = _h3_cell(lat, lon)
        for offset in range(3):
            atype = AMENITY_TYPES[(counter + offset) % len(AMENITY_TYPES)]
            counter += 1
            rows.append(
                {
                    "osm_id": f"node/{1000 + counter}",
                    "amenity_type": atype,
                    "name": f"{name} {atype.replace('_', ' ').title()} {offset + 1}",
                    "lat": lat + offset * 0.0008,
                    "lon": lon + offset * 0.0008,
                    "h3_cell": cell,
                    "suburb_id": suburb_id,
                    "_updated_at": now,
                }
            )
    return rows


def _gen_hazard_rows() -> list[dict]:
    """
    One hazard row per H3 cell in h3_cell_rows. Most cells are clean; a couple
    of Onehunga / Henderson / New Lynn cells flagged as flood-prone for testing
    (those suburbs are known flood-affected in reality too).
    """
    now = _utc_now()
    seen: set[int] = set()
    cell_suburb: dict[int, str] = {}
    for suburb_id, _, _, _, lat, lon in SUBURBS:
        centroid = _h3_cell(lat, lon)
        for cell in h3.grid_disk(centroid, 1):
            cell_int = int(cell)
            if cell_int in seen:
                continue
            seen.add(cell_int)
            cell_suburb[cell_int] = suburb_id

    flood_prone_suburbs = {"134700", "134800", "141100", "141900"}
    coastal_suburbs = {"134700", "134800"}  # Onehunga sits on Manukau Harbour

    rows = []
    for cell_int, suburb_id in cell_suburb.items():
        in_flood = suburb_id in flood_prone_suburbs
        in_coastal = suburb_id in coastal_suburbs
        sources = []
        if in_flood:
            sources.append("auckland_council_flood_plain")
        if in_coastal:
            sources.append("auckland_coastal_inundation_1_aep")
        rows.append(
            {
                "h3_cell": cell_int,
                "in_flood_plain": in_flood,
                "in_flood_prone_area": in_flood,
                "in_flood_sensitive_area": in_flood,
                "in_coastal_inundation_1_aep": in_coastal,
                "in_coastal_inundation_100yr": in_coastal,
                "in_regional_flood_zone": False,
                "hazard_sources": sources,
                "max_rainfall_event": 100 if in_flood else None,
                "sample_report_url": None,
                "_updated_at": now,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Spark write helpers
# ---------------------------------------------------------------------------

# Columns whose pandas dtype needs explicit casting to Spark ArrayType when written.
_ARRAY_COLUMNS = {"hazard_sources": "array<string>"}


def _create_databricks_session():
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
                "Rerun with --serverless, --cluster-id CLUSTER_ID, set "
                "DATABRICKS_SERVERLESS=true, set DATABRICKS_CLUSTER_ID, or add "
                f"cluster_id/serverless to your Databricks profile ({PROFILE})."
            ) from None
        raise


def _write_table(spark, rows: list[dict], table: str) -> None:
    import pandas as pd
    from pyspark.sql import functions as F

    df = spark.createDataFrame(pd.DataFrame(rows))
    # Pandas can't infer ArrayType for list columns — coerce explicitly.
    for col, dtype in _ARRAY_COLUMNS.items():
        if col in rows[0]:
            df = df.withColumn(col, F.col(col).cast(dtype))

    df.write.format("delta").mode("overwrite").saveAsTable(table)
    print(f"[generate_test_data] wrote {len(rows):,} rows → {table}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    datasets = {
        "suburb":          _gen_suburb_rows(),
        "h3_cell":         _gen_h3_cell_rows(),
        "suburb__year":    _gen_suburb_year_rows(),
        "ta__month":       _gen_ta_month_rows(),
        "ta__quarter":     _gen_ta_quarter_rows(),
        "region__quarter": _gen_region_quarter_rows(),
        "isochrone":       _gen_isochrone_rows(),
        "amenity__h3":     _gen_amenity_h3_rows(),
        "hazard":          _gen_hazard_rows(),
    }

    if DRY_RUN:
        print(f"[generate_test_data] Would write the following to {TARGET_NAMESPACE}.*:\n")
        for table, rows in datasets.items():
            print(f"  {TARGET_NAMESPACE}.{table:<20} {len(rows):>6,} rows")
        print("\n[generate_test_data] Re-run with --write to execute.")
        return

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
