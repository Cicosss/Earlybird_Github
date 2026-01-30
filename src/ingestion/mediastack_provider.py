"""
EarlyBird Mediastack Provider - Enhanced V1.0 (Tavily-like Architecture)

Mediastack API provides FREE unlimited news search as last-resort fallback.
Enhanced with Tavily-like architecture: key rotation, budget tracking, circuit breaker, caching, deduplication.

Features:
- 4 API keys rotation (from different MediaStack accounts)
- Rate limiting (1 req/sec)
- Response caching (30 min TTL)
- Cross-component deduplication via SharedContentCache
- Circuit breaker for consecutive failures
- Budget tracking (monitoring only - free tier)
- HTTPS support (available on all plans)

Specs:
- Endpoint: https://api.mediastack.com/v1/news (or http)
- Auth: access_key query parameter
- Rate Limit: None (free tier is unlimited, but we enforce 1 req/sec for stability)
- Quota: Unlimited on free tier

API Keys (from user):
1. 757ba57e51058d48f40f949042506859
2. 18d7da435a3454f4bcd9e40e071818f5
3. 3c3c532dce3f64b9d22622d489cd1b01
4. 379aa9d1da33df5aeea2ad66df13b85d

Requirements: Standard library only (no new dependencies)
"""
import hashlib
import html
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from urllib.parse import quote

from config.settings import (
    MEDIASTACK_ENABLED,
    MEDIASTACK_API_URL,
    MEDIASTACK_USE_HTTPS,
    MEDIASTACK_API_KEYS,
    MEDIASTACK_RATE_LIMIT_SECONDS,
    MEDIASTACK_CACHE_TTL_SECONDS,
    MEDIASTACK_CIRCUIT_BREAKER_ENABLED,
    MEDIASTACK_CIRCUIT_BREAKER_THRESHOLD,
    MEDIASTACK_CIRCUIT_BREAKER_RECOVERY_SECONDS,
    MEDIASTACK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
)
from src.utils.http_client import get_http_client

# Import MediaStack management components
from src.ingestion.mediastack_key_rotator import MediaStackKeyRotator, get_mediastack_key_rotator
from src.ingestion.mediastack_budget import MediaStackBudget, get_mediastack_budget

# Import SharedContentCache for cross-component deduplication
try:
    from src.utils.shared_cache import get_shared_cache
    _SHARED_CACHE_AVAILABLE = True
except ImportError:
    _SHARED_CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Circuit breaker settings (can be overridden by config)
CIRCUIT_BREAKER_THRESHOLD = MEDIASTACK_CIRCUIT_BREAKER_THRESHOLD
CIRCUIT_BREAKER_RECOVERY_SECONDS = MEDIASTACK_CIRCUIT_BREAKER_RECOVERY_SECONDS
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = MEDIASTACK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD

# Sport-related keywords to filter results (Mediastack doesn't have category filtering on free tier)
SPORT_KEYWORDS = ["football", "soccer", "calcio", "fútbol", "futebol", "futbol", "injury", "lineup", "squad"]

# Exclusion terms for post-fetch filtering (aligned with search_provider.py SPORT_EXCLUSION_TERMS)
# These terms indicate wrong sport or women's football - filter out from results
EXCLUSION_KEYWORDS = [
    # Basketball
    "basket", "basketball", "euroleague", "nba", "pallacanestro", "baloncesto",
    "koszykówka", "basketbol",
    # American Football
    "nfl", "american football", "touchdown", "super bowl",
    # Women's Football (to avoid false positives on shared team names)
    "women", "woman", "ladies", "feminine", "femminile", "femenino",
    "kobiet", "kadın", "bayan", "wsl", "liga f",
    # Other sports
    "handball", "volleyball", "rugby", "futsal",
]


def _clean_query_for_mediastack(query: str) -> str:
    """
    Remove exclusion terms (-term syntax) from query.
    
    Mediastack API doesn't support negative search operators,
    so we strip them to avoid polluting the keyword search.
    
    Args:
        query: Original query with potential -term exclusions
        
    Returns:
        Cleaned query with only positive keywords
    """
    if not query:
        return ""
    
    cleaned = query
    
    # First pass: remove multi-word exclusions (e.g., "-liga f", "-american football")
    multi_word_exclusions = [kw for kw in EXCLUSION_KEYWORDS if ' ' in kw]
    for kw in multi_word_exclusions:
        # Match "-liga f" or "- liga f" 
        pattern = rf'\s*-\s*{re.escape(kw)}\b'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Second pass: remove single-word exclusions
    single_word_exclusions = [kw for kw in EXCLUSION_KEYWORDS if ' ' not in kw]
    for kw in single_word_exclusions:
        pattern = rf'\s*-\s*{re.escape(kw)}\b'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def _matches_exclusion(text: str) -> bool:
    """
    Check if text contains any exclusion keywords.
    
    Args:
        text: Text to check (title, description, etc.)
        
    Returns:
        True if text contains excluded terms, False otherwise
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    for keyword in EXCLUSION_KEYWORDS:
        # Use word boundary check for short keywords to avoid false positives
        # e.g., "women" shouldn't match "showmen"
        if len(keyword) <= 4:
            # Short keyword: require word boundary
            if re.search(rf'\b{re.escape(keyword)}\b', text_lower):
                return True
        else:
            # Longer keyword: simple contains is fine
            if keyword in text_lower:
                return True
    
    return False


@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    response: List[Dict]
    cached_at: datetime
    ttl_seconds: int = MEDIASTACK_CACHE_TTL_SECONDS
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        elapsed = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds


@dataclass
class CircuitBreakerState:
    """Circuit breaker state machine."""
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_recovery_attempt: Optional[float] = None


class CircuitBreaker:
    """
    Circuit breaker pattern for resilience.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Circuit open, block requests
    - HALF_OPEN: Recovery attempt
    """
    
    def __init__(self):
        self._state = CircuitBreakerState()
        self._lock = threading.Lock()
    
    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._state.consecutive_failures = 0
            self._state.consecutive_successes += 1
            
            # If in HALF_OPEN and enough successes, close circuit
            if self._state.state == "HALF_OPEN" and \
               self._state.consecutive_successes >= CIRCUIT_BREAKER_SUCCESS_THRESHOLD:
                self._state.state = "CLOSED"
                logger.info("🔄 Circuit breaker: CLOSED (recovery successful)")
    
    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._state.consecutive_failures += 1
            self._state.consecutive_successes = 0
            self._state.last_failure_time = time.time()
            
            # If threshold reached, open circuit
            if self._state.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                self._state.state = "OPEN"
                logger.warning(
                    f"⚠️ Circuit breaker: OPEN ({self._state.consecutive_failures} failures)"
                )
    
    def should_allow_request(self) -> bool:
        """
        Check if request should be allowed.
        
        Returns:
            True if request is allowed, False if circuit is open
        """
        if not MEDIASTACK_CIRCUIT_BREAKER_ENABLED:
            return True
        
        with self._lock:
            # If OPEN, check if recovery time has passed
            if self._state.state == "OPEN":
                if self._state.last_failure_time is None:
                    return False
                
                elapsed = time.time() - self._state.last_failure_time
                if elapsed >= CIRCUIT_BREAKER_RECOVERY_SECONDS:
                    self._state.state = "HALF_OPEN"
                    self._state.last_recovery_attempt = time.time()
                    self._state.consecutive_successes = 0
                    logger.info("🔄 Circuit breaker: HALF_OPEN (recovery attempt)")
                    return True
                return False
            
            # If HALF_OPEN, check if we should close
            elif self._state.state == "HALF_OPEN":
                return True
            
            # CLOSED - allow request
            return True
    
    def get_state(self) -> Dict:
        """Get current circuit breaker state for monitoring."""
        with self._lock:
            return {
                "state": self._state.state,
                "consecutive_failures": self._state.consecutive_failures,
                "consecutive_successes": self._state.consecutive_successes,
                "last_failure_time": self._state.last_failure_time,
                "last_recovery_attempt": self._state.last_recovery_attempt,
            }


class MediastackProvider:
    """
    Mediastack News API Provider - Enhanced with Tavily-like architecture.
    
    Features:
    - 4 API keys rotation (from different accounts)
    - Rate limiting (1 req/sec)
    - Response caching (30 min TTL)
    - Cross-component deduplication via SharedContentCache
    - Circuit breaker for resilience
    - Budget tracking (monitoring only - free tier)
    - Query sanitization and post-fetch filtering (existing)
    - HTTPS support (available on all plans)
    
    V1.0: Enhanced with Tavily-like architecture components.
    """
    
    def __init__(
        self,
        key_rotator: Optional[MediaStackKeyRotator] = None,
        budget: Optional[MediaStackBudget] = None,
    ):
        """
        Initialize MediastackProvider.
        
        Args:
            key_rotator: Optional key rotator (defaults to singleton)
            budget: Optional budget manager (defaults to singleton)
        """
        self._key_rotator = key_rotator or get_mediastack_key_rotator()
        self._budget = budget or get_mediastack_budget()
        self._cache: Dict[str, CacheEntry] = {}
        self._last_request_time: float = 0.0
        self._http_client = get_http_client()
        self._circuit_breaker = CircuitBreaker()
        self._shared_cache = get_shared_cache() if _SHARED_CACHE_AVAILABLE else None
        self._fallback_active = False
        self._request_count = 0
        self._error_count = 0
        
        # V1.0: Daily tracking
        self._daily_usage: int = 0
        self._last_reset_date: Optional[str] = None
        
        if MEDIASTACK_ENABLED and self._key_rotator.is_available():
            cache_status = "with shared cache" if self._shared_cache else "local cache only"
            https_status = "HTTPS" if MEDIASTACK_USE_HTTPS else "HTTP"
            logger.info(
                f"✅ MediastackProvider V1.0 initialized with circuit breaker "
                f"({cache_status}, {https_status})"
            )
        else:
            logger.debug("MediastackProvider not available (disabled or no keys)")
    
    def is_available(self) -> bool:
        """
        Check if Mediastack is available and within budget.
        
        Returns:
            True if Mediastack can be used
        """
        if not MEDIASTACK_ENABLED:
            return False
        
        if self._fallback_active:
            return False
        
        return self._key_rotator.is_available()
    
    def _check_and_reset_daily_usage(self) -> None:
        """
        Check if we've crossed a day boundary and reset daily usage if needed.
        
        Uses UTC date to ensure consistency across timezones.
        """
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if self._last_reset_date is None:
            self._last_reset_date = current_date
        elif current_date != self._last_reset_date:
            logger.info(f"📅 Daily reset: {self._daily_usage} calls on {self._last_reset_date}")
            self._daily_usage = 0
            self._last_reset_date = current_date
    
    def _apply_rate_limit(self) -> None:
        """
        Apply rate limiting (1 request per second).
        """
        now = time.time()
        elapsed = now - self._last_request_time
        
        if elapsed < MEDIASTACK_RATE_LIMIT_SECONDS:
            sleep_time = MEDIASTACK_RATE_LIMIT_SECONDS - elapsed
            logger.debug(f"⏱️ Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_request_time = now
    
    def _is_duplicate(self, content: str) -> bool:
        """
        Check if content is duplicate using SharedContentCache.
        
        Args:
            content: Content to check for duplicates
            
        Returns:
            True if content is duplicate, False otherwise
        """
        if not self._shared_cache:
            return False
        
        # Generate cache key from content
        cache_key = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # Check if content is already seen
        return self._shared_cache.is_seen(content=cache_key, source="mediastack")
    
    def _mark_seen(self, content: str) -> None:
        """
        Mark content as seen in SharedContentCache.
        
        Args:
            content: Content to mark as seen
        """
        if not self._shared_cache:
            return
        
        # Generate cache key from content
        cache_key = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # Mark as seen
        self._shared_cache.mark_seen(content=cache_key, source="mediastack")
    
    def _get_cached_response(self, cache_key: str) -> Optional[List[Dict]]:
        """
        Get cached response if available and not expired.
        
        Args:
            cache_key: Cache key to look up
            
        Returns:
            Cached response or None if not found/expired
        """
        entry = self._cache.get(cache_key)
        if entry is None or entry.is_expired():
            return None
        
        logger.debug(f"💾 Cache hit for: {cache_key[:32]}...")
        return entry.response
    
    def _cache_response(self, cache_key: str, response: List[Dict]) -> None:
        """
        Cache a response with TTL.
        
        Args:
            cache_key: Cache key
            response: Response to cache
        """
        self._cache[cache_key] = CacheEntry(
            response=response,
            cached_at=datetime.now(timezone.utc),
        )
        
        # Clean old cache entries
        self._cleanup_cache()
    
    def _cleanup_cache(self) -> None:
        """
        Remove expired cache entries.
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"🧹 Cleaned up {len(expired_keys)} expired cache entries")
    
    def _generate_cache_key(self, query: str, limit: int, countries: str) -> str:
        """
        Generate a cache key for the request.
        
        Args:
            query: Search query
            limit: Result limit
            countries: Country codes
            
        Returns:
            Cache key string
        """
        key_parts = [query, str(limit), countries]
        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()
    
    def search_news(self, query: str, limit: int = 5, countries: str = "it,gb,us") -> List[Dict]:
        """
        Search news using Mediastack API with Tavily-like enhancements.
        
        Enhanced with:
        - Rate limiting (1 req/sec)
        - Circuit breaker pattern
        - Local caching (30 min TTL)
        - Cross-component deduplication
        - Key rotation
        - Budget tracking
        
        Args:
            query: Search query string (keywords)
            limit: Maximum number of results (default 5, max 100 on free tier)
            countries: Comma-separated country codes (default: it,gb,us)
            
        Returns:
            List of dicts with title, url, snippet, source
            
        Raises:
            ValueError: If API key is not configured
        """
        # Check availability
        if not self.is_available():
            logger.debug("MediastackProvider not available")
            return []
        
        # Apply rate limiting
        self._apply_rate_limit()
        
        # Check circuit breaker
        if not self._circuit_breaker.should_allow_request():
            logger.warning("⚠️ Circuit breaker OPEN - blocking request")
            return []
        
        # Guard: empty query
        if not query or len(query.strip()) < 2:
            logger.warning("⚠️ Mediastack: Empty or too short query skipped")
            return []
        
        # Check for duplicates
        if self._is_duplicate(query):
            logger.debug(f"🔄 Duplicate query detected: {query[:50]}...")
            return []
        
        # Generate cache key
        cache_key = self._generate_cache_key(query, limit, countries)
        
        # Check cache
        cached = self._get_cached_response(cache_key)
        if cached is not None:
            logger.info(f"💾 Cache hit for query: {query[:50]}...")
            return cached[:limit]
        
        # Check budget (always returns True for MediaStack free tier)
        if not self._budget.can_call("search_provider"):
            logger.warning("⚠️ Budget check failed (should not happen for MediaStack)")
            return []
        
        # Get current API key from rotator
        api_key = self._key_rotator.get_current_key()
        if not api_key:
            logger.warning("⚠️ No MediaStack API keys available")
            return []
        
        logger.info(f"🆘 [MEDIASTACK] Enhanced search: {query[:60]}...")
        
        # Clean query: remove -term exclusions (Mediastack doesn't support them)
        clean_query = _clean_query_for_mediastack(query)
        
        if not clean_query or len(clean_query.strip()) < 2:
            logger.warning("⚠️ Mediastack: Query empty after cleaning exclusions")
            return []
        
        logger.debug(f"🆘 [MEDIASTACK] Cleaned query: {clean_query[:60]}...")
        
        try:
            # Phase 1 Critical Fix: URL-encode query to handle special characters
            # This fixes search failures for non-English team names
            encoded_query = quote(clean_query, safe=' ')
            
            # Build API URL (HTTP or HTTPS based on config)
            api_url = MEDIASTACK_API_URL
            
            # Mediastack uses query params, not headers for auth
            response = self._http_client.get_sync(
                api_url,
                rate_limit_key="mediastack",  # Separate rate limit key
                use_fingerprint=False,  # API calls don't need fingerprinting
                params={
                    "access_key": api_key,
                    "keywords": encoded_query,  # Use URL-encoded cleaned query
                    "countries": countries,
                    "languages": "en,it,es,pt,de,fr",
                    "limit": min(limit * 2, 100),  # Request more to compensate for filtering
                    "sort": "published_desc",  # Most recent first
                },
                timeout=15,
                max_retries=2
            )
            
            self._request_count += 1
            
            # Handle errors
            if response.status_code != 200:
                self._error_count += 1
                logger.error(f"❌ Mediastack error: HTTP {response.status_code}")
                
                # Record circuit breaker failure
                self._circuit_breaker.record_failure()
                
                # Check for 429/432 - mark key exhausted and rotate
                if response.status_code in (429, 432):
                    self._key_rotator.mark_exhausted()
                    logger.warning("⚠️ MediaStack key exhausted, rotating...")
                    
                    # Retry with next key
                    return self.search_news(query, limit, countries)
                
                return []
            
            data = response.json()
            
            # Check for API errors in response
            if "error" in data:
                error_info = data.get("error", {})
                error_code = error_info.get("code", "unknown")
                error_msg = error_info.get("message", "Unknown error")
                logger.error(f"❌ Mediastack API error [{error_code}]: {error_msg}")
                self._error_count += 1
                
                # Record circuit breaker failure
                self._circuit_breaker.record_failure()
                
                return []
            
            # Parse results from data array
            news_items = data.get("data", [])
            
            if not news_items:
                logger.debug("Mediastack: No results found")
                return []
            
            results = []
            filtered_count = 0
            for item in news_items:
                # Extract and clean fields
                title = item.get("title", "")
                url = item.get("url", "")
                description = item.get("description", "")
                source_name = item.get("source", "")
                published_at = item.get("published_at", "")
                
                # Skip items without essential fields
                if not title or not url:
                    continue
                
                # Post-fetch filter: exclude wrong sports/women's football
                if _matches_exclusion(title) or _matches_exclusion(description):
                    filtered_count += 1
                    continue
                
                # Clean description (unescape HTML, limit length)
                clean_summary = ""
                if description:
                    clean_summary = html.unescape(description)[:350]
                
                results.append({
                    "title": title,
                    "url": url,
                    "link": url,  # Alias for compatibility
                    "snippet": clean_summary,
                    "summary": clean_summary,  # Alias for analyzer
                    "source": f"mediastack:{source_name}" if source_name else "mediastack",
                    "date": published_at,
                })
                
                # Stop once we have enough results
                if len(results) >= limit:
                    break
            
            if filtered_count > 0:
                logger.debug(f"🆘 [MEDIASTACK] Filtered out {filtered_count} wrong-sport results")
            
            # Cache the response
            self._cache_response(cache_key, results)
            
            # Mark query as seen
            self._mark_seen(query)
            
            # Record success
            self._circuit_breaker.record_success()
            self._key_rotator.record_call()
            self._budget.record_call("search_provider")
            
            logger.info(f"🆘 [MEDIASTACK] Found {len(results)} results (enhanced)")
            return results
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"❌ Mediastack error: {e}")
            
            # Record circuit breaker failure
            self._circuit_breaker.record_failure()
            
            return []
    
    def get_stats(self) -> Dict:
        """
        Get provider statistics for monitoring.
        
        Returns:
            Dict with provider statistics including all components
        """
        return {
            "enabled": MEDIASTACK_ENABLED,
            "available": self.is_available(),
            "fallback_active": self._fallback_active,
            "cache_size": len(self._cache),
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": (self._error_count / self._request_count * 100) if self._request_count > 0 else 0,
            "keys": self._key_rotator.get_status(),
            "budget": self._budget.get_status(),
            "circuit_breaker": self._circuit_breaker.get_state(),
        }


# Singleton instance
_mediastack_instance: Optional[MediastackProvider] = None


def get_mediastack_provider() -> MediastackProvider:
    """
    Get or create the singleton MediastackProvider instance.
    
    Returns:
        Singleton instance of MediastackProvider
    """
    global _mediastack_instance
    if _mediastack_instance is None:
        _mediastack_instance = MediastackProvider()
    return _mediastack_instance


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🆘 MEDIASTACK PROVIDER TEST (Enhanced V1.0)")
    print("=" * 60)
    
    provider = get_mediastack_provider()
    
    print(f"\n🔍 Available: {provider.is_available()}")
    
    if not provider.is_available():
        print("❌ MEDIASTACK not available (disabled or no keys)")
        exit(1)
    
    # Test search
    print("\n📰 Testing search...")
    results = provider.search_news("Serie A football injury", limit=3)
    
    print(f"   Found {len(results)} results")
    for r in results:
        print(f"   • {r.get('title', 'No title')[:60]}...")
        print(f"     Source: {r.get('source', 'unknown')}")
    
    # Stats
    stats = provider.get_stats()
    print(f"\n📊 Stats:")
    print(f"   Requests: {stats['request_count']}")
    print(f"   Errors: {stats['error_count']}")
    print(f"   Cache Size: {stats['cache_size']}")
    print(f"   Keys: {stats['keys']}")
    print(f"   Circuit Breaker: {stats['circuit_breaker']}")
    
    print("\n✅ Mediastack Provider test complete")
