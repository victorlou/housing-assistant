# Census 2023 (income / dwellings)

On-demand (or annual) fetch of Stats NZ **2023 Census totals by topic** SA2 layers from ArcGIS, then bronze → silver → gold — same job shape as `pipelines/gtfs`.

Research notes: [`.devnotes/census/README.md`](../../.devnotes/census/README.md).

## Job flow

1. **fetch_households_sa2** / **fetch_dwellings_sa2** (parallel) — page ArcGIS FeatureServer → JSONL and field-dictionary CSV on `/Volumes/housing/bronze/census_files/<dataset>/<date>/`.
2. **transform_bronze** — Auto Loader → `housing.bronze.census_households_sa2`, `housing.bronze.census_dwellings_sa2`.
3. **transform_silver** — unpivot `VAR_*`, join field dictionary → `census_sa2_metric`, `census_sa2_area`.
4. **transform_gold** — `income__year__suburb`, `suburb` (SA2 geography until `place_lookup` exists).

## Gold tables

| Table | Contents |
|-------|----------|
| `housing.gold.income__year__suburb` | 2023 median household income, household counts by SA2 |
| `housing.gold.suburb` | SA2 snapshot: H3 centroid, tenure, income (partial `suburb` dim) |

NZDep2023 is **not** in this bundle yet (SA1 / separate ADE tables).

## Deploy

```bash
cd pipelines/census_2023
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run census_2023_ingest --target dev
```

## Verify

```sql
SELECT source, status, content_hash, bytes_written, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'census_2023%'
ORDER BY fetched_at DESC;

SELECT census_year, COUNT(*) FROM housing.gold.income__year__suburb GROUP BY 1;
SELECT COUNT(*) FROM housing.silver.census_sa2_metric;
```

## Local fetch (optional)

```bash
python -m pip install requests
python .devnotes/census/scripts/fetch_arcgis.py --all
```

Then upload JSONL to the census bronze volume before running transforms only.
