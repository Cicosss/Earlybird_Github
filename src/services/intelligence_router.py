"""
EarlyBird Intelligence Router - V7.0 (DeepSeek + Tavily)

Routes intelligence requests to DeepSeek provider with Tavily pre-enrichment.
Perplexity available as optional fallback for non-critical failures.

V7.0: Added Tavily AI Search for match context enrichment before DeepSeek
V6.0: DeepSeek as sole primary provider (no cooldown needed - high rate limits)
V5.1: Added DeepSeekIntelProvider as primary provider (replaces Gemini)
V5.0: Original implementation with Gemini + Perplexity fallback

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class IntelligenceRouter:
    """
    Routes intelligence requests to DeepSeek (primary) with Tavily pre-enrichment.
    
    V7.0: Tavily AI Search for match context enrichment before DeepSeek analysis.
    V6.0: Simplified routing - DeepSeek has high rate limits, no cooldown needed.
    Perplexity used only as fallback for transient errors.
    
    Requirements: 2.1-2.6, 3.1-3.4
    """
    
    def __init__(self):
        """
        Initialize IntelligenceRouter with DeepSeek as primary provider and Tavily for enrichment.
        
        Requirements: 2.1-2.4, 3.1
        """
        # Import here to avoid circular dependencies
        from src.ingestion.deepseek_intel_provider import get_deepseek_provider
        from src.ingestion.perplexity_provider import get_perplexity_provider
        from src.ingestion.tavily_provider import get_tavily_provider
        from src.ingestion.tavily_query_builder import TavilyQueryBuilder
        from src.ingestion.tavily_budget import get_budget_manager
        
        self._primary_provider = get_deepseek_provider()
        self._fallback_provider = get_perplexity_provider()
        self._tavily = get_tavily_provider()
        self._tavily_query_builder = TavilyQueryBuilder
        self._budget_manager = get_budget_manager()
        
        tavily_status = "enabled" if self._tavily.is_available() else "disabled"
        logger.info(f"🔀 IntelligenceRouter V7.0 initialized (DeepSeek primary, Tavily {tavily_status}, Perplexity fallback)")
    
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
        fallback_func: Callable,
        *args,
        **kwargs
    ) -> Optional[Any]:
        """
        Route a request to DeepSeek, with Perplexity as optional fallback.
        
        V6.0: Simplified routing - DeepSeek primary, Perplexity fallback on errors.
        No cooldown management needed (DeepSeek has high rate limits).
        
        Args:
            operation: Name of the operation for logging
            primary_func: Primary provider (DeepSeek) method to call
            fallback_func: Fallback provider (Perplexity) method to call
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
            logger.warning(f"⚠️ [DEEPSEEK] {operation} failed: {e}, trying Perplexity fallback...")
            
            # Fall back to Perplexity on any error
            try:
                return fallback_func(*args, **kwargs)
            except Exception as perplexity_error:
                logger.warning(f"⚠️ [PERPLEXITY] {operation} fallback failed: {perplexity_error}")
                return None
    
    # ============================================
    # PROXIED METHODS - Same interface as GeminiAgentProvider/DeepSeekIntelProvider
    # ============================================
    
    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: Optional[str] = None,
        referee: Optional[str] = None,
        missing_players: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Get deep analysis for a match.
        
        Routes to active provider based on cooldown state.
        
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
            fallback_func=lambda: self._fallback_provider.get_match_deep_dive(
                home_team, away_team, match_date, referee, missing_players
            )
        )
    
    def verify_news_item(
        self,
        news_title: str,
        news_snippet: str,
        team_name: str,
        news_source: str = "Unknown",
        match_context: str = "upcoming match"
    ) -> Optional[Dict]:
        """
        Verify a news item using web search.
        
        Routes to active provider based on cooldown state.
        
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
            fallback_func=lambda: self._fallback_provider.verify_news_item(
                news_title, news_snippet, team_name, news_source, match_context
            )
        )
    
    def verify_news_batch(
        self,
        news_items: List[Dict],
        team_name: str,
        match_context: str = "upcoming match",
        max_items: int = 5
    ) -> List[Dict]:
        """
        Verify multiple news items with Tavily pre-filtering.
        
        V7.0: Uses Tavily as pre-filter before DeepSeek verification.
        
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
        
        # Step 2: Route to DeepSeek/Perplexity for full verification
        result = self._route_request(
            operation="news_batch_verification",
            primary_func=lambda: self._primary_provider.verify_news_batch(
                prefiltered_items, team_name, match_context, max_items
            ),
            fallback_func=lambda: self._fallback_provider.verify_news_batch(
                prefiltered_items, team_name, match_context, max_items
            )
        )
        
        # Return original items if routing failed
        return result if result is not None else prefiltered_items
    
    def get_betting_stats(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get corner/cards statistics for combo enrichment.
        
        Routes to active provider based on cooldown state.
        
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
            fallback_func=lambda: self._fallback_provider.get_betting_stats(
                home_team, away_team, match_date, league
            )
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
        detected_factors: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Confirm uncertain biscotto signal with Tavily evidence search.
        
        V7.0: Uses Tavily to search for mutual benefit evidence before DeepSeek.
        
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
            home_team=home_team,
            away_team=away_team,
            league=league,
            season_context=season_context
        )
        
        # Step 2: Route to DeepSeek/Perplexity for confirmation
        result = self._route_request(
            operation="biscotto_confirmation",
            primary_func=lambda: self._primary_provider.confirm_biscotto(
                home_team, away_team, match_date, league,
                draw_odds, implied_prob, odds_pattern, season_context, detected_factors
            ),
            fallback_func=lambda: self._fallback_provider.confirm_biscotto(
                home_team, away_team, match_date, league,
                draw_odds, implied_prob, odds_pattern, season_context, detected_factors
            )
        )
        
        # Step 3: Merge Tavily evidence into result
        if result and tavily_evidence:
            result["tavily_evidence"] = tavily_evidence
            result["tavily_enriched"] = True
        elif result:
            result["tavily_enriched"] = False
        
        return result
    
    def format_for_prompt(self, deep_dive: Optional[Dict]) -> str:
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
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str = ""
    ) -> Optional[str]:
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
                ]
            )
            
            # Execute search
            response = self._tavily.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=True
            )
            
            if response:
                # Record budget usage
                self._budget_manager.record_call("main_pipeline")
                
                # Format enrichment
                enrichment_parts = []
                
                if response.answer:
                    enrichment_parts.append(f"[TAVILY SUMMARY]\n{response.answer}")
                
                if response.results:
                    snippets = [f"• {r.title}: {r.content[:200]}" for r in response.results[:3]]
                    if snippets:
                        enrichment_parts.append(f"[TAVILY SOURCES]\n" + "\n".join(snippets))
                
                if enrichment_parts:
                    logger.info(f"🔍 [TAVILY] Match enrichment found for {home_team} vs {away_team}")
                    return "\n\n".join(enrichment_parts)
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ [TAVILY] Match enrichment failed: {e}")
            return None
    
    def _merge_tavily_context(
        self,
        existing_context: str,
        tavily_enrichment: str
    ) -> str:
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
        self,
        home_team: str,
        away_team: str,
        league: str,
        season_context: str
    ) -> Optional[Dict]:
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
        if not self._tavily.is_available():
            return None
        
        if not self._budget_manager.can_call("main_pipeline", is_critical=True):
            return None
        
        try:
            query = self._tavily_query_builder.build_biscotto_query(
                home_team=home_team,
                away_team=away_team,
                league=league,
                season_context=season_context
            )
            
            response = self._tavily.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True
            )
            
            if response:
                self._budget_manager.record_call("main_pipeline")
                
                evidence = {
                    "source": "tavily",
                    "answer": response.answer,
                    "articles": [
                        {"title": r.title, "url": r.url, "snippet": r.content}
                        for r in response.results[:3]
                    ]
                }
                
                logger.info(f"🔍 [TAVILY] Biscotto evidence search completed for {home_team} vs {away_team}")
                return evidence
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ [TAVILY] Biscotto evidence search failed: {e}")
            return None
    
    def _tavily_prefilter_news(
        self,
        news_items: List[Dict],
        team_name: str
    ) -> List[Dict]:
        """
        Use Tavily to pre-filter news items before DeepSeek verification.
        
        Args:
            news_items: List of news item dicts
            team_name: Team the news is about
            
        Returns:
            News items with Tavily pre-verification
            
        Requirements: 3.4
        """
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
                    news_title=title,
                    team_name=team_name
                )
                
                response = self._tavily.search(
                    query=query,
                    search_depth="basic",
                    max_results=3,
                    include_answer=True
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
        existing_context: str = ""
    ) -> Optional[Dict]:
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
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            league=league
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
            
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Match context enrichment failed: {e}")
            
            # Return Tavily-only enrichment if DeepSeek fails
            if tavily_enrichment:
                return {
                    "context": tavily_enrichment,
                    "source": "tavily_only",
                    "tavily_enriched": True
                }
            
            return None
    
    def extract_twitter_intel(
        self,
        handles: List[str],
        max_posts_per_account: int = 5
    ) -> Optional[Dict]:
        """
        Extract recent tweets from specified accounts.
        
        Uses DeepSeek + Brave Search.
        
        Args:
            handles: List of Twitter handles (with @)
            max_posts_per_account: Max posts to extract per account
            
        Returns:
            Dict with extracted tweets or None
        """
        try:
            return self._primary_provider.extract_twitter_intel(handles, max_posts_per_account)
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Twitter intel extraction failed: {e}")
            return None
    
    def format_enrichment_for_prompt(self, enrichment: Dict) -> str:
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
    
    def get_circuit_status(self) -> Dict:
        """
        Get provider status for monitoring.
        
        Returns:
            Dict with provider statistics including Tavily status
        """
        tavily_status = self._tavily.get_status() if self._tavily else {}
        budget_status = self._budget_manager.get_status() if self._budget_manager else {}
        
        return {
            "provider": "deepseek",
            "available": self._primary_provider.is_available(),
            "cooldown_active": False,  # V6.0: No cooldown with DeepSeek
            "tavily": {
                "available": self._tavily.is_available() if self._tavily else False,
                "fallback_active": tavily_status.get("fallback_active", False),
                "cache_size": tavily_status.get("cache_size", 0),
            },
            "budget": {
                "monthly_used": budget_status.monthly_used if budget_status else 0,
                "monthly_limit": budget_status.monthly_limit if budget_status else 0,
                "is_degraded": budget_status.is_degraded if budget_status else False,
                "is_disabled": budget_status.is_disabled if budget_status else False,
            }
        }


# ============================================
# SINGLETON INSTANCE
# ============================================

_intelligence_router_instance: Optional[IntelligenceRouter] = None


def get_intelligence_router() -> IntelligenceRouter:
    """Get or create the singleton IntelligenceRouter instance."""
    global _intelligence_router_instance
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
