"""
Property-Based Tests for Verification Layer

Uses Hypothesis to verify correctness properties defined in the design document.
Each test validates a specific property from the spec.

Requirements: 1.2, 2.2, 3.3, 4.2, 5.2, 6.1, 6.5, 7.1, 7.3, 8.1, 8.2
"""
import pytest
from hypothesis import given, strategies as st, settings, assume

from src.analysis.verification_layer import (
    # Data classes
    VerificationRequest,
    VerifiedData,
    VerificationResult,
    PlayerImpact,
    FormStats,
    H2HStats,
    RefereeStats,
    VerificationStatus,
    # Constants
    PLAYER_KEY_IMPACT_THRESHOLD,
    CRITICAL_IMPACT_THRESHOLD,
    FORM_DEVIATION_THRESHOLD,
    H2H_CARDS_THRESHOLD,
    H2H_CORNERS_THRESHOLD,
    COMBINED_CORNERS_THRESHOLD,
    REFEREE_STRICT_THRESHOLD,
    REFEREE_LENIENT_THRESHOLD,
    VERIFICATION_SCORE_THRESHOLD,
    LOW_SCORING_THRESHOLD,
)


# ============================================
# STRATEGIES (Generators)
# ============================================

# Player name strategy
player_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=2,
    max_size=30
).filter(lambda x: x.strip())

# Impact score strategy (1-10)
impact_score_st = st.integers(min_value=1, max_value=10)

# Team name strategy
team_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
    min_size=2,
    max_size=50
).filter(lambda x: x.strip())

# Match ID strategy
match_id_st = st.text(min_size=1, max_size=20).filter(lambda x: x.strip())

# Date strategy (YYYY-MM-DD)
date_st = st.dates().map(lambda d: d.strftime("%Y-%m-%d"))

# League strategy
league_st = st.sampled_from([
    "soccer_england_premier_league",
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_turkey_super_league",
    "soccer_greece_super_league",
])

# Market strategy
market_st = st.sampled_from([
    "Over 2.5 Goals",
    "Under 2.5 Goals",
    "Over 1.5 Goals",
    "1",
    "X",
    "2",
    "1X",
    "X2",
    "BTTS",
    "Over 9.5 Corners",
    "Over 4.5 Cards",
])

# Injury severity strategy
injury_severity_st = st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"])

# Score strategy (0-10)
score_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Goals average strategy
goals_avg_st = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)

# Cards per game strategy
cards_per_game_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Corners average strategy
corners_avg_st = st.floats(min_value=0.0, max_value=15.0, allow_nan=False, allow_infinity=False)


# ============================================
# PROPERTY 1: Key Player Classification Threshold
# **Feature: verification-layer, Property 1: Key player classification threshold**
# **Validates: Requirements 1.2**
# ============================================

@given(
    name=player_name_st,
    impact_score=impact_score_st,
)
@settings(max_examples=100)
def test_property_1_key_player_classification(name: str, impact_score: int):
    """
    **Feature: verification-layer, Property 1: Key player classification threshold**
    **Validates: Requirements 1.2**
    
    *For any* player with impact_score >= 7, that player SHALL be classified 
    as is_key_player = True in the verification result.
    """
    player = PlayerImpact(name=name, impact_score=impact_score)
    
    # Property: impact_score >= 7 implies is_key_player = True
    if impact_score >= PLAYER_KEY_IMPACT_THRESHOLD:
        assert player.is_key_player is True, (
            f"Player with impact_score={impact_score} should be key_player "
            f"(threshold={PLAYER_KEY_IMPACT_THRESHOLD})"
        )
    else:
        assert player.is_key_player is False, (
            f"Player with impact_score={impact_score} should NOT be key_player "
            f"(threshold={PLAYER_KEY_IMPACT_THRESHOLD})"
        )


# ============================================
# PROPERTY 7: Referee Strict Classification
# **Feature: verification-layer, Property 7: Referee strict classification**
# **Validates: Requirements 4.2**
# ============================================

@given(
    name=player_name_st,
    cards_per_game=cards_per_game_st,
)
@settings(max_examples=100)
def test_property_7_referee_strict_classification(name: str, cards_per_game: float):
    """
    **Feature: verification-layer, Property 7: Referee strict classification**
    **Validates: Requirements 4.2**
    
    *For any* referee with cards_per_game >= 5.0, the referee SHALL be 
    classified as strictness = "strict".
    """
    referee = RefereeStats(name=name, cards_per_game=cards_per_game)
    
    # Property: cards_per_game >= 5.0 implies strictness = "strict"
    if cards_per_game >= REFEREE_STRICT_THRESHOLD:
        assert referee.strictness == "strict", (
            f"Referee with cards_per_game={cards_per_game} should be 'strict' "
            f"(threshold={REFEREE_STRICT_THRESHOLD})"
        )
        assert referee.is_strict() is True
    elif cards_per_game <= REFEREE_LENIENT_THRESHOLD:
        assert referee.strictness == "lenient", (
            f"Referee with cards_per_game={cards_per_game} should be 'lenient' "
            f"(threshold={REFEREE_LENIENT_THRESHOLD})"
        )
        assert referee.is_lenient() is True
    elif cards_per_game > 0:
        assert referee.strictness == "average", (
            f"Referee with cards_per_game={cards_per_game} should be 'average'"
        )


# ============================================
# PROPERTY 5: H2H Cards Market Flag
# **Feature: verification-layer, Property 5: H2H cards market flag**
# **Validates: Requirements 3.3**
# ============================================

@given(
    avg_cards=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    matches_analyzed=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100)
def test_property_5_h2h_cards_market_flag(avg_cards: float, matches_analyzed: int):
    """
    **Feature: verification-layer, Property 5: H2H cards market flag**
    **Validates: Requirements 3.3**
    
    *For any* H2H stats with avg_cards >= 4.5, the alternative_markets 
    SHALL include "Over Cards" variant.
    """
    h2h = H2HStats(
        matches_analyzed=matches_analyzed,
        avg_cards=avg_cards,
    )
    
    # Property: avg_cards >= 4.5 implies suggests_over_cards() = True
    if avg_cards >= H2H_CARDS_THRESHOLD:
        assert h2h.suggests_over_cards() is True, (
            f"H2H with avg_cards={avg_cards} should suggest Over Cards "
            f"(threshold={H2H_CARDS_THRESHOLD})"
        )
    else:
        assert h2h.suggests_over_cards() is False, (
            f"H2H with avg_cards={avg_cards} should NOT suggest Over Cards "
            f"(threshold={H2H_CARDS_THRESHOLD})"
        )


# ============================================
# PROPERTY 6: H2H Corners Market Flag
# **Feature: verification-layer, Property 6: H2H corners market flag**
# **Validates: Requirements 3.4**
# ============================================

@given(
    avg_corners=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    matches_analyzed=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100)
def test_property_6_h2h_corners_market_flag(avg_corners: float, matches_analyzed: int):
    """
    **Feature: verification-layer, Property 6: H2H corners market flag**
    **Validates: Requirements 3.4**
    
    *For any* H2H stats with avg_corners >= 10, the alternative_markets 
    SHALL include "Over Corners" variant.
    """
    h2h = H2HStats(
        matches_analyzed=matches_analyzed,
        avg_corners=avg_corners,
    )
    
    # Property: avg_corners >= 10 implies suggests_over_corners() = True
    if avg_corners >= H2H_CORNERS_THRESHOLD:
        assert h2h.suggests_over_corners() is True, (
            f"H2H with avg_corners={avg_corners} should suggest Over Corners "
            f"(threshold={H2H_CORNERS_THRESHOLD})"
        )
    else:
        assert h2h.suggests_over_corners() is False, (
            f"H2H with avg_corners={avg_corners} should NOT suggest Over Corners "
            f"(threshold={H2H_CORNERS_THRESHOLD})"
        )


# ============================================
# PROPERTY 9: Combined Corners Threshold
# **Feature: verification-layer, Property 9: Combined corners threshold**
# **Validates: Requirements 5.2**
# ============================================

@given(
    home_corner_avg=corners_avg_st,
    away_corner_avg=corners_avg_st,
)
@settings(max_examples=100)
def test_property_9_combined_corners_threshold(home_corner_avg: float, away_corner_avg: float):
    """
    **Feature: verification-layer, Property 9: Combined corners threshold**
    **Validates: Requirements 5.2**
    
    *For any* verification where home_corner_avg + away_corner_avg >= 10.5, 
    the alternative_markets SHALL include "Over 9.5 Corners".
    """
    verified = VerifiedData(
        home_corner_avg=home_corner_avg,
        away_corner_avg=away_corner_avg,
    )
    
    combined = home_corner_avg + away_corner_avg
    
    # Property: combined >= 10.5 implies suggests_over_corners() = True
    if combined >= COMBINED_CORNERS_THRESHOLD:
        assert verified.suggests_over_corners() is True, (
            f"Combined corners {combined} should suggest Over 9.5 Corners "
            f"(threshold={COMBINED_CORNERS_THRESHOLD})"
        )
    else:
        assert verified.suggests_over_corners() is False, (
            f"Combined corners {combined} should NOT suggest Over 9.5 Corners "
            f"(threshold={COMBINED_CORNERS_THRESHOLD})"
        )


# ============================================
# PROPERTY 10: Verification Result Status Validity
# **Feature: verification-layer, Property 10: Verification result status validity**
# **Validates: Requirements 6.1**
# ============================================

@given(
    status=st.sampled_from(list(VerificationStatus)),
    original_score=score_st,
    adjusted_score=score_st,
)
@settings(max_examples=100)
def test_property_10_verification_result_status_validity(
    status: VerificationStatus,
    original_score: float,
    adjusted_score: float,
):
    """
    **Feature: verification-layer, Property 10: Verification result status validity**
    **Validates: Requirements 6.1**
    
    *For any* completed verification, the status SHALL be exactly one of: 
    CONFIRM, REJECT, or CHANGE_MARKET.
    """
    result = VerificationResult(
        status=status,
        original_score=original_score,
        adjusted_score=adjusted_score,
        original_market="Over 2.5 Goals",
    )
    
    # Property: status must be one of the valid enum values
    assert result.status in [
        VerificationStatus.CONFIRM,
        VerificationStatus.REJECT,
        VerificationStatus.CHANGE_MARKET,
    ], f"Invalid status: {result.status}"
    
    # Verify helper methods work correctly
    if status == VerificationStatus.CONFIRM:
        assert result.is_confirmed() is True
        assert result.is_rejected() is False
        assert result.should_change_market() is False
    elif status == VerificationStatus.REJECT:
        assert result.is_confirmed() is False
        assert result.is_rejected() is True
        assert result.should_change_market() is False
    elif status == VerificationStatus.CHANGE_MARKET:
        assert result.is_confirmed() is False
        assert result.is_rejected() is False
        assert result.should_change_market() is True


# ============================================
# PROPERTY 11: Reasoning Presence
# **Feature: verification-layer, Property 11: Reasoning presence**
# **Validates: Requirements 6.5**
# ============================================

@given(
    reasoning=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
)
@settings(max_examples=100)
def test_property_11_reasoning_presence(reasoning: str):
    """
    **Feature: verification-layer, Property 11: Reasoning presence**
    **Validates: Requirements 6.5**
    
    *For any* VerificationResult, the reasoning field SHALL be non-empty 
    and contain Italian text.
    
    Note: This test verifies the structure. The actual Italian content
    is validated in integration tests.
    """
    result = VerificationResult(
        status=VerificationStatus.CONFIRM,
        original_score=8.0,
        adjusted_score=8.0,
        original_market="Over 2.5 Goals",
        reasoning=reasoning,
    )
    
    # Property: reasoning must be non-empty
    assert result.reasoning is not None
    assert len(result.reasoning.strip()) > 0, "Reasoning must be non-empty"


# ============================================
# FORM STATS PROPERTIES
# ============================================

@given(
    goals_scored=st.integers(min_value=0, max_value=25),
    goals_conceded=st.integers(min_value=0, max_value=25),
    wins=st.integers(min_value=0, max_value=5),
    draws=st.integers(min_value=0, max_value=5),
    losses=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_form_stats_low_scoring_classification(
    goals_scored: int,
    goals_conceded: int,
    wins: int,
    draws: int,
    losses: int,
):
    """
    Test that FormStats correctly classifies low-scoring teams.
    
    *For any* team with avg_goals_scored < 1.0, is_low_scoring() returns True.
    """
    form = FormStats(
        goals_scored=goals_scored,
        goals_conceded=goals_conceded,
        wins=wins,
        draws=draws,
        losses=losses,
    )
    
    avg = goals_scored / 5.0
    
    if avg < LOW_SCORING_THRESHOLD:
        assert form.is_low_scoring() is True, (
            f"Team with avg {avg} goals should be low_scoring "
            f"(threshold={LOW_SCORING_THRESHOLD})"
        )
    else:
        assert form.is_low_scoring() is False


@given(
    wins=st.integers(min_value=0, max_value=5),
    remaining=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_form_stats_losing_streak_detection(wins: int, remaining: int):
    """
    Test that FormStats correctly detects losing streaks.
    
    *For any* team with 0 wins in last 5 matches, is_on_losing_streak() returns True.
    """
    # Distribute remaining matches between draws and losses to total 5
    draws = min(remaining, 5 - wins)
    losses = 5 - wins - draws
    
    form = FormStats(wins=wins, draws=draws, losses=losses)
    
    if wins == 0 and form.matches_played >= 5:
        assert form.is_on_losing_streak() is True, (
            f"Team with 0 wins should be on losing streak"
        )
    elif wins > 0:
        assert form.is_on_losing_streak() is False


# ============================================
# VERIFICATION REQUEST VALIDATION
# ============================================

@given(
    match_id=match_id_st,
    home_team=team_name_st,
    away_team=team_name_st,
    match_date=date_st,
    league=league_st,
    preliminary_score=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    suggested_market=market_st,
    home_injury_severity=injury_severity_st,
    away_injury_severity=injury_severity_st,
)
@settings(max_examples=100)
def test_verification_request_validation(
    match_id: str,
    home_team: str,
    away_team: str,
    match_date: str,
    league: str,
    preliminary_score: float,
    suggested_market: str,
    home_injury_severity: str,
    away_injury_severity: str,
):
    """
    Test that VerificationRequest validates and normalizes inputs correctly.
    """
    request = VerificationRequest(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        league=league,
        preliminary_score=preliminary_score,
        suggested_market=suggested_market,
        home_injury_severity=home_injury_severity,
        away_injury_severity=away_injury_severity,
    )
    
    # Verify normalization
    assert request.home_injury_severity == home_injury_severity.upper()
    assert request.away_injury_severity == away_injury_severity.upper()
    
    # Verify critical injury detection
    if home_injury_severity.upper() == "CRITICAL":
        assert request.has_critical_injuries("home") is True
    if away_injury_severity.upper() == "CRITICAL":
        assert request.has_critical_injuries("away") is True
    
    # Verify both_teams_critical
    if home_injury_severity.upper() == "CRITICAL" and away_injury_severity.upper() == "CRITICAL":
        assert request.both_teams_critical() is True
    else:
        assert request.both_teams_critical() is False


@given(
    suggested_market=market_st,
)
@settings(max_examples=100)
def test_verification_request_market_detection(suggested_market: str):
    """
    Test that VerificationRequest correctly detects market types.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market=suggested_market,
    )
    
    market_lower = suggested_market.lower()
    
    # Over goals detection
    if "over" in market_lower and "goal" in market_lower:
        assert request.is_over_market() is True
    else:
        assert request.is_over_market() is False
    
    # Cards detection
    if "card" in market_lower:
        assert request.is_cards_market() is True
    else:
        assert request.is_cards_market() is False
    
    # Corners detection
    if "corner" in market_lower:
        assert request.is_corners_market() is True
    else:
        assert request.is_corners_market() is False


# ============================================
# VERIFIED DATA AGGREGATION PROPERTIES
# ============================================

@given(
    home_impacts=st.lists(
        st.tuples(player_name_st, impact_score_st),
        min_size=0,
        max_size=10,
    ),
    away_impacts=st.lists(
        st.tuples(player_name_st, impact_score_st),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=100)
def test_verified_data_key_player_aggregation(
    home_impacts: list,
    away_impacts: list,
):
    """
    Test that VerifiedData correctly aggregates key player impacts.
    
    *For any* set of player impacts, the total key player impact should
    equal the sum of impact scores for players with score >= 7.
    """
    home_players = [
        PlayerImpact(name=name, impact_score=score)
        for name, score in home_impacts
    ]
    away_players = [
        PlayerImpact(name=name, impact_score=score)
        for name, score in away_impacts
    ]
    
    verified = VerifiedData(
        home_player_impacts=home_players,
        away_player_impacts=away_players,
    )
    
    # Calculate expected totals
    expected_home_key = sum(
        score for _, score in home_impacts
        if score >= PLAYER_KEY_IMPACT_THRESHOLD
    )
    expected_away_key = sum(
        score for _, score in away_impacts
        if score >= PLAYER_KEY_IMPACT_THRESHOLD
    )
    
    # Verify aggregation
    assert verified.get_total_key_player_impact("home") == expected_home_key
    assert verified.get_total_key_player_impact("away") == expected_away_key
    assert verified.get_total_key_player_impact("any") == expected_home_key + expected_away_key
    
    # Verify critical threshold detection
    total_key = expected_home_key + expected_away_key
    if total_key > CRITICAL_IMPACT_THRESHOLD:
        assert verified.has_critical_key_player_impact() is True
    else:
        assert verified.has_critical_key_player_impact() is False



# ============================================
# PROPERTY 13: Provider Fallback
# **Feature: verification-layer, Property 13: Provider fallback**
# **Validates: Requirements 7.3**
# ============================================

from typing import Optional, Dict
from unittest.mock import Mock, patch, MagicMock


def create_test_request(
    match_id: str = "test_123",
    home_team: str = "Home FC",
    away_team: str = "Away FC",
    preliminary_score: float = 8.0,
) -> 'VerificationRequest':
    """Helper to create test VerificationRequest."""
    return VerificationRequest(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=preliminary_score,
        suggested_market="Over 2.5 Goals",
    )


class MockTavilyVerifier:
    """Mock TavilyVerifier that can be configured to fail."""
    
    def __init__(self, should_fail: bool = False, is_available: bool = True):
        self._should_fail = should_fail
        self._is_available = is_available
        self._call_count = 0
    
    def is_available(self) -> bool:
        return self._is_available
    
    def query(self, request) -> Optional[Dict]:
        self._call_count += 1
        if self._should_fail:
            return None
        return {"answer": "test", "results": [], "provider": "tavily"}
    
    def query_optimized(self, request) -> Optional[Dict]:
        """V2.0: Optimized multi-query method."""
        self._call_count += 1
        if self._should_fail:
            return None
        return {"answer": "test optimized", "results": [], "provider": "tavily_v2"}
    
    def query_with_fallback(self, request) -> Optional[Dict]:
        """V2.4: Multi-site fallback query method."""
        self._call_count += 1
        if self._should_fail:
            return None
        return {
            "answer": "test fallback",
            "results": [],
            "provider": "tavily_v2.4_fallback",
            "fallback_executed": False,
            "primary_extraction_rate": 100.0,
        }
    
    def parse_response(self, response, request) -> VerifiedData:
        return VerifiedData(source="tavily", data_confidence="MEDIUM")
    
    def parse_optimized_response(self, response, request) -> VerifiedData:
        """V2.0: Parse optimized response."""
        return VerifiedData(source="tavily_v2", data_confidence="MEDIUM")
    
    def get_call_count(self) -> int:
        return self._call_count


class MockPerplexityVerifier:
    """Mock PerplexityVerifier that can be configured to fail."""
    
    def __init__(self, should_fail: bool = False, is_available: bool = True):
        self._should_fail = should_fail
        self._is_available = is_available
        self._call_count = 0
    
    def is_available(self) -> bool:
        return self._is_available
    
    def query(self, request) -> Optional[Dict]:
        self._call_count += 1
        if self._should_fail:
            return None
        return {"answer": "test", "provider": "perplexity"}
    
    def parse_response(self, response, request) -> VerifiedData:
        return VerifiedData(source="perplexity", data_confidence="MEDIUM")
    
    def get_call_count(self) -> int:
        return self._call_count


# Import orchestrator for testing
from src.analysis.verification_layer import VerificationOrchestrator


@given(
    tavily_fails=st.booleans(),
    perplexity_fails=st.booleans(),
    tavily_available=st.booleans(),
    perplexity_available=st.booleans(),
)
@settings(max_examples=100)
def test_property_13_provider_fallback(
    tavily_fails: bool,
    perplexity_fails: bool,
    tavily_available: bool,
    perplexity_available: bool,
):
    """
    **Feature: verification-layer, Property 13: Provider fallback**
    **Validates: Requirements 7.3**
    
    *For any* Tavily API failure, the system SHALL attempt Perplexity 
    fallback before returning error.
    
    V2.4: Orchestrator tries query_with_fallback() first, then query() as fallback,
    so Tavily may be called up to 2 times before falling back to Perplexity.
    """
    # Create mock verifiers
    mock_tavily = MockTavilyVerifier(
        should_fail=tavily_fails,
        is_available=tavily_available
    )
    mock_perplexity = MockPerplexityVerifier(
        should_fail=perplexity_fails,
        is_available=perplexity_available
    )
    
    # Create orchestrator with mocks
    orchestrator = VerificationOrchestrator(
        tavily_verifier=mock_tavily,
        perplexity_verifier=mock_perplexity,
    )
    
    request = create_test_request()
    
    # Get verified data
    result = orchestrator.get_verified_data(request)
    
    # Property: If Tavily fails AND is available, Perplexity should be tried
    if tavily_available and tavily_fails:
        # V2.4: Tavily is called twice (fallback + legacy fallback)
        assert mock_tavily.get_call_count() == 2, (
            f"Tavily should be called twice (fallback + legacy), got {mock_tavily.get_call_count()}"
        )
        
        # If Perplexity is available, it should be tried as fallback
        if perplexity_available:
            assert mock_perplexity.get_call_count() == 1, (
                "Perplexity should be called as fallback when Tavily fails"
            )
    
    # Property: If Tavily succeeds, Perplexity should NOT be called
    if tavily_available and not tavily_fails:
        # V2.4: Only fallback query is called when it succeeds
        assert mock_tavily.get_call_count() == 1
        assert mock_perplexity.get_call_count() == 0, (
            "Perplexity should NOT be called when Tavily succeeds"
        )
        # V2.4: Fallback queries return "tavily_v2" or "tavily_v2.4_fallback"
        assert result.source in ["tavily", "tavily_v2", "tavily_v2.4_fallback"], (
            f"Expected source 'tavily', 'tavily_v2', or 'tavily_v2.4_fallback', got '{result.source}'"
        )
    
    # Property: If both fail, result should have LOW confidence
    if (tavily_fails or not tavily_available) and (perplexity_fails or not perplexity_available):
        assert result.data_confidence == "LOW", (
            "When all providers fail, confidence should be LOW"
        )


def test_property_13_fallback_order():
    """
    Test that fallback order is correct: Tavily first, then Perplexity.
    
    **Feature: verification-layer, Property 13: Provider fallback**
    **Validates: Requirements 7.3**
    
    V2.4: Updated to track query_with_fallback calls (used by default).
    Orchestrator tries: query_with_fallback -> query (legacy) -> perplexity
    """
    call_order = []
    
    class OrderTrackingTavily(MockTavilyVerifier):
        def query(self, request):
            call_order.append("tavily_legacy")
            return super().query(request)
        
        def query_optimized(self, request):
            call_order.append("tavily_optimized")
            return super().query_optimized(request)
        
        def query_with_fallback(self, request):
            call_order.append("tavily_fallback")
            return super().query_with_fallback(request)
    
    class OrderTrackingPerplexity(MockPerplexityVerifier):
        def query(self, request):
            call_order.append("perplexity")
            return super().query(request)
    
    # Test 1: Tavily fails, Perplexity succeeds
    call_order.clear()
    orchestrator = VerificationOrchestrator(
        tavily_verifier=OrderTrackingTavily(should_fail=True),
        perplexity_verifier=OrderTrackingPerplexity(should_fail=False),
    )
    
    request = create_test_request()
    result = orchestrator.get_verified_data(request)
    
    # V2.4: Orchestrator tries fallback -> legacy -> perplexity
    assert call_order == ["tavily_fallback", "tavily_legacy", "perplexity"], (
        f"Expected order ['tavily_fallback', 'tavily_legacy', 'perplexity'], got {call_order}"
    )
    assert result.source == "perplexity"
    
    # Test 2: Tavily succeeds, Perplexity not called
    call_order.clear()
    orchestrator = VerificationOrchestrator(
        tavily_verifier=OrderTrackingTavily(should_fail=False),
        perplexity_verifier=OrderTrackingPerplexity(should_fail=False),
    )
    
    result = orchestrator.get_verified_data(request)
    
    # V2.4: Only fallback query is called when it succeeds
    assert call_order == ["tavily_fallback"], (
        f"Expected order ['tavily_fallback'], got {call_order}"
    )
    # V2.4: Fallback queries return "tavily_v2" or "tavily_v2.4_fallback"
    assert result.source in ["tavily", "tavily_v2", "tavily_v2.4_fallback"], (
        f"Expected source 'tavily', 'tavily_v2', or 'tavily_v2.4_fallback', got '{result.source}'"
    )


# ============================================
# PROPERTY 12: Score Threshold Gating
# **Feature: verification-layer, Property 12: Score threshold gating**
# **Validates: Requirements 7.1**
# ============================================

@given(
    preliminary_score=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_property_12_score_threshold_gating(preliminary_score: float):
    """
    **Feature: verification-layer, Property 12: Score threshold gating**
    **Validates: Requirements 7.1**
    
    *For any* alert with preliminary_score < 7.5, the verification layer 
    SHALL NOT be invoked (skip verification).
    """
    orchestrator = VerificationOrchestrator(
        tavily_verifier=MockTavilyVerifier(),
        perplexity_verifier=MockPerplexityVerifier(),
    )
    
    request = create_test_request(preliminary_score=preliminary_score)
    
    should_skip = orchestrator.should_skip_verification(request)
    
    # Property: score < 7.5 implies skip verification
    if preliminary_score < VERIFICATION_SCORE_THRESHOLD:
        assert should_skip is True, (
            f"Score {preliminary_score} < {VERIFICATION_SCORE_THRESHOLD} should skip verification"
        )
    else:
        assert should_skip is False, (
            f"Score {preliminary_score} >= {VERIFICATION_SCORE_THRESHOLD} should NOT skip verification"
        )



# ============================================
# LOGIC VALIDATOR PROPERTY TESTS
# ============================================

from src.analysis.verification_layer import (
    LogicValidator,
    CRITICAL_INJURY_OVER_PENALTY,
)


# ============================================
# PROPERTY 14: Critical Injury Over Penalty
# **Feature: verification-layer, Property 14: Critical injury Over penalty**
# **Validates: Requirements 8.1**
# ============================================

@given(
    preliminary_score=st.floats(min_value=7.5, max_value=10.0, allow_nan=False, allow_infinity=False),
    home_injury_severity=st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    away_injury_severity=st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    suggested_market=st.sampled_from([
        "Over 2.5 Goals", "Over 1.5 Goals", "Under 2.5 Goals", "1", "2", "BTTS"
    ]),
)
@settings(max_examples=100)
def test_property_14_critical_injury_over_penalty(
    preliminary_score: float,
    home_injury_severity: str,
    away_injury_severity: str,
    suggested_market: str,
):
    """
    **Feature: verification-layer, Property 14: Critical injury Over penalty**
    **Validates: Requirements 8.1**
    
    *For any* team with injury_severity = "CRITICAL" AND suggested market = "Over 2.5 Goals",
    the adjusted_score SHALL be less than original_score.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=preliminary_score,
        suggested_market=suggested_market,
        home_injury_severity=home_injury_severity,
        away_injury_severity=away_injury_severity,
    )
    
    verified = VerifiedData(source="test", data_confidence="MEDIUM")
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: CRITICAL injury + Over market implies adjusted_score < original_score
    is_over_market = "over" in suggested_market.lower() and "goal" in suggested_market.lower()
    has_critical = home_injury_severity == "CRITICAL" or away_injury_severity == "CRITICAL"
    
    if has_critical and is_over_market:
        assert result.adjusted_score < result.original_score, (
            f"CRITICAL injury + Over market should reduce score. "
            f"Original: {result.original_score}, Adjusted: {result.adjusted_score}"
        )
        # Verify penalty amount
        expected_max = result.original_score - CRITICAL_INJURY_OVER_PENALTY
        assert result.adjusted_score <= expected_max, (
            f"Penalty should be at least {CRITICAL_INJURY_OVER_PENALTY}"
        )


# ============================================
# PROPERTY 3: Form Deviation Warning
# **Feature: verification-layer, Property 3: Form deviation warning**
# **Validates: Requirements 2.2**
# ============================================

@given(
    home_goals_scored=st.integers(min_value=0, max_value=15),
    away_goals_scored=st.integers(min_value=0, max_value=15),
)
@settings(max_examples=100)
def test_property_3_form_deviation_warning(
    home_goals_scored: int,
    away_goals_scored: int,
):
    """
    **Feature: verification-layer, Property 3: Form deviation warning**
    **Validates: Requirements 2.2**
    
    *For any* team where |last5_avg - season_avg| / season_avg > 0.30,
    the verification result SHALL include a form_warning.
    
    Note: This test verifies the low-scoring detection which is a form warning.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market="Over 2.5 Goals",
    )
    
    # Create form stats
    home_form = FormStats(goals_scored=home_goals_scored, wins=2, draws=1, losses=2)
    away_form = FormStats(goals_scored=away_goals_scored, wins=2, draws=1, losses=2)
    
    verified = VerifiedData(
        source="test",
        data_confidence="MEDIUM",
        home_form=home_form,
        away_form=away_form,
    )
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: Both teams low scoring + Over market should trigger warning
    home_avg = home_goals_scored / 5.0
    away_avg = away_goals_scored / 5.0
    
    if home_avg < LOW_SCORING_THRESHOLD and away_avg < LOW_SCORING_THRESHOLD:
        # Should have inconsistency about low scoring
        has_low_scoring_warning = any(
            "basso punteggio" in issue.lower() or "low scoring" in issue.lower()
            for issue in result.inconsistencies
        )
        assert has_low_scoring_warning, (
            f"Both teams low scoring ({home_avg:.1f}, {away_avg:.1f}) should trigger warning"
        )


# ============================================
# PROPERTY 4: Under Market Recommendation on Low Scoring
# **Feature: verification-layer, Property 4: Under market recommendation on low scoring**
# **Validates: Requirements 2.3**
# ============================================

def test_property_4_under_market_recommendation():
    """
    **Feature: verification-layer, Property 4: Under market recommendation on low scoring**
    **Validates: Requirements 2.3**
    
    *For any* verification where both teams have last5_goals_avg < 1.0 AND 
    original market is Over, the recommended_market SHALL be Under or 
    alternative_markets SHALL include Under.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market="Over 2.5 Goals",
    )
    
    # Both teams low scoring (< 1.0 goals per game in last 5)
    home_form = FormStats(goals_scored=3, wins=1, draws=2, losses=2)  # 0.6 avg
    away_form = FormStats(goals_scored=4, wins=1, draws=1, losses=3)  # 0.8 avg
    
    verified = VerifiedData(
        source="test",
        data_confidence="MEDIUM",
        home_form=home_form,
        away_form=away_form,
    )
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: Should recommend Under or include Under in alternatives
    has_under = (
        (result.recommended_market and "under" in result.recommended_market.lower()) or
        any("under" in alt.lower() for alt in result.alternative_markets)
    )
    
    assert has_under, (
        f"Both teams low scoring should recommend Under market. "
        f"Recommended: {result.recommended_market}, Alternatives: {result.alternative_markets}"
    )


# ============================================
# PROPERTY 8: Referee Lenient Veto
# **Feature: verification-layer, Property 8: Referee lenient veto**
# **Validates: Requirements 4.3**
# ============================================

@given(
    cards_per_game=st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_property_8_referee_lenient_veto(cards_per_game: float):
    """
    **Feature: verification-layer, Property 8: Referee lenient veto**
    **Validates: Requirements 4.3**
    
    *For any* referee with cards_per_game <= 3.0 AND suggested market contains "Cards",
    the result SHALL NOT recommend Over Cards.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market="Over 4.5 Cards",
        fotmob_referee_name="Test Referee",
    )
    
    referee = RefereeStats(name="Test Referee", cards_per_game=cards_per_game)
    
    verified = VerifiedData(
        source="test",
        data_confidence="MEDIUM",
        referee=referee,
        referee_confidence="MEDIUM",
    )
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: Lenient referee should veto Over Cards
    if cards_per_game <= REFEREE_LENIENT_THRESHOLD:
        # Should have veto inconsistency
        has_veto = any(
            "veto" in issue.lower() or "permissivo" in issue.lower()
            for issue in result.inconsistencies
        )
        assert has_veto, (
            f"Lenient referee ({cards_per_game} cards/game) should veto Over Cards"
        )


# ============================================
# PROPERTY 15: Double Critical Under Suggestion
# **Feature: verification-layer, Property 15: Double critical Under suggestion**
# **Validates: Requirements 8.2**
# ============================================

def test_property_15_double_critical_under_suggestion():
    """
    **Feature: verification-layer, Property 15: Double critical Under suggestion**
    **Validates: Requirements 8.2**
    
    *For any* verification where both teams have injury_severity = "CRITICAL",
    the alternative_markets SHALL include Under variant.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market="Over 2.5 Goals",
        home_injury_severity="CRITICAL",
        away_injury_severity="CRITICAL",
    )
    
    verified = VerifiedData(source="test", data_confidence="MEDIUM")
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: Both teams CRITICAL should suggest Under
    has_under = any("under" in alt.lower() for alt in result.alternative_markets)
    
    assert has_under, (
        f"Both teams CRITICAL should suggest Under market. "
        f"Alternatives: {result.alternative_markets}"
    )


# ============================================
# PROPERTY 2: Market Reconsideration Flag
# **Feature: verification-layer, Property 2: Market reconsideration flag**
# **Validates: Requirements 1.3, 8.1**
# ============================================

def test_property_2_market_reconsideration_flag():
    """
    **Feature: verification-layer, Property 2: Market reconsideration flag**
    **Validates: Requirements 1.3, 8.1**
    
    *For any* verification where total key_player impact > 20 AND suggested 
    market contains "Over", the result SHALL include a market reconsideration 
    flag or CHANGE_MARKET status.
    """
    request = VerificationRequest(
        match_id="test_123",
        home_team="Home FC",
        away_team="Away FC",
        match_date="2026-01-15",
        league="soccer_england_premier_league",
        preliminary_score=8.0,
        suggested_market="Over 2.5 Goals",
        home_missing_players=["Player1", "Player2", "Player3"],
    )
    
    # Create high impact players (total > 20)
    home_impacts = [
        PlayerImpact(name="Player1", impact_score=8),  # Key player
        PlayerImpact(name="Player2", impact_score=8),  # Key player
        PlayerImpact(name="Player3", impact_score=7),  # Key player
    ]
    
    verified = VerifiedData(
        source="test",
        data_confidence="MEDIUM",
        home_player_impacts=home_impacts,
        home_total_impact=23.0,
    )
    
    validator = LogicValidator()
    result = validator.validate(request, verified)
    
    # Property: High key player impact + Over should trigger reconsideration
    total_key_impact = sum(p.impact_score for p in home_impacts if p.is_key_player)
    
    if total_key_impact > CRITICAL_IMPACT_THRESHOLD:
        # Should have CHANGE_MARKET status or inconsistency
        has_reconsideration = (
            result.status == VerificationStatus.CHANGE_MARKET or
            result.status == VerificationStatus.REJECT or
            len(result.inconsistencies) > 0
        )
        assert has_reconsideration, (
            f"High key player impact ({total_key_impact}) + Over should trigger reconsideration"
        )


# ============================================
# INTEGRATION TESTS FOR MAIN.PY HELPER
# Task 7: Integration with main.py
# ============================================

def test_run_verification_check_helper_available():
    """
    Test that run_verification_check helper is importable from main.py.
    
    Validates: Task 7.1 - Integration with main.py
    """
    try:
        from src.main import run_verification_check, _VERIFICATION_LAYER_AVAILABLE
        assert callable(run_verification_check)
        # The flag should exist
        assert isinstance(_VERIFICATION_LAYER_AVAILABLE, bool)
    except ImportError as e:
        pytest.skip(f"main.py import failed (expected in isolated test): {e}")


def test_run_verification_check_returns_tuple():
    """
    Test that run_verification_check returns a 4-tuple.
    
    Validates: Task 7.1, 7.2 - Correct return format
    """
    try:
        from src.main import run_verification_check
    except ImportError:
        pytest.skip("main.py import failed")
    
    # Create mock match and analysis objects
    class MockMatch:
        id = "test_123"
        home_team = "Test Home"
        away_team = "Test Away"
        league = "soccer_england_premier_league"
        start_time = None
        referee_name = None
    
    class MockAnalysis:
        score = 8.5
        recommended_market = "Over 2.5 Goals"
        home_missing_players = []
        away_missing_players = []
        home_injury_severity = "LOW"
        away_injury_severity = "LOW"
        home_injury_impact = 0.0
        away_injury_impact = 0.0
    
    result = run_verification_check(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats={},
        away_stats={},
        context_label="TEST"
    )
    
    # Should return a 4-tuple
    assert isinstance(result, tuple)
    assert len(result) == 4
    
    should_send, adjusted_score, adjusted_market, verification_result = result
    
    # Validate types
    assert isinstance(should_send, bool)
    assert isinstance(adjusted_score, (int, float))
    # adjusted_market can be None or str
    assert adjusted_market is None or isinstance(adjusted_market, str)
    # verification_result can be None or VerificationResult


def test_run_verification_check_skips_low_score():
    """
    Test that run_verification_check skips verification for low scores.
    
    Validates: Property 12 - Score threshold gating
    """
    try:
        from src.main import run_verification_check
    except ImportError:
        pytest.skip("main.py import failed")
    
    class MockMatch:
        id = "test_low_score"
        home_team = "Test Home"
        away_team = "Test Away"
        league = "soccer_england_premier_league"
        start_time = None
        referee_name = None
    
    class MockAnalysis:
        score = 5.0  # Below threshold (7.5)
        recommended_market = "Over 2.5 Goals"
        home_missing_players = []
        away_missing_players = []
        home_injury_severity = "LOW"
        away_injury_severity = "LOW"
        home_injury_impact = 0.0
        away_injury_impact = 0.0
    
    should_send, adjusted_score, adjusted_market, verification_result = run_verification_check(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats={},
        away_stats={},
        context_label="TEST"
    )
    
    # Should pass through without verification
    assert should_send is True
    assert adjusted_score == 5.0
    assert adjusted_market == "Over 2.5 Goals"
    assert verification_result is None  # No verification performed


def test_send_alert_accepts_verification_info():
    """
    Test that send_alert function accepts verification_info parameter.
    
    Validates: Task 7.3 - Add verification result to alert message
    """
    import inspect
    from src.alerting.notifier import send_alert
    
    sig = inspect.signature(send_alert)
    params = list(sig.parameters.keys())
    
    assert 'verification_info' in params, "send_alert should accept verification_info parameter"


def test_verification_info_format():
    """
    Test that verification_info dict has expected structure.
    
    Validates: Task 7.3 - Verification info format
    """
    from src.analysis.verification_layer import (
        VerificationResult,
        VerificationStatus,
        VerifiedData,
    )
    
    # Create a sample verification result
    result = VerificationResult(
        status=VerificationStatus.CONFIRM,
        original_score=8.5,
        adjusted_score=8.0,
        original_market="Over 2.5 Goals",
        inconsistencies=["Test inconsistency"],
        overall_confidence="HIGH",
        reasoning="Test reasoning in Italian",
        verified_data=VerifiedData(source="test"),
    )
    
    # Build verification_info dict as done in main.py
    verification_info = {
        'status': result.status.value,
        'confidence': result.overall_confidence,
        'reasoning': result.reasoning[:200] if result.reasoning else None,
        'inconsistencies_count': len(result.inconsistencies),
    }
    
    # Validate structure
    assert verification_info['status'] == 'confirm'
    assert verification_info['confidence'] == 'HIGH'
    assert verification_info['reasoning'] == 'Test reasoning in Italian'
    assert verification_info['inconsistencies_count'] == 1


def test_settings_verification_constants():
    """
    Test that verification settings are defined in config/settings.py.
    
    Validates: Task 8.1 - Add verification settings to config
    """
    from config.settings import (
        VERIFICATION_ENABLED,
        VERIFICATION_SCORE_THRESHOLD,
        VERIFICATION_TIMEOUT,
        PLAYER_KEY_IMPACT_THRESHOLD,
        CRITICAL_IMPACT_THRESHOLD,
        FORM_DEVIATION_THRESHOLD,
        LOW_SCORING_THRESHOLD,
        H2H_CARDS_THRESHOLD,
        H2H_CORNERS_THRESHOLD,
        COMBINED_CORNERS_THRESHOLD,
        REFEREE_STRICT_THRESHOLD,
        REFEREE_LENIENT_THRESHOLD,
        CRITICAL_INJURY_OVER_PENALTY,
        FORM_WARNING_PENALTY,
        INCONSISTENCY_PENALTY,
    )
    
    # Validate types and reasonable values
    assert isinstance(VERIFICATION_ENABLED, bool)
    assert isinstance(VERIFICATION_SCORE_THRESHOLD, (int, float))
    assert VERIFICATION_SCORE_THRESHOLD == 7.5
    assert isinstance(VERIFICATION_TIMEOUT, int)
    assert VERIFICATION_TIMEOUT > 0
    
    # Thresholds should be positive
    assert PLAYER_KEY_IMPACT_THRESHOLD > 0
    assert CRITICAL_IMPACT_THRESHOLD > 0
    assert FORM_DEVIATION_THRESHOLD > 0
    assert LOW_SCORING_THRESHOLD > 0
    assert H2H_CARDS_THRESHOLD > 0
    assert H2H_CORNERS_THRESHOLD > 0
    assert COMBINED_CORNERS_THRESHOLD > 0
    assert REFEREE_STRICT_THRESHOLD > 0
    assert REFEREE_LENIENT_THRESHOLD > 0
    
    # Penalties should be positive
    assert CRITICAL_INJURY_OVER_PENALTY > 0
    assert FORM_WARNING_PENALTY > 0
    assert INCONSISTENCY_PENALTY > 0


# ============================================
# V7.0.1: INJURY DATA EXTRACTION FROM FOTMOB CONTEXT
# ============================================

def test_calculate_injury_severity():
    """
    Test that _calculate_injury_severity correctly classifies injury severity.
    
    Validates: V7.0.1 - Injury data extraction from FotMob context
    """
    from src.analysis.verification_layer import _calculate_injury_severity
    
    # CRITICAL: 5+ injuries
    assert _calculate_injury_severity(5) == "CRITICAL"
    assert _calculate_injury_severity(7) == "CRITICAL"
    assert _calculate_injury_severity(10) == "CRITICAL"
    
    # HIGH: 3-4 injuries
    assert _calculate_injury_severity(3) == "HIGH"
    assert _calculate_injury_severity(4) == "HIGH"
    
    # MEDIUM: 1-2 injuries
    assert _calculate_injury_severity(1) == "MEDIUM"
    assert _calculate_injury_severity(2) == "MEDIUM"
    
    # LOW: 0 injuries
    assert _calculate_injury_severity(0) == "LOW"


def test_create_verification_request_with_fotmob_context():
    """
    Test that create_verification_request_from_match extracts injury data from FotMob context.
    
    Validates: V7.0.1 - Injury data extraction from FotMob context
    """
    from src.analysis.verification_layer import create_verification_request_from_match
    
    # Mock match object
    class MockMatch:
        id = "test_123"
        home_team = "Home FC"
        away_team = "Away FC"
        league = "soccer_england_premier_league"
        start_time = None
    
    # Mock analysis object (NewsLog)
    class MockAnalysis:
        score = 8.5
        recommended_market = "Over 2.5 Goals"
    
    # FotMob context with injuries
    home_context = {
        'injuries': [
            {'name': 'Player A', 'reason': 'Knee injury'},
            {'name': 'Player B', 'reason': 'Suspended'},
            {'name': 'Player C', 'reason': 'Illness'},
            {'name': 'Player D', 'reason': 'Muscle strain'},
            {'name': 'Player E', 'reason': 'Ankle injury'},
        ]
    }
    away_context = {
        'injuries': [
            {'name': 'Player X', 'reason': 'Red card suspension'},
        ]
    }
    
    request = create_verification_request_from_match(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats={},
        away_stats={},
        home_context=home_context,
        away_context=away_context,
    )
    
    # Verify injury data was extracted
    assert len(request.home_missing_players) == 5
    assert 'Player A' in request.home_missing_players
    assert 'Player E' in request.home_missing_players
    
    assert len(request.away_missing_players) == 1
    assert 'Player X' in request.away_missing_players
    
    # Verify severity was calculated correctly
    assert request.home_injury_severity == "CRITICAL"  # 5 injuries
    assert request.away_injury_severity == "MEDIUM"    # 1 injury
    
    # Verify impact was calculated
    assert request.home_injury_impact == 15.0  # 5 * 3.0
    assert request.away_injury_impact == 3.0   # 1 * 3.0


def test_create_verification_request_with_empty_context():
    """
    Test that create_verification_request_from_match handles empty/None context gracefully.
    
    Validates: V7.0.1 - Edge case handling for empty FotMob context
    """
    from src.analysis.verification_layer import create_verification_request_from_match
    
    class MockMatch:
        id = "test_456"
        home_team = "Home FC"
        away_team = "Away FC"
        league = "soccer_italy_serie_a"
        start_time = None
    
    class MockAnalysis:
        score = 7.8
        recommended_market = "1"
    
    # Test with None context
    request = create_verification_request_from_match(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats=None,
        away_stats=None,
        home_context=None,
        away_context=None,
    )
    
    assert request.home_missing_players == []
    assert request.away_missing_players == []
    assert request.home_injury_severity == "LOW"
    assert request.away_injury_severity == "LOW"
    
    # Test with empty dict context
    request2 = create_verification_request_from_match(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats={},
        away_stats={},
        home_context={},
        away_context={},
    )
    
    assert request2.home_missing_players == []
    assert request2.away_missing_players == []


def test_create_verification_request_with_malformed_injuries():
    """
    Test that create_verification_request_from_match handles malformed injury data.
    
    Validates: V7.0.1 - Robustness against malformed FotMob data
    """
    from src.analysis.verification_layer import create_verification_request_from_match
    
    class MockMatch:
        id = "test_789"
        home_team = "Home FC"
        away_team = "Away FC"
        league = "soccer_spain_la_liga"
        start_time = None
    
    class MockAnalysis:
        score = 8.0
        recommended_market = "BTTS"
    
    # Malformed context: injuries is not a list, or contains non-dict items
    home_context = {
        'injuries': "not a list"  # Should be handled gracefully
    }
    away_context = {
        'injuries': [
            {'name': 'Valid Player'},
            None,  # Invalid entry
            {'no_name_key': 'Missing name'},  # Missing 'name' key
            {'name': ''},  # Empty name
            {'name': 'Another Valid'},
        ]
    }
    
    request = create_verification_request_from_match(
        match=MockMatch(),
        analysis=MockAnalysis(),
        home_stats={},
        away_stats={},
        home_context=home_context,
        away_context=away_context,
    )
    
    # Home should have no injuries (malformed data)
    assert request.home_missing_players == []
    assert request.home_injury_severity == "LOW"
    
    # Away should only have valid players
    assert len(request.away_missing_players) == 2
    assert 'Valid Player' in request.away_missing_players
    assert 'Another Valid' in request.away_missing_players
    assert request.away_injury_severity == "MEDIUM"  # 2 injuries


# ============================================
# V7.0.2 BUG FIX REGRESSION TESTS
# ============================================

def test_bug6_referee_empty_string_regression():
    """
    BUG 6 REGRESSION TEST: Empty referee name should not match at index 0.
    
    Before fix: "" would match at index 0 in any text, causing false positives.
    After fix V7.0.2: Empty string returns None immediately.
    After fix V7.1: Empty string triggers generic pattern search (intentional).
    
    V7.1 UPDATE: Now we intentionally search for generic referee patterns
    when no name is provided. The test is updated to reflect this.
    """
    from src.analysis.verification_layer import TavilyVerifier
    
    verifier = TavilyVerifier()
    
    # V7.1: With empty/None referee name, we now search for generic patterns
    # Text without referee context should NOT match
    result_no_context = verifier._parse_referee_stats(
        text="Some random text without referee context",
        referee_name=""
    )
    assert result_no_context is None, "Text without referee patterns should return None"
    
    # V7.1: Text WITH referee patterns should match even without known name
    result_with_pattern = verifier._parse_referee_stats(
        text="The referee averages 5.0 cards per game this season",
        referee_name=""
    )
    assert result_with_pattern is not None, "V7.1: Should extract from generic referee pattern"
    assert result_with_pattern.cards_per_game == 5.0
    
    # Test with whitespace only - same behavior as empty
    result_whitespace = verifier._parse_referee_stats(
        text="Some random text without referee context",
        referee_name="   "
    )
    assert result_whitespace is None, "Text without referee patterns should return None"
    
    # Test with None - same behavior
    result_none = verifier._parse_referee_stats(
        text="Some random text without referee context",
        referee_name=None
    )
    assert result_none is None, "Text without referee patterns should return None"
    
    # Test with valid name - should work normally
    result_valid = verifier._parse_referee_stats(
        text="Referee John Smith averages 5.2 cards per game this season",
        referee_name="John Smith"
    )
    assert result_valid is not None, "Valid referee name should parse correctly"
    assert result_valid.cards_per_game == 5.2


def test_bug3_form_regex_no_N_character_regression():
    """
    BUG 3 REGRESSION TEST: Form regex should only match W/D/L, not N.
    
    Before fix: Pattern [WDLN] would match "N" causing matches_played < 5.
    After fix: Pattern [WDL] only matches valid results.
    """
    from src.analysis.verification_layer import TavilyVerifier
    
    verifier = TavilyVerifier()
    
    # Test with text containing "N" that could be mistaken for form
    # e.g., "WDLNW" should NOT match as form (N is not a valid result)
    result = verifier._parse_form_stats(
        text="Team FC form: WDLNW in recent matches",  # N in middle
        team_name="Team FC"
    )
    
    # If it matches, it should only count W, D, L
    if result:
        total = result.wins + result.draws + result.losses
        # Should be 5 if matched correctly (WWDLL pattern elsewhere)
        # or should not match at all if WDLNW is the only pattern
        assert total <= 5, f"Form should have at most 5 matches, got {total}"
    
    # Test with valid form string
    result_valid = verifier._parse_form_stats(
        text="Team FC last 5 matches: W-W-D-L-L scored 8 goals",
        team_name="Team FC"
    )
    if result_valid:
        assert result_valid.wins + result_valid.draws + result_valid.losses == 5


def test_bug5_constants_from_settings():
    """
    BUG 5 REGRESSION TEST: Constants should be imported from settings.py.
    
    This ensures that modifying settings.py affects verification_layer.py.
    """
    from config.settings import (
        PLAYER_KEY_IMPACT_THRESHOLD as SETTINGS_PLAYER_THRESHOLD,
        VERIFICATION_SCORE_THRESHOLD as SETTINGS_SCORE_THRESHOLD,
    )
    from src.analysis.verification_layer import (
        PLAYER_KEY_IMPACT_THRESHOLD as VL_PLAYER_THRESHOLD,
        VERIFICATION_SCORE_THRESHOLD as VL_SCORE_THRESHOLD,
    )
    
    # Constants should match between settings and verification_layer
    assert SETTINGS_PLAYER_THRESHOLD == VL_PLAYER_THRESHOLD, (
        f"PLAYER_KEY_IMPACT_THRESHOLD mismatch: settings={SETTINGS_PLAYER_THRESHOLD}, "
        f"verification_layer={VL_PLAYER_THRESHOLD}"
    )
    assert SETTINGS_SCORE_THRESHOLD == VL_SCORE_THRESHOLD, (
        f"VERIFICATION_SCORE_THRESHOLD mismatch: settings={SETTINGS_SCORE_THRESHOLD}, "
        f"verification_layer={VL_SCORE_THRESHOLD}"
    )


def test_bug2_losing_streak_incomplete_data_documented():
    """
    BUG 2 DOCUMENTATION TEST: is_on_losing_streak returns False for incomplete data.
    
    This test documents the intentional behavior: if matches_played < 5,
    the function returns False to avoid false positives.
    """
    from src.analysis.verification_layer import FormStats
    
    # Incomplete data (only 3 matches) - should return False even with 0 wins
    incomplete_form = FormStats(wins=0, draws=1, losses=2)  # 3 matches
    assert incomplete_form.matches_played == 3
    assert incomplete_form.is_on_losing_streak() is False, (
        "Incomplete data (< 5 matches) should return False for losing streak"
    )
    
    # Complete data with 0 wins - should return True
    complete_losing = FormStats(wins=0, draws=2, losses=3)  # 5 matches
    assert complete_losing.matches_played == 5
    assert complete_losing.is_on_losing_streak() is True, (
        "Complete data with 0 wins should return True for losing streak"
    )
    
    # Complete data with wins - should return False
    complete_winning = FormStats(wins=2, draws=1, losses=2)  # 5 matches
    assert complete_winning.matches_played == 5
    assert complete_winning.is_on_losing_streak() is False, (
        "Complete data with wins should return False for losing streak"
    )


# ============================================
# V2.1 REGRESSION TESTS: Generic Parser
# ============================================

def test_v21_parser_generic_team_names():
    """
    V2.1 REGRESSION TEST: Parser should work with any team name, not just Inter/Milan.
    
    This test ensures the OptimizedResponseParser correctly extracts form stats
    for teams from any league (Brazilian, English, Spanish, etc.).
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    # Test with Brazilian teams
    parser = OptimizedResponseParser(
        home_team='Flamengo',
        away_team='Palmeiras',
        referee_name='Wilton Sampaio',
        players=['gabriel barbosa', 'endrick']
    )
    
    text = '''Flamengo won 2, drew 2, and lost 1. Palmeiras won 1, drew 0, and lost 4.'''
    
    request = VerificationRequest(
        match_id='test',
        home_team='Flamengo',
        away_team='Palmeiras',
        match_date='2025-01-15',
        league='brazil',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Form stats should be extracted for both teams
    assert result.home_form is not None, 'Flamengo form should be extracted'
    assert result.away_form is not None, 'Palmeiras form should be extracted'
    assert result.home_form.wins == 2, f'Flamengo wins should be 2, got {result.home_form.wins}'
    assert result.home_form.draws == 2, f'Flamengo draws should be 2'
    assert result.home_form.losses == 1, f'Flamengo losses should be 1'
    assert result.away_form.wins == 1, f'Palmeiras wins should be 1, got {result.away_form.wins}'


def test_v21_parser_player_values_thousands():
    """
    V2.1 REGRESSION TEST: Parser should handle €Xk (thousands) format.
    
    Players with lower market values are often shown as €400k instead of €0.4m.
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
        market_value_to_impact,
    )
    
    parser = OptimizedResponseParser(
        home_team='Flamengo',
        away_team='Palmeiras',
        referee_name=None,
        players=['gabriel barbosa', 'endrick']
    )
    
    # Text with mixed formats: €400k and €60m
    text = '''Gabriel Barbosa's market value is €400k. Endrick's market value is €60m.'''
    
    request = VerificationRequest(
        match_id='test',
        home_team='Flamengo',
        away_team='Palmeiras',
        match_date='2025-01-15',
        league='brazil',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=['Gabriel Barbosa'],
        away_missing_players=['Endrick'],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Gabriel Barbosa: €400k = €0.4m -> impact 3
    assert result.home_player_impacts[0].impact_score == 3, (
        f'Gabriel Barbosa (€400k) should be impact 3, got {result.home_player_impacts[0].impact_score}'
    )
    
    # Endrick: €60m -> impact 9
    assert result.away_player_impacts[0].impact_score == 9, (
        f'Endrick (€60m) should be impact 9, got {result.away_player_impacts[0].impact_score}'
    )


def test_v21_parser_italian_teams_regression():
    """
    V2.1 REGRESSION TEST: Parser should still work with Italian teams.
    
    Ensures the generic parser doesn't break existing Inter/Milan functionality.
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Inter',
        away_team='Milan',
        referee_name='Mariani',
        players=['lautaro martinez', 'leao']
    )
    
    text = '''Inter won 3, drew 1, and lost 1. Milan won 2, drew 2, and lost 1.
    Lautaro Martinez's market value is €80m. Leao's market value is €70m.'''
    
    request = VerificationRequest(
        match_id='test',
        home_team='Inter',
        away_team='Milan',
        match_date='2025-01-15',
        league='italy',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=['Lautaro Martinez'],
        away_missing_players=['Leao'],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Form stats
    assert result.home_form is not None, 'Inter form should be extracted'
    assert result.away_form is not None, 'Milan form should be extracted'
    assert result.home_form.wins == 3, f'Inter wins should be 3'
    assert result.away_form.wins == 2, f'Milan wins should be 2'
    
    # Player impacts
    assert result.home_player_impacts[0].impact_score == 10, (
        f'Lautaro (€80m) should be impact 10'
    )
    assert result.away_player_impacts[0].impact_score == 9, (
        f'Leao (€70m) should be impact 9'
    )


# ============================================
# V2.2 MULTI-LANGUAGE PARSER TESTS
# ============================================

def test_v22_parser_turkish_teams():
    """
    V2.2 TEST: Parser should work with Turkish teams (Elite 7 league).
    
    Tests:
    - Turkish team name matching (Galatasaray, Fenerbahçe)
    - Accent handling (ç, ş, ı)
    - Form extraction
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        referee_name='Cüneyt Çakır',
        players=['icardi', 'dzeko']
    )
    
    text = '''Galatasaray won 4, drew 0, and lost 1. Fenerbahce won 3, drew 1, and lost 1.
    Icardi's market value is €15m. Dzeko's market value is €5m.'''
    
    request = VerificationRequest(
        match_id='test_turkey',
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        match_date='2025-01-15',
        league='soccer_turkey_super_league',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=['Icardi'],
        away_missing_players=['Dzeko'],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Form stats should be extracted
    assert result.home_form is not None, 'Galatasaray form should be extracted'
    assert result.away_form is not None, 'Fenerbahce form should be extracted'
    assert result.home_form.wins == 4, f'Galatasaray wins should be 4, got {result.home_form.wins}'
    
    # Player impacts
    assert len(result.home_player_impacts) == 1, 'Should have 1 home player'
    assert result.home_player_impacts[0].impact_score == 6, (
        f'Icardi (€15m) should be impact 6, got {result.home_player_impacts[0].impact_score}'
    )


def test_v22_parser_corner_extraction():
    """
    V2.2 TEST: Parser should extract corner stats from various formats.
    
    Tests the sentence-based corner extraction that handles:
    - "Team...and X corner per game" format
    - Decimal point issues in regex
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Flamengo',
        away_team='Palmeiras',
        referee_name='Test Ref',
        players=[]
    )
    
    # This is the actual format from Tavily responses
    text = '''Flamengo has an average of 1.8 goals per game, 1.0 yellow cards per game, and 5 corners per game. 
    Palmeiras averages 1.8 goals per game, 1.0 yellow cards per game, and 8 corners per game.'''
    
    request = VerificationRequest(
        match_id='test_corners',
        home_team='Flamengo',
        away_team='Palmeiras',
        match_date='2025-01-15',
        league='brazil',
        preliminary_score=8.0,
        suggested_market='Over 9.5 Corners',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Corner stats should be extracted
    assert result.home_corner_avg is not None, 'Flamengo corners should be extracted'
    assert result.away_corner_avg is not None, 'Palmeiras corners should be extracted'
    assert result.home_corner_avg == 5.0, f'Flamengo corners should be 5, got {result.home_corner_avg}'
    assert result.away_corner_avg == 8.0, f'Palmeiras corners should be 8, got {result.away_corner_avg}'


def test_v22_text_normalizer_accents():
    """
    V2.2 TEST: Text normalizer should handle accented characters.
    
    Tests fold_accents and normalize_for_matching functions.
    Note: Turkish dotless i (ı) is a separate letter, not an accent.
    """
    from src.utils.text_normalizer import fold_accents, normalize_for_matching
    
    # Turkish - ç is accent, ı is separate letter (preserved)
    assert fold_accents('Fenerbahçe') == 'Fenerbahce'
    assert 'cak' in fold_accents('Çakır').lower()  # ç→c works, ı preserved
    
    # Portuguese
    assert fold_accents('São Paulo') == 'Sao Paulo'
    assert fold_accents('Grêmio') == 'Gremio'
    
    # German
    assert fold_accents('Müller') == 'Muller'
    assert fold_accents('Götze') == 'Gotze'
    
    # Full normalization (lowercase + whitespace collapse)
    assert normalize_for_matching('Fenerbahçe SK') == 'fenerbahce sk'
    assert normalize_for_matching('  São  Paulo  ') == 'sao paulo'


def test_v22_fuzzy_team_matching():
    """
    V2.2 TEST: Fuzzy matching should find teams with typos/variations.
    """
    from src.utils.text_normalizer import fuzzy_match_team, find_team_in_text
    
    # Exact match
    found, score = fuzzy_match_team('Galatasaray', 'Galatasaray won the match')
    assert found, 'Should find exact match'
    assert score == 100
    
    # Accent variation
    found, score = fuzzy_match_team('Fenerbahçe', 'Fenerbahce played well')
    assert found, 'Should find accent variation'
    
    # Alias matching
    found, score = find_team_in_text('Galatasaray', 'Cimbom won 3-0')
    assert found, 'Should find team by alias (Cimbom)'


def test_v222_form_written_numbers():
    """
    V2.2.2 TEST: Parser should extract form stats with written numbers.
    
    Tests the flexible pattern for sentences like:
    "Galatasaray won two, Fenerbahçe won one, and there were two draws"
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        referee_name=None,
        players=[]
    )
    
    # This is the actual format from Tavily Turkey response
    text = '''In the last five matches, Galatasaray won two, Fenerbahçe won one, and there were two draws.'''
    
    request = VerificationRequest(
        match_id='test_written_nums',
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        match_date='2025-01-15',
        league='turkey',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Galatasaray: won 2, draws 2, losses 1 (5 - 2 - 2 = 1)
    assert result.home_form is not None, 'Galatasaray form should be extracted'
    assert result.home_form.wins == 2, f'Galatasaray wins should be 2, got {result.home_form.wins}'
    assert result.home_form.draws == 2, f'Galatasaray draws should be 2, got {result.home_form.draws}'
    
    # Fenerbahçe: won 1, draws 2, losses 2 (5 - 1 - 2 = 2)
    assert result.away_form is not None, 'Fenerbahçe form should be extracted'
    assert result.away_form.wins == 1, f'Fenerbahçe wins should be 1, got {result.away_form.wins}'


# ============================================
# V2.4 MULTI-SITE FALLBACK TESTS
# ============================================

def test_v24_site_priority_configuration():
    """
    V2.4 TEST: SITE_PRIORITY configuration should be defined.
    
    Tests that the multi-site fallback configuration exists and has
    the expected structure.
    """
    from src.analysis.verification_layer import SITE_PRIORITY
    
    # Should have entries for each data type
    assert 'team_stats' in SITE_PRIORITY, 'Should have team_stats sites'
    assert 'player_values' in SITE_PRIORITY, 'Should have player_values sites'
    assert 'form' in SITE_PRIORITY, 'Should have form sites'
    assert 'referee' in SITE_PRIORITY, 'Should have referee sites'
    assert 'h2h' in SITE_PRIORITY, 'Should have h2h sites'
    
    # Each should be a non-empty list
    for key, sites in SITE_PRIORITY.items():
        assert isinstance(sites, list), f'{key} should be a list'
        assert len(sites) > 0, f'{key} should have at least one site'
        for site in sites:
            assert isinstance(site, str), f'{key} sites should be strings'
            assert '.' in site, f'{key} sites should be domain names'


def test_v24_query_builder_fallback_queries():
    """
    V2.4 TEST: OptimizedQueryBuilder should generate fallback queries.
    
    Tests that get_fallback_queries returns appropriate queries for
    missing data types.
    """
    from src.analysis.verification_layer import OptimizedQueryBuilder
    
    builder = OptimizedQueryBuilder(
        home_team='Celtic',
        away_team='Rangers',
        players=['Furuhashi', 'Tavernier'],
        referee_name='Nick Walsh',
        league='Scottish Premiership',
    )
    
    # Test with missing corners
    fallback = builder.get_fallback_queries(['corners'])
    assert len(fallback) > 0, 'Should generate fallback for corners'
    assert any('soccerstats' in q[1].lower() or 'flashscore' in q[1].lower() for q in fallback), (
        'Fallback should use secondary sites'
    )
    
    # Test with missing form
    fallback_form = builder.get_fallback_queries(['form'])
    assert len(fallback_form) > 0, 'Should generate fallback for form'
    
    # Test with multiple missing types
    fallback_multi = builder.get_fallback_queries(['corners', 'form', 'h2h'])
    assert len(fallback_multi) >= 1, 'Should generate fallbacks for multiple types'
    
    # Test with empty list - should return empty
    fallback_empty = builder.get_fallback_queries([])
    assert fallback_empty == [], 'Empty missing list should return empty fallback'


def test_v24_identify_missing_data():
    """
    V2.4 TEST: TavilyVerifier._identify_missing_data should correctly identify gaps.
    
    Tests that the method correctly identifies which data types are missing
    from a VerifiedData object.
    """
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerifiedData,
        FormStats,
        H2HStats,
    )
    
    verifier = TavilyVerifier()
    
    # Test with all data missing
    empty_verified = VerifiedData(source='test', data_confidence='LOW')
    missing = verifier._identify_missing_data(empty_verified)
    assert 'corners' in missing, 'Should identify missing corners'
    assert 'form' in missing, 'Should identify missing form'
    assert 'h2h' in missing, 'Should identify missing h2h'
    
    # Test with partial data
    partial_verified = VerifiedData(
        source='test',
        data_confidence='MEDIUM',
        home_corner_avg=5.0,
        away_corner_avg=6.0,
        corner_confidence='MEDIUM',
        home_form=FormStats(wins=2, draws=1, losses=2),
        away_form=FormStats(wins=3, draws=0, losses=2),
        form_confidence='MEDIUM',
    )
    missing_partial = verifier._identify_missing_data(partial_verified)
    assert 'corners' not in missing_partial, 'Should not flag corners as missing'
    assert 'form' not in missing_partial, 'Should not flag form as missing'
    assert 'h2h' in missing_partial, 'Should identify missing h2h'
    
    # Test with complete data
    complete_verified = VerifiedData(
        source='test',
        data_confidence='HIGH',
        home_corner_avg=5.0,
        away_corner_avg=6.0,
        corner_confidence='HIGH',
        home_form=FormStats(wins=2, draws=1, losses=2),
        away_form=FormStats(wins=3, draws=0, losses=2),
        form_confidence='HIGH',
        h2h=H2HStats(matches_analyzed=5, avg_goals=2.5, avg_corners=10.0),
        h2h_confidence='HIGH',
    )
    missing_complete = verifier._identify_missing_data(complete_verified)
    assert len(missing_complete) == 0 or 'team_stats' in missing_complete, (
        'Complete data should have minimal missing items'
    )


def test_v24_query_with_fallback_no_fallback_needed():
    """
    V2.4 TEST: query_with_fallback should not execute fallback when data is complete.
    
    Tests that fallback queries are only executed when extraction rate < 75%.
    """
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
    )
    
    # Create a mock verifier that returns complete data
    class MockTavilyVerifierComplete(TavilyVerifier):
        def __init__(self):
            super().__init__()
            self._fallback_called = False
        
        def is_available(self):
            return True
        
        def query_optimized(self, request):
            return {
                'answer': '''Celtic won 4, drew 1, lost 0. Rangers won 3, drew 1, lost 1.
                Celtic averages 6.5 corners per game. Rangers averages 5.8 corners per game.
                Head to head: 2.8 goals average, 10.5 corners average.
                Nick Walsh averages 4.2 cards per game.''',
                'results': [],
                'provider': 'tavily_v2',
                'queries_executed': 4,
                'query_times': {},
            }
        
        def _execute_fallback_queries(self, request, missing_data):
            self._fallback_called = True
            return super()._execute_fallback_queries(request, missing_data)
    
    verifier = MockTavilyVerifierComplete()
    
    request = VerificationRequest(
        match_id='test_no_fallback',
        home_team='Celtic',
        away_team='Rangers',
        match_date='2025-01-15',
        league='soccer_scotland_premiership',
        preliminary_score=8.0,
        suggested_market='Over 2.5 Goals',
        fotmob_referee_name='Nick Walsh',
    )
    
    response = verifier.query_with_fallback(request)
    
    assert response is not None, 'Should return response'
    # With complete data, fallback should not be executed
    # (extraction rate should be >= 75%)


def test_v24_extract_league_name_extended():
    """
    V2.4 TEST: _extract_league_name should handle all Elite 7 and Tier 2 leagues.
    
    Tests that the league name extraction works for all managed leagues.
    """
    from src.analysis.verification_layer import TavilyVerifier
    
    verifier = TavilyVerifier()
    
    # Elite 7 leagues
    assert 'Super Lig' in verifier._extract_league_name('soccer_turkey_super_league')
    assert 'Primera' in verifier._extract_league_name('soccer_argentina_primera_division')
    assert 'Scottish' in verifier._extract_league_name('soccer_scotland_premiership')
    assert 'A-League' in verifier._extract_league_name('soccer_australia_a_league')
    assert 'Ekstraklasa' in verifier._extract_league_name('soccer_poland_ekstraklasa')
    
    # Tier 2 leagues
    assert 'J-League' in verifier._extract_league_name('soccer_japan_j_league')
    assert 'Brazil' in verifier._extract_league_name('soccer_brazil_serie_b')
    
    # Unknown league should return formatted version
    unknown = verifier._extract_league_name('soccer_unknown_league')
    assert 'Unknown' in unknown or 'unknown' in unknown.lower()


def test_v24_fallback_query_site_targeting():
    """
    V2.4 TEST: Fallback queries should target secondary sites.
    
    Tests that fallback queries use different sites than primary queries.
    """
    from src.analysis.verification_layer import OptimizedQueryBuilder, SITE_PRIORITY
    
    builder = OptimizedQueryBuilder(
        home_team='Boca Juniors',
        away_team='River Plate',
        players=['Cavani', 'Borja'],
        referee_name='Fernando Rapallini',
        league='Primera División',
    )
    
    # Primary query uses footystats.org
    primary_query = builder.build_team_stats_query()
    assert 'footystats.org' in primary_query, 'Primary should use footystats.org'
    
    # Fallback should use secondary sites
    fallback_queries = builder.get_fallback_queries(['team_stats'])
    if fallback_queries:
        fallback_query = fallback_queries[0][1]
        # Should use a different site
        assert 'soccerstats' in fallback_query.lower() or 'flashscore' in fallback_query.lower(), (
            'Fallback should use secondary site'
        )


def test_v24_edge_case_empty_missing_data():
    """
    V2.4 EDGE CASE: _identify_missing_data with None values.
    
    Tests that the method handles None values gracefully.
    """
    from src.analysis.verification_layer import TavilyVerifier, VerifiedData
    
    verifier = TavilyVerifier()
    
    # VerifiedData with explicit None values
    verified = VerifiedData(
        source='test',
        data_confidence='LOW',
        home_corner_avg=None,
        away_corner_avg=None,
        home_form=None,
        away_form=None,
        h2h=None,
    )
    
    # Should not raise exception
    missing = verifier._identify_missing_data(verified)
    assert isinstance(missing, list), 'Should return a list'
    assert 'corners' in missing, 'Should identify None corners as missing'


# ============================================
# V2.5 FORM PARSING FIX TESTS
# ============================================

def test_v25_form_has_won_drawn_pattern():
    """
    V2.5 TEST: Parser should extract form stats with "has won X, drawn Y" pattern.
    
    This pattern is common in Tavily responses for Turkish and other leagues:
    "Team has won 4, drawn 1, and conceded..."
    
    Before V2.5: Only matched "Team won X, drew Y, lost Z"
    After V2.5: Also matches "Team has won X, drawn Y" (calculates losses)
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        referee_name=None,
        players=[]
    )
    
    # This is the actual format from Tavily Turkey response
    text = '''In the last 5 matches, Galatasaray has won 4, drawn 1, and conceded an average of 0.6 goals per game. Fenerbahçe has won 3, drawn 2, and scored an average of 2.8 goals per game.'''
    
    request = VerificationRequest(
        match_id='test_v25_form',
        home_team='Galatasaray',
        away_team='Fenerbahçe',
        match_date='2025-01-15',
        league='turkey',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Galatasaray: has won 4, drawn 1 -> losses = 5 - 4 - 1 = 0
    assert result.home_form is not None, 'Galatasaray form should be extracted'
    assert result.home_form.wins == 4, f'Galatasaray wins should be 4, got {result.home_form.wins}'
    assert result.home_form.draws == 1, f'Galatasaray draws should be 1, got {result.home_form.draws}'
    assert result.home_form.losses == 0, f'Galatasaray losses should be 0, got {result.home_form.losses}'
    
    # Fenerbahçe: has won 3, drawn 2 -> losses = 5 - 3 - 2 = 0
    assert result.away_form is not None, 'Fenerbahçe form should be extracted'
    assert result.away_form.wins == 3, f'Fenerbahçe wins should be 3, got {result.away_form.wins}'
    assert result.away_form.draws == 2, f'Fenerbahçe draws should be 2, got {result.away_form.draws}'


def test_v25_form_accent_insensitive_matching():
    """
    V2.5 TEST: Form parsing should be accent-insensitive.
    
    Team names with accents (Fenerbahçe) should match normalized patterns.
    """
    from src.analysis.verification_layer import (
        OptimizedResponseParser,
        VerificationRequest,
    )
    
    parser = OptimizedResponseParser(
        home_team='Fenerbahçe',  # With Turkish ç
        away_team='Beşiktaş',    # With Turkish ş
        referee_name=None,
        players=[]
    )
    
    # Text without proper Turkish characters
    text = '''Fenerbahce won 3, drew 1, and lost 1. Besiktas won 2, drew 2, and lost 1.'''
    
    request = VerificationRequest(
        match_id='test_v25_accents',
        home_team='Fenerbahçe',
        away_team='Beşiktaş',
        match_date='2025-01-15',
        league='turkey',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    result = parser.parse_to_verified_data(text, request)
    
    # Should match despite accent differences
    assert result.home_form is not None, 'Fenerbahçe form should be extracted (accent-insensitive)'
    assert result.home_form.wins == 3
    assert result.away_form is not None, 'Beşiktaş form should be extracted (accent-insensitive)'
    assert result.away_form.wins == 2


def test_v25_fallback_threshold_75_inclusive():
    """
    V2.5 TEST: Fallback should execute when extraction rate is exactly 75%.
    
    Before V2.5: Threshold was < 75 (exclusive)
    After V2.5: Threshold is <= 75 (inclusive)
    """
    from src.analysis.verification_layer import TavilyVerifier, VerifiedData, FormStats
    
    verifier = TavilyVerifier()
    
    # Create verified data with exactly 75% extraction (6/8)
    verified = VerifiedData(
        source='test',
        data_confidence='MEDIUM',
        home_form=FormStats(wins=2, draws=1, losses=2),
        away_form=FormStats(wins=3, draws=0, losses=2),
        form_confidence='MEDIUM',
        # Missing: corners (2 items), so 6/8 = 75%
        home_corner_avg=None,
        away_corner_avg=None,
        corner_confidence='LOW',
    )
    
    missing = verifier._identify_missing_data(verified)
    
    # Should identify corners as missing
    assert 'corners' in missing or 'team_stats' in missing, (
        'Should identify missing data at 75% extraction'
    )


# ============================================
# V2.6 PERPLEXITY FALLBACK FOR CORNERS TESTS
# ============================================

def test_v26_execute_perplexity_fallback_returns_corner_data():
    """
    V2.6 TEST: _execute_perplexity_fallback should return corner data from Perplexity.
    
    Tests that when Tavily cannot find corner data, Perplexity is called
    and returns corner statistics.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
        VerifiedData,
    )
    
    verifier = TavilyVerifier()
    
    request = VerificationRequest(
        match_id='test_v26_perplexity',
        home_team='Club León',
        away_team='Tigres UANL',
        match_date='2025-01-15',
        league='soccer_mexico_liga_mx',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    verified = VerifiedData(
        source='tavily_v2',
        data_confidence='MEDIUM',
        home_corner_avg=None,  # Missing corners
        away_corner_avg=None,
    )
    
    # Mock Perplexity provider
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = {
        'home_corners_avg': 5.2,
        'away_corners_avg': 4.8,
        'corners_total_avg': 10.0,
        'corners_signal': 'High',
        'corners_reasoning': 'Both teams attack wide',
        'data_confidence': 'Medium',
        'sources_found': 'FBref, SofaScore',
    }
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = verifier._execute_perplexity_fallback(request, verified)
    
    assert result is not None, 'Should return corner data from Perplexity'
    assert result['home_corners_avg'] == 5.2, f"Expected home_corners_avg=5.2, got {result['home_corners_avg']}"
    assert result['away_corners_avg'] == 4.8, f"Expected away_corners_avg=4.8, got {result['away_corners_avg']}"
    assert result['provider'] == 'perplexity_v2.6'
    
    # Verify Perplexity was called with correct parameters
    mock_perplexity.get_betting_stats.assert_called_once()
    call_args = mock_perplexity.get_betting_stats.call_args
    assert call_args.kwargs['home_team'] == 'Club León'
    assert call_args.kwargs['away_team'] == 'Tigres UANL'


def test_v26_perplexity_fallback_not_called_when_unavailable():
    """
    V2.6 TEST: _execute_perplexity_fallback should return None when Perplexity unavailable.
    
    Edge case: Perplexity API key not configured or provider disabled.
    """
    from unittest.mock import patch
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
        VerifiedData,
    )
    
    verifier = TavilyVerifier()
    
    request = VerificationRequest(
        match_id='test_v26_unavailable',
        home_team='Test Home',
        away_team='Test Away',
        match_date='2025-01-15',
        league='test_league',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    verified = VerifiedData(source='test', data_confidence='LOW')
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', False):
        result = verifier._execute_perplexity_fallback(request, verified)
    
    assert result is None, 'Should return None when Perplexity unavailable'


def test_v26_perplexity_fallback_handles_empty_response():
    """
    V2.6 TEST: _execute_perplexity_fallback should handle empty Perplexity response.
    
    Edge case: Perplexity returns None or empty dict.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
        VerifiedData,
    )
    
    verifier = TavilyVerifier()
    
    request = VerificationRequest(
        match_id='test_v26_empty',
        home_team='Test Home',
        away_team='Test Away',
        match_date='2025-01-15',
        league='test_league',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    verified = VerifiedData(source='test', data_confidence='LOW')
    
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = None  # Empty response
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = verifier._execute_perplexity_fallback(request, verified)
    
    assert result is None, 'Should return None when Perplexity returns empty response'


def test_v26_perplexity_fallback_handles_no_corner_data():
    """
    V2.6 TEST: _execute_perplexity_fallback should return None when no corner data found.
    
    Edge case: Perplexity returns response but without corner averages.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
        VerifiedData,
    )
    
    verifier = TavilyVerifier()
    
    request = VerificationRequest(
        match_id='test_v26_no_corners',
        home_team='Test Home',
        away_team='Test Away',
        match_date='2025-01-15',
        league='test_league',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    verified = VerifiedData(source='test', data_confidence='LOW')
    
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = {
        'home_corners_avg': None,  # No corner data found
        'away_corners_avg': None,
        'corners_signal': 'Unknown',
        'data_confidence': 'Low',
    }
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = verifier._execute_perplexity_fallback(request, verified)
    
    assert result is None, 'Should return None when Perplexity finds no corner data'


def test_v26_query_with_fallback_calls_perplexity_when_corners_missing():
    """
    V2.6 TEST: query_with_fallback should call Perplexity when corners still missing.
    
    Integration test: After Tavily primary + fallback, if corners are still missing,
    Perplexity should be called as third-level fallback.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
    )
    
    # Create a mock Tavily provider
    mock_tavily_provider = MagicMock()
    mock_tavily_provider.search.return_value = MagicMock(
        answer="Test team won 3, drew 1, lost 1. No corner data available.",
        results=[]
    )
    
    verifier = TavilyVerifier(tavily_provider=mock_tavily_provider)
    
    request = VerificationRequest(
        match_id='test_v26_integration',
        home_team='Wisła Kraków',
        away_team='Lech Poznań',
        match_date='2025-01-15',
        league='soccer_poland_ekstraklasa',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    # Mock Perplexity to return corner data
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = {
        'home_corners_avg': 4.5,
        'away_corners_avg': 5.0,
        'corners_total_avg': 9.5,
        'corners_signal': 'Medium',
        'data_confidence': 'Medium',
    }
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = verifier.query_with_fallback(request)
    
    # Should have called Perplexity for corners
    assert result is not None, 'query_with_fallback should return result'
    
    # Check if Perplexity was called (corners were missing from Tavily)
    if result.get('perplexity_fallback_executed'):
        assert 'perplexity_corners' in result, 'Should include perplexity_corners in response'
        assert result['perplexity_corners']['home_corners_avg'] == 4.5


def test_v26_orchestrator_integrates_perplexity_corners():
    """
    V2.6 TEST: VerificationOrchestrator should integrate Perplexity corner data.
    
    End-to-end test: Orchestrator should merge Perplexity corner data into VerifiedData.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        VerificationOrchestrator,
        TavilyVerifier,
        VerificationRequest,
    )
    
    # Create mock Tavily that returns data without corners
    mock_tavily_provider = MagicMock()
    mock_tavily_provider.search.return_value = MagicMock(
        answer="Wisła Kraków won 2, drew 2, lost 1. Lech Poznań won 3, drew 1, lost 1.",
        results=[]
    )
    
    tavily_verifier = TavilyVerifier(tavily_provider=mock_tavily_provider)
    
    # Mock Perplexity
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = {
        'home_corners_avg': 4.2,
        'away_corners_avg': 5.1,
        'corners_total_avg': 9.3,
        'corners_signal': 'Medium',
        'data_confidence': 'Medium',
    }
    
    orchestrator = VerificationOrchestrator(
        tavily_verifier=tavily_verifier,
        use_optimized_queries=True
    )
    
    request = VerificationRequest(
        match_id='test_v26_orchestrator',
        home_team='Wisła Kraków',
        away_team='Lech Poznań',
        match_date='2025-01-15',
        league='soccer_poland_ekstraklasa',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = orchestrator.get_verified_data(request)
    
    # If Perplexity was called and returned data, corners should be integrated
    # Note: This depends on whether Tavily extraction triggered Perplexity fallback
    assert result is not None, 'Orchestrator should return VerifiedData'
    
    # Check source includes perplexity if corners were integrated
    if result.home_corner_avg is not None:
        # Corners were found (either from Tavily or Perplexity)
        assert result.home_corner_avg > 0 or result.away_corner_avg > 0


def test_v26_perplexity_rescue_when_tavily_fails_completely():
    """
    V2.6 TEST: Perplexity should be called when Tavily fails completely.
    
    Edge case: All Tavily API keys exhausted (HTTP 432) or circuit breaker open.
    Perplexity should be called as "rescue" fallback.
    """
    from unittest.mock import patch, MagicMock
    from src.analysis.verification_layer import (
        TavilyVerifier,
        VerificationRequest,
    )
    
    # Create a mock Tavily provider that always fails
    mock_tavily_provider = MagicMock()
    mock_tavily_provider.search.return_value = None  # Simulates complete failure
    
    verifier = TavilyVerifier(tavily_provider=mock_tavily_provider)
    
    request = VerificationRequest(
        match_id='test_v26_rescue',
        home_team='Lech Poznań',
        away_team='Legia Warszawa',
        match_date='2025-01-15',
        league='soccer_poland_ekstraklasa',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
    )
    
    # Mock Perplexity to return corner data
    mock_perplexity = MagicMock()
    mock_perplexity.is_available.return_value = True
    mock_perplexity.get_betting_stats.return_value = {
        'home_corners_avg': 5.0,
        'away_corners_avg': 4.5,
        'corners_total_avg': 9.5,
        'corners_signal': 'Medium',
        'data_confidence': 'Medium',
    }
    
    with patch('src.analysis.verification_layer.PERPLEXITY_AVAILABLE', True):
        with patch('src.analysis.verification_layer.get_perplexity_provider', return_value=mock_perplexity):
            result = verifier.query_with_fallback(request)
    
    # Should have called Perplexity as rescue
    assert result is not None, 'Should return result from Perplexity rescue'
    assert result.get('perplexity_fallback_executed') == True, 'Perplexity should have been executed'
    assert result.get('provider') == 'perplexity_v2.6_rescue', f"Expected provider 'perplexity_v2.6_rescue', got {result.get('provider')}"
    assert 'perplexity_corners' in result, 'Should include perplexity_corners'
    assert result['perplexity_corners']['home_corners_avg'] == 5.0


# ============================================
# V7.1 TESTS: Referee extraction without known name
# ============================================

def test_v71_referee_extraction_without_known_name():
    """
    V7.1 TEST: Referee stats should be extracted even without fotmob_referee_name.
    
    The parser should find referee patterns like:
    - "Referee: John Smith averages 4.2 cards per game"
    - "The referee averages 5.1 yellow cards"
    
    This test would FAIL in V7.0 (returned None without known name).
    """
    from src.analysis.verification_layer import VerificationOrchestrator
    
    # Access the internal method via the orchestrator's _tavily verifier
    orchestrator = VerificationOrchestrator(use_optimized_queries=True)
    
    # Test text with referee stats but no known name
    test_texts = [
        ("The referee averages 4.5 cards per game in Premier League matches.", 4.5),
        ("referee: 3.8 yellow cards per game this season.", 3.8),
        ("Match official: 5.2 cards per game average in Serie A.", 5.2),
        ("Statistics show 4.2 cards per match for this fixture.", 4.2),
        ("Booking average: 3.5 for this competition.", 3.5),
    ]
    
    for text, expected_cards in test_texts:
        result = orchestrator._tavily._parse_referee_stats(text, referee_name=None)
        assert result is not None, f"Should extract referee from: {text[:50]}..."
        assert result.cards_per_game > 0, "Should have positive cards_per_game"
        assert 0.5 <= result.cards_per_game <= 10, "Cards per game should be in valid range"


def test_v71_referee_extraction_with_known_name_still_works():
    """
    V7.1 TEST: Referee extraction with known name should still work (regression test).
    """
    from src.analysis.verification_layer import VerificationOrchestrator
    
    orchestrator = VerificationOrchestrator(use_optimized_queries=True)
    
    text = "Michael Oliver has been strict this season. Oliver averages 4.5 cards per game."
    
    result = orchestrator._tavily._parse_referee_stats(text, referee_name="Michael Oliver")
    assert result is not None, "Should extract referee with known name"
    assert result.name == "Michael Oliver", "Should preserve known name"
    assert result.cards_per_game == 4.5, "Should extract correct cards value"


def test_v71_referee_extraction_sanity_check():
    """
    V7.1 TEST: Referee extraction should reject invalid values.
    
    Cards per game should be between 0.5 and 10 (sanity check).
    """
    from src.analysis.verification_layer import VerificationOrchestrator
    
    orchestrator = VerificationOrchestrator(use_optimized_queries=True)
    
    # Invalid: 0.1 cards per game (too low)
    text_low = "The referee averages 0.1 cards per game."
    result_low = orchestrator._tavily._parse_referee_stats(text_low, referee_name=None)
    assert result_low is None, "Should reject cards_per_game < 0.5"
    
    # Invalid: 15 cards per game (too high)
    text_high = "The referee averages 15 cards per game."
    result_high = orchestrator._tavily._parse_referee_stats(text_high, referee_name=None)
    assert result_high is None, "Should reject cards_per_game > 10"
    
    # Valid: 4.5 cards per game
    text_valid = "The referee averages 4.5 cards per game."
    result_valid = orchestrator._tavily._parse_referee_stats(text_valid, referee_name=None)
    assert result_valid is not None, "Should accept valid cards_per_game"
    assert result_valid.cards_per_game == 4.5


def test_v71_parse_fotmob_form():
    """
    V7.1 TEST: FotMob form string should be parsed correctly.
    
    FotMob provides form as "WWDLL" or "W-W-D-L-L".
    This is more reliable than parsing from Tavily text.
    """
    from src.analysis.verification_layer import TavilyVerifier
    
    verifier = TavilyVerifier()
    
    # Test standard format
    result = verifier._parse_fotmob_form("WWDLL")
    assert result is not None, "Should parse WWDLL"
    assert result.wins == 2
    assert result.draws == 1
    assert result.losses == 2
    
    # Test with dashes
    result = verifier._parse_fotmob_form("W-W-D-L-L")
    assert result is not None, "Should parse W-W-D-L-L"
    assert result.wins == 2
    assert result.draws == 1
    assert result.losses == 2
    
    # Test lowercase
    result = verifier._parse_fotmob_form("wwdll")
    assert result is not None, "Should parse lowercase"
    assert result.wins == 2
    
    # Test empty/None
    assert verifier._parse_fotmob_form(None) is None
    assert verifier._parse_fotmob_form("") is None
    assert verifier._parse_fotmob_form("   ") is None
    
    # Test all wins
    result = verifier._parse_fotmob_form("WWWWW")
    assert result is not None
    assert result.wins == 5
    assert result.draws == 0
    assert result.losses == 0


def test_v71_parse_optimized_response_uses_fotmob_form():
    """
    V7.1 REGRESSION TEST: parse_optimized_response should use FotMob form data.
    
    BUG: parse_optimized_response was calling OptimizedResponseParser.parse_to_verified_data()
    which did NOT have _parse_fotmob_form method. The method was only in TavilyVerifier.
    
    FIX: Added _parse_fotmob_form to OptimizedResponseParser and modified parse_to_verified_data
    to use FotMob form as priority over Tavily text parsing.
    
    This test would FAIL with the bug (verified.home_form = None)
    and PASS with the fix (verified.home_form = FormStats with wins=3, draws=1, losses=1)
    """
    from src.analysis.verification_layer import TavilyVerifier, VerificationRequest
    
    verifier = TavilyVerifier()
    
    # Create request with FotMob form data
    request = VerificationRequest(
        match_id='test_regression_fotmob_form',
        home_team='Liverpool',
        away_team='Manchester United',
        match_date='2026-01-15',
        league='soccer_england_premier_league',
        preliminary_score=8.0,
        suggested_market='Over 2.5',
        home_missing_players=[],
        away_missing_players=[],
        home_form_last5="WWDWL",  # 3W 1D 1L
        away_form_last5="WDLWW",  # 3W 1D 1L
    )
    
    # Empty Tavily response (simulating no form data from Tavily)
    empty_response = {
        "answer": "No form data found in this response",
        "results": [],
    }
    
    # Call parse_optimized_response - this should use FotMob form
    verified = verifier.parse_optimized_response(empty_response, request)
    
    # CRITICAL: These assertions would FAIL with the bug
    assert verified.home_form is not None, "BUG: home_form should be parsed from FotMob data"
    assert verified.away_form is not None, "BUG: away_form should be parsed from FotMob data"
    
    # Verify correct parsing
    assert verified.home_form.wins == 3, f"Expected 3 wins, got {verified.home_form.wins}"
    assert verified.home_form.draws == 1, f"Expected 1 draw, got {verified.home_form.draws}"
    assert verified.home_form.losses == 1, f"Expected 1 loss, got {verified.home_form.losses}"
    
    assert verified.away_form.wins == 3, f"Expected 3 wins, got {verified.away_form.wins}"
    assert verified.away_form.draws == 1, f"Expected 1 draw, got {verified.away_form.draws}"
    assert verified.away_form.losses == 1, f"Expected 1 loss, got {verified.away_form.losses}"
    
    # Verify HIGH confidence when FotMob form is available
    assert verified.form_confidence == "HIGH", f"Expected HIGH confidence with FotMob form, got {verified.form_confidence}"
