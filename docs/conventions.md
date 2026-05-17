# Lakehouse conventions

Small set of rules we apply across `housing.gold.*` so every contributor (and every consumer — Genie, the agent, ad-hoc SQL writers) finds the same shapes in the same places. Read this before adding a new gold table.

## Gold-table naming

```
<spatial_dim>__<time_grain>    ← time-series fact, one row per (dim, period)
<spatial_dim>                  ← static dim, one row per entity (no time component)
<entity>                       ← non-spatial dims and facts (transit_stop, isochrone)
```

The **table name tells you the grain**, not what's in it. Columns tell you the metrics.

So when the agent wants every metric we know about Auckland TA in March 2026, it's a single `SELECT * FROM ta__month WHERE ta_name='Auckland' ORDER BY date DESC LIMIT 1` — not five joins across `house_price__month__ta`, `rent_price__month__ta`, `housing_indicator__month__ta`, …

### Examples

| Table | Grain | Why this name |
|---|---|---|
| `gold.region__quarter` | region + quarter | RBNZ M10 quarterly indicators (HPI, sales count, etc.) |
| `gold.ta__month` | territorial authority + month | HUD monthly snapshots (prices, rents, MSD waiting list) |
| `gold.ta__quarter` | territorial authority + quarter | HUD affordability indices (deep quarterly time series) |
| `gold.suburb__year` *(planned)* | SA2 + year | Census-derived suburb stats across census years |
| `gold.suburb` | SA2 | Static dim — current snapshot of name/TA/region/centroid/area/latest-census attributes |
| `gold.h3_cell` | H3 cell | Static spatial bridge — cell → suburb_id mapping |
| `gold.transit_stop`, `gold.transit_route` | entity-noun | Static dim, no spatial-dim prefix because the table IS the dim |
| `gold.amenity__h3` | H3 cell | Static-ish; one row per amenity, breakdown by h3 |
| `gold.isochrone` | (origin_h3, destination_h3) pair | Fact table, no time grain (snapshot of one weekday's reachability) |

### When in doubt

- **Don't** name a table after the metric family (`house_price__month__ta`). The next metric family at the same grain will want the same name, then you have two tables to query.
- **Do** name a table after `<grain>__<time>`. Add columns as new metrics arrive; the consumer's query never changes.
- **Don't** invent a fake time grain (`amenity__day__h3` for what's actually a static dim). Use the no-time form.
- **Do** keep a long-format silver alongside the wide gold when source data has many series — useful escape hatch for power users, but the gold should still be wide and consumer-facing.

## Column naming

- **Snake case** everywhere (`current_annual_median_sales_nzd`, not `currentAnnualMedianSalesNZD`).
- **Unit in the column name** for any numeric value where unit is non-obvious (`_nzd`, `_km2`, `_pct`, `_per_10k_pop`, etc.). Agent prompts can't disambiguate "median_rent" vs "median_rent_weekly" vs "median_rent_annual" — the column should say.
- **Period qualifier in the column name** for snapshot vs cumulative vs rolling-window numbers (`annual_sales_volume` = rolling 12 months; `current_annual_median_sales_nzd` = the trailing-12-month aggregate current at this row's date).
- **`_updated_at` always last.** Refresh timestamp, not data semantics.

## Spatial join hierarchy

```
h3_cell  →  suburb_id (SA2)  →  territorial_authority  →  region  →  New Zealand
```

Every spatial fact picks one level and exposes the join key for it. The agent traverses up the hierarchy (suburb → TA → region) by joining through the appropriate dim table. Consumers should never have to compute spatial relationships themselves.

| Level | Source | Joined to next-up via |
|---|---|---|
| `h3_cell` | every spatial fact | `gold.h3_cell.suburb_id` |
| `suburb_id` (SA2) | `gold.suburb` | `gold.suburb.territorial_authority` |
| `territorial_authority` | `gold.ta__*` | `gold.suburb.region` (per-SA2, but consistent within a TA) |
| `region` | `gold.region__*` | rollup to NZ |

## Time-period conventions

- Quarter date column: **first day of the quarter** (`2024-01-01`, not `2024-03-31` end-of-quarter). Easier for `BETWEEN` queries.
- `quarter_label` STRING column alongside (`"2024-Q1"`) for human display.
- Month date column: **first day of the month** (`2024-03-01`). Same reason.
- Year column: just an `INT` (`2023`).

## Table comments

Heavy. Genie reads them. Each gold table needs:

1. **What it is** — one sentence.
2. **Grain** — what does one row represent.
3. **Sparsity** — if rows can be missing dimensions, say so.
4. **Join hint** — which columns connect to which other tables.
5. **Filtering caveat** — known gotchas (e.g. "filter `population_2023 > 500` to exclude harbour SA2s").

Column comments need units, valid ranges where applicable, and a one-phrase semantic explanation. See `gold.suburb` and `gold.ta__month` for the bar.

## Anti-patterns to avoid

- Splitting metrics across tables at the same grain. Wide is good when grain matches.
- Hardcoding business-logic filters in queries instead of comments. The agent + Genie won't know unless the table tells them.
- Using `__day__` when the table doesn't actually have daily granularity. Pick the natural grain.
- Adding `_id` to natural primary keys that are already named meaningfully (`sa2_code`, not `sa2_code_id`).

## When adding a new gold table

1. Decide its **grain** (`<spatial>__<time>` or just `<spatial>` for static).
2. Check whether an existing table at that grain could absorb the metrics — if yes, add columns, don't add a table.
3. Write the table comment and column comments before writing the SELECT — they're the contract.
4. Run `DESCRIBE EXTENDED housing.gold.<your_table>` after deploying and confirm Genie's metadata layer sees the comments.
