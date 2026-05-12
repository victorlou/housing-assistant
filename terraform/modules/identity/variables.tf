variable "project_tag" {
  description = "Tag applied to created principals."
  type        = string
}

variable "environment" {
  description = "Environment name suffix (e.g. dev)."
  type        = string
  default     = "dev"
}

variable "workspace_id" {
  description = "Numeric Databricks workspace ID. Used to assign the account-level admin group to this workspace."
  type        = string
}
