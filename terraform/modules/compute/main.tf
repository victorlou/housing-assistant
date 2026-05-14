# Single serverless SQL warehouse used by Genie, the dashboard, the agent
# (via the Genie tool), and ad-hoc developer queries.
resource "databricks_sql_endpoint" "main" {
  name                      = var.warehouse_name
  cluster_size              = var.cluster_size
  warehouse_type            = "PRO"
  enable_serverless_compute = true
  auto_stop_mins            = var.auto_stop_minutes
  max_num_clusters          = var.max_clusters

  tags {
    custom_tags {
      key   = "project"
      value = var.project_tag
    }
  }
}
