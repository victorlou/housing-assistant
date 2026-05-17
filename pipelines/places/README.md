# places

Canonical place dimension for the housing lakehouse — Stats NZ Statistical Area 2 (2023) polygons mapped to H3 cells, with a `suburb_name`/`territorial_authority`/`region` lookup. Powers any "where is this property", "what's this suburb like", or "show me suburbs that..." question from Genie, the agent, and the consumer view.

Source: **Stats NZ DataFinder** (Koordinates platform, same family as LINZ Data Service). Currently one dataset:

- `sa2_polygons` — "Statistical Area 2 Higher Geographies 2023 (generalised)", [layer 111218](https://datafinder.stats.govt.nz/layer/111218-statistical-area-2-higher-geographies-2023-generalised/), via WFS as GeoJSON in WGS84. Same SA2 polygons as the bare 111227 layer but pre-joined with parent territorial authority + region attributes, so silver doesn't need a separate spatial join.
- `sa2_census` — Stats NZ 2023 Census aggregates per SA2 (downloaded manually as CSV from DataFinder, e.g. [layer 120897](https://datafinder.stats.govt.nz/layer/120897-2023-census-totals-by-topic-for-individuals-by-statistical-area-2-part-1/)). Wide source format with hundreds of columns; silver projects just `population_2023` and `median_age_2023`. Refreshes 5-yearly so manual upload is fine.

2023 Census demographics are joined from `housing.silver.census_sa2_features` (produced by [`pipelines/census_2023`](../census_2023/)). Run `census_2023_ingest` before refreshing places gold.

## Contract — gold tables

Two tables form the public surface. Consumers (Genie, the agent, the consumer view) join here; the rest of the pipeline can be replumbed underneath without touching them.

### `housing.gold.suburb`

One row per SA2.

```sql
CREATE TABLE housing.gold.suburb (
  suburb_id              STRING NOT NULL,    -- Stats NZ SA2 2023 code (6 digits)
  suburb_name            STRING NOT NULL,    -- "Onehunga West"
  territorial_authority  STRING,             -- "Auckland"
  region                 STRING,             -- "Auckland Region"
  centroid_h3            BIGINT,             -- res-8 cell at polygon centroid
  land_area_km2          DOUBLE,             -- Stats NZ LAND_AREA_SQ_KM (excludes water)
  population_2023        INT,                -- 2023 Census usual residents
  median_age_2023        DOUBLE,             -- 2023 Census median age
  median_household_income_2023 DOUBLE,       -- from census_2023
  household_count_2023   INT,
  owner_occupier_pct_2023 DOUBLE,
  median_weekly_rent_2023 DOUBLE,
  percent_crowded_2023   DOUBLE,
  geometry               BINARY,             -- WKB for downstream spatial queries
  _updated_at            TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (region);
```

We keep the dim name `suburb` even though the grain is SA2. The shape and the language consumers use (suburb name, TA, region) are what matter; `suburb_id` happens to be the SA2 code.

### `housing.gold.h3_cell`

One row per H3 cell at resolution 8. The workhorse — every fact (transit_stop, isochrone, future listings/sales) joins here on `h3_cell`, then `h3_cell.suburb_id → gold.suburb` is a flat lookup.

```sql
CREATE TABLE housing.gold.h3_cell (
  h3_cell      BIGINT NOT NULL,     -- res-8 cell (logical PK)
  suburb_id    STRING,               -- FK to gold.suburb;
                                     -- null for cells outside any SA2 (water, EEZ)
  _updated_at  TIMESTAMP NOT NULL
)
USING DELTA;
```

**Boundary tie-breaking.** An H3 cell on an SA2 boundary intersects multiple polygons. We assign the cell to the SA2 with the largest intersection area (window over `ST_Intersection` of the cell boundary and each candidate polygon). Built into `gold.py`.

## How it works

```
fetch_sa2_polygons  →  transform_bronze  →  transform_silver  →  transform_gold
   (notebook)          (DLT pipeline)        (DLT pipeline)        (DLT pipeline)
```

### Task 1: `fetch_sa2_polygons`

`notebooks/fetch.py` downloads the SA2 GeoJSON from Stats NZ DataFinder WFS (layer 111227, `srsName=EPSG:4326`), and lands two files under `/Volumes/housing/bronze/places_files/`:

- `_geojson/sa2_polygons/<date>.geojson` — raw audit copy.
- `sa2_polygons/<date>.jsonl` — one feature per line, Auto-Loader friendly.

Auth: the Stats NZ API key is read from the `housing-assistant` secret scope and substituted into the URL's `{api_key}` placeholder (Koordinates style). If the key isn't configured yet, the task logs `status='skipped'` and exits cleanly so downstream pipelines aren't blocked.

Hash-dedup is via `housing.bronze.ingest_runs` (`source = 'places_sa2_polygons'`). Same shape as the GTFS fetch.

### Task 2: `transform_bronze` (pipeline)

`notebooks/bronze.py` defines `places_sa2_polygon_raw` — a streaming Auto Loader table over the JSONL files, attaching `_source = 'stats_nz'`, `_run_date`, `_ingested_at`, `_source_file`.

### Task 3: `transform_silver` (pipeline)

`notebooks/silver.py` produces `housing.silver.sa2_polygon`: one row per SA2 with code, name, TA, region, raw GeoJSON geometry kept as string, and a WKB binary form for spatial work. Projected from `properties.SA22023_V1_00*` fields. Expectations drop rows missing geometry or `sa2_code`.

### Task 4: `transform_gold` (pipeline)

`notebooks/gold.py` materialises the two gold contract tables:

- `suburb` — projected from `silver.sa2_polygon`, with `centroid_h3` from `h3_pointash3(st_centroid(...))` and `area_km2` from `st_area / 1e6`. Demographic columns left null.
- `h3_cell` — `h3_polyfillash3(geometry, 8)` exploded, then a row-number window picks the largest-overlap SA2 per cell.

## Identity model

- **Job runs as:** `sp-housing-jobs`.
- **Pipelines run as:** same SP. Tables owned by the SP, not the deployer.
- **Compute:** serverless for the fetch task and all three DLT pipelines.
- **Failure alerts:** email to the address configured in `databricks.yml`.

## Schedule

- **Cron:** first Sunday of each quarter, 04:00 Pacific/Auckland. SA2 polygons refresh annually at most — daily would just hash-skip.

## Deploy

```bash
cd pipelines/places
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

## Run on demand

```bash
databricks bundle run places_ingest --target dev
```

## Verify

```sql
-- Latest fetch attempt
SELECT source, status, content_hash, file_count, bytes_written, notes, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'places_%' ORDER BY fetched_at DESC LIMIT 5;

-- Suburb count by region (~2,395 SA2s nationally)
SELECT region, COUNT(*) AS suburbs
FROM housing.gold.suburb
GROUP BY region ORDER BY suburbs DESC;

-- Every Auckland transit stop now resolves to a suburb
SELECT s.feed_source, COUNT(*) AS stops_with_suburb
FROM housing.gold.transit_stop s
JOIN housing.gold.h3_cell c USING (h3_cell)
WHERE c.suburb_id IS NOT NULL
GROUP BY s.feed_source;

-- Cells with no suburb (sanity — should be water/EEZ only, expect 0 for AKL stops)
SELECT COUNT(*) FROM housing.gold.h3_cell WHERE suburb_id IS NULL;

-- Census enrichment on suburb (after census_2023_ingest + places gold refresh)
SELECT COUNT(*) AS suburbs,
       COUNT(population_2023) AS with_pop,
       COUNT(median_age_2023) AS with_age,
       COUNT(median_household_income_2023) AS with_income
FROM housing.gold.suburb;

-- Top 10 most populous suburbs nationally
SELECT suburb_name, territorial_authority, population_2023, median_age_2023
FROM housing.gold.suburb
WHERE population_2023 IS NOT NULL
ORDER BY population_2023 DESC
LIMIT 10;
```

## Setup before first run

### Get a Stats NZ DataFinder API key

DataFinder uses Koordinates' standard auth — same as LINZ. Free signup:

1. Register at [datafinder.stats.govt.nz](https://datafinder.stats.govt.nz/) (or sign in if you already have an account).
2. Visit **My DataFinder → APIs** and create a new key. Read-only access is fine.
3. Store it in the project secret scope:

```bash
databricks --profile hackathon secrets put-secret housing-assistant stats_nz_api_key
# paste the key when prompted
```

The bundle picks it up via the `auth_secret_key = "stats_nz_api_key"` parameter in `databricks.yml`. Until this is configured, `fetch_sa2_polygons` logs `status='skipped'` and exits cleanly.

### Upload the SA2 census CSV (one-time, refresh every 5 years)

Census data isn't on the Koordinates WFS API like the polygons — it sits behind a per-table CSV export on DataFinder. Since the data refreshes every 5 years anyway, manual upload is the simpler path:

1. Open [DataFinder layer 120897](https://datafinder.stats.govt.nz/layer/120897-2023-census-totals-by-topic-for-individuals-by-statistical-area-2-part-1/) (2023 Census totals by topic for individuals by SA2 — part 1) in a browser. Use the **Download** button to grab the table as CSV. Part 2 ([layer 120898](https://datafinder.stats.govt.nz/layer/120898-2023-census-totals-by-topic-for-individuals-by-statistical-area-2-part-2/)) has additional columns; for the population + median age we use today, part 1 alone is enough.
2. Upload it to the bronze volume with today's date as the filename:

   ```bash
   # First-time only: create the directory.
   databricks --profile hackathon fs mkdirs \
     dbfs:/Volumes/housing/bronze/places_files/sa2_census

   # Every refresh:
   today=$(date +%Y-%m-%d)
   databricks --profile hackathon fs cp \
     ~/Downloads/<the-census-csv>.csv \
     "dbfs:/Volumes/housing/bronze/places_files/sa2_census/${today}.csv"
   ```

3. On the next pipeline run, `fetch_sa2_census` validates + hashes the CSV, bronze streams it via Auto Loader, and silver/gold join it into `housing.gold.suburb`.

## What's still TODO

The notebooks are wired up but a few things need verifying or following up:

- **Stats NZ DataFinder API key** in the `housing-assistant` secret scope (see [Setup before first run](#setup-before-first-run)).
- **SA2 polygon property names** in `silver.py` (`SA22023_V1_00`, `SA22023_V1_00_NAME`, `TA2023_V1_00*`, `REGC2023_V1_00*`, `LAND_AREA_SQ_KM`). Verify against `housing.bronze.places_sa2_polygon_raw` with `DESCRIBE`; the `properties` struct should show all of these as nested fields. If any are absent on layer 111218 the SELECT in `silver.py` is the one place to fix.
- **Census enrichment.** After [`pipelines/census_2023`](../census_2023/) ingest, run `places_ingest` (or refresh the `places_gold` pipeline) so `gold.suburb` picks up `census_sa2_features`. If census silver is missing, demographic columns stay null.

## Volume migration note

If you've already deployed the old LINZ-targeted bundle, the bronze volume rename `linz_files` → `places_files` is destructive in Terraform: the old volume gets dropped and a new one created. Any landings under `/Volumes/housing/bronze/linz_files/` are lost — those were the layer-50280 points anyway, all data quality wrong. Run `terraform apply` from `terraform/envs/dev` to perform the swap.

## Layer-swap cleanup (if you ran against 111227 first)

A prior iteration targeted layer 111227 (bare SA2 polygons, no TA/region attributes). If you ran the pipeline once against that and now need to swap to 111218, clean up first so Auto Loader doesn't merge schemas across layers:

```bash
# Drop the bronze raw table — silver/gold will rebuild on next run.
databricks --profile hackathon sql --query "DROP TABLE IF EXISTS housing.bronze.places_sa2_polygon_raw"

# Wipe the volume landings so the fetch isn't hash-skipped.
databricks --profile hackathon fs rm -r dbfs:/Volumes/housing/bronze/places_files/_geojson/sa2_polygons/
databricks --profile hackathon fs rm -r dbfs:/Volumes/housing/bronze/places_files/sa2_polygons/

# Then in the UI: `places_bronze` pipeline → Settings → Full refresh.
# That resets Auto Loader's checkpoint so it reads from scratch.
```

After this, `databricks bundle run places_ingest --target dev` does a clean fetch from layer 111218.

## Coming next

- **Census:** additional 2023 topics can be added via `pipelines/census_2023/census_2023_gold.yml` without changing the suburb contract shape.
- **School zones:** Ministry of Education school catchment polygons → new `gold.school_zone` dim plus a `gold.h3_cell__school_zone` bridge (cells can sit in multiple zones simultaneously — primary, intermediate, secondary — so a single FK column on h3_cell won't do).
- **Amenities:** supermarkets, hospitals, employment centres. Gives Genie destinations beyond pre-defined transit origin centres.
- **Address-level lookup:** LINZ NZ Addresses in [`pipelines/linz_nz_addresses`](../linz_nz_addresses/) (`linz_nz_addresses_files` volume). Useful for the "is this listing near a bus stop" question.
