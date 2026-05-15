# Lakehouse Gold Schema

Column-level definitions for all `housing.gold.*` tables that the agent tools consume. Use this as the contract when writing pipelines, building Genie semantic layers, or implementing tool functions.

> **Test data:** The seed script (`app/app-templates/agent-langgraph-advanced/scripts/generate_test_data.py`) writes synthetic data to `workspace.test.*` — the `workspace` catalog, `test` schema. Never touches `housing.gold.*` in production.

---

## Naming Convention

- **Dimension tables** (stable reference data): entity name only — `suburb`, `school`, `hazard`
- **Fact / aggregated tables** (time-series measures): `<entity>__<time_grain>__<breakdowns>` — `rent__month__suburb`, `income__year__suburb`

---

## Table: `suburb`

Canonical suburb dimension. H3 cells at resolution 8 (~0.75 km² each). One row per `(suburb_name, territorial_authority)` pair.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `suburb_name` | STRING | N | Canonical suburb name (e.g. `"Onehunga"`) |
| `territorial_authority` | STRING | N | Containing TA (e.g. `"Auckland City"`) |
| `region` | STRING | N | Region (e.g. `"Auckland Region"`) |
| `h3_cells` | ARRAY\<STRING\> | N | List of H3 res-8 cell IDs covering the suburb |
| `h3_centroid` | STRING | Y | H3 cell closest to suburb centroid (for isochrone origin) |
| `area_km2` | DOUBLE | Y | Approximate area in km² |
| `population_2021` | INTEGER | Y | Stats NZ 2021 census population |
| `median_age` | DOUBLE | Y | Median age from 2021 census |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(suburb_name, territorial_authority)`

**Sample rows:**

| suburb_name | territorial_authority | region | h3_centroid |
|---|---|---|---|
| Onehunga | Auckland City | Auckland Region | 8928308291bfffff |
| Mt Albert | Auckland City | Auckland Region | 892830808cbffff |
| Sandringham | Auckland City | Auckland Region | 892830808d3ffff |
| Newton | Auckland City | Auckland Region | 89283080dcbffff |
| Glen Eden | Waitākere Ranges | Auckland Region | 8928308065bffff |

---

## Table: `hazard`

Natural hazard risk per H3 res-8 cell. Sourced from LINZ coastal/flood zones and EQC liquefaction maps.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `h3_cell` | STRING | N | H3 res-8 cell ID |
| `flood_risk` | STRING | N | `"low"`, `"medium"`, or `"high"` |
| `coastal_risk` | STRING | N | `"low"`, `"medium"`, or `"high"` |
| `liquefaction_risk` | STRING | N | `"low"`, `"medium"`, or `"high"` |
| `flood_zone_name` | STRING | Y | Source zone label (e.g. `"100yr floodplain"`) |
| `source` | STRING | Y | Data source (e.g. `"LINZ"`, `"Auckland Council"`) |
| `effective_date` | DATE | Y | Date hazard classification was applied |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `h3_cell`

**Used by tool:** `lookup_hazards(suburb)` — joins to `suburb.h3_cells` to aggregate per-suburb risk (worst-case cell wins).

**Aggregation rule:** if any cell in the suburb is `"high"`, return `"high"`; else if any is `"medium"`, return `"medium"`; else `"low"`.

---

## Table: `isochrone`

Pre-computed travel-time reachability. Each row describes which H3 cells are reachable from `h3_origin` via `mode` within `minutes_bucket` minutes. Generated offline from GTFS feeds (transit) and OSRM (drive/walk).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `h3_origin` | STRING | N | Origin H3 res-8 cell |
| `mode` | STRING | N | `"transit"`, `"drive"`, or `"walk"` |
| `minutes_bucket` | INTEGER | N | Upper bound: `10`, `20`, `30`, `45`, or `60` |
| `h3_destinations` | ARRAY\<STRING\> | N | H3 cells reachable within this time bucket |
| `destination_count` | INTEGER | N | `len(h3_destinations)` (pre-computed for fast filtering) |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(h3_origin, mode, minutes_bucket)`

**Partitioned by:** `mode`

**Used by tool:** `compute_isochrone(origin_h3, mode, minutes)` — returns `h3_destinations` for matching `(h3_origin, mode, minutes_bucket >= minutes)`.

**Query pattern:**
```sql
SELECT h3_destinations
FROM housing.gold.isochrone
WHERE h3_origin = :origin_h3
  AND mode = :mode
  AND minutes_bucket = (
    SELECT MIN(minutes_bucket) FROM housing.gold.isochrone
    WHERE h3_origin = :origin_h3 AND mode = :mode AND minutes_bucket >= :minutes
  )
```

---

## Table: `rent__month__suburb`

Monthly median rent by suburb and dwelling type. Sourced from MBIE rental bond data.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `suburb_name` | STRING | N | Canonical suburb name |
| `territorial_authority` | STRING | N | Containing TA |
| `month` | DATE | N | First day of month (e.g. `2024-01-01`) |
| `dwelling_type` | STRING | N | `"all"`, `"house"`, `"apartment"`, or `"townhouse"` |
| `median_rent_weekly` | INTEGER | Y | Median weekly rent in NZD |
| `p25_rent_weekly` | INTEGER | Y | 25th percentile weekly rent |
| `p75_rent_weekly` | INTEGER | Y | 75th percentile weekly rent |
| `sample_size` | INTEGER | Y | Number of bonds in period |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(suburb_name, territorial_authority, month, dwelling_type)`

**Partitioned by:** `month` (year-month)

**Used by tool:** `score_affordability(suburb, household_income)` — fetches `median_rent_weekly` for the most recent month and `dwelling_type = 'all'`.

---

## Table: `income__year__suburb`

Annual household income statistics by suburb. Sourced from Stats NZ census and annual income survey.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `suburb_name` | STRING | N | Canonical suburb name |
| `territorial_authority` | STRING | N | Containing TA |
| `year` | INTEGER | N | Reference year (e.g. `2023`) |
| `median_household_income_annual` | INTEGER | Y | Median annual household income NZD |
| `income_decile` | INTEGER | Y | National income decile 1–10 (1 = lowest) |
| `sample_size` | INTEGER | Y | Number of households in sample |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(suburb_name, territorial_authority, year)`

**Used by tool:** `score_affordability(suburb, household_income)` — used as fallback when the user hasn't provided their own income (the system prompt instructs the agent to use suburb median income as baseline).

---

## Table: `school`

School dimension. Sourced from Education Counts NZ.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `school_id` | STRING | N | Ministry of Education school ID |
| `school_name` | STRING | N | Official school name |
| `suburb_name` | STRING | Y | Nearest suburb |
| `territorial_authority` | STRING | Y | Containing TA |
| `h3_cell` | STRING | Y | H3 res-8 cell of school location |
| `school_type` | STRING | Y | `"primary"`, `"intermediate"`, `"secondary"`, `"composite"` |
| `year_levels` | STRING | Y | Year levels offered (e.g. `"1-6"`, `"7-10"`, `"1-13"`) |
| `eqi_score` | INTEGER | Y | Equity Index score (formerly decile; higher = more affluent intake) |
| `roll_2023` | INTEGER | Y | 2023 roll count |
| `latitude` | DOUBLE | Y | WGS84 latitude |
| `longitude` | DOUBLE | Y | WGS84 longitude |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `school_id`

**Used by:** `query_genie` (via Genie semantic layer) — not queried directly by agent tools.

---

## Table: `crime__month__area_unit`

Monthly crime incident counts by area unit and category. Sourced from NZ Police.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `area_unit_name` | STRING | N | NZ area unit name (finer than suburb) |
| `territorial_authority` | STRING | N | Containing TA |
| `month` | DATE | N | First day of month |
| `category` | STRING | N | Crime category (e.g. `"theft"`, `"assault"`, `"burglary"`) |
| `incidents` | INTEGER | N | Incident count |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(area_unit_name, month, category)`

**Used by:** `query_genie` only.

---

## Table: `house_price__month__territorial_authority`

Monthly house price index by TA and dwelling type. Sourced from Stats NZ HPI.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `territorial_authority` | STRING | N | TA name |
| `month` | DATE | N | First day of month |
| `dwelling_type` | STRING | N | `"all"`, `"house"`, `"apartment"` |
| `hpi_index` | DOUBLE | Y | House Price Index (base 1000 = 2010-Q1) |
| `yoy_change_pct` | DOUBLE | Y | Year-on-year % change |
| `_updated_at` | TIMESTAMP | N | Row last refreshed |

**Primary key:** `(territorial_authority, month, dwelling_type)`

**Used by:** `query_genie` only — primarily for council planner queries ("which TAs saw rent grow > 8% while income grew < 3%?").

---

## Tool → Table Cross-Reference

| Tool | Tables read | Join key |
|---|---|---|
| `lookup_hazards(suburb)` | `suburb` → `hazard` | `suburb.h3_cells` ↔ `hazard.h3_cell` |
| `compute_isochrone(origin_h3, mode, minutes)` | `isochrone` | `h3_origin`, `mode`, `minutes_bucket` |
| `score_affordability(suburb, household_income)` | `rent__month__suburb`, `income__year__suburb` | `suburb_name` |
| `query_genie(question)` | all tables (via Genie semantic layer) | — |
| `save_user_profile` | Lakebase `user_constraints` | `user_id` |
| `set_alert` | Lakebase `saved_searches`, `alerts` | `user_id` |

---

## Delta Format Notes

- All gold tables are Delta Lake format in Unity Catalog
- Catalog: `housing`, schema: `gold`
- Tables are managed (storage under UC-controlled path)
- Partitioning: fact tables partition by `month`; dimension tables are unpartitioned
- Optimize/ZORDER hints: `rent__month__suburb` → ZORDER by `suburb_name`; `isochrone` → ZORDER by `h3_origin`

**Author:** Naineel Soyantar | **Last Updated:** 2026-05-15
