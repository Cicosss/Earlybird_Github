"""
Regression tests for bug fixes in market_intelligence.py and biscotto_engine.py

These tests verify that the bugs identified in the code review are fixed
and won't regress in future changes.

Bug fixes covered:
1. detect_odds_pattern: current_odd <= 0 not handled
2. detect_rlm_v2: confidence LOW was unreachable
3. detect_steam_move: now_naive variable was unused (cleanup)
4. calculate_news_freshness_multiplier: import re moved to module level
"""
import pytest
from unittest.mock import MagicMock


class TestDetectOddsPatternFixes:
    """Tests for detect_odds_pattern edge case fixes."""
    
    def test_current_odd_zero_returns_stable(self):
        """
        BUG FIX: current_odd <= 0 should return STABLE, not cause invalid calculation.
        
        Before fix: Only opening_odd <= 0 was checked, current_odd <= 0 would
        cause invalid drop_pct calculation.
        """
        from src.analysis.biscotto_engine import detect_odds_pattern, BiscottoPattern
        
        # current_odd = 0 should be handled gracefully
        result = detect_odds_pattern(opening_odd=3.50, current_odd=0)
        assert result == BiscottoPattern.STABLE
        
        # current_odd negative should also be handled
        result = detect_odds_pattern(opening_odd=3.50, current_odd=-1.0)
        assert result == BiscottoPattern.STABLE
    
    def test_both_odds_invalid_returns_stable(self):
        """Both odds invalid should return STABLE."""
        from src.analysis.biscotto_engine import detect_odds_pattern, BiscottoPattern
        
        result = detect_odds_pattern(opening_odd=0, current_odd=0)
        assert result == BiscottoPattern.STABLE
        
        result = detect_odds_pattern(opening_odd=-1, current_odd=-1)
        assert result == BiscottoPattern.STABLE
    
    def test_valid_odds_still_work(self):
        """Valid odds should still produce correct patterns."""
        from src.analysis.biscotto_engine import detect_odds_pattern, BiscottoPattern
        
        # Significant drop (DRIFT pattern)
        result = detect_odds_pattern(opening_odd=3.50, current_odd=3.00)
        assert result in [BiscottoPattern.DRIFT, BiscottoPattern.CRASH]
        
        # No significant movement (STABLE)
        result = detect_odds_pattern(opening_odd=3.50, current_odd=3.45)
        assert result == BiscottoPattern.STABLE


class TestRLMV2ConfidenceFixes:
    """Tests for detect_rlm_v2 confidence level fixes."""
    
    def create_mock_match(self, opening_home, current_home, opening_away, current_away):
        """Helper to create mock match object."""
        match = MagicMock()
        match.opening_home_odd = opening_home
        match.current_home_odd = current_home
        match.opening_away_odd = opening_away
        match.current_away_odd = current_away
        match.id = "test_match"
        return match
    
    def test_confidence_low_is_reachable(self):
        """
        BUG FIX: confidence LOW should be reachable when movement is barely above threshold.
        
        Before fix: With default threshold 3%, the condition `movement >= 3` for MEDIUM
        was always true when we entered the if block, making LOW unreachable.
        
        After fix: LOW is assigned when movement is within 1% of the threshold.
        """
        from src.analysis.market_intelligence import detect_rlm_v2
        
        # Movement exactly at threshold (3.0%) - should be LOW
        match = self.create_mock_match(
            opening_home=2.00, current_home=2.06,  # +3.0% exactly
            opening_away=2.00, current_away=1.94
        )
        public = {'home': 0.70, 'away': 0.30}
        
        result = detect_rlm_v2(match, public)
        
        assert result is not None
        assert result.detected
        assert result.confidence == 'LOW', f"Expected LOW, got {result.confidence}"
    
    def test_confidence_medium_still_works(self):
        """MEDIUM confidence should still work for movements >= threshold + 1%."""
        from src.analysis.market_intelligence import detect_rlm_v2
        
        # Movement at 4.5% (above 3% + 1% = 4%)
        match = self.create_mock_match(
            opening_home=2.00, current_home=2.09,  # +4.5%
            opening_away=2.00, current_away=1.91
        )
        public = {'home': 0.70, 'away': 0.30}
        
        result = detect_rlm_v2(match, public)
        
        assert result is not None
        assert result.confidence == 'MEDIUM'
    
    def test_confidence_high_still_works(self):
        """HIGH confidence should still work for movements >= 5%."""
        from src.analysis.market_intelligence import detect_rlm_v2
        
        # Movement at 6%
        match = self.create_mock_match(
            opening_home=2.00, current_home=2.12,  # +6%
            opening_away=2.00, current_away=1.88
        )
        public = {'home': 0.70, 'away': 0.30}
        
        result = detect_rlm_v2(match, public)
        
        assert result is not None
        assert result.confidence == 'HIGH'
        assert result.high_potential is True


class TestImportOptimization:
    """Tests to verify import optimizations don't break functionality."""
    
    def test_regex_parsing_still_works(self):
        """
        Verify that moving 'import re' to module level doesn't break regex parsing.
        """
        from src.analysis.market_intelligence import calculate_news_freshness_multiplier
        
        # Test various date formats that use regex
        multiplier, minutes = calculate_news_freshness_multiplier("15 minutes ago")
        assert minutes == 15
        
        multiplier, minutes = calculate_news_freshness_multiplier("2 hours ago")
        assert minutes == 120
        
        multiplier, minutes = calculate_news_freshness_multiplier("3 days ago")
        assert minutes == 3 * 24 * 60


class TestSteamMoveCleanup:
    """Tests to verify steam move detection still works after cleanup."""
    
    def test_steam_move_timezone_handling(self):
        """
        Verify that removing unused now_naive variable doesn't break timezone handling.
        
        The fix removed the unused now_naive variable. This test ensures
        timezone-aware comparisons still work correctly.
        """
        from src.analysis.market_intelligence import detect_steam_move
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        
        # Create mock snapshots with naive timestamps (as stored in DB)
        # Need at least 2 snapshots for comparison
        old_snapshot = MagicMock()
        old_snapshot.timestamp = (now - timedelta(minutes=10)).replace(tzinfo=None)
        old_snapshot.home_odd = 2.00
        old_snapshot.draw_odd = 3.50
        old_snapshot.away_odd = 3.80
        
        recent_snapshot = MagicMock()
        recent_snapshot.timestamp = (now - timedelta(minutes=5)).replace(tzinfo=None)
        recent_snapshot.home_odd = 1.95
        recent_snapshot.draw_odd = 3.50
        recent_snapshot.away_odd = 3.80
        
        with patch('src.analysis.market_intelligence.get_odds_history') as mock_history:
            mock_history.return_value = [old_snapshot, recent_snapshot]
            
            # Current odds show 6% drop from 10-min-ago snapshot
            current_odds = {'home': 1.88, 'draw': 3.50, 'away': 3.80}
            
            result = detect_steam_move('match123', current_odds)
            
            # Should detect steam move without timezone errors
            assert result is not None
            assert result.detected
            assert result.market == 'HOME'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
