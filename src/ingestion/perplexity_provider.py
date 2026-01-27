"""
EarlyBird Perplexity Provider V5.0

Fallback AI provider using Perplexity API (sonar-pro model).
Provides identical interface to GeminiAgentProvider for seamless fallback.

V5.0: Added verify_news_item, verify_news_batch, get_betting_stats, confirm_biscotto
      for full compatibility with IntelligenceRouter fallback.

Requirements:
- requests
- PERPLEXITY_API_KEY in config/settings.py or environment

Flow: Analyzer -> IntelligenceRouter -> Gemini (primary) / Perplexity (fallback)
"""
import logging
import os
import requests
from typing import Dict, List, Optional, Type

from src.ingestion.prompts import (
    build_deep_dive_prompt,
    build_news_verification_prompt,
    build_betting_stats_prompt,
    build_biscotto_confirmation_prompt
)
from src.utils.ai_parser import parse_ai_json, normalize_deep_dive_response
from src.schemas.perplexity_schemas import (
    DeepDiveResponse,
    BettingStatsResponse,
    DEEP_DIVE_JSON_SCHEMA,
    BETTING_STATS_JSON_SCHEMA
)
from src.prompts.system_prompts import (
    DEEP_DIVE_SYSTEM_PROMPT,
    BETTING_STATS_SYSTEM_PROMPT
)

logger = logging.getLogger(__name__)

# Import from settings (with fallback to env)
try:
    from config.settings import PERPLEXITY_API_KEY, PERPLEXITY_ENABLED
except ImportError:
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    PERPLEXITY_ENABLED = os.getenv("PERPLEXITY_ENABLED", "true").lower() == "true"

PERPLEXITY_MODEL = "sonar-pro"  # Best for research/grounded responses
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_TIMEOUT = 60  # seconds


class PerplexityProvider:
    """
    Perplexity AI provider for deep match analysis.
    
    Uses Perplexity's sonar-pro model with web search grounding.
    Provides identical interface to GeminiAgentProvider.
    """
    
    def __init__(self):
        self._enabled = False
        
        if not PERPLEXITY_ENABLED:
            logger.info("ℹ️ Perplexity Provider disabled via config")
            return
        
        if not PERPLEXITY_API_KEY:
            logger.info("ℹ️ Perplexity Provider disabled: PERPLEXITY_API_KEY not set")
            return
        
        self._enabled = True
        logger.info("🔮 Perplexity Provider initialized (Fallback)")
    
    def is_available(self) -> bool:
        """Check if Perplexity Provider is available."""
        return self._enabled
    
    def get_match_deep_dive(
        self,
        home_team: str,
        away_team: str,
        match_date: str = None,
        referee: str = None,
        missing_players: list = None
    ) -> Optional[Dict]:
        """
        Get deep analysis for a match from Perplexity.
        
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
            logger.debug("Perplexity Provider not available")
            return None
        
        # Build prompt using shared template
        prompt = build_deep_dive_prompt(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            referee=referee,
            missing_players=missing_players
        )
        
        logger.info(f"🔮 [PERPLEXITY] Deep dive: {home_team} vs {away_team}")
        if missing_players:
            logger.info(f"   📋 Analyzing {len(missing_players)} missing players")
        
        try:
            result = self._query_api(prompt, task_type="deep_dive")
            if result:
                logger.info(f"✅ [PERPLEXITY] Deep dive complete")
                return result
            else:
                logger.warning("⚠️ [PERPLEXITY] No response from API")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] Deep dive failed: {e}")
            return None
    
    def _query_api(self, prompt: str, task_type: str = "deep_dive") -> Optional[Dict]:
        """
        Query Perplexity API with structured outputs support.
        
        Args:
            prompt: The analysis prompt
            task_type: Type of task ("deep_dive" or "betting_stats")
            
        Returns:
            Parsed and validated response dict or None
        """
        # Select system prompt and schema based on task type
        if task_type == "deep_dive":
            system_prompt = DEEP_DIVE_SYSTEM_PROMPT
            json_schema = DEEP_DIVE_JSON_SCHEMA
            response_model = DeepDiveResponse
        elif task_type == "betting_stats":
            system_prompt = BETTING_STATS_SYSTEM_PROMPT
            json_schema = BETTING_STATS_JSON_SCHEMA
            response_model = BettingStatsResponse
        else:
            logger.warning(f"⚠️ [PERPLEXITY] Unknown task type: {task_type}")
            return None
        
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Base payload
        payload = {
            "model": PERPLEXITY_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Low temperature for consistent output
            "max_tokens": 1000
        }
        
        # Add structured output format if supported
        try:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "schema": json_schema,
                    "name": f"{task_type}_response",
                    "strict": True
                }
            }
        except Exception as e:
            logger.debug(f"🔍 [PERPLEXITY] Structured output not available: {e}")
            # Fallback to regular JSON response without schema
        
        try:
            response = requests.post(
                PERPLEXITY_API_URL,
                headers=headers,
                json=payload,
                timeout=PERPLEXITY_TIMEOUT
            )
            
            if response.status_code != 200:
                logger.warning(f"⚠️ [PERPLEXITY] API error: {response.status_code} - {response.text[:200]}")
                return None
            
            data = response.json()
            
            # Extract text from OpenAI-compatible response format
            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [PERPLEXITY] Empty choices in response")
                return None
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if not content:
                logger.warning("⚠️ [PERPLEXITY] Empty content in response")
                return None
            
            # Parse with Pydantic validation
            try:
                # Try direct Pydantic parsing first (for structured outputs)
                validated_response = response_model.model_validate_json(content)
                return validated_response.model_dump()
            except Exception as pydantic_error:
                logger.debug(f"🔍 [PERPLEXITY] Pydantic validation failed: {pydantic_error}")
                
                # Fallback to legacy parsing
                parsed = parse_ai_json(content)
                if task_type == "deep_dive":
                    return normalize_deep_dive_response(parsed)
                else:
                    # For betting_stats, return raw parsed (will be normalized by caller)
                    return parsed
            
        except requests.exceptions.Timeout:
            logger.warning("⚠️ [PERPLEXITY] Request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ [PERPLEXITY] Request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] Unexpected error: {e}")
            return None
    
    def _query_api_raw(self, prompt: str) -> Optional[Dict]:
        """
        Query Perplexity API and return raw parsed JSON (no normalization).
        
        Used by methods that need custom response formats (betting_stats, etc.)
        
        Args:
            prompt: The analysis prompt
            
        Returns:
            Raw parsed JSON dict or None
        """
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": PERPLEXITY_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a football analyst. Respond ONLY with valid JSON. No markdown, no explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(
                PERPLEXITY_API_URL,
                headers=headers,
                json=payload,
                timeout=PERPLEXITY_TIMEOUT
            )
            
            if response.status_code != 200:
                logger.warning(f"⚠️ [PERPLEXITY] API error: {response.status_code} - {response.text[:200]}")
                return None
            
            data = response.json()
            
            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [PERPLEXITY] Empty choices in response")
                return None
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if not content:
                logger.warning("⚠️ [PERPLEXITY] Empty content in response")
                return None
            
            # Return raw parsed JSON without normalization
            return parse_ai_json(content)
            
        except requests.exceptions.Timeout:
            logger.warning("⚠️ [PERPLEXITY] Request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ [PERPLEXITY] Request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] Unexpected error: {e}")
            return None
    
    def format_for_prompt(self, deep_dive: Dict) -> str:
        """
        Format deep dive results for injection into AI prompt.
        
        Identical to GeminiAgentProvider.format_for_prompt for compatibility.
        
        Args:
            deep_dive: Result from get_match_deep_dive
            
        Returns:
            Formatted string for prompt injection
        """
        if not deep_dive:
            return ""
        
        parts = ["[PERPLEXITY INTELLIGENCE]"]
        
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
        
        # BTTS Tactical Impact (V4.1) - Allineato con Gemini
        if deep_dive.get("btts_impact") and deep_dive.get("btts_impact") != "Unknown":
            parts.append(f"⚽ BTTS TACTICAL: {deep_dive['btts_impact']}")
        
        # Motivation Intelligence (V4.2)
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
    
    # ============================================
    # V5.0: NEWS VERIFICATION (Fallback for Gemini)
    # ============================================
    
    def verify_news_item(
        self,
        news_title: str,
        news_snippet: str,
        team_name: str,
        news_source: str = "Unknown",
        match_context: str = "upcoming match"
    ) -> Optional[Dict]:
        """
        V5.0: Verify a news item using Perplexity with web search.
        
        Identical interface to GeminiAgentProvider.verify_news_item().
        Called during cooldown when Gemini is unavailable.
        
        Args:
            news_title: Title of the news article
            news_snippet: Snippet/summary of the news
            team_name: Team the news is about
            news_source: Original source of the news
            match_context: Match context (e.g., "vs Real Madrid on 2024-01-15")
            
        Returns:
            Dict with verification result or None on failure
            
        Requirements: 2.2, 2.5
        """
        if not self.is_available():
            logger.debug("Perplexity Provider not available for news verification")
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
            match_context=match_context
        )
        
        logger.info(f"🔮 [PERPLEXITY] Verifying news: {(news_title or news_snippet)[:50]}...")
        
        try:
            # Use _query_api_raw to get raw JSON (not normalized as deep_dive)
            result = self._query_api_raw(prompt)
            if result:
                normalized = self._normalize_verification_result(result)
                status = normalized.get('verification_status', 'UNKNOWN')
                logger.info(f"✅ [PERPLEXITY] Verification complete: {status}")
                return normalized
            else:
                logger.warning("⚠️ [PERPLEXITY] No response for news verification")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] News verification failed: {e}")
            return None
    
    def _normalize_verification_result(self, data: Dict) -> Dict:
        """
        Normalize and validate news verification response.
        
        Ensures identical structure to GeminiAgentProvider response.
        
        Args:
            data: Raw parsed JSON from Perplexity
            
        Returns:
            Normalized dict with all expected fields
        """
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
    
    def verify_news_batch(
        self,
        news_items: List[Dict],
        team_name: str,
        match_context: str = "upcoming match",
        max_items: int = 5
    ) -> List[Dict]:
        """
        V5.0: Verify multiple news items efficiently.
        
        Identical interface to GeminiAgentProvider.verify_news_batch().
        Filters items that need verification and verifies them in sequence.
        
        Args:
            news_items: List of news item dicts with 'title', 'snippet', 'source', 'confidence'
            team_name: Team the news is about
            match_context: Match context string
            max_items: Maximum items to verify (to respect rate limits)
            
        Returns:
            List of news items with added 'perplexity_verification' field
            
        Requirements: 2.2, 2.5
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
            
            # Skip HIGH/VERY_HIGH confidence (already reliable)
            if confidence in ['HIGH', 'VERY_HIGH']:
                continue
            
            # Check if contains critical keywords
            title = (item.get('title') or '').lower()
            snippet = (item.get('snippet') or '').lower()
            text = f"{title} {snippet}"
            
            has_critical_keyword = any(kw in text for kw in CRITICAL_KEYWORDS)
            
            if has_critical_keyword:
                items_to_verify.append(item)
        
        # Limit to max_items to respect rate limits
        items_to_verify = items_to_verify[:max_items]
        
        if not items_to_verify:
            logger.debug("No news items need verification")
            return news_items
        
        logger.info(f"🔮 [PERPLEXITY] Verifying {len(items_to_verify)} news items...")
        
        # Verify each item
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
                item['perplexity_verification'] = verification
                
                # Boost confidence if verified
                if verification.get('verified') and verification.get('verification_status') == 'CONFIRMED':
                    item['confidence'] = 'HIGH'
                    item['confidence_boosted_by'] = 'perplexity_verification'
                    verified_count += 1
                
                # Add additional context to snippet if found
                additional = verification.get('additional_context', '')
                if additional and additional != "Unknown" and len(additional) > 10:
                    item['snippet'] = f"{item.get('snippet', '')} [PERPLEXITY: {additional}]"
        
        if verified_count > 0:
            logger.info(f"✅ [PERPLEXITY] Verified {verified_count}/{len(items_to_verify)} news items")
        
        return news_items
    
    # ============================================
    # V5.0: BETTING STATS (Fallback for Gemini)
    # ============================================
    
    def get_betting_stats(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str = None
    ) -> Optional[Dict]:
        """
        V5.0: Get corner/cards statistics for combo enrichment.
        
        Identical interface to GeminiAgentProvider.get_betting_stats().
        Called during cooldown when Gemini is unavailable.
        
        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date in YYYY-MM-DD format
            league: League name for context
            
        Returns:
            Dict with corner/cards stats or None on failure
            
        Requirements: 2.3, 2.5
        """
        if not self.is_available():
            logger.debug("Perplexity Provider not available for betting stats")
            return None
        
        # Build specialized prompt for betting stats
        prompt = build_betting_stats_prompt(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            league=league
        )
        
        logger.info(f"🔮 [PERPLEXITY] Fetching betting stats: {home_team} vs {away_team} ({match_date})")
        
        try:
            # Use _query_api with structured outputs for betting stats
            result = self._query_api(prompt, task_type="betting_stats")
            if result:
                logger.info(f"✅ [PERPLEXITY] Betting stats retrieved: corners={result.get('corners_signal')}, cards={result.get('cards_signal')}")
                return result
            else:
                logger.warning("⚠️ [PERPLEXITY] No response for betting stats")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] Betting stats failed: {e}")
            return None
    
    # ============================================
    # V5.0: BISCOTTO CONFIRMATION (Fallback for Gemini)
    # ============================================
    
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
        V5.0: Confirm uncertain biscotto signal using Perplexity with web search.
        
        Identical interface to GeminiAgentProvider.confirm_biscotto().
        Called during cooldown when Gemini is unavailable.
        
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
            
        Requirements: 2.4, 2.5
        """
        if not self.is_available():
            logger.debug("Perplexity Provider not available for biscotto confirmation")
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
            detected_factors=detected_factors
        )
        
        logger.info(f"🔮 [PERPLEXITY] Confirming biscotto: {home_team} vs {away_team}...")
        
        try:
            # Use _query_api_raw to get raw JSON (not normalized as deep_dive)
            result = self._query_api_raw(prompt)
            if result:
                normalized = self._normalize_biscotto_confirmation(result)
                confirmed = normalized.get('biscotto_confirmed', False)
                boost = normalized.get('confidence_boost', 0)
                recommendation = normalized.get('final_recommendation', 'Unknown')
                logger.info(f"✅ [PERPLEXITY] Biscotto confirmation: confirmed={confirmed}, boost=+{boost}, rec={recommendation}")
                return normalized
            else:
                logger.warning("⚠️ [PERPLEXITY] No response for biscotto confirmation")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ [PERPLEXITY] Biscotto confirmation failed: {e}")
            return None
    
    def _normalize_biscotto_confirmation(self, data: Dict) -> Dict:
        """
        Normalize and validate biscotto confirmation response.
        
        Ensures identical structure to GeminiAgentProvider response.
        
        Args:
            data: Raw parsed JSON from Perplexity
            
        Returns:
            Normalized dict with all expected fields
        """
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


# Singleton instance
_perplexity_instance: Optional[PerplexityProvider] = None


def get_perplexity_provider() -> PerplexityProvider:
    """Get or create the singleton PerplexityProvider instance."""
    global _perplexity_instance
    if _perplexity_instance is None:
        _perplexity_instance = PerplexityProvider()
    return _perplexity_instance


def is_perplexity_available() -> bool:
    """Check if Perplexity Provider is available."""
    return get_perplexity_provider().is_available()
