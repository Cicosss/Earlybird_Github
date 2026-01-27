"""
EarlyBird Radar Cross-Source Validator V1.0

Aggrega alert da fonti multiple per aumentare la confidence.

Logica:
- Alert da 1 fonte = confidence originale
- Alert confermato da 2+ fonti entro 15 min = confidence boost (+15%)
- Alert confermato da 3+ fonti = HIGH confidence override

Questo riduce i falsi positivi e aumenta la qualità degli alert.

V1.0: Initial implementation
"""
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from threading import RLock
from collections import defaultdict

logger = logging.getLogger(__name__)

# Configuration
AGGREGATION_WINDOW_MINUTES = 15    # Window to aggregate alerts
CONFIDENCE_BOOST_2_SOURCES = 0.15  # +15% for 2 sources
CONFIDENCE_BOOST_3_SOURCES = 0.25  # +25% for 3+ sources
MAX_CONFIDENCE = 0.95              # Cap confidence at 95%
CACHE_TTL_MINUTES = 60             # Keep entries for 1 hour


@dataclass
class PendingAlert:
    """
    Alert waiting for cross-source validation.
    
    Attributes:
        team: Affected team name
        category: Alert category (MASS_ABSENCE, etc.)
        sources: List of source names that reported this
        first_seen: When first source reported
        last_seen: When last source reported
        original_confidence: Confidence from first source
        boosted_confidence: Confidence after cross-validation
        source_urls: URLs from each source
    """
    team: str
    category: str
    sources: List[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    original_confidence: float = 0.0
    boosted_confidence: float = 0.0
    source_urls: List[str] = field(default_factory=list)
    
    def add_source(self, source_name: str, url: str, confidence: float) -> None:
        """Add a new source confirmation."""
        if source_name not in self.sources:
            self.sources.append(source_name)
            self.source_urls.append(url)
        
        self.last_seen = datetime.now(timezone.utc)
        
        # Update confidence based on source count
        self._recalculate_confidence(confidence)
    
    def _recalculate_confidence(self, new_confidence: float) -> None:
        """Recalculate boosted confidence based on source count."""
        # Use highest original confidence
        if new_confidence > self.original_confidence:
            self.original_confidence = new_confidence
        
        source_count = len(self.sources)
        
        if source_count >= 3:
            boost = CONFIDENCE_BOOST_3_SOURCES
        elif source_count >= 2:
            boost = CONFIDENCE_BOOST_2_SOURCES
        else:
            boost = 0.0
        
        self.boosted_confidence = min(
            self.original_confidence + boost,
            MAX_CONFIDENCE
        )
    
    @property
    def source_count(self) -> int:
        """Number of sources that confirmed this alert."""
        return len(self.sources)
    
    @property
    def is_multi_source(self) -> bool:
        """True if confirmed by 2+ sources."""
        return self.source_count >= 2
    
    def get_validation_tag(self) -> str:
        """Get tag for alert message."""
        if self.source_count >= 3:
            return f"✅✅✅ CONFERMATO ({self.source_count} fonti)"
        elif self.source_count >= 2:
            return f"✅✅ CONFERMATO ({self.source_count} fonti)"
        else:
            return ""


class CrossSourceValidator:
    """
    Validates alerts across multiple sources.
    
    Maintains a buffer of recent alerts and checks for cross-source confirmation.
    """
    
    def __init__(
        self,
        aggregation_window_minutes: int = AGGREGATION_WINDOW_MINUTES,
        cache_ttl_minutes: int = CACHE_TTL_MINUTES
    ):
        """
        Initialize validator.
        
        Args:
            aggregation_window_minutes: Time window to aggregate alerts
            cache_ttl_minutes: How long to keep entries in cache
        """
        self._aggregation_window = timedelta(minutes=aggregation_window_minutes)
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        
        # Cache: key -> PendingAlert
        # Key is hash of (team_normalized, category)
        self._pending_alerts: Dict[str, PendingAlert] = {}
        
        # Lock for thread safety
        self._lock = RLock()
        
        # Stats
        self._alerts_processed = 0
        self._multi_source_alerts = 0
    
    def _generate_key(self, team: str, category: str) -> str:
        """Generate cache key from team and category."""
        # Normalize team name for matching
        team_normalized = team.lower().strip()
        # Remove common suffixes
        for suffix in [' fc', ' sc', ' cf', ' ac', ' as', ' fk', ' sk']:
            if team_normalized.endswith(suffix):
                team_normalized = team_normalized[:-len(suffix)].strip()
        
        key_str = f"{team_normalized}:{category}"
        return hashlib.md5(key_str.encode()).hexdigest()[:12]
    
    def register_alert(
        self,
        team: str,
        category: str,
        source_name: str,
        source_url: str,
        confidence: float
    ) -> Tuple[float, bool, str]:
        """
        Register an alert and check for cross-source validation.
        
        Args:
            team: Affected team name
            category: Alert category
            source_name: Name of the source
            source_url: URL of the source
            confidence: Original confidence score
            
        Returns:
            Tuple of (boosted_confidence, is_multi_source, validation_tag)
        """
        if not team or not category:
            return confidence, False, ""
        
        with self._lock:
            self._alerts_processed += 1
            
            # Cleanup expired entries first
            self._cleanup_expired()
            
            key = self._generate_key(team, category)
            now = datetime.now(timezone.utc)
            
            if key in self._pending_alerts:
                # Existing alert - check if within aggregation window
                pending = self._pending_alerts[key]
                
                if now - pending.first_seen <= self._aggregation_window:
                    # Within window - add source
                    pending.add_source(source_name, source_url, confidence)
                    
                    if pending.is_multi_source:
                        self._multi_source_alerts += 1
                        logger.info(
                            f"✅ [CROSS-VALIDATOR] Multi-source confirmation for {team}: "
                            f"{pending.source_count} sources, confidence {pending.boosted_confidence:.0%}"
                        )
                    
                    return (
                        pending.boosted_confidence,
                        pending.is_multi_source,
                        pending.get_validation_tag()
                    )
                else:
                    # Outside window - replace with new alert
                    self._pending_alerts[key] = PendingAlert(
                        team=team,
                        category=category,
                        sources=[source_name],
                        source_urls=[source_url],
                        original_confidence=confidence,
                        boosted_confidence=confidence
                    )
            else:
                # New alert
                self._pending_alerts[key] = PendingAlert(
                    team=team,
                    category=category,
                    sources=[source_name],
                    source_urls=[source_url],
                    original_confidence=confidence,
                    boosted_confidence=confidence
                )
            
            return confidence, False, ""
    
    def check_existing(self, team: str, category: str) -> Optional[PendingAlert]:
        """
        Check if there's an existing alert for this team/category.
        
        Useful for checking before sending to see if we should wait for more sources.
        
        Args:
            team: Team name
            category: Alert category
            
        Returns:
            PendingAlert if exists and within window, None otherwise
        """
        with self._lock:
            key = self._generate_key(team, category)
            
            if key not in self._pending_alerts:
                return None
            
            pending = self._pending_alerts[key]
            now = datetime.now(timezone.utc)
            
            if now - pending.first_seen <= self._aggregation_window:
                return pending
            
            return None
    
    def should_wait_for_confirmation(
        self,
        team: str,
        category: str,
        min_wait_seconds: int = 30
    ) -> bool:
        """
        Check if we should wait for more sources before sending.
        
        Returns True if:
        - Alert was just registered (< min_wait_seconds ago)
        - Only 1 source so far
        
        This allows time for other sources to confirm.
        
        Args:
            team: Team name
            category: Alert category
            min_wait_seconds: Minimum seconds to wait for confirmation
            
        Returns:
            True if should wait, False if can send now
        """
        with self._lock:
            key = self._generate_key(team, category)
            
            if key not in self._pending_alerts:
                return False
            
            pending = self._pending_alerts[key]
            now = datetime.now(timezone.utc)
            
            # If already multi-source, no need to wait
            if pending.is_multi_source:
                return False
            
            # If enough time has passed, don't wait
            seconds_since_first = (now - pending.first_seen).total_seconds()
            if seconds_since_first >= min_wait_seconds:
                return False
            
            # Should wait for potential confirmation
            return True
    
    def _cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = datetime.now(timezone.utc)
        expired_keys = [
            k for k, v in self._pending_alerts.items()
            if now - v.last_seen > self._cache_ttl
        ]
        
        for k in expired_keys:
            del self._pending_alerts[k]
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict:
        """Get validator statistics."""
        with self._lock:
            return {
                "alerts_processed": self._alerts_processed,
                "multi_source_alerts": self._multi_source_alerts,
                "pending_count": len(self._pending_alerts),
                "multi_source_rate": (
                    self._multi_source_alerts / self._alerts_processed
                    if self._alerts_processed > 0 else 0
                )
            }
    
    def clear(self) -> None:
        """Clear all pending alerts."""
        with self._lock:
            self._pending_alerts.clear()


# Singleton instance
_validator: Optional[CrossSourceValidator] = None
_validator_lock = RLock()


def get_cross_validator() -> CrossSourceValidator:
    """Get singleton instance of CrossSourceValidator."""
    global _validator
    
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = CrossSourceValidator()
                logger.info("✅ [CROSS-VALIDATOR] Validator initialized")
    
    return _validator


def reset_cross_validator() -> None:
    """Reset the validator (for testing)."""
    global _validator
    with _validator_lock:
        _validator = None
