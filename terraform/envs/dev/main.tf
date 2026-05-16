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
# ─────────────────────────────────────────────────────────────────────
module "lakebase" {
  source       = "../../modules/lakebase"
  project_id   = local.name_prefix
  display_name = "Housing Assistant ${title(var.environment)}"
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

# Note on secrets: the secret scope `housing-assistant` is provisioned by the
# `secrets` module above, but individual secret VALUES are managed out of
# band via the Databricks CLI. See docs/runbook.md ("Managing per-source API
# keys") for the commands. Keeping the values out of Terraform state means
# they live only in the Databricks secret vault, not on developer laptops.
