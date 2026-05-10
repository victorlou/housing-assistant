# Managed Postgres for user state, on the Lakebase Autoscaling platform.
#
# Creating a project auto-provisions:
#   - a `production` branch
#   - a `primary` read-write endpoint on that branch
#
# Scale-to-zero is OFF by default on the auto-created endpoint. Autoscaling
# range and scale-to-zero are configured via the Postgres API or the Lakebase
# Autoscaling UI, not via the Database instance API. We do that as a one-time
# post-apply step — see docs/runbook.md.
#
# Resource is in Beta. Spec/status field names may change; pin a working
# provider version in versions.tf and re-verify on upgrades.
resource "databricks_postgres_project" "main" {
  project_id = var.project_id

  spec = {
    pg_version   = var.pg_version
    display_name = var.display_name
  }
}
