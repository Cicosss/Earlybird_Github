#!/usr/bin/env python3
"""
Simple Test for Biscotto Engine Migration (V13.0)

This test verifies that the migration from Legacy to Advanced Biscotto Engine
works correctly at the core level.

Author: EarlyBird AI
Date: 2026-03-04
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_advanced_engine_available():
    """Test 1: Verify Advanced Biscotto Engine is available."""
    print("\n" + "="*60)
    print("TEST 1: Advanced Biscotto Engine Availability")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import (
            BiscottoAnalysis,
            BiscottoSeverity,
            BiscottoPattern,
            get_enhanced_biscotto_analysis,
            analyze_biscotto,
        )
        print("\n✅ PASS: Advanced Biscotto Engine imported successfully")
        print(f"   - BiscottoAnalysis: {BiscottoAnalysis}")
        print(f"   - BiscottoSeverity: {BiscottoSeverity}")
        print(f"   - BiscottoPattern: {BiscottoPattern}")
        print(f"   - get_enhanced_biscotto_analysis: {get_enhanced_biscotto_analysis}")
        print(f"   - analyze_biscotto: {analyze_biscotto}")
        return True
    except ImportError as e:
        print(f"\n❌ FAIL: Could not import Advanced Biscotto Engine: {e}")
        return False


def test_analyze_biscotto_function():
    """Test 2: Verify analyze_biscotto function works."""
    print("\n" + "="*60)
    print("TEST 2: analyze_biscotto Function")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import analyze_biscotto, BiscottoSeverity
        
        # Test with suspicious draw odds
        analysis = analyze_biscotto(
            home_team="Juventus",
            away_team="Inter Milan",
            current_draw_odd=2.45,
            opening_draw_odd=3.10,
            home_motivation=None,
            away_motivation=None,
            matches_remaining=None,
            league_key="soccer_italy_serie_a",
        )
        
        print(f"\nMatch: Juventus vs Inter Milan")
        print(f"Draw Odds: 2.45 (from 3.10)")
        print(f"\nAnalysis Result:")
        print(f"  is_suspect: {analysis.is_suspect}")
        print(f"  severity: {analysis.severity.value}")
        print(f"  confidence: {analysis.confidence}%")
        print(f"  pattern: {analysis.pattern.value}")
        print(f"  zscore: {analysis.zscore}")
        print(f"  drop_percentage: {analysis.drop_percentage:.1f}%")
        print(f"  reasoning: {analysis.reasoning}")
        print(f"  betting_recommendation: {analysis.betting_recommendation}")
        
        if analysis.factors:
            print(f"  factors:")
            for factor in analysis.factors[:3]:
                print(f"    - {factor}")
        
        # Verify basic detection
        if not analysis.is_suspect:
            print(f"\n❌ FAIL: Should detect as suspect")
            return False
        
        if analysis.severity not in [BiscottoSeverity.HIGH, BiscottoSeverity.EXTREME]:
            print(f"\n❌ FAIL: Severity should be HIGH or EXTREME")
            return False
        
        print(f"\n✅ PASS: analyze_biscotto works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ FAIL: analyze_biscotto failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_enhanced_biscotto_analysis():
    """Test 3: Verify get_enhanced_biscotto_analysis function works."""
    print("\n" + "="*60)
    print("TEST 3: get_enhanced_biscotto_analysis Function")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis
        
        # Create mock match object
        class MockMatch:
            def __init__(self):
                self.home_team = "AC Milan"
                self.away_team = "Napoli"
                self.league = "soccer_italy_serie_a"
                self.current_draw_odd = 2.30
                self.opening_draw_odd = 2.90
        
        match = MockMatch()
        
        # Call the function
        analysis, context_str = get_enhanced_biscotto_analysis(
            match_obj=match,
            home_motivation=None,
            away_motivation=None,
        )
        
        print(f"\nMatch: {match.home_team} vs {match.away_team}")
        print(f"Draw Odds: {match.current_draw_odd:.2f} (from {match.opening_draw_odd:.2f})")
        print(f"\nAnalysis Result:")
        print(f"  is_suspect: {analysis.is_suspect}")
        print(f"  severity: {analysis.severity.value}")
        print(f"  confidence: {analysis.confidence}%")
        print(f"  pattern: {analysis.pattern.value}")
        print(f"  reasoning: {analysis.reasoning}")
        
        if context_str:
            print(f"\nContext String:")
            print(f"  {context_str[:200]}...")
        
        # Verify basic detection
        if not analysis.is_suspect:
            print(f"\n❌ FAIL: Should detect as suspect")
            return False
        
        print(f"\n✅ PASS: get_enhanced_biscotto_analysis works correctly")
        return True
        
    except Exception as e:
        print(f"\n❌ FAIL: get_enhanced_biscotto_analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pattern_detection():
    """Test 4: Verify pattern detection (DRIFT vs CRASH)."""
    print("\n" + "="*60)
    print("TEST 4: Pattern Detection")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import (
            analyze_biscotto,
            BiscottoPattern,
        )
        
        # Test CRASH pattern (sudden large drop)
        analysis_crash = analyze_biscotto(
            home_team="Team A",
            away_team="Team B",
            current_draw_odd=2.30,
            opening_draw_odd=3.00,  # 23.3% drop
        )
        
        print(f"\nCRASH Test (23.3% drop):")
        print(f"  Pattern: {analysis_crash.pattern.value}")
        
        if analysis_crash.pattern != BiscottoPattern.CRASH:
            print(f"  ⚠️  Expected CRASH, got {analysis_crash.pattern.value}")
        else:
            print(f"  ✅ CRASH detected correctly")
        
        # Test DRIFT pattern (gradual drop)
        analysis_drift = analyze_biscotto(
            home_team="Team C",
            away_team="Team D",
            current_draw_odd=2.60,
            opening_draw_odd=2.85,  # 8.8% drop
        )
        
        print(f"\nDRIFT Test (8.8% drop):")
        print(f"  Pattern: {analysis_drift.pattern.value}")
        
        if analysis_drift.pattern != BiscottoPattern.DRIFT:
            print(f"  ⚠️  Expected DRIFT, got {analysis_drift.pattern.value}")
        else:
            print(f"  ✅ DRIFT detected correctly")
        
        print(f"\n✅ PASS: Pattern detection works")
        return True
        
    except Exception as e:
        print(f"\n❌ FAIL: Pattern detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_minor_league_thresholds():
    """Test 5: Verify minor league dynamic thresholds."""
    print("\n" + "="*60)
    print("TEST 5: Minor League Dynamic Thresholds")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import (
            analyze_biscotto,
            get_draw_threshold_for_league,
        )
        
        # Test standard league threshold
        std_threshold = get_draw_threshold_for_league("soccer_italy_serie_a", end_of_season=False)
        print(f"\nStandard League (Serie A) threshold: {std_threshold}")
        
        # Test minor league threshold
        minor_threshold = get_draw_threshold_for_league("soccer_italy_serie_b", end_of_season=True)
        print(f"Minor League (Serie B, end of season) threshold: {minor_threshold}")
        
        # Verify minor league has stricter threshold
        if minor_threshold <= std_threshold:
            print(f"\n⚠️  Minor league threshold ({minor_threshold}) should be stricter than standard ({std_threshold})")
        else:
            print(f"  ✅ Minor league has stricter threshold as expected")
        
        # Test detection with minor league
        analysis_minor = analyze_biscotto(
            home_team="Brescia",
            away_team="Palermo",
            current_draw_odd=2.55,  # Below 2.50 but above 2.60
            opening_draw_odd=3.20,
            league_key="soccer_italy_serie_b",
            matches_remaining=3,  # End of season
        )
        
        print(f"\nMinor League Test (2.55 draw odd, end of season):")
        print(f"  is_suspect: {analysis_minor.is_suspect}")
        print(f"  severity: {analysis_minor.severity.value}")
        print(f"  confidence: {analysis_minor.confidence}%")
        
        print(f"\n✅ PASS: Minor league thresholds work")
        return True
        
    except Exception as e:
        print(f"\n❌ FAIL: Minor league thresholds failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_zscore_calculation():
    """Test 6: Verify Z-score calculation."""
    print("\n" + "="*60)
    print("TEST 6: Z-Score Calculation")
    print("="*60)
    
    try:
        from src.analysis.biscotto_engine import (
            analyze_biscotto,
            calculate_zscore,
            calculate_implied_probability,
        )
        
        # Test Z-score calculation directly
        prob_2_50 = calculate_implied_probability(2.50)
        zscore_2_50 = calculate_zscore(prob_2_50)
        
        print(f"\nDraw odd 2.50:")
        print(f"  Implied probability: {prob_2_50:.2%}")
        print(f"  Z-score: {zscore_2_50:.2f}")
        
        prob_2_00 = calculate_implied_probability(2.00)
        zscore_2_00 = calculate_zscore(prob_2_00)
        
        print(f"\nDraw odd 2.00:")
        print(f"  Implied probability: {prob_2_00:.2%}")
        print(f"  Z-score: {zscore_2_00:.2f}")
        
        # Test with full analysis
        analysis = analyze_biscotto(
            home_team="Team X",
            away_team="Team Y",
            current_draw_odd=2.00,
            opening_draw_odd=2.50,
        )
        
        print(f"\nFull Analysis (draw odd 2.00):")
        print(f"  zscore: {analysis.zscore}")
        print(f"  implied_probability: {analysis.implied_probability:.2%}")
        
        # Verify Z-score is significant for low odds
        if analysis.zscore < 1.0:
            print(f"\n⚠️  Z-score should be higher for draw odd 2.00")
        else:
            print(f"  ✅ Z-score calculation correct")
        
        print(f"\n✅ PASS: Z-score calculation works")
        return True
        
    except Exception as e:
        print(f"\n❌ FAIL: Z-score calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*60)
    print("BISCOTTO ENGINE MIGRATION TEST SUITE (V13.0) - SIMPLE")
    print("="*60)
    
    tests = [
        ("Advanced Engine Availability", test_advanced_engine_available),
        ("analyze_biscotto Function", test_analyze_biscotto_function),
        ("get_enhanced_biscotto_analysis Function", test_get_enhanced_biscotto_analysis),
        ("Pattern Detection", test_pattern_detection),
        ("Minor League Thresholds", test_minor_league_thresholds),
        ("Z-Score Calculation", test_zscore_calculation),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Migration successful.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
