output "instance_id" {
  description = "Lakebase instance resource ID"
  value       = databricks_database_instance.this.id
}

output "instance_uid" {
  description = "Lakebase instance UID (stable, used in CLI commands)"
  value       = databricks_database_instance.this.uid
}

output "host" {
  description = "Postgres host"
  value       = databricks_database_instance.this.pgconn[0].host
}

output "port" {
  description = "Postgres port"
  value       = databricks_database_instance.this.pgconn[0].port
}

output "dbname" {
  description = "Postgres database name"
  value       = databricks_database_instance.this.pgconn[0].dbname
}

output "connection_name" {
  description = "UC connection name (used when wiring agent tools)"
  value       = databricks_connection.lakebase.name
}
