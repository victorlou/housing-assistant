terraform {
  required_version = ">= 1.7"

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.52"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}

provider "aws" {
  region = var.aws_region
}
