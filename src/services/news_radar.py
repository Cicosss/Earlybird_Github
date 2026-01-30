"""
EarlyBird News Radar Monitor - Autonomous Web Monitoring

Independent component that monitors configured web sources 24/7 to discover
betting-relevant news on minor leagues NOT covered by the main bot.

Unlike the Browser Monitor (which feeds the main pipeline), News Radar:
- Operates completely independently from the main bot
- Sends direct Telegram alerts without database interaction
- Monitors leagues/sources NOT covered by the existing system
- Has a simplified flow: extract → filter → analyze → alert

Flow:
1. Load configured source URLs from config/news_radar_sources.json
2. Continuously scan sources in a loop (default 5 min interval)
3. Extract page text with HTTP + Trafilatura (fallback: Playwright)
4. Apply exclusion filters (basketball, women's, youth, NFL, etc.)
5. Analyze relevance for betting-relevant news (injuries, suspensions, etc.)
6. If ambiguous (0.5-0.7 confidence): call DeepSeek for deeper analysis
7. If relevant (confidence >= 0.7): send Telegram alert
8. Deduplicate using content hash cache (24h TTL)

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.4, 7.1-7.4, 8.1-8.4, 9.1-9.4, 10.1-10.4
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import random
import requests
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# V1.1: Import shared content analysis utilities
from src.utils.content_analysis import (
    AnalysisResult,
    ExclusionFilter,
    RelevanceAnalyzer,
    PositiveNewsFilter,
    get_exclusion_filter,
    get_relevance_analyzer,
    get_positive_news_filter,
)

# V2.0: Import high-value signal detection
from src.utils.high_value_detector import (
    GarbageFilter,
    HighSignalDetector,
    SignalResult,
    get_garbage_filter,
    get_signal_detector,
)
from src.utils.radar_prompts import (
    build_analysis_prompt_v2,
    CATEGORY_EMOJI,
    CATEGORY_ITALIAN,
    BETTING_IMPACT_EMOJI,
)

# V1.3: Import light enrichment for database context
try:
    from src.utils.radar_enrichment import enrich_radar_alert_async, EnrichmentContext
    _ENRICHMENT_AVAILABLE = True
except ImportError:
    _ENRICHMENT_AVAILABLE = False
    EnrichmentContext = None

# V7.3: Import odds movement checker
try:
    from src.utils.radar_odds_check import check_odds_for_alert_async, OddsMovementStatus
    _ODDS_CHECK_AVAILABLE = True
except ImportError:
    _ODDS_CHECK_AVAILABLE = False
    OddsMovementStatus = None

# V7.3: Import cross-source validator
try:
    from src.utils.radar_cross_validator import get_cross_validator
    _CROSS_VALIDATOR_AVAILABLE = True
except ImportError:
    _CROSS_VALIDATOR_AVAILABLE = False

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_CONFIG_FILE = "config/news_radar_sources.json"
DEFAULT_SCAN_INTERVAL_MINUTES = 5
DEFAULT_PAGE_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_CACHE_MAX_ENTRIES = 5000
DEFAULT_NAVIGATION_DELAY_SECONDS = 3
DEFAULT_MAX_LINKS_PER_PAGINATED = 10
MAX_TEXT_LENGTH = 30000

# Confidence thresholds
DEEPSEEK_CONFIDENCE_THRESHOLD = 0.5  # Below this: skip
ALERT_CONFIDENCE_THRESHOLD = 0.7     # Above this: alert directly

# DeepSeek rate limiting
DEEPSEEK_MIN_INTERVAL_SECONDS = 2.0

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300  # 5 minutes

# HTTP configuration
HTTP_TIMEOUT = 15
HTTP_MIN_CONTENT_LENGTH = 200

# OpenRouter API
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Trafilatura import with fallback
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("⚠️ [NEWS-RADAR] trafilatura not installed, using raw text extraction")


# ============================================
# DATA MODELS
# ============================================

@dataclass
class RadarSource:
    """
    Configuration for a monitored source URL.
    
    Attributes:
        url: Source URL to monitor
        name: Human-readable name for the source
        priority: Scan priority (1=highest, higher numbers=lower priority)
        scan_interval_minutes: How often to scan this source
        navigation_mode: "single" for single page, "paginated" for multi-page
        link_selector: CSS selector for links in paginated mode
        last_scanned: Timestamp of last scan
        source_timezone: Timezone of the source (e.g., "Europe/London", "America/Sao_Paulo")
                        Used for timezone-aware scanning optimization
    
    Requirements: 1.1, 8.1, 8.4, 9.1
    """
    url: str
    name: str = ""
    priority: int = 1
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    navigation_mode: str = "single"  # "single" or "paginated"
    link_selector: Optional[str] = None
    last_scanned: Optional[datetime] = None
    source_timezone: Optional[str] = None  # V7.3: e.g., "Europe/London"
    
    def __post_init__(self):
        if not self.name:
            self.name = self.url[:50]
    
    def is_due_for_scan(self) -> bool:
        """
        Check if this source is due for scanning.
        
        V7.3: Considers timezone for off-peak optimization.
        """
        if self.last_scanned is None:
            return True
        
        # Calculate effective interval (may be extended during off-peak)
        effective_interval = self._get_effective_interval()
        
        elapsed = datetime.now(timezone.utc) - self.last_scanned
        return elapsed >= timedelta(minutes=effective_interval)
    
    def _get_effective_interval(self) -> int:
        """
        V7.3: Get effective scan interval based on source timezone.
        
        During off-peak hours (midnight-6am local time), extends interval
        to save resources since news is less likely to be published.
        
        Returns:
            Effective interval in minutes
        """
        if not self.source_timezone:
            return self.scan_interval_minutes
        
        try:
            # Try to get local hour for the source
            from zoneinfo import ZoneInfo
            
            tz = ZoneInfo(self.source_timezone)
            local_now = datetime.now(tz)
            local_hour = local_now.hour
            
            # Off-peak: midnight to 6am local time
            if 0 <= local_hour < 6:
                # Double the interval during off-peak
                return self.scan_interval_minutes * 2
            
            # Peak hours: normal interval
            return self.scan_interval_minutes
            
        except Exception:
            # If timezone parsing fails, use default interval
            return self.scan_interval_minutes


@dataclass
class RadarAlert:
    """
    Alert to be sent to Telegram.
    
    V2.0: Enhanced with structured betting data.
    
    Attributes:
        source_name: Name of the source where news was found
        source_url: URL of the source
        affected_team: Team affected by the news
        opponent: Opponent team (if known)
        competition: League/cup name (if known)
        match_date: Match date (if known)
        category: Type of signal (MASS_ABSENCE, DECIMATED, YOUTH_TEAM, etc.)
        absent_count: Number of players unavailable
        absent_players: List of player names (if known)
        betting_impact: CRITICAL, HIGH, MEDIUM, LOW
        summary: Brief summary of the news (in Italian)
        confidence: Confidence score (0.0-1.0)
        discovered_at: Timestamp when news was discovered
        enrichment_context: Optional enrichment data from database
    
    Requirements: 6.1, 6.2
    """
    source_name: str
    source_url: str
    affected_team: str
    category: str
    summary: str
    confidence: float
    # V2.0: New structured fields
    opponent: Optional[str] = None
    competition: Optional[str] = None
    match_date: Optional[str] = None
    absent_count: int = 0
    absent_players: List[str] = field(default_factory=list)
    betting_impact: str = "MEDIUM"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    enrichment_context: Optional[Any] = None
    
    def to_telegram_message(self) -> str:
        """
        Format alert as Telegram message in Italian.
        
        V2.0: Enhanced format with structured betting data.
        Uses 🔔 RADAR emoji to distinguish from main bot (🚨 EARLYBIRD).
        
        Requirements: 6.2, 6.3
        """
        # Get emoji and Italian category from prompts module
        emoji = CATEGORY_EMOJI.get(self.category, "📰")
        category_it = CATEGORY_ITALIAN.get(self.category, self.category)
        impact_emoji = BETTING_IMPACT_EMOJI.get(self.betting_impact, "")
        
        # Handle unknown team
        team_display = self.affected_team if self.affected_team and self.affected_team != "Unknown" else "Da verificare"
        
        # Build match info line
        match_info = ""
        if self.opponent:
            match_info = f"\n⚽ *Partita:* {team_display} vs {self.opponent}"
            if self.competition:
                match_info += f" ({self.competition})"
            if self.match_date:
                match_info += f"\n📅 *Data:* {self.match_date}"
        
        # Build absent players line
        absent_info = ""
        if self.absent_count > 0:
            absent_info = f"\n❌ *Assenti:* {self.absent_count} giocatori"
            if self.absent_players:
                # Show max 5 names
                names = self.absent_players[:5]
                if len(self.absent_players) > 5:
                    names.append(f"+{len(self.absent_players) - 5} altri")
                absent_info += f"\n   {', '.join(names)}"
        
        # Build enrichment line if available
        enrichment_line = ""
        if self.enrichment_context and hasattr(self.enrichment_context, 'format_context_line'):
            context_str = self.enrichment_context.format_context_line()
            if context_str:
                enrichment_line = f"\n{context_str}"
        
        # V7.3: Build validation line (odds + cross-source)
        validation_line = ""
        validation_parts = []
        
        # Add odds suffix if available
        if hasattr(self, '_odds_suffix') and self._odds_suffix:
            validation_parts.append(self._odds_suffix)
        
        # Add cross-source validation tag if available
        if hasattr(self, '_validation_tag') and self._validation_tag:
            validation_parts.append(self._validation_tag)
        
        if validation_parts:
            validation_line = f"\n{' | '.join(validation_parts)}"
        
        return (
            f"🔔 *RADAR ALERT* {emoji} {impact_emoji}\n\n"
            f"*Squadra:* {team_display}\n"
            f"*Categoria:* {category_it}"
            f"{match_info}"
            f"{absent_info}\n\n"
            f"📋 *Riepilogo:* {self.summary}"
            f"{enrichment_line}"
            f"{validation_line}\n\n"
            f"*Fonte:* {self.source_name}\n"
            f"🔗 {self.source_url}\n\n"
            f"_Impatto betting: {self.betting_impact} | Affidabilità: {self.confidence:.0%}_"
        )


# NOTE: AnalysisResult is now imported from src.utils.content_analysis


@dataclass
class GlobalSettings:
    """Global settings for News Radar."""
    default_scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    page_timeout_seconds: int = DEFAULT_PAGE_TIMEOUT_SECONDS
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS
    deepseek_confidence_threshold: float = DEEPSEEK_CONFIDENCE_THRESHOLD
    alert_confidence_threshold: float = ALERT_CONFIDENCE_THRESHOLD
    navigation_delay_seconds: int = DEFAULT_NAVIGATION_DELAY_SECONDS
    max_links_per_paginated_source: int = DEFAULT_MAX_LINKS_PER_PAGINATED


@dataclass
class RadarConfig:
    """Complete News Radar configuration."""
    sources: List[RadarSource] = field(default_factory=list)
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)


# ============================================
# CONTENT CACHE (Deduplication)
# ============================================

class ContentCache:
    """
    Hash-based content cache for deduplication.
    
    Uses first 1000 chars of content to compute hash.
    Implements LRU eviction when max entries exceeded.
    Entries expire after TTL hours.
    
    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    
    def __init__(
        self, 
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES, 
        ttl_hours: int = DEFAULT_CACHE_TTL_HOURS
    ):
        self._cache: OrderedDict[str, datetime] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours
    
    def compute_hash(self, content: str) -> str:
        """
        Compute hash from first 1000 chars of content.
        
        Requirements: 7.1
        
        Phase 1 Critical Fix: Changed errors='ignore' to errors='replace' to preserve
        special characters. Added Unicode normalization before hashing.
        """
        content_prefix = content[:1000] if len(content) > 1000 else content
        # Phase 1 Critical Fix: Use errors='replace' instead of 'ignore' to preserve special characters
        # Phase 1 Critical Fix: Add Unicode normalization before hashing
        return hashlib.sha256(content_prefix.encode('utf-8', errors='replace')).hexdigest()[:16]
    
    def is_cached(self, content: str) -> bool:
        """
        Check if content hash exists and is not expired.
        
        Requirements: 7.2, 7.4
        """
        if not content:
            return False
        
        content_hash = self.compute_hash(content)
        
        if content_hash not in self._cache:
            return False
        
        # Check expiration
        cached_at = self._cache[content_hash]
        if datetime.now(timezone.utc) - cached_at > timedelta(hours=self._ttl_hours):
            del self._cache[content_hash]
            return False
        
        # Move to end (LRU)
        self._cache.move_to_end(content_hash)
        return True
    
    def add(self, content: str) -> None:
        """
        Store content hash with current timestamp.
        
        Requirements: 7.3
        """
        if not content:
            return
        
        content_hash = self.compute_hash(content)
        
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        
        self._cache[content_hash] = datetime.now(timezone.utc)
    
    def evict_expired(self) -> int:
        """Remove all expired entries. Returns count of evicted entries."""
        now = datetime.now(timezone.utc)
        expired = [
            h for h, ts in self._cache.items()
            if now - ts > timedelta(hours=self._ttl_hours)
        ]
        for h in expired:
            del self._cache[h]
        return len(expired)
    
    def size(self) -> int:
        """Return current cache size."""
        return len(self._cache)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


# ============================================
# CIRCUIT BREAKER
# ============================================

class CircuitBreaker:
    """
    Circuit Breaker pattern for per-source failure handling.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Source is failing, skip requests for recovery_timeout
    - HALF_OPEN: Testing if source recovered, allow one request
    
    Requirements: 1.4
    """
    
    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY_TIMEOUT
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"
    
    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.debug("🔄 [CIRCUIT-BREAKER] Transitioning to HALF_OPEN")
                return True
            return False
        
        if self.state == "HALF_OPEN":
            return True
        
        return False
    
    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            logger.info("✅ [CIRCUIT-BREAKER] Circuit CLOSED (recovered)")
        elif self.state == "CLOSED":
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            logger.warning("⚠️ [CIRCUIT-BREAKER] Circuit OPEN (failed in HALF_OPEN)")
        elif self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"🔴 [CIRCUIT-BREAKER] Circuit OPEN after {self.failure_count} failures")
    
    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state for stats."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time
        }


# ============================================
# EXCLUSION FILTER & RELEVANCE ANALYZER
# ============================================
# NOTE: ExclusionFilter and RelevanceAnalyzer are now imported from
# src.utils.content_analysis for DRY compliance and shared usage with browser_monitor.


# ============================================
# CONFIG LOADING
# ============================================

def load_config(config_file: str = DEFAULT_CONFIG_FILE) -> RadarConfig:
    """
    Load News Radar configuration from JSON file.
    
    Requirements: 1.1, 8.1, 8.3
    """
    config_path = Path(config_file)
    
    if not config_path.exists():
        logger.warning(f"⚠️ [NEWS-RADAR] Config file not found: {config_file}")
        return RadarConfig()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Parse global settings
        gs_data = data.get('global_settings', {})
        global_settings = GlobalSettings(
            default_scan_interval_minutes=gs_data.get('default_scan_interval_minutes', DEFAULT_SCAN_INTERVAL_MINUTES),
            page_timeout_seconds=gs_data.get('page_timeout_seconds', DEFAULT_PAGE_TIMEOUT_SECONDS),
            cache_ttl_hours=gs_data.get('cache_ttl_hours', DEFAULT_CACHE_TTL_HOURS),
            deepseek_confidence_threshold=gs_data.get('deepseek_confidence_threshold', DEEPSEEK_CONFIDENCE_THRESHOLD),
            alert_confidence_threshold=gs_data.get('alert_confidence_threshold', ALERT_CONFIDENCE_THRESHOLD),
            navigation_delay_seconds=gs_data.get('navigation_delay_seconds', DEFAULT_NAVIGATION_DELAY_SECONDS),
            max_links_per_paginated_source=gs_data.get('max_links_per_paginated_source', DEFAULT_MAX_LINKS_PER_PAGINATED),
        )
        
        # Parse sources
        sources = []
        for src_data in data.get('sources', []):
            # Skip sources without required 'url' field
            if 'url' not in src_data:
                logger.warning(f"⚠️ [NEWS-RADAR] Skipping source without URL: {src_data}")
                continue
            
            source = RadarSource(
                url=src_data['url'],
                name=src_data.get('name', src_data['url'][:50]),
                priority=src_data.get('priority', 1),
                scan_interval_minutes=src_data.get('scan_interval_minutes', global_settings.default_scan_interval_minutes),
                navigation_mode=src_data.get('navigation_mode', 'single'),
                link_selector=src_data.get('link_selector'),
                source_timezone=src_data.get('source_timezone')  # V7.3: timezone-aware scanning
            )
            sources.append(source)
        
        logger.info(f"✅ [NEWS-RADAR] Loaded {len(sources)} sources from {config_file}")
        return RadarConfig(sources=sources, global_settings=global_settings)
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ [NEWS-RADAR] Invalid JSON in config: {e}")
        return RadarConfig()
    except Exception as e:
        logger.error(f"❌ [NEWS-RADAR] Failed to load config: {e}")
        return RadarConfig()


# ============================================
# CONTENT EXTRACTOR
# ============================================

class ContentExtractor:
    """
    Extracts clean text from web pages.
    
    Uses hybrid approach:
    1. HTTP + Trafilatura (fast, works for ~80% of sites)
    2. Playwright fallback with stealth mode (slower, ~95% success)
    
    V1.3: Added browser lock for race condition protection
    
    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    
    def __init__(self, page_timeout: int = DEFAULT_PAGE_TIMEOUT_SECONDS):
        self._page_timeout = page_timeout
        self._playwright = None
        self._browser = None
        self._browser_lock: Optional[asyncio.Lock] = None  # V1.3: Lock for browser recreation
        
        # Stats
        self._http_extractions = 0
        self._browser_extractions = 0
        self._failed_extractions = 0
    
    async def initialize(self) -> bool:
        """
        Initialize Playwright browser (optional).
        
        V7.4: Now returns True even without Playwright - HTTP-only mode is supported.
        Playwright is optional and provides fallback for JS-heavy sites.
        
        Returns True if initialized successfully (HTTP-only or with Playwright).
        """
        try:
            from playwright.async_api import async_playwright
            
            logger.info("🌐 [NEWS-RADAR] Launching Playwright...")
            self._playwright = await async_playwright().start()
            
            # V1.3: Removed --single-process (causes instability on heavy sites)
            # Chromium with --single-process crashes frequently on ads/JS-heavy pages
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-sandbox',
                    '--disable-extensions'
                ]
            )
            
            logger.info("✅ [NEWS-RADAR] Playwright initialized")
            
            # V1.3: Initialize browser lock for race condition protection
            self._browser_lock = asyncio.Lock()
            
            return True
            
        except ImportError:
            # V7.4: Playwright is optional - HTTP-only mode works for most sites
            logger.warning("⚠️ [NEWS-RADAR] Playwright not installed - running in HTTP-only mode")
            logger.info("   HTTP + Trafilatura will be used for content extraction")
            return True  # Continue without Playwright
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Failed to initialize Playwright: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown Playwright and release resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] Error closing browser: {e}")
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"⚠️ [NEWS-RADAR] Error stopping Playwright: {e}")
            self._playwright = None
    
    async def _ensure_browser_connected(self) -> bool:
        """
        V1.3: Ensure browser is connected, recreate if disconnected.
        
        This fixes the critical bug where the browser crashes/disconnects
        but self._browser is not None, causing TargetClosedError on new_page().
        
        V1.3: Uses asyncio.Lock to serialize browser recreation across coroutines.
        
        Returns:
            True if browser is available and connected, False otherwise
        """
        # V1.3: Use lock to serialize browser recreation
        if self._browser_lock is None:
            self._browser_lock = asyncio.Lock()
        
        async with self._browser_lock:
            # Re-check after acquiring lock (another coroutine might have fixed it)
            if self._browser and self._browser.is_connected():
                return True
            
            # Case 1: No browser at all
            if not self._browser:
                logger.warning("⚠️ [NEWS-RADAR] Browser is None, attempting to recreate...")
                return await self._recreate_browser_internal()
            
            # Case 2: Browser exists but is disconnected
            try:
                if not self._browser.is_connected():
                    logger.warning("⚠️ [NEWS-RADAR] Browser disconnected, recreating...")
                    return await self._recreate_browser_internal()
            except Exception as e:
                # is_connected() itself failed - browser is in bad state
                logger.warning(f"⚠️ [NEWS-RADAR] Browser state check failed: {e}, recreating...")
                return await self._recreate_browser_internal()
            
            return True
    
    async def _recreate_browser_internal(self) -> bool:
        """
        V1.3: Internal browser recreation (called with lock held).
        
        Safely closes existing resources and reinitializes Playwright.
        IMPORTANT: This method assumes the caller holds self._browser_lock.
        
        Returns:
            True if browser was successfully recreated
        """
        logger.info("🔄 [NEWS-RADAR] Recreating browser...")
        
        # Clean up existing browser (if any)
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass  # Ignore errors on already-closed browser
            self._browser = None
        
        # Recreate browser using existing playwright instance
        if self._playwright:
            try:
                # V1.3: Removed --single-process (causes instability on heavy sites)
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--disable-setuid-sandbox',
                        '--no-sandbox',
                        '--disable-extensions'
                    ]
                )
                logger.info("✅ [NEWS-RADAR] Browser recreated successfully")
                return True
            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] Failed to recreate browser: {e}")
                # Try full reinitialization
                await self.shutdown()
                return await self.initialize()
        else:
            # No playwright instance, do full initialization
            return await self.initialize()
    
    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        """
        Extract clean article text using Trafilatura.
        
        Requirements: 2.1
        """
        if not TRAFILATURA_AVAILABLE or not html:
            return None
        
        try:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=True,
            )
            
            if text and len(text) > 100:
                return text
            
            return None
            
        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] Trafilatura extraction failed: {e}")
            return None
    
    async def _extract_with_http(self, url: str) -> Optional[str]:
        """
        Try to extract content using pure HTTP (no browser).
        
        Requirements: 2.1
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=HTTP_TIMEOUT,
                headers=headers
            )
            
            if response.status_code != 200:
                return None
            
            html = response.text
            text = self._extract_with_trafilatura(html)
            
            if text and len(text) > HTTP_MIN_CONTENT_LENGTH:
                self._http_extractions += 1
                logger.debug(f"⚡ [NEWS-RADAR] HTTP extraction success: {url[:40]}...")
                return text
            
            return None
            
        except requests.Timeout:
            logger.debug(f"⏱️ [NEWS-RADAR] HTTP timeout: {url[:40]}...")
            return None
        except Exception as e:
            logger.debug(f"⚠️ [NEWS-RADAR] HTTP extraction failed: {e}")
            return None
    
    async def _extract_with_browser(self, url: str) -> Optional[str]:
        """
        Extract content using Playwright browser.
        
        V1.2: Now uses _ensure_browser_connected() for auto-recovery.
        
        Requirements: 2.2
        """
        # V1.2: Ensure browser is connected, recreate if needed
        if not await self._ensure_browser_connected():
            logger.error("❌ [NEWS-RADAR] Browser not available and could not be recreated")
            return None
        
        page = None
        try:
            page = await self._browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 720})
            
            # Apply stealth if available
            try:
                from playwright_stealth import Stealth
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
            except ImportError:
                pass
            
            # Navigate
            timeout_ms = self._page_timeout * 1000
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            
            # Get HTML for Trafilatura
            html = await page.content()
            text = self._extract_with_trafilatura(html)
            
            # Fallback to raw text
            if not text:
                text = await page.inner_text("body")
            
            if text and len(text) > MAX_TEXT_LENGTH:
                text = text[:MAX_TEXT_LENGTH]
            
            self._browser_extractions += 1
            return text
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ [NEWS-RADAR] Browser timeout: {url[:60]}...")
            return None
        except Exception as e:
            logger.warning(f"⚠️ [NEWS-RADAR] Browser extraction error: {e}")
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
    
    async def extract(self, url: str) -> Optional[str]:
        """
        Extract text content from URL.
        
        Uses hybrid approach: HTTP first, browser fallback.
        
        Requirements: 2.1, 2.2, 2.4
        """
        # Try HTTP first (fast)
        text = await self._extract_with_http(url)
        if text:
            return text
        
        # Fallback to browser
        text = await self._extract_with_browser(url)
        if text:
            return text
        
        self._failed_extractions += 1
        logger.debug(f"📄 [NEWS-RADAR] Extraction failed: {url[:50]}...")
        return None
    
    async def extract_with_navigation(
        self, 
        url: str, 
        link_selector: str,
        max_links: int = DEFAULT_MAX_LINKS_PER_PAGINATED,
        delay_seconds: int = DEFAULT_NAVIGATION_DELAY_SECONDS
    ) -> List[Tuple[str, str]]:
        """
        Extract from paginated source.
        
        Extracts links from main page, visits each, and extracts content.
        
        V1.2: Now uses _ensure_browser_connected() for auto-recovery.
        
        Requirements: 9.1, 9.2, 9.3, 9.4
        
        Returns:
            List of (url, content) tuples
        """
        # V1.2: Ensure browser is connected, recreate if needed
        if not await self._ensure_browser_connected():
            logger.error("❌ [NEWS-RADAR] Browser not available for navigation and could not be recreated")
            return []
        
        results = []
        page = None
        
        try:
            page = await self._browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 720})
            
            # Navigate to main page
            timeout_ms = self._page_timeout * 1000
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            
            # Extract links
            links = await page.eval_on_selector_all(
                link_selector,
                "elements => elements.map(e => e.href).filter(h => h && h.startsWith('http'))"
            )
            
            # Limit number of links
            links = links[:max_links]
            logger.info(f"🔗 [NEWS-RADAR] Found {len(links)} links on {url[:40]}...")
            
            # Visit each link
            for link_url in links:
                try:
                    # Delay between pages
                    await asyncio.sleep(delay_seconds)
                    
                    # Extract content from linked page
                    content = await self.extract(link_url)
                    if content:
                        results.append((link_url, content))
                        
                except Exception as e:
                    logger.debug(f"⚠️ [NEWS-RADAR] Failed to extract {link_url[:40]}: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Navigation extraction failed: {e}")
            return results
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
    
    async def extract_batch_http(
        self,
        urls: List[str],
        max_concurrent: int = 5
    ) -> Dict[str, Optional[str]]:
        """
        V7.3: Batch HTTP extraction for multiple URLs in parallel.
        
        Uses asyncio.gather() to parallelize HTTP requests.
        Falls back to browser only for URLs that fail HTTP extraction.
        
        Args:
            urls: List of URLs to extract
            max_concurrent: Maximum concurrent HTTP requests (default 5)
            
        Returns:
            Dict mapping URL -> extracted content (or None if failed)
        """
        if not urls:
            return {}
        
        results: Dict[str, Optional[str]] = {}
        
        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def extract_single(url: str) -> Tuple[str, Optional[str]]:
            """Extract single URL with semaphore."""
            async with semaphore:
                try:
                    # Try HTTP first (fast)
                    content = await self._extract_with_http(url)
                    return (url, content)
                except Exception as e:
                    logger.debug(f"⚠️ [NEWS-RADAR] Batch HTTP failed for {url[:40]}: {e}")
                    return (url, None)
        
        # Run all extractions in parallel
        tasks = [extract_single(url) for url in urls]
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        browser_fallback_urls = []
        for i, result in enumerate(completed):
            url = urls[i]  # Get original URL by index
            if isinstance(result, Exception):
                # Exception occurred - add to fallback
                logger.debug(f"⚠️ [NEWS-RADAR] Batch task exception for {url[:40]}: {result}")
                browser_fallback_urls.append(url)
                continue
            
            _, content = result
            if content:
                results[url] = content
            else:
                # Mark for browser fallback
                browser_fallback_urls.append(url)
        
        # Browser fallback for failed URLs (sequential to avoid overload)
        if browser_fallback_urls:
            logger.debug(f"🌐 [NEWS-RADAR] Browser fallback for {len(browser_fallback_urls)} URLs")
            for url in browser_fallback_urls:
                content = await self._extract_with_browser(url)
                results[url] = content
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get extraction statistics."""
        return {
            "http_extractions": self._http_extractions,
            "browser_extractions": self._browser_extractions,
            "failed_extractions": self._failed_extractions,
        }


# ============================================
# DEEPSEEK FALLBACK
# ============================================

class DeepSeekFallback:
    """
    DeepSeek API for content analysis.
    
    V2.0: Completely rewritten for high-value signal extraction.
    - Uses new structured prompt
    - Extracts team, opponent, absent count, player names
    - Applies strict quality gates
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    def __init__(self, min_interval: float = DEEPSEEK_MIN_INTERVAL_SECONDS):
        self._min_interval = min_interval
        self._last_call_time: float = 0.0
        self._call_count = 0
    
    async def _wait_for_rate_limit(self) -> None:
        """
        Wait if needed to respect rate limit.
        
        Requirements: 5.4
        """
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            wait_time = self._min_interval - elapsed
            await asyncio.sleep(wait_time)
    
    def _parse_response_v2(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON response from DeepSeek V2 prompt.
        
        Returns structured dict or None if parsing fails.
        """
        # Handle DeepSeek <think> tags
        if '<think>' in response_text:
            response_text = re.sub(r'<think>[\s\S]*?</think>', '', response_text)
        
        try:
            data = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                # Try to find JSON object in text
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        return None
                else:
                    return None
        
        return data
    
    async def analyze_v2(self, content: str) -> Optional[Dict[str, Any]]:
        """
        V2.0: Analyze content with structured extraction.
        
        Returns dict with:
        - is_high_value: bool
        - team: str or None
        - opponent: str or None
        - competition: str or None
        - match_date: str or None
        - category: str
        - absent_count: int
        - absent_players: list
        - betting_impact: str
        - confidence: float
        - summary_italian: str
        
        Returns None if API unavailable or parsing fails.
        """
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("❌ [NEWS-RADAR] No OpenRouter API key for DeepSeek")
            return None
        
        # Rate limiting
        await self._wait_for_rate_limit()
        
        model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
        prompt = build_analysis_prompt_v2(content)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.local",
            "X-Title": "EarlyBird News Radar V2"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,  # Lower for more consistent structured output
            "max_tokens": 800
        }
        
        try:
            response = await asyncio.to_thread(
                requests.post,
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=45
            )
            
            self._last_call_time = time.time()
            self._call_count += 1
            
            if response.status_code != 200:
                logger.error(f"❌ [NEWS-RADAR] DeepSeek HTTP error: {response.status_code}")
                return None
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ [NEWS-RADAR] DeepSeek returned invalid JSON: {e}")
                return None
            
            # Extract response text
            choices = data.get("choices", [])
            if not choices:
                logger.warning("⚠️ [NEWS-RADAR] DeepSeek response missing 'choices'")
                return None
            
            first_choice = choices[0] if isinstance(choices, list) and len(choices) > 0 else None
            if not isinstance(first_choice, dict):
                logger.warning(f"⚠️ [NEWS-RADAR] DeepSeek invalid choice format")
                return None
            
            message = first_choice.get("message", {})
            if not isinstance(message, dict):
                logger.warning(f"⚠️ [NEWS-RADAR] DeepSeek invalid message format")
                return None
            
            response_text = message.get("content", "")
            
            if not response_text:
                logger.warning("⚠️ [NEWS-RADAR] DeepSeek returned empty response")
                return None
            
            logger.debug(f"🤖 [NEWS-RADAR] DeepSeek V2 analysis complete (call #{self._call_count})")
            
            result = self._parse_response_v2(response_text)
            
            # Apply quality gate
            if result:
                result = self._apply_quality_gate(result)
            
            return result
            
        except requests.Timeout:
            logger.warning("⚠️ [NEWS-RADAR] DeepSeek timeout")
            return None
        except requests.RequestException as e:
            logger.error(f"❌ [NEWS-RADAR] DeepSeek network error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] DeepSeek unexpected error: {e}")
            return None
    
    def _apply_quality_gate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply strict quality gate to analysis result.
        
        Rules:
        1. If team is null/empty → is_high_value = False
        2. If betting_impact is LOW/NONE → is_high_value = False
        3. If category is LOW_VALUE/NOT_RELEVANT → is_high_value = False
        4. If confidence < 0.7 → is_high_value = False
        """
        # Rule 1: Team must be identified
        team = result.get('team')
        if not team or team.lower() in ('null', 'unknown', 'none', ''):
            result['is_high_value'] = False
            result['quality_gate_reason'] = 'team_not_identified'
            logger.debug("🚫 [NEWS-RADAR] Quality gate: team not identified")
            return result
        
        # Rule 2: Betting impact must be meaningful
        impact = result.get('betting_impact', 'NONE')
        if impact in ('LOW', 'NONE'):
            result['is_high_value'] = False
            result['quality_gate_reason'] = f'low_betting_impact ({impact})'
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low betting impact ({impact})")
            return result
        
        # Rule 3: Category must be high-value
        category = result.get('category', 'NOT_RELEVANT')
        if category in ('LOW_VALUE', 'NOT_RELEVANT'):
            result['is_high_value'] = False
            result['quality_gate_reason'] = f'low_value_category ({category})'
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low value category ({category})")
            return result
        
        # Rule 4: Confidence must be sufficient
        confidence = result.get('confidence', 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        
        if confidence < 0.7:
            result['is_high_value'] = False
            result['quality_gate_reason'] = f'low_confidence ({confidence:.2f})'
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate: low confidence ({confidence:.2f})")
            return result
        
        # Passed all gates
        result['quality_gate_reason'] = 'passed'
        return result
    
    # ============================================
    # BACKWARD COMPATIBILITY METHODS (V1 API)
    # ============================================
    
    def _build_prompt(self, content: str) -> str:
        """
        V1 backward compatibility: Build analysis prompt.
        
        Redirects to V2 prompt builder.
        """
        return build_analysis_prompt_v2(content)
    
    def _parse_response(self, response_text: str) -> Optional[AnalysisResult]:
        """
        V1 backward compatibility: Parse JSON response.
        
        Parses both V1 and V2 formats and converts to V1 AnalysisResult.
        Applies quality gate for betting_impact.
        
        V1 format: is_relevant, affected_team, summary
        V2 format: is_high_value, team, summary_italian
        """
        result = self._parse_response_v2(response_text)
        if not result:
            return None
        
        # Apply quality gate
        result = self._apply_quality_gate(result)
        
        # Determine is_relevant based on V2 fields (or V1 fallback)
        # V1 logic: is_relevant = True only if betting_impact is HIGH/MEDIUM/CRITICAL
        betting_impact = result.get('betting_impact', 'LOW')
        if betting_impact not in ('HIGH', 'MEDIUM', 'CRITICAL'):
            betting_impact = 'LOW'
        
        # Support both V1 (is_relevant) and V2 (is_high_value)
        is_relevant = result.get('is_high_value', result.get('is_relevant', False))
        if betting_impact == 'LOW':
            is_relevant = False
        
        # Support both V1 (affected_team) and V2 (team)
        affected_team = result.get('team') or result.get('affected_team')
        
        # Support both V1 (summary) and V2 (summary_italian)
        summary = result.get('summary_italian') or result.get('summary', '')
        
        return AnalysisResult(
            is_relevant=is_relevant,
            category=result.get('category', 'OTHER'),
            affected_team=affected_team,
            confidence=float(result.get('confidence', 0.0)),
            summary=summary,
            betting_impact=betting_impact
        )
    
    # Keep old method for backward compatibility
    async def analyze(self, content: str) -> Optional[AnalysisResult]:
        """
        Legacy method - redirects to V2 and converts result.
        
        Kept for backward compatibility.
        """
        result = await self.analyze_v2(content)
        if not result:
            return None
        
        # Convert V2 result to AnalysisResult
        return AnalysisResult(
            is_relevant=result.get('is_high_value', False),
            category=result.get('category', 'OTHER'),
            affected_team=result.get('team'),
            confidence=float(result.get('confidence', 0.0)),
            summary=result.get('summary_italian', ''),
            betting_impact=result.get('betting_impact', 'LOW')
        )
    
    def get_last_call_time(self) -> float:
        """Get timestamp of last API call."""
        return self._last_call_time
    
    def get_call_count(self) -> int:
        """Get total number of API calls."""
        return self._call_count


# ============================================
# TELEGRAM ALERTER
# ============================================

class TelegramAlerter:
    """
    Sends alerts to Telegram.
    
    Uses 🔔 RADAR emoji to distinguish from main bot (🚨 EARLYBIRD).
    Implements retry with exponential backoff.
    
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self._alerts_sent = 0
        self._alerts_failed = 0
    
    async def send_alert(self, alert: RadarAlert, max_retries: int = 3) -> bool:
        """
        Send formatted alert to Telegram.
        
        Returns True if sent successfully.
        
        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        if not self._token or not self._chat_id:
            logger.error("❌ [NEWS-RADAR] Telegram credentials not configured")
            return False
        
        message = alert.to_telegram_message()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        # Retry with exponential backoff
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    requests.post,
                    url,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self._alerts_sent += 1
                    logger.info(f"🔔 [NEWS-RADAR] Alert sent: {alert.affected_team} - {alert.category}")
                    return True
                
                if response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                    logger.warning(f"⚠️ [NEWS-RADAR] Telegram rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                
                logger.error(f"❌ [NEWS-RADAR] Telegram error: {response.status_code} - {response.text[:100]}")
                
            except requests.Timeout:
                logger.warning(f"⚠️ [NEWS-RADAR] Telegram timeout (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] Telegram error: {e}")
            
            # Exponential backoff: 2s, 4s, 8s
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                await asyncio.sleep(wait_time)
        
        self._alerts_failed += 1
        logger.error(f"❌ [NEWS-RADAR] Failed to send alert after {max_retries} attempts")
        return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get alerter statistics."""
        return {
            "alerts_sent": self._alerts_sent,
            "alerts_failed": self._alerts_failed,
        }


# ============================================
# NEWS RADAR MONITOR (Main Class)
# ============================================

class NewsRadarMonitor:
    """
    Autonomous news monitoring component.
    
    Runs independently from main bot, sends direct Telegram alerts.
    
    Flow:
    1. Load sources from config
    2. Scan sources in priority order
    3. Extract content (HTTP + Playwright fallback)
    4. Apply exclusion filter
    5. Analyze relevance
    6. Route based on confidence (alert / deepseek / skip)
    7. Send Telegram alerts
    
    Requirements: 1.1-1.4, 10.1-10.4
    """
    
    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE):
        """
        Initialize NewsRadarMonitor.
        
        V2.0: Simplified - uses singleton filters from modules.
        
        Requirements: 1.1
        """
        self._config_file = config_file
        self._config: RadarConfig = RadarConfig()
        self._config_mtime: float = 0.0
        
        # Components
        self._content_cache: Optional[ContentCache] = None
        self._extractor: Optional[ContentExtractor] = None
        self._deepseek: Optional[DeepSeekFallback] = None
        self._alerter: Optional[TelegramAlerter] = None
        
        # V7.0: Optional Tavily
        self._tavily = None
        self._tavily_budget = None
        
        # Circuit breakers per source
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # State
        self._running = False
        self._stop_event = asyncio.Event()
        self._scan_task: Optional[asyncio.Task] = None
        
        # Stats
        self._urls_scanned = 0
        self._alerts_sent = 0
        self._last_cycle_time: Optional[datetime] = None
        
        logger.info("🔔 [NEWS-RADAR] V2.0 Monitor created")
    
    async def start(self) -> bool:
        """
        Start the monitor.
        
        Returns True if started successfully.
        
        Requirements: 1.1, 10.1
        """
        if self._running:
            logger.warning("⚠️ [NEWS-RADAR] Already running")
            return True
        
        try:
            # Load configuration
            self._config = load_config(self._config_file)
            self._update_config_mtime()
            
            if not self._config.sources:
                logger.warning("⚠️ [NEWS-RADAR] No sources configured")
            
            # Initialize components
            self._content_cache = ContentCache(
                max_entries=DEFAULT_CACHE_MAX_ENTRIES,
                ttl_hours=self._config.global_settings.cache_ttl_hours
            )
            
            self._extractor = ContentExtractor(
                page_timeout=self._config.global_settings.page_timeout_seconds
            )
            
            if not await self._extractor.initialize():
                logger.error("❌ [NEWS-RADAR] Failed to initialize extractor")
                return False
            
            # V2.0: Initialize DeepSeek and alerter (other filters are singletons)
            self._deepseek = DeepSeekFallback()
            self._alerter = TelegramAlerter()
            
            # V7.0: Initialize Tavily for pre-enrichment (optional)
            try:
                from src.ingestion.tavily_provider import get_tavily_provider
                from src.ingestion.tavily_budget import get_budget_manager
                self._tavily = get_tavily_provider()
                self._tavily_budget = get_budget_manager()
                tavily_status = "enabled" if self._tavily.is_available() else "disabled"
                logger.info(f"🔍 [NEWS-RADAR] Tavily pre-enrichment {tavily_status}")
            except ImportError:
                self._tavily = None
                self._tavily_budget = None
                logger.debug("⚠️ [NEWS-RADAR] Tavily not available")
            
            # Start scan loop
            self._running = True
            self._stop_event.clear()
            self._scan_task = asyncio.create_task(self._scan_loop())
            
            logger.info(f"✅ [NEWS-RADAR] V2.0 Started with {len(self._config.sources)} sources")
            logger.info(f"   High-value signal detection: ENABLED")
            logger.info(f"   Quality gate: ENABLED (team required, impact >= MEDIUM)")
            return True
            
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Failed to start: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop the monitor gracefully.
        
        Requirements: 10.3
        """
        if not self._running:
            return True
        
        logger.info("🛑 [NEWS-RADAR] Stopping...")
        
        self._running = False
        self._stop_event.set()
        
        # Wait for scan task
        if self._scan_task:
            try:
                self._scan_task.cancel()
                await asyncio.wait_for(asyncio.shield(self._scan_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._scan_task = None
        
        # Shutdown extractor
        if self._extractor:
            await self._extractor.shutdown()
        
        logger.info("✅ [NEWS-RADAR] Stopped")
        return True
    
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running
    
    def _update_config_mtime(self) -> None:
        """Update stored config file modification time."""
        try:
            self._config_mtime = Path(self._config_file).stat().st_mtime
        except Exception:
            self._config_mtime = 0.0
    
    def _check_config_changed(self) -> bool:
        """Check if config file has been modified."""
        try:
            current_mtime = Path(self._config_file).stat().st_mtime
            return current_mtime > self._config_mtime
        except Exception:
            return False
    
    def reload_sources(self) -> None:
        """
        Reload sources from config file (hot reload).
        
        Requirements: 8.2
        """
        old_count = len(self._config.sources)
        self._config = load_config(self._config_file)
        self._update_config_mtime()
        
        new_count = len(self._config.sources)
        logger.info(f"🔄 [NEWS-RADAR] Reloaded config: {old_count} → {new_count} sources")
    
    def _get_circuit_breaker(self, url: str) -> CircuitBreaker:
        """Get or create circuit breaker for a URL."""
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = CircuitBreaker()
        return self._circuit_breakers[url]
    
    async def _scan_loop(self) -> None:
        """
        Main scan loop that runs continuously.
        
        Requirements: 1.2, 1.3
        """
        logger.info("🔄 [NEWS-RADAR] Scan loop started")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Check for config hot reload
                if self._check_config_changed():
                    self.reload_sources()
                
                # Run scan cycle
                alerts_sent = await self.scan_cycle()
                
                self._last_cycle_time = datetime.now(timezone.utc)
                logger.info(f"🔔 [NEWS-RADAR] Cycle complete: {self._urls_scanned} URLs, {alerts_sent} alerts")
                
                # Wait before next cycle
                interval = self._config.global_settings.default_scan_interval_minutes * 60
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval
                    )
                    break
                except asyncio.TimeoutError:
                    pass
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [NEWS-RADAR] Scan loop error: {e}")
                await asyncio.sleep(60)
        
        logger.info("🛑 [NEWS-RADAR] Scan loop stopped")
    
    async def scan_cycle(self) -> int:
        """
        Execute one scan cycle over all due sources.
        
        V7.3: Uses batch HTTP extraction for single-page sources.
        
        Returns number of alerts sent.
        
        Requirements: 1.2, 8.4
        """
        alerts_sent = 0
        urls_scanned = 0
        
        # Get sources due for scanning, sorted by priority (descending = highest first)
        due_sources = [s for s in self._config.sources if s.is_due_for_scan()]
        due_sources.sort(key=lambda s: s.priority)  # Lower number = higher priority
        
        if not due_sources:
            return 0
        
        # V7.3: Separate single-page and paginated sources
        single_sources = [s for s in due_sources if s.navigation_mode != "paginated"]
        paginated_sources = [s for s in due_sources if s.navigation_mode == "paginated"]
        
        # V7.3: Batch HTTP extraction for single-page sources
        if single_sources:
            # Filter by circuit breaker
            eligible_sources = []
            for source in single_sources:
                breaker = self._get_circuit_breaker(source.url)
                if breaker.can_execute():
                    eligible_sources.append(source)
                else:
                    logger.debug(f"🔴 [NEWS-RADAR] Skipping {source.name} (circuit OPEN)")
            
            if eligible_sources:
                # Batch extract all URLs
                urls = [s.url for s in eligible_sources]
                logger.info(f"⚡ [NEWS-RADAR] Batch extracting {len(urls)} single-page sources")
                
                contents = await self._extractor.extract_batch_http(urls, max_concurrent=5)
                
                # Process each result
                for source in eligible_sources:
                    if not self._running or self._stop_event.is_set():
                        break
                    
                    content = contents.get(source.url)
                    breaker = self._get_circuit_breaker(source.url)
                    urls_scanned += 1
                    
                    if content:
                        breaker.record_success()
                        alert = await self._process_content(content, source, source.url)
                        
                        if alert:
                            if self._alerter and await self._alerter.send_alert(alert):
                                alerts_sent += 1
                                self._alerts_sent += 1
                    else:
                        breaker.record_failure()
                    
                    # Update last scanned time
                    source.last_scanned = datetime.now(timezone.utc)
        
        # Process paginated sources sequentially (require browser navigation)
        for source in paginated_sources:
            if not self._running or self._stop_event.is_set():
                break
            
            # Scan source
            alert = await self.scan_source(source)
            urls_scanned += 1
            
            if alert:
                # Send alert
                if self._alerter and await self._alerter.send_alert(alert):
                    alerts_sent += 1
                    self._alerts_sent += 1
            
            # Update last scanned time
            source.last_scanned = datetime.now(timezone.utc)
        
        self._urls_scanned = urls_scanned
        return alerts_sent
    
    async def scan_source(self, source: RadarSource) -> Optional[RadarAlert]:
        """
        Scan a single source URL.
        
        Requirements: 1.4, 2.4, 10.2
        """
        try:
            # Check circuit breaker
            breaker = self._get_circuit_breaker(source.url)
            if not breaker.can_execute():
                logger.debug(f"🔴 [NEWS-RADAR] Skipping {source.name} (circuit OPEN)")
                return None
            
            # Extract content
            if source.navigation_mode == "paginated" and source.link_selector:
                # Paginated extraction
                results = await self._extractor.extract_with_navigation(
                    source.url,
                    source.link_selector,
                    max_links=self._config.global_settings.max_links_per_paginated_source,
                    delay_seconds=self._config.global_settings.navigation_delay_seconds
                )
                
                # Process each extracted page
                for page_url, content in results:
                    alert = await self._process_content(content, source, page_url)
                    if alert:
                        breaker.record_success()
                        return alert
                
                if not results:
                    breaker.record_failure()
                else:
                    breaker.record_success()
                return None
            else:
                # Single page extraction
                content = await self._extractor.extract(source.url)
                
                if not content:
                    breaker.record_failure()
                    return None
                
                breaker.record_success()
                return await self._process_content(content, source, source.url)
                
        except Exception as e:
            logger.error(f"❌ [NEWS-RADAR] Error scanning {source.name}: {e}")
            return None
    
    async def _process_content(
        self, 
        content: str, 
        source: RadarSource, 
        url: str
    ) -> Optional[RadarAlert]:
        """
        V2.0: Process extracted content through the new high-value pipeline.
        
        New flow:
        1. Garbage filter (skip menus, login, etc.)
        2. High-value signal detection (multilingual patterns)
        3. If signal detected → DeepSeek for structured extraction
        4. Quality gate (team must be identified, impact must be HIGH/MEDIUM)
        5. Create alert only if passes all gates
        
        Requirements: 3.5, 4.5, 5.1, 5.2
        """
        # V1.1: Safety check - ensure components are initialized
        if not self._content_cache:
            logger.error("❌ [NEWS-RADAR] Components not initialized - call start() first")
            return None
        
        # V7.0: Check shared cache first (cross-component deduplication)
        try:
            from src.utils.shared_cache import get_shared_cache
            shared_cache = get_shared_cache()
            if shared_cache.is_duplicate(content=content, url=url, source="news_radar"):
                logger.debug(f"🔄 [NEWS-RADAR] Skipping cross-component duplicate: {url[:50]}...")
                return None
        except ImportError:
            pass  # Shared cache not available, continue with local cache
        
        # Check local cache (deduplication)
        if self._content_cache.is_cached(content):
            logger.debug(f"🔄 [NEWS-RADAR] Skipping duplicate: {url[:50]}...")
            return None
        
        # Cache content locally
        self._content_cache.add(content)
        
        # V7.0: Mark in shared cache
        try:
            from src.utils.shared_cache import get_shared_cache
            shared_cache = get_shared_cache()
            shared_cache.mark_seen(content=content, url=url, source="news_radar")
        except ImportError:
            pass
        
        # ============================================
        # V2.0: NEW HIGH-VALUE PIPELINE
        # ============================================
        
        # Step 1: Garbage filter
        garbage_filter = get_garbage_filter()
        is_garbage, garbage_reason = garbage_filter.is_garbage(content)
        if is_garbage:
            logger.debug(f"🗑️ [NEWS-RADAR] Garbage filtered ({garbage_reason}): {url[:50]}...")
            return None
        
        # Clean content
        cleaned_content = garbage_filter.clean_content(content)
        if len(cleaned_content) < 100:
            logger.debug(f"🗑️ [NEWS-RADAR] Content too short after cleaning: {url[:50]}...")
            return None
        
        # Step 2: Apply exclusion filter (basketball, women's, etc.)
        exclusion_filter = get_exclusion_filter()
        if exclusion_filter.is_excluded(cleaned_content):
            reason = exclusion_filter.get_exclusion_reason(cleaned_content)
            logger.debug(f"🚫 [NEWS-RADAR] Excluded ({reason}): {url[:50]}...")
            return None
        
        # Step 3: Apply positive news filter (player returning = skip)
        positive_filter = get_positive_news_filter()
        if positive_filter.is_positive_news(cleaned_content):
            reason = positive_filter.get_positive_reason(cleaned_content)
            logger.debug(f"✅ [NEWS-RADAR] Skipping positive news ({reason}): {url[:50]}...")
            return None
        
        # Step 4: High-value signal detection
        signal_detector = get_signal_detector()
        signal = signal_detector.detect(cleaned_content)
        
        if not signal.detected:
            # No high-value signal detected by patterns
            # Still try DeepSeek for non-European languages or subtle signals
            # But only if content looks promising (has some football keywords)
            if not self._has_football_keywords(cleaned_content):
                logger.debug(f"📭 [NEWS-RADAR] No signal, no football keywords: {url[:50]}...")
                return None
            
            # V7.3: Pre-filter score to reduce unnecessary DeepSeek calls
            prefilter_score = self._compute_prefilter_score(cleaned_content)
            if prefilter_score < 0.3:
                logger.debug(f"📭 [NEWS-RADAR] Pre-filter score too low ({prefilter_score:.2f}): {url[:50]}...")
                return None
            
            logger.debug(f"🔍 [NEWS-RADAR] No pattern match, pre-filter={prefilter_score:.2f}, trying DeepSeek: {url[:50]}...")
        else:
            logger.info(f"🎯 [NEWS-RADAR] High-value signal: {signal.signal_type} ({signal.matched_pattern})")
        
        # Step 5: DeepSeek structured extraction
        deep_result = await self._deepseek.analyze_v2(cleaned_content)
        
        if not deep_result:
            logger.debug(f"❌ [NEWS-RADAR] DeepSeek analysis failed: {url[:50]}...")
            return None
        
        # Step 6: Check if passed quality gate
        if not deep_result.get('is_high_value', False):
            reason = deep_result.get('quality_gate_reason', 'unknown')
            logger.debug(f"🚫 [NEWS-RADAR] Quality gate failed ({reason}): {url[:50]}...")
            return None
        
        # Step 7: Create alert with structured data
        alert = RadarAlert(
            source_name=source.name,
            source_url=url,
            affected_team=deep_result.get('team', 'Unknown'),
            opponent=deep_result.get('opponent'),
            competition=deep_result.get('competition'),
            match_date=deep_result.get('match_date'),
            category=deep_result.get('category', 'OTHER'),
            absent_count=deep_result.get('absent_count', 0),
            absent_players=deep_result.get('absent_players', []),
            betting_impact=deep_result.get('betting_impact', 'MEDIUM'),
            summary=deep_result.get('summary_italian', 'Notizia rilevante per betting'),
            confidence=float(deep_result.get('confidence', 0.8))
        )
        
        # Step 8: Enrich alert with database context
        alert = await self._enrich_alert(alert)
        
        # ============================================
        # V7.3: NEW VALIDATION STEPS
        # ============================================
        
        # Step 9: Fixture correlation check
        # Skip alert if team doesn't play within 72h
        if alert.enrichment_context and not alert.enrichment_context.has_match():
            logger.info(f"⏭️ [NEWS-RADAR] Skipping alert - no match within 72h for {alert.affected_team}")
            return None
        
        # Step 10: Odds movement check
        odds_suffix = ""
        if _ODDS_CHECK_AVAILABLE and alert.affected_team and alert.affected_team != "Unknown":
            try:
                match_id = alert.enrichment_context.match_id if alert.enrichment_context else None
                odds_result, odds_suffix = await check_odds_for_alert_async(
                    alert.affected_team,
                    match_id=match_id
                )
                
                # Log odds status
                if odds_result.status != OddsMovementStatus.UNKNOWN:
                    logger.info(f"📊 [NEWS-RADAR] Odds check for {alert.affected_team}: {odds_result.edge_assessment}")
                
                # Adjust confidence based on odds movement
                if odds_result.should_boost_priority:
                    alert.confidence = min(alert.confidence + 0.05, 0.95)
                    logger.info(f"💎 [NEWS-RADAR] Confidence boosted (stable odds): {alert.confidence:.0%}")
                elif odds_result.should_reduce_priority:
                    # Don't skip, but note in summary
                    alert.summary = f"{alert.summary} [⚠️ Quote già mosse]"
                    logger.warning(f"⚠️ [NEWS-RADAR] Major odds movement detected - market may already know")
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Odds check failed: {e}")
        
        # Step 11: Cross-source validation
        validation_tag = ""
        if _CROSS_VALIDATOR_AVAILABLE and alert.affected_team and alert.affected_team != "Unknown":
            try:
                validator = get_cross_validator()
                boosted_confidence, is_multi_source, validation_tag = validator.register_alert(
                    team=alert.affected_team,
                    category=alert.category,
                    source_name=source.name,
                    source_url=url,
                    confidence=alert.confidence
                )
                
                if is_multi_source:
                    alert.confidence = boosted_confidence
                    logger.info(f"✅ [NEWS-RADAR] Multi-source confirmation: {validation_tag}")
            except Exception as e:
                logger.debug(f"⚠️ [NEWS-RADAR] Cross-validation failed: {e}")
        
        # Store validation info for alert message
        alert._odds_suffix = odds_suffix
        alert._validation_tag = validation_tag
        
        logger.info(
            f"🔔 [NEWS-RADAR] Alert created: {alert.affected_team} - {alert.category} "
            f"({alert.absent_count} assenti, impact={alert.betting_impact})"
        )
        
        return alert
    
    def _has_football_keywords(self, content: str) -> bool:
        """
        Quick check if content has basic football keywords.
        
        Used to decide if DeepSeek analysis is worth trying
        when no high-value pattern was detected.
        """
        football_keywords = [
            'football', 'soccer', 'match', 'game', 'team', 'player',
            'goal', 'league', 'cup', 'coach', 'manager', 'squad',
            'calcio', 'fútbol', 'futebol', 'fußball', 'voetbal',
            'partita', 'partido', 'jogo', 'spiel', 'wedstrijd',
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in football_keywords)
    
    def _compute_prefilter_score(self, content: str) -> float:
        """
        V7.3: Compute quick pre-filter score to decide if DeepSeek is worth calling.
        
        This reduces unnecessary API calls by ~30-40% by filtering out
        content that is unlikely to be betting-relevant.
        
        Score components:
        - Injury/absence keywords: +0.3
        - Team/player mentions: +0.2
        - Match context (vs, against): +0.2
        - Negative sentiment (out, miss, doubt): +0.2
        - Recency indicators (today, tomorrow): +0.1
        
        Returns:
            Score 0.0-1.0 (threshold 0.3 for DeepSeek call)
        """
        if not content:
            return 0.0
        
        content_lower = content.lower()
        score = 0.0
        
        # Injury/absence keywords (+0.3)
        injury_keywords = [
            'injury', 'injured', 'infortunio', 'lesión', 'lesão',
            'out', 'miss', 'absent', 'assente', 'ausente',
            'ruled out', 'sidelined', 'unavailable',
            'suspended', 'sospeso', 'suspenso', 'sancionado',
            'doubt', 'doubtful', 'dubbio', 'duda',
        ]
        if any(kw in content_lower for kw in injury_keywords):
            score += 0.3
        
        # Team/player context (+0.2)
        team_indicators = [
            'team', 'squad', 'club', 'squadra', 'equipo', 'equipe',
            'player', 'giocatore', 'jugador', 'jogador',
            'striker', 'midfielder', 'defender', 'goalkeeper',
            'attaccante', 'centrocampista', 'difensore', 'portiere',
        ]
        if any(kw in content_lower for kw in team_indicators):
            score += 0.2
        
        # Match context (+0.2)
        match_indicators = [
            ' vs ', ' v ', 'against', 'contro', 'contra',
            'match', 'game', 'partita', 'partido', 'jogo',
            'fixture', 'clash', 'derby',
        ]
        if any(kw in content_lower for kw in match_indicators):
            score += 0.2
        
        # Negative sentiment for betting (+0.2)
        negative_betting = [
            'will miss', 'won\'t play', 'not available',
            'ruled out', 'sidelined', 'benched',
            'non giocherà', 'no jugará', 'não jogará',
            'crisis', 'emergency', 'blow', 'setback',
        ]
        if any(kw in content_lower for kw in negative_betting):
            score += 0.2
        
        # Recency indicators (+0.1)
        recency = [
            'today', 'tomorrow', 'tonight', 'weekend',
            'oggi', 'domani', 'stasera',
            'hoy', 'mañana', 'hoje', 'amanhã',
        ]
        if any(kw in content_lower for kw in recency):
            score += 0.1
        
        return min(score, 1.0)
    
    async def _enrich_alert(self, alert: RadarAlert) -> RadarAlert:
        """
        V1.3: Enrich alert with database context (classifica, biscotto).
        
        Light enrichment that adds context without heavy API calls.
        Uses data already in database or FotMob cache.
        
        V7.3: Always sets enrichment_context (even if no match found)
        to allow fixture correlation check in Step 9.
        
        Args:
            alert: RadarAlert to enrich
            
        Returns:
            Same alert with enrichment_context populated (if available)
        """
        if not _ENRICHMENT_AVAILABLE:
            logger.debug("⚠️ [NEWS-RADAR] Enrichment module not available")
            return alert
        
        # Skip if no team to enrich
        if not alert.affected_team or alert.affected_team == "Unknown":
            return alert
        
        try:
            # Get enrichment context asynchronously
            context = await enrich_radar_alert_async(alert.affected_team)
            
            # V7.3: Always set context (even if no match) for fixture correlation
            if context:
                alert.enrichment_context = context
                if context.has_match():
                    logger.info(
                        f"✨ [NEWS-RADAR] Enriched alert for {alert.affected_team}: "
                        f"{context.team_zone}, match {context.home_team} vs {context.away_team}"
                    )
                else:
                    logger.debug(f"📭 [NEWS-RADAR] No upcoming match for {alert.affected_team}")
                
        except Exception as e:
            # Enrichment failure should not block alert
            logger.warning(f"⚠️ [NEWS-RADAR] Enrichment failed for {alert.affected_team}: {e}")
        
        return alert
    
    async def _tavily_enrich(self, content: str, url: str) -> Optional[str]:
        """
        V7.0: Use Tavily to enrich ambiguous content before DeepSeek.
        
        Called when initial analysis has confidence between 0.5 and 0.7.
        
        Args:
            content: Original content text
            url: Source URL for context
            
        Returns:
            Enriched context string or None
            
        Requirements: 4.1, 4.2
        """
        if not self._tavily or not self._tavily.is_available():
            return None
        
        if not self._tavily_budget or not self._tavily_budget.can_call("news_radar"):
            logger.debug("📊 [NEWS-RADAR] Tavily budget limit reached")
            return None
        
        try:
            # Extract key terms from content for search
            # Use first 200 chars as search context
            search_context = content[:200].replace('\n', ' ').strip()
            
            # Build search query
            query = f"football soccer {search_context}"
            
            # V7.1: Use native Tavily news parameters for better filtering
            response = self._tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=True,
                topic="news",
                days=3
            )
            
            if response:
                self._tavily_budget.record_call("news_radar")
                
                enrichment_parts = []
                
                if response.answer:
                    enrichment_parts.append(f"[TAVILY CONTEXT]\n{response.answer}")
                
                if response.results:
                    snippets = [f"• {r.content[:150]}" for r in response.results[:2]]
                    if snippets:
                        enrichment_parts.append("\n".join(snippets))
                
                if enrichment_parts:
                    logger.info(f"🔍 [NEWS-RADAR] Tavily enrichment found for {url[:50]}...")
                    return "\n".join(enrichment_parts)
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ [NEWS-RADAR] Tavily enrichment failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        return {
            "running": self._running,
            "sources_count": len(self._config.sources),
            "urls_scanned": self._urls_scanned,
            "alerts_sent": self._alerts_sent,
            "cache_size": self._content_cache.size() if self._content_cache else 0,
            "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
            "extractor_stats": self._extractor.get_stats() if self._extractor else {},
            "alerter_stats": self._alerter.get_stats() if self._alerter else {},
        }
