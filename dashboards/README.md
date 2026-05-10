# Dashboards

Databricks AI/BI Dashboards. The planner view is built here.

## Layout

```
dashboards/
├── planner/
│   ├── dashboard.lvdash.json   # exported dashboard definition
│   ├── queries/                # SQL queries used by the dashboard
│   └── README.md               # what this dashboard shows, owner
└── cost-monitor/               # internal: spend tracker
```

## Conventions

- Dashboards live in source control as exported JSON, edited in the Databricks UI, then re-exported.
- Companion SQL queries are extracted into `queries/` so they are reviewable and reusable.
- One folder per dashboard.

## Planner dashboard: what it shows

See `docs/personas.md` for the full design. At minimum on demo day:

- National choropleth: rent-to-income ratio by territorial authority, with trend.
- Cliff watch: TAs where rent growth has outpaced income growth by 2+ standard deviations over four quarters.
- Demographic crosscuts: affordability dynamics by household size and age cohort.
- Hazard-overlay map: low-income suburbs in flood / coastal-inundation zones.

## Cost monitor: what it shows

A simple usage report from `system.billing.usage`, filtered to `project = "housing-assistant"`. Useful for tracking spend at a glance.
