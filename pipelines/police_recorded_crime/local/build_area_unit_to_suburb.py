"""
One-off build of `housing.silver.area_unit_to_suburb` from Stats NZ's
Geographic Areas Table 2023.

Police recorded-crime data is keyed by Area Unit 2013 (a retired Stats NZ
geography) and doesn't carry an area-unit *code* in the CSV, only the name.
Our other suburb-level data (`gold.suburb`, `gold.suburb__year`, etc.) is
keyed by SA2 2023 codes. To make crime joinable at suburb grain we need a
bridge: `AU2013_name → SA22023_code`.

Building it end-to-end on Databricks would be a full pipeline. But the
source is *static* — Stats NZ's Geographic Areas Table 2023, a meshblock-
level concordance of every NZ geography that won't change until the next
census cycle. So this is a one-off local build that writes the silver
table directly via the SQL warehouse: parquet → bronze volume →
CREATE OR REPLACE TABLE.

## Why this file is the right source

Earlier iterations used two separate files (a 2013 Census SA2 × AU
population crosstab + the standalone AU2013 attribute table). That worked
for the AU → SA2_2018 hop but left a ~27% gap on the SA2_2018 → SA2_2023
join (Stats NZ renumbered ~30% of SA2s in the 2023 vintage update,
considerably more than the "135 new SA2s" headline figure).

The Geographic Areas Table 2023 (DataFinder layer 111243) sits at
meshblock grain and carries every NZ geographic classification per row,
including AU2013_code/name, SA22018_code, SA22023_code. We aggregate
meshblocks to (AU2013, SA22023) overlaps in one pass — single bridge,
no vintage gap, ~100% coverage.

## Source

`geographic-areas-table-2023.csv` inside `statsnz-geographic-areas-table-
2023-CSV.zip` from
https://datafinder.stats.govt.nz/table/111243-geographic-areas-table-2023/.
57,539 rows, one per 2023 meshblock. All meshblocks have AU2013/SA22023
codes populated.

## Output

`housing.silver.area_unit_to_suburb` — long-format bridge with one row per
(AU2013, SA22023) overlap.

| column          | type   | description                                                                |
|-----------------|--------|----------------------------------------------------------------------------|
| area_unit       | STRING | AU2013 name. Matches `silver.crime_victimisation_monthly.area_unit`.       |
| au_code_2013    | STRING | 6-digit Stats NZ AU2013 code.                                              |
| suburb_id       | STRING | 6-digit Stats NZ SA22023 code. Joins to `gold.suburb.suburb_id` directly.  |
| meshblock_count | INT    | Number of 2023 meshblocks at this (AU, SA22023) overlap.                   |
| au_share        | DOUBLE | meshblock_count / sum-over-AU. Allocation weight for AU metrics → SA22023. |
| sa2_share       | DOUBLE | meshblock_count / sum-over-SA22023. Reverse-direction weight.              |

## Allocation note

We weight by meshblock count rather than 2013 census population. Meshblocks
are Stats NZ's atomic units and are designed to contain a roughly uniform
number of people (~100-200), so meshblock-count weighting is a clean proxy
for population-share and avoids tying us to any single census year.

## Run

    python pipelines/police_recorded_crime/local/build_area_unit_to_suburb.py \\
        --source path/to/geographic-areas-table-2023.csv

Defaults to reading the source from `local/data/`. Pass `--dry-run` to
inspect row counts without writing to UC.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import zipfile
from collections import Counter, defaultdict
from functools import lru_cache
from io import TextIOWrapper
from pathlib import Path

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


# ── Databricks config ──────────────────────────────────────────────────
DATABRICKS_PROFILE = "hackathon"
DATABRICKS_WAREHOUSE_NAME = "housing-assistant-dev"

BRONZE_VOLUME_TARGET = (
    "/Volumes/housing/bronze/crime_files/concordance/area_unit_to_suburb.parquet"
)
SILVER_TABLE = "housing.silver.area_unit_to_suburb"

TABLE_COMMENT = (
    "AU2013 → SA22023 meshblock-weighted concordance, with AU2013 names "
    "attached for joins to police_recorded_crime silver. Built one-off "
    "from Stats NZ's Geographic Areas Table 2023 (DataFinder layer 111243) "
    "by pipelines/police_recorded_crime/local/build_area_unit_to_suburb.py. "
    "About 4.6k rows, one per (AU2013, SA22023) overlap. Allocation weights "
    "(`au_share`, `sa2_share`) are derived from meshblock counts; meshblocks "
    "are Stats NZ atomic units of ~100-200 people so the weighting is a "
    "clean proxy for population share. JOINS: area_unit = "
    "silver.crime_victimisation_monthly.area_unit (after the trailing-dot "
    "strip in police bronze); suburb_id = gold.suburb.suburb_id (SA22023)."
)

COLUMN_COMMENTS = {
    "area_unit": (
        "Stats NZ AU2013 name. Matches "
        "`silver.crime_victimisation_monthly.area_unit` exactly after the "
        "trailing-dot strip in police bronze."
    ),
    "au_code_2013": "6-digit Stats NZ AU2013 code.",
    "suburb_id": (
        "6-digit Stats NZ SA22023 code. Joins to gold.suburb.suburb_id "
        "directly — no vintage gap since the source is the 2023-vintage "
        "Geographic Areas Table."
    ),
    "meshblock_count": (
        "Number of 2023 meshblocks at this (AU, SA22023) overlap. The basis "
        "for the share columns."
    ),
    "au_share": (
        "meshblock_count / SUM(meshblock_count) OVER (PARTITION BY au_code_2013). "
        "Use to allocate AU-level metrics to overlapping SA22023s: each SA2 "
        "receives `au_share × metric_at_au`."
    ),
    "sa2_share": (
        "meshblock_count / SUM(meshblock_count) OVER (PARTITION BY suburb_id). "
        "Reverse-direction weight."
    ),
}


# ── Build helpers ──────────────────────────────────────────────────────


def iter_meshblock_rows(zip_path: Path):
    """
    Stream rows from geographic-areas-table-2023.csv inside the zip.

    Yields (au_code, au_name, sa22023_code, sa22023_name) tuples. Skips
    rows missing any key (in practice all 57,539 rows have all four).
    """
    csv.field_size_limit(sys.maxsize)
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("geographic-areas-table-2023.csv") as fh:
            text = TextIOWrapper(fh, encoding="utf-8-sig")
            rdr = csv.DictReader(text)
            for row in rdr:
                au_code = (row.get("AU2013_code") or "").strip()
                au_name = (row.get("AU2013_name") or "").strip()
                sa_code = (row.get("SA22023_code") or "").strip()
                sa_name = (row.get("SA22023_name") or "").strip()
                if not (au_code and au_name and sa_code and sa_name):
                    continue
                yield au_code, au_name, sa_code, sa_name


def build_bridge(zip_path: Path) -> pd.DataFrame:
    overlap_counts: Counter[tuple[str, str]] = Counter()
    au_names: dict[str, str] = {}
    sa_names: dict[str, str] = {}
    for au_code, au_name, sa_code, sa_name in iter_meshblock_rows(zip_path):
        overlap_counts[(au_code, sa_code)] += 1
        au_names.setdefault(au_code, au_name)
        sa_names.setdefault(sa_code, sa_name)

    total_meshblocks = sum(overlap_counts.values())
    print(f"Meshblocks: {total_meshblocks:,}")
    print(f"Distinct (AU, SA22023) overlaps: {len(overlap_counts):,}")
    print(f"Distinct AUs:       {len(au_names):,}")
    print(f"Distinct SA22023s:  {len(sa_names):,}")

    au_totals: dict[str, int] = defaultdict(int)
    sa_totals: dict[str, int] = defaultdict(int)
    for (au, sa), count in overlap_counts.items():
        au_totals[au] += count
        sa_totals[sa] += count

    records: list[dict] = []
    for (au, sa), count in overlap_counts.items():
        records.append(
            {
                "area_unit": au_names[au],
                "au_code_2013": au,
                "suburb_id": sa,
                "meshblock_count": int(count),
                "au_share": round(count / au_totals[au], 6),
                "sa2_share": round(count / sa_totals[sa], 6),
            }
        )

    df = pd.DataFrame.from_records(records).astype(
        {
            "area_unit": "string",
            "au_code_2013": "string",
            "suburb_id": "string",
            "meshblock_count": "int64",
            "au_share": "float64",
            "sa2_share": "float64",
        }
    )
    return df.sort_values(["area_unit", "suburb_id"]).reset_index(drop=True)


# ── Databricks I/O ─────────────────────────────────────────────────────


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


# ── Main ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).parent
        / "data"
        / "statsnz-geographic-areas-table-2023-CSV.zip",
        help="Path to the zip containing geographic-areas-table-2023.csv.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the UC write; just print the row count + sample.",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        sys.exit(
            f"Missing source file: {args.source}\n"
            f"  Download from "
            f"https://datafinder.stats.govt.nz/table/111243-geographic-areas-table-2023/ "
            f"and place under pipelines/police_recorded_crime/local/data/."
        )

    df = build_bridge(args.source)

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
