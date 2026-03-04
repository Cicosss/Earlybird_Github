#!/usr/bin/env python3
"""
Simple test to verify mirror fallback works correctly.
This test disables Supabase connection to force mirror fallback.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def main():
    """Test mirror fallback without Supabase connection."""
    print("=" * 60)
    print("MIRROR FALLBACK TEST")
    print("=" * 60)

    # Temporarily disable Supabase to force mirror fallback
    print("\n🔄 Temporarily disabling Supabase connection...")
    original_url = os.getenv("SUPABASE_URL")
    original_key = os.getenv("SUPABASE_KEY")
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_KEY"] = ""

    try:
        import time

        from src.database.supabase_provider import SupabaseProvider

        print("\n🔄 Creating SupabaseProvider (will fail to connect)...")
        start = time.time()
        provider = SupabaseProvider()
        init_time = time.time() - start
        print(f"✅ SupabaseProvider initialized in {init_time:.2f}s")

        if provider.is_connected():
            print("\n⚠️ Unexpected: Supabase connected (should have failed)")
            return False

        print(f"\n✅ Supabase connection failed as expected: {provider.get_connection_error()}")

        # Test mirror fallback
        print("\n🔄 Testing mirror fallback for news_sources...")
        start = time.time()
        data = provider.fetch_all_news_sources()
        fetch_time = time.time() - start

        print(f"\n✅ Mirror fallback completed in {fetch_time:.2f}s")
        print(f"✅ Returned {len(data)} sources")

        if len(data) > 0:
            print("\n✅ Mirror fallback is working correctly!")
            # Show first few sources
            for i, source in enumerate(data[:3]):
                print(f"  {i + 1}. {source.get('name', 'Unknown')}: {source.get('url', 'No URL')}")
            return True
        else:
            print("\n❌ Mirror fallback returned no data")
            return False

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Restore original environment variables
        if original_url:
            os.environ["SUPABASE_URL"] = original_url
        if original_key:
            os.environ["SUPABASE_KEY"] = original_key


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
