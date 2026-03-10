"""
Brave Budget Manager - V1.1

Tracks and manages Brave API budget across 3 API keys.
Implements tiered throttling based on usage thresholds.

Requirements: Refactored to inherit from BaseBudgetManager (V1.1)
"""

import logging
import threading

from config.settings import (
    BRAVE_BUDGET_ALLOCATION,
    BRAVE_DEGRADED_THRESHOLD,
    BRAVE_DISABLED_THRESHOLD,
    BRAVE_MONTHLY_BUDGET,
)

from .base_budget_manager import BaseBudgetManager

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
        allocations: dict[str, int] | None = None,
        enable_persistence: bool = True,
        enable_monitoring: bool = True,
        enable_reporting: bool = True,
    ):
        """
        Initialize BudgetManager.

        Args:
            monthly_limit: Total monthly API call limit (default 6000)
            allocations: Per-component budget allocations
            enable_persistence: Enable budget persistence to SQLite
            enable_monitoring: Enable intelligent monitoring and state change detection
            enable_reporting: Enable intelligent reporting with trend analysis
        """
        super().__init__(
            monthly_limit=monthly_limit,
            allocations=allocations or BRAVE_BUDGET_ALLOCATION,
            provider_name="Brave",
            enable_persistence=enable_persistence,
            enable_monitoring=enable_monitoring,
            enable_reporting=enable_reporting,
        )

    def get_degraded_threshold(self) -> float:
        """Get degraded threshold for Brave (90%)."""
        return BRAVE_DEGRADED_THRESHOLD

    def get_disabled_threshold(self) -> float:
        """Get disabled threshold for Brave (95%)."""
        return BRAVE_DISABLED_THRESHOLD

    # V13.0: Removed can_call() override to use BaseBudgetManager's intelligent features
    # The base class implementation includes:
    # - Intelligent monitoring and state change detection
    # - Alert triggering on threshold crossings
    # - Proper integration with budget persistence
    # - Component allocation checks
    # - Critical component handling
    # - Degraded and disabled mode logic


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_manager_instance: BudgetManager | None = None
_budget_manager_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_brave_budget_manager() -> BudgetManager:
    """
    Get or create singleton BudgetManager instance.

    V12.2: Fixed lazy initialization race condition.
    Multiple threads can safely call this function concurrently.
    """
    global _budget_manager_instance
    if _budget_manager_instance is None:
        with _budget_manager_instance_init_lock:
            # Double-checked locking pattern for thread safety
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
