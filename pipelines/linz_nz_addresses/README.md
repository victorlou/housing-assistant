# LINZ NZ Addresses

## Ingest job (Databricks)

`notebooks/fetch.py` runs on a schedule and mirrors the GTFS Auckland Transport pattern:

1. Pages LINZ LDS WFS (NZ Addresses layer) into a temp JSONL file on the driver.
2. Computes `content_hash` (SHA-256 of the JSONL bytes). If it matches the last successful run, logs `skipped` to `housing.bronze.ingest_runs` and does not publish a new landing.
3. Otherwise moves the file to `/Volumes/housing/bronze/linz_nz_addresses_files/nz_addresses/YYYY-MM-DD/linz_nz_addresses.jsonl` (same `housing` catalog convention as GTFS).
4. Deletes date-stamped landing folders older than the retention window (default 90 days).
5. Logs every run to `housing.bronze.ingest_runs`.

**API key:** Prefer Databricks secrets (`auth_secret_scope` + `auth_secret_key` widgets). If `auth_secret_scope` is empty, the job uses the `LINZ_API_KEY` environment variable on the compute (set via job/cluster env if not using secrets).

WFS layer and paging defaults live in `notebooks/fetch.py` (aligned with `linz_nz_addresses.yml` for local CLI). Job `base_parameters` are `feed_source`, `retention_days`, `auth_secret_scope`, and `auth_secret_key`, like the GTFS fetch tasks.

## Lakeflow pipeline (DLT)

The bundle defines three DLT pipelines (bronze → silver → gold), matching `pipelines/gtfs/notebooks`:

- **Bronze** (`notebooks/bronze.py`): Auto Loader over `**/*.jsonl` → `linz_nz_addresses_raw`, `linz_nz_addresses`.
- **Silver** (`notebooks/silver.py`): `housing.silver.nz_address` (typed coords + H3).
- **Gold** (`notebooks/gold.py`): `housing.gold.nz_address` (current lifecycle only, Genie-ready).

If your Terraform `catalog_name` is not `housing`, update `BRONZE_VOLUME` in `notebooks/fetch.py` and the volume path in `notebooks/bronze.py` together.

## Local fetch (optional)

For ad-hoc runs from your laptop:

```bash
cd pipelines/linz_nz_addresses
set LINZ_API_KEY=...
python notebooks/linz_fetch_wfs.py --output ./out
```

Config defaults live in `linz_nz_addresses.yml` (`${LINZ_API_KEY}` expansion for that path only).

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
WHERE source LIKE 'linz_nz_addresses%'
ORDER BY fetched_at DESC
LIMIT 10;
```

```sql
LIST '/Volumes/housing/bronze/linz_nz_addresses_files/nz_addresses/';
```

API reference: [LINZ Data Service](https://data.linz.govt.nz/).
