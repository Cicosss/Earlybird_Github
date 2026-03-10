"""
Base Budget Manager - V2.0

Abstract base class for API budget management across providers.
Implements common budget tracking, tiered throttling, and reset behavior.

Providers:
- BraveBudgetManager (3 API keys)
- TavilyBudgetManager (7 API keys)
- MediaStackBudgetManager (free unlimited)

V2.0 Changes:
- Added budget persistence (SQLite)
- Added intelligent monitoring and state change detection
- Added intelligent reporting with trend analysis
- Added intelligent alerting with deduplication
- Fixed daily_limit calculation to use actual days in month
- Integrated with BudgetMonitor, BudgetReporter, and BudgetPersistence

V1.1 Changes:
- Now uses unified BudgetStatus from budget_status.py
- Standardized API across all providers
"""

import calendar
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .budget_status import BudgetStatus

logger = logging.getLogger(__name__)


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
        allocations: dict[str, int] | None = None,
        provider_name: str = "Provider",
        enable_persistence: bool = True,
        enable_monitoring: bool = True,
        enable_reporting: bool = True,
    ):
        """
        Initialize BaseBudgetManager.

        Args:
            monthly_limit: Total monthly API call limit (0 = unlimited)
            allocations: Per-component budget allocations
            provider_name: Name of provider for logging
            enable_persistence: Enable budget persistence to SQLite
            enable_monitoring: Enable intelligent monitoring and state change detection
            enable_reporting: Enable intelligent reporting with trend analysis
        """
        self._monthly_limit = monthly_limit
        self._monthly_used = 0
        self._daily_used = 0
        self._last_reset_day: int | None = None
        self._last_reset_month: int | None = None
        self._provider_name = provider_name

        # Per-component tracking
        self._allocations = allocations or {}
        self._component_usage: dict[str, int] = {component: 0 for component in self._allocations}

        # Thread safety: Lock for protecting counter operations
        self._lock = threading.Lock()

        # V2.0: Intelligent features
        self._enable_persistence = enable_persistence
        self._enable_monitoring = enable_monitoring
        self._enable_reporting = enable_reporting
        self._persistence = None
        self._monitor = None
        self._reporter = None
        self._alert_deduplication: dict[str, float] = {}  # Track last alert time

        # Initialize intelligent features
        self._init_intelligent_features()

        logger.info(
            f"📊 {self._provider_name} BudgetManager V2.0 initialized: {monthly_limit} calls/month, "
            f"{len(self._allocations)} components "
            f"(persistence={enable_persistence}, monitoring={enable_monitoring}, reporting={enable_reporting})"
        )

    @abstractmethod
    def get_degraded_threshold(self) -> float:
        """Get degraded threshold (e.g., 0.90 for 90%)."""
        pass

    @abstractmethod
    def get_disabled_threshold(self) -> float:
        """Get disabled threshold (e.g., 0.95 for 95%)."""
        pass

    def _init_intelligent_features(self) -> None:
        """Initialize intelligent features (persistence, monitoring, reporting)."""
        try:
            # Initialize persistence
            if self._enable_persistence:
                from .budget_persistence import BudgetPersistence

                self._persistence = BudgetPersistence()
                self._load_budget_from_persistence()

            # Initialize monitoring
            if self._enable_monitoring:
                from .budget_monitor import get_budget_monitor

                self._monitor = get_budget_monitor()
                self._monitor.start_monitoring()

                # Register alert callback
                self._monitor.register_alert_callback(self._on_budget_alert)

            # Initialize reporting
            if self._enable_reporting:
                from .budget_reporter import get_budget_reporter

                self._reporter = get_budget_reporter()

        except ImportError as e:
            logger.warning(f"⚠️ Failed to initialize intelligent features: {e}")
            # Disable features if import fails
            self._enable_persistence = False
            self._enable_monitoring = False
            self._enable_reporting = False

    def _load_budget_from_persistence(self) -> None:
        """Load budget data from persistence."""
        if not self._persistence:
            return

        try:
            budget_data = self._persistence.load_budget(self._provider_name)
            if budget_data:
                # Check if data is from current month
                last_updated = budget_data.get("last_updated")
                if last_updated:
                    last_updated_dt = datetime.fromisoformat(last_updated)
                    current_month = datetime.now(timezone.utc).month

                    if last_updated_dt.month == current_month:
                        # Load data from persistence
                        self._monthly_used = budget_data.get("monthly_used", 0)
                        self._daily_used = budget_data.get("daily_used", 0)
                        self._component_usage = budget_data.get("component_usage", {})
                        self._last_reset_day = budget_data.get("last_reset_day")
                        self._last_reset_month = budget_data.get("last_reset_month")

                        logger.info(
                            f"💾 [{self._provider_name}] Budget loaded from persistence: "
                            f"{self._monthly_used}/{self._monthly_limit}"
                        )
                    else:
                        # Data is from previous month, ignore
                        logger.debug(
                            f"💾 [{self._provider_name}] Persistence data is from previous month, ignoring"
                        )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load budget from persistence: {e}")

    def _save_budget_to_persistence(self) -> None:
        """Save budget data to persistence."""
        if not self._persistence or not self._enable_persistence:
            return

        try:
            self._persistence.save_budget(
                provider_name=self._provider_name,
                monthly_used=self._monthly_used,
                daily_used=self._daily_used,
                monthly_limit=self._monthly_limit,
                component_usage=dict(self._component_usage),
                last_reset_day=self._last_reset_day,
                last_reset_month=self._last_reset_month,
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to save budget to persistence: {e}")

    def _on_budget_alert(self, provider_name: str, alert_data: dict[str, Any]) -> None:
        """
        Handle budget alerts from monitor.

        Args:
            provider_name: Name of the provider
            alert_data: Alert data dictionary
        """
        if provider_name != self._provider_name:
            return

        alert_type = alert_data.get("alert_type")
        timestamp = alert_data.get("timestamp")

        # Deduplicate alerts (only alert once per hour)
        alert_key = f"{provider_name}_{alert_type}"
        last_alert_time = self._alert_deduplication.get(alert_key, 0)

        if timestamp:
            alert_time = datetime.fromisoformat(timestamp).timestamp()
            if alert_time - last_alert_time < 3600:  # 1 hour
                logger.debug(f"🔍 Alert deduplicated: {alert_key}")
                return

        # Update last alert time
        if timestamp:
            self._alert_deduplication[alert_key] = datetime.fromisoformat(timestamp).timestamp()

        # Log alert
        logger.warning(
            f"🚨 [{provider_name}] Budget Alert: {alert_type} - "
            f"{alert_data.get('status', {}).get('usage_percentage', 0):.1f}%"
        )

        # Save budget history for reporting
        if self._persistence:
            status = alert_data.get("status", {})
            self._persistence.save_budget_history(
                provider_name=provider_name,
                monthly_used=status.get("monthly_used", 0),
                daily_used=status.get("daily_used", 0),
                usage_percentage=status.get("usage_percentage", 0.0),
                is_degraded=status.get("is_degraded", False),
                is_disabled=status.get("is_disabled", False),
                component_usage=status.get("component_usage", {}),
            )

    def can_call(self, component: str, is_critical: bool = False) -> bool:
        """
        Check if component can make a call.

        Args:
            component: Component name (e.g., 'main_pipeline', 'news_radar')
            is_critical: Whether this is a critical call

        Returns:
            True if call is allowed, False otherwise
        """
        with self._lock:
            self._check_daily_reset()

            # BUG FIX #2: Reject unknown components
            # Unknown components can make unlimited calls, which is a security risk
            if component not in self._allocations and component not in self._critical_components:
                logger.warning(
                    f"🚨 [{self._provider_name}-BUDGET] Call blocked for unknown component '{component}': "
                    f"Component not in allocations. Known components: {list(self._allocations.keys())}"
                )
                return False

            # Unlimited providers always allow calls
            if self._monthly_limit == 0:
                return True

            usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

            # Disabled mode: Only critical calls
            if usage_pct >= self.get_disabled_threshold():
                if is_critical or component in self._critical_components:
                    logger.debug(
                        f"📊 [{self._provider_name}-BUDGET] Critical call allowed for {component} in disabled mode"
                    )
                    return True
                logger.warning(
                    f"⚠️ [{self._provider_name}-BUDGET] Call blocked for {component}: budget disabled (>{self.get_disabled_threshold() * 100:.0f}%)"
                )
                return False

            # Degraded mode: Throttle non-critical
            if usage_pct >= self.get_degraded_threshold():
                if is_critical or component in self._critical_components:
                    return True
                # Allow only 50% of normal calls in degraded mode
                component_used = self._component_usage.get(component, 0)
                component_limit = self._allocations.get(component, 0)
                if component_used >= component_limit * 0.5:
                    logger.warning(
                        f"⚠️ [{self._provider_name}-BUDGET] Call throttled for {component}: degraded mode"
                    )
                    return False

            # Normal mode: Check component allocation
            component_used = self._component_usage.get(component, 0)
            component_limit = self._allocations.get(component, 0)

            if component_limit > 0 and component_used >= component_limit:
                logger.warning(
                    f"⚠️ [{self._provider_name}-BUDGET] Component {component} at allocation limit ({component_limit})"
                )
                return False

            return True

    def record_call(self, component: str) -> None:
        """
        Record an API call.

        Args:
            component: Component that made the call
        """
        with self._lock:
            # BUG FIX #3: Error handling to prevent budget leaks
            # Even if logging fails, we must ensure counters are incremented
            try:
                self._check_daily_reset()

                # Increment counters first - this is the critical operation
                self._monthly_used += 1
                self._daily_used += 1

                if component in self._component_usage:
                    self._component_usage[component] += 1
                else:
                    self._component_usage[component] = 1

                # Log milestone usage (non-critical - can fail without breaking functionality)
                try:
                    if self._monthly_limit > 0:
                        usage_pct = self._monthly_used / self._monthly_limit * 100
                        if self._monthly_used % 100 == 0:
                            logger.info(
                                f"📊 [{self._provider_name}-BUDGET] Usage: {self._monthly_used}/{self._monthly_limit} ({usage_pct:.1f}%)"
                            )
                    else:
                        if self._monthly_used % 100 == 0:
                            logger.info(
                                f"📊 [{self._provider_name}-BUDGET] Usage: {self._monthly_used} calls (monitoring)"
                            )
                except Exception as e:
                    # Logging failure is non-critical, just log the error
                    logger.error(
                        f"🚨 [{self._provider_name}-BUDGET] Failed to log milestone for {component}: {e}"
                    )

                # Check thresholds (non-critical - can fail without breaking functionality)
                try:
                    self._check_thresholds()
                except Exception as e:
                    # Threshold check failure is non-critical, just log the error
                    logger.error(
                        f"🚨 [{self._provider_name}-BUDGET] Failed to check thresholds for {component}: {e}"
                    )

            except Exception as e:
                # Critical error in counter operations - this is serious
                logger.error(
                    f"🚨 [{self._provider_name}-BUDGET] CRITICAL: Failed to record call for {component}: {e}"
                )
                # Re-raise to alert the caller that something went wrong
                raise

    def _calculate_daily_limit(self) -> int:
        """
        Calculate daily limit based on actual days in current month.

        Returns:
            Daily limit (0 if unlimited)
        """
        if not self._allocations:
            return 0

        # Get current month and year
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month

        # Get number of days in current month
        days_in_month = calendar.monthrange(year, month)[1]

        # Calculate daily limit
        total_allocation = sum(self._allocations.values())
        daily_limit = total_allocation // days_in_month

        return daily_limit

    def _check_budget_status(self) -> None:
        """
        Check budget status and trigger monitoring.

        This method is called after each API call to check if the budget
        status has changed and trigger intelligent monitoring.
        """
        if not self._monitor:
            return

        try:
            # Get current budget status
            status = self.get_status()

            # Convert to dictionary for monitoring
            status_dict = status.to_dict()

            # Check budget status with monitor
            self._monitor.check_budget_status(self._provider_name, status_dict)

        except Exception as e:
            # Monitoring failure is non-critical, just log error
            logger.debug(f"🔍 [{self._provider_name}-BUDGET] Failed to check budget status: {e}")

    def get_status(self) -> BudgetStatus:
        """
        Get current budget status.

        Returns:
            BudgetStatus with usage information
        """
        with self._lock:
            self._check_daily_reset()

            usage_pct = self._monthly_used / self._monthly_limit if self._monthly_limit > 0 else 0

            # V2.0: Calculate daily_limit using actual days in month
            daily_limit = self._calculate_daily_limit()

            return BudgetStatus(
                monthly_used=self._monthly_used,
                monthly_limit=self._monthly_limit,
                daily_used=self._daily_used,
                daily_limit=daily_limit,
                is_degraded=usage_pct >= self.get_degraded_threshold()
                if self._monthly_limit > 0
                else False,
                is_disabled=usage_pct >= self.get_disabled_threshold()
                if self._monthly_limit > 0
                else False,
                usage_percentage=usage_pct * 100,
                component_usage=dict(self._component_usage),
                daily_reset_date=None,  # Not tracked in BaseBudgetManager
                provider_name=self._provider_name,
            )

    def reset_monthly(self) -> None:
        """
        Reset monthly counters.

        Called on month boundary.
        """
        with self._lock:
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
        """
        Check if we need to reset daily counters.

        NOTE: This method is called from within locked contexts in can_call() and record_call().
        When called from other methods, it must be protected by the lock externally.
        """
        now = datetime.now(timezone.utc)
        current_day = now.day
        current_month = now.month

        # Monthly reset
        if self._last_reset_month is None:
            self._last_reset_month = current_month
        elif current_month != self._last_reset_month:
            logger.info("📅 New month detected, resetting budget")
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
                f"🚨 [{self._provider_name}-BUDGET] DISABLED threshold reached ({self.get_disabled_threshold() * 100:.0f}%): "
                f"Only critical calls allowed"
            )

        # Check degraded threshold
        degraded_count = int(self._monthly_limit * self.get_degraded_threshold())
        if self._monthly_used == degraded_count:
            logger.warning(
                f"⚠️ [{self._provider_name}-BUDGET] DEGRADED threshold reached ({self.get_degraded_threshold() * 100:.0f}%): "
                f"Non-critical calls throttled"
            )

    def get_remaining_budget(self) -> int:
        """Get remaining monthly budget."""
        with self._lock:
            return max(0, self._monthly_limit - self._monthly_used)

    def get_component_remaining(self, component: str) -> int:
        """Get remaining budget for a specific component."""
        with self._lock:
            allocation = self._allocations.get(component, 0)
            used = self._component_usage.get(component, 0)
            return max(0, allocation - used)
