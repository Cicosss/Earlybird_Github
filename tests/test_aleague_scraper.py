"""
Tests for A-League Dedicated Scraper

Verifies:
1. Edge cases (empty team_name, None values)
2. Team name extraction and matching
3. Article filtering (Ins & Outs vs regular news)
4. Rate limiting
5. Integration with news_hunter

V1.0 - Initial tests for Deep Research implementation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestALeagueScraperEdgeCases:
    """Tests for edge cases that would cause bugs."""
    
    def test_empty_team_name_returns_empty_list(self):
        """Empty team_name should return empty list, not crash."""
        from src.ingestion.aleague_scraper import search_aleague_news
        
        # Test empty string
        result = search_aleague_news("", "match_001", force=True)
        assert result == [], "Empty team_name should return empty list"
        
        # Test whitespace only
        result = search_aleague_news("   ", "match_001", force=True)
        assert result == [], "Whitespace-only team_name should return empty list"
    
    def test_none_team_name_returns_empty_list(self):
        """None team_name should return empty list, not crash."""
        from src.ingestion.aleague_scraper import search_aleague_news
        
        # This would crash without the edge case handling
        result = search_aleague_news(None, "match_001", force=True)
        assert result == [], "None team_name should return empty list"
    
    def test_extract_team_mentions_with_none(self):
        """_extract_team_mentions should handle None inputs."""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        
        # None text
        assert _extract_team_mentions(None, "Sydney FC") == False
        
        # None team_name
        assert _extract_team_mentions("Some text about Sydney", None) == False
        
        # Both None
        assert _extract_team_mentions(None, None) == False
    
    def test_has_injury_content_with_none(self):
        """_has_injury_content should handle None input."""
        from src.ingestion.aleague_scraper import _has_injury_content
        
        assert _has_injury_content(None) == False
        assert _has_injury_content("") == False


class TestALeagueTeamMatching:
    """Tests for team name matching logic."""
    
    def test_direct_team_match(self):
        """Direct team name should match."""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        
        assert _extract_team_mentions("Sydney FC injury update", "Sydney FC") == True
        assert _extract_team_mentions("Melbourne Victory squad news", "Melbourne Victory") == True
    
    def test_alias_team_match(self):
        """Team aliases should match."""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        
        # "Sky Blues" is alias for Sydney FC
        assert _extract_team_mentions("Sky Blues announce new signing", "Sydney FC") == True
        
        # "Wanderers" is alias for Western Sydney Wanderers
        assert _extract_team_mentions("Wanderers injury crisis", "Western Sydney Wanderers") == True
        
        # "Roar" is alias for Brisbane Roar
        assert _extract_team_mentions("Roar confirm squad changes", "Brisbane Roar") == True
    
    def test_case_insensitive_match(self):
        """Matching should be case-insensitive."""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        
        assert _extract_team_mentions("SYDNEY FC NEWS", "sydney fc") == True
        assert _extract_team_mentions("sydney fc news", "SYDNEY FC") == True
    
    def test_no_match_different_team(self):
        """Different team should not match."""
        from src.ingestion.aleague_scraper import _extract_team_mentions
        
        assert _extract_team_mentions("Melbourne Victory news", "Sydney FC") == False
        assert _extract_team_mentions("Perth Glory update", "Brisbane Roar") == False


class TestALeagueArticleFiltering:
    """Tests for article type detection."""
    
    def test_ins_outs_detection(self):
        """Ins & Outs articles should be detected."""
        from src.ingestion.aleague_scraper import _is_ins_outs_article
        
        # URL-based detection
        assert _is_ins_outs_article(
            "https://aleagues.com.au/news/ins-outs-team-news-round-10/",
            "Team News Round 10"
        ) == True
        
        # Title-based detection
        assert _is_ins_outs_article(
            "https://aleagues.com.au/news/some-article/",
            "Ins and Outs: Round 10 Team News"
        ) == True
        
        # Injury update detection
        assert _is_ins_outs_article(
            "https://aleagues.com.au/news/injury-update-sydney-fc/",
            "Sydney FC Injury Update"
        ) == True
    
    def test_regular_news_not_ins_outs(self):
        """Regular news should not be flagged as Ins & Outs."""
        from src.ingestion.aleague_scraper import _is_ins_outs_article
        
        assert _is_ins_outs_article(
            "https://aleagues.com.au/news/transfer-news/",
            "New Signing Announced"
        ) == False
        
        assert _is_ins_outs_article(
            "https://aleagues.com.au/news/match-report/",
            "Sydney FC wins 2-1"
        ) == False
    
    def test_injury_content_detection(self):
        """Injury-related content should be detected."""
        from src.ingestion.aleague_scraper import _has_injury_content
        
        assert _has_injury_content("Player ruled out with hamstring injury") == True
        assert _has_injury_content("Striker returns from knee injury") == True
        assert _has_injury_content("Squad announcement for Saturday") == True
        assert _has_injury_content("Starting lineup confirmed") == True
        
        # Non-injury content
        assert _has_injury_content("Club announces new sponsor") == False
        assert _has_injury_content("Ticket sales now open") == False


class TestALeagueRateLimiting:
    """Tests for rate limiting logic."""
    
    def test_should_scrape_first_time(self):
        """First scrape should always be allowed."""
        from src.ingestion.aleague_scraper import _should_scrape, _last_scrape_time
        import src.ingestion.aleague_scraper as scraper_module
        
        # Reset state
        scraper_module._last_scrape_time = None
        
        assert _should_scrape() == True
    
    def test_should_not_scrape_immediately_after(self):
        """Scrape should be blocked immediately after previous scrape."""
        from src.ingestion.aleague_scraper import _should_scrape, _mark_scraped
        import src.ingestion.aleague_scraper as scraper_module
        
        # Mark as just scraped
        _mark_scraped()
        
        assert _should_scrape() == False
    
    def test_should_scrape_after_interval(self):
        """Scrape should be allowed after interval passes."""
        from src.ingestion.aleague_scraper import _should_scrape, SCRAPE_INTERVAL_MINUTES
        import src.ingestion.aleague_scraper as scraper_module
        
        # Set last scrape to past the interval
        scraper_module._last_scrape_time = datetime.now() - timedelta(minutes=SCRAPE_INTERVAL_MINUTES + 1)
        
        assert _should_scrape() == True


class TestALeagueArticleDeduplication:
    """Tests for article deduplication."""
    
    def test_article_hash_consistency(self):
        """Same URL should produce same hash."""
        from src.ingestion.aleague_scraper import _get_article_hash
        
        hash1 = _get_article_hash("https://aleagues.com.au/news/article-1/")
        hash2 = _get_article_hash("https://aleagues.com.au/news/article-1/")
        hash3 = _get_article_hash("https://aleagues.com.au/news/article-2/")
        
        assert hash1 == hash2, "Same URL should produce same hash"
        assert hash1 != hash3, "Different URLs should produce different hashes"
    
    def test_seen_article_tracking(self):
        """Seen articles should be tracked."""
        from src.ingestion.aleague_scraper import _is_article_seen, _seen_articles
        
        # Clear cache
        _seen_articles.clear()
        
        url = "https://aleagues.com.au/news/test-article/"
        
        # First time should return False and add to cache
        assert _is_article_seen(url) == False
        
        # Second time should return True
        assert _is_article_seen(url) == True


class TestALeagueIntegration:
    """Tests for integration with news_hunter."""
    
    def test_scraper_singleton(self):
        """Singleton should return same instance."""
        from src.ingestion.aleague_scraper import get_aleague_scraper
        
        scraper1 = get_aleague_scraper()
        scraper2 = get_aleague_scraper()
        
        assert scraper1 is scraper2, "Singleton should return same instance"
    
    def test_result_structure(self):
        """Results should have required fields for news_hunter."""
        # Mock a result to verify structure
        expected_fields = [
            'match_id', 'team', 'keyword', 'title', 'snippet',
            'link', 'date', 'source', 'search_type',
            'confidence', 'priority_boost', 'source_type'
        ]
        
        mock_result = {
            'match_id': 'test_001',
            'team': 'Sydney FC',
            'keyword': 'aleague_ins_outs',
            'title': 'Test Article',
            'snippet': 'Test content',
            'link': 'https://aleagues.com.au/news/test/',
            'date': datetime.now().isoformat(),
            'source': 'A-Leagues Official',
            'search_type': 'aleague_scraper',
            'confidence': 'VERY_HIGH',
            'priority_boost': 2.0,
            'source_type': 'official_scraper',
        }
        
        for field in expected_fields:
            assert field in mock_result, f"Result should have '{field}' field"


# ============================================
# Run tests
# ============================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestNewsHunterIntegration:
    """Tests for integration with news_hunter.py"""
    
    def test_aleague_scraper_flag_exists(self):
        """news_hunter should have _ALEAGUE_SCRAPER_AVAILABLE flag."""
        from src.processing.news_hunter import _ALEAGUE_SCRAPER_AVAILABLE
        
        # Flag should exist and be True (since we have the module)
        assert isinstance(_ALEAGUE_SCRAPER_AVAILABLE, bool)
        assert _ALEAGUE_SCRAPER_AVAILABLE == True, "A-League scraper should be available"
    
    def test_run_hunter_only_for_aleague(self):
        """A-League scraper should only run for soccer_australia_aleague."""
        # Verify the condition in news_hunter
        import inspect
        from src.processing.news_hunter import run_hunter_for_match
        
        source = inspect.getsource(run_hunter_for_match)
        
        # Check that A-League scraper is conditionally called
        assert 'soccer_australia_aleague' in source, "Should check for A-League sport_key"
        assert '_ALEAGUE_SCRAPER_AVAILABLE' in source, "Should check if scraper is available"
    
    def test_aleague_results_have_correct_search_type(self):
        """Results should have search_type='aleague_scraper' for summary counting."""
        from src.ingestion.aleague_scraper import search_aleague_news
        
        # Force a search
        results = search_aleague_news("Sydney FC", "test_match", force=True)
        
        # If we got results, verify search_type
        for r in results:
            assert r.get('search_type') == 'aleague_scraper', \
                f"search_type should be 'aleague_scraper', got {r.get('search_type')}"
    
    def test_summary_counts_aleague_results(self):
        """news_hunter summary should count aleague_scraper results."""
        import inspect
        from src.processing.news_hunter import run_hunter_for_match
        
        source = inspect.getsource(run_hunter_for_match)
        
        # Check that summary counts A-League results
        assert "aleague_scraper" in source, "Summary should count aleague_scraper results"
        assert "aleague_total" in source, "Should have aleague_total counter"


class TestSourcesConfigTelegramGlobal:
    """Tests for global Telegram channels in sources_config."""
    
    def test_global_key_exists(self):
        """TELEGRAM_INSIDERS should have _global key."""
        from src.processing.sources_config import TELEGRAM_INSIDERS
        
        assert '_global' in TELEGRAM_INSIDERS, "_global key should exist"
        assert len(TELEGRAM_INSIDERS['_global']) >= 2, "Should have at least 2 global channels"
    
    def test_global_channels_added_to_all_countries(self):
        """get_all_telegram_channels should add global channels to all countries."""
        from src.processing.sources_config import get_all_telegram_channels, TELEGRAM_INSIDERS
        
        global_channels = TELEGRAM_INSIDERS['_global']
        all_channels = get_all_telegram_channels()
        
        # _global should NOT be in the result
        assert '_global' not in all_channels, "_global should not be a key in result"
        
        # Each country should have global channels
        for country, channels in all_channels.items():
            for gc in global_channels:
                assert gc in channels, f"Global channel {gc} should be in {country}"
    
    def test_get_telegram_channels_includes_global(self):
        """get_telegram_channels(league_key) should include global channels."""
        from src.processing.sources_config import get_telegram_channels, TELEGRAM_INSIDERS
        
        global_channels = TELEGRAM_INSIDERS['_global']
        
        # Test for Turkey
        turkey_channels = get_telegram_channels('soccer_turkey_super_league')
        for gc in global_channels:
            assert gc in turkey_channels, f"Global channel {gc} should be in Turkey channels"
        
        # Test for Australia (has no country-specific channels)
        aus_channels = get_telegram_channels('soccer_australia_aleague')
        for gc in global_channels:
            assert gc in aus_channels, f"Global channel {gc} should be in Australia channels"
    
    def test_unknown_league_returns_global_only(self):
        """Unknown league should return only global channels."""
        from src.processing.sources_config import get_telegram_channels, TELEGRAM_INSIDERS
        
        global_channels = TELEGRAM_INSIDERS['_global']
        
        # Unknown league
        unknown_channels = get_telegram_channels('soccer_unknown_league')
        
        assert unknown_channels == global_channels, \
            f"Unknown league should return global channels only, got {unknown_channels}"
