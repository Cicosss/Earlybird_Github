"""
League Manager - Tiered League Strategy

TIER 1 (Gold List): Always scanned every cycle
TIER 2 (Rotation): Round-robin, 2-3 leagues per cycle

News Hunt Gating:
- Tier 1: Search if odds drop > 5% OR FotMob warning
- Tier 2: Search ONLY if odds drop > 15% OR FotMob HIGH RISK

V10.0: Hybrid Supabase Integration
- Primary: Fetch leagues from Supabase database
- Fallback: Use hardcoded TIER_1/TIER_2 lists if Supabase unavailable
"""
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Set, Optional, Any

import requests

from config.settings import ODDS_API_KEY

logger = logging.getLogger(__name__)

# ============================================
# V10.0: SUPABASE INTEGRATION
# ============================================
try:
    from src.database.supabase_provider import get_supabase
    _SUPABASE_AVAILABLE = True
    logger.info("✅ Supabase Provider available for league management")
except ImportError as e:
    _SUPABASE_AVAILABLE = False
    logger.warning(f"⚠️ Supabase Provider not available: {e}")

BASE_URL = "https://api.the-odds-api.com/v4"

# Connection pooling
_session: Optional[requests.Session] = None
_session_lock: threading.Lock = threading.Lock()

# Maximum leagues to process per run (API quota management)
MAX_LEAGUES_PER_RUN = 12


def _get_session() -> requests.Session:
    """Get or create reusable requests session (thread-safe)."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                _session.headers.update({
                    'User-Agent': 'EarlyBird/7.0'
                })
    return _session


def _close_session() -> None:
    """Close the requests session (call on shutdown)."""
    global _session
    with _session_lock:
        if _session is not None:
            _session.close()
            _session = None
            logger.debug("🔌 Requests session closed")


# ============================================
# TIER 1 - ELITE 7 (Always Scanned)
# ============================================
TIER_1_LEAGUES: List[str] = [
    "soccer_turkey_super_league",         # Turkey Süper Lig
    "soccer_argentina_primera_division",  # Argentina Primera División
    "soccer_mexico_ligamx",               # Mexico Liga MX
    "soccer_greece_super_league",         # Greece Super League
    "soccer_spl",                         # Scotland Premiership
    "soccer_australia_aleague",           # Australia A-League
    "soccer_poland_ekstraklasa",          # Poland Ekstraklasa
]

# ============================================
# TIER 2 - FALLBACK LEAGUES (8 leghe in rotazione)
# ============================================
# Tier 2 riabilitato per Fallback System V4.3
# Attivato quando Tier 1 è silenzioso (Trigger D)
TIER_2_LEAGUES: List[str] = [
    "soccer_norway_eliteserien",
    "soccer_france_ligue_one",
    "soccer_belgium_first_div",
    "soccer_austria_bundesliga",
    "soccer_netherlands_eredivisie",
    "soccer_china_superleague",
    "soccer_japan_j_league",
    "soccer_brazil_serie_b",
]

# Round-robin state
_tier2_index: int = 0
_tier2_index_lock: threading.Lock = threading.Lock()
TIER_2_PER_CYCLE: int = 3

# ============================================
# TIER 2 FALLBACK STATE (V4.3)
# ============================================
_consecutive_dry_cycles: int = 0
_tier2_activations_today: int = 0
_last_tier2_activation_cycle: int = 0
_current_cycle: int = 0
_last_reset_date: str = ""
_tier2_fallback_index: int = 0  # Separate index for fallback rotation
_state_lock: threading.Lock = threading.Lock()  # Lock for state modifications

# Fallback configuration
TIER2_FALLBACK_BATCH_SIZE: int = 3  # Leghe per attivazione
TIER2_FALLBACK_COOLDOWN: int = 3    # Cicli di cooldown dopo attivazione
TIER2_FALLBACK_DAILY_LIMIT: int = 3 # Max attivazioni/giorno
TIER2_DRY_CYCLES_THRESHOLD: int = 2 # Cicli secchi prima di attivare fallback

# Combined for validation
ALL_LEAGUES: List[str] = TIER_1_LEAGUES + TIER_2_LEAGUES
ALL_LEAGUES_SET: Set[str] = set(ALL_LEAGUES)

# Backward compatibility alias
ELITE_LEAGUES: List[str] = TIER_1_LEAGUES

# ============================================
# V10.0: SUPABASE LEAGUE FETCHING WITH FALLBACK
# ============================================

def _fetch_tier1_from_supabase() -> Optional[List[str]]:
    """
    Fetch Tier 1 leagues from Supabase (priority=1).
    
    Returns:
        List of league api_keys with priority=1, or None if Supabase unavailable
    """
    if not _SUPABASE_AVAILABLE:
        return None
    
    try:
        sb = get_supabase()
        if not sb:
            return None
        
        leagues = sb.get_active_leagues()
        
        # Filter for priority=1 (Tier 1)
        tier1_leagues = [
            league.get('api_key') 
            for league in leagues 
            if league.get('priority') == 1 and league.get('api_key')
        ]
        
        if tier1_leagues:
            logger.info(f"✅ [SUPABASE] Fetched {len(tier1_leagues)} Tier 1 leagues from database")
            return tier1_leagues
        else:
            logger.warning("⚠️ [SUPABASE] No Tier 1 leagues found (priority=1)")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ [SUPABASE] Failed to fetch Tier 1 leagues: {e}")
        return None


def _fetch_tier2_from_supabase() -> Optional[List[str]]:
    """
    Fetch Tier 2 leagues from Supabase (priority=2).
    
    Returns:
        List of league api_keys with priority=2, or None if Supabase unavailable
    """
    if not _SUPABASE_AVAILABLE:
        return None
    
    try:
        sb = get_supabase()
        if not sb:
            return None
        
        leagues = sb.get_active_leagues()
        
        # Filter for priority=2 (Tier 2)
        tier2_leagues = [
            league.get('api_key') 
            for league in leagues 
            if league.get('priority') == 2 and league.get('api_key')
        ]
        
        if tier2_leagues:
            logger.info(f"✅ [SUPABASE] Fetched {len(tier2_leagues)} Tier 2 leagues from database")
            return tier2_leagues
        else:
            logger.info("ℹ️ [SUPABASE] No Tier 2 leagues found (priority=2)")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ [SUPABASE] Failed to fetch Tier 2 leagues: {e}")
        return None


def get_tier1_leagues() -> List[str]:
    """
    Get Tier 1 leagues with Supabase-first strategy.
    
    Priority:
    1. Try Supabase (priority=1 leagues)
    2. Fallback to hardcoded TIER_1_LEAGUES
    
    Returns:
        List of Tier 1 league keys
    """
    # Try Supabase first
    tier1_from_supabase = _fetch_tier1_from_supabase()
    
    if tier1_from_supabase:
        return tier1_from_supabase
    
    # Fallback to hardcoded list
    logger.info("🔄 [FALLBACK] Using hardcoded TIER_1_LEAGUES")
    return TIER_1_LEAGUES.copy()


def get_tier2_leagues() -> List[str]:
    """
    Get Tier 2 leagues with Supabase-first strategy.
    
    Priority:
    1. Try Supabase (priority=2 leagues)
    2. Fallback to hardcoded TIER_2_LEAGUES
    
    Returns:
        List of Tier 2 league keys
    """
    # Try Supabase first
    tier2_from_supabase = _fetch_tier2_from_supabase()
    
    if tier2_from_supabase:
        return tier2_from_supabase
    
    # Fallback to hardcoded list
    logger.info("🔄 [FALLBACK] Using hardcoded TIER_2_LEAGUES")
    return TIER_2_LEAGUES.copy()


# ============================================
# V10.0: CONTINENTAL BRAIN - "Follow the Sun" LOGIC
# ============================================

def get_active_leagues_for_continental_blocks() -> List[str]:
    """
    Get active leagues for current continental blocks based on UTC time.
    
    V10.0: Implements "Follow the Sun" logic:
    1. Query Supabase to find which Continental Blocks (LATAM, ASIA, AFRICA) are active
       based on active_hours_utc array
    2. Filter leagues to ONLY those belonging to active continents
    3. Fail-safe: Fallback to data/supabase_mirror.json if Supabase unreachable
    
    Returns:
        List of active league api_keys for current continental blocks
    """
    if not _SUPABASE_AVAILABLE:
        logger.warning("⚠️ [CONTINENTAL] Supabase not available, using fallback")
        return _get_continental_fallback()
    
    try:
        sb = get_supabase()
        if not sb:
            logger.warning("⚠️ [CONTINENTAL] Supabase provider not initialized, using fallback")
            return _get_continental_fallback()
        
        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour
        
        # Get active continental blocks for current hour
        active_blocks = sb.get_active_continent_blocks(current_utc_hour)
        
        if not active_blocks:
            logger.warning(f"⚠️ [CONTINENTAL] No active continental blocks at {current_utc_hour}:00 UTC")
            return []
        
        logger.info(f"✅ [CONTINENTAL] Active blocks at {current_utc_hour}:00 UTC: {active_blocks}")
        
        # Get all active leagues from Supabase
        all_active_leagues = sb.get_active_leagues()
        
        if not all_active_leagues:
            logger.warning("⚠️ [CONTINENTAL] No active leagues found in Supabase")
            return _get_continental_fallback()
        
        # Filter leagues by active continental blocks
        active_leagues = []
        for league in all_active_leagues:
            continent_name = league.get("continent", {}).get("name")
            if continent_name in active_blocks:
                api_key = league.get("api_key")
                if api_key:
                    active_leagues.append(api_key)
        
        if active_leagues:
            logger.info(f"✅ [CONTINENTAL] Identified {len(active_leagues)} active leagues for blocks: {active_blocks}")
            return active_leagues
        else:
            logger.warning(f"⚠️ [CONTINENTAL] No leagues found for active blocks: {active_blocks}")
            return []
            
    except Exception as e:
        logger.error(f"❌ [CONTINENTAL] Error fetching continental leagues: {e}")
        return _get_continental_fallback()


def _get_continental_fallback() -> List[str]:
    """
    Fallback to mirror file when Supabase is unreachable.
    
    Returns:
        List of league api_keys from mirror or empty list
    """
    try:
        import json
        from pathlib import Path
        
        mirror_path = Path("data/supabase_mirror.json")
        
        if not mirror_path.exists():
            logger.warning("⚠️ [CONTINENTAL] Mirror file not found: data/supabase_mirror.json")
            return []
        
        with open(mirror_path, 'r', encoding='utf-8') as f:
            mirror_data = json.load(f)
        
        # Mirror data is nested under "data" key
        data = mirror_data.get("data", {})
        
        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour
        
        # Get active continents from mirror
        continents = data.get("continents", [])
        active_blocks = []
        for continent in continents:
            active_hours = continent.get("active_hours_utc", [])
            if current_utc_hour in active_hours:
                active_blocks.append(continent.get("name"))
        
        if not active_blocks:
            logger.warning(f"⚠️ [CONTINENTAL] No active continental blocks at {current_utc_hour}:00 UTC (mirror)")
            return []
        
        logger.info(f"✅ [CONTINENTAL] Active blocks from mirror at {current_utc_hour}:00 UTC: {active_blocks}")
        
        # Get leagues and countries from mirror
        leagues = data.get("leagues", [])
        countries = data.get("countries", [])
        
        # Build country_id -> continent_id mapping
        country_to_continent = {
            c["id"]: c.get("continent_id") 
            for c in countries 
            if "id" in c and "continent_id" in c
        }
        
        # Build continent_id -> continent_name mapping
        continent_map = {
            c["id"]: c.get("name") 
            for c in continents 
            if "id" in c and "name" in c
        }
        
        # Filter leagues by active continental blocks
        active_leagues = []
        for league in leagues:
            country_id = league.get("country_id")
            if not country_id:
                continue
            
            continent_id = country_to_continent.get(country_id)
            if not continent_id:
                continue
            
            continent_name = continent_map.get(continent_id)
            if continent_name in active_blocks:
                api_key = league.get("api_key")
                if api_key:
                    active_leagues.append(api_key)
        
        if active_leagues:
            logger.info(f"✅ [CONTINENTAL] Identified {len(active_leagues)} active leagues from mirror for blocks: {active_blocks}")
            return active_leagues
        else:
            logger.warning(f"⚠️ [CONTINENTAL] No leagues found for active blocks in mirror: {active_blocks}")
            return []
            
    except Exception as e:
        logger.error(f"❌ [CONTINENTAL] Error loading mirror fallback: {e}")
        return []

# Priority (higher = processed first)
LEAGUE_PRIORITY: Dict[str, int] = {
    # Elite 7
    "soccer_turkey_super_league": 100,
    "soccer_argentina_primera_division": 98,
    "soccer_mexico_ligamx": 96,
    "soccer_greece_super_league": 94,
    "soccer_spl": 92,
    "soccer_australia_aleague": 90,
    "soccer_poland_ekstraklasa": 88,
}

# ============================================
# REGION MAPPINGS (Elite 7 only)
# ============================================
LATAM_LEAGUES: Set[str] = {
    "soccer_argentina_primera_division",
    "soccer_mexico_ligamx",
}

AUSTRALIA_LEAGUES: Set[str] = {
    "soccer_australia_aleague",
}

ASIA_LEAGUES: Set[str] = set()  # Disabled with Tier 2

EUROPE_LEAGUES: Set[str] = {
    "soccer_turkey_super_league",
    "soccer_greece_super_league",
    "soccer_spl",
    "soccer_france_ligue_one",
}


# ============================================
# API FUNCTIONS
# ============================================
def fetch_all_sports() -> List[Dict[str, Any]]:
    """
    Fetch all active sports from The-Odds-API (FREE endpoint).
    
    Returns:
        List of sports/leagues dictionaries
    """
    if not ODDS_API_KEY or ODDS_API_KEY == "YOUR_ODDS_API_KEY":
        logger.warning("⚠️ ODDS_API_KEY not configured")
        return []
    
    try:
        url = f"{BASE_URL}/sports"
        params = {"apiKey": ODDS_API_KEY}
        response = _get_session().get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Sports API error: {response.status_code}")
            return []
        
        sports = response.json()
        logger.info(f"📊 Fetched {len(sports)} sports/leagues from API")
        return sports
        
    except requests.exceptions.Timeout:
        logger.error("⏱️ Timeout fetching sports from API")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 Network error fetching sports: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Error fetching sports: {e}", exc_info=True)
        return []


def get_quota_status() -> Dict[str, Any]:
    """
    Get current API quota status.
    
    Returns:
        Dict with requests_used and requests_remaining
    """
    try:
        url = f"{BASE_URL}/sports"
        params = {"apiKey": ODDS_API_KEY}
        response = _get_session().get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Quota check failed: {response.status_code}")
            return {"requests_used": "error", "requests_remaining": "error"}
        
        return {
            "requests_used": response.headers.get("x-requests-used", "unknown"),
            "requests_remaining": response.headers.get("x-requests-remaining", "unknown"),
        }
    except requests.exceptions.Timeout:
        logger.error("⏱️ Timeout checking quota")
        return {"requests_used": "timeout", "requests_remaining": "timeout"}
    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 Network error checking quota: {e}")
        return {"requests_used": "error", "requests_remaining": "error"}
    except Exception as e:
        logger.error(f"❌ Error checking quota: {e}", exc_info=True)
        return {"requests_used": "error", "requests_remaining": "error"}


# ============================================
# TIER FUNCTIONS
# ============================================
def is_tier1_league(sport_key: str) -> bool:
    """Check if league is Tier 1 (Gold List)."""
    return sport_key in TIER_1_LEAGUES


def is_tier2_league(sport_key: str) -> bool:
    """Check if league is Tier 2 (Rotation)."""
    return sport_key in TIER_2_LEAGUES


def is_elite_league(sport_key: str) -> bool:
    """Check if league is Tier 1. Alias for backward compatibility."""
    return is_tier1_league(sport_key)


def is_niche_league(sport_key: str) -> bool:
    """Check if league is in our verified list (Tier 1 or Tier 2)."""
    return sport_key in ALL_LEAGUES_SET


def get_league_priority(sport_key: str) -> int:
    """Get priority score (higher = more important)."""
    return LEAGUE_PRIORITY.get(sport_key, 10)


def get_league_tier(sport_key: str) -> str:
    """Get tier label for a league."""
    if is_tier1_league(sport_key):
        return "TIER1"
    elif is_tier2_league(sport_key):
        return "TIER2"
    return "OTHER"


# ============================================
# REGION FUNCTIONS
# ============================================
def is_latam_league(sport_key: str) -> bool:
    return sport_key in LATAM_LEAGUES


def is_australia_league(sport_key: str) -> bool:
    return sport_key in AUSTRALIA_LEAGUES


def is_asia_league(sport_key: str) -> bool:
    return sport_key in ASIA_LEAGUES


def is_europe_league(sport_key: str) -> bool:
    return sport_key in EUROPE_LEAGUES


def get_regions_for_league(sport_key: str) -> str:
    """Get appropriate regions parameter for Odds API."""
    if is_australia_league(sport_key):
        return "au,uk,eu"
    if is_asia_league(sport_key):
        return "eu,uk,au"
    if is_latam_league(sport_key):
        return "us,eu"
    return "eu,uk"


# ============================================
# CYCLE MANAGEMENT
# ============================================
def get_tier2_for_cycle() -> List[str]:
    """
    Get next batch of Tier 2 leagues (round-robin).
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Thread-safe implementation.
    
    Returns:
        List of Tier 2 league keys for this cycle
    """
    global _tier2_index
    
    # Get Tier 2 leagues from Supabase or fallback
    tier2_leagues = get_tier2_leagues()
    
    if not tier2_leagues:
        return []
    
    with _tier2_index_lock:
        # Wrap around
        start = _tier2_index % len(tier2_leagues)
        
        # Get next batch
        batch = []
        for i in range(TIER_2_PER_CYCLE):
            idx = (start + i) % len(tier2_leagues)
            batch.append(tier2_leagues[idx])
        
        # Advance index for next cycle
        _tier2_index = (start + TIER_2_PER_CYCLE) % len(tier2_leagues)
    
    return batch


def get_leagues_for_cycle(emergency_mode: bool = False) -> List[str]:
    """
    Get leagues to fetch for this cycle.
    
    V10.0: Uses Continental Brain logic with Supabase-first strategy.
    
    Normal: Active leagues for current continental blocks (based on UTC time)
    Emergency: Tier 1 only (fallback)
    
    Args:
        emergency_mode: If True, only return Tier 1 leagues
        
    Returns:
        List of league keys to process
    """
    if emergency_mode:
        logger.info("🚨 Emergency mode: Tier 1 only")
        return get_tier1_leagues()
    
    # V10.0: Use Continental Brain logic
    leagues = get_active_leagues_for_continental_blocks()
    
    if not leagues:
        logger.warning("⚠️ No active leagues for current continental blocks, using Tier 1 fallback")
        leagues = get_tier1_leagues()
    
    # Limit to MAX_LEAGUES_PER_RUN for API quota management
    if len(leagues) > MAX_LEAGUES_PER_RUN:
        logger.info(f"⚠️ Limiting leagues from {len(leagues)} to {MAX_LEAGUES_PER_RUN} (API quota)")
        leagues = leagues[:MAX_LEAGUES_PER_RUN]
    
    logger.info(f"🎯 Cycle: {len(leagues)} active leagues for current continental blocks")
    
    return leagues


def get_active_niche_leagues(max_leagues: int = 12) -> List[str]:
    """
    Get active leagues from our verified list.
    Checks API for currently active leagues.
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Args:
        max_leagues: Maximum number of leagues to return
        
    Returns:
        List of active league keys sorted by priority
    """
    logger.info("🔍 Checking for active leagues...")
    
    all_sports = fetch_all_sports()
    
    if not all_sports:
        logger.warning("⚠️ No sports data - using fallback")
        return get_leagues_for_cycle()
    
    active_keys = {s['key'] for s in all_sports if s.get('active', False)}
    
    # Filter our leagues that are active
    tier1_leagues = get_tier1_leagues()
    tier2_leagues = get_tier2_leagues()
    
    active_tier1 = [l for l in tier1_leagues if l in active_keys]
    active_tier2 = [l for l in tier2_leagues if l in active_keys]
    
    logger.info(f"✅ Active: {len(active_tier1)} Tier1, {len(active_tier2)} Tier2")
    
    # Combine: all active Tier1 + rotating Tier2
    tier2_batch = [l for l in get_tier2_for_cycle() if l in active_keys]
    leagues = active_tier1 + tier2_batch
    
    # Sort by priority
    leagues.sort(key=lambda k: get_league_priority(k), reverse=True)
    
    return leagues[:max_leagues]


def get_elite_leagues() -> List[str]:
    """
    Get Tier 1 leagues. Alias for backward compatibility.
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Returns:
        List of Tier 1 league keys
    """
    return get_tier1_leagues()


def get_fallback_leagues() -> List[str]:
    """
    Fallback to Tier 1 if discovery fails.
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Returns:
        List of Tier 1 league keys
    """
    return get_tier1_leagues()


# ============================================
# TIER 2 FALLBACK SYSTEM (V4.3)
# ============================================
def _check_daily_reset() -> None:
    """
    Reset contatori giornalieri a mezzanotte.
    
    Thread-safe implementation using timezone-aware datetime.
    """
    global _tier2_activations_today, _last_reset_date
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    with _state_lock:
        if _last_reset_date != today:
            logger.info(f"🔄 Tier 2 Fallback: Reset giornaliero ({_last_reset_date} → {today})")
            _tier2_activations_today = 0
            _last_reset_date = today


def increment_cycle() -> None:
    """
    Incrementa il contatore cicli (chiamato da main.py ad ogni ciclo).
    
    Thread-safe implementation.
    """
    global _current_cycle
    
    with _state_lock:
        _current_cycle += 1
    
    _check_daily_reset()


def should_activate_tier2_fallback(alerts_sent: int, high_potential_count: int) -> bool:
    """
    Trigger D: Attiva Tier 2 Fallback SE:
    - alerts_sent == 0
    - AND (high_potential_count == 0 OR consecutive_dry_cycles >= 2)
    - AND cooldown rispettato (3 cicli)
    - AND limite giornaliero non superato (3/giorno)
    
    Args:
        alerts_sent: Numero di alert inviati nel ciclo Tier 1
        high_potential_count: Numero di match high_potential trovati
        
    Returns:
        True se il fallback deve essere attivato
    """
    global _consecutive_dry_cycles, _tier2_activations_today
    global _last_tier2_activation_cycle, _current_cycle
    
    _check_daily_reset()
    
    with _state_lock:
        # Se ci sono stati alert, reset dry cycles e non attivare
        if alerts_sent > 0:
            if _consecutive_dry_cycles > 0:
                logger.info(f"✅ Tier 1 produttivo - Reset dry cycles ({_consecutive_dry_cycles} → 0)")
            _consecutive_dry_cycles = 0
            return False
        
        # Incrementa dry cycles (nessun alert)
        _consecutive_dry_cycles += 1
        logger.info(f"📉 Tier 1 silenzioso - Dry cycles: {_consecutive_dry_cycles}")
        
        # Check limite giornaliero
        if _tier2_activations_today >= TIER2_FALLBACK_DAILY_LIMIT:
            logger.info(f"⚠️ Tier 2 Fallback: Limite giornaliero raggiunto ({_tier2_activations_today}/{TIER2_FALLBACK_DAILY_LIMIT})")
            return False
        
        # Check cooldown (3 cicli dopo ultima attivazione)
        if _last_tier2_activation_cycle > 0:
            cycles_since_last = _current_cycle - _last_tier2_activation_cycle
            if cycles_since_last < TIER2_FALLBACK_COOLDOWN:
                logger.info(f"⏳ Tier 2 Fallback: Cooldown attivo ({cycles_since_last}/{TIER2_FALLBACK_COOLDOWN} cicli)")
                return False
        
        # Trigger D: high_potential == 0 OR dry_cycles >= threshold
        if high_potential_count == 0 or _consecutive_dry_cycles >= TIER2_DRY_CYCLES_THRESHOLD:
            reason = "no high_potential" if high_potential_count == 0 else f"dry_cycles >= {TIER2_DRY_CYCLES_THRESHOLD}"
            logger.info(f"🔄 Tier 2 Fallback: Trigger D attivato ({reason})")
            return True
        
        return False


def get_tier2_fallback_batch() -> List[str]:
    """
    Ottiene il prossimo batch di 3 leghe Tier 2 per il fallback (round-robin).
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Thread-safe implementation.
    
    Returns:
        Lista di 3 leghe Tier 2 in rotazione
    """
    global _tier2_fallback_index
    
    # Get Tier 2 leagues from Supabase or fallback
    tier2_leagues = get_tier2_leagues()
    
    if not tier2_leagues:
        logger.warning("⚠️ Tier 2 Fallback: Nessuna lega Tier 2 configurata")
        return []
    
    with _state_lock:
        batch = []
        for i in range(TIER2_FALLBACK_BATCH_SIZE):
            idx = (_tier2_fallback_index + i) % len(tier2_leagues)
            batch.append(tier2_leagues[idx])
        
        # Avanza l'indice per la prossima chiamata
        _tier2_fallback_index = (_tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE) % len(tier2_leagues)
        
        batch_num = (_tier2_fallback_index // TIER2_FALLBACK_BATCH_SIZE) % (len(tier2_leagues) // TIER2_FALLBACK_BATCH_SIZE + 1)
        total_batches = (len(tier2_leagues) + TIER2_FALLBACK_BATCH_SIZE - 1) // TIER2_FALLBACK_BATCH_SIZE
        
        logger.info(f"🔄 Tier 2 Fallback batch: {batch} (rotazione {batch_num}/{total_batches})")
    
    return batch


def record_tier2_activation() -> None:
    """
    Registra un'attivazione del fallback Tier 2.
    
    Thread-safe implementation.
    """
    global _tier2_activations_today, _last_tier2_activation_cycle, _current_cycle
    
    with _state_lock:
        _tier2_activations_today += 1
        _last_tier2_activation_cycle = _current_cycle
    
    logger.info(f"📊 Tier 2 Fallback: Attivazione registrata ({_tier2_activations_today}/{TIER2_FALLBACK_DAILY_LIMIT} oggi)")


def reset_daily_tier2_stats() -> None:
    """
    Reset manuale delle statistiche giornaliere Tier 2.
    
    Thread-safe implementation.
    """
    global _tier2_activations_today, _consecutive_dry_cycles
    
    with _state_lock:
        _tier2_activations_today = 0
        _consecutive_dry_cycles = 0
    
    logger.info("🔄 Tier 2 Fallback: Stats giornaliere resettate manualmente")


def get_tier2_fallback_status() -> Dict[str, Any]:
    """
    Ritorna lo stato corrente del sistema Tier 2 Fallback.
    
    V10.0: Uses Supabase-first strategy with fallback to hardcoded lists.
    
    Thread-safe implementation.
    
    Returns:
        Dict with current fallback status
    """
    _check_daily_reset()
    
    # Get Tier 2 leagues from Supabase or fallback
    tier2_leagues = get_tier2_leagues()
    
    with _state_lock:
        cycles_since_activation = _current_cycle - _last_tier2_activation_cycle if _last_tier2_activation_cycle > 0 else -1
        cooldown_remaining = max(0, TIER2_FALLBACK_COOLDOWN - cycles_since_activation) if cycles_since_activation >= 0 else 0
        
        return {
            "current_cycle": _current_cycle,
            "consecutive_dry_cycles": _consecutive_dry_cycles,
            "activations_today": _tier2_activations_today,
            "daily_limit": TIER2_FALLBACK_DAILY_LIMIT,
            "cooldown_remaining": cooldown_remaining,
            "last_activation_cycle": _last_tier2_activation_cycle,
            "next_batch_preview": tier2_leagues[_tier2_fallback_index:_tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE] if tier2_leagues else [],
        }


# ============================================
# CLI
# ============================================
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("=" * 60)
    print("🎯 TIERED LEAGUE STRATEGY")
    print("=" * 60)
    
    print("\n📋 TIER 1 (Gold List - Always Scanned):")
    for i, league in enumerate(TIER_1_LEAGUES, 1):
        print(f"  {i}. {league}")
    
    print(f"\n📋 TIER 2 (Rotation - {TIER_2_PER_CYCLE}/cycle):")
    for i, league in enumerate(TIER_2_LEAGUES, 1):
        print(f"  {i}. {league}")
    
    print("\n🔄 Simulating 3 cycles:")
    for cycle in range(3):
        batch = get_tier2_for_cycle()
        print(f"  Cycle {cycle+1}: {batch}")
    
    print("\n💰 API Quota:")
    quota = get_quota_status()
    print(f"  Used: {quota['requests_used']}")
    print(f"  Remaining: {quota['requests_remaining']}")
    
    # Cleanup session on exit
    _close_session()
