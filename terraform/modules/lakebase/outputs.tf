output "project_name" {
  description = "Postgres API resource name (e.g. projects/housing-assistant-dev). Used as the parent for branch and endpoint resources."
  value       = databricks_postgres_project.main.name
}

output "project_id" {
  description = "Lakebase project ID — the lowercase identifier used in CLI paths and the UI."
  value       = var.project_id
}

output "production_branch_name" {
  description = "Postgres API name of the auto-created production branch."
  value       = local.production_branch_name
}

output "production_endpoint_name" {
  description = "Postgres API name of the auto-created primary endpoint on the production branch."
  value       = local.production_endpoint_name
}

output "database_name" {
  description = "Postgres database name (use as PGDATABASE in agents/.env)."
  value       = local.postgres_database_name
}

output "database_resource_name" {
  description = "Full Lakebase API resource name for the application database."
  value       = databricks_postgres_database.main.name
}

output "role_name" {
  description = "Postgres role name — the SP application ID (use as PGUSER in agents/.env)."
  value       = databricks_postgres_role.main.spec.postgres_role
}

output "role_resource_name" {
  description = "Full Lakebase API resource name for the database role."
  value       = databricks_postgres_role.main.name
}
