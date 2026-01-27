"""
Test Suite for V5.0 Sample Size Guards

Verifica che:
1. FROZEN state (n < 30): weights sempre = 1.0
2. WARMING_UP state (30-50): adjustments limitati a ±0.1
3. ACTIVE state (50+): full optimization
4. Edge cases: n=0, n=29, n=30, n=49, n=50

Questi test FALLIREBBERO con la versione V4.3 (MIN_SAMPLE_SIZE=8)
e PASSANO con V5.0 (MIN_SAMPLE_SIZE=30).
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.optimizer import (
    calculate_advanced_weight,
    get_optimizer_state,
    OptimizerState,
    MIN_SAMPLE_SIZE,
    WARMING_SAMPLE_SIZE,
    NEUTRAL_WEIGHT
)


class TestOptimizerState:
    """Test optimizer state machine."""
    
    def test_frozen_state_zero_bets(self):
        """n=0 should be FROZEN."""
        state = get_optimizer_state(0)
        assert state == OptimizerState.FROZEN
    
    def test_frozen_state_low_bets(self):
        """n=8 (old threshold) should still be FROZEN in V5.0."""
        state = get_optimizer_state(8)
        assert state == OptimizerState.FROZEN
    
    def test_frozen_state_boundary(self):
        """n=29 should be FROZEN (just below threshold)."""
        state = get_optimizer_state(29)
        assert state == OptimizerState.FROZEN
    
    def test_warming_state_at_threshold(self):
        """n=30 should be WARMING_UP (at threshold)."""
        state = get_optimizer_state(30)
        assert state == OptimizerState.WARMING_UP
    
    def test_warming_state_mid(self):
        """n=40 should be WARMING_UP."""
        state = get_optimizer_state(40)
        assert state == OptimizerState.WARMING_UP
    
    def test_warming_state_boundary(self):
        """n=49 should be WARMING_UP (just below ACTIVE)."""
        state = get_optimizer_state(49)
        assert state == OptimizerState.WARMING_UP
    
    def test_active_state_at_threshold(self):
        """n=50 should be ACTIVE."""
        state = get_optimizer_state(50)
        assert state == OptimizerState.ACTIVE
    
    def test_active_state_high(self):
        """n=100 should be ACTIVE."""
        state = get_optimizer_state(100)
        assert state == OptimizerState.ACTIVE


class TestFrozenStateWeights:
    """Test that FROZEN state always returns neutral weight."""
    
    def test_frozen_returns_neutral_positive_roi(self):
        """Even with positive ROI, FROZEN should return 1.0."""
        weight = calculate_advanced_weight(
            roi=0.5,  # 50% ROI - very good!
            sharpe=2.0,
            max_drawdown=0.0,
            n_samples=10,  # FROZEN
            sortino=3.0
        )
        assert weight == NEUTRAL_WEIGHT
    
    def test_frozen_returns_neutral_negative_roi(self):
        """Even with negative ROI, FROZEN should return 1.0."""
        weight = calculate_advanced_weight(
            roi=-0.3,  # -30% ROI - very bad!
            sharpe=-1.0,
            max_drawdown=-0.25,
            n_samples=15,  # FROZEN
            sortino=-0.5
        )
        assert weight == NEUTRAL_WEIGHT
    
    def test_frozen_ignores_drawdown_brake(self):
        """FROZEN should NOT trigger drawdown brake."""
        weight = calculate_advanced_weight(
            roi=-0.1,
            sharpe=0.0,
            max_drawdown=-0.30,  # Would trigger brake in ACTIVE
            n_samples=20,  # FROZEN
            sortino=0.0
        )
        # Should be 1.0, NOT 0.5 (brake not applied)
        assert weight == NEUTRAL_WEIGHT
    
    def test_frozen_at_boundary(self):
        """n=29 should still be FROZEN."""
        weight = calculate_advanced_weight(
            roi=0.3,
            sharpe=1.5,
            max_drawdown=-0.05,
            n_samples=29,  # Just below threshold
            sortino=2.0
        )
        assert weight == NEUTRAL_WEIGHT


class TestWarmingStateWeights:
    """Test that WARMING_UP state limits adjustments to ±0.1."""
    
    def test_warming_caps_increase(self):
        """WARMING_UP should cap weight increase to +0.1."""
        # With high ROI, uncapped weight would be > 1.1
        weight = calculate_advanced_weight(
            roi=0.5,  # Would give ~2.0 weight uncapped
            sharpe=2.0,
            max_drawdown=0.0,
            n_samples=35,  # WARMING_UP
            sortino=3.0,
            previous_weight=1.0
        )
        # Should be capped at 1.1 (previous + 0.1)
        assert weight <= 1.1
    
    def test_warming_caps_decrease(self):
        """WARMING_UP should cap weight decrease to -0.1."""
        weight = calculate_advanced_weight(
            roi=-0.3,  # Would give ~0.4 weight uncapped
            sharpe=-1.0,
            max_drawdown=-0.15,
            n_samples=40,  # WARMING_UP
            sortino=-0.5,
            previous_weight=1.0
        )
        # Should be capped at 0.9 (previous - 0.1)
        assert weight >= 0.9
    
    def test_warming_allows_small_adjustment(self):
        """WARMING_UP should allow adjustments within ±0.1."""
        weight = calculate_advanced_weight(
            roi=0.05,  # Small positive ROI
            sharpe=0.8,
            max_drawdown=-0.05,
            n_samples=45,
            sortino=1.0,
            previous_weight=1.0
        )
        # Should be slightly above 1.0 but within bounds
        assert 0.9 <= weight <= 1.1


class TestActiveStateWeights:
    """Test that ACTIVE state allows full optimization."""
    
    def test_active_allows_high_weight(self):
        """ACTIVE should allow weight > 1.1."""
        weight = calculate_advanced_weight(
            roi=0.4,  # Good ROI
            sharpe=2.0,
            max_drawdown=-0.05,
            n_samples=60,  # ACTIVE
            sortino=2.5,
            previous_weight=1.0
        )
        # Should be > 1.1 (not capped)
        assert weight > 1.1
    
    def test_active_allows_low_weight(self):
        """ACTIVE should allow weight < 0.9."""
        weight = calculate_advanced_weight(
            roi=-0.2,  # Bad ROI
            sharpe=0.2,
            max_drawdown=-0.15,
            n_samples=70,  # ACTIVE
            sortino=0.3,
            previous_weight=1.0
        )
        # Should be < 0.9 (not capped)
        assert weight < 0.9
    
    def test_active_triggers_drawdown_brake(self):
        """ACTIVE should trigger drawdown brake at -20%."""
        weight = calculate_advanced_weight(
            roi=0.1,  # Positive ROI
            sharpe=1.0,
            max_drawdown=-0.25,  # Triggers brake
            n_samples=80,  # ACTIVE
            sortino=1.2,
            previous_weight=1.0
        )
        # Drawdown brake should cut weight significantly
        assert weight < 0.8


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_zero_samples(self):
        """n=0 should return neutral weight."""
        weight = calculate_advanced_weight(
            roi=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            n_samples=0,
            sortino=0.0
        )
        assert weight == NEUTRAL_WEIGHT
    
    def test_none_sortino(self):
        """None sortino should fallback to sharpe."""
        weight = calculate_advanced_weight(
            roi=0.2,
            sharpe=1.5,
            max_drawdown=-0.05,
            n_samples=60,
            sortino=None  # Fallback to sharpe
        )
        # Should not crash and return valid weight
        assert 0.2 <= weight <= 2.0
    
    def test_none_previous_weight(self):
        """None previous_weight should default to 1.0."""
        weight = calculate_advanced_weight(
            roi=0.3,
            sharpe=1.5,
            max_drawdown=-0.05,
            n_samples=35,  # WARMING_UP
            sortino=2.0,
            previous_weight=None  # Should default to 1.0
        )
        # Should be capped relative to 1.0
        assert 0.9 <= weight <= 1.1
    
    def test_extreme_positive_roi(self):
        """Extreme positive ROI should be capped at MAX_WEIGHT."""
        weight = calculate_advanced_weight(
            roi=10.0,  # 1000% ROI - unrealistic
            sharpe=5.0,
            max_drawdown=0.0,
            n_samples=100,
            sortino=10.0
        )
        assert weight <= 2.0  # MAX_WEIGHT
    
    def test_extreme_negative_roi(self):
        """Extreme negative ROI should be capped at MIN_WEIGHT."""
        weight = calculate_advanced_weight(
            roi=-5.0,  # -500% ROI - unrealistic
            sharpe=-5.0,
            max_drawdown=-0.5,
            n_samples=100,
            sortino=-5.0
        )
        assert weight >= 0.2  # MIN_WEIGHT


class TestRegressionV43ToV50:
    """
    Regression tests that would FAIL on V4.3 and PASS on V5.0.
    
    These tests verify the critical fix: MIN_SAMPLE_SIZE increased from 8 to 30.
    """
    
    def test_8_bets_no_longer_adjusts(self):
        """
        V4.3 BUG: 8 bets would allow weight adjustment.
        V5.0 FIX: 8 bets should be FROZEN (no adjustment).
        """
        weight = calculate_advanced_weight(
            roi=0.5,  # Would give high weight in V4.3
            sharpe=2.0,
            max_drawdown=0.0,
            n_samples=8,  # V4.3 MIN_SAMPLE_SIZE
            sortino=3.0
        )
        # V4.3 would return ~1.5+, V5.0 should return 1.0
        assert weight == NEUTRAL_WEIGHT, \
            f"V5.0 regression: n=8 should be FROZEN, got weight={weight}"
    
    def test_20_bets_no_longer_adjusts(self):
        """
        V4.3 BUG: 20 bets would allow full adjustment.
        V5.0 FIX: 20 bets should be FROZEN.
        """
        weight = calculate_advanced_weight(
            roi=-0.3,  # Would give low weight in V4.3
            sharpe=-1.0,
            max_drawdown=-0.25,
            n_samples=20,
            sortino=-0.5
        )
        # V4.3 would return ~0.5, V5.0 should return 1.0
        assert weight == NEUTRAL_WEIGHT, \
            f"V5.0 regression: n=20 should be FROZEN, got weight={weight}"
    
    def test_min_sample_size_is_30(self):
        """Verify MIN_SAMPLE_SIZE constant is 30."""
        assert MIN_SAMPLE_SIZE == 30, \
            f"MIN_SAMPLE_SIZE should be 30, got {MIN_SAMPLE_SIZE}"
    
    def test_warming_sample_size_is_50(self):
        """Verify WARMING_SAMPLE_SIZE constant is 50."""
        assert WARMING_SAMPLE_SIZE == 50, \
            f"WARMING_SAMPLE_SIZE should be 50, got {WARMING_SAMPLE_SIZE}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
