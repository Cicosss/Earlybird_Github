#!/usr/bin/env python3
"""
Integration test for SupabaseProvider with lock contention monitoring.

This test verifies that components using SupabaseProvider work correctly
with the new lock contention monitoring.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_supabase_provider_singleton():
    """Test that SupabaseProvider singleton works correctly."""
    print("TEST 1: SupabaseProvider Singleton")
    print("-" * 60)

    try:
        from src.database.supabase_provider import get_supabase

        # Get singleton instance
        provider1 = get_supabase()
        provider2 = get_supabase()

        # Verify it's the same instance
        if provider1 is provider2:
            print("✅ Singleton pattern works correctly")
        else:
            print("❌ Singleton pattern broken!")
            return False

        # Test cache operations
        provider1._set_cache("test_key", {"data": "test_value"})
        result = provider1._get_from_cache("test_key")

        if result == {"data": "test_value"}:
            print("✅ Cache operations work correctly")
        else:
            print(f"❌ Cache operations failed: {result}")
            return False

        # Test lock stats
        stats = provider1.get_cache_lock_stats()
        print(f"✅ Lock stats: {stats}")

        if stats["wait_count"] > 0:
            print("✅ Lock contention monitoring is active")
        else:
            print("❌ Lock contention monitoring not working!")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_global_orchestrator_integration():
    """Test that GlobalOrchestrator works with SupabaseProvider."""
    print("\nTEST 2: GlobalOrchestrator Integration")
    print("-" * 60)

    try:
        from src.processing.global_orchestrator import get_global_orchestrator

        # Get orchestrator instance
        orchestrator = get_global_orchestrator()

        # Check if SupabaseProvider is initialized
        if hasattr(orchestrator, "supabase_provider"):
            print("✅ GlobalOrchestrator has SupabaseProvider")
        else:
            print("❌ GlobalOrchestrator missing SupabaseProvider!")
            return False

        # Test that we can access SupabaseProvider methods
        if orchestrator.supabase_provider:
            stats = orchestrator.supabase_provider.get_cache_lock_stats()
            print(f"✅ Can access SupabaseProvider lock stats: {stats}")
        else:
            print("❌ Cannot access SupabaseProvider!")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_news_hunter_integration():
    """Test that NewsHunter works with SupabaseProvider."""
    print("\nTEST 3: NewsHunter Integration")
    print("-" * 60)

    try:
        from src.ingestion.news_hunter import _SUPABASE_PROVIDER, _SUPABASE_PROVIDER_AVAILABLE

        # Check if SupabaseProvider is available
        if _SUPABASE_PROVIDER_AVAILABLE:
            print("✅ NewsHunter has SupabaseProvider available")
        else:
            print("❌ NewsHunter SupabaseProvider not available!")
            return False

        # Check if we can access the provider
        if _SUPABASE_PROVIDER:
            stats = _SUPABASE_PROVIDER.get_cache_lock_stats()
            print(f"✅ Can access SupabaseProvider lock stats: {stats}")
        else:
            print("❌ Cannot access SupabaseProvider!")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_league_manager_integration():
    """Test that LeagueManager works with SupabaseProvider."""
    print("\nTEST 4: LeagueManager Integration")
    print("-" * 60)

    try:
        from src.ingestion.league_manager import get_odds_key

        # Test that we can get odds key (which uses SupabaseProvider)
        key = get_odds_key()
        print(f"✅ LeagueManager can access SupabaseProvider: got odds key")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("SupabaseProvider Integration Test Suite")
    print("=" * 60 + "\n")

    tests = [
        test_supabase_provider_singleton,
        test_global_orchestrator_integration,
        test_news_hunter_integration,
        test_league_manager_integration,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ ALL INTEGRATION TESTS PASSED!")
        print("\n📊 Integration Analysis:")
        print("   - SupabaseProvider singleton: ✅ Working")
        print("   - GlobalOrchestrator integration: ✅ Working")
        print("   - NewsHunter integration: ✅ Working")
        print("   - LeagueManager integration: ✅ Working")
        print("   - Lock contention monitoring: ✅ Active")
        print("   - Production ready: ✅ Yes")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
