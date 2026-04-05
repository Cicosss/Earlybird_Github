#!/usr/bin/env python3
"""
Debug script to understand league data enrichment process.

Author: CoVe Verification
Date: 2026-03-03
"""

import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def test_debug_leagues():
    """Debug league data enrichment."""
    print("\n" + "=" * 80)
    print("🔍 DEBUG LEAGUES TEST")
    print("=" * 80)

    # Import SupabaseProvider
    print("\n[1/5] Importing SupabaseProvider...")
    try:
        from src.database.supabase_provider import get_supabase

        supabase = get_supabase()
        print("   ✅ SupabaseProvider imported successfully")
    except Exception as e:
        print(f"   ❌ Failed to import SupabaseProvider: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Get all active leagues
    print("\n[2/5] Getting all active leagues...")
    try:
        all_leagues = supabase.get_active_leagues()
        print(f"   ✅ Got {len(all_leagues)} active leagues")
    except Exception as e:
        print(f"   ❌ Failed to get active leagues: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Group leagues by continent
    print("\n[3/5] Grouping leagues by continent...")
    leagues_by_continent = {}
    for league in all_leagues:
        continent_obj = league.get("continent", {})
        continent = (
            continent_obj.get("name", "UNKNOWN") if isinstance(continent_obj, dict) else "UNKNOWN"
        )

        if continent not in leagues_by_continent:
            leagues_by_continent[continent] = []

        leagues_by_continent[continent].append(league)

    # Print results
    print("\n[4/5] Printing results...")
    for continent in sorted(leagues_by_continent.keys()):
        leagues = leagues_by_continent[continent]
        print(f"\n   {continent}: {len(leagues)} leagues")
        for league in leagues:
            league_id = league.get("id", "N/A")
            league_name = league.get("tier_name", league.get("api_key", "N/A"))
            country = league.get("country", {})
            country_name = country.get("name", "N/A") if isinstance(country, dict) else "N/A"
            print(f"      - {league_name} ({country_name}) (id: {league_id})")

    # Test get_active_leagues_for_continent
    print("\n[5/5] Testing get_active_leagues_for_continent()...")
    test_continents = ["LATAM", "ASIA", "AFRICA"]
    for continent in test_continents:
        try:
            leagues = supabase.get_active_leagues_for_continent(continent)
            print(f"   {continent}: {len(leagues)} leagues")
        except Exception as e:
            print(f"   {continent}: Error - {e}")

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"   Total active leagues: {len(all_leagues)}")
    print(f"   Continents with leagues: {sorted(leagues_by_continent.keys())}")
    return True


def main():
    """Main entry point."""
    try:
        success = test_debug_leagues()

        if success:
            print("\n✅ Debug leagues test PASSED")
            return 0
        else:
            print("\n❌ Debug leagues test FAILED")
            return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
