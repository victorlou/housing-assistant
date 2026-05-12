variable "production_branch_name" {
  description = "Postgres API name of the Lakebase production branch, e.g. projects/<project>/branches/production."
  type        = string
}

variable "production_endpoint_name" {
  description = "Postgres API name of the Lakebase read-write production endpoint, e.g. projects/<project>/branches/production/endpoints/primary."
  type        = string
}

variable "postgres_database_name" {
  description = "Postgres database name to run migrations against."
  type        = string
}

variable "app_service_principal_client_id" {
  description = "Application/client ID UUID of the Databricks App's auto-created service principal used as the Postgres user for schema migrations."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.app_service_principal_client_id))
    error_message = "app_service_principal_client_id must be a UUID application/client ID."
  }
}

variable "app_service_principal_client_secret" {
  description = "Client secret for the Databricks App's auto-created service principal. Used only to authenticate Databricks CLI calls for Lakebase migrations."
  type        = string
  sensitive   = true
}

variable "databricks_host" {
  description = "Workspace URL, e.g. https://dbc-xxxxx.cloud.databricks.com."
  type        = string

  validation {
    condition     = can(regex("^https://", var.databricks_host))
    error_message = "databricks_host must be set to the Databricks workspace URL, e.g. https://dbc-xxxxx.cloud.databricks.com."
  }
}
