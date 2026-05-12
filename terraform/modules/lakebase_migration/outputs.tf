output "schema_migration_id" {
  description = "ID of the Lakebase schema migration null_resource."
  value       = null_resource.schema_migration.id
}
