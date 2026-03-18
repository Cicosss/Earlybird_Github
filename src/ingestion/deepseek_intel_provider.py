"""
EarlyBird DeepSeek Intel Provider - OpenRouter API (V10.0)

Drop-in replacement for GeminiAgentProvider using DeepSeek via OpenRouter.
Uses TwitterIntelCache for Twitter extraction (Twitter blocks search engine indexing).

Flow:
1. TwitterIntelCache for Twitter/X tweets (Twitter blocks site:twitter.com since mid-2023)
2. DDG Search (primary) or Brave Search (fallback) for real-time web results
3. DeepSeek via OpenRouter for AI analysis

V10.0: Replaced broken search engine Twitter queries with TwitterIntelCache.
       Twitter/X blocks search engine indexing (site:twitter.com returns 0 results).
V6.4: Fixed double URL encoding bug - HTTPX automatically encodes query parameters.
       Do NOT manually encode to avoid double encoding (causes HTTP 422).
V6.1: DDG as primary search to reduce Brave API quota consumption
       Brave quota reserved for news_hunter which needs higher quality results
V1.0: Initial implementation with same interface as GeminiAgentProvider

Requirements:
- OPENROUTER_API_KEY environment variable
- TwitterIntelCache for Twitter/X extraction (V10.0)
- DDG library (ddgs) for primary search
- Brave Search API (via BraveSearchProvider) as fallback
"""

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from config.settings import DEEPSEEK_CACHE_TTL_SECONDS
from src.ingestion.brave_provider import get_brave_provider
from src.ingestion.prompts import (
    build_betting_stats_prompt,
    build_biscotto_confirmation_prompt,
    build_deep_dive_prompt,
    build_match_context_enrichment_prompt,
    build_news_verification_prompt,
)
from src.ingestion.search_provider import get_search_provider
from src.prompts.system_prompts import (
    BETTING_STATS_SYSTEM_PROMPT,
    DEEP_DIVE_SYSTEM_PROMPT,
)
from src.schemas.perplexity_schemas import DeepDiveResponse
from src.utils.ai_parser import normalize_deep_dive_response, parse_ai_json
from src.utils.http_client import get_http_client
from src.utils.validators import safe_get, safe_list_get

# V6.0: CooldownManager import removed - OpenRouter/DeepSeek has high rate limits
# and should not share cooldown state with Gemini Direct API

logger = logging.getLogger(__name__)

# V10.0: Import TwitterIntelCache to replace broken search engine queries
try:
    from src.services.twitter_intel_cache import get_twitter_intel_cache

    _TWITTER_INTEL_CACHE_AVAILABLE = True
    logger.info("✅ TwitterIntelCache available for DeepSeek Twitter extraction")
except ImportError as e:
    _TWITTER_INTEL_CACHE_AVAILABLE = False
    logger.warning(f"⚠️ TwitterIntelCache not available: {e}")

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Dual-Model Configuration (V6.2)
# Model A: Standard model for translation, metadata extraction, low-priority tasks
MODEL_A_STANDARD = "deepseek/deepseek-chat"  # DeepSeek V3 Stable via OpenRouter

# Model B: Reasoner model for triangulation, verification, final verdict
MODEL_B_REASONER = "deepseek/deepseek-r1-0528:free"  # DeepSeek R1 Reasoner via OpenRouter

# Legacy model for backward compatibility (defaults to Model A)
DEEPSEEK_MODEL = os.getenv("OPENROUTER_MODEL", MODEL_A_STANDARD)

# Rate limiting configuration
DEEPSEEK_MIN_INTERVAL = 2.0  # Minimum seconds between requests (Requirements 4.2)


@dataclass
class DeepSeekCacheEntry:
    """Cache entry for DeepSeek responses with TTL and LRU tracking."""

    response: str
    cached_at: datetime
    ttl_seconds: int = DEEPSEEK_CACHE_TTL_SECONDS
    last_accessed: datetime = None

    def __post_init__(self):
        """Initialize last_accessed if not provided."""
        if self.last_accessed is None:
            self.last_accessed = datetime.now(timezone.utc)

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        elapsed = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self):
        """Update last_accessed timestamp for LRU tracking."""
        self.last_accessed = datetime.now(timezone.utc)


class DeepSeekIntelProvider:
    """
    Provider AI che usa DeepSeek via OpenRouter + Brave Search.
    Drop-in replacement per GeminiAgentProvider.

    Requirements: 1.1, 1.2, 1.3, 1.4, 2.1-2.8

    V6.3: Added system prompts for JSON output consistency.
    Matches PerplexityProvider and analyzer.py architecture to fix
    JSON extraction failures.
    """

    def __init__(self):
        """
        Inizializza con OPENROUTER_API_KEY e BraveSearchProvider.

        V6.2: Dual-Model Support
        - Model A (Standard): For translation, metadata extraction, low-priority tasks
        - Model B (Reasoner): For triangulation, verification, final verdict

        Requirements: 1.1, 1.2
        """
        self._api_key = OPENROUTER_API_KEY
        self._enabled = False
        self._last_request_time = 0.0  # For rate limiting
        self._brave_provider = None
        self._http_client = None  # Centralized HTTP client

        # V6.2: Dual-Model Configuration
        self._model_a = MODEL_A_STANDARD
        self._model_b = MODEL_B_REASONER

        # V6.2: Cost tracking for both models
        self._model_a_calls = 0
        self._model_b_calls = 0

        # V12.6: Response caching to reduce API costs
        self._cache: dict[str, DeepSeekCacheEntry] = {}
        self._cache_lock = threading.Lock()  # Thread-safe cache access
        self._cache_hits = 0
        self._cache_misses = 0

        if not self._api_key:
            logger.warning("⚠️ DeepSeek Intel Provider disabled: OPENROUTER_API_KEY not set")
            return

        try:
            self._brave_provider = get_brave_provider()
            self._search_provider = get_search_provider()  # V6.1: DDG primary for DeepSeek
            self._http_client = get_http_client()  # Use centralized HTTP client
            self._enabled = True
            logger.info("🤖 DeepSeek Intel Provider initialized (OpenRouter + DDG/Brave Search)")
            logger.info(f"   Model A (Standard): {self._model_a}")
            logger.info(f"   Model B (Reasoner): {self._model_b}")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek Intel Provider init failed: {e}")

    def is_available(self) -> bool:
        """
        Check if DeepSeek Intel Provider is available.

        Returns True only if:
        - API key is configured

        V6.0: CooldownManager check REMOVED - OpenRouter has high rate limits
        and should not be blocked by Gemini's cooldown state.

        Requirements: 1.4
        """
        if not self._enabled or not self._api_key:
            return False

        # V6.0: CooldownManager check removed
        # OpenRouter/DeepSeek has much higher rate limits than Gemini Direct API
        # and should not share cooldown state with Gemini

        return True

    def is_available_ignore_cooldown(self) -> bool:
        """
        Check if provider is configured (ignores cooldown state).

        Useful for checking if provider can be used once cooldown ends.
        """
        return self._enabled and bool(self._api_key)

    # ============================================
    # CACHE METHODS (V12.6)
    # ============================================

    def _generate_cache_key(self, model: str, messages: list) -> str:
        """
        Generate a unique cache key for a request.

        Args:
            model: Model ID being called
            messages: List of message dicts

        Returns:
            SHA256 hash as cache key
        """
        # Create a deterministic string representation
        key_data = f"{model}:{json.dumps(messages, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> str | None:
        """
        Retrieve response from cache if available and not expired.
        Updates last_accessed timestamp for LRU tracking.

        Args:
            cache_key: Cache key to look up

        Returns:
            Cached response or None if not found/expired
        """
        with self._cache_lock:
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                if not entry.is_expired():
                    # Update last_accessed for LRU tracking
                    entry.touch()
                    self._cache_hits += 1
                    logger.debug(f"💾 [DEEPSEEK] Cache hit for {cache_key[:16]}...")
                    return entry.response
                else:
                    # Clean up expired entry
                    del self._cache[cache_key]
                    logger.debug(f"🗑️  [DEEPSEEK] Cache expired for {cache_key[:16]}...")
        self._cache_misses += 1
        return None

    def _store_in_cache(self, cache_key: str, response: str) -> None:
        """
        Store response in cache.

        Args:
            cache_key: Cache key to store under
            response: Response to cache
        """
        with self._cache_lock:
            self._cache[cache_key] = DeepSeekCacheEntry(
                response=response,
                cached_at=datetime.now(timezone.utc),
            )

            # Cleanup old entries (keep cache size reasonable)
            if len(self._cache) > 1000:
                self._cleanup_cache()

    def _cleanup_cache(self) -> None:
        """
        Remove expired and oldest cache entries to enforce size limit.
        Uses hybrid approach: removes expired entries first, then LRU eviction.
        """
        with self._cache_lock:
            # First, remove expired entries
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"🧹 [DEEPSEEK] Cleaned up {len(expired_keys)} expired cache entries")

            # If still over limit, remove oldest entries (by last_accessed) - LRU eviction
            if len(self._cache) > 1000:
                sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].last_accessed)
                num_to_remove = len(self._cache) - 1000
                for i in range(num_to_remove):
                    key, _ = sorted_entries[i]
                    del self._cache[key]
                logger.debug(f"🧹 [DEEPSEEK] LRU eviction: removed {num_to_remove} oldest entries")

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics for monitoring.

        Returns:
            Dict with cache stats
        """
        with self._cache_lock:
            total_requests = self._cache_hits + self._cache_misses
            hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0
            return {
                "cache_size": len(self._cache),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "hit_rate_percent": round(hit_rate, 2),
            }

    # ============================================
    # INTERNAL METHODS
    # ============================================

    def _wait_for_rate_limit(self):
        """
        Enforce rate limiting between DeepSeek API calls.

        Waits until DEEPSEEK_MIN_INTERVAL has passed since last request.

        Requirements: 4.2
        """
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < DEEPSEEK_MIN_INTERVAL:
            wait_time = DEEPSEEK_MIN_INTERVAL - elapsed
            logger.debug(f"⏳ [DEEPSEEK] Rate limit: waiting {wait_time:.1f}s")
            time.sleep(wait_time)

        self._last_request_time = time.time()

    def _search_brave(self, query: str, limit: int = 5) -> list[dict]:
        """
        Esegue ricerca web e ritorna risultati.

        V6.1: Usa DDG come primary per risparmiare quota Brave.
        Brave viene usato solo come fallback se DDG fallisce.

        Gestisce errori gracefully (return empty list on failure).

        V6.4: Fixed double URL encoding bug - HTTPX automatically encodes query parameters.
        Do NOT manually encode to avoid double encoding (causes HTTP 422).

        Requirements: 3.1, 3.3, 3.4

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of dicts with title, url, snippet
        """
        # V6.1: Try SearchProvider first (DDG primary, then Brave fallback)
        # This saves Brave quota for news_hunter which needs higher quality results
        if hasattr(self, "_search_provider") and self._search_provider:
            try:
                logger.debug(f"🔍 [DEEPSEEK] DDG search: {query[:60]}...")
                results = self._search_provider.search(query, limit)
                if results:
                    logger.debug(f"🔍 [DEEPSEEK] DDG returned {len(results)} results")
                    return results
            except Exception as e:
                logger.debug(f"[DEEPSEEK] SearchProvider failed: {e}")

        # Fallback to direct Brave if SearchProvider unavailable or failed
        if not self._brave_provider:
            logger.debug("[DEEPSEEK] Brave provider not available")
            return []

        try:
            logger.debug(f"🔍 [DEEPSEEK] Brave fallback: {query[:60]}...")
            results = self._brave_provider.search_news(query, limit=limit)
            logger.debug(f"🔍 [DEEPSEEK] Brave returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Brave search error: {e}")
            return []

    def _format_brave_results(self, results: list[dict]) -> str:
        """
        Formatta risultati Brave per inclusione nel prompt.

        Include title, URL, snippet per ogni risultato.

        Requirements: 3.2, 3.5

        Args:
            results: List of Brave search results

        Returns:
            Formatted string for prompt injection
        """
        if not results:
            return ""

        parts = ["[WEB SEARCH RESULTS]"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            snippet = result.get("snippet", result.get("summary", ""))

            parts.append(f"{i}. Title: {title}")
            if url:
                parts.append(f"   URL: {url}")
            if snippet:
                parts.append(f"   Summary: {snippet}")
            parts.append("")  # Empty line between results

        return "\n".join(parts)

    def _build_prompt_with_context(self, base_prompt: str, brave_results: str) -> str:
        """
        Costruisce prompt finale con contesto Brave.

        Rimuove riferimenti a Google Search e aggiunge istruzioni per DeepSeek.

        Requirements: 5.1, 5.2, 5.3, 5.4

        Args:
            base_prompt: Original prompt from prompts.py
            brave_results: Formatted Brave search results

        Returns:
            Final prompt for DeepSeek
        """
        # Remove Google Search references (Requirements 5.1)
        cleaned_prompt = base_prompt.replace("Google Search", "web search")
        cleaned_prompt = cleaned_prompt.replace("google search", "web search")
        cleaned_prompt = cleaned_prompt.replace("search grounding", "provided sources")
        cleaned_prompt = cleaned_prompt.replace("Search Grounding", "provided sources")

        if brave_results:
            # Add Brave results and instruction (Requirements 5.2, 5.3)
            context_section = f"""
{brave_results}

IMPORTANT: Analyze the information from the web search results above. 
Base your analysis on these sources and your training knowledge.
"""
            return f"{context_section}\n\n{cleaned_prompt}"
        else:
            # No web results - use training knowledge only (Requirements 5.4)
            no_results_instruction = """
NOTE: No recent web search results available. 
Base your analysis on your training knowledge only.
Be conservative in your assessments when lacking current data.

"""
            return f"{no_results_instruction}{cleaned_prompt}"

    def _call_deepseek(self, prompt: str, operation_name: str, task_type: str = None) -> str | None:
        """
        Chiama DeepSeek via OpenRouter con rate limiting.

        V6.0: CooldownManager NON usato - OpenRouter ha rate limit alti.
        Su 429 ritorna None ma NON attiva cooldown globale.

        V6.2: Uses Model A (Standard) by default for backward compatibility.

        V6.3: Added system prompts for JSON output consistency.
        Matches PerplexityProvider and analyzer.py architecture.

        Requirements: 4.2, 7.2

        Args:
            prompt: The prompt to send to DeepSeek
            operation_name: Name for logging
            task_type: Type of task ("deep_dive", "betting_stats", etc.)

        Returns:
            Raw response text or None on failure
        """
        # V6.3: Select system prompt based on task type
        system_prompt = None
        if task_type == "deep_dive":
            system_prompt = DEEP_DIVE_SYSTEM_PROMPT
        elif task_type == "betting_stats":
            system_prompt = BETTING_STATS_SYSTEM_PROMPT

        # V6.2: Use Model A for backward compatibility
        # Build messages with system prompt if available
        if system_prompt:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [{"role": "user", "content": prompt}]

        return self._call_model(self._model_a, messages, operation_name=operation_name)

    # ============================================
    # DUAL-MODEL METHODS (V6.2)
    # ============================================

    def call_standard_model(self, messages: list, **kwargs) -> str:
        """
        Call Model A (Standard) for standard tasks.

        Use for:
        - Translation tasks
        - Metadata extraction
        - Basic classification
        - Low-priority analysis
        - Initial filtering

        Args:
            messages: List of message dicts (role, content)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response content or None on failure
        """
        return self._call_model(self._model_a, messages, **kwargs)

    def call_reasoner_model(self, messages: list, **kwargs) -> str:
        """
        Call Model B (Reasoner) for reasoning tasks.

        Use for:
        - Triangulation
        - VerificationLayer
        - Final BET/NO BET verdict
        - Cross-source conflict resolution
        - High-confidence decisions

        Args:
            messages: List of message dicts (role, content)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response content or None on failure

        Note:
            Model B failures should fall back to Model A with a warning.
        """
        try:
            result = self._call_model(self._model_b, messages, **kwargs)
            if result:
                self._model_b_calls += 1
                return result
            else:
                # Model B failed - fall back to Model A with warning
                logger.warning("⚠️ [DEEPSEEK] Model B failed, falling back to Model A")
                result = self._call_model(self._model_a, messages, **kwargs)
                if result:
                    self._model_a_calls += 1
                return result
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Model B exception, falling back to Model A: {e}")
            result = self._call_model(self._model_a, messages, **kwargs)
            if result:
                self._model_a_calls += 1
            return result

    def _call_model(self, model: str, messages: list, **kwargs) -> str | None:
        """
        Internal method to call specified model via OpenRouter.

        V6.2: Parameterized by model to support dual-model operation.

        Args:
            model: Model ID to call (Model A or Model B)
            messages: List of message dicts (role, content)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Raw response text or None on failure
        """
        # V6.0: CooldownManager check removed
        # OpenRouter/DeepSeek has much higher rate limits than Gemini Direct API

        # V12.6: Check cache first
        cache_key = self._generate_cache_key(model, messages)
        cached_response = self._get_from_cache(cache_key)
        if cached_response is not None:
            return cached_response

        # Rate limiting (local, not shared)
        self._wait_for_rate_limit()

        # Determine operation name for logging
        operation_name = kwargs.get("operation_name", f"call_{model.split('/')[-1]}")

        # Log which model is being used
        if model == self._model_a:
            logger.info(f"🧠 [DEEPSEEK] Using Model A (Standard) for: {operation_name}")
        elif model == self._model_b:
            logger.info(f"🧠 [DEEPSEEK] Using Model B (Reasoner) for: {operation_name}")
        else:
            logger.info(f"🧠 [DEEPSEEK] Using model {model} for: {operation_name}")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.betting",  # Required by OpenRouter
            "X-Title": "EarlyBird Betting Intelligence",
        }

        # Build payload with model and messages
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get(
                "temperature", 0.3
            ),  # Lower temperature for more consistent analysis
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        # Add include_reasoning for Model B if requested
        if model == self._model_b and kwargs.get("include_reasoning", False):
            payload["include_reasoning"] = True

        try:
            # Use centralized HTTP client instead of creating new client
            if not self._http_client:
                logger.error("❌ [DEEPSEEK] HTTP client not initialized")
                return None

            response = self._http_client.post_sync(
                OPENROUTER_API_URL,
                rate_limit_key="openrouter",
                headers=headers,
                json=payload,
                timeout=kwargs.get("timeout", 60),
                max_retries=kwargs.get("max_retries", 2),
            )

            # Handle 429 rate limit
            # V6.0: Log warning but do NOT activate global cooldown
            # OpenRouter 429s are transient and should not block the system
            if response.status_code == 429:
                error_msg = f"OpenRouter 429: {response.text}"
                logger.warning(f"⚠️ [DEEPSEEK] Rate limit hit (transient): {error_msg}")
                # Return None to trigger Perplexity fallback via IntelligenceRouter
                return None

            # Handle other errors
            if response.status_code != 200:
                logger.error(
                    f"❌ [DEEPSEEK] API error: HTTP {response.status_code} - {response.text}"
                )
                return None

            data = response.json()

            # Extract response text
            choices = data.get("choices", [])
            if not choices:
                logger.warning(f"⚠️ [DEEPSEEK] Empty response for {operation_name}")
                return None

            # V7.0: Safe array access with bounds checking
            first_choice = safe_list_get(choices, 0)
            if not first_choice:
                logger.warning(f"⚠️ [DEEPSEEK] No choices in response for {operation_name}")
                return None

            # V7.0: Safe nested dictionary access with type checking
            content = safe_get(first_choice, "message", "content", default="")
            if not content:
                logger.warning(f"⚠️ [DEEPSEEK] No content in response for {operation_name}")
                return None

            # V6.0: CooldownManager.record_successful_call() removed
            # OpenRouter/DeepSeek doesn't use shared cooldown state

            # V6.3: Debug logging for response content (first 500 chars)
            logger.debug(f"🔍 [DEEPSEEK] Response preview: {content[:500] if content else 'EMPTY'}")

            logger.info(f"✅ [DEEPSEEK] {operation_name} complete")

            # V12.6: Store response in cache
            self._store_in_cache(cache_key, content)

            return content

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Error in {operation_name}: {e}")
            return None

    def get_model_usage_stats(self) -> dict:
        """
        Get usage statistics for both models.

        Returns:
            Dict with model_a_calls and model_b_calls
        """
        return {
            "model_a_calls": self._model_a_calls,
            "model_b_calls": self._model_b_calls,
            "total_calls": self._model_a_calls + self._model_b_calls,
        }

    # ============================================
    # NORMALIZATION HELPERS
    # ============================================

    def _normalize_verification_result(self, data: dict) -> dict:
        """Normalize news verification response with safe defaults."""

        def safe_bool(val, default=False):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "yes", "si", "1", "confirmed")
            return default

        def safe_str(val, default="Unknown"):
            if val is None or val == "":
                return default
            return str(val)

        def safe_list(val, default=None):
            if default is None:
                default = []
            if val is None:
                return default
            if isinstance(val, list):
                return [str(v) for v in val if v]
            if isinstance(val, str):
                return [val]
            return default

        return {
            "verified": safe_bool(data.get("verified")),
            "verification_status": safe_str(data.get("verification_status"), "UNVERIFIED"),
            "confidence_level": safe_str(data.get("confidence_level"), "LOW"),
            "verification_sources": safe_list(data.get("verification_sources")),
            "additional_context": safe_str(data.get("additional_context"), ""),
            "betting_impact": safe_str(data.get("betting_impact"), "Unknown"),
            "is_current": safe_bool(data.get("is_current"), True),
            "notes": safe_str(data.get("notes"), ""),
        }

    def _normalize_biscotto_confirmation(self, data: dict) -> dict:
        """Normalize biscotto confirmation response with safe defaults."""

        def safe_bool(val, default=False):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "yes", "si", "1", "confirmed")
            return default

        def safe_int(val, default=0, min_val=0, max_val=30):
            if val is None:
                return default
            try:
                result = int(val)
                return max(min_val, min(max_val, result))
            except (ValueError, TypeError):
                return default

        def safe_str(val, default="Unknown"):
            if val is None or val == "":
                return default
            return str(val)

        return {
            "biscotto_confirmed": safe_bool(data.get("biscotto_confirmed")),
            "confidence_boost": safe_int(data.get("confidence_boost"), 0, 0, 30),
            "home_team_objective": safe_str(data.get("home_team_objective")),
            "away_team_objective": safe_str(data.get("away_team_objective")),
            "mutual_benefit_found": safe_bool(data.get("mutual_benefit_found")),
            "mutual_benefit_reason": safe_str(
                data.get("mutual_benefit_reason"), "No clear mutual benefit"
            ),
            "h2h_pattern": safe_str(data.get("h2h_pattern"), "No data"),
            "club_relationship": safe_str(data.get("club_relationship"), "None found"),
            "manager_hints": safe_str(data.get("manager_hints"), "None found"),
            "market_sentiment": safe_str(data.get("market_sentiment"), "Unknown"),
            "additional_context": safe_str(data.get("additional_context"), ""),
            "final_recommendation": safe_str(data.get("final_recommendation"), "MONITOR LIVE"),
        }

    def _normalize_match_enrichment(self, data: dict) -> dict:
        """Normalize match enrichment response with safe defaults."""

        def safe_str(val, default="Unknown"):
            if val is None or val == "":
                return default
            return str(val)

        return {
            "home_form": safe_str(data.get("home_form")),
            "home_form_trend": safe_str(data.get("home_form_trend")),
            "away_form": safe_str(data.get("away_form")),
            "away_form_trend": safe_str(data.get("away_form_trend")),
            "home_recent_news": safe_str(data.get("home_recent_news")),
            "away_recent_news": safe_str(data.get("away_recent_news")),
            "h2h_recent": safe_str(data.get("h2h_recent")),
            "h2h_goals_pattern": safe_str(data.get("h2h_goals_pattern")),
            "match_importance": safe_str(data.get("match_importance")),
            "home_motivation": safe_str(data.get("home_motivation")),
            "away_motivation": safe_str(data.get("away_motivation")),
            "weather_forecast": safe_str(data.get("weather_forecast")),
            "weather_impact": safe_str(data.get("weather_impact")),
            "additional_context": safe_str(data.get("additional_context"), ""),
            "data_freshness": safe_str(data.get("data_freshness"), "Unknown"),
        }

    def _normalize_betting_stats(self, data: dict) -> dict:
        """
        Normalize betting stats response using Pydantic validation.

        Uses BettingStatsResponse schema for type-safe validation and field name consistency.
        Replaces legacy field name mapping with schema-based validation.

        Args:
            data: Raw parsed JSON from DeepSeek API

        Returns:
            Validated dict with correct field names matching BettingStatsResponse schema
        """
        from src.schemas.perplexity_schemas import BettingStatsResponse

        if not data:
            return None

        try:
            # Validate with Pydantic schema
            validated = BettingStatsResponse(**data)
            return validated.model_dump()
        except Exception as e:
            logger.warning(f"[DEEPSEEK] Betting stats validation failed: {e}")
            return None

    # ============================================
    # PUBLIC API METHODS (Same interface as GeminiAgentProvider)
    # ============================================

    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: str = None,
        referee: str = None,
        missing_players: list = None,
    ) -> dict | None:
        """
        Get deep analysis for a match using DeepSeek + Brave Search.

        Requirements: 2.1, 7.1

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format (optional)
            referee: Referee name (optional)
            missing_players: List of player names reported missing (optional)

        Returns:
            Dict with analysis or None on failure
        """
        # Validate inputs (Requirements 7.1) - check for None, empty, or whitespace-only
        if not home_team or not home_team.strip() or not away_team or not away_team.strip():
            logger.debug("[DEEPSEEK] Deep dive skipped: missing team names")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        try:
            # Build search query
            search_query = f"{home_team} vs {away_team} match preview analysis"
            if match_date:
                search_query += f" {match_date}"

            # Search Brave for context
            brave_results = self._search_brave(search_query, limit=5)
            formatted_results = self._format_brave_results(brave_results)

            # Build prompt with context
            base_prompt = build_deep_dive_prompt(
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                referee=referee,
                missing_players=missing_players,
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)

            logger.info(f"🤖 [DEEPSEEK] Deep dive: {home_team} vs {away_team}")

            # Call DeepSeek with system prompt
            response_text = self._call_deepseek(final_prompt, "deep_dive", task_type="deep_dive")

            if not response_text:
                return None

            # Try Pydantic validation first for strict enum checking
            try:
                validated = DeepDiveResponse.model_validate_json(response_text)
                return validated.model_dump()
            except Exception as validation_error:
                logger.debug(f"[DEEPSEEK] Pydantic validation failed: {validation_error}")
                # Fallback to legacy parsing with normalization
                parsed = parse_ai_json(response_text, None)
                return normalize_deep_dive_response(parsed)

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Deep dive error: {e}")
            return None

    def get_betting_stats(
        self, home_team: str, away_team: str, match_date: str, league: str = None
    ) -> dict | None:
        """
        Get corner/cards statistics using DeepSeek + Brave Search.

        Requirements: 2.2, 7.1

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name for context

        Returns:
            Dict with betting stats or None on failure
        """
        # Validate inputs (Requirements 7.1) - check for None, empty, or whitespace-only
        if (
            not home_team
            or not home_team.strip()
            or not away_team
            or not away_team.strip()
            or not match_date
            or not match_date.strip()
        ):
            logger.debug("[DEEPSEEK] Betting stats skipped: missing required params")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        try:
            # Build search query
            search_query = f"{home_team} vs {away_team} corners cards statistics"
            if league:
                search_query += f" {league}"

            # Search Brave for context
            brave_results = self._search_brave(search_query, limit=5)
            formatted_results = self._format_brave_results(brave_results)

            # Build prompt with context
            base_prompt = build_betting_stats_prompt(
                home_team=home_team, away_team=away_team, match_date=match_date, league=league
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)

            logger.info(f"🎰 [DEEPSEEK] Betting stats: {home_team} vs {away_team}")

            # Call DeepSeek with system prompt
            response_text = self._call_deepseek(
                final_prompt, "betting_stats", task_type="betting_stats"
            )

            if not response_text:
                return None

            # Parse and normalize
            parsed = parse_ai_json(response_text, None)
            if parsed:
                return self._normalize_betting_stats(parsed)
            return None

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Betting stats error: {e}")
            return None

    def verify_news_item(
        self,
        news_title: str,
        news_snippet: str,
        team_name: str,
        news_source: str = "Unknown",
        match_context: str = "upcoming match",
    ) -> dict | None:
        """
        Verify a news item using DeepSeek + Brave Search.

        Requirements: 2.3, 7.1

        Args:
            news_title: Title of the news article
            news_snippet: Snippet/summary of the news
            team_name: Team the news is about
            news_source: Original source of the news
            match_context: Match context string

        Returns:
            Dict with verification result or None on failure
        """
        # Validate inputs (Requirements 7.1)
        if not news_title and not news_snippet:
            logger.debug("[DEEPSEEK] News verification skipped: no title or snippet")
            return None

        if not team_name:
            logger.debug("[DEEPSEEK] News verification skipped: no team name")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        try:
            # Build search query from news content
            search_text = news_title or news_snippet
            search_query = f"{team_name} {search_text[:100]}"

            # Search Brave for verification
            brave_results = self._search_brave(search_query, limit=5)
            formatted_results = self._format_brave_results(brave_results)

            # Build prompt with context
            base_prompt = build_news_verification_prompt(
                news_title=news_title or "",
                news_snippet=news_snippet or "",
                team_name=team_name,
                news_source=news_source,
                match_context=match_context,
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)

            logger.info(f"🔍 [DEEPSEEK] Verifying news: {(news_title or news_snippet)[:50]}...")

            # Call DeepSeek
            response_text = self._call_deepseek(final_prompt, "news_verification")

            if not response_text:
                return None

            # Parse and normalize
            parsed = parse_ai_json(response_text, None)
            if parsed:
                result = self._normalize_verification_result(parsed)
                logger.info(f"✅ [DEEPSEEK] Verification: {result.get('verification_status')}")
                return result
            return None

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] News verification error: {e}")
            return None

    def verify_news_batch(
        self,
        news_items: list[dict],
        team_name: str,
        match_context: str = "upcoming match",
        max_items: int = 5,
    ) -> list[dict]:
        """
        Verify multiple news items efficiently.

        Requirements: 2.4

        Args:
            news_items: List of news item dicts
            team_name: Team the news is about
            match_context: Match context string
            max_items: Maximum items to verify

        Returns:
            List of news items with added 'deepseek_verification' field
        """
        if not self.is_available():
            return news_items

        if not news_items:
            return []

        # Keywords that indicate news worth verifying
        CRITICAL_KEYWORDS = [
            "injury",
            "injured",
            "infortunio",
            "lesión",
            "lesão",
            "out",
            "ruled out",
            "miss",
            "absent",
            "assente",
            "baja",
            "suspended",
            "squalificato",
            "sancionado",
            "doubt",
            "doubtful",
            "dubbio",
            "crisis",
            "sacked",
            "fired",
            "esonerato",
        ]

        # Filter items that need verification
        items_to_verify = []
        for item in news_items:
            confidence = item.get("confidence", "LOW")

            # Skip HIGH/VERY_HIGH confidence
            if confidence in ["HIGH", "VERY_HIGH"]:
                continue

            # Check for critical keywords
            title = (item.get("title") or "").lower()
            snippet = (item.get("snippet") or "").lower()
            text = f"{title} {snippet}"

            if any(kw in text for kw in CRITICAL_KEYWORDS):
                items_to_verify.append(item)

        items_to_verify = items_to_verify[:max_items]

        if not items_to_verify:
            logger.debug("[DEEPSEEK] No news items need verification")
            return news_items

        logger.info(f"🔍 [DEEPSEEK] Verifying {len(items_to_verify)} news items...")

        verified_count = 0
        for item in items_to_verify:
            verification = self.verify_news_item(
                news_title=item.get("title", ""),
                news_snippet=item.get("snippet", ""),
                team_name=team_name,
                news_source=item.get("source", "Unknown"),
                match_context=match_context,
            )

            if verification:
                item["deepseek_verification"] = verification

                if (
                    verification.get("verified")
                    and verification.get("verification_status") == "CONFIRMED"
                ):
                    item["confidence"] = "HIGH"
                    item["confidence_boosted_by"] = "deepseek_verification"
                    verified_count += 1

                additional = verification.get("additional_context", "")
                if additional and additional != "Unknown" and len(additional) > 10:
                    item["snippet"] = f"{item.get('snippet', '')} [DEEPSEEK: {additional}]"

        if verified_count > 0:
            logger.info(
                f"✅ [DEEPSEEK] Verified {verified_count}/{len(items_to_verify)} news items"
            )

        return news_items

    def confirm_biscotto(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str,
        draw_odds: float,
        implied_prob: float,
        odds_pattern: str,
        season_context: str,
        detected_factors: list[str] = None,
    ) -> dict | None:
        """
        Confirm uncertain biscotto signal using DeepSeek + Brave Search.

        Requirements: 2.5, 7.1

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date
            league: League name
            draw_odds: Current draw odds
            implied_prob: Implied probability
            odds_pattern: Pattern detected
            season_context: End of season context
            detected_factors: Factors already detected

        Returns:
            Dict with confirmation result or None on failure
        """
        # Validate inputs (Requirements 7.1) - check for None, empty, or whitespace-only
        if not home_team or not home_team.strip() or not away_team or not away_team.strip():
            logger.debug("[DEEPSEEK] Biscotto confirmation skipped: missing team names")
            return None

        if draw_odds is None or draw_odds <= 1.0:
            logger.debug("[DEEPSEEK] Biscotto confirmation skipped: invalid draw odds")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        try:
            # Build search query
            search_query = f"{home_team} vs {away_team} {league} standings objectives"
            if match_date:
                search_query += f" {match_date}"

            # Search Brave for context
            brave_results = self._search_brave(search_query, limit=5)
            formatted_results = self._format_brave_results(brave_results)

            # Build prompt with context
            base_prompt = build_biscotto_confirmation_prompt(
                home_team=home_team,
                away_team=away_team,
                match_date=match_date or "upcoming",
                league=league or "Unknown",
                draw_odds=draw_odds,
                implied_prob=implied_prob or 0,
                odds_pattern=odds_pattern or "Unknown",
                season_context=season_context or "Unknown",
                detected_factors=detected_factors,
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)

            logger.info(f"🍪 [DEEPSEEK] Confirming biscotto: {home_team} vs {away_team}")

            # Call DeepSeek
            response_text = self._call_deepseek(final_prompt, "biscotto_confirmation")

            if not response_text:
                return None

            # Parse and normalize
            parsed = parse_ai_json(response_text, None)
            if parsed:
                result = self._normalize_biscotto_confirmation(parsed)
                logger.info(f"✅ [DEEPSEEK] Biscotto: confirmed={result.get('biscotto_confirmed')}")
                return result
            return None

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Biscotto confirmation error: {e}")
            return None

    def verify_final_alert(self, verification_prompt: str) -> dict | None:
        """
        Verify final alert using DeepSeek without web search.

        This method is designed for FinalAlertVerifier which provides
        a comprehensive verification prompt with all match data, analysis,
        and context. No web search is performed as all information
        is already included in the prompt.

        Args:
            verification_prompt: Complete verification prompt with match data,
                               analysis, reasoning, and context

        Returns:
            Dict with verification result or None on failure

        Requirements: 2.6
        """
        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available for final alert verification")
            return None

        # Validate input
        if not verification_prompt or not verification_prompt.strip():
            logger.debug("[DEEPSEEK] Final alert verification skipped: empty prompt")
            return None

        try:
            logger.info("🔍 [DEEPSEEK] Verifying final alert...")

            # Call DeepSeek with the verification prompt
            # Use Model B (Reasoner) for final verification as it requires careful analysis
            messages = [
                {
                    "role": "system",
                    "content": "You are a professional betting analyst and fact-checker with 10+ years of experience in sports betting and football analysis. Respond ONLY with valid JSON in the format specified in the user prompt. No markdown, no explanations.",
                },
                {"role": "user", "content": verification_prompt},
            ]

            response_text = self.call_reasoner_model(
                messages,
                temperature=0.1,
                max_tokens=2000,
                operation_name="final_alert_verification",
            )

            if not response_text:
                return None

            # Parse the JSON response
            parsed = parse_ai_json(response_text, None)
            if not parsed:
                logger.warning("[DEEPSEEK] Failed to parse final alert verification response")
                return None

            # Normalize the response to ensure all required fields are present
            result = self._normalize_final_alert_verification(parsed)
            status = result.get("verification_status", "UNKNOWN")
            should_send = result.get("should_send", False)

            logger.info(
                f"✅ [DEEPSEEK] Final alert verification: {status}, should_send={should_send}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Final alert verification error: {e}")
            return None

    def _normalize_final_alert_verification(self, data: dict) -> dict:
        """Normalize final alert verification response with safe defaults."""

        def safe_bool(val, default=False):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "yes", "si", "1", "confirmed")
            return default

        def safe_int(val, default=0, min_val=0, max_val=10):
            if val is None:
                return default
            try:
                result = int(val)
                return max(min_val, min(max_val, result))
            except (ValueError, TypeError):
                return default

        def safe_str(val, default="Unknown"):
            if val is None or val == "":
                return default
            return str(val)

        def safe_list(val, default=None):
            if default is None:
                default = []
            if val is None:
                return default
            if isinstance(val, list):
                return [str(v) for v in val if v]
            if isinstance(val, str):
                return [val]
            return default

        return {
            "verification_status": safe_str(data.get("verification_status"), "NEEDS_REVIEW"),
            "confidence_level": safe_str(data.get("confidence_level"), "LOW"),
            "should_send": safe_bool(data.get("should_send"), False),
            "logic_score": safe_int(data.get("logic_score"), 5, 0, 10),
            "data_accuracy_score": safe_int(data.get("data_accuracy_score"), 5, 0, 10),
            "reasoning_quality_score": safe_int(data.get("reasoning_quality_score"), 5, 0, 10),
            "market_validation": safe_str(data.get("market_validation"), "QUESTIONABLE"),
            "key_strengths": safe_list(data.get("key_strengths")),
            "key_weaknesses": safe_list(data.get("key_weaknesses")),
            "missing_information": safe_list(data.get("missing_information")),
            "rejection_reason": safe_str(data.get("rejection_reason"), ""),
            "final_recommendation": safe_str(data.get("final_recommendation"), "NO_BET"),
            "suggested_modifications": safe_str(data.get("suggested_modifications"), ""),
            "data_discrepancies": safe_list(data.get("data_discrepancies")),
            "discrepancy_impact": safe_str(data.get("discrepancy_impact"), "MINOR"),
            "adjusted_score_if_discrepancy": safe_int(
                data.get("adjusted_score_if_discrepancy"), 5, 0, 10
            ),
            "source_verification": {
                "source_confirmed": safe_bool(data.get("source_confirmed"), False),
                "cross_source_found": safe_bool(data.get("cross_source_found"), False),
                "source_bias_detected": safe_bool(data.get("source_bias_detected"), False),
                "source_reliability_adjusted": safe_str(
                    data.get("source_reliability_adjusted"), "LOW"
                ),
                "verification_issues": safe_list(data.get("verification_issues")),
            },
        }

    def enrich_match_context(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str,
        existing_context: str = "",
    ) -> dict | None:
        """
        Enrich match context using DeepSeek + Brave Search.

        Requirements: 2.6, 7.1

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date
            league: League name
            existing_context: Already gathered context

        Returns:
            Dict with enriched context or None on failure
        """
        # Validate inputs (Requirements 7.1) - check for None, empty, or whitespace-only
        if not home_team or not home_team.strip() or not away_team or not away_team.strip():
            logger.debug("[DEEPSEEK] Match enrichment skipped: missing team names")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        try:
            # Build search query
            search_query = f"{home_team} vs {away_team} news form injuries"
            if league:
                search_query += f" {league}"

            # Search Brave for context
            brave_results = self._search_brave(search_query, limit=5)
            formatted_results = self._format_brave_results(brave_results)

            # Build prompt with context
            base_prompt = build_match_context_enrichment_prompt(
                home_team=home_team,
                away_team=away_team,
                match_date=match_date or "upcoming",
                league=league or "Unknown",
                existing_context=existing_context or "",
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)

            logger.info(f"📊 [DEEPSEEK] Enriching context: {home_team} vs {away_team}")

            # Call DeepSeek
            response_text = self._call_deepseek(final_prompt, "match_enrichment")

            if not response_text:
                return None

            # Parse and normalize
            parsed = parse_ai_json(response_text, None)
            if parsed:
                result = self._normalize_match_enrichment(parsed)
                logger.info(
                    f"✅ [DEEPSEEK] Context enriched (freshness: {result.get('data_freshness')})"
                )
                return result
            return None

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Match enrichment error: {e}")
            return None

    def extract_twitter_intel(
        self, handles: list[str], max_posts_per_account: int = 5
    ) -> dict | None:
        """
        Extract recent tweets using TwitterIntelCache (V10.0).

        Twitter/X blocks search engine indexing (site:twitter.com returns 0 results
        since mid-2023). This method now uses cached tweets from verified
        accounts instead of search engines.

        V10.0: Replaced broken search engine queries with TwitterIntelCache.

        Requirements: 2.7, 7.1

        Args:
            handles: List of Twitter handles (with @)
            max_posts_per_account: Max posts per account

        Returns:
            Dict with extracted tweets or None on failure
        """
        # Validate inputs (Requirements 7.1)
        if not handles:
            logger.debug("[DEEPSEEK] Twitter extraction skipped: no handles")
            return None

        # Filter out invalid handles
        valid_handles = [h for h in handles if h and isinstance(h, str) and h.strip()]

        if not valid_handles:
            logger.debug("[DEEPSEEK] Twitter extraction skipped: no valid handles after filtering")
            return None

        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None

        # V10.0: Use TwitterIntelCache instead of search engines
        if not _TWITTER_INTEL_CACHE_AVAILABLE:
            logger.warning("⚠️ [DEEPSEEK] TwitterIntelCache not available, cannot extract tweets")
            return None

        try:
            logger.info(
                f"🐦 [DEEPSEEK] Extracting tweets from {len(valid_handles)} accounts via TwitterIntelCache..."
            )

            # Get cache instance
            cache = get_twitter_intel_cache()

            # Check if cache is fresh (populated this cycle)
            if not cache.is_fresh:
                logger.debug(
                    f"🐦 [DEEPSEEK] Twitter Intel cache not fresh ({cache.cache_age_minutes}m old), skipping"
                )
                return None

            # Topics filter for football-relevant tweets
            topics_filter = [
                "injury",
                "lineup",
                "squad",
                "out",
                "doubt",
                "miss",
                "absent",
                "transfer",
                "breaking",
                "preview",
            ]

            # Collect all relevant tweets from cache
            all_accounts = []
            for handle in valid_handles:
                # Search cache for this handle
                handle_clean = handle.replace("@", "")
                relevant_tweets = cache.search_intel(
                    query=handle_clean,
                    league_key=None,  # Search all cached accounts
                    topics=topics_filter,
                )

                if relevant_tweets:
                    # Limit to max_posts_per_account
                    tweets = relevant_tweets[:max_posts_per_account]

                    # Format posts to match expected structure
                    posts = []
                    for tweet in tweets:
                        posts.append(
                            {
                                "date": tweet.date or "",
                                "content": tweet.content,
                                "topics": tweet.topics if tweet.topics else [],
                            }
                        )

                    all_accounts.append(
                        {
                            "handle": handle,
                            "posts": posts,
                        }
                    )

            # Build final result
            if not all_accounts:
                logger.warning(
                    f"🐦 [DEEPSEEK] No cached Twitter intel found for {len(valid_handles)} handles"
                )
                return None

            result = {
                "accounts": all_accounts,
                "extraction_time": datetime.now(timezone.utc).isoformat(),
                # V10.0: Add metadata for debugging
                "_meta": {
                    "total_handles_requested": len(valid_handles),
                    "accounts_returned": len(all_accounts),
                    "source": "twitter_intel_cache",
                    "is_complete": len(all_accounts)
                    >= len(valid_handles) * 0.5,  # At least 50% coverage
                },
            }

            accounts_with_posts = sum(1 for a in all_accounts if a.get("posts"))
            total_posts = sum(len(a.get("posts", [])) for a in all_accounts)

            logger.info(
                f"✅ [DEEPSEEK] Twitter: {accounts_with_posts}/{len(all_accounts)} accounts with posts, "
                f"{total_posts} total posts (source: TwitterIntelCache)"
            )

            return result

        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Twitter extraction error: {e}")
            return None

    # ============================================
    # FORMATTING METHODS (Same as GeminiAgentProvider)
    # ============================================

    def format_for_prompt(self, deep_dive: dict) -> str:
        """
        Format deep dive results for injection into AI prompt.

        Requirements: 2.8

        Args:
            deep_dive: Result from get_match_deep_dive

        Returns:
            Formatted string for prompt injection
        """
        if not deep_dive:
            return ""

        parts = ["[DEEPSEEK INTELLIGENCE]"]

        # Helper function for case-insensitive "Unknown" check
        def is_unknown(value: str) -> bool:
            """Check if value is 'Unknown' (case-insensitive)."""
            if not value or not isinstance(value, str):
                return True
            return value.lower().startswith("unknown")

        if deep_dive.get("internal_crisis") and not is_unknown(deep_dive.get("internal_crisis")):
            parts.append(f"⚠️ INTERNAL CRISIS: {deep_dive['internal_crisis']}")

        if deep_dive.get("turnover_risk") and not is_unknown(deep_dive.get("turnover_risk")):
            parts.append(f"🔄 TURNOVER RISK: {deep_dive['turnover_risk']}")

        if deep_dive.get("referee_intel") and not is_unknown(deep_dive.get("referee_intel")):
            parts.append(f"⚖️ REFEREE: {deep_dive['referee_intel']}")

        if deep_dive.get("biscotto_potential") and not is_unknown(
            deep_dive.get("biscotto_potential")
        ):
            parts.append(f"🍪 BISCOTTO: {deep_dive['biscotto_potential']}")

        if deep_dive.get("injury_impact") and deep_dive.get("injury_impact") != "None reported":
            parts.append(f"🏥 INJURY IMPACT: {deep_dive['injury_impact']}")

        if deep_dive.get("btts_impact") and not is_unknown(deep_dive.get("btts_impact")):
            parts.append(f"⚽ BTTS TACTICAL: {deep_dive['btts_impact']}")

        if deep_dive.get("motivation_home") and not is_unknown(deep_dive.get("motivation_home")):
            parts.append(f"🔥 MOTIVATION HOME: {deep_dive['motivation_home']}")

        if deep_dive.get("motivation_away") and not is_unknown(deep_dive.get("motivation_away")):
            parts.append(f"🔥 MOTIVATION AWAY: {deep_dive['motivation_away']}")

        if deep_dive.get("table_context") and not is_unknown(deep_dive.get("table_context")):
            parts.append(f"📊 TABLE: {deep_dive['table_context']}")

        return "\n".join(parts)

    def format_enrichment_for_prompt(self, enrichment: dict) -> str:
        """
        Format match context enrichment for injection into AI prompt.

        Requirements: 2.8

        Args:
            enrichment: Result from enrich_match_context

        Returns:
            Formatted string for prompt injection
        """
        if not enrichment:
            return ""

        parts = ["[DEEPSEEK FRESH CONTEXT]"]

        if enrichment.get("home_form") and enrichment.get("home_form") != "Unknown":
            trend = enrichment.get("home_form_trend", "")
            trend_str = f" ({trend})" if trend and trend != "Unknown" else ""
            parts.append(f"📈 HOME FORM: {enrichment['home_form']}{trend_str}")

        if enrichment.get("away_form") and enrichment.get("away_form") != "Unknown":
            trend = enrichment.get("away_form_trend", "")
            trend_str = f" ({trend})" if trend and trend != "Unknown" else ""
            parts.append(f"📈 AWAY FORM: {enrichment['away_form']}{trend_str}")

        if enrichment.get("home_recent_news") and enrichment.get("home_recent_news") != "Unknown":
            parts.append(f"📰 HOME NEWS: {enrichment['home_recent_news']}")

        if enrichment.get("away_recent_news") and enrichment.get("away_recent_news") != "Unknown":
            parts.append(f"📰 AWAY NEWS: {enrichment['away_recent_news']}")

        if enrichment.get("h2h_recent") and enrichment.get("h2h_recent") != "Unknown":
            goals = enrichment.get("h2h_goals_pattern", "")
            goals_str = f" - {goals}" if goals and goals != "Unknown" else ""
            parts.append(f"⚔️ H2H: {enrichment['h2h_recent']}{goals_str}")

        if enrichment.get("match_importance") and enrichment.get("match_importance") != "Unknown":
            parts.append(f"🎯 IMPORTANCE: {enrichment['match_importance']}")

        if enrichment.get("home_motivation") and enrichment.get("home_motivation") != "Unknown":
            parts.append(f"🔥 HOME MOTIVATION: {enrichment['home_motivation']}")

        if enrichment.get("away_motivation") and enrichment.get("away_motivation") != "Unknown":
            parts.append(f"🔥 AWAY MOTIVATION: {enrichment['away_motivation']}")

        if enrichment.get("weather_impact") and enrichment.get("weather_impact") not in [
            "Unknown",
            "None",
        ]:
            forecast = enrichment.get("weather_forecast", "")
            parts.append(f"🌦️ WEATHER: {forecast} - Impact: {enrichment['weather_impact']}")

        if (
            enrichment.get("additional_context")
            and len(enrichment.get("additional_context", "")) > 10
        ):
            parts.append(f"📝 EXTRA: {enrichment['additional_context'][:200]}")

        return "\n".join(parts) if len(parts) > 1 else ""


# ============================================
# SINGLETON INSTANCE
# ============================================

_deepseek_instance: DeepSeekIntelProvider | None = None
_deepseek_lock = threading.Lock()


def get_deepseek_provider() -> DeepSeekIntelProvider:
    """
    Get or create singleton DeepSeekIntelProvider instance (thread-safe).

    Uses double-checked locking pattern for thread safety.

    Requirements: 8.1, 8.2, 8.3
    """
    global _deepseek_instance

    if _deepseek_instance is None:
        with _deepseek_lock:
            if _deepseek_instance is None:
                _deepseek_instance = DeepSeekIntelProvider()
                logger.debug("🤖 [DEEPSEEK] Global DeepSeekIntelProvider instance initialized")

    return _deepseek_instance
