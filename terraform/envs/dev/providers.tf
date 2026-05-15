# Two Databricks providers:
#
# 1. The default, workspace-scoped provider. Used for almost everything:
#    catalog, schemas, volumes, jobs, the app, Lakebase, secrets.
#
# 2. The aliased account-scoped provider. Used only for account-level
#    resources we can't create at workspace level: groups (which UC requires
#    to be account-level), and the permission assignment that lets a
#    workspace see the group.
#
# Each provider authenticates via its own CLI profile. See docs/runbook.md
# for one-time setup.

provider "databricks" {
  host    = var.databricks_host
  profile = var.databricks_profile
}

provider "databricks" {
  alias      = "account"
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
  profile    = var.databricks_account_profile
}
