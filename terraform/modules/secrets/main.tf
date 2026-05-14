# Single Databricks-backed secret scope for all project-level secrets
# (transit API keys, third-party tokens, anything pipelines or the agent need).
resource "databricks_secret_scope" "main" {
  name                     = var.scope_name
  initial_manage_principal = "users"
}
