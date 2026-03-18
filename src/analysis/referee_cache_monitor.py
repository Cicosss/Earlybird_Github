"""
Referee Cache Monitoring Module

Provides monitoring and metrics for the RefereeCache, including:
- Cache hit rate tracking
- Performance metrics
- Cache health monitoring
- Statistics reporting

Usage:
    from src.analysis.referee_cache_monitor import get_referee_cache_monitor

    monitor = get_referee_cache_monitor()
    monitor.record_hit("Michael Oliver")
    monitor.record_miss("Unknown Referee")

    # Get metrics
    metrics = monitor.get_metrics()
    print(f"Hit rate: {metrics['hit_rate']:.2%}")
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Timer
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Metrics file location
METRICS_DIR = Path("data/metrics")
METRICS_FILE = METRICS_DIR / "referee_cache_metrics.json"


class RefereeCacheMonitor:
    """
    Monitor for RefereeCache operations.

    Tracks cache hits, misses, and provides metrics for monitoring.
    Thread-safe for concurrent access.
    """

    def __init__(self, metrics_file: Path = METRICS_FILE, flush_interval: float = 30.0):
        self.metrics_file = metrics_file
        self._lock = Lock()
        self._metrics = self._load_metrics()
        self._dirty = False  # Track if metrics have been modified
        self._flush_interval = flush_interval  # Seconds between automatic flushes
        self._flush_timer = None
        self._shutdown_event = Event()
        self._start_flush_timer()

    def _load_metrics(self) -> Dict[str, Any]:
        """Load metrics from file."""
        if not self.metrics_file.exists():
            return self._create_empty_metrics()

        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(
                f"❌ [REFEREE-CACHE-MONITOR] Failed to load cache metrics from {self.metrics_file}: {e}\n"
                f"Stack trace:\n{traceback.format_exc()}"
            )
            return self._create_empty_metrics()

    def _create_empty_metrics(self) -> Dict[str, Any]:
        """Create empty metrics structure."""
        return {
            "hits": 0,
            "misses": 0,
            "total_requests": 0,
            "hit_rate": 0.0,
            "last_updated": None,
            "referee_stats": {},
            "boost_usage": {},  # Track referee data usage for boost calculations
            "performance": {
                "avg_hit_time_ms": 0.0,
                "avg_miss_time_ms": 0.0,
                "total_hit_time_ms": 0.0,
                "total_miss_time_ms": 0.0,
            },
        }

    def _save_metrics(self):
        """Save metrics to file (called outside lock to reduce contention)."""
        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(self._metrics, f, indent=2, ensure_ascii=False)
            logger.debug(f"Metrics saved to {self.metrics_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache metrics: {e}")

    def _flush_metrics(self):
        """Flush metrics to disk if dirty."""
        if not self._dirty:
            return

        # Copy metrics outside lock to minimize lock time
        with self._lock:
            if not self._dirty:
                return
            metrics_copy = self._metrics.copy()
            self._dirty = False

        # Perform I/O outside lock
        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(metrics_copy, f, indent=2, ensure_ascii=False)
            logger.debug(f"Metrics flushed to {self.metrics_file}")
        except Exception as e:
            logger.warning(f"Failed to flush cache metrics: {e}")
            # Mark as dirty again if save failed
            with self._lock:
                self._dirty = True

    def _schedule_flush(self):
        """Schedule next flush if not shutting down."""
        if self._shutdown_event.is_set():
            return

        self._flush_timer = Timer(self._flush_interval, self._flush_metrics)
        self._flush_timer.daemon = True  # Don't prevent program shutdown
        self._flush_timer.start()

    def _start_flush_timer(self):
        """Start the periodic flush timer."""
        self._schedule_flush()

    def flush(self):
        """Force immediate flush of metrics to disk."""
        self._flush_metrics()

    def shutdown(self):
        """Shutdown monitor and flush metrics."""
        self._shutdown_event.set()
        if self._flush_timer:
            self._flush_timer.cancel()
        self.flush()
        logger.info("RefereeCacheMonitor shutdown complete")

    def record_hit(self, referee_name: str, hit_time_ms: Optional[float] = None):
        """
        Record a cache hit.

        Args:
            referee_name: Name of the referee
            hit_time_ms: Time taken for cache hit in milliseconds (optional)
        """
        with self._lock:
            self._metrics["hits"] += 1
            self._metrics["total_requests"] += 1
            self._metrics["hit_rate"] = self._calculate_hit_rate()
            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Track per-referee stats
            if referee_name not in self._metrics["referee_stats"]:
                self._metrics["referee_stats"][referee_name] = {
                    "hits": 0,
                    "misses": 0,
                    "last_accessed": None,
                }

            self._metrics["referee_stats"][referee_name]["hits"] += 1
            self._metrics["referee_stats"][referee_name]["last_accessed"] = datetime.now(
                timezone.utc
            ).isoformat()

            # Track performance
            if hit_time_ms is not None:
                self._metrics["performance"]["total_hit_time_ms"] += hit_time_ms
                self._metrics["performance"]["avg_hit_time_ms"] = (
                    self._metrics["performance"]["total_hit_time_ms"] / self._metrics["hits"]
                )

            self._dirty = True
            logger.debug(f"Cache hit recorded for referee: {referee_name}")

    def record_miss(self, referee_name: str, miss_time_ms: Optional[float] = None):
        """
        Record a cache miss.

        Args:
            referee_name: Name of the referee
            miss_time_ms: Time taken for cache miss in milliseconds (optional)
        """
        with self._lock:
            self._metrics["misses"] += 1
            self._metrics["total_requests"] += 1
            self._metrics["hit_rate"] = self._calculate_hit_rate()
            self._metrics["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Track per-referee stats
            if referee_name not in self._metrics["referee_stats"]:
                self._metrics["referee_stats"][referee_name] = {
                    "hits": 0,
                    "misses": 0,
                    "last_accessed": None,
                }

            self._metrics["referee_stats"][referee_name]["misses"] += 1
            self._metrics["referee_stats"][referee_name]["last_accessed"] = datetime.now(
                timezone.utc
            ).isoformat()

            # Track performance
            if miss_time_ms is not None:
                self._metrics["performance"]["total_miss_time_ms"] += miss_time_ms
                self._metrics["performance"]["avg_miss_time_ms"] = (
                    self._metrics["performance"]["total_miss_time_ms"] / self._metrics["misses"]
                )

            self._dirty = True
            logger.debug(f"Cache miss recorded for referee: {referee_name}")

    def record_boost_usage(self, referee_name: str):
        """
        Record that referee data was used for boost calculation.

        This is separate from cache hit tracking because:
        1. Cache hit tracking measures cache effectiveness
        2. Boost usage tracking measures how often referee data influences decisions

        Args:
            referee_name: Name of the referee whose data was used
        """
        with self._lock:
            # Initialize boost_usage tracking if not present
            if "boost_usage" not in self._metrics:
                self._metrics["boost_usage"] = {}

            # Track per-referee boost usage
            if referee_name not in self._metrics["boost_usage"]:
                self._metrics["boost_usage"][referee_name] = 0

            self._metrics["boost_usage"][referee_name] += 1
            self._dirty = True
            logger.debug(f"Boost usage recorded for referee: {referee_name}")

    def _calculate_hit_rate(self) -> float:
        """Calculate current hit rate."""
        if self._metrics["total_requests"] == 0:
            return 0.0
        return self._metrics["hits"] / self._metrics["total_requests"]

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current cache metrics.

        Returns:
            Dict with cache metrics including hit rate, hits, misses, etc.
        """
        with self._lock:
            return self._metrics.copy()

    def get_hit_rate(self) -> float:
        """
        Get current cache hit rate.

        Returns:
            Hit rate as a float between 0.0 and 1.0
        """
        with self._lock:
            return self._metrics["hit_rate"]

    def get_referee_stats(self, referee_name: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific referee.

        Args:
            referee_name: Name of the referee

        Returns:
            Dict with referee-specific stats or None if not found
        """
        with self._lock:
            return self._metrics["referee_stats"].get(referee_name)

    def get_top_referees(self, limit: int = 10) -> List[Tuple[str, int]]:
        """
        Get top referees by access count.

        Args:
            limit: Maximum number of referees to return

        Returns:
            List of tuples (referee_name, total_accesses)
        """
        with self._lock:
            referee_accesses = [
                (name, stats["hits"] + stats["misses"])
                for name, stats in self._metrics["referee_stats"].items()
            ]
            return sorted(referee_accesses, key=lambda x: x[1], reverse=True)[:limit]

    def reset_metrics(self):
        """Reset all metrics to zero."""
        with self._lock:
            self._metrics = self._create_empty_metrics()
            self._dirty = True
            logger.info("Cache metrics reset")

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary.

        Returns:
            Dict with performance metrics
        """
        with self._lock:
            return {
                "avg_hit_time_ms": self._metrics["performance"]["avg_hit_time_ms"],
                "avg_miss_time_ms": self._metrics["performance"]["avg_miss_time_ms"],
                "total_hits": self._metrics["hits"],
                "total_misses": self._metrics["misses"],
                "hit_rate": self._metrics["hit_rate"],
            }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get cache health status.

        Returns:
            Dict with health indicators
        """
        with self._lock:
            hit_rate = self._metrics["hit_rate"]
            total_requests = self._metrics["total_requests"]

            # Determine health status
            if total_requests == 0:
                health = "unknown"
                message = "No requests yet"
            elif hit_rate >= 0.8:
                health = "excellent"
                message = f"High hit rate ({hit_rate:.1%})"
            elif hit_rate >= 0.6:
                health = "good"
                message = f"Good hit rate ({hit_rate:.1%})"
            elif hit_rate >= 0.4:
                health = "fair"
                message = f"Moderate hit rate ({hit_rate:.1%})"
            else:
                health = "poor"
                message = f"Low hit rate ({hit_rate:.1%})"

            return {
                "health": health,
                "message": message,
                "hit_rate": hit_rate,
                "total_requests": total_requests,
                "last_updated": self._metrics["last_updated"],
            }

    def print_metrics(self):
        """Print current metrics to console."""
        metrics = self.get_metrics()
        health = self.get_health_status()

        print("\n" + "=" * 60)
        print("REFEREE CACHE METRICS")
        print("=" * 60)
        print(f"Total Requests: {metrics['total_requests']}")
        print(f"Hits: {metrics['hits']}")
        print(f"Misses: {metrics['misses']}")
        print(f"Hit Rate: {metrics['hit_rate']:.2%}")
        print(f"Health: {health['health'].upper()} - {health['message']}")
        print(f"Last Updated: {metrics['last_updated']}")
        print("\nPerformance:")
        print(f"  Avg Hit Time: {metrics['performance']['avg_hit_time_ms']:.2f} ms")
        print(f"  Avg Miss Time: {metrics['performance']['avg_miss_time_ms']:.2f} ms")
        print("\nTop Referees:")
        for referee, count in self.get_top_referees(5):
            print(f"  {referee}: {count} accesses")
        print("=" * 60 + "\n")


# Global monitor instance
_referee_cache_monitor = None
_monitor_lock = Lock()


def get_referee_cache_monitor() -> RefereeCacheMonitor:
    """
    Get the global referee cache monitor instance (thread-safe singleton).

    Returns:
        RefereeCacheMonitor instance
    """
    global _referee_cache_monitor
    if _referee_cache_monitor is None:
        with _monitor_lock:
            # Double-checked locking pattern for thread safety
            if _referee_cache_monitor is None:
                _referee_cache_monitor = RefereeCacheMonitor()
    return _referee_cache_monitor


# Decorator for automatic monitoring
def monitor_cache_access(referee_name_param: str = "referee_name"):
    """
    Decorator to automatically monitor cache access.

    Args:
        referee_name_param: Name of the parameter containing referee name

    Usage:
        @monitor_cache_access("referee_name")
        def get_referee_stats(referee_name: str) -> Optional[RefereeStats]:
            cache = get_referee_cache()
            stats = cache.get(referee_name)

            if stats:
                # Record hit (decorator handles this automatically)
                return stats
            else:
                # Record miss (decorator handles this automatically)
                return None
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_referee_cache_monitor()

            # Extract referee name from arguments
            referee_name = None
            if referee_name_param in kwargs:
                referee_name = kwargs[referee_name_param]
            elif args:
                # Assume first positional argument is referee_name
                referee_name = args[0]

            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000

            # Record hit or miss based on result
            if result is not None:
                monitor.record_hit(referee_name or "unknown", elapsed_ms)
            else:
                monitor.record_miss(referee_name or "unknown", elapsed_ms)

            return result

        return wrapper

    return decorator
