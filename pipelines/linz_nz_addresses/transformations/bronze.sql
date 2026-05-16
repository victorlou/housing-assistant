-- Bronze: LINZ NZ Addresses from landed JSONL (one GeoJSON Feature per line).
--
-- JSONL is written by the `linz_nz_addresses_ingest` Databricks job (see `notebooks/fetch.py`).
-- DLT materialises every streaming table below as managed Delta under this pipeline catalog.
--
-- Landings: `addresses_files` volume (Terraform `bronze_volumes`) under
-- `linz_nz_addresses/YYYY-MM-DD/linz_nz_addresses.jsonl` from the ingest job.
-- If catalog_name is not `housing`, replace the catalog segment below (must match the ingest job).

CREATE STREAMING TABLE linz_nz_addresses_raw
COMMENT "Raw LINZ NZ address features landed as JSONL (WFS via scheduled fetch job)."
AS SELECT *
FROM cloud_files(
  '/Volumes/housing/bronze/addresses_files/linz_nz_addresses',
  'json',
  map('cloudFiles.inferColumnTypes', 'true')
);

-- Flattened bronze streaming table from raw (requires cloud_files upstream for STREAM()).
-- Uses TBLPROPERTIES (not TABLE PROPERTIES) per streaming-table DDL; alias + backticks avoid `properties` token clashes.
CREATE STREAMING TABLE linz_nz_addresses_features
COMMENT 'LINZ NZ addresses as typed bronze Delta (flattened GeoJSON Feature properties).'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
)
AS SELECT
  rf.id AS feature_id,
  rf.geometry_name AS source_geometry_name,
  rf.geometry.type AS geometry_type,
  CAST(element_at(rf.geometry.coordinates, 1) AS DOUBLE) AS longitude,
  CAST(element_at(rf.geometry.coordinates, 2) AS DOUBLE) AS latitude,
  rf.`properties`.address_id AS address_id,
  rf.`properties`.source_dataset AS source_dataset,
  rf.`properties`.change_id AS change_id,
  rf.`properties`.full_address_number AS full_address_number,
  rf.`properties`.full_road_name AS full_road_name,
  rf.`properties`.full_address AS full_address,
  rf.`properties`.territorial_authority AS territorial_authority,
  rf.`properties`.unit_type AS unit_type,
  rf.`properties`.unit_value AS unit_value,
  rf.`properties`.level_type AS level_type,
  rf.`properties`.level_value AS level_value,
  rf.`properties`.address_number_prefix AS address_number_prefix,
  rf.`properties`.address_number AS address_number,
  rf.`properties`.address_number_suffix AS address_number_suffix,
  rf.`properties`.address_number_high AS address_number_high,
  rf.`properties`.road_name_prefix AS road_name_prefix,
  rf.`properties`.road_name AS road_name,
  rf.`properties`.road_type_name AS road_type_name,
  rf.`properties`.road_suffix AS road_suffix,
  rf.`properties`.water_name AS water_name,
  rf.`properties`.water_body_name AS water_body_name,
  rf.`properties`.suburb_locality AS suburb_locality,
  rf.`properties`.town_city AS town_city,
  rf.`properties`.address_class AS address_class,
  rf.`properties`.address_lifecycle AS address_lifecycle,
  rf.`properties`.gd2000_xcoord AS gd2000_xcoord,
  rf.`properties`.gd2000_ycoord AS gd2000_ycoord,
  rf.`properties`.road_name_ascii AS road_name_ascii,
  rf.`properties`.water_name_ascii AS water_name_ascii,
  rf.`properties`.water_body_name_ascii AS water_body_name_ascii,
  rf.`properties`.suburb_locality_ascii AS suburb_locality_ascii,
  rf.`properties`.town_city_ascii AS town_city_ascii,
  rf.`properties`.full_road_name_ascii AS full_road_name_ascii,
  rf.`properties`.full_address_ascii AS full_address_ascii,
  rf.geometry AS geojson_geometry_struct
FROM STREAM(linz_nz_addresses_raw) AS rf;
