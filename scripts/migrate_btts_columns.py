#!/usr/bin/env python3
"""
BTTS Columns Migration Script - V12.7
Adds BTTS odds columns to the matches table in Supabase.

Usage:
    python scripts/migrate_btts_columns.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

# Try to import supabase
try:
    from supabase import create_client
    from supabase.errors import APIError
    from supabase.lib.client_options import SyncClientOptions

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("❌ Supabase client not installed. Run: pip install supabase")


def get_supabase_client():
    """Get Supabase client using the service role key for admin operations."""
    if not SUPABASE_AVAILABLE:
        return None

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("❌ Supabase credentials not found in environment")
        return None

    # Use service role key for admin operations (if available)
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if service_key:
        print("✅ Using service role key for admin operations")
        admin_key = service_key
    else:
        print("⚠️ Service role key not found, using regular key (may have limited permissions)")
        admin_key = key

    # Configure client with admin options
    options = SyncClientOptions(
        postgrest_client_timeout=30,
        storage_client_timeout=33,
    )

    client = create_client(url, admin_key, options=options)
    return client


def check_columns_exist(client):
    """Check if BTTS columns already exist in matches table."""
    try:
        result = client.table("matches").select("current_btts_yes").limit(1).execute()
        return True
    except APIError as e:
        if "column" in str(e).lower() or "does not exist" in str(e).lower():
            return False
        raise


def migrate_btts_columns():
    """Migrate BTTS columns to matches table."""
    print("=" * 60)
    print("🔄 BTTS Columns Migration - V12.7")
    print("=" * 60)
    print()

    client = get_supabase_client()
    if not client:
        return 1

    # Check if columns already exist
    print("🔍 Checking if BTTS columns already exist...")
    if check_columns_exist(client):
        print("✅ BTTS columns already exist! No migration needed.")
        return 0

    print("📋 BTTS columns not found. Proceeding with migration...")
    print()

    # SQL migration statements
    migration_statements = [
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS opening_btts_yes FLOAT;",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS opening_btts_no FLOAT;",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS current_btts_yes FLOAT;",
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS current_btts_no FLOAT;",
    ]

    # Execute migration
    print("🚀 Executing migration...")

    for i, stmt in enumerate(migration_statements):
        print(f"   [{i + 1}/{len(migration_statements)}] Executing: {stmt[:60]}...")

        # Try using RPC to execute SQL (if available)
        try:
            result = client.rpc("exec_sql", sql=stmt).execute()
            if hasattr(result, "error") and result.error:
                error_msg = str(result.error)
                if "already exists" in error_msg.lower():
                    print("   ⚠️ Column already exists: skipping...")
                elif "duplicate" in error_msg.lower():
                    print("   ⚠️ Duplicate column, skipping...")
                else:
                    print(f"   ❌ Error: {error_msg}")
                    return 1

            print(f"   ✅ Statement {i + 1}/{len(migration_statements)} executed successfully")
        except Exception as e:
            # RPC not available, try direct approach
            print(f"   ⚠️ RPC not available: {e}")
            print("   Please run the migration SQL manually in Supabase SQL Editor:")
            print()
            print("=" * 60)
            for s in migration_statements:
                print(s)
            print("=" * 60)
            print()
            print(
                "📍 Supabase SQL Editor: https://supabase.com/dashboard/project/jtpxabdskyewrwvkayws/sql"
            )
            print()
            return 1

    # Verify migration
    print()
    print("🔍 Verifying migration...")
    try:
        result = client.table("matches").select("current_btts_yes").limit(1).execute()
        print("✅ Migration verified successfully!")
        print("✅ All BTTS columns now exist in matches table")
        return 0
    except APIError as e:
        print(f"❌ Migration verification failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(migrate_btts_columns())
