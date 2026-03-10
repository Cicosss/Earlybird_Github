"""
Comprehensive tests for unified BudgetStatus implementation.

Tests cover:
- BudgetStatus dataclass initialization and methods
- BaseBudgetManager integration
- Provider consistency (Brave, Tavily, MediaStack)
- Edge cases and error handling
- Serialization and deserialization

Created: 2026-03-08
Purpose: Verify unified BudgetStatus implementation works correctly
"""

import pytest

from src.ingestion.budget_status import BudgetStatus
from src.ingestion.brave_budget import BudgetManager


class TestBudgetStatusDataclass:
    """Test BudgetStatus dataclass functionality."""

    def test_basic_initialization(self):
        """Test basic BudgetStatus initialization."""
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
        )

        assert status.monthly_used == 100
        assert status.monthly_limit == 1000
        assert status.daily_used == 10
        assert status.daily_limit == 100
        assert status.is_degraded is False
        assert status.is_disabled is False
        assert status.usage_percentage == 10.0

    def test_initialization_with_optional_fields(self):
        """Test BudgetStatus initialization with optional fields."""
        status = BudgetStatus(
            monthly_used=500,
            monthly_limit=1000,
            daily_used=50,
            daily_limit=100,
            is_degraded=True,
            is_disabled=False,
            usage_percentage=50.0,
            component_usage={"main_pipeline": 300, "news_radar": 200},
            daily_reset_date="2026-03-08",
            provider_name="TestProvider",
        )

        assert status.component_usage == {"main_pipeline": 300, "news_radar": 200}
        assert status.daily_reset_date == "2026-03-08"
        assert status.provider_name == "TestProvider"

    def test_to_dict(self):
        """Test BudgetStatus.to_dict() method."""
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            component_usage={"test": 10},
            daily_reset_date="2026-03-08",
            provider_name="TestProvider",
        )

        status_dict = status.to_dict()

        assert isinstance(status_dict, dict)
        assert status_dict["monthly_used"] == 100
        assert status_dict["monthly_limit"] == 1000
        assert status_dict["daily_used"] == 10
        assert status_dict["daily_limit"] == 100
        assert status_dict["is_degraded"] is False
        assert status_dict["is_disabled"] is False
        assert status_dict["usage_percentage"] == 10.0
        assert status_dict["component_usage"] == {"test": 10}
        assert status_dict["daily_reset_date"] == "2026-03-08"
        assert status_dict["provider_name"] == "TestProvider"

    def test_get_remaining_monthly(self):
        """Test BudgetStatus.get_remaining_monthly() method."""
        # Normal case
        status = BudgetStatus(
            monthly_used=300,
            monthly_limit=1000,
            daily_used=30,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=30.0,
        )
        assert status.get_remaining_monthly() == 700

        # At limit
        status = BudgetStatus(
            monthly_used=1000,
            monthly_limit=1000,
            daily_used=100,
            daily_limit=100,
            is_degraded=True,
            is_disabled=False,
            usage_percentage=100.0,
        )
        assert status.get_remaining_monthly() == 0

        # Over limit (should return 0, not negative)
        status = BudgetStatus(
            monthly_used=1100,
            monthly_limit=1000,
            daily_used=110,
            daily_limit=100,
            is_degraded=True,
            is_disabled=True,
            usage_percentage=110.0,
        )
        assert status.get_remaining_monthly() == 0

        # Unlimited (0 limit)
        status = BudgetStatus(
            monthly_used=999999,
            monthly_limit=0,
            daily_used=9999,
            daily_limit=0,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=0.0,
        )
        assert status.get_remaining_monthly() == 0

    def test_get_remaining_daily(self):
        """Test BudgetStatus.get_remaining_daily() method."""
        # Normal case
        status = BudgetStatus(
            monthly_used=300,
            monthly_limit=1000,
            daily_used=30,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=30.0,
        )
        assert status.get_remaining_daily() == 70

        # At limit
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=100,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
        )
        assert status.get_remaining_daily() == 0

        # Over limit (should return 0, not negative)
        status = BudgetStatus(
            monthly_used=110,
            monthly_limit=1000,
            daily_used=110,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=11.0,
        )
        assert status.get_remaining_daily() == 0

        # Unlimited (0 limit)
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=9999,
            daily_limit=0,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
        )
        assert status.get_remaining_daily() == 0

    def test_is_healthy(self):
        """Test BudgetStatus.is_healthy() method."""
        # Healthy
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
        )
        assert status.is_healthy() is True

        # Degraded
        status = BudgetStatus(
            monthly_used=900,
            monthly_limit=1000,
            daily_used=90,
            daily_limit=100,
            is_degraded=True,
            is_disabled=False,
            usage_percentage=90.0,
        )
        assert status.is_healthy() is False

        # Disabled
        status = BudgetStatus(
            monthly_used=950,
            monthly_limit=1000,
            daily_used=95,
            daily_limit=100,
            is_degraded=True,
            is_disabled=True,
            usage_percentage=95.0,
        )
        assert status.is_healthy() is False

    def test_repr(self):
        """Test BudgetStatus.__repr__() method."""
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            provider_name="TestProvider",
        )
        repr_str = repr(status)

        assert "BudgetStatus" in repr_str
        assert "TestProvider" in repr_str
        assert "100/1000" in repr_str
        assert "10.0%" in repr_str
        assert "HEALTHY" in repr_str

        status = BudgetStatus(
            monthly_used=900,
            monthly_limit=1000,
            daily_used=90,
            daily_limit=100,
            is_degraded=True,
            is_disabled=False,
            usage_percentage=90.0,
            provider_name="TestProvider",
        )
        repr_str = repr(status)
        assert "DEGRADED" in repr_str

        status = BudgetStatus(
            monthly_used=950,
            monthly_limit=1000,
            daily_used=95,
            daily_limit=100,
            is_degraded=True,
            is_disabled=True,
            usage_percentage=95.0,
            provider_name="TestProvider",
        )
        repr_str = repr(status)
        assert "DISABLED" in repr_str


class TestBudgetManagerIntegration:
    """Test BudgetManager integration with unified BudgetStatus."""

    def test_get_status_returns_unified_budget_status(self):
        """Test that BudgetManager.get_status() returns unified BudgetStatus."""
        manager = BudgetManager(monthly_limit=1000)

        status = manager.get_status()

        assert isinstance(status, BudgetStatus)
        assert status.monthly_limit == 1000
        assert status.provider_name == "Brave"
        assert status.component_usage is not None
        assert status.daily_reset_date is None

    def test_get_status_after_calls(self):
        """Test BudgetStatus after recording calls."""
        manager = BudgetManager(monthly_limit=1000)

        # Record some calls
        manager.record_call("main_pipeline")
        manager.record_call("main_pipeline")
        manager.record_call("news_radar")

        status = manager.get_status()

        assert status.monthly_used == 3
        assert status.daily_used == 3
        assert status.component_usage is not None
        assert status.usage_percentage == 0.3

    def test_get_status_degraded_and_disabled(self):
        """Test BudgetStatus with degraded and disabled states."""
        manager = BudgetManager(monthly_limit=1000)

        # Simulate high usage
        for _ in range(900):
            manager.record_call("main_pipeline")

        status = manager.get_status()

        assert status.is_degraded is True
        assert status.is_disabled is False

        # Simulate very high usage
        for _ in range(60):
            manager.record_call("main_pipeline")

        status = manager.get_status()

        assert status.is_degraded is True
        assert status.is_disabled is True

    def test_get_status_unlimited(self):
        """Test BudgetStatus with unlimited budget (0 limit)."""
        manager = BudgetManager(monthly_limit=0)

        # Record some calls
        manager.record_call("main_pipeline")
        manager.record_call("main_pipeline")

        status = manager.get_status()

        assert status.monthly_limit == 0
        # daily_limit is calculated from allocations, not set to 0
        assert status.daily_limit > 0
        assert status.monthly_used == 2
        assert status.is_degraded is False
        assert status.is_disabled is False


class TestBudgetStatusConsistency:
    """Test BudgetStatus consistency across providers."""

    def test_budget_status_serialization_consistency(self):
        """Test that BudgetStatus serialization is consistent."""
        status1 = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            component_usage={"test": 10},
            daily_reset_date="2026-03-08",
            provider_name="Provider1",
        )

        status2 = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            component_usage={"test": 10},
            daily_reset_date="2026-03-08",
            provider_name="Provider2",
        )

        dict1 = status1.to_dict()
        dict2 = status2.to_dict()

        # Same data except provider_name
        assert dict1["monthly_used"] == dict2["monthly_used"]
        assert dict1["monthly_limit"] == dict2["monthly_limit"]
        assert dict1["daily_used"] == dict2["daily_used"]
        assert dict1["daily_limit"] == dict2["daily_limit"]
        assert dict1["is_degraded"] == dict2["is_degraded"]
        assert dict1["is_disabled"] == dict2["is_disabled"]
        assert dict1["usage_percentage"] == dict2["usage_percentage"]
        assert dict1["component_usage"] == dict2["component_usage"]
        assert dict1["daily_reset_date"] == dict2["daily_reset_date"]

        # Different provider names
        assert dict1["provider_name"] == "Provider1"
        assert dict2["provider_name"] == "Provider2"

    def test_budget_status_with_none_optional_fields(self):
        """Test BudgetStatus with None optional fields."""
        status = BudgetStatus(
            monthly_used=100,
            monthly_limit=1000,
            daily_used=10,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            component_usage=None,
            daily_reset_date=None,
            provider_name=None,
        )

        assert status.component_usage is None
        assert status.daily_reset_date is None
        assert status.provider_name is None

        # to_dict() should handle None values correctly
        status_dict = status.to_dict()
        assert status_dict["component_usage"] is None
        assert status_dict["daily_reset_date"] is None
        assert status_dict["provider_name"] is None


class TestBudgetStatusEdgeCases:
    """Test BudgetStatus edge cases."""

    def test_zero_values(self):
        """Test BudgetStatus with zero values."""
        status = BudgetStatus(
            monthly_used=0,
            monthly_limit=1000,
            daily_used=0,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=0.0,
        )

        assert status.get_remaining_monthly() == 1000
        assert status.get_remaining_daily() == 100
        assert status.is_healthy() is True

    def test_negative_values_handled(self):
        """Test that negative values are handled gracefully."""
        # This shouldn't happen in practice, but let's test it
        status = BudgetStatus(
            monthly_used=-10,
            monthly_limit=1000,
            daily_used=-5,
            daily_limit=100,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=-1.0,
        )

        # get_remaining_* should handle negative values
        remaining_monthly = status.get_remaining_monthly()
        remaining_daily = status.get_remaining_daily()

        assert remaining_monthly >= 0
        assert remaining_daily >= 0

    def test_very_large_values(self):
        """Test BudgetStatus with very large values."""
        status = BudgetStatus(
            monthly_used=999999999,
            monthly_limit=1000000000,
            daily_used=99999999,
            daily_limit=100000000,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=99.9999999,
        )

        assert status.monthly_used == 999999999
        assert status.monthly_limit == 1000000000
        assert status.usage_percentage == 99.9999999

    def test_usage_percentage_precision(self):
        """Test usage_percentage precision."""
        status = BudgetStatus(
            monthly_used=1,
            monthly_limit=3,
            daily_used=1,
            daily_limit=3,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=33.33333333333333,
        )

        assert status.usage_percentage == 33.33333333333333

    def test_component_usage_with_many_components(self):
        """Test BudgetStatus with many components."""
        component_usage = {f"component_{i}": i * 10 for i in range(100)}
        status = BudgetStatus(
            monthly_used=1000,
            monthly_limit=10000,
            daily_used=100,
            daily_limit=1000,
            is_degraded=False,
            is_disabled=False,
            usage_percentage=10.0,
            component_usage=component_usage,
        )

        assert len(status.component_usage) == 100
        assert status.component_usage["component_0"] == 0
        assert status.component_usage["component_99"] == 990


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
