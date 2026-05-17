# Census 2023 (income / dwellings / individuals)

On-demand fetch of Stats NZ **2023 Census totals by topic** SA2 layers from ArcGIS, then bronze → silver → gold — same job shape as [`pipelines/gtfs`](../gtfs/).

**Canonical suburb dimension:** `housing.gold.suburb` is owned by [`pipelines/places`](../places/). This bundle produces SA2 marts and `housing.silver.census_sa2_features`; run places gold after census to enrich `gold.suburb`.

Research notes: [`.devnotes/census/README.md`](../../.devnotes/census/README.md) (local, gitignored).

## Job flow

```
fetch_households_sa2 ─┐
fetch_dwellings_sa2  ─┤  (parallel)
fetch_individuals_sa2─┘
         │ ALL_DONE
         ▼
transform_bronze  →  transform_silver  →  transform_gold
```

1. **fetch_*** — page ArcGIS FeatureServer → JSONL + field-dictionary CSV on `/Volumes/housing/bronze/census_2023_files/<dataset>/<date>/`.
2. **transform_bronze** — Auto Loader → `housing.bronze.census_2023_*_sa2`.
3. **transform_silver** — long `census_sa2_metric`, wide `census_sa2_features` (manifest: `census_2023_gold.yml`).
4. **transform_gold** — Genie-ready marts below.

## Gold tables

| Table | Contents |
|-------|----------|
| `housing.gold.income__year__suburb` | Median household income, household counts by SA2 |
| `housing.gold.tenure__year__suburb` | Tenure counts + owner-occupier % |
| `housing.gold.rent__year__suburb` | Median weekly rent (renting households) |
| `housing.gold.crowding__year__suburb` | Crowding counts + % crowded |
| `housing.gold.dwelling__year__suburb` | Dampness, mould, heating, mean rooms |
| `housing.gold.census_metric__year__sa2` | Long curated metrics for open-ended queries |

NZDep2023 is **not** in this bundle (SA1 / separate ADE tables).

## Relationship to housing_indicators (HUD)

HUD ships **TA-level** census themes (Tenure, Crowding, Housing Deprivation, Rent Proportion) in `housing.gold.housing_indicator__month__ta`. This pipeline is the **SA2 canonical** source. Use HUD for TA rollups and affordability; use census marts + `gold.suburb` for suburb-level questions.

Optional validation: roll up SA2 `owner_occupier_pct` to TA and compare to HUD `Census Tenure` for the same TA.

## Identity model

- **Job runs as:** `sp-housing-jobs`.
- **Pipelines:** serverless DLT, same SP.
- **Failure alerts:** email in `databricks.yml`.

## Schedule

Paused annual cron (5 Mar 04:00 NZ). Census is a static snapshot — run on demand after deploy.

## Deploy

```bash
cd pipelines/census_2023
databricks bundle validate --target dev -p hackathon
databricks bundle deploy --target dev -p hackathon
databricks bundle run census_2023_ingest --target dev -p hackathon
```

Then refresh places gold (see [`pipelines/places/README.md`](../places/README.md)).

## Verify

```sql
SELECT source, status, content_hash, bytes_written, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'census_2023%'
ORDER BY fetched_at DESC;

SELECT COUNT(*) FROM housing.silver.census_sa2_metric;
SELECT COUNT(*) FROM housing.silver.census_sa2_features;

SELECT census_year, COUNT(*), COUNT(median_household_income)
FROM housing.gold.income__year__suburb
GROUP BY census_year;

SELECT COUNT(*) FROM housing.gold.tenure__year__suburb;
SELECT COUNT(*) FROM housing.gold.census_metric__year__sa2;
```

## Configuration

- ArcGIS layers: [`config/sources/census_2023.yml`](../../config/sources/census_2023.yml)
- Gold metric manifest: [`census_2023_gold.yml`](./census_2023_gold.yml) (copy in [`config/sources/census_2023_gold.yml`](../../config/sources/census_2023_gold.yml))

## Local fetch (optional)

```bash
python -m pip install requests pyyaml
python .devnotes/census/scripts/fetch_arcgis.py --all
```

Upload JSONL to the census bronze volume before running transforms only.
