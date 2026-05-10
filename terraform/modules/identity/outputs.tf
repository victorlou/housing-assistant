output "jobs_application_id" {
  description = "UUID of the jobs service principal — use as the principal in grants and permissions."
  value       = databricks_service_principal.jobs.application_id
}

output "jobs_id" {
  description = "Numeric Databricks ID of the jobs service principal."
  value       = databricks_service_principal.jobs.id
}

output "jobs_display_name" {
  description = "Display name of the jobs service principal."
  value       = databricks_service_principal.jobs.display_name
}
