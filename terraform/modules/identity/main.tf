# Service principal that owns ingestion pipelines and any scheduled jobs.
# The Databricks App gets its own auto-created service principal — see the
# app module for its Lakebase resource binding.
resource "databricks_service_principal" "jobs" {
  display_name          = "${var.project_tag}-${var.environment}-jobs"
  workspace_access      = true
  databricks_sql_access = true
  force                 = true
}
