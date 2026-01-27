"""
EarlyBird Nitter Fallback Scraper - V1.0

Fallback scraper for Twitter Intel when DeepSeek/Gemini fails.
Uses Nitter instances (twiiit.com, xcancel.com) to extract tweets
from configured accounts.

FLOW:
1. DeepSeek extract_twitter_intel() fails
2. NitterFallbackScraper.scrape_accounts() is called
3. For each account:
   a. Select Nitter instance (round-robin)
   b. Navigate with Playwright (anti-bot protection)
   c. Extract tweets from HTML
   d. Apply ExclusionFilter (skip basketball, women's, etc.)
   e. Apply RelevanceAnalyzer (keyword-based scoring)
4. Return filtered tweets in same format as DeepSeek

OPTIMIZATIONS:
- Round-robin between instances (reduce ban risk)
- Pre-filtering HTML (skip irrelevant pages early)
- Persistent cache (avoid re-scraping same content)
- Retry with fallback (if one instance fails, try another)
- Health check (test instances at startup)

Requirements: Playwright, BeautifulSoup4
"""
import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

# Import shared content analysis utilities
from src.utils.content_analysis import (
    ExclusionFilter,
    RelevanceAnalyzer,
    get_exclusion_filter,
    get_relevance_analyzer,
)

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

# Nitter instances (round-robin)
NITTER_INSTANCES = [
    "https://twiiit.com",      # Redirects to active Nitter instance
    "https://xcancel.com",     # Alternative Nitter frontend
]

# Fallback instances if primary ones fail
NITTER_FALLBACK_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

# Scraping configuration
SCRAPE_DELAY_MIN = 1.5  # Minimum delay between requests (seconds)
SCRAPE_DELAY_MAX = 3.0  # Maximum delay between requests (seconds)
PAGE_TIMEOUT_SECONDS = 30
MAX_TWEETS_PER_ACCOUNT = 5
MAX_RETRIES_PER_ACCOUNT = 2

# Cache configuration
CACHE_FILE = "data/nitter_cache.json"
CACHE_TTL_HOURS = 6  # Cache tweets for 6 hours

# Pre-filtering keywords (skip pages without these)
RELEVANCE_KEYWORDS = [
    "injury", "injured", "out", "miss", "absent", "doubt",
    "lineup", "squad", "team", "starting", "bench",
    "transfer", "signing", "loan", "deal",
    "suspended", "ban", "red card",
    "infortunio", "lesión", "lesão", "kontuzja", "sakatlık",
    "convocati", "formazione", "escalação",
]


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class ScrapedTweet:
    """Tweet extracted from Nitter."""
    handle: str
    date: str
    content: str
    topics: List[str] = field(default_factory=list)
    relevance_score: float = 0.0


@dataclass
class InstanceHealth:
    """Health status of a Nitter instance."""
    url: str
    is_healthy: bool = True
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None


# ============================================
# PERSISTENT CACHE
# ============================================

class NitterCache:
    """
    Persistent cache for scraped tweets.
    
    Saves to JSON file to avoid re-scraping same content.
    Implements TTL-based expiration.
    """
    
    def __init__(self, cache_file: str = CACHE_FILE, ttl_hours: int = CACHE_TTL_HOURS):
        self._cache_file = Path(cache_file)
        self._ttl_hours = ttl_hours
        self._cache: Dict[str, Dict] = {}
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cache from file."""
        if not self._cache_file.exists():
            self._cache = {}
            return
        
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Filter expired entries
                now = datetime.now(timezone.utc)
                self._cache = {
                    k: v for k, v in data.items()
                    if self._is_valid_entry(v, now)
                }
            logger.debug(f"🐦 [NITTER-CACHE] Loaded {len(self._cache)} entries")
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-CACHE] Failed to load cache: {e}")
            self._cache = {}
    
    def _is_valid_entry(self, entry: Dict, now: datetime) -> bool:
        """Check if cache entry is still valid."""
        if 'cached_at' not in entry:
            return False
        try:
            cached_at = datetime.fromisoformat(entry['cached_at'].replace('Z', '+00:00'))
            return (now - cached_at) < timedelta(hours=self._ttl_hours)
        except Exception:
            return False
    
    def _save_cache(self) -> None:
        """Save cache to file."""
        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-CACHE] Failed to save cache: {e}")
    
    def get(self, handle: str) -> Optional[List[Dict]]:
        """Get cached tweets for a handle."""
        handle_key = handle.lower().replace('@', '')
        entry = self._cache.get(handle_key)
        if entry and self._is_valid_entry(entry, datetime.now(timezone.utc)):
            return entry.get('tweets', [])
        return None
    
    def set(self, handle: str, tweets: List[Dict]) -> None:
        """Cache tweets for a handle."""
        handle_key = handle.lower().replace('@', '')
        self._cache[handle_key] = {
            'tweets': tweets,
            'cached_at': datetime.now(timezone.utc).isoformat()
        }
        self._save_cache()
    
    def clear_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._cache.items() if not self._is_valid_entry(v, now)]
        for k in expired:
            del self._cache[k]
        if expired:
            self._save_cache()
        return len(expired)


# ============================================
# NITTER FALLBACK SCRAPER
# ============================================

class NitterFallbackScraper:
    """
    Fallback scraper for Twitter Intel using Nitter instances.
    
    Uses Playwright to bypass anti-bot protection on Nitter instances.
    Implements round-robin instance selection and intelligent retry.
    
    Features:
    - Round-robin between instances (reduce ban risk)
    - Pre-filtering HTML (skip irrelevant pages early)
    - Persistent cache (avoid re-scraping)
    - Health check (test instances at startup)
    - Retry with fallback (if one instance fails, try another)
    """
    
    def __init__(self):
        """Initialize the scraper."""
        self._instances = list(NITTER_INSTANCES)
        self._fallback_instances = list(NITTER_FALLBACK_INSTANCES)
        self._instance_index = 0
        self._instance_health: Dict[str, InstanceHealth] = {}
        
        # Initialize health tracking
        for url in self._instances + self._fallback_instances:
            self._instance_health[url] = InstanceHealth(url=url)
        
        # Cache
        self._cache = NitterCache()
        
        # Filters
        self._exclusion_filter = get_exclusion_filter()
        self._relevance_analyzer = get_relevance_analyzer()
        
        # Playwright resources (lazy init)
        self._playwright = None
        self._browser = None
        
        # Stats
        self._total_scraped = 0
        self._cache_hits = 0
        self._instance_switches = 0
        
        logger.info("🐦 [NITTER-FALLBACK] Initialized")
    
    async def _ensure_browser(self) -> bool:
        """Ensure Playwright browser is initialized."""
        if self._browser and self._browser.is_connected():
            return True
        
        try:
            from playwright.async_api import async_playwright
            
            if not self._playwright:
                self._playwright = await async_playwright().start()
            
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-extensions'
                ]
            )
            logger.info("✅ [NITTER-FALLBACK] Browser initialized")
            return True
        except Exception as e:
            logger.error(f"❌ [NITTER-FALLBACK] Failed to init browser: {e}")
            return False
    
    async def close(self) -> None:
        """Close browser resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
    
    def _get_next_instance(self) -> str:
        """Get next healthy instance (round-robin)."""
        # Try primary instances first
        for _ in range(len(self._instances)):
            url = self._instances[self._instance_index]
            self._instance_index = (self._instance_index + 1) % len(self._instances)
            
            health = self._instance_health.get(url)
            if health and health.is_healthy:
                return url
        
        # Try fallback instances
        for url in self._fallback_instances:
            health = self._instance_health.get(url)
            if health and health.is_healthy:
                self._instance_switches += 1
                return url
        
        # All unhealthy, try first primary anyway
        return self._instances[0]
    
    def _mark_instance_success(self, url: str) -> None:
        """Mark instance as successful."""
        health = self._instance_health.get(url)
        if health:
            health.is_healthy = True
            health.consecutive_failures = 0
            health.last_success = datetime.now(timezone.utc)
    
    def _mark_instance_failure(self, url: str) -> None:
        """Mark instance as failed."""
        health = self._instance_health.get(url)
        if health:
            health.consecutive_failures += 1
            health.last_check = datetime.now(timezone.utc)
            if health.consecutive_failures >= 3:
                health.is_healthy = False
                logger.warning(f"⚠️ [NITTER-FALLBACK] Instance marked unhealthy: {url}")

    
    async def health_check(self) -> Dict[str, bool]:
        """
        Test all instances and return health status.
        
        Returns:
            Dict mapping instance URL to health status
        """
        if not await self._ensure_browser():
            return {url: False for url in self._instances + self._fallback_instances}
        
        results = {}
        
        for url in self._instances + self._fallback_instances:
            try:
                page = await self._browser.new_page()
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                
                # Try to load homepage
                response = await page.goto(url, timeout=PAGE_TIMEOUT_SECONDS * 1000)
                
                if response and response.status == 200:
                    # Check if it's a valid Nitter page (not a captcha)
                    content = await page.content()
                    if 'nitter' in content.lower() or 'timeline' in content.lower():
                        results[url] = True
                        self._mark_instance_success(url)
                    else:
                        results[url] = False
                        self._mark_instance_failure(url)
                else:
                    results[url] = False
                    self._mark_instance_failure(url)
                
                await page.close()
                
            except Exception as e:
                logger.debug(f"⚠️ [NITTER-FALLBACK] Health check failed for {url}: {e}")
                results[url] = False
                self._mark_instance_failure(url)
        
        healthy_count = sum(1 for v in results.values() if v)
        logger.info(f"🐦 [NITTER-FALLBACK] Health check: {healthy_count}/{len(results)} instances healthy")
        
        return results
    
    def _pre_filter_html(self, html: str) -> bool:
        """
        Quick check if HTML contains relevant keywords.
        
        Optimization: Skip full parsing if page is clearly irrelevant.
        
        Args:
            html: Raw HTML content
            
        Returns:
            True if page might be relevant, False to skip
        """
        if not html:
            return False
        
        html_lower = html.lower()
        
        # Check for any relevance keyword
        for keyword in RELEVANCE_KEYWORDS:
            if keyword in html_lower:
                return True
        
        return False
    
    def _extract_tweets_from_html(self, html: str, handle: str) -> List[ScrapedTweet]:
        """
        Extract tweets from Nitter HTML.
        
        Args:
            html: Page HTML content
            handle: Twitter handle being scraped
            
        Returns:
            List of extracted tweets
        """
        if not BS4_AVAILABLE or not html:
            return []
        
        tweets = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Nitter tweet selectors (may vary by instance)
        tweet_containers = soup.select('.timeline-item, .tweet-body, .main-tweet')
        
        for container in tweet_containers[:MAX_TWEETS_PER_ACCOUNT]:
            try:
                # Extract content
                content_elem = container.select_one('.tweet-content, .tweet-text, .content')
                if not content_elem:
                    continue
                
                content = content_elem.get_text(strip=True)
                if not content or len(content) < 10:
                    continue
                
                # Apply exclusion filter
                if self._exclusion_filter.is_excluded(content):
                    continue
                
                # Extract date
                date_elem = container.select_one('.tweet-date a, .tweet-published, time')
                date_str = ""
                if date_elem:
                    date_str = date_elem.get('title', '') or date_elem.get_text(strip=True)
                
                # Analyze relevance
                analysis = self._relevance_analyzer.analyze(content)
                
                # Determine topics
                topics = []
                if analysis.category != "OTHER":
                    topics.append(analysis.category.lower())
                
                tweets.append(ScrapedTweet(
                    handle=handle,
                    date=date_str or datetime.now().strftime("%Y-%m-%d"),
                    content=content[:500],  # Limit content length
                    topics=topics,
                    relevance_score=analysis.confidence
                ))
                
            except Exception as e:
                logger.debug(f"⚠️ [NITTER-FALLBACK] Error parsing tweet: {e}")
                continue
        
        return tweets

    
    async def _scrape_account(self, handle: str) -> List[ScrapedTweet]:
        """
        Scrape tweets from a single account.
        
        Args:
            handle: Twitter handle (with or without @)
            
        Returns:
            List of scraped tweets
        """
        # Guard against None/invalid handle
        if not handle or not isinstance(handle, str):
            return []
        
        # Normalize handle
        handle_clean = handle.replace('@', '').strip()
        if not handle_clean:
            return []
        
        # Check cache first
        cached = self._cache.get(handle_clean)
        if cached:
            self._cache_hits += 1
            logger.debug(f"🐦 [NITTER-FALLBACK] Cache hit for @{handle_clean}")
            return [
                ScrapedTweet(
                    handle=f"@{handle_clean}",
                    date=t.get('date', ''),
                    content=t.get('content', ''),
                    topics=t.get('topics', []),
                    relevance_score=t.get('relevance_score', 0.5)
                )
                for t in cached
            ]
        
        # Ensure browser is ready
        if not await self._ensure_browser():
            return []
        
        tweets = []
        last_error = None
        
        # Try with retry
        for attempt in range(MAX_RETRIES_PER_ACCOUNT):
            instance_url = self._get_next_instance()
            profile_url = f"{instance_url}/{handle_clean}"
            
            try:
                page = await self._browser.new_page()
                
                # Set stealth headers
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                })
                
                # Navigate to profile
                response = await page.goto(
                    profile_url,
                    timeout=PAGE_TIMEOUT_SECONDS * 1000,
                    wait_until='domcontentloaded'
                )
                
                if not response or response.status != 200:
                    await page.close()
                    self._mark_instance_failure(instance_url)
                    continue
                
                # Wait for content to load (Nitter uses JS)
                await page.wait_for_timeout(2000)
                
                # Get HTML
                html = await page.content()
                await page.close()
                
                # Pre-filter check
                if not self._pre_filter_html(html):
                    logger.debug(f"🐦 [NITTER-FALLBACK] No relevant content for @{handle_clean}")
                    self._mark_instance_success(instance_url)
                    # Cache empty result to avoid re-scraping
                    self._cache.set(handle_clean, [])
                    return []
                
                # Extract tweets
                tweets = self._extract_tweets_from_html(html, f"@{handle_clean}")
                
                if tweets:
                    self._mark_instance_success(instance_url)
                    self._total_scraped += len(tweets)
                    
                    # Cache results
                    self._cache.set(handle_clean, [
                        {
                            'date': t.date,
                            'content': t.content,
                            'topics': t.topics,
                            'relevance_score': t.relevance_score
                        }
                        for t in tweets
                    ])
                    
                    logger.debug(f"✅ [NITTER-FALLBACK] Scraped {len(tweets)} tweets from @{handle_clean}")
                    return tweets
                else:
                    # No tweets found but page loaded OK
                    self._mark_instance_success(instance_url)
                    self._cache.set(handle_clean, [])
                    return []
                
            except Exception as e:
                last_error = e
                # V6.2 FIX 8: Log at INFO level for visibility in production
                logger.info(f"⚠️ [NITTER-FALLBACK] Attempt {attempt+1}/{MAX_RETRIES_PER_ACCOUNT} failed for @{handle_clean}: {type(e).__name__}: {e}")
                self._mark_instance_failure(instance_url)
                
                # Random delay before retry
                await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))
        
        # V6.2 FIX 8: Log final failure at WARNING with full error details
        logger.warning(f"❌ [NITTER-FALLBACK] All {MAX_RETRIES_PER_ACCOUNT} attempts failed for @{handle_clean}: {type(last_error).__name__}: {last_error}")
        return []

    
    async def scrape_accounts(
        self,
        handles: List[str],
        max_posts_per_account: int = MAX_TWEETS_PER_ACCOUNT
    ) -> Optional[Dict]:
        """
        Scrape tweets from multiple accounts.
        
        Main entry point - returns data in same format as DeepSeek.
        
        Args:
            handles: List of Twitter handles (with @)
            max_posts_per_account: Max tweets per account
            
        Returns:
            Dict in DeepSeek format: {"accounts": [...], "extraction_time": "..."}
        """
        if not handles:
            return None
        
        # Filter out None/invalid handles (must be non-empty string after stripping @)
        valid_handles = [
            h for h in handles 
            if h and isinstance(h, str) and h.replace('@', '').strip()
        ]
        if not valid_handles:
            return None
        
        logger.info(f"🐦 [NITTER-FALLBACK] Scraping {len(valid_handles)} accounts...")
        
        accounts_data = []
        
        for handle in valid_handles:
            # Scrape account
            tweets = await self._scrape_account(handle)
            
            # Format for output
            handle_clean = handle.replace('@', '').strip()
            posts = [
                {
                    "date": t.date,
                    "content": t.content,
                    "topics": t.topics
                }
                for t in tweets[:max_posts_per_account]
            ]
            
            accounts_data.append({
                "handle": f"@{handle_clean}",
                "posts": posts
            })
            
            # Delay between accounts
            if handle != valid_handles[-1]:  # Not last
                await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))
        
        # Count accounts with data
        accounts_with_posts = sum(1 for a in accounts_data if a.get('posts'))
        total_posts = sum(len(a.get('posts', [])) for a in accounts_data)
        
        logger.info(
            f"✅ [NITTER-FALLBACK] Scraped {accounts_with_posts}/{len(handles)} accounts, "
            f"{total_posts} tweets (cache hits: {self._cache_hits})"
        )
        
        return {
            "accounts": accounts_data,
            "extraction_time": datetime.now(timezone.utc).isoformat(),
            "source": "nitter_fallback",
            "stats": {
                "total_scraped": self._total_scraped,
                "cache_hits": self._cache_hits,
                "instance_switches": self._instance_switches
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scraper statistics."""
        return {
            "total_scraped": self._total_scraped,
            "cache_hits": self._cache_hits,
            "instance_switches": self._instance_switches,
            "instance_health": {
                url: {
                    "healthy": h.is_healthy,
                    "failures": h.consecutive_failures
                }
                for url, h in self._instance_health.items()
            }
        }


# ============================================
# SINGLETON INSTANCE
# ============================================

_nitter_scraper_instance: Optional[NitterFallbackScraper] = None


def get_nitter_fallback_scraper() -> NitterFallbackScraper:
    """Get or create singleton NitterFallbackScraper instance."""
    global _nitter_scraper_instance
    if _nitter_scraper_instance is None:
        _nitter_scraper_instance = NitterFallbackScraper()
    return _nitter_scraper_instance


async def scrape_twitter_intel_fallback(
    handles: List[str],
    max_posts_per_account: int = MAX_TWEETS_PER_ACCOUNT
) -> Optional[Dict]:
    """
    Convenience function to scrape Twitter intel via Nitter fallback.
    
    Args:
        handles: List of Twitter handles
        max_posts_per_account: Max tweets per account
        
    Returns:
        Dict in DeepSeek format or None on failure
    """
    scraper = get_nitter_fallback_scraper()
    return await scraper.scrape_accounts(handles, max_posts_per_account)


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    import sys
    
    async def test_scraper():
        print("=" * 60)
        print("🐦 NITTER FALLBACK SCRAPER - TEST")
        print("=" * 60)
        
        scraper = get_nitter_fallback_scraper()
        
        # Health check
        print("\n🏥 Health Check:")
        health = await scraper.health_check()
        for url, is_healthy in health.items():
            status = "✅" if is_healthy else "❌"
            print(f"   {status} {url}")
        
        # Test scraping
        test_handles = ["@RudyGaletti", "@AnthonyRJoseph"]
        print(f"\n🔍 Scraping {len(test_handles)} accounts...")
        
        result = await scraper.scrape_accounts(test_handles)
        
        if result:
            print(f"\n📊 Results:")
            print(f"   Accounts: {len(result.get('accounts', []))}")
            for acc in result.get('accounts', []):
                posts = acc.get('posts', [])
                print(f"   {acc['handle']}: {len(posts)} tweets")
                for post in posts[:2]:
                    print(f"      - {post['content'][:60]}...")
        else:
            print("❌ No results")
        
        # Stats
        print(f"\n📈 Stats:")
        stats = scraper.get_stats()
        print(f"   Total scraped: {stats['total_scraped']}")
        print(f"   Cache hits: {stats['cache_hits']}")
        
        # Cleanup
        await scraper.close()
        print("\n✅ Test complete")
    
    asyncio.run(test_scraper())
