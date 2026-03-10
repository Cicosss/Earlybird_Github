#!/usr/bin/env python3
"""Check the actual table name in the database."""

import os
import sqlite3
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.models import DB_DIR, DB_FILE

db_path = os.path.join(DB_DIR, DB_FILE)
print(f"Database path: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print("\nTables in database:")
    for table in tables:
        print(f"  - {table[0]}")

    # Check for news_log or news_logs
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'news_log%'")
    news_log_tables = cursor.fetchall()
    print("\nNews log related tables:")
    for table in news_log_tables:
        print(f"  - {table[0]}")

    # Get columns from news_log table if it exists
    if news_log_tables:
        table_name = news_log_tables[0][0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"\nColumns in {table_name} table:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

    conn.close()
