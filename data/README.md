# Data

This folder is **not** for raw data. Raw data lands in Unity Catalog managed volumes.

What lives here is the **canonical source registry** that ingestion pipelines read.

## Layout

```
data/
├── sources.yaml            # canonical source registry, single source of truth
└── README.md
```

## sources.yaml

Every open data source we use is described here. The YAML schema:

```yaml
sources:
  - name: tenancy_bonds
    publisher: MBIE Tenancy Services
    licence: CC-BY-4.0
    url: https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/
    auth: none
    cadence: monthly
    ingestion_pipeline: pipelines/tenancy_bonds
    target_tables:
      - housing.gold.fact_rent_by_suburb_month
    tier: 1
    notes: |
      Published as zipped CSV. Geographic key is suburb at SA2 level.
      Pre-2021 data uses different boundaries; handle separately.
```

The full source list lives in `docs/data-sources.md`. This YAML file is the machine-readable mirror.
