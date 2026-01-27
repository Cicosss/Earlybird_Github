"""
EarlyBird Telegram Trust Score Module V1.0

Validates Telegram insider channels algorithmically to filter out
the 95% of "Fixed Match" / "Insider" channels that are scams.

VALIDATION METRICS:
1. Timestamp Lag: Does the message ANTICIPATE odds movement? (True insider)
   - T_msg < T_drop → REAL INSIDER (info before market)
   - T_msg > T_drop → FAKE GURU (commenting after the fact)

2. Edit/Delete Ratio: Does the channel modify messages post-match?
   - High edit rate → UNTRUSTWORTHY (hiding wrong predictions)

3. Echo Chamber Detection: Is this channel just copying others?
   - Same message within 2 min of another channel → AGGREGATOR (ignore)

4. Red Flags: Automatic disqualification keywords
   - "Fixed", "100% Safe", "Mafia", "Max Bet" → SCAM

Reference: Deep Research Report Section 24
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

# Timestamp Lag thresholds (minutes)
TIMESTAMP_LAG_INSIDER_THRESHOLD = 0      # Message before odds drop = insider
TIMESTAMP_LAG_FAST_FOLLOWER = 5          # Within 5 min = fast follower (acceptable)
TIMESTAMP_LAG_LATE_THRESHOLD = 30        # > 30 min after drop = late (suspicious)

# Trust Score weights
WEIGHT_TIMESTAMP_LAG = 0.40              # 40% of score
WEIGHT_EDIT_RATIO = 0.25                 # 25% of score
WEIGHT_ACCURACY = 0.25                   # 25% of score (historical accuracy)
WEIGHT_RED_FLAGS = 0.10                  # 10% penalty for red flags

# Minimum messages to calculate trust score
MIN_MESSAGES_FOR_TRUST = 5

# Edit/Delete thresholds
MAX_ACCEPTABLE_EDIT_RATIO = 0.10         # Max 10% edits acceptable
MAX_ACCEPTABLE_DELETE_RATIO = 0.05       # Max 5% deletes acceptable

# Echo Chamber detection window (seconds)
ECHO_CHAMBER_WINDOW_SECONDS = 120        # 2 minutes


class TrustLevel(Enum):
    """Trust level classification for Telegram channels."""
    VERIFIED = "VERIFIED"       # Trust Score >= 0.80
    TRUSTED = "TRUSTED"         # Trust Score >= 0.60
    NEUTRAL = "NEUTRAL"         # Trust Score >= 0.40
    SUSPICIOUS = "SUSPICIOUS"   # Trust Score >= 0.20
    BLACKLISTED = "BLACKLISTED" # Trust Score < 0.20 or red flags


@dataclass
class ChannelMetrics:
    """Metrics tracked for each Telegram channel."""
    channel_id: str
    channel_name: str
    
    # Message counts
    total_messages: int = 0
    messages_with_odds_impact: int = 0  # Messages that preceded odds movement
    
    # Timestamp lag stats
    avg_timestamp_lag_minutes: float = 0.0  # Negative = before odds drop (good)
    insider_hits: int = 0                    # Messages that anticipated market
    late_messages: int = 0                   # Messages after market moved
    
    # Edit/Delete tracking
    total_edits: int = 0
    total_deletes: int = 0
    
    # Accuracy tracking (for channels that make predictions)
    predictions_made: int = 0
    predictions_correct: int = 0
    
    # Red flags detected
    red_flags_count: int = 0
    red_flag_types: List[str] = field(default_factory=list)
    
    # Echo chamber
    echo_messages: int = 0  # Messages that were copies of other channels
    
    # Computed scores
    trust_score: float = 0.5  # Default neutral
    trust_level: TrustLevel = TrustLevel.NEUTRAL
    
    # Timestamps
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageValidation:
    """Result of validating a single Telegram message."""
    is_valid: bool
    trust_multiplier: float  # 0.0 to 1.0, applied to news impact
    reason: str
    timestamp_lag_minutes: Optional[float] = None
    is_insider_hit: bool = False
    red_flags: List[str] = field(default_factory=list)
    is_echo: bool = False


# ============================================
# RED FLAG DETECTION
# ============================================

# Keywords that indicate scam channels (multi-language)
RED_FLAG_KEYWORDS = [
    # English
    "fixed match", "100% safe", "100% sure", "guaranteed win",
    "mafia", "max bet", "all in", "insider tip", "vip tip",
    "free fixed", "paid fixed", "contact admin",
    # Italian
    "partita fissa", "sicuro al 100%", "scommessa sicura",
    # Turkish
    "şikeli maç", "kesin kazanç", "garanti",
    # Spanish
    "partido arreglado", "apuesta segura",
    # Portuguese
    "jogo combinado", "aposta certa",
]

# Patterns that indicate promotional/scam content
RED_FLAG_PATTERNS = [
    r"@\w+\s*(for|per|para)\s*(vip|premium|paid)",  # "Contact @admin for VIP"
    r"(telegram|whatsapp|signal)\s*:?\s*\+?\d{10,}",  # Phone numbers
    r"(deposit|deposito|depósito)\s*\d+",  # Deposit requests
    r"(odds?|quota)\s*[>≥]\s*[5-9]\d*",  # Unrealistic odds claims
    r"(win|vinto|ganado)\s*\d{2,}\s*(in a row|consecutive|di fila)",  # Fake streaks
]


def detect_red_flags(text: str) -> List[str]:
    """
    Detect red flags in message text that indicate scam/fake channels.
    
    Args:
        text: Message text to analyze
        
    Returns:
        List of detected red flag types
    """
    if not text:
        return []
    
    text_lower = text.lower()
    flags = []
    
    # Check keywords
    for keyword in RED_FLAG_KEYWORDS:
        if keyword in text_lower:
            flags.append(f"KEYWORD:{keyword}")
    
    # Check patterns
    for pattern in RED_FLAG_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            flags.append(f"PATTERN:{pattern[:20]}")
    
    return flags


# ============================================
# TIMESTAMP LAG ANALYSIS
# ============================================

def calculate_timestamp_lag(
    message_time: datetime,
    first_odds_drop_time: Optional[datetime]
) -> Tuple[float, bool]:
    """
    Calculate the lag between message timestamp and first odds movement.
    
    CRITICAL INSIGHT: True insiders post BEFORE the market moves.
    Fake gurus post AFTER the market has already reacted.
    
    Args:
        message_time: When the Telegram message was posted
        first_odds_drop_time: When odds first dropped significantly (from odds_snapshots)
        
    Returns:
        Tuple of (lag_minutes, is_insider_hit)
        - Negative lag = message before odds drop (INSIDER)
        - Positive lag = message after odds drop (FOLLOWER)
    """
    # Edge case: No message time
    if not message_time:
        return 0.0, False
    
    if not first_odds_drop_time:
        # No odds data available - can't validate
        return 0.0, False
    
    # Normalize timezones
    if message_time.tzinfo is None:
        message_time = message_time.replace(tzinfo=timezone.utc)
    if first_odds_drop_time.tzinfo is None:
        first_odds_drop_time = first_odds_drop_time.replace(tzinfo=timezone.utc)
    
    # Calculate lag in minutes
    delta = (message_time - first_odds_drop_time).total_seconds() / 60
    
    # Insider hit = message came BEFORE odds dropped
    is_insider = delta < TIMESTAMP_LAG_INSIDER_THRESHOLD
    
    return delta, is_insider


# ============================================
# ECHO CHAMBER DETECTION
# ============================================

# In-memory cache for recent messages (for echo detection)
# Key: hash of normalized text, Value: (channel_id, timestamp)
_recent_messages_cache: Dict[str, Tuple[str, datetime]] = {}
_CACHE_MAX_SIZE = 1000
_CACHE_TTL_SECONDS = 3600  # FIX: 1 hour TTL to prevent memory leak


def _normalize_text_for_echo(text: str) -> str:
    """Normalize text for echo comparison (remove whitespace, lowercase)."""
    if not text:
        return ""
    # Remove extra whitespace, lowercase, remove common filler words
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    # Remove emojis and special chars for comparison
    normalized = re.sub(r'[^\w\s]', '', normalized)
    return normalized


def _get_text_hash(text: str) -> str:
    """Get hash of normalized text for echo detection."""
    import hashlib
    normalized = _normalize_text_for_echo(text)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def check_echo_chamber(
    channel_id: str,
    message_text: str,
    message_time: datetime
) -> Tuple[bool, Optional[str]]:
    """
    Check if this message is an echo (copy) of a recent message from another channel.
    
    Args:
        channel_id: Source channel ID
        message_text: Message text
        message_time: Message timestamp
        
    Returns:
        Tuple of (is_echo, original_channel_id)
    """
    global _recent_messages_cache
    
    if not message_text or len(message_text) < 20:
        # Too short to be meaningful echo
        return False, None
    
    text_hash = _get_text_hash(message_text)
    
    # Normalize message_time timezone
    if message_time.tzinfo is None:
        message_time = message_time.replace(tzinfo=timezone.utc)
    
    # Check if we've seen this text recently from another channel
    if text_hash in _recent_messages_cache:
        original_channel, original_time = _recent_messages_cache[text_hash]
        
        # Normalize original_time timezone
        if original_time.tzinfo is None:
            original_time = original_time.replace(tzinfo=timezone.utc)
        
        # Different channel posted same content?
        if original_channel != channel_id:
            time_diff = abs((message_time - original_time).total_seconds())
            
            if time_diff <= ECHO_CHAMBER_WINDOW_SECONDS:
                logger.debug(f"Echo detected: {channel_id} copied from {original_channel}")
                return True, original_channel
    
    # Add to cache
    _recent_messages_cache[text_hash] = (channel_id, message_time)
    
    # FIX: Cleanup expired entries (TTL-based) + size limit
    now = datetime.now(timezone.utc)
    expired_keys = []
    
    for key, (_, entry_time) in _recent_messages_cache.items():
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        age_seconds = (now - entry_time).total_seconds()
        if age_seconds > _CACHE_TTL_SECONDS:
            expired_keys.append(key)
    
    # Remove expired entries
    for key in expired_keys:
        del _recent_messages_cache[key]
    
    # If still too large after TTL cleanup, remove oldest 20%
    if len(_recent_messages_cache) > _CACHE_MAX_SIZE:
        sorted_items = sorted(
            _recent_messages_cache.items(),
            key=lambda x: x[1][1] if x[1][1].tzinfo else x[1][1].replace(tzinfo=timezone.utc)
        )
        for key, _ in sorted_items[:int(_CACHE_MAX_SIZE * 0.2)]:
            del _recent_messages_cache[key]
    
    return False, None


# ============================================
# TRUST SCORE CALCULATION
# ============================================

def calculate_trust_score(metrics: ChannelMetrics) -> Tuple[float, TrustLevel]:
    """
    Calculate overall trust score for a channel based on its metrics.
    
    Formula:
    - 40% Timestamp Lag Score (insider hits vs late messages)
    - 25% Edit/Delete Score (low edit ratio = trustworthy)
    - 25% Accuracy Score (if predictions tracked)
    - 10% Red Flag Penalty
    
    Args:
        metrics: Channel metrics
        
    Returns:
        Tuple of (trust_score 0-1, trust_level)
    """
    # Not enough data - return neutral
    if metrics.total_messages < MIN_MESSAGES_FOR_TRUST:
        return 0.5, TrustLevel.NEUTRAL
    
    # 1. Timestamp Lag Score (0-1)
    # Higher score = more insider hits, fewer late messages
    if metrics.messages_with_odds_impact > 0:
        insider_ratio = metrics.insider_hits / metrics.messages_with_odds_impact
        late_ratio = metrics.late_messages / metrics.messages_with_odds_impact
        timestamp_score = (insider_ratio * 1.0) - (late_ratio * 0.5)
        timestamp_score = max(0, min(1, timestamp_score))
    else:
        timestamp_score = 0.5  # Neutral if no odds impact data
    
    # 2. Edit/Delete Score (0-1)
    # Lower edit/delete ratio = higher score
    if metrics.total_messages > 0:
        edit_ratio = metrics.total_edits / metrics.total_messages
        delete_ratio = metrics.total_deletes / metrics.total_messages
        
        edit_score = 1.0 - min(1.0, edit_ratio / MAX_ACCEPTABLE_EDIT_RATIO)
        delete_score = 1.0 - min(1.0, delete_ratio / MAX_ACCEPTABLE_DELETE_RATIO)
        edit_delete_score = (edit_score + delete_score) / 2
    else:
        edit_delete_score = 0.5
    
    # 3. Accuracy Score (0-1)
    if metrics.predictions_made >= 5:
        accuracy_score = metrics.predictions_correct / metrics.predictions_made
    else:
        accuracy_score = 0.5  # Neutral if not enough predictions
    
    # 4. Red Flag Penalty (0-1, where 1 = no flags)
    red_flag_penalty = max(0, 1.0 - (metrics.red_flags_count * 0.2))
    
    # 5. Echo Chamber Penalty
    if metrics.total_messages > 0:
        echo_ratio = metrics.echo_messages / metrics.total_messages
        echo_penalty = max(0, 1.0 - (echo_ratio * 2))  # Heavy penalty for echoes
    else:
        echo_penalty = 1.0
    
    # Weighted combination
    trust_score = (
        (timestamp_score * WEIGHT_TIMESTAMP_LAG) +
        (edit_delete_score * WEIGHT_EDIT_RATIO) +
        (accuracy_score * WEIGHT_ACCURACY) +
        (red_flag_penalty * WEIGHT_RED_FLAGS)
    ) * echo_penalty
    
    # Clamp to 0-1
    trust_score = max(0, min(1, trust_score))
    
    # Determine trust level
    if metrics.red_flags_count >= 3 or trust_score < 0.20:
        trust_level = TrustLevel.BLACKLISTED
    elif trust_score >= 0.80:
        trust_level = TrustLevel.VERIFIED
    elif trust_score >= 0.60:
        trust_level = TrustLevel.TRUSTED
    elif trust_score >= 0.40:
        trust_level = TrustLevel.NEUTRAL
    else:
        trust_level = TrustLevel.SUSPICIOUS
    
    return trust_score, trust_level


# V4.3: Alias for backward compatibility and clarity
calculate_trust_score_v2 = calculate_trust_score


# ============================================
# MESSAGE VALIDATION (Main Entry Point)
# ============================================

def validate_telegram_message(
    channel_id: str,
    channel_name: str,
    message_text: str,
    message_time: datetime,
    first_odds_drop_time: Optional[datetime] = None,
    channel_metrics: Optional[ChannelMetrics] = None
) -> MessageValidation:
    """
    Validate a single Telegram message and return trust multiplier.
    
    This is the main entry point called by telegram_listener.py
    
    Args:
        channel_id: Telegram channel ID
        channel_name: Channel username
        message_text: Message content
        message_time: When message was posted
        first_odds_drop_time: When odds first moved (from market_intelligence)
        channel_metrics: Pre-loaded channel metrics (optional)
        
    Returns:
        MessageValidation with trust multiplier and validation details
    """
    # 1. Check red flags first (instant disqualification)
    red_flags = detect_red_flags(message_text)
    if len(red_flags) >= 2:
        return MessageValidation(
            is_valid=False,
            trust_multiplier=0.0,
            reason=f"RED FLAGS DETECTED: {', '.join(red_flags[:3])}",
            red_flags=red_flags
        )
    
    # 2. Check echo chamber
    is_echo, original_channel = check_echo_chamber(channel_id, message_text, message_time)
    if is_echo:
        return MessageValidation(
            is_valid=False,
            trust_multiplier=0.1,  # Very low multiplier for echoes
            reason=f"ECHO: Copied from @{original_channel}",
            is_echo=True
        )
    
    # 3. Calculate timestamp lag
    lag_minutes, is_insider = calculate_timestamp_lag(message_time, first_odds_drop_time)
    
    # 4. Determine trust multiplier based on lag
    if is_insider:
        # Message came BEFORE odds moved - true insider!
        trust_multiplier = 1.0
        reason = f"✅ INSIDER: Message {abs(lag_minutes):.0f}min BEFORE odds drop"
    elif lag_minutes <= TIMESTAMP_LAG_FAST_FOLLOWER:
        # Fast follower - acceptable
        trust_multiplier = 0.8
        reason = f"⚡ FAST: Message {lag_minutes:.0f}min after odds drop"
    elif lag_minutes <= TIMESTAMP_LAG_LATE_THRESHOLD:
        # Moderate delay - reduce trust
        trust_multiplier = 0.5
        reason = f"⏰ DELAYED: Message {lag_minutes:.0f}min after odds drop"
    else:
        # Very late - likely just commenting on known info
        trust_multiplier = 0.2
        reason = f"📜 LATE: Message {lag_minutes:.0f}min after odds drop (stale)"
    
    # 5. Apply channel trust score if available
    if channel_metrics:
        channel_trust = channel_metrics.trust_score
        trust_multiplier *= channel_trust
        
        if channel_metrics.trust_level == TrustLevel.BLACKLISTED:
            return MessageValidation(
                is_valid=False,
                trust_multiplier=0.0,
                reason=f"BLACKLISTED CHANNEL: {channel_name}",
                timestamp_lag_minutes=lag_minutes,
                red_flags=red_flags
            )
        elif channel_metrics.trust_level == TrustLevel.VERIFIED:
            trust_multiplier = min(1.0, trust_multiplier * 1.2)  # Boost verified channels
    
    # 6. Apply red flag penalty (if any flags but not disqualified)
    if red_flags:
        trust_multiplier *= (1.0 - len(red_flags) * 0.15)
        reason += f" | ⚠️ {len(red_flags)} red flag(s)"
    
    # Clamp final multiplier
    trust_multiplier = max(0.0, min(1.0, trust_multiplier))
    
    return MessageValidation(
        is_valid=trust_multiplier > 0.1,
        trust_multiplier=trust_multiplier,
        reason=reason,
        timestamp_lag_minutes=lag_minutes,
        is_insider_hit=is_insider,
        red_flags=red_flags,
        is_echo=False
    )


# ============================================
# HELPER: Get First Odds Drop Time
# ============================================

def get_first_odds_drop_time(
    match_id: str,
    threshold_pct: float = 3.0
) -> Optional[datetime]:
    """
    Get the timestamp of the first significant odds drop for a match.
    
    Uses odds_snapshots table from market_intelligence module.
    
    Args:
        match_id: Match ID to check
        threshold_pct: Minimum % drop to consider significant
        
    Returns:
        Datetime of first significant drop, or None
    """
    try:
        from src.analysis.market_intelligence import get_odds_history
        
        snapshots = get_odds_history(match_id, hours_back=48)
        
        if len(snapshots) < 2:
            return None
        
        # Find first significant drop
        for i in range(1, len(snapshots)):
            prev = snapshots[i-1]
            curr = snapshots[i]
            
            # Check home odds drop
            if prev.home_odd and curr.home_odd and prev.home_odd > 0:
                drop_pct = ((prev.home_odd - curr.home_odd) / prev.home_odd) * 100
                if drop_pct >= threshold_pct:
                    return curr.timestamp
            
            # Check away odds drop
            if prev.away_odd and curr.away_odd and prev.away_odd > 0:
                drop_pct = ((prev.away_odd - curr.away_odd) / prev.away_odd) * 100
                if drop_pct >= threshold_pct:
                    return curr.timestamp
        
        return None
        
    except ImportError:
        logger.debug("market_intelligence module not available")
        return None
    except Exception as e:
        logger.warning(f"Error getting first odds drop time: {e}")
        return None


# ============================================
# V4.3: ODDS CORRELATION TRACKING
# ============================================

def track_odds_correlation(
    channel_id: str,
    message_time: datetime,
    match_id: str,
    threshold_pct: float = 3.0
) -> Optional[float]:
    """
    V4.3: Track correlation between Telegram message timing and odds movement.
    
    This is the core of Trust Score V2 - it determines if a channel
    ANTICIPATES market movements (true insider) or just FOLLOWS them (fake guru).
    
    Algorithm:
    1. Get first significant odds drop for the match
    2. Calculate lag: message_time - first_drop_time
    3. Negative lag = INSIDER (message before drop)
    4. Positive lag = FOLLOWER (message after drop)
    5. Update channel metrics in database
    
    Args:
        channel_id: Telegram channel ID
        message_time: When the message was posted
        match_id: Match ID to correlate with
        threshold_pct: Minimum % drop to consider significant (default 3%)
        
    Returns:
        Lag in minutes (negative = insider, positive = follower), or None if no data
    """
    # Edge case: missing required parameters
    if not channel_id or not match_id:
        logger.debug("track_odds_correlation: missing channel_id or match_id")
        return None
    
    if not message_time:
        logger.debug("track_odds_correlation: missing message_time")
        return None
    
    try:
        # Get first significant odds drop
        first_drop_time = get_first_odds_drop_time(match_id, threshold_pct)
        
        if not first_drop_time:
            # No significant drop found - can't correlate
            logger.debug(f"No significant odds drop found for match {match_id}")
            return None
        
        # Calculate timestamp lag
        lag_minutes, is_insider = calculate_timestamp_lag(message_time, first_drop_time)
        
        # Determine if late (>30 min after drop)
        is_late = lag_minutes > TIMESTAMP_LAG_LATE_THRESHOLD
        
        # Update channel metrics in database
        try:
            from src.database.telegram_channel_model import update_channel_metrics
            
            update_channel_metrics(
                channel_id=channel_id,
                is_insider_hit=is_insider,
                is_late=is_late,
                timestamp_lag=lag_minutes
            )
            
            logger.debug(
                f"Odds correlation tracked: channel={channel_id}, "
                f"lag={lag_minutes:.1f}min, insider={is_insider}, late={is_late}"
            )
            
        except ImportError:
            logger.warning("telegram_channel_model not available for metrics update")
        except Exception as e:
            logger.warning(f"Failed to update channel metrics: {e}")
        
        return lag_minutes
        
    except Exception as e:
        logger.error(f"Error tracking odds correlation: {e}")
        return None


def get_channel_trust_metrics(channel_id: str) -> Optional[ChannelMetrics]:
    """
    V4.3: Load channel metrics from database for trust calculation.
    
    Args:
        channel_id: Telegram channel ID
        
    Returns:
        ChannelMetrics object or None if not found
    """
    try:
        from src.database.telegram_channel_model import get_channel_metrics
        
        metrics_dict = get_channel_metrics(channel_id)
        
        if not metrics_dict:
            return None
        
        # FIX: Safe TrustLevel parsing with fallback
        trust_level_str = metrics_dict.get('trust_level', 'NEUTRAL')
        try:
            trust_level = TrustLevel(trust_level_str)
        except ValueError:
            logger.warning(f"Invalid trust_level '{trust_level_str}' for channel {channel_id}, defaulting to NEUTRAL")
            trust_level = TrustLevel.NEUTRAL
        
        return ChannelMetrics(
            channel_id=metrics_dict.get('channel_id', channel_id),
            channel_name=metrics_dict.get('channel_name', 'unknown'),
            total_messages=metrics_dict.get('total_messages', 0),
            messages_with_odds_impact=metrics_dict.get('insider_hits', 0) + metrics_dict.get('late_messages', 0),
            avg_timestamp_lag_minutes=metrics_dict.get('avg_timestamp_lag', 0.0),
            insider_hits=metrics_dict.get('insider_hits', 0),
            late_messages=metrics_dict.get('late_messages', 0),
            echo_messages=metrics_dict.get('echo_messages', 0),
            red_flags_count=metrics_dict.get('red_flags_count', 0),
            trust_score=metrics_dict.get('trust_score', 0.5),
            trust_level=trust_level
        )
        
    except ImportError:
        logger.debug("telegram_channel_model not available")
        return None
    except Exception as e:
        logger.warning(f"Error loading channel metrics: {e}")
        return None


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("🔍 TELEGRAM TRUST SCORE MODULE V4.3 TEST")
    print("=" * 60)
    
    # Test red flag detection
    print("\n📛 Testing Red Flag Detection:")
    test_texts = [
        "Galatasaray XI: Muslera, Torreira...",  # Clean
        "100% SAFE BET! Fixed match insider tip!",  # Scam
        "Contact @admin for VIP tips, deposit 50$",  # Scam
        "Team news: Icardi ruled out with injury",  # Clean
    ]
    
    for text in test_texts:
        flags = detect_red_flags(text)
        status = "🚨 SCAM" if flags else "✅ CLEAN"
        print(f"   {status}: '{text[:40]}...' → {flags}")
    
    # Test timestamp lag
    print("\n⏱️ Testing Timestamp Lag:")
    now = datetime.now(timezone.utc)
    
    test_cases = [
        (now - timedelta(minutes=10), now, "Message 10min BEFORE drop"),
        (now, now - timedelta(minutes=10), "Message 10min AFTER drop"),
        (now, now - timedelta(minutes=60), "Message 60min AFTER drop"),
    ]
    
    for msg_time, drop_time, desc in test_cases:
        lag, is_insider = calculate_timestamp_lag(msg_time, drop_time)
        status = "✅ INSIDER" if is_insider else "❌ FOLLOWER"
        print(f"   {status}: {desc} → lag={lag:.0f}min")
    
    # Test full validation
    print("\n🔐 Testing Full Validation:")
    validation = validate_telegram_message(
        channel_id="test_channel",
        channel_name="TestChannel",
        message_text="Galatasaray starting XI confirmed: Muslera in goal",
        message_time=now - timedelta(minutes=5),
        first_odds_drop_time=now
    )
    
    print(f"   Valid: {validation.is_valid}")
    print(f"   Trust Multiplier: {validation.trust_multiplier:.2f}")
    print(f"   Reason: {validation.reason}")
    print(f"   Insider Hit: {validation.is_insider_hit}")
    
    # V4.3: Test odds correlation tracking
    print("\n📊 V4.3 - Testing Odds Correlation Tracking:")
    print("   (Requires database connection - skipping in standalone test)")
    print("   Function: track_odds_correlation(channel_id, message_time, match_id)")
    print("   - Returns lag in minutes (negative = insider)")
    print("   - Updates channel metrics in telegram_channels table")
    print("   - Classifies: INSIDER (<0min), FAST (0-5min), DELAYED (5-30min), LATE (>30min)")
    
    print("\n✅ Test complete")
