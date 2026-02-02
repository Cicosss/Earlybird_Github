"""
Twitter Intel Cache Service - EarlyBird V7.0

Gestisce la cache dei tweet estratti via Gemini Search Grounding.
All'inizio di ogni ciclo, interroga Gemini per gli ultimi 5 post
di ogni account configurato e mantiene i dati in cache per tutto il ciclo.

V7.0: Tavily AI Search integration for Twitter intel recovery when
Gemini/Nitter fails. Uses Tavily to search for recent tweets from
configured accounts as fallback.

FLUSSO:
1. All'inizio del ciclo: refresh_twitter_intel()
2. Durante il ciclo: get_cached_intel() per consultare i dati
3. Per alert: enrich_alert_with_twitter_intel() per arricchire contesto
4. Fine ciclo: cache viene invalidata automaticamente al prossimo refresh
5. V7.0: Se Gemini fallisce, usa Tavily per recuperare intel

UTILIZZO:
    from src.services.twitter_intel_cache import TwitterIntelCache
    
    cache = TwitterIntelCache()
    await cache.refresh_twitter_intel()  # Inizio ciclo
    
    # Durante il ciclo
    intel = cache.get_intel_for_league("soccer_turkey_super_league")
    relevant = cache.search_intel("Galatasaray injury")

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import logging
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import configurazione account
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.twitter_intel_accounts import (
    get_twitter_intel_accounts,
    get_all_twitter_handles,
    get_handles_by_tier,
    LeagueTier,
    TwitterIntelAccount,
    build_gemini_twitter_extraction_prompt
)

# V7.0: Tavily integration for Twitter recovery
_TAVILY_AVAILABLE = False
_TavilyProvider = None
_TavilyQueryBuilder = None
_get_budget_manager = None

try:
    from src.ingestion.tavily_provider import get_tavily_provider, TavilyProvider
    from src.ingestion.tavily_query_builder import TavilyQueryBuilder
    from src.ingestion.tavily_budget import get_budget_manager
    _TAVILY_AVAILABLE = True
    _TavilyProvider = TavilyProvider
    _TavilyQueryBuilder = TavilyQueryBuilder
    _get_budget_manager = get_budget_manager
except ImportError as e:
    logging.debug(f"Tavily not available for Twitter recovery: {e}")


class IntelRelevance(Enum):
    """Rilevanza dell'intel per un alert"""
    HIGH = "high"        # Menziona direttamente team/player dell'alert
    MEDIUM = "medium"    # Menziona lega o topic correlato
    LOW = "low"          # Generico, potenzialmente utile
    NONE = "none"        # Non rilevante


@dataclass
class CachedTweet:
    """Singolo tweet cachato"""
    handle: str
    date: str
    content: str
    topics: List[str] = field(default_factory=list)
    raw_data: Dict = field(default_factory=dict)


@dataclass
class TwitterIntelCacheEntry:
    """Entry della cache per un account"""
    handle: str
    account_name: str
    league_focus: str
    tweets: List[CachedTweet] = field(default_factory=list)
    last_refresh: datetime = None
    extraction_success: bool = False
    error_message: str = None


class TwitterIntelCache:
    """
    Cache per intel Twitter estratti via Gemini Search Grounding.
    
    Singleton pattern per garantire una sola istanza della cache
    condivisa tra tutti i componenti del sistema.
    
    V7.1: Thread-safe singleton con double-check locking pattern.
    Necessario perché la cache può essere acceduta da:
    - Main thread (pipeline principale)
    - BrowserMonitorThread (monitoraggio web)
    - Async tasks (news_hunter, tweet_relevance_filter)
    """
    
    _instance: Optional['TwitterIntelCache'] = None
    _instance_lock: Optional[threading.Lock] = None  # Initialized lazily to avoid import-time issues
    _initialization_lock: Optional[threading.Lock] = None  # Separate lock for initialization
    
    @classmethod
    def _get_lock(cls) -> threading.Lock:
        """Get or create the instance lock (lazy initialization)."""
        if cls._instance_lock is None:
            cls._instance_lock = threading.Lock()
        return cls._instance_lock
    
    @classmethod
    def _get_initialization_lock(cls) -> threading.Lock:
        """Get or create the initialization lock (lazy initialization)."""
        if cls._initialization_lock is None:
            cls._initialization_lock = threading.Lock()
        return cls._initialization_lock
    
    def __new__(cls) -> 'TwitterIntelCache':
        # Fast path: instance already exists
        if cls._instance is not None:
            return cls._instance
        
        # Slow path: need to create instance with lock
        lock = cls._get_lock()
        with lock:
            # Double-check inside lock to prevent race condition
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        # Check if already initialized (thread-safe)
        if getattr(self, '_initialized', False):
            return
            
        # Use initialization lock to prevent race conditions during __init__
        init_lock = self._get_initialization_lock()
        with init_lock:
            # Double-check after acquiring lock
            if getattr(self, '_initialized', False):
                return
            
            self._cache: Dict[str, TwitterIntelCacheEntry] = {}
            self._last_full_refresh: Optional[datetime] = None
            self._cycle_id: Optional[str] = None
            self._cache_lock: threading.Lock = threading.Lock()  # Lock for cache operations
            
            # V7.0: Tavily integration for Twitter recovery
            self._tavily: Optional[Any] = None
            self._unavailable_accounts: Dict[str, datetime] = {}  # handle -> marked_unavailable_time
            self._tavily_recovery_count: int = 0
            
            if _TAVILY_AVAILABLE:
                try:
                    from src.ingestion.tavily_provider import get_tavily_provider
                    self._tavily = get_tavily_provider()
                    logging.info("🐦 TwitterIntelCache initialized with Tavily recovery")
                except Exception as e:
                    logging.warning(f"🐦 Tavily not available for Twitter recovery: {e}")
            else:
                logging.info("🐦 TwitterIntelCache initialized (no Tavily)")
            
            # Mark as initialized AFTER all initialization is complete
            self._initialized = True
    
    @property
    def is_fresh(self) -> bool:
        """Verifica se la cache è stata refreshata in questo ciclo"""
        if not self._last_full_refresh:
            return False
        # Cache valida per 360 minuti (6 ore) per risparmiare quota Gemini API
        # Con 1500 req/day limit, refresh ogni 6h = 4 refresh/day = ~20 chiamate/day per Twitter
        now = datetime.now(timezone.utc)
        # Handle both naive and timezone-aware datetimes
        if self._last_full_refresh.tzinfo is None:
            # Naive datetime - convert to UTC (assuming naive is in local time, convert to UTC)
            # Use timestamp to properly convert to UTC
            last_refresh = datetime.fromtimestamp(self._last_full_refresh.timestamp(), tz=timezone.utc)
        else:
            # Timezone-aware datetime - convert to UTC if needed
            last_refresh = self._last_full_refresh.astimezone(timezone.utc) if self._last_full_refresh.tzinfo else self._last_full_refresh
        return now - last_refresh < timedelta(minutes=360)

    @property
    def cache_age_minutes(self) -> int:
        """Età della cache in minuti"""
        if not self._last_full_refresh:
            return -1
        now = datetime.now(timezone.utc)
        # Handle both naive and timezone-aware datetimes
        if self._last_full_refresh.tzinfo is None:
            # Naive datetime - convert to UTC (assuming naive is in local time, convert to UTC)
            # Use timestamp to properly convert to UTC
            last_refresh = datetime.fromtimestamp(self._last_full_refresh.timestamp(), tz=timezone.utc)
        else:
            # Timezone-aware datetime - convert to UTC if needed
            last_refresh = self._last_full_refresh.astimezone(timezone.utc) if self._last_full_refresh.tzinfo else self._last_full_refresh
        return int((now - last_refresh).total_seconds() / 60)
    
    def _normalize_handle(self, handle: str) -> str:
        """
        Normalizza un handle Twitter per lookup nella cache.
        
        Args:
            handle: Handle Twitter (con o senza @)
            
        Returns:
            Handle normalizzato (lowercase, senza @)
        """
        if not handle or not isinstance(handle, str):
            return ""
        return handle.lower().replace("@", "").strip()
    
    def get_cached_intel(self) -> Dict[str, TwitterIntelCacheEntry]:
        """
        Ottiene tutti i dati cachati.
        
        Returns:
            Dict con handle -> TwitterIntelCacheEntry
        """
        with self._cache_lock:
            return dict(self._cache)
    
    async def refresh_twitter_intel(
        self,
        gemini_service: Any,
        tier: Optional[LeagueTier] = None,
        max_posts_per_account: int = 5
    ) -> Dict[str, Any]:
        """
        Refresha la cache interrogando Gemini per gli ultimi tweet.
        
        Chiamare all'inizio di ogni ciclo.
        
        Args:
            gemini_service: Istanza del servizio Gemini con Search Grounding
            tier: Opzionale, filtra per tier (Elite 7 o Tier 2)
            max_posts_per_account: Numero max di post per account
            
        Returns:
            Dict con statistiche del refresh
        """
        start_time = datetime.now(timezone.utc)
        self._cycle_id = start_time.strftime("%Y%m%d_%H%M%S")
        
        logging.info(f"🐦 Starting Twitter Intel refresh (cycle: {self._cycle_id})")
        
        # Ottieni handle da interrogare
        if tier:
            handles_by_country = get_handles_by_tier(tier)
            all_handles = []
            for handles in handles_by_country.values():
                all_handles.extend(handles)
        else:
            all_handles = get_all_twitter_handles()
        
        logging.info(f"🐦 Querying {len(all_handles)} Twitter accounts via Gemini")
        
        # Costruisci prompt per Gemini
        prompt = build_gemini_twitter_extraction_prompt(all_handles, max_posts_per_account)
        
        # Query Gemini con Search Grounding
        stats = {
            "cycle_id": self._cycle_id,
            "accounts_queried": len(all_handles),
            "accounts_with_data": 0,
            "total_tweets_cached": 0,
            "errors": [],
            "duration_seconds": 0
        }
        
        try:
            # Chiama Gemini (assumendo che gemini_service abbia un metodo search_grounding)
            response = await self._query_gemini(gemini_service, prompt)
            
            if response:
                # Parsa la risposta e popola la cache
                parsed = self._parse_gemini_response(response)
                
                with self._cache_lock:
                    for account_data in parsed.get("accounts", []):
                        handle = account_data.get("handle", "")
                        tweets = account_data.get("posts", [])
                        
                        if tweets:
                            stats["accounts_with_data"] += 1
                            stats["total_tweets_cached"] += len(tweets)
                        
                        # Trova info account dalla configurazione
                        account_info = self._find_account_info(handle)
                        
                        # Crea entry cache
                        entry = TwitterIntelCacheEntry(
                            handle=handle,
                            account_name=account_info.name if account_info else handle,
                            league_focus=account_info.focus if account_info else "unknown",
                            tweets=[
                                CachedTweet(
                                    handle=handle,
                                    date=t.get("date", ""),
                                    content=t.get("content", ""),
                                    topics=t.get("topics", []),
                                    raw_data=t
                                )
                                for t in tweets
                            ],
                            last_refresh=datetime.now(timezone.utc),
                            extraction_success=True
                        )
                        
                        # Use normalized handle for cache key
                        self._cache[self._normalize_handle(handle)] = entry
                
        except Exception as e:
            logging.error(f"🐦 Error refreshing Twitter intel: {e}", exc_info=True)
            stats["errors"].append(str(e))
        
        # Finalizza stats
        stats["duration_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._last_full_refresh = datetime.now(timezone.utc)
        
        # V7.0: Attempt Tavily recovery for accounts without data
        if self._tavily and hasattr(self._tavily, 'is_available') and self._tavily.is_available():
            failed_handles = [
                h for h in all_handles
                if self._normalize_handle(h) not in self._cache 
                or not self._cache.get(self._normalize_handle(h), TwitterIntelCacheEntry(
                    handle="", account_name="", league_focus=""
                )).tweets
            ]
            
            if failed_handles:
                logging.info(f"🐦 [TAVILY] Attempting recovery for {len(failed_handles)} failed accounts...")
                recovery_stats = self.recover_failed_accounts(failed_handles)
                stats["tavily_recovery"] = recovery_stats
                stats["accounts_with_data"] += recovery_stats.get("recovered", 0)
                stats["total_tweets_cached"] += recovery_stats.get("tweets_recovered", 0)
        
        logging.info(
            f"🐦 Twitter Intel refresh complete: "
            f"{stats['accounts_with_data']}/{stats['accounts_queried']} accounts, "
            f"{stats['total_tweets_cached']} tweets cached "
            f"({stats['duration_seconds']:.1f}s)"
        )
        
        return stats
    
    async def _query_gemini(self, gemini_service: Any, prompt: str) -> Optional[str]:
        """
        Query Gemini con Search Grounding.
        
        Args:
            gemini_service: Servizio Gemini (GeminiAgentProvider)
            prompt: Prompt per l'estrazione (non usato, usiamo metodo dedicato)
            
        Returns:
            Risposta raw da Gemini
        """
        try:
            # Usa il metodo dedicato extract_twitter_intel
            if hasattr(gemini_service, 'extract_twitter_intel'):
                # Ottieni tutti gli handle
                all_handles = get_all_twitter_handles()
                return gemini_service.extract_twitter_intel(all_handles, max_posts_per_account=5)
            else:
                logging.warning("🐦 Gemini service doesn't have extract_twitter_intel method")
                return None
        except Exception as e:
            logging.error(f"🐦 Gemini query failed: {e}")
            return None
    
    def _parse_gemini_response(self, response: Any) -> Dict:
        """
        Parsa la risposta di Gemini.
        
        Args:
            response: Risposta da Gemini (già dict dal metodo extract_twitter_intel)
            
        Returns:
            Dict con dati strutturati
        """
        try:
            # Se è già un dict, ritornalo direttamente
            if isinstance(response, dict):
                return response
            
            # Se è una stringa, prova a parsare come JSON
            if isinstance(response, str):
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    return json.loads(json_match.group())
            
            # Fallback: parsing manuale
            logging.warning("🐦 Could not parse Gemini response, using fallback")
            return {"accounts": []}
            
        except json.JSONDecodeError as e:
            logging.error(f"🐦 JSON parse error: {e}")
            return {"accounts": []}
    
    def _find_account_info(self, handle: str) -> Optional[TwitterIntelAccount]:
        """
        Trova info account dalla configurazione.
        
        V6.2: Usa funzione centralizzata find_account_by_handle per evitare duplicazione.
        """
        from config.twitter_intel_accounts import find_account_by_handle
        return find_account_by_handle(handle)
    
    def get_intel_for_league(self, league_key: str) -> List[CachedTweet]:
        """
        Ottiene tutti i tweet cachati per una lega specifica.
        
        Args:
            league_key: Chiave API della lega
            
        Returns:
            Lista di tweet rilevanti per la lega
        """
        accounts = get_twitter_intel_accounts(league_key)
        tweets = []
        
        with self._cache_lock:
            for account in accounts:
                handle_key = self._normalize_handle(account.handle)
                if handle_key in self._cache:
                    tweets.extend(self._cache[handle_key].tweets)
        
        return tweets
    
    def search_intel(
        self,
        query: str,
        league_key: Optional[str] = None,
        topics: Optional[List[str]] = None
    ) -> List[CachedTweet]:
        """
        Cerca nella cache tweet che matchano la query.
        
        Args:
            query: Testo da cercare (team name, player, etc.)
            league_key: Opzionale, filtra per lega
            topics: Opzionale, filtra per topic (injury, lineup, etc.)
            
        Returns:
            Lista di tweet rilevanti
        """
        if not query or not isinstance(query, str):
            return []
        
        results = []
        query_lower = query.lower()
        
        # Determina quali entry cercare
        if league_key:
            accounts = get_twitter_intel_accounts(league_key)
            with self._cache_lock:
                entries = [
                    self._cache.get(self._normalize_handle(a.handle))
                    for a in accounts
                    if self._normalize_handle(a.handle) in self._cache
                ]
        else:
            with self._cache_lock:
                entries = list(self._cache.values())
        
        for entry in entries:
            if not entry:
                continue
                
            for tweet in entry.tweets:
                # Match query nel contenuto
                if query_lower in tweet.content.lower():
                    # Filtra per topic se specificato
                    if topics:
                        if any(t in tweet.topics for t in topics):
                            results.append(tweet)
                    else:
                        results.append(tweet)
        
        return results
    
    def enrich_alert_with_twitter_intel(
        self,
        alert: Dict,
        home_team: str,
        away_team: str,
        league_key: str
    ) -> Dict:
        """
        Arricchisce un alert con intel Twitter rilevanti.
        
        Args:
            alert: Alert da arricchire
            home_team: Nome team casa
            away_team: Nome team trasferta
            league_key: Chiave lega
            
        Returns:
            Alert arricchito con campo 'twitter_intel'
        """
        relevant_tweets = []
        
        # Cerca menzioni dei team
        for team in [home_team, away_team]:
            tweets = self.search_intel(team, league_key)
            for tweet in tweets:
                relevant_tweets.append({
                    "handle": tweet.handle,
                    "content": tweet.content[:200],  # Tronca per brevità
                    "date": tweet.date,
                    "topics": tweet.topics,
                    "relevance": self._calculate_relevance(tweet, team, alert)
                })
        
        # Ordina per rilevanza
        relevant_tweets.sort(
            key=lambda x: {"high": 0, "medium": 1, "low": 2, "none": 3}.get(x["relevance"], 3)
        )
        
        # Aggiungi all'alert
        alert["twitter_intel"] = {
            "tweets": relevant_tweets[:5],  # Max 5 tweet più rilevanti
            "cache_age_minutes": self.cache_age_minutes,
            "cycle_id": self._cycle_id
        }
        
        return alert
    
    def _calculate_relevance(
        self,
        tweet: CachedTweet,
        team: str,
        alert: Dict
    ) -> str:
        """Calcola rilevanza di un tweet per un alert"""
        content_lower = tweet.content.lower()
        team_lower = team.lower()
        
        # HIGH: menziona team + topic critico (injury, lineup)
        if team_lower in content_lower:
            if any(t in tweet.topics for t in ["injury", "lineup", "squad"]):
                return "high"
            return "medium"
        
        # MEDIUM: topic correlato
        if any(t in tweet.topics for t in ["injury", "lineup", "transfer"]):
            return "medium"
        
        # LOW: generico
        return "low"
    
    # ============================================
    # V7.0: TAVILY TWITTER RECOVERY
    # ============================================
    
    def _tavily_recover_tweets(
        self,
        handle: str,
        keywords: Optional[List[str]] = None,
        max_results: int = 5
    ) -> List[CachedTweet]:
        """
        V7.0: Recover tweets via Tavily when Gemini/Nitter fails.
        
        Uses Tavily AI Search to find recent tweets from a specific account.
        Results are normalized to CachedTweet format.
        
        Args:
            handle: Twitter handle (with or without @)
            keywords: Optional keywords to filter results (e.g., ["injury", "lineup"])
            max_results: Maximum number of tweets to recover
            
        Returns:
            List of CachedTweet objects recovered from Tavily
            
        Requirements: 8.1, 8.2
        """
        if not self._tavily or not hasattr(self._tavily, 'is_available') or not self._tavily.is_available():
            logging.debug(f"🐦 Tavily not available for Twitter recovery: {handle}")
            return []
        
        # Normalize handle for consistency
        normalized_handle = self._normalize_handle(handle)
        
        # Check if account is marked as unavailable (cooldown)
        if normalized_handle in self._unavailable_accounts:
            marked_time = self._unavailable_accounts[normalized_handle]
            # 1 hour cooldown before retrying unavailable accounts
            if datetime.now(timezone.utc) - marked_time < timedelta(hours=1):
                logging.debug(f"🐦 Account {handle} in cooldown, skipping Tavily recovery")
                return []
            else:
                # Cooldown expired, remove from unavailable
                del self._unavailable_accounts[normalized_handle]
        
        # Check budget allocation for twitter_recovery
        if _TAVILY_AVAILABLE and _get_budget_manager:
            try:
                budget_manager = _get_budget_manager()
                if not budget_manager.can_call("twitter_recovery"):
                    logging.debug(f"🐦 Tavily budget exhausted for twitter_recovery")
                    return []
            except Exception as e:
                logging.debug(f"🐦 Budget check failed: {e}")
                pass  # Continue without budget check if manager unavailable
        
        # Build Tavily query for Twitter recovery
        if _TavilyQueryBuilder:
            query = _TavilyQueryBuilder.build_twitter_recovery_query(handle, keywords)
        else:
            # Fallback if TavilyQueryBuilder not available
            clean_handle = handle.strip()
            if not clean_handle.startswith("@"):
                clean_handle = f"@{clean_handle}"
            query = f"Twitter {clean_handle} recent tweets"
            if keywords:
                query += f" {' '.join(keywords[:5])}"
        
        if not query:
            return []
        
        logging.info(f"🐦 [TAVILY] Recovering tweets for {handle}...")
        
        try:
            # Search via Tavily
            response = self._tavily.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
                include_answer=True
            )
            
            if not response or not hasattr(response, 'results') or not response.results:
                # No results - mark account as temporarily unavailable
                self._mark_account_unavailable(handle)
                logging.warning(f"🐦 [TAVILY] No results for {handle}, marking unavailable")
                return []
            
            # Record budget usage
            if _TAVILY_AVAILABLE and _get_budget_manager:
                try:
                    budget_manager = _get_budget_manager()
                    budget_manager.record_call("twitter_recovery")
                except Exception as e:
                    logging.debug(f"🐦 Budget recording failed: {e}")
            
            # Normalize Tavily results to CachedTweet format
            recovered_tweets = []
            for result in response.results[:max_results]:
                tweet = self._normalize_tavily_to_tweet(handle, result)
                if tweet:
                    recovered_tweets.append(tweet)
            
            self._tavily_recovery_count += len(recovered_tweets)
            
            logging.info(
                f"🐦 [TAVILY] Recovered {len(recovered_tweets)} tweets for {handle} "
                f"(total recoveries: {self._tavily_recovery_count})"
            )
            
            return recovered_tweets
            
        except Exception as e:
            logging.error(f"🐦 [TAVILY] Error recovering tweets for {handle}: {e}", exc_info=True)
            return []
    
    def _normalize_tavily_to_tweet(
        self,
        handle: str,
        tavily_result: Any
    ) -> Optional[CachedTweet]:
        """
        V7.0: Normalize Tavily search result to CachedTweet format.
        
        Extracts tweet-like content from Tavily results and applies
        freshness decay for older content.
        
        Args:
            handle: Twitter handle
            tavily_result: TavilyResult object from search
            
        Returns:
            CachedTweet or None if normalization fails
            
        Requirements: 8.2, 8.3
        """
        if not tavily_result:
            return None
        
        try:
            # Extract content from Tavily result
            content = getattr(tavily_result, 'content', '') or ""
            title = getattr(tavily_result, 'title', '') or ""
            url = getattr(tavily_result, 'url', '') or ""
            published_date = getattr(tavily_result, 'published_date', '') or ""
            
            # Skip if no meaningful content
            if not content and not title:
                return None
            
            # Combine title and content for tweet-like format
            tweet_content = content if content else title
            
            # Truncate to reasonable tweet length
            if len(tweet_content) > 500:
                tweet_content = tweet_content[:497] + "..."
            
            # Extract topics from content
            topics = self._extract_topics_from_content(tweet_content)
            
            # Apply freshness decay for tweets > 24h old
            freshness_score = self._calculate_freshness_score(published_date)
            
            # Create CachedTweet
            tweet = CachedTweet(
                handle=handle,
                date=published_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                content=tweet_content,
                topics=topics,
                raw_data={
                    "source": "tavily",
                    "url": url,
                    "title": title,
                    "freshness_score": freshness_score,
                    "tavily_score": getattr(tavily_result, 'score', 0.0)
                }
            )
            
            return tweet
            
        except Exception as e:
            logging.debug(f"🐦 Error normalizing Tavily result: {e}")
            return None
    
    def _extract_topics_from_content(self, content: str) -> List[str]:
        """
        Extract betting-relevant topics from content.
        
        Args:
            content: Tweet/article content
            
        Returns:
            List of detected topics
        """
        if not content:
            return []
        
        content_lower = content.lower()
        topics = []
        
        # Topic detection patterns
        topic_patterns = {
            "injury": ["injury", "injured", "out", "sidelined", "ruled out", "doubt", 
                      "infortunio", "lesión", "sakatlık", "kontuzja"],
            "lineup": ["lineup", "starting", "xi", "squad", "team news", "formation",
                      "formazione", "alineación", "kadro", "skład"],
            "transfer": ["transfer", "signing", "loan", "deal", "move",
                        "trasferimento", "fichaje", "transfer"],
            "suspension": ["suspended", "suspension", "ban", "red card", "yellow",
                          "squalifica", "sanción", "ceza"],
            "fitness": ["fitness", "training", "recovery", "return", "back",
                       "allenamento", "entrenamiento", "antrenman"],
        }
        
        for topic, keywords in topic_patterns.items():
            if any(kw in content_lower for kw in keywords):
                topics.append(topic)
        
        return topics
    
    def _calculate_freshness_score(self, published_date: str) -> float:
        """
        V7.0: Calculate freshness score with decay for older content.
        
        Tweets > 24h old get penalized with exponential decay.
        
        Args:
            published_date: Date string (various formats supported)
            
        Returns:
            Freshness score between 0.0 and 1.0
            
        Requirements: 8.3
        """
        if not published_date:
            return 0.5  # Unknown date = medium freshness
        
        try:
            # Try to parse date
            from dateutil import parser as date_parser
            pub_dt = date_parser.parse(published_date)
            
            # Make timezone-aware if needed
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            age_hours = (now - pub_dt).total_seconds() / 3600
            
            # Freshness decay: 1.0 for <6h, decays to 0.3 at 24h, 0.1 at 48h
            if age_hours <= 6:
                return 1.0
            elif age_hours <= 24:
                # Linear decay from 1.0 to 0.5 over 6-24h
                return 1.0 - (age_hours - 6) * (0.5 / 18)
            elif age_hours <= 48:
                # Steeper decay from 0.5 to 0.2 over 24-48h
                return 0.5 - (age_hours - 24) * (0.3 / 24)
            else:
                # Very old content
                return max(0.1, 0.2 - (age_hours - 48) * 0.001)
                
        except Exception as e:
            logging.debug(f"🐦 Error calculating freshness score: {e}")
            return 0.5  # Parse error = medium freshness
    
    def _mark_account_unavailable(self, handle: str) -> None:
        """
        V7.0: Mark account as temporarily unavailable.
        
        When Tavily returns no results for an account, mark it
        to avoid repeated failed queries.
        
        Args:
            handle: Twitter handle to mark
            
        Requirements: 8.4
        """
        normalized_handle = self._normalize_handle(handle)
        self._unavailable_accounts[normalized_handle] = datetime.now(timezone.utc)
        logging.debug(f"🐦 Account {handle} marked as temporarily unavailable")
    
    def recover_failed_accounts(
        self,
        failed_handles: List[str],
        keywords: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        V7.0: Batch recover tweets for accounts that failed Gemini extraction.
        
        Called after refresh_twitter_intel() if some accounts have no data.
        Uses Tavily to attempt recovery for failed accounts.
        
        Args:
            failed_handles: List of handles that failed Gemini extraction
            keywords: Optional keywords to filter results
            
        Returns:
            Dict with recovery statistics
            
        Requirements: 8.1
        """
        if not self._tavily or not hasattr(self._tavily, 'is_available') or not self._tavily.is_available():
            return {"recovered": 0, "failed": len(failed_handles), "skipped": 0}
        
        stats = {
            "recovered": 0,
            "failed": 0,
            "skipped": 0,
            "tweets_recovered": 0
        }
        
        for handle in failed_handles:
            # Skip if already in cache with data
            handle_key = self._normalize_handle(handle)
            with self._cache_lock:
                if handle_key in self._cache and self._cache[handle_key].tweets:
                    stats["skipped"] += 1
                    continue
            
            # Attempt Tavily recovery
            tweets = self._tavily_recover_tweets(handle, keywords)
            
            if tweets:
                # Find account info
                account_info = self._find_account_info(handle)
                
                # Create/update cache entry
                entry = TwitterIntelCacheEntry(
                    handle=handle,
                    account_name=account_info.name if account_info else handle,
                    league_focus=account_info.focus if account_info else "unknown",
                    tweets=tweets,
                    last_refresh=datetime.now(timezone.utc),
                    extraction_success=True,
                    error_message=None
                )
                
                with self._cache_lock:
                    self._cache[handle_key] = entry
                stats["recovered"] += 1
                stats["tweets_recovered"] += len(tweets)
            else:
                stats["failed"] += 1
        
        if stats["recovered"] > 0:
            logging.info(
                f"🐦 [TAVILY] Recovery complete: {stats['recovered']} accounts, "
                f"{stats['tweets_recovered']} tweets recovered"
            )
        
        return stats
    
    def get_cache_summary(self) -> Dict[str, Any]:
        """
        Ottiene un riepilogo dello stato della cache.
        
        Returns:
            Dict con statistiche cache
        """
        with self._cache_lock:
            total_tweets = sum(len(e.tweets) for e in self._cache.values())
            accounts_with_data = sum(1 for e in self._cache.values() if e.tweets)
            
            # V7.0: Include Tavily recovery stats
            tavily_tweets = sum(
                1 for e in self._cache.values() 
                for t in e.tweets 
                if t.raw_data.get("source") == "tavily"
            )
            
            return {
                "is_fresh": self.is_fresh,
                "cache_age_minutes": self.cache_age_minutes,
                "cycle_id": self._cycle_id,
                "total_accounts": len(self._cache),
                "accounts_with_data": accounts_with_data,
                "total_tweets": total_tweets,
                "tavily_recovered_tweets": tavily_tweets,
                "tavily_recovery_count": self._tavily_recovery_count,
                "unavailable_accounts": len(self._unavailable_accounts),
                "last_refresh": self._last_full_refresh.isoformat() if self._last_full_refresh else None
            }
    
    def clear_cache(self) -> None:
        """Svuota la cache (chiamare a fine ciclo se necessario)"""
        with self._cache_lock:
            self._cache.clear()
        self._last_full_refresh = None
        self._cycle_id = None
        logging.info("🐦 Twitter Intel cache cleared")


# ============================================
# SINGLETON INSTANCE
# ============================================

_twitter_intel_cache: Optional[TwitterIntelCache] = None
_twitter_intel_cache_lock: Optional[threading.Lock] = None  # Lazy initialization


def _get_cache_lock() -> threading.Lock:
    """Get or create the cache lock (lazy initialization)."""
    global _twitter_intel_cache_lock
    if _twitter_intel_cache_lock is None:
        _twitter_intel_cache_lock = threading.Lock()
    return _twitter_intel_cache_lock


def get_twitter_intel_cache() -> TwitterIntelCache:
    """
    Ottiene l'istanza singleton della cache.
    
    V7.1: Thread-safe con double-check locking pattern.
    
    Returns:
        TwitterIntelCache instance
    """
    global _twitter_intel_cache
    
    # Fast path: instance already exists
    if _twitter_intel_cache is not None:
        return _twitter_intel_cache
    
    # Slow path: need to create instance with lock
    lock = _get_cache_lock()
    with lock:
        # Double-check inside lock
        if _twitter_intel_cache is None:
            _twitter_intel_cache = TwitterIntelCache()
    
    return _twitter_intel_cache


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    import asyncio
    
    async def test_cache():
        print("=" * 60)
        print("🐦 TWITTER INTEL CACHE - TEST")
        print("=" * 60)
        
        cache = get_twitter_intel_cache()
        
        # Test senza Gemini (mock)
        print("\n📊 Cache Summary (before refresh):")
        print(json.dumps(cache.get_cache_summary(), indent=2))
        
        # Simula alcuni dati
        cache._cache["@rudygaletti"] = TwitterIntelCacheEntry(
            handle="@RudyGaletti",
            account_name="Rudy Galetti",
            league_focus="Turkey Super Lig",
            tweets=[
                CachedTweet(
                    handle="@RudyGaletti",
                    date="2026-01-01",
                    content="Galatasaray: Icardi out for 2 weeks with muscle injury",
                    topics=["injury"]
                )
            ],
            last_refresh=datetime.now(),
            extraction_success=True
        )
        
        cache._last_full_refresh = datetime.now()
        cache._cycle_id = "test_cycle"
        
        print("\n📊 Cache Summary (after mock data):")
        print(json.dumps(cache.get_cache_summary(), indent=2))
        
        # Test search
        print("\n🔍 Search 'Galatasaray':")
        results = cache.search_intel("Galatasaray")
        for r in results:
            print(f"   [{r.handle}] {r.content[:50]}...")
        
        print("\n✅ Test complete")
    
    asyncio.run(test_cache())
