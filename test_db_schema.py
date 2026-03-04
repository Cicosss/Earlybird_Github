#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.getcwd())

print("Test 5: Verify database schema and functions work")
try:
    from src.alerting.orchestration_metrics import (
        get_metrics_collector,
    )

    # Get collector instance
    collector = get_metrics_collector()
    print("✅ get_metrics_collector() works")

    # Check database tables
    cursor = collector._conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"   Tables: {tables}")

    # Check news_log schema
    cursor.execute("PRAGMA table_info(news_log)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"   news_log columns: {columns}")

    # Test _get_matches_in_analysis_count
    count = collector._get_matches_in_analysis_count()
    print(f"   _get_matches_in_analysis_count(): {count}")

    # Test _get_alerts_count
    alerts = collector._get_alerts_count()
    print(f"   _get_alerts_count(): {alerts}")

    # Test _get_matches_analyzed_count
    analyzed = collector._get_matches_analyzed_count()
    print(f"   _get_matches_analyzed_count(): {analyzed}")

    cursor.close()
    print("✅ All functions work correctly")
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback

    traceback.print_exc()
