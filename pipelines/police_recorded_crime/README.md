# NZ Police recorded crime

Bronze → silver → gold for manually uploaded Police Tableau CSV exports (same job shape as `pipelines/gtfs/`).

## Data

Tableau **Full Data** export: ANZSOC offence codes, `Year Month`, `Victimisations`. **No geography** in the current file — see [`.devnotes/police/schema.md`](../../.devnotes/police/schema.md).

## Prerequisites

Unity Catalog volume `housing.bronze.crime_files` must exist (Terraform seeds it in `terraform/modules/catalog`). If missing:

```sql
CREATE VOLUME IF NOT EXISTS housing.bronze.crime_files
  COMMENT 'NZ Police crime statistics CSV landings';
```

## Upload landing file (before running the job)

```powershell
$date = Get-Date -Format "yyyy-MM-dd"
databricks fs cp "$env:USERPROFILE\Downloads\ANZSOC_Full Data_data.csv" `
  "dbfs:/Volumes/housing/bronze/crime_files/police_recorded_crime/$date/anzsoc_victimisations.csv" `
  --overwrite -p hackathon
```

## Deploy

```bash
cd pipelines/police_recorded_crime
databricks bundle validate --target dev -p hackathon
databricks bundle deploy --target dev -p hackathon
```

## Run (bronze → silver → gold)

```bash
databricks bundle run police_recorded_crime_ingest --target dev -p hackathon
```

Or run pipelines individually:

```bash
databricks bundle run police_bronze --target dev -p hackathon
databricks bundle run police_silver --target dev -p hackathon
databricks bundle run police_gold --target dev -p hackathon
```

## Tables

| Layer | Table | Role |
|-------|-------|------|
| Bronze | `housing.bronze.police_anzsoc_victimisations_raw` | Auto Loader CSV |
| Bronze | `housing.bronze.police_anzsoc_victimisations` | Typed rows |
| Silver | `housing.silver.crime_victimisation_monthly` | `SUM(victimisations)` by month + ANZSOC subdivision |
| Gold | `housing.gold.crime__month__anzsoc_subdivision` | Genie-ready national mart |

`housing.gold.crime__month__area_unit` (area-unit breakdown) waits on a geographic Police export.

## Verify

```sql
SELECT COUNT(*) FROM housing.bronze.police_anzsoc_victimisations;
SELECT COUNT(*) FROM housing.silver.crime_victimisation_monthly;
SELECT COUNT(*) FROM housing.gold.crime__month__anzsoc_subdivision;

SELECT report_month, anzsoc_division, SUM(victimisation_count) AS total
FROM housing.gold.crime__month__anzsoc_subdivision
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC
LIMIT 20;
```

Registry: [`data/sources.yaml`](../../data/sources.yaml). Plan: [`.devnotes/police/databricks-plan.md`](../../.devnotes/police/databricks-plan.md).
