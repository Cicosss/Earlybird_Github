"""
EarlyBird DeepSeek Intel Provider - OpenRouter API (V6.1)

Drop-in replacement for GeminiAgentProvider using DeepSeek via OpenRouter.
Uses DDG as primary search (to save Brave quota) with Brave as fallback.

Flow:
1. DDG Search (primary) or Brave Search (fallback) for real-time web results
2. DeepSeek via OpenRouter for AI analysis

V6.1: DDG as primary search to reduce Brave API quota consumption
      Brave quota reserved for news_hunter which needs higher quality results
V1.0: Initial implementation with same interface as GeminiAgentProvider

Requirements:
- OPENROUTER_API_KEY environment variable
- DDG library (ddgs) for primary search
- Brave Search API (via BraveSearchProvider) as fallback

Phase 1 Critical Fix: Added URL encoding for non-ASCII characters in search queries
"""
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

from src.ingestion.brave_provider import get_brave_provider
from src.ingestion.search_provider import get_search_provider
from src.ingestion.prompts import (
    build_deep_dive_prompt,
    build_betting_stats_prompt,
    build_news_verification_prompt,
    build_biscotto_confirmation_prompt,
    build_match_context_enrichment_prompt
)
from src.utils.ai_parser import parse_ai_json, normalize_deep_dive_response
from src.utils.http_client import get_http_client

# V6.0: CooldownManager import removed - OpenRouter/DeepSeek has high rate limits
# and should not share cooldown state with Gemini Direct API

logger = logging.getLogger(__name__)

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEEPSEEK_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")  # DeepSeek V3.2 via OpenRouter
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Rate limiting configuration
DEEPSEEK_MIN_INTERVAL = 2.0  # Minimum seconds between requests (Requirements 4.2)


class DeepSeekIntelProvider:
    """
    Provider AI che usa DeepSeek via OpenRouter + Brave Search.
    Drop-in replacement per GeminiAgentProvider.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 2.1-2.8
    """
    
    def __init__(self):
        """
        Inizializza con OPENROUTER_API_KEY e BraveSearchProvider.
        
        Requirements: 1.1, 1.2
        """
        self._api_key = OPENROUTER_API_KEY
        self._enabled = False
        self._last_request_time = 0.0  # For rate limiting
        self._brave_provider = None
        self._http_client = None  # Centralized HTTP client
        
        if not self._api_key:
            logger.warning("⚠️ DeepSeek Intel Provider disabled: OPENROUTER_API_KEY not set")
            return
        
        try:
            self._brave_provider = get_brave_provider()
            self._search_provider = get_search_provider()  # V6.1: DDG primary for DeepSeek
            self._http_client = get_http_client()  # Use centralized HTTP client
            self._enabled = True
            logger.info("🤖 DeepSeek Intel Provider initialized (OpenRouter + DDG/Brave Search)")
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
    
    def _search_brave(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Esegue ricerca web e ritorna risultati.
        
        V6.1: Usa DDG come primary per risparmiare quota Brave.
        Brave viene usato solo come fallback se DDG fallisce.
        
        Gestisce errori gracefully (return empty list on failure).
        
        Phase 1 Critical Fix: URL-encode query to handle non-ASCII characters
        (e.g., Turkish "ş", Polish "ą", Greek "α").
        
        Requirements: 3.1, 3.3, 3.4
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of dicts with title, url, snippet
        """
        # Phase 1 Critical Fix: URL-encode query to handle special characters
        # This fixes search failures for non-English team names
        encoded_query = quote(query, safe=' ')
        
        # V6.1: Try SearchProvider first (DDG primary, then Brave fallback)
        # This saves Brave quota for news_hunter which needs higher quality results
        if hasattr(self, '_search_provider') and self._search_provider:
            try:
                logger.debug(f"🔍 [DEEPSEEK] DDG search: {query[:60]}...")
                results = self._search_provider.search(encoded_query, limit)
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
            results = self._brave_provider.search_news(encoded_query, limit=limit)
            logger.debug(f"🔍 [DEEPSEEK] Brave returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"⚠️ [DEEPSEEK] Brave search error: {e}")
            return []
    
    def _format_brave_results(self, results: List[Dict]) -> str:
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
    
    def _build_prompt_with_context(
        self,
        base_prompt: str,
        brave_results: str
    ) -> str:
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
    
    def _call_deepseek(
        self,
        prompt: str,
        operation_name: str
    ) -> Optional[str]:
        """
        Chiama DeepSeek via OpenRouter con rate limiting.
        
        V6.0: CooldownManager NON usato - OpenRouter ha rate limit alti.
        Su 429 ritorna None ma NON attiva cooldown globale.
        
        Requirements: 4.2, 7.2
        
        Args:
            prompt: The prompt to send to DeepSeek
            operation_name: Name for logging
            
        Returns:
            Raw response text or None on failure
        """
        # V6.0: CooldownManager check removed
        # OpenRouter/DeepSeek has much higher rate limits than Gemini Direct API
        
        # Rate limiting (local, not shared)
        self._wait_for_rate_limit()
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.betting",  # Required by OpenRouter
            "X-Title": "EarlyBird Betting Intelligence"
        }
        
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # Lower temperature for more consistent analysis
            "max_tokens": 2000
        }
        
        try:
            logger.info(f"🤖 [DEEPSEEK] {operation_name}...")
            
            # Use centralized HTTP client instead of creating new client
            if not self._http_client:
                logger.error("❌ [DEEPSEEK] HTTP client not initialized")
                return None
            
            response = self._http_client.post_sync(
                OPENROUTER_API_URL,
                rate_limit_key="openrouter",
                headers=headers,
                json=payload,
                timeout=60,
                max_retries=2
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
                logger.error(f"❌ [DEEPSEEK] API error: HTTP {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            
            # Extract response text
            choices = data.get("choices", [])
            if not choices:
                logger.warning(f"⚠️ [DEEPSEEK] Empty response for {operation_name}")
                return None
            
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                logger.warning(f"⚠️ [DEEPSEEK] No content in response for {operation_name}")
                return None
            
            # V6.0: CooldownManager.record_successful_call() removed
            # OpenRouter/DeepSeek doesn't use shared cooldown state
            
            logger.info(f"✅ [DEEPSEEK] {operation_name} complete")
            return content
            
        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Error in {operation_name}: {e}")
            return None
    
    # ============================================
    # NORMALIZATION HELPERS
    # ============================================
    
    def _normalize_verification_result(self, data: Dict) -> Dict:
        """Normalize news verification response with safe defaults."""
        def safe_bool(val, default=False):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ('true', 'yes', 'si', '1', 'confirmed')
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
    
    def _normalize_biscotto_confirmation(self, data: Dict) -> Dict:
        """Normalize biscotto confirmation response with safe defaults."""
        def safe_bool(val, default=False):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ('true', 'yes', 'si', '1', 'confirmed')
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
            "mutual_benefit_reason": safe_str(data.get("mutual_benefit_reason"), "No clear mutual benefit"),
            "h2h_pattern": safe_str(data.get("h2h_pattern"), "No data"),
            "club_relationship": safe_str(data.get("club_relationship"), "None found"),
            "manager_hints": safe_str(data.get("manager_hints"), "None found"),
            "market_sentiment": safe_str(data.get("market_sentiment"), "Unknown"),
            "additional_context": safe_str(data.get("additional_context"), ""),
            "final_recommendation": safe_str(data.get("final_recommendation"), "MONITOR LIVE"),
        }
    
    def _normalize_match_enrichment(self, data: Dict) -> Dict:
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
    
    def _normalize_betting_stats(self, data: Dict) -> Dict:
        """Normalize betting stats response with safe defaults."""
        def safe_str(val, default="Unknown"):
            if val is None or val == "":
                return default
            return str(val)
        
        def safe_float(val, default=0.0):
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default
        
        def safe_int(val, default=0):
            if val is None:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default
        
        return {
            "avg_corners_home": safe_float(data.get("avg_corners_home")),
            "avg_corners_away": safe_float(data.get("avg_corners_away")),
            "avg_corners_total": safe_float(data.get("avg_corners_total")),
            "avg_cards_home": safe_float(data.get("avg_cards_home")),
            "avg_cards_away": safe_float(data.get("avg_cards_away")),
            "avg_cards_total": safe_float(data.get("avg_cards_total")),
            "recent_corners_trend": safe_str(data.get("recent_corners_trend")),
            "recent_cards_trend": safe_str(data.get("recent_cards_trend")),
            "h2h_corners_avg": safe_float(data.get("h2h_corners_avg")),
            "h2h_cards_avg": safe_float(data.get("h2h_cards_avg")),
            "over_corners_recommendation": safe_str(data.get("over_corners_recommendation")),
            "over_cards_recommendation": safe_str(data.get("over_cards_recommendation")),
            "confidence_level": safe_str(data.get("confidence_level"), "LOW"),
            "data_freshness": safe_str(data.get("data_freshness"), "Unknown"),
            "additional_context": safe_str(data.get("additional_context"), ""),
        }


    # ============================================
    # PUBLIC API METHODS (Same interface as GeminiAgentProvider)
    # ============================================
    
    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: str = None,
        referee: str = None,
        missing_players: list = None
    ) -> Optional[Dict]:
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
                missing_players=missing_players
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)
            
            logger.info(f"🤖 [DEEPSEEK] Deep dive: {home_team} vs {away_team}")
            
            # Call DeepSeek
            response_text = self._call_deepseek(final_prompt, "deep_dive")
            
            if not response_text:
                return None
            
            # Parse and normalize
            parsed = parse_ai_json(response_text, None)
            return normalize_deep_dive_response(parsed)
            
        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Deep dive error: {e}")
            return None
    
    def get_betting_stats(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str = None
    ) -> Optional[Dict]:
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
        if not home_team or not home_team.strip() or not away_team or not away_team.strip() or not match_date or not match_date.strip():
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
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                league=league
            )
            final_prompt = self._build_prompt_with_context(base_prompt, formatted_results)
            
            logger.info(f"🎰 [DEEPSEEK] Betting stats: {home_team} vs {away_team}")
            
            # Call DeepSeek
            response_text = self._call_deepseek(final_prompt, "betting_stats")
            
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
        match_context: str = "upcoming match"
    ) -> Optional[Dict]:
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
                match_context=match_context
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
        news_items: List[Dict],
        team_name: str,
        match_context: str = "upcoming match",
        max_items: int = 5
    ) -> List[Dict]:
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
            'injury', 'injured', 'infortunio', 'lesión', 'lesão',
            'out', 'ruled out', 'miss', 'absent', 'assente', 'baja',
            'suspended', 'squalificato', 'sancionado',
            'doubt', 'doubtful', 'dubbio',
            'crisis', 'sacked', 'fired', 'esonerato'
        ]
        
        # Filter items that need verification
        items_to_verify = []
        for item in news_items:
            confidence = item.get('confidence', 'LOW')
            
            # Skip HIGH/VERY_HIGH confidence
            if confidence in ['HIGH', 'VERY_HIGH']:
                continue
            
            # Check for critical keywords
            title = (item.get('title') or '').lower()
            snippet = (item.get('snippet') or '').lower()
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
                news_title=item.get('title', ''),
                news_snippet=item.get('snippet', ''),
                team_name=team_name,
                news_source=item.get('source', 'Unknown'),
                match_context=match_context
            )
            
            if verification:
                item['deepseek_verification'] = verification
                
                if verification.get('verified') and verification.get('verification_status') == 'CONFIRMED':
                    item['confidence'] = 'HIGH'
                    item['confidence_boosted_by'] = 'deepseek_verification'
                    verified_count += 1
                
                additional = verification.get('additional_context', '')
                if additional and additional != "Unknown" and len(additional) > 10:
                    item['snippet'] = f"{item.get('snippet', '')} [DEEPSEEK: {additional}]"
        
        if verified_count > 0:
            logger.info(f"✅ [DEEPSEEK] Verified {verified_count}/{len(items_to_verify)} news items")
        
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
        detected_factors: List[str] = None
    ) -> Optional[Dict]:
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
                detected_factors=detected_factors
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
    
    def enrich_match_context(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str,
        existing_context: str = ""
    ) -> Optional[Dict]:
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
                existing_context=existing_context or ""
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
                logger.info(f"✅ [DEEPSEEK] Context enriched (freshness: {result.get('data_freshness')})")
                return result
            return None
            
        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Match enrichment error: {e}")
            return None
    
    def extract_twitter_intel(
        self,
        handles: List[str],
        max_posts_per_account: int = 5
    ) -> Optional[Dict]:
        """
        Extract recent tweets using DeepSeek + Brave Search.
        
        V6.2 FIX: Processa TUTTI gli handle in batch da 10, non solo i primi 10.
        Ritorna anche statistiche su quanti handle sono stati processati.
        
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
        
        # V6.2: Filter out invalid handles
        valid_handles = [
            h for h in handles 
            if h and isinstance(h, str) and h.strip()
        ]
        
        if not valid_handles:
            logger.debug("[DEEPSEEK] Twitter extraction skipped: no valid handles after filtering")
            return None
        
        if not self.is_available():
            logger.debug("[DEEPSEEK] Provider not available")
            return None
        
        try:
            # V6.2 FIX: Process ALL handles in batches of 10
            BATCH_SIZE = 10
            all_accounts = []
            total_handles = len(valid_handles)
            batches_processed = 0
            batches_failed = 0
            
            logger.info(f"🐦 [DEEPSEEK] Extracting tweets from {total_handles} accounts in {(total_handles + BATCH_SIZE - 1) // BATCH_SIZE} batches...")
            
            for batch_start in range(0, total_handles, BATCH_SIZE):
                batch_handles = valid_handles[batch_start:batch_start + BATCH_SIZE]
                batch_num = batch_start // BATCH_SIZE + 1
                
                logger.debug(f"🐦 [DEEPSEEK] Processing batch {batch_num}: {len(batch_handles)} handles")
                
                # Build search query for this batch
                handles_str = " OR ".join(batch_handles)
                search_query = f"site:twitter.com OR site:x.com {handles_str} football"
                
                # Search Brave for Twitter content
                brave_results = self._search_brave(search_query, limit=10)
                formatted_results = self._format_brave_results(brave_results)
                
                # Build prompt for tweet extraction - V6.2: Escape braces properly
                prompt = f"""You are a football news aggregator. Extract recent tweets from the search results.

TASK: Find football-related posts from these accounts: {', '.join(batch_handles)}

{formatted_results}

OUTPUT FORMAT: Return ONLY a JSON object with this structure:
- "accounts": array of objects with "handle", "posts" array
- Each post has: "date" (YYYY-MM-DD), "content" (tweet text), "topics" (array of tags)
- "extraction_time": ISO8601 timestamp

TOPIC TAGS: injury, lineup, transfer, squad, breaking, preview

RULES:
1. Last 7 days only
2. Football content only
3. Max 280 chars per post
4. Empty posts array if no content found for an account
5. Include ALL accounts from the task list, even if no posts found"""
                
                # Call DeepSeek for this batch
                response_text = self._call_deepseek(prompt, f"twitter_batch_{batch_num}")
                
                if response_text:
                    parsed = parse_ai_json(response_text, None)
                    if parsed and parsed.get("accounts"):
                        all_accounts.extend(parsed["accounts"])
                        batches_processed += 1
                    else:
                        batches_failed += 1
                        logger.warning(f"⚠️ [DEEPSEEK] Batch {batch_num} returned no accounts")
                else:
                    batches_failed += 1
                    logger.warning(f"⚠️ [DEEPSEEK] Batch {batch_num} failed")
            
            # Build final result
            if not all_accounts:
                logger.warning(f"⚠️ [DEEPSEEK] All {batches_failed} batches failed, no accounts extracted")
                return None
            
            result = {
                "accounts": all_accounts,
                "extraction_time": datetime.utcnow().isoformat() + "Z",
                # V6.2: Add metadata for debugging and fallback logic
                "_meta": {
                    "total_handles_requested": total_handles,
                    "accounts_returned": len(all_accounts),
                    "batches_processed": batches_processed,
                    "batches_failed": batches_failed,
                    "is_complete": len(all_accounts) >= total_handles * 0.5  # At least 50% coverage
                }
            }
            
            accounts_with_posts = sum(1 for a in all_accounts if a.get("posts"))
            total_posts = sum(len(a.get("posts", [])) for a in all_accounts)
            
            logger.info(
                f"✅ [DEEPSEEK] Twitter: {accounts_with_posts}/{len(all_accounts)} accounts with posts, "
                f"{total_posts} total posts ({batches_processed} batches OK, {batches_failed} failed)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [DEEPSEEK] Twitter extraction error: {e}")
            return None
    
    # ============================================
    # FORMATTING METHODS (Same as GeminiAgentProvider)
    # ============================================
    
    def format_for_prompt(self, deep_dive: Dict) -> str:
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
        
        if deep_dive.get("btts_impact") and deep_dive.get("btts_impact") != "Unknown":
            parts.append(f"⚽ BTTS TACTICAL: {deep_dive['btts_impact']}")
        
        if deep_dive.get("motivation_home") and deep_dive.get("motivation_home") != "Unknown":
            parts.append(f"🔥 MOTIVATION HOME: {deep_dive['motivation_home']}")
        
        if deep_dive.get("motivation_away") and deep_dive.get("motivation_away") != "Unknown":
            parts.append(f"🔥 MOTIVATION AWAY: {deep_dive['motivation_away']}")
        
        if deep_dive.get("table_context") and deep_dive.get("table_context") != "Unknown":
            parts.append(f"📊 TABLE: {deep_dive['table_context']}")
        
        return "\n".join(parts)
    
    def format_enrichment_for_prompt(self, enrichment: Dict) -> str:
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
        
        if enrichment.get("weather_impact") and enrichment.get("weather_impact") not in ["Unknown", "None"]:
            forecast = enrichment.get("weather_forecast", "")
            parts.append(f"🌦️ WEATHER: {forecast} - Impact: {enrichment['weather_impact']}")
        
        if enrichment.get("additional_context") and len(enrichment.get("additional_context", "")) > 10:
            parts.append(f"📝 EXTRA: {enrichment['additional_context'][:200]}")
        
        return "\n".join(parts) if len(parts) > 1 else ""


# ============================================
# SINGLETON INSTANCE
# ============================================

_deepseek_instance: Optional[DeepSeekIntelProvider] = None
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
