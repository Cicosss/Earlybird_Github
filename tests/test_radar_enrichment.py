"""
Test suite for Radar Light Enrichment Module V1.0

Tests:
1. EnrichmentContext dataclass functionality
2. RadarLightEnricher.find_upcoming_match()
3. RadarLightEnricher.get_team_context_light()
4. RadarLightEnricher.check_biscotto_light()
5. Full enrichment flow
6. Edge cases (None team, Unknown team, no match found)
7. Integration with RadarAlert.to_telegram_message()

Author: EarlyBird AI
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestEnrichmentContext:
    """Test EnrichmentContext dataclass."""
    
    def test_default_values(self):
        """Test default initialization."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext()
        
        assert ctx.match_id is None
        assert ctx.home_team is None
        assert ctx.team_zone is None
        assert ctx.is_biscotto_suspect is False
        assert ctx.enrichment_source == "database"
    
    def test_has_match_false_when_no_match(self):
        """Test has_match() returns False when no match_id."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext()
        assert ctx.has_match() is False
    
    def test_has_match_true_when_match_found(self):
        """Test has_match() returns True when match_id present."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(match_id="test_123")
        assert ctx.has_match() is True
    
    def test_is_end_of_season_true(self):
        """Test is_end_of_season() with <= 5 matches remaining."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(matches_remaining=3)
        assert ctx.is_end_of_season() is True
        
        ctx2 = EnrichmentContext(matches_remaining=5)
        assert ctx2.is_end_of_season() is True
    
    def test_is_end_of_season_false(self):
        """Test is_end_of_season() with > 5 matches remaining."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(matches_remaining=10)
        assert ctx.is_end_of_season() is False
        
        ctx2 = EnrichmentContext(matches_remaining=None)
        assert ctx2.is_end_of_season() is False
    
    def test_format_context_line_empty_when_no_match(self):
        """Test format_context_line() returns empty string when no match."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext()
        assert ctx.format_context_line() == ""
    
    def test_format_context_line_with_match(self):
        """Test format_context_line() with match data."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(
            match_id="test_123",
            home_team="Galatasaray",
            away_team="Fenerbahce",
            team_zone="Relegation",
            team_position=18,
            total_teams=20
        )
        
        line = ctx.format_context_line()
        
        assert "Galatasaray vs Fenerbahce" in line
        assert "Zona Retrocessione" in line
        assert "#18/20" in line
    
    def test_format_context_line_with_biscotto(self):
        """Test format_context_line() includes biscotto warning."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(
            match_id="test_123",
            home_team="TeamA",
            away_team="TeamB",
            is_biscotto_suspect=True,
            biscotto_severity="HIGH"
        )
        
        line = ctx.format_context_line()
        
        assert "🍪 BISCOTTO" in line
        assert "HIGH" in line
    
    def test_format_context_line_end_of_season(self):
        """Test format_context_line() includes end of season warning."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(
            match_id="test_123",
            home_team="TeamA",
            away_team="TeamB",
            matches_remaining=3
        )
        
        line = ctx.format_context_line()
        
        assert "Ultime 3 giornate" in line


class TestRadarLightEnricher:
    """Test RadarLightEnricher class."""
    
    def test_enricher_initialization(self):
        """Test enricher initializes correctly."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        # Should have checked dependencies
        assert hasattr(enricher, '_db_available')
        assert hasattr(enricher, '_fotmob_available')
        assert hasattr(enricher, '_biscotto_available')
    
    def test_find_upcoming_match_returns_none_for_empty_team(self):
        """Test find_upcoming_match() returns None for empty team name."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        result = enricher.find_upcoming_match("")
        assert result is None
        
        result2 = enricher.find_upcoming_match(None)
        assert result2 is None
    
    @patch('src.utils.radar_enrichment.RadarLightEnricher._check_dependencies')
    def test_find_upcoming_match_with_mock_db(self, mock_deps):
        """Test find_upcoming_match() with mocked database."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        # Create enricher with mocked DB
        enricher = RadarLightEnricher()
        enricher._db_available = True
        
        # Mock the database query
        mock_match = Mock()
        mock_match.id = "test_match_123"
        mock_match.home_team = "Galatasaray"
        mock_match.away_team = "Fenerbahce"
        mock_match.start_time = datetime.now() + timedelta(hours=24)
        mock_match.league = "soccer_turkey_super_lig"
        mock_match.current_draw_odd = 3.20
        mock_match.opening_draw_odd = 3.50
        
        with patch('src.database.models.SessionLocal') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = [mock_match]
            
            result = enricher.find_upcoming_match("Galatasaray")
            
            # Should find the match
            assert result is not None
            assert result["match_id"] == "test_match_123"
            assert result["home_team"] == "Galatasaray"
            assert result["is_home"] is True
    
    def test_get_team_context_light_returns_unknown_for_empty(self):
        """Test get_team_context_light() returns Unknown for empty team."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        result = enricher.get_team_context_light("")
        assert result["zone"] == "Unknown"
        
        result2 = enricher.get_team_context_light(None)
        assert result2["zone"] == "Unknown"
    
    def test_check_biscotto_light_returns_false_when_not_end_of_season(self):
        """Test check_biscotto_light() returns False when not end of season."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        match_info = {"current_draw_odd": 2.50}
        team_context = {"matches_remaining": 15}  # Not end of season
        
        is_suspect, severity = enricher.check_biscotto_light(match_info, team_context)
        
        assert is_suspect is False
        assert severity is None
    
    def test_check_biscotto_light_returns_false_when_no_draw_odd(self):
        """Test check_biscotto_light() returns False when no draw odds."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        match_info = {"current_draw_odd": None}
        team_context = {"matches_remaining": 3}  # End of season
        
        is_suspect, severity = enricher.check_biscotto_light(match_info, team_context)
        
        assert is_suspect is False
        assert severity is None
    
    def test_enrich_returns_empty_context_for_unknown_team(self):
        """Test enrich() returns empty context for Unknown team."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        result = enricher.enrich("Unknown")
        
        assert result.has_match() is False
    
    def test_enrich_returns_empty_context_for_none_team(self):
        """Test enrich() returns empty context for None team."""
        from src.utils.radar_enrichment import RadarLightEnricher
        
        enricher = RadarLightEnricher()
        
        result = enricher.enrich(None)
        
        assert result.has_match() is False


class TestSingletonPattern:
    """Test singleton pattern for enricher."""
    
    def test_get_radar_enricher_returns_same_instance(self):
        """Test get_radar_enricher() returns singleton."""
        from src.utils.radar_enrichment import get_radar_enricher
        
        enricher1 = get_radar_enricher()
        enricher2 = get_radar_enricher()
        
        assert enricher1 is enricher2


class TestRadarAlertIntegration:
    """Test integration with RadarAlert."""
    
    def test_radar_alert_with_enrichment_context(self):
        """Test RadarAlert.to_telegram_message() includes enrichment."""
        from src.services.news_radar import RadarAlert
        from src.utils.radar_enrichment import EnrichmentContext
        
        # Create enrichment context
        ctx = EnrichmentContext(
            match_id="test_123",
            home_team="Galatasaray",
            away_team="Fenerbahce",
            team_zone="Relegation",
            team_position=18,
            total_teams=20,
            matches_remaining=3,
            is_biscotto_suspect=True,
            biscotto_severity="HIGH"
        )
        
        # Create alert with enrichment
        alert = RadarAlert(
            source_name="Test Source",
            source_url="https://example.com",
            affected_team="Galatasaray",
            category="INJURY",
            summary="Icardi out for 3 weeks",
            confidence=0.85,
            enrichment_context=ctx
        )
        
        message = alert.to_telegram_message()
        
        # Should include enrichment info
        assert "Galatasaray vs Fenerbahce" in message
        assert "Zona Retrocessione" in message or "Relegation" in message
        assert "BISCOTTO" in message
    
    def test_radar_alert_without_enrichment_context(self):
        """Test RadarAlert.to_telegram_message() works without enrichment."""
        from src.services.news_radar import RadarAlert
        
        alert = RadarAlert(
            source_name="Test Source",
            source_url="https://example.com",
            affected_team="Galatasaray",
            category="INJURY",
            summary="Icardi out for 3 weeks",
            confidence=0.85,
            enrichment_context=None
        )
        
        message = alert.to_telegram_message()
        
        # Should still work
        assert "RADAR ALERT" in message
        assert "Galatasaray" in message
        assert "Icardi out" in message


class TestAsyncEnrichment:
    """Test async enrichment wrapper."""
    
    @pytest.mark.asyncio
    async def test_enrich_radar_alert_async(self):
        """Test async enrichment wrapper."""
        from src.utils.radar_enrichment import enrich_radar_alert_async
        
        # Should not raise even with unknown team
        result = await enrich_radar_alert_async("Unknown Team XYZ")
        
        assert result is not None
        assert result.has_match() is False  # No match expected for fake team


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_enrichment_context_translate_zone(self):
        """Test zone translation to Italian."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext()
        
        assert ctx._translate_zone("Title Race") == "Lotta Scudetto"
        assert ctx._translate_zone("Relegation") == "Zona Retrocessione"
        assert ctx._translate_zone("Unknown Zone") == "Unknown Zone"  # Passthrough
    
    def test_format_context_line_with_unknown_zone(self):
        """Test format_context_line() handles Unknown zone gracefully."""
        from src.utils.radar_enrichment import EnrichmentContext
        
        ctx = EnrichmentContext(
            match_id="test_123",
            home_team="TeamA",
            away_team="TeamB",
            team_zone="Unknown"
        )
        
        line = ctx.format_context_line()
        
        # Should not include "Unknown" or "Sconosciuto"
        assert "Unknown" not in line
        assert "Sconosciuto" not in line
        # But should still have match info
        assert "TeamA vs TeamB" in line
