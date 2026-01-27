"""
EarlyBird Database Migration System

Auto-migrates database schema to add new columns without data loss.
Called at startup to ensure DB is always up-to-date.
"""
import logging
import sqlite3
import os

logger = logging.getLogger(__name__)

# Database path
DB_PATH = "data/earlybird.db"


VALID_TABLE_NAMES = {'matches', 'news_logs', 'team_aliases'}

def get_table_columns(cursor, table_name: str) -> set:
    """Get existing column names for a table.
    
    Args:
        cursor: SQLite cursor
        table_name: Table name (must be in VALID_TABLE_NAMES whitelist)
        
    Returns:
        Set of column names
    """
    # Validate table name against whitelist to prevent SQL injection
    if table_name not in VALID_TABLE_NAMES:
        logger.warning(f"Invalid table name requested: {table_name}")
        return set()
    
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    return columns


def check_and_migrate():
    """
    Check database schema and apply migrations if needed.
    
    This function:
    1. Inspects existing table columns
    2. Adds missing columns via ALTER TABLE
    3. Logs all changes
    
    Safe to run multiple times - only adds missing columns.
    """
    if not os.path.exists(DB_PATH):
        logger.info("📦 Database not found - will be created on first run")
        return
    
    logger.info("🔍 Checking database schema for migrations...")
    
    try:
        # Use timeout to wait for lock release (matches SQLAlchemy config)
        conn = sqlite3.connect(DB_PATH, timeout=60)
        cursor = conn.cursor()
        # Set busy_timeout PRAGMA for additional lock handling
        cursor.execute("PRAGMA busy_timeout=60000")
        
        migrations_applied = 0
        
        # ============================================
        # MIGRATION: news_logs table
        # ============================================
        news_logs_columns = get_table_columns(cursor, 'news_logs')
        
        # Add combo_suggestion column
        if 'combo_suggestion' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.combo_suggestion")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN combo_suggestion TEXT")
            migrations_applied += 1
        
        # Add combo_reasoning column
        if 'combo_reasoning' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.combo_reasoning")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN combo_reasoning TEXT")
            migrations_applied += 1
        
        # Add recommended_market column
        if 'recommended_market' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.recommended_market")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN recommended_market TEXT")
            migrations_applied += 1
        
        # V3.0: Add primary_driver for quantitative optimization
        if 'primary_driver' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.primary_driver")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN primary_driver TEXT")
            migrations_applied += 1
        
        # V3.0: Add closing_odds for CLV analysis (future)
        if 'closing_odds' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.closing_odds")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN closing_odds REAL")
            migrations_applied += 1
        
        # V3.5: Add source for intelligence tracking (web, telegram_ocr, telegram_channel)
        if 'source' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.source")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN source TEXT DEFAULT 'web'")
            migrations_applied += 1
        
        # V4.2: CLV Tracking - odds_taken (odds when alert was sent)
        if 'odds_taken' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.odds_taken")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN odds_taken REAL")
            migrations_applied += 1
        
        # V4.2: CLV Tracking - clv_percent (calculated after match starts)
        if 'clv_percent' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.clv_percent")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN clv_percent REAL")
            migrations_applied += 1
        
        # V7.4: Combo Expansion Tracking - Auto-Learning System
        if 'combo_outcome' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.combo_outcome")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN combo_outcome TEXT")
            migrations_applied += 1
        
        if 'combo_explanation' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.combo_explanation")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN combo_explanation TEXT")
            migrations_applied += 1
        
        if 'expansion_type' not in news_logs_columns:
            logger.info("   📝 Adding column: news_logs.expansion_type")
            cursor.execute("ALTER TABLE news_logs ADD COLUMN expansion_type TEXT")
            migrations_applied += 1
        
        # ============================================
        # MIGRATION: matches table
        # ============================================
        matches_columns = get_table_columns(cursor, 'matches')
        
        # V2.6: Add highest_score_sent for score-delta deduplication
        if 'highest_score_sent' not in matches_columns:
            logger.info("   📝 Adding column: matches.highest_score_sent")
            cursor.execute("ALTER TABLE matches ADD COLUMN highest_score_sent REAL DEFAULT 0.0")
            migrations_applied += 1
        
        # V3.2: Add last_deep_dive_time for INVESTIGATOR MODE cooldown
        if 'last_deep_dive_time' not in matches_columns:
            logger.info("   📝 Adding column: matches.last_deep_dive_time")
            cursor.execute("ALTER TABLE matches ADD COLUMN last_deep_dive_time DATETIME")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Corners
        if 'home_corners' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_corners")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_corners INTEGER")
            migrations_applied += 1
        
        if 'away_corners' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_corners")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_corners INTEGER")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Yellow Cards (separate)
        if 'home_yellow_cards' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_yellow_cards")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_yellow_cards INTEGER")
            migrations_applied += 1
        
        if 'away_yellow_cards' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_yellow_cards")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_yellow_cards INTEGER")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Red Cards (separate)
        if 'home_red_cards' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_red_cards")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_red_cards INTEGER")
            migrations_applied += 1
        
        if 'away_red_cards' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_red_cards")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_red_cards INTEGER")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Expected Goals
        if 'home_xg' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_xg")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_xg REAL")
            migrations_applied += 1
        
        if 'away_xg' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_xg")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_xg REAL")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Possession
        if 'home_possession' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_possession")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_possession REAL")
            migrations_applied += 1
        
        if 'away_possession' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_possession")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_possession REAL")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Shots on Target
        if 'home_shots_on_target' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_shots_on_target")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_shots_on_target INTEGER")
            migrations_applied += 1
        
        if 'away_shots_on_target' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_shots_on_target")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_shots_on_target INTEGER")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Big Chances
        if 'home_big_chances' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_big_chances")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_big_chances INTEGER")
            migrations_applied += 1
        
        if 'away_big_chances' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_big_chances")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_big_chances INTEGER")
            migrations_applied += 1
        
        # V3.7: Stats Warehousing - Fouls
        if 'home_fouls' not in matches_columns:
            logger.info("   📝 Adding column: matches.home_fouls")
            cursor.execute("ALTER TABLE matches ADD COLUMN home_fouls INTEGER")
            migrations_applied += 1
        
        if 'away_fouls' not in matches_columns:
            logger.info("   📝 Adding column: matches.away_fouls")
            cursor.execute("ALTER TABLE matches ADD COLUMN away_fouls INTEGER")
            migrations_applied += 1
        
        # V7.3: Temporal Deduplication - last_alert_time
        if 'last_alert_time' not in matches_columns:
            logger.info("   📝 Adding column: matches.last_alert_time (V7.3 - Temporal Reset)")
            cursor.execute("ALTER TABLE matches ADD COLUMN last_alert_time DATETIME")
            migrations_applied += 1
        
        # ============================================
        # MIGRATION: Performance Indexes
        # ============================================
        # V3.3: Add composite index for main query optimization (start_time + league)
        # Check if index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_match_time_league'")
        if not cursor.fetchone():
            logger.info("   📝 Creating index: idx_match_time_league (start_time, league)")
            cursor.execute("CREATE INDEX idx_match_time_league ON matches (start_time, league)")
            migrations_applied += 1
        
        # Commit all changes
        conn.commit()
        conn.close()
        
        if migrations_applied > 0:
            logger.info(f"✅ Database schema updated: {migrations_applied} migration(s) applied")
        else:
            logger.info("✅ Database schema is up-to-date")
            
    except sqlite3.Error as e:
        logger.error(f"❌ Database migration failed: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected migration error: {e}")


def get_schema_version() -> dict:
    """
    Get current schema information for debugging.
    
    Returns:
        Dict with table names and their columns
    """
    if not os.path.exists(DB_PATH):
        return {"error": "Database not found"}
    
    try:
        # Use timeout to wait for lock release (matches SQLAlchemy config)
        conn = sqlite3.connect(DB_PATH, timeout=60)
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout=60000")
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema = {}
        for table in tables:
            schema[table] = list(get_table_columns(cursor, table))
        
        conn.close()
        return schema
        
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # Run migration directly for testing
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("=" * 50)
    print("EarlyBird Database Migration Tool")
    print("=" * 50)
    
    # Show current schema
    print("\n📊 Current Schema:")
    schema = get_schema_version()
    for table, columns in schema.items():
        print(f"   {table}: {columns}")
    
    # Run migration
    print("\n🔄 Running migrations...")
    check_and_migrate()
    
    # Show updated schema
    print("\n📊 Updated Schema:")
    schema = get_schema_version()
    for table, columns in schema.items():
        print(f"   {table}: {columns}")
