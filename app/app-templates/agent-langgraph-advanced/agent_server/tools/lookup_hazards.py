import json
import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import build_in_params as _build_in_params
from agent_server.tools.utils import execute_statement as _execute
from agent_server.tools.utils import resolve_suburb_fuzzy as _resolve

logger = logging.getLogger(__name__)

_RISK_ORDER = {"high": 2, "medium": 1, "low": 0}


def _worst(levels: list[str]) -> str:
    return max(levels, key=lambda x: _RISK_ORDER.get(x, -1), default="unknown")


def _bool(v) -> bool:
    """Normalise a database boolean that may arrive as bool, string, or None."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).lower() == "true"


@tool
def lookup_hazards(suburb_name: str) -> dict:
    """
    Return worst-case natural hazard risk levels for a suburb across flood and coastal
    categories.

    Call this for every suburb that passes the budget/commute filter when the user
    has a hazard constraint (flood zone avoidance, coastal concerns).
    Also call in planner queries to identify "double burden" suburbs — areas that are
    both housing-stressed (from score_affordability) and high-risk (from this tool).
    Double-burden suburbs are the strongest candidates for council intervention.

    When a colloquial name matches multiple Stats NZ SA2 areas (e.g. "Takanini" covers
    several SA2s), worst-case risk is computed across ALL matched areas and H3 cells —
    giving the most conservative (safest) risk assessment for the neighbourhood.

    Trigger phrases: "flood zone", "flood risk", "coastal", "natural disaster",
    "safe area", "not near water", "post-Cyclone Gabrielle".

    Risk levels per category: "low", "medium", "high".
    Worst-case rule: any H3 cell flagged "high" → suburb is "high" for that category.

    Args:
        suburb_name: Suburb name (e.g. "Henderson", "Takanini", "Mangere")

    Returns:
        Dict with:
          - suburb: suburb name (or colloquial name when multiple SA2s were merged)
          - matched_areas: list of SA2 names included in the assessment
          - flood_risk: worst-case flood risk across all matched areas
          - coastal_risk: worst-case coastal inundation risk across all matched areas
          - overall_risk: single worst level across flood and coastal
          - hazard_sources: deduplicated hazard layer IDs that triggered a flag
          - cells_examined: total H3 cells assessed across all matched areas
          - error: present only if the suburb was not found or has no hazard data
    """
    suburb_rows = _resolve(suburb_name)
    if not suburb_rows or not suburb_rows[0][0]:
        return {
            "suburb": suburb_name,
            "error": f"Suburb '{suburb_name}' not found. Check suburb name spelling.",
        }

    suburb_ids = [row[0] for row in suburb_rows]
    matched_names = [row[1] for row in suburb_rows]
    display_name = matched_names[0] if len(suburb_ids) == 1 else suburb_name

    id_placeholders, id_params = _build_in_params(suburb_ids, "hid")

    hazard_rows = _execute(
        f"""
        SELECT h.in_flood_plain, h.in_flood_prone_area, h.in_flood_sensitive_area,
               h.in_coastal_inundation_1_aep, h.in_coastal_inundation_100yr,
               h.in_regional_flood_zone, h.hazard_sources
        FROM {_CATALOG}.{_SCHEMA}.h3_cell hc
        JOIN {_CATALOG}.{_SCHEMA}.hazard h ON hc.h3_cell = h.h3_cell
        WHERE hc.suburb_id IN ({id_placeholders})
        """,
        id_params,
    )
    if not hazard_rows:
        return {
            "suburb": display_name,
            "matched_areas": matched_names,
            "error": f"No hazard data found for '{display_name}'. The suburb may be outside hazard data coverage.",
        }

    flood_risk = (
        "high"
        if any(_bool(r[0]) for r in hazard_rows)
        else "medium"
        if any(_bool(r[1]) or _bool(r[2]) or _bool(r[5]) for r in hazard_rows)
        else "low"
    )
    coastal_risk = (
        "high"
        if any(_bool(r[3]) for r in hazard_rows)
        else "medium"
        if any(_bool(r[4]) for r in hazard_rows)
        else "low"
    )
    overall_risk = _worst([flood_risk, coastal_risk])

    all_sources: list[str] = []
    for row in hazard_rows:
        raw = row[6]
        if raw is None:
            continue
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                all_sources.extend(parsed)
            except (json.JSONDecodeError, TypeError):
                all_sources.append(raw)
        else:
            all_sources.extend(raw)
    hazard_sources = list(dict.fromkeys(s for s in all_sources if s))

    return {
        "suburb": display_name,
        "matched_areas": matched_names,
        "flood_risk": flood_risk,
        "coastal_risk": coastal_risk,
        "overall_risk": overall_risk,
        "hazard_sources": hazard_sources,
        "cells_examined": len(hazard_rows),
    }
