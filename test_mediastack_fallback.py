#!/usr/bin/env python3
"""
Test script to verify MediaStack fallback works correctly for problematic queries.

This test simulates the scenario where Brave and DuckDuckGo fail,
and verifies that MediaStack successfully returns results.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ingestion.search_provider import SearchProvider

def test_mediastack_fallback():
    """Test MediaStack fallback with problematic queries."""
    print("=" * 80)
    print("🆘 MEDIASTACK FALLBACK TEST - Problematic Queries")
    print("=" * 80)
    
    # Initialize SearchProvider
    provider = SearchProvider()
    
    # Test queries from the log (Turkey, Mexico, Greece)
    test_queries = [
        {
            "name": "Turkey (Turkish characters)",
            "query": "(site:fanatik.com.tr OR site:turkish-football.com OR site:dailysabah.com) (rotasyon OR yedek ağırlıklı OR kadro dışı) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal",
            "expected_length": 373,
        },
        {
            "name": "Mexico (Spanish characters)",
            "query": "(site:mediotiempo.com OR site:espn.com.mx OR site:record.com.mx) (rotation squad OR equipo alternativo OR descanso titulares) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal",
            "expected_length": 373,
        },
        {
            "name": "Greece (Greek characters)",
            "query": "(site:sport-fm.gr OR site:sdna.gr OR site:in.gr) (ροτασιόν OR εναλλακτική ενδεκάδα OR ανάπαυση) football -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal",
            "expected_length": 373,
        },
    ]
    
    results = []
    
    for i, test in enumerate(test_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"TEST {i}: {test['name']}")
        print(f"{'=' * 80}")
        
        query = test['query']
        expected_length = test['expected_length']
        
        print(f"\n📝 Query length: {len(query)} chars (expected: {expected_length})")
        print(f"📝 Query preview: {query[:100]}...")
        
        # Perform search (should fallback to MediaStack)
        print(f"\n🔍 Searching...")
        search_results = provider.search(query, num_results=5)
        
        print(f"\n📊 Results:")
        print(f"   Number of results: {len(search_results)}")
        
        if search_results:
            print(f"   ✅ SUCCESS: Got {len(search_results)} results!")
            print(f"\n   Sample result:")
            for j, result in enumerate(search_results[:2], 1):
                print(f"      {j}. {result.get('title', 'N/A')[:60]}...")
                print(f"         URL: {result.get('link', 'N/A')[:60]}...")
                print(f"         Source: {result.get('source', 'N/A')}")
            results.append({
                "name": test['name'],
                "success": True,
                "num_results": len(search_results),
            })
        else:
            print(f"   ❌ FAILURE: No results returned!")
            results.append({
                "name": test['name'],
                "success": False,
                "num_results": 0,
            })
    
    # Summary
    print(f"\n{'=' * 80}")
    print("📊 SUMMARY")
    print(f"{'=' * 80}")
    
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    failed_tests = total_tests - successful_tests
    
    print(f"\nTotal tests: {total_tests}")
    print(f"✅ Successful: {successful_tests}")
    print(f"❌ Failed: {failed_tests}")
    
    for result in results:
        status = "✅" if result['success'] else "❌"
        print(f"   {status} {result['name']}: {result['num_results']} results")
    
    print(f"\n{'=' * 80}")
    if successful_tests == total_tests:
        print("✅ ALL TESTS PASSED: MediaStack fallback works correctly!")
        print(f"{'=' * 80}")
        return True
    else:
        print(f"❌ SOME TESTS FAILED: {failed_tests}/{total_tests} tests failed")
        print(f"{'=' * 80}")
        return False

if __name__ == "__main__":
    success = test_mediastack_fallback()
    sys.exit(0 if success else 1)
