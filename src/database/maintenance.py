"""
Database Maintenance Module for EarlyBird V3.3
Handles automated cleanup of old data to prevent DB bloat.

Features:
- Prunes matches older than X days
- Cascades to news_logs (respects FK constraints)
- Safe transaction handling with rollback
"""

import logging
from datetime import datetime, timedelta, timezone

from src.database.models import Match, NewsLog, SessionLocal

logger = logging.getLogger(__name__)

# Default retention period
DEFAULT_RETENTION_DAYS = 30


def prune_old_data(days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """
    Remove old matches and associated news_logs from the database.

    Deletion order (FK safe):
    1. Delete NewsLog entries for old matches (children first)
    2. Delete old Match entries (parents second)

    Args:
        days: Number of days to retain data (default: 30)

    Returns:
        Dict with counts: {'matches_deleted': X, 'logs_deleted': Y}
    """
    logger.info(f"🧹 Avvio pulizia database (retention: {days} giorni)...")

    stats = {"matches_deleted": 0, "logs_deleted": 0, "error": None}

    db = SessionLocal()

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        logger.info(f"   📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')} UTC")

        # Step 1: Find old match IDs
        old_match_ids = db.query(Match.id).filter(Match.start_time < cutoff_date).all()
        old_match_ids = [m[0] for m in old_match_ids]

        if not old_match_ids:
            logger.info("   ✅ Nessun dato vecchio da eliminare.")
            return stats

        logger.info(f"   🔍 Trovati {len(old_match_ids)} match da eliminare...")

        # Step 2: Delete NewsLog entries (children first - FK constraint)
        logs_deleted = (
            db.query(NewsLog)
            .filter(NewsLog.match_id.in_(old_match_ids))
            .delete(synchronize_session=False)
        )

        stats["logs_deleted"] = logs_deleted
        logger.info(f"   🗑️ Eliminati {logs_deleted} news_logs...")

        # Step 3: Delete Match entries (parents second)
        matches_deleted = (
            db.query(Match).filter(Match.id.in_(old_match_ids)).delete(synchronize_session=False)
        )

        stats["matches_deleted"] = matches_deleted
        logger.info(f"   🗑️ Eliminati {matches_deleted} match...")

        # Commit transaction
        db.commit()

        logger.info(
            f"🧹 Database pulito: rimossi {matches_deleted} match e {logs_deleted} log vecchi."
        )

    except Exception as e:
        logger.error(f"❌ Errore durante pulizia database: {e}")
        try:
            db.rollback()
        except Exception as rollback_error:
            logger.error(f"❌ Rollback failed: {rollback_error}")
        stats["error"] = str(e)

    finally:
        db.close()

    return stats


def get_db_stats() -> dict:
    """
    Get current database statistics for monitoring.

    Returns:
        Dict with counts and oldest record dates
    """
    db = SessionLocal()

    try:
        total_matches = db.query(Match).count()
        total_logs = db.query(NewsLog).count()

        oldest_match = db.query(Match).order_by(Match.start_time.asc()).first()
        oldest_date = oldest_match.start_time if oldest_match else None

        return {
            "total_matches": total_matches,
            "total_logs": total_logs,
            "oldest_match_date": oldest_date,
        }

    except Exception as e:
        logger.error(f"Errore lettura statistiche DB: {e}")
        return {"error": str(e)}

    finally:
        db.close()


def emergency_cleanup() -> dict:
    """
    Emergency cleanup function to free disk space when disk usage is critical.

    Actions:
    1. Find any .log file > 20MB and truncate it
    2. Clear temp/ folder
    3. Log: "🚨 Emergency cleanup triggered due to high disk usage."

    Returns:
        Dict with cleanup stats: {'logs_truncated': X, 'temp_files_deleted': Y}
    """
    logger.info("🚨 Emergency cleanup triggered due to high disk usage.")

    stats = {"logs_truncated": 0, "temp_files_deleted": 0, "error": None}

    # 1. Find and truncate large log files (>20MB)
    LOG_SIZE_THRESHOLD_MB = 20
    LOG_SIZE_THRESHOLD_BYTES = LOG_SIZE_THRESHOLD_MB * 1024 * 1024

    try:
        from pathlib import Path

        # Search for .log files in current directory and subdirectories
        for log_file in Path(".").rglob("*.log"):
            try:
                file_size = log_file.stat().st_size
                if file_size > LOG_SIZE_THRESHOLD_BYTES:
                    # Truncate the log file (keep last 100KB)
                    keep_bytes = 100 * 1024  # Keep last 100KB
                    with open(log_file, "rb+") as f:
                        f.seek(0, 2)  # Seek to end
                        if f.tell() > keep_bytes:
                            f.seek(f.tell() - keep_bytes)  # Seek back
                            remaining = f.read()  # Read last part
                            f.seek(0)  # Seek to beginning
                            f.write(remaining)  # Write back
                            f.truncate()  # Truncate at current position

                    stats["logs_truncated"] += 1
                    logger.info(
                        f"   🗑️ Truncated {log_file.name} ({file_size / 1024 / 1024:.1f}MB -> ~100KB)"
                    )
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to truncate {log_file.name}: {e}")

    except Exception as e:
        logger.error(f"❌ Error during log cleanup: {e}")
        stats["error"] = str(e)

    # 2. Clear temp/ folder
    try:
        temp_dir = Path("temp")
        if temp_dir.exists() and temp_dir.is_dir():
            deleted_count = 0
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        import shutil

                        shutil.rmtree(item)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Failed to delete {item.name}: {e}")

            stats["temp_files_deleted"] = deleted_count
            if deleted_count > 0:
                logger.info(f"   🗑️ Cleared temp/ folder: {deleted_count} items deleted")
            else:
                logger.info("   ℹ️ temp/ folder already empty")
        else:
            logger.info("   ℹ️ temp/ folder does not exist")

    except Exception as e:
        logger.error(f"❌ Error during temp cleanup: {e}")
        if not stats["error"]:
            stats["error"] = str(e)

    logger.info(
        f"✅ Emergency cleanup completed: {stats['logs_truncated']} logs truncated, {stats['temp_files_deleted']} temp files deleted"
    )
    return stats


def cleanup_stale_radar_triggers(timeout_minutes: int = 10, send_alert: bool = True) -> dict:
    """
    Cleanup stale radar triggers that have been in PENDING_RADAR_TRIGGER state for too long.

    This prevents triggers from getting stuck if the Main Pipeline crashes during processing.

    Args:
        timeout_minutes: Maximum age in minutes before a trigger is considered stale (default: 10)
        send_alert: Whether to send Telegram alert when stale triggers are found (default: True)

    Returns:
        Dict with cleanup stats: {'triggers_cleaned': X, 'triggers_failed': Y}
    """
    logger.info(f"🧹 Checking for stale radar triggers (timeout: {timeout_minutes} minutes)...")

    stats = {"triggers_cleaned": 0, "triggers_failed": 0, "error": None}

    db = SessionLocal()

    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        logger.info(f"   📅 Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M')} UTC")

        # Find stale triggers
        stale_triggers = (
            db.query(NewsLog)
            .filter(NewsLog.status == "PENDING_RADAR_TRIGGER")
            .filter(NewsLog.created_at < cutoff_time)
            .all()
        )

        if not stale_triggers:
            logger.info("   ✅ No stale radar triggers found.")
            return stats

        logger.info(f"   🔍 Found {len(stale_triggers)} stale trigger(s)...")

        # Update each stale trigger
        for trigger in stale_triggers:
            try:
                # Get match for logging
                match = db.query(Match).filter(Match.id == trigger.match_id).first()
                match_info = (
                    f"{match.home_team} vs {match.away_team}"
                    if match
                    else f"Match ID {trigger.match_id}"
                )

                # Update trigger status to FAILED
                trigger.status = "FAILED"
                trigger.summary = (
                    f"{trigger.summary} [STALE: Not processed within {timeout_minutes} minutes]"
                )

                logger.warning(
                    f"   ⚠️ Stale radar trigger marked as FAILED: {match_info} "
                    f"(age: {(datetime.now(timezone.utc) - trigger.created_at).total_seconds() / 60:.1f} minutes)"
                )

                stats["triggers_cleaned"] += 1

            except Exception as e:
                logger.error(f"   ❌ Failed to update stale trigger {trigger.id}: {e}")
                stats["triggers_failed"] += 1

        # Commit transaction
        db.commit()

        logger.info(
            f"🧹 Stale radar triggers cleaned: {stats['triggers_cleaned']} marked as FAILED, "
            f"{stats['triggers_failed']} errors"
        )

        # Send alert if stale triggers were found
        if send_alert and stats["triggers_cleaned"] > 0:
            try:
                from src.alerting.notifier import send_status_message

                alert_message = (
                    f"🚨 <b>STALE RADAR TRIGGERS DETECTED</b>\n\n"
                    f"• Cleaned: {stats['triggers_cleaned']} stale trigger(s)\n"
                    f"• Timeout: {timeout_minutes} minutes\n"
                    f"• Failed updates: {stats['triggers_failed']}\n\n"
                    f"⚠️ This may indicate Main Pipeline crashes or performance issues."
                )
                send_status_message(alert_message)
                logger.info("   📢 Alert sent to Telegram about stale radar triggers")
            except ImportError:
                logger.warning("   ⚠️ Could not import send_status_message for alerting")
            except Exception as e:
                logger.error(f"   ❌ Failed to send alert: {e}")

    except Exception as e:
        logger.error(f"❌ Error during stale radar trigger cleanup: {e}")
        try:
            db.rollback()
        except Exception as rollback_error:
            logger.error(f"❌ Rollback failed: {rollback_error}")
        stats["error"] = str(e)

    finally:
        db.close()

    return stats


if __name__ == "__main__":
    # Test maintenance directly
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 50)
    print("EarlyBird Database Maintenance")
    print("=" * 50)

    # Show current stats
    stats = get_db_stats()
    print("\nStatistiche attuali:")
    print(f"  - Match totali: {stats.get('total_matches', 'N/A')}")
    print(f"  - Log totali: {stats.get('total_logs', 'N/A')}")
    print(f"  - Match più vecchio: {stats.get('oldest_match_date', 'N/A')}")

    # Run pruning (dry run - comment out for real execution)
    # result = prune_old_data(days=30)
    # print(f"\nRisultato pulizia: {result}")
