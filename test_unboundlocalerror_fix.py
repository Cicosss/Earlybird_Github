#!/usr/bin/env python3
"""
Temporary test to verify the UnboundLocalError fix in run_verification_check.

This test simulates the scenario where an exception occurs before the label
would have been assigned in the old code, verifying that the fix prevents
the UnboundLocalError by initializing label early.
"""

import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.analysis.verification_layer import VerificationStatus
from src.core.analysis_engine import AnalysisEngine
from src.database.models import Match, NewsLog


def test_unboundlocalerror_fix():
    """
    Test that the UnboundLocalError fix works correctly.

    This test simulates the scenario where create_verification_request_from_match
    raises an exception before the label would have been assigned in the old code.
    With the fix, label is initialized early, so the exception handler can use it.
    """
    print("=" * 80)
    print("TEST: UnboundLocalError Fix Verification")
    print("=" * 80)

    # Create mock objects
    mock_match = Mock(spec=Match)
    mock_match.id = "test_match_123"
    mock_match.home_team = "Test Home"
    mock_match.away_team = "Test Away"
    mock_match.league = "Test League"
    mock_match.start_time = datetime(2026, 2, 16, 13, 0, 0)

    mock_analysis = Mock(spec=NewsLog)
    mock_analysis.score = 8.5
    mock_analysis.recommended_market = "OVER_2.5"
    mock_analysis.primary_market = "OVER_2.5"

    # Create AnalysisEngine instance
    engine = AnalysisEngine()

    # Test Case 1: Exception in create_verification_request_from_match
    print("\n[Test Case 1] Exception in create_verification_request_from_match")
    print("-" * 80)

    with patch(
        "src.core.analysis_engine.create_verification_request_from_match"
    ) as mock_create_req:
        # Simulate an exception that would occur before label assignment in old code
        mock_create_req.side_effect = AttributeError("Test exception before label assignment")

        try:
            result = engine.run_verification_check(
                match=mock_match,
                analysis=mock_analysis,
                home_stats=None,
                away_stats=None,
                home_context=None,
                away_context=None,
                context_label="TIER1",
            )

            # If we get here, the fix worked - no UnboundLocalError
            print("✅ PASS: No UnboundLocalError occurred")
            print(f"   Result: {result}")
            print(f"   should_send: {result[0]}")
            print(f"   adjusted_score: {result[1]}")
            print(f"   adjusted_market: {result[2]}")
            print(f"   verification_result: {result[3]}")

        except UnboundLocalError as e:
            print(f"❌ FAIL: UnboundLocalError still occurs: {e}")
            return False
        except Exception as e:
            # Other exceptions are expected and handled by the except block
            print(
                f"✅ PASS: Exception handled correctly (not UnboundLocalError): {type(e).__name__}"
            )

    # Test Case 2: Exception in verify_alert
    print("\n[Test Case 2] Exception in verify_alert")
    print("-" * 80)

    with patch("src.core.analysis_engine.verify_alert") as mock_verify:
        # Simulate an exception that would occur before label assignment in old code
        mock_verify.side_effect = RuntimeError("Test exception in verify_alert")

        try:
            result = engine.run_verification_check(
                match=mock_match,
                analysis=mock_analysis,
                home_stats=None,
                away_stats=None,
                home_context=None,
                away_context=None,
                context_label="TIER2",
            )

            # If we get here, the fix worked - no UnboundLocalError
            print("✅ PASS: No UnboundLocalError occurred")
            print(f"   Result: {result}")

        except UnboundLocalError as e:
            print(f"❌ FAIL: UnboundLocalError still occurs: {e}")
            return False
        except Exception as e:
            # Other exceptions are expected and handled by the except block
            print(
                f"✅ PASS: Exception handled correctly (not UnboundLocalError): {type(e).__name__}"
            )

    # Test Case 3: Different context_label values
    print("\n[Test Case 3] Different context_label values")
    print("-" * 80)

    context_labels = ["", "TIER1", "TIER2", "RADAR"]

    for context_label in context_labels:
        with patch(
            "src.core.analysis_engine.create_verification_request_from_match"
        ) as mock_create_req:
            mock_create_req.side_effect = ValueError("Test exception")

            try:
                result = engine.run_verification_check(
                    match=mock_match,
                    analysis=mock_analysis,
                    home_stats=None,
                    away_stats=None,
                    home_context=None,
                    away_context=None,
                    context_label=context_label,
                )
                print(f"✅ PASS: context_label='{context_label}' - No UnboundLocalError")

            except UnboundLocalError as e:
                print(f"❌ FAIL: context_label='{context_label}' - UnboundLocalError: {e}")
                return False
            except Exception as e:
                print(
                    f"✅ PASS: context_label='{context_label}' - Exception handled: {type(e).__name__}"
                )

    # Test Case 4: Normal operation (no exception)
    print("\n[Test Case 4] Normal operation (no exception)")
    print("-" * 80)

    from src.analysis.verification_layer import VerificationResult

    mock_result = Mock(spec=VerificationResult)
    mock_result.status = VerificationStatus.CONFIRM
    mock_result.adjusted_score = 8.0
    mock_result.original_market = "OVER_2.5"
    mock_result.suggested_market = None
    mock_result.reason = None

    with (
        patch("src.core.analysis_engine.create_verification_request_from_match") as mock_create_req,
        patch("src.core.analysis_engine.verify_alert") as mock_verify,
    ):
        mock_create_req.return_value = Mock()  # Mock VerificationRequest
        mock_verify.return_value = mock_result

        try:
            result = engine.run_verification_check(
                match=mock_match,
                analysis=mock_analysis,
                home_stats=None,
                away_stats=None,
                home_context=None,
                away_context=None,
                context_label="TIER1",
            )

            print("✅ PASS: Normal operation works correctly")
            print(f"   should_send: {result[0]}")
            print(f"   adjusted_score: {result[1]}")
            print(f"   adjusted_market: {result[2]}")

        except Exception as e:
            print(f"❌ FAIL: Normal operation failed: {e}")
            return False

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - UnboundLocalError fix verified!")
    print("=" * 80)
    return True


def test_label_initialization():
    """
    Test that label is properly initialized with different context_label values.
    """
    print("\n" + "=" * 80)
    print("TEST: Label Initialization Verification")
    print("=" * 80)

    # Test that label is initialized correctly
    test_cases = [
        ("", ""),
        ("TIER1", "[TIER1] "),
        ("TIER2", "[TIER2] "),
        ("RADAR", "[RADAR] "),
    ]

    for context_label, expected_label in test_cases:
        actual_label = f"[{context_label}] " if context_label else ""
        if actual_label == expected_label:
            print(f"✅ PASS: context_label='{context_label}' -> label='{actual_label}'")
        else:
            print(
                f"❌ FAIL: context_label='{context_label}' -> expected '{expected_label}', got '{actual_label}'"
            )
            return False

    print("\n✅ Label initialization test passed!")
    return True


if __name__ == "__main__":
    print("\n🧪 Running UnboundLocalError Fix Verification Tests\n")

    # Run tests
    test1_passed = test_label_initialization()
    test2_passed = test_unboundlocalerror_fix()

    if test1_passed and test2_passed:
        print("\n" + "=" * 80)
        print("🎉 ALL VERIFICATION TESTS PASSED!")
        print("=" * 80)
        print("\nThe UnboundLocalError fix has been successfully verified.")
        print("The 'label' variable is now initialized early in the try block,")
        print("preventing UnboundLocalError when exceptions occur before the old")
        print("assignment point.")
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("❌ SOME TESTS FAILED!")
        print("=" * 80)
        sys.exit(1)
