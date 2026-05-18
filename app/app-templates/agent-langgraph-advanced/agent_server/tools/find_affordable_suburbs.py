import logging
from typing import Optional

from langchain_core.tools import tool

from agent_server.tools.utils import CATALOG as _CATALOG
from agent_server.tools.utils import SCHEMA as _SCHEMA
from agent_server.tools.utils import execute_statement as _execute
from agent_server.tools.utils import resolve_suburb_fuzzy as _resolve

logger = logging.getLogger(__name__)

_RISK_ORDER = {"high": 2, "medium": 1, "low": 0, "unknown": -1}


def _worst(a: str, b: str) -> str:
    return a if _RISK_ORDER.get(a, -1) >= _RISK_ORDER.get(b, -1) else b


@tool
def find_affordable_suburbs(
    origin: str,
    mode: str = "transit",
    minutes: int = 30,
    max_weekly_rent: Optional[float] = None,
    household_income: Optional[float] = None,
    exclude_high_flood: bool = False,
    exclude_high_coastal: bool = False,
    limit: int = 8,
) -> dict:
    """
    Find suburbs matching commute, budget, and hazard constraints in a single step.

    Use this whenever the user gives you a combination of constraints — origin workplace,
    rent budget, income, and/or hazard preference. It runs isochrone + rent scoring +
    hazard filtering in one query and returns a pre-ranked shortlist. This avoids calling
    compute_isochrone, score_affordability, and lookup_hazards separately for each suburb.

    Use the individual tools instead when:
      - The user asks about one specific suburb ("is Onehunga affordable?")
      - You only need one dimension (just hazard, just rent, just commute)
      - You need the full reachable suburb list without filtering

    Args:
        origin: Origin suburb or workplace area (e.g. "Newmarket", "Britomart")
        mode: Travel mode — "transit" (default) or "walk"
        minutes: Maximum travel time in minutes (default 30)
        max_weekly_rent: Only return suburbs with median weekly rent ≤ this (NZD).
                         Convert the user's weekly budget directly — do not annualise.
        household_income: Annual household income in NZD for rent-to-income calculation.
                          If omitted, uses each suburb's median income and returns
                          income_decile (1=lowest, 10=highest) per suburb.
        exclude_high_flood: If True, drop suburbs where flood_risk = "high"
        exclude_high_coastal: If True, drop suburbs where coastal_risk = "high"
        limit: Max suburbs to return, sorted cheapest rent first (default 8, max 10)

    Returns:
        Dict with:
          - origin: resolved origin suburb
          - mode, minutes: parameters used
          - income_source: "user_provided" or "suburb_median"
          - results: list of dicts — suburb_name, median_rent_weekly, rent_to_income_pct,
                     affordability_band, flood_risk, coastal_risk, overall_risk,
                     and income_decile when income_source = "suburb_median"
          - filtered_count: number of suburbs in results
          - error: present if origin suburb not found
    """
    # Step 1: resolve origin suburb_id (fuzzy: exact first, ILIKE fallback)
    suburb_rows = _resolve(origin)
    if not suburb_rows or not suburb_rows[0][0]:
        return {
            "origin": origin,
            "results": [],
            "error": f"Suburb '{origin}' not found.",
        }
    origin_suburb_id, matched_origin = suburb_rows[0][0], suburb_rows[0][1]

    income_param = (
        float(household_income) if household_income and household_income > 0 else 0.0
    )
    using_user_income = income_param > 0
    safe_limit = min(int(limit), 10)

    # Build optional WHERE clauses (values injected via params to avoid injection)
    flood_clause = "AND hz.flood_risk != 'high'" if exclude_high_flood else ""
    coastal_clause = "AND hz.coastal_risk != 'high'" if exclude_high_coastal else ""
    rent_clause = "AND sd.median_weekly_rent <= :max_rent" if max_weekly_rent else ""
    max_rent_val = float(max_weekly_rent) if max_weekly_rent else 9_999_999.0

    # Step 2: single compound query — isochrone + rent + income + hazard aggregate
    rows = _execute(
        f"""
        WITH reachable AS (
          SELECT DISTINCT dest_hc.suburb_id
          FROM {_CATALOG}.{_SCHEMA}.h3_cell origin_hc
          JOIN {_CATALOG}.{_SCHEMA}.isochrone iso
            ON origin_hc.h3_cell = iso.origin_h3
          JOIN {_CATALOG}.{_SCHEMA}.h3_cell dest_hc
            ON iso.destination_h3 = dest_hc.h3_cell
          WHERE origin_hc.suburb_id = :origin_suburb_id
            AND iso.mode        = :mode
            AND iso.travel_minutes <= :minutes
            AND iso.travel_minutes  > 0
            AND iso.computation_version = 'r5py-v2'
            AND dest_hc.suburb_id != :origin_suburb_id
        ),
        suburb_data AS (
          SELECT suburb_id, median_weekly_rent, median_household_income,
                 NTILE(10) OVER (ORDER BY median_household_income) AS income_decile
          FROM {_CATALOG}.{_SCHEMA}.suburb__year
          QUALIFY ROW_NUMBER() OVER (PARTITION BY suburb_id ORDER BY census_year DESC) = 1
        ),
        hazard_agg AS (
          SELECT
            hc.suburb_id,
            CASE
              WHEN BOOL_OR(h.in_flood_plain) THEN 'high'
              WHEN BOOL_OR(h.in_flood_prone_area)
                OR BOOL_OR(h.in_flood_sensitive_area)
                OR BOOL_OR(h.in_regional_flood_zone) THEN 'medium'
              ELSE 'low'
            END AS flood_risk,
            CASE
              WHEN BOOL_OR(h.in_coastal_inundation_1_aep) THEN 'high'
              WHEN BOOL_OR(h.in_coastal_inundation_100yr)  THEN 'medium'
              ELSE 'low'
            END AS coastal_risk
          FROM {_CATALOG}.{_SCHEMA}.h3_cell hc
          JOIN {_CATALOG}.{_SCHEMA}.hazard h ON hc.h3_cell = h.h3_cell
          WHERE hc.suburb_id IN (SELECT suburb_id FROM reachable)
          GROUP BY hc.suburb_id
        )
        SELECT
          s.suburb_name,
          sd.median_weekly_rent,
          ROUND(
            sd.median_weekly_rent * 52.0
            / CASE WHEN :income_param > 0 THEN :income_param
                   ELSE sd.median_household_income END
            * 100, 1
          )                                        AS rent_to_income_pct,
          CASE
            WHEN sd.median_weekly_rent * 52.0
                 / CASE WHEN :income_param > 0 THEN :income_param
                        ELSE sd.median_household_income END < 0.25 THEN 'affordable'
            WHEN sd.median_weekly_rent * 52.0
                 / CASE WHEN :income_param > 0 THEN :income_param
                        ELSE sd.median_household_income END <= 0.35 THEN 'moderate stress'
            ELSE 'housing stressed'
          END                                      AS affordability_band,
          sd.income_decile,
          COALESCE(hz.flood_risk,   'unknown')     AS flood_risk,
          COALESCE(hz.coastal_risk, 'unknown')     AS coastal_risk
        FROM reachable rec
        JOIN {_CATALOG}.{_SCHEMA}.suburb s  ON rec.suburb_id = s.suburb_id
        JOIN suburb_data sd                 ON rec.suburb_id = sd.suburb_id
        LEFT JOIN hazard_agg hz             ON rec.suburb_id = hz.suburb_id
        WHERE s.population_2023 > 500
          {rent_clause}
          {flood_clause}
          {coastal_clause}
        ORDER BY sd.median_weekly_rent ASC
        LIMIT {safe_limit}
        """,
        [
            {"name": "origin_suburb_id", "value": origin_suburb_id, "type": "STRING"},
            {"name": "mode", "value": mode, "type": "STRING"},
            {"name": "minutes", "value": str(minutes), "type": "INT"},
            {"name": "income_param", "value": str(income_param), "type": "DOUBLE"},
            {"name": "max_rent", "value": str(max_rent_val), "type": "DOUBLE"},
        ],
    )

    results = []
    for row in rows:
        (
            suburb_name,
            median_rent,
            rent_pct,
            band,
            income_decile,
            flood_risk,
            coastal_risk,
        ) = row
        entry = {
            "suburb_name": suburb_name,
            "median_rent_weekly": int(median_rent) if median_rent is not None else None,
            "rent_to_income_pct": float(rent_pct) if rent_pct is not None else None,
            "affordability_band": band,
            "flood_risk": flood_risk,
            "coastal_risk": coastal_risk,
            "overall_risk": _worst(flood_risk or "unknown", coastal_risk or "unknown"),
        }
        if not using_user_income and income_decile is not None:
            entry["income_decile"] = income_decile
        results.append(entry)

    return {
        "origin": matched_origin,
        "mode": mode,
        "minutes": minutes,
        "income_source": "user_provided" if using_user_income else "suburb_median",
        "results": results,
        "filtered_count": len(results),
    }
