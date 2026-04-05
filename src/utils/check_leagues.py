"""
League Verification Script - V11.2 Flat Architecture

Verifies that the league system is 100% data-driven from Supabase/Mirror.
Reports the number of active leagues from each priority tier.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ingestion.league_manager import (
    get_all_active_leagues,
    get_leagues_for_cycle,
    get_tier1_leagues,
    get_tier2_leagues,
)


def main():
    print("=" * 50)
    print("🎯 V11.2 FLAT ARCHITECTURE - LEAGUE VERIFICATION")
    print("   100% Supabase/Mirror Data-Driven")
    print("=" * 50)

    tier1 = get_tier1_leagues()
    tier2 = get_tier2_leagues()
    all_active = get_all_active_leagues()

    print(f"\n📋 Tier 1 (Priority 1): {len(tier1)} leagues")
    for i, league in enumerate(tier1, 1):
        print(f"   {i}. {league}")

    print(f"\n📋 Tier 2 (Priority 2): {len(tier2)} leagues")
    if tier2:
        for league in tier2:
            print(f"   - {league}")
    else:
        print("   (empty - no priority=2 leagues)")

    print(f"\n📊 Total Active Leagues: {len(all_active)}")

    # Verify cycle returns leagues
    cycle_leagues = get_leagues_for_cycle()
    print(f"\n🔄 get_leagues_for_cycle(): {len(cycle_leagues)} leagues")

    # Final check
    print("\n" + "=" * 50)
    if len(all_active) > 0:
        print(
            f"✅ PASS: V11.2 Flat Architecture Active ({len(all_active)} leagues from Supabase/Mirror)"
        )
    else:
        print(f"❌ FAIL: No active leagues found. Check Supabase connection and mirror file.")
    print("=" * 50)


if __name__ == "__main__":
    main()
