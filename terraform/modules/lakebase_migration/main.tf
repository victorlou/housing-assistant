# Lakebase role and database setup.
#
# This is intentionally separate from the Lakebase resource module to break the
# cyclic dependency between the app module (which needs Lakebase branch/database
# names for its resource binding) and the Lakebase module (which needs the app's
# service principal to create the Postgres role). The intended ordering is:
#   1. Lakebase project is created (lakebase module).
#   2. Databricks App is created with a `resources.postgres` binding that grants
#      its auto-created service principal CAN_CONNECT_AND_CREATE on Lakebase.
#   3. This module creates the Postgres role and database for the app SP.
#
# Schema migrations are managed by Drizzle ORM (packages/db/src/schema-housing.ts).
# Run `npm run db:migrate` from e2e-chatbot-app-next to apply them.

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

