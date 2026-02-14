"""
Base Budget Manager - V1.0

Abstract base class for API budget management across providers.
Implements common budget tracking, tiered throttling, and reset behavior.

Providers:
- BraveBudgetManager (3 API keys)
- TavilyBudgetManager (7 API keys)
- MediaStackBudgetManager (free unlimited)
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

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


class BaseBudgetManager(ABC):
    """
    Abstract base class for budget management.

    Implements tiered throttling:
    - Normal: Full functionality
    - Degraded (>90%): Non-critical calls throttled
    - Disabled (>95%): Only critical calls allowed
    """

    # Critical components that can still call even in disabled mode
    _critical_components = {"main_pipeline", "settlement_clv"}

    def __init__(
        self,
        monthly_limit: int,
        allocations: Optional[Dict[str, int]] = None,
        provider_name: str = "Provider",
    ):
        """
        Initialize BaseBudgetManager.

        Args:
            monthly_limit: Total monthly API call limit (0 = unlimited)
            allocations: Per-component budget allocations
            provider_name: Name of provider for logging
        """
        self._monthly_limit = monthly_limit
        self._monthly_used = 0
        self._daily_used = 0
        self._last_reset_day: Optional[int] = None
        self._last_reset_month: Optional[int] = None
        self._provider_name = provider_name

        # Per-component tracking
        self._allocations = allocations or {}
        self._component_usage: Dict[str, int] = {
            component: 0 for component in self._allocations
        }

        logger.info(
            f"📊 {self._provider_name} BudgetManager initialized: {monthly_limit} calls/month, "
            f"{len(self._allocations)} components"
        )

    @abstractmethod
    def get_degraded_threshold(self) -> float:
        """Get degraded threshold (e.g., 0.90 for 90%)."""
        pass

    @abstractmethod
    def get_disabled_threshold(self) -> float:
        """Get disabled threshold (e.g., 0.95 for 95%)."""
        pass

    def can_call(self, component: str, is_critical: bool = False) -> bool:
        """
        Check if component can make a call.

        Args:
            component: Component name (e.g., 'main_pipeline', 'news_radar')
            is_critical: Whether this is a critical call

        Returns:
            True if call is allowed, False otherwise
        """
        self._check_daily_reset()

        # Unlimited providers always allow calls
        if self._monthly_limit == 0:
            return True

        usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

        # Disabled mode: Only critical calls
        if usage_pct >= self.get_disabled_threshold():
            if is_critical or component in self._critical_components:
                logger.debug(f"📊 [{self._provider_name}-BUDGET] Critical call allowed for {component} in disabled mode")
                return True
            logger.warning(f"⚠️ [{self._provider_name}-BUDGET] Call blocked for {component}: budget disabled (>{self.get_disabled_threshold()*100:.0f}%)")
            return False

        # Degraded mode: Throttle non-critical
        if usage_pct >= self.get_degraded_threshold():
            if is_critical or component in self._critical_components:
                return True
            # Allow only 50% of normal calls in degraded mode
            component_used = self._component_usage.get(component, 0)
            component_limit = self._allocations.get(component, 0)
            if component_used >= component_limit * 0.5:
                logger.warning(f"⚠️ [{self._provider_name}-BUDGET] Call throttled for {component}: degraded mode")
                return False

        # Normal mode: Check component allocation
        component_used = self._component_usage.get(component, 0)
        component_limit = self._allocations.get(component, 0)

        if component_limit > 0 and component_used >= component_limit:
            logger.warning(f"⚠️ [{self._provider_name}-BUDGET] Component {component} at allocation limit ({component_limit})")
            return False

        return True

    def record_call(self, component: str) -> None:
        """
        Record an API call.

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
        if self._monthly_limit > 0:
            usage_pct = self._monthly_used / self._monthly_limit * 100
            if self._monthly_used % 100 == 0:
                logger.info(f"📊 [{self._provider_name}-BUDGET] Usage: {self._monthly_used}/{self._monthly_limit} ({usage_pct:.1f}%)")
        else:
            if self._monthly_used % 100 == 0:
                logger.info(f"📊 [{self._provider_name}-BUDGET] Usage: {self._monthly_used} calls (monitoring)")

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
            daily_limit=sum(self._allocations.values()) // 30 if self._allocations else 0,
            is_degraded=usage_pct >= self.get_degraded_threshold() if self._monthly_limit > 0 else False,
            is_disabled=usage_pct >= self.get_disabled_threshold() if self._monthly_limit > 0 else False,
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
        # Reset ALL component usage values to 0
        for component in self._component_usage:
            self._component_usage[component] = 0
        # Also initialize any missing components from allocations
        for component in self._allocations:
            if component not in self._component_usage:
                self._component_usage[component] = 0
        self._last_reset_month = datetime.now(timezone.utc).month
        self._last_reset_day = datetime.now(timezone.utc).day

        logger.info(f"📊 [{self._provider_name}-BUDGET] Monthly reset complete")

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

        # Daily reset (just daily counter)
        if self._last_reset_day is None:
            self._last_reset_day = current_day
        elif current_day != self._last_reset_day:
            self._daily_used = 0
            self._last_reset_day = current_day
            logger.debug(f"📊 [{self._provider_name}-BUDGET] Daily counter reset")

    def _check_thresholds(self) -> None:
        """
        Check and log threshold crossings.
        """
        if self._monthly_limit == 0:
            return

        usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

        # Check disabled threshold
        disabled_count = int(self._monthly_limit * self.get_disabled_threshold())
        if self._monthly_used == disabled_count:
            logger.warning(
                f"🚨 [{self._provider_name}-BUDGET] DISABLED threshold reached ({self.get_disabled_threshold()*100:.0f}%): "
                f"Only critical calls allowed"
            )

        # Check degraded threshold
        degraded_count = int(self._monthly_limit * self.get_degraded_threshold())
        if self._monthly_used == degraded_count:
            logger.warning(
                f"⚠️ [{self._provider_name}-BUDGET] DEGRADED threshold reached ({self.get_degraded_threshold()*100:.0f}%): "
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
