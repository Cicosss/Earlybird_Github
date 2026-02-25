"""
Unit Tests for Smart Cache V2.0 - Stale-While-Revalidate (SWR) Functionality

Verifies:
1. SWR fresh hit behavior
2. SWR stale hit behavior with background refresh
3. SWR miss and fetch behavior
4. Background refresh threading
5. SWR metrics tracking
6. SWR with TTL expiration
7. SWR disabled fallback
8. Edge cases and error handling
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock


class TestSWRFreshHit:
    """Tests for SWR fresh cache hits."""

    def test_swr_fresh_hit_returns_cached_value(self):
        """Fresh cache hit should return cached value immediately."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value={"data": "fresh"})

        # First call - miss and fetch
        result, is_fresh = cache.get_with_swr("key1", fetch_func, ttl=3600)
        assert result == {"data": "fresh"}
        assert is_fresh is True
        assert fetch_func.call_count == 1

        # Second call - fresh hit (no fetch)
        result, is_fresh = cache.get_with_swr("key1", fetch_func, ttl=3600)
        assert result == {"data": "fresh"}
        assert is_fresh is True
        assert fetch_func.call_count == 1  # No additional call

    def test_swr_fresh_hit_before_expiration(self):
        """Fresh hit should work before TTL expires."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # Fetch and cache
        cache.get_with_swr("key", fetch_func, ttl=2)  # 2 second TTL

        # Immediate hit should be fresh
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=2)
        assert result == "value"
        assert is_fresh is True
        assert fetch_func.call_count == 1

    def test_swr_fresh_hit_tracks_latency(self):
        """Fresh hits should track cached latency in metrics."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss
        cache.get_with_swr("key", fetch_func, ttl=3600)

        # Second call - fresh hit
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)

        metrics = cache.get_swr_metrics()
        assert metrics.hits == 1
        assert metrics.avg_cached_latency_ms > 0
        assert metrics.avg_cached_latency_ms < 100  # Should be fast


class TestSWRStaleHit:
    """Tests for SWR stale cache hits with background refresh."""

    def test_swr_stale_hit_returns_stale_data(self):
        """Stale cache hit should return stale data immediately."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss and fetch
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for fresh entry to expire
        time.sleep(1.5)

        # Second call - stale hit (should return stale data)
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)
        assert result == "value"
        assert is_fresh is False

    def test_swr_stale_hit_triggers_background_refresh(self):
        """Stale hit should trigger background refresh."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss and fetch
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)
        assert fetch_func.call_count == 1

        # Wait for fresh entry to expire
        time.sleep(1.5)

        # Second call - stale hit (triggers background refresh)
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for background thread to complete
        time.sleep(0.5)

        # Background refresh should have been triggered
        assert fetch_func.call_count >= 2  # Original + background refresh

    def test_swr_stale_entry_expiration(self):
        """Stale entry should expire after stale_ttl."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss and fetch
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=2)

        # Wait for both fresh and stale to expire
        time.sleep(3)

        # Should be a miss now
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=2)
        assert fetch_func.call_count == 2  # Original + new fetch
        assert is_fresh is True  # Fresh from new fetch

    def test_swr_stale_hit_tracks_metrics(self):
        """Stale hits should be tracked in metrics."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for fresh entry to expire
        time.sleep(1.5)

        # Second call - stale hit
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        metrics = cache.get_swr_metrics()
        assert metrics.hits == 1
        assert metrics.stale_hits == 1
        assert metrics.stale_hit_rate() > 0


class TestSWRMiss:
    """Tests for SWR cache misses."""

    def test_swr_miss_fetches_and_caches(self):
        """Cache miss should fetch and cache the value."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="fetched_value")

        # First call - miss
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)

        assert result == "fetched_value"
        assert is_fresh is True
        assert fetch_func.call_count == 1

        # Verify cached
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
        assert result == "fetched_value"
        assert fetch_func.call_count == 1  # No additional fetch

    def test_swr_miss_tracks_uncached_latency(self):
        """Cache miss should track uncached latency in metrics."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)

        def slow_fetch():
            time.sleep(0.1)
            return "slow_value"

        # Call - miss with slow fetch
        cache.get_with_swr("key", slow_fetch, ttl=3600)

        metrics = cache.get_swr_metrics()
        assert metrics.misses == 1
        assert metrics.avg_uncached_latency_ms >= 100  # At least 100ms

    def test_swr_miss_with_fetch_error(self):
        """Cache miss should handle fetch errors gracefully."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(side_effect=Exception("Fetch failed"))

        # Call - miss with error
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)

        assert result is None
        assert is_fresh is False

        metrics = cache.get_swr_metrics()
        assert metrics.misses == 1


class TestSWRBackgroundRefresh:
    """Tests for SWR background refresh threading."""

    def test_swr_background_refresh_updates_cache(self):
        """Background refresh should update cache with fresh data."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_count = {"count": 0}

        def fetch_func():
            fetch_count["count"] += 1
            return f"value_v{fetch_count['count']}"

        # First call - miss and fetch v1
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)
        assert result == "value_v1"
        assert fetch_count["count"] == 1

        # Wait for fresh entry to expire
        time.sleep(1.5)

        # Second call - stale hit, triggers background refresh
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)
        assert result == "value_v1"  # Still stale
        assert is_fresh is False

        # Wait for background refresh to complete
        time.sleep(0.5)

        # Third call - should get fresh v2
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)
        assert result == "value_v2"  # Fresh from background refresh
        assert is_fresh is True

    def test_swr_background_refresh_failure_handling(self):
        """Background refresh failures should be tracked."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # First call - miss and fetch
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for fresh entry to expire
        time.sleep(1.5)

        # Make fetch fail on background refresh
        fetch_func.side_effect = Exception("Background refresh failed")

        # Stale hit - triggers failing background refresh
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for background thread
        time.sleep(0.5)

        metrics = cache.get_swr_metrics()
        assert metrics.background_refresh_failures == 1

    def test_swr_max_background_threads_limit(self):
        """Should limit concurrent background refresh threads."""
        from src.utils.smart_cache import SWR_MAX_BACKGROUND_THREADS, SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)

        # Fill cache with stale entries
        for i in range(SWR_MAX_BACKGROUND_THREADS + 5):
            fetch_func = Mock(return_value=f"value{i}")
            cache.get_with_swr(f"key{i}", fetch_func, ttl=1, stale_ttl=3)

        # Wait for fresh entries to expire
        time.sleep(1.5)

        # Try to trigger many background refreshes
        for i in range(SWR_MAX_BACKGROUND_THREADS + 5):
            fetch_func = Mock(return_value=f"updated{i}")
            cache.get_with_swr(f"key{i}", fetch_func, ttl=1, stale_ttl=3)

        # Wait for background threads to start
        time.sleep(0.1)

        # Should not exceed max threads
        with cache._background_lock:
            assert len(cache._background_refresh_threads) <= SWR_MAX_BACKGROUND_THREADS


class TestSWRMetrics:
    """Tests for SWR metrics tracking."""

    def test_swr_metrics_hit_rate(self):
        """Hit rate should be calculated correctly."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # 1 miss, 1 hit
        cache.get_with_swr("key", fetch_func, ttl=3600)
        cache.get_with_swr("key", fetch_func, ttl=3600)

        metrics = cache.get_swr_metrics()
        assert metrics.hit_rate() == 50.0  # 1 hit / 2 total

    def test_swr_metrics_stale_hit_rate(self):
        """Stale hit rate should be calculated correctly."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        # 1 miss
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        # Wait for fresh to expire
        time.sleep(1.5)

        # 1 stale hit
        cache.get_with_swr("key", fetch_func, ttl=1, stale_ttl=3)

        metrics = cache.get_swr_metrics()
        assert metrics.stale_hit_rate() == 50.0  # 1 stale / 2 total

    def test_swr_metrics_includes_in_stats(self):
        """SWR metrics should be included in get_stats()."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        cache.get_with_swr("key", fetch_func, ttl=3600)

        stats = cache.get_stats()
        assert "swr_enabled" in stats
        assert "swr_hit_rate_pct" in stats
        assert "swr_stale_hit_rate_pct" in stats
        assert "avg_cached_latency_ms" in stats
        assert "avg_uncached_latency_ms" in stats
        assert "background_refreshes" in stats

    def test_swr_metrics_returns_copy(self):
        """get_swr_metrics should return a copy to prevent external modification."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        cache.get_with_swr("key", fetch_func, ttl=3600)

        metrics1 = cache.get_swr_metrics()
        metrics2 = cache.get_swr_metrics()

        # Modify metrics1
        metrics1.hits = 999

        # metrics2 should be unchanged
        assert metrics2.hits != 999


class TestSWRDisabled:
    """Tests for SWR disabled fallback behavior."""

    def test_swr_disabled_uses_normal_cache(self):
        """When SWR disabled, should use normal cache behavior."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=False)
        fetch_func = Mock(return_value="value")

        # First call - miss and fetch
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
        assert result == "value"
        assert is_fresh is True
        assert fetch_func.call_count == 1

        # Second call - hit (no stale behavior)
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
        assert result == "value"
        assert is_fresh is True
        assert fetch_func.call_count == 1

    def test_swr_disabled_no_stale_entry(self):
        """When SWR disabled, should not create stale entries."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=False)
        fetch_func = Mock(return_value="value")

        cache.get_with_swr("key", fetch_func, ttl=3600)

        # Should only have one entry (no :stale entry)
        assert "key" in cache._cache
        assert "key:stale" not in cache._cache


class TestSWREdgeCases:
    """Tests for SWR edge cases and error handling."""

    def test_swr_none_value_not_cached(self):
        """None values should not be cached."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value=None)

        # First call - miss, returns None
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
        assert result is None
        assert is_fresh is False

        # Second call - still miss (not cached)
        result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
        assert result is None
        assert is_fresh is False
        assert fetch_func.call_count == 2  # Called again

    def test_swr_default_stale_ttl_multiplier(self):
        """Should use SWR_TTL_MULTIPLIER when stale_ttl not provided."""
        from src.utils.smart_cache import SWR_TTL_MULTIPLIER, SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        ttl = 100
        cache.get_with_swr("key", fetch_func, ttl=ttl)

        # Check stale entry TTL
        stale_key = "key:stale"
        if stale_key in cache._cache:
            stale_entry = cache._cache[stale_key]
            assert stale_entry.ttl_seconds == ttl * SWR_TTL_MULTIPLIER

    def test_swr_with_match_time(self):
        """SWR should work with match_time parameter."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")
        match_time = datetime.now(timezone.utc) + timedelta(hours=24)

        cache.get_with_swr("key", fetch_func, ttl=3600, match_time=match_time)

        # Verify match_time is stored
        entry = cache._cache.get("key")
        assert entry is not None
        assert entry.match_time == match_time

    def test_swr_concurrent_access_thread_safety(self):
        """SWR should be thread-safe under concurrent access."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_swr", swr_enabled=True)
        fetch_func = Mock(return_value="value")

        results = []
        errors = []

        def worker():
            try:
                result, is_fresh = cache.get_with_swr("key", fetch_func, ttl=3600)
                results.append((result, is_fresh))
            except Exception as e:
                errors.append(e)

        # Spawn multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0
        assert len(results) == 10

        # All results should be valid
        for result, is_fresh in results:
            assert result == "value"
            assert is_fresh is True


class TestSWRIntegration:
    """Integration tests for SWR with data_provider."""

    def test_swr_integration_with_team_cache(self):
        """SWR should work with global team cache."""
        from src.utils.smart_cache import get_team_cache

        cache = get_team_cache()
        fetch_func = Mock(return_value={"team_id": 123})

        # SWR should be enabled on global caches
        assert cache.swr_enabled is True

        result, is_fresh = cache.get_with_swr("team:123", fetch_func, ttl=3600)
        assert result == {"team_id": 123}
        assert is_fresh is True

    def test_swr_integration_with_match_cache(self):
        """SWR should work with global match cache."""
        from src.utils.smart_cache import get_match_cache

        cache = get_match_cache()
        fetch_func = Mock(return_value={"match_id": 456})

        result, is_fresh = cache.get_with_swr("match:456", fetch_func, ttl=600)
        assert result == {"match_id": 456}
        assert is_fresh is True

    def test_swr_integration_with_search_cache(self):
        """SWR should work with global search cache."""
        from src.utils.smart_cache import get_search_cache

        cache = get_search_cache()
        fetch_func = Mock(return_value={"results": []})

        result, is_fresh = cache.get_with_swr("search:test", fetch_func, ttl=1800)
        assert result == {"results": []}
        assert is_fresh is True
