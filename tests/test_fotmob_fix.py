#!/usr/bin/env python3
"""
Test script to verify FotMob endpoint fix.
Tests that get_match_lineup() now works with the corrected /matchDetails endpoint.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ingestion.data_provider import get_data_provider


def test_match_lineup():
    """Test that match lineup can be retrieved with the fixed endpoint."""
    print("=" * 60)
    print("🧪 Testing FotMob Endpoint Fix")
    print("=" * 60)

    # Test match ID from the error log
    match_id = 4818909
    print(f"\n📋 Testing match ID: {match_id}")
    print("   Match: Hearts vs Hibernian")

    try:
        fotmob = get_data_provider()
        print("\n✅ FotMob provider initialized")

        # Test get_match_lineup
        print(f"\n🔍 Calling get_match_lineup({match_id})...")
        match_data = fotmob.get_match_lineup(match_id)

        if match_data:
            print("\n✅ SUCCESS: Match lineup data retrieved!")
            print(f"   Data keys: {list(match_data.keys())}")

            # Check for lineup data
            content = match_data.get("content", {})
            if "lineup" in content:
                lineup = content["lineup"]
                print("\n✅ Lineup data found:")
                print(f"   - Match ID: {lineup.get('matchId')}")
                print(f"   - Lineup type: {lineup.get('lineupType')}")
                print(f"   - Source: {lineup.get('source')}")

                # Check home and away teams
                if "homeTeam" in lineup:
                    home_team = lineup["homeTeam"]
                    print(f"\n   🏠 Home Team: {home_team.get('name')}")
                    players = home_team.get("players", [])
                    print(f"      Players: {len(players)}")

                if "awayTeam" in lineup:
                    away_team = lineup["awayTeam"]
                    print(f"\n   ✈️  Away Team: {away_team.get('name')}")
                    players = away_team.get("players", [])
                    print(f"      Players: {len(players)}")

                print("\n✅ FIX VERIFIED: The /matchDetails endpoint works correctly!")
                return True
            else:
                print("\n⚠️ WARNING: No lineup data in response")
                print(f"   Content keys: {list(content.keys())}")
                return False
        else:
            print("\n❌ FAILED: No data returned from get_match_lineup()")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_match_lineup()
    sys.exit(0 if success else 1)
