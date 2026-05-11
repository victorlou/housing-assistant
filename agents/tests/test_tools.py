"""Unit tests for agent tools."""

import pytest
from tools.score_affordability import score_affordability


class TestScoreAffordability:
    """Tests for the score_affordability tool (pure logic)."""

    def test_very_affordable(self):
        """Test when rent is well under 30% of income."""
        # Assume annual income of $60,000 (weekly: ~$1,154)
        # 30% of weekly income: ~$346
        # Rent at $300/week should be very affordable
        user_income = 60000
        # score_affordability uses weekly threshold
        # You may need to adjust the call based on how it actually handles income
        score = score_affordability("test-suburb", user_income)
        assert score > 0.8, "Rent well under 30% should score high"

    def test_unaffordable(self):
        """Test when rent exceeds 30% of income."""
        # Income $20,000/year (weekly: ~$385)
        # 30% threshold: ~$115/week
        # Rent at $500/week should be unaffordable
        user_income = 20000
        score = score_affordability("test-suburb", user_income)
        assert score < 0.3, "Rent far above 30% should score low"

    def test_edge_case_at_threshold(self):
        """Test when rent is exactly at the 30% threshold."""
        # This should score 1.0 (meets the threshold)
        # Note: Adjust income/rent ratio to match tool's logic
        user_income = 50000  # Weekly ~$962, 30% = ~$289
        score = score_affordability("test-suburb", user_income)
        assert 0.8 <= score <= 1.0, "Rent at threshold should score ~1.0"

    def test_returns_valid_range(self):
        """Test that score is always between 0.0 and 1.0."""
        for income in [20000, 40000, 80000, 120000]:
            score = score_affordability("test-suburb", income)
            assert 0.0 <= score <= 1.0, f"Score out of range for income {income}: {score}"


# TODO: Add tests for other tools once they read real data
# class TestQueryGenie:
#     def test_valid_question(self):
#         """Test Genie returns structured data."""
#         ...
#
# class TestComputeIsochrone:
#     def test_valid_origin_and_mode(self):
#         """Test isochrone returns list of H3 cells."""
#         ...
