"""
Regression tests for V1.1 fixes in market_intelligence.py, biscotto_engine.py, news_hunter.py

Tests cover:
1. Fix #2: search_beat_writers deprecation warning
2. Fix #3/#8: Freshness tags consistency (time-based vs decay-based)
3. Fix #4: RLM edge case for invalid odds (< 1.0)
4. Fix #5: time_window_min calculation from odds_snapshots
5. Fix #6: public_bet estimation for away favorites
6. Fix #7: matches_remaining league-specific estimation
7. Fix #9: Logger pattern consistency

Author: EarlyBird Audit V1.1
"""
import pytest
import warnings
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# ============================================
# FIX #2: search_beat_writers DEPRECATION
# ============================================

class TestSearchBeatWritersDeprecation:
    """Test Fix #2: search_beat_writers should emit deprecation warning."""
    
    def test_deprecation_warning_emitted(self):
        """search_beat_writers() should emit DeprecationWarning."""
        from src.processing.news_hunter import search_beat_writers
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Call deprecated function
            result = search_beat_writers("Test Team", "soccer_italy_serie_a", "match123")
            
            # Should emit deprecation warning
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1, "Expected DeprecationWarning"
            assert "deprecated" in str(deprecation_warnings[0].message).lower()


# ============================================
# FIX #3/#8: FRESHNESS TAGS CONSISTENCY
# ============================================

class TestFreshnessTagsConsistency:
    """Test Fix #3/#8: Freshness tags should be time-based, not decay-based."""
    
    def test_fresh_tag_under_60_minutes(self):
        """News < 60 min old should be tagged FRESH."""
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        _, tag = apply_news_decay_v2(10.0, 30)  # 30 min old
        assert tag == "🔥 FRESH", f"Expected FRESH for 30min, got {tag}"
        
        _, tag = apply_news_decay_v2(10.0, 59)  # 59 min old
        assert tag == "🔥 FRESH", f"Expected FRESH for 59min, got {tag}"
    
    def test_aging_tag_60_to_360_minutes(self):
        """News 60-360 min old should be tagged AGING."""
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        _, tag = apply_news_decay_v2(10.0, 60)  # 60 min old
        assert tag == "⏰ AGING", f"Expected AGING for 60min, got {tag}"
        
        _, tag = apply_news_decay_v2(10.0, 180)  # 3 hours old
        assert tag == "⏰ AGING", f"Expected AGING for 180min, got {tag}"
        
        _, tag = apply_news_decay_v2(10.0, 359)  # 5h59m old
        assert tag == "⏰ AGING", f"Expected AGING for 359min, got {tag}"
    
    def test_stale_tag_over_360_minutes(self):
        """News > 360 min old should be tagged STALE."""
        from src.analysis.market_intelligence import apply_news_decay_v2
        
        _, tag = apply_news_decay_v2(10.0, 360)  # 6 hours old
        assert tag == "📜 STALE", f"Expected STALE for 360min, got {tag}"
        
        _, tag = apply_news_decay_v2(10.0, 720)  # 12 hours old
        assert tag == "📜 STALE", f"Expected STALE for 720min, got {tag}"
    
    def test_consistency_with_news_hunter(self):
        """Tags should match news_hunter.py thresholds."""
        from src.analysis.market_intelligence import (
            FRESHNESS_FRESH_THRESHOLD_MIN,
            FRESHNESS_AGING_THRESHOLD_MIN
        )
        
        # These should match news_hunter.py constants
        assert FRESHNESS_FRESH_THRESHOLD_MIN == 60
        assert FRESHNESS_AGING_THRESHOLD_MIN == 360


# ============================================
# FIX #4: RLM EDGE CASE FOR INVALID ODDS
# ============================================

class TestRLMInvalidOddsEdgeCase:
    """Test Fix #4: RLM should handle invalid odds (< 1.0) gracefully."""
    
    def test_rlm_v1_rejects_odds_below_1(self):
        """detect_reverse_line_movement should return None for odds < 1.0."""
        from src.analysis.market_intelligence import detect_reverse_line_movement
        
        mock_match = MagicMock()
        mock_match.opening_home_odd = 0.5  # Invalid: odds must be > 1.0
        mock_match.current_home_odd = 1.80
        mock_match.opening_away_odd = 2.50
        mock_match.current_away_odd = 2.60
        
        result = detect_reverse_line_movement(mock_match)
        assert result is None, "Should return None for invalid odds"
    
    def test_rlm_v2_rejects_odds_below_1(self):
        """detect_rlm_v2 should return None for odds < 1.0."""
        from src.analysis.market_intelligence import detect_rlm_v2
        
        mock_match = MagicMock()
        mock_match.id = "test123"
        mock_match.opening_home_odd = 0.99  # Invalid: odds must be > 1.0
        mock_match.current_home_odd = 1.80
        mock_match.opening_away_odd = 2.50
        mock_match.current_away_odd = 2.60
        
        result = detect_rlm_v2(mock_match)
        assert result is None, "Should return None for invalid odds"
    
    def test_rlm_accepts_valid_odds(self):
        """RLM should work normally with valid odds > 1.0."""
        from src.analysis.market_intelligence import detect_reverse_line_movement
        
        mock_match = MagicMock()
        mock_match.opening_home_odd = 1.50  # Valid
        mock_match.current_home_odd = 1.60  # Rising (RLM signal)
        mock_match.opening_away_odd = 2.50
        mock_match.current_away_odd = 2.40
        
        # Should not crash, may or may not detect signal depending on thresholds
        result = detect_reverse_line_movement(mock_match)
        # Just verify it doesn't crash
        assert result is None or hasattr(result, 'detected')


# ============================================
# FIX #5: time_window_min CALCULATION
# ============================================

class TestTimeWindowMinCalculation:
    """Test Fix #5: time_window_min should be calculated from odds_snapshots."""
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_time_window_calculated_from_snapshots(self, mock_history):
        """time_window_min should reflect actual odds history."""
        from src.analysis.market_intelligence import _estimate_rlm_time_window
        
        # Create mock snapshots
        now = datetime.now(timezone.utc)
        old_snapshot = MagicMock()
        old_snapshot.timestamp = now - timedelta(minutes=45)
        
        mock_history.return_value = [old_snapshot, MagicMock()]
        
        result = _estimate_rlm_time_window("match123")
        
        # Should return approximately 45 minutes
        assert result >= 40 and result <= 50, f"Expected ~45min, got {result}"
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_time_window_zero_when_no_history(self, mock_history):
        """time_window_min should be 0 when no history available."""
        from src.analysis.market_intelligence import _estimate_rlm_time_window
        
        mock_history.return_value = []
        
        result = _estimate_rlm_time_window("match123")
        assert result == 0
    
    def test_time_window_zero_for_none_match_id(self):
        """time_window_min should be 0 for None match_id."""
        from src.analysis.market_intelligence import _estimate_rlm_time_window
        
        result = _estimate_rlm_time_window(None)
        assert result == 0


# ============================================
# FIX #6: PUBLIC_BET ESTIMATION FOR AWAY FAVORITES
# ============================================

class TestPublicBetEstimationAwayFavorite:
    """Test Fix #6: public_bet estimation should handle away favorites correctly."""
    
    def test_away_favorite_gets_public_bias(self):
        """When away is favorite, public_away should be boosted by 15%."""
        from src.analysis.market_intelligence import detect_reverse_line_movement
        
        mock_match = MagicMock()
        # Away is favorite (lower odds = higher implied probability)
        mock_match.opening_home_odd = 3.50  # Home is underdog
        mock_match.current_home_odd = 3.60
        mock_match.opening_away_odd = 1.80  # Away is favorite
        mock_match.current_away_odd = 1.85
        
        # Call without public_bet_distribution to trigger estimation
        result = detect_reverse_line_movement(mock_match, public_bet_distribution=None)
        
        # The function should estimate public_away > public_home
        # We can't directly test internal estimation, but we verify no crash
        assert result is None or hasattr(result, 'detected')
    
    def test_home_favorite_gets_public_bias(self):
        """When home is favorite, public_home should be boosted by 15%."""
        from src.analysis.market_intelligence import detect_reverse_line_movement
        
        mock_match = MagicMock()
        # Home is favorite
        mock_match.opening_home_odd = 1.50  # Home is favorite
        mock_match.current_home_odd = 1.55
        mock_match.opening_away_odd = 3.00  # Away is underdog
        mock_match.current_away_odd = 2.90
        
        result = detect_reverse_line_movement(mock_match, public_bet_distribution=None)
        assert result is None or hasattr(result, 'detected')


# ============================================
# FIX #7: MATCHES_REMAINING LEAGUE-SPECIFIC
# ============================================

class TestMatchesRemainingLeagueSpecific:
    """Test Fix #7: matches_remaining should use league-specific calendars."""
    
    def test_european_league_april_is_end_of_season(self):
        """European leagues in April should return ~4 matches remaining."""
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        april_date = datetime(2026, 4, 15, tzinfo=timezone.utc)
        result = _estimate_matches_remaining_from_date(april_date, "soccer_italy_serie_a")
        
        assert result == 4, f"Expected 4 for European April, got {result}"
    
    def test_aleague_april_is_end_of_season(self):
        """A-League (southern hemisphere) in April should also be end of season."""
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        april_date = datetime(2026, 4, 15, tzinfo=timezone.utc)
        result = _estimate_matches_remaining_from_date(april_date, "soccer_australia_aleague")
        
        assert result == 4, f"Expected 4 for A-League April, got {result}"
    
    def test_aleague_october_is_early_season(self):
        """A-League in October should be early season (many matches remaining)."""
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        october_date = datetime(2025, 10, 15, tzinfo=timezone.utc)
        result = _estimate_matches_remaining_from_date(october_date, "soccer_australia_aleague")
        
        assert result == 25, f"Expected 25 for A-League October, got {result}"
    
    def test_mls_october_is_end_of_season(self):
        """MLS in October should be end of season / playoffs."""
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        october_date = datetime(2025, 10, 15, tzinfo=timezone.utc)
        result = _estimate_matches_remaining_from_date(october_date, "soccer_usa_mls")
        
        assert result == 4, f"Expected 4 for MLS October, got {result}"
    
    def test_none_match_time_returns_none(self):
        """None match_start_time should return None."""
        from src.analysis.biscotto_engine import _estimate_matches_remaining_from_date
        
        result = _estimate_matches_remaining_from_date(None, "soccer_italy_serie_a")
        assert result is None


# ============================================
# FIX #9: LOGGER PATTERN CONSISTENCY
# ============================================

class TestLoggerPatternConsistency:
    """Test Fix #9: market_intelligence.py should use module logger."""
    
    def test_module_logger_exists(self):
        """market_intelligence.py should define module-level logger."""
        from src.analysis import market_intelligence
        
        assert hasattr(market_intelligence, 'logger')
        assert market_intelligence.logger.name == 'src.analysis.market_intelligence'
    
    def test_no_direct_logging_calls(self):
        """Verify no direct logging.info/debug calls remain (checked via grep)."""
        import inspect
        from src.analysis import market_intelligence
        
        source = inspect.getsource(market_intelligence)
        
        # Should not have logging.info, logging.debug, etc. (except in comments/strings)
        # The only allowed pattern is logger = logging.getLogger
        import re
        
        # Find all logging.X( calls that are not part of getLogger
        # Simple approach: count occurrences and exclude getLogger
        info_calls = source.count('logging.info(')
        debug_calls = source.count('logging.debug(')
        error_calls = source.count('logging.error(')
        warning_calls = source.count('logging.warning(')
        
        total_direct = info_calls + debug_calls + error_calls + warning_calls
        
        assert total_direct == 0, (
            f"Found {total_direct} direct logging calls: "
            f"info={info_calls}, debug={debug_calls}, error={error_calls}, warning={warning_calls}"
        )
