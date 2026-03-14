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

# V10.0: Import Multi-Level Intelligence Gate
try:
    from src.utils.intelligence_gate import (
        apply_intelligence_gate,
        level_1_keyword_check,
        level_1_keyword_check_with_details,
        level_2_translate_and_classify,
    )

    _INTELLIGENCE_GATE_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_GATE_AVAILABLE = False

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

# Nitter instances (round-robin)
NITTER_INSTANCES = [
    "https://twiiit.com",  # Redirects to active Nitter instance
    "https://xcancel.com",  # Alternative Nitter frontend
]

# Fallback instances if primary ones fail
NITTER_FALLBACK_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

# Scraping configuration
SCRAPE_DELAY_MIN = 1.5  # Minimum delay between requests (seconds)
SCRAPE_DELAY_MAX = 3.0  # Maximum delay between requests (seconds)
PAGE_TIMEOUT_SECONDS = 30
MAX_TWEETS_PER_ACCOUNT = 5
# V12.5 COVE FIX: Make MAX_RETRIES_PER_ACCOUNT configurable via NITTER_MAX_RETRIES env var
# Default increased from 2 to 3 for better VPS network conditions
MAX_RETRIES_PER_ACCOUNT = int(os.getenv("NITTER_MAX_RETRIES", "3"))
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

# Native language keywords for pre-AI filtering
# These are betting-relevant terms in non-English/Italian languages
# VPS FIX: Updated to match intelligence_gate.py keywords for consistency
# Now covers 9 languages instead of 3 (spanish, arabic, french, german, portuguese, polish, turkish, russian, dutch)
NATIVE_KEYWORDS = {
    "spanish": [
        "lesión",  # injury
        "huelga",  # strike
        "lesionado",  # injured
        "dolor",  # pain
        "problema físico",  # physical problem
        "baja",  # absence/miss
        "reserva",  # reserve/bench
        "descartado",  # ruled out
        "duda",  # doubtful
        "convocatoria",  # call-up/squad announcement
        "equipo",  # team
        "jugador",  # player
        "entrenador",  # coach
        "club",  # club
        "alineación",  # lineup
        "once titular",  # starting eleven
        "banquillo",  # bench
    ],
    "arabic": [
        "إصابة",  # injury
        "أزمة",  # crisis
        "إصابة طبية",  # medical injury
        "مشكلة صحية",  # health problem
        "غياب",  # absence
        "مصاب",  # injured
        "الاحتياط",  # reserve/bench
        "تشكيلة",  # lineup/formation
        "فريق",  # team
        "لاعب",  # player
        "مدرب",  # coach
        "نادي",  # club
        "الفريق الأساسي",  # starting team
        "القائمة",  # squad list
    ],
    "french": [
        "blessure",  # injury
        "grève",  # strike
        "douleur",  # pain
        "problème physique",  # physical problem
        "absence",  # absence
        "blessé",  # injured
        "forfait",  # ruled out
        "réserve",  # reserve/bench
        "composition",  # lineup/formation
        "équipe",  # team
        "joueur",  # player
        "entraîneur",  # coach
        "club",  # club
        "titulaire",  # starter
        "remplaçant",  # substitute
        "effectif",  # squad
    ],
    "german": [
        "verletzung",  # injury
        "streik",  # strike
        "schmerz",  # pain
        "körperliches problem",  # physical problem
        "abwesenheit",  # absence
        "verletzt",  # injured
        "reservist",  # reserve/bench
        "aufstellung",  # lineup/formation
        "mannschaft",  # team
        "spieler",  # player
        "trainer",  # coach
        "verein",  # club
        "stammspieler",  # starter
        "ersatzspieler",  # substitute
        "kader",  # squad
    ],
    "portuguese": [
        "lesão",  # injury
        "greve",  # strike
        "dor",  # pain
        "problema físico",  # physical problem
        "ausência",  # absence
        "lesionado",  # injured
        "reserva",  # reserve/bench
        "escalação",  # lineup/formation
        "equipe",  # team
        "jogador",  # player
        "treinador",  # coach
        "clube",  # club
        "titular",  # starter
        "reserva",  # substitute
        "elenco",  # squad
    ],
    "polish": [
        "kontuzja",  # injury
        "strajk",  # strike
        "ból",  # pain
        "problem fizyczny",  # physical problem
        "nieobecność",  # absence
        "kontuzjowany",  # injured
        "rezerwowy",  # reserve/bench
        "skład",  # lineup/formation
        "drużyna",  # team
        "zawodnik",  # player
        "trener",  # coach
        "klub",  # club
        "wyjściowy",  # starter
        "rezerwowy",  # substitute
        "kadr",  # squad
    ],
    "turkish": [
        "sakatlık",  # injury
        "grev",  # strike
        "ağrı",  # pain
        "fiziksel sorun",  # physical problem
        "yokluk",  # absence
        "sakat",  # injured
        "yedek",  # reserve/bench
        "kadro",  # lineup/formation
        "takım",  # team
        "oyuncu",  # player
        "antrenör",  # coach
        "kulüp",  # club
        "ilk on bir",  # starting eleven
        "yedek",  # substitute
        "squad",  # squad
    ],
    "russian": [
        "травма",  # injury
        "забастовка",  # strike
        "боль",  # pain
        "физическая проблема",  # physical problem
        "отсутствие",  # absence
        "травмирован",  # injured
        "запасной",  # reserve/bench
        "состав",  # lineup/formation
        "команда",  # team
        "игрок",  # player
        "тренер",  # coach
        "клуб",  # club
        "основной",  # starter
        "запасной",  # substitute
        "состав",  # squad
    ],
    "dutch": [
        "blessure",  # injury
        "staking",  # strike
        "pijn",  # pain
        "fysiek probleem",  # physical problem
        "afwezigheid",  # absence
        "geblesseerd",  # injured
        "reservespeler",  # reserve/bench
        "opstelling",  # lineup/formation
        "team",  # team
        "speler",  # player
        "trainer",  # coach
        "club",  # club
        "basis",  # starter
        "wisselspeler",  # substitute
        "selectie",  # squad
    ],
}

# Flatten all keywords for efficient matching
ALL_NATIVE_KEYWORDS = []
for lang, keywords in NATIVE_KEYWORDS.items():
    ALL_NATIVE_KEYWORDS.extend(keywords)


# ============================================
# DATA CLASSES
# ============================================


@dataclass
class ScrapedTweet:
    """Tweet extracted from Nitter."""

    handle: str
    date: str
    content: str
    topics: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    # V9.5: Layer 2 analysis results
    translation: str | None = None  # Italian translation from DeepSeek-V3
    is_betting_relevant: bool | None = None  # Betting relevance from DeepSeek-V3
    gate_triggered_keyword: str | None = None  # Keyword that triggered Layer 1 gate


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

    # Check each keyword
    for keyword in ALL_NATIVE_KEYWORDS:
        if keyword in text_lower:
            logger.debug(f"🚪 [NATIVE-GATE] PASSED - Keyword found: '{keyword}'")
            return True, keyword

    logger.debug("🚪 [NATIVE-GATE] DISCARDED - No native keywords found")
    return False, None


# ============================================
# V9.5: DEEPSEEK-V3 FLASH ANALYSIS (Layer 2)
# ============================================


def build_flash_analysis_prompt(tweet_text: str) -> str:
    """
    Build prompt for DeepSeek-V3 flash analysis.

    This prompt asks for:
    - One-sentence translation to Italian
    - Boolean classification: is_betting_relevant
    - Specific instruction: "Rilevante solo se parla di infortuni o cambi formazione"

    Args:
        tweet_text: The tweet content to analyze

    Returns:
        Formatted prompt for DeepSeek-V3
    """
    prompt = f"""Analyze this tweet and provide a JSON response with the following structure:
{{
  "translation": "one-sentence Italian translation",
  "is_betting_relevant": true/false
}}

Tweet to analyze:
"{tweet_text}"

IMPORTANT:
- Translate to Italian in one sentence
- Set is_betting_relevant to true ONLY if the tweet discusses injuries (infortuni) or lineup changes (cambi formazione)
- If the tweet is about salaries, transfers, or other non-betting topics, set is_betting_relevant to false
- Return ONLY valid JSON, no other text

Respond with JSON only."""
    return prompt


def parse_flash_analysis_response(response: str) -> dict | None:
    """
    Parse DeepSeek-V3 flash analysis response.

    Args:
        response: Raw response text from DeepSeek

    Returns:
        Dict with 'translation' and 'is_betting_relevant' keys, or None on failure
    """
    if not response:
        return None

    try:
        # Try to parse as JSON
        import json

        data = json.loads(response)

        # Extract required fields
        translation = data.get("translation", "")
        is_betting_relevant = data.get("is_betting_relevant", False)

        # Validate types
        if not isinstance(translation, str):
            logger.warning(f"⚠️ [FLASH-ANALYSIS] Invalid translation type: {type(translation)}")
            translation = ""

        # Handle boolean conversion (may come as string)
        if isinstance(is_betting_relevant, str):
            is_betting_relevant = is_betting_relevant.lower() in ("true", "yes", "si", "1")
        elif not isinstance(is_betting_relevant, bool):
            is_betting_relevant = bool(is_betting_relevant)

        return {"translation": translation, "is_betting_relevant": is_betting_relevant}

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ [FLASH-ANALYSIS] Failed to parse JSON: {e}")
        # Try to extract JSON from response
        try:
            import re

            json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
            if json_match:
                return parse_flash_analysis_response(json_match.group())
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error(f"❌ [FLASH-ANALYSIS] Error parsing response: {e}")
        return None


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
        """Save cache to file."""
        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
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
        """Cache tweets for a handle."""
        with self._cache_lock:  # VPS FIX: Thread-safe write
            handle_key = handle.lower().replace("@", "")
            self._cache[handle_key] = {
                "tweets": tweets,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_cache()  # This is already inside the lock

    def clear_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        with self._cache_lock:  # VPS FIX: Thread-safe modification
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._cache.items() if not self._is_valid_entry(v, now)]
            for k in expired:
                del self._cache[k]
            if expired:
                self._save_cache()  # This is already inside the lock
            return len(expired)


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
        self._instances = list(NITTER_INSTANCES)
        self._fallback_instances = list(NITTER_FALLBACK_INSTANCES)
        self._instance_index = 0
        self._instance_health: dict[str, InstanceHealth] = {}

        # Thread safety: Add lock for protecting InstanceHealth modifications
        self._health_lock = threading.Lock()

        # Initialize health tracking
        for url in self._instances + self._fallback_instances:
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
    # V9.5: DEEPSEEK-V3 FLASH ANALYSIS (Layer 2)
    # ============================================

    async def _call_deepseek_flash_analysis(self, tweet_text: str) -> dict | None:
        """
        Call DeepSeek-V3 for flash analysis (Layer 2).

        This method uses DeepSeek-V3 (NOT R1) for translation and classification
        of tweets that passed the native keyword gate.

        Args:
            tweet_text: The tweet content to analyze

        Returns:
            Dict with 'translation' and 'is_betting_relevant' keys, or None on failure
        """
        if not OPENROUTER_API_KEY:
            logger.warning(
                "⚠️ [FLASH-ANALYSIS] OPENROUTER_API_KEY not set, skipping DeepSeek analysis"
            )
            return None

        try:
            # Build prompt
            prompt = build_flash_analysis_prompt(tweet_text)

            # Prepare request
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://earlybird.betting",
                "X-Title": "EarlyBird Betting Intelligence",
            }

            payload = {
                "model": DEEPSEEK_V3_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            }

            # Import http_client for the request
            from src.utils.http_client import get_http_client

            http_client = get_http_client()

            if not http_client:
                logger.error("❌ [FLASH-ANALYSIS] HTTP client not available")
                return None

            # Make request
            logger.info("🤖 [FLASH-ANALYSIS] Analyzing tweet with DeepSeek-V3...")
            response = http_client.post_sync(
                OPENROUTER_API_URL,
                rate_limit_key="openrouter",
                headers=headers,
                json=payload,
                timeout=30,
                max_retries=1,
            )

            # Handle response
            if response.status_code == 429:
                logger.warning("⚠️ [FLASH-ANALYSIS] Rate limit hit (429)")
                return None

            if response.status_code != 200:
                logger.error(f"❌ [FLASH-ANALYSIS] API error: HTTP {response.status_code}")
                return None

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [FLASH-ANALYSIS] Empty response")
                return None

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("⚠️ [FLASH-ANALYSIS] No content in response")
                return None

            # Parse response
            result = parse_flash_analysis_response(content)
            if result:
                logger.info(
                    f"✅ [FLASH-ANALYSIS] Complete - Translation: '{result['translation'][:50]}...', Relevant: {result['is_betting_relevant']}"
                )
            else:
                logger.warning("⚠️ [FLASH-ANALYSIS] Failed to parse response")

            return result

        except Exception as e:
            logger.error(f"❌ [FLASH-ANALYSIS] Error: {e}")
            return None

    async def _process_tweets_layer2(self, tweets: list[ScrapedTweet]) -> list[ScrapedTweet]:
        """
        Process tweets with V10.0 Layer 2: AI Translation and Classification.

        This method applies Layer 2 analysis (translation + classification) to tweets
        that passed Layer 1 (zero-cost keyword gate).

        Uses the centralized intelligence_gate module for consistency with NewsHunter.

        Args:
            tweets: List of tweets that passed Layer 1 gate

        Returns:
            List of tweets with Layer 2 analysis results populated
        """
        processed_tweets = []

        for tweet in tweets:
            try:
                # V10.0 Layer 2: AI Translation and Classification (via intelligence_gate module)
                logger.info(f"🤖 [INTEL-GATE-L2] Processing tweet from {tweet.handle}...")

                if _INTELLIGENCE_GATE_AVAILABLE:
                    # Use centralized intelligence gate module
                    level_2_result = await level_2_translate_and_classify(tweet.content)

                    if level_2_result.get("success"):
                        # Populate Layer 2 results
                        tweet.translation = level_2_result.get("translation", "")
                        tweet.is_betting_relevant = level_2_result.get("is_relevant", False)

                        logger.info(
                            f"✅ [INTEL-GATE-L2] Complete - Translation: '{tweet.translation[:50]}...', "
                            f"Relevant: {tweet.is_betting_relevant}"
                        )
                    else:
                        # AI failed - mark as None (will be handled downstream)
                        logger.warning(
                            f"⚠️ [INTEL-GATE-L2] Failed for tweet from {tweet.handle}: {level_2_result.get('error')}"
                        )
                        tweet.translation = None
                        tweet.is_betting_relevant = None
                else:
                    # Fallback to legacy implementation
                    analysis_result = await self._call_deepseek_flash_analysis(tweet.content)

                    if analysis_result:
                        # Populate Layer 2 results
                        tweet.translation = analysis_result.get("translation", "")
                        tweet.is_betting_relevant = analysis_result.get(
                            "is_betting_relevant", False
                        )

                        logger.info(
                            f"✅ [LAYER-2-FLASH] Complete - Translation: '{tweet.translation[:50]}...', "
                            f"Relevant: {tweet.is_betting_relevant}"
                        )
                    else:
                        # DeepSeek failed - mark as None (will be handled downstream)
                        logger.warning(f"⚠️ [LAYER-2-FLASH] Failed for tweet from {tweet.handle}")
                        tweet.translation = None
                        tweet.is_betting_relevant = None

                processed_tweets.append(tweet)

            except Exception as e:
                logger.error(f"❌ [INTEL-GATE-L2] Error processing tweet: {e}")
                # Include tweet even if Layer 2 failed
                processed_tweets.append(tweet)

        return processed_tweets

    def _get_next_instance(self) -> str:
        """Get next healthy instance (round-robin)."""
        # Try primary instances first
        for _ in range(len(self._instances)):
            url = self._instances[self._instance_index]
            self._instance_index = (self._instance_index + 1) % len(self._instances)

            health = self._instance_health.get(url)
            if health and health.is_healthy:
                return url

        # Try fallback instances
        for url in self._fallback_instances:
            health = self._instance_health.get(url)
            if health and health.is_healthy:
                self._instance_switches += 1
                return url

        # All unhealthy, try first primary anyway
        return self._instances[0]

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
            return {url: False for url in self._instances + self._fallback_instances}

        results = {}

        for url in self._instances + self._fallback_instances:
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

                    # V12.5 COVE FIX: Check for Cloudflare challenges/captchas
                    cloudflare_indicators = [
                        "cloudflare",
                        "captcha",
                        "challenge platform",
                        "attention required",
                        "checking your browser",
                        "ray id",
                        "cf_chl_rc_i",
                    ]

                    has_cloudflare = any(
                        indicator in content_lower for indicator in cloudflare_indicators
                    )

                    if has_cloudflare:
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] Instance {url} is blocked by Cloudflare/captcha"
                        )
                        results[url] = False
                        self._mark_instance_failure(url, "CloudflareBlock")
                        await page.close()
                        continue

                    # V12.5 COVE FIX: Verify it's a valid Nitter page
                    is_nitter_page = "nitter" in content_lower or "timeline" in content_lower

                    if not is_nitter_page:
                        logger.warning(
                            f"⚠️ [NITTER-FALLBACK] Instance {url} does not appear to be a Nitter page"
                        )
                        results[url] = False
                        self._mark_instance_failure(url, "InvalidPage")
                        await page.close()
                        continue

                    # V12.5 COVE FIX: Verify tweet containers are present
                    # Check for common Nitter tweet container classes
                    tweet_container_indicators = ["timeline-item", "tweet", "timeline", "status"]

                    has_tweet_containers = any(
                        indicator in content_lower for indicator in tweet_container_indicators
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

        tweets = []
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
                topics = []
                if analysis.category != "OTHER":
                    topics.append(analysis.category.lower())

                # V10.0: Initialize with None - Layer 2 analysis will be done asynchronously
                tweet = ScrapedTweet(
                    handle=handle,
                    date=date_str or datetime.now().strftime("%Y-%m-%d"),
                    content=content[:500],  # Limit content length
                    topics=topics,
                    relevance_score=analysis.confidence,
                    translation=None,  # Will be set by Layer 2
                    is_betting_relevant=None,  # Will be set by Layer 2
                    gate_triggered_keyword=triggered_keyword,  # Keyword that triggered Layer 1
                )

                tweets.append(tweet)

            except Exception as e:
                logger.debug(f"⚠️ [NITTER-FALLBACK] Error parsing tweet: {e}")
                continue

        return tweets

    async def _scrape_account(self, handle: str) -> list[ScrapedTweet]:
        """
        Scrape tweets from a single account.

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
                    # V9.5: Include Layer 2 results from cache
                    translation=t.get("translation"),
                    is_betting_relevant=t.get("is_betting_relevant"),
                    gate_triggered_keyword=t.get("gate_triggered_keyword"),
                )
                for t in cached
            ]

        # Ensure browser is ready
        if not await self._ensure_browser():
            return []

        tweets = []
        last_error = None

        # Try with retry
        for attempt in range(MAX_RETRIES_PER_ACCOUNT):
            instance_url = self._get_next_instance()
            profile_url = f"{instance_url}/{handle_clean}"

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
                    profile_url, timeout=PAGE_TIMEOUT_SECONDS * 1000, wait_until="domcontentloaded"
                )

                if not response or response.status != 200:
                    status_code = response.status if response else "unknown"
                    await page.close()
                    self._mark_instance_failure(instance_url, f"HTTP{status_code}")
                    continue

                # Wait for content to load (Nitter uses JS)
                await page.wait_for_timeout(2000)

                # Get HTML
                html = await page.content()
                await page.close()

                # Pre-filter check
                if not self._pre_filter_html(html):
                    logger.debug(f"🐦 [NITTER-FALLBACK] No relevant content for @{handle_clean}")
                    self._mark_instance_success(instance_url)
                    # Cache empty result to avoid re-scraping
                    self._cache.set(handle_clean, [])
                    return []

                # Extract tweets (includes V10.0 Layer 1 gate)
                tweets = self._extract_tweets_from_html(html, f"@{handle_clean}")

                if tweets:
                    self._mark_instance_success(instance_url)
                    self._total_scraped += len(tweets)

                    # V10.0 Layer 2: AI Translation and Classification (via intelligence_gate module)
                    # Only process tweets that passed Layer 1 gate
                    if tweets:
                        logger.info(
                            f"🤖 [INTEL-GATE-L2] Processing {len(tweets)} tweets from @{handle_clean}..."
                        )
                        tweets = await self._process_tweets_layer2(tweets)

                    # Cache results
                    self._cache.set(
                        handle_clean,
                        [
                            {
                                "date": t.date,
                                "content": t.content,
                                "topics": t.topics,
                                "relevance_score": t.relevance_score,
                                # V9.5: Include Layer 2 results in cache
                                "translation": t.translation,
                                "is_betting_relevant": t.is_betting_relevant,
                                "gate_triggered_keyword": t.gate_triggered_keyword,
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
                last_error = e
                error_type = type(e).__name__
                error_message = str(e)

                # V12.5 COVE FIX: Distinguish between error types for better diagnostics
                if error_type == "ConnectionRefusedError":
                    # Connection refused - could be VPS firewall, IP blocking, or Nitter instance down
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] Connection REFUSED for @{handle_clean} from {instance_url} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                        f"Possible causes: VPS firewall, IP blocked by Nitter, or instance down"
                    )
                    self._mark_instance_failure(instance_url, error_type)
                elif error_type in ("TimeoutError", "asyncio.TimeoutError"):
                    # Timeout error - network issue or slow response
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] TIMEOUT for @{handle_clean} from {instance_url} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                        f"Network issue or slow response"
                    )
                    self._mark_instance_failure(instance_url, error_type)
                elif (
                    "403" in error_message
                    or "429" in error_message
                    or "blocked" in error_message.lower()
                ):
                    # Rate limiting or blocking
                    logger.warning(
                        f"⚠️ [NITTER-FALLBACK] BLOCKED/RATE LIMITED for @{handle_clean} from {instance_url} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT}) - "
                        f"Instance may be blocking requests"
                    )
                    self._mark_instance_failure(instance_url, "RateLimited")
                else:
                    # Generic error
                    logger.info(
                        f"⚠️ [NITTER-FALLBACK] Attempt {attempt + 1}/{MAX_RETRIES_PER_ACCOUNT} failed for @{handle_clean}: "
                        f"{error_type}: {error_message}"
                    )
                    self._mark_instance_failure(instance_url, error_type)

                # Random delay before retry
                await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

        # V12.5 COVE FIX: Log final failure with detailed error classification
        final_error_type = type(last_error).__name__
        final_error_message = str(last_error)

        if final_error_type == "ConnectionRefusedError":
            logger.error(
                f"❌ [NITTER-FALLBACK] All {MAX_RETRIES_PER_ACCOUNT} attempts failed for @{handle_clean} - "
                f"CONNECTION REFUSED - Check VPS firewall and ensure Nitter instances are accessible"
            )
        elif final_error_type in ("TimeoutError", "asyncio.TimeoutError"):
            logger.error(
                f"❌ [NITTER-FALLBACK] All {MAX_RETRIES_PER_ACCOUNT} attempts failed for @{handle_clean} - "
                f"TIMEOUT - Network connectivity issue or Nitter instances too slow"
            )
        elif (
            "403" in final_error_message
            or "429" in final_error_message
            or "blocked" in final_error_message.lower()
        ):
            logger.error(
                f"❌ [NITTER-FALLBACK] All {MAX_RETRIES_PER_ACCOUNT} attempts failed for @{handle_clean} - "
                f"BLOCKED/RATE LIMITED - Nitter instances are blocking requests"
            )
        else:
            logger.error(
                f"❌ [NITTER-FALLBACK] All {MAX_RETRIES_PER_ACCOUNT} attempts failed for @{handle_clean}: "
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

        accounts_data = []

        for handle in valid_handles:
            # Scrape account
            tweets = await self._scrape_account(handle)

            # Format for output
            handle_clean = handle.replace("@", "").strip()
            posts = [
                {
                    "date": t.date,
                    "content": t.content,
                    "topics": t.topics,
                    # V10.0: Include Layer 2 analysis results in output
                    "translation": t.translation,
                    "is_betting_relevant": t.is_betting_relevant,
                    "gate_triggered_keyword": t.gate_triggered_keyword,
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
            scrape_result = await self.scrape_accounts(handles_list)

            if not scrape_result:
                logger.warning("⚠️ [NITTER-CYCLE] No tweets scraped")
                return result

            result["handles_processed"] = len(handles_list)
            accounts_data = scrape_result.get("accounts", [])

            # Step 3: Filter via TweetRelevanceFilter
            relevant_tweets = []
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
                all_sources = []
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

        # Use fuzzy matching for partial matches (90% threshold)
        for team_name in [home_team, away_team]:
            # Match against tweet content
            content_similarity = SequenceMatcher(None, team_name.lower(), tweet_lower).ratio()
            if content_similarity >= 0.9:
                logger.debug(
                    f"✅ [NITTER-CYCLE] Fuzzy match found: '{team_name}' ~ '{tweet_content[:30]}...' "
                    f"(similarity: {content_similarity:.2f})"
                )
                return True

            # Match against handle description
            desc_similarity = SequenceMatcher(None, team_name.lower(), desc_lower).ratio()
            if desc_similarity >= 0.9:
                logger.debug(
                    f"✅ [NITTER-CYCLE] Fuzzy match found in description: '{team_name}' ~ '{handle_description[:30]}...' "
                    f"(similarity: {desc_similarity:.2f})"
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
    expired_keys = []

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
