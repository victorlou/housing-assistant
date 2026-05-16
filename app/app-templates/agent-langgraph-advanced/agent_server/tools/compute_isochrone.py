import json
import logging

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import execute_statement as _execute

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
          - reachable_cell_count: number of H3 cells covered (proxy for geographic area)
          - error: present only if the origin suburb was not found in the data
    """
    # Step 1: resolve suburb name → h3_centroid
    centroid_rows = _execute(
        f"SELECT h3_centroid FROM {_CATALOG}.{_SCHEMA}.suburb WHERE suburb_name = :suburb LIMIT 1",
        [{"name": "suburb", "value": suburb_name, "type": "STRING"}],
    )
    if not centroid_rows or not centroid_rows[0][0]:
        return {
            "origin": suburb_name,
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_cell_count": 0,
            "error": f"Suburb '{suburb_name}' not found in housing data.",
        }
    h3_origin = centroid_rows[0][0]

    # Step 2: fetch h3_destinations for the closest minutes_bucket >= requested minutes
    iso_rows = _execute(
        f"""
        SELECT h3_destinations
        FROM {_CATALOG}.{_SCHEMA}.isochrone
        WHERE h3_origin = :h3_origin
          AND mode = :mode
          AND minutes_bucket = (
            SELECT MIN(minutes_bucket)
            FROM {_CATALOG}.{_SCHEMA}.isochrone
            WHERE h3_origin = :h3_origin
              AND mode = :mode
              AND minutes_bucket >= :minutes
          )
        LIMIT 1
        """,
        [
            {"name": "h3_origin", "value": h3_origin, "type": "STRING"},
            {"name": "mode", "value": mode, "type": "STRING"},
            {"name": "minutes", "value": str(minutes), "type": "INT"},
        ],
    )
    if not iso_rows or not iso_rows[0][0]:
        return {
            "origin": suburb_name,
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_cell_count": 0,
        }

    # h3_destinations is returned as a JSON array string by the Statement Execution API
    raw = iso_rows[0][0]
    h3_destinations: list[str] = json.loads(raw) if isinstance(raw, str) else list(raw)

    # Step 3: resolve destination cells → suburb names
    reachable_suburbs: list[str] = []
    if h3_destinations:
        placeholders = ", ".join(f"'{c}'" for c in h3_destinations)
        suburb_rows = _execute(
            f"""
            SELECT DISTINCT suburb_name
            FROM {_CATALOG}.{_SCHEMA}.suburb
            WHERE h3_centroid IN ({placeholders})
              AND suburb_name != :origin
            ORDER BY suburb_name
            """,
            [{"name": "origin", "value": suburb_name, "type": "STRING"}],
        )
        reachable_suburbs = [row[0] for row in suburb_rows if row[0]]

    return {
        "origin": suburb_name,
        "mode": mode,
        "minutes": minutes,
        "reachable_suburbs": reachable_suburbs,
        "reachable_cell_count": len(h3_destinations),
    }
