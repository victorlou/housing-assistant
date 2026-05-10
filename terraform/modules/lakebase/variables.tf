variable "project_tag" {
  description = "Tag for cost tracking."
  type        = string
}

variable "instance_name" {
  description = "Lakebase database instance name."
  type        = string
}

variable "capacity" {
  description = "Lakebase compute capacity tier (e.g. CU_1, CU_2)."
  type        = string
  default     = "CU_1"
}

variable "node_count" {
  description = "Number of nodes. 1 = primary only (cheapest, fine for dev). 2 = primary + readable replica."
  type        = number
  default     = 1
}
