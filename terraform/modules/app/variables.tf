variable "project_tag" {
  description = "Tag for cost tracking."
  type        = string
}

variable "app_name" {
  description = "Databricks App name."
  type        = string
}

variable "warehouse_id" {
  description = "ID of the SQL warehouse the app should be allowed to use."
  type        = string
}

variable "lakebase_branch_name" {
  description = "Lakebase Autoscaling branch resource name to bind to the Databricks App, e.g. projects/<project>/branches/production."
  type        = string
}

variable "lakebase_database_resource_name" {
  description = "Full Lakebase Autoscaling database resource name to bind to the Databricks App, e.g. projects/<project>/branches/production/databases/<database_id>."
  type        = string
}
