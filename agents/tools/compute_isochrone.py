"""Compute isochrone (reachable areas) from origin."""

from langchain_core.tools import tool
from typing import Optional


@tool
def compute_isochrone(origin_h3: str, mode: str, minutes: int) -> list[str]:
    """
    Return H3 cells reachable from origin_h3 in minutes or fewer.

    Args:
        origin_h3: Origin H3 cell ID (e.g., "8928308291bfffff")
        mode: Travel mode ("transit", "drive", or "walk")
        minutes: Travel time limit (e.g., 30 minutes)

    Returns:
        List of H3 cell IDs reachable within the time limit
    """
    # TODO: Implement isochrone lookup
    # 1. Get DatabricksSession
    # 2. Query housing.gold.fact_isochrone table:
    #    SELECT DISTINCT h3_destination
    #    FROM housing.gold.fact_isochrone
    #    WHERE h3_origin = %s AND mode = %s AND minutes <= %s
    # 3. Return list of H3 cells

    # Stub: Return empty list for now
    print(f"[STUB] compute_isochrone: origin={origin_h3}, mode={mode}, minutes={minutes}")
    return []
