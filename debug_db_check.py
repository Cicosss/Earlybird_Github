#!/usr/bin/env python3
"""
Database Integrity Check and Diagnostic Script
===============================================
Comprehensive database verification for EarlyBird bot debug session.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from src.database.models import Match, NewsLog, SessionLocal, TeamAlias, init_db


def check_database_integrity():
    """Check database integrity and structure."""
    print("=" * 80)
    print("DATABASE INTEGRITY CHECK")
    print("=" * 80)

    try:
        # Initialize database
        init_db()
        print("✅ Database initialized successfully")

        session = SessionLocal()

        try:
            # Check table counts
            print("\n📊 TABLE COUNTS:")
            print("-" * 40)

            match_count = session.query(func.count(Match.id)).scalar()
            newslog_count = session.query(func.count(NewsLog.id)).scalar()
            teamalias_count = session.query(func.count(TeamAlias.id)).scalar()

            print(f"  Matches:        {match_count:,}")
            print(f"  News Logs:      {newslog_count:,}")
            print(f"  Team Aliases:   {teamalias_count:,}")

            # Check database file size
            db_path = Path("data/earlybird.db")
            if db_path.exists():
                db_size_mb = db_path.stat().st_size / (1024 * 1024)
                print(f"\n  Database Size:  {db_size_mb:.2f} MB")

            # Check for orphaned records
            print("\n🔍 ORPHANED RECORDS CHECK:")
            print("-" * 40)

            # Check NewsLogs without valid match_id
            orphaned_newslogs = (
                session.query(NewsLog)
                .filter(~NewsLog.match_id.in_(session.query(Match.id)))
                .count()
            )

            if orphaned_newslogs > 0:
                print(f"  ⚠️  Orphaned NewsLogs: {orphaned_newslogs}")
            else:
                print("  ✅ No orphaned NewsLogs")

            # Check match status distribution
            print("\n📈 MATCH STATUS DISTRIBUTION:")
            print("-" * 40)

            status_counts = (
                session.query(Match.match_status, func.count(Match.id))
                .group_by(Match.match_status)
                .all()
            )

            for status, count in status_counts:
                status_label = status or "NULL"
                print(f"  {status_label:20s}: {count:,}")

            # Check upcoming matches
            now = datetime.utcnow()
            upcoming_matches = session.query(Match).filter(Match.start_time > now).count()

            print(f"\n  Upcoming matches: {upcoming_matches:,}")

            # Check recent matches (last 24 hours)
            recent_cutoff = now - timedelta(hours=24)
            recent_matches = session.query(Match).filter(Match.start_time >= recent_cutoff).count()

            print(f"  Recent matches (24h): {recent_matches:,}")

            # Check alert status
            print("\n🚨 ALERT STATUS:")
            print("-" * 40)

            sent_alerts = session.query(NewsLog).filter(NewsLog.sent == True).count()
            pending_alerts = session.query(NewsLog).filter(NewsLog.sent == False).count()

            print(f"  Sent alerts:     {sent_alerts:,}")
            print(f"  Pending alerts:  {pending_alerts:,}")

            # Check high confidence alerts
            high_confidence = session.query(NewsLog).filter(NewsLog.score >= 8).count()

            print(f"  High confidence (score >= 8): {high_confidence:,}")

            # Check verification status
            print("\n✅ VERIFICATION STATUS:")
            print("-" * 40)

            verification_counts = (
                session.query(NewsLog.verification_status, func.count(NewsLog.id))
                .group_by(NewsLog.verification_status)
                .all()
            )

            for status, count in verification_counts:
                status_label = status or "NULL"
                print(f"  {status_label:20s}: {count:,}")

            # Check category distribution
            print("\n📋 CATEGORY DISTRIBUTION:")
            print("-" * 40)

            category_counts = (
                session.query(NewsLog.category, func.count(NewsLog.id))
                .group_by(NewsLog.category)
                .order_by(func.count(NewsLog.id).desc())
                .limit(10)
                .all()
            )

            for category, count in category_counts:
                category_label = category or "NULL"
                print(f"  {category_label:20s}: {count:,}")

            # Check for data quality issues
            print("\n🔧 DATA QUALITY CHECKS:")
            print("-" * 40)

            # Matches without odds
            matches_no_odds = session.query(Match).filter(Match.current_home_odd.is_(None)).count()

            print(f"  Matches without odds: {matches_no_odds:,}")

            # NewsLogs without summary
            newslogs_no_summary = (
                session.query(NewsLog)
                .filter(NewsLog.summary.is_(None) | (NewsLog.summary == ""))
                .count()
            )

            print(f"  NewsLogs without summary: {newslogs_no_summary:,}")

            # Check for duplicate match IDs (shouldn't happen with primary key)
            print("\n🔄 DUPLICATE CHECK:")
            print("-" * 40)
            print("  ✅ No duplicates (primary key constraint)")

            # Check database performance
            print("\n⚡ PERFORMANCE METRICS:")
            print("-" * 40)

            # Sample query performance
            start_time = datetime.now()
            session.query(Match).limit(100).all()
            query_time = (datetime.now() - start_time).total_seconds() * 1000

            print(f"  Sample query (100 matches): {query_time:.2f} ms")

            # Check WAL mode
            try:
                result = session.execute(text("PRAGMA journal_mode")).fetchone()
                print(f"  Journal mode: {result[0] if result else 'Unknown'}")
            except Exception as e:
                print(f"  ⚠️  Could not check journal mode: {e}")

            # Check cache size
            try:
                result = session.execute(text("PRAGMA cache_size")).fetchone()
                print(f"  Cache size: {result[0] if result else 'Unknown'}")
            except Exception as e:
                print(f"  ⚠️  Could not check cache size: {e}")

            print("\n" + "=" * 80)
            print("✅ DATABASE INTEGRITY CHECK COMPLETED SUCCESSFULLY")
            print("=" * 80)

            return True

        except SQLAlchemyError as e:
            print(f"\n❌ Database error: {e}")
            return False
        finally:
            session.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def check_environment_variables():
    """Check critical environment variables."""
    print("\n" + "=" * 80)
    print("ENVIRONMENT VARIABLES CHECK")
    print("=" * 80)

    critical_vars = [
        "ODDS_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "BRAVE_API_KEY_1",
        "BRAVE_API_KEY_2",
        "BRAVE_API_KEY_3",
        "TAVILY_API_KEY_1",
        "MEDIASTACK_API_KEY_1",
        "PERPLEXITY_API_KEY",
        "OPENROUTER_API_KEY",
    ]

    print("\n🔑 CRITICAL VARIABLES:")
    print("-" * 40)

    missing_vars = []
    for var in critical_vars:
        # Special handling for TELEGRAM_BOT_TOKEN with fallback to TELEGRAM_TOKEN
        # This matches the pattern in config/settings.py and src/alerting/notifier.py
        if var == "TELEGRAM_BOT_TOKEN":
            value = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_TOKEN", "")
            if value:
                # Show which variable was used
                source = (
                    "TELEGRAM_BOT_TOKEN"
                    if os.getenv("TELEGRAM_BOT_TOKEN")
                    else "TELEGRAM_TOKEN (fallback)"
                )
                masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                print(f"  ✅ {var:30s}: {masked} [{source}]")
            else:
                print(f"  ⚠️  {var:30s}: NOT SET (neither TELEGRAM_BOT_TOKEN nor TELEGRAM_TOKEN)")
                missing_vars.append(var)
        else:
            value = os.getenv(var)
            if value:
                # Show first few characters only
                masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                print(f"  ✅ {var:30s}: {masked}")
            else:
                print(f"  ⚠️  {var:30s}: NOT SET")
                missing_vars.append(var)

    if missing_vars:
        print(f"\n⚠️  {len(missing_vars)} critical variables missing")
        print("   Some functionality may be limited")
    else:
        print("\n✅ All critical variables set")

    return len(missing_vars) == 0


def main():
    """Main diagnostic function."""
    print("\n" + "=" * 80)
    print("EARLYBIRD BOT - COMPREHENSIVE DIAGNOSTIC CHECK")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    # Check environment variables
    env_ok = check_environment_variables()

    # Check database integrity
    db_ok = check_database_integrity()

    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"  Environment: {'✅ OK' if env_ok else '⚠️  WARNING'}")
    print(f"  Database:    {'✅ OK' if db_ok else '❌ ERROR'}")
    print("=" * 80)

    if env_ok and db_ok:
        print("\n✅ System ready for testing")
        return 0
    else:
        print("\n⚠️  Some issues detected - review above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
