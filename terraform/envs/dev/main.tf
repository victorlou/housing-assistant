locals {
  name_prefix = "${var.project_tag}-${var.environment}"
}

# ─────────────────────────────────────────────────────────────────────
# Identity. The jobs service principal owns pipelines and ingestion.
# The app gets its own auto-created service principal (see app module).
# ─────────────────────────────────────────────────────────────────────
module "identity" {
  source      = "../../modules/identity"
  project_tag = var.project_tag
  environment = var.environment
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
# Lakebase. Managed Postgres for user state.
# ─────────────────────────────────────────────────────────────────────
module "lakebase" {
  source        = "../../modules/lakebase"
  project_tag   = var.project_tag
  instance_name = local.name_prefix
  capacity      = var.lakebase_capacity
}

# ─────────────────────────────────────────────────────────────────────
# App. Databricks App and the warehouse binding it depends on.
# ─────────────────────────────────────────────────────────────────────
module "app" {
  source       = "../../modules/app"
  project_tag  = var.project_tag
  app_name     = local.name_prefix
  warehouse_id = module.compute.warehouse_id
}

# ─────────────────────────────────────────────────────────────────────
# Cross-cutting grants and permissions. We keep these here so each module
# stays a pure resource factory and the wiring is visible at the top level.
# ─────────────────────────────────────────────────────────────────────

# Warehouse: jobs SP and app SP can both use it.
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
}

# Catalog usage: both SPs need to traverse the catalog.
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

# Gold schema: the app reads, the jobs SP writes (write grant lives in catalog module).
resource "databricks_grant" "gold_app_read" {
  schema     = "${module.catalog.catalog_name}.gold"
  principal  = module.app.app_service_principal_client_id
  privileges = ["USE_SCHEMA", "SELECT"]
}

# App schema: the app reads + writes its own user state.
resource "databricks_grant" "app_state_rw" {
  schema     = "${module.catalog.catalog_name}.app"
  principal  = module.app.app_service_principal_client_id
  privileges = ["USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
}
