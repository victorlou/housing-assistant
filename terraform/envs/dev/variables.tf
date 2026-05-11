variable "databricks_host" {
  description = "Databricks workspace URL, e.g. https://<workspace>.cloud.databricks.com"
  type        = string
}

variable "databricks_token" {
  description = "Databricks personal access token"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region hosting the workspace"
  type        = string
  default     = "us-west-2"
}

variable "env" {
  description = "Environment label applied to all resource names and tags"
  type        = string
  default     = "dev"
}

variable "catalog_name" {
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
