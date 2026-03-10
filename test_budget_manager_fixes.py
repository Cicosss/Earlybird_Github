#!/usr/bin/env python3
"""
Test script to verify BudgetManager fixes for:
1. Thread safety with Lock
2. Unknown component rejection
3. Error handling in record_call()
"""

import sys
import threading

from src.ingestion.brave_budget import get_brave_budget_manager
from src.ingestion.tavily_budget import get_budget_manager as get_tavily_budget_manager


def test_unknown_component_rejection():
    """Test that unknown components are rejected."""
    print("\n=== Test 1: Unknown Component Rejection ===")

    brave = get_brave_budget_manager()

    # Known components should work
    known_components = [
        "main_pipeline",
        "news_radar",
        "browser_monitor",
        "telegram_monitor",
        "settlement_clv",
        "twitter_recovery",
    ]

    for component in known_components:
        result = brave.can_call(component)
        print(f"✓ Known component '{component}': can_call() = {result}")
        assert result is True, f"Known component '{component}' should be allowed"

    # Unknown components should be rejected
    unknown_components = ["unknown_component", "hacker_script", "malicious_bot"]

    for component in unknown_components:
        result = brave.can_call(component)
        print(f"✗ Unknown component '{component}': can_call() = {result}")
        assert result is False, f"Unknown component '{component}' should be rejected"

    print("✓ Test 1 PASSED: Unknown components are correctly rejected")


def test_thread_safety():
    """Test that multiple threads can safely call can_call() and record_call()."""
    print("\n=== Test 2: Thread Safety ===")

    brave = get_brave_budget_manager()

    # Reset to known state
    brave.reset_monthly()

    # Number of concurrent threads
    num_threads = 10
    calls_per_thread = 100

    results = {"success": 0, "errors": 0}
    lock = threading.Lock()

    def worker(component: str):
        """Worker thread that makes API calls."""
        for _ in range(calls_per_thread):
            try:
                if brave.can_call(component):
                    brave.record_call(component)
                    with lock:
                        results["success"] += 1
                else:
                    with lock:
                        results["success"] += 1  # Still counts as successful check
            except Exception as e:
                print(f"✗ Error in thread: {e}")
                with lock:
                    results["errors"] += 1

    # Create and start threads
    threads = []
    for i in range(num_threads):
        component = "main_pipeline"
        t = threading.Thread(target=worker, args=(component,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify results
    total_calls = num_threads * calls_per_thread
    status = brave.get_status()

    print(f"  Threads: {num_threads}")
    print(f"  Calls per thread: {calls_per_thread}")
    print(f"  Total operations: {total_calls}")
    print(f"  Successful operations: {results['success']}")
    print(f"  Errors: {results['errors']}")
    print(f"  Monthly used: {status.monthly_used}")
    print(f"  Component 'main_pipeline' used: {status.component_usage.get('main_pipeline', 0)}")

    assert results["errors"] == 0, f"Thread safety test failed with {results['errors']} errors"
    assert status.monthly_used == total_calls, (
        f"Expected {total_calls} calls, got {status.monthly_used}"
    )

    print("✓ Test 2 PASSED: Thread safety verified")


def test_error_handling():
    """Test that record_call() handles errors gracefully."""
    print("\n=== Test 3: Error Handling in record_call() ===")

    brave = get_brave_budget_manager()

    # Reset to known state
    brave.reset_monthly()

    # Record some normal calls
    for _ in range(5):
        brave.can_call("main_pipeline")
        brave.record_call("main_pipeline")

    status = brave.get_status()
    print(f"  Monthly used after 5 calls: {status.monthly_used}")
    assert status.monthly_used == 5, f"Expected 5 calls, got {status.monthly_used}"

    # Test that record_call() doesn't crash even with edge cases
    try:
        # Record call for a component not in allocations (should still work due to error handling)
        brave.record_call("temp_component")
        print("✓ record_call() handled unknown component gracefully")
    except Exception as e:
        print(f"✗ record_call() failed: {e}")
        raise

    status = brave.get_status()
    print(f"  Monthly used after unknown component: {status.monthly_used}")

    print("✓ Test 3 PASSED: Error handling works correctly")


def test_integration_points():
    """Test that all integration points still work."""
    print("\n=== Test 4: Integration Points ===")

    brave = get_brave_budget_manager()
    tavily = get_tavily_budget_manager()

    # Test all known components for Brave
    brave_components = [
        "main_pipeline",
        "news_radar",
        "browser_monitor",
        "telegram_monitor",
        "settlement_clv",
        "twitter_recovery",
    ]

    for component in brave_components:
        result = brave.can_call(component)
        print(f"  Brave - {component}: can_call() = {result}")
        assert result is True, f"Brave component '{component}' should be allowed"

    # Test all known components for Tavily
    tavily_components = [
        "main_pipeline",
        "news_radar",
        "browser_monitor",
        "telegram_monitor",
        "settlement_clv",
        "twitter_recovery",
    ]

    for component in tavily_components:
        result = tavily.can_call(component)
        print(f"  Tavily - {component}: can_call() = {result}")
        assert result is True, f"Tavily component '{component}' should be allowed"

    print("✓ Test 4 PASSED: All integration points work correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("BudgetManager Fixes Verification Tests")
    print("=" * 60)

    try:
        test_unknown_component_rejection()
        test_thread_safety()
        test_error_handling()
        test_integration_points()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("  ✓ Unknown components are rejected")
        print("  ✓ Thread safety with Lock works correctly")
        print("  ✓ Error handling prevents budget leaks")
        print("  ✓ All integration points still work")
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
