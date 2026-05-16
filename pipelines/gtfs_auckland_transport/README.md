# gtfs

Weekly fetch of New Zealand GTFS feeds (Auckland Transport, Metlink/Wellington, BUSIT/Waikato, Metroinfo/Christchurch) followed by bronze → silver → gold transformations.

> The folder name (`pipelines/gtfs_auckland_transport/`) is historical: this started as Auckland-only and now covers four feeds. The bundle name (`gtfs_auckland_transport`) is kept so the deployed bundle root path stays stable. Workspace resources (job, pipelines) are renamed to drop the misleading suffix — see "Migration" below.

## Migration from the Auckland-only setup

Previous deploys created workspace resources with names like `gtfs_auckland_transport_ingest` and `gtfs_auckland_transport_bronze`. The current bundle renames them to `gtfs_ingest`, `gtfs_bronze`, `gtfs_silver`, `gtfs_gold`. On the next `databricks bundle deploy`, DAB will:

1. Delete the old workspace resources (the four with `_auckland_transport_` in their names).
2. Create the renamed resources.

Old job run history and pipeline event history are lost in the rename. Existing data in `housing.bronze.*` / `housing.silver.*` / `housing.gold.*` is unaffected because the table names are unchanged.

## What it does

The bundle defines one **job** with four sequential tasks, plus three **pipelines** the tasks trigger.

### Tasks 1–3: parallel fetches per feed

`notebooks/fetch.py` runs once per feed, in parallel. Each task receives `feed_source` and `source_url` (plus optional auth parameters) and:

1. Downloads the feed's GTFS zip.
2. Hashes the bytes and compares against the last successful run **for that feed**. If unchanged, logs `status='skipped'` and exits.
3. Otherwise, writes the raw zip and extracted `.txt` files to the bronze volume in a file-type-first layout:
   - `/Volumes/housing/bronze/gtfs_files/_zip/<feed>/<date>.zip` (audit)
   - `/Volumes/housing/bronze/gtfs_files/<file_name>/<feed>/<date>.txt`
4. Deletes landings for **this feed** older than `retention_days` (default 90). Other feeds' files are untouched.
5. Logs the run to `housing.bronze.ingest_runs` either way, namespaced as `source = 'gtfs_<feed_source>'`.

Currently configured feeds:

| Feed | Region | URL | Auth | Status |
|---|---|---|---|---|
| `auckland_transport` | Auckland | `https://gtfs.at.govt.nz/gtfs.zip` | none | enabled |
| `metlink` | Wellington | `https://static.opendata.metlink.org.nz/v1/gtfs/full.zip` | none | enabled |
| `busit` | Waikato | `https://wrcscheduledata.blob.core.windows.net/wrcgtfs/busit-nz-public.zip` | none | enabled |
| `metroinfo` | Christchurch | `https://apis.metroinfo.co.nz/rti/gtfs/v1/gtfs.zip` | API key required | wired, gracefully skips until secret is set |

### Adding a Metroinfo (Christchurch) API key

When access is granted, store the key as a Databricks secret in the `housing-assistant` scope:

```bash
databricks secrets put-secret \
  --scope housing-assistant \
  --key metroinfo_api_key
# CLI prompts for the value; paste, hit Enter
```

The next scheduled run picks it up automatically. No code change. The `fetch_metroinfo` task reads the secret, sets the `Ocp-Apim-Subscription-Key` HTTP header, and proceeds. Until then the task logs `status='skipped'` with a clear message in `ingest_runs.notes`.

### Why partial-success is OK

The three fetch tasks run in parallel and are independent — one feed failing or being skipped doesn't break the others. `transform_bronze` has `run_if: ALL_DONE`, so it runs once every fetch finishes regardless of outcome. The bronze pipeline only sees whatever files actually landed; silver/gold cascade from there.

### Task 4: `transform_bronze` (pipeline)

`notebooks/bronze.py` defines 13 streaming DLT tables, one per GTFS file (`gtfs_agency`, `gtfs_calendar`, `gtfs_calendar_dates`, `gtfs_fare_attributes`, `gtfs_fare_rules`, `gtfs_feed_info`, `gtfs_frequencies`, `gtfs_routes`, `gtfs_shapes`, `gtfs_stop_times`, `gtfs_stops`, `gtfs_transfers`, `gtfs_trips`). Each loads from `/Volumes/housing/bronze/gtfs_files/<file_name>/`, picking up `<feed>/<date>.txt` files from every configured feed.

Provenance columns added on every row: `_feed_source`, `_run_date`, `_ingested_at`, `_source_file`.

Schema evolution is `addNewColumns`, so feeds with feed-specific optional columns (e.g. Auckland's `contract_id`, Metlink's `etm_id`) all land cleanly with NULL where a column doesn't exist in a particular feed.

### Task 5: `transform_silver` (pipeline)

`notebooks/silver.py` produces conformed entities in `housing.silver`:

- `transit_stop` — typed coordinates, H3 cell at resolution 8. DLT expectations drop rows missing coordinates and warn on out-of-range NZ latitudes/longitudes.
- `transit_route` — routes joined with agency name, plus a readable `route_type_label` ("bus", "ferry", "rail", etc.).
- `transit_service_day` — `calendar.txt` weekday rules expanded into one row per (service_id, date), with `calendar_dates.txt` overrides applied.

`stop_times` is deliberately not in silver yet. It's the heaviest file and the right shape depends on what gold/isochrone needs.

### Task 6: `transform_gold` (pipeline)

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
