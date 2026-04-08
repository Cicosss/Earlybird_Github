"""
Referee Statistics Cache

Caches referee statistics to reduce dependency on external providers (Tavily/Perplexity).
Referee statistics change slowly, so a 7-day TTL is appropriate.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache file location
CACHE_DIR = Path("data/cache")
CACHE_FILE = CACHE_DIR / "referee_stats.json"

# TTL: 7 days (referee stats change slowly)
CACHE_TTL_DAYS = 7


class RefereeCache:
    """Cache for referee statistics."""

    def __init__(self, cache_file: Path = CACHE_FILE, ttl_days: int = CACHE_TTL_DAYS):
        self.cache_file = cache_file
        self.ttl_days = ttl_days
        self._lock = threading.RLock()  # RLock allows reentrant locking (same thread can acquire multiple times)
        self._cache = {}

        # V12.1: Lock contention monitoring for production observability
        self._lock_wait_time = 0.0
        self._lock_wait_count = 0
        self._lock_timeout_count = 0

        self._ensure_cache_dir()

    def _acquire_lock_with_monitoring(self):
        """
        Acquire lock with contention monitoring.

        V12.1: Track lock wait times and contention for production observability.
        V12.3: Use adaptive threshold based on cache size and recent performance.
        """
        start_time = time.time()
        self._lock.acquire()
        wait_time = time.time() - start_time

        # Update monitoring metrics
        self._lock_wait_time += wait_time
        self._lock_wait_count += 1

        # V12.3: Calculate adaptive threshold based on cache size and recent performance
        cache_size = len(self._cache)
        recent_avg_wait = (
            self._lock_wait_time / self._lock_wait_count if self._lock_wait_count > 0 else 0.0
        )
        # Adaptive threshold: base 100ms + cache size factor + recent performance factor
        adaptive_threshold = 0.1 + (cache_size * 0.001) + (recent_avg_wait * 0.5)

        # Log warnings for high contention using adaptive threshold
        if wait_time > adaptive_threshold:
            logger.warning(
                f"⚠️ [REFEREE-CACHE] High lock contention detected: "
                f"waited {wait_time:.3f}s (threshold: {adaptive_threshold:.3f}s, "
                f"cache_size: {cache_size}, total waits: {self._lock_wait_count}, "
                f"avg wait: {self._lock_wait_time / self._lock_wait_count:.3f}s)"
            )

        return True

    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> dict:
        """
        Load cache from file (thread-safe).

        V12.2: Added error logging and alert via orchestration_metrics on cache corruption.
        V12.3: Update in-memory cache to ensure consistency.
        """
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                # V12.3: Update in-memory cache for consistency
                self._cache = cache_data
                return cache_data
        except Exception as e:
            logger.error(
                f"❌ [REFEREE-CACHE] Failed to load referee cache: {e}. "
                f"Cache file may be corrupted. Starting with empty cache."
            )
            # V12.2: Alert operators via orchestration metrics
            try:
                from src.alerting.orchestration_metrics import get_metrics_collector

                metrics = get_metrics_collector()
                if metrics:
                    metrics.record_cache_corruption("referee_cache", str(e))
            except Exception:
                pass  # Don't fail if metrics not available
            return {}

    def _save_cache(self, cache: dict):
        """Save cache to file (thread-safe)."""
        with self._lock:
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to save referee cache: {e}")

    def get(self, referee_name: str) -> Optional[dict]:
        """
        Get referee stats from cache.

        Args:
            referee_name: Name of the referee

        Returns:
            Dict with referee stats or None if not found/expired
        """
        # V12.3: Load cache from file outside lock to reduce contention
        cache = self._load_cache()

        # V12.1: Acquire lock with contention monitoring
        self._acquire_lock_with_monitoring()
        try:
            if referee_name not in self._cache:
                return None

            entry = self._cache[referee_name]

            # Check if entry is expired
            cached_at = entry.get("cached_at")
            if not cached_at:
                return None

            # V12.3: Add error handling for datetime parsing
            try:
                cached_date = datetime.fromisoformat(cached_at)
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ [REFEREE-CACHE] Invalid cache timestamp for {referee_name}: {e}")
                return None

            expiry_date = cached_date + timedelta(days=self.ttl_days)

            # Use timezone-aware datetime for comparison
            if datetime.now(timezone.utc) > expiry_date:
                logger.info(f"Referee cache expired for {referee_name}")
                return None

            logger.debug(f"Referee cache hit for {referee_name}")
            return entry.get("stats")
        finally:
            self._lock.release()

    def set(self, referee_name: str, stats: dict):
        """
        Set referee stats in cache (thread-safe).

        Args:
            referee_name: Name of the referee
            stats: Dict with referee stats (cards_per_game, strictness, etc.)
        """
        # V12.1: Acquire lock with contention monitoring
        self._acquire_lock_with_monitoring()
        try:
            cache = self._load_cache()
            cache[referee_name] = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "stats": stats,
                "referee_strictness": stats.get(
                    "strictness", "unknown"
                ),  # Store strictness separately for consistency
            }
            self._save_cache(cache)
            # V12.3: Update in-memory cache to ensure consistency
            self._cache = cache
            logger.info(f"Referee cache updated for {referee_name}")
        finally:
            self._lock.release()

    def clear(self):
        """
        Clear all cache entries (thread-safe).

        V12.3: Added lock acquisition to prevent race conditions.
        """
        # V12.3: Acquire lock with contention monitoring
        self._acquire_lock_with_monitoring()
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            # V12.3: Clear in-memory cache
            self._cache = {}
            logger.info("Referee cache cleared")
        finally:
            self._lock.release()

    def get_stats(self) -> dict:
        """
        Get cache statistics (thread-safe).

        Returns:
            Dict with cache stats (total_entries, expired_entries, etc.)
        """
        # V12.3: Load cache from file outside lock to reduce contention
        cache = self._load_cache()

        # V12.1: Acquire lock with contention monitoring
        self._acquire_lock_with_monitoring()
        try:
            total_entries = len(cache)
            expired_entries = 0

            for entry in cache.values():
                cached_at = entry.get("cached_at")
                if cached_at:
                    # V12.3: Add error handling for datetime parsing
                    try:
                        cached_date = datetime.fromisoformat(cached_at)
                        expiry_date = cached_date + timedelta(days=self.ttl_days)
                        # Use timezone-aware datetime for comparison
                        if datetime.now(timezone.utc) > expiry_date:
                            expired_entries += 1
                    except (ValueError, TypeError):
                        # Invalid timestamp, treat as expired
                        expired_entries += 1

            return {
                "total_entries": total_entries,
                "expired_entries": expired_entries,
                "valid_entries": total_entries - expired_entries,
                "ttl_days": self.ttl_days,
                # V12.1: Lock contention metrics
                "lock_wait_count": self._lock_wait_count,
                "lock_wait_time_total": round(self._lock_wait_time, 3),
                "lock_wait_time_avg": round(self._lock_wait_time / self._lock_wait_count, 3)
                if self._lock_wait_count > 0
                else 0.0,
            }
        finally:
            self._lock.release()

    def get_lock_stats(self) -> dict:
        """
        Get lock contention statistics for monitoring.

        V12.1: Expose lock contention metrics for production observability.

        Returns:
            Dict with lock stats (wait_count, wait_time_avg, etc.)
        """
        return {
            "wait_count": self._lock_wait_count,
            "wait_time_total": round(self._lock_wait_time, 3),
            "wait_time_avg": round(self._lock_wait_time / self._lock_wait_count, 3)
            if self._lock_wait_count > 0
            else 0.0,
            "timeout_count": self._lock_timeout_count,
        }

    def reset_lock_stats(self):
        """
        Reset lock contention statistics.

        Issue 2 fix: Reset lock stats periodically to prevent averages from becoming
        meaningless over time. This method is thread-safe and should be called by
        the metrics collector every hour.

        V12.3: Use consistent lock pattern with monitoring.
        """
        # V12.3: Acquire lock with contention monitoring for consistency
        self._acquire_lock_with_monitoring()
        try:
            self._lock_wait_time = 0.0
            self._lock_wait_count = 0
            self._lock_timeout_count = 0
        finally:
            self._lock.release()


# Global cache instance
_referee_cache = None
_referee_cache_lock = threading.Lock()


def get_referee_cache() -> RefereeCache:
    """
    Get the global referee cache instance (thread-safe singleton).

    Returns:
        RefereeCache instance
    """
    global _referee_cache
    if _referee_cache is None:
        with _referee_cache_lock:
            # Double-checked locking pattern for thread safety
            if _referee_cache is None:
                _referee_cache = RefereeCache()
    return _referee_cache
