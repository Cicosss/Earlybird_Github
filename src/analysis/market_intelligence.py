"""
EarlyBird Market Intelligence Module V1.1

Advanced market analysis features:
1. Steam Move Detection - Rapid odds movements in short time windows
2. Reverse Line Movement - Smart money going against public betting
3. News Decay - Exponential decay of news impact over time

These signals integrate with the existing Sharp Money detection
to provide a more complete picture of market dynamics.

V1.1 Changes:
- Fix #9: Standardized logging to use module logger pattern
- Fix #4: Added edge case protection for odds <= 1.0 in RLM V1
- Fix #6: Improved public_bet estimation for away favorites
- Fix #5: Calculate time_window_min from odds_snapshots
- Fix #3/8: Aligned freshness tags with news_hunter.py constants
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from sqlalchemy import Column, String, Integer, DateTime, Float, Index, create_engine, event
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, engine, SessionLocal, Match

# ============================================
# ODDS SNAPSHOT MODEL (Historical Tracking)
# ============================================

class OddsSnapshot(Base):
    """
    Stores historical odds snapshots for time-based analysis.
    Each snapshot captures odds at a specific moment in time.
    """
    __tablename__ = 'odds_snapshots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # H2H Odds at this snapshot
    home_odd = Column(Float, nullable=True)
    draw_odd = Column(Float, nullable=True)
    away_odd = Column(Float, nullable=True)
    
    # Sharp bookie odds (for steam move detection)
    sharp_home_odd = Column(Float, nullable=True)
    sharp_draw_odd = Column(Float, nullable=True)
    sharp_away_odd = Column(Float, nullable=True)
    
    # Source bookmaker
    sharp_bookie = Column(String, nullable=True)
    
    # Composite index for efficient time-range queries
    __table_args__ = (
        Index('idx_snapshot_match_time', 'match_id', 'timestamp'),
    )


# ============================================
# CONFIGURATION
# ============================================

# Steam Move Detection
STEAM_MOVE_THRESHOLD_PCT = 5.0      # Minimum % drop to consider "steam"
STEAM_MOVE_TIME_WINDOW_MIN = 15     # Time window in minutes (uniform for Elite 7)
STEAM_MOVE_RAPID_WINDOW_MIN = 5     # Rapid steam (very aggressive)

# Reverse Line Movement
RLM_PUBLIC_THRESHOLD = 0.65         # 65%+ public on one side
RLM_ODDS_INCREASE_THRESHOLD = 0.03  # Odds must increase by 3%+ despite public money
RLM_MIN_VALID_ODD = 1.01            # Fix #4: Minimum valid odd (odds are always > 1.0)

# News Decay - V4.3: Now league-adaptive (see get_news_decay_lambda in settings.py)
# Default values for backward compatibility
NEWS_DECAY_LAMBDA = 0.05            # Default decay rate (overridden by league-specific)
NEWS_DECAY_HALF_LIFE_MIN = 14       # Default half-life in minutes
NEWS_MAX_AGE_HOURS = 24             # News older than this has near-zero impact

# ============================================
# FRESHNESS MODULE (V7.0 - Centralized)
# ============================================
# Now uses src/utils/freshness.py as single source of truth
try:
    from src.utils.freshness import (
        get_freshness_tag as _central_freshness_tag,
        FRESHNESS_FRESH_THRESHOLD_MIN,
        FRESHNESS_AGING_THRESHOLD_MIN,
        calculate_decay_multiplier,
        get_league_decay_rate
    )
    _FRESHNESS_MODULE_AVAILABLE = True
except ImportError:
    _FRESHNESS_MODULE_AVAILABLE = False
    # Fallback constants if module not available
    FRESHNESS_FRESH_THRESHOLD_MIN = 60
    FRESHNESS_AGING_THRESHOLD_MIN = 360


def get_steam_window_for_league(league_key: str) -> int:
    """
    Get Steam Move time window for a league.
    
    All monitored leagues (Elite 7) are niche markets with slower reaction.
    Using uniform 15 min window for all.
    
    Args:
        league_key: League identifier (not used, kept for API compatibility)
        
    Returns:
        Time window in minutes (15 for all leagues)
    """
    return STEAM_MOVE_TIME_WINDOW_MIN


# ============================================
# STEAM MOVE DETECTION
# ============================================

@dataclass
class SteamMoveSignal:
    """Result of steam move detection."""
    detected: bool
    market: str
    drop_pct: float
    time_window_min: int
    start_odds: float
    end_odds: float
    is_rapid: bool
    confidence: str
    message: str


def get_odds_history(match_id: str, hours_back: int = 24) -> List[OddsSnapshot]:
    """
    Fetch odds history for a match within the specified time window.
    
    Args:
        match_id: Match ID to query
        hours_back: How many hours of history to fetch
        
    Returns:
        List of OddsSnapshot ordered by timestamp (oldest first)
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        cutoff_naive = cutoff.replace(tzinfo=None)
        
        snapshots = db.query(OddsSnapshot).filter(
            OddsSnapshot.match_id == match_id,
            OddsSnapshot.timestamp >= cutoff_naive
        ).order_by(OddsSnapshot.timestamp.asc()).all()
        
        return snapshots
    finally:
        db.close()


def detect_steam_move(
    match_id: str,
    current_odds: Dict[str, float],
    time_window_minutes: int = None,
    threshold_pct: float = STEAM_MOVE_THRESHOLD_PCT,
    league_key: str = None
) -> Optional[SteamMoveSignal]:
    """
    STEAM MOVE DETECTION: Detect rapid odds movements in short time windows.
    
    A "Steam Move" is a sudden, coordinated drop in odds across bookmakers,
    typically initiated by sharp bettors (syndicates) who have information.
    
    V4.3: Now supports tier-based time windows.
    - Tier 1 leagues (PL, La Liga, etc.): 5 min window (fast markets)
    - Tier 2+ leagues: 15 min window (slower markets)
    
    Detection Logic:
    1. Fetch odds history for the match
    2. Look for drops > threshold% within the time window
    3. Prioritize sharp bookie movements (Pinnacle, Betfair)
    
    Args:
        match_id: Match ID to analyze
        current_odds: Current odds dict {'home': x, 'draw': y, 'away': z}
        time_window_minutes: Time window to check (if None, uses tier-based default)
        threshold_pct: Minimum % drop to trigger signal
        league_key: League identifier for tier-based window (V4.3)
        
    Returns:
        SteamMoveSignal if detected, None otherwise
    """
    if not match_id or not current_odds:
        return None
    
    if time_window_minutes is None:
        time_window_minutes = get_steam_window_for_league(league_key)
    
    snapshots = get_odds_history(match_id, hours_back=2)
    
    if len(snapshots) < 2:
        return None
    
    now = datetime.now(timezone.utc)
    
    markets = [
        ('HOME', 'home_odd', current_odds.get('home')),
        ('DRAW', 'draw_odd', current_odds.get('draw')),
        ('AWAY', 'away_odd', current_odds.get('away'))
    ]
    
    best_signal = None
    best_drop = 0
    
    for market_name, field_name, current_odd in markets:
        if not current_odd or current_odd <= 1.0:
            continue
        
        for snapshot in snapshots:
            snapshot_time = snapshot.timestamp
            if snapshot_time.tzinfo is None:
                snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)
            
            minutes_ago = (now - snapshot_time).total_seconds() / 60
            
            if minutes_ago > time_window_minutes:
                continue
            
            historical_odd = getattr(snapshot, field_name, None)
            if not historical_odd or historical_odd <= 1.0:
                continue
            
            if historical_odd > current_odd:
                drop_pct = ((historical_odd - current_odd) / historical_odd) * 100
                
                if drop_pct >= threshold_pct and drop_pct > best_drop:
                    is_rapid = minutes_ago <= STEAM_MOVE_RAPID_WINDOW_MIN
                    
                    if drop_pct >= 10 or is_rapid:
                        confidence = 'HIGH'
                    elif drop_pct >= 7:
                        confidence = 'MEDIUM'
                    else:
                        confidence = 'LOW'
                    
                    best_signal = SteamMoveSignal(
                        detected=True,
                        market=market_name,
                        drop_pct=drop_pct,
                        time_window_min=int(minutes_ago),
                        start_odds=historical_odd,
                        end_odds=current_odd,
                        is_rapid=is_rapid,
                        confidence=confidence,
                        message=f"🚨 STEAM MOVE [{market_name}]: {historical_odd:.2f} → {current_odd:.2f} ({drop_pct:.1f}% in {int(minutes_ago)}min)"
                    )
                    best_drop = drop_pct
    
    return best_signal


# ============================================
# REVERSE LINE MOVEMENT DETECTION
# ============================================

def _estimate_rlm_time_window(match_id: Optional[str]) -> int:
    """
    Fix #5: Estimate time window for RLM pattern development from odds_snapshots.
    
    Calculates how long the reverse line movement pattern has been developing
    by analyzing the odds_snapshots history for the match.
    
    Args:
        match_id: Match ID to query snapshots for
        
    Returns:
        Estimated time window in minutes (0 if no data available)
    """
    if not match_id:
        return 0
    
    try:
        snapshots = get_odds_history(match_id, hours_back=24)
        
        if len(snapshots) < 2:
            return 0
        
        now = datetime.now(timezone.utc)
        oldest_snapshot = snapshots[0]
        
        if oldest_snapshot.timestamp:
            snapshot_time = oldest_snapshot.timestamp
            if snapshot_time.tzinfo is None:
                snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)
            
            minutes_ago = int((now - snapshot_time).total_seconds() / 60)
            return min(minutes_ago, 1440)
        
        return 0
        
    except Exception as e:
        logger.debug(f"Could not estimate RLM time window: {e}")
        return 0


@dataclass
class ReverseLineSignal:
    """Result of reverse line movement detection."""
    detected: bool
    market: str
    public_side: str
    sharp_side: str
    odds_movement_pct: float
    confidence: str
    message: str


@dataclass
class RLMSignalV2:
    """
    V4.3: Enhanced Reverse Line Movement signal with additional fields.
    
    Improvements over V1:
    - public_percentage: Exact public betting percentage
    - time_window_min: How long the pattern developed
    - recommendation: Clear betting recommendation
    - high_potential: Flag for AI analysis priority
    """
    detected: bool
    market: str
    public_side: str
    sharp_side: str
    public_percentage: float
    odds_movement_pct: float
    confidence: str
    time_window_min: int
    recommendation: str
    high_potential: bool
    message: str


def detect_reverse_line_movement(
    match: Match,
    public_bet_distribution: Optional[Dict[str, float]] = None
) -> Optional[ReverseLineSignal]:
    """
    REVERSE LINE MOVEMENT: Detect when odds move AGAINST public betting.
    
    This is a strong signal that sharp money (professionals) is betting
    the opposite side of the public. The bookmakers adjust odds based on
    sharp action, not public volume.
    
    Detection Logic:
    - If 65%+ of public bets are on HOME, but HOME odds are RISING → Sharp on AWAY
    - If 65%+ of public bets are on AWAY, but AWAY odds are RISING → Sharp on HOME
    
    V1.1 Fixes:
    - Fix #4: Added RLM_MIN_VALID_ODD check (odds must be > 1.0)
    - Fix #6: Improved public_bet estimation for away favorites
    
    Args:
        match: Match object with opening and current odds
        public_bet_distribution: Optional dict {'home': 0.70, 'away': 0.30}
                                 If not provided, we estimate from odds movement
                                 
    Returns:
        ReverseLineSignal if detected, None otherwise
    """
    if not match:
        return None
    
    if not match.opening_home_odd or not match.current_home_odd:
        return None
    if not match.opening_away_odd or not match.current_away_odd:
        return None
    
    if match.opening_home_odd < RLM_MIN_VALID_ODD or match.opening_away_odd < RLM_MIN_VALID_ODD:
        logger.debug(f"RLM V1: Invalid odds (< {RLM_MIN_VALID_ODD}), skipping")
        return None
    
    home_movement_pct = ((match.current_home_odd - match.opening_home_odd) / match.opening_home_odd) * 100
    away_movement_pct = ((match.current_away_odd - match.opening_away_odd) / match.opening_away_odd) * 100
    
    if public_bet_distribution is None:
        total_implied = (1/match.opening_home_odd) + (1/match.opening_away_odd)
        if total_implied <= 0:
            return None
        
        home_implied = (1/match.opening_home_odd) / total_implied
        
        PUBLIC_FAVORITE_BIAS = 0.15
        
        if home_implied > 0.5:
            public_home = min(0.85, home_implied + PUBLIC_FAVORITE_BIAS)
            public_away = 1 - public_home
        else:
            public_away = min(0.85, (1 - home_implied) + PUBLIC_FAVORITE_BIAS)
            public_home = 1 - public_away
        
        public_bet_distribution = {'home': public_home, 'away': public_away}
    
    public_home = public_bet_distribution.get('home', 0.5)
    public_away = public_bet_distribution.get('away', 0.5)
    
    signal = None
    
    if public_home >= RLM_PUBLIC_THRESHOLD and home_movement_pct >= (RLM_ODDS_INCREASE_THRESHOLD * 100):
        confidence = 'HIGH' if home_movement_pct >= 5 else 'MEDIUM'
        signal = ReverseLineSignal(
            detected=True,
            market='AWAY',
            public_side='HOME',
            sharp_side='AWAY',
            odds_movement_pct=home_movement_pct,
            confidence=confidence,
            message=f"🔄 REVERSE LINE: {public_home*100:.0f}% public on HOME, but odds RISING {home_movement_pct:+.1f}% → SHARP on AWAY"
        )
    
    elif public_away >= RLM_PUBLIC_THRESHOLD and away_movement_pct >= (RLM_ODDS_INCREASE_THRESHOLD * 100):
        confidence = 'HIGH' if away_movement_pct >= 5 else 'MEDIUM'
        signal = ReverseLineSignal(
            detected=True,
            market='HOME',
            public_side='AWAY',
            sharp_side='HOME',
            odds_movement_pct=away_movement_pct,
            confidence=confidence,
            message=f"🔄 REVERSE LINE: {public_away*100:.0f}% public on AWAY, but odds RISING {away_movement_pct:+.1f}% → SHARP on HOME"
        )
    
    return signal


def detect_rlm_v2(
    match: Match,
    public_bet_distribution: Optional[Dict[str, float]] = None,
    min_public_threshold: float = RLM_PUBLIC_THRESHOLD,
    min_odds_increase: float = RLM_ODDS_INCREASE_THRESHOLD
) -> Optional[RLMSignalV2]:
    """
    V4.3: Enhanced RLM detection with configurable thresholds.
    
    Improvements over V1:
    - Configurable thresholds
    - public_percentage field for exact betting distribution
    - recommendation field with clear betting suggestion
    - high_potential flag for AI analysis priority
    - Handles edge case of insufficient data gracefully
    
    V1.1 Fixes:
    - Fix #4: Use RLM_MIN_VALID_ODD constant for validation
    - Fix #5: Calculate time_window_min from odds_snapshots
    - Fix #6: Improved public_bet estimation for away favorites
    - Fix #9: Use module logger instead of logging.debug
    
    Args:
        match: Match object with opening and current odds
        public_bet_distribution: Optional dict {'home': 0.70, 'away': 0.30}
        min_public_threshold: Minimum public % to trigger (default 0.65)
        min_odds_increase: Minimum odds increase % (default 0.03 = 3%)
        
    Returns:
        RLMSignalV2 if detected, None otherwise
    """
    if not match:
        logger.debug("RLM V2: No match provided")
        return None
    
    if not match.opening_home_odd or not match.current_home_odd:
        logger.debug(f"RLM V2: Insufficient home odds data for match {getattr(match, 'id', 'unknown')}")
        return None
    if not match.opening_away_odd or not match.current_away_odd:
        logger.debug(f"RLM V2: Insufficient away odds data for match {getattr(match, 'id', 'unknown')}")
        return None
    
    if match.opening_home_odd < RLM_MIN_VALID_ODD or match.opening_away_odd < RLM_MIN_VALID_ODD:
        logger.debug(f"RLM V2: Invalid odds (< {RLM_MIN_VALID_ODD})")
        return None
    
    home_movement_pct = ((match.current_home_odd - match.opening_home_odd) / match.opening_home_odd) * 100
    away_movement_pct = ((match.current_away_odd - match.opening_away_odd) / match.opening_away_odd) * 100
    
    time_window_min = _estimate_rlm_time_window(getattr(match, 'id', None))
    
    if public_bet_distribution is None:
        total_implied = (1/match.opening_home_odd) + (1/match.opening_away_odd)
        if total_implied <= 0:
            return None
        
        home_implied = (1/match.opening_home_odd) / total_implied
        
        PUBLIC_FAVORITE_BIAS = 0.15
        
        if home_implied > 0.5:
            public_home = min(0.85, home_implied + PUBLIC_FAVORITE_BIAS)
            public_away = 1 - public_home
        else:
            public_away = min(0.85, (1 - home_implied) + PUBLIC_FAVORITE_BIAS)
            public_home = 1 - public_away
        
        public_bet_distribution = {'home': public_home, 'away': public_away}
    
    public_home = public_bet_distribution.get('home', 0.5)
    public_away = public_bet_distribution.get('away', 0.5)
    
    min_odds_increase_pct = min_odds_increase * 100
    
    signal = None
    
    if public_home >= min_public_threshold and home_movement_pct >= min_odds_increase_pct:
        if home_movement_pct >= 5:
            confidence = 'HIGH'
        elif home_movement_pct >= min_odds_increase_pct + 1:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'
        
        high_potential = confidence == 'HIGH'
        
        signal = RLMSignalV2(
            detected=True,
            market='AWAY',
            public_side='HOME',
            sharp_side='AWAY',
            public_percentage=public_home,
            odds_movement_pct=home_movement_pct,
            confidence=confidence,
            time_window_min=time_window_min,
            recommendation=f"Consider AWAY (sharp money detected)",
            high_potential=high_potential,
            message=f"🔄 RLM V2: {public_home*100:.0f}% public on HOME, odds RISING {home_movement_pct:+.1f}% → SHARP on AWAY"
        )
    
    elif public_away >= min_public_threshold and away_movement_pct >= min_odds_increase_pct:
        if away_movement_pct >= 5:
            confidence = 'HIGH'
        elif away_movement_pct >= min_odds_increase_pct + 1:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'
        
        high_potential = confidence == 'HIGH'
        
        signal = RLMSignalV2(
            detected=True,
            market='HOME',
            public_side='AWAY',
            sharp_side='HOME',
            public_percentage=public_away,
            odds_movement_pct=away_movement_pct,
            confidence=confidence,
            time_window_min=time_window_min,
            recommendation=f"Consider HOME (sharp money detected)",
            high_potential=high_potential,
            message=f"🔄 RLM V2: {public_away*100:.0f}% public on AWAY, odds RISING {away_movement_pct:+.1f}% → SHARP on HOME"
        )
    
    if signal and signal.high_potential:
        logger.info(f"⚡ HIGH POTENTIAL RLM detected: {signal.message}")
    
    return signal


# ============================================
# NEWS DECAY FUNCTION
# ============================================

def apply_news_decay(
    impact_score: float,
    minutes_since_publish: int,
    lambda_decay: float = None,
    league_key: str = None
) -> float:
    """
    NEWS DECAY: Apply exponential decay to news impact based on age.
    
    V4.3: Now supports league-adaptive decay rates.
    - Tier 1 leagues (PL, La Liga, etc.): Fast decay (λ=0.14, half-life ~5 min)
    - Tier 2+ leagues: Slow decay (λ=0.023, half-life ~30 min)
    
    The betting market prices in news very quickly (especially Asian markets).
    A news item that's 30 minutes old has likely already moved the odds.
    
    Formula: Impact_t = Impact_0 * e^(-λt)
    
    With default λ=0.05:
    - 5 min old: 78% impact remaining
    - 15 min old: 47% impact remaining  
    - 30 min old: 22% impact remaining
    - 60 min old: 5% impact remaining
    
    Args:
        impact_score: Original impact/relevance score (0-10)
        minutes_since_publish: Minutes since news was published
        lambda_decay: Decay rate (if None, uses league-specific or default)
        league_key: League identifier for adaptive decay (V4.3)
        
    Returns:
        Decayed impact score
    """
    if impact_score <= 0:
        return 0.0
    
    if minutes_since_publish <= 0:
        return impact_score
    
    if lambda_decay is None:
        try:
            from config.settings import get_news_decay_lambda
            lambda_decay = get_news_decay_lambda(league_key) if league_key else NEWS_DECAY_LAMBDA
        except ImportError:
            lambda_decay = NEWS_DECAY_LAMBDA
    
    max_minutes = NEWS_MAX_AGE_HOURS * 60
    if minutes_since_publish >= max_minutes:
        return impact_score * 0.01
    
    decay_factor = math.exp(-lambda_decay * minutes_since_publish)
    decay_factor = max(0.01, decay_factor)
    
    return impact_score * decay_factor


def apply_news_decay_v2(
    impact_score: float,
    minutes_since_publish: int,
    league_key: str = None,
    source_type: str = "mainstream",
    minutes_to_kickoff: int = None
) -> tuple:
    """
    V4.3: Enhanced news decay with league, source, and kickoff awareness.
    
    Improvements over V1:
    1. League-specific decay rates (Tier1 vs Elite)
    2. Source-based modifiers (insider sources decay slower)
    3. Kickoff proximity acceleration (news decays faster near kickoff)
    4. Freshness tags for AI context
    
    Args:
        impact_score: Original impact (0-10)
        minutes_since_publish: Age of news in minutes
        league_key: For league-specific decay rate
        source_type: For source-based modifier ('beat_writer', 'reddit', etc.)
        minutes_to_kickoff: For kickoff proximity acceleration
        
    Returns:
        Tuple of (decayed_score, freshness_tag)
    """
    if impact_score <= 0:
        return 0.0, "📜 STALE"
    
    if minutes_since_publish <= 0:
        return impact_score, "🔥 FRESH"
    
    try:
        from config.settings import get_news_decay_lambda, get_source_decay_modifier
        base_lambda = get_news_decay_lambda(league_key)
        source_modifier = get_source_decay_modifier(source_type)
    except ImportError:
        base_lambda = NEWS_DECAY_LAMBDA
        source_modifier = 1.0
    
    effective_lambda = base_lambda * source_modifier
    
    if minutes_to_kickoff is not None and minutes_to_kickoff <= 30:
        effective_lambda *= 2.0
    
    max_minutes = NEWS_MAX_AGE_HOURS * 60
    if minutes_since_publish >= max_minutes:
        return impact_score * 0.01, "📜 STALE"
    
    decay_factor = math.exp(-effective_lambda * minutes_since_publish)
    decay_factor = max(0.01, decay_factor)
    
    decayed_score = impact_score * decay_factor
    
    freshness_tag = _get_freshness_tag_from_minutes(minutes_since_publish)
    
    return decayed_score, freshness_tag


def _get_freshness_tag_from_minutes(minutes_old: int) -> str:
    """
    V7.0: Centralized freshness tag - delegates to src/utils/freshness.py
    
    Uses TIME-based thresholds instead of decay_factor for consistency:
    - 🔥 FRESH: < 60 min (high market impact, news not yet priced in)
    - ⏰ AGING: 60-360 min (moderate impact, partially priced in)
    - 📜 STALE: > 360 min (low impact, likely fully priced in)
    
    Args:
        minutes_old: Age of news in minutes
        
    Returns:
        Freshness tag emoji + label
    """
    if _FRESHNESS_MODULE_AVAILABLE:
        return _central_freshness_tag(minutes_old)
    
    if minutes_old < 0:
        logger.debug(f"Clock skew detected: minutes_old={minutes_old}, treating as FRESH")
        return "🔥 FRESH"
    
    if minutes_old < FRESHNESS_FRESH_THRESHOLD_MIN:
        return "🔥 FRESH"
    elif minutes_old < FRESHNESS_AGING_THRESHOLD_MIN:
        return "⏰ AGING"
    else:
        return "📜 STALE"


def calculate_news_freshness_multiplier(
    news_date_str: Optional[str],
    reference_time: Optional[datetime] = None,
    league_key: str = None
) -> Tuple[float, int]:
    """
    Calculate freshness multiplier for a news item based on its date string.
    
    V4.3: Now supports league-specific decay rates via league_key parameter.
    
    Parses various date formats from search results and calculates
    how many minutes old the news is.
    
    Args:
        news_date_str: Date string from search result (e.g., "2 hours ago", "Dec 28, 2024")
        reference_time: Reference time for comparison (default: now)
        league_key: League identifier for adaptive decay (V4.3)
        
    Returns:
        Tuple of (multiplier, minutes_old)
        multiplier: 0.0-1.0 freshness factor
        minutes_old: Estimated age in minutes
    """
    if not news_date_str:
        return apply_news_decay(1.0, 30, league_key=league_key) / 1.0, 30
    
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    
    news_date_lower = news_date_str.lower().strip()
    minutes_old = 30
    
    try:
        if 'just now' in news_date_lower or 'now' == news_date_lower:
            minutes_old = 1
        elif 'second' in news_date_lower:
            minutes_old = 1
        elif 'minute' in news_date_lower:
            match = re.search(r'(\d+)\s*min', news_date_lower)
            if match:
                minutes_old = int(match.group(1))
            else:
                minutes_old = 5
        elif 'hour' in news_date_lower:
            match = re.search(r'(\d+)\s*hour', news_date_lower)
            if match:
                hours = int(match.group(1))
                minutes_old = hours * 60
            else:
                minutes_old = 60
        elif 'day' in news_date_lower:
            match = re.search(r'(\d+)\s*day', news_date_lower)
            if match:
                days = int(match.group(1))
                minutes_old = days * 24 * 60
            else:
                minutes_old = 24 * 60
        elif 'yesterday' in news_date_lower:
            minutes_old = 24 * 60
        elif 'week' in news_date_lower:
            minutes_old = 7 * 24 * 60
        else:
            from dateutil import parser as date_parser
            try:
                parsed_date = date_parser.parse(news_date_str)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                
                delta = reference_time - parsed_date
                minutes_old = max(1, int(delta.total_seconds() / 60))
            except Exception:
                minutes_old = 30
    except Exception as e:
        logger.debug(f"Could not parse news date '{news_date_str}': {e}")
        minutes_old = 30
    
    multiplier = apply_news_decay(1.0, minutes_old, league_key=league_key)
    
    return multiplier, minutes_old


# ============================================
# SNAPSHOT MANAGEMENT
# ============================================

def save_odds_snapshot(
    match_id: str,
    home_odd: Optional[float],
    draw_odd: Optional[float],
    away_odd: Optional[float],
    sharp_home_odd: Optional[float] = None,
    sharp_draw_odd: Optional[float] = None,
    sharp_away_odd: Optional[float] = None,
    sharp_bookie: Optional[str] = None
) -> bool:
    """
    Save an odds snapshot for historical tracking.
    
    Called during fixture ingestion to build odds history.
    
    Args:
        match_id: Match ID
        home_odd, draw_odd, away_odd: Current market odds
        sharp_*: Sharp bookie odds (optional)
        sharp_bookie: Name of sharp bookie
        
    Returns:
        True if saved successfully
    """
    if not match_id:
        return False
    
    db = SessionLocal()
    try:
        snapshot = OddsSnapshot(
            match_id=match_id,
            timestamp=datetime.now(timezone.utc),
            home_odd=home_odd,
            draw_odd=draw_odd,
            away_odd=away_odd,
            sharp_home_odd=sharp_home_odd,
            sharp_draw_odd=sharp_draw_odd,
            sharp_away_odd=sharp_away_odd,
            sharp_bookie=sharp_bookie
        )
        db.add(snapshot)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save odds snapshot: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def cleanup_old_snapshots(days_to_keep: int = 7) -> int:
    """
    Clean up old odds snapshots to prevent database bloat.
    
    Args:
        days_to_keep: Number of days of history to retain
        
    Returns:
        Number of snapshots deleted
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        cutoff_naive = cutoff.replace(tzinfo=None)
        
        deleted = db.query(OddsSnapshot).filter(
            OddsSnapshot.timestamp < cutoff_naive
        ).delete()
        
        db.commit()
        logger.info(f"🧹 Cleaned up {deleted} old odds snapshots")
        return deleted
    except Exception as e:
        logger.error(f"Failed to cleanup snapshots: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


# ============================================
# COMBINED MARKET INTELLIGENCE
# ============================================

@dataclass
class MarketIntelligence:
    """Combined market intelligence signals."""
    steam_move: Optional[SteamMoveSignal]
    reverse_line: Optional[ReverseLineSignal]
    rlm_v2: Optional[RLMSignalV2] = None
    has_signals: bool = False
    summary: str = ""


def analyze_market_intelligence(
    match: Match,
    public_bet_distribution: Optional[Dict[str, float]] = None,
    league_key: str = None
) -> MarketIntelligence:
    """
    Run all market intelligence checks for a match.
    
    V4.3: Now supports league_key for tier-based Steam Move windows.
    Also includes enhanced RLM V2 detection with high_potential flagging.
    
    Combines:
    - Steam Move Detection (with tier-based windows)
    - Reverse Line Movement (V1 for backward compatibility)
    - RLM V2 (enhanced with recommendation and high_potential)
    
    Args:
        match: Match object with odds data
        public_bet_distribution: Optional public betting percentages
        league_key: League identifier for tier-based analysis (V4.3)
        
    Returns:
        MarketIntelligence with all signals
    """
    if not match:
        return MarketIntelligence(
            steam_move=None,
            reverse_line=None,
            rlm_v2=None,
            has_signals=False,
            summary="No match data"
        )
    
    effective_league = league_key or getattr(match, 'league', None)
    
    current_odds = {
        'home': match.current_home_odd,
        'draw': match.current_draw_odd,
        'away': match.current_away_odd
    }
    
    steam_signal = detect_steam_move(match.id, current_odds, league_key=effective_league)
    
    rlm_signal = detect_reverse_line_movement(match, public_bet_distribution)
    
    rlm_v2_signal = detect_rlm_v2(match, public_bet_distribution)
    
    signals = []
    if steam_signal and steam_signal.detected:
        signals.append(steam_signal.message)
    
    if rlm_v2_signal and rlm_v2_signal.detected:
        signals.append(rlm_v2_signal.message)
        if rlm_v2_signal.high_potential:
            signals.append(f"⚡ HIGH POTENTIAL: {rlm_v2_signal.recommendation}")
    elif rlm_signal and rlm_signal.detected:
        signals.append(rlm_signal.message)
    
    has_signals = len(signals) > 0
    summary = " | ".join(signals) if signals else "No advanced market signals"
    
    return MarketIntelligence(
        steam_move=steam_signal,
        reverse_line=rlm_signal,
        rlm_v2=rlm_v2_signal,
        has_signals=has_signals,
        summary=summary
    )


# ============================================
# DATABASE INITIALIZATION
# ============================================

def init_market_intelligence_db():
    """Create the odds_snapshots table if it doesn't exist."""
    try:
        OddsSnapshot.__table__.create(engine, checkfirst=True)
        logger.info("✅ Market Intelligence DB initialized (odds_snapshots table)")
    except Exception as e:
        logger.error(f"Failed to initialize market intelligence DB: {e}")
