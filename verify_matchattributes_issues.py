"""
Verification script to test the three identified limitations in MatchAttributes.

This script verifies:
1. to_dict() does not serialize datetime in _extra_fields
2. Method names accessible via __getitem__
3. SQLAlchemy session detachment issues
"""

from datetime import datetime
from src.utils.match_helper import MatchAttributes


def test_issue_1_datetime_in_extra_fields():
    """
    Issue 1: to_dict() does not serialize datetime in _extra_fields
    
    The extract_match_info() function adds last_deep_dive_time to _extra_fields,
    which is a datetime object. When to_dict() is called, this datetime should
    be serialized to ISO format, but currently it's not.
    """
    print("\n" + "="*80)
    print("TEST 1: datetime in _extra_fields serialization")
    print("="*80)
    
    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B",
        start_time=datetime(2026, 3, 12, 15, 0, 0)
    )
    
    # Add a datetime to _extra_fields (like last_deep_dive_time)
    test_datetime = datetime(2026, 3, 12, 10, 0, 0)
    attrs["last_deep_dive_time"] = test_datetime
    
    # Convert to dict
    result = attrs.to_dict()
    
    print(f"Original datetime: {test_datetime}")
    print(f"Type in _extra_fields: {type(attrs._extra_fields['last_deep_dive_time'])}")
    print(f"Type in to_dict() result: {type(result['last_deep_dive_time'])}")
    print(f"Value in to_dict() result: {result['last_deep_dive_time']}")
    
    # Check if datetime is serialized
    if isinstance(result['last_deep_dive_time'], str):
        print("✅ PASS: datetime in _extra_fields is serialized to string")
        return True
    else:
        print("❌ FAIL: datetime in _extra_fields is NOT serialized")
        print("   This will cause JSON serialization errors!")
        return False


def test_issue_2_method_names_accessible():
    """
    Issue 2: Method names accessible via __getitem__
    
    The __getitem__ implementation uses hasattr(self.__class__, key) which
    returns True for class methods. This means method names can be accessed
    as dictionary keys, returning the method object instead of raising KeyError.
    """
    print("\n" + "="*80)
    print("TEST 2: Method names accessible via __getitem__")
    print("="*80)
    
    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B"
    )
    
    # Try to access method names as dictionary keys
    method_names = ["keys", "values", "items", "get", "update", "to_dict"]
    
    issues_found = []
    for method_name in method_names:
        try:
            result = attrs[method_name]
            if callable(result):
                print(f"❌ FAIL: attrs['{method_name}'] returns {result} (method object)")
                issues_found.append(method_name)
            else:
                print(f"✅ PASS: attrs['{method_name}'] returns value: {result}")
        except KeyError:
            print(f"✅ PASS: attrs['{method_name}'] raises KeyError (expected)")
    
    if issues_found:
        print(f"\n❌ ISSUE CONFIRMED: Method names {issues_found} are accessible via __getitem__")
        print("   This breaks dictionary-like behavior expectations!")
        return False
    else:
        print("\n✅ PASS: No method names accessible via __getitem__")
        return True


def test_issue_3_session_detachment():
    """
    Issue 3: SQLAlchemy session detachment
    
    The current implementation extracts attributes using getattr() but doesn't
    make deep copies. If the Match object becomes detached from the session,
    lazy-loaded relationships or attributes could still cause DetachedInstanceError.
    """
    print("\n" + "="*80)
    print("TEST 3: SQLAlchemy session detachment simulation")
    print("="*80)
    
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
    from src.utils.match_helper import extract_match_info
    match = MockMatch()
    match_info = extract_match_info(match)
    
    # Verify that datetime objects are copied (not references)
    print(f"match.start_time: {match.start_time}")
    print(f"match_info['start_time']: {match_info['start_time']}")
    print(f"Are they the same object? {match.start_time is match_info['start_time']}")
    
    # Modify the original match's datetime
    match.start_time = datetime(2026, 3, 13, 15, 0, 0)
    print(f"\nAfter modifying match.start_time:")
    print(f"match.start_time: {match.start_time}")
    print(f"match_info['start_time']: {match_info['start_time']}")
    
    if match.start_time == match_info['start_time']:
        print("❌ FAIL: match_info still references the original datetime object")
        print("   If the session detaches, this could cause issues!")
        return False
    else:
        print("✅ PASS: match_info has an independent copy of the datetime")
        return True


def test_json_serialization():
    """
    Test JSON serialization to verify datetime handling.
    """
    print("\n" + "="*80)
    print("TEST 4: JSON serialization with datetime in _extra_fields")
    print("="*80)
    
    import json
    
    # Create a MatchAttributes object
    attrs = MatchAttributes(
        match_id="test123",
        home_team="Team A",
        away_team="Team B",
        start_time=datetime(2026, 3, 12, 15, 0, 0)
    )
    
    # Add datetime to _extra_fields
    attrs["last_deep_dive_time"] = datetime(2026, 3, 12, 10, 0, 0)
    
    # Try to serialize to JSON
    try:
        result = attrs.to_dict()
        json_str = json.dumps(result)
        print(f"✅ PASS: JSON serialization successful")
        print(f"JSON: {json_str[:200]}...")
        return True
    except TypeError as e:
        print(f"❌ FAIL: JSON serialization failed with error: {e}")
        return False


def main():
    """Run all verification tests."""
    print("\n" + "="*80)
    print("MATCHATTRIBUTES ISSUES VERIFICATION")
    print("="*80)
    
    results = {
        "Issue 1: datetime in _extra_fields": test_issue_1_datetime_in_extra_fields(),
        "Issue 2: Method names accessible": test_issue_2_method_names_accessible(),
        "Issue 3: Session detachment": test_issue_3_session_detachment(),
        "JSON Serialization": test_json_serialization(),
    }
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for issue, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {issue}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed - No issues found!")
    else:
        print(f"\n❌ {total - passed} issue(s) confirmed - Fixes needed!")


if __name__ == "__main__":
    main()
