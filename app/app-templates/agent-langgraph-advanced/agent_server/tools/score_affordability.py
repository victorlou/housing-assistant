import logging
from typing import Optional

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import execute_statement as _execute
from agent_server.tools.utils import resolve_suburb_fuzzy as _resolve

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
          - median_rent_weekly: census median weekly rent for the suburb (NZD)
          - annual_rent: weekly × 52 (NZD)
          - household_income_annual: income used (user-provided or suburb median, NZD)
          - income_source: "user_provided" or "suburb_median"
          - income_decile: 1–10 ranking (only present when income_source = "suburb_median")
          - rent_to_income_pct: rent as a percentage of annual income (e.g. 38.5)
          - affordability_band: "affordable", "moderate stress", or "housing stressed"
          - data_year: census year of the suburb-level rent data (e.g. 2023)
          - ta_median_rent_nzd: most recent monthly median rent at TA level (NZD) — more
                                current than census data but coarser geography. For Auckland
                                suburbs this is uniform across all 633 Auckland SA2s (post-
                                supercity amalgamation — one TA covers the whole region).
          - ta_data_month: date of the TA-level rent observation (cite this for currency)
          - error: present only if rent or income data is missing for this suburb
    """
    # Step 1: resolve suburb → suburb_id and territorial_authority (fuzzy: exact first, ILIKE fallback)
    suburb_rows = _resolve(suburb_name, ", territorial_authority")
    if not suburb_rows:
        return {"suburb": suburb_name, "error": f"Suburb '{suburb_name}' not found."}
    suburb_id, matched_name, ta_name = suburb_rows[0][0], suburb_rows[0][1], suburb_rows[0][2]

    # Step 2: suburb-level census rent (primary — most granular)
    rent_rows = _execute(
        f"""
        SELECT median_weekly_rent, census_year
        FROM {_CATALOG}.{_SCHEMA}.suburb__year
        WHERE suburb_id = :suburb_id
          AND census_year = (
            SELECT MAX(census_year)
            FROM {_CATALOG}.{_SCHEMA}.suburb__year
            WHERE suburb_id = :suburb_id
          )
        LIMIT 1
        """,
        [{"name": "suburb_id", "value": suburb_id, "type": "STRING"}],
    )
    if not rent_rows:
        return {"suburb": matched_name, "error": f"No rent data found for '{matched_name}'."}
    weekly_rent = float(rent_rows[0][0])
    data_year = int(rent_rows[0][1])

    # Step 3: TA-level monthly rent (supplement — more current, coarser geography).
    # Filter median_rent_nzd IS NOT NULL — ta__month rows for HPI/sales-only months have NULL rent.
    ta_rent_rows = _execute(
        f"""
        SELECT median_rent_nzd, date
        FROM {_CATALOG}.{_SCHEMA}.ta__month
        WHERE ta_name = :ta_name
          AND median_rent_nzd IS NOT NULL
          AND date = (
            SELECT MAX(date)
            FROM {_CATALOG}.{_SCHEMA}.ta__month
            WHERE ta_name = :ta_name
              AND median_rent_nzd IS NOT NULL
          )
        LIMIT 1
        """,
        [{"name": "ta_name", "value": ta_name, "type": "STRING"}],
    )
    ta_median_rent = float(ta_rent_rows[0][0]) if ta_rent_rows and ta_rent_rows[0][0] is not None else None
    ta_data_month = str(ta_rent_rows[0][1]) if ta_rent_rows and ta_rent_rows[0][1] is not None else None

    # Step 4: income — user-provided or suburb median with computed decile
    income_source = "user_provided"
    income_decile = None

    if household_income is None:
        income_rows = _execute(
            f"""
            WITH ranked AS (
              SELECT suburb_id, median_household_income,
                     NTILE(10) OVER (ORDER BY median_household_income) AS income_decile
              FROM {_CATALOG}.{_SCHEMA}.suburb__year
              WHERE census_year = (
                SELECT MAX(census_year) FROM {_CATALOG}.{_SCHEMA}.suburb__year
              )
            )
            SELECT median_household_income, income_decile
            FROM ranked
            WHERE suburb_id = :suburb_id
            """,
            [{"name": "suburb_id", "value": suburb_id, "type": "STRING"}],
        )
        if not income_rows:
            return {
                "suburb": matched_name,
                "median_rent_weekly": int(weekly_rent),
                "data_year": data_year,
                "error": f"No income data found for '{matched_name}'. Provide a household_income value.",
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
        "suburb": matched_name,
        "median_rent_weekly": int(weekly_rent),
        "annual_rent": int(annual_rent),
        "household_income_annual": int(household_income),
        "income_source": income_source,
        "rent_to_income_pct": pct,
        "affordability_band": band,
        "data_year": data_year,
    }
    if ta_median_rent is not None:
        result["ta_median_rent_nzd"] = int(ta_median_rent)
        result["ta_data_month"] = ta_data_month
    if income_decile is not None:
        result["income_decile"] = income_decile

    return result
