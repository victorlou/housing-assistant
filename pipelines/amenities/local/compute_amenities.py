"""
Extract NZ amenity POIs from clipped OSM PBFs and land them in
`housing.gold.amenity__h3`.

For each regional PBF already present under `../../isochrone/local/data/`
(the isochrone compute downloads + clips them — we reuse the same files):

  1. `osmium tags-filter` strips the PBF to just amenity-tagged features
     (nodes + ways + relations).
  2. `osmium export -f geojson` converts the filtered PBF to GeoJSON.
  3. Python parses the GeoJSON, categorises features into our 8 amenity
     types, computes a centroid for non-point geometries, and an H3 res-8
     cell from (lat, lon).
  4. All regions' records are concatenated, written as a single parquet,
     uploaded to `dbfs:/Volumes/housing/bronze/amenities_files/amenity_all.parquet`,
     and `CREATE OR REPLACE TABLE housing.gold.amenity__h3` materialises
     gold with `suburb_id` denormalised in via a LEFT JOIN to `gold.h3_cell`.

Prerequisites — already in place if the isochrone pipeline runs from this
machine:

- `brew install osmium-tool`
- Python venv with `pandas`, `shapely`, `h3>=4.0`, `pyarrow`,
  `databricks-sdk` (see `requirements.txt`)
- `databricks auth login --profile hackathon` once
- Regional clipped OSM PBFs at `../../isochrone/local/data/<region>-*.osm.pbf`

Run:
  source .venv/bin/activate
  python compute_amenities.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from functools import lru_cache
from pathlib import Path

import h3.api.basic_int as h3
import pandas as pd
from shapely.geometry import shape

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config
from databricks.sdk.service.sql import StatementState


# ── Config ──────────────────────────────────────────────────────────
HERE = Path(__file__).parent
# Reuse the isochrone PBFs so we don't duplicate the ~150 MB download.
OSM_DATA_DIR = (HERE / ".." / ".." / "isochrone" / "local" / "data").resolve()

DATABRICKS_PROFILE = "hackathon"
DATABRICKS_WAREHOUSE_NAME = "housing-assistant-dev"

H3_RESOLUTION = 8

BRONZE_VOLUME_TARGET = "/Volumes/housing/bronze/amenities_files/amenity_all.parquet"
GOLD_TABLE = "housing.gold.amenity__h3"

# Regions to extract from — one PBF per region. The glob picks the latest
# date-stamped clip (e.g. auckland-260515.osm.pbf).
REGIONS = [
    {"key": "auckland", "display": "Auckland", "pbf_glob": "auckland-*.osm.pbf"},
    {"key": "wellington", "display": "Wellington", "pbf_glob": "wellington-*.osm.pbf"},
    {"key": "waikato", "display": "Waikato", "pbf_glob": "waikato-*.osm.pbf"},
    {
        "key": "christchurch",
        "display": "Christchurch",
        "pbf_glob": "christchurch-*.osm.pbf",
    },
]

# Map (osm_tag_key, osm_tag_value) → our canonical amenity_type. Order is
# significant only for tags that overlap between keys — first match wins
# (e.g. both shop=supermarket and amenity=supermarket map to "supermarket").
# Deliberate column alignment; ruff would squish the contents below.
# fmt: off
AMENITY_TAG_MAP: dict[tuple[str, str], str] = {
    ("shop", "supermarket"):     "supermarket",
    ("amenity", "supermarket"):  "supermarket",
    ("amenity", "hospital"):     "hospital",
    ("amenity", "school"):       "school",
    ("amenity", "college"):      "school",
    ("amenity", "university"):   "school",
    ("amenity", "kindergarten"): "early_childhood",
    ("amenity", "childcare"):    "early_childhood",
    ("amenity", "pharmacy"):     "pharmacy",
    ("amenity", "clinic"):       "gp_clinic",
    ("amenity", "doctors"):      "gp_clinic",
    ("leisure", "park"):         "park",
    ("amenity", "library"):      "library",
}
# fmt: on

# osmium tags-filter expressions. We accept nodes, ways, and relations
# (`nwr/`) for each tag key — osmium-export then computes centroids for the
# non-point geometries.
OSMIUM_FILTERS = [
    "nwr/shop=supermarket",
    "nwr/amenity=supermarket,hospital,school,college,university,"
    "kindergarten,childcare,pharmacy,clinic,doctors,library",
    "nwr/leisure=park",
]


# ── osmium driver ───────────────────────────────────────────────────


def ensure_osmium() -> None:
    if not shutil.which("osmium"):
        sys.exit(
            "\n  osmium not on PATH. Install once:\n\n    brew install osmium-tool\n"
        )


def latest_pbf(pattern: str) -> Path | None:
    matches = sorted(OSM_DATA_DIR.glob(pattern))
    return matches[-1] if matches else None


def categorise(properties: dict) -> str | None:
    """Pick the first amenity_type whose tag pattern matches this feature."""
    for (key, value), category in AMENITY_TAG_MAP.items():
        if properties.get(key) == value:
            return category
    return None


def extract_region(region: dict) -> list[dict]:
    pbf = latest_pbf(region["pbf_glob"])
    if pbf is None:
        print(
            f"  ⚠ No PBF matching {region['pbf_glob']!r} under {OSM_DATA_DIR}. "
            "Run isochrone compute first or place the clipped PBF there."
        )
        return []

    print(f"  Filtering {pbf.name} ({pbf.stat().st_size / 1e6:,.1f} MB)")

    with tempfile.TemporaryDirectory() as tmp:
        filtered_pbf = Path(tmp) / "filtered.osm.pbf"
        geojson_out = Path(tmp) / "amenities.geojson"

        subprocess.run(
            [
                "osmium",
                "tags-filter",
                "--overwrite",
                str(pbf),
                *OSMIUM_FILTERS,
                "-o",
                str(filtered_pbf),
            ],
            check=True,
        )
        # `--add-unique-id=type_id` makes each Feature's top-level `id`
        # field the canonical "node/123" / "way/456" / "relation/789" form,
        # which is the stable OSM identifier we want in gold.
        subprocess.run(
            [
                "osmium",
                "export",
                "--overwrite",
                "-f",
                "geojson",
                "--add-unique-id=type_id",
                str(filtered_pbf),
                "-o",
                str(geojson_out),
            ],
            check=True,
        )

        # osmium-export writes a FeatureCollection. For Auckland this is a
        # few MB at most — load whole, no streaming needed.
        payload = json.loads(geojson_out.read_text(encoding="utf-8"))

    features = payload.get("features", []) or []

    records: list[dict] = []
    skipped_no_category = 0
    skipped_no_id = 0
    skipped_bad_geom = 0

    for feature in features:
        props = feature.get("properties") or {}
        category = categorise(props)
        if not category:
            skipped_no_category += 1
            continue

        try:
            geom = shape(feature["geometry"])
            centroid = geom.centroid
            if centroid.is_empty:
                skipped_bad_geom += 1
                continue
            lat, lon = float(centroid.y), float(centroid.x)
        except (KeyError, ValueError, TypeError):
            skipped_bad_geom += 1
            continue

        # osmium-export with --add-unique-id=type_id puts the stable OSM
        # identifier on the Feature itself (e.g. "node/123"). Fall back
        # to a few less-common locations for resilience.
        osm_id = feature.get("id") or props.get("@id") or props.get("osm_id")
        if osm_id is None:
            skipped_no_id += 1
            continue
        osm_id_str = str(osm_id)
        # Bare numeric ids (no slash) — assume node and prefix.
        if "/" not in osm_id_str:
            osm_id_str = f"node/{osm_id_str}"

        records.append(
            {
                "osm_id": osm_id_str,
                "amenity_type": category,
                "name": props.get("name"),
                "lat": lat,
                "lon": lon,
                "h3_cell": h3.latlng_to_cell(lat, lon, H3_RESOLUTION),
            }
        )

    print(
        f"  Extracted {len(records):,} amenities from {region['display']} ({pbf.name})"
    )

    # Self-diagnostic: if we got zero, dump a sample of the GeoJSON so the
    # next-iteration fix doesn't need guesswork. Almost always a key-name
    # mismatch between this code and osmium-export's actual output shape.
    if not records and features:
        print(
            f"  ⚠ 0 amenities extracted but GeoJSON had {len(features):,} "
            f"features. Diagnostic counters:"
        )
        print(f"     skipped_no_category = {skipped_no_category:,}")
        print(f"     skipped_no_id       = {skipped_no_id:,}")
        print(f"     skipped_bad_geom    = {skipped_bad_geom:,}")
        print("  ⚠ First feature in this region's GeoJSON (debug):")
        print(f"     {json.dumps(features[0], default=str)[:800]}")

    return records


# ── Databricks plumbing ─────────────────────────────────────────────


@lru_cache(maxsize=1)
def _workspace() -> tuple[Config, WorkspaceClient]:
    cfg = Config(profile=DATABRICKS_PROFILE)
    return cfg, WorkspaceClient(config=cfg)


@lru_cache(maxsize=1)
def _warehouse_id() -> str:
    _, workspace = _workspace()
    matches = [
        w for w in workspace.warehouses.list() if w.name == DATABRICKS_WAREHOUSE_NAME
    ]
    if not matches:
        sys.exit(f"No SQL warehouse named {DATABRICKS_WAREHOUSE_NAME!r}.")
    return matches[0].id


def _run_sql(stmt: str, wait_s: int = 50) -> list[list]:
    _, workspace = _workspace()
    response = workspace.statement_execution.execute_statement(
        warehouse_id=_warehouse_id(),
        statement=stmt,
        wait_timeout=f"{wait_s}s",
    )
    while response.status and response.status.state in (
        StatementState.PENDING,
        StatementState.RUNNING,
    ):
        time.sleep(1)
        response = workspace.statement_execution.get_statement(response.statement_id)
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


def upload_to_volume(local_path: Path, volume_path: str) -> None:
    print(f"\nUploading {local_path.name} → {volume_path}")
    _, workspace = _workspace()
    with open(local_path, "rb") as fin:
        workspace.files.upload(
            file_path=volume_path,
            contents=fin,
            overwrite=True,
        )
    print(f"  ✓ uploaded ({local_path.stat().st_size / 1e6:,.2f} MB)")


TABLE_COMMENT = (
    "NZ amenity points-of-interest extracted from OpenStreetMap and "
    "categorised into 8 buckets that matter for housing affordability "
    "(supermarket, hospital, school, early_childhood, pharmacy, gp_clinic, "
    "park, library). One row per OSM feature — note that OSM often tags a "
    "single real-world entity multiple times (e.g. a school's buildings, "
    "grounds, and field as separate features), so counts overstate "
    "real-world facility counts somewhat. JOINS: every row carries an "
    "h3_cell (joins to gold.h3_cell.h3_cell) and a denormalised "
    "suburb_id (joins straight to gold.suburb.suburb_id — saves a hop). "
    "Refresh cadence: quarterly-ish, regenerated by a local osmium pipeline "
    "(see pipelines/amenities/local/). Coverage best in Auckland, "
    "Wellington, Christchurch, Hamilton; rural NZ amenities can be sparse."
)

COLUMN_COMMENTS = {
    "osm_id": (
        "Stable OSM identifier in 'type/id' form, e.g. 'node/123456' or "
        "'way/789012'. Use to link back to the OSM entity at "
        "openstreetmap.org/{type}/{id}."
    ),
    "amenity_type": (
        "Category in our taxonomy: supermarket, hospital, school, "
        "early_childhood, pharmacy, gp_clinic, park, library. Partition "
        "column — filter on this for type-specific queries."
    ),
    "name": (
        "Human-readable name from OSM 'name' tag, e.g. 'Woolworths', "
        "'Auckland Hospital', 'Mt Albert Grammar School'. Often null for "
        "minor parks and unbranded facilities."
    ),
    "lat": "Latitude in WGS84 decimal degrees. For ways/polygons, this is the centroid.",
    "lon": "Longitude in WGS84 decimal degrees. For ways/polygons, this is the centroid.",
    "h3_cell": (
        "H3 resolution-8 cell (~0.7 km² hexagon) covering this amenity. "
        "Joins to gold.h3_cell.h3_cell and indirectly to gold.suburb."
    ),
    "suburb_id": (
        "Denormalised foreign key to gold.suburb.suburb_id (= Stats NZ SA2 "
        "code). Pre-joined here at materialisation time so consumer queries "
        "skip the gold.h3_cell hop. NULL for amenities whose H3 cell falls "
        "outside any NZ SA2 (rare — typically offshore)."
    ),
    "_updated_at": "When this row was last materialised. Roughly == when compute_amenities.py last ran.",
}


def refresh_gold_table(volume_path: str, table: str) -> None:
    """
    Replace the gold table with the latest parquet, denormalising `suburb_id`
    from gold.h3_cell at materialisation time so consumer queries don't have
    to do the join themselves.
    """
    print(f"Refreshing {table} from {volume_path}")
    _run_sql(f"""
        CREATE OR REPLACE TABLE {table}
        USING DELTA
        PARTITIONED BY (amenity_type)
        AS
        SELECT
            a.osm_id,
            a.amenity_type,
            a.name,
            a.lat,
            a.lon,
            a.h3_cell,
            c.suburb_id,
            current_timestamp() AS _updated_at
        FROM parquet.`{volume_path}` a
        LEFT JOIN housing.gold.h3_cell c
          ON c.h3_cell = a.h3_cell
    """)
    _apply_comments(table, TABLE_COMMENT, COLUMN_COMMENTS)
    [(row_count,)] = _run_sql(f"SELECT COUNT(*) FROM {table}")
    print(f"  ✓ {table} has {int(row_count):,} rows")


def _apply_comments(
    table: str, table_comment: str, column_comments: dict[str, str]
) -> None:
    """
    Apply COMMENT ON TABLE + ALTER COLUMN COMMENT for every column listed.
    Comments propagate into Genie's schema descriptions, so this is the
    primary place to put discoverable guidance for natural-language queries.
    """

    def _esc(s: str) -> str:
        return s.replace("'", "''")

    _run_sql(f"COMMENT ON TABLE {table} IS '{_esc(table_comment)}'")
    for col, comment in column_comments.items():
        _run_sql(f"ALTER TABLE {table} ALTER COLUMN {col} COMMENT '{_esc(comment)}'")


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    ensure_osmium()

    print(f"Amenity extraction · OSM resolution {H3_RESOLUTION}")
    print(f"  Reading PBFs from {OSM_DATA_DIR}")
    print()

    all_records: list[dict] = []
    for region in REGIONS:
        header = f"{region['display']} ({region['key']})"
        print(f"━━━ {header} {'━' * max(56 - len(header), 1)}")
        try:
            all_records.extend(extract_region(region))
        except SystemExit:
            raise
        except Exception as exc:
            print(f"  ✗ FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
        print()

    if not all_records:
        sys.exit("No amenities extracted across any region.")

    df = pd.DataFrame(all_records)
    print(f"━━━ Combined {'━' * 49}")
    print(f"  {len(df):,} amenities across {df['amenity_type'].nunique()} types")
    print()
    print("Per-type breakdown:")
    summary = (
        df.groupby("amenity_type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    print(summary.to_string(index=False))

    combined_path = HERE / "amenity_all.parquet"
    df.to_parquet(combined_path, index=False)
    print(f"\n  → {combined_path.name}")

    upload_to_volume(combined_path, BRONZE_VOLUME_TARGET)
    refresh_gold_table(BRONZE_VOLUME_TARGET, GOLD_TABLE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
