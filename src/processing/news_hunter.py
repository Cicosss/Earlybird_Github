"""
EarlyBird News Hunter Module V8.0

Multi-tier news aggregation system for betting intelligence:
- TIER 0: Browser Monitor (active web monitoring)
- TIER 0: A-League Scraper (direct scraping for Australian league)
- TIER 0.5: Beat Writer Priority (Twitter Intel Cache)
- TIER 1: Hyper-local news search (site-dorked)
- TIER 2: Insider intel (placeholder for future expansion)

VPS Compatibility:
- Uses environment variables for API keys
- Implements rate limiting for all external APIs
- Graceful fallbacks when services are unavailable
- Thread-safe discovery queue integration
"""

import logging
import time
import os
import requests
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from threading import Lock
import uuid

from config.settings import SERPER_API_KEY, NATIVE_KEYWORDS
from src.database.models import TeamAlias, SessionLocal, Match as MatchModel
from src.processing.sources_config import (
    get_sources_for_league,
    get_keywords_for_league,
    get_country_from_league,
    get_insider_handles,
    get_beat_writers,
    BeatWriter
)
from src.utils.validators import safe_dict_get

# V10.0: Import Multi-Level Intelligence Gate
try:
    from src.utils.intelligence_gate import (
        level_1_keyword_check,
        level_2_translate_and_classify,
        apply_intelligence_gate,
    )
    _INTELLIGENCE_GATE_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_GATE_AVAILABLE = False
    logging.debug("Intelligence gate module not available for news_hunter")

# V8.0: Reddit monitoring removed - provided no betting edge

# ============================================
# NEWS DECAY (Market Intelligence Integration)
# ============================================
try:
    from src.analysis.market_intelligence import calculate_news_freshness_multiplier
    _NEWS_DECAY_AVAILABLE = True
except ImportError:
    _NEWS_DECAY_AVAILABLE = False

# ============================================
# DEEP DIVE ON DEMAND (V8.1)
# ============================================
try:
    from src.utils.article_reader import apply_deep_dive_to_results
    _ARTICLE_READER_AVAILABLE = True
except ImportError:
    _ARTICLE_READER_AVAILABLE = False
    logging.debug("Article reader not available for deep dive feature")

# ============================================
# SEARCH PROVIDER SELECTION
# ============================================
# Priority: DuckDuckGo (free, native) > Serper (paid API)

# Try to import search provider
try:
    from src.ingestion.search_provider import get_search_provider, LEAGUE_DOMAINS
    _SEARCH_PROVIDER_AVAILABLE = True
except ImportError:
    _SEARCH_PROVIDER_AVAILABLE = False
    LEAGUE_DOMAINS: Dict[str, List[str]] = {}

# Try to import A-League scraper (TIER 0 - direct scraping)
try:
    from src.ingestion.aleague_scraper import get_aleague_scraper
    _ALEAGUE_SCRAPER_AVAILABLE = True
except ImportError:
    _ALEAGUE_SCRAPER_AVAILABLE = False

# Try to import Browser Monitor (TIER 0 - active web monitoring)
try:
    from src.services.browser_monitor import DiscoveredNews
    _BROWSER_MONITOR_AVAILABLE = True
except ImportError:
    _BROWSER_MONITOR_AVAILABLE = False
    DiscoveredNews = Any  # Type placeholder

# ============================================
# TWITTER INTEL CACHE V7.0 (Replaces broken site:twitter.com search)
# ============================================
try:
    from src.services.twitter_intel_cache import get_twitter_intel_cache, CachedTweet
    _TWITTER_INTEL_CACHE_AVAILABLE = True
except ImportError:
    _TWITTER_INTEL_CACHE_AVAILABLE = False
    CachedTweet = Any  # Type placeholder
    logging.debug("Twitter Intel Cache not available for news_hunter")

# ============================================
# SUPABASE SOCIAL SOURCES INTEGRATION (V9.0)
# ============================================
# Fetches social sources (Twitter/X handles) from Supabase with fallback to local config

_SUPABASE_AVAILABLE = False
_SUPABASE_PROVIDER = None

try:
    from src.database.supabase_provider import get_supabase
    _SUPABASE_AVAILABLE = True
    _SUPABASE_PROVIDER = get_supabase()
    logging.info("✅ Supabase provider available for social sources")
except ImportError:
    logging.warning("⚠️ Supabase provider not available, using local config fallback")
    _SUPABASE_AVAILABLE = False


def get_social_sources_from_supabase(league_key: str) -> List[str]:
    """
    Fetch Twitter/X handles from Supabase social_sources table.
    
    Falls back to local sources_config.py if Supabase is unavailable
    or the social_sources table doesn't exist yet.
    
    Args:
        league_key: API league key (e.g., 'soccer_turkey_super_league')
        
    Returns:
        List of Twitter handles (with @)
    """
    # Try Supabase first
    if _SUPABASE_AVAILABLE and _SUPABASE_PROVIDER:
        try:
            # Map league_key to country for Supabase query
            country = get_country_from_league(league_key)
            
            if country:
                # Try to get social sources for this league/country
                # Note: Using get_social_sources() as fallback since social_sources_for_league
                # might not exist yet in the database
                all_social_sources = _SUPABASE_PROVIDER.get_social_sources()
                
                # Filter social sources by league/country if possible
                # For now, return all social sources and let caller filter
                if all_social_sources:
                    handles = []
                    for source in all_social_sources:
                        handle = source.get('handle', '')
                        if handle and isinstance(handle, str):
                            # Ensure handle starts with @
                            if not handle.startswith('@'):
                                handle = f"@{handle.lstrip('@')}"
                            handles.append(handle)
                    
                    logging.info(f"📡 [SUPABASE] Fetched {len(handles)} social sources from Supabase for {league_key}")
                    return handles
                
        except Exception as e:
            logging.warning(f"⚠️ [SUPABASE] Failed to fetch social sources: {e}")
    
    # Fallback to local sources_config.py
    logging.info(f"🔄 [FALLBACK] Using local sources_config.py for {league_key}")
    handles = get_insider_handles(league_key)
    beat_writers = get_beat_writers(league_key)
    
    # Combine insider handles and beat writers, deduplicate
    all_handles = list(set(handles + [w.handle for w in beat_writers]))
    
    logging.info(f"📋 [LOCAL] Using {len(all_handles)} handles from local config for {league_key}")
    return all_handles


def get_beat_writers_from_supabase(league_key: str) -> List[BeatWriter]:
    """
    Fetch beat writers from Supabase social_sources table.
    
    Falls back to local sources_config.py if Supabase is unavailable.
    
    Args:
        league_key: API league key
        
    Returns:
        List of BeatWriter objects
    """
    # Try Supabase first
    if _SUPABASE_AVAILABLE and _SUPABASE_PROVIDER:
        try:
            country = get_country_from_league(league_key)
            
            if country:
                all_social_sources = _SUPABASE_PROVIDER.get_social_sources()
                
                # Filter for beat writer type accounts
                beat_writers = []
                for source in all_social_sources:
                    handle = source.get('handle', '')
                    source_type = source.get('source_type', '').lower()
                    
                    # Check if this is a beat writer/journalist type
                    if source_type in ['beat_writer', 'journalist', 'insider']:
                        if handle and isinstance(handle, str):
                            # Ensure handle starts with @
                            if not handle.startswith('@'):
                                handle = f"@{handle.lstrip('@')}"
                            
                            # Create BeatWriter object from Supabase data
                            beat_writers.append(BeatWriter(
                                handle=handle,
                                name=source.get('name', handle),
                                outlet=source.get('outlet', 'Unknown'),
                                specialty=source.get('specialty', 'general'),
                                reliability=source.get('reliability', 0.75),
                                avg_lead_time_min=source.get('lead_time_min', 10)
                            ))
                
                if beat_writers:
                    logging.info(f"📡 [SUPABASE] Fetched {len(beat_writers)} beat writers from Supabase for {league_key}")
                    return beat_writers
                
        except Exception as e:
            logging.warning(f"⚠️ [SUPABASE] Failed to fetch beat writers: {e}")
    
    # Fallback to local sources_config.py
    logging.info(f"🔄 [FALLBACK] Using local beat writers for {league_key}")
    return get_beat_writers(league_key)

# ============================================
# BROWSER MONITOR INTEGRATION (TIER 0)
# V7.0: Now uses DiscoveryQueue for thread-safe communication
# ============================================

# V7.0: Try to use new DiscoveryQueue, fallback to legacy dict
try:
    from src.utils.discovery_queue import get_discovery_queue, DiscoveryQueue
    _DISCOVERY_QUEUE_AVAILABLE = True
except ImportError:
    _DISCOVERY_QUEUE_AVAILABLE = False
    DiscoveryQueue = Any  # Type placeholder

# Legacy storage (kept for backward compatibility during transition)
_browser_monitor_discoveries: Dict[str, List[Dict]] = {}
_browser_monitor_lock = Lock()

# Discovery expiration (24 hours)
_BROWSER_MONITOR_TTL_HOURS = 24

# ============================================
# SERPER API CONFIGURATION (V7.1 - Centralized)
# ============================================
# Timeout and rate limiting constants for all Serper API calls.
# Centralizing these allows easy tuning for network conditions.

SERPER_REQUEST_TIMEOUT = 30      # Seconds - timeout for HTTP requests
SERPER_RATE_LIMIT_DELAY = 0.3    # Seconds - delay between API calls (rate limiting)
SERPER_RATE_LIMIT_DELAY_SLOW = 0.5  # Seconds - slower delay for generic search (less aggressive)

# ============================================
# FRESHNESS TAG (V7.0 - Centralized Module)
# ============================================
# Now uses src/utils/freshness.py as single source of truth
# This eliminates duplication with market_intelligence.py and news_radar.py

try:
    from src.utils.freshness import (
        get_freshness_tag,
        calculate_minutes_old,
        FRESHNESS_FRESH_THRESHOLD_MIN,
        FRESHNESS_AGING_THRESHOLD_MIN
    )
    _FRESHNESS_MODULE_AVAILABLE = True
except ImportError:
    _FRESHNESS_MODULE_AVAILABLE = False
    # Fallback constants if module not available
    FRESHNESS_FRESH_THRESHOLD_MIN = 60
    FRESHNESS_AGING_THRESHOLD_MIN = 360
    
    def get_freshness_tag(minutes_old: int) -> str:
        """Fallback freshness tag calculation."""
        if minutes_old < 0:
            return "🔥 FRESH"
        if minutes_old < FRESHNESS_FRESH_THRESHOLD_MIN:
            return "🔥 FRESH"
        elif minutes_old < FRESHNESS_AGING_THRESHOLD_MIN:
            return "⏰ AGING"
        else:
            return "📜 STALE"


def register_browser_monitor_discovery(news: Any) -> None:
    """
    Callback called by BrowserMonitor when relevant news is found.
    Stores the discovery for later retrieval by run_hunter_for_match.
    
    V7.0: Now uses DiscoveryQueue for thread-safe communication.
    V6.2: Uses centralized get_freshness_tag() for DRY compliance.
    
    Args:
        news: DiscoveredNews object from browser monitor
        
    Requirements: 4.1, 4.2
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return
    
    # Safely extract attributes with defaults
    try:
        title = getattr(news, 'title', None) or "No title"
        snippet = getattr(news, 'snippet', None) or ""
        url = getattr(news, 'url', None) or ""
        source_name = getattr(news, 'source_name', None) or "Unknown"
        affected_team = getattr(news, 'affected_team', None) or "Unknown"
        league_key = getattr(news, 'league_key', None) or "unknown"
        category = getattr(news, 'category', None) or "general"
        confidence = getattr(news, 'confidence', None) or 0.5
        discovered_at = getattr(news, 'discovered_at', None)
    except Exception as e:
        logging.warning(f"Failed to extract news attributes: {e}")
        return
    
    # Calculate freshness for News Decay integration
    now = datetime.now(timezone.utc)
    if discovered_at is None:
        discovered_at = now
    
    try:
        minutes_old = int((now - discovered_at).total_seconds() / 60)
    except (TypeError, AttributeError):
        minutes_old = 0
    
    # Use centralized freshness tag function
    freshness_tag = get_freshness_tag(minutes_old)
    
    # Build discovery data dict
    discovery_data: Dict[str, Any] = {
        # Core fields (required by dossier builder)
        'match_id': None,  # Will be matched later
        'team': affected_team,
        'title': title,
        'snippet': snippet,
        'link': url,
        'source': source_name,
        'date': discovered_at.isoformat() if hasattr(discovered_at, 'isoformat') else str(discovered_at),
        
        # News Decay fields
        'freshness_tag': freshness_tag,
        'minutes_old': minutes_old,
        
        # Browser Monitor specific fields
        'keyword': 'browser_monitor',
        'search_type': 'browser_monitor',
        'confidence': 'HIGH',
        'category': category,
        'priority_boost': 2.0,
        'source_type': 'browser_monitor',
        'league_key': league_key,
        'gemini_confidence': confidence,
        'discovered_at': discovered_at.isoformat() if hasattr(discovered_at, 'isoformat') else str(discovered_at),
    }
    
    # V7.0: Use DiscoveryQueue if available
    if _DISCOVERY_QUEUE_AVAILABLE:
        try:
            queue = get_discovery_queue()
            queue.push(
                data=discovery_data,
                league_key=league_key,
                team=affected_team,
                title=title,
                snippet=snippet,
                url=url,
                source_name=source_name,
                category=category,
                confidence=confidence
            )
        except Exception as e:
            logging.warning(f"DiscoveryQueue push failed, using legacy: {e}")
            _legacy_store_discovery(discovery_data, league_key)
    else:
        _legacy_store_discovery(discovery_data, league_key)
    
    # Safe logging
    title_preview = title[:50] if len(title) > 50 else title
    logging.info(f"🌐 [BROWSER-MONITOR] Registered discovery: {title_preview} for {affected_team}")


def _legacy_store_discovery(discovery_data: Dict[str, Any], league_key: str) -> None:
    """Store discovery in legacy storage (fallback)."""
    discovery_uuid = str(uuid.uuid4())
    discovery_data['_uuid'] = discovery_uuid
    
    with _browser_monitor_lock:
        if league_key not in _browser_monitor_discoveries:
            _browser_monitor_discoveries[league_key] = []
        _browser_monitor_discoveries[league_key].append(discovery_data)


def get_browser_monitor_news(match_id: str, team_names: List[str], league_key: str) -> List[Dict]:
    """
    Get browser monitor discoveries relevant to a match.
    Called by run_hunter_for_match as TIER 0 source.
    
    V7.0: Now uses DiscoveryQueue for thread-safe retrieval.
    
    Args:
        match_id: Match ID to tag results with
        team_names: List of team names to match against
        league_key: League key to filter discoveries
        
    Returns:
        List of news items matching the teams
        
    Requirements: 4.2, 4.3, 4.4
    """
    if not _BROWSER_MONITOR_AVAILABLE:
        return []
    
    if not team_names:
        return []
    
    # V7.0: Use DiscoveryQueue if available
    if _DISCOVERY_QUEUE_AVAILABLE:
        queue = get_discovery_queue()
        return queue.pop_for_match(match_id, team_names, league_key)
    
    # Legacy fallback (same as before)
    now = datetime.now(timezone.utc)
    
    with _browser_monitor_lock:
        if league_key not in _browser_monitor_discoveries:
            return []
        discoveries_snapshot = _browser_monitor_discoveries[league_key][:]
    
    snapshot_uuids = {d.get('_uuid') for d in discoveries_snapshot if d.get('_uuid')}
    
    results = []
    valid_discoveries = []
    valid_uuids = set()
    
    for discovery in discoveries_snapshot:
        discovered_at_str = discovery.get('discovered_at')
        discovered_at = None
        is_expired = False
        
        if discovered_at_str:
            try:
                discovered_at = datetime.fromisoformat(discovered_at_str.replace('Z', '+00:00'))
                if now - discovered_at > timedelta(hours=_BROWSER_MONITOR_TTL_HOURS):
                    is_expired = True
            except (ValueError, TypeError):
                pass
        
        if is_expired:
            continue
        
        valid_discoveries.append(discovery)
        if discovery.get('_uuid'):
            valid_uuids.add(discovery['_uuid'])
        
        affected_team = (discovery.get('team') or '').lower().strip()
        if not affected_team:
            continue
            
        for team_name in team_names:
            team_name_lower = (team_name or '').lower().strip()
            if not team_name_lower:
                continue
                
            if team_name_lower in affected_team or affected_team in team_name_lower:
                result = discovery.copy()
                result['match_id'] = match_id
                
                if discovered_at:
                    minutes_old = int((now - discovered_at).total_seconds() / 60)
                    result['minutes_old'] = minutes_old
                    result['freshness_tag'] = get_freshness_tag(minutes_old)
                
                results.append(result)
                break
    
    # Cleanup expired
    expired_count = len(discoveries_snapshot) - len(valid_discoveries)
    if expired_count > 0:
        with _browser_monitor_lock:
            current = _browser_monitor_discoveries.get(league_key, [])
            new_entries = []
            for d in current:
                d_uuid = d.get('_uuid')
                if d_uuid is None:
                    new_entries.append(d)
                elif d_uuid not in snapshot_uuids:
                    new_entries.append(d)
                elif d_uuid in valid_uuids:
                    new_entries.append(d)
            _browser_monitor_discoveries[league_key] = new_entries
    
    return results


def clear_browser_monitor_discoveries(league_key: Optional[str] = None) -> int:
    """
    Clear browser monitor discoveries.
    
    V7.0: Now also clears DiscoveryQueue for proper test isolation.
    
    Args:
        league_key: If provided, clear only for this league. Otherwise clear all.
        
    Returns:
        Number of discoveries cleared
    """
    count = 0
    
    # V7.0: Clear DiscoveryQueue first
    if _DISCOVERY_QUEUE_AVAILABLE:
        queue = get_discovery_queue()
        count += queue.clear(league_key)
    
    # Legacy storage cleanup
    with _browser_monitor_lock:
        if league_key:
            legacy_count = len(_browser_monitor_discoveries.get(league_key, []))
            _browser_monitor_discoveries[league_key] = []
            count += legacy_count
        else:
            legacy_count = sum(len(v) for v in _browser_monitor_discoveries.values())
            _browser_monitor_discoveries.clear()
            count += legacy_count
    
    return count


def cleanup_expired_browser_monitor_discoveries() -> int:
    """
    Proactively clean up expired browser monitor discoveries.
    
    Should be called periodically (e.g., every hour or at start of each pipeline cycle)
    to prevent memory leaks from accumulated stale discoveries.
    
    Returns:
        Number of expired discoveries removed
    """
    now = datetime.now(timezone.utc)
    removed_count = 0
    
    with _browser_monitor_lock:
        for league_key in list(_browser_monitor_discoveries.keys()):
            original_count = len(_browser_monitor_discoveries[league_key])
            
            valid_discoveries = []
            for discovery in _browser_monitor_discoveries[league_key]:
                discovered_at_str = discovery.get('discovered_at')
                if not discovered_at_str:
                    # No timestamp - keep it (conservative)
                    valid_discoveries.append(discovery)
                    continue
                
                try:
                    discovered_at = datetime.fromisoformat(discovered_at_str.replace('Z', '+00:00'))
                    if now - discovered_at <= timedelta(hours=_BROWSER_MONITOR_TTL_HOURS):
                        valid_discoveries.append(discovery)
                    # else: expired, don't add to valid_discoveries
                except (ValueError, TypeError):
                    # Invalid timestamp - keep it (conservative)
                    valid_discoveries.append(discovery)
            
            _browser_monitor_discoveries[league_key] = valid_discoveries
            removed_count += original_count - len(valid_discoveries)
        
        # Remove empty league keys to save memory
        empty_keys = [k for k, v in _browser_monitor_discoveries.items() if not v]
        for k in empty_keys:
            del _browser_monitor_discoveries[k]
    
    if removed_count > 0:
        logging.info(f"🧹 [BROWSER-MONITOR] Cleaned up {removed_count} expired discoveries")
    
    return removed_count


def get_browser_monitor_stats() -> Dict:
    """
    Get statistics about browser monitor discoveries for monitoring.
    
    Returns:
        Dict with total_discoveries, by_league counts, oldest_discovery_age_hours
    """
    now = datetime.now(timezone.utc)
    
    with _browser_monitor_lock:
        total = sum(len(v) for v in _browser_monitor_discoveries.values())
        by_league = {k: len(v) for k, v in _browser_monitor_discoveries.items()}
        
        oldest_age_hours = 0
        for discoveries in _browser_monitor_discoveries.values():
            for d in discoveries:
                discovered_at_str = d.get('discovered_at')
                if discovered_at_str:
                    try:
                        discovered_at = datetime.fromisoformat(discovered_at_str.replace('Z', '+00:00'))
                        age_hours = (now - discovered_at).total_seconds() / 3600
                        oldest_age_hours = max(oldest_age_hours, age_hours)
                    except (ValueError, TypeError):
                        pass
        
        return {
            'total_discoveries': total,
            'by_league': by_league,
            'oldest_discovery_age_hours': round(oldest_age_hours, 1),
            'ttl_hours': _BROWSER_MONITOR_TTL_HOURS
        }


SERPER_URL = "https://google.serper.dev/search"
SERPER_NEWS_URL = "https://google.serper.dev/news"

# Global flag to disable Serper when credits are exhausted
_SERPER_CREDITS_EXHAUSTED = False

# ============================================
# DEEP DIVE ON DEMAND (V8.1)
# ============================================
# Configuration for upgrading shallow search results to full article content

# Enable/disable deep dive feature
DEEP_DIVE_ENABLED = True

# Maximum articles to deep dive per search (to limit performance impact)
DEEP_DIVE_MAX_ARTICLES = 3

# Timeout for article fetch (seconds)
DEEP_DIVE_TIMEOUT = 15

# Snippet length threshold - skip deep dive if snippet is already long enough
DEEP_DIVE_SNIPPET_THRESHOLD = 500

# Keywords that indicate article contains valuable details
# Multi-language support for injury, squad, tactical, and transfer news
DEEP_DIVE_TRIGGERS = [
    # Injury-related
    "injury", "injured", "out", "ruled out", "doubtful",
    "hamstring", "knee", "ankle", "muscle", "strain",
    
    # Squad-related
    "squad", "lineup", "starting", "bench", "xi",
    "missing", "absent", "unavailable", "sidelined",
    
    # Tactical/Transfer
    "turnover", "suspension", "suspended", "transfer", "signing",
    "loan", "deal", "agreement",
    
    # Multi-language
    "infortunio", "lesión", "lesão", "kontuzja", "sakatlık",
    "convocati", "formazione", "escalação", "kadro",
]

def _check_serper_response(response, query: str = None) -> bool:
    """
    Check Serper response and set exhausted flag if needed.
    
    V6.3: Enhanced logging for HTTP 400 errors to diagnose query issues.
    
    Args:
        response: requests.Response object
        query: Optional query string for diagnostic logging
        
    Returns:
        True if response is OK (200), False otherwise
    """
    global _SERPER_CREDITS_EXHAUSTED
    
    if response.status_code == 200:
        return True
    
    # V6.3: Enhanced error logging for diagnostics
    try:
        error_data = response.json()
        error_message = error_data.get('message', 'No message')
        
        # Credit exhaustion
        if 'Not enough credits' in error_message:
            if not _SERPER_CREDITS_EXHAUSTED:
                logging.warning("⚠️ SERPER API: Credits exhausted! Switching to DDG if available.")
                _SERPER_CREDITS_EXHAUSTED = True
            return False
        
        # V6.3: HTTP 400 - Bad Request (query issue)
        if response.status_code == 400:
            query_preview = (query[:100] + '...') if query and len(query) > 100 else (query or 'N/A')
            logging.warning(
                f"⚠️ SERPER HTTP 400 (Bad Request): {error_message} | "
                f"Query length: {len(query) if query else 0} | "
                f"Query preview: {query_preview}"
            )
            return False
        
        # V6.3: HTTP 429 - Rate limit
        if response.status_code == 429:
            logging.warning(f"⚠️ SERPER HTTP 429 (Rate Limit): {error_message}")
            return False
        
        # Other errors with message
        logging.error(f"❌ SERPER HTTP {response.status_code}: {error_message}")
        
    except Exception as e:
        # V6.3: Log raw response text for non-JSON errors
        response_preview = response.text[:200] if response.text else 'Empty response'
        logging.error(
            f"❌ SERPER HTTP {response.status_code} (non-JSON): {response_preview} | "
            f"Parse error: {e}"
        )
    
    return False

def _is_serper_available() -> bool:
    """Check if Serper API is available."""
    if _SERPER_CREDITS_EXHAUSTED:
        return False
    if not SERPER_API_KEY or "YOUR_SERPER_API_KEY" in SERPER_API_KEY:
        return False
    return True

def _is_ddg_available() -> bool:
    """Check if DuckDuckGo search provider is available."""
    if not _SEARCH_PROVIDER_AVAILABLE:
        return False
    try:
        provider = get_search_provider()
        return provider.is_available()
    except Exception as e:
        logging.debug(f"Search provider availability check failed: {e}")
        return False

def _get_search_backend() -> str:
    """Determine which search backend to use.
    
    Returns: 'ddg', 'serper', or 'none'
    """
    # Priority 1: DuckDuckGo (free, native)
    if _is_ddg_available():
        return 'ddg'
    
    # Priority 2: Serper (paid, limited)
    if _is_serper_available():
        return 'serper'
    
    return 'none'


# ============================================
# V4.3: BEAT WRITER PRIORITY SEARCH
# V7.0: Now uses Twitter Intel Cache instead of broken site:twitter.com
# ============================================

def search_beat_writers_priority(
    team_alias: str,
    league_key: str,
    match_id: str
) -> List[Dict]:
    """
    V7.0: PRIORITY search for beat writer content via Twitter Intel Cache.
    
    This function is called BEFORE generic searches to catch breaking news
    from verified beat writers. Results are tagged with:
    - confidence: "HIGH"
    - priority_boost: 1.5
    - source_type: "beat_writer"
    
    Beat writers often break news 10-30 minutes before mainstream media,
    giving us a significant edge in the betting market.
    
    V7.0: Now uses TwitterIntelCache instead of broken site:twitter.com search.
    The cache is populated at cycle start with tweets from configured insider
    accounts (including beat writers) via DeepSeek/Gemini with Nitter fallback.
    
    V9.0: Now fetches beat writers from Supabase social_sources table
    with fallback to local sources_config.py.
    
    Args:
        team_alias: Team name to search for
        league_key: League API key (e.g., 'soccer_argentina_primera_division')
        match_id: Match ID for tracking
        
    Returns:
        List of search results with HIGH confidence tagging
    """
    results = []
    
    # Guard: empty team alias
    if not team_alias or not team_alias.strip():
        return results
    
    # Get beat writers for this league (for metadata enrichment)
    # V9.0: Try Supabase first, fallback to local config
    beat_writers = get_beat_writers_from_supabase(league_key)
    beat_writer_handles = {w.handle.lower().replace('@', ''): w for w in beat_writers} if beat_writers else {}
    
    # V7.0: Use Twitter Intel Cache instead of broken search
    if not _TWITTER_INTEL_CACHE_AVAILABLE:
        logging.debug("Twitter Intel Cache not available for beat writer search")
        return results
    
    try:
        cache = get_twitter_intel_cache()
        
        if not cache.is_fresh:
            logging.debug(f"Twitter Intel cache not fresh for beat writer search")
            return results
        
        # Search cache for team mentions
        topics_filter = ['injury', 'lineup', 'squad', 'out', 'doubt', 'miss', 'transfer']
        
        # V7.0.1: Try league-specific search first, then global fallback
        relevant_tweets = cache.search_intel(
            query=team_alias,
            league_key=league_key,
            topics=topics_filter
        )
        
        # Fallback: search entire cache if league-specific search found nothing
        if not relevant_tweets:
            relevant_tweets = cache.search_intel(
                query=team_alias,
                league_key=None,  # Search all cached accounts
                topics=topics_filter
            )
        
        if not relevant_tweets:
            logging.debug(f"No beat writer intel found for {team_alias}")
            return results
        
        logging.info(f"⭐ BEAT WRITER PRIORITY: Found {len(relevant_tweets)} cached tweets for {team_alias}")
        
        for tweet in relevant_tweets[:5]:
            handle_clean = tweet.handle.lower().replace('@', '') if tweet.handle else ''
            
            # Check if this tweet is from a known beat writer
            source_writer = beat_writer_handles.get(handle_clean)
            
            result = {
                'match_id': match_id,
                'team': team_alias,
                'keyword': 'beat_writer_priority',
                'title': f"@{handle_clean}: {tweet.content[:60]}..." if len(tweet.content) > 60 else f"@{handle_clean}: {tweet.content}",
                'snippet': tweet.content,
                'link': f"https://twitter.com/{handle_clean}",
                'date': tweet.date or '',
                'source': tweet.handle or 'Twitter Intel',
                'search_type': 'beat_writer_cache',
                'confidence': 'HIGH',
                'priority_boost': 1.5,
                'source_type': 'beat_writer' if source_writer else 'twitter_intel',
                'topics': tweet.topics if tweet.topics else []
            }
            
            # Add beat writer metadata if identified
            if source_writer:
                result['beat_writer_name'] = source_writer.name
                result['beat_writer_outlet'] = source_writer.outlet
                result['beat_writer_specialty'] = source_writer.specialty
                result['beat_writer_reliability'] = source_writer.reliability
            
            results.append(result)
        
        if results:
            logging.info(f"   ⭐ [CACHE] Found {len(results)} beat writer results")
        
    except Exception as e:
        logging.warning(f"Beat writer cache search failed: {e}")
    
    return results


# ============================================
# EXOTIC LEAGUE SEARCH STRATEGIES
# ============================================
# Each exotic league has custom search strategies due to
# hard-to-scrape sources (Weibo, YouTube Live, etc.)
# Solution: Use "Proxy Sources" - Twitter aggregators and text tickers

EXOTIC_SEARCH_STRATEGIES = {
    "australia": {
        "name": "A-League (Australia)",
        "search_type": "search",  # Web search to catch official articles
        "strategies": [
            {
                "name": "aleagues_official",
                "template": 'site:aleagues.com.au ("ins and outs" OR "injury update") {team_name}',
                "description": "A-Leagues Official - Ins & Outs articles (GOLDEN SOURCE)",
                "priority": 1,
            },
            {
                "name": "keepup",
                "template": 'site:keepup.com.au {team_name} (injury OR lineup OR squad)',
                "description": "Keep Up - A-League specialist",
                "priority": 2,
            },
            {
                "name": "foxsports_au",
                "template": 'site:foxsports.com.au {team_name} a-league (team news OR injury)',
                "description": "Fox Sports Australia",
                "priority": 3,
            },
        ],
    },
    "china": {
        "name": "China Super League",
        "search_type": "search",  # Web search (not news) to catch Twitter
        "strategies": [
            {
                "name": "twitter_proxy",
                "template": 'site:twitter.com "HotpotFootball" {team_name}',
                "description": "Twitter proxy - faster than Weibo scraping",
                "priority": 1,
            },
            {
                "name": "dongqiudi",
                "template": 'site:dongqiudi.com {team_name}',
                "description": "Dongqiudi - Chinese football portal",
                "priority": 2,
            },
        ],
    },
    "japan": {
        "name": "J-League",
        "search_type": "mixed",  # Both news and web search
        "strategies": [
            {
                "name": "nikkansports",
                "template": 'site:nikkansports.com {team_name} (injury OR lineup OR 怪我 OR スタメン)',
                "search_type": "news",
                "description": "Nikkan Sports - official + tabloid",
                "priority": 1,
            },
            {
                "name": "official_releases",
                "template": '{team_name} "press release" OR "official" OR "公式"',
                "search_type": "search",  # Web search to catch club sites
                "description": "Official club releases",
                "priority": 2,
            },
        ],
    },
    "brazil_b": {
        "name": "Brazil Serie B",
        "search_type": "news",
        "strategies": [
            {
                "name": "lance_ticker",
                "template": 'site:lance.com.br {team_name} (urgente OR desfalque OR escalação)',
                "description": "Lance! text ticker - CazéTV mirror",
                "priority": 1,
            },
            {
                "name": "globo_esporte",
                "template": 'site:globoesporte.globo.com {team_name} serie b',
                "description": "Globo Esporte - major portal",
                "priority": 2,
            },
        ],
    },
}


def get_search_strategy(league_key: str) -> dict:
    """
    Get custom search strategy for a league.
    
    SPECIAL LEAGUES use custom strategies:
    - Australia: Official "Ins & Outs" articles from aleagues.com.au
    - China/Japan/Brazil B: Proxy sources (Twitter aggregators, text tickers)
    
    Args:
        league_key: API league key (e.g., 'soccer_australia_aleague')
        
    Returns:
        Strategy dict with search templates, or None for standard leagues
    """
    # STRICT matching by exact league key
    LEAGUE_TO_STRATEGY = {
        "soccer_australia_aleague": "australia",
        "soccer_china_superleague": "china",
        "soccer_japan_j_league": "japan",
        "soccer_brazil_serie_b": "brazil_b",
    }
    
    strategy_key = LEAGUE_TO_STRATEGY.get(league_key)
    if strategy_key:
        return EXOTIC_SEARCH_STRATEGIES[strategy_key]
    
    return None  # Standard league - use default search


def get_native_keywords(language_code: str) -> List[str]:
    return NATIVE_KEYWORDS.get(language_code, [])

def get_country_code(language_code: str) -> str:
    # Approximate mapping for GL parameter
    gl_map = {'pt': 'br', 'tr': 'tr', 'pl': 'pl', 'ro': 'ro', 'es': 'co'}
    return gl_map.get(language_code, 'us')


# ============================================
# DYNAMIC COUNTRY-AGNOSTIC SEARCH
# ============================================
# For leagues not in sources_config, auto-detect country and search

# Country code extraction from league key
LEAGUE_COUNTRY_CODES = {
    # Scandinavia
    "sweden": "se", "norway": "no", "denmark": "dk", "finland": "fi",
    # Western Europe
    "austria": "at", "switzerland": "ch", "netherlands": "nl", "belgium": "be",
    "portugal": "pt", "france": "fr", "germany": "de", "spain": "es", "italy": "it",
    # Eastern Europe
    "romania": "ro", "bulgaria": "bg", "serbia": "rs", "croatia": "hr",
    "czech": "cz", "poland": "pl", "ukraine": "ua",
    # UK
    "england": "uk", "scotland": "uk", "spl": "uk",
    # Asia
    "korea": "kr", "saudi": "sa", "china": "cn", "japan": "jp",
    # South America
    "colombia": "co", "chile": "cl", "uruguay": "uy", "ecuador": "ec",
    "peru": "pe", "brazil": "br", "argentina": "ar", "mexico": "mx",
    # Africa
    "africa": "com",  # Use .com for pan-African
    # Other
    "usa": "us", "australia": "au", "turkey": "tr", "greece": "gr",
}

# Multi-language injury/lineup keywords for dynamic search
UNIVERSAL_KEYWORDS = {
    "en": ["injury", "lineup", "squad", "ruled out", "team news"],
    "es": ["lesión", "alineación", "convocados", "baja"],
    "pt": ["lesão", "escalação", "desfalque"],
    "de": ["verletzung", "aufstellung", "kader"],
    "fr": ["blessure", "composition", "absent"],
    "it": ["infortunio", "formazione", "assente"],
    "pl": ["kontuzja", "skład", "absencja"],
    "ro": ["accidentare", "echipa", "absent"],
    "tr": ["sakatlık", "kadro", "eksik"],
    "sv": ["skada", "uppställning", "saknas"],  # Swedish
    "no": ["skade", "lagoppstilling"],  # Norwegian
    "da": ["skade", "startopstilling"],  # Danish
    "hr": ["ozljeda", "postava"],  # Croatian
    "sr": ["povreda", "sastav"],  # Serbian
    "bg": ["контузия", "състав"],  # Bulgarian
    "uk": ["травма", "склад"],  # Ukrainian
    "ko": ["부상", "라인업"],  # Korean
    "ar": ["إصابة", "تشكيلة"],  # Arabic (Saudi)
}

# Country to language mapping
COUNTRY_LANGUAGE = {
    # Scandinavia
    "se": "sv", "no": "no", "dk": "da", "fi": "en",
    # Western Europe
    "at": "de", "ch": "de", "nl": "en", "be": "en",
    "pt": "pt", "fr": "fr", "de": "de", "es": "es", "it": "it",
    # Eastern Europe
    "ro": "ro", "bg": "bg", "rs": "sr", "hr": "hr",
    "cz": "en", "pl": "pl", "ua": "uk",
    # UK
    "uk": "en",
    # Asia
    "kr": "ko", "sa": "ar", "cn": "en", "jp": "en",
    # South America
    "co": "es", "cl": "es", "uy": "es", "ec": "es", "pe": "es",
    "br": "pt", "ar": "es", "mx": "es",
    # Africa
    "com": "en",
    # Other
    "us": "en", "au": "en", "tr": "tr", "gr": "en",
}


def extract_country_from_league(league_key: str) -> Optional[str]:
    """
    Extract country code from league key.
    
    Examples:
        soccer_sweden_allsvenskan -> se
        soccer_korea_kleague1 -> kr
        soccer_saudi_pro_league -> sa
    """
    league_lower = league_key.lower()
    
    for country_name, code in LEAGUE_COUNTRY_CODES.items():
        if country_name in league_lower:
            return code
    
    return None


def build_dynamic_search_query(team_name: str, league_key: str) -> tuple:
    """
    Build a country-agnostic search query for leagues not in sources_config.
    
    Strategy:
    1. Detect country from league key
    2. Get native language keywords
    3. Build query with country TLD site restriction
    
    Args:
        team_name: Team to search
        league_key: League API key
        
    Returns:
        Tuple of (query_string, country_code)
    """
    country_code = extract_country_from_league(league_key)
    
    if not country_code:
        # Fallback to generic English search
        return f'"{team_name}" (injury OR lineup OR squad OR "team news")', "us"
    
    # Get language for this country
    lang = COUNTRY_LANGUAGE.get(country_code, "en")
    
    # Get keywords in native language + English
    native_kw = UNIVERSAL_KEYWORDS.get(lang, [])
    english_kw = UNIVERSAL_KEYWORDS.get("en", [])
    
    # Combine unique keywords
    all_keywords = list(set(native_kw + english_kw[:2]))[:4]
    kw_string = " OR ".join(all_keywords)
    
    # Build query with country TLD
    # site:.{country_code} restricts to that country's domains
    query = f'"{team_name}" ({kw_string}) site:.{country_code}'
    
    logging.info(f"🌍 Dynamic search [{country_code}]: {query[:60]}...")
    
    return query, country_code


def search_dynamic_country(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    DYNAMIC COUNTRY-AGNOSTIC SEARCH for leagues not in sources_config.
    
    Automatically detects country from league key and searches
    country-specific domains with native + English keywords.
    
    V6.1: Now supports DDG backend with Serper fallback.
    
    Args:
        team_alias: Team name to search
        league_key: League API key
        match_id: Match ID for tracking
        
    Returns:
        List of search results
    """
    results = []
    query, country_code = build_dynamic_search_query(team_alias, league_key)
    
    # ============================================
    # DDG BACKEND (PRIMARY - FREE)
    # ============================================
    backend = _get_search_backend()
    
    if backend == 'ddg':
        try:
            provider = get_search_provider()
            ddg_results = provider.search_news(query, num_results=5, league_key=league_key)
            
            for item in ddg_results:
                results.append({
                    'match_id': match_id,
                    'team': team_alias,
                    'keyword': f'dynamic_{country_code}',
                    'title': safe_dict_get(item, 'title', default=''),
                    'snippet': safe_dict_get(item, 'snippet', default=''),
                    'link': safe_dict_get(item, 'link', default=''),
                    'date': safe_dict_get(item, 'date', default=None),
                    'source': safe_dict_get(item, 'source', default=f'Dynamic ({country_code})'),
                    'search_type': 'dynamic_country'
                })
            
            if results:
                logging.info(f"   🌍 [DDG] Dynamic search found {len(results)} results")
            return results
            
        except Exception as e:
            logging.warning(f"DDG dynamic search failed: {e}")
            # Fall through to Serper
    
    # ============================================
    # SERPER BACKEND (FALLBACK - PAID)
    # ============================================
    if not _is_serper_available():
        return results
    
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    post_data = {
        "q": query,
        "tbs": "qdr:d",  # Last 24 hours
        "num": 5,
        "gl": country_code
    }
    
    try:
        time.sleep(SERPER_RATE_LIMIT_DELAY)
        response = requests.post(SERPER_URL, headers=headers, json=post_data, timeout=SERPER_REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if 'organic' in data:
                for item in data['organic']:
                    results.append({
                        'match_id': match_id,
                        'team': team_alias,
                        'keyword': f'dynamic_{country_code}',
                        'title': safe_dict_get(item, 'title', default=''),
                        'snippet': safe_dict_get(item, 'snippet', default=''),
                        'link': safe_dict_get(item, 'link', default=''),
                        'date': safe_dict_get(item, 'date', default=None),
                        'source': safe_dict_get(item, 'source', default=f'Dynamic ({country_code})'),
                        'search_type': 'dynamic_country'
                    })
            logging.info(f"   🌍 [Serper] Dynamic search found {len(results)} results")
        else:
            _check_serper_response(response, query=query)
            
    except Exception as e:
        logging.error(f"Error in dynamic search: {e}")
    
    return results

def search_exotic_league(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    EXOTIC LEAGUE SEARCH: Custom strategies for China, Japan, Brazil B.
    
    Uses "Proxy Sources" strategy:
    - China: Twitter aggregators (@HotpotFootball) instead of Weibo
    - Japan: Nikkan Sports + official club releases (web search)
    - Brazil B: Lance! ticker + Globo Esporte
    
    V6.1: Now supports DDG backend with Serper fallback.
    
    Args:
        team_alias: Team name to search
        league_key: League API key
        match_id: Match ID for tracking
        
    Returns:
        List of search results from exotic strategy
    """
    strategy = get_search_strategy(league_key)
    if not strategy:
        return []
    
    backend = _get_search_backend()
    if backend == 'none':
        logging.warning("No search backend available for exotic league search")
        return []
    
    results = []
    
    logging.info(f"🌏 EXOTIC SEARCH: {strategy['name']} strategy for {team_alias}")
    
    for strat in strategy["strategies"]:
        # Build query from template
        query = strat["template"].format(team_name=team_alias)
        
        # Determine search type (news vs web)
        search_type = strat.get("search_type", strategy.get("search_type", "news"))
        
        logging.info(f"   🔍 [{strat['name']}] {search_type}: {query[:60]}...")
        
        # ============================================
        # DDG BACKEND (PRIMARY - FREE)
        # ============================================
        if backend == 'ddg':
            try:
                provider = get_search_provider()
                ddg_results = provider.search_news(query, num_results=5, league_key=league_key)
                
                for item in ddg_results:
                    results.append({
                        'match_id': match_id,
                        'team': team_alias,
                        'keyword': strat['name'],
                        'title': safe_dict_get(item, 'title', default=''),
                        'snippet': safe_dict_get(item, 'snippet', default='') or safe_dict_get(item, 'description', default=''),
                        'link': safe_dict_get(item, 'link', default=''),
                        'date': safe_dict_get(item, 'date', default=None),
                        'source': safe_dict_get(item, 'source', default=strat['name']),
                        'search_type': f"exotic_{strat['name']}",
                        'strategy': strategy['name'],
                    })
                
                if ddg_results:
                    logging.info(f"   ✅ [{strat['name']}] [DDG] Found {len(ddg_results)} results")
                continue  # Move to next strategy
                
            except Exception as e:
                logging.warning(f"DDG exotic search failed for {strat['name']}: {e}")
                # Fall through to Serper for this strategy
        
        # ============================================
        # SERPER BACKEND (FALLBACK - PAID)
        # ============================================
        if not _is_serper_available():
            continue
        
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        
        url = SERPER_NEWS_URL if search_type == "news" else SERPER_URL
        
        post_data = {
            "q": query,
            "num": 5,
        }
        
        # Add time filter for freshness
        if search_type == "search":
            post_data["tbs"] = "qdr:d"  # Last 24 hours
        
        try:
            time.sleep(SERPER_RATE_LIMIT_DELAY)
            response = requests.post(url, headers=headers, json=post_data, timeout=SERPER_REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle both news and organic results
                items = data.get('news', data.get('organic', []))
                
                for item in items:
                    results.append({
                        'match_id': match_id,
                        'team': team_alias,
                        'keyword': strat['name'],
                        'title': safe_dict_get(item, 'title', default=''),
                        'snippet': safe_dict_get(item, 'snippet', default='') or safe_dict_get(item, 'description', default=''),
                        'link': safe_dict_get(item, 'link', default=''),
                        'date': safe_dict_get(item, 'date', default=None),
                        'source': safe_dict_get(item, 'source', default=strat['name']),
                        'search_type': f"exotic_{strat['name']}",
                        'strategy': strategy['name'],
                    })
                
                logging.info(f"   ✅ [{strat['name']}] [Serper] Found {len(items)} results")
            else:
                _check_serper_response(response, query=query)
                
        except Exception as e:
            logging.error(f"   ❌ Error in exotic search ({strat['name']}): {e}")
    
    return results


def search_twitter_rumors(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    TWITTER INTEL V7.0: Use cached Twitter Intel instead of broken search.
    
    Since Twitter/X blocks search engine indexing (site:twitter.com returns 0 results
    on all search engines since mid-2023), we now leverage the TwitterIntelCache
    populated at cycle start via DeepSeek/Gemini with Nitter fallback.
    
    This approach:
    - Uses verified insider accounts (configured in twitter_intel_accounts.py)
    - Zero API calls (cache lookup is O(1))
    - Higher quality data (curated accounts vs random search results)
    - Nitter fallback ensures data even when AI providers fail
    
    Args:
        team_alias: Team name to search
        league_key: League API key for filtering
        match_id: Match ID for tracking
        
    Returns:
        List of Twitter results from cache
    """
    results = []
    
    # Guard: empty team alias
    if not team_alias or not team_alias.strip():
        return results
    
    # V7.0: Use Twitter Intel Cache instead of broken search engine queries
    if not _TWITTER_INTEL_CACHE_AVAILABLE:
        logging.debug("Twitter Intel Cache not available, skipping Twitter search")
        return results
    
    try:
        cache = get_twitter_intel_cache()
        
        # Check if cache is fresh (populated this cycle)
        if not cache.is_fresh:
            logging.debug(f"🐦 Twitter Intel cache not fresh ({cache.cache_age_minutes}m old), skipping")
            return results
        
        # Search cache for team-relevant tweets
        # Topics filter ensures we get injury/lineup news, not random mentions
        topics_filter = ['injury', 'lineup', 'squad', 'out', 'doubt', 'miss', 'absent']
        
        # V7.0.1: Try league-specific search first (more precise), then global fallback
        relevant_tweets = cache.search_intel(
            query=team_alias,
            league_key=league_key,
            topics=topics_filter
        )
        
        # Fallback: search entire cache if league-specific search found nothing
        if not relevant_tweets:
            relevant_tweets = cache.search_intel(
                query=team_alias,
                league_key=None,  # Search all cached accounts
                topics=topics_filter
            )
        
        if not relevant_tweets:
            logging.debug(f"🐦 No cached Twitter intel for {team_alias}")
            return results
        
        # Convert CachedTweet objects to result dicts (max 5)
        for tweet in relevant_tweets[:5]:
            # Build Twitter URL from handle
            handle_clean = tweet.handle.replace('@', '') if tweet.handle else 'unknown'
            twitter_url = f"https://twitter.com/{handle_clean}"
            
            # Build title from handle + content preview
            title = f"@{handle_clean}: {tweet.content[:60]}..." if len(tweet.content) > 60 else f"@{handle_clean}: {tweet.content}"
            
            results.append({
                'match_id': match_id,
                'team': team_alias,
                'keyword': 'twitter_intel_cache',
                'title': title,
                'snippet': tweet.content,
                'link': twitter_url,
                'date': tweet.date or '',
                'source': 'Twitter/X (Intel Cache)',
                'search_type': 'twitter_intel_cache',
                'confidence': 'HIGH',  # Verified insider accounts
                'priority_boost': 1.3,  # Boost for real-time intel
                'topics': tweet.topics if tweet.topics else [],
                'source_type': 'twitter_intel'
            })
        
        if results:
            logging.info(f"🐦 [CACHE] Found {len(results)} Twitter intel for {team_alias} (cache age: {cache.cache_age_minutes}m)")
        
    except Exception as e:
        logging.warning(f"🐦 Twitter Intel Cache search failed: {e}")
    
    return results


def search_news_local(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    HYPER-LOCAL NEWS SEARCH with site-dorking + Twitter hack.
    
    Uses DuckDuckGo (native) if available, falls back to Serper API.
    
    V6.2: Fixed dead fallback - now properly falls through to Serper when DDG fails.
    
    Strategy:
    0. EXOTIC CHECK: If exotic league, use custom proxy strategy first
    1. Primary: Site-dorked query on local news sources
    2. Secondary: Twitter/X search for real-time rumors
    3. Fallback: Generic search if no results
    
    Args:
        team_alias: Team name to search
        league_key: League API key (e.g., 'soccer_argentina_primera_division')
        match_id: Match ID for tracking
        
    Returns:
        List of merged news results
    """
    if os.getenv("USE_MOCK_DATA") == "true":
        from src.mocks import MOCK_SEARCH_RESULTS
        return MOCK_SEARCH_RESULTS.get(match_id, [])

    # Determine search backend
    backend = _get_search_backend()
    if backend == 'none':
        logging.warning("No search backend available (DDG down, Serper exhausted)")
        return []
    
    # Get local sources and keywords for this league
    sources = get_sources_for_league(league_key)
    keywords = get_keywords_for_league(league_key)
    country = get_country_from_league(league_key)
    
    results = []
    
    # ============================================
    # STRATEGY 0: EXOTIC LEAGUE PROXY SEARCH
    # ============================================
    exotic_strategy = get_search_strategy(league_key)
    if exotic_strategy:
        logging.info(f"🌏 Detected EXOTIC league: {exotic_strategy['name']}")
        exotic_results = search_exotic_league(team_alias, league_key, match_id)
        results.extend(exotic_results)
        
        if exotic_results:
            logging.info(f"   🌏 Exotic search found {len(exotic_results)} results - skipping standard")
            return results
        else:
            logging.info(f"   🌏 Exotic search empty - falling back to standard")
    
    # V6.2: Flag to track if we should use Serper (either as primary or fallback)
    use_serper = (backend == 'serper')
    ddg_succeeded = False
    
    # ============================================
    # DDG BACKEND (FREE, NATIVE)
    # ============================================
    if backend == 'ddg':
        logging.info(f"🔍 [DDG] Local search for {team_alias}...")
        try:
            provider = get_search_provider()
            ddg_results = provider.search_local_news(
                team_name=team_alias,
                domains=sources[:3] if sources else [],
                keywords=keywords[:2] if keywords else ['injury', 'lineup'],
                num_results=5,
                league_key=league_key
            )
            
            for item in ddg_results:
                results.append({
                    'match_id': match_id,
                    'team': team_alias,
                    'keyword': 'local_news',
                    'title': safe_dict_get(item, 'title', default=''),
                    'snippet': safe_dict_get(item, 'snippet', default=''),
                    'link': safe_dict_get(item, 'link', default=''),
                    'date': safe_dict_get(item, 'date', default=None),
                    'source': safe_dict_get(item, 'source', default='DuckDuckGo'),
                    'search_type': 'ddg_local'
                })
            
            logging.info(f"   📰 [DDG] Found {len(ddg_results)} local news results")
            
            # V7.0: Use Twitter Intel Cache instead of broken DDG Twitter search
            # (site:twitter.com returns 0 results since Twitter blocked indexing)
            twitter_cache_results = search_twitter_rumors(team_alias, league_key, match_id)
            results.extend(twitter_cache_results)
            
            ddg_succeeded = True
            
        except Exception as e:
            logging.error(f"DDG search failed: {e}")
            # V6.2: Set flag to fall through to Serper
            if _is_serper_available():
                use_serper = True
                logging.info("   ⚠️ Falling back to Serper...")
    
    # V6.2: Return early only if DDG succeeded
    if ddg_succeeded:
        return results
    
    # ============================================
    # SERPER BACKEND (PAID, FALLBACK)
    # V6.2: Now properly reached when DDG fails
    # ============================================
    if not use_serper:
        # Neither DDG nor Serper available
        return results
    
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Country code mapping for Serper
    gl_map = {
        'argentina': 'ar', 'mexico': 'mx', 'greece': 'gr',
        'turkey': 'tr', 'scotland': 'uk',
        'china': 'cn', 'japan': 'jp', 'brazil_b': 'br'
    }
    country_code = gl_map.get(country, 'us')
    
    # ============================================
    # STRATEGY 1: Site-dorked local news query
    # Uses top 3 domains + native keywords for comprehensive coverage
    # ============================================
    if sources:
        # Use top 3 domains for good coverage
        site_dork = " OR ".join([f"site:{domain}" for domain in sources[:3]])
        # Use top 2 keywords (native + English fallback)
        kw_string = " OR ".join(keywords[:2]) if len(keywords) >= 2 else keywords[0] if keywords else "injury"
        
        query = f'"{team_alias}" ({kw_string}) ({site_dork})'
        logging.info(f"🔍 [Serper] Local search: {query[:70]}...")
        
        post_data = {
            "q": query,
            "tbs": "qdr:d",  # Last 24 hours
            "num": 5,
            "gl": country_code
        }
        
        try:
            time.sleep(SERPER_RATE_LIMIT_DELAY)
            response = requests.post(SERPER_URL, headers=headers, json=post_data, timeout=SERPER_REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if 'organic' in data:
                    for item in data['organic']:
                        results.append({
                            'match_id': match_id,
                            'team': team_alias,
                            'keyword': kw_string[:30],
                            'title': safe_dict_get(item, 'title', default=''),
                            'snippet': safe_dict_get(item, 'snippet', default=''),
                            'link': safe_dict_get(item, 'link', default=''),
                            'date': safe_dict_get(item, 'date', default=None),
                            'source': safe_dict_get(item, 'source', default=''),
                            'search_type': 'local_site_dork'
                        })
                logging.info(f"   📰 Found {len(results)} local news results")
            else:
                _check_serper_response(response, query=query)
                
        except Exception as e:
            logging.error(f"Error in local search: {e}")
    
    # ============================================
    # STRATEGY 2: Twitter/X hack for real-time rumors
    # ============================================
    twitter_results = search_twitter_rumors(team_alias, league_key, match_id)
    results.extend(twitter_results)
    
    # ============================================
    # STRATEGY 3: DYNAMIC COUNTRY SEARCH (for unconfigured leagues)
    # ============================================
    if not results and not sources:
        # League not in sources_config - use dynamic country detection
        logging.info(f"🌍 No configured sources - trying dynamic country search for {league_key}")
        dynamic_results = search_dynamic_country(team_alias, league_key, match_id)
        results.extend(dynamic_results)
    
    # ============================================
    # STRATEGY 4: Fallback to generic if still nothing
    # ============================================
    if not results:
        logging.info(f"🔍 Fallback to generic search for {team_alias}")
        results = search_news_generic(team_alias, keywords if keywords else ["injury", "lineup"], country_code, match_id)
    
    return results


def search_news_generic(team_alias: str, keywords: List[str], country_code: str, match_id: str) -> List[Dict]:
    """
    Generic news search without site-dorking (fallback).
    """
    if not _is_serper_available():
        return []

    results = []
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Use top 2 keywords
    target_keywords = keywords[:2] if keywords else ["injury", "lineup"]
    
    for keyword in target_keywords:
        query = f'"{team_alias}" {keyword}'
        
        post_data = {
            "q": query,
            "tbs": "qdr:d",
            "num": 3,
            "gl": country_code
        }
        
        try:
            time.sleep(SERPER_RATE_LIMIT_DELAY_SLOW)
            response = requests.post(SERPER_URL, headers=headers, json=post_data, timeout=SERPER_REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if 'organic' in data:
                    for item in data['organic']:
                            results.append({
                                'match_id': match_id,
                                'team': team_alias,
                                'keyword': keyword,
                                'title': safe_dict_get(item, 'title', default=''),
                                'snippet': safe_dict_get(item, 'snippet', default=''),
                                'link': safe_dict_get(item, 'link', default=''),
                                'date': safe_dict_get(item, 'date', default=None),
                                'source': safe_dict_get(item, 'source', default=''),
                                'search_type': 'generic'
                            })
            else:
                _check_serper_response(response, query=query)
                
        except Exception as e:
            logging.error(f"Error in generic search: {e}")
            
    return results


def search_news(team_alias: str, language_code: str, match_id: str, league_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Main search function - routes to local or generic search.
    
    If league_key is provided, uses hyper-local search with site-dorking.
    Otherwise falls back to generic keyword search.
    
    Args:
        team_alias: Team name to search for
        language_code: Language code for keywords (e.g., 'en', 'es')
        match_id: Match ID for tracking
        league_key: League API key for contextual search (optional)
        
    Returns:
        List of news items as dictionaries
    """
    if not team_alias or not isinstance(team_alias, str):
        logging.warning("search_news called with invalid team_alias")
        return []
    
    if league_key:
        return search_news_local(team_alias, league_key, match_id)
    
    # Legacy fallback
    keywords = get_native_keywords(language_code)
    country_code = get_country_code(language_code)
    return search_news_generic(team_alias, keywords, country_code, match_id)


# ============================================
# MODULE EXPORTS
# ============================================

__all__ = [
    'run_hunter_for_match',
    'search_news',
    'search_news_local',
    'search_news_generic',
    'search_beat_writers_priority',
    'search_twitter_rumors',
    'search_exotic_league',
    'search_dynamic_country',
    'register_browser_monitor_discovery',
    'get_browser_monitor_news',
    'clear_browser_monitor_discoveries',
    'cleanup_expired_browser_monitor_discoveries',
    'get_browser_monitor_stats',
    'SERPER_REQUEST_TIMEOUT',
    'SERPER_RATE_LIMIT_DELAY',
    '_SERPER_CREDITS_EXHAUSTED',
    'DEEP_DIVE_ENABLED',
    'DEEP_DIVE_MAX_ARTICLES',
    'DEEP_DIVE_TIMEOUT',
    'DEEP_DIVE_SNIPPET_THRESHOLD',
    'DEEP_DIVE_TRIGGERS',
]


# ============================================
# INSIDER INTEL LAYER (Beat Writers)
# ============================================

def search_beat_writers(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    DEPRECATED: This function is no longer called in the main flow.
    
    V1.1 Fix #2: Beat writers are now searched via search_beat_writers_priority() 
    in TIER 0.5, which is called earlier in run_hunter_for_match().
    
    This function is kept for backward compatibility but logs a deprecation warning.
    Use search_beat_writers_priority() instead.
    
    Original purpose:
    Search Twitter for beat writer and insider account mentions.
    Beat writers often break news before mainstream media.
    
    Args:
        team_alias: Team name to search
        league_key: League API key
        match_id: Match ID for tracking
        
    Returns:
        List of insider Twitter results (empty if deprecated path used)
    """
    import warnings
    warnings.warn(
        "search_beat_writers() is deprecated. Use search_beat_writers_priority() instead. "
        "Beat writers are now searched in TIER 0.5 for better priority.",
        DeprecationWarning,
        stacklevel=2
    )
    logging.warning(
        f"⚠️ DEPRECATED: search_beat_writers() called for {team_alias}. "
        f"This function is no longer used - beat writers are in TIER 0.5."
    )
    
    # Still execute for backward compatibility, but prefer search_beat_writers_priority
    if not _is_serper_available():
        return []
    
    insider_handles = get_insider_handles(league_key)
    if not insider_handles:
        return []
    
    results = []
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Build query with top 3 insider handles
    handles_query = " OR ".join([f'"{h}"' for h in insider_handles[:3]])
    query = f'site:twitter.com ({handles_query}) "{team_alias}"'
    
    logging.info(f"🎯 Beat Writer search: {query[:70]}...")
    
    post_data = {
        "q": query,
        "tbs": "qdr:d",  # Last 24 hours
        "num": 5
    }
    
    try:
        time.sleep(SERPER_RATE_LIMIT_DELAY)
        response = requests.post(SERPER_URL, headers=headers, json=post_data, timeout=SERPER_REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if 'organic' in data:
                for item in data['organic']:
                    # Try to identify which insider posted
                    source_handle = "Unknown Insider"
                    link = safe_dict_get(item, 'link', default='').lower()
                    for handle in insider_handles:
                        if handle.lower().replace('@', '') in link:
                            source_handle = handle
                            break
                    
                    results.append({
                        'match_id': match_id,
                        'team': team_alias,
                        'keyword': 'beat_writer',
                        'title': safe_dict_get(item, 'title', default=''),
                        'snippet': safe_dict_get(item, 'snippet', default=''),
                        'link': safe_dict_get(item, 'link', default=''),
                        'date': safe_dict_get(item, 'date', default=None),
                        'source': source_handle,
                        'search_type': 'insider_beat_writer',
                        'confidence': 'HIGH'  # Beat writers are reliable
                    })
            logging.info(f"   🎯 Found {len(results)} beat writer results")
        else:
            _check_serper_response(response, query=query)
            
    except Exception as e:
        logging.error(f"Error in beat writer search: {e}")
    
    return results


# ============================================
# V8.0: search_reddit_deep() REMOVED
# ============================================
# Reddit deep scan provided no betting edge - rumors arrived too late.
# Function removed to save API calls and reduce latency.
# Historical note: Used site:reddit.com/r/{subreddit} queries via DDG/Serper.


def search_insiders(team_alias: str, league_key: str, match_id: str) -> List[Dict]:
    """
    INSIDER INTEL LAYER: Placeholder for future insider sources.
    
    V8.0: Reddit deep scan removed - provided no betting edge.
    Beat writers are already searched in TIER 0.5 (search_beat_writers_priority).
    
    This function now returns empty list but is kept for:
    1. Backward compatibility with callers
    2. Future expansion (Telegram private channels, WhatsApp bridges, etc.)
    
    Args:
        team_alias: Team name to search
        league_key: League API key
        match_id: Match ID for tracking
        
    Returns:
        Empty list (placeholder for future insider sources)
    """
    # V8.0: Reddit removed, beat writers moved to TIER 0.5
    # This function is now a placeholder for future insider sources
    # such as Telegram private channels or WhatsApp bridges
    
    # Log only in debug to avoid noise
    logging.debug(f"🕵️ INSIDER INTEL: No additional sources for {team_alias} [{league_key}]")
    
    return []

def _apply_intelligence_gate_to_news(news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply V10.0 3-level intelligence gate to news items.
    
    This function filters news items through the intelligence gate:
    - Level 1: Zero-cost keyword check (local)
    - Level 2: AI translation and classification (if Level 1 passes)
    
    News items that fail Level 1 are discarded immediately (no API cost).
    News items that fail Level 2 are discarded after AI analysis.
    
    Args:
        news_items: List of news items to filter
        
    Returns:
        List of news items that passed the gate (with gate metadata added)
    """
    if not _INTELLIGENCE_GATE_AVAILABLE:
        # Gate not available - return all items unchanged
        return news_items
    
    if not news_items:
        return []
    
    filtered_news = []
    level_1_discarded = 0
    level_2_discarded = 0
    level_2_processed = 0
    
    for item in news_items:
        try:
            # Combine title and snippet for gate analysis
            text_to_analyze = ""
            if item.get('title'):
                text_to_analyze += item['title'] + " "
            if item.get('snippet'):
                text_to_analyze += item['snippet']
            
            if not text_to_analyze or len(text_to_analyze.strip()) < 5:
                # Skip items with insufficient text
                continue
            
            # Level 1: Zero-cost keyword check
            passes_level_1, triggered_keyword = level_1_keyword_check(text_to_analyze)
            
            if not passes_level_1:
                # Discard immediately - no API cost
                level_1_discarded += 1
                logging.debug(f"🚪 [INTEL-GATE-L1] DISCARDED - No native keywords in: {item.get('title', '')[:50]}...")
                continue
            
            # Level 1 passed - add gate metadata
            item['gate_level_1_passed'] = True
            item['gate_level_1_keyword'] = triggered_keyword
            
            # For now, we'll skip Level 2 for news items (too expensive)
            # NewsHunter already has relevance filtering via keywords and sources
            # Level 2 is more critical for Twitter intel (shorter text)
            # We'll mark Level 2 as passed by default for news items
            item['gate_level_2_passed'] = True
            item['gate_level_2_translation'] = None
            item['gate_level_2_relevant'] = True
            
            filtered_news.append(item)
            level_2_processed += 1
            
        except Exception as e:
            logging.warning(f"Intelligence gate error for item: {e}")
            # Include item even if gate failed (better to have false positives)
            filtered_news.append(item)
    
    # Log gate statistics
    if level_1_discarded > 0 or level_2_discarded > 0:
        logging.info(
            f"🚪 [INTEL-GATE] Filtered {level_1_discarded} items at Level 1, "
            f"{level_2_discarded} items at Level 2, "
            f"kept {len(filtered_news)} items"
        )
    else:
        logging.debug(f"🚪 [INTEL-GATE] All {len(filtered_news)} items passed gate")
    
    return filtered_news


def run_hunter_for_match(match: MatchModel, include_insiders: bool = True) -> List[Dict[str, Any]]:
    """
    Run full news hunt for a match: local news + Twitter + Insiders.
    
    Search Strategy (LAYERED - each layer ADDS to results):
    1. TIER 0: Browser Monitor (active web monitoring with AI analysis)
    2. TIER 0: A-League Scraper (for Australian league only)
    3. TIER 0.5: Beat Writer Priority Search
    4. TIER 1: Hyper-local site-dorked news (ole.com.ar, fanatik.com.tr, etc.)
    5. TIER 1: Twitter/X hack for real-time rumors
    6. TIER 2: INSIDER INTEL - Placeholder for future sources (Telegram private, etc.)
    7. Fallback: Generic search if nothing found
    
    V8.0: Reddit monitoring removed - provided no betting edge.
    V6.1 FIX: Added null check for match parameter.
    
    Args:
        match: Match model with league and team info
        include_insiders: Whether to scan insider sources (placeholder for future)
        
    Returns:
        Combined list of news items for Gemini analysis
    """
    # V6.1: Null check for match parameter
    if match is None:
        logging.error("run_hunter_for_match called with None match")
        return []
    
    # Validate match has required attributes
    if not hasattr(match, 'league') or not match.league:
        logging.error("Match object missing 'league' attribute")
        return []
    
    if not hasattr(match, 'home_team') or not hasattr(match, 'away_team'):
        logging.error("Match object missing team attributes")
        return []
    
    db = SessionLocal()
    try:
        # match.league contains the sport_key (e.g., 'soccer_argentina_primera_division')
        sport_key = match.league
        
        # Get language from country mapping
        country = get_country_from_league(sport_key)
        COUNTRY_TO_LANG: Dict[str, str] = {
            # Elite 7
            'turkey': 'tr', 'argentina': 'es', 'mexico': 'es', 
            'greece': 'el', 'scotland': 'en', 'australia': 'en',
            'poland': 'pl',
            # Tier 2
            'norway': 'no', 'france': 'fr', 'belgium': 'nl',
            'austria': 'de', 'netherlands': 'nl',
            'china': 'zh', 'japan': 'ja', 'brazil_b': 'pt',
            # Other
            'egypt': 'ar'
        }
        lang = COUNTRY_TO_LANG.get(country, 'en')
        
        # Get Aliases with safe attribute access
        try:
            home_alias = db.query(TeamAlias).filter(TeamAlias.api_name == match.home_team).first()
            away_alias = db.query(TeamAlias).filter(TeamAlias.api_name == match.away_team).first()
            
            home_search_name = home_alias.search_name if home_alias and hasattr(home_alias, 'search_name') else match.home_team
            away_search_name = away_alias.search_name if away_alias and hasattr(away_alias, 'search_name') else match.away_team
        except Exception as e:
            logging.warning(f"Failed to load team aliases: {e}")
            home_search_name = match.home_team
            away_search_name = match.away_team
        
        all_news: List[Dict[str, Any]] = []
        
        # ============================================
        # TIER 0: Browser Monitor (HIGHEST PRIORITY)
        # ============================================
        browser_monitor_count = 0
        if _BROWSER_MONITOR_AVAILABLE:
            logging.info(f"🌐 Browser Monitor (TIER 0) for {sport_key}...")
            
            try:
                browser_monitor_news = get_browser_monitor_news(
                    match_id=match.id,
                    team_names=[home_search_name, away_search_name],
                    league_key=sport_key
                )
                all_news.extend(browser_monitor_news)
                browser_monitor_count = len(browser_monitor_news)
                
                if browser_monitor_count > 0:
                    logging.info(f"   🌐 Browser Monitor added {browser_monitor_count} HIGH confidence discoveries")
            except Exception as e:
                logging.warning(f"Browser Monitor error: {e}")
        
        # ============================================
        # TIER 0: A-League Dedicated Scraper (GOLDEN SOURCE)
        # ============================================
        aleague_count = 0
        if _ALEAGUE_SCRAPER_AVAILABLE and sport_key == "soccer_australia_aleague":
            logging.info(f"🦘 A-League scraper (TIER 0) for {sport_key}...")
            
            try:
                scraper = get_aleague_scraper()
                if scraper.is_available():
                    home_aleague_news = scraper.search_team_news(home_search_name, match.id)
                    all_news.extend(home_aleague_news)
                    
                    away_aleague_news = scraper.search_team_news(away_search_name, match.id)
                    all_news.extend(away_aleague_news)
                    
                    aleague_count = len(home_aleague_news) + len(away_aleague_news)
                    if aleague_count > 0:
                        logging.info(f"   🦘 A-League scraper added {aleague_count} VERY_HIGH confidence articles")
                else:
                    logging.debug("A-League scraper: aleagues.com.au not reachable")
            except Exception as e:
                logging.warning(f"A-League scraper error: {e}")
        
        # ============================================
        # TIER 0.5: BEAT WRITER PRIORITY SEARCH
        # ============================================
        beat_writer_count = 0
        logging.info(f"⭐ Beat Writer Priority search for {sport_key}...")
        
        try:
            home_bw_news = search_beat_writers_priority(home_search_name, sport_key, match.id)
            all_news.extend(home_bw_news)
            
            away_bw_news = search_beat_writers_priority(away_search_name, sport_key, match.id)
            all_news.extend(away_bw_news)
            
            beat_writer_count = len(home_bw_news) + len(away_bw_news)
            if beat_writer_count > 0:
                logging.info(f"   ⭐ Beat Writers added {beat_writer_count} HIGH confidence results")
        except Exception as e:
            logging.warning(f"Beat writer search error: {e}")
        
        # ============================================
        # TIER 1: Local News + Twitter (via search_news)
        # ============================================
        try:
            logging.info(f"🔍 Hunting news for Home: {home_search_name} [{sport_key}]")
            home_news = search_news(home_search_name, lang, match.id, league_key=sport_key)
            all_news.extend(home_news)
            
            logging.info(f"🔍 Hunting news for Away: {away_search_name} [{sport_key}]")
            away_news = search_news(away_search_name, lang, match.id, league_key=sport_key)
            all_news.extend(away_news)
        except Exception as e:
            logging.error(f"News search error: {e}")
        
        # ============================================
        # TIER 2: INSIDER INTEL (Placeholder)
        # ============================================
        if include_insiders:
            try:
                home_insider_news = search_insiders(home_search_name, sport_key, match.id)
                away_insider_news = search_insiders(away_search_name, sport_key, match.id)
                
                insider_count = len(home_insider_news) + len(away_insider_news)
                if insider_count > 0:
                    all_news.extend(home_insider_news)
                    all_news.extend(away_insider_news)
                    logging.info(f"   🕵️ Insider layer added {insider_count} results")
            except Exception as e:
                logging.debug(f"Insider search error: {e}")
        
        # ============================================
        # DEEP DIVE ON DEMAND (V8.1)
        # ============================================
        # Upgrade shallow search results to full article content
        # for high-value keywords (injury, squad, transfer, etc.)
        if DEEP_DIVE_ENABLED and _ARTICLE_READER_AVAILABLE and all_news:
            try:
                logging.info(f"🔍 [DEEP-DIVE] Processing {len(all_news)} search results...")
                
                all_news = apply_deep_dive_to_results(
                    results=all_news,
                    triggers=DEEP_DIVE_TRIGGERS,
                    max_articles=DEEP_DIVE_MAX_ARTICLES,
                    timeout=DEEP_DIVE_TIMEOUT
                )
                
                deep_dive_count = len([n for n in all_news if n.get('deep_dive') == True])
                if deep_dive_count > 0:
                    logging.info(f"   ✅ [DEEP-DIVE] Upgraded {deep_dive_count} articles to full content")
                    
            except Exception as e:
                logging.warning(f"Deep dive processing failed: {e}")
        
        # ============================================
        # V10.0: INTELLIGENCE GATE FILTERING
        # ============================================
        # Apply 3-level intelligence gate to filter out non-relevant content
        # This reduces AI costs by ~95% by discarding irrelevant items at local level
        if all_news:
            original_count = len(all_news)
            all_news = _apply_intelligence_gate_to_news(all_news)
            filtered_count = len(all_news)
            
            if original_count > filtered_count:
                logging.info(
                    f"🚪 [INTEL-GATE] Filtered {original_count - filtered_count}/{original_count} items "
                    f"({((original_count - filtered_count) / original_count * 100):.1f}% reduction)"
                )
        
        # ============================================
        # SUMMARY
        # ============================================
        tier1_search_types = [
            'local_site_dork', 'ddg_local', 'generic', 'dynamic_country',
            'twitter_intel_cache',
            'exotic_aleagues_official', 'exotic_keepup', 'exotic_foxsports_au',
            'exotic_twitter_proxy', 'exotic_dongqiudi', 'exotic_nikkansports',
            'exotic_official_releases', 'exotic_lance_ticker', 'exotic_globo_esporte',
        ]
        tier1_count = len([n for n in all_news if n.get('search_type') in tier1_search_types])
        beat_writer_total = len([n for n in all_news if n.get('search_type') in ('beat_writer_cache', 'beat_writer_priority', 'insider_beat_writer')])
        aleague_total = len([n for n in all_news if n.get('search_type') == 'aleague_scraper'])
        browser_monitor_total = len([n for n in all_news if n.get('search_type') == 'browser_monitor'])
        
        logging.info(f"📰 News Hunter total: {browser_monitor_total} BrowserMonitor + {aleague_total} A-League + {beat_writer_total} BeatWriters + {tier1_count} Tier1")
        
        # ============================================
        # NEWS DECAY: Apply freshness multiplier
        # ============================================
        if _NEWS_DECAY_AVAILABLE and all_news:
            _apply_news_decay(all_news, match, sport_key)
        
        return all_news
        
    finally:
        db.close()


def _apply_news_decay(all_news: List[Dict[str, Any]], match: MatchModel, sport_key: str) -> None:
    """
    Apply news decay multipliers to all news items.
    
    Args:
        all_news: List of news items to process
        match: Match model for kickoff time calculation
        sport_key: League key for decay rates
    """
    fresh_count = 0
    stale_count = 0
    
    try:
        from src.analysis.market_intelligence import apply_news_decay_v2
        _V2_AVAILABLE = True
    except ImportError:
        _V2_AVAILABLE = False
    
    # Calculate minutes_to_kickoff
    minutes_to_kickoff: Optional[int] = None
    if hasattr(match, 'start_time') and match.start_time:
        try:
            now = datetime.now(timezone.utc)
            match_start = match.start_time
            if match_start.tzinfo is None:
                match_start = match_start.replace(tzinfo=timezone.utc)
            
            delta_seconds = (match_start - now).total_seconds()
            minutes_to_kickoff = int(delta_seconds / 60) if delta_seconds > 0 else 0
        except Exception as e:
            logging.debug(f"Could not calculate minutes_to_kickoff: {e}")
    
    for item in all_news:
        news_date = safe_dict_get(item, 'date', default=None)
        source_type = safe_dict_get(item, 'source_type', default='') or safe_dict_get(item, 'search_type', default='mainstream')
        
        try:
            multiplier, minutes_old = calculate_news_freshness_multiplier(
                news_date, 
                league_key=sport_key
            )
            
            if _V2_AVAILABLE and minutes_old > 0:
                _, freshness_tag = apply_news_decay_v2(
                    impact_score=1.0,
                    minutes_since_publish=minutes_old,
                    league_key=sport_key,
                    source_type=source_type,
                    minutes_to_kickoff=minutes_to_kickoff
                )
                item['freshness_tag'] = freshness_tag
            else:
                item['freshness_tag'] = get_freshness_tag(minutes_old)
            
            item['freshness_multiplier'] = round(multiplier, 2)
            item['minutes_old'] = minutes_old
            
            if item['freshness_tag'] == '🔥 FRESH':
                fresh_count += 1
            elif item['freshness_tag'] == '📜 STALE':
                stale_count += 1
        except Exception as e:
            logging.debug(f"News decay calculation failed for item: {e}")
            item['freshness_tag'] = '⏰ AGING'
            item['freshness_multiplier'] = 0.5
            item['minutes_old'] = -1
    
    if fresh_count > 0 or stale_count > 0:
        kickoff_info = f", kickoff in {minutes_to_kickoff}min" if minutes_to_kickoff is not None else ""
        logging.info(f"   ⏱️ News Decay: {fresh_count} fresh, {stale_count} stale{kickoff_info}")
