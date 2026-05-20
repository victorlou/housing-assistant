from typing import Optional

from langchain_core.tools import tool


@tool
def render_map(
    suburbs: list[dict],
    isochrone_suburb: Optional[str],
    isochrone_minutes: Optional[int],
    isochrone_mode: Optional[str],
    filter_summary: str,
) -> dict:
    """
    Update the frontend map with the current filter state. Call this after every
    filtering step (commute, rent, hazard) and whenever the user asks to focus on
    a specific suburb.

    Args:
        suburbs: List of {name: str, status: "active"|"dimmed"|"highlighted"} dicts.
            active = passes all filters (green pin)
            dimmed = eliminated by a filter (grey, still visible)
            highlighted = single suburb the user wants to zoom into (teal ring)
        isochrone_suburb: The commute-origin suburb name, or null if no commute filter.
        isochrone_minutes: Integer travel time cap, or null.
        isochrone_mode: "transit" | "walking" | "driving" | null
        filter_summary: 1-2 sentence plain-English summary of active filters shown as
            the map legend. E.g. "Within 30 min transit of Auckland CBD · Rent ≤ $700/wk"

    Returns:
        {"rendered": True} on success.
    """
    return {"rendered": True}
