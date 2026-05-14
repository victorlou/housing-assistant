variable "project_tag" {
  description = "Project tag applied to catalog and schema properties."
  type        = string
}

variable "catalog_name" {
  description = "Unity Catalog name."
  type        = string
}

variable "jobs_principal_name" {
  description = "Application ID of the jobs service principal — gets read/write on bronze/silver/gold."
  type        = string
}
