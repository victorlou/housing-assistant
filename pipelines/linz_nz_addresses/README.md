# LINZ NZ Addresses pipeline

DLT pipeline: JSONL lands on the `linz_nz_addresses` UC volume; the pipeline reads it with Auto Loader and writes **managed Delta** tables in UC (`linz_nz_addresses_raw` keeps one-row-per-feature JSON shape; `linz_nz_addresses_features` flattens GeoJSON properties for typed queries).

There is no separate “Spine” feed here—repo comments mean Spine-style YAML (`${ENV}`) expansion for local fetch config only.

## Land data

Set `LINZ_API_KEY` in `.env`. Tune `config/sources/linz_nz_addresses.yml` if needed, then:

```bash
uv run python -m ingestion.linz_wfs --output ./out
databricks fs cp "./out/linz_nz_addresses_YYYYMMDD.jsonl" "/Volumes/workspace/bronze/linz_nz_addresses/" --profile <name>
```

(`terraform output linz_nz_addresses_files_path` for the exact prefix.)

## Deploy

```bash
cd pipelines/linz_nz_addresses
databricks bundle deploy --target dev
```

If your catalog is not `workspace`, update `transformations/bronze.sql` to match that output.

See [`.devnotes/linz-lds-apis.md`](../../.devnotes/linz-lds-apis.md).
