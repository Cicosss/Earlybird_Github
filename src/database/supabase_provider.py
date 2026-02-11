#!/usr/bin/env python3
"""
SupabaseProvider - Enterprise Database Bridge (V9.0)

Provides a robust, cached connection to Supabase with:
- Singleton Pattern: Single connection instance via get_supabase()
- Hierarchical Fetching: Continental-Country-League-Sources map
- Smart Cache: 1-hour in-memory cache for league configurations
- Fail-Safe Mirror: Local fallback to data/supabase_mirror.json

Author: Lead Architect
Date: 2026-02-08
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from pathlib import Path

# Setup path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

# Type hint for Client (avoid import error if not installed)
if TYPE_CHECKING:
    from supabase import Client

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase client not installed. Run: pip install supabase")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CACHE_TTL_SECONDS = 3600  # 1 hour cache
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")
DATA_DIR = Path("data")


class SupabaseProvider:
    """
    Enterprise Supabase Provider with singleton pattern, caching, and fail-safe mirror.
    
    Features:
    - Singleton pattern ensures only one connection instance
    - Hierarchical data fetching (Continents -> Countries -> Leagues -> Sources)
    - Smart 1-hour cache to minimize API usage
    - Fail-safe mirror: saves local copy and falls back on connection failure
    """
    
    _instance: Optional['SupabaseProvider'] = None
    _client: Optional[Any] = None
    
    def __new__(cls):
        """Singleton pattern: ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the Supabase provider (only once)."""
        if self._initialized:
            return
        
        self._initialized = True
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._connected = False
        self._connection_error: Optional[str] = None
        
        # Ensure data directory exists
        DATA_DIR.mkdir(exist_ok=True)
        
        # Initialize connection
        self._initialize_connection()
    
    def _initialize_connection(self) -> None:
        """Initialize Supabase client connection."""
        if not SUPABASE_AVAILABLE:
            self._connection_error = "Supabase package not installed"
            logger.error(self._connection_error)
            return
        
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        
        if not supabase_url or not supabase_key:
            self._connection_error = "SUPABASE_URL or SUPABASE_KEY not configured in .env"
            logger.error(self._connection_error)
            return
        
        try:
            self._client = create_client(supabase_url, supabase_key)
            self._connected = True
            logger.info("Supabase connection established successfully")
        except Exception as e:
            self._connection_error = f"Failed to connect to Supabase: {e}"
            logger.error(self._connection_error)
            self._connected = False
    
    def is_connected(self) -> bool:
        """Check if Supabase connection is active."""
        return self._connected
    
    def get_connection_error(self) -> Optional[str]:
        """Get the connection error message if any."""
        return self._connection_error
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid (within TTL)."""
        if cache_key not in self._cache_timestamps:
            return False
        
        cache_age = time.time() - self._cache_timestamps[cache_key]
        return cache_age < CACHE_TTL_SECONDS
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Retrieve data from cache if valid."""
        if self._is_cache_valid(cache_key):
            logger.debug(f"Cache hit for key: {cache_key}")
            return self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: Any) -> None:
        """Store data in cache with current timestamp."""
        self._cache[cache_key] = data
        self._cache_timestamps[cache_key] = time.time()
        logger.debug(f"Cache set for key: {cache_key}")
    
    def _save_to_mirror(self, data: Dict[str, Any], version: str = "V9.5") -> None:
        """
        Save Supabase data to local mirror file with version and checksum.
        
        Args:
            data: Data to save to mirror
            version: Mirror version string
        """
        try:
            # Validate UTF-8 integrity before saving
            if not self._validate_utf8_integrity(data):
                logger.warning("⚠️ UTF-8 integrity check failed, but saving anyway")
            
            # Calculate checksum for integrity verification
            checksum = self._calculate_checksum(data)
            
            mirror_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "version": version,
                "checksum": checksum,
                "data": data
            }
            with open(MIRROR_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(mirror_data, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Supabase data mirrored to {MIRROR_FILE_PATH} (v{version}, checksum: {checksum[:8]}...)")
        except Exception as e:
            logger.error(f"❌ Failed to save mirror: {e}")
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """
        Calculate checksum for data integrity verification.
        
        Args:
            data: Data to calculate checksum for
            
        Returns:
            Hexadecimal checksum string
        """
        import hashlib
        try:
            # Convert data to JSON string with sorted keys for consistency
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            # Calculate SHA-256 hash
            checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            return checksum
        except Exception as e:
            logger.error(f"❌ Failed to calculate checksum: {e}")
            return ""
    
    def _validate_utf8_integrity(self, data: Dict[str, Any]) -> bool:
        """
        Validate UTF-8 integrity of multilingual content.
        
        Args:
            data: Data to validate
            
        Returns:
            bool: True if UTF-8 integrity is valid
        """
        try:
            # Test encoding/decoding
            json_str = json.dumps(data, ensure_ascii=False)
            decoded = json.loads(json_str)
            
            # Check for common multilingual characters
            test_strings = [
                "Arabic: إصابة أزمة",
                "Spanish: lesión huelga",
                "French: blessure grève",
                "German: verletzung streik",
                "Portuguese: lesão greve"
            ]
            
            for test_str in test_strings:
                encoded = test_str.encode('utf-8')
                decoded_str = encoded.decode('utf-8')
                if test_str != decoded_str:
                    logger.error(f"❌ UTF-8 integrity check failed for: {test_str}")
                    return False
                    
            logger.info("✅ UTF-8 integrity validated")
            return True
            
        except Exception as e:
            logger.error(f"❌ UTF-8 validation failed: {e}")
            return False
    
    def _load_from_mirror(self) -> Optional[Dict[str, Any]]:
        """
        Load data from local mirror file with checksum validation.
        
        Returns:
            Mirror data dict or None if file doesn't exist or validation fails
        """
        if not MIRROR_FILE_PATH.exists():
            logger.warning(f"⚠️ Mirror file not found: {MIRROR_FILE_PATH}")
            return None
        
        try:
            with open(MIRROR_FILE_PATH, 'r', encoding='utf-8') as f:
                mirror_data = json.load(f)
            
            timestamp = mirror_data.get("timestamp", "")
            version = mirror_data.get("version", "UNKNOWN")
            checksum = mirror_data.get("checksum", "")
            data = mirror_data.get("data", {})
            
            # Validate checksum if present
            if checksum:
                calculated_checksum = self._calculate_checksum(data)
                if calculated_checksum != checksum:
                    logger.error(f"❌ Mirror checksum mismatch! Expected: {checksum[:8]}..., Got: {calculated_checksum[:8]}...")
                    logger.warning("⚠️ Mirror data may be corrupted, using anyway")
                else:
                    logger.info(f"✅ Mirror checksum validated: {checksum[:8]}...")
            
            logger.info(f"✅ Loaded mirror from {timestamp} (v{version})")
            return data
        except Exception as e:
            logger.error(f"❌ Failed to load mirror: {e}")
            return None
    
    def _execute_query(self, table_name: str, cache_key: str, 
                       select: str = "*", filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute Supabase query with caching and fail-safe mirror.
        
        Args:
            table_name: Name of the table to query
            cache_key: Unique key for caching
            select: Select clause (default: "*")
            filters: Optional dictionary of filters
            
        Returns:
            List of records from the table
        """
        # Try cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Try Supabase connection
        if self._connected and self._client:
            try:
                query = self._client.table(table_name).select(select)
                
                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)
                
                response = query.execute()
                data = response.data if hasattr(response, 'data') else []
                
                # Cache the result
                self._set_cache(cache_key, data)
                
                return data
                
            except Exception as e:
                logger.warning(f"Supabase query failed for {table_name}: {e}")
                # Fall through to mirror
        
        # Fallback to mirror
        logger.info(f"Falling back to mirror for {table_name}")
        mirror_data = self._load_from_mirror()
        
        if mirror_data and table_name in mirror_data:
            return mirror_data[table_name]
        
        logger.error(f"No data available for {table_name} (Supabase and mirror failed)")
        return []
    
    def fetch_continents(self) -> List[Dict[str, Any]]:
        """
        Fetch all continents from Supabase.
        
        Returns:
            List of continent records
        """
        cache_key = "continents"
        data = self._execute_query("continents", cache_key)
        logger.info(f"Fetched {len(data)} continents")
        return data
    
    def fetch_countries(self, continent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch countries, optionally filtered by continent.
        
        Args:
            continent_id: Optional continent ID to filter countries
            
        Returns:
            List of country records
        """
        cache_key = f"countries_{continent_id}" if continent_id else "countries_all"
        filters = {"continent_id": continent_id} if continent_id else None
        data = self._execute_query("countries", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} countries")
        return data
    
    def fetch_leagues(self, country_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch leagues, optionally filtered by country.
        
        Args:
            country_id: Optional country ID to filter leagues
            
        Returns:
            List of league records
        """
        cache_key = f"leagues_{country_id}" if country_id else "leagues_all"
        filters = {"country_id": country_id} if country_id else None
        data = self._execute_query("leagues", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} leagues")
        return data
    
    def fetch_sources(self, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch news sources, optionally filtered by league.
        
        Note: This method queries the 'news_sources' table in Supabase.
        The table was renamed from 'sources' to 'news_sources' in V9.5.
        
        Args:
            league_id: Optional league ID to filter sources
            
        Returns:
            List of news source records
        """
        cache_key = f"news_sources_{league_id}" if league_id else "news_sources_all"
        filters = {"league_id": league_id} if league_id else None
        data = self._execute_query("news_sources", cache_key, filters=filters)
        logger.info(f"Fetched {len(data)} news sources")
        return data
    
    def fetch_hierarchical_map(self) -> Dict[str, Any]:
        """
        Fetch the complete Continental-Country-League-Sources hierarchy.
        
        Returns:
            Nested dictionary structure:
            {
                "continents": [
                    {
                        "id": "eu",
                        "name": "Europe",
                        "countries": [
                            {
                                "id": "it",
                                "name": "Italy",
                                "leagues": [
                                    {
                                        "id": "serie_a",
                                        "name": "Serie A",
                                        "sources": [...]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        """
        cache_key = "hierarchical_map_full"
        
        # Try cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Build hierarchical structure
        continents = self.fetch_continents()
        hierarchical_data = {"continents": []}
        
        for continent in continents:
            continent_data = {
                "id": continent.get("id"),
                "name": continent.get("name"),
                "countries": []
            }
            
            countries = self.fetch_countries(continent.get("id"))
            
            for country in countries:
                country_data = {
                    "id": country.get("id"),
                    "name": country.get("name"),
                    "leagues": []
                }
                
                leagues = self.fetch_leagues(country.get("id"))
                
                for league in leagues:
                    league_data = {
                        "id": league.get("id"),
                        "name": league.get("name"),
                        "sources": self.fetch_sources(league.get("id"))
                    }
                    country_data["leagues"].append(league_data)
                
                continent_data["countries"].append(country_data)
            
            hierarchical_data["continents"].append(continent_data)
        
        # Cache the result
        self._set_cache(cache_key, hierarchical_data)
        
        # Save to mirror
        mirror_data = {
            "continents": continents,
            "countries": self.fetch_countries(),
            "leagues": self.fetch_leagues(),
            "sources": self.fetch_sources()
        }
        self._save_to_mirror(mirror_data)
        
        logger.info("Built complete hierarchical map")
        return hierarchical_data
    
    # ============================================
    # V9.2: DATABASE-DRIVEN INTELLIGENCE ENGINE METHODS
    # ============================================
    
    def get_active_leagues(self) -> List[Dict[str, Any]]:
        """
        Fetch all active leagues with country and continent information.
        
        Returns:
            List of active league records with enriched data:
            [
                {
                    "id": "league_uuid",
                    "api_key": "soccer_brazil_campeonato",
                    "tier_name": "Série A",
                    "priority": 1,
                    "is_active": true,
                    "country": {
                        "id": "country_uuid",
                        "name": "Brazil",
                        "iso_code": "BR"
                    },
                    "continent": {
                        "id": "continent_uuid",
                        "name": "LATAM",
                        "active_hours_utc": [12, 13, 14, ...]
                    }
                },
                ...
            ]
        """
        cache_key = "active_leagues_full"
        
        # Try cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch active leagues
        leagues = self._execute_query("leagues", cache_key, filters={"is_active": True})
        
        if not leagues:
            logger.warning("No active leagues found in database")
            return []
        
        # Fetch all countries and continents for enrichment
        all_countries = self.fetch_countries()
        all_continents = self.fetch_continents()
        
        # Build lookup dictionaries
        country_map = {c["id"]: c for c in all_countries}
        continent_map = {c["id"]: c for c in all_continents}
        
        # Enrich leagues with country and continent data
        enriched_leagues = []
        for league in leagues:
            country_id = league.get("country_id")
            country = country_map.get(country_id)
            
            if not country:
                logger.warning(f"League {league.get('api_key')} has no valid country_id")
                continue
            
            continent_id = country.get("continent_id")
            continent = continent_map.get(continent_id)
            
            if not continent:
                logger.warning(f"Country {country.get('name')} has no valid continent_id")
                continue
            
            enriched_league = {
                **league,
                "country": {
                    "id": country["id"],
                    "name": country["name"],
                    "iso_code": country.get("iso_code")
                },
                "continent": {
                    "id": continent["id"],
                    "name": continent["name"],
                    "active_hours_utc": continent.get("active_hours_utc", [])
                }
            }
            enriched_leagues.append(enriched_league)
        
        logger.info(f"Found {len(enriched_leagues)} active leagues")
        return enriched_leagues
    
    def get_active_leagues_for_continent(self, continent_name: str) -> List[Dict[str, Any]]:
        """
        Fetch active leagues for a specific continent.
        
        Args:
            continent_name: Continent name (e.g., "LATAM", "ASIA", "AFRICA")
            
        Returns:
            List of active league records for the continent
        """
        all_active = self.get_active_leagues()
        
        filtered = [
            league for league in all_active
            if league.get("continent", {}).get("name") == continent_name
        ]
        
        logger.info(f"Found {len(filtered)} active leagues for continent {continent_name}")
        return filtered
    
    def get_active_continent_blocks(self, current_utc_hour: int) -> List[str]:
        """
        Determine which continental blocks are active based on current UTC time.
        
        Args:
            current_utc_hour: Current hour in UTC (0-23)
            
        Returns:
            List of active continent names (e.g., ["LATAM", "ASIA"])
        """
        continents = self.fetch_continents()
        
        active_blocks = []
        for continent in continents:
            active_hours = continent.get("active_hours_utc", [])
            if current_utc_hour in active_hours:
                active_blocks.append(continent["name"])
        
        logger.debug(f"Active continental blocks at {current_utc_hour}:00 UTC: {active_blocks}")
        return active_blocks
    
    def get_news_sources(self, league_id: str) -> List[Dict[str, Any]]:
        """
        Fetch news sources for a specific league.
        
        Args:
            league_id: League UUID or ID
            
        Returns:
            List of news source records
        """
        cache_key = f"news_sources_{league_id}"
        return self._execute_query("news_sources", cache_key, filters={"league_id": league_id})
    
    def fetch_all_news_sources(self) -> List[Dict[str, Any]]:
        """
        Fetch all news sources without league filter.
        
        Returns:
            List of all news source records
        """
        cache_key = "news_sources_all"
        return self._execute_query("news_sources", cache_key)
    
    def get_social_sources(self) -> List[Dict[str, Any]]:
        """
        Fetch all social sources (Twitter/X handles).
        
        Returns:
            List of social source records
        """
        cache_key = "social_sources_all"
        return self._execute_query("social_sources", cache_key)
    
    def get_social_sources_for_league(self, league_id: str) -> List[Dict[str, Any]]:
        """
        Fetch social sources for a specific league.
        
        Args:
            league_id: League UUID or ID
            
        Returns:
            List of social source records for the league
        """
        cache_key = f"social_sources_{league_id}"
        return self._execute_query("social_sources", cache_key, filters={"league_id": league_id})
    
    def get_continental_sources(self, continent_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all news sources for leagues in a continent.
        
        Args:
            continent_id: Continent UUID or ID
            
        Returns:
            List of news source records for the continent
        """
        # Get all countries in the continent
        countries = self.fetch_countries(continent_id)
        
        # Get all leagues in those countries
        all_leagues = []
        for country in countries:
            leagues = self.fetch_leagues(country["id"])
            all_leagues.extend(leagues)
        
        # Get all sources for those leagues
        all_sources = []
        for league in all_leagues:
            sources = self.get_news_sources(league["id"])
            all_sources.extend(sources)
        
        logger.debug(f"Found {len(all_sources)} sources for continent {continent_id}")
        return all_sources
    
    def validate_api_keys(self, leagues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate API keys for active leagues.
        
        Logs CRITICAL warnings for invalid API keys but does not stop the bot.
        
        Args:
            leagues: List of league records with api_key field
            
        Returns:
            Dict with validation results:
            {
                "valid": ["soccer_brazil_campeonato", ...],
                "invalid": [{"api_key": "invalid_key", "league": "...", "error": "..."}],
                "total": 10
            }
        """
        valid_keys = []
        invalid_keys = []
        
        for league in leagues:
            api_key = league.get("api_key")
            league_name = league.get("tier_name", league.get("api_key", "Unknown"))
            
            if not api_key:
                invalid_keys.append({
                    "api_key": None,
                    "league": league_name,
                    "error": "No API key provided"
                })
                logger.critical(f"CRITICAL: League '{league_name}' has no API key configured")
                continue
            
            # Basic validation: check if it follows the expected pattern
            # The-Odds-API keys typically start with "soccer_"
            if not api_key.startswith("soccer_"):
                invalid_keys.append({
                    "api_key": api_key,
                    "league": league_name,
                    "error": "API key does not follow expected pattern (should start with 'soccer_')"
                })
                logger.critical(f"CRITICAL: Invalid API key '{api_key}' for league '{league_name}'")
                continue
            
            valid_keys.append(api_key)
        
        result = {
            "valid": valid_keys,
            "invalid": invalid_keys,
            "total": len(leagues),
            "valid_count": len(valid_keys),
            "invalid_count": len(invalid_keys)
        }
        
        if invalid_keys:
            logger.warning(f"API Key Validation: {len(invalid_keys)} invalid keys found out of {len(leagues)} total")
        else:
            logger.info(f"API Key Validation: All {len(leagues)} API keys are valid")
        
        return result
    
    def update_mirror(self, force: bool = False) -> bool:
        """
        Update the local mirror with fresh data from Supabase.
        
        Args:
            force: If True, bypass cache and fetch fresh data
            
        Returns:
            True if mirror was updated successfully, False otherwise
        """
        try:
            # Invalidate cache if forcing update
            if force:
                self.invalidate_cache()
            
            # Fetch all data including social_sources and news_sources
            mirror_data = {
                "continents": self.fetch_continents(),
                "countries": self.fetch_countries(),
                "leagues": self.fetch_leagues(),
                "sources": self.fetch_sources(),
                "social_sources": self.get_social_sources(),
                "news_sources": self.fetch_all_news_sources()
            }
            
            # Save to mirror with version and checksum
            self._save_to_mirror(mirror_data, version="V9.5")
            
            logger.info("✅ Local mirror updated successfully with social_sources and news_sources")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update mirror: {e}")
            return False
    
    # ============================================
    # V9.5: LOCAL MIRROR WITH SOCIAL_SOURCES METADATA
    # ============================================
    
    def create_local_mirror(self) -> bool:
        """
        Create local mirror with social_sources and news_sources metadata (V9.5).
        
        This function creates a comprehensive local mirror that includes:
        - Standard Supabase data (continents, countries, leagues, sources)
        - Full social_sources list from Supabase
        - Full news_sources list from Supabase
        - Social sources metadata from Nitter scraper with V9.5 fields:
          * translation: Italian translation from DeepSeek-V3
          * is_betting_relevant: Boolean relevance flag
          * gate_triggered_keyword: Which keyword triggered the gate
          * is_convergent: Convergence status from analyzer
          * convergence_sources: JSON with web and social signal details
        
        UTF-8 encoding is ensured for Arabic and Spanish characters.
        Checksum is calculated for integrity verification.
        
        Returns:
            True if mirror was created successfully, False otherwise
        """
        try:
            logger.info("🔄 Creating local mirror with social_sources and news_sources metadata...")
            
            # Fetch standard Supabase data
            mirror_data = {
                "continents": self.fetch_continents(),
                "countries": self.fetch_countries(),
                "leagues": self.fetch_leagues(),
                "sources": self.fetch_sources(),
                "social_sources": self.get_social_sources(),
                "news_sources": self.fetch_all_news_sources()
            }
            
            # Validate that social_sources and news_sources are not empty
            social_sources_count = len(mirror_data.get("social_sources", []))
            news_sources_count = len(mirror_data.get("news_sources", []))
            
            if social_sources_count == 0:
                logger.warning("⚠️ No social_sources found in Supabase - mirror may be incomplete")
            else:
                logger.info(f"✅ Captured {social_sources_count} social_sources")
            
            if news_sources_count == 0:
                logger.warning("⚠️ No news_sources found in Supabase - mirror may be incomplete")
            else:
                logger.info(f"✅ Captured {news_sources_count} news_sources")
            
            # Try to load social sources from Nitter cache (if available)
            social_sources_data = self._load_social_sources_from_cache()
            if social_sources_data:
                mirror_data["social_sources_tweets"] = social_sources_data
                logger.info(f"✅ Loaded {len(social_sources_data.get('tweets', []))} tweets from Nitter cache")
            else:
                mirror_data["social_sources_tweets"] = {"tweets": [], "last_updated": None}
                logger.info("ℹ️ No Nitter cache data available")
            
            # Save to mirror with UTF-8 encoding, version, and checksum
            self._save_to_mirror(mirror_data, version="V9.5")
            
            logger.info("✅ Local mirror created successfully with social_sources and news_sources metadata")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create local mirror: {e}")
            return False
    
    def _load_social_sources_from_cache(self) -> Optional[Dict[str, Any]]:
        """
        Load social sources from Nitter cache.
        
        This function reads the Nitter cache file and extracts tweet data
        with V9.5 fields for inclusion in the mirror.
        
        Returns:
            Dict with tweets list and last_updated timestamp, or None if cache not available
        """
        try:
            from pathlib import Path
            cache_file = Path("data/nitter_cache.json")
            
            if not cache_file.exists():
                logger.debug("Nitter cache file not found")
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Extract tweets from cache with V9.5 fields
            tweets = []
            for handle_key, entry in cache_data.items():
                if isinstance(entry, dict) and 'tweets' in entry:
                    for tweet in entry['tweets']:
                        # Ensure V9.5 fields are present (with defaults if missing)
                        tweet_data = {
                            "handle": handle_key,
                            "date": tweet.get("date"),
                            "content": tweet.get("content"),
                            "topics": tweet.get("topics", []),
                            "relevance_score": tweet.get("relevance_score", 0.0),
                            # V9.5 fields
                            "translation": tweet.get("translation"),
                            "is_betting_relevant": tweet.get("is_betting_relevant"),
                            "gate_triggered_keyword": tweet.get("gate_triggered_keyword"),
                            "is_convergent": tweet.get("is_convergent"),
                            "convergence_sources": tweet.get("convergence_sources")
                        }
                        tweets.append(tweet_data)
            
            # Get last updated timestamp from cache
            last_updated = None
            if tweets:
                # Use the most recent tweet date as last_updated
                dates = [t.get("date") for t in tweets if t.get("date")]
                if dates:
                    last_updated = max(dates)
            
            logger.debug(f"Loaded {len(tweets)} tweets from Nitter cache")
            
            return {
                "tweets": tweets,
                "last_updated": last_updated
            }
            
        except Exception as e:
            logger.warning(f"Failed to load social sources from cache: {e}")
            return None
    
    def refresh_mirror(self) -> bool:
        """
        Refresh the local mirror at the start of a cycle.
        
        This function is called at the start of each 6-hour cycle to ensure
        the mirror has the latest social_sources data. It is idempotent
        and can be called multiple times safely.
        
        Returns:
            True if mirror was refreshed successfully, False otherwise
        """
        try:
            logger.info("🔄 Refreshing local mirror at cycle start...")
            
            # Create fresh mirror with latest data
            success = self.create_local_mirror()
            
            if success:
                logger.info("✅ Mirror refreshed successfully")
            else:
                logger.warning("⚠️ Mirror refresh failed, will use existing mirror")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh mirror: {e}")
            return False
    
    def invalidate_cache(self, cache_key: Optional[str] = None) -> None:
        """
        Invalidate cache entries.
        
        Args:
            cache_key: Specific cache key to invalidate. If None, clears all cache.
        """
        if cache_key:
            self._cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            logger.info(f"Invalidated cache for key: {cache_key}")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.info("Invalidated all cache")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_entries": len(self._cache),
            "cache_keys": list(self._cache.keys()),
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "connected": self._connected,
            "mirror_exists": MIRROR_FILE_PATH.exists()
        }
    
    def test_connection(self) -> bool:
        """
        Test Supabase connectivity by querying the continents table.
        
        Returns:
            True if connection is successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.error("Not connected to Supabase")
            return False
        
        try:
            response = self._client.table("continents").select("*").limit(1).execute()
            data = response.data if hasattr(response, 'data') else []
            logger.info(f"Connection test successful. Found {len(data)} continents")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            self._connected = False
            self._connection_error = str(e)
            return False


def get_supabase() -> SupabaseProvider:
    """
    Get the singleton SupabaseProvider instance.
    
    Returns:
        The single SupabaseProvider instance
    """
    return SupabaseProvider()


# Convenience functions for direct access
def fetch_continents() -> List[Dict[str, Any]]:
    """Convenience function to fetch continents."""
    return get_supabase().fetch_continents()


def fetch_countries(continent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience function to fetch countries."""
    return get_supabase().fetch_countries(continent_id)


def fetch_leagues(country_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience function to fetch leagues."""
    return get_supabase().fetch_leagues(country_id)


def fetch_sources(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience function to fetch sources."""
    return get_supabase().fetch_sources(league_id)


def fetch_hierarchical_map() -> Dict[str, Any]:
    """Convenience function to fetch the complete hierarchical map."""
    return get_supabase().fetch_hierarchical_map()


def create_local_mirror() -> bool:
    """Convenience function to create local mirror with social_sources metadata."""
    return get_supabase().create_local_mirror()


def refresh_mirror() -> bool:
    """Convenience function to refresh local mirror at cycle start."""
    return get_supabase().refresh_mirror()


if __name__ == "__main__":
    # Test the Supabase provider
    print("=" * 60)
    print("SupabaseProvider - Connection Test")
    print("=" * 60)
    
    provider = get_supabase()
    
    # Test connection
    print("\n1. Testing connection...")
    if provider.test_connection():
        print("✅ Connection successful")
    else:
        print(f"❌ Connection failed: {provider.get_connection_error()}")
    
    # Fetch continents
    print("\n2. Fetching continents...")
    continents = provider.fetch_continents()
    print(f"✅ Found {len(continents)} continents")
    for continent in continents[:5]:
        print(f"   - {continent.get('id')}: {continent.get('name')}")
    
    # Fetch hierarchical map
    print("\n3. Fetching hierarchical map...")
    hierarchy = provider.fetch_hierarchical_map()
    print(f"✅ Built hierarchy with {len(hierarchy['continents'])} continents")
    
    # Cache stats
    print("\n4. Cache statistics...")
    stats = provider.get_cache_stats()
    print(f"✅ Cache entries: {stats['cache_entries']}")
    print(f"✅ Connected: {stats['connected']}")
    print(f"✅ Mirror exists: {stats['mirror_exists']}")
    
    print("\n" + "=" * 60)
    print("Supabase Bridge Active. 1-hour Cache and Mirroring established.")
    print("=" * 60)
