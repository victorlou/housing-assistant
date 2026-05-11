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
