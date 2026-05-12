variable "project_id" {
  description = "DNS-compliant Lakebase project ID. Lowercase letters, digits, and hyphens; 1-63 chars; cannot start or end with a hyphen. Becomes part of the Postgres API resource path and is immutable after creation."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", var.project_id))
    error_message = "project_id must be lowercase letters, digits, or hyphens, 1-63 chars, and cannot start or end with a hyphen."
  }
}

variable "display_name" {
  description = "Human-readable name shown in the Lakebase Autoscaling UI."
  type        = string
}

variable "pg_version" {
  description = "PostgreSQL major version. 17 is the Lakebase Autoscaling default."
  type        = number
  default     = 17
}

variable "database_id" {
  description = "Lakebase database resource ID (4-63 chars, lowercase letters, numbers, hyphens). This becomes the final component of the API resource path."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,61}[a-z0-9]$", var.database_id))
    error_message = "database_id must be 4-63 characters: lowercase letters, numbers, and hyphens; cannot start or end with a hyphen."
  }
}

variable "postgres_database_name" {
  description = "Actual Postgres database name. Must be an unquoted Postgres identifier, so use underscores instead of hyphens. If omitted, database_id is converted by replacing hyphens with underscores."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_database_name == null || can(regex("^[a-z_][a-z0-9_]{0,62}$", var.postgres_database_name))
    error_message = "postgres_database_name must be 1-63 characters and match an unquoted lowercase Postgres identifier: start with a letter or underscore, then letters, digits, or underscores."
  }
}

