"""
EarlyBird Nitter Fallback Scraper - V1.0

Fallback scraper for Twitter Intel when DeepSeek/Gemini fails.
Uses Nitter instances (twiiit.com, xcancel.com) to extract tweets
from configured accounts.

FLOW:
1. DeepSeek extract_twitter_intel() fails
2. NitterFallbackScraper.scrape_accounts() is called
3. For each account:
   a. Select Nitter instance (round-robin)
   b. Navigate with Playwright (anti-bot protection)
   c. Extract tweets from HTML
   d. Apply ExclusionFilter (skip basketball, women's, etc.)
   e. Apply RelevanceAnalyzer (keyword-based scoring)
4. Return filtered tweets in same format as DeepSeek

OPTIMIZATIONS:
- Round-robin between instances (reduce ban risk)
- Pre-filtering HTML (skip irrelevant pages early)
- Persistent cache (avoid re-scraping same content)
- Retry with fallback (if one instance fails, try another)
- Health check (test instances at startup)

Requirements: Playwright, BeautifulSoup4
"""

import asyncio
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

# V12.1: playwright-stealth import with fallback (COVE FIX)
try:
    from playwright_stealth import Stealth

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    Stealth = None

# Import shared content analysis utilities
from src.utils.content_analysis import (
    get_exclusion_filter,
    get_relevance_analyzer,
)

# P2: Import stop check utility
from config.settings import is_stop_requested

# FIX #2: Import transient error configuration
# FIX #6: Import CIRCUIT_BREAKER_CONFIG for threshold configuration
try:
    from src.config.nitter_instances import (
        CIRCUIT_BREAKER_CONFIG,
        TRANSIENT_ERROR_CONFIG,
    )
except ImportError:
    # Fallback if config not available
    TRANSIENT_ERROR_CONFIG = {
        "failure_threshold": 5,
        "recovery_timeout": 300,
        "error_types": ["TimeoutError", "asyncio.TimeoutError"],
    }
    CIRCUIT_BREAKER_CONFIG = {"failure_threshold": 3, "recovery_timeout": 600}

# V10.0: Import Multi-Level Intelligence Gate (Layer 1 only - Layer 2 removed as dead code)
# V12.7 ROOT FIX: Import ALL_KEYWORDS to eliminate duplicate keyword dictionary.
# Previously maintained a separate NATIVE_KEYWORDS dict that went out of sync.
# Now intelligence_gate.py is the single source of truth for all keyword data.
try:
    from src.utils.intelligence_gate import (
        ALL_KEYWORDS as _UNIFIED_GATE_KEYWORDS,
        apply_intelligence_gate,
        level_1_keyword_check,
        level_1_keyword_check_with_details,
    )

    _INTELLIGENCE_GATE_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_GATE_AVAILABLE = False
    _UNIFIED_GATE_KEYWORDS: list[str] = []  # Empty: populated from emergency fallback below

logger = logging.getLogger(__name__)

if not _INTELLIGENCE_GATE_AVAILABLE:
    logger.warning(
        "⚠️ [INTEL-GATE] Intelligence gate module not available, using legacy implementation"
    )

# V12.1: Log stealth availability (COVE FIX)
if not STEALTH_AVAILABLE:
    logger.warning("⚠️ [NITTER] playwright-stealth not installed, running without stealth")

# ============================================
# CONFIGURATION
# ============================================

# Dedicated fallback instances (V14.0 COVE FIX: Completely separated from NitterPool)
# PRIMARY: xcancel.com and twiiit.com are redirector services that work excellently
# with Playwright stealth mode and handle Anubis protection better than raw Nitter.
# These are NOT in NitterPool's instance list (NitterPool uses xcancel.com as a direct
# Nitter instance, not as a redirector like NitterFallbackScraper does).
_FALLBACK_PRIMARY_INSTANCES = [
    "https://twiiit.com",  # Redirector: routes to healthy Nitter backends
    "https://xcancel.com",  # Redirector: routes to healthy Nitter backends
]

# SECONDARY: Standalone Nitter instances (not in NitterPool)
# Note: nitter.poast.org was UNHEALTHY per status.d420.de (2026-04-06 22:24 UTC).
# Kept as secondary fallback in case it recovers. If it remains unhealthy,
# consider removing it from the list.
_FALLBACK_SECONDARY_INSTANCES = [
    "https://nitter.poast.org",  # US, was unhealthy 2026-04-06 22:24 UTC - kept as fallback
]

# V14.0 COVE FIX: TERTIARY ELIMINATED - No genuinely separate instances available.
# NitterFallbackScraper (Playwright + redirectors twiiit.com/xcancel.com) and
# NitterPool (Scrapling + direct instances) use fundamentally different scraping
# approaches, so some instance overlap is acceptable. The Playwright stealth mode
# with redirectors handles anti-bot protection differently than Scrapling.
#
# Previous tertiary instances removed because:
# - nitter.net: Overlaps with NitterPool
# - nitter.poast.org: Duplicate of secondary AND unhealthy
#
# The PRIMARY (twiiit.com, xcancel.com redirectors) and SECONDARY tiers
# provide sufficient coverage. Redirectors route to healthy Nitter backends
# and are the primary strength of NitterFallbackScraper.
_FALLBACK_TERTIARY_INSTANCES: list[str] = []  # Empty - no genuinely separate instances

# Scraping configuration
SCRAPE_DELAY_MIN = 1.5
SCRAPE_DELAY_MAX = 3.0
PAGE_TIMEOUT_SECONDS = 30
MAX_TWEETS_PER_ACCOUNT = 5

# V13.1 COVE FIX: Per-instance retry before switching to next instance
# Previously was 1 (try once, switch). Now 2: retry same instance once before switching.
# This handles transient VPS network issues (brief timeouts, connection resets)
RETRIES_PER_INSTANCE = int(os.getenv("NITTER_RETRIES_PER_INSTANCE", "2"))

# Calculate max retries from the actual dedicated fallback instances
# V14.0: Tertiary tier removed - no genuinely separate instances available.
# PRIMARY (redirectors) + SECONDARY provide sufficient coverage.
_NUM_FALLBACK_INSTANCES = (
    len(_FALLBACK_PRIMARY_INSTANCES) + len(_FALLBACK_SECONDARY_INSTANCES)
    # Tertiary removed: was duplicate of secondary and NitterPool instances
)
MAX_RETRIES_PER_ACCOUNT = int(os.getenv("NITTER_MAX_RETRIES", str(_NUM_FALLBACK_INSTANCES)))
# V12.5.1 COVE FIX: MAX_NITTER_RECOVERY_ACCOUNTS limits accounts to recover via Nitter
# This prevents excessive latency when many accounts lack data after Tavily
MAX_NITTER_RECOVERY_ACCOUNTS = int(os.getenv("MAX_NITTER_RECOVERY_ACCOUNTS", "10"))

# Cache configuration
CACHE_FILE = "data/nitter_cache.json"
CACHE_TTL_HOURS = 6  # Cache tweets for 6 hours

# V9.5: DeepSeek-V3 Flash Analysis configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEEPSEEK_V3_MODEL = "deepseek/deepseek-chat-v3-0324"  # DeepSeek V3.2 via OpenRouter
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Pre-filtering keywords (skip pages without these)
RELEVANCE_KEYWORDS = [
    "injury",
    "injured",
    "out",
    "miss",
    "absent",
    "doubt",
    "lineup",
    "squad",
    "team",
    "starting",
    "bench",
    "transfer",
    "signing",
    "loan",
    "deal",
    "suspended",
    "ban",
    "red card",
    "infortunio",
    "lesión",
    "lesão",
    "kontuzja",
    "sakatlık",
    "convocati",
    "formazione",
    "escalação",
]

# ============================================
# V9.5: NATIVE KEYWORD GATE (Layer 1 - Zero Cost)
# ============================================

# Single Source of Truth: ALL_KEYWORDS imported from intelligence_gate.py
# Contains INJURY_KEYWORDS (10 languages) + TEAM_KEYWORDS (9 languages) = 199 keywords
#
# ROOT FIX (V12.7): Previously this module maintained a separate 157-line NATIVE_KEYWORDS
# dictionary that was a duplicate of intelligence_gate.py keyword data. This caused:
#   1. Type annotation mismatch (ALL_NATIVE_KEYWORDS: list[dict[str, Any]] but contained str)
#   2. Keyword desync between modules (V12.7 Arabic/Spanish/Portuguese crisis keywords missing)
#   3. Maintenance burden (every keyword change required editing 2 files)
# Now intelligence_gate.py is the canonical source, eliminating all three problems.

# Emergency-only fallback: minimal critical keywords if intelligence_gate.py is completely unavailable
# This covers only the most essential betting-relevant terms that exist in ALL_KEYWORDS.
# IMPORTANT: All keywords here MUST be in ALL_KEYWORDS to maintain consistency between
# normal path (uses ALL_KEYWORDS via intelligence_gate) and emergency path (uses this list).
# Keywords NOT in ALL_KEYWORDS: lineup, bench, strike (removed - not in canonical list)
_EMERGENCY_FALLBACK_KEYWORDS: list[str] = [
    # Injury terms (core) - all from ALL_KEYWORDS
    "injury",
    "injured",
    "lesión",
    "blessure",
    "verletzung",
    "lesão",
    "kontuzja",
    "sakatlık",
    "травма",
    # Absence/ruled out - all from ALL_KEYWORDS
    "absent",
    "ruled out",
    "doubt",
    "absence",
    "غياب",
    # Team/squad - subset from ALL_KEYWORDS
    "squad",
    # Arabic critical injury terms - from ALL_KEYWORDS
    "مصاب",
    "إصابة",
    # Crisis/disruption (translated forms in target languages) - from ALL_KEYWORDS
    "huelga",  # Spanish strike
    "grève",  # French strike
]

# Use unified keywords from intelligence_gate if available, otherwise emergency fallback
_GATE_KEYWORDS: list[str] = (
    _UNIFIED_GATE_KEYWORDS if _UNIFIED_GATE_KEYWORDS else _EMERGENCY_FALLBACK_KEYWORDS
)


# ============================================
# DATA CLASSES
# ============================================


@dataclass
class ScrapedTweet:
    """Tweet extracted from Nitter.

    Simplified dataclass containing only essential fields used by downstream components.
    Removed V9.5 Layer 2 fields (translation, is_betting_relevant, gate_triggered_keyword)
    as they were never used by any downstream component (analysis_engine.py, news_hunter.py,
    twitter_intel_cache.py, openrouter_fallback_provider.py, deepseek_intel_provider.py).
    """

    handle: str
    date: str
    content: str
    topics: list[str] = field(default_factory=list)
    relevance_score: float = 0.0


# Import unified InstanceHealth from nitter_pool.py for consistency
from src.services.nitter_pool import InstanceHealth

# ============================================
# V9.5: NATIVE KEYWORD GATE (Layer 1 - Zero Cost)
# ============================================


def passes_native_gate(tweet_text: str) -> tuple[bool, str | None]:
    """
    Check if tweet contains native language keywords (Layer 1 filter).

    This is a zero-cost pre-AI filter that checks tweets against native
    language keywords BEFORE any API calls. Only tweets that pass this gate
    proceed to Layer 2 (DeepSeek analysis).

    V12.7 ROOT FIX: Now uses _GATE_KEYWORDS (imported from intelligence_gate.py)
    instead of a duplicate local dictionary, guaranteeing keyword consistency
    across all modules in the bot.

    Args:
        tweet_text: The tweet content to check

    Returns:
        Tuple of (passes_gate: bool, triggered_keyword: Optional[str])
        - passes_gate: True if at least one keyword found, False otherwise
        - triggered_keyword: The first keyword that triggered the gate, or None

    Note:
        - Handles UTF-8 encoding properly for Arabic characters
        - Case-insensitive matching
        - Fast string matching only (no API calls)
    """
    if not tweet_text:
        return False, None

    # Normalize text for matching (lowercase)
    text_lower = tweet_text.lower()

    # Check each keyword from the unified gate keywords (single source of truth)
    for keyword in _GATE_KEYWORDS:
        if keyword in text_lower:
            logger.debug(f"🚪 [NATIVE-GATE] PASSED - Keyword found: '{keyword}'")
            return True, keyword

    logger.debug("🚪 [NATIVE-GATE] DISCARDED - No native keywords found")
    return False, None


# V14.0 COVE FIX: REMOVED dead code - build_flash_analysis_prompt() and
# parse_flash_analysis_response() were Layer 2 AI analysis functions that were
# never called by any downstream component. This eliminates ~85 lines of dead
# code and reduces maintenance burden. The Layer 2 analysis was replaced by
# direct keyword gating (Layer 1) which is more efficient.
#
# REMOVED FUNCTIONS:
# - build_flash_analysis_prompt(): Built DeepSeek-V3 prompts for tweet translation
# - parse_flash_analysis_response(): Parsed DeepSeek JSON responses
#
# These were removed because:
# 1. No downstream component used the translation or is_betting_relevant fields
# 2. The Layer 1 keyword gate (passes_native_gate) provides zero-cost filtering
# 3. Removing eliminates wasted API calls, reduces latency, simplifies codebase


# ============================================
# PERSISTENT CACHE
# ============================================


class NitterCache:
    """
    Persistent cache for scraped tweets.

    Saves to JSON file to avoid re-scraping same content.
    Implements TTL-based expiration.
    """

    def __init__(self, cache_file: str = CACHE_FILE, ttl_hours: int = CACHE_TTL_HOURS):
        self._cache_file = Path(cache_file)
        self._ttl_hours = ttl_hours
        self._cache: dict[str, dict] = {}
        self._cache_lock = threading.Lock()  # VPS FIX: Thread safety for cache operations
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from file."""
        if not self._cache_file.exists():
            with self._cache_lock:  # VPS FIX: Thread-safe initialization
                self._cache = {}
            return

        try:
            with open(self._cache_file, encoding="utf-8") as f:
                data = json.load(f)
                # Filter expired entries
                now = datetime.now(timezone.utc)
                with self._cache_lock:  # VPS FIX: Thread-safe write
                    self._cache = {k: v for k, v in data.items() if self._is_valid_entry(v, now)}
            logger.debug(f"🐦 [NITTER-CACHE] Loaded {len(self._cache)} entries")
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-CACHE] Failed to load cache: {e}")
            with self._cache_lock:  # VPS FIX: Thread-safe initialization on error
                self._cache = {}

    def _is_valid_entry(self, entry: dict, now: datetime) -> bool:
        """Check if cache entry is still valid."""
        if "cached_at" not in entry:
            return False
        try:
            cached_at = datetime.fromisoformat(entry["cached_at"].replace("Z", "+00:00"))
            return (now - cached_at) < timedelta(hours=self._ttl_hours)
        except Exception:
            return False

    def _save_cache(self) -> None:
        """Save cache to file (called outside lock to avoid blocking)."""
        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-CACHE] Failed to save cache: {e}")

    def _save_cache_unlocked(self, cache_copy: dict[str, dict]) -> None:
        """
        V14.0 COVE FIX: Save cache to file from a copy (called outside lock).

        This method saves a copy of the cache to avoid blocking other threads
        during I/O operations. The copy is made while holding the lock, then
        the lock is released before the I/O-intensive save operation.

        Args:
            cache_copy: A copy of the cache dict to save
        """
        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_copy, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"⚠️ [NITTER-CACHE] Failed to save cache: {e}")

    def get(self, handle: str) -> list[dict] | None:
        """
        Get cached tweets for a handle.

        Returns:
            list[dict] | None: Cached tweets if found and valid, None if not found or expired.
        """
        with self._cache_lock:  # VPS FIX: Thread-safe read
            handle_key = handle.lower().replace("@", "")
            entry = self._cache.get(handle_key)
            if entry and self._is_valid_entry(entry, datetime.now(timezone.utc)):
                return entry.get("tweets", [])
            return None

    def set(self, handle: str, tweets: list[dict]) -> None:
        """Cache tweets for a handle (V14.0: I/O moved outside lock)."""
        # V14.0 COVE FIX: Copy data under lock, then save outside lock
        # This prevents blocking other threads during I/O operations
        cache_entry = {
            "tweets": tweets,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._cache_lock:  # VPS FIX: Thread-safe write
            handle_key = handle.lower().replace("@", "")
            self._cache[handle_key] = cache_entry
            # Copy cache for save while still under lock (atomic snapshot)
            cache_copy = dict(self._cache)
        # Save outside lock - doesn't block other threads
        self._save_cache_unlocked(cache_copy)

    def clear_expired(self) -> int:
        """Remove expired entries. Returns count removed. (V14.0: I/O moved outside lock)."""
        with self._cache_lock:  # VPS FIX: Thread-safe modification
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._cache.items() if not self._is_valid_entry(v, now)]
            for k in expired:
                del self._cache[k]
            expired_count = len(expired)
            if expired_count > 0:
                # Copy cache for save while still under lock (atomic snapshot)
                cache_copy = dict(self._cache)
            else:
                cache_copy = None
        # Save outside lock - doesn't block other threads
        if cache_copy is not None:
            self._save_cache_unlocked(cache_copy)
        return expired_count


# ============================================
# NITTER FALLBACK SCRAPER
# ============================================


class NitterFallbackScraper:
    """
    Fallback scraper for Twitter Intel using Nitter instances.

    Uses Playwright to bypass anti-bot protection on Nitter instances.
    Implements round-robin instance selection and intelligent retry.

    Features:
    - Round-robin between instances (reduce ban risk)
    - Pre-filtering HTML (skip irrelevant pages early)
    - Persistent cache (avoid re-scraping)
    - Health check (test instances at startup)
    - Retry with fallback (if one instance fails, try another)
    """

    def __init__(self):
        """Initialize the scraper."""
        self._instances = list(_FALLBACK_PRIMARY_INSTANCES)
        self._fallback_instances = list(_FALLBACK_SECONDARY_INSTANCES)
        # V13.1 COVE FIX: Tertiary instances from NitterPool config (last resort)
        self._tertiary_instances = list(_FALLBACK_TERTIARY_INSTANCES)
        self._instance_index = 0
        self._instance_health: dict[str, InstanceHealth] = {}

        # Thread safety: Add lock for protecting InstanceHealth modifications
        self._health_lock = threading.Lock()

        # Initialize health tracking for all instance tiers
        for url in self._instances + self._fallback_instances + self._tertiary_instances:
            self._instance_health[url] = InstanceHealth(url=url)

        # Cache
        self._cache = NitterCache()

        # Filters
        self._exclusion_filter = get_exclusion_filter()
        self._relevance_analyzer = get_relevance_analyzer()

        # Playwright resources (lazy init)
        self._playwright = None
        self._browser = None

        # VPS FIX: Lock for thread-safe browser initialization
        self._browser_lock = asyncio.Lock()

        # Stats
        self._total_scraped = 0
        self._cache_hits = 0
        self._instance_switches = 0

        logger.info("🐦 [NITTER-FALLBACK] Initialized")

    async def _ensure_browser(self) -> bool:
        """Ensure Playwright browser is initialized."""
        if self._browser and self._browser.is_connected():
            return True

        async with self._browser_lock:  # VPS FIX: Thread-safe browser initialization
            # Double-check after acquiring lock
            if self._browser and self._browser.is_connected():
                return True

            try:
                from playwright.async_api import async_playwright

                if not self._playwright:
                    self._playwright = await async_playwright().start()

                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-extensions",
                    ],
                )
                logger.info("✅ [NITTER-FALLBACK] Browser initialized")
                return True
            except Exception as e:
                logger.error(f"❌ [NITTER-FALLBACK] Failed to init browser: {e}")
                return False

    async def close(self) -> None:
        """Close browser resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # ============================================
    # V12.1: PLAYWRIGHT STEALTH (COVE FIX)
    # ============================================

    async def _apply_stealth(self, page) -> None:
        """
        V12.1: Apply playwright-stealth to evade bot detection.

        Bypasses ~70-80% of detection on Nitter instances.
        """
        if STEALTH_AVAILABLE and Stealth is not None:
            try:
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                logger.debug("🥷 [NITTER] Stealth mode applied")
            except Exception as e:
                logger.warning(f"[NITTER] Stealth failed: {e}")

    # ============================================
    # REMOVED: V9.5 DEEPSEEK-V3 FLASH ANALYSIS (Layer 2)
    # ============================================
    # Removed _call_deepseek_flash_analysis() and _process_tweets_layer2() methods
    # as they were processing dead code (translation, is_betting_relevant fields)
    # that were never used by any downstream component.
    # This eliminates wasted API calls, reduces latency, and simplifies the codebase.

    # Recovery timeout: how long before an unhealthy instance gets a second chance
    # V13.1 COVE FIX: Reduced from 600s to 300s for faster recovery on VPS
    _RECOVERY_TIMEOUT_SECONDS = 300  # 5 minutes (was 10 minutes)

    def _soft_reset_unhealthy_instances(self) -> int:
        """
        V13.1 COVE FIX: Soft reset transient failure counters on all instances.

        Called when ALL instances are unhealthy, before giving up on an account.
        This prevents cascading failures where one bad account poisons the pool
        for all subsequent accounts.

        Unlike full recovery (which requires waiting 10 minutes), this only resets
        transient failure counters and consecutive_failures, allowing instances to
        be retried for the next account. Permanent failures (403, Cloudflare) are
        NOT reset.

        Returns:
            Number of instances that were soft-reset
        """
        reset_count = 0
        with self._health_lock:
            for url, health in self._instance_health.items():
                if not health.is_healthy:
                    # Only soft-reset if the failure was primarily transient
                    # (more transient than permanent failures)
                    if health.transient_failures > health.permanent_failures:
                        health.is_healthy = True
                        health.consecutive_failures = 0
                        health.transient_failures = 0
                        # Keep permanent_failures and last_failure_time for monitoring
                        reset_count += 1
                        logger.debug(
                            f"🔄 [NITTER-FALLBACK] Soft-reset instance: {url} "
                            f"(permanent_failures={health.permanent_failures} preserved)"
                        )
        if reset_count > 0:
            logger.info(
                f"🔄 [NITTER-FALLBACK] Soft-reset {reset_count} instances "
                f"(transient-only reset, permanent failures preserved)"
            )
        return reset_count

    def _recover_stale_instances(self) -> int:
        """
        Reset instances that have been unhealthy longer than the recovery timeout.

        Unlike NitterPool which uses a proper CircuitBreaker with HALF_OPEN state,
        this method provides a simpler time-based recovery for NitterFallbackScraper.

        Returns:
            Number of instances recovered
        """
        recovered = 0
        now = time.time()
        with self._health_lock:
            for url, health in self._instance_health.items():
                if not health.is_healthy and health.last_failure_time is not None:
                    elapsed = now - health.last_failure_time
                    if elapsed >= self._RECOVERY_TIMEOUT_SECONDS:
                        health.is_healthy = True
                        health.consecutive_failures = 0
                        health.transient_failures = 0
                        health.permanent_failures = 0
                        recovered += 1
                        logger.info(
                            f"🔄 [NITTER-FALLBACK] Instance recovered after {int(elapsed)}s: {url}"
                        )
        return recovered

    def _get_next_instance(self) -> str | None:
        """Get next healthy instance (round-robin) with automatic recovery.

        V13.1 COVE FIX: Now includes tertiary instances from NitterPool config
        as last resort, providing 8+ total instances instead of just 3.
        """
        self._recover_stale_instances()

        # Try primary instances first
        for _ in range(len(self._instances)):
            url = self._instances[self._instance_index]
            self._instance_index = (self._instance_index + 1) % len(self._instances)

            health = self._instance_health.get(url)
            if health and health.is_healthy:
                return url

        # Try fallback (secondary) instances
        for url in self._fallback_instances:
            health = self._instance_health.get(url)
            if health and health.is_healthy:
                self._instance_switches += 1
                return url

        # V13.1 COVE FIX: Try tertiary instances (from NitterPool config)
        # These are the last resort before giving up on an account
        for url in self._tertiary_instances:
            health = self._instance_health.get(url)
            if health and health.is_healthy:
                self._instance_switches += 1
                logger.debug(f"🔄 [NITTER-FALLBACK] Using tertiary instance: {url}")
                return url

        logger.debug("⚠️ [NITTER-FALLBACK] All instances unhealthy, no more retries")
        return None

    def _is_transient_error(self, error_type: str) -> bool:
        """
        Check if an error type is considered transient (network-related).

        FIX #2: VPS Timeout Handling - Distinguish between transient and permanent failures.

        Args:
            error_type: The name of the exception type

        Returns:
            True if the error is transient, False otherwise
        """
        return error_type in TRANSIENT_ERROR_CONFIG.get("error_types", [])

    def _mark_instance_success(self, url: str) -> None:
        """
        Mark instance as successful.

        Thread-safe: Uses threading.Lock to protect InstanceHealth modifications.
        """
        with self._health_lock:
            health = self._instance_health.get(url)
            if health:
                health.is_healthy = True
                health.consecutive_failures = 0
                health.transient_failures = 0
                health.permanent_failures = 0
                # Use unified field name (last_success_time) from nitter_pool.py
                health.last_success_time = time.time()
                health.successful_calls += 1
                health.total_calls += 1

    def _mark_instance_failure(self, url: str, error_type: str = "Unknown") -> None:
        """
        Mark instance as failed.

        Thread-safe: Uses threading.Lock to protect InstanceHealth modifications.

        VPS Timeout Handling: Use different thresholds for transient vs permanent errors.
        Uses float timestamp (Unix time) for consistency with nitter_pool.py.

        Args:
            url: Instance URL
            error_type: Type of error that occurred
        """
        with self._health_lock:
            health = self._instance_health.get(url)
            if health:
                # Use float timestamp (Unix time) for consistency with nitter_pool.py
                health.last_check = time.time()
                health.total_calls += 1

                # Determine if this is a transient or permanent error
                is_transient = self._is_transient_error(error_type)

                if is_transient:
                    health.transient_failures += 1
                    # Use higher threshold for transient errors
                    threshold = TRANSIENT_ERROR_CONFIG.get("failure_threshold", 5)
                    failure_count = health.transient_failures
                    logger.debug(
                        f"⚠️ [NITTER-FALLBACK] Transient error {error_type} for {url} "
                        f"({failure_count}/{threshold})"
                    )
                else:
                    health.permanent_failures += 1
                    # Use CIRCUIT_BREAKER_CONFIG for permanent error threshold
                    threshold = CIRCUIT_BREAKER_CONFIG.get("failure_threshold", 3)
                    failure_count = health.permanent_failures
                    logger.debug(
                        f"⚠️ [NITTER-FALLBACK] Permanent error {error_type} for {url} "
                        f"({failure_count}/{threshold})"
                    )

                # Update consecutive failures for backward compatibility
                health.consecutive_failures = max(
                    health.transient_failures, health.permanent_failures
                )
                # Track last failure time for recovery mechanism
                health.last_failure_time = time.time()

                # Check if instance should be marked unhealthy
                if failure_count >= threshold:
                    health.is_healthy = False
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] Instance marked unhealthy: {url} "
                        f"({error_type} - {failure_count}/{threshold} failures)"
                    )

    async def health_check(self) -> dict[str, bool]:
        """
        Test all instances and return health status.

        V12.5 COVE FIX: Enhanced health check that:
        - Detects Cloudflare challenges/captchas
        - Verifies tweet containers are present
        - Checks for actual Nitter page content
        - Provides detailed diagnostics for failures

        Returns:
            Dict mapping instance URL to health status
        """
        if not await self._ensure_browser():
            return {
                url: False
                for url in self._instances + self._fallback_instances + self._tertiary_instances
            }

        results = {}

        for url in self._instances + self._fallback_instances + self._tertiary_instances:
            try:
                page = await self._browser.new_page()
                # V12.1: Apply stealth mode (COVE FIX)
                await self._apply_stealth(page)
                await page.set_extra_http_headers(
                    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )

                # Try to load homepage
                response = await page.goto(url, timeout=PAGE_TIMEOUT_SECONDS * 1000)

                if response and response.status == 200:
                    # Get page content for analysis
                    content = await page.content()
                    content_lower = content.lower()

                    # V14.0 COVE FIX: Enhanced anti-bot detection - Cloudflare + Anubis
                    # Both Cloudflare and Anubis are commonly used by Nitter instances
                    # to block automated scraping. Anubis uses proof-of-work challenges.
                    anti_bot_indicators = [
                        # Cloudflare
                        "cloudflare",
                        "attention required",
                        "checking your browser",
                        "ray id",
                        "cf_chl_rc_i",
                        # Anubis (proof-of-work anti-bot used by nitter.privacyredirect.com,
                        # nitter.catsarch.com, and others)
                        "anubis",
                        "proof-of-work",
                        "hashcash",
                        "protecting the server against the scourge of ai companies",
                    ]

                    has_anti_bot = any(
                        indicator in content_lower for indicator in anti_bot_indicators
                    )

                    if has_anti_bot:
                        # Distinguish between Cloudflare and Anubis for better logging
                        if "anubis" in content_lower or "proof-of-work" in content_lower:
                            logger.warning(
                                f"⚠️ [NITTER-FALLBACK] Instance {url} is blocked by Anubis anti-bot"
                            )
                            results[url] = False
                            self._mark_instance_failure(url, "AnubisBlock")
                        else:
                            logger.warning(
                                f"⚠️ [NITTER-FALLBACK] Instance {url} is blocked by Cloudflare/captcha"
                            )
                            results[url] = False
                            self._mark_instance_failure(url, "CloudflareBlock")
                        await page.close()
                        continue

                    # V14.0 COVE FIX: Verify it's a valid Nitter page with SPECIFIC indicators
                    # Previously used "timeline" which is too generic (any social media page has timeline).
                    # Now uses Nitter-specific identifiers:
                    # - "nitter": The word "nitter" in page content
                    # - "peleton": Nitter's JavaScript framework name (very specific)
                    # - "profile-grid": Nitter's profile grid CSS class
                    # - "timeline-item": Nitter's tweet container class (actual HTML class name)
                    nitter_specific_indicators = [
                        "nitter",  # Nitter branding
                        "peleton",  # Nitter's JS framework (unique to Nitter)
                        "profile-grid",  # Nitter profile grid class
                        "timeline-item",  # Nitter tweet container class
                    ]

                    is_nitter_page = any(
                        indicator in content_lower for indicator in nitter_specific_indicators
                    )

                    if not is_nitter_page:
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] Instance {url} does not appear to be a Nitter page"
                        )
                        results[url] = False
                        self._mark_instance_failure(url, "InvalidPage")
                        await page.close()
                        continue

                    # V14.0 COVE FIX: Verify tweet containers with PROPER CSS SELECTORS
                    # Previously used raw substring matching which could produce false positives
                    # (e.g., "timeline-item" might appear in unexpected contexts).
                    # Now uses BeautifulSoup's select() to properly find elements with
                    # specific CSS classes - more accurate and robust detection.
                    if BS4_AVAILABLE:
                        try:
                            soup = BeautifulSoup(content, "html.parser")
                            # Use proper CSS selectors to find tweet containers
                            # .timeline-item: The primary tweet container in Nitter HTML
                            # .main-tweet: Alternative container used in some Nitter instances
                            # .tweet-body: Tweet content wrapper
                            tweet_containers = soup.select(
                                ".timeline-item, .main-tweet, .tweet-body"
                            )
                            has_tweet_containers = len(tweet_containers) > 0
                            if has_tweet_containers:
                                logger.debug(
                                    f"✅ [NITTER-FALLBACK] Found {len(tweet_containers)} "
                                    f"tweet containers on {url}"
                                )
                        except Exception as e:
                            logger.debug(
                                f"⚠️ [NITTER-FALLBACK] BS4 parsing failed for {url}: {e}, "
                                f"falling back to substring check"
                            )
                            # Fallback: use substring check if BS4 fails
                            nitter_tweet_container_classes = [
                                "timeline-item",
                                "main-tweet",
                                "tweet-body",
                            ]
                            has_tweet_containers = any(
                                css_class in content_lower
                                for css_class in nitter_tweet_container_classes
                            )
                    else:
                        # Fallback without BS4: substring check
                        nitter_tweet_container_classes = [
                            "timeline-item",
                            "main-tweet",
                            "tweet-body",
                        ]
                        has_tweet_containers = any(
                            css_class in content_lower
                            for css_class in nitter_tweet_container_classes
                        )

                    if not has_tweet_containers:
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] Instance {url} has no tweet containers"
                        )
                        results[url] = False
                        self._mark_instance_failure(url, "NoTweetContainers")
                        await page.close()
                        continue

                    # All checks passed - instance is healthy
                    results[url] = True
                    self._mark_instance_success(url)
                    logger.debug(f"✅ [NITTER-FALLBACK] Instance {url} is healthy")
                else:
                    status_code = response.status if response else "unknown"
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] Instance {url} returned status {status_code}"
                    )
                    results[url] = False
                    self._mark_instance_failure(url, f"HTTP{status_code}")

                await page.close()

            except Exception as e:
                error_type = type(e).__name__
                logger.debug(f"⚠️ [NITTER-FALLBACK] Health check failed for {url}: {e}")
                results[url] = False
                self._mark_instance_failure(url, error_type)

        healthy_count = sum(1 for v in results.values() if v)
        logger.info(
            f"🐦 [NITTER-FALLBACK] Health check: {healthy_count}/{len(results)} instances healthy"
        )

        return results

    def _pre_filter_html(self, html: str) -> bool:
        """
        Quick check if HTML contains relevant keywords.

        Optimization: Skip full parsing if page is clearly irrelevant.

        Args:
            html: Raw HTML content

        Returns:
            True if page might be relevant, False to skip
        """
        if not html:
            return False

        html_lower = html.lower()

        # Check for any relevance keyword
        for keyword in RELEVANCE_KEYWORDS:
            if keyword in html_lower:
                return True

        return False

    def _extract_tweets_from_html(self, html: str, handle: str) -> list[ScrapedTweet]:
        """
        Extract tweets from Nitter HTML with V10.0 three-layer filtering.

        V10.0 Layer 1: Zero-cost keyword check (via intelligence_gate module)
        V10.0 Layer 2: AI translation and classification (via intelligence_gate module)
        V10.0 Layer 3: R1 reasoning (handled separately in Task 2)

        Args:
            html: Page HTML content
            handle: Twitter handle being scraped

        Returns:
            List of extracted tweets with Layer 2 analysis results
        """
        if not BS4_AVAILABLE or not html:
            return []

        tweets: list[ScrapedTweet] = []
        soup = BeautifulSoup(html, "html.parser")

        # Nitter tweet selectors (may vary by instance)
        tweet_containers = soup.select(".timeline-item, .tweet-body, .main-tweet")

        for container in tweet_containers[:MAX_TWEETS_PER_ACCOUNT]:
            try:
                # Extract content
                content_elem = container.select_one(".tweet-content, .tweet-text, .content")
                if not content_elem:
                    continue

                content = content_elem.get_text(strip=True)
                if not content or len(content) < 10:
                    continue

                # Apply exclusion filter
                if self._exclusion_filter.is_excluded(content):
                    continue

                # V10.0 Layer 1: Zero-cost keyword check (via intelligence_gate module)
                if _INTELLIGENCE_GATE_AVAILABLE:
                    passes_gate, triggered_keyword = level_1_keyword_check(content)
                else:
                    # Fallback to legacy implementation
                    passes_gate, triggered_keyword = passes_native_gate(content)

                if not passes_gate:
                    logger.info(
                        f"🚪 [INTEL-GATE-L1] DISCARDED - No native keywords found in tweet from {handle}"
                    )
                    continue  # Skip tweet - gate discarded it

                logger.info(
                    f"🚪 [INTEL-GATE-L1] PASSED - Keyword '{triggered_keyword}' found in tweet from {handle}"
                )

                # Extract date
                date_elem = container.select_one(".tweet-date a, .tweet-published, time")
                date_str = ""
                if date_elem:
                    date_str = date_elem.get("title", "") or date_elem.get_text(strip=True)

                # Analyze relevance (existing logic)
                analysis = self._relevance_analyzer.analyze(content)

                # Determine topics
                topics: list[str] = []
                if analysis.category != "OTHER":
                    topics.append(analysis.category.lower())

                # FIXED: Store full content (not truncated to 500 chars)
                # Previous truncation lost critical information for downstream analysis
                tweet = ScrapedTweet(
                    handle=handle,
                    date=date_str or datetime.now().strftime("%Y-%m-%d"),
                    content=content,  # Store full content
                    topics=topics,
                    relevance_score=analysis.confidence,
                )

                tweets.append(tweet)

            except Exception as e:
                logger.debug(f"⚠️ [NITTER-FALLBACK] Error parsing tweet: {e}")
                continue

        return tweets

    async def _scrape_account(self, handle: str) -> list[ScrapedTweet]:
        """
        Scrape tweets from a single account.

        V13.1 COVE FIX: Now includes per-instance retry (RETRIES_PER_INSTANCE=2)
        and soft reset when all instances are unhealthy.

        Retry strategy:
        1. Outer loop: iterate over different instances (up to MAX_RETRIES_PER_ACCOUNT)
        2. Inner loop: retry same instance up to RETRIES_PER_INSTANCE times
        3. If all instances unhealthy: soft-reset transient failures and retry once more
        4. Only then give up on this account

        Args:
            handle: Twitter handle (with or without @)

        Returns:
            List of scraped tweets
        """
        # Guard against None/invalid handle
        if not handle or not isinstance(handle, str):
            return []

        # Normalize handle
        handle_clean = handle.replace("@", "").strip()
        if not handle_clean:
            return []

        # Check cache first
        cached = self._cache.get(handle_clean)
        if cached:
            self._cache_hits += 1
            logger.debug(f"🐦 [NITTER-FALLBACK] Cache hit for @{handle_clean}")
            return [
                ScrapedTweet(
                    handle=f"@{handle_clean}",
                    date=t.get("date", ""),
                    content=t.get("content", ""),
                    topics=t.get("topics", []),
                    relevance_score=t.get("relevance_score", 0.5),
                )
                for t in cached
            ]

        # Ensure browser is ready
        if not await self._ensure_browser():
            return []

        tweets: list[ScrapedTweet] = []
        last_error = None
        soft_reset_done = False  # V13.1: Track if soft reset was already attempted

        # Outer loop: try different instances
        attempt = 0
        while attempt < MAX_RETRIES_PER_ACCOUNT:
            instance_url = self._get_next_instance()

            # V13.1 COVE FIX: If no healthy instance available, try soft reset first
            if instance_url is None:
                if not soft_reset_done:
                    reset_count = self._soft_reset_unhealthy_instances()
                    soft_reset_done = True
                    if reset_count > 0:
                        # Try again after soft reset
                        instance_url = self._get_next_instance()
                        logger.info(
                            f"🔄 [NITTER-FALLBACK] Soft-reset recovered {reset_count} instances "
                            f"for @{handle_clean}, retrying..."
                        )

                if instance_url is None:
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] No healthy instances available for @{handle_clean}, "
                        f"stopping after {attempt} attempts"
                    )
                    last_error = Exception("No healthy Nitter instances available")
                    break

            profile_url = f"{instance_url}/{handle_clean}"

            # V13.1 COVE FIX: Inner loop - retry same instance before switching
            instance_succeeded = False
            for instance_retry in range(RETRIES_PER_INSTANCE):
                page = None  # Track page for guaranteed cleanup
                try:
                    page = await self._browser.new_page()

                    # V12.1: Apply stealth mode (COVE FIX)
                    await self._apply_stealth(page)

                    # Set stealth headers
                    await page.set_extra_http_headers(
                        {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.5",
                            "Accept-Encoding": "gzip, deflate, br",
                            "DNT": "1",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                        }
                    )

                    # Navigate to profile
                    response = await page.goto(
                        profile_url,
                        timeout=PAGE_TIMEOUT_SECONDS * 1000,
                        wait_until="domcontentloaded",
                    )

                    if not response or response.status != 200:
                        status_code = response.status if response else "unknown"
                        await page.close()
                        last_error = Exception(f"HTTP{status_code}")
                        self._mark_instance_failure(instance_url, f"HTTP{status_code}")
                        # V13.1: Don't retry on HTTP errors - switch instance immediately
                        break

                    # Wait for content to load (Nitter uses JS)
                    await page.wait_for_timeout(2000)

                    # Get HTML
                    html = await page.content()
                    await page.close()

                    # Pre-filter check
                    if not self._pre_filter_html(html):
                        logger.debug(
                            f"🐦 [NITTER-FALLBACK] No relevant content for @{handle_clean}"
                        )
                        self._mark_instance_success(instance_url)
                        # Cache empty result to avoid re-scraping
                        self._cache.set(handle_clean, [])
                        return []

                    # Extract tweets (includes V10.0 Layer 1 gate)
                    tweets = self._extract_tweets_from_html(html, f"@{handle_clean}")

                    if tweets:
                        self._mark_instance_success(instance_url)
                        self._total_scraped += len(tweets)

                        # Cache results (simplified - only essential fields)
                        self._cache.set(
                            handle_clean,
                            [
                                {
                                    "date": t.date,
                                    "content": t.content,
                                    "topics": t.topics,
                                    "relevance_score": t.relevance_score,
                                }
                                for t in tweets
                            ],
                        )

                        logger.debug(
                            f"✅ [NITTER-FALLBACK] Scraped {len(tweets)} tweets from @{handle_clean}"
                        )
                        return tweets
                    else:
                        # No tweets found but page loaded OK
                        self._mark_instance_success(instance_url)
                        self._cache.set(handle_clean, [])
                        return []

                except Exception as e:
                    # FIX: Close leaked page on any exception (TimeoutError, network error, etc.)
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:
                            pass  # Page cleanup must never mask the original error

                    last_error = e
                    error_type = type(e).__name__
                    error_message = str(e)

                    # V13.1 COVE FIX: Enhanced error classification with per-instance retry awareness
                    if error_type == "ConnectionRefusedError":
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] Connection REFUSED for @{handle_clean} from {instance_url} "
                            f"(instance retry {instance_retry + 1}/{RETRIES_PER_INSTANCE}, "
                            f"attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                            f"Possible causes: VPS firewall, IP blocked by Nitter, or instance down"
                        )
                        self._mark_instance_failure(instance_url, error_type)
                        # Connection refused is usually permanent - don't retry same instance
                        break
                    elif error_type in ("TimeoutError", "asyncio.TimeoutError"):
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] TIMEOUT for @{handle_clean} from {instance_url} "
                            f"(instance retry {instance_retry + 1}/{RETRIES_PER_INSTANCE}, "
                            f"attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                            f"Network issue or slow response"
                        )
                        self._mark_instance_failure(instance_url, error_type)
                        # V13.1: Timeout is transient - retry same instance with short delay
                        if instance_retry < RETRIES_PER_INSTANCE - 1:
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            continue
                    elif (
                        "403" in error_message
                        or "429" in error_message
                        or "blocked" in error_message.lower()
                    ):
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] BLOCKED/RATE LIMITED for @{handle_clean} from {instance_url} "
                            f"(instance retry {instance_retry + 1}/{RETRIES_PER_INSTANCE}, "
                            f"attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                            f"Instance may be blocking requests"
                        )
                        self._mark_instance_failure(instance_url, "RateLimited")
                        # Rate limit is permanent - don't retry same instance
                        break
                    else:
                        logger.info(
                            f"⚠️ [NITTER-FALLBACK] Attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT} failed "
                            f"for @{handle_clean}: {error_type}: {error_message}"
                        )
                        self._mark_instance_failure(instance_url, error_type)
                        # V13.1: Generic error - retry same instance with short delay
                        if instance_retry < RETRIES_PER_INSTANCE - 1:
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            continue

            # Move to next instance
            attempt += 1
            # V13.1: Delay between instance switches (not between per-instance retries)
            if attempt < MAX_RETRIES_PER_ACCOUNT:
                await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

        # V12.5 COVE FIX: Log final failure with detailed error classification
        final_error_type = type(last_error).__name__ if last_error else "Unknown"
        final_error_message = str(last_error) if last_error else "No error recorded"

        if final_error_type == "ConnectionRefusedError":
            logger.error(
                f"❌ [NITTER-FALLBACK] All {attempt} attempts failed for @{handle_clean} - "
                f"CONNECTION REFUSED - Check VPS firewall and ensure Nitter instances are accessible"
            )
        elif final_error_type in ("TimeoutError", "asyncio.TimeoutError"):
            logger.error(
                f"❌ [NITTER-FALLBACK] All {attempt} attempts failed for @{handle_clean} - "
                f"TIMEOUT - Network connectivity issue or Nitter instances too slow"
            )
        elif (
            "403" in final_error_message
            or "429" in final_error_message
            or "blocked" in final_error_message.lower()
        ):
            logger.error(
                f"❌ [NITTER-FALLBACK] All {attempt} attempts failed for @{handle_clean} - "
                f"BLOCKED/RATE LIMITED - Nitter instances are blocking requests"
            )
        else:
            logger.error(
                f"❌ [NITTER-FALLBACK] All {attempt} attempts failed for @{handle_clean}: "
                f"{final_error_type}: {final_error_message}"
            )
        return []

    async def scrape_accounts(
        self, handles: list[str], max_posts_per_account: int = MAX_TWEETS_PER_ACCOUNT
    ) -> dict | None:
        """
        Scrape tweets from multiple accounts.

        Main entry point - returns data in same format as DeepSeek.

        Args:
            handles: List of Twitter handles (with @)
            max_posts_per_account: Max tweets per account

        Returns:
            Dict in DeepSeek format: {"accounts": [...], "extraction_time": "..."}
        """
        if not handles:
            return None

        # Filter out None/invalid handles (must be non-empty string after stripping @)
        valid_handles = [
            h for h in handles if h and isinstance(h, str) and h.replace("@", "").strip()
        ]
        if not valid_handles:
            return None

        # V9.0: Log handles being monitored for transparency
        logger.info(
            f"🐦 [NITTER-FALLBACK] Monitoring {len(valid_handles)} Twitter handles: {', '.join(valid_handles[:10])}"
        )
        if len(valid_handles) > 10:
            logger.info(f"🐦 [NITTER-FALLBACK] ... and {len(valid_handles) - 10} more")

        logger.info(f"🐦 [NITTER-FALLBACK] Scraping {len(valid_handles)} accounts...")

        accounts_data: list[dict[str, Any]] = []

        for handle in valid_handles:
            # P2: Check for full stop before each handle
            if is_stop_requested():
                logger.info("🛑 [NITTER-FALLBACK] Stop requested during scraping, aborting")
                break

            # Scrape account
            tweets = await self._scrape_account(handle)

            # Format for output
            handle_clean = handle.replace("@", "").strip()
            posts = [
                {
                    "date": t.date,
                    "content": t.content,
                    "topics": t.topics,
                }
                for t in tweets[:max_posts_per_account]
            ]

            accounts_data.append({"handle": f"@{handle_clean}", "posts": posts})

            # Delay between accounts
            if handle != valid_handles[-1]:  # Not last
                await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

        # Count accounts with data
        accounts_with_posts = sum(1 for a in accounts_data if a.get("posts"))
        total_posts = sum(len(a.get("posts", [])) for a in accounts_data)

        logger.info(
            f"✅ [NITTER-FALLBACK] Scraped {accounts_with_posts}/{len(handles)} accounts, "
            f"{total_posts} tweets (cache hits: {self._cache_hits})"
        )

        return {
            "accounts": accounts_data,
            "extraction_time": datetime.now(timezone.utc).isoformat(),
            "source": "nitter_fallback",
            "stats": {
                "total_scraped": self._total_scraped,
                "cache_hits": self._cache_hits,
                "instance_switches": self._instance_switches,
            },
        }

    def get_stats(self) -> dict[str, Any]:
        """Get scraper statistics."""
        return {
            "total_scraped": self._total_scraped,
            "cache_hits": self._cache_hits,
            "instance_switches": self._instance_switches,
            "instance_health": {
                url: {
                    "healthy": h.is_healthy,
                    "failures": h.consecutive_failures,
                    # FIX #2 & #5: Add detailed failure tracking and monitoring fields
                    "transient_failures": h.transient_failures,
                    "permanent_failures": h.permanent_failures,
                    "total_calls": h.total_calls,
                    "successful_calls": h.successful_calls,
                    "success_rate": (
                        h.successful_calls / h.total_calls if h.total_calls > 0 else 0.0
                    ),
                    # FIX #4: Convert float timestamps to ISO format for display
                    "last_success": (
                        datetime.fromtimestamp(h.last_success_time, timezone.utc).isoformat()
                        if h.last_success_time
                        else None
                    ),
                    "last_check": (
                        datetime.fromtimestamp(h.last_check, timezone.utc).isoformat()
                        if h.last_check
                        else None
                    ),
                }
                for url, h in self._instance_health.items()
            },
        }

    # ============================================
    # V10.5: INTELLIGENCE-DRIVEN MATCH TRIGGERING
    # ============================================

    async def run_cycle(self, continent: str | None = None) -> dict[str, Any]:
        """
        Run a complete Nitter intelligence cycle.

        This method:
        1. Fetches handles from Supabase (social_sources table)
        2. Scrapes tweets via NitterPool
        3. Filters via TweetRelevanceFilter
        4. Links relevant tweets to upcoming matches
        5. Triggers analysis if 90% confident

        Args:
            continent: Optional continent name (LATAM, ASIA, AFRICA) to filter sources

        Returns:
            Dict with cycle results including:
            - handles_processed: Number of handles scraped
            - tweets_found: Total tweets found
            - relevant_tweets: Tweets with relevance > 0.7
            - matches_triggered: Number of matches triggered for analysis
            - errors: List of errors encountered
        """
        result = {
            "handles_processed": 0,
            "tweets_found": 0,
            "relevant_tweets": 0,
            "matches_triggered": 0,
            "errors": [],
        }

        try:
            # V10.5 FIX: Clear expired intel cache at start of each cycle
            clear_nitter_intel_cache()

            # Step 1: Fetch handles from Supabase
            logger.info(f"🐦 [NITTER-CYCLE] Starting cycle for continent: {continent or 'ALL'}")
            handles_data = await self._get_handles_from_supabase(continent)

            if not handles_data:
                # V12.4 FIX: Improved warning message with continent name and reduced severity
                continent_name = continent or "ALL"
                logger.info(
                    f"ℹ️ [NITTER-CYCLE] No active handles found for continent: {continent_name}"
                )
                logger.debug(f"   This is expected if no leagues are active in {continent_name}")
                return result

            # Extract handles with their league_id mapping
            handles_with_league = {}
            for source in handles_data:
                handle = source.get("identifier", "")
                league_id = source.get("league_id", "")
                if handle and league_id:
                    handles_with_league[f"@{handle}"] = {
                        "league_id": league_id,
                        "description": source.get("description", ""),
                    }

            logger.info(f"📋 [NITTER-CYCLE] Found {len(handles_with_league)} handles to scrape")

            # Step 2: Scrape tweets via NitterPool
            handles_list = list(handles_with_league.keys())

            # P2: Check for stop before heavy scraping
            if is_stop_requested():
                logger.info("🛑 [NITTER-CYCLE] Stop requested, aborting cycle")
                return result

            scrape_result = await self.scrape_accounts(handles_list)

            if not scrape_result:
                logger.warning("⚠️ [NITTER-CYCLE] No tweets scraped")
                return result

            result["handles_processed"] = len(handles_list)
            accounts_data = scrape_result.get("accounts", [])

            # Step 3: Filter via TweetRelevanceFilter
            relevant_tweets: list[dict[str, Any]] = []
            for account in accounts_data:
                handle = account.get("handle", "")
                posts = account.get("posts", [])
                result["tweets_found"] += len(posts)

                for post in posts:
                    content = post.get("content", "")
                    if not content:
                        continue

                    # Apply TweetRelevanceFilter
                    filter_result = self._apply_tweet_relevance_filter(content)

                    # Check if relevance > 0.7 (high confidence)
                    if filter_result.get("score", 0.0) > 0.7:
                        relevant_tweets.append(
                            {
                                "handle": handle,
                                "content": content,
                                "score": filter_result.get("score", 0.0),
                                "topics": filter_result.get("topics", []),
                                "league_id": handles_with_league.get(handle, {}).get("league_id"),
                                "description": handles_with_league.get(handle, {}).get(
                                    "description", ""
                                ),
                            }
                        )

            result["relevant_tweets"] = len(relevant_tweets)
            logger.info(f"✅ [NITTER-CYCLE] Found {len(relevant_tweets)} relevant tweets")

            # Step 4: Link relevant tweets to upcoming matches and trigger analysis
            if relevant_tweets:
                await self._link_and_trigger_matches(relevant_tweets, result)

            logger.info(
                f"🎯 [NITTER-CYCLE] Cycle complete: {result['handles_processed']} handles, "
                f"{result['tweets_found']} tweets, {result['relevant_tweets']} relevant, "
                f"{result['matches_triggered']} matches triggered"
            )

        except Exception as e:
            error_msg = f"❌ [NITTER-CYCLE] Error: {e}"
            logger.error(error_msg)
            result["errors"].append(str(e))

        return result

    async def _get_handles_from_supabase(
        self, continent: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch handles from Supabase social_sources table.

        Args:
            continent: Optional continent name to filter sources

        Returns:
            List of social source records with handle and league_id
        """
        try:
            # Import inside method to avoid circular imports
            from src.database.supabase_provider import get_supabase

            supabase = get_supabase()

            if continent:
                # Get leagues for this continent, then get social sources for those leagues
                active_leagues = supabase.get_active_leagues_for_continent(continent)
                all_sources: list[dict[str, Any]] = []
                for league in active_leagues:
                    league_id = league.get("id")
                    if league_id:
                        league_sources = supabase.get_social_sources_for_league(league_id)
                        all_sources.extend(league_sources)
            else:
                # Get all social sources
                all_sources = supabase.get_social_sources()

            # Filter only active sources
            active_sources = [s for s in all_sources if s.get("is_active", False)]

            logger.info(
                f"📦 [NITTER-CYCLE] Loaded {len(active_sources)} active social sources from Supabase"
            )
            return active_sources

        except Exception as e:
            logger.error(f"❌ [NITTER-CYCLE] Failed to fetch handles from Supabase: {e}")
            return []

    def _apply_tweet_relevance_filter(self, text: str) -> dict[str, Any]:
        """
        Apply TweetRelevanceFilter to tweet content.

        Args:
            text: Tweet content to analyze

        Returns:
            Dict with relevance score and topics
        """
        try:
            # Import inside method to avoid circular imports
            from src.services.tweet_relevance_filter import get_tweet_relevance_filter

            filter_instance = get_tweet_relevance_filter()
            return filter_instance.analyze(text)

        except Exception as e:
            logger.warning(f"[NITTER-CYCLE] TweetRelevanceFilter failed: {e}")
            return {"is_relevant": False, "score": 0.0, "topics": []}

    async def _link_and_trigger_matches(
        self, relevant_tweets: list[dict[str, Any]], result: dict[str, Any]
    ) -> None:
        """
        Link relevant tweets to upcoming matches and trigger analysis if 90% confident.

        For each relevant tweet:
        1. Look up the league_id associated with the handle
        2. Query DB for upcoming matches in that league (Next 72h)
        3. If team name fuzzy matches Home or Away team -> TRIGGER

        Args:
            relevant_tweets: List of relevant tweets with league_id
            result: Result dict to update with matches_triggered count
        """
        try:
            # Import inside method to avoid circular imports
            from src.database.db_manager import get_db_session
            from src.database.models import Match

            now_utc = datetime.now(timezone.utc)
            next_72h = now_utc + timedelta(hours=72)

            for tweet in relevant_tweets:
                handle = tweet.get("handle", "")
                content = tweet.get("content", "")
                league_id = tweet.get("league_id")
                description = tweet.get("description", "")

                if not league_id:
                    continue

                # Query DB for upcoming matches in this league
                try:
                    with get_db_session() as db_session:
                        upcoming_matches = (
                            db_session.query(Match)
                            .filter(
                                Match.league == league_id,
                                Match.start_time >= now_utc,
                                Match.start_time <= next_72h,
                            )
                            .order_by(Match.start_time)
                            .all()
                        )

                        if not upcoming_matches:
                            logger.debug(
                                f"🔍 [NITTER-CYCLE] No upcoming matches for league {league_id}"
                            )
                            continue

                        # Check for fuzzy match with team names
                        for match in upcoming_matches:
                            # VPS FIX: Extract Match attributes safely to prevent session detachment
                            # This prevents "Trust validation error" when Match object becomes detached
                            # from session due to connection pool recycling under high load
                            home_team = getattr(match, "home_team", None)
                            away_team = getattr(match, "away_team", None)

                            if not home_team or not away_team:
                                continue

                            if await self._check_team_match(
                                content, description, home_team, away_team
                            ):
                                # 90% confident - trigger analysis
                                await self._trigger_analysis(match, handle, content)
                                result["matches_triggered"] += 1
                                break  # Only trigger once per tweet

                except Exception as e:
                    logger.warning(f"⚠️ [NITTER-CYCLE] Error querying matches: {e}")
                    continue

        except Exception as e:
            logger.error(f"❌ [NITTER-CYCLE] Error linking tweets to matches: {e}")

    async def _check_team_match(
        self, tweet_content: str, handle_description: str, home_team: str, away_team: str
    ) -> bool:
        """
        Check if tweet content or handle description fuzzy matches team names.

        Uses SequenceMatcher for fuzzy string matching with 90% threshold.

        Args:
            tweet_content: Tweet text content
            handle_description: Handle description from Supabase
            home_team: Home team name
            away_team: Away team name

        Returns:
            True if 90% confident tweet belongs to this match
        """
        if not home_team or not away_team:
            return False

        # Normalize text for matching
        tweet_lower = tweet_content.lower()
        desc_lower = handle_description.lower()
        home_lower = home_team.lower()
        away_lower = away_team.lower()

        # Check for exact match first (highest confidence)
        if home_lower in tweet_lower or away_lower in tweet_lower:
            logger.debug(
                f"✅ [NITTER-CYCLE] Exact team match found: '{home_team}' or '{away_team}' in tweet"
            )
            return True

        # Check for team names in handle description
        if home_lower in desc_lower or away_lower in desc_lower:
            logger.debug(
                f"✅ [NITTER-CYCLE] Team match found in description: '{home_team}' or '{away_team}'"
            )
            return True

        # V14.0 COVE FIX: Word-level fuzzy matching instead of full-string comparison.
        # Previously used SequenceMatcher on full tweet text (~280 chars) vs team name
        # (~15 chars), which always produced low similarity ratios since the strings
        # differ vastly in length. Now uses word-level matching:
        # 1. Split team name into words (tokens)
        # 2. Check if each team word appears as substring in tweet
        # 3. For multi-word teams, also try token-pair fuzzy matching
        #
        # This correctly handles cases like "Man United" matching "manchester united"
        # in the tweet text, where the full-string approach would fail.
        import re

        for team_name in [home_team, away_team]:
            team_words = team_name.lower().split()
            matched_words = 0

            for word in team_words:
                # Skip very short words (<3 chars) that cause false positives
                if len(word) < 3:
                    continue
                # Check if this team word appears in tweet
                if word in tweet_lower:
                    matched_words += 1

            # Require at least half the team name words to match (fuzzy match)
            if len(team_words) >= 2 and matched_words >= len(team_words) / 2:
                logger.debug(
                    f"✅ [NITTER-CYCLE] Fuzzy team match: '{team_name}' "
                    f"({matched_words}/{len(team_words)} words matched in tweet)"
                )
                return True

            # For single-word team names, use substring match on a normalized version
            # (removes common suffixes like "fc", "sc", "cf", "ul", etc.)
            if len(team_words) == 1:
                word = team_words[0]
                # Strip common suffixes that might cause mismatch
                normalized_word = re.sub(r"(fc|sc|cf|ul|afc|rc|ac|as|ss|gs|ks|fs)$", "", word)
                if len(normalized_word) >= 4 and normalized_word in tweet_lower:
                    logger.debug(
                        f"✅ [NITTER-CYCLE] Fuzzy single-word match: '{team_name}' "
                        f"(normalized: '{normalized_word}')"
                    )
                    return True

        return False

    async def _trigger_analysis(self, match: Any, handle: str, tweet_text: str) -> None:
        """
        Trigger analysis for a match with insider tweet intel.

        V10.5 FIX: Now stores intel in shared cache for main.py to use.

        Args:
            match: Match database object
            handle: Twitter handle that provided the intel
            tweet_text: Tweet content
        """
        try:
            # VPS FIX: Extract Match attributes safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", None)
            away_team = getattr(match, "away_team", None)
            match_id = getattr(match, "id", None)

            if not home_team or not away_team or not match_id:
                logger.warning("⚠️ [NITTER-CYCLE] Invalid match object")
                return

            # Build forced narrative with insider tweet context
            forced_narrative = f"INSIDER TWEET ({handle}): {tweet_text}"

            logger.info(
                f"🚨 [NITTER-CYCLE] TRIGGER: Found intel for {home_team} vs {away_team} "
                f"via {handle}"
            )

            # V10.5 FIX: Store intel in shared cache for main.py to access
            with _nitter_intel_cache_lock:  # VPS FIX: Thread-safe write
                _nitter_intel_cache[match_id] = {
                    "handle": handle,
                    "intel": forced_narrative,
                    "timestamp": datetime.now(timezone.utc),
                }

            logger.info(
                f"✅ [NITTER-CYCLE] Intel cached for match {match_id}: {forced_narrative[:100]}..."
            )

        except Exception as e:
            logger.error(f"❌ [NITTER-CYCLE] Error triggering analysis: {e}")


# ============================================
# V10.5: NITTER INTEL CACHE (Shared with main.py)
# ============================================

# Cache for storing Nitter intel that main.py can access
# Format: {match_id: {"handle": str, "intel": str, "timestamp": datetime}}
_nitter_intel_cache: dict[str, dict[str, Any]] = {}
_nitter_intel_cache_lock = threading.Lock()  # VPS FIX: Thread safety for concurrent access


def get_nitter_intel_for_match(match_id: str) -> dict[str, Any] | None:
    """
    Get cached Nitter intel for a specific match.

    This allows main.py to access insider intel gathered by Nitter cycle.

    Args:
        match_id: Match ID from database

    Returns:
        Dict with 'handle', 'intel', 'timestamp' keys, or None if no intel exists
    """
    with _nitter_intel_cache_lock:  # VPS FIX: Thread-safe read
        return _nitter_intel_cache.get(match_id)


def clear_nitter_intel_cache() -> None:
    """
    Clear expired Nitter intel cache entries.

    Removes entries older than 24 hours to prevent stale intel.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    expired_keys: list[str] = []

    with _nitter_intel_cache_lock:  # VPS FIX: Thread-safe modification
        for match_id, intel_data in _nitter_intel_cache.items():
            intel_time = intel_data.get("timestamp")
            if intel_time and (now - intel_time).total_seconds() > 86400:  # 24 hours
                expired_keys.append(match_id)

        for key in expired_keys:
            del _nitter_intel_cache[key]

    if expired_keys:
        logger.debug(f"🗑️ [NITTER-CACHE] Cleared {len(expired_keys)} expired entries")


# ============================================
# SINGLETON INSTANCE
# ============================================

_nitter_scraper_instance: NitterFallbackScraper | None = None
_nitter_scraper_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_nitter_fallback_scraper() -> NitterFallbackScraper:
    """
    Get or create singleton NitterFallbackScraper instance.

    V12.2: Fixed lazy initialization race condition.
    Multiple threads can safely call this function concurrently.
    """
    global _nitter_scraper_instance
    if _nitter_scraper_instance is None:
        with _nitter_scraper_instance_init_lock:
            # Double-checked locking pattern for thread safety
            if _nitter_scraper_instance is None:
                _nitter_scraper_instance = NitterFallbackScraper()
    return _nitter_scraper_instance


async def scrape_twitter_intel_fallback(
    handles: list[str], max_posts_per_account: int = MAX_TWEETS_PER_ACCOUNT
) -> dict | None:
    """
    Convenience function to scrape Twitter intel via Nitter fallback.

    Args:
        handles: List of Twitter handles
        max_posts_per_account: Max tweets per account

    Returns:
        Dict in DeepSeek format or None on failure
    """
    scraper = get_nitter_fallback_scraper()
    return await scraper.scrape_accounts(handles, max_posts_per_account)


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":

    async def test_scraper():
        print("=" * 60)
        print("🐦 NITTER FALLBACK SCRAPER - TEST")
        print("=" * 60)

        scraper = get_nitter_fallback_scraper()

        # Health check
        print("\n🏥 Health Check:")
        health = await scraper.health_check()
        for url, is_healthy in health.items():
            status = "✅" if is_healthy else "❌"
            print(f"   {status} {url}")

        # Test scraping
        test_handles = ["@RudyGaletti", "@AnthonyRJoseph"]
        print(f"\n🔍 Scraping {len(test_handles)} accounts...")

        result = await scraper.scrape_accounts(test_handles)

        if result:
            print("\n📊 Results:")
            print(f"   Accounts: {len(result.get('accounts', []))}")
            for acc in result.get("accounts", []):
                posts = acc.get("posts", [])
                print(f"   {acc['handle']}: {len(posts)} tweets")
                for post in posts[:2]:
                    print(f"      - {post['content'][:60]}...")
        else:
            print("❌ No results")

        # Stats
        print("\n📈 Stats:")
        stats = scraper.get_stats()
        print(f"   Total scraped: {stats['total_scraped']}")
        print(f"   Cache hits: {stats['cache_hits']}")

        # Cleanup
        await scraper.close()
        print("\n✅ Test complete")

    asyncio.run(test_scraper())
