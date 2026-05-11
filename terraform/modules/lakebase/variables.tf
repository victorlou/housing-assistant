variable "env" {
  type = string
}

variable "catalog_name" {
  description = "Unity Catalog catalog that owns the app schema (e.g. 'housing')"
  type        = string
}

variable "capacity" {
  description = "Lakebase capacity units"
  type        = number
  default     = 1
}

variable "admin_user" {
  description = "Postgres admin username"
  type        = string
}

variable "admin_password" {
  description = "Postgres admin password"
  type        = string
  sensitive   = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
