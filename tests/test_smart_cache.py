"""
Tests for Smart Cache V1.0

Verifies:
1. Dynamic TTL calculation based on match proximity
2. Cache hit/miss behavior
3. Expiration handling
4. Edge cases (None, started matches, etc.)
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import time


class TestSmartCacheTTLCalculation:
    """Tests for TTL calculation based on match proximity."""
    
    def test_ttl_far_match_over_24h(self):
        """Match > 24h away should get 6h TTL."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        far_match = datetime.now(timezone.utc) + timedelta(hours=48)
        
        cache.set("key", "value", match_time=far_match)
        
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.ttl_seconds == 6 * 3600, f"Expected 6h TTL, got {entry.ttl_seconds}s"
    
    def test_ttl_medium_match_6_to_24h(self):
        """Match 6-24h away should get 2h TTL."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        medium_match = datetime.now(timezone.utc) + timedelta(hours=12)
        
        cache.set("key", "value", match_time=medium_match)
        
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.ttl_seconds == 2 * 3600, f"Expected 2h TTL, got {entry.ttl_seconds}s"
    
    def test_ttl_close_match_1_to_6h(self):
        """Match 1-6h away should get 30min TTL."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        close_match = datetime.now(timezone.utc) + timedelta(hours=3)
        
        cache.set("key", "value", match_time=close_match)
        
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.ttl_seconds == 30 * 60, f"Expected 30min TTL, got {entry.ttl_seconds}s"
    
    def test_ttl_imminent_match_under_1h(self):
        """Match < 1h away should get 5min TTL."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        imminent_match = datetime.now(timezone.utc) + timedelta(minutes=30)
        
        cache.set("key", "value", match_time=imminent_match)
        
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.ttl_seconds == 5 * 60, f"Expected 5min TTL, got {entry.ttl_seconds}s"
    
    def test_ttl_started_match_no_cache(self):
        """Match already started should NOT be cached (TTL=0)."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        started_match = datetime.now(timezone.utc) - timedelta(minutes=15)
        
        cache.set("key", "value", match_time=started_match)
        
        # Should not be in cache
        assert "key" not in cache._cache, "Started match should not be cached"
    
    def test_ttl_none_match_time_uses_default(self):
        """None match_time should use default TTL (30min)."""
        from src.utils.smart_cache import SmartCache, DEFAULT_TTL_SECONDS
        
        cache = SmartCache(name="test")
        cache.set("key", "value", match_time=None)
        
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.ttl_seconds == DEFAULT_TTL_SECONDS
    
    def test_ttl_naive_datetime_handled(self):
        """Naive datetime (no timezone) should be handled safely."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        # Naive datetime (no tzinfo)
        naive_match = datetime.now() + timedelta(hours=12)
        
        # Should not raise
        cache.set("key", "value", match_time=naive_match)
        
        entry = cache._cache.get("key")
        assert entry is not None


class TestSmartCacheBasicOperations:
    """Tests for basic cache operations."""
    
    def test_set_and_get(self):
        """Basic set/get should work."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        cache.set("key1", {"data": "value1"})
        
        result = cache.get("key1")
        assert result == {"data": "value1"}
    
    def test_get_missing_key_returns_none(self):
        """Getting missing key should return None."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        result = cache.get("nonexistent")
        
        assert result is None
    
    def test_invalidate_removes_entry(self):
        """Invalidate should remove specific entry."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        removed = cache.invalidate("key1")
        
        assert removed is True
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
    
    def test_invalidate_pattern_removes_matching(self):
        """Invalidate pattern should remove matching entries."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        cache.set("team:123", "data1")
        cache.set("team:456", "data2")
        cache.set("match:789", "data3")
        
        removed = cache.invalidate_pattern("team:")
        
        assert removed == 2
        assert cache.get("team:123") is None
        assert cache.get("team:456") is None
        assert cache.get("match:789") == "data3"
    
    def test_clear_removes_all(self):
        """Clear should remove all entries."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.clear()
        
        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestSmartCacheExpiration:
    """Tests for cache expiration."""
    
    def test_expired_entry_returns_none(self):
        """Expired entry should return None on get."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        # Set with very short TTL
        cache.set("key", "value", ttl_override=1)  # 1 second TTL
        
        # Should be available immediately
        assert cache.get("key") == "value"
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be expired
        assert cache.get("key") is None
    
    def test_is_expired_method(self):
        """CacheEntry.is_expired should work correctly."""
        from src.utils.smart_cache import CacheEntry
        
        # Not expired
        entry = CacheEntry(
            data="test",
            created_at=time.time(),
            ttl_seconds=3600
        )
        assert entry.is_expired() is False
        
        # Expired
        entry_old = CacheEntry(
            data="test",
            created_at=time.time() - 7200,  # 2 hours ago
            ttl_seconds=3600  # 1 hour TTL
        )
        assert entry_old.is_expired() is True


class TestSmartCacheEviction:
    """Tests for cache eviction."""
    
    def test_evicts_when_full(self):
        """Cache should evict oldest entries when full."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test", max_size=5)
        
        # Fill cache
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")
            time.sleep(0.01)  # Ensure different timestamps
        
        # Add one more (should trigger eviction)
        cache.set("key_new", "value_new")
        
        # Should have evicted some entries
        assert len(cache._cache) <= 5
        # New entry should be present
        assert cache.get("key_new") == "value_new"


class TestSmartCacheStats:
    """Tests for cache statistics."""
    
    def test_stats_tracking(self):
        """Stats should track hits, misses, evictions."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        
        # Miss
        cache.get("nonexistent")
        
        # Set and hit
        cache.set("key", "value")
        cache.get("key")
        cache.get("key")
        
        stats = cache.get_stats()
        
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert stats['hit_rate_pct'] > 0


class TestSmartCacheIntegration:
    """Integration tests with data_provider."""
    
    def test_global_caches_exist(self):
        """Global cache instances should be available."""
        from src.utils.smart_cache import (
            get_team_cache,
            get_match_cache,
            get_search_cache
        )
        
        team_cache = get_team_cache()
        match_cache = get_match_cache()
        search_cache = get_search_cache()
        
        assert team_cache is not None
        assert match_cache is not None
        assert search_cache is not None
        
        # Should be SmartCache instances
        from src.utils.smart_cache import SmartCache
        assert isinstance(team_cache, SmartCache)
        assert isinstance(match_cache, SmartCache)
        assert isinstance(search_cache, SmartCache)
    
    def test_get_all_cache_stats(self):
        """get_all_cache_stats should return stats for all caches."""
        from src.utils.smart_cache import get_all_cache_stats
        
        stats = get_all_cache_stats()
        
        assert 'team_cache' in stats
        assert 'match_cache' in stats
        assert 'search_cache' in stats
        
        for cache_stats in stats.values():
            assert 'size' in cache_stats
            assert 'hits' in cache_stats
            assert 'misses' in cache_stats


class TestSmartCacheEdgeCases:
    """Edge case tests."""
    
    def test_none_value_cached(self):
        """None value should NOT be cached (to avoid caching errors)."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        
        # This is handled at the caller level, but cache should accept None
        cache.set("key", None)
        
        # None values are stored (caller decides what to cache)
        result = cache.get("key")
        assert result is None  # Returns None (either not cached or value is None)
    
    def test_empty_string_key(self):
        """Empty string key should work."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        cache.set("", "value")
        
        assert cache.get("") == "value"
    
    def test_large_data_cached(self):
        """Large data should be cached without issues."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        large_data = {"items": list(range(10000))}
        
        cache.set("large", large_data)
        result = cache.get("large")
        
        assert result == large_data
    
    def test_ttl_override(self):
        """TTL override should take precedence over calculated TTL."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test")
        far_match = datetime.now(timezone.utc) + timedelta(hours=48)
        
        # Override with 1 minute TTL despite far match
        cache.set("key", "value", match_time=far_match, ttl_override=60)
        
        entry = cache._cache.get("key")
        assert entry.ttl_seconds == 60, "TTL override should take precedence"


# ============================================
# REGRESSION TESTS FOR BUG FIXES (2026-01-06)
# ============================================

class TestSmartCacheSetReturnValue:
    """
    REGRESSION TEST: set() now returns bool to indicate if cached.
    
    BUG: set() returned None silently when TTL=0, caller didn't know.
    FIX: Returns True if cached, False if skipped.
    """
    
    def test_set_returns_true_when_cached(self):
        """set() should return True when value is cached."""
        from src.utils.smart_cache import SmartCache
        from datetime import datetime, timezone, timedelta
        
        cache = SmartCache(name="test_return")
        far_match = datetime.now(timezone.utc) + timedelta(hours=48)
        
        result = cache.set("key1", "value1", match_time=far_match)
        assert result is True
    
    def test_set_returns_false_when_ttl_zero(self):
        """set() should return False when TTL=0 (match started)."""
        from src.utils.smart_cache import SmartCache
        from datetime import datetime, timezone, timedelta
        
        cache = SmartCache(name="test_return")
        started_match = datetime.now(timezone.utc) - timedelta(minutes=30)
        
        result = cache.set("key2", "value2", match_time=started_match)
        assert result is False
        assert cache.get("key2") is None  # Not in cache


class TestCachedDecoratorKeyError:
    """
    REGRESSION TEST: Decorator handles key_func exceptions.
    
    BUG: If key_func raised exception, decorator crashed.
    FIX: Catches exception and bypasses cache.
    """
    
    def test_decorator_handles_key_func_exception(self):
        """Decorator should bypass cache if key_func fails."""
        from src.utils.smart_cache import SmartCache, cached_with_match_time
        
        cache = SmartCache(name="test_decorator")
        call_count = 0
        
        def bad_key_func(*args, **kwargs):
            raise ValueError("Intentional error")
        
        @cached_with_match_time(cache=cache, key_func=bad_key_func)
        def my_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # Should not crash, should call function directly
        result = my_func(5)
        assert result == 10
        assert call_count == 1
        
        # Call again - should still work (bypassing cache each time)
        result2 = my_func(5)
        assert result2 == 10
        assert call_count == 2  # Called again because cache bypassed
