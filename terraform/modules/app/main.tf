# Empty Databricks App. The frontend stack ships in a follow-up PR; this just
# stands up the runtime and binds the app's auto-created service principal to
# the warehouse and Lakebase.
#
# `resources` registers external resource bindings the app needs at runtime.
# Newer provider versions express this as a typed attribute (list of objects),
# not nested blocks. We register the SQL warehouse and Lakebase Autoscaling
# branch/database so their credentials are automatically wired into the app
# environment and the app identity receives the required permissions.
resource "databricks_app" "main" {
  name        = var.app_name
  description = "Housing Assistant consumer surface"

  resources = [
    {
      name        = "warehouse"
      description = "Serverless SQL warehouse the app calls Genie through."
      sql_warehouse = {
        id         = var.warehouse_id
        permission = "CAN_USE"
      }
    },
    {
      name        = "lakebase"
      description = "Lakebase Autoscaling Postgres database for application state."
      postgres = {
        branch     = var.lakebase_branch_name
        database   = var.lakebase_database_resource_name
        permission = "CAN_CONNECT_AND_CREATE"
      }
    }
  ]
}
