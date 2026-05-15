# Pipelines

Lakeflow Declarative Pipelines that move open NZ data from raw landings into the lakehouse.

## Layout

```
pipelines/
├── <source>/
│   ├── databricks.yml      # bundle definition
│   ├── pipeline.yml        # pipeline definition
│   ├── transformations/    # SQL or Python files
│   └── README.md           # what this pipeline does, schedule, owner
└── marts/                  # optional future bundle for orchestration only; silver/gold SQL lives in dbt/
```

## Conventions

- One pipeline per source for **ingest and bronze** (and any DLT that stays in the bundle). **Silver and gold** transformations are maintained in **`dbt/`** (see `dbt/README.md` and `docs/architecture.md`). Do not duplicate silver/gold logic in DLT unless an ADR explicitly moves it.
- Bronze is never edited in place; silver/gold are created or replaced by dbt runs.
- Prefer SQL over Python for transformations where practical.
- Pipelines land data in **bronze** volumes and bronze Delta tables. dbt reads bronze via `source()` and writes only to `housing.silver.*` and `housing.gold.*`. Never write `housing.app.*` from pipelines or dbt without an explicit design.
- Schedules are defined in `pipeline.yml`, not in code.

## Adding a new source

1. Add an entry to `data/sources.yaml`.
2. Create `pipelines/<source>/` with the bundle config.
3. Land raw files into the `housing.bronze.<source>_files` volume.
4. Add bronze parsing in the source pipeline (DLT or jobs). Add or extend **`dbt/`** models (`source()` → staging → silver → gold) for conforming and marts.
5. Update `docs/data-sources.md` with the new source.
6. If a new gold table is introduced, add or update the corresponding dbt mart and any Genie exposure.

## Local development

```bash
cd pipelines/<source>
databricks bundle deploy --target dev
databricks bundle run <pipeline-name> --target dev
```

See `docs/runbook.md` for the full developer workflow.
