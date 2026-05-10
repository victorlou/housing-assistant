variable "uc_catalog_name" {
  type        = string
  description = "Existing Unity Catalog to attach bronze/silver/gold/app and the tenancy_bonds volume to. Defaults to workspace (required for accounts where new catalogs must be created with Default Storage in the UI). Use housing only after that catalog exists."
  default     = "workspace"
}

variable "tenancy_bonds_volume_name" {
  type        = string
  description = "Managed volume under bronze for raw tenancy bond files."
}

variable "tenancy_bonds_volume_comment" {
  type        = string
  description = "Volume description in UC."
}

variable "data_principal_names" {
  type        = list(string)
  default     = []
  description = "Principals granted bronze DDL and READ/WRITE on the tenancy_bonds volume. No catalog-level grants are applied (avoids overwriting ACLs on shared catalogs like workspace)."
}

variable "layer_schema_names" {
  type        = list(string)
  default     = ["bronze", "silver", "gold", "app"]
  description = "Schemas to create under the catalog."
}
