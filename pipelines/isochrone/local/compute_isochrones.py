"""
Multi-region transit isochrone compute via r5py.

For every region in REGIONS, the script:

  1. Auto-clips a regional OSM PBF from a single NZ-wide extract using
     `osmium extract` (skipped if the clip already exists).
  2. Pulls the latest GTFS zip for that feed from the bronze volume and
     strips header-only tables that R5 refuses to parse.
  3. Builds a routing graph (OSM walking + GTFS transit), cached on disk.
  4. Computes door-to-door travel times from a handful of origin centres
     to every H3 cell hosting a stop in `housing.gold.transit_stop`, plus
     a ring of neighbouring cells (so residential cells near transit show
     up even when they don't host their own stop).

After all regions are done it concatenates everything, uploads the combined
Parquet to `dbfs:/Volumes/housing/bronze/osm_files/isochrone_all.parquet`,
and refreshes `housing.gold.isochrone` via a CREATE OR REPLACE TABLE on the
configured SQL warehouse.

Only one manual prerequisite: place a NZ-wide OSM PBF (e.g. from Geofabrik)
under data/ matching `data/new-zealand-*.osm.pbf`, and `brew install
osmium-tool` once.

All Databricks calls use the `hackathon` profile via the standard SDK +
SQL connector.

Run:
  sdk use java 21.0.5-tem
  source .venv/bin/activate
  python compute_isochrones.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import geopandas as gpd
# h3-py 4.x ships the string-based API as the default top-level module — every
# call expects hex H3 IDs like "8928308280fffff". We work in the BIGINT
# representation (matches Databricks' `h3_cell` column), so we import the
# integer-based API alias and use ints end-to-end.
import h3.api.basic_int as h3
import pandas as pd
from shapely.geometry import Point

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config
from databricks.sdk.service.sql import StatementState

from r5py import TransportNetwork, TravelTimeMatrix, TransportMode


# ── Config ──────────────────────────────────────────────────────────
HERE = Path(__file__).parent
DATA = HERE / "data"

DATABRICKS_PROFILE = "hackathon"
DATABRICKS_WAREHOUSE_NAME = "housing-assistant-dev"

DEPARTURE = datetime(2026, 5, 20, 8, 30)  # Wednesday 08:30 NZT
MAX_TRAVEL_MIN = 90
H3_RESOLUTION = 8
COMPUTATION_VERSION = "r5py-v1"

# Ring of H3 neighbours to include around each stop cell. 0 = stop cells only;
# 1 = stop cells + 6 immediate neighbours each (~3-5× more cells after dedup).
DESTINATION_RING = 1

# Where the combined Parquet lands on Databricks and which table it backs.
BRONZE_VOLUME_TARGET = (
    "/Volumes/housing/bronze/osm_files/isochrone_all.parquet"
)
GOLD_TABLE = "housing.gold.isochrone"

# Source NZ-wide OSM extract. Used as input to per-region osmium clipping.
# Place any *.osm.pbf matching this glob under data/ once.
NZ_OSM_SOURCE_GLOB = "new-zealand-*.osm.pbf"

# Region definitions. Add a new entry to bring another NZ region online.
# clip_bbox is "min_lon,min_lat,max_lon,max_lat" — same format osmium uses.
REGIONS = [
    {
        "feed_source": "auckland_transport",
        "display_name": "Auckland",
        "region_key": "auckland",
        "clip_bbox": "174.40,-37.85,175.30,-36.25",
        "gtfs_volume": "/Volumes/housing/bronze/gtfs_files/_zip/auckland_transport",
        "origins": [
            ("britomart", "Britomart", -36.84393, 174.76682),
            ("newmarket", "Newmarket", -36.87015, 174.77648),
            ("albany", "Albany", -36.72823, 174.70019),
            ("manukau", "Manukau", -36.99113, 174.88004),
            ("henderson", "Henderson", -36.87598, 174.62881),
            ("smales_farm", "Smales Farm", -36.77781, 174.74798),
            ("sylvia_park", "Sylvia Park", -36.91035, 174.84249),
        ],
    },
    {
        "feed_source": "metlink",
        "display_name": "Wellington",
        "region_key": "wellington",
        "clip_bbox": "174.65,-41.40,175.15,-40.95",
        "gtfs_volume": "/Volumes/housing/bronze/gtfs_files/_zip/metlink",
        "origins": [
            ("wellington_stn", "Wellington Station", -41.27866, 174.78035),
            ("lambton_quay", "Lambton Quay", -41.28448, 174.77685),
            ("courtenay_place", "Courtenay Place", -41.29368, 174.78173),
            ("petone", "Petone", -41.22850, 174.87410),
            ("hutt_central", "Hutt Central", -41.20961, 174.91124),
            ("porirua_stn", "Porirua Station", -41.13427, 174.84016),
        ],
    },
    {
        "feed_source": "busit",
        "display_name": "Waikato (Hamilton)",
        "region_key": "waikato",
        "clip_bbox": "175.05,-38.00,175.40,-37.55",
        "gtfs_volume": "/Volumes/housing/bronze/gtfs_files/_zip/busit",
        "origins": [
            ("hamilton_centre", "Hamilton Transport Centre", -37.78603, 175.27786),
            ("the_base", "The Base / Te Awa", -37.74916, 175.24193),
            ("chartwell", "Chartwell Mall", -37.76574, 175.27893),
            ("hamilton_east", "Hamilton East / University", -37.79213, 175.30005),
        ],
    },
    {
        "feed_source": "metroinfo",
        "display_name": "Christchurch",
        "region_key": "christchurch",
        "clip_bbox": "172.30,-43.75,172.85,-43.35",
        "gtfs_volume": "/Volumes/housing/bronze/gtfs_files/_zip/metroinfo",
        "origins": [
            ("bus_interchange", "Bus Interchange", -43.53309, 172.63659),
            ("riccarton", "Riccarton Mall", -43.53212, 172.59247),
            ("hornby", "Hornby South Mall", -43.55139, 172.55168),
            ("eastgate", "Eastgate / Linwood", -43.53388, 172.66837),
            ("northlands", "Northlands Mall", -43.49443, 172.59890),
        ],
    },
]


# ── h3 helpers ──────────────────────────────────────────────────────


def _coerce_h3_int(value) -> int:
    """
    Normalise any H3 cell representation to a Python int.

    h3-py returns Python ints, numpy ints, OR hex strings depending on
    version and API mode. `isinstance(x, int)` is False for numpy ints, and
    the now-removed `h3.str_to_int` blew up on them (it did `int(x, 16)` and
    int() refuses an explicit base on non-strings). So we branch on str
    explicitly and otherwise rely on the universal `int(...)` coercion.
    """
    if isinstance(value, str):
        return int(value, 16)
    return int(value)


def _h3_cell_int(lat: float, lon: float, res: int) -> int:
    """Return an H3 cell as a Python int. Databricks' BIGINT representation."""
    return _coerce_h3_int(h3.latlng_to_cell(lat, lon, res))


def _h3_disk_ints(cell_int: int, k: int) -> Iterable[int]:
    """Return cell + k-ring neighbours as Python ints, regardless of h3 version."""
    for c in h3.grid_disk(cell_int, k):
        yield _coerce_h3_int(c)


def _h3_centroid(cell_int: int) -> tuple[float, float]:
    """Return (lat, lon) of an H3 cell's centroid."""
    lat, lon = h3.cell_to_latlng(cell_int)
    return float(lat), float(lon)


# ── Workspace helpers ───────────────────────────────────────────────


@lru_cache(maxsize=1)
def _workspace() -> tuple[Config, WorkspaceClient]:
    """
    Resolve auth once per process. lru_cache means every caller shares the
    same Config + WorkspaceClient, so the OAuth refresh-token cache is hit
    exactly once instead of being re-resolved per call (each fresh Config
    can otherwise re-trigger the browser prompt).
    """
    cfg = Config(profile=DATABRICKS_PROFILE)
    return cfg, WorkspaceClient(config=cfg)


@lru_cache(maxsize=1)
def _warehouse_id() -> str:
    _, workspace = _workspace()
    matching = [
        w for w in workspace.warehouses.list() if w.name == DATABRICKS_WAREHOUSE_NAME
    ]
    if not matching:
        sys.exit(
            f"No SQL warehouse named {DATABRICKS_WAREHOUSE_NAME!r} found."
        )
    return matching[0].id


def _run_sql(stmt: str) -> list[list]:
    """
    Run a SQL statement against the warehouse via the SDK's statement
    execution API. Single auth path (shared with WorkspaceClient), no
    separate dbsql token resolution. Returns `data_array` rows for SELECTs,
    [] for DDL/DML.
    """
    _, workspace = _workspace()

    response = workspace.statement_execution.execute_statement(
        warehouse_id=_warehouse_id(),
        statement=stmt,
        wait_timeout="50s",  # 50s is the API max for the initial wait
    )

    # Poll if the statement is still running past the initial wait window.
    while response.status and response.status.state in (
        StatementState.PENDING,
        StatementState.RUNNING,
    ):
        time.sleep(1)
        response = workspace.statement_execution.get_statement(
            response.statement_id
        )

    state = response.status.state if response.status else None
    if state != StatementState.SUCCEEDED:
        err = (
            response.status.error.message
            if response.status and response.status.error
            else f"state={state}"
        )
        raise RuntimeError(f"SQL failed: {err}\n  Statement: {stmt.strip()}")

    if response.result and response.result.data_array:
        return response.result.data_array
    return []


# ── Inputs per region ───────────────────────────────────────────────


def ensure_osm_clip(region: dict) -> Path:
    """
    Return the regional OSM PBF for this region, clipping it from the NZ-wide
    extract on first run. Cached by filename; subsequent runs are no-ops.

    Looks for:
      data/<region_key>-*.osm.pbf  (existing clip, any date suffix)
    If absent, clips:
      data/<NZ source>.osm.pbf  ── osmium extract -b clip_bbox ──▶  data/<region_key>-<source_date>.osm.pbf
    """
    region_key = region["region_key"]
    existing = sorted(DATA.glob(f"{region_key}-*.osm.pbf"))
    if existing:
        return existing[-1]

    sources = sorted(DATA.glob(NZ_OSM_SOURCE_GLOB))
    if not sources:
        sys.exit(
            f"\n  ERROR: no NZ OSM extract found at data/{NZ_OSM_SOURCE_GLOB}.\n"
            f"  Download it once (~378 MB) from Geofabrik:\n\n"
            f"    curl -L -o data/new-zealand-260515.osm.pbf \\\n"
            f"      https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf\n"
        )
    source = sources[-1]

    if not shutil.which("osmium"):
        sys.exit(
            "\n  ERROR: osmium not on PATH. Install it once:\n\n"
            "    brew install osmium-tool\n"
        )

    # Carry the source's date suffix into the clip filename so re-downloads
    # of the NZ extract produce a freshly-named clip and trigger r5py to
    # rebuild the routing graph.
    suffix = source.name.replace("new-zealand-", "").replace(".osm.pbf", "")
    target = DATA / f"{region_key}-{suffix}.osm.pbf"

    print(
        f"  Clipping {source.name} → {target.name} (bbox {region['clip_bbox']})"
    )
    subprocess.run(
        [
            "osmium",
            "extract",
            "-b",
            region["clip_bbox"],
            str(source),
            "-o",
            str(target),
        ],
        check=True,
    )
    return target


def ensure_gtfs(volume_path: str, local_path: Path) -> Path:
    """Download the latest GTFS zip from a Databricks volume. Cached locally."""
    if local_path.exists():
        return local_path

    DATA.mkdir(parents=True, exist_ok=True)
    print(f"  Fetching {local_path.name} from {volume_path}")
    _, workspace = _workspace()

    entries = sorted(
        workspace.files.list_directory_contents(volume_path),
        key=lambda e: e.path,
    )
    zips = [e for e in entries if e.path.endswith(".zip")]
    if not zips:
        sys.exit(f"No .zip files in {volume_path}")

    latest = zips[-1]
    download = workspace.files.download(latest.path)
    with open(local_path, "wb") as fout:
        shutil.copyfileobj(download.contents, fout)
    return local_path


def clean_gtfs_zip(src_zip: Path) -> Path:
    """
    Strip header-only tables (e.g. AT's empty fare_attributes.txt) that R5
    refuses to parse. Cached as <stem>.cleaned.zip.
    """
    cleaned = src_zip.with_name(src_zip.stem + ".cleaned.zip")
    if cleaned.exists() and cleaned.stat().st_mtime >= src_zip.stat().st_mtime:
        return cleaned

    skipped: list[str] = []
    with (
        zipfile.ZipFile(src_zip) as src,
        zipfile.ZipFile(cleaned, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            data = src.read(info.filename)
            lines = [
                ln for ln in data.decode("utf-8", errors="ignore").splitlines()
                if ln.strip()
            ]
            if len(lines) <= 1:
                skipped.append(info.filename)
                continue
            dst.writestr(info, data)

    if skipped:
        print(f"  Stripped header-only tables: {', '.join(skipped)}")
    return cleaned


def fetch_destinations(feed_source: str, ring: int) -> gpd.GeoDataFrame:
    """
    Build the destination grid: every distinct H3 cell hosting a stop in the
    given feed PLUS its `ring`-step H3 neighbours, deduplicated. Each cell's
    coordinate is its canonical H3 centroid (not a sampled stop position),
    so cells without stops are also routable.
    """
    rows = _run_sql(f"""
        SELECT DISTINCT h3_cell
        FROM housing.gold.transit_stop
        WHERE feed_source = '{feed_source}'
    """)
    # statement_execution returns BIGINT values as decimal strings.
    stop_cells = [int(r[0]) for r in rows]
    print(f"  Stops: {len(stop_cells):,} distinct H3 cells")

    expanded: set[int] = set()
    for c in stop_cells:
        expanded.update(_h3_disk_ints(c, ring))
    print(f"  Destinations after ring-{ring} expansion: {len(expanded):,}")

    rows = []
    for cell in sorted(expanded):
        lat, lon = _h3_centroid(cell)
        rows.append({"id": cell, "lat": lat, "lon": lon})
    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.lon, df.lat),
        crs="EPSG:4326",
    )[["id", "geometry"]]


def origins_gdf(origin_list: list[tuple]) -> gpd.GeoDataFrame:
    rows = [
        {
            "id": cid,
            "name": name,
            "lat": lat,
            "lon": lon,
            "h3_cell": _h3_cell_int(lat, lon, H3_RESOLUTION),
        }
        for cid, name, lat, lon in origin_list
    ]
    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.lon, df.lat),
        crs="EPSG:4326",
    )


# ── Per-region compute ──────────────────────────────────────────────


def compute_region(region: dict) -> pd.DataFrame:
    feed_source = region["feed_source"]

    osm_pbf = ensure_osm_clip(region)
    gtfs_zip = clean_gtfs_zip(
        ensure_gtfs(
            volume_path=region["gtfs_volume"],
            local_path=DATA / f"{feed_source}_gtfs.zip",
        )
    )
    print(f"  OSM:  {osm_pbf.name} ({osm_pbf.stat().st_size / 1e6:,.1f} MB)")
    print(f"  GTFS: {gtfs_zip.name} ({gtfs_zip.stat().st_size / 1e6:,.1f} MB)")

    destinations = fetch_destinations(feed_source, DESTINATION_RING)
    origins = origins_gdf(region["origins"])
    print(f"  Origins: {len(origins)}  ·  Destinations: {len(destinations):,}")

    print("  Building routing network...")
    network = TransportNetwork(osm_pbf=str(osm_pbf), gtfs=[str(gtfs_zip)])

    print("  Computing travel-time matrix...")
    matrix = TravelTimeMatrix(
        transport_network=network,
        origins=origins,
        destinations=destinations,
        departure=DEPARTURE,
        transport_modes=[TransportMode.TRANSIT, TransportMode.WALK],
        max_time=timedelta(minutes=MAX_TRAVEL_MIN),
    )
    if "travel_time" in matrix.columns:
        matrix = matrix.rename(columns={"travel_time": "travel_minutes"})

    origin_h3_by_id = dict(zip(origins["id"], origins["h3_cell"]))
    rows = matrix.assign(
        origin_h3=matrix["from_id"].map(origin_h3_by_id),
        destination_h3=matrix["to_id"],
        mode="transit",
        feed_source=feed_source,
        departure_time=DEPARTURE.strftime("%H:%M"),
        service_date=DEPARTURE.date(),
        computed_at=pd.Timestamp.utcnow(),
        computation_version=COMPUTATION_VERSION,
    )
    # Drop unreached destinations, then hard-cap to MAX_TRAVEL_MIN before
    # bucketing. r5py's `max_time` only caps the transit search; access/egress
    # walking can push the reported total above it (we saw values up to ~115
    # min for a 90-min cap). Filter pre-bucket so the gold table honours the
    # cap we advertise.
    rows = rows.dropna(subset=["travel_minutes"]).copy()
    rows = rows[rows["travel_minutes"] <= MAX_TRAVEL_MIN].copy()
    rows["travel_minutes"] = (rows["travel_minutes"] / 5).round().astype(int) * 5

    return rows[
        [
            "origin_h3",
            "destination_h3",
            "mode",
            "travel_minutes",
            "feed_source",
            "departure_time",
            "service_date",
            "computed_at",
            "computation_version",
        ]
    ]


# ── Publish to Databricks ───────────────────────────────────────────


def upload_to_volume(local_path: Path, volume_path: str) -> None:
    """Upload the combined Parquet to the bronze volume, overwriting in place."""
    print(f"\nUploading {local_path.name} → {volume_path}")
    _, workspace = _workspace()
    with open(local_path, "rb") as fin:
        workspace.files.upload(
            file_path=volume_path,
            contents=fin,
            overwrite=True,
        )
    print(f"  ✓ uploaded ({local_path.stat().st_size / 1e6:,.2f} MB)")


def refresh_gold_table(volume_path: str, table: str) -> None:
    """
    Replace `housing.gold.isochrone` with the contents of the uploaded
    Parquet. CREATE OR REPLACE preserves UC grants on the table.
    """
    print(f"Refreshing {table} from {volume_path}")
    _run_sql(f"""
        CREATE OR REPLACE TABLE {table}
        USING DELTA
        PARTITIONED BY (mode, feed_source)
        AS SELECT * FROM parquet.`{volume_path}`
    """)
    [(row_count,)] = _run_sql(f"SELECT COUNT(*) FROM {table}")
    print(f"  ✓ {table} has {int(row_count):,} rows")


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    print(f"Multi-region isochrone compute · departure {DEPARTURE.isoformat()}")
    print(f"  H3 resolution: {H3_RESOLUTION}  ·  ring: {DESTINATION_RING}")
    print(f"  Cap: {MAX_TRAVEL_MIN} min  ·  Modes: transit + walk")
    print()

    all_results: list[pd.DataFrame] = []
    for region in REGIONS:
        feed = region["feed_source"]
        header = f"{region['display_name']} ({feed})"
        print(f"━━━ {header} {'━' * (max(56 - len(header), 1))}")
        try:
            df = compute_region(region)
            out = HERE / f"isochrone_{feed}.parquet"
            df.to_parquet(out, index=False)
            print(f"  ✓ {len(df):,} rows → {out.name}")
            all_results.append(df)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"  ✗ FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            continue
        print()

    if not all_results:
        sys.exit("No regions succeeded — nothing to write.")

    combined = pd.concat(all_results, ignore_index=True)
    combined_path = HERE / "isochrone_all.parquet"
    combined.to_parquet(combined_path, index=False)

    print(f"━━━ Combined {'━' * 49}")
    print(f"  {len(combined):,} rows across {len(all_results)} region(s)")
    print(f"  → {combined_path.name}")

    print("\nPer-region summary:")
    summary = (
        combined.groupby("feed_source")["travel_minutes"]
        .agg(reachable_pairs="count", min_min="min", max_min="max")
        .sort_values("reachable_pairs", ascending=False)
    )
    print(summary.to_string())

    upload_to_volume(combined_path, BRONZE_VOLUME_TARGET)
    refresh_gold_table(BRONZE_VOLUME_TARGET, GOLD_TABLE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
