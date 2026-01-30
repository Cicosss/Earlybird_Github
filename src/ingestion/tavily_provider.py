"""
Tavily AI Search Provider - V7.3

AI-optimized search API with key rotation and caching.
Provides structured results with AI-generated answers.

Features:
- 7 API keys rotation (1000 calls each = 7000/month)
- Rate limiting (1 req/sec)
- Response caching (30 min TTL)
- V7.3: Cross-component cache deduplication via SharedContentCache
- Automatic fallback on exhaustion
- Circuit breaker for consecutive failures
- Brave/DDG fallback when Tavily unavailable

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 10.1, 10.2, 10.3, 10.4

Phase 1 Critical Fix: Added URL encoding for non-ASCII characters in search queries
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

from config.settings import (
    TAVILY_ENABLED,
    TAVILY_RATE_LIMIT_SECONDS,
    TAVILY_CACHE_TTL_SECONDS,
    BRAVE_API_KEY,
)
from src.ingestion.tavily_key_rotator import TavilyKeyRotator, get_tavily_key_rotator
from src.utils.http_client import get_http_client

# V7.3: Import SharedContentCache for cross-component deduplication
try:
    from src.utils.shared_cache import get_shared_cache
    _SHARED_CACHE_AVAILABLE = True
except ImportError:
    _SHARED_CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Tavily API endpoint
TAVILY_API_URL = "https://api.tavily.com/search"

# Circuit breaker settings
CIRCUIT_BREAKER_THRESHOLD = 3  # Open after 3 consecutive failures
CIRCUIT_BREAKER_RECOVERY_SECONDS = 60  # Try recovery every 60 seconds
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2  # Close after 2 consecutive successes


@dataclass
class TavilyResult:
    """Individual search result from Tavily."""
    title: str
    url: str
    content: str  # Snippet
    score: float  # Relevance score
    published_date: Optional[str] = None


@dataclass
class TavilyResponse:
    """Response from Tavily API."""
    query: str
    answer: Optional[str]  # AI-generated answer
    results: List[TavilyResult] = field(default_factory=list)
    response_time: float = 0.0


@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    response: TavilyResponse
    cached_at: datetime
    ttl_seconds: int = TAVILY_CACHE_TTL_SECONDS
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        elapsed = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds


@dataclass
class BudgetStatus:
    """Budget status for monitoring."""
    monthly_used: int
    monthly_limit: int
    daily_used: int
    daily_limit: int
    is_degraded: bool
    is_disabled: bool
    daily_reset_date: Optional[str] = None  # ISO format date of last daily reset


class CircuitBreakerState:
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Tavily failing, use fallback
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for Tavily API resilience.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Tavily failing, use fallback
    - HALF_OPEN: Testing recovery
    
    Thresholds:
    - Open after 3 consecutive failures
    - Recovery attempt every 60 seconds
    - Close after 2 consecutive successes
    
    Requirements: 10.1, 10.2, 10.3, 10.4
    """
    state: str = CircuitBreakerState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_recovery_attempt: Optional[float] = None
    
    def record_success(self) -> None:
        """Record a successful API call."""
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        
        # In HALF_OPEN state, close circuit after enough successes
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.consecutive_successes >= CIRCUIT_BREAKER_SUCCESS_THRESHOLD:
                logger.info("🔌 [CIRCUIT] Closing circuit - Tavily recovered")
                self.state = CircuitBreakerState.CLOSED
                self.consecutive_successes = 0
    
    def record_failure(self) -> None:
        """Record a failed API call."""
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        # Open circuit after threshold failures
        if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            if self.state != CircuitBreakerState.OPEN:
                logger.warning(
                    f"🔌 [CIRCUIT] Opening circuit after {self.consecutive_failures} failures"
                )
            self.state = CircuitBreakerState.OPEN
    
    def should_allow_request(self) -> bool:
        """
        Check if a request should be allowed.
        
        Returns:
            True if request should proceed, False if should use fallback
        """
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            # Check if we should attempt recovery
            now = time.time()
            if self.last_recovery_attempt is None:
                self.last_recovery_attempt = now
            
            elapsed = now - self.last_recovery_attempt
            if elapsed >= CIRCUIT_BREAKER_RECOVERY_SECONDS:
                logger.info("🔌 [CIRCUIT] Attempting recovery (half-open)")
                self.state = CircuitBreakerState.HALF_OPEN
                self.last_recovery_attempt = now
                self.consecutive_successes = 0
                return True
            
            return False
        
        # HALF_OPEN: allow request for testing
        return True
    
    def get_status(self) -> Dict:
        """Get circuit breaker status."""
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure_time": self.last_failure_time,
            "last_recovery_attempt": self.last_recovery_attempt,
        }


class TavilyProvider:
    """
    Tavily AI Search Provider with Key Rotation.
    
    Features:
    - 7 API keys rotation (1000 calls each)
    - Rate limiting (1 req/sec)
    - Response caching (30 min TTL)
    - Automatic fallback on exhaustion
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """
    
    def __init__(self, key_rotator: Optional[TavilyKeyRotator] = None):
        """
        Initialize TavilyProvider.
        
        Args:
            key_rotator: Optional key rotator (defaults to singleton)
            
        Requirements: 1.1
        """
        self._key_rotator = key_rotator or get_tavily_key_rotator()
        self._cache: Dict[str, CacheEntry] = {}
        self._last_request_time: float = 0.0
        self._http_client = get_http_client()
        self._fallback_active = False
        
        # V7.0: Circuit breaker for resilience
        self._circuit_breaker = CircuitBreaker()
        self._fallback_calls: int = 0
        
        # V7.3: Shared cache for cross-component deduplication
        self._shared_cache = get_shared_cache() if _SHARED_CACHE_AVAILABLE else None
        
        # V7.4: Daily tracking implementation
        self._daily_usage: int = 0
        self._daily_limit: int = 250  # ~7000 monthly / 28 days
        self._last_reset_date: Optional[str] = None
        
        if TAVILY_ENABLED and self._key_rotator.is_available():
            cache_status = "with shared cache" if self._shared_cache else "local cache only"
            logger.info(f"✅ Tavily AI Search initialized with circuit breaker ({cache_status})")
        else:
            logger.debug("Tavily AI Search not available (disabled or no keys)")
    
    def is_available(self) -> bool:
        """
        Check if Tavily is available and within budget.
        
        Returns:
            True if Tavily can be used
            
        Requirements: 1.5
        """
        if not TAVILY_ENABLED:
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
        
        Requirements: 1.2
        """
        now = time.time()
        elapsed = now - self._last_request_time
        
        if elapsed < TAVILY_RATE_LIMIT_SECONDS:
            sleep_time = TAVILY_RATE_LIMIT_SECONDS - elapsed
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _get_cache_key(
        self,
        query: str,
        search_depth: str,
        max_results: int,
        topic: Optional[str] = None,
        days: Optional[int] = None
    ) -> str:
        """Generate cache key from query parameters."""
        key_str = f"{query}|{search_depth}|{max_results}|{topic}|{days}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _check_cache(self, cache_key: str) -> Optional[TavilyResponse]:
        """
        Check cache for existing response.
        
        Args:
            cache_key: Cache key to look up
            
        Returns:
            Cached response if valid, None otherwise
            
        Requirements: 1.3
        """
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired():
                logger.debug(f"📦 [TAVILY] Cache hit for key {cache_key[:8]}...")
                return entry.response
            else:
                # Clean up expired entry
                del self._cache[cache_key]
        
        return None
    
    def _update_cache(self, cache_key: str, response: TavilyResponse) -> None:
        """
        Update cache with new response.
        
        Args:
            cache_key: Cache key
            response: Response to cache
            
        Requirements: 1.3
        """
        self._cache[cache_key] = CacheEntry(
            response=response,
            cached_at=datetime.now(timezone.utc)
        )
        
        # Cleanup old entries (keep cache size reasonable)
        if len(self._cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self) -> None:
        """Remove expired cache entries."""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
        topic: Optional[str] = None,
        days: Optional[int] = None
    ) -> Optional[TavilyResponse]:
        """
        Execute search with caching and rate limiting.
        
        V7.3: Added cross-component deduplication via SharedContentCache.
        
        Args:
            query: Search query
            search_depth: "basic" or "advanced"
            max_results: Maximum number of results
            include_answer: Include AI-generated answer
            include_raw_content: Include full page content
            topic: Search topic - "general" or "news" (native Tavily parameter)
            days: Limit results to last N days (native Tavily parameter, only for topic="news")
            
        Returns:
            TavilyResponse or None on failure
            
        Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 10.1, 10.2, 10.3
        """
        # Generate cache key for this query
        cache_key = self._get_cache_key(query, search_depth, max_results, topic, days)
        
        # V7.3: Check shared cache first (cross-component deduplication)
        if self._shared_cache:
            # Use cache_key as content identifier for deduplication
            if self._shared_cache.is_duplicate(content=cache_key, source="tavily"):
                # Check local cache for actual response
                cached = self._check_cache(cache_key)
                if cached:
                    logger.debug(f"📦 [TAVILY] Shared cache HIT: {query[:50]}...")
                    return cached
        
        # Check local cache (backward compatibility)
        cached = self._check_cache(cache_key)
        if cached:
            return cached
        
        # Check circuit breaker
        if not self._circuit_breaker.should_allow_request():
            logger.debug("🔌 [CIRCUIT] Open - using fallback")
            return self._fallback_search(query, max_results)
        
        if not self.is_available():
            logger.debug("Tavily not available, trying fallback")
            return self._fallback_search(query, max_results)
        
        # Get current API key
        api_key = self._key_rotator.get_current_key()
        if not api_key:
            logger.warning("⚠️ No Tavily API key available")
            self._fallback_active = True
            return self._fallback_search(query, max_results)
        
        # Apply rate limiting
        self._apply_rate_limit()
        
        logger.info(f"🔍 [TAVILY] Searching: {query[:60]}...")
        
        start_time = time.time()
        
        try:
            # Phase 1 Critical Fix: URL-encode query to handle special characters
            # This fixes search failures for non-English team names
            encoded_query = quote(query, safe=' ')
            
            # Build request payload
            payload = {
                "api_key": api_key,
                "query": encoded_query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
            }
            
            # Add native topic/days parameters if specified
            if topic:
                payload["topic"] = topic
            if days is not None and topic == "news":
                payload["days"] = days
            
            response = self._http_client.post_sync(
                TAVILY_API_URL,
                rate_limit_key="tavily",
                json=payload,
                timeout=30,
                max_retries=1
            )
            
            response_time = time.time() - start_time
            
            # Handle 429 or 432 - quota exceeded
            # 429 = standard rate limit, 432 = Tavily-specific monthly quota exceeded
            if response.status_code in (429, 432):
                logger.warning(f"⚠️ [TAVILY] Key exhausted (HTTP {response.status_code}), rotating...")
                self._key_rotator.mark_exhausted()
                self._circuit_breaker.record_failure()
                
                if self._key_rotator.rotate_to_next():
                    # Retry with new key
                    return self.search(
                        query, search_depth, max_results,
                        include_answer, include_raw_content,
                        topic, days
                    )
                else:
                    # All keys exhausted
                    self._fallback_active = True
                    logger.warning("⚠️ [TAVILY] All keys exhausted, switching to fallback")
                    return self._fallback_search(query, max_results)
            
            # Handle other errors
            if response.status_code != 200:
                logger.error(f"❌ [TAVILY] Error: HTTP {response.status_code}")
                self._circuit_breaker.record_failure()
                return self._fallback_search(query, max_results)
            
            # Record successful call
            self._key_rotator.record_call()
            self._circuit_breaker.record_success()
            
            # Record daily usage
            self._check_and_reset_daily_usage()
            self._daily_usage += 1
            
            # Parse response
            data = response.json()
            
            results = []
            for item in data.get("results", []):
                results.append(TavilyResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                    published_date=item.get("published_date")
                ))
            
            tavily_response = TavilyResponse(
                query=query,
                answer=data.get("answer"),
                results=results,
                response_time=response_time
            )
            
            # Cache the response (local cache)
            self._update_cache(cache_key, tavily_response)
            
            # V7.3: Mark in shared cache for cross-component deduplication
            if self._shared_cache:
                self._shared_cache.mark_seen(content=cache_key, source="tavily")
                logger.debug(f"📦 [TAVILY] Marked in shared cache: {query[:50]}...")
            
            logger.info(f"🔍 [TAVILY] Found {len(results)} results in {response_time:.2f}s")
            return tavily_response
            
        except Exception as e:
            logger.error(f"❌ [TAVILY] Error: {e}")
            self._circuit_breaker.record_failure()
            return self._fallback_search(query, max_results)
    
    def _fallback_search(
        self,
        query: str,
        max_results: int = 5
    ) -> Optional[TavilyResponse]:
        """
        V7.0: Fallback search using Brave or DuckDuckGo.
        
        Called when Tavily is unavailable or circuit breaker is open.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            TavilyResponse with fallback results, or None
            
        Requirements: 10.2, 10.4
        """
        self._fallback_calls += 1
        
        # Try Brave first (if API key available)
        if BRAVE_API_KEY:
            result = self._fallback_to_brave(query, max_results)
            if result:
                return result
        
        # Fall back to DuckDuckGo
        result = self._fallback_to_ddg(query, max_results)
        if result:
            return result
        
        logger.warning("⚠️ [FALLBACK] All search providers failed")
        return None
    
    def _fallback_to_brave(
        self,
        query: str,
        max_results: int = 5
    ) -> Optional[TavilyResponse]:
        """
        V7.0: Fallback to Brave Search API.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            TavilyResponse with Brave results, or None
            
        Requirements: 10.2
        """
        if not BRAVE_API_KEY:
            return None
        
        logger.info(f"🔍 [BRAVE FALLBACK] Searching: {query[:60]}...")
        
        try:
            start_time = time.time()
            
            response = self._http_client.get_sync(
                "https://api.search.brave.com/res/v1/web/search",
                rate_limit_key="brave",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                params={
                    "q": query,
                    "count": max_results,
                },
                timeout=15,
                max_retries=1
            )
            
            response_time = time.time() - start_time
            
            if response.status_code != 200:
                logger.warning(f"⚠️ [BRAVE] Error: HTTP {response.status_code}")
                return None
            
            data = response.json()
            web_results = data.get("web", {}).get("results", [])
            
            results = []
            for item in web_results[:max_results]:
                results.append(TavilyResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("description", ""),
                    score=0.5,  # Default score for fallback
                    published_date=item.get("age")
                ))
            
            logger.info(f"🔍 [BRAVE FALLBACK] Found {len(results)} results in {response_time:.2f}s")
            
            return TavilyResponse(
                query=query,
                answer=None,  # Brave doesn't provide AI answers
                results=results,
                response_time=response_time
            )
            
        except Exception as e:
            logger.error(f"❌ [BRAVE FALLBACK] Error: {e}")
            return None
    
    def _fallback_to_ddg(
        self,
        query: str,
        max_results: int = 5
    ) -> Optional[TavilyResponse]:
        """
        V7.0: Fallback to DuckDuckGo search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            TavilyResponse with DDG results, or None
            
        Requirements: 10.2
        """
        logger.info(f"🔍 [DDG FALLBACK] Searching: {query[:60]}...")
        
        try:
            # Try both import paths for compatibility
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            
            start_time = time.time()
            
            with DDGS() as ddgs:
                ddg_results = list(ddgs.text(query, max_results=max_results))
            
            response_time = time.time() - start_time
            
            if not ddg_results:
                logger.warning("⚠️ [DDG] No results found")
                return None
            
            results = []
            for item in ddg_results[:max_results]:
                results.append(TavilyResult(
                    title=item.get("title", ""),
                    url=item.get("href", item.get("link", "")),
                    content=item.get("body", item.get("snippet", "")),
                    score=0.4,  # Lower score for DDG fallback
                    published_date=None
                ))
            
            logger.info(f"🔍 [DDG FALLBACK] Found {len(results)} results in {response_time:.2f}s")
            
            return TavilyResponse(
                query=query,
                answer=None,  # DDG doesn't provide AI answers
                results=results,
                response_time=response_time
            )
            
        except ImportError:
            logger.warning("⚠️ [DDG] duckduckgo_search/ddgs not installed")
            return None
        except Exception as e:
            logger.error(f"❌ [DDG FALLBACK] Error: {e}")
            return None
    
    def search_news(
        self,
        query: str,
        days: int = 7,
        max_results: int = 5
    ) -> List[Dict]:
        """
        Search specifically for news articles using native Tavily parameters.
        
        Uses topic="news" and days parameter for optimal filtering
        instead of query string manipulation.
        
        Args:
            query: Search query
            days: Limit to articles from last N days (native Tavily parameter)
            max_results: Maximum number of results
            
        Returns:
            List of dicts with title, url, snippet
        """
        # Use native Tavily news parameters instead of query manipulation
        response = self.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
            topic="news",
            days=days
        )
        
        if not response:
            return []
        
        # Convert to standard format
        return [
            {
                "title": r.title,
                "url": r.url,
                "link": r.url,
                "snippet": r.content,
                "summary": r.content,
                "score": r.score,
                "published_date": r.published_date,
                "source": "tavily"
            }
            for r in response.results
        ]
    
    def get_budget_status(self) -> BudgetStatus:
        """
        Get current budget usage statistics.
        
        Returns:
            BudgetStatus with usage information
        """
        status = self._key_rotator.get_status()
        total_usage = status["total_usage"]
        monthly_limit = 7000  # 7 keys × 1000 calls
        
        # Check and reset daily usage if needed
        self._check_and_reset_daily_usage()
        
        return BudgetStatus(
            monthly_used=total_usage,
            monthly_limit=monthly_limit,
            daily_used=self._daily_usage,
            daily_limit=self._daily_limit,
            is_degraded=total_usage >= monthly_limit * 0.90,
            is_disabled=total_usage >= monthly_limit * 0.95,
            daily_reset_date=self._last_reset_date
        )
    
    def reset_fallback(self) -> None:
        """Reset fallback mode (for recovery attempts)."""
        self._fallback_active = False
    
    def get_status(self) -> Dict:
        """Get provider status for monitoring."""
        key_status = self._key_rotator.get_status()
        budget = self.get_budget_status()
        
        return {
            "enabled": TAVILY_ENABLED,
            "available": self.is_available(),
            "fallback_active": self._fallback_active,
            "fallback_calls": self._fallback_calls,
            "cache_size": len(self._cache),
            "keys": key_status,
            "budget": {
                "monthly_used": budget.monthly_used,
                "monthly_limit": budget.monthly_limit,
                "daily_used": budget.daily_used,
                "daily_limit": budget.daily_limit,
                "daily_reset_date": budget.daily_reset_date,
                "is_degraded": budget.is_degraded,
                "is_disabled": budget.is_disabled,
            },
            "circuit_breaker": self._circuit_breaker.get_status(),
        }


# ============================================
# SINGLETON INSTANCE
# ============================================

_tavily_instance: Optional[TavilyProvider] = None
_tavily_lock = threading.Lock()


def get_tavily_provider() -> TavilyProvider:
    """
    Get or create the singleton TavilyProvider instance (thread-safe).
    
    Uses double-checked locking pattern for thread safety.
    """
    global _tavily_instance
    
    if _tavily_instance is None:
        with _tavily_lock:
            if _tavily_instance is None:
                _tavily_instance = TavilyProvider()
                logger.debug("🔍 [TAVILY] Global TavilyProvider instance initialized")
    
    return _tavily_instance
