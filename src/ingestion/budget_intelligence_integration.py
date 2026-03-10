"""
Budget Intelligence Integration Module - V1.1

Integrates intelligent budget monitoring, reporting, and alerting into the bot.
Provides periodic monitoring of circuit status and budget health.

V1.1 Changes:
- Fixed lock management to use asyncio.Lock instead of threading.Lock for async operations

Created: 2026-03-08
Purpose: Resolve missing intelligent integration of budget monitoring
"""

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class BudgetIntelligenceIntegration:
    """
    Integrates intelligent budget features into the bot.

    Features:
    - Periodic monitoring of circuit status
    - Automatic reporting of budget usage
    - Intelligent alerting for budget issues
    - Integration with existing bot components
    """

    def __init__(
        self,
        monitoring_interval_seconds: int = 3600,
        reporting_interval_hours: int = 24,
    ):
        """
        Initialize BudgetIntelligenceIntegration.

        Args:
            monitoring_interval_seconds: Interval between monitoring cycles (default: 1 hour)
            reporting_interval_hours: Interval between reports (default: 24 hours)
        """
        self._monitoring_interval = monitoring_interval_seconds
        self._reporting_interval = reporting_interval_hours * 3600  # Convert to seconds

        self._monitoring_task: asyncio.Task | None = None
        self._monitoring_active = False
        self._lock = asyncio.Lock()

        # Track last report time
        self._last_report_time: dict[str, datetime] = {}

        logger.info(
            f"🔍 BudgetIntelligenceIntegration initialized: "
            f"{monitoring_interval_seconds}s monitoring, {reporting_interval_hours}h reporting"
        )

    async def start_monitoring(self) -> None:
        """Start periodic monitoring in background."""
        async with self._lock:
            if self._monitoring_active:
                logger.warning("🔍 Budget monitoring already active")
                return

            self._monitoring_active = True
            logger.info(f"🔍 Budget monitoring started (interval: {self._monitoring_interval}s)")

        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self) -> None:
        """Stop periodic monitoring."""
        async with self._lock:
            if not self._monitoring_active:
                logger.warning("🔍 Budget monitoring not active")
                return

            self._monitoring_active = False
            logger.info("🔍 Budget monitoring stopped")

        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("🔍 Budget monitoring loop started")

        while self._monitoring_active:
            try:
                # Monitor circuit status
                await self._monitor_circuit_status()

                # Generate reports if needed
                await self._generate_reports()

                # Wait for next cycle
                await asyncio.sleep(self._monitoring_interval)

            except asyncio.CancelledError:
                logger.info("🔍 Budget monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"🚨 Budget monitoring loop error: {e}")
                # Wait for next cycle even if error occurs
                await asyncio.sleep(self._monitoring_interval)

        logger.info("🔍 Budget monitoring loop stopped")

    async def _monitor_circuit_status(self) -> None:
        """Monitor circuit status from IntelligenceRouter."""
        try:
            # Import IntelligenceRouter (lazy import to avoid circular dependencies)
            from src.services.intelligence_router import IntelligenceRouter

            # Get IntelligenceRouter instance
            router = IntelligenceRouter()

            # Get circuit status
            circuit_status = router.get_circuit_status()

            if not circuit_status:
                logger.debug("🔍 No circuit status available")
                return

            # Log circuit status
            provider = circuit_status.get("provider", "unknown")
            available = circuit_status.get("available", False)
            budget_status = circuit_status.get("budget", {})

            logger.info(
                f"🔍 Circuit Status: {provider} available={available}, "
                f"budget={budget_status.get('usage_percentage', 0):.1f}%"
            )

            # Check budget status for alerts
            await self._check_budget_alerts(provider, budget_status)

        except ImportError as e:
            logger.warning(f"⚠️ Failed to import IntelligenceRouter: {e}")
        except Exception as e:
            logger.error(f"🚨 Failed to monitor circuit status: {e}")

    async def _check_budget_alerts(self, provider_name: str, budget_status: dict[str, Any]) -> None:
        """
        Check budget status for alerts.

        Args:
            provider_name: Name of the provider
            budget_status: Budget status dictionary
        """
        usage_percentage = budget_status.get("usage_percentage", 0.0)
        is_degraded = budget_status.get("is_degraded", False)
        is_disabled = budget_status.get("is_disabled", False)

        # Check for degraded mode
        if is_degraded and not is_disabled:
            logger.warning(f"⚠️ [{provider_name}] Budget DEGRADED: {usage_percentage:.1f}%")

        # Check for disabled mode
        if is_disabled:
            logger.error(f"🚨 [{provider_name}] Budget DISABLED: {usage_percentage:.1f}%")

    async def _generate_reports(self) -> None:
        """Generate budget reports if needed."""
        try:
            # Import BudgetReporter (lazy import)
            from src.ingestion.budget_reporter import get_budget_reporter
            from src.services.intelligence_router import IntelligenceRouter

            reporter = get_budget_reporter()

            # Get IntelligenceRouter instance
            router = IntelligenceRouter()

            # Get circuit status
            circuit_status = router.get_circuit_status()
            if not circuit_status:
                return

            budget_status = circuit_status.get("budget", {})
            provider_name = circuit_status.get("provider", "unknown")

            # Check if report should be generated
            if reporter.should_generate_report(provider_name):
                # Get budget history
                from src.ingestion.budget_persistence import BudgetPersistence

                persistence = BudgetPersistence()
                history = persistence.get_budget_history(provider_name, hours=24)

                # Generate report
                report = reporter.generate_report(
                    provider_name=provider_name,
                    status=budget_status,
                    history=history,
                )

                # Save report to file
                try:
                    reporter.save_report_to_file(report, format="json")
                except Exception as e:
                    logger.error(f"🚨 Failed to save report: {e}")

        except ImportError as e:
            logger.warning(f"⚠️ Failed to import reporting modules: {e}")
        except Exception as e:
            logger.error(f"🚨 Failed to generate reports: {e}")


# Global integration instance
_global_integration: BudgetIntelligenceIntegration | None = None
_integration_lock = threading.Lock()  # threading.Lock for singleton pattern (synchronous)


def get_budget_intelligence_integration() -> BudgetIntelligenceIntegration:
    """
    Get global budget intelligence integration instance.

    Returns:
        BudgetIntelligenceIntegration instance
    """
    global _global_integration

    with _integration_lock:
        if _global_integration is None:
            _global_integration = BudgetIntelligenceIntegration()
        return _global_integration


async def start_budget_intelligence() -> None:
    """Start budget intelligence monitoring."""
    integration = get_budget_intelligence_integration()
    await integration.start_monitoring()


async def stop_budget_intelligence() -> None:
    """Stop budget intelligence monitoring."""
    integration = get_budget_intelligence_integration()
    await integration.stop_monitoring()
