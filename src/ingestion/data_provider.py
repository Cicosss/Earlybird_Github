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
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

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
FOTMOB_MIN_REQUEST_INTERVAL = 1.0
FOTMOB_REQUEST_TIMEOUT = 15
FOTMOB_MAX_RETRIES = 3

# V6.1: Thread-safe rate limiting for VPS multi-thread scenarios
import threading
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
        'Ħ': 'H', 'ħ': 'h',
        'Ł': 'L', 'ł': 'l',
        'Đ': 'D', 'đ': 'd',
        'Ø': 'O', 'ø': 'o',
        'Æ': 'AE', 'æ': 'ae',
        'Œ': 'OE', 'œ': 'oe',
        'ß': 'ss',
        'Þ': 'Th', 'þ': 'th',
        'Ð': 'D', 'ð': 'd',
    }
    
    result = text
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)
    
    normalized = unicodedata.normalize('NFKD', result)
    ascii_text = normalized.encode('ASCII', 'ignore').decode('utf-8')
    return ascii_text.strip()


def fuzzy_match_team(search_name: str, candidates: List[str], threshold: float = 0.6) -> Optional[str]:
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
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.fotmob.com/',
        'Origin': 'https://www.fotmob.com'
    }
    
    PREFIXES_TO_STRIP = [
        "FC", "AS", "AC", "SC", "SV", "SK", "FK", "IF", "BK", "CF", "CD",
        "FSV", "TSG", "VfB", "VfL", "SpVgg", "SG", "TuS", "SSV",
        "HNK", "HSK", "HŠK", "NK", "GNK", "RNK",
        "KAA", "KV", "KRC", "KSC", "KVC", "KFCO",
        "Real", "Sporting", "Club", "Deportivo", "Atlético", "Atletico",
        "Athletic", "Racing", "United", "City", "Dynamo", "Dinamo"
    ]
    
    SUFFIXES_TO_STRIP = [
        "FC", "SC", "SK", "FK", "IF", "BK", "CF", "AC", "AS", "SV",
        "United", "City", "Calcio", "Spor", "Club"
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
        "Sivasspor": "Sivasspor",
        "Başakşehir": "Istanbul Basaksehir",
        "Istanbul Basaksehir FK": "Istanbul Basaksehir",
        "Gazişehir Gaziantep": "Gaziantep FK",
        "Gazisehir Gaziantep": "Gaziantep FK",
        "Gaziantep": "Gaziantep FK",
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
        """Enforce minimum interval between FotMob requests to avoid bans."""
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
        """Make HTTP request with retry logic and specific error handling."""
        self._rate_limit()
        
        for attempt in range(retries):
            self._rotate_user_agent()
            
            try:
                resp = self.session.get(url, timeout=FOTMOB_REQUEST_TIMEOUT)
                
                if resp.status_code == 200:
                    return resp
                
                if resp.status_code == 429:
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"⚠️ FotMob rate limit (429). Attesa {delay}s prima del retry {attempt + 1}/{retries}")
                    time.sleep(delay)
                    continue
                
                if resp.status_code in (502, 503, 504):
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"⚠️ FotMob server error ({resp.status_code}). Retry {attempt + 1}/{retries} in {delay}s")
                    time.sleep(delay)
                    continue
                
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
        """Search for teams on FotMob with robust error handling."""
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
            if name.lower().startswith(prefix.lower() + " "):
                stripped = name[len(prefix):].strip()
                if len(stripped) >= 3:
                    return stripped
        return name
    
    def _strip_suffix(self, team_name: str) -> str:
        """Strip common suffixes from team name."""
        name = team_name.strip()
        for suffix in self.SUFFIXES_TO_STRIP:
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
        """Find FotMob team ID for a team name with fuzzy matching."""
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
                team_id = results[0]['id']
                fotmob_name = results[0]['name']
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Mapped: {team_name} → {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name
        
        results = self.search_team(team_name)
        
        if results:
            for r in results:
                if r['name'].lower() == team_name.lower():
                    self._team_cache[cache_key] = (r['id'], r['name'])
                    logger.info(f"✅ Exact match: {r['name']} (ID: {r['id']})")
                    return r['id'], r['name']
            
            candidate_names = [r['name'] for r in results]
            best_match = fuzzy_match_team(team_name, candidate_names)
            
            if best_match:
                for r in results:
                    if r['name'] == best_match:
                        self._team_cache[cache_key] = (r['id'], r['name'])
                        return r['id'], r['name']
            
            if len(results) == 1 or SequenceMatcher(None, team_name.lower(), results[0]['name'].lower()).ratio() > 0.5:
                team_id = results[0]['id']
                fotmob_name = results[0]['name']
                self._team_cache[cache_key] = (team_id, fotmob_name)
                logger.info(f"✅ Found: {fotmob_name} (ID: {team_id})")
                return team_id, fotmob_name
        
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
                
                if len(results) == 1:
                    team_id = results[0]['id']
                    fotmob_name = results[0]['name']
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Prefix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name
        
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
                
                if len(results) == 1:
                    team_id = results[0]['id']
                    fotmob_name = results[0]['name']
                    self._team_cache[cache_key] = (team_id, fotmob_name)
                    logger.info(f"✅ Suffix-stripped: {team_name} → {fotmob_name} (ID: {team_id})")
                    return team_id, fotmob_name
        
        first_word = team_name.split()[0] if team_name else ""
        if first_word and len(first_word) >= 4 and first_word.lower() != team_name.lower():
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
        """Get team details including squad and next match."""
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
                return {
                    "_error": True,
                    "_error_msg": "Dati FotMob non disponibili",
                    "team_id": team_id,
                    "squad": {},
                    "fixtures": {}
                }
            
            try:
                data = resp.json()
                
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
        """Extract injured/unavailable players from team squad data."""
        injuries = []
        
        if not team_data or not isinstance(team_data, dict):
            return injuries
        
        try:
            squad_data = team_data.get('squad', {})
            
            if isinstance(squad_data, dict):
                squad_groups = squad_data.get('squad', [])
            else:
                squad_groups = squad_data if isinstance(squad_data, list) else []
            
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
                    
                    injury = player.get('injury')
                    if injury:
                        injuries.append({
                            'name': player.get('name', 'Unknown'),
                            'reason': injury.get('type', 'Injury') if isinstance(injury, dict) else str(injury),
                            'status': injury.get('expectedReturn', 'Unknown') if isinstance(injury, dict) else 'Unknown',
                            'is_injured': True
                        })
                    
                    injury_info = player.get('injuryInformation')
                    if injury_info and isinstance(injury_info, dict):
                        if not any(i['name'] == player.get('name') for i in injuries):
                            injuries.append({
                                'name': player.get('name', 'Unknown'),
                                'reason': injury_info.get('injuryType', 'Injury'),
                                'status': injury_info.get('expectedReturn', 'Unknown'),
                                'is_injured': True
                            })
                    
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
            
            if is_home is None:
                logger.debug(f"FotMob 'is_home' field missing, trusting Odds API order")
                return odds_home_team, odds_away_team, False
                
            # Verify that the opponent in the fixture matches the expected away team
            # This prevents swapping when the fixture is for a different match altogether
            fixture_opponent = fixture.get('opponent', '')
            if fixture_opponent and odds_away_team:
                expected_opponent = normalize_unicode(odds_away_team).lower()
                actual_opponent = normalize_unicode(fixture_opponent).lower()
                
                if expected_opponent not in actual_opponent and actual_opponent not in expected_opponent:
                    logger.debug(f"FotMob opponent mismatch: expected '{odds_away_team}', got '{fixture_opponent}'")
                    logger.debug("Trusting Odds API order due to mismatch")
                    return odds_home_team, odds_away_team, False
                
            if is_home:
                # Team is confirmed as home by FotMob - no swap needed
                return odds_home_team, odds_away_team, False
            else:
                # Team is away according to FotMob - swap them
                logger.warning(f"⚠️ Home/Away inverted by Odds API: {odds_home_team} vs {odds_away_team}")
                logger.warning(f"✅ Corrected to: {odds_away_team} vs {odds_home_team}")
                return odds_away_team, odds_home_team, True
                
        except Exception as e:
            logger.error(f"Home/Away validation failed: {e}")
            return odds_home_team, odds_away_team, False

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
            
            # V5.1: Validate home/away order against Odds API
            if home_team and away_team and home_team != away_team:
                validated_home, validated_away, swapped = self.validate_home_away_order(
                    home_team, away_team
                )
                result['home_team'] = validated_home
                result['away_team'] = validated_away
                
                if swapped:
                    logger.info(f"✅ Home/Away aligned to Odds API for {home_team} vs {away_team}")
            
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
            
            # Kickoff time validation
            if match_date:
                match_time = result.get('match_time')
                if match_time:
                    try:
                        from dateutil import parser
                        import pytz
                        
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
                                logger.warning(f"⚠️ Match time mismatch: found {match_dt}, expected {expected_dt}")
                                logger.warning(f"⚠️ Delta {delta_hours:.1f}h exceeds 4h tolerance - rejecting")
                                return None
                            else:
                                logger.debug(f"✅ Match time validated: diff={delta_hours:.1f}h (within 4h tolerance)")
                    except ImportError:
                        # dateutil not available, fall back to basic parsing
                        logger.debug("dateutil not available, skipping strict time validation")
                    except Exception as e:
                        logger.debug(f"Date validation error (non-critical): {e}")
        
        return result

    def get_match_lineup(self, match_id: int) -> Optional[Dict]:
        """Get match lineup and detailed match data using match ID."""
        cache_key = f"match_lineup:{match_id}"
        if _SMART_CACHE_AVAILABLE:
            cached = get_match_cache().get(cache_key)
            if cached is not None:
                return cached
        
        try:
            url = f"{self.BASE_URL}/matches?matchId={match_id}"
            resp = self._make_request(url)
            
            if resp is None:
                logger.warning(f"⚠️ FotMob match lineup non disponibili per ID {match_id}")
                return None
            
            try:
                data = resp.json()
                
                if _SMART_CACHE_AVAILABLE and data:
                    get_match_cache().set(cache_key, data)
                
                return data
            except ValueError as e:
                logger.error(f"❌ FotMob match lineup JSON non valido: {e}")
                return None
            
        except Exception as e:
            logger.error(f"❌ FotMob Match Lineup Error: {e}")
            return None

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
                        if position is not None and isinstance(position, (int, float)) and position > 0 and position <= total_teams:
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
                            result["points"] = row.get('pts')
                            result["played"] = row.get('played')
                            result["form"] = self._extract_form(row)
                            
                            return result
        
        except Exception as e:
            logger.error(f"Error getting table context for {team_name}: {e}")
            result["error"] = str(e)
        
        return result

    def _extract_form(self, team_row: Dict) -> Optional[str]:
        """Extract last 5 matches form string from table row."""
        form = team_row.get('form', [])
        if isinstance(form, list):
            form_str = ""
            for f in form[-5:]:
                if isinstance(f, dict):
                    result_val = f.get('result', '?')
                    form_str += result_val[0].upper() if result_val else '?'
                elif isinstance(f, str):
                    form_str += f[0].upper() if f else '?'
            return form_str if form_str else None
        return None

    def get_fixture_details(self, team_name: str) -> Optional[Dict]:
        """Get fixture details for a team's next match."""
        team_id = get_fotmob_team_id(team_name) if _TEAM_MAPPING_AVAILABLE else None
        fotmob_name = team_name
        
        if not team_id:
            team_id, fotmob_name = self.search_team_id(team_name)
        
        if not team_id:
            return {"error": f"Team not found: {team_name}", "source": "FotMob"}
        
        try:
            team_data = self.get_team_details(team_id)
            if not team_data:
                return {"error": "Could not fetch team details", "source": "FotMob"}
            
            injuries = self._extract_squad_injuries(team_data, fotmob_name)
            
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
            is_home = next_match.get('home', None)
            
            return {
                "team_id": team_id,
                "team_name": fotmob_name,
                "match_id": match_id,
                "opponent": next_match.get('opponent', {}).get('name', 'Unknown'),
                "match_time": next_match.get('utcTime'),
                "is_home": is_home,
                "injuries": injuries,
                "confirmed_absentees": injuries,
                "source": "FotMob"
            }
            
        except Exception as e:
            logger.error(f"FotMob Fixture Error: {e}")
            return {"error": str(e), "source": "FotMob"}


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
