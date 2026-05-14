locals {
  name_prefix = "${var.project_tag}-${var.environment}"
}

# ─────────────────────────────────────────────────────────────────────
# Identity. The jobs service principal owns pipelines and ingestion.
# The Databricks App gets its own auto-created service principal, which is
# granted Lakebase access through the app resource binding.
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
# Lakebase. Managed Postgres for user state, on the Autoscaling platform.
# Scale-to-zero is enabled as a one-time post-apply step (see runbook).
# Only creates the Postgres project; role and database are created in
# lakebase_migration after the app service principal is known.
# ─────────────────────────────────────────────────────────────────────
module "lakebase" {
  source                 = "../../modules/lakebase"
  project_id             = local.name_prefix
  display_name           = "Housing Assistant ${title(var.environment)}"
  database_id            = "${local.name_prefix}-db"
  postgres_database_name = "${replace(local.name_prefix, "-", "_")}_db"
}

# ─────────────────────────────────────────────────────────────────────
# App. Databricks App and the warehouse/Lakebase bindings it depends on.
# The app resource binding grants the app's auto-created service principal
# CAN_CONNECT_AND_CREATE on the Lakebase Autoscaling database.
# ─────────────────────────────────────────────────────────────────────
module "app" {
  source                 = "../../modules/app"
  project_tag            = var.project_tag
  app_name               = local.name_prefix
  warehouse_id           = module.compute.warehouse_id
  lakebase_branch_name   = module.lakebase.production_branch_name
  lakebase_database_name = module.lakebase.database_resource_name

  depends_on = [module.compute, module.lakebase]
}

# ─────────────────────────────────────────────────────────────────────
# Lakebase migration. Runs after both lakebase and app are ready:
# creates the Postgres role + database for the app service principal,
# then applies schema.sql.
# ─────────────────────────────────────────────────────────────────────
module "lakebase_migration" {
  source                          = "../../modules/lakebase_migration"
  production_branch_name          = module.lakebase.production_branch_name
  postgres_database_name          = module.lakebase.database_name
  database_id                     = "${local.name_prefix}-db"
  app_service_principal_client_id = module.app.app_service_principal_client_id

  depends_on = [module.lakebase, module.app]
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
