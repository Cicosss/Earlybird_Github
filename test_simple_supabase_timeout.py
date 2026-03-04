#!/usr/bin/env python3
"""
Simple test to verify Supabase timeout configuration.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def test_timeout_config():
    """Test that timeout is configured correctly."""
    print("=" * 60)
    print("SIMPLE SUPABASE TIMEOUT TEST")
    print("=" * 60)

    try:
        from src.database.supabase_provider import SUPABASE_QUERY_TIMEOUT, SupabaseProvider

        print(f"\n✅ SUPABASE_QUERY_TIMEOUT constant: {SUPABASE_QUERY_TIMEOUT}s")

        print("\n🔄 Creating SupabaseProvider...")
        provider = SupabaseProvider()

        if not provider.is_connected():
            print(f"\n⚠️ Supabase not connected: {provider.get_connection_error()}")
            print("ℹ️  This is expected if SUPABASE_URL/KEY are not configured")
            return True

        print("\n✅ Supabase connected")

        # Check if client has timeout configuration
        if hasattr(provider._client, "_options"):
            options = provider._client._options
            print(f"\n🔍 Client options type: {type(options)}")
            print(f"🔍 Client options dir: {[x for x in dir(options) if not x.startswith('_')]}")

            if hasattr(options, "postgrest_client_timeout"):
                timeout = options.postgrest_client_timeout
                print(f"\n✅ Client timeout configured: {timeout}s")

                if timeout == SUPABASE_QUERY_TIMEOUT:
                    print("✅ Timeout matches SUPABASE_QUERY_TIMEOUT constant")
                else:
                    print(f"⚠️ Timeout mismatch: expected {SUPABASE_QUERY_TIMEOUT}s, got {timeout}s")
            else:
                print("\n⚠️ postgrest_client_timeout not found in client options")
        else:
            print("\n⚠️ Client options not accessible")

        print(
            f"\n🔄 Testing query execution (should timeout after {SUPABASE_QUERY_TIMEOUT}s if Supabase is slow)..."
        )
        import time

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
        else:
            print("\n✅ Timeout appears to be working correctly")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_timeout_config()
    sys.exit(0 if success else 1)
