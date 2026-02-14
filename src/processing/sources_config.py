"""
Hyper-Local News Sources Configuration - Elite 6 Strategy

Maps Elite 6 leagues to their best local news domains for site-specific searching.
These sources provide the most reliable and timely injury/lineup news.

ELITE 6 LEAGUES:
1. Turkey, 2. Argentina, 3. Mexico, 4. Greece, 5. Scotland, 6. Australia

NOTE: Seasonal leagues (China, Japan, Brazil_B) and Egypt (hybrid mode) are kept
for OpportunityRadar narrative-first alerts.

Usage:
    from src.processing.sources_config import get_sources_for_league
    sources = get_sources_for_league("soccer_argentina_primera_division")
"""
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ============================================
# V4.3: BEAT WRITER DATA STRUCTURE
# ============================================

@dataclass
class BeatWriter:
    """
    V4.3: Represents a verified beat writer or insider account.
    
    Beat writers are journalists who specialize in covering specific teams
    or leagues, often with privileged access to breaking news.
    
    Attributes:
        handle: Twitter/X handle (with @)
        name: Full name of the journalist
        outlet: Media outlet they work for
        specialty: Area of expertise (injuries, transfers, lineups)
        reliability: Historical accuracy score (0.0-1.0)
        avg_lead_time_min: Average minutes before mainstream media picks up their news
    """
    handle: str
    name: str
    outlet: str
    specialty: str  # "injuries", "transfers", "lineups", "general"
    reliability: float  # 0.0-1.0
    avg_lead_time_min: int  # Minutes ahead of mainstream


# ============================================
# V4.4: BEAT WRITERS DATABASE (REVISED)
# ============================================
# V4.4 IMPORTANT NOTE FROM DEEP RESEARCH:
# The concept of "beat writers who leak injury/lineup news 10-30 min 
# before mainstream media" does NOT exist in the way originally assumed.
# 
# REALITY:
# - Real leaks come from anonymous club insiders (WhatsApp/Discord), not journalists
# - Journalists REPORT leaks, they don't CREATE them
# - Transfer specialists (Fabrizio Romano) exist, but injury/lineup specialists don't
# - The "lead time" metric is not measurable without 6+ months of tracking
#
# This database now contains OFFICIAL/VERIFIED accounts that post quickly,
# NOT insider sources. Reliability scores are estimates based on account activity.

# DEPRECATED: Intelligence now managed via Supabase
# This dictionary serves as FALLBACK ONLY when Supabase is unavailable
# Last updated: 2026-02-13
# Migration status: Graceful degradation active
BEAT_WRITERS_DB = {
    "turkey": [
        # Official accounts - fast but not "insider"
        BeatWriter("@Fanatik", "Fanatik", "Fanatik", "general", 0.75, 10),
    ],
    "argentina": [
        # Official media accounts
        BeatWriter("@TyCSports", "TyC Sports", "TyC Sports", "general", 0.80, 10),
        BeatWriter("@TNTSportsLA", "TNT Sports LA", "TNT Sports", "general", 0.80, 10),
    ],
    "mexico": [
        # Transfer specialist (verified)
        BeatWriter("@FabrizioRomano", "Fabrizio Romano", "Independent", "transfers", 0.95, 30),
    ],
    "greece": [
        BeatWriter("@GreekFooty", "Greek Football News", "Aggregator", "general", 0.70, 10),
    ],
    "scotland": [
        BeatWriter("@PLZSoccer", "PLZ Soccer", "PLZ Soccer", "general", 0.80, 10),
        BeatWriter("@ClydeSSB", "Clyde SSB", "Clyde Radio", "general", 0.75, 10),
    ],
    "australia": [
        # Official A-Leagues account - posts lineups ~60 min before kickoff
        BeatWriter("@ALeagues", "A-Leagues Official", "A-Leagues", "lineups", 0.95, 60),
        BeatWriter("@KeepUpFC", "Keep Up FC", "Keep Up", "general", 0.80, 15),
    ],
    "china": [
        BeatWriter("@HotpotFootball", "Hotpot Football", "Aggregator", "general", 0.75, 15),
    ],
    "japan": [
        BeatWriter("@J_League_En", "J-League English", "J-League Official", "lineups", 0.90, 60),
        BeatWriter("@dan_orlowitz", "Dan Orlowitz", "Japan Times", "general", 0.85, 15),
    ],
    "brazil_b": [
        BeatWriter("@geglobo", "GE Globo", "Globo Esporte", "general", 0.80, 10),
    ],
    "egypt": [
        BeatWriter("@KingFut", "KingFut", "KingFut", "general", 0.75, 10),
    ],
    "poland": [
        BeatWriter("@EkstraklasaSA", "Ekstraklasa", "Ekstraklasa Official", "lineups", 0.90, 60),
    ],
}

# ============================================
# LOCAL NEWS SOURCES BY COUNTRY
# ============================================
# Elite 6 leagues + seasonal/hybrid for Radar support

# DEPRECATED: Intelligence now managed via Supabase
# This dictionary serves as FALLBACK ONLY when Supabase is unavailable
# Last updated: 2026-02-13
# Migration status: Graceful degradation active
LOCAL_SOURCES_MAPPING = {
    # ============================================
    # ELITE 6 LEAGUES
    # ============================================
    "turkey": [
        "fanatik.com.tr",       # Fanatik - Major sports newspaper
        "sporx.com",            # Sporx - Sports portal
        "sabah.com.tr",         # Sabah - News with sports section
    ],
    "argentina": [
        "ole.com.ar",           # Olé - Argentina's #1 sports newspaper
        "tycsports.com",        # TyC Sports - Major sports broadcaster
        "infobae.com",          # Infobae - News with strong sports section
    ],
    "mexico": [
        "mediotiempo.com",      # Medio Tiempo - Leading sports portal
        "record.com.mx",        # Record - Major sports newspaper
        "espn.com.mx",          # ESPN Mexico - Reliable coverage
    ],
    "greece": [
        "sdna.gr",              # SDNA - Sports news agency
        "contra.gr",            # Contra - Popular sports site
        "gazzetta.gr",          # Gazzetta Greece - Sports daily
    ],
    "scotland": [
        "dailyrecord.co.uk",    # Daily Record - Scottish tabloid
        "thescottishsun.co.uk", # Scottish Sun - Wide coverage
        "bbc.com/sport",        # BBC Sport - Reliable for Scottish football
    ],
    "australia": [
        "aleagues.com.au",      # A-Leagues Official - Primary source
        "keepup.com.au",        # Keep Up - A-League specialist
        "foxsports.com.au",     # Fox Sports Australia
    ],
    # ============================================
    # SEASONAL LEAGUES (for Radar support)
    # ============================================
    "china": [
        "twitter.com",          # PROXY: @HotpotFootball aggregator
        "dongqiudi.com",        # Dongqiudi - Chinese football portal
    ],
    "japan": [
        "nikkansports.com",     # Nikkan Sports - Major Japanese sports daily
        "soccerdigestweb.com",  # Soccer Digest - J-League specialist
        "football-zone.net",    # Football Zone - Japanese football news
    ],
    "brazil_b": [
        "lance.com.br",         # Lance! - Text ticker
        "globoesporte.globo.com", # Globo Esporte - Major sports portal
        "uol.com.br/esporte",   # UOL Esporte - Wide coverage
    ],
    # ============================================
    # EGYPT - HYBRID MODE (No Odds Available)
    # ============================================
    "egypt": [
        "yallakora.com",        # Yalla Kora - Egypt's #1 sports site
        "filgoal.com",          # FilGoal - Major Egyptian football portal
        "kingfut.com",          # KingFut - Egyptian football specialist
    ],
}

# Native language keywords for injury/lineup searches
NATIVE_KEYWORDS = {
    "argentina": ["lesionados", "bajas", "formación", "convocados", "ausentes"],
    "mexico": ["lesionados", "bajas", "alineación", "convocatoria", "ausencias"],
    "greece": ["τραυματίες", "απουσίες", "ενδεκάδα", "αποστολή"],
    "turkey": ["sakatlar", "kadro", "ilk 11", "eksikler", "kadroda yok"],
    "scotland": ["injury", "team news", "lineup", "squad", "ruled out"],
    # AUSTRALIA FOCUS
    "australia": ["injury", "squad", "lineup", "team news", "ruled out", "starting XI"],
    # SEASONAL LEAGUES
    "china": ["伤病", "首发", "阵容", "缺阵", "injury", "lineup"],  # Chinese + English fallback
    "japan": ["怪我", "スタメン", "欠場", "injury", "lineup"],  # Japanese + English fallback
    "brazil_b": ["desfalque", "escalação", "lesão", "urgente", "time titular"],
    # EGYPT - Arabic keywords
    "egypt": ["إصابة", "غياب", "تشكيل", "تشكيلة", "مصاب", "injury", "lineup"],
}

# ============================================
# INSIDER INTEL LAYER (Beat Writers + Aggregators)
# ============================================
# Twitter handles of trusted beat writers and insider accounts
# These are searched via site:twitter.com for breaking news
#
# V4.4 NOTE: Deep Research confirmed that "beat writers who leak 
# injury/lineup news 10-30 min before mainstream" don't exist publicly.
# Real leaks come from anonymous club insiders, not journalists.
# These handles are for OFFICIAL accounts that post quickly, not insiders.

# DEPRECATED: Intelligence now managed via Supabase
# This dictionary serves as FALLBACK ONLY when Supabase is unavailable
# Last updated: 2026-02-13
# Migration status: Graceful degradation active
INSIDER_HANDLES = {
    "argentina": [
        "@TyCSports",           # TyC Sports - Official (fast on breaking news)
        "@ESPNArgentina",       # ESPN Argentina - Official
        "@TNTSportsLA",         # TNT Sports Latin America
    ],
    "mexico": [
        "@ABORICUA_MX",         # Placeholder - needs verification
        "@FabrizioRomano",      # Fabrizio Romano (covers Liga MX transfers)
        "@ABORICUA_MX2",        # Placeholder - needs verification
    ],
    "greece": [
        "@SDABORICUA",          # SDNA - Greek sports news (needs verification)
        "@GreekFooty",          # Greek Football News aggregator
        "@NovasportsGR",        # Novasports Greece
    ],
    "turkey": [
        "@Aboricua_TR",         # Placeholder - needs verification
        "@beaboricuaTR",        # beIN Sports Turkey (needs verification)
        "@Fanatik",             # Fanatik - Turkish sports daily
    ],
    "scotland": [
        "@PLZSoccer",           # PLZ Soccer - Scottish football show
        "@ClydeSSB",            # Clyde SSB - Scottish football radio
        "@ScotlandSky",         # Sky Sports Scotland (needs verification)
    ],
    # AUSTRALIA FOCUS - OFFICIAL SOURCE STRATEGY
    "australia": [
        "@ALeagues",            # A-Leagues Official
        "@KeepUpFC",            # Keep Up FC - A-League specialist
        "@FOXFootballAU",       # Fox Football Australia
    ],
    # SEASONAL LEAGUES
    "china": [
        "@HotpotFootball",      # Hotpot Football - Chinese football aggregator
        "@WildEastFootball",    # Wild East Football - CSL coverage
    ],
    "japan": [
        "@J_League_En",         # J-League English official
        "@dan_orlowitz",        # Dan Orlowitz - J-League journalist (verified)
    ],
    "brazil_b": [
        "@geglobo",             # GE Globo official
        "@TNTSportsBR",         # TNT Sports Brazil
    ],
    # EGYPT
    "egypt": [
        "@FilGoalNews",         # FilGoal - Egyptian football
        "@KingFut",             # KingFut - Egyptian football
    ],
    # POLAND
    "poland": [
        "@LaczyNasPilka",       # Polish FA official
        "@EkstraklasaSA",       # Ekstraklasa official
    ],
}

# ============================================
# TELEGRAM INSIDER CHANNELS
# ============================================
# Verified Telegram channels for real-time squad/injury intel
# These are monitored by telegram_listener.py

TELEGRAM_INSIDERS = {
    # ============================================
    # GLOBAL AGGREGATORS (cover all Elite 7 leagues)
    # Added V4.4 from Deep Research - Fast aggregators (5-15 min from club announcements)
    # ============================================
    "_global": [
        "injuries_suspensions",  # @injuries_suspensions - 100+ leagues, 5-15 min lead time
        "allfootballss",         # @allfootballss - General news aggregator
    ],
    # ============================================
    # LEAGUE-SPECIFIC CHANNELS
    # ============================================
    "turkey": [
        "sporhaberleriguncel",   # Turkish sports news aggregator
        "bgysportshaber",        # BGY Sports - Turkish football news
        "ErsinnSezer",           # Ersin Sezer - Turkish insider
        "besiktashaberleri",     # Besiktas news channel
        "spor_tr",               # Turkish sports general
        # V4.5: Removed "ensuperlig" - channel no longer exists (ValueError: No user has "ensuperlig" as username)
    ],
    "scotland": [
        "GlasgowRangersUpdates", # Rangers FC updates
        "SportMedics",           # Sports injury news
    ],
    "greece": [
        "thkalogiros",           # Greek football insider
    ],
    "argentina": [
        "infoboca",              # Boca Juniors insider channel
    ],
    "mexico": [],                # Limited Telegram presence - WhatsApp dominant
    # AUSTRALIA FOCUS
    "australia": [],             # Limited Telegram - use A-League scraper instead
    # SEASONAL LEAGUES
    "china": [],                 # WeChat dominant, not Telegram
    "japan": [],                 # LINE dominant, not Telegram
    "brazil_b": [],              # WhatsApp dominant
    # EGYPT
    "egypt": [],                 # To be added
    # POLAND
    "poland": [],                # Limited Telegram presence
}



def get_country_from_league(league_key: str) -> Optional[str]:
    """
    Extract country identifier from league key.
    STRICT: Only matches our 9 target leagues.
    
    Args:
        league_key: API league key (e.g., 'soccer_argentina_primera_division')
        
    Returns:
        Country key or None
    """
    # STRICT mapping by exact league key
    LEAGUE_TO_COUNTRY = {
        "soccer_turkey_super_league": "turkey",
        "soccer_argentina_primera_division": "argentina",
        "soccer_mexico_ligamx": "mexico",
        "soccer_greece_super_league": "greece",
        "soccer_spl": "scotland",
        "soccer_australia_aleague": "australia",
        "soccer_poland_ekstraklasa": "poland",
        "soccer_china_superleague": "china",
        "soccer_japan_j_league": "japan",
        "soccer_brazil_serie_b": "brazil_b",
    }
    
    return LEAGUE_TO_COUNTRY.get(league_key)


def get_sources_for_league(league_key: str) -> List[str]:
    """
    Get local news sources for a league.
    
    Args:
        league_key: API league key
        
    Returns:
        List of domain names for site-dorking
    """
    country = get_country_from_league(league_key)
    if country:
        return LOCAL_SOURCES_MAPPING.get(country, [])
    return []


def get_keywords_for_league(league_key: str) -> List[str]:
    """
    Get native language keywords for a league.
    
    Args:
        league_key: API league key
        
    Returns:
        List of native keywords for injury/lineup searches
    """
    country = get_country_from_league(league_key)
    if country:
        return NATIVE_KEYWORDS.get(country, [])
    return ["injury", "lineup", "squad", "ruled out"]  # English fallback


def get_insider_handles(league_key: str) -> List[str]:
    """
    Get Twitter handles of beat writers and insider accounts.
    
    Args:
        league_key: API league key
        
    Returns:
        List of Twitter handles (with @)
    """
    country = get_country_from_league(league_key)
    if country:
        return INSIDER_HANDLES.get(country, [])
    return []


def get_telegram_channels(league_key: str) -> List[str]:
    """
    Get Telegram insider channels for a league.
    
    Args:
        league_key: API league key
        
    Returns:
        List of Telegram channel usernames
    """
    country = get_country_from_league(league_key)
    if country:
        return TELEGRAM_INSIDERS.get(country, [])
    return []


def get_all_telegram_channels() -> dict:
    """
    Get all configured Telegram channels grouped by country.
    
    V4.4: Now includes global aggregator channels in each country's list.
    Global channels (key "_global") are appended to all country lists.
    
    Returns:
        Dict of country -> list of channel usernames (including global aggregators)
    """
    # Get global channels that apply to all leagues
    global_channels = TELEGRAM_INSIDERS.get("_global", [])
    
    result = {}
    for country, channels in TELEGRAM_INSIDERS.items():
        # Skip the _global key itself
        if country == "_global":
            continue
        
        # Combine country-specific + global channels
        combined = list(channels) if channels else []
        combined.extend(global_channels)
        
        # Only include if there are channels
        if combined:
            result[country] = combined
    
    return result


def get_telegram_channels(league_key: str) -> List[str]:
    """
    Get Telegram channels for a specific league.
    
    V4.4: Includes global aggregator channels automatically.
    
    Args:
        league_key: API league key (e.g., 'soccer_turkey_super_league')
        
    Returns:
        List of Telegram channel usernames
    """
    country = get_country_from_league(league_key)
    if not country:
        # Return only global channels for unknown leagues
        return TELEGRAM_INSIDERS.get("_global", [])
    
    # Get country-specific channels
    country_channels = TELEGRAM_INSIDERS.get(country, [])
    
    # Add global channels
    global_channels = TELEGRAM_INSIDERS.get("_global", [])
    
    # Combine and deduplicate
    combined = list(country_channels) + [c for c in global_channels if c not in country_channels]
    
    return combined


# ============================================
# V4.3: BEAT WRITER FUNCTIONS
# ============================================

def get_beat_writers(league_key: str) -> List[BeatWriter]:
    """
    V4.3: Get beat writers for a league.
    
    Beat writers are searched BEFORE generic searches for priority intel.
    Results from beat writers get confidence="HIGH" and priority_boost=1.5.
    
    Args:
        league_key: API league key (e.g., 'soccer_argentina_primera_division')
        
    Returns:
        List of BeatWriter objects for the league
    """
    country = get_country_from_league(league_key)
    if country:
        return BEAT_WRITERS_DB.get(country, [])
    return []


def get_beat_writer_handles(league_key: str) -> List[str]:
    """
    V4.3: Get just the Twitter handles of beat writers for a league.
    
    Convenience function for search queries.
    
    Args:
        league_key: API league key
        
    Returns:
        List of Twitter handles (with @)
    """
    writers = get_beat_writers(league_key)
    return [w.handle for w in writers]


def get_beat_writer_by_handle(handle: str, league_key: str = None) -> Optional[BeatWriter]:
    """
    V4.3: Look up a beat writer by their Twitter handle.
    
    Args:
        handle: Twitter handle (with or without @)
        league_key: Optional league to narrow search
        
    Returns:
        BeatWriter object or None if not found
    """
    # Normalize handle
    if not handle.startswith('@'):
        handle = f'@{handle}'
    handle_lower = handle.lower()
    
    # Search in specific league or all leagues
    if league_key:
        writers = get_beat_writers(league_key)
        for writer in writers:
            if writer.handle.lower() == handle_lower:
                return writer
    else:
        # Search all leagues
        for country_writers in BEAT_WRITERS_DB.values():
            for writer in country_writers:
                if writer.handle.lower() == handle_lower:
                    return writer
    
    return None


def build_site_dork_query(team_name: str, league_key: str) -> str:
    """
    Build a Serper query with site-dorking for local sources.
    
    Example output:
        "River Plate lesionados site:ole.com.ar OR site:tycsports.com"
    
    Args:
        team_name: Team to search for
        league_key: League key to determine sources
        
    Returns:
        Formatted search query with site operators
    """
    sources = get_sources_for_league(league_key)
    keywords = get_keywords_for_league(league_key)
    
    if not sources:
        # Fallback to generic search
        return f"{team_name} injury lineup news"
    
    # Build site-dork string
    site_dork = " OR ".join([f"site:{domain}" for domain in sources])
    
    # Use first keyword (most common injury term)
    keyword = keywords[0] if keywords else "injury"
    
    return f"{team_name} {keyword} ({site_dork})"


# ============================================
# V8.1: SOURCE TIERS DATABASE
# ============================================
# Assigns credibility tier and weight to news sources.
# Used by news_scorer.py to calculate news importance.
#
# TIER 1 (weight 1.0): Official club/league sources, major broadcasters
# TIER 2 (weight 0.8): Reputable sports newspapers, beat writers
# TIER 3 (weight 0.5): Aggregators, blogs, unverified sources
#
# Format: domain -> (tier, weight, source_type)

@dataclass
class SourceTier:
    """Credibility tier for a news source."""
    tier: int           # 1, 2, or 3
    weight: float       # 0.0-1.0 credibility multiplier
    source_type: str    # "official", "newspaper", "broadcaster", "aggregator", "blog"


# ============================================
# V9.5: WHITE-LIST CACHING (Zero-Maintenance Strategy)
# ============================================
# All sources in Supabase are Tier 1 (Maximum Trust)
# This eliminates the need for manual SOURCE_TIERS_DB maintenance

_TRUSTED_DOMAINS_CACHE: Set[str] = set()
_TRUSTED_HANDLES_CACHE: Set[str] = set()
_WHITE_LIST_INITIALIZED = False


def _initialize_white_list() -> None:
    """
    Initialize white-list cache from Supabase.
    
    Fetches all news_sources (domains) and social_sources (handles)
    and caches them in memory for fast lookups.
    """
    global _TRUSTED_DOMAINS_CACHE, _TRUSTED_HANDLES_CACHE, _WHITE_LIST_INITIALIZED
    
    if _WHITE_LIST_INITIALIZED:
        return
    
    try:
        from src.database.supabase_provider import get_supabase
        supabase = get_supabase()
        
        # Fetch all news sources (domains)
        all_news_sources = supabase.fetch_all_news_sources()
        for source in all_news_sources:
            domain = source.get('domain', '').strip().lower()
            if domain:
                # Remove www. prefix for normalization
                if domain.startswith('www.'):
                    domain = domain[4:]
                _TRUSTED_DOMAINS_CACHE.add(domain)
        
        # Fetch all social sources (Twitter handles)
        all_social_sources = supabase.get_social_sources()
        for source in all_social_sources:
            handle = source.get('identifier', '').strip().lower()
            if handle:
                # Ensure handle starts with @
                if not handle.startswith('@'):
                    handle = f"@{handle.lstrip('@')}"
                _TRUSTED_HANDLES_CACHE.add(handle)
        
        _WHITE_LIST_INITIALIZED = True
        logger.info(f"✅ [WHITE-LIST] Initialized with {len(_TRUSTED_DOMAINS_CACHE)} domains and {len(_TRUSTED_HANDLES_CACHE)} handles")
        
    except Exception as e:
        logger.warning(f"⚠️ [WHITE-LIST] Failed to initialize from Supabase: {e}")
        # Fall back to empty cache - will use DEFAULT_SOURCE_TIER


def get_trust_score(url_or_handle: str) -> SourceTier:
    """
    Get trust score for a source using white-list logic.
    
    RULE: If source is in Supabase (news_sources or social_sources),
    it's Tier 1 (Maximum Trust). Otherwise, it's Tier 3 (Low Trust).
    
    Args:
        url_or_handle: Full URL, domain, or Twitter handle of the source
        
    Returns:
        SourceTier with tier, weight, and source_type
    """
    # Initialize white-list on first call
    if not _WHITE_LIST_INITIALIZED:
        _initialize_white_list()
    
    if not url_or_handle:
        return DEFAULT_SOURCE_TIER
    
    # Normalize input
    normalized = url_or_handle.strip().lower()
    
    # Check if it's a Twitter handle
    if normalized.startswith('@') or normalized.startswith('twitter.com/') or normalized.startswith('x.com/'):
        # Extract handle
        if normalized.startswith('@'):
            handle = normalized
        elif 'twitter.com/' in normalized:
            handle = f"@{normalized.split('twitter.com/')[1].split('/')[0]}"
        elif 'x.com/' in normalized:
            handle = f"@{normalized.split('x.com/')[1].split('/')[0]}"
        else:
            handle = normalized
        
        # Check white-list
        if handle in _TRUSTED_HANDLES_CACHE:
            return SourceTier(1, 1.0, "social")
        else:
            return SourceTier(3, 0.5, "social")
    
    # It's a URL/domain
    # Remove protocol
    if "://" in normalized:
        normalized = normalized.split("://")[1]
    
    # Remove path
    domain = normalized.split("/")[0]
    
    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Check white-list
    if domain in _TRUSTED_DOMAINS_CACHE:
        return SourceTier(1, 1.0, "official")
    
    # Not in white-list - return Tier 3 (Low Trust)
    return SourceTier(3, 0.5, "unknown")

# ============================================
# V8.1: SOURCE TIERS DATABASE (DEPRECATED - REPLACED BY WHITE-LIST)
# ============================================
# Assigns credibility tier and weight to news sources.
# Used by news_scorer.py to calculate news importance.
#
# TIER 1 (weight 1.0): Official club/league sources, major broadcasters
# TIER 2 (weight 0.8): Reputable sports newspapers, beat writers
# TIER 3 (weight 0.5): Aggregators, blogs, unverified sources
#
# Format: domain -> (tier, weight, source_type)
#
# DEPRECATED: Now using Supabase white-list strategy (get_trust_score)
# All sources in Supabase are Tier 1 (Maximum Trust)
# This dictionary is kept for reference but no longer used
# Last updated: 2026-02-13
# Migration status: Replaced by white-list logic

# SOURCE_TIERS_DB = {
#     # ============================================
#     # TIER 1 - Official & Major Broadcasters (weight 1.0)
#     # ============================================
#     # These sources have direct access or official status
#     "aleagues.com.au": SourceTier(1, 1.0, "official"),
#     "bbc.com": SourceTier(1, 1.0, "broadcaster"),
#     "bbc.co.uk": SourceTier(1, 1.0, "broadcaster"),
#     "sky.it": SourceTier(1, 1.0, "broadcaster"),
#     "skysports.com": SourceTier(1, 1.0, "broadcaster"),
#     "espn.com": SourceTier(1, 0.95, "broadcaster"),
#     "espn.com.mx": SourceTier(1, 0.95, "broadcaster"),
#     "nikkansports.com": SourceTier(1, 0.95, "official"),
#
#     # ============================================
#     # TIER 2 - Major Sports Newspapers (weight 0.8)
#     # ============================================
#     # Reputable newspapers with sports sections
#     "gazzetta.it": SourceTier(2, 0.85, "newspaper"),
#     "gazzetta.gr": SourceTier(2, 0.85, "newspaper"),
#     "ole.com.ar": SourceTier(2, 0.85, "newspaper"),
#     "tycsports.com": SourceTier(2, 0.85, "broadcaster"),
#     "mediotiempo.com": SourceTier(2, 0.85, "newspaper"),
#     "record.com.mx": SourceTier(2, 0.80, "newspaper"),
#     "fanatik.com.tr": SourceTier(2, 0.80, "newspaper"),
#     "sporx.com": SourceTier(2, 0.80, "newspaper"),
#     "sdna.gr": SourceTier(2, 0.80, "newspaper"),
#     "contra.gr": SourceTier(2, 0.75, "newspaper"),
#     "dailyrecord.co.uk": SourceTier(2, 0.80, "newspaper"),
#     "thescottishsun.co.uk": SourceTier(2, 0.75, "newspaper"),
#     "foxsports.com.au": SourceTier(2, 0.85, "broadcaster"),
#     "keepup.com.au": SourceTier(2, 0.80, "newspaper"),
#     "lance.com.br": SourceTier(2, 0.80, "newspaper"),
#     "globoesporte.globo.com": SourceTier(2, 0.85, "broadcaster"),
#     "football-italia.net": SourceTier(2, 0.80, "aggregator"),
#     "yallakora.com": SourceTier(2, 0.80, "newspaper"),
#     "filgoal.com": SourceTier(2, 0.80, "newspaper"),
#     "kingfut.com": SourceTier(2, 0.75, "newspaper"),
#     "infobae.com": SourceTier(2, 0.75, "newspaper"),
#     "sabah.com.tr": SourceTier(2, 0.75, "newspaper"),
#     "soccerdigestweb.com": SourceTier(2, 0.80, "newspaper"),
#     "football-zone.net": SourceTier(2, 0.75, "newspaper"),
#
#     # ============================================
#     # TIER 3 - Aggregators & Blogs (weight 0.5)
#     # ============================================
#     # Less reliable, often repost from other sources
#     "twitter.com": SourceTier(3, 0.6, "social"),  # Variable - depends on account
#     "x.com": SourceTier(3, 0.6, "social"),
#     "reddit.com": SourceTier(3, 0.4, "social"),
#     "dongqiudi.com": SourceTier(3, 0.6, "aggregator"),
#     "calciomercato.com": SourceTier(3, 0.5, "aggregator"),
#     "transfermarkt.com": SourceTier(3, 0.7, "database"),  # Good for data, not breaking news
# }

# Default tier for unknown sources
DEFAULT_SOURCE_TIER = SourceTier(3, 0.5, "unknown")


# ============================================
# DEPRECATED: get_source_tier() - REPLACED BY get_trust_score()
# ============================================
# This function has been replaced by get_trust_score() which uses
# Supabase white-list logic instead of local SOURCE_TIERS_DB
# Last updated: 2026-02-13
# Migration status: Replaced by white-list logic

# def get_source_tier(url: str) -> SourceTier:
#     """
#     Get the credibility tier for a news source URL.
#
#     Args:
#         url: Full URL or domain of the news source
#
#     Returns:
#         SourceTier with tier, weight, and source_type
#     """
#     if not url:
#         return DEFAULT_SOURCE_TIER
#
#     # Extract domain from URL
#     url_lower = url.lower()
#
#     # Remove protocol
#     if "://" in url_lower:
#         url_lower = url_lower.split("://")[1]
#
#     # Remove path
#     domain = url_lower.split("/")[0]
#
#     # Remove www.
#     if domain.startswith("www."):
#         domain = domain[4:]
#
#     # Check exact match first
#     if domain in SOURCE_TIERS_DB:
#         return SOURCE_TIERS_DB[domain]
#
#     # Check if domain ends with any known domain (for subdomains)
#     for known_domain, tier in SOURCE_TIERS_DB.items():
#         if domain.endswith(known_domain) or known_domain in domain:
#             return tier
#
#     return DEFAULT_SOURCE_TIER


def get_source_weight(url: str) -> float:
    """
    Get credibility weight (0.0-1.0) for a news source URL.
    
    Args:
        url: Full URL or domain of the news source
        
    Returns:
        Credibility weight between 0.0 and 1.0
    """
    return get_trust_score(url).weight


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("🌍 9-LEAGUE FINAL STRATEGY - SOURCES CONFIG")
    print("=" * 60)
    print("V8.0: Reddit monitoring removed (no betting edge)")
    
    test_leagues = [
        # Core leagues
        "soccer_turkey_super_league",
        "soccer_argentina_primera_division",
        "soccer_mexico_ligamx",
        "soccer_greece_super_league",
        "soccer_spl",
        # Australia focus
        "soccer_australia_aleague",
        # Seasonal leagues
        "soccer_china_superleague",
        "soccer_japan_j_league",
        "soccer_brazil_serie_b",
    ]
    
    for league in test_leagues:
        country = get_country_from_league(league)
        sources = get_sources_for_league(league)
        keywords = get_keywords_for_league(league)
        telegram = get_telegram_channels(league)
        
        print(f"\n📰 {league}")
        print(f"   Country: {country}")
        print(f"   Sources: {', '.join(sources)}")
        print(f"   Keywords: {', '.join(keywords[:3])}")
        print(f"   Telegram: {', '.join(telegram) if telegram else 'None'}")
        
        # Example query
        query = build_site_dork_query("Test Team", league)
        print(f"   Example Query: {query[:60]}...")
