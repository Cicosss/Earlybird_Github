"""
Tavily Budget Manager - V7.1

Tracks and manages Tavily API budget across 7 API keys.
Implements tiered throttling based on usage thresholds.

Requirements: Refactored to inherit from BaseBudgetManager (V7.1)
"""
import logging
from typing import Dict, Optional

from config.settings import (
    TAVILY_BUDGET_ALLOCATION,
    TAVILY_MONTHLY_BUDGET,
    TAVILY_DEGRADED_THRESHOLD,
    TAVILY_DISABLED_THRESHOLD,
)

from .base_budget_manager import BaseBudgetManager, BudgetStatus

logger = logging.getLogger(__name__)


class BudgetManager(BaseBudgetManager):
    """
    Tracks and manages Tavily API budget.

    Implements tiered throttling:
    - Normal: Full functionality
    - Degraded (>90%): Non-critical calls throttled
    - Disabled (>95%): Only critical calls allowed

    Requirements: Refactored to inherit from BaseBudgetManager (V7.1)
    """

    def __init__(
        self,
        monthly_limit: int = TAVILY_MONTHLY_BUDGET,
        allocations: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize BudgetManager.

        Args:
            monthly_limit: Total monthly API call limit (default 7000)
            allocations: Per-component budget allocations
        """
        super().__init__(
            monthly_limit=monthly_limit,
            allocations=allocations or TAVILY_BUDGET_ALLOCATION,
            provider_name="Tavily",
        )

    def get_degraded_threshold(self) -> float:
        """Get degraded threshold for Tavily (90%)."""
        return TAVILY_DEGRADED_THRESHOLD

    def get_disabled_threshold(self) -> float:
        """Get disabled threshold for Tavily (95%)."""
        return TAVILY_DISABLED_THRESHOLD


# ============================================
# SINGLETON INSTANCE
# ============================================

_budget_manager_instance: Optional[BudgetManager] = None


def get_budget_manager() -> BudgetManager:
    """Get or create singleton BudgetManager instance."""
    global _budget_manager_instance
    if _budget_manager_instance is None:
        _budget_manager_instance = BudgetManager()
    return _budget_manager_instance
