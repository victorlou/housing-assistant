terraform {
  required_version = ">= 1.13.0"

  required_providers {
    databricks = {
      source                = "databricks/databricks"
      version               = "~> 1.85"
      configuration_aliases = [databricks.account]
    }
    time = {
      source = "hashicorp/time"
    }
  }
}
