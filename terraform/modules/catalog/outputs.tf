output "uc_catalog_name" {
  value       = data.databricks_catalog.target.name
  description = "Unity Catalog where Housing Assistant objects live."
}

output "tenancy_bonds_volume_name" {
  value       = databricks_volume.tenancy_bonds.name
  description = "Managed volume name (under bronze)."
}

output "tenancy_bonds_volume_id" {
  value       = databricks_volume.tenancy_bonds.id
  description = "Three-part UC identifier catalog.schema.volume."
}

output "tenancy_bonds_files_path" {
  value       = "/Volumes/${data.databricks_catalog.target.name}/${databricks_schema.layer["bronze"].name}/${databricks_volume.tenancy_bonds.name}"
  description = "Workspace file path prefix for databricks fs cp and uploads."
}

output "linz_nz_addresses_volume_name" {
  value       = databricks_volume.linz_nz_addresses.name
  description = "Managed volume name (under bronze)."
}

output "linz_nz_addresses_volume_id" {
  value       = databricks_volume.linz_nz_addresses.id
  description = "Three-part UC identifier catalog.schema.volume."
}

output "linz_nz_addresses_files_path" {
  value       = "/Volumes/${data.databricks_catalog.target.name}/${databricks_schema.layer["bronze"].name}/${databricks_volume.linz_nz_addresses.name}"
  description = "Workspace file path prefix for LINZ address JSONL landings."
}
