# Managed Postgres for user state, on the Lakebase Autoscaling platform.
#
# Creating a project auto-provisions:
#   - a `production` branch
#   - a `primary` read-write endpoint on that branch
#
# This module also creates the app service-principal-backed Postgres role and
# application database. Schema migrations are managed by Drizzle ORM
# (packages/db/src/schema-housing.ts), not Terraform.
#
# Scale-to-zero is OFF by default on the auto-created endpoint. Autoscaling
# range and scale-to-zero are configured via the Postgres API or the Lakebase
# Autoscaling UI, not via the Database instance API. We do that as a one-time
# post-apply step — see docs/runbook.md.
#
# Resource is in Beta. Spec/status field names may change; pin a working
# provider version in versions.tf and re-verify on upgrades.
locals {
  production_branch_name   = "${databricks_postgres_project.main.name}/branches/production"
  production_endpoint_name = "${local.production_branch_name}/endpoints/primary"
  postgres_database_name   = coalesce(var.postgres_database_name, replace(var.database_id, "-", "_"))
  database_resource_name   = "${local.production_branch_name}/databases/${var.database_id}"
}

resource "databricks_postgres_project" "main" {
  project_id = var.project_id

  spec = {
    pg_version   = var.pg_version
    display_name = var.display_name
  }
}

resource "databricks_postgres_role" "app" {
  role_id = "app-sp"
  parent  = local.production_branch_name

  spec = {
    identity_type    = "SERVICE_PRINCIPAL"
    postgres_role    = var.app_service_principal_client_id
    auth_method      = "LAKEBASE_OAUTH_V1"
    membership_roles = ["DATABRICKS_SUPERUSER"]

    attributes = {
      createdb   = false
      createrole = false
      bypassrls  = false
    }
  }
}

resource "databricks_postgres_database" "main" {
  database_id = var.database_id
  parent      = local.production_branch_name

  spec = {
    postgres_database = local.postgres_database_name
    role              = databricks_postgres_role.app.name
  }

  depends_on = [databricks_postgres_role.app]
}
