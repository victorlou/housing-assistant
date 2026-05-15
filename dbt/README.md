# dbt — medallion (bronze, silver, gold)

This project follows a **three-layer medallion** layout under `models/bronze/`, `models/silver/`, and `models/gold/`.

- **Physical UC bronze** tables are still produced only by **ingest jobs and DLT**. dbt declares them as `source()` in `models/bronze/sources.yml`.
- **`models/bronze/*.sql`** holds **ephemeral** models: typed cleanup over those sources. They do **not** create relations in `housing.bronze`, so there is no second writer to the bronze schema.
- **`models/silver/`** and **`models/gold/`** materialise to Unity Catalog schemas **`silver`** and **`gold`** (see `macros/generate_schema_name.sql`).

## Prerequisites

- Python 3.11+ (see root [`docs/runbook.md`](../docs/runbook.md))
- `pip install -r ../requirements-dbt.txt`
- Databricks SQL warehouse HTTP path and a PAT (or OAuth per adapter docs)

## Setup

1. Copy [`profiles.yml.example`](profiles.yml.example) to `~/.dbt/profiles.yml` (or merge the `housing_assistant` profile).
2. Export `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`, and optionally `DBT_UC_CATALOG` (default `housing`).
3. Confirm bronze relation names in UC match [`models/bronze/sources.yml`](models/bronze/sources.yml). DLT output names can differ from `linz_nz_addresses_features`; update the YAML if needed.
4. From this directory:

```bash
dbt deps    # no packages by default; safe to run
dbt debug
dbt run --select linz_nz_addresses+
dbt test --select linz_nz_addresses+
```

## Catalog override

```bash
dbt run --vars '{"uc_catalog": "workspace"}'
```

## Layout

```
models/
├── bronze/     # ephemeral: source → cleanup (no UC bronze writes)
├── silver/     # conformed tables in schema silver
└── gold/       # marts / dims in schema gold
```

## Bronze column contract

[`bronze/linz_nz_addresses.sql`](bronze/linz_nz_addresses.sql) expects columns on `housing.bronze.linz_nz_addresses_features`, including at least:

`address_id`, `change_id`, `lifecycle_phase`, `full_address_ascii`, `suburb_locality_ascii`, `town_city_ascii`, `territorial_authority_ascii`, `latitude`, `longitude`

If your bronze table uses different names, adjust that file accordingly.

## Follow-up work (track as GitHub issues)

Parent context: [issue #5 — dbt in-repo for silver and gold](https://github.com/victorlou/housing-assistant/issues/5).

Suggested follow-ups (file separately and link them from #5 or a milestone):

1. **Orchestration** — Databricks Job or bundle task running `dbt run` on a schedule after bronze refreshes; run-as aligned with the jobs service principal in Terraform.
2. **Gold marts** — Implement each mart from `docs/architecture.md` (`suburb`, `school`, `hazard`, `isochrone`, rent/income/crime/HPI facts) as its own issue once sources exist in bronze.
3. **`silver.place_lookup`** — Choose seed in repo vs external curated table vs pipeline; document in `docs/data-sources.md` and model in dbt.
