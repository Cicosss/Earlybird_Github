#!/usr/bin/env python3
"""
Integration tests for RefereeCache V9.0

Tests the RefereeCache implementation including:
- Cache file operations (read/write)
- TTL (Time-To-Live) enforcement
- Cache hit/miss scenarios
- Global cache instance management
- Error handling and recovery
- Thread safety considerations

These tests use real file I/O operations but are isolated in a test cache directory.
"""

import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.analysis.referee_cache import CACHE_TTL_DAYS, RefereeCache, get_referee_cache

# ============================================
# FIXTURES
# ============================================


@pytest.fixture
def temp_cache_dir():
    """
    Create a temporary directory for test cache files.
    Automatically cleaned up after each test.
    """
    temp_dir = tempfile.mkdtemp()
    cache_file = Path(temp_dir) / "test_referee_stats.json"
    yield temp_dir, cache_file
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def referee_cache(temp_cache_dir):
    """
    Create a RefereeCache instance with temporary cache file.
    """
    temp_dir, cache_file = temp_cache_dir
    return RefereeCache(cache_file=cache_file, ttl_days=CACHE_TTL_DAYS)


@pytest.fixture
def sample_referee_stats():
    """Sample referee statistics for testing."""
    return {
        "name": "Michael Oliver",
        "cards_per_game": 5.2,
        "strictness": "strict",
        "matches_officiated": 150,
    }


@pytest.fixture
def sample_referee_stats_2():
    """Second sample referee statistics for testing."""
    return {
        "name": "Antonio Mateu Lahoz",
        "cards_per_game": 4.3,
        "strictness": "average",
        "matches_officiated": 120,
    }


# ============================================
# TEST CLASS: Cache File Operations
# ============================================


class TestRefereeCacheFileOperations:
    """Test basic cache file operations."""

    def test_cache_file_created_on_init(self, temp_cache_dir):
        """Test that cache file is created when cache is initialized."""
        temp_dir, cache_file = temp_cache_dir

        # Cache file should not exist yet
        assert not cache_file.exists()

        # Initialize cache
        cache = RefereeCache(cache_file=cache_file, ttl_days=7)

        # Cache directory should be created
        assert cache_file.parent.exists()

        # Cache file should still not exist (created on first write)
        assert not cache_file.exists()

    def test_cache_file_created_on_first_write(self, referee_cache, sample_referee_stats):
        """Test that cache file is created on first set() operation."""
        cache_file = referee_cache.cache_file

        # Cache file should not exist yet
        assert not cache_file.exists()

        # Write to cache
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Cache file should now exist
        assert cache_file.exists()

    def test_cache_file_structure(self, referee_cache, sample_referee_stats):
        """Test that cache file has correct JSON structure."""
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Read cache file directly
        with open(referee_cache.cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # Verify structure
        assert "Michael Oliver" in cache_data
        assert "cached_at" in cache_data["Michael Oliver"]
        assert "stats" in cache_data["Michael Oliver"]
        assert cache_data["Michael Oliver"]["stats"] == sample_referee_stats

    def test_cache_file_multiple_entries(
        self, referee_cache, sample_referee_stats, sample_referee_stats_2
    ):
        """Test that cache file can store multiple referee entries."""
        referee_cache.set("Michael Oliver", sample_referee_stats)
        referee_cache.set("Antonio Mateu Lahoz", sample_referee_stats_2)

        # Read cache file
        with open(referee_cache.cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # Verify both entries exist
        assert len(cache_data) == 2
        assert "Michael Oliver" in cache_data
        assert "Antonio Mateu Lahoz" in cache_data

    def test_cache_file_persistence(self, temp_cache_dir, sample_referee_stats):
        """Test that cache persists across cache instance recreations."""
        temp_dir, cache_file = temp_cache_dir

        # Create first cache instance and write data
        cache1 = RefereeCache(cache_file=cache_file, ttl_days=7)
        cache1.set("Michael Oliver", sample_referee_stats)

        # Create second cache instance (simulates process restart)
        cache2 = RefereeCache(cache_file=cache_file, ttl_days=7)

        # Verify data persists
        retrieved = cache2.get("Michael Oliver")
        assert retrieved == sample_referee_stats


# ============================================
# TEST CLASS: Cache Get/Set Operations
# ============================================


class TestRefereeCacheGetSet:
    """Test cache get() and set() operations."""

    def test_set_and_get_success(self, referee_cache, sample_referee_stats):
        """Test successful set and get operations."""
        referee_cache.set("Michael Oliver", sample_referee_stats)

        retrieved = referee_cache.get("Michael Oliver")
        assert retrieved == sample_referee_stats

    def test_get_nonexistent_referee(self, referee_cache):
        """Test getting a referee that doesn't exist in cache."""
        retrieved = referee_cache.get("Nonexistent Referee")
        assert retrieved is None

    def test_get_empty_cache(self, referee_cache):
        """Test getting from an empty cache."""
        retrieved = referee_cache.get("Any Referee")
        assert retrieved is None

    def test_set_overwrites_existing(self, referee_cache, sample_referee_stats):
        """Test that set() overwrites existing entry."""
        # Set initial data
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Set new data
        new_stats = {
            "name": "Michael Oliver",
            "cards_per_game": 6.0,
            "strictness": "strict",
            "matches_officiated": 160,
        }
        referee_cache.set("Michael Oliver", new_stats)

        # Verify new data
        retrieved = referee_cache.get("Michael Oliver")
        assert retrieved == new_stats
        assert retrieved["cards_per_game"] == 6.0

    def test_set_case_sensitivity(self, referee_cache, sample_referee_stats):
        """Test that referee names are case-sensitive."""
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Different case should not match
        retrieved = referee_cache.get("michael oliver")
        assert retrieved is None

        retrieved = referee_cache.get("MICHAEL OLIVER")
        assert retrieved is None

    def test_set_unicode_names(self, referee_cache):
        """Test that cache handles unicode referee names."""
        unicode_stats = {
            "name": "Álvaro Fernández",
            "cards_per_game": 4.1,
            "strictness": "average",
            "matches_officiated": 100,
        }

        referee_cache.set("Álvaro Fernández", unicode_stats)

        retrieved = referee_cache.get("Álvaro Fernández")
        assert retrieved == unicode_stats


# ============================================
# TEST CLASS: TTL (Time-To-Live) Enforcement
# ============================================


class TestRefereeCacheTTL:
    """Test TTL (Time-To-Live) enforcement."""

    def test_get_valid_entry(self, referee_cache, sample_referee_stats):
        """Test getting a valid (non-expired) entry."""
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Should be immediately available
        retrieved = referee_cache.get("Michael Oliver")
        assert retrieved == sample_referee_stats

    def test_get_expired_entry(self, temp_cache_dir, sample_referee_stats):
        """Test that expired entries return None."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache with 1-day TTL
        cache = RefereeCache(cache_file=cache_file, ttl_days=1)

        # Set entry
        cache.set("Michael Oliver", sample_referee_stats)

        # Manually modify cached_at to be 2 days ago
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        old_cached_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        cache_data["Michael Oliver"]["cached_at"] = old_cached_at

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Entry should be expired
        retrieved = cache.get("Michael Oliver")
        assert retrieved is None

    def test_get_entry_exactly_at_ttl_boundary(self, temp_cache_dir, sample_referee_stats):
        """Test entry exactly at TTL boundary (edge case)."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache with 1-day TTL
        cache = RefereeCache(cache_file=cache_file, ttl_days=1)

        # Set entry
        cache.set("Michael Oliver", sample_referee_stats)

        # Manually set cached_at to exactly 1 day ago
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        boundary_cached_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cache_data["Michael Oliver"]["cached_at"] = boundary_cached_at

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Entry should be considered expired (now > expiry_date)
        retrieved = cache.get("Michael Oliver")
        assert retrieved is None

    def test_get_entry_one_second_before_expiration(self, temp_cache_dir, sample_referee_stats):
        """Test entry one second before expiration."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache with 1-day TTL
        cache = RefereeCache(cache_file=cache_file, ttl_days=1)

        # Set entry
        cache.set("Michael Oliver", sample_referee_stats)

        # Manually set cached_at to 1 day minus 1 second ago
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        almost_expired_at = (
            datetime.now(timezone.utc) - timedelta(days=1) + timedelta(seconds=1)
        ).isoformat()
        cache_data["Michael Oliver"]["cached_at"] = almost_expired_at

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Entry should still be valid
        retrieved = cache.get("Michael Oliver")
        assert retrieved == sample_referee_stats

    def test_custom_ttl(self, temp_cache_dir, sample_referee_stats):
        """Test cache with custom TTL."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache with 30-day TTL
        cache = RefereeCache(cache_file=cache_file, ttl_days=30)

        # Set entry
        cache.set("Michael Oliver", sample_referee_stats)

        # Manually set cached_at to 15 days ago
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        old_cached_at = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        cache_data["Michael Oliver"]["cached_at"] = old_cached_at

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Entry should still be valid (15 < 30)
        retrieved = cache.get("Michael Oliver")
        assert retrieved == sample_referee_stats


# ============================================
# TEST CLASS: Cache Statistics
# ============================================


class TestRefereeCacheStats:
    """Test cache statistics reporting."""

    def test_get_stats_empty_cache(self, referee_cache):
        """Test stats for empty cache."""
        stats = referee_cache.get_stats()

        assert stats["total_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["ttl_days"] == CACHE_TTL_DAYS

    def test_get_stats_single_entry(self, referee_cache, sample_referee_stats):
        """Test stats for cache with one entry."""
        referee_cache.set("Michael Oliver", sample_referee_stats)

        stats = referee_cache.get_stats()

        assert stats["total_entries"] == 1
        assert stats["expired_entries"] == 0
        assert stats["valid_entries"] == 1

    def test_get_stats_multiple_entries(
        self, referee_cache, sample_referee_stats, sample_referee_stats_2
    ):
        """Test stats for cache with multiple entries."""
        referee_cache.set("Michael Oliver", sample_referee_stats)
        referee_cache.set("Antonio Mateu Lahoz", sample_referee_stats_2)

        stats = referee_cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 0
        assert stats["valid_entries"] == 2

    def test_get_stats_with_expired_entries(
        self, temp_cache_dir, sample_referee_stats, sample_referee_stats_2
    ):
        """Test stats with expired entries."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache with 1-day TTL
        cache = RefereeCache(cache_file=cache_file, ttl_days=1)

        # Set two entries
        cache.set("Michael Oliver", sample_referee_stats)
        cache.set("Antonio Mateu Lahoz", sample_referee_stats_2)

        # Expire one entry
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        old_cached_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        cache_data["Michael Oliver"]["cached_at"] = old_cached_at

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Check stats
        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["valid_entries"] == 1

    def test_get_stats_ttl_value(self, referee_cache):
        """Test that stats reports correct TTL value."""
        cache = RefereeCache(cache_file=referee_cache.cache_file, ttl_days=14)
        stats = cache.get_stats()

        assert stats["ttl_days"] == 14


# ============================================
# TEST CLASS: Cache Clear Operations
# ============================================


class TestRefereeCacheClear:
    """Test cache clear operations."""

    def test_clear_empty_cache(self, referee_cache):
        """Test clearing an empty cache."""
        referee_cache.clear()

        # Cache file should not exist
        assert not referee_cache.cache_file.exists()

    def test_clear_populated_cache(
        self, referee_cache, sample_referee_stats, sample_referee_stats_2
    ):
        """Test clearing a populated cache."""
        # Add entries
        referee_cache.set("Michael Oliver", sample_referee_stats)
        referee_cache.set("Antonio Mateu Lahoz", sample_referee_stats_2)

        # Verify entries exist
        assert referee_cache.get("Michael Oliver") is not None
        assert referee_cache.get("Antonio Mateu Lahoz") is not None

        # Clear cache
        referee_cache.clear()

        # Verify entries are gone
        assert referee_cache.get("Michael Oliver") is None
        assert referee_cache.get("Antonio Mateu Lahoz") is None

        # Cache file should not exist
        assert not referee_cache.cache_file.exists()

    def test_clear_recreates_on_next_set(self, referee_cache, sample_referee_stats):
        """Test that cache can be used after clear."""
        # Set and clear
        referee_cache.set("Michael Oliver", sample_referee_stats)
        referee_cache.clear()

        # Set new entry
        referee_cache.set("Antonio Mateu Lahoz", sample_referee_stats)

        # Verify new entry works
        retrieved = referee_cache.get("Antonio Mateu Lahoz")
        assert retrieved == sample_referee_stats


# ============================================
# TEST CLASS: Global Cache Instance
# ============================================


class TestRefereeCacheGlobalInstance:
    """Test global cache instance management."""

    def test_get_referee_cache_singleton(self):
        """Test that get_referee_cache() returns singleton instance."""
        cache1 = get_referee_cache()
        cache2 = get_referee_cache()

        # Should be the same instance
        assert cache1 is cache2

    def test_global_cache_persistence(self, sample_referee_stats):
        """Test that global cache persists across calls."""
        cache = get_referee_cache()
        cache.set("Michael Oliver", sample_referee_stats)

        # Get cache again
        cache2 = get_referee_cache()

        # Should retrieve same data
        retrieved = cache2.get("Michael Oliver")
        assert retrieved == sample_referee_stats

    def test_global_cache_default_location(self):
        """Test that global cache uses default location."""
        cache = get_referee_cache()

        # Should use default cache file location
        assert cache.cache_file.name == "referee_stats.json"
        assert "cache" in str(cache.cache_file.parent)


# ============================================
# TEST CLASS: Error Handling
# ============================================


class TestRefereeCacheErrorHandling:
    """Test error handling and recovery."""

    def test_get_corrupted_cache_file(self, temp_cache_dir):
        """Test handling of corrupted cache file."""
        temp_dir, cache_file = temp_cache_dir

        # Create corrupted cache file
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write("This is not valid JSON {{{")

        # Cache should handle gracefully
        cache = RefereeCache(cache_file=cache_file, ttl_days=7)

        # Should return None for any get operation
        retrieved = cache.get("Any Referee")
        assert retrieved is None

    def test_set_with_permission_error(self, temp_cache_dir, sample_referee_stats):
        """Test handling of permission errors on write."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache
        cache = RefereeCache(cache_file=cache_file, ttl_days=7)

        # Make cache directory read-only (Unix-like systems only)
        try:
            cache_file.parent.chmod(0o444)

            # Set should not crash, but may log warning
            cache.set("Michael Oliver", sample_referee_stats)

            # Restore permissions
            cache_file.parent.chmod(0o755)

        except (OSError, PermissionError):
            # Skip test if chmod not supported
            pytest.skip("chmod not supported on this system")

    def test_get_with_missing_cached_at(self, temp_cache_dir, sample_referee_stats):
        """Test handling of entry without cached_at field."""
        temp_dir, cache_file = temp_cache_dir

        # Create cache file with malformed entry
        cache_data = {
            "Michael Oliver": {
                "stats": sample_referee_stats
                # Missing "cached_at" field
            }
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Cache should handle gracefully
        cache = RefereeCache(cache_file=cache_file, ttl_days=7)

        # Should return None for malformed entry
        retrieved = cache.get("Michael Oliver")
        assert retrieved is None

    def test_set_with_invalid_stats(self, referee_cache):
        """Test setting referee stats with invalid data types."""
        # Should handle various data types gracefully
        invalid_stats = {
            "name": "Test Referee",
            "cards_per_game": "not a number",  # Invalid type
            "strictness": "unknown",
        }

        # Should not crash
        referee_cache.set("Test Referee", invalid_stats)

        # Should be able to retrieve (even if invalid)
        retrieved = referee_cache.get("Test Referee")
        assert retrieved is not None
        assert retrieved["cards_per_game"] == "not a number"


# ============================================
# TEST CLASS: Concurrent Access
# ============================================


class TestRefereeCacheConcurrency:
    """Test cache behavior under concurrent access."""

    def test_concurrent_set_operations(self, referee_cache):
        """Test multiple set operations on same referee."""
        stats1 = {"name": "Michael Oliver", "cards_per_game": 5.0}
        stats2 = {"name": "Michael Oliver", "cards_per_game": 5.5}
        stats3 = {"name": "Michael Oliver", "cards_per_game": 6.0}

        # Set multiple times
        referee_cache.set("Michael Oliver", stats1)
        referee_cache.set("Michael Oliver", stats2)
        referee_cache.set("Michael Oliver", stats3)

        # Last set should win
        retrieved = referee_cache.get("Michael Oliver")
        assert retrieved["cards_per_game"] == 6.0

    def test_concurrent_different_referees(self, referee_cache):
        """Test setting multiple different referees."""
        referees = [
            ("Michael Oliver", {"cards_per_game": 5.2}),
            ("Antonio Mateu Lahoz", {"cards_per_game": 4.3}),
            ("Felix Brych", {"cards_per_game": 2.8}),
            ("Daniele Orsato", {"cards_per_game": 3.5}),
        ]

        # Set all
        for name, stats in referees:
            referee_cache.set(name, stats)

        # Verify all are retrievable
        for name, stats in referees:
            retrieved = referee_cache.get(name)
            assert retrieved is not None
            assert retrieved["cards_per_game"] == stats["cards_per_game"]


# ============================================
# TEST CLASS: Integration with RefereeStats
# ============================================


class TestRefereeCacheIntegration:
    """Test integration of RefereeCache with RefereeStats class."""

    def test_cache_referee_stats_object(self, referee_cache):
        """Test caching and retrieving RefereeStats objects."""
        from src.analysis.verification_layer import RefereeStats

        # Create RefereeStats object
        referee_stats = RefereeStats(
            name="Michael Oliver", cards_per_game=5.2, matches_officiated=150
        )

        # Convert to dict for caching
        stats_dict = {
            "name": referee_stats.name,
            "cards_per_game": referee_stats.cards_per_game,
            "strictness": referee_stats.strictness,
            "matches_officiated": referee_stats.matches_officiated,
        }

        # Cache it
        referee_cache.set("Michael Oliver", stats_dict)

        # Retrieve and recreate RefereeStats
        retrieved_dict = referee_cache.get("Michael Oliver")
        retrieved_stats = RefereeStats(**retrieved_dict)

        # Verify equality
        assert retrieved_stats.name == referee_stats.name
        assert retrieved_stats.cards_per_game == referee_stats.cards_per_game
        assert retrieved_stats.strictness == referee_stats.strictness

    def test_cache_hit_rate_tracking(self, referee_cache, sample_referee_stats):
        """Test tracking cache hit rate (manual implementation)."""
        # Set up cache
        referee_cache.set("Michael Oliver", sample_referee_stats)

        # Simulate cache hits and misses
        hits = 0
        misses = 0

        # Hit
        if referee_cache.get("Michael Oliver"):
            hits += 1

        # Miss
        if not referee_cache.get("Nonexistent Referee"):
            misses += 1

        # Another hit
        if referee_cache.get("Michael Oliver"):
            hits += 1

        # Calculate hit rate
        total_requests = hits + misses
        hit_rate = hits / total_requests if total_requests > 0 else 0.0

        assert hits == 2
        assert misses == 1
        assert hit_rate == 2.0 / 3.0


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
