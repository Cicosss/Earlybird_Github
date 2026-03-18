"""
Integration Tests for RefereeStrictness Feature

Tests the complete data flow from FotMob → RefereeStats → notifier,
ensuring type consistency and correct enum handling across all components.

Coverage:
- RefereeStats object conversion to dict
- RefereeStrictness enum vs RefereeStats lowercase values (backward compatibility)
- referee_cache with expired entries for referee_strictness
- End-to-end flow from FotMob → RefereeStats → notifier
- Case-insensitive validation in Pydantic models
"""

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.analysis.referee_cache import RefereeCache
from src.analysis.verification_layer import RefereeStats
from src.schemas.perplexity_schemas import BettingStatsResponse, RefereeStrictness


class TestRefereeStatsEnumIntegration:
    """Test RefereeStats integration with RefereeStrictness enum."""

    def test_referee_stats_uses_enum(self):
        """Test that RefereeStats.strictness is a RefereeStrictness enum."""
        referee = RefereeStats(name="Test Referee", cards_per_game=5.2)
        assert isinstance(referee.strictness, RefereeStrictness)
        assert referee.strictness == RefereeStrictness.STRICT

    def test_referee_stats_strict_classification(self):
        """Test strict classification (>= 5.0 cards/game)."""
        referee = RefereeStats(name="Strict Referee", cards_per_game=5.2)
        assert referee.strictness == RefereeStrictness.STRICT
        assert referee.is_strict() is True
        assert referee.is_lenient() is False

    def test_referee_stats_medium_classification(self):
        """Test medium classification (3.0-5.0 cards/game)."""
        referee = RefereeStats(name="Medium Referee", cards_per_game=4.0)
        assert referee.strictness == RefereeStrictness.MEDIUM
        assert referee.is_strict() is False
        assert referee.is_lenient() is False

    def test_referee_stats_lenient_classification(self):
        """Test lenient classification (<= 3.0 cards/game)."""
        referee = RefereeStats(name="Lenient Referee", cards_per_game=2.5)
        assert referee.strictness == RefereeStrictness.LENIENT
        assert referee.is_strict() is False
        assert referee.is_lenient() is True

    def test_referee_stats_unknown_classification(self):
        """Test unknown classification (negative cards/game)."""
        referee = RefereeStats(name="Unknown Referee", cards_per_game=-1.0)
        assert referee.strictness == RefereeStrictness.UNKNOWN
        assert referee.is_strict() is False
        assert referee.is_lenient() is False


class TestRefereeStatsBackwardCompatibility:
    """Test backward compatibility with string strictness values."""

    def test_referee_stats_with_lowercase_string(self):
        """Test RefereeStats accepts lowercase string strictness."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=4.0,
            strictness="strict",  # Lowercase string (old format)
        )
        # Should be converted to enum
        assert isinstance(referee.strictness, RefereeStrictness)
        # But auto-classified based on cards_per_game
        assert referee.strictness == RefereeStrictness.MEDIUM

    def test_referee_stats_with_capitalized_string(self):
        """Test RefereeStats accepts capitalized string strictness."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=4.0,
            strictness="Strict",  # Capitalized string (RefereeStrictness enum value)
        )
        # Should be converted to enum
        assert isinstance(referee.strictness, RefereeStrictness)
        # But auto-classified based on cards_per_game
        assert referee.strictness == RefereeStrictness.MEDIUM

    def test_referee_stats_with_average_string(self):
        """Test RefereeStats accepts 'average' string (old format)."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=4.0,
            strictness="average",  # Old format
        )
        # Should be converted to enum
        assert isinstance(referee.strictness, RefereeStrictness)
        # But auto-classified based on cards_per_game
        assert referee.strictness == RefereeStrictness.MEDIUM

    def test_referee_stats_dict_conversion(self):
        """Test converting RefereeStats to dict and back."""
        referee1 = RefereeStats(
            name="Test Referee",
            cards_per_game=4.2,
            strictness=RefereeStrictness.MEDIUM,
            matches_officiated=150,
        )

        # Convert to dict
        referee_dict = dataclasses.asdict(referee1)

        # Verify dict structure
        assert referee_dict["name"] == "Test Referee"
        assert referee_dict["cards_per_game"] == 4.2
        assert referee_dict["strictness"] == RefereeStrictness.MEDIUM
        assert referee_dict["matches_officiated"] == 150

        # Convert back to RefereeStats
        referee2 = RefereeStats(**referee_dict)

        # Verify equality
        assert referee2.name == referee1.name
        assert referee2.cards_per_game == referee1.cards_per_game
        assert referee2.strictness == referee1.strictness
        assert referee2.matches_officiated == referee1.matches_officiated


class TestRefereeCacheIntegration:
    """Test referee_cache integration with RefereeStrictness enum."""

    def test_referee_cache_stores_strictness(self):
        """Test that referee_cache stores referee_strictness separately."""
        import os
        import tempfile

        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = os.path.join(tmp_dir, "referee_stats.json")
            cache = RefereeCache(cache_file=Path(cache_file))

            # Create RefereeStats with enum
            referee = RefereeStats(
                name="Test Referee",
                cards_per_game=5.2,
                strictness=RefereeStrictness.STRICT,
                matches_officiated=150,
            )

            # Convert to dict for cache
            referee_dict = dataclasses.asdict(referee)

            # Store in cache
            cache.set("Test Referee", referee_dict)

            # Retrieve from cache
            cached_stats = cache.get("Test Referee")

            # Verify cache structure
            assert cached_stats is not None
            assert cached_stats["name"] == "Test Referee"
            assert cached_stats["cards_per_game"] == 5.2
            assert cached_stats["strictness"] == RefereeStrictness.STRICT

            # Verify referee_strictness is stored separately
            cache_data = cache._load_cache()
            assert "referee_strictness" in cache_data["Test Referee"]
            assert cache_data["Test Referee"]["referee_strictness"] == RefereeStrictness.STRICT

    def test_referee_cache_with_expired_entry(self):
        """Test referee_cache with expired entries for referee_strictness."""
        import os
        import tempfile

        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = os.path.join(tmp_dir, "referee_stats.json")
            cache = RefereeCache(cache_file=Path(cache_file), ttl_days=1)

            # Create RefereeStats with enum
            referee = RefereeStats(
                name="Test Referee",
                cards_per_game=5.2,
                strictness=RefereeStrictness.STRICT,
                matches_officiated=150,
            )

            # Convert to dict for cache
            referee_dict = dataclasses.asdict(referee)

            # Store in cache
            cache.set("Test Referee", referee_dict)

            # Manually expire the cache entry
            cache_data = cache._load_cache()
            cache_data["Test Referee"]["cached_at"] = (
                datetime.now(timezone.utc) - timedelta(days=2)
            ).isoformat()
            cache._save_cache(cache_data)

            # Try to retrieve - should return None (expired)
            cached_stats = cache.get("Test Referee")
            assert cached_stats is None

    def test_referee_cache_backward_compatibility(self):
        """Test referee_cache backward compatibility with string strictness."""
        import os
        import tempfile

        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = os.path.join(tmp_dir, "referee_stats.json")
            cache = RefereeCache(cache_file=Path(cache_file))

            # Create RefereeStats with string strictness (old format)
            referee_dict = {
                "name": "Test Referee",
                "cards_per_game": 5.2,
                "strictness": "strict",  # Lowercase string (old format)
                "matches_officiated": 150,
            }

            # Store in cache
            cache.set("Test Referee", referee_dict)

            # Retrieve from cache
            cached_stats = cache.get("Test Referee")

            # Verify cache structure
            assert cached_stats is not None
            assert cached_stats["name"] == "Test Referee"
            assert cached_stats["cards_per_game"] == 5.2
            # The strictness should be stored as-is (string)
            assert cached_stats["strictness"] == "strict"

            # Verify referee_strictness is stored separately
            cache_data = cache._load_cache()
            assert cache_data["Test Referee"]["referee_strictness"] == "strict"


class TestRefereeStatsToNotifierIntegration:
    """Test RefereeStats integration with notifier._build_referee_section()."""

    def test_referee_stats_to_dict_for_notifier(self):
        """Test converting RefereeStats to dict for notifier."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=5.2,
            strictness=RefereeStrictness.STRICT,
            matches_officiated=150,
        )

        # Convert to dict (as done in analysis_engine.py)
        referee_intel = dataclasses.asdict(referee)

        # Verify dict structure expected by notifier
        assert isinstance(referee_intel, dict)
        assert referee_intel.get("name") == "Test Referee"
        assert referee_intel.get("cards_per_game") == 5.2
        assert referee_intel.get("strictness") == RefereeStrictness.STRICT
        assert referee_intel.get("matches_officiated") == 150

        # Verify .get() method works (expected by notifier)
        assert referee_intel.get("name", "Unknown") == "Test Referee"
        assert referee_intel.get("strictness", "Unknown") == RefereeStrictness.STRICT

    def test_referee_stats_dict_mapping_for_notifier(self):
        """Test mapping RefereeStats dict to notifier's expected keys."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=5.2,
            strictness=RefereeStrictness.STRICT,
            matches_officiated=150,
        )

        # Convert to dict
        referee_intel = dataclasses.asdict(referee)

        # Map to notifier's expected keys
        mapped_intel = {
            "referee_name": referee_intel.get("name"),
            "referee_cards_avg": referee_intel.get("cards_per_game"),
            "referee_strictness": str(referee_intel.get("strictness")),  # Convert enum to string
            "home_cards_avg": None,
            "away_cards_avg": None,
            "cards_reasoning": "",
        }

        # Verify mapping
        assert mapped_intel["referee_name"] == "Test Referee"
        assert mapped_intel["referee_cards_avg"] == 5.2
        assert mapped_intel["referee_strictness"] == "Strict"  # Enum value as string


class TestRefereeStrictnessEnumValidation:
    """Test RefereeStrictness enum validation in Pydantic models."""

    def test_referee_strictness_enum_values(self):
        """Test RefereeStrictness enum has correct values."""
        assert RefereeStrictness.STRICT.value == "Strict"
        assert RefereeStrictness.MEDIUM.value == "Medium"
        assert RefereeStrictness.LENIENT.value == "Lenient"
        assert RefereeStrictness.UNKNOWN.value == "Unknown"

    def test_referee_strictness_enum_inheritance(self):
        """Test RefereeStrictness enum inherits from str."""
        assert issubclass(RefereeStrictness, str)
        assert isinstance(RefereeStrictness.STRICT, str)
        assert RefereeStrictness.STRICT == "Strict"

    def test_referee_strictness_case_insensitive_validation(self):
        """Test case-insensitive validation in BettingStatsResponse."""
        # Test with capitalized enum value
        response1 = BettingStatsResponse(referee_strictness=RefereeStrictness.STRICT)
        assert response1.referee_strictness == RefereeStrictness.STRICT

        # Test with lowercase string (should be converted to enum)
        response2 = BettingStatsResponse(referee_strictness="strict")
        assert response2.referee_strictness == RefereeStrictness.STRICT

        # Test with mixed case
        response3 = BettingStatsResponse(referee_strictness="StRiCt")
        assert response3.referee_strictness == RefereeStrictness.STRICT

    def test_referee_strictness_unknown_fallback(self):
        """Test unknown strictness falls back to UNKNOWN."""
        response = BettingStatsResponse(referee_strictness="invalid_value")
        assert response.referee_strictness == RefereeStrictness.UNKNOWN


class TestEndToEndRefereeStrictnessFlow:
    """Test end-to-end flow from FotMob → RefereeStats → notifier."""

    def test_complete_flow_from_dict_to_notifier(self):
        """Test complete flow from dict → RefereeStats → dict → notifier."""
        # Step 1: Simulate dict from FotMob/enrichment
        referee_dict = {
            "name": "Test Referee",
            "cards_per_game": 5.2,
            "strictness": "unknown",  # Initial value (will be auto-classified)
            "matches_officiated": 150,
        }

        # Step 2: Convert to RefereeStats (as done in analysis_engine.py)
        referee_stats = RefereeStats(**referee_dict)

        # Verify auto-classification
        assert referee_stats.strictness == RefereeStrictness.STRICT

        # Step 3: Convert to dict for notifier (as done in analysis_engine.py)
        referee_intel = dataclasses.asdict(referee_stats)

        # Verify dict structure
        assert isinstance(referee_intel, dict)
        assert referee_intel["name"] == "Test Referee"
        assert referee_intel["cards_per_game"] == 5.2
        assert referee_intel["strictness"] == RefereeStrictness.STRICT

        # Step 4: Map to notifier's expected keys
        mapped_intel = {
            "referee_name": referee_intel.get("name"),
            "referee_cards_avg": referee_intel.get("cards_per_game"),
            "referee_strictness": str(referee_intel.get("strictness")),
            "home_cards_avg": None,
            "away_cards_avg": None,
            "cards_reasoning": "",
        }

        # Verify final mapping
        assert mapped_intel["referee_name"] == "Test Referee"
        assert mapped_intel["referee_cards_avg"] == 5.2
        assert mapped_intel["referee_strictness"] == "Strict"

    def test_complete_flow_with_cache(self, tmp_path):
        """Test complete flow with cache integration."""
        cache = RefereeCache(cache_file=tmp_path / "referee_stats.json")

        # Step 1: Create RefereeStats
        referee_stats = RefereeStats(
            name="Test Referee",
            cards_per_game=5.2,
            strictness=RefereeStrictness.STRICT,
            matches_officiated=150,
        )

        # Step 2: Store in cache
        referee_dict = dataclasses.asdict(referee_stats)
        cache.set("Test Referee", referee_dict)

        # Step 3: Retrieve from cache
        cached_stats = cache.get("Test Referee")

        # Step 4: Recreate RefereeStats from cache
        referee_stats2 = RefereeStats(**cached_stats)

        # Verify consistency
        assert referee_stats2.name == referee_stats.name
        assert referee_stats2.cards_per_game == referee_stats.cards_per_game
        assert referee_stats2.strictness == referee_stats.strictness

        # Step 5: Convert to dict for notifier
        referee_intel = dataclasses.asdict(referee_stats2)

        # Verify final structure
        assert isinstance(referee_intel, dict)
        assert referee_intel["strictness"] == RefereeStrictness.STRICT


class TestRefereeStrictnessEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_referee_stats_with_zero_cards(self):
        """Test RefereeStats with zero cards per game."""
        referee = RefereeStats(name="Zero Cards Referee", cards_per_game=0.0)
        assert referee.strictness == RefereeStrictness.LENIENT

    def test_referee_stats_with_very_high_cards(self):
        """Test RefereeStats with very high cards per game."""
        referee = RefereeStats(name="Very Strict Referee", cards_per_game=10.0)
        assert referee.strictness == RefereeStrictness.STRICT

    def test_referee_stats_boundary_at_strict_threshold(self):
        """Test RefereeStats at strict threshold (5.0)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=5.0)
        assert referee.strictness == RefereeStrictness.STRICT

    def test_referee_stats_boundary_at_lenient_threshold(self):
        """Test RefereeStats at lenient threshold (3.0)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=3.0)
        assert referee.strictness == RefereeStrictness.LENIENT

    def test_referee_stats_boundary_at_medium_threshold(self):
        """Test RefereeStats at medium threshold (4.0)."""
        referee = RefereeStats(name="Boundary Referee", cards_per_game=4.0)
        assert referee.strictness == RefereeStrictness.MEDIUM

    def test_referee_stats_enum_serialization(self):
        """Test RefereeStrictness enum serialization to JSON."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=5.2,
            strictness=RefereeStrictness.STRICT,
            matches_officiated=150,
        )

        # Convert to dict
        referee_dict = dataclasses.asdict(referee)

        # Verify enum is serialized to string
        assert isinstance(referee_dict["strictness"], str)
        assert referee_dict["strictness"] == "Strict"

    def test_referee_stats_none_strictness(self):
        """Test RefereeStats with None strictness."""
        referee = RefereeStats(
            name="Test Referee",
            cards_per_game=5.2,
            strictness=None,  # None should be handled
            matches_officiated=150,
        )
        # Should be auto-classified
        assert referee.strictness == RefereeStrictness.STRICT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
