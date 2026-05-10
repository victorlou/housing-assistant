locals {
  uc_resource_tags = {
    project = "housing-assistant"
  }

  schema_tag_assignments = flatten([
    for schema_name in var.layer_schema_names : [
      for key, val in local.uc_resource_tags : {
        assignment_id = "${schema_name}_${key}"
        schema_name     = schema_name
        tag_key         = key
        tag_value       = val
      }
    ]
  ])

  volume_tag_assignments = flatten([
    for vol_key in ["tenancy_bonds", "linz_nz_addresses"] : [
      for tag_key, tag_val in local.uc_resource_tags : {
        assignment_id = "${vol_key}_${tag_key}"
        volume_key     = vol_key
        tag_key         = tag_key
        tag_value       = tag_val
      }
    ]
  ])
}

resource "databricks_entity_tag_assignment" "layer_schema" {
  for_each = { for p in local.schema_tag_assignments : p.assignment_id => p }

  entity_type = "schemas"
  entity_name = "${data.databricks_catalog.target.name}.${each.value.schema_name}"
  tag_key     = each.value.tag_key
  tag_value   = each.value.tag_value
}

resource "databricks_entity_tag_assignment" "tenancy_bonds_volume" {
  for_each = {
    for p in local.volume_tag_assignments : p.assignment_id => p
    if p.volume_key == "tenancy_bonds"
  }

  entity_type = "volumes"
  entity_name = "${data.databricks_catalog.target.name}.${databricks_schema.layer["bronze"].name}.${databricks_volume.tenancy_bonds.name}"
  tag_key     = each.value.tag_key
  tag_value   = each.value.tag_value
}

resource "databricks_entity_tag_assignment" "linz_nz_addresses_volume" {
  for_each = {
    for p in local.volume_tag_assignments : p.assignment_id => p
    if p.volume_key == "linz_nz_addresses"
  }

  entity_type = "volumes"
  entity_name = "${data.databricks_catalog.target.name}.${databricks_schema.layer["bronze"].name}.${databricks_volume.linz_nz_addresses.name}"
  tag_key     = each.value.tag_key
  tag_value   = each.value.tag_value
}
