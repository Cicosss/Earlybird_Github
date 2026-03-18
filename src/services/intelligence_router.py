"""
EarlyBird Intelligence Router - V8.1 (DeepSeek + Tavily + Claude 3 Haiku)

Routes intelligence requests to DeepSeek provider with Tavily pre-enrichment.
Three-level fallback: DeepSeek (primary) → Tavily (fallback 1) → Claude 3 Haiku (fallback 2).

V8.1: Intelligent feature detection via startup_validator.is_feature_disabled()
      - Skips Tavily enrichment if 'tavily_enrichment' is disabled
      - Logs clear status messages for disabled features
V8.0: Added Claude 3 Haiku as third-level fallback via OpenRouter
V7.0: Added Tavily AI Search for match context enrichment before DeepSeek
V6.0: DeepSeek as sole primary provider (no cooldown needed - high rate limits)
V5.1: Added DeepSeekIntelProvider as primary provider (replaces Gemini)
V5.0: Original implementation with Gemini + Perplexity fallback

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# V8.1: Import startup validator for intelligent feature detection
try:
    from src.utils.startup_validator import is_feature_disabled

    _STARTUP_VALIDATOR_AVAILABLE = True
except ImportError:
    _STARTUP_VALIDATOR_AVAILABLE = False
    logger.debug("Startup validator not available - all features enabled by default")

    def is_feature_disabled(feature: str) -> bool:
        """Fallback: no features are disabled if validator unavailable."""
        return False


class IntelligenceRouter:
    """
    Routes intelligence requests to DeepSeek (primary) with three-level fallback.

    V8.0: Three-level fallback - DeepSeek → Tavily → Claude 3 Haiku
    V7.0: Tavily AI Search for match context enrichment before DeepSeek analysis.
    V6.0: Simplified routing - DeepSeek has high rate limits, no cooldown needed.

    Requirements: 2.1-2.6, 3.1-3.4
    """

    def __init__(self):
        """
        Initialize IntelligenceRouter with three-level fallback.

        Requirements: 2.1-2.4, 3.1
        """
        # Import here to avoid circular dependencies
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        from src.ingestion.openrouter_fallback_provider import get_openrouter_fallback_provider
        from src.ingestion.tavily_budget import get_budget_manager
        from src.ingestion.tavily_provider import get_tavily_provider
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder

        self._primary_provider = get_deepseek_provider()
        self._fallback_1_provider = get_tavily_provider()  # Tavily
        self._fallback_2_provider = get_openrouter_fallback_provider()  # Claude 3 Haiku
        self._tavily = get_tavily_provider()
        self._tavily_query_builder = TavilyQueryBuilder
        self._budget_manager = get_budget_manager()

        fallback_1_status = "enabled" if self._fallback_1_provider.is_available() else "disabled"
        fallback_2_status = "enabled" if self._fallback_2_provider.is_available() else "disabled"
        logger.info(
            f"🔀 IntelligenceRouter V8.0 initialized "
            f"(DeepSeek primary, Tavily {fallback_1_status}, Claude 3 Haiku {fallback_2_status})"
        )

    # ============================================
    # PUBLIC API - Status Methods
    # ============================================

    def is_available(self) -> bool:
        """
        Check if the primary provider (DeepSeek) is available.

        Returns:
            True if DeepSeek is available, False otherwise
        """
        return self._primary_provider.is_available()

    def get_active_provider_name(self) -> str:
        """
        Get the name of the currently active provider.

        Returns:
            Always "deepseek" (V6.0 - DeepSeek only)
        """
        return "deepseek"

    def get_cooldown_status(self) -> None:
        """
        Get current cooldown status (deprecated - kept for backward compatibility).

        Returns:
            None (cooldown no longer used with DeepSeek)
        """
        return None

    # ============================================
    # INTERNAL - Request Routing
    # ============================================

    def _route_request(
        self,
        operation: str,
        primary_func: Callable,
        fallback_1_func: Callable,
        fallback_2_func: Callable,
        *args,
        **kwargs,
    ) -> Any | None:
        """
        Route a request with three-level fallback.

        V8.0: Three-level fallback - DeepSeek → Tavily → Claude 3 Haiku
        No cooldown management needed (DeepSeek has high rate limits).

        Args:
            operation: Name of the operation for logging
            primary_func: Primary provider (DeepSeek) method to call
            fallback_1_func: Fallback 1 provider (Tavily) method to call
            fallback_2_func: Fallback 2 provider (Claude 3 Haiku) method to call
            *args, **kwargs: Arguments to pass to the provider method

        Returns:
            Provider response or None on failure

        Requirements: 2.1-2.4, 2.6
        """
        # Try DeepSeek first (primary)
        try:
            result = primary_func(*args, **kwargs)
            return result
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] {operation} failed: {e}, trying Tavily fallback...")

            # Fall back to Tavily
            try:
                return fallback_1_func(*args, **kwargs)
            except Exception as tavily_error:
                logger.warning(
                    f"⚠️ [TAVILY] {operation} fallback failed: {tavily_error}, trying Claude 3 Haiku fallback..."
                )

                # Fall back to Claude 3 Haiku
                try:
                    return fallback_2_func(*args, **kwargs)
                except Exception as claude_error:
                    logger.warning(f"⚠️ [CLAUDE] {operation} fallback failed: {claude_error}")
                    return None

    # ============================================
    # PROXIED METHODS - Same interface as GeminiAgentProvider/DeepSeekIntelProvider
    # ============================================

    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: str | None = None,
        referee: str | None = None,
        missing_players: list[str] | None = None,
    ) -> dict | None:
        """
        Get deep analysis for a match.

        Routes to DeepSeek (primary) → Claude 3 Haiku (fallback).
        Tavily is NOT used as fallback because it doesn't have get_match_deep_dive() method.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format (optional)
            referee: Referee name (optional)
            missing_players: List of player names reported missing (optional)

        Returns:
            Dict with analysis or None on failure

        Requirements: 2.1
        """
        return self._route_request(
            operation="deep_dive",
            primary_func=lambda: self._primary_provider.get_match_deep_dive(
                home_team, away_team, match_date, referee, missing_players
            ),
            fallback_1_func=lambda: self._fallback_2_provider.get_match_deep_dive(
                home_team, away_team, match_date, referee, missing_players
            ),
            fallback_2_func=None,  # No third fallback for deep dive
        )

    def verify_news_item(
        self,
        news_title: str,
        news_snippet: str,
        team_name: str,
        news_source: str = "Unknown",
        match_context: str = "upcoming match",
    ) -> dict | None:
        """
        Verify a news item using web search.

        Routes to DeepSeek (primary) → Claude 3 Haiku (fallback).
        Tavily is NOT used as fallback because it doesn't have verify_news_item() method.

        Args:
            news_title: Title of the news article
            news_snippet: Snippet/summary of the news
            team_name: Team the news is about
            news_source: Original source of the news
            match_context: Match context string

        Returns:
            Dict with verification result or None on failure

        Requirements: 2.2
        """
        return self._route_request(
            operation="news_verification",
            primary_func=lambda: self._primary_provider.verify_news_item(
                news_title, news_snippet, team_name, news_source, match_context
            ),
            fallback_1_func=lambda: self._fallback_2_provider.verify_news_item(
                news_title, news_snippet, team_name, news_source, match_context
            ),
            fallback_2_func=None,  # No third fallback for news verification
        )

    def verify_news_batch(
        self,
        news_items: list[dict],
        team_name: str,
        match_context: str = "upcoming match",
        max_items: int = 5,
    ) -> list[dict]:
        """
        Verify multiple news items with Tavily pre-filtering.

        V7.0: Uses Tavily as pre-filter before DeepSeek verification.
        V8.1: Fixed fallback routing - Tavily doesn't have verify_news_batch() method.

        Args:
            news_items: List of news item dicts
            team_name: Team the news is about
            match_context: Match context string
            max_items: Maximum items to verify

        Returns:
            List of news items with verification results

        Requirements: 2.2, 3.4
        """
        if not news_items:
            return news_items

        # Step 1: Pre-filter with Tavily
        prefiltered_items = self._tavily_prefilter_news(news_items, team_name)

        # Step 2: Route to DeepSeek → Claude 3 Haiku for full verification
        # Tavily is NOT used as fallback because it doesn't have verify_news_batch() method
        result = self._route_request(
            operation="news_batch_verification",
            primary_func=lambda: self._primary_provider.verify_news_batch(
                prefiltered_items, team_name, match_context, max_items
            ),
            fallback_1_func=lambda: self._fallback_2_provider.verify_news_batch(
                prefiltered_items, team_name, match_context, max_items
            ),
            fallback_2_func=None,  # No third fallback for news batch verification
        )

        # Return original items if routing failed
        return result if result is not None else prefiltered_items

    def get_betting_stats(
        self, home_team: str, away_team: str, match_date: str, league: str | None = None
    ) -> dict | None:
        """
        Get corner/cards statistics for combo enrichment.

        Routes to DeepSeek (primary) → Claude 3 Haiku (fallback).
        Tavily is NOT used as fallback because it doesn't have get_betting_stats() method.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name for context

        Returns:
            Dict with betting stats or None on failure

        Requirements: 2.3
        """
        return self._route_request(
            operation="betting_stats",
            primary_func=lambda: self._primary_provider.get_betting_stats(
                home_team, away_team, match_date, league
            ),
            fallback_1_func=lambda: self._fallback_2_provider.get_betting_stats(
                home_team, away_team, match_date, league
            ),
            fallback_2_func=None,  # No third fallback for betting stats
        )

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
        detected_factors: list[str] | None = None,
    ) -> dict | None:
        """
        Confirm uncertain biscotto signal with Tavily evidence search.

        V7.0: Uses Tavily to search for mutual benefit evidence before DeepSeek.
        V8.1: Fixed fallback routing - Tavily doesn't have confirm_biscotto() method.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name
            draw_odds: Current draw odds
            implied_prob: Implied probability (0-100)
            odds_pattern: Pattern detected (DRIFT, CRASH, STABLE)
            season_context: End of season context string
            detected_factors: List of factors already detected

        Returns:
            Dict with confirmation result or None on failure

        Requirements: 2.4, 3.3
        """
        # Step 1: Search for biscotto evidence with Tavily
        tavily_evidence = self._tavily_search_biscotto_evidence(
            home_team=home_team, away_team=away_team, league=league, season_context=season_context
        )

        # Step 2: Route to DeepSeek → Claude 3 Haiku for confirmation
        # Tavily is NOT used as fallback because it doesn't have confirm_biscotto() method
        result = self._route_request(
            operation="biscotto_confirmation",
            primary_func=lambda: self._primary_provider.confirm_biscotto(
                home_team,
                away_team,
                match_date,
                league,
                draw_odds,
                implied_prob,
                odds_pattern,
                season_context,
                detected_factors,
            ),
            fallback_1_func=lambda: self._fallback_2_provider.confirm_biscotto(
                home_team,
                away_team,
                match_date,
                league,
                draw_odds,
                implied_prob,
                odds_pattern,
                season_context,
                detected_factors,
            ),
            fallback_2_func=None,  # No third fallback for biscotto confirmation
        )

        # Step 3: Merge Tavily evidence into result
        if result and tavily_evidence:
            result["tavily_evidence"] = tavily_evidence
            result["tavily_enriched"] = True
        elif result:
            result["tavily_enriched"] = False

        return result

    def verify_final_alert(self, verification_prompt: str) -> dict | None:
        """
        Verify final alert using AI providers without web search.

        This method is designed for FinalAlertVerifier which provides
        a comprehensive verification prompt with all match data, analysis,
        and context. No web search is performed as all information
        is already included in the prompt.

        Routes to DeepSeek (primary) → Claude 3 Haiku (fallback).
        Tavily is NOT used as fallback because it doesn't have verify_final_alert() method.

        Args:
            verification_prompt: Complete verification prompt with match data,
                               analysis, reasoning, and context

        Returns:
            Dict with verification result or None on failure

        Requirements: 2.6
        """
        return self._route_request(
            operation="final_alert_verification",
            primary_func=lambda: self._primary_provider.verify_final_alert(verification_prompt),
            fallback_1_func=lambda: self._fallback_2_provider.verify_final_alert(
                verification_prompt
            ),
            fallback_2_func=None,  # No third fallback for final alert verification
        )

    def format_for_prompt(self, deep_dive: dict | None) -> str:
        """
        Format deep dive results for injection into AI prompt.

        Uses DeepSeek's formatter for consistent output.

        Args:
            deep_dive: Result from get_match_deep_dive

        Returns:
            Formatted string for prompt injection
        """
        if not deep_dive:
            return ""

        return self._primary_provider.format_for_prompt(deep_dive)

    # ============================================
    # ADDITIONAL METHODS (DeepSeek-specific, passthrough)
    # ============================================

    def _tavily_enrich_match(
        self, home_team: str, away_team: str, match_date: str, league: str = ""
    ) -> str | None:
        """
        Use Tavily to gather match context before DeepSeek analysis.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name for context

        Returns:
            Enriched context string or None

        Requirements: 3.1
        """
        # V8.1: Check if Tavily enrichment is disabled via startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("tavily_enrichment"):
            logger.debug(
                "⏭️ [TAVILY] Enrichment disabled by startup validator (TAVILY_API_KEY not configured)"
            )
            return None

        if not self._tavily.is_available():
            return None

        # Check budget
        if not self._budget_manager.can_call("main_pipeline"):
            logger.debug("📊 [TAVILY] Budget limit reached for main_pipeline")
            return None

        try:
            # Build enrichment query
            query = self._tavily_query_builder.build_match_enrichment_query(
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                questions=[
                    "Recent team news and injuries",
                    "Current form and standings",
                    "Key player availability",
                    "Head-to-head recent results",
                ],
            )

            # Execute search
            response = self._tavily.search(
                query=query, search_depth="basic", max_results=5, include_answer=True
            )

            if response:
                # Record budget usage
                self._budget_manager.record_call("main_pipeline")

                # Format enrichment
                enrichment_parts = []

                if response.answer:
                    enrichment_parts.append(f"[TAVILY SUMMARY]\n{response.answer}")

                if response.results:
                    snippets = [
                        f"• {r.title}: {(r.content or '')[:200]}" for r in response.results[:3]
                    ]
                    if snippets:
                        enrichment_parts.append("[TAVILY SOURCES]\n" + "\n".join(snippets))

                if enrichment_parts:
                    logger.info(
                        f"🔍 [TAVILY] Match enrichment found for {home_team} vs {away_team}"
                    )
                    return "\n\n".join(enrichment_parts)

            return None

        except Exception as e:
            logger.warning(f"⚠️ [TAVILY] Match enrichment failed: {e}")
            return None

    def _merge_tavily_context(self, existing_context: str, tavily_enrichment: str) -> str:
        """
        Merge Tavily enrichment with existing context.

        Args:
            existing_context: Already gathered context
            tavily_enrichment: Tavily search results

        Returns:
            Merged context string

        Requirements: 3.2
        """
        if not tavily_enrichment:
            return existing_context

        if not existing_context:
            return tavily_enrichment

        # Merge with clear separation
        return f"{existing_context}\n\n{tavily_enrichment}"

    def _tavily_search_biscotto_evidence(
        self, home_team: str, away_team: str, league: str, season_context: str
    ) -> dict | None:
        """
        Use Tavily to search for biscotto (mutual benefit) evidence.

        Args:
            home_team: Home team name
            away_team: Away team name
            league: League name
            season_context: Season context string

        Returns:
            Dict with evidence or None

        Requirements: 3.3
        """
        # V8.1: Check if Tavily enrichment is disabled by startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("tavily_enrichment"):
            logger.debug(
                "⏭️ [TAVILY] Biscotto evidence search disabled by startup validator (TAVILY_API_KEY not configured)"
            )
            return None

        if not self._tavily.is_available():
            return None

        if not self._budget_manager.can_call("main_pipeline", is_critical=True):
            return None

        try:
            query = self._tavily_query_builder.build_biscotto_query(
                home_team=home_team,
                away_team=away_team,
                league=league,
                season_context=season_context,
            )

            response = self._tavily.search(
                query=query, search_depth="advanced", max_results=5, include_answer=True
            )

            if response:
                self._budget_manager.record_call("main_pipeline")

                evidence = {
                    "source": "tavily",
                    "answer": response.answer,
                    "articles": [
                        {"title": r.title, "url": r.url, "snippet": r.content}
                        for r in response.results[:3]
                    ],
                }

                logger.info(
                    f"🔍 [TAVILY] Biscotto evidence search completed for {home_team} vs {away_team}"
                )
                return evidence

            return None

        except Exception as e:
            logger.warning(f"⚠️ [TAVILY] Biscotto evidence search failed: {e}")
            return None

    def _tavily_prefilter_news(self, news_items: list[dict], team_name: str) -> list[dict]:
        """
        Use Tavily to pre-filter news items before DeepSeek verification.

        Args:
            news_items: List of news item dicts
            team_name: Team the news is about

        Returns:
            News items with Tavily pre-verification

        Requirements: 3.4
        """
        # V8.1: Check if Tavily enrichment is disabled by startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("tavily_enrichment"):
            logger.debug(
                "⏭️ [TAVILY] News pre-filter disabled by startup validator (TAVILY_API_KEY not configured)"
            )
            return news_items

        if not self._tavily.is_available():
            return news_items

        if not news_items:
            return news_items

        if not self._budget_manager.can_call("main_pipeline"):
            return news_items

        try:
            # Only verify top 3 items to save budget
            items_to_verify = news_items[:3]

            for item in items_to_verify:
                title = item.get("title", "")
                if not title:
                    continue

                query = self._tavily_query_builder.build_news_verification_query(
                    news_title=title, team_name=team_name
                )

                response = self._tavily.search(
                    query=query, search_depth="basic", max_results=3, include_answer=True
                )

                if response:
                    self._budget_manager.record_call("main_pipeline")

                    # Add Tavily verification to item
                    item["tavily_verified"] = True
                    item["tavily_answer"] = response.answer
                    item["tavily_sources"] = len(response.results)

                    logger.debug(f"🔍 [TAVILY] Pre-verified news: {title[:50]}...")

            return news_items

        except Exception as e:
            logger.warning(f"⚠️ [TAVILY] News pre-filter failed: {e}")
            return news_items

    def enrich_match_context(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str,
        existing_context: str = "",
    ) -> dict | None:
        """
        Enrich match context with Tavily before DeepSeek analysis.

        V7.0: Uses Tavily for initial enrichment, then DeepSeek for deep analysis.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name
            existing_context: Already gathered context

        Returns:
            Dict with enriched context or None

        Requirements: 3.1, 3.2
        """
        # Step 1: Try Tavily enrichment first
        tavily_enrichment = self._tavily_enrich_match(
            home_team=home_team, away_team=away_team, match_date=match_date, league=league
        )

        # Step 2: Merge Tavily context with existing
        merged_context = self._merge_tavily_context(existing_context, tavily_enrichment)

        # Step 3: Continue with DeepSeek analysis
        try:
            result = self._primary_provider.enrich_match_context(
                home_team, away_team, match_date, league, merged_context
            )

            # Add Tavily flag to result
            if result:
                result["tavily_enriched"] = tavily_enrichment is not None
                return result
            else:
                # DeepSeek returned None - fall back to Tavily enrichment
                logger.warning(
                    "⚠️ [DEEPSEEK] Match context enrichment returned None, using Tavily fallback"
                )

        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Match context enrichment failed: {e}")

        # Return Tavily-only enrichment if DeepSeek fails or returns None
        if tavily_enrichment:
            logger.info("✅ [INTELLIGENCEROUTER] Using Tavily-only enrichment as fallback")
            return {
                "context": tavily_enrichment,
                "source": "tavily_only",
                "tavily_enriched": True,
            }

        logger.warning(
            "⚠️ [INTELLIGENCEROUTER] No enrichment available (DeepSeek and Tavily both failed)"
        )
        return None

    def extract_twitter_intel(
        self, handles: list[str], max_posts_per_account: int = 5
    ) -> dict | None:
        """
        Extract recent tweets from specified accounts.

        Uses DeepSeek + TwitterIntelCache (V10.0) with fallback to Claude 3 Haiku.

        Args:
            handles: List of Twitter handles (with @)
            max_posts_per_account: Max posts to extract per account

        Returns:
            Dict with extracted tweets or None
        """
        try:
            result = self._primary_provider.extract_twitter_intel(handles, max_posts_per_account)
            if result is None:
                logger.debug(f"🐦 [INTEL] No Twitter intel available for {len(handles)} handles")
            return result
        except Exception as e:
            logger.warning(
                f"⚠️ [DEEPSEEK] Twitter intel extraction failed: {e}, trying Claude fallback..."
            )

            # Fall back to OpenRouterFallbackProvider (Claude 3 Haiku)
            try:
                result = self._fallback_2_provider.extract_twitter_intel(
                    handles, max_posts_per_account
                )
                if result:
                    logger.info(
                        "✅ [INTELLIGENCEROUTER] Using Claude 3 Haiku fallback for Twitter intel"
                    )
                return result
            except Exception as fallback_error:
                logger.warning(f"⚠️ [CLAUDE] Twitter intel fallback failed: {fallback_error}")
                return None

    def format_enrichment_for_prompt(self, enrichment: dict) -> str:
        """
        Format match context enrichment for injection into AI prompt.

        Args:
            enrichment: Result from enrich_match_context

        Returns:
            Formatted string for prompt injection
        """
        if not enrichment:
            return ""

        return self._primary_provider.format_enrichment_for_prompt(enrichment)

    def get_circuit_status(self) -> dict:
        """
        Get provider status for monitoring.

        V6.1: Budget now uses unified BudgetStatus.to_dict() for serialization.

        Returns:
            Dict with provider statistics including Tavily status
        """
        tavily_status = self._tavily.get_status() if self._tavily else {}
        budget_status = self._budget_manager.get_status() if self._budget_manager else None

        return {
            "provider": "deepseek",
            "available": self._primary_provider.is_available(),
            "cooldown_active": False,  # V6.0: No cooldown with DeepSeek
            "tavily": {
                "available": self._tavily.is_available() if self._tavily else False,
                "fallback_active": tavily_status.get("fallback_active", False),
                "cache_size": tavily_status.get("cache_size", 0),
            },
            "budget": budget_status.to_dict()
            if budget_status
            else {
                "monthly_used": 0,
                "monthly_limit": 0,
                "daily_used": 0,
                "daily_limit": 0,
                "is_degraded": False,
                "is_disabled": False,
                "usage_percentage": 0.0,
                "component_usage": None,
                "daily_reset_date": None,
                "provider_name": None,
            },
        }


# ============================================
# SINGLETON INSTANCE
# ============================================

_intelligence_router_instance: IntelligenceRouter | None = None
_intelligence_router_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_intelligence_router() -> IntelligenceRouter:
    """
    Get or create the singleton IntelligenceRouter instance.

    Thread-safe implementation using double-checked locking pattern.
    """
    global _intelligence_router_instance
    if _intelligence_router_instance is None:
        with _intelligence_router_instance_init_lock:
            if _intelligence_router_instance is None:
                _intelligence_router_instance = IntelligenceRouter()
    return _intelligence_router_instance


def is_intelligence_available() -> bool:
    """Check if any intelligence provider is available."""
    try:
        return get_intelligence_router().is_available()
    except Exception as e:
        logger.error(f"Error checking intelligence availability: {e}")
        return False
