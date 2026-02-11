"""
Test MediaStack Budget (V1.0)

Tests for MediaStackBudget component.

Run: pytest tests/test_mediastack_budget.py -v
"""
import pytest
from unittest.mock import patch

from src.ingestion.mediastack_budget import MediaStackBudget, BudgetStatus


class TestMediaStackBudget:
    """Tests for MediaStackBudget class."""

    def test_initialization_with_default_allocations(self):
        """Budget should initialize with default allocations."""
        budget = MediaStackBudget()
        
        assert budget._monthly_limit == 0  # Unlimited
        assert budget._monthly_used == 0
        assert budget._daily_used == 0
        assert "search_provider" in budget._component_usage

    def test_initialization_with_custom_allocations(self):
        """Budget should initialize with custom allocations."""
        allocations = {"component1": 100, "component2": 200}
        budget = MediaStackBudget(allocations=allocations)
        
        assert "component1" in budget._component_usage
        assert "component2" in budget._component_usage

    def test_can_call_always_returns_true(self):
        """can_call should always return True for MediaStack (free unlimited)."""
        budget = MediaStackBudget()
        
        assert budget.can_call("search_provider") == True
        assert budget.can_call("any_component") == True

    def test_record_call_increments_usage(self):
        """record_call should increment usage counters."""
        budget = MediaStackBudget()
        
        budget.record_call("search_provider")
        assert budget._monthly_used == 1
        assert budget._daily_used == 1
        assert budget._component_usage["search_provider"] == 1

    def test_record_call_multiple_components(self):
        """record_call should track usage per component."""
        budget = MediaStackBudget()
        
        budget.record_call("search_provider")
        budget.record_call("news_radar")
        budget.record_call("search_provider")
        
        assert budget._monthly_used == 3
        assert budget._component_usage["search_provider"] == 2
        assert budget._component_usage["news_radar"] == 1

    def test_get_status_returns_complete_info(self):
        """get_status should return complete status information."""
        budget = MediaStackBudget()
        
        budget.record_call("search_provider")
        budget.record_call("news_radar")
        
        status = budget.get_status()
        
        assert isinstance(status, BudgetStatus)
        assert status.monthly_used == 2
        assert status.monthly_limit == 0  # Unlimited
        assert status.is_degraded == False
        assert status.is_disabled == False
        assert status.usage_percentage == 0.0
        assert "search_provider" in status.component_usage

    def test_reset_daily_clears_daily_counters(self):
        """reset_daily should clear daily counters."""
        budget = MediaStackBudget()
        
        budget.record_call("search_provider")
        budget.record_call("news_radar")
        
        budget.reset_daily()
        
        assert budget._daily_used == 0
        assert budget._monthly_used == 2  # Monthly should be preserved

    def test_reset_monthly_clears_monthly_counters(self):
        """reset_monthly should clear monthly counters."""
        # Create budget with custom allocations that include "news_radar"
        allocations = {"search_provider": 0, "news_radar": 0}
        budget = MediaStackBudget(allocations=allocations)
        
        budget.record_call("search_provider")
        budget.record_call("news_radar")
        
        budget.reset_monthly()
        
        assert budget._monthly_used == 0
        assert budget._daily_used == 0
        assert budget._component_usage["search_provider"] == 0
        assert budget._component_usage["news_radar"] == 0

    def test_status_shows_unlimited_for_media_stack(self):
        """Budget status should show MediaStack is unlimited."""
        budget = MediaStackBudget()
        
        budget.record_call("search_provider")
        status = budget.get_status()
        
        assert status.monthly_limit == 0
        assert status.daily_limit == 0
        assert status.is_degraded == False
        assert status.is_disabled == False

    @patch('src.ingestion.mediastack_budget.MEDIASTACK_BUDGET_ALLOCATION', {"search_provider": 0})
    def test_singleton_returns_same_instance(self):
        """Singleton should return the same instance."""
        from src.ingestion.mediastack_budget import get_mediastack_budget
        
        instance1 = get_mediastack_budget()
        instance2 = get_mediastack_budget()
        
        assert instance1 is instance2

    def test_record_call_with_unknown_component(self):
        """record_call should handle unknown components."""
        budget = MediaStackBudget()
        
        budget.record_call("unknown_component")
        
        assert "unknown_component" in budget._component_usage
        assert budget._component_usage["unknown_component"] == 1

    def test_multiple_calls_accumulate_correctly(self):
        """Multiple record_call calls should accumulate correctly."""
        budget = MediaStackBudget()
        
        for _ in range(10):
            budget.record_call("search_provider")
        
        assert budget._monthly_used == 10
        assert budget._daily_used == 10
        assert budget._component_usage["search_provider"] == 10
