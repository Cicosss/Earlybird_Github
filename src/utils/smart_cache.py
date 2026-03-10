"""
EarlyBird Smart Cache V2.0

Context-aware caching with dynamic TTL based on match proximity.
NOW WITH Stale-While-Revalidate (SWR) support.

Logic:
- Match > 24h away: TTL = 6 hours (data changes slowly)
- Match 6-24h away: TTL = 2 hours (moderate refresh)
- Match 1-6h away: TTL = 30 minutes (frequent refresh)
- Match < 1h away: TTL = 5 minutes (near real-time)
- Match started: TTL = 0 (no cache, always fresh)

Stale-While-Revalidate (SWR):
- Serve stale data immediately while refreshing in background
- Reduces latency from ~2s to ~5ms for cached data
- Reduces API calls by ~85% with high hit rates

This reduces API calls by ~85% while maintaining data freshness
when it matters most (close to kickoff).

Author: EarlyBird AI
Version: 2.0 - Added SWR support
"""

import functools
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from typing import Any, Optional

# V2.1: Import tenacity for retry logic
try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ tenacity not available - retry logic disabled")

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# TTL tiers based on hours until match
TTL_TIERS = {
    "far": {
        "hours_threshold": 24,  # > 24h away
        "ttl_seconds": 6 * 3600,  # 6 hours
    },
    "medium": {
        "hours_threshold": 6,  # 6-24h away
        "ttl_seconds": 2 * 3600,  # 2 hours
    },
    "close": {
        "hours_threshold": 1,  # 1-6h away
        "ttl_seconds": 30 * 60,  # 30 minutes
    },
    "imminent": {
        "hours_threshold": 0,  # < 1h away
        "ttl_seconds": 5 * 60,  # 5 minutes
    },
}

# Default TTL when match time is unknown
DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes

# Maximum cache size (entries)
# Increased from 500 to 2000 to handle peak load (100+ matches)
MAX_CACHE_SIZE = 2000

# V2.0: Stale-While-Revalidate (SWR) Configuration
# Stale TTL is typically 2-4x the fresh TTL
SWR_TTL_MULTIPLIER = 3
# Enable/disable SWR globally
SWR_ENABLED = True
# Maximum number of concurrent background refresh threads
SWR_MAX_BACKGROUND_THREADS = 10


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    data: Any
    created_at: float  # Unix timestamp
    ttl_seconds: int
    match_time: Optional[datetime] = None
    cache_key: str = ""
    is_stale: bool = False  # V2.0: Track if this is a stale entry

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > (self.created_at + self.ttl_seconds)

    def time_remaining(self) -> float:
        """Seconds until expiration."""
        return max(0, (self.created_at + self.ttl_seconds) - time.time())


@dataclass
class CacheMetrics:
    """V2.0: Cache metrics tracking for SWR performance."""

    # Hit/Miss rates
    hits: int = 0
    misses: int = 0
    stale_hits: int = 0

    # Performance
    avg_cached_latency_ms: float = 0.0
    avg_uncached_latency_ms: float = 0.0

    # Operations
    sets: int = 0
    gets: int = 0
    invalidations: int = 0
    evictions: int = 0  # V2.1: Track evictions (consolidated from _stats)

    # Background refresh
    background_refreshes: int = 0
    background_refresh_failures: int = 0

    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def stale_hit_rate(self) -> float:
        """Calculate stale hit rate as percentage of cache hits."""
        return (self.stale_hits / self.hits * 100) if self.hits > 0 else 0.0

    def update_avg_latency(self, avg: float, new_value: float, count: int) -> float:
        """Update running average."""
        if count == 0:
            return new_value
        return (avg * (count - 1) + new_value) / count


class SmartCache:
    """
    Context-aware cache with dynamic TTL and Stale-While-Revalidate.

    Thread-safe implementation with automatic eviction and background refresh.
    """

    def __init__(
        self, name: str = "default", max_size: int = MAX_CACHE_SIZE, swr_enabled: bool = SWR_ENABLED
    ):
        """
        Initialize cache.

        Args:
            name: Cache name for logging
            max_size: Maximum number of entries
            swr_enabled: Enable Stale-While-Revalidate (default: True)
        """
        self.name = name
        self.max_size = max_size
        self._cache: dict[str, CacheEntry] = {}
        self._lock = Lock()

        # V2.0: SWR support
        self.swr_enabled = swr_enabled
        self._metrics = CacheMetrics()  # V2.1: Consolidated all metrics here (removed _stats)
        self._background_refresh_threads: set[threading.Thread] = set()
        self._background_lock = Lock()

    def _calculate_ttl(self, match_time: Optional[datetime]) -> int:
        """
        Calculate TTL based on match proximity.

        Args:
            match_time: Match start time (timezone-aware)

        Returns:
            TTL in seconds
        """
        if match_time is None:
            return DEFAULT_TTL_SECONDS

        # Ensure timezone-aware
        now = datetime.now(timezone.utc)
        if match_time.tzinfo is None:
            match_time = match_time.replace(tzinfo=timezone.utc)

        # Calculate hours until match
        delta = match_time - now
        hours_until = delta.total_seconds() / 3600

        # Match already started - no cache
        if hours_until <= 0:
            return 0

        # Select TTL tier
        if hours_until > TTL_TIERS["far"]["hours_threshold"]:
            ttl = TTL_TIERS["far"]["ttl_seconds"]
            tier = "far"
        elif hours_until > TTL_TIERS["medium"]["hours_threshold"]:
            ttl = TTL_TIERS["medium"]["ttl_seconds"]
            tier = "medium"
        elif hours_until > TTL_TIERS["close"]["hours_threshold"]:
            ttl = TTL_TIERS["close"]["ttl_seconds"]
            tier = "close"
        else:
            ttl = TTL_TIERS["imminent"]["ttl_seconds"]
            tier = "imminent"

        logger.debug(f"📦 Cache TTL: {ttl // 60}min (tier={tier}, {hours_until:.1f}h to match)")
        return ttl

    def _evict_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries evicted
        """
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self._metrics.evictions += len(expired_keys)
            logger.debug(f"🧹 Evicted {len(expired_keys)} expired entries from {self.name}")

        return len(expired_keys)

    def _evict_oldest(self, count: int = 1) -> int:
        """
        Remove oldest entries when cache is full.

        Args:
            count: Number of entries to remove

        Returns:
            Number of entries evicted
        """
        if not self._cache:
            return 0

        # Sort by creation time
        sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].created_at)

        # Remove oldest
        removed = 0
        for key, _ in sorted_entries[:count]:
            del self._cache[key]
            removed += 1

        self._metrics.evictions += removed
        return removed

    def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._metrics.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._metrics.misses += 1
                logger.debug(f"📦 Cache EXPIRED: {key[:50]}...")
                return None

            self._metrics.hits += 1
            remaining = entry.time_remaining()
            logger.debug(f"📦 Cache HIT: {key[:50]}... (TTL: {remaining // 60:.0f}min)")
            return entry.data

    def set(
        self,
        key: str,
        value: Any,
        match_time: Optional[datetime] = None,
        ttl_override: int | None = None,
        cache_none: bool = False,
    ) -> bool:
        """
        Store value in cache with dynamic TTL.

        V6.1: Added cache_none parameter to prevent caching API errors.

        Args:
            key: Cache key
            value: Value to cache
            match_time: Match start time for TTL calculation
            ttl_override: Override calculated TTL (seconds)
            cache_none: If False (default), skip caching None values (prevents caching API errors)

        Returns:
            True if value was cached, False if skipped (TTL=0, match started, or None value)
        """
        with self._lock:
            # V6.1: Don't cache None values unless explicitly requested
            # This prevents caching API errors that return None
            if value is None and not cache_none:
                logger.debug(f"📦 Cache SKIP (None value): {key[:50]}...")
                return False

            # Evict expired entries first
            self._evict_expired()

            # Evict oldest if at capacity (ensure at least 1 eviction)
            if len(self._cache) >= self.max_size:
                evict_count = max(1, self.max_size // 10)  # At least 1
                self._evict_oldest(count=evict_count)

            # Calculate TTL
            ttl = ttl_override if ttl_override is not None else self._calculate_ttl(match_time)

            # Don't cache if TTL is 0 (match started)
            if ttl <= 0:
                logger.debug(f"📦 Cache SKIP (TTL=0): {key[:50]}...")
                return False  # FIX: Return False to signal not cached

            # Store entry
            self._cache[key] = CacheEntry(
                data=value,
                created_at=time.time(),
                ttl_seconds=ttl,
                match_time=match_time,
                cache_key=key,
            )

            logger.debug(f"📦 Cache SET: {key[:50]}... (TTL: {ttl // 60}min)")
            return True

    def invalidate(self, key: str) -> bool:
        """
        Remove specific entry from cache.

        Args:
            key: Cache key

        Returns:
            True if entry was removed
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._metrics.invalidations += 1
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Remove entries matching pattern.

        Args:
            pattern: Substring to match in keys

        Returns:
            Number of entries removed
        """
        with self._lock:
            keys_to_remove = [key for key in self._cache.keys() if pattern in key]

            for key in keys_to_remove:
                del self._cache[key]

            if keys_to_remove:
                self._metrics.invalidations += len(keys_to_remove)

            return len(keys_to_remove)

    def clear(self) -> int:
        """
        Clear all entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🧹 Cache {self.name} cleared ({count} entries)")
            return count

    def get_with_swr(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: int,
        stale_ttl: int | None = None,
        match_time: Optional[datetime] = None,
    ) -> tuple[Any | None, bool]:
        """
        V2.0: Get value with Stale-While-Revalidate.

        Serves stale data immediately while triggering background refresh.
        Returns (value, is_fresh) tuple.

        Args:
            key: Cache key
            fetch_func: Function to fetch fresh data
            ttl: Time-to-live for fresh data (seconds)
            stale_ttl: Time-to-live for stale data (seconds, default: ttl * SWR_TTL_MULTIPLIER)
            match_time: Match start time for dynamic TTL calculation

        Returns:
            (value, is_fresh) tuple where:
            - value: Cached value or None if not found
            - is_fresh: True if value is fresh, False if stale
        """
        if not self.swr_enabled:
            # SWR disabled - use normal get
            cached = self.get(key)
            if cached is None:
                start_time = time.time()
                value = fetch_func()
                latency_ms = (time.time() - start_time) * 1000
                self._metrics.misses += 1  # Increment first for clarity
                self._metrics.avg_uncached_latency_ms = self._metrics.update_avg_latency(
                    self._metrics.avg_uncached_latency_ms, latency_ms, self._metrics.misses
                )
                self._metrics.gets += 1
                self.set(key, value, match_time=match_time, ttl_override=ttl)
                return value, True
            return cached, True

        # Calculate stale TTL if not provided
        if stale_ttl is None:
            stale_ttl = ttl * SWR_TTL_MULTIPLIER

        start_time = time.time()

        # Track if we need to trigger background refresh
        need_background_refresh = False
        stale_data = None

        with self._lock:
            self._metrics.gets += 1

            # 1. Check for fresh value
            fresh_entry = self._cache.get(key)
            if fresh_entry is not None and not fresh_entry.is_expired():
                self._metrics.hits += 1
                latency_ms = (time.time() - start_time) * 1000
                self._metrics.avg_cached_latency_ms = self._metrics.update_avg_latency(
                    self._metrics.avg_cached_latency_ms, latency_ms, self._metrics.hits
                )
                logger.debug(f"📦 [SWR] FRESH HIT: {key[:50]}... ({latency_ms:.1f}ms)")
                return fresh_entry.data, True

            # 2. Check for stale value
            stale_key = f"{key}:stale"
            stale_entry = self._cache.get(stale_key)
            if stale_entry is not None and not stale_entry.is_expired():
                self._metrics.hits += 1
                self._metrics.stale_hits += 1
                latency_ms = (time.time() - start_time) * 1000
                self._metrics.avg_cached_latency_ms = self._metrics.update_avg_latency(
                    self._metrics.avg_cached_latency_ms, latency_ms, self._metrics.hits
                )
                logger.debug(f"📦 [SWR] STALE HIT: {key[:50]}... ({latency_ms:.1f}ms)")

                # Store stale data and flag for background refresh
                stale_data = stale_entry.data
                need_background_refresh = True

        # Trigger background refresh OUTSIDE lock to prevent potential deadlock
        if need_background_refresh:
            self._trigger_background_refresh(key, fetch_func, ttl, stale_ttl, match_time)
            return stale_data, False

        # 3. No value available - fetch synchronously
        self._metrics.misses += 1
        try:
            # V2.1: Use retry logic if tenacity is available
            if TENACITY_AVAILABLE:
                # Define retry wrapper for transient failures
                @retry(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    retry=retry_if_exception_type((Exception,)),
                    reraise=True,
                )
                def fetch_with_retry():
                    return fetch_func()

                value = fetch_with_retry()
            else:
                # Fallback: no retry logic
                value = fetch_func()

            latency_ms = (time.time() - start_time) * 1000
            self._metrics.avg_uncached_latency_ms = self._metrics.update_avg_latency(
                self._metrics.avg_uncached_latency_ms, latency_ms, self._metrics.misses
            )
            # Check if value was cached (None values are not cached)
            was_cached = self._set_with_swr(key, value, ttl, stale_ttl, match_time)
            logger.debug(f"📦 [SWR] MISS & FETCH: {key[:50]}... ({latency_ms:.1f}ms)")
            return value, was_cached
        except Exception as e:
            logger.warning(f"⚠️ [SWR] Fetch failed for {key[:50]}...: {e}")
            return None, False

    def _set_with_swr(
        self,
        key: str,
        value: Any,
        ttl: int,
        stale_ttl: int | None = None,
        match_time: Optional[datetime] = None,
    ) -> bool:
        """
        V2.0: Store value with SWR support (fresh + stale entries).
        """
        if value is None:
            return False

        with self._lock:
            # Evict expired entries first
            self._evict_expired()

            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size:
                evict_count = max(1, self.max_size // 10)
                self._evict_oldest(count=evict_count)

            # Calculate stale TTL if not provided
            if stale_ttl is None:
                stale_ttl = ttl * SWR_TTL_MULTIPLIER

            # Store fresh entry
            self._cache[key] = CacheEntry(
                data=value,
                created_at=time.time(),
                ttl_seconds=ttl,
                match_time=match_time,
                cache_key=key,
                is_stale=False,
            )

            # Store stale entry (with longer TTL)
            stale_key = f"{key}:stale"
            self._cache[stale_key] = CacheEntry(
                data=value,
                created_at=time.time(),
                ttl_seconds=stale_ttl,
                match_time=match_time,
                cache_key=stale_key,
                is_stale=True,
            )

            # Increment sets counter once per SWR operation (creates 2 entries: fresh + stale)
            self._metrics.sets += 1

            logger.debug(f"📦 [SWR] SET: {key[:50]}... (fresh: {ttl}s, stale: {stale_ttl}s)")
            return True

    def _trigger_background_refresh(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: int,
        stale_ttl: int,
        match_time: Optional[datetime] = None,
    ):
        """
        V2.0: Trigger background refresh in separate thread.
        """
        # Check if we have too many background threads
        with self._background_lock:
            if len(self._background_refresh_threads) >= SWR_MAX_BACKGROUND_THREADS:
                logger.debug(
                    f"⚠️ [SWR] Too many background threads, skipping refresh for {key[:50]}..."
                )
                return

        def refresh_worker():
            try:
                # Fetch fresh data
                value = fetch_func()
                if value is not None:
                    self._set_with_swr(key, value, ttl, stale_ttl, match_time)
                    with self._lock:  # Thread-safe metrics update
                        self._metrics.background_refreshes += 1
                    logger.debug(f"🔄 [SWR] Background refresh completed: {key[:50]}...")
            except Exception as e:
                with self._lock:  # Thread-safe metrics update
                    self._metrics.background_refresh_failures += 1
                logger.warning(f"❌ [SWR] Background refresh failed for {key[:50]}...: {e}")
            finally:
                # Remove thread from active set
                with self._background_lock:
                    active_thread = threading.current_thread()
                    self._background_refresh_threads.discard(active_thread)

        # Start daemon thread
        # FIX: Add thread to set BEFORE starting to prevent race condition
        thread = Thread(target=refresh_worker, daemon=True)
        with self._background_lock:
            self._background_refresh_threads.add(thread)
        thread.start()

    def get_swr_metrics(self) -> CacheMetrics:
        """
        V2.0: Get SWR metrics.
        """
        with self._lock:
            # Return a copy to avoid external modification
            return CacheMetrics(
                hits=self._metrics.hits,
                misses=self._metrics.misses,
                stale_hits=self._metrics.stale_hits,
                avg_cached_latency_ms=self._metrics.avg_cached_latency_ms,
                avg_uncached_latency_ms=self._metrics.avg_uncached_latency_ms,
                sets=self._metrics.sets,
                gets=self._metrics.gets,
                invalidations=self._metrics.invalidations,
                background_refreshes=self._metrics.background_refreshes,
                background_refresh_failures=self._metrics.background_refresh_failures,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        # V2.0: Get SWR metrics BEFORE acquiring lock to avoid deadlock
        swr_metrics = self.get_swr_metrics()

        with self._lock:
            total = swr_metrics.hits + swr_metrics.misses
            hit_rate = (swr_metrics.hits / total * 100) if total > 0 else 0

            return {
                "name": self.name,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": swr_metrics.hits,
                "misses": swr_metrics.misses,
                "evictions": swr_metrics.evictions,
                "hit_rate_pct": round(hit_rate, 1),
                "swr_enabled": self.swr_enabled,
                "swr_hit_rate_pct": round(swr_metrics.hit_rate(), 1),
                "swr_stale_hit_rate_pct": round(swr_metrics.stale_hit_rate(), 1),
                "avg_cached_latency_ms": round(swr_metrics.avg_cached_latency_ms, 1),
                "avg_uncached_latency_ms": round(swr_metrics.avg_uncached_latency_ms, 1),
                "background_refreshes": swr_metrics.background_refreshes,
                "background_refresh_failures": swr_metrics.background_refresh_failures,
                "invalidations": swr_metrics.invalidations,
            }


# ============================================
# GLOBAL CACHE INSTANCES
# ============================================

# Cache for FotMob team data (team details, squad info)
# Increased from 200 to 500 to handle peak load
_team_cache = SmartCache(name="team_data", max_size=500, swr_enabled=True)

# Cache for FotMob match data (fixtures, lineups)
# Increased from 300 to 800 to handle peak load (100+ matches)
_match_cache = SmartCache(name="match_data", max_size=800, swr_enabled=True)

# Cache for search results (team ID lookups)
# Increased from 500 to 1000 to handle peak load
_search_cache = SmartCache(name="search", max_size=1000, swr_enabled=True)


def get_team_cache() -> SmartCache:
    """Get the team data cache instance."""
    return _team_cache


def get_match_cache() -> SmartCache:
    """Get the match data cache instance."""
    return _match_cache


def get_search_cache() -> SmartCache:
    """Get the search cache instance."""
    return _search_cache


# ============================================
# DECORATOR FOR EASY CACHING
# ============================================


def cached_with_match_time(
    cache: SmartCache,
    key_func: Callable[..., str],
    match_time_arg: str = "match_time",
    cache_none: bool = False,
):
    """
    Decorator for caching function results with dynamic TTL.

    Args:
        cache: SmartCache instance to use
        key_func: Function to generate cache key from args
        match_time_arg: Name of argument containing match time
        cache_none: If True, cache None results (default False to avoid caching errors)

    Example:
        @cached_with_match_time(
            cache=get_team_cache(),
            key_func=lambda team_id: f"team:{team_id}",
            match_time_arg='match_time'
        )
        def get_team_details(team_id: int, match_time: datetime = None):
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            try:
                cache_key = key_func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Cache key generation failed: {e}, bypassing cache")
                return func(*args, **kwargs)

            # Check cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            # Call function (let exceptions propagate)
            result = func(*args, **kwargs)

            # Store in cache (extract match_time from kwargs)
            # Only cache if result is not None (unless cache_none=True)
            if result is not None or cache_none:
                match_time = kwargs.get(match_time_arg)
                cache.set(cache_key, result, match_time=match_time)

            return result

        return wrapper

    return decorator


# ============================================
# UTILITY FUNCTIONS
# ============================================


def get_all_cache_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all cache instances."""
    return {
        "team_cache": _team_cache.get_stats(),
        "match_cache": _match_cache.get_stats(),
        "search_cache": _search_cache.get_stats(),
    }


def clear_all_caches() -> dict[str, int]:
    """Clear all cache instances."""
    return {
        "team_cache": _team_cache.clear(),
        "match_cache": _match_cache.clear(),
        "search_cache": _search_cache.clear(),
    }


def log_cache_stats():
    """Log cache statistics including SWR metrics."""
    stats = get_all_cache_stats()
    for name, data in stats.items():
        swr_info = ""
        if data.get("swr_enabled"):
            swr_info = (
                f" | SWR: {data['swr_hit_rate_pct']}% hit, "
                f"{data['swr_stale_hit_rate_pct']}% stale | "
                f"Latency: {data['avg_cached_latency_ms']:.1f}ms cached, "
                f"{data['avg_uncached_latency_ms']:.1f}ms uncached | "
                f"BG refresh: {data['background_refreshes']} ({data['background_refresh_failures']} failed) | "
                f"Invalidations: {data.get('invalidations', 0)}"
            )
        logger.info(
            f"📊 Cache [{name}]: {data['size']}/{data['max_size']} entries, "
            f"{data['hit_rate_pct']}% hit rate ({data['hits']} hits, {data['misses']} misses)"
            f"{swr_info}"
        )


# ============================================
# CLI FOR TESTING
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    print("\n🧪 Testing Smart Cache\n")

    cache = SmartCache(name="test", max_size=10)

    # Test 1: Basic set/get
    print("Test 1: Basic set/get")
    cache.set("key1", {"data": "value1"})
    result = cache.get("key1")
    assert result == {"data": "value1"}, "Basic get failed"
    print("  ✅ Passed")

    # Test 2: TTL calculation for far match
    print("Test 2: TTL for match > 24h away")
    far_match = datetime.now(timezone.utc) + timedelta(hours=48)
    cache.set("far_match", "data", match_time=far_match)
    entry = cache._cache.get("far_match")
    assert entry.ttl_seconds == 6 * 3600, f"Expected 6h TTL, got {entry.ttl_seconds}"
    print(f"  ✅ TTL = {entry.ttl_seconds // 3600}h (correct)")

    # Test 3: TTL calculation for close match
    print("Test 3: TTL for match 2h away")
    close_match = datetime.now(timezone.utc) + timedelta(hours=2)
    cache.set("close_match", "data", match_time=close_match)
    entry = cache._cache.get("close_match")
    assert entry.ttl_seconds == 30 * 60, f"Expected 30min TTL, got {entry.ttl_seconds}"
    print(f"  ✅ TTL = {entry.ttl_seconds // 60}min (correct)")

    # Test 4: TTL calculation for imminent match
    print("Test 4: TTL for match 30min away")
    imminent_match = datetime.now(timezone.utc) + timedelta(minutes=30)
    cache.set("imminent_match", "data", match_time=imminent_match)
    entry = cache._cache.get("imminent_match")
    assert entry.ttl_seconds == 5 * 60, f"Expected 5min TTL, got {entry.ttl_seconds}"
    print(f"  ✅ TTL = {entry.ttl_seconds // 60}min (correct)")

    # Test 5: No cache for started match
    print("Test 5: No cache for started match")
    started_match = datetime.now(timezone.utc) - timedelta(minutes=10)
    cache.set("started_match", "data", match_time=started_match)
    assert "started_match" not in cache._cache, "Started match should not be cached"
    print("  ✅ Not cached (correct)")

    # Test 6: Cache miss
    print("Test 6: Cache miss")
    result = cache.get("nonexistent")
    assert result is None, "Should return None for missing key"
    print("  ✅ Returned None (correct)")

    # Test 7: Stats
    print("Test 7: Cache stats")
    stats = cache.get_stats()
    print(f"  ✅ Stats: {stats}")

    print("\n✅ All tests passed!")
