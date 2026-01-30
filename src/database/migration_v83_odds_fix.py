"""
Database Migration V8.3: Fix Learning Loop Integrity - Proper Odds Capture

This migration adds new fields to properly track historical odds for accurate ROI calculation.

Problem:
- `odds_taken` and `closing_odds` were storing current odds at analysis time
- ROI calculations were using incorrect odds, falsifying learning data

Solution:
- Add `odds_at_alert` to store actual odds when alert is sent
- Add `odds_at_kickoff` to store actual odds at match kickoff
- Add `alert_sent_at` to track when alert was sent
- Add indexes for frequently queried fields to improve query performance

Indexes Created:
- idx_news_logs_odds_at_kickoff: For CLV calculations
- idx_news_logs_alert_sent_at: For time-based queries

Run: python -m src.database.migration_v83_odds_fix
"""

import logging
from sqlalchemy import text
from src.database.db import get_db_context

logger = logging.getLogger(__name__)


def migrate():
    """Apply V8.3 migration to add proper odds tracking fields."""
    
    with get_db_context() as db:
        try:
            # Check if new columns already exist
            inspector = db.bind.dialect.get_inspector(db.bind)
            columns = [col['name'] for col in inspector.get_columns('news_logs')]
            
            new_columns = ['odds_at_alert', 'odds_at_kickoff', 'alert_sent_at']
            columns_to_add = [col for col in new_columns if col not in columns]
            
            if not columns_to_add:
                logger.info("✅ V8.3 Migration: New columns already exist. Skipping.")
                return True
            
            logger.info(f"🔄 V8.3 Migration: Adding columns: {columns_to_add}")
            
            # Add new columns
            if 'odds_at_alert' in columns_to_add:
                db.execute(text("ALTER TABLE news_logs ADD COLUMN odds_at_alert FLOAT"))
                logger.info("  ✓ Added odds_at_alert column")
            
            if 'odds_at_kickoff' in columns_to_add:
                db.execute(text("ALTER TABLE news_logs ADD COLUMN odds_at_kickoff FLOAT"))
                logger.info("  ✓ Added odds_at_kickoff column")
            
            if 'alert_sent_at' in columns_to_add:
                db.execute(text("ALTER TABLE news_logs ADD COLUMN alert_sent_at DATETIME"))
                logger.info("  ✓ Added alert_sent_at column")
            
            db.commit()
            logger.info("✅ V8.3 Migration completed successfully!")
            
            # Create indexes for frequently queried fields
            # This improves query performance as the dataset grows
            try:
                # Check if indexes already exist
                indexes = inspector.get_indexes('news_logs')
                existing_index_names = [idx['name'] for idx in indexes]
                
                # Create index for odds_at_kickoff (used in CLV calculations)
                if 'idx_news_logs_odds_at_kickoff' not in existing_index_names:
                    db.execute(text("CREATE INDEX idx_news_logs_odds_at_kickoff ON news_logs(odds_at_kickoff)"))
                    logger.info("  ✓ Created index on odds_at_kickoff")
                else:
                    logger.info("  ✓ Index on odds_at_kickoff already exists")
                
                # Create index for alert_sent_at (used in time-based queries)
                if 'idx_news_logs_alert_sent_at' not in existing_index_names:
                    db.execute(text("CREATE INDEX idx_news_logs_alert_sent_at ON news_logs(alert_sent_at)"))
                    logger.info("  ✓ Created index on alert_sent_at")
                else:
                    logger.info("  ✓ Index on alert_sent_at already exists")
                
                db.commit()
                logger.info("✅ V8.3 Indexes created successfully!")
                
            except Exception as e:
                logger.warning(f"⚠️  Could not create indexes: {e}")
                logger.warning("⚠️  Migration completed but indexes may be missing. Performance may be affected.")
                # Don't fail the migration if indexes fail
            
            # Log data quality note
            logger.info("ℹ️  Note: Existing records will have NULL values for new columns.")
            logger.info("ℹ️  New alerts will use proper odds tracking going forward.")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ V8.3 Migration failed: {e}")
            db.rollback()
            return False


def rollback():
    """
    Rollback V8.3 migration by removing new columns and indexes.
    
    IMPORTANT: SQLite does not support DROP COLUMN directly. Manual rollback steps are required.
    
    Manual Rollback Procedure:
    ---------------------------
    1. Backup your database:
       cp data/earlybird.db data/earlybird.db.backup
    
    2. Drop the V8.3 indexes (if they exist):
       DROP INDEX IF EXISTS idx_news_logs_odds_at_kickoff;
       DROP INDEX IF EXISTS idx_news_logs_alert_sent_at;
    
    3. Create a new table without the V8.3 columns:
       CREATE TABLE news_logs_new (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           match_id INTEGER NOT NULL,
           news_summary TEXT,
           news_url TEXT,
           highest_score_sent FLOAT,
           sent BOOLEAN DEFAULT FALSE,
           created_at DATETIME,
           odds_taken FLOAT,
           closing_odds FLOAT,
           recommended_market TEXT,
           FOREIGN KEY (match_id) REFERENCES matches (id)
       );
    
    4. Copy data from old table to new table (excluding V8.3 columns):
       INSERT INTO news_logs_new (id, match_id, news_summary, news_url, highest_score_sent, sent, created_at, odds_taken, closing_odds, recommended_market)
       SELECT id, match_id, news_summary, news_url, highest_score_sent, sent, created_at, odds_taken, closing_odds, recommended_market
       FROM news_logs;
    
    5. Drop the old table:
       DROP TABLE news_logs;
    
    6. Rename the new table:
       ALTER TABLE news_logs_new RENAME TO news_logs;
    
    7. Recreate pre-existing indexes if any:
       CREATE INDEX IF NOT EXISTS idx_news_logs_match_id ON news_logs(match_id);
       CREATE INDEX IF NOT EXISTS idx_news_logs_sent ON news_logs(sent);
    
    Note: This is a destructive operation. Always backup before proceeding.
    """
    
    with get_db_context() as db:
        try:
            logger.warning("⚠️  Rolling back V8.3 migration...")
            logger.warning("⚠️  SQLite doesn't support DROP COLUMN. Manual intervention required.")
            logger.warning("⚠️  See docstring for detailed manual rollback steps.")
            logger.warning("⚠️  To rollback: 1) Backup data 2) Recreate table without new columns 3) Restore data")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ V8.3 Rollback failed: {e}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
