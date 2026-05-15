# gtfs_auckland_transport

Weekly fetch of the Auckland Transport GTFS feed to the lakehouse.

## What it does

`notebooks/fetch.py` runs once a week and:

1. Downloads the GTFS zip from Auckland Transport's published URL.
2. Reads `feed_info.txt` from the zip and checks the `feed_version` against the last successful run. If unchanged, the run is logged as `skipped` and nothing else happens.
3. Otherwise, writes the raw zip and the extracted `.txt` files to `/Volumes/housing/bronze/gtfs_files/auckland_transport/YYYY-MM-DD/`.
4. Deletes any date-stamped landing folders older than the retention window (default 90 days). Audit-trail kept; storage stays bounded.
5. Logs the run to `housing.bronze.ingest_runs` either way.

The downstream Lakeflow pipeline (separate PR) picks up new files via Auto Loader and lands them as Delta tables.

## Schedule and identity

- **Cron:** Sunday 03:00 Pacific/Auckland.
- **Runs as:** `sp-housing-jobs` (the jobs service principal provisioned by Terraform).
- **Compute:** serverless. The notebook only needs `requests` and `pyspark`, both present in the default runtime.
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
