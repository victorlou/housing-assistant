"""Set up an alert for saved search."""

from langchain_core.tools import tool
import os


@tool
def set_alert(query: str, threshold: float, channel: str) -> str:
    """
    Save a search and set up alerts.

    Args:
        query: Natural language query (e.g., "suburbs under $800 near work")
        threshold: Alert trigger (float 0.0-1.0, e.g., 0.5 = alert if affordability drops below 50%)
        channel: Notification channel ("email", "push", or "webhook")

    Returns:
        "Alert set" or error message
    """
    # TODO: Implement alert creation
    # 1. Get user_id from CURRENT_USER_ID env var
    # 2. Connect to Lakebase (psycopg2)
    # 3. INSERT into saved_searches table (if doesn't exist)
    # 4. INSERT into alerts table with affordability_threshold and channel
    # 5. Return "Alert set"

    user_id = os.getenv("CURRENT_USER_ID")
    print(f"[STUB] set_alert: user_id={user_id}, query={query}, threshold={threshold}, channel={channel}")
    return "Alert set"
