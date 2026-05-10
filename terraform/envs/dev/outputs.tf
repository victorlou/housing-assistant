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

output "lakebase_instance_name" {
  description = "Lakebase database instance name."
  value       = module.lakebase.instance_name
}

output "lakebase_read_write_dns" {
  description = "Lakebase read-write DNS endpoint."
  value       = module.lakebase.read_write_dns
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

output "secret_scope_name" {
  description = "Databricks-backed secret scope name."
  value       = module.secrets.scope_name
}
