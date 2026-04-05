"""
Database Migration V13.0: Complete Schema Fix and Outcome Fields

This migration fixes critical database schema issues and adds V13.0 outcome fields.

Problems Fixed:
1. Table name mismatch: Renames 'news_log' to 'news_logs' to match SQLAlchemy model
2. Missing columns: Adds all columns defined in the NewsLog model
3. V13.0 outcome fields: Adds outcome and outcome_explanation columns
4. Missing indexes: Creates indexes for frequently queried fields

Background:
- The database was created with table name 'news_log' (singular)
- SQLAlchemy model defines __tablename__ = "news_logs" (plural)
- Previous migrations were not executed, leaving many columns missing
- This migration brings the database in sync with the SQLAlchemy model

Run: python -m src.database.migration_v13_complete_schema
"""

import logging

from sqlalchemy import inspect, text

from src.database.db import get_db_context

logger = logging.getLogger(__name__)


def migrate():
    """Apply V13.0 complete schema migration."""

    with get_db_context() as db:
        try:
            inspector = inspect(db.bind)

            # Step 1: Check if news_log table exists (old name)
            tables = inspector.get_table_names()
            has_news_log = "news_log" in tables
            has_news_logs = "news_logs" in tables

            logger.info(f"📊 Current tables: {tables}")
            logger.info(f"   - news_log exists: {has_news_log}")
            logger.info(f"   - news_logs exists: {has_news_logs}")

            # Step 2: Rename table if needed
            if has_news_log and not has_news_logs:
                logger.info("🔄 Renaming 'news_log' to 'news_logs'...")
                db.execute(text("ALTER TABLE news_log RENAME TO news_logs"))
                db.commit()
                logger.info("✅ Table renamed successfully")
                # Update inspector after rename
                inspector = inspect(db.bind)
            elif has_news_logs:
                logger.info("ℹ️ 'news_logs' table already exists - skipping rename")
            else:
                logger.error("❌ Neither 'news_log' nor 'news_logs' table exists!")
                return False

            # Step 3: Get current columns
            columns = [col["name"] for col in inspector.get_columns("news_logs")]
            logger.info(f"📊 Current columns in news_logs: {len(columns)}")

            # Step 4: Define all missing columns based on SQLAlchemy model
            missing_columns: list[tuple] = []

            # Content fields
            if "summary" not in columns:
                missing_columns.append(("summary", "TEXT"))
            if "score" not in columns:
                missing_columns.append(("score", "INTEGER DEFAULT 0"))

            # Primary identification (CRITICAL - foreign key to matches table)
            if "match_id" not in columns:
                missing_columns.append(("match_id", "String"))
            if "category" not in columns:
                missing_columns.append(("category", "TEXT"))
            if "affected_team" not in columns:
                missing_columns.append(("affected_team", "TEXT"))

            # Status tracking
            if "status" not in columns:
                missing_columns.append(("status", "TEXT"))
            if "verification_status" not in columns:
                missing_columns.append(("verification_status", "TEXT"))
            if "verification_reason" not in columns:
                missing_columns.append(("verification_reason", "TEXT"))

            # Combo bet fields
            if "combo_suggestion" not in columns:
                missing_columns.append(("combo_suggestion", "TEXT"))
            if "combo_reasoning" not in columns:
                missing_columns.append(("combo_reasoning", "TEXT"))
            if "recommended_market" not in columns:
                missing_columns.append(("recommended_market", "TEXT"))

            # Driver classification
            if "primary_driver" not in columns:
                missing_columns.append(("primary_driver", "TEXT"))

            # CLV Tracking (legacy)
            if "odds_taken" not in columns:
                missing_columns.append(("odds_taken", "REAL"))
            if "closing_odds" not in columns:
                missing_columns.append(("closing_odds", "REAL"))
            if "clv_percent" not in columns:
                missing_columns.append(("clv_percent", "REAL"))

            # V8.3: Proper historical odds tracking
            if "odds_at_alert" not in columns:
                missing_columns.append(("odds_at_alert", "REAL"))
            if "odds_at_kickoff" not in columns:
                missing_columns.append(("odds_at_kickoff", "REAL"))
            if "alert_sent_at" not in columns:
                missing_columns.append(("alert_sent_at", "DATETIME"))

            # V14.0: Line movement explanation via Tavily
            if "line_movement_explanation" not in columns:
                missing_columns.append(("line_movement_explanation", "TEXT"))

            # Combo outcome tracking
            if "combo_outcome" not in columns:
                missing_columns.append(("combo_outcome", "TEXT"))
            if "combo_explanation" not in columns:
                missing_columns.append(("combo_explanation", "TEXT"))
            if "expansion_type" not in columns:
                missing_columns.append(("expansion_type", "TEXT"))

            # V13.0: Primary bet outcome tracking (CRITICAL)
            if "outcome" not in columns:
                missing_columns.append(("outcome", "VARCHAR(10)"))
            if "outcome_explanation" not in columns:
                missing_columns.append(("outcome_explanation", "TEXT"))

            # Additional fields from migration.py
            if "source" not in columns:
                missing_columns.append(("source", "TEXT DEFAULT 'web'"))
            if "source_confidence" not in columns:
                missing_columns.append(("source_confidence", "REAL"))
            if "confidence_breakdown" not in columns:
                missing_columns.append(("confidence_breakdown", "TEXT"))
            if "final_verifier_result" not in columns:
                missing_columns.append(("final_verifier_result", "TEXT"))
            if "feedback_loop_used" not in columns:
                missing_columns.append(("feedback_loop_used", "BOOLEAN DEFAULT FALSE"))
            if "feedback_loop_iterations" not in columns:
                missing_columns.append(("feedback_loop_iterations", "INTEGER DEFAULT 0"))
            if "modification_plan" not in columns:
                missing_columns.append(("modification_plan", "TEXT"))
            if "modification_applied" not in columns:
                missing_columns.append(("modification_applied", "BOOLEAN DEFAULT FALSE"))
            if "original_score" not in columns:
                missing_columns.append(("original_score", "INTEGER"))
            if "original_market" not in columns:
                missing_columns.append(("original_market", "TEXT"))
            if "is_convergent" not in columns:
                missing_columns.append(("is_convergent", "BOOLEAN DEFAULT FALSE"))
            if "convergence_sources" not in columns:
                missing_columns.append(("convergence_sources", "TEXT"))
            if "confidence" not in columns:
                missing_columns.append(("confidence", "REAL"))

            # Step 5: Add missing columns
            if missing_columns:
                logger.info(f"🔄 Adding {len(missing_columns)} missing columns...")
                for col_name, col_type in missing_columns:
                    db.execute(text(f"ALTER TABLE news_logs ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"  ✓ Added {col_name} ({col_type})")
                db.commit()
                logger.info("✅ All missing columns added successfully!")
            else:
                logger.info("ℹ️ All columns already exist - no migration needed")

            # Step 6: Create indexes for frequently queried fields
            try:
                indexes = inspector.get_indexes("news_logs")
                existing_index_names = [idx["name"] for idx in indexes]

                # Index for odds_at_kickoff (used in CLV calculations)
                if "idx_news_logs_odds_at_kickoff" not in existing_index_names:
                    db.execute(
                        text(
                            "CREATE INDEX idx_news_logs_odds_at_kickoff ON news_logs(odds_at_kickoff)"
                        )
                    )
                    logger.info("  ✓ Created index on odds_at_kickoff")
                else:
                    logger.info("  ✓ Index on odds_at_kickoff already exists")

                # Index for alert_sent_at (used in time-based queries)
                if "idx_news_logs_alert_sent_at" not in existing_index_names:
                    db.execute(
                        text("CREATE INDEX idx_news_logs_alert_sent_at ON news_logs(alert_sent_at)")
                    )
                    logger.info("  ✓ Created index on alert_sent_at")
                else:
                    logger.info("  ✓ Index on alert_sent_at already exists")

                # Index for match_id (foreign key)
                if "idx_news_logs_match_id" not in existing_index_names:
                    db.execute(text("CREATE INDEX idx_news_logs_match_id ON news_logs(match_id)"))
                    logger.info("  ✓ Created index on match_id")
                else:
                    logger.info("  ✓ Index on match_id already exists")

                # Index for sent (status tracking)
                if "idx_news_logs_sent" not in existing_index_names:
                    db.execute(text("CREATE INDEX idx_news_logs_sent ON news_logs(sent)"))
                    logger.info("  ✓ Created index on sent")
                else:
                    logger.info("  ✓ Index on sent already exists")

                db.commit()
                logger.info("✅ All indexes created successfully!")

            except Exception as e:
                logger.warning(f"⚠️  Could not create indexes: {e}")
                logger.warning(
                    "⚠️  Migration completed but indexes may be missing. Performance may be affected."
                )
                # Don't fail the migration if indexes fail

            # Step 7: Verify migration
            logger.info("🔍 Verifying migration...")
            inspector = inspect(db.bind)
            columns_after = [col["name"] for col in inspector.get_columns("news_logs")]
            logger.info(f"📊 Columns after migration: {len(columns_after)}")

            # Check critical V13.0 columns
            critical_columns = ["outcome", "outcome_explanation"]
            missing_critical = [col for col in critical_columns if col not in columns_after]

            if missing_critical:
                logger.error(f"❌ Critical columns missing: {missing_critical}")
                return False

            logger.info("✅ Migration completed successfully!")
            logger.info("✅ All critical V13.0 columns are present")
            logger.info("ℹ️  Note: Existing records will have NULL values for new columns.")
            logger.info("ℹ️  New alerts will populate these columns going forward.")

            return True

        except Exception as e:
            logger.error(f"❌ V13.0 Migration failed: {e}", exc_info=True)
            try:
                db.rollback()
            except Exception as rollback_error:
                logger.error(f"❌ Rollback failed: {rollback_error}")
            return False


def rollback():
    """
    Rollback V13.0 migration.

    IMPORTANT: SQLite does not support DROP COLUMN directly. Manual rollback steps are required.

    Manual Rollback Procedure:
    ---------------------------
    1. Backup your database:
       cp data/earlybird.db data/earlybird.db.backup

    2. Drop the V13.0 indexes (if they exist):
       DROP INDEX IF EXISTS idx_news_logs_odds_at_kickoff;
       DROP INDEX IF EXISTS idx_news_logs_alert_sent_at;
       DROP INDEX IF EXISTS idx_news_logs_match_id;
       DROP INDEX IF EXISTS idx_news_logs_sent;

    3. Rename table back to news_log:
       ALTER TABLE news_logs RENAME TO news_log;

    Note: This is a destructive operation. Always backup before proceeding.
    """

    with get_db_context() as db:
        try:
            logger.warning("⚠️  Rolling back V13.0 migration...")
            logger.warning("⚠️  SQLite doesn't support DROP COLUMN. Manual intervention required.")
            logger.warning("⚠️  See docstring for detailed manual rollback steps.")
            logger.warning(
                "⚠️  To rollback: 1) Backup data 2) Drop indexes 3) Rename table back to news_log"
            )

            return False

        except Exception as e:
            logger.error(f"❌ V13.0 Rollback failed: {e}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
