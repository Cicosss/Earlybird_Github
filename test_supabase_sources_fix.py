#!/usr/bin/env python3
"""
Test Suite for Bug #15: Supabase - Table 'sources' Not Found Fix

This test verifies that the fetch_sources() method correctly queries the 'news_sources' table
instead of the non-existent 'sources' table.

Author: CoVe Debug Mode
Date: 2026-02-10
"""

import sys
import os
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_1_import_supabase_provider():
    """Test 1: Import SupabaseProvider module"""
    logger.info("TEST 1: Importing SupabaseProvider module...")
    try:
        from src.database.supabase_provider import SupabaseProvider, get_supabase
        logger.info("✅ PASSED: SupabaseProvider imported successfully")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: Could not import SupabaseProvider: {e}")
        return False

def test_2_fetch_sources_method_exists():
    """Test 2: Verify fetch_sources() method exists"""
    logger.info("TEST 2: Verifying fetch_sources() method exists...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        provider = SupabaseProvider()
        
        if hasattr(provider, 'fetch_sources'):
            logger.info("✅ PASSED: fetch_sources() method exists")
            return True
        else:
            logger.error("❌ FAILED: fetch_sources() method not found")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error checking method existence: {e}")
        return False

def test_3_fetch_sources_signature():
    """Test 3: Verify fetch_sources() method signature"""
    logger.info("TEST 3: Verifying fetch_sources() method signature...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        import inspect
        
        provider = SupabaseProvider()
        method = getattr(provider, 'fetch_sources')
        
        # Get method signature
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        
        # Expected parameters: self, league_id (optional)
        expected_params = ['self', 'league_id']
        
        if params == expected_params:
            logger.info(f"✅ PASSED: Method signature correct: {params}")
            return True
        else:
            logger.error(f"❌ FAILED: Expected params {expected_params}, got {params}")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error checking method signature: {e}")
        return False

def test_4_fetch_sources_queries_news_sources_table():
    """Test 4: Verify fetch_sources() queries 'news_sources' table"""
    logger.info("TEST 4: Verifying fetch_sources() queries 'news_sources' table...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        import inspect
        
        # Get source code of the method
        source = inspect.getsource(SupabaseProvider.fetch_sources)
        
        # Check if it queries 'news_sources' table
        if '"news_sources"' in source or "'news_sources'" in source:
            logger.info("✅ PASSED: fetch_sources() queries 'news_sources' table")
            return True
        else:
            logger.error("❌ FAILED: fetch_sources() does not query 'news_sources' table")
            logger.error(f"Source code:\n{source}")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error checking table name: {e}")
        return False

def test_5_fetch_sources_with_mirror_fallback():
    """Test 5: Verify fetch_sources() works with mirror fallback"""
    logger.info("TEST 5: Verifying fetch_sources() works with mirror fallback...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        
        provider = SupabaseProvider()
        
        # Try to fetch sources (should use mirror if Supabase fails)
        sources = provider.fetch_sources()
        
        if sources is not None:
            logger.info(f"✅ PASSED: fetch_sources() returned {len(sources)} sources (from mirror)")
            return True
        else:
            logger.error("❌ FAILED: fetch_sources() returned None")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error fetching sources: {e}")
        return False

def test_6_fetch_sources_with_league_filter():
    """Test 6: Verify fetch_sources() works with league filter"""
    logger.info("TEST 6: Verifying fetch_sources() works with league filter...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        
        provider = SupabaseProvider()
        
        # Try to fetch sources for a specific league (should use mirror if Supabase fails)
        # Use a league ID from the mirror
        league_id = "4b6f37db-d1f3-42b5-9495-987ef260fb2f"  # Brazil Serie A
        sources = provider.fetch_sources(league_id)
        
        if sources is not None:
            logger.info(f"✅ PASSED: fetch_sources(league_id) returned {len(sources)} sources (from mirror)")
            return True
        else:
            logger.error("❌ FAILED: fetch_sources(league_id) returned None")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error fetching sources with league filter: {e}")
        return False

def test_7_fetch_hierarchical_map():
    """Test 7: Verify fetch_hierarchical_map() works correctly"""
    logger.info("TEST 7: Verifying fetch_hierarchical_map() works correctly...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        
        provider = SupabaseProvider()
        
        # Try to fetch hierarchical map (uses fetch_sources internally)
        hierarchical_map = provider.fetch_hierarchical_map()
        
        if hierarchical_map and "continents" in hierarchical_map:
            logger.info(f"✅ PASSED: fetch_hierarchical_map() returned map with {len(hierarchical_map['continents'])} continents")
            return True
        else:
            logger.error("❌ FAILED: fetch_hierarchical_map() returned invalid data")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error fetching hierarchical map: {e}")
        return False

def test_8_cache_key_uses_news_sources():
    """Test 8: Verify cache key uses 'news_sources' prefix"""
    logger.info("TEST 8: Verifying cache key uses 'news_sources' prefix...")
    try:
        from src.database.supabase_provider import SupabaseProvider
        import inspect
        
        # Get source code of the method
        source = inspect.getsource(SupabaseProvider.fetch_sources)
        
        # Check if cache key uses 'news_sources' prefix
        if 'news_sources_' in source:
            logger.info("✅ PASSED: Cache key uses 'news_sources_' prefix")
            return True
        else:
            logger.error("❌ FAILED: Cache key does not use 'news_sources_' prefix")
            logger.error(f"Source code:\n{source}")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error checking cache key: {e}")
        return False

def run_all_tests():
    """Run all tests and report results"""
    logger.info("=" * 80)
    logger.info("Starting Bug #15 Fix Test Suite")
    logger.info("=" * 80)
    
    tests = [
        test_1_import_supabase_provider,
        test_2_fetch_sources_method_exists,
        test_3_fetch_sources_signature,
        test_4_fetch_sources_queries_news_sources_table,
        test_5_fetch_sources_with_mirror_fallback,
        test_6_fetch_sources_with_league_filter,
        test_7_fetch_hierarchical_map,
        test_8_cache_key_uses_news_sources,
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
        logger.info("-" * 80)
    
    # Summary
    passed = sum(results)
    total = len(results)
    logger.info("=" * 80)
    logger.info(f"TEST SUMMARY: {passed}/{total} tests passed")
    logger.info("=" * 80)
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Bug #15 fix is working correctly.")
        return True
    else:
        logger.error(f"❌ {total - passed} test(s) failed. Please review the errors above.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
