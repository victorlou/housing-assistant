"""
One-off build of `housing.silver.area_unit_to_suburb` from two Stats NZ sources.

Police recorded-crime data is keyed by Area Unit 2013 (a retired Stats NZ
geography) and doesn't carry an area-unit *code* in the CSV, only the name.
Our other suburb-level data (`gold.suburb`, `gold.suburb__year`, etc.) is
keyed by SA2 2023 codes. To make crime joinable at suburb grain we need a
bridge.

Building it end-to-end on Databricks would be a full pipeline. But the
underlying source files are *static* — they're 2013 Census artifacts plus
the AU2013 polygon attribute table, neither of which will ever change.
So this is a one-off local build that writes the silver table directly via
the SQL warehouse: parquet → bronze volume → CREATE OR REPLACE TABLE.

## Sources

1. **Concordance crosstab** — Stats NZ workbook
   `2013-census-population-counts-by-sa22018-and-au2013.xlsx`. A 2,179 ×
   1,919 matrix: rows are SA2 2018 codes, columns are AU2013 codes, cells
   are 2013 Census usual residents at the (SA2, AU) intersection.
   Population > 0 SA2s only.

2. **AU2013 attribute table** — `area-unit-2013.csv` inside the zipped
   `statsnz-area-unit-2013-CSV.zip` from Stats NZ DataFinder layer 25743.
   2,004 (code, name, area) tuples plus polygon WKT (we drop WKT — only
   the name↔code dim is needed).

Both files were uploaded once and live in the bronze volume. They don't
change between runs.

## Output

`housing.silver.area_unit_to_suburb` — long-format bridge with one row per
non-zero (au_code, sa2_code) overlap. About 4k rows total.

| column          | type   | description                                                            |
|-----------------|--------|------------------------------------------------------------------------|
| area_unit       | STRING | AU2013 name. Matches `silver.crime_victimisation_monthly.area_unit`.   |
| au_code_2013    | STRING | 6-digit Stats NZ AU2013 code.                                          |
| suburb_id       | STRING | 6-digit Stats NZ SA2 2018 code. ~94% overlap with SA2 2023.            |
| population_2013 | INT    | 2013 Census usual residents at this (au, sa2) overlap.                 |
| au_share        | DOUBLE | population / sum-over-au. Allocation weight for crime → SA2.           |
| sa2_share       | DOUBLE | population / sum-over-sa2.                                             |

## Run

    sdk use java 21.0.5-tem   # not strictly needed; just for env consistency
    python pipelines/police_recorded_crime/local/build_area_unit_to_suburb.py \\
        --crosstab path/to/2013-census-population-counts-by-sa22018-and-au2013.xlsx \\
        --au-zip   path/to/statsnz-area-unit-2013-CSV.zip

Defaults assume the source files sit next to this script (download them to
`pipelines/police_recorded_crime/local/data/` for repeatable runs).

Add `--dry-run` to skip the UC write and just print row counts.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl required. Install via: pip install openpyxl")

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas + pyarrow required. Install via: pip install pandas pyarrow")

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config
    from databricks.sdk.service.sql import StatementState
except ImportError:
    sys.exit("databricks-sdk required. Install via: pip install databricks-sdk")


# ── Databricks config (mirror compute_isochrones.py) ────────────────────
DATABRICKS_PROFILE = "hackathon"
DATABRICKS_WAREHOUSE_NAME = "housing-assistant-dev"

# Where the parquet lands on bronze and which silver table it backs.
BRONZE_VOLUME_TARGET = (
    "/Volumes/housing/bronze/crime_files/concordance/area_unit_to_suburb.parquet"
)
SILVER_TABLE = "housing.silver.area_unit_to_suburb"

TABLE_COMMENT = (
    "AU2013 → SA2 2018 population-weighted concordance, with the canonical "
    "AU2013 name attached for joins to police_recorded_crime silver. Built "
    "one-off from two static Stats NZ files (2013 Census crosstab + AU2013 "
    "attribute table) by pipelines/police_recorded_crime/local/"
    "build_area_unit_to_suburb.py. Around 4k rows — one per non-zero "
    "(AU, SA2) overlap. SA2 2023 added 135 new SA2s vs 2018; those will not "
    "appear in this bridge and downstream rows for those SA2s receive NULL. "
    "JOINS: area_unit = silver.crime_victimisation_monthly.area_unit (after "
    "the trailing-dot strip applied in bronze); suburb_id = gold.suburb.suburb_id."
)

COLUMN_COMMENTS = {
    "area_unit": (
        "Stats NZ AU2013 name. Matches "
        "`silver.crime_victimisation_monthly.area_unit` exactly after the "
        "trailing-dot strip in police bronze."
    ),
    "au_code_2013": "6-digit Stats NZ AU2013 code.",
    "suburb_id": (
        "6-digit Stats NZ SA2 2018 code. Joins to gold.suburb.suburb_id with "
        "~94% coverage (135 SA2s added in the 2023 vintage have no bridge row)."
    ),
    "population_2013": (
        "2013 Census usually-resident population at the (au_code, suburb_id) "
        "overlap. Non-zero by construction (zeros dropped during the build)."
    ),
    "au_share": (
        "population_2013 / SUM(population_2013) OVER (PARTITION BY au_code_2013). "
        "Use to allocate AU-level metrics to overlapping SA2s: each SA2 "
        "receives `au_share × metric_at_au`."
    ),
    "sa2_share": (
        "population_2013 / SUM(population_2013) OVER (PARTITION BY suburb_id). "
        "Reverse-direction weight."
    ),
}


# ── Build helpers ───────────────────────────────────────────────────────


def load_au2013_dim(zip_path: Path) -> dict[str, str]:
    """Return {au_code: au_name} for all ~2,004 area units."""
    csv.field_size_limit(sys.maxsize)  # WKT polygons blow past the default
    au_dim: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("area-unit-2013.csv") as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8-sig")
            for row in csv.DictReader(text):
                au_dim[str(row["AU2013_V1_00"])] = row["AU2013_V1_00_NAME"]
    return au_dim


def iter_crosstab(xlsx_path: Path):
    """
    Stream the SA2 2018 × AU2013 population crosstab.

    Yields (au_code_2013, sa2_code_2018, population_2013) tuples for every
    non-zero cell. Skips title / blank / header rows.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Counts"]

    # Row 1 = title, row 2 = caption, row 3 = header with AU codes,
    # rows 4..N = SA2 rows. Col 1 is SA2 code; cols 2..M are AU codes.
    header = next(ws.iter_rows(min_row=3, max_row=3, values_only=True))
    au_codes = [str(c) if c is not None else None for c in header[1:]]

    for row in ws.iter_rows(min_row=4, values_only=True):
        sa2_code = row[0]
        if sa2_code is None:
            continue
        sa2_code = str(sa2_code)
        for au_code, pop in zip(au_codes, row[1:]):
            if au_code is None or pop is None or pop == 0:
                continue
            yield au_code, sa2_code, int(pop)


def build_bridge(crosstab_path: Path, au_zip_path: Path) -> pd.DataFrame:
    au_dim = load_au2013_dim(au_zip_path)
    print(f"AU2013 dim: {len(au_dim):,} (code, name) tuples")

    triples = list(iter_crosstab(crosstab_path))
    print(f"Non-zero overlaps: {len(triples):,}")

    au_totals: dict[str, int] = defaultdict(int)
    sa2_totals: dict[str, int] = defaultdict(int)
    for au, sa2, pop in triples:
        au_totals[au] += pop
        sa2_totals[sa2] += pop

    unmatched_codes: set[str] = set()
    records: list[dict] = []
    for au, sa2, pop in triples:
        name = au_dim.get(au)
        if name is None:
            unmatched_codes.add(au)
            continue
        records.append(
            {
                "area_unit": name,
                "au_code_2013": au,
                "suburb_id": sa2,
                "population_2013": pop,
                "au_share": round(pop / au_totals[au], 6),
                "sa2_share": round(pop / sa2_totals[sa2], 6),
            }
        )

    if unmatched_codes:
        print(
            f"  WARN: {len(unmatched_codes)} AU code(s) in crosstab not in AU "
            f"dim: {sorted(unmatched_codes)}"
        )

    df = pd.DataFrame.from_records(records).astype(
        {
            "area_unit": "string",
            "au_code_2013": "string",
            "suburb_id": "string",
            "population_2013": "int64",
            "au_share": "float64",
            "sa2_share": "float64",
        }
    )
    return df.sort_values(["area_unit", "suburb_id"]).reset_index(drop=True)


# ── Databricks I/O (mirror compute_isochrones.py) ───────────────────────


@lru_cache(maxsize=1)
def _workspace() -> tuple[Config, WorkspaceClient]:
    cfg = Config(profile=DATABRICKS_PROFILE)
    return cfg, WorkspaceClient(config=cfg)


@lru_cache(maxsize=1)
def _warehouse_id() -> str:
    _, workspace = _workspace()
    matching = [
        w for w in workspace.warehouses.list() if w.name == DATABRICKS_WAREHOUSE_NAME
    ]
    if not matching:
        sys.exit(f"No SQL warehouse named {DATABRICKS_WAREHOUSE_NAME!r} found.")
    return matching[0].id


def _run_sql(stmt: str) -> list[list]:
    _, workspace = _workspace()
    response = workspace.statement_execution.execute_statement(
        warehouse_id=_warehouse_id(),
        statement=stmt,
        wait_timeout="50s",
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


def upload_parquet(df: pd.DataFrame, volume_path: str) -> Path:
    """Write the DataFrame to a temp parquet file and upload to the volume."""
    local = Path(__file__).parent / "_tmp_area_unit_to_suburb.parquet"
    df.to_parquet(local, index=False)
    print(
        f"Built parquet: {local.name} ({local.stat().st_size / 1024:,.1f} KB, "
        f"{len(df):,} rows)"
    )

    _, workspace = _workspace()
    with open(local, "rb") as fin:
        workspace.files.upload(
            file_path=volume_path,
            contents=fin,
            overwrite=True,
        )
    print(f"  ✓ uploaded → {volume_path}")
    return local


def refresh_silver_table(volume_path: str, table: str) -> None:
    """CREATE OR REPLACE the silver table from the uploaded parquet, then comment."""
    print(f"Refreshing {table} from {volume_path}")
    _run_sql(
        f"CREATE OR REPLACE TABLE {table} USING DELTA AS "
        f"SELECT * FROM parquet.`{volume_path}`"
    )

    def _esc(s: str) -> str:
        return s.replace("'", "''")

    _run_sql(f"COMMENT ON TABLE {table} IS '{_esc(TABLE_COMMENT)}'")
    for col, comment in COLUMN_COMMENTS.items():
        _run_sql(f"ALTER TABLE {table} ALTER COLUMN {col} COMMENT '{_esc(comment)}'")

    [(row_count,)] = _run_sql(f"SELECT COUNT(*) FROM {table}")
    print(f"  ✓ {table} has {int(row_count):,} rows")


# ── Main ────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crosstab",
        type=Path,
        default=Path(__file__).parent
        / "data"
        / "2013-census-population-counts-by-sa22018-and-au2013.xlsx",
    )
    parser.add_argument(
        "--au-zip",
        type=Path,
        default=Path(__file__).parent / "data" / "statsnz-area-unit-2013-CSV.zip",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the UC write; just print the row count.",
    )
    args = parser.parse_args()

    for p in (args.crosstab, args.au_zip):
        if not p.is_file():
            sys.exit(
                f"Missing source file: {p}\n"
                f"  Download from Stats NZ DataFinder and place under "
                f"pipelines/police_recorded_crime/local/data/."
            )

    df = build_bridge(args.crosstab, args.au_zip)

    if args.dry_run:
        print(f"\n[dry-run] would write {len(df):,} rows to {SILVER_TABLE}")
        print(df.head(10).to_string(index=False))
        return 0

    local = upload_parquet(df, BRONZE_VOLUME_TARGET)
    refresh_silver_table(BRONZE_VOLUME_TARGET, SILVER_TABLE)
    local.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
