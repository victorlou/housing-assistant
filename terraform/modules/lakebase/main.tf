# ---------------------------------------------------------------------------
# Lakebase (managed Postgres) instance
# ---------------------------------------------------------------------------

resource "databricks_database_instance" "this" {
  name     = "${var.env}-housing-lakebase"
  capacity = var.capacity
}

# ---------------------------------------------------------------------------
# OLTP schema — applied via psql once the instance is ready.
# Re-runs whenever schema.sql changes (tracked by its hash).
# Requires: psql in PATH, PGPASSWORD env var or .pgpass entry.
# ---------------------------------------------------------------------------

resource "null_resource" "schema" {
  triggers = {
    schema_hash  = filesha256("${path.module}/sql/schema.sql")
    instance_uid = databricks_database_instance.this.uid
  } # mentioned schema_hash - to make sure to re-run when schema.sql changes; instance_uid - to run after instance is ready

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      PGPASSWORD = var.admin_password
    }
    command = <<-EOT
      psql \
        "host=${databricks_database_instance.this.pgconn[0].host} \
         port=${databricks_database_instance.this.pgconn[0].port} \
         dbname=${databricks_database_instance.this.pgconn[0].dbname} \
         user=${var.admin_user} \
         sslmode=require" \
        -f "${path.module}/sql/schema.sql"
    EOT
  }

  depends_on = [databricks_database_instance.this]
}

# ---------------------------------------------------------------------------
# Unity Catalog federation — makes housing.app a foreign schema backed by
# the Lakebase public schema. Genie and dashboards can JOIN across it.
# The connection uses the admin credential; tighten to a read-only role
# before granting broader UC access.
# ---------------------------------------------------------------------------

resource "databricks_connection" "lakebase" {
  name            = "${var.env}-housing-lakebase"
  connection_type = "POSTGRESQL"
  comment         = "Lakebase OLTP — housing_app/public (user state tables)"

  options = {
    host     = databricks_database_instance.this.pgconn[0].host
    port     = tostring(databricks_database_instance.this.pgconn[0].port)
    database = databricks_database_instance.this.pgconn[0].dbname
    user     = var.admin_user
    password = var.admin_password
  }

  depends_on = [null_resource.schema]
}

# Federated schema: housing.app → Lakebase public schema
resource "databricks_schema" "app" {
  catalog_name    = var.catalog_name
  name            = "app"
  comment         = "Federated view of Lakebase user-state tables"
  connection_name = databricks_connection.lakebase.name

  options = {
    database = databricks_database_instance.this.pgconn[0].dbname
    schema   = "public"
  }
}
