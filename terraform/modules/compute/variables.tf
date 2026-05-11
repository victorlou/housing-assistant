variable "project_tag" {
  description = "Tag applied to the warehouse for cost tracking."
  type        = string
}

variable "warehouse_name" {
  description = "Display name of the SQL warehouse."
  type        = string
}

variable "cluster_size" {
  description = "Warehouse t-shirt size. Smallest is 2X-Small."
  type        = string
  default     = "2X-Small"
}

variable "auto_stop_minutes" {
  description = "Idle minutes before the warehouse auto-stops. Aggressive default for cost control."
  type        = number
  default     = 5
}

variable "max_clusters" {
  description = "Maximum concurrent clusters for autoscaling."
  type        = number
  default     = 1
}
