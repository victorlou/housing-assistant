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
<<<<<<< HEAD
  description = "Unity Catalog catalog name for the lakehouse"
  type        = string
  default     = "housing"
}

variable "secret_scope" {
  description = "Databricks-backed secret scope name"
  type        = string
  default     = "housing-assistant"
}

variable "lakebase_capacity" {
  description = "Lakebase instance capacity units"
  type        = number
  default     = 1
}

variable "lakebase_admin_user" {
  description = "Initial Postgres admin username for Lakebase"
  type        = string
  default     = "housing_admin"
}

variable "lakebase_admin_password" {
  description = "Initial Postgres admin password for Lakebase (stored in secret scope after first apply)"
  type        = string
  sensitive   = true
}

variable "sp_jobs_name" {
  description = "Display name of the service principal used by jobs and pipelines"
  type        = string
  default     = "sp-housing-jobs"
}

variable "sp_app_name" {
  description = "Display name of the service principal used by the Databricks App"
  type        = string
  default     = "sp-housing-app"
}
=======
  description = "Unity Catalog name."
  type        = string
  default     = "housing"
}
>>>>>>> origin/feature/terraform-base
