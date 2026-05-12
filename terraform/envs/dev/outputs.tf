output "catalog_name" {
  description = "Unity Catalog name."
  value       = module.catalog.catalog_name
}

output "warehouse_id" {
  description = "Serverless SQL warehouse ID."
  value       = module.compute.warehouse_id
}

output "warehouse_jdbc_url" {
  description = "JDBC URL for the SQL warehouse."
  value       = module.compute.warehouse_jdbc_url
}

output "lakebase_project_name" {
  description = "Lakebase project resource name (Postgres API)."
  value       = module.lakebase.project_name
}

output "lakebase_project_id" {
  description = "Lakebase project ID."
  value       = module.lakebase.project_id
}

output "lakebase_production_endpoint_name" {
  description = "Postgres API name of the auto-created production endpoint. Use with `databricks postgres update-endpoint` to enable scale-to-zero."
  value       = module.lakebase.production_endpoint_name
}

output "app_url" {
  description = "Public URL of the Databricks App."
  value       = module.app.app_url
}

output "app_service_principal_client_id" {
  description = "Client ID of the app's auto-created service principal."
  value       = module.app.app_service_principal_client_id
}

output "jobs_service_principal_application_id" {
  description = "Application ID of the jobs service principal."
  value       = module.identity.jobs_application_id
}

output "admins_group_display_name" {
  description = "Account-level admin group. Add yourself and teammates to it in the account console (User management → Groups) to inherit full data access."
  value       = module.identity.admins_group_display_name
}

output "secret_scope_name" {
  description = "Databricks-backed secret scope name."
  value       = module.secrets.scope_name
}
