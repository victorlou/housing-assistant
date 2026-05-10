-- Bronze: raw LINZ address features (one GeoJSON Feature per line) from the managed volume.
-- Default catalog is `workspace` (Terraform default). If uc_catalog_name is different, replace
-- the path segment below to match `terraform output linz_nz_addresses_files_path`.

CREATE OR REFRESH STREAMING LIVE TABLE linz_nz_addresses_raw
COMMENT "Raw LINZ NZ address features landed as JSONL (WFS via config-driven fetch)."
AS SELECT *
FROM read_files(
  '/Volumes/workspace/bronze/linz_nz_addresses/*.jsonl',
  format => 'json'
);
