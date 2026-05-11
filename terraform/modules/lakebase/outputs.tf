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
  value       = "${databricks_postgres_project.main.name}/branches/production"
}

output "production_endpoint_name" {
  description = "Postgres API name of the auto-created primary endpoint on the production branch."
  value       = "${databricks_postgres_project.main.name}/branches/production/endpoints/primary"
}
