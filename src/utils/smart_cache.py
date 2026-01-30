"""
EarlyBird Smart Cache V1.0

Context-aware caching with dynamic TTL based on match proximity.

Logic:
- Match > 24h away: TTL = 6 hours (data changes slowly)
- Match 6-24h away: TTL = 2 hours (moderate refresh)
- Match 1-6h away: TTL = 30 minutes (frequent refresh)
- Match < 1h away: TTL = 5 minutes (near real-time)
- Match started: TTL = 0 (no cache, always fresh)

This reduces API calls by ~70% while maintaining data freshness
when it matters most (close to kickoff).

Author: EarlyBird AI
"""
import functools
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# TTL tiers based on hours until match
TTL_TIERS = {
    'far': {
        'hours_threshold': 24,      # > 24h away
        'ttl_seconds': 6 * 3600,    # 6 hours
    },
    'medium': {
        'hours_threshold': 6,       # 6-24h away
        'ttl_seconds': 2 * 3600,    # 2 hours
    },
    'close': {
        'hours_threshold': 1,       # 1-6h away
        'ttl_seconds': 30 * 60,     # 30 minutes
    },
    'imminent': {
        'hours_threshold': 0,       # < 1h away
        'ttl_seconds': 5 * 60,      # 5 minutes
    },
}

# Default TTL when match time is unknown
DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes

# Maximum cache size (entries)
MAX_CACHE_SIZE = 500


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    data: Any
    created_at: float  # Unix timestamp
    ttl_seconds: int
    match_time: Optional[datetime] = None
    cache_key: str = ""
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > (self.created_at + self.ttl_seconds)
    
    def time_remaining(self) -> float:
        """Seconds until expiration."""
        return max(0, (self.created_at + self.ttl_seconds) - time.time())


class SmartCache:
    """
    Context-aware cache with dynamic TTL.
    
    Thread-safe implementation with automatic eviction.
    """
    
    def __init__(self, name: str = "default", max_size: int = MAX_CACHE_SIZE):
        """
        Initialize cache.
        
        Args:
            name: Cache name for logging
            max_size: Maximum number of entries
        """
        self.name = name
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
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
        if hours_until > TTL_TIERS['far']['hours_threshold']:
            ttl = TTL_TIERS['far']['ttl_seconds']
            tier = 'far'
        elif hours_until > TTL_TIERS['medium']['hours_threshold']:
            ttl = TTL_TIERS['medium']['ttl_seconds']
            tier = 'medium'
        elif hours_until > TTL_TIERS['close']['hours_threshold']:
            ttl = TTL_TIERS['close']['ttl_seconds']
            tier = 'close'
        else:
            ttl = TTL_TIERS['imminent']['ttl_seconds']
            tier = 'imminent'
        
        logger.debug(f"📦 Cache TTL: {ttl//60}min (tier={tier}, {hours_until:.1f}h to match)")
        return ttl
    
    def _evict_expired(self) -> int:
        """
        Remove expired entries.
        
        Returns:
            Number of entries evicted
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            self._stats['evictions'] += len(expired_keys)
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
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].created_at
        )
        
        # Remove oldest
        removed = 0
        for key, _ in sorted_entries[:count]:
            del self._cache[key]
            removed += 1
        
        self._stats['evictions'] += removed
        return removed
    
    def get(self, key: str) -> Optional[Any]:
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
                self._stats['misses'] += 1
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self._stats['misses'] += 1
                logger.debug(f"📦 Cache EXPIRED: {key[:50]}...")
                return None
            
            self._stats['hits'] += 1
            remaining = entry.time_remaining()
            logger.debug(f"📦 Cache HIT: {key[:50]}... (TTL: {remaining//60:.0f}min)")
            return entry.data
    
    def set(
        self,
        key: str,
        value: Any,
        match_time: Optional[datetime] = None,
        ttl_override: Optional[int] = None,
        cache_none: bool = False
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
                cache_key=key
            )
            
            logger.debug(f"📦 Cache SET: {key[:50]}... (TTL: {ttl//60}min)")
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
            keys_to_remove = [
                key for key in self._cache.keys()
                if pattern in key
            ]
            
            for key in keys_to_remove:
                del self._cache[key]
            
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total * 100) if total > 0 else 0
            
            return {
                'name': self.name,
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'evictions': self._stats['evictions'],
                'hit_rate_pct': round(hit_rate, 1),
            }


# ============================================
# GLOBAL CACHE INSTANCES
# ============================================

# Cache for FotMob team data (team details, squad info)
_team_cache = SmartCache(name="team_data", max_size=200)

# Cache for FotMob match data (fixtures, lineups)
_match_cache = SmartCache(name="match_data", max_size=300)

# Cache for search results (team ID lookups)
_search_cache = SmartCache(name="search", max_size=500)


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
    match_time_arg: str = 'match_time',
    cache_none: bool = False
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

def get_all_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all cache instances."""
    return {
        'team_cache': _team_cache.get_stats(),
        'match_cache': _match_cache.get_stats(),
        'search_cache': _search_cache.get_stats(),
    }


def clear_all_caches() -> Dict[str, int]:
    """Clear all cache instances."""
    return {
        'team_cache': _team_cache.clear(),
        'match_cache': _match_cache.clear(),
        'search_cache': _search_cache.clear(),
    }


def log_cache_stats():
    """Log cache statistics."""
    stats = get_all_cache_stats()
    for name, data in stats.items():
        logger.info(
            f"📊 Cache [{name}]: {data['size']}/{data['max_size']} entries, "
            f"{data['hit_rate_pct']}% hit rate ({data['hits']} hits, {data['misses']} misses)"
        )


# ============================================
# CLI FOR TESTING
# ============================================

if __name__ == "__main__":
    import sys
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
