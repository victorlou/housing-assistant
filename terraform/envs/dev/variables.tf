variable "uc_catalog_name" {
  type        = string
  default     = "workspace"
  description = "Existing UC catalog for Housing Assistant schemas and volume. Default workspace suits Default Storage accounts; set to housing after creating that catalog in the UI."
}

variable "data_principal_names" {
  type        = list(string)
  default     = []
  description = "Optional. Principals granted bronze DDL and tenancy_bonds volume read/write (no catalog-level grants)."
}
