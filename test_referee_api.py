#!/usr/bin/env python3
"""
Test script to verify referee_info implementation works correctly.
Tests get_referee_info() method with real API calls to FotMob.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ingestion.data_provider import FotMobProvider

def test_referee_info(team_name: str):
    """Test get_referee_info() method with a real team."""
    print(f"\n{'='*60}")
    print(f"Testing get_referee_info() for: {team_name}")
    print(f"{'='*60}")
    
    try:
        provider = FotMobProvider()
        result = provider.get_referee_info(team_name)
        
        if result:
            print(f"\n✅ SUCCESS: Referee info extracted!")
            print(f"   Referee Name: {result.get('name')}")
            print(f"   Strictness: {result.get('strictness')}")
            print(f"   Cards/Game: {result.get('cards_per_game')}")
            return True
        else:
            print(f"\n⚠️  NO DATA: Referee info not available")
            print(f"   This could mean:")
            print(f"   - Team has no upcoming match")
            print(f"   - Match ID not available")
            print(f"   - Referee data not in API response")
            return False
            
    except AttributeError as e:
        print(f"\n❌ ERROR: Method not found!")
        print(f"   {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error!")
        print(f"   {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "🧪 Referee Info API Test" + "\n")
    print("Testing real API calls to FotMob to verify referee extraction")
    print("This will make actual HTTP requests to FotMob API")
    print("\n" + "-"*60)
    
    # Test with real teams
    test_teams = ["Alanyaspor", "Eyupspor"]
    
    results = {
        'success': 0,
        'no_data': 0,
        'error': 0
    }
    
    for team in test_teams:
        success = test_referee_info(team)
        if success:
            results['success'] += 1
        elif 'NO DATA' in str(success):
            results['no_data'] += 1
        else:
            results['error'] += 1
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Teams tested: {len(test_teams)}")
    print(f"✅ Successful: {results['success']}")
    print(f"⚠️  No Data: {results['no_data']}")
    print(f"❌ Errors: {results['error']}")
    
    if results['success'] > 0:
        print("\n✅ Implementation is working correctly!")
        print("Referee names are being extracted from FotMob API")
    elif results['no_data'] > 0:
        print("\n⚠️  Some teams have no upcoming matches")
        print("This is expected - implementation handles this gracefully")
    else:
        print("\n❌ Implementation has issues!")
        print("Check the error messages above")
    
    print(f"\n{'='*60}\n")
