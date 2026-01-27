"""
Test Suite for CLV Tracker V5.0

Verifica che:
1. CLV calculation è corretta
2. Edge cases gestiti (None, zero, invalid odds)
3. Statistics calculation funziona
4. Edge quality classification è corretta
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.clv_tracker import (
    CLVTracker,
    CLVStats,
    CLV_EXCELLENT_THRESHOLD,
    CLV_GOOD_THRESHOLD,
    CLV_MINIMUM_SAMPLE
)


class TestCLVCalculation:
    """Test CLV calculation logic."""
    
    def setup_method(self):
        """Setup tracker for each test."""
        self.tracker = CLVTracker(margin=0.05)
    
    def test_positive_clv(self):
        """Test positive CLV when we beat the closing line."""
        # We took 2.20, closed at 2.00 → we got better odds
        clv = self.tracker.calculate_clv(odds_taken=2.20, closing_odds=2.00)
        assert clv is not None
        assert clv > 0, f"Expected positive CLV, got {clv}"
    
    def test_negative_clv(self):
        """Test negative CLV when closing line beat us."""
        # We took 1.80, closed at 2.00 → we got worse odds
        clv = self.tracker.calculate_clv(odds_taken=1.80, closing_odds=2.00)
        assert clv is not None
        assert clv < 0, f"Expected negative CLV, got {clv}"
    
    def test_zero_clv_same_odds(self):
        """Test near-zero CLV when odds are similar."""
        # Same odds (accounting for margin removal)
        clv = self.tracker.calculate_clv(odds_taken=2.00, closing_odds=2.00)
        assert clv is not None
        # Should be close to 0 (margin adjustment makes it slightly negative)
        assert -5 < clv < 5, f"Expected near-zero CLV, got {clv}"
    
    def test_none_odds_taken(self):
        """Test None odds_taken returns None."""
        clv = self.tracker.calculate_clv(odds_taken=None, closing_odds=2.00)
        assert clv is None
    
    def test_none_closing_odds(self):
        """Test None closing_odds returns None."""
        clv = self.tracker.calculate_clv(odds_taken=2.00, closing_odds=None)
        assert clv is None
    
    def test_invalid_odds_taken_below_one(self):
        """Test odds_taken <= 1.0 returns None."""
        clv = self.tracker.calculate_clv(odds_taken=1.0, closing_odds=2.00)
        assert clv is None
        
        clv = self.tracker.calculate_clv(odds_taken=0.5, closing_odds=2.00)
        assert clv is None
    
    def test_invalid_closing_odds_below_one(self):
        """Test closing_odds <= 1.0 returns None."""
        clv = self.tracker.calculate_clv(odds_taken=2.00, closing_odds=1.0)
        assert clv is None
        
        clv = self.tracker.calculate_clv(odds_taken=2.00, closing_odds=0.8)
        assert clv is None
    
    def test_zero_odds(self):
        """Test zero odds returns None (no division by zero)."""
        clv = self.tracker.calculate_clv(odds_taken=0, closing_odds=2.00)
        assert clv is None
        
        clv = self.tracker.calculate_clv(odds_taken=2.00, closing_odds=0)
        assert clv is None
    
    def test_high_odds(self):
        """Test CLV calculation with high odds (longshots)."""
        # Longshot: took 10.00, closed at 8.00
        clv = self.tracker.calculate_clv(odds_taken=10.00, closing_odds=8.00)
        assert clv is not None
        assert clv > 0, "Should be positive CLV for better longshot odds"
    
    def test_low_odds(self):
        """Test CLV calculation with low odds (heavy favorites)."""
        # Heavy favorite: took 1.20, closed at 1.15
        # Note: With margin removal, closing 1.15 becomes ~1.21 fair odds
        # So taking 1.20 is actually WORSE than fair closing
        clv = self.tracker.calculate_clv(odds_taken=1.20, closing_odds=1.15)
        assert clv is not None
        # CLV can be negative here due to margin adjustment
        # The important thing is it doesn't crash and returns a valid number
        assert -10 < clv < 10, f"CLV should be reasonable, got {clv}"


class TestCLVStatsCalculation:
    """Test CLV statistics calculation."""
    
    def setup_method(self):
        """Setup tracker for each test."""
        self.tracker = CLVTracker()
    
    def test_empty_clv_values(self):
        """Test stats with empty CLV list."""
        stats = self.tracker._calculate_stats(total_bets=10, clv_values=[])
        
        assert stats.total_bets == 10
        assert stats.bets_with_clv == 0
        assert stats.avg_clv == 0.0
        assert stats.edge_quality == "INSUFFICIENT_DATA"
    
    def test_single_clv_value(self):
        """Test stats with single CLV value."""
        stats = self.tracker._calculate_stats(total_bets=1, clv_values=[3.5])
        
        assert stats.bets_with_clv == 1
        assert stats.avg_clv == 3.5
        assert stats.median_clv == 3.5
        assert stats.positive_clv_rate == 100.0
        assert stats.edge_quality == "INSUFFICIENT_DATA"  # n < 20
    
    def test_mixed_clv_values(self):
        """Test stats with mixed positive/negative CLV."""
        clv_values = [2.0, -1.0, 3.0, -0.5, 1.5]
        stats = self.tracker._calculate_stats(total_bets=5, clv_values=clv_values)
        
        assert stats.bets_with_clv == 5
        assert stats.avg_clv == 1.0  # (2-1+3-0.5+1.5)/5 = 1.0
        assert stats.positive_clv_rate == 60.0  # 3/5 positive
        assert stats.min_clv == -1.0
        assert stats.max_clv == 3.0
    
    def test_edge_quality_excellent(self):
        """Test EXCELLENT edge quality classification."""
        # Need n >= 20 and avg_clv >= 2.0
        clv_values = [2.5] * 25  # 25 bets with +2.5% CLV each
        stats = self.tracker._calculate_stats(total_bets=25, clv_values=clv_values)
        
        assert stats.edge_quality == "EXCELLENT"
    
    def test_edge_quality_good(self):
        """Test GOOD edge quality classification."""
        # Need n >= 20 and 0.5 <= avg_clv < 2.0
        clv_values = [1.0] * 25  # 25 bets with +1.0% CLV each
        stats = self.tracker._calculate_stats(total_bets=25, clv_values=clv_values)
        
        assert stats.edge_quality == "GOOD"
    
    def test_edge_quality_marginal(self):
        """Test MARGINAL edge quality classification."""
        # Need n >= 20 and 0 < avg_clv < 0.5
        clv_values = [0.3] * 25  # 25 bets with +0.3% CLV each
        stats = self.tracker._calculate_stats(total_bets=25, clv_values=clv_values)
        
        assert stats.edge_quality == "MARGINAL"
    
    def test_edge_quality_no_edge(self):
        """Test NO_EDGE quality classification."""
        # Need n >= 20 and avg_clv <= 0
        clv_values = [-0.5] * 25  # 25 bets with -0.5% CLV each
        stats = self.tracker._calculate_stats(total_bets=25, clv_values=clv_values)
        
        assert stats.edge_quality == "NO_EDGE"
    
    def test_edge_quality_insufficient_data(self):
        """Test INSUFFICIENT_DATA classification."""
        # n < 20
        clv_values = [5.0] * 15  # Only 15 bets
        stats = self.tracker._calculate_stats(total_bets=15, clv_values=clv_values)
        
        assert stats.edge_quality == "INSUFFICIENT_DATA"


class TestCLVStatsToDict:
    """Test CLVStats serialization."""
    
    def test_to_dict(self):
        """Test CLVStats.to_dict() method."""
        stats = CLVStats(
            total_bets=100,
            bets_with_clv=80,
            avg_clv=1.5678,
            median_clv=1.2345,
            positive_clv_rate=65.4321,
            std_dev=2.3456,
            min_clv=-5.1234,
            max_clv=8.9876,
            edge_quality="GOOD"
        )
        
        d = stats.to_dict()
        
        assert d['total_bets'] == 100
        assert d['bets_with_clv'] == 80
        assert d['avg_clv'] == 1.57  # Rounded to 2 decimals
        assert d['median_clv'] == 1.23
        assert d['positive_clv_rate'] == 65.4  # Rounded to 1 decimal
        assert d['edge_quality'] == "GOOD"


class TestCLVConstants:
    """Test CLV threshold constants."""
    
    def test_excellent_threshold(self):
        """Verify EXCELLENT threshold is 2.0%."""
        assert CLV_EXCELLENT_THRESHOLD == 2.0
    
    def test_good_threshold(self):
        """Verify GOOD threshold is 0.5%."""
        assert CLV_GOOD_THRESHOLD == 0.5
    
    def test_minimum_sample(self):
        """Verify minimum sample is 20."""
        assert CLV_MINIMUM_SAMPLE == 20


class TestCLVMarginAdjustment:
    """Test that margin adjustment works correctly."""
    
    def test_margin_affects_clv(self):
        """Test that different margins give different CLV."""
        tracker_5pct = CLVTracker(margin=0.05)
        tracker_10pct = CLVTracker(margin=0.10)
        
        clv_5pct = tracker_5pct.calculate_clv(odds_taken=2.00, closing_odds=2.00)
        clv_10pct = tracker_10pct.calculate_clv(odds_taken=2.00, closing_odds=2.00)
        
        # Higher margin = higher fair odds = lower CLV for same taken odds
        assert clv_5pct != clv_10pct
    
    def test_default_margin_is_5_percent(self):
        """Test default margin is 5%."""
        tracker = CLVTracker()
        assert tracker.margin == 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
