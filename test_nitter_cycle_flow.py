#!/usr/bin/env python3
"""
Test Nitter Cycle Flow with Real Supabase Calls

This script simulates the exact flow of the nitter cycle to identify
why "No handles found in Supabase" warning occurs despite
38 active sources existing in the database.

Author: CoVe Verification
Date: 2026-03-03
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


async def test_nitter_cycle_flow():
    """Test the exact nitter cycle flow."""
    print("\n" + "=" * 80)
    print("🔍 NITTER CYCLE FLOW TEST (REAL SUPABASE CALLS)")
    print("=" * 80)

    # Step 1: Import and instantiate SupabaseProvider
    print("\n[1/6] Importing SupabaseProvider...")
    try:
        from src.database.supabase_provider import get_supabase

        print("✅ SupabaseProvider imported successfully")
    except Exception as e:
        print(f"❌ Failed to import SupabaseProvider: {e}")
        return False

    # Step 2: Get Supabase instance
    print("\n[2/6] Getting Supabase instance...")
    try:
        supabase = get_supabase()
        print("✅ Supabase instance obtained")
    except Exception as e:
        print(f"❌ Failed to get Supabase instance: {e}")
        return False

    # Step 3: Check connection status
    print("\n[3/6] Checking connection status...")
    is_connected = supabase.is_connected()
    print(f"   Connected: {is_connected}")

    if not is_connected:
        conn_error = supabase.get_connection_error()
        print(f"❌ Connection error: {conn_error}")
        return False
    else:
        print("✅ Supabase is connected")

    # Step 4: Test get_social_sources() (no continent filter)
    print("\n[4/6] Testing get_social_sources() (no continent filter)...")
    try:
        all_sources = supabase.get_social_sources()
        print(f"✅ Query executed successfully")
        print(f"   Total sources returned: {len(all_sources)}")

        if len(all_sources) == 0:
            print("⚠️  ISSUE: get_social_sources() returned empty list!")
        else:
            print(f"   Sample source: {all_sources[0].get('identifier', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed to get social sources: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Step 5: Filter for active sources (exact logic from nitter cycle)
    print("\n[5/6] Filtering for active sources...")
    try:
        active_sources = [s for s in all_sources if s.get("is_active", False)]
        print(f"✅ Filter applied successfully")
        print(f"   Active sources: {len(active_sources)}")

        if len(active_sources) == 0:
            print("⚠️  ISSUE: No active sources after filtering!")
            print("   This would trigger the 'No handles found in Supabase' warning")
        else:
            print(f"   Sample active source: {active_sources[0].get('identifier', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed to filter sources: {e}")
        return False

    # Step 6: Test with continent filter (if applicable)
    print("\n[6/6] Testing get_active_leagues_for_continent()...")
    test_continents = ["LATAM", "ASIA", "AFRICA"]

    for continent in test_continents:
        try:
            active_leagues = supabase.get_active_leagues_for_continent(continent)
            print(f"   {continent}: {len(active_leagues)} active leagues")

            # Get social sources for these leagues
            all_sources_for_continent = []
            for league in active_leagues:
                league_id = league.get("id")
                if league_id:
                    league_sources = supabase.get_social_sources_for_league(league_id)
                    all_sources_for_continent.extend(league_sources)

            # Filter active
            active_sources_for_continent = [
                s for s in all_sources_for_continent if s.get("is_active", False)
            ]

            print(
                f"      Total sources: {len(all_sources_for_continent)}, Active: {len(active_sources_for_continent)}"
            )

        except Exception as e:
            print(f"   {continent}: Error - {e}")

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    if len(active_sources) > 0:
        print("✅ SUCCESS: Active social sources found")
        print("   The nitter cycle should work correctly")
        print("   If you still see the warning, check:")
        print("   1. Cache expiration (TTL: 1 hour)")
        print("   2. Mirror file data")
        print("   3. Logs for other errors")
        return True
    else:
        print("❌ ERROR: No active social sources found")
        print("   This would trigger the 'No handles found in Supabase' warning")
        print("   SOLUTION: Set is_active=True for at least one source")
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(test_nitter_cycle_flow())

        if success:
            print("\n✅ Nitter cycle flow test PASSED")
            return 0
        else:
            print("\n❌ Nitter cycle flow test FAILED")
            return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
