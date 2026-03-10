#!/usr/bin/env python3
"""
Comprehensive test to validate CLV fixes applied.

This test verifies all critical fixes from COVE_CLVSTATS_DOUBLE_VERIFICATION_VPS_REPORT.md:
1. Validation for odds > 1000
2. Validation for infinity
3. Validation for NaN
4. Module-level imports (math, statistics)
5. Configurable days_back in notifier
"""

import sys

from src.analysis.clv_tracker import CLVTracker, get_clv_tracker


def test_critical_validation_fixes():
    """Test Fix #1-3: Missing validation in CLVTracker.calculate_clv()"""
    print("\n" + "=" * 70)
    print("TEST 1: Critical Validation Fixes")
    print("=" * 70)

    tracker = CLVTracker(margin=0.05)

    # Test cases that should return None
    test_cases_invalid = [
        (1500, 2.00, "odds_taken > 1000"),
        (2.00, 1500, "closing_odds > 1000"),
        (float("inf"), 2.00, "odds_taken = infinity"),
        (2.00, float("inf"), "closing_odds = infinity"),
        (float("nan"), 2.00, "odds_taken = NaN"),
        (2.00, float("nan"), "closing_odds = NaN"),
        (None, 2.00, "odds_taken = None"),
        (2.00, None, "closing_odds = None"),
        (1.0, 2.00, "odds_taken <= 1.0"),
        (2.00, 1.0, "closing_odds <= 1.0"),
        (0, 2.00, "odds_taken = 0"),
        (2.00, 0, "closing_odds = 0"),
    ]

    all_passed = True
    for odds_taken, closing_odds, description in test_cases_invalid:
        result = tracker.calculate_clv(odds_taken, closing_odds)
        if result is None:
            print(f"✅ PASS: {description} → None (correct)")
        else:
            print(f"❌ FAIL: {description} → {result}% (should be None)")
            all_passed = False

    # Test cases that should return valid CLV
    test_cases_valid = [
        (2.20, 2.00, "positive CLV"),
        (1.80, 2.00, "negative CLV"),
        (2.00, 2.00, "zero CLV"),
        (10.00, 8.00, "high odds but valid"),
        (1.20, 1.15, "low odds but valid"),
    ]

    for odds_taken, closing_odds, description in test_cases_valid:
        result = tracker.calculate_clv(odds_taken, closing_odds)
        if result is not None and isinstance(result, float):
            print(f"✅ PASS: {description} → {result:.2f}% (valid)")
        else:
            print(f"❌ FAIL: {description} → {result} (should be valid CLV)")
            all_passed = False

    return all_passed


def test_module_level_imports():
    """Test Fix #4: Module-level imports"""
    print("\n" + "=" * 70)
    print("TEST 2: Module-Level Imports")
    print("=" * 70)

    # Check that math and statistics are imported at module level
    import src.analysis.clv_tracker as clv_module

    # Check if math is in the module's namespace
    has_math = hasattr(clv_module, "math")
    has_statistics = hasattr(clv_module, "statistics")

    if has_math:
        print("✅ PASS: 'math' is imported at module level")
    else:
        print("❌ FAIL: 'math' is NOT imported at module level")

    if has_statistics:
        print("✅ PASS: 'statistics' is imported at module level")
    else:
        print("❌ FAIL: 'statistics' is NOT imported at module level")

    return has_math and has_statistics


def test_calculate_stats_import():
    """Test that _calculate_stats doesn't import statistics internally"""
    print("\n" + "=" * 70)
    print("TEST 3: _calculate_stats Import Check")
    print("=" * 70)

    import inspect

    from src.analysis.clv_tracker import CLVTracker

    # Get the source code of _calculate_stats
    source = inspect.getsource(CLVTracker._calculate_stats)

    # Check if 'import statistics' appears in the function
    has_internal_import = "import statistics" in source

    if not has_internal_import:
        print("✅ PASS: _calculate_stats does NOT import statistics internally")
        return True
    else:
        print("❌ FAIL: _calculate_stats still imports statistics internally")
        return False


def test_notifier_configurable_days_back():
    """Test Fix #5: Configurable days_back in notifier"""
    print("\n" + "=" * 70)
    print("TEST 4: Configurable days_back in Notifier")
    print("=" * 70)

    import inspect

    from src.alerting.notifier import send_clv_strategy_report

    # Get the function signature
    sig = inspect.signature(send_clv_strategy_report)

    # Check if days_back parameter exists
    has_days_back_param = "days_back" in sig.parameters

    if has_days_back_param:
        # Check if it has a default value
        param = sig.parameters["days_back"]
        has_default = param.default != inspect.Parameter.empty

        if has_default:
            print(
                f"✅ PASS: send_clv_strategy_report has days_back parameter with default={param.default}"
            )
            return True
        else:
            print("✅ PASS: send_clv_strategy_report has days_back parameter (no default)")
            return True
    else:
        print("❌ FAIL: send_clv_strategy_report does NOT have days_back parameter")
        return False


def test_consistency_with_settler():
    """Test that CLVTracker.calculate_clv() is consistent with settler.calculate_clv()"""
    print("\n" + "=" * 70)
    print("TEST 5: Consistency with Settler Implementation")
    print("=" * 70)

    from src.analysis.clv_tracker import CLVTracker
    from src.analysis.settler import calculate_clv as settler_calculate_clv

    tracker = CLVTracker(margin=0.05)

    # Test cases
    test_cases = [
        (2.20, 2.00),
        (1.80, 2.00),
        (2.00, 2.00),
        (10.00, 8.00),
        (1.20, 1.15),
    ]

    all_consistent = True
    for odds_taken, closing_odds in test_cases:
        settler_result = settler_calculate_clv(odds_taken, closing_odds, margin=0.05)
        tracker_result = tracker.calculate_clv(odds_taken, closing_odds)

        if settler_result == tracker_result:
            print(f"✅ PASS: ({odds_taken}, {closing_odds}) → Both return {settler_result:.2f}%")
        else:
            print(
                f"❌ FAIL: ({odds_taken}, {closing_odds}) → Settler: {settler_result:.2f}%, Tracker: {tracker_result:.2f}%"
            )
            all_consistent = False

    return all_consistent


def test_singleton_thread_safety():
    """Test that get_clv_tracker() returns the same instance"""
    print("\n" + "=" * 70)
    print("TEST 6: Singleton Pattern")
    print("=" * 70)

    tracker1 = get_clv_tracker()
    tracker2 = get_clv_tracker()

    if tracker1 is tracker2:
        print("✅ PASS: get_clv_tracker() returns the same instance (singleton)")
        return True
    else:
        print("❌ FAIL: get_clv_tracker() returns different instances")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("CLV FIXES VALIDATION TEST SUITE")
    print("=" * 70)
    print("Testing fixes from COVE_CLVSTATS_DOUBLE_VERIFICATION_VPS_REPORT.md")

    results = []

    # Run all tests
    results.append(("Critical Validation Fixes", test_critical_validation_fixes()))
    results.append(("Module-Level Imports", test_module_level_imports()))
    results.append(("_calculate_stats Import Check", test_calculate_stats_import()))
    results.append(("Configurable days_back", test_notifier_configurable_days_back()))
    results.append(("Consistency with Settler", test_consistency_with_settler()))
    results.append(("Singleton Pattern", test_singleton_thread_safety()))

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("=" * 70)

    if all_passed:
        print("\n🎉 ALL TESTS PASSED! CLV fixes are working correctly.")
        print("\nThe bot is now ready for VPS deployment with:")
        print("  ✅ Critical validation fixes applied")
        print("  ✅ Module-level imports optimized")
        print("  ✅ Configurable days_back parameter")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED! Please review the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
