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
import requests
import requests.exceptions
import urllib.parse
import logging
import unicodedata
import time
import functools
import random
from difflib import SequenceMatcher, get_close_matches
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

# Try to import thefuzz for better fuzzy matching
try:
    from thefuzz import fuzz as thefuzz_fuzz
    _THEFUZZ_AVAILABLE = True
except ImportError:
    _THEFUZZ_AVAILABLE = False
    thefuzz_fuzz = None

# Logger must be defined BEFORE any code that uses it
logger = logging.getLogger(__name__)

# V4.3: Smart Cache with dynamic TTL
try:
    from src.utils.smart_cache import (
        get_team_cache,
        get_match_cache,
        get_search_cache,
        log_cache_stats
    )
    _SMART_CACHE_AVAILABLE = True
except ImportError:
    _SMART_CACHE_AVAILABLE = False
    logger.warning("⚠️ Smart Cache not available - using no cache")

# V5.2: Import team mapping at top-level for performance
# (lazy import inside functions was causing repeated import overhead)
try:
    from src.ingestion.fotmob_team_mapping import get_fotmob_team_id
    _TEAM_MAPPING_AVAILABLE = True
except ImportError:
    _TEAM_MAPPING_AVAILABLE = False
    get_fotmob_team_id = None
    logger.warning("⚠️ FotMob team mapping not available - using dynamic search only")

# ============================================
# RATE LIMITING & CACHING CONFIGURATION
# ============================================
FOTMOB_MIN_REQUEST_INTERVAL = 1.0  # Minimum seconds between requests
FOTMOB_REQUEST_TIMEOUT = 15  # Timeout in seconds
FOTMOB_MAX_RETRIES = 3  # Max retries for transient errors

# V6.1: Thread-safe rate limiting for VPS multi-thread scenarios
import threading
_fotmob_rate_limit_lock = threading.Lock()
_last_fotmob_request_time = 0.0

# ============================================
# USER-AGENT ROTATION (Anti-Bot Evasion)
# ============================================
# Modern browser User-Agents (updated Dec 2024)
# Rotate to avoid fingerprinting and WAF blocks
USER_AGENTS = [
    # Chrome 131 (Dec 2024) - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 131 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox 133 (Dec 2024) - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Firefox 133 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Edge 131 (Dec 2024)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Safari 17.2 (Dec 2024)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Chrome 131 - Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Get a random User-Agent from the rotation pool."""
    return random.choice(USER_AGENTS)


def normalize_unicode(text: str) -> str:
    """
    Normalize unicode characters to ASCII equivalents.
    Converts: Ħamrun -> Hamrun, Malmö -> Malmo, etc.
    
    Args:
        text: Input string with potential unicode characters
        
    Returns:
        ASCII-normalized string
    """
    if not text:
        return text
    
    # Manual replacements for characters that don't decompose well
    replacements = {
        'Ħ': 'H', 'ħ': 'h',  # Maltese H-bar
        'Ł': 'L', 'ł': 'l',  # Polish L-stroke
        'Đ': 'D', 'đ': 'd',  # Croatian D-stroke
        'Ø': 'O', 'ø': 'o',  # Danish/Norwegian O-slash
        'Æ': 'AE', 'æ': 'ae',  # Ligature
        'Œ': 'OE', 'œ': 'oe',  # Ligature
        'ß': 'ss',  # German sharp S
        'Þ': 'Th', 'þ': 'th',  # Icelandic thorn
        'Ð': 'D', 'ð': 'd',  # Icelandic eth
    }
    
    result = text
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)
    
    # NFKD normalization decomposes characters (e.g., ö -> o + combining mark)
    # Then encode to ASCII ignoring non-ASCII chars, decode back to string
    normalized = unicodedata.normalize('NFKD', result)
    ascii_text = normalized.encode('ASCII', 'ignore').decode('utf-8')
    return ascii_text.strip()


def fuzzy_match_team(search_name: str, candidates: List[str], threshold: float = 0.6) -> Optional[str]:
    """
    Find best fuzzy match for a team name.
    
    Strategies:
    1. Exact match (case-insensitive)
    2. First word match (e.g., "Persija" matches "Persija Jakarta")
    3. Token overlap (e.g., "FC Seoul" matches "Seoul FC")
    4. Token set ratio via thefuzz (handles "Man Utd" vs "Manchester United")
    5. Sequence similarity (difflib fallback)
    
    Args:
        search_name: Team name to find
        candidates: List of possible team names
        threshold: Minimum similarity score (0-1)
        
    Returns:
        Best matching candidate or None
    """
    if not candidates:
        return None
    
    # Safety: handle None or empty search_name
    if not search_name:
        return None
    
    search_lower = search_name.lower().strip()
    search_tokens = set(search_lower.split())
    search_first = search_lower.split()[0] if search_lower else ""
    
    best_match = None
    best_score = 0
    
    for candidate in candidates:
        # Safety: skip None/empty candidates
        if not candidate:
            continue
            
        cand_lower = candidate.lower().strip()
        cand_tokens = set(cand_lower.split())
        
        # Strategy 1: Exact match
        if search_lower == cand_lower:
            return candidate
        
        # Strategy 2: First word match (common for Asian/South American teams)
        cand_first = cand_lower.split()[0] if cand_lower else ""
        if search_first and cand_first and search_first == cand_first and len(search_first) >= 4:
            return candidate
        
        # Strategy 3: Token overlap (handles "FC X" vs "X FC")
        overlap = len(search_tokens & cand_tokens)
        if overlap >= 1 and overlap >= len(search_tokens) * 0.5:
            token_score = overlap / max(len(search_tokens), len(cand_tokens))
            if token_score > best_score:
                best_score = token_score
                best_match = candidate
        
        # Strategy 4: Token set ratio via thefuzz (handles abbreviations like "Man Utd")
        if _THEFUZZ_AVAILABLE and thefuzz_fuzz is not None:
            try:
                # token_set_ratio handles word order and partial matches better
                # "Man Utd" vs "Manchester United" → ~70% instead of ~48%
                fuzz_score = thefuzz_fuzz.token_set_ratio(search_lower, cand_lower) / 100.0
                if fuzz_score > best_score:
                    best_score = fuzz_score
                    best_match = candidate
            except Exception as e:
                # Fallback to difflib if thefuzz fails
                logger.debug(f"thefuzz matching failed, using difflib fallback: {e}")
        
        # Strategy 5: Sequence similarity (fallback)
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
    
    # Base headers (User-Agent rotated per-request)
    BASE_HEADERS = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.fotmob.com/',
        'Origin': 'https://www.fotmob.com'
    }
    
    # Prefixes to strip for better matching (case-insensitive)
    # Expanded list to cover German, Croatian, Dutch, Norwegian clubs
    PREFIXES_TO_STRIP = [
        # Standard
        "FC", "AS", "AC", "SC", "SV", "SK", "FK", "IF", "BK", "CF", "CD",
        # German
        "FSV", "TSG", "VfB", "VfL", "SpVgg", "SG", "TuS", "SSV",
        # Croatian/Balkan
        "HNK", "HSK", "HŠK", "NK", "GNK", "RNK",
        # Dutch/Belgian
        "KAA", "KV", "KRC", "KSC", "KVC", "KFCO",
        # Other
        "Real", "Sporting", "Club", "Deportivo", "Atlético", "Atletico",
        "Athletic", "Racing", "United", "City", "Dynamo", "Dinamo"
    ]
    
    # Suffixes to strip
    SUFFIXES_TO_STRIP = [
        "FC", "SC", "SK", "FK", "IF", "BK", "CF", "AC", "AS", "SV",
        "United", "City", "Calcio", "Spor", "Club"
    ]
    
    # HARDCODED IDs for teams that FotMob search returns wrong results
    # Format: "API Team Name" -> (FotMob ID, FotMob Name)
    HARDCODED_IDS = {
        # Greek teams (FotMob returns Nicosia instead of Piraeus)
        "Olympiacos": (8638, "Olympiacos"),
        "Olympiakos": (8638, "Olympiacos"),
        "Olympiacos Piraeus": (8638, "Olympiacos"),
        "Olympiakos Piraeus": (8638, "Olympiacos"),
        "Olympiacos FC": (8638, "Olympiacos"),
    }
    
    # Manual mapping for stubborn cases (API name -> FotMob search name)
    MANUAL_MAPPING = {
        # Italian
        "AS Roma": "Roma",
        "AC Milan": "Milan",
        "AC Monza": "Monza",
        "US Lecce": "Lecce",
        "US Sassuolo": "Sassuolo",
        "Milan": "AC Milan",
        "Inter": "Internazionale",
        "Inter Milan": "Internazionale",
        # English
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
        # German
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
        # Spanish
        "Atlético Madrid": "Atletico Madrid",
        "Atletico": "Atletico Madrid",
        "Real Sociedad": "Sociedad",
        "Real Betis": "Betis",
        "Athletic Bilbao": "Athletic Club",
        "Celta Vigo": "Celta",
        "Rayo": "Rayo Vallecano",
        # French
        "PSG": "Paris Saint-Germain",
        "Paris SG": "Paris Saint-Germain",
        "Monaco": "AS Monaco",
        "Lyon": "Olympique Lyonnais",
        "Marseille": "Olympique Marseille",
        "Saint-Étienne": "Saint-Etienne",
        # Portuguese
        "Sporting": "Sporting CP",
        "Sporting Lisbon": "Sporting CP",
        "Benfica": "SL Benfica",
        "Porto": "FC Porto",
        # Dutch
        "Ajax": "Ajax Amsterdam",
        "PSV": "PSV Eindhoven",
        "Feyenoord": "Feyenoord Rotterdam",
        # Swiss
        "FC Basel": "Basel",
        "FC Zurich": "Zurich",
        "FC Zürich": "Zurich",
        "Young Boys": "BSC Young Boys",
        # Turkish
        "Galatasaray SK": "Galatasaray",
        "Fenerbahçe": "Fenerbahce",
        "Beşiktaş": "Besiktas",
        "Çaykur Rizespor": "Rizespor",
        "Caykur Rizespor": "Rizespor",
        "Göztepe": "Goztepe",
        "Göztepe SK": "Goztepe",
        "Sivasspor": "Sivasspor",
        "Başakşehir": "Istanbul Basaksehir",
        "Istanbul Basaksehir FK": "Istanbul Basaksehir",
        "Gazişehir Gaziantep": "Gaziantep FK",
        "Gazisehir Gaziantep": "Gaziantep FK",
        "Gaziantep": "Gaziantep FK",
        # Greek (API name -> FotMob search name)
        "Olympiacos": "Olympiakos",
        "Olympiakos": "Olympiakos",
        "Olympiacos Piraeus": "Olympiakos",
        "Olympiakos Piraeus": "Olympiakos",
        "Panathinaikos Athens": "Panathinaikos",
        "Panathinaikos FC": "Panathinaikos",
        "PAOK": "PAOK Thessaloniki",
        "PAOK FC": "PAOK Thessaloniki",
        "AEK": "AEK Athens",
        "AEK Athens FC": "AEK Athens",
        # Scottish
        "Celtic": "Celtic FC",
        "Rangers": "Rangers FC",
        # Australian
        "Sydney": "Sydney FC",
        "Melbourne": "Melbourne Victory",
        "Western Sydney": "Western Sydney Wanderers",
        # Argentine
        "Boca": "Boca Juniors",
        "River": "River Plate",
        "Racing": "Racing Club",
        # Mexican
        "America": "Club America",
        "Club América": "Club America",
        "Guadalajara": "CD Guadalajara",
        "Chivas": "CD Guadalajara",
        # German (additional)
        "FSV Mainz 05": "Mainz 05",
        "FSV Mainz": "Mainz 05",
        "SC Freiburg": "Freiburg",
        "VfB Stuttgart": "Stuttgart",
        "VfL Wolfsburg": "Wolfsburg",
        "VfL Bochum": "Bochum",
        "TSG Hoffenheim": "Hoffenheim",
        "SpVgg Greuther Fürth": "Greuther Furth",
        # Norwegian
        "SK Brann": "Brann",
        "Rosenborg BK": "Rosenborg",
        "Molde FK": "Molde",
        "Viking FK": "Viking",
        "Bodø/Glimt": "Bodo/Glimt",
        # Croatian/Balkan
        "HNK Rijeka": "Rijeka",
        "HNK Hajduk Split": "Hajduk Split",
        "GNK Dinamo Zagreb": "Dinamo Zagreb",
        "NK Osijek": "Osijek",
        "HŠK Zrinjski Mostar": "Zrinjski Mostar",
        "NK Maribor": "Maribor",
        # Maltese
        "Ħamrun Spartans FC": "Hamrun Spartans",
        "Hamrun Spartans FC": "Hamrun Spartans",
        "Valletta FC": "Valletta",
        # Belgian
        "KAA Gent": "Gent",
        "KRC Genk": "Genk",
        "KV Mechelen": "Mechelen",
        # Swedish
        "Malmö FF": "Malmo FF",
        "AIK Stockholm": "AIK",
        "Djurgårdens IF": "Djurgardens IF",
        "IFK Göteborg": "IFK Goteborg",
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self._team_cache: Dict[str, Tuple[int, str]] = {}
        self._last_request_time = 0.0
        logger.info("✅ FotMob Provider initialized (UA rotation enabled)")
    
    def _rotate_user_agent(self):
        """Rotate User-Agent header for anti-bot evasion."""
        new_ua = get_random_user_agent()
        self.session.headers['User-Agent'] = new_ua
        logger.debug(f"🎭 UA rotated: {new_ua[:50]}...")
    
    def _rate_limit(self):
        """
        Enforce minimum interval between FotMob requests to avoid bans.
        V6.1: Thread-safe implementation for VPS multi-thread scenarios.
        """
        global _last_fotmob_request_time
        
        with _fotmob_rate_limit_lock:
            now = time.time()
            elapsed = now - _last_fotmob_request_time
            if elapsed < FOTMOB_MIN_REQUEST_INTERVAL:
                sleep_time = FOTMOB_MIN_REQUEST_INTERVAL - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
            _last_fotmob_request_time = time.time()
    
    def _make_request(self, url: str, retries: int = FOTMOB_MAX_RETRIES) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic and specific error handling.
        
        Args:
            url: URL to request
            retries: Number of retries for transient errors
            
        Returns:
            Response object or None on failure
        """
        self._rate_limit()
        
        for attempt in range(retries):
            # Rotate User-Agent on each attempt (anti-fingerprinting)
            self._rotate_user_agent()
            
            try:
                resp = self.session.get(url, timeout=FOTMOB_REQUEST_TIMEOUT)
                
                # Success
                if resp.status_code == 200:
                    return resp
                
                # Rate limited - exponential backoff
                if resp.status_code == 429:
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"⚠️ FotMob rate limit (429). Attesa {delay}s prima del retry {attempt + 1}/{retries}")
                    time.sleep(delay)
                    continue
                
                # Server errors - retry with backoff
                if resp.status_code in (502, 503, 504):
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"⚠️ FotMob server error ({resp.status_code}). Retry {attempt + 1}/{retries} in {delay}s")
                    time.sleep(delay)
                    continue
                
                # Client error (403, 404, etc.) - retry with new UA on 403
                if resp.status_code == 403:
                    if attempt < retries - 1:
                        delay = 2 ** (attempt + 1)
                        logger.warning(f"⚠️ FotMob 403 - rotating UA and retrying in {delay}s ({attempt + 1}/{retries})")
                        time.sleep(delay)
                        continue
                    logger.error(f"❌ FotMob accesso negato (403) dopo {retries} tentativi con UA diversi")
                    return None
                
                logger.error(f"❌ FotMob errore HTTP {resp.status_code}")
                return None
                
            except requests.exceptions.Timeout:
                delay = 2 ** (attempt + 1)
                logger.warning(f"⚠️ FotMob timeout. Retry {attempt + 1}/{retries} in {delay}s")
                time.sleep(delay)
                
            except requests.exceptions.ConnectionError as e:
                delay = 2 ** (attempt + 1)
                logger.warning(f"⚠️ FotMob errore connessione: {e}. Retry {attempt + 1}/{retries} in {delay}s")
                time.sleep(delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ FotMob errore richiesta: {e}")
                return None
        
        logger.error(f"❌ FotMob fallito dopo {retries} tentativi")
        return None
    
    def search_team(self, team_name: str) -> List[Dict]:
        """
        Search for teams on FotMob with robust error handling.
        
        Args:
            team_name: Team name to search
            
        Returns:
            List of matching teams with id, name, country (empty list on failure)
        """
        try:
            encoded_name = urllib.parse.quote(team_name)
            url = f"{self.BASE_URL}/search/suggest?term={encoded_name}"
            
            resp = self._make_request(url)
            
            if resp is None:
                logger.debug(f"FotMob search fallito per: {team_name}")
                return []
            
            try:
                data = resp.json()
            except ValueError as e:
                logger.error(f"❌ FotMob risposta JSON non valida: {e}")
                return []
            
            results = []
            
            for group in data:
                suggestions = group.get('suggestions', [])
                for suggestion in suggestions:
                    if suggestion.get('type') == 'team':
                        results.append({
                            'id': int(suggestion.get('id', 0)),
                            'name': suggestion.get('name', 'Unknown'),
                            'country': suggestion.get('country', 'Unknown')
                        })
            
            return results
            
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"❌ FotMob JSON decode error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ FotMob Search Error: {e}")
            return []
    
    def _strip_prefix(self, team_name: str) -> str:
        """Strip common prefixes from team name."""
        name = team_name.strip()
        for prefix in self.PREFIXES_TO_STRIP:
            # Check if name starts with prefix followed by space
            if name.lower().startswith(prefix.lower() + " "):
                stripped = name[len(prefix):].strip()
                if len(stripped) >= 3:
                    return stripped
        return name
    
    def _strip_suffix(self, team_name: str) -> str:
        """Strip common suffixes from team name."""
        name = team_name.strip()
        for suffix in self.SUFFIXES_TO_STRIP:
            # Check if name ends with space followed by suffix
            if name.lower().endswith(" " + suffix.lower()):
                stripped = name[:-len(suffix)-1].strip()
                if len(stripped) >= 3:
                    return stripped
        return name
    
    def _clean_team_name(self, team_name: str) -> str:
        """Apply both prefix and suffix stripping."""
        name = self._strip_prefix(team_name)
        name = self._strip_suffix(name)
        return name

    def search_team_id(self, team_name: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Find FotMob team ID for a team name with fuzzy matching.
        
        Search Strategy:
        -1. Check HARDCODED_IDS first (for teams with wrong FotMob search results)
        0. Check manual mapping dictionary first
        1. Check cache
        2. Exact search via FotMob API
        3. Fuzzy match against results
        4. Try with prefix stripped (AS Roma -> Roma)
        5. Try with suffix stripped (Basel FC -> Basel)
        6. Try first word only (for "Persija Jakarta" → "Persija")
        
        Args:
            team_name: Team name to search
            
        Returns:
            Tuple of (team_id, fotmob_name) or (None, None)
        """
        # Strategy -1: Check HARDCODED_IDS first (bypass FotMob search entirely)
        if team_name in self.HARDCODED_IDS:
            team_id, fotmob_name = self.HARDCODED_IDS[team_name]
            logger.info(f"🔒 Hardcoded ID: {team_name} → {fotmob_name} (ID: {team_id})")
            self._team_cache[team_name.lower().strip()] = (team_id, fotmob_name)
            return team_id, fotmob_name
        
        # Check cache first
        cache_key = team_name.lower().strip()
        if cache_key in self._team_cache:
            return self._team_cache[cache_key]
        
        # Also check cache with normalized name
        normalized_name = normalize_unicode(team_name)
        normalized_cache_key = normalized_name.lower().strip()
        if normalized_cache_key != cache_key and normalized_cache_key in self._team_cache:
            return self._team_cache[normalized_cache_key]
        
        # Strategy 0: Check manual mapping dictionary (try both original and normalized)
        if team_name in self.MANUAL_MAPPING:
            mapped_name = self.MANUAL_MAPPING[team_name]
            logger.info(f"📖 Manual mapping: {team_name} → {mapped_name}")
            results = self.search_team(mapped_name)
            if results:
                team_id = results[0]['id']
                fotmob_name = results[0]['name']
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Mapped: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name
        
        # Strategy 1: Direct search
        results = self.search_team(team_name)
        
        if results:
            # Try exact match first
            for r in results:
                if r['name'].lower() == team_name.lower():
                    self._team_cache[cache_key] = (r['id'], r['name'])
                    logger.info(f"✅ Exact match: {r['name']} (ID: {r['id']})")
                    return r['id'], r['name']
            
            # Fuzzy match against results
            candidate_names = [r['name'] for r in results]
            best_match = fuzzy_match_team(team_name, candidate_names)
            
            if best_match:
                for r in results:
                    if r['name'] == best_match:
                        self._team_cache[cache_key] = (r['id'], r['name'])
                        return r['id'], r['name']
            
            # Fallback: take first result if reasonable
            if len(results) == 1 or SequenceMatcher(None, team_name.lower(), results[0]['name'].lower()).ratio() > 0.5:
                team_id = results[0]['id']
                fotmob_name = results[0]['name']
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Found: {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name
        
        # Strategy 2: Try with PREFIX stripped (AS Roma -> Roma)
        prefix_stripped = self._strip_prefix(team_name)
        if prefix_stripped != team_name and len(prefix_stripped) >= 3:
            logger.debug(f"🔄 Trying prefix-stripped: {team_name} → {prefix_stripped}")
            results = self.search_team(prefix_stripped)
            if results:
                candidate_names = [r['name'] for r in results]
                best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)
                
                if best_match:
                    for r in results:
                        if r['name'] == best_match:
                            self._team_cache[cache_key] = (r['id'], r['name'])
                            logger.info(f"✅ Prefix-stripped match: {team_name} → {r['name']} (ID: {r['id']})")
                            return r['id'], r['name']
                
                # Take first result if only one
                if len(results) == 1:
                    team_id = results[0]['id']
                    fotmob_name = results[0]['name']
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Prefix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name
        
        # Strategy 3: Try with SUFFIX stripped (Basel FC -> Basel)
        suffix_stripped = self._strip_suffix(team_name)
        if suffix_stripped != team_name and len(suffix_stripped) >= 3:
            logger.debug(f"🔄 Trying suffix-stripped: {team_name} → {suffix_stripped}")
            results = self.search_team(suffix_stripped)
            if results:
                candidate_names = [r['name'] for r in results]
                best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)
                
                if best_match:
                    for r in results:
                        if r['name'] == best_match:
                            self._team_cache[cache_key] = (r['id'], r['name'])
                            logger.info(f"✅ Suffix-stripped match: {team_name} → {r['name']} (ID: {r['id']})")
                            return r['id'], r['name']
                
                # Take first result if only one
                if len(results) == 1:
                    team_id = results[0]['id']
                    fotmob_name = results[0]['name']
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Suffix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name
        
        # Strategy 4: Try first word only (common for Asian teams)
        first_word = team_name.split()[0] if team_name else ""
        if first_word and len(first_word) >= 4 and first_word.lower() != team_name.lower():
            # Skip if first word is a common prefix
            if first_word.upper() not in [p.upper() for p in self.PREFIXES_TO_STRIP]:
                results = self.search_team(first_word)
                if results:
                    candidate_names = [r['name'] for r in results]
                    best_match = fuzzy_match_team(team_name, candidate_names, threshold=0.4)
                    
                    if best_match:
                        for r in results:
                            if r['name'] == best_match:
                                self._team_cache[cache_key] = (r['id'], r['name'])
                                logger.info(f"✅ First-word match: {team_name} → {r['name']} (ID: {r['id']})")
                                return r['id'], r['name']
        
        # Strategy 5: Try fully cleaned name (both prefix and suffix)
        clean_name = self._clean_team_name(team_name)
        if clean_name != team_name and clean_name != prefix_stripped and clean_name != suffix_stripped:
            logger.debug(f"🔄 Trying fully cleaned: {team_name} → {clean_name}")
            results = self.search_team(clean_name)
            if results:
                team_id = results[0]['id']
                fotmob_name = results[0]['name']
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Cleaned match: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name
        
        # Strategy 6: Try with unicode normalized name (Ħamrun -> Hamrun, Malmö -> Malmo)
        if normalized_name != team_name:
            logger.debug(f"🔄 Trying unicode normalized: {team_name} → {normalized_name}")
            results = self.search_team(normalized_name)
            if results:
                candidate_names = [r['name'] for r in results]
                best_match = fuzzy_match_team(normalized_name, candidate_names, threshold=0.5)
                
                if best_match:
                    for r in results:
                        if r['name'] == best_match:
                            self._team_cache[cache_key] = (r['id'], r['name'])
                            self._team_cache[normalized_cache_key] = (r['id'], r['name'])
                            logger.info(f"✅ Unicode normalized: {team_name} → {r['name']} (ID: {r['id']})")
                            return r['id'], r['name']
                
                # Take first result
                if results:
                    team_id = results[0]['id']
                    fotmob_name = results[0]['name']
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    self._team_cache[normalized_cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Unicode normalized: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name
        
        logger.warning(f"⚠️ Team not found: {team_name}")
        return None, None
    
    def get_team_details(self, team_id: int, match_time: datetime = None) -> Optional[Dict]:
        """
        Get team details including squad and next match.
        Includes fail-safe fallback returning partial data on error.
        
        V4.3: Now uses Smart Cache with dynamic TTL based on match proximity.
        
        Args:
            team_id: FotMob team ID
            match_time: Match start time for cache TTL calculation (optional)
            
        Returns:
            Team data dict or fail-safe dict with error flag
        """
        # V4.3: Check smart cache first
        cache_key = f"team_details:{team_id}"
        if _SMART_CACHE_AVAILABLE:
            cached = get_team_cache().get(cache_key)
            if cached is not None:
                return cached
        
        try:
            url = f"{self.BASE_URL}/teams?id={team_id}"
            resp = self._make_request(url)
            
            if resp is None:
                logger.warning(f"⚠️ FotMob team details non disponibili per ID {team_id}")
                # Return fail-safe structure instead of None
                return {
                    "_error": True,
                    "_error_msg": "Dati FotMob non disponibili",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {}
                }
            
            try:
                data = resp.json()
                
                # V4.3: Store in smart cache with dynamic TTL
                if _SMART_CACHE_AVAILABLE and data and not data.get('_error'):
                    get_team_cache().set(cache_key, data, match_time=match_time)
                
                return data
            except ValueError as e:
                logger.error(f"❌ FotMob team details JSON non valido: {e}")
                return {
                    "_error": True,
                    "_error_msg": "Risposta JSON non valida",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {}
                }
            
        except Exception as e:
            logger.error(f"❌ FotMob Team Details Error: {e}")
            return {
                "_error": True,
                "_error_msg": str(e),
                "team_id": team_id,
                "squad": {},
                "fixtures": {}
            }


    def _extract_squad_injuries(self, team_data: Dict, team_name: str) -> List[Dict]:
        """
        Extract injured/unavailable players from team squad data.
        
        Args:
            team_data: FotMob team data
            team_name: Team name for logging
            
        Returns:
            List of injured players with name, reason, status (never None)
        """
        injuries = []
        
        if not team_data or not isinstance(team_data, dict):
            return injuries
        
        try:
            # FotMob squad structure: {'squad': {'squad': [groups...]}}
            squad_data = team_data.get('squad', {})
            
            # Handle nested structure
            if isinstance(squad_data, dict):
                squad_groups = squad_data.get('squad', [])
            else:
                squad_groups = squad_data if isinstance(squad_data, list) else []
            
            # Ensure squad_groups is iterable
            if squad_groups is None:
                squad_groups = []
            
            for group in squad_groups:
                if not isinstance(group, dict):
                    continue
                    
                players = group.get('members') or []
                if not isinstance(players, list):
                    continue
                    
                for player in players:
                    if not isinstance(player, dict):
                        continue
                    
                    # Check for injury field
                    injury = player.get('injury')
                    if injury:
                        injuries.append({
                            'name': player.get('name', 'Unknown'),
                            'reason': injury.get('type', 'Injury') if isinstance(injury, dict) else str(injury),
                            'status': injury.get('expectedReturn', 'Unknown') if isinstance(injury, dict) else 'Unknown',
                            'is_injured': True
                        })
                    
                    # Check for injuryInformation field
                    injury_info = player.get('injuryInformation')
                    if injury_info and isinstance(injury_info, dict):
                        if not any(i['name'] == player.get('name') for i in injuries):
                            injuries.append({
                                'name': player.get('name', 'Unknown'),
                                'reason': injury_info.get('injuryType', 'Injury'),
                                'status': injury_info.get('expectedReturn', 'Unknown'),
                                'is_injured': True
                            })
                    
                    # Check for unavailable status flags
                    if player.get('isInjured') or player.get('isSuspended'):
                        if not any(i['name'] == player.get('name') for i in injuries):
                            injuries.append({
                                'name': player.get('name', 'Unknown'),
                                'reason': 'Suspended' if player.get('isSuspended') else 'Injured',
                                'status': 'Unavailable',
                                'is_injured': True
                            })
            
            if injuries:
                logger.info(f"✅ Found {len(injuries)} unavailable players for {team_name}")
            
        except Exception as e:
            logger.error(f"Error extracting injuries: {e}")
        
        return injuries

    def get_fixture_details(self, team_name: str) -> Optional[Dict]:
        """
        Get fixture details for a team's next match.
        Chain: Search Team -> Get Team Details -> Find Next Match -> Extract Injuries
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with match intel (injuries, suspensions, etc.)
        """
        # Try mapped ID first (use top-level import)
        team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
        fotmob_name = team_name
        
        if not team_id:
            # Search dynamically
            team_id, fotmob_name = self.search_team_id(team_name)
        
        if not team_id:
            return {"error": f"Team not found: {team_name}", "source": "FotMob"}
        
        try:
            # Get team details to find next match
            team_data = self.get_team_details(team_id)
            if not team_data:
                return {"error": "Could not fetch team details", "source": "FotMob"}
            
            # Extract injuries from squad
            injuries = self._extract_squad_injuries(team_data, fotmob_name)
            
            # Find next match
            next_match = team_data.get('nextMatch')
            if not next_match:
                fixtures = team_data.get('fixtures', {})
                upcoming = fixtures.get('allFixtures', {}).get('nextMatch')
                if upcoming:
                    next_match = upcoming
            
            if not next_match:
                return {
                    "team_id": team_id,
                    "team_name": fotmob_name,
                    "injuries": injuries,
                    "confirmed_absentees": injuries,
                    "source": "FotMob"
                }
            
            match_id = next_match.get('id')
            
            # V5.1: Extract is_home flag for home/away validation
            # FotMob returns 'home': True/False indicating if searched team plays at home
            is_home = next_match.get('home', None)  # None if not available
            
            return {
                "team_id": team_id,
                "team_name": fotmob_name,
                "match_id": match_id,
                "opponent": next_match.get('opponent', {}).get('name', 'Unknown'),
                "match_time": next_match.get('utcTime'),
                "is_home": is_home,  # V5.1: True if team plays at home, False if away, None if unknown
                "injuries": injuries,
                "confirmed_absentees": injuries,
                "source": "FotMob"
            }
            
        except Exception as e:
            logger.error(f"FotMob Fixture Error: {e}")
            return {"error": str(e), "source": "FotMob"}

    def get_match_details(self, team_name: str, home_team: str = None, away_team: str = None, match_date=None) -> Optional[Dict]:
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
        
        if result and not result.get('error'):
            # Transform injuries to missing_players format
            result['missing_players'] = result.get('injuries', [])
            
            fotmob_team = result.get('team_name', team_name)
            fotmob_opponent = result.get('opponent', 'Unknown')
            
            # Default assignment
            result['home_team'] = fotmob_team
            result['away_team'] = fotmob_opponent
            
            # Home/Away Alignment Check (if Odds API teams provided)
            if home_team and away_team:
                # Calculate similarity scores
                from difflib import SequenceMatcher
                
                # Check if FotMob team matches Odds API home or away
                fotmob_vs_home = SequenceMatcher(None, fotmob_team.lower(), home_team.lower()).ratio()
                fotmob_vs_away = SequenceMatcher(None, fotmob_team.lower(), away_team.lower()).ratio()
                
                # Also check opponent
                opponent_vs_home = SequenceMatcher(None, fotmob_opponent.lower(), home_team.lower()).ratio()
                opponent_vs_away = SequenceMatcher(None, fotmob_opponent.lower(), away_team.lower()).ratio()
                
                # Detection: FotMob has inverted home/away
                # If FotMob's "team" matches our "away" AND FotMob's "opponent" matches our "home"
                if fotmob_vs_away > fotmob_vs_home and opponent_vs_home > opponent_vs_away:
                    if fotmob_vs_away > 0.5 and opponent_vs_home > 0.5:
                        logger.info(f"🔄 Swapped Home/Away data to match Odds API: {home_team} vs {away_team}")
                        
                        # SWAP: Align to Odds API structure
                        result['home_team'] = home_team
                        result['away_team'] = away_team
                        
                        # Swap injuries if they're team-specific
                        if 'home_injuries' in result and 'away_injuries' in result:
                            result['home_injuries'], result['away_injuries'] = result['away_injuries'], result['home_injuries']
                else:
                    # Normal case: FotMob matches Odds API
                    result['home_team'] = home_team
                    result['away_team'] = away_team
            
            # ========================================
            # H2H HISTORY EXTRACTION (V4.1 - BTTS Intelligence)
            # ========================================
            # Fetch last 5 H2H matches for BTTS trend analysis
            result['h2h_history'] = []
            
            if result.get('match_id'):
                try:
                    match_data = self.get_match_lineup(result['match_id'])
                    if match_data:
                        # Navigate safe paths for H2H data
                        content = match_data.get('content', {})
                        
                        # Try multiple FotMob H2H paths
                        raw_h2h = (
                            content.get('h2h', {}).get('matches', []) or
                            content.get('matchFacts', {}).get('h2h', {}).get('matches', []) or
                            content.get('h2h', []) or
                            []
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
                            status = m.get('status', {})
                            if not status.get('started', False):
                                continue  # Skip future matches
                            
                            h_score = None
                            a_score = None
                            
                            # Priority 1: Direct score fields
                            h_score = m.get('homeScore')
                            a_score = m.get('awayScore')
                            
                            # Priority 2: Nested in home/away objects
                            if h_score is None:
                                home_obj = m.get('home', {})
                                if isinstance(home_obj, dict):
                                    h_score = home_obj.get('score')
                            if a_score is None:
                                away_obj = m.get('away', {})
                                if isinstance(away_obj, dict):
                                    a_score = away_obj.get('score')
                            
                            # Priority 3: Parse from status.scoreStr ("2 - 1")
                            if h_score is None or a_score is None:
                                score_str = status.get('scoreStr', '')
                                if score_str and ' - ' in score_str:
                                    try:
                                        parts = score_str.split(' - ')
                                        if len(parts) == 2:
                                            h_score = int(parts[0].strip())
                                            a_score = int(parts[1].strip())
                                    except (ValueError, IndexError):
                                        pass
                            
                            # Skip if still no valid scores
                            if h_score is None or a_score is None:
                                continue
                            
                            try:
                                h2h_data.append({
                                    'home_score': int(h_score),
                                    'away_score': int(a_score)
                                })
                            except (ValueError, TypeError):
                                # Skip malformed score data
                                continue
                        
                        result['h2h_history'] = h2h_data
                        
                        if h2h_data:
                            logger.info(f"📊 H2H History: Found {len(h2h_data)} matches for {result.get('home_team', 'Unknown')} vs {result.get('away_team', 'Unknown')}")
                        
                except Exception as e:
                    logger.debug(f"H2H extraction failed (non-critical): {e}")
            
            # Date Validation (CRITICAL: Prevent wrong match mapping)
            # Tolerance: 4 hours - if FotMob match is outside this window, reject it
            if match_date and result.get('match_time'):
                try:
                    from datetime import datetime, timedelta
                    from dateutil import parser as date_parser
                    
                    # Normalize input time (from DB/Odds API) - ensure UTC
                    if isinstance(match_date, datetime):
                        expected_date = match_date
                    elif isinstance(match_date, str):
                        expected_date = date_parser.parse(match_date)
                    else:
                        expected_date = None
                    
                    if expected_date:
                        # Ensure expected_date is UTC-aware
                        if expected_date.tzinfo is None:
                            expected_date = expected_date.replace(tzinfo=timezone.utc)
                        
                        # Parse FotMob match time
                        fotmob_time_str = result.get('match_time')
                        if fotmob_time_str:
                            # FotMob uses ISO format (usually with Z or +00:00)
                            if isinstance(fotmob_time_str, str):
                                fotmob_time = date_parser.parse(fotmob_time_str)
                            else:
                                fotmob_time = fotmob_time_str
                            
                            # Ensure FotMob time is UTC-aware
                            if fotmob_time.tzinfo is None:
                                fotmob_time = fotmob_time.replace(tzinfo=timezone.utc)
                            
                            # Calculate time difference in seconds
                            delta_seconds = abs((fotmob_time - expected_date).total_seconds())
                            delta_hours = delta_seconds / 3600
                            
                            # STRICT: 4 hours tolerance to prevent wrong match mapping
                            if delta_seconds > 4 * 3600:
                                logger.warning(
                                    f"⚠️ WRONG MATCH REJECTED: {team_name} | "
                                    f"Expected={expected_date.strftime('%Y-%m-%d %H:%M')} UTC, "
                                    f"FotMob={fotmob_time.strftime('%Y-%m-%d %H:%M')} UTC, "
                                    f"Diff={delta_hours:.1f}h (max 4h)"
                                )
                                return None
                            else:
                                logger.debug(f"✅ Match time validated: diff={delta_hours:.1f}h (within 4h tolerance)")
                            
                except ImportError:
                    # dateutil not available, fall back to basic parsing
                    logger.debug("dateutil not available, skipping strict time validation")
                except Exception as e:
                    logger.debug(f"Date validation error (non-critical): {e}")
        
        return result

    def validate_home_away_order(self, odds_home_team: str, odds_away_team: str) -> Tuple[str, str, bool]:
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
            
            if not fixture or fixture.get('error'):
                # FotMob lookup failed - trust Odds API order
                logger.debug(f"FotMob lookup failed for {odds_home_team}, trusting Odds API order")
                return odds_home_team, odds_away_team, False
            
            is_home = fixture.get('is_home')
            
            # If is_home is None, FotMob didn't provide this info - trust Odds API
            if is_home is None:
                logger.debug(f"FotMob didn't provide is_home for {odds_home_team}, trusting Odds API order")
                return odds_home_team, odds_away_team, False
            
            # Validate opponent matches
            fotmob_opponent = fixture.get('opponent', '')
            
            # Use fuzzy matching to verify opponent is the expected away team
            from difflib import SequenceMatcher
            opponent_similarity = SequenceMatcher(
                None, 
                fotmob_opponent.lower(), 
                odds_away_team.lower()
            ).ratio()
            
            # If opponent doesn't match expected away team, this might be wrong match
            if opponent_similarity < 0.5:
                logger.warning(
                    f"⚠️ FotMob opponent mismatch: expected '{odds_away_team}', "
                    f"got '{fotmob_opponent}' (similarity: {opponent_similarity:.2f}). "
                    f"Trusting Odds API order."
                )
                return odds_home_team, odds_away_team, False
            
            # Core logic: Check if Odds API home team actually plays at home
            if is_home:
                # FotMob confirms: odds_home_team plays at home → order is correct
                logger.debug(f"✅ Home/Away order validated: {odds_home_team} (H) vs {odds_away_team} (A)")
                return odds_home_team, odds_away_team, False
            else:
                # FotMob says: odds_home_team plays AWAY → order is INVERTED!
                logger.warning(
                    f"🔄 HOME/AWAY INVERSION DETECTED! "
                    f"Odds API: {odds_home_team} vs {odds_away_team} | "
                    f"FotMob: {odds_home_team} plays AWAY. "
                    f"Correcting to: {odds_away_team} vs {odds_home_team}"
                )
                return odds_away_team, odds_home_team, True
                
        except Exception as e:
            logger.error(f"Error validating home/away order: {e}")
            # On error, trust Odds API order
            return odds_home_team, odds_away_team, False

    def get_player_injuries(self, team_name: str) -> List[Dict]:
        """
        Get list of injured players for a team.
        
        Args:
            team_name: Name of the team
            
        Returns:
            List of injured players (never None, always a list)
        """
        try:
            result = self.get_fixture_details(team_name)
            
            if result and not result.get('error'):
                injuries = result.get('injuries')
                # Ensure we always return a list, never None
                return injuries if isinstance(injuries, list) else []
            
            return []
        except Exception as e:
            logger.error(f"Error getting player injuries for {team_name}: {e}")
            return []

    def get_table_context(self, team_name: str) -> Dict:
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
            "error": None
        }
        
        try:
            # Get team ID (use top-level import)
            team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
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
            table_data = team_data.get('tableData')
            
            if not table_data:
                # Try alternative paths
                overview = team_data.get('overview', {})
                table_data = overview.get('table')
            
            if not table_data:
                # V4.4: Try direct 'table' key (FotMob API variation)
                table_data = team_data.get('table')
            
            if not table_data:
                # Season might not have started or it's a cup match
                result["zone"] = "Unknown"
                result["motivation"] = "Unknown (No table data - cup match or season start)"
                logger.info(f"⚠️ No table data for {team_name} - possibly cup match or early season")
                return result
            
            # Parse table position
            # FotMob table structure varies, try common patterns
            if isinstance(table_data, dict):
                tables = table_data.get('tables', [table_data])
            elif isinstance(table_data, list):
                # V4.4: Handle table[0]['data'] structure
                tables = []
                for item in table_data:
                    if isinstance(item, dict):
                        # Try item['data'] first (new FotMob structure)
                        if 'data' in item:
                            tables.append(item['data'])
                        else:
                            tables.append(item)
            else:
                tables = []
            
            for table in tables:
                if not isinstance(table, dict):
                    continue
                    
                rows = table.get('table', {}).get('all', [])
                if not rows:
                    rows = table.get('all', [])
                
                total_teams = len(rows)
                
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    
                    row_name = row.get('name', '').lower()
                    row_short = row.get('shortName', '').lower()
                    
                    if team_name.lower() in row_name or team_name.lower() in row_short:
                        position = row.get('idx', row.get('position'))
                        
                        # Validate position is a valid number (not None, not 0 for 1-indexed leagues)
                        if position is not None and isinstance(position, (int, float)) and position > 0:
                            result["position"] = position
                            result["total_teams"] = total_teams
                            result["points"] = row.get('pts')
                            result["form"] = row.get('form', [])
                            
                            # V4.4: Calculate matches_remaining for Biscotto Engine
                            played = row.get('played', row.get('games'))
                            if played is not None and total_teams > 1:
                                result["played"] = played
                                # Standard league: (N-1)*2 total matches per team
                                total_matches = (total_teams - 1) * 2
                                result["matches_remaining"] = max(0, total_matches - played)
                            
                            # Calculate zone and motivation
                            # Safe: position and total_teams are validated above
                            # V5.2: Also check position <= total_teams to avoid pct > 1.0
                            if total_teams > 0 and position <= total_teams:
                                pct = position / total_teams
                                
                                if pct <= 0.15:  # Top 15%
                                    result["zone"] = "Title Race"
                                    result["motivation"] = "HIGH - Fighting for title/promotion"
                                elif pct <= 0.35:  # Top 35%
                                    result["zone"] = "European Spots"
                                    result["motivation"] = "HIGH - Chasing European qualification"
                                elif pct >= 0.85:  # Bottom 15%
                                    result["zone"] = "Relegation"
                                    result["motivation"] = "DESPERATE - Fighting relegation"
                                elif pct >= 0.70:  # Bottom 30%
                                    result["zone"] = "Danger Zone"
                                    result["motivation"] = "HIGH - Avoiding relegation battle"
                                else:
                                    result["zone"] = "Mid-Table"
                                    result["motivation"] = "MEDIUM - Nothing to play for"
                            
                            logger.info(f"📊 {team_name}: Position {position}/{total_teams} ({result['zone']})")
                            return result
            
            # Team not found in table
            result["zone"] = "Unknown"
            result["motivation"] = "Unknown (Team not found in table)"
            
        except Exception as e:
            logger.error(f"Error getting table context for {team_name}: {e}")
            result["error"] = str(e)
        
        return result

    def get_physical_context(self, team_name: str) -> Dict:
        """
        LAYER 2: FATIGUE ANALYSIS
        
        Get physical context: time since last match + recent form.
        Safe: Returns "Fresh" if no previous match found (season start).
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with hours_since_last, fatigue_level, form_string
        """
        result = {
            "hours_since_last": None,
            "fatigue_level": "Unknown",
            "last_match": None,
            "form_string": None,
            "form_points": None,
            "error": None
        }
        
        try:
            # Get team ID (use top-level import)
            team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
            if not team_id:
                team_id, _ = self.search_team_id(team_name)
            
            if not team_id:
                result["error"] = "Team not found"
                result["fatigue_level"] = "Unknown"
                return result
            
            # Get team details
            team_data = self.get_team_details(team_id)
            if not team_data:
                result["error"] = "Could not fetch team data"
                result["fatigue_level"] = "Unknown"
                return result
            
            # Extract fixtures/recent matches
            fixtures = team_data.get('fixtures', {})
            
            # Get last match
            last_match = fixtures.get('allFixtures', {}).get('lastMatch')
            
            if not last_match:
                # Try alternative: recent results
                recent = team_data.get('recentResults', [])
                if recent and len(recent) > 0:
                    last_match = recent[0]
            
            if last_match:
                # Parse last match time
                match_time_str = last_match.get('utcTime')
                
                if match_time_str:
                    try:
                        match_time = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                        now = datetime.now(match_time.tzinfo) if match_time.tzinfo else datetime.now(timezone.utc)
                        
                        hours_diff = (now - match_time).total_seconds() / 3600
                        result["hours_since_last"] = round(hours_diff, 1)
                        
                        # Determine fatigue level
                        if hours_diff < 72:  # Less than 3 days
                            result["fatigue_level"] = "HIGH - Less than 72h rest"
                        elif hours_diff < 96:  # 3-4 days
                            result["fatigue_level"] = "MEDIUM - 3-4 days rest"
                        elif hours_diff < 168:  # 4-7 days
                            result["fatigue_level"] = "LOW - Normal rest (4-7 days)"
                        else:  # More than 7 days
                            result["fatigue_level"] = "FRESH - Extended rest (7+ days)"
                        
                        # Get opponent info
                        opponent = last_match.get('opponent', {})
                        result["last_match"] = f"vs {opponent.get('name', 'Unknown')}"
                        
                        logger.info(f"⏱️ {team_name}: {hours_diff:.0f}h since last match ({result['fatigue_level']})")
                        
                    except Exception as e:
                        logger.warning(f"Could not parse match time: {e}")
            else:
                # No previous match - season start
                result["fatigue_level"] = "FRESH - Season start (no recent matches)"
                logger.info(f"⏱️ {team_name}: No recent matches found - assuming fresh")
            
            # Extract form (last 5 results)
            form_data = team_data.get('form', [])
            
            if not form_data:
                # Try from table data
                table_ctx = self.get_table_context(team_name)
                form_data = table_ctx.get('form', [])
            
            if form_data and isinstance(form_data, list):
                # Form is usually list of W/D/L or similar
                form_string = ""
                form_points = 0
                
                for f in form_data[:5]:
                    if isinstance(f, dict):
                        res = f.get('result', f.get('resultString', ''))
                    else:
                        res = str(f)
                    
                    if res in ['W', 'w', 'win', 'Win']:
                        form_string += "W"
                        form_points += 3
                    elif res in ['D', 'd', 'draw', 'Draw']:
                        form_string += "D"
                        form_points += 1
                    elif res in ['L', 'l', 'loss', 'Loss']:
                        form_string += "L"
                    else:
                        form_string += "?"
                
                result["form_string"] = form_string
                result["form_points"] = form_points
                logger.info(f"📈 {team_name}: Form {form_string} ({form_points} pts from last 5)")
            
        except Exception as e:
            logger.error(f"Error getting physical context for {team_name}: {e}")
            result["error"] = str(e)
            result["fatigue_level"] = "Unknown"
        
        return result

    def get_full_team_context(self, team_name: str) -> Dict:
        """
        Get complete team context: injuries + motivation + fatigue.
        
        Combines all intelligence layers for comprehensive analysis.
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with all context data
        """
        context = {
            "team": team_name,
            "injuries": [],
            "motivation": {},
            "fatigue": {},
            "summary": ""
        }
        
        # Get injuries
        context["injuries"] = self.get_player_injuries(team_name)
        
        # Get motivation (table position)
        context["motivation"] = self.get_table_context(team_name)
        
        # Get fatigue (physical state)
        context["fatigue"] = self.get_physical_context(team_name)
        
        # Build summary
        parts = []
        
        if context["injuries"]:
            parts.append(f"{len(context['injuries'])} injured")
        
        if context["motivation"].get("zone") != "Unknown":
            parts.append(f"{context['motivation']['zone']}")
        
        if context["fatigue"].get("fatigue_level") != "Unknown":
            parts.append(context["fatigue"]["fatigue_level"].split(" - ")[0])
        
        context["summary"] = " | ".join(parts) if parts else "No significant context"
        
        return context

    def get_match_lineup(self, match_id: int, match_time: datetime = None) -> Optional[Dict]:
        """
        Fetch match details including predicted/confirmed lineups.
        
        V4.3: Now uses Smart Cache with dynamic TTL based on match proximity.
        
        Args:
            match_id: FotMob match ID
            match_time: Match start time for cache TTL calculation (optional)
            
        Returns:
            Match data dict or None
        """
        # V4.3: Check smart cache first
        cache_key = f"match_lineup:{match_id}"
        if _SMART_CACHE_AVAILABLE:
            cached = get_match_cache().get(cache_key)
            if cached is not None:
                return cached
        
        try:
            url = f"{self.BASE_URL}/matchDetails?matchId={match_id}"
            resp = self._make_request(url)
            
            if resp is None:
                logger.warning(f"FotMob match details request failed for match {match_id}")
                return None
            
            try:
                data = resp.json()
            except ValueError as e:
                logger.error(f"❌ FotMob match details JSON non valido: {e}")
                return None
            
            # V4.3: Store in smart cache with dynamic TTL
            if _SMART_CACHE_AVAILABLE and data:
                get_match_cache().set(cache_key, data, match_time=match_time)
            
            return data
            
        except Exception as e:
            logger.error(f"FotMob Match Details Error: {e}")
            return None

    def _find_stat_value(self, stats_list: List, stat_name: str) -> Tuple[Optional[any], Optional[any]]:
        """
        V3.7: Robust parser for FotMob nested stats structure.
        
        FotMob stats are nested: Categories (Attack, Defense, Top Stats) -> Items
        Each item has: title, stats[home, away] with value/key
        
        Args:
            stats_list: List of stat categories from FotMob
            stat_name: Name of stat to find (e.g., "Corners", "Yellow cards")
            
        Returns:
            Tuple of (home_value, away_value) or (None, None) if not found
        """
        if not stats_list:
            return None, None
        
        stat_name_lower = stat_name.lower()
        
        for category in stats_list:
            if not isinstance(category, dict):
                continue
            
            items = category.get('items', [])
            if not items:
                # Some categories use 'stats' instead of 'items'
                items = category.get('stats', [])
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                title = item.get('title', '').lower()
                
                # Match stat name (flexible matching)
                if stat_name_lower in title or title in stat_name_lower:
                    stats = item.get('stats', [])
                    
                    if len(stats) >= 2:
                        home_stat = stats[0]
                        away_stat = stats[1]
                        
                        # Extract values - FotMob uses 'value' or direct number
                        home_val = home_stat.get('value') if isinstance(home_stat, dict) else home_stat
                        away_val = away_stat.get('value') if isinstance(away_stat, dict) else away_stat
                        
                        return home_val, away_val
        
        return None, None

    def _parse_stat_value(self, value: any, is_percentage: bool = False) -> Optional[float]:
        """
        Parse stat value from FotMob format to float.
        
        Handles: "55%", "2.34", 55, None
        
        Args:
            value: Raw value from FotMob
            is_percentage: If True, strip % and return as float
            
        Returns:
            Float value or None
        """
        if value is None:
            return None
        
        try:
            if isinstance(value, (int, float)):
                return float(value)
            
            if isinstance(value, str):
                # Remove % sign and whitespace
                cleaned = value.strip().replace('%', '').strip()
                if cleaned:
                    return float(cleaned)
        except (ValueError, TypeError):
            pass
        
        return None

    def get_match_stats(self, match_id: int) -> Optional[Dict]:
        """
        V3.7: Fetch detailed match stats for warehousing.
        
        Extracts: Corners, Yellow/Red Cards, xG, Possession, Shots on Target,
                  Big Chances, Fouls from finished matches.
        
        Args:
            match_id: FotMob match ID
            
        Returns:
            Dict with stats or None if unavailable
        """
        try:
            match_data = self.get_match_lineup(match_id)
            if not match_data:
                return None
            
            content = match_data.get('content', {})
            stats_data = content.get('stats', {})
            
            # FotMob stats path: content.stats.Periods.All.stats
            stats_list = None
            if isinstance(stats_data, dict):
                periods = stats_data.get('Periods', {})
                if periods:
                    all_period = periods.get('All', {})
                    stats_list = all_period.get('stats', [])
                
                # Fallback to old paths
                if not stats_list:
                    stats_list = stats_data.get('Ede') or stats_data.get('stats')
                    if not stats_list and stats_data:
                        # Try first non-empty value
                        for value in stats_data.values():
                            if isinstance(value, list) and value:
                                stats_list = value
                                break
            elif isinstance(stats_data, list):
                stats_list = stats_data
            
            if not stats_list:
                logger.debug(f"No stats found for match {match_id}")
                return None
            
            result = {}
            
            # Helper to parse int stats (0 if missing)
            def parse_int(val):
                parsed = self._parse_stat_value(val)
                return int(parsed) if parsed is not None else 0
            
            # Corners
            home_corners, away_corners = self._find_stat_value(stats_list, 'Corners')
            result['home_corners'] = parse_int(home_corners)
            result['away_corners'] = parse_int(away_corners)
            
            # Yellow Cards (separate)
            home_yellow, away_yellow = self._find_stat_value(stats_list, 'Yellow cards')
            result['home_yellow_cards'] = parse_int(home_yellow)
            result['away_yellow_cards'] = parse_int(away_yellow)
            
            # Red Cards (separate)
            home_red, away_red = self._find_stat_value(stats_list, 'Red cards')
            result['home_red_cards'] = parse_int(home_red)
            result['away_red_cards'] = parse_int(away_red)
            
            # Expected Goals (xG) - None if missing (float)
            home_xg, away_xg = self._find_stat_value(stats_list, 'Expected goals (xG)')
            if home_xg is None:
                home_xg, away_xg = self._find_stat_value(stats_list, 'Expected goals')
            result['home_xg'] = self._parse_stat_value(home_xg)
            result['away_xg'] = self._parse_stat_value(away_xg)
            
            # Possession (both home and away) - None if missing (float)
            home_poss, away_poss = self._find_stat_value(stats_list, 'Ball possession')
            if home_poss is None:
                home_poss, away_poss = self._find_stat_value(stats_list, 'Possession')
            result['home_possession'] = self._parse_stat_value(home_poss, is_percentage=True)
            result['away_possession'] = self._parse_stat_value(away_poss, is_percentage=True)
            
            # Shots on Target
            home_sot, away_sot = self._find_stat_value(stats_list, 'Shots on target')
            result['home_shots_on_target'] = parse_int(home_sot)
            result['away_shots_on_target'] = parse_int(away_sot)
            
            # Big Chances (can be in "Top stats" or "Shots" category)
            home_bc, away_bc = self._find_stat_value(stats_list, 'Big chances')
            result['home_big_chances'] = parse_int(home_bc)
            result['away_big_chances'] = parse_int(away_bc)
            
            # Fouls (FotMob uses "Fouls committed")
            home_fouls, away_fouls = self._find_stat_value(stats_list, 'Fouls committed')
            if home_fouls is None:
                home_fouls, away_fouls = self._find_stat_value(stats_list, 'Fouls')
            result['home_fouls'] = parse_int(home_fouls)
            result['away_fouls'] = parse_int(away_fouls)
            
            # Log what we found
            found_stats = [k for k, v in result.items() if v is not None and v != 0]
            if found_stats:
                logger.debug(f"📊 Match {match_id} stats: {len(found_stats)} fields populated")
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching match stats for {match_id}: {e}")
            return None

    def get_referee_info(self, team_name: str) -> Optional[Dict]:
        """
        REFEREE ANALYSIS: Extract referee info for upcoming match.
        
        Data extraction paths:
        1. content.matchFacts.infoBox.Referee.name
        2. Fallback: content.stats for referee stats
        
        SAFETY: Returns None if referee data unavailable.
        Do NOT hallucinate - only return confirmed data.
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with referee name and stats (if available), or None
        """
        try:
            # Get team ID (use top-level import)
            team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
            if not team_id:
                team_id, _ = self.search_team_id(team_name)
            
            if not team_id:
                return None
            
            # Get team details to find next match
            team_data = self.get_team_details(team_id)
            if not team_data:
                return None
            
            # Get next match ID
            next_match = team_data.get('nextMatch')
            if not next_match:
                fixtures = team_data.get('fixtures', {})
                next_match = fixtures.get('allFixtures', {}).get('nextMatch')
            
            if not next_match:
                return None
            
            match_id = next_match.get('id')
            if not match_id:
                return None
            
            # Fetch match details
            match_data = self.get_match_lineup(match_id)
            if not match_data:
                return None
            
            # Extract referee info
            result = {
                "name": None,
                "stats": None,
                "cards_per_game": None,
                "strictness": "Unknown"
            }
            
            # Path 1: content.matchFacts.infoBox.Referee
            content = match_data.get('content', {})
            match_facts = content.get('matchFacts', {})
            info_box = match_facts.get('infoBox', {})
            
            referee_data = info_box.get('Referee')
            
            if referee_data:
                if isinstance(referee_data, dict):
                    result["name"] = referee_data.get('text') or referee_data.get('name')
                elif isinstance(referee_data, str):
                    result["name"] = referee_data
            
            # Path 2: Try alternative locations
            if not result["name"]:
                # Sometimes in header or general
                header = match_data.get('header', {})
                result["name"] = header.get('referee')
            
            if not result["name"]:
                # Try general match info
                general = match_data.get('general', {})
                result["name"] = general.get('referee')
            
            # Path 3: Extract referee stats if available
            stats = content.get('stats', {})
            
            if stats and isinstance(stats, dict):
                # Look for referee-specific stats
                referee_stats = stats.get('referee')
                if referee_stats:
                    result["stats"] = referee_stats
                    
                    # Try to extract cards per game
                    if isinstance(referee_stats, dict):
                        result["cards_per_game"] = referee_stats.get('cardsPerGame') or referee_stats.get('avgCards')
            
            # Determine strictness based on available data (V2.8 thresholds)
            if result["cards_per_game"]:
                cpg = float(result["cards_per_game"])
                if cpg >= 5.5:
                    result["strictness"] = "VERY_STRICT"  # Override: Always suggest Over Cards
                elif cpg >= 3.5:
                    result["strictness"] = "STRICT"  # Allow Over Cards with context
                elif cpg >= 2.5:
                    result["strictness"] = "AVERAGE"  # Caution
                else:
                    result["strictness"] = "LENIENT"  # VETO: Forbid Over Cards
            
            if result["name"]:
                logger.info(f"⚖️ Referee: {result['name']} (Strictness: {result['strictness']})")
                return result
            
            logger.info(f"⚠️ No referee data available for {team_name}'s next match")
            return None
            
        except Exception as e:
            logger.error(f"Error getting referee info for {team_name}: {e}")
            return None

    def get_stadium_coordinates(self, team_name: str) -> Optional[Tuple[float, float]]:
        """
        WEATHER INTEGRATION: Extract stadium coordinates for upcoming match.
        
        Data extraction paths:
        1. content.matchFacts.infoBox.Stadium.geo
        2. content.matchFacts.infoBox.Stadium.location
        3. venue.coordinates from match data
        
        SAFETY: Returns None if coordinates unavailable or invalid (0,0).
        Do NOT attempt to guess coordinates from city name.
        
        Args:
            team_name: Name of the team
            
        Returns:
            Tuple of (latitude, longitude) or None
        """
        try:
            # Get team ID (use top-level import)
            team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
            if not team_id:
                team_id, _ = self.search_team_id(team_name)
            
            if not team_id:
                return None
            
            # Get team details to find next match
            team_data = self.get_team_details(team_id)
            if not team_data:
                return None
            
            # Get next match ID
            next_match = team_data.get('nextMatch')
            if not next_match:
                fixtures = team_data.get('fixtures', {})
                next_match = fixtures.get('allFixtures', {}).get('nextMatch')
            
            if not next_match:
                return None
            
            match_id = next_match.get('id')
            if not match_id:
                return None
            
            # Fetch match details
            match_data = self.get_match_lineup(match_id)
            if not match_data:
                return None
            
            # Extract stadium coordinates from various paths
            lat, lon = None, None
            
            # Path 1: content.matchFacts.infoBox.Stadium
            content = match_data.get('content', {})
            match_facts = content.get('matchFacts', {})
            info_box = match_facts.get('infoBox', {})
            
            stadium_data = info_box.get('Stadium')
            if stadium_data and isinstance(stadium_data, dict):
                # Try geo field
                geo = stadium_data.get('geo')
                if geo and isinstance(geo, dict):
                    lat = geo.get('lat') or geo.get('latitude')
                    lon = geo.get('lon') or geo.get('lng') or geo.get('longitude')
                
                # Try location field
                if lat is None or lon is None:
                    location = stadium_data.get('location')
                    if location and isinstance(location, dict):
                        lat = location.get('lat') or location.get('latitude')
                        lon = location.get('lon') or location.get('lng') or location.get('longitude')
            
            # Path 2: venue in match data
            if lat is None or lon is None:
                venue = match_data.get('venue', {})
                if venue and isinstance(venue, dict):
                    coords = venue.get('coordinates', {})
                    if coords:
                        lat = coords.get('lat') or coords.get('latitude')
                        lon = coords.get('lon') or coords.get('lng') or coords.get('longitude')
            
            # Path 3: general.venue
            if lat is None or lon is None:
                general = match_data.get('general', {})
                venue = general.get('venue', {})
                if venue and isinstance(venue, dict):
                    lat = venue.get('lat')
                    lon = venue.get('lon') or venue.get('lng')
            
            # Validate coordinates
            if lat is not None and lon is not None:
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                    
                    # Reject invalid coordinates
                    if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
                        logger.debug(f"Invalid coordinate range for {team_name}: {lat_f}, {lon_f}")
                        return None
                    
                    # Reject null island (0,0) - likely missing data
                    if lat_f == 0.0 and lon_f == 0.0:
                        logger.debug(f"Null island coordinates for {team_name} - likely missing data")
                        return None
                    
                    logger.info(f"🏟️ Stadium coords for {team_name}: {lat_f:.4f}, {lon_f:.4f}")
                    return (lat_f, lon_f)
                    
                except (TypeError, ValueError) as e:
                    logger.debug(f"Could not parse coordinates for {team_name}: {e}")
                    return None
            
            logger.debug(f"No stadium coordinates found for {team_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting stadium coordinates for {team_name}: {e}")
            return None

    def _extract_key_starters(self, team_data: Dict) -> List[Dict]:
        """
        Extract key starters (top 13 players from squad).
        Excludes coaches/managers.
        
        Args:
            team_data: FotMob team data
            
        Returns:
            List of key players with name
        """
        key_players = []
        
        try:
            squad_data = team_data.get('squad', {})
            
            if isinstance(squad_data, dict):
                squad_groups = squad_data.get('squad', [])
            else:
                squad_groups = squad_data if isinstance(squad_data, list) else []
            
            all_players = []
            
            for group in squad_groups:
                if not isinstance(group, dict):
                    continue
                
                # Skip coach/staff groups
                group_title = group.get('title', '')
                if isinstance(group_title, str):
                    group_title_lower = group_title.lower()
                    if 'coach' in group_title_lower or 'staff' in group_title_lower or 'manager' in group_title_lower:
                        continue
                
                players = group.get('members', [])
                for player in players:
                    if not isinstance(player, dict):
                        continue
                    
                    name = player.get('name', '')
                    
                    # Skip if role indicates non-player (role can be dict or string)
                    role = player.get('role', {})
                    if isinstance(role, dict):
                        role_key = role.get('key', '').lower()
                        if 'coach' in role_key or 'manager' in role_key:
                            continue
                    elif isinstance(role, str):
                        if 'coach' in role.lower() or 'manager' in role.lower():
                            continue
                    
                    if name:
                        # Try to get minutes played from various sources
                        minutes = 0
                        
                        # Check stats dict
                        stats = player.get('stats')
                        if isinstance(stats, dict):
                            minutes = stats.get('minutesPlayed', 0) or stats.get('minutes', 0)
                        
                        # Check direct fields
                        if not minutes:
                            minutes = player.get('minutesPlayed', 0)
                        
                        # Estimate from appearances if no minutes
                        if not minutes:
                            appearances = player.get('appearances', 0) or player.get('games', 0)
                            if appearances:
                                minutes = appearances * 60  # Estimate 60 min per game
                        
                        # If still no minutes, use position order as proxy
                        # (players listed first in squad are usually starters)
                        if not minutes:
                            minutes = 100 - len(all_players)  # Decreasing priority
                        
                        all_players.append({
                            'name': name,
                            'minutes': minutes,
                            'id': player.get('id')
                        })
            
            # Sort by minutes and take top 13
            all_players.sort(key=lambda x: x['minutes'], reverse=True)
            key_players = all_players[:13]
            
        except Exception as e:
            logger.error(f"Error extracting key starters: {e}")
        
        return key_players

    def _extract_predicted_lineup(self, match_data: Dict, team_id: int) -> Optional[List[str]]:
        """
        Extract predicted lineup from match data.
        
        SAFETY: Returns None if no predicted lineup available.
        
        Args:
            match_data: FotMob match details
            team_id: Team ID to extract lineup for
            
        Returns:
            List of player names in predicted lineup, or None if unavailable
        """
        try:
            # FotMob structure varies - try multiple paths
            content = match_data.get('content', {})
            lineup_data = content.get('lineup', {})
            
            if not lineup_data:
                # Try alternative path
                lineup_data = match_data.get('lineup', {})
            
            if not lineup_data:
                logger.info("⚠️ No lineup data available for this match")
                return None
            
            # Check for predicted lineup
            lineup_tab = lineup_data.get('lineup', [])
            
            if not lineup_tab:
                logger.info("⚠️ No predicted lineup available")
                return None
            
            # Find the correct team's lineup
            for team_lineup in lineup_tab:
                if not isinstance(team_lineup, dict):
                    continue
                
                lineup_team_id = team_lineup.get('teamId')
                
                if lineup_team_id == team_id:
                    players = []
                    
                    # Extract starting XI
                    starters = team_lineup.get('players', [])
                    
                    # FotMob lineup structure: list of position groups
                    for position_group in starters:
                        if isinstance(position_group, list):
                            for player in position_group:
                                if isinstance(player, dict):
                                    name = player.get('name', '')
                                    if name:
                                        players.append(name)
                        elif isinstance(position_group, dict):
                            name = position_group.get('name', '')
                            if name:
                                players.append(name)
                    
                    if players:
                        logger.info(f"✅ Found predicted lineup: {len(players)} players")
                        return players
            
            logger.info("⚠️ Team lineup not found in match data")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting predicted lineup: {e}")
            return None

    def get_turnover_risk(self, team_name: str) -> Optional[Dict]:
        """
        TURNOVER DETECTION: Compare predicted lineup vs key starters.
        
        Detects potential rotation by checking how many regular starters
        are missing from the predicted lineup.
        
        SAFETY: Returns None if predicted lineup is not available
        (common in lower leagues). Do not penalize in this case.
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with risk_level, missing_names, count
            OR None if lineup data unavailable
        """
        try:
            # Get team ID (use top-level import)
            team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
            if not team_id:
                team_id, _ = self.search_team_id(team_name)
            
            if not team_id:
                logger.warning(f"⚠️ Cannot check turnover - team not found: {team_name}")
                return None
            
            # Get team details for key starters
            team_data = self.get_team_details(team_id)
            if not team_data:
                return None
            
            # Extract key starters (top 13 by minutes)
            key_starters = self._extract_key_starters(team_data)
            
            if not key_starters:
                logger.info(f"⚠️ No key starters data for {team_name}")
                return None
            
            key_starter_names = {p['name'].lower() for p in key_starters}
            
            # Get next match ID
            next_match = team_data.get('nextMatch')
            if not next_match:
                fixtures = team_data.get('fixtures', {})
                next_match = fixtures.get('allFixtures', {}).get('nextMatch')
            
            if not next_match:
                logger.info(f"⚠️ No upcoming match for {team_name}")
                return None
            
            match_id = next_match.get('id')
            if not match_id:
                return None
            
            # Fetch match details for predicted lineup
            match_data = self.get_match_lineup(match_id)
            
            if not match_data:
                return None
            
            # Extract predicted lineup (SAFETY: may return None)
            predicted_lineup = self._extract_predicted_lineup(match_data, team_id)
            
            if predicted_lineup is None:
                # No predicted lineup available - graceful exit
                logger.info(f"📋 No predicted lineup for {team_name} - skipping turnover check")
                return None
            
            predicted_names = {p.lower() for p in predicted_lineup}
            
            # Calculate missing starters
            missing_starters = []
            for player in key_starters[:11]:  # Focus on top 11
                if player['name'].lower() not in predicted_names:
                    missing_starters.append(player['name'])
            
            turnover_count = len(missing_starters)
            
            # Determine risk level
            if turnover_count >= 5:
                risk_level = "HIGH"
            elif turnover_count >= 3:
                risk_level = "MEDIUM"
            elif turnover_count >= 1:
                risk_level = "LOW"
            else:
                risk_level = "NONE"
            
            result = {
                "risk_level": risk_level,
                "missing_names": missing_starters,
                "count": turnover_count,
                "key_starters_checked": len(key_starters[:11]),
                "predicted_lineup_size": len(predicted_lineup)
            }
            
            if turnover_count > 0:
                logger.info(f"🔄 TURNOVER [{risk_level}]: {team_name} missing {turnover_count} starters: {', '.join(missing_starters[:3])}...")
            else:
                logger.info(f"✅ No turnover detected for {team_name}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking turnover for {team_name}: {e}")
            return None


    def _extract_stat_value(self, stats_data: any, keywords: List[str], is_per_game: bool = False) -> Optional[float]:
        """
        Helper to extract stat values from nested FotMob JSON structures.
        
        Searches through various FotMob stat structures for matching labels.
        Handles multiple languages (EN, IT, ES, PT, DE, TR).
        
        Args:
            stats_data: FotMob stats data (can be list, dict, or nested)
            keywords: List of keywords to match (e.g., ["Corners", "Calci d'angolo"])
            is_per_game: If True, value is already per-game average
            
        Returns:
            Extracted float value or None
        """
        if not stats_data:
            return None
        
        def parse_value(val: any) -> Optional[float]:
            """Parse value handling comma decimals and strings."""
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                # Handle comma as decimal separator (European format)
                clean = val.replace(',', '.').strip()
                try:
                    return float(clean)
                except ValueError:
                    return None
            return None
        
        def search_in_structure(data: any, depth: int = 0) -> Optional[float]:
            """Recursively search for stat value in nested structures."""
            if depth > 10:  # Prevent infinite recursion
                return None
            
            if isinstance(data, dict):
                # Check if this dict has a matching title/label/name
                for key in ['title', 'label', 'name', 'key', 'statName']:
                    label = data.get(key, '')
                    if isinstance(label, str):
                        label_lower = label.lower()
                        for kw in keywords:
                            if kw.lower() in label_lower:
                                # Found match - extract value
                                for val_key in ['value', 'stat', 'statValue', 'per90', 'perGame', 'total', 'avg']:
                                    if val_key in data:
                                        parsed = parse_value(data[val_key])
                                        if parsed is not None:
                                            logger.debug(f"📊 Found {kw}: {parsed} (key: {val_key})")
                                            return parsed
                
                # Recurse into dict values
                for v in data.values():
                    result = search_in_structure(v, depth + 1)
                    if result is not None:
                        return result
                        
            elif isinstance(data, list):
                # Search each item in list
                for item in data:
                    result = search_in_structure(item, depth + 1)
                    if result is not None:
                        return result
            
            return None
        
        return search_in_structure(stats_data)

    def get_team_stats(self, team_name: str) -> Dict:
        """
        BETTING MARKETS ENGINE: Extract granular stats for Goals, Cards, Corners.
        
        V2.6 UPGRADE: Robust nested JSON parsing with multi-language support.
        
        Returns stats for:
        - Goals: Avg Scored + Avg Conceded -> High_Scoring signal
        - Cards: Avg Yellow/Red per game -> Aggressive signal
        - Corners: Direct stats OR Shots Proxy -> Corner potential
        
        CORNER KEYWORDS (multi-language):
        - EN: "Corners", "Total Corners", "Corners per match"
        - IT: "Calci d'angolo", "Corner"
        - ES: "Córners", "Tiros de esquina"
        - PT: "Escanteios"
        - DE: "Ecken"
        - TR: "Köşe vuruşları"
        
        SHOTS KEYWORDS (multi-language):
        - EN: "Shots on target", "Shots on target per match"
        - IT: "Tiri in porta", "Tiri nello specchio"
        - ES: "Tiros a puerta"
        - PT: "Chutes no gol"
        
        Args:
            team_name: Name of the team
            
        Returns:
            Dict with goals, cards, corners stats and signals
        """
        result = {
            "team": team_name,
            # Sample size (for Poisson reliability)
            "matches_played": None,
            "poisson_reliable": False,  # True if matches >= 5
            # Goals Engine
            "avg_goals_scored": None,
            "avg_goals_conceded": None,
            "goals_total": None,
            "goals_signal": "Unknown",
            # Cards Engine
            "avg_yellow_cards": None,
            "avg_red_cards": None,
            "avg_total_cards": None,
            "cards_signal": "Unknown",
            # Corners Engine
            "avg_corners": None,
            "corners_source": "Unknown",
            "avg_shots_on_target": None,
            "corners_signal": "Unknown",
            # Summary
            "stats_summary": "",
            "error": None
        }
        
        try:
            # Get team ID - prefer dynamic search over static mapping for accuracy
            team_id, _ = self.search_team_id(team_name)
            
            if not team_id:
                # Fallback to static mapping (use top-level import)
                team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
            
            if not team_id:
                result["error"] = "Team not found"
                return result
            
            # Get team details
            team_data = self.get_team_details(team_id)
            if not team_data:
                result["error"] = "Could not fetch team data"
                return result
            
            # Extract stats from various FotMob paths
            overview = team_data.get('overview', {})
            stats = team_data.get('stats', {})
            
            # Try to get season stats
            season_stats = stats.get('seasonStats', {})
            if not season_stats:
                season_stats = overview.get('stats', {})
            
            # Also check table for goals (FotMob uses 'table' as a list)
            table_list = team_data.get('table', [])
            
            # ========================================
            # GOALS ENGINE
            # ========================================
            goals_scored = None
            goals_conceded = None
            games_played = None
            
            # Path 1: From table data (most reliable) - FotMob structure: table[].data.table.all[]
            if table_list and isinstance(table_list, list):
                for table_item in table_list:
                    if not isinstance(table_item, dict):
                        continue
                    
                    # FotMob structure: table[].data.table.all[]
                    data_section = table_item.get('data', {})
                    if isinstance(data_section, dict):
                        rows = data_section.get('table', {}).get('all', [])
                    else:
                        rows = []
                    
                    # Fallback to old structure
                    if not rows:
                        rows = table_item.get('table', {}).get('all', [])
                    if not rows:
                        rows = table_item.get('all', [])
                    
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        row_name = row.get('name', '').lower()
                        row_short = row.get('shortName', '').lower()
                        row_id = row.get('id')
                        
                        # Match by name or ID
                        if team_name.lower() in row_name or team_name.lower() in row_short or row_id == team_id:
                            # Try direct fields first
                            goals_scored = row.get('scoresFor', row.get('goalsFor'))
                            goals_conceded = row.get('scoresAgainst', row.get('goalsAgainst'))
                            games_played = row.get('played', row.get('games'))
                            
                            # Parse scoresStr if direct fields are None (e.g., "32-11")
                            if goals_scored is None and row.get('scoresStr'):
                                scores_str = row.get('scoresStr', '')
                                if '-' in scores_str:
                                    try:
                                        parts = scores_str.split('-')
                                        goals_scored = int(parts[0])
                                        goals_conceded = int(parts[1])
                                        logger.info(f"📊 {team_name}: Parsed scoresStr '{scores_str}' -> GF:{goals_scored}, GA:{goals_conceded}")
                                    except (ValueError, IndexError):
                                        pass
                            
                            if games_played:
                                break
                    
                    if games_played:
                        break
            
            # Path 2: From season stats
            if not goals_scored and season_stats:
                goals_scored = season_stats.get('goalsScored', season_stats.get('goals'))
                goals_conceded = season_stats.get('goalsConceded')
                games_played = season_stats.get('gamesPlayed', season_stats.get('matches'))
            
            # Store matches played for Poisson reliability check
            if games_played:
                result["matches_played"] = games_played
                # Poisson is reliable with >= 5 matches sample size
                result["poisson_reliable"] = games_played >= 5
                if not result["poisson_reliable"]:
                    logger.warning(f"⚠️ {team_name}: Only {games_played} matches played - Poisson unreliable (need >= 5)")
            
            # Calculate averages
            if goals_scored is not None and games_played and games_played > 0:
                result["avg_goals_scored"] = round(goals_scored / games_played, 2)
            
            if goals_conceded is not None and games_played and games_played > 0:
                result["avg_goals_conceded"] = round(goals_conceded / games_played, 2)
            
            if result["avg_goals_scored"] and result["avg_goals_conceded"]:
                result["goals_total"] = round(result["avg_goals_scored"] + result["avg_goals_conceded"], 2)
                
                # Signal: High_Scoring if total > 2.8
                if result["goals_total"] > 2.8:
                    result["goals_signal"] = "High_Scoring"
                elif result["goals_total"] > 2.3:
                    result["goals_signal"] = "Medium"
                else:
                    result["goals_signal"] = "Low_Scoring"
                
                logger.info(f"⚽ {team_name} Goals: {result['avg_goals_scored']} scored, {result['avg_goals_conceded']} conceded (Total: {result['goals_total']} - {result['goals_signal']})")
            
            # ========================================
            # CARDS ENGINE (Discipline)
            # ========================================
            yellow_cards = None
            red_cards = None
            
            # Path 1: From season stats
            if season_stats:
                yellow_cards = season_stats.get('yellowCards', season_stats.get('yellows'))
                red_cards = season_stats.get('redCards', season_stats.get('reds'))
            
            # Path 2: From overview stats
            if not yellow_cards and overview:
                overview_stats = overview.get('stats', [])
                if isinstance(overview_stats, list):
                    for stat_group in overview_stats:
                        if isinstance(stat_group, dict):
                            items = stat_group.get('items', [])
                            for item in items:
                                if isinstance(item, dict):
                                    title = item.get('title', '').lower()
                                    if 'yellow' in title:
                                        yellow_cards = item.get('value')
                                    elif 'red' in title:
                                        red_cards = item.get('value')
            
            # Calculate averages
            if yellow_cards is not None and games_played and games_played > 0:
                result["avg_yellow_cards"] = round(yellow_cards / games_played, 2)
            
            if red_cards is not None and games_played and games_played > 0:
                result["avg_red_cards"] = round(red_cards / games_played, 2)
            
            if result["avg_yellow_cards"] is not None:
                result["avg_total_cards"] = round(
                    (result["avg_yellow_cards"] or 0) + (result["avg_red_cards"] or 0), 2
                )
                
                # Signal: Aggressive if avg cards > 2.5
                if result["avg_total_cards"] > 2.5:
                    result["cards_signal"] = "Aggressive"
                elif result["avg_total_cards"] > 1.8:
                    result["cards_signal"] = "Medium"
                else:
                    result["cards_signal"] = "Disciplined"
                
                logger.info(f"🟨 {team_name} Cards: {result['avg_yellow_cards']} yellow, {result['avg_red_cards'] or 0} red (Total: {result['avg_total_cards']} - {result['cards_signal']})")
            
            # ========================================
            # CORNERS ENGINE (V2.6 - Robust Nested Parsing)
            # ========================================
            corners = None
            shots_on_target = None
            
            # Multi-language corner keywords
            corner_keywords = [
                "Corners", "Total Corners", "Corners per match", "Corners won",
                "Calci d'angolo", "Corner",  # Italian
                "Córners", "Tiros de esquina",  # Spanish
                "Escanteios",  # Portuguese
                "Ecken",  # German
                "Köşe vuruşları"  # Turkish
            ]
            
            # Multi-language shots keywords
            shots_keywords = [
                "Shots on target", "Shots on target per match", "Accurate shots",
                "Tiri in porta", "Tiri nello specchio",  # Italian
                "Tiros a puerta", "Tiros a portería",  # Spanish
                "Chutes no gol", "Finalizações certas",  # Portuguese
                "Schüsse aufs Tor",  # German
                "İsabetli şutlar"  # Turkish
            ]
            
            # PLAN A: Search for direct corner stats using robust helper
            # Search in multiple FotMob data paths
            search_paths = [
                season_stats,
                overview.get('stats', []),
                stats.get('stats', []),
                team_data.get('stats', {}).get('stats', []),
                team_data.get('overview', {}).get('stats', [])
            ]
            
            for search_path in search_paths:
                if corners is None and search_path:
                    corners = self._extract_stat_value(search_path, corner_keywords)
                    if corners is not None:
                        logger.info(f"🚩 {team_name}: Found corners in FotMob data: {corners}")
                        break
            
            if corners is not None and games_played and games_played > 0:
                # If corners is total (> 20), calculate per game
                if corners > 20:
                    result["avg_corners"] = round(corners / games_played, 2)
                else:
                    result["avg_corners"] = round(corners, 2)
                result["corners_source"] = "Direct"
                
                # Signal based on direct corners (TUNED THRESHOLDS)
                if result["avg_corners"] > 5.0:
                    result["corners_signal"] = "High"
                elif result["avg_corners"] > 4.0:
                    result["corners_signal"] = "Medium"
                else:
                    result["corners_signal"] = "Low"
                
                logger.info(f"🚩 {team_name} Corners: {result['avg_corners']} per game (Direct - {result['corners_signal']})")
            
            else:
                # PLAN B: Shots Proxy - search using robust helper
                logger.info(f"🔄 {team_name}: No direct corner stats, using Shots Proxy...")
                
                for search_path in search_paths:
                    if shots_on_target is None and search_path:
                        shots_on_target = self._extract_stat_value(search_path, shots_keywords)
                        if shots_on_target is not None:
                            logger.info(f"🎯 {team_name}: Found shots on target: {shots_on_target}")
                            break
                
                if shots_on_target is not None:
                    # If total (> 20), calculate per game
                    if shots_on_target > 20 and games_played and games_played > 0:
                        result["avg_shots_on_target"] = round(shots_on_target / games_played, 2)
                    else:
                        result["avg_shots_on_target"] = round(shots_on_target, 2)
                    
                    result["corners_source"] = "Shots_Proxy"
                    
                    # PROXY LOGIC (TUNED THRESHOLDS):
                    # shots_on_target > 4.5 -> HIGH corner potential (heavy pressure)
                    # shots_on_target < 2.5 -> LOW corner potential
                    if result["avg_shots_on_target"] > 4.5:
                        result["corners_signal"] = "High"
                    elif result["avg_shots_on_target"] > 3.5:
                        result["corners_signal"] = "Medium"
                    elif result["avg_shots_on_target"] < 2.5:
                        result["corners_signal"] = "Low"
                    else:
                        result["corners_signal"] = "Medium"
                    
                    logger.info(f"🎯 {team_name} Shots on Target: {result['avg_shots_on_target']} -> Corner Proxy: {result['corners_signal']}")
                else:
                    result["corners_source"] = "Unavailable"
                    result["corners_signal"] = "Unknown"
                    logger.info(f"⚠️ {team_name}: No corner or shots data available")
            
            # ========================================
            # BUILD SUMMARY STRING
            # ========================================
            summary_parts = []
            
            if result["goals_total"]:
                summary_parts.append(f"Goals {result['goals_total']}")
            
            if result["avg_total_cards"]:
                summary_parts.append(f"Cards {result['avg_total_cards']}")
            
            if result["avg_corners"]:
                summary_parts.append(f"Corners {result['avg_corners']}")
            elif result["avg_shots_on_target"]:
                summary_parts.append(f"ShotsOnTarget {result['avg_shots_on_target']} (Corner Proxy: {result['corners_signal']})")
            
            result["stats_summary"] = ", ".join(summary_parts) if summary_parts else "No stats available"
            
        except Exception as e:
            logger.error(f"Error getting team stats for {team_name}: {e}")
            result["error"] = str(e)
        
        return result

    def get_tactical_insights(self, home_team: str, away_team: str) -> Dict:
        """
        TACTICAL ANALYSIS: Extract Home/Away form contrast, style, and defensive leaks.
        
        Used by the "Deep Dive" investigation to gather tactical context.
        
        Signals:
        - Fortress: Home PPG > 2.0 (strong at home)
        - Travel Sick: Away PPG < 0.8 (weak on the road)
        - High Possession: >55% possession (control style)
        - Counter Attack: <40% possession but high shots (counter style)
        - Leaky Defense: >1.8 goals conceded per game
        
        Args:
            home_team: Home team name
            away_team: Away team name
            
        Returns:
            Dict with tactical summary and signals
        """
        result = {
            "home_team": home_team,
            "away_team": away_team,
            "home_ppg": None,
            "home_ppg_home": None,  # PPG at home only
            "away_ppg": None,
            "away_ppg_away": None,  # PPG away only
            "home_goals_conceded": None,
            "away_goals_conceded": None,
            "home_signal": None,
            "away_signal": None,
            "tactical_summary": "",
            "error": None
        }
        
        try:
            # Get stats for both teams
            home_stats = self.get_team_stats(home_team)
            away_stats = self.get_team_stats(away_team)
            
            # Get table context for PPG
            home_table = self.get_table_context(home_team)
            away_table = self.get_table_context(away_team)
            
            signals = []
            
            # ========================================
            # HOME TEAM ANALYSIS
            # ========================================
            if home_stats and not home_stats.get('error'):
                # Goals conceded
                if home_stats.get('avg_goals_conceded'):
                    result["home_goals_conceded"] = home_stats['avg_goals_conceded']
                    if home_stats['avg_goals_conceded'] > 1.8:
                        signals.append(f"⚠️ {home_team} LEAKY DEFENSE ({home_stats['avg_goals_conceded']:.1f} conceded/game)")
            
            # PPG from table context
            if home_table and home_table.get('points') and home_table.get('position'):
                # Estimate PPG (rough calculation)
                matches_played = home_stats.get('matches_played') if home_stats else None
                if matches_played and matches_played > 0:
                    ppg = home_table['points'] / matches_played
                    result["home_ppg"] = round(ppg, 2)
                    
                    # Fortress signal (assume home PPG is ~1.3x overall PPG)
                    estimated_home_ppg = ppg * 1.3
                    result["home_ppg_home"] = round(estimated_home_ppg, 2)
                    
                    if estimated_home_ppg > 2.0:
                        result["home_signal"] = "FORTRESS"
                        signals.append(f"🏰 {home_team} is a FORTRESS at home (~{estimated_home_ppg:.1f} PPG)")
            
            # ========================================
            # AWAY TEAM ANALYSIS
            # ========================================
            if away_stats and not away_stats.get('error'):
                # Goals conceded
                if away_stats.get('avg_goals_conceded'):
                    result["away_goals_conceded"] = away_stats['avg_goals_conceded']
                    if away_stats['avg_goals_conceded'] > 1.8:
                        signals.append(f"⚠️ {away_team} LEAKY DEFENSE ({away_stats['avg_goals_conceded']:.1f} conceded/game)")
            
            # PPG from table context
            if away_table and away_table.get('points') and away_table.get('position'):
                matches_played = away_stats.get('matches_played') if away_stats else None
                if matches_played and matches_played > 0:
                    ppg = away_table['points'] / matches_played
                    result["away_ppg"] = round(ppg, 2)
                    
                    # Travel Sick signal (assume away PPG is ~0.7x overall PPG)
                    estimated_away_ppg = ppg * 0.7
                    result["away_ppg_away"] = round(estimated_away_ppg, 2)
                    
                    if estimated_away_ppg < 0.8:
                        result["away_signal"] = "TRAVEL_SICK"
                        signals.append(f"🤢 {away_team} is TRAVEL SICK (~{estimated_away_ppg:.1f} PPG away)")
            
            # ========================================
            # BUILD TACTICAL SUMMARY
            # ========================================
            if signals:
                result["tactical_summary"] = " | ".join(signals)
            else:
                result["tactical_summary"] = f"No strong tactical signals detected for {home_team} vs {away_team}"
            
            logger.info(f"🎯 Tactical Insights: {result['tactical_summary']}")
            
        except Exception as e:
            logger.error(f"Error getting tactical insights: {e}")
            result["error"] = str(e)
            result["tactical_summary"] = f"Error: {str(e)}"
        
        return result

    # ============================================
    # MOTIVATION ENGINE - League Table Context
    # ============================================
    def get_league_table_context(
        self,
        league_id: int,
        home_team_id: int = None,
        away_team_id: int = None,
        home_team_name: str = None,
        away_team_name: str = None
    ) -> Dict:
        """
        Fetch league table and determine motivation context for both teams.
        
        Strategy: "Bet on desperate teams vs unmotivated teams"
        - Relegation zone teams are DESPERATE (high motivation)
        - Title/Europe zone teams are HUNGRY (high motivation)
        - Mid-table safe teams may lack motivation
        
        Args:
            league_id: FotMob league ID
            home_team_id: FotMob team ID for home team (optional)
            away_team_id: FotMob team ID for away team (optional)
            home_team_name: Team name for fuzzy matching if ID not provided
            away_team_name: Team name for fuzzy matching if ID not provided
            
        Returns:
            Dict with motivation context for both teams
        """
        result = {
            "home_rank": None,
            "home_points": None,
            "home_zone": "Unknown",
            "home_form": None,
            "home_goal_diff": None,
            "away_rank": None,
            "away_points": None,
            "away_zone": "Unknown",
            "away_form": None,
            "away_goal_diff": None,
            "total_teams": None,
            "motivation_mismatch": False,
            "motivation_summary": "",
            "error": None
        }
        
        if not league_id:
            result["error"] = "No league_id provided"
            return result
        
        try:
            # Fetch league table from FotMob
            url = f"{self.BASE_URL}/leagues?id={league_id}"
            self._rate_limit()
            resp = self._make_request(url)
            
            if not resp:
                result["error"] = "Failed to fetch league data"
                return result
            
            try:
                data = resp.json()
            except ValueError:
                result["error"] = "Invalid JSON response"
                return result
            
            # Extract table data - FotMob structure varies
            table_data = None
            
            # Path 1: data.table[0].data.table.all
            tables = data.get('table', [])
            if tables and isinstance(tables, list):
                for t in tables:
                    if isinstance(t, dict):
                        inner = t.get('data', {}).get('table', {}).get('all', [])
                        if inner:
                            table_data = inner
                            break
                        # Alternative: direct 'all' key
                        inner = t.get('data', {}).get('table', {}).get('tables', [])
                        if inner and isinstance(inner, list) and inner:
                            table_data = inner[0].get('table', [])
                            break
            
            # Path 2: data.table (direct array)
            if not table_data:
                if isinstance(tables, list) and tables:
                    first = tables[0]
                    if isinstance(first, dict) and 'table' in first:
                        table_data = first.get('table', [])
            
            # Path 3: data.standings
            if not table_data:
                standings = data.get('standings', [])
                if standings:
                    table_data = standings
            
            if not table_data:
                result["error"] = "Could not parse league table"
                logger.warning(f"⚠️ Could not parse table for league {league_id}")
                return result
            
            total_teams = len(table_data)
            result["total_teams"] = total_teams
            
            # Define zones based on league size
            europe_cutoff = min(4, total_teams // 4) if total_teams > 8 else 2
            relegation_cutoff = total_teams - 3 if total_teams > 6 else total_teams - 1
            
            def determine_zone(rank: int) -> str:
                if rank <= europe_cutoff:
                    return "TITLE/EUROPE"
                elif rank >= relegation_cutoff:
                    return "RELEGATION"
                else:
                    return "MID-TABLE"
            
            def extract_form(team_entry: dict) -> str:
                """Extract last 5 results form string."""
                form = team_entry.get('form', [])
                if isinstance(form, list):
                    # Form is list of dicts with 'result' key or just strings
                    form_str = ""
                    for f in form[-5:]:
                        if isinstance(f, dict):
                            result_val = f.get('result', '?')
                            # Safety: handle empty string or None
                            form_str += result_val[0].upper() if result_val else '?'
                        elif isinstance(f, str):
                            form_str += f[0].upper() if f else '?'
                    return form_str if form_str else None
                return None
            
            # Find teams in table
            for entry in table_data:
                if not isinstance(entry, dict):
                    continue
                
                entry_id = entry.get('id') or entry.get('teamId')
                entry_name = entry.get('name') or entry.get('teamName', '')
                rank = entry.get('idx') or entry.get('position') or entry.get('rank')
                points = entry.get('pts') or entry.get('points')
                goal_diff = entry.get('goalConDiff') or entry.get('gd') or entry.get('goalDifference')
                
                # Match home team
                home_matched = False
                if home_team_id and entry_id == home_team_id:
                    home_matched = True
                elif home_team_name and entry_name:
                    # Fuzzy match
                    if (home_team_name.lower() in entry_name.lower() or 
                        entry_name.lower() in home_team_name.lower()):
                        home_matched = True
                
                if home_matched and rank:
                    result["home_rank"] = rank
                    result["home_points"] = points
                    result["home_goal_diff"] = goal_diff
                    result["home_zone"] = determine_zone(rank)
                    result["home_form"] = extract_form(entry)
                
                # Match away team
                away_matched = False
                if away_team_id and entry_id == away_team_id:
                    away_matched = True
                elif away_team_name and entry_name:
                    if (away_team_name.lower() in entry_name.lower() or 
                        entry_name.lower() in away_team_name.lower()):
                        away_matched = True
                
                if away_matched and rank:
                    result["away_rank"] = rank
                    result["away_points"] = points
                    result["away_goal_diff"] = goal_diff
                    result["away_zone"] = determine_zone(rank)
                    result["away_form"] = extract_form(entry)
            
            # Determine motivation mismatch
            desperate_zones = {"TITLE/EUROPE", "RELEGATION"}
            safe_zone = "MID-TABLE"
            
            home_desperate = result["home_zone"] in desperate_zones
            away_desperate = result["away_zone"] in desperate_zones
            home_safe = result["home_zone"] == safe_zone
            away_safe = result["away_zone"] == safe_zone
            
            if (home_desperate and away_safe) or (away_desperate and home_safe):
                result["motivation_mismatch"] = True
            
            # Build summary
            summaries = []
            if result["home_rank"]:
                form_str = f", Form: {result['home_form']}" if result["home_form"] else ""
                summaries.append(f"Home: #{result['home_rank']} ({result['home_zone']}){form_str}")
            if result["away_rank"]:
                form_str = f", Form: {result['away_form']}" if result["away_form"] else ""
                summaries.append(f"Away: #{result['away_rank']} ({result['away_zone']}){form_str}")
            
            if result["motivation_mismatch"]:
                summaries.append("⚠️ MOTIVATION MISMATCH DETECTED")
            
            result["motivation_summary"] = " | ".join(summaries) if summaries else "Table context unavailable"
            
            logger.info(f"📊 League Table Context: {result['motivation_summary']}")
            
        except Exception as e:
            logger.error(f"Error fetching league table context: {e}")
            result["error"] = str(e)
        
        return result


# Singleton instance
_provider_instance = None


def get_data_provider() -> FotMobProvider:
    """
    Get singleton instance of FotMobProvider.
    
    Returns:
        FotMobProvider instance
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = FotMobProvider()
    return _provider_instance


# ============================================
# CACHED WRAPPER FUNCTIONS (lru_cache)
# ============================================
# These functions wrap FotMobProvider methods with lru_cache
# to reduce API traffic by 30-40% for static data lookups.

@functools.lru_cache(maxsize=128)
def get_team_id_cached(team_name: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Cached wrapper for team ID lookup.
    
    Team IDs are static data - caching reduces FotMob API calls significantly.
    Cache persists for the lifetime of the process.
    
    Args:
        team_name: Name of the team to search
        
    Returns:
        Tuple of (team_id, fotmob_name) or (None, None)
    """
    provider = get_data_provider()
    return provider.search_team_id(team_name)


@functools.lru_cache(maxsize=64)
def get_table_context_cached(team_name: str) -> Dict:
    """
    Cached wrapper for league table context.
    
    Table positions change infrequently (once per matchday).
    Cache reduces redundant API calls during analysis runs.
    
    Args:
        team_name: Name of the team
        
    Returns:
        Dict with position, zone, motivation level
    """
    provider = get_data_provider()
    return provider.get_table_context(team_name)


def clear_static_cache() -> None:
    """
    Clear all lru_cache entries.
    
    Call this at the start of a new analysis cycle or daily
    to ensure fresh data is fetched.
    """
    get_team_id_cached.cache_clear()
    get_table_context_cached.cache_clear()
    logger.info("🗑️ Cache FotMob svuotata")
