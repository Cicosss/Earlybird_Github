"""
EarlyBird Mediastack Provider - Emergency Fallback Search Engine (V4.5)

Mediastack API provides FREE unlimited news search as last-resort fallback.
Used when Brave, DDG, and Serper all fail or are rate-limited.

Specs:
- Endpoint: http://api.mediastack.com/v1/news
- Auth: access_key query parameter
- Rate Limit: None (free tier is unlimited)
- Quota: Unlimited on free tier
- Limitation: Free tier uses HTTP only (no HTTPS)

Priority in search chain: Brave -> DDG -> Serper -> Mediastack (emergency)

Note: Mediastack free tier has lower quality results than paid alternatives,
but provides a safety net when all other sources fail.

V4.5: Added query sanitization and post-fetch filtering for sport exclusions.
      Mediastack API doesn't support -term syntax, so we clean the query
      and filter results after fetching.
"""
import html
import logging
import re
from typing import List, Dict, Optional

from config.settings import MEDIASTACK_API_KEY
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)

# API endpoint (free tier uses HTTP, not HTTPS)
MEDIASTACK_API_URL = "http://api.mediastack.com/v1/news"

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


class MediastackProvider:
    """
    Mediastack News API Provider - Emergency fallback.
    
    Free tier with unlimited requests, used as last resort
    when Brave, DDG, and Serper all fail.
    
    V4.5: Added query sanitization and post-fetch filtering.
          Mediastack doesn't support -term syntax, so we:
          1. Clean query before sending (remove -term patterns)
          2. Filter results after fetch (exclude wrong sports)
    """
    
    def __init__(self):
        self._api_key = MEDIASTACK_API_KEY
        self._http_client = get_http_client()
        self._request_count = 0
        self._error_count = 0
        
        if self._api_key:
            logger.info("✅ Mediastack API initialized (emergency fallback)")
        else:
            logger.debug("Mediastack API key not configured")
    
    def is_available(self) -> bool:
        """Check if Mediastack is available (has API key configured)."""
        return bool(self._api_key) and self._api_key not in ("", "YOUR_MEDIASTACK_API_KEY")
    
    def search_news(self, query: str, limit: int = 5, countries: str = "it,gb,us") -> List[Dict]:
        """
        Search news using Mediastack API.
        
        Uses centralized HTTP client. No rate limiting needed (unlimited free tier).
        
        Args:
            query: Search query string (keywords)
            limit: Maximum number of results (default 5, max 100 on free tier)
            countries: Comma-separated country codes (default: it,gb,us)
            
        Returns:
            List of dicts with title, url, snippet, source
            
        Raises:
            ValueError: If API key is not configured
        """
        if not self._api_key:
            raise ValueError("MEDIASTACK_API_KEY not configured in environment")
        
        # Guard: empty query
        if not query or len(query.strip()) < 2:
            logger.warning("⚠️ Mediastack: Empty or too short query skipped")
            return []
        
        logger.info(f"🆘 [MEDIASTACK] Emergency search: {query[:60]}...")
        
        # Clean query: remove -term exclusions (Mediastack doesn't support them)
        clean_query = _clean_query_for_mediastack(query)
        
        if not clean_query or len(clean_query.strip()) < 2:
            logger.warning("⚠️ Mediastack: Query empty after cleaning exclusions")
            return []
        
        logger.debug(f"🆘 [MEDIASTACK] Cleaned query: {clean_query[:60]}...")
        
        try:
            # Mediastack uses query params, not headers for auth
            response = self._http_client.get_sync(
                MEDIASTACK_API_URL,
                rate_limit_key="default",  # No special rate limiting needed
                use_fingerprint=False,  # API calls don't need fingerprinting
                params={
                    "access_key": self._api_key,
                    "keywords": clean_query,  # Use cleaned query
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
                return []
            
            data = response.json()
            
            # Check for API errors in response
            if "error" in data:
                error_info = data.get("error", {})
                error_code = error_info.get("code", "unknown")
                error_msg = error_info.get("message", "Unknown error")
                logger.error(f"❌ Mediastack API error [{error_code}]: {error_msg}")
                self._error_count += 1
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
            
            logger.info(f"🆘 [MEDIASTACK] Found {len(results)} results (emergency fallback)")
            return results
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"❌ Mediastack error: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Get provider statistics for monitoring."""
        return {
            "available": self.is_available(),
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": (self._error_count / self._request_count * 100) if self._request_count > 0 else 0,
        }


# Singleton instance
_mediastack_instance: Optional[MediastackProvider] = None


def get_mediastack_provider() -> MediastackProvider:
    """Get or create the singleton MediastackProvider instance."""
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
    print("🆘 MEDIASTACK PROVIDER TEST")
    print("=" * 60)
    
    provider = get_mediastack_provider()
    
    print(f"\n🔍 Available: {provider.is_available()}")
    
    if not provider.is_available():
        print("❌ MEDIASTACK_API_KEY not configured")
        print("   Get free key at: https://mediastack.com/signup/free")
        exit(1)
    
    # Test search
    print("\n📰 Testing search...")
    results = provider.search_news("Serie A football injury", limit=3)
    
    print(f"   Found {len(results)} results")
    for r in results:
        print(f"   • {r.get('title', 'No title')[:60]}...")
        print(f"     Source: {r.get('source', 'unknown')}")
    
    # Stats
    print(f"\n📊 Stats: {provider.get_stats()}")
    
    print("\n✅ Mediastack Provider test complete")
