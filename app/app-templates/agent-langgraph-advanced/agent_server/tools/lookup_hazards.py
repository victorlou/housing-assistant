import json
import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
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

    Trigger phrases: "flood zone", "flood risk", "coastal", "natural disaster",
    "safe area", "not near water", "post-Cyclone Gabrielle".

    Risk levels per category: "low", "medium", "high".
    Worst-case rule: any H3 cell flagged "high" → suburb is "high" for that category.

    Args:
        suburb_name: Suburb name (e.g. "Henderson", "Takanini", "Mangere")

    Returns:
        Dict with:
          - suburb: suburb name
          - flood_risk: worst-case flood risk — "high" (in flood plain),
                        "medium" (flood-prone/sensitive/regional overlay), or "low"
          - coastal_risk: worst-case coastal inundation risk — "high" (1% AEP),
                          "medium" (100-year return), or "low"
          - overall_risk: single worst level across flood and coastal.
                          Use this as the top-line safety signal.
          - hazard_sources: deduplicated list of data layer IDs contributing a hazard
                            flag at this suburb (e.g. ["auckland_flood_plain_100yr"]).
                            Empty list if no hazard layers triggered.
          - cells_examined: number of H3 cells assessed (coverage indicator)
          - error: present only if the suburb was not found in the data
    """
    # Step 1: resolve suburb name → suburb_id (fuzzy: exact first, ILIKE fallback)
    suburb_rows = _resolve(suburb_name)
    if not suburb_rows or not suburb_rows[0][0]:
        return {
            "suburb": suburb_name,
            "error": f"Suburb '{suburb_name}' not found. Check suburb name spelling.",
        }
    suburb_id, matched_name = suburb_rows[0][0], suburb_rows[0][1]

    # Step 2: join h3_cell → hazard to get all boolean hazard flags for this suburb
    hazard_rows = _execute(
        f"""
        SELECT h.in_flood_plain, h.in_flood_prone_area, h.in_flood_sensitive_area,
               h.in_coastal_inundation_1_aep, h.in_coastal_inundation_100yr,
               h.in_regional_flood_zone, h.hazard_sources
        FROM {_CATALOG}.{_SCHEMA}.h3_cell hc
        JOIN {_CATALOG}.{_SCHEMA}.hazard h ON hc.h3_cell = h.h3_cell
        WHERE hc.suburb_id = :suburb_id
        """,
        [{"name": "suburb_id", "value": suburb_id, "type": "STRING"}],
    )
    if not hazard_rows:
        return {
            "suburb": matched_name,
            "error": f"No hazard data found for '{matched_name}'. The suburb may be outside hazard data coverage.",
        }

    # Derive risk levels from boolean flags (worst-case across all H3 cells)
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

    # Flatten and deduplicate hazard_sources arrays across all cells
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
    hazard_sources = list(
        dict.fromkeys(s for s in all_sources if s)
    )  # dedupe, preserve order

    return {
        "suburb": matched_name,
        "flood_risk": flood_risk,
        "coastal_risk": coastal_risk,
        "overall_risk": overall_risk,
        "hazard_sources": hazard_sources,
        "cells_examined": len(hazard_rows),
    }
