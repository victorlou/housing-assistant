# Genie space

Natural-language Q&A surface over `housing.gold.*`. Consumed by:

1. **The agent** — calls into this space via its `query_genie` tool. The space ID becomes `DATABRICKS_GENIE_SPACE_ID` in the agent's `.env`.
2. **Humans** — point a browser at the space directly for ad-hoc questions during the demo or for planner-style exploration.

## Provisioning status: manual

The Databricks Terraform provider (1.115 as of mid-2026) **does not support Genie spaces as a resource**. DABs support is in flight ([databricks/cli#4191](https://github.com/databricks/cli/pull/4191)) but not landed. So the space is created and curated **manually via the workspace UI**.

The curation content is version-controlled as Terraform `local.genie_*` blocks in `terraform/envs/dev/main.tf`. The operator copies from there into the UI section-by-section. When DABs / Terraform support lands, the locals wire straight into the resource without rewriting any glossary.

## Where each block of content goes

Genie's UI splits the semantic layer into four sections. Spreading content across them is better than dumping everything into a single Instructions field — Genie picks the right section per question, and a shorter Instructions block leaves more room for the LLM to attend to user input (Genie itself warns: *"Long instructions can limit the amount of other information that Genie can learn from."*).

| Section | What goes there | Terraform local |
|---|---|---|
| Instructions | Cross-cutting context — spatial grains, synonyms, NZ caveats, honest limitations | `local.genie_instructions` |
| Joins | Explicit Left → Right table relationships with cardinality | `local.genie_joins` |
| Common SQL Expressions → **Filters** | Boolean conditions for WHERE | `local.genie_filters` |
| Common SQL Expressions → **Measures** | Aggregations over many rows | `local.genie_measures` |
| Common SQL Expressions → **Dimensions** | Per-row calculated values | `local.genie_dimensions` |
| SQL queries & functions | Example queries Genie learns patterns from | `local.genie_sql_queries` |
| Sample questions | One-click prompts shown in the UI | `local.genie_sample_questions` |

We **do not** name personas ("Sarah", "Daniel") inside any of these blocks — Genie would cheerfully greet users by those names. Personas are internal-framing docs only ([`docs/personas.md`](personas.md)).

## One-time setup

### 1. Create the space

Databricks workspace → **AI/BI → Genie → Create a New Genie Space**:

- **Name**: `housing-assistant-dev-housing` (matches `${local.name_prefix}-housing`).
- **Description**: "Natural-language Q&A over NZ housing affordability data — rent, income, crime, hazards, commute, demographics — at suburb, TA, and region grain."
- **Warehouse**: pick the `housing-assistant-dev` serverless warehouse.
- **Tables**: add all 12 from [Tables](#tables) below.
- Save.

### 2. Paste Instructions

[Instructions section](#instructions) below.

### 3. Paste Joins

[Joins section](#joins) below — one row per relationship. The UI dialog asks for Left Table, Right Table, Join condition, Relationship Type, Instructions.

### 4. Paste Common SQL Expressions

The UI splits this into three types — paste each into the right tab:

- [Filters](#filters) — boolean conditions for WHERE clauses
- [Measures](#measures) — aggregations over many rows
- [Dimensions](#dimensions) — per-row calculated values

Each entry has Name, Code, Synonyms (comma-separated), Instructions, and a target Table.

### 5. Paste SQL queries & functions

[SQL queries & functions](#sql-queries--functions) — example queries Genie learns patterns from.

### 6. Paste Sample questions

[Sample questions](#sample-questions) — one-click prompts.

### 7. Wire permissions

Open the space → **Share** or **Permissions**:

| Principal | Permission |
|---|---|
| `sp-housing-jobs` (jobs SP) | `Can Run` |
| `sp-housing-app` (app SP) | `Can Run` |
| `housing-assistant-dev-admins` | `Can Manage` |

The SP IDs are available from `terraform output jobs_service_principal_application_id` and `terraform output app_service_principal_client_id`.

### 8. Capture the space ID and wire the agent

```bash
# The space ID is in the URL: https://<workspace>/genie/rooms/<space_id>
echo "DATABRICKS_GENIE_SPACE_ID=<space-id-from-url>" \
  >> app/app-templates/agent-langgraph-advanced/.env
```

That's it — the agent's `query_genie` tool now targets this space.

---

## Tables

Twelve tables. Add each in the UI's "Add tables" dialog.

| # | Table | Why it's in the space |
|---|---|---|
| 1 | `housing.gold.suburb` | Canonical SA2 dim — every suburb question starts here |
| 2 | `housing.gold.suburb__year` | Wide census + crime per suburb — "tell me about X" answers |
| 3 | `housing.gold.ta__month` | HUD monthly TA metrics — sales, rent, MSD register |
| 4 | `housing.gold.ta__quarter` | HUD quarterly affordability indices, 25-year time series |
| 5 | `housing.gold.region__quarter` | RBNZ HPI per region — country-level trends |
| 6 | `housing.gold.h3_cell` | Spatial bridge between H3 cells and `suburb_id` |
| 7 | `housing.gold.isochrone` | Symmetric transit travel-time matrix |
| 8 | `housing.gold.amenity__h3` | OSM POIs — supermarkets, schools, parks, hospitals |
| 9 | `housing.gold.hazard` | Flood + coastal risk flags per H3 cell |
| 10 | `housing.gold.transit_stop` | GTFS stops |
| 11 | `housing.gold.transit_route` | GTFS routes with agency + type |
| 12 | `housing.gold.nz_address` | Current LINZ addresses |

## Instructions

Paste verbatim into the space's **Instructions** field. Kept deliberately short (Genie's warning) — everything joinable / pivotable / showable as a query lives in the dedicated sections below.

```
Natural-language Q&A over New Zealand housing affordability data. Data lives at three spatial grains; pick the right one for the question and cross-grain joins are spelled out in the Joins section.

- Suburb = Stats NZ SA2 2023 area (~2,395). Joined via suburb_id (6-digit code). Primary grain. Tables: suburb, suburb__year.
- Territorial authority (TA) = council area (67 of them). Joined via ta_name. Tables: ta__month, ta__quarter.
- Region = Stats NZ region (16). Joined via region. Tables: region__quarter.
- H3 cell = res-8 hexagon (~0.7 km²) used as the universal spatial key. h3_cell.suburb_id bridges any H3-keyed fact to a suburb.

## Synonyms

- "rent" / "weekly rent" → suburb__year.median_weekly_rent (NZD/week, 2023 census) or ta__month.median_rent_nzd (TA-monthly).
- "income" → suburb__year.median_household_income (NZD/year, before tax).
- "crime" / "victimisations" → suburb__year.total_victimisations_2023.
- "crowded" → suburb__year.percent_crowded.
- "homeowner" / "owner-occupier" → suburb__year.owner_occupier_pct.
- "HPI" / "house price index" → region__quarter.hpi or ta__month.current_hpi.
- "affordability" → one of the *_affordability_index columns on ta__quarter. Higher = less affordable.
- "flood risk" → any in_flood_* boolean on hazard.
- "commute" / "reachable in N minutes" → isochrone.travel_minutes.

## Filters to remember

- Residential queries: filter suburb.population_2023 > 500 (excludes ~600 non-residential SA2s — harbour, EEZ, airport, etc.).
- Current state per TA: ta__month is sparse — Sales/Bonds rows only on HUD snapshot dates, MSD rows monthly. Use ORDER BY date DESC LIMIT 1 per ta_name.
- Origin from lat/lon: isochrone.origin_h3 = h3_longlatash3(lon, lat, 8). The matrix is symmetric.

## NZ caveats

- "Auckland" is a single TA covering ~580 SA2s (post-supercity amalgamation). Every Auckland SA2 shares the same ta__month / ta__quarter row.
- Colloquial suburb names don't always match one SA2 — "Onehunga" is split into Onehunga North East / North West / South East. When the user names a suburb, prefer suburb_name LIKE '%X%'.
- TA names use macrons (Ōtorohanga, Hawke's Bay). Match case-insensitively against user input.

## Honest limitations

- Crime is only 2023 at suburb grain. For monthly trends or offence categories, the user has to drop to housing.silver.crime_victimisation_monthly directly.
- Rent / income on suburb__year are 2023 census snapshots. Monthly TA rent (HUD Bonds) is on ta__month.
- Amenities are OSM-derived — coverage is best in Auckland / Wellington / Christchurch.
```

## Joins

Add each as a separate row via **Joins → Define join relationship**. The UI dialog has five fields per row.

| Left | Right | Join condition | Relationship | Instructions |
|---|---|---|---|---|
| `suburb` | `suburb__year` | `` `suburb`.`suburb_id` = `suburb__year`.`suburb_id` `` | One-to-Many | Static suburb dim joined to its time-series census + crime fact. The headline 'tell me about this suburb' join. |
| `suburb` | `ta__month` | `` `suburb`.`territorial_authority` = `ta__month`.`ta_name` `` | Many-to-Many | Attribute monthly TA-level HUD metrics (HPI, sale price, weekly rent, MSD register) to a suburb. Auckland alone has ~580 SA2s sharing one TA. Use `ORDER BY date DESC LIMIT 1` per `ta_name` for current-state. |
| `suburb` | `ta__quarter` | `` `suburb`.`territorial_authority` = `ta__quarter`.`ta_name` `` | Many-to-Many | Quarterly TA-level HUD affordability indices (25-yr time series). |
| `suburb` | `region__quarter` | `` `suburb`.`region` = `region__quarter`.`region` `` | Many-to-Many | RBNZ M10 HPI / sales. Today every row in region__quarter is region = 'New Zealand'. |
| `suburb` | `h3_cell` | `` `suburb`.`suburb_id` = `h3_cell`.`suburb_id` `` | One-to-Many | Suburb to its constituent H3 cells. First hop for any H3-keyed fact. |
| `h3_cell` | `hazard` | `` `h3_cell`.`h3_cell` = `hazard`.`h3_cell` `` | One-to-One | Cell to flood / coastal booleans. Aggregate booleans across a suburb's cells to attribute risk. |
| `h3_cell` | `amenity__h3` | `` `h3_cell`.`h3_cell` = `amenity__h3`.`h3_cell` `` | One-to-Many | Cell to OSM amenities. `amenity__h3.suburb_id` is denormalised too, so the bridge can be skipped. |
| `h3_cell` | `transit_stop` | `` `h3_cell`.`h3_cell` = `transit_stop`.`h3_cell` `` | One-to-Many | Cell to GTFS stops. |
| `h3_cell` | `isochrone` | `` `h3_cell`.`h3_cell` = `isochrone`.`destination_h3` `` | One-to-Many | Cell as reachable destination. Origin from `h3_longlatash3(lon, lat, 8)`. Matrix is symmetric. |
| `h3_cell` | `nz_address` | `` `h3_cell`.`h3_cell` = `nz_address`.`h3_cell` `` | One-to-Many | Cell to LINZ addresses for proximity queries. |
| `transit_stop` | `transit_route` | `` `transit_stop`.`feed_source` = `transit_route`.`feed_source` `` | Many-to-Many | Lightly normalised — feed-level lookup only. |

## Filters

UI: **Common SQL Expressions → New filter**. Boolean SQL expression that lands in WHERE clauses when the user mentions the synonyms.

### `is_residential` — on `suburb`

- **Code**: `population_2023 > 500`
- **Synonyms**: `residential, where people live, livable, lived-in, real suburbs`
- **Instructions**: Excludes ~600 non-residential SA2s — harbour, EEZ, airport runway, industrial zones. Use for any "where should I live" / "compare these suburbs" question. Don't use for exhaustive geographic queries (e.g. "list every SA2 in Auckland").

### `is_rent_affordable_at_median_income` — on `suburb__year`

- **Code**: `median_weekly_rent * 52.0 <= median_household_income * 0.30`
- **Synonyms**: `affordable rent, rent affordable, rent under 30 percent, rent affordable to locals`
- **Instructions**: Standard NZ housing affordability test: median weekly rent (annualised) is no more than 30% of median household income. True / false for each suburb. Pairs naturally with `is_residential` on the suburb dim.

### `is_auckland_region` — on `suburb`

- **Code**: `region = 'Auckland Region'`
- **Synonyms**: `Auckland, in Auckland, Auckland metro, Auckland-wide`
- **Instructions**: Filter to suburbs in the Auckland Region.

## Measures

UI: **Common SQL Expressions → New measure**. Aggregating SQL expression for GROUP BY contexts.

### `total_population` — on `suburb`

- **Code**: `SUM(population_2023)`
- **Synonyms**: `total population, total residents, headcount, people, residents`
- **Instructions**: Sum of usual-resident 2023 census population across grouped suburbs. Don't use unfiltered across the whole table — includes non-residential SA2s with near-zero population.

### `median_weekly_rent_across_group` — on `suburb__year`

- **Code**: `PERCENTILE(median_weekly_rent, 0.5)`
- **Synonyms**: `median rent, typical rent, average rent across suburbs`
- **Instructions**: Median of median weekly rents across grouped suburbs (e.g. "median rent across Auckland TA"). Note this is a median-of-medians, not a true population-weighted median.

### `total_victimisations` — on `suburb__year`

- **Code**: `SUM(total_victimisations_2023)`
- **Synonyms**: `total crime, total victimisations, total recorded crime`
- **Instructions**: Sum of 2023 recorded victimisations across grouped suburbs. Bigger suburbs have more crime in absolute terms — prefer the `crime_per_1k_residents` dimension for fair cross-suburb comparison.

### `latest_mortgage_affordability` — on `ta__quarter`

- **Code**: `MAX_BY(mortgage_affordability_index, quarter)`
- **Synonyms**: `current mortgage affordability, latest affordability, today's affordability`
- **Instructions**: Most recent observation of the mortgage affordability index per TA. Higher = less affordable. Use when the user asks for "current" or "latest" affordability.

## Dimensions

UI: **Common SQL Expressions → New dimension**. SQL expression calculating a new per-row value.

### `owner_occupier_share` — on `suburb__year`

- **Code**: `tenure_owned * 1.0 / NULLIF(tenure_total_stated, 0)`
- **Synonyms**: `homeowner share, owner-occupier share, % owners, ownership rate`
- **Instructions**: Share of households owning or partly owning their dwelling. NULL-safe vs the raw column when stated == 0. Value between 0 and 1.

### `crime_per_1k_residents` — on `suburb__year`

- **Code**: `total_victimisations_2023 * 1000.0 / NULLIF(population_total, 0)`
- **Synonyms**: `crime rate, victimisation rate, crime per capita, crime per 1000, per-capita crime`
- **Instructions**: Annual recorded victimisations per 1,000 residents (2023). Use this rather than raw counts for fair cross-suburb comparison.

### `affordable_weekly_rent_threshold` — on `suburb__year`

- **Code**: `median_household_income * 0.30 / 52.0`
- **Synonyms**: `affordable rent ceiling, what rent locals can afford, 30 percent rent limit`
- **Instructions**: Maximum weekly rent considered affordable for a household at the suburb's median income (30% of weekly income — the standard NZ housing affordability ceiling).

### `damp_share` — on `suburb__year`

- **Code**: `(dwellings_always_damp + dwellings_sometimes_damp) * 1.0 / NULLIF(dwellings_damp_total_stated, 0)`
- **Synonyms**: `damp share, damp dwellings, % damp, damp housing rate`
- **Instructions**: Share of dwellings reporting 'always' or 'sometimes' damp in the 2023 census. Higher = worse housing quality. Value between 0 and 1.

### `mould_share` — on `suburb__year`

- **Code**: `dwellings_mould_a4_always * 1.0 / NULLIF(dwellings_mould_total_stated, 0)`
- **Synonyms**: `mould share, mouldy dwellings, % with mould`
- **Instructions**: Share of dwellings with A4-sized-or-larger mould always present (2023 census). Value between 0 and 1.

### `rent_to_income_ratio` — on `suburb__year`

- **Code**: `median_weekly_rent * 52.0 / NULLIF(median_household_income, 0)`
- **Synonyms**: `rent burden, rent-to-income, rent share of income, how unaffordable`
- **Instructions**: Median weekly rent annualised, divided by median household income. > 0.30 is the standard NZ "unaffordable" threshold. Companion to the `is_rent_affordable_at_median_income` filter.

## SQL queries & functions

Paste each as a named example query in the UI's **SQL queries & functions** section. Genie learns the join patterns from these.

### Suburb summary

> Headline 'tell me about this suburb' answer — rent, income, crime, demographics, plus a per-capita crime rate.

```sql
SELECT s.suburb_name,
       s.territorial_authority,
       s.population_2023,
       y.median_household_income,
       y.median_weekly_rent,
       y.percent_crowded,
       y.total_victimisations_2023,
       ROUND(y.total_victimisations_2023 * 1000.0 / NULLIF(s.population_2023, 0), 1) AS crime_per_1k
FROM housing.gold.suburb        s
JOIN housing.gold.suburb__year  y USING (suburb_id)
WHERE y.census_year = 2023
  AND s.suburb_name ILIKE :suburb_name_pattern;
```

### 30-minute transit reach from a lat/lon

> Which suburbs are reachable within N minutes by transit from a given workplace lat/lon.

```sql
SELECT DISTINCT s.suburb_name, MIN(i.travel_minutes) AS min_travel_minutes
FROM housing.gold.isochrone i
JOIN housing.gold.h3_cell   c ON c.h3_cell   = i.destination_h3
JOIN housing.gold.suburb    s ON s.suburb_id = c.suburb_id
WHERE i.origin_h3 = h3_longlatash3(:origin_lon, :origin_lat, 8)
  AND i.travel_minutes <= :max_minutes
  AND s.population_2023 > 500
GROUP BY s.suburb_name
ORDER BY min_travel_minutes, s.suburb_name;
```

### Flood + coastal risk for a suburb

> Aggregate hazard booleans across all H3 cells covering a suburb. Returns the share of cells flagged for each risk.

```sql
SELECT s.suburb_name,
       COUNT(*)                                              AS cells,
       AVG(CAST(h.in_flood_plain              AS INT))       AS share_in_flood_plain,
       AVG(CAST(h.in_flood_prone_area         AS INT))       AS share_in_flood_prone_area,
       AVG(CAST(h.in_coastal_inundation_1_aep AS INT))       AS share_in_coastal_1_aep,
       AVG(CAST(h.in_coastal_inundation_100yr AS INT))       AS share_in_coastal_100yr
FROM housing.gold.suburb     s
JOIN housing.gold.h3_cell    c ON c.suburb_id = s.suburb_id
LEFT JOIN housing.gold.hazard h ON h.h3_cell  = c.h3_cell
WHERE s.suburb_name ILIKE :suburb_name_pattern
GROUP BY s.suburb_name;
```

### TA affordability trend

> 25-year trajectory of HUD's four affordability indices for one or more TAs.

```sql
SELECT ta_name, quarter_label, quarter,
       deposit_affordability_index,
       mortgage_affordability_index,
       rent_affordability_index,
       median_to_median_ratio
FROM housing.gold.ta__quarter
WHERE ta_name IN (SELECT explode(:ta_names))
ORDER BY ta_name, quarter;
```

### Top-N most affordable TAs right now

> Ten cheapest TAs by mortgage affordability index in the most recent quarter.

```sql
WITH latest AS (
  SELECT MAX(quarter) AS quarter FROM housing.gold.ta__quarter
)
SELECT q.ta_name, q.quarter_label,
       q.mortgage_affordability_index,
       q.median_to_median_ratio
FROM housing.gold.ta__quarter q
JOIN latest l ON l.quarter = q.quarter
WHERE q.ta_name <> 'New Zealand'
ORDER BY q.mortgage_affordability_index ASC
LIMIT 10;
```

### Latest TA monthly snapshot

> Per-TA: the most recent row from the sparse `ta__month`, joined to its current affordability quarter. Useful for "current state" questions.

```sql
WITH latest_month AS (
  SELECT ta_name, MAX(date) AS date FROM housing.gold.ta__month GROUP BY ta_name
),
latest_quarter AS (
  SELECT ta_name, MAX(quarter) AS quarter FROM housing.gold.ta__quarter GROUP BY ta_name
)
SELECT m.ta_name, m.date,
       m.current_hpi, m.current_annual_median_sales_nzd, m.median_rent_nzd,
       m.housing_register,
       q.mortgage_affordability_index
FROM housing.gold.ta__month m
JOIN latest_month lm ON lm.ta_name = m.ta_name AND lm.date = m.date
LEFT JOIN housing.gold.ta__quarter q ON q.ta_name = m.ta_name
LEFT JOIN latest_quarter lq ON lq.ta_name = q.ta_name AND lq.quarter = q.quarter
WHERE m.ta_name <> 'New Zealand';
```

### Suburbs with a supermarket and a school

> Residential SA2s that contain at least one supermarket AND at least one school. Useful for proximity-based shortlists.

```sql
SELECT s.suburb_name, s.territorial_authority,
       COUNT(DISTINCT CASE WHEN a.amenity_type = 'supermarket' THEN a.osm_id END) AS supermarkets,
       COUNT(DISTINCT CASE WHEN a.amenity_type = 'school'      THEN a.osm_id END) AS schools
FROM housing.gold.suburb       s
JOIN housing.gold.amenity__h3  a ON a.suburb_id = s.suburb_id
WHERE s.population_2023 > 500
GROUP BY s.suburb_name, s.territorial_authority
HAVING supermarkets > 0 AND schools > 0
ORDER BY supermarkets DESC, schools DESC;
```

## Sample questions

Paste each as a separate sample question in the UI.

1. Which Auckland suburbs have median weekly rent under $700 and population above 1,000?
2. Show me the 10 most affordable TAs by mortgage affordability index in the most recent quarter.
3. How has the mortgage affordability index for Auckland trended since 2010?
4. Which suburbs are reachable within 30 minutes by transit from Britomart?
5. Which TAs saw rent grow more than 8% year-on-year but median income grow less than 3%?
6. Tell me about Onehunga North East — rent, income, crime, flood risk.
7. Which SA2s have both a supermarket and a primary school within their boundary?
8. Compare Mt Albert and Sandringham on every dimension you have data for.

---

## How Genie reads our semantic layer

Genie's understanding of "rent", "income", "Auckland", etc. comes from **three sources**:

1. **Unity Catalog table + column comments.** Every gold pipeline's `@dlt.table(comment=...)` and per-column comment lands in UC metadata, and Genie reads it. This is why each pipeline's gold notebook is verbose: those comments ARE the synonyms-and-glossary layer for free.
2. **The Instructions block.** Cross-table context that doesn't fit on any single column: spatial-grain framing, synonyms, NZ-specific caveats.
3. **Joins / Common SQL Expressions / SQL queries & functions sections.** Structured knowledge — relationships, named business concepts, example query patterns. Genie picks the right section per question.

If a question should land cleanly but doesn't, the fix order is:

1. **Look at the SQL Genie generated.** Usually the answer is "Genie joined wrong tables" or "picked wrong column" — fixable by tightening the relevant column comment or adding a Join.
2. **Check column comments** in the gold notebook. Make them more verbose or add synonyms.
3. **Update Instructions** if the issue is cross-table.
4. **Add an example query** to SQL queries & functions demonstrating the pattern.

Each fix is a small PR; the data layer doesn't need to change.

## Refreshing the space

UI-managed for now. Edits live in Terraform (`terraform/envs/dev/main.tf` `local.genie_*`) so the diff is version-controlled, then mirror manually in the UI:

- **Adding / removing a table**: do it in the UI's Tables tab. Mirror in `local.genie_tables`.
- **Updating instructions / synonyms**: edit `local.genie_instructions` in Terraform. Copy the new value, paste into the UI's Instructions field.
- **Joins / SQL expressions / example queries / sample questions**: same pattern — Terraform is the canonical version.

When Terraform/DABs support lands, the next apply will replace whatever's in the UI with what's in the locals, so keeping them in sync is forward-compatible.

## Verifying the space works

Open the space in a browser and try a sample question. Programmatically — from a Databricks notebook:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
space_id = "<the genie_space_id from the URL>"
result = w.genie.start_conversation_and_wait(
    space_id=space_id,
    content="Tell me about Onehunga North East — rent, income, crime.",
)
print(result.attachments[0].query.query)         # the SQL Genie generated
print(result.attachments[0].query.description)    # Genie's natural-language answer
```

## When Terraform support lands

Track [databricks/cli#4191](https://github.com/databricks/cli/pull/4191) and the Terraform provider release notes. When `databricks_genie_space` (or DAB equivalent) ships:

1. Restore `terraform/modules/genie/` from this PR's git history (or write a new module against whatever the eventual resource looks like).
2. Wire the `local.genie_*` blocks straight into the module — they're already structured the right way (joins as objects, expressions as objects, queries as objects).
3. Run `terraform import` to adopt the manually-created space into state, or destroy and re-create.

## Related docs

- [`lakehouse-gold-schema.md`](lakehouse-gold-schema.md) — column-level definitions of every table in the space
- [`agent-tool-extension-guide.md`](agent-tool-extension-guide.md) — how the agent's `query_genie` tool calls into this space
- [`conventions.md`](conventions.md) — naming conventions for gold tables (Genie depends on these)
- [`personas.md`](personas.md) — internal-framing personas (NOT in Genie content)
- [`runbook.md`](runbook.md) — operational steps including credential rotation
