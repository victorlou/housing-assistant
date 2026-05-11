output "catalog_name" {
  description = "Catalog name."
  value       = databricks_catalog.main.name
}

output "schema_names" {
  description = "Map of schema name to fully qualified id."
  value       = { for k, s in databricks_schema.schemas : k => s.id }
}

output "bronze_volumes" {
  description = "Map of volume short name to full UC path."
  value = {
    for k, v in databricks_volume.bronze :
    k => "/Volumes/${v.catalog_name}/${v.schema_name}/${v.name}"
  }
}
