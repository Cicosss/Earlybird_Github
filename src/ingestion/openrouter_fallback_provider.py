"""
OpenRouter Fallback Provider - V1.0

Uses Claude 3 Haiku as fallback for Perplexity.
Provides identical interface to PerplexityProvider.

V1.0: Initial implementation with Claude 3 Haiku as fallback model
       - get_match_deep_dive
       - verify_news_item
       - get_betting_stats
       - confirm_biscotto

Requirements:
- requests
- OPENROUTER_API_KEY in config/settings.py or environment
- Model: anthropic/claude-3-haiku

Flow: Analyzer -> IntelligenceRouter -> DeepSeek (primary) / Tavily (fallback 1) / Claude 3 Haiku (fallback 2)
"""

import logging
import os
import threading

import requests

from src.ingestion.prompts import (
    build_betting_stats_prompt,
    build_biscotto_confirmation_prompt,
    build_news_verification_prompt,
)
from src.schemas.perplexity_schemas import (
    BETTING_STATS_JSON_SCHEMA,
    DEEP_DIVE_JSON_SCHEMA,
)
from src.utils.ai_parser import normalize_deep_dive_response, parse_ai_json

logger = logging.getLogger(__name__)

# Import from settings (with fallback to env)
try:
    from config.settings import OPENROUTER_API_KEY
except ImportError:
    import os

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# MAJOR FIX #1: Read model from environment variable instead of hardcoding
# This allows configuration without code changes
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT = 60  # seconds


class OpenRouterFallbackProvider:
    """
    OpenRouter fallback provider using Claude 3 Haiku.

    Provides identical interface to PerplexityProvider for seamless fallback.
    Used as third-level fallback after DeepSeek (primary) and Tavily (fallback 1).
    """

    def __init__(self):
        self._enabled = False

        if not OPENROUTER_API_KEY:
            logger.info("ℹ️ OpenRouter Fallback Provider disabled: OPENROUTER_API_KEY not set")
            return

        self._enabled = True
        logger.info("✅ OpenRouter Fallback Provider initialized (Claude 3 Haiku)")

    def is_available(self) -> bool:
        """Check if OpenRouter Fallback Provider is available."""
        return self._enabled

    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: str = None,
        referee: str = None,
        missing_players: list = None,
    ) -> dict | None:
        """
        Get deep analysis for a match from Claude 3 Haiku.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format (optional)
            referee: Referee name (optional)
            missing_players: List of player names reported missing (optional)

        Returns:
            Dict with internal_crisis, turnover_risk, referee_intel, biscotto_potential, injury_impact
            or None on failure
        """
        if not self.is_available():
            logger.debug("OpenRouter Fallback Provider not available")
            return None

        # Build prompt using shared template
        from src.ingestion.prompts import build_deep_dive_prompt

        prompt = build_deep_dive_prompt(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            referee=referee,
            missing_players=missing_players,
        )

        logger.info(f"🤖 [CLAUDE] Deep dive: {home_team} vs {away_team}")
        if missing_players:
            logger.info(f"   📋 Analyzing {len(missing_players)} missing players")

        try:
            result = self._query_api(prompt, task_type="deep_dive")
            if result:
                logger.info("✅ [CLAUDE] Deep dive complete")
                return result
            else:
                logger.warning("⚠️ [CLAUDE] No response from API")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] Deep dive failed: {e}")
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
        Verify a news item using Claude 3 Haiku.

        Identical interface to PerplexityProvider.verify_news_item().
        Called when DeepSeek and Tavily are unavailable.

        Args:
            news_title: Title of the news article
            news_snippet: Snippet/summary of the news
            team_name: Team the news is about
            news_source: Original source of the news
            match_context: Match context (e.g., "vs Real Madrid on 2024-01-15")

        Returns:
            Dict with verification result or None on failure
        """
        if not self.is_available():
            logger.debug("OpenRouter Fallback Provider not available for news verification")
            return None

        # Validate inputs - edge case handling
        if not news_title and not news_snippet:
            logger.debug("News verification skipped: no title or snippet provided")
            return None

        if not team_name:
            logger.debug("News verification skipped: no team name provided")
            return None

        # Build prompt using shared template
        prompt = build_news_verification_prompt(
            news_title=news_title or "",
            news_snippet=news_snippet or "",
            team_name=team_name,
            news_source=news_source,
            match_context=match_context,
        )

        logger.info(f"🤖 [CLAUDE] Verifying news: {(news_title or news_snippet)[:50]}...")

        try:
            # Use _query_api_raw to get raw JSON (not normalized as deep_dive)
            result = self._query_api_raw(prompt)
            if result:
                normalized = self._normalize_verification_result(result)
                status = normalized.get("verification_status", "UNKNOWN")
                logger.info(f"✅ [CLAUDE] Verification complete: {status}")
                return normalized
            else:
                logger.warning("⚠️ [CLAUDE] No response for news verification")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] News verification failed: {e}")
            return None

    def get_betting_stats(
        self, home_team: str, away_team: str, match_date: str, league: str = None
    ) -> dict | None:
        """
        Get corner/cards statistics for combo enrichment.

        Identical interface to PerplexityProvider.get_betting_stats().
        Called when DeepSeek and Tavily are unavailable.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name for context

        Returns:
            Dict with corner/cards stats or None on failure
        """
        if not self.is_available():
            logger.debug("OpenRouter Fallback Provider not available for betting stats")
            return None

        # Build specialized prompt for betting stats
        prompt = build_betting_stats_prompt(
            home_team=home_team, away_team=away_team, match_date=match_date, league=league
        )

        logger.info(
            f"🤖 [CLAUDE] Fetching betting stats: {home_team} vs {away_team} ({match_date})"
        )

        try:
            # Use _query_api with structured outputs for betting stats
            result = self._query_api(prompt, task_type="betting_stats")
            if result:
                logger.info(
                    f"✅ [CLAUDE] Betting stats retrieved: corners={result.get('corners_signal')}, cards={result.get('cards_signal')}"
                )
                return result
            else:
                logger.warning("⚠️ [CLAUDE] No response for betting stats")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] Betting stats failed: {e}")
            return None

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
        Confirm uncertain biscotto signal using Claude 3 Haiku.

        Identical interface to PerplexityProvider.confirm_biscotto().
        Called when DeepSeek and Tavily are unavailable.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name
            draw_odds: Current draw odds
            implied_prob: Implied probability (0-100)
            odds_pattern: Pattern detected (DRIFT, CRASH, STABLE)
            season_context: End of season context string
            detected_factors: List of factors already detected by BiscottoEngine

        Returns:
            Dict with confirmation result or None on failure
        """
        if not self.is_available():
            logger.debug("OpenRouter Fallback Provider not available for biscotto confirmation")
            return None

        # Validate inputs - edge case handling
        if not home_team or not away_team:
            logger.debug("Biscotto confirmation skipped: missing team names")
            return None

        if draw_odds is None or draw_odds <= 1.0:
            logger.debug("Biscotto confirmation skipped: invalid draw odds")
            return None

        # Build prompt
        prompt = build_biscotto_confirmation_prompt(
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

        logger.info(f"🤖 [CLAUDE] Confirming biscotto: {home_team} vs {away_team}...")

        try:
            # Use _query_api_raw to get raw JSON (not normalized as deep_dive)
            result = self._query_api_raw(prompt)
            if result:
                normalized = self._normalize_biscotto_confirmation(result)
                confirmed = normalized.get("biscotto_confirmed", False)
                boost = normalized.get("confidence_boost", 0)
                recommendation = normalized.get("final_recommendation", "Unknown")
                logger.info(
                    f"✅ [CLAUDE] Biscotto confirmation: confirmed={confirmed}, boost=+{boost}, rec={recommendation}"
                )
                return normalized
            else:
                logger.warning("⚠️ [CLAUDE] No response for biscotto confirmation")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] Biscotto confirmation failed: {e}")
            return None

    def _query_api(self, prompt: str, task_type: str = "deep_dive") -> dict | None:
        """
        Query Claude 3 Haiku API with structured outputs support.

        Args:
            prompt: The analysis prompt
            task_type: Type of task ("deep_dive" or "betting_stats")

        Returns:
            Parsed and validated response dict or None
        """
        # Select system prompt and schema based on task type
        if task_type == "deep_dive":
            from src.prompts.system_prompts import DEEP_DIVE_SYSTEM_PROMPT

            system_prompt = DEEP_DIVE_SYSTEM_PROMPT
            json_schema = DEEP_DIVE_JSON_SCHEMA
        elif task_type == "betting_stats":
            from src.prompts.system_prompts import BETTING_STATS_SYSTEM_PROMPT

            system_prompt = BETTING_STATS_SYSTEM_PROMPT
            json_schema = BETTING_STATS_JSON_SCHEMA
        else:
            logger.warning(f"⚠️ [CLAUDE] Unknown task type: {task_type}")
            return None

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        # Base payload
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,  # Low temperature for consistent output
            "max_tokens": 1000,
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL, headers=headers, json=payload, timeout=OPENROUTER_TIMEOUT
            )

            if response.status_code != 200:
                logger.warning(
                    f"⚠️ [CLAUDE] API error: {response.status_code} - {response.text[:200]}"
                )
                return None

            data = response.json()

            # Extract text from OpenAI-compatible response format
            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [CLAUDE] Empty choices in response")
                return None

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if not content:
                logger.warning("⚠️ [CLAUDE] Empty content in response")
                return None

            # Parse with legacy parsing (Claude doesn't support structured outputs like Perplexity)
            parsed = parse_ai_json(content)
            if task_type == "deep_dive":
                return normalize_deep_dive_response(parsed)
            else:
                # For betting_stats, return raw parsed (will be normalized by caller)
                return parsed

        except requests.exceptions.Timeout:
            logger.warning("⚠️ [CLAUDE] Request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ [CLAUDE] Request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] Unexpected error: {e}")
            return None

    def _query_api_raw(self, prompt: str) -> dict | None:
        """
        Query Claude 3 Haiku API and return raw parsed JSON (no normalization).

        Used by methods that need custom response formats (betting_stats, etc.)

        Args:
            prompt: The analysis prompt

        Returns:
            Raw parsed JSON dict or None
        """
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a football analyst. Respond ONLY with valid JSON. No markdown, no explanations.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1000,
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL, headers=headers, json=payload, timeout=OPENROUTER_TIMEOUT
            )

            if response.status_code != 200:
                logger.warning(
                    f"⚠️ [CLAUDE] API error: {response.status_code} - {response.text[:200]}"
                )
                return None

            data = response.json()

            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [CLAUDE] Empty choices in response")
                return None

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if not content:
                logger.warning("⚠️ [CLAUDE] Empty content in response")
                return None

            # Return raw parsed JSON without normalization
            return parse_ai_json(content)

        except requests.exceptions.Timeout:
            logger.warning("⚠️ [CLAUDE] Request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ [CLAUDE] Request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ [CLAUDE] Unexpected error: {e}")
            return None

    def _normalize_verification_result(self, data: dict) -> dict:
        """
        Normalize and validate news verification response.

        Ensures identical structure to PerplexityProvider response.

        Args:
            data: Raw parsed JSON from Claude 3 Haiku

        Returns:
            Normalized dict with all expected fields
        """

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
        """
        Normalize and validate biscotto confirmation response.

        Ensures identical structure to PerplexityProvider response.

        Args:
            data: Raw parsed JSON from Claude 3 Haiku

        Returns:
            Normalized dict with all expected fields
        """

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

    def verify_final_alert(self, verification_prompt: str) -> dict | None:
        """
        Verify final alert using Claude 3 Haiku without web search.

        This method is designed for FinalAlertVerifier which provides
        a comprehensive verification prompt with all match data, analysis,
        and context. No web search is performed as all information
        is already included in the prompt.

        Args:
            verification_prompt: Complete verification prompt with match data,
                               analysis, reasoning, and context

        Returns:
            Dict with verification result or None on failure
        """
        if not self.is_available():
            logger.debug("[CLAUDE] Provider not available for final alert verification")
            return None

        # Validate input
        if not verification_prompt or not verification_prompt.strip():
            logger.debug("[CLAUDE] Final alert verification skipped: empty prompt")
            return None

        try:
            logger.info("🔍 [CLAUDE] Verifying final alert...")

            # Build messages for Claude 3 Haiku
            messages = [
                {
                    "role": "system",
                    "content": "You are a professional betting analyst and fact-checker with 10+ years of experience in sports betting and football analysis. Respond ONLY with valid JSON in the format specified in the user prompt. No markdown, no explanations.",
                },
                {"role": "user", "content": verification_prompt},
            ]

            # Call Claude 3 Haiku with the verification prompt
            response_text = self._query_api_raw(messages)
            if not response_text:
                return None

            # Parse the JSON response
            parsed = response_text  # _query_api_raw already returns parsed JSON
            if not parsed:
                logger.warning("[CLAUDE] Failed to parse final alert verification response")
                return None

            # Normalize the response to ensure all required fields are present
            result = self._normalize_final_alert_verification(parsed)
            status = result.get("verification_status", "UNKNOWN")
            should_send = result.get("should_send", False)

            logger.info(
                f"✅ [CLAUDE] Final alert verification: {status}, should_send={should_send}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ [CLAUDE] Final alert verification error: {e}")
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

    def format_for_prompt(self, deep_dive: dict) -> str:
        """
        Format deep dive results for injection into AI prompt.

        Identical to PerplexityProvider.format_for_prompt for compatibility.

        Args:
            deep_dive: Result from get_match_deep_dive

        Returns:
            Formatted string for prompt injection
        """
        if not deep_dive:
            return ""

        parts = ["[CLAUDE INTELLIGENCE]"]

        if deep_dive.get("internal_crisis") and deep_dive.get("internal_crisis") != "Unknown":
            parts.append(f"⚠️ INTERNAL CRISIS: {deep_dive['internal_crisis']}")

        if deep_dive.get("turnover_risk") and deep_dive.get("turnover_risk") != "Unknown":
            parts.append(f"🔄 TURNOVER RISK: {deep_dive['turnover_risk']}")

        if deep_dive.get("referee_intel") and deep_dive.get("referee_intel") != "Unknown":
            parts.append(f"⚖️ REFEREE: {deep_dive['referee_intel']}")

        if deep_dive.get("biscotto_potential") and deep_dive.get("biscotto_potential") != "Unknown":
            parts.append(f"🍪 BISCOTTO: {deep_dive['biscotto_potential']}")

        if deep_dive.get("injury_impact") and deep_dive.get("injury_impact") != "None reported":
            parts.append(f"🏥 INJURY IMPACT: {deep_dive['injury_impact']}")

        # BTTS Tactical Impact
        if deep_dive.get("btts_impact") and deep_dive.get("btts_impact") != "Unknown":
            parts.append(f"⚽ BTTS TACTICAL: {deep_dive['btts_impact']}")

        # Motivation Intelligence
        if deep_dive.get("motivation_home") and deep_dive.get("motivation_home") != "Unknown":
            parts.append(f"🔥 MOTIVATION HOME: {deep_dive['motivation_home']}")

        if deep_dive.get("motivation_away") and deep_dive.get("motivation_away") != "Unknown":
            parts.append(f"🔥 MOTIVATION AWAY: {deep_dive['motivation_away']}")

        if deep_dive.get("table_context") and deep_dive.get("table_context") != "Unknown":
            parts.append(f"📊 TABLE: {deep_dive['table_context']}")

        # Legacy fields
        if deep_dive.get("referee_stats") and not deep_dive.get("referee_intel"):
            parts.append(f"⚖️ REFEREE: {deep_dive['referee_stats']}")

        if deep_dive.get("h2h_results"):
            parts.append(f"📊 H2H: {deep_dive['h2h_results']}")

        if deep_dive.get("injuries"):
            parts.append(f"🏥 INJURIES: {deep_dive['injuries']}")

        # Raw intel fallback
        if deep_dive.get("raw_intel") and len(parts) == 1:
            parts.append(f"📝 RAW INTEL: {deep_dive['raw_intel'][:500]}")

        return "\n".join(parts)


# Singleton instance
_openrouter_fallback_instance: OpenRouterFallbackProvider | None = None
_openrouter_fallback_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_openrouter_fallback_provider() -> OpenRouterFallbackProvider:
    """
    Get or create the singleton OpenRouterFallbackProvider instance.

    Multiple threads can safely call this function concurrently.
    """
    global _openrouter_fallback_instance
    if _openrouter_fallback_instance is None:
        with _openrouter_fallback_instance_init_lock:
            # Double-checked locking pattern for thread safety
            if _openrouter_fallback_instance is None:
                _openrouter_fallback_instance = OpenRouterFallbackProvider()
    return _openrouter_fallback_instance


def is_openrouter_fallback_available() -> bool:
    """Check if OpenRouter Fallback Provider is available."""
    return get_openrouter_fallback_provider().is_available()
