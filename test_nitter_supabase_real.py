#!/usr/bin/env python3
"""
Real Supabase Connection Test for Nitter Cycle Warning

This script makes REAL calls to Supabase to:
1. Verify connection works
2. Check if social_sources table exists
3. Check if there are active sources
4. Identify why "No handles found in Supabase" warning occurs

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

try:
    from supabase import create_client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("❌ ERROR: Supabase client not installed. Run: pip install supabase")
    sys.exit(1)


def test_supabase_connection():
    """Test real Supabase connection."""
    print("\n" + "=" * 80)
    print("🔍 REAL SUPABASE CONNECTION TEST")
    print("=" * 80)

    # Step 1: Check environment variables
    print("\n[1/5] Checking environment variables...")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")

    if not supabase_url:
        print("❌ SUPABASE_URL not found in .env")
        return False
    else:
        print(f"✅ SUPABASE_URL found: {supabase_url[:30]}...")

    if not supabase_key:
        print("❌ SUPABASE_KEY not found in .env")
        return False
    else:
        print(f"✅ SUPABASE_KEY found: {supabase_key[:10]}...")

    # Step 2: Connect to Supabase
    print("\n[2/5] Connecting to Supabase...")
    try:
        client = create_client(supabase_url, supabase_key)
        print("✅ Connected to Supabase successfully")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return False

    # Step 3: Check if social_sources table exists
    print("\n[3/5] Checking if social_sources table exists...")
    try:
        response = client.table("social_sources").select("*", count="exact").execute()
        count = response.count if hasattr(response, "count") else len(response.data)
        print(f"✅ social_sources table exists!")
        print(f"   Total records: {count}")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ social_sources table does NOT exist or is not accessible")
        print(f"   Error: {error_msg}")

        if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
            print("\n⚠️  CRITICAL ISSUE: social_sources table does not exist in Supabase!")
            print("   This is why the nitter cycle shows 'No handles found in Supabase'")
            print("   SOLUTION: Create the social_sources table in Supabase")
            return False

        return False

    # Step 4: Check for active sources
    print("\n[4/5] Checking for active social sources...")
    try:
        response = client.table("social_sources").select("*").eq("is_active", True).execute()
        active_sources = response.data if hasattr(response, "data") else []
        print(f"✅ Query executed successfully")
        print(f"   Active sources (is_active=True): {len(active_sources)}")

        if len(active_sources) == 0:
            print("\n⚠️  ISSUE FOUND: No active social sources in database!")
            print("   This is why the nitter cycle shows 'No handles found in Supabase'")
            print("   SOLUTION: Set is_active=True for at least one social source")
        else:
            print(f"\n✅ Active sources found:")
            for i, source in enumerate(active_sources[:5], 1):
                identifier = source.get("identifier", "N/A")
                description = source.get("description", "N/A")
                league_id = source.get("league_id", "N/A")
                print(f"   {i}. @{identifier} - {description} (league: {league_id})")

            if len(active_sources) > 5:
                print(f"   ... and {len(active_sources) - 5} more")

    except Exception as e:
        print(f"❌ Failed to query active sources: {e}")
        return False

    # Step 5: Check for any sources (active or inactive)
    print("\n[5/5] Checking all social sources (including inactive)...")
    try:
        response = client.table("social_sources").select("*").execute()
        all_sources = response.data if hasattr(response, "data") else []
        print(f"✅ Query executed successfully")
        print(f"   Total sources (all): {len(all_sources)}")

        if len(all_sources) == 0:
            print("\n⚠️  ISSUE FOUND: social_sources table is completely empty!")
            print("   This is why the nitter cycle shows 'No handles found in Supabase'")
            print("   SOLUTION: Add social sources to the social_sources table")
        elif len(all_sources) > 0 and len(active_sources) == 0:
            print(f"\n⚠️  ISSUE FOUND: All {len(all_sources)} sources are inactive!")
            print("   This is why the nitter cycle shows 'No handles found in Supabase'")
            print("   SOLUTION: Set is_active=True for at least one source")

    except Exception as e:
        print(f"❌ Failed to query all sources: {e}")
        return False

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    if len(active_sources) > 0:
        print("✅ SUCCESS: Active social sources found in Supabase")
        print("   The nitter cycle should work correctly")
        print("   If you still see the warning, check the logs for other errors")
        return True
    elif len(all_sources) > 0:
        print("⚠️  WARNING: Social sources exist but none are active")
        print("   SOLUTION: Set is_active=True for at least one source")
        return False
    else:
        print("❌ ERROR: social_sources table is empty")
        print("   SOLUTION: Add social sources to the database")
        return False


def main():
    """Main entry point."""
    success = test_supabase_connection()

    if success:
        print("\n✅ Supabase verification PASSED")
        print("   Nitter cycle should work correctly")
        return 0
    else:
        print("\n❌ Supabase verification FAILED")
        print("\n⚠️  NEXT STEPS:")
        print("   1. Fix the issue identified above")
        print("   2. Restart the bot")
        print("   3. Check if warning persists")
        return 1


if __name__ == "__main__":
    sys.exit(main())
