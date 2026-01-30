"""
EarlyBird Shared Cache - Cross-Component Deduplication V1.0

This module provides a shared content cache for deduplication across:
- Main Pipeline (main.py)
- News Radar (news_radar.py)
- Browser Monitor (browser_monitor.py)

The shared cache prevents duplicate alerts when the same news is discovered
by multiple components (e.g., News Radar finds news, then Browser Monitor
finds the same news on a different source).

Architecture:
    News Radar ──────┐
                     │
    Browser Monitor ─┼──> SharedContentCache ──> Deduplication
                     │
    Main Pipeline ───┘

Features:
- Thread-safe operations
- Content hash-based deduplication (first 1000 chars)
- URL-based deduplication (normalized)
- TTL-based expiration
- LRU eviction when at capacity
- Cross-component statistics

V1.0: Initial implementation for unified deduplication.

Phase 1 Critical Fix: Added Unicode normalization for consistent text handling
"""
import hashlib
import logging
import re
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Optional, Dict, Tuple, Set, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger(__name__)


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode to NFC form for consistent text handling.
    
    Phase 1 Critical Fix: Ensures special characters from Turkish, Polish,
    Greek, Arabic, Chinese, Japanese, Korean, and other languages
    are handled consistently across all components.
    
    Args:
        text: Input text to normalize
        
    Returns:
        Normalized text in NFC form
    """
    if not text:
        return ""
    return unicodedata.normalize('NFC', text)

# Configuration
DEFAULT_MAX_ENTRIES = 10000
DEFAULT_TTL_HOURS = 24


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    
    Removes tracking parameters, normalizes case, removes fragments.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL string
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url.lower().strip())
        
        # Remove common tracking parameters
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'ref', 'source', 'mc_cid', 'mc_eid',
            '_ga', '_gl', 'hsCtaTracking', 'mkt_tok'
        }
        
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        filtered_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in tracking_params
        }
        
        # Rebuild URL without tracking params and fragment
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),  # Remove trailing slash
            parsed.params,
            urlencode(filtered_params, doseq=True) if filtered_params else '',
            ''  # Remove fragment
        ))
        
        return normalized
        
    except Exception as e:
        logger.debug(f"URL normalization failed for '{url}': {e}")
        return url.lower().strip()


def compute_content_hash(content: str, prefix_length: int = 1000) -> str:
    """
    Compute hash from content prefix.
    
    Uses first N characters to handle minor variations in article endings.
    
    Args:
        content: Text content to hash
        prefix_length: Number of characters to use (default 1000)
        
    Returns:
        16-character hex hash
    """
    if not content:
        return ""
    
    # Normalize whitespace for consistent hashing
    normalized = ' '.join(content.split())
    prefix = normalized[:prefix_length]
    
    return hashlib.sha256(prefix.encode('utf-8', errors='ignore')).hexdigest()[:16]


def compute_simhash(content: str, hash_bits: int = 64) -> int:
    """
    V7.3: Compute simhash for fuzzy content matching.
    
    Simhash generates similar hashes for similar content, allowing
    detection of "almost identical" articles from different sources.
    
    Algorithm:
    1. Tokenize content into words
    2. Hash each word
    3. For each bit position, sum +1 if bit is 1, -1 if bit is 0
    4. Final hash: bit is 1 if sum > 0, else 0
    
    Args:
        content: Text content to hash
        hash_bits: Number of bits in hash (default 64)
        
    Returns:
        Integer simhash value
    """
    if not content:
        return 0
    
    # Normalize and tokenize
    content_lower = content.lower()
    # Remove punctuation and split into words
    words = re.findall(r'\b\w{3,}\b', content_lower)  # Words with 3+ chars
    
    if not words:
        return 0
    
    # Initialize bit sums
    bit_sums = [0] * hash_bits
    
    for word in words:
        # Hash the word
        word_hash = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
        
        # Update bit sums
        for i in range(hash_bits):
            if word_hash & (1 << i):
                bit_sums[i] += 1
            else:
                bit_sums[i] -= 1
    
    # Build final hash
    simhash = 0
    for i in range(hash_bits):
        if bit_sums[i] > 0:
            simhash |= (1 << i)
    
    return simhash


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Compute Hamming distance between two hashes.
    
    Hamming distance = number of differing bits.
    Lower distance = more similar content.
    
    Args:
        hash1: First hash
        hash2: Second hash
        
    Returns:
        Number of differing bits
    """
    xor = hash1 ^ hash2
    distance = 0
    while xor:
        distance += xor & 1
        xor >>= 1
    return distance


class SharedContentCache:
    """
    Thread-safe content cache for cross-component deduplication.
    
    Provides three deduplication strategies:
    1. Content hash: Based on first 1000 chars of content (exact match)
    2. URL: Based on normalized URL
    3. Simhash: Fuzzy matching for "almost identical" content (V7.3)
    
    Content is considered duplicate if ANY strategy matches.
    
    Usage:
        cache = SharedContentCache()
        
        # Check if content is duplicate
        if cache.is_duplicate(content="...", url="..."):
            return  # Skip duplicate
        
        # Mark as seen
        cache.mark_seen(content="...", url="...", source="news_radar")
    """
    
    # V7.3: Simhash similarity threshold (max Hamming distance for "similar")
    # 3 bits difference in 64-bit hash ≈ 95% similar content
    SIMHASH_THRESHOLD = 3
    
    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        enable_fuzzy: bool = True
    ):
        """
        Initialize the shared cache.
        
        Args:
            max_entries: Maximum entries before LRU eviction
            ttl_hours: Hours before entries expire
            enable_fuzzy: Enable simhash fuzzy matching (V7.3)
        """
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours
        self._enable_fuzzy = enable_fuzzy
        
        # Content hash cache: hash -> (timestamp, source)
        self._content_cache: OrderedDict[str, Tuple[datetime, str]] = OrderedDict()
        
        # URL cache: normalized_url -> (timestamp, source)
        self._url_cache: OrderedDict[str, Tuple[datetime, str]] = OrderedDict()
        
        # V7.3: Simhash cache for fuzzy matching: simhash -> (timestamp, source, content_preview)
        self._simhash_cache: OrderedDict[int, Tuple[datetime, str, str]] = OrderedDict()
        
        # Lock for thread safety
        self._lock = RLock()
        
        # Statistics by source
        self._stats: Dict[str, Dict[str, int]] = {
            'news_radar': {'checked': 0, 'duplicates': 0, 'added': 0, 'fuzzy_matches': 0},
            'browser_monitor': {'checked': 0, 'duplicates': 0, 'added': 0, 'fuzzy_matches': 0},
            'main_pipeline': {'checked': 0, 'duplicates': 0, 'added': 0, 'fuzzy_matches': 0},
            'unknown': {'checked': 0, 'duplicates': 0, 'added': 0, 'fuzzy_matches': 0}
        }
    
    def is_duplicate(
        self,
        content: Optional[str] = None,
        url: Optional[str] = None,
        source: str = "unknown"
    ) -> bool:
        """
        Check if content or URL is a duplicate.
        
        Returns True if ANY of:
        - Content hash matches a cached entry (not expired)
        - Normalized URL matches a cached entry (not expired)
        - V7.3: Simhash is within threshold of a cached entry (fuzzy match)
        
        Args:
            content: Text content to check (optional)
            url: URL to check (optional)
            source: Source component for statistics
            
        Returns:
            True if duplicate, False otherwise
        """
        if not content and not url:
            return False
        
        # Normalize source for stats
        if source not in self._stats:
            source = 'unknown'
        
        with self._lock:
            self._stats[source]['checked'] += 1
            now = datetime.now(timezone.utc)
            
            # Check content hash (exact match)
            if content:
                content_hash = compute_content_hash(content)
                if content_hash and content_hash in self._content_cache:
                    cached_time, cached_source = self._content_cache[content_hash]
                    if now - cached_time <= timedelta(hours=self._ttl_hours):
                        # Move to end (LRU)
                        self._content_cache.move_to_end(content_hash)
                        self._stats[source]['duplicates'] += 1
                        logger.debug(f"🔄 [SHARED-CACHE] Content duplicate detected (original: {cached_source})")
                        return True
                    else:
                        # Expired, remove it
                        del self._content_cache[content_hash]
            
            # Check URL
            if url:
                normalized_url = normalize_url(url)
                if normalized_url and normalized_url in self._url_cache:
                    cached_time, cached_source = self._url_cache[normalized_url]
                    if now - cached_time <= timedelta(hours=self._ttl_hours):
                        # Move to end (LRU)
                        self._url_cache.move_to_end(normalized_url)
                        self._stats[source]['duplicates'] += 1
                        logger.debug(f"🔄 [SHARED-CACHE] URL duplicate detected (original: {cached_source})")
                        return True
                    else:
                        # Expired, remove it
                        del self._url_cache[normalized_url]
            
            # V7.3: Check simhash (fuzzy match)
            if content and self._enable_fuzzy:
                content_simhash = compute_simhash(content)
                if content_simhash:
                    for cached_simhash, (cached_time, cached_source, preview) in list(self._simhash_cache.items()):
                        # Check expiration
                        if now - cached_time > timedelta(hours=self._ttl_hours):
                            del self._simhash_cache[cached_simhash]
                            continue
                        
                        # Check similarity
                        distance = hamming_distance(content_simhash, cached_simhash)
                        if distance <= self.SIMHASH_THRESHOLD:
                            self._simhash_cache.move_to_end(cached_simhash)
                            self._stats[source]['duplicates'] += 1
                            self._stats[source]['fuzzy_matches'] += 1
                            logger.debug(
                                f"🔄 [SHARED-CACHE] Fuzzy duplicate detected "
                                f"(distance={distance}, original: {cached_source})"
                            )
                            return True
            
            return False
    
    def mark_seen(
        self,
        content: Optional[str] = None,
        url: Optional[str] = None,
        source: str = "unknown"
    ) -> None:
        """
        Mark content and/or URL as seen.
        
        Should be called after processing content that passed is_duplicate().
        V7.3: Also stores simhash for fuzzy matching.
        
        Args:
            content: Text content to mark
            url: URL to mark
            source: Source component for statistics
        """
        if not content and not url:
            return
        
        # Normalize source for stats
        if source not in self._stats:
            source = 'unknown'
        
        with self._lock:
            now = datetime.now(timezone.utc)
            
            # Add content hash
            if content:
                content_hash = compute_content_hash(content)
                if content_hash:
                    # Evict oldest if at capacity
                    while len(self._content_cache) >= self._max_entries // 3:
                        self._content_cache.popitem(last=False)
                    
                    self._content_cache[content_hash] = (now, source)
                
                # V7.3: Add simhash for fuzzy matching
                if self._enable_fuzzy:
                    content_simhash = compute_simhash(content)
                    if content_simhash:
                        # Evict oldest if at capacity
                        while len(self._simhash_cache) >= self._max_entries // 3:
                            self._simhash_cache.popitem(last=False)
                        
                        # Store with content preview for debugging
                        preview = content[:100] if content else ""
                        self._simhash_cache[content_simhash] = (now, source, preview)
            
            # Add URL
            if url:
                normalized_url = normalize_url(url)
                if normalized_url:
                    # Evict oldest if at capacity
                    while len(self._url_cache) >= self._max_entries // 3:
                        self._url_cache.popitem(last=False)
                    
                    self._url_cache[normalized_url] = (now, source)
            
            self._stats[source]['added'] += 1
    
    def check_and_mark(
        self,
        content: Optional[str] = None,
        url: Optional[str] = None,
        source: str = "unknown"
    ) -> bool:
        """
        Atomic check-and-mark operation.
        
        If not duplicate, marks as seen and returns False.
        If duplicate, returns True without marking.
        
        This is the recommended method for most use cases.
        
        Args:
            content: Text content
            url: URL
            source: Source component
            
        Returns:
            True if duplicate (skip processing), False if new (proceed)
        """
        # Check if duplicate first (is_duplicate acquires its own lock)
        if self.is_duplicate(content, url, source):
            return True
        
        # Mark as seen (mark_seen acquires its own lock)
        self.mark_seen(content, url, source)
        return False
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Should be called periodically (e.g., hourly).
        
        Returns:
            Number of entries removed
        """
        removed = 0
        now = datetime.now(timezone.utc)
        
        with self._lock:
            # Clean content cache
            expired_content = [
                h for h, (ts, _) in self._content_cache.items()
                if now - ts > timedelta(hours=self._ttl_hours)
            ]
            for h in expired_content:
                del self._content_cache[h]
                removed += 1
            
            # Clean URL cache
            expired_urls = [
                u for u, (ts, _) in self._url_cache.items()
                if now - ts > timedelta(hours=self._ttl_hours)
            ]
            for u in expired_urls:
                del self._url_cache[u]
                removed += 1
            
            # V7.3: Clean simhash cache
            expired_simhash = [
                sh for sh, (ts, _, _) in self._simhash_cache.items()
                if now - ts > timedelta(hours=self._ttl_hours)
            ]
            for sh in expired_simhash:
                del self._simhash_cache[sh]
                removed += 1
        
        if removed > 0:
            logger.info(f"🧹 [SHARED-CACHE] Cleaned up {removed} expired entries")
        
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats by source
        """
        with self._lock:
            return {
                'content_cache_size': len(self._content_cache),
                'url_cache_size': len(self._url_cache),
                'simhash_cache_size': len(self._simhash_cache),  # V7.3
                'fuzzy_enabled': self._enable_fuzzy,  # V7.3
                'max_entries': self._max_entries,
                'ttl_hours': self._ttl_hours,
                'by_source': dict(self._stats)
            }
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._content_cache.clear()
            self._url_cache.clear()
            self._simhash_cache.clear()  # V7.3
    
    def size(self) -> int:
        """Get total cache size (content + URL + simhash entries)."""
        with self._lock:
            return len(self._content_cache) + len(self._url_cache) + len(self._simhash_cache)


# ============================================
# SINGLETON INSTANCE
# ============================================

_shared_cache: Optional[SharedContentCache] = None
_cache_lock = RLock()


def get_shared_cache() -> SharedContentCache:
    """
    Get the global shared cache instance (thread-safe singleton).
    
    Returns:
        The global SharedContentCache instance
    """
    global _shared_cache
    
    if _shared_cache is None:
        with _cache_lock:
            if _shared_cache is None:
                _shared_cache = SharedContentCache()
                logger.info("📦 [SHARED-CACHE] Global shared cache initialized")
    
    return _shared_cache


def reset_shared_cache() -> None:
    """Reset the global shared cache (for testing)."""
    global _shared_cache
    with _cache_lock:
        _shared_cache = None
