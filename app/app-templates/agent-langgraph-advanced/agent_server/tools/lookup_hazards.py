import json
import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import execute_statement as _execute

logger = logging.getLogger(__name__)

_RISK_ORDER = {"high": 2, "medium": 1, "low": 0}


def _worst(levels: list[str]) -> str:
    return max(levels, key=lambda x: _RISK_ORDER.get(x, -1), default="unknown")


@tool
def lookup_hazards(suburb_name: str) -> dict:
    """
    Return worst-case natural hazard risk levels for a suburb across flood, coastal,
    and liquefaction categories.

    Call this for every suburb that passes the budget/commute filter when the user
    has a hazard constraint (flood zone avoidance, earthquake safety, coastal concerns).
    Also call in planner queries to identify "double burden" suburbs — areas that are
    both housing-stressed (from score_affordability) and high-risk (from this tool).
    Double-burden suburbs are the strongest candidates for council intervention.

    Trigger phrases: "flood zone", "flood risk", "earthquake", "liquefaction", "coastal",
    "natural disaster", "safe area", "not near water", "post-Cyclone Gabrielle".

    Risk levels per category: "low", "medium", "high".
    Worst-case rule: any H3 cell with "high" → suburb is "high" for that category.
    A suburb-level "medium" means no cells are high but at least one is medium.

    Args:
        suburb_name: Suburb name (e.g. "Henderson", "Takanini", "Mangere")

    Returns:
        Dict with:
          - suburb: suburb name
          - flood_risk: worst-case flood risk across the suburb's H3 cells
          - coastal_risk: worst-case coastal inundation/erosion risk
          - liquefaction_risk: worst-case liquefaction/earthquake risk
          - overall_risk: single worst level across all three categories.
                          Use this as the top-line safety signal.
          - flood_zone_name: Auckland Council flood zone name if applicable, else null
          - cells_examined: number of H3 cells assessed (coverage indicator)
          - error: present only if the suburb was not found in the data
    """
    # Step 1: resolve suburb name → h3_cells array.
    # LATERAL VIEW + JOIN is not supported by the Statement Execution API; do it in two queries.
    cell_rows = _execute(
        f"SELECT h3_cells FROM {_CATALOG}.{_SCHEMA}.suburb WHERE suburb_name = :suburb LIMIT 1",
        [{"name": "suburb", "value": suburb_name, "type": "STRING"}],
    )
    if not cell_rows or not cell_rows[0][0]:
        return {
            "suburb": suburb_name,
            "error": f"Suburb '{suburb_name}' not found. Check suburb name spelling.",
        }
    raw = cell_rows[0][0]
    h3_cells: list[str] = json.loads(raw) if isinstance(raw, str) else list(raw)
    if not h3_cells:
        return {
            "suburb": suburb_name,
            "error": f"No H3 cells found for '{suburb_name}'.",
        }

    # Step 2: fetch hazard rows for those cells using IN with string literals.
    placeholders = ", ".join(f"'{c}'" for c in h3_cells)
    hazard_rows = _execute(
        f"""
        SELECT flood_risk, coastal_risk, liquefaction_risk, flood_zone_name
        FROM {_CATALOG}.{_SCHEMA}.hazard
        WHERE h3_cell IN ({placeholders})
        """,
        [],
    )
    if not hazard_rows:
        return {
            "suburb": suburb_name,
            "error": f"No hazard data found for '{suburb_name}'. Check suburb name spelling.",
        }

    flood_levels        = [row[0] for row in hazard_rows if row[0]]
    coastal_levels      = [row[1] for row in hazard_rows if row[1]]
    liquefaction_levels = [row[2] for row in hazard_rows if row[2]]
    flood_zone_names    = [row[3] for row in hazard_rows if row[3]]

    flood_risk = _worst(flood_levels)
    coastal_risk = _worst(coastal_levels)
    liquefaction_risk = _worst(liquefaction_levels)
    overall_risk = _worst([flood_risk, coastal_risk, liquefaction_risk])

    return {
        "suburb": suburb_name,
        "flood_risk": flood_risk,
        "coastal_risk": coastal_risk,
        "liquefaction_risk": liquefaction_risk,
        "overall_risk": overall_risk,
        "flood_zone_name": flood_zone_names[0] if flood_zone_names else None,
        "cells_examined": len(hazard_rows),
    }
