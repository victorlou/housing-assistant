# Lakebase role, database, and schema migration.
#
# This is intentionally separate from the Lakebase resource module to break the
# cyclic dependency between the app module (which needs Lakebase branch/database
# names for its resource binding) and the Lakebase module (which needs the app's
# service principal to create the Postgres role). The intended ordering is:
#   1. Lakebase project is created (lakebase module).
#   2. Databricks App is created with a `resources.postgres` binding that grants
#      its auto-created service principal CAN_CONNECT_AND_CREATE on Lakebase.
#   3. This module creates the Postgres role and database, then runs schema.sql.
#
# The migration runs as the Databricks CLI identity executing Terraform. The CLI
# generates a short-lived Lakebase database credential for that identity, and the
# same identity is used as PGUSER. This avoids trying to use the app's internal
# service principal from local-exec, because Terraform does not have a client
# secret for that auto-created app service principal.
locals {
  databricks_cli_profile_arg = var.databricks_profile == "" ? "" : "--profile ${var.databricks_profile}"
}

resource "databricks_postgres_role" "app" {
  role_id = "app-sp"
  parent  = var.production_branch_name

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
  parent      = var.production_branch_name

  spec = {
    postgres_database = var.postgres_database_name
    role              = databricks_postgres_role.app.name
  }

  depends_on = [databricks_postgres_role.app]
}

resource "null_resource" "schema_migration" {
  triggers = {
    schema_hash              = filesha256("${path.module}/sql/schema.sql")
    production_branch_name   = var.production_branch_name
    production_endpoint_name = var.production_endpoint_name
    database_name            = var.postgres_database_name
    database_user            = var.database_user
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail

      echo "==> Fetching Lakebase endpoint host..."
      ENDPOINT_HOST=$(databricks ${local.databricks_cli_profile_arg} postgres list-endpoints \
        "${var.production_branch_name}" \
        --output json \
        | jq -r '.[] | select(.status.endpoint_type == "ENDPOINT_TYPE_READ_WRITE") | .status.hosts.host' \
        | head -1)

      if [ -z "$${ENDPOINT_HOST}" ]; then
        echo "ERROR: no read-write endpoint found. Is the production branch endpoint ACTIVE?"
        exit 1
      fi

      if [ -n "${var.database_user}" ]; then
        DATABASE_USER="${var.database_user}"
      else
        echo "==> Resolving Databricks CLI user..."
        DATABASE_USER=$(databricks ${local.databricks_cli_profile_arg} current-user me \
          --output json \
          | jq -r '.userName // .user_name')
      fi

      if [ -z "$${DATABASE_USER}" ] || [ "$${DATABASE_USER}" = "null" ]; then
        echo "ERROR: no Databricks database user returned"
        exit 1
      fi

      echo "==> Generating short-lived Lakebase database credential..."
      DATABASE_TOKEN=$(databricks ${local.databricks_cli_profile_arg} postgres generate-database-credential \
        "${var.production_endpoint_name}" \
        --output json \
        | jq -r '.token')

      [ -z "$${DATABASE_TOKEN}" ] || [ "$${DATABASE_TOKEN}" = "null" ] && { echo "ERROR: no Lakebase database token returned"; exit 1; }

      echo "==> Endpoint: $${ENDPOINT_HOST}"
      echo "==> Running migration as '$${DATABASE_USER}' against '${var.postgres_database_name}'..."

      PGUSER="$${DATABASE_USER}" PGPASSWORD="$${DATABASE_TOKEN}" psql \
        "postgresql://$${ENDPOINT_HOST}/${var.postgres_database_name}?sslmode=require" \
        --file="${path.module}/sql/schema.sql" \
        --set ON_ERROR_STOP=on \
        --echo-errors

      echo "==> Migration complete."
    EOT
  }
}
