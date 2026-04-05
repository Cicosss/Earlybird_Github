"""
Telegram Intelligence Listener

Monitors verified insider Telegram channels for squad/injury news.
Implements STRICT TIME-GATING to prevent "Time Hallucinations" (old news alerts).

CRITICAL FILTERS:
1. Message must be < 12 hours old
2. Team mentioned must have an UPCOMING match (next 48h)
3. If match was yesterday -> DROP (post-match commentary)

V2.0: Intelligent feature detection via startup_validator.is_feature_disabled()
     - Skips Tavily verification if 'tavily_enrichment' is disabled
     - Logs clear status messages for disabled features
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import ChannelInvalidError, ChannelPrivateError, UsernameNotOccupiedError

from config.settings import DATA_DIR, is_stop_requested
from src.analysis.image_ocr import process_squad_image
from src.analysis.squad_analyzer import analyze_squad_list
from src.database.models import Match, TeamAlias
from src.processing.sources_config import get_all_telegram_channels
from src.utils.content_analysis import RelevanceAnalyzer
from src.utils.validators import safe_dict_get

# Initialize logger for this module
logger = logging.getLogger(__name__)

# V2.0: Import startup validator for intelligent feature detection
try:
    from src.utils.startup_validator import is_feature_disabled

    _STARTUP_VALIDATOR_AVAILABLE = True
except ImportError:
    _STARTUP_VALIDATOR_AVAILABLE = False
    logger.debug("Startup validator not available - all features enabled by default")

    def is_feature_disabled(feature: str) -> bool:
        """Fallback if startup validator is not available."""
        return False


# ============================================
# TRUST SCORE INTEGRATION (V4.3)
# ============================================
try:
    from src.analysis.telegram_trust_score import (
        ChannelMetrics,
        _get_text_hash,
        extract_prediction_from_text,  # V1.1: Prediction extraction
        get_first_odds_drop_time,
        track_odds_correlation,  # V4.3: Odds correlation tracking
        validate_telegram_message,
    )
    from src.database.telegram_channel_model import (
        get_blacklisted_channels,
        get_channel_metrics,
        get_or_create_channel,
        init_telegram_tracking_db,
        log_telegram_message,
        update_channel_metrics,
    )

    _TRUST_SCORE_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Trust Score module not available: {e}")
    _TRUST_SCORE_AVAILABLE = False

load_dotenv()


# ============================================
# TAVILY INTEL VERIFICATION (V7.0)
# ============================================


async def _tavily_verify_intel(intel_text: str, team_name: str) -> dict | None:
    """
    V7.0: Use Tavily to verify intel from medium-trust Telegram channels.

    Called when trust score is between 0.4 and 0.7.

    Args:
        intel_text: The intel message text
        team_name: Team the intel is about

    Returns:
        Dict with 'confirmed', 'contradicted', or None if inconclusive

    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    try:
        from src.ingestion.tavily_budget import get_budget_manager
        from src.ingestion.tavily_provider import get_tavily_provider
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        # V2.0: Check if Tavily enrichment is disabled by startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("tavily_enrichment"):
            logging.debug(
                "⏭️ [TELEGRAM] Tavily verification disabled by startup validator (TAVILY_API_KEY not configured)"
            )
            return None

        tavily = get_tavily_provider()
        budget = get_budget_manager()

        if not tavily or not tavily.is_available():
            logging.debug("📊 [TELEGRAM] Tavily provider not available")
            return None

        if not budget or not budget.can_call("telegram_monitor"):
            logging.debug("📊 [TELEGRAM] Tavily budget limit reached")
            return None

        # Build verification query
        query = TavilyQueryBuilder.build_news_verification_query(
            news_title=intel_text[:200], team_name=team_name
        )

        # V7.1: Use native Tavily news parameters for better filtering
        response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
            topic="news",
            days=3,
        )

        if response:
            budget.record_call("telegram_monitor")

            # Analyze response to determine confirmation/contradiction
            answer = (response.answer or "").lower()

            # Keywords indicating confirmation
            confirm_keywords = ["confirmed", "reports", "according to", "official", "announced"]
            # Keywords indicating contradiction
            contradict_keywords = [
                "denied",
                "false",
                "rumor",
                "unconfirmed",
                "no evidence",
                "not true",
            ]

            has_confirm = any(kw in answer for kw in confirm_keywords)
            has_contradict = any(kw in answer for kw in contradict_keywords)

            if has_confirm and not has_contradict:
                return {"confirmed": True, "answer": response.answer}
            elif has_contradict and not has_confirm:
                return {"contradicted": True, "answer": response.answer}
            else:
                # Inconclusive
                return {"inconclusive": True, "answer": response.answer}

        return None

    except ImportError:
        logging.debug("⚠️ [TELEGRAM] Tavily not available")
        return None
    except Exception as e:
        logging.warning(f"⚠️ [TELEGRAM] Tavily verification failed: {e}")
        return None


def _safe_int_env(key: str, default: int = 0) -> int:
    """Safely parse integer from environment variable."""
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        logging.warning(f"⚠️ Invalid {key} value '{val}', using default {default}")
        return default


API_ID = _safe_int_env("TELEGRAM_API_ID", 0)
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
# Use data/ directory for session file (consistent with setup_telegram_auth.py and run_telegram_monitor.py)
SESSION_NAME = os.path.join(DATA_DIR, "earlybird_monitor")

# ============================================
# TIME-GATING CONFIGURATION
# ============================================
MAX_MESSAGE_AGE_HOURS = 12  # Drop messages older than this
MATCH_LOOKAHEAD_HOURS = 48  # Only process if match in next N hours
MIN_MATCH_TIME_HOURS = 1  # Ignore if match already started

# Squad-related keywords (multi-language) - centralized from RelevanceAnalyzer
SQUAD_KEYWORDS = RelevanceAnalyzer.SQUAD_KEYWORDS

# Team name patterns for extraction (common suffixes to remove)
TEAM_SUFFIXES = ["FC", "SK", "AS", "AC", "FK", "SC", "CF", "CD", "SD", "UD", "RCD", "CA"]


def normalize_datetime(dt: datetime) -> datetime:
    """Convert datetime to naive UTC for comparison."""
    try:
        if dt.tzinfo is not None:
            # Convert to UTC then remove timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        logger.error(f"Error normalizing datetime: {e}")
        return datetime.now(timezone.utc).replace(tzinfo=None)


def is_message_fresh(msg_date: datetime, max_age_hours: int = MAX_MESSAGE_AGE_HOURS) -> bool:
    """
    TIME-GATE #1: Check if message is fresh enough to process.

    Args:
        msg_date: Message timestamp
        max_age_hours: Maximum age in hours

    Returns:
        True if message is fresh, False if too old
    """
    try:
        now = datetime.now(timezone.utc)
        msg_time = normalize_datetime(msg_date)
        # Normalize 'now' to naive UTC for consistent comparison
        now_naive = now.replace(tzinfo=None)
        cutoff = now_naive - timedelta(hours=max_age_hours)

        is_fresh = msg_time >= cutoff
        if not is_fresh:
            age_hours = (now_naive - msg_time).total_seconds() / 3600
            logger.debug(
                f"📅 [TELEGRAM] Message too old: {age_hours:.1f} hours (max: {max_age_hours}h)"
            )

        return is_fresh
    except Exception as e:
        logger.error(f"Error checking message freshness: {e}")
        return False


def extract_team_names_from_text(text: str) -> list[str]:
    """
    Extract potential team names from message text.

    Uses pattern matching to find capitalized words that could be team names.

    Args:
        text: Message text

    Returns:
        List of potential team names
    """
    if not text:
        return []

    teams: list[str] = []

    # Pattern 1: Words starting with capital letter (potential team names)
    # Match 2+ consecutive capitalized words
    pattern = (
        r"\b([A-Z][a-zğüşıöçİĞÜŞÖÇ]+"
        r"(?:\s+[A-Z][a-zğüşıöçİĞÜŞÖÇ]+)*)\b"
    )
    matches = re.findall(pattern, text)

    for match in matches:
        # Clean up common suffixes
        clean_name = match
        for suffix in TEAM_SUFFIXES:
            if clean_name.endswith(f" {suffix}"):
                clean_name = clean_name[: -len(suffix) - 1].strip()

        if len(clean_name) >= 3:  # Minimum 3 chars
            teams.append(clean_name)

    # Pattern 2: All-caps words (often team abbreviations or names)
    caps_pattern = r"\b([A-ZĞÜŞİÖÇ]{3,})\b"
    caps_matches = re.findall(caps_pattern, text)
    teams.extend(caps_matches)

    return list(set(teams))  # Remove duplicates


def has_upcoming_match(
    team_name: str, lookahead_hours: int = MATCH_LOOKAHEAD_HOURS
) -> tuple[bool, Match | None]:
    """
    TIME-GATE #2: Check if team has an upcoming match in ACTIVE LEAGUES.

    V12.4: Now uses dynamic active scope (Supabase + Tier1 + Tier2)
    instead of hardcoded ELITE_LEAGUES (7 leagues only).

    This prevents processing news about teams from non-active leagues
    (e.g., Benfica from Portuguese Liga).

    Args:
        team_name: Team name to check
        lookahead_hours: Hours to look ahead

    Returns:
        Tuple of (has_match, match_object)
    """
    try:
        # V12.4/V11.2: Use dynamic active scope from Supabase/Mirror
        # No more hardcoded ELITE_LEAGUES fallback
        from src.database.models import get_db_session

        from src.ingestion.league_manager import is_in_active_scope

        with get_db_session() as db:
            now = datetime.now(timezone.utc)
            min_time = now + timedelta(hours=MIN_MATCH_TIME_HOURS)
            max_time = now + timedelta(hours=lookahead_hours)

            # Search for team in home or away
            team_lower = team_name.lower()

            matches = (
                db.query(Match)
                .filter(Match.start_time >= min_time, Match.start_time <= max_time)
                .all()
            )

            for match in matches:
                home_team = getattr(match, "home_team", None)
                away_team = getattr(match, "away_team", None)
                league = getattr(match, "league", None)

                if not home_team or not away_team:
                    continue

                home_lower = home_team.lower()
                away_lower = away_team.lower()

                # Fuzzy match: team name contained in home/away
                if (
                    team_lower in home_lower
                    or team_lower in away_lower
                    or home_lower in team_lower
                    or away_lower in team_lower
                ):
                    # V11.2: Use dynamic active scope from Supabase/Mirror
                    if league:
                        if not is_in_active_scope(league):
                            logger.debug(f"⏭️ [SCOPE] Skipping non-active league: {league}")
                            continue

                    logger.debug(f"🏆 [TELEGRAM] Found upcoming match: {home_team} vs {away_team}")
                    return True, match

            logger.debug(f"🏆 [TELEGRAM] No upcoming matches for {team_name}")
            return False, None

    except Exception as e:
        logger.error(f"Error checking upcoming match for {team_name}: {e}")
        return False, None


def should_process_message(msg_date: datetime, text: str) -> tuple[bool, Match | None, str]:
    """
    MASTER TIME-GATE: Determine if a message should be processed.

    Checks:
    1. Message freshness (< 12 hours)
    2. Team has upcoming match (next 48h)

    Args:
        msg_date: Message timestamp
        text: Message text

    Returns:
        Tuple of (should_process, match_object, reason)
    """
    try:
        # Gate 1: Message freshness
        if not is_message_fresh(msg_date):
            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            msg_naive = normalize_datetime(msg_date)
            age_hours = (now_naive - msg_naive).total_seconds() / 3600
            reason = f"Message too old ({age_hours:.1f}h > {MAX_MESSAGE_AGE_HOURS}h)"
            logger.debug(f"⏭️ [TELEGRAM] {reason}")
            return False, None, reason

        # Gate 2: Extract team names and check for upcoming matches
        team_names = extract_team_names_from_text(text)

        if not team_names:
            reason = "No team names detected in message"
            logger.debug(f"⏭️ [TELEGRAM] {reason}")
            return False, None, reason

        # Check each potential team name
        for team_name in team_names:
            has_match, match = has_upcoming_match(team_name)
            if has_match:
                reason = f"Team '{team_name}' has upcoming match"
                logger.debug(f"✅ [TELEGRAM] {reason}")
                return True, match, reason

        reason = f"No upcoming matches for detected teams: {team_names[:3]}"
        logger.debug(f"⏭️ [TELEGRAM] {reason}")
        return False, None, reason

    except Exception as e:
        logger.error(f"Error checking if message should be processed: {e}")
        return False, None, "Error checking message validity"


async def get_channel_entity_safe(client: TelegramClient, channel: str):
    """
    ROBUST CONNECTION: Safely get channel entity with error handling.

    Handles:
    - Deleted channels
    - Renamed channels
    - Private channels
    - Invalid usernames

    Args:
        client: Telegram client
        channel: Channel username

    Returns:
        Channel entity or None if unavailable
    """
    try:
        entity = await client.get_entity(channel)
        return entity
    except UsernameNotOccupiedError:
        logging.warning(f"⚠️ Channel @{channel} does not exist (deleted/renamed)")
        return None
    except ChannelPrivateError:
        logging.warning(f"⚠️ Channel @{channel} is private (need to join)")
        return None
    except ChannelInvalidError:
        logging.warning(f"⚠️ Channel @{channel} is invalid")
        return None
    except Exception as e:
        logging.warning(f"⚠️ Error accessing @{channel}: {type(e).__name__}: {e}")
        return None


async def fetch_squad_images(existing_client: TelegramClient = None) -> list[dict]:
    """
    Main function to fetch squad list images from Telegram channels.

    UPGRADED with:
    - Robust connection (skip deleted/renamed channels)
    - Strict time-gating (12h freshness + upcoming match check)
    - Support for existing client to avoid session lock

    Args:
        existing_client: Optional existing TelegramClient to reuse (avoids session lock)

    Returns:
        List of dicts with: team, image_path, ocr_text, match_id
    """
    if not API_ID or not API_HASH:
        logging.error("Telegram API credentials not configured")
        return []

    # Check if session file exists (only if no existing client)
    if not existing_client and not os.path.exists(f"{SESSION_NAME}.session"):
        logging.error("❌ Session file not found. Please run: python setup_telegram_auth.py")
        return []

    results: list[dict[str, Any]] = []

    # Initialize Trust Score DB once at start (not in loop to avoid lock issues)
    if _TRUST_SCORE_AVAILABLE:
        try:
            init_telegram_tracking_db()
        except Exception as e:
            logging.warning(f"⚠️ Could not initialize telegram tracking DB: {e}")

    # Use existing client or create new one
    client = existing_client
    should_disconnect = False

    try:
        if client is None:
            # Create new client only if none provided
            client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
            await client.connect()
            should_disconnect = True

            if not await client.is_user_authorized():
                logging.error("Session expired. Please re-run setup_telegram_auth.py")
                await client.disconnect()
                return []

            logging.info("✅ Connected to Telegram")

        # Get all configured insider channels
        all_channels = get_all_telegram_channels()

        # Also get teams with configured Telegram channels (legacy support)
        from src.database.models import get_db_session

        teams: list[dict[str, str]] = []
        try:
            with get_db_session() as db:
                teams = db.query(TeamAlias).filter(TeamAlias.telegram_channel.isnot(None)).all()
                # Detach objects from session to use outside context
                teams = [
                    {
                        "api_name": t.api_name,
                        "search_name": t.search_name,
                        "telegram_channel": t.telegram_channel,
                    }
                    for t in teams
                ]
        except Exception as e:
            logging.warning(f"⚠️ Could not load team aliases: {e}")

        # Build channel list: insider channels + team-specific channels
        channels_to_monitor: list[dict[str, str]] = []

        # Add insider channels
        for country, channels in all_channels.items():
            for channel in channels:
                channels_to_monitor.append(
                    {"channel": channel, "country": country, "type": "insider"}
                )

        # Add team-specific channels
        for team in teams:
            channels_to_monitor.append(
                {
                    "channel": team["telegram_channel"],
                    "team": team["api_name"],
                    "search_name": team["search_name"],
                    "type": "team",
                }
            )

        if not channels_to_monitor:
            logging.warning("No Telegram channels configured")
            await client.disconnect()
            return []

        logging.info(f"📡 Monitoring {len(channels_to_monitor)} Telegram channels...")

        # Create temp directory for images
        os.makedirs("./temp", exist_ok=True)

        # Stats for logging
        stats = {
            "channels_checked": 0,
            "channels_failed": 0,
            "channels_blacklisted": 0,
            "messages_checked": 0,
            "messages_dropped_old": 0,
            "messages_dropped_no_match": 0,
            "messages_dropped_low_trust": 0,
            "messages_processed": 0,
            "insider_hits": 0,
        }

        # Loop through each channel
        for channel_info in channels_to_monitor:
            # P1: Check for full stop before each channel
            if is_stop_requested():
                logging.info("🛑 Stop requested during channel iteration, aborting")
                break

            channel = channel_info["channel"]

            # ROBUST CONNECTION: Safe entity retrieval
            entity = await get_channel_entity_safe(client, channel)

            if entity is None:
                stats["channels_failed"] += 1
                continue

            stats["channels_checked"] += 1
            logging.info(f"📡 Checking channel: @{channel}")

            try:
                # Fetch last 10 messages
                messages = await client.get_messages(entity, limit=10)

                for msg in messages:
                    stats["messages_checked"] += 1

                    # ============================================
                    # DUAL MODE: TEXT + IMAGE OCR
                    # ============================================
                    # Step 1: Initialize with caption/text
                    caption_text = msg.message or msg.text or ""
                    full_text = caption_text
                    ocr_text = None
                    image_path = None

                    # Step 2: If has image, download and OCR FIRST
                    # This allows us to use OCR text for time-gating
                    if msg.photo:
                        timestamp = int(msg.date.timestamp())
                        image_path = f"./temp/{channel}_{timestamp}.jpg"

                        try:
                            await client.download_media(msg.photo, image_path)
                            logging.debug(f"📥 Downloaded image: {image_path}")

                            # Extract text via OCR (use local file path)
                            # V5.0: Pass channel_info for contextual trust bypass
                            ocr_text = process_squad_image(
                                f"file://{os.path.abspath(image_path)}", channel_info=channel_info
                            )

                            if ocr_text:
                                # APPEND OCR text to full_text for analysis
                                full_text += f"\n[OCR]: {ocr_text}"
                                logging.debug(f"📸 OCR extracted {len(ocr_text)} chars")
                        except Exception as ocr_err:
                            logging.warning(f"OCR failed for {image_path}: {ocr_err}")

                    # Step 3: TIME-GATING with COMBINED text (caption + OCR)
                    should_process, match, reason = should_process_message(msg.date, full_text)

                    if not should_process:
                        if "too old" in reason.lower():
                            stats["messages_dropped_old"] += 1
                        else:
                            stats["messages_dropped_no_match"] += 1
                        logging.debug(f"   ⏭️ Skipped: {reason}")
                        # Clean up downloaded image if not processing
                        if image_path and os.path.exists(image_path):
                            try:
                                os.remove(image_path)
                            except Exception as cleanup_err:
                                logging.debug(
                                    f"Could not remove temp image {image_path}: {cleanup_err}"
                                )
                        continue

                    # Step 4: Check for squad keywords in COMBINED text
                    full_text_lower = full_text.lower()
                    has_keyword = any(keyword in full_text_lower for keyword in SQUAD_KEYWORDS)

                    # Must have either keyword OR image with OCR content
                    if not has_keyword and not (msg.photo and ocr_text):
                        logging.debug("   ⏭️ No keywords and no useful OCR")
                        continue

                    # Step 5: PROCESS - Message passed all gates
                    stats["messages_processed"] += 1
                    logging.info(f"🎯 Processing message from @{channel}")
                    logging.info(f"   Reason: {reason}")
                    logging.info(
                        f"   Caption: {caption_text[:80]}..."
                        if caption_text
                        else "   Caption: (none)"
                    )
                    if ocr_text:
                        logging.info(f"   OCR: {ocr_text[:80]}...")

                    # ============================================
                    # Step 5b: TRUST SCORE VALIDATION (V4.3)
                    # ============================================
                    trust_multiplier = 1.0
                    trust_validation_reason = "Trust Score not available"
                    is_insider_hit = False

                    if _TRUST_SCORE_AVAILABLE:
                        try:
                            # Get or create channel record (side effect:
                            # creates/updates channel in DB)
                            get_or_create_channel(channel, channel)

                            # Check if channel is blacklisted
                            blacklisted = get_blacklisted_channels()
                            if channel in blacklisted:
                                logging.warning(f"   🚫 BLACKLISTED channel @{channel} - skipping")
                                stats["messages_dropped_no_match"] += 1
                                continue

                            # Get first odds drop time for this match (if available)
                            first_drop_time = None
                            if match:
                                # VPS FIX: Extract match_id safely to prevent session detachment
                                match_id = getattr(match, "id", None)
                                if match_id:
                                    first_drop_time = get_first_odds_drop_time(match_id)

                            # Load channel metrics for validation
                            channel_metrics_dict = get_channel_metrics(channel)
                            channel_metrics_obj = None
                            if channel_metrics_dict:
                                channel_metrics_obj = ChannelMetrics(
                                    channel_id=channel,
                                    channel_name=channel,
                                    total_messages=channel_metrics_dict.get("total_messages", 0),
                                    messages_with_odds_impact=channel_metrics_dict.get(
                                        "insider_hits", 0
                                    )
                                    + channel_metrics_dict.get("late_messages", 0),
                                    insider_hits=channel_metrics_dict.get("insider_hits", 0),
                                    late_messages=channel_metrics_dict.get("late_messages", 0),
                                    echo_messages=channel_metrics_dict.get("echo_messages", 0),
                                    red_flags_count=channel_metrics_dict.get("red_flags_count", 0),
                                    trust_score=channel_metrics_dict.get("trust_score", 0.5),
                                )

                            # Validate message
                            validation = validate_telegram_message(
                                channel_id=channel,
                                channel_name=channel,
                                message_text=full_text,
                                message_time=msg.date,
                                first_odds_drop_time=first_drop_time,
                                channel_metrics=channel_metrics_obj,
                            )

                            trust_multiplier = validation.trust_multiplier
                            trust_validation_reason = validation.reason
                            is_insider_hit = validation.is_insider_hit

                            # Log validation result
                            if validation.is_valid:
                                logging.info(
                                    f"   🔐 Trust: {trust_multiplier:.2f} | "
                                    f"{trust_validation_reason}"
                                )
                            else:
                                logging.warning(
                                    f"   ⚠️ Low Trust: {trust_multiplier:.2f} | "
                                    f"{trust_validation_reason}"
                                )

                            # V1.2: Check if message was edited (Telethon provides edit_date)
                            was_edited = hasattr(msg, "edit_date") and msg.edit_date is not None

                            # Update channel metrics
                            update_channel_metrics(
                                channel_id=channel,
                                is_insider_hit=is_insider_hit,
                                is_late=(
                                    validation.timestamp_lag_minutes
                                    and validation.timestamp_lag_minutes > 30
                                ),
                                is_echo=validation.is_echo,
                                is_edit=was_edited,  # V1.2: Track edits in channel metrics
                                red_flags=validation.red_flags,
                                timestamp_lag=validation.timestamp_lag_minutes,
                            )

                            # Log message for audit
                            # VPS FIX: Extract match_id safely to prevent session detachment
                            match_id = getattr(match, "id", None) if match else None

                            # V1.1: Extract prediction from message text
                            prediction_data = {"prediction_type": None, "prediction_team": None}
                            if match and full_text:
                                home_team_name = getattr(match, "home_team", None)
                                away_team_name = getattr(match, "away_team", None)
                                try:
                                    prediction_data = extract_prediction_from_text(
                                        text=full_text,
                                        home_team=home_team_name,
                                        away_team=away_team_name,
                                    )
                                    if prediction_data.get("prediction_type"):
                                        logging.info(
                                            f"   🔮 Prediction detected: {prediction_data['prediction_type']}"
                                            + (
                                                f" ({prediction_data['prediction_team']})"
                                                if prediction_data.get("prediction_team")
                                                else ""
                                            )
                                        )
                                except Exception as pred_err:
                                    logging.debug(f"   Prediction extraction error: {pred_err}")

                            log_telegram_message(
                                channel_id=channel,
                                message_id=str(msg.id) if hasattr(msg, "id") else None,
                                text_hash=_get_text_hash(full_text),
                                text_preview=full_text[:200] if full_text else None,
                                message_time=msg.date,
                                match_id=match_id,
                                timestamp_lag=validation.timestamp_lag_minutes,
                                was_insider_hit=is_insider_hit,
                                is_echo=validation.is_echo,
                                echo_source=validation.echo_source_channel,  # FIX: Propagate echo source
                                trust_multiplier=trust_multiplier,
                                validation_reason=trust_validation_reason,
                                red_flags=validation.red_flags,
                                # V1.1: Pass prediction data
                                prediction_type=prediction_data.get("prediction_type"),
                                prediction_team=prediction_data.get("prediction_team"),
                                # V1.2: Pass edit status
                                was_edited=was_edited,
                            )

                            # V4.3: Track odds correlation for Trust Score V2
                            # This updates channel metrics with insider/follower classification
                            if match and msg.date:
                                try:
                                    # VPS FIX: Extract match_id safely to prevent session detachment
                                    match_id = getattr(match, "id", None)
                                    if match_id:
                                        lag_minutes = track_odds_correlation(
                                            channel_id=channel,
                                            message_time=msg.date,
                                            match_id=match_id,
                                        )
                                    if lag_minutes is not None:
                                        if lag_minutes < 0:
                                            logging.info(
                                                f"   📊 INSIDER: Message {abs(lag_minutes):.0f}min "
                                                f"BEFORE odds drop"
                                            )
                                        elif lag_minutes <= 5:
                                            logging.debug(
                                                f"   📊 FAST: Message {lag_minutes:.0f}min "
                                                f"after odds drop"
                                            )
                                        else:
                                            logging.debug(
                                                f"   📊 LATE: Message {lag_minutes:.0f}min "
                                                f"after odds drop"
                                            )
                                except Exception as corr_err:
                                    logging.debug(f"   Odds correlation tracking error: {corr_err}")

                            # Skip messages with very low trust
                            if trust_multiplier < 0.15:
                                logging.info(
                                    f"   ⏭️ Skipping low-trust message "
                                    f"(multiplier: {trust_multiplier:.2f})"
                                )
                                continue

                            # Determine team info BEFORE using it in Tavily verification
                            # VPS FIX: Extract home_team safely to prevent session detachment
                            home_team = (
                                getattr(match, "home_team", "Unknown") if match else "Unknown"
                            )
                            team_name = channel_info.get("team", home_team)
                            search_name = channel_info.get("search_name", team_name)

                            # V7.0: Tavily verification for medium-trust channels (0.4-0.7)
                            if 0.4 <= trust_multiplier <= 0.7:
                                tavily_result = await _tavily_verify_intel(full_text, team_name)
                                if tavily_result:
                                    if tavily_result.get("confirmed"):
                                        # Tavily confirms - boost trust by 0.2
                                        trust_multiplier = min(1.0, trust_multiplier + 0.2)
                                        trust_validation_reason += " | Tavily CONFIRMED (+0.2)"
                                        logging.info(
                                            f"   🔍 Tavily confirmed intel, "
                                            f"trust boosted to {trust_multiplier:.2f}"
                                        )
                                    elif tavily_result.get("contradicted"):
                                        # Tavily contradicts - reduce trust by 0.1
                                        trust_multiplier = max(0.0, trust_multiplier - 0.1)
                                        trust_validation_reason += " | Tavily CONTRADICTED (-0.1)"
                                        logging.warning(
                                            f"   ⚠️ Tavily contradicted intel, "
                                            f"trust reduced to {trust_multiplier:.2f}"
                                        )
                                    # else: inconclusive - keep original trust

                        except Exception as trust_err:
                            logging.warning(f"   ⚠️ Trust validation error: {trust_err}")
                            trust_multiplier = 0.5  # Default to neutral on error

                    results.append(
                        {
                            "team": team_name,
                            "team_search_name": search_name,
                            "image_path": image_path,
                            "ocr_text": ocr_text,
                            "caption": caption_text,
                            "full_text": full_text,  # Combined text for analysis
                            "timestamp": msg.date,
                            "channel": channel,
                            "match": match,
                            "channel_type": channel_info["type"],
                            "has_image": msg.photo is not None,
                            # V4.3: Trust Score fields
                            "trust_multiplier": trust_multiplier,
                            "trust_reason": trust_validation_reason,
                            "is_insider_hit": is_insider_hit,
                        }
                    )

            except Exception as e:
                logging.error(f"Error processing channel @{channel}: {e}")
                continue

        # Only disconnect if we created the client
        if should_disconnect:
            await client.disconnect()

        # Log stats
        logging.info("📊 Telegram Monitor Stats:")
        logging.info(
            f"   Channels: {stats['channels_checked']} checked, "
            f"{stats['channels_failed']} failed, "
            f"{stats['channels_blacklisted']} blacklisted"
        )
        logging.info(f"   Messages: {stats['messages_checked']} checked")
        logging.info(
            f"   Dropped: {stats['messages_dropped_old']} old, "
            f"{stats['messages_dropped_no_match']} no match, "
            f"{stats['messages_dropped_low_trust']} low trust"
        )
        logging.info(
            f"   Processed: {stats['messages_processed']} | Insider Hits: {stats['insider_hits']}"
        )
        logging.info(f"✅ Found {len(results)} relevant items")

        return results

    except Exception as e:
        import traceback

        logging.error(f"Critical error in Telegram listener: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return []


async def monitor_channels_for_squads(existing_client: TelegramClient = None) -> list[dict]:
    """
    High-level wrapper to monitor channels and analyze squad lists.

    DUAL MODE: Processes both text-only and image messages.
    Uses combined text (caption + OCR) for analysis.

    Args:
        existing_client: Optional existing TelegramClient to reuse

    Returns:
        List of alerts (missing player detected)
    """
    squad_images = await fetch_squad_images(existing_client=existing_client)

    alerts: list[dict[str, Any]] = []

    for squad in squad_images:
        has_image = safe_dict_get(squad, "has_image", default=False)
        ocr_text = safe_dict_get(squad, "ocr_text", default=None)

        # ============================================
        # DUAL MODE PROCESSING
        # ============================================

        if has_image and ocr_text:
            # MODE 1: Image with OCR - Full squad analysis
            logging.info(f"📸 Analyzing squad image from @{squad['channel']}")

            alert = analyze_squad_list(
                image_url=squad["image_path"],
                team_name=squad["team_search_name"],
                match_id=f"telegram_{squad['channel']}_{int(squad['timestamp'].timestamp())}",
            )

            if alert:
                alert["source"] = "TELEGRAM_CHANNEL"
                alert["channel"] = squad["channel"]
                alert["channel_type"] = safe_dict_get(squad, "channel_type", default="unknown")
                alert["match"] = safe_dict_get(squad, "match", default=None)
                alert["mode"] = "IMAGE_OCR"
                alerts.append(alert)
                logging.info(f"🚨 ALERT (IMAGE): {alert['summary']}")
            else:
                # Even if no missing players, report the lineup detection
                caption_preview = safe_dict_get(squad, "caption", default="")[:100]
                ocr_preview = ocr_text[:100] if ocr_text else ""

                alerts.append(
                    {
                        "summary": (
                            f"📋 Squad list detected from @{squad['channel']}: "
                            f"{caption_preview or ocr_preview}"
                        ),
                        "score": 5,  # Informational
                        "url": f"https://t.me/{squad['channel']}",
                        "source": "TELEGRAM_CHANNEL",
                        "channel": squad["channel"],
                        "channel_type": safe_dict_get(squad, "channel_type", default="unknown"),
                        "match": safe_dict_get(squad, "match", default=None),
                        "mode": "IMAGE_OCR",
                        "ocr_text": ocr_text,
                    }
                )

        elif has_image and not ocr_text:
            # MODE 2: Image without OCR (OCR failed) - Report with caption only
            caption = safe_dict_get(squad, "caption", default="")
            if caption:
                alerts.append(
                    {
                        "summary": f"📷 Image posted by @{squad['channel']}: {caption[:200]}",
                        "score": 4,  # Lower score - OCR failed
                        "url": f"https://t.me/{squad['channel']}",
                        "source": "TELEGRAM_CHANNEL",
                        "channel": squad["channel"],
                        "channel_type": safe_dict_get(squad, "channel_type", default="unknown"),
                        "match": safe_dict_get(squad, "match", default=None),
                        "mode": "IMAGE_NO_OCR",
                    }
                )

        else:
            # MODE 3: Text-only message
            caption = safe_dict_get(squad, "caption", default="")
            if caption:
                alerts.append(
                    {
                        "summary": f"📢 Intel from @{squad['channel']}: {caption[:200]}",
                        "score": 6,  # Medium score for text intel
                        "url": f"https://t.me/{squad['channel']}",
                        "source": "TELEGRAM_CHANNEL",
                        "channel": squad["channel"],
                        "channel_type": safe_dict_get(squad, "channel_type", default="unknown"),
                        "match": safe_dict_get(squad, "match", default=None),
                        "mode": "TEXT_ONLY",
                    }
                )

        # Cleanup temp image after processing (Bug 2 fix)
        image_path = squad.get("image_path")
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
                logging.debug(f"🗑️ Cleaned up temp image: {image_path}")
            except Exception as cleanup_err:
                logging.warning(f"Could not remove temp image {image_path}: {cleanup_err}")

    # Log summary
    image_alerts = len([a for a in alerts if a.get("mode") == "IMAGE_OCR"])
    text_alerts = len([a for a in alerts if a.get("mode") == "TEXT_ONLY"])
    logging.info(f"📊 Alert Summary: {image_alerts} image-based, {text_alerts} text-based")

    return alerts


def run_telegram_monitor():
    """
    Synchronous wrapper for running the async monitor.
    Can be called from main.py loop.
    """
    import asyncio

    return asyncio.run(monitor_channels_for_squads())


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    print("=" * 60)
    print("🔍 TELEGRAM INTELLIGENCE LISTENER TEST")
    print("=" * 60)

    print("\n📋 Configured Channels:")
    all_channels = get_all_telegram_channels()
    for country, channels in all_channels.items():
        if channels:
            print(f"   {country}: {', '.join(channels)}")

    print("\n⏰ Time-Gating Config:")
    print(f"   Max message age: {MAX_MESSAGE_AGE_HOURS} hours")
    print(f"   Match lookahead: {MATCH_LOOKAHEAD_HOURS} hours")
    print(f"   Min match time: {MIN_MATCH_TIME_HOURS} hours")

    print("\n🔍 Testing time-gate functions...")

    # Test freshness check
    fresh_time = datetime.now(timezone.utc) - timedelta(hours=2)
    old_time = datetime.now(timezone.utc) - timedelta(hours=24)

    print(f"   2h old message fresh? {is_message_fresh(fresh_time)}")
    print(f"   24h old message fresh? {is_message_fresh(old_time)}")

    # Test team extraction
    test_text = "Galatasaray XI for tonight: Muslera, Torreira, Icardi..."
    teams = extract_team_names_from_text(test_text)
    print(f"   Extracted teams from '{test_text[:40]}...': {teams}")

    print("\n✅ Test complete")
