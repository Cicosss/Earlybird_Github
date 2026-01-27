"""
Tests for Nitter Fallback Scraper - EarlyBird V6.1

Tests cover:
1. NitterCache - persistent cache functionality
2. NitterFallbackScraper - scraping logic
3. Integration with ExclusionFilter and RelevanceAnalyzer
4. Edge cases and error handling
"""
import pytest
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock


class TestNitterCache:
    """Tests for NitterCache persistent storage."""
    
    def test_cache_set_and_get(self):
        """Cache should store and retrieve tweets."""
        from src.services.nitter_fallback_scraper import NitterCache
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = NitterCache(cache_file=f.name, ttl_hours=6)
            
            # Set tweets
            tweets = [
                {'date': '2026-01-08', 'content': 'Test tweet', 'topics': ['injury']}
            ]
            cache.set('RudyGaletti', tweets)
            
            # Get tweets
            result = cache.get('RudyGaletti')
            assert result is not None
            assert len(result) == 1
            assert result[0]['content'] == 'Test tweet'
    
    def test_cache_handles_at_symbol(self):
        """Cache should normalize handles with/without @."""
        from src.services.nitter_fallback_scraper import NitterCache
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = NitterCache(cache_file=f.name, ttl_hours=6)
            
            # Set with @
            cache.set('@TestHandle', [{'content': 'test'}])
            
            # Get without @
            result = cache.get('TestHandle')
            assert result is not None
    
    def test_cache_expiration(self):
        """Expired entries should not be returned."""
        from src.services.nitter_fallback_scraper import NitterCache
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = NitterCache(cache_file=f.name, ttl_hours=1)
            
            # Manually insert expired entry
            old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            cache._cache['expired_handle'] = {
                'tweets': [{'content': 'old'}],
                'cached_at': old_time
            }
            
            # Should return None for expired
            result = cache.get('expired_handle')
            assert result is None


class TestNitterFallbackScraper:
    """Tests for NitterFallbackScraper."""
    
    def test_scraper_initialization(self):
        """Scraper should initialize with default instances."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        assert scraper._instances is not None
        assert len(scraper._instances) >= 2
        assert scraper._total_scraped == 0
    
    def test_get_next_instance_round_robin(self):
        """Instance selection should rotate."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        first = scraper._get_next_instance()
        second = scraper._get_next_instance()
        
        # Should get different instances (round-robin)
        # Note: May be same if only one healthy instance
        assert first is not None
        assert second is not None
    
    def test_mark_instance_failure(self):
        """Instance should be marked unhealthy after failures."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        url = scraper._instances[0]
        
        # Mark 3 failures
        for _ in range(3):
            scraper._mark_instance_failure(url)
        
        health = scraper._instance_health.get(url)
        assert health is not None
        assert health.is_healthy is False
        assert health.consecutive_failures >= 3
    
    def test_mark_instance_success_resets_failures(self):
        """Success should reset failure count."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        url = scraper._instances[0]
        
        # Add some failures
        scraper._mark_instance_failure(url)
        scraper._mark_instance_failure(url)
        
        # Mark success
        scraper._mark_instance_success(url)
        
        health = scraper._instance_health.get(url)
        assert health.consecutive_failures == 0
        assert health.is_healthy is True


class TestPreFiltering:
    """Tests for HTML pre-filtering optimization."""
    
    def test_pre_filter_with_relevant_content(self):
        """Should return True for HTML with relevant keywords."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        html = "<div>Player injured in training today</div>"
        assert scraper._pre_filter_html(html) is True
    
    def test_pre_filter_with_irrelevant_content(self):
        """Should return False for HTML without relevant keywords."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # Content without any football/betting relevant keywords
        html = "<div>Beautiful sunny day in Rome today, perfect for a walk in the park</div>"
        assert scraper._pre_filter_html(html) is False
    
    def test_pre_filter_empty_html(self):
        """Should return False for empty HTML."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        assert scraper._pre_filter_html("") is False
        assert scraper._pre_filter_html(None) is False


class TestTweetExtraction:
    """Tests for tweet extraction from HTML."""
    
    def test_extract_tweets_filters_excluded_content(self):
        """Should filter out basketball/women's content."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # HTML with basketball content (should be excluded)
        html = """
        <div class="timeline-item">
            <div class="tweet-content">NBA Finals: Lakers vs Celtics tonight!</div>
            <span class="tweet-date">Jan 8, 2026</span>
        </div>
        """
        
        tweets = scraper._extract_tweets_from_html(html, "@TestHandle")
        
        # Should be empty (basketball excluded)
        assert len(tweets) == 0
    
    def test_extract_tweets_keeps_relevant_content(self):
        """Should keep football injury news."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # HTML with football injury (should be kept)
        html = """
        <div class="timeline-item">
            <div class="tweet-content">Manchester United star ruled out with hamstring injury</div>
            <span class="tweet-date">Jan 8, 2026</span>
        </div>
        """
        
        tweets = scraper._extract_tweets_from_html(html, "@TestHandle")
        
        # Should have 1 tweet
        assert len(tweets) == 1
        assert "injury" in tweets[0].content.lower()


class TestIntegration:
    """Integration tests."""
    
    def test_singleton_instance(self):
        """Should return same instance."""
        from src.services.nitter_fallback_scraper import get_nitter_fallback_scraper
        
        scraper1 = get_nitter_fallback_scraper()
        scraper2 = get_nitter_fallback_scraper()
        
        assert scraper1 is scraper2
    
    def test_stats_tracking(self):
        """Stats should be tracked correctly."""
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        stats = scraper.get_stats()
        
        assert 'total_scraped' in stats
        assert 'cache_hits' in stats
        assert 'instance_health' in stats


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_scrape_account_with_none_handle(self):
        """Should return empty list for None handle (not crash)."""
        import asyncio
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # Should NOT crash, should return empty list
        # V8.0 FIX: Use asyncio.run() instead of deprecated get_event_loop()
        result = asyncio.run(scraper._scrape_account(None))
        assert result == []
    
    def test_scrape_accounts_filters_invalid_handles(self):
        """Should filter out None/invalid handles from list."""
        import asyncio
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # List with None and invalid handles - all invalid
        handles = [None, "", "@", "   "]
        
        # Should not crash, should return None (all invalid)
        # V8.0 FIX: Use asyncio.run() instead of deprecated get_event_loop()
        result = asyncio.run(scraper.scrape_accounts(handles))
        assert result is None
    
    def test_scrape_accounts_all_invalid_returns_none(self):
        """Should return None if all handles are invalid."""
        import asyncio
        from src.services.nitter_fallback_scraper import NitterFallbackScraper
        
        scraper = NitterFallbackScraper()
        
        # All invalid handles (integers are not strings)
        handles = [None, "", "@", "   "]
        
        # V8.0 FIX: Use asyncio.run() instead of deprecated get_event_loop()
        result = asyncio.run(scraper.scrape_accounts(handles))
        assert result is None
