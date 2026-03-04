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
from typing import Any

import psutil

# Import centralized version tracking
from src.version import get_version_with_module

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
LOCK_CONTENTION_METRICS_INTERVAL = 300  # 5 minutes

# Alert thresholds (configurable via environment variables)
CPU_THRESHOLD = float(os.getenv("METRICS_CPU_THRESHOLD", "80.0"))
MEMORY_THRESHOLD = float(os.getenv("METRICS_MEMORY_THRESHOLD", "85.0"))
DISK_THRESHOLD = float(os.getenv("METRICS_DISK_THRESHOLD", "90.0"))


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
    errors_by_type: dict[str, int] = field(default_factory=dict)


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
        self._restart_count = 0

        # Metrics cache for performance optimization
        self._system_metrics_cache: SystemMetrics | None = None
        self._orchestration_metrics_cache: OrchestrationMetrics | None = None
        self._business_metrics_cache: BusinessMetrics | None = None

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize the metrics database table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

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

            # Create news_log table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    summary TEXT,
                    sent BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()

            logger.info(f"✅ Metrics database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize metrics database: {e}")

    def start(self):
        """Start the metrics collector."""
        if self._running:
            logger.warning("⚠️ Metrics collector already running")
            return

        self._running = True
        self._restart_count += 1
        self._process_start_time = time.time()

        # Start metrics collection thread
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()

        logger.info("✅ Orchestration metrics collector started")

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

            # Collect lock contention metrics every 5 minutes
            if now - last_lock_contention_collection >= LOCK_CONTENTION_METRICS_INTERVAL:
                try:
                    metrics = self._collect_lock_contention_metrics()
                    self._store_metrics("lock_contention", metrics)
                    last_lock_contention_collection = now
                except Exception as e:
                    logger.error(f"❌ Failed to collect lock contention metrics: {e}")

            # Sleep for 1 second before next check
            time.sleep(1)

    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system-level metrics."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Disk
        disk = psutil.disk_usage("/")
        disk_percent = disk.percent

        # Network
        network = psutil.net_io_counters()
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
        """Get the number of active leagues."""
        try:
            from src.processing.global_orchestrator import get_global_orchestrator

            orchestrator = get_global_orchestrator()
            result = orchestrator.get_all_active_leagues()

            return len(result.get("leagues", []))
        except Exception as e:
            logger.error(f"❌ Failed to get active leagues count: {e}")
            return 0

    def _get_matches_in_analysis_count(self) -> int:
        """Get the number of matches currently in analysis."""
        try:
            conn = sqlite3.connect(self.db_path)
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
            conn.close()

            return count
        except Exception as e:
            logger.error(f"❌ Failed to get matches in analysis count: {e}")
            return 0

    def _get_alerts_count(self, hours: int) -> int:
        """Get the number of alerts sent in the last N hours."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Count alerts sent in the last N hours
            cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            cursor.execute(
                """
                SELECT COUNT(*) FROM news_log
                WHERE sent = 1 AND created_at > ?
            """,
                (cutoff_time,),
            )

            count = cursor.fetchone()[0]
            conn.close()

            return count
        except Exception as e:
            logger.error(f"❌ Failed to get alerts count: {e}")
            return 0

    def _get_matches_analyzed_count(self, hours: int) -> int:
        """Get the number of matches analyzed in the last N hours."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Count matches analyzed in the last N hours
            cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            cursor.execute(
                """
                SELECT COUNT(*) FROM news_log
                WHERE created_at > ?
            """,
                (cutoff_time,),
            )

            count = cursor.fetchone()[0]
            conn.close()

            return count
        except Exception as e:
            logger.error(f"❌ Failed to get matches analyzed count: {e}")
            return 0

    def _get_errors_by_type(self) -> dict[str, int]:
        """Get errors by type from logs."""
        # This is a simplified implementation
        # In a real scenario, we would parse log files
        return {
            "database_errors": 0,
            "api_errors": 0,
            "analysis_errors": 0,
            "notification_errors": 0,
        }

    def _collect_lock_contention_metrics(self) -> LockContentionMetrics:
        """Collect lock contention metrics from cache components."""
        try:
            # Get SupabaseProvider lock stats
            from src.database.supabase_provider import get_supabase

            supabase = get_supabase()
            supabase_stats = supabase.get_cache_lock_stats()

            # Get RefereeCache lock stats
            from src.analysis.referee_cache import get_referee_cache

            referee_cache = get_referee_cache()
            referee_stats = referee_cache.get_lock_stats()

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
        except Exception as e:
            logger.error(f"❌ Failed to collect lock contention metrics: {e}")
            # Return empty metrics on error
            return LockContentionMetrics(
                timestamp=datetime.now(timezone.utc),
                supabase_cache_wait_count=0,
                supabase_cache_wait_time_total=0.0,
                supabase_cache_wait_time_avg=0.0,
                supabase_cache_timeout_count=0,
                referee_cache_wait_count=0,
                referee_cache_wait_time_total=0.0,
                referee_cache_wait_time_avg=0.0,
                referee_cache_timeout_count=0,
            )

    def _store_metrics(self, metric_type: str, metrics: Any):
        """Store metrics in the database (thread-safe)."""
        with self._lock:
            try:
                import json

                conn = sqlite3.connect(self.db_path)
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
                conn.close()

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
            f"❌ [ORCHESTRATION-METRICS] Cache corruption recorded: "
            f"{cache_name} - {error}"
        )



    def _check_system_alerts(self, metrics: SystemMetrics):
        """Check system metrics against thresholds and send alerts."""
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
            for alert in alerts:
                logger.warning(alert)

            # Could integrate with existing notifier here
            # from src.alerting.notifier import send_alert
            # send_alert(...)

    def get_metrics_summary(self) -> str:
        """Get a summary of recent metrics."""
        try:
            import json

            conn = sqlite3.connect(self.db_path)
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
                summary_lines.append(f"   Matches in Analysis: {metrics['matches_in_analysis']}")
                summary_lines.append(f"   Process Restarts: {metrics['process_restart_count']}")
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

            conn.close()

            return "\n".join(summary_lines)
        except Exception as e:
            logger.error(f"❌ Failed to get metrics summary: {e}")
            return "❌ Failed to get metrics summary"


# ============================================
# GLOBAL INSTANCE
# ============================================
_metrics_collector: OrchestrationMetricsCollector | None = None
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
