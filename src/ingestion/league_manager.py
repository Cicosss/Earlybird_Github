"""
League Manager - V11.2 Flat Architecture (100% Data-Driven)

ARCHITECTURE:
- ZERO hardcoded league hierarchies. All league data comes from Supabase
  or its local cache (data/supabase_mirror.json).
- CRITICAL LAW: If Supabase is unreachable AND the Mirror is missing/empty,
  the bot logs a CRITICAL error and sleeps. It is NO LONGER allowed to
  "pretend" to work by falling back to hardcoded lists.
- Continental "Follow the Sun" logic is preserved via Supabase metadata.
- Priority, regions, and tier information are all derived dynamically.

PRESERVED:
- Tactical Veto V8.0 and Balanced Probability logic (untouched)
- Tier 2 Fallback System (now fed by Supabase priority=2 leagues)
- Round-robin rotation for secondary leagues
- Thread-safe operations throughout

MIGRATED (V11.2):
- TIER_1_LEAGUES → Supabase priority=1 leagues
- TIER_2_LEAGUES → Supabase priority=2 leagues
- ELITE_LEAGUES → Alias for get_tier1_leagues() (dynamic)
- ALL_LEAGUES → All active leagues from Supabase
- LEAGUE_PRIORITY → Derived from Supabase priority field
- Region mappings → Derived from country/continent metadata in Supabase
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from config.settings import ODDS_API_KEY, ODDS_API_KEYS

logger = logging.getLogger(__name__)

# ============================================
# V11.2: SUPABASE INTEGRATION (Single Source of Truth)
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
_session: requests.Session | None = None
_session_lock: threading.Lock = threading.Lock()

# ============================================
# V11.2 (B4): HARDWARE PERFORMANCE UNLOCK
# ============================================
# With 12GB RAM, we can scan all 56+ leagues concurrently per cycle.
# Old limit (12) was designed for a constrained environment.
MAX_LEAGUES_PER_RUN = 100

# ============================================
# MIRROR CONFIGURATION
# ============================================
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")

# ============================================
# CRITICAL ERROR THRESHOLD
# ============================================
# When both Supabase AND mirror are unavailable, sleep this many seconds
# before retrying to prevent log spam.
_DATA_UNAVAILABLE_SLEEP_SECONDS = 60

# ============================================
# ODDS API KEY ROTATION SYSTEM (BUG 5 FIX)
# ============================================
# Thread-safe key rotation for automatic failover
_current_odds_key_index: int = 0
_odds_key_lock: threading.Lock = threading.Lock()


def _get_current_odds_key() -> str:
    """
    Get the current Odds API key with automatic rotation.

    Returns:
        Current API key string
    """
    global _current_odds_key_index
    with _odds_key_lock:
        # Filter out empty keys
        valid_keys = [key for key in ODDS_API_KEYS if key and key != ""]

        if not valid_keys:
            # Fallback to single key if no rotation keys available
            return ODDS_API_KEY

        # Ensure index is within bounds
        if _current_odds_key_index >= len(valid_keys):
            _current_odds_key_index = 0  # Loop back to first key

        current_key = valid_keys[_current_odds_key_index]
        return current_key


def _rotate_odds_key() -> str:
    """
    Rotate to the next Odds API key.

    Returns:
        Next API key string
    """
    global _current_odds_key_index
    with _odds_key_lock:
        valid_keys = [key for key in ODDS_API_KEYS if key and key != ""]

        if not valid_keys:
            return ODDS_API_KEY

        # Move to next key
        _current_odds_key_index = (_current_odds_key_index + 1) % len(valid_keys)

        next_key = valid_keys[_current_odds_key_index]
        logger.info(f"🔄 Rotated to Odds API Key {_current_odds_key_index + 1}/{len(valid_keys)}")

        return next_key


def _reset_odds_key_rotation():
    """
    Reset the Odds API key rotation to the first key.
    """
    global _current_odds_key_index
    with _odds_key_lock:
        _current_odds_key_index = 0
        logger.info("🔄 Reset Odds API key rotation to Key 1")


def _get_session() -> requests.Session:
    """Get or create reusable requests session (thread-safe)."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                _session.headers.update({"User-Agent": "EarlyBird/7.0"})
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
# V11.2: UNIFIED DATA ACCESS LAYER
# ============================================
# All league data flows through this single layer.
# Supabase → Mirror → CRITICAL (no hardcoded fallbacks).


def _load_mirror_data() -> dict | None:
    """
    Load raw data from the local mirror file.

    Returns:
        Mirror data dict (inner 'data' key) or None if unavailable
    """
    try:
        if not MIRROR_FILE_PATH.exists():
            logger.warning(f"⚠️ [MIRROR] File not found: {MIRROR_FILE_PATH}")
            return None

        with open(MIRROR_FILE_PATH, encoding="utf-8") as f:
            mirror_raw = json.load(f)

        data = mirror_raw.get("data", {})
        if not data:
            logger.warning("⚠️ [MIRROR] Mirror file is empty or has no 'data' key")
            return None

        timestamp = mirror_raw.get("timestamp", "unknown")
        version = mirror_raw.get("version", "unknown")
        logger.info(f"✅ [MIRROR] Loaded mirror v{version} from {timestamp}")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"❌ [MIRROR] JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ [MIRROR] Error loading: {e}")
        return None


def _extract_leagues_from_mirror_data(data: dict, priority: int | None = None) -> list[str]:
    """
    Extract league api_keys from mirror data, optionally filtered by priority.

    Args:
        data: Raw mirror 'data' dict with 'leagues', 'countries', 'continents'
        priority: If set, filter to this priority value

    Returns:
        List of api_key strings
    """
    leagues = data.get("leagues", [])
    result: list[str] = []

    for league in leagues:
        if not league.get("is_active", False):
            continue
        if priority is not None and league.get("priority") != priority:
            continue
        api_key = league.get("api_key")
        if api_key:
            result.append(api_key)

    return result


def _extract_all_active_from_mirror(data: dict) -> list[str]:
    """
    Extract ALL active league api_keys from mirror data.

    Args:
        data: Raw mirror 'data' dict

    Returns:
        List of all active api_key strings
    """
    return _extract_leagues_from_mirror_data(data, priority=None)


def _fetch_leagues_from_supabase(priority: int | None = None) -> list[str] | None:
    """
    Fetch league api_keys from Supabase, optionally filtered by priority.

    Args:
        priority: If set, filter to this priority value

    Returns:
        List of api_key strings, or None if Supabase unavailable
    """
    if not _SUPABASE_AVAILABLE:
        return None

    try:
        sb = get_supabase()  # type: ignore[misc]
        if not sb:
            return None

        leagues = sb.get_active_leagues()

        if priority is not None:
            filtered = [
                str(league["api_key"])
                for league in leagues
                if league.get("priority") == priority and league.get("api_key")
            ]
        else:
            filtered = [str(league["api_key"]) for league in leagues if league.get("api_key")]

        return filtered if filtered else None

    except Exception as e:
        logger.warning(f"⚠️ [SUPABASE] Failed to fetch leagues: {e}")
        return None


def _get_leagues_with_fallback(priority: int | None = None, label: str = "") -> list[str]:
    """
    V11.2: Unified league sourcing with strict fallback chain.

    Chain: Supabase → Mirror → CRITICAL (sleep + return empty)

    Args:
        priority: Optional priority filter
        label: Label for logging (e.g., "Tier 1", "All Active")

    Returns:
        List of league api_keys (may be empty if all sources fail)
    """
    # Source 1: Supabase
    supabase_result = _fetch_leagues_from_supabase(priority)
    if supabase_result:
        logger.info(f"✅ [SUPABASE] Fetched {len(supabase_result)} {label} leagues from database")
        return supabase_result

    # Source 2: Local Mirror
    mirror_data = _load_mirror_data()
    if mirror_data:
        mirror_result = _extract_leagues_from_mirror_data(mirror_data, priority)
        if mirror_result:
            logger.info(f"📦 [MIRROR] Using {len(mirror_result)} {label} leagues from local mirror")
            return mirror_result

    # Source 3: CRITICAL - No data available
    logger.critical(
        f"🚨 [CRITICAL] No {label} leagues available! "
        f"Supabase unreachable AND mirror empty/missing. "
        f"Bot cannot operate without league data. Sleeping {_DATA_UNAVAILABLE_SLEEP_SECONDS}s."
    )
    time.sleep(_DATA_UNAVAILABLE_SLEEP_SECONDS)
    return []


# ============================================
# V11.2: DYNAMIC TIER / PRIORITY LOOKUPS
# ============================================
# These replace the old hardcoded constants.
# They query Supabase/Mirror once and cache the result.


# Cache for priority mapping (league_key -> priority_score)
_priority_cache: dict[str, int] | None = None
_priority_cache_lock = threading.Lock()

# Cache for region mapping (league_key -> continent_name)
_region_cache: dict[str, str] | None = None
_region_cache_lock = threading.Lock()

# TTL for metadata caches (10 minutes)
_METADATA_CACHE_TTL = 600
_priority_cache_time: float = 0
_region_cache_time: float = 0


def _build_priority_cache() -> dict[str, int]:
    """
    Build priority mapping from Supabase/Mirror data.

    Returns:
        Dict mapping league api_key to priority score
    """
    global _priority_cache, _priority_cache_time

    now = time.time()
    if _priority_cache is not None and (now - _priority_cache_time) < _METADATA_CACHE_TTL:
        return _priority_cache

    with _priority_cache_lock:
        now = time.time()
        if _priority_cache is not None and (now - _priority_cache_time) < _METADATA_CACHE_TTL:
            return _priority_cache

        priority_map: dict[str, int] = {}

        # Try Supabase first
        if _SUPABASE_AVAILABLE:
            try:
                sb = get_supabase()
                if sb:
                    leagues = sb.get_active_leagues()
                    for league in leagues:
                        api_key = league.get("api_key", "")
                        prio = league.get("priority", 10)
                        if api_key:
                            # Convert priority: higher Supabase priority = higher score
                            # Supabase priority 1 = score 100, priority 2 = score 50, etc.
                            score = max(10, 110 - (prio * 10)) if prio else 10
                            priority_map[api_key] = score
            except Exception as e:
                logger.debug(f"[PRIORITY] Supabase lookup failed: {e}")

        # If Supabase didn't return data, try mirror
        if not priority_map:
            mirror_data = _load_mirror_data()
            if mirror_data:
                for league in mirror_data.get("leagues", []):
                    api_key = league.get("api_key", "")
                    prio = league.get("priority", 10)
                    if api_key and league.get("is_active", False):
                        score = max(10, 110 - (prio * 10)) if prio else 10
                        priority_map[api_key] = score

        _priority_cache = priority_map
        _priority_cache_time = now
        logger.debug(f"[PRIORITY] Built cache with {len(priority_map)} league priorities")
        return priority_map


def _build_region_cache() -> dict[str, str]:
    """
    Build region mapping from Supabase/Mirror data.

    Maps league api_key to continent name for region derivation.

    Returns:
        Dict mapping league api_key to continent name
    """
    global _region_cache, _region_cache_time

    now = time.time()
    if _region_cache is not None and (now - _region_cache_time) < _METADATA_CACHE_TTL:
        return _region_cache

    with _region_cache_lock:
        now = time.time()
        if _region_cache is not None and (now - _region_cache_time) < _METADATA_CACHE_TTL:
            return _region_cache

        region_map: dict[str, str] = {}

        # Try Supabase first
        if _SUPABASE_AVAILABLE:
            try:
                sb = get_supabase()
                if sb:
                    leagues = sb.get_active_leagues()
                    for league in leagues:
                        api_key = league.get("api_key", "")
                        continent = league.get("continent", {}).get("name", "")
                        if api_key and continent:
                            region_map[api_key] = continent
            except Exception as e:
                logger.debug(f"[REGION] Supabase lookup failed: {e}")

        # If Supabase didn't return data, try mirror
        if not region_map:
            mirror_data = _load_mirror_data()
            if mirror_data:
                continents = mirror_data.get("continents", [])
                countries = mirror_data.get("countries", [])
                leagues = mirror_data.get("leagues", [])

                continent_map = {c["id"]: c.get("name", "") for c in continents if "id" in c}
                country_to_continent = {
                    c["id"]: c.get("continent_id") for c in countries if "id" in c
                }

                for league in leagues:
                    api_key = league.get("api_key", "")
                    country_id = league.get("country_id")
                    if not api_key or not country_id:
                        continue
                    continent_id = country_to_continent.get(country_id)
                    if continent_id:
                        continent_name = continent_map.get(continent_id, "")
                        if continent_name:
                            region_map[api_key] = continent_name

        _region_cache = region_map
        _region_cache_time = now
        logger.debug(f"[REGION] Built cache with {len(region_map)} league regions")
        return region_map


def clear_metadata_caches() -> None:
    """Clear priority and region metadata caches (for testing or after config changes)."""
    global _priority_cache, _priority_cache_time, _region_cache, _region_cache_time
    with _priority_cache_lock:
        _priority_cache = None
        _priority_cache_time = 0
    with _region_cache_lock:
        _region_cache = None
        _region_cache_time = 0


# ============================================
# V11.2: BACKWARD-COMPATIBLE DYNAMIC CONSTANTS
# ============================================
# These are now functions that return dynamic data, but we also
# provide module-level attributes for legacy code that imports them.
# They evaluate at import time to the best available data.


def _get_all_leagues_dynamic() -> list[str]:
    """Get ALL active leagues from Supabase/Mirror."""
    return _get_leagues_with_fallback(priority=None, label="All Active")


# ============================================
# PUBLIC API: TIER LEAGUE ACCESS
# ============================================


def get_tier1_leagues() -> list[str]:
    """
    V11.2: Get priority=1 leagues from Supabase/Mirror only.

    No hardcoded fallback. If both sources fail, logs CRITICAL and returns [].

    Returns:
        List of priority=1 league api_keys
    """
    return _get_leagues_with_fallback(priority=1, label="Tier 1")


def get_tier2_leagues() -> list[str]:
    """
    V11.2: Get priority=2 leagues from Supabase/Mirror only.

    No hardcoded fallback. If both sources fail, logs CRITICAL and returns [].

    Returns:
        List of priority=2 league api_keys
    """
    return _get_leagues_with_fallback(priority=2, label="Tier 2")


def get_all_active_leagues() -> list[str]:
    """
    V11.2: Get ALL active leagues from Supabase/Mirror only.

    Returns:
        List of all active league api_keys
    """
    return _get_leagues_with_fallback(priority=None, label="All Active")


# ============================================
# V11.2: DYNAMIC TIER CHECKS
# ============================================
# These now query the dynamic data instead of hardcoded sets.


def is_tier1_league(sport_key: str) -> bool:
    """
    Check if a league has priority=1 in Supabase/Mirror data.

    Args:
        sport_key: League API key

    Returns:
        True if league is priority=1
    """
    if not sport_key:
        return False
    tier1 = get_tier1_leagues()
    return sport_key in tier1


def is_tier2_league(sport_key: str) -> bool:
    """
    Check if a league has priority=2 in Supabase/Mirror data.

    Args:
        sport_key: League API key

    Returns:
        True if league is priority=2
    """
    if not sport_key:
        return False
    tier2 = get_tier2_leagues()
    return sport_key in tier2


def is_elite_league(sport_key: str) -> bool:
    """
    Check if league is priority=1. Alias for backward compatibility.

    Args:
        sport_key: League API key

    Returns:
        True if league is priority=1 (elite)
    """
    return is_tier1_league(sport_key)


def is_niche_league(sport_key: str) -> bool:
    """
    Check if league is in active scope (any priority).

    Args:
        sport_key: League API key

    Returns:
        True if league is actively monitored
    """
    return is_in_active_scope(sport_key)


# ============================================
# V11.2: CONTINENTAL BRAIN - "Follow the Sun" LOGIC
# ============================================


def get_active_leagues_for_continental_blocks() -> list[str]:
    """
    Get active leagues for current continental blocks based on UTC time.

    V11.2: Fully Supabase/Mirror driven. No hardcoded fallbacks.

    Returns:
        List of active league api_keys for current continental blocks
    """
    if not _SUPABASE_AVAILABLE:
        logger.warning("⚠️ [CONTINENTAL] Supabase not available, using mirror")
        return _get_continental_from_mirror()

    try:
        sb = get_supabase()
        if not sb:
            logger.warning("⚠️ [CONTINENTAL] Supabase provider not initialized, using mirror")
            return _get_continental_from_mirror()

        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour

        # Get active continental blocks for current hour
        active_blocks = sb.get_active_continent_blocks(current_utc_hour)

        if not active_blocks:
            logger.warning(
                f"⚠️ [CONTINENTAL] No active continental blocks at {current_utc_hour}:00 UTC"
            )
            return []

        logger.info(f"✅ [CONTINENTAL] Active blocks at {current_utc_hour}:00 UTC: {active_blocks}")

        # Get all active leagues from Supabase
        all_active_leagues = sb.get_active_leagues()

        if not all_active_leagues:
            logger.warning("⚠️ [CONTINENTAL] No active leagues found in Supabase")
            return _get_continental_from_mirror()

        # Filter leagues by active continental blocks
        active_leagues: list[str] = []
        for league in all_active_leagues:
            continent_name = league.get("continent", {}).get("name")
            if continent_name in active_blocks:
                api_key = league.get("api_key")
                if api_key:
                    active_leagues.append(api_key)

        if active_leagues:
            logger.info(
                f"✅ [CONTINENTAL] Identified {len(active_leagues)} active leagues for blocks: {active_blocks}"
            )
            return active_leagues
        else:
            logger.warning(f"⚠️ [CONTINENTAL] No leagues found for active blocks: {active_blocks}")
            return []

    except Exception as e:
        logger.error(f"❌ [CONTINENTAL] Error fetching continental leagues: {e}")
        return _get_continental_from_mirror()


def _get_continental_from_mirror() -> list[str]:
    """
    Fallback to mirror file when Supabase is unreachable.

    Returns:
        List of league api_keys from mirror for active continental blocks
    """
    mirror_data = _load_mirror_data()
    if not mirror_data:
        logger.critical(
            "🚨 [CRITICAL] Continental lookup failed: Supabase unreachable AND mirror unavailable!"
        )
        return []

    try:
        # Get current UTC hour
        current_utc_hour = datetime.now(timezone.utc).hour

        # Get active continents from mirror
        continents = mirror_data.get("continents", [])
        active_blocks: list[str] = []
        for continent in continents:
            active_hours = continent.get("active_hours_utc", [])
            if current_utc_hour in active_hours:
                active_blocks.append(continent.get("name"))

        if not active_blocks:
            logger.info(
                f"ℹ️ [CONTINENTAL] No active continental blocks at {current_utc_hour}:00 UTC (mirror)"
            )
            return []

        logger.info(
            f"✅ [CONTINENTAL] Active blocks from mirror at {current_utc_hour}:00 UTC: {active_blocks}"
        )

        # Get leagues and countries from mirror
        leagues = mirror_data.get("leagues", [])
        countries = mirror_data.get("countries", [])

        # Build country_id -> continent_id mapping
        country_to_continent = {
            c["id"]: c.get("continent_id") for c in countries if "id" in c and "continent_id" in c
        }

        # Build continent_id -> continent_name mapping
        continent_map = {c["id"]: c.get("name") for c in continents if "id" in c and "name" in c}

        # Filter leagues by active continental blocks
        active_leagues: list[str] = []
        for league in leagues:
            if not league.get("is_active", False):
                continue
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
            logger.info(
                f"✅ [CONTINENTAL] Identified {len(active_leagues)} active leagues from mirror"
            )
        return active_leagues

    except Exception as e:
        logger.error(f"❌ [CONTINENTAL] Error loading mirror: {e}")
        return []


# ============================================
# API FUNCTIONS
# ============================================
def fetch_all_sports() -> list[dict[str, Any]]:
    """
    Fetch all active sports from The-Odds-API (FREE endpoint).

    Returns:
        List of sports/leagues dictionaries
    """
    current_key = _get_current_odds_key()
    if not current_key or current_key == "YOUR_ODDS_API_KEY":
        logger.warning("⚠️ ODDS_API_KEY not configured")
        return []

    try:
        url = f"{BASE_URL}/sports"
        params = {"apiKey": current_key}
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


def get_quota_status() -> dict[str, Any]:
    """
    Get current API quota status.

    Returns:
        Dict with requests_used and requests_remaining
    """
    try:
        url = f"{BASE_URL}/sports"
        params = {"apiKey": _get_current_odds_key()}
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
# V12.4: ACTIVE SCOPE VALIDATOR (Root Cause Fix - Benfica Infection)
# ============================================
# Central mechanism to validate whether a league/team is in the active scope.
# Used by NewsRadar, OpportunityRadar, TelegramListener, RadarEnrichment
# to prevent non-active league data from leaking into the pipeline.

_active_scope_cache: list[str] | None = None
_active_scope_cache_time: float = 0
_active_scope_cache_lock = threading.Lock()
_ACTIVE_SCOPE_CACHE_TTL = 300  # 5 minutes


def get_all_active_league_keys() -> list[str]:
    """
    V11.2: Get ALL currently active league keys from Supabase/Mirror.

    No hardcoded fallbacks. Supabase → Mirror → CRITICAL.

    Returns deduplicated list. Results are cached for 5 minutes.

    Returns:
        List of active league API keys (e.g., 'soccer_turkey_super_league')
    """
    global _active_scope_cache, _active_scope_cache_time

    now = time.time()

    # Return cached if fresh
    if (
        _active_scope_cache is not None
        and (now - _active_scope_cache_time) < _ACTIVE_SCOPE_CACHE_TTL
    ):
        return _active_scope_cache

    with _active_scope_cache_lock:
        # Double-checked locking
        if (
            _active_scope_cache is not None
            and (now - _active_scope_cache_time) < _ACTIVE_SCOPE_CACHE_TTL
        ):
            return _active_scope_cache

        active_keys: set[str] = set()

        # Source 1: Supabase active leagues
        try:
            supabase = get_supabase()
            if supabase and supabase.is_connected():
                leagues = supabase.get_active_leagues(bypass_cache=False)
                for league in leagues:
                    api_key = league.get("api_key", "")
                    if api_key and api_key.startswith("soccer_"):
                        active_keys.add(api_key)
        except Exception as e:
            logger.debug(f"[SCOPE] Supabase lookup failed: {e}")

        # Source 2: Mirror (if Supabase didn't return data)
        if not active_keys:
            mirror_data = _load_mirror_data()
            if mirror_data:
                mirror_keys = _extract_all_active_from_mirror(mirror_data)
                active_keys.update(mirror_keys)

        # Source 3: CRITICAL - no data available
        if not active_keys:
            logger.critical(
                "🚨 [CRITICAL] get_all_active_league_keys: No active leagues found! "
                "Supabase unreachable AND mirror empty/missing. "
                "System cannot validate league scope."
            )

        result = list(active_keys)
        _active_scope_cache = result
        _active_scope_cache_time = now

        logger.debug(f"[SCOPE] Active league keys: {len(result)} leagues")
        return result


def is_in_active_scope(sport_key: str) -> bool:
    """
    V12.4/V11.2: Check if a league key is in the active scope.

    This is the CENTRAL validator that all components should use
    to determine if a league/team should be processed.

    Args:
        sport_key: League API key (e.g., 'soccer_portugal_primeira_liga')

    Returns:
        True if the league is actively monitored, False otherwise.
    """
    if not sport_key:
        return False

    # Normalize: strip whitespace
    sport_key = sport_key.strip()

    # Check against dynamic active leagues (Supabase + Mirror)
    active_keys = get_all_active_league_keys()
    return sport_key in active_keys


def is_team_in_active_scope(team_name: str) -> bool:
    """
    V12.4: Check if a team plays in an active league by querying the DB.

    Args:
        team_name: Team name to check

    Returns:
        True if the team has an upcoming match in an active league.
    """
    if not team_name:
        return False

    try:
        from src.database.models import Match, SessionLocal

        active_keys = set(get_all_active_league_keys())
        team_lower = team_name.lower().strip()

        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            max_time = now + timedelta(hours=96)

            matches = (
                db.query(Match).filter(Match.start_time >= now, Match.start_time <= max_time).all()
            )

            for match in matches:
                home = getattr(match, "home_team", "") or ""
                away = getattr(match, "away_team", "") or ""
                league = getattr(match, "league", "") or ""

                if team_lower in home.lower() or team_lower in away.lower():
                    if league in active_keys:
                        return True

            return False
        finally:
            db.close()

    except Exception as e:
        logger.debug(f"[SCOPE] Team scope check failed for {team_name}: {e}")
        return False


def clear_active_scope_cache() -> None:
    """V12.4: Clear the active scope cache (for testing or after config changes)."""
    global _active_scope_cache, _active_scope_cache_time
    with _active_scope_cache_lock:
        _active_scope_cache = None
        _active_scope_cache_time = 0


def get_league_priority(sport_key: str) -> int:
    """
    V11.2: Get priority score from Supabase/Mirror metadata.

    Higher score = more important. Derived from Supabase priority field:
    - priority 1 → score 100
    - priority 2 → score 50
    - unknown → score 10

    Args:
        sport_key: League API key

    Returns:
        Priority score (int)
    """
    priority_map = _build_priority_cache()
    return priority_map.get(sport_key, 10)


def get_league_tier(sport_key: str) -> str:
    """
    V11.2: Get tier label for a league based on dynamic data.

    Args:
        sport_key: League API key

    Returns:
        Tier label string
    """
    if is_tier1_league(sport_key):
        return "TIER1"
    elif is_tier2_league(sport_key):
        return "TIER2"
    return "OTHER"


# ============================================
# V11.2: DYNAMIC REGION DERIVATION
# ============================================
# Regions are now derived from Supabase continent metadata
# instead of hardcoded league-to-region mappings.


def _get_continent_for_league(sport_key: str) -> str:
    """
    Get continent name for a league from cached metadata.

    Args:
        sport_key: League API key

    Returns:
        Continent name string (e.g., 'LATAM', 'EUROPE') or empty string
    """
    region_map = _build_region_cache()
    return region_map.get(sport_key, "")


def is_latam_league(sport_key: str) -> bool:
    """Check if league belongs to LATAM continent."""
    return _get_continent_for_league(sport_key) == "LATAM"


def is_australia_league(sport_key: str) -> bool:
    """Check if league belongs to OCEANIA/Australia continent."""
    continent = _get_continent_for_league(sport_key)
    return continent in ("OCEANIA", "AUSTRALIA")


def is_asia_league(sport_key: str) -> bool:
    """Check if league belongs to ASIA continent."""
    return _get_continent_for_league(sport_key) == "ASIA"


def is_europe_league(sport_key: str) -> bool:
    """Check if league belongs to EUROPE continent."""
    return _get_continent_for_league(sport_key) == "EUROPE"


def get_regions_for_league(sport_key: str) -> str:
    """
    Get appropriate regions parameter for Odds API based on continent.

    Args:
        sport_key: League API key

    Returns:
        Regions string for Odds API
    """
    continent = _get_continent_for_league(sport_key)
    if continent in ("OCEANIA", "AUSTRALIA"):
        return "au,uk,eu"
    if continent == "ASIA":
        return "eu,uk,au"
    if continent == "LATAM":
        return "us,eu"
    if continent == "AFRICA":
        return "eu,uk"
    return "eu,uk"


# ============================================
# CYCLE MANAGEMENT
# ============================================

# Round-robin state for Tier 2
_tier2_index: int = 0
_tier2_index_lock: threading.Lock = threading.Lock()
TIER_2_PER_CYCLE: int = 3

# Tier 2 Fallback State
_consecutive_dry_cycles: int = 0
_tier2_activations_today: int = 0
_last_tier2_activation_cycle: int = 0
_current_cycle: int = 0
_last_reset_date: str = ""
_tier2_fallback_index: int = 0
_state_lock: threading.Lock = threading.Lock()

# Fallback configuration
TIER2_FALLBACK_BATCH_SIZE: int = 3
TIER2_FALLBACK_COOLDOWN: int = 3
TIER2_FALLBACK_DAILY_LIMIT: int = 3
TIER2_DRY_CYCLES_THRESHOLD: int = 2


def get_tier2_for_cycle() -> list[str]:
    """
    Get next batch of Tier 2 leagues (round-robin).

    V11.2: Uses Supabase/Mirror only. No hardcoded fallback.

    Thread-safe implementation.

    Returns:
        List of Tier 2 league keys for this cycle
    """
    global _tier2_index

    tier2_leagues = get_tier2_leagues()

    if not tier2_leagues:
        return []

    with _tier2_index_lock:
        start = _tier2_index % len(tier2_leagues)

        batch: list[str] = []
        for i in range(TIER_2_PER_CYCLE):
            idx = (start + i) % len(tier2_leagues)
            batch.append(tier2_leagues[idx])

        _tier2_index = (start + TIER_2_PER_CYCLE) % len(tier2_leagues)

    return batch


def get_leagues_for_cycle(emergency_mode: bool = False) -> list[str]:
    """
    Get leagues to fetch for this cycle.

    V11.2: Fully Supabase/Mirror driven. No hardcoded fallbacks.

    Normal: Active leagues for current continental blocks (based on UTC time)
    Emergency: Priority=1 leagues only

    Args:
        emergency_mode: If True, only return priority=1 leagues

    Returns:
        List of league keys to process
    """
    if emergency_mode:
        logger.info("🚨 Emergency mode: Priority 1 only")
        return get_tier1_leagues()

    # Use Continental Brain logic
    leagues = get_active_leagues_for_continental_blocks()

    if not leagues:
        logger.warning(
            "⚠️ No active leagues for current continental blocks. "
            "Attempting all active leagues as fallback."
        )
        leagues = get_all_active_leagues()

    # Limit to MAX_LEAGUES_PER_RUN for API quota management
    if len(leagues) > MAX_LEAGUES_PER_RUN:
        logger.info(f"⚠️ Limiting leagues from {len(leagues)} to {MAX_LEAGUES_PER_RUN} (API quota)")
        leagues = leagues[:MAX_LEAGUES_PER_RUN]

    logger.info(f"🎯 Cycle: {len(leagues)} active leagues")

    return leagues


def get_active_niche_leagues(max_leagues: int = MAX_LEAGUES_PER_RUN) -> list[str]:
    """
    Get active leagues from our verified list.
    Checks API for currently active leagues.

    V11.2: Uses Supabase/Mirror only. No hardcoded fallbacks.

    Args:
        max_leagues: Maximum number of leagues to return

    Returns:
        List of active league keys sorted by priority
    """
    logger.info("🔍 Checking for active leagues...")

    all_sports = fetch_all_sports()

    if not all_sports:
        logger.warning("⚠️ No sports data from API - using Supabase/Mirror data")
        return get_leagues_for_cycle()

    active_keys = {s["key"] for s in all_sports if s.get("active", False)}

    # Get all active leagues from Supabase/Mirror
    all_monitored = get_all_active_leagues()

    # Filter to those currently active on the API
    active_monitored = [l for l in all_monitored if l in active_keys]

    if not active_monitored:
        logger.warning("⚠️ No monitored leagues currently active on API")
        return get_leagues_for_cycle()

    logger.info(f"✅ Active monitored leagues: {len(active_monitored)}")

    # Sort by priority
    active_monitored.sort(key=lambda k: get_league_priority(k), reverse=True)

    return active_monitored[:max_leagues]


def get_elite_leagues() -> list[str]:
    """
    Get priority=1 leagues. Alias for backward compatibility.

    V11.2: Uses Supabase/Mirror only.

    Returns:
        List of priority=1 league keys
    """
    return get_tier1_leagues()


def get_fallback_leagues() -> list[str]:
    """
    Fallback leagues if discovery fails.

    V11.2: Returns all active leagues from Supabase/Mirror.

    Returns:
        List of active league keys
    """
    return get_all_active_leagues()


# ============================================
# TIER 2 FALLBACK SYSTEM (V4.3 - preserved, now data-driven)
# ============================================
def _check_daily_reset() -> None:
    """
    Reset daily counters at midnight UTC.

    Thread-safe implementation.
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
    Increment cycle counter (called by main.py each cycle).

    Thread-safe implementation.
    """
    global _current_cycle

    with _state_lock:
        _current_cycle += 1

    _check_daily_reset()


def should_activate_tier2_fallback(alerts_sent: int, high_potential_count: int) -> bool:
    """
    Trigger D: Activate Tier 2 Fallback IF:
    - alerts_sent == 0
    - AND (high_potential_count == 0 OR consecutive_dry_cycles >= 2)
    - AND cooldown respected (3 cycles)
    - AND daily limit not exceeded (3/day)

    Args:
        alerts_sent: Number of alerts sent in the cycle
        high_potential_count: Number of high_potential matches found

    Returns:
        True if fallback should be activated
    """
    global _consecutive_dry_cycles, _tier2_activations_today
    global _last_tier2_activation_cycle, _current_cycle

    _check_daily_reset()

    with _state_lock:
        if alerts_sent > 0:
            if _consecutive_dry_cycles > 0:
                logger.info(
                    f"✅ Tier 1 produttivo - Reset dry cycles ({_consecutive_dry_cycles} → 0)"
                )
            _consecutive_dry_cycles = 0
            return False

        _consecutive_dry_cycles += 1
        logger.info(f"📉 Tier 1 silenzioso - Dry cycles: {_consecutive_dry_cycles}")

        if _tier2_activations_today >= TIER2_FALLBACK_DAILY_LIMIT:
            logger.info(
                f"⚠️ Tier 2 Fallback: Limite giornaliero raggiunto ({_tier2_activations_today}/{TIER2_FALLBACK_DAILY_LIMIT})"
            )
            return False

        if _last_tier2_activation_cycle > 0:
            cycles_since_last = _current_cycle - _last_tier2_activation_cycle
            if cycles_since_last < TIER2_FALLBACK_COOLDOWN:
                logger.info(
                    f"⏳ Tier 2 Fallback: Cooldown attivo ({cycles_since_last}/{TIER2_FALLBACK_COOLDOWN} cicli)"
                )
                return False

        if high_potential_count == 0 or _consecutive_dry_cycles >= TIER2_DRY_CYCLES_THRESHOLD:
            reason = (
                "no high_potential"
                if high_potential_count == 0
                else f"dry_cycles >= {TIER2_DRY_CYCLES_THRESHOLD}"
            )
            logger.info(f"🔄 Tier 2 Fallback: Trigger D attivato ({reason})")
            return True

        return False


def get_tier2_fallback_batch() -> list[str]:
    """
    Get next batch of 3 Tier 2 leagues for fallback (round-robin).

    V11.2: Uses Supabase/Mirror only.

    Thread-safe implementation.

    Returns:
        List of 3 Tier 2 leagues in rotation
    """
    global _tier2_fallback_index

    tier2_leagues = get_tier2_leagues()

    if not tier2_leagues:
        logger.warning("⚠️ Tier 2 Fallback: No Tier 2 leagues configured in Supabase/Mirror")
        return []

    with _state_lock:
        batch: list[str] = []
        for i in range(TIER2_FALLBACK_BATCH_SIZE):
            idx = (_tier2_fallback_index + i) % len(tier2_leagues)
            batch.append(tier2_leagues[idx])

        _tier2_fallback_index = (_tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE) % len(
            tier2_leagues
        )

        batch_num = (_tier2_fallback_index // TIER2_FALLBACK_BATCH_SIZE) % (
            len(tier2_leagues) // TIER2_FALLBACK_BATCH_SIZE + 1
        )
        total_batches = (
            len(tier2_leagues) + TIER2_FALLBACK_BATCH_SIZE - 1
        ) // TIER2_FALLBACK_BATCH_SIZE

        logger.info(f"🔄 Tier 2 Fallback batch: {batch} (rotazione {batch_num}/{total_batches})")

    return batch


def record_tier2_activation() -> None:
    """
    Record a Tier 2 fallback activation.

    Thread-safe implementation.
    """
    global _tier2_activations_today, _last_tier2_activation_cycle, _current_cycle

    with _state_lock:
        _tier2_activations_today += 1
        _last_tier2_activation_cycle = _current_cycle

    logger.info(
        f"📊 Tier 2 Fallback: Attivazione registrata ({_tier2_activations_today}/{TIER2_FALLBACK_DAILY_LIMIT} oggi)"
    )


def reset_daily_tier2_stats() -> None:
    """
    Manual reset of daily Tier 2 statistics.

    Thread-safe implementation.
    """
    global _tier2_activations_today, _consecutive_dry_cycles

    with _state_lock:
        _tier2_activations_today = 0
        _consecutive_dry_cycles = 0

    logger.info("🔄 Tier 2 Fallback: Stats giornaliere resettate manualmente")


def get_tier2_fallback_status() -> dict[str, Any]:
    """
    Return current Tier 2 Fallback system status.

    Thread-safe implementation.

    Returns:
        Dict with current fallback status
    """
    _check_daily_reset()

    tier2_leagues = get_tier2_leagues()

    with _state_lock:
        cycles_since_activation = (
            _current_cycle - _last_tier2_activation_cycle
            if _last_tier2_activation_cycle > 0
            else -1
        )
        cooldown_remaining = (
            max(0, TIER2_FALLBACK_COOLDOWN - cycles_since_activation)
            if cycles_since_activation >= 0
            else 0
        )

        return {
            "current_cycle": _current_cycle,
            "consecutive_dry_cycles": _consecutive_dry_cycles,
            "activations_today": _tier2_activations_today,
            "daily_limit": TIER2_FALLBACK_DAILY_LIMIT,
            "cooldown_remaining": cooldown_remaining,
            "last_activation_cycle": _last_tier2_activation_cycle,
            "next_batch_preview": tier2_leagues[
                _tier2_fallback_index : _tier2_fallback_index + TIER2_FALLBACK_BATCH_SIZE
            ]
            if tier2_leagues
            else [],
        }


# ============================================
# CLI
# ============================================
if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("🎯 V11.2 FLAT ARCHITECTURE - 100% DATA-DRIVEN")
    print("=" * 60)

    print("\n📋 Tier 1 (Priority 1 - from Supabase/Mirror):")
    tier1 = get_tier1_leagues()
    for i, league in enumerate(tier1, 1):
        print(f"  {i}. {league}")

    print(f"\n📋 Tier 2 (Priority 2 - from Supabase/Mirror):")
    tier2 = get_tier2_leagues()
    for i, league in enumerate(tier2, 1):
        print(f"  {i}. {league}")

    print(f"\n📋 All Active Leagues:")
    all_active = get_all_active_leagues()
    for i, league in enumerate(all_active, 1):
        print(f"  {i}. {league}")

    print("\n🔄 Simulating 3 Tier 2 cycles:")
    for cycle in range(3):
        batch = get_tier2_for_cycle()
        print(f"  Cycle {cycle + 1}: {batch}")

    print("\n💰 API Quota:")
    quota = get_quota_status()
    print(f"  Used: {quota['requests_used']}")
    print(f"  Remaining: {quota['requests_remaining']}")

    # Cleanup session on exit
    _close_session()
