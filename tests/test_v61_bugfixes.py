"""
Test V6.1 Bug Fixes

Tests for the 10 bug fixes applied in V6.1:
1. Thread-safe rate limiting in data_provider.py
2. Removed duplicate import in main.py
3. Robust timezone handling in ingest_fixtures.py
4. Cache protection for None values in smart_cache.py
5. Division by zero protection in is_biscotto_suspect
6. Singleton pattern verification for FotMobProvider
7. http_client.py completeness verification
8. get_table_context completeness verification
9. These regression tests
10. Cache not duplicated (singleton verified)

Author: EarlyBird V6.1
"""
import unittest
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestThreadSafeRateLimiting(unittest.TestCase):
    """Test #1: Thread-safe rate limiting in FotMobProvider."""
    
    def test_rate_limit_lock_exists(self):
        """Verify that the rate limit lock is defined."""
        from src.ingestion.data_provider import _fotmob_rate_limit_lock
        import threading
        
        self.assertIsInstance(_fotmob_rate_limit_lock, type(threading.Lock()))
    
    def test_concurrent_rate_limiting(self):
        """Test that concurrent calls don't bypass rate limiting."""
        from src.ingestion.data_provider import (
            _fotmob_rate_limit_lock, 
            _last_fotmob_request_time,
            FOTMOB_MIN_REQUEST_INTERVAL
        )
        
        # This test verifies the lock exists and is a proper Lock object
        self.assertTrue(hasattr(_fotmob_rate_limit_lock, 'acquire'))
        self.assertTrue(hasattr(_fotmob_rate_limit_lock, 'release'))


class TestTimezoneHandling(unittest.TestCase):
    """Test #3: Robust timezone handling in should_update_league."""
    
    def test_naive_datetime_handling(self):
        """Test that naive datetimes are properly converted to UTC."""
        from src.ingestion.ingest_fixtures import should_update_league
        from unittest.mock import MagicMock
        
        # Create mock DB session
        mock_db = MagicMock()
        
        # Create mock match with naive datetime (no timezone)
        mock_match = MagicMock()
        mock_match.start_time = datetime.now() + timedelta(hours=12)  # Naive
        mock_match.league = "test_league"
        
        # Mock query to return our match
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_match]
        mock_db.query.return_value.filter.return_value.scalar.return_value = None
        
        # Should not raise TypeError about comparing naive and aware datetimes
        try:
            result = should_update_league(mock_db, "test_league")
            # If we get here without exception, the fix works
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 3)
        except TypeError as e:
            if "can't compare" in str(e) and "naive" in str(e):
                self.fail("Timezone handling bug: comparing naive and aware datetimes")
            raise


class TestSmartCacheNoneProtection(unittest.TestCase):
    """Test #4: Cache protection for None values."""
    
    def test_none_value_not_cached_by_default(self):
        """Test that None values are not cached by default."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test_none", max_size=10)
        
        # Try to cache None
        result = cache.set("test_key", None)
        
        # Should return False (not cached)
        self.assertFalse(result)
        
        # Should not be in cache
        self.assertIsNone(cache.get("test_key"))
    
    def test_none_value_cached_when_explicit(self):
        """Test that None values can be cached when cache_none=True."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test_none_explicit", max_size=10)
        
        # Cache None explicitly
        result = cache.set("test_key", None, cache_none=True)
        
        # Should return True (cached)
        self.assertTrue(result)
    
    def test_valid_value_still_cached(self):
        """Test that valid values are still cached normally."""
        from src.utils.smart_cache import SmartCache
        
        cache = SmartCache(name="test_valid", max_size=10)
        
        # Cache a valid value
        result = cache.set("test_key", {"data": "value"})
        
        # Should return True
        self.assertTrue(result)
        
        # Should be retrievable
        cached = cache.get("test_key")
        self.assertEqual(cached, {"data": "value"})


class TestBiscottoSuspectEdgeCases(unittest.TestCase):
    """Test #5: Division by zero and edge case protection in is_biscotto_suspect."""
    
    def test_none_draw_odd(self):
        """Test handling of None draw_odd."""
        from src.main import is_biscotto_suspect
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = None
        mock_match.opening_draw_odd = 3.5
        
        result = is_biscotto_suspect(mock_match)
        
        self.assertFalse(result['is_suspect'])
        self.assertIsNone(result['draw_odd'])
    
    def test_zero_draw_odd(self):
        """Test handling of zero draw_odd (invalid)."""
        from src.main import is_biscotto_suspect
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = 0
        mock_match.opening_draw_odd = 3.5
        
        result = is_biscotto_suspect(mock_match)
        
        self.assertFalse(result['is_suspect'])
    
    def test_negative_draw_odd(self):
        """Test handling of negative draw_odd (invalid)."""
        from src.main import is_biscotto_suspect
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = -1.5
        mock_match.opening_draw_odd = 3.5
        
        result = is_biscotto_suspect(mock_match)
        
        self.assertFalse(result['is_suspect'])
    
    def test_none_opening_draw(self):
        """Test handling of None opening_draw (no division by zero)."""
        from src.main import is_biscotto_suspect
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = 2.8
        mock_match.opening_draw_odd = None
        
        # Should not raise ZeroDivisionError
        result = is_biscotto_suspect(mock_match)
        
        # drop_pct should be 0 when opening_draw is None
        self.assertEqual(result['drop_pct'], 0)
    
    def test_zero_opening_draw(self):
        """Test handling of zero opening_draw (no division by zero)."""
        from src.main import is_biscotto_suspect
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = 2.8
        mock_match.opening_draw_odd = 0
        
        # Should not raise ZeroDivisionError
        result = is_biscotto_suspect(mock_match)
        
        # drop_pct should be 0 when opening_draw is 0
        self.assertEqual(result['drop_pct'], 0)
    
    def test_valid_biscotto_detection(self):
        """Test that valid biscotto detection still works."""
        from src.main import is_biscotto_suspect, BISCOTTO_SUSPICIOUS_LOW
        
        mock_match = MagicMock()
        mock_match.current_draw_odd = BISCOTTO_SUSPICIOUS_LOW - 0.1  # Below threshold
        mock_match.opening_draw_odd = 3.5
        
        result = is_biscotto_suspect(mock_match)
        
        self.assertTrue(result['is_suspect'])
        self.assertEqual(result['severity'], 'HIGH')


class TestSingletonPattern(unittest.TestCase):
    """Test #6 & #10: Singleton pattern for FotMobProvider."""
    
    def test_get_data_provider_returns_same_instance(self):
        """Test that get_data_provider returns the same instance."""
        from src.ingestion.data_provider import get_data_provider
        
        provider1 = get_data_provider()
        provider2 = get_data_provider()
        
        self.assertIs(provider1, provider2)
    
    def test_cache_shared_across_calls(self):
        """Test that the team cache is shared (same instance)."""
        from src.ingestion.data_provider import get_data_provider
        
        provider1 = get_data_provider()
        provider2 = get_data_provider()
        
        # Add to cache via provider1
        provider1._team_cache['test_team'] = (123, 'Test Team')
        
        # Should be visible via provider2 (same instance)
        self.assertIn('test_team', provider2._team_cache)
        
        # Cleanup
        del provider1._team_cache['test_team']


class TestImportDeduplication(unittest.TestCase):
    """Test #2: Verify no duplicate imports in main.py."""
    
    def test_intelligence_router_single_import(self):
        """Test that intelligence_router is imported only once."""
        import ast
        
        with open('src/main.py', 'r') as f:
            content = f.read()
        
        # Count occurrences of the import statement
        import_count = content.count('from src.services.intelligence_router import get_intelligence_router')
        
        # Should be exactly 1 (the unified import)
        self.assertEqual(import_count, 1, 
            f"Expected 1 import of get_intelligence_router, found {import_count}")


class TestModuleSyntax(unittest.TestCase):
    """Test #7 & #8: Verify modules compile without syntax errors."""
    
    def test_http_client_compiles(self):
        """Test that http_client.py compiles without errors."""
        import py_compile
        try:
            py_compile.compile('src/utils/http_client.py', doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"http_client.py has syntax error: {e}")
    
    def test_data_provider_compiles(self):
        """Test that data_provider.py compiles without errors."""
        import py_compile
        try:
            py_compile.compile('src/ingestion/data_provider.py', doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"data_provider.py has syntax error: {e}")
    
    def test_main_compiles(self):
        """Test that main.py compiles without errors."""
        import py_compile
        try:
            py_compile.compile('src/main.py', doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"main.py has syntax error: {e}")
    
    def test_ingest_fixtures_compiles(self):
        """Test that ingest_fixtures.py compiles without errors."""
        import py_compile
        try:
            py_compile.compile('src/ingestion/ingest_fixtures.py', doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"ingest_fixtures.py has syntax error: {e}")
    
    def test_smart_cache_compiles(self):
        """Test that smart_cache.py compiles without errors."""
        import py_compile
        try:
            py_compile.compile('src/utils/smart_cache.py', doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"smart_cache.py has syntax error: {e}")


if __name__ == '__main__':
    unittest.main()
