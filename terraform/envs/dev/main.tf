module "catalog" {
  source = "../../modules/catalog"

  uc_catalog_name                   = var.uc_catalog_name
  tenancy_bonds_volume_name       = "tenancy_bonds"
  tenancy_bonds_volume_comment      = "Raw MBIE Tenancy Services bond statistics (CSV or zip landings; pipeline parses to bronze tables)."
  linz_nz_addresses_volume_name     = "linz_nz_addresses"
  linz_nz_addresses_volume_comment  = "Raw LINZ NZ Street Address exports (JSONL from WFS; pipeline reads into bronze tables)."
  data_principal_names              = var.data_principal_names
}

output "tenancy_bonds_files_path" {
  description = "Upload raw tenancy files here (Catalog UI or databricks fs cp)."
  value       = module.catalog.tenancy_bonds_files_path
}

output "tenancy_bonds_volume_id" {
  description = "Unity Catalog three-part volume name."
  value       = module.catalog.tenancy_bonds_volume_id
}

output "linz_nz_addresses_files_path" {
  description = "Upload LINZ address JSONL snapshots here (Catalog UI or databricks fs cp)."
  value       = module.catalog.linz_nz_addresses_files_path
}

output "linz_nz_addresses_volume_id" {
  description = "Unity Catalog three-part volume name for LINZ address landings."
  value       = module.catalog.linz_nz_addresses_volume_id
}

output "uc_catalog_name" {
  description = "Catalog containing bronze/silver/gold/app and the volume."
  value       = module.catalog.uc_catalog_name
}
