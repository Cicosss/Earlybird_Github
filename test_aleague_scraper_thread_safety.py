"""
Thread Safety Test for ALeagueScraper VPS Fixes

This test verifies that all three critical thread-safety issues have been fixed:
1. Race condition in _last_scrape_time (atomic check-and-mark)
2. Race condition in is_available() cache (atomic check-and-set)
3. Retry logic for availability check (5-minute re-check interval)
"""

import threading
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

# Import the module to test
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ingestion.aleague_scraper import (
    _last_scrape_time,
    _scrape_time_lock,
    _try_acquire_scrape_lock,
    _should_scrape,
    _mark_scraped,
    ALeagueScraper,
    get_aleague_scraper,
)


def test_fix1_atomic_scrape_lock():
    """
    Test Fix 1: Verify _try_acquire_scrape_lock() is atomic
    and prevents concurrent scrapes.
    """
    print("\n" + "=" * 60)
    print("TEST 1: Atomic Scrape Lock")
    print("=" * 60)

    # Reset global state
    global _last_scrape_time
    with _scrape_time_lock:
        _last_scrape_time = None

    # Test 1a: First scrape should succeed
    result = _try_acquire_scrape_lock()
    assert result is True, "First scrape should succeed"
    print("✓ First scrape acquired lock")

    # Test 1b: Immediate second scrape should fail
    result = _try_acquire_scrape_lock()
    assert result is False, "Immediate second scrape should fail"
    print("✓ Second scrape blocked (rate limiting works)")

    # Test 1c: Concurrent scrapes should be serialized
    with _scrape_time_lock:
        _last_scrape_time = None

    scrape_count = 0
    lock = threading.Lock()

    def try_scrape():
        nonlocal scrape_count
        if _try_acquire_scrape_lock():
            with lock:
                scrape_count += 1

    # Launch 10 threads simultaneously
    threads = []
    for _ in range(10):
        t = threading.Thread(target=try_scrape)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert scrape_count == 1, f"Only 1 scrape should succeed, got {scrape_count}"
    print(f"✓ Concurrent scrapes serialized: {scrape_count}/10 succeeded")


def test_fix1_deprecated_functions_still_work():
    """
    Test that deprecated _should_scrape() and _mark_scraped()
    still work for backward compatibility.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Deprecated Functions Backward Compatibility")
    print("=" * 60)

    # Reset global state
    global _last_scrape_time
    with _scrape_time_lock:
        _last_scrape_time = None

    # Test _should_scrape()
    result = _should_scrape()
    assert result is True, "First check should return True"
    print("✓ _should_scrape() works")

    # Test _mark_scraped()
    _mark_scraped()
    print("✓ _mark_scraped() works")

    # Test that _should_scrape() now returns False
    result = _should_scrape()
    assert result is False, "Second check should return False"
    print("✓ Rate limiting works with deprecated functions")


def test_fix2_atomic_availability_check():
    """
    Test Fix 2: Verify is_available() is atomic and prevents
    multiple threads from triggering simultaneous checks.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Atomic Availability Check")
    print("=" * 60)

    scraper = get_aleague_scraper()

    # Reset state
    scraper._available = None
    scraper._last_check_time = None

    # Mock the availability check function
    check_count = 0
    lock = threading.Lock()

    def mock_check():
        nonlocal check_count
        with lock:
            check_count += 1
        time.sleep(0.01)  # Simulate network delay
        return True

    with patch("ingestion.aleague_scraper.is_aleague_scraper_available", side_effect=mock_check):
        # Test 2a: First call should trigger check
        result = scraper.is_available()
        assert result is True, "Availability check should return True"
        assert check_count == 1, "Check should be called once"
        print("✓ First call triggered availability check")

        # Test 2b: Second call should use cached result
        result = scraper.is_available()
        assert result is True, "Cached result should be True"
        assert check_count == 1, "Check should not be called again"
        print("✓ Second call used cached result")

        # Test 2c: Concurrent calls should only trigger one check
        scraper._available = None
        scraper._last_check_time = None
        check_count = 0

        results = []

        def check_availability():
            results.append(scraper.is_available())

        threads = []
        for _ in range(10):
            t = threading.Thread(target=check_availability)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert check_count == 1, f"Only 1 check should be triggered, got {check_count}"
        assert all(results), "All results should be True"
        print(f"✓ Concurrent calls serialized: {check_count}/10 checks triggered")


def test_fix3_retry_logic():
    """
    Test Fix 3: Verify retry logic re-checks availability after 5 minutes.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Retry Logic (5-minute re-check)")
    print("=" * 60)

    scraper = get_aleague_scraper()

    # Reset state
    scraper._available = None
    scraper._last_check_time = None

    check_count = 0

    def mock_check():
        nonlocal check_count
        check_count += 1
        # First check fails, second succeeds
        return check_count > 1

    with patch("ingestion.aleague_scraper.is_aleague_scraper_available", side_effect=mock_check):
        # Test 3a: First check fails
        result = scraper.is_available()
        assert result is False, "First check should fail"
        assert check_count == 1, "Check should be called once"
        print("✓ First check failed as expected")

        # Test 3b: Immediate second call uses cached result
        result = scraper.is_available()
        assert result is False, "Cached result should be False"
        assert check_count == 1, "Check should not be called again"
        print("✓ Second call used cached False result")

        # Test 3c: Simulate 5 minutes passing
        old_check_time = scraper._last_check_time
        with scraper._available_lock:
            scraper._last_check_time = datetime.fromtimestamp(
                old_check_time.timestamp() - scraper._CHECK_INTERVAL_MINUTES * 60 - 1
            )

        # Test 3d: After 5 minutes, should re-check
        result = scraper.is_available()
        assert result is True, "Re-check should succeed"
        assert check_count == 2, "Check should be called again"
        print("✓ Re-check triggered after 5 minutes")

        # Test 3e: Verify _last_check_time was updated
        assert scraper._last_check_time > old_check_time, "Check time should be updated"
        print("✓ Check time updated after re-check")


def test_integration():
    """
    Integration test: Verify all fixes work together in a realistic scenario.
    """
    print("\n" + "=" * 60)
    print("TEST 5: Integration Test (All Fixes Together)")
    print("=" * 60)

    scraper = get_aleague_scraper()

    # Reset state
    global _last_scrape_time
    with _scrape_time_lock:
        _last_scrape_time = None
    scraper._available = None
    scraper._last_check_time = None

    availability_checks = 0
    scrape_attempts = 0

    def mock_availability():
        nonlocal availability_checks
        availability_checks += 1
        return True

    def mock_search(team_name, match_id, force):
        nonlocal scrape_attempts
        scrape_attempts += 1
        return []

    with patch(
        "ingestion.aleague_scraper.is_aleague_scraper_available", side_effect=mock_availability
    ):
        with patch("ingestion.aleague_scraper.search_aleague_news", side_effect=mock_search):
            # Simulate multiple threads calling the scraper
            results = []
            lock = threading.Lock()

            def call_scraper():
                if scraper.is_available():
                    result = scraper.search_team_news("Sydney FC", "match_123")
                    with lock:
                        results.append(result)

            threads = []
            for _ in range(5):
                t = threading.Thread(target=call_scraper)
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Verify behavior
            assert availability_checks == 1, (
                f"Should check availability once, got {availability_checks}"
            )
            assert scrape_attempts == 1, f"Should scrape once, got {scrape_attempts}"
            assert len(results) == 5, f"Should have 5 results, got {len(results)}"
            print("✓ All fixes work together correctly")
            print(f"  - Availability checks: {availability_checks}")
            print(f"  - Scrape attempts: {scrape_attempts}")
            print(f"  - Results returned: {len(results)}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("ALEAGUE SCRAPER THREAD SAFETY TEST SUITE")
    print("=" * 60)
    print("\nTesting VPS Fixes:")
    print("1. Atomic scrape lock (Fix 1)")
    print("2. Atomic availability check (Fix 2)")
    print("3. Retry logic (Fix 3)")

    try:
        test_fix1_atomic_scrape_lock()
        test_fix1_deprecated_functions_still_work()
        test_fix2_atomic_availability_check()
        test_fix3_retry_logic()
        test_integration()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe ALeagueScraper is now thread-safe and VPS-ready!")
        print("\nFixes applied:")
        print("  ✓ Fix 1: Atomic _try_acquire_scrape_lock() prevents concurrent scrapes")
        print("  ✓ Fix 2: Atomic is_available() prevents duplicate checks")
        print("  ✓ Fix 3: Retry logic re-checks availability after 5 minutes")
        return 0

    except AssertionError as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        return 1
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST ERROR")
        print("=" * 60)
        print(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
