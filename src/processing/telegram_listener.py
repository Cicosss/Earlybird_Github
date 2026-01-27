"""
Telegram Intelligence Listener

Monitors verified insider Telegram channels for squad/injury news.
Implements STRICT TIME-GATING to prevent "Time Hallucinations" (old news alerts).

CRITICAL FILTERS:
1. Message must be < 12 hours old
2. Team mentioned must have an UPCOMING match (next 48h)
3. If match was yesterday -> DROP (post-match commentary)
"""
import os
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto
from telethon.errors import ChannelPrivateError, ChannelInvalidError, UsernameNotOccupiedError
from src.database.models import TeamAlias, Match, SessionLocal
from src.analysis.image_ocr import process_squad_image, extract_player_names
from src.analysis.squad_analyzer import analyze_squad_list
from src.processing.sources_config import get_all_telegram_channels, TELEGRAM_INSIDERS

# ============================================
# TRUST SCORE INTEGRATION (V4.3)
# ============================================
try:
    from src.analysis.telegram_trust_score import (
        validate_telegram_message,
        get_first_odds_drop_time,
        detect_red_flags,
        track_odds_correlation,  # V4.3: Odds correlation tracking
        ChannelMetrics,
        TrustLevel,
        _get_text_hash
    )
    from src.database.telegram_channel_model import (
        init_telegram_tracking_db,
        get_or_create_channel,
        update_channel_metrics,
        log_telegram_message,
        get_channel_metrics,
        get_blacklisted_channels
    )
    _TRUST_SCORE_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Trust Score module not available: {e}")
    _TRUST_SCORE_AVAILABLE = False

load_dotenv()


# ============================================
# TAVILY INTEL VERIFICATION (V7.0)
# ============================================

async def _tavily_verify_intel(intel_text: str, team_name: str) -> Optional[Dict]:
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
        from src.ingestion.tavily_provider import get_tavily_provider
        from src.ingestion.tavily_budget import get_budget_manager
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder
        
        tavily = get_tavily_provider()
        budget = get_budget_manager()
        
        if not tavily or not tavily.is_available():
            return None
        
        if not budget or not budget.can_call("telegram_monitor"):
            logging.debug("📊 [TELEGRAM] Tavily budget limit reached")
            return None
        
        # Build verification query
        query = TavilyQueryBuilder.build_news_verification_query(
            news_title=intel_text[:200],
            team_name=team_name
        )
        
        # V7.1: Use native Tavily news parameters for better filtering
        response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
            topic="news",
            days=3
        )
        
        if response:
            budget.record_call("telegram_monitor")
            
            # Analyze response to determine confirmation/contradiction
            answer = (response.answer or "").lower()
            
            # Keywords indicating confirmation
            confirm_keywords = ["confirmed", "reports", "according to", "official", "announced"]
            # Keywords indicating contradiction
            contradict_keywords = ["denied", "false", "rumor", "unconfirmed", "no evidence", "not true"]
            
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
    val = os.getenv(key, '')
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        logging.warning(f"⚠️ Invalid {key} value '{val}', using default {default}")
        return default


API_ID = _safe_int_env('TELEGRAM_API_ID', 0)
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
SESSION_NAME = 'earlybird_monitor'

# ============================================
# TIME-GATING CONFIGURATION
# ============================================
MAX_MESSAGE_AGE_HOURS = 12      # Drop messages older than this
MATCH_LOOKAHEAD_HOURS = 48      # Only process if match in next N hours
MIN_MATCH_TIME_HOURS = 1        # Ignore if match already started

# Squad-related keywords (multi-language)
SQUAD_KEYWORDS = [
    'XI', '11', 'KADRO', 'ESCALAÇÃO', 'LINEUP', 'START',
    'FORMAZIONE', 'SKŁAD', 'CONVOCADOS', 'SQUAD',
    'STARTING', 'LINE UP', 'İLK 11', 'KADROSU',
    'SAKAT', 'SAKATLIK', 'INJURY', 'INJURED', 'OUT',
    'EKSIK', 'MISSING', 'RULED OUT', 'DOUBTFUL'
]

# Team name patterns for extraction (common suffixes to remove)
TEAM_SUFFIXES = ['FC', 'SK', 'AS', 'AC', 'FK', 'SC', 'CF', 'CD', 'SD', 'UD', 'RCD', 'CA']


def normalize_datetime(dt: datetime) -> datetime:
    """Convert datetime to naive UTC for comparison."""
    if dt.tzinfo is not None:
        # Convert to UTC then remove timezone
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_message_fresh(msg_date: datetime, max_age_hours: int = MAX_MESSAGE_AGE_HOURS) -> bool:
    """
    TIME-GATE #1: Check if message is fresh enough to process.
    
    Args:
        msg_date: Message timestamp
        max_age_hours: Maximum age in hours
        
    Returns:
        True if message is fresh, False if too old
    """
    now = datetime.now(timezone.utc)
    msg_time = normalize_datetime(msg_date)
    # Normalize 'now' to naive UTC for consistent comparison
    now_naive = now.replace(tzinfo=None)
    cutoff = now_naive - timedelta(hours=max_age_hours)
    
    return msg_time >= cutoff


def extract_team_names_from_text(text: str) -> List[str]:
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
    
    teams = []
    
    # Pattern 1: Words starting with capital letter (potential team names)
    # Match 2+ consecutive capitalized words
    pattern = r'\b([A-Z][a-zğüşıöçİĞÜŞÖÇ]+(?:\s+[A-Z][a-zğüşıöçİĞÜŞÖÇ]+)*)\b'
    matches = re.findall(pattern, text)
    
    for match in matches:
        # Clean up common suffixes
        clean_name = match
        for suffix in TEAM_SUFFIXES:
            if clean_name.endswith(f' {suffix}'):
                clean_name = clean_name[:-len(suffix)-1].strip()
        
        if len(clean_name) >= 3:  # Minimum 3 chars
            teams.append(clean_name)
    
    # Pattern 2: All-caps words (often team abbreviations or names)
    caps_pattern = r'\b([A-ZĞÜŞİÖÇ]{3,})\b'
    caps_matches = re.findall(caps_pattern, text)
    teams.extend(caps_matches)
    
    return list(set(teams))  # Remove duplicates


def has_upcoming_match(team_name: str, lookahead_hours: int = MATCH_LOOKAHEAD_HOURS) -> Tuple[bool, Optional[Match]]:
    """
    TIME-GATE #2: Check if team has an upcoming match in ELITE LEAGUES ONLY.
    
    This prevents processing old news about past matches AND
    filters out non-Elite leagues (Serie A, Premier League, etc.)
    
    Args:
        team_name: Team name to check
        lookahead_hours: Hours to look ahead
        
    Returns:
        Tuple of (has_match, match_object)
    """
    # Import Elite leagues for filtering
    from src.ingestion.league_manager import ELITE_LEAGUES
    from src.database.models import get_db_session
    
    try:
        with get_db_session() as db:
            now = datetime.now(timezone.utc)
            min_time = now + timedelta(hours=MIN_MATCH_TIME_HOURS)  # Match not started yet
            max_time = now + timedelta(hours=lookahead_hours)
            
            # Search for team in home or away
            team_lower = team_name.lower()
            
            matches = db.query(Match).filter(
                Match.start_time >= min_time,
                Match.start_time <= max_time
            ).all()
            
            for match in matches:
                home_lower = match.home_team.lower()
                away_lower = match.away_team.lower()
                
                # Fuzzy match: team name contained in home/away
                if (team_lower in home_lower or 
                    team_lower in away_lower or
                    home_lower in team_lower or
                    away_lower in team_lower):
                    
                    # ELITE FILTER: Only process matches from Elite leagues
                    match_league = match.league if hasattr(match, 'league') else None
                    if match_league and match_league not in ELITE_LEAGUES:
                        logging.debug(f"⏭️ Skipping non-Elite league: {match_league}")
                        continue
                    
                    return True, match
            
            return False, None
        
    except Exception as e:
        logging.error(f"Error checking upcoming match: {e}")
        return False, None


def should_process_message(msg_date: datetime, text: str) -> Tuple[bool, Optional[Match], str]:
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
    # Gate 1: Message freshness
    if not is_message_fresh(msg_date):
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        msg_naive = normalize_datetime(msg_date)
        age_hours = (now_naive - msg_naive).total_seconds() / 3600
        return False, None, f"Message too old ({age_hours:.1f}h > {MAX_MESSAGE_AGE_HOURS}h)"
    
    # Gate 2: Extract team names and check for upcoming matches
    team_names = extract_team_names_from_text(text)
    
    if not team_names:
        return False, None, "No team names detected in message"
    
    # Check each potential team name
    for team_name in team_names:
        has_match, match = has_upcoming_match(team_name)
        if has_match:
            return True, match, f"Team '{team_name}' has upcoming match"
    
    return False, None, f"No upcoming matches for detected teams: {team_names[:3]}"


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


async def fetch_squad_images(existing_client: TelegramClient = None) -> List[Dict]:
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
    if not existing_client and not os.path.exists(f'{SESSION_NAME}.session'):
        logging.error("❌ Session file not found. Please run: python setup_telegram_auth.py")
        return []
    
    results = []
    
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
        teams = []
        try:
            with get_db_session() as db:
                teams = db.query(TeamAlias).filter(TeamAlias.telegram_channel.isnot(None)).all()
                # Detach objects from session to use outside context
                teams = [{'api_name': t.api_name, 'search_name': t.search_name, 'telegram_channel': t.telegram_channel} for t in teams]
        except Exception as e:
            logging.warning(f"⚠️ Could not load team aliases: {e}")
        
        # Build channel list: insider channels + team-specific channels
        channels_to_monitor = []
        
        # Add insider channels
        for country, channels in all_channels.items():
            for channel in channels:
                channels_to_monitor.append({
                    'channel': channel,
                    'country': country,
                    'type': 'insider'
                })
        
        # Add team-specific channels
        for team in teams:
            channels_to_monitor.append({
                'channel': team['telegram_channel'],
                'team': team['api_name'],
                'search_name': team['search_name'],
                'type': 'team'
            })
        
        if not channels_to_monitor:
            logging.warning("No Telegram channels configured")
            await client.disconnect()
            return []
        
        logging.info(f"📡 Monitoring {len(channels_to_monitor)} Telegram channels...")
        
        # Create temp directory for images
        os.makedirs('./temp', exist_ok=True)
        
        # Stats for logging
        stats = {
            'channels_checked': 0,
            'channels_failed': 0,
            'channels_blacklisted': 0,
            'messages_checked': 0,
            'messages_dropped_old': 0,
            'messages_dropped_no_match': 0,
            'messages_dropped_low_trust': 0,
            'messages_processed': 0,
            'insider_hits': 0
        }
        
        # Loop through each channel
        for channel_info in channels_to_monitor:
            channel = channel_info['channel']
            
            # ROBUST CONNECTION: Safe entity retrieval
            entity = await get_channel_entity_safe(client, channel)
            
            if entity is None:
                stats['channels_failed'] += 1
                continue
            
            stats['channels_checked'] += 1
            logging.info(f"📡 Checking channel: @{channel}")
            
            try:
                # Fetch last 10 messages
                messages = await client.get_messages(entity, limit=10)
                
                for msg in messages:
                    stats['messages_checked'] += 1
                    
                    # ============================================
                    # DUAL MODE: TEXT + IMAGE OCR
                    # ============================================
                    # Step 1: Initialize with caption/text
                    caption_text = msg.message or msg.text or ''
                    full_text = caption_text
                    ocr_text = None
                    image_path = None
                    
                    # Step 2: If has image, download and OCR FIRST
                    # This allows us to use OCR text for time-gating
                    if msg.photo:
                        timestamp = int(msg.date.timestamp())
                        image_path = f'./temp/{channel}_{timestamp}.jpg'
                        
                        try:
                            await client.download_media(msg.photo, image_path)
                            logging.debug(f"📥 Downloaded image: {image_path}")
                            
                            # Extract text via OCR (use local file path)
                            ocr_text = process_squad_image(f"file://{os.path.abspath(image_path)}")
                            
                            if ocr_text:
                                # APPEND OCR text to full_text for analysis
                                full_text += f"\n[OCR]: {ocr_text}"
                                logging.debug(f"📸 OCR extracted {len(ocr_text)} chars")
                        except Exception as ocr_err:
                            logging.warning(f"OCR failed for {image_path}: {ocr_err}")
                    
                    # Step 3: TIME-GATING with COMBINED text (caption + OCR)
                    should_process, match, reason = should_process_message(msg.date, full_text)
                    
                    if not should_process:
                        if 'too old' in reason.lower():
                            stats['messages_dropped_old'] += 1
                        else:
                            stats['messages_dropped_no_match'] += 1
                        logging.debug(f"   ⏭️ Skipped: {reason}")
                        # Clean up downloaded image if not processing
                        if image_path and os.path.exists(image_path):
                            try:
                                os.remove(image_path)
                            except Exception as cleanup_err:
                                logging.debug(f"Could not remove temp image {image_path}: {cleanup_err}")
                        continue
                    
                    # Step 4: Check for squad keywords in COMBINED text
                    full_text_upper = full_text.upper()
                    has_keyword = any(keyword in full_text_upper for keyword in SQUAD_KEYWORDS)
                    
                    # Must have either keyword OR image with OCR content
                    if not has_keyword and not (msg.photo and ocr_text):
                        logging.debug(f"   ⏭️ No keywords and no useful OCR")
                        continue
                    
                    # Step 5: PROCESS - Message passed all gates
                    stats['messages_processed'] += 1
                    logging.info(f"🎯 Processing message from @{channel}")
                    logging.info(f"   Reason: {reason}")
                    logging.info(f"   Caption: {caption_text[:80]}..." if caption_text else "   Caption: (none)")
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
                            # Get or create channel record
                            channel_record = get_or_create_channel(channel, channel)
                            
                            # Check if channel is blacklisted
                            blacklisted = get_blacklisted_channels()
                            if channel in blacklisted:
                                logging.warning(f"   🚫 BLACKLISTED channel @{channel} - skipping")
                                stats['messages_dropped_no_match'] += 1
                                continue
                            
                            # Get first odds drop time for this match (if available)
                            first_drop_time = None
                            if match and hasattr(match, 'id'):
                                first_drop_time = get_first_odds_drop_time(match.id)
                            
                            # Load channel metrics for validation
                            channel_metrics_dict = get_channel_metrics(channel)
                            channel_metrics_obj = None
                            if channel_metrics_dict:
                                channel_metrics_obj = ChannelMetrics(
                                    channel_id=channel,
                                    channel_name=channel,
                                    total_messages=channel_metrics_dict.get('total_messages', 0),
                                    messages_with_odds_impact=channel_metrics_dict.get('insider_hits', 0) + channel_metrics_dict.get('late_messages', 0),
                                    insider_hits=channel_metrics_dict.get('insider_hits', 0),
                                    late_messages=channel_metrics_dict.get('late_messages', 0),
                                    echo_messages=channel_metrics_dict.get('echo_messages', 0),
                                    red_flags_count=channel_metrics_dict.get('red_flags_count', 0),
                                    trust_score=channel_metrics_dict.get('trust_score', 0.5)
                                )
                            
                            # Validate message
                            validation = validate_telegram_message(
                                channel_id=channel,
                                channel_name=channel,
                                message_text=full_text,
                                message_time=msg.date,
                                first_odds_drop_time=first_drop_time,
                                channel_metrics=channel_metrics_obj
                            )
                            
                            trust_multiplier = validation.trust_multiplier
                            trust_validation_reason = validation.reason
                            is_insider_hit = validation.is_insider_hit
                            
                            # Log validation result
                            if validation.is_valid:
                                logging.info(f"   🔐 Trust: {trust_multiplier:.2f} | {trust_validation_reason}")
                            else:
                                logging.warning(f"   ⚠️ Low Trust: {trust_multiplier:.2f} | {trust_validation_reason}")
                            
                            # Update channel metrics
                            update_channel_metrics(
                                channel_id=channel,
                                is_insider_hit=is_insider_hit,
                                is_late=validation.timestamp_lag_minutes and validation.timestamp_lag_minutes > 30,
                                is_echo=validation.is_echo,
                                red_flags=validation.red_flags,
                                timestamp_lag=validation.timestamp_lag_minutes
                            )
                            
                            # Log message for audit
                            log_telegram_message(
                                channel_id=channel,
                                message_id=str(msg.id) if hasattr(msg, 'id') else None,
                                text_hash=_get_text_hash(full_text),
                                text_preview=full_text[:200] if full_text else None,
                                message_time=msg.date,
                                match_id=match.id if match else None,
                                timestamp_lag=validation.timestamp_lag_minutes,
                                was_insider_hit=is_insider_hit,
                                is_echo=validation.is_echo,
                                trust_multiplier=trust_multiplier,
                                validation_reason=trust_validation_reason,
                                red_flags=validation.red_flags
                            )
                            
                            # V4.3: Track odds correlation for Trust Score V2
                            # This updates channel metrics with insider/follower classification
                            if match and hasattr(match, 'id') and msg.date:
                                try:
                                    lag_minutes = track_odds_correlation(
                                        channel_id=channel,
                                        message_time=msg.date,
                                        match_id=match.id
                                    )
                                    if lag_minutes is not None:
                                        if lag_minutes < 0:
                                            logging.info(f"   📊 INSIDER: Message {abs(lag_minutes):.0f}min BEFORE odds drop")
                                        elif lag_minutes <= 5:
                                            logging.debug(f"   📊 FAST: Message {lag_minutes:.0f}min after odds drop")
                                        else:
                                            logging.debug(f"   📊 LATE: Message {lag_minutes:.0f}min after odds drop")
                                except Exception as corr_err:
                                    logging.debug(f"   Odds correlation tracking error: {corr_err}")
                            
                            # Skip messages with very low trust
                            if trust_multiplier < 0.15:
                                logging.info(f"   ⏭️ Skipping low-trust message (multiplier: {trust_multiplier:.2f})")
                                continue
                            
                            # V7.0: Tavily verification for medium-trust channels (0.4-0.7)
                            if 0.4 <= trust_multiplier <= 0.7:
                                tavily_result = await _tavily_verify_intel(full_text, team_name)
                                if tavily_result:
                                    if tavily_result.get('confirmed'):
                                        # Tavily confirms - boost trust by 0.2
                                        trust_multiplier = min(1.0, trust_multiplier + 0.2)
                                        trust_validation_reason += " | Tavily CONFIRMED (+0.2)"
                                        logging.info(f"   🔍 Tavily confirmed intel, trust boosted to {trust_multiplier:.2f}")
                                    elif tavily_result.get('contradicted'):
                                        # Tavily contradicts - reduce trust by 0.1
                                        trust_multiplier = max(0.0, trust_multiplier - 0.1)
                                        trust_validation_reason += " | Tavily CONTRADICTED (-0.1)"
                                        logging.warning(f"   ⚠️ Tavily contradicted intel, trust reduced to {trust_multiplier:.2f}")
                                    # else: inconclusive - keep original trust
                                
                        except Exception as trust_err:
                            logging.warning(f"   ⚠️ Trust validation error: {trust_err}")
                            trust_multiplier = 0.5  # Default to neutral on error
                    
                    # Determine team info
                    team_name = channel_info.get('team', match.home_team if match else 'Unknown')
                    search_name = channel_info.get('search_name', team_name)
                    
                    results.append({
                        'team': team_name,
                        'team_search_name': search_name,
                        'image_path': image_path,
                        'ocr_text': ocr_text,
                        'caption': caption_text,
                        'full_text': full_text,  # Combined text for analysis
                        'timestamp': msg.date,
                        'channel': channel,
                        'match': match,
                        'channel_type': channel_info['type'],
                        'has_image': msg.photo is not None,
                        # V4.3: Trust Score fields
                        'trust_multiplier': trust_multiplier,
                        'trust_reason': trust_validation_reason,
                        'is_insider_hit': is_insider_hit
                    })
                    
            except Exception as e:
                logging.error(f"Error processing channel @{channel}: {e}")
                continue
        
        # Only disconnect if we created the client
        if should_disconnect:
            await client.disconnect()
        
        # Log stats
        logging.info(f"📊 Telegram Monitor Stats:")
        logging.info(f"   Channels: {stats['channels_checked']} checked, {stats['channels_failed']} failed, {stats['channels_blacklisted']} blacklisted")
        logging.info(f"   Messages: {stats['messages_checked']} checked")
        logging.info(f"   Dropped: {stats['messages_dropped_old']} old, {stats['messages_dropped_no_match']} no match, {stats['messages_dropped_low_trust']} low trust")
        logging.info(f"   Processed: {stats['messages_processed']} | Insider Hits: {stats['insider_hits']}")
        logging.info(f"✅ Found {len(results)} relevant items")
        
        return results
        
    except Exception as e:
        import traceback
        logging.error(f"Critical error in Telegram listener: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return []


async def monitor_channels_for_squads(existing_client: TelegramClient = None) -> List[Dict]:
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
    
    alerts = []
    
    for squad in squad_images:
        # Get combined text for analysis
        full_text = squad.get('full_text', squad.get('caption', ''))
        has_image = squad.get('has_image', False)
        ocr_text = squad.get('ocr_text')
        
        # ============================================
        # DUAL MODE PROCESSING
        # ============================================
        
        if has_image and ocr_text:
            # MODE 1: Image with OCR - Full squad analysis
            logging.info(f"📸 Analyzing squad image from @{squad['channel']}")
            
            alert = analyze_squad_list(
                image_url=squad['image_path'],
                team_name=squad['team_search_name'],
                match_id=f"telegram_{squad['channel']}_{int(squad['timestamp'].timestamp())}"
            )
            
            if alert:
                alert['source'] = 'TELEGRAM_CHANNEL'
                alert['channel'] = squad['channel']
                alert['channel_type'] = squad.get('channel_type', 'unknown')
                alert['match'] = squad.get('match')
                alert['mode'] = 'IMAGE_OCR'
                alerts.append(alert)
                logging.info(f"🚨 ALERT (IMAGE): {alert['summary']}")
            else:
                # Even if no missing players, report the lineup detection
                caption_preview = squad.get('caption', '')[:100]
                ocr_preview = ocr_text[:100] if ocr_text else ''
                
                alerts.append({
                    'summary': f"📋 Squad list detected from @{squad['channel']}: {caption_preview or ocr_preview}",
                    'score': 5,  # Informational
                    'url': f"https://t.me/{squad['channel']}",
                    'source': 'TELEGRAM_CHANNEL',
                    'channel': squad['channel'],
                    'channel_type': squad.get('channel_type', 'unknown'),
                    'match': squad.get('match'),
                    'mode': 'IMAGE_OCR',
                    'ocr_text': ocr_text
                })
                
        elif has_image and not ocr_text:
            # MODE 2: Image without OCR (OCR failed) - Report with caption only
            caption = squad.get('caption', '')
            if caption:
                alerts.append({
                    'summary': f"📷 Image posted by @{squad['channel']}: {caption[:200]}",
                    'score': 4,  # Lower score - OCR failed
                    'url': f"https://t.me/{squad['channel']}",
                    'source': 'TELEGRAM_CHANNEL',
                    'channel': squad['channel'],
                    'channel_type': squad.get('channel_type', 'unknown'),
                    'match': squad.get('match'),
                    'mode': 'IMAGE_NO_OCR'
                })
                
        else:
            # MODE 3: Text-only message
            caption = squad.get('caption', '')
            if caption:
                alerts.append({
                    'summary': f"📢 Intel from @{squad['channel']}: {caption[:200]}",
                    'score': 6,  # Medium score for text intel
                    'url': f"https://t.me/{squad['channel']}",
                    'source': 'TELEGRAM_CHANNEL',
                    'channel': squad['channel'],
                    'channel_type': squad.get('channel_type', 'unknown'),
                    'match': squad.get('match'),
                    'mode': 'TEXT_ONLY'
                })
    
    # Log summary
    image_alerts = len([a for a in alerts if a.get('mode') == 'IMAGE_OCR'])
    text_alerts = len([a for a in alerts if a.get('mode') == 'TEXT_ONLY'])
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
    import asyncio
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
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
