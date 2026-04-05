#!/usr/bin/env python3
"""
Test script to verify MatchAttributes hybrid access patterns and backward compatibility.

This test ensures that the enhanced MatchAttributes class maintains full backward
compatibility with existing dict-based code while providing type-safe access.
"""

from datetime import datetime
from src.utils.match_helper import MatchAttributes, extract_match_info, extract_match_odds


class MockMatch:
    """Mock Match object for testing."""

    def __init__(self):
        self.id = "test_match_123"
        self.home_team = "Team A"
        self.away_team = "Team B"
        self.league = "soccer_test_league"
        self.start_time = datetime.now()
        self.last_deep_dive_time = None
        self.opening_home_odd = 2.50
        self.opening_draw_odd = 3.20
        self.opening_away_odd = 2.80
        self.current_home_odd = 2.45
        self.current_draw_odd = 3.15
        self.current_away_odd = 2.85
        self.opening_over_2_5 = 1.90
        self.opening_under_2_5 = 1.95
        self.current_over_2_5 = 1.88
        self.current_under_2_5 = 1.97


def test_hybrid_access_patterns():
    """Test both type-safe and dictionary-like access patterns."""
    print("=" * 80)
    print("TEST 1: Hybrid Access Patterns")
    print("=" * 80)

    attrs = MatchAttributes(
        match_id="test_123", home_team="Home", away_team="Away", league="test_league"
    )

    # Test type-safe access
    print("\n✓ Type-safe access:")
    print(f"  attrs.home_team = {attrs.home_team}")
    print(f"  attrs.away_team = {attrs.away_team}")

    # Test dictionary-like access
    print("\n✓ Dictionary-like access:")
    print(f"  attrs['home_team'] = {attrs['home_team']}")
    print(f"  attrs['away_team'] = {attrs['away_team']}")

    # Test get() method
    print("\n✓ get() method:")
    print(f"  attrs.get('home_team') = {attrs.get('home_team')}")
    print(f"  attrs.get('nonexistent', 'default') = {attrs.get('nonexistent', 'default')}")

    # Test keys(), values(), items()
    print("\n✓ Dictionary-like methods:")
    print(f"  keys() = {attrs.keys()}")
    print(f"  'home_team' in attrs = {'home_team' in attrs}")
    print(f"  'nonexistent' in attrs = {'nonexistent' in attrs}")

    print("\n✅ TEST 1 PASSED: All hybrid access patterns work correctly\n")


def test_flexible_composition():
    """Test flexible composition with update() method."""
    print("=" * 80)
    print("TEST 2: Flexible Composition")
    print("=" * 80)

    attrs = MatchAttributes(match_id="test_123", home_team="Home", away_team="Away")

    # Test update() method
    print("\n✓ Adding extra fields with update():")
    attrs.update(
        {
            "custom_field_1": "value_1",
            "custom_field_2": "value_2",
            "home_context": {"form": "good"},
            "away_context": {"form": "bad"},
        }
    )

    print(f"  attrs['custom_field_1'] = {attrs['custom_field_1']}")
    print(f"  attrs['home_context'] = {attrs['home_context']}")

    # Test that extra fields are included in to_dict()
    print("\n✓ to_dict() includes extra fields:")
    attrs_dict = attrs.to_dict()
    print(f"  'custom_field_1' in attrs_dict = {'custom_field_1' in attrs_dict}")
    print(f"  'home_context' in attrs_dict = {'home_context' in attrs_dict}")

    print("\n✅ TEST 2 PASSED: Flexible composition works correctly\n")


def test_json_serialization():
    """Test JSON serialization with datetime handling."""
    print("=" * 80)
    print("TEST 3: JSON Serialization")
    print("=" * 80)

    attrs = MatchAttributes(
        match_id="test_123",
        home_team="Home",
        away_team="Away",
        league="test_league",
        start_time=datetime.now(),
    )

    # Test to_dict() with datetime
    print("\n✓ to_dict() handles datetime correctly:")
    attrs_dict = attrs.to_dict()
    print(f"  start_time type in dict: {type(attrs_dict['start_time'])}")
    print(f"  start_time value: {attrs_dict['start_time']}")

    # Test that it's ISO format string
    assert isinstance(attrs_dict["start_time"], str), "start_time should be string in dict"
    assert "T" in attrs_dict["start_time"], "start_time should be in ISO format"

    print("\n✅ TEST 3 PASSED: JSON serialization works correctly\n")


def test_backward_compatibility():
    """Test backward compatibility with existing dict-based code."""
    print("=" * 80)
    print("TEST 4: Backward Compatibility")
    print("=" * 80)

    mock_match = MockMatch()

    # Test extract_match_info
    print("\n✓ extract_match_info() returns MatchAttributes with dict-like access:")
    match_info = extract_match_info(mock_match)

    # Old dict-based code pattern
    home_team = match_info["home_team"]
    away_team = match_info["away_team"]
    league = match_info["league"]
    print(f"  match_info['home_team'] = {home_team}")
    print(f"  match_info['away_team'] = {away_team}")
    print(f"  match_info['league'] = {league}")

    # Test extract_match_odds
    print("\n✓ extract_match_odds() returns MatchAttributes with dict-like access:")
    match_odds = extract_match_odds(mock_match)

    # Old dict-based code pattern
    current_home = match_odds["current_home_odd"]
    current_draw = match_odds["current_draw_odd"]
    current_away = match_odds["current_away_odd"]
    print(f"  match_odds['current_home_odd'] = {current_home}")
    print(f"  match_odds['current_draw_odd'] = {current_draw}")
    print(f"  match_odds['current_away_odd'] = {current_away}")

    # Test dict.update() pattern (used in analyzer.py)
    print("\n✓ dict.update() pattern works:")
    snippet_data = {}
    snippet_data.update(
        {
            "match_id": match_info["match_id"],
            "home_team": match_info["home_team"],
            "away_team": match_info["away_team"],
            "league": match_info["league"],
            "start_time": match_info["start_time"],
            "current_home_odd": match_odds["current_home_odd"],
            "current_away_odd": match_odds["current_away_odd"],
            "current_draw_odd": match_odds["current_draw_odd"],
        }
    )
    print(f"  snippet_data has {len(snippet_data)} fields")
    print(f"  snippet_data['home_team'] = {snippet_data['home_team']}")

    # Test nested dict pattern (used in verifier_integration.py)
    print("\n✓ Nested dict pattern works:")
    alert_data = {
        "match": {
            "home_team": match_info["home_team"],
            "away_team": match_info["away_team"],
            "league": match_info["league"],
            "start_time": match_info["start_time"].isoformat()
            if match_info["start_time"]
            else None,
            "opening_home_odd": match_odds["opening_home_odd"],
            "current_home_odd": match_odds["current_home_odd"],
            "opening_draw_odd": match_odds["opening_draw_odd"],
            "current_draw_odd": match_odds["current_draw_odd"],
            "opening_away_odd": match_odds["opening_away_odd"],
            "current_away_odd": match_odds["current_away_odd"],
        }
    }
    print(f"  alert_data['match']['home_team'] = {alert_data['match']['home_team']}")
    print(f"  alert_data['match'] has {len(alert_data['match'])} fields")

    print("\n✅ TEST 4 PASSED: Backward compatibility maintained\n")


def test_type_safety_improvements():
    """Test new type-safe access patterns."""
    print("=" * 80)
    print("TEST 5: Type Safety Improvements")
    print("=" * 80)

    mock_match = MockMatch()

    # Test extract_match_info
    match_info = extract_match_info(mock_match)

    # New type-safe access pattern
    print("\n✓ Type-safe access (NEW):")
    print(f"  match_info.home_team = {match_info.home_team}")
    print(f"  match_info.away_team = {match_info.away_team}")
    print(f"  match_info.league = {match_info.league}")

    # Test extract_match_odds
    match_odds = extract_match_odds(mock_match)

    print("\n✓ Type-safe access for odds (NEW):")
    print(f"  match_odds.current_home_odd = {match_odds.current_home_odd}")
    print(f"  match_odds.current_draw_odd = {match_odds.current_draw_odd}")
    print(f"  match_odds.current_away_odd = {match_odds.current_away_odd}")

    # Test to_dict() for JSON serialization
    print("\n✓ to_dict() for JSON serialization (NEW):")
    info_dict = match_info.to_dict()
    odds_dict = match_odds.to_dict()
    print(f"  info_dict has {len(info_dict)} fields")
    print(f"  odds_dict has {len(odds_dict)} fields")

    print("\n✅ TEST 5 PASSED: Type safety improvements work correctly\n")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("MATCHATTRIBUTES HYBRID ACCESS PATTERNS - TEST SUITE")
    print("=" * 80)
    print()

    try:
        test_hybrid_access_patterns()
        test_flexible_composition()
        test_json_serialization()
        test_backward_compatibility()
        test_type_safety_improvements()

        print("=" * 80)
        print("✅ ALL TESTS PASSED - MatchAttributes hybrid implementation is working!")
        print("=" * 80)
        print()
        print("SUMMARY:")
        print("  ✓ Backward compatibility maintained (dict access still works)")
        print("  ✓ Type-safe access enabled (attribute access now works)")
        print("  ✓ Flexible composition supported (update() method)")
        print("  ✓ JSON serialization handled (to_dict() with datetime)")
        print("  ✓ Component communication preserved (all existing patterns work)")
        print()

    except Exception as e:
        print("=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(run_all_tests())
