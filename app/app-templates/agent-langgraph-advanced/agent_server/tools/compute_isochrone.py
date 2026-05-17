import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
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

    Args:
        suburb_name: Origin suburb (e.g. "Britomart", "Onehunga"). This is where the
                     user travels *from* — typically their workplace or CBD.
        mode: Travel mode — "transit" (default), "drive", or "walk".
              Default to "transit" unless the user explicitly says they drive or walk.
        minutes: Maximum travel time in minutes. Default 30 unless stated otherwise.

    Returns:
        Dict with:
          - origin: resolved origin suburb name
          - mode: travel mode used
          - minutes: time limit applied
          - reachable_suburbs: list of suburb names reachable within the time limit.
                               Pass each of these to score_affordability / lookup_hazards.
          - reachable_cell_count: number of distinct reachable suburbs found
          - error: present only if the origin suburb was not found in the data
    """
    # Step 1: resolve suburb name → suburb_id (fuzzy: exact first, ILIKE fallback)
    suburb_rows = _resolve(suburb_name)
    if not suburb_rows or not suburb_rows[0][0]:
        return {
            "origin": suburb_name,
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_cell_count": 0,
            "error": f"Suburb '{suburb_name}' not found in housing data.",
        }
    origin_suburb_id, matched_name = suburb_rows[0][0], suburb_rows[0][1]

    # Step 2: join all H3 cells in origin suburb → isochrone → destination cells → suburb.
    # Isochrone origin cells are transit-stop-adjacent — using suburb_id (not centroid_h3)
    # ensures we find the cells that are actually in the isochrone table.
    # travel_minutes > 0 drops self-reach rows; r5py-v2 is the current computation.
    result_rows = _execute(
        f"""
        SELECT DISTINCT s.suburb_name
        FROM {_CATALOG}.{_SCHEMA}.h3_cell origin_hc
        JOIN {_CATALOG}.{_SCHEMA}.isochrone iso ON origin_hc.h3_cell = iso.origin_h3
        JOIN {_CATALOG}.{_SCHEMA}.h3_cell dest_hc ON iso.destination_h3 = dest_hc.h3_cell
        JOIN {_CATALOG}.{_SCHEMA}.suburb s ON dest_hc.suburb_id = s.suburb_id
        WHERE origin_hc.suburb_id = :origin_suburb_id
          AND iso.mode = :mode
          AND iso.travel_minutes <= :minutes
          AND iso.travel_minutes > 0
          AND iso.computation_version = 'r5py-v2'
          AND s.suburb_id != :origin_suburb_id
          AND s.population_2023 > 500
        ORDER BY s.suburb_name
        """,
        [
            {"name": "origin_suburb_id", "value": origin_suburb_id, "type": "STRING"},
            {"name": "mode", "value": mode, "type": "STRING"},
            {"name": "minutes", "value": str(minutes), "type": "INT"},
        ],
    )

    reachable_suburbs = [row[0] for row in result_rows if row[0]]

    return {
        "origin": matched_name,
        "mode": mode,
        "minutes": minutes,
        "reachable_suburbs": reachable_suburbs,
        "reachable_cell_count": len(reachable_suburbs),
    }
