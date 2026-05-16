import logging
from typing import Optional

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import execute_statement as _execute

logger = logging.getLogger(__name__)


@tool
def score_affordability(suburb_name: str, household_income: Optional[float] = None) -> dict:
    """
    Score the housing affordability of a suburb for a given (or median) household income.

    Call this on each suburb returned by compute_isochrone to filter candidates by budget,
    or directly when the user asks if a specific suburb is affordable. The tool is also
    the primary source of rent figures for planner affordability analysis.

    Trigger phrases: "can I afford X", "how much is rent in Y", "is Y within my budget",
    "compare rent across these suburbs", "affordability analysis", "rent-to-income ratio".

    Affordability bands (rent as % of annual income):
      - affordable       → rent < 25%  of annual income
      - moderate stress  → rent 25–35% of annual income
      - housing stressed → rent > 35%  of annual income

    Note: The 30% threshold stated in the glossary is the user-facing definition.
    The bands use 25/35 to give a graduated signal rather than a binary cut.

    Args:
        suburb_name: Suburb name (e.g. "Onehunga", "Mt Albert")
        household_income: Annual household income in NZD. Omit if the user has not
                          stated their income — the tool uses the suburb's median income
                          instead and returns income_decile (1=lowest, 10=highest).
                          income_decile is especially useful for planner queries
                          about low-income households.

    Returns:
        Dict with:
          - suburb: suburb name
          - median_rent_weekly: latest median weekly rent, all dwelling types (NZD)
          - annual_rent: weekly × 52 (NZD)
          - household_income_annual: income used (user-provided or suburb median, NZD)
          - income_source: "user_provided" or "suburb_median"
          - income_decile: 1–10 ranking (only present when income_source = "suburb_median")
          - rent_to_income_pct: rent as a percentage of annual income (e.g. 38.5)
          - affordability_band: "affordable", "moderate stress", or "housing stressed"
          - data_month: YYYY-MM-DD of the rent data used (cite this in planner responses)
          - error: present only if rent or income data is missing for this suburb
    """
    # Step 1: latest median rent for suburb (all dwelling types)
    rent_rows = _execute(
        f"""
        SELECT median_rent_weekly, month
        FROM {_CATALOG}.{_SCHEMA}.rent__month__suburb
        WHERE suburb_name = :suburb
          AND dwelling_type = 'all'
          AND month = (
            SELECT MAX(month)
            FROM {_CATALOG}.{_SCHEMA}.rent__month__suburb
            WHERE suburb_name = :suburb AND dwelling_type = 'all'
          )
        LIMIT 1
        """,
        [{"name": "suburb", "value": suburb_name, "type": "STRING"}],
    )
    if not rent_rows:
        return {"suburb": suburb_name, "error": f"No rent data found for '{suburb_name}'."}

    weekly_rent = float(rent_rows[0][0])
    data_month = str(rent_rows[0][1])

    # Step 2: income — user-provided or suburb median
    income_source = "user_provided"
    income_decile = None

    if household_income is None:
        income_rows = _execute(
            f"""
            SELECT median_household_income_annual, income_decile
            FROM {_CATALOG}.{_SCHEMA}.income__year__suburb
            WHERE suburb_name = :suburb
              AND year = (
                SELECT MAX(year)
                FROM {_CATALOG}.{_SCHEMA}.income__year__suburb
                WHERE suburb_name = :suburb
              )
            LIMIT 1
            """,
            [{"name": "suburb", "value": suburb_name, "type": "STRING"}],
        )
        if not income_rows:
            return {
                "suburb": suburb_name,
                "median_rent_weekly": int(weekly_rent),
                "error": f"No income data found for '{suburb_name}'. Provide a household_income value.",
            }
        household_income = float(income_rows[0][0])
        income_decile = income_rows[0][1]
        income_source = "suburb_median"

    annual_rent = weekly_rent * 52
    ratio = annual_rent / household_income if household_income > 0 else None
    pct = round(ratio * 100, 1) if ratio is not None else None

    if ratio is None:
        band = "unknown"
    elif ratio < 0.25:
        band = "affordable"
    elif ratio <= 0.35:
        band = "moderate stress"
    else:
        band = "housing stressed"

    result: dict = {
        "suburb": suburb_name,
        "median_rent_weekly": int(weekly_rent),
        "annual_rent": int(annual_rent),
        "household_income_annual": int(household_income),
        "income_source": income_source,
        "rent_to_income_pct": pct,
        "affordability_band": band,
        "data_month": data_month,
    }
    if income_decile is not None:
        result["income_decile"] = income_decile

    return result
