"""
Unified BudgetStatus Definition

This module provides a single, consistent BudgetStatus dataclass used across
all providers (Brave, Tavily, MediaStack) to ensure type safety and
consistency in budget monitoring.

Created: 2026-03-08
Purpose: Resolve duplicate BudgetStatus definitions and standardize API
"""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class BudgetStatus:
    """
    Unified budget status for monitoring across all providers.

    This dataclass provides comprehensive budget tracking information
    including monthly/daily usage, degradation status, and provider-specific
    metadata.

    Attributes:
        monthly_used: Total API calls used this month
        monthly_limit: Monthly API call limit (0 = unlimited)
        daily_used: API calls used today
        daily_limit: Daily API call limit (0 = unlimited)
        is_degraded: Whether provider is in degraded mode (>90% usage)
        is_disabled: Whether provider is disabled (>95% usage)
        usage_percentage: Usage as percentage (0-100)
        component_usage: Per-component usage breakdown (optional)
        daily_reset_date: ISO format date of last daily reset (optional)
        provider_name: Name of the provider (optional, for logging)
    """

    monthly_used: int
    monthly_limit: int
    daily_used: int
    daily_limit: int
    is_degraded: bool
    is_disabled: bool
    usage_percentage: float
    component_usage: dict[str, int] | None = None
    daily_reset_date: str | None = None
    provider_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert BudgetStatus to dictionary.

        This provides a consistent way to serialize BudgetStatus for
        JSON responses, logging, or external APIs.

        Returns:
            Dictionary representation of BudgetStatus
        """
        return asdict(self)

    def get_remaining_monthly(self) -> int:
        """
        Get remaining monthly budget.

        Returns:
            Remaining calls this month (0 if unlimited)
        """
        if self.monthly_limit == 0:
            return 0  # Unlimited
        return max(0, self.monthly_limit - self.monthly_used)

    def get_remaining_daily(self) -> int:
        """
        Get remaining daily budget.

        Returns:
            Remaining calls today (0 if unlimited)
        """
        if self.daily_limit == 0:
            return 0  # Unlimited
        return max(0, self.daily_limit - self.daily_used)

    def is_healthy(self) -> bool:
        """
        Check if provider is in healthy state.

        Returns:
            True if not degraded and not disabled
        """
        return not self.is_degraded and not self.is_disabled

    def __repr__(self) -> str:
        """String representation for logging."""
        provider = self.provider_name or "Provider"
        status = "DISABLED" if self.is_disabled else ("DEGRADED" if self.is_degraded else "HEALTHY")
        return (
            f"BudgetStatus({provider}): {self.monthly_used}/{self.monthly_limit} "
            f"({self.usage_percentage:.1f}%) - {status}"
        )
