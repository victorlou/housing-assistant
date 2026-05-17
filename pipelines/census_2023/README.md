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
4. **transform_gold** — Genie-ready wide table below.

## Gold tables

Following [`docs/conventions.md`](../../docs/conventions.md) (`<spatial_dim>__<time_grain>`): one wide table at SA2 + census-year grain.

| Table | Contents |
|-------|----------|
| `housing.gold.suburb__year` | Every curated 2023 Census metric per SA2 — income, tenure, rent, crowding, dwelling quality, demographics. One row per `(suburb_id, census_year)`. |

For long-format / open-ended Genie queries (any HUD theme, any field) use `housing.silver.census_sa2_metric` directly — it's the unpivoted escape hatch and stays in silver per the conventions doc.

NZDep2023 is **not** in this bundle (SA1 / separate ADE tables).

## Relationship to housing_indicators (HUD)

HUD ships **TA-level** census themes (Tenure, Crowding, Housing Deprivation, Rent Proportion) in the long-format silver `housing.silver.housing_indicator` (filter `theme LIKE 'Census %' OR theme = 'Rent Proportion'`); they aren't pivoted into `gold.ta__month` because the SA2 census marts now cover those questions at finer grain. This pipeline is the **SA2 canonical** source. Use HUD `housing.gold.ta__quarter` / `ta__month` for TA-level affordability, sales, rent, and MSD; use census marts + `gold.suburb` for suburb-level questions.

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

-- One row per (suburb_id, census_year); expect ~2,395 SA2s for census_year = 2023.
SELECT census_year,
       COUNT(*)                          AS suburbs,
       COUNT(median_household_income)    AS with_income,
       COUNT(median_weekly_rent)         AS with_rent,
       COUNT(percent_crowded)            AS with_crowding
FROM housing.gold.suburb__year
GROUP BY census_year;

-- Top 10 most expensive renting suburbs in 2023
SELECT suburb_name, median_weekly_rent
FROM housing.gold.suburb__year
WHERE census_year = 2023 AND median_weekly_rent IS NOT NULL
ORDER BY median_weekly_rent DESC LIMIT 10;

-- Long-format escape hatch for any HUD metric not pivoted into the wide table
SELECT COUNT(*) FROM housing.silver.census_sa2_metric;
```

## Configuration

- ArcGIS layers: [`census_2023.yml`](./census_2023.yml)
- Gold metric manifest: [`census_2023_gold.yml`](./census_2023_gold.yml)

## Local fetch (optional)

```bash
python -m pip install requests pyyaml
python .devnotes/census/scripts/fetch_arcgis.py --all
```

Upload JSONL to the census bronze volume before running transforms only.
