# Schedules

Single page that lists every scheduled job in the lakehouse, when it runs, why that cadence, and what it depends on. The crons here are documentation — the source of truth for any cron string is the `schedule:` block in each pipeline's `databricks.yml`. When you change a schedule, update the bundle *and* this doc.

All times are **Pacific/Auckland**.

## At a glance

| Bundle | Job | Cron | Cadence | Pause status | Why this cadence |
|---|---|---|---|---|---|
| [`gtfs`](../pipelines/gtfs/databricks.yml) | `gtfs_ingest` | `0 0 3 ? * SUN` | Weekly, Sun 03:00 | UNPAUSED | NZ regional agencies (AT, Metlink, BUSIT, Metroinfo) republish GTFS roughly weekly around service-change windows. Sunday 03:00 puts the refresh ahead of any consumer that wants fresh transit data on Monday morning. |
| [`linz_nz_addresses`](../pipelines/linz_nz_addresses/databricks.yml) | `linz_nz_addresses_ingest` | `0 0 4 ? * MON` | Weekly, Mon 04:00 | UNPAUSED | LINZ Data Service refreshes the NZ Addresses layer on a rolling basis; weekly polling against content-hash dedup catches updates promptly without much waste. |
| [`places`](../pipelines/places/databricks.yml) | `places_ingest` | `0 0 4 ? JAN,APR,JUL,OCT SUN#1` | Quarterly, first Sun 04:00 | UNPAUSED | SA2 polygons only change with Stats NZ census-boundary revisions (years apart). Census attributes refresh every 5 years. Quarterly polling is generous — most runs hash-skip cleanly. |
| [`prices`](../pipelines/prices/databricks.yml) | `prices_ingest` | `0 0 4 10 * ?` | Monthly, 10th 04:00 | UNPAUSED | RBNZ M10 publishes quarterly HPI ~4 months after the reference quarter. Monthly polling catches the publication day without much waste; the 10th is late enough that publishers have caught up. |
| [`housing_indicators`](../pipelines/housing_indicators/databricks.yml) | `housing_indicators_ingest` | `0 0 4 10 * ?` | Monthly, 10th 04:00 | UNPAUSED | HUD Local Housing Statistics XLSX refreshes monthly. Same 10th-of-the-month rationale as `prices`. |
| [`police_recorded_crime`](../pipelines/police_recorded_crime/databricks.yml) | `police_recorded_crime_ingest` | `0 0 6 1 * ?` | Monthly, 1st 06:00 | **PAUSED** | NZ Police updates the ANZSOC Tableau export monthly; cadence reflects the publisher. Paused until the manual CSV-upload workflow is validated end-to-end. |
| [`census_2023`](../pipelines/census_2023/databricks.yml) | `census_2023_ingest` | `0 0 5 1 3 ?` | Annual, 5 Mar 04:00 | **PAUSED** | Census 2023 is a static snapshot. Annual cron is a placeholder for the next census; current cadence is "run on demand after deploy". |
| [`flood`](../pipelines/flood/databricks.yml) | `flood_ingest` | `0 0 4 1 6 ?` | Annual, 1 Jun 04:00 | **PAUSED** | Regional flood-hazard polygons change rarely (council plan revisions, post-event remapping). Paused until the 12 regional fetches are validated. |

Manual local-compute scripts (no schedule):

| Script | Cadence in practice | Why local |
|---|---|---|
| [`pipelines/amenities/local/compute_amenities.py`](../pipelines/amenities/local/compute_amenities.py) | Re-run on demand, roughly quarterly | Needs `osmium` + ~5 GB NZ OSM extract. Refreshes `housing.gold.amenity__h3`. OSM amenity data drifts slowly. |
| [`pipelines/isochrone/local/compute_isochrones.py`](../pipelines/isochrone/local/compute_isochrones.py) | Re-run on demand, roughly quarterly or whenever GTFS feeds materially change | Needs JDK 21 + r5py (Databricks Serverless can't install JDK 21 via init scripts). Refreshes `housing.gold.isochrone`. |

## What fires on a typical week

Active (UNPAUSED) jobs only:

```
Sunday    03:00  gtfs_ingest                                    (every week)
Monday    04:00  linz_nz_addresses_ingest                       (every week)
Sunday    04:00  places_ingest                                  (first Sunday of Jan/Apr/Jul/Oct only)
10th      04:00  prices_ingest + housing_indicators_ingest      (whichever weekday the 10th lands on)
```

Currently **paused** (manual / on-demand only): `census_2023_ingest`, `flood_ingest`, `police_recorded_crime_ingest`. Un-pause each one only after its end-to-end workflow has been validated; see the pipeline README for the manual-run command.

Concurrency note: `prices_ingest` and `housing_indicators_ingest` both fire at 04:00 on the 10th. They use independent DLT pipelines and volumes, so concurrent execution is fine; the only side effect is that any failure email arrives in a pair. Stagger to 04:00 and 04:30 if you want crisper separation.

## Why cron, not file-arrival triggers

Every scheduled job follows a "fetch (hash-skip if nothing changed) → bronze → silver → gold" shape (`police_recorded_crime` skips the fetch step — landings are uploaded manually). Cron + hash-skip is simpler than wiring file-arrival triggers for sources we don't control:

- We don't get a webhook when HUD, RBNZ, or Stats NZ publishes. We'd be polling anyway.
- The fetch step writes to `housing.bronze.<source>.ingest_runs` with a `status` column (`new`, `unchanged`, `skipped`) so missed runs and dud uploads are diagnosable without inspecting the file system.
- The first downstream task uses `run_if: ALL_DONE`, so a single failing fetch (e.g. one agency's GTFS endpoint is briefly down) doesn't block the rest.

## Cross-pipeline dependencies

Most bundles are independent — they don't consume another's gold tables in their own pipeline. Three real dependencies exist:

- **`places_gold` reads `housing.silver.census_sa2_features`** (produced by `census_2023_silver`). Order matters: run `census_2023_ingest` before refreshing `places_gold` if you want fresh census demographics on `gold.suburb`. If `census_sa2_features` is missing entirely, `places_gold` materialises `gold.suburb` with null census columns.
- **`compute_amenities.py` (local)** reads `housing.gold.h3_cell` (from `places_gold`) to stamp `suburb_id` onto each amenity. Re-run after `places_ingest` if SA2 polygons changed.
- **`compute_isochrones.py` (local)** reads `housing.gold.transit_stop` (from `gtfs_gold`) for its origin/destination cell set, and pulls each region's latest GTFS zip from `bronze.gtfs_files._zip/<feed>/`. After a GTFS refresh that changes the stop set, isochrones are stale until manually re-run.

If we ever automate either local script, the natural trigger is "on completion of `gtfs_ingest`" via the Databricks Jobs API (run_job_task), not cron. Until then, the manual cadence is fine — the underlying data (OSM road network, GTFS schedules, OSM amenities) doesn't shift fast enough to justify automation lift.

## Identity and notifications

Every scheduled job runs as the `sp-housing-jobs` service principal (`jobs_service_principal_id` in each bundle). Failure emails go to the value of `notification_email` in each bundle's `targets.dev` block — currently a mix of `victor.lourenco@zuru.com` (most bundles) and `isabelbody@zuru.com` (`police_recorded_crime`). When more people join the project, switch each bundle to a shared group email; don't list individuals.

## Changing a schedule

1. Edit the `schedule.quartz_cron_expression` in the bundle's `databricks.yml`.
2. Update the corresponding row in [the at-a-glance table above](#at-a-glance).
3. `databricks bundle deploy --target dev` from the pipeline's folder.
4. Confirm in the Databricks UI under Workflows → the renamed job → Schedule tab.

Quartz cron is **not** Unix cron. The cheat sheet:

```
quartz_cron_expression: "sec min hr day-of-month month day-of-week year?"
                         0   0   4   10           *     ?           (?-year optional)
```

The day-of-month / day-of-week slot must have exactly one of the two as `?` (Quartz treats them as mutually exclusive). `SUN#1` means "the first Sunday of the month"; `0 0 3 ? * SUN` means "every Sunday at 03:00".

## Related docs

- [`runbook.md`](runbook.md) — how to deploy bundles, rotate credentials, troubleshoot a failing run.
- [`conventions.md`](conventions.md) — gold-table naming and column conventions (what each scheduled job produces).
- [`architecture.md`](architecture.md) — overall lakehouse shape, where these jobs sit in the data flow.
