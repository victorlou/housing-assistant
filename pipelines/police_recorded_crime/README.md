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

Unity Catalog volume `housing.bronze.crime_files` (Terraform seeds it in `terraform/modules/catalog`).

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

Or run pipelines individually:

```bash
databricks bundle run police_recorded_crime_bronze --target dev -p hackathon --refresh-all
databricks bundle run police_recorded_crime_silver --target dev -p hackathon --refresh-all
databricks bundle run police_recorded_crime_gold --target dev -p hackathon --refresh-all
```

## Tables

| Layer | Table | Role |
|-------|-------|------|
| Bronze | `housing.bronze.police_recorded_crime_anzsoc_victimisations_raw` | Auto Loader CSV |
| Bronze | `housing.bronze.police_recorded_crime_anzsoc_victimisations` | Typed rows |
| Silver | `housing.silver.crime_victimisation_monthly` | `SUM(victimisations)` by month, area unit, ANZSOC subdivision |
| Gold | `housing.gold.crime__month__area_unit` | Genie-ready area-unit mart |

## Verify

```sql
SELECT COUNT(*) FROM housing.bronze.police_recorded_crime_anzsoc_victimisations;
SELECT COUNT(*) FROM housing.silver.crime_victimisation_monthly;
SELECT COUNT(*) FROM housing.gold.crime__month__area_unit;

SELECT report_month, territorial_authority, area_unit, anzsoc_division, SUM(victimisation_count) AS total
FROM housing.gold.crime__month__area_unit
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 5 DESC
LIMIT 20;
```
