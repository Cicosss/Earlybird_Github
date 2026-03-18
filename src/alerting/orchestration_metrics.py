#!/usr/bin/env python3
"""
EarlyBird Orchestration Metrics Collector (V11.1)

Extended monitoring module for orchestration-specific metrics.
This module extends the existing health_monitor.py with orchestration-specific metrics:
- Active leagues count
- Matches in analysis count
- Alerts sent per hour
- Errors by type
- Process restart count
- Process uptime

Metrics are collected at different frequencies:
- System metrics: every 5 minutes
- Orchestration metrics: every 1 minute
- Business metrics: every 10 minutes

Metrics are stored in the SQLite database for efficient querying.

Author: Lead Architect
Date: 2026-02-23
"""

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psutil

# Import centralized version tracking
from src.version import get_version_with_module

# Import GlobalOrchestrator for active leagues tracking - Issue #2 fix
# Moved from inside _get_active_leagues_count() method to top of file
# to avoid inefficient repeated imports and potential circular import issues
try:
    from src.processing.global_orchestrator import get_global_orchestrator

    _GLOBAL_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    _GLOBAL_ORCHESTRATOR_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ GlobalOrchestrator not available, active leagues count will be 0")

# Import notifier for sending alerts to Telegram - Recommendation #1 fix
# Import is optional and will not fail if notifier is not available
try:
    from src.alerting.notifier import send_status_message

    _NOTIFIER_AVAILABLE = True
except ImportError:
    _NOTIFIER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.debug("Notifier not available, alerts will only be logged")

# Log version on import
logger = logging.getLogger(__name__)
logger.info(f"📦 {get_version_with_module('Orchestration Metrics')}")

# ============================================
# CONFIGURATION
# ============================================
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "earlybird.db",
)
METRICS_TABLE = "orchestration_metrics"

# Collection frequencies (in seconds)
SYSTEM_METRICS_INTERVAL = 300  # 5 minutes
ORCHESTRATION_METRICS_INTERVAL = 60  # 1 minute
BUSINESS_METRICS_INTERVAL = 600  # 10 minutes
LOCK_CONTENTION_METRICS_INTERVAL = 30  # 30 seconds (was 300 - Issue 4 fix)
LOCK_CONTENTION_STATS_RESET_INTERVAL = 3600  # 1 hour - Issue 2 fix
METRICS_RETENTION_DAYS = int(
    os.getenv("METRICS_RETENTION_DAYS", "7")
)  # Keep 7 days of metrics - Issue 2 fix

# Alert thresholds (configurable via environment variables)
CPU_THRESHOLD = float(os.getenv("METRICS_CPU_THRESHOLD", "80.0"))
MEMORY_THRESHOLD = float(os.getenv("METRICS_MEMORY_THRESHOLD", "85.0"))
DISK_THRESHOLD = float(os.getenv("METRICS_DISK_THRESHOLD", "90.0"))

# MEDIUM FIX #5: Disk path for monitoring (configurable via environment variable)
# On some VPS, data might be on /data or /home instead of root filesystem
DISK_MONITOR_PATH = os.getenv("METRICS_DISK_PATH", "/")


# IMPORTANT FIX #3: Validate thresholds are between 0-100
# Invalid thresholds can cause incorrect alerts or no alerts
def _validate_threshold(name: str, value: float, default: float) -> float:
    """Validate threshold is between 0-100, return default if invalid."""
    if value < 0 or value > 100:
        logger.warning(
            f"⚠️ Invalid {name} threshold: {value} (must be 0-100), using default: {default}"
        )
        return default
    return value


CPU_THRESHOLD = _validate_threshold("CPU", CPU_THRESHOLD, 80.0)
MEMORY_THRESHOLD = _validate_threshold("MEMORY", MEMORY_THRESHOLD, 85.0)
DISK_THRESHOLD = _validate_threshold("DISK", DISK_THRESHOLD, 90.0)

# Lock contention alert thresholds (configurable via environment variables) - Issue 1 fix
LOCK_CONTENTION_TIMEOUT_THRESHOLD = int(os.getenv("LOCK_CONTENTION_TIMEOUT_THRESHOLD", "10"))
LOCK_CONTENTION_WAIT_TIME_THRESHOLD = float(
    os.getenv("LOCK_CONTENTION_WAIT_TIME_THRESHOLD", "0.5")
)  # 500ms
LOCK_CONTENTION_ALERT_THROTTLE_MINUTES = int(
    os.getenv("LOCK_CONTENTION_ALERT_THROTTLE_MINUTES", "5")
)  # Don't alert more than once every 5 minutes for same issue


# ============================================
# DATA STRUCTURES
# ============================================
@dataclass
class SystemMetrics:
    """System-level metrics (CPU, memory, disk, network)."""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_sent: int
    network_recv: int


@dataclass
class OrchestrationMetrics:
    """Orchestration-specific metrics."""

    timestamp: datetime
    active_leagues: int
    matches_in_analysis: int
    process_restart_count: int
    process_uptime_seconds: float


@dataclass
class BusinessMetrics:
    """Business-level metrics."""

    timestamp: datetime
    alerts_sent_last_hour: int
    alerts_sent_last_24h: int
    matches_analyzed_last_hour: int
    matches_analyzed_last_24h: int
    errors_by_type: Dict[str, int] = field(default_factory=dict)


@dataclass
class LockContentionMetrics:
    """Lock contention metrics for cache operations."""

    timestamp: datetime
    supabase_cache_wait_count: int
    supabase_cache_wait_time_total: float
    supabase_cache_wait_time_avg: float
    supabase_cache_timeout_count: int
    referee_cache_wait_count: int
    referee_cache_wait_time_total: float
    referee_cache_wait_time_avg: float
    referee_cache_timeout_count: int


# ============================================
# METRICS COLLECTOR
# ============================================
class OrchestrationMetricsCollector:
    """
    Collects and stores orchestration metrics.

    This class extends the existing health_monitor.py with
    orchestration-specific metrics.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

        # Track process start time
        self._process_start_time = time.time()

        # Recommendation #2 fix: Restart count will be loaded from database in _init_database()
        self._restart_count = 0

        # Metrics cache for performance optimization
        self._system_metrics_cache: Optional[SystemMetrics] = None
        self._orchestration_metrics_cache: Optional[OrchestrationMetrics] = None
        self._business_metrics_cache: Optional[BusinessMetrics] = None

        # Lock contention alert throttling - Issue 1 fix
        self._last_alert_time: Dict[str, float] = {}  # Track last alert time for each alert type

        # Lock stats reset tracking - Issue 2 fix
        self._last_lock_stats_reset = time.time()

        # Ensure data directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"📁 Created data directory: {db_dir}")

        # Initialize database (will load restart count from database)
        self._init_database()

    def _init_database(self):
        """Initialize the metrics database table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # IMPORTANT FIX #4: Enable WAL (Write-Ahead Logging) mode for better concurrency
                # WAL mode allows simultaneous readers and writers, which is critical for
                # multi-threaded VPS environments where the metrics collector runs in a
                # separate thread while the main bot accesses the database
                cursor.execute("PRAGMA journal_mode=WAL;")
                logger.info("✅ SQLite WAL mode enabled for better concurrency")

                # Create metrics table if it doesn't exist
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {METRICS_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        metric_type TEXT NOT NULL,
                        metric_data TEXT NOT NULL
                    )
                """)

                # Create index for faster queries
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{METRICS_TABLE}_timestamp
                    ON {METRICS_TABLE}(timestamp)
                """)

                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{METRICS_TABLE}_type
                    ON {METRICS_TABLE}(metric_type)
                """)

                # Create errors table for intelligent error tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS orchestration_errors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        error_type TEXT NOT NULL,
                        error_message TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        severity TEXT DEFAULT 'ERROR',
                        component TEXT,
                        match_id TEXT
                    )
                """)

                # Create index for faster error queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_orchestration_errors_timestamp
                    ON orchestration_errors(timestamp)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_orchestration_errors_type
                    ON orchestration_errors(error_type)
                """)

                # Recommendation #2 fix: Create metadata table for persistent restart count tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS orchestration_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                conn.commit()

            logger.info(f"✅ Metrics database initialized at {self.db_path}")

            # Recommendation #2 fix: Load restart count from database
            self._restart_count = self._load_restart_count_from_db()

            # Clean up old metrics on initialization - Issue 2 fix
            self._cleanup_old_metrics()
        except Exception as e:
            logger.error(f"❌ Failed to initialize metrics database: {e}")

    def start(self):
        """
        Start the metrics collector.

        Recommendation #2 fix: Increments restart count and persists to database
        to track actual process restarts across bot restarts.
        """
        if self._running:
            logger.warning("⚠️ Metrics collector already running")
            return

        self._running = True

        # Recommendation #2 fix: Increment restart count and persist to database
        self._restart_count += 1
        self._save_restart_count_to_db(self._restart_count)

        self._process_start_time = time.time()

        # Start metrics collection thread
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()

        logger.info(
            f"✅ Orchestration metrics collector started (restart count: {self._restart_count})"
        )

    def stop(self):
        """Stop the metrics collector."""
        if not self._running:
            return

        self._running = False

        if self._thread:
            self._thread.join(timeout=5)

        logger.info("✅ Orchestration metrics collector stopped")

    def _collection_loop(self):
        """Main collection loop."""
        last_system_collection = 0
        last_orchestration_collection = 0
        last_business_collection = 0
        last_lock_contention_collection = 0
        last_cleanup = 0

        while self._running:
            now = time.time()

            # Collect system metrics every 5 minutes
            if now - last_system_collection >= SYSTEM_METRICS_INTERVAL:
                try:
                    metrics = self._collect_system_metrics()
                    self._store_metrics("system", metrics)
                    self._check_system_alerts(metrics)
                    last_system_collection = now
                except Exception as e:
                    logger.error(f"❌ Failed to collect system metrics: {e}")

            # Collect orchestration metrics every 1 minute
            if now - last_orchestration_collection >= ORCHESTRATION_METRICS_INTERVAL:
                try:
                    metrics = self._collect_orchestration_metrics()
                    self._store_metrics("orchestration", metrics)
                    last_orchestration_collection = now
                except Exception as e:
                    logger.error(f"❌ Failed to collect orchestration metrics: {e}")

            # Collect business metrics every 10 minutes
            if now - last_business_collection >= BUSINESS_METRICS_INTERVAL:
                try:
                    metrics = self._collect_business_metrics()
                    self._store_metrics("business", metrics)
                    last_business_collection = now
                except Exception as e:
                    logger.error(f"❌ Failed to collect business metrics: {e}")

            # Collect lock contention metrics every 30 seconds (was 5 minutes) - Issue 4 fix
            if now - last_lock_contention_collection >= LOCK_CONTENTION_METRICS_INTERVAL:
                try:
                    metrics = self._collect_lock_contention_metrics()
                    self._store_metrics("lock_contention", metrics)
                    self._check_lock_contention_alerts(metrics)  # Issue 1 fix: Check alerts
                    last_lock_contention_collection = now
                except Exception as e:
                    logger.error(f"❌ Failed to collect lock contention metrics: {e}")

            # Reset lock stats every hour - Issue 2 fix
            if now - self._last_lock_stats_reset >= LOCK_CONTENTION_STATS_RESET_INTERVAL:
                try:
                    self._reset_lock_stats()
                    self._last_lock_stats_reset = now
                except Exception as e:
                    logger.error(f"❌ Failed to reset lock stats: {e}")

            # Clean up old metrics daily - Issue 2 fix
            if now - last_cleanup >= 86400:  # 24 hours
                try:
                    self._cleanup_old_metrics()
                    last_cleanup = now
                except Exception as e:
                    logger.error(f"❌ Failed to cleanup old metrics: {e}")

            # Sleep for 1 second before next check
            time.sleep(1)

    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system-level metrics."""
        # CPU
        # CRITICAL FIX #2: Use interval=None to avoid blocking for 1 second
        # interval=None returns CPU usage since last call without blocking
        cpu_percent = psutil.cpu_percent(interval=None)

        # Memory
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Disk
        # MEDIUM FIX #5: Use configurable disk path instead of hardcoded "/"
        disk = psutil.disk_usage(DISK_MONITOR_PATH)
        disk_percent = disk.percent

        # Network
        network = psutil.net_io_counters()
        # CRITICAL FIX #1: psutil.net_io_counters() can return None on containers/restricted systems
        # Use default values of 0 to prevent AttributeError
        if network is None:
            network_sent = 0
            network_recv = 0
            logger.warning(
                "⚠️ psutil.net_io_counters() returned None, using default network values (0)"
            )
        else:
            network_sent = network.bytes_sent
            network_recv = network.bytes_recv

        return SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            network_sent=network_sent,
            network_recv=network_recv,
        )

    def _collect_orchestration_metrics(self) -> OrchestrationMetrics:
        """Collect orchestration-specific metrics."""
        # Get active leagues count
        active_leagues = self._get_active_leagues_count()

        # Get matches in analysis count
        matches_in_analysis = self._get_matches_in_analysis_count()

        # Calculate process uptime
        uptime_seconds = time.time() - self._process_start_time

        return OrchestrationMetrics(
            timestamp=datetime.now(timezone.utc),
            active_leagues=active_leagues,
            matches_in_analysis=matches_in_analysis,
            process_restart_count=self._restart_count,
            process_uptime_seconds=uptime_seconds,
        )

    def _collect_business_metrics(self) -> BusinessMetrics:
        """Collect business-level metrics."""
        # Get alerts sent in last hour and 24h
        alerts_last_hour = self._get_alerts_count(hours=1)
        alerts_last_24h = self._get_alerts_count(hours=24)

        # Get matches analyzed in last hour and 24h
        matches_last_hour = self._get_matches_analyzed_count(hours=1)
        matches_last_24h = self._get_matches_analyzed_count(hours=24)

        # Get errors by type
        errors_by_type = self._get_errors_by_type()

        return BusinessMetrics(
            timestamp=datetime.now(timezone.utc),
            alerts_sent_last_hour=alerts_last_hour,
            alerts_sent_last_24h=alerts_last_24h,
            matches_analyzed_last_hour=matches_last_hour,
            matches_analyzed_last_24h=matches_last_24h,
            errors_by_type=errors_by_type,
        )

    def _get_active_leagues_count(self) -> int:
        """
        Get the number of active leagues.

        Issue #1 fix: Added None check to prevent AttributeError if result is None.
        While get_all_active_leagues() should never return None, this provides
        defense-in-depth protection and prevents bot crashes.

        Issue #2 fix: Import moved to top of file to avoid inefficient
        repeated imports and potential circular import issues.
        """
        try:
            if not _GLOBAL_ORCHESTRATOR_AVAILABLE:
                logger.warning("⚠️ GlobalOrchestrator not available, returning 0 active leagues")
                return 0

            orchestrator = get_global_orchestrator()
            if orchestrator is None:
                logger.warning("⚠️ GlobalOrchestrator instance is None, returning 0 active leagues")
                return 0

            result = orchestrator.get_all_active_leagues()

            # Issue #1 fix: Check if result is None before calling .get()
            if result is None:
                logger.warning(
                    "⚠️ get_all_active_leagues() returned None, returning 0 active leagues"
                )
                return 0

            return len(result.get("leagues", []))
        except Exception as e:
            logger.error(f"❌ Failed to get active leagues count: {e}")
            return 0

    def _get_matches_in_analysis_count(self) -> int:
        """Get the number of matches currently in analysis."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Count matches with start_time in the future
                    now = datetime.now(timezone.utc).isoformat()
                    cursor.execute(
                        """
                            SELECT COUNT(*) FROM matches
                            WHERE start_time > ?
                        """,
                        (now,),
                    )

                    count = cursor.fetchone()[0]

                return count
            except Exception as e:
                logger.error(f"❌ Failed to get matches in analysis count: {e}")
                return 0

    def _get_alerts_count(self, hours: int) -> int:
        """Get the number of alerts sent in the last N hours."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Count alerts sent in the last N hours
                    # FIXED: Changed table name from 'news_log' to 'news_logs' (plural)
                    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM news_logs
                        WHERE sent = 1 AND created_at > ?
                    """,
                        (cutoff_time,),
                    )

                    count = cursor.fetchone()[0]

                return count
            except Exception as e:
                logger.error(f"❌ Failed to get alerts count: {e}")
                return 0

    def _get_matches_analyzed_count(self, hours: int) -> int:
        """
        Get the number of matches analyzed in the last N hours.

        FIXED: Uses COUNT(DISTINCT match_id) to correctly count unique matches
        instead of counting all NewsLog entries (which overcounts).
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Count matches analyzed in the last N hours
                    # FIXED: Changed table name from 'news_log' to 'news_logs' (plural)
                    # FIXED: Uses COUNT(DISTINCT match_id) to count unique matches
                    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                    cursor.execute(
                        """
                        SELECT COUNT(DISTINCT match_id) FROM news_logs
                        WHERE created_at > ?
                    """,
                        (cutoff_time,),
                    )

                    count = cursor.fetchone()[0]

                return count
            except Exception as e:
                logger.error(f"❌ Failed to get matches analyzed count: {e}")
                return 0

    def record_error(
        self,
        error_type: str,
        error_message: str,
        severity: str = "ERROR",
        component: Optional[str] = None,
        match_id: Optional[str] = None,
    ):
        """
        Record an error occurrence in the database for intelligent tracking.

        Args:
            error_type: Type of error (database_errors, api_errors, analysis_errors, notification_errors)
            error_message: Error message
            severity: Error severity (ERROR, CRITICAL, WARNING)
            component: Component that generated the error
            match_id: Optional match ID if error is related to a specific match
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Insert error into database
                    cursor.execute(
                        """
                        INSERT INTO orchestration_errors
                        (error_type, error_message, timestamp, severity, component, match_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            error_type,
                            error_message[:500],  # Limit error message length
                            datetime.now(timezone.utc).isoformat(),
                            severity,
                            component,
                            match_id,
                        ),
                    )

                    conn.commit()

                logger.debug(f"📊 Recorded error: {error_type} - {error_message[:100]}")
            except Exception as e:
                logger.error(f"❌ Failed to record error: {e}")

    def _get_errors_by_type(self) -> Dict[str, int]:
        """
        Get errors by type from the database in the last 24 hours.

        Returns:
            Dictionary with error counts by type
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Get error counts from the last 24 hours
                    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

                    cursor.execute(
                        """
                        SELECT error_type, COUNT(*)
                        FROM orchestration_errors
                        WHERE timestamp > ?
                        GROUP BY error_type
                    """,
                        (cutoff_time,),
                    )

                    errors = {}
                    for row in cursor.fetchall():
                        errors[row[0]] = row[1]

                # Ensure all error types are present with default 0
                default_errors = {
                    "database_errors": 0,
                    "api_errors": 0,
                    "analysis_errors": 0,
                    "notification_errors": 0,
                }
                default_errors.update(errors)

                return default_errors
            except Exception as e:
                logger.error(f"❌ Failed to get errors by type: {e}")
                return {
                    "database_errors": 0,
                    "api_errors": 0,
                    "analysis_errors": 0,
                    "notification_errors": 0,
                }

    def _collect_lock_contention_metrics(self) -> LockContentionMetrics:
        """
        Collect lock contention metrics from cache components.

        Issue 3 fix: Granular error handling with specific exceptions and retry logic.
        """
        supabase_stats = {
            "wait_count": 0,
            "wait_time_total": 0.0,
            "wait_time_avg": 0.0,
            "timeout_count": 0,
        }
        referee_stats = {
            "wait_count": 0,
            "wait_time_total": 0.0,
            "wait_time_avg": 0.0,
            "timeout_count": 0,
        }

        # Get SupabaseProvider lock stats with retry logic
        max_retries = 3
        base_delay = 1.0  # seconds

        for attempt in range(max_retries):
            try:
                from src.database.supabase_provider import get_supabase

                supabase = get_supabase()
                supabase_stats = supabase.get_cache_lock_stats()
                break  # Success - exit retry loop
            except ImportError as e:
                logger.error(f"❌ Failed to import SupabaseProvider: {e}")
                break  # Permanent error - no retry
            except AttributeError as e:
                logger.error(f"❌ SupabaseProvider method not available: {e}")
                break  # Permanent error - no retry
            except RuntimeError as e:
                # Transient error - retry with exponential backoff
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"⚠️ Supabase lock stats collection attempt {attempt + 1}/{max_retries} "
                        f"failed. Retrying in {delay}s... Error: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"❌ Failed to get Supabase lock stats after {max_retries} attempts: {e}"
                    )
            except Exception as e:
                logger.error(f"❌ Unexpected error getting Supabase lock stats: {e}")
                break

        # Get RefereeCache lock stats with retry logic
        for attempt in range(max_retries):
            try:
                from src.analysis.referee_cache import get_referee_cache

                referee_cache = get_referee_cache()
                referee_stats = referee_cache.get_lock_stats()
                break  # Success - exit retry loop
            except ImportError as e:
                logger.error(f"❌ Failed to import RefereeCache: {e}")
                break  # Permanent error - no retry
            except AttributeError as e:
                logger.error(f"❌ RefereeCache method not available: {e}")
                break  # Permanent error - no retry
            except RuntimeError as e:
                # Transient error - retry with exponential backoff
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"⚠️ Referee lock stats collection attempt {attempt + 1}/{max_retries} "
                        f"failed. Retrying in {delay}s... Error: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"❌ Failed to get Referee lock stats after {max_retries} attempts: {e}"
                    )
            except Exception as e:
                logger.error(f"❌ Unexpected error getting Referee lock stats: {e}")
                break

        return LockContentionMetrics(
            timestamp=datetime.now(timezone.utc),
            supabase_cache_wait_count=supabase_stats.get("wait_count", 0),
            supabase_cache_wait_time_total=supabase_stats.get("wait_time_total", 0.0),
            supabase_cache_wait_time_avg=supabase_stats.get("wait_time_avg", 0.0),
            supabase_cache_timeout_count=supabase_stats.get("timeout_count", 0),
            referee_cache_wait_count=referee_stats.get("wait_count", 0),
            referee_cache_wait_time_total=referee_stats.get("wait_time_total", 0.0),
            referee_cache_wait_time_avg=referee_stats.get("wait_time_avg", 0.0),
            referee_cache_timeout_count=referee_stats.get("timeout_count", 0),
        )

    def _store_metrics(self, metric_type: str, metrics: Any):
        """Store metrics in the database (thread-safe)."""
        with self._lock:
            try:
                import json

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Serialize metrics to JSON
                    metrics_json = json.dumps(metrics, default=str)

                    # Insert metrics
                    cursor.execute(
                        f"""
                        INSERT INTO {METRICS_TABLE} (timestamp, metric_type, metric_data)
                        VALUES (?, ?, ?)
                    """,
                        (datetime.now(timezone.utc).isoformat(), metric_type, metrics_json),
                    )

                    conn.commit()

                logger.debug(f"📊 Stored {metric_type} metrics")
            except Exception as e:
                logger.error(f"❌ Failed to store metrics: {e}")

    def record_cache_corruption(self, cache_name: str, error: str):
        """
        Record cache corruption event for operator alerting.

        V12.2: Added cache corruption tracking for production observability.

        Args:
            cache_name: Name of the corrupted cache (e.g., "referee_cache", "supabase_cache")
            error: Error message from cache load failure
        """
        corruption_event = {
            "cache_name": cache_name,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._store_metrics("cache_corruption", corruption_event)
        logger.error(
            f"❌ [ORCHESTRATION-METRICS] Cache corruption recorded: {cache_name} - {error}"
        )

    def _check_system_alerts(self, metrics: SystemMetrics):
        """
        Check system metrics against thresholds and send alerts.

        Recommendation #1 fix: Now integrates with notifier to send alerts
        to Telegram in addition to logging. Alerts are only sent if notifier
        is available and configured.
        """
        alerts = []

        if metrics.cpu_percent > CPU_THRESHOLD:
            alerts.append(f"⚠️ HIGH CPU: {metrics.cpu_percent:.1f}% (threshold: {CPU_THRESHOLD}%)")

        if metrics.memory_percent > MEMORY_THRESHOLD:
            alerts.append(
                f"⚠️ HIGH MEMORY: {metrics.memory_percent:.1f}% (threshold: {MEMORY_THRESHOLD}%)"
            )

        if metrics.disk_percent > DISK_THRESHOLD:
            alerts.append(
                f"⚠️ HIGH DISK: {metrics.disk_percent:.1f}% (threshold: {DISK_THRESHOLD}%)"
            )

        # Send alerts if any thresholds exceeded
        if alerts:
            # Log alerts locally
            for alert in alerts:
                logger.warning(alert)

            # Recommendation #1 fix: Send alerts to Telegram if notifier is available
            if _NOTIFIER_AVAILABLE:
                try:
                    # Build formatted message for Telegram
                    message = "🚨 <b>SYSTEM ALERT</b>\n\n"
                    message += "\n".join(alerts)
                    message += (
                        f"\n\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )

                    send_status_message(message)
                    logger.info("📤 System alerts sent to Telegram")
                except Exception as e:
                    logger.error(f"❌ Failed to send system alerts to Telegram: {e}")

    def _check_lock_contention_alerts(self, metrics: LockContentionMetrics):
        """
        Check lock contention metrics against thresholds and send alerts.

        Issue 1 fix: Implements alerting for lock contention metrics with throttling
        to prevent alert fatigue. Also implements automated responses to mitigate
        lock contention issues.
        """
        alerts = []
        automated_actions = []
        now = time.time()

        # Check Supabase cache lock contention
        if metrics.supabase_cache_timeout_count > LOCK_CONTENTION_TIMEOUT_THRESHOLD:
            alert_key = "supabase_timeout"
            if self._should_send_alert(alert_key, now):
                alerts.append(
                    f"⚠️ HIGH SUPABASE CACHE LOCK TIMEOUTS: "
                    f"{metrics.supabase_cache_timeout_count} (threshold: {LOCK_CONTENTION_TIMEOUT_THRESHOLD})"
                )
                self._last_alert_time[alert_key] = now

        if metrics.supabase_cache_wait_time_avg > LOCK_CONTENTION_WAIT_TIME_THRESHOLD:
            alert_key = "supabase_wait_time"
            if self._should_send_alert(alert_key, now):
                alerts.append(
                    f"⚠️ HIGH SUPABASE CACHE LOCK WAIT TIME: "
                    f"{metrics.supabase_cache_wait_time_avg:.3f}s (threshold: {LOCK_CONTENTION_WAIT_TIME_THRESHOLD}s)"
                )
                self._last_alert_time[alert_key] = now

        # Check Referee cache lock contention
        if metrics.referee_cache_timeout_count > LOCK_CONTENTION_TIMEOUT_THRESHOLD:
            alert_key = "referee_timeout"
            if self._should_send_alert(alert_key, now):
                alerts.append(
                    f"⚠️ HIGH REFEREE CACHE LOCK TIMEOUTS: "
                    f"{metrics.referee_cache_timeout_count} (threshold: {LOCK_CONTENTION_TIMEOUT_THRESHOLD})"
                )
                self._last_alert_time[alert_key] = now

        if metrics.referee_cache_wait_time_avg > LOCK_CONTENTION_WAIT_TIME_THRESHOLD:
            alert_key = "referee_wait_time"
            if self._should_send_alert(alert_key, now):
                alerts.append(
                    f"⚠️ HIGH REFEREE CACHE LOCK WAIT TIME: "
                    f"{metrics.referee_cache_wait_time_avg:.3f}s (threshold: {LOCK_CONTENTION_WAIT_TIME_THRESHOLD}s)"
                )
                self._last_alert_time[alert_key] = now

        # Send alerts if any thresholds exceeded
        if alerts:
            # Log alerts locally
            for alert in alerts:
                logger.warning(f"🔒 [LOCK-CONTENTION] {alert}")

            # Recommendation #1 fix: Send alerts to Telegram if notifier is available
            if _NOTIFIER_AVAILABLE:
                try:
                    # Build formatted message for Telegram
                    message = "🚨 <b>LOCK CONTENTION ALERT</b>\n\n"
                    message += "\n".join(alerts)
                    message += (
                        f"\n\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )

                    send_status_message(message)
                    logger.info("📤 Lock contention alerts sent to Telegram")
                except Exception as e:
                    logger.error(f"❌ Failed to send lock contention alerts to Telegram: {e}")

            # Implement automated responses to mitigate lock contention - Issue 8 fix
            automated_actions = self._generate_automated_responses(metrics)
            if automated_actions:
                for action in automated_actions:
                    logger.info(f"🤖 [LOCK-CONTENTION] Automated action: {action}")

    def _should_send_alert(self, alert_key: str, now: float) -> bool:
        """
        Check if an alert should be sent based on throttling rules.

        Args:
            alert_key: Unique identifier for the alert type
            now: Current timestamp

        Returns:
            True if alert should be sent, False if throttled
        """
        if alert_key not in self._last_alert_time:
            return True  # First time alert

        time_since_last_alert = now - self._last_alert_time[alert_key]
        throttle_seconds = LOCK_CONTENTION_ALERT_THROTTLE_MINUTES * 60

        return time_since_last_alert >= throttle_seconds

    def _generate_automated_responses(self, metrics: LockContentionMetrics) -> List[str]:
        """
        Generate automated responses to mitigate lock contention issues.

        Issue 8 fix: The bot is intelligent and should respond to lock contention
        by taking proactive measures to reduce contention.

        Args:
            metrics: Current lock contention metrics

        Returns:
            List of automated actions taken
        """
        actions = []

        # If Supabase cache has high contention, recommend increasing cache TTL
        if (
            metrics.supabase_cache_timeout_count > LOCK_CONTENTION_TIMEOUT_THRESHOLD
            or metrics.supabase_cache_wait_time_avg > LOCK_CONTENTION_WAIT_TIME_THRESHOLD
        ):
            actions.append(
                "Consider increasing SUPABASE_CACHE_TTL_SECONDS to reduce cache lock acquisitions"
            )

        # If Referee cache has high contention, recommend checking cache usage
        if (
            metrics.referee_cache_timeout_count > LOCK_CONTENTION_TIMEOUT_THRESHOLD
            or metrics.referee_cache_wait_time_avg > LOCK_CONTENTION_WAIT_TIME_THRESHOLD
        ):
            actions.append(
                "Consider reviewing RefereeCache usage patterns - high contention may indicate cache misses"
            )

        # Log detailed diagnostics for root cause analysis - Issue 9 fix
        if metrics.supabase_cache_wait_time_avg > 1.0:  # Very high wait time (> 1s)
            logger.warning(
                f"🔍 [LOCK-CONTENTION] DIAGNOSTIC: Supabase cache lock wait time is very high "
                f"({metrics.supabase_cache_wait_time_avg:.3f}s). This may indicate: "
                f"1) Slow I/O on VPS, 2) High concurrent access, 3) Cache lock held for long periods"
            )

        if metrics.referee_cache_wait_time_avg > 1.0:  # Very high wait time (> 1s)
            logger.warning(
                f"🔍 [LOCK-CONTENTION] DIAGNOSTIC: Referee cache lock wait time is very high "
                f"({metrics.referee_cache_wait_time_avg:.3f}s). This may indicate: "
                f"1) Slow I/O on VPS, 2) High concurrent access, 3) Cache lock held for long periods"
            )

        return actions

    def _reset_lock_stats(self):
        """
        Reset lock contention statistics in SupabaseProvider and RefereeCache.

        Issue 2 fix: Periodically reset lock stats to prevent averages from becoming
        meaningless over time. Stats are reset every hour.
        """
        try:
            # Reset SupabaseProvider lock stats
            from src.database.supabase_provider import get_supabase

            supabase = get_supabase()
            if hasattr(supabase, "reset_cache_lock_stats"):
                supabase.reset_cache_lock_stats()
                logger.info("🔄 [LOCK-CONTENTION] Reset SupabaseProvider cache lock stats")
            else:
                logger.warning("⚠️ SupabaseProvider.reset_cache_lock_stats() not available")
        except Exception as e:
            logger.error(f"❌ Failed to reset SupabaseProvider lock stats: {e}")

        try:
            # Reset RefereeCache lock stats
            from src.analysis.referee_cache import get_referee_cache

            referee_cache = get_referee_cache()
            if hasattr(referee_cache, "reset_lock_stats"):
                referee_cache.reset_lock_stats()
                logger.info("🔄 [LOCK-CONTENTION] Reset RefereeCache lock stats")
            else:
                logger.warning("⚠️ RefereeCache.reset_lock_stats() not available")
        except Exception as e:
            logger.error(f"❌ Failed to reset RefereeCache lock stats: {e}")

    def _cleanup_old_metrics(self):
        """
        Clean up old metrics from the database to prevent excessive growth.

        Issue 2 fix: Implements data retention to keep only the last N days of metrics.
        This prevents the database from growing indefinitely with high-frequency collection.
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Calculate cutoff time
                    cutoff_time = (
                        datetime.now(timezone.utc) - timedelta(days=METRICS_RETENTION_DAYS)
                    ).isoformat()

                    # Delete old metrics
                    cursor.execute(
                        f"""
                        DELETE FROM {METRICS_TABLE}
                        WHERE timestamp < ?
                    """,
                        (cutoff_time,),
                    )

                    deleted_count = cursor.rowcount
                    conn.commit()

                if deleted_count > 0:
                    logger.info(
                        f"🗑️ [METRICS-CLEANUP] Deleted {deleted_count} old metrics entries "
                        f"(older than {METRICS_RETENTION_DAYS} days)"
                    )
            except Exception as e:
                logger.error(f"❌ Failed to cleanup old metrics: {e}")

    def _load_restart_count_from_db(self) -> int:
        """
        Load restart count from database.

        Recommendation #2 fix: Loads the persistent restart count from the database
        to track actual process restarts across bot restarts.

        Returns:
            Restart count (0 if not found or error occurs)
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT value FROM orchestration_metadata
                        WHERE key = 'restart_count'
                    """)

                    row = cursor.fetchone()

                if row:
                    restart_count = int(row[0])
                    logger.info(f"📊 Loaded restart count from database: {restart_count}")
                    return restart_count
                else:
                    logger.info("📊 No restart count found in database, starting from 0")
                    return 0
            except Exception as e:
                logger.error(f"❌ Failed to load restart count from database: {e}")
                return 0

    def _save_restart_count_to_db(self, restart_count: int):
        """
        Save restart count to database.

        Recommendation #2 fix: Persists the restart count to the database
        to track actual process restarts across bot restarts.

        Args:
            restart_count: The restart count to save
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO orchestration_metadata (key, value, updated_at)
                        VALUES (?, ?, ?)
                    """,
                        (
                            "restart_count",
                            str(restart_count),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )

                    conn.commit()

                logger.debug(f"📊 Saved restart count to database: {restart_count}")
            except Exception as e:
                logger.error(f"❌ Failed to save restart count to database: {e}")

    def get_metrics_summary(self) -> str:
        """Get a summary of recent metrics."""
        with self._lock:
            try:
                import json

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Get latest metrics of each type
                    summary_lines = ["📊 ORCHESTRATION METRICS SUMMARY", ""]

                    # System metrics
                    cursor.execute(f"""
                        SELECT metric_data FROM {METRICS_TABLE}
                        WHERE metric_type = 'system'
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        metrics = json.loads(row[0])
                        summary_lines.append("🖥️ System Metrics:")
                        summary_lines.append(f"   CPU: {metrics['cpu_percent']:.1f}%")
                        summary_lines.append(f"   Memory: {metrics['memory_percent']:.1f}%")
                        summary_lines.append(f"   Disk: {metrics['disk_percent']:.1f}%")
                        summary_lines.append("")

                    # Orchestration metrics
                    cursor.execute(f"""
                        SELECT metric_data FROM {METRICS_TABLE}
                        WHERE metric_type = 'orchestration'
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        metrics = json.loads(row[0])
                        summary_lines.append("🎯 Orchestration Metrics:")
                        summary_lines.append(f"   Active Leagues: {metrics['active_leagues']}")
                        summary_lines.append(
                            f"   Matches in Analysis: {metrics['matches_in_analysis']}"
                        )
                        summary_lines.append(
                            f"   Process Restarts: {metrics['process_restart_count']}"
                        )
                        summary_lines.append(f"   Uptime: {metrics['process_uptime_seconds']:.0f}s")
                        summary_lines.append("")

                    # Business metrics
                    cursor.execute(f"""
                        SELECT metric_data FROM {METRICS_TABLE}
                        WHERE metric_type = 'business'
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        metrics = json.loads(row[0])
                        summary_lines.append("📈 Business Metrics:")
                        summary_lines.append(f"   Alerts (1h): {metrics['alerts_sent_last_hour']}")
                        summary_lines.append(f"   Alerts (24h): {metrics['alerts_sent_last_24h']}")
                        summary_lines.append(
                            f"   Matches Analyzed (1h): {metrics['matches_analyzed_last_hour']}"
                        )
                        summary_lines.append(
                            f"   Matches Analyzed (24h): {metrics['matches_analyzed_last_24h']}"
                        )

                return "\n".join(summary_lines)
            except Exception as e:
                logger.error(f"❌ Failed to get metrics summary: {e}")
                return "❌ Failed to get metrics summary"


# ============================================
# ERROR TRACKING INTEGRATION
# ============================================
def record_error_intelligent(
    error_type: str,
    error_message: str,
    severity: str = "ERROR",
    component: Optional[str] = None,
    match_id: Optional[str] = None,
):
    """
    Intelligent error recording that integrates with orchestration metrics.

    This function provides a centralized way to record errors across the entire bot.
    It automatically categorizes errors and stores them in the database for tracking.

    Args:
        error_type: Type of error (database_errors, api_errors, analysis_errors, notification_errors)
        error_message: Error message
        severity: Error severity (ERROR, CRITICAL, WARNING)
        component: Component that generated the error
        match_id: Optional match ID if error is related to a specific match
    """
    try:
        collector = get_metrics_collector()
        collector.record_error(error_type, error_message, severity, component, match_id)
    except Exception as e:
        # Don't fail if metrics collector is not available
        logger.debug(f"Failed to record error in metrics: {e}")


# ============================================
# GLOBAL INSTANCE
# ============================================
_metrics_collector: Optional[OrchestrationMetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> OrchestrationMetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector

    with _metrics_lock:
        if _metrics_collector is None:
            _metrics_collector = OrchestrationMetricsCollector()

        return _metrics_collector


def start_metrics_collection():
    """Start the metrics collector."""
    collector = get_metrics_collector()
    collector.start()


def stop_metrics_collection():
    """Stop the metrics collector."""
    collector = get_metrics_collector()
    collector.stop()


if __name__ == "__main__":
    # Test the metrics collector
    collector = OrchestrationMetricsCollector()
    collector.start()

    try:
        # Run for 60 seconds
        time.sleep(60)

        # Print summary
        print(collector.get_metrics_summary())
    finally:
        collector.stop()
