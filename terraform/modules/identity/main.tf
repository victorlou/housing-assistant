# Service principal that owns ingestion pipelines and any scheduled jobs.
# The Databricks App gets its own auto-created service principal — see the
# app module for that.
resource "databricks_service_principal" "jobs" {
  display_name          = "${var.project_tag}-${var.environment}-jobs"
  workspace_access      = true
  databricks_sql_access = true
  force                 = true
}

# Account-level admin group. Created via the account-level provider so it is
# a real account-level principal, which Unity Catalog requires for grants.
# Permissions are managed in Terraform (at the env level); membership is
# managed in the account console so adding or removing a teammate doesn't
# need a `terraform apply`.
resource "databricks_group" "admins" {
  provider              = databricks.account
  display_name          = "${var.project_tag}-${var.environment}-admins"
  workspace_access      = true
  databricks_sql_access = true
  force                 = true
}

# Assign the account-level group to this workspace so members get workspace
# access. USER is enough for what we need; ADMIN would also make them
# workspace admins, which we don't want by default.
resource "databricks_mws_permission_assignment" "admins_to_workspace" {
  provider     = databricks.account
  workspace_id = var.workspace_id
  principal_id = databricks_group.admins.id
  permissions  = ["USER"]
}

# Eventual-consistency cushion. Even with the group at account level,
# Unity Catalog's principal cache takes a few seconds to see new
# principals. Without this, grants in the env can fail with
# "Could not find principal" on first apply.
resource "time_sleep" "wait_for_admins_group" {
  depends_on      = [databricks_mws_permission_assignment.admins_to_workspace]
  create_duration = "30s"
}
