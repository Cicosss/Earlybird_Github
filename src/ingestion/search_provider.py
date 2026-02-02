"""
EarlyBird Search Provider - Brave Primary with DDG/Serper/Mediastack Fallback

Search Priority (V4.4):
1. Brave Search API (Quality + Stability, 2000/month quota)
2. DuckDuckGo (Python lib, free, no API key, no Docker required)
3. Serper (paid API, fallback)
4. Mediastack (FREE unlimited, emergency last-resort)

Provides robust search without any Docker dependencies.

V4.4: 
- Migrated to centralized HTTP client with fingerprint rotation
- Added Mediastack as 4th fallback (free unlimited tier)

Phase 1 Critical Fix: Added URL encoding for non-ASCII characters in search queries
"""
import html
import logging
import os
import random
from typing import List, Dict, Optional
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Import centralized HTTP client
from src.utils.http_client import get_http_client

# ============================================
# CONFIGURATION
# ============================================
DDGS_TIMEOUT = 10

# Anti-Ban Jitter: Random delay between requests to avoid pattern detection
# V7.6: Reduced from 3-6s to 1-2s for better performance (saves 20-40s per 10 requests)
# Actual rate limiting is handled by centralized HTTP client (see src/utils/http_client.py)
JITTER_MIN = 1.0  # Minimum delay in seconds (documentation only - see http_client.py)
JITTER_MAX = 2.0  # Maximum delay in seconds (documentation only - see http_client.py)

# Sport Filter: Exclude basketball/other sports to avoid "Wrong Sport" hallucinations
# Also excludes Women's Football to avoid false positives on teams with shared names
SPORT_EXCLUSION_TERMS = " -basket -basketball -euroleague -nba -pallacanestro -baloncesto -koszykówka -basketbol -nfl -american football -touchdown -women -woman -ladies -feminine -femminile -femenino -kobiet -kadın -bayan -wsl -liga f -handball -volleyball -rugby -futsal"

# ============================================
# LOCALIZED SPORT KEYWORDS BY LEAGUE
# ============================================
# Appends native "football" keyword to queries to filter out basketball/other sports
LEAGUE_SPORT_KEYWORDS = {
    # Turkey
    "soccer_turkey_super_league": "futbol",
    "soccer_turkey_1_lig": "futbol",
    # Spain
    "soccer_spain_la_liga": "fútbol",
    "soccer_spain_segunda_division": "fútbol",
    # Portugal
    "soccer_portugal_primeira_liga": "futebol",
    # Brazil
    "soccer_brazil_campeonato": "futebol",
    "soccer_brazil_serie_b": "futebol",
    # Argentina
    "soccer_argentina_primera_division": "fútbol",
    # Mexico
    "soccer_mexico_ligamx": "fútbol",
    # Colombia
    "soccer_colombia_primera_a": "fútbol",
    # Greece
    "soccer_greece_super_league": "ποδόσφαιρο",
    # Poland
    "soccer_poland_ekstraklasa": "piłka nożna",
    # Romania
    "soccer_romania_liga_1": "fotbal",
    # Italy
    "soccer_italy_serie_a": "calcio",
    "soccer_italy_serie_b": "calcio",
    # France
    "soccer_france_ligue_one": "football",
    "soccer_france_ligue_two": "football",
    # Germany
    "soccer_germany_bundesliga": "fußball",
    "soccer_germany_bundesliga2": "fußball",
    # Netherlands
    "soccer_netherlands_eredivisie": "voetbal",
    # Belgium
    "soccer_belgium_first_div": "voetbal",
    # USA/MLS
    "soccer_usa_mls": "soccer",
    # Australia
    "soccer_australia_aleague": "football",
    # Japan
    "soccer_japan_j_league": "サッカー",
    # Korea
    "soccer_korea_kleague1": "축구",
    # China
    "soccer_china_superleague": "足球",
    # Saudi
    "soccer_saudi_professional_league": "كرة القدم",
    # Norway
    "soccer_norway_eliteserien": "fotball",
    # Austria
    "soccer_austria_bundesliga": "fußball",
    # Switzerland
    "soccer_switzerland_superleague": "fussball",
    # Scotland
    "soccer_spl": "football",
}

# Default keyword for unlisted leagues
DEFAULT_SPORT_KEYWORD = "football"

# ============================================
# INSIDER DOMAINS BY LEAGUE (V4.3)
# ============================================
# High-quality local sources for each league.
# Used with site: operator for targeted searches.
# 3 domains per league for focused dorking.

LEAGUE_DOMAINS = {
    # ==========================================
    # TIER 1 - GOLD LIST
    # ==========================================
    # TURKEY (news + forum)
    "soccer_turkey_super_league": [
        "ajansspor.com", "fotospor.com", "turkish-football.com", "gscimbom.com"
    ],
    # ARGENTINA (news + forums)
    "soccer_argentina_primera_division": [
        "dobleamarilla.com.ar", "mundoalbiceleste.com", "turiver.com", "promiedos.com.ar"
    ],
    # MEXICO (news + forum)
    "soccer_mexico_ligamx": [
        "futboltotal.com.mx", "soyfutbol.com", "fmfstateofmind.com", "bigsoccer.com"
    ],
    # GREECE (news + forum)
    "soccer_greece_super_league": [
        "agonasport.com", "sdna.gr", "sportdog.gr", "paokmania.gr"
    ],
    # SCOTLAND (news + forum)
    "soccer_spl": [
        "dailyrecord.co.uk", "thescottishsun.co.uk", "scottishfootballnews.com", "pieandbovril.com"
    ],
    # AUSTRALIA
    "soccer_australia_aleague": [
        "theroar.com.au", "ftbl.com.au", "keepup.com.au"
    ],
    # FRANCE (news + forums)
    "soccer_france_ligue_one": [
        "maxifoot.fr", "lequipe.fr", "culturepsg.com", "lephoceen.fr"
    ],
    # PORTUGAL
    "soccer_portugal_primeira_liga": [
        "ojogo.pt", "abola.pt", "maisfutebol.iol.pt"
    ],
    # SWITZERLAND
    "soccer_switzerland_superleague": [
        "blick.ch", "20min.ch", "transfermarkt.ch"
    ],
    
    # ==========================================
    # TIER 2 - ROTATION
    # ==========================================
    # NORWAY (news + forum)
    "soccer_norway_eliteserien": [
        "nettavisen.no", "tv2.no", "vg.no", "vgd.no"
    ],
    # POLAND (forums + news) - Polish football is forum-centric
    "soccer_poland_ekstraklasa": [
        "swiatpilki.com",           # Main Polish football forum
        "weszlo.com",               # Major news site
        "meczyki.pl",               # News aggregator
        "90minut.pl",               # Historic forum + news
        "ekstraklasakibice.fora.pl" # Ekstraklasa-focused forum
    ],
    # BELGIUM
    "soccer_belgium_first_div": [
        "voetbalkrant.com", "walfoot.be", "sporza.be"
    ],
    # AUSTRIA (news + forum)
    "soccer_austria_bundesliga": [
        "abseits.at", "laola1.at", "ligaportal.at", "austriansoccerboard.at"
    ],
    # NETHERLANDS (news + forum)
    "soccer_netherlands_eredivisie": [
        "fcupdate.nl", "voetbalprimeur.nl", "vi.nl", "voetbalzone.nl"
    ],
    # CHINA (news + forum)
    "soccer_china_superleague": [
        "dongqiudi.com", "wildeastfootball.net", "sports.sina.com.cn", "bbs.hupu.com"
    ],
    # JAPAN (news + forum)
    "soccer_japan_j_league": [
        "gekisaka.jp", "soccerdigestweb.com", "football-zone.net", "wc2014.5ch.net"
    ],
    # BRAZIL SERIE B (news + forum)
    "soccer_brazil_serie_b": [
        "ge.globo.com", "futebolinterior.com.br", "sambafoot.com", "hardmob.com.br"
    ],
}

# Import Brave Search Provider
try:
    from src.ingestion.brave_provider import get_brave_provider, BraveSearchProvider
    _BRAVE_AVAILABLE = True
except ImportError:
    _BRAVE_AVAILABLE = False
    logger.debug("Brave provider not available")

# Import DuckDuckGo Search (renamed package: ddgs)
try:
    from ddgs import DDGS
    _DDGS_AVAILABLE = True
    logger.info("✅ DuckDuckGo Search library available")
except ImportError:
    _DDGS_AVAILABLE = False
    logger.warning("⚠️ ddgs not installed. Run: pip install ddgs")

# Try to import Serper config
try:
    from config.settings import SERPER_API_KEY
except ImportError:
    SERPER_API_KEY = None

# Import Mediastack Provider (V4.4 - emergency fallback)
try:
    from src.ingestion.mediastack_provider import get_mediastack_provider
    _MEDIASTACK_AVAILABLE = True
except ImportError:
    _MEDIASTACK_AVAILABLE = False
    logger.debug("Mediastack provider not available")


class SearchProvider:
    """
    Search Provider with Brave as primary engine (V4.5).
    
    Layer 0: Brave Search API - Quality + Stability (2000/month)
    Layer 1: DuckDuckGo - Free, no API key needed, no Docker
    Layer 2: Mediastack - FREE unlimited, emergency last-resort
    
    V4.5: Removed Serper from fallback chain (HTTP 400 due to long queries).
    
    V4.4: Uses centralized HTTP client with fingerprint rotation.
    """
    
    def __init__(self):
        self._ddgs_available = _DDGS_AVAILABLE
        self._serper_exhausted = False
        self._last_request_time = 0
        self._brave = get_brave_provider() if _BRAVE_AVAILABLE else None
        self._mediastack = get_mediastack_provider() if _MEDIASTACK_AVAILABLE else None
        self._http_client = get_http_client()  # Centralized HTTP client
        
        if self._brave and self._brave.is_available():
            logger.info("🔍 SearchProvider initialized (Brave Primary + DDG/Serper/Mediastack Fallback)")
        else:
            logger.info("🔍 SearchProvider initialized (DDG Primary + Serper Fallback)")
    
    def _apply_rate_limit(self, rate_limit_key: str = "duckduckgo"):
        """Apply rate limiting via centralized HTTP client.
        
        Delegates to HTTP client's rate limiter for consistent behavior.
        """
        # Rate limiting is now handled by HTTP client
        # This method exists for backward compatibility
        pass
    
    # ============================================
    # LAYER 0: BRAVE SEARCH (Primary - Quality + Stability)
    # ============================================
    def _search_brave(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search using Brave Search API (primary engine V3.6)."""
        if not self._brave or not self._brave.is_available():
            return []
        
        try:
            results = self._brave.search_news(query, num_results)
            # Normalize field names for compatibility
            for r in results:
                if 'url' in r and 'link' not in r:
                    r['link'] = r['url']
            return results
        except ValueError as e:
            logger.warning(f"⚠️ Brave Search not configured: {e}")
            return []
        except Exception as e:
            logger.warning(f"⚠️ Brave Search failed: {e}")
            return []
    
    # ============================================
    # LAYER 1: DUCKDUCKGO (Secondary - Free Fallback)
    # ============================================
    def _search_duckduckgo(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search using DuckDuckGo Python library (secondary engine).
        
        Includes specific error handling for common failure modes.
        Uses timelimit="w" to filter results to past week only.
        Rate limiting applied via centralized HTTP client.
        """
        if not self._ddgs_available:
            logger.warning("Libreria DuckDuckGo non disponibile")
            return []
        
        # Apply rate limiting before DDG call (DDG uses requests internally)
        rate_limiter = self._http_client._get_rate_limiter("duckduckgo")
        rate_limiter.wait_sync()
        
        # DIAGNOSTIC: Log query complexity before making request
        query_length = len(query)
        # SOLUTION B: Using reliable engines only (duckduckgo, brave, google)
        # Grokipedia disabled due to timeout issues with complex queries
        # NOTE: "bing" engine not available in DDGS library
        logger.debug(f"[DDGS-DIAG] Starting DuckDuckGo search - Query length: {query_length} chars, Max results: {num_results}, Timeout: {DDGS_TIMEOUT}s, Engines: duckduckgo,brave,google")
        if query_length > 200:
            logger.debug(f"[DDGS-DIAG] Long query detected (first 100 chars): {query[:100]}...")
        
        try:
            # DIAGNOSTIC: Pass timeout parameter to DDGS constructor
            ddgs = DDGS(timeout=DDGS_TIMEOUT)
            # timelimit="w" filters to past week - prevents stale news
            # SOLUTION B: Disable Grokipedia engine (unreliable for complex queries)
            # Use only reliable engines: duckduckgo, brave, google
            # NOTE: "bing" engine is not available in DDGS library
            raw_results = ddgs.text(
                query, 
                max_results=num_results, 
                timelimit="w",
                backend="duckduckgo,brave,google"  # Skip grokipedia (bing not available)
            )
            
            results = []
            for item in raw_results:
                # Clean and truncate snippet to save tokens (unescape HTML + limit to 350 chars)
                raw_snippet = item.get("body", "")
                clean_snippet = html.unescape(raw_snippet)[:350] if raw_snippet else ""
                
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("href", ""),
                    "url": item.get("href", ""),  # Alias for compatibility
                    "snippet": clean_snippet,
                    "summary": clean_snippet,  # Analyzer compatibility
                    "source": "duckduckgo",
                    "date": "",
                })
            
            if results:
                logger.debug(f"[DuckDuckGo] Trovati {len(results)} risultati")
            return results
            
        except Exception as e:
            error_msg = str(e).lower()
            error_type = type(e).__name__
            
            # DIAGNOSTIC: Enhanced error logging with query context
            logger.error(f"[DDGS-ERROR] Search failed - Error type: {error_type}, Query length: {query_length}, Error: {e}")
            
            if "ratelimit" in error_msg or "rate" in error_msg or "429" in error_msg:
                logger.warning(f"⚠️ DuckDuckGo rate limit raggiunto: {e}")
                # Trigger fingerprint rotation on rate limit
                self._http_client._fingerprint.force_rotate()
            elif "403" in error_msg or "forbidden" in error_msg:
                logger.warning(f"⚠️ DuckDuckGo accesso negato (possibile blocco IP): {e}")
                self._http_client._fingerprint.force_rotate()
            elif "timeout" in error_msg:
                logger.warning(f"⚠️ DuckDuckGo timeout - servizio lento (query length: {query_length} chars)")
            elif "connection" in error_msg:
                logger.warning(f"⚠️ DuckDuckGo errore connessione: {e}")
            else:
                logger.warning(f"⚠️ DuckDuckGo errore ricerca: {e}")
            return []
    
    # ============================================
    # LAYER 2: SERPER (DISABLED - queries too long cause HTTP 400)
    # ============================================
    def _search_serper(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search using Serper API (paid fallback).
        
        V4.5: DISABLED - Serper has a ~2048 char limit and our queries with
        sport exclusions + site dorking easily exceed 500+ chars, causing HTTP 400.
        Keeping the method for potential future use with shorter queries.
        
        Uses centralized HTTP client with rate limiting and retry logic.
        """
        # V4.5: Serper disabled - queries too long cause HTTP 400
        # The sport exclusion terms + site dorking make queries 500+ chars
        # which exceeds Serper's limit. Mediastack is a better fallback.
        logger.debug("⚠️ Serper disabled (query length issues)")
        return []
    
    # ============================================
    # LAYER 3: MEDIASTACK (FREE Unlimited Emergency Fallback)
    # ============================================
    def _search_mediastack(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search using Mediastack API (free unlimited fallback).
        
        Last-resort fallback when Brave, DDG, and Serper all fail.
        Free tier has unlimited requests but lower quality results.
        
        Args:
            query: Search query string
            num_results: Maximum results to return
            
        Returns:
            List of search results
        """
        if not self._mediastack or not self._mediastack.is_available():
            return []
        
        try:
            results = self._mediastack.search_news(query, limit=num_results)
            # Normalize field names for compatibility
            for r in results:
                if 'url' in r and 'link' not in r:
                    r['link'] = r['url']
            return results
        except ValueError as e:
            logger.warning(f"⚠️ Mediastack not configured: {e}")
            return []
        except Exception as e:
            logger.warning(f"⚠️ Mediastack search failed: {e}")
            return []
    
    def _build_insider_query(self, team: str, keywords: str, league_key: str = None) -> str:
        """
        Build search query with insider domain dorking for Elite leagues.
        
        If league_key is in LEAGUE_DOMAINS, restricts search to those domains
        using site: operator for higher quality results.
        
        Phase 1 Critical Fix: URL-encode team names and keywords to handle non-ASCII
        characters (e.g., Turkish "ş", Polish "ą", Greek "α").
        
        Args:
            team: Team name
            keywords: Search keywords (e.g., "injury OR lineup")
            league_key: League key for domain lookup
            
        Returns:
            Formatted query string with site: dorking if applicable
        """
        # Phase 1 Critical Fix: URL-encode team name to handle special characters
        # This fixes search failures for non-English team names like "Beşiktaş", "Lech Poznań"
        encoded_team = quote(team, safe='')
        
        # Phase 1 Critical Fix: URL-encode keywords to handle special characters
        encoded_keywords = quote(keywords, safe=' ')
        
        # Base query with URL-encoded team and keywords
        base_query = f'"{encoded_team}" {encoded_keywords}'
        
        # Add insider domain dorking if league has configured domains
        if league_key and league_key in LEAGUE_DOMAINS:
            domains = LEAGUE_DOMAINS[league_key]
            # Phase 1 Critical Fix: URL-encode domain names as well
            site_dork = " OR ".join([f"site:{quote(d, safe='')}" for d in domains])
            base_query = f'{base_query} ({site_dork})'
            logger.debug(f"🎯 Insider dorking for {league_key}: {domains}")
        
        # Add sport exclusions (these are ASCII, no encoding needed)
        base_query = f'{base_query}{SPORT_EXCLUSION_TERMS}'
        
        return base_query
    
    def search_insider_news(
        self,
        team: str,
        league_key: str,
        keywords: str = "injury OR lineup OR squad OR team news",
        num_results: int = 5
    ) -> List[Dict]:
        """
        Search insider sources for a specific team and league.
        
        Uses curated domain list for higher quality results.
        Falls back to general search if no domains configured.
        
        Args:
            team: Team name
            league_key: League key (e.g., "soccer_turkey_super_league")
            keywords: Search keywords
            num_results: Maximum results
            
        Returns:
            List of search results
        """
        query = self._build_insider_query(team, keywords, league_key)
        
        if league_key in LEAGUE_DOMAINS:
            logger.info(f"🔍 [INSIDER] Searching {team} on {LEAGUE_DOMAINS[league_key]}")
        
        return self.search(query, num_results)
    
    # ============================================
    # MAIN SEARCH METHOD (Brave -> DDG -> Mediastack)
    # ============================================
    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """
        Search with automatic failover.
        
        Priority: Brave -> DuckDuckGo -> Mediastack
        
        V4.5: Removed Serper from chain (HTTP 400 due to long queries with
        sport exclusions + site dorking exceeding Serper's ~2048 char limit).
        
        Rate limiting is handled by centralized HTTP client.
        Fingerprint rotation on 403/429 errors.
        """
        # Guard: Skip empty or too short queries
        if not query or len(query.strip()) < 3:
            logger.warning(f"⚠️ Empty or too short query skipped: '{query}'")
            return []
        
        # Layer 0: Brave Search (Primary - Quality + Stability)
        try:
            if self._brave and self._brave.is_available():
                results = self._search_brave(query, num_results)
                if results:
                    return results
        except Exception as e:
            logger.warning(f"⚠️ Brave Search failed: {e}")
        
        # Layer 1: DuckDuckGo (Free Fallback)
        # Rate limiting handled by HTTP client via rate_limit_key="duckduckgo"
        try:
            results = self._search_duckduckgo(query, num_results)
            if results:
                return results
        except Exception as e:
            error_msg = str(e).lower()
            if "ratelimit" in error_msg or "rate" in error_msg or "429" in error_msg:
                logger.warning(f"⚠️ Rate Limit DuckDuckGo rilevato. Fallback a Mediastack.")
            else:
                logger.warning(f"DuckDuckGo error: {e}")
        
        # Layer 2: Mediastack (FREE unlimited emergency fallback)
        # V4.5: Serper removed - Mediastack is now the direct fallback after DDG
        results = self._search_mediastack(query, num_results)
        if results:
            logger.info(f"🆘 Mediastack emergency fallback returned {len(results)} results")
            return results
        
        logger.warning(f"All search backends failed for: {query[:50]}...")
        return []
    
    def search_news(self, query: str, num_results: int = 5, league_key: str = None) -> List[Dict]:
        """Search specifically for news (football only, excludes basketball).
        
        If league_key is provided and has insider domains configured,
        uses site: dorking for higher quality results.
        
        Args:
            query: Search query string
            num_results: Maximum number of results
            league_key: Optional league key for localized sport keyword and insider domains
        """
        # Add localized sport keyword if league_key provided
        sport_keyword = DEFAULT_SPORT_KEYWORD
        if league_key and league_key in LEAGUE_SPORT_KEYWORDS:
            sport_keyword = LEAGUE_SPORT_KEYWORDS[league_key]
        
        # Build query with insider domain dorking if available
        if league_key and league_key in LEAGUE_DOMAINS:
            domains = LEAGUE_DOMAINS[league_key]
            site_dork = " OR ".join([f"site:{d}" for d in domains])
            news_query = f"{query} {sport_keyword} ({site_dork}){SPORT_EXCLUSION_TERMS}"
            logger.debug(f"🎯 News search with insider domains: {domains}")
        else:
            news_query = f"{query} {sport_keyword} news OR update OR latest{SPORT_EXCLUSION_TERMS}"
        
        return self.search(news_query, num_results)
    
    def search_twitter(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search Twitter/X content.
        
        DEPRECATED V7.0: This method returns 0 results because Twitter/X
        blocked search engine indexing in mid-2023. Use TwitterIntelCache
        instead for Twitter data.
        
        Kept for backward compatibility but will always return empty results.
        """
        logger.warning(
            "⚠️ search_twitter() is DEPRECATED - Twitter blocks indexing. "
            "Use TwitterIntelCache instead."
        )
        twitter_query = f"{query} site:twitter.com OR site:x.com"
        return self.search(twitter_query, num_results)
    
    def search_local_news(
        self,
        team_name: str,
        domains: List[str],
        keywords: List[str],
        num_results: int = 5,
        league_key: str = None
    ) -> List[Dict]:
        """Search local news sources for team information (football only).
        
        Args:
            team_name: Team name to search (can be empty for general radar scans)
            domains: List of domains to search
            keywords: List of keywords to include
            num_results: Maximum number of results
            league_key: Optional league key for localized sport keyword
        """
        # Build query parts
        query_parts = []
        
        # Add team name if provided
        if team_name and team_name.strip():
            query_parts.append(f'"{team_name}"')
        
        # Add domain filter
        if domains:
            site_filter = " OR ".join([f"site:{d}" for d in domains[:3]])
            query_parts.append(f'({site_filter})')
        
        # Add keywords
        if keywords:
            kw_filter = " OR ".join(keywords[:3])
            query_parts.append(f'({kw_filter})')
        
        # Combine parts
        query = " ".join(query_parts)
        
        # Guard: Skip if query is empty or too short
        if not query or len(query.strip()) < 5:
            logger.warning(f"⚠️ Skipping empty/short query in search_local_news")
            return []
        
        # Add localized sport keyword
        sport_keyword = DEFAULT_SPORT_KEYWORD
        if league_key and league_key in LEAGUE_SPORT_KEYWORDS:
            sport_keyword = LEAGUE_SPORT_KEYWORDS[league_key]
        query = f'{query} {sport_keyword}'
        
        # Add sport exclusion to filter out basketball news
        query = f'{query}{SPORT_EXCLUSION_TERMS}'
        
        return self.search(query, num_results)
    
    def is_available(self) -> bool:
        """Check if any search backend is available.
        
        V4.5: Removed Serper from availability check (disabled due to query length issues).
        """
        brave_ok = self._brave and self._brave.is_available() if self._brave else False
        mediastack_ok = self._mediastack and self._mediastack.is_available() if self._mediastack else False
        return brave_ok or self._ddgs_available or mediastack_ok


# ============================================
# SINGLETON & CONVENIENCE FUNCTIONS
# ============================================
_provider_instance: Optional[SearchProvider] = None


def get_search_provider() -> SearchProvider:
    """Get or create the singleton SearchProvider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = SearchProvider()
    return _provider_instance


def search_news(query: str, num_results: int = 5, league_key: str = None) -> List[Dict]:
    """Convenience function for news search."""
    return get_search_provider().search_news(query, num_results, league_key=league_key)


def search_twitter(query: str, num_results: int = 5) -> List[Dict]:
    """Convenience function for Twitter search.
    
    DEPRECATED V7.0: Returns 0 results - Twitter blocks indexing.
    Use TwitterIntelCache instead.
    """
    return get_search_provider().search_twitter(query, num_results)


def search_local(team: str, domains: List[str], keywords: List[str], league_key: str = None) -> List[Dict]:
    """Convenience function for local news search."""
    return get_search_provider().search_local_news(team, domains, keywords, league_key=league_key)


def search_insider(team: str, league_key: str, keywords: str = "injury OR lineup OR squad") -> List[Dict]:
    """Convenience function for insider domain search."""
    return get_search_provider().search_insider_news(team, league_key, keywords)



