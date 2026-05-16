# LINZ NZ Addresses

## Ingest job (Databricks)

`notebooks/fetch.py` runs on a schedule and mirrors the GTFS Auckland Transport pattern:

1. Pages LINZ LDS WFS (NZ Addresses layer) into a temp JSONL file on the driver.
2. Computes `content_hash` (SHA-256 of the JSONL bytes). If it matches the last successful run, logs `skipped` to `housing.bronze.ingest_runs` and does not publish a new landing.
3. Otherwise moves the file to `/Volumes/housing/bronze/addresses_files/linz_nz_addresses/YYYY-MM-DD/linz_nz_addresses.jsonl` (same `housing` catalog convention as GTFS).
4. Deletes date-stamped landing folders older than the retention window (default 90 days).
5. Logs every run to `housing.bronze.ingest_runs`.

**API key:** Prefer Databricks secrets (`secret_scope` + `secret_key` widgets). If `secret_scope` is empty, the job uses the `LINZ_API_KEY` environment variable on the compute (set via job/cluster env if not using secrets).

WFS layer and paging defaults live in `notebooks/fetch.py` (aligned with `config/sources/linz_nz_addresses.yml` for local CLI). Job `base_parameters` are only `retention_days`, `secret_scope`, and `secret_key`, like the small widget surface on the GTFS job.

## Lakeflow pipeline (DLT)

The bundle still defines the DLT pipeline: Auto Loader reads `**/*.jsonl` under `addresses_files/linz_nz_addresses/` and materialises `linz_nz_addresses_raw` and `linz_nz_addresses_features` in the pipeline catalog.

If your Terraform `catalog_name` is not `housing`, update `BRONZE_VOLUME` in `notebooks/fetch.py`, the path in `transformations/bronze.sql`, and `resources.pipelines.linz_nz_addresses.catalog` in `databricks.yml` together.

## Local fetch (optional)

For ad-hoc runs from your laptop:

```bash
set LINZ_API_KEY=...
python -m ingestion.linz_wfs --output ./out
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

API reference: [LINZ Data Service](https://data.linz.govt.nz/).
