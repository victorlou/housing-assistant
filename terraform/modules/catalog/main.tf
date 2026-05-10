locals {
  layer_schemas = toset(var.layer_schema_names)
}

resource "databricks_schema" "layer" {
  for_each     = local.layer_schemas
  catalog_name = data.databricks_catalog.target.name
  name         = each.key
  comment      = "${title(each.key)} layer for Housing Assistant."
}

resource "databricks_volume" "tenancy_bonds" {
  name         = var.tenancy_bonds_volume_name
  catalog_name = data.databricks_catalog.target.name
  schema_name  = databricks_schema.layer["bronze"].name
  volume_type  = "MANAGED"
  comment      = var.tenancy_bonds_volume_comment
}
