# Lakehouse Gold Schema

Column-level definitions for every `housing.gold.*` table the agent tools, Genie semantic layer, and consumer view read from. **This is the contract** — every pipeline's gold layer publishes against it.

If something here disagrees with what's actually in Unity Catalog, the pipeline's `@dlt.table` schema string wins — open the gold notebook for that pipeline and update this doc to match.

> **Naming convention.** Time-series facts follow `<spatial_dim>__<time_grain>` (e.g. `suburb__year`, `ta__month`, `region__quarter`). Static dims use just the entity name (`suburb`, `hazard`, `nz_address`, `transit_stop`, `isochrone`, `amenity__h3`). See [`conventions.md`](conventions.md) for the why.
>
> **Test data.** `app/app-templates/agent-langgraph-advanced/scripts/generate_test_data.py` writes synthetic data to `workspace.test.*` mirroring the schemas below. Tool code switches between test and prod with one env-var change (`HOUSING_CATALOG`, `HOUSING_SCHEMA`) — see [`agent-tool-extension-guide.md`](agent-tool-extension-guide.md).

## Table inventory

| Table | Type | Grain | Source pipeline |
|---|---|---|---|
| [`suburb`](#suburb) | static dim | one row per SA2 2023 | `pipelines/places` |
| [`h3_cell`](#h3_cell) | spatial bridge | one row per H3 res-8 cell | `pipelines/places` |
| [`suburb__year`](#suburb__year) | time-series fact | (suburb_id, census_year) | `pipelines/census_2023` |
| [`ta__month`](#ta__month) | time-series fact | (ta_name, date) | `pipelines/housing_indicators` |
| [`ta__quarter`](#ta__quarter) | time-series fact | (ta_name, quarter) | `pipelines/housing_indicators` |
| [`region__quarter`](#region__quarter) | time-series fact | (region, quarter) | `pipelines/prices` |
| [`transit_stop`](#transit_stop) | static dim | (feed_source, stop_id) | `pipelines/gtfs` |
| [`transit_route`](#transit_route) | static dim | (feed_source, route_id) | `pipelines/gtfs` |
| [`isochrone`](#isochrone) | static fact | (origin_h3, destination_h3) | `pipelines/isochrone` (local compute) |
| [`amenity__h3`](#amenity__h3) | static dim | one OSM amenity per row, keyed by H3 | `pipelines/amenities` (local compute) |
| [`hazard`](#hazard) | static dim | one row per H3 res-8 cell | `pipelines/flood` |
| [`nz_address`](#nz_address) | static dim | one row per LINZ address (current) | `pipelines/linz_nz_addresses` |

## `suburb`

Canonical NZ suburb dimension. One row per Stats NZ Statistical Area 2 (SA2) 2023.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `suburb_id` | STRING | N | 6-digit SA2 2023 code. Stable logical PK. |
| `suburb_name` | STRING | N | SA2 2023 name (e.g. `"Onehunga West"`). Close to colloquial suburb usage but sometimes finer. |
| `territorial_authority` | STRING | Y | Containing TA (e.g. `"Auckland"`). Joins to `ta__month` / `ta__quarter`. |
| `region` | STRING | Y | Containing region (e.g. `"Auckland Region"`). Joins to `region__quarter`. |
| `centroid_h3` | BIGINT | Y | H3 res-8 cell at the SA2 centroid. Single-point handle for spatial queries. |
| `land_area_km2` | DOUBLE | Y | Land area in km² (excludes water surfaces). |
| `population_2023` | INT | Y | 2023 Census usual residents. Near-zero for non-residential SA2s (harbour, EEZ, airport). **Filter `> 500` for residential queries.** |
| `median_age_2023` | DOUBLE | Y | Median age of usual residents. |
| `geometry` | BINARY | Y | SA2 polygon as WKB. For downstream spatial work. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

Partitioned by `region`. ~2,379 rows (16 offshore SA2s with null geometry drop out via `has_centroid` expect_or_drop).

## `h3_cell`

Spatial bridge: every H3 res-8 cell whose centre falls inside an SA2, mapped to that SA2. **The workhorse join** — every H3-keyed fact reaches its suburb through this table.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `h3_cell` | BIGINT | N | H3 res-8 cell. Logical PK. |
| `suburb_id` | STRING | Y | FK to `suburb.suburb_id`. NULL only on the rare boundary tie that survived `dropDuplicates`. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

**Standard pattern:** `JOIN gold.h3_cell USING (h3_cell)` then `JOIN gold.suburb USING (suburb_id)`. Built via `h3_polyfillash3` (centre-based polyfill), so each cell maps to at most one SA2.

## `suburb__year`

Wide time-series fact at SA2 + census-year grain. **The headline "tell me about this suburb" table** — every curated census metric plus annual crime totals in one row per (suburb, year).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `census_year` | INT | N | Census reference year. Currently `2023`. |
| `suburb_id` | STRING | N | SA2 2023 code. Joins to `suburb.suburb_id`. |
| `suburb_name` | STRING | Y | Official SA2 name. |
| `median_household_income` | DOUBLE | Y | Median household income, NZD before tax. |
| `households_total` | INT | Y | Households in occupied private dwellings. |
| `households_income_stated` | INT | Y | Denominator for `median_household_income`. |
| `tenure_owned` | INT | Y | Households owning or partly owning. |
| `tenure_not_owned` | INT | Y | Households not owning, not in family trust. |
| `tenure_total_stated` | INT | Y | Denominator for `owner_occupier_pct`. |
| `owner_occupier_pct` | DOUBLE | Y | `tenure_owned / tenure_total_stated`. |
| `median_weekly_rent` | DOUBLE | Y | Median weekly rent (renting households), NZD. |
| `renting_households_total` | INT | Y | Renting households in occupied private dwellings. |
| `renting_households_stated` | INT | Y | Denominator for median rent. |
| `households_crowded` | INT | Y | Households classified as crowded (Canadian National Occupancy Standard). |
| `households_crowding_total_stated` | INT | Y | Denominator for `percent_crowded`. |
| `percent_crowded` | DOUBLE | Y | `households_crowded / households_crowding_total_stated`. |
| `dwellings_always_damp` | INT | Y | Dwellings reported as always damp. |
| `dwellings_sometimes_damp` | INT | Y | Dwellings reported as sometimes damp. |
| `dwellings_damp_total_stated` | INT | Y | Denominator for damp metrics. |
| `dwellings_mould_a4_always` | INT | Y | Dwellings with A4-sized-or-larger mould always present. |
| `dwellings_mould_total_stated` | INT | Y | Denominator for mould metrics. |
| `dwellings_no_heating` | INT | Y | Dwellings reporting no heating. |
| `dwellings_mean_rooms` | DOUBLE | Y | Mean rooms per dwelling. |
| `population_total` | INT | Y | Usually-resident population. |
| `median_age` | DOUBLE | Y | Median age (years). |
| `total_victimisations_2023` | INT | Y | NZ Police recorded victimisations in 2023, allocated from AU2013 crime data via `silver.area_unit_to_suburb`. ~97% SA2 coverage; ~3% null for non-residential SA2s with no overlapping AU. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

**For long-format / open-ended Genie queries** (any unpivoted metric not in this list), hit `housing.silver.census_sa2_metric` instead.

## `ta__month`

Time-series fact at NZ territorial-authority + month grain. **Sparse by design** — Sales/Bonds rows appear on snapshot dates HUD publishes; MSD rows appear every month back to 2017.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `ta_name` | STRING | N | TA name (Stats NZ canonical NZGB form) or `"New Zealand"` for the rollup. Joins to `suburb.territorial_authority`. |
| `ta_code` | STRING | Y | HUD's stable numeric area_id. |
| `date` | DATE | N | End-of-period date. MSD = month-end; Sales/Bonds = HUD snapshot date. |
| `current_hpi` | DOUBLE | Y | House Price Index at snapshot. |
| `current_annual_median_sales_nzd` | DOUBLE | Y | Median residential sale price (NZD), trailing 12 months. |
| `current_annual_lower_q_sales_nzd` | DOUBLE | Y | Lower-quartile sale price, trailing 12 months. |
| `annual_sales_volume` | INT | Y | Residential sales count, trailing 12 months. |
| `median_rent_nzd` | DOUBLE | Y | Weekly median rent, trailing 12 months (HUD Bonds / MBIE upstream). |
| `average_rent_nzd` | DOUBLE | Y | Weekly average rent, trailing 12 months. |
| `lower_quartile_rent_nzd` | DOUBLE | Y | Weekly lower-quartile rent, trailing 12 months. |
| `housing_register` | INT | Y | Households on MSD social-housing register at month-end. |
| `housing_register_per_10k_pop` | DOUBLE | Y | MSD register per 10k TA population. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

**"Current state" pattern:** `WHERE ta_name = X ORDER BY date DESC LIMIT 1`. Partitioned by `ta_name`.

## `ta__quarter`

Quarterly TA-level affordability indices from HUD. **The deepest time series in the lakehouse** — 25 years back to 2001-Q1.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `ta_name` | STRING | N | TA name or `"New Zealand"`. Joins to `suburb.territorial_authority`. |
| `ta_code` | STRING | Y | HUD numeric area_id. |
| `quarter` | DATE | N | First day of quarter (`2024-01-01` = Q1 2024). |
| `quarter_label` | STRING | N | Human-readable label, e.g. `"2024-Q1"`. |
| `deposit_affordability_index` | DOUBLE | Y | Deposit required vs household income capacity. Higher = less affordable. |
| `mortgage_affordability_index` | DOUBLE | Y | Mortgage servicing cost vs household income. |
| `rent_affordability_index` | DOUBLE | Y | Median rent vs household income. |
| `median_to_median_ratio` | DOUBLE | Y | Median house price / median household income. Auckland peaked ~10x in 2021. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

Partitioned by `ta_name`.

## `region__quarter`

Region + quarter time-series fact. Today every row carries `region = "New Zealand"` because the only source (RBNZ M10 Housing) is country-aggregate. When regional sources land (REINZ, Stats NZ property transfers), this table fills with real region values without schema change.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `region` | STRING | N | Stats-NZ-aligned region (e.g. `"Auckland Region"`) or `"New Zealand"`. Joins to `suburb.region`. |
| `quarter` | DATE | N | First day of quarter. |
| `quarter_label` | STRING | N | e.g. `"2024-Q1"`. |
| `hpi` | DOUBLE | Y | House Price Index (base ≈ 1000 at Q4 2003). |
| `hpi_yoy_pct` | DOUBLE | Y | Year-on-year % change in HPI (4-quarter LAG per region). Null for the first year of each region. |
| `sales_count` | INT | Y | Residential property transactions settled in the quarter. |
| `total_value_nzdm` | DOUBLE | Y | Total value of NZ housing stock, NZD millions (nominal). |
| `residential_investment_nzdm_real` | DOUBLE | Y | Real residential investment, NZD millions (chain-volume). |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

Partitioned by `region`.

## `transit_stop`

Public-transit stops with H3 cells. One row per `(feed_source, stop_id)`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `feed_source` | STRING | Y | GTFS feed: `"auckland_transport"`, `"metlink"`, `"busit"`, `"metroinfo"`. |
| `stop_id` | STRING | Y | Operator's stop identifier. Unique within `feed_source`. |
| `stop_name` | STRING | Y | Public-facing name (e.g. `"Britomart Train Station"`). |
| `stop_code` | STRING | Y | Short code on signage/apps. |
| `stop_lat` | DOUBLE | Y | WGS84 latitude. |
| `stop_lon` | DOUBLE | Y | WGS84 longitude. |
| `h3_cell` | BIGINT | Y | H3 res-8 cell. Join key for spatial queries. |

## `transit_route`

Transit routes with agency and type. One row per `(feed_source, route_id)`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `feed_source` | STRING | Y | GTFS feed identifier. |
| `route_id` | STRING | Y | Operator's route identifier. |
| `agency_id` | STRING | Y | Operator agency identifier. |
| `agency_name` | STRING | Y | Human-readable operator (e.g. `"AT Metro Bus"`). |
| `route_short_name` | STRING | Y | Short route name shown to riders (e.g. `"74"`, `"WEST"`). |
| `route_long_name` | STRING | Y | Long description (e.g. `"Britomart - Glen Innes"`). |
| `route_type` | INT | Y | GTFS code (0=tram, 1=subway, 2=rail, 3=bus, 4=ferry, …). |
| `route_type_label` | STRING | Y | Human-readable type (`"bus"`, `"rail"`, `"ferry"`, …). |

## `isochrone`

**Symmetric** public-transit travel-time matrix across NZ's four metro regions (Auckland, Wellington, Waikato/Hamilton, Christchurch). One row per `(origin_h3, destination_h3)` pair reachable within 90 min on Wednesday 08:30 NZT. Origin and destination cells come from the **same set** per region — every cell hosting a transit stop plus a 1-ring of neighbours — so any lat/lon near transit works as either side.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `origin_h3` | BIGINT | Y | H3 res-8 cell of origin. Use `h3_longlatash3(lon, lat, 8)` to look up for any workplace. |
| `destination_h3` | BIGINT | Y | H3 res-8 cell of destination. Same set as `origin_h3`. Joins to `h3_cell.h3_cell`. |
| `mode` | STRING | Y | Currently `"transit"`. Future: `"drive"`, `"walk"`. Partition column. |
| `travel_minutes` | INT | Y | Total trip time bucketed to 5 min, hard-capped at 90. Self-reach (`origin = destination`) reports 0. |
| `feed_source` | STRING | Y | GTFS feed (also a partition column). |
| `departure_time` | STRING | Y | Assumed departure clock time (currently `"08:30"`). |
| `service_date` | DATE | Y | Service date used for the routing query. |
| `computed_at` | TIMESTAMP | Y | When this row was produced by r5py. |
| `computation_version` | STRING | Y | Algorithm version. Current: `"r5py-v2"` (symmetric). |

**Query pattern** — destinations reachable from a workplace lat/lon in 30 min:

```sql
SELECT destination_h3, travel_minutes
FROM housing.gold.isochrone
WHERE origin_h3 = h3_longlatash3(:lon, :lat, 8)
  AND travel_minutes <= 30;
```

~600k rows total: Auckland 372k, Christchurch 122k, Wellington 77k, Hamilton 36k.

## `amenity__h3`

NZ amenity POIs extracted from OpenStreetMap, keyed by H3 res-8 cell. 8 canonical categories: `supermarket`, `hospital`, `school`, `early_childhood`, `pharmacy`, `gp_clinic`, `park`, `library`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `osm_id` | STRING | Y | Stable OSM identifier in `type/id` form (`"node/123"`, `"way/456"`, `"relation/789"`). |
| `amenity_type` | STRING | Y | One of the 8 categories above. Partition column. |
| `name` | STRING | Y | OSM `name` tag (e.g. `"Woolworths"`, `"Auckland Hospital"`). Often null for minor parks. |
| `lat` | DOUBLE | Y | WGS84 latitude (centroid for non-point geometries). |
| `lon` | DOUBLE | Y | WGS84 longitude. |
| `h3_cell` | BIGINT | Y | H3 res-8 cell containing the amenity. |
| `suburb_id` | STRING | Y | Denormalised FK to `suburb.suburb_id` (pre-joined via `h3_cell` at build time). |
| `_updated_at` | TIMESTAMP | Y | When this row was last materialised. |

**Caveat:** OSM often tags a single real-world entity multiple times (a school's buildings, grounds, and field can be separate features), so raw counts overstate facility counts somewhat. Use `COUNT(DISTINCT name)` per `(suburb_id, amenity_type)` for a closer approximation.

## `hazard`

Flood-hazard flags per H3 res-8 cell across NZ regions. Each cell carries booleans indicating which ingested hazard layers it intersects.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `h3_cell` | BIGINT | N | H3 res-8 cell. |
| `in_flood_plain` | BOOLEAN | Y | Modelled flood plain or 1% AEP river flood extent. |
| `in_flood_prone_area` | BOOLEAN | Y | Catchment-level flood-prone area (Auckland). |
| `in_flood_sensitive_area` | BOOLEAN | Y | Flood-sensitive planning overlay. |
| `in_coastal_inundation_1_aep` | BOOLEAN | Y | Coastal inundation 1% AEP. |
| `in_coastal_inundation_100yr` | BOOLEAN | Y | Coastal inundation 100-year return. |
| `in_regional_flood_zone` | BOOLEAN | Y | Other regional-council flood-hazard polygons. |
| `hazard_sources` | ARRAY\<STRING\> | Y | Layer IDs contributing hazard at this cell. |
| `max_rainfall_event` | INT | Y | Largest rainfall ARI code (e.g. `100`) when present. |
| `sample_report_url` | STRING | Y | Link to a source model report when available. |
| `_updated_at` | TIMESTAMP | N | When this row was last refreshed. |

Flood + coastal only — no liquefaction or earthquake layers in this table today. Join via `h3_cell` → `h3_cell.suburb_id` → `suburb` to attribute hazards to a suburb.

## `nz_address`

Current LINZ NZ Addresses (current lifecycle only — excludes proposed/retired). One row per `address_id`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `address_id` | STRING | Y | LINZ stable address identifier. |
| `full_address` | STRING | Y | Formatted address string. |
| `suburb_locality` | STRING | Y | LINZ suburb / locality label (not always the Stats NZ SA2). |
| `town_city` | STRING | Y | Town or city. |
| `territorial_authority` | STRING | Y | Containing TA (council name). |
| `address_class` | STRING | Y | LINZ address class. |
| `longitude` | DOUBLE | Y | WGS84 longitude. |
| `latitude` | DOUBLE | Y | WGS84 latitude. |
| `h3_cell` | BIGINT | Y | H3 res-8 cell. Join key to `h3_cell.h3_cell` → `suburb`. |

## Tool → table cross-reference

The agent's tools live under `app/app-templates/agent-langgraph-advanced/agent_server/`. See [`agent-tool-extension-guide.md`](agent-tool-extension-guide.md) for the wire-up pattern.

| Tool | Tables read | Join key |
|---|---|---|
| `query_genie(question)` | All gold tables via the Genie semantic layer | — |
| `lookup_suburb(name)` | `suburb` | `suburb_name` fuzzy match → `suburb_id` |
| `suburb_snapshot(suburb_id)` | `suburb`, `suburb__year` (`census_year = 2023`) | `suburb_id` |
| `compute_isochrone(origin_lat, origin_lon, minutes, mode='transit')` | `isochrone`, `h3_cell`, `suburb` | `origin_h3 = h3_longlatash3(lon, lat, 8)` |
| `lookup_hazards(suburb_id)` | `suburb` → `h3_cell` → `hazard` | `suburb_id` → `h3_cell` |
| `amenities_near(suburb_id, types)` | `amenity__h3` | `suburb_id` (denormalised) |
| `affordability_context(ta_name)` | `ta__month`, `ta__quarter` (latest per TA) | `ta_name` |
| `save_user_profile` | Lakebase `user_constraints` (not gold) | `user_id` |
| `set_alert` | Lakebase `saved_searches`, `alerts` (not gold) | `user_id` |

## Delta / Unity Catalog notes

- All gold tables are Delta in Unity Catalog under `housing.gold.*`.
- Tables are managed (UC-controlled storage).
- Time-series facts partition by their spatial column (`ta_name`, `region`).
- Genie reads table + column comments from UC, so every gold table carries verbose comments at both levels. **If you add a column, comment it** — that's how Genie disambiguates "rent" between weekly and annual, NZD and AUD, etc.

## Useful query patterns

**Sarah's "tell me about Onehunga"** — one row per suburb with everything:

```sql
SELECT s.suburb_name, s.territorial_authority,
       y.median_household_income, y.median_weekly_rent, y.percent_crowded,
       y.total_victimisations_2023,
       ROUND(y.total_victimisations_2023 * 1000.0 / s.population_2023, 1) AS crime_per_1k
FROM housing.gold.suburb        s
JOIN housing.gold.suburb__year  y USING (suburb_id)
WHERE y.census_year = 2023
  AND s.suburb_name LIKE 'Onehunga%';
```

**"What's a 30-min transit commute from this lat/lon get me?"**

```sql
SELECT DISTINCT s.suburb_name
FROM housing.gold.isochrone i
JOIN housing.gold.h3_cell   h ON h.h3_cell = i.destination_h3
JOIN housing.gold.suburb    s ON s.suburb_id = h.suburb_id
WHERE i.origin_h3 = h3_longlatash3(174.76682, -36.84393, 8)  -- Britomart
  AND i.travel_minutes <= 30
ORDER BY s.suburb_name;
```

**TA affordability trend** — Daniel's planner query:

```sql
SELECT ta_name, quarter_label,
       mortgage_affordability_index, median_to_median_ratio
FROM housing.gold.ta__quarter
WHERE ta_name IN ('Auckland', 'Wellington City', 'Christchurch City')
ORDER BY ta_name, quarter;
```

**Hazard exposure per suburb** — Sarah's "is Onehunga flood-safe?":

```sql
SELECT s.suburb_name,
       COUNT(*)                                                AS cells,
       SUM(CAST(h.in_flood_plain          AS INT))            AS in_flood,
       SUM(CAST(h.in_coastal_inundation_100yr AS INT))        AS in_coastal
FROM housing.gold.suburb     s
JOIN housing.gold.h3_cell    c ON c.suburb_id = s.suburb_id
LEFT JOIN housing.gold.hazard h ON h.h3_cell = c.h3_cell
WHERE s.suburb_name = 'Onehunga West'
GROUP BY s.suburb_name;
```

---

**Last updated:** 2026-05-17 (post Isabel data-ingestion merge + census/crime gold refactor).
