output "app_name" {
  description = "App name."
  value       = databricks_app.main.name
}

output "app_url" {
  description = "Public URL of the app."
  value       = databricks_app.main.url
}

output "app_service_principal_client_id" {
  description = "Client ID (UUID) of the Databricks App's auto-created service principal. The app resource binding grants this identity CAN_CONNECT_AND_CREATE on Lakebase."
  value       = databricks_app.main.service_principal_client_id
}

output "app_service_principal_id" {
  description = "Numeric Databricks ID of the Databricks App's auto-created service principal."
  value       = databricks_app.main.service_principal_id
}
