"""
MediaStack API Key Rotator - V1.0

Manages rotation between 4 MediaStack API keys (FREE unlimited tier).
Automatically rotates to next key on 429/432 errors.
No double-cycle needed - MediaStack is free unlimited.

Requirements: Standard library only (no new dependencies)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.settings import MEDIASTACK_API_KEYS

logger = logging.getLogger(__name__)


class MediaStackKeyRotator:
    """
    Manages rotation between 4 MediaStack API keys.
    
    Each key is from a different MediaStack account (FREE unlimited tier).
    Automatically rotates to next key on 429/432 error.
    Monthly reset ensures keys are available at start of each month.
    
    Requirements: Standard library only
    """
    
    def __init__(self, keys: Optional[List[str]] = None):
        """
        Initialize key rotator with API keys.
        
        Args:
            keys: List of API keys (defaults to MEDIASTACK_API_KEYS from settings)
        """
        # Load keys from config or use provided keys
        raw_keys = keys if keys is not None else MEDIASTACK_API_KEYS
        
        # Filter out empty/None keys
        self._keys: List[str] = [k for k in raw_keys if k and k.strip()]
        self._current_index: int = 0
        self._key_usage: Dict[int, int] = {i: 0 for i in range(len(self._keys))}
        self._exhausted_keys: set = set()
        self._last_reset_month: Optional[int] = None
        
        if self._keys:
            logger.info(f"🔑 MediaStackKeyRotator V1.0 initialized with {len(self._keys)} keys")
        else:
            logger.warning("⚠️ MediaStackKeyRotator: No valid API keys found!")
    
    def get_current_key(self) -> Optional[str]:
        """
        Get current active API key, or None if all exhausted.
        
        Returns:
            Current API key or None if all keys exhausted
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
        
        When all keys are exhausted, attempts a monthly reset before returning False.
        MediaStack is free unlimited, so this is mainly for resilience.
        
        Returns:
            True if rotation successful, False if all keys exhausted (even after reset attempt)
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
                    f"🔄 MediaStack key rotation: Key {original_index + 1} → Key {self._current_index + 1} "
                    f"({remaining} keys remaining)"
                )
                return True
        
        # All keys exhausted - try monthly reset
        current_month = datetime.now(timezone.utc).month
        
        # Check if we can reset (month has passed since last reset)
        if self._last_reset_month is None or current_month != self._last_reset_month:
            logger.info("🔄 MediaStack: All keys exhausted, attempting monthly reset")
            self.reset_all()
            # Try rotation again after reset
            for _ in range(len(self._keys)):
                self._current_index = (self._current_index + 1) % len(self._keys)
                if self._current_index not in self._exhausted_keys:
                    logger.info(
                        f"🔄 MediaStack: After reset, using Key {self._current_index + 1}"
                    )
                    return True
        
        # All keys exhausted even after reset attempt
        logger.warning(
            f"⚠️ All MediaStack API keys exhausted. Activating fallback."
        )
        return False
    
    def mark_exhausted(self, key_index: Optional[int] = None) -> None:
        """
        Mark a key as exhausted (received 429/432).
        
        Args:
            key_index: Index of key to mark (defaults to current key)
        """
        if key_index is None:
            key_index = self._current_index
        
        if 0 <= key_index < len(self._keys):
            self._exhausted_keys.add(key_index)
            logger.warning(
                f"⚠️ MediaStack Key {key_index + 1} marked as exhausted "
                f"(usage: {self._key_usage.get(key_index, 0)} calls)"
            )
    
    def record_call(self) -> None:
        """
        Record a successful API call for current key.
        """
        if self._keys and 0 <= self._current_index < len(self._keys):
            self._key_usage[self._current_index] = self._key_usage.get(self._current_index, 0) + 1
    
    def reset_all(self) -> None:
        """
        Reset all keys to available status (monthly reset).
        """
        self._current_index = 0
        self._key_usage = {i: 0 for i in range(len(self._keys))}
        self._exhausted_keys = set()
        self._last_reset_month = datetime.now(timezone.utc).month
        
        logger.info(f"🔄 MediaStack keys reset: All {len(self._keys)} keys now available")
    
    def _check_monthly_reset(self) -> None:
        """
        Check if we've crossed a month boundary and reset if needed.
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

_key_rotator_instance: Optional[MediaStackKeyRotator] = None


def get_mediastack_key_rotator() -> MediaStackKeyRotator:
    """
    Get or create the singleton MediaStackKeyRotator instance.
    
    Returns:
        Singleton instance of MediaStackKeyRotator
    """
    global _key_rotator_instance
    if _key_rotator_instance is None:
        _key_rotator_instance = MediaStackKeyRotator()
    return _key_rotator_instance


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🔑 MEDIASTACK KEY ROTATOR TEST")
    print("=" * 60)
    
    rotator = get_mediastack_key_rotator()
    
    print(f"\n📊 Status: {rotator.get_status()}")
    print(f"\n✅ Available: {rotator.is_available()}")
    print(f"📊 Total Usage: {rotator.get_total_usage()} calls")
    print(f"🔑 Current Key: {rotator.get_current_key()[:20]}...")
    
    # Test rotation
    print("\n🔄 Testing rotation...")
    rotator.mark_exhausted()
    print(f"   After marking exhausted: {rotator.get_current_key()[:20]}...")
    print(f"   Status: {rotator.get_status()}")
    
    print("\n✅ MediaStack Key Rotator test complete")
