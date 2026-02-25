"""
Integration Tests for SWR Cache with Data Provider

Verifies SWR integration with:
1. FotMobProvider._get_with_swr()
2. log_fotmob_cache_metrics()
3. End-to-end SWR workflows
"""

import time


class TestSWRIntegrationBasic:
    """Basic integration tests for SWR with data_provider."""

    def test_get_with_swr_returns_tuple(self):
        """_get_with_swr should return (value, is_fresh) tuple."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        # Test with SWR enabled
        if provider._swr_cache:
            result, is_fresh = provider._get_with_swr(
                "test_key",
                lambda: {"data": "test"},
                ttl=3600,
                stale_ttl=7200,
            )
            assert isinstance(result, dict)
            assert isinstance(is_fresh, bool)

    def test_get_with_swr_caches_results(self):
        """_get_with_swr should cache results correctly."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # First call - miss
            result1, is_fresh1 = provider._get_with_swr(
                "cache_test",
                lambda: {"value": 1},
                ttl=3600,
                stale_ttl=7200,
            )
            assert result1 == {"value": 1}
            assert is_fresh1 is True

            # Second call - fresh hit
            result2, is_fresh2 = provider._get_with_swr(
                "cache_test",
                lambda: {"value": 2},
                ttl=3600,
                stale_ttl=7200,
            )
            assert result2 == {"value": 1}  # Still cached value
            assert is_fresh2 is True

    def test_get_with_swr_stale_behavior(self):
        """_get_with_swr should serve stale data and refresh."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # First call - miss
            result1, is_fresh1 = provider._get_with_swr(
                "stale_test",
                lambda: {"value": "v1"},
                ttl=1,
                stale_ttl=3,
            )
            assert result1 == {"value": "v1"}
            assert is_fresh1 is True

            # Wait for fresh to expire
            time.sleep(1.5)

            # Second call - stale hit
            result2, is_fresh2 = provider._get_with_swr(
                "stale_test",
                lambda: {"value": "v2"},
                ttl=1,
                stale_ttl=3,
            )
            assert result2 == {"value": "v1"}  # Stale data
            assert is_fresh2 is False

            # Wait for background refresh
            time.sleep(0.5)

            # Third call - should have fresh data from background refresh
            result3, is_fresh3 = provider._get_with_swr(
                "stale_test",
                lambda: {"value": "v3"},
                ttl=1,
                stale_ttl=3,
            )
            # Should be fresh from background refresh
            assert is_fresh3 is True


class TestSWRIntegrationMetrics:
    """Integration tests for SWR metrics logging."""

    def test_log_fotmob_cache_metrics_callable(self):
        """log_fotmob_cache_metrics should be callable."""
        from src.ingestion.data_provider import log_fotmob_cache_metrics

        # Should not raise
        try:
            log_fotmob_cache_metrics()
        except Exception as e:
            # Function should handle errors gracefully
            assert "not available" in str(e) or "module" in str(e)

    def test_swr_metrics_tracks_operations(self):
        """SWR metrics should track cache operations."""
        from src.utils.smart_cache import SmartCache

        cache = SmartCache(name="test_metrics", swr_enabled=True)

        # Perform some operations
        cache.get_with_swr("key1", lambda: "value1", ttl=3600)
        cache.get_with_swr("key1", lambda: "value1", ttl=3600)  # Hit
        cache.get_with_swr("key2", lambda: "value2", ttl=3600)  # Miss

        # Check metrics
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "swr_hit_rate_pct" in stats


class TestSWRIntegrationEndToEnd:
    """End-to-end integration tests for SWR workflow."""

    def test_full_swr_miss_hit_cycle(self):
        """Test complete SWR cycle: miss -> hit -> stale -> refresh."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # Clear cache
            provider._swr_cache.clear()

            # Step 1: MISS
            result1, is_fresh1 = provider._get_with_swr(
                "e2e_test",
                lambda: {"version": 1},
                ttl=1,
                stale_ttl=3,
            )
            assert result1 == {"version": 1}
            assert is_fresh1 is True

            # Step 2: FRESH HIT
            result2, is_fresh2 = provider._get_with_swr(
                "e2e_test",
                lambda: {"version": 2},
                ttl=1,
                stale_ttl=3,
            )
            assert result2 == {"version": 1}  # Still cached
            assert is_fresh2 is True

            # Wait for fresh to expire
            time.sleep(1.5)

            # Step 3: STALE HIT (triggers background refresh)
            result3, is_fresh3 = provider._get_with_swr(
                "e2e_test",
                lambda: {"version": 3},
                ttl=1,
                stale_ttl=3,
            )
            assert result3 == {"version": 1}  # Stale
            assert is_fresh3 is False

            # Wait for background refresh
            time.sleep(0.5)

            # Step 4: FRESH HIT (from background refresh)
            result4, is_fresh4 = provider._get_with_swr(
                "e2e_test",
                lambda: {"version": 4},
                ttl=1,
                stale_ttl=3,
            )
            # Should be fresh from background refresh
            assert is_fresh4 is True

    def test_swr_with_none_return_value(self):
        """SWR should handle None return values correctly."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # Call that returns None
            result, is_fresh = provider._get_with_swr(
                "none_test",
                lambda: None,
                ttl=3600,
                stale_ttl=7200,
            )
            # None values are not cached
            assert result is None
            assert is_fresh is False


class TestSWRIntegrationConcurrency:
    """Integration tests for concurrent SWR access."""

    def test_concurrent_swr_access(self):
        """Test concurrent access to _get_with_swr."""
        import threading

        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            results = []
            errors = []

            def worker(worker_id):
                try:
                    result, is_fresh = provider._get_with_swr(
                        "concurrent_test",
                        lambda: {"worker": worker_id},
                        ttl=3600,
                        stale_ttl=7200,
                    )
                    results.append((result, is_fresh))
                except Exception as e:
                    errors.append(e)

            # Spawn multiple threads
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should have no errors
            assert len(errors) == 0
            assert len(results) == 5

            # All results should be valid
            for result, is_fresh in results:
                assert isinstance(result, dict)
                assert isinstance(is_fresh, bool)


class TestSWRIntegrationEdgeCases:
    """Integration tests for edge cases."""

    def test_swr_with_exception_in_fetch(self):
        """SWR should handle exceptions in fetch function."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # Call that raises exception
            result, is_fresh = provider._get_with_swr(
                "error_test",
                lambda: (_ for _ in ()).throw(ValueError("Test error")),
                ttl=3600,
                stale_ttl=7200,
            )
            # Should handle exception gracefully
            assert result is None
            assert is_fresh is False

    def test_swr_with_different_keys(self):
        """SWR should handle different cache keys correctly."""
        from src.ingestion.data_provider import FotMobProvider

        provider = FotMobProvider()

        if provider._swr_cache:
            # Clear cache
            provider._swr_cache.clear()

            # Fetch multiple different keys
            result1, _ = provider._get_with_swr("key1", lambda: "v1", ttl=3600)
            result2, _ = provider._get_with_swr("key2", lambda: "v2", ttl=3600)
            result3, _ = provider._get_with_swr("key3", lambda: "v3", ttl=3600)

            assert result1 == "v1"
            assert result2 == "v2"
            assert result3 == "v3"

            # Should have 3 entries
            stats = provider._swr_cache.get_stats()
            assert stats["size"] >= 3
