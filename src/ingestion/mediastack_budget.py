"""
MediaStack Budget Manager - V1.0

Tracks MediaStack API usage across components (monitoring only).
MediaStack is FREE unlimited tier - no throttling implemented.

Requirements: Standard library only (no new dependencies)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from config.settings import (
    MEDIASTACK_BUDGET_ENABLED,
    MEDIASTACK_BUDGET_ALLOCATION,
)

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Budget status for monitoring."""

    monthly_used: int
    monthly_limit: int
    daily_used: int
    daily_limit: int
    is_degraded: bool
    is_disabled: bool
    usage_percentage: float
    component_usage: Dict[str, int]


class MediaStackBudget:
    """
    Tracks MediaStack API usage across components.

    MediaStack is FREE unlimited tier - this is for monitoring only.
    No throttling is implemented.

    Requirements: Standard library only
    """

    def __init__(
        self,
        allocations: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize MediaStackBudget.

        Args:
            allocations: Per-component budget allocations (for monitoring)
        """
        # MediaStack is free unlimited - set limit to 0 for monitoring
        self._monthly_limit = 0  # 0 = unlimited
        self._monthly_used = 0
        self._daily_used = 0
        self._last_reset_day: Optional[int] = None
        self._last_reset_month: Optional[int] = None

        # Per-component tracking
        self._allocations = allocations or MEDIASTACK_BUDGET_ALLOCATION
        self._component_usage: Dict[str, int] = {
            component: 0 for component in self._allocations
        }

        logger.info(
            f"📊 MediaStackBudget initialized: {len(self._allocations)} components "
            f"(monitoring only - free unlimited tier)"
        )

    def can_call(self, component: str) -> bool:
        """
        Check if component can make a MediaStack call.

        MediaStack is free unlimited - always returns True.
        This method exists for API compatibility and monitoring.

        Args:
            component: Component name (e.g., 'search_provider')

        Returns:
            Always True (MediaStack is free unlimited)
        """
        self._check_daily_reset()
        return True  # MediaStack is free unlimited

    def record_call(self, component: str) -> None:
        """
        Record a MediaStack API call.

        Args:
            component: Component that made the call
        """
        self._check_daily_reset()

        self._monthly_used += 1
        self._daily_used += 1

        if component in self._component_usage:
            self._component_usage[component] += 1
        else:
            self._component_usage[component] = 1

        # Log milestone usage
        if self._monthly_used % 100 == 0:
            logger.info(f"📊 [MEDIASTACK] Usage: {self._monthly_used} calls (monitoring)")

    def get_status(self) -> BudgetStatus:
        """
        Get budget status for monitoring.

        Returns:
            BudgetStatus with current usage information
        """
        usage_pct = 0.0  # MediaStack is unlimited

        return BudgetStatus(
            monthly_used=self._monthly_used,
            monthly_limit=self._monthly_limit,
            daily_used=self._daily_used,
            daily_limit=0,  # No limit
            is_degraded=False,
            is_disabled=False,
            usage_percentage=usage_pct,
            component_usage=dict(self._component_usage),
        )

    def reset_daily(self) -> None:
        """
        Reset daily counters.
        """
        self._daily_used = 0
        self._last_reset_day = datetime.now(timezone.utc).day
        logger.info("📅 MediaStack budget: Daily reset")

    def reset_monthly(self) -> None:
        """
        Reset monthly counters.
        """
        self._monthly_used = 0
        self._daily_used = 0  # Also reset daily counter
        self._component_usage = {component: 0 for component in self._allocations}
        self._last_reset_month = datetime.now(timezone.utc).month
        logger.info("📅 MediaStack budget: Monthly reset")

    def _check_daily_reset(self) -> None:
        """
        Check if we've crossed a day boundary and reset if needed.
        """
        current_day = datetime.now(timezone.utc).day

        if self._last_reset_day is None:
            self._last_reset_day = current_day
        elif current_day != self._last_reset_day:
            self.reset_daily()

    def _check_monthly_reset(self) -> None:
        """
        Check if we've crossed a month boundary and reset if needed.
        """
        current_month = datetime.now(timezone.utc).month

        if self._last_reset_month is None:
            self._last_reset_month = current_month
        elif current_month != self._last_reset_month:
            self.reset_monthly()


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_instance: Optional[MediaStackBudget] = None


def get_mediastack_budget() -> MediaStackBudget:
    """
    Get or create the singleton MediaStackBudget instance.

    Returns:
        Singleton instance of MediaStackBudget
    """
    global _budget_instance
    if _budget_instance is None:
        _budget_instance = MediaStackBudget()
    return _budget_instance


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("📊 MEDIASTACK BUDGET TEST")
    print("=" * 60)

    budget = get_mediastack_budget()

    # Test recording calls
    print("\n📝 Recording test calls...")
    budget.record_call("search_provider")
    budget.record_call("search_provider")
    budget.record_call("news_radar")

    # Get status
    status = budget.get_status()
    print(f"\n📊 Status:")
    print(f"   Monthly Used: {status.monthly_used}")
    print(f"   Daily Used: {status.daily_used}")
    print(f"   Component Usage: {status.component_usage}")
    print(f"   Can Call: {budget.can_call('search_provider')}")

    print("\n✅ MediaStack Budget test complete")
