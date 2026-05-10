output "instance_name" {
  description = "Lakebase instance name."
  value       = databricks_database_instance.main.name
}

output "instance_uid" {
  description = "Lakebase instance UID — stable identifier."
  value       = databricks_database_instance.main.uid
}

output "read_write_dns" {
  description = "Postgres read-write DNS endpoint."
  value       = databricks_database_instance.main.read_write_dns
}

output "state" {
  description = "Current state of the instance."
  value       = databricks_database_instance.main.state
}
