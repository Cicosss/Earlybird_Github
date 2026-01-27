"""
EarlyBird Discovery Queue - Thread-Safe News Discovery Communication V1.0

This module provides a thread-safe queue for communication between:
- Browser Monitor (producer) - discovers news 24/7
- Main Pipeline (consumer) - processes news for analysis

Replaces the previous dict-based global storage with a proper queue pattern
that provides:
- Thread-safe operations without explicit locking
- Automatic expiration of old discoveries
- Memory-bounded storage with configurable limits
- League-based filtering for efficient retrieval
- Statistics for monitoring

Architecture:
    Browser Monitor ──push()──> DiscoveryQueue ──pop_for_match()──> Main Pipeline
                                     │
                                     └── Automatic TTL expiration
                                     └── Memory limit enforcement

V1.0: Initial implementation replacing _browser_monitor_discoveries dict.
"""
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from threading import Lock, RLock
from typing import Optional, List, Dict, Callable, Any

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MAX_ENTRIES = 1000
DEFAULT_TTL_HOURS = 24


@dataclass
class DiscoveryItem:
    """
    A single news discovery item in the queue.
    
    Attributes:
        uuid: Unique identifier for reliable tracking
        league_key: League this discovery belongs to
        team: Affected team name
        title: News title
        snippet: News snippet/summary
        url: Source URL
        source_name: Name of the source
        category: News category (INJURY, SUSPENSION, etc.)
        confidence: AI confidence score
        discovered_at: When the news was discovered
        data: Full discovery data dict for compatibility
    """
    uuid: str
    league_key: str
    team: str
    title: str
    snippet: str
    url: str
    source_name: str
    category: str
    confidence: float
    discovered_at: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
        """Check if this discovery has expired."""
        now = datetime.now(timezone.utc)
        age = now - self.discovered_at
        return age > timedelta(hours=ttl_hours)
    
    def matches_team(self, team_names: List[str]) -> bool:
        """
        Check if this discovery matches any of the given team names.
        
        Uses case-insensitive substring matching.
        """
        if not self.team or not team_names:
            return False
        
        team_lower = self.team.lower().strip()
        if not team_lower:
            return False
        
        for name in team_names:
            if not name:
                continue
            name_lower = name.lower().strip()
            if not name_lower:
                continue
            # Bidirectional substring match
            if team_lower in name_lower or name_lower in team_lower:
                return True
        
        return False


class DiscoveryQueue:
    """
    Thread-safe queue for news discoveries.
    
    Provides a clean interface for Browser Monitor to push discoveries
    and Main Pipeline to consume them, with automatic expiration and
    memory management.
    
    Thread Safety:
    - All public methods are thread-safe
    - Uses RLock for reentrant locking (allows nested calls)
    - Minimizes lock hold time for better concurrency
    
    Usage:
        queue = DiscoveryQueue()
        
        # Producer (Browser Monitor)
        queue.push(discovery_data, league_key="soccer_epl")
        
        # Consumer (Main Pipeline)
        items = queue.pop_for_match(
            match_id="abc123",
            team_names=["Arsenal", "Chelsea"],
            league_key="soccer_epl"
        )
    """
    
    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_hours: int = DEFAULT_TTL_HOURS
    ):
        """
        Initialize the discovery queue.
        
        Args:
            max_entries: Maximum items to store (oldest evicted first)
            ttl_hours: Hours before items expire
        """
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours
        
        # Main storage: deque for O(1) append/popleft
        self._queue: deque[DiscoveryItem] = deque(maxlen=max_entries)
        
        # Index by league for fast filtering
        self._by_league: Dict[str, List[str]] = {}  # league_key -> [uuids]
        
        # Lock for thread safety (RLock allows reentrant calls)
        self._lock = RLock()
        
        # Statistics
        self._total_pushed = 0
        self._total_popped = 0
        self._total_expired = 0
        self._total_evicted = 0
        
        # V6.0: High-priority callback for event-driven processing
        # When a high-confidence discovery is pushed, this callback is invoked
        # to trigger immediate processing instead of waiting for next cycle
        self._high_priority_callback: Optional[Callable[[str], None]] = None
        self._high_priority_threshold: float = 0.85  # Confidence threshold
        self._high_priority_categories: set = {'INJURY', 'SUSPENSION', 'LINEUP'}
    
    def register_high_priority_callback(
        self,
        callback: Callable[[str], None],
        threshold: float = 0.85,
        categories: Optional[List[str]] = None
    ) -> None:
        """
        Register a callback for high-priority discoveries.
        
        When a discovery with confidence >= threshold AND category in categories
        is pushed, the callback is invoked with the league_key.
        
        This enables event-driven processing: instead of waiting 120 minutes
        for the next cycle, high-priority news triggers immediate analysis.
        
        Args:
            callback: Function to call with league_key when high-priority news arrives
            threshold: Minimum confidence to trigger (default 0.85)
            categories: List of categories to trigger on (default: INJURY, SUSPENSION, LINEUP)
            
        Thread Safety:
            The callback is invoked OUTSIDE the lock to prevent deadlocks.
            The callback should be thread-safe and non-blocking.
        """
        self._high_priority_callback = callback
        self._high_priority_threshold = threshold
        if categories:
            self._high_priority_categories = set(categories)
        logger.info(f"📢 [QUEUE] High-priority callback registered (threshold={threshold}, categories={self._high_priority_categories})")
    
    def push(
        self,
        data: Dict[str, Any],
        league_key: str,
        team: Optional[str] = None,
        title: Optional[str] = None,
        snippet: Optional[str] = None,
        url: Optional[str] = None,
        source_name: Optional[str] = None,
        category: str = "OTHER",
        confidence: float = 0.0
    ) -> str:
        """
        Push a new discovery to the queue.
        
        Args:
            data: Full discovery data dict (for compatibility)
            league_key: League identifier
            team: Affected team name
            title: News title
            snippet: News snippet
            url: Source URL
            source_name: Source name
            category: News category
            confidence: AI confidence score
            
        Returns:
            UUID of the pushed item
        """
        item_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Extract fields from data if not provided explicitly
        team = team or data.get('team') or data.get('affected_team') or ''
        title = title or data.get('title') or ''
        snippet = snippet or data.get('snippet') or ''
        url = url or data.get('link') or data.get('url') or ''
        source_name = source_name or data.get('source') or data.get('source_name') or ''
        category = category or data.get('category') or 'OTHER'
        confidence = confidence or data.get('confidence') or data.get('gemini_confidence') or 0.0
        
        # V7.1 FIX: Ensure confidence is float with proper string mapping
        if isinstance(confidence, str):
            # Map string confidence levels to numeric values
            confidence_map = {
                'HIGH': 0.85,
                'MEDIUM': 0.65,
                'LOW': 0.4,
                'VERY_HIGH': 0.95,
            }
            confidence_upper = confidence.upper().strip()
            if confidence_upper in confidence_map:
                confidence = confidence_map[confidence_upper]
            else:
                # Try to parse as float (e.g., "0.8")
                try:
                    confidence = float(confidence)
                except ValueError:
                    confidence = 0.5  # Safe default
        
        item = DiscoveryItem(
            uuid=item_uuid,
            league_key=league_key,
            team=team,
            title=title,
            snippet=snippet,
            url=url,
            source_name=source_name,
            category=category,
            confidence=confidence,
            discovered_at=now,
            data=data
        )
        
        with self._lock:
            # Check if we need to evict (deque handles this, but we track stats)
            if len(self._queue) >= self._max_entries:
                self._total_evicted += 1
                # Remove oldest from league index
                oldest = self._queue[0]
                if oldest.league_key in self._by_league:
                    try:
                        self._by_league[oldest.league_key].remove(oldest.uuid)
                    except ValueError:
                        pass
            
            # Add to queue
            self._queue.append(item)
            
            # Update league index
            if league_key not in self._by_league:
                self._by_league[league_key] = []
            self._by_league[league_key].append(item_uuid)
            
            self._total_pushed += 1
            
            # V6.0: Check if this is a high-priority discovery
            # Store values needed for callback BEFORE releasing lock
            should_trigger = (
                self._high_priority_callback is not None and
                confidence >= self._high_priority_threshold and
                category in self._high_priority_categories
            )
            callback_ref = self._high_priority_callback if should_trigger else None
        
        # V6.0: Invoke callback OUTSIDE lock to prevent deadlocks
        if callback_ref is not None:
            try:
                logger.info(f"🚨 [QUEUE] High-priority discovery! Triggering callback for {league_key} (conf={confidence:.2f}, cat={category})")
                callback_ref(league_key)
            except Exception as e:
                logger.warning(f"⚠️ [QUEUE] High-priority callback failed: {e}")
        
        logger.debug(f"📥 [QUEUE] Pushed discovery: {title[:50] if title else 'No title'} for {team}")
        return item_uuid
    
    def pop_for_match(
        self,
        match_id: str,
        team_names: List[str],
        league_key: str
    ) -> List[Dict[str, Any]]:
        """
        Get all discoveries matching a match's teams.
        
        This is the main consumer method. It:
        1. Filters by league
        2. Filters by team name match
        3. Removes expired items
        4. Returns matching items with match_id attached
        
        Items are NOT removed from queue (they may match multiple matches).
        Use cleanup_expired() periodically to remove old items.
        
        Args:
            match_id: Match ID to attach to results
            team_names: List of team names to match against
            league_key: League to filter by
            
        Returns:
            List of discovery dicts with match_id attached
        """
        if not team_names:
            return []
        
        results = []
        now = datetime.now(timezone.utc)
        
        with self._lock:
            # Get UUIDs for this league
            league_uuids = set(self._by_league.get(league_key, []))
            
            if not league_uuids:
                return []
            
            # Find matching items
            for item in self._queue:
                if item.uuid not in league_uuids:
                    continue
                
                # Skip expired
                if item.is_expired(self._ttl_hours):
                    continue
                
                # Check team match
                if not item.matches_team(team_names):
                    continue
                
                # Build result dict (compatible with existing code)
                result = item.data.copy()
                result['match_id'] = match_id
                result['_uuid'] = item.uuid
                
                # Ensure core fields are present (may not be in data dict)
                result['team'] = item.team
                result['title'] = item.title
                result['snippet'] = item.snippet
                result['link'] = item.url
                result['url'] = item.url
                result['source'] = item.source_name
                result['category'] = item.category
                result['confidence'] = item.confidence
                result['discovered_at'] = item.discovered_at.isoformat()
                
                # Recalculate freshness at retrieval time
                minutes_old = int((now - item.discovered_at).total_seconds() / 60)
                result['minutes_old'] = minutes_old
                
                # Import freshness function
                try:
                    from src.utils.freshness import get_freshness_tag
                    result['freshness_tag'] = get_freshness_tag(minutes_old)
                except ImportError:
                    # Fallback
                    if minutes_old < 60:
                        result['freshness_tag'] = "🔥 FRESH"
                    elif minutes_old < 360:
                        result['freshness_tag'] = "⏰ AGING"
                    else:
                        result['freshness_tag'] = "📜 STALE"
                
                results.append(result)
                self._total_popped += 1
        
        if results:
            logger.info(f"📤 [QUEUE] Retrieved {len(results)} discoveries for {team_names[0] if team_names else 'unknown'}")
        
        return results
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired items from the queue.
        
        Should be called periodically (e.g., every hour or at pipeline start).
        
        Returns:
            Number of items removed
        """
        removed = 0
        
        with self._lock:
            # Build list of non-expired items
            valid_items = []
            valid_uuids_by_league: Dict[str, List[str]] = {}
            
            for item in self._queue:
                if item.is_expired(self._ttl_hours):
                    removed += 1
                    self._total_expired += 1
                else:
                    valid_items.append(item)
                    if item.league_key not in valid_uuids_by_league:
                        valid_uuids_by_league[item.league_key] = []
                    valid_uuids_by_league[item.league_key].append(item.uuid)
            
            # Replace queue contents
            self._queue.clear()
            self._queue.extend(valid_items)
            
            # Update league index
            self._by_league = valid_uuids_by_league
        
        if removed > 0:
            logger.info(f"🧹 [QUEUE] Cleaned up {removed} expired discoveries")
        
        return removed
    
    def clear(self, league_key: Optional[str] = None) -> int:
        """
        Clear items from the queue.
        
        Args:
            league_key: If provided, only clear items for this league.
                       If None, clear all items.
                       
        Returns:
            Number of items cleared
        """
        with self._lock:
            if league_key is None:
                count = len(self._queue)
                self._queue.clear()
                self._by_league.clear()
                return count
            
            # Clear only specific league
            uuids_to_remove = set(self._by_league.get(league_key, []))
            if not uuids_to_remove:
                return 0
            
            # Filter queue
            remaining = [item for item in self._queue if item.uuid not in uuids_to_remove]
            count = len(self._queue) - len(remaining)
            
            self._queue.clear()
            self._queue.extend(remaining)
            
            # Update league index
            if league_key in self._by_league:
                del self._by_league[league_key]
            
            return count
    
    def size(self, league_key: Optional[str] = None) -> int:
        """
        Get current queue size.
        
        Args:
            league_key: If provided, count only items for this league.
            
        Returns:
            Number of items in queue
        """
        with self._lock:
            if league_key is None:
                return len(self._queue)
            return len(self._by_league.get(league_key, []))
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics for monitoring.
        
        Returns:
            Dict with queue stats
        """
        with self._lock:
            # Calculate oldest item age
            oldest_age_hours = 0.0
            now = datetime.now(timezone.utc)
            
            if self._queue:
                oldest = self._queue[0]
                oldest_age_hours = (now - oldest.discovered_at).total_seconds() / 3600
            
            return {
                'current_size': len(self._queue),
                'max_entries': self._max_entries,
                'ttl_hours': self._ttl_hours,
                'leagues_count': len(self._by_league),
                'by_league': {k: len(v) for k, v in self._by_league.items()},
                'oldest_age_hours': round(oldest_age_hours, 1),
                'total_pushed': self._total_pushed,
                'total_popped': self._total_popped,
                'total_expired': self._total_expired,
                'total_evicted': self._total_evicted
            }


# ============================================
# SINGLETON INSTANCE
# ============================================
# Global queue instance for cross-module communication

_discovery_queue: Optional[DiscoveryQueue] = None
_queue_lock = Lock()


def get_discovery_queue() -> DiscoveryQueue:
    """
    Get the global discovery queue instance (thread-safe singleton).
    
    Returns:
        The global DiscoveryQueue instance
    """
    global _discovery_queue
    
    if _discovery_queue is None:
        with _queue_lock:
            # Double-check locking
            if _discovery_queue is None:
                _discovery_queue = DiscoveryQueue()
                logger.info("📦 [QUEUE] Global discovery queue initialized")
    
    return _discovery_queue


def reset_discovery_queue() -> None:
    """
    Reset the global discovery queue (for testing).
    """
    global _discovery_queue
    with _queue_lock:
        _discovery_queue = None
