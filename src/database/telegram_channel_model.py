"""
EarlyBird Telegram Channel Tracking Model

Persists channel metrics for Trust Score calculation.
Tracks historical performance of each Telegram channel.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text

from src.database.models import Base, engine, get_db_session

logger = logging.getLogger(__name__)


class TelegramChannel(Base):
    """
    Tracks metrics for each monitored Telegram channel.
    Used by telegram_trust_score.py for validation.
    """

    __tablename__ = "telegram_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, unique=True, nullable=False, index=True)
    channel_name = Column(String, nullable=False)

    # Message counts
    total_messages = Column(Integer, default=0)
    messages_with_odds_impact = Column(Integer, default=0)

    # Timestamp lag stats
    avg_timestamp_lag_minutes = Column(Float, default=0.0)
    insider_hits = Column(Integer, default=0)  # Messages that anticipated market
    late_messages = Column(Integer, default=0)  # Messages after market moved

    # Edit/Delete tracking
    total_edits = Column(Integer, default=0)
    total_deletes = Column(Integer, default=0)

    # Accuracy tracking
    predictions_made = Column(Integer, default=0)
    predictions_correct = Column(Integer, default=0)

    # Red flags
    red_flags_count = Column(Integer, default=0)
    red_flag_types = Column(Text, nullable=True)  # JSON list of flag types

    # Echo chamber
    echo_messages = Column(Integer, default=0)

    # Computed scores (updated periodically)
    trust_score = Column(Float, default=0.5)
    trust_level = Column(
        String, default="NEUTRAL"
    )  # VERIFIED, TRUSTED, NEUTRAL, SUSPICIOUS, BLACKLISTED

    # Status
    is_active = Column(Boolean, default=True)
    is_blacklisted = Column(Boolean, default=False)
    blacklist_reason = Column(String, nullable=True)

    # Timestamps
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_message_time = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Index for trust score queries
    __table_args__ = (Index("idx_channel_trust", "trust_score", "is_active"),)


class TelegramMessageLog(Base):
    """
    Logs individual messages for audit and echo detection.
    Keeps last 7 days of messages for analysis.
    """

    __tablename__ = "telegram_message_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=True)  # Telegram message ID

    # Content (for echo detection)
    text_hash = Column(String, nullable=True, index=True)  # MD5 hash of normalized text
    text_preview = Column(String, nullable=True)  # First 200 chars

    # Timestamps
    message_time = Column(DateTime, nullable=False)
    ingested_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Validation results
    was_edited = Column(Boolean, default=False)
    was_deleted = Column(Boolean, default=False)
    is_echo = Column(Boolean, default=False)
    echo_source_channel = Column(String, nullable=True)

    # Odds correlation
    match_id = Column(String, nullable=True)
    timestamp_lag_minutes = Column(Float, nullable=True)
    was_insider_hit = Column(Boolean, default=False)

    # Trust validation
    trust_multiplier = Column(Float, nullable=True)
    validation_reason = Column(String, nullable=True)
    red_flags_detected = Column(Text, nullable=True)  # JSON list

    # Prediction tracking (V1.1 - Post-match feedback loop)
    prediction_type = Column(
        String, nullable=True
    )  # HOME_WIN, AWAY_WIN, DRAW, OVER_2.5, UNDER_2.5, BTTS_YES, BTTS_NO, etc.
    prediction_team = Column(String, nullable=True)  # Team name if prediction is team-specific
    prediction_verified = Column(
        Boolean, default=False
    )  # Has this prediction been checked against match result?
    prediction_correct = Column(
        Boolean, nullable=True
    )  # Was the prediction correct? (None = not verified yet)

    # Index for cleanup queries
    __table_args__ = (
        Index("idx_msg_channel_time", "channel_id", "message_time"),
        Index("idx_msg_match_prediction", "match_id", "prediction_type"),
    )


# ============================================
# DATABASE OPERATIONS
# ============================================

_telegram_db_initialized = False


def init_telegram_tracking_db(max_retries: int = 5, retry_delay: float = 2.0):
    """Create telegram tracking tables if they don't exist.

    Uses a flag to avoid repeated initialization calls which can cause
    'database is locked' errors when called in a loop.

    Args:
        max_retries: Number of retries on database lock
        retry_delay: Base delay between retries (exponential backoff)
    """
    global _telegram_db_initialized

    if _telegram_db_initialized:
        return  # Already initialized this session

    import time

    last_error = None

    for attempt in range(max_retries):
        try:
            TelegramChannel.__table__.create(engine, checkfirst=True)
            TelegramMessageLog.__table__.create(engine, checkfirst=True)
            _telegram_db_initialized = True
            logger.info("✅ Telegram tracking DB initialized")
            return
        except Exception as e:
            error_str = str(e).lower()
            if "database is locked" in error_str or "locked" in error_str:
                last_error = e
                wait_time = retry_delay * (2**attempt)
                logger.warning(
                    f"⚠️ DB locked during init (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Failed to initialize telegram tracking DB: {e}")
                return

    # All retries exhausted
    if last_error:
        logger.error(
            f"Failed to initialize telegram tracking DB after {max_retries} retries: {last_error}"
        )


def get_or_create_channel(channel_id: str, channel_name: str) -> dict:
    """
    Get existing channel or create new one.

    Args:
        channel_id: Telegram channel ID
        channel_name: Channel username

    Returns:
        Dict with channel data (detached from session)
    """
    try:
        with get_db_session() as db:
            channel = (
                db.query(TelegramChannel).filter(TelegramChannel.channel_id == channel_id).first()
            )

            if not channel:
                channel = TelegramChannel(
                    channel_id=channel_id,
                    channel_name=channel_name,
                    first_seen=datetime.now(timezone.utc),
                )
                db.add(channel)
                db.flush()  # Get ID before commit
                logger.info(f"📡 New Telegram channel tracked: @{channel_name}")

            # Return a detached dict copy of the data
            return {
                "id": channel.id,
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "trust_score": channel.trust_score,
                "trust_level": channel.trust_level,
                "is_blacklisted": channel.is_blacklisted,
                "total_messages": channel.total_messages,
                "insider_hits": channel.insider_hits,
            }
    except Exception as e:
        logger.error(f"Error in get_or_create_channel: {e}")
        # Return a minimal dict on error
        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "trust_score": 0.5,
            "trust_level": "NEUTRAL",
            "is_blacklisted": False,
            "total_messages": 0,
            "insider_hits": 0,
        }


def update_channel_metrics(
    channel_id: str,
    is_insider_hit: bool = False,
    is_late: bool = False,
    is_echo: bool = False,
    is_edit: bool = False,
    is_delete: bool = False,
    red_flags: list = None,
    timestamp_lag: float = None,
):
    """
    Update channel metrics after processing a message.

    Args:
        channel_id: Channel to update
        is_insider_hit: Message anticipated odds movement
        is_late: Message was late (>30min after drop)
        is_echo: Message was copy of another channel
        is_edit: Message was edited
        is_delete: Message was deleted
        red_flags: List of detected red flags
        timestamp_lag: Lag in minutes (negative = before drop)
    """
    try:
        with get_db_session() as db:
            channel = (
                db.query(TelegramChannel).filter(TelegramChannel.channel_id == channel_id).first()
            )

            if not channel:
                logger.warning(f"Channel not found for update: {channel_id}")
                return

            # Update counts
            channel.total_messages += 1

            if is_insider_hit:
                channel.insider_hits += 1
                channel.messages_with_odds_impact += 1
            elif is_late:
                channel.late_messages += 1
                channel.messages_with_odds_impact += 1

            if is_echo:
                channel.echo_messages += 1

            if is_edit:
                channel.total_edits += 1

            if is_delete:
                channel.total_deletes += 1

            if red_flags:
                channel.red_flags_count += len(red_flags)
                # Append to existing flags
                import json

                existing = json.loads(channel.red_flag_types) if channel.red_flag_types else []
                existing.extend(red_flags)
                channel.red_flag_types = json.dumps(existing[-50:])  # Keep last 50

            # Update average timestamp lag (rolling average)
            if timestamp_lag is not None:
                n = channel.messages_with_odds_impact
                if n > 0:
                    old_avg = channel.avg_timestamp_lag_minutes or 0.0
                    channel.avg_timestamp_lag_minutes = ((old_avg * (n - 1)) + timestamp_lag) / n
                else:
                    channel.avg_timestamp_lag_minutes = timestamp_lag

            # Recalculate trust score
            from src.analysis.telegram_trust_score import ChannelMetrics, calculate_trust_score

            metrics = ChannelMetrics(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                total_messages=channel.total_messages,
                messages_with_odds_impact=channel.messages_with_odds_impact,
                avg_timestamp_lag_minutes=channel.avg_timestamp_lag_minutes,
                insider_hits=channel.insider_hits,
                late_messages=channel.late_messages,
                total_edits=channel.total_edits,
                total_deletes=channel.total_deletes,
                predictions_made=channel.predictions_made,
                predictions_correct=channel.predictions_correct,
                red_flags_count=channel.red_flags_count,
                echo_messages=channel.echo_messages,
            )

            trust_score, trust_level = calculate_trust_score(metrics)
            channel.trust_score = trust_score
            channel.trust_level = trust_level.value

            # Auto-blacklist if trust too low
            if trust_level.value == "BLACKLISTED":
                channel.is_blacklisted = True
                channel.blacklist_reason = "Auto-blacklisted: Trust score below threshold"
                logger.warning(f"🚫 Channel auto-blacklisted: @{channel.channel_name}")

            channel.last_message_time = datetime.now(timezone.utc)
            channel.last_updated = datetime.now(timezone.utc)
            # commit is automatic in context manager

    except Exception as e:
        logger.error(f"Error updating channel metrics: {e}")


def log_telegram_message(
    channel_id: str,
    message_id: str,
    text_hash: str,
    text_preview: str,
    message_time: datetime,
    match_id: str = None,
    timestamp_lag: float = None,
    was_insider_hit: bool = False,
    is_echo: bool = False,
    echo_source: str = None,
    trust_multiplier: float = None,
    validation_reason: str = None,
    red_flags: list = None,
    # V1.1: Prediction tracking parameters
    prediction_type: str = None,
    prediction_team: str = None,
    # V1.2: Edit/Delete tracking
    was_edited: bool = False,
):
    """
    Log a processed Telegram message for audit trail.

    Args:
        channel_id: Source channel
        message_id: Telegram message ID
        text_hash: Hash of normalized text
        text_preview: First 200 chars
        message_time: When message was posted
        match_id: Related match (if any)
        timestamp_lag: Lag vs odds drop
        was_insider_hit: True if anticipated market
        is_echo: True if copy of another channel
        echo_source: Original channel if echo
        trust_multiplier: Calculated trust multiplier
        validation_reason: Why this multiplier
        red_flags: Detected red flags
        prediction_type: Type of prediction (HOME_WIN, AWAY_WIN, DRAW, OVER_2.5, etc.)
        prediction_team: Team name if prediction is team-specific
        was_edited: True if message was edited after posting (from Telethon msg.edit_date)
    """
    try:
        import json

        with get_db_session() as db:
            log = TelegramMessageLog(
                channel_id=channel_id,
                message_id=message_id,
                text_hash=text_hash,
                text_preview=text_preview[:200] if text_preview else None,
                message_time=message_time,
                match_id=match_id,
                timestamp_lag_minutes=timestamp_lag,
                was_insider_hit=was_insider_hit,
                was_edited=was_edited,  # V1.2: Track edited messages
                is_echo=is_echo,
                echo_source_channel=echo_source,
                trust_multiplier=trust_multiplier,
                validation_reason=validation_reason,
                red_flags_detected=json.dumps(red_flags) if red_flags else None,
                # V1.1: Prediction tracking
                prediction_type=prediction_type,
                prediction_team=prediction_team,
                prediction_verified=False,
                prediction_correct=None,
            )

            db.add(log)
            # commit is automatic in context manager

    except Exception as e:
        logger.error(f"Error logging telegram message: {e}")


def get_channel_metrics(channel_id: str) -> dict:
    """
    Get current metrics for a channel.

    Args:
        channel_id: Channel to query

    Returns:
        Dict with channel metrics or None
    """
    try:
        with get_db_session() as db:
            channel = (
                db.query(TelegramChannel).filter(TelegramChannel.channel_id == channel_id).first()
            )

            if not channel:
                return None

            return {
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "total_messages": channel.total_messages,
                "messages_with_odds_impact": channel.messages_with_odds_impact,
                "insider_hits": channel.insider_hits,
                "late_messages": channel.late_messages,
                "total_edits": channel.total_edits,
                "total_deletes": channel.total_deletes,
                "predictions_made": channel.predictions_made,
                "predictions_correct": channel.predictions_correct,
                "echo_messages": channel.echo_messages,
                "red_flags_count": channel.red_flags_count,
                "red_flag_types": channel.red_flag_types,  # JSON string, will be deserialized
                "trust_score": channel.trust_score,
                "trust_level": channel.trust_level,
                "is_blacklisted": channel.is_blacklisted,
                "avg_timestamp_lag": channel.avg_timestamp_lag_minutes,
                "first_seen": channel.first_seen,
                "last_updated": channel.last_updated,
            }
    except Exception as e:
        logger.error(f"Error getting channel metrics: {e}")
        return None


def cleanup_old_message_logs(days_to_keep: int = 7) -> int:
    """
    Clean up old message logs to prevent DB bloat.

    Args:
        days_to_keep: Days of history to retain

    Returns:
        Number of records deleted
    """
    try:
        with get_db_session() as db:
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            cutoff_naive = cutoff.replace(tzinfo=None)

            deleted = (
                db.query(TelegramMessageLog)
                .filter(TelegramMessageLog.message_time < cutoff_naive)
                .delete()
            )

            # commit is automatic in context manager
            logger.info(f"🧹 Cleaned up {deleted} old telegram message logs")
            return deleted
    except Exception as e:
        logger.error(f"Error cleaning up message logs: {e}")
        return 0


def get_trusted_channels(min_trust_score: float = 0.6) -> list:
    """
    Get list of trusted channels for priority processing.

    Args:
        min_trust_score: Minimum trust score threshold

    Returns:
        List of channel names
    """
    try:
        with get_db_session() as db:
            channels = (
                db.query(TelegramChannel)
                .filter(
                    TelegramChannel.is_active == True,
                    TelegramChannel.is_blacklisted == False,
                    TelegramChannel.trust_score >= min_trust_score,
                )
                .order_by(TelegramChannel.trust_score.desc())
                .all()
            )

            return [c.channel_name for c in channels]
    except Exception as e:
        logger.error(f"Error getting trusted channels: {e}")
        return []


def get_blacklisted_channels() -> list:
    """Get list of blacklisted channels to skip."""
    try:
        with get_db_session() as db:
            channels = (
                db.query(TelegramChannel).filter(TelegramChannel.is_blacklisted == True).all()
            )

            return [c.channel_name for c in channels]
    except Exception as e:
        logger.error(f"Error getting blacklisted channels: {e}")
        return []


# ============================================
# PREDICTION TRACKING (V1.1 - Post-match Feedback Loop)
# ============================================


def update_channel_predictions(
    channel_id: str,
    is_prediction: bool = False,
    was_correct: bool = False,
):
    """
    Update channel prediction metrics after match settlement.

    This function is called by the settlement service after a match ends
    to update the predictions_made and predictions_correct counters.

    Args:
        channel_id: Channel to update
        is_prediction: Whether this message contained a prediction
        was_correct: Whether the prediction was correct (only relevant if is_prediction=True)
    """
    if not is_prediction:
        return  # No prediction to track

    try:
        with get_db_session() as db:
            channel = (
                db.query(TelegramChannel).filter(TelegramChannel.channel_id == channel_id).first()
            )

            if not channel:
                logger.warning(f"Channel not found for prediction update: {channel_id}")
                return

            # Increment predictions_made
            channel.predictions_made += 1

            # Increment predictions_correct if prediction was correct
            if was_correct:
                channel.predictions_correct += 1

            channel.last_updated = datetime.now(timezone.utc)

            # Log the update
            accuracy = (
                channel.predictions_correct / channel.predictions_made
                if channel.predictions_made > 0
                else 0.0
            )
            logger.info(
                f"📊 Channel @{channel.channel_name} prediction tracked: "
                f"{'CORRECT' if was_correct else 'INCORRECT'} | "
                f"Accuracy: {accuracy:.1%} ({channel.predictions_correct}/{channel.predictions_made})"
            )

            # Recalculate trust score with new prediction data
            from src.analysis.telegram_trust_score import ChannelMetrics, calculate_trust_score

            metrics = ChannelMetrics(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                total_messages=channel.total_messages,
                messages_with_odds_impact=channel.messages_with_odds_impact,
                avg_timestamp_lag_minutes=channel.avg_timestamp_lag_minutes,
                insider_hits=channel.insider_hits,
                late_messages=channel.late_messages,
                total_edits=channel.total_edits,
                total_deletes=channel.total_deletes,
                predictions_made=channel.predictions_made,
                predictions_correct=channel.predictions_correct,
                red_flags_count=channel.red_flags_count,
                echo_messages=channel.echo_messages,
            )

            trust_score, trust_level = calculate_trust_score(metrics)
            channel.trust_score = trust_score
            channel.trust_level = trust_level.value

            # Check for auto-blacklist due to poor accuracy
            if channel.predictions_made >= 10 and accuracy < 0.25:
                channel.is_blacklisted = True
                channel.blacklist_reason = (
                    f"Auto-blacklisted: Prediction accuracy below 25% ({accuracy:.1%})"
                )
                logger.warning(
                    f"🚫 Channel auto-blacklisted due to poor accuracy: @{channel.channel_name}"
                )

            # commit is automatic in context manager

    except Exception as e:
        logger.error(f"Error updating channel predictions: {e}")


def get_pending_predictions_for_match(match_id: str) -> list[dict]:
    """
    Get all unverified predictions for a specific match.

    Called by settlement service after match ends to verify predictions.

    Args:
        match_id: Match ID to query

    Returns:
        List of dicts with prediction data
    """
    try:
        with get_db_session() as db:
            predictions = (
                db.query(TelegramMessageLog)
                .filter(
                    TelegramMessageLog.match_id == match_id,
                    TelegramMessageLog.prediction_type.isnot(None),
                    TelegramMessageLog.prediction_verified == False,
                )
                .all()
            )

            return [
                {
                    "id": p.id,
                    "channel_id": p.channel_id,
                    "prediction_type": p.prediction_type,
                    "prediction_team": p.prediction_team,
                    "message_time": p.message_time,
                }
                for p in predictions
            ]
    except Exception as e:
        logger.error(f"Error getting pending predictions: {e}")
        return []


def verify_prediction(
    prediction_id: int,
    was_correct: bool,
):
    """
    Mark a prediction as verified and update channel metrics.

    Args:
        prediction_id: ID of the TelegramMessageLog to update
        was_correct: Whether the prediction was correct
    """
    try:
        with get_db_session() as db:
            prediction = (
                db.query(TelegramMessageLog).filter(TelegramMessageLog.id == prediction_id).first()
            )

            if not prediction:
                logger.warning(f"Prediction not found: {prediction_id}")
                return

            # Mark as verified
            prediction.prediction_verified = True
            prediction.prediction_correct = was_correct

            # Update channel metrics
            channel_id = prediction.channel_id

            # Commit first, then update channel (to avoid session conflicts)
            db.flush()

        # Now update channel predictions (in a new session)
        update_channel_predictions(
            channel_id=channel_id,
            is_prediction=True,
            was_correct=was_correct,
        )

    except Exception as e:
        logger.error(f"Error verifying prediction: {e}")
