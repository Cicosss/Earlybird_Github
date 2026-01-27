"""
League Manager - Tiered League Strategy

TIER 1 (Gold List): Always scanned every cycle
TIER 2 (Rotation): Round-robin, 2-3 leagues per cycle

News Hunt Gating:
- Tier 1: Search if odds drop > 5% OR FotMob warning
- Tier 2: Search ONLY if odds drop > 15% OR FotMob HIGH RISK
"""
import requests
import logging
from datetime import datetime
from typing import List, Dict, Set, Optional
from config.settings import ODDS_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"

# Connection pooling
_session: Optional[requests.Session] = None

# Maximum leagues to process per run (API quota management)
MAX_LEAGUES_PER_RUN = 12


def _get_session() -> requests.Session:
    """Get or create reusable requests session."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


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
def fetch_all_sports() -> List[Dict]:
    """Fetch all active sports from The-Odds-API (FREE endpoint)."""
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
        
    except Exception as e:
        logger.error(f"Error fetching sports: {e}")
        return []


def get_quota_status() -> Dict:
    """Get current API quota status."""
    try:
        url = f"{BASE_URL}/sports"
        params = {"apiKey": ODDS_API_KEY}
        response = _get_session().get(url, params=params, timeout=10)
        
        return {
            "requests_used": response.headers.get("x-requests-used", "unknown"),
            "requests_remaining": response.headers.get("x-requests-remaining", "unknown"),
        }
    except Exception as e:
        logger.error(f"Error checking quota: {e}")
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
    """Get next batch of Tier 2 leagues (round-robin)."""
    global _tier2_index
    
    if not TIER_2_LEAGUES:
        return []
    
    # Wrap around
    start = _tier2_index % len(TIER_2_LEAGUES)
    
    # Get next batch
    batch = []
    for i in range(TIER_2_PER_CYCLE):
        idx = (start + i) % len(TIER_2_LEAGUES)
        batch.append(TIER_2_LEAGUES[idx])
    
    # Advance index for next cycle
    _tier2_index = (start + TIER_2_PER_CYCLE) % len(TIER_2_LEAGUES)
    
    return batch


def get_leagues_for_cycle(emergency_mode: bool = False) -> List[str]:
    """
    Get leagues to fetch for this cycle.
    
    Normal: Tier 1 + rotating Tier 2 batch
    Emergency: Tier 1 only
    """
    if emergency_mode:
        logger.info("🚨 Emergency mode: Tier 1 only")
        return TIER_1_LEAGUES.copy()
    
    tier2_batch = get_tier2_for_cycle()
    leagues = TIER_1_LEAGUES + tier2_batch
    
    logger.info(f"🎯 Cycle: {len(TIER_1_LEAGUES)} Tier1 + {len(tier2_batch)} Tier2 = {len(leagues)} leagues")
    logger.info(f"   Tier2 batch: {tier2_batch}")
    
    return leagues


def get_active_niche_leagues(max_leagues: int = 12) -> List[str]:
    """
    Get active leagues from our verified list.
    Checks API for currently active leagues.
    """
    logger.info("🔍 Checking for active leagues...")
    
    all_sports = fetch_all_sports()
    
    if not all_sports:
        logger.warning("⚠️ No sports data - using fallback")
        return get_leagues_for_cycle()
    
    active_keys = {s['key'] for s in all_sports if s.get('active', False)}
    
    # Filter our leagues that are active
    active_tier1 = [l for l in TIER_1_LEAGUES if l in active_keys]
    active_tier2 = [l for l in TIER_2_LEAGUES if l in active_keys]
    
    logger.info(f"✅ Active: {len(active_tier1)} Tier1, {len(active_tier2)} Tier2")
    
    # Combine: all active Tier1 + rotating Tier2
    tier2_batch = [l for l in get_tier2_for_cycle() if l in active_keys]
    leagues = active_tier1 + tier2_batch
    
    # Sort by priority
    leagues.sort(key=lambda k: get_league_priority(k), reverse=True)
    
    return leagues[:max_leagues]


def get_elite_leagues() -> List[str]:
    """Get Tier 1 leagues. Alias for backward compatibility."""
    return TIER_1_LEAGUES.copy()


def get_fallback_leagues() -> List[str]:
    """Fallback to Tier 1 if discovery fails."""
    return TIER_1_LEAGUES.copy()


# ============================================
# TIER 2 FALLBACK SYSTEM (V4.3)
# ============================================
def _check_daily_reset() -> None:
    """Reset contatori giornalieri a mezzanotte."""
    global _tier2_activations_today, _last_reset_date
    
    today = datetime.now().strftime("%Y-%m-%d")
    if _last_reset_date != today:
        logger.info(f"🔄 Tier 2 Fallback: Reset giornaliero ({_last_reset_date} → {today})")
        _tier2_activations_today = 0
        _last_reset_date = today


def increment_cycle() -> None:
    """Incrementa il contatore cicli (chiamato da main.py ad ogni ciclo)."""
    global _current_cycle
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
    
    Returns:
        Lista di 3 leghe Tier 2 in rotazione
    """
    global _tier2_fallback_index
    
    if not TIER_2_LEAGUES:
        logger.warning("⚠️ Tier 2 Fallback: Nessuna lega Tier 2 configurata")
        return []
    
    batch = []
    for i in range(TIER2_FALLBACK_BATCH_SIZE):
        idx = (_tier2_fallback_index + i) % len(TIER_2_LEAGUES)
        batch.append(TIER_2_LEAGUES[idx])
    
    # Avanza l'indice per la prossima chiamata
    _tier2_fallback_index = (_tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE) % len(TIER_2_LEAGUES)
    
    batch_num = (_tier2_fallback_index // TIER2_FALLBACK_BATCH_SIZE) % (len(TIER_2_LEAGUES) // TIER2_FALLBACK_BATCH_SIZE + 1)
    total_batches = (len(TIER_2_LEAGUES) + TIER2_FALLBACK_BATCH_SIZE - 1) // TIER2_FALLBACK_BATCH_SIZE
    
    logger.info(f"🔄 Tier 2 Fallback batch: {batch} (rotazione {batch_num}/{total_batches})")
    
    return batch


def record_tier2_activation() -> None:
    """Registra un'attivazione del fallback Tier 2."""
    global _tier2_activations_today, _last_tier2_activation_cycle, _current_cycle
    
    _tier2_activations_today += 1
    _last_tier2_activation_cycle = _current_cycle
    
    logger.info(f"📊 Tier 2 Fallback: Attivazione registrata ({_tier2_activations_today}/{TIER2_FALLBACK_DAILY_LIMIT} oggi)")


def reset_daily_tier2_stats() -> None:
    """Reset manuale delle statistiche giornaliere Tier 2."""
    global _tier2_activations_today, _consecutive_dry_cycles
    
    _tier2_activations_today = 0
    _consecutive_dry_cycles = 0
    logger.info("🔄 Tier 2 Fallback: Stats giornaliere resettate manualmente")


def get_tier2_fallback_status() -> Dict:
    """Ritorna lo stato corrente del sistema Tier 2 Fallback."""
    _check_daily_reset()
    
    cycles_since_activation = _current_cycle - _last_tier2_activation_cycle if _last_tier2_activation_cycle > 0 else -1
    cooldown_remaining = max(0, TIER2_FALLBACK_COOLDOWN - cycles_since_activation) if cycles_since_activation >= 0 else 0
    
    return {
        "current_cycle": _current_cycle,
        "consecutive_dry_cycles": _consecutive_dry_cycles,
        "activations_today": _tier2_activations_today,
        "daily_limit": TIER2_FALLBACK_DAILY_LIMIT,
        "cooldown_remaining": cooldown_remaining,
        "last_activation_cycle": _last_tier2_activation_cycle,
        "next_batch_preview": TIER_2_LEAGUES[_tier2_fallback_index:_tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE] if TIER_2_LEAGUES else [],
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
