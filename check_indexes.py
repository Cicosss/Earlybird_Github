#!/usr/bin/env python3
"""Check indexes on news_logs table."""

import os
import sqlite3
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.models import DB_DIR, DB_FILE

db_path = os.path.join(DB_DIR, DB_FILE)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all indexes
cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='news_logs' ORDER BY name"
)
indexes = cursor.fetchall()
print("Indexes on news_logs table:")
for idx in indexes:
    print(f"  - {idx[0]}")

# Check for critical indexes
critical_indexes = [
    "idx_news_logs_odds_at_kickoff",
    "idx_news_logs_alert_sent_at",
    "idx_news_logs_match_id",
    "idx_news_logs_sent",
]

print("\nCritical indexes:")
for idx_name in critical_indexes:
    exists = any(idx[0] == idx_name for idx in indexes)
    print(f"  - {idx_name}: {'✅' if exists else '❌'}")

conn.close()
