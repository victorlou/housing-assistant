output "app_name" {
  description = "App name."
  value       = databricks_app.main.name
}

output "app_url" {
  description = "Public URL of the app."
  value       = databricks_app.main.url
}

output "app_service_principal_client_id" {
  description = "Client ID (UUID) of the auto-created service principal — use as the principal in grants and permissions."
  value       = databricks_app.main.service_principal_client_id
}

output "app_service_principal_id" {
  description = "Numeric Databricks ID of the app's service principal."
  value       = databricks_app.main.service_principal_id
}
