"""
Brave Budget Manager - V1.0

Tracks and manages Brave API budget across 3 API keys.
Implements tiered throttling based on usage thresholds.

Requirements: Duplicated from TavilyBudget (V7.0)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from config.settings import (
    BRAVE_BUDGET_ALLOCATION,
    BRAVE_MONTHLY_BUDGET,
    BRAVE_DEGRADED_THRESHOLD,
    BRAVE_DISABLED_THRESHOLD,
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


class BudgetManager:
    """
    Tracks and manages Brave API budget.

    Implements tiered throttling:
    - Normal: Full functionality
    - Degraded (>90%): Non-critical calls throttled
    - Disabled (>95%): Only critical calls allowed

    Requirements: Duplicated from TavilyBudget (V7.0)
    """

    def __init__(
        self,
        monthly_limit: int = BRAVE_MONTHLY_BUDGET,
        allocations: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize BudgetManager.

        Args:
            monthly_limit: Total monthly API call limit (default 6000)
            allocations: Per-component budget allocations
        """
        self._monthly_limit = monthly_limit
        self._monthly_used = 0
        self._daily_used = 0
        self._last_reset_day: Optional[int] = None
        self._last_reset_month: Optional[int] = None

        # Per-component tracking
        self._allocations = allocations or BRAVE_BUDGET_ALLOCATION
        self._component_usage: Dict[str, int] = {
            component: 0 for component in self._allocations
        }

        # Critical components that can still call even in disabled mode
        self._critical_components = {"main_pipeline", "settlement_clv"}

        logger.info(
            f"📊 Brave BudgetManager initialized: {monthly_limit} calls/month, "
            f"{len(self._allocations)} components"
        )

    def can_call(self, component: str, is_critical: bool = False) -> bool:
        """
        Check if component can make a Brave call.

        Args:
            component: Component name (e.g., 'main_pipeline', 'news_radar')
            is_critical: Whether this is a critical call

        Returns:
            True if call is allowed, False otherwise
        """
        self._check_daily_reset()

        usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

        # Disabled mode (>95%): Only critical calls
        if usage_pct >= BRAVE_DISABLED_THRESHOLD:
            if is_critical or component in self._critical_components:
                logger.debug(f"📊 [BRAVE-BUDGET] Critical call allowed for {component} in disabled mode")
                return True
            logger.warning(f"⚠️ [BRAVE-BUDGET] Call blocked for {component}: budget disabled (>{BRAVE_DISABLED_THRESHOLD*100:.0f}%)")
            return False

        # Degraded mode (>90%): Throttle non-critical
        if usage_pct >= BRAVE_DEGRADED_THRESHOLD:
            if is_critical or component in self._critical_components:
                return True
            # Allow only 50% of normal calls in degraded mode
            component_used = self._component_usage.get(component, 0)
            component_limit = self._allocations.get(component, 0)
            if component_used >= component_limit * 0.5:
                logger.warning(f"⚠️ [BRAVE-BUDGET] Call throttled for {component}: degraded mode")
                return False

        # Normal mode: Check component allocation
        component_used = self._component_usage.get(component, 0)
        component_limit = self._allocations.get(component, 0)

        if component_limit > 0 and component_used >= component_limit:
            logger.warning(f"⚠️ [BRAVE-BUDGET] Component {component} at allocation limit ({component_limit})")
            return False

        return True

    def record_call(self, component: str) -> None:
        """
        Record a Brave API call.

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
        usage_pct = self._monthly_used / self._monthly_limit * 100
        if self._monthly_used % 100 == 0:
            logger.info(f"📊 [BRAVE-BUDGET] Usage: {self._monthly_used}/{self._monthly_limit} ({usage_pct:.1f}%)")

        # Check thresholds
        self._check_thresholds()

    def get_status(self) -> BudgetStatus:
        """
        Get current budget status.

        Returns:
            BudgetStatus with usage information
        """
        self._check_daily_reset()

        usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

        return BudgetStatus(
            monthly_used=self._monthly_used,
            monthly_limit=self._monthly_limit,
            daily_used=self._daily_used,
            daily_limit=sum(self._allocations.values()) // 30,  # Approximate daily limit
            is_degraded=usage_pct >= BRAVE_DEGRADED_THRESHOLD,
            is_disabled=usage_pct >= BRAVE_DISABLED_THRESHOLD,
            usage_percentage=usage_pct * 100,
            component_usage=dict(self._component_usage),
        )

    def reset_monthly(self) -> None:
        """
        Reset monthly counters.

        Called on month boundary.
        """
        self._monthly_used = 0
        self._daily_used = 0
        self._component_usage = {component: 0 for component in self._allocations}
        self._last_reset_month = datetime.now(timezone.utc).month
        self._last_reset_day = datetime.now(timezone.utc).day

        logger.info("📊 [BRAVE-BUDGET] Monthly reset complete")

    def _check_daily_reset(self) -> None:
        """Check if we need to reset daily counters."""
        now = datetime.now(timezone.utc)
        current_day = now.day
        current_month = now.month

        # Monthly reset
        if self._last_reset_month is None:
            self._last_reset_month = current_month
        elif current_month != self._last_reset_month:
            logger.info(f"📅 New month detected, resetting budget")
            self.reset_monthly()
            return

        # Daily reset (just the daily counter)
        if self._last_reset_day is None:
            self._last_reset_day = current_day
        elif current_day != self._last_reset_day:
            self._daily_used = 0
            self._last_reset_day = current_day
            logger.debug("📊 [BRAVE-BUDGET] Daily counter reset")

    def _check_thresholds(self) -> None:
        """
        Check and log threshold crossings.
        """
        usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

        # Check 95% threshold (disabled)
        disabled_count = int(self._monthly_limit * BRAVE_DISABLED_THRESHOLD)
        if self._monthly_used == disabled_count:
            logger.warning(
                f"🚨 [BRAVE-BUDGET] DISABLED threshold reached ({BRAVE_DISABLED_THRESHOLD*100:.0f}%): "
                f"Only critical calls allowed"
            )

        # Check 90% threshold (degraded)
        degraded_count = int(self._monthly_limit * BRAVE_DEGRADED_THRESHOLD)
        if self._monthly_used == degraded_count:
            logger.warning(
                f"⚠️ [BRAVE-BUDGET] DEGRADED threshold reached ({BRAVE_DEGRADED_THRESHOLD*100:.0f}%): "
                f"Non-critical calls throttled"
            )

    def get_remaining_budget(self) -> int:
        """Get remaining monthly budget."""
        return max(0, self._monthly_limit - self._monthly_used)

    def get_component_remaining(self, component: str) -> int:
        """Get remaining budget for a specific component."""
        allocation = self._allocations.get(component, 0)
        used = self._component_usage.get(component, 0)
        return max(0, allocation - used)


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_manager_instance: Optional[BudgetManager] = None


def get_brave_budget_manager() -> BudgetManager:
    """Get or create the singleton BudgetManager instance."""
    global _budget_manager_instance
    if _budget_manager_instance is None:
        _budget_manager_instance = BudgetManager()
    return _budget_manager_instance
