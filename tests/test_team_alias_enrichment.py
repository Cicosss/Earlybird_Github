"""
TeamAlias Enrichment Tests

Tests for the TeamAlias enrichment system.
"""

# Add parent directory to path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "/home/linux/Earlybird_Github")

from src.database.team_alias_enrichment import (
    add_team_mapping,
    enrich_team_alias_data,
    get_all_mapped_teams,
    get_fotmob_id,
    get_team_country,
    get_team_league,
    get_team_mapping_stats,
    get_telegram_channel,
    get_twitter_handle,
)


class TestTwitterHandleMapping:
    """Test Twitter handle mapping."""

    def test_get_twitter_handle_existing(self):
        """Test getting Twitter handle for existing team."""
        handle = get_twitter_handle("Galatasaray")
        assert handle == "@GalatasaraySK"

    def test_get_twitter_handle_case_insensitive(self):
        """Test case-insensitive Twitter handle lookup."""
        handle = get_twitter_handle("galatasaray")
        assert handle == "@GalatasaraySK"

    def test_get_twitter_handle_not_found(self):
        """Test getting Twitter handle for non-existent team."""
        handle = get_twitter_handle("Unknown Team")
        assert handle is None


class TestTelegramChannelMapping:
    """Test Telegram channel mapping."""

    def test_get_telegram_channel_existing(self):
        """Test getting Telegram channel for existing team."""
        channel = get_telegram_channel("Galatasaray")
        assert channel == "galatasaray"

    def test_get_telegram_channel_case_insensitive(self):
        """Test case-insensitive Telegram channel lookup."""
        channel = get_telegram_channel("galatasaray")
        assert channel == "galatasaray"

    def test_get_telegram_channel_not_found(self):
        """Test getting Telegram channel for non-existent team."""
        channel = get_telegram_channel("Unknown Team")
        assert channel is None


class TestFotMobIdMapping:
    """Test FotMob ID mapping."""

    def test_get_fotmob_id_existing(self):
        """Test getting FotMob ID for existing team."""
        fotmob_id = get_fotmob_id("Galatasaray")
        assert fotmob_id == 8601

    def test_get_fotmob_id_case_insensitive(self):
        """Test case-insensitive FotMob ID lookup."""
        fotmob_id = get_fotmob_id("galatasaray")
        assert fotmob_id == 8601

    def test_get_fotmob_id_not_found(self):
        """Test getting FotMob ID for non-existent team."""
        fotmob_id = get_fotmob_id("Unknown Team")
        assert fotmob_id is None

    @patch("src.database.team_alias_enrichment.get_fotmob_team_id")
    def test_get_fotmob_id_fallback_to_mapping_file(self, mock_get_fotmob_team_id):
        """Test fallback to fotmob_team_mapping.py when not in local cache."""
        mock_get_fotmob_team_id.return_value = 12345

        fotmob_id = get_fotmob_id("Unknown Team")
        assert fotmob_id == 12345
        mock_get_fotmob_team_id.assert_called_once_with("Unknown Team")


class TestCountryMapping:
    """Test country mapping."""

    def test_get_team_country_existing(self):
        """Test getting country for existing team."""
        country = get_team_country("Galatasaray")
        assert country == "turkey"

    def test_get_team_country_case_insensitive(self):
        """Test case-insensitive country lookup."""
        country = get_team_country("galatasaray")
        assert country == "turkey"

    def test_get_team_country_not_found(self):
        """Test getting country for non-existent team."""
        country = get_team_country("Unknown Team")
        assert country is None


class TestLeagueMapping:
    """Test league mapping."""

    def test_get_team_league_existing(self):
        """Test getting league for existing team."""
        league = get_team_league("Galatasaray")
        assert league == "soccer_turkey_super_league"

    def test_get_team_league_case_insensitive(self):
        """Test case-insensitive league lookup."""
        league = get_team_league("galatasaray")
        assert league == "soccer_turkey_super_league"

    def test_get_team_league_not_found(self):
        """Test getting league for non-existent team."""
        league = get_team_league("Unknown Team")
        assert league is None


class TestEnrichTeamAliasData:
    """Test enrich_team_alias_data function."""

    def test_enrich_team_alias_data_complete(self):
        """Test enriching team with all available data."""
        data = enrich_team_alias_data("Galatasaray")

        assert data["twitter_handle"] == "@GalatasaraySK"
        assert data["telegram_channel"] == "galatasaray"
        assert data["fotmob_id"] == 8601
        assert data["country"] == "turkey"
        assert data["league"] == "soccer_turkey_super_league"

    def test_enrich_team_alias_data_partial(self):
        """Test enriching team with partial data."""
        data = enrich_team_alias_data("Boca Juniors")

        assert data["twitter_handle"] == "@BocaJrsOficial"
        assert data["telegram_channel"] == "infoboca"
        assert data["country"] == "argentina"
        assert data["league"] == "soccer_argentina_primera_division"
        # FotMob ID might not be available
        assert data["fotmob_id"] is None or isinstance(data["fotmob_id"], int)

    def test_enrich_team_alias_data_empty(self):
        """Test enriching team with no available data."""
        data = enrich_team_alias_data("Unknown Team")

        assert data["twitter_handle"] is None
        assert data["telegram_channel"] is None
        assert data["fotmob_id"] is None
        assert data["country"] is None
        assert data["league"] is None


class TestAddTeamMapping:
    """Test add_team_mapping function."""

    def test_add_twitter_handle(self):
        """Test adding Twitter handle mapping."""
        add_team_mapping("Test Team", twitter_handle="@TestTeam")

        handle = get_twitter_handle("Test Team")
        assert handle == "@TestTeam"

    def test_add_telegram_channel(self):
        """Test adding Telegram channel mapping."""
        add_team_mapping("Test Team 2", telegram_channel="testteam2")

        channel = get_telegram_channel("Test Team 2")
        assert channel == "testteam2"

    def test_add_fotmob_id(self):
        """Test adding FotMob ID mapping."""
        add_team_mapping("Test Team 3", fotmob_id=99999)

        fotmob_id = get_fotmob_id("Test Team 3")
        assert fotmob_id == 99999

    def test_add_country(self):
        """Test adding country mapping."""
        add_team_mapping("Test Team 4", country="test_country")

        country = get_team_country("Test Team 4")
        assert country == "test_country"

    def test_add_league(self):
        """Test adding league mapping."""
        add_team_mapping("Test Team 5", league="soccer_test_league")

        league = get_team_league("Test Team 5")
        assert league == "soccer_test_league"

    def test_add_multiple_mappings(self):
        """Test adding multiple mappings at once."""
        add_team_mapping(
            "Test Team 6",
            twitter_handle="@TestTeam6",
            telegram_channel="testteam6",
            fotmob_id=88888,
            country="test_country_6",
            league="soccer_test_league_6",
        )

        assert get_twitter_handle("Test Team 6") == "@TestTeam6"
        assert get_telegram_channel("Test Team 6") == "testteam6"
        assert get_fotmob_id("Test Team 6") == 88888
        assert get_team_country("Test Team 6") == "test_country_6"
        assert get_team_league("Test Team 6") == "soccer_test_league_6"


class TestGetAllMappedTeams:
    """Test get_all_mapped_teams function."""

    def test_get_all_mapped_teams(self):
        """Test getting all mapped teams."""
        teams = get_all_mapped_teams()

        assert isinstance(teams, list)
        assert len(teams) > 0
        assert "Galatasaray" in teams
        assert "Boca Juniors" in teams


class TestGetTeamMappingStats:
    """Test get_team_mapping_stats function."""

    def test_get_team_mapping_stats(self):
        """Test getting mapping statistics."""
        stats = get_team_mapping_stats()

        assert isinstance(stats, dict)
        assert "total_teams" in stats
        assert "twitter_handles" in stats
        assert "telegram_channels" in stats
        assert "fotmob_ids" in stats
        assert "countries" in stats
        assert "leagues" in stats

        # Verify counts are non-negative
        assert stats["total_teams"] >= 0
        assert stats["twitter_handles"] >= 0
        assert stats["telegram_channels"] >= 0
        assert stats["fotmob_ids"] >= 0
        assert stats["countries"] >= 0
        assert stats["leagues"] >= 0

        # Verify total_teams is the union of all mappings
        assert stats["total_teams"] >= stats["twitter_handles"]
        assert stats["total_teams"] >= stats["telegram_channels"]
        assert stats["total_teams"] >= stats["fotmob_ids"]
        assert stats["total_teams"] >= stats["countries"]
        assert stats["total_teams"] >= stats["leagues"]


class TestIntegrationWithDatabase:
    """Integration tests with database operations."""

    @patch("src.database.db.get_db_context")
    def test_ensure_alias_creates_enriched_alias(self, mock_get_db_context):
        """Test that _ensure_alias creates enriched TeamAlias."""
        from src.database.db import _ensure_alias
        from src.database.models import TeamAlias

        # Setup mock session
        mock_session = MagicMock()
        mock_get_db_context.return_value.__enter__.return_value = mock_session

        # Mock query to return None (team doesn't exist)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Call _ensure_alias
        _ensure_alias(mock_session, "Galatasaray")

        # Verify TeamAlias was created with enriched data
        assert mock_session.add.called
        added_alias = mock_session.add.call_args[0][0]

        assert isinstance(added_alias, TeamAlias)
        assert added_alias.api_name == "Galatasaray"
        assert added_alias.search_name == "Galatasaray"
        assert added_alias.twitter_handle == "@GalatasaraySK"
        assert added_alias.telegram_channel == "galatasaray"
        assert added_alias.fotmob_id == "8601"
        assert added_alias.country == "turkey"
        assert added_alias.league == "soccer_turkey_super_league"

    @patch("src.database.db.get_db_context")
    def test_ensure_alias_skips_existing_alias(self, mock_get_db_context):
        """Test that _ensure_alias skips existing TeamAlias."""
        from src.database.db import _ensure_alias

        # Setup mock session
        mock_session = MagicMock()
        mock_get_db_context.return_value.__enter__.return_value = mock_session

        # Mock query to return existing alias
        mock_alias = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_alias

        # Call _ensure_alias
        _ensure_alias(mock_session, "Galatasaray")

        # Verify TeamAlias was NOT created
        assert not mock_session.add.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
