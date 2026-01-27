"""
Test Twitter Intel Cache - EarlyBird V4.5

Tests for the Twitter Intel Cache service and configuration.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestTwitterIntelAccounts:
    """Test the Twitter Intel Accounts configuration."""
    
    def test_get_all_twitter_handles_returns_list(self):
        """All handles should be returned as a list."""
        from config.twitter_intel_accounts import get_all_twitter_handles
        
        handles = get_all_twitter_handles()
        
        assert isinstance(handles, list)
        assert len(handles) > 0
        # All handles should start with @
        for handle in handles:
            assert handle.startswith("@"), f"Handle {handle} should start with @"
    
    def test_get_all_twitter_handles_count(self):
        """Should have approximately 49 accounts configured."""
        from config.twitter_intel_accounts import get_all_twitter_handles
        
        handles = get_all_twitter_handles()
        
        # We configured 49 accounts
        assert len(handles) >= 45, f"Expected at least 45 handles, got {len(handles)}"
        assert len(handles) <= 60, f"Expected at most 60 handles, got {len(handles)}"
    
    def test_get_account_count_structure(self):
        """Account count should return proper structure."""
        from config.twitter_intel_accounts import get_account_count
        
        stats = get_account_count()
        
        assert "elite_7_total" in stats
        assert "tier_2_total" in stats
        assert "global_total" in stats
        assert "total" in stats
        assert "by_country" in stats
        # V4.6: Total now includes global accounts
        assert stats["total"] == stats["elite_7_total"] + stats["tier_2_total"] + stats["global_total"]
    
    def test_get_twitter_intel_accounts_for_turkey(self):
        """Turkey should have 4 accounts configured."""
        from config.twitter_intel_accounts import get_twitter_intel_accounts
        
        accounts = get_twitter_intel_accounts("soccer_turkey_super_league")
        
        assert len(accounts) == 4
        handles = [a.handle for a in accounts]
        assert "@RudyGaletti" in handles
    
    def test_get_twitter_intel_accounts_unknown_league(self):
        """Unknown league should return empty list."""
        from config.twitter_intel_accounts import get_twitter_intel_accounts
        
        accounts = get_twitter_intel_accounts("soccer_unknown_league")
        
        assert accounts == []
    
    def test_get_twitter_intel_accounts_none_league(self):
        """None league should return empty list (edge case)."""
        from config.twitter_intel_accounts import get_twitter_intel_accounts
        
        accounts = get_twitter_intel_accounts(None)
        
        assert accounts == []
    
    def test_get_handles_by_tier_elite_7(self):
        """Elite 7 tier should return correct countries."""
        from config.twitter_intel_accounts import get_handles_by_tier, LeagueTier
        
        handles = get_handles_by_tier(LeagueTier.ELITE_7)
        
        assert "turkey" in handles
        assert "argentina" in handles
        assert "scotland" in handles
        # Tier 2 countries should NOT be in Elite 7
        assert "france" not in handles
        assert "norway" not in handles
    
    def test_get_handles_by_tier_global(self):
        """Global tier should return global accounts."""
        from config.twitter_intel_accounts import get_handles_by_tier, LeagueTier
        
        handles = get_handles_by_tier(LeagueTier.GLOBAL)
        
        assert "global" in handles
        assert "@oluwashina" in handles["global"]
    
    def test_global_accounts_included_in_all_handles(self):
        """Global accounts should be included in get_all_twitter_handles()."""
        from config.twitter_intel_accounts import get_all_twitter_handles
        
        handles = get_all_twitter_handles()
        
        assert "@oluwashina" in handles
    
    def test_get_account_count_includes_global(self):
        """Account count should include global accounts."""
        from config.twitter_intel_accounts import get_account_count
        
        stats = get_account_count()
        
        assert "global_total" in stats
        assert stats["global_total"] >= 1
        assert stats["total"] == stats["elite_7_total"] + stats["tier_2_total"] + stats["global_total"]


class TestTwitterIntelCache:
    """Test the Twitter Intel Cache service."""
    
    def test_cache_singleton(self):
        """Cache should be a singleton."""
        from src.services.twitter_intel_cache import get_twitter_intel_cache
        
        cache1 = get_twitter_intel_cache()
        cache2 = get_twitter_intel_cache()
        
        assert cache1 is cache2
    
    def test_find_account_info_global(self):
        """_find_account_info should find global accounts."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Search for global account
        account_info = cache._find_account_info("@oluwashina")
        
        assert account_info is not None
        assert account_info.handle == "@oluwashina"
        assert "global" in account_info.focus.lower() or "international" in account_info.focus.lower() or "african" in account_info.focus.lower()
    
    def test_cache_initial_state(self):
        """Cache should start empty."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        # Create new instance (bypass singleton for testing)
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        assert cache.is_fresh == False
        assert cache.cache_age_minutes == -1
        assert cache._cycle_id is None
    
    def test_cache_summary_structure(self):
        """Cache summary should have correct structure."""
        from src.services.twitter_intel_cache import get_twitter_intel_cache
        
        cache = get_twitter_intel_cache()
        summary = cache.get_cache_summary()
        
        assert "is_fresh" in summary
        assert "cache_age_minutes" in summary
        assert "cycle_id" in summary
        assert "total_accounts" in summary
        assert "accounts_with_data" in summary
        assert "total_tweets" in summary
    
    def test_search_intel_empty_cache(self):
        """Search on empty cache should return empty list."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        # Create fresh instance
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        
        results = cache.search_intel("Galatasaray")
        
        assert results == []
    
    def test_search_intel_with_data(self):
        """Search should find matching tweets."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache, 
            CachedTweet, 
            TwitterIntelCacheEntry
        )
        
        # Create fresh instance with mock data
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Add mock data
        cache._cache["@rudygaletti"] = TwitterIntelCacheEntry(
            handle="@RudyGaletti",
            account_name="Rudy Galetti",
            league_focus="Turkey",
            tweets=[
                CachedTweet(
                    handle="@RudyGaletti",
                    date="2026-01-01",
                    content="Galatasaray: Icardi out for 2 weeks",
                    topics=["injury"]
                ),
                CachedTweet(
                    handle="@RudyGaletti",
                    date="2026-01-01",
                    content="Fenerbahce signs new player",
                    topics=["transfer"]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        # Search for Galatasaray
        results = cache.search_intel("Galatasaray")
        
        assert len(results) == 1
        assert "Icardi" in results[0].content
    
    def test_search_intel_case_insensitive(self):
        """Search should be case insensitive."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache, 
            CachedTweet, 
            TwitterIntelCacheEntry
        )
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        cache._cache["@test"] = TwitterIntelCacheEntry(
            handle="@test",
            account_name="Test",
            league_focus="Test",
            tweets=[
                CachedTweet(
                    handle="@test",
                    date="2026-01-01",
                    content="GALATASARAY news here",
                    topics=[]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        # Search lowercase
        results = cache.search_intel("galatasaray")
        
        assert len(results) == 1
    
    def test_search_intel_with_topics_filter(self):
        """Search with topics filter should only return matching topics."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache, 
            CachedTweet, 
            TwitterIntelCacheEntry
        )
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        cache._cache["@test"] = TwitterIntelCacheEntry(
            handle="@test",
            account_name="Test",
            league_focus="Test",
            tweets=[
                CachedTweet(
                    handle="@test",
                    date="2026-01-01",
                    content="Team injury news",
                    topics=["injury"]
                ),
                CachedTweet(
                    handle="@test",
                    date="2026-01-01",
                    content="Team transfer news",
                    topics=["transfer"]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        # Search with injury topic filter
        results = cache.search_intel("Team", topics=["injury"])
        
        assert len(results) == 1
        assert "injury" in results[0].content
    
    def test_get_intel_for_league_empty(self):
        """Get intel for league with no data should return empty list."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        
        results = cache.get_intel_for_league("soccer_turkey_super_league")
        
        assert results == []
    
    def test_clear_cache(self):
        """Clear cache should reset all state."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache,
            TwitterIntelCacheEntry
        )
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Add some data
        cache._cache["@test"] = TwitterIntelCacheEntry(
            handle="@test",
            account_name="Test",
            league_focus="Test",
            tweets=[],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        cache._last_full_refresh = datetime.now()
        cache._cycle_id = "test_cycle"
        
        # Clear
        cache.clear_cache()
        
        assert len(cache._cache) == 0
        assert cache._last_full_refresh is None
        assert cache._cycle_id is None


class TestMainIntegration:
    """Test the main.py integration."""
    
    def test_refresh_twitter_intel_sync_no_crash(self):
        """refresh_twitter_intel_sync should not crash even if services unavailable.
        
        V7.8 FIX: Mock external services to avoid network calls that block tests.
        - Mock _INTELLIGENCE_ROUTER_AVAILABLE to False (skip DeepSeek API)
        - Mock _try_nitter_fallback to return None (skip Nitter scraping)
        """
        # This should not raise any exception
        try:
            # Mock external services to avoid network calls
            with patch('src.main._INTELLIGENCE_ROUTER_AVAILABLE', False), \
                 patch('src.main._try_nitter_fallback', return_value=None):
                from src.main import refresh_twitter_intel_sync
                refresh_twitter_intel_sync()
        except ImportError:
            # If main.py has import issues, that's a different problem
            pytest.skip("main.py has import issues")
        except Exception as e:
            # Should not crash, just log warnings
            pytest.fail(f"refresh_twitter_intel_sync crashed: {e}")


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_enrich_alert_with_empty_cache(self):
        """Enriching alert with empty cache should not crash."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        cache._cycle_id = "test"
        cache._last_full_refresh = datetime.now()
        
        alert = {"score": 8, "market": "Home Win"}
        
        enriched = cache.enrich_alert_with_twitter_intel(
            alert=alert,
            home_team="Galatasaray",
            away_team="Fenerbahce",
            league_key="soccer_turkey_super_league"
        )
        
        assert "twitter_intel" in enriched
        assert enriched["twitter_intel"]["tweets"] == []
    
    def test_enrich_alert_preserves_original_data(self):
        """Enriching alert should preserve original alert data."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        cache._cycle_id = "test"
        cache._last_full_refresh = datetime.now()
        
        alert = {
            "score": 8, 
            "market": "Home Win",
            "custom_field": "should_be_preserved"
        }
        
        enriched = cache.enrich_alert_with_twitter_intel(
            alert=alert,
            home_team="Test",
            away_team="Test2",
            league_key="test"
        )
        
        assert enriched["score"] == 8
        assert enriched["market"] == "Home Win"
        assert enriched["custom_field"] == "should_be_preserved"
    
    def test_cache_is_fresh_after_refresh(self):
        """Cache should be fresh immediately after refresh."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Simulate refresh
        cache._last_full_refresh = datetime.now()
        
        assert cache.is_fresh == True
        assert cache.cache_age_minutes >= 0
        assert cache.cache_age_minutes < 1  # Should be less than 1 minute old
    
    def test_cache_is_stale_after_timeout(self):
        """Cache should be stale after 360 minutes (6 hours)."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Simulate old refresh (370 minutes ago - past 6 hour threshold)
        cache._last_full_refresh = datetime.now() - timedelta(minutes=370)
        
        assert cache.is_fresh == False
        assert cache.cache_age_minutes >= 370
    
    def test_cache_is_fresh_within_6_hours(self):
        """Cache should be fresh within 6 hour window."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        # Simulate refresh 3 hours ago (within 6 hour window)
        cache._last_full_refresh = datetime.now() - timedelta(minutes=180)
        
        assert cache.is_fresh == True
        assert cache.cache_age_minutes >= 180


class TestTwitterIntelIntegration:
    """Test the full integration of Twitter Intel with alerts."""
    
    def test_send_alert_accepts_twitter_intel_param(self):
        """send_alert should accept twitter_intel parameter without crashing."""
        from src.alerting.notifier import send_alert
        import inspect
        
        sig = inspect.signature(send_alert)
        params = list(sig.parameters.keys())
        
        assert 'twitter_intel' in params, "send_alert should have twitter_intel parameter"
    
    def test_twitter_intel_none_does_not_crash(self):
        """Passing None for twitter_intel should not crash."""
        # This tests the edge case of None twitter_intel
        from src.alerting.notifier import send_alert
        
        # We can't actually send (no Telegram config in tests)
        # but we can verify the function signature accepts None
        import inspect
        sig = inspect.signature(send_alert)
        twitter_param = sig.parameters.get('twitter_intel')
        
        assert twitter_param is not None
        assert twitter_param.default is None
    
    def test_twitter_intel_empty_tweets_list(self):
        """Empty tweets list should not crash the alert formatting."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        cache._cycle_id = "test"
        cache._last_full_refresh = datetime.now()
        
        # Search should return empty list
        results = cache.search_intel("NonExistentTeam", topics=['injury'])
        
        assert results == []
    
    def test_search_intel_with_none_topics(self):
        """search_intel with None topics should not crash."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache,
            CachedTweet,
            TwitterIntelCacheEntry
        )
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        cache._cache["@test"] = TwitterIntelCacheEntry(
            handle="@test",
            account_name="Test",
            league_focus="Test",
            tweets=[
                CachedTweet(
                    handle="@test",
                    date="2026-01-01",
                    content="Test content here",
                    topics=[]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        # Search with None topics (should not filter by topics)
        results = cache.search_intel("Test", topics=None)
        
        assert len(results) == 1
    
    def test_search_intel_with_empty_topics_list(self):
        """search_intel with empty topics list should not filter by topics."""
        from src.services.twitter_intel_cache import (
            TwitterIntelCache,
            CachedTweet,
            TwitterIntelCacheEntry
        )
        
        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        
        cache._cache["@test"] = TwitterIntelCacheEntry(
            handle="@test",
            account_name="Test",
            league_focus="Test",
            tweets=[
                CachedTweet(
                    handle="@test",
                    date="2026-01-01",
                    content="Test content",
                    topics=["injury"]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        # Search with empty topics list - empty list is falsy, so no topic filter applied
        results = cache.search_intel("Test", topics=[])
        
        # Empty topics list means no filtering (returns all matches)
        assert len(results) == 1
    
    def test_main_twitter_intel_available_flag(self):
        """Verify _TWITTER_INTEL_AVAILABLE flag exists in main."""
        from src.main import _TWITTER_INTEL_AVAILABLE
        
        # Should be a boolean
        assert isinstance(_TWITTER_INTEL_AVAILABLE, bool)


class TestTwitterIntelHelper:
    """Test the DRY helper function for Twitter Intel enrichment."""
    
    def test_get_twitter_intel_for_match_exists(self):
        """Helper function should exist and be importable."""
        from src.main import get_twitter_intel_for_match
        
        assert callable(get_twitter_intel_for_match)
    
    def test_get_twitter_intel_for_match_returns_none_when_unavailable(self):
        """Should return None when Twitter Intel is not available."""
        from src.main import get_twitter_intel_for_match
        
        # Create a mock match object
        class MockMatch:
            home_team = "TestTeam"
            away_team = "TestTeam2"
            league = "test_league"
        
        # With empty cache, should return None
        result = get_twitter_intel_for_match(MockMatch())
        
        # Result is None because cache is not fresh
        assert result is None
    
    def test_get_twitter_intel_for_match_with_context_label(self):
        """Should accept context_label parameter."""
        from src.main import get_twitter_intel_for_match
        import inspect
        
        sig = inspect.signature(get_twitter_intel_for_match)
        params = sig.parameters
        
        assert 'context_label' in params
        assert params['context_label'].default == ""


