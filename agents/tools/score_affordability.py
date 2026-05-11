"""Score affordability of a suburb."""

from langchain_core.tools import tool


@tool
def score_affordability(suburb: str, user_income: int) -> float:
    """
    Score suburb affordability (0.0 = unaffordable, 1.0 = very affordable).

    Logic:
    - If median_rent <= 30% of user_income: score = 1.0
    - Otherwise: score decreases linearly towards 0.0

    Args:
        suburb: Suburb name (e.g., "Newton")
        user_income: User's annual household income (NZD)

    Returns:
        Affordability score (float between 0.0 and 1.0)
    """
    # TODO: Implement affordability scoring
    # 1. Get median rent for suburb from housing.gold.fact_rent_by_suburb_month
    # 2. Calculate weekly threshold = user_income * 0.3 / 52
    # 3. Apply scoring logic:
    #    if rent_weekly <= threshold: return 1.0
    #    else: return max(0.0, 1.0 - (rent_weekly - threshold) / threshold)

    # Stub: Return 0.5 for now
    print(f"[STUB] score_affordability: suburb={suburb}, income={user_income}")
    return 0.5
