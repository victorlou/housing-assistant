output "warehouse_id" {
  description = "SQL warehouse ID."
  value       = databricks_sql_endpoint.main.id
}

output "warehouse_name" {
  description = "SQL warehouse display name."
  value       = databricks_sql_endpoint.main.name
}

output "warehouse_jdbc_url" {
  description = "JDBC URL for connecting external tools."
  value       = databricks_sql_endpoint.main.jdbc_url
}

output "warehouse_http_path" {
  description = "HTTP path used by the SQL connector."
  value       = databricks_sql_endpoint.main.odbc_params[0].path
}
