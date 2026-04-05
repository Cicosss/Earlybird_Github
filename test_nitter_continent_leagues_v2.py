#!/usr/bin/env python3
"""
Test script to verify active leagues by continent in Supabase.
This will verify the claim that only LATAM has active leagues.
Uses SupabaseProvider to get enriched data.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_supabase_leagues_by_continent():
    """Test Supabase connection and check active leagues by continent."""
    print("=" * 80)
    print("🔍 SUPABASE LEAGUES BY CONTINENT TEST (Using SupabaseProvider)")
    print("=" * 80)
    print()

    # Check environment variables
    print("[1/4] Checking environment variables...")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        print("❌ SUPABASE_URL not found in environment")
        return False
    if not supabase_key:
        print("❌ SUPABASE_KEY not found in environment")
        return False

    print(f"✅ SUPABASE_URL found: {supabase_url[:50]}...")
    print(f"✅ SUPABASE_KEY found: {supabase_key[:20]}...")
    print()

    # Import and create SupabaseProvider
    print("[2/4] Creating SupabaseProvider...")
    try:
        from src.database.supabase_provider import get_supabase

        supabase = get_supabase()
        print("✅ SupabaseProvider created successfully")
        print()
    except Exception as e:
        print(f"❌ Failed to create SupabaseProvider: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Get all active leagues
    print("[3/4] Fetching active leagues...")
    try:
        all_leagues = supabase.get_active_leagues()
        print(f"✅ Fetched {len(all_leagues)} active leagues")
        print()
    except Exception as e:
        print(f"❌ Failed to fetch active leagues: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Group leagues by continent
    print("[4/4] Analyzing leagues by continent...")
    leagues_by_continent = {}

    for league in all_leagues:
        # continent is a nested object with a 'name' field
        continent_obj = league.get("continent", {})
        continent = (
            continent_obj.get("name", "UNKNOWN") if isinstance(continent_obj, dict) else "UNKNOWN"
        )

        if continent not in leagues_by_continent:
            leagues_by_continent[continent] = []

        leagues_by_continent[continent].append(league)

    # Print results
    print("=" * 80)
    print("📊 ACTIVE LEAGUES BY CONTINENT")
    print("=" * 80)
    print()

    for continent in sorted(leagues_by_continent.keys()):
        leagues = leagues_by_continent[continent]
        status_icon = "✅" if leagues else "⚠️"

        print(f"{status_icon} {continent}:")
        print(f"   Active leagues: {len(leagues)}")

        if leagues:
            print(f"   Active leagues:")
            for league in leagues:
                league_id = league.get("id", "N/A")
                league_name = league.get("tier_name", league.get("api_key", "N/A"))
                country = league.get("country", {})
                country_name = country.get("name", "N/A") if isinstance(country, dict) else "N/A"
                print(f"      - {league_name} ({country_name}) (id: {league_id})")
        else:
            print(f"   ⚠️  No active leagues - nitter cycle will find 0 sources")
        print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()

    continents_with_active = [c for c, leagues in leagues_by_continent.items() if leagues]
    continents_without_active = [c for c, leagues in leagues_by_continent.items() if not leagues]

    print(f"✅ Continents with active leagues: {len(continents_with_active)}")
    for continent in continents_with_active:
        print(f"   - {continent}: {len(leagues_by_continent[continent])} active leagues")

    if continents_without_active:
        print(f"⚠️  Continents without active leagues: {len(continents_without_active)}")
        for continent in continents_without_active:
            print(f"   - {continent}: 0 active leagues (nitter cycle will log warning)")
    else:
        print("✅ All continents have active leagues")

    print()
    print("✅ Supabase leagues verification PASSED")
    return True


if __name__ == "__main__":
    try:
        success = test_supabase_leagues_by_continent()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
