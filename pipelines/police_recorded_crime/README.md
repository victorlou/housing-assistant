# NZ Police recorded crime

Bronze → silver → gold for manually uploaded Police Tableau CSV exports (same job shape as `pipelines/gtfs/`).

## Data

Tableau **Full Data** export (`ANZSOC_Full Data.csv`):

| Column | Role |
|--------|------|
| `Year Month` | Report month label |
| `Territorial Authority` | TA name |
| `Area Unit` | Stats NZ area unit |
| `Month Year` | Duplicate month label (kept in bronze) |
| `Victimisations` | Count |
| `ANZSOC Division` / `Group` / `Subdivision` | Offence hierarchy (text labels) |

Rows with `Area Unit = 999999` are excluded in bronze.

## Prerequisites

- Unity Catalog volume `housing.bronze.crime_files` (Terraform seeds it in `terraform/modules/catalog`).
- **AU2013 ↔ SA2 concordance silver table** — one-off upload, see [Area-unit-to-suburb bridge](#area-unit-to-suburb-bridge-one-off) below. Without it, crime stays at area-unit grain and won't join to `gold.suburb`.

## Area-unit-to-suburb bridge (one-off)

Police data is keyed by **Area Unit 2013**, a retired Stats NZ geography that doesn't sit in our `h3_cell → suburb_id (SA2) → TA → region` hierarchy. To make crime joinable at suburb grain we need a bridge table.

The bridge is built locally (one-off) from two static Stats NZ source files because they're 2013 Census artifacts that will never change. See [`local/build_area_unit_to_suburb.py`](local/build_area_unit_to_suburb.py) for the build details + source URLs.

[`local/build_area_unit_to_suburb.py`](local/build_area_unit_to_suburb.py) writes the silver table directly via `parquet → bronze volume → CREATE OR REPLACE TABLE` (same auth + SQL-warehouse pattern as `compute_isochrones.py` and `compute_amenities.py`). About 4k rows. Schema after build:

| column          | type   | description                                                                              |
|-----------------|--------|------------------------------------------------------------------------------------------|
| `area_unit`       | STRING | AU2013 name. Matches `police_recorded_crime_anzsoc_victimisations.area_unit` (silver). |
| `au_code_2013`    | STRING | 6-digit AU2013 code.                                                                   |
| `suburb_id`       | STRING | 6-digit SA2 2018 code. ~94% overlap with SA2 2023 (135 SA2s added since).              |
| `population_2013` | INT    | 2013 Census usual residents at this (au, sa2) overlap.                                 |
| `au_share`        | DOUBLE | population / sum-over-AU. Allocation weight: SA2 gets `au_share × victimisations`.     |
| `sa2_share`       | DOUBLE | population / sum-over-SA2. Reverse-direction weight.                                   |

### Run once

Place the two source files (see script docstring for DataFinder URLs) under `pipelines/police_recorded_crime/local/data/` then:

```bash
python pipelines/police_recorded_crime/local/build_area_unit_to_suburb.py
# add --dry-run to inspect without writing
```

The script lands `housing.silver.area_unit_to_suburb` populated with ~4k rows, applies the table + column comments, and leaves the parquet at `dbfs:/Volumes/housing/bronze/crime_files/concordance/area_unit_to_suburb.parquet` as the source-of-truth artefact. Re-runnable if Stats NZ ever republishes either source file.

### Known gaps

- 1 AU code (`626602`) in the census crosstab isn't present in the AU2013 attribute table — single row dropped in the build. Likely a boundary edit between vintages. Doesn't affect any major area.
- SA2 2023 added 135 SA2s vs 2018. Those won't appear in the bridge; downstream rows will have NULL `suburb_id`. Mostly recent urban infill; fix later if it matters.
- Colloquial names like "Onehunga" don't appear in AU2013 — they're split into `Onehunga North East / North West / South East`. Genie should be primed to expand these.

## Upload landing file (before running the job)

```powershell
$date = Get-Date -Format "yyyy-MM-dd"
databricks fs mkdir "dbfs:/Volumes/housing/bronze/crime_files/police_recorded_crime/$date" -p hackathon
databricks fs cp "$env:USERPROFILE\Downloads\ANZSOC_Full Data.csv" `
  "dbfs:/Volumes/housing/bronze/crime_files/police_recorded_crime/$date/anzsoc_victimisations.csv" `
  --overwrite -p hackathon
```

Remove superseded landings so Auto Loader does not re-ingest old exports.

## Deploy

```bash
cd pipelines/police_recorded_crime
databricks bundle validate --target dev -p hackathon
databricks bundle deploy --target dev -p hackathon
```

## Run (bronze → silver → gold)

After a schema change or landing replacement, use full refresh:

```bash
databricks bundle run police_recorded_crime_ingest --target dev -p hackathon --refresh-all
```

Or run pipelines individually (no gold layer in this bundle — see [Cross-pipeline order](#cross-pipeline-order)):

```bash
databricks bundle run police_recorded_crime_bronze --target dev -p hackathon --refresh-all
databricks bundle run police_recorded_crime_silver --target dev -p hackathon --refresh-all
```

## Tables

| Layer | Table | Role |
|-------|-------|------|
| Bronze | `housing.bronze.police_recorded_crime_anzsoc_victimisations_raw` | Auto Loader CSV |
| Bronze | `housing.bronze.police_recorded_crime_anzsoc_victimisations` | Typed rows |
| Silver | `housing.silver.crime_victimisation_monthly` | `SUM(victimisations)` by month, area unit, ANZSOC subdivision — long-format breakdown escape hatch |
| Silver | `housing.silver.area_unit_to_suburb` | One-off concordance: AU2013 name + code ↔ SA2 2018 with population-weighted shares. Built locally; see [Area-unit-to-suburb bridge](#area-unit-to-suburb-bridge-one-off). |
| Silver | `housing.silver.crime_at_suburb_year` | Annual victimisations per SA2, allocated from AU data via the bridge. One row per (suburb_id, crime_year). This is what `gold.suburb__year` consumes. |

This bundle has **no gold layer of its own**. Crime totals are folded into `housing.gold.suburb__year` (owned by the `census_2023` pipeline) so consumers get census demographics, dwelling quality, and crime in a single SELECT at one canonical suburb/year grain. Long-format breakdowns stay in silver per the conventions doc.

## Cross-pipeline order

`census_2023.gold.suburb__year` reads `silver.crime_at_suburb_year` via `spark.read.table`. For the crime column to populate, run **police silver before census gold**:

```bash
databricks bundle run police_recorded_crime_ingest --target dev -p hackathon
databricks bundle run census_2023_gold           --target dev -p hackathon --refresh-all
```

If police silver hasn't run yet, the census gold pipeline gracefully nulls the crime column (same try/except pattern places gold uses for census features).

## Verify

```sql
SELECT COUNT(*) FROM housing.bronze.police_recorded_crime_anzsoc_victimisations;
SELECT COUNT(*) FROM housing.silver.crime_victimisation_monthly;
SELECT COUNT(*) FROM housing.silver.area_unit_to_suburb;
SELECT COUNT(*) FROM housing.silver.crime_at_suburb_year;

-- Top suburbs by total victimisations in 2023
SELECT suburb_id, suburb_name, total_victimisations_2023, population_total
FROM housing.gold.suburb__year
WHERE total_victimisations_2023 IS NOT NULL
ORDER BY total_victimisations_2023 DESC
LIMIT 20;

-- Offence-subdivision breakdown for one area unit (silver, long-format)
SELECT report_month, anzsoc_division, anzsoc_subdivision, victimisation_count
FROM housing.silver.crime_victimisation_monthly
WHERE area_unit = 'Onehunga North East' AND report_month >= add_months(current_date(), -12)
ORDER BY report_month DESC, victimisation_count DESC;
```
