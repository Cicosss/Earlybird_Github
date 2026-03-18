#!/usr/bin/env python3
"""
Test script to verify StructuredAnalysis integration.

This script tests the intelligent component communication and workflow integration.
"""

import sys
from typing import Any

# Add src to path
sys.path.insert(0, "src")

from src.utils.high_value_detector import StructuredAnalysis


def test_from_dict():
    """Test conversion from dict to StructuredAnalysis."""
    print("🧪 TEST 1: from_dict() conversion")

    # Simulate LLM response
    llm_response = {
        "is_high_value": True,
        "team": "Juventus",
        "opponent": "Milan",
        "competition": "Serie A",
        "match_date": "2026-03-20",
        "category": "MASS_ABSENCE",
        "absent_count": 4,
        "absent_players": ["Chiesa", "Vlahovic", "Locatelli", "Bremer"],
        "absent_roles": ["FWD", "FWD", "MID", "DEF"],
        "absent_reason": "injury",
        "match_importance": "IMPORTANT",
        "motivation_home": "HIGH",
        "motivation_away": "NORMAL",
        "has_travel_issues": False,
        "has_financial_crisis": False,
        "betting_impact": "HIGH",
        "confidence": 0.85,
        "summary_italian": "Juventus senza 4 titolari per infortunio",
        "summary_en": "Juventus missing 4 starters due to injuries",
    }

    # Convert to StructuredAnalysis
    analysis = StructuredAnalysis.from_dict(llm_response)

    # Verify fields
    assert analysis.team == "Juventus", f"Expected 'Juventus', got '{analysis.team}'"
    assert analysis.opponent == "Milan", f"Expected 'Milan', got '{analysis.opponent}'"
    assert analysis.absent_count == 4, f"Expected 4, got {analysis.absent_count}"
    assert len(analysis.absent_names) == 4, f"Expected 4 players, got {len(analysis.absent_names)}"
    assert len(analysis.absent_roles) == 4, f"Expected 4 roles, got {len(analysis.absent_roles)}"
    assert analysis.match_importance == "IMPORTANT", f"Expected 'IMPORTANT', got '{analysis.match_importance}'"
    assert analysis.motivation_home == "HIGH", f"Expected 'HIGH', got '{analysis.motivation_home}'"
    assert analysis.motivation_away == "NORMAL", f"Expected 'NORMAL', got '{analysis.motivation_away}'"
    assert analysis.has_travel_issues == False, f"Expected False, got {analysis.has_travel_issues}"
    assert analysis.has_financial_crisis == False, f"Expected False, got {analysis.has_financial_crisis}"
    assert analysis.summary_en == "Juventus missing 4 starters due to injuries", f"Summary EN mismatch"
    assert analysis.summary_it == "Juventus senza 4 titolari per infortunio", f"Summary IT mismatch"

    print("✅ from_dict() conversion: PASSED")
    return True


def test_is_valid_for_alert():
    """Test validation logic."""
    print("\n🧪 TEST 2: is_valid_for_alert() validation")

    # Test case 1: Valid - 3+ absences
    analysis1 = StructuredAnalysis(
        team="Inter",
        absent_count=3,
        absent_names=["Lautaro", "Barella", "Bastoni"],
    )
    assert analysis1.is_valid_for_alert() == True, "3+ absences should be valid"
    print("  ✅ 3+ absences: VALID")

    # Test case 2: Valid - Youth team
    analysis2 = StructuredAnalysis(
        team="Roma",
        absent_type="YOUTH_TEAM",
        absent_count=0,
    )
    assert analysis2.is_valid_for_alert() == True, "Youth team should be valid"
    print("  ✅ Youth team: VALID")

    # Test case 3: Valid - Financial crisis
    analysis3 = StructuredAnalysis(
        team="Napoli",
        has_financial_crisis=True,
        absent_count=0,
    )
    assert analysis3.is_valid_for_alert() == True, "Financial crisis should be valid"
    print("  ✅ Financial crisis: VALID")

    # Test case 4: Valid - Goalkeeper absent
    analysis4 = StructuredAnalysis(
        team="Lazio",
        absent_count=1,
        absent_roles=["GK"],
    )
    assert analysis4.is_valid_for_alert() == True, "Goalkeeper absent should be valid"
    print("  ✅ Goalkeeper absent: VALID")

    # Test case 5: Invalid - No team
    analysis5 = StructuredAnalysis(
        team=None,
        absent_count=5,
    )
    assert analysis5.is_valid_for_alert() == False, "No team should be invalid"
    print("  ✅ No team: INVALID")

    # Test case 6: Invalid - Only 1 non-key player
    analysis6 = StructuredAnalysis(
        team="Fiorentina",
        absent_count=1,
        absent_names=["Random Player"],
    )
    assert analysis6.is_valid_for_alert() == False, "1 non-key player should be invalid"
    print("  ✅ 1 non-key player: INVALID")

    print("✅ is_valid_for_alert() validation: PASSED")
    return True


def test_get_alert_priority():
    """Test priority calculation."""
    print("\n🧪 TEST 3: get_alert_priority() priority calculation")

    # Test case 1: CRITICAL - Youth team
    analysis1 = StructuredAnalysis(
        team="Atalanta",
        absent_type="YOUTH_TEAM",
        absent_count=0,
    )
    assert analysis1.get_alert_priority() == "CRITICAL", "Youth team should be CRITICAL"
    print("  ✅ Youth team: CRITICAL")

    # Test case 2: CRITICAL - Financial crisis
    analysis2 = StructuredAnalysis(
        team="Sassuolo",
        has_financial_crisis=True,
        absent_count=0,
    )
    assert analysis2.get_alert_priority() == "CRITICAL", "Financial crisis should be CRITICAL"
    print("  ✅ Financial crisis: CRITICAL")

    # Test case 3: CRITICAL - 5+ absences
    analysis3 = StructuredAnalysis(
        team="Torino",
        absent_count=5,
    )
    assert analysis3.get_alert_priority() == "CRITICAL", "5+ absences should be CRITICAL"
    print("  ✅ 5+ absences: CRITICAL")

    # Test case 4: HIGH - 3 absences
    analysis4 = StructuredAnalysis(
        team="Bologna",
        absent_count=3,
    )
    assert analysis4.get_alert_priority() == "HIGH", "3 absences should be HIGH"
    print("  ✅ 3 absences: HIGH")

    # Test case 5: HIGH - Goalkeeper absent
    analysis5 = StructuredAnalysis(
        team="Udinese",
        absent_count=1,
        absent_roles=["GK"],
    )
    assert analysis5.get_alert_priority() == "HIGH", "Goalkeeper absent should be HIGH"
    print("  ✅ Goalkeeper absent: HIGH")

    # Test case 6: HIGH - Travel issues
    analysis6 = StructuredAnalysis(
        team="Monza",
        has_travel_issues=True,
        absent_count=0,
    )
    assert analysis6.get_alert_priority() == "HIGH", "Travel issues should be HIGH"
    print("  ✅ Travel issues: HIGH")

    # Test case 7: MEDIUM - 1 absence
    analysis7 = StructuredAnalysis(
        team="Cagliari",
        absent_count=1,
    )
    assert analysis7.get_alert_priority() == "MEDIUM", "1 absence should be MEDIUM"
    print("  ✅ 1 absence: MEDIUM")

    # Test case 8: LOW - No absences
    analysis8 = StructuredAnalysis(
        team="Genoa",
        absent_count=0,
    )
    assert analysis8.get_alert_priority() == "LOW", "No absences should be LOW"
    print("  ✅ No absences: LOW")

    print("✅ get_alert_priority() priority calculation: PASSED")
    return True


def test_cross_validate_with_pattern():
    """Test cross-validation with pattern detector."""
    print("\n🧪 TEST 4: cross_validate_with_pattern() validation")

    # Test case 1: Agreement - boost confidence
    analysis1 = StructuredAnalysis(
        team="Verona",
        absent_type="INJURY",
        absent_count=4,
        confidence=0.80,
    )
    is_valid, adjustment = analysis1.cross_validate_with_pattern("MASS_ABSENCE", 4)
    assert is_valid == True, "Agreement should be valid"
    assert adjustment > 0, f"Agreement should boost confidence, got {adjustment}"
    print(f"  ✅ Agreement: confidence boost +{adjustment:.2f}")

    # Test case 2: Disagreement - penalty
    analysis2 = StructuredAnalysis(
        team="Lecce",
        absent_type="OTHER",
        absent_count=0,
        confidence=0.80,
    )
    is_valid, adjustment = analysis2.cross_validate_with_pattern("MASS_ABSENCE", 5)
    assert is_valid == True, "Should still be valid"
    assert adjustment < 0, f"Disagreement should penalize confidence, got {adjustment}"
    print(f"  ✅ Disagreement: confidence penalty {adjustment:.2f}")

    # Test case 3: No pattern detected - no adjustment
    analysis3 = StructuredAnalysis(
        team="Empoli",
        absent_type="INJURY",
        absent_count=2,
        confidence=0.80,
    )
    is_valid, adjustment = analysis3.cross_validate_with_pattern(None, None)
    assert is_valid == True, "No pattern should be valid"
    assert adjustment == 0, f"No pattern should have no adjustment, got {adjustment}"
    print(f"  ✅ No pattern: no adjustment")

    print("✅ cross_validate_with_pattern() validation: PASSED")
    return True


def test_enrich_with_context():
    """Test enrichment with database context."""
    print("\n🧪 TEST 5: enrich_with_context() enrichment")

    # Create analysis with missing fields
    analysis = StructuredAnalysis(
        team="Parma",
        opponent=None,
        competition=None,
        match_date=None,
        match_importance="NORMAL",
        motivation_home="NORMAL",
        motivation_away="NORMAL",
    )

    # Enrichment data from database
    enrichment_data = {
        "opponent": "Como",
        "competition": "Serie B",
        "match_date": "2026-03-21",
        "match_importance": "IMPORTANT",
        "motivation_home": "HIGH",
        "motivation_away": "LOW",
    }

    # Apply enrichment
    analysis.enrich_with_context(enrichment_data)

    # Verify enrichment
    assert analysis.opponent == "Como", f"Expected 'Como', got '{analysis.opponent}'"
    assert analysis.competition == "Serie B", f"Expected 'Serie B', got '{analysis.competition}'"
    assert analysis.match_date == "2026-03-21", f"Expected '2026-03-21', got '{analysis.match_date}'"
    assert analysis.match_importance == "IMPORTANT", f"Expected 'IMPORTANT', got '{analysis.match_importance}'"
    assert analysis.motivation_home == "HIGH", f"Expected 'HIGH', got '{analysis.motivation_home}'"
    assert analysis.motivation_away == "LOW", f"Expected 'LOW', got '{analysis.motivation_away}'"

    print("  ✅ Opponent enriched: Como")
    print("  ✅ Competition enriched: Serie B")
    print("  ✅ Match date enriched: 2026-03-21")
    print("  ✅ Match importance enriched: IMPORTANT")
    print("  ✅ Motivation home enriched: HIGH")
    print("  ✅ Motivation away enriched: LOW")

    print("✅ enrich_with_context() enrichment: PASSED")
    return True


def test_to_dict():
    """Test conversion back to dict."""
    print("\n🧪 TEST 6: to_dict() conversion")

    analysis = StructuredAnalysis(
        team="Palermo",
        opponent="Bari",
        absent_count=2,
        absent_names=["Bruno", "Silvestri"],
        absent_roles=["MID", "GK"],
        competition="Serie C",
        match_date="2026-03-22",
        match_importance="NORMAL",
        motivation_home="NORMAL",
        motivation_away="NORMAL",
        has_travel_issues=False,
        has_financial_crisis=False,
        confidence=0.75,
        summary_en="Palermo missing 2 players",
        summary_it="Palermo senza 2 giocatori",
        betting_impact="MEDIUM",
    )

    # Convert to dict
    result = analysis.to_dict()

    # Verify fields
    assert result["team"] == "Palermo", f"Expected 'Palermo', got '{result['team']}'"
    assert result["opponent"] == "Bari", f"Expected 'Bari', got '{result['opponent']}'"
    assert result["absent_count"] == 2, f"Expected 2, got {result['absent_count']}"
    assert len(result["absent_players"]) == 2, f"Expected 2 players, got {len(result['absent_players'])}"
    assert len(result["absent_roles"]) == 2, f"Expected 2 roles, got {len(result['absent_roles'])}"
    assert result["competition"] == "Serie C", f"Expected 'Serie C', got '{result['competition']}'"
    assert result["match_date"] == "2026-03-22", f"Expected '2026-03-22', got '{result['match_date']}'"
    assert result["match_importance"] == "NORMAL", f"Expected 'NORMAL', got '{result['match_importance']}'"
    assert result["motivation_home"] == "NORMAL", f"Expected 'NORMAL', got '{result['motivation_home']}'"
    assert result["motivation_away"] == "NORMAL", f"Expected 'NORMAL', got '{result['motivation_away']}'"
    assert result["has_travel_issues"] == False, f"Expected False, got {result['has_travel_issues']}"
    assert result["has_financial_crisis"] == False, f"Expected False, got {result['has_financial_crisis']}"
    assert result["summary_en"] == "Palermo missing 2 players", f"Summary EN mismatch"
    assert result["summary_it"] == "Palermo senza 2 giocatori", f"Summary IT mismatch"
    assert result["betting_impact"] == "MEDIUM", f"Expected 'MEDIUM', got '{result['betting_impact']}'"

    print("✅ to_dict() conversion: PASSED")
    return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("🤖 STRUCTUREDANALYSIS INTEGRATION TEST SUITE")
    print("=" * 70)

    tests = [
        test_from_dict,
        test_is_valid_for_alert,
        test_get_alert_priority,
        test_cross_validate_with_pattern,
        test_enrich_with_context,
        test_to_dict,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    if failed == 0:
        print("✅ ALL TESTS PASSED! StructuredAnalysis is working correctly.")
        return 0
    else:
        print(f"❌ {failed} test(s) failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
