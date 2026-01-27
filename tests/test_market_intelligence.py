"""
Tests for Market Intelligence Module

Tests cover:
1. News Decay - Exponential decay calculation
2. Reverse Line Movement - Detection logic
3. Steam Move - Time-window based detection
"""
import pytest
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Import the module under test
from src.analysis.market_intelligence import (
    apply_news_decay,
    calculate_news_freshness_multiplier,
    detect_reverse_line_movement,
    detect_steam_move,
    ReverseLineSignal,
    SteamMoveSignal,
    NEWS_DECAY_LAMBDA,
    RLM_PUBLIC_THRESHOLD,
    STEAM_MOVE_THRESHOLD_PCT
)


class TestNewsDecay:
    """Tests for news decay functionality."""
    
    def test_decay_zero_minutes_returns_original(self):
        """News just published should have full impact."""
        score = 10.0
        result = apply_news_decay(score, minutes_since_publish=0)
        assert result == score
    
    def test_decay_negative_minutes_returns_original(self):
        """Edge case: negative time should return original."""
        score = 8.0
        result = apply_news_decay(score, minutes_since_publish=-5)
        assert result == score
    
    def test_decay_reduces_over_time(self):
        """Impact should decrease as news ages."""
        score = 10.0
        result_5min = apply_news_decay(score, 5)
        result_30min = apply_news_decay(score, 30)
        result_60min = apply_news_decay(score, 60)
        
        assert result_5min > result_30min > result_60min
        assert result_5min < score  # Should be less than original
    
    def test_decay_formula_correctness(self):
        """Verify exponential decay formula: Impact_t = Impact_0 * e^(-λt)"""
        score = 10.0
        minutes = 20
        lambda_val = NEWS_DECAY_LAMBDA
        
        expected = score * math.exp(-lambda_val * minutes)
        result = apply_news_decay(score, minutes, lambda_val)
        
        assert abs(result - expected) < 0.001
    
    def test_decay_zero_score_returns_zero(self):
        """Zero impact should stay zero."""
        result = apply_news_decay(0.0, 30)
        assert result == 0.0
    
    def test_decay_very_old_news_has_minimal_impact(self):
        """News older than 24h should have ~1% impact."""
        score = 10.0
        very_old_minutes = 25 * 60  # 25 hours
        result = apply_news_decay(score, very_old_minutes)
        
        # Should be capped at 1% minimum
        assert result == pytest.approx(score * 0.01, rel=0.1)
    
    def test_decay_custom_lambda(self):
        """Custom decay rate should work correctly."""
        score = 10.0
        # Faster decay
        fast_result = apply_news_decay(score, 10, lambda_decay=0.1)
        # Slower decay
        slow_result = apply_news_decay(score, 10, lambda_decay=0.02)
        
        assert fast_result < slow_result


class TestNewsFreshnessMultiplier:
    """Tests for news date parsing and freshness calculation."""
    
    def test_just_now_is_fresh(self):
        """'Just now' should have high freshness."""
        multiplier, minutes = calculate_news_freshness_multiplier("just now")
        assert minutes <= 5
        assert multiplier > 0.9
    
    def test_minutes_ago_parsing(self):
        """'X minutes ago' should parse correctly."""
        multiplier, minutes = calculate_news_freshness_multiplier("15 minutes ago")
        assert minutes == 15
    
    def test_hours_ago_parsing(self):
        """'X hours ago' should parse correctly."""
        multiplier, minutes = calculate_news_freshness_multiplier("2 hours ago")
        assert minutes == 120
    
    def test_days_ago_parsing(self):
        """'X days ago' should parse correctly."""
        multiplier, minutes = calculate_news_freshness_multiplier("1 day ago")
        assert minutes == 24 * 60
    
    def test_none_date_uses_default(self):
        """None date should use default assumption."""
        multiplier, minutes = calculate_news_freshness_multiplier(None)
        assert minutes == 30  # Default
        assert 0 < multiplier < 1
    
    def test_empty_string_uses_default(self):
        """Empty string should use default."""
        multiplier, minutes = calculate_news_freshness_multiplier("")
        assert minutes == 30


class TestReverseLineMovement:
    """Tests for Reverse Line Movement detection."""
    
    def create_mock_match(self, opening_home, current_home, opening_away, current_away):
        """Helper to create mock match object."""
        match = MagicMock()
        match.opening_home_odd = opening_home
        match.current_home_odd = current_home
        match.opening_away_odd = opening_away
        match.current_away_odd = current_away
        return match
    
    def test_no_rlm_when_odds_drop_with_public(self):
        """No RLM when odds move WITH public money."""
        # Public on HOME (favorite), HOME odds dropping = normal
        match = self.create_mock_match(
            opening_home=1.80, current_home=1.70,  # Dropping
            opening_away=2.20, current_away=2.30
        )
        public = {'home': 0.70, 'away': 0.30}
        
        result = detect_reverse_line_movement(match, public)
        assert result is None or not result.detected
    
    def test_rlm_detected_when_odds_rise_against_public(self):
        """RLM detected when odds rise despite heavy public action."""
        # 70% public on HOME, but HOME odds RISING = sharp on AWAY
        match = self.create_mock_match(
            opening_home=1.80, current_home=1.90,  # Rising 5.5%
            opening_away=2.20, current_away=2.10
        )
        public = {'home': 0.70, 'away': 0.30}
        
        result = detect_reverse_line_movement(match, public)
        
        assert result is not None
        assert result.detected
        assert result.sharp_side == 'AWAY'
        assert result.public_side == 'HOME'
    
    def test_rlm_requires_threshold_public(self):
        """RLM requires public threshold to be met."""
        # Only 50% on HOME - not enough for RLM
        match = self.create_mock_match(
            opening_home=1.80, current_home=1.90,
            opening_away=2.20, current_away=2.10
        )
        public = {'home': 0.50, 'away': 0.50}
        
        result = detect_reverse_line_movement(match, public)
        assert result is None or not result.detected
    
    def test_rlm_none_match_returns_none(self):
        """None match should return None."""
        result = detect_reverse_line_movement(None, {'home': 0.7, 'away': 0.3})
        assert result is None
    
    def test_rlm_missing_odds_returns_none(self):
        """Missing odds should return None."""
        match = self.create_mock_match(
            opening_home=None, current_home=1.90,
            opening_away=2.20, current_away=2.10
        )
        result = detect_reverse_line_movement(match, {'home': 0.7, 'away': 0.3})
        assert result is None
    
    def test_rlm_estimates_public_when_not_provided(self):
        """Should estimate public distribution from odds when not provided."""
        # Strong favorite (1.50) should attract public money
        match = self.create_mock_match(
            opening_home=1.50, current_home=1.60,  # Rising despite being favorite
            opening_away=3.00, current_away=2.80
        )
        
        # Don't provide public distribution - let it estimate
        result = detect_reverse_line_movement(match, None)
        
        # Should detect RLM since favorite odds are rising
        # (estimation assumes public bets on favorites)
        assert result is not None
        assert result.detected


class TestSteamMove:
    """Tests for Steam Move detection."""
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_steam_move_detected_on_rapid_drop(self, mock_history):
        """Steam move detected when odds drop rapidly."""
        # Create mock snapshots - need at least 2 for comparison
        now = datetime.now(timezone.utc)
        
        # Older snapshot (baseline)
        old_snapshot = MagicMock()
        old_snapshot.timestamp = (now - timedelta(minutes=10)).replace(tzinfo=None)
        old_snapshot.home_odd = 2.00
        old_snapshot.draw_odd = 3.50
        old_snapshot.away_odd = 3.80
        
        # More recent snapshot (still shows high odds)
        recent_snapshot = MagicMock()
        recent_snapshot.timestamp = (now - timedelta(minutes=5)).replace(tzinfo=None)
        recent_snapshot.home_odd = 1.95
        recent_snapshot.draw_odd = 3.50
        recent_snapshot.away_odd = 3.80
        
        mock_history.return_value = [old_snapshot, recent_snapshot]
        
        # Current odds show 6% drop on HOME from the 10-min-ago snapshot
        current_odds = {'home': 1.88, 'draw': 3.50, 'away': 3.80}
        
        result = detect_steam_move('match123', current_odds)
        
        assert result is not None
        assert result.detected
        assert result.market == 'HOME'
        assert result.drop_pct >= 5.0
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_no_steam_move_on_slow_drop(self, mock_history):
        """No steam move when drop is outside time window."""
        # Snapshot from 2 hours ago (outside 15 min window)
        now = datetime.now(timezone.utc)
        old_snapshot = MagicMock()
        old_snapshot.timestamp = (now - timedelta(hours=2)).replace(tzinfo=None)
        old_snapshot.home_odd = 2.00
        old_snapshot.draw_odd = 3.50
        old_snapshot.away_odd = 3.80
        
        mock_history.return_value = [old_snapshot]
        
        current_odds = {'home': 1.80, 'draw': 3.50, 'away': 3.80}
        
        result = detect_steam_move('match123', current_odds)
        
        # Should not detect because snapshot is too old
        assert result is None or not result.detected
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_no_steam_move_on_small_drop(self, mock_history):
        """No steam move when drop is below threshold."""
        now = datetime.now(timezone.utc)
        old_snapshot = MagicMock()
        old_snapshot.timestamp = (now - timedelta(minutes=5)).replace(tzinfo=None)
        old_snapshot.home_odd = 2.00
        old_snapshot.draw_odd = 3.50
        old_snapshot.away_odd = 3.80
        
        mock_history.return_value = [old_snapshot]
        
        # Only 2% drop - below 5% threshold
        current_odds = {'home': 1.96, 'draw': 3.50, 'away': 3.80}
        
        result = detect_steam_move('match123', current_odds)
        
        assert result is None or not result.detected
    
    @patch('src.analysis.market_intelligence.get_odds_history')
    def test_steam_move_insufficient_history(self, mock_history):
        """No steam move when insufficient history."""
        mock_history.return_value = []  # No history
        
        current_odds = {'home': 1.80, 'draw': 3.50, 'away': 3.80}
        result = detect_steam_move('match123', current_odds)
        
        assert result is None
    
    def test_steam_move_none_match_id(self):
        """None match_id should return None."""
        result = detect_steam_move(None, {'home': 1.80})
        assert result is None
    
    def test_steam_move_empty_odds(self):
        """Empty odds should return None."""
        result = detect_steam_move('match123', {})
        assert result is None


class TestEdgeCases:
    """Edge case tests for robustness."""
    
    def test_decay_with_negative_score(self):
        """Negative score should return 0."""
        result = apply_news_decay(-5.0, 10)
        assert result == 0.0
    
    def test_rlm_with_zero_odds(self):
        """Zero odds should be handled gracefully."""
        match = MagicMock()
        match.opening_home_odd = 0
        match.current_home_odd = 1.90
        match.opening_away_odd = 2.20
        match.current_away_odd = 2.10
        
        result = detect_reverse_line_movement(match, {'home': 0.7, 'away': 0.3})
        # Should handle gracefully (no division by zero)
        assert result is None or isinstance(result, ReverseLineSignal)
    
    def test_freshness_with_malformed_date(self):
        """Malformed date should use default."""
        multiplier, minutes = calculate_news_freshness_multiplier("not a date at all xyz")
        assert minutes == 30  # Default fallback
        assert 0 < multiplier <= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
