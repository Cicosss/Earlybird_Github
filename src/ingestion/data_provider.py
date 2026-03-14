"""
FotMob Data Provider
Clean implementation using standard requests library.
Free, reliable, and up-to-date football data.

Features:
- Fuzzy team name matching for obscure leagues
- Unicode normalization for special characters
- Smart caching with dynamic TTL based on match proximity (V4.3)
- Full team context (injuries, motivation, fatigue)
- Robust error handling with fail-safe fallbacks
- Rate limiting protection
- User-Agent rotation for anti-bot evasion
"""

import json
import logging
import os
import random
import time
import unicodedata
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Protocol

import pytz
import requests
import requests.exceptions
from dateutil import parser

# Try to import thefuzz for better fuzzy matching
try:
    from thefuzz import fuzz as thefuzz_fuzz

    _THEFUZZ_AVAILABLE = True
except ImportError:
    _THEFUZZ_AVAILABLE = False
    thefuzz_fuzz = None

logger = logging.getLogger(__name__)

# V4.3: Smart Cache with dynamic TTL
try:
    from src.utils.smart_cache import (
        get_match_cache,
        get_search_cache,
        get_team_cache,
        log_cache_stats,
    )

    _SMART_CACHE_AVAILABLE = True
except ImportError:
    _SMART_CACHE_AVAILABLE = False
    logger.warning("⚠️ Smart Cache not available - using no cache")

# V5.2: Import team mapping at top-level for performance
try:
    from src.ingestion.fotmob_team_mapping import get_fotmob_team_id

    _TEAM_MAPPING_AVAILABLE = True
except ImportError:
    _TEAM_MAPPING_AVAILABLE = False
    get_fotmob_team_id = None
    logger.warning("⚠️ FotMob team mapping not available - using dynamic search only")

# ============================================
# TYPE DEFINITIONS
# ============================================


class ResponseLike(Protocol):
    """Protocol for response-like objects with status_code and json() method."""

    status_code: int

    def json(self) -> dict:
        """Parse and return JSON data from the response."""
        ...


class _MockResponse:
    """
    Mock response object for Playwright fallback.

    This class provides a duck-typed response object that is compatible
    with requests.Response for the subset of methods used by FotMobProvider.
    """

    def __init__(self, data: dict):
        """Initialize mock response with JSON data."""
        self.status_code = 200
        self._data = data

    def json(self) -> dict:
        """Return the JSON data."""
        return self._data

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"_MockResponse(status_code={self.status_code}, data_keys={list(self._data.keys())})"


# ============================================
# RATE LIMITING & CACHING CONFIGURATION
# ============================================
# FIX: Make temporal constants configurable via environment variables
FOTMOB_MIN_REQUEST_INTERVAL = float(
    os.getenv("FOTMOB_MIN_REQUEST_INTERVAL", "2.0")
)  # V6.2: Increased from 1.0s to 2.0s for better anti-bot evasion
FOTMOB_REQUEST_TIMEOUT = int(os.getenv("FOTMOB_REQUEST_TIMEOUT", "15"))
FOTMOB_MAX_RETRIES = 3

# V6.2: Request jitter configuration to prevent predictable patterns
FOTMOB_JITTER_MIN = -0.5  # Minimum jitter in seconds
FOTMOB_JITTER_MAX = 0.5  # Maximum jitter in seconds

# V6.1: Thread-safe rate limiting for VPS multi-thread scenarios
import threading

# Import safe access utilities for V7.0 defensive programming
from src.utils.validators import safe_get

_fotmob_rate_limit_lock = threading.Lock()
_last_fotmob_request_time = 0.0

# ============================================
# USER-AGENT ROTATION (Anti-Bot Evasion)
# ============================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Get a random User-Agent from the rotation pool."""
    return random.choice(USER_AGENTS)


def normalize_unicode(text: str) -> str:
    """
    Normalize unicode characters to ASCII equivalents.
    Converts: Ħamrun -> Hamrun, Malmö -> Malmo, etc.
    """
    if not text:
        return text

    replacements = {
        "Ħ": "H",
        "ħ": "h",
        "Ł": "L",
        "ł": "l",
        "Đ": "D",
        "đ": "d",
        "Ø": "O",
        "ø": "o",
        "Æ": "AE",
        "æ": "ae",
        "Œ": "OE",
        "œ": "oe",
        "ß": "ss",
        "Þ": "Th",
        "þ": "th",
        "Ð": "D",
        "ð": "d",
    }

    result = text
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)

    normalized = unicodedata.normalize("NFKD", result)
    ascii_text = normalized.encode("ASCII", "ignore").decode("utf-8")
    return ascii_text.strip()


def fuzzy_match_team(search_name: str, candidates: list[str], threshold: float = 0.6) -> str | None:
    """
    Find best fuzzy match for a team name.
    """
    if not candidates:
        return None

    if not search_name:
        return None

    search_lower = search_name.lower().strip()
    search_tokens = set(search_lower.split())
    search_first = search_lower.split()[0] if search_lower else ""

    best_match = None
    best_score = 0

    for candidate in candidates:
        if not candidate:
            continue

        cand_lower = candidate.lower().strip()
        cand_tokens = set(cand_lower.split())

        if search_lower == cand_lower:
            return candidate

        cand_first = cand_lower.split()[0] if cand_lower else ""
        if search_first and cand_first and search_first == cand_first and len(search_first) >= 4:
            return candidate

        overlap = len(search_tokens & cand_tokens)
        if overlap >= 1 and overlap >= len(search_tokens) * 0.5:
            token_score = overlap / max(len(search_tokens), len(cand_tokens))
            if token_score > best_score:
                best_score = token_score
                best_match = candidate

        if _THEFUZZ_AVAILABLE and thefuzz_fuzz is not None:
            try:
                fuzz_score = thefuzz_fuzz.token_set_ratio(search_lower, cand_lower) / 100.0
                if fuzz_score > best_score:
                    best_score = fuzz_score
                    best_match = candidate
            except Exception as e:
                logger.debug(f"thefuzz matching failed, using difflib fallback: {e}")

        seq_score = SequenceMatcher(None, search_lower, cand_lower).ratio()
        if seq_score > best_score:
            best_score = seq_score
            best_match = candidate

    if best_score >= threshold:
        logger.info(f"🔍 Fuzzy match: '{search_name}' → '{best_match}' (score: {best_score:.2f})")
        return best_match

    return None


class FotMobProvider:
    """
    FotMob data provider for live football data.
    Handles team search, match details, and injury extraction.
    """

    BASE_URL = "https://www.fotmob.com/api"

    BASE_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.fotmob.com/",
        "Origin": "https://www.fotmob.com",
    }

    PREFIXES_TO_STRIP = [
        "FC",
        "AS",
        "AC",
        "SC",
        "SV",
        "SK",
        "FK",
        "IF",
        "BK",
        "CF",
        "CD",
        "FSV",
        "TSG",
        "VfB",
        "VfL",
        "SpVgg",
        "SG",
        "TuS",
        "SSV",
        "HNK",
        "HSK",
        "HŠK",
        "NK",
        "GNK",
        "RNK",
        "KAA",
        "KV",
        "KRC",
        "KSC",
        "KVC",
        "KFCO",
        "Real",
        "Sporting",
        "Club",
        "Deportivo",
        "Atlético",
        "Atletico",
        "Athletic",
        "Racing",
        "United",
        "City",
        "Dynamo",
        "Dinamo",
        # Brazilian prefixes
        "Sociedade",
        "Esportiva",
        "Clube",
        "de",
        "do",
        "da",
    ]

    SUFFIXES_TO_STRIP = [
        "FC",
        "SC",
        "SK",
        "FK",
        "IF",
        "BK",
        "CF",
        "AC",
        "AS",
        "SV",
        "United",
        "City",
        "Calcio",
        "Spor",
        "Club",
    ]

    HARDCODED_IDS = {
        "Olympiacos": (8638, "Olympiacos"),
        "Olympiakos": (8638, "Olympiacos"),
        "Olympiacos Piraeus": (8638, "Olympiacos"),
        "Olympiakos Piraeus": (8638, "Olympiacos"),
        "Olympiacos FC": (8638, "Olympiacos"),
    }

    MANUAL_MAPPING = {
        "AS Roma": "Roma",
        "AC Milan": "Milan",
        "AC Monza": "Monza",
        "US Lecce": "Lecce",
        "US Sassuolo": "Sassuolo",
        "Milan": "AC Milan",
        "Inter": "Internazionale",
        "Inter Milan": "Internazionale",
        "Man Utd": "Manchester United",
        "Man City": "Manchester City",
        "Wolves": "Wolverhampton Wanderers",
        "Spurs": "Tottenham Hotspur",
        "Newcastle": "Newcastle United",
        "West Ham": "West Ham United",
        "Brighton": "Brighton and Hove Albion",
        "Nottm Forest": "Nottingham Forest",
        "Nott'm Forest": "Nottingham Forest",
        "Sheffield Utd": "Sheffield United",
        "Leeds": "Leeds United",
        "Bayern": "Bayern Munich",
        "Bayern München": "Bayern Munich",
        "Dortmund": "Borussia Dortmund",
        "Borussia Dortmund": "Dortmund",
        "Gladbach": "Borussia Monchengladbach",
        "Leverkusen": "Bayer Leverkusen",
        "RB Leipzig": "Leipzig",
        "Mainz 05": "Mainz",
        "FC Köln": "Koln",
        "1. FC Köln": "Koln",
        "Atlético Madrid": "Atletico Madrid",
        "Atletico": "Atletico Madrid",
        "Real Sociedad": "Sociedad",
        "Real Betis": "Betis",
        "Athletic Bilbao": "Athletic Club",
        "Celta Vigo": "Celta",
        "Rayo": "Rayo Vallecano",
        "PSG": "Paris Saint-Germain",
        "Paris SG": "Paris Saint-Germain",
        "Monaco": "AS Monaco",
        "Lyon": "Olympique Lyonnais",
        "Marseille": "Olympique Marseille",
        "Saint-Étienne": "Saint-Etienne",
        "Sporting": "Sporting CP",
        "Sporting Lisbon": "Sporting CP",
        "Sporting Clube de Portugal": "Sporting CP",
        "Sporting CP": "Sporting CP",
        "Benfica": "SL Benfica",
        "Porto": "FC Porto",
        "Ajax": "Ajax Amsterdam",
        "PSV": "PSV Eindhoven",
        "Feyenoord": "Feyenoord Rotterdam",
        "FC Basel": "Basel",
        "FC Zurich": "Zurich",
        "FC Zürich": "Zurich",
        "Young Boys": "BSC Young Boys",
        "Galatasaray SK": "Galatasaray",
        "Fenerbahçe": "Fenerbahce",
        "Beşiktaş": "Besiktas",
        "Çaykur Rizespor": "Rizespor",
        "Caykur Rizespor": "Rizespor",
        "Göztepe": "Goztepe",
        "Göztepe SK": "Goztepe",
        # Brazilian team mappings
        "Sociedade Esportiva Palmeiras": "Palmeiras",
        "Clube de Regatas do Flamengo": "Flamengo",
        "Sport Club Corinthians Paulista": "Corinthians",
        "São Paulo Futebol Clube": "São Paulo",
        "Sao Paulo Futebol Clube": "São Paulo",
        "Santos Futebol Clube": "Santos",
        "Botafogo de Futebol e Regatas": "Botafogo",
        "Grêmio Foot-Ball Porto Alegrense": "Grêmio",
        "Gremio Foot-Ball Porto Alegrense": "Grêmio",
        "Sport Club Internacional": "Internacional",
        "Cruzeiro Esporte Clube": "Cruzeiro",
        "Clube Atlético Mineiro": "Atlético Mineiro",
        "Clube Atletico Mineiro": "Atlético Mineiro",
        "Esporte Clube Bahia": "Bahia",
        "Sport Club do Recife": "Sport Recife",
        "Esporte Clube Vitória": "Vitória",
        "Esporte Clube Vitoria": "Vitória",
        "Fluminense Football Club": "Fluminense",
        "Athletico Paranaense": "Athletico Paranaense",
        "Atlético Paranaense": "Athletico Paranaense",
        "Fortaleza Esporte Clube": "Fortaleza",
        "Ceará Sporting Club": "Ceará",
        "Ceara Sporting Club": "Ceará",
        "Coritiba Foot Ball Club": "Coritiba",
        "Goiás Esporte Clube": "Goiás",
        "Goias Esporte Clube": "Goiás",
        "Cuiabá Esporte Clube": "Cuiabá",
        "Cuiaba Esporte Clube": "Cuiabá",
        "Avaí Futebol Clube": "Avaí",
        "Avai Futebol Clube": "Avaí",
        "Red Bull Bragantino": "Bragantino",
        "América Futebol Clube": "América Mineiro",
        "America Futebol Clube": "América Mineiro",
        "Esporte Clube Juventude": "Juventude",
        "Sivasspor": "Sivasspor",
        "Başakşehir": "Istanbul Basaksehir",
        "Istanbul Basaksehir FK": "Istanbul Basaksehir",
        "Gazişehir Gaziantep": "Gaziantep FK",
        "Gazisehir Gaziantep": "Gaziantep FK",
        "Gaziantep": "Gaziantep FK",
        "Olympiacos": "Olympiacos",
        "Olympiakos": "Olympiacos",
        "Olympiacos Piraeus": "Olympiacos",
        "Olympiakos Piraeus": "Olympiacos",
        "Panathinaikos Athens": "Panathinaikos",
        "Panathinaikos FC": "Panathinaikos",
        "PAOK": "PAOK Thessaloniki",
        "PAOK FC": "PAOK Thessaloniki",
        "AEK": "AEK Athens",
        "AEK Athens FC": "AEK Athens",
        "Celtic": "Celtic FC",
        "Rangers": "Rangers FC",
        "Sydney": "Sydney FC",
        "Melbourne": "Melbourne Victory",
        "Western Sydney": "Western Sydney Wanderers",
        "Boca": "Boca Juniors",
        "River": "River Plate",
        "Racing": "Racing Club",
        "America": "Club America",
        "Club América": "Club America",
        "Guadalajara": "CD Guadalajara",
        "Chivas": "CD Guadalajara",
        "FSV Mainz 05": "Mainz 05",
        "FSV Mainz": "Mainz 05",
        "SC Freiburg": "Freiburg",
        "VfB Stuttgart": "Stuttgart",
        "VfL Wolfsburg": "Wolfsburg",
        "VfL Bochum": "Bochum",
        "TSG Hoffenheim": "Hoffenheim",
        "SpVgg Greuther Fürth": "Greuther Furth",
        "SK Brann": "Brann",
        "Rosenborg BK": "Rosenborg",
        "Molde FK": "Molde",
        "Viking FK": "Viking",
        "Bodø/Glimt": "Bodo/Glimt",
        "HNK Rijeka": "Rijeka",
        "HNK Hajduk Split": "Hajduk Split",
        "GNK Dinamo Zagreb": "Dinamo Zagreb",
        "NK Osijek": "Osijek",
        "HŠK Zrinjski Mostar": "Zrinjski Mostar",
        "NK Maribor": "Maribor",
        "Ħamrun Spartans FC": "Hamrun Spartans",
        "Hamrun Spartans FC": "Hamrun Spartans",
        "Valletta FC": "Valletta",
        "KAA Gent": "Gent",
        "KRC Genk": "Genk",
        "KV Mechelen": "Mechelen",
        "Malmö FF": "Malmo FF",
        "AIK Stockholm": "AIK",
        "Djurgårdens IF": "Djurgardens IF",
        "IFK Göteborg": "IFK Goteborg",
    }

    @staticmethod
    def _create_error_dict(error_msg: str, data: dict | None = None) -> dict:
        """
        Create a standardized error dictionary.

        This ensures consistent error handling across all FotMobProvider methods.

        Args:
            error_msg: Human-readable error message
            data: Optional partial data that was successfully retrieved

        Returns:
            Dict with standardized error structure
        """
        error_dict = {
            "error": True,
            "error_msg": error_msg,
        }
        if data is not None:
            error_dict["data"] = data
        return error_dict

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self._team_cache: dict[str, tuple[int, str]] = {}
        self._last_request_time = 0.0

        # V7.0: Initialize aggressive cache for FotMob data (24h TTL)
        # This reduces FotMob requests by 80-90%
        try:
            from src.utils.smart_cache import SmartCache

            self._swr_cache = SmartCache(name="fotmob_swr", max_size=2000, swr_enabled=True)
            logger.info(
                "✅ FotMob Provider initialized (UA rotation + Aggressive SWR caching enabled)"
            )
        except ImportError:
            self._swr_cache = None
            logger.warning("⚠️ SWR cache not available - using standard cache only")

        # V7.0: Cache metrics for monitoring (directly from SmartCache, not incremented)
        self._cache_hits = 0
        self._cache_misses = 0
        self._playwright_fallback_count = 0

        # V7.0: Playwright resources (lazy initialization)
        self._playwright = None
        self._browser = None
        self._playwright_available = False

        # V7.0: Lock for thread-safe Playwright initialization
        self._playwright_lock = threading.Lock()

        # V7.0: Browser restart mechanism for long-running processes
        self._playwright_request_count = 0
        self._max_requests_per_browser = 1000  # Restart browser every 1000 requests

    def _get_with_swr(
        self,
        cache_key: str,
        fetch_func: Callable[[], Any],
        ttl: int,
        stale_ttl: int | None = None,
    ) -> tuple[Any | None, bool]:
        """
        V7.0: Get data with Stale-While-Revalidate caching + metrics tracking.

        Returns (value, is_fresh) tuple where is_fresh indicates if data is fresh.
        """
        if self._swr_cache is None:
            # SWR not available - fetch directly
            self._cache_misses += 1
            return fetch_func(), True

        result, is_fresh = self._swr_cache.get_with_swr(
            key=cache_key,
            fetch_func=fetch_func,
            ttl=ttl,
            stale_ttl=stale_ttl,
        )

        # V7.0: Track cache metrics using SmartCache's internal metrics
        # Note: is_fresh=True means data is fresh (could be cache hit OR fresh fetch)
        # is_fresh=False means data is stale (stale cache hit) OR fetch failed
        # We use SmartCache's internal metrics to get accurate hit/miss counts
        if self._swr_cache is not None:
            cache_metrics = self._swr_cache.get_swr_metrics()
            self._cache_hits = cache_metrics.hits
            self._cache_misses = cache_metrics.misses

        return result, is_fresh

    def log_cache_metrics(self):
        """
        V7.0: Log cache performance metrics for monitoring.

        This helps track the effectiveness of the aggressive caching strategy.
        Note: Metrics are retrieved directly from SmartCache, not from instance attributes.
        """
        if self._swr_cache is not None:
            cache_metrics = self._swr_cache.get_swr_metrics()
            total_requests = cache_metrics.hits + cache_metrics.misses
            if total_requests > 0:
                hit_rate = (cache_metrics.hits / total_requests) * 100
                logger.info(
                    f"📊 [FOTMOB] Cache Metrics - "
                    f"Hits: {cache_metrics.hits}, "
                    f"Misses: {cache_metrics.misses}, "
                    f"Hit Rate: {hit_rate:.1f}%, "
                    f"Playwright Fallbacks: {self._playwright_fallback_count}"
                )
            else:
                logger.info("📊 [FOTMOB] Cache Metrics - No requests yet")
        else:
            # SWR cache not available - use instance attributes
            total_requests = self._cache_hits + self._cache_misses
            if total_requests > 0:
                hit_rate = (self._cache_hits / total_requests) * 100
                logger.info(
                    f"📊 [FOTMOB] Cache Metrics (Legacy) - "
                    f"Hits: {self._cache_hits}, "
                    f"Misses: {self._cache_misses}, "
                    f"Hit Rate: {hit_rate:.1f}%, "
                    f"Playwright Fallbacks: {self._playwright_fallback_count}"
                )
            else:
                logger.info("📊 [FOTMOB] Cache Metrics - No requests yet")

    def cleanup(self):
        """
        V7.0: Cleanup resources when shutting down.

        Ensures Playwright resources are properly released.
        """
        self._shutdown_playwright()
        logger.info("✅ [FOTMOB] Cleanup completed")

    def _rotate_user_agent(self):
        """Rotate User-Agent header for anti-bot evasion."""
        new_ua = get_random_user_agent()
        self.session.headers["User-Agent"] = new_ua
        logger.debug(f"🎭 UA rotated: {new_ua[:50]}...")

    def _rate_limit(self):
        """
        V6.2: Enforce minimum interval between FotMob requests to avoid bans.

        V6.3: CRITICAL FIX - Rate limiting is now enforced INSIDE the request loop
        to prevent burst patterns from multiple threads making simultaneous requests.

        Added jitter to prevent predictable request patterns that trigger anti-bot detection.
        """
        global _last_fotmob_request_time

        with _fotmob_rate_limit_lock:
            now = time.time()
            elapsed = now - _last_fotmob_request_time

            # V6.2: Add random jitter to prevent pattern detection
            jitter = random.uniform(FOTMOB_JITTER_MIN, FOTMOB_JITTER_MAX)
            required_interval = FOTMOB_MIN_REQUEST_INTERVAL + max(0, jitter)

            if elapsed < required_interval:
                sleep_time = required_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s (jitter: {jitter:+.2f}s)")
                time.sleep(sleep_time)

            _last_fotmob_request_time = time.time()

    def _make_request(
        self, url: str, retries: int = FOTMOB_MAX_RETRIES
    ) -> requests.Response | None:
        """
        V6.3: Make HTTP request with retry logic and specific error handling.

        CRITICAL FIX V6.3: Rate limiting ensures proper timing between requests.
        The lock establishes timing windows in _rate_limit(), but HTTP requests are made
        after lock release. Use max_workers=1 to prevent burst patterns that trigger
        FotMob's anti-bot detection.

        Key improvements:
        - Rotates User-Agent on EVERY request attempt (not just retries)
        - Enhanced rate limiting with jitter (now enforced correctly)
        - Better backoff strategy for 403 errors
        - Thread-safe request serialization
        """
        for attempt in range(retries):
            # V6.3: Rate limit BEFORE each request attempt (inside lock)
            # This ensures proper spacing between ALL requests, including retries
            self._rate_limit()

            # V6.2: Rotate UA on EVERY request attempt, not just retries
            # This prevents pattern detection from repeated UAs
            self._rotate_user_agent()

            try:
                # HTTP request is now made AFTER rate limiting (but still inside lock's timing window)
                resp = self.session.get(url, timeout=FOTMOB_REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    return resp

                if resp.status_code == 429:
                    # V6.2: Longer backoff for rate limit errors
                    delay = 3 ** (attempt + 1)  # 3s, 9s, 27s (was 2s, 4s, 8s)
                    logger.warning(
                        f"⚠️ FotMob rate limit (429). Attesa {delay}s prima del retry {attempt + 1}/{retries}"
                    )
                    time.sleep(delay)
                    continue

                if resp.status_code in (502, 503, 504):
                    delay = 2 ** (attempt + 1)
                    logger.warning(
                        f"⚠️ FotMob server error ({resp.status_code}). Retry {attempt + 1}/{retries} in {delay}s"
                    )
                    time.sleep(delay)
                    continue

                if resp.status_code == 403:
                    if attempt < retries - 1:
                        # V6.2: Reasonable backoff for 403 errors to avoid rapid retries
                        delay = 3 ** (attempt + 1)  # 3s, 9s, 27s (was 5s, 25s, 125s)
                        logger.warning(
                            f"⚠️ FotMob 403 - rotating UA and retrying in {delay}s ({attempt + 1}/{retries})"
                        )
                        time.sleep(delay)
                        continue
                    logger.error(
                        f"❌ FotMob accesso negato (403) dopo {retries} tentativi con UA diversi"
                    )
                    return None

                logger.error(f"❌ FotMob errore HTTP {resp.status_code}")
                return None

            except requests.exceptions.Timeout:
                delay = 2 ** (attempt + 1)
                logger.warning(f"⚠️ FotMob timeout. Retry {attempt + 1}/{retries} in {delay}s")
                time.sleep(delay)

            except requests.exceptions.ConnectionError as e:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"⚠️ FotMob errore connessione: {e}. Retry {attempt + 1}/{retries} in {delay}s"
                )
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"❌ FotMob errore richiesta: {e}")
                return None

        logger.error(f"❌ FotMob fallito dopo {retries} tentativi")
        return None

    # ============================================
    # V7.0: PLAYWRIGHT FALLBACK (Hybrid Approach)
    # ============================================

    def _initialize_playwright(self) -> tuple[bool, str | None]:
        """
        V7.0: Initialize Playwright for fallback when requests get 403.

        Returns:
            Tuple of (success, error_message)
        """
        # V7.0: Use lock to prevent concurrent initialization
        with self._playwright_lock:
            # Double-check after acquiring lock
            if self._playwright_available and self._browser is not None:
                return True, None

            try:
                from playwright.sync_api import sync_playwright

                logger.info("🌐 [FOTMOB] Initializing Playwright for fallback...")

                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )

                self._playwright_available = True
                logger.info("✅ [FOTMOB] Playwright initialized successfully")
                return True, None

            except ImportError:
                error_msg = "playwright package not installed"
                logger.warning(f"⚠️ [FOTMOB] {error_msg}")
                self._playwright_available = False
                return False, error_msg
            except Exception as e:
                error_msg = f"Playwright initialization failed: {e}"
                logger.error(f"❌ [FOTMOB] {error_msg}")
                self._playwright_available = False
                self._playwright = None
                self._browser = None
                return False, error_msg

    def _shutdown_playwright(self):
        """V7.0: Shutdown Playwright and release resources."""
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.warning(f"⚠️ [FOTMOB] Error closing browser: {e}")
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.warning(f"⚠️ [FOTMOB] Error stopping Playwright: {e}")
            self._playwright = None

        self._playwright_available = False

    def _fetch_with_playwright(self, url: str) -> dict | None:
        """
        V7.0: Fetch data using Playwright as fallback when requests get 403.

        This bypasses FotMob's anti-bot detection by using a real browser.

        Args:
            url: The FotMob API URL to fetch

        Returns:
            JSON data as dict or None if failed
        """
        if not self._playwright_available:
            # Try to initialize Playwright on-demand
            success, _ = self._initialize_playwright()
            if not success:
                logger.error("❌ [FOTMOB] Playwright not available for fallback")
                return None

        # V7.0: Check if browser needs restart (every 1000 requests)
        self._playwright_request_count += 1
        if self._playwright_request_count >= self._max_requests_per_browser:
            with self._playwright_lock:
                # Double-check after acquiring lock to prevent race condition
                if self._playwright_request_count >= self._max_requests_per_browser:
                    logger.info(
                        f"🔄 [FOTMOB] Restarting browser after {self._max_requests_per_browser} requests..."
                    )
                    self._shutdown_playwright()
                    success, _ = self._initialize_playwright()
                    if not success:
                        return None
                    self._playwright_request_count = 0

        page = None
        try:
            # Create a new page for each request
            page = self._browser.new_page()

            # Set realistic headers
            page.set_extra_http_headers(self.BASE_HEADERS)

            # Navigate to the URL
            page.goto(url, timeout=30000)

            # Wait for response
            page.wait_for_load_state("networkidle", timeout=15000)

            # Get the response body
            content = page.content()

            # Parse JSON
            data = json.loads(content)

            self._playwright_fallback_count += 1
            logger.info(
                f"✅ [FOTMOB] Playwright fallback successful (count: {self._playwright_fallback_count})"
            )

            return data

        except json.JSONDecodeError as e:
            logger.error(f"❌ [FOTMOB] Playwright JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [FOTMOB] Playwright fetch error: {e}")
            return None
        finally:
            # V7.0: Always close the page, even if exception occurred
            if page is not None:
                try:
                    page.close()
                except Exception as e:
                    logger.warning(f"⚠️ [FOTMOB] Error closing page: {e}")

    def _make_request_with_fallback(
        self, url: str, retries: int = FOTMOB_MAX_RETRIES
    ) -> ResponseLike | None:
        """
        V7.0: Hybrid approach - Try requests first, fallback to Playwright on 403.

        This reduces VPS load by using requests for 90% of requests (low load)
        and only using Playwright when necessary (high load but bypasses anti-bot).

        Args:
            url: The FotMob API URL to fetch
            retries: Number of retry attempts for requests

        Returns:
            Response object or None if all attempts failed
        """
        # Phase 1: Try requests (low load)
        for attempt in range(retries):
            # Rate limit BEFORE each request attempt
            self._rate_limit()

            # Rotate UA on EVERY request attempt
            self._rotate_user_agent()

            try:
                resp = self.session.get(url, timeout=FOTMOB_REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    return resp

                if resp.status_code == 429:
                    delay = 3 ** (attempt + 1)
                    logger.warning(
                        f"⚠️ [FOTMOB] Rate limit (429). Attesa {delay}s prima del retry {attempt + 1}/{retries}"
                    )
                    time.sleep(delay)
                    continue

                if resp.status_code in (502, 503, 504):
                    delay = 2 ** (attempt + 1)
                    logger.warning(
                        f"⚠️ [FOTMOB] Server error ({resp.status_code}). Retry {attempt + 1}/{retries} in {delay}s"
                    )
                    time.sleep(delay)
                    continue

                if resp.status_code == 403:
                    if attempt < retries - 1:
                        delay = 5 ** (attempt + 1)
                        logger.warning(
                            f"⚠️ [FOTMOB] 403 - rotating UA and retrying in {delay}s ({attempt + 1}/{retries})"
                        )
                        time.sleep(delay)
                        continue
                    # All retries failed with 403 - trigger Playwright fallback
                    logger.warning(
                        "⚠️ [FOTMOB] All request retries failed with 403 - trying Playwright fallback"
                    )
                    break

                logger.error(f"❌ [FOTMOB] HTTP error {resp.status_code}")
                return None

            except requests.exceptions.Timeout:
                delay = 2 ** (attempt + 1)
                logger.warning(f"⚠️ [FOTMOB] Timeout. Retry {attempt + 1}/{retries} in {delay}s")
                time.sleep(delay)

            except requests.exceptions.ConnectionError as e:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"⚠️ [FOTMOB] Connection error: {e}. Retry {attempt + 1}/{retries} in {delay}s"
                )
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"❌ [FOTMOB] Request error: {e}")
                return None

        # Phase 2: Fallback to Playwright (high load but bypasses anti-bot)
        logger.info("🔄 [FOTMOB] Falling back to Playwright...")
        data = self._fetch_with_playwright(url)

        if data is not None:
            # Create a mock response object using module-level class
            return _MockResponse(data)

        logger.error("❌ [FOTMOB] Both requests and Playwright failed")
        return None

    def search_team(self, team_name: str) -> list[dict]:
        """
        V7.0: Search for teams on FotMob with robust error handling and Playwright fallback.
        """
        try:
            encoded_name = urllib.parse.quote(team_name)
            url = f"{self.BASE_URL}/search/suggest?term={encoded_name}"

            # V7.0: Use hybrid approach (requests + Playwright fallback)
            resp = self._make_request_with_fallback(url)

            if resp is None:
                logger.debug(f"FotMob search fallito per: {team_name}")
                return []

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ FotMob risposta JSON non valida: {e}")
                return []
            except ValueError as e:
                logger.error(f"❌ FotMob risposta JSON non valida: {e}")
                return []

            results = []

            for group in data:
                suggestions = group.get("suggestions", [])
                for suggestion in suggestions:
                    if suggestion.get("type") == "team":
                        results.append(
                            {
                                "id": int(suggestion.get("id", 0)),
                                "name": suggestion.get("name", "Unknown"),
                                "country": suggestion.get("country", "Unknown"),
                            }
                        )

            return results

        except Exception as e:
            logger.error(f"❌ FotMob Search Error: {e}")
            return []

    def _strip_prefix(self, team_name: str) -> str:
        """Strip common prefixes from team name."""
        name = team_name.strip()
        for prefix in self.PREFIXES_TO_STRIP:
            if name.lower().startswith(prefix.lower() + " "):
                stripped = name[len(prefix) :].strip()
                if len(stripped) >= 3:
                    return stripped
        return name

    def _strip_suffix(self, team_name: str) -> str:
        """Strip common suffixes from team name."""
        name = team_name.strip()
        for suffix in self.SUFFIXES_TO_STRIP:
            if name.lower().endswith(" " + suffix.lower()):
                stripped = name[: -len(suffix) - 1].strip()
                if len(stripped) >= 3:
                    return stripped
        return name

    def _clean_team_name(self, team_name: str) -> str:
        """Apply both prefix and suffix stripping."""
        name = self._strip_prefix(team_name)
        name = self._strip_suffix(name)
        return name

    def search_team_id(self, team_name: str) -> tuple[int | None, str | None]:
        """Find FotMob team ID for a team name with fuzzy matching."""
        logger.debug(f"🔍 Team resolution START: '{team_name}'")
        if team_name in self.HARDCODED_IDS:
            team_id, fotmob_name = self.HARDCODED_IDS[team_name]
            logger.info(f"🔒 Hardcoded ID: {team_name} → {fotmob_name} (ID: {team_id})")
            self._team_cache[team_name.lower().strip()] = (team_id, fotmob_name)
            return team_id, fotmob_name

        cache_key = team_name.lower().strip()
        if cache_key in self._team_cache:
            return self._team_cache[cache_key]

        normalized_name = normalize_unicode(team_name)
        normalized_cache_key = normalized_name.lower().strip()
        if normalized_cache_key != cache_key and normalized_cache_key in self._team_cache:
            return self._team_cache[normalized_cache_key]

        if team_name in self.MANUAL_MAPPING:
            mapped_name = self.MANUAL_MAPPING[team_name]
            logger.info(f"📖 Manual mapping: {team_name} → {mapped_name}")
            results = self.search_team(mapped_name)
            if results:
                team_id = results[0]["id"]
                fotmob_name = results[0]["name"]
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Mapped: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name

        results = self.search_team(team_name)
        logger.debug(f"🔍 Direct search for '{team_name}': {len(results)} results")

        if results:
            for r in results:
                if r["name"].lower() == team_name.lower():
                    self._team_cache[cache_key] = (r["id"], r["name"])
                    logger.info(f"✅ Exact match: {r['name']} (ID: {r['id']})")
                    return r["id"], r["name"]

            candidate_names = [r["name"] for r in results]
            best_match = fuzzy_match_team(team_name, candidate_names)

            if best_match:
                for r in results:
                    if r["name"] == best_match:
                        self._team_cache[cache_key] = (r["id"], r["name"])
                        return r["id"], r["name"]

            if (
                len(results) == 1
                or SequenceMatcher(None, team_name.lower(), results[0]["name"].lower()).ratio()
                > 0.5
            ):
                team_id = results[0]["id"]
                fotmob_name = results[0]["name"]
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Found: {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name

        prefix_stripped = self._strip_prefix(team_name)
        if prefix_stripped != team_name and len(prefix_stripped) >= 3:
            logger.debug(f"🔄 Trying prefix-stripped: {team_name} → {prefix_stripped}")
            results = self.search_team(prefix_stripped)
            if results:
                candidate_names = [r["name"] for r in results]
                best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)

                if best_match:
                    for r in results:
                        if r["name"] == best_match:
                            self._team_cache[cache_key] = (r["id"], r["name"])
                            logger.info(
                                f"✅ Prefix-stripped match: {team_name} → {r['name']} (ID: {r['id']})"
                            )
                            return r["id"], r["name"]

                if len(results) == 1:
                    team_id = results[0]["id"]
                    fotmob_name = results[0]["name"]
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Prefix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name

        suffix_stripped = self._strip_suffix(team_name)
        if suffix_stripped != team_name and len(suffix_stripped) >= 3:
            logger.debug(f"🔄 Trying suffix-stripped: {team_name} → {suffix_stripped}")
            results = self.search_team(suffix_stripped)
            if results:
                candidate_names = [r["name"] for r in results]
                best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)

                if best_match:
                    for r in results:
                        if r["name"] == best_match:
                            self._team_cache[cache_key] = (r["id"], r["name"])
                            logger.info(
                                f"✅ Suffix-stripped match: {team_name} → {r['name']} (ID: {r['id']})"
                            )
                            return r["id"], r["name"]

                if len(results) == 1:
                    team_id = results[0]["id"]
                    fotmob_name = results[0]["name"]
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Suffix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name

        first_word = team_name.split()[0] if team_name else ""
        if first_word and len(first_word) >= 4 and first_word.lower() != team_name.lower():
            if first_word.upper() not in [p.upper() for p in self.PREFIXES_TO_STRIP]:
                results = self.search_team(first_word)
                if results:
                    candidate_names = [r["name"] for r in results]
                    best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)

                    if best_match:
                        for r in results:
                            if r["name"] == best_match:
                                self._team_cache[cache_key] = (r["id"], r["name"])
                                logger.info(
                                    f"✅ First-word match: {team_name} → {r['name']} (ID: {r['id']})"
                                )
                                return r["id"], r["name"]

        clean_name = self._clean_team_name(team_name)
        if (
            clean_name != team_name
            and clean_name != prefix_stripped
            and clean_name != suffix_stripped
        ):
            logger.debug(f"🔄 Trying fully cleaned: {team_name} → {clean_name}")
            results = self.search_team(clean_name)
            if results:
                team_id = results[0]["id"]
                fotmob_name = results[0]["name"]
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Cleaned match: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name

        if normalized_name != team_name:
            logger.debug(f"🔄 Trying unicode normalized: {team_name} → {normalized_name}")
            results = self.search_team(normalized_name)
            if results:
                candidate_names = [r["name"] for r in results]
                best_match = fuzzy_match_team(normalized_name, candidate_names, threshold=0.5)

                if best_match:
                    for r in results:
                        if r["name"] == best_match:
                            self._team_cache[cache_key] = (r["id"], r["name"])
                            self._team_cache[normalized_cache_key] = (r["id"], r["name"])
                            logger.info(
                                f"✅ Unicode normalized: {team_name} → {r['name']} (ID: {r['id']})"
                            )
                            return r["id"], r["name"]

                # If no fuzzy match, use first result
                team_id = results[0]["id"]
                fotmob_name = results[0]["name"]
                self._team_cache[cache_key] = (team_id, fotmob_name)
                self._team_cache[normalized_cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Unicode normalized: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name

        # Last word fallback: try searching with just the last word
        # This helps with Brazilian teams like "Sociedade Esportiva Palmeiras" -> "Palmeiras"
        words = team_name.split()
        if len(words) > 1:
            last_word = words[-1]
            if len(last_word) >= 4 and last_word.lower() not in [
                p.lower() for p in self.PREFIXES_TO_STRIP
            ]:
                logger.debug(f"🔄 Trying last word fallback: {team_name} → {last_word}")
                results = self.search_team(last_word)
                if results:
                    candidate_names = [r["name"] for r in results]
                    best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.3)

                    if best_match:
                        for r in results:
                            if r["name"] == best_match:
                                self._team_cache[cache_key] = (r["id"], r["name"])
                                logger.info(
                                    f"✅ Last-word match: {team_name} → {r['name']} (ID: {r['id']})"
                                )
                                return r["id"], r["name"]

                    if len(results) == 1:
                        team_id = results[0]["id"]
                        fotmob_name = results[0]["name"]
                        self._team_cache[cache_key] = (team_id, fotmob_name)
                        logger.info(
                            f"✅ Last-word fallback: {team_name} → {fotmob_name} (ID: {team_id})"
                        )
                        return team_id, fotmob_name

        logger.warning(f"⚠️ Team not found: {team_name}")
        return None, None

    def get_team_details(self, team_id: int, match_time: datetime = None) -> dict | None:
        """
        V7.0: Get team details including squad and next match with aggressive caching.

        Uses 24h TTL to reduce FotMob requests by 80-90%.
        Falls back to Playwright when requests get 403.
        """
        # V7.1: Include season in cache key to prevent serving stale data across seasons
        season = match_time.year if match_time else None
        cache_key = f"team_details:{team_id}:{season}" if season else f"team_details:{team_id}"

        # V7.0: Use SWR caching with aggressive TTL (24 hours)
        if self._swr_cache is not None:

            def fetch_team_details():
                url = f"{self.BASE_URL}/teams?id={team_id}"
                # V7.0: Use hybrid approach (requests + Playwright fallback)
                resp = self._make_request_with_fallback(url)

                if resp is None:
                    logger.warning(f"⚠️ FotMob team details non disponibili per ID {team_id}")
                    return self._create_error_dict(
                        "Dati FotMob non disponibili",
                        data={"team_id": team_id, "squad": {}, "fixtures": {}},
                    )

                try:
                    data = resp.json()
                    return data
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"❌ FotMob team details JSON non valido: {e}")
                    return self._create_error_dict(
                        "Risposta JSON non valida",
                        data={"team_id": team_id, "squad": {}, "fixtures": {}},
                    )

            # V7.0: Use aggressive TTL (24h fresh, 72h stale)
            result, is_fresh = self._get_with_swr(
                cache_key=cache_key,
                fetch_func=fetch_team_details,
                ttl=24 * 3600,  # 24 hours - aggressive caching
                stale_ttl=72 * 3600,  # 72 hours stale
            )

            if result is not None:
                freshness = "FRESH" if is_fresh else "STALE"
                logger.debug(f"📦 Team details for {team_id}: {freshness}")
                return result

        # Fallback: Use old cache if SWR not available
        if _SMART_CACHE_AVAILABLE:
            cached = get_team_cache().get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                return cached

        # Fetch without cache (shouldn't reach here)
        self._cache_misses += 1
        try:
            url = f"{self.BASE_URL}/teams?id={team_id}"
            resp = self._make_request_with_fallback(url)

            if resp is None:
                logger.warning(f"⚠️ FotMob team details non disponibili per ID {team_id}")
                return {
                    "_error": True,
                    "_error_msg": "Dati FotMob non disponibili",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {},
                }

            try:
                data = resp.json()

                if _SMART_CACHE_AVAILABLE and data and not data.get("_error"):
                    get_team_cache().set(cache_key, data, match_time=match_time)

                return data
            except json.JSONDecodeError as e:
                logger.error(f"❌ FotMob team details JSON non valido: {e}")
                return {
                    "_error": True,
                    "_error_msg": "Risposta JSON non valida",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {},
                }
            except ValueError as e:
                logger.error(f"❌ FotMob team details JSON non valido: {e}")
                return {
                    "_error": True,
                    "_error_msg": "Risposta JSON non valida",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {},
                }

        except Exception as e:
            logger.error(f"❌ FotMob Team Details Error: {e}")
            return {
                "_error": True,
                "_error_msg": str(e),
                "team_id": team_id,
                "squad": {},
                "fixtures": {},
            }

    def get_team_details_by_name(self, team_name: str, match_time: datetime = None) -> dict | None:
        """
        Get team details by team name (wrapper that converts name to ID).

        This is a convenience wrapper that converts a team name to a FotMob ID
        and then calls get_team_details with the ID.

        Args:
            team_name: Name of team
            match_time: Optional match time for cache TTL calculation

        Returns:
            Dict with team details or None if not found
        """
        try:
            # Convert team name to team ID
            team_id, fotmob_name = self.search_team_id(team_name)

            if team_id is None:
                logger.warning(f"⚠️ Team ID not found for: {team_name}")
                return self._create_error_dict(
                    f"Team not found: {team_name}",
                    data={"team_id": None, "squad": {}, "fixtures": {}},
                )

            # Get team details using the ID
            return self.get_team_details(team_id, match_time)

        except Exception as e:
            logger.error(f"❌ Error getting team details by name for {team_name}: {e}")
            return self._create_error_dict(
                str(e), data={"team_id": None, "squad": {}, "fixtures": {}}
            )

    def _extract_squad_injuries(self, team_data: dict, team_name: str) -> list[dict]:
        """Extract injured/unavailable players from team squad data."""
        injuries = []

        if not team_data or not isinstance(team_data, dict):
            return injuries

        try:
            squad_data = team_data.get("squad", {})

            if isinstance(squad_data, dict):
                squad_groups = squad_data.get("squad", [])
            else:
                squad_groups = squad_data if isinstance(squad_data, list) else []

            if squad_groups is None:
                squad_groups = []

            for group in squad_groups:
                if not isinstance(group, dict):
                    continue

                players = group.get("members") or []
                if not isinstance(players, list):
                    continue

                for player in players:
                    if not isinstance(player, dict):
                        continue

                    injury = player.get("injury")
                    if injury:
                        injuries.append(
                            {
                                "name": player.get("name", "Unknown"),
                                "reason": injury.get("type", "Injury")
                                if isinstance(injury, dict)
                                else str(injury),
                                "status": injury.get("expectedReturn", "Unknown")
                                if isinstance(injury, dict)
                                else "Unknown",
                                "is_injured": True,
                            }
                        )

                    injury_info = player.get("injuryInformation")
                    if injury_info and isinstance(injury_info, dict):
                        if not any(i["name"] == player.get("name") for i in injuries):
                            injuries.append(
                                {
                                    "name": player.get("name", "Unknown"),
                                    "reason": injury_info.get("injuryType", "Injury"),
                                    "status": injury_info.get("expectedReturn", "Unknown"),
                                    "is_injured": True,
                                }
                            )

                    if player.get("isInjured") or player.get("isSuspended"):
                        if not any(i["name"] == player.get("name") for i in injuries):
                            injuries.append(
                                {
                                    "name": player.get("name", "Unknown"),
                                    "reason": "Suspended"
                                    if player.get("isSuspended")
                                    else "Injured",
                                    "status": "Unavailable",
                                    "is_injured": True,
                                }
                            )

            if injuries:
                logger.info(f"✅ Found {len(injuries)} unavailable players for {team_name}")

        except Exception as e:
            logger.error(f"Error extracting injuries: {e}")

        return injuries

    def validate_home_away_order(
        self, odds_home_team: str, odds_away_team: str
    ) -> tuple[str, str, bool]:
        """
        V5.1: Validate and correct home/away order using FotMob as source of truth.

        The Odds API sometimes returns inverted home/away teams. FotMob's 'is_home'
        field indicates whether the searched team plays at home, allowing us to
        detect and correct inversions.

        Strategy:
        1. Search for home team in FotMob
        2. Check if FotMob says this team plays at home (is_home=True)
        3. If is_home=False, the teams are inverted → swap them

        Args:
            odds_home_team: Home team name from Odds API
            odds_away_team: Away team name from Odds API

        Returns:
            Tuple of (correct_home_team, correct_away_team, was_swapped)
            - was_swapped: True if teams were inverted and corrected
        """
        try:
            # Get fixture details for the "home" team according to Odds API
            fixture = self.get_fixture_details(odds_home_team)

            if not fixture or fixture.get("error"):
                # FotMob lookup failed - trust Odds API order
                logger.debug(f"FotMob lookup failed for {odds_home_team}, trusting Odds API order")
                return odds_home_team, odds_away_team, False

            is_home = fixture.get("is_home")

            if is_home is None:
                logger.debug("FotMob 'is_home' field missing, trusting Odds API order")
                return odds_home_team, odds_away_team, False

            # Verify that the opponent in the fixture matches the expected away team
            # This prevents swapping when the fixture is for a different match altogether
            fixture_opponent = fixture.get("opponent", "")
            if fixture_opponent and odds_away_team:
                expected_opponent = normalize_unicode(odds_away_team).lower()
                actual_opponent = normalize_unicode(fixture_opponent).lower()

                if (
                    expected_opponent not in actual_opponent
                    and actual_opponent not in expected_opponent
                ):
                    logger.debug(
                        f"FotMob opponent mismatch: expected '{odds_away_team}', got '{fixture_opponent}'"
                    )
                    logger.debug("Trusting Odds API order due to mismatch")
                    return odds_home_team, odds_away_team, False

            if is_home:
                # Team is confirmed as home by FotMob - no swap needed
                return odds_home_team, odds_away_team, False
            else:
                # Team is away according to FotMob - swap them
                logger.warning(
                    f"⚠️ Home/Away inverted by Odds API: {odds_home_team} vs {odds_away_team}"
                )
                logger.warning(f"✅ Corrected to: {odds_away_team} vs {odds_home_team}")
                return odds_away_team, odds_home_team, True

        except Exception as e:
            logger.error(f"Home/Away validation failed: {e}")
            return odds_home_team, odds_away_team, False

    def get_match_details(
        self, team_name: str, home_team: str = None, away_team: str = None, match_date=None
    ) -> dict | None:
        """
        Get match details including missing players with Home/Away alignment.

        Aligns FotMob data to match Odds API structure (Source of Truth).
        If FotMob has inverted home/away, swaps the data accordingly.

        CRITICAL: Validates kickoff time to prevent wrong match mapping.
        If FotMob returns a match >4 hours different from expected, rejects it.

        Args:
            team_name: Name of the team to search
            home_team: Expected home team from Odds API (optional)
            away_team: Expected away team from Odds API (optional)
            match_date: Expected match datetime for validation (datetime object or ISO string)

        Returns:
            Dict with match intel, aligned to Odds API home/away, or None if wrong match
        """
        result = self.get_fixture_details(team_name)

        if result and not result.get("error"):
            # Transform injuries to missing_players format
            result["missing_players"] = result.get("injuries", [])

            fotmob_team = result.get("team_name", team_name)
            fotmob_opponent = result.get("opponent", "Unknown")

            # Default assignment
            result["home_team"] = fotmob_team
            result["away_team"] = fotmob_opponent

            # V5.1: Validate home/away order against Odds API
            if home_team and away_team and home_team != away_team:
                validated_home, validated_away, swapped = self.validate_home_away_order(
                    home_team, away_team
                )
                result["home_team"] = validated_home
                result["away_team"] = validated_away

                if swapped:
                    logger.info(f"✅ Home/Away aligned to Odds API for {home_team} vs {away_team}")

            # ========================================
            # H2H HISTORY EXTRACTION (V4.1 - BTTS Intelligence)
            # ========================================
            # Fetch last 5 H2H matches for BTTS trend analysis
            result["h2h_history"] = []

            if result.get("match_id"):
                try:
                    match_data = self.get_match_lineup(result["match_id"])
                    if match_data:
                        # Navigate safe paths for H2H data
                        content = match_data.get("content", {})

                        # Try multiple FotMob H2H paths
                        # V7.0: Safe nested dictionary access with type checking
                        raw_h2h = (
                            safe_get(content, "h2h", "matches")
                            or safe_get(content, "matchFacts", "h2h", "matches")
                            or safe_get(content, "h2h")
                            or []
                        )

                        h2h_data = []
                        for m in raw_h2h:
                            # Stop if we have 5 valid matches
                            if len(h2h_data) >= 5:
                                break

                            if not isinstance(m, dict):
                                continue

                            # FotMob H2H structure: scores are in status.scoreStr ("2 - 1")
                            # Only consider matches that have started (played)
                            status = m.get("status", {})
                            if not status.get("started", False):
                                continue  # Skip future matches

                            h_score = None
                            a_score = None

                            # Priority 1: Direct score fields
                            h_score = m.get("homeScore")
                            a_score = m.get("awayScore")

                            # Priority 2: Nested in home/away objects
                            if h_score is None:
                                home_obj = m.get("home", {})
                                if isinstance(home_obj, dict):
                                    h_score = home_obj.get("score")
                            if a_score is None:
                                away_obj = m.get("away", {})
                                if isinstance(away_obj, dict):
                                    a_score = away_obj.get("score")

                            # Priority 3: Parse from status.scoreStr ("2 - 1")
                            if h_score is None or a_score is None:
                                score_str = status.get("scoreStr", "")
                                if score_str and " - " in score_str:
                                    try:
                                        parts = score_str.split(" - ")
                                        if len(parts) == 2:
                                            h_score = int(parts[0].strip())
                                            a_score = int(parts[1].strip())
                                    except (ValueError, IndexError):
                                        pass

                            # Skip if still no valid scores
                            if h_score is None or a_score is None:
                                continue

                            try:
                                h2h_data.append(
                                    {"home_score": int(h_score), "away_score": int(a_score)}
                                )
                            except (ValueError, TypeError):
                                # Skip malformed score data
                                continue

                        result["h2h_history"] = h2h_data

                        if h2h_data:
                            logger.info(
                                f"📊 H2H History: Found {len(h2h_data)} matches for {result.get('home_team', 'Unknown')} vs {result.get('away_team', 'Unknown')}"
                            )

                except Exception as e:
                    logger.debug(f"H2H extraction failed (non-critical): {e}")

            # Kickoff time validation
            if match_date:
                match_time = result.get("match_time")
                if match_time:
                    try:
                        match_dt = parser.parse(match_time).astimezone(pytz.UTC)

                        if isinstance(match_date, str):
                            expected_dt = parser.parse(match_date).astimezone(pytz.UTC)
                        elif isinstance(match_date, datetime):
                            if match_date.tzinfo is None:
                                expected_dt = match_date.replace(tzinfo=pytz.UTC)
                            else:
                                expected_dt = match_date.astimezone(pytz.UTC)
                        else:
                            expected_dt = None

                        if expected_dt:
                            delta = abs(match_dt - expected_dt)
                            delta_hours = delta.total_seconds() / 3600

                            if delta_hours > 4:
                                logger.warning(
                                    f"⚠️ Match time mismatch: found {match_dt}, expected {expected_dt}"
                                )
                                logger.warning(
                                    f"⚠️ Delta {delta_hours:.1f}h exceeds 4h tolerance - rejecting"
                                )
                                return None
                            else:
                                logger.debug(
                                    f"✅ Match time validated: diff={delta_hours:.1f}h (within 4h tolerance)"
                                )
                    except Exception as e:
                        logger.debug(f"Date validation error (non-critical): {e}")

        return result

    def get_match_lineup(self, match_id: int) -> dict | None:
        """
        V7.0: Get match lineup and detailed match data using match ID with Playwright fallback.
        """
        cache_key = f"match_lineup:{match_id}"

        # V7.0: Use SWR caching with aggressive TTL
        if self._swr_cache is not None:

            def fetch_match_lineup():
                url = f"{self.BASE_URL}/matchDetails?matchId={match_id}"
                # V7.0: Use hybrid approach (requests + Playwright fallback)
                resp = self._make_request_with_fallback(url)

                if resp is None:
                    logger.warning(f"⚠️ FotMob match lineup non disponibili per ID {match_id}")
                    return None

                try:
                    data = resp.json()
                    return data
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"❌ FotMob match lineup JSON non valido: {e}")
                    return None

            # V7.0: Use aggressive TTL (24h fresh, 72h stale)
            result, is_fresh = self._get_with_swr(
                cache_key=cache_key,
                fetch_func=fetch_match_lineup,
                ttl=24 * 3600,  # 24 hours - aggressive caching
                stale_ttl=72 * 3600,  # 72 hours stale
            )

            if result is not None:
                freshness = "FRESH" if is_fresh else "STALE"
                logger.debug(f"📦 Match lineup for {match_id}: {freshness}")
                return result

        # Fallback: Use old cache if SWR not available
        if _SMART_CACHE_AVAILABLE:
            cached = get_match_cache().get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                return cached

        # Fetch without cache (shouldn't reach here)
        self._cache_misses += 1
        try:
            url = f"{self.BASE_URL}/matchDetails?matchId={match_id}"
            # V7.0: Use hybrid approach (requests + Playwright fallback)
            resp = self._make_request_with_fallback(url)

            if resp is None:
                logger.warning(f"⚠️ FotMob match lineup non disponibili per ID {match_id}")
                return None

            try:
                data = resp.json()

                if _SMART_CACHE_AVAILABLE and data:
                    get_match_cache().set(cache_key, data)

                return data
            except json.JSONDecodeError as e:
                logger.error(f"❌ FotMob match lineup JSON non valido: {e}")
                return None
            except ValueError as e:
                logger.error(f"❌ FotMob match lineup JSON non valido: {e}")
                return None

        except Exception as e:
            logger.error(f"❌ FotMob Match Lineup Error: {e}")
            return None

    def get_match_stats(self, match_id: int) -> dict | None:
        """
        Get match statistics including corners, cards, possession, shots, xG, etc.

        This method extracts detailed match statistics from FotMob API response.
        Used by settlement service to evaluate corner/card bets.

        Args:
            match_id: FotMob match ID

        Returns:
            Dict with match statistics or None if unavailable
            Keys: home_corners, away_corners, home_yellow_cards, away_yellow_cards,
                  home_red_cards, away_red_cards, home_xg, away_xg,
                  home_possession, away_possession, home_shots_on_target,
                  away_shots_on_target, home_big_chances, away_big_chances,
                  home_fouls, away_fouls
        """
        # Get match lineup data which includes statistics
        match_data = self.get_match_lineup(match_id)
        if not match_data:
            logger.warning(f"⚠️ Could not fetch match stats for ID {match_id}")
            return None

        try:
            result = {}

            # Navigate to statistics section
            # FotMob API structure varies, try multiple paths
            content = match_data.get("content", {}) if isinstance(match_data, dict) else {}
            match_stats = (
                content.get("stats", {})
                or content.get("matchStats", {})
                or content.get("statistics", {})
                or {}
            )

            # Extract home team stats
            home_stats = match_stats.get("home", {}) if isinstance(match_stats, dict) else {}
            # Extract away team stats
            away_stats = match_stats.get("away", {}) if isinstance(match_stats, dict) else {}

            # Extract corners
            result["home_corners"] = home_stats.get("corners")
            result["away_corners"] = away_stats.get("corners")

            # Extract cards
            result["home_yellow_cards"] = home_stats.get("yellowCards")
            result["away_yellow_cards"] = away_stats.get("yellowCards")
            result["home_red_cards"] = home_stats.get("redCards")
            result["away_red_cards"] = away_stats.get("redCards")

            # Extract possession (percentage)
            result["home_possession"] = home_stats.get("possession")
            result["away_possession"] = away_stats.get("possession")

            # Extract shots on target
            result["home_shots_on_target"] = home_stats.get("shotsOnTarget")
            result["away_shots_on_target"] = away_stats.get("shotsOnTarget")

            # Extract big chances
            result["home_big_chances"] = home_stats.get("bigChances")
            result["away_big_chances"] = away_stats.get("bigChances")

            # Extract expected goals (xG)
            result["home_xg"] = home_stats.get("xg")
            result["away_xg"] = away_stats.get("xg")

            # Extract fouls
            result["home_fouls"] = home_stats.get("fouls")
            result["away_fouls"] = away_stats.get("fouls")

            # Check if we got any data
            has_data = any(v is not None for v in result.values())
            if not has_data:
                logger.warning(f"⚠️ No statistics available for match {match_id}")
                return None

            return result

        except Exception as e:
            logger.error(f"❌ Error extracting match stats for {match_id}: {e}")
            return None

    def get_table_context(self, team_name: str) -> dict:
        """
        LAYER 1: MOTIVATION ANALYSIS

        Get league table position and motivation context for a team.
        Safe: Returns "Unknown" if table data unavailable (cup match, season start).

        Args:
            team_name: Name of the team

        Returns:
            Dict with position, zone, motivation level
        """
        result = {
            "position": None,
            "total_teams": None,
            "zone": "Unknown",
            "motivation": "Unknown",
            "form": None,
            "points": None,
            "played": None,
            "matches_remaining": None,
            "error": None,
        }

        try:
            # Get team ID (use top-level import)
            team_id = None
            if _TEAM_MAPPING_AVAILABLE and get_fotmob_team_id is not None:
                team_id = get_fotmob_team_id(team_name)

            if not team_id:
                team_id, _ = self.search_team_id(team_name)

            if not team_id:
                result["error"] = "Team not found"
                return result

            # Get team details
            team_data = self.get_team_details(team_id)
            if not team_data:
                result["error"] = "Could not fetch team data"
                return result

            # Extract table info from team data
            # FotMob structure: team_data -> tableData or overview -> table or table
            table_data = team_data.get("tableData")

            if not table_data:
                # Try alternative paths
                overview = team_data.get("overview", {})
                table_data = overview.get("table")

            if not table_data:
                # V4.4: Try direct 'table' key (FotMob API variation)
                table_data = team_data.get("table")

            if not table_data:
                # Season might not have started or it's a cup match
                result["zone"] = "Unknown"
                result["motivation"] = "Unknown (No table data - cup match or season start)"
                logger.info(f"⚠️ No table data for {team_name} - possibly cup match or early season")
                return result

            # Parse table position
            # FotMob table structure varies, try common patterns
            if isinstance(table_data, dict):
                tables = table_data.get("tables", [table_data])
            elif isinstance(table_data, list):
                # V4.4: Handle table[0]['data'] structure
                tables = []
                for item in table_data:
                    if isinstance(item, dict):
                        # Try item['data'] first (new FotMob structure)
                        if "data" in item:
                            tables.append(item["data"])
                        else:
                            tables.append(item)
            else:
                tables = []

            for table in tables:
                if not isinstance(table, dict):
                    continue

                # V7.0: Safe nested dictionary access with type checking
                rows = safe_get(table, "table", "all", default=[])
                if not rows:
                    rows = table.get("all", []) if isinstance(table, dict) else []

                total_teams = len(rows)

                for row in rows:
                    if not isinstance(row, dict):
                        continue

                    row_name = row.get("name", "").lower()
                    row_short = row.get("shortName", "").lower()

                    if team_name.lower() in row_name or team_name.lower() in row_short:
                        position = row.get("idx", row.get("position"))

                        # Validate position is a valid number (not None, not 0 for 1-indexed leagues)
                        if (
                            position is not None
                            and isinstance(position, (int, float))
                            and position > 0
                            and position <= total_teams
                        ):
                            result["position"] = position
                            result["total_teams"] = total_teams

                            # Calculate zone based on position percent
                            pct = position / total_teams

                            # Determine motivation zone
                            if pct <= 0.20:
                                result["zone"] = "Champions League"
                                result["motivation"] = "Top of table - Secure Champions League"
                            elif pct <= 0.40:
                                result["zone"] = "European Spots"
                                result["motivation"] = "Push for European qualification"
                            elif pct <= 0.60:
                                result["zone"] = "Mid-Table"
                                result["motivation"] = "Mid-table safety - No pressure"
                            elif pct <= 0.80:
                                result["zone"] = "Relegation Battle"
                                result["motivation"] = "Fight against relegation"
                            else:
                                result["zone"] = "Relegation Zone"
                                result["motivation"] = "Direct relegation threat"

                            # Extract additional stats from table row
                            result["points"] = row.get("pts")
                            result["played"] = row.get("played")
                            result["form"] = self._extract_form(row)

                            return result

        except Exception as e:
            logger.error(f"Error getting table context for {team_name}: {e}")
            result["error"] = str(e)

        return result

    def _extract_form(self, team_row: dict) -> str | None:
        """Extract last 5 matches form string from table row."""
        form = team_row.get("form", [])
        if isinstance(form, list):
            form_str = ""
            for f in form[-5:]:
                if isinstance(f, dict):
                    result_val = f.get("result", "?")
                    form_str += result_val[0].upper() if result_val else "?"
                elif isinstance(f, str):
                    form_str += f[0].upper() if f else "?"
            return form_str if form_str else None

    def get_league_table_context(
        self,
        league_id: str = None,
        home_team_id: str = None,
        away_team_id: str = None,
        home_team_name: str = None,
        away_team_name: str = None,
    ) -> dict:
        """
        Get league table context for both home and away teams.

        This method combines table context for both teams to provide complete
        motivation analysis for match prediction.

        Args:
            league_id: League ID (not used, kept for compatibility)
            home_team_id: Home team FotMob ID (not used, kept for compatibility)
            away_team_id: Away team FotMob ID (not used, kept for compatibility)
            home_team_name: Home team name
            away_team_name: Away team name

        Returns:
            Dict with combined context for both teams:
            - home_rank, home_zone, home_form, home_motivation
            - away_rank, away_zone, away_form, away_motivation
            - motivation_summary: Combined summary
            - error: Error message if any
        """
        result = {
            "home_rank": None,
            "home_zone": "Unknown",
            "home_form": None,
            "home_motivation": "Unknown",
            "away_rank": None,
            "away_zone": "Unknown",
            "away_form": None,
            "away_motivation": "Unknown",
            "motivation_summary": "N/A",
            "error": None,
        }

        try:
            # Get context for home team
            if home_team_name:
                home_context = self.get_table_context(home_team_name)
                if home_context and not home_context.get("error"):
                    result["home_rank"] = home_context.get("position")
                    result["home_zone"] = home_context.get("zone", "Unknown")
                    result["home_form"] = home_context.get("form")
                    result["home_motivation"] = home_context.get("motivation", "Unknown")
                else:
                    result["error"] = (
                        home_context.get("error") if home_context else "Home team not found"
                    )

            # Get context for away team
            if away_team_name:
                away_context = self.get_table_context(away_team_name)
                if away_context and not away_context.get("error"):
                    result["away_rank"] = away_context.get("position")
                    result["away_zone"] = away_context.get("zone", "Unknown")
                    result["away_form"] = away_context.get("form")
                    result["away_motivation"] = away_context.get("motivation", "Unknown")
                else:
                    if not result["error"]:
                        result["error"] = (
                            away_context.get("error") if away_context else "Away team not found"
                        )

            # Create motivation summary
            if result["home_motivation"] != "Unknown" and result["away_motivation"] != "Unknown":
                result["motivation_summary"] = (
                    f"Home: {result['home_motivation']} | Away: {result['away_motivation']}"
                )
            elif result["home_motivation"] != "Unknown":
                result["motivation_summary"] = f"Home: {result['home_motivation']}"
            elif result["away_motivation"] != "Unknown":
                result["motivation_summary"] = f"Away: {result['away_motivation']}"

            return result

        except Exception as e:
            logger.error(f"❌ Error getting league table context: {e}")
            result["error"] = str(e)
            return result

    def get_fixture_details(self, team_name: str) -> dict | None:
        """Get fixture details for a team's next match."""
        team_id = None
        fotmob_name = team_name

        if _TEAM_MAPPING_AVAILABLE and get_fotmob_team_id is not None:
            team_id = get_fotmob_team_id(team_name)

        if not team_id:
            team_id, fotmob_name = self.search_team_id(team_name)

        if not team_id:
            return self._create_error_dict(
                f"Team not found: {team_name}", data={"source": "FotMob"}
            )

        try:
            team_data = self.get_team_details(team_id)
            if not team_data:
                return self._create_error_dict(
                    "Could not fetch team details", data={"source": "FotMob"}
                )

            injuries = self._extract_squad_injuries(team_data, fotmob_name)

            next_match = team_data.get("nextMatch")
            if not next_match:
                # V7.0: Safe nested dictionary access with type checking
                fixtures = safe_get(team_data, "fixtures")
                upcoming = safe_get(fixtures, "allFixtures", "nextMatch")
                if upcoming:
                    next_match = upcoming

            if not next_match:
                return {
                    "team_id": team_id,
                    "team_name": fotmob_name,
                    "injuries": injuries,
                    "confirmed_absentees": injuries,
                    "source": "FotMob",
                }

            match_id = next_match.get("id")
            is_home = next_match.get("home", None)

            return {
                "team_id": team_id,
                "team_name": fotmob_name,
                "match_id": match_id,
                # V7.0: Safe nested dictionary access with type checking
                "opponent": safe_get(next_match, "opponent", "name", default="Unknown"),
                "match_time": safe_get(next_match, "utcTime"),
                "is_home": is_home,
                "injuries": injuries,
                "confirmed_absentees": injuries,
                "source": "FotMob",
            }

        except Exception as e:
            logger.error(f"FotMob Fixture Error: {e}")
            return {"error": str(e), "source": "FotMob"}

    def get_referee_info(self, team_name: str) -> dict | None:
        """
        Get referee information for a team's next match.

        This method extracts referee data from FotMob match lineup data.
        Note: FotMob API provides referee name but not statistics (cards per game).
        Statistics must be fetched separately via search providers (Tavily/Perplexity).

        Args:
            team_name: Name of the team

        Returns:
            Dict with referee info: {'name': str, 'strictness': str, 'cards_per_game': float}
            Returns None if referee data is unavailable
        """
        try:
            # Step 1: Get fixture details to find the next match
            fixture = self.get_fixture_details(team_name)

            if not fixture or fixture.get("error"):
                logger.debug(f"No fixture data for {team_name}, cannot get referee info")
                return None

            # Step 2: Get match ID from fixture
            match_id = fixture.get("match_id")

            if not match_id:
                logger.debug(f"No match ID in fixture for {team_name}")
                return None

            # Step 3: Get match lineup data which contains referee information
            match_data = self.get_match_lineup(match_id)

            if not match_data:
                logger.debug(f"No match lineup data for match_id {match_id}")
                return None

            # Step 4: Extract referee name from match data
            # FotMob structure varies, try multiple paths
            referee_name = None

            # Path 1: Direct referee field in content
            content = match_data.get("content", {})
            if isinstance(content, dict):
                referee_name = content.get("referee")

                # Path 2: Nested in matchFacts
                if not referee_name:
                    match_facts = content.get("matchFacts", {})
                    if isinstance(match_facts, dict):
                        referee_name = match_facts.get("referee")

                # Path 3: Nested in general
                if not referee_name:
                    general = content.get("general", {})
                    if isinstance(general, dict):
                        referee_name = general.get("referee")

                # Path 4: Nested in matchData
                if not referee_name:
                    match_data_obj = content.get("matchData", {})
                    if isinstance(match_data_obj, dict):
                        referee_name = match_data_obj.get("referee")

            # Path 5: Try top-level match structure
            if not referee_name:
                referee_name = match_data.get("referee")

            # Path 6: Try nested referee object with name field
            if not referee_name:
                if isinstance(content, dict):
                    referee_obj = content.get("referee")
                    if isinstance(referee_obj, dict):
                        referee_name = referee_obj.get("name")

            # Normalize referee name if found
            if referee_name:
                referee_name = str(referee_name).strip()
                if referee_name and referee_name.lower() != "unknown":
                    logger.info(f"⚖️ Referee found for {team_name}: {referee_name}")

                    # Return structured referee info
                    # Note: cards_per_game and strictness will be populated by search providers
                    return {
                        "name": referee_name,
                        "strictness": "unknown",  # Will be determined by search providers
                        "cards_per_game": None,  # Will be fetched by search providers
                    }

            logger.debug(f"No referee data found for {team_name}'s next match")
            return None

        except Exception as e:
            logger.error(f"Error getting referee info for {team_name}: {e}")
            return None

    def get_full_team_context(self, team_name: str) -> dict[str, Any]:
        """
        Get full team context including injuries, motivation, and fatigue.

        This method aggregates data from multiple FotMob endpoints to provide
        comprehensive team intelligence for match analysis.

        Args:
            team_name: Name of team

        Returns:
            Dict with team context: injuries, motivation, fatigue, etc.
        """
        try:
            # Get team details which includes injuries
            # Use the wrapper function that converts team_name to team_id
            team_details = self.get_team_details_by_name(team_name)

            if not team_details or team_details.get("error"):
                error_msg = (
                    team_details.get("error_msg", "Unknown error")
                    if team_details
                    else "Team not found"
                )
                return self._create_error_dict(
                    error_msg,
                    data={
                        "injuries": [],
                        "motivation": {
                            "zone": "Unknown",
                            "position": None,
                            "motivation": "Unknown",
                        },
                        "fatigue": {"fatigue_level": "Unknown", "hours_since_last": None},
                    },
                )

            # Extract injuries
            injuries = team_details.get("injuries", [])

            # Get table context for motivation
            table_context = self.get_table_context(team_name)

            # Build full context
            # V5.3: motivation and fatigue are always dicts for consistent API
            motivation_dict = {
                "zone": table_context.get("zone", "Unknown"),
                "position": table_context.get("position"),
                "motivation": table_context.get("motivation", "Unknown"),
            }
            fatigue_dict = {
                "fatigue_level": "Unknown",  # Would need match history to calculate
                "hours_since_last": None,
            }

            context = {
                "team_name": team_name,
                "injuries": injuries,
                "motivation": motivation_dict,
                "motivation_zone": table_context.get("zone", "Unknown"),  # Keep for backward compat
                "table_position": table_context.get("position"),
                "form": table_context.get("form"),
                "fatigue": fatigue_dict,
                "error": None,
            }

            logger.info(
                f"✅ Full team context for {team_name}: {len(injuries)} injuries, motivation={context['motivation']}"
            )
            return context

        except Exception as e:
            logger.error(f"Error getting full team context for {team_name}: {e}")
            return {
                "injuries": [],
                "motivation": {"zone": "Unknown", "position": None, "motivation": "Unknown"},
                "fatigue": {"fatigue_level": "Unknown", "hours_since_last": None},
                "error": str(e),
            }

    def get_turnover_risk(self, team_name: str) -> dict[str, Any] | None:
        """
        Get turnover risk assessment for a team.

        Analyzes squad stability and recent transfers to assess
        the risk of player turnover affecting match performance.

        Args:
            team_name: Name of team

        Returns:
            Dict with turnover risk assessment or None if unavailable
        """
        try:
            # Get team details to analyze squad
            # Use the wrapper function that converts team_name to team_id
            team_details = self.get_team_details_by_name(team_name)

            if not team_details or team_details.get("error"):
                return None

            # Extract squad information
            squad_data = team_details.get("squad", {})

            # Analyze turnover risk factors
            # Note: FotMob doesn't provide direct turnover data, so we estimate
            # based on squad size and recent activity
            risk_level = "MEDIUM"
            risk_factors = []

            # Factor 1: Squad size (smaller squads = higher turnover risk)
            squad_size = len(squad_data.get("players", [])) if isinstance(squad_data, dict) else 0
            if squad_size < 20:
                risk_level = "HIGH"
                risk_factors.append("Small squad (<20 players)")
            elif squad_size < 25:
                risk_level = "MEDIUM"

            # Factor 2: Check for recent transfers (not directly available from FotMob)
            # This would require additional data sources

            result = {
                "team_name": team_name,
                "risk_level": risk_level,
                "squad_size": squad_size,
                "risk_factors": risk_factors,
                "recommendation": self._get_turnover_recommendation(risk_level),
                "missing_names": [],  # Would need transfer history data
                "count": 0,  # Would need transfer history data
                "error": None,
            }

            logger.info(f"✅ Turnover risk for {team_name}: {risk_level} (squad: {squad_size})")
            return result

        except Exception as e:
            logger.error(f"Error getting turnover risk for {team_name}: {e}")
            return None

    def _get_turnover_recommendation(self, risk_level: str) -> str:
        """Get recommendation based on turnover risk level."""
        recommendations = {
            "HIGH": "Consider squad rotation - high turnover risk may affect performance",
            "MEDIUM": "Monitor squad stability - moderate turnover risk",
            "LOW": "Stable squad - low turnover risk",
        }
        return recommendations.get(risk_level, "Unknown risk level")

    def get_stadium_coordinates(self, team_name: str) -> tuple[float, float] | None:
        """
        Get stadium coordinates for a team.

        Extracts geographical location of team's home stadium
        for weather analysis and travel distance calculations.

        Args:
            team_name: Name of team

        Returns:
            Tuple of (latitude, longitude) or None if unavailable
        """
        try:
            # Get team details to find stadium info
            # Use the wrapper function that converts team_name to team_id
            team_details = self.get_team_details_by_name(team_name)

            if not team_details or team_details.get("error"):
                return None

            # Try to extract stadium information from team details
            # FotMob may include stadium data in various locations
            stadium_info = None

            # Path 1: Direct stadium field
            if "stadium" in team_details:
                stadium_info = team_details["stadium"]

            # Path 2: Nested in team data
            if not stadium_info and "teamData" in team_details:
                team_data = team_details["teamData"]
                if isinstance(team_data, dict):
                    stadium_info = team_data.get("stadium")

            # Path 3: Check for venue information
            if not stadium_info and "venue" in team_details:
                stadium_info = team_details["venue"]

            if not stadium_info:
                logger.debug(f"No stadium info found for {team_name}")
                return None

            # Extract coordinates from stadium info
            # Stadium info may be a dict with lat/lon or a string
            if isinstance(stadium_info, dict):
                lat = stadium_info.get("lat") or stadium_info.get("latitude")
                lon = stadium_info.get("lon") or stadium_info.get("longitude")

                if lat is not None and lon is not None:
                    logger.info(f"✅ Stadium coordinates for {team_name}: ({lat}, {lon})")
                    return (float(lat), float(lon))

            logger.debug(f"Stadium coordinates not available for {team_name}")
            return None

        except Exception as e:
            logger.error(f"Error getting stadium coordinates for {team_name}: {e}")
            return None

    def get_team_stats(self, team_name: str) -> dict[str, Any]:
        """
        Get team statistics for a team.

        Extracts performance metrics including goals, cards, corners,
        and other key statistics for match analysis.

        Note: FotMob API does not provide comprehensive team statistics.
        This function returns None values as FotMob doesn't expose this data.
        For team statistics, use the search providers (Tavily/Perplexity)
        which query footystats.org, soccerstats.com, or flashscore.com.

        Args:
            team_name: Name of team

        Returns:
            Dict with team statistics (all None values from FotMob)
        """
        try:
            # Get team details which may include stats
            # Use the wrapper function that converts team_name to team_id
            team_details = self.get_team_details_by_name(team_name)

            if not team_details or team_details.get("error"):
                logger.debug(
                    f"FotMob team details not available for {team_name} - stats will be None"
                )
                return self._create_error_dict(
                    "FotMob does not provide team statistics",
                    data={
                        "team_name": team_name,
                        "goals_avg": None,
                        "cards_avg": None,
                        "corners_avg": None,
                        "shots_avg": None,
                        "possession_avg": None,
                        "source": "fotmob",
                        "note": "FotMob does not provide team statistics. Use search providers (Tavily/Perplexity) for stats from footystats.org, soccerstats.com, or flashscore.com",
                    },
                )

            # Extract statistics from team details
            # FotMob structure varies, try multiple paths
            stats = {}

            # Path 1: Direct stats field
            if "stats" in team_details:
                stats = team_details["stats"]

            # Path 2: Nested in teamData
            if not stats and "teamData" in team_details:
                team_data = team_details["teamData"]
                if isinstance(team_data, dict):
                    stats = team_data.get("stats")

            # Path 3: Nested in overview
            if not stats and "overview" in team_details:
                overview = team_details["overview"]
                if isinstance(overview, dict):
                    stats = overview.get("stats")

            # Path 4: Nested in statistics
            if not stats and "statistics" in team_details:
                stats = team_details["statistics"]

            # Extract key metrics - FotMob doesn't provide these, so they'll be None
            result = {
                "team_name": team_name,
                "goals_avg": stats.get("goals_avg") if stats else None,
                "cards_avg": stats.get("cards_avg") if stats else None,
                "corners_avg": stats.get("corners_avg") if stats else None,
                "shots_avg": stats.get("shots_avg") if stats else None,
                "possession_avg": stats.get("possession_avg") if stats else None,
                "error": None,
                "source": "fotmob",
                "note": "FotMob does not provide team statistics. Use search providers (Tavily/Perplexity) for stats from footystats.org, soccerstats.com, or flashscore.com",
            }

            logger.info(
                f"✅ Team stats for {team_name}: goals={result['goals_avg']}, cards={result['cards_avg']}"
            )
            return result

        except Exception as e:
            logger.error(f"Error getting team stats for {team_name}: {e}")
            return {
                "team_name": team_name,
                "goals_avg": None,
                "cards_avg": None,
                "corners_avg": None,
                "shots_avg": None,
                "possession_avg": None,
                "error": str(e),
                "source": "fotmob",
                "note": "FotMob does not provide team statistics. Use search providers (Tavily/Perplexity) for stats from footystats.org, soccerstats.com, or flashscore.com",
            }

    def get_tactical_insights(self, home_team: str, away_team: str) -> dict[str, Any]:
        """
        Get tactical insights for a match between two teams.

        Analyzes playing styles, formations, and tactical matchups
        to provide intelligence for match prediction.

        Args:
            home_team: Name of home team
            away_team: Name of away team

        Returns:
            Dict with tactical insights
        """
        try:
            # Get details for both teams
            home_details = self.get_team_details(home_team)
            away_details = self.get_team_details(away_team)

            if not home_details or home_details.get("error"):
                error_msg = f"Home team data unavailable: {home_details.get('error_msg') if home_details else 'Not found'}"
                return self._create_error_dict(
                    error_msg,
                    data={
                        "home_style": "Unknown",
                        "away_style": "Unknown",
                        "formation_matchup": "Unknown",
                        "tactical_advantage": "Unknown",
                    },
                )

            if not away_details or away_details.get("error"):
                error_msg = f"Away team data unavailable: {away_details.get('error_msg') if away_details else 'Not found'}"
                return self._create_error_dict(
                    error_msg,
                    data={
                        "home_style": "Unknown",
                        "away_style": "Unknown",
                        "formation_matchup": "Unknown",
                        "tactical_advantage": "Unknown",
                    },
                )

            # Extract tactical information
            # FotMob may provide formation, playing style, etc.
            home_stats = home_details.get("stats", {})
            away_stats = away_details.get("stats", {})

            # Analyze playing styles (estimated from stats)
            home_style = self._estimate_playing_style(home_stats)
            away_style = self._estimate_playing_style(away_stats)

            # Determine tactical advantage
            advantage = self._calculate_tactical_advantage(home_stats, away_stats)

            result = {
                "home_team": home_team,
                "away_team": away_team,
                "home_style": home_style,
                "away_style": away_style,
                "formation_matchup": "Unknown",  # Would need lineup data
                "tactical_advantage": advantage,
                "key_factors": self._get_tactical_key_factors(home_stats, away_stats),
                "error": None,
            }

            logger.info(f"✅ Tactical insights for {home_team} vs {away_team}: {advantage}")
            return result

        except Exception as e:
            logger.error(f"Error getting tactical insights for {home_team} vs {away_team}: {e}")
            return {
                "home_style": "Unknown",
                "away_style": "Unknown",
                "formation_matchup": "Unknown",
                "tactical_advantage": "Unknown",
                "error": str(e),
            }

    def _estimate_playing_style(self, stats: dict) -> str:
        """Estimate playing style from team statistics."""
        if not stats:
            return "Unknown"

        goals_avg = stats.get("goals_avg", 0)
        shots_avg = stats.get("shots_avg", 0)
        possession_avg = stats.get("possession_avg", 50)

        # Estimate style based on metrics
        if goals_avg > 2.0 and shots_avg > 15:
            return "Attacking"
        elif goals_avg < 1.0 and possession_avg > 55:
            return "Possession-based"
        elif shots_avg > 12:
            return "Balanced"
        else:
            return "Defensive"

    def _calculate_tactical_advantage(self, home_stats: dict, away_stats: dict) -> str:
        """Calculate tactical advantage based on team statistics."""
        home_goals = home_stats.get("goals_avg", 0) or 0
        away_goals = away_stats.get("goals_avg", 0) or 0

        if home_goals > away_goals * 1.3:
            return "Home team advantage"
        elif away_goals > home_goals * 1.3:
            return "Away team advantage"
        else:
            return "Balanced"

    def _get_tactical_key_factors(self, home_stats: dict, away_stats: dict) -> list[str]:
        """Get key tactical factors for analysis."""
        factors = []

        home_goals = home_stats.get("goals_avg", 0) or 0
        away_goals = away_stats.get("goals_avg", 0) or 0

        if abs(home_goals - away_goals) > 0.5:
            factors.append(f"Goal difference: {abs(home_goals - away_goals):.1f}")

        home_cards = home_stats.get("cards_avg", 0) or 0
        away_cards = away_stats.get("cards_avg", 0) or 0

        if home_cards > 3.0:
            factors.append(f"Home team aggressive ({home_cards:.1f} cards/game)")
        if away_cards > 3.0:
            factors.append(f"Away team aggressive ({away_cards:.1f} cards/game)")

        return factors

    def check_player_status(
        self, player_name: str, team_name: str = None, team_id: int = None, season: int = 2024
    ) -> dict:
        """
        Check if a player is a key player by querying API-Football.

        This method provides player intelligence for news enrichment by checking
        player statistics and determining if they are key players.

        NEW APPROACH (V2): Uses team+season with local name matching
        instead of search parameter which doesn't work reliably.

        Args:
            player_name: Full name of the player
            team_name: Name of the team (deprecated, for backward compatibility)
            team_id: API-Football team ID (preferred parameter)
            season: Season year (default: 2024)

        Returns:
            Dict with keys: 'found', 'is_key', 'stats', 'player_name', 'role'
            - found: True if player found, False otherwise
            - is_key: True if player is a key player, False otherwise
            - stats: String with player statistics summary
            - player_name: Full name of the player
            - role: Player role (Key Player, Regular Starter, Rotation Player, Reserve)
        """
        try:
            # Lazy import to avoid circular dependencies
            from src.analysis.player_intel import check_player_status as _check_player_status

            # NEW APPROACH: Use team_id if provided, otherwise fallback to old behavior
            if team_id is not None:
                # New approach: team+season with local matching
                result = _check_player_status(player_name, team_id, season)
            else:
                # Fallback: Try to get team_id from team_name (backward compatibility)
                # This will fail with the new implementation, so we need team_id
                logger.warning(
                    f"check_player_status called with team_name='{team_name}' but no team_id. "
                    f"New approach requires team_id. Player '{player_name}' will not be found."
                )
                return {
                    "found": False,
                    "is_key": False,
                    "stats": "Team ID required (new approach)",
                    "player_name": player_name,
                    "role": "Unknown",
                }

            # Adapt the return structure to match what calling code expects
            if result is None:
                # Player not found or API error
                return {
                    "found": False,
                    "is_key": False,
                    "stats": "Not found or API error",
                    "player_name": player_name,
                    "role": "Unknown",
                }

            # Player found - adapt the structure
            return {
                "found": True,
                "is_key": result.get("is_key", False),
                "stats": result.get("stats_summary", "No stats available"),
                "player_name": result.get("player_name", player_name),
                "role": result.get("role", "Unknown"),
            }

        except Exception as e:
            logger.error(f"Error checking player status for {player_name}: {e}")
            return {
                "found": False,
                "is_key": False,
                "stats": f"Error: {str(e)}",
                "player_name": player_name,
                "role": "Unknown",
            }


# Singleton instance
_provider_instance = None
_provider_lock = threading.Lock()


def get_data_provider() -> FotMobProvider:
    """
    Get singleton instance of FotMobProvider (thread-safe).

    V6.3: Thread-safe with double-check locking pattern.
    This is critical because FotMobProvider may be accessed from multiple threads:
    - Main thread (pipeline principale)
    - BrowserMonitorThread (monitoraggio web)
    - Parallel enrichment threads

    Returns:
        FotMobProvider instance
    """
    global _provider_instance
    if _provider_instance is None:
        with _provider_lock:
            if _provider_instance is None:  # Double-check
                _provider_instance = FotMobProvider()
    return _provider_instance


def log_fotmob_cache_metrics():
    """
    V2.0: Log FotMob SWR cache metrics.

    This function logs detailed metrics about cache performance,
    hit rates, and background refresh statistics.
    """
    try:
        from src.utils.smart_cache import get_all_cache_stats, log_cache_stats

        logger.info("📊 FotMob SWR Cache Metrics:")
        log_cache_stats()
    except ImportError:
        logger.warning("⚠️ Smart cache module not available - cannot log metrics")
