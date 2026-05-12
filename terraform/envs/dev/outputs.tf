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

output "lakebase_branch_name" {
  description = "Postgres API name of the Lakebase production branch."
  value       = module.lakebase.production_branch_name
}

output "lakebase_database_name" {
  description = "Postgres database name created for application state."
  value       = module.lakebase.database_name
}

output "lakebase_database_resource_name" {
  description = "Full Lakebase API resource name for the application database."
  value       = module.lakebase.database_resource_name
}

output "app_url" {
  description = "Public URL of the Databricks App."
  value       = module.app.app_url
}

output "app_service_principal_client_id" {
  description = "Client ID of the Databricks App's auto-created service principal. The app resource binding grants this identity CAN_CONNECT_AND_CREATE on Lakebase."
  value       = module.app.app_service_principal_client_id
}

output "jobs_service_principal_application_id" {
  description = "Application ID of the jobs service principal."
  value       = module.identity.jobs_application_id
}

output "secret_scope_name" {
  description = "Databricks-backed secret scope name."
  value       = module.secrets.scope_name
}
