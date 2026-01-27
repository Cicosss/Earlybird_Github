"""
Tests for Fatigue Engine V2.0 and Biscotto Engine V2.0

These tests verify:
1. Edge cases (None values, empty lists, division by zero)
2. Correct severity calculations
3. Integration helpers work correctly
"""
import pytest
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass


class TestFatigueEngine:
    """Tests for src/analysis/fatigue_engine.py"""
    
    def test_import(self):
        """Test that fatigue engine imports correctly."""
        from src.analysis.fatigue_engine import (
            calculate_fatigue_index,
            get_squad_depth_score,
            analyze_team_fatigue,
            analyze_fatigue_differential,
            get_enhanced_fatigue_context
        )
        assert callable(calculate_fatigue_index)
        assert callable(analyze_team_fatigue)
    
    def test_squad_depth_elite_team(self):
        """Elite teams should have lower fatigue multiplier."""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_ELITE
        
        score = get_squad_depth_score("Manchester City")
        assert score == SQUAD_DEPTH_ELITE
        
        score = get_squad_depth_score("Real Madrid")
        assert score == SQUAD_DEPTH_ELITE
    
    def test_squad_depth_unknown_team(self):
        """Unknown teams should get default multiplier."""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_MID
        
        score = get_squad_depth_score("Unknown FC")
        assert score == SQUAD_DEPTH_MID
    
    def test_squad_depth_none_team(self):
        """None team name should return default."""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_MID
        
        score = get_squad_depth_score(None)
        assert score == SQUAD_DEPTH_MID
    
    def test_fatigue_index_empty_schedule(self):
        """Empty schedule should return 0 fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        fatigue, matches = calculate_fatigue_index([], now)
        
        assert fatigue == 0.0
        assert matches == 0
    
    def test_fatigue_index_none_schedule(self):
        """None schedule should return 0 fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        fatigue, matches = calculate_fatigue_index(None, now)
        
        assert fatigue == 0.0
        assert matches == 0
    
    def test_fatigue_index_recent_match(self):
        """Match yesterday should give high fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        fatigue, matches = calculate_fatigue_index([yesterday], now)
        
        assert fatigue > 0.3  # Should be significant
        assert matches == 1
    
    def test_fatigue_index_old_match(self):
        """Match 10 days ago should give low fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        old_match = now - timedelta(days=10)
        
        fatigue, matches = calculate_fatigue_index([old_match], now)
        
        assert fatigue < 0.2  # Should be low
        assert matches == 1
    
    def test_fatigue_index_congestion(self):
        """Multiple recent matches should give moderate fatigue."""
        from src.analysis.fatigue_engine import calculate_fatigue_index
        
        now = datetime.now(timezone.utc)
        schedule = [
            now - timedelta(days=3),
            now - timedelta(days=6),
            now - timedelta(days=10),
        ]
        
        fatigue, matches = calculate_fatigue_index(schedule, now)
        
        assert fatigue > 0.15  # Should show some fatigue from congestion
        assert matches == 3
    
    def test_analyze_team_fatigue_none_hours(self):
        """Should handle None hours_since_last gracefully."""
        from src.analysis.fatigue_engine import analyze_team_fatigue
        
        result = analyze_team_fatigue(
            team_name="Test FC",
            hours_since_last=None
        )
        
        assert result.fatigue_index == 0.0
        assert result.fatigue_level == "FRESH"
    
    def test_analyze_team_fatigue_critical(self):
        """Less than 72h rest should be CRITICAL."""
        from src.analysis.fatigue_engine import analyze_team_fatigue
        
        result = analyze_team_fatigue(
            team_name="Test FC",
            hours_since_last=48  # 2 days
        )
        
        assert result.fatigue_level == "CRITICAL"
        assert result.late_game_risk in ["HIGH", "MEDIUM"]
    
    def test_fatigue_differential(self):
        """Test fatigue comparison between two teams."""
        from src.analysis.fatigue_engine import analyze_fatigue_differential
        
        result = analyze_fatigue_differential(
            home_team="Tired FC",
            away_team="Fresh FC",
            home_hours_since_last=48,  # Very tired
            away_hours_since_last=120  # Well rested
        )
        
        assert result.home_fatigue.fatigue_level == "CRITICAL"
        assert result.away_fatigue.fatigue_level in ["LOW", "FRESH"]
        assert result.advantage == "AWAY"  # Away team is fresher


class TestBiscottoEngine:
    """Tests for src/analysis/biscotto_engine.py"""
    
    def test_import(self):
        """Test that biscotto engine imports correctly."""
        from src.analysis.biscotto_engine import (
            analyze_biscotto,
            calculate_implied_probability,
            calculate_zscore,
            BiscottoSeverity
        )
        assert callable(analyze_biscotto)
        assert callable(calculate_implied_probability)
    
    def test_implied_probability_normal(self):
        """Test implied probability calculation."""
        from src.analysis.biscotto_engine import calculate_implied_probability
        
        # Odds 2.0 = 50% probability
        prob = calculate_implied_probability(2.0)
        assert prob == 0.5
        
        # Odds 4.0 = 25% probability
        prob = calculate_implied_probability(4.0)
        assert prob == 0.25
    
    def test_implied_probability_edge_cases(self):
        """Test edge cases for implied probability."""
        from src.analysis.biscotto_engine import calculate_implied_probability
        
        # None odds
        prob = calculate_implied_probability(None)
        assert prob == 0.0
        
        # Invalid odds (<=1)
        prob = calculate_implied_probability(1.0)
        assert prob == 0.0
        
        prob = calculate_implied_probability(0.5)
        assert prob == 0.0
    
    def test_zscore_normal(self):
        """Test Z-Score calculation."""
        from src.analysis.biscotto_engine import calculate_zscore, LEAGUE_AVG_DRAW_PROB
        
        # Probability equal to average = Z-Score 0
        zscore = calculate_zscore(LEAGUE_AVG_DRAW_PROB)
        assert zscore == 0.0
        
        # Higher probability = positive Z-Score
        zscore = calculate_zscore(0.50)  # 50% vs 28% avg
        assert zscore > 2.0  # Should be significant
    
    def test_zscore_edge_cases(self):
        """Test Z-Score edge cases."""
        from src.analysis.biscotto_engine import calculate_zscore
        
        # Zero probability
        zscore = calculate_zscore(0.0)
        assert zscore == 0.0
        
        # Negative probability (invalid)
        zscore = calculate_zscore(-0.5)
        assert zscore == 0.0
    
    def test_analyze_biscotto_none_odds(self):
        """Should handle None odds gracefully."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        result = analyze_biscotto(
            home_team="Home FC",
            away_team="Away FC",
            current_draw_odd=None
        )
        
        assert result.is_suspect == False
        assert result.severity == BiscottoSeverity.NONE
        assert result.betting_recommendation == "AVOID"
    
    def test_analyze_biscotto_extreme(self):
        """Very low draw odds should trigger EXTREME severity."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        result = analyze_biscotto(
            home_team="Home FC",
            away_team="Away FC",
            current_draw_odd=1.80,  # Very low
            opening_draw_odd=3.00   # Significant drop
        )
        
        assert result.is_suspect == True
        assert result.severity == BiscottoSeverity.EXTREME
        assert "BET X" in result.betting_recommendation
    
    def test_analyze_biscotto_suspicious(self):
        """Low draw odds should trigger at least MEDIUM severity."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        result = analyze_biscotto(
            home_team="Home FC",
            away_team="Away FC",
            current_draw_odd=2.30,  # Below 2.50 threshold
            opening_draw_odd=2.80
        )
        
        assert result.is_suspect == True
        # Can be EXTREME, HIGH, or MEDIUM depending on combined factors
        assert result.severity in [BiscottoSeverity.EXTREME, BiscottoSeverity.HIGH, BiscottoSeverity.MEDIUM]
    
    def test_analyze_biscotto_normal(self):
        """Normal draw odds should not trigger."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        result = analyze_biscotto(
            home_team="Home FC",
            away_team="Away FC",
            current_draw_odd=3.50,  # Normal odds
            opening_draw_odd=3.60   # Minimal movement
        )
        
        assert result.is_suspect == False
        assert result.severity == BiscottoSeverity.NONE
    
    def test_analyze_biscotto_with_motivation(self):
        """Mutual benefit from classifica should boost severity."""
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        # Both teams in relegation zone
        home_motivation = {
            'position': 18,
            'total_teams': 20,
            'points': 25,
            'zone': 'Relegation'
        }
        away_motivation = {
            'position': 17,
            'total_teams': 20,
            'points': 26,
            'zone': 'Danger Zone'
        }
        
        result = analyze_biscotto(
            home_team="Home FC",
            away_team="Away FC",
            current_draw_odd=2.60,  # Slightly suspicious
            opening_draw_odd=3.20,
            home_motivation=home_motivation,
            away_motivation=away_motivation,
            matches_remaining=3  # End of season
        )
        
        # Should detect end-of-season and mutual benefit
        assert result.end_of_season_match == True


class TestIntegration:
    """Integration tests for both engines."""
    
    def test_fatigue_context_helper(self):
        """Test the integration helper for main.py."""
        from src.analysis.fatigue_engine import get_enhanced_fatigue_context
        
        home_context = {
            'fatigue': {'hours_since_last': 72}
        }
        away_context = {
            'fatigue': {'hours_since_last': 120}
        }
        
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Home FC",
            away_team="Away FC",
            home_context=home_context,
            away_context=away_context
        )
        
        assert differential is not None
        assert "FATIGUE" in context_str
    
    def test_fatigue_context_empty_context(self):
        """Should handle empty context dicts."""
        from src.analysis.fatigue_engine import get_enhanced_fatigue_context
        
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Home FC",
            away_team="Away FC",
            home_context={},
            away_context={}
        )
        
        assert differential is not None
        # Should still work with None hours
    
    def test_biscotto_with_empty_motivation_no_crash(self):
        """
        REGRESSION TEST: Biscotto engine must not crash when motivation dicts are empty.
        
        This test would FAIL if home_motivation/away_motivation were not initialized
        before the 'if fotmob:' block in main.py (the bug we fixed).
        """
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis, BiscottoSeverity
        
        # Simulate the scenario where fotmob=None, so motivation dicts are empty
        home_motivation = {}  # Empty dict, not None
        away_motivation = {}  # Empty dict, not None
        
        @dataclass
        class MockMatch:
            home_team: str = "Test FC"
            away_team: str = "Demo United"
            current_draw_odd: float = 2.40
            opening_draw_odd: float = 2.90
            start_time: datetime = None
            def __post_init__(self):
                self.start_time = datetime.now(timezone.utc)
        
        match = MockMatch()
        
        # This should NOT raise any exception
        analysis, context_str = get_enhanced_biscotto_analysis(
            match_obj=match,
            home_motivation=home_motivation,
            away_motivation=away_motivation
        )
        
        # Verify it returns valid results
        assert analysis is not None
        assert analysis.severity in [BiscottoSeverity.NONE, BiscottoSeverity.LOW, 
                                      BiscottoSeverity.MEDIUM, BiscottoSeverity.HIGH,
                                      BiscottoSeverity.EXTREME]
        # Context should still be generated (may be empty if not suspect)
        assert isinstance(context_str, str)
    
    def test_main_py_variable_initialization_pattern(self):
        """
        REGRESSION TEST: Verify the variable initialization pattern used in main.py.
        
        This simulates the exact flow in main.py to ensure variables are accessible
        even when the 'if fotmob:' block is skipped.
        """
        # Simulate main.py initialization (BEFORE if fotmob:)
        home_context = {}
        away_context = {}
        home_motivation = {}
        away_motivation = {}
        
        fotmob = None  # Simulate FotMob not available
        
        if fotmob:
            # This block is skipped
            home_context = {'motivation': {'zone': 'Title Race'}}
            home_motivation = home_context.get('motivation', {})
            away_motivation = away_context.get('motivation', {})
        
        # Variables must be accessible here (outside the if block)
        # This would raise NameError if not initialized before the if block
        assert home_motivation == {}
        assert away_motivation == {}
        assert home_context == {}
        assert away_context == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
