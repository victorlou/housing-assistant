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
# Creates the Postgres project, service-principal-backed Postgres role, and
# application database. Migrations are handled separately below.
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
  source                          = "../../modules/app"
  project_tag                     = var.project_tag
  app_name                        = local.name_prefix
  warehouse_id                    = module.compute.warehouse_id
  lakebase_branch_name            = module.lakebase.production_branch_name
  lakebase_database_resource_name = module.lakebase.database_resource_name

  depends_on = [module.compute, module.lakebase]
}

# Client secret used by the migration step to authenticate Databricks CLI
# commands as the Databricks App service principal. This keeps the Lakebase
# database credential subject aligned with the Postgres username.
resource "databricks_service_principal_secret" "app" {
  service_principal_id = module.app.app_service_principal_id

  depends_on = [module.app]
}

# ─────────────────────────────────────────────────────────────────────
# Lakebase migration. Runs after both lakebase and app are ready and only
# applies schema.sql using the Databricks App service-principal identity.
# ─────────────────────────────────────────────────────────────────────
module "lakebase_migration" {
  source                              = "../../modules/lakebase_migration"
  production_branch_name              = module.lakebase.production_branch_name
  production_endpoint_name            = module.lakebase.production_endpoint_name
  postgres_database_name              = module.lakebase.database_name
  app_service_principal_client_id     = module.app.app_service_principal_client_id
  app_service_principal_client_secret = databricks_service_principal_secret.app.secret
  databricks_host                     = var.databricks_host

  depends_on = [module.lakebase, module.app, databricks_service_principal_secret.app]
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
  catalog    = module.catalog.catalog_name
  principal  = module.identity.admins_group_display_name
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

# Admin group: full data access on every schema. Members get this by being
# added to the group in the account console (not Terraform).
locals {
  admin_schema_privileges = [
    "USE_SCHEMA",
    "SELECT",
    "MODIFY",
    "CREATE_TABLE",
    "CREATE_VOLUME",
    "READ_VOLUME",
    "WRITE_VOLUME",
  ]
}

resource "databricks_grant" "admins_schemas" {
  for_each   = module.catalog.schema_names
  schema     = each.value
  principal  = module.identity.admins_group_display_name
  privileges = local.admin_schema_privileges
}
