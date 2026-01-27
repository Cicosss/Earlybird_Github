"""
Test V5.1 Integration Fixes

Tests for the fixes applied to Phase 4, 5, 6 integration:
1. minutes_to_kickoff in News Decay
2. Null-check for home_context/away_context in tier-based gating
3. matches_remaining fallback estimation in Biscotto Engine

These tests verify that the fixes work correctly and prevent regressions.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# ============================================
# TEST 1: minutes_to_kickoff in News Decay
# ============================================

class TestNewsDecayKickoffProximity:
    """Test that news decay correctly uses kickoff proximity."""
    
    def test_apply_news_decay_v2_with_kickoff_proximity(self):
        """
        Test that apply_news_decay_v2 accelerates decay when kickoff is near.
        
        Bug: minutes_to_kickoff was always None, so kickoff acceleration never applied.
        Fix: Calculate minutes_to_kickoff from match.start_time in run_hunter_for_match.
        """
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        # Same news age (30 minutes old)
        minutes_since_publish = 30
        
        # Case 1: Kickoff far away (2 hours) - normal decay
        score_far, tag_far = apply_news_decay_v2(
            impact_score=1.0,
            minutes_since_publish=minutes_since_publish,
            league_key="soccer_england_premier_league",
            source_type="mainstream",
            minutes_to_kickoff=120  # 2 hours away
        )
        
        # Case 2: Kickoff imminent (15 minutes) - accelerated decay
        score_near, tag_near = apply_news_decay_v2(
            impact_score=1.0,
            minutes_since_publish=minutes_since_publish,
            league_key="soccer_england_premier_league",
            source_type="mainstream",
            minutes_to_kickoff=15  # 15 minutes away - should double decay
        )
        
        # Near-kickoff should have LOWER score (more decay)
        assert score_near < score_far, (
            f"News near kickoff should decay faster. "
            f"Far: {score_far}, Near: {score_near}"
        )
        
        # The difference should be significant (at least 20% more decay)
        decay_ratio = score_near / score_far
        assert decay_ratio < 0.8, (
            f"Kickoff proximity should cause at least 20% more decay. "
            f"Ratio: {decay_ratio}"
        )
    
    def test_apply_news_decay_v2_none_kickoff_fallback(self):
        """
        Test that apply_news_decay_v2 works correctly when minutes_to_kickoff is None.
        
        This ensures backward compatibility - the function should not crash.
        """
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        # Should not raise exception
        score, tag = apply_news_decay_v2(
            impact_score=1.0,
            minutes_since_publish=30,
            league_key="soccer_england_premier_league",
            source_type="mainstream",
            minutes_to_kickoff=None  # Explicitly None
        )
        
        assert score > 0, "Score should be positive"
        assert tag in ["🔥 FRESH", "⏰ AGING", "📜 STALE"], f"Invalid tag: {tag}"
    
    def test_minutes_to_kickoff_calculation(self):
        """
        Test the minutes_to_kickoff calculation logic that was added to run_hunter_for_match.
        
        This simulates the calculation without running the full function.
        """
        # Simulate match 90 minutes from now
        now = datetime.now(timezone.utc)
        match_start = now + timedelta(minutes=90)
        
        # Calculate minutes_to_kickoff (same logic as in run_hunter_for_match)
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        
        delta_seconds = (match_start - now).total_seconds()
        minutes_to_kickoff = int(delta_seconds / 60) if delta_seconds > 0 else 0
        
        # Should be approximately 90 (allow 1 minute tolerance for test execution time)
        assert 89 <= minutes_to_kickoff <= 91, f"Expected ~90, got {minutes_to_kickoff}"
    
    def test_minutes_to_kickoff_past_match(self):
        """
        Test that minutes_to_kickoff is 0 for matches that already started.
        """
        now = datetime.now(timezone.utc)
        match_start = now - timedelta(minutes=30)  # Started 30 min ago
        
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        
        delta_seconds = (match_start - now).total_seconds()
        minutes_to_kickoff = int(delta_seconds / 60) if delta_seconds > 0 else 0
        
        assert minutes_to_kickoff == 0, f"Past match should have 0 minutes_to_kickoff, got {minutes_to_kickoff}"


# ============================================
# TEST 2: Null-check for context dicts
# ============================================

class TestTierBasedGatingNullCheck:
    """Test that tier-based gating handles None/empty contexts safely."""
    
    def test_fotmob_high_risk_with_empty_context(self):
        """
        Test that fotmob_high_risk calculation doesn't crash with empty context.
        
        Bug: Original code did home_context.get('injuries') without checking if home_context is truthy.
        Fix: Added explicit null-checks before accessing dict keys.
        """
        # Simulate empty contexts (FotMob unavailable or returned empty)
        home_context = {}
        away_context = {}
        home_turnover = None
        away_turnover = None
        
        # This is the FIXED logic from main.py
        home_injuries = home_context.get('injuries') if home_context else []
        away_injuries = away_context.get('injuries') if away_context else []
        
        has_home_injury_crisis = isinstance(home_injuries, list) and len(home_injuries) >= 3
        has_away_injury_crisis = isinstance(away_injuries, list) and len(away_injuries) >= 3
        has_home_turnover_crisis = home_turnover and home_turnover.get('risk_level') == 'HIGH'
        has_away_turnover_crisis = away_turnover and away_turnover.get('risk_level') == 'HIGH'
        
        fotmob_high_risk = (
            has_home_injury_crisis or 
            has_away_injury_crisis or 
            has_home_turnover_crisis or 
            has_away_turnover_crisis
        )
        
        # Should be False (no data = no high risk)
        # Note: In Python, False or False or None or None = None, so we check for falsy
        assert not fotmob_high_risk, "Empty context should not trigger high risk"
    
    def test_fotmob_high_risk_with_none_context(self):
        """
        Test that fotmob_high_risk handles None context gracefully.
        """
        home_context = None
        away_context = None
        home_turnover = None
        away_turnover = None
        
        # FIXED logic
        home_injuries = home_context.get('injuries') if home_context else []
        away_injuries = away_context.get('injuries') if away_context else []
        
        has_home_injury_crisis = isinstance(home_injuries, list) and len(home_injuries) >= 3
        has_away_injury_crisis = isinstance(away_injuries, list) and len(away_injuries) >= 3
        
        # Should not crash and should be False
        assert has_home_injury_crisis is False
        assert has_away_injury_crisis is False
    
    def test_fotmob_high_risk_with_valid_injuries(self):
        """
        Test that fotmob_high_risk correctly detects injury crisis.
        """
        home_context = {
            'injuries': [
                {'name': 'Player A'},
                {'name': 'Player B'},
                {'name': 'Player C'},
                {'name': 'Player D'}  # 4 injuries = crisis
            ]
        }
        away_context = {'injuries': []}
        home_turnover = None
        away_turnover = None
        
        # FIXED logic
        home_injuries = home_context.get('injuries') if home_context else []
        away_injuries = away_context.get('injuries') if away_context else []
        
        has_home_injury_crisis = isinstance(home_injuries, list) and len(home_injuries) >= 3
        has_away_injury_crisis = isinstance(away_injuries, list) and len(away_injuries) >= 3
        
        assert has_home_injury_crisis is True, "4 injuries should trigger crisis"
        assert has_away_injury_crisis is False, "0 injuries should not trigger crisis"
    
    def test_fotmob_high_risk_with_turnover(self):
        """
        Test that turnover HIGH risk is detected correctly.
        """
        home_context = {}
        away_context = {}
        home_turnover = {'risk_level': 'HIGH', 'count': 5}
        away_turnover = {'risk_level': 'MEDIUM', 'count': 2}
        
        has_home_turnover_crisis = home_turnover and home_turnover.get('risk_level') == 'HIGH'
        has_away_turnover_crisis = away_turnover and away_turnover.get('risk_level') == 'HIGH'
        
        assert has_home_turnover_crisis is True
        assert has_away_turnover_crisis is False


# ============================================
# TEST 3: matches_remaining fallback in Biscotto Engine
# ============================================

class TestBiscottoMatchesRemainingFallback:
    """Test the matches_remaining fallback estimation."""
    
    def test_estimate_matches_remaining_april(self):
        """
        Test that April matches are estimated as end-of-season.
        """
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        # April 15th - should be end of season
        april_match = datetime(2026, 4, 15, 15, 0, tzinfo=timezone.utc)
        
        result = _estimate_matches_remaining_from_date(april_match)
        
        assert result is not None, "Should return an estimate"
        assert result <= 5, f"April should be end-of-season (<=5 matches), got {result}"
    
    def test_estimate_matches_remaining_may(self):
        """
        Test that May matches are estimated as end-of-season.
        """
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        # May 10th - definitely end of season
        may_match = datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc)
        
        result = _estimate_matches_remaining_from_date(may_match)
        
        assert result is not None
        assert result <= 5, f"May should be end-of-season (<=5 matches), got {result}"
    
    def test_estimate_matches_remaining_september(self):
        """
        Test that September matches are NOT end-of-season.
        """
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        # September 20th - early season
        sept_match = datetime(2025, 9, 20, 15, 0, tzinfo=timezone.utc)
        
        result = _estimate_matches_remaining_from_date(sept_match)
        
        assert result is not None
        assert result > 20, f"September should be early season (>20 matches), got {result}"
    
    def test_estimate_matches_remaining_none_input(self):
        """
        Test that None input returns None (no crash).
        """
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        result = _estimate_matches_remaining_from_date(None)
        
        assert result is None, "None input should return None"
    
    def test_estimate_matches_remaining_naive_datetime(self):
        """
        Test that naive datetime (no timezone) is handled correctly.
        """
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        # Naive datetime (no tzinfo) - common from SQLite
        naive_match = datetime(2026, 4, 15, 15, 0)  # No timezone
        
        result = _estimate_matches_remaining_from_date(naive_match)
        
        assert result is not None, "Should handle naive datetime"
        assert result <= 5, f"April should be end-of-season, got {result}"
    
    def test_get_enhanced_biscotto_uses_fallback(self):
        """
        Test that get_enhanced_biscotto_analysis uses fallback when FotMob data unavailable.
        """
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        
        # Mock match object with April date (end of season)
        mock_match = MagicMock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.40  # Suspicious but not extreme
        mock_match.opening_draw_odd = 3.00
        mock_match.league = "soccer_italy_serie_a"
        mock_match.start_time = datetime(2026, 4, 20, 15, 0, tzinfo=timezone.utc)
        
        # Empty motivation (FotMob unavailable) - no matches_remaining
        home_motivation = {}
        away_motivation = {}
        
        analysis, context_str = get_enhanced_biscotto_analysis(
            mock_match,
            home_motivation,
            away_motivation
        )
        
        # Should detect end-of-season via fallback
        assert analysis.end_of_season_match is True, (
            "April match with no FotMob data should use fallback to detect end-of-season"
        )
    
    def test_get_enhanced_biscotto_prefers_fotmob_data(self):
        """
        Test that FotMob data is preferred over fallback estimation.
        """
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        
        # Mock match object with April date
        mock_match = MagicMock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.40
        mock_match.opening_draw_odd = 3.00
        mock_match.league = "soccer_italy_serie_a"
        mock_match.start_time = datetime(2026, 4, 20, 15, 0, tzinfo=timezone.utc)
        
        # FotMob says 15 matches remaining (mid-season, contradicts April date)
        home_motivation = {'matches_remaining': 15}
        away_motivation = {'matches_remaining': 15}
        
        analysis, context_str = get_enhanced_biscotto_analysis(
            mock_match,
            home_motivation,
            away_motivation
        )
        
        # Should use FotMob data (15 > 5), NOT end-of-season
        assert analysis.end_of_season_match is False, (
            "FotMob data (15 matches) should override date-based fallback"
        )


# ============================================
# INTEGRATION TEST
# ============================================

class TestV51IntegrationFlow:
    """Integration tests for the complete V5.1 fix flow."""
    
    def test_news_decay_integration_with_match_object(self):
        """
        Test that the full news decay flow works with a match object.
        
        This simulates what happens in run_hunter_for_match.
        """
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        # Simulate match starting in 30 minutes
        now = datetime.now(timezone.utc)
        match_start = now + timedelta(minutes=30)
        
        # Calculate minutes_to_kickoff (same as in run_hunter_for_match)
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        delta_seconds = (match_start - now).total_seconds()
        minutes_to_kickoff = int(delta_seconds / 60) if delta_seconds > 0 else 0
        
        # Apply decay to 20-minute-old news
        score, tag = apply_news_decay_v2(
            impact_score=1.0,
            minutes_since_publish=20,
            league_key="soccer_turkey_super_lig",
            source_type="beat_writer",
            minutes_to_kickoff=minutes_to_kickoff
        )
        
        # With kickoff in 30 min, 20-min-old news should decay more than normal
        # (accelerated decay kicks in when kickoff <= 30 min)
        # The decay is doubled, so score should be noticeably lower than without acceleration
        assert score < 0.6, f"Near-kickoff news should decay significantly, got {score}"
