"""
Database Migration V7.3 - Add last_alert_time field

Adds last_alert_time column to Match table for temporal deduplication reset.

This migration is safe to run multiple times (idempotent).
"""
import logging
from sqlalchemy import text
from src.database.models import engine

logger = logging.getLogger(__name__)


def migrate_v73():
    """
    Add last_alert_time column to matches table.
    
    V7.3 FIX: Enables temporal reset of highest_score_sent after 24h.
    """
    logger.info("🔄 Running V7.3 migration: Adding last_alert_time column...")
    
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('matches') WHERE name='last_alert_time'"
        ))
        exists = result.scalar() > 0
        
        if exists:
            logger.info("✅ Column last_alert_time already exists, skipping migration")
            return
        
        # Add column
        try:
            conn.execute(text(
                "ALTER TABLE matches ADD COLUMN last_alert_time DATETIME"
            ))
            conn.commit()
            logger.info("✅ V7.3 migration complete: last_alert_time column added")
        except Exception as e:
            logger.error(f"❌ V7.3 migration failed: {e}")
            raise


if __name__ == "__main__":
    # Run migration standalone
    logging.basicConfig(level=logging.INFO)
    migrate_v73()
