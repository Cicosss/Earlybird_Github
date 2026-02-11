"""
EarlyBird Brave Search Provider - Primary Search Engine (V4.0)

Brave Search API provides high-quality, stable search results.

Specs:
- Endpoint: https://api.search.brave.com/res/v1/web/search
- Auth: X-Subscription-Token header (NOT Bearer token)
- Rate Limit: 1 request/2 seconds (enforced with 2.0s delay)
- Quota: 2000/month per key (3 keys = 6000/month baseline)

Priority in search chain: Brave -> DuckDuckGo -> Serper

V4.4: Migrated to centralized HTTP client with fingerprint rotation.
V4.0: Added API key rotation and budget management (duplicated from Tavily).

V4.5: Fixed double URL encoding bug that caused HTTP 422 errors with non-ASCII characters.
       HTTPX automatically encodes query parameters; manual encoding was causing double encoding.
"""
import html
import logging
from typing import List, Dict, Optional

from config.settings import BRAVE_API_KEY
from src.ingestion.brave_key_rotator import BraveKeyRotator, get_brave_key_rotator
from src.ingestion.brave_budget import BudgetManager, get_brave_budget_manager
from src.utils.http_client import get_http_client
from src.utils.validators import safe_get

logger = logging.getLogger(__name__)

# API endpoint
BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """
    Brave Search API Provider.
    
    High-quality search with strict rate limiting.
    V4.4: Uses centralized HTTP client.
    V4.0: Added API key rotation and budget management.
    """
    
    def __init__(self):
        # V4.0: Initialize key rotator and budget manager
        self._key_rotator = get_brave_key_rotator()
        self._budget_manager = get_brave_budget_manager()
        
        # Keep existing fields for backward compatibility
        self._api_key = BRAVE_API_KEY  # Fallback to single key
        self._rate_limited = False
        self._http_client = get_http_client()
        
        # V4.0: Feature flag for key rotation (default: True)
        self._key_rotation_enabled = True
        
        if self._key_rotator.is_available():
            logger.info("✅ Brave Search API V4.0 initialized with key rotation and budget management")
        elif self._api_key:
            logger.info("✅ Brave Search API initialized (single key mode)")
        else:
            logger.debug("Brave Search API key not configured")
    
    def is_available(self) -> bool:
        """Check if Brave Search is available and not rate limited."""
        if not self._api_key:
            return False
        
        if self._rate_limited:
            return False
        
        # V4.0: Check if key rotator has available keys
        if self._key_rotation_enabled and not self._key_rotator.is_available():
            return False
        
        return True
    
    def search_news(self, query: str, limit: int = 5, component: str = "unknown") -> List[Dict]:
        """
        Search using Brave Search API.

        Uses centralized HTTP client with rate limiting (1.1s).
        V4.0: Added key rotation and budget management.
        V4.5: Fixed double URL encoding bug - HTTPX automatically encodes query parameters.

        Args:
            query: Search query string (can contain non-ASCII characters like Turkish "ş", Polish "ą", Greek "α")
            limit: Maximum number of results (default 5)
            component: Component making the request (for budget tracking)

        Returns:
            List of dicts with title, url, snippet

        Raises:
            ValueError: If API key is not configured
        """
        if not self._api_key:
            raise ValueError("BRAVE_API_KEY not configured in environment")
        
        if self._rate_limited:
            logger.warning("⚠️ Brave Search temporarily rate limited")
            return []
        
        # V4.0: Check budget before making API call
        if self._key_rotation_enabled and not self._budget_manager.can_call(component):
            logger.warning(f"⚠️ [BRAVE-BUDGET] Call blocked for {component}: budget exhausted")
            return []
        
        logger.info(f"🔍 [BRAVE] Searching: {query[:60]}...")
        
        # V4.0: Get current API key from rotator
        api_key = self._key_rotator.get_current_key() if self._key_rotation_enabled else self._api_key
        
        if not api_key:
            logger.warning("⚠️ No Brave API key available - all keys exhausted")
            return []
        
        try:
            # HTTPX automatically URL-encodes the query parameter
            # Do NOT manually encode to avoid double encoding (causes HTTP 422)
            response = self._http_client.get_sync(
                BRAVE_API_URL,
                rate_limit_key="brave",
                use_fingerprint=False,  # API calls use API key auth
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json"
                },
                params={
                    "q": query,
                    "count": limit,
                    "freshness": "pw"  # Past Week - filters out stale news
                },
                timeout=15,
                max_retries=2
            )
            
            # Handle rate limiting (429)
            if response.status_code == 429:
                # V4.0: Mark key as exhausted and rotate to next
                if self._key_rotation_enabled:
                    logger.warning("⚠️ Brave Search rate limit (429) - rotating key")
                    self._key_rotator.mark_exhausted()
                    
                    # Check if rotation succeeded before retrying
                    if self._key_rotator.rotate_to_next():
                        # Retry with new key
                        return self.search_news(query, limit, component)
                    else:
                        # All keys exhausted - fall back to DDG
                        logger.warning("⚠️ All Brave keys exhausted - failing over to DDG")
                        return []
                else:
                    logger.warning("⚠️ Brave Search rate limit (429) - failing over to DDG")
                    self._rate_limited = True
                    return []
            
            # Handle other errors
            if response.status_code != 200:
                logger.error(f"❌ Brave Search error: HTTP {response.status_code}")
                return []
            
            # V4.0: Record successful call in budget manager
            if self._key_rotation_enabled:
                self._budget_manager.record_call(component)
                self._key_rotator.record_call()
            
            data = response.json()
            
            # Parse results from web.results
            web_results = safe_get(data, "web", "results", default=[])
            
            results = []
            for item in web_results[:limit]:
                raw_desc = item.get("description", "")
                clean_summary = html.unescape(raw_desc)[:350] if raw_desc else ""
                
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "link": item.get("url", ""),  # Alias for compatibility
                    "snippet": clean_summary,  # DDG/Serper compatibility
                    "summary": clean_summary,  # Analyzer compatibility
                    "source": "brave"
                })
            
            logger.info(f"🔍 [BRAVE] Found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"❌ Brave Search error: {e}")
            return []
    
    def reset_rate_limit(self):
        """Reset rate limit flag (call after some time has passed)."""
        self._rate_limited = False
    
    def get_status(self) -> Dict:
        """
        Get status of Brave provider for monitoring.
        
        V4.0: Returns key rotation and budget status.
        
        Returns:
            Dict with status information
        """
        return {
            "key_rotation_enabled": self._key_rotation_enabled,
            "rate_limited": self._rate_limited,
            "key_rotator": self._key_rotator.get_status() if self._key_rotation_enabled else None,
            "budget": self._budget_manager.get_status().__dict__ if self._key_rotation_enabled else None,
        }


# Singleton instance
_brave_instance: Optional[BraveSearchProvider] = None


def get_brave_provider() -> BraveSearchProvider:
    """Get or create the singleton BraveSearchProvider instance."""
    global _brave_instance
    if _brave_instance is None:
        _brave_instance = BraveSearchProvider()
    return _brave_instance


def reset_brave_provider() -> None:
    """
    Reset the singleton BraveSearchProvider instance for test isolation.
    
    This function is used by tests to ensure clean state between test runs.
    """
    global _brave_instance
    _brave_instance = None
