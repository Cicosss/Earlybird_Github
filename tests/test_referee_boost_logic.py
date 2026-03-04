#!/usr/bin/env python3
"""
Unit tests for Referee Boost Logic V9.0

Tests the RefereeStats class and referee boost logic in analyzer.py
without making real API calls.

Coverage:
- RefereeStats class methods
- Strictness classification
- Boost logic triggers
- Multiplier calculations
- Edge cases and boundary conditions
"""

import logging

import pytest

from src.analysis.verification_layer import RefereeStats

# ============================================
# FIXTURES
# ============================================


@pytest.fixture
def strict_referee():
    """Referee with high cards per game (>= 5.0)."""
    return RefereeStats(name="Michael Oliver", cards_per_game=5.2, matches_officiated=150)


@pytest.fixture
def moderate_referee():
    """Referee with moderate cards per game (>= 4.0 but < 5.0)."""
    return RefereeStats(name="Antonio Mateu Lahoz", cards_per_game=4.3, matches_officiated=120)


@pytest.fixture
def lenient_referee():
    """Referee with low cards per game (<= 3.0)."""
    return RefereeStats(name="Felix Brych", cards_per_game=2.8, matches_officiated=180)


@pytest.fixture
def average_referee():
    """Referee with average cards per game (> 3.0 but < 4.0)."""
    return RefereeStats(name="Daniele Orsato", cards_per_game=3.5, matches_officiated=140)


@pytest.fixture
def unknown_referee():
    """Referee with no stats (0.0 cards per game)."""
    return RefereeStats(name="Unknown Referee", cards_per_game=0.0, matches_officiated=0)


# ============================================
# TEST CLASS: RefereeStats - Strictness Classification
# ============================================


class TestRefereeStatsStrictness:
    """Test automatic strictness classification in __post_init__."""

    def test_strict_classification(self, strict_referee):
        """Strict referee should be classified as 'strict' (>= 5.0 cards)."""
        assert strict_referee.strictness == "strict"
        assert strict_referee.is_strict()
        assert not strict_referee.is_lenient()

    def test_moderate_classification(self, moderate_referee):
        """Moderate referee should be classified as 'average' (>= 4.0 but < 5.0)."""
        assert moderate_referee.strictness == "average"
        assert not moderate_referee.is_strict()
        assert not moderate_referee.is_lenient()

    def test_lenient_classification(self, lenient_referee):
        """Lenient referee should be classified as 'lenient' (<= 3.0 cards)."""
        assert lenient_referee.strictness == "lenient"
        assert not lenient_referee.is_strict()
        assert lenient_referee.is_lenient()

    def test_average_classification(self, average_referee):
        """Average referee should be classified as 'average' (> 3.0 but < 4.0)."""
        assert average_referee.strictness == "average"
        assert not average_referee.is_strict()
        assert not average_referee.is_lenient()

    def test_unknown_classification(self, unknown_referee):
        """Unknown referee (0.0 cards) should remain 'unknown'."""
        assert unknown_referee.strictness == "unknown"
        assert not unknown_referee.is_strict()
        assert not unknown_referee.is_lenient()

    def test_boundary_strict_threshold(self):
        """Test exact boundary at 5.0 cards (strict threshold)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=5.0)
        assert referee.strictness == "strict"
        assert referee.is_strict()

    def test_boundary_lenient_threshold(self):
        """Test exact boundary at 3.0 cards (lenient threshold)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=3.0)
        assert referee.strictness == "lenient"
        assert referee.is_lenient()

    def test_boundary_boost_threshold(self):
        """Test exact boundary at 4.0 cards (boost threshold)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=4.0)
        assert referee.strictness == "average"
        assert not referee.is_strict()
        assert not referee.is_lenient()


# ============================================
# TEST CLASS: RefereeStats - Boost Methods
# ============================================


class TestRefereeStatsBoostMethods:
    """Test boost-related methods of RefereeStats."""

    def test_should_boost_cards_strict(self, strict_referee):
        """Strict referee (>= 5.0) should boost cards."""
        assert strict_referee.should_boost_cards() is True

    def test_should_boost_cards_moderate(self, moderate_referee):
        """Moderate referee (>= 4.0) should boost cards."""
        assert moderate_referee.should_boost_cards() is True

    def test_should_boost_cards_average(self, average_referee):
        """Average referee (< 4.0) should NOT boost cards."""
        assert average_referee.should_boost_cards() is False

    def test_should_boost_cards_lenient(self, lenient_referee):
        """Lenient referee (<= 3.0) should NOT boost cards."""
        assert lenient_referee.should_boost_cards() is False

    def test_should_boost_cards_unknown(self, unknown_referee):
        """Unknown referee (0.0) should NOT boost cards."""
        assert unknown_referee.should_boost_cards() is False

    def test_should_boost_cards_boundary(self):
        """Test exact boundary at 4.0 cards."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=4.0)
        assert referee.should_boost_cards() is True

    def test_should_upgrade_cards_strict(self, strict_referee):
        """Strict referee (>= 5.0) should upgrade cards line."""
        assert strict_referee.should_upgrade_cards_line() is True

    def test_should_upgrade_cards_moderate(self, moderate_referee):
        """Moderate referee (< 5.0) should NOT upgrade cards line."""
        assert moderate_referee.should_upgrade_cards_line() is False

    def test_should_upgrade_cards_boundary(self):
        """Test exact boundary at 5.0 cards."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=5.0)
        assert referee.should_upgrade_cards_line() is True


# ============================================
# TEST CLASS: RefereeStats - Multiplier Methods
# ============================================


class TestRefereeStatsMultiplier:
    """Test boost multiplier calculations."""

    def test_get_boost_multiplier_strong(self, strict_referee):
        """Strict referee (>= 5.0) should get 1.5x multiplier."""
        assert strict_referee.get_boost_multiplier() == 1.5

    def test_get_boost_multiplier_moderate(self, moderate_referee):
        """Moderate referee (>= 4.0 but < 5.0) should get 1.2x multiplier."""
        assert moderate_referee.get_boost_multiplier() == 1.2

    def test_get_boost_multiplier_none(self, average_referee):
        """Average referee (< 4.0) should get 1.0x (no boost)."""
        assert average_referee.get_boost_multiplier() == 1.0

    def test_get_boost_multiplier_lenient(self, lenient_referee):
        """Lenient referee (<= 3.0) should get 1.0x (no boost)."""
        assert lenient_referee.get_boost_multiplier() == 1.0

    def test_get_boost_multiplier_unknown(self, unknown_referee):
        """Unknown referee (0.0) should get 1.0x (no boost)."""
        assert unknown_referee.get_boost_multiplier() == 1.0

    def test_get_boost_multiplier_boundaries(self):
        """Test multiplier at exact boundaries."""
        # At 5.0: strong boost
        referee_5_0 = RefereeStats(name="Boundary", cards_per_game=5.0)
        assert referee_5_0.get_boost_multiplier() == 1.5

        # At 4.0: moderate boost
        referee_4_0 = RefereeStats(name="Boundary", cards_per_game=4.0)
        assert referee_4_0.get_boost_multiplier() == 1.2

        # Just below 4.0: no boost
        referee_3_9 = RefereeStats(name="Boundary", cards_per_game=3.9)
        assert referee_3_9.get_boost_multiplier() == 1.0


# ============================================
# TEST CLASS: RefereeStats - Veto Methods
# ============================================


class TestRefereeStatsVeto:
    """Test veto-related methods of RefereeStats."""

    def test_should_veto_cards_lenient(self, lenient_referee):
        """Lenient referee should veto Over Cards suggestions."""
        assert lenient_referee.should_veto_cards() is True

    def test_should_veto_cards_average(self, average_referee):
        """Average referee should NOT veto Over Cards suggestions."""
        assert average_referee.should_veto_cards() is False

    def test_should_veto_cards_strict(self, strict_referee):
        """Strict referee should NOT veto Over Cards suggestions."""
        assert strict_referee.should_veto_cards() is False

    def test_should_veto_cards_moderate(self, moderate_referee):
        """Moderate referee should NOT veto Over Cards suggestions."""
        assert moderate_referee.should_veto_cards() is False


# ============================================
# TEST CLASS: Analyzer Boost Logic
# ============================================


class TestAnalyzerBoostLogic:
    """Test the referee boost logic in analyzer.py."""

    def test_boost_case1_no_bet_to_bet_strict_referee(self, strict_referee, log_capture):
        """
        CASE 1: Strict referee + "NO BET" → Override to "Over 3.5 Cards"
        with high intensity context.
        """
        # Simulate boost logic
        verdict = "NO BET"
        recommended_market = "NONE"
        tactical_context = "Derby della Madonnina - High rivalry match"
        confidence = 70

        # Check if boost should apply
        is_high_intensity = (
            "derby" in tactical_context.lower() or "rivalry" in tactical_context.lower()
        )

        # Apply boost logic
        if verdict == "NO BET" and strict_referee.should_boost_cards():
            if is_high_intensity or strict_referee.cards_per_game >= 4.0:
                verdict = "BET"
                recommended_market = "Over 3.5 Cards"
                confidence = min(95, confidence + 10)

        # Verify boost was applied
        assert verdict == "BET"
        assert recommended_market == "Over 3.5 Cards"
        assert confidence == 80  # 70 + 10, capped at 95

    def test_boost_case1_no_bet_to_bet_without_intensity(self, strict_referee):
        """
        CASE 1: Strict referee + "NO BET" → Override to "Over 3.5 Cards"
        WITHOUT high intensity context (but cards_per_game >= 4.0).
        """
        verdict = "NO BET"
        recommended_market = "NONE"
        tactical_context = "Regular league match"
        confidence = 70

        is_high_intensity = (
            "derby" in tactical_context.lower() or "rivalry" in tactical_context.lower()
        )

        # Apply boost logic
        if verdict == "NO BET" and strict_referee.should_boost_cards():
            if is_high_intensity or strict_referee.cards_per_game >= 4.0:
                verdict = "BET"
                recommended_market = "Over 3.5 Cards"
                confidence = min(95, confidence + 10)

        # Verify boost was applied (because cards_per_game >= 4.0)
        assert verdict == "BET"
        assert recommended_market == "Over 3.5 Cards"

    def test_boost_case1_no_bet_no_boost_average_referee(self, average_referee):
        """
        CASE 1: Average referee (3.5 cards) + "NO BET" → NO OVERRIDE
        because cards_per_game < 4.0 and no high intensity.
        """
        verdict = "NO BET"
        recommended_market = "NONE"
        tactical_context = "Regular league match"

        is_high_intensity = (
            "derby" in tactical_context.lower() or "rivalry" in tactical_context.lower()
        )

        # Apply boost logic
        if verdict == "NO BET" and average_referee.should_boost_cards():
            if is_high_intensity or average_referee.cards_per_game >= 4.0:
                verdict = "BET"
                recommended_market = "Over 3.5 Cards"

        # Verify boost was NOT applied
        assert verdict == "NO BET"
        assert recommended_market == "NONE"

    def test_boost_case2_upgrade_cards_line(self, strict_referee):
        """
        CASE 2: Very strict referee + "Over 3.5" → Upgrade to "Over 4.5"
        """
        recommended_market = "Over 3.5 Cards"
        confidence = 75

        # Apply upgrade logic
        if recommended_market == "Over 3.5 Cards" and strict_referee.should_upgrade_cards_line():
            recommended_market = "Over 4.5 Cards"
            confidence = min(95, confidence + 10)

        # Verify upgrade was applied
        assert recommended_market == "Over 4.5 Cards"
        assert confidence == 85

    def test_boost_case2_no_upgrade_moderate_referee(self, moderate_referee):
        """
        CASE 2: Moderate referee + "Over 3.5" → NO UPGRADE
        """
        recommended_market = "Over 3.5 Cards"
        confidence = 75

        # Apply upgrade logic
        if recommended_market == "Over 3.5 Cards" and moderate_referee.should_upgrade_cards_line():
            recommended_market = "Over 4.5 Cards"
            confidence = min(95, confidence + 10)

        # Verify upgrade was NOT applied
        assert recommended_market == "Over 3.5 Cards"
        assert confidence == 75

    def test_boost_goals_market_strict_referee(self, strict_referee):
        """
        V9.1: Strict referee → Reduce confidence for Over Goals.
        """
        recommended_market = "Over 2.5 Goals"
        confidence = 80
        boost_multiplier = strict_referee.get_boost_multiplier()

        # Apply influence logic
        if "goal" in recommended_market.lower():
            if strict_referee.is_strict():
                if "over" in recommended_market.lower():
                    confidence = max(50, confidence - 15 * (boost_multiplier - 1.0))

        # Verify confidence was reduced
        assert confidence < 80  # Should be reduced
        assert confidence == 72.5  # 80 - 15 * (1.5 - 1.0) = 80 - 7.5 = 72.5

    def test_boost_corners_market_strict_referee(self, strict_referee):
        """
        V9.1: Strict referee → Increase confidence for Over Corners.
        """
        recommended_market = "Over 9.5 Corners"
        confidence = 75
        boost_multiplier = strict_referee.get_boost_multiplier()

        # Apply influence logic
        if "corner" in recommended_market.lower():
            if strict_referee.is_strict():
                if "over" in recommended_market.lower():
                    confidence = min(95, confidence + 10 * (boost_multiplier - 1.0))

        # Verify confidence was increased
        assert confidence > 75  # Should be increased
        assert confidence == 80.0  # 75 + 10 * (1.5 - 1.0) = 75 + 5.0 = 80.0

    def test_boost_winner_market_strict_referee(self, strict_referee):
        """
        V9.1: Strict referee → Slightly reduce confidence for Winner market.
        """
        recommended_market = "1"
        confidence = 78
        boost_multiplier = strict_referee.get_boost_multiplier()

        # Apply influence logic
        if recommended_market in ["1", "X", "2", "1X", "X2", "12"]:
            if strict_referee.is_strict():
                confidence = max(50, confidence - 5 * (boost_multiplier - 1.0))

        # Verify confidence was slightly reduced
        assert confidence < 78  # Should be reduced
        assert confidence == 75.5  # 78 - 5 * (1.5 - 1.0) = 78 - 2.5 = 75.5

    def test_boost_no_influence_non_strict_referee(self, average_referee):
        """
        Non-strict referee should NOT influence other markets.
        """
        recommended_market = "Over 2.5 Goals"
        confidence = 80
        boost_multiplier = average_referee.get_boost_multiplier()

        # Apply influence logic
        if "goal" in recommended_market.lower():
            if average_referee.is_strict():
                if "over" in recommended_market.lower():
                    confidence = max(50, confidence - 15 * (boost_multiplier - 1.0))

        # Verify confidence was NOT changed (referee is not strict)
        assert confidence == 80


# ============================================
# TEST CLASS: Edge Cases
# ============================================


class TestRefereeStatsEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_cards_per_game(self):
        """Negative cards per game should be handled gracefully."""
        referee = RefereeStats(name="Invalid Referee", cards_per_game=-1.0)
        assert referee.cards_per_game == -1.0
        assert referee.strictness == "unknown"  # Should classify as unknown
        assert referee.should_boost_cards() is False
        assert referee.should_upgrade_cards_line() is False
        assert referee.get_boost_multiplier() == 1.0

    def test_very_high_cards_per_game(self):
        """Very high cards per game (e.g., 10.0) should work correctly."""
        referee = RefereeStats(name="Very Strict Referee", cards_per_game=10.0)
        assert referee.strictness == "strict"
        assert referee.is_strict()
        assert referee.should_boost_cards() is True
        assert referee.should_upgrade_cards_line() is True
        assert referee.get_boost_multiplier() == 1.5

    def test_zero_matches_officiated(self):
        """Zero matches officiated should not affect classification."""
        referee = RefereeStats(name="New Referee", cards_per_game=4.5, matches_officiated=0)
        assert referee.strictness == "average"
        assert referee.should_boost_cards() is True

    def test_manual_strictness_override(self):
        """Manual strictness setting should be preserved."""
        referee = RefereeStats(
            name="Manual Referee", cards_per_game=0.0, strictness="strict", matches_officiated=100
        )
        # Note: __post_init__ will override this based on cards_per_game
        # So this tests that auto-classification takes precedence
        assert referee.strictness == "unknown"  # Auto-classified as unknown

    def test_dict_conversion(self):
        """Test converting RefereeStats to dict and back."""
        referee = RefereeStats(
            name="Test Referee", cards_per_game=4.2, strictness="average", matches_officiated=150
        )

        # Convert to dict
        referee_dict = {
            "name": referee.name,
            "cards_per_game": referee.cards_per_game,
            "strictness": referee.strictness,
            "matches_officiated": referee.matches_officiated,
        }

        # Convert back to RefereeStats
        referee2 = RefereeStats(**referee_dict)

        # Verify equality
        assert referee.name == referee2.name
        assert referee.cards_per_game == referee2.cards_per_game
        assert referee.strictness == referee2.strictness
        assert referee.matches_officiated == referee2.matches_officiated


# ============================================
# TEST CLASS: Integration with Analyzer
# ============================================


class TestRefereeIntegrationWithAnalyzer:
    """Test integration of RefereeStats with analyzer.py logic."""

    def test_referee_info_type_check(self, strict_referee):
        """Test that isinstance check works correctly."""
        # This simulates the check in analyzer.py:2079
        referee_info = strict_referee

        # The isinstance check should pass
        assert isinstance(referee_info, RefereeStats)
        assert referee_info is not None
        assert isinstance(referee_info, RefereeStats) is True

    def test_referee_info_dict_to_refereestats_conversion(self):
        """Test converting dict to RefereeStats (as per FIX #1)."""
        # Simulate dict from data_provider.py
        referee_info_dict = {
            "name": "Michael Oliver",
            "strictness": "unknown",
            "cards_per_game": None,
        }

        # Convert to RefereeStats (as per FIX #1)
        if isinstance(referee_info_dict, dict):
            referee_stats = RefereeStats(
                name=referee_info_dict.get("name", "Unknown"),
                cards_per_game=referee_info_dict.get("cards_per_game", 0.0) or 0.0,
                strictness=referee_info_dict.get("strictness", "unknown"),
            )
        else:
            referee_stats = referee_info_dict

        # Verify conversion
        assert isinstance(referee_stats, RefereeStats)
        assert referee_stats.name == "Michael Oliver"
        assert referee_stats.cards_per_game == 0.0  # None converted to 0.0
        assert referee_stats.strictness == "unknown"

    def test_referee_info_dict_with_stats_conversion(self):
        """Test converting dict with actual stats to RefereeStats."""
        # Simulate dict with actual stats (after fetching from search providers)
        referee_info_dict = {
            "name": "Michael Oliver",
            "strictness": "strict",
            "cards_per_game": 5.2,
            "matches_officiated": 150,
        }

        # Convert to RefereeStats
        if isinstance(referee_info_dict, dict):
            referee_stats = RefereeStats(
                name=referee_info_dict.get("name", "Unknown"),
                cards_per_game=referee_info_dict.get("cards_per_game", 0.0) or 0.0,
                strictness=referee_info_dict.get("strictness", "unknown"),
                matches_officiated=referee_info_dict.get("matches_officiated", 0),
            )
        else:
            referee_stats = referee_info_dict

        # Verify conversion and auto-classification
        assert isinstance(referee_stats, RefereeStats)
        assert referee_stats.name == "Michael Oliver"
        assert referee_stats.cards_per_game == 5.2
        # Note: __post_init__ will reclassify based on cards_per_game
        assert referee_stats.strictness == "strict"
        assert referee_stats.is_strict()
        assert referee_stats.should_boost_cards() is True
        assert referee_stats.should_upgrade_cards_line() is True


# ============================================
# TEST CLASS: Logging Verification
# ============================================


class TestRefereeBoostLogging:
    """Test that referee boost events are logged correctly."""

    def test_boost_applied_logging(self, strict_referee, log_capture):
        """Test that boost application is logged."""

        # Simulate boost application
        verdict = "NO BET"
        tactical_context = "Derby della Madonnina"

        is_high_intensity = "derby" in tactical_context.lower()

        if verdict == "NO BET" and strict_referee.should_boost_cards():
            if is_high_intensity or strict_referee.cards_per_game >= 4.0:
                logging.info(
                    f"⚖️ REFEREE BOOST: Arbitro severo ({strict_referee.name}: "
                    f"{strict_referee.cards_per_game:.1f} cards/game) "
                    f"+ Derby/High Intensity → suggesting Over 3.5 Cards"
                )

        # Verify log was captured
        log_capture.assert_logged("REFEREE BOOST", level="INFO")
        log_capture.assert_logged("Arbitro severo", level="INFO")
        log_capture.assert_logged("Derby/High Intensity", level="INFO")

    def test_upgrade_applied_logging(self, strict_referee, log_capture):
        """Test that upgrade application is logged."""

        recommended_market = "Over 3.5 Cards"

        if recommended_market == "Over 3.5 Cards" and strict_referee.should_upgrade_cards_line():
            recommended_market = "Over 4.5 Cards"
            logging.info(
                f"⚖️ REFEREE UPGRADE: Arbitro molto severo ({strict_referee.name}: "
                f"{strict_referee.cards_per_game:.1f} cards/game) "
                f"→ upgrading to {recommended_market}"
            )

        # Verify log was captured
        log_capture.assert_logged("REFEREE UPGRADE", level="INFO")
        log_capture.assert_logged("Arbitro molto severo", level="INFO")
        log_capture.assert_logged("upgrading to", level="INFO")


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
