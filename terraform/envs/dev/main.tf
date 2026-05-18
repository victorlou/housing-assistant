locals {
  name_prefix = "${var.project_tag}-${var.environment}"
}

# ─────────────────────────────────────────────────────────────────────
# Identity. Jobs SP at workspace level. Admin group at account level
# (UC requires account-level principals), plus the assignment that
# makes the group visible in this workspace.
# ─────────────────────────────────────────────────────────────────────
module "identity" {
  source       = "../../modules/identity"
  project_tag  = var.project_tag
  environment  = var.environment
  workspace_id = var.workspace_id

  providers = {
    databricks         = databricks
    databricks.account = databricks.account
  }
}

# ─────────────────────────────────────────────────────────────────────
# Secrets. Single Databricks-backed scope for the project.
# ─────────────────────────────────────────────────────────────────────
module "secrets" {
  source     = "../../modules/secrets"
  scope_name = var.project_tag
}

# ─────────────────────────────────────────────────────────────────────
# Lakehouse. Catalog + schemas + volumes + grants for the jobs SP.
# ─────────────────────────────────────────────────────────────────────
module "catalog" {
  source              = "../../modules/catalog"
  project_tag         = var.project_tag
  catalog_name        = var.catalog_name
  jobs_principal_name = module.identity.jobs_application_id
}

# ─────────────────────────────────────────────────────────────────────
# Compute. Serverless 2X-Small SQL warehouse with aggressive auto-stop.
# ─────────────────────────────────────────────────────────────────────
module "compute" {
  source         = "../../modules/compute"
  project_tag    = var.project_tag
  warehouse_name = local.name_prefix
}

# ─────────────────────────────────────────────────────────────────────
# Lakebase. Managed Postgres for user state, on the Autoscaling platform.
# Scale-to-zero is enabled as a one-time post-apply step (see runbook).
# Creates the Postgres project, app service-principal-backed role, and
# application database. Schema migrations are managed by Drizzle ORM.
# ─────────────────────────────────────────────────────────────────────
module "lakebase" {
  source                          = "../../modules/lakebase"
  project_id                      = local.name_prefix
  display_name                    = "Housing Assistant ${title(var.environment)}"
  database_id                     = "${local.name_prefix}-db"
  postgres_database_name          = "${replace(local.name_prefix, "-", "_")}_db"
  app_service_principal_client_id = module.app.app_service_principal_client_id
}

# Preserve Terraform state addresses when merging the old lakebase_migration
# module resources into the lakebase module.
moved {
  from = module.lakebase_migration.databricks_postgres_role.app
  to   = module.lakebase.databricks_postgres_role.app
}

moved {
  from = module.lakebase_migration.databricks_postgres_database.main
  to   = module.lakebase.databricks_postgres_database.main
}

# ─────────────────────────────────────────────────────────────────────
# App. Databricks App and the warehouse/Lakebase bindings it depends on.
# The app resource binding grants the app's auto-created service principal
# CAN_CONNECT_AND_CREATE on the Lakebase Autoscaling database.
# ─────────────────────────────────────────────────────────────────────
module "app" {
  source                          = "../../modules/app"
  project_tag                     = var.project_tag
  app_name                        = local.name_prefix
  warehouse_id                    = module.compute.warehouse_id
  lakebase_branch_name            = module.lakebase.production_branch_name
  lakebase_database_resource_name = module.lakebase.database_resource_name

}

# ─────────────────────────────────────────────────────────────────────
# Cross-cutting grants and permissions. We keep these here so each module
# stays a pure resource factory and the wiring is visible at the top level.
# ─────────────────────────────────────────────────────────────────────

# Warehouse: jobs SP, app SP, and the admin group can all use it.
# Admins get CAN_MANAGE so they can pause it and grant access.
resource "databricks_permissions" "warehouse" {
  sql_endpoint_id = module.compute.warehouse_id

  access_control {
    service_principal_name = module.identity.jobs_application_id
    permission_level       = "CAN_USE"
  }

  access_control {
    service_principal_name = module.app.app_service_principal_client_id
    permission_level       = "CAN_USE"
  }

  access_control {
    group_name       = module.identity.admins_group_display_name
    permission_level = "CAN_MANAGE"
  }
}

# Catalog usage: the SPs and the admin group all need to traverse the catalog.
resource "databricks_grant" "catalog_usage_jobs" {
  catalog    = module.catalog.catalog_name
  principal  = module.identity.jobs_application_id
  privileges = ["USE_CATALOG"]
}

resource "databricks_grant" "catalog_usage_app" {
  catalog    = module.catalog.catalog_name
  principal  = module.app.app_service_principal_client_id
  privileges = ["USE_CATALOG"]
}

resource "databricks_grant" "catalog_usage_admins" {
  catalog   = module.catalog.catalog_name
  principal = module.identity.admins_group_display_name
  # Admins are co-owners of the project. They need:
  #   - ALL_PRIVILEGES: covers everything DATA-related (SELECT, MODIFY,
  #     CREATE_*, etc. on objects below the catalog).
  #   - MANAGE: separate UC privilege that grants the right to grant /
  #     revoke privileges to other principals. ALL_PRIVILEGES explicitly
  #     does NOT include MANAGE per Databricks UC docs.
  # Without MANAGE, co-owners couldn't adjust the jobs SP's grants when
  # adding a new pipeline. Both privileges = full co-owner posture.
  privileges = ["ALL_PRIVILEGES", "MANAGE"]
}

# Gold schema: the app reads, the jobs SP writes (write grant lives in catalog module).
# Reference the schema via the module output so Terraform infers the dependency
# on the schema resource and doesn't race ahead of its creation.
resource "databricks_grant" "gold_app_read" {
  schema     = module.catalog.schema_names["gold"]
  principal  = module.app.app_service_principal_client_id
  privileges = ["USE_SCHEMA", "SELECT"]
}

# App schema: the app reads + writes its own user state.
resource "databricks_grant" "app_state_rw" {
  schema     = module.catalog.schema_names["app"]
  principal  = module.app.app_service_principal_client_id
  privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
}

# Admin group: full access on every schema, including the right to grant
# privileges to other principals. Members get this by being added to the
# group in the account console (not Terraform). ALL_PRIVILEGES + MANAGE
# rather than an explicit privilege list — admins are co-owners and
# shouldn't need a Terraform change to grant a new SP access to a schema
# or run admin-y maintenance. ALL_PRIVILEGES alone doesn't include MANAGE
# (that's a separate UC privilege per Databricks docs), so we list both.
resource "databricks_grant" "admins_schemas" {
  for_each   = module.catalog.schema_names
  schema     = each.value
  principal  = module.identity.admins_group_display_name
  privileges = ["ALL_PRIVILEGES", "MANAGE"]
}

# Note on secrets: the secret scope `housing-assistant` is provisioned by the
# `secrets` module above, but individual secret VALUES are managed out of
# band via the Databricks CLI. See docs/runbook.md ("Managing per-source API
# keys") for the commands. Keeping the values out of Terraform state means
# they live only in the Databricks secret vault, not on developer laptops.

# ─────────────────────────────────────────────────────────────────────
# Genie space. Natural-language Q&A surface over `housing.gold.*`.
#
# IMPORTANT — manual UI creation. The Databricks Terraform provider
# (1.115 as of writing) does NOT support Genie spaces as a resource.
# DABs support is in flight (databricks/cli#4191) but not landed. So the
# space is created manually via the workspace UI; see docs/genie-space.md
# for the click path + paste-ready content.
#
# The `local.genie_*` values below are the source-of-truth for the
# curation content (tables, instructions, sample questions). The doc
# embeds them too — when you tweak instructions here, copy the new
# value into the UI; when DABs/Terraform support lands we'll wire these
# straight into the resource without rewriting them.
# ─────────────────────────────────────────────────────────────────────
locals {
  # Fully-qualified gold tables surfaced to Genie. Order is cosmetic — Genie
  # picks tables based on user-question relevance, not declaration order.
  genie_tables = [
    for t in [
      # Headline dim + main fact (suburb-grain questions)
      "suburb",
      "suburb__year",
      # Time-series at coarser grain (TA / region trends)
      "ta__month",
      "ta__quarter",
      "region__quarter",
      # Spatial fabric — Genie joins through these for "near X" / "commute to Y"
      "h3_cell",
      "isochrone",
      "amenity__h3",
      "hazard",
      # Transit + address — supporting context for commute / proximity questions
      "transit_stop",
      "transit_route",
      "nz_address",
    ] : "${module.catalog.catalog_name}.gold.${t}"
  ]

  # Instructions are intentionally short. Genie's own warning: "Long
  # instructions can limit the amount of other information that Genie can
  # learn from." Anything joinable / pivotable / showable as an example
  # query goes in the dedicated UI sections (Joins / Common SQL Expressions
  # / SQL queries & functions) — see local.genie_joins etc. below.
  #
  # We do NOT mention named personas ("Sarah", "Daniel") here — Genie would
  # cheerfully greet users by those names. Personas are internal-framing
  # docs only (see docs/personas.md).
  genie_instructions = <<-EOT
    Natural-language Q&A over New Zealand housing affordability data. Data lives at three spatial grains; pick the right one for the question and cross-grain joins are spelled out in the Joins section.

    - **Suburb** = Stats NZ SA2 2023 area (~2,395). Joined via `suburb_id` (6-digit code). Primary grain. Tables: `suburb`, `suburb__year`.
    - **Territorial authority (TA)** = council area (67 of them). Joined via `ta_name`. Tables: `ta__month`, `ta__quarter`.
    - **Region** = Stats NZ region (16). Joined via `region`. Tables: `region__quarter`.
    - **H3 cell** = res-8 hexagon (~0.7 km²) used as the universal spatial key. `h3_cell.suburb_id` bridges any H3-keyed fact to a suburb.

    ## Synonyms

    - "rent" / "weekly rent" → `suburb__year.median_weekly_rent` (NZD/week, 2023 census) or `ta__month.median_rent_nzd` (TA-monthly).
    - "income" → `suburb__year.median_household_income` (NZD/year, before tax).
    - "crime" / "victimisations" → `suburb__year.total_victimisations_2023`.
    - "crowded" → `suburb__year.percent_crowded`.
    - "homeowner" / "owner-occupier" → `suburb__year.owner_occupier_pct`.
    - "HPI" / "house price index" → `region__quarter.hpi` or `ta__month.current_hpi`.
    - "affordability" → one of the `*_affordability_index` columns on `ta__quarter`. Higher = less affordable.
    - "flood risk" → any `in_flood_*` boolean on `hazard`.
    - "commute" / "reachable in N minutes" → `isochrone.travel_minutes`.

    ## Filters to remember

    - **Residential queries**: filter `suburb.population_2023 > 500` (excludes ~600 non-residential SA2s — harbour, EEZ, airport, etc.).
    - **Current state per TA**: `ta__month` is sparse — Sales/Bonds rows only on HUD snapshot dates, MSD rows monthly. Use `ORDER BY date DESC LIMIT 1 per ta_name`.
    - **Origin from lat/lon**: `isochrone.origin_h3 = h3_longlatash3(lon, lat, 8)`. The matrix is symmetric.

    ## NZ caveats

    - "Auckland" is a single TA covering ~580 SA2s (post-supercity amalgamation). Every Auckland SA2 shares the same `ta__month` / `ta__quarter` row.
    - Colloquial suburb names don't always match one SA2 — "Onehunga" is split into Onehunga North East / North West / South East. When the user names a suburb, prefer `suburb_name LIKE '%X%'`.
    - TA names use macrons (Ōtorohanga, Hawke's Bay). Match case-insensitively against user input.

    ## Honest limitations

    - Crime is only 2023 at suburb grain. For monthly trends or offence categories, the user has to drop to `housing.silver.crime_victimisation_monthly` directly.
    - Rent / income on `suburb__year` are 2023 census snapshots. Monthly TA rent (HUD Bonds) is on `ta__month`.
    - Amenities are OSM-derived — coverage is best in Auckland / Wellington / Christchurch.
  EOT

  # Joins. The UI's "Joins" section takes Left Table, Right Table, Join
  # condition, Relationship Type (ONE_TO_ONE / ONE_TO_MANY / MANY_TO_ONE /
  # MANY_TO_MANY), and per-join Instructions.
  #
  # Relationship convention: pick the direction that puts the *parent / smaller
  # cardinality* on the Right. So "suburb (left, many cells) → h3_cell (right,
  # one cell each)" wouldn't make sense — h3_cell is the larger set. Reading
  # them as "Left → Right": "many lefts can share one right" for MANY_TO_ONE,
  # "one left has many rights" for ONE_TO_MANY. Genie matches the SQL
  # convention.
  genie_joins = [
    {
      left_table        = "suburb"
      right_table       = "suburb__year"
      join_condition    = "`suburb`.`suburb_id` = `suburb__year`.`suburb_id`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Static suburb dim joined to its time-series census + crime fact. The headline 'tell me about this suburb' join. One row per suburb on the left; potentially multiple census years on the right (today only 2023)."
    },
    {
      left_table        = "suburb"
      right_table       = "ta__month"
      join_condition    = "`suburb`.`territorial_authority` = `ta__month`.`ta_name`"
      relationship_type = "MANY_TO_MANY"
      instructions      = "Use to attribute monthly TA-level HUD metrics (HPI, sale price, weekly rent, MSD register) to a specific suburb. Many SA2s share each TA — Auckland alone has ~580. For 'current state' questions use ORDER BY date DESC LIMIT 1 per ta_name; the table is sparse, Sales/Bonds rows only appear on HUD snapshot dates."
    },
    {
      left_table        = "suburb"
      right_table       = "ta__quarter"
      join_condition    = "`suburb`.`territorial_authority` = `ta__quarter`.`ta_name`"
      relationship_type = "MANY_TO_MANY"
      instructions      = "Suburb to quarterly TA-level HUD affordability indices (deepest time series, back to 2001-Q1). Best for 'how affordable is X right now / over time' questions."
    },
    {
      left_table        = "suburb"
      right_table       = "region__quarter"
      join_condition    = "`suburb`.`region` = `region__quarter`.`region`"
      relationship_type = "MANY_TO_MANY"
      instructions      = "Suburb to RBNZ M10 quarterly HPI / sales / investment. Today every row in region__quarter carries region = 'New Zealand' (country-aggregate), so the join effectively pulls national figures. Will fill with proper region values when regional sources land."
    },
    {
      left_table        = "suburb"
      right_table       = "h3_cell"
      join_condition    = "`suburb`.`suburb_id` = `h3_cell`.`suburb_id`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Suburb to its constituent H3 res-8 cells (~4-15 cells per suburb). Use as the first hop to reach any H3-keyed fact (hazard, amenity, isochrone, transit, addresses)."
    },
    {
      left_table        = "h3_cell"
      right_table       = "hazard"
      join_condition    = "`h3_cell`.`h3_cell` = `hazard`.`h3_cell`"
      relationship_type = "ONE_TO_ONE"
      instructions      = "Cell to flood / coastal hazard booleans. To attribute risk to a whole suburb, aggregate the booleans (AVG of CAST AS INT) across the suburb's cells."
    },
    {
      left_table        = "h3_cell"
      right_table       = "amenity__h3"
      join_condition    = "`h3_cell`.`h3_cell` = `amenity__h3`.`h3_cell`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Cell to OSM amenities (supermarkets, schools, hospitals, parks, etc.). `amenity__h3.suburb_id` is also denormalised, so the bridge can be skipped when joining straight from `suburb` to `amenity__h3`."
    },
    {
      left_table        = "h3_cell"
      right_table       = "transit_stop"
      join_condition    = "`h3_cell`.`h3_cell` = `transit_stop`.`h3_cell`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Cell to GTFS public-transit stops. Useful for 'near a bus stop' / 'within walking distance of transit' questions."
    },
    {
      left_table        = "h3_cell"
      right_table       = "isochrone"
      join_condition    = "`h3_cell`.`h3_cell` = `isochrone`.`destination_h3`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Cell as a reachable destination in the isochrone matrix. Origin is derived from a workplace lat/lon via h3_longlatash3(lon, lat, 8). Filter `travel_minutes <= N` to get reachable cells. Matrix is symmetric — same cell set on both sides."
    },
    {
      left_table        = "h3_cell"
      right_table       = "nz_address"
      join_condition    = "`h3_cell`.`h3_cell` = `nz_address`.`h3_cell`"
      relationship_type = "ONE_TO_MANY"
      instructions      = "Cell to current LINZ addresses for 'near this address' / proximity questions."
    },
    {
      left_table        = "transit_stop"
      right_table       = "transit_route"
      join_condition    = "`transit_stop`.`feed_source` = `transit_route`.`feed_source`"
      relationship_type = "MANY_TO_MANY"
      instructions      = "Lightly normalised — a stop belongs to many routes via stop_times in silver; the gold view exposes feed-level lookups only."
    },
  ]

  # Boolean filters. Genie places each in a WHERE clause when a user mentions
  # the synonyms. Each is scoped to one table.
  genie_filters = [
    {
      table        = "suburb"
      name         = "is_residential"
      code         = "population_2023 > 500"
      synonyms     = "residential, where people live, livable, lived-in, real suburbs"
      instructions = "Excludes ~600 non-residential SA2s — harbour, EEZ, airport runway, industrial zones. Use for any 'where should I live' / 'compare these suburbs' question. Don't use for exhaustive geographic queries (e.g. 'list every SA2 in Auckland')."
    },
    {
      table        = "suburb__year"
      name         = "is_rent_affordable_at_median_income"
      code         = "median_weekly_rent * 52.0 <= median_household_income * 0.30"
      synonyms     = "affordable rent, rent affordable, rent under 30 percent, rent affordable to locals"
      instructions = "Standard NZ housing affordability test: median weekly rent (annualised) is no more than 30% of median household income. True / false for each suburb. Pairs naturally with `is_residential` on the suburb dim."
    },
    {
      table        = "suburb"
      name         = "is_auckland_region"
      code         = "region = 'Auckland Region'"
      synonyms     = "Auckland, in Auckland, Auckland metro, Auckland-wide"
      instructions = "Filter to suburbs in the Auckland Region (covers Auckland City + Waitākere Ranges + North Shore + Manukau-Papakura + Mangere-Otāhuhu TAs)."
    },
  ]

  # Aggregating measures. Each scoped to one table.
  genie_measures = [
    {
      table        = "suburb"
      name         = "total_population"
      code         = "SUM(population_2023)"
      synonyms     = "total population, total residents, headcount, people, residents"
      instructions = "Sum of usual-resident 2023 census population across grouped suburbs. Don't use unfiltered across the whole table — includes non-residential SA2s with near-zero population."
    },
    {
      table        = "suburb__year"
      name         = "median_weekly_rent_across_group"
      code         = "PERCENTILE(median_weekly_rent, 0.5)"
      synonyms     = "median rent, typical rent, average rent across suburbs"
      instructions = "Median of median weekly rents across grouped suburbs (e.g. 'median rent across Auckland TA'). Note this is a median-of-medians, not a true population-weighted median."
    },
    {
      table        = "suburb__year"
      name         = "total_victimisations"
      code         = "SUM(total_victimisations_2023)"
      synonyms     = "total crime, total victimisations, total recorded crime"
      instructions = "Sum of 2023 recorded victimisations across grouped suburbs. Use with caution unweighted — bigger suburbs have more crime in absolute terms. Prefer the `crime_per_1k_residents` dimension for per-capita comparisons."
    },
    {
      table        = "ta__quarter"
      name         = "latest_mortgage_affordability"
      code         = "MAX_BY(mortgage_affordability_index, quarter)"
      synonyms     = "current mortgage affordability, latest affordability, today's affordability"
      instructions = "Most recent observation of the mortgage affordability index per TA. Higher = less affordable. Use when the user asks for 'current' or 'latest' affordability."
    },
  ]

  # Per-row calculated dimensions. Each scoped to one table.
  genie_dimensions = [
    {
      table        = "suburb__year"
      name         = "owner_occupier_share"
      code         = "tenure_owned * 1.0 / NULLIF(tenure_total_stated, 0)"
      synonyms     = "homeowner share, owner-occupier share, % owners, ownership rate"
      instructions = "Share of households owning or partly owning their dwelling. Safe vs the raw `owner_occupier_pct` column because it NULL-guards when stated == 0. Between 0 and 1."
    },
    {
      table        = "suburb__year"
      name         = "crime_per_1k_residents"
      code         = "total_victimisations_2023 * 1000.0 / NULLIF(population_total, 0)"
      synonyms     = "crime rate, victimisation rate, crime per capita, crime per 1000, per-capita crime"
      instructions = "Annual recorded victimisations per 1,000 residents (2023). Use this rather than raw counts for fair cross-suburb comparison — bigger suburbs have more crime even at the same rate."
    },
    {
      table        = "suburb__year"
      name         = "affordable_weekly_rent_threshold"
      code         = "median_household_income * 0.30 / 52.0"
      synonyms     = "affordable rent ceiling, what rent locals can afford, 30 percent rent limit"
      instructions = "Maximum weekly rent considered affordable for a household at the suburb's median income (30% of weekly income — the standard NZ housing affordability ceiling)."
    },
    {
      table        = "suburb__year"
      name         = "damp_share"
      code         = "(dwellings_always_damp + dwellings_sometimes_damp) * 1.0 / NULLIF(dwellings_damp_total_stated, 0)"
      synonyms     = "damp share, damp dwellings, % damp, damp housing rate"
      instructions = "Share of dwellings reporting 'always' or 'sometimes' damp in the 2023 census. Higher = worse housing quality. Between 0 and 1."
    },
    {
      table        = "suburb__year"
      name         = "mould_share"
      code         = "dwellings_mould_a4_always * 1.0 / NULLIF(dwellings_mould_total_stated, 0)"
      synonyms     = "mould share, mouldy dwellings, % with mould"
      instructions = "Share of dwellings with A4-sized-or-larger mould always present (2023 census). Between 0 and 1."
    },
    {
      table        = "suburb__year"
      name         = "rent_to_income_ratio"
      code         = "median_weekly_rent * 52.0 / NULLIF(median_household_income, 0)"
      synonyms     = "rent burden, rent-to-income, rent share of income, how unaffordable"
      instructions = "Median weekly rent annualised, divided by median household income. > 0.30 is the standard NZ 'unaffordable' threshold. Companion to the `is_rent_affordable_at_median_income` filter."
    },
  ]

  # Example queries Genie can learn from. Each one teaches a pattern.
  genie_sql_queries = [
    {
      name        = "Suburb summary"
      description = "Headline 'tell me about this suburb' answer — rent, income, crime, demographics, plus a per-capita crime rate."
      sql         = <<-SQL
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
          AND s.suburb_name ILIKE :suburb_name_pattern
      SQL
    },
    {
      name        = "30-minute transit reach from a lat/lon"
      description = "Which suburbs are reachable within N minutes by transit from a given workplace lat/lon. The isochrone matrix is symmetric, so origin_h3 is derived from the workplace coords."
      sql         = <<-SQL
        SELECT DISTINCT s.suburb_name, MIN(i.travel_minutes) AS min_travel_minutes
        FROM housing.gold.isochrone i
        JOIN housing.gold.h3_cell   c ON c.h3_cell   = i.destination_h3
        JOIN housing.gold.suburb    s ON s.suburb_id = c.suburb_id
        WHERE i.origin_h3 = h3_longlatash3(:origin_lon, :origin_lat, 8)
          AND i.travel_minutes <= :max_minutes
          AND s.population_2023 > 500
        GROUP BY s.suburb_name
        ORDER BY min_travel_minutes, s.suburb_name
      SQL
    },
    {
      name        = "Flood + coastal risk for a suburb"
      description = "Aggregate hazard booleans across all H3 cells covering a suburb. Returns the share of cells flagged for each risk."
      sql         = <<-SQL
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
        GROUP BY s.suburb_name
      SQL
    },
    {
      name        = "TA affordability trend"
      description = "25-year trajectory of HUD's four affordability indices for one or more TAs. Mortgage / rent / deposit indices plus the price-to-income ratio."
      sql         = <<-SQL
        SELECT ta_name, quarter_label, quarter,
               deposit_affordability_index,
               mortgage_affordability_index,
               rent_affordability_index,
               median_to_median_ratio
        FROM housing.gold.ta__quarter
        WHERE ta_name IN (SELECT explode(:ta_names))
        ORDER BY ta_name, quarter
      SQL
    },
    {
      name        = "Top-N most affordable TAs right now"
      description = "Ten cheapest TAs by mortgage affordability index in the most recent quarter."
      sql         = <<-SQL
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
        LIMIT 10
      SQL
    },
    {
      name        = "Latest TA monthly snapshot"
      description = "Per-TA: the most recent row from the sparse ta__month, joined to its current affordability quarter. Useful for 'current state' questions."
      sql         = <<-SQL
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
        WHERE m.ta_name <> 'New Zealand'
      SQL
    },
    {
      name        = "Suburbs with a supermarket and a school"
      description = "Residential SA2s that contain at least one supermarket AND at least one school (any year level). Useful for proximity-based shortlists."
      sql         = <<-SQL
        SELECT s.suburb_name, s.territorial_authority,
               COUNT(DISTINCT CASE WHEN a.amenity_type = 'supermarket' THEN a.osm_id END) AS supermarkets,
               COUNT(DISTINCT CASE WHEN a.amenity_type = 'school'      THEN a.osm_id END) AS schools
        FROM housing.gold.suburb       s
        JOIN housing.gold.amenity__h3  a ON a.suburb_id = s.suburb_id
        WHERE s.population_2023 > 500
        GROUP BY s.suburb_name, s.territorial_authority
        HAVING supermarkets > 0 AND schools > 0
        ORDER BY supermarkets DESC, schools DESC
      SQL
    },
  ]

  # Sample questions surfaced in the UI as one-click prompts.
  genie_sample_questions = [
    "Which Auckland suburbs have median weekly rent under $$700 and population above 1,000?",
    "Show me the 10 most affordable TAs by mortgage affordability index in the most recent quarter.",
    "How has the mortgage affordability index for Auckland trended since 2010?",
    "Which suburbs are reachable within 30 minutes by transit from Britomart?",
    "Which TAs saw rent grow more than 8% year-on-year but median income grow less than 3%?",
    "Tell me about Onehunga North East — rent, income, crime, flood risk.",
    "Which SA2s have both a supermarket and a primary school within their boundary?",
    "Compare Mt Albert and Sandringham on every dimension you have data for.",
  ]
}

# When DABs/Terraform support for Genie spaces lands, the module call lives
# here and reads from the locals above. Tracking issue: databricks/cli#4191.
