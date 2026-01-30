"""
EarlyBird Brave Search Provider - Primary Search Engine (V3.6)

Brave Search API provides high-quality, stable search results.

Specs:
- Endpoint: https://api.search.brave.com/res/v1/web/search
- Auth: X-Subscription-Token header (NOT Bearer token)
- Rate Limit: 1 request/2 seconds (enforced with 2.0s delay)
- Quota: 2000/month

Priority in search chain: Brave -> DuckDuckGo -> Serper

V4.4: Migrated to centralized HTTP client with fingerprint rotation.

Phase 1 Critical Fix: Added URL encoding for non-ASCII characters in search queries
"""
import html
import logging
from typing import List, Dict, Optional
from urllib.parse import quote

from config.settings import BRAVE_API_KEY
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)

# API endpoint
BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """
    Brave Search API Provider.
    
    High-quality search with strict rate limiting.
    V4.4: Uses centralized HTTP client.
    """
    
    def __init__(self):
        self._api_key = BRAVE_API_KEY
        self._rate_limited = False
        self._http_client = get_http_client()
        
        if self._api_key:
            logger.info("✅ Brave Search API initialized")
        else:
            logger.debug("Brave Search API key not configured")
    
    def is_available(self) -> bool:
        """Check if Brave Search is available and not rate limited."""
        return bool(self._api_key) and not self._rate_limited
    
    def search_news(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search using Brave Search API.
        
        Uses centralized HTTP client with rate limiting (1.1s).
        
        Phase 1 Critical Fix: URL-encode query to handle non-ASCII characters
        (e.g., Turkish "ş", Polish "ą", Greek "α").
        
        Args:
            query: Search query string
            limit: Maximum number of results (default 5)
            
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
        
        logger.info(f"🔍 [BRAVE] Searching: {query[:60]}...")
        
        # Phase 1 Critical Fix: URL-encode query to handle special characters
        # This fixes search failures for non-English team names
        encoded_query = quote(query, safe=' ')
        
        try:
            response = self._http_client.get_sync(
                BRAVE_API_URL,
                rate_limit_key="brave",
                use_fingerprint=False,  # API calls use API key auth
                headers={
                    "X-Subscription-Token": self._api_key,
                    "Accept": "application/json"
                },
                params={
                    "q": encoded_query,
                    "count": limit,
                    "freshness": "pw"  # Past Week - filters out stale news
                },
                timeout=15,
                max_retries=2
            )
            
            # Handle rate limiting (429)
            if response.status_code == 429:
                logger.warning("⚠️ Brave Search rate limit (429) - failing over to DDG")
                self._rate_limited = True
                return []
            
            # Handle other errors
            if response.status_code != 200:
                logger.error(f"❌ Brave Search error: HTTP {response.status_code}")
                return []
            
            data = response.json()
            
            # Parse results from web.results
            web_results = data.get("web", {}).get("results", [])
            
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


# Singleton instance
_brave_instance: Optional[BraveSearchProvider] = None


def get_brave_provider() -> BraveSearchProvider:
    """Get or create the singleton BraveSearchProvider instance."""
    global _brave_instance
    if _brave_instance is None:
        _brave_instance = BraveSearchProvider()
    return _brave_instance
