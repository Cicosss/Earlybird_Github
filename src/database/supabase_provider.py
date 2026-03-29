#!/usr/bin/env python3
"""
SupabaseProvider - Enterprise Database Bridge (V9.0)

Provides a robust, cached connection to Supabase with:
- Singleton Pattern: Single connection instance via get_supabase()
- Hierarchical Fetching: Continental-Country-League-Sources map
- Smart Cache: Configurable cache with default 5-minute TTL (300s)
- Fail-Safe Mirror: Local fallback to data/supabase_mirror.json

Author: Lead Architect
Date: 2026-02-08
"""

import json
import logging
import os

# Setup path
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

# V12.5: Use absolute path for .env file for consistency with main.py
# This ensures environment variables are loaded correctly regardless of working directory
env_file = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_file)

# Type hint for Client (avoid import error if not installed)
if TYPE_CHECKING:
    pass

try:
    from supabase import create_client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase client not installed. Run: pip install supabase")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
# V12.5: Cache TTL is now configurable via environment variable (default: 300 seconds = 5 minutes)
# This reduces cache staleness while still providing caching benefits
CACHE_TTL_SECONDS = int(os.getenv("SUPABASE_CACHE_TTL_SECONDS", "300"))
SUPABASE_QUERY_TIMEOUT = 10.0  # 10 second timeout for queries (V11.1)
CACHE_LOCK_TIMEOUT = 10.0  # V12.2: Increased from 5.0s for VPS with slow I/O
CACHE_LOCK_RETRIES = 2  # V12.2: Retry lock acquisition on timeout
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")
DATA_DIR = Path("data")


class SupabaseProvider:
    """
    Enterprise Supabase Provider with singleton pattern, caching, and fail-safe mirror.

    Features:
    - Singleton pattern ensures only one connection instance
    - Hierarchical data fetching (Continents -> Countries -> Leagues -> Sources)
    - Smart configurable cache with default 5-minute TTL (300s) to minimize API usage
    - Fail-safe mirror: saves local copy and falls back on connection failure
    - Thread-safe operations (V11.1)
    - Atomic mirror writes with fallback (V11.1, V12.5)
    - Data completeness validation (V11.1)
    - Connection retry logic with exponential backoff (V12.5)
    """

    _instance: Optional["SupabaseProvider"] = None
    _client: Any | None = None
    _instance_lock = threading.Lock()  # Thread-safe singleton creation (V11.1)

    def __new__(cls):
        """Singleton pattern: ensure only one instance exists (thread-safe)."""
        if cls._instance is None:
            with cls._instance_lock:  # V11.1: Thread-safe singleton creation
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the Supabase provider (only once)."""
        if self._initialized:
            return

        self._initialized = True
        self._cache: dict[str, Any] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_lock = threading.Lock()  # V11.1: Thread-safe cache operations
        self._connected = False
        self._connection_error: str | None = None

        # V12.1: Lock contention monitoring for production observability
        self._cache_lock_wait_time = 0.0
        self._cache_lock_wait_count = 0
        self._cache_lock_timeout_count = 0

        # V12.5: Cache metrics tracking for observability
        self._cache_hit_count = 0
        self._cache_miss_count = 0
        self._cache_bypass_count = 0

        # Ensure data directory exists
        DATA_DIR.mkdir(exist_ok=True)

        # Initialize connection
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """
        Initialize Supabase client connection with retry logic.

        V11.2: Added detailed timing logs for debugging timeout issues.
        V12.5: Added retry logic with exponential backoff for VPS deployment.
        """
        logger.debug("🔄 Starting Supabase connection initialization...")
        init_start = time.time()

        if not SUPABASE_AVAILABLE:
            self._connection_error = "Supabase package not installed"
            logger.error(self._connection_error)
            return

        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")

        if not supabase_url or not supabase_key:
            self._connection_error = "SUPABASE_URL or SUPABASE_KEY not configured in .env"
            logger.error(self._connection_error)
            return

        # V12.5: Add retry logic with exponential backoff for VPS deployment
        max_retries = 3
        base_delay = 2.0  # seconds

        for attempt in range(max_retries):
            try:
                # V11.1: Create Supabase client with explicit timeout to prevent indefinite hangs
                # Use httpx.Client with timeout for all HTTP operations
                import httpx
                from supabase.lib.client_options import SyncClientOptions

                logger.debug(f"🔄 Creating httpx client with timeout {SUPABASE_QUERY_TIMEOUT}s...")
                httpx_timeout = httpx.Timeout(
                    connect=SUPABASE_QUERY_TIMEOUT,
                    read=SUPABASE_QUERY_TIMEOUT,
                    write=SUPABASE_QUERY_TIMEOUT,
                    pool=SUPABASE_QUERY_TIMEOUT,
                )
                httpx_client = httpx.Client(timeout=httpx_timeout)
                logger.debug("✅ httpx client created")

                # Create Supabase client with custom httpx client
                logger.debug("🔄 Creating Supabase client with custom httpx client...")
                options = SyncClientOptions(
                    postgrest_client_timeout=SUPABASE_QUERY_TIMEOUT,
                    httpx_client=httpx_client,
                )
                self._client = create_client(supabase_url, supabase_key, options=options)
                self._connected = True

                init_time = time.time() - init_start
                logger.info(
                    f"✅ Supabase connection established successfully in {init_time:.2f}s "
                    f"(timeout: {SUPABASE_QUERY_TIMEOUT}s, attempt: {attempt + 1}/{max_retries})"
                )
                return  # Success - exit retry loop
            except Exception as e:
                self._connection_error = f"Failed to connect to Supabase: {e}"

                if attempt < max_retries - 1:
                    # Calculate delay with exponential backoff
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"⚠️ Connection attempt {attempt + 1}/{max_retries} failed. "
                        f"Retrying in {delay}s... Error: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(self._connection_error)
                    self._connected = False
                    logger.error(
                        f"❌ All {max_retries} connection attempts failed. "
                        f"Bot will use mirror data as fallback."
                    )

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to Supabase.

        V12.5: Added reconnection method for VPS deployment recovery.

        Returns:
            True if reconnection was successful, False otherwise
        """
        logger.info("🔄 Attempting to reconnect to Supabase...")
        self._connected = False
        self._connection_error = None
        self._initialize_connection()
        return self._connected

    def is_connected(self) -> bool:
        """Check if Supabase connection is active."""
        return self._connected

    def get_connection_error(self) -> str | None:
        """Get the connection error message if any."""
        return self._connection_error

    def get_cache_lock_stats(self) -> dict:
        """
        Get cache lock contention statistics for monitoring.

        V12.1: Expose lock contention metrics for production observability.

        Returns:
            Dict with lock stats (wait_count, wait_time_avg, etc.)
        """
        return {
            "wait_count": self._cache_lock_wait_count,
            "wait_time_total": round(self._cache_lock_wait_time, 3),
            "wait_time_avg": round(self._cache_lock_wait_time / self._cache_lock_wait_count, 3)
            if self._cache_lock_wait_count > 0
            else 0.0,
            "timeout_count": self._cache_lock_timeout_count,
        }

    def get_cache_metrics(self) -> dict:
        """
        Get cache performance metrics for monitoring.

        V12.5: Expose cache hit/miss metrics for production observability.

        Returns:
            Dict with cache metrics (hit_count, miss_count, hit_ratio, etc.)
        """
        total_requests = self._cache_hit_count + self._cache_miss_count
        hit_ratio = (
            round(self._cache_hit_count / total_requests * 100, 2) if total_requests > 0 else 0.0
        )

        return {
            "hit_count": self._cache_hit_count,
            "miss_count": self._cache_miss_count,
            "bypass_count": self._cache_bypass_count,
            "total_requests": total_requests,
            "hit_ratio_percent": hit_ratio,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "cached_keys_count": len(self._cache),
        }

    def reset_cache_lock_stats(self):
        """
        Reset cache lock contention statistics.

        Issue 2 fix: Reset lock stats periodically to prevent averages from becoming
        meaningless over time. This method is thread-safe and should be called by
        the metrics collector every hour.
        """
        with self._cache_lock:
            self._cache_lock_wait_time = 0.0
            self._cache_lock_wait_count = 0
            self._cache_lock_timeout_count = 0

    def invalidate_cache(self, cache_key: str | None = None) -> None:
        """
        Invalidate cache for a specific key or all cache entries.

        V12.5: Add cache invalidation mechanism for manual cache clearing.

        Args:
            cache_key: Specific cache key to invalidate. If None, clears all cache.
        """
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                if cache_key:
                    # Invalidate specific cache key
                    if cache_key in self._cache:
                        del self._cache[cache_key]
                        del self._cache_timestamps[cache_key]
                        logger.info(f"🗑️ Cache invalidated for key: {cache_key}")
                    else:
                        logger.debug(f"Cache key not found: {cache_key}")
                else:
                    # Invalidate all cache
                    cleared_count = len(self._cache)
                    self._cache.clear()
                    self._cache_timestamps.clear()
                    logger.info(f"🗑️ All cache cleared ({cleared_count} entries)")
            finally:
                self._cache_lock.release()
        else:
            logger.warning("Failed to acquire cache lock for invalidation")

    def invalidate_leagues_cache(self) -> None:
        """
        Invalidate all league-related cache entries.

        V12.5: Convenience method to clear league cache when leagues are modified.
        V12.5: Optimized to acquire lock ONCE for all keys (reduced lock contention).
        V13.0: CRITICAL FIX - Moved key listing inside lock to prevent race condition.

        This clears cache for:
        - active_leagues_full
        - leagues table queries
        - countries table queries
        - continents table queries
        """
        league_related_keys = [
            "active_leagues_full",
            "leagues",
            "countries",
            "continents",
        ]

        # V13.0: CRITICAL FIX - Acquire lock BEFORE getting keys to prevent race condition
        # Previous version had race condition where keys were fetched outside lock
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                # Also invalidate any keys that contain "leagues", "countries", or "continents"
                all_keys = list(self._cache.keys())
                for key in all_keys:
                    if any(
                        keyword in key.lower() for keyword in ["leagues", "countries", "continents"]
                    ):
                        league_related_keys.append(key)

                # Remove duplicates while preserving order
                league_related_keys = list(dict.fromkeys(league_related_keys))

                # V12.5: OPTIMIZATION - Acquire lock ONCE, invalidate all keys, then release
                # This is much more efficient than calling invalidate_cache() for each key
                # which would acquire/release the lock multiple times
                cleared_count = 0
                for key in league_related_keys:
                    if key in self._cache:
                        del self._cache[key]
                        if key in self._cache_timestamps:
                            del self._cache_timestamps[key]
                        cleared_count += 1
                logger.info(f"🗑️ League cache invalidated ({cleared_count} entries)")
            finally:
                self._cache_lock.release()
        else:
            logger.warning("Failed to acquire cache lock for league invalidation")

    def _acquire_cache_lock_with_monitoring(self, timeout: float = CACHE_LOCK_TIMEOUT) -> bool:
        """
        Acquire cache lock with contention monitoring.

        V12.1: Track lock wait times and contention for production observability.

        Args:
            timeout: Maximum time to wait for lock acquisition (default: 5.0s)

        Returns:
            True if lock was acquired, False if timeout occurred
        """
        start_time = time.time()
        acquired = self._cache_lock.acquire(timeout=timeout)
        wait_time = time.time() - start_time

        if acquired:
            # Update monitoring metrics
            self._cache_lock_wait_time += wait_time
            self._cache_lock_wait_count += 1

            # Log warnings for high contention
            if wait_time > 0.1:  # More than 100ms
                logger.warning(
                    f"⚠️ [SUPABASE-PROVIDER] High cache lock contention detected: "
                    f"waited {wait_time:.3f}s (total waits: {self._cache_lock_wait_count}, "
                    f"avg wait: {self._cache_lock_wait_time / self._cache_lock_wait_count:.3f}s)"
                )
        else:
            # Track timeout
            self._cache_lock_timeout_count += 1
            logger.warning(
                f"⚠️ [SUPABASE-PROVIDER] Cache lock acquisition timeout after {wait_time:.3f}s "
                f"(timeout: {timeout}s, total timeouts: {self._cache_lock_timeout_count})"
            )

        return acquired

    def _is_cache_valid_unlocked(self, cache_key: str) -> bool:
        """
        Check if cache entry is still valid (within TTL).

        WARNING: This method assumes the caller already holds _cache_lock.
        It does NOT acquire the lock internally to avoid deadlock.

        Args:
            cache_key: Cache key to check

        Returns:
            True if cache entry is valid, False otherwise
        """
        if cache_key not in self._cache_timestamps:
            return False

        cache_age = time.time() - self._cache_timestamps[cache_key]
        return cache_age < CACHE_TTL_SECONDS

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cache entry is still valid (within TTL) - thread-safe wrapper.

        Args:
            cache_key: Cache key to check

        Returns:
            True if cache entry is valid, False otherwise
        """
        # V12.1: Use lock acquisition with monitoring
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                return self._is_cache_valid_unlocked(cache_key)
            finally:
                self._cache_lock.release()
        else:
            logger.warning(f"Failed to acquire cache lock for validity check: {cache_key}")
            return False

    def _get_from_cache(self, cache_key: str, bypass_cache: bool = False) -> Any | None:
        """
        Retrieve data from cache if valid (thread-safe).

        V12.2: Added retry logic for lock acquisition.
        V12.5: Added bypass_cache parameter, cache miss logging, and cache age information.

        Args:
            cache_key: Cache key to retrieve
            bypass_cache: If True, skip cache and return None (forces fresh data fetch)

        Returns:
            Cached data if valid, None otherwise
        """
        # V12.5: Track bypass operations (thread-safe)
        # Note: We track bypass_count here before acquiring lock to avoid
        # unnecessary lock overhead for simple bypass operations
        if bypass_cache:
            # V12.5: Simplified - use lock for thread safety (atomic_add doesn't exist in stdlib)
            with self._cache_lock:
                self._cache_bypass_count += 1
            logger.debug(f"🔄 Cache bypassed for key: {cache_key}")
            return None

        # V12.0: Fixed deadlock - use _is_cache_valid_unlocked() instead of _is_cache_valid()
        # V12.1: Use lock acquisition with monitoring
        # V12.2: Added retry logic for improved VPS compatibility
        # V12.5: Added fallback to stale cache when lock acquisition fails
        for attempt in range(CACHE_LOCK_RETRIES):
            if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
                try:
                    if self._is_cache_valid_unlocked(cache_key):
                        # V12.5: Track cache hit and log with age information
                        self._cache_hit_count += 1
                        cache_age = time.time() - self._cache_timestamps[cache_key]
                        logger.debug(
                            f"✅ Cache HIT for key: {cache_key} (age: {cache_age:.1f}s, TTL: {CACHE_TTL_SECONDS}s)"
                        )
                        return self._cache[cache_key]
                    else:
                        # V12.5: Track cache miss and log reason
                        self._cache_miss_count += 1
                        if cache_key in self._cache_timestamps:
                            cache_age = time.time() - self._cache_timestamps[cache_key]
                            logger.debug(
                                f"❌ Cache MISS for key: {cache_key} (expired: {cache_age:.1f}s > TTL: {CACHE_TTL_SECONDS}s)"
                            )
                        else:
                            logger.debug(f"❌ Cache MISS for key: {cache_key} (not found)")
                        return None
                finally:
                    self._cache_lock.release()
            else:
                if attempt < CACHE_LOCK_RETRIES - 1:
                    logger.warning(
                        f"Retry {attempt + 1}/{CACHE_LOCK_RETRIES} for cache lock: {cache_key}"
                    )
                else:
                    # V12.5: All retries exhausted - try to return stale cache as fallback
                    total_wait_time = CACHE_LOCK_TIMEOUT * CACHE_LOCK_RETRIES
                    logger.error(
                        f"❌ Cache lock acquisition failed after {CACHE_LOCK_RETRIES} retries "
                        f"(total wait: {total_wait_time}s) for key: {cache_key}"
                    )
                    # Fallback: Return stale cache if available to prevent bot timeout
                    # V12.5: Add age check to prevent returning obsolete data (COVE FIX)
                    MAX_STALE_CACHE_AGE = 3600  # 1 hour in seconds
                    if cache_key in self._cache:
                        cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
                        # Don't return cache older than 1 hour
                        if cache_age > MAX_STALE_CACHE_AGE:
                            logger.warning(
                                f"⚠️ Stale cache too old ({cache_age:.1f}s > {MAX_STALE_CACHE_AGE}s), "
                                f"returning None for key: {cache_key}"
                            )
                            return None
                        logger.warning(
                            f"⚠️ Returning stale cache for {cache_key} (age: {cache_age:.1f}s) "
                            f"as fallback to prevent bot timeout"
                        )
                        return self._cache[cache_key]
                    return None
        return None

    def _set_cache(self, cache_key: str, data: Any) -> None:
        """
        Store data in cache with current timestamp (thread-safe).

        Args:
            cache_key: Cache key to store
            data: Data to cache
        """
        # V12.0: Standardized lock usage - use timeout to prevent deadlock
        # V12.1: Use lock acquisition with monitoring
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                self._cache[cache_key] = data
                self._cache_timestamps[cache_key] = time.time()
                logger.debug(f"Cache set for key: {cache_key}")
            finally:
                self._cache_lock.release()
        else:
            logger.warning(f"Failed to acquire cache lock for {cache_key}")

    def _validate_data_completeness(self, data: dict[str, Any]) -> bool:
        """
        Validate data completeness before saving to mirror.

        V11.1: Check for required top-level keys.
        V12.5: Added structural validation for nested data to prevent corruption.
        V13.0: HIGH FIX - Added "social_sources" to required keys to match mirror data.

        Args:
            data: Data to validate

        Returns:
            True if data is complete and structurally valid, False otherwise
        """
        # V11.1: Check for required top-level keys
        # V13.0: Added "social_sources" to match what create_local_mirror() and update_mirror() save
        required_keys = ["continents", "countries", "leagues", "news_sources", "social_sources"]
        missing_keys = [key for key in required_keys if key not in data]

        if missing_keys:
            logger.warning(f"⚠️ Missing required keys in mirror data: {missing_keys}")
            return False

        # V12.5: Validate data types and structure
        for key in required_keys:
            value = data[key]

            # Check that value is a list
            if not isinstance(value, list):
                logger.error(
                    f"❌ Invalid data type for {key}: expected list, got {type(value).__name__}"
                )
                return False

            # Check if section is empty
            if len(value) == 0:
                logger.warning(f"⚠️ Empty section in mirror data: {key}")
                # Don't fail on empty sections, just warn
                continue

            # V12.5: Validate structure of first item (if list is not empty)
            if len(value) > 0:
                first_item = value[0]
                if not isinstance(first_item, dict):
                    logger.error(
                        f"❌ Invalid structure for {key}: expected dict items, got {type(first_item).__name__}"
                    )
                    return False

                # Check for required fields based on key type
                if key == "continents":
                    required_fields = ["id", "name"]
                elif key == "countries":
                    required_fields = ["id", "name", "continent_id"]
                elif key == "leagues":
                    required_fields = ["id", "api_key", "tier_name", "country_id"]
                elif key == "news_sources":
                    # V13.0 COVE FIX: Removed "name" from required_fields - downstream code uses .get() with fallback
                    # The news_sources table may have records without explicit "name" field
                    required_fields = ["id", "league_id"]
                elif key == "social_sources":
                    # V13.0 COVE FIX: Removed "name" from required_fields - downstream code uses .get() with fallback
                    # The social_sources table may have records without explicit "name" field
                    required_fields = ["id", "league_id"]
                else:
                    required_fields = []

                if required_fields:
                    missing_fields = [f for f in required_fields if f not in first_item]
                    if missing_fields:
                        logger.warning(
                            f"⚠️ {key} items missing required fields: {missing_fields}. "
                            f"First item keys: {list(first_item.keys())}"
                        )

        return True

    def _save_to_mirror(self, data: dict[str, Any], version: str = "V9.5") -> None:
        """
        Save Supabase data to local mirror file with version and checksum.

        V11.1: Uses atomic write pattern to prevent corruption on crashes.
        V11.1: Validates data completeness before saving.

        Args:
            data: Data to save to mirror
            version: Mirror version string
        """
        try:
            # V11.1: Validate data completeness before saving
            if not self._validate_data_completeness(data):
                logger.warning("⚠️ Data completeness validation failed, not updating mirror")
                return

            # Validate UTF-8 integrity before saving
            if not self._validate_utf8_integrity(data):
                logger.warning("⚠️ UTF-8 integrity check failed, but saving anyway")

            # Calculate checksum for integrity verification
            checksum = self._calculate_checksum(data)

            mirror_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": version,
                "checksum": checksum,
                "data": data,
            }

            # V11.1: Atomic write pattern - write to temp file, then rename
            # V12.5: Added error handling and fallback for VPS filesystem compatibility
            temp_file = MIRROR_FILE_PATH.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(mirror_data, f, indent=2, ensure_ascii=False)

            # Atomic rename (POSIX guarantees atomicity on same filesystem)
            # V12.5: Added fallback for Docker overlay and container filesystems
            try:
                temp_file.replace(MIRROR_FILE_PATH)
                logger.info(
                    f"✅ Atomic mirror write successful to {MIRROR_FILE_PATH} (v{version}, checksum: {checksum[:8]}...)"
                )
            except Exception as e:
                logger.error(f"❌ Atomic write failed: {e}")
                # Fallback: Create backup and write directly
                if MIRROR_FILE_PATH.exists():
                    backup_path = MIRROR_FILE_PATH.with_suffix(".bak")
                    try:
                        MIRROR_FILE_PATH.replace(backup_path)
                        logger.info(f"📦 Created backup at {backup_path}")
                    except Exception as backup_err:
                        logger.warning(f"⚠️ Failed to create backup: {backup_err}")
                # Write directly with UTF-8 encoding
                try:
                    with open(MIRROR_FILE_PATH, "w", encoding="utf-8") as f:
                        json.dump(mirror_data, f, indent=2, ensure_ascii=False)
                    logger.info(
                        f"✅ Direct mirror write successful to {MIRROR_FILE_PATH} (v{version}, checksum: {checksum[:8]}...)"
                    )
                except Exception as direct_err:
                    logger.error(f"❌ Direct write also failed: {direct_err}")
                    raise
        except Exception as e:
            logger.error(f"❌ Failed to save mirror: {e}")

    def _calculate_checksum(self, data: dict[str, Any]) -> str:
        """
        Calculate checksum for data integrity verification.

        Args:
            data: Data to calculate checksum for

        Returns:
            Hexadecimal checksum string
        """
        import hashlib

        try:
            # Convert data to JSON string with sorted keys for consistency
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            # Calculate SHA-256 hash
            checksum = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
            return checksum
        except Exception as e:
            logger.error(f"❌ Failed to calculate checksum: {e}")
            return ""

    def _validate_utf8_integrity(self, data: dict[str, Any]) -> bool:
        """
        Validate UTF-8 integrity of multilingual content.

        Args:
            data: Data to validate

        Returns:
            bool: True if UTF-8 integrity is valid
        """
        try:
            # Test encoding/decoding
            json_str = json.dumps(data, ensure_ascii=False)
            decoded = json.loads(json_str)

            # Check for common multilingual characters
            test_strings = [
                "Arabic: إصابة أزمة",
                "Spanish: lesión huelga",
                "French: blessure grève",
                "German: verletzung streik",
                "Portuguese: lesão greve",
            ]

            for test_str in test_strings:
                encoded = test_str.encode("utf-8")
                decoded_str = encoded.decode("utf-8")
                if test_str != decoded_str:
                    logger.error(f"❌ UTF-8 integrity check failed for: {test_str}")
                    return False

            logger.info("✅ UTF-8 integrity validated")
            return True

        except Exception as e:
            logger.error(f"❌ UTF-8 validation failed: {e}")
            return False

    def _load_from_mirror(self) -> dict[str, Any] | None:
        """
        Load data from local mirror file with checksum validation.

        V13.0: HIGH FIX - Added "social_sources" to validation to match mirror data.

        Returns:
            Mirror data dict or None if file doesn't exist or validation fails
        """
        if not MIRROR_FILE_PATH.exists():
            logger.warning(f"⚠️ Mirror file not found: {MIRROR_FILE_PATH}")
            return None

        try:
            with open(MIRROR_FILE_PATH, encoding="utf-8") as f:
                mirror_data = json.load(f)

            timestamp = mirror_data.get("timestamp", "")
            version = mirror_data.get("version", "UNKNOWN")
            checksum = mirror_data.get("checksum", "")
            data = mirror_data.get("data", {})

            # Validate checksum if present
            # V12.5: Enhanced checksum validation with structural checks and fallback
            # V13.0: Added "social_sources" to required keys validation
            if checksum:
                calculated_checksum = self._calculate_checksum(data)
                if calculated_checksum != checksum:
                    logger.error(
                        f"❌ Mirror checksum mismatch! Expected: {checksum[:8]}..., Got: {calculated_checksum[:8]}..."
                    )
                    # V12.5: Try to validate JSON structure before deciding to use or reject
                    try:
                        # Validate JSON structure - check for required top-level keys
                        # V13.0: Added "social_sources" to match what create_local_mirror() and update_mirror() save
                        if isinstance(data, dict) and all(
                            k in data
                            for k in [
                                "continents",
                                "countries",
                                "leagues",
                                "news_sources",
                                "social_sources",
                            ]
                        ):
                            logger.warning(
                                "⚠️ Mirror checksum failed but JSON structure is valid - using with caution"
                            )
                            logger.info(
                                f"✅ Loaded mirror from {timestamp} (v{version}) - checksum warning"
                            )
                            return data
                        else:
                            logger.error(
                                "❌ Mirror JSON structure is invalid - returning empty data"
                            )
                            return {}
                    except Exception as e:
                        logger.error(f"❌ Mirror data is corrupted: {e} - returning empty data")
                        return {}
                else:
                    logger.info(f"✅ Mirror checksum validated: {checksum[:8]}...")

            logger.info(f"✅ Loaded mirror from {timestamp} (v{version})")
            return data
        except Exception as e:
            logger.error(f"❌ Failed to load mirror: {e}")
            return None

    def _execute_query(
        self,
        table_name: str,
        cache_key: str,
        select: str = "*",
        filters: dict[str, Any] | None = None,
        bypass_cache: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Execute Supabase query with caching and fail-safe mirror.

        V11.1: Added explicit timeout to prevent indefinite hangs on VPS.
        V11.2: Added detailed timing logs for debugging timeout issues.
        V11.3: Fixed potential deadlock by releasing cache lock before query.
        V12.5: Added bypass_cache parameter and enhanced logging for cache behavior.

        Args:
            table_name: Name of the table to query
            cache_key: Unique key for caching
            select: Select clause (default: "*")
            filters: Optional dictionary of filters
            bypass_cache: If True, skip cache and fetch fresh data (default: False)

        Returns:
            List of records from the table
        """
        # Try cache first (with lock)
        cached_data = self._get_from_cache(cache_key, bypass_cache=bypass_cache)
        if cached_data is not None:
            logger.debug(f"✅ Cache hit for {table_name} (key: {cache_key})")
            return cached_data

        # V12.5: Log that we're fetching fresh data
        if bypass_cache:
            logger.info(f"🔄 Bypassing cache for {table_name} (key: {cache_key})")
        else:
            logger.debug(f"🔄 Cache miss for {table_name} (key: {cache_key}), fetching fresh data")

        # Try Supabase connection
        if self._connected and self._client:
            try:
                logger.debug(
                    f"🔄 Executing query for {table_name} (timeout: {SUPABASE_QUERY_TIMEOUT}s)..."
                )
                query_start = time.time()

                query = self._client.table(table_name).select(select)

                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)

                # V11.1: Execute query (timeout configured at client creation)
                # V12.5: Added explicit timeout verification to detect slow queries
                logger.debug(f"🔄 Calling query.execute() for {table_name}...")
                execute_start = time.time()
                response = query.execute()
                execute_time = time.time() - execute_start
                logger.debug(
                    f"✅ query.execute() completed in {execute_time:.2f}s for {table_name}"
                )

                # V12.5: Explicit timeout verification to detect slow queries
                if execute_time > SUPABASE_QUERY_TIMEOUT * 0.9:  # 90% of timeout threshold
                    logger.warning(
                        f"⚠️ Query for {table_name} took {execute_time:.2f}s "
                        f"(close to timeout threshold of {SUPABASE_QUERY_TIMEOUT}s)"
                    )

                data = response.data if hasattr(response, "data") else []

                total_time = time.time() - query_start
                logger.info(
                    f"✅ Supabase query for {table_name} completed in {total_time:.2f}s (returned {len(data)} records)"
                )

                # Cache the result (with lock)
                self._set_cache(cache_key, data)

                return data

            except Exception as e:
                # V11.1: Enhanced error logging with timeout detection
                error_type = type(e).__name__
                error_msg = str(e)

                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    logger.error(
                        f"⏱️ Supabase query timeout for {table_name} (>{SUPABASE_QUERY_TIMEOUT}s)"
                    )
                else:
                    logger.warning(
                        f"Supabase query failed for {table_name}: {error_type}: {error_msg}"
                    )
                # Fall through to mirror

        # Fallback to mirror
        logger.info(f"🔄 Falling back to mirror for {table_name}")
        mirror_start = time.time()
        mirror_data = self._load_from_mirror()
        mirror_time = time.time() - mirror_start

        if mirror_data and table_name in mirror_data:
            logger.info(
                f"✅ Mirror fallback for {table_name} completed in {mirror_time:.2f}s (returned {len(mirror_data[table_name])} records)"
            )
            return mirror_data[table_name]

        logger.error(f"❌ No data available for {table_name} (Supabase and mirror failed)")
        return []

    def fetch_continents(self) -> list[dict[str, Any]]:
        """
        Fetch all continents from Supabase.

        Returns:
            List of continent records
        """
        cache_key = "continents"
        data = self._execute_query("continents", cache_key)
        logger.info(f"Fetched {len(data)} continents")
        return data

    def fetch_countries(self, continent_id: str | None = None) -> list[dict[str, Any]]:
        """
        Fetch countries, optionally filtered by continent.

        Args:
            continent_id: Optional continent ID to filter countries

        Returns:
            List of country records
        """
        cache_key = f"countries_{continent_id}" if continent_id else "countries_all"
        filters = {"continent_id": continent_id} if continent_id else None
        data = self._execute_query("countries", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} countries")
        return data

    def fetch_leagues(self, country_id: str | None = None) -> list[dict[str, Any]]:
        """
        Fetch leagues, optionally filtered by country.

        Args:
            country_id: Optional country ID to filter leagues

        Returns:
            List of league records
        """
        cache_key = f"leagues_{country_id}" if country_id else "leagues_all"
        filters = {"country_id": country_id} if country_id else None
        data = self._execute_query("leagues", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} leagues")
        return data

    def fetch_sources(self, league_id: str | None = None) -> list[dict[str, Any]]:
        """
        Fetch news sources, optionally filtered by league.

        Note: This method queries the 'news_sources' table in Supabase.
        The table was renamed from 'sources' to 'news_sources' in V9.5.

        Args:
            league_id: Optional league ID to filter sources

        Returns:
            List of news source records
        """
        cache_key = f"news_sources_{league_id}" if league_id else "news_sources_all"
        filters = {"league_id": league_id} if league_id else None
        data = self._execute_query("news_sources", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} news sources")
        return data

    def fetch_hierarchical_map(self) -> dict[str, Any]:
        """
        Fetch the complete Continental-Country-League-Sources hierarchy.

        Returns:
            Nested dictionary structure:
            {
                "continents": [
                    {
                        "id": "eu",
                        "name": "Europe",
                        "countries": [
                            {
                                "id": "it",
                                "name": "Italy",
                                "leagues": [
                                    {
                                        "id": "serie_a",
                                        "name": "Serie A",
                                        "sources": [...]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        """
        cache_key = "hierarchical_map_full"

        # Try cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # Build hierarchical structure
        continents = self.fetch_continents()
        hierarchical_data = {"continents": []}

        # V13.0: Collect all data during iteration to avoid redundant fetches
        all_countries = []
        all_leagues = []
        all_sources = []

        for continent in continents:
            continent_data = {
                "id": continent.get("id"),
                "name": continent.get("name"),
                "countries": [],
            }

            countries = self.fetch_countries(continent.get("id"))
            all_countries.extend(countries)

            for country in countries:
                country_data = {"id": country.get("id"), "name": country.get("name"), "leagues": []}

                leagues = self.fetch_leagues(country.get("id"))
                all_leagues.extend(leagues)

                for league in leagues:
                    sources = self.fetch_sources(league.get("id"))
                    all_sources.extend(sources)

                    league_data = {
                        "id": league.get("id"),
                        "name": league.get("name"),
                        "sources": sources,
                    }
                    country_data["leagues"].append(league_data)

                continent_data["countries"].append(country_data)

            hierarchical_data["continents"].append(continent_data)

        # Cache the result
        self._set_cache(cache_key, hierarchical_data)

        # V13.0: Use collected data instead of fetching again
        mirror_data = {
            "continents": continents,
            "countries": all_countries,
            "leagues": all_leagues,
            "news_sources": all_sources,
        }
        self._save_to_mirror(mirror_data)

        logger.info("Built complete hierarchical map")
        return hierarchical_data

    # ============================================
    # V9.2: DATABASE-DRIVEN INTELLIGENCE ENGINE METHODS
    # ============================================

    def get_active_leagues(self, bypass_cache: bool = False) -> list[dict[str, Any]]:
        """
        Fetch all active leagues with country and continent information.

        V12.5: Added bypass_cache parameter for critical operations.

        Args:
            bypass_cache: If True, skip cache and fetch fresh data (default: False)

        Returns:
            List of active league records with enriched data:
            [
                {
                    "id": "league_uuid",
                    "api_key": "soccer_brazil_campeonato",
                    "tier_name": "Série A",
                    "priority": 1,
                    "is_active": true,
                    "country": {
                        "id": "country_uuid",
                        "name": "Brazil",
                        "iso_code": "BR"
                    },
                    "continent": {
                        "id": "continent_uuid",
                        "name": "LATAM",
                        "active_hours_utc": [12, 13, 14, ...]
                    }
                },
                ...
            ]
        """
        cache_key = "active_leagues_full"

        # Try cache first
        cached_data = self._get_from_cache(cache_key, bypass_cache=bypass_cache)
        if cached_data is not None:
            return cached_data

        # Fetch active leagues (use different cache key to avoid conflict)
        leagues = self._execute_query(
            "leagues", "leagues_active", filters={"is_active": True}, bypass_cache=bypass_cache
        )

        if not leagues:
            logger.warning("No active leagues found in database")
            return []

        # V13.0: MEDIUM FIX - Collect unique country_ids from active leagues
        # Removed incorrect continent_id assignment and unused continent_ids set
        # Continent info is fetched through countries (see line 1137)
        country_ids = set()
        for league in leagues:
            country_id = league.get("country_id")
            if country_id:
                country_ids.add(country_id)

        # Fetch only the countries and continents needed for active leagues
        # This is much more efficient than fetching all countries/continents
        countries_to_fetch = list(country_ids)
        continents_to_fetch = set()

        # Build lookup dictionaries
        country_map = {}
        continent_map = {}

        if countries_to_fetch:
            logger.debug(f"Fetching {len(countries_to_fetch)} countries for active leagues")
            countries = self.fetch_countries()
            for country in countries:
                country_map[country["id"]] = country
                continent_id = country.get("continent_id")
                if continent_id:
                    continents_to_fetch.add(continent_id)

        if continents_to_fetch:
            logger.debug(f"Fetching {len(continents_to_fetch)} continents for active leagues")
            continents = self.fetch_continents()
            for continent in continents:
                continent_map[continent["id"]] = continent

        # Enrich leagues with country and continent data
        enriched_leagues = []
        for league in leagues:
            country_id = league.get("country_id")
            country = country_map.get(country_id)

            if not country:
                logger.warning(f"League {league.get('api_key')} has no valid country_id")
                continue

            continent_id = country.get("continent_id")
            continent = continent_map.get(continent_id)

            if not continent:
                logger.warning(f"Country {country.get('name')} has no valid continent_id")
                continue

            enriched_league = {
                **league,
                "country": {
                    "id": country["id"],
                    "name": country["name"],
                    "iso_code": country.get("iso_code"),
                },
                "continent": {
                    "id": continent["id"],
                    "name": continent["name"],
                    "active_hours_utc": continent.get("active_hours_utc", []),
                },
            }
            enriched_leagues.append(enriched_league)

        # Cache the enriched result (use different cache key to avoid conflict)
        self._set_cache(cache_key, enriched_leagues)

        logger.info(f"Found {len(enriched_leagues)} active leagues")
        return enriched_leagues

    def get_active_leagues_for_continent(
        self, continent_name: str, bypass_cache: bool = False
    ) -> list[dict[str, Any]]:
        """
        Fetch active leagues for a specific continent.

        V12.5: Added bypass_cache parameter for critical operations.

        Args:
            continent_name: Continent name (e.g., "LATAM", "ASIA", "AFRICA")
            bypass_cache: If True, skip cache and fetch fresh data (default: False)

        Returns:
            List of active league records for the continent
        """
        all_active = self.get_active_leagues(bypass_cache=bypass_cache)

        filtered = [
            league
            for league in all_active
            if league.get("continent", {}).get("name") == continent_name
        ]

        logger.info(f"Found {len(filtered)} active leagues for continent {continent_name}")
        return filtered

    def get_active_continent_blocks(self, current_utc_hour: int) -> list[str]:
        """
        Determine which continental blocks are active based on current UTC time.

        V12.5: Added validation for empty active_hours_utc arrays to detect configuration errors.

        Args:
            current_utc_hour: Current hour in UTC (0-23)

        Returns:
            List of active continent names (e.g., ["LATAM", "ASIA"])
        """
        continents = self.fetch_continents()

        active_blocks = []
        continents_without_hours = []

        for continent in continents:
            active_hours = continent.get("active_hours_utc", [])
            if not active_hours:
                # V12.5: Log warning for continents without active hours
                continents_without_hours.append(continent.get("name", "Unknown"))
                continue

            if current_utc_hour in active_hours:
                active_blocks.append(continent["name"])

        # V12.5: Log warning if any continents have empty active_hours_utc
        if continents_without_hours:
            logger.warning(
                f"⚠️ {len(continents_without_hours)} continents have empty active_hours_utc: "
                f"{continents_without_hours}. These continents will never be active."
            )

        logger.debug(f"Active continental blocks at {current_utc_hour}:00 UTC: {active_blocks}")
        return active_blocks

    def get_news_sources(self, league_id: str) -> list[dict[str, Any]]:
        """
        Fetch news sources for a specific league.

        Args:
            league_id: League UUID or ID

        Returns:
            List of news source records
        """
        cache_key = f"news_sources_{league_id}"
        return self._execute_query("news_sources", cache_key, filters={"league_id": league_id})

    def fetch_all_news_sources(self) -> list[dict[str, Any]]:
        """
        Fetch all news sources without league filter.

        Returns:
            List of all news source records
        """
        cache_key = "news_sources_all"
        return self._execute_query("news_sources", cache_key)

    def get_social_sources(self) -> list[dict[str, Any]]:
        """
        Fetch all social sources (Twitter/X handles).

        Returns:
            List of social source records
        """
        cache_key = "social_sources_all"
        return self._execute_query("social_sources", cache_key)

    def get_social_sources_for_league(self, league_id: str) -> list[dict[str, Any]]:
        """
        Fetch social sources for a specific league.

        Args:
            league_id: League UUID or ID

        Returns:
            List of social source records for the league
        """
        cache_key = f"social_sources_{league_id}"
        return self._execute_query("social_sources", cache_key, filters={"league_id": league_id})

    # V13.0: Removed dead code - get_continental_sources() was never called anywhere in the codebase
    # Verified by searching for all references across the project

    def validate_api_keys(self, leagues: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Validate API keys for active leagues.

        Logs CRITICAL warnings for invalid API keys but does not stop the bot.

        Args:
            leagues: List of league records with api_key field

        Returns:
            Dict with validation results:
            {
                "valid": ["soccer_brazil_campeonato", ...],
                "invalid": [{"api_key": "invalid_key", "league": "...", "error": "..."}],
                "total": 10
            }
        """
        valid_keys = []
        invalid_keys = []

        for league in leagues:
            api_key = league.get("api_key")
            league_name = league.get("tier_name", league.get("api_key", "Unknown"))

            if not api_key:
                invalid_keys.append(
                    {"api_key": None, "league": league_name, "error": "No API key provided"}
                )
                logger.critical(f"CRITICAL: League '{league_name}' has no API key configured")
                continue

            # Basic validation: check if it follows the expected pattern
            # The-Odds-API keys typically start with "soccer_"
            if not api_key.startswith("soccer_"):
                invalid_keys.append(
                    {
                        "api_key": api_key,
                        "league": league_name,
                        "error": "API key does not follow expected pattern (should start with 'soccer_')",
                    }
                )
                logger.critical(f"CRITICAL: Invalid API key '{api_key}' for league '{league_name}'")
                continue

            valid_keys.append(api_key)

        result = {
            "valid": valid_keys,
            "invalid": invalid_keys,
            "total": len(leagues),
            "valid_count": len(valid_keys),
            "invalid_count": len(invalid_keys),
        }

        if invalid_keys:
            logger.warning(
                f"API Key Validation: {len(invalid_keys)} invalid keys found out of {len(leagues)} total"
            )
        else:
            logger.info(f"API Key Validation: All {len(leagues)} API keys are valid")

        return result

    def update_mirror(self, force: bool = False) -> bool:
        """
        Update the local mirror with fresh data from Supabase.

        Args:
            force: If True, bypass cache and fetch fresh data

        Returns:
            True if mirror was updated successfully, False otherwise

        Note:
            When force=True, this calls invalidate_cache() which clears ALL cache entries.
            For targeted league-only invalidation, use invalidate_leagues_cache() separately.
        """
        try:
            # Invalidate cache if forcing update
            if force:
                self.invalidate_cache()

            # Fetch all data including social_sources and news_sources
            mirror_data = {
                "continents": self.fetch_continents(),
                "countries": self.fetch_countries(),
                "leagues": self.fetch_leagues(),
                "social_sources": self.get_social_sources(),
                "news_sources": self.fetch_all_news_sources(),
            }

            # Save to mirror with version and checksum
            self._save_to_mirror(mirror_data, version="V9.5")

            logger.info("✅ Local mirror updated successfully with social_sources and news_sources")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update mirror: {e}")
            return False

    # ============================================
    # V9.5: LOCAL MIRROR WITH SOCIAL_SOURCES METADATA
    # ============================================

    def create_local_mirror(self) -> bool:
        """
        Create local mirror with social_sources and news_sources metadata (V9.5).

        This function creates a comprehensive local mirror that includes:
        - Standard Supabase data (continents, countries, leagues, sources)
        - Full social_sources list from Supabase
        - Full news_sources list from Supabase
        - Social sources metadata from Nitter scraper (simplified - removed dead Layer2 fields):
          * is_convergent: Convergence status from analyzer
          * convergence_sources: JSON with web and social signal details

        REMOVED: translation, is_betting_relevant, gate_triggered_keyword (dead code - never used)

        UTF-8 encoding is ensured for Arabic and Spanish characters.
        Checksum is calculated for integrity verification.

        Returns:
            True if mirror was created successfully, False otherwise
        """
        try:
            logger.info("🔄 Creating local mirror with social_sources and news_sources metadata...")

            # Fetch standard Supabase data
            mirror_data = {
                "continents": self.fetch_continents(),
                "countries": self.fetch_countries(),
                "leagues": self.fetch_leagues(),
                "social_sources": self.get_social_sources(),
                "news_sources": self.fetch_all_news_sources(),
            }

            # Validate that social_sources and news_sources are not empty
            social_sources_count = len(mirror_data.get("social_sources", []))
            news_sources_count = len(mirror_data.get("news_sources", []))

            if social_sources_count == 0:
                logger.warning("⚠️ No social_sources found in Supabase - mirror may be incomplete")
            else:
                logger.info(f"✅ Captured {social_sources_count} social_sources")

            if news_sources_count == 0:
                logger.warning("⚠️ No news_sources found in Supabase - mirror may be incomplete")
            else:
                logger.info(f"✅ Captured {news_sources_count} news_sources")

            # Try to load social sources from Nitter cache (if available)
            social_sources_data = self._load_social_sources_from_cache()
            if social_sources_data:
                mirror_data["social_sources_tweets"] = social_sources_data
                logger.info(
                    f"✅ Loaded {len(social_sources_data.get('tweets', []))} tweets from Nitter cache"
                )
            else:
                mirror_data["social_sources_tweets"] = {"tweets": [], "last_updated": None}
                logger.info("ℹ️ No Nitter cache data available")

            # Save to mirror with UTF-8 encoding, version, and checksum
            self._save_to_mirror(mirror_data, version="V9.5")

            logger.info(
                "✅ Local mirror created successfully with social_sources and news_sources metadata"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create local mirror: {e}")
            return False

    def _load_social_sources_from_cache(self) -> dict[str, Any] | None:
        """
        Load social sources from Nitter cache with file locking.

        V12.5: Added file locking to prevent race conditions when multiple threads
        access the Nitter cache file simultaneously.

        This function reads the Nitter cache file and extracts tweet data
        with V9.5 fields for inclusion in the mirror.

        Returns:
            Dict with tweets list and last_updated timestamp, or None if cache not available
        """
        try:
            from pathlib import Path

            cache_file = Path("data/nitter_cache.json")

            if not cache_file.exists():
                logger.debug("Nitter cache file not found")
                return None

            # V12.5: Try to use file locking (Linux-specific)
            # Fall back to non-blocking read if fcntl is not available
            try:
                import fcntl

                with open(cache_file, "r", encoding="utf-8") as f:
                    # Acquire exclusive lock (non-blocking)
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        cache_data = json.load(f)
                        logger.debug("✅ Nitter cache loaded with file locking")
                    except BlockingIOError:
                        logger.warning("⚠️ Nitter cache file is locked by another process, skipping")
                        return None
            except ImportError:
                # fcntl not available (e.g., Windows), fall back to simple read
                logger.debug("fcntl not available, loading cache without file locking")
                with open(cache_file, encoding="utf-8") as f:
                    cache_data = json.load(f)

            # Extract tweets from cache (simplified - removed dead Layer2 fields)
            tweets = []
            for handle_key, entry in cache_data.items():
                if isinstance(entry, dict) and "tweets" in entry:
                    for tweet in entry["tweets"]:
                        # REMOVED: translation, is_betting_relevant, gate_triggered_keyword (dead code)
                        # KEPT: is_convergent, convergence_sources (actively used by convergence detection)
                        tweet_data = {
                            "handle": handle_key,
                            "date": tweet.get("date"),
                            "content": tweet.get("content"),
                            "topics": tweet.get("topics", []),
                            "relevance_score": tweet.get("relevance_score", 0.0),
                            "is_convergent": tweet.get("is_convergent"),
                            "convergence_sources": tweet.get("convergence_sources"),
                        }
                        tweets.append(tweet_data)

            # Get last updated timestamp from cache
            last_updated = None
            if tweets:
                # Use the most recent tweet date as last_updated
                dates = [t.get("date") for t in tweets if t.get("date")]
                if dates:
                    last_updated = max(dates)

            logger.debug(f"Loaded {len(tweets)} tweets from Nitter cache")

            return {"tweets": tweets, "last_updated": last_updated}

        except Exception as e:
            logger.warning(f"Failed to load social sources from cache: {e}")
            return None

    def refresh_mirror(self) -> bool:
        """
        Refresh the local mirror at the start of a cycle.

        This function is called at the start of each 6-hour cycle to ensure
        the mirror has the latest social_sources data. It is idempotent
        and can be called multiple times safely.

        Returns:
            True if mirror was refreshed successfully, False otherwise
        """
        try:
            logger.info("🔄 Refreshing local mirror at cycle start...")

            # Create fresh mirror with latest data
            success = self.create_local_mirror()

            if success:
                logger.info("✅ Mirror refreshed successfully")
            else:
                logger.warning("⚠️ Mirror refresh failed, will use existing mirror")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to refresh mirror: {e}")
            return False

    def invalidate_cache(self, cache_key: str | None = None) -> None:
        """
        Invalidate cache entries (thread-safe).

        Args:
            cache_key: Specific cache key to invalidate. If None, clears all cache.
        """
        # V11.1: Thread-safe cache invalidation
        # V12.1: Use lock acquisition with monitoring
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                if cache_key:
                    self._cache.pop(cache_key, None)
                    self._cache_timestamps.pop(cache_key, None)
                    logger.info(f"Invalidated cache for key: {cache_key}")
                else:
                    self._cache.clear()
                    self._cache_timestamps.clear()
                    logger.info("Invalidated all cache")
            finally:
                self._cache_lock.release()
        else:
            logger.warning(f"Failed to acquire cache lock for invalidation: {cache_key}")

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_entries": len(self._cache),
            "cache_keys": list(self._cache.keys()),
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "connected": self._connected,
            "mirror_exists": MIRROR_FILE_PATH.exists(),
        }

    def test_connection(self) -> bool:
        """
        Test Supabase connectivity by querying the continents table.

        Returns:
            True if connection is successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.error("Not connected to Supabase")
            return False

        try:
            response = self._client.table("continents").select("*").limit(1).execute()
            data = response.data if hasattr(response, "data") else []
            logger.info(f"Connection test successful. Found {len(data)} continents")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            self._connected = False
            self._connection_error = str(e)
            return False


def get_supabase() -> SupabaseProvider:
    """
    Get the singleton SupabaseProvider instance.

    Returns:
        The single SupabaseProvider instance
    """
    return SupabaseProvider()


# Convenience functions for direct access
def fetch_continents() -> list[dict[str, Any]]:
    """Convenience function to fetch continents."""
    return get_supabase().fetch_continents()


def fetch_countries(continent_id: str | None = None) -> list[dict[str, Any]]:
    """Convenience function to fetch countries."""
    return get_supabase().fetch_countries(continent_id)


def fetch_leagues(country_id: str | None = None) -> list[dict[str, Any]]:
    """Convenience function to fetch leagues."""
    return get_supabase().fetch_leagues(country_id)


def fetch_sources(league_id: str | None = None) -> list[dict[str, Any]]:
    """Convenience function to fetch sources."""
    return get_supabase().fetch_sources(league_id)


def fetch_hierarchical_map() -> dict[str, Any]:
    """Convenience function to fetch the complete hierarchical map."""
    return get_supabase().fetch_hierarchical_map()


def create_local_mirror() -> bool:
    """Convenience function to create local mirror with social_sources metadata."""
    return get_supabase().create_local_mirror()


def refresh_mirror() -> bool:
    """Convenience function to refresh local mirror at cycle start."""
    return get_supabase().refresh_mirror()


if __name__ == "__main__":
    # Test the Supabase provider
    print("=" * 60)
    print("SupabaseProvider - Connection Test")
    print("=" * 60)

    provider = get_supabase()

    # Test connection
    print("\n1. Testing connection...")
    if provider.test_connection():
        print("✅ Connection successful")
    else:
        print(f"❌ Connection failed: {provider.get_connection_error()}")

    # Fetch continents
    print("\n2. Fetching continents...")
    continents = provider.fetch_continents()
    print(f"✅ Found {len(continents)} continents")
    for continent in continents[:5]:
        print(f"   - {continent.get('id')}: {continent.get('name')}")

    # Fetch hierarchical map
    print("\n3. Fetching hierarchical map...")
    hierarchy = provider.fetch_hierarchical_map()
    print(f"✅ Built hierarchy with {len(hierarchy['continents'])} continents")

    # Cache stats
    print("\n4. Cache statistics...")
    stats = provider.get_cache_stats()
    print(f"✅ Cache entries: {stats['cache_entries']}")
    print(f"✅ Connected: {stats['connected']}")
    print(f"✅ Mirror exists: {stats['mirror_exists']}")

    print("\n" + "=" * 60)
    print("Supabase Bridge Active. 1-hour Cache and Mirroring established.")
    print("=" * 60)
