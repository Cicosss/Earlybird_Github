"""
Test suite for EarlyBird V4.3 Deep Research Enhancements

Tests:
1. League-specific Home Advantage
2. Dixon-Coles rho tuning (-0.07)
3. League-adaptive News Decay
4. Sortino-based weight calculation

These tests verify the enhancements from the Deep Research report.
"""
import pytest
import math
from unittest.mock import patch


class TestHomeAdvantageByLeague:
    """Tests for league-specific Home Advantage (V4.3)"""
    
    def test_get_home_advantage_high_ha_leagues(self):
        """High HA leagues (Turkey, Greece, Argentina) should return 0.35+"""
        from config.settings import get_home_advantage
        
        # High HA leagues
        assert get_home_advantage("soccer_turkey_super_league") >= 0.35
        assert get_home_advantage("soccer_greece_super_league") >= 0.38
        assert get_home_advantage("soccer_argentina_primera_division") >= 0.35
    
    def test_get_home_advantage_low_ha_leagues(self):
        """Low HA leagues (Bundesliga, PL) should return < 0.27"""
        from config.settings import get_home_advantage
        
        # Low HA leagues
        assert get_home_advantage("soccer_germany_bundesliga") <= 0.25
        assert get_home_advantage("soccer_england_premier_league") <= 0.26
    
    def test_get_home_advantage_default(self):
        """Unknown leagues should return default (0.30)"""
        from config.settings import get_home_advantage, DEFAULT_HOME_ADVANTAGE
        
        assert get_home_advantage("soccer_unknown_league") == DEFAULT_HOME_ADVANTAGE
        assert get_home_advantage(None) == DEFAULT_HOME_ADVANTAGE
        assert get_home_advantage("") == DEFAULT_HOME_ADVANTAGE
    
    def test_math_predictor_uses_league_ha(self):
        """MathPredictor should use league-specific HA"""
        from src.analysis.math_engine import MathPredictor
        
        # Turkey has high HA
        predictor_turkey = MathPredictor(league_key="soccer_turkey_super_league")
        assert predictor_turkey.home_advantage >= 0.35
        
        # Bundesliga has low HA
        predictor_bundesliga = MathPredictor(league_key="soccer_germany_bundesliga")
        assert predictor_bundesliga.home_advantage <= 0.25
        
        # Different leagues should have different HA
        assert predictor_turkey.home_advantage > predictor_bundesliga.home_advantage
    
    def test_simulate_match_applies_home_advantage(self):
        """simulate_match should boost home_lambda with HA"""
        from src.analysis.math_engine import MathPredictor
        
        # Same stats, different leagues
        stats = {
            'home_scored': 1.5, 'home_conceded': 1.0,
            'away_scored': 1.2, 'away_conceded': 1.3
        }
        
        # High HA league
        predictor_high = MathPredictor(league_key="soccer_greece_super_league")
        result_high = predictor_high.simulate_match(**stats)
        
        # Low HA league
        predictor_low = MathPredictor(league_key="soccer_germany_bundesliga")
        result_low = predictor_low.simulate_match(**stats)
        
        # High HA should give higher home win probability
        assert result_high is not None
        assert result_low is not None
        assert result_high.home_win_prob > result_low.home_win_prob
    
    def test_simulate_match_without_ha(self):
        """simulate_match with apply_home_advantage=False should not apply HA"""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor(league_key="soccer_turkey_super_league")
        
        stats = {
            'home_scored': 1.5, 'home_conceded': 1.0,
            'away_scored': 1.2, 'away_conceded': 1.3
        }
        
        result_with_ha = predictor.simulate_match(**stats, apply_home_advantage=True)
        result_without_ha = predictor.simulate_match(**stats, apply_home_advantage=False)
        
        # Without HA, home win prob should be lower
        assert result_with_ha.home_win_prob > result_without_ha.home_win_prob


class TestDixonColesRhoTuning:
    """Tests for Dixon-Coles rho parameter tuning (V4.3)"""
    
    def test_dixon_coles_rho_value(self):
        """Dixon-Coles rho should be -0.07 (tuned from -0.10)"""
        from src.analysis.math_engine import DIXON_COLES_RHO
        
        assert DIXON_COLES_RHO == -0.07
    
    def test_dixon_coles_correction_applied(self):
        """Dixon-Coles correction should affect low-scoring probabilities"""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # Test correction factor for 0-0
        correction_00 = predictor.dixon_coles_correction(0, 0, 1.5, 1.2)
        assert correction_00 != 1.0  # Should be modified
        
        # Test correction factor for 1-1
        correction_11 = predictor.dixon_coles_correction(1, 1, 1.5, 1.2)
        assert correction_11 != 1.0  # Should be modified
        
        # Test no correction for high scores
        correction_33 = predictor.dixon_coles_correction(3, 3, 1.5, 1.2)
        assert correction_33 == 1.0  # No correction for high scores


class TestLeagueAdaptiveNewsDecay:
    """Tests for news decay (V4.3) - uniform for Elite 7"""
    
    def test_get_news_decay_lambda_uniform(self):
        """All leagues should have same decay (λ=0.023) - Elite 7 are niche markets"""
        from config.settings import get_news_decay_lambda
        
        # All monitored leagues use same decay
        leagues = [
            "soccer_turkey_super_league",
            "soccer_argentina_primera_division",
            "soccer_greece_super_league",
            "soccer_mexico_ligamx",
            "soccer_poland_ekstraklasa",
        ]
        
        for league in leagues:
            lambda_val = get_news_decay_lambda(league)
            assert lambda_val == 0.023, f"League {league} should have λ=0.023"
    
    def test_get_news_decay_lambda_none(self):
        """None league should return default (0.023)"""
        from config.settings import get_news_decay_lambda
        
        lambda_val = get_news_decay_lambda(None)
        assert lambda_val == 0.023
    
    def test_apply_news_decay_uniform(self):
        """apply_news_decay should use uniform lambda for all leagues"""
        from src.analysis.market_intelligence import apply_news_decay
        
        impact = 10.0
        minutes = 10
        
        # All leagues use same decay
        decayed_turkey = apply_news_decay(impact, minutes, league_key="soccer_turkey_super_league")
        decayed_argentina = apply_news_decay(impact, minutes, league_key="soccer_argentina_primera_division")
        
        # Both should have same decay (uniform λ=0.023)
        assert decayed_turkey == decayed_argentina
    
    def test_apply_news_decay_edge_cases(self):
        """apply_news_decay should handle edge cases safely"""
        from src.analysis.market_intelligence import apply_news_decay
        
        # Zero impact
        assert apply_news_decay(0, 10) == 0.0
        
        # Negative impact
        assert apply_news_decay(-5, 10) == 0.0
        
        # Zero minutes (fresh news)
        assert apply_news_decay(10, 0) == 10.0
        
        # Very old news (should return ~1% residual)
        very_old = apply_news_decay(10, 24 * 60 + 1)  # > 24 hours
        assert very_old == pytest.approx(0.1, rel=0.1)  # ~1% of 10


class TestSortinoBasedWeightCalculation:
    """Tests for Sortino-based weight calculation (V4.3)"""
    
    def test_sortino_penalty_threshold(self):
        """Sortino penalty threshold should be 1.5"""
        from src.analysis.optimizer import SORTINO_PENALTY_THRESHOLD
        
        assert SORTINO_PENALTY_THRESHOLD == 1.5
    
    def test_calculate_advanced_weight_uses_sortino(self):
        """calculate_advanced_weight should use Sortino when provided"""
        from src.analysis.optimizer import calculate_advanced_weight
        
        # V5.0: Need n_samples >= 50 for ACTIVE state (full optimization)
        # Good Sortino (no penalty)
        weight_good = calculate_advanced_weight(
            roi=0.1, sharpe=0.3, max_drawdown=-0.1, n_samples=60, sortino=2.0
        )
        
        # Bad Sortino (penalty applied)
        weight_bad = calculate_advanced_weight(
            roi=0.1, sharpe=0.3, max_drawdown=-0.1, n_samples=60, sortino=1.0
        )
        
        # Good Sortino should result in higher weight
        assert weight_good > weight_bad
    
    def test_calculate_advanced_weight_fallback_to_sharpe(self):
        """calculate_advanced_weight should fallback to Sharpe if Sortino is None"""
        from src.analysis.optimizer import calculate_advanced_weight
        
        # V5.0: Need n_samples >= 50 for ACTIVE state
        # Without Sortino, should use Sharpe
        weight = calculate_advanced_weight(
            roi=0.1, sharpe=0.3, max_drawdown=-0.1, n_samples=60, sortino=None
        )
        
        # Should still calculate a valid weight
        assert 0.2 <= weight <= 2.0
    
    def test_calc_sortino_no_downside(self):
        """calc_sortino should return 5.0 for all-winning strategies"""
        from src.analysis.optimizer import calc_sortino
        
        # All wins (no downside)
        all_wins = [0.5, 0.8, 1.2, 0.3, 0.6, 0.9, 0.4, 0.7, 1.0, 0.5]
        sortino = calc_sortino(all_wins)
        
        assert sortino == 5.0  # Perfect strategy
    
    def test_calc_sortino_with_losses(self):
        """calc_sortino should penalize only downside volatility"""
        from src.analysis.optimizer import calc_sortino
        
        # Mix of wins and losses (more wins than losses for positive Sortino)
        mixed = [0.8, -1.0, 0.9, 0.7, 1.2, -1.0, 0.6, 0.8, 0.9, 0.5]
        sortino = calc_sortino(mixed)
        
        # Should be a valid number (can be negative if losses dominate)
        assert isinstance(sortino, float)
        assert sortino != 5.0  # Not perfect (has losses)
    
    def test_calc_sortino_insufficient_samples(self):
        """calc_sortino should return 0 for < 10 samples"""
        from src.analysis.optimizer import calc_sortino
        
        few_samples = [0.5, 0.8, 1.2]
        assert calc_sortino(few_samples) == 0.0


class TestIntegration:
    """Integration tests for V4.3 enhancements"""
    
    def test_full_poisson_analysis_with_league(self):
        """Full Poisson analysis should work with league-specific settings"""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor(league_key="soccer_turkey_super_league")
        
        result = predictor.analyze_match(
            home_scored=1.8,
            home_conceded=0.9,
            away_scored=1.2,
            away_conceded=1.5,
            home_odd=1.75,
            draw_odd=3.50,
            away_odd=4.50
        )
        
        assert 'poisson' in result
        assert 'edges' in result
        assert result['poisson'].home_win_prob > 0
        assert result['poisson'].draw_prob > 0
        assert result['poisson'].away_win_prob > 0
        
        # Probabilities should sum to ~1
        total = (result['poisson'].home_win_prob + 
                 result['poisson'].draw_prob + 
                 result['poisson'].away_win_prob)
        assert 0.99 <= total <= 1.01
    
    def test_optimizer_records_sortino(self):
        """Optimizer should record and use Sortino in weight calculation"""
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        # Use temp file for test
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_path)
            
            # Record some bets
            optimizer.record_bet_result("soccer_turkey_super_league", "Over 2.5", "WIN", 1.9, "MATH_VALUE")
            optimizer.record_bet_result("soccer_turkey_super_league", "Over 2.5", "WIN", 1.85, "MATH_VALUE")
            optimizer.record_bet_result("soccer_turkey_super_league", "Over 2.5", "LOSS", 1.9, "MATH_VALUE")
            
            # Check that sortino is tracked
            stats = optimizer.data['stats'].get('soccer_turkey_super_league', {}).get('OVER', {})
            assert 'sortino' in stats
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestNewsHunterIntegration:
    """Tests for news_hunter integration with league-adaptive decay"""
    
    def test_calculate_news_freshness_uniform(self):
        """calculate_news_freshness_multiplier should use uniform decay for all leagues"""
        from src.analysis.market_intelligence import calculate_news_freshness_multiplier
        
        news_date = "10 minutes ago"
        
        # All leagues use same decay
        mult_turkey, mins1 = calculate_news_freshness_multiplier(
            news_date, 
            league_key="soccer_turkey_super_league"
        )
        
        mult_argentina, mins2 = calculate_news_freshness_multiplier(
            news_date, 
            league_key="soccer_argentina_primera_division"
        )
        
        # Both should parse same minutes
        assert mins1 == mins2 == 10
        
        # Both should have same multiplier (uniform decay)
        assert mult_turkey == mult_argentina
    
    def test_calculate_news_freshness_backward_compatible(self):
        """calculate_news_freshness_multiplier should work without league_key"""
        from src.analysis.market_intelligence import calculate_news_freshness_multiplier
        
        # Should not raise error without league_key
        multiplier, minutes = calculate_news_freshness_multiplier("5 minutes ago")
        
        assert minutes == 5
        assert 0 < multiplier <= 1
    
    def test_quick_poisson_with_league(self):
        """quick_poisson should support league_key parameter"""
        from src.analysis.math_engine import quick_poisson
        
        # With league_key
        result_turkey = quick_poisson(1.5, 1.0, 1.2, 1.3, league_key="soccer_turkey_super_league")
        
        # Without league_key (backward compatible)
        result_default = quick_poisson(1.5, 1.0, 1.2, 1.3)
        
        assert result_turkey is not None
        assert result_default is not None
        
        # Turkey has high HA (0.38), default is 0.30
        # So Turkey should give higher home win prob
        assert result_turkey.home_win_prob > result_default.home_win_prob


class TestEdgeCasesV43:
    """Edge case tests for V4.3 enhancements"""
    
    def test_home_advantage_none_league(self):
        """get_home_advantage should handle None league gracefully"""
        from config.settings import get_home_advantage, DEFAULT_HOME_ADVANTAGE
        
        assert get_home_advantage(None) == DEFAULT_HOME_ADVANTAGE
    
    def test_home_advantage_empty_league(self):
        """get_home_advantage should handle empty string"""
        from config.settings import get_home_advantage, DEFAULT_HOME_ADVANTAGE
        
        assert get_home_advantage("") == DEFAULT_HOME_ADVANTAGE
    
    def test_news_decay_none_league(self):
        """get_news_decay_lambda should handle None league"""
        from config.settings import get_news_decay_lambda
        
        # Should return default (0.023) for None
        lambda_val = get_news_decay_lambda(None)
        assert lambda_val == 0.023
    
    def test_math_predictor_none_league(self):
        """MathPredictor should work with None league_key"""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor(league_key=None)
        result = predictor.simulate_match(1.5, 1.0, 1.2, 1.3)
        
        assert result is not None
        assert 0 < result.home_win_prob < 1
    
    def test_apply_news_decay_none_league(self):
        """apply_news_decay should work with None league_key"""
        from src.analysis.market_intelligence import apply_news_decay
        
        result = apply_news_decay(10.0, 10, league_key=None)
        
        assert result > 0
        assert result < 10.0  # Should have decayed


# ============================================
# V4.3 PHASE 1 ENHANCEMENTS (Deep Research)
# ============================================

class TestSteamMoveTierBasedWindows:
    """Tests for Steam Move time windows (V4.3 Phase 1)"""
    
    def test_get_steam_window_uniform_for_all_leagues(self):
        """All leagues should use 15 min window (Elite 7 are niche markets)"""
        from src.analysis.market_intelligence import get_steam_window_for_league, STEAM_MOVE_TIME_WINDOW_MIN
        
        # All monitored leagues use same window
        leagues = [
            "soccer_turkey_super_league",
            "soccer_argentina_primera_division",
            "soccer_greece_super_league",
            "soccer_mexico_ligamx",
            "soccer_poland_ekstraklasa",
        ]
        
        for league in leagues:
            window = get_steam_window_for_league(league)
            assert window == STEAM_MOVE_TIME_WINDOW_MIN, f"{league} should use 15 min window"
    
    def test_get_steam_window_none_league(self):
        """None league should return default (15 min)"""
        from src.analysis.market_intelligence import get_steam_window_for_league, STEAM_MOVE_TIME_WINDOW_MIN
        
        window = get_steam_window_for_league(None)
        assert window == STEAM_MOVE_TIME_WINDOW_MIN
    
    def test_get_steam_window_empty_league(self):
        """Empty string league should return default"""
        from src.analysis.market_intelligence import get_steam_window_for_league, STEAM_MOVE_TIME_WINDOW_MIN
        
        window = get_steam_window_for_league("")
        assert window == STEAM_MOVE_TIME_WINDOW_MIN
    
    def test_detect_steam_move_accepts_league_key(self):
        """detect_steam_move should accept league_key parameter"""
        from src.analysis.market_intelligence import detect_steam_move
        
        # Should not raise error with league_key
        result = detect_steam_move('match123', {'home': 1.85}, league_key="soccer_turkey_super_league")
        # Result is None (no history), but should not raise error
        assert result is None


class TestBiscottoMinorLeagueThresholds:
    """Tests for minor league biscotto thresholds (V4.3 Phase 1)"""
    
    def test_is_minor_league_biscotto_risk(self):
        """Minor leagues should be identified correctly"""
        from src.analysis.biscotto_engine import is_minor_league_biscotto_risk
        
        # Minor leagues (high biscotto risk)
        assert is_minor_league_biscotto_risk("soccer_italy_serie_b") is True
        assert is_minor_league_biscotto_risk("soccer_spain_segunda_division") is True
        assert is_minor_league_biscotto_risk("soccer_germany_bundesliga2") is True
        assert is_minor_league_biscotto_risk("soccer_brazil_serie_b") is True
        
        # Major leagues (not high risk)
        assert is_minor_league_biscotto_risk("soccer_italy_serie_a") is False
        assert is_minor_league_biscotto_risk("soccer_england_premier_league") is False
    
    def test_is_minor_league_none_league(self):
        """None league should return False"""
        from src.analysis.biscotto_engine import is_minor_league_biscotto_risk
        
        assert is_minor_league_biscotto_risk(None) is False
        assert is_minor_league_biscotto_risk("") is False
    
    def test_get_draw_threshold_minor_league_end_season(self):
        """Minor league in end-of-season should use stricter threshold (2.60)"""
        from src.analysis.biscotto_engine import (
            get_draw_threshold_for_league, 
            MINOR_LEAGUE_DRAW_THRESHOLD,
            DRAW_SUSPICIOUS_LOW
        )
        
        # Minor league + end of season = stricter threshold
        threshold = get_draw_threshold_for_league("soccer_italy_serie_b", end_of_season=True)
        assert threshold == MINOR_LEAGUE_DRAW_THRESHOLD  # 2.60
        
        # Minor league + NOT end of season = standard threshold
        threshold_mid = get_draw_threshold_for_league("soccer_italy_serie_b", end_of_season=False)
        assert threshold_mid == DRAW_SUSPICIOUS_LOW  # 2.50
        
        # Major league + end of season = standard threshold
        threshold_major = get_draw_threshold_for_league("soccer_italy_serie_a", end_of_season=True)
        assert threshold_major == DRAW_SUSPICIOUS_LOW  # 2.50
    
    def test_analyze_biscotto_uses_dynamic_threshold(self):
        """analyze_biscotto should use dynamic threshold for minor leagues"""
        from src.analysis.biscotto_engine import analyze_biscotto
        
        # Draw odd at 2.55 - between 2.50 (standard) and 2.60 (minor league)
        # Should be flagged for minor league in end-of-season, not for major league
        
        # Minor league, end of season (matches_remaining=3)
        result_minor = analyze_biscotto(
            home_team="Team A",
            away_team="Team B",
            current_draw_odd=2.55,
            opening_draw_odd=3.00,
            matches_remaining=3,  # End of season
            league_key="soccer_italy_serie_b"
        )
        
        # Major league, end of season
        result_major = analyze_biscotto(
            home_team="Team A",
            away_team="Team B",
            current_draw_odd=2.55,
            opening_draw_odd=3.00,
            matches_remaining=3,
            league_key="soccer_italy_serie_a"
        )
        
        # Minor league should have higher severity (2.55 < 2.60 threshold)
        # Major league should have lower severity (2.55 > 2.50 threshold)
        assert result_minor.confidence >= result_major.confidence
    
    def test_get_enhanced_biscotto_extracts_matches_remaining(self):
        """V4.4: get_enhanced_biscotto_analysis should extract matches_remaining from motivation context"""
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis, BiscottoSeverity
        from unittest.mock import MagicMock
        
        # Create mock match object
        mock_match = MagicMock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.30  # Suspicious
        mock_match.opening_draw_odd = 3.20
        mock_match.league = "soccer_italy_serie_b"
        
        # Motivation context WITH matches_remaining (V4.4 fix)
        home_motivation = {
            "position": 15,
            "total_teams": 20,
            "zone": "Danger Zone",
            "points": 25,
            "matches_remaining": 3  # End of season!
        }
        away_motivation = {
            "position": 16,
            "total_teams": 20,
            "zone": "Relegation",
            "points": 22,
            "matches_remaining": 3
        }
        
        analysis, context_str = get_enhanced_biscotto_analysis(
            match_obj=mock_match,
            home_motivation=home_motivation,
            away_motivation=away_motivation
        )
        
        # With matches_remaining=3, end_of_season should be True
        assert analysis.end_of_season_match is True
        # Both teams in danger/relegation zone at end of season = mutual benefit
        assert analysis.mutual_benefit is True
        # Should be flagged as suspect
        assert analysis.is_suspect is True
    
    def test_get_enhanced_biscotto_handles_none_matches_remaining(self):
        """V4.4: Should handle None matches_remaining gracefully (regression test)"""
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        from unittest.mock import MagicMock
        
        mock_match = MagicMock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.30
        mock_match.opening_draw_odd = 3.20
        mock_match.league = "soccer_italy_serie_a"
        
        # Old-style motivation WITHOUT matches_remaining (pre-V4.4)
        home_motivation = {
            "position": 10,
            "total_teams": 20,
            "zone": "Mid-Table",
            "points": 35
            # NO matches_remaining key!
        }
        away_motivation = None  # Edge case: None motivation
        
        # Should NOT raise any exception
        analysis, context_str = get_enhanced_biscotto_analysis(
            match_obj=mock_match,
            home_motivation=home_motivation,
            away_motivation=away_motivation
        )
        
        # Without matches_remaining, end_of_season should be False
        assert analysis.end_of_season_match is False
        assert analysis is not None


class TestFatigueLowTierTeams:
    """Tests for LOW_TIER_TEAMS fatigue multiplier (V4.3 Phase 1)"""
    
    def test_get_squad_depth_low_tier_teams(self):
        """Low tier teams should return 1.3x fatigue multiplier"""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_LOW
        
        low_tier_teams = [
            "Luton Town",
            "Burnley",
            "Sheffield United",
            "Lecce",
            "Empoli",
            "Frosinone",
            "Almeria",
            "Heidenheim",
            "Istanbulspor",
        ]
        
        for team in low_tier_teams:
            score = get_squad_depth_score(team)
            assert score == SQUAD_DEPTH_LOW, f"{team} should have 1.3x fatigue multiplier"
    
    def test_get_squad_depth_elite_teams(self):
        """Elite teams should still return 0.5x multiplier"""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_ELITE
        
        elite_teams = ["Manchester City", "Real Madrid", "Bayern Munich"]
        
        for team in elite_teams:
            score = get_squad_depth_score(team)
            assert score == SQUAD_DEPTH_ELITE, f"{team} should have 0.5x fatigue multiplier"
    
    def test_get_squad_depth_mid_tier_teams(self):
        """Unknown teams should return 1.0x multiplier (default)"""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_MID
        
        # Teams not in any list
        unknown_teams = ["Random FC", "Unknown United", "Test City"]
        
        for team in unknown_teams:
            score = get_squad_depth_score(team)
            assert score == SQUAD_DEPTH_MID, f"{team} should have 1.0x fatigue multiplier"
    
    def test_get_squad_depth_none_team(self):
        """None team should return default multiplier"""
        from src.analysis.fatigue_engine import get_squad_depth_score, SQUAD_DEPTH_MID
        
        assert get_squad_depth_score(None) == SQUAD_DEPTH_MID
        assert get_squad_depth_score("") == SQUAD_DEPTH_MID
    
    def test_fatigue_analysis_uses_low_tier(self):
        """analyze_team_fatigue should apply 1.3x for low tier teams"""
        from src.analysis.fatigue_engine import analyze_team_fatigue
        
        # Same fatigue conditions, different team tiers
        hours_since_last = 60  # Very short rest
        
        # Low tier team (1.3x multiplier)
        result_low = analyze_team_fatigue("Luton Town", hours_since_last)
        
        # Elite team (0.5x multiplier)
        result_elite = analyze_team_fatigue("Manchester City", hours_since_last)
        
        # Low tier should have higher fatigue index
        assert result_low.fatigue_index > result_elite.fatigue_index
        assert result_low.squad_depth_score > result_elite.squad_depth_score


class TestPhase1Integration:
    """Integration tests for Phase 1 enhancements"""
    
    def test_market_intelligence_with_league(self):
        """analyze_market_intelligence should accept league_key"""
        from src.analysis.market_intelligence import analyze_market_intelligence
        from unittest.mock import MagicMock
        
        # Create mock match
        mock_match = MagicMock()
        mock_match.id = "test_match_123"
        mock_match.league = "soccer_england_premier_league"
        mock_match.current_home_odd = 1.85
        mock_match.current_draw_odd = 3.50
        mock_match.current_away_odd = 4.20
        mock_match.opening_home_odd = 1.90
        mock_match.opening_away_odd = 4.00
        
        # Should not raise error
        result = analyze_market_intelligence(mock_match, league_key="soccer_england_premier_league")
        
        assert result is not None
        assert hasattr(result, 'steam_move')
        assert hasattr(result, 'reverse_line')
    
    def test_biscotto_analysis_extracts_league_from_match(self):
        """get_enhanced_biscotto_analysis should extract league from match_obj"""
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        from unittest.mock import MagicMock
        
        # Create mock match with league
        mock_match = MagicMock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.55
        mock_match.opening_draw_odd = 3.00
        mock_match.league = "soccer_italy_serie_b"  # Minor league
        
        # Should not raise error and should use league
        analysis, context = get_enhanced_biscotto_analysis(mock_match)
        
        assert analysis is not None
        assert isinstance(context, str)
