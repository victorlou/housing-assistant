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
