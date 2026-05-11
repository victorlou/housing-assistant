variable "project_tag" {
  description = "Tag applied to created principals."
  type        = string
}

variable "environment" {
  description = "Environment name suffix (e.g. dev)."
  type        = string
  default     = "dev"
}
