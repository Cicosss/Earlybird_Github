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
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from scrapling import AsyncFetcher, Fetcher

from src.config.nitter_instances import (
    CIRCUIT_BREAKER_CONFIG,
    NITTER_INSTANCES,
    ROUND_ROBIN_CONFIG,
)

logger = logging.getLogger(__name__)

# Note: User-Agent rotation removed - Scrapling handles stealth headers automatically
# via the 'stealthy_headers' parameter (enabled by default)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls allowed
    OPEN = "open"  # Circuit is open, calls blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class InstanceHealth:
    """Tracks health metrics for a single Nitter instance."""

    url: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
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

    def get_stats(self) -> Dict[str, any]:
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
        self._lock = asyncio.Lock()

        # Initialize circuit breakers for each instance
        for instance in self.instances:
            self.circuit_breakers[instance] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            self.health[instance] = InstanceHealth(url=instance)

        logger.info(f"🐦 [NITTER-POOL] Initialized with {len(self.instances)} instances")

    async def get_healthy_instance(self) -> Optional[str]:
        """
        Get a healthy Nitter instance using round-robin logic.

        Iterates through instances in round-robin order and returns the first
        healthy instance (circuit is not OPEN). If all instances are unhealthy,
        returns None.

        Returns:
            URL of a healthy instance, or None if all are unhealthy
        """
        async with self._lock:
            # Try each instance in round-robin order
            for _ in range(len(self.instances)):
                instance = self.instances[self._round_robin_index]
                circuit_breaker = self.circuit_breakers[instance]

                # Check if instance is healthy
                if circuit_breaker.can_call():
                    self._round_robin_index = (self._round_robin_index + 1) % len(self.instances)
                    return instance

                # Move to next instance
                self._round_robin_index = (self._round_robin_index + 1) % len(self.instances)

            # No healthy instances available
            logger.warning("⚠️ [NITTER-POOL] No healthy instances available")
            return None

    def record_success(self, instance: str) -> None:
        """
        Record a successful call to an instance.

        Args:
            instance: URL of the instance
        """
        if instance in self.circuit_breakers:
            self.circuit_breakers[instance].record_success()
            self.health[instance].consecutive_failures = 0
            self.health[instance].last_success_time = time.time()
            self.health[instance].successful_calls += 1
            self.health[instance].total_calls += 1
            logger.debug(f"✅ [NITTER-POOL] Success recorded for {instance}")

    def record_failure(self, instance: str) -> None:
        """
        Record a failed call to an instance.

        Args:
            instance: URL of the instance
        """
        if instance in self.circuit_breakers:
            self.circuit_breakers[instance].record_failure()
            self.health[instance].consecutive_failures += 1
            self.health[instance].last_failure_time = time.time()
            self.health[instance].total_calls += 1
            logger.warning(f"❌ [NITTER-POOL] Failure recorded for {instance}")

    def get_instance_health(self, instance: str) -> Optional[InstanceHealth]:
        """
        Get health information for a specific instance.

        Args:
            instance: URL of the instance

        Returns:
            InstanceHealth object, or None if instance not found
        """
        return self.health.get(instance)

    def get_all_health(self) -> Dict[str, InstanceHealth]:
        """
        Get health information for all instances.

        Returns:
            Dictionary mapping instance URLs to InstanceHealth objects
        """
        return self.health.copy()

    def get_healthy_instances(self) -> List[str]:
        """
        Get list of all currently healthy instances.

        Returns:
            List of instance URLs that are not in OPEN state
        """
        healthy = []
        for instance, circuit_breaker in self.circuit_breakers.items():
            if circuit_breaker.can_call():
                healthy.append(instance)
        return healthy

    def reset_instance(self, instance: str) -> bool:
        """
        Reset circuit breaker for a specific instance.

        Args:
            instance: URL of the instance

        Returns:
            True if reset was successful, False if instance not found
        """
        if instance in self.circuit_breakers:
            self.circuit_breakers[instance].reset()
            self.health[instance].consecutive_failures = 0
            self.health[instance].state = CircuitState.CLOSED
            return True
        return False

    def reset_all(self) -> None:
        """Reset all circuit breakers to initial state."""
        for instance in self.instances:
            self.reset_instance(instance)

    def get_pool_stats(self) -> Dict[str, any]:
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
        topics = []

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
    ) -> List[Dict[str, any]]:
        """
        Parse RSS XML response to extract tweets.

        Args:
            content: RSS XML content
            instance: Nitter instance URL (for constructing tweet URLs)
            username: Twitter username

        Returns:
            List of standardized tweet dictionaries
        """
        tweets = []
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
    ) -> List[Dict[str, any]]:
        """
        Parse HTML response to extract tweets (fallback method).

        Args:
            content: HTML content
            instance: Nitter instance URL (for constructing tweet URLs)
            username: Twitter username

        Returns:
            List of standardized tweet dictionaries
        """
        tweets = []
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

                date_text = tweet_date.get("title") or tweet_date.get_text()
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
            # Use synchronous Fetcher with browser impersonation
            fetcher = Fetcher()
            response = fetcher.get(url, timeout=15, impersonate="chrome", stealthy_headers=True)

            # Return response text
            return response.text
        except Exception as e:
            logger.error(f"❌ [NITTER-POOL] Browser fetch failed for {url}: {e}")
            raise

    async def fetch_tweets_async(self, username: str, max_retries: int = 3) -> List[Dict[str, any]]:
        """
        Fetch tweets from a Twitter username using Nitter instances with hybrid scraping.

        Hybrid Scraping Logic (V11.1):
        1. Fast Path: AsyncFetcher (awaitable) - RSS first, then HTML parsing
        2. Slow Path (Fallback): If HTTP fails (403/Captcha), trigger Browser via asyncio.to_thread

        Automatically retries with different instances on connection errors.

        Args:
            username: Twitter username (without @)
            max_retries: Maximum number of instance retries (default: 3)

        Returns:
            List of standardized tweet dictionaries with keys:
            - content: str - Cleaned tweet text
            - published_at: datetime - UTC timestamp
            - url: str - Tweet URL
            - id: str - Tweet ID
        """
        # Strip @ prefix if present
        username = username.lstrip("@")

        tweets = []
        retry_count = 0

        # Initialize Scrapling fetcher with stealth capabilities (V11.0 optimization: create once outside retry loop)
        # Note: Scrapling handles User-Agent rotation automatically via stealthy_headers
        # V11.0.1: Using AsyncFetcher directly with parameters in get() calls
        fetcher = AsyncFetcher()

        while retry_count < max_retries:
            instance = await self.get_healthy_instance()
            if not instance:
                logger.error(f"❌ [NITTER-POOL] No healthy instances available for @{username}")
                break

            logger.debug(
                f"🔄 [NITTER-POOL] Attempting to fetch tweets for @{username} from {instance} "
                f"(attempt {retry_count + 1}/{max_retries})"
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
                            logger.debug(f"⚠️ [NITTER-POOL] RSS response was empty for @{username}")
                    elif response.status == 404:
                        # User not found - don't record failure
                        logger.warning(
                            f"⚠️ [NITTER-POOL] User @{username} not found (404) on {instance}"
                        )
                        return []
                    elif response.status in (403, 429):
                        # Forbidden or Too Many Requests - trigger browser fallback
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
                    logger.debug(f"⚠️ [NITTER-POOL] RSS request failed for @{username}: {e}")

                # Attempt 2: Fallback to HTML parsing (Fast Path)
                html_url = f"{instance}/{username}"
                try:
                    response = await fetcher.get(
                        html_url, timeout=10, impersonate="chrome", stealthy_headers=True
                    )
                    if response.status == 200:
                        # Note: Scrapling's Response.body contains the raw bytes content
                        # response.text may be empty, so we use body and decode it
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
                            logger.debug(f"⚠️ [NITTER-POOL] HTML response was empty for @{username}")
                    elif response.status == 404:
                        # User not found - don't record failure
                        logger.warning(
                            f"⚠️ [NITTER-POOL] User @{username} not found (404) on {instance}"
                        )
                        return []
                    elif response.status in (403, 429):
                        # Forbidden or Too Many Requests - trigger browser fallback
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
                    logger.debug(f"⚠️ [NITTER-POOL] HTML request failed for @{username}: {e}")

                # Both attempts failed - record failure and retry with next instance
                self.record_failure(instance)
                retry_count += 1

            except Exception as e:
                # Unexpected error - record failure and retry
                logger.error(
                    f"❌ [NITTER-POOL] Unexpected error fetching tweets for @{username}: {e}"
                )
                self.record_failure(instance)
                retry_count += 1

        # All retries exhausted
        logger.error(
            f"❌ [NITTER-POOL] Failed to fetch tweets for @{username} after {max_retries} attempts"
        )
        return tweets


# Singleton instance for global access
_nitter_pool: Optional[NitterPool] = None


def get_nitter_pool() -> NitterPool:
    """
    Get the global NitterPool singleton instance.

    Returns:
        The global NitterPool instance
    """
    global _nitter_pool
    if _nitter_pool is None:
        _nitter_pool = NitterPool()
    return _nitter_pool


def reset_nitter_pool() -> None:
    """Reset the global NitterPool singleton instance."""
    global _nitter_pool
    _nitter_pool = None
