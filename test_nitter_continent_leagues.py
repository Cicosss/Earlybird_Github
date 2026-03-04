#!/usr/bin/env python3
"""
Test script to verify active leagues by continent in Supabase.
This will verify the claim that only LATAM has active leagues.
"""

import os
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_supabase_leagues_by_continent():
    """Test Supabase connection and check active leagues by continent."""
    print("=" * 80)
    print("🔍 SUPABASE LEAGUES BY CONTINENT TEST")
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

    # Connect to Supabase
    print("[2/4] Connecting to Supabase...")
    try:
        from supabase import create_client

        supabase = create_client(supabase_url, supabase_key)
        print("✅ Connected to Supabase successfully")
        print()
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return False

    # Check if leagues table exists
    print("[3/4] Checking leagues table...")
    try:
        # Use the correct schema: leagues has api_key, tier_name, and nested continent object
        response = (
            supabase.table("leagues")
            .select("id, api_key, tier_name, is_active, continent")
            .execute()
        )
        print("✅ leagues table exists!")
        print(f"   Total records: {len(response.data)}")
        print()
    except Exception as e:
        print(f"❌ Failed to query leagues table: {e}")
        return False

    # Group leagues by continent
    print("[4/4] Analyzing leagues by continent...")
    leagues_by_continent = {}
    active_leagues_by_continent = {}

    for league in response.data:
        # continent is a nested object with a 'name' field
        continent_obj = league.get("continent", {})
        continent = (
            continent_obj.get("name", "UNKNOWN") if isinstance(continent_obj, dict) else "UNKNOWN"
        )
        is_active = league.get("is_active", False)

        if continent not in leagues_by_continent:
            leagues_by_continent[continent] = []
            active_leagues_by_continent[continent] = []

        leagues_by_continent[continent].append(league)
        if is_active:
            active_leagues_by_continent[continent].append(league)

    # Print results
    print("=" * 80)
    print("📊 LEAGUES BY CONTINENT")
    print("=" * 80)
    print()

    for continent in sorted(leagues_by_continent.keys()):
        total = len(leagues_by_continent[continent])
        active = len(active_leagues_by_continent[continent])
        status_icon = "✅" if active > 0 else "⚠️"

        print(f"{status_icon} {continent}:")
        print(f"   Total leagues: {total}")
        print(f"   Active leagues: {active}")

        if active > 0:
            print("   Active leagues:")
            for league in active_leagues_by_continent[continent]:
                league_id = league.get("id", "N/A")
                league_name = league.get("tier_name", league.get("api_key", "N/A"))
                print(f"      - {league_name} (id: {league_id})")
        else:
            print("   ⚠️  No active leagues - nitter cycle will find 0 sources")
        print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()

    continents_with_active = [c for c, leagues in active_leagues_by_continent.items() if leagues]
    continents_without_active = [
        c
        for c, leagues in leagues_by_continent.items()
        if not active_leagues_by_continent.get(c, [])
    ]

    print(f"✅ Continents with active leagues: {len(continents_with_active)}")
    for continent in continents_with_active:
        print(f"   - {continent}: {len(active_leagues_by_continent[continent])} active leagues")

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
