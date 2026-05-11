"""Save user preferences to Lakebase."""

from langchain_core.tools import tool
import os


@tool
def save_user_profile(constraints: dict) -> str:
    """
    Save user's constraints to Lakebase for future sessions.

    Args:
        constraints: Dict with keys (all optional):
            - budget_weekly: int
            - work_location: str
            - commute_mode: str ("transit", "drive", or "any")
            - max_commute_minutes: int
            - household_size: int
            - pets: bool
            - no_flood_zone: bool

    Returns:
        "Profile saved" or error message
    """
    # TODO: Implement Lakebase UPSERT
    # 1. Get user_id from CURRENT_USER_ID env var
    # 2. Connect to Lakebase (psycopg2)
    # 3. UPSERT into user_constraints table:
    #    INSERT INTO user_constraints (...) VALUES (...)
    #    ON CONFLICT (user_id) DO UPDATE SET ...
    # 4. Return "Profile saved"

    user_id = os.getenv("CURRENT_USER_ID")
    print(f"[STUB] save_user_profile: user_id={user_id}, constraints={constraints}")
    return "Profile saved"
