import logging
from typing import Optional

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import build_in_params as _build_in_params
from agent_server.tools.utils import execute_statement as _execute
from agent_server.tools.utils import resolve_suburb_fuzzy as _resolve

logger = logging.getLogger(__name__)


@tool
def score_affordability(
    suburb_name: str, household_income: Optional[float] = None
) -> dict:
    """
    Score the housing affordability of a suburb for a given (or median) household income.

    Call this on each suburb returned by compute_isochrone to filter candidates by budget,
    or directly when the user asks if a specific suburb is affordable. The tool is also
    the primary source of rent figures for planner affordability analysis.

    When a colloquial name matches multiple Stats NZ SA2 areas (e.g. "Henderson" covers
    Henderson East and Henderson West), rent and income figures are population-weighted
    across all matched SA2s to give a single representative answer.

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
          - suburb: suburb name (or colloquial name when multiple SA2s were merged)
          - matched_areas: list of SA2 names included in the calculation
          - median_rent_weekly: population-weighted median weekly rent (NZD)
          - annual_rent: weekly × 52 (NZD)
          - household_income_annual: income used (user-provided or weighted suburb median, NZD)
          - income_source: "user_provided" or "suburb_median"
          - income_decile: population-weighted 1–10 ranking (only when income_source = "suburb_median")
          - rent_to_income_pct: rent as a percentage of annual income (e.g. 38.5)
          - affordability_band: "affordable", "moderate stress", or "housing stressed"
          - data_year: census year of the suburb-level rent data
          - ta_median_rent_nzd: most recent monthly median rent at TA level (NZD)
          - ta_data_month: date of the TA-level rent observation
          - error: present only if rent or income data is missing for this suburb
    """
    suburb_rows = _resolve(suburb_name, ", territorial_authority")
    if not suburb_rows:
        return {"suburb": suburb_name, "error": f"Suburb '{suburb_name}' not found."}

    suburb_ids = [row[0] for row in suburb_rows]
    matched_names = [row[1] for row in suburb_rows]
    # Use TA from the most-populous match (first row after population-desc ordering)
    ta_name = suburb_rows[0][2]
    display_name = matched_names[0] if len(suburb_ids) == 1 else suburb_name

    id_placeholders, id_params = _build_in_params(suburb_ids, "sid")

    # Fetch rent + population for all matched SA2s (latest census year per suburb)
    rent_rows = _execute(
        f"""
        SELECT sy.suburb_id, sy.median_weekly_rent, sy.census_year,
               COALESCE(s.population_2023, 1) AS pop
        FROM {_CATALOG}.{_SCHEMA}.suburb__year sy
        JOIN {_CATALOG}.{_SCHEMA}.suburb s ON sy.suburb_id = s.suburb_id
        WHERE sy.suburb_id IN ({id_placeholders})
          AND sy.census_year = (
            SELECT MAX(sy2.census_year)
            FROM {_CATALOG}.{_SCHEMA}.suburb__year sy2
            WHERE sy2.suburb_id = sy.suburb_id
          )
        """,
        id_params,
    )
    if not rent_rows:
        return {
            "suburb": display_name,
            "error": f"No rent data found for '{display_name}'.",
        }

    # Population-weighted average rent
    total_pop = sum(float(r[3]) for r in rent_rows)
    weighted_rent = sum(float(r[1]) * float(r[3]) for r in rent_rows) / total_pop
    data_year = int(max(r[2] for r in rent_rows))

    # TA-level monthly rent (coarser but more current)
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
    ta_median_rent = (
        float(ta_rent_rows[0][0])
        if ta_rent_rows and ta_rent_rows[0][0] is not None
        else None
    )
    ta_data_month = (
        str(ta_rent_rows[0][1])
        if ta_rent_rows and ta_rent_rows[0][1] is not None
        else None
    )

    # Income — user-provided or population-weighted suburb median with decile
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
            SELECT r.suburb_id, r.median_household_income, r.income_decile,
                   COALESCE(s.population_2023, 1) AS pop
            FROM ranked r
            JOIN {_CATALOG}.{_SCHEMA}.suburb s ON r.suburb_id = s.suburb_id
            WHERE r.suburb_id IN ({id_placeholders})
            """,
            id_params,
        )
        if not income_rows:
            return {
                "suburb": display_name,
                "matched_areas": matched_names,
                "median_rent_weekly": int(round(weighted_rent)),
                "data_year": data_year,
                "error": f"No income data found for '{display_name}'. Provide a household_income value.",
            }
        inc_pop = sum(float(r[3]) for r in income_rows)
        household_income = sum(float(r[1]) * float(r[3]) for r in income_rows) / inc_pop
        # Population-weighted decile (round to nearest integer)
        income_decile = int(round(
            sum(float(r[2]) * float(r[3]) for r in income_rows) / inc_pop
        ))
        income_source = "suburb_median"

    annual_rent = weighted_rent * 52
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
        "suburb": display_name,
        "matched_areas": matched_names,
        "median_rent_weekly": int(round(weighted_rent)),
        "annual_rent": int(round(annual_rent)),
        "household_income_annual": int(round(household_income)),
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
