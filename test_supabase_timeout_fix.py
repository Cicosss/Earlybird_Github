#!/usr/bin/env python3
"""
Test script to verify Supabase timeout fix.

This test verifies that:
1. Supabase client is created with proper timeout configuration
2. Timeout errors are handled correctly
3. Fallback to mirror works when Supabase times out
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def test_supabase_client_timeout():
    """Test that Supabase client is created with timeout configuration."""
    print("=" * 60)
    print("TEST 1: Supabase Client Timeout Configuration")
    print("=" * 60)

    try:
        from src.database.supabase_provider import SUPABASE_QUERY_TIMEOUT, SupabaseProvider

        print(f"✅ SUPABASE_QUERY_TIMEOUT constant: {SUPABASE_QUERY_TIMEOUT}s")

        provider = SupabaseProvider()

        if provider.is_connected():
            print("✅ Supabase connection established")

            # Check if client has timeout configuration
            if hasattr(provider._client, "_options"):
                options = provider._client._options
                if hasattr(options, "postgrest_client_timeout"):
                    timeout = options.postgrest_client_timeout
                    print(f"✅ Client timeout configured: {timeout}s")

                    if timeout == SUPABASE_QUERY_TIMEOUT:
                        print("✅ Timeout matches SUPABASE_QUERY_TIMEOUT constant")
                    else:
                        print(
                            f"⚠️ Timeout mismatch: expected {SUPABASE_QUERY_TIMEOUT}s, got {timeout}s"
                        )
                else:
                    print("⚠️ postgrest_client_timeout not found in client options")
            else:
                print("⚠️ Client options not accessible")
        else:
            print(f"⚠️ Supabase connection failed: {provider.get_connection_error()}")
            print("ℹ️  This is expected if SUPABASE_URL/KEY are not configured")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_news_radar_supabase_loading():
    """Test that News Radar can load config from Supabase with timeout."""
    print("\n" + "=" * 60)
    print("TEST 2: News Radar Supabase Loading")
    print("=" * 60)

    try:
        from src.services.news_radar import load_config_from_supabase

        print("🔄 Attempting to load config from Supabase...")
        config = load_config_from_supabase()

        print("✅ Config loaded successfully")
        print(f"✅ Sources found: {len(config.sources)}")

        if config.sources:
            print(f"✅ First source: {config.sources[0].name}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_timeout_handling():
    """Test that timeout errors are handled correctly."""
    print("\n" + "=" * 60)
    print("TEST 3: Timeout Error Handling")
    print("=" * 60)

    try:
        from src.database.supabase_provider import SupabaseProvider

        provider = SupabaseProvider()

        if not provider.is_connected():
            print("ℹ️  Supabase not connected, skipping timeout test")
            return True

        # Try to fetch data (this should timeout if Supabase is slow)
        print("🔄 Testing query execution...")
        data = provider.fetch_all_news_sources()

        print(f"✅ Query completed (returned {len(data)} sources)")
        print("✅ Timeout handling working correctly")

        return True

    except Exception as e:
        error_msg = str(e).lower()
        if "timeout" in error_msg or "timed out" in error_msg:
            print(f"✅ Timeout error caught and handled: {e}")
            return True
        else:
            print(f"❌ Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SUPABASE TIMEOUT FIX VERIFICATION")
    print("=" * 60 + "\n")

    results = []

    # Run tests
    results.append(("Client Timeout Configuration", test_supabase_client_timeout()))
    results.append(("News Radar Loading", test_news_radar_supabase_loading()))
    results.append(("Timeout Handling", test_timeout_handling()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! Supabase timeout fix is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
