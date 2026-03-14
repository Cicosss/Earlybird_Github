"""
URL Normalizer - Intelligent Deduplication for News Items

Prevents duplicate news from being counted multiple times by:
1. Normalizing URLs (removing tracking params, fragments, etc.)
2. Content-based hashing (title + key phrases)
3. Fuzzy matching for similar articles from different sources

V1.0 - Initial implementation for Deep Research improvements
V2.0 - Thread-safe, memory-bounded, TTL-aware implementation (COVE fixes)
"""

import hashlib
import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Default configuration (consistent with ContentCache)
DEFAULT_MAX_ENTRIES = 10000
DEFAULT_TTL_HOURS = 24

# ============================================
# URL NORMALIZATION
# ============================================

# Tracking parameters to remove (common across news sites)
TRACKING_PARAMS = {
    # UTM parameters
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    # Social media
    "fbclid",
    "gclid",
    "twclid",
    "igshid",
    # Analytics
    "ref",
    "source",
    "via",
    "from",
    # News site specific
    "ncid",
    "ocid",
    "cmpid",
    "partner",
    # Mobile
    "amp",
    "_amp",
}


def normalize_url(url: str) -> str:
    """
    Normalize URL by removing tracking parameters and fragments.

    This ensures that the same article with different tracking params
    is recognized as the same URL.

    Examples:
        https://example.com/article?utm_source=twitter → https://example.com/article
        https://example.com/article#comments → https://example.com/article
        https://example.com/article?id=123&utm_source=fb → https://example.com/article?id=123

    Args:
        url: Original URL

    Returns:
        Normalized URL without tracking params and fragments
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url.strip())

        # Remove fragment (#comments, #section, etc.)
        # Keep query params that are NOT tracking
        query_params = parse_qs(parsed.query, keep_blank_values=False)

        # Filter out tracking parameters
        clean_params = {k: v for k, v in query_params.items() if k.lower() not in TRACKING_PARAMS}

        # Rebuild query string (sorted for consistency)
        clean_query = urlencode(clean_params, doseq=True) if clean_params else ""

        # Rebuild URL without fragment
        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc.lower(),  # Lowercase domain
                parsed.path.rstrip("/"),  # Remove trailing slash
                parsed.params,
                clean_query,
                "",  # No fragment
            )
        )

        return normalized

    except Exception as e:
        logger.debug(f"URL normalization failed for {url}: {e}")
        return url


def get_url_hash(url: str) -> str:
    """
    Get hash of normalized URL for deduplication.

    V2.0 COVE FIX: Returns empty string for None/empty URLs to prevent
    false positives (all None/empty URLs would otherwise have the same hash).

    Args:
        url: URL to hash

    Returns:
        16-char hash of normalized URL, or empty string if url is None/empty
    """
    if not url:
        return ""

    normalized = normalize_url(url)
    if not normalized:
        return ""

    return hashlib.md5(normalized.encode()).hexdigest()[:16]


# ============================================
# CONTENT-BASED DEDUPLICATION
# ============================================


def extract_content_signature(title: str, snippet: str = "") -> str:
    """
    Extract a content signature for fuzzy deduplication.

    This helps detect when the same news is reported by different sources
    with different URLs but similar content.

    Strategy:
    - Extract key entities (names, teams, numbers)
    - Normalize text (lowercase, remove punctuation)
    - Create hash of key content

    Args:
        title: Article title
        snippet: Article snippet/description

    Returns:
        Content signature hash
    """
    if not title:
        return ""

    # Combine title and first part of snippet
    text = f"{title} {snippet[:200] if snippet else ''}".lower()

    # Remove common words and punctuation
    text = re.sub(r"[^\w\s]", " ", text)

    # Extract potential key entities (capitalized words, numbers)
    # These are likely player names, team names, scores
    words = text.split()

    # Keep only significant words (length > 3, not common)
    common_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "will",
        "have",
        "been",
        "were",
        "are",
        "was",
        "has",
        "had",
        "but",
        "not",
        "they",
        "their",
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "all",
        "news",
        "update",
        "latest",
        "breaking",
        "report",
        "says",
        "said",
        "injury",
        "injured",
        "team",
        "match",
        "game",
        "player",
        "players",
    }

    key_words = [w for w in words if len(w) > 3 and w not in common_words]

    # Sort for consistency and take first 10
    key_words = sorted(set(key_words))[:10]

    # Create signature
    signature = " ".join(key_words)

    return hashlib.md5(signature.encode()).hexdigest()[:12]


def are_articles_similar(
    title1: str, title2: str, snippet1: str = "", snippet2: str = "", threshold: float = 0.4
) -> bool:
    """
    Check if two articles are likely about the same news.

    Uses multiple strategies:
    1. Key entity overlap (names, teams - case insensitive)
    2. Word overlap with low threshold
    3. Substring matching for key terms

    Args:
        title1, title2: Article titles
        snippet1, snippet2: Article snippets
        threshold: Similarity threshold (0-1)

    Returns:
        True if articles are likely duplicates
    """
    if not title1 or not title2:
        return False

    t1_lower = title1.lower()
    t2_lower = title2.lower()

    # Strategy 1: Extract key entities (words > 4 chars, likely names/teams)
    def extract_key_words(text: str) -> set[str]:
        if not text:
            return set()
        # Split and filter
        words = text.lower().split()
        # Keep words > 4 chars that aren't common
        stop_words = {
            "with",
            "from",
            "that",
            "this",
            "will",
            "have",
            "been",
            "were",
            "their",
            "about",
            "after",
            "before",
            "could",
            "would",
            "should",
            "injury",
            "injured",
            "ruled",
            "sidelined",
            "problem",
            "issue",
            "player",
            "star",
            "team",
            "match",
            "game",
            "news",
            "update",
        }
        return set(w for w in words if len(w) > 4 and w not in stop_words)

    words1 = extract_key_words(t1_lower)
    words2 = extract_key_words(t2_lower)

    if words1 and words2:
        # Check for key entity overlap
        common = words1 & words2
        if len(common) >= 1:
            # At least one significant word in common (likely team/player name)
            return True

    # Strategy 2: Check if key proper nouns appear in both
    # Extract capitalized words from original (before lowercasing)
    def get_proper_nouns(text: str) -> set[str]:
        # Find sequences of capitalized words (team names, player names)
        matches = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        return set(m.lower() for m in matches if len(m) > 3)

    nouns1 = get_proper_nouns(title1)
    nouns2 = get_proper_nouns(title2)

    if nouns1 and nouns2:
        common_nouns = nouns1 & nouns2
        if common_nouns:
            return True

    # Strategy 3: Simple word overlap ratio
    all_words1 = set(t1_lower.split())
    all_words2 = set(t2_lower.split())

    if all_words1 and all_words2:
        intersection = len(all_words1 & all_words2)
        smaller_set = min(len(all_words1), len(all_words2))

        # If more than 40% of smaller title's words appear in larger
        if smaller_set > 0 and intersection / smaller_set >= threshold:
            return True

    return False


# ============================================
# INTELLIGENT DEDUPLICATION CACHE
# ============================================


class NewsDeduplicator:
    """
    Intelligent news deduplication with multiple strategies.

    V2.0 COVE FIXES:
    - Thread-safe: Uses threading.RLock for all operations
    - Memory-bounded: LRU eviction with max_entries
    - TTL-aware: Entries expire after ttl_hours
    - Safe error handling: Properly handles None/empty values

    Strategies:
    1. URL-based: Normalized URL hash
    2. Content-based: Title/snippet signature
    3. Source-aware: Same news from different sources
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_hours: int = DEFAULT_TTL_HOURS):
        """
        Initialize the deduplicator.

        Args:
            max_entries: Maximum entries before LRU eviction
            ttl_hours: Hours before entries expire
        """
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours

        # URL cache: url_hash -> timestamp
        self._seen_urls: "OrderedDict[str, datetime]" = OrderedDict()

        # Content cache: content_sig -> timestamp
        self._seen_content: "OrderedDict[str, datetime]" = OrderedDict()

        # URL to content mapping: url_hash -> content_sig
        self._url_to_content: "dict[str, str]" = {}

        # Thread-safe lock (RLock allows reentrant calls)
        self._lock = threading.RLock()

        # Statistics
        self._stats = {
            "checked": 0,
            "duplicates": 0,
            "added": 0,
            "expired": 0,
            "evicted": 0,
        }

    def is_duplicate(
        self, url: str, title: str, snippet: str = "", check_content: bool = True
    ) -> tuple[bool, str]:
        """
        Check if news item is a duplicate.

        V2.0 COVE FIX: Thread-safe, checks TTL on every access.

        Args:
            url: Article URL
            title: Article title
            snippet: Article snippet
            check_content: Whether to also check content similarity

        Returns:
            Tuple of (is_duplicate, reason)
        """
        with self._lock:
            self._stats["checked"] += 1

            # Strategy 1: URL-based deduplication
            url_hash = get_url_hash(url)

            if url_hash and url_hash in self._seen_urls:
                # Check if expired
                timestamp = self._seen_urls[url_hash]
                if datetime.now(timezone.utc) - timestamp > timedelta(hours=self._ttl_hours):
                    # Expired, remove it
                    del self._seen_urls[url_hash]
                    self._stats["expired"] += 1
                else:
                    # Valid duplicate
                    self._stats["duplicates"] += 1
                    # Move to end (LRU)
                    self._seen_urls.move_to_end(url_hash)
                    return True, "duplicate_url"

            # Strategy 2: Content-based deduplication
            if check_content and title:
                content_sig = extract_content_signature(title, snippet)

                if content_sig and content_sig in self._seen_content:
                    # Check if expired
                    timestamp = self._seen_content[content_sig]
                    if datetime.now(timezone.utc) - timestamp > timedelta(hours=self._ttl_hours):
                        # Expired, remove it
                        del self._seen_content[content_sig]
                        self._stats["expired"] += 1
                    else:
                        # Valid duplicate
                        self._stats["duplicates"] += 1
                        # Move to end (LRU)
                        self._seen_content.move_to_end(content_sig)
                        return True, "duplicate_content"

            return False, ""

    def mark_seen(self, url: str, title: str, snippet: str = ""):
        """
        Mark a news item as seen.

        V2.0 COVE FIX: Thread-safe, enforces max_entries with LRU eviction.

        Args:
            url: Article URL
            title: Article title
            snippet: Article snippet
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            url_hash = get_url_hash(url)

            if url_hash:
                self._seen_urls[url_hash] = now

                if title:
                    content_sig = extract_content_signature(title, snippet)
                    if content_sig:
                        self._seen_content[content_sig] = now
                        self._url_to_content[url_hash] = content_sig

                self._stats["added"] += 1

                # Enforce max_entries (LRU eviction)
                self._evict_if_needed()

    def _evict_if_needed(self):
        """
        Evict oldest entries if at capacity.

        V2.0 COVE FIX: Thread-safe LRU eviction.
        """
        # Evict URLs if at capacity
        while len(self._seen_urls) >= self._max_entries:
            self._seen_urls.popitem(last=False)
            self._stats["evicted"] += 1

        # Evict content if at capacity
        while len(self._seen_content) >= self._max_entries:
            self._seen_content.popitem(last=False)
            self._stats["evicted"] += 1

    def clear(self):
        """
        Clear all caches.

        V2.0 COVE FIX: Thread-safe.
        """
        with self._lock:
            self._seen_urls.clear()
            self._seen_content.clear()
            self._url_to_content.clear()

    def get_stats(self) -> dict[str, int]:
        """
        Get deduplication statistics.

        V2.0 COVE FIX: Includes additional statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "unique_urls": len(self._seen_urls),
                "unique_content": len(self._seen_content),
                **self._stats,
            }


# ============================================
# SINGLETON INSTANCE
# ============================================
_deduplicator: "NewsDeduplicator | None" = None
_deduplicator_lock = threading.Lock()


def get_deduplicator() -> "NewsDeduplicator":
    """
    Get singleton deduplicator instance.

    V2.0 COVE FIX: Thread-safe singleton pattern with lock.
    """
    global _deduplicator
    if _deduplicator is None:
        with _deduplicator_lock:
            # Double-checked locking pattern
            if _deduplicator is None:
                _deduplicator = NewsDeduplicator()
    return _deduplicator


# ============================================
# CLI for testing
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("🔍 URL NORMALIZER TEST")
    print("=" * 60)

    # Test URL normalization
    test_urls = [
        "https://aleagues.com.au/news/ins-outs-round-10/",
        "https://aleagues.com.au/news/ins-outs-round-10/?utm_source=twitter",
        "https://aleagues.com.au/news/ins-outs-round-10/#comments",
        "https://ALEAGUES.COM.AU/news/ins-outs-round-10",
    ]

    print("\n📎 URL Normalization:")
    for url in test_urls:
        normalized = normalize_url(url)
        print(f"  {url[:50]}...")
        print(f"    → {normalized}")

    # Test content signature
    print("\n📝 Content Signature:")
    titles = [
        "Sydney FC star ruled out with hamstring injury",
        "Sydney FC player sidelined due to hamstring problem",
        "Melbourne Victory signs new striker from Europe",
    ]

    for title in titles:
        sig = extract_content_signature(title)
        print(f"  {title[:40]}... → {sig}")

    # Test similarity
    print("\n🔄 Similarity Check:")
    print(f"  Similar: {are_articles_similar(titles[0], titles[1])}")
    print(f"  Different: {are_articles_similar(titles[0], titles[2])}")
