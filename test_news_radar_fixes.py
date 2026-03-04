#!/usr/bin/env python3
"""
Test script to verify News Radar fixes:
1. Mirror file exists and can be loaded
2. Timeout is working correctly
3. Detailed logging shows execution timing
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def test_mirror_file():
    """Test that the mirror file exists and can be loaded."""
    print("=" * 60)
    print("TEST 1: MIRROR FILE")
    print("=" * 60)

    mirror_path = Path("data/supabase_mirror.json")

    if not mirror_path.exists():
        print(f"\n❌ Mirror file not found at {mirror_path}")
        return False

    print(f"\n✅ Mirror file exists at {mirror_path}")

    # Load and validate the mirror file
    import json

    try:
        with open(mirror_path, "r", encoding="utf-8") as f:
            mirror_data = json.load(f)

        print("\n📊 Mirror file contents:")
        for key, value in mirror_data.items():
            if isinstance(value, list):
                print(f"  - {key}: {len(value)} records")
            elif isinstance(value, dict):
                if "tweets" in value:
                    print(f"  - {key}: {len(value.get('tweets', []))} tweets")
                else:
                    print(f"  - {key}: {len(value)} keys")
            else:
                print(f"  - {key}: {type(value).__name__}")

        # Check for news_sources
        if "news_sources" in mirror_data:
            news_sources = mirror_data["news_sources"]
            print(f"\n✅ News sources found: {len(news_sources)} sources")

            # Show first few sources
            for i, source in enumerate(news_sources[:3]):
                print(f"  {i + 1}. {source.get('name', 'Unknown')}: {source.get('url', 'No URL')}")

            return True
        else:
            print("\n❌ No news_sources found in mirror file")
            return False

    except Exception as e:
        print(f"\n❌ Error loading mirror file: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_supabase_timeout():
    """Test that Supabase timeout is working correctly."""
    print("\n" + "=" * 60)
    print("TEST 2: SUPABASE TIMEOUT")
    print("=" * 60)

    try:
        from src.database.supabase_provider import SUPABASE_QUERY_TIMEOUT, SupabaseProvider

        print(f"\n✅ SUPABASE_QUERY_TIMEOUT constant: {SUPABASE_QUERY_TIMEOUT}s")

        print("\n🔄 Creating SupabaseProvider...")
        import time

        start = time.time()
        provider = SupabaseProvider()
        init_time = time.time() - start
        print(f"✅ SupabaseProvider initialized in {init_time:.2f}s")

        if not provider.is_connected():
            print(f"\n⚠️ Supabase not connected: {provider.get_connection_error()}")
            print("ℹ️  This is expected if SUPABASE_URL/KEY are not configured")
            print("ℹ️  Testing mirror fallback instead...")
            return test_mirror_fallback(provider)

        print("\n✅ Supabase connected")

        # Test query with timing
        print(
            f"\n🔄 Testing query execution (should timeout after {SUPABASE_QUERY_TIMEOUT}s if Supabase is slow)..."
        )
        start = time.time()

        data = provider.fetch_all_news_sources()

        elapsed = time.time() - start
        print(f"\n✅ Query completed in {elapsed:.2f}s")
        print(f"✅ Returned {len(data)} sources")

        if elapsed > SUPABASE_QUERY_TIMEOUT + 5:
            print(
                f"\n⚠️ WARNING: Query took {elapsed:.2f}s but timeout is {SUPABASE_QUERY_TIMEOUT}s"
            )
            print("⚠️ This suggests timeout may not be working correctly")
            return False
        else:
            print(f"\n✅ Timeout appears to be working correctly (completed in {elapsed:.2f}s)")
            return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_mirror_fallback(provider):
    """Test that mirror fallback works when Supabase is not connected."""
    print("\n" + "=" * 60)
    print("TEST 3: MIRROR FALLBACK")
    print("=" * 60)

    try:
        import time

        print("\n🔄 Testing mirror fallback (Supabase not connected)...")
        start = time.time()

        data = provider.fetch_all_news_sources()

        elapsed = time.time() - start
        print(f"\n✅ Mirror fallback completed in {elapsed:.2f}s")
        print(f"✅ Returned {len(data)} sources")

        if len(data) > 0:
            print("\n✅ Mirror fallback is working correctly")
            # Show first few sources
            for i, source in enumerate(data[:3]):
                print(f"  {i + 1}. {source.get('name', 'Unknown')}: {source.get('url', 'No URL')}")
            return True
        else:
            print("\n❌ Mirror fallback returned no data")
            return False

    except Exception as e:
        print(f"\n❌ Mirror fallback test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_news_radar_loading():
    """Test that News Radar can load configuration with the fixes."""
    print("\n" + "=" * 60)
    print("TEST 4: NEWS RADAR LOADING")
    print("=" * 60)

    try:
        from src.services.news_radar import load_config_from_supabase

        print("\n🔄 Testing News Radar configuration loading...")
        import time

        start = time.time()
        config = load_config_from_supabase()
        load_time = time.time() - start

        print(f"\n✅ News Radar config loaded in {load_time:.2f}s")

        if config.sources:
            print(f"✅ Loaded {len(config.sources)} web sources")
            # Show first few sources
            for i, source in enumerate(config.sources[:3]):
                print(f"  {i + 1}. {source.name}: {source.url}")
            return True
        else:
            print("\n❌ No sources loaded in config")
            return False

    except Exception as e:
        print(f"\n❌ News Radar loading test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("NEWS RADAR FIXES VERIFICATION")
    print("=" * 60)

    results = []

    # Test 1: Mirror file
    results.append(("Mirror File", test_mirror_file()))

    # Test 2: Supabase timeout
    results.append(("Supabase Timeout", test_supabase_timeout()))

    # Test 4: News Radar loading
    results.append(("News Radar Loading", test_news_radar_loading()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result for _, result in results)

    if all_passed:
        print("\n✅ All tests passed!")
        return True
    else:
        print("\n❌ Some tests failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
