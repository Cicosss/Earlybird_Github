"""
EarlyBird Freshness Module - Centralized News Freshness Logic V1.0

This module provides a SINGLE SOURCE OF TRUTH for all freshness-related
calculations across the entire EarlyBird system.

Used by:
- src/processing/news_hunter.py (register_browser_monitor_discovery, get_browser_monitor_news)
- src/analysis/market_intelligence.py (apply_news_decay_v2, _get_freshness_tag_from_minutes)
- src/services/news_radar.py (RadarAlert freshness)
- src/services/browser_monitor.py (DiscoveredNews freshness)
- src/main.py (dossier builder freshness tags)

V1.0: Extracted from news_hunter.py and market_intelligence.py for DRY compliance.

Freshness Categories:
- 🔥 FRESH: < 60 min - High market impact, news likely NOT priced in yet
- ⏰ AGING: 60-360 min (1-6h) - Moderate impact, partially priced in
- 📜 STALE: > 360 min (6h+) - Low impact, likely fully priced in by market
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================
# FRESHNESS THRESHOLDS (Single Source of Truth)
# ============================================
# These constants define the boundaries between freshness categories.
# Changing them here automatically updates the entire system.

FRESHNESS_FRESH_THRESHOLD_MIN = 60      # < 60 min = FRESH
FRESHNESS_AGING_THRESHOLD_MIN = 360     # < 360 min (6h) = AGING, else STALE

# News Decay Configuration
NEWS_DECAY_LAMBDA_DEFAULT = 0.05        # Default decay rate
NEWS_MAX_AGE_HOURS = 24                 # News older than this has near-zero impact
NEWS_RESIDUAL_VALUE = 0.01              # 1% residual value for very old news


@dataclass
class FreshnessResult:
    """
    Result of freshness calculation.
    
    Attributes:
        tag: Emoji + label (e.g., "🔥 FRESH")
        minutes_old: Age in minutes
        decay_multiplier: 0.0-1.0 multiplier for impact scoring
        category: Category name without emoji ("FRESH", "AGING", "STALE")
    """
    tag: str
    minutes_old: int
    decay_multiplier: float
    category: str


def get_freshness_tag(minutes_old: int) -> str:
    """
    Get freshness tag based on news age in minutes.
    
    This is the CANONICAL function for freshness tag calculation.
    All other modules should import and use this function.
    
    Tags align with market impact expectations:
    - 🔥 FRESH: < 60 min - Breaking news, high edge potential
    - ⏰ AGING: 60-360 min - News spreading, moderate edge
    - 📜 STALE: > 360 min - Likely priced in, low edge
    
    Args:
        minutes_old: Age of news in minutes (handles negative = clock skew)
        
    Returns:
        Freshness tag emoji + label (e.g., "🔥 FRESH")
    """
    # Handle clock skew (future timestamps from different timezones)
    if minutes_old < 0:
        logger.debug(f"Clock skew detected: minutes_old={minutes_old}, treating as FRESH")
        return "🔥 FRESH"
    
    if minutes_old < FRESHNESS_FRESH_THRESHOLD_MIN:
        return "🔥 FRESH"
    elif minutes_old < FRESHNESS_AGING_THRESHOLD_MIN:
        return "⏰ AGING"
    else:
        return "📜 STALE"


def get_freshness_category(minutes_old: int) -> str:
    """
    Get freshness category name without emoji.
    
    Useful for programmatic comparisons and logging.
    
    Args:
        minutes_old: Age of news in minutes
        
    Returns:
        Category name: "FRESH", "AGING", or "STALE"
    """
    if minutes_old < 0:
        return "FRESH"
    
    if minutes_old < FRESHNESS_FRESH_THRESHOLD_MIN:
        return "FRESH"
    elif minutes_old < FRESHNESS_AGING_THRESHOLD_MIN:
        return "AGING"
    else:
        return "STALE"


def calculate_minutes_old(
    timestamp: datetime,
    reference_time: Optional[datetime] = None
) -> int:
    """
    Calculate how many minutes old a timestamp is.
    
    Handles timezone-aware and naive datetimes safely.
    
    Args:
        timestamp: The datetime to check
        reference_time: Reference time (default: now UTC)
        
    Returns:
        Minutes old (can be negative if timestamp is in future)
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    
    # Ensure both are timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    
    delta = reference_time - timestamp
    return int(delta.total_seconds() / 60)


def calculate_decay_multiplier(
    minutes_old: int,
    lambda_decay: float = NEWS_DECAY_LAMBDA_DEFAULT,
    max_age_hours: int = NEWS_MAX_AGE_HOURS
) -> float:
    """
    Calculate exponential decay multiplier for news impact.
    
    Formula: multiplier = e^(-λt)
    
    With default λ=0.05:
    - 5 min old: 78% impact remaining
    - 15 min old: 47% impact remaining  
    - 30 min old: 22% impact remaining
    - 60 min old: 5% impact remaining
    
    Args:
        minutes_old: Age of news in minutes
        lambda_decay: Decay rate (higher = faster decay)
        max_age_hours: Cap age at this many hours
        
    Returns:
        Decay multiplier between NEWS_RESIDUAL_VALUE and 1.0
    """
    if minutes_old <= 0:
        return 1.0
    
    # Cap at max age
    max_minutes = max_age_hours * 60
    if minutes_old >= max_minutes:
        return NEWS_RESIDUAL_VALUE
    
    # Apply exponential decay
    decay_factor = math.exp(-lambda_decay * minutes_old)
    
    # Ensure minimum residual value
    return max(NEWS_RESIDUAL_VALUE, decay_factor)


def get_full_freshness(
    timestamp: datetime,
    reference_time: Optional[datetime] = None,
    lambda_decay: float = NEWS_DECAY_LAMBDA_DEFAULT
) -> FreshnessResult:
    """
    Get complete freshness analysis for a timestamp.
    
    Combines tag, minutes_old, and decay multiplier in one call.
    This is the recommended function for most use cases.
    
    Args:
        timestamp: The datetime to analyze
        reference_time: Reference time (default: now UTC)
        lambda_decay: Decay rate for multiplier calculation
        
    Returns:
        FreshnessResult with all freshness data
    """
    minutes_old = calculate_minutes_old(timestamp, reference_time)
    tag = get_freshness_tag(minutes_old)
    category = get_freshness_category(minutes_old)
    decay_multiplier = calculate_decay_multiplier(minutes_old, lambda_decay)
    
    return FreshnessResult(
        tag=tag,
        minutes_old=minutes_old,
        decay_multiplier=decay_multiplier,
        category=category
    )


def parse_relative_time(time_str: str) -> Optional[int]:
    """
    Parse relative time strings like "2 hours ago" into minutes.
    
    Supports common formats from search engines and news sites:
    - "X minutes ago", "X mins ago", "X min ago"
    - "X hours ago", "X hrs ago", "X hr ago"
    - "X days ago"
    - "yesterday"
    - "just now", "now"
    
    Args:
        time_str: Relative time string
        
    Returns:
        Minutes old, or None if parsing fails
    """
    if not time_str:
        return None
    
    time_str = time_str.lower().strip()
    
    # Handle "just now" / "now"
    if time_str in ('just now', 'now', 'agora', 'ahora', 'jetzt', 'maintenant'):
        return 0
    
    # Handle "yesterday"
    if time_str in ('yesterday', 'ieri', 'ayer', 'ontem', 'gestern', 'hier'):
        return 24 * 60  # 1440 minutes
    
    import re
    
    # Pattern: "X minutes/hours/days ago"
    patterns = [
        (r'(\d+)\s*(?:minute|min|minuto|minuti|minuten|minut)s?\s*(?:ago|fa|hace|atrás|vor|il y a)?', 1),
        (r'(\d+)\s*(?:hour|hr|ora|ore|hora|horas|stunde|stunden|heure)s?\s*(?:ago|fa|hace|atrás|vor|il y a)?', 60),
        (r'(\d+)\s*(?:day|giorno|giorni|día|dias|tag|tage|jour)s?\s*(?:ago|fa|hace|atrás|vor|il y a)?', 60 * 24),
        (r'(\d+)\s*(?:week|settimana|settimane|semana|semanas|woche|wochen|semaine)s?\s*(?:ago|fa|hace|atrás|vor|il y a)?', 60 * 24 * 7),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, time_str)
        if match:
            try:
                value = int(match.group(1))
                return value * multiplier
            except (ValueError, IndexError):
                continue
    
    return None


# ============================================
# LEAGUE-SPECIFIC DECAY RATES
# ============================================
# Different leagues have different market efficiency.
# Tier 1 leagues (PL, La Liga) price in news faster than niche leagues.

LEAGUE_DECAY_RATES = {
    # Tier 1 - Fast markets (λ=0.14, half-life ~5 min)
    'soccer_epl': 0.14,
    'soccer_spain_la_liga': 0.14,
    'soccer_germany_bundesliga': 0.14,
    'soccer_italy_serie_a': 0.14,
    'soccer_france_ligue_one': 0.14,
    
    # Tier 2 - Medium markets (λ=0.05, half-life ~14 min)
    'soccer_netherlands_eredivisie': 0.05,
    'soccer_portugal_primeira_liga': 0.05,
    'soccer_turkey_super_league': 0.05,
    
    # Tier 3 - Slow markets (λ=0.023, half-life ~30 min)
    # Default for all other leagues
}

DEFAULT_LEAGUE_DECAY_RATE = 0.023  # Slow decay for niche leagues


def get_league_decay_rate(league_key: Optional[str]) -> float:
    """
    Get the appropriate decay rate for a league.
    
    Tier 1 leagues have faster decay (news priced in quickly).
    Niche leagues have slower decay (more edge opportunity).
    
    Args:
        league_key: League identifier (e.g., 'soccer_epl')
        
    Returns:
        Decay rate (lambda) for exponential decay
    """
    if not league_key:
        return DEFAULT_LEAGUE_DECAY_RATE
    
    return LEAGUE_DECAY_RATES.get(league_key, DEFAULT_LEAGUE_DECAY_RATE)


def get_league_aware_freshness(
    timestamp: datetime,
    league_key: Optional[str] = None,
    reference_time: Optional[datetime] = None
) -> FreshnessResult:
    """
    Get freshness analysis with league-specific decay rate.
    
    Use this when you need league-aware decay multipliers.
    
    Args:
        timestamp: The datetime to analyze
        league_key: League identifier for decay rate lookup
        reference_time: Reference time (default: now UTC)
        
    Returns:
        FreshnessResult with league-appropriate decay multiplier
    """
    lambda_decay = get_league_decay_rate(league_key)
    return get_full_freshness(timestamp, reference_time, lambda_decay)
