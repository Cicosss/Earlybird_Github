"""
Test script for Bug #6: TwitterIntelCache - Metodo Refresh Mancante

This script tests the fix for the missing refresh() method in TwitterIntelCache.
The fix ensures that refresh_twitter_intel_sync() correctly calls the async
refresh_twitter_intel() method with the DeepSeek provider.
"""

import sys
import os
import logging

# Setup path
sys.path.insert(0, os.getcwd())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all required modules can be imported."""
    logger.info("🧪 Testing imports...")
    try:
        from src.main import refresh_twitter_intel_sync, _TWITTER_INTEL_AVAILABLE, _DEEPSEEK_PROVIDER_AVAILABLE
        from src.services.twitter_intel_cache import get_twitter_intel_cache
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        logger.info("✅ All imports successful")
        logger.info(f"   - Twitter Intel Available: {_TWITTER_INTEL_AVAILABLE}")
        logger.info(f"   - DeepSeek Provider Available: {_DEEPSEEK_PROVIDER_AVAILABLE}")
        return True
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        return False

def test_cache_instance():
    """Test that TwitterIntelCache can be instantiated."""
    logger.info("🧪 Testing TwitterIntelCache instance...")
    try:
        from src.services.twitter_intel_cache import get_twitter_intel_cache
        cache = get_twitter_intel_cache()
        logger.info(f"✅ TwitterIntelCache instance created")
        logger.info(f"   - Cache fresh: {cache.is_fresh}")
        logger.info(f"   - Cache age: {cache.cache_age_minutes} minutes")
        return True
    except Exception as e:
        logger.error(f"❌ Cache instance creation failed: {e}")
        return False

def test_deepseek_provider():
    """Test that DeepSeek provider can be instantiated."""
    logger.info("🧪 Testing DeepSeek provider...")
    try:
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        provider = get_deepseek_provider()
        logger.info("✅ DeepSeek provider instance created")
        logger.info(f"   - Has extract_twitter_intel: {hasattr(provider, 'extract_twitter_intel')}")
        return True
    except Exception as e:
        logger.error(f"❌ DeepSeek provider creation failed: {e}")
        return False

def test_refresh_twitter_intel_sync():
    """Test that refresh_twitter_intel_sync() works correctly."""
    logger.info("🧪 Testing refresh_twitter_intel_sync()...")
    try:
        from src.main import refresh_twitter_intel_sync
        
        # Call the function
        refresh_twitter_intel_sync()
        logger.info("✅ refresh_twitter_intel_sync() executed without errors")
        return True
    except Exception as e:
        logger.error(f"❌ refresh_twitter_intel_sync() failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_method_signature():
    """Test that refresh_twitter_intel() has the correct signature."""
    logger.info("🧪 Testing refresh_twitter_intel() signature...")
    try:
        from src.services.twitter_intel_cache import TwitterIntelCache
        import inspect
        
        # Check if the method exists and is async
        if hasattr(TwitterIntelCache, 'refresh_twitter_intel'):
            method = getattr(TwitterIntelCache, 'refresh_twitter_intel')
            is_async = inspect.iscoroutinefunction(method)
            logger.info(f"✅ refresh_twitter_intel() exists")
            logger.info(f"   - Is async: {is_async}")
            
            # Check parameters
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            logger.info(f"   - Parameters: {params}")
            
            # Verify required parameters
            required_params = ['self', 'gemini_service']
            has_required = all(p in params for p in required_params)
            logger.info(f"   - Has required params: {has_required}")
            
            return is_async and has_required
        else:
            logger.error("❌ refresh_twitter_intel() method not found")
            return False
    except Exception as e:
        logger.error(f"❌ Signature test failed: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("=" * 70)
    logger.info("🧪 Testing Bug #6 Fix: TwitterIntelCache - Metodo Refresh Mancante")
    logger.info("=" * 70)
    
    tests = [
        ("Imports", test_imports),
        ("Cache Instance", test_cache_instance),
        ("DeepSeek Provider", test_deepseek_provider),
        ("Method Signature", test_method_signature),
        ("Refresh Function", test_refresh_twitter_intel_sync),
    ]
    
    results = []
    for name, test_func in tests:
        logger.info("\n" + "=" * 70)
        result = test_func()
        results.append((name, result))
        logger.info("=" * 70)
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 70)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    logger.info("=" * 70)
    
    return all(result for _, result in results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
