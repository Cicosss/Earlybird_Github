"""
EarlyBird Health Monitor

Tracks system health and sends periodic heartbeat reports.
Includes spam protection for error alerts and self-diagnosis capabilities.

Historical Version: V3.7

Production-ready with comprehensive system diagnostics
- System diagnostics (disk, database, APIs)
- 6-hour cooldown per issue type to prevent spam
Updated: 2026-02-23 (Centralized Version Tracking)
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil
import requests
import requests.exceptions
from sqlalchemy import text

# Import centralized version tracking
from src.version import get_version_with_module

# Log version on import
logger = logging.getLogger(__name__)
logger.info(f"📦 {get_version_with_module('Health Monitor')}")

# Try to import database models, but don't fail if not available
# (allows health monitor to work even if DB is down)
try:
    from src.database.models import SessionLocal

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    SessionLocal = None

logger = logging.getLogger(__name__)

# ============================================
# CONSTANTS
# ============================================
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARNING = "WARNING"

ISSUE_COOLDOWN_HOURS = 6
ERROR_ALERT_COOLDOWN_MINUTES = 30
HEARTBEAT_INTERVAL_HOURS = 4

DISK_WARNING_THRESHOLD = 80
DISK_CRITICAL_THRESHOLD = 90

API_TIMEOUT_SECONDS = 10

# Persistence file for health stats
STATS_FILE = Path("data/health_stats.json")


# ============================================
# DATA CLASSES
# ============================================


@dataclass
class HealthStats:
    """Container for health statistics."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_scans: int = 0
    total_alerts_sent: int = 0
    total_errors: int = 0
    last_scan_time: datetime | None = None
    last_alert_time: datetime | None = None
    last_error_time: datetime | None = None
    last_error_message: str = ""
    matches_processed: int = 0
    news_items_analyzed: int = 0


# ============================================
# HEALTH MONITOR CLASS
# ============================================


class HealthMonitor:
    """
    Health monitoring system with spam protection.

    Features:
    - Tracks scans, alerts, errors
    - Periodic heartbeat reports (every 4 hours)
    - Error alert cooldown (30 minutes between alerts)
    - Uptime tracking
    - V3.7: Self-diagnosis (disk, database, APIs)
    """

    def __init__(self):
        self.stats = HealthStats()
        self._stats_lock = threading.Lock()  # Thread-safe stats operations
        self._last_error_alert_time: datetime | None = None
        self._last_heartbeat_time: datetime | None = None
        self._error_count_since_last_alert = 0
        # V3.7: Track last alert time per issue type (anti-spam)
        self.last_alerts: dict[str, datetime] = {}

        # Load stats from file on startup
        self._load_stats_from_file()

        logger.info("Health Monitor initialized")

    def _load_stats_from_file(self) -> None:
        """Load stats from JSON file on startup."""
        try:
            if STATS_FILE.exists():
                with open(STATS_FILE, "r") as f:
                    data = json.load(f)

                # Load stats into HealthStats object
                self.stats.total_scans = data.get("total_scans", 0)
                self.stats.total_alerts_sent = data.get("total_alerts_sent", 0)
                self.stats.total_errors = data.get("total_errors", 0)
                self.stats.matches_processed = data.get("matches_processed", 0)
                self.stats.news_items_analyzed = data.get("news_items_analyzed", 0)

                # Load datetime fields
                if "start_time" in data:
                    try:
                        self.stats.start_time = datetime.fromisoformat(data["start_time"])
                    except (ValueError, TypeError):
                        pass  # Keep default if parsing fails

                if "last_scan_time" in data and data["last_scan_time"]:
                    try:
                        self.stats.last_scan_time = datetime.fromisoformat(data["last_scan_time"])
                    except (ValueError, TypeError):
                        pass

                if "last_alert_time" in data and data["last_alert_time"]:
                    try:
                        self.stats.last_alert_time = datetime.fromisoformat(data["last_alert_time"])
                    except (ValueError, TypeError):
                        pass

                if "last_error_time" in data and data["last_error_time"]:
                    try:
                        self.stats.last_error_time = datetime.fromisoformat(data["last_error_time"])
                    except (ValueError, TypeError):
                        pass

                self.stats.last_error_message = data.get("last_error_message", "")

                logger.info(
                    f"Loaded stats from file: {self.stats.total_scans} scans, {self.stats.total_alerts_sent} alerts"
                )
        except Exception as e:
            logger.warning(f"Failed to load stats from file: {e}")
            # Continue with default values

    def _save_stats_to_file(self) -> None:
        """Save stats to JSON file."""
        try:
            data = {
                "total_scans": self.stats.total_scans,
                "total_alerts_sent": self.stats.total_alerts_sent,
                "total_errors": self.stats.total_errors,
                "matches_processed": self.stats.matches_processed,
                "news_items_analyzed": self.stats.news_items_analyzed,
                "start_time": self.stats.start_time.isoformat() if self.stats.start_time else None,
                "last_scan_time": self.stats.last_scan_time.isoformat()
                if self.stats.last_scan_time
                else None,
                "last_alert_time": self.stats.last_alert_time.isoformat()
                if self.stats.last_alert_time
                else None,
                "last_error_time": self.stats.last_error_time.isoformat()
                if self.stats.last_error_time
                else None,
                "last_error_message": self.stats.last_error_message,
            }

            # Create directory if it doesn't exist
            STATS_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(STATS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats to file: {e}")
            # Continue without crashing

    @property
    def uptime(self) -> timedelta:
        """Get system uptime."""
        return datetime.now(timezone.utc) - self.stats.start_time

    @property
    def uptime_str(self) -> str:
        """Get formatted uptime string."""
        delta = self.uptime
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def record_scan(self, matches_count: int = 0, news_count: int = 0) -> None:
        """Record a completed scan cycle."""
        try:
            with self._stats_lock:
                self.stats.total_scans += 1
                self.stats.last_scan_time = datetime.now(timezone.utc)
                self.stats.matches_processed += matches_count
                self.stats.news_items_analyzed += news_count
            logger.debug(f"Scan #{self.stats.total_scans} recorded")
            # Save stats to file
            self._save_stats_to_file()
        except Exception as e:
            logger.error(f"Failed to record scan: {e}")
            # Continue without crashing

    def record_alert_sent(self) -> None:
        """Record an alert that was sent."""
        try:
            with self._stats_lock:
                self.stats.total_alerts_sent += 1
                self.stats.last_alert_time = datetime.now(timezone.utc)
            logger.debug(f"Alert #{self.stats.total_alerts_sent} recorded")
            # Save stats to file
            self._save_stats_to_file()
        except Exception as e:
            logger.error(f"Failed to record alert: {e}")
            # Continue without crashing

    def record_error(self, error_message: str) -> None:
        """Record an error occurrence."""
        try:
            with self._stats_lock:
                self.stats.total_errors += 1
                self.stats.last_error_time = datetime.now(timezone.utc)
                self.stats.last_error_message = str(error_message)[:200]
                self._error_count_since_last_alert += 1
            logger.debug(f"Error #{self.stats.total_errors} recorded")
            # Save stats to file
            self._save_stats_to_file()
        except Exception as e:
            logger.error(f"Failed to record error: {e}")
            # Continue without crashing

    def should_send_error_alert(self) -> bool:
        """
        Check if we should send an error alert.

        Returns True only if:
        - No error alert sent in the last 30 minutes

        This prevents spam loops when errors occur repeatedly.
        """
        if self._last_error_alert_time is None:
            return True

        cooldown = timedelta(minutes=ERROR_ALERT_COOLDOWN_MINUTES)
        time_since_last = datetime.now(timezone.utc) - self._last_error_alert_time

        if time_since_last >= cooldown:
            return True

        remaining = cooldown - time_since_last
        logger.debug(f"Error alert suppressed. Cooldown: {remaining.seconds // 60}m remaining")
        return False

    def mark_error_alert_sent(self) -> None:
        """Mark that an error alert was just sent."""
        try:
            self._last_error_alert_time = datetime.now(timezone.utc)
            suppressed_count = self._error_count_since_last_alert - 1
            self._error_count_since_last_alert = 0

            if suppressed_count > 0:
                logger.info(f"Error alert sent ({suppressed_count} similar errors were suppressed)")
        except Exception as e:
            logger.error(f"Failed to mark error alert sent: {e}")
            # Continue without crashing

    def should_send_heartbeat(self) -> bool:
        """
        Check if it's time to send a heartbeat report.

        Returns True every 4 hours.
        """
        try:
            if self._last_heartbeat_time is None:
                return True

            interval = timedelta(hours=HEARTBEAT_INTERVAL_HOURS)
            time_since_last = datetime.now(timezone.utc) - self._last_heartbeat_time

            return time_since_last >= interval
        except Exception as e:
            logger.error(f"Failed to check heartbeat status: {e}")
            return False  # Don't send heartbeat if check fails

    def mark_heartbeat_sent(self) -> None:
        """Mark that a heartbeat was just sent."""
        try:
            self._last_heartbeat_time = datetime.now(timezone.utc)
            logger.info("Heartbeat sent")
        except Exception as e:
            logger.error(f"Failed to mark heartbeat sent: {e}")
            # Continue without crashing

    def get_heartbeat_message(
        self, api_quota: dict[str, Any] | None = None, cache_metrics: dict[str, Any] | None = None
    ) -> str:
        """
        Generate heartbeat status message.

        Args:
            api_quota: Optional dict with 'remaining' and 'used' keys
            cache_metrics: Optional dict with Supabase cache metrics (V12.5)

        Returns:
            Formatted status message
        """
        try:
            with self._stats_lock:
                total_scans = self.stats.total_scans
                total_alerts_sent = self.stats.total_alerts_sent
                total_errors = self.stats.total_errors
                matches_processed = self.stats.matches_processed
                news_items_analyzed = self.stats.news_items_analyzed
                last_scan_time = self.stats.last_scan_time
        except Exception as e:
            logger.error(f"Failed to read stats for heartbeat: {e}")
            total_scans = 0
            total_alerts_sent = 0
            total_errors = 0
            matches_processed = 0
            news_items_analyzed = 0
            last_scan_time = None

        lines = [
            "💓 <b>EARLYBIRD HEARTBEAT</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"⏱️ Uptime: <b>{self.uptime_str}</b>",
            f"🔄 Scans: <b>{total_scans}</b>",
            f"📤 Alerts Sent: <b>{total_alerts_sent}</b>",
            f"⚽ Matches Processed: <b>{matches_processed}</b>",
            f"📰 News Analyzed: <b>{news_items_analyzed}</b>",
        ]

        # Add error info if any
        if total_errors > 0:
            lines.append(f"❌ Errors: <b>{total_errors}</b>")

        # Add API quota if available
        if api_quota:
            remaining = api_quota.get("remaining", "N/A")
            used = api_quota.get("used", "N/A")
            lines.append(f"💰 API Quota: <b>{remaining}</b> remaining ({used} used)")

        # Add cache metrics if available (V12.5)
        if cache_metrics:
            hit_ratio = cache_metrics.get("hit_ratio_percent", 0.0)
            hit_count = cache_metrics.get("hit_count", 0)
            miss_count = cache_metrics.get("miss_count", 0)
            bypass_count = cache_metrics.get("bypass_count", 0)
            total_requests = cache_metrics.get("total_requests", 0)
            ttl_seconds = cache_metrics.get("cache_ttl_seconds", 0)
            cached_keys = cache_metrics.get("cached_keys_count", 0)

            lines.append(
                f"💾 Cache Hit Ratio: <b>{hit_ratio:.1f}%</b> ({hit_count} hits, {miss_count} misses)"
            )
            if bypass_count > 0:
                lines.append(f"🔄 Cache Bypass: <b>{bypass_count}</b> requests")
            lines.append(f"⏱️ Cache TTL: <b>{ttl_seconds}s</b> ({cached_keys} keys cached)")

            # V2.0: Add SWR cache metrics if available
            swr_team_hit_rate = cache_metrics.get("swr_team_data_hit_rate", None)
            swr_match_hit_rate = cache_metrics.get("swr_match_data_hit_rate", None)
            swr_search_hit_rate = cache_metrics.get("swr_search_hit_rate", None)

            if swr_team_hit_rate is not None:
                lines.append(f"📦 Team Cache Hit Rate: <b>{swr_team_hit_rate:.1f}%</b>")
            if swr_match_hit_rate is not None:
                lines.append(f"📦 Match Cache Hit Rate: <b>{swr_match_hit_rate:.1f}%</b>")
            if swr_search_hit_rate is not None:
                lines.append(f"📦 Search Cache Hit Rate: <b>{swr_search_hit_rate:.1f}%</b>")

            # Add background refresh metrics
            swr_team_bg_refreshes = cache_metrics.get("swr_team_data_background_refreshes", 0)
            swr_match_bg_refreshes = cache_metrics.get("swr_match_data_background_refreshes", 0)
            swr_team_bg_failures = cache_metrics.get("swr_team_data_background_refresh_failures", 0)
            swr_match_bg_failures = cache_metrics.get(
                "swr_match_data_background_refresh_failures", 0
            )

            if swr_team_bg_refreshes > 0 or swr_match_bg_refreshes > 0:
                lines.append(
                    f"🔄 BG Refreshes: Team={swr_team_bg_refreshes} (failures: {swr_team_bg_failures}), "
                    f"Match={swr_match_bg_refreshes} (failures: {swr_match_bg_failures})"
                )

        # Add last scan time
        if last_scan_time:
            try:
                time_ago = datetime.now(timezone.utc) - last_scan_time
                minutes_ago = time_ago.seconds // 60
                lines.append(f"🕐 Last Scan: <b>{minutes_ago}m ago</b>")
            except Exception as e:
                logger.error(f"Failed to calculate time since last scan: {e}")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("✅ System operational")

        return "\n".join(lines)

    def get_error_message(self, error: Exception) -> str:
        """
        Generate error alert message.

        Args:
            error: The exception that occurred

        Returns:
            Formatted error message
        """
        try:
            with self._stats_lock:
                total_scans = self.stats.total_scans
                total_errors = self.stats.total_errors
        except Exception as e:
            logger.error(f"Failed to read stats for error message: {e}")
            total_scans = 0
            total_errors = 0

        error_type = type(error).__name__
        error_msg = str(error)[:300]

        # Count suppressed errors
        suppressed = self._error_count_since_last_alert - 1
        suppressed_text = f"\n⚠️ ({suppressed} similar errors suppressed)" if suppressed > 0 else ""

        lines = [
            "🚨 <b>EARLYBIRD CRITICAL ERROR</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"❌ Type: <code>{error_type}</code>",
            f"📝 Message: <code>{error_msg}</code>",
            f"⏱️ Uptime: {self.uptime_str}",
            f"🔄 Scans completed: {total_scans}",
            f"❌ Total errors: {total_errors}",
            suppressed_text,
            "━━━━━━━━━━━━━━━━━━━━",
            "🔄 System will attempt restart...",
        ]

        return "\n".join(line for line in lines if line)

    def get_stats_dict(self) -> dict[str, Any]:
        """Get stats as dictionary for API/logging."""
        try:
            with self._stats_lock:
                total_scans = self.stats.total_scans
                total_alerts_sent = self.stats.total_alerts_sent
                total_errors = self.stats.total_errors
                matches_processed = self.stats.matches_processed
                news_items_analyzed = self.stats.news_items_analyzed
                last_scan = self.stats.last_scan_time
                last_error_time = self.stats.last_error_time
                last_error_message = self.stats.last_error_message
        except Exception as e:
            logger.error(f"Failed to read stats for dict: {e}")
            total_scans = 0
            total_alerts_sent = 0
            total_errors = 0
            matches_processed = 0
            news_items_analyzed = 0
            last_scan = None
            last_error_time = None
            last_error_message = None

        return {
            "uptime": self.uptime_str,
            "total_scans": total_scans,
            "total_alerts_sent": total_alerts_sent,
            "total_errors": total_errors,
            "matches_processed": matches_processed,
            "news_items_analyzed": news_items_analyzed,
            "last_scan": last_scan.isoformat() if last_scan else None,
            "last_error": last_error_message if last_error_time else None,
        }

    # ============================================
    # SELF-DIAGNOSIS AGENT
    # ============================================

    def run_diagnostics(self) -> list[tuple[str, str, str]]:
        """
        Esegue diagnostica completa del sistema.

        Controlli:
        1. SYSTEM: Spazio disco (> 90% = ERROR)
        2. DATABASE: Connessione SQLite (timeout/error = CRITICAL)
        3. APIs: Verifica accesso Odds API (401/403 = WARNING)

        Returns:
            Lista di tuple (issue_key, severity, message_it)
        """
        issues = []

        # --- 1. SYSTEM: Disk Usage ---
        issues.extend(self._check_disk_usage())

        # --- 2. DATABASE: Connection Check ---
        issues.extend(self._check_database())

        # --- 3. APIs: Odds API Check ---
        issues.extend(self._check_odds_api())

        return issues

    def _check_disk_usage(self) -> list[tuple[str, str, str]]:
        """Check disk usage and return issues if thresholds exceeded."""
        issues = []
        try:
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent

            if disk_percent > DISK_CRITICAL_THRESHOLD:
                issues.append(
                    (
                        "disk_full",
                        SEVERITY_ERROR,
                        f"⚠️ Disco in esaurimento: {disk_percent:.1f}% utilizzato",
                    )
                )
                logger.warning(f"DISK CRITICAL: {disk_percent:.1f}% used")
            elif disk_percent > DISK_WARNING_THRESHOLD:
                logger.info(f"Disk usage: {disk_percent:.1f}%")
            else:
                logger.debug(f"Disk usage: {disk_percent:.1f}%")
        except Exception as e:
            issues.append(
                (
                    "disk_check_failed",
                    SEVERITY_WARNING,
                    f"⚠️ Impossibile verificare disco: {str(e)[:100]}",
                )
            )
            logger.error(f"Disk check failed: {e}")

        return issues

    def _check_database(self) -> list[tuple[str, str, str]]:
        """Check database connectivity and return issues if any."""
        issues = []

        if not DB_AVAILABLE or SessionLocal is None:
            issues.append(
                ("database_unavailable", SEVERITY_WARNING, "⚠️ Database module not available")
            )
            return issues

        try:
            db = SessionLocal()
            try:
                # Simple query to verify connection
                result = db.execute(text("SELECT 1")).fetchone()
                if result and result[0] == 1:
                    logger.debug("Database connection OK")
                else:
                    raise Exception("Unexpected query result")
            finally:
                db.close()
        except Exception as e:
            issues.append(
                (
                    "database_error",
                    SEVERITY_CRITICAL,
                    f"🚨 Database non raggiungibile: {str(e)[:100]}",
                )
            )
            logger.error(f"DATABASE CRITICAL: {e}")

        return issues

    def _check_odds_api(self) -> list[tuple[str, str, str]]:
        """Check Odds API connectivity and return issues if any."""
        issues = []

        odds_api_key = os.getenv("ODDS_API_KEY")
        if not odds_api_key:
            logger.debug("Odds API key not configured - skipping check")
            return issues

        try:
            # Quick check - just verify API key is valid (use sports endpoint)
            url = f"https://api.the-odds-api.com/v4/sports/?apiKey={odds_api_key}"
            response = requests.get(url, timeout=API_TIMEOUT_SECONDS)

            if response.status_code == 401:
                issues.append(
                    (
                        "odds_api_auth",
                        SEVERITY_WARNING,
                        "⚠️ API Quote Errore: Chiave API non valida (401)",
                    )
                )
                logger.warning("Odds API: Invalid API key (401)")
            elif response.status_code == 403:
                issues.append(
                    (
                        "odds_api_forbidden",
                        SEVERITY_WARNING,
                        "⚠️ API Quote Errore: Accesso negato (403)",
                    )
                )
                logger.warning("Odds API: Forbidden (403)")
            elif response.status_code == 429:
                issues.append(
                    ("odds_api_quota", SEVERITY_WARNING, "⚠️ API Quote Errore: Quota esaurita (429)")
                )
                logger.warning("Odds API: Rate limited (429)")
            elif response.status_code != 200:
                logger.warning(f"Odds API: Unexpected status {response.status_code}")
            else:
                logger.debug("Odds API connection OK")

        except requests.exceptions.Timeout:
            issues.append(
                ("odds_api_timeout", SEVERITY_WARNING, "⚠️ API Quote Errore: Timeout connessione")
            )
            logger.warning("Odds API: Connection timeout")
        except requests.exceptions.ConnectionError as e:
            issues.append(
                ("odds_api_connection", SEVERITY_WARNING, "⚠️ API Quote Errore: Connessione fallita")
            )
            logger.warning(f"Odds API: Connection error - {e}")
        except Exception as e:
            logger.error(f"Odds API check failed: {e}")

        return issues

    def report_issues(self, issues: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        """
        Filtra issues già segnalati nelle ultime 6 ore e invia alert per i nuovi.

        Args:
            issues: Lista di tuple (issue_key, severity, message_it)

        Returns:
            Lista di issues nuovi (non in cooldown)
        """
        if not issues:
            return []

        try:
            now = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"Failed to get current time for report_issues: {e}")
            return []

        cooldown = timedelta(hours=ISSUE_COOLDOWN_HOURS)
        new_issues = []

        # Use lock for thread-safe access to last_alerts
        with self._stats_lock:
            for issue_key, severity, message in issues:
                last_alert = self.last_alerts.get(issue_key)

                # Check cooldown
                if last_alert and (now - last_alert) < cooldown:
                    hours_ago = (now - last_alert).total_seconds() / 3600
                    logger.debug(f"Issue '{issue_key}' in cooldown ({hours_ago:.1f}h ago)")
                    continue

                # New issue - add to list and update timestamp
                new_issues.append((issue_key, severity, message))
                self.last_alerts[issue_key] = now
                logger.info(f"New issue detected: {issue_key} ({severity})")

        # Send alert if there are new issues
        if new_issues:
            self._send_diagnostic_alert(new_issues)

        return new_issues

    def _send_diagnostic_alert(self, issues: list[tuple[str, str, str]]) -> None:
        """
        Invia alert diagnostico a Telegram.

        Args:
            issues: Lista di tuple (issue_key, severity, message_it)
        """
        try:
            from src.alerting.notifier import send_status_message

            # Build message
            lines = [
                "🩺 <b>DIAGNOSTICA SISTEMA</b>",
                "━━━━━━━━━━━━━━━━━━━━",
            ]

            for issue_key, severity, message in issues:
                severity_emoji = {
                    SEVERITY_CRITICAL: "🔴",
                    SEVERITY_ERROR: "🟠",
                    SEVERITY_WARNING: "🟡",
                }.get(severity, "⚪")
                lines.append(f"{severity_emoji} {message}")

            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"⏱️ Uptime: {self.uptime_str}")

            message = "\n".join(lines)
            send_status_message(message)

            logger.info(f"Diagnostic alert sent ({len(issues)} issues)")
        except Exception as e:
            logger.error(f"Failed to send diagnostic alert: {e}")


# ============================================
# SINGLETON INSTANCE
# ============================================

_monitor_instance: HealthMonitor | None = None
_monitor_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_health_monitor() -> HealthMonitor:
    """
    Get singleton instance of HealthMonitor.

    V12.2: Fixed lazy initialization race condition.
    Multiple threads can safely call this function concurrently.
    """
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_instance_init_lock:
            # Double-checked locking pattern for thread safety
            if _monitor_instance is None:
                _monitor_instance = HealthMonitor()
    return _monitor_instance
