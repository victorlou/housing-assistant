"""Layer metadata and hazard categories for flood silver/gold."""

from __future__ import annotations

from typing import Any

from flood_fetch_arcgis import load_layers_config

HAZARD_CATEGORY_BY_SOURCE: dict[str, str] = {
    "auckland_flood_plains": "flood_plain",
    "auckland_flood_prone_areas": "flood_prone",
    "auckland_flood_sensitive_areas": "flood_sensitive",
    "auckland_coastal_inundation_1_aep": "coastal_inundation_1_aep",
    "auckland_coastal_inundation_100yr": "coastal_inundation_100yr",
    "greater_wellington_100yr_outline": "regional_flood_zone",
    "wellington_city_100yr": "regional_flood_zone",
    "hamilton_100yr": "flood_plain",  # NB: currently quarantined in gold.py (UNTRUSTED_SOURCES).
    "queenstown_lakes_orc_hazard": "regional_flood_zone",
    "queenstown_lakes_wanaka_100yr": "flood_plain",
    "canterbury_selwyn_flood_zones": "regional_flood_zone",
    "otago_waitaki_floodplain": "regional_flood_zone",
}

FLOOD_PLAIN_SOURCES = {
    "auckland_flood_plains",
    "hamilton_100yr",
    "queenstown_lakes_wanaka_100yr",
}

FLOOD_PRONE_SOURCES = {"auckland_flood_prone_areas"}

FLOOD_SENSITIVE_SOURCES = {"auckland_flood_sensitive_areas"}

COASTAL_1_AEP_SOURCES = {"auckland_coastal_inundation_1_aep"}

COASTAL_100YR_SOURCES = {"auckland_coastal_inundation_100yr"}

REGIONAL_FLOOD_SOURCES = {
    "greater_wellington_100yr_outline",
    "wellington_city_100yr",
    "queenstown_lakes_orc_hazard",
    "canterbury_selwyn_flood_zones",
    "otago_waitaki_floodplain",
}


def layer_metadata_rows() -> list[dict[str, Any]]:
    """Rows for joining registry metadata onto bronze features."""
    rows = []
    for layer_id, spec in load_layers_config().items():
        rows.append(
            {
                "hazard_source": layer_id,
                "file_stem": spec["file_stem"],
                "publisher": spec.get("publisher"),
                "region_name": spec.get("region_name"),
                "return_period": spec.get("return_period"),
                "aep": spec.get("aep"),
                "hazard_category": HAZARD_CATEGORY_BY_SOURCE.get(
                    layer_id, "regional_flood_zone"
                ),
            }
        )
    return rows
