"""
EarlyBird V4.4 Verification Tests

Comprehensive tests to verify:
1. All imports work correctly
2. Edge cases are handled
3. Integration between modules works
4. No regressions from recent changes

Author: EarlyBird AI
"""
import pytest
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

# Ensure src is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestImports:
    """Verify all critical imports work."""
    
    def test_import_fatigue_engine(self):
        from src.analysis.fatigue_engine import (
            get_enhanced_fatigue_context,
            FatigueDifferential,
            analyze_team_fatigue,
            get_squad_depth_score,
            ELITE_SQUAD_TEAMS,
            LOW_TIER_TEAMS
        )
        assert FatigueDifferential is not None
        assert callable(get_enhanced_fatigue_context)
        assert callable(analyze_team_fatigue)
        assert callable(get_squad_depth_score)
        assert len(ELITE_SQUAD_TEAMS) > 0
        assert len(LOW_TIER_TEAMS) > 0
    
    def test_import_biscotto_engine(self):
        from src.analysis.biscotto_engine import (
            get_enhanced_biscotto_analysis,
            BiscottoSeverity,
            analyze_biscotto,
            is_minor_league_biscotto_risk,
            get_draw_threshold_for_league,
            MINOR_LEAGUES_BISCOTTO_RISK
        )
        assert BiscottoSeverity is not None
        assert callable(get_enhanced_biscotto_analysis)
        assert callable(analyze_biscotto)
        assert callable(is_minor_league_biscotto_risk)
        assert callable(get_draw_threshold_for_league)
        assert len(MINOR_LEAGUES_BISCOTTO_RISK) > 0
    
    def test_import_market_intelligence(self):
        from src.analysis.market_intelligence import (
            analyze_market_intelligence,
            apply_news_decay,
            apply_news_decay_v2,
            detect_steam_move,
            detect_reverse_line_movement,
            detect_rlm_v2,
            calculate_news_freshness_multiplier,
            SteamMoveSignal,
            ReverseLineSignal,
            RLMSignalV2,
            MarketIntelligence
        )
        assert callable(analyze_market_intelligence)
        assert callable(apply_news_decay)
        assert callable(apply_news_decay_v2)
        assert callable(detect_steam_move)
        assert callable(detect_reverse_line_movement)
        assert callable(detect_rlm_v2)
        assert callable(calculate_news_freshness_multiplier)
    
    def test_import_optimizer(self):
        from src.analysis.optimizer import (
            get_optimizer,
            StrategyOptimizer,
            calc_sharpe,
            calc_sortino,
            calc_max_drawdown,
            calculate_advanced_weight,
            categorize_market
        )
        assert callable(get_optimizer)
        assert callable(calc_sharpe)
        assert callable(calc_sortino)
        assert callable(calc_max_drawdown)
        assert callable(calculate_advanced_weight)
        assert callable(categorize_market)
    
    def test_import_settler(self):
        from src.analysis.settler import (
            settle_pending_bets,
            evaluate_bet,
            calculate_clv,
            evaluate_over_under,
            RESULT_WIN,
            RESULT_LOSS,
            RESULT_PUSH,
            RESULT_PENDING
        )
        assert callable(settle_pending_bets)
        assert callable(evaluate_bet)
        assert callable(calculate_clv)
        assert callable(evaluate_over_under)
        assert RESULT_WIN == "WIN"
        assert RESULT_LOSS == "LOSS"
    
    def test_import_league_manager(self):
        from src.ingestion.league_manager import (
            get_active_niche_leagues,
            is_elite_league,
            is_tier1_league,
            is_tier2_league,
            should_activate_tier2_fallback,
            get_tier2_fallback_batch,
            record_tier2_activation,
            increment_cycle,
            TIER_1_LEAGUES,
            TIER_2_LEAGUES,
            ELITE_LEAGUES
        )
        assert callable(get_active_niche_leagues)
        assert callable(is_elite_league)
        assert callable(should_activate_tier2_fallback)
        assert callable(get_tier2_fallback_batch)
        assert len(TIER_1_LEAGUES) > 0
        assert len(TIER_2_LEAGUES) > 0
    
    def test_import_settings(self):
        from config.settings import (
            get_home_advantage,
            get_news_decay_lambda,
            get_source_decay_modifier,
            HOME_ADVANTAGE_BY_LEAGUE,
            TIER1_LEAGUES,
            NEWS_DECAY_LAMBDA_TIER1,
            NEWS_DECAY_LAMBDA_ELITE,
            BISCOTTO_KEYWORDS
        )
        assert callable(get_home_advantage)
        assert callable(get_news_decay_lambda)
        assert callable(get_source_decay_modifier)
        assert len(HOME_ADVANTAGE_BY_LEAGUE) > 0
        assert len(TIER1_LEAGUES) > 0


class TestEdgeCases:
    """Test edge cases that could cause crashes."""
    
    def test_fatigue_engine_none_inputs(self):
        from src.analysis.fatigue_engine import (
            get_squad_depth_score,
            analyze_team_fatigue,
            get_fatigue_level
        )
        
        # None team name
        assert get_squad_depth_score(None) == 1.0
        
        # Empty team name
        assert get_squad_depth_score("") == 1.0
        
        # None hours
        result = analyze_team_fatigue("Test Team", None)
        assert result.fatigue_level in ["FRESH", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        
        # Fatigue level with None hours
        level = get_fatigue_level(0.5, None)
        assert level in ["FRESH", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    
    def test_biscotto_engine_none_inputs(self):
        from src.analysis.biscotto_engine import (
            analyze_biscotto,
            calculate_implied_probability,
            calculate_zscore,
            is_minor_league_biscotto_risk,
            get_draw_threshold_for_league
        )
        
        # None odds
        result = analyze_biscotto("Home", "Away", None)
        assert result.is_suspect == False
        assert result.severity.value == "NONE"
        
        # Invalid odds
        result = analyze_biscotto("Home", "Away", 0.5)
        assert result.is_suspect == False
        
        # None league
        assert is_minor_league_biscotto_risk(None) == False
        assert get_draw_threshold_for_league(None, False) == 2.50
        
        # Implied probability edge cases
        assert calculate_implied_probability(None) == 0.0
        assert calculate_implied_probability(0.5) == 0.0
        assert calculate_implied_probability(1.0) == 0.0
        
        # Z-score edge cases
        assert calculate_zscore(0) == 0.0
        assert calculate_zscore(-1) == 0.0
    
    def test_market_intelligence_none_inputs(self):
        from src.analysis.market_intelligence import (
            apply_news_decay,
            apply_news_decay_v2,
            calculate_news_freshness_multiplier
        )
        
        # Zero/negative score
        assert apply_news_decay(0, 10) == 0.0
        assert apply_news_decay(-5, 10) == 0.0
        
        # Zero/negative minutes
        assert apply_news_decay(10, 0) == 10.0
        assert apply_news_decay(10, -5) == 10.0
        
        # V2 with None inputs
        score, tag = apply_news_decay_v2(0, 10)
        assert score == 0.0
        
        score, tag = apply_news_decay_v2(10, 0)
        assert score == 10.0
        assert tag == "🔥 FRESH"
        
        # Freshness multiplier with None
        mult, mins = calculate_news_freshness_multiplier(None)
        assert mult > 0
        assert mins == 30  # Default
        
        mult, mins = calculate_news_freshness_multiplier("")
        assert mult > 0
    
    def test_optimizer_edge_cases(self):
        from src.analysis.optimizer import (
            calc_sharpe,
            calc_sortino,
            calc_max_drawdown,
            calculate_advanced_weight,
            categorize_market
        )
        
        # Empty lists
        assert calc_sharpe([]) == 0.0
        assert calc_sortino([]) == 0.0
        assert calc_max_drawdown([]) == 0.0
        
        # Insufficient samples
        assert calc_sharpe([1.0, 2.0]) == 0.0
        assert calc_sortino([1.0, 2.0]) == 0.0
        
        # Zero variance (all same values)
        same_values = [1.0] * 15
        sharpe = calc_sharpe(same_values)
        assert sharpe == 5.0  # Consistent positive returns
        
        # All losses
        all_losses = [-1.0] * 15
        sortino = calc_sortino(all_losses)
        assert sortino < 0
        
        # Weight calculation edge cases
        weight = calculate_advanced_weight(0, 0, 0, 0)
        assert 0.2 <= weight <= 2.0
        
        weight = calculate_advanced_weight(0.5, 2.0, -0.05, 50, sortino=2.0)
        assert 0.2 <= weight <= 2.0
        
        # Market categorization
        assert categorize_market(None) == "UNKNOWN"
        assert categorize_market("") == "UNKNOWN"
        assert categorize_market("Over 2.5 Goals") == "OVER"
        assert categorize_market("BTTS") == "BTTS"
    
    def test_settler_edge_cases(self):
        from src.analysis.settler import (
            calculate_clv,
            evaluate_over_under,
            evaluate_bet
        )
        
        # CLV edge cases
        assert calculate_clv(None, 2.0) is None
        assert calculate_clv(2.0, None) is None
        assert calculate_clv(0.5, 2.0) is None  # Invalid odds
        assert calculate_clv(2.0, 0.5) is None  # Invalid odds
        
        # Valid CLV
        clv = calculate_clv(2.0, 1.9)
        assert clv is not None
        assert isinstance(clv, float)
        
        # Over/Under evaluation
        result, msg = evaluate_over_under("Over 9.5 Corners", 10, True)
        assert result == "WIN"
        
        result, msg = evaluate_over_under("Under 9.5 Corners", 10, True)
        assert result == "LOSS"
        
        result, msg = evaluate_over_under("Over 9.5 Corners", 10, False)
        assert result == "PENDING"
        
        # Invalid format
        result, msg = evaluate_over_under("Invalid Market", 10, True)
        assert result == "PENDING"
        
        # Bet evaluation with cancelled match
        result, msg = evaluate_bet("Home Win", 2, 1, 1.5, "CANCELLED")
        assert result == "PUSH"
        
        result, msg = evaluate_bet("Home Win", 2, 1, 1.5, "POSTPONED")
        assert result == "PUSH"
    
    def test_settings_edge_cases(self):
        from config.settings import (
            get_home_advantage,
            get_news_decay_lambda,
            get_source_decay_modifier
        )
        
        # None inputs
        assert get_home_advantage(None) == 0.30
        assert get_home_advantage("") == 0.30
        
        assert get_news_decay_lambda(None) == 0.023  # Elite default
        assert get_news_decay_lambda("") == 0.023
        
        assert get_source_decay_modifier(None) == 1.0
        assert get_source_decay_modifier("") == 1.0
        assert get_source_decay_modifier("unknown_source") == 1.0


class TestIntegration:
    """Test integration between modules."""
    
    def test_fatigue_context_integration(self):
        """Test that fatigue context helper works with empty FotMob data."""
        from src.analysis.fatigue_engine import get_enhanced_fatigue_context
        
        # Empty context dicts (simulating FotMob failure)
        differential, context_str = get_enhanced_fatigue_context(
            home_team="Test Home",
            away_team="Test Away",
            home_context={},
            away_context={},
            match_start_time=datetime.now(timezone.utc)
        )
        
        assert differential is not None
        assert differential.home_fatigue is not None
        assert differential.away_fatigue is not None
        assert isinstance(context_str, str)
    
    def test_biscotto_integration_with_match_mock(self):
        """Test biscotto analysis with mocked match object."""
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        
        # Create mock match object
        mock_match = Mock()
        mock_match.home_team = "Team A"
        mock_match.away_team = "Team B"
        mock_match.current_draw_odd = 2.30
        mock_match.opening_draw_odd = 2.80
        mock_match.league = "soccer_italy_serie_b"
        
        analysis, context_str = get_enhanced_biscotto_analysis(
            match_obj=mock_match,
            home_motivation={'zone': 'Relegation', 'position': 18},
            away_motivation={'zone': 'Mid-table', 'position': 10}
        )
        
        assert analysis is not None
        assert analysis.current_draw_odd == 2.30
        assert isinstance(context_str, str)
    
    def test_market_intelligence_integration(self):
        """Test market intelligence with mocked match."""
        from src.analysis.market_intelligence import analyze_market_intelligence
        
        # Create mock match
        mock_match = Mock()
        mock_match.id = "test_match_123"
        mock_match.league = "soccer_turkey_super_league"
        mock_match.opening_home_odd = 2.0
        mock_match.current_home_odd = 2.1
        mock_match.opening_away_odd = 3.5
        mock_match.current_away_odd = 3.3
        mock_match.current_draw_odd = 3.2
        
        result = analyze_market_intelligence(mock_match)
        
        assert result is not None
        assert isinstance(result.summary, str)
        assert isinstance(result.has_signals, bool)
    
    def test_optimizer_weight_application(self):
        """Test optimizer weight calculation and application."""
        from src.analysis.optimizer import (
            StrategyOptimizer,
            calculate_advanced_weight,
            categorize_market
        )
        
        # Test weight calculation with various inputs
        weight = calculate_advanced_weight(
            roi=0.15,
            sharpe=1.2,
            max_drawdown=-0.08,
            n_samples=25,
            sortino=1.8
        )
        
        assert 0.2 <= weight <= 2.0
        
        # Test market categorization
        assert categorize_market("Home Win") == "1X2"
        assert categorize_market("Over 2.5 Goals") == "OVER"
        assert categorize_market("BTTS Yes") == "BTTS"
        assert categorize_market("Over 9.5 Corners") == "CORNERS"
        assert categorize_market("Over 4.5 Cards") == "CARDS"


class TestDatabaseModels:
    """Test database model edge cases."""
    
    def test_match_model_attributes(self):
        """Verify Match model has all required attributes."""
        from src.database.models import Match
        
        # Check all expected columns exist
        expected_columns = [
            'id', 'league', 'home_team', 'away_team', 'start_time',
            'opening_home_odd', 'opening_away_odd', 'opening_draw_odd',
            'current_home_odd', 'current_away_odd', 'current_draw_odd',
            'sharp_bookie', 'sharp_home_odd', 'sharp_draw_odd', 'sharp_away_odd',
            'highest_score_sent', 'last_deep_dive_time',
            'home_corners', 'away_corners',
            'home_yellow_cards', 'away_yellow_cards',
            'home_red_cards', 'away_red_cards',
            'home_xg', 'away_xg'
        ]
        
        for col in expected_columns:
            assert hasattr(Match, col), f"Match model missing column: {col}"
    
    def test_newslog_model_attributes(self):
        """Verify NewsLog model has all required attributes."""
        from src.database.models import NewsLog
        
        expected_columns = [
            'id', 'match_id', 'url', 'summary', 'score', 'category',
            'affected_team', 'timestamp', 'sent',
            'combo_suggestion', 'combo_reasoning', 'recommended_market',
            'primary_driver', 'closing_odds', 'odds_taken', 'clv_percent',
            'source'
        ]
        
        for col in expected_columns:
            assert hasattr(NewsLog, col), f"NewsLog model missing column: {col}"


class TestLeagueManagerFallback:
    """Test Tier 2 Fallback System."""
    
    def test_fallback_trigger_logic(self):
        """Test fallback trigger conditions."""
        from src.ingestion.league_manager import (
            should_activate_tier2_fallback,
            reset_daily_tier2_stats,
            increment_cycle
        )
        
        # Reset state
        reset_daily_tier2_stats()
        
        # With alerts, should not activate
        result = should_activate_tier2_fallback(alerts_sent=1, high_potential_count=0)
        assert result == False
        
        # Reset and test dry cycles
        reset_daily_tier2_stats()
        
        # First dry cycle - may or may not trigger depending on high_potential
        result = should_activate_tier2_fallback(alerts_sent=0, high_potential_count=0)
        # With 0 high_potential, should trigger immediately
        assert result == True
    
    def test_fallback_batch_rotation(self):
        """Test that fallback batches rotate correctly."""
        from src.ingestion.league_manager import (
            get_tier2_fallback_batch,
            reset_daily_tier2_stats,
            TIER_2_LEAGUES
        )
        
        reset_daily_tier2_stats()
        
        # Get multiple batches
        batch1 = get_tier2_fallback_batch()
        batch2 = get_tier2_fallback_batch()
        
        # Batches should be different (rotation)
        assert batch1 != batch2 or len(TIER_2_LEAGUES) <= 3
        
        # All items should be valid Tier 2 leagues
        for league in batch1 + batch2:
            assert league in TIER_2_LEAGUES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
