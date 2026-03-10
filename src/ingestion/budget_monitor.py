"""
Budget Monitor Module - V1.0

Provides intelligent monitoring of budget status with state change detection.
Detects budget threshold crossings and triggers alerts.

Created: 2026-03-08
Purpose: Resolve missing budget_monitor.py file
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BudgetMonitor:
    """
    Intelligent budget monitor with state change detection.

    Features:
    - State change detection (normal -> degraded -> disabled)
    - Alert triggering on threshold crossings
    - Per-provider monitoring
    - Thread-safe operations
    """

    def __init__(self):
        """Initialize BudgetMonitor."""
        # Track last known state for each provider
        self._last_states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Alert callbacks
        self._alert_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

        logger.info("🔍 BudgetMonitor initialized")

    def start_monitoring(self) -> None:
        """
        Start budget monitoring.

        This is a no-op for the synchronous monitor.
        Actual monitoring is done via check_budget_status() calls.
        """
        logger.debug("🔍 Budget monitoring started")

    def stop_monitoring(self) -> None:
        """
        Stop budget monitoring.

        This is a no-op for the synchronous monitor.
        """
        logger.debug("🔍 Budget monitoring stopped")

    def register_alert_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """
        Register an alert callback.

        Args:
            callback: Function to call on budget state change
                      (provider_name: str, alert_data: dict[str, Any]) -> None
        """
        with self._lock:
            self._alert_callbacks.append(callback)
            logger.debug(f"🔍 Alert callback registered: {callback.__name__}")

    def check_budget_status(self, provider_name: str, status: dict[str, Any]) -> None:
        """
        Check budget status and detect state changes.

        Args:
            provider_name: Name of the provider
            status: Current budget status dictionary
        """
        with self._lock:
            # Get last known state
            last_state = self._last_states.get(provider_name)

            # Check for state changes
            if last_state is None:
                # First time seeing this provider - just record state
                self._last_states[provider_name] = status.copy()
                logger.debug(f"🔍 [{provider_name}] Initial state recorded")
                return

            # Detect state changes
            self._detect_state_changes(provider_name, last_state, status)

            # Update last known state
            self._last_states[provider_name] = status.copy()

    def _detect_state_changes(
        self,
        provider_name: str,
        last_state: dict[str, Any],
        current_state: dict[str, Any],
    ) -> None:
        """
        Detect and report state changes.

        Args:
            provider_name: Name of the provider
            last_state: Previous budget state
            current_state: Current budget state
        """
        # Check for degraded mode change
        last_degraded = last_state.get("is_degraded", False)
        current_degraded = current_state.get("is_degraded", False)

        if current_degraded and not last_degraded:
            # Entered degraded mode
            self._trigger_alert(
                provider_name,
                "degraded_mode_entered",
                current_state,
            )
        elif not current_degraded and last_degraded:
            # Exited degraded mode
            self._trigger_alert(
                provider_name,
                "degraded_mode_exited",
                current_state,
            )

        # Check for disabled mode change
        last_disabled = last_state.get("is_disabled", False)
        current_disabled = current_state.get("is_disabled", False)

        if current_disabled and not last_disabled:
            # Entered disabled mode
            self._trigger_alert(
                provider_name,
                "disabled_mode_entered",
                current_state,
            )
        elif not current_disabled and last_disabled:
            # Exited disabled mode
            self._trigger_alert(
                provider_name,
                "disabled_mode_exited",
                current_state,
            )

        # Check for usage percentage milestones
        last_usage = last_state.get("usage_percentage", 0.0)
        current_usage = current_state.get("usage_percentage", 0.0)

        # Check for crossing 50%, 75%, 90%, 95%
        milestones = [50.0, 75.0, 90.0, 95.0]
        for milestone in milestones:
            if last_usage < milestone and current_usage >= milestone:
                self._trigger_alert(
                    provider_name,
                    f"usage_milestone_{int(milestone)}",
                    current_state,
                )

    def _trigger_alert(
        self,
        provider_name: str,
        alert_type: str,
        status: dict[str, Any],
    ) -> None:
        """
        Trigger an alert.

        Args:
            provider_name: Name of the provider
            alert_type: Type of alert
            status: Current budget status
        """
        # Build alert data
        alert_data = {
            "alert_type": alert_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status.copy(),
        }

        # Call all registered callbacks
        for callback in self._alert_callbacks:
            try:
                callback(provider_name, alert_data)
            except Exception as e:
                logger.error(f"🚨 Alert callback failed for {provider_name}: {e}")


# Global monitor instance
_global_monitor: BudgetMonitor | None = None
_monitor_lock = threading.Lock()


def get_budget_monitor() -> BudgetMonitor:
    """
    Get global budget monitor instance.

    Returns:
        BudgetMonitor instance
    """
    global _global_monitor

    with _monitor_lock:
        if _global_monitor is None:
            _global_monitor = BudgetMonitor()
        return _global_monitor
