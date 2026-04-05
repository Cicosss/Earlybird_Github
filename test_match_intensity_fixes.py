#!/usr/bin/env python3
"""
Test script to verify MatchIntensity validator fixes.

Tests:
1. Case-insensitive validation
2. Fallback to UNKNOWN for invalid values
3. Proper enum conversion
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from schemas.perplexity_schemas import BettingStatsResponse, MatchIntensity


def test_match_intensity_case_insensitive():
    """Test that match_intensity validation is case-insensitive."""
    print("Test 1: Case-insensitive validation")

    test_cases = [
        ("High", MatchIntensity.HIGH),
        ("high", MatchIntensity.HIGH),
        ("HIGH", MatchIntensity.HIGH),
        ("Medium", MatchIntensity.MEDIUM),
        ("medium", MatchIntensity.MEDIUM),
        ("Low", MatchIntensity.LOW),
        ("low", MatchIntensity.LOW),
    ]

    for input_value, expected in test_cases:
        data = {
            "corners_signal": "High",
            "match_intensity": input_value,
            "is_derby": False,
            "data_confidence": "High",
        }
        response = BettingStatsResponse(**data)
        assert response.match_intensity == expected, (
            f"Failed: input={input_value}, expected={expected}, got={response.match_intensity}"
        )
        print(f"  ✓ '{input_value}' -> {expected.value}")

    print("✅ Test 1 PASSED\n")


def test_match_intensity_invalid_fallback():
    """Test that invalid match_intensity falls back to UNKNOWN."""
    print("Test 2: Fallback to UNKNOWN for invalid values")

    invalid_values = [
        "InvalidValue",
        "extreme",
        "123",
        "",
        "null",
    ]

    for input_value in invalid_values:
        data = {
            "corners_signal": "High",
            "match_intensity": input_value,
            "is_derby": False,
            "data_confidence": "High",
        }
        response = BettingStatsResponse(**data)
        assert response.match_intensity == MatchIntensity.UNKNOWN, (
            f"Failed: input='{input_value}', expected=UNKNOWN, got={response.match_intensity}"
        )
        print(f"  ✓ '{input_value}' -> UNKNOWN")

    print("✅ Test 2 PASSED\n")


def test_match_intensity_default():
    """Test that match_intensity defaults to UNKNOWN when not provided."""
    print("Test 3: Default to UNKNOWN when not provided")

    data = {
        "corners_signal": "High",
        "is_derby": False,
        "data_confidence": "High",
    }
    response = BettingStatsResponse(**data)
    assert response.match_intensity == MatchIntensity.UNKNOWN, (
        f"Failed: expected=UNKNOWN, got={response.match_intensity}"
    )
    print(f"  ✓ Not provided -> UNKNOWN")

    print("✅ Test 3 PASSED\n")


def test_referee_strictness_case_insensitive():
    """Test that referee_strictness validation is case-insensitive."""
    print("Test 4: Referee strictness case-insensitive validation")

    test_cases = [
        ("Strict", "Strict"),
        ("strict", "Strict"),
        ("Medium", "Medium"),
        ("medium", "Medium"),
        ("Lenient", "Lenient"),
        ("lenient", "Lenient"),
    ]

    for input_value, expected in test_cases:
        data = {
            "corners_signal": "High",
            "match_intensity": "High",
            "referee_strictness": input_value,
            "is_derby": False,
            "data_confidence": "High",
        }
        response = BettingStatsResponse(**data)
        assert response.referee_strictness.value == expected, (
            f"Failed: input={input_value}, expected={expected}, got={response.referee_strictness.value}"
        )
        print(f"  ✓ '{input_value}' -> {expected}")

    print("✅ Test 4 PASSED\n")


def test_cards_signal_case_insensitive():
    """Test that cards_signal validation is case-insensitive."""
    print("Test 5: Cards signal case-insensitive validation")

    test_cases = [
        ("Aggressive", "Aggressive"),
        ("aggressive", "Aggressive"),
        ("Medium", "Medium"),
        ("medium", "Medium"),
        ("Disciplined", "Disciplined"),
        ("disciplined", "Disciplined"),
    ]

    for input_value, expected in test_cases:
        data = {
            "corners_signal": "High",
            "cards_signal": input_value,
            "match_intensity": "High",
            "is_derby": False,
            "data_confidence": "High",
        }
        response = BettingStatsResponse(**data)
        assert response.cards_signal.value == expected, (
            f"Failed: input={input_value}, expected={expected}, got={response.cards_signal.value}"
        )
        print(f"  ✓ '{input_value}' -> {expected}")

    print("✅ Test 5 PASSED\n")


if __name__ == "__main__":
    print("=" * 60)
    print("MatchIntensity Validator Fixes - Test Suite")
    print("=" * 60)
    print()

    try:
        test_match_intensity_case_insensitive()
        test_match_intensity_invalid_fallback()
        test_match_intensity_default()
        test_referee_strictness_case_insensitive()
        test_cards_signal_case_insensitive()

        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        sys.exit(1)
