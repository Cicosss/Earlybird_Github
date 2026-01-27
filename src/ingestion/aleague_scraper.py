"""
A-League Dedicated Scraper - TIER 0 Source

Scrapes aleagues.com.au "Ins & Outs" articles directly for injury/squad news.
This is a GOLDEN SOURCE because A-League publishes injury news 3-5 DAYS before matches,
giving us a massive latency advantage over bookmakers who wait for mainstream media.

STRATEGY:
- Direct scraping of aleagues.com.au/news/ pages
- Filters for "ins-outs" and "team-news" articles
- Extracts player names and injury status
- Returns results as TIER 0 source (highest priority)

V1.0 - Initial implementation from Deep Research findings
"""
import logging
import requests
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
import threading

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================
ALEAGUE_BASE_URL = "https://aleagues.com.au"
ALEAGUE_NEWS_URL = f"{ALEAGUE_BASE_URL}/news/"
REQUEST_TIMEOUT = 15  # seconds
MAX_ARTICLES = 20
ARTICLE_MAX_AGE_DAYS = 7  # A-League publishes 3-5 days before match

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Keywords that indicate "Ins & Outs" articles (GOLDEN SOURCE)
INS_OUTS_KEYWORDS = [
    "ins-outs",
    "ins-and-outs",
    "ins and outs",      # With spaces (in titles)
    "ins & outs",        # With ampersand
    "team-news",
    "team news",         # With space
    "injury-update",
    "injury update",     # With space
    "suspensions",
    "injuries",
    "ruled-out",
    "ruled out",         # With space
    "doubtful",
]

# Keywords in article content that indicate injury/squad info
CONTENT_KEYWORDS = [
    "injury", "injured", "out", "ruled out", "doubtful",
    "suspension", "suspended", "unavailable", "sidelined",
    "hamstring", "knee", "ankle", "muscle", "strain",
    "return", "returns", "back", "available", "fit",
    "squad", "lineup", "starting", "bench",
]

# Cache for seen articles
_seen_articles: Set[str] = set()
_seen_articles_lock = threading.Lock()

# Last scrape time
_last_scrape_time: Optional[datetime] = None
SCRAPE_INTERVAL_MINUTES = 30  # Don't scrape more than every 30 min


def _get_article_hash(url: str) -> str:
    """Generate unique hash for article deduplication."""
    return hashlib.md5(url.lower().strip().encode()).hexdigest()[:16]


def _is_article_seen(url: str) -> bool:
    """Check if article was already processed."""
    article_hash = _get_article_hash(url)
    with _seen_articles_lock:
        if article_hash in _seen_articles:
            return True
        _seen_articles.add(article_hash)
        # Limit cache size
        if len(_seen_articles) > 500:
            _seen_articles.clear()
        return False


def _should_scrape() -> bool:
    """Check if enough time has passed since last scrape."""
    global _last_scrape_time
    
    if _last_scrape_time is None:
        return True
    
    elapsed = datetime.now() - _last_scrape_time
    return elapsed.total_seconds() >= SCRAPE_INTERVAL_MINUTES * 60


def _mark_scraped():
    """Mark current time as last scrape."""
    global _last_scrape_time
    _last_scrape_time = datetime.now()


def _is_ins_outs_article(url: str, title: str) -> bool:
    """
    Check if article is an "Ins & Outs" type article.
    
    These are the GOLDEN SOURCE articles that publish 3-5 days before matches.
    """
    text = f"{url} {title}".lower()
    
    for keyword in INS_OUTS_KEYWORDS:
        if keyword in text:
            return True
    
    return False


def _extract_team_mentions(text: str, team_name: str) -> bool:
    """Check if text mentions the target team."""
    if not text or not team_name:
        return False
    
    text_lower = text.lower()
    team_lower = team_name.lower()
    
    # Direct match
    if team_lower in text_lower:
        return True
    
    # Common A-League team name variations
    team_aliases = {
        "sydney fc": ["sydney", "sky blues"],
        "melbourne victory": ["victory", "melbourne v"],
        "melbourne city": ["city", "melbourne c"],
        "western sydney wanderers": ["wanderers", "wsw", "western sydney"],
        "brisbane roar": ["roar", "brisbane"],
        "adelaide united": ["adelaide", "reds"],
        "perth glory": ["perth", "glory"],
        "central coast mariners": ["mariners", "central coast", "ccm"],
        "newcastle jets": ["jets", "newcastle"],
        "wellington phoenix": ["phoenix", "wellington"],
        "macarthur fc": ["macarthur", "bulls"],
        "western united": ["western united", "wufc"],
        "auckland fc": ["auckland"],
    }
    
    for canonical, aliases in team_aliases.items():
        if team_lower in canonical or canonical in team_lower:
            for alias in aliases:
                if alias in text_lower:
                    return True
    
    return False


def _has_injury_content(text: str) -> bool:
    """Check if text contains injury/squad related content."""
    if not text:
        return False
    
    text_lower = text.lower()
    
    for keyword in CONTENT_KEYWORDS:
        if keyword in text_lower:
            return True
    
    return False


def scrape_aleague_news_list() -> List[Dict]:
    """
    Scrape the A-League news listing page for article URLs.
    
    Returns:
        List of article metadata (url, title, date)
    """
    articles = []
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        response = requests.get(
            ALEAGUE_NEWS_URL,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code != 200:
            logger.warning(f"A-League news page returned {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find article links - A-League uses various article card formats
        # Look for links containing /news/ in href
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            
            # Filter for news articles
            if '/news/' not in href:
                continue
            
            # Skip category/tag pages
            if '/news/category/' in href or '/news/tag/' in href:
                continue
            
            # Build full URL
            if href.startswith('/'):
                full_url = f"{ALEAGUE_BASE_URL}{href}"
            elif href.startswith('http'):
                full_url = href
            else:
                continue
            
            # Get title from link text or parent
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                # Try to find title in parent elements
                parent = link.find_parent(['article', 'div'])
                if parent:
                    h_tag = parent.find(['h1', 'h2', 'h3', 'h4'])
                    if h_tag:
                        title = h_tag.get_text(strip=True)
            
            if not title or len(title) < 10:
                continue
            
            # Check if this is an "Ins & Outs" article (priority)
            is_ins_outs = _is_ins_outs_article(full_url, title)
            
            articles.append({
                'url': full_url,
                'title': title,
                'is_ins_outs': is_ins_outs,
                'scraped_at': datetime.now().isoformat(),
            })
        
        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article['url'] not in seen_urls:
                seen_urls.add(article['url'])
                unique_articles.append(article)
        
        # Sort: Ins & Outs articles first
        unique_articles.sort(key=lambda x: (not x['is_ins_outs'], x['title']))
        
        logger.info(f"📰 A-League scraper found {len(unique_articles)} articles ({sum(1 for a in unique_articles if a['is_ins_outs'])} Ins&Outs)")
        
        return unique_articles[:MAX_ARTICLES]
        
    except requests.RequestException as e:
        logger.error(f"A-League scraper request error: {e}")
        return []
    except Exception as e:
        logger.error(f"A-League scraper error: {e}")
        return []


def scrape_article_content(url: str) -> Optional[str]:
    """
    Scrape full content of an A-League article.
    
    Args:
        url: Article URL
        
    Returns:
        Article text content or None
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find article content - try common selectors
        content_selectors = [
            'article',
            '.article-content',
            '.post-content',
            '.entry-content',
            '[class*="article"]',
            'main',
        ]
        
        content = None
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                content = element.get_text(separator=' ', strip=True)
                if len(content) > 200:  # Minimum content length
                    break
        
        return content
        
    except Exception as e:
        logger.debug(f"Error scraping article {url}: {e}")
        return None


def search_aleague_news(
    team_name: str,
    match_id: str,
    force: bool = False
) -> List[Dict]:
    """
    Search A-League news for team-specific injury/squad information.
    
    This is a TIER 0 source - highest priority because A-League publishes
    injury news 3-5 DAYS before matches.
    
    Args:
        team_name: Team to search for
        match_id: Match ID for tracking
        force: Force scrape even if recently scraped
        
    Returns:
        List of relevant news items with TIER 0 tagging
    """
    # Edge case: empty/None team_name
    if not team_name or not team_name.strip():
        logger.debug("A-League scraper: empty team_name, skipping")
        return []
    
    team_name = team_name.strip()
    results = []
    
    # Rate limiting
    if not force and not _should_scrape():
        logger.debug("A-League scraper: skipping (scraped recently)")
        return []
    
    logger.info(f"🦘 A-League scraper searching for: {team_name}")
    
    # Get article list
    articles = scrape_aleague_news_list()
    
    if not articles:
        logger.debug("A-League scraper: no articles found")
        return []
    
    _mark_scraped()
    
    # Process articles
    for article in articles:
        url = article['url']
        title = article['title']
        is_ins_outs = article['is_ins_outs']
        
        # Skip if already seen
        if _is_article_seen(url):
            continue
        
        # Check if title mentions team
        title_mentions_team = _extract_team_mentions(title, team_name)
        
        # For Ins & Outs articles, always include (they cover all teams)
        # For other articles, require team mention in title
        if not is_ins_outs and not title_mentions_team:
            continue
        
        # Get article content for deeper analysis
        content = None
        if is_ins_outs or title_mentions_team:
            content = scrape_article_content(url)
        
        # Check if content mentions team (for Ins & Outs articles)
        content_mentions_team = False
        if content:
            content_mentions_team = _extract_team_mentions(content, team_name)
        
        # Final filter: must mention team somewhere
        if not title_mentions_team and not content_mentions_team:
            continue
        
        # Check for injury-related content
        has_injury_info = _has_injury_content(title) or (content and _has_injury_content(content))
        
        # Build result
        snippet = content[:500] if content else title
        
        result = {
            'match_id': match_id,
            'team': team_name,
            'keyword': 'aleague_ins_outs' if is_ins_outs else 'aleague_news',
            'title': title,
            'snippet': snippet,
            'link': url,
            'date': article.get('scraped_at'),
            'source': 'A-Leagues Official',
            'search_type': 'aleague_scraper',
            # TIER 0 tagging
            'confidence': 'VERY_HIGH' if is_ins_outs else 'HIGH',
            'priority_boost': 2.0 if is_ins_outs else 1.5,
            'source_type': 'official_scraper',
            'is_ins_outs': is_ins_outs,
            'has_injury_info': has_injury_info,
        }
        
        results.append(result)
        
        logger.info(f"   🦘 Found: {title[:60]}... [{'INS&OUTS' if is_ins_outs else 'NEWS'}]")
    
    if results:
        logger.info(f"   🦘 A-League scraper: {len(results)} relevant articles for {team_name}")
    
    return results


def is_aleague_scraper_available() -> bool:
    """
    Check if A-League scraper can reach the website.
    
    Returns:
        True if aleagues.com.au is reachable
    """
    try:
        response = requests.head(
            ALEAGUE_BASE_URL,
            timeout=5,
            headers={"User-Agent": USER_AGENT}
        )
        return response.status_code < 400
    except Exception as e:
        logger.debug(f"A-League availability check failed: {e}")
        return False


# ============================================
# SINGLETON ACCESSOR
# ============================================
_scraper_instance = None
_scraper_lock = threading.Lock()


class ALeagueScraper:
    """Singleton wrapper for A-League scraper functionality."""
    
    def __init__(self):
        self._available = None
    
    def is_available(self) -> bool:
        """Check if scraper is available."""
        if self._available is None:
            self._available = is_aleague_scraper_available()
        return self._available
    
    def search_team_news(
        self,
        team_name: str,
        match_id: str,
        force: bool = False
    ) -> List[Dict]:
        """Search for team news."""
        return search_aleague_news(team_name, match_id, force)
    
    def should_scrape(self) -> bool:
        """Check if enough time has passed since last scrape."""
        return _should_scrape()


def get_aleague_scraper() -> ALeagueScraper:
    """Get singleton A-League scraper instance."""
    global _scraper_instance
    
    with _scraper_lock:
        if _scraper_instance is None:
            _scraper_instance = ALeagueScraper()
        return _scraper_instance


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🦘 A-LEAGUE SCRAPER TEST")
    print("=" * 60)
    
    # Check availability
    scraper = get_aleague_scraper()
    print(f"\n📡 Scraper available: {scraper.is_available()}")
    
    if not scraper.is_available():
        print("❌ Cannot reach aleagues.com.au")
        sys.exit(1)
    
    # Test team search
    test_team = sys.argv[1] if len(sys.argv) > 1 else "Sydney FC"
    print(f"\n🔍 Searching for: {test_team}")
    
    results = scraper.search_team_news(test_team, "test_match_001", force=True)
    
    print(f"\n📰 Found {len(results)} results:")
    for r in results:
        ins_outs_tag = "🌟 INS&OUTS" if r.get('is_ins_outs') else "📰 NEWS"
        print(f"   {ins_outs_tag} {r['title'][:50]}...")
        print(f"      URL: {r['link']}")
        print(f"      Confidence: {r['confidence']}")
