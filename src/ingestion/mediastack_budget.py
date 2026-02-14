"""
MediaStack Budget Manager - V1.1

Tracks MediaStack API usage across components (monitoring only).
MediaStack is FREE unlimited tier - no throttling implemented.

Requirements: Refactored to inherit from BaseBudgetManager (V1.1)
"""
import logging
from typing import Dict, Optional

from config.settings import (
    MEDIASTACK_BUDGET_ENABLED,
    MEDIASTACK_BUDGET_ALLOCATION,
)

from .base_budget_manager import BaseBudgetManager, BudgetStatus

logger = logging.getLogger(__name__)


class MediaStackBudget(BaseBudgetManager):
    """
    Tracks MediaStack API usage across components.

    MediaStack is FREE unlimited tier - this is for monitoring only.
    No throttling is implemented.

    Requirements: Refactored to inherit from BaseBudgetManager (V1.1)
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
        super().__init__(
            monthly_limit=0,  # 0 = unlimited
            allocations=allocations or MEDIASTACK_BUDGET_ALLOCATION,
            provider_name="MediaStack",
        )

    def get_degraded_threshold(self) -> float:
        """MediaStack is unlimited - no degraded threshold."""
        return 0.0

    def get_disabled_threshold(self) -> float:
        """MediaStack is unlimited - no disabled threshold."""
        return 0.0

    def can_call(self, component: str, is_critical: bool = False) -> bool:
        """
        Check if component can make a MediaStack call.

        MediaStack is free unlimited - always returns True.
        This method exists for API compatibility and monitoring.

        Args:
            component: Component name (e.g., 'search_provider')
            is_critical: Ignored for MediaStack

        Returns:
            Always True (MediaStack is free unlimited)
        """
        self._check_daily_reset()
        return True  # MediaStack is free unlimited

    def reset_daily(self) -> None:
        """
        Reset daily counters.
        """
        self._daily_used = 0
        from datetime import datetime, timezone
        self._last_reset_day = datetime.now(timezone.utc).day
        logger.info("📅 MediaStack budget: Daily reset")


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_instance: Optional[MediaStackBudget] = None


def get_mediastack_budget() -> MediaStackBudget:
    """
    Get or create singleton MediaStackBudget instance.

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
