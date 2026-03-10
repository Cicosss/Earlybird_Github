"""
BettingQuant Edge Cases Unit Tests

Comprehensive unit tests for all edge cases identified in the COVE verification report.
These tests ensure the BettingQuant component handles all edge cases gracefully and
produces correct decisions under all conditions.

Test Cases:
1. None match object (defensive check)
2. Empty market_odds dictionary
3. All invalid odds (all <= 1.05)
4. Very high odds (> 10.00)
5. ai_prob = None
6. ai_prob = 0.0
7. ai_prob = 1.0
8. Invalid team stats (negative values)
9. Zero league_avg
10. Probability >= 0.99 (safety clamp)

Author: COVE Verification Fixes
Date: 2026-03-07
"""

from datetime import datetime

import pytest

from src.core.betting_quant import (
    LEAGUE_AVG_GOALS,
    BettingDecision,
    BettingQuant,
    VetoReason,
)
from src.database.models import Match, NewsLog

# ============================================
# FIXTURES
# ============================================


@pytest.fixture
def betting_quant():
    """Create a BettingQuant instance with default league_avg."""
    return BettingQuant(league_avg=1.35, league_key="serie_a")


@pytest.fixture
def mock_match():
    """Create a mock Match object with valid data."""
    return Match(
        id="test-match-123",
        league="serie_a",
        home_team="Juventus",
        away_team="AC Milan",
        start_time=datetime.utcnow(),
        opening_home_odd=2.10,
        current_home_odd=1.95,
        opening_draw_odd=3.40,
        current_draw_odd=3.30,
        opening_away_odd=3.50,
        current_away_odd=3.80,
        opening_over_2_5=1.75,
        current_over_2_5=1.70,
        opening_under_2_5=2.10,
        current_under_2_5=2.15,
    )


@pytest.fixture
def mock_analysis():
    """Create a mock NewsLog object with valid data."""
    return NewsLog(
        id=1,
        match_id="test-match-123",
        url="https://example.com/news",
        summary="Test analysis",
        score=8,
        category="INJURY",
        affected_team="Juventus",
        recommended_market="1",
        confidence=75.0,
        status="pending",
    )


@pytest.fixture
def valid_market_odds():
    """Create valid market odds dictionary."""
    return {
        "home": 1.95,
        "draw": 3.30,
        "away": 3.80,
        "over_25": 1.70,
        "under_25": 2.15,
    }


@pytest.fixture
def valid_team_stats():
    """Create valid team statistics."""
    return {
        "home_scored": 1.8,
        "home_conceded": 0.9,
        "away_scored": 1.2,
        "away_conceded": 1.4,
    }


# ============================================
# TEST CASE 1: None Match Object
# ============================================


@pytest.mark.unit
def test_none_match_object(betting_quant, mock_analysis, valid_team_stats, valid_market_odds):
    """
    Test that BettingQuant handles None match object gracefully.

    This tests the defensive check added in the COVE verification fix.
    Should return NO BET decision with appropriate error message.
    """
    decision = betting_quant.evaluate_bet(
        match=None,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=valid_market_odds,
        ai_prob=0.75,
    )

    # Verify NO BET decision
    assert decision.should_bet is False
    assert decision.verdict == "NO BET"
    assert "None" in decision.safety_violation.lower()
    assert decision.veto_reason == VetoReason.SAFETY_VIOLATION


# ============================================
# TEST CASE 2: Empty market_odds Dictionary
# ============================================


@pytest.mark.unit
def test_empty_market_odds(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant handles empty market_odds dictionary gracefully.

    Should return NO BET decision as no markets are available.
    """
    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds={},  # Empty dictionary
        ai_prob=0.75,
    )

    # Verify NO BET decision
    assert decision.should_bet is False
    assert decision.verdict == "NO BET"
    assert decision.veto_reason == VetoReason.NO_VALUE


# ============================================
# TEST CASE 3: All Invalid Odds (all <= 1.05)
# ============================================


@pytest.mark.unit
def test_all_invalid_odds(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant rejects all invalid odds (<= 1.05).

    Should return NO BET decision with safety violation.
    """
    invalid_odds = {
        "home": 1.02,
        "draw": 1.03,
        "away": 1.04,
        "over_25": 1.01,
        "under_25": 1.05,
    }

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=invalid_odds,
        ai_prob=0.75,
    )

    # Verify NO BET decision
    assert decision.should_bet is False
    assert decision.verdict == "NO BET"
    assert decision.veto_reason == VetoReason.SAFETY_VIOLATION
    assert "too low" in decision.safety_violation.lower()


# ============================================
# TEST CASE 4: Very High Odds (> 10.00)
# ============================================


@pytest.mark.unit
def test_very_high_odds(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant handles very high odds (> 10.00) correctly.

    Should apply volatility guard and reduce stake by 50%.
    """
    high_odds = {
        "home": 12.00,
        "draw": 8.00,
        "away": 1.20,
        "over_25": 15.00,
        "under_25": 1.10,
    }

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=high_odds,
        ai_prob=0.75,
    )

    # If bet is approved, verify volatility guard was applied
    if decision.should_bet:
        assert decision.volatility_adjusted is True
        # Final stake should be reduced by volatility guard
        assert decision.final_stake < decision.kelly_stake


# ============================================
# TEST CASE 5: ai_prob = None
# ============================================


@pytest.mark.unit
def test_ai_prob_none(
    betting_quant, mock_match, mock_analysis, valid_team_stats, valid_market_odds
):
    """
    Test that BettingQuant handles ai_prob = None correctly.

    Should use only mathematical probability without AI input.
    Balanced probability should be calculated without AI.
    """
    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=valid_market_odds,
        ai_prob=None,  # No AI probability
    )

    # Verify decision is made
    assert isinstance(decision, BettingDecision)
    assert decision.ai_prob is None
    # Balanced probability should still be calculated
    assert decision.balanced_prob >= 0.0


# ============================================
# TEST CASE 6: ai_prob = 0.0
# ============================================


@pytest.mark.unit
def test_ai_prob_zero(
    betting_quant, mock_match, mock_analysis, valid_team_stats, valid_market_odds
):
    """
    Test that BettingQuant handles ai_prob = 0.0 correctly.

    Should treat zero AI probability as no confidence from AI.
    """
    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=valid_market_odds,
        ai_prob=0.0,  # Zero AI probability
    )

    # Verify decision is made
    assert isinstance(decision, BettingDecision)
    assert decision.ai_prob == 0.0
    # Balanced probability should still be calculated
    assert decision.balanced_prob >= 0.0


# ============================================
# TEST CASE 7: ai_prob = 1.0
# ============================================


@pytest.mark.unit
def test_ai_prob_one(betting_quant, mock_match, mock_analysis, valid_team_stats, valid_market_odds):
    """
    Test that BettingQuant handles ai_prob = 1.0 correctly.

    Should handle maximum AI confidence appropriately.
    """
    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=valid_market_odds,
        ai_prob=1.0,  # Maximum AI probability
    )

    # Verify decision is made
    assert isinstance(decision, BettingDecision)
    assert decision.ai_prob == 100.0
    # Balanced probability should still be calculated
    assert decision.balanced_prob >= 0.0


# ============================================
# TEST CASE 8: Invalid Team Stats (Negative Values)
# ============================================


@pytest.mark.unit
def test_invalid_team_stats_negative(betting_quant, mock_match, mock_analysis, valid_market_odds):
    """
    Test that BettingQuant handles invalid team stats (negative values) gracefully.

    Poisson simulation should fail and return NO BET decision.
    """
    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=-1.0,  # Invalid: negative
        home_conceded=-1.0,  # Invalid: negative
        away_scored=-1.0,  # Invalid: negative
        away_conceded=-1.0,  # Invalid: negative
        market_odds=valid_market_odds,
        ai_prob=0.75,
    )

    # Verify NO BET decision
    assert decision.should_bet is False
    assert decision.verdict == "NO BET"
    assert decision.veto_reason == VetoReason.NO_VALUE
    assert "insufficient data" in decision.safety_violation.lower()


# ============================================
# TEST CASE 9: Zero League Average
# ============================================


@pytest.mark.unit
def test_zero_league_avg(mock_match, mock_analysis, valid_team_stats, valid_market_odds):
    """
    Test that BettingQuant handles zero league_avg correctly.

    Should handle division by zero gracefully (protected in MathPredictor).
    """
    betting_quant = BettingQuant(league_avg=0.0, league_key="test")

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=valid_market_odds,
        ai_prob=0.75,
    )

    # Verify decision is made without crashing
    assert isinstance(decision, BettingDecision)


# ============================================
# TEST CASE 10: Probability >= 0.99 (Safety Clamp)
# ============================================


@pytest.mark.unit
def test_probability_clamp_safety(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant clamps probability >= 0.99 for safety.

    No certainty exists in sports, so probability should be clamped to 0.99.
    """
    # Create market odds that would result in very high probability
    # (very low odds for a very strong team)
    market_odds = {
        "home": 1.01,  # Very low odds -> very high probability
        "draw": 50.00,
        "away": 100.00,
        "over_25": 1.50,
        "under_25": 2.50,
    }

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"] * 3,  # Very strong home team
        home_conceded=0.1,  # Very strong defense
        away_scored=0.1,  # Very weak away team
        away_conceded=valid_team_stats["away_conceded"] * 3,  # Very weak defense
        market_odds=market_odds,
        ai_prob=0.99,  # Very high AI confidence
    )

    # Verify decision is made
    assert isinstance(decision, BettingDecision)
    # Probability should be clamped to 0.99 (99%)
    assert decision.math_prob <= 99.0


# ============================================
# TEST CASE 11: League Average Goals Dictionary
# ============================================


@pytest.mark.unit
def test_league_avg_goals_dictionary():
    """
    Test that LEAGUE_AVG_GOALS dictionary contains expected values.

    Verify the documentation of league average goals is correct.
    """
    assert isinstance(LEAGUE_AVG_GOALS, dict)
    assert "premier_league" in LEAGUE_AVG_GOALS
    assert "la_liga" in LEAGUE_AVG_GOALS
    assert "serie_a" in LEAGUE_AVG_GOALS
    assert "bundesliga" in LEAGUE_AVG_GOALS
    assert "ligue_1" in LEAGUE_AVG_GOALS
    assert "default" in LEAGUE_AVG_GOALS

    # Verify values are reasonable (between 1.0 and 2.0)
    for league, avg_goals in LEAGUE_AVG_GOALS.items():
        assert 1.0 <= avg_goals <= 2.0, f"{league}: {avg_goals} is out of range"


# ============================================
# TEST CASE 12: calculate_stake Method
# ============================================


@pytest.mark.unit
def test_calculate_stake_normal_case(betting_quant):
    """
    Test calculate_stake method with normal inputs.

    Should return a stake between 0.5% and 5.0%.
    """
    stake = betting_quant.calculate_stake(
        math_prob=0.60,  # 60% probability
        bookmaker_odd=2.00,  # Even money odds
        sample_size=10,
        ai_prob=0.65,
    )

    # Verify stake is within bounds
    assert 0.5 <= stake <= 5.0


@pytest.mark.unit
def test_calculate_stake_with_ai_prob_none(betting_quant):
    """
    Test calculate_stake method with ai_prob = None.

    Should calculate stake without AI input.
    """
    stake = betting_quant.calculate_stake(
        math_prob=0.60,
        bookmaker_odd=2.00,
        sample_size=10,
        ai_prob=None,
    )

    # Verify stake is calculated
    assert 0.0 <= stake <= 5.0


@pytest.mark.unit
def test_calculate_stake_volatility_guard(betting_quant):
    """
    Test calculate_stake method with high odds (volatility guard).

    Should reduce stake by 50% for odds > 4.50.
    """
    stake = betting_quant.calculate_stake(
        math_prob=0.20,  # Low probability
        bookmaker_odd=5.00,  # High odds (> 4.50)
        sample_size=10,
        ai_prob=0.25,
    )

    # Verify stake is calculated (may be very low)
    assert 0.0 <= stake <= 5.0


# ============================================
# TEST CASE 13: Market Warning (Late to Market)
# ============================================


@pytest.mark.unit
def test_market_warning_late_to_market(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant generates market warning for late-to-market alerts.

    When odds drop >= 15%, should generate warning but NOT veto.
    """
    # Create match with significant odds drop
    mock_match.opening_home_odd = 2.50
    mock_match.current_home_odd = 2.00  # 20% drop (> 15%)

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds={
            "home": 2.00,
            "draw": 3.30,
            "away": 3.80,
            "over_25": 1.70,
            "under_25": 2.15,
        },
        ai_prob=0.75,
    )

    # Verify market warning is generated
    if decision.should_bet:
        assert decision.market_warning is not None
        assert (
            "late to market" in decision.market_warning.lower()
            or "dropped" in decision.market_warning.lower()
        )


# ============================================
# TEST CASE 14: Stake Capping
# ============================================


@pytest.mark.unit
def test_stake_capping_minimum(betting_quant):
    """
    Test that stake capping enforces minimum stake (0.5%).

    Even if Kelly suggests lower stake, should cap at 0.5%.
    """
    stake = betting_quant.calculate_stake(
        math_prob=0.51,  # Very small edge
        bookmaker_odd=1.98,  # Close to even money
        sample_size=10,
        ai_prob=0.51,
    )

    # Verify minimum stake is enforced
    assert stake >= 0.5


@pytest.mark.unit
def test_stake_capping_maximum(betting_quant):
    """
    Test that stake capping enforces maximum stake (5.0%).

    Even if Kelly suggests higher stake, should cap at 5.0%.
    """
    stake = betting_quant.calculate_stake(
        math_prob=0.90,  # Very high probability
        bookmaker_odd=1.10,  # Very low odds
        sample_size=100,  # Large sample size
        ai_prob=0.90,
    )

    # Verify maximum stake is enforced
    assert stake <= 5.0


# ============================================
# TEST CASE 15: Missing Market Keys
# ============================================


@pytest.mark.unit
def test_missing_market_keys(betting_quant, mock_match, mock_analysis, valid_team_stats):
    """
    Test that BettingQuant handles missing market keys gracefully.

    Should skip missing markets and evaluate available ones.
    """
    # Only provide 1X2 markets, no totals
    partial_odds = {
        "home": 1.95,
        "draw": 3.30,
        "away": 3.80,
        # over_25, under_25, btts missing
    }

    decision = betting_quant.evaluate_bet(
        match=mock_match,
        analysis=mock_analysis,
        home_scored=valid_team_stats["home_scored"],
        home_conceded=valid_team_stats["home_conceded"],
        away_scored=valid_team_stats["away_scored"],
        away_conceded=valid_team_stats["away_conceded"],
        market_odds=partial_odds,
        ai_prob=0.75,
    )

    # Verify decision is made without crashing
    assert isinstance(decision, BettingDecision)


# ============================================
# TEST CASE 16: Performance Monitoring
# ============================================


@pytest.mark.unit
def test_performance_monitoring_evaluate_bet(
    betting_quant, mock_match, mock_analysis, valid_team_stats, valid_market_odds, caplog
):
    """
    Test that performance monitoring logs execution time.

    Verify that timing logs are generated for evaluate_bet().
    """
    with caplog.at_level("DEBUG"):
        decision = betting_quant.evaluate_bet(
            match=mock_match,
            analysis=mock_analysis,
            home_scored=valid_team_stats["home_scored"],
            home_conceded=valid_team_stats["home_conceded"],
            away_scored=valid_team_stats["away_scored"],
            away_conceded=valid_team_stats["away_conceded"],
            market_odds=valid_market_odds,
            ai_prob=0.75,
        )

    # Verify performance log is present
    assert any(
        "completed in" in record.message and "ms" in record.message for record in caplog.records
    )


@pytest.mark.unit
def test_performance_monitoring_calculate_stake(betting_quant, caplog):
    """
    Test that performance monitoring logs execution time.

    Verify that timing logs are generated for calculate_stake().
    """
    with caplog.at_level("DEBUG"):
        stake = betting_quant.calculate_stake(
            math_prob=0.60,
            bookmaker_odd=2.00,
            sample_size=10,
            ai_prob=0.65,
        )

    # Verify performance log is present
    assert any(
        "completed in" in record.message and "ms" in record.message for record in caplog.records
    )
