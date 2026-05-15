# LINZ NZ Addresses

## Ingest job (Databricks)

`notebooks/fetch.py` runs on a schedule and mirrors the GTFS Auckland Transport pattern:

1. Pages LINZ LDS WFS (NZ Addresses layer) into a temp JSONL file on the driver.
2. Computes `content_hash` (SHA-256 of the JSONL bytes). If it matches the last successful run, logs `skipped` to `housing.bronze.ingest_runs` and does not publish a new landing.
3. Otherwise moves the file to `/Volumes/<catalog>/bronze/addresses_files/linz_nz_addresses/YYYY-MM-DD/linz_nz_addresses.jsonl`.
4. Deletes date-stamped landing folders older than the retention window (default 90 days).
5. Logs every run to `housing.bronze.ingest_runs`.

**API key:** Prefer Databricks secrets (`secret_scope` + `secret_key` widgets). If `secret_scope` is empty, the job uses the `LINZ_API_KEY` environment variable on the compute (set via job/cluster env if not using secrets).

WFS parameters (`type_names`, `page_size`, etc.) are job `base_parameters` in `databricks.yml` (same idea as GTFS `source_url`).

## Lakeflow pipeline (DLT)

The bundle still defines the DLT pipeline: Auto Loader reads `**/*.jsonl` under `addresses_files/linz_nz_addresses/` and materialises `linz_nz_addresses_raw` and `linz_nz_addresses_features` in the pipeline catalog.

If your Terraform `catalog_name` is not `housing`, set the ingest job `catalog` parameter and update the volume path in `transformations/bronze.sql` to match `/Volumes/<your_catalog>/bronze/addresses_files/...`.

## Local fetch (optional)

For ad-hoc runs from your laptop:

```bash
set LINZ_API_KEY=...
uv run python -m ingestion.linz_wfs --output ./out
```

Config defaults live in `config/sources/linz_nz_addresses.yml` (`${LINZ_API_KEY}` expansion for that path only).

## Deploy

```bash
cd pipelines/linz_nz_addresses
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

Run the ingest job once:

```bash
databricks bundle run linz_nz_addresses_ingest --target dev
```

## Verify

```sql
SELECT run_id, status, content_hash, bytes_written, target_path, notes, error_message
FROM housing.bronze.ingest_runs
WHERE source = 'linz_nz_addresses'
ORDER BY fetched_at DESC
LIMIT 10;
```

```sql
LIST '/Volumes/housing/bronze/addresses_files/linz_nz_addresses/';
```

See also [`.devnotes/linz-lds-apis.md`](../../.devnotes/linz-lds-apis.md).
