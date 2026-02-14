#!/usr/bin/env python3
"""
Test Script for ISSUE #1: Mirror Obsoleto - Refresh Mirror After Bug Fixes

This test executes refresh_mirror() to regenerate the local mirror with the correct keys
after fixing BUG #1 and BUG #2.

Author: CoVe Debug Mode
Date: 2026-02-12
"""

import sys
import os
import logging
import json
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_1_import_refresh_mirror():
    """Test 1: Import refresh_mirror function"""
    logger.info("TEST 1: Importing refresh_mirror function...")
    try:
        from src.database.supabase_provider import refresh_mirror
        logger.info("✅ PASSED: refresh_mirror imported successfully")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: Could not import refresh_mirror: {e}")
        return False

def test_2_execute_refresh_mirror():
    """Test 2: Execute refresh_mirror() to regenerate the mirror"""
    logger.info("TEST 2: Executing refresh_mirror()...")
    try:
        from src.database.supabase_provider import refresh_mirror
        success = refresh_mirror()
        
        if success:
            logger.info("✅ PASSED: refresh_mirror() executed successfully")
            return True
        else:
            logger.error("❌ FAILED: refresh_mirror() returned False")
            return False
    except Exception as e:
        logger.error(f"❌ FAILED: Error executing refresh_mirror(): {e}")
        import traceback
        traceback.print_exc()
        return False

def test_3_verify_mirror_structure():
    """Test 3: Verify the mirror has the correct structure and keys"""
    logger.info("TEST 3: Verifying mirror structure...")
    try:
        mirror_path = Path("data/supabase_mirror.json")
        
        if not mirror_path.exists():
            logger.error(f"❌ FAILED: Mirror file not found at {mirror_path}")
            return False
        
        with open(mirror_path, 'r') as f:
            mirror_data = json.load(f)
        
        # The actual data is nested under the "data" key
        if "data" not in mirror_data:
            logger.error(f"❌ FAILED: Mirror missing 'data' key")
            return False
        
        data = mirror_data["data"]
        
        # Check for expected keys
        expected_keys = ["continents", "countries", "leagues", "news_sources", "social_sources"]
        missing_keys = []
        extra_keys = []
        
        for key in expected_keys:
            if key not in data:
                missing_keys.append(key)
        
        for key in data:
            if key not in expected_keys:
                extra_keys.append(key)
        
        # Check for the wrong key "sources"
        if "sources" in data:
            logger.error(f"❌ FAILED: Mirror still contains wrong key 'sources'")
            return False
        
        if missing_keys:
            logger.error(f"❌ FAILED: Mirror missing keys: {missing_keys}")
            return False
        
        if extra_keys:
            logger.warning(f"⚠️ WARNING: Mirror has extra keys: {extra_keys}")
        
        # Log counts
        for key in expected_keys:
            count = len(data.get(key, []))
            logger.info(f"   {key}: {count} records")
        
        logger.info("✅ PASSED: Mirror has correct structure")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: Error verifying mirror structure: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_4_verify_news_sources_present():
    """Test 4: Verify news_sources are present in the mirror"""
    logger.info("TEST 4: Verifying news_sources are present...")
    try:
        mirror_path = Path("data/supabase_mirror.json")
        
        with open(mirror_path, 'r') as f:
            mirror_data = json.load(f)
        
        data = mirror_data.get("data", {})
        news_sources = data.get("news_sources", [])
        
        if not news_sources:
            logger.error("❌ FAILED: news_sources is empty in the mirror")
            return False
        
        logger.info(f"✅ PASSED: news_sources has {len(news_sources)} records")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: Error verifying news_sources: {e}")
        return False

def test_5_verify_social_sources_present():
    """Test 5: Verify social_sources are present in the mirror"""
    logger.info("TEST 5: Verifying social_sources are present...")
    try:
        mirror_path = Path("data/supabase_mirror.json")
        
        with open(mirror_path, 'r') as f:
            mirror_data = json.load(f)
        
        data = mirror_data.get("data", {})
        social_sources = data.get("social_sources", [])
        
        if not social_sources:
            logger.error("❌ FAILED: social_sources is empty in the mirror")
            return False
        
        logger.info(f"✅ PASSED: social_sources has {len(social_sources)} records")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: Error verifying social_sources: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("ISSUE #1: Mirror Obsoleto - Refresh Mirror Test Suite")
    logger.info("=" * 60)
    
    tests = [
        test_1_import_refresh_mirror,
        test_2_execute_refresh_mirror,
        test_3_verify_mirror_structure,
        test_4_verify_news_sources_present,
        test_5_verify_social_sources_present,
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
        logger.info("-" * 60)
    
    passed = sum(results)
    total = len(results)
    
    logger.info("=" * 60)
    logger.info(f"TEST SUMMARY: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("✅ ALL TESTS PASSED!")
        return 0
    else:
        logger.error(f"❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
