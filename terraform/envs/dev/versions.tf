terraform {
  required_version = ">= 1.13.0"

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.85"
    }

    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}
