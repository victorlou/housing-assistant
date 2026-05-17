# housing_indicators

NZ housing-market indicators from the **HUD Local Housing Statistics (LHS)** dashboard, by territorial authority. Lands two wide time-series gold tables keyed on TA + period — `ta__month` and `ta__quarter` — covering everything HUD publishes that fits at those grains (prices, rents, affordability, MSD waiting-list pressure).

Complements `pipelines/prices/` (RBNZ M10, NZ-aggregate, 1990-current) by adding TA-level granularity (67 TAs) plus metrics beyond just HPI.

## Contract — gold tables

Following the lakehouse convention `<spatial_dim>__<time_grain>` (see `docs/conventions.md`): the table tells you the grain, columns tell you the metrics. The agent doesn't have to know which HUD theme a metric came from — it's all in one table per (dim, period).

### `housing.gold.ta__month`

One row per (ta_name, date). Sparse by design — Sales/Bonds rows appear on snapshot dates HUD publishes; MSD rows appear monthly back to 2017.

```sql
CREATE TABLE housing.gold.ta__month (
  ta_name                            STRING NOT NULL,    -- "Auckland", "Wellington City", … or "New Zealand" rollup
  ta_code                            STRING,
  date                               DATE NOT NULL,
  -- Sales (HUD snapshots; rolling-annual values)
  current_hpi                        DOUBLE,
  current_annual_median_sales_nzd    DOUBLE,
  current_annual_lower_q_sales_nzd   DOUBLE,
  annual_sales_volume                INT,
  -- Rent / bonds (HUD snapshots from MBIE rental-bond lodgements)
  median_rent_nzd                    DOUBLE,
  average_rent_nzd                   DOUBLE,
  lower_quartile_rent_nzd            DOUBLE,
  -- MSD waiting list (true monthly time series back to 2017)
  housing_register                   INT,
  housing_register_per_10k_pop       DOUBLE,
  _updated_at                        TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (ta_name);
```

### `housing.gold.ta__quarter`

One row per (ta_name, quarter). HUD's four affordability indices — the deepest time series in the lakehouse (2001-current).

```sql
CREATE TABLE housing.gold.ta__quarter (
  ta_name                       STRING NOT NULL,
  ta_code                       STRING,
  quarter                       DATE NOT NULL,
  quarter_label                 STRING NOT NULL,    -- "2024-Q1"
  deposit_affordability_index   DOUBLE,
  mortgage_affordability_index  DOUBLE,
  rent_affordability_index      DOUBLE,
  median_to_median_ratio        DOUBLE,
  _updated_at                   TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (ta_name);
```

The long-format unpivoted source-of-truth stays at `housing.silver.housing_indicator` for anyone who wants the raw HUD shape; gold tables are the curated wide views consumers should hit.

## Joining to the suburb dim

`ta_name` matches `gold.suburb.territorial_authority` exactly across all 67 NZ TAs (silver normalises HUD's ASCII forms to Stats NZ canonical NZGB names). Sample join:

```sql
SELECT u.suburb_name,
       m.current_annual_median_sales_nzd,
       m.median_rent_nzd,
       q.mortgage_affordability_index
FROM housing.gold.suburb u
LEFT JOIN housing.gold.ta__month m
  ON m.ta_name = u.territorial_authority
  AND m.date = (SELECT MAX(date) FROM housing.gold.ta__month WHERE ta_name = u.territorial_authority)
LEFT JOIN housing.gold.ta__quarter q
  ON q.ta_name = u.territorial_authority
  AND q.quarter = (SELECT MAX(quarter) FROM housing.gold.ta__quarter WHERE ta_name = u.territorial_authority)
WHERE u.region = 'Auckland Region';
```

## How it works

```
fetch_hud_lhs  →  transform_bronze  →  transform_silver  →  transform_gold
  (notebook)       (DLT pipeline)        (DLT pipeline)        (DLT pipeline)
```

`notebooks/fetch.py` validates a manually-uploaded HUD LHS XLSX and writes a tidy long CSV. Bronze Auto Loader streams that CSV in. Silver projects it into `housing.silver.housing_indicator` (long format, one row per (date, area, theme, series, ethnicity), with HUD TA names normalised to Stats NZ canonical). Gold pivots the long format into the two wide tables above via conditional-aggregation (DLT-safe equivalent of `GroupedData.pivot`).

## Identity / schedule / deploy

- **Job runs as:** `sp-housing-jobs` (same for the three DLT pipelines).
- **Compute:** serverless throughout.
- **Cron:** 10th of every month, 04:00 Pacific/Auckland. HUD refreshes monthly; runs hash-skip cleanly when no fresh XLSX is uploaded.

```bash
cd pipelines/housing_indicators
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

## Refreshing the HUD XLSX

Once per month:

1. Open [hud.govt.nz/stats-and-insights/local-housing-statistics/key-data](https://www.hud.govt.nz/stats-and-insights/local-housing-statistics/key-data), download the **Local housing statistics data download (XLSX)** link.
2. Upload:

   ```bash
   today=$(date +%Y-%m-%d)
   databricks --profile hackathon fs cp \
     ~/Downloads/LHS-data-download-*.xlsx \
     "dbfs:/Volumes/housing/bronze/housing_indicators_files/_xlsx/hud_lhs/${today}.xlsx"
   ```

3. Trigger or wait for the cron tick: `databricks bundle run housing_indicators_ingest --target dev`.

## Verify

```sql
-- Headline shape per gold table
SELECT 'ta__month'   AS table, COUNT(*) AS rows,
       COUNT(DISTINCT ta_name) AS tas, MIN(date), MAX(date)
FROM housing.gold.ta__month
UNION ALL
SELECT 'ta__quarter', COUNT(*), COUNT(DISTINCT ta_name),
       CAST(MIN(quarter) AS STRING), CAST(MAX(quarter) AS STRING)
FROM housing.gold.ta__quarter;

-- Latest snapshot of every metric for one TA — the agent's typical query
SELECT * FROM housing.gold.ta__month
WHERE ta_name = 'Wellington City'
ORDER BY date DESC LIMIT 5;

-- 25-year affordability trend for Auckland
SELECT quarter_label, mortgage_affordability_index, median_to_median_ratio
FROM housing.gold.ta__quarter
WHERE ta_name = 'Auckland'
ORDER BY quarter;
```

## Known caveats (for Genie / agent instructions)

- **Sparse rows** in `ta__month`. A given (TA, date) row may have only some columns populated — MSD rows almost always have `housing_register` but no `current_hpi`; Sales snapshot rows have prices but no MSD. For "current state per TA", `ORDER BY date DESC LIMIT 1` is the canonical pattern.
- **Auckland is one TA.** Post-supercity amalgamation. Every SA2 in Auckland Region joins to the same `ta__month` / `ta__quarter` row. Document this if Genie asks "median price in Onehunga" — the answer is TA-grained, not suburb-grained.
- **Two TAs have data gaps**: Wairoa District has affordability data but no Sales snapshots (low transaction volume); "Area Outside Territorial Authority" has neither (Stats NZ placeholder for offshore SA2s).

## Migration from prior schema

The previous gold layer split HUD's data across four tables (`housing_indicator__month__ta`, `house_price__month__ta`, `rent_price__month__ta`, `affordability__quarter__ta`). Those have been retired in favour of the two-table convention above. If you have old references anywhere:

```sql
-- One-time cleanup
DROP TABLE IF EXISTS housing.gold.housing_indicator__month__ta;
DROP TABLE IF EXISTS housing.gold.house_price__month__ta;
DROP TABLE IF EXISTS housing.gold.rent_price__month__ta;
DROP TABLE IF EXISTS housing.gold.affordability__quarter__ta;
```

## Relationship to census_2023

[`pipelines/census_2023`](../census_2023/) ingests **SA2-level** 2023 Census metrics from Stats NZ ArcGIS and enriches `housing.gold.suburb` via `housing.silver.census_sa2_features`. This bundle (HUD) remains the source for **territorial-authority** housing-market indicators plus **TA-level** census summaries (themes `Census Tenure`, `Census Crowding`, `Census Housing Deprivation`, `Rent Proportion`).

| Question grain | Use |
|----------------|-----|
| Suburb / SA2 demographics | `housing.gold.suburb`, `housing.gold.income__year__suburb`, other `*__year__suburb` census marts |
| TA affordability (quarterly, 25-year back to 2001) | `housing.gold.ta__quarter` |
| TA sales / rent / MSD (monthly) | `housing.gold.ta__month` |
| TA-level HUD census themes (Tenure, Crowding, Housing Deprivation, Rent Proportion) | `housing.silver.housing_indicator` (long-format, filter `theme IN ('Census Tenure', ...)`) — not pivoted into gold because the SA2 census marts now cover the same questions at finer grain. |

Median household income at SA2 is **not** in HUD; use census marts. HUD uses income only inside affordability ratios.

## Coming next

- **Automated URL fetch.** HUD's download URL is predictable (`/assets/Uploads/Documents/LHS-data-download-<Month>-<Year>.xlsx`). If `hud.govt.nz` doesn't Cloudflare-block Databricks egress (RBNZ does, HUD probably doesn't), this becomes one of the few NZ open-data sources we can poll automatically.
- **More pivoted views as need emerges.** MSD (housing register) — easy follow-up; census tenure/crowding at TA are largely superseded by SA2 census marts for suburb questions.
- **REINZ Monthly Property Report PDF parser** → adds TA-level median sale price columns to `ta__month` from REINZ direct (currently HUD relays this with a lag).
- **Trade Me Property Price Index** as an alternative TA-level rent source.
