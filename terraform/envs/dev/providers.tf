# Auth: use environment variables only (nothing profile-specific in git).
# See docs/runbook.md — typically DATABRICKS_CONFIG_PROFILE or DATABRICKS_HOST + DATABRICKS_TOKEN.
provider "databricks" {}
