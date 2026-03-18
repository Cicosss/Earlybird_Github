#!/usr/bin/env python3
"""
BTTS Columns Migration Script for SQLite - V12.7
Adds BTTS odds columns to the matches table in SQLite.

Usage:
    python scripts/migrate_btts_sqlite.py
"""

import sqlite3
import os

DB_PATH = "data/earlybird.db"

def migrate_btts_columns():
    """Add BTTS columns to matches table."""
    print("=" * 60)
    print("🔄 BTTS Columns Migration for SQLite - V12.7")
    print("=" * 60)
    print()

    if not os.path.exists(DB_PATH):
        print(f"❌ Database file not found: {DB_PATH}")
        print("   Creating new database...")
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(matches)")
    columns = [col[1] for col in cursor.fetchall()]

    btts_columns = [
        ("opening_btts_yes", "FLOAT"),
        ("opening_btts_no", "FLOAT"),
        ("current_btts_yes", "FLOAT"),
        ("current_btts_no", "FLOAT"),
    ]

    columns_to_add = [(name, dtype) for name, dtype in btts_columns if name not in columns]

    if not columns_to_add:
        print("✅ All BTTS columns already exist!")
        conn.close()
        return 0

    print(f"📋 Adding {len(columns_to_add)} BTTS columns...")
    print()

    for col_name, col_type in columns_to_add:
        try:
            sql = f"ALTER TABLE matches ADD COLUMN {col_name} {col_type}"
            print(f"   Executing: {sql}")
            cursor.execute(sql)
            print(f"   ✅ Added: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"   ⚠️ Column {col_name} already exists, skipping")
            else:
                print(f"   ❌ Error adding {col_name}: {e}")
                conn.close()
                return 1

    conn.commit()

    # Verify migration
    print()
    print("🔍 Verifying migration...")
    cursor.execute("PRAGMA table_info(matches)")
    columns = [col[1] for col in cursor.fetchall()]

    all_present = all(name in columns for name, _ in btts_columns)

    if all_present:
        print("✅ Migration verified successfully!")
        print("✅ All BTTS columns now exist in matches table")
        print()
        print("   Columns added:")
        for name, _ in btts_columns:
            print(f"   - {name}")
    else:
        print("❌ Migration verification failed")
        conn.close()
        return 1

    conn.close()
    return 0


if __name__ == "__main__":
    exit(migrate_btts_columns())
