"""
Test script to verify Brave Search double encoding fix (Bug #7)

This test verifies that:
1. Queries with non-ASCII characters (Turkish, Polish, Greek, etc.) work correctly
2. The query is NOT double-encoded (which causes HTTP 422 errors)
3. HTTPX handles the URL encoding automatically

Bug #7: Brave Search API - HTTP 422 Error
Cause: Double URL encoding caused by manual encoding + HTTPX automatic encoding
Fix: Removed manual encoding, let HTTPX handle it automatically
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ingestion.brave_provider import get_brave_provider, BraveSearchProvider
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_argentina_query():
    """Test Argentina league query with Spanish characters (ó, ñ)"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Argentina League Query (Spanish characters)")
    logger.info("="*70)

    query = "(site:ole.com.ar OR site:tycsports.com OR site:mundoalbiceleste.com) (equipo alternativo OR muletto OR rotación masiva) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal"

    provider = get_brave_provider()

    if not provider.is_available():
        logger.warning("⚠️ Brave Search not available - skipping test")
        return None

    logger.info(f"Query length: {len(query)} characters")
    logger.info(f"Query preview: {query[:100]}...")

    results = provider.search_news(query, limit=5, component="test_argentina")

    if results:
        logger.info(f"✅ SUCCESS: Found {len(results)} results")
        for i, result in enumerate(results[:2], 1):
            logger.info(f"  {i}. {result.get('title', 'N/A')[:60]}...")
            logger.info(f"     URL: {result.get('url', 'N/A')[:80]}...")
        return True
    else:
        logger.error("❌ FAILED: No results returned")
        return False


def test_turkey_query():
    """Test Turkey league query with Turkish characters (ş, ı, ğ)"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Turkey League Query (Turkish characters)")
    logger.info("="*70)

    query = "(site:fanatik.com.tr OR site:turkish-football.com OR site:dailysabah.com) (rotasyon OR yedek ağırlıklı OR kadro dışı) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal"

    provider = get_brave_provider()

    if not provider.is_available():
        logger.warning("⚠️ Brave Search not available - skipping test")
        return None

    logger.info(f"Query length: {len(query)} characters")
    logger.info(f"Query preview: {query[:100]}...")

    results = provider.search_news(query, limit=5, component="test_turkey")

    if results:
        logger.info(f"✅ SUCCESS: Found {len(results)} results")
        for i, result in enumerate(results[:2], 1):
            logger.info(f"  {i}. {result.get('title', 'N/A')[:60]}...")
            logger.info(f"     URL: {result.get('url', 'N/A')[:80]}...")
        return True
    else:
        logger.error("❌ FAILED: No results returned")
        return False


def test_mexico_query():
    """Test Mexico league query with Spanish characters"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Mexico League Query (Spanish characters)")
    logger.info("="*70)

    query = "(site:mediotiempo.com OR site:espn.com.mx OR site:record.com.mx) (rotation squad OR equipo alternativo OR descanso titulares) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal"

    provider = get_brave_provider()

    if not provider.is_available():
        logger.warning("⚠️ Brave Search not available - skipping test")
        return None

    logger.info(f"Query length: {len(query)} characters")
    logger.info(f"Query preview: {query[:100]}...")

    results = provider.search_news(query, limit=5, component="test_mexico")

    if results:
        logger.info(f"✅ SUCCESS: Found {len(results)} results")
        for i, result in enumerate(results[:2], 1):
            logger.info(f"  {i}. {result.get('title', 'N/A')[:60]}...")
            logger.info(f"     URL: {result.get('url', 'N/A')[:80]}...")
        return True
    else:
        logger.error("❌ FAILED: No results returned")
        return False


def test_greece_query():
    """Test Greece league query with Greek characters"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Greece League Query (Greek characters)")
    logger.info("="*70)

    query = "(site:agonasport.com OR site:greekcitytimes.com OR site:gazzetta.gr) (rotation expected OR rested for europe OR reserves) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal"

    provider = get_brave_provider()

    if not provider.is_available():
        logger.warning("⚠️ Brave Search not available - skipping test")
        return None

    logger.info(f"Query length: {len(query)} characters")
    logger.info(f"Query preview: {query[:100]}...")

    results = provider.search_news(query, limit=5, component="test_greece")

    if results:
        logger.info(f"✅ SUCCESS: Found {len(results)} results")
        for i, result in enumerate(results[:2], 1):
            logger.info(f"  {i}. {result.get('title', 'N/A')[:60]}...")
            logger.info(f"     URL: {result.get('url', 'N/A')[:80]}...")
        return True
    else:
        logger.error("❌ FAILED: No results returned")
        return False


def test_simple_query():
    """Test simple English query as baseline"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Simple English Query (baseline)")
    logger.info("="*70)

    query = "football news premier league"

    provider = get_brave_provider()

    if not provider.is_available():
        logger.warning("⚠️ Brave Search not available - skipping test")
        return None

    logger.info(f"Query: {query}")

    results = provider.search_news(query, limit=5, component="test_simple")

    if results:
        logger.info(f"✅ SUCCESS: Found {len(results)} results")
        for i, result in enumerate(results[:2], 1):
            logger.info(f"  {i}. {result.get('title', 'N/A')[:60]}...")
        return True
    else:
        logger.error("❌ FAILED: No results returned")
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "="*70)
    logger.info("BRAVE SEARCH DOUBLE ENCODING FIX - TEST SUITE")
    logger.info("="*70)
    logger.info("Bug #7: Brave Search API - HTTP 422 Error")
    logger.info("Fix: Removed manual URL encoding to prevent double encoding")
    logger.info("="*70)

    # Check API key
    api_key = os.environ.get('BRAVE_API_KEY_1')
    if not api_key:
        logger.error("❌ BRAVE_API_KEY_1 not found in environment")
        logger.info("Please set BRAVE_API_KEY_1 in .env file")
        return

    logger.info(f"✅ API Key found: {api_key[:10]}...{api_key[-10:]}")

    # Run tests
    tests = [
        ("Simple Query", test_simple_query),
        ("Argentina Query", test_argentina_query),
        ("Turkey Query", test_turkey_query),
        ("Mexico Query", test_mexico_query),
        ("Greece Query", test_greece_query),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ {test_name} raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)

    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)

    for test_name, result in results:
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️ SKIPPED"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {len(results)} tests")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Skipped: {skipped}")

    if failed == 0 and skipped == 0:
        logger.info("\n✅ ALL TESTS PASSED - Double encoding fix is working correctly!")
        return 0
    elif failed > 0:
        logger.error(f"\n❌ {failed} TEST(S) FAILED - Double encoding fix may not be working correctly")
        return 1
    else:
        logger.warning(f"\n⚠️ {skipped} TEST(S) SKIPPED - Brave Search not available")
        return 0


if __name__ == "__main__":
    sys.exit(main())
