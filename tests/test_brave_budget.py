"""
Tests for Brave Budget Manager - V1.0

Tests budget management, tiered throttling, and reset behavior.
"""
import pytest
from datetime import datetime, timezone, timedelta
from src.ingestion.brave_budget import BudgetManager, BudgetStatus


class TestBraveBudgetManager:
    """Test suite for Brave BudgetManager."""
    
    def test_initialization(self):
        """Test that budget manager initializes correctly."""
        manager = BudgetManager(monthly_limit=6000)
        
        assert manager._monthly_limit == 6000
        assert manager._monthly_used == 0
        assert manager._daily_used == 0
        assert len(manager._component_usage) > 0
    
    def test_initialization_with_allocations(self):
        """Test initialization with custom allocations."""
        allocations = {
            "component1": 1000,
            "component2": 2000,
        }
        manager = BudgetManager(
            monthly_limit=6000,
            allocations=allocations
        )
        
        assert manager._allocations == allocations
        assert "component1" in manager._component_usage
        assert "component2" in manager._component_usage
    
    def test_can_call_normal_mode(self):
        """Test that calls are allowed in normal mode."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Should be allowed
        assert manager.can_call("component1") == True
        assert manager.can_call("component2") == True
    
    def test_can_call_degraded_mode(self):
        """Test that non-critical calls are throttled in degraded mode."""
        allocations = {"component1": 1000}
        manager = BudgetManager(monthly_limit=6000, allocations=allocations)
        
        # Use 90% of budget (5400 calls)
        manager._monthly_used = 5400
        
        # V10.0: In degraded mode (>90%), non-critical calls are throttled (return False)
        # First call should be throttled for non-critical components
        assert manager.can_call("component1") == False
        
        # Even if component has used less than 50% of allocation, still throttled in degraded mode
        manager._component_usage["component1"] = 500  # 50% of 1000
        assert manager.can_call("component1") == False
        
        # Critical components should still be allowed
        assert manager.can_call("main_pipeline") == True
    
    def test_can_call_disabled_mode(self):
        """Test that only critical calls are allowed in disabled mode."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Use 95% of budget (5700 calls)
        manager._monthly_used = 5700
        
        # Critical component should be allowed
        assert manager.can_call("main_pipeline") == True
        assert manager.can_call("settlement_clv") == True
        
        # Non-critical component should be blocked
        assert manager.can_call("component1") == False
    
    def test_can_call_with_is_critical_flag(self):
        """Test is_critical flag override."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Use 95% of budget
        manager._monthly_used = 5700
        
        # Non-critical component with is_critical=True should be allowed
        assert manager.can_call("component1", is_critical=True) == True
        
        # Non-critical component with is_critical=False should be blocked
        assert manager.can_call("component1", is_critical=False) == False
    
    def test_can_call_at_allocation_limit(self):
        """Test that calls are blocked at component allocation limit."""
        allocations = {"component1": 1000}
        manager = BudgetManager(monthly_limit=6000, allocations=allocations)
        
        # Should be allowed initially
        assert manager.can_call("component1") == True
        
        # Use up the allocation
        manager._component_usage["component1"] = 1000
        
        # Now should be blocked at allocation limit
        assert manager.can_call("component1") == False
    
    def test_record_call(self):
        """Test recording a call."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Record a call
        manager.record_call("component1")
        
        assert manager._monthly_used == 1
        assert manager._daily_used == 1
        assert manager._component_usage["component1"] == 1
        
        # Record another call for different component
        manager.record_call("component2")
        
        assert manager._monthly_used == 2
        assert manager._daily_used == 2
        assert manager._component_usage["component2"] == 1
    
    def test_get_status(self):
        """Test getting budget status."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Record some usage
        manager.record_call("component1")
        manager.record_call("component1")
        manager.record_call("component2")
        
        status = manager.get_status()
        
        assert isinstance(status, BudgetStatus)
        assert status.monthly_used == 3
        assert status.monthly_limit == 6000
        assert status.daily_used == 3
        assert status.usage_percentage == 0.05  # 3/6000 * 100
        assert status.is_degraded == False
        assert status.is_disabled == False
        assert "component1" in status.component_usage
        assert "component2" in status.component_usage
    
    def test_get_status_degraded_mode(self):
        """Test status in degraded mode."""
        manager = BudgetManager(monthly_limit=6000)
        manager._monthly_used = 5400  # 90%
        
        status = manager.get_status()
        
        assert status.is_degraded == True
        assert status.is_disabled == False
    
    def test_get_status_disabled_mode(self):
        """Test status in disabled mode."""
        manager = BudgetManager(monthly_limit=6000)
        manager._monthly_used = 5700  # 95%
        
        status = manager.get_status()
        
        assert status.is_degraded == True
        assert status.is_disabled == True
    
    def test_reset_monthly(self):
        """Test monthly reset."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Record some usage
        manager.record_call("component1")
        manager.record_call("component2")
        
        # Reset
        manager.reset_monthly()
        
        assert manager._monthly_used == 0
        assert manager._daily_used == 0
        assert all(usage == 0 for usage in manager._component_usage.values())
        assert manager._last_reset_month == datetime.now(timezone.utc).month
    
    def test_get_remaining_budget(self):
        """Test getting remaining budget."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Record some usage
        manager._monthly_used = 1500
        
        assert manager.get_remaining_budget() == 4500
        
        # At limit
        manager._monthly_used = 6000
        assert manager.get_remaining_budget() == 0
        
        # Over limit (shouldn't happen, but test defensive)
        manager._monthly_used = 6500
        assert manager.get_remaining_budget() == 0
    
    def test_get_component_remaining(self):
        """Test getting remaining budget for component."""
        allocations = {"component1": 1000}
        manager = BudgetManager(monthly_limit=6000, allocations=allocations)
        
        # Record usage for component
        manager._component_usage["component1"] = 500
        
        assert manager.get_component_remaining("component1") == 500  # 1000 - 500 = 500
        
        # At limit
        manager._component_usage["component1"] = 1000
        assert manager.get_component_remaining("component1") == 0
        
        # Over limit (shouldn't happen, but test defensive)
        manager._component_usage["component1"] = 1500
        assert manager.get_component_remaining("component1") == 0
    
    def test_unknown_component(self):
        """Test handling of unknown component."""
        manager = BudgetManager(monthly_limit=6000)
        
        # Record call for unknown component
        manager.record_call("unknown_component")
        
        # Should be added to component_usage
        assert "unknown_component" in manager._component_usage
        assert manager._component_usage["unknown_component"] == 1
    
    def test_critical_components_list(self):
        """Test that critical components are correctly identified."""
        manager = BudgetManager(monthly_limit=6000)
        
        assert "main_pipeline" in manager._critical_components
        assert "settlement_clv" in manager._critical_components
        assert "component1" not in manager._critical_components
    
    def test_zero_monthly_limit(self):
        """Test handling of zero monthly limit."""
        manager = BudgetManager(monthly_limit=0)
        
        # Should not crash
        status = manager.get_status()
        assert status.monthly_limit == 0
        
        # Can call should work (no limit)
        assert manager.can_call("component1") == True
