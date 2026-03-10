"""
Budget Reporter Module - V1.1

Provides intelligent reporting of budget usage and trends.
Generates periodic reports for monitoring and analysis.

V1.1 Changes:
- Fixed path handling to use relative paths instead of os.getcwd()

Created: 2026-03-08
Purpose: Resolve missing intelligent reporting integration
"""

import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BudgetReporter:
    """
    Intelligent budget reporter with periodic reporting and trend analysis.

    Features:
    - Periodic reporting of budget usage
    - Trend analysis (usage over time)
    - Per-component reporting
    - Per-provider reporting
    - Report generation in multiple formats (text, JSON, CSV)
    """

    def __init__(
        self,
        report_interval_hours: int = 24,
        report_dir: str | None = None,
    ):
        """
        Initialize BudgetReporter.

        Args:
            report_interval_hours: Interval between reports (default: 24 hours)
            report_dir: Directory to save reports (default: data/budget_reports)
        """
        self._report_interval = report_interval_hours * 3600  # Convert to seconds
        # Use pathlib for reliable relative path handling
        if report_dir is None:
            report_dir = str(Path(__file__).parent.parent / "data" / "budget_reports")
        self._report_dir = report_dir

        # Ensure report directory exists
        os.makedirs(self._report_dir, exist_ok=True)

        # Track last report time
        self._last_report_time: dict[str, datetime] = {}

        # Callbacks for report generation
        self._report_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

        logger.info(
            f"📊 BudgetReporter initialized: {report_interval_hours}h interval, "
            f"reports in {self._report_dir}"
        )

    def register_report_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """
        Register a callback for report generation.

        Args:
            callback: Function to call when report is generated
                     (provider_name: str, report: dict[str, Any]) -> None
        """
        self._report_callbacks.append(callback)
        logger.debug(f"📊 Report callback registered: {callback.__name__}")

    def should_generate_report(self, provider_name: str) -> bool:
        """
        Check if report should be generated for a provider.

        Args:
            provider_name: Name of the provider

        Returns:
            True if report should be generated, False otherwise
        """
        last_report = self._last_report_time.get(provider_name)
        if last_report is None:
            return True

        time_since_last_report = (datetime.now(timezone.utc) - last_report).total_seconds()
        return time_since_last_report >= self._report_interval

    def generate_report(
        self,
        provider_name: str,
        status: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate budget report for a provider.

        Args:
            provider_name: Name of the provider
            status: Current budget status
            history: Optional budget history for trend analysis

        Returns:
            Report dictionary
        """
        # Generate report
        report = {
            "provider_name": provider_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_status": status,
            "trends": self._analyze_trends(history) if history else None,
            "recommendations": self._generate_recommendations(status),
        }

        # Update last report time
        self._last_report_time[provider_name] = datetime.now(timezone.utc)

        # Log report
        logger.info(f"📊 [{provider_name}] Budget report generated")

        # Call report callbacks
        for callback in self._report_callbacks:
            try:
                callback(provider_name, report)
            except Exception as e:
                logger.error(f"🚨 Report callback failed for {provider_name}: {e}")

        return report

    def _analyze_trends(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Analyze budget usage trends from history.

        Args:
            history: Budget history entries

        Returns:
            Trend analysis dictionary
        """
        if not history:
            return {}

        # Calculate trend metrics
        usage_percentages = [entry.get("usage_percentage", 0.0) for entry in history]
        monthly_used = [entry.get("monthly_used", 0) for entry in history]

        trends = {
            "entries": len(history),
            "avg_usage_percentage": sum(usage_percentages) / len(usage_percentages),
            "max_usage_percentage": max(usage_percentages),
            "min_usage_percentage": min(usage_percentages),
            "total_monthly_used": monthly_used[0] if monthly_used else 0,
            "usage_trend": self._calculate_usage_trend(usage_percentages),
        }

        return trends

    def _calculate_usage_trend(self, usage_percentages: list[float]) -> str:
        """
        Calculate usage trend (increasing, decreasing, stable).

        Args:
            usage_percentages: List of usage percentages

        Returns:
            Trend string
        """
        if len(usage_percentages) < 2:
            return "unknown"

        # Compare first and last entries
        first = usage_percentages[-1]
        last = usage_percentages[0]

        diff = last - first

        if diff > 5.0:
            return "increasing"
        elif diff < -5.0:
            return "decreasing"
        else:
            return "stable"

    def _generate_recommendations(self, status: dict[str, Any]) -> list[str]:
        """
        Generate recommendations based on budget status.

        Args:
            status: Current budget status

        Returns:
            List of recommendations
        """
        recommendations = []

        usage_percentage = status.get("usage_percentage", 0.0)
        is_degraded = status.get("is_degraded", False)
        is_disabled = status.get("is_disabled", False)

        # Check if budget is low
        if usage_percentage > 80.0:
            recommendations.append(
                f"⚠️ Budget usage is high ({usage_percentage:.1f}%). "
                f"Consider reducing non-critical operations."
            )

        # Check if budget is in degraded mode
        if is_degraded:
            recommendations.append(
                "⚠️ Budget is in degraded mode. Non-critical operations are being throttled."
            )

        # Check if budget is in disabled mode
        if is_disabled:
            recommendations.append(
                "🚨 Budget is in disabled mode. Only critical operations are allowed."
            )

        # Check component usage
        component_usage = status.get("component_usage")
        if component_usage:
            # Find components with high usage
            monthly_limit = status.get("monthly_limit", 0)
            for component, used in component_usage.items():
                component_percentage = (used / monthly_limit * 100) if monthly_limit > 0 else 0
                if component_percentage > 10.0:
                    recommendations.append(
                        f"📊 Component '{component}' uses {component_percentage:.1f}% of budget. "
                        f"Consider optimizing usage."
                    )

        # If no recommendations, add positive message
        if not recommendations:
            recommendations.append("✅ Budget usage is healthy. No recommendations.")

        return recommendations

    def save_report_to_file(self, report: dict[str, Any], format: str = "json") -> str:
        """
        Save report to file.

        Args:
            report: Report dictionary
            format: File format (json, txt, csv)

        Returns:
            Path to saved file
        """
        provider_name = report.get("provider_name", "unknown")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "json":
            filename = f"{provider_name}_report_{timestamp}.json"
            filepath = os.path.join(self._report_dir, filename)
            self._save_json_report(report, filepath)
        elif format == "txt":
            filename = f"{provider_name}_report_{timestamp}.txt"
            filepath = os.path.join(self._report_dir, filename)
            self._save_text_report(report, filepath)
        elif format == "csv":
            filename = f"{provider_name}_report_{timestamp}.csv"
            filepath = os.path.join(self._report_dir, filename)
            self._save_csv_report(report, filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"📊 Report saved to {filepath}")
        return filepath

    def _save_json_report(self, report: dict[str, Any], filepath: str) -> None:
        """Save report as JSON."""
        import json

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _save_text_report(self, report: dict[str, Any], filepath: str) -> None:
        """Save report as text."""
        with open(filepath, "w") as f:
            f.write(f"Budget Report: {report['provider_name']}\n")
            f.write(f"Generated: {report['timestamp']}\n")
            f.write("=" * 80 + "\n\n")

            # Current status
            status = report["current_status"]
            f.write("Current Status:\n")
            f.write(f"  Monthly Used: {status['monthly_used']}/{status['monthly_limit']}\n")
            f.write(f"  Daily Used: {status['daily_used']}/{status['daily_limit']}\n")
            f.write(f"  Usage: {status['usage_percentage']:.1f}%\n")
            f.write(f"  Degraded: {status['is_degraded']}\n")
            f.write(f"  Disabled: {status['is_disabled']}\n\n")

            # Recommendations
            f.write("Recommendations:\n")
            for rec in report["recommendations"]:
                f.write(f"  {rec}\n")

    def _save_csv_report(self, report: dict[str, Any], filepath: str) -> None:
        """Save report as CSV."""
        import csv

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow(
                [
                    "Provider",
                    "Timestamp",
                    "Monthly Used",
                    "Monthly Limit",
                    "Daily Used",
                    "Daily Limit",
                    "Usage %",
                    "Degraded",
                    "Disabled",
                ]
            )

            # Write status row
            status = report["current_status"]
            writer.writerow(
                [
                    report["provider_name"],
                    report["timestamp"],
                    status["monthly_used"],
                    status["monthly_limit"],
                    status["daily_used"],
                    status["daily_limit"],
                    f"{status['usage_percentage']:.2f}",
                    status["is_degraded"],
                    status["is_disabled"],
                ]
            )


# Global reporter instance
_global_reporter: BudgetReporter | None = None
_reporter_lock = threading.Lock()


def get_budget_reporter() -> BudgetReporter:
    """
    Get global budget reporter instance.

    Returns:
        BudgetReporter instance
    """
    global _global_reporter

    with _reporter_lock:
        if _global_reporter is None:
            _global_reporter = BudgetReporter()
        return _global_reporter
