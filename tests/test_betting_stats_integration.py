"""
Integration tests for betting stats data flow.

Tests verify the complete data flow from provider to verification layer,
ensuring field names match BettingStatsResponse schema and data is preserved correctly.
"""

from src.schemas.perplexity_schemas import BettingStatsResponse


class TestBettingStatsFormValidation:
    """Verify form validation works correctly."""

    def test_form_validation_total_exceeds_5_corrects_to_5(self):
        """
        Verify form validation corrects totals exceeding 5 to exactly 5.

        This test ensures the fix for Bug #2: Form validation logic flaw.
        The validator should reduce the largest field first, then the second largest,
        until total equals exactly 5.
        """
        # Test case 1: Total = 6 (exceeds by 1)
        response = BettingStatsResponse(
            home_form_wins=4,
            home_form_draws=2,
            home_form_losses=0,
            # Other fields with defaults
        )

        total = response.home_form_wins + response.home_form_draws + response.home_form_losses
        assert total == 5, (
            f"Expected total=5, got {total} (W={response.home_form_wins}, D={response.home_form_draws}, L={response.home_form_losses})"
        )

        # Test case 2: Total = 7 (exceeds by 2)
        response2 = BettingStatsResponse(
            home_form_wins=5,
            home_form_draws=1,
            home_form_losses=1,
            # Other fields with defaults
        )

        total2 = response2.home_form_wins + response2.home_form_draws + response2.home_form_losses
        assert total2 == 5, (
            f"Expected total=5, got {total2} (W={response2.home_form_wins}, D={response2.home_form_draws}, L={response2.home_form_losses})"
        )

        # Test case 3: Total = 8 (exceeds by 3)
        response3 = BettingStatsResponse(
            home_form_wins=5,
            home_form_draws=2,
            home_form_losses=1,
            # Other fields with defaults
        )

        total3 = response3.home_form_wins + response3.home_form_draws + response3.home_form_losses
        assert total3 == 5, (
            f"Expected total=5, got {total3} (W={response3.home_form_wins}, D={response3.home_form_draws}, L={response3.home_form_losses})"
        )

    def test_form_validation_away_team(self):
        """Verify form validation works correctly for away team."""
        # Test case: Total = 6 (exceeds by 1)
        response = BettingStatsResponse(
            away_form_wins=3,
            away_form_draws=2,
            away_form_losses=1,
            # Other fields with defaults
        )

        total = response.away_form_wins + response.away_form_draws + response.away_form_losses
        assert total == 5, (
            f"Expected total=5, got {total} (W={response.away_form_wins}, D={response.away_form_draws}, L={response.away_form_losses})"
        )

    def test_form_validation_total_equals_5_unchanged(self):
        """Verify form validation doesn't change totals that equal 5."""
        response = BettingStatsResponse(
            home_form_wins=3,
            home_form_draws=1,
            home_form_losses=1,
            away_form_wins=2,
            away_form_draws=2,
            away_form_losses=1,
            # Other fields with defaults
        )

        home_total = response.home_form_wins + response.home_form_draws + response.home_form_losses
        away_total = response.away_form_wins + response.away_form_draws + response.away_form_losses

        assert home_total == 5, f"Expected home_total=5, got {home_total}"
        assert away_total == 5, f"Expected away_total=5, got {away_total}"

    def test_form_validation_total_less_than_5_unchanged(self):
        """Verify form validation doesn't change totals less than 5."""
        response = BettingStatsResponse(
            home_form_wins=2,
            home_form_draws=1,
            home_form_losses=0,
            away_form_wins=1,
            away_form_draws=1,
            away_form_losses=0,
            # Other fields with defaults
        )

        home_total = response.home_form_wins + response.home_form_draws + response.home_form_losses
        away_total = response.away_form_wins + response.away_form_draws + response.away_form_losses

        assert home_total == 3, f"Expected home_total=3, got {home_total}"
        assert away_total == 2, f"Expected away_total=2, got {away_total}"
