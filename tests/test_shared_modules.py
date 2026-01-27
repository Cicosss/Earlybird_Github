"""
Tests for EarlyBird Shared Modules V7.0

Tests the new centralized modules:
1. src/utils/freshness.py - Centralized freshness logic
2. src/utils/discovery_queue.py - Thread-safe discovery queue
3. src/utils/shared_cache.py - Cross-component deduplication cache

These tests validate:
- Correct freshness tag calculation
- Thread-safe queue operations
- Cross-component deduplication
- Edge case handling (None, empty, clock skew)
"""
import pytest
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


# ============================================
# FRESHNESS MODULE TESTS
# ============================================

class TestFreshnessModule:
    """Tests for src/utils/freshness.py"""
    
    def test_freshness_tag_fresh(self):
        """Test FRESH tag for news < 60 min old."""
        from src.utils.freshness import get_freshness_tag
        
        assert get_freshness_tag(0) == "🔥 FRESH"
        assert get_freshness_tag(30) == "🔥 FRESH"
        assert get_freshness_tag(59) == "🔥 FRESH"
    
    def test_freshness_tag_aging(self):
        """Test AGING tag for news 60-360 min old."""
        from src.utils.freshness import get_freshness_tag
        
        assert get_freshness_tag(60) == "⏰ AGING"
        assert get_freshness_tag(180) == "⏰ AGING"
        assert get_freshness_tag(359) == "⏰ AGING"
    
    def test_freshness_tag_stale(self):
        """Test STALE tag for news > 360 min old."""
        from src.utils.freshness import get_freshness_tag
        
        assert get_freshness_tag(360) == "📜 STALE"
        assert get_freshness_tag(1000) == "📜 STALE"
        assert get_freshness_tag(10000) == "📜 STALE"
    
    def test_freshness_tag_clock_skew(self):
        """Test that negative minutes (clock skew) returns FRESH."""
        from src.utils.freshness import get_freshness_tag
        
        # Negative minutes = future timestamp = clock skew
        assert get_freshness_tag(-5) == "🔥 FRESH"
        assert get_freshness_tag(-100) == "🔥 FRESH"
    
    def test_calculate_minutes_old(self):
        """Test minutes calculation from timestamp."""
        from src.utils.freshness import calculate_minutes_old
        
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=30)
        
        minutes = calculate_minutes_old(past, now)
        assert 29 <= minutes <= 31  # Allow 1 min tolerance
    
    def test_calculate_minutes_old_naive_datetime(self):
        """Test that naive datetimes are handled correctly."""
        from src.utils.freshness import calculate_minutes_old
        
        # Naive datetime (no timezone)
        naive_past = datetime.utcnow() - timedelta(minutes=60)
        
        minutes = calculate_minutes_old(naive_past)
        assert 59 <= minutes <= 61
    
    def test_decay_multiplier_fresh(self):
        """Test decay multiplier for fresh news."""
        from src.utils.freshness import calculate_decay_multiplier
        
        # 0 minutes = 100% impact
        assert calculate_decay_multiplier(0) == 1.0
        
        # 5 minutes = ~78% impact
        mult = calculate_decay_multiplier(5)
        assert 0.7 < mult < 0.85
    
    def test_decay_multiplier_stale(self):
        """Test decay multiplier for stale news."""
        from src.utils.freshness import calculate_decay_multiplier
        
        # Very old news = minimum residual value
        mult = calculate_decay_multiplier(24 * 60)  # 24 hours
        assert mult == 0.01  # Residual value
    
    def test_full_freshness_result(self):
        """Test get_full_freshness returns complete result."""
        from src.utils.freshness import get_full_freshness, FreshnessResult
        
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=30)
        
        result = get_full_freshness(past, now)
        
        assert isinstance(result, FreshnessResult)
        assert result.tag == "🔥 FRESH"
        assert result.category == "FRESH"
        assert 29 <= result.minutes_old <= 31
        assert 0 < result.decay_multiplier < 1
    
    def test_parse_relative_time(self):
        """Test parsing of relative time strings."""
        from src.utils.freshness import parse_relative_time
        
        assert parse_relative_time("just now") == 0
        assert parse_relative_time("5 minutes ago") == 5
        assert parse_relative_time("2 hours ago") == 120
        assert parse_relative_time("1 day ago") == 1440
        assert parse_relative_time("yesterday") == 1440
        
        # Invalid strings
        assert parse_relative_time("") is None
        assert parse_relative_time("invalid") is None
    
    def test_league_decay_rates(self):
        """Test league-specific decay rates."""
        from src.utils.freshness import get_league_decay_rate
        
        # Tier 1 leagues have faster decay
        epl_rate = get_league_decay_rate("soccer_epl")
        assert epl_rate == 0.14
        
        # Unknown leagues use default (slower decay)
        unknown_rate = get_league_decay_rate("soccer_unknown_league")
        assert unknown_rate == 0.023
        
        # None returns default
        none_rate = get_league_decay_rate(None)
        assert none_rate == 0.023


# ============================================
# DISCOVERY QUEUE TESTS
# ============================================

class TestDiscoveryQueue:
    """Tests for src/utils/discovery_queue.py"""
    
    def test_push_and_pop(self):
        """Test basic push and pop operations."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue(max_entries=100, ttl_hours=24)
        
        # Push a discovery
        uuid = queue.push(
            data={'title': 'Test News'},
            league_key='soccer_epl',
            team='Arsenal',
            title='Test News',
            url='https://example.com/news'
        )
        
        assert uuid is not None
        assert queue.size() == 1
        
        # Pop for matching team
        results = queue.pop_for_match(
            match_id='match123',
            team_names=['Arsenal', 'Chelsea'],
            league_key='soccer_epl'
        )
        
        assert len(results) == 1
        assert results[0]['match_id'] == 'match123'
        assert results[0]['team'] == 'Arsenal'
    
    def test_pop_no_match(self):
        """Test pop returns empty for non-matching teams."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        queue.push(
            data={},
            league_key='soccer_epl',
            team='Arsenal'
        )
        
        # Different team
        results = queue.pop_for_match(
            match_id='match123',
            team_names=['Liverpool'],
            league_key='soccer_epl'
        )
        
        assert len(results) == 0
    
    def test_pop_different_league(self):
        """Test pop returns empty for different league."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        queue.push(
            data={},
            league_key='soccer_epl',
            team='Arsenal'
        )
        
        # Different league
        results = queue.pop_for_match(
            match_id='match123',
            team_names=['Arsenal'],
            league_key='soccer_spain_la_liga'
        )
        
        assert len(results) == 0
    
    def test_empty_team_names(self):
        """Test pop handles empty team_names gracefully."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        queue.push(data={}, league_key='soccer_epl', team='Arsenal')
        
        # Empty team names
        results = queue.pop_for_match(
            match_id='match123',
            team_names=[],
            league_key='soccer_epl'
        )
        
        assert results == []
    
    def test_none_team_in_list(self):
        """Test pop handles None values in team_names."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        queue.push(data={}, league_key='soccer_epl', team='Arsenal')
        
        # Team names with None
        results = queue.pop_for_match(
            match_id='match123',
            team_names=[None, 'Arsenal', ''],
            league_key='soccer_epl'
        )
        
        assert len(results) == 1
    
    def test_max_entries_eviction(self):
        """Test LRU eviction when max entries exceeded."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue(max_entries=3, ttl_hours=24)
        
        # Add 4 items (exceeds max of 3)
        queue.push(data={}, league_key='l1', team='Team1')
        queue.push(data={}, league_key='l2', team='Team2')
        queue.push(data={}, league_key='l3', team='Team3')
        queue.push(data={}, league_key='l4', team='Team4')
        
        # Should have max 3 entries
        assert queue.size() <= 3
    
    def test_thread_safety(self):
        """Test queue is thread-safe under concurrent access."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue(max_entries=1000, ttl_hours=24)
        errors = []
        
        def producer(thread_id):
            try:
                for i in range(100):
                    queue.push(
                        data={'thread': thread_id, 'item': i},
                        league_key='soccer_epl',
                        team=f'Team{thread_id}'
                    )
            except Exception as e:
                errors.append(e)
        
        def consumer():
            try:
                for _ in range(50):
                    queue.pop_for_match(
                        match_id='match',
                        team_names=['Team0', 'Team1'],
                        league_key='soccer_epl'
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        # Start threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=producer, args=(i,))
            threads.append(t)
        
        for _ in range(2):
            t = threading.Thread(target=consumer)
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"
    
    def test_cleanup_expired(self):
        """Test cleanup removes expired entries."""
        from src.utils.discovery_queue import DiscoveryQueue, DiscoveryItem
        
        queue = DiscoveryQueue(max_entries=100, ttl_hours=1)
        
        # Add item
        queue.push(data={}, league_key='soccer_epl', team='Arsenal')
        assert queue.size() == 1
        
        # Manually expire the item
        with queue._lock:
            if queue._queue:
                item = queue._queue[0]
                item.discovered_at = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # Cleanup
        removed = queue.cleanup_expired()
        assert removed == 1
        assert queue.size() == 0
    
    def test_stats(self):
        """Test statistics tracking."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        queue.push(data={}, league_key='soccer_epl', team='Arsenal')
        queue.pop_for_match('m1', ['Arsenal'], 'soccer_epl')
        
        stats = queue.get_stats()
        
        assert stats['current_size'] >= 0
        assert stats['total_pushed'] >= 1
        assert 'by_league' in stats


# ============================================
# SHARED CACHE TESTS
# ============================================

class TestSharedCache:
    """Tests for src/utils/shared_cache.py"""
    
    def test_content_deduplication(self):
        """Test content-based deduplication."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        content = "This is test content for deduplication"
        
        # First check - not duplicate
        assert cache.is_duplicate(content=content) is False
        
        # Mark as seen
        cache.mark_seen(content=content, source="test")
        
        # Second check - is duplicate
        assert cache.is_duplicate(content=content) is True
    
    def test_url_deduplication(self):
        """Test URL-based deduplication."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        url = "https://example.com/news/article"
        
        assert cache.is_duplicate(url=url) is False
        cache.mark_seen(url=url, source="test")
        assert cache.is_duplicate(url=url) is True
    
    def test_url_normalization(self):
        """Test URL normalization removes tracking params."""
        from src.utils.shared_cache import normalize_url
        
        url1 = "https://example.com/news?utm_source=twitter&id=123"
        url2 = "https://example.com/news?id=123"
        
        # Both should normalize to same URL (without utm_source)
        assert normalize_url(url1) == normalize_url(url2)
    
    def test_check_and_mark_atomic(self):
        """Test atomic check-and-mark operation."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        content = "Atomic test content"
        
        # First call - not duplicate, marks as seen
        is_dup = cache.check_and_mark(content=content, source="test")
        assert is_dup is False
        
        # Second call - is duplicate
        is_dup = cache.check_and_mark(content=content, source="test")
        assert is_dup is True
    
    def test_cross_source_deduplication(self):
        """Test deduplication works across different sources."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        content = "Cross-source test content"
        
        # news_radar marks content
        cache.mark_seen(content=content, source="news_radar")
        
        # browser_monitor checks - should be duplicate
        is_dup = cache.is_duplicate(content=content, source="browser_monitor")
        assert is_dup is True
    
    def test_empty_content_handling(self):
        """Test empty/None content is handled safely."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        # None content
        assert cache.is_duplicate(content=None) is False
        cache.mark_seen(content=None)  # Should not raise
        
        # Empty string
        assert cache.is_duplicate(content="") is False
        cache.mark_seen(content="")  # Should not raise
    
    def test_stats_by_source(self):
        """Test statistics are tracked by source."""
        from src.utils.shared_cache import SharedContentCache
        
        cache = SharedContentCache()
        
        cache.check_and_mark(content="test1", source="news_radar")
        cache.check_and_mark(content="test2", source="browser_monitor")
        cache.check_and_mark(content="test1", source="main_pipeline")  # Duplicate
        
        stats = cache.get_stats()
        
        assert stats['by_source']['news_radar']['added'] >= 1
        assert stats['by_source']['browser_monitor']['added'] >= 1
        assert stats['by_source']['main_pipeline']['duplicates'] >= 1
    
    def test_singleton_instance(self):
        """Test singleton returns same instance."""
        from src.utils.shared_cache import get_shared_cache, reset_shared_cache
        
        reset_shared_cache()
        
        cache1 = get_shared_cache()
        cache2 = get_shared_cache()
        
        assert cache1 is cache2


# ============================================
# INTEGRATION TESTS
# ============================================

class TestIntegration:
    """Integration tests for the shared modules working together."""
    
    def test_freshness_in_discovery_queue(self):
        """Test freshness tags are correctly applied in discovery queue."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        # Push discovery
        queue.push(
            data={},
            league_key='soccer_epl',
            team='Arsenal',
            title='Breaking News'
        )
        
        # Pop and check freshness tag
        results = queue.pop_for_match(
            match_id='match123',
            team_names=['Arsenal'],
            league_key='soccer_epl'
        )
        
        assert len(results) == 1
        assert 'freshness_tag' in results[0]
        assert results[0]['freshness_tag'] == "🔥 FRESH"  # Just added = fresh
    
    def test_news_hunter_uses_centralized_freshness(self):
        """Test news_hunter imports from centralized freshness module."""
        # This test verifies the import works
        from src.processing.news_hunter import get_freshness_tag
        
        # Should return same results as centralized module
        assert get_freshness_tag(30) == "🔥 FRESH"
        assert get_freshness_tag(120) == "⏰ AGING"
        assert get_freshness_tag(500) == "📜 STALE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================
# REGRESSION TESTS
# ============================================

class TestRegressions:
    """Regression tests for bugs found during code review."""
    
    def test_discovery_queue_returns_core_fields(self):
        """
        Regression test for bug: pop_for_match was not including core fields
        (team, title, snippet, etc.) in the result dict when they weren't
        in the original data dict.
        
        Bug found: 2026-01-08
        """
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        # Push with minimal data dict (simulating real-world usage)
        queue.push(
            data={},  # Empty data dict
            league_key='soccer_epl',
            team='Manchester United',
            title='Breaking: Injury Update',
            snippet='Key player ruled out',
            url='https://example.com/news/123',
            source_name='Sky Sports',
            category='INJURY',
            confidence=0.9
        )
        
        # Pop and verify ALL core fields are present
        results = queue.pop_for_match(
            match_id='match_456',
            team_names=['Manchester United'],
            league_key='soccer_epl'
        )
        
        assert len(results) == 1
        result = results[0]
        
        # These fields MUST be present regardless of what was in data dict
        assert result['team'] == 'Manchester United'
        assert result['title'] == 'Breaking: Injury Update'
        assert result['snippet'] == 'Key player ruled out'
        assert result['url'] == 'https://example.com/news/123'
        assert result['link'] == 'https://example.com/news/123'  # Alias
        assert result['source'] == 'Sky Sports'
        assert result['category'] == 'INJURY'
        assert result['confidence'] == 0.9
        assert result['match_id'] == 'match_456'
        assert 'freshness_tag' in result
        assert 'minutes_old' in result
        assert 'discovered_at' in result
    
    def test_get_browser_monitor_news_no_duplicate_return(self):
        """
        Regression test for bug: get_browser_monitor_news had duplicate
        'return results' statements (dead code).
        
        Bug found: 2026-01-08
        
        This test verifies the function returns correctly and doesn't
        have any syntax issues from the duplicate return.
        """
        from src.processing.news_hunter import get_browser_monitor_news
        
        # Should return empty list for non-existent league
        results = get_browser_monitor_news(
            match_id='test_match',
            team_names=['Test Team'],
            league_key='non_existent_league_xyz'
        )
        
        assert isinstance(results, list)
        assert len(results) == 0
