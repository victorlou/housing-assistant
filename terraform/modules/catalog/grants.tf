# databricks_grants is authoritative per securable. We intentionally do not grant at
# catalog scope so shared catalogs (e.g. workspace) are not ACL-wiped.

resource "databricks_grants" "bronze" {
  count  = length(var.data_principal_names) > 0 ? 1 : 0
  schema = databricks_schema.layer["bronze"].id

  dynamic "grant" {
    for_each = var.data_principal_names
    content {
      principal  = grant.value
      privileges = ["USE_SCHEMA", "CREATE_TABLE", "CREATE_VOLUME"]
    }
  }
}

resource "databricks_grants" "tenancy_bonds_volume" {
  count  = length(var.data_principal_names) > 0 ? 1 : 0
  volume = databricks_volume.tenancy_bonds.id

  dynamic "grant" {
    for_each = var.data_principal_names
    content {
      principal  = grant.value
      privileges = ["READ_VOLUME", "WRITE_VOLUME"]
    }
  }
}

resource "databricks_grants" "linz_nz_addresses_volume" {
  count  = length(var.data_principal_names) > 0 ? 1 : 0
  volume = databricks_volume.linz_nz_addresses.id

  dynamic "grant" {
    for_each = var.data_principal_names
    content {
      principal  = grant.value
      privileges = ["READ_VOLUME", "WRITE_VOLUME"]
    }
  }
}
