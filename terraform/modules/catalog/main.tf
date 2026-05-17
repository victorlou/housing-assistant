locals {
  schemas = ["bronze", "silver", "gold", "app"]

  # Volumes per source. The pipelines append more over time; this is the seed.
  # Domain-organized, not provider-organized. Each volume holds raw landings
  # for one functional area; pipelines distinguish sources within via folder
  # structure + a `_source` column. Add a new volume here only when the new
  # ingestion actually exists — we don't pre-provision speculative volumes.
  bronze_volumes = [
    "gtfs_files",                    # NZ transit feeds (AT, Metlink, BUSIT, Metroinfo)
    "places_files",                  # Stats NZ SA2 polygons (+ future school zones, amenity points)
    "census_2023_files",             # 2023 Census SA2 ArcGIS landings
    "linz_nz_addresses_files",       # LINZ NZ Addresses WFS JSONL
    "crime_files",                   # NZ Police Tableau CSV landings (police_recorded_crime/)
    "prices_files",                  # RBNZ HPI (NZ-aggregate price index time series)
    "housing_indicators_files",      # HUD Local Housing Statistics (TA-level prices, rents, affordability, MSD)
    "flood_files",                   # Regional flood hazard ArcGIS JSONL landings
    "amenities_files",               # Amenity POIs (supermarkets, schools, hospitals, parks) extracted from OSM
  ]
}

resource "databricks_catalog" "main" {
  name           = var.catalog_name
  comment        = "Housing Assistant lakehouse"
  isolation_mode = "ISOLATED"

  properties = {
    project = var.project_tag
  }

  # In Default Storage workspaces, Databricks auto-allocates storage_root when
  # the catalog is created via the UI. Terraform's databricks_catalog resource
  # cannot trigger that path itself (open issue: databricks/cli#4513), so we
  # rely on a manual UI create + `terraform import`. Once imported, ignore
  # storage_root drift — any change to it would force replacement and fail.
  lifecycle {
    ignore_changes = [storage_root]
  }
}

resource "databricks_schema" "schemas" {
  for_each     = toset(local.schemas)
  catalog_name = databricks_catalog.main.name
  name         = each.key
  comment      = "Housing Assistant ${each.key} layer"

  properties = {
    project = var.project_tag
    layer   = each.key
  }
}

resource "databricks_volume" "bronze" {
  for_each     = toset(local.bronze_volumes)
  catalog_name = databricks_catalog.main.name
  schema_name  = databricks_schema.schemas["bronze"].name
  name         = each.key
  volume_type  = "MANAGED"
  comment      = "Raw landings for the ${replace(each.key, "_files", "")} source"
}

# Jobs SP grants on the lakehouse layers. The app SP grants are wired at the env
# level so this module stays a pure resource factory.
#
# DLT in Unity Catalog distinguishes two flavours of `dlt.table`:
#   - streaming reads        → STREAMING TABLE   (needs CREATE_TABLE)
#   - batch reads (read.table) → MATERIALIZED VIEW (needs CREATE_MATERIALIZED_VIEW)
# Silver/gold are MV-heavy. Bronze is streaming-only today but we grant the MV
# privilege there too for futureproofing — costs nothing.
resource "databricks_grant" "jobs_bronze" {
  schema     = databricks_schema.schemas["bronze"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW", "CREATE_VOLUME", "READ_VOLUME", "WRITE_VOLUME", "SELECT"]
}

resource "databricks_grant" "jobs_silver" {
  schema     = databricks_schema.schemas["silver"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW", "CREATE_VOLUME", "SELECT"]
}

resource "databricks_grant" "jobs_gold" {
  schema     = databricks_schema.schemas["gold"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW", "CREATE_VOLUME", "SELECT"]
}
