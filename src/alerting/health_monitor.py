"""
EarlyBird Health Monitor

Tracks system health and sends periodic heartbeat reports.
Includes spam protection for error alerts.

V3.7: Added Self-Diagnosis Agent (HealthMonitor)
- System diagnostics (disk, database, APIs)
- 6-hour cooldown per issue type to prevent spam
"""
import os
import logging
import psutil
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Issue severity levels
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARNING = "WARNING"

# Cooldown for repeated alerts (6 hours)
ISSUE_COOLDOWN_HOURS = 6


@dataclass
class HealthStats:
    """Container for health statistics."""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_scans: int = 0
    total_alerts_sent: int = 0
    total_errors: int = 0
    last_scan_time: Optional[datetime] = None
    last_alert_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None
    last_error_message: str = ""
    matches_processed: int = 0
    news_items_analyzed: int = 0


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
    
    # Cooldown periods
    ERROR_ALERT_COOLDOWN_MINUTES = 30
    HEARTBEAT_INTERVAL_HOURS = 4
    
    def __init__(self):
        self.stats = HealthStats()
        self._last_error_alert_time: Optional[datetime] = None
        self._last_heartbeat_time: Optional[datetime] = None
        self._error_count_since_last_alert = 0
        # V3.7: Track last alert time per issue type (anti-spam)
        self.last_alerts: Dict[str, datetime] = {}
        logger.info("💓 Health Monitor initialized")
    
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
    
    def record_scan(self, matches_count: int = 0, news_count: int = 0):
        """Record a completed scan cycle."""
        self.stats.total_scans += 1
        self.stats.last_scan_time = datetime.now(timezone.utc)
        self.stats.matches_processed += matches_count
        self.stats.news_items_analyzed += news_count
        logger.debug(f"📊 Scan #{self.stats.total_scans} recorded")
    
    def record_alert_sent(self):
        """Record an alert that was sent."""
        self.stats.total_alerts_sent += 1
        self.stats.last_alert_time = datetime.now(timezone.utc)
        logger.debug(f"📤 Alert #{self.stats.total_alerts_sent} recorded")
    
    def record_error(self, error_message: str):
        """Record an error occurrence."""
        self.stats.total_errors += 1
        self.stats.last_error_time = datetime.now(timezone.utc)
        self.stats.last_error_message = str(error_message)[:200]
        self._error_count_since_last_alert += 1
        logger.debug(f"❌ Error #{self.stats.total_errors} recorded")
    
    def should_send_error_alert(self) -> bool:
        """
        Check if we should send an error alert.
        
        Returns True only if:
        - No error alert sent in the last 30 minutes
        
        This prevents spam loops when errors occur repeatedly.
        """
        if self._last_error_alert_time is None:
            return True
        
        cooldown = timedelta(minutes=self.ERROR_ALERT_COOLDOWN_MINUTES)
        time_since_last = datetime.now(timezone.utc) - self._last_error_alert_time
        
        if time_since_last >= cooldown:
            return True
        
        remaining = cooldown - time_since_last
        logger.debug(f"⏳ Error alert suppressed. Cooldown: {remaining.seconds // 60}m remaining")
        return False
    
    def mark_error_alert_sent(self):
        """Mark that an error alert was just sent."""
        self._last_error_alert_time = datetime.now(timezone.utc)
        suppressed_count = self._error_count_since_last_alert - 1
        self._error_count_since_last_alert = 0
        
        if suppressed_count > 0:
            logger.info(f"📤 Error alert sent ({suppressed_count} similar errors were suppressed)")
    
    def should_send_heartbeat(self) -> bool:
        """
        Check if it's time to send a heartbeat report.
        
        Returns True every 4 hours.
        """
        if self._last_heartbeat_time is None:
            return True
        
        interval = timedelta(hours=self.HEARTBEAT_INTERVAL_HOURS)
        time_since_last = datetime.now(timezone.utc) - self._last_heartbeat_time
        
        return time_since_last >= interval
    
    def mark_heartbeat_sent(self):
        """Mark that a heartbeat was just sent."""
        self._last_heartbeat_time = datetime.now(timezone.utc)
        logger.info("💓 Heartbeat sent")
    
    def get_heartbeat_message(self, api_quota: Optional[Dict] = None) -> str:
        """
        Generate heartbeat status message.
        
        Args:
            api_quota: Optional dict with 'remaining' and 'used' keys
            
        Returns:
            Formatted status message
        """
        lines = [
            "💓 <b>EARLYBIRD HEARTBEAT</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"⏱️ Uptime: <b>{self.uptime_str}</b>",
            f"🔄 Scans: <b>{self.stats.total_scans}</b>",
            f"📤 Alerts Sent: <b>{self.stats.total_alerts_sent}</b>",
            f"⚽ Matches Processed: <b>{self.stats.matches_processed}</b>",
            f"📰 News Analyzed: <b>{self.stats.news_items_analyzed}</b>",
        ]
        
        # Add error info if any
        if self.stats.total_errors > 0:
            lines.append(f"❌ Errors: <b>{self.stats.total_errors}</b>")
        
        # Add API quota if available
        if api_quota:
            remaining = api_quota.get('remaining', 'N/A')
            used = api_quota.get('used', 'N/A')
            lines.append(f"💰 API Quota: <b>{remaining}</b> remaining ({used} used)")
        
        # Add last scan time
        if self.stats.last_scan_time:
            time_ago = datetime.now(timezone.utc) - self.stats.last_scan_time
            minutes_ago = time_ago.seconds // 60
            lines.append(f"🕐 Last Scan: <b>{minutes_ago}m ago</b>")
        
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
            f"🔄 Scans completed: {self.stats.total_scans}",
            f"❌ Total errors: {self.stats.total_errors}",
            suppressed_text,
            "━━━━━━━━━━━━━━━━━━━━",
            "🔄 System will attempt restart...",
        ]
        
        return "\n".join(line for line in lines if line)
    
    def get_stats_dict(self) -> Dict:
        """Get stats as dictionary for API/logging."""
        return {
            "uptime": self.uptime_str,
            "total_scans": self.stats.total_scans,
            "total_alerts_sent": self.stats.total_alerts_sent,
            "total_errors": self.stats.total_errors,
            "matches_processed": self.stats.matches_processed,
            "news_items_analyzed": self.stats.news_items_analyzed,
            "last_scan": self.stats.last_scan_time.isoformat() if self.stats.last_scan_time else None,
            "last_error": self.stats.last_error_message if self.stats.last_error_time else None,
        }

    # ============================================
    # V3.7: SELF-DIAGNOSIS AGENT
    # ============================================
    
    def run_diagnostics(self) -> List[Tuple[str, str, str]]:
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
        try:
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            if disk_percent > 90:
                issues.append((
                    "disk_full",
                    SEVERITY_ERROR,
                    f"⚠️ Disco in esaurimento: {disk_percent:.1f}% utilizzato"
                ))
                logger.warning(f"🔴 DISK CRITICAL: {disk_percent:.1f}% used")
            elif disk_percent > 80:
                logger.info(f"🟡 Disk usage: {disk_percent:.1f}%")
            else:
                logger.debug(f"🟢 Disk usage: {disk_percent:.1f}%")
        except Exception as e:
            issues.append((
                "disk_check_failed",
                SEVERITY_WARNING,
                f"⚠️ Impossibile verificare disco: {str(e)[:100]}"
            ))
            logger.error(f"Disk check failed: {e}")
        
        # --- 2. DATABASE: Connection Check ---
        try:
            from sqlalchemy import text
            from src.database.models import SessionLocal
            db = SessionLocal()
            try:
                # Simple query to verify connection
                result = db.execute(text("SELECT 1")).fetchone()
                if result and result[0] == 1:
                    logger.debug("🟢 Database connection OK")
                else:
                    raise Exception("Unexpected query result")
            finally:
                db.close()
        except Exception as e:
            issues.append((
                "database_error",
                SEVERITY_CRITICAL,
                f"🚨 Database non raggiungibile: {str(e)[:100]}"
            ))
            logger.error(f"🔴 DATABASE CRITICAL: {e}")
        
        # --- 3. APIs: Odds API Check ---
        try:
            odds_api_key = os.getenv("ODDS_API_KEY")
            if odds_api_key:
                # Quick check - just verify API key is valid (use sports endpoint)
                url = f"https://api.the-odds-api.com/v4/sports/?apiKey={odds_api_key}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 401:
                    issues.append((
                        "odds_api_auth",
                        SEVERITY_WARNING,
                        "⚠️ API Quote Errore: Chiave API non valida (401)"
                    ))
                    logger.warning("🟡 Odds API: Invalid API key (401)")
                elif response.status_code == 403:
                    issues.append((
                        "odds_api_forbidden",
                        SEVERITY_WARNING,
                        "⚠️ API Quote Errore: Accesso negato (403)"
                    ))
                    logger.warning("🟡 Odds API: Forbidden (403)")
                elif response.status_code == 429:
                    issues.append((
                        "odds_api_quota",
                        SEVERITY_WARNING,
                        "⚠️ API Quote Errore: Quota esaurita (429)"
                    ))
                    logger.warning("🟡 Odds API: Rate limited (429)")
                elif response.status_code != 200:
                    logger.warning(f"🟡 Odds API: Unexpected status {response.status_code}")
                else:
                    logger.debug("🟢 Odds API connection OK")
            else:
                logger.debug("⚪ Odds API key not configured - skipping check")
        except requests.exceptions.Timeout:
            issues.append((
                "odds_api_timeout",
                SEVERITY_WARNING,
                "⚠️ API Quote Errore: Timeout connessione"
            ))
            logger.warning("🟡 Odds API: Connection timeout")
        except requests.exceptions.ConnectionError as e:
            issues.append((
                "odds_api_connection",
                SEVERITY_WARNING,
                f"⚠️ API Quote Errore: Connessione fallita"
            ))
            logger.warning(f"🟡 Odds API: Connection error - {e}")
        except Exception as e:
            logger.error(f"Odds API check failed: {e}")
        

        
        return issues
    
    def report_issues(self, issues: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """
        Filtra issues già segnalati nelle ultime 6 ore e invia alert per i nuovi.
        
        Args:
            issues: Lista di tuple (issue_key, severity, message_it)
            
        Returns:
            Lista di issues nuovi (non in cooldown)
        """
        if not issues:
            return []
        
        now = datetime.now(timezone.utc)
        cooldown = timedelta(hours=ISSUE_COOLDOWN_HOURS)
        new_issues = []
        
        for issue_key, severity, message in issues:
            last_alert = self.last_alerts.get(issue_key)
            
            # Check cooldown
            if last_alert and (now - last_alert) < cooldown:
                hours_ago = (now - last_alert).total_seconds() / 3600
                logger.debug(f"⏳ Issue '{issue_key}' in cooldown ({hours_ago:.1f}h ago)")
                continue
            
            # New issue - add to list and update timestamp
            new_issues.append((issue_key, severity, message))
            self.last_alerts[issue_key] = now
            logger.info(f"🆕 New issue detected: {issue_key} ({severity})")
        
        # Send alert if there are new issues
        if new_issues:
            self._send_diagnostic_alert(new_issues)
        
        return new_issues
    
    def _send_diagnostic_alert(self, issues: List[Tuple[str, str, str]]):
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
                    SEVERITY_WARNING: "🟡"
                }.get(severity, "⚪")
                lines.append(f"{severity_emoji} {message}")
            
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"⏱️ Uptime: {self.uptime_str}")
            
            message = "\n".join(lines)
            send_status_message(message)
            
            logger.info(f"📤 Diagnostic alert sent ({len(issues)} issues)")
        except Exception as e:
            logger.error(f"Failed to send diagnostic alert: {e}")


# Singleton instance
_monitor_instance: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get singleton instance of HealthMonitor."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = HealthMonitor()
    return _monitor_instance
