locals {
  schemas = ["bronze", "silver", "gold", "app"]

  # Volumes per source. The pipelines append more over time; this is the seed.
  bronze_volumes = [
    "tenancy_bonds_files",
    "census_files",
    "house_price_index_files",
    "gtfs_files",
    "crime_files",
    "schools_files",
    "addresses_files",
    "hazards_files",
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
resource "databricks_grant" "jobs_bronze" {
  schema     = databricks_schema.schemas["bronze"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_VOLUME", "READ_VOLUME", "WRITE_VOLUME", "SELECT"]
}

resource "databricks_grant" "jobs_silver" {
  schema     = databricks_schema.schemas["silver"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_VOLUME", "SELECT"]
}

resource "databricks_grant" "jobs_gold" {
  schema     = databricks_schema.schemas["gold"].id
  principal  = var.jobs_principal_name
  privileges = ["USE_SCHEMA", "MODIFY", "CREATE_TABLE", "CREATE_VOLUME", "SELECT"]
}
