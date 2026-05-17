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
| Silver | `housing.silver.crime_victimisation_monthly` | `SUM(victimisations)` by month, area unit, ANZSOC subdivision — long-format breakdown escape hatch |
| Gold | `housing.gold.area_unit__month` | Wide-at-grain Genie-ready mart: one row per (area_unit, month) with `total_victimisations` |

Following [`docs/conventions.md`](../../docs/conventions.md): gold is wide-at-grain (`<spatial_dim>__<time_grain>`); long-format breakdowns stay in silver.

## Verify

```sql
SELECT COUNT(*) FROM housing.bronze.police_recorded_crime_anzsoc_victimisations;
SELECT COUNT(*) FROM housing.silver.crime_victimisation_monthly;
SELECT COUNT(*) FROM housing.gold.area_unit__month;

-- Top area units by total recorded victimisations in the latest month
SELECT report_month, territorial_authority, area_unit, total_victimisations
FROM housing.gold.area_unit__month
WHERE report_month = (SELECT MAX(report_month) FROM housing.gold.area_unit__month)
ORDER BY total_victimisations DESC
LIMIT 20;

-- Offence-subdivision breakdown for one area unit (silver, long-format)
SELECT report_month, anzsoc_division, anzsoc_subdivision, victimisation_count
FROM housing.silver.crime_victimisation_monthly
WHERE area_unit = 'Onehunga West' AND report_month >= add_months(current_date(), -12)
ORDER BY report_month DESC, victimisation_count DESC;
```
