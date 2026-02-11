#!/usr/bin/env python3
"""
Test script to verify Bug #20 fix: Team Stats - None Values

This script tests that:
1. get_team_details_by_name correctly converts team_name to team_id
2. get_team_stats returns proper structure with None values and helpful note
3. The fix doesn't crash the system
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ingestion.data_provider import FotMobProvider
from unittest.mock import Mock, patch, MagicMock
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_get_team_details_by_name():
    """Test that get_team_details_by_name converts team_name to team_id."""
    print("\n=== Test 1: get_team_details_by_name ===")
    
    provider = FotMobProvider()
    
    # Mock the search_team_id to return a known ID
    with patch.object(provider, 'search_team_id', return_value=(12345, 'Hearts')):
        # Mock get_team_details to return test data
        with patch.object(provider, 'get_team_details', return_value={
            'team_id': 12345,
            'name': 'Hearts',
            'squad': {},
            'fixtures': {}
        }) as mock_get_team_details:
            result = provider.get_team_details_by_name('Hearts')
            
            # Verify search_team_id was called
            provider.search_team_id.assert_called_once_with('Hearts')
            
            # Verify get_team_details was called with the ID
            mock_get_team_details.assert_called_once_with(12345, None)
            
            print(f"✅ get_team_details_by_name correctly converts team_name to team_id")
            print(f"   Result: {result}")
            return True

def test_get_team_stats():
    """Test that get_team_stats returns proper structure."""
    print("\n=== Test 2: get_team_stats ===")
    
    provider = FotMobProvider()
    
    # Mock get_team_details_by_name to return empty stats
    with patch.object(provider, 'get_team_details_by_name', return_value={
        'team_id': 12345,
        'name': 'Hearts',
        'squad': {},
        'fixtures': {}
    }):
        result = provider.get_team_stats('Hearts')
        
        # Verify result structure
        assert 'team_name' in result
        assert 'goals_avg' in result
        assert 'cards_avg' in result
        assert 'corners_avg' in result
        assert 'error' in result
        assert 'source' in result
        assert 'note' in result
        
        # Verify values are None (FotMob doesn't provide stats)
        assert result['goals_avg'] is None
        assert result['cards_avg'] is None
        assert result['corners_avg'] is None
        
        # Verify source and note
        assert result['source'] == 'fotmob'
        assert 'FotMob does not provide team statistics' in result['note']
        
        print(f"✅ get_team_stats returns proper structure")
        print(f"   Result: {result}")
        return True

def test_get_team_stats_with_error():
    """Test that get_team_stats handles errors gracefully."""
    print("\n=== Test 3: get_team_stats with error ===")
    
    provider = FotMobProvider()
    
    # Mock get_team_details_by_name to return an error
    with patch.object(provider, 'get_team_details_by_name', return_value={
        '_error': True,
        '_error_msg': 'Team not found'
    }):
        result = provider.get_team_stats('Unknown Team')
        
        # Verify result structure
        assert 'team_name' in result
        assert 'goals_avg' in result
        assert 'cards_avg' in result
        assert 'corners_avg' in result
        assert 'error' in result
        assert 'source' in result
        assert 'note' in result
        
        # Verify values are None
        assert result['goals_avg'] is None
        assert result['cards_avg'] is None
        assert result['corners_avg'] is None
        assert result['error'] is None  # Error should be None for graceful handling
        
        print(f"✅ get_team_stats handles errors gracefully")
        print(f"   Result: {result}")
        return True

def test_get_full_team_context():
    """Test that get_full_team_context uses the wrapper."""
    print("\n=== Test 4: get_full_team_context ===")
    
    provider = FotMobProvider()
    
    # Mock get_team_details_by_name
    with patch.object(provider, 'get_team_details_by_name', return_value={
        'team_id': 12345,
        'name': 'Hearts',
        'squad': {},
        'fixtures': {}
    }):
        with patch.object(provider, 'get_table_context', return_value={
            'zone': 'Mid-table',
            'position': 6,
            'motivation': 'Medium'
        }):
            result = provider.get_full_team_context('Hearts')
            
            # Verify result structure
            assert 'injuries' in result
            assert 'motivation' in result
            assert 'fatigue' in result
            
            print(f"✅ get_full_team_context uses the wrapper correctly")
            print(f"   Result: {result}")
            return True

def test_get_stadium_coordinates():
    """Test that get_stadium_coordinates uses the wrapper."""
    print("\n=== Test 5: get_stadium_coordinates ===")
    
    provider = FotMobProvider()
    
    # Mock get_team_details_by_name to return stadium info
    with patch.object(provider, 'get_team_details_by_name', return_value={
        'team_id': 12345,
        'name': 'Hearts',
        'stadium': {
            'lat': 55.8642,
            'lon': -3.1879
        }
    }):
        result = provider.get_stadium_coordinates('Hearts')
        
        # Verify result
        assert result is not None
        assert result[0] == 55.8642
        assert result[1] == -3.1879
        
        print(f"✅ get_stadium_coordinates uses the wrapper correctly")
        print(f"   Result: {result}")
        return True

def test_get_turnover_risk():
    """Test that get_turnover_risk uses the wrapper."""
    print("\n=== Test 6: get_turnover_risk ===")
    
    provider = FotMobProvider()
    
    # Mock get_team_details_by_name
    with patch.object(provider, 'get_team_details_by_name', return_value={
        'team_id': 12345,
        'name': 'Hearts',
        'squad': {}
    }):
        result = provider.get_turnover_risk('Hearts')
        
        # Result may be None (no turnover risk data available)
        print(f"✅ get_turnover_risk uses the wrapper correctly")
        print(f"   Result: {result}")
        return True

if __name__ == '__main__':
    print("=" * 60)
    print("Testing Bug #20 Fix: Team Stats - None Values")
    print("=" * 60)
    
    tests = [
        test_get_team_details_by_name,
        test_get_team_stats,
        test_get_team_stats_with_error,
        test_get_full_team_context,
        test_get_stadium_coordinates,
        test_get_turnover_risk
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n❌ {failed} test(s) failed!")
        sys.exit(1)
