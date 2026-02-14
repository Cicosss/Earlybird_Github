"""
Brave Budget Manager - V1.1

Tracks and manages Brave API budget across 3 API keys.
Implements tiered throttling based on usage thresholds.

Requirements: Refactored to inherit from BaseBudgetManager (V1.1)
"""
import logging
from typing import Dict, Optional

from config.settings import (
    BRAVE_BUDGET_ALLOCATION,
    BRAVE_MONTHLY_BUDGET,
    BRAVE_DEGRADED_THRESHOLD,
    BRAVE_DISABLED_THRESHOLD,
)

from .base_budget_manager import BaseBudgetManager, BudgetStatus

logger = logging.getLogger(__name__)


class BudgetManager(BaseBudgetManager):
    """
    Tracks and manages Brave API budget.

    Implements tiered throttling:
    - Normal: Full functionality
    - Degraded (>90%): Non-critical calls throttled
    - Disabled (>95%): Only critical calls allowed

    Requirements: Refactored to inherit from BaseBudgetManager (V1.1)
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
        super().__init__(
            monthly_limit=monthly_limit,
            allocations=allocations or BRAVE_BUDGET_ALLOCATION,
            provider_name="Brave",
        )

    def get_degraded_threshold(self) -> float:
        """Get degraded threshold for Brave (90%)."""
        return BRAVE_DEGRADED_THRESHOLD

    def get_disabled_threshold(self) -> float:
        """Get disabled threshold for Brave (95%)."""
        return BRAVE_DISABLED_THRESHOLD

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

        # V10.0: Fix - Ensure degraded mode check returns False (not True) when at threshold
        # The degraded mode check was incorrectly returning True when usage_pct == BRAVE_DEGRADED_THRESHOLD
        # This caused test_can_call_degraded_mode to fail
        if usage_pct >= BRAVE_DEGRADED_THRESHOLD:
            # In degraded mode (>90%), non-critical calls should be THROTTLED (return False)
            # NOT allowed (return True)
            if not is_critical and component not in self._critical_components:
                logger.debug(f"📊 [BRAVE-BUDGET] Throttling non-critical call in degraded mode")
                return False

        # Normal mode: Check component allocation
        component_used = self._component_usage.get(component, 0)
        component_limit = self._allocations.get(component, 0)

        if component_limit > 0 and component_used >= component_limit:
            logger.warning(f"⚠️ [BRAVE-BUDGET] Component {component} at allocation limit ({component_limit})")
            return False

        return True


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_manager_instance: Optional[BudgetManager] = None


def get_brave_budget_manager() -> BudgetManager:
    """Get or create singleton BudgetManager instance."""
    global _budget_manager_instance
    if _budget_manager_instance is None:
        _budget_manager_instance = BudgetManager()
    return _budget_manager_instance


def reset_brave_budget_manager() -> None:
    """
    Reset singleton BudgetManager instance for test isolation.

    This function is used by tests to ensure clean state between test runs.
    """
    global _budget_manager_instance
    _budget_manager_instance = None
