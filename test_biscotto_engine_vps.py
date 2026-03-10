#!/usr/bin/env python3
"""
Test script for biscotto_engine VPS verification.

Tests:
1. Basic functionality with valid data
2. Edge cases (None values, invalid odds)
3. Minor league detection
4. Fallback estimation for matches_remaining
5. Integration with Match object
"""

import logging
import sys
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import biscotto_engine
try:
    from src.analysis.biscotto_engine import (
        BiscottoPattern,
        BiscottoSeverity,
        _estimate_matches_remaining_from_date,
        analyze_biscotto,
        calculate_implied_probability,
        calculate_zscore,
        detect_odds_pattern,
        get_draw_threshold_for_league,
        get_enhanced_biscotto_analysis,
        is_minor_league_biscotto_risk,
    )

    BISCOTTO_ENGINE_AVAILABLE = True
    logger.info("✅ Biscotto Engine imported successfully")
except ImportError as e:
    BISCOTTO_ENGINE_AVAILABLE = False
    logger.error(f"❌ Failed to import biscotto_engine: {e}")
    sys.exit(1)


class MockMatch:
    """Mock Match object for testing."""

    def __init__(
        self, league, home_team, away_team, start_time, current_draw_odd, opening_draw_odd=None
    ):
        self.league = league
        self.home_team = home_team
        self.away_team = away_team
        self.start_time = start_time
        self.current_draw_odd = current_draw_odd
        self.opening_draw_odd = opening_draw_odd


def test_basic_functionality():
    """Test 1: Basic biscotto detection with valid data."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Basic Biscotto Detection")
    logger.info("=" * 60)

    result = analyze_biscotto(
        home_team="Juventus",
        away_team="Milan",
        current_draw_odd=2.40,
        opening_draw_odd=3.00,
        home_motivation={
            "position": 5,
            "total_teams": 20,
            "points": 45,
            "zone": "Mid-table",
            "matches_remaining": 4,
        },
        away_motivation={
            "position": 6,
            "total_teams": 20,
            "points": 43,
            "zone": "Mid-table",
            "matches_remaining": 4,
        },
        matches_remaining=4,
        league_key="soccer_italy_serie_a",
    )

    logger.info(f"  Is Suspect: {result.is_suspect}")
    logger.info(f"  Severity: {result.severity.value}")
    logger.info(f"  Confidence: {result.confidence}%")
    logger.info(f"  Reasoning: {result.reasoning}")
    logger.info(f"  Betting Recommendation: {result.betting_recommendation}")
    logger.info(f"  Factors: {result.factors}")

    assert result is not None, "Result should not be None"
    assert isinstance(result.is_suspect, bool), "is_suspect should be bool"
    assert result.severity in BiscottoSeverity, "severity should be valid enum"
    assert 0 <= result.confidence <= 100, "confidence should be 0-100"

    logger.info("✅ TEST 1 PASSED")
    return True


def test_edge_cases():
    """Test 2: Edge cases with None/invalid values."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Edge Cases (None/Invalid Values)")
    logger.info("=" * 60)

    # Test with None draw odds
    result = analyze_biscotto(
        home_team="Team A",
        away_team="Team B",
        current_draw_odd=None,
        opening_draw_odd=None,
    )

    logger.info(f"  None odds - Is Suspect: {result.is_suspect}")
    assert not result.is_suspect, "Should not be suspect with None odds"
    assert result.severity == BiscottoSeverity.NONE, "Severity should be NONE"

    # Test with invalid odds
    result = analyze_biscotto(
        home_team="Team A",
        away_team="Team B",
        current_draw_odd=0.5,  # Too low
        opening_draw_odd=1.0,
    )

    logger.info(f"  Invalid odds - Is Suspect: {result.is_suspect}")
    assert result is not None, "Should return result even with invalid odds"

    logger.info("✅ TEST 2 PASSED")
    return True


def test_minor_league_detection():
    """Test 3: Minor league biscotto risk detection."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Minor League Detection")
    logger.info("=" * 60)

    # Test Serie B (minor league)
    is_risk = is_minor_league_biscotto_risk("soccer_italy_serie_b")
    logger.info(f"  Serie B is high risk: {is_risk}")
    assert is_risk, "Serie B should be high risk"

    # Test Premier League (not minor league)
    is_risk = is_minor_league_biscotto_risk("soccer_england_premier_league")
    logger.info(f"  Premier League is high risk: {is_risk}")
    assert not is_risk, "Premier League should not be high risk"

    # Test dynamic threshold
    threshold = get_draw_threshold_for_league("soccer_italy_serie_b", end_of_season=True)
    logger.info(f"  Serie B end-of-season threshold: {threshold}")
    assert threshold == 2.60, "Serie B end-of-season threshold should be 2.60"

    threshold = get_draw_threshold_for_league("soccer_england_premier_league", end_of_season=True)
    logger.info(f"  Premier League end-of-season threshold: {threshold}")
    assert threshold == 2.50, "Premier League threshold should be 2.50"

    logger.info("✅ TEST 3 PASSED")
    return True


def test_fallback_estimation():
    """Test 4: Fallback estimation for matches_remaining."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Fallback Estimation for matches_remaining")
    logger.info("=" * 60)

    # Test European league in April (end of season)
    match_time = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
    remaining = _estimate_matches_remaining_from_date(match_time, "soccer_italy_serie_a")
    logger.info(f"  April match (Serie A): {remaining} matches remaining")
    assert remaining == 4, "April should return 4 matches remaining"

    # Test European league in December (mid-season)
    match_time = datetime(2026, 12, 15, 18, 0, tzinfo=timezone.utc)
    remaining = _estimate_matches_remaining_from_date(match_time, "soccer_italy_serie_a")
    logger.info(f"  December match (Serie A): {remaining} matches remaining")
    assert remaining == 18, "December should return 18 matches remaining"

    # Test Southern hemisphere league (A-League)
    match_time = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
    remaining = _estimate_matches_remaining_from_date(match_time, "soccer_australia_aleague")
    logger.info(f"  April match (A-League): {remaining} matches remaining")
    assert remaining == 4, "April A-League should return 4 matches remaining"

    # Test MLS
    match_time = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
    remaining = _estimate_matches_remaining_from_date(match_time, "soccer_usa_mls")
    logger.info(f"  September match (MLS): {remaining} matches remaining")
    assert remaining == 4, "September MLS should return 4 matches remaining"

    # Test None datetime
    remaining = _estimate_matches_remaining_from_date(None, "soccer_italy_serie_a")
    logger.info(f"  None datetime: {remaining} matches remaining")
    assert remaining is None, "None datetime should return None"

    logger.info("✅ TEST 4 PASSED")
    return True


def test_match_object_integration():
    """Test 5: Integration with Match object using get_enhanced_biscotto_analysis."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Match Object Integration")
    logger.info("=" * 60)

    # Create mock match
    match = MockMatch(
        league="soccer_italy_serie_b",
        home_team="Brescia",
        away_team="Palermo",
        start_time=datetime(2026, 4, 20, 15, 0, tzinfo=timezone.utc),
        current_draw_odd=2.55,
        opening_draw_odd=3.20,
    )

    # Test with motivation data
    home_motivation = {
        "position": 10,
        "total_teams": 20,
        "points": 40,
        "zone": "Mid-table",
        "matches_remaining": 4,
    }

    away_motivation = {
        "position": 11,
        "total_teams": 20,
        "points": 38,
        "zone": "Mid-table",
        "matches_remaining": 4,
    }

    analysis, context_str = get_enhanced_biscotto_analysis(
        match_obj=match,
        home_motivation=home_motivation,
        away_motivation=away_motivation,
    )

    logger.info(f"  Analysis: {analysis.severity.value}")
    logger.info(f"  Confidence: {analysis.confidence}%")
    logger.info(f"  Context String:\n{context_str}")

    assert analysis is not None, "Analysis should not be None"
    assert isinstance(context_str, str), "Context string should be string"

    # Test without motivation data (should use fallback)
    analysis2, context_str2 = get_enhanced_biscotto_analysis(
        match_obj=match,
        home_motivation=None,
        away_motivation=None,
    )

    logger.info(f"  No motivation - Severity: {analysis2.severity.value}")
    assert analysis2 is not None, "Should work without motivation data"

    logger.info("✅ TEST 5 PASSED")
    return True


def test_pattern_detection():
    """Test 6: Odds pattern detection."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Odds Pattern Detection")
    logger.info("=" * 60)

    # Test CRASH pattern (20% drop)
    pattern = detect_odds_pattern(3.50, 2.80)
    logger.info(f"  3.50 -> 2.80: {pattern.value}")
    assert pattern == BiscottoPattern.CRASH, "Should detect CRASH pattern (20% drop)"

    # Test DRIFT pattern (10% drop)
    pattern = detect_odds_pattern(3.50, 3.15)
    logger.info(f"  3.50 -> 3.15: {pattern.value}")
    assert pattern == BiscottoPattern.DRIFT, "Should detect DRIFT pattern (10% drop)"

    # Test CRASH pattern
    pattern = detect_odds_pattern(3.50, 2.50)
    logger.info(f"  3.50 -> 2.50: {pattern.value}")
    assert pattern == BiscottoPattern.CRASH, "Should detect CRASH pattern"

    # Test STABLE pattern
    pattern = detect_odds_pattern(3.00, 2.95)
    logger.info(f"  3.00 -> 2.95: {pattern.value}")
    assert pattern == BiscottoPattern.STABLE, "Should detect STABLE pattern"

    # Test REVERSE pattern
    pattern = detect_odds_pattern(2.50, 3.00)
    logger.info(f"  2.50 -> 3.00: {pattern.value}")
    assert pattern == BiscottoPattern.REVERSE, "Should detect REVERSE pattern"

    # Test None values
    pattern = detect_odds_pattern(None, None)
    logger.info(f"  None -> None: {pattern.value}")
    assert pattern == BiscottoPattern.STABLE, "None values should return STABLE"

    logger.info("✅ TEST 6 PASSED")
    return True


def test_zscore_calculation():
    """Test 7: Z-Score calculation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Z-Score Calculation")
    logger.info("=" * 60)

    # Test normal draw probability
    implied_prob = calculate_implied_probability(3.00)  # ~33%
    zscore = calculate_zscore(implied_prob)
    logger.info(f"  Odds 3.00: Implied prob={implied_prob:.2f}, Z-Score={zscore:.2f}")

    # Test low draw probability (high odds)
    implied_prob = calculate_implied_probability(4.00)  # 25%
    zscore = calculate_zscore(implied_prob)
    logger.info(f"  Odds 4.00: Implied prob={implied_prob:.2f}, Z-Score={zscore:.2f}")

    # Test very low draw probability (very high odds)
    implied_prob = calculate_implied_probability(5.00)  # 20%
    zscore = calculate_zscore(implied_prob)
    logger.info(f"  Odds 5.00: Implied prob={implied_prob:.2f}, Z-Score={zscore:.2f}")
    assert zscore < 0, "High odds should have negative Z-Score"

    # Test high draw probability (low odds)
    implied_prob = calculate_implied_probability(2.00)  # 50%
    zscore = calculate_zscore(implied_prob)
    logger.info(f"  Odds 2.00: Implied prob={implied_prob:.2f}, Z-Score={zscore:.2f}")
    assert zscore > 2.0, "Low odds should have high positive Z-Score"

    logger.info("✅ TEST 7 PASSED")
    return True


def run_all_tests():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("BISCOTTO ENGINE VPS VERIFICATION TESTS")
    logger.info("=" * 60)

    tests = [
        test_basic_functionality,
        test_edge_cases,
        test_minor_league_detection,
        test_fallback_estimation,
        test_match_object_integration,
        test_pattern_detection,
        test_zscore_calculation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            logger.error(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"❌ {test.__name__} ERROR: {e}")
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"TEST RESULTS: {passed} passed, {failed} failed")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
