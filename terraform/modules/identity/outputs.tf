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

output "admins_group_display_name" {
  description = "Account-level admin group display name. Use as the principal in UC grants and warehouse permissions."
  value       = databricks_group.admins.display_name
  # Block reads of this output until the propagation cushion has elapsed,
  # so grants don't fire before UC sees the group.
  depends_on = [time_sleep.wait_for_admins_group]
}

output "admins_group_id" {
  description = "Numeric Databricks ID of the admin group."
  value       = databricks_group.admins.id
  depends_on  = [time_sleep.wait_for_admins_group]
}
