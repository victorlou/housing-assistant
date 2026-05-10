output "scope_name" {
  description = "Secret scope name."
  value       = databricks_secret_scope.main.name
}
