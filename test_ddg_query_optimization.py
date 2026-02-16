#!/usr/bin/env python3
"""
Test DDG Query Optimization V9.5

Verifica che:
1. _optimize_query_for_ddg funzioni correttamente in tavily_provider.py
2. _get_query_variations generi le variazioni corrette in search_provider.py
3. La query degradation riduca gli errori "No results found"
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def test_optimize_query_for_ddg():
    """Test _optimize_query_for_ddg in tavily_provider.py"""
    print("\n" + "=" * 60)
    print("TEST 1: _optimize_query_for_ddg (tavily_provider.py)")
    print("=" * 60)

    try:
        from src.ingestion.tavily_provider import TavilyProvider

        # Create a mock provider (we only need the method)
        provider = TavilyProvider()

        # Test 1: Short query (should not be modified)
        short_query = '"Team Name" football'
        result = provider._optimize_query_for_ddg(short_query)
        assert result == short_query, f"Short query should not be modified: {result}"
        print(f"✅ Test 1.1: Short query unchanged: {len(result)} chars")

        # Test 2: Long query with sport exclusions (should remove exclusions)
        long_query = '"Team Name" (site:domain1.com OR site:domain2.com) (injury OR lineup) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal'
        result = provider._optimize_query_for_ddg(long_query)
        assert len(result) <= 280, f"Optimized query should be <= 280 chars: {len(result)}"
        assert "-basket" not in result, "Sport exclusions should be removed"
        print(f"✅ Test 1.2: Long query optimized: {len(long_query)} → {len(result)} chars")

        # Test 3: Query with site dork (should remove dork if still too long)
        query_with_dork = '"Team Name" (site:domain1.com OR site:domain2.com OR site:domain3.com OR site:domain4.com) (injury OR lineup OR squad) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal'
        result = provider._optimize_query_for_ddg(query_with_dork)
        assert len(result) <= 280, f"Optimized query should be <= 280 chars: {len(result)}"
        print(f"✅ Test 1.3: Query with site dork optimized: {len(query_with_dork)} → {len(result)} chars")

        print("\n✅ All tests for _optimize_query_for_ddg PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_query_variations():
    """Test _get_query_variations in search_provider.py"""
    print("\n" + "=" * 60)
    print("TEST 2: _get_query_variations (search_provider.py)")
    print("=" * 60)

    try:
        from src.ingestion.search_provider import SearchProvider

        provider = SearchProvider()

        # Test 1: Simple query (should return 1 variation)
        simple_query = '"Team Name" football'
        variations = provider._get_query_variations(simple_query)
        assert len(variations) >= 1, f"Should have at least 1 variation: {len(variations)}"
        print(f"✅ Test 2.1: Simple query generates {len(variations)} variation(s)")

        # Test 2: Query with sport exclusions (should return 2+ variations)
        query_with_exclusions = '"Team Name" (injury OR lineup) football -basket -basketball -euroleague -nba'
        variations = provider._get_query_variations(query_with_exclusions)
        assert len(variations) >= 2, f"Should have at least 2 variations: {len(variations)}"
        # First variation should be optimized
        assert len(variations[0]) <= 280, f"First variation should be optimized: {len(variations[0])}"
        # Second variation should be without exclusions
        assert "-basket" not in variations[1], "Second variation should exclude sport terms"
        print(f"✅ Test 2.2: Query with exclusions generates {len(variations)} variations")
        for i, v in enumerate(variations):
            print(f"   Variation {i+1}: {v[:80]}... ({len(v)} chars)")

        # Test 3: Query with site dork (should return 3+ variations)
        query_with_dork = '"Team Name" (site:domain1.com OR site:domain2.com) (injury OR lineup) football -basket -basketball -euroleague -nba'
        variations = provider._get_query_variations(query_with_dork)
        assert len(variations) >= 3, f"Should have at least 3 variations: {len(variations)}"
        # Third variation should be without site dork
        assert "site:" not in variations[2], "Third variation should exclude site dork"
        print(f"✅ Test 2.3: Query with site dork generates {len(variations)} variations")
        for i, v in enumerate(variations):
            print(f"   Variation {i+1}: {v[:80]}... ({len(v)} chars)")

        # Test 4: Complex query (should return 4 variations)
        complex_query = '"Team Name" (site:domain1.com OR site:domain2.com OR site:domain3.com) (injury OR lineup OR squad) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal'
        variations = provider._get_query_variations(complex_query)
        assert len(variations) == 4, f"Should have exactly 4 variations: {len(variations)}"
        print(f"✅ Test 2.4: Complex query generates {len(variations)} variations")
        for i, v in enumerate(variations):
            print(f"   Variation {i+1}: {v[:80]}... ({len(v)} chars)")

        print("\n✅ All tests for _get_query_variations PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_degradation_integration():
    """Test query degradation integration"""
    print("\n" + "=" * 60)
    print("TEST 3: Query Degradation Integration")
    print("=" * 60)

    try:
        from src.ingestion.search_provider import SearchProvider

        provider = SearchProvider()

        # Test with a very long query that would fail without optimization
        long_query = '"Galatasaray" (site:fanatik.com.tr OR site:turkish-football.com OR site:dailysabah.com) (injury OR lineup OR squad) futbol -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal'

        print(f"Original query length: {len(long_query)} chars")
        print(f"Query: {long_query[:100]}...")

        # Generate variations
        variations = provider._get_query_variations(long_query)
        print(f"\nGenerated {len(variations)} variations:")

        for i, variation in enumerate(variations):
            print(f"\nVariation {i+1}:")
            print(f"  Length: {len(variation)} chars")
            print(f"  Query: {variation[:100]}...")

            # Verify each variation is within DDG limits
            assert len(variation) <= 280, f"Variation {i+1} exceeds DDG limit: {len(variation)}"

        print("\n✅ All variations are within DDG limits (≤280 chars)")
        print("\n✅ Query degradation integration test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("DDG Query Optimization V9.5 - Test Suite")
    print("=" * 60)

    results = []

    # Run all tests
    results.append(("_optimize_query_for_ddg", test_optimize_query_for_ddg()))
    results.append(("_get_query_variations", test_get_query_variations()))
    results.append(("Query Degradation Integration", test_query_degradation_integration()))

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests PASSED!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
