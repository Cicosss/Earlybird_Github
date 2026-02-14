#!/usr/bin/env python3
"""
Verify Social Sources Table Existence (CoVe Mode)

This script verifies if the social_sources table exists in Supabase
and checks its structure and data.

Author: Database Architect (CoVe Mode)
Date: 2026-02-11
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("ERROR: Supabase client not installed. Run: pip install supabase")
    sys.exit(1)


def verify_social_sources_table():
    """Verify if social_sources table exists and check its structure."""
    print("\n" + "="*80)
    print("🔍 VERIFYING: social_sources Table")
    print("="*80)
    
    # Connect to Supabase
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL or SUPABASE_KEY not configured in .env")
        return False
    
    try:
        client = create_client(supabase_url, supabase_key)
        print(f"✅ Connected to Supabase")
    except Exception as e:
        print(f"ERROR: Failed to connect to Supabase: {e}")
        return False
    
    # Try to query social_sources table
    print("\nAttempting to query social_sources table...")
    try:
        response = client.table("social_sources").select("*", count="exact").execute()
        count = response.count if hasattr(response, 'count') else len(response.data)
        print(f"✅ social_sources table exists!")
        print(f"   Record count: {count}")
        
        if response.data:
            print(f"   Sample record: {response.data[0]}")
            print(f"   Columns: {list(response.data[0].keys())}")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ social_sources table does NOT exist or is not accessible")
        print(f"   Error: {error_msg}")
        
        # Check if it's a "relation does not exist" error
        if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
            print("\n⚠️  CRITICAL ISSUE: social_sources table does not exist in Supabase!")
            print("   The code references this table but it's not in the database.")
            print("   This will cause the mirror to be incomplete.")
            return False
        
        return False


def main():
    """Main entry point."""
    success = verify_social_sources_table()
    
    if success:
        print("\n✅ social_sources table verification PASSED")
    else:
        print("\n❌ social_sources table verification FAILED")
        print("\n⚠️  RECOMMENDATION:")
        print("   1. Create the social_sources table in Supabase, OR")
        print("   2. Remove references to social_sources from the code")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
