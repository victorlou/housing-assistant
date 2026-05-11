# Empty Databricks App. The frontend stack ships in a follow-up PR; this just
# stands up the runtime so the app's auto-created service principal exists and
# can be granted access to the warehouse, catalog, and Lakebase.
#
# `resources` registers external resource bindings the app needs at runtime.
# Newer provider versions express this as a typed attribute (list of objects),
# not nested blocks. We register the SQL warehouse so its credentials are
# automatically wired into the app environment.
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
    }
  ]
}
