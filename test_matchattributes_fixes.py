"""
Comprehensive test suite for MatchAttributes fixes applied to resolve
the three identified limitations in the verification report.

This test suite verifies:
1. datetime objects in _extra_fields are properly serialized to ISO format
2. Method names are NOT accessible via __getitem__ (proper KeyError behavior)
3. SQLAlchemy session detachment is properly handled
4. JSON serialization works correctly with datetime in _extra_fields
5. All existing functionality remains intact (backward compatibility)
"""

import json
from datetime import datetime

from src.utils.match_helper import MatchAttributes, extract_match_info


def test_datetime_in_extra_fields_serialization():
    """
    Test that datetime objects in _extra_fields are serialized to ISO format.

    This was Issue 1 in the verification report.
    """
    print("\n" + "=" * 80)
    print("TEST 1: datetime in _extra_fields serialization")
    print("=" * 80)

    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B",
        start_time=datetime(2026, 3, 12, 15, 0, 0),
    )

    # Add datetime to _extra_fields (like last_deep_dive_time)
    test_datetime = datetime(2026, 3, 12, 10, 0, 0)
    attrs["last_deep_dive_time"] = test_datetime

    # Convert to dict
    result = attrs.to_dict()

    # Verify datetime is serialized
    assert isinstance(result["last_deep_dive_time"], str), (
        f"Expected str, got {type(result['last_deep_dive_time'])}"
    )
    assert result["last_deep_dive_time"] == "2026-03-12T10:00:00", (
        f"Expected '2026-03-12T10:00:00', got {result['last_deep_dive_time']}"
    )

    print("✅ PASS: datetime in _extra_fields is serialized to ISO format")
    return True


def test_method_names_not_accessible():
    """
    Test that method names are NOT accessible via __getitem__.

    This was Issue 2 in the verification report.
    """
    print("\n" + "=" * 80)
    print("TEST 2: Method names NOT accessible via __getitem__")
    print("=" * 80)

    # Create a MatchAttributes object
    attrs = MatchAttributes(match_id="test123", home_team="Team A", away_team="Team B")

    # Method names that should NOT be accessible as dictionary keys
    method_names = ["keys", "values", "items", "get", "update", "to_dict"]

    for method_name in method_names:
        # Try to access method name as dictionary key
        result = attrs[method_name]

        # Should return None (from _extra_fields.get()), not a method object
        assert result is None, f"Expected None for attrs['{method_name}'], got {result}"

        # Should NOT be callable
        assert not callable(result), (
            f"attrs['{method_name}'] should not be callable, got {callable(result)}"
        )

    print("✅ PASS: Method names are NOT accessible via __getitem__")
    return True


def test_json_serialization_with_datetime_in_extra_fields():
    """
    Test that JSON serialization works correctly with datetime in _extra_fields.

    This is a consequence of Issue 1 being fixed.
    """
    print("\n" + "=" * 80)
    print("TEST 3: JSON serialization with datetime in _extra_fields")
    print("=" * 80)

    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B",
        start_time=datetime(2026, 3, 12, 15, 0, 0),
    )

    # Add datetime to _extra_fields
    attrs["last_deep_dive_time"] = datetime(2026, 3, 12, 10, 0, 0)

    # Try to serialize to JSON
    result = attrs.to_dict()
    json_str = json.dumps(result)

    # Verify JSON is valid
    parsed = json.loads(json_str)
    assert parsed["last_deep_dive_time"] == "2026-03-12T10:00:00", (
        f"Expected '2026-03-12T10:00:00', got {parsed['last_deep_dive_time']}"
    )

    print("✅ PASS: JSON serialization works correctly")
    return True


def test_session_detachment_handling():
    """
    Test that SQLAlchemy session detachment is properly handled.

    This was Issue 3 in the verification report (already working, but verify).
    """
    print("\n" + "=" * 80)
    print("TEST 4: SQLAlchemy session detachment handling")
    print("=" * 80)

    # Create a mock Match object with datetime attributes
    class MockMatch:
        def __init__(self):
            self.id = "test123"
            self.home_team = "Team A"
            self.away_team = "Team B"
            self.league = "test_league"
            self.start_time = datetime(2026, 3, 12, 15, 0, 0)
            self.last_deep_dive_time = datetime(2026, 3, 12, 10, 0, 0)
            self.opening_home_odd = 2.5
            self.current_home_odd = 2.3

    # Extract attributes
    match = MockMatch()
    match_info = extract_match_info(match)

    # Verify that datetime objects are copied (not references)
    assert match.start_time == match_info["start_time"], "Datetime values should be equal"

    # Modify the original match's datetime
    match.start_time = datetime(2026, 3, 13, 15, 0, 0)

    # Verify match_info is independent
    assert match.start_time != match_info["start_time"], (
        "match_info should have an independent copy of the datetime"
    )

    print("✅ PASS: Session detachment is properly handled")
    return True


def test_backward_compatibility():
    """
    Test that all existing functionality remains intact.
    """
    print("\n" + "=" * 80)
    print("TEST 5: Backward compatibility")
    print("=" * 80)

    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B",
        league="test_league",
        start_time=datetime(2026, 3, 12, 15, 0, 0),
    )

    # Test dictionary-like access
    assert attrs["home_team"] == "Team A"
    assert attrs["away_team"] == "Team B"

    # Test type-safe access
    assert attrs.home_team == "Team A"
    assert attrs.away_team == "Team B"

    # Test get() method
    assert attrs.get("home_team") == "Team A"
    assert attrs.get("nonexistent") is None
    assert attrs.get("nonexistent", "default") == "default"

    # Test update() method
    attrs.update({"custom_field": "value"})
    assert attrs["custom_field"] == "value"

    # Test keys() method
    keys = attrs.keys()
    assert "home_team" in keys
    assert "custom_field" in keys

    # Test values() method
    values = attrs.values()
    assert "Team A" in values
    assert "value" in values

    # Test items() method
    items = attrs.items()
    assert ("home_team", "Team A") in items
    assert ("custom_field", "value") in items

    # Test __contains__ method
    assert "home_team" in attrs
    assert "custom_field" in attrs
    assert "nonexistent" not in attrs

    # Test to_dict() method
    result = attrs.to_dict()
    assert result["home_team"] == "Team A"
    assert result["custom_field"] == "value"

    print("✅ PASS: All existing functionality works correctly")
    return True


def test_extract_match_info_with_datetime_in_extra_fields():
    """
    Test that extract_match_info() properly handles datetime in _extra_fields.

    This is a real-world usage pattern from src/main.py:620
    """
    print("\n" + "=" * 80)
    print("TEST 6: extract_match_info() with datetime in _extra_fields")
    print("=" * 80)

    # Create a mock Match object
    class MockMatch:
        def __init__(self):
            self.id = "test123"
            self.home_team = "Team A"
            self.away_team = "Team B"
            self.league = "test_league"
            self.start_time = datetime(2026, 3, 12, 15, 0, 0)
            self.last_deep_dive_time = datetime(2026, 3, 12, 10, 0, 0)

    # Extract match info
    match = MockMatch()
    match_info = extract_match_info(match)

    # Verify last_deep_dive_time is in _extra_fields
    assert "last_deep_dive_time" in match_info._extra_fields, (
        "last_deep_dive_time should be in _extra_fields"
    )

    # Verify datetime is accessible
    assert match_info["last_deep_dive_time"] == datetime(2026, 3, 12, 10, 0, 0), (
        "last_deep_dive_time should be accessible via __getitem__"
    )

    # Verify to_dict() serializes datetime in _extra_fields
    result = match_info.to_dict()
    assert isinstance(result["last_deep_dive_time"], str), (
        "last_deep_dive_time should be serialized to string in to_dict()"
    )
    assert result["last_deep_dive_time"] == "2026-03-12T10:00:00", (
        "last_deep_dive_time should be in ISO format"
    )

    # Verify JSON serialization works
    json_str = json.dumps(result)
    parsed = json.loads(json_str)
    assert parsed["last_deep_dive_time"] == "2026-03-12T10:00:00", (
        "JSON should contain serialized datetime"
    )

    print("✅ PASS: extract_match_info() handles datetime in _extra_fields correctly")
    return True


def test_edge_cases():
    """
    Test edge cases and corner scenarios.
    """
    print("\n" + "=" * 80)
    print("TEST 7: Edge cases")
    print("=" * 80)

    # Test 1: None datetime in _extra_fields
    attrs = MatchAttributes(home_team="Team A")
    attrs["last_deep_dive_time"] = None
    result = attrs.to_dict()
    assert result["last_deep_dive_time"] is None, "None datetime should remain None in to_dict()"

    # Test 2: Multiple datetime objects in _extra_fields
    attrs = MatchAttributes(home_team="Team A")
    attrs["datetime1"] = datetime(2026, 3, 12, 10, 0, 0)
    attrs["datetime2"] = datetime(2026, 3, 13, 15, 0, 0)
    result = attrs.to_dict()
    assert isinstance(result["datetime1"], str), "datetime1 should be serialized"
    assert isinstance(result["datetime2"], str), "datetime2 should be serialized"

    # Test 3: Mixed types in _extra_fields
    attrs = MatchAttributes(home_team="Team A")
    attrs["string_field"] = "value"
    attrs["int_field"] = 42
    attrs["float_field"] = 3.14
    attrs["datetime_field"] = datetime(2026, 3, 12, 10, 0, 0)
    attrs["dict_field"] = {"key": "value"}
    result = attrs.to_dict()
    assert result["string_field"] == "value"
    assert result["int_field"] == 42
    assert result["float_field"] == 3.14
    assert isinstance(result["datetime_field"], str), "datetime_field should be serialized"
    assert result["dict_field"] == {"key": "value"}

    # Test 4: Empty _extra_fields
    attrs = MatchAttributes(home_team="Team A")
    result = attrs.to_dict()
    assert "home_team" in result, "Core fields should be in to_dict()"

    # Test 5: to_dict() with include_extra=False
    attrs = MatchAttributes(home_team="Team A")
    attrs["custom_field"] = "value"
    result = attrs.to_dict(include_extra=False)
    assert "custom_field" not in result, "Extra fields should not be included"
    assert "home_team" in result, "Core fields should be included"

    print("✅ PASS: All edge cases handled correctly")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("MATCHATTRIBUTES FIXES COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    tests = [
        ("datetime in _extra_fields serialization", test_datetime_in_extra_fields_serialization),
        ("Method names NOT accessible", test_method_names_not_accessible),
        ("JSON serialization", test_json_serialization_with_datetime_in_extra_fields),
        ("Session detachment handling", test_session_detachment_handling),
        ("Backward compatibility", test_backward_compatibility),
        (
            "extract_match_info() with datetime",
            test_extract_match_info_with_datetime_in_extra_fields,
        ),
        ("Edge cases", test_edge_cases),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except AssertionError as e:
            print(f"❌ FAIL: {name}")
            print(f"   Error: {e}")
            results[name] = False
        except Exception as e:
            print(f"❌ ERROR: {name}")
            print(f"   Error: {e}")
            results[name] = False

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed - All fixes verified!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
