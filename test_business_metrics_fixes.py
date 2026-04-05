#!/usr/bin/env python3
"""
Test script for BusinessMetrics fixes verification.

This script tests the fixes applied to orchestration_metrics.py:
1. Table name fix (news_log -> news_logs)
2. Semantic mismatch fix (COUNT(*) -> COUNT(DISTINCT match_id))
3. Error tracking implementation
"""

import os
import sys
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

# Setup path
sys.path.append(os.getcwd())

from src.alerting.orchestration_metrics import OrchestrationMetricsCollector


def test_table_name_fix():
    """Test that queries use correct table name 'news_logs' (plural)."""
    print("🧪 Testing BUG #1: Table name fix...")

    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        # Initialize collector with test database
        collector = OrchestrationMetricsCollector(db_path=test_db_path)

        # Create news_logs table manually for testing
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # Create news_logs table (plural, as in models.py)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                sent BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert test data
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO news_logs (match_id, sent, created_at) VALUES (?, ?, ?)",
            ("match1", 1, now),
        )
        cursor.execute(
            "INSERT INTO news_logs (match_id, sent, created_at) VALUES (?, ?, ?)",
            ("match2", 1, now),
        )
        conn.commit()
        conn.close()

        # Test _get_alerts_count (should not raise "no such table" error)
        try:
            alerts = collector._get_alerts_count(hours=1)
            print(f"✅ _get_alerts_count() returned {alerts} (expected 2)")
            assert alerts == 2, f"Expected 2 alerts, got {alerts}"
        except sqlite3.OperationalError as e:
            if "no such table: news_log" in str(e):
                print(f"❌ FAILED: Still using wrong table name 'news_log' (singular)")
                return False
            raise

        print("✅ BUG #1 FIXED: Table name corrected to 'news_logs' (plural)")
        return True

    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)


def test_semantic_mismatch_fix():
    """Test that matches_analyzed uses COUNT(DISTINCT match_id)."""
    print("\n🧪 Testing BUG #2: Semantic mismatch fix...")

    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        # Initialize collector with test database
        collector = OrchestrationMetricsCollector(db_path=test_db_path)

        # Create news_logs table manually for testing
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # Create news_logs table (plural, as in models.py)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert test data: 3 news entries for match1, 2 for match2
        # Total: 5 entries, but only 2 unique matches
        now = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            cursor.execute(
                "INSERT INTO news_logs (match_id, created_at) VALUES (?, ?)", ("match1", now)
            )
        for i in range(2):
            cursor.execute(
                "INSERT INTO news_logs (match_id, created_at) VALUES (?, ?)", ("match2", now)
            )
        conn.commit()
        conn.close()

        # Test _get_matches_analyzed_count
        matches = collector._get_matches_analyzed_count(hours=1)
        print(f"✅ _get_matches_analyzed_count() returned {matches} (expected 2)")

        if matches == 5:
            print(
                f"❌ FAILED: Still using COUNT(*) - counting all entries instead of unique matches"
            )
            return False
        elif matches == 2:
            print(f"✅ BUG #2 FIXED: Using COUNT(DISTINCT match_id) to count unique matches")
            return True
        else:
            print(f"❌ FAILED: Unexpected count {matches}")
            return False

    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)


def test_error_tracking_implementation():
    """Test that errors_by_type returns real error counts from database."""
    print("\n🧪 Testing BUG #3: Error tracking implementation...")

    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        # Initialize collector with test database
        collector = OrchestrationMetricsCollector(db_path=test_db_path)

        # Record some test errors
        collector.record_error(
            error_type="database_errors",
            error_message="Test database error",
            severity="ERROR",
            component="test",
        )
        collector.record_error(
            error_type="api_errors",
            error_message="Test API error",
            severity="ERROR",
            component="test",
        )
        collector.record_error(
            error_type="database_errors",
            error_message="Another database error",
            severity="ERROR",
            component="test",
        )

        # Test _get_errors_by_type
        errors = collector._get_errors_by_type()
        print(f"✅ _get_errors_by_type() returned: {errors}")

        # Check if errors are tracked correctly
        if errors == {
            "database_errors": 0,
            "api_errors": 0,
            "analysis_errors": 0,
            "notification_errors": 0,
        }:
            print(f"❌ FAILED: Still returning hardcoded zeros")
            return False
        elif errors.get("database_errors") == 2 and errors.get("api_errors") == 1:
            print(f"✅ BUG #3 FIXED: Error tracking implemented correctly")
            return True
        else:
            print(f"❌ FAILED: Unexpected error counts {errors}")
            return False

    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)


def test_record_error_intelligent():
    """Test that record_error_intelligent function works correctly."""
    print("\n🧪 Testing record_error_intelligent function...")

    try:
        from src.alerting.orchestration_metrics import record_error_intelligent

        # Create a temporary database for testing
        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
            test_db_path = f.name

        try:
            # Initialize collector with test database
            collector = OrchestrationMetricsCollector(db_path=test_db_path)

            # Test record_error_intelligent
            record_error_intelligent(
                error_type="database_errors",
                error_message="Test error via record_error_intelligent",
                severity="ERROR",
                component="test_component",
                match_id="test_match",
            )

            # Verify error was recorded
            errors = collector._get_errors_by_type()
            print(f"✅ record_error_intelligent() recorded error: {errors}")

            if errors.get("database_errors") == 1:
                print(f"✅ record_error_intelligent() works correctly")
                return True
            else:
                print(f"❌ FAILED: Error not recorded correctly")
                return False

        finally:
            # Cleanup
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)
    except ImportError as e:
        print(f"❌ FAILED: record_error_intelligent not available: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("🧪 BusinessMetrics Fixes Verification Tests")
    print("=" * 70)

    results = []

    # Test BUG #1: Table name fix
    results.append(("BUG #1: Table name fix", test_table_name_fix()))

    # Test BUG #2: Semantic mismatch fix
    results.append(("BUG #2: Semantic mismatch fix", test_semantic_mismatch_fix()))

    # Test BUG #3: Error tracking implementation
    results.append(("BUG #3: Error tracking implementation", test_error_tracking_implementation()))

    # Test record_error_intelligent function
    results.append(("record_error_intelligent", test_record_error_intelligent()))

    # Print summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not result:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED - BusinessMetrics fixes are working correctly!")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Please review the fixes")
        return 1


if __name__ == "__main__":
    sys.exit(main())
