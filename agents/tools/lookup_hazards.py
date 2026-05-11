"""Look up natural hazards for a suburb."""

from langchain_core.tools import tool


@tool
def lookup_hazards(suburb: str) -> dict:
    """
    Return hazard risks for suburb (flood, coastal, liquefaction).

    Args:
        suburb: Suburb name (e.g., "Newton")

    Returns:
        Dict with keys:
        - flood_risk: "high", "medium", or "low"
        - coastal_risk: "high", "medium", or "low"
        - liquefaction_risk: "high", "medium", or "low"
    """
    # TODO: Implement hazard lookup
    # 1. Get suburb's H3 cells from housing.gold.dim_suburb
    # 2. Query housing.gold.dim_hazard for those cells
    # 3. Aggregate risk levels (if any cell is "high", return "high"; else if any is "medium", return "medium"; else "low")
    # 4. Return dict with all three risk types

    # Stub: Return low risk for all
    print(f"[STUB] lookup_hazards: suburb={suburb}")
    return {
        "flood_risk": "low",
        "coastal_risk": "low",
        "liquefaction_risk": "low",
    }
