variable "production_branch_name" {
  description = "Postgres API name of the Lakebase production branch, e.g. projects/<project>/branches/production."
  type        = string
}

variable "postgres_database_name" {
  description = "Postgres database name to run migrations against."
  type        = string
}

variable "app_service_principal_client_id" {
  description = "Application/client ID UUID of the Databricks App's auto-created service principal. Mapped to a Postgres role that owns the app database."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.app_service_principal_client_id))
    error_message = "app_service_principal_client_id must be a UUID application/client ID."
  }
}

variable "database_id" {
  description = "Lakebase database resource ID (4-63 chars, lowercase letters, numbers, hyphens)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,61}[a-z0-9]$", var.database_id))
    error_message = "database_id must be 4-63 characters: lowercase letters, numbers, and hyphens; cannot start or end with a hyphen."
  }
}
