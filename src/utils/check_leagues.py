"""
Elite 7 League Verification Script

Verifies that only the Elite 7 leagues are active.
Expected: 7 leagues (TR, AR, MX, GR, SC, AU, FR)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ingestion.league_manager import (
    TIER_1_LEAGUES,
    TIER_2_LEAGUES,
    ALL_LEAGUES,
    get_leagues_for_cycle,
    get_elite_leagues,
)

def main():
    print("=" * 50)
    print("🎯 ELITE 7 LEAGUE VERIFICATION")
    print("=" * 50)
    
    print(f"\n📋 TIER 1 (Elite 7): {len(TIER_1_LEAGUES)} leagues")
    for i, league in enumerate(TIER_1_LEAGUES, 1):
        print(f"   {i}. {league}")
    
    print(f"\n📋 TIER 2 (Disabled): {len(TIER_2_LEAGUES)} leagues")
    if TIER_2_LEAGUES:
        for league in TIER_2_LEAGUES:
            print(f"   - {league}")
    else:
        print("   (empty - disabled)")
    
    print(f"\n📊 Total Active: {len(ALL_LEAGUES)} leagues")
    
    # Verify cycle returns only Elite 7
    cycle_leagues = get_leagues_for_cycle()
    print(f"\n🔄 get_leagues_for_cycle(): {len(cycle_leagues)} leagues")
    
    # Final check
    expected = 7
    actual = len(TIER_1_LEAGUES)
    
    print("\n" + "=" * 50)
    if actual == expected and len(TIER_2_LEAGUES) == 0:
        print(f"✅ PASS: Elite 7 Strategy Active ({actual} leagues)")
    else:
        print(f"❌ FAIL: Expected {expected} Elite + 0 Tier2, got {actual} + {len(TIER_2_LEAGUES)}")
    print("=" * 50)

if __name__ == "__main__":
    main()
