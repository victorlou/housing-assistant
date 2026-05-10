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
└── marts/                  # gold-layer pipeline that fans in from sources
```

## Conventions

- One pipeline per source.
- Bronze → Silver → Gold layering. Bronze is never edited.
- Prefer SQL over Python for transformations.
- Every pipeline writes only within the UC catalog configured in Terraform (`uc_catalog_name`, default `workspace`) under `bronze` / `silver` / `gold`. Never directly to `<catalog>.app.*`.
- Schedules are defined in `pipeline.yml`, not in code.

## Adding a new source

1. Add an entry to `data/sources.yaml`.
2. Create `pipelines/<source>/` with the bundle config.
3. Land raw files into `<uc_catalog>.bronze.<source>_volume` (see Terraform outputs / Catalog UI).
4. Add bronze parsing → silver conforming → gold materialisation.
5. Update `docs/data-sources.md` with the new source.
6. Update the marts pipeline if a new gold table was created.

## Local development

```bash
cd pipelines/<source>
databricks bundle deploy --target dev
databricks bundle run <pipeline-name> --target dev
```

See `docs/runbook.md` for the full developer workflow.
