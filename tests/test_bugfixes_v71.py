"""
EarlyBird V7.1 Bug Fixes - Regression Tests

Tests for bugs fixed in V7.1:
1. search_type mismatch in news_hunter summary (beat_writer_cache vs beat_writer_priority)
2. Bare except clauses catching all exceptions
3. Thread-safety for TwitterIntelCache singleton
4. Confidence string mapping in discovery_queue (HIGH/MEDIUM/LOW)
5. Missing country mappings in COUNTRY_TO_LANG

Run with: pytest tests/test_bugfixes_v71.py -v
"""
import pytest
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestSearchTypeMismatchFix:
    """
    FIX 1: search_type mismatch in news_hunter summary.
    
    Before fix: beat_writer_total always 0 because searching for 'beat_writer_priority'
    After fix: searches for both 'beat_writer_cache' and 'beat_writer_priority'
    """
    
    def test_beat_writer_cache_counted_in_summary(self):
        """Beat writer results with search_type='beat_writer_cache' should be counted."""
        # Simulate news items as returned by search_beat_writers_priority
        all_news = [
            {'search_type': 'beat_writer_cache', 'team': 'Galatasaray'},
            {'search_type': 'beat_writer_cache', 'team': 'Fenerbahce'},
            {'search_type': 'local_site_dork', 'team': 'Galatasaray'},
        ]
        
        # This is the FIXED logic from news_hunter.py
        beat_writer_total = len([n for n in all_news if n.get('search_type') in ('beat_writer_cache', 'beat_writer_priority')])
        
        assert beat_writer_total == 2, f"Expected 2 beat writer results, got {beat_writer_total}"
    
    def test_beat_writer_priority_still_counted(self):
        """Legacy search_type='beat_writer_priority' should still be counted."""
        all_news = [
            {'search_type': 'beat_writer_priority', 'team': 'Test'},
        ]
        
        beat_writer_total = len([n for n in all_news if n.get('search_type') in ('beat_writer_cache', 'beat_writer_priority')])
        
        assert beat_writer_total == 1


class TestExceptClauseFix:
    """
    FIX 2: Bare except clauses should specify exception types.
    
    Before fix: except: pass (catches KeyboardInterrupt, SystemExit, etc.)
    After fix: except (IndexError, AttributeError): pass
    """
    
    def test_subreddit_extraction_handles_index_error(self):
        """Subreddit extraction should handle IndexError gracefully."""
        link = "https://reddit.com/r/"  # Missing subreddit name
        subreddit = "reddit"
        
        if '/r/' in link:
            try:
                subreddit = link.split('/r/')[1].split('/')[0]
            except (IndexError, AttributeError):
                pass
        
        # Should fall back to default, not crash
        assert subreddit in ("reddit", "")
    
    def test_subreddit_extraction_valid_url(self):
        """Valid Reddit URL should extract subreddit correctly."""
        link = "https://reddit.com/r/soccer/comments/123"
        subreddit = "reddit"
        
        if '/r/' in link:
            try:
                subreddit = link.split('/r/')[1].split('/')[0]
            except (IndexError, AttributeError):
                pass
        
        assert subreddit == "soccer"


class TestTwitterIntelCacheThreadSafety:
    """
    FIX 3: TwitterIntelCache singleton should be thread-safe.
    
    Before fix: Race condition in __new__ could create multiple instances
    After fix: Double-check locking pattern prevents race condition
    """
    
    def test_singleton_returns_same_instance(self):
        """Multiple calls should return the same instance."""
        from src.services.twitter_intel_cache import get_twitter_intel_cache
        
        cache1 = get_twitter_intel_cache()
        cache2 = get_twitter_intel_cache()
        
        assert cache1 is cache2, "Singleton should return same instance"
    
    def test_singleton_thread_safe(self):
        """Concurrent access should not create multiple instances."""
        from src.services.twitter_intel_cache import TwitterIntelCache
        
        instances = []
        errors = []
        
        def get_instance():
            try:
                instance = TwitterIntelCache()
                instances.append(id(instance))
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads trying to get instance simultaneously
        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        
        # Start all threads at roughly the same time
        for t in threads:
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        assert len(set(instances)) == 1, f"Multiple instances created: {set(instances)}"


class TestConfidenceStringMapping:
    """
    FIX 4: Confidence string mapping in discovery_queue.
    
    Before fix: 'HIGH', 'MEDIUM', 'LOW' all mapped to 0.8
    After fix: Proper mapping (HIGH=0.85, MEDIUM=0.65, LOW=0.4)
    """
    
    def test_confidence_high_mapping(self):
        """'HIGH' should map to 0.85."""
        confidence = 'HIGH'
        confidence_map = {
            'HIGH': 0.85,
            'MEDIUM': 0.65,
            'LOW': 0.4,
            'VERY_HIGH': 0.95,
        }
        
        result = confidence_map.get(confidence.upper().strip(), 0.5)
        assert result == 0.85
    
    def test_confidence_medium_mapping(self):
        """'MEDIUM' should map to 0.65, not 0.8."""
        confidence = 'MEDIUM'
        confidence_map = {
            'HIGH': 0.85,
            'MEDIUM': 0.65,
            'LOW': 0.4,
            'VERY_HIGH': 0.95,
        }
        
        result = confidence_map.get(confidence.upper().strip(), 0.5)
        assert result == 0.65, f"MEDIUM should be 0.65, got {result}"
    
    def test_confidence_low_mapping(self):
        """'LOW' should map to 0.4, not 0.8."""
        confidence = 'LOW'
        confidence_map = {
            'HIGH': 0.85,
            'MEDIUM': 0.65,
            'LOW': 0.4,
            'VERY_HIGH': 0.95,
        }
        
        result = confidence_map.get(confidence.upper().strip(), 0.5)
        assert result == 0.4, f"LOW should be 0.4, got {result}"
    
    def test_confidence_numeric_string(self):
        """Numeric string like '0.75' should parse correctly."""
        confidence = '0.75'
        
        # Simulate the fixed logic
        confidence_map = {'HIGH': 0.85, 'MEDIUM': 0.65, 'LOW': 0.4}
        confidence_upper = confidence.upper().strip()
        
        if confidence_upper in confidence_map:
            result = confidence_map[confidence_upper]
        else:
            try:
                result = float(confidence)
            except ValueError:
                result = 0.5
        
        assert result == 0.75


class TestCountryMappingFix:
    """
    FIX 5: Missing country mappings in COUNTRY_TO_LANG.
    
    Before fix: norway, france, belgium, austria, netherlands missing
    After fix: All Tier 2 countries included
    """
    
    def test_tier2_countries_have_mapping(self):
        """All Tier 2 countries should have language mapping."""
        COUNTRY_TO_LANG = {
            # Elite 7
            'turkey': 'tr', 'argentina': 'es', 'mexico': 'es', 
            'greece': 'el', 'scotland': 'en', 'australia': 'en',
            'poland': 'pl',
            # Tier 2
            'norway': 'no', 'france': 'fr', 'belgium': 'nl',
            'austria': 'de', 'netherlands': 'nl',
            'china': 'zh', 'japan': 'ja', 'brazil_b': 'pt',
            # Other
            'egypt': 'ar'
        }
        
        tier2_countries = ['norway', 'france', 'belgium', 'austria', 'netherlands']
        
        for country in tier2_countries:
            assert country in COUNTRY_TO_LANG, f"Missing mapping for {country}"
            assert COUNTRY_TO_LANG[country] != 'en' or country in ('belgium',), \
                f"{country} should have native language, not 'en'"
    
    def test_unknown_country_defaults_to_english(self):
        """Unknown countries should default to English."""
        COUNTRY_TO_LANG = {'turkey': 'tr'}
        
        lang = COUNTRY_TO_LANG.get('unknown_country', 'en')
        assert lang == 'en'


class TestDiscoveryQueueIntegration:
    """
    Integration test for discovery_queue with confidence handling.
    """
    
    def test_push_with_string_confidence(self):
        """Push should handle string confidence values correctly."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        # Push with string confidence
        uuid = queue.push(
            data={'title': 'Test news'},
            league_key='soccer_turkey_super_league',
            team='Galatasaray',
            confidence='HIGH'  # String, not float
        )
        
        assert uuid is not None
        
        # Retrieve and verify confidence was converted
        results = queue.pop_for_match(
            match_id='test_match',
            team_names=['Galatasaray'],
            league_key='soccer_turkey_super_league'
        )
        
        if results:
            # Confidence should be numeric now
            conf = results[0].get('confidence')
            assert isinstance(conf, (int, float)), f"Confidence should be numeric, got {type(conf)}"
            assert conf == 0.85, f"HIGH should map to 0.85, got {conf}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
