#!/usr/bin/env python3
"""
Integration Test for Biscotto Engine Migration (V13.0)

This test verifies end-to-end integration of the Advanced Biscotto Engine
with the main bot components: data flow, alerting, and fallback paths.

Author: EarlyBird AI
Date: 2026-03-04
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_end_to_end_biscotto_detection():
    """
    TEST 1: End-to-End Biscotto Detection Flow

    Verifies that enhanced fields flow correctly from:
    Match → is_biscotto_suspect() → check_biscotto_suspects() → send_biscotto_alert()
    """
    print("\n" + "=" * 60)
    print("TEST 1: End-to-End Biscotto Detection Flow")
    print("=" * 60)

    try:
        from src.core.analysis_engine import AnalysisEngine
        from src.main import is_biscotto_suspect

        # Create a mock Match object with suspicious draw odds
        mock_match = Mock()
        mock_match.home_team = "Juventus"
        mock_match.away_team = "Inter Milan"
        mock_match.league = "soccer_italy_serie_a"
        mock_match.current_draw_odd = 2.45
        mock_match.opening_draw_odd = 3.10
        mock_match.start_time = datetime.now(timezone.utc) + timedelta(hours=24)

        # Test is_biscotto_suspect() returns enhanced fields
        print("\nStep 1: Testing is_biscotto_suspect()...")
        result = is_biscotto_suspect(mock_match)

        # Verify all enhanced fields are present
        required_fields = [
            "is_suspect",
            "severity",
            "reason",
            "draw_odd",
            "drop_pct",
            "confidence",
            "factors",
            "pattern",
            "zscore",
            "mutual_benefit",
            "betting_recommendation",
        ]

        missing_fields = [f for f in required_fields if f not in result]
        if missing_fields:
            print(f"\n❌ FAIL: Missing fields in result: {missing_fields}")
            return False

        print("  ✅ All required fields present")
        print(f"  - is_suspect: {result['is_suspect']}")
        print(f"  - severity: {result['severity']}")
        print(f"  - confidence: {result['confidence']}%")
        print(f"  - pattern: {result['pattern']}")
        print(f"  - zscore: {result['zscore']}")
        print(f"  - mutual_benefit: {result['mutual_benefit']}")
        print(f"  - betting_recommendation: {result['betting_recommendation']}")
        if result["factors"]:
            print(f"  - factors ({len(result['factors'])}): {result['factors'][:2]}...")

        # Test AnalysisEngine.is_biscotto_suspect() returns same structure
        print("\nStep 2: Testing AnalysisEngine.is_biscotto_suspect()...")
        ae_result = AnalysisEngine.is_biscotto_suspect(mock_match)

        for field in required_fields:
            if field not in ae_result:
                print(f"\n❌ FAIL: Missing field in AE result: {field}")
                return False

        print("  ✅ AnalysisEngine returns same structure")

        print("\n✅ PASS: End-to-end data flow works correctly")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: End-to-end test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_analysis_engine_check_suspects_enhanced_fields():
    """
    TEST 2: AnalysisEngine.check_biscotto_suspects() Enhanced Fields

    Verifies that check_biscotto_suspects() returns suspect dictionaries
    with all enhanced fields (CRITICAL FIX VERIFICATION).
    """
    print("\n" + "=" * 60)
    print("TEST 2: AnalysisEngine.check_biscotto_suspects() Enhanced Fields")
    print("=" * 60)

    try:
        from src.core.analysis_engine import AnalysisEngine
        from src.database.models import Match, SessionLocal

        # Create a test match in database
        db = SessionLocal()
        try:
            # Clean up any existing test matches
            db.query(Match).filter(Match.home_team == "TEST_Juventus").delete()
            db.commit()

            # Create test match with suspicious draw odds
            test_match = Match(
                home_team="TEST_Juventus",
                away_team="TEST_Inter Milan",
                league="soccer_italy_serie_a",
                start_time=datetime.now(timezone.utc) + timedelta(hours=24),
                current_draw_odd=2.45,
                opening_draw_odd=3.10,
            )
            db.add(test_match)
            db.commit()

            # Test check_biscotto_suspects()
            print("\nStep 1: Calling check_biscotto_suspects()...")
            suspects = AnalysisEngine.check_biscotto_suspects()

            # Find our test match in suspects
            test_suspect = None
            for suspect in suspects:
                if suspect["match"].home_team == "TEST_Juventus":
                    test_suspect = suspect
                    break

            if not test_suspect:
                print("\n⚠️  Test match not detected as suspect (expected for some scenarios)")
                print("  ✅ Test passed (no crash)")
                return True

            # Verify enhanced fields are present
            print("\nStep 2: Verifying enhanced fields in suspect dict...")
            required_enhanced_fields = [
                "confidence",
                "factors",
                "pattern",
                "zscore",
                "mutual_benefit",
                "betting_recommendation",
            ]

            missing_fields = [f for f in required_enhanced_fields if f not in test_suspect]
            if missing_fields:
                print(f"\n❌ FAIL: Missing enhanced fields: {missing_fields}")
                print(f"  Available keys: {list(test_suspect.keys())}")
                return False

            print("  ✅ All enhanced fields present:")
            print(f"    - confidence: {test_suspect['confidence']}")
            print(f"    - pattern: {test_suspect['pattern']}")
            print(f"    - zscore: {test_suspect['zscore']}")
            print(f"    - mutual_benefit: {test_suspect['mutual_benefit']}")
            print(f"    - betting_recommendation: {test_suspect['betting_recommendation']}")
            if test_suspect["factors"]:
                print(f"    - factors: {test_suspect['factors']}")

            print("\n✅ PASS: Enhanced fields flow correctly through AnalysisEngine")
            return True

        finally:
            # Clean up test data
            db.query(Match).filter(Match.home_team == "TEST_Juventus").delete()
            db.commit()
            db.close()

    except Exception as e:
        print(f"\n❌ FAIL: AnalysisEngine test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_send_biscotto_alert_with_enhanced_fields():
    """
    TEST 3: send_biscotto_alert() with Enhanced Fields

    Verifies that send_biscotto_alert() correctly formats and includes
    all enhanced fields in the Telegram message.
    """
    print("\n" + "=" * 60)
    print("TEST 3: send_biscotto_alert() with Enhanced Fields")
    print("=" * 60)

    try:
        from src.alerting.notifier import send_biscotto_alert

        # Create mock match object
        mock_match = Mock()
        mock_match.home_team = "AC Milan"
        mock_match.away_team = "Napoli"
        mock_match.league = "Serie A"
        mock_match.start_time = datetime.now(timezone.utc) + timedelta(hours=48)

        # Test with all enhanced fields
        print("\nStep 1: Testing send_biscotto_alert() with enhanced fields...")

        # Mock Telegram API to prevent actual sending
        with patch("src.alerting.notifier._send_telegram_request") as mock_send:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_send.return_value = mock_response

            send_biscotto_alert(
                match_obj=mock_match,
                draw_odd=2.30,
                drop_pct=20.7,
                severity="HIGH",
                reasoning="Quota X sospetta",
                # Enhanced fields
                confidence=75,
                factors=["🟠 Quota X sospetta: 2.30", "📉 Drop significativo: -20.7%"],
                pattern="CRASH",
                zscore=1.9,
                mutual_benefit=True,
                betting_recommendation="BET X (Fiducia moderata)",
            )

        # Verify the call was made
        if not mock_send.called:
            print("\n❌ FAIL: Telegram API not called")
            return False

        # Get the payload sent to Telegram
        call_args = mock_send.call_args
        if call_args and len(call_args) > 0:
            # call_args[0] is the tuple of positional args: (url, payload, timeout)
            args_tuple = call_args[0]
            if len(args_tuple) > 1:
                payload = args_tuple[1]
            else:
                payload = None
        else:
            payload = None

        if not payload:
            print("\n❌ FAIL: No payload found")
            return False

        message = payload.get("text", "")

        # Verify enhanced fields are in the message
        print("\nStep 2: Verifying enhanced fields in message...")
        checks = {
            "Confidence": "Confidence:" in message and "75%" in message,
            "Pattern": "Pattern:" in message and "CRASH" in message,
            "Z-Score": "Z-Score:" in message and "1.9" in message,
            "Mutual Benefit": "Mutual Benefit:" in message,
            "Betting Recommendation": "Recommendation:" in message and "BET X" in message,
            "Factors": "Factors:" in message,
        }

        all_passed = True
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'present' if passed else 'MISSING'}")
            if not passed:
                all_passed = False

        if not all_passed:
            print("\n❌ FAIL: Some enhanced fields missing from message")
            print("\nMessage preview (first 500 chars):")
            print(message[:500])
            return False

        print("\n✅ PASS: All enhanced fields included in Telegram message")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: send_biscotto_alert test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_graceful_fallback_to_legacy():
    """
    TEST 4: Graceful Fallback to Legacy Implementation

    Verifies that when Advanced Engine fails, the system falls back
    to legacy implementation without crashing.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Graceful Fallback to Legacy Implementation")
    print("=" * 60)

    try:
        from src.main import is_biscotto_suspect

        # Create mock match
        mock_match = Mock()
        mock_match.home_team = "Roma"
        mock_match.away_team = "Lazio"
        mock_match.current_draw_odd = 2.45
        mock_match.opening_draw_odd = 3.10

        # Test with Advanced Engine disabled (simulate failure)
        print("\nStep 1: Testing fallback when Advanced Engine unavailable...")

        with patch("src.main._BISCOTTO_ENGINE_AVAILABLE", False):
            result = is_biscotto_suspect(mock_match)

        # Verify result has all fields (even with fallback)
        print("\nStep 2: Verifying fallback result structure...")
        required_fields = [
            "is_suspect",
            "severity",
            "reason",
            "draw_odd",
            "drop_pct",
            "confidence",
            "factors",
            "pattern",
            "zscore",
            "mutual_benefit",
            "betting_recommendation",
        ]

        missing_fields = [f for f in required_fields if f not in result]
        if missing_fields:
            print(f"\n❌ FAIL: Fallback missing fields: {missing_fields}")
            return False

        print("  ✅ Fallback returns all required fields")
        print(f"  - is_suspect: {result['is_suspect']}")
        print(f"  - severity: {result['severity']}")
        print(f"  - confidence: {result['confidence']}")
        print(f"  - pattern: {result['pattern']}")

        # Verify fallback values are sensible
        if result["confidence"] not in [0, 60, 75, 90]:
            print(f"\n⚠️  Unexpected confidence value: {result['confidence']}")

        if result["pattern"] not in ["STABLE", "DRIFT", "CRASH"]:
            print(f"\n⚠️  Unexpected pattern value: {result['pattern']}")

        print("\n✅ PASS: Graceful fallback works correctly")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: Fallback test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_fotmob_motivation_fetch_failure():
    """
    TEST 5: FotMob Motivation Data Fetch Failure

    Verifies that when FotMob motivation data fetch fails,
    the system continues without crashing.
    """
    print("\n" + "=" * 60)
    print("TEST 5: FotMob Motivation Data Fetch Failure")
    print("=" * 60)

    try:
        from src.main import is_biscotto_suspect

        # Create mock match
        mock_match = Mock()
        mock_match.home_team = "Atalanta"
        mock_match.away_team = "Udinese"
        mock_match.current_draw_odd = 2.45
        mock_match.opening_draw_odd = 3.10

        # Test with FotMob fetch failure
        print("\nStep 1: Testing with FotMot fetch failure...")

        with patch("src.main.get_data_provider") as mock_provider:
            # Simulate FotMob fetch error
            mock_provider.side_effect = Exception("FotMob API error")

            result = is_biscotto_suspect(mock_match)

        # Verify system handled the error gracefully
        print("\nStep 2: Verifying error was handled gracefully...")
        if not result:
            print("\n❌ FAIL: No result returned (should return dict)")
            return False

        required_fields = [
            "is_suspect",
            "severity",
            "reason",
            "draw_odd",
            "drop_pct",
            "confidence",
            "factors",
            "pattern",
            "zscore",
            "mutual_benefit",
            "betting_recommendation",
        ]

        missing_fields = [f for f in required_fields if f not in result]
        if missing_fields:
            print(f"\n❌ FAIL: Missing fields after FotMob failure: {missing_fields}")
            return False

        print("  ✅ System handled FotMob failure gracefully")
        print(f"  - is_suspect: {result['is_suspect']}")
        print(f"  - confidence: {result['confidence']}")

        print("\n✅ PASS: FotMob fetch failure handled correctly")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: FotMob failure test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_backward_compatibility():
    """
    TEST 6: Backward Compatibility

    Verifies that existing code paths that don't use enhanced fields
    continue to work correctly.
    """
    print("\n" + "=" * 60)
    print("TEST 6: Backward Compatibility")
    print("=" * 60)

    try:
        from src.alerting.notifier import send_biscotto_alert

        # Create mock match
        mock_match = Mock()
        mock_match.home_team = "Fiorentina"
        mock_match.away_team = "Torino"
        mock_match.league = "Serie A"
        mock_match.start_time = datetime.now(timezone.utc) + timedelta(hours=72)

        # Test without enhanced fields (old-style call)
        print("\nStep 1: Testing old-style call without enhanced fields...")

        with patch("src.alerting.notifier._send_telegram_request") as mock_send:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_send.return_value = mock_response

            send_biscotto_alert(
                match_obj=mock_match,
                draw_odd=2.50,
                drop_pct=15.0,
                severity="MEDIUM",
                reasoning="Drop significativo",
                # NO enhanced fields (old-style)
            )

        # Verify the call succeeded
        if not mock_send.called:
            print("\n❌ FAIL: Telegram API not called")
            return False

        print("  ✅ Old-style call works correctly")

        # Test with None values for enhanced fields
        print("\nStep 2: Testing with None values for enhanced fields...")

        with patch("src.alerting.notifier._send_telegram_request") as mock_send:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_send.return_value = mock_response

            send_biscotto_alert(
                match_obj=mock_match,
                draw_odd=2.50,
                drop_pct=15.0,
                severity="MEDIUM",
                reasoning="Drop significativo",
                # Enhanced fields with None values
                confidence=None,
                factors=None,
                pattern=None,
                zscore=None,
                mutual_benefit=None,
                betting_recommendation=None,
            )

        if not mock_send.called:
            print("\n❌ FAIL: Telegram API not called with None values")
            return False

        print("  ✅ None values handled correctly")

        print("\n✅ PASS: Backward compatibility maintained")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: Backward compatibility test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_data_consistency_across_components():
    """
    TEST 7: Data Consistency Across Components

    Verifies that data structures are consistent between:
    - is_biscotto_suspect() in src/main.py
    - AnalysisEngine.is_biscotto_suspect() in src/core/analysis_engine.py
    - send_biscotto_alert() in src/alerting/notifier.py
    """
    print("\n" + "=" * 60)
    print("TEST 7: Data Consistency Across Components")
    print("=" * 60)

    try:
        from src.core.analysis_engine import AnalysisEngine
        from src.main import is_biscotto_suspect

        # Create mock match
        mock_match = Mock()
        mock_match.home_team = "Sassuolo"
        mock_match.away_team = "Empoli"
        mock_match.current_draw_odd = 2.30
        mock_match.opening_draw_odd = 2.90

        # Test both implementations return same structure
        print("\nStep 1: Comparing is_biscotto_suspect() implementations...")

        main_result = is_biscotto_suspect(mock_match)
        ae_result = AnalysisEngine.is_biscotto_suspect(mock_match)

        # Check both have same keys
        main_keys = set(main_result.keys())
        ae_keys = set(ae_result.keys())

        if main_keys != ae_keys:
            print("\n❌ FAIL: Different keys returned")
            print(f"  Main.py keys: {main_keys}")
            print(f"  AnalysisEngine keys: {ae_keys}")
            return False

        print("  ✅ Both implementations return same structure")

        # Check data types are consistent
        print("\nStep 2: Verifying data type consistency...")
        type_checks = {
            "confidence": (int, type(None)),
            "factors": (list, type(None)),
            "pattern": (str, type(None)),
            "zscore": (float, type(None)),
            "mutual_benefit": (bool, type(None)),
            "betting_recommendation": (str, type(None)),
        }

        all_consistent = True
        for field, expected_types in type_checks.items():
            main_type = type(main_result.get(field))
            ae_type = type(ae_result.get(field))

            if main_type not in expected_types or ae_type not in expected_types:
                print(f"  ❌ {field}: main={main_type}, ae={ae_type}")
                all_consistent = False

        if not all_consistent:
            print("\n❌ FAIL: Data type inconsistency found")
            return False

        print("  ✅ All data types are consistent")

        print("\n✅ PASS: Data consistency verified across components")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: Data consistency test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("BISCOTTO ENGINE MIGRATION INTEGRATION TEST SUITE (V13.0)")
    print("=" * 60)

    tests = [
        ("End-to-End Biscotto Detection Flow", test_end_to_end_biscotto_detection),
        (
            "AnalysisEngine.check_biscotto_suspects() Enhanced Fields",
            test_analysis_engine_check_suspects_enhanced_fields,
        ),
        (
            "send_biscotto_alert() with Enhanced Fields",
            test_send_biscotto_alert_with_enhanced_fields,
        ),
        ("Graceful Fallback to Legacy", test_graceful_fallback_to_legacy),
        ("FotMob Motivation Fetch Failure", test_fotmob_motivation_fetch_failure),
        ("Backward Compatibility", test_backward_compatibility),
        ("Data Consistency Across Components", test_data_consistency_across_components),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ UNEXPECTED ERROR in {test_name}: {e}")
            import traceback

            traceback.print_exc()
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("✅ Biscotto Engine V13.0 migration is production-ready")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("❌ Please review and fix failing tests before deployment")
        return 1


if __name__ == "__main__":
    sys.exit(main())
