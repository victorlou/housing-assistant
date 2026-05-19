import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import build_in_params as _build_in_params
from agent_server.tools.utils import execute_statement as _execute
from agent_server.tools.utils import resolve_suburb_fuzzy as _resolve

logger = logging.getLogger(__name__)


@tool
def compute_isochrone(suburb_name: str, mode: str, minutes: int) -> dict:
    """
    Return the list of suburbs reachable from an origin suburb within a travel-time limit.

    Call this first whenever the user mentions a workplace, commute, or travel time.
    The returned `reachable_suburbs` list is the candidate set — pass each suburb in that
    list to score_affordability and/or lookup_hazards to filter down to a shortlist.

    Trigger phrases: "commute from X", "30 minutes from Y", "what suburbs can I reach",
    "how far is X from work", "accessible by transit".

    When a colloquial name matches multiple Stats NZ SA2 areas (e.g. "Henderson" matches
    Henderson East and Henderson West), the isochrone is computed from ALL matched areas
    and the results are unioned — giving the full reachable set as the user would expect.

    Args:
        suburb_name: Origin suburb (e.g. "Auckland CBD", "Onehunga", "Henderson").
                     Use suburb names, not station/precinct labels.
        mode: Travel mode — "transit" (default), "drive", or "walk".
              Default to "transit" unless the user explicitly says they drive or walk.
        minutes: Maximum travel time in minutes. Default 30 unless stated otherwise.

    Returns:
        Dict with:
          - origin: resolved origin suburb name (or colloquial name if multiple SA2s matched)
          - matched_areas: list of SA2 names that were used as origin (len > 1 means merged)
          - mode: travel mode used
          - minutes: time limit applied
          - reachable_suburbs: deduplicated list of suburb names reachable within the limit.
                               Pass each of these to score_affordability / lookup_hazards.
          - reachable_count: number of distinct reachable suburbs found
          - error: present only if the origin suburb was not found in the data
    """
    suburb_rows = _resolve(suburb_name)
    if not suburb_rows or not suburb_rows[0][0]:
        return {
            "origin": suburb_name,
            "matched_areas": [],
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_count": 0,
            "error": f"Suburb '{suburb_name}' not found in housing data.",
        }

    suburb_ids = [row[0] for row in suburb_rows]
    matched_names = [row[1] for row in suburb_rows]
    display_name = matched_names[0] if len(suburb_ids) == 1 else suburb_name

    origin_placeholders, origin_params = _build_in_params(suburb_ids, "oid")

    result_rows = _execute(
        f"""
        SELECT DISTINCT s.suburb_name
        FROM {_CATALOG}.{_SCHEMA}.h3_cell origin_hc
        JOIN {_CATALOG}.{_SCHEMA}.isochrone iso ON origin_hc.h3_cell = iso.origin_h3
        JOIN {_CATALOG}.{_SCHEMA}.h3_cell dest_hc ON iso.destination_h3 = dest_hc.h3_cell
        JOIN {_CATALOG}.{_SCHEMA}.suburb s ON dest_hc.suburb_id = s.suburb_id
        WHERE origin_hc.suburb_id IN ({origin_placeholders})
          AND iso.mode = :mode
          AND iso.travel_minutes <= :minutes
          AND iso.travel_minutes > 0
          AND iso.computation_version = 'r5py-v2'
          AND s.suburb_id NOT IN ({origin_placeholders})
          AND s.population_2023 > 500
        ORDER BY s.suburb_name
        """,
        [
            *origin_params,
            {"name": "mode", "value": mode, "type": "STRING"},
            {"name": "minutes", "value": str(minutes), "type": "INT"},
        ],
    )

    reachable_suburbs = [row[0] for row in result_rows if row[0]]

    return {
        "origin": display_name,
        "matched_areas": matched_names,
        "mode": mode,
        "minutes": minutes,
        "reachable_suburbs": reachable_suburbs,
        "reachable_count": len(reachable_suburbs),
    }
