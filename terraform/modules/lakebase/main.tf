# Managed Postgres for user state. The schema (users, user_constraints,
# saved_searches, alerts, conversation_turns) is bootstrapped from a notebook
# rather than from Terraform — keeps DDL out of the state file.
#
# NOTE on naming: a Lakebase database instance maps to a Postgres server.
# Inside it, the app-specific Postgres database (typical name: `housing`) is
# created out-of-band the first time we connect. Mirror tables in the
# `housing.app` UC schema reflect a subset of these.
resource "databricks_database_instance" "main" {
  name     = var.instance_name
  capacity = var.capacity

  # 1 node = no readable replicas. Fine for development.
  node_count = var.node_count
}
