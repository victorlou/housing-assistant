# gtfs_auckland_transport

Weekly fetch of the Auckland Transport GTFS feed to the lakehouse, followed by bronze → silver → gold transformations.

## What it does

The bundle defines one **job** with four sequential tasks, plus three **pipelines** the tasks trigger.

### Task 1: `fetch` (notebook)

`notebooks/fetch.py` runs the download:

1. Downloads the GTFS zip from Auckland Transport's published URL.
2. Hashes the bytes and compares against the last successful run. If unchanged, logs `status='skipped'` and exits.
3. Otherwise, writes the raw zip and the extracted `.txt` files to `/Volumes/housing/bronze/gtfs_files/auckland_transport/YYYY-MM-DD/`.
4. Deletes any date-stamped landing folders older than `retention_days` (default 90).
5. Logs the run to `housing.bronze.ingest_runs` either way.

### Task 2: `transform_bronze` (pipeline)

`notebooks/bronze.py` defines 13 streaming DLT tables, one per GTFS file (`gtfs_agency`, `gtfs_calendar`, `gtfs_calendar_dates`, `gtfs_fare_attributes`, `gtfs_fare_rules`, `gtfs_feed_info`, `gtfs_frequencies`, `gtfs_routes`, `gtfs_shapes`, `gtfs_stop_times`, `gtfs_stops`, `gtfs_transfers`, `gtfs_trips`). Each table is fed by Auto Loader with a `pathGlobFilter` that matches its file type across all feed sources, so future feeds (Metlink, ECan) drop into the same tables with a different `_feed_source` value.

Provenance columns added on every row: `_feed_source`, `_run_date`, `_ingested_at`, `_source_file`.

### Task 3: `transform_silver` (pipeline)

`notebooks/silver.py` produces conformed entities in `housing.silver`:

- `transit_stop` — typed coordinates, H3 cell at resolution 8. DLT expectations drop rows missing coordinates and warn on out-of-range NZ latitudes/longitudes.
- `transit_route` — routes joined with agency name, plus a readable `route_type_label` ("bus", "ferry", "rail", etc.).
- `transit_service_day` — `calendar.txt` weekday rules expanded into one row per (service_id, date), with `calendar_dates.txt` overrides applied.

`stop_times` is deliberately not in silver yet. It's the heaviest file and the right shape depends on what gold/isochrone needs.

### Task 4: `transform_gold` (pipeline)

`notebooks/gold.py` produces Genie-ready dimension tables in `housing.gold`:

- `transit_stop` — stops keyed by H3 cell.
- `transit_route` — routes with agency and type label.

The high-value gold table — `isochrone` (origin H3 → reachable H3s by mode and minute bucket) — needs a routing engine like `r5py` and is a separate workstream.

## Schedule and identity

- **Cron:** Sunday 03:00 Pacific/Auckland.
- **Runs as:** `sp-housing-jobs` (the jobs service principal provisioned by Terraform).
- **Compute:** serverless for both the fetch notebook task and all three DLT pipelines.
- **Failure alerts:** email to the address configured in `databricks.yml`.

## Deploy

```bash
cd pipelines/gtfs_auckland_transport
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

Validate inspects the bundle without touching the workspace. Deploy uploads the notebook and creates/updates the job.

## Run on demand

To trigger an off-schedule run (without waiting for Sunday):

```bash
databricks bundle run gtfs_auckland_transport_ingest --target dev
```

You can also click **Run now** on the job in the Workspaces UI.

## Verify

After a run, check the log:

```sql
SELECT
  run_id, status, feed_version, file_count, bytes_written,
  duration_seconds, fetched_at, notes, error_message
FROM housing.bronze.ingest_runs
WHERE source = 'gtfs_auckland_transport'
ORDER BY fetched_at DESC
LIMIT 10;
```

And the bronze tables:

```sql
SELECT _feed_source, COUNT(*) AS rows
FROM housing.bronze.gtfs_stops
GROUP BY _feed_source;
```

And the volume:

```sql
LIST '/Volumes/housing/bronze/gtfs_files/auckland_transport/';
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `403 Forbidden` on download | AT changed the URL | Update `source_url` in `databricks.yml`, redeploy |
| `Permission denied` writing to volume | `sp-housing-jobs` lost `WRITE_VOLUME` | Reapply `terraform/envs/dev` |
| Job runs but never lands files | `feed_version` is the same as last run | Working as designed — confirm via `ingest_runs.status = 'skipped'` |
| `housing.bronze.ingest_runs` not found | First run hasn't created it yet | The notebook creates the table idempotently; trigger a run |

## Configuration

Both parameters live in `databricks.yml` under `base_parameters` and can be overridden per run:

- `source_url` — the GTFS zip URL.
- `retention_days` — how long to keep date-stamped landings. Defaults to 90.
