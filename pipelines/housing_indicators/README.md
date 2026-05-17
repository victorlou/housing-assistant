# housing_indicators

NZ housing-market indicators from the **HUD Local Housing Statistics (LHS)** dashboard, by territorial authority. Lands a long-format fact table plus three pivoted convenience tables for the most-asked questions (house prices, rent prices, affordability indices).

Complements `pipelines/prices/` (RBNZ M10, NZ-aggregate, 1990-2025) by adding TA-level granularity (67 TAs) plus metrics beyond just HPI: median sale price, median rent, deposit/mortgage/rent affordability indices, MSD housing register pressure, census tenure / crowding / deprivation.

## Contract — gold tables

### `housing.gold.housing_indicator__month__ta` (long-format fact)

The source of truth. One row per (date, area, theme, series, ethnicity). Mirrors HUD's tidy long shape so future themes / series land without schema change.

```sql
CREATE TABLE housing.gold.housing_indicator__month__ta (
  ta_name      STRING NOT NULL,    -- joins to gold.suburb.territorial_authority
  ta_code      STRING,             -- HUD's stable numeric area_id
  date         DATE NOT NULL,      -- end-of-period for this observation
  theme        STRING NOT NULL,    -- "Affordability", "MSD", "Sales", "Bonds", "RPI",
                                   -- "Building Consents", "Census Tenure",
                                   -- "Census Crowding", "Census Housing Deprivation",
                                   -- "Rent Proportion", "population"
  series       STRING NOT NULL,    -- e.g. "Current Annual Median Sales Price",
                                   -- "Deposit affordability index", "Housing Register"
  ethnicity    STRING,             -- demographic cut; mostly null, set for some census series
  value        DOUBLE,             -- the actual number
  value_type   STRING,             -- "index", "NZD", "percent", "count", "ratio", ...
  _updated_at  TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (theme);
```

### `housing.gold.house_price__month__ta` (pivoted view, "Sales" theme)

```sql
CREATE TABLE housing.gold.house_price__month__ta (
  ta_name                              STRING NOT NULL,
  ta_code                              STRING,
  date                                 DATE NOT NULL,    -- snapshot date the values refer to
  current_hpi                          DOUBLE,           -- House Price Index, current
  current_annual_median_sales_nzd      DOUBLE,           -- median sale price, current rolling year
  current_annual_lower_q_sales_nzd     DOUBLE,           -- lower-quartile sale price, current rolling year
  annual_sales_volume                  INT,              -- transactions in the rolling year
  _updated_at                          TIMESTAMP NOT NULL
)
USING DELTA;
```

### `housing.gold.rent_price__month__ta` (pivoted view, "Bonds" theme)

```sql
CREATE TABLE housing.gold.rent_price__month__ta (
  ta_name                STRING NOT NULL,
  ta_code                STRING,
  date                   DATE NOT NULL,
  median_rent_nzd        DOUBLE,
  average_rent_nzd       DOUBLE,
  lower_quartile_rent_nzd DOUBLE,
  _updated_at            TIMESTAMP NOT NULL
)
USING DELTA;
```

### `housing.gold.affordability__quarter__ta` (pivoted view, "Affordability" theme)

The deepest time series in HUD — quarterly affordability indices going back to 2001.

```sql
CREATE TABLE housing.gold.affordability__quarter__ta (
  ta_name                       STRING NOT NULL,
  ta_code                       STRING,
  quarter                       DATE NOT NULL,    -- first day of the quarter
  quarter_label                 STRING NOT NULL,  -- "2024-Q1"
  deposit_affordability_index   DOUBLE,           -- ratio of deposit needed vs household income
  mortgage_affordability_index  DOUBLE,           -- ratio of mortgage servicing vs household income
  rent_affordability_index      DOUBLE,           -- ratio of median rent vs household income
  median_to_median_ratio        DOUBLE,           -- median house price ÷ median household income
  _updated_at                   TIMESTAMP NOT NULL
)
USING DELTA;
```

## Join key to the suburb dim

`ta_name` is what HUD publishes ("Auckland", "Christchurch City", "Carterton District", ...) and matches `gold.suburb.territorial_authority` exactly for the 67 NZ TAs. Joins look like:

```sql
SELECT u.suburb_name, hp.current_annual_median_sales_nzd, a.mortgage_affordability_index
FROM housing.gold.suburb u
LEFT JOIN housing.gold.house_price__month__ta hp
  ON hp.ta_name = u.territorial_authority
  AND hp.date = (SELECT MAX(date) FROM housing.gold.house_price__month__ta)
LEFT JOIN housing.gold.affordability__quarter__ta a
  ON a.ta_name = u.territorial_authority
  AND a.quarter = (SELECT MAX(quarter) FROM housing.gold.affordability__quarter__ta)
WHERE u.region = 'Auckland Region';
```

## How it works

```
fetch_hud_lhs  →  transform_bronze  →  transform_silver  →  transform_gold
  (notebook)       (DLT pipeline)       (DLT pipeline)        (DLT pipeline)
```

### Task 1: `fetch_hud_lhs`

Reads the most recent HUD LHS XLSX uploaded to `/Volumes/housing/bronze/housing_indicators_files/_xlsx/hud_lhs/`, parses the `Metrics` sheet (already in tidy long format, no pivoting needed), and writes a CSV alongside at `/Volumes/housing/bronze/housing_indicators_files/hud_lhs/<date>.csv` for Auto Loader to stream.

Hash-dedup against `housing.bronze.ingest_runs` (`source = 'housing_indicators_hud_lhs'`).

Same volume-read pattern as `pipelines/prices/`. HUD doesn't appear to have Cloudflare protection on the LHS file (your browser download worked cleanly), so a future PR can add automated URL fetch — see [Coming next](#coming-next). For now, manual monthly upload.

### Tasks 2–4: bronze → silver → gold

- `bronze.py` → `housing_indicators_hud_lhs_raw` (Auto Loader CSV + provenance).
- `silver.py` → `housing_indicator` (typed long format, expectations dropping rows missing date/area/theme/series).
- `gold.py` materializes four tables:
  1. `housing_indicator__month__ta` (long, partitioned by theme).
  2. `house_price__month__ta` (Sales theme pivoted).
  3. `rent_price__month__ta` (Bonds theme pivoted).
  4. `affordability__quarter__ta` (Affordability theme pivoted, quarter-grain).

## Identity model

- **Job runs as:** `sp-housing-jobs`.
- **Pipelines run as:** same SP. Tables owned by the SP.
- **Compute:** serverless for the fetch task and all three DLT pipelines.
- **Failure alerts:** email to the address configured in `databricks.yml`.

## Schedule

- **Cron:** 10th of every month, 04:00 Pacific/Auckland. HUD refreshes the dashboard + the downloadable XLSX monthly. Manual upload + cron trigger picks up the new month automatically.

## Refreshing the HUD XLSX

Once per month:

1. Open [hud.govt.nz/stats-and-insights/local-housing-statistics/key-data](https://www.hud.govt.nz/stats-and-insights/local-housing-statistics/key-data) in a browser, scroll to "Local Housing Statistics data download", click the **Local housing statistics data download (XLSX)** link. The file is `LHS-data-download-<Month>-<Year>.xlsx`.
2. Upload it to the bronze volume with today's date as the filename:

   ```bash
   # First-time only: create the directory.
   databricks --profile hackathon fs mkdirs \
     dbfs:/Volumes/housing/bronze/housing_indicators_files/_xlsx/hud_lhs

   # Every month:
   today=$(date +%Y-%m-%d)
   databricks --profile hackathon fs cp \
     ~/Downloads/LHS-data-download-*.xlsx \
     "dbfs:/Volumes/housing/bronze/housing_indicators_files/_xlsx/hud_lhs/${today}.xlsx"
   ```

3. Trigger the bundle (or wait for the next monthly cron tick):

   ```bash
   cd pipelines/housing_indicators
   databricks bundle run housing_indicators_ingest --target dev
   ```

## Deploy

```bash
cd pipelines/housing_indicators
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

## Verify

```sql
-- Latest fetch attempt
SELECT source, status, content_hash, file_count, bytes_written, notes, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'housing_indicators_%' ORDER BY fetched_at DESC LIMIT 5;

-- Long-format row count by theme (expect Affordability biggest, then MSD)
SELECT theme, COUNT(*) AS rows, COUNT(DISTINCT ta_name) AS tas, MIN(date), MAX(date)
FROM housing.gold.housing_indicator__month__ta
GROUP BY theme ORDER BY rows DESC;

-- Most recent house-price snapshot per TA (top 10 by median)
SELECT ta_name, current_annual_median_sales_nzd, current_hpi
FROM housing.gold.house_price__month__ta
WHERE date = (SELECT MAX(date) FROM housing.gold.house_price__month__ta)
ORDER BY current_annual_median_sales_nzd DESC LIMIT 10;

-- Auckland affordability trend over 5 years
SELECT quarter_label, mortgage_affordability_index, deposit_affordability_index, rent_affordability_index
FROM housing.gold.affordability__quarter__ta
WHERE ta_name = 'Auckland'
  AND quarter >= add_months(current_date(), -60)
ORDER BY quarter;

-- Join everything: per-suburb affordability snapshot for Auckland
SELECT u.suburb_name, a.mortgage_affordability_index, a.rent_affordability_index
FROM housing.gold.suburb u
JOIN housing.gold.affordability__quarter__ta a ON a.ta_name = u.territorial_authority
WHERE u.region = 'Auckland Region'
  AND a.quarter = (SELECT MAX(quarter) FROM housing.gold.affordability__quarter__ta);
```

## What's worth verifying on first run

- **TA name alignment** with `gold.suburb.territorial_authority`. HUD ships TA names in a simplified ASCII form (no macrons, no hyphens, "Hawkes" not "Hawke's"). Silver normalises 8 known mismatches to Stats NZ's canonical NZGB names via the `TA_NAME_FIXES_SQL` CASE statement at the top of `silver.py` — Queenstown-Lakes, Thames-Coromandel, Matamata-Piako, Ōtorohanga, Ōpōtiki, Mackenzie (HUD ships "MacKenzie" with a capital K!), Central Hawke's Bay, Chatham Islands Territory. If HUD adds a new TA in a future release with another stylistic difference, add it to the CASE.
- **Series names in pivot maps.** `gold.py`'s pivots reference series like `"Current Annual Median Sales Price"` and `"Deposit affordability index"` verbatim. If HUD renames a series in a future release, the pivot column lands null until updated.
- **`value_type` consistency.** Silver casts `value` to DOUBLE assuming all values are numeric. HUD has been consistent so far; if a series ever ships as a string label, the cast fails — fix in silver.

## Known coverage gaps in HUD source

Even with TA-name normalisation applied, two areas have no HUD data and will return NULL on joins:

- **Area Outside Territorial Authority** — a Stats NZ placeholder for SA2s outside any administrative TA (offshore EEZ, etc.). 27 SA2s; HUD doesn't publish for them by design.
- **Wairoa District** — HUD ships affordability data but not Sales data (low transaction volume). Affordability join works; house_price join returns NULL.

Both are real data gaps, not bugs.

## Relationship to census_2023

[`pipelines/census_2023`](../census_2023/) ingests **SA2-level** 2023 Census metrics from Stats NZ ArcGIS and enriches `housing.gold.suburb` via `housing.silver.census_sa2_features`. This bundle (HUD) remains the source for **territorial-authority** housing-market indicators plus **TA-level** census summaries (themes `Census Tenure`, `Census Crowding`, `Census Housing Deprivation`, `Rent Proportion`).

| Question grain | Use |
|----------------|-----|
| Suburb / SA2 demographics | `housing.gold.suburb`, `housing.gold.income__year__suburb`, other `*__year__suburb` census marts |
| TA affordability, sales, rent | `housing.gold.affordability__quarter__ta`, `house_price__month__ta`, etc. |
| TA census % (quick join on `ta_name`) | `housing.gold.housing_indicator__month__ta` |

Median household income at SA2 is **not** in HUD; use census marts. HUD uses income only inside affordability ratios.

## Coming next

- **Automated URL fetch.** HUD's download URL is predictable (`/assets/Uploads/Documents/LHS-data-download-<Month>-<Year>.xlsx`). If `hud.govt.nz` doesn't Cloudflare-block Databricks egress (RBNZ does, HUD probably doesn't), this becomes one of the few NZ open-data sources we can poll automatically.
- **More pivoted views as need emerges.** MSD (housing register) — easy follow-up; census tenure/crowding at TA are largely superseded by SA2 census marts for suburb questions.
