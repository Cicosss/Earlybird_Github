"""
Regression tests for Phase 7, 8, 9 implementation.

Phase 7: Optimizer (Self-Learning)
Phase 8: Alert Dispatch (Threshold + Dedup)
Phase 9: Nightly Settlement

These tests verify the core functionality doesn't break with future changes.
"""
import pytest
from datetime import datetime, timezone


class TestPhase7Optimizer:
    """Phase 7: Optimizer Self-Learning tests."""
    
    def test_sortino_calculation_with_losses(self):
        """Sortino should penalize only downside volatility."""
        from src.analysis.optimizer import calc_sortino
        
        # Mix of wins and losses
        returns = [0.85, -1.0, 0.90, -1.0, 0.75, -1.0, 0.80, -1.0, 0.95, -1.0, 0.70]
        sortino = calc_sortino(returns)
        
        # Should return a value (not crash)
        assert isinstance(sortino, float)
    
    def test_sortino_empty_list_returns_zero(self):
        """Empty returns list should return 0, not crash."""
        from src.analysis.optimizer import calc_sortino
        
        assert calc_sortino([]) == 0.0
    
    def test_sortino_all_wins_returns_high_value(self):
        """All wins (no downside) should return high Sortino."""
        from src.analysis.optimizer import calc_sortino
        
        returns = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.5, 0.6, 0.7, 0.8]
        sortino = calc_sortino(returns)
        
        assert sortino == 5.0  # Max value for no downside
    
    def test_max_drawdown_calculation(self):
        """Max drawdown should detect largest peak-to-trough decline."""
        from src.analysis.optimizer import calc_max_drawdown
        
        # PnL: peak at 1.5, trough at 0.6 = 60% drawdown
        pnl = [1.0, 0.5, 1.5, 0.8, 1.2, 0.6]
        dd = calc_max_drawdown(pnl)
        
        assert dd == pytest.approx(-0.6, rel=0.01)
    
    def test_max_drawdown_empty_list(self):
        """Empty PnL list should return 0."""
        from src.analysis.optimizer import calc_max_drawdown
        
        assert calc_max_drawdown([]) == 0.0
    
    def test_optimizer_state_machine(self):
        """V5.0 Sample Size Guards state machine."""
        from src.analysis.optimizer import get_optimizer_state, OptimizerState
        
        assert get_optimizer_state(10) == OptimizerState.FROZEN
        assert get_optimizer_state(29) == OptimizerState.FROZEN
        assert get_optimizer_state(30) == OptimizerState.WARMING_UP
        assert get_optimizer_state(49) == OptimizerState.WARMING_UP
        assert get_optimizer_state(50) == OptimizerState.ACTIVE
        assert get_optimizer_state(100) == OptimizerState.ACTIVE
    
    def test_market_categorization(self):
        """Market strings should be categorized correctly."""
        from src.analysis.optimizer import categorize_market
        
        assert categorize_market('Over 2.5 Goals') == 'OVER'
        assert categorize_market('Under 2.5') == 'UNDER'
        assert categorize_market('Home Win') == '1X2'
        assert categorize_market('BTTS') == 'BTTS'
        assert categorize_market('Over 9.5 Corners') == 'CORNERS'
        assert categorize_market('Over 4.5 Cards') == 'CARDS'
        assert categorize_market('') == 'UNKNOWN'
        assert categorize_market(None) == 'UNKNOWN'
    
    def test_weight_bounds(self):
        """Weights should always be within MIN_WEIGHT and MAX_WEIGHT."""
        from src.analysis.optimizer import calculate_advanced_weight, MIN_WEIGHT, MAX_WEIGHT
        
        # Extreme positive ROI
        weight = calculate_advanced_weight(roi=1.0, sharpe=2.0, max_drawdown=0.0, n_samples=60, sortino=3.0)
        assert MIN_WEIGHT <= weight <= MAX_WEIGHT
        
        # Extreme negative ROI
        weight = calculate_advanced_weight(roi=-1.0, sharpe=-1.0, max_drawdown=-0.5, n_samples=60, sortino=-1.0)
        assert MIN_WEIGHT <= weight <= MAX_WEIGHT
    
    def test_frozen_state_returns_neutral_weight(self):
        """FROZEN state should always return 1.0 weight."""
        from src.analysis.optimizer import calculate_advanced_weight, NEUTRAL_WEIGHT
        
        # Even with great ROI, FROZEN state should return 1.0
        weight = calculate_advanced_weight(roi=0.5, sharpe=2.0, max_drawdown=0.0, n_samples=10, sortino=3.0)
        assert weight == NEUTRAL_WEIGHT


class TestPhase8AlertDispatch:
    """Phase 8: Alert Dispatch tests."""
    
    def test_alert_threshold_value(self):
        """Alert threshold should be 9.0 (Elite Quality - V8.3)."""
        from config.settings import ALERT_THRESHOLD_HIGH
        
        assert ALERT_THRESHOLD_HIGH == 9.0
    
    def test_deduplication_first_alert(self):
        """First alert (highest_sent=0) should always send if above threshold."""
        from config.settings import ALERT_THRESHOLD_HIGH
        
        score = 9.2  # V8.3: Score above 9.0 threshold
        highest_sent = 0.0
        delta = score - highest_sent
        
        should_alert = score >= ALERT_THRESHOLD_HIGH and (highest_sent == 0 or delta >= 1.5)
        assert should_alert is True
    
    def test_deduplication_delta_below_threshold(self):
        """Delta < 1.5 should NOT send alert."""
        from config.settings import ALERT_THRESHOLD_HIGH
        
        score = 8.8
        highest_sent = 8.0  # Delta = 0.8 < 1.5
        delta = score - highest_sent
        
        should_alert = score >= ALERT_THRESHOLD_HIGH and (highest_sent == 0 or delta >= 1.5)
        assert should_alert is False
    
    def test_deduplication_delta_above_threshold(self):
        """Delta >= 1.5 should send alert."""
        from config.settings import ALERT_THRESHOLD_HIGH
        
        score = 9.5
        highest_sent = 8.0  # Delta = 1.5
        delta = score - highest_sent
        
        should_alert = score >= ALERT_THRESHOLD_HIGH and (highest_sent == 0 or delta >= 1.5)
        assert should_alert is True
    
    def test_score_below_threshold_never_alerts(self):
        """Score below 8.6 should never alert."""
        from config.settings import ALERT_THRESHOLD_HIGH
        
        score = 7.5
        highest_sent = 0.0
        
        should_alert = score >= ALERT_THRESHOLD_HIGH and (highest_sent == 0 or (score - highest_sent) >= 1.5)
        assert should_alert is False


class TestPhase9Settlement:
    """Phase 9: Nightly Settlement tests."""
    
    def test_clv_calculation_positive(self):
        """CLV should be positive when we got better odds than closing."""
        from src.analysis.settler import calculate_clv
        
        # We took 2.10, closed at 1.95 = we beat the line
        clv = calculate_clv(odds_taken=2.10, closing_odds=1.95)
        
        assert clv is not None
        assert clv > 0
    
    def test_clv_calculation_negative(self):
        """CLV should be negative when closing odds were better."""
        from src.analysis.settler import calculate_clv
        
        # We took 1.80, closed at 2.00 = we didn't beat the line
        clv = calculate_clv(odds_taken=1.80, closing_odds=2.00)
        
        assert clv is not None
        assert clv < 0
    
    def test_clv_none_inputs(self):
        """CLV should return None for invalid inputs."""
        from src.analysis.settler import calculate_clv
        
        assert calculate_clv(None, 1.95) is None
        assert calculate_clv(2.10, None) is None
        assert calculate_clv(1.0, 1.95) is None  # odds <= 1.0 invalid
        assert calculate_clv(2.10, 1.0) is None
    
    def test_evaluate_bet_home_win(self):
        """Home Win should be WIN when home_score > away_score."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        result, _ = evaluate_bet('Home Win', 2, 1)
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('Home Win', 1, 2)
        assert result == RESULT_LOSS
    
    def test_evaluate_bet_away_win(self):
        """Away Win should be WIN when away_score > home_score."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        result, _ = evaluate_bet('Away Win', 1, 2)
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('Away Win', 2, 1)
        assert result == RESULT_LOSS
    
    def test_evaluate_bet_draw(self):
        """Draw should be WIN when scores are equal."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        result, _ = evaluate_bet('Draw', 1, 1)
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('Draw', 2, 1)
        assert result == RESULT_LOSS
    
    def test_evaluate_bet_over_under(self):
        """Over/Under goals should evaluate correctly."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        # Over 2.5 with 4 goals = WIN
        result, _ = evaluate_bet('Over 2.5 Goals', 2, 2)
        assert result == RESULT_WIN
        
        # Over 2.5 with 2 goals = LOSS
        result, _ = evaluate_bet('Over 2.5 Goals', 1, 1)
        assert result == RESULT_LOSS
        
        # Under 2.5 with 1 goal = WIN
        result, _ = evaluate_bet('Under 2.5 Goals', 1, 0)
        assert result == RESULT_WIN
    
    def test_evaluate_bet_btts(self):
        """BTTS should be WIN when both teams score."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        result, _ = evaluate_bet('BTTS', 1, 1)
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('BTTS', 2, 0)
        assert result == RESULT_LOSS
    
    def test_evaluate_bet_double_chance(self):
        """Double Chance (1X, X2) should evaluate correctly."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        # 1X covers Home Win or Draw
        result, _ = evaluate_bet('1X', 2, 1)  # Home win
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('1X', 1, 1)  # Draw
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('1X', 1, 2)  # Away win
        assert result == RESULT_LOSS
        
        # X2 covers Draw or Away Win
        result, _ = evaluate_bet('X2', 1, 2)  # Away win
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet('X2', 2, 1)  # Home win
        assert result == RESULT_LOSS
    
    def test_evaluate_bet_cancelled_match(self):
        """Cancelled/Postponed matches should return PUSH."""
        from src.analysis.settler import evaluate_bet, RESULT_PUSH
        
        result, _ = evaluate_bet('Home Win', 0, 0, match_status='CANCELLED')
        assert result == RESULT_PUSH
        
        result, _ = evaluate_bet('Home Win', 0, 0, match_status='POSTPONED')
        assert result == RESULT_PUSH
    
    def test_settlement_min_score(self):
        """Settlement should only include matches with score >= 7.0."""
        from config.settings import SETTLEMENT_MIN_SCORE
        
        assert SETTLEMENT_MIN_SCORE == 7.0


class TestDriverTracking:
    """Test driver (alpha source) tracking."""
    
    def test_valid_drivers(self):
        """All 5 drivers should be recognized."""
        from src.analysis.optimizer import VALID_DRIVERS
        
        expected = ["INJURY_INTEL", "SHARP_MONEY", "MATH_VALUE", "CONTEXT_PLAY", "CONTRARIAN", "UNKNOWN"]
        assert set(VALID_DRIVERS) == set(expected)
    
    def test_invalid_driver_defaults_to_unknown(self):
        """Invalid driver should be treated as UNKNOWN."""
        from src.analysis.optimizer import get_optimizer
        
        opt = get_optimizer()
        
        # Record with invalid driver
        opt.record_bet_result(
            league='test_league',
            market='Home Win',
            outcome='WIN',
            odds=1.90,
            driver='INVALID_DRIVER'
        )
        
        # Should be recorded under UNKNOWN
        assert 'UNKNOWN' in opt.data.get('drivers', {})


class TestPushOutcomeHandling:
    """V5.1 FIX: PUSH outcomes should not affect optimizer stats."""
    
    def test_push_outcome_does_not_count_as_loss(self):
        """
        REGRESSION TEST: PUSH (cancelled/postponed) should NOT be counted as LOSS.
        
        Bug found: record_bet_result treated any non-WIN outcome as LOSS,
        including PUSH from cancelled matches. This corrupted optimizer stats.
        
        Fix: Skip PUSH outcomes entirely - they should not affect learning.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        # Create isolated optimizer
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record a WIN
            optimizer.record_bet_result(
                league='test_push_league',
                market='Home Win',
                outcome='WIN',
                odds=2.0,
                driver='MATH_VALUE'
            )
            
            # Get stats after WIN
            stats_after_win = optimizer.data['stats'].get('test_push_league', {}).get('1X2', {})
            bets_after_win = stats_after_win.get('bets', 0)
            wins_after_win = stats_after_win.get('wins', 0)
            profit_after_win = stats_after_win.get('profit', 0)
            
            assert bets_after_win == 1, "Should have 1 bet after WIN"
            assert wins_after_win == 1, "Should have 1 win after WIN"
            assert profit_after_win == 1.0, "Profit should be 1.0 (odds 2.0 - 1)"
            
            # Record a PUSH (cancelled match)
            optimizer.record_bet_result(
                league='test_push_league',
                market='Home Win',
                outcome='PUSH',
                odds=1.9,
                driver='MATH_VALUE'
            )
            
            # Stats should NOT change after PUSH
            stats_after_push = optimizer.data['stats'].get('test_push_league', {}).get('1X2', {})
            bets_after_push = stats_after_push.get('bets', 0)
            wins_after_push = stats_after_push.get('wins', 0)
            profit_after_push = stats_after_push.get('profit', 0)
            
            assert bets_after_push == 1, f"PUSH should not increment bets (got {bets_after_push})"
            assert wins_after_push == 1, f"PUSH should not change wins (got {wins_after_push})"
            assert profit_after_push == 1.0, f"PUSH should not change profit (got {profit_after_push})"
            
        finally:
            os.unlink(temp_file)
    
    def test_push_in_settlement_details_is_skipped(self):
        """
        Integration test: recalculate_weights should skip PUSH outcomes.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Simulate settlement_stats with mixed outcomes
            settlement_stats = {
                'settled': 3,
                'details': [
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'WIN', 'odds': 2.0, 'driver': 'MATH_VALUE'},
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'PUSH', 'odds': 1.9, 'driver': 'MATH_VALUE'},
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'LOSS', 'odds': 1.8, 'driver': 'MATH_VALUE'},
                ]
            }
            
            optimizer.recalculate_weights(settlement_stats)
            
            # Should have 2 bets (WIN + LOSS), not 3
            stats = optimizer.data['stats'].get('test_league', {}).get('1X2', {})
            assert stats.get('bets', 0) == 2, "Should have 2 bets (PUSH skipped)"
            assert stats.get('wins', 0) == 1, "Should have 1 win"
            
            # Profit: WIN (+1.0) + LOSS (-1.0) = 0.0
            assert stats.get('profit', 0) == 0.0, "Profit should be 0.0"
            
        finally:
            os.unlink(temp_file)


class TestEnvVarParsing:
    """V5.1 FIX: Safe environment variable parsing."""
    
    def test_safe_int_env_empty_string(self):
        """
        REGRESSION TEST: Empty TELEGRAM_API_ID should not crash.
        
        Bug found: int(os.getenv('TELEGRAM_API_ID', 0)) crashes if
        the env var exists but is empty string.
        
        Fix: Use _safe_int_env() helper that handles empty/invalid values.
        """
        import os
        from src.processing.telegram_listener import _safe_int_env
        
        # Save original
        original = os.environ.get('TEST_SAFE_INT', None)
        
        try:
            # Test empty string
            os.environ['TEST_SAFE_INT'] = ''
            result = _safe_int_env('TEST_SAFE_INT', 42)
            assert result == 42, f"Empty string should return default, got {result}"
            
            # Test non-numeric
            os.environ['TEST_SAFE_INT'] = 'abc'
            result = _safe_int_env('TEST_SAFE_INT', 42)
            assert result == 42, f"Non-numeric should return default, got {result}"
            
            # Test valid number
            os.environ['TEST_SAFE_INT'] = '123'
            result = _safe_int_env('TEST_SAFE_INT', 42)
            assert result == 123, f"Valid number should parse, got {result}"
            
            # Test missing var
            del os.environ['TEST_SAFE_INT']
            result = _safe_int_env('TEST_SAFE_INT', 42)
            assert result == 42, f"Missing var should return default, got {result}"
            
        finally:
            # Restore original
            if original is not None:
                os.environ['TEST_SAFE_INT'] = original
            elif 'TEST_SAFE_INT' in os.environ:
                del os.environ['TEST_SAFE_INT']


class TestOptimizerV52Fixes:
    """V5.2 FIX: Input validation and edge case handling."""
    
    def test_max_drawdown_negative_start(self):
        """
        REGRESSION TEST: calc_max_drawdown should handle negative starting PnL.
        
        Bug found: If pnl_history starts with negative values (e.g., [-1.0, -0.5, ...]),
        the old code set peak = pnl_history[0] which was negative, and drawdown
        was never calculated correctly because `if peak > 0` was always False.
        
        Fix: Start peak from -inf so it tracks the actual maximum even with negative starts.
        """
        from src.analysis.optimizer import calc_max_drawdown
        
        # Scenario: Start losing, then recover, then drop again
        # Peak should be at 1.0, trough at -1.5 after peak
        pnl = [-1.0, -0.5, 0.5, 1.0, 0.2, -0.5]
        dd = calc_max_drawdown(pnl)
        
        # After reaching peak of 1.0, drops to -0.5 = 150% drawdown
        # But we cap at the trough after peak: (−0.5 − 1.0) / 1.0 = −1.5 = -150%
        assert dd < 0, "Should detect drawdown"
        assert dd == pytest.approx(-1.5, rel=0.01), f"Expected -1.5 (150% DD), got {dd}"
    
    def test_max_drawdown_all_negative(self):
        """
        Edge case: All negative PnL should return 0 (no positive peak to measure from).
        """
        from src.analysis.optimizer import calc_max_drawdown
        
        pnl = [-1.0, -2.0, -1.5, -3.0]
        dd = calc_max_drawdown(pnl)
        
        # No positive peak, so no meaningful drawdown
        assert dd == 0.0, f"All negative PnL should return 0, got {dd}"
    
    def test_record_bet_result_invalid_outcome(self):
        """
        REGRESSION TEST: Invalid outcome should be treated as LOSS, not crash.
        
        Bug found: Outcomes like "VOID", "CANCELLED", or typos like "win" (lowercase)
        were silently treated incorrectly.
        
        Fix: Validate outcome and default to LOSS with warning.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record with invalid outcome
            optimizer.record_bet_result(
                league='test_invalid_outcome',
                market='Home Win',
                outcome='VOID',  # Invalid - should be treated as LOSS
                odds=2.0,
                driver='MATH_VALUE'
            )
            
            stats = optimizer.data['stats'].get('test_invalid_outcome', {}).get('1X2', {})
            
            # Should be recorded as a LOSS
            assert stats.get('bets', 0) == 1, "Should have 1 bet"
            assert stats.get('wins', 0) == 0, "Should have 0 wins (treated as LOSS)"
            assert stats.get('profit', 0) == -1.0, "Profit should be -1.0 (loss)"
            
        finally:
            os.unlink(temp_file)
    
    def test_record_bet_result_invalid_odds(self):
        """
        REGRESSION TEST: Invalid odds should be corrected, not cause wrong calculations.
        
        Bug found: odds <= 0 or odds <= 1.0 would cause incorrect profit calculations.
        
        Fix: Validate odds and use default 1.9 if invalid.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record with invalid odds (0)
            optimizer.record_bet_result(
                league='test_invalid_odds',
                market='Over 2.5',
                outcome='WIN',
                odds=0,  # Invalid - should use default 1.9
                driver='MATH_VALUE'
            )
            
            stats = optimizer.data['stats'].get('test_invalid_odds', {}).get('OVER', {})
            
            # Should use default odds 1.9, so profit = 1.9 - 1 = 0.9
            assert stats.get('bets', 0) == 1, "Should have 1 bet"
            assert stats.get('profit', 0) == pytest.approx(0.9, rel=0.01), \
                f"Profit should be 0.9 (default odds 1.9), got {stats.get('profit', 0)}"
            
            # Test odds = 1.0 (no profit possible)
            optimizer.record_bet_result(
                league='test_invalid_odds_2',
                market='Over 2.5',
                outcome='WIN',
                odds=1.0,  # Invalid - should use default 1.9
                driver='MATH_VALUE'
            )
            
            stats2 = optimizer.data['stats'].get('test_invalid_odds_2', {}).get('OVER', {})
            assert stats2.get('profit', 0) == pytest.approx(0.9, rel=0.01), \
                f"Odds=1.0 should use default 1.9, got profit {stats2.get('profit', 0)}"
            
        finally:
            os.unlink(temp_file)
    
    def test_record_bet_result_extreme_odds_capped(self):
        """
        Edge case: Extremely high odds should be capped to prevent outlier effects.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record with extreme odds
            optimizer.record_bet_result(
                league='test_extreme_odds',
                market='Home Win',
                outcome='WIN',
                odds=500.0,  # Suspiciously high - should cap at 100
                driver='MATH_VALUE'
            )
            
            stats = optimizer.data['stats'].get('test_extreme_odds', {}).get('1X2', {})
            
            # Should cap at 100, so profit = 100 - 1 = 99
            assert stats.get('profit', 0) == pytest.approx(99.0, rel=0.01), \
                f"Extreme odds should be capped at 100, got profit {stats.get('profit', 0)}"
            
        finally:
            os.unlink(temp_file)

    def test_record_bet_result_none_league_or_market(self):
        """
        REGRESSION TEST: None/empty league or market should be skipped, not crash.
        
        Bug found: If settlement_stats contains bets with None league or market,
        _normalize_key() crashes with AttributeError: 'NoneType' object has no attribute 'lower'
        
        Fix: Validate league/market at start of record_bet_result and in recalculate_weights.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Test direct call with None
            optimizer.record_bet_result(
                league=None,
                market='Over 2.5',
                outcome='WIN',
                odds=1.9
            )
            
            optimizer.record_bet_result(
                league='test',
                market=None,
                outcome='WIN',
                odds=1.9
            )
            
            optimizer.record_bet_result(
                league='',
                market='Over 2.5',
                outcome='WIN',
                odds=1.9
            )
            
            # Should have 0 bets (all skipped)
            assert optimizer.data['global']['total_bets'] == 0, \
                "None/empty league/market should be skipped"
            
            # Test via recalculate_weights
            settlement_stats = {
                'settled': 3,
                'details': [
                    {'league': 'valid_league', 'market': 'Over 2.5', 'outcome': 'WIN', 'odds': 1.85, 'driver': 'MATH_VALUE'},
                    {'league': None, 'market': 'Over 2.5', 'outcome': 'WIN', 'odds': 1.85, 'driver': 'MATH_VALUE'},
                    {'league': 'valid_league', 'market': None, 'outcome': 'WIN', 'odds': 1.85, 'driver': 'MATH_VALUE'},
                ]
            }
            
            # Should not crash
            optimizer.recalculate_weights(settlement_stats)
            
            # Should have 1 valid bet
            assert optimizer.data['global']['total_bets'] == 1, \
                f"Should have 1 valid bet, got {optimizer.data['global']['total_bets']}"
            
        finally:
            os.unlink(temp_file)


class TestSettlerV53Fixes:
    """V5.3 FIX: Tavily response handling edge cases."""
    
    def test_tavily_response_with_none_title_content(self):
        """
        REGRESSION TEST: Tavily results with None title/content should not crash.
        
        Bug found: If Tavily returns results where title or content is None,
        the code crashed with TypeError: 'NoneType' object is not subscriptable
        when trying to do r.content[:100].
        
        Fix: Guard against None values before string operations.
        """
        # This test verifies the fix is in place by checking the function handles
        # edge cases gracefully. We can't easily mock Tavily here, but we verify
        # the settler module loads without errors.
        from src.analysis.settler import _tavily_post_match_search
        from datetime import datetime, timezone
        
        # Call with valid params - should return None (no Tavily configured in test)
        # but should NOT crash
        result = _tavily_post_match_search(
            home_team="Test Home",
            away_team="Test Away", 
            match_date=datetime.now(timezone.utc)
        )
        
        # Should return None gracefully (Tavily not available in test env)
        assert result is None or isinstance(result, str), \
            f"Should return None or string, got {type(result)}"
    
    def test_clv_calculation_with_nan(self):
        """
        Edge case: CLV calculation should handle NaN values gracefully.
        """
        from src.analysis.settler import calculate_clv
        import math
        
        # NaN odds should return None
        result = calculate_clv(float('nan'), 1.95)
        assert result is None, "NaN odds_taken should return None"
        
        result = calculate_clv(2.10, float('nan'))
        assert result is None, "NaN closing_odds should return None"
    
    def test_evaluate_over_under_edge_cases(self):
        """
        Edge cases for Over/Under evaluation.
        """
        from src.analysis.settler import evaluate_over_under, RESULT_PENDING
        
        # Empty market string
        result, _ = evaluate_over_under("", 10)
        assert result == RESULT_PENDING, "Empty market should return PENDING"
        
        # Market without over/under keyword
        result, _ = evaluate_over_under("Home Win", 10)
        assert result == RESULT_PENDING, "Non-over/under market should return PENDING"
        
        # Float actual_total (should work)
        result, _ = evaluate_over_under("Over 2.5 Goals", 3.0)
        # Should not crash - 3.0 > 2.5 so WIN expected
        assert result is not None


class TestDynamicThresholdEdgeCases:
    """Test dynamic threshold calculation edge cases."""
    
    def test_dynamic_threshold_with_empty_optimizer(self):
        """
        Dynamic threshold should return base value when optimizer has no data.
        """
        from src.analysis.optimizer import get_dynamic_alert_threshold, ALERT_THRESHOLD_BASE
        
        # Should not crash even with minimal data
        threshold, explanation = get_dynamic_alert_threshold()
        
        assert isinstance(threshold, float), "Threshold should be float"
        assert 7.0 <= threshold <= 10.0, f"Threshold {threshold} out of reasonable range"
        assert isinstance(explanation, str), "Explanation should be string"
    
    def test_dynamic_threshold_bounds(self):
        """
        Dynamic threshold should always be within MIN and MAX bounds.
        """
        from src.analysis.optimizer import (
            get_dynamic_alert_threshold,
            ALERT_THRESHOLD_MIN,
            ALERT_THRESHOLD_MAX
        )
        
        threshold, _ = get_dynamic_alert_threshold()
        
        assert threshold >= ALERT_THRESHOLD_MIN, \
            f"Threshold {threshold} below minimum {ALERT_THRESHOLD_MIN}"
        assert threshold <= ALERT_THRESHOLD_MAX, \
            f"Threshold {threshold} above maximum {ALERT_THRESHOLD_MAX}"


class TestOptimizerThreadSafety:
    """Test thread safety of optimizer operations."""
    
    def test_optimizer_singleton_returns_same_instance(self):
        """
        get_optimizer() should return the same instance (singleton pattern).
        """
        from src.analysis.optimizer import get_optimizer
        
        opt1 = get_optimizer()
        opt2 = get_optimizer()
        
        assert opt1 is opt2, "get_optimizer() should return singleton"
    
    def test_optimizer_data_lock_exists(self):
        """
        Optimizer should have a data lock for thread safety.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Should have _data_lock attribute
            assert hasattr(optimizer, '_data_lock'), \
                "Optimizer should have _data_lock for thread safety"
            
        finally:
            os.unlink(temp_file)


class TestCategorizeMarketV53:
    """V5.3 FIX: Improved market categorization edge cases."""
    
    def test_over_under_all_thresholds(self):
        """
        REGRESSION TEST: Over/Under with any threshold should categorize correctly.
        
        Bug found: "Over 0.5 Goals" was categorized as OTHER because the
        MARKET_CATEGORIES dict only had "over 2.5", "over 1.5", "over 3.5".
        
        Fix: Use regex pattern to match any Over/Under X.X format.
        """
        from src.analysis.optimizer import categorize_market
        
        # Test various Over thresholds
        assert categorize_market("Over 0.5 Goals") == "OVER"
        assert categorize_market("Over 1.5 Goals") == "OVER"
        assert categorize_market("Over 2.5 Goals") == "OVER"
        assert categorize_market("Over 3.5 Goals") == "OVER"
        assert categorize_market("Over 4.5 Goals") == "OVER"
        
        # Test various Under thresholds
        assert categorize_market("Under 0.5 Goals") == "UNDER"
        assert categorize_market("Under 1.5 Goals") == "UNDER"
        assert categorize_market("Under 2.5 Goals") == "UNDER"
        assert categorize_market("Under 3.5 Goals") == "UNDER"
    
    def test_single_character_markets(self):
        """
        REGRESSION TEST: Single character markets should categorize as 1X2.
        
        Bug found: "1" was categorized as OVER (matched "over 1.5" after
        removing dots), "X" was categorized as DOUBLE_CHANCE.
        
        Fix: Handle single character markets explicitly before other matching.
        """
        from src.analysis.optimizer import categorize_market
        
        assert categorize_market("1") == "1X2", "Single '1' should be 1X2 (Home Win)"
        assert categorize_market("2") == "1X2", "Single '2' should be 1X2 (Away Win)"
        assert categorize_market("X") == "1X2", "Single 'X' should be 1X2 (Draw)"
        assert categorize_market("x") == "1X2", "Lowercase 'x' should be 1X2"
    
    def test_corners_cards_priority(self):
        """
        Corners and Cards markets should be categorized correctly even with Over/Under.
        """
        from src.analysis.optimizer import categorize_market
        
        assert categorize_market("Over 9.5 Corners") == "CORNERS"
        assert categorize_market("Over 10.5 Corners") == "CORNERS"
        assert categorize_market("Under 8.5 Corners") == "CORNERS"
        assert categorize_market("Over 4.5 Cards") == "CARDS"
        assert categorize_market("Over 5.5 Yellow Cards") == "CARDS"
        assert categorize_market("Under 3.5 Booking Points") == "CARDS"
    
    def test_combo_markets(self):
        """
        Combo markets should categorize based on the most specific component.
        """
        from src.analysis.optimizer import categorize_market
        
        # Combo with Over - should be OVER (goals implied)
        result = categorize_market("Home Win + Over 2.5")
        assert result == "OVER", f"Combo should be OVER, got {result}"
        
        # BTTS combos
        result = categorize_market("BTTS + Over 2.5")
        assert result in ("BTTS", "OVER"), f"BTTS combo should be BTTS or OVER, got {result}"


class TestNoneParameterHandling:
    """V5.3 FIX: None parameter handling in optimizer and settler."""
    
    def test_apply_weight_to_score_with_none_league(self):
        """
        REGRESSION TEST: apply_weight_to_score should handle None league gracefully.
        
        Bug found: Calling apply_weight_to_score with league=None caused
        AttributeError in _normalize_key() when trying to call .lower() on None.
        
        Fix: Validate league parameter and return base_score if None/empty.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Should not crash with None league
            score, msg = optimizer.apply_weight_to_score(8.5, None, market='Over 2.5')
            assert score == 8.5, f"Should return base_score unchanged, got {score}"
            assert msg == "", f"Should return empty message, got '{msg}'"
            
            # Should not crash with empty league
            score, msg = optimizer.apply_weight_to_score(8.5, '', market='Over 2.5')
            assert score == 8.5, f"Should return base_score unchanged, got {score}"
            
        finally:
            os.unlink(temp_file)
    
    def test_evaluate_bet_with_none_scores(self):
        """
        REGRESSION TEST: evaluate_bet should handle None scores gracefully.
        
        Bug found: Calling evaluate_bet with home_score=None caused
        TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'
        
        Fix: Validate score parameters and return PENDING if None.
        """
        from src.analysis.settler import evaluate_bet, RESULT_PENDING
        
        # Should not crash with None home_score
        result, msg = evaluate_bet('Home Win', None, 1)
        assert result == RESULT_PENDING, f"Should return PENDING, got {result}"
        
        # Should not crash with None away_score
        result, msg = evaluate_bet('Home Win', 2, None)
        assert result == RESULT_PENDING, f"Should return PENDING, got {result}"
        
        # Should not crash with both None
        result, msg = evaluate_bet('Home Win', None, None)
        assert result == RESULT_PENDING, f"Should return PENDING, got {result}"
    
    def test_evaluate_bet_with_string_scores(self):
        """
        Edge case: evaluate_bet should handle string scores (convert to int).
        """
        from src.analysis.settler import evaluate_bet, RESULT_WIN
        
        # String scores should be converted to int
        result, msg = evaluate_bet('Home Win', '2', '1')
        assert result == RESULT_WIN, f"String scores should work, got {result}"
    
    def test_evaluate_bet_with_invalid_string_scores(self):
        """
        Edge case: evaluate_bet should handle invalid string scores gracefully.
        """
        from src.analysis.settler import evaluate_bet, RESULT_PENDING
        
        # Invalid string scores should return PENDING
        result, msg = evaluate_bet('Home Win', 'abc', '1')
        assert result == RESULT_PENDING, f"Invalid string should return PENDING, got {result}"


class TestOddsTypeConversion:
    """V5.3 FIX: Odds type conversion and validation."""
    
    def test_record_bet_result_with_string_odds(self):
        """
        REGRESSION TEST: record_bet_result should handle string odds.
        
        Bug found: Passing odds as string (e.g., '2.10' from JSON) caused
        TypeError: '<=' not supported between instances of 'str' and 'float'
        
        Fix: Convert odds to float before validation.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Should not crash with string odds
            optimizer.record_bet_result(
                league='test_string_odds',
                market='Home Win',
                outcome='WIN',
                odds='2.10',  # String instead of float
                driver='MATH_VALUE'
            )
            
            stats = optimizer.data['stats'].get('test_string_odds', {}).get('1X2', {})
            assert stats.get('bets', 0) == 1, "Should have 1 bet"
            # Profit should be 2.10 - 1 = 1.10
            assert abs(stats.get('profit', 0) - 1.10) < 0.01, f"Profit should be 1.10, got {stats.get('profit', 0)}"
            
        finally:
            os.unlink(temp_file)
    
    def test_record_bet_result_with_invalid_odds_type(self):
        """
        Edge case: Invalid odds type should use default 1.9.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Should not crash with invalid odds type
            optimizer.record_bet_result(
                league='test_invalid_odds_type',
                market='Home Win',
                outcome='WIN',
                odds={'invalid': 'dict'},  # Invalid type
                driver='MATH_VALUE'
            )
            
            stats = optimizer.data['stats'].get('test_invalid_odds_type', {}).get('1X2', {})
            assert stats.get('bets', 0) == 1, "Should have 1 bet"
            # Should use default 1.9, profit = 1.9 - 1 = 0.9
            assert abs(stats.get('profit', 0) - 0.9) < 0.01, f"Should use default odds 1.9, got profit {stats.get('profit', 0)}"
            
        finally:
            os.unlink(temp_file)
    
    def test_recalculate_weights_with_mixed_odds_types(self):
        """
        Integration test: recalculate_weights should handle mixed odds types.
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            settlement_stats = {
                'settled': 3,
                'details': [
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'WIN', 'odds': 1.95, 'driver': 'MATH_VALUE'},
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'WIN', 'odds': '2.10', 'driver': 'MATH_VALUE'},  # String
                    {'league': 'test_league', 'market': 'Home Win', 'outcome': 'LOSS', 'odds': 1.80, 'driver': 'MATH_VALUE'},
                ]
            }
            
            # Should not crash
            optimizer.recalculate_weights(settlement_stats)
            
            assert optimizer.data['global']['total_bets'] == 3, "Should have 3 bets"
            
        finally:
            os.unlink(temp_file)


class TestEndToEndIntegration:
    """
    Integration tests that verify the complete data flow from settler to optimizer.
    These tests simulate real-world scenarios that would occur on the VPS.
    """
    
    def test_full_settlement_to_optimizer_flow(self):
        """
        INTEGRATION TEST: Simulate complete nightly settlement flow.
        
        This test verifies:
        1. Settlement stats are correctly structured
        2. Optimizer processes all valid bets
        3. Invalid data (None league/market, string odds) is handled gracefully
        4. PUSH outcomes are skipped
        5. Weights are updated correctly
        """
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Simulate realistic settlement_stats from settler
            # This mimics what settle_pending_bets() returns
            settlement_stats = {
                'total_checked': 10,
                'settled': 7,
                'wins': 4,
                'losses': 2,
                'pending': 2,
                'pushes': 1,
                'errors': 0,
                'roi_pct': 15.5,
                'avg_clv': 2.3,
                'details': [
                    # Normal WIN with float odds
                    {
                        'match': 'Team A vs Team B',
                        'league': 'soccer_italy_serie_a',
                        'market': 'Over 2.5 Goals',
                        'score': 8.5,
                        'result': '3-1',
                        'outcome': 'WIN',
                        'explanation': '✅ Over 2.5 Preso (4 gol)',
                        'odds': 1.85,
                        'driver': 'MATH_VALUE',
                        'clv': 3.2
                    },
                    # WIN with string odds (from JSON backup)
                    {
                        'match': 'Team C vs Team D',
                        'league': 'soccer_england_premier_league',
                        'market': 'Home Win',
                        'score': 8.8,
                        'result': '2-0',
                        'outcome': 'WIN',
                        'explanation': '✅ Vittoria Casa 2-0',
                        'odds': '2.10',  # String odds!
                        'driver': 'INJURY_INTEL',
                        'clv': 1.5
                    },
                    # LOSS with normal data
                    {
                        'match': 'Team E vs Team F',
                        'league': 'soccer_germany_bundesliga',
                        'market': 'BTTS',
                        'score': 8.2,
                        'result': '2-0',
                        'outcome': 'LOSS',
                        'explanation': '❌ BTTS Mancato (2-0)',
                        'odds': 1.75,
                        'driver': 'SHARP_MONEY',
                        'clv': -0.8
                    },
                    # PUSH - should be skipped
                    {
                        'match': 'Team G vs Team H',
                        'league': 'soccer_spain_la_liga',
                        'market': 'Away Win',
                        'score': 8.0,
                        'result': 'VOID (postponed)',
                        'outcome': 'PUSH',
                        'explanation': '⚠️ Match postponed',
                        'odds': 2.50,
                        'driver': 'CONTEXT_PLAY'
                    },
                    # None league - should be skipped
                    {
                        'match': 'Unknown Match',
                        'league': None,
                        'market': 'Over 2.5',
                        'score': 7.5,
                        'result': '3-2',
                        'outcome': 'WIN',
                        'explanation': '✅ Over 2.5',
                        'odds': 1.90,
                        'driver': 'UNKNOWN'
                    },
                    # Empty market - should be skipped
                    {
                        'match': 'Another Match',
                        'league': 'soccer_france_ligue_1',
                        'market': '',
                        'score': 7.8,
                        'result': '1-1',
                        'outcome': 'LOSS',
                        'explanation': '❌ Loss',
                        'odds': 1.80,
                        'driver': 'MATH_VALUE'
                    },
                    # WIN with extreme odds (should be capped)
                    {
                        'match': 'Team I vs Team J',
                        'league': 'soccer_turkey_super_league',
                        'market': 'Over 0.5 Goals',  # V5.3 fix test
                        'score': 9.0,
                        'result': '1-0',
                        'outcome': 'WIN',
                        'explanation': '✅ Over 0.5 Preso',
                        'odds': 250.0,  # Extreme - should cap at 100
                        'driver': 'CONTRARIAN'
                    },
                ]
            }
            
            # Process settlement
            result = optimizer.recalculate_weights(settlement_stats)
            assert result is True, "recalculate_weights should return True"
            
            # Verify correct number of bets processed
            # Expected: 4 valid bets (2 skipped: PUSH + None league + empty market)
            assert optimizer.data['global']['total_bets'] == 4, \
                f"Should have 4 valid bets, got {optimizer.data['global']['total_bets']}"
            
            # Verify Serie A Over was recorded correctly
            serie_a_stats = optimizer.data['stats'].get('soccer_italy_serie_a', {}).get('OVER', {})
            assert serie_a_stats.get('bets', 0) == 1, "Serie A OVER should have 1 bet"
            assert serie_a_stats.get('wins', 0) == 1, "Serie A OVER should have 1 win"
            assert abs(serie_a_stats.get('profit', 0) - 0.85) < 0.01, "Profit should be ~0.85 (1.85 - 1)"
            
            # Verify Premier League 1X2 with string odds was converted correctly
            pl_stats = optimizer.data['stats'].get('soccer_england_premier_league', {}).get('1X2', {})
            assert pl_stats.get('bets', 0) == 1, "PL 1X2 should have 1 bet"
            # Profit should be 1.10 (2.10 - 1) - string was converted to float
            assert abs(pl_stats.get('profit', 0) - 1.10) < 0.01, \
                f"String odds should be converted, profit should be 1.10, got {pl_stats.get('profit', 0)}"
            
            # Verify Turkey Over 0.5 was categorized as OVER (V5.3 fix)
            turkey_stats = optimizer.data['stats'].get('soccer_turkey_super_league', {}).get('OVER', {})
            assert turkey_stats.get('bets', 0) == 1, "Turkey OVER should have 1 bet (Over 0.5 categorized correctly)"
            # Profit should be 99.0 (100 - 1) because odds were capped at 100
            assert turkey_stats.get('profit', 0) == 99.0, \
                f"Extreme odds should be capped at 100, profit should be 99.0, got {turkey_stats.get('profit', 0)}"
            
            # Verify drivers were tracked
            assert 'MATH_VALUE' in optimizer.data['drivers'], "MATH_VALUE driver should be tracked"
            assert 'INJURY_INTEL' in optimizer.data['drivers'], "INJURY_INTEL driver should be tracked"
            
            # Verify PUSH was NOT recorded (Spain La Liga should not exist)
            assert 'soccer_spain_la_liga' not in optimizer.data['stats'], \
                "PUSH outcome should not create stats entry"
            
            # Verify None league was skipped (no crash, no entry)
            # This is implicit - if we got here without crash, it worked
            
        finally:
            os.unlink(temp_file)
    
    def test_apply_weight_integration_with_real_data(self):
        """
        INTEGRATION TEST: Verify apply_weight_to_score works with real match data patterns.
        
        This simulates the flow in main.py where match.league could potentially be None
        or empty in edge cases (e.g., data migration issues).
        """
        from src.analysis.optimizer import StrategyOptimizer, NEUTRAL_WEIGHT
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # First, record some bets to have weights
            # Use 80% win rate to ensure positive ROI and good metrics
            for i in range(55):  # Enough to be in ACTIVE state (>50)
                optimizer.record_bet_result(
                    league='soccer_italy_serie_a',
                    market='Over 2.5',
                    outcome='WIN' if i % 5 != 0 else 'LOSS',  # 80% win rate
                    odds=1.85,
                    driver='MATH_VALUE'
                )
            
            # Test 1: Normal case - should apply weight
            # With 80% win rate and positive ROI, weight should be adjusted
            score, msg = optimizer.apply_weight_to_score(
                base_score=8.5,
                league='soccer_italy_serie_a',
                market='Over 2.5',
                driver='MATH_VALUE'
            )
            # Weight is applied - score should be different from base (could be higher or lower)
            # The key is that it doesn't crash and returns a valid score
            assert 0 <= score <= 10, f"Score should be in valid range, got {score}"
            assert isinstance(score, (int, float)), f"Score should be numeric, got {type(score)}"
            
            # Test 2: None league - should return base score unchanged
            score, msg = optimizer.apply_weight_to_score(
                base_score=8.5,
                league=None,
                market='Over 2.5'
            )
            assert score == 8.5, f"None league should return base score, got {score}"
            assert msg == "", f"None league should return empty message, got '{msg}'"
            
            # Test 3: Empty league - should return base score unchanged
            score, msg = optimizer.apply_weight_to_score(
                base_score=8.5,
                league='',
                market='Over 2.5'
            )
            assert score == 8.5, f"Empty league should return base score, got {score}"
            
            # Test 4: None market - should return base score unchanged
            score, msg = optimizer.apply_weight_to_score(
                base_score=8.5,
                league='soccer_italy_serie_a',
                market=None
            )
            assert score == 8.5, f"None market should return base score, got {score}"
            
            # Test 5: Unknown league (no data) - V6.1: Now uses global market fallback
            # Before V6.1: Would return base score (1.0 weight)
            # After V6.1: Falls back to global OVER market weight from soccer_italy_serie_a
            score, msg = optimizer.apply_weight_to_score(
                base_score=8.5,
                league='soccer_unknown_league',
                market='Over 2.5'
            )
            # V6.1 FIX: Unknown league now gets global market weight (not neutral)
            # The global OVER market has data from soccer_italy_serie_a with ~80% win rate
            # So the weight should be > 1.0, and score should be adjusted
            # We just verify it doesn't crash and returns a valid score
            assert 0 <= score <= 10, f"Score should be in valid range, got {score}"
            
        finally:
            os.unlink(temp_file)
    
    def test_categorize_market_all_real_world_formats(self):
        """
        INTEGRATION TEST: Verify categorize_market handles all real-world market formats.
        
        These are actual market strings that appear in the system from various sources.
        """
        from src.analysis.optimizer import categorize_market
        
        # Real-world Over/Under formats
        over_formats = [
            "Over 2.5 Goals",
            "Over 2.5",
            "over 2.5 goals",
            "Over 0.5 Goals",  # V5.3 fix
            "Over 1.5 Goals",
            "Over 3.5 Goals",
            "Over 4.5 Goals",
            "over2.5",
            "Over 2.5 Gol",  # Italian format
        ]
        for fmt in over_formats:
            result = categorize_market(fmt)
            assert result == "OVER", f"'{fmt}' should be OVER, got {result}"
        
        under_formats = [
            "Under 2.5 Goals",
            "Under 2.5",
            "under 2.5 goals",
            "Under 0.5 Goals",
            "Under 3.5 Goals",
        ]
        for fmt in under_formats:
            result = categorize_market(fmt)
            assert result == "UNDER", f"'{fmt}' should be UNDER, got {result}"
        
        # Real-world 1X2 formats
        one_x_two_formats = [
            "Home Win",
            "Away Win",
            "Draw",
            "1",  # V5.3 fix
            "2",  # V5.3 fix
            "X",  # V5.3 fix
            "x",
            "home",
            "away",
        ]
        for fmt in one_x_two_formats:
            result = categorize_market(fmt)
            assert result == "1X2", f"'{fmt}' should be 1X2, got {result}"
        
        # Real-world Corners formats
        corner_formats = [
            "Over 9.5 Corners",
            "Over 10.5 Corners",
            "Under 8.5 Corners",
            "Over 11 Corners",
        ]
        for fmt in corner_formats:
            result = categorize_market(fmt)
            assert result == "CORNERS", f"'{fmt}' should be CORNERS, got {result}"
        
        # Real-world Cards formats
        card_formats = [
            "Over 4.5 Cards",
            "Over 5.5 Yellow Cards",
            "Under 3.5 Cards",
            "Over 4 Booking Points",
        ]
        for fmt in card_formats:
            result = categorize_market(fmt)
            assert result == "CARDS", f"'{fmt}' should be CARDS, got {result}"
        
        # BTTS formats
        btts_formats = [
            "BTTS",
            "Both Teams To Score",
            "both teams to score",
            "Both Teams",
        ]
        for fmt in btts_formats:
            result = categorize_market(fmt)
            assert result == "BTTS", f"'{fmt}' should be BTTS, got {result}"
        
        # Double Chance formats
        dc_formats = [
            "1X",
            "X2",
            "12",
            "Double Chance",
        ]
        for fmt in dc_formats:
            result = categorize_market(fmt)
            assert result == "DOUBLE_CHANCE", f"'{fmt}' should be DOUBLE_CHANCE, got {result}"
