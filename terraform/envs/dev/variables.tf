variable "databricks_host" {
  description = "Workspace URL, e.g. https://dbc-xxxxx.cloud.databricks.com. May be left empty if DATABRICKS_HOST is set."
  type        = string
  default     = ""
}

variable "databricks_profile" {
  description = "Databricks CLI profile for workspace-level authentication."
  type        = string
  default     = ""
}

variable "databricks_account_id" {
  description = "Databricks account UUID (top of the account console). Required for managing account-level groups and workspace assignments."
  type        = string
}

variable "databricks_account_profile" {
  description = "Databricks CLI profile for account-level authentication. Set up once with `databricks auth login --host https://accounts.cloud.databricks.com --account-id <UUID>`."
  type        = string
  default     = "hackathon-account"
}

variable "workspace_id" {
  description = "Numeric Databricks workspace ID (visible in the account console under Workspaces). Used to assign the admin group to this workspace."
  type        = string
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
