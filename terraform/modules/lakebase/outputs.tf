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
  description = "Full Lakebase API resource name for the application database, e.g. projects/<project>/branches/production/databases/<database_id>."
  value       = local.database_resource_name
}
