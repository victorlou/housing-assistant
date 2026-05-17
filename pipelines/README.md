# Pipelines

Lakeflow Declarative Pipelines that move open NZ data from raw landings into the lakehouse.

## Layout

```
pipelines/
├── flood/                  # regional flood hazard ArcGIS → gold.hazard (H3)
├── gtfs/                   # NZ transit feeds
├── census_2023/            # Stats NZ census SA2
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
- Every pipeline writes to `housing.bronze.*` / `housing.silver.*` / `housing.gold.*` only. Never directly to `housing.app.*`.
- Schedules are defined in `pipeline.yml`, not in code.

## Adding a new source

1. Create `pipelines/<source>/` with the bundle config.
2. Land raw files into the `housing.bronze.<source>_files` volume.
3. Add bronze parsing → silver conforming → gold materialisation.
4. Update `docs/data-sources.md` with the new source.
5. Update the marts pipeline if a new gold table was created.

## Local development

```bash
cd pipelines/<source>
databricks bundle deploy --target dev
databricks bundle run <pipeline-name> --target dev
```

See `docs/runbook.md` for the full developer workflow.
