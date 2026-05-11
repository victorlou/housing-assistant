# The Databricks provider authenticates via, in order of precedence:
#   1. DATABRICKS_HOST + DATABRICKS_TOKEN environment variables
#   2. The Databricks CLI profile selected by DATABRICKS_CONFIG_PROFILE
#   3. The default profile in ~/.databrickscfg
#
# For local development, run `databricks configure --token` once, then
# `terraform plan` will pick the credentials up automatically.

provider "databricks" {
  host    = var.databricks_host
  profile = var.databricks_profile
}
