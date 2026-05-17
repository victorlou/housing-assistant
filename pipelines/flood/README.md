# flood

Annual fetch of regional flood hazard polygon layers (Auckland Council, GWRC, councils) followed by bronze → silver → gold transformations.

Silver/gold distinguish layers via `hazard_source` (parallel to GTFS `_feed_source`).

## How it works

The bundle defines one **job** with parallel fetches plus three **pipelines**.

### Tasks 1–12: parallel fetches per layer

`notebooks/fetch.py` runs once per row in [`regions.yaml`](regions.yaml). Each task:

1. Pages the ArcGIS MapServer/FeatureServer (`f=json`, geometry included).
2. Hashes the JSONL bytes and compares against the last successful run for that layer. If unchanged, logs `status='skipped'` and exits.
3. Otherwise writes to `/Volumes/housing/bronze/flood_files/<file_stem>/<date>/features.jsonl`.
4. Prunes landings for **this layer** older than `retention_days` (default 365).
5. Logs to `housing.bronze.ingest_runs` as `source = 'flood_<hazard_source>'`.

### Transforms

- `transform_bronze` — `run_if: ALL_DONE` after all fetches; streams JSONL into `housing.bronze.flood_hazard_feature`.
- `transform_silver` — `flood_hazard_zone` (polygons) and `flood_hazard_h3` (H3 res-8 cells).
- `transform_gold` — `housing.gold.hazard` boolean flags per H3 cell.

## Schedule

- **Cron:** 4 June 04:00 Pacific/Auckland (annual).
- **Default:** `PAUSED` — run on demand until validated.

## Deploy

```bash
cd pipelines/flood
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

Apply Terraform for `flood_files` volume before first fetch (or `CREATE VOLUME IF NOT EXISTS housing.bronze.flood_files` in dev):

```bash
cd terraform/envs/dev
terraform apply
```

## Run on demand

```bash
databricks bundle run flood_ingest --target dev
```

## Verify

```sql
SELECT source, status, content_hash, bytes_written, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'flood_%'
ORDER BY fetched_at DESC;

SELECT _hazard_source, COUNT(*) FROM housing.bronze.flood_hazard_feature GROUP BY 1;

SELECT COUNT(*), SUM(CAST(in_flood_plain AS INT)) FROM housing.gold.hazard;
```

## Research

Layer discovery and Auckland API notes: [`.devnotes/flood/`](../../.devnotes/flood/).
