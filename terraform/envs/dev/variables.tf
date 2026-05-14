variable "databricks_host" {
  description = "Workspace URL, e.g. https://dbc-xxxxx.cloud.databricks.com. May be left empty if DATABRICKS_HOST is set."
  type        = string
  default     = ""
}

variable "databricks_profile" {
  description = "Databricks CLI profile to authenticate as. May be left empty if DATABRICKS_HOST + DATABRICKS_TOKEN are set."
  type        = string
  default     = ""
}

variable "project_tag" {
  description = "Tag applied to every resource for cost tracking and discovery."
  type        = string
  default     = "housing-assistant"
}

variable "environment" {
  description = "Short environment name used as a suffix for resources that share a workspace."
  type        = string
  default     = "dev"
}

variable "catalog_name" {
  description = "Unity Catalog name."
  type        = string
  default     = "housing"
}
