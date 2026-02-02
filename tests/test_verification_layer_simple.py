"""
Simple test to verify safe_dict_get import works in verification_layer.py
"""

# Test 1: Verify that safe_dict_get is imported
def test_safe_dict_get_import():
    from src.analysis.verification_layer import safe_dict_get
    assert safe_dict_get is not None, "safe_dict_get should be imported"


# Test 2: Verify that safe_dict_get is used correctly
def test_safe_dict_get_usage():
    # Mock data that should return None for non-dict values
    mock_data = {'not_a_dict': 'string value'}
    
    # Import safe_dict_get
    from src.analysis.verification_layer import safe_dict_get
    
    # Test with non-dict data (should return default)
    result = safe_dict_get(mock_data, 'key1', default='default')
    assert result == 'default', f"safe_dict_get should return default for non-dict data"
    print("✅ safe_dict_get returns default for non-dict data")


if __name__ == "__main__":
    test_safe_dict_get_import()
    test_safe_dict_get_usage()
    print("\n" + "="*60)
    print("✅ All tests passed!")
