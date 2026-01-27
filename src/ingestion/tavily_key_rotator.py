"""
Tavily API Key Rotator - V7.0

Manages rotation between 7 Tavily API keys (1000 calls each = 7000/month).
Automatically rotates to next key on 429 error.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from config.settings import TAVILY_API_KEYS

logger = logging.getLogger(__name__)


class TavilyKeyRotator:
    """
    Manages rotation between 7 Tavily API keys.
    
    Each key has 1000 calls/month limit.
    Automatically rotates to next key on 429 error.
    
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
    """
    
    def __init__(self, keys: Optional[List[str]] = None):
        """
        Initialize key rotator with API keys.
        
        Args:
            keys: List of API keys (defaults to TAVILY_API_KEYS from settings)
            
        Requirements: 11.1
        """
        # Load keys from config or use provided keys
        raw_keys = keys if keys is not None else TAVILY_API_KEYS
        
        # Filter out empty/None keys
        self._keys: List[str] = [k for k in raw_keys if k and k.strip()]
        self._current_index: int = 0
        self._key_usage: Dict[int, int] = {i: 0 for i in range(len(self._keys))}
        self._exhausted_keys: Set[int] = set()
        self._last_reset_month: Optional[int] = None
        
        if self._keys:
            logger.info(f"🔑 TavilyKeyRotator initialized with {len(self._keys)} keys")
        else:
            logger.warning("⚠️ TavilyKeyRotator: No valid API keys found!")
    
    def get_current_key(self) -> Optional[str]:
        """
        Get current active API key, or None if all exhausted.
        
        Returns:
            Current API key or None if all keys exhausted
            
        Requirements: 11.1
        """
        if not self._keys:
            return None
        
        # Check for monthly reset
        self._check_monthly_reset()
        
        # If current key is exhausted, try to rotate
        if self._current_index in self._exhausted_keys:
            if not self.rotate_to_next():
                return None
        
        return self._keys[self._current_index]
    
    def rotate_to_next(self) -> bool:
        """
        Rotate to next available key.
        
        Returns:
            True if rotation successful, False if all keys exhausted
            
        Requirements: 11.2, 11.3
        """
        if not self._keys:
            return False
        
        original_index = self._current_index
        
        # Try each key in sequence
        for _ in range(len(self._keys)):
            self._current_index = (self._current_index + 1) % len(self._keys)
            
            if self._current_index not in self._exhausted_keys:
                remaining = len(self._keys) - len(self._exhausted_keys)
                logger.info(
                    f"🔄 Tavily key rotation: Key {original_index + 1} → Key {self._current_index + 1} "
                    f"({remaining} keys remaining)"
                )
                return True
        
        # All keys exhausted
        logger.warning("⚠️ All Tavily API keys exhausted!")
        return False
    
    def mark_exhausted(self, key_index: Optional[int] = None) -> None:
        """
        Mark a key as exhausted (received 429).
        
        Args:
            key_index: Index of key to mark (defaults to current key)
            
        Requirements: 11.2
        """
        if key_index is None:
            key_index = self._current_index
        
        if 0 <= key_index < len(self._keys):
            self._exhausted_keys.add(key_index)
            logger.warning(
                f"⚠️ Tavily Key {key_index + 1} marked as exhausted "
                f"(usage: {self._key_usage.get(key_index, 0)} calls)"
            )
    
    def record_call(self) -> None:
        """
        Record a successful API call for current key.
        
        Requirements: 11.2
        """
        if self._keys and 0 <= self._current_index < len(self._keys):
            self._key_usage[self._current_index] = self._key_usage.get(self._current_index, 0) + 1
    
    def reset_all(self) -> None:
        """
        Reset all keys to available status (monthly reset).
        
        Requirements: 11.5
        """
        self._current_index = 0
        self._key_usage = {i: 0 for i in range(len(self._keys))}
        self._exhausted_keys = set()
        self._last_reset_month = datetime.now(timezone.utc).month
        
        logger.info(f"🔄 Tavily keys reset: All {len(self._keys)} keys now available")
    
    def _check_monthly_reset(self) -> None:
        """
        Check if we've crossed a month boundary and reset if needed.
        
        Requirements: 11.5
        """
        current_month = datetime.now(timezone.utc).month
        
        if self._last_reset_month is None:
            self._last_reset_month = current_month
        elif current_month != self._last_reset_month:
            logger.info(f"📅 New month detected (was {self._last_reset_month}, now {current_month})")
            self.reset_all()
    
    def get_status(self) -> Dict:
        """
        Get rotation status for monitoring.
        
        Returns:
            Dict with rotation status information
            
        Requirements: 11.3
        """
        total_keys = len(self._keys)
        available_keys = total_keys - len(self._exhausted_keys)
        total_usage = sum(self._key_usage.values())
        
        return {
            "total_keys": total_keys,
            "available_keys": available_keys,
            "current_key_index": self._current_index + 1 if self._keys else 0,
            "exhausted_keys": sorted([i + 1 for i in self._exhausted_keys]),
            "key_usage": {f"key_{i+1}": usage for i, usage in self._key_usage.items()},
            "total_usage": total_usage,
            "is_available": available_keys > 0,
            "last_reset_month": self._last_reset_month,
        }
    
    def is_available(self) -> bool:
        """
        Check if at least one key is available.
        
        Returns:
            True if at least one key is available
        """
        if not self._keys:
            return False
        
        self._check_monthly_reset()
        return len(self._exhausted_keys) < len(self._keys)
    
    def get_total_usage(self) -> int:
        """
        Get total API calls made across all keys.
        
        Returns:
            Total number of API calls
        """
        return sum(self._key_usage.values())
    
    def get_current_key_usage(self) -> int:
        """
        Get usage count for current key.
        
        Returns:
            Number of calls made with current key
        """
        return self._key_usage.get(self._current_index, 0)


# ============================================
# SINGLETON INSTANCE
# ============================================

_key_rotator_instance: Optional[TavilyKeyRotator] = None


def get_tavily_key_rotator() -> TavilyKeyRotator:
    """Get or create the singleton TavilyKeyRotator instance."""
    global _key_rotator_instance
    if _key_rotator_instance is None:
        _key_rotator_instance = TavilyKeyRotator()
    return _key_rotator_instance
