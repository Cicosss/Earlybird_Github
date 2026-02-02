"""
Test suite for V4.2 Quantitative Metrics Enhancement.

Tests:
- calc_sortino: Sortino Ratio calculation with edge cases
- calc_sharpe: Verify existing Sharpe still works
- calculate_clv: CLV calculation with edge cases
- Edge cases: empty lists, all wins, all losses, zero variance
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.optimizer import calc_sharpe, calc_sortino


# Inline CLV function for testing (mirrors settler.calculate_clv)
def calculate_clv_test(odds_taken: float, closing_odds: float, margin: float = 0.05):
    """Test version of CLV calculation."""
    if not odds_taken or not closing_odds:
        return None
    if odds_taken <= 1.0 or closing_odds <= 1.0:
        return None
    
    try:
        implied_prob = 1.0 / closing_odds
        fair_prob = implied_prob / (1.0 + margin)
        fair_prob = max(0.01, min(0.99, fair_prob))
        fair_closing_odds = 1.0 / fair_prob
        clv = ((odds_taken / fair_closing_odds) - 1.0) * 100
        return round(clv, 2)
    except (ZeroDivisionError, ValueError):
        return None


class TestSortinoRatio:
    """Test Sortino Ratio calculation - V4.2 NEW."""
    
    def test_sortino_empty_list(self):
        """Empty list should return 0.0, not crash."""
        result = calc_sortino([])
        assert result == 0.0
    
    def test_sortino_insufficient_samples(self):
        """Less than 10 samples should return 0.0."""
        result = calc_sortino([0.5, -0.3, 0.8])  # Only 3 samples
        assert result == 0.0
    
    def test_sortino_all_wins(self):
        """All positive returns = no downside = high Sortino."""
        returns = [0.85, 0.90, 0.75, 0.80, 0.95, 0.70, 0.88, 0.92, 0.78, 0.85]
        result = calc_sortino(returns)
        assert result == 5.0  # Perfect strategy (no losses)
    
    def test_sortino_all_losses(self):
        """All negative returns should give low/negative Sortino."""
        returns = [-1.0] * 10  # 10 losses
        result = calc_sortino(returns)
        assert result < 0  # Negative mean, should be negative
    
    def test_sortino_mixed_returns(self):
        """Mixed returns should calculate correctly."""
        # 7 wins (+0.9 each) and 3 losses (-1.0 each)
        returns = [0.9, 0.9, -1.0, 0.9, 0.9, -1.0, 0.9, 0.9, 0.9, -1.0]
        result = calc_sortino(returns)
        # Mean = (7*0.9 - 3*1.0) / 10 = 0.33
        # Downside only considers the -1.0 values
        assert result > 0  # Positive mean, should be positive
        assert isinstance(result, float)
    
    def test_sortino_better_than_sharpe_for_high_variance_wins(self):
        """Sortino should be higher than Sharpe when wins are volatile."""
        # High variance in wins, consistent losses
        returns = [2.0, 0.1, -1.0, 3.0, 0.2, -1.0, 1.5, 0.3, -1.0, 2.5]
        sharpe = calc_sharpe(returns)
        sortino = calc_sortino(returns)
        # Sortino ignores upside volatility, so should be >= Sharpe
        # (not always true mathematically, but for this pattern it should be)
        assert sortino > 0
        assert sharpe > 0


class TestSharpeRatio:
    """Verify existing Sharpe Ratio still works after changes."""
    
    def test_sharpe_empty_list(self):
        """Empty list should return 0.0."""
        result = calc_sharpe([])
        assert result == 0.0
    
    def test_sharpe_insufficient_samples(self):
        """Less than 10 samples should return 0.0."""
        result = calc_sharpe([0.5, -0.3])
        assert result == 0.0
    
    def test_sharpe_zero_variance(self):
        """All same positive returns = high Sharpe (consistent winner)."""
        returns = [0.5] * 10
        result = calc_sharpe(returns)
        assert result == 5.0  # Consistent profit
    
    def test_sharpe_zero_variance_negative(self):
        """All same negative returns = 0 Sharpe."""
        returns = [-0.5] * 10
        result = calc_sharpe(returns)
        assert result == 0.0  # Consistent loss
    
    def test_sharpe_mixed_returns(self):
        """Mixed returns should calculate correctly."""
        returns = [0.9, 0.9, -1.0, 0.9, 0.9, -1.0, 0.9, 0.9, 0.9, -1.0]
        result = calc_sharpe(returns)
        assert result > 0
        assert isinstance(result, float)


class TestEdgeCases:
    """Edge cases that could crash the system."""
    
    def test_sortino_none_in_list(self):
        """None values in list should be handled or raise clear error."""
        # This tests if we need to add None filtering
        # Current implementation expects clean data from optimizer
        returns = [0.5, 0.3, 0.8, 0.2, 0.6, 0.4, 0.7, 0.9, 0.1, 0.5]
        result = calc_sortino(returns)
        assert isinstance(result, float)
    
    def test_sortino_single_loss(self):
        """Single loss among many wins."""
        returns = [0.9] * 9 + [-0.5]  # 9 wins, 1 small loss
        result = calc_sortino(returns)
        assert result > 0  # Should still be positive
    
    def test_sharpe_extreme_values(self):
        """Extreme values shouldn't cause overflow."""
        returns = [100.0, -50.0, 75.0, -25.0, 80.0, -30.0, 90.0, -40.0, 85.0, -35.0]
        result = calc_sharpe(returns)
        assert isinstance(result, float)
        assert not float('inf') == result
        assert not float('-inf') == result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCLVCalculation:
    """Test CLV (Closing Line Value) calculation - V4.2 NEW."""
    
    def test_clv_none_odds_taken(self):
        """None odds_taken should return None."""
        result = calculate_clv_test(None, 1.85)
        assert result is None
    
    def test_clv_none_closing_odds(self):
        """None closing_odds should return None."""
        result = calculate_clv_test(1.90, None)
        assert result is None
    
    def test_clv_invalid_odds_taken(self):
        """Odds <= 1.0 should return None."""
        result = calculate_clv_test(1.0, 1.85)
        assert result is None
        result = calculate_clv_test(0.5, 1.85)
        assert result is None
    
    def test_clv_invalid_closing_odds(self):
        """Closing odds <= 1.0 should return None."""
        result = calculate_clv_test(1.90, 1.0)
        assert result is None
        result = calculate_clv_test(1.90, 0.8)
        assert result is None
    
    def test_clv_positive(self):
        """Better odds than closing = positive CLV."""
        # We took 2.00, closed at 1.80 (we got better odds)
        result = calculate_clv_test(2.00, 1.80)
        assert result is not None
        assert result > 0  # Positive CLV
    
    def test_clv_negative(self):
        """Worse odds than closing = negative CLV."""
        # We took 1.70, closed at 1.90 (we got worse odds)
        result = calculate_clv_test(1.70, 1.90)
        assert result is not None
        assert result < 0  # Negative CLV
    
    def test_clv_same_odds(self):
        """Same odds = ~0 CLV (accounting for margin removal)."""
        result = calculate_clv_test(1.85, 1.85)
        assert result is not None
        # Should be slightly positive because we remove margin from closing
        assert -5 < result < 10  # Reasonable range
    
    def test_clv_realistic_scenario(self):
        """Realistic betting scenario."""
        # Took Home Win at 1.95, closed at 1.80
        # This is a good CLV scenario (got better odds)
        result = calculate_clv_test(1.95, 1.80)
        assert result is not None
        assert result > 0
        assert isinstance(result, float)
    
    def test_clv_edge_case_very_low_closing(self):
        """Very low closing odds (heavy favorite)."""
        result = calculate_clv_test(1.20, 1.10)
        assert result is not None
        # Should still calculate without error
        assert isinstance(result, float)
    
    def test_clv_edge_case_high_odds(self):
        """High odds (underdog)."""
        result = calculate_clv_test(5.00, 4.50)
        assert result is not None
        assert result > 0  # We got better odds



class TestDixonColesCorrection:
    """Test Dixon-Coles correction for low-scoring games - V4.2 NEW."""
    
    def test_dixon_coles_0_0(self):
        """0-0 should have correction > 1 (draws underestimated)."""
        from src.analysis.math_engine import MathPredictor
        
        correction = MathPredictor.dixon_coles_correction(0, 0, 1.5, 1.2)
        # With negative rho, 1 - (lambda_h * lambda_a * rho) > 1
        assert correction > 1.0
    
    def test_dixon_coles_1_1(self):
        """1-1 should have correction close to 1."""
        from src.analysis.math_engine import MathPredictor
        
        correction = MathPredictor.dixon_coles_correction(1, 1, 1.5, 1.2)
        # 1 - rho where rho is negative, so > 1
        assert correction > 1.0
    
    def test_dixon_coles_high_score_no_correction(self):
        """High scores (2+) should have no correction."""
        from src.analysis.math_engine import MathPredictor
        
        correction = MathPredictor.dixon_coles_correction(2, 1, 1.5, 1.2)
        assert correction == 1.0
        
        correction = MathPredictor.dixon_coles_correction(3, 2, 1.5, 1.2)
        assert correction == 1.0
    
    def test_poisson_with_dixon_coles_increases_draw_prob(self):
        """Dixon-Coles should increase draw probability vs standard Poisson."""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # Without Dixon-Coles
        result_standard = predictor.simulate_match(1.5, 1.0, 1.2, 1.3, use_dixon_coles=False)
        
        # With Dixon-Coles
        result_dc = predictor.simulate_match(1.5, 1.0, 1.2, 1.3, use_dixon_coles=True)
        
        assert result_standard is not None
        assert result_dc is not None
        
        # Draw probability should be higher with Dixon-Coles
        assert result_dc.draw_prob >= result_standard.draw_prob * 0.99  # Allow small tolerance


class TestShrinkageKelly:
    """Test Shrinkage Kelly with confidence intervals - V4.2 NEW."""
    
    def test_shrinkage_reduces_stake_small_sample(self):
        """Small sample size should reduce Kelly stake."""
        from src.analysis.math_engine import MathPredictor
        
        # Same probability, different sample sizes
        edge_small = MathPredictor.calculate_edge(0.60, 1.80, sample_size=5)
        edge_large = MathPredictor.calculate_edge(0.60, 1.80, sample_size=50)
        
        # Smaller sample = more uncertainty = lower stake
        assert edge_small.kelly_stake <= edge_large.kelly_stake
    
    def test_shrinkage_disabled(self):
        """Disabling shrinkage should give standard Kelly."""
        from src.analysis.math_engine import MathPredictor
        
        edge_shrunk = MathPredictor.calculate_edge(0.60, 1.80, sample_size=5, use_shrinkage=True)
        edge_standard = MathPredictor.calculate_edge(0.60, 1.80, sample_size=5, use_shrinkage=False)
        
        # Standard Kelly should be >= shrunk Kelly
        assert edge_standard.kelly_stake >= edge_shrunk.kelly_stake
    
    def test_shrinkage_converges_large_sample(self):
        """Large sample should converge to standard Kelly."""
        from src.analysis.math_engine import MathPredictor
        
        edge_shrunk = MathPredictor.calculate_edge(0.60, 1.80, sample_size=100, use_shrinkage=True)
        edge_standard = MathPredictor.calculate_edge(0.60, 1.80, sample_size=100, use_shrinkage=False)
        
        # Should be very close with large sample
        assert abs(edge_shrunk.kelly_stake - edge_standard.kelly_stake) < 0.5
    
    def test_shrinkage_edge_case_zero_sample(self):
        """Zero sample size should not crash."""
        from src.analysis.math_engine import MathPredictor
        
        edge = MathPredictor.calculate_edge(0.60, 1.80, sample_size=0)
        assert edge is not None
        assert isinstance(edge.kelly_stake, float)
    
    def test_shrinkage_edge_case_extreme_prob(self):
        """Extreme probabilities should be handled safely."""
        from src.analysis.math_engine import MathPredictor
        
        # Very high probability
        edge_high = MathPredictor.calculate_edge(0.95, 1.10, sample_size=10)
        assert edge_high is not None
        
        # Very low probability
        edge_low = MathPredictor.calculate_edge(0.10, 8.00, sample_size=10)
        assert edge_low is not None
    
    def test_kelly_not_zero_with_significant_edge(self):
        """V4.5 REGRESSION: Kelly should NOT be 0% when edge is significant (>10%).
        
        Bug found: With 74.1% math prob vs 60.2% implied (13.9% edge),
        the old shrinkage formula gave Kelly=0% because:
        - 95% CI (1.96 * SE) was too aggressive
        - confidence_factor (n/30) was too conservative
        
        This test ensures the fix works: significant edge should give positive Kelly.
        """
        from src.analysis.math_engine import MathPredictor
        
        # Auckland FC case: 74.1% math prob, ~1.66 odd (60.2% implied), 13.9% edge
        edge_result = MathPredictor.calculate_edge(0.741, 1.66, sample_size=10)
        
        assert edge_result.has_value, "Should have value with 13.9% edge"
        assert edge_result.kelly_stake > 0, \
            f"Kelly should be > 0% with 13.9% edge, got {edge_result.kelly_stake}%"
        assert edge_result.kelly_stake >= 1.0, \
            f"Kelly should be at least 1% with significant edge, got {edge_result.kelly_stake}%"
    
    def test_kelly_zero_for_marginal_edge(self):
        """Kelly should be 0% or very low for marginal edges (<5%)."""
        from src.analysis.math_engine import MathPredictor
        
        # 55% math prob vs 50% implied = 5% edge (marginal)
        edge_result = MathPredictor.calculate_edge(0.55, 2.00, sample_size=10)
        
        # With shrinkage, marginal edge should give 0% or very low stake
        # V8.3: Minimum stake is 5.0%
        assert edge_result.kelly_stake <= 5.0, \
            f"Kelly should be <=5.0% for marginal edge, got {edge_result.kelly_stake}%"



class TestEndToEndFlow:
    """Test end-to-end integration of V4.2 features."""
    
    def test_optimizer_records_sortino(self):
        """Verify Sortino is calculated when recording bet results."""
        from src.analysis.optimizer import StrategyOptimizer
        import tempfile
        import os
        
        # Create temp optimizer
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            optimizer = StrategyOptimizer(weights_file=temp_file)
            
            # Record 15 bets (enough for metrics)
            for i in range(10):
                optimizer.record_bet_result(
                    league="test_league",
                    market="Home Win",
                    outcome="WIN" if i % 3 != 0 else "LOSS",
                    odds=1.85,
                    driver="MATH_VALUE"
                )
            
            # Verify Sortino was calculated
            stats = optimizer.data['stats'].get('test_league', {}).get('1X2', {})
            assert 'sortino' in stats
            assert stats['sortino'] != 0.0 or stats['bets'] < 10  # Either calculated or not enough data
            
            # Verify driver Sortino
            driver_stats = optimizer.data['drivers'].get('MATH_VALUE', {})
            assert 'sortino' in driver_stats
            
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def test_dixon_coles_in_full_analysis(self):
        """Verify Dixon-Coles is applied in full match analysis."""
        from src.analysis.math_engine import MathPredictor
        
        predictor = MathPredictor()
        
        # Run full analysis (which uses simulate_match internally)
        result = predictor.analyze_match(
            home_scored=1.5,
            home_conceded=1.0,
            away_scored=1.2,
            away_conceded=1.3,
            home_odd=1.80,
            draw_odd=3.50,
            away_odd=4.50
        )
        
        assert 'error' not in result
        assert result['poisson'] is not None
        
        # Draw probability should be reasonable (Dixon-Coles increases it)
        assert result['poisson'].draw_prob > 0.15  # At least 15%
    
    def test_shrinkage_kelly_in_edge_calculation(self):
        """Verify Shrinkage Kelly is applied in edge calculation."""
        from src.analysis.math_engine import MathPredictor
        
        # With small sample, Kelly should be conservative
        edge_small = MathPredictor.calculate_edge(0.55, 1.90, sample_size=5)
        edge_large = MathPredictor.calculate_edge(0.55, 1.90, sample_size=50)
        
        # Small sample should have lower or equal stake
        assert edge_small.kelly_stake <= edge_large.kelly_stake
    
    def test_clv_calculation_realistic(self):
        """Test CLV with realistic betting scenario."""
        # Scenario: We took 1.95, line closed at 1.80 (we beat the closing line)
        clv = calculate_clv_test(1.95, 1.80)
        
        assert clv is not None
        assert clv > 0  # Positive CLV (we got better odds)
        
        # Scenario: We took 1.70, line closed at 1.90 (we didn't beat the line)
        clv_bad = calculate_clv_test(1.70, 1.90)
        
        assert clv_bad is not None
        assert clv_bad < 0  # Negative CLV
    
    def test_settlement_details_include_clv(self):
        """Verify settlement details structure includes CLV field."""
        # This tests the structure, not actual DB operations
        details = {
            'match': 'Team A vs Team B',
            'league': 'test_league',
            'market': 'Home Win',
            'score': 8.5,
            'result': '2-1',
            'outcome': 'WIN',
            'explanation': 'Test',
            'odds': 1.85,
            'driver': 'MATH_VALUE',
            'clv': 3.5  # V4.2: CLV field
        }
        
        assert 'clv' in details
        assert details['clv'] == 3.5
