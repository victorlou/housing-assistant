terraform {
  required_version = ">= 1.13.0"

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.85"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}
