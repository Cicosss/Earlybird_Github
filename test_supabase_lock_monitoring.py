#!/usr/bin/env python3
"""
Test script to verify SupabaseProvider lock contention monitoring fix.

This script tests:
1. The _acquire_cache_lock_with_monitoring method exists and works
2. All cache operations use the monitoring method
3. Lock stats are correctly tracked
"""

import sys
import os
import time
import threading

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.supabase_provider import SupabaseProvider


def test_method_exists():
    """Test that the _acquire_cache_lock_with_monitoring method exists."""
    print("=" * 60)
    print("TEST 1: Method Existence")
    print("=" * 60)

    provider = SupabaseProvider()

    # Check if method exists
    if hasattr(provider, '_acquire_cache_lock_with_monitoring'):
        print("✅ _acquire_cache_lock_with_monitoring method exists")
    else:
        print("❌ _acquire_cache_lock_with_monitoring method NOT found")
        return False

    # Check if metrics are initialized
    if hasattr(provider, '_cache_lock_wait_time'):
        print("✅ _cache_lock_wait_time metric initialized")
    else:
        print("❌ _cache_lock_wait_time metric NOT initialized")
        return False

    if hasattr(provider, '_cache_lock_wait_count'):
        print("✅ _cache_lock_wait_count metric initialized")
    else:
        print("❌ _cache_lock_wait_count metric NOT initialized")
        return False

    if hasattr(provider, '_cache_lock_timeout_count'):
        print("✅ _cache_lock_timeout_count metric initialized")
    else:
        print("❌ _cache_lock_timeout_count metric NOT initialized")
        return False

    print()
    return True


def test_lock_acquisition():
    """Test that lock acquisition works with monitoring."""
    print("=" * 60)
    print("TEST 2: Lock Acquisition with Monitoring")
    print("=" * 60)

    provider = SupabaseProvider()

    # Get initial stats
    initial_stats = provider.get_cache_lock_stats()
    print(f"Initial stats: {initial_stats}")

    # Acquire lock multiple times
    for i in range(5):
        acquired = provider._acquire_cache_lock_with_monitoring(timeout=5.0)
        if acquired:
            print(f"✅ Lock acquisition {i+1} successful")
            provider._cache_lock.release()
        else:
            print(f"❌ Lock acquisition {i+1} failed")
            return False

    # Check updated stats
    updated_stats = provider.get_cache_lock_stats()
    print(f"Updated stats: {updated_stats}")

    if updated_stats['wait_count'] == initial_stats['wait_count'] + 5:
        print(f"✅ Wait count increased correctly: {updated_stats['wait_count']}")
    else:
        print(f"❌ Wait count NOT increased correctly: {updated_stats['wait_count']}")
        return False

    if updated_stats['wait_time_total'] > initial_stats['wait_time_total']:
        print(f"✅ Wait time increased: {updated_stats['wait_time_total']:.3f}s")
    else:
        print(f"❌ Wait time NOT increased")
        return False

    print()
    return True


def test_cache_operations():
    """Test that cache operations use monitoring."""
    print("=" * 60)
    print("TEST 3: Cache Operations with Monitoring")
    print("=" * 60)

    provider = SupabaseProvider()

    # Get initial stats
    initial_stats = provider.get_cache_lock_stats()
    print(f"Initial stats: {initial_stats}")

    # Test _set_cache
    provider._set_cache("test_key", {"data": "test_value"})
    print("✅ _set_cache executed")

    # Test _get_from_cache
    result = provider._get_from_cache("test_key")
    if result == {"data": "test_value"}:
        print("✅ _get_from_cache retrieved data correctly")
    else:
        print(f"❌ _get_from_cache retrieved incorrect data: {result}")
        return False

    # Test _is_cache_valid
    is_valid = provider._is_cache_valid("test_key")
    if is_valid:
        print("✅ _is_cache_valid returned True")
    else:
        print("❌ _is_cache_valid returned False")
        return False

    # Test invalidate_cache
    provider.invalidate_cache("test_key")
    print("✅ invalidate_cache executed")

    # Check updated stats
    updated_stats = provider.get_cache_lock_stats()
    print(f"Updated stats: {updated_stats}")

    if updated_stats['wait_count'] > initial_stats['wait_count']:
        print(f"✅ Wait count increased: {updated_stats['wait_count']}")
    else:
        print(f"❌ Wait count NOT increased")
        return False

    print()
    return True


def test_concurrent_access():
    """Test that concurrent access works correctly."""
    print("=" * 60)
    print("TEST 4: Concurrent Access")
    print("=" * 60)

    provider = SupabaseProvider()

    # Get initial stats
    initial_stats = provider.get_cache_lock_stats()
    print(f"Initial stats: {initial_stats}")

    # Create multiple threads that access cache
    def cache_worker(worker_id):
        for i in range(10):
            key = f"worker_{worker_id}_key_{i}"
            provider._set_cache(key, {"worker": worker_id, "iteration": i})
            result = provider._get_from_cache(key)
            if result != {"worker": worker_id, "iteration": i}:
                print(f"❌ Worker {worker_id} iteration {i} got incorrect data")
                return False
        return True

    threads = []
    for i in range(3):
        t = threading.Thread(target=cache_worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    print("✅ All threads completed successfully")

    # Check updated stats
    updated_stats = provider.get_cache_lock_stats()
    print(f"Updated stats: {updated_stats}")

    if updated_stats['wait_count'] > initial_stats['wait_count']:
        print(f"✅ Wait count increased: {updated_stats['wait_count']}")
    else:
        print(f"❌ Wait count NOT increased")
        return False

    print()
    return True


def test_get_cache_lock_stats():
    """Test that get_cache_lock_stats returns correct format."""
    print("=" * 60)
    print("TEST 5: get_cache_lock_stats Method")
    print("=" * 60)

    provider = SupabaseProvider()

    stats = provider.get_cache_lock_stats()
    print(f"Stats: {stats}")

    # Check required keys
    required_keys = ['wait_count', 'wait_time_total', 'wait_time_avg', 'timeout_count']
    for key in required_keys:
        if key in stats:
            print(f"✅ Stats has key: {key}")
        else:
            print(f"❌ Stats missing key: {key}")
            return False

    # Check data types
    if isinstance(stats['wait_count'], int):
        print(f"✅ wait_count is int: {stats['wait_count']}")
    else:
        print(f"❌ wait_count is not int: {type(stats['wait_count'])}")
        return False

    if isinstance(stats['wait_time_total'], (int, float)):
        print(f"✅ wait_time_total is number: {stats['wait_time_total']}")
    else:
        print(f"❌ wait_time_total is not number: {type(stats['wait_time_total'])}")
        return False

    if isinstance(stats['wait_time_avg'], (int, float)):
        print(f"✅ wait_time_avg is number: {stats['wait_time_avg']}")
    else:
        print(f"❌ wait_time_avg is not number: {type(stats['wait_time_avg'])}")
        return False

    if isinstance(stats['timeout_count'], int):
        print(f"✅ timeout_count is int: {stats['timeout_count']}")
    else:
        print(f"❌ timeout_count is not int: {type(stats['timeout_count'])}")
        return False

    print()
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SupabaseProvider Lock Contention Monitoring Test Suite")
    print("=" * 60 + "\n")

    tests = [
        test_method_exists,
        test_lock_acquisition,
        test_cache_operations,
        test_concurrent_access,
        test_get_cache_lock_stats,
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
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe SupabaseProvider lock contention monitoring fix is working correctly.")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
