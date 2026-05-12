# Lakebase schema migration.
#
# Lakebase infrastructure (project, role, and database) is owned by the
# lakebase module. This module only applies schema.sql after the app has been
# created and its Databricks App service principal is available.
#
# The migration connects as the Databricks App service principal so objects
# created by schema.sql are owned by the same identity that the app uses at
# runtime.
resource "null_resource" "schema_migration" {
  triggers = {
    schema_hash                     = filesha256("${path.module}/sql/schema.sql")
    production_branch_name          = var.production_branch_name
    production_endpoint_name        = var.production_endpoint_name
    database_name                   = var.postgres_database_name
    app_service_principal_client_id = var.app_service_principal_client_id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]

    environment = {
      DATABRICKS_HOST          = var.databricks_host
      DATABRICKS_CLIENT_ID     = var.app_service_principal_client_id
      DATABRICKS_CLIENT_SECRET = var.app_service_principal_client_secret
      DATABRICKS_AUTH_TYPE     = "oauth-m2m"
    }

    command = <<-EOT
      set -euo pipefail

      DATABASE_USER="${var.app_service_principal_client_id}"

      echo "==> Verifying Databricks service principal authentication..."
      databricks current-user me --output json | jq -r '.userName // .applicationId // .id'

      echo "==> Fetching Lakebase endpoint host..."
      ENDPOINT_HOST=$(databricks postgres list-endpoints \
        "${var.production_branch_name}" \
        --output json \
        | jq -r '.[] | select(.status.endpoint_type == "ENDPOINT_TYPE_READ_WRITE") | .status.hosts.host' \
        | head -1)

      if [ -z "$${ENDPOINT_HOST}" ]; then
        echo "ERROR: no read-write endpoint found. Is the production branch endpoint ACTIVE?"
        exit 1
      fi

      echo "==> Generating short-lived Lakebase database credential as app service principal..."
      DATABASE_TOKEN=$(databricks postgres generate-database-credential \
        "${var.production_endpoint_name}" \
        --output json \
        | jq -r '.token')

      [ -z "$${DATABASE_TOKEN}" ] || [ "$${DATABASE_TOKEN}" = "null" ] && { echo "ERROR: no Lakebase database token returned"; exit 1; }

      echo "==> Endpoint: $${ENDPOINT_HOST}"
      echo "==> Running migration as app service principal '$${DATABASE_USER}' against '${var.postgres_database_name}'..."

      PGPASSWORD="$${DATABASE_TOKEN}" psql \
        "postgresql://$${DATABASE_USER}@$${ENDPOINT_HOST}/${var.postgres_database_name}?sslmode=require" \
        --file="${path.module}/sql/schema.sql" \
        --set ON_ERROR_STOP=on \
        --echo-errors

      echo "==> Migration complete."
    EOT
  }
}
