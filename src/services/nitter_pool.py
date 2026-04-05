"""
Nitter Instance Pool Manager
============================
Manages a pool of Nitter instances with circuit breaker pattern to handle
failures and automatically rotate through healthy instances.

This module provides:
- CircuitBreaker: Prevents cascading failures by stopping calls to unhealthy instances
- NitterPool: Manages instance rotation and health tracking
- Round-robin load balancing across healthy instances

Stealth Scraping (V11.0):
- Uses Scrapling library with TLS fingerprint spoofing to bypass WAFs
- Automatically handles browser impersonation (Chrome by default)
- Removes need for manual User-Agent rotation
"""

import asyncio
import logging
import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from scrapling import AsyncFetcher, Fetcher

from src.config.nitter_instances import (
    CIRCUIT_BREAKER_CONFIG,
    NITTER_INSTANCES,
    ROUND_ROBIN_CONFIG,
    TRANSIENT_ERROR_CONFIG,
)

logger = logging.getLogger(__name__)

# Note: User-Agent rotation removed - Scrapling handles stealth headers automatically
# via the 'stealthy_headers' parameter (enabled by default)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls allowed
    OPEN = "open"  # Circuit is open, calls blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


class NitterPoolExhaustedError(Exception):
    """
    Raised when all Nitter instances have been tried and none succeeded.

    This signals the caller to activate fallback mechanisms (e.g., Brave Search).

    Attributes:
        username: The Twitter username that was being fetched
        instances_tried: Number of instances that were tried
        last_error: The last error that occurred
    """

    def __init__(
        self,
        message: str,
        username: str = "",
        instances_tried: int = 0,
        last_error: Optional[str] = None,
    ):
        super().__init__(message)
        self.username = username
        self.instances_tried = instances_tried
        self.last_error = last_error


# Cloudflare detection indicators (copied from nitter_fallback_scraper.py for consistency)
CLOUDFLARE_INDICATORS = [
    "cloudflare",
    "captcha",
    "challenge platform",
    "attention required",
    "checking your browser",
    "ray id",
    "cf_chl_rc_i",
]


@dataclass
class InstanceHealth:
    """
    Tracks health metrics for a single Nitter instance.

    Unified health tracking for both NitterPool and NitterFallbackScraper.
    Includes all fields from both implementations for consistency.
    """

    url: str
    # Circuit breaker state (from nitter_pool.py)
    state: CircuitState = CircuitState.CLOSED
    # Health status (from nitter_fallback_scraper.py)
    is_healthy: bool = True
    # Failure tracking (both implementations)
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    # Additional tracking (from nitter_fallback_scraper.py)
    last_check: Optional[float] = None
    transient_failures: int = 0  # Network timeouts, connection errors
    permanent_failures: int = 0  # 403, 429, blocked
    # Call statistics (both implementations)
    total_calls: int = 0
    successful_calls: int = 0


class CircuitBreaker:
    """
    Circuit breaker implementation for Nitter instances.

    Automatically opens (stops using an instance) after 3 consecutive failures
    and closes (retries) after a 10-minute cooldown.

    States:
    - CLOSED: Normal operation, all calls are allowed
    - OPEN: Circuit is tripped, calls are blocked
    - HALF_OPEN: Testing if service has recovered, limited calls allowed
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_CONFIG["failure_threshold"],
        recovery_timeout: int = CIRCUIT_BREAKER_CONFIG["recovery_timeout"],
        half_open_max_calls: int = CIRCUIT_BREAKER_CONFIG["half_open_max_calls"],
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Number of calls allowed in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        # Thread safety: Add lock for protecting circuit breaker state
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    def can_call(self) -> bool:
        """
        Check if a call is allowed based on current state.

        Returns:
            True if call is allowed, False otherwise
        """
        if self._state == CircuitState.CLOSED:
            return True
        elif self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time and (
                time.time() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                return True
            return False
        elif self._state == CircuitState.HALF_OPEN:
            # Allow limited calls in HALF_OPEN state
            return self._half_open_calls < self.half_open_max_calls
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                # If successful in HALF_OPEN, close the circuit
                if self._half_open_calls >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    logger.info("✅ [CIRCUIT-BREAKER] Circuit CLOSED - Recovery successful")
            else:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()

            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"⚠️ [CIRCUIT-BREAKER] Circuit OPENED - "
                    f"{self._consecutive_failures} consecutive failures"
                )

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary containing circuit breaker metrics
        """
        return {
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
            "recovery_timeout": self.recovery_timeout,
            "half_open_calls": self._half_open_calls,
        }


class NitterPool:
    """
    Manages a pool of Nitter instances with circuit breakers and round-robin rotation.

    Features:
    - Circuit breaker pattern for each instance
    - Round-robin load balancing across healthy instances
    - Automatic instance health tracking
    - Graceful fallback when all instances are unhealthy
    """

    def __init__(
        self,
        instances: Optional[List[str]] = None,
        failure_threshold: int = CIRCUIT_BREAKER_CONFIG["failure_threshold"],
        recovery_timeout: int = CIRCUIT_BREAKER_CONFIG["recovery_timeout"],
    ):
        """
        Initialize Nitter instance pool.

        Args:
            instances: List of Nitter instance URLs (defaults to config)
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before retrying failed instances
        """
        self.instances = instances or NITTER_INSTANCES.copy()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.health: Dict[str, InstanceHealth] = {}
        self._round_robin_index = ROUND_ROBIN_CONFIG["initial_index"]
        # CRITICAL BUG #2 FIX: Use threading.Lock instead of asyncio.Lock for consistency
        # asyncio.Lock doesn't work when called from non-async contexts (e.g., twitter_intel_cache.py:1207)
        self._lock = threading.Lock()
        # Thread safety: Add lock for protecting InstanceHealth modifications
        self._health_lock = threading.Lock()

        # Initialize circuit breakers for each instance
        for instance in self.instances:
            self.circuit_breakers[instance] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            self.health[instance] = InstanceHealth(url=instance)

        logger.info(f"🐦 [NITTER-POOL] Initialized with {len(self.instances)} instances")

    def get_healthy_instance(self) -> Optional[str]:
        """
        Get a healthy Nitter instance using round-robin logic.

        Iterates through instances in round-robin order and returns the first
        healthy instance (circuit is not OPEN). If all instances are unhealthy,
        returns None.

        CRITICAL BUG #2 FIX: Changed from async to sync method to work with threading.Lock
        This ensures thread safety when called from both async and non-async contexts.

        MODERATE BUG #9 FIX: Only increment index for healthy instances to improve
        round-robin effectiveness. Previously, the index was incremented for all
        instances (healthy or not), which reduced efficiency when many instances
        were unhealthy.

        Returns:
            URL of a healthy instance, or None if all are unhealthy
        """
        with self._lock:
            # MODERATE BUG #9 FIX: Build list of healthy instances first
            # This improves efficiency by only iterating through healthy instances
            # instead of checking all instances (including unhealthy ones)
            healthy_instances = [
                instance
                for instance in self.instances
                if self.circuit_breakers[instance].can_call()
            ]

            if not healthy_instances:
                logger.warning("⚠️ [NITTER-POOL] No healthy instances available")
                return None

            # Use round-robin on healthy instances only
            # This ensures we don't waste time checking unhealthy instances
            healthy_index = self._round_robin_index % len(healthy_instances)
            selected_instance = healthy_instances[healthy_index]

            # Increment index for next call (use original instance list size to maintain distribution)
            self._round_robin_index = (self._round_robin_index + 1) % len(self.instances)

            return selected_instance

    def record_success(self, instance: str) -> None:
        """
        Record a successful call to an instance.

        Thread-safe: Uses threading.Lock to protect InstanceHealth modifications.
        CRITICAL BUG #3 FIX: Properly synchronize CircuitBreaker state access
        by calling record_success() which uses its own lock, then reading state
        under the same lock to avoid race conditions.

        Args:
            instance: URL of the instance
        """
        if instance in self.circuit_breakers:
            # First, record success in CircuitBreaker (uses its own lock)
            self.circuit_breakers[instance].record_success()

            # Then, update InstanceHealth under _health_lock
            with self._health_lock:
                self.health[instance].consecutive_failures = 0
                self.health[instance].last_success_time = time.time()
                self.health[instance].successful_calls += 1
                self.health[instance].total_calls += 1
                # CRITICAL BUG #3 FIX: Get state from CircuitBreaker after record_success()
                # This ensures we read the state after it's been updated under CircuitBreaker's lock
                self.health[instance].state = self.circuit_breakers[instance].state
                # Update unified fields
                self.health[instance].is_healthy = True
                self.health[instance].transient_failures = 0
                self.health[instance].permanent_failures = 0
                self.health[instance].last_check = time.time()
                logger.debug(f"✅ [NITTER-POOL] Success recorded for {instance}")

    def record_failure(self, instance: str, is_transient: bool = False) -> None:
        """
        Record a failed call to an instance.

        Thread-safe: Uses threading.Lock to protect InstanceHealth modifications.
        CRITICAL BUG #3 FIX: Properly synchronize CircuitBreaker state access
        by calling record_failure() which uses its own lock, then reading state
        under the same lock to avoid race conditions.

        Args:
            instance: URL of the instance
            is_transient: Whether the failure is transient (network timeout, etc.)
        """
        if instance in self.circuit_breakers:
            # First, record failure in CircuitBreaker (uses its own lock)
            self.circuit_breakers[instance].record_failure()

            # Then, update InstanceHealth under _health_lock
            with self._health_lock:
                self.health[instance].consecutive_failures += 1
                self.health[instance].last_failure_time = time.time()
                self.health[instance].total_calls += 1
                # CRITICAL BUG #3 FIX: Get state from CircuitBreaker after record_failure()
                # This ensures we read the state after it's been updated under CircuitBreaker's lock
                self.health[instance].state = self.circuit_breakers[instance].state
                # Update unified fields
                self.health[instance].last_check = time.time()
                # SERIOUS BUG #4 FIX: Distinguish between transient and permanent failures
                if is_transient:
                    self.health[instance].transient_failures += 1
                else:
                    self.health[instance].permanent_failures += 1
                # Check if instance should be marked unhealthy
                if (
                    self.health[instance].consecutive_failures
                    >= self.circuit_breakers[instance].failure_threshold
                ):
                    self.health[instance].is_healthy = False
                logger.warning(f"❌ [NITTER-POOL] Failure recorded for {instance}")

    def get_instance_health(self, instance: str) -> Optional[InstanceHealth]:
        """
        Get health information for a specific instance.

        MODERATE BUG #8 FIX: Added lock protection to prevent inconsistent reads
        when multiple threads are accessing health data simultaneously.

        Args:
            instance: URL of the instance

        Returns:
            InstanceHealth object, or None if instance not found
        """
        with self._health_lock:
            # Return a copy to prevent external modifications
            health = self.health.get(instance)
            if health is not None:
                # Return a deep copy to prevent external modifications
                from dataclasses import replace

                return replace(health)
            return None

    def get_all_health(self) -> Dict[str, InstanceHealth]:
        """
        Get health information for all instances.

        MODERATE BUG #8 FIX: Added lock protection to prevent inconsistent reads
        when multiple threads are accessing health data simultaneously.

        Returns:
            Dictionary mapping instance URLs to InstanceHealth objects
        """
        with self._health_lock:
            # Return a deep copy to prevent external modifications
            from dataclasses import replace

            return {k: replace(v) for k, v in self.health.items()}

    def get_healthy_instances(self) -> List[str]:
        """
        Get list of all currently healthy instances.

        Returns:
            List of instance URLs that are not in OPEN state
        """
        healthy: list[str] = []
        for instance, circuit_breaker in self.circuit_breakers.items():
            if circuit_breaker.can_call():
                healthy.append(instance)
        return healthy

    def reset_instance(self, instance: str) -> bool:
        """
        Reset circuit breaker for a specific instance.

        Thread-safe: Uses threading.Lock to protect InstanceHealth modifications.

        Args:
            instance: URL of the instance

        Returns:
            True if reset was successful, False if instance not found
        """
        with self._health_lock:
            if instance in self.circuit_breakers:
                self.circuit_breakers[instance].reset()
                self.health[instance].consecutive_failures = 0
                # Synchronize InstanceHealth.state with CircuitBreaker state
                self.health[instance].state = self.circuit_breakers[instance].state
                return True
            return False

    def reset_all(self) -> None:
        """Reset all circuit breakers to initial state."""
        for instance in self.instances:
            self.reset_instance(instance)

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get overall pool statistics.

        Returns:
            Dictionary containing pool-wide metrics
        """
        healthy_count = len(self.get_healthy_instances())
        total_calls = sum(h.total_calls for h in self.health.values())
        successful_calls = sum(h.successful_calls for h in self.health.values())

        return {
            "total_instances": len(self.instances),
            "healthy_instances": healthy_count,
            "unhealthy_instances": len(self.instances) - healthy_count,
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": total_calls - successful_calls,
            "success_rate": successful_calls / total_calls if total_calls > 0 else 0.0,
            "round_robin_index": self._round_robin_index,
        }

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """
        Normalize a date string to UTC datetime object and return as ISO8601 string.

        Args:
            date_str: Date string in various formats

        Returns:
            ISO8601 formatted UTC datetime string, or None if parsing fails
        """
        try:
            dt = date_parser.parse(date_str)
            # Convert to UTC if timezone-aware
            if dt.tzinfo is not None:
                from datetime import timezone

                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.isoformat() if dt else None
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-POOL] Failed to parse date '{date_str}': {e}")
            return None

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Check if an error is transient (network timeout, connection error, etc.).

        SERIOUS BUG #4 FIX: Implement transient error detection to distinguish
        between temporary network issues and permanent failures (403, 429).

        Args:
            error: The exception to check

        Returns:
            True if the error is transient, False otherwise
        """
        error_type_name = type(error).__name__
        return error_type_name in TRANSIENT_ERROR_CONFIG["error_types"]

    def _detect_cloudflare_block(self, content: str) -> bool:
        """
        Detect if content indicates a Cloudflare challenge/block.

        COVE FIX: Add Cloudflare detection to distinguish between:
        - Empty response (user has no tweets)
        - Cloudflare challenge (instance is blocked)

        Args:
            content: HTML/text content to check

        Returns:
            True if Cloudflare challenge detected, False otherwise
        """
        if not content:
            return False
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in CLOUDFLARE_INDICATORS)

    def _clean_tweet_text(self, text: str) -> str:
        """
        Clean HTML tags and links from tweet text.

        Args:
            text: Raw tweet text with HTML

        Returns:
            Cleaned text without HTML tags and links
        """
        # Remove HTML tags
        soup = BeautifulSoup(text, "lxml")
        clean_text = soup.get_text()

        # Remove extra whitespace
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        return clean_text

    def _extract_topics_from_content(self, content: str) -> List[str]:
        """
        Extract betting-relevant topics from tweet content.

        Args:
            content: Tweet content

        Returns:
            List of detected topics (injury, lineup, transfer, etc.)
        """
        if not content:
            return []

        content_lower = content.lower()
        topics: list[str] = []

        # Topic detection patterns (same as TwitterIntelCache)
        topic_patterns = {
            "injury": [
                "injury",
                "injured",
                "out",
                "sidelined",
                "ruled out",
                "doubt",
                "infortunio",
                "lesión",
                "sakatlık",
                "kontuzja",
            ],
            "lineup": [
                "lineup",
                "starting",
                "xi",
                "squad",
                "team news",
                "formation",
                "formazione",
                "alineación",
                "kadro",
                "skład",
            ],
            "transfer": [
                "transfer",
                "loan",
                "signed",
                "joined",
                "deal",
                "agreement",
            ],
        }

        # Check each topic category
        for topic, keywords in topic_patterns.items():
            if any(keyword in content_lower for keyword in keywords):
                if topic not in topics:
                    topics.append(topic)

        return topics

    def _parse_rss_response(
        self, content: str, instance: str, username: str
    ) -> List[Dict[str, Any]]:
        """
        Parse RSS XML response to extract tweets.

        Args:
            content: RSS XML content
            instance: Nitter instance URL (for constructing tweet URLs)
            username: Twitter username

        Returns:
            List of standardized tweet dictionaries
        """
        tweets: list[dict[str, Any]] = []
        try:
            soup = BeautifulSoup(content, "xml")
            items = soup.find_all("item")

            for item in items:
                # Extract tweet ID from link
                link = item.find("link")
                if not link:
                    continue

                link_text = link.get_text()
                tweet_id = link_text.split("/")[-1]

                # Extract content
                description = item.find("description")
                if not description:
                    continue

                content_text = description.get_text()

                # Extract and normalize date
                pub_date = item.find("pubDate")
                if not pub_date:
                    continue

                published_at = self._normalize_date(pub_date.get_text())
                if not published_at:
                    continue

                # Clean the content
                clean_content = self._clean_tweet_text(content_text)

                # Extract topics
                topics = self._extract_topics_from_content(clean_content)

                tweets.append(
                    {
                        "content": clean_content,
                        "published_at": published_at,
                        "url": link_text,
                        "id": tweet_id,
                        "topics": topics,
                        "raw_data": {"source": "nitter", "url": link_text},
                    }
                )

            logger.debug(f"✅ [NITTER-POOL] Parsed {len(tweets)} tweets from RSS for @{username}")

        except Exception as e:
            logger.error(f"❌ [NITTER-POOL] Failed to parse RSS response: {e}")

        return tweets

    def _parse_html_response(
        self, content: str, instance: str, username: str
    ) -> List[Dict[str, Any]]:
        """
        Parse HTML response to extract tweets (fallback method).

        Args:
            content: HTML content
            instance: Nitter instance URL (for constructing tweet URLs)
            username: Twitter username

        Returns:
            List of standardized tweet dictionaries
        """
        tweets: list[dict[str, Any]] = []
        try:
            soup = BeautifulSoup(content, "lxml")

            # Nitter HTML structure: tweets are in .timeline-item divs
            timeline_items = soup.find_all("div", class_="timeline-item")

            for item in timeline_items:
                # Extract tweet ID from data-id attribute
                tweet_id = item.get("data-id")
                if not tweet_id:
                    continue

                # Extract tweet content
                tweet_content = item.find("div", class_="tweet-content")
                if not tweet_content:
                    continue

                content_text = tweet_content.get_text()

                # Extract date
                tweet_date = item.find("span", class_="tweet-date")
                if not tweet_date:
                    continue

                date_attr = tweet_date.get("title")
                if isinstance(date_attr, str):
                    date_text = date_attr
                else:
                    date_text = tweet_date.get_text()
                published_at = self._normalize_date(date_text)
                if not published_at:
                    continue

                # Clean the content
                clean_content = self._clean_tweet_text(content_text)

                # Extract topics
                topics = self._extract_topics_from_content(clean_content)

                # Construct URL
                url = f"{instance}/{username}/status/{tweet_id}"

                tweets.append(
                    {
                        "content": clean_content,
                        "published_at": published_at,
                        "url": url,
                        "id": tweet_id,
                        "topics": topics,
                        "raw_data": {"source": "nitter", "url": url},
                    }
                )

            logger.debug(f"✅ [NITTER-POOL] Parsed {len(tweets)} tweets from HTML for @{username}")

        except Exception as e:
            logger.error(f"❌ [NITTER-POOL] Failed to parse HTML response: {e}")

        return tweets

    def _browser_fetch(self, url: str) -> str:
        """
        Fetch content using synchronous browser-like fetcher.

        This method uses the synchronous Fetcher with browser impersonation
        to handle cases where AsyncFetcher fails (e.g., 403/Captcha).
        This is a blocking operation and should be run in a thread.

        Args:
            url: URL to fetch

        Returns:
            Response text content

        Raises:
            Exception: If the fetch fails
        """
        try:
            # V15.0 FIX: Use Fetcher class directly (no instantiation).
            # Scrapling 0.4: Fetcher.get is already a bound method on a pre-created singleton.
            # Calling Fetcher() triggers a deprecation warning and is a no-op.
            response = Fetcher.get(url, timeout=15, impersonate="chrome", stealthy_headers=True)

            # Return response text
            return response.text
        except Exception as e:
            logger.error(f"❌ [NITTER-POOL] Browser fetch failed for {url}: {e}")
            raise

    async def fetch_tweets_async(
        self, username: str, max_retries: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch tweets from a Twitter username using Nitter instances with hybrid scraping.

        Hybrid Scraping Logic (V11.1):
        1. Fast Path: AsyncFetcher (awaitable) - RSS first, then HTML parsing
        2. Slow Path (Fallback): If HTTP fails (403/Captcha), trigger Browser via asyncio.to_thread

        COVE FIX: Automatically retries ALL available instances until one succeeds.
        Previously used max_retries=3 which was too limiting with 13 instances available.

        When all instances fail, raises NitterPoolExhaustedError to signal caller
        to activate fallback mechanisms (e.g., Brave Search).

        Args:
            username: Twitter username (without @)
            max_retries: Maximum number of instance retries.
                        None = try all instances (len(self.instances))
                        This ensures all instances are tried before giving up.

        Returns:
            List of standardized tweet dictionaries with keys:
            - content: str - Cleaned tweet text
            - published_at: datetime - UTC timestamp
            - url: str - Tweet URL
            - id: str - Tweet ID

        Raises:
            NitterPoolExhaustedError: When all instances have been tried and none succeeded
        """
        # Strip @ prefix if present
        username = username.lstrip("@")

        tweets: list[dict[str, Any]] = []
        retry_count = 0

        # COVE FIX: Use all instances by default, not just 3
        # If max_retries is None, use len(self.instances) to try all instances
        effective_max_retries = max_retries if max_retries is not None else len(self.instances)

        # Track instances tried and last error for NitterPoolExhaustedError
        instances_tried = 0
        last_error = None

        # V11.0 optimization: use AsyncFetcher class directly (no instantiation).
        # Scrapling 0.4: AsyncFetcher.get is already a bound method on a pre-created singleton.
        # Calling AsyncFetcher() triggers a deprecated deprecation warning and is a no-op.
        # Note: Scrapling handles User-Agent rotation automatically via stealthy_headers
        fetcher = AsyncFetcher

        while retry_count < effective_max_retries:
            # CRITICAL BUG #2 FIX: get_healthy_instance() is now sync, no await needed
            instance = self.get_healthy_instance()
            if not instance:
                # COVE FIX: When no healthy instances available, raise NitterPoolExhaustedError
                # This signals the caller to activate fallback mechanisms
                raise NitterPoolExhaustedError(
                    f"❌ [NITTER-POOL] All instances unhealthy or exhausted for @{username} "
                    f"(tried {instances_tried} instances)",
                    username=username,
                    instances_tried=instances_tried,
                    last_error=last_error,
                )

            logger.debug(
                f"🔄 [NITTER-POOL] Attempting to fetch tweets for @{username} from {instance} "
                f"(attempt {retry_count + 1}/{effective_max_retries})"
            )

            try:
                # Attempt 1: Try RSS feed first (Fast Path)
                rss_url = f"{instance}/{username}/rss"
                try:
                    response = await fetcher.get(
                        rss_url, timeout=10, impersonate="chrome", stealthy_headers=True
                    )
                    if response.status == 200:
                        # Note: Scrapling's Response.body contains the raw bytes content
                        # response.text may be empty, so we use body and decode it
                        # CRITICAL BUG #1 FIX: Check if response.body is None before decoding
                        if response.body is None:
                            logger.warning(f"⚠️ [NITTER-POOL] response.body is None for {rss_url}")
                            # Try using response.text as fallback
                            rss_content = response.text if response.text else ""
                        else:
                            rss_content = response.body.decode("utf-8", errors="ignore")
                        tweets = self._parse_rss_response(rss_content, instance, username)

                        if tweets:
                            self.record_success(instance)
                            logger.info(
                                f"✅ [NITTER-POOL] Successfully fetched "
                                f"{len(tweets)} tweets "
                                f"for @{username} via RSS from {instance}"
                            )
                            return tweets
                        else:
                            # COVE FIX: Check if this is a Cloudflare block or genuinely empty
                            if self._detect_cloudflare_block(rss_content):
                                logger.warning(
                                    f"⚠️ [NITTER-POOL] RSS blocked by Cloudflare for @{username} on {instance}"
                                )
                                self.record_failure(instance, is_transient=False)
                            else:
                                logger.debug(
                                    f"⚠️ [NITTER-POOL] RSS response was empty for @{username} (genuinely no tweets)"
                                )
                    elif response.status == 404:
                        # SERIOUS BUG #6 FIX: Record failure for 404 responses
                        # If an instance consistently returns 404, it should be marked as unhealthy
                        logger.warning(
                            f"⚠️ [NITTER-POOL] User @{username} not found (404) on {instance}"
                        )
                        # Record failure but don't retry (user not found is permanent)
                        self.record_failure(instance, is_transient=False)
                        return []
                    elif response.status in (403, 429, 500, 502, 503, 504):
                        # SERIOUS BUG #5 FIX: Extend browser fallback to server errors (500, 502, 503, 504)
                        # These errors can benefit from browser impersonation
                        logger.warning(
                            f"⚠️ [NITTER-POOL] RSS blocked ({response.status}) for @{username}, "
                            f"trying browser fallback..."
                        )
                        try:
                            # Use asyncio.to_thread to run blocking browser fetch in a thread
                            rss_content = await asyncio.to_thread(self._browser_fetch, rss_url)
                            tweets = self._parse_rss_response(rss_content, instance, username)

                            if tweets:
                                self.record_success(instance)
                                logger.info(
                                    f"✅ [NITTER-POOL] Successfully fetched "
                                    f"{len(tweets)} tweets "
                                    f"for @{username} via RSS (Browser Fallback) from {instance}"
                                )
                                return tweets
                        except Exception as browser_error:
                            logger.debug(
                                f"⚠️ [NITTER-POOL] Browser fallback failed for RSS: {browser_error}"
                            )
                    else:
                        logger.debug(
                            f"⚠️ [NITTER-POOL] RSS returned status {response.status} for @{username}"
                        )
                except (Exception, asyncio.TimeoutError) as e:
                    # SERIOUS BUG #4 FIX: Detect transient errors and record accordingly
                    is_transient = self._is_transient_error(e)
                    logger.debug(
                        f"⚠️ [NITTER-POOL] RSS request failed for @{username}: {e} (transient={is_transient})"
                    )

                # Attempt 2: Fallback to HTML parsing (Fast Path)
                html_url = f"{instance}/{username}"
                try:
                    response = await fetcher.get(
                        html_url, timeout=10, impersonate="chrome", stealthy_headers=True
                    )
                    if response.status == 200:
                        # Note: Scrapling's Response.body contains the raw bytes content
                        # response.text may be empty, so we use body and decode it
                        # CRITICAL BUG #1 FIX: Check if response.body is None before decoding
                        if response.body is None:
                            logger.warning(f"⚠️ [NITTER-POOL] response.body is None for {html_url}")
                            # Try using response.text as fallback
                            html_content = response.text if response.text else ""
                        else:
                            html_content = response.body.decode("utf-8", errors="ignore")
                        tweets = self._parse_html_response(html_content, instance, username)

                        if tweets:
                            self.record_success(instance)
                            logger.info(
                                f"✅ [NITTER-POOL] Successfully fetched "
                                f"{len(tweets)} tweets "
                                f"for @{username} via HTML from {instance}"
                            )
                            return tweets
                        else:
                            # COVE FIX: Check if this is a Cloudflare block or genuinely empty
                            if self._detect_cloudflare_block(html_content):
                                logger.warning(
                                    f"⚠️ [NITTER-POOL] HTML blocked by Cloudflare for @{username} on {instance}"
                                )
                                self.record_failure(instance, is_transient=False)
                            else:
                                logger.debug(
                                    f"⚠️ [NITTER-POOL] HTML response was empty for @{username} (genuinely no tweets)"
                                )
                    elif response.status == 404:
                        # SERIOUS BUG #6 FIX: Record failure for 404 responses
                        # If an instance consistently returns 404, it should be marked as unhealthy
                        logger.warning(
                            f"⚠️ [NITTER-POOL] User @{username} not found (404) on {instance}"
                        )
                        # Record failure but don't retry (user not found is permanent)
                        self.record_failure(instance, is_transient=False)
                        return []
                    elif response.status in (403, 429, 500, 502, 503, 504):
                        # SERIOUS BUG #5 FIX: Extend browser fallback to server errors (500, 502, 503, 504)
                        # These errors can benefit from browser impersonation
                        logger.warning(
                            f"⚠️ [NITTER-POOL] HTML blocked ({response.status}) for @{username}, "
                            f"trying browser fallback..."
                        )
                        try:
                            # Use asyncio.to_thread to run blocking browser fetch in a thread
                            html_content = await asyncio.to_thread(self._browser_fetch, html_url)
                            tweets = self._parse_html_response(html_content, instance, username)

                            if tweets:
                                self.record_success(instance)
                                logger.info(
                                    f"✅ [NITTER-POOL] Successfully fetched "
                                    f"{len(tweets)} tweets "
                                    f"for @{username} via HTML (Browser Fallback) from {instance}"
                                )
                                return tweets
                        except Exception as browser_error:
                            logger.debug(
                                f"⚠️ [NITTER-POOL] Browser fallback failed for HTML: {browser_error}"
                            )
                    else:
                        logger.debug(
                            f"⚠️ [NITTER-POOL] HTML returned status "
                            f"{response.status} for @{username}"
                        )
                except (Exception, asyncio.TimeoutError) as e:
                    # SERIOUS BUG #4 FIX: Detect transient errors and record accordingly
                    is_transient = self._is_transient_error(e)
                    logger.debug(
                        f"⚠️ [NITTER-POOL] HTML request failed for @{username}: {e} (transient={is_transient})"
                    )

                # Both attempts failed - record failure and retry with next instance
                # SERIOUS BUG #4 FIX: Track whether the failure was transient
                # Note: We can't determine is_transient here without the exception object
                # For now, we'll use a conservative approach and treat as permanent
                self.record_failure(instance, is_transient=False)
                instances_tried += 1
                last_error = "RSS+HTML both empty or failed"
                retry_count += 1

            except Exception as e:
                # Unexpected error - record failure and retry
                # SERIOUS BUG #4 FIX: Detect transient errors
                is_transient = self._is_transient_error(e)
                logger.error(
                    f"❌ [NITTER-POOL] Unexpected error fetching tweets for @{username}: {e} (transient={is_transient})"
                )
                self.record_failure(instance, is_transient=is_transient)
                instances_tried += 1
                last_error = str(e)
                retry_count += 1

        # All retries exhausted - COVE FIX: Raise NitterPoolExhaustedError to signal caller
        # This enables fallback mechanisms (e.g., Brave Search) to be activated
        logger.error(
            f"❌ [NITTER-POOL] Failed to fetch tweets for @{username} after {instances_tried} instances tried"
        )
        raise NitterPoolExhaustedError(
            f"❌ [NITTER-POOL] All instances exhausted for @{username} after {instances_tried} attempts",
            username=username,
            instances_tried=instances_tried,
            last_error=last_error,
        )


# Singleton instance for global access
_nitter_pool: Optional[NitterPool] = None
_nitter_pool_lock = threading.Lock()


def get_nitter_pool() -> NitterPool:
    """
    Get the global NitterPool singleton instance.

    Uses double-checked locking pattern for thread safety:
    1. First check without lock (fast path)
    2. Acquire lock if instance is None
    3. Second check with lock (prevent race condition)
    4. Create instance if still None

    Returns:
        The global NitterPool instance
    """
    global _nitter_pool
    # First check without lock (fast path)
    if _nitter_pool is None:
        # Acquire lock and check again (double-checked locking)
        with _nitter_pool_lock:
            # Second check with lock (prevent race condition)
            if _nitter_pool is None:
                _nitter_pool = NitterPool()
    return _nitter_pool


def reset_nitter_pool() -> None:
    """Reset the global NitterPool singleton instance."""
    global _nitter_pool
    with _nitter_pool_lock:
        _nitter_pool = None
