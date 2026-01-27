"""
Reddit Monitor - DEPRECATED V8.0

⚠️ THIS MODULE IS DEPRECATED AND NO LONGER USED ⚠️

Reddit monitoring was removed in V8.0 because:
1. Rumors arrived too late (already priced in by market)
2. Low signal-to-noise ratio (fan speculation vs real intel)
3. Added ~3s latency per match with no betting edge
4. API calls wasted on low-value data

The module is kept for:
- Historical reference
- Potential future reactivation if Reddit becomes useful
- Backward compatibility during transition

All functions now return empty results when called.
REDDIT_ENABLED is permanently set to False in config/settings.py.

Original purpose:
Scans subreddits for high-value rumors via Redlib (privacy frontend).
Monitors football subreddits for injury news, lineup leaks, etc.
"""
import logging
import random
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

# V8.0: Reddit Monitor permanently disabled
# Check if Reddit Monitor is enabled (always False now)
try:
    from config.settings import REDDIT_ENABLED
except ImportError:
    REDDIT_ENABLED = False  # Default to disabled

if not REDDIT_ENABLED:
    logging.debug("🔴 Reddit Monitor disabled (V8.0 - deprecated)")

# V8.0: Import kept for backward compatibility but functions return empty
from src.processing.sources_config import get_reddit_sources, get_country_from_league

# ============================================
# REDLIB INSTANCE POOL (Privacy Frontend)
# ============================================
# Localhost (self-hosted) takes priority, public instances as fallback
REDLIB_LOCALHOST = "http://127.0.0.1:8888"

# Public instances as fallback - unstable, need aggressive retries
REDLIB_PUBLIC_INSTANCES = [
    "https://redlib.catsarch.com",
    "https://redlib.reallyaweso.me",
    "https://lr.ptr.moe",
    "https://reddit.rtrace.io",
    "https://libreddit.bus-hit.me",
    "https://libreddit.projectsegfau.lt",
    "https://redlib.perennialteks.com",
    "https://redlib.freedit.eu",
]

# Combined list: localhost first, then public fallbacks
REDLIB_INSTANCES = [REDLIB_LOCALHOST] + REDLIB_PUBLIC_INSTANCES

# Fallback to direct Reddit API (often 403'd but worth trying)
REDDIT_BASE_URL = "https://www.reddit.com/r/{subreddit}/new.json"

# Stealth Browser Headers
REDLIB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "0",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Keywords that indicate valuable rumors (multi-language)
RUMOR_KEYWORDS = {
    "high_value": [
        "injury", "injured", "ruled out", "doubtful", "suspended",
        "lesionado", "lesión", "baja", "duda", "sancionado",
        "sakat", "cezalı", "kadro dışı",
        "τραυματίας", "απών",
        "lineup", "squad", "starting XI", "team news",
        "formación", "alineación", "convocatoria",
        "kadro", "ilk 11",
    ],
    "medium_value": [
        "bench", "rotation", "rested", "fitness",
        "suplente", "rotación", "descanso",
        "yedek", "dinlenme",
        "travel", "flight", "delayed",
        "coach", "manager", "argument", "conflict",
    ],
}


class RedlibClient:
    """
    Redlib client with round-robin instance failover.
    
    Handles the instability of public Redlib instances by trying
    multiple endpoints until one succeeds.
    """
    
    def __init__(self, instances: List[str] = None):
        if instances:
            self.instances = instances
        else:
            # Localhost first (self-hosted), then shuffle public instances
            public = REDLIB_PUBLIC_INSTANCES.copy()
            random.shuffle(public)
            self.instances = [REDLIB_LOCALHOST] + public
        self._failed_instances = set()
        self._last_success_instance = None
    
    def _parse_posts_from_response(self, data: dict) -> List[Dict]:
        """
        Parse posts from Redlib/Reddit JSON response.
        
        Handles different response structures:
        - Reddit API: data['data']['children']
        - Redlib: data['data']['children'] or data['posts']
        """
        posts = []
        
        # Try Reddit API format: data.data.children
        if isinstance(data, dict):
            if 'data' in data and isinstance(data['data'], dict):
                children = data['data'].get('children', [])
                if children:
                    for child in children:
                        if isinstance(child, dict) and 'data' in child:
                            posts.append(child['data'])
                        elif isinstance(child, dict):
                            posts.append(child)
                    return posts
            
            # Try Redlib format: data.posts
            if 'posts' in data:
                posts_list = data['posts']
                if isinstance(posts_list, list):
                    return posts_list
            
            # Try direct children array
            if 'children' in data:
                children = data['children']
                if isinstance(children, list):
                    for child in children:
                        if isinstance(child, dict) and 'data' in child:
                            posts.append(child['data'])
                        elif isinstance(child, dict):
                            posts.append(child)
                    return posts
        
        return posts
    
    def fetch_posts(self, subreddit: str, limit: int = 25) -> List[Dict]:
        """
        Fetch posts from subreddit using Redlib with round-robin failover.
        
        Tries each instance until one succeeds. Aggressive retries due to
        instance instability.
        
        Args:
            subreddit: Subreddit name (without r/)
            limit: Number of posts to fetch
            
        Returns:
            List of post data dictionaries
        """
        # Prioritize last successful instance
        instances_to_try = self.instances.copy()
        if self._last_success_instance and self._last_success_instance in instances_to_try:
            instances_to_try.remove(self._last_success_instance)
            instances_to_try.insert(0, self._last_success_instance)
        
        for instance in instances_to_try:
            # Skip recently failed instances (but retry after all others fail)
            if instance in self._failed_instances and instance != instances_to_try[-1]:
                continue
                
            url = f"{instance}/r/{subreddit}/new.json"
            
            try:
                logging.debug(f"🔄 Trying Redlib: {instance}/r/{subreddit}")
                time.sleep(0.5)  # Small delay between requests
                
                response = requests.get(
                    url,
                    headers=REDLIB_HEADERS,
                    params={"limit": min(limit, 100)},
                    timeout=10
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        posts = self._parse_posts_from_response(data)
                        
                        if posts:
                            logging.info(f"✅ Redlib success: {instance} returned {len(posts)} posts")
                            self._last_success_instance = instance
                            self._failed_instances.discard(instance)
                            return posts
                        else:
                            logging.debug(f"⚠️ Redlib {instance}: Empty response")
                            
                    except (ValueError, KeyError) as e:
                        logging.debug(f"⚠️ Redlib {instance}: JSON parse error - {e}")
                        
                elif response.status_code == 403:
                    logging.debug(f"⚠️ Redlib {instance}: 403 Forbidden")
                    self._failed_instances.add(instance)
                    
                elif response.status_code == 429:
                    logging.debug(f"⚠️ Redlib {instance}: Rate limited")
                    self._failed_instances.add(instance)
                    time.sleep(2)  # Extra delay on rate limit
                    
                else:
                    logging.debug(f"⚠️ Redlib {instance}: HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logging.debug(f"⚠️ Redlib {instance}: Timeout")
                self._failed_instances.add(instance)
                
            except requests.exceptions.ConnectionError:
                logging.debug(f"⚠️ Redlib {instance}: Connection error")
                self._failed_instances.add(instance)
                
            except Exception as e:
                logging.debug(f"⚠️ Redlib {instance}: {e}")
                self._failed_instances.add(instance)
        
        # All Redlib instances failed - try direct Reddit as last resort
        logging.warning(f"⚠️ All Redlib instances failed for r/{subreddit}, trying direct Reddit...")
        return self._fetch_direct_reddit(subreddit, limit)
    
    def _fetch_direct_reddit(self, subreddit: str, limit: int) -> List[Dict]:
        """Fallback to direct Reddit API (often 403'd but worth trying)."""
        url = REDDIT_BASE_URL.format(subreddit=subreddit)
        
        try:
            time.sleep(1)
            response = requests.get(
                url,
                headers=REDLIB_HEADERS,
                params={"limit": min(limit, 100)},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                posts = self._parse_posts_from_response(data)
                if posts:
                    logging.info(f"✅ Direct Reddit fallback success: {len(posts)} posts")
                    return posts
                    
            logging.debug(f"Direct Reddit failed: HTTP {response.status_code}")
            
        except Exception as e:
            logging.debug(f"Direct Reddit error: {e}")
        
        return []


# Singleton client instance
_redlib_client: Optional[RedlibClient] = None


def get_redlib_client() -> RedlibClient:
    """Get or create singleton RedlibClient."""
    global _redlib_client
    if _redlib_client is None:
        _redlib_client = RedlibClient()
    return _redlib_client


def fetch_subreddit_posts(subreddit: str, limit: int = 25) -> List[Dict]:
    """
    Fetch recent posts from a subreddit using Redlib with failover.
    
    Args:
        subreddit: Subreddit name (without r/)
        limit: Number of posts to fetch (max 100)
        
    Returns:
        List of post data dictionaries
    """
    client = get_redlib_client()
    return client.fetch_posts(subreddit, limit)


def search_reddit_via_provider(subreddit: str, team_names: List[str] = None, limit: int = 10) -> List[Dict]:
    """
    Search Reddit via SearchProvider (DuckDuckGo/Serper) when Redlib fails.
    
    Uses site:reddit.com/r/{subreddit} query to find relevant posts.
    
    Args:
        subreddit: Subreddit name
        team_names: Team names to search for
        limit: Max results
        
    Returns:
        List of pseudo-post dictionaries compatible with filter_relevant_posts
    """
    try:
        from src.ingestion.search_provider import get_search_provider
        provider = get_search_provider()
        
        posts = []
        search_teams = team_names if team_names else [""]
        
        for team in search_teams[:2]:  # Limit to 2 teams to save API calls
            if team:
                query = f'site:reddit.com/r/{subreddit} "{team}" (injury OR lineup OR squad)'
            else:
                query = f'site:reddit.com/r/{subreddit} (injury OR lineup OR transfer)'
            
            results = provider.search(query, num_results=5)
            
            for item in results:
                posts.append({
                    "title": item.get("title", ""),
                    "selftext": item.get("snippet", ""),
                    "permalink": item.get("link", "").replace("https://reddit.com", "").replace("https://www.reddit.com", ""),
                    "subreddit": subreddit,
                    "author": "unknown",
                    "created_utc": time.time(),
                    "ups": 0,
                })
        
        if posts:
            logging.info(f"🔍 SearchProvider found {len(posts)} Reddit results for r/{subreddit}")
        
        return posts
        
    except Exception as e:
        logging.error(f"SearchProvider Reddit fallback failed: {e}")
        return []


def filter_relevant_posts(
    posts: List[Dict],
    team_names: List[str] = None,
    max_age_hours: int = 24
) -> List[Dict]:
    """
    Filter posts for relevant rumors based on keywords and team names.
    
    Args:
        posts: Raw post data from Reddit/Redlib
        team_names: Optional list of team names to filter for
        max_age_hours: Only include posts from last N hours
        
    Returns:
        Filtered list of relevant posts with confidence scores
    """
    relevant = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    
    for post in posts:
        # Check post age
        created_utc = post.get("created_utc", 0)
        if isinstance(created_utc, str):
            try:
                created_utc = float(created_utc)
            except ValueError:
                created_utc = time.time()
        
        try:
            post_time = datetime.fromtimestamp(created_utc, timezone.utc)
            if post_time < cutoff_time:
                continue
        except (ValueError, OSError):
            pass  # Invalid timestamp, include anyway
        
        title = post.get("title", "") or ""
        selftext = post.get("selftext", "") or post.get("body", "") or ""
        combined_text = f"{title} {selftext}".lower()
        
        # Calculate relevance score
        score = 0
        matched_keywords = []
        
        for kw in RUMOR_KEYWORDS["high_value"]:
            if kw.lower() in combined_text:
                score += 3
                matched_keywords.append(kw)
        
        for kw in RUMOR_KEYWORDS["medium_value"]:
            if kw.lower() in combined_text:
                score += 1
                matched_keywords.append(kw)
        
        team_matched = None
        if team_names:
            for team in team_names:
                if team.lower() in combined_text:
                    score += 2
                    team_matched = team
                    break
        
        if score >= 3:
            permalink = post.get("permalink", "") or ""
            relevant.append({
                "title": post.get("title"),
                "selftext": (selftext)[:500],
                "url": f"https://reddit.com{permalink}" if permalink else "",
                "subreddit": post.get("subreddit"),
                "author": post.get("author"),
                "created_utc": created_utc,
                "upvotes": post.get("ups", 0) or post.get("score", 0),
                "relevance_score": min(score, 10),
                "matched_keywords": matched_keywords[:5],
                "team_matched": team_matched,
            })
    
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    return relevant


def scan_league_subreddits(league_key: str, team_names: List[str] = None) -> List[Dict]:
    """
    Scan all subreddits for a league and return relevant rumors.
    
    Uses Redlib first, falls back to SearchProvider if all instances fail.
    
    Args:
        league_key: API league key (e.g., 'soccer_turkey_super_league')
        team_names: Optional team names to prioritize
        
    Returns:
        List of structured rumors for Gemini analysis
    """
    subreddits = get_reddit_sources(league_key)
    
    if not subreddits:
        logging.info(f"No Reddit sources configured for {league_key}")
        return []
    
    all_rumors = []
    use_search_fallback = False
    
    for subreddit in subreddits:
        logging.info(f"🔴 Scanning r/{subreddit} via Redlib...")
        
        posts = fetch_subreddit_posts(subreddit, limit=25)
        
        if not posts:
            logging.info(f"   📡 Using SearchProvider fallback for r/{subreddit}")
            posts = search_reddit_via_provider(subreddit, team_names, limit=10)
            use_search_fallback = True
        
        if posts:
            max_age = 48 if use_search_fallback else 24
            relevant = filter_relevant_posts(posts, team_names, max_age_hours=max_age)
            logging.info(f"   Found {len(relevant)} relevant posts in r/{subreddit}")
            all_rumors.extend(relevant)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_rumors = []
    for rumor in all_rumors:
        if rumor["url"] not in seen_urls:
            seen_urls.add(rumor["url"])
            unique_rumors.append(rumor)
    
    return unique_rumors


def format_rumors_for_gemini(rumors: List[Dict], match_id: str = None) -> List[Dict]:
    """
    Format Reddit rumors as news items for Gemini analysis.
    
    Reddit rumors get a max confidence of 5 (low) unless keywords are extreme.
    This prevents false positives from unverified fan speculation.
    
    Args:
        rumors: List of Reddit rumors
        match_id: Optional match ID for tracking
        
    Returns:
        List of news items compatible with Gemini analyzer
    """
    news_items = []
    
    for rumor in rumors:
        score = rumor.get("relevance_score", 3)
        if score >= 9:
            max_confidence = 5
        elif score >= 6:
            max_confidence = 4
        else:
            max_confidence = 3
        
        created_utc = rumor.get("created_utc", 0)
        try:
            date_str = datetime.fromtimestamp(created_utc, timezone.utc).isoformat()
        except (ValueError, OSError):
            date_str = datetime.now(timezone.utc).isoformat()
        
        news_items.append({
            "match_id": match_id,
            "team": rumor.get("team_matched", "Unknown"),
            "keyword": "reddit_rumor",
            "title": rumor.get("title"),
            "snippet": rumor.get("selftext", "")[:300],
            "link": rumor.get("url"),
            "date": date_str,
            "source": f"Reddit r/{rumor.get('subreddit')}",
            "search_type": "reddit_monitor",
            "max_confidence": max_confidence,
            "relevance_score": score,
            "matched_keywords": rumor.get("matched_keywords", []),
        })
    
    return news_items


def run_reddit_monitor(league_key: str, team_names: List[str] = None, match_id: str = None) -> List[Dict]:
    """
    Main entry point for Reddit monitoring.
    
    Scans configured subreddits for a league and returns Gemini-ready news items.
    
    Args:
        league_key: API league key
        team_names: Team names to prioritize in search
        match_id: Match ID for tracking
        
    Returns:
        List of news items for Gemini analysis
    """
    if not REDDIT_ENABLED:
        logging.debug("Reddit Monitor disabled")
        return []
    
    country = get_country_from_league(league_key)
    logging.info(f"🔴 Reddit Monitor starting for {country} ({league_key})")
    
    rumors = scan_league_subreddits(league_key, team_names)
    
    if rumors:
        logging.info(f"🔴 Reddit Monitor found {len(rumors)} rumors")
        return format_rumors_for_gemini(rumors, match_id)
    else:
        logging.info(f"🔴 Reddit Monitor: No relevant rumors found")
        return []


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    print("=" * 60)
    print("🔴 REDDIT MONITOR TEST (Redlib Backend)")
    print("=" * 60)
    print(f"📡 Redlib Instances: {len(REDLIB_INSTANCES)}")
    for inst in REDLIB_INSTANCES:
        print(f"   - {inst}")
    
    # Test leagues
    test_cases = [
        ("soccer_turkey_super_league", ["Galatasaray", "Fenerbahce"]),
        ("soccer_mexico_ligamx", ["Club America", "Chivas"]),
        ("soccer_spl", ["Celtic", "Rangers"]),
    ]
    
    for league_key, teams in test_cases:
        print(f"\n📡 Testing {league_key}...")
        
        subreddits = get_reddit_sources(league_key)
        print(f"   Subreddits: {subreddits}")
        
        if subreddits:
            posts = fetch_subreddit_posts(subreddits[0], limit=10)
            print(f"   Fetched {len(posts)} posts from r/{subreddits[0]}")
            
            if posts:
                relevant = filter_relevant_posts(posts, teams, max_age_hours=48)
                print(f"   Relevant posts: {len(relevant)}")
                
                for r in relevant[:2]:
                    print(f"\n   📌 {r['title'][:60]}...")
                    print(f"      Score: {r['relevance_score']}, Keywords: {r['matched_keywords'][:3]}")
    
    print("\n" + "=" * 60)
    print("✅ Reddit Monitor test complete")
