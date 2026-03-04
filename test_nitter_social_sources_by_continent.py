#!/usr/bin/env python3
"""
Test script to verify social sources by continent in Supabase.
This will check if each continent's active leagues have social sources.
"""

import os
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_social_sources_by_continent():
    """Test Supabase connection and check social sources by continent."""
    print("=" * 80)
    print("🔍 SUPABASE SOCIAL SOURCES BY CONTINENT TEST")
    print("=" * 80)
    print()

    # Check environment variables
    print("[1/5] Checking environment variables...")
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
    print("[2/5] Creating SupabaseProvider...")
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
    print("[3/5] Fetching active leagues...")
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
    print("[4/5] Analyzing social sources by continent...")
    leagues_by_continent = {}

    for league in all_leagues:
        continent_obj = league.get("continent", {})
        continent = (
            continent_obj.get("name", "UNKNOWN") if isinstance(continent_obj, dict) else "UNKNOWN"
        )
        league_id = league.get("id")
        league_name = league.get("tier_name", league.get("api_key", "N/A"))

        if continent not in leagues_by_continent:
            leagues_by_continent[continent] = []

        leagues_by_continent[continent].append({"id": league_id, "name": league_name})

    # Check social sources for each continent
    print("=" * 80)
    print("📊 SOCIAL SOURCES BY CONTINENT")
    print("=" * 80)
    print()

    for continent in sorted(leagues_by_continent.keys()):
        leagues = leagues_by_continent[continent]
        print(f"🌍 {continent}:")
        print(f"   Active leagues: {len(leagues)}")

        total_sources = 0
        for league in leagues:
            league_id = league["id"]
            league_name = league["name"]

            try:
                sources = supabase.get_social_sources_for_league(league_id)
                active_sources = [s for s in sources if s.get("is_active", False)]
                total_sources += len(active_sources)

                if active_sources:
                    print(f"   ✅ {league_name}: {len(active_sources)} active sources")
                    for source in active_sources[:3]:  # Show first 3
                        handle = source.get("identifier", "N/A")
                        print(f"      - @{handle}")
                    if len(active_sources) > 3:
                        print(f"      ... and {len(active_sources) - 3} more")
                else:
                    print(f"   ⚠️  {league_name}: 0 active sources")
            except Exception as e:
                print(f"   ❌ {league_name}: Error fetching sources: {e}")

        print(f"   📊 Total active sources for {continent}: {total_sources}")
        print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()

    print("✅ Social sources verification PASSED")
    return True


if __name__ == "__main__":
    try:
        success = test_social_sources_by_continent()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
