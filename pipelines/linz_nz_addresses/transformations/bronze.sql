-- Bronze: LINZ NZ Addresses from landed JSONL (one GeoJSON Feature per line).
--
-- Landing stays JSONL on the UC volume (cheap uploads from ingestion.linz_wfs). DLT still
-- materialises every STREAMING LIVE TABLE below as managed Delta under this pipeline catalog.
--
-- Default catalog is `workspace` (Terraform default). If uc_catalog_name is different, replace
-- the path segment below to match `terraform output linz_nz_addresses_files_path`.

CREATE OR REFRESH STREAMING LIVE TABLE linz_nz_addresses_raw
COMMENT "Raw LINZ NZ address features landed as JSONL (WFS via config-driven fetch)."
AS SELECT *
FROM read_files(
  '/Volumes/workspace/bronze/linz_nz_addresses/*.jsonl',
  format => 'json'
);

-- Explicit downstream Delta table: flattened GeoJSON for stable typed reads (still bronze / no business rules).
CREATE STREAMING LIVE TABLE linz_nz_addresses_features
COMMENT "LINZ NZ addresses as typed bronze Delta (flattened GeoJSON Feature properties)."
TABLE PROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
)
AS SELECT
  id AS feature_id,
  geometry_name AS source_geometry_name,
  geometry.type AS geometry_type,
  CAST(element_at(geometry.coordinates, 1) AS DOUBLE) AS longitude,
  CAST(element_at(geometry.coordinates, 2) AS DOUBLE) AS latitude,
  properties.address_id AS address_id,
  properties.source_dataset AS source_dataset,
  properties.change_id AS change_id,
  properties.full_address_number AS full_address_number,
  properties.full_road_name AS full_road_name,
  properties.full_address AS full_address,
  properties.territorial_authority AS territorial_authority,
  properties.unit_type AS unit_type,
  properties.unit_value AS unit_value,
  properties.level_type AS level_type,
  properties.level_value AS level_value,
  properties.address_number_prefix AS address_number_prefix,
  properties.address_number AS address_number,
  properties.address_number_suffix AS address_number_suffix,
  properties.address_number_high AS address_number_high,
  properties.road_name_prefix AS road_name_prefix,
  properties.road_name AS road_name,
  properties.road_type_name AS road_type_name,
  properties.road_suffix AS road_suffix,
  properties.water_name AS water_name,
  properties.water_body_name AS water_body_name,
  properties.suburb_locality AS suburb_locality,
  properties.town_city AS town_city,
  properties.address_class AS address_class,
  properties.address_lifecycle AS address_lifecycle,
  properties.gd2000_xcoord AS gd2000_xcoord,
  properties.gd2000_ycoord AS gd2000_ycoord,
  properties.road_name_ascii AS road_name_ascii,
  properties.water_name_ascii AS water_name_ascii,
  properties.water_body_name_ascii AS water_body_name_ascii,
  properties.suburb_locality_ascii AS suburb_locality_ascii,
  properties.town_city_ascii AS town_city_ascii,
  properties.full_road_name_ascii AS full_road_name_ascii,
  properties.full_address_ascii AS full_address_ascii,
  geometry AS geojson_geometry_struct
FROM STREAM(linz_nz_addresses_raw);
