locals {
  tags = {
    project = "housing-assistant"
    env     = var.env
  }
}

# ---------------------------------------------------------------------------
# Secret scope
# (full implementation tracked in modules/secrets)
# ---------------------------------------------------------------------------

module "secrets" {
  source = "../../modules/secrets"

  scope_name = var.secret_scope
  env        = var.env
  tags       = local.tags
}

# ---------------------------------------------------------------------------
# Lakebase — managed Postgres OLTP + Unity Catalog federation
#
# Provisions:
#   • databricks_database_instance  (the Postgres instance)
#   • null_resource schema          (runs sql/schema.sql via psql)
#   • databricks_connection         (UC foreign connection)
#   • databricks_schema housing.app (federated schema in UC)
#
# After apply, housing.app exposes: users, user_constraints, saved_searches,
# alerts, conversation_turns — readable by Genie and the AI/BI dashboard.
# ---------------------------------------------------------------------------

module "lakebase" {
  source = "../../modules/lakebase"

  env            = var.env
  catalog_name   = module.catalog.catalog_name
  capacity       = var.lakebase_capacity
  admin_user     = var.lakebase_admin_user
  admin_password = var.lakebase_admin_password
  tags           = local.tags

  depends_on = [module.catalog]
}

# ---------------------------------------------------------------------------
# Outputs useful for agent wiring and runbook ops
# ---------------------------------------------------------------------------

output "lakebase_host" {
  description = "Postgres host — paste into agents/.env"
  value       = module.lakebase.host
}

output "lakebase_port" {
  value = module.lakebase.port
}

output "lakebase_dbname" {
  value = module.lakebase.dbname
}

output "lakebase_instance_uid" {
  description = "Used with: databricks database-instances stop <uid>"
  value       = module.lakebase.instance_uid
}

output "uc_connection_name" {
  description = "UC connection name for housing.app federation"
  value       = module.lakebase.connection_name
}
