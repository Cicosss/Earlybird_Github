#!/usr/bin/env python3
"""
Database Migration Script for V13.0 Outcome Fields

This script adds the 'outcome' and 'outcome_explanation' fields
to the news_logs table to support CLV and ROI analysis.

Usage:
    python scripts/migrate_outcome_fields.py

The script will:
1. Connect to database using project configuration
2. Check if fields already exist
3. Add missing fields
4. Verify the migration was successful
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import DB_DIR, DB_FILE

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns


def apply_migration():
    """Apply V13.0 outcome fields migration."""

    # Build database path
    db_path = os.path.join(DB_DIR, DB_FILE)
    logger.info(f"📦 Connecting to database: {db_path}")

    # Check if database exists
    if not os.path.exists(db_path):
        logger.error(f"❌ Database not found at: {db_path}")
        return False

    # Create backup before migration
    backup_path = f"{db_path}.backup"
    try:
        import shutil

        logger.info(f"💾 Creating backup: {backup_path}")
        shutil.copy2(db_path, backup_path)
        logger.info("✅ Backup created successfully")
    except Exception as e:
        logger.warning(f"⚠️ Could not create backup: {e}")
        logger.warning("⚠️ Continuing without backup...")

    # Connect to database
    try:
        conn = sqlite3.connect(db_path, timeout=60)
        cursor = conn.cursor()
        logger.info("✅ Connected to database successfully")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return False

    # Migration status
    migrations_applied = []

    try:
        # Check and add 'outcome' column
        if not check_column_exists(cursor, "news_logs", "outcome"):
            logger.info("➕ Adding 'outcome' column to news_logs table...")
            cursor.execute("""
                ALTER TABLE news_logs 
                ADD COLUMN outcome VARCHAR(10)
            """)
            migrations_applied.append("outcome")
            logger.info("✅ 'outcome' column added successfully")
        else:
            logger.info("ℹ️ 'outcome' column already exists - skipping")

        # Check and add 'outcome_explanation' column
        if not check_column_exists(cursor, "news_logs", "outcome_explanation"):
            logger.info("➕ Adding 'outcome_explanation' column to news_logs table...")
            cursor.execute("""
                ALTER TABLE news_logs 
                ADD COLUMN outcome_explanation TEXT
            """)
            migrations_applied.append("outcome_explanation")
            logger.info("✅ 'outcome_explanation' column added successfully")
        else:
            logger.info("ℹ️ 'outcome_explanation' column already exists - skipping")

        # Commit changes
        conn.commit()

        if migrations_applied:
            logger.info(
                f"✅ Migration completed successfully! Applied: {', '.join(migrations_applied)}"
            )
        else:
            logger.info("ℹ️ All columns already exist - no migration needed")

        # Verify migration
        logger.info("🔍 Verifying migration...")
        cursor.execute("PRAGMA table_info(news_logs)")
        columns = [col[1] for col in cursor.fetchall()]

        if "outcome" in columns and "outcome_explanation" in columns:
            logger.info("✅ Verification successful - both columns exist")

            # Show sample of schema
            logger.info("📊 Current news_logs schema:")
            for col in cursor.fetchall():
                logger.info(f"   - {col[1]} ({col[2]})")

            return True
        else:
            logger.error("❌ Verification failed - columns not found")
            return False

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
            logger.info("🔌 Database connection closed")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("🚀 V13.0 DATABASE MIGRATION: Outcome Fields")
    logger.info("=" * 60)
    logger.info("")

    success = apply_migration()

    logger.info("")
    logger.info("=" * 60)
    if success:
        logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run the bot to test the new functionality")
        logger.info("2. Monitor logs for CLV report generation")
        logger.info("3. Verify that outcomes are saved during settlement")
        logger.info("4. Check Telegram for strategy performance reports")
        sys.exit(0)
    else:
        logger.error("❌ MIGRATION FAILED")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("- Check database file permissions")
        logger.error("- Verify database is not locked by another process")
        logger.error("- Ensure EARLYBIRD_DATA_DIR and EARLYBIRD_DB_FILE are set correctly")
        logger.error("- Check backup file if migration failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
