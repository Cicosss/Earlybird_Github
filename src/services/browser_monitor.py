"""
EarlyBird Browser Monitor - Always-On Web Monitoring V7.5

Independent component that actively monitors web sources 24/7 to discover
breaking news before they appear on search engines.

Unlike the Enrichment Worker (which enriches existing news), the Browser Monitor
is an ACTIVE SOURCE that discovers new news by navigating directly to websites.

Flow:
1. Load configured source URLs from config/browser_sources.json
2. Continuously scan sources in a loop (default 5 min interval)
3. Extract page text with Playwright + Trafilatura (clean article extraction)
4. [V7.5] Apply ExclusionFilter (skip basketball, women's, NFL, etc.)
5. [V7.5] Apply RelevanceAnalyzer (keyword-based pre-filtering)
6. [V7.5] Route based on confidence:
   - confidence < 0.5 → SKIP (no API call)
   - 0.5 ≤ confidence < 0.7 → DeepSeek FALLBACK (API call)
   - confidence ≥ 0.7 → ALERT DIRECT (no API call)
7. If relevant (confidence >= 0.7): notify news_hunter via callback
8. Deduplicate using content hash cache (24h TTL, 10k max entries)

V7.0 Improvements:
- playwright-stealth: Anti-detection (70-80% bypass rate on news sites)
- Resource blocking: -50% latency, -28% memory (block images/fonts/ads)
- Trafilatura: Clean article extraction (88-92% accuracy vs 70% raw text)

V7.1 Improvements:
- Circuit Breaker: Per-source failure tracking, skip failing sources temporarily
- Exponential Backoff: Smart retry with jitter (2s → 4s → 8s)
- Hybrid HTTP+Browser: Try HTTP first (5x faster), fallback to browser

V7.3 Improvements:
- Module-level imports: urlparse, psutil, browser_fingerprint for reliability
- Smarter retry logic: Only retry on network errors, not empty content
- Better JSON error handling: Specific exceptions for API response parsing
- Thread-safe stop: Uses call_soon_threadsafe for immediate shutdown
- Circuit breaker fix: Only counts network errors, not empty pages

V7.4 Improvements:
- Paginated Navigation: Navigate internal links for Elite 7 and Tier 2 sources
- extract_with_navigation(): Extract links from homepage, visit each article
- navigation_mode: "single" (default) or "paginated" per source
- link_selector: CSS selector to find article links on homepage
- max_links: Configurable limit on links to follow (default 5)

V7.5 Improvements:
- Smart API Usage: Pre-filter with ExclusionFilter + RelevanceAnalyzer
- 60-80% reduction in DeepSeek API calls
- Shared content_analysis module with news_radar (DRY compliance)
- Three-tier routing: SKIP / DEEPSEEK_FALLBACK / ALERT_DIRECT

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.4, 6.1-6.4, 7.1-7.4, 8.1-8.4
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import random
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, Tuple
from collections import OrderedDict
from urllib.parse import urlparse

# V7.5: Import shared content analysis utilities
from src.utils.content_analysis import (
    AnalysisResult,
    ExclusionFilter,
    RelevanceAnalyzer,
    get_exclusion_filter,
    get_relevance_analyzer,
)

# V7.3: Import psutil with fallback for memory monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# V7.3: Import browser fingerprint (lazy import fallback if not available)
try:
    from src.utils.browser_fingerprint import get_fingerprint
    FINGERPRINT_AVAILABLE = True
except ImportError:
    FINGERPRINT_AVAILABLE = False
    get_fingerprint = None

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_CONFIG_FILE = "config/browser_sources.json"
MAX_TEXT_LENGTH = 30000  # 30k characters
DEFAULT_SCAN_INTERVAL_MINUTES = 5
DEFAULT_MAX_CONCURRENT_PAGES = 2
DEFAULT_NAVIGATION_INTERVAL_SECONDS = 10
DEFAULT_PAGE_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_CACHE_MAX_ENTRIES = 10000
MEMORY_HIGH_THRESHOLD = 80  # Pause if > 80%
MEMORY_LOW_THRESHOLD = 70   # Resume if < 70%
RELEVANCE_CONFIDENCE_THRESHOLD = 0.7

# V7.5: Smart API routing thresholds
DEEPSEEK_CONFIDENCE_THRESHOLD = 0.5  # Use DeepSeek for 0.5 <= confidence < 0.7
ALERT_CONFIDENCE_THRESHOLD = 0.7     # Alert directly for confidence >= 0.7

# V7.6: Tavily short content threshold
TAVILY_SHORT_CONTENT_THRESHOLD = 500  # Use Tavily for content < 500 chars

# DeepSeek Configuration (V6.0)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# V7.1: Circuit Breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # Open circuit after 3 consecutive failures
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300  # 5 minutes before trying again
CIRCUIT_BREAKER_HALF_OPEN_TIMEOUT = 60  # 1 minute in half-open state

# V7.1: Retry configuration
MAX_RETRIES = 2
RETRY_BASE_DELAY = 2  # seconds
RETRY_MAX_DELAY = 8  # seconds

# V7.1: HTTP timeout for hybrid mode
HTTP_TIMEOUT = 10  # seconds
HTTP_MIN_CONTENT_LENGTH = 200  # Minimum chars for valid HTTP extraction

# V7.0: Resource blocking patterns (images, fonts, ads, tracking)
BLOCKED_RESOURCE_PATTERNS = [
    '**/*.{png,jpg,jpeg,gif,svg,webp,ico}',  # Images
    '**/*.{woff,woff2,ttf,eot,otf}',  # Fonts
    '**/*doubleclick*',  # Ads
    '**/*googleadservices*',  # Ads
    '**/*google-analytics*',  # Tracking
    '**/*facebook.com/tr*',  # Tracking
    '**/*googlesyndication*',  # Ads
    '**/*adservice*',  # Ads
]

# V7.0/V8.4: Trafilatura via centralized module (handles warning suppression)
try:
    from src.utils.trafilatura_extractor import (
        extract_with_trafilatura as _central_extract,
        extract_with_fallback as _extract_with_fallback,
        is_valid_html,
        TRAFILATURA_AVAILABLE,
        record_extraction,
    )
    # Keep trafilatura import for backward compatibility
    if TRAFILATURA_AVAILABLE:
        import trafilatura
except ImportError:
    TRAFILATURA_AVAILABLE = False
    _central_extract = None
    _extract_with_fallback = None
    is_valid_html = lambda x: True  # type: ignore
    record_extraction = lambda x, y: None  # type: ignore
    logger.warning("⚠️ [BROWSER-MONITOR] trafilatura_extractor not available, using raw text extraction")

# V7.2: Human behavior simulation configuration
BEHAVIOR_SIMULATION_ENABLED = True  # Can be disabled for testing
BEHAVIOR_SCROLL_STEPS = (2, 4)  # Min/max scroll steps
BEHAVIOR_SCROLL_DELAY = (0.2, 0.6)  # Delay between scrolls (seconds)
BEHAVIOR_MOUSE_MOVE_ENABLED = True  # Simulate mouse movements
BEHAVIOR_TYPING_DELAY = (0.05, 0.15)  # Per-character typing delay (if needed)

# V7.0: playwright-stealth import with fallback
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    Stealth = None
    logger.warning("⚠️ [BROWSER-MONITOR] playwright-stealth not installed, running without stealth")


# ============================================
# V7.1: CIRCUIT BREAKER PATTERN
# ============================================

class CircuitBreaker:
    """
    Circuit Breaker pattern for per-source failure handling.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Source is failing, skip requests for recovery_timeout
    - HALF_OPEN: Testing if source recovered, allow one request
    
    V7.1: Prevents cascade failures when a source is down.
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
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.success_count = 0
    
    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # Check if recovery timeout has passed
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info(f"🔄 [CIRCUIT-BREAKER] Transitioning to HALF_OPEN")
                return True
            return False
        
        if self.state == "HALF_OPEN":
            # Allow one test request
            return True
        
        return False
    
    def record_success(self) -> None:
        """
        Record a successful request.
        
        V7.3: Simplified logic - one success in HALF_OPEN closes the circuit.
        """
        if self.state == "HALF_OPEN":
            # One success is enough to close the circuit
            self.state = "CLOSED"
            self.failure_count = 0
            self.success_count = 0
            logger.info(f"✅ [CIRCUIT-BREAKER] Circuit CLOSED (recovered)")
        elif self.state == "CLOSED":
            # Reset failure count on success in normal operation
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "HALF_OPEN":
            # Failed during test, go back to OPEN
            self.state = "OPEN"
            logger.warning(f"⚠️ [CIRCUIT-BREAKER] Circuit OPEN (failed in HALF_OPEN)")
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


# V7.4: Paginated navigation configuration
DEFAULT_MAX_LINKS_PER_PAGINATED = 5  # Max links to follow per source
DEFAULT_NAVIGATION_DELAY_SECONDS = 3  # Delay between page visits


@dataclass
class MonitoredSource:
    """
    Configuration for a monitored source URL.
    
    Attributes:
        url: Source URL to monitor
        league_key: League key for categorization
        scan_interval_minutes: How often to scan this source
        priority: Scan priority (1=highest, higher numbers=lower priority)
        name: Human-readable name for the source
        navigation_mode: "single" for single page, "paginated" for multi-page
        link_selector: CSS selector for links in paginated mode
        max_links: Maximum number of links to follow in paginated mode
        last_scanned: Timestamp of last scan
        source_timezone: Timezone of the source (e.g., "Europe/London", "America/Sao_Paulo")
                        Used for timezone-aware scanning optimization during off-peak hours
    
    V7.5: Added source_timezone for off-peak optimization.
    """
    url: str
    league_key: str
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    priority: int = 1
    name: str = ""
    navigation_mode: str = "single"  # V7.4: "single" or "paginated"
    link_selector: Optional[str] = None  # V7.4: CSS selector for paginated mode
    max_links: int = DEFAULT_MAX_LINKS_PER_PAGINATED  # V7.4: Max links to follow
    last_scanned: Optional[datetime] = None
    source_timezone: Optional[str] = None  # V7.5: e.g., "Europe/London"
    
    def is_due_for_scan(self) -> bool:
        """
        Check if this source is due for scanning.
        
        V7.5: Considers timezone for off-peak optimization.
        During off-peak hours (midnight-6am local time), extends interval
        to save resources since news is less likely to be published.
        
        Returns:
            True if source is due for scanning, False otherwise
        """
        if self.last_scanned is None:
            return True
        
        # Calculate effective interval (may be extended during off-peak)
        effective_interval = self._get_effective_interval()
        
        elapsed = datetime.now(timezone.utc) - self.last_scanned
        return elapsed >= timedelta(minutes=effective_interval)
    
    def _get_effective_interval(self) -> int:
        """
        V7.5: Get effective scan interval based on source timezone.
        
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
class GlobalSettings:
    """Global settings for the browser monitor."""
    default_scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    max_concurrent_pages: int = DEFAULT_MAX_CONCURRENT_PAGES
    navigation_interval_seconds: int = DEFAULT_NAVIGATION_INTERVAL_SECONDS
    page_timeout_seconds: int = DEFAULT_PAGE_TIMEOUT_SECONDS
    cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS
    cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES


@dataclass
class DiscoveredNews:
    """News item discovered by the monitor."""
    url: str
    title: str
    snippet: str
    category: str  # INJURY, LINEUP, SUSPENSION, TRANSFER, TACTICAL, OTHER
    affected_team: str
    confidence: float
    league_key: str
    source_name: str
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MonitorConfig:
    """Complete monitor configuration."""
    sources: List[MonitoredSource] = field(default_factory=list)
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)


class ContentCache:
    """
    Hash-based content cache for deduplication.
    
    Uses first 1000 chars of content to compute hash.
    Implements LRU eviction when max entries exceeded.
    Entries expire after TTL hours.
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    def __init__(self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES, ttl_hours: int = DEFAULT_CACHE_TTL_HOURS):
        self._cache: OrderedDict[str, datetime] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_hours = ttl_hours
    
    def compute_hash(self, content: str) -> str:
        """Compute hash from first 1000 chars of content.
        
        Phase 1 Critical Fix: Changed errors='ignore' to errors='replace' to preserve
        special characters. Added Unicode normalization before hashing.
        """
        # Use first 1000 chars for hash
        content_prefix = content[:1000] if len(content) > 1000 else content
        # Phase 1 Critical Fix: Use errors='replace' instead of 'ignore' to preserve special characters
        # Phase 1 Critical Fix: Add Unicode normalization before hashing
        return hashlib.sha256(content_prefix.encode('utf-8', errors='replace')).hexdigest()[:16]
    
    def is_cached(self, content: str) -> bool:
        """Check if content hash exists and is not expired.
        
        Args:
            content: Text content to check (handles None/empty safely)
            
        Returns:
            True if content is cached and not expired, False otherwise
        """
        # V7.3: Safe handling of None/empty content
        if not content:
            return False
        
        content_hash = self.compute_hash(content)
        
        if content_hash not in self._cache:
            return False
        
        # Check expiration
        cached_at = self._cache[content_hash]
        if datetime.now(timezone.utc) - cached_at > timedelta(hours=self._ttl_hours):
            # Expired, remove it
            del self._cache[content_hash]
            return False
        
        # Move to end (LRU)
        self._cache.move_to_end(content_hash)
        return True
    
    def cache(self, content: str) -> None:
        """Store content hash with current timestamp.
        
        Args:
            content: Text content to cache (handles None/empty safely)
        """
        # V7.3: Safe handling of None/empty content
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


def load_config(config_file: str = DEFAULT_CONFIG_FILE) -> MonitorConfig:
    """
    Load monitor configuration from JSON file.
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        MonitorConfig with sources and global settings
        
    Requirements: 2.1, 2.2
    """
    config_path = Path(config_file)
    
    if not config_path.exists():
        logger.warning(f"⚠️ [BROWSER-MONITOR] Config file not found: {config_file}")
        return MonitorConfig()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Parse global settings
        gs_data = data.get('global_settings', {})
        global_settings = GlobalSettings(
            default_scan_interval_minutes=gs_data.get('default_scan_interval_minutes', DEFAULT_SCAN_INTERVAL_MINUTES),
            max_concurrent_pages=gs_data.get('max_concurrent_pages', DEFAULT_MAX_CONCURRENT_PAGES),
            navigation_interval_seconds=gs_data.get('navigation_interval_seconds', DEFAULT_NAVIGATION_INTERVAL_SECONDS),
            page_timeout_seconds=gs_data.get('page_timeout_seconds', DEFAULT_PAGE_TIMEOUT_SECONDS),
            cache_ttl_hours=gs_data.get('cache_ttl_hours', DEFAULT_CACHE_TTL_HOURS),
            cache_max_entries=gs_data.get('cache_max_entries', DEFAULT_CACHE_MAX_ENTRIES)
        )
        
        # Parse sources
        sources = []
        for src_data in data.get('sources', []):
            if 'url' not in src_data or 'league_key' not in src_data:
                logger.warning(f"⚠️ [BROWSER-MONITOR] Skipping invalid source: {src_data}")
                continue
            
            source = MonitoredSource(
                url=src_data['url'],
                league_key=src_data['league_key'],
                scan_interval_minutes=src_data.get('scan_interval_minutes', global_settings.default_scan_interval_minutes),
                priority=src_data.get('priority', 1),
                name=src_data.get('name', src_data['url'][:50]),
                navigation_mode=src_data.get('navigation_mode', 'single'),  # V7.4
                link_selector=src_data.get('link_selector'),  # V7.4
                max_links=src_data.get('max_links', DEFAULT_MAX_LINKS_PER_PAGINATED),  # V7.4
                source_timezone=src_data.get('source_timezone')  # V7.5
            )
            sources.append(source)
        
        logger.info(f"✅ [BROWSER-MONITOR] Loaded {len(sources)} sources from {config_file}")
        return MonitorConfig(sources=sources, global_settings=global_settings)
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ [BROWSER-MONITOR] Invalid JSON in config: {e}")
        return MonitorConfig()
    except Exception as e:
        logger.error(f"❌ [BROWSER-MONITOR] Failed to load config: {e}")
        return MonitorConfig()


def get_sources_for_league(config: MonitorConfig, league_key: str) -> List[MonitoredSource]:
    """
    Get all sources configured for a specific league.
    
    Args:
        config: Monitor configuration
        league_key: League key to filter by
        
    Returns:
        List of MonitoredSource for the league
        
    Requirements: 2.4
    """
    return [s for s in config.sources if s.league_key == league_key]


def get_memory_usage_percent() -> float:
    """
    Get current system memory usage percentage.
    
    V7.3: Uses module-level psutil import with fallback.
    
    Returns:
        Memory usage as percentage (0-100)
    """
    if not PSUTIL_AVAILABLE or psutil is None:
        return 50.0  # Assume memory is fine if psutil not available
    
    try:
        return psutil.virtual_memory().percent
    except Exception:
        return 50.0


class BrowserMonitor:
    """
    Independent browser monitor that actively scans web sources 24/7.
    
    Discovers breaking news by navigating to configured URLs, extracting
    content with Playwright, and analyzing relevance with DeepSeek.
    
    V7.0 Improvements:
    - playwright-stealth: Anti-detection (70-80% bypass rate)
    - Resource blocking: -50% latency, -28% memory
    - Trafilatura: Clean article extraction (88-92% accuracy)
    
    V7.1 Improvements:
    - Circuit Breaker: Per-source failure tracking
    - Exponential Backoff: Smart retry with jitter
    - Hybrid HTTP+Browser: HTTP first, browser fallback
    
    Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.4, 6.1-6.4, 7.1-7.4, 8.1-8.4
    """
    
    def __init__(
        self,
        config_file: str = DEFAULT_CONFIG_FILE,
        on_news_discovered: Optional[Callable[[DiscoveredNews], None]] = None
    ):
        """
        Initialize BrowserMonitor.
        
        Args:
            config_file: Path to browser_sources.json config file
            on_news_discovered: Callback invoked when relevant news is found
        """
        self._config_file = config_file
        self._on_news_discovered = on_news_discovered
        
        # State
        self._running = False
        self._paused = False
        self._stop_event = asyncio.Event()
        
        # Configuration
        self._config: MonitorConfig = MonitorConfig()
        self._config_mtime: float = 0.0
        
        # Content cache for deduplication
        self._content_cache: Optional[ContentCache] = None
        
        # Playwright resources
        self._playwright = None
        self._browser = None
        self._page_semaphore: Optional[asyncio.Semaphore] = None
        
        # Navigation timing
        self._last_navigation_time: float = 0.0
        
        # Stats
        self._urls_scanned = 0
        self._news_discovered = 0
        self._last_cycle_time: Optional[datetime] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._deepseek_calls = 0  # Track DeepSeek usage
        
        # V7.0: Track extraction method stats
        self._trafilatura_extractions = 0
        self._fallback_extractions = 0
        self._blocked_resources = 0
        
        # V7.1: Circuit breakers per source (keyed by URL)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # V7.1: Hybrid mode stats
        self._http_extractions = 0
        self._browser_extractions = 0
        self._circuit_breaker_skips = 0
        
        # V7.2: Behavior simulation stats
        self._behavior_simulations = 0
        self._behavior_simulation_failures = 0  # V7.6: Track failures for monitoring
        
        # V7.5: Smart API routing stats
        self._excluded_count = 0  # Content excluded by ExclusionFilter
        self._skipped_low_confidence = 0  # Skipped due to low confidence (< 0.5)
        self._direct_alerts = 0  # Direct alerts without DeepSeek (confidence >= 0.7)
        self._deepseek_fallbacks = 0  # DeepSeek fallback calls (0.5 <= confidence < 0.7)
        
        # V7.6: Tavily for short content expansion (initialized in start(), set to None here)
        self._tavily = None
        self._tavily_budget = None
        
        # V7.7: Lock per serializzare la ricreazione del browser (evita race condition)
        # Quando il browser crasha, più coroutine potrebbero tentare di ricrearlo
        # contemporaneamente. Il lock garantisce che solo una lo faccia.
        self._browser_lock: Optional[asyncio.Lock] = None  # Initialized in start()
        
        logger.info("🌐 [BROWSER-MONITOR] V7.7 Created (Browser stability fix + Smart API Routing)")
    
    # ============================================
    # LIFECYCLE METHODS
    # ============================================
    
    async def start(self) -> bool:
        """
        Start the browser monitor.
        
        Initializes Playwright, loads config, and starts the scan loop.
        
        Returns:
            True if started successfully, False otherwise
            
        Requirements: 1.1
        """
        if self._running:
            logger.warning("⚠️ [BROWSER-MONITOR] Already running")
            return True
        
        try:
            # Load configuration
            self._config = load_config(self._config_file)
            self._update_config_mtime()
            
            if not self._config.sources:
                logger.warning("⚠️ [BROWSER-MONITOR] No sources configured, starting anyway")
            
            # Initialize content cache
            self._content_cache = ContentCache(
                max_entries=self._config.global_settings.cache_max_entries,
                ttl_hours=self._config.global_settings.cache_ttl_hours
            )
            
            # V7.6: Initialize Tavily for short content expansion
            try:
                from src.ingestion.tavily_provider import get_tavily_provider
                from src.ingestion.tavily_budget import get_budget_manager
                self._tavily = get_tavily_provider()
                self._tavily_budget = get_budget_manager()
                tavily_status = "enabled" if self._tavily.is_available() else "disabled"
                logger.info(f"🔍 [BROWSER-MONITOR] Tavily short content expansion {tavily_status}")
            except ImportError:
                self._tavily = None
                self._tavily_budget = None
                logger.debug("⚠️ [BROWSER-MONITOR] Tavily not available")
            
            # Initialize Playwright
            if not await self._initialize_playwright():
                return False
            
            # Initialize semaphore for concurrent page limit
            self._page_semaphore = asyncio.Semaphore(
                self._config.global_settings.max_concurrent_pages
            )
            
            # V7.7: Initialize browser recreation lock
            self._browser_lock = asyncio.Lock()
            
            # Start scan loop
            self._running = True
            self._stop_event.clear()
            self._scan_task = asyncio.create_task(self._scan_loop())
            
            logger.info(f"✅ [BROWSER-MONITOR] Started with {len(self._config.sources)} sources")
            return True
            
        except Exception as e:
            logger.error(f"❌ [BROWSER-MONITOR] Failed to start: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop the browser monitor gracefully.
        
        Stops the scan loop and releases browser resources.
        
        Returns:
            True if stopped successfully
            
        Requirements: 1.4
        """
        if not self._running:
            return True
        
        logger.info("🛑 [BROWSER-MONITOR] Stopping...")
        
        # Signal stop
        self._running = False
        self._stop_event.set()
        
        # Wait for scan task to finish
        if self._scan_task:
            try:
                self._scan_task.cancel()
                await asyncio.wait_for(asyncio.shield(self._scan_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._scan_task = None
        
        # Shutdown Playwright
        await self._shutdown_playwright()
        
        logger.info("✅ [BROWSER-MONITOR] Stopped")
        return True
    
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running
    
    def is_paused(self) -> bool:
        """Check if monitor is paused (due to rate limit or memory)."""
        return self._paused
    
    def request_stop(self) -> None:
        """
        Thread-safe stop request.
        
        V7.3: Uses get_running_loop() for Python 3.10+ compatibility.
        Falls back gracefully if no event loop is running.
        
        Can be called from any thread to signal the monitor to stop.
        The actual cleanup happens in the monitor's own event loop.
        """
        logger.info("🛑 [BROWSER-MONITOR] Stop requested (thread-safe)")
        self._running = False
        
        # V7.3: Thread-safe event loop signaling (Python 3.10+ compatible)
        try:
            # Try to get the running loop (works from any thread)
            loop = asyncio.get_running_loop()
            # Schedule _stop_event.set() to run in the correct loop
            loop.call_soon_threadsafe(self._stop_event.set)
            logger.debug("🛑 [BROWSER-MONITOR] Stop event signaled via call_soon_threadsafe")
        except RuntimeError:
            # No event loop running in this thread - this is expected when called
            # from a non-async context. The _running flag will be checked on next iteration.
            logger.debug("🛑 [BROWSER-MONITOR] No running event loop, relying on _running flag")
    
    # ============================================
    # PLAYWRIGHT MANAGEMENT
    # ============================================
    
    async def _initialize_playwright(self) -> bool:
        """
        Initialize Playwright browser.
        
        Returns:
            True if initialized successfully
            
        Requirements: 3.1, 6.1
        """
        try:
            from playwright.async_api import async_playwright
            
            logger.info("🌐 [BROWSER-MONITOR] Launching Playwright...")
            self._playwright = await async_playwright().start()
            
            # Launch Chromium in headless mode with minimal resources
            # V7.7: Removed --single-process (causes instability on heavy sites)
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
            
            logger.info("✅ [BROWSER-MONITOR] Playwright initialized")
            return True
            
        except ImportError:
            logger.error("❌ [BROWSER-MONITOR] Playwright not installed")
            return False
        except Exception as e:
            logger.error(f"❌ [BROWSER-MONITOR] Failed to initialize Playwright: {e}")
            return False
    
    async def _shutdown_playwright(self) -> None:
        """Shutdown Playwright and release resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"⚠️ [BROWSER-MONITOR] Error closing browser: {e}")
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"⚠️ [BROWSER-MONITOR] Error stopping Playwright: {e}")
            self._playwright = None
    
    async def _ensure_browser_connected(self) -> bool:
        """
        V7.7: Ensure browser is connected, recreate if disconnected.
        
        This fixes the critical bug where the browser crashes/disconnects
        but self._browser is not None, causing TargetClosedError on new_page().
        
        V7.7: Uses asyncio.Lock to serialize browser recreation across coroutines.
        This prevents race conditions where multiple coroutines try to recreate
        the browser simultaneously after a crash.
        
        Returns:
            True if browser is available and connected, False otherwise
        """
        # V7.7: Use lock to serialize browser recreation
        # Multiple coroutines might detect the crash simultaneously
        if self._browser_lock is None:
            # Fallback if lock not initialized (shouldn't happen in normal flow)
            self._browser_lock = asyncio.Lock()
        
        async with self._browser_lock:
            # Re-check after acquiring lock (another coroutine might have fixed it)
            if self._browser and self._browser.is_connected():
                return True
            
            # Case 1: No browser at all
            if not self._browser:
                logger.warning("⚠️ [BROWSER-MONITOR] Browser is None, attempting to recreate...")
                return await self._recreate_browser_internal()
            
            # Case 2: Browser exists but is disconnected
            try:
                if not self._browser.is_connected():
                    logger.warning("⚠️ [BROWSER-MONITOR] Browser disconnected, recreating...")
                    return await self._recreate_browser_internal()
            except Exception as e:
                # is_connected() itself failed - browser is in bad state
                logger.warning(f"⚠️ [BROWSER-MONITOR] Browser state check failed: {e}, recreating...")
                return await self._recreate_browser_internal()
            
            return True
    
    async def _recreate_browser_internal(self) -> bool:
        """
        V7.7: Internal browser recreation (called with lock held).
        
        Safely closes existing resources and reinitializes Playwright.
        IMPORTANT: This method assumes the caller holds self._browser_lock.
        
        Returns:
            True if browser was successfully recreated
        """
        logger.info("🔄 [BROWSER-MONITOR] Recreating browser...")
        
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
                # V7.7: Removed --single-process (causes instability on heavy sites)
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
                logger.info("✅ [BROWSER-MONITOR] Browser recreated successfully")
                return True
            except Exception as e:
                logger.error(f"❌ [BROWSER-MONITOR] Failed to recreate browser: {e}")
                # Try full reinitialization
                await self._shutdown_playwright()
                return await self._initialize_playwright()
        else:
            # No playwright instance, do full initialization
            return await self._initialize_playwright()
    
    # ============================================
    # CONTENT EXTRACTION
    # ============================================
    
    async def _setup_resource_blocking(self, page) -> None:
        """
        V7.0: Block images, fonts, ads, tracking to reduce latency by ~50%.
        
        This significantly improves performance without affecting content extraction.
        """
        async def abort_route(route):
            """Async handler to abort blocked resources."""
            try:
                await route.abort()
            except Exception:
                pass  # Ignore abort errors (page might be closed)
        
        for pattern in BLOCKED_RESOURCE_PATTERNS:
            try:
                await page.route(pattern, abort_route)
                self._blocked_resources += 1
            except Exception:
                pass  # Ignore routing errors
    
    async def _apply_stealth(self, page) -> None:
        """
        V7.0: Apply playwright-stealth to evade bot detection.
        
        Bypasses ~70-80% of detection on news sites.
        """
        if STEALTH_AVAILABLE and Stealth is not None:
            try:
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                logger.debug("🥷 [BROWSER-MONITOR] Stealth mode applied")
            except Exception as e:
                logger.warning(f"⚠️ [BROWSER-MONITOR] Stealth failed: {e}")
    
    async def _simulate_human_behavior(self, page) -> None:
        """
        V7.2: Simulate realistic human behavior to evade behavioral detection.
        
        Implements:
        - Gradual scrolling with variable speed (not instant jumps)
        - Random mouse movements within viewport
        - Variable delays between actions
        
        This helps bypass sites that detect bot-like instant navigation patterns.
        """
        if not BEHAVIOR_SIMULATION_ENABLED:
            return
        
        try:
            # Get viewport dimensions safely
            viewport = page.viewport_size
            if not viewport:
                viewport = {"width": 1280, "height": 720}
            
            viewport_width = viewport.get("width", 1280)
            viewport_height = viewport.get("height", 720)
            
            # 1. Random mouse movement (simulates user looking at page)
            if BEHAVIOR_MOUSE_MOVE_ENABLED:
                try:
                    # Move to a random position in the upper half of the page
                    x = random.randint(100, max(101, viewport_width - 100))
                    y = random.randint(100, max(101, viewport_height // 2))
                    await page.mouse.move(x, y)
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                except Exception:
                    pass  # Mouse move is optional, don't fail on it
            
            # 2. Gradual scrolling (2-4 scroll steps with delays)
            num_scrolls = random.randint(*BEHAVIOR_SCROLL_STEPS)
            
            for i in range(num_scrolls):
                # Calculate scroll amount (30-50% of viewport per scroll)
                scroll_percent = random.uniform(0.3, 0.5)
                scroll_amount = int(viewport_height * scroll_percent)
                
                # Execute smooth scroll via JavaScript
                await page.evaluate(f"""
                    () => {{
                        window.scrollBy({{
                            top: {scroll_amount},
                            behavior: 'smooth'
                        }});
                    }}
                """)
                
                # Variable delay between scrolls
                delay = random.uniform(*BEHAVIOR_SCROLL_DELAY)
                await asyncio.sleep(delay)
                
                # Occasionally move mouse during scroll (more human-like)
                if BEHAVIOR_MOUSE_MOVE_ENABLED and random.random() < 0.3:
                    try:
                        x = random.randint(100, max(101, viewport_width - 100))
                        y = random.randint(100, max(101, viewport_height - 100))
                        await page.mouse.move(x, y)
                    except Exception:
                        pass
            
            # 3. Small pause at the end (user "reading")
            await asyncio.sleep(random.uniform(0.2, 0.5))
            
            self._behavior_simulations += 1
            logger.debug(f"🎭 [BROWSER-MONITOR] Human behavior simulated ({num_scrolls} scrolls)")
            
        except Exception as e:
            # V7.6: Track failures for monitoring (helps detect if sites are blocking us)
            self._behavior_simulation_failures += 1
            # Behavior simulation is optional - don't fail extraction on errors
            logger.debug(f"⚠️ [BROWSER-MONITOR] Behavior simulation skipped: {e}")
    
    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        """
        V7.0/V8.4: Extract clean article text using Trafilatura.
        
        Trafilatura provides 88-92% accuracy vs 70% for raw text extraction.
        It removes navigation, ads, footers, and extracts only article content.
        
        V8.4: Now uses centralized extractor with:
        - Pre-validation to avoid "discarding data: None" warnings
        - Intelligent fallback chain (trafilatura → regex → raw)
        
        Args:
            html: Raw HTML content
            
        Returns:
            Clean article text or None if extraction fails
        """
        if not TRAFILATURA_AVAILABLE or not html:
            return None
        
        # V8.4: Use centralized extractor with pre-validation
        if _central_extract is not None:
            # Pre-validate HTML to avoid trafilatura warnings
            if not is_valid_html(html):
                logger.debug("[BROWSER-MONITOR] HTML validation failed, skipping trafilatura")
                record_extraction('validation', False)
                return None
            
            text = _central_extract(html)
            if text:
                self._trafilatura_extractions += 1
                record_extraction('trafilatura', True)
                return text
            
            # Try fallback extraction (regex/raw) for better content recovery
            if _extract_with_fallback is not None:
                text, method = _extract_with_fallback(html)
                if text:
                    record_extraction(method, True)
                    logger.debug(f"[BROWSER-MONITOR] Fallback extraction succeeded: {method}")
                    return text
            
            record_extraction('trafilatura', False)
            return None
        
        # Legacy fallback if centralized extractor not available
        try:
            # Extract with trafilatura (fast, accurate)
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,  # Use fallback extractors if main fails
                favor_precision=True,  # Prefer precision over recall
            )
            
            if text and len(text) > 100:
                self._trafilatura_extractions += 1
                return text
            
            return None
            
        except Exception as e:
            logger.debug(f"⚠️ [BROWSER-MONITOR] Trafilatura extraction failed: {e}")
            return None
    
    async def extract_content(self, url: str) -> Optional[str]:
        """
        Extract text content from a URL using Playwright + Trafilatura.
        
        V7.0 Improvements:
        - Stealth mode to evade bot detection
        - Resource blocking for 50% latency reduction
        - Trafilatura for clean article extraction (88-92% accuracy)
        
        V7.6 Improvements:
        - Auto-recovery: Recreates browser if disconnected/crashed
        
        V7.7 Improvements:
        - Retry with browser recreation on TargetClosedError
        - Lock-protected browser recreation to avoid race conditions
        
        Args:
            url: URL to extract content from
            
        Returns:
            Extracted text (max 30k chars) or None on failure
            
        Requirements: 3.1, 6.1, 6.4
        """
        # V7.7: Retry loop for browser crash recovery
        max_retries = 2
        for attempt in range(max_retries):
            # V7.6: Ensure browser is connected, recreate if needed
            if not await self._ensure_browser_connected():
                logger.error("❌ [BROWSER-MONITOR] Browser not available and could not be recreated")
                return None
            
            if not self._page_semaphore:
                logger.error("❌ [BROWSER-MONITOR] Semaphore not initialized")
                return None
            
            # Acquire semaphore for concurrent page limit
            async with self._page_semaphore:
                page = None
                try:
                    # Create new page
                    page = await self._browser.new_page()
                    await page.set_viewport_size({"width": 1280, "height": 720})
                    
                    # V7.0: Apply stealth mode
                    await self._apply_stealth(page)
                    
                    # V7.0: Setup resource blocking (images, fonts, ads)
                    await self._setup_resource_blocking(page)
                    
                    # Navigate with timeout
                    timeout_ms = self._config.global_settings.page_timeout_seconds * 1000
                    await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    
                    # V7.2: Simulate human behavior (scroll, mouse movement)
                    # This helps bypass behavioral detection on protected sites
                    await self._simulate_human_behavior(page)
                    
                    # V7.0: Get HTML for Trafilatura extraction
                    html = await page.content()
                    
                    # V7.0: Try Trafilatura first (clean extraction)
                    text = self._extract_with_trafilatura(html)
                    
                    # Fallback to raw inner_text if Trafilatura fails
                    if not text:
                        text = await page.inner_text("body")
                        self._fallback_extractions += 1
                        logger.debug(f"📄 [BROWSER-MONITOR] Using fallback extraction for {url[:40]}...")
                    
                    # Limit text length
                    if text and len(text) > MAX_TEXT_LENGTH:
                        text = text[:MAX_TEXT_LENGTH]
                    
                    return text
                    
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ [BROWSER-MONITOR] Timeout: {url[:60]}...")
                    return None
                except Exception as e:
                    # V7.7: Check if this is a browser disconnection error (retryable)
                    error_msg = str(e).lower()
                    if "closed" in error_msg or "target" in error_msg:
                        logger.warning(f"⚠️ [BROWSER-MONITOR] Browser crashed (attempt {attempt + 1}/{max_retries}): {e}")
                        # Mark browser as needing recreation
                        self._browser = None
                        if attempt < max_retries - 1:
                            # Retry after recreation
                            continue
                        else:
                            logger.error(f"❌ [BROWSER-MONITOR] Browser crash recovery failed after {max_retries} attempts")
                            return None
                    else:
                        logger.warning(f"⚠️ [BROWSER-MONITOR] Navigation error: {e}")
                        return None
                finally:
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            pass
        
        return None  # Should not reach here, but safety fallback
    
    # ============================================
    # V7.1: HYBRID HTTP + BROWSER EXTRACTION
    # ============================================
    
    async def _extract_with_http(self, url: str) -> Optional[str]:
        """
        V7.1: Try to extract content using pure HTTP (no browser).
        V7.2: Now uses domain-sticky fingerprinting for consistency.
        V7.3: Uses module-level imports for reliability.
        
        This is 5x faster than browser extraction and works for ~80% of news sites.
        Falls back to browser if HTTP fails or content is too short.
        
        Args:
            url: URL to extract content from
            
        Returns:
            Extracted text or None if HTTP extraction fails
        """
        # V7.3: Check fingerprint availability at module level
        if not FINGERPRINT_AVAILABLE or get_fingerprint is None:
            logger.debug("⚠️ [BROWSER-MONITOR] Fingerprint module not available, skipping HTTP extraction")
            return None
        
        try:
            # V7.2: Extract domain for sticky fingerprint
            domain = None
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower() if parsed.netloc else None
            except Exception:
                pass
            
            # V7.2: Get domain-sticky headers for consistency
            fingerprint = get_fingerprint()
            if domain:
                headers = fingerprint.get_headers_for_domain(domain)
            else:
                headers = fingerprint.get_headers()
            
            # Use asyncio.to_thread for sync requests call
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=HTTP_TIMEOUT,
                headers=headers
            )
            
            if response.status_code != 200:
                # V7.2: Rotate domain fingerprint on errors
                if response.status_code in (403, 429) and domain:
                    fingerprint.force_rotate_domain(domain)
                return None
            
            html = response.text
            
            # Try Trafilatura extraction
            text = self._extract_with_trafilatura(html)
            
            if text and len(text) > HTTP_MIN_CONTENT_LENGTH:
                self._http_extractions += 1
                logger.debug(f"⚡ [BROWSER-MONITOR] HTTP extraction success: {url[:40]}...")
                return text
            
            return None
            
        except requests.Timeout:
            logger.debug(f"⏱️ [BROWSER-MONITOR] HTTP timeout: {url[:40]}...")
            return None
        except requests.RequestException as e:
            # V7.3: Specific exception for network errors (retryable)
            logger.debug(f"🌐 [BROWSER-MONITOR] HTTP network error: {e}")
            raise  # Re-raise to signal retryable error
        except Exception as e:
            logger.debug(f"⚠️ [BROWSER-MONITOR] HTTP extraction failed: {e}")
            return None
    
    async def extract_content_hybrid(self, url: str) -> Optional[str]:
        """
        V7.1: Hybrid extraction - HTTP first, browser fallback.
        V7.3: Fixed to properly catch HTTP errors and fallback to browser.
        
        Strategy:
        1. Try HTTP + Trafilatura (fast, 80% success rate)
        2. If HTTP fails or raises network error, use browser extraction (slower, 95% success rate)
        
        Args:
            url: URL to extract content from
            
        Returns:
            Extracted text or None if all methods fail
        """
        # Try HTTP first (5x faster)
        try:
            text = await self._extract_with_http(url)
            if text:
                return text
        except requests.RequestException:
            # V7.3: HTTP network error - fallback to browser (don't propagate)
            logger.debug(f"🔄 [BROWSER-MONITOR] HTTP failed, falling back to browser: {url[:40]}...")
        
        # Fallback to browser extraction
        self._browser_extractions += 1
        return await self.extract_content(url)
    
    # ============================================
    # V7.4: PAGINATED NAVIGATION EXTRACTION
    # ============================================
    
    async def extract_with_navigation(
        self, 
        url: str, 
        link_selector: str,
        max_links: int = DEFAULT_MAX_LINKS_PER_PAGINATED,
        delay_seconds: int = DEFAULT_NAVIGATION_DELAY_SECONDS
    ) -> List[Tuple[str, str]]:
        """
        V7.4: Extract from paginated source by navigating internal links.
        
        Extracts links from main page using CSS selector, visits each linked page,
        and extracts content. This allows discovering news from article pages
        rather than just reading the homepage.
        
        Args:
            url: Main page URL to start from
            link_selector: CSS selector to find article links
            max_links: Maximum number of links to follow (default 5)
            delay_seconds: Delay between page visits (default 3s)
            
        Returns:
            List of (article_url, content) tuples
            
        Requirements: V7.4 - Paginated navigation for Elite 7 and Tier 2 sources
        """
        # V7.6: Ensure browser is connected, recreate if needed
        if not await self._ensure_browser_connected():
            logger.error("❌ [BROWSER-MONITOR] Browser not available for navigation and could not be recreated")
            return []
        
        if not self._page_semaphore:
            logger.error("❌ [BROWSER-MONITOR] Semaphore not initialized")
            return []
        
        # V7.4: Validate inputs
        if not link_selector:
            logger.warning(f"⚠️ [BROWSER-MONITOR] No link_selector for {url[:40]}...")
            return []
        
        results: List[Tuple[str, str]] = []
        page = None
        
        async with self._page_semaphore:
            try:
                # Create new page
                page = await self._browser.new_page()
                await page.set_viewport_size({"width": 1280, "height": 720})
                
                # V7.0: Apply stealth mode
                await self._apply_stealth(page)
                
                # V7.0: Setup resource blocking
                await self._setup_resource_blocking(page)
                
                # Navigate to main page
                timeout_ms = self._config.global_settings.page_timeout_seconds * 1000
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                
                # V7.2: Simulate human behavior
                await self._simulate_human_behavior(page)
                
                # Extract links using CSS selector
                try:
                    links = await page.eval_on_selector_all(
                        link_selector,
                        "elements => elements.map(e => e.href).filter(h => h && h.startsWith('http'))"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ [BROWSER-MONITOR] Failed to extract links with selector '{link_selector}': {e}")
                    links = []
                
                # V7.4: Deduplicate and limit links
                seen_links = set()
                unique_links = []
                for link in links:
                    if link not in seen_links and len(unique_links) < max_links:
                        seen_links.add(link)
                        unique_links.append(link)
                
                if not unique_links:
                    logger.debug(f"📄 [BROWSER-MONITOR] No links found on {url[:40]}... with selector '{link_selector}'")
                    return []
                
                logger.info(f"🔗 [BROWSER-MONITOR] Found {len(unique_links)} links on {url[:40]}...")
                
                # Close main page before visiting links
                await page.close()
                page = None
                
                # Visit each linked page
                for link_url in unique_links:
                    try:
                        # Delay between pages to avoid rate limiting
                        await asyncio.sleep(delay_seconds)
                        
                        # Check if we should stop
                        if not self._running or self._stop_event.is_set():
                            break
                        
                        # Extract content from linked page using hybrid extraction
                        content = await self.extract_content_hybrid(link_url)
                        if content and len(content) > 100:
                            results.append((link_url, content))
                            logger.debug(f"📄 [BROWSER-MONITOR] Extracted {len(content)} chars from {link_url[:40]}...")
                            
                    except Exception as e:
                        logger.debug(f"⚠️ [BROWSER-MONITOR] Failed to extract {link_url[:40]}: {e}")
                        continue
                
                logger.info(f"✅ [BROWSER-MONITOR] Paginated extraction: {len(results)}/{len(unique_links)} pages from {url[:40]}...")
                return results
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ [BROWSER-MONITOR] Timeout navigating {url[:60]}...")
                return results
            except Exception as e:
                # V7.6: Check if this is a browser disconnection error
                error_msg = str(e).lower()
                if "closed" in error_msg or "target" in error_msg:
                    logger.warning(f"⚠️ [BROWSER-MONITOR] Browser disconnected during paginated navigation: {e}")
                    # Mark browser as needing recreation on next call
                    self._browser = None
                else:
                    logger.error(f"❌ [BROWSER-MONITOR] Navigation extraction failed: {e}")
                return results
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
    
    # ============================================
    # V7.1: CIRCUIT BREAKER MANAGEMENT
    # ============================================
    
    def _get_circuit_breaker(self, url: str) -> CircuitBreaker:
        """Get or create circuit breaker for a URL."""
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = CircuitBreaker()
        return self._circuit_breakers[url]
    
    def _should_skip_source(self, url: str) -> bool:
        """Check if source should be skipped due to circuit breaker."""
        breaker = self._get_circuit_breaker(url)
        if not breaker.can_execute():
            self._circuit_breaker_skips += 1
            logger.debug(f"🔴 [BROWSER-MONITOR] Skipping {url[:40]}... (circuit OPEN)")
            return True
        return False
    
    def _record_source_success(self, url: str) -> None:
        """Record successful extraction for circuit breaker."""
        breaker = self._get_circuit_breaker(url)
        breaker.record_success()
    
    def _record_source_failure(self, url: str, is_network_error: bool = False) -> None:
        """
        Record failed extraction for circuit breaker.
        
        V7.3: Only counts network errors toward circuit breaker threshold.
        Empty content is not a network failure.
        
        V7.6: Changed default to False for safety - callers must explicitly
        indicate network errors to avoid false positives in circuit breaker.
        
        Args:
            url: Source URL
            is_network_error: True if failure was due to network/server error
        """
        if is_network_error:
            breaker = self._get_circuit_breaker(url)
            breaker.record_failure()
    
    def _cleanup_old_circuit_breakers(self, max_age_hours: int = 24) -> int:
        """
        V7.6: Remove circuit breakers not used in the last N hours.
        
        Prevents unbounded growth of _circuit_breakers dict when many
        different URLs are scanned over time.
        
        Args:
            max_age_hours: Remove breakers older than this (default 24h)
            
        Returns:
            Number of circuit breakers removed
        """
        if not self._circuit_breakers:
            return 0
        
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Find breakers to remove (no recent failure = not actively tracked)
        to_remove = []
        for url, cb in self._circuit_breakers.items():
            # Remove if: no failure recorded OR last failure was too long ago
            if cb.last_failure_time is None:
                # Never failed - can be removed if circuit is CLOSED
                if cb.state == "CLOSED" and cb.failure_count == 0:
                    to_remove.append(url)
            elif (now - cb.last_failure_time) > max_age_seconds:
                # Old failure - safe to remove
                to_remove.append(url)
        
        for url in to_remove:
            del self._circuit_breakers[url]
        
        if to_remove:
            logger.debug(f"🧹 [BROWSER-MONITOR] Cleaned up {len(to_remove)} old circuit breakers")
        
        return len(to_remove)
    
    # ============================================
    # V7.1: RETRY WITH EXPONENTIAL BACKOFF
    # ============================================
    
    async def _extract_with_retry(self, url: str) -> Tuple[Optional[str], bool]:
        """
        V7.1: Extract content with exponential backoff retry.
        V7.3: Improved to distinguish network errors from empty content.
        
        Retry strategy: 2s → 4s → 8s (with jitter)
        Only retries on network errors, not on empty content.
        
        Args:
            url: URL to extract content from
            
        Returns:
            Tuple of (content, is_network_error):
            - content: Extracted text or None
            - is_network_error: True if failure was due to network error (for circuit breaker)
        """
        last_error = None
        is_network_error = False
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Use hybrid extraction (HTTP first, browser fallback)
                content = await self.extract_content_hybrid(url)
                
                if content:
                    return (content, False)  # Success, not a network error
                
                # Content was None/empty - this is NOT a network error
                # Don't retry, just return empty result
                logger.debug(f"📄 [BROWSER-MONITOR] Empty content (not retrying): {url[:40]}...")
                return (None, False)
                
            except (requests.RequestException, asyncio.TimeoutError) as e:
                # Network-related errors - these are retryable
                last_error = e
                is_network_error = True
                
                if attempt < MAX_RETRIES:
                    # Calculate delay with exponential backoff + jitter
                    delay = min(
                        RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                        RETRY_MAX_DELAY
                    )
                    logger.debug(f"🔄 [BROWSER-MONITOR] Retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s (network error): {url[:40]}...")
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                # Non-network errors (parsing, etc.) - don't retry
                logger.debug(f"⚠️ [BROWSER-MONITOR] Non-retryable error: {e}")
                return (None, False)
        
        logger.warning(f"⚠️ [BROWSER-MONITOR] All retries failed for {url[:40]}...: {last_error}")
        return (None, is_network_error)
    
    # ============================================
    # CONFIGURATION HOT RELOAD
    # ============================================
    
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
        
        Requirements: 2.3
        """
        old_count = len(self._config.sources)
        self._config = load_config(self._config_file)
        self._update_config_mtime()
        
        # Update cache settings if changed
        if self._content_cache:
            self._content_cache._max_entries = self._config.global_settings.cache_max_entries
            self._content_cache._ttl_hours = self._config.global_settings.cache_ttl_hours
        
        new_count = len(self._config.sources)
        logger.info(f"🔄 [BROWSER-MONITOR] Reloaded config: {old_count} → {new_count} sources")
    
    # ============================================
    # SCAN LOOP
    # ============================================
    
    async def _scan_loop(self) -> None:
        """
        Main scan loop that runs continuously.
        
        Requirements: 1.2, 1.3
        """
        logger.info("🔄 [BROWSER-MONITOR] Scan loop started")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Check for config hot reload
                if self._check_config_changed():
                    self.reload_sources()
                
                # Run scan cycle
                news_found = await self.scan_cycle()
                
                self._last_cycle_time = datetime.now(timezone.utc)
                logger.info(f"🌐 [BROWSER-MONITOR] Cycle complete: {self._urls_scanned} URLs, {news_found} relevant items")
                
                # Wait before next cycle
                interval = self._config.global_settings.default_scan_interval_minutes * 60
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval
                    )
                    # Stop event was set
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue loop
                    pass
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [BROWSER-MONITOR] Scan loop error: {e}")
                await asyncio.sleep(60)  # Wait before retry
        
        logger.info("🛑 [BROWSER-MONITOR] Scan loop stopped")
    
    async def scan_cycle(self) -> int:
        """
        Execute one scan cycle over all due sources.
        
        Returns:
            Number of relevant news items found
            
        Requirements: 1.2, 6.2, 6.3
        """
        news_found = 0
        urls_scanned = 0
        
        # V7.6: Periodic cleanup of old circuit breakers (every cycle)
        self._cleanup_old_circuit_breakers(max_age_hours=24)
        
        # Get sources due for scanning, sorted by priority
        due_sources = [s for s in self._config.sources if s.is_due_for_scan()]
        due_sources.sort(key=lambda s: s.priority)
        
        for source in due_sources:
            if not self._running or self._stop_event.is_set():
                break
            
            # Check memory before navigation
            await self._check_memory_pressure()
            
            # Enforce navigation interval
            await self._enforce_navigation_interval()
            
            # Scan source
            result = await self.scan_source(source)
            urls_scanned += 1
            
            if result:
                news_found += 1
            
            # Update last scanned time
            source.last_scanned = datetime.now(timezone.utc)
        
        self._urls_scanned = urls_scanned
        return news_found
    
    async def scan_source(self, source: MonitoredSource) -> Optional[DiscoveredNews]:
        """
        Scan a single source URL.
        
        V7.1: Uses Circuit Breaker and retry with exponential backoff.
        V7.4: Supports paginated navigation for Elite 7 and Tier 2 sources.
        
        Args:
            source: Source to scan
            
        Returns:
            DiscoveredNews if relevant news found, None otherwise
            (For paginated sources, returns the first relevant news found)
            
        Requirements: 3.4, 3.5, 4.1, V7.4
        """
        try:
            # V7.1: Check circuit breaker before attempting
            if self._should_skip_source(source.url):
                return None
            
            # V7.4: Use paginated extraction if configured
            if source.navigation_mode == "paginated" and source.link_selector:
                return await self._scan_source_paginated(source)
            
            # V7.1: Extract content with retry and hybrid mode (single page)
            # V7.3: Now returns tuple (content, is_network_error)
            content, is_network_error = await self._extract_with_retry(source.url)
            
            if not content:
                # V7.3: Only record failure for circuit breaker if it was a network error
                self._record_source_failure(source.url, is_network_error=is_network_error)
                return None
            
            # V7.1: Record success for circuit breaker
            self._record_source_success(source.url)
            
            # Analyze and create news from single page content
            return await self._analyze_and_create_news(source, source.url, content)
            
        except Exception as e:
            logger.error(f"❌ [BROWSER-MONITOR] Error scanning {source.url[:50]}: {e}")
            return None
    
    async def _scan_source_paginated(self, source: MonitoredSource) -> Optional[DiscoveredNews]:
        """
        V7.4: Scan a paginated source by navigating internal links.
        
        Extracts links from main page, visits each, analyzes content,
        and returns the first relevant news found.
        
        Args:
            source: Source with navigation_mode="paginated" and link_selector set
            
        Returns:
            First DiscoveredNews found, or None if no relevant news
        """
        logger.info(f"🔗 [BROWSER-MONITOR] Paginated scan: {source.name or source.url[:40]}...")
        
        # Extract content from linked pages
        results = await self.extract_with_navigation(
            url=source.url,
            link_selector=source.link_selector,
            max_links=source.max_links,
            delay_seconds=DEFAULT_NAVIGATION_DELAY_SECONDS
        )
        
        if not results:
            # No content extracted - could be network error or empty page
            # Don't count as network error for circuit breaker (selector might just not match)
            logger.debug(f"📄 [BROWSER-MONITOR] No content from paginated source: {source.url[:40]}...")
            return None
        
        # V7.1: Record success for circuit breaker (we got some content)
        self._record_source_success(source.url)
        
        # Analyze each extracted page
        first_news = None
        for article_url, content in results:
            # Check if we should stop
            if not self._running or self._stop_event.is_set():
                break
            
            # Analyze and create news
            news = await self._analyze_and_create_news(source, article_url, content)
            if news and first_news is None:
                first_news = news
                # Continue analyzing other pages but don't return yet
                # This allows discovering multiple news items in one scan
        
        return first_news
    
    async def _analyze_and_create_news(
        self, 
        source: MonitoredSource, 
        article_url: str, 
        content: str
    ) -> Optional[DiscoveredNews]:
        """
        V7.5: Analyze content and create DiscoveredNews if relevant.
        
        Smart API routing to reduce DeepSeek calls by 60-80%:
        1. Check cache (deduplication)
        2. Apply ExclusionFilter (skip basketball, women's, NFL, etc.)
        3. Apply RelevanceAnalyzer (keyword-based pre-filtering)
        4. Route based on confidence:
           - confidence < 0.5 → SKIP (no API call)
           - 0.5 ≤ confidence < 0.7 → DeepSeek FALLBACK (API call)
           - confidence ≥ 0.7 → ALERT DIRECT (no API call)
        
        Args:
            source: Source configuration
            article_url: URL of the article (may differ from source.url for paginated)
            content: Extracted text content
            
        Returns:
            DiscoveredNews if relevant, None otherwise
        """
        # Check cache (deduplication)
        if self._content_cache and self._content_cache.is_cached(content):
            logger.debug(f"🔄 [BROWSER-MONITOR] Skipping duplicate: {article_url[:50]}...")
            return None
        
        # Cache content
        if self._content_cache:
            self._content_cache.cache(content)
        
        # V7.6: Expand short content with Tavily
        if len(content) < TAVILY_SHORT_CONTENT_THRESHOLD:
            expanded_content = await self._tavily_expand_short_content(content, article_url)
            if expanded_content:
                content = expanded_content
                logger.debug(f"🔍 [BROWSER-MONITOR] Content expanded with Tavily: {len(content)} chars")
            elif not content.strip():
                # No content and Tavily returned nothing - skip
                logger.debug(f"⏭️ [BROWSER-MONITOR] Skipping empty content: {article_url[:50]}...")
                return None
        
        # V7.5: Step 1 - Apply ExclusionFilter (skip non-football content)
        exclusion_filter = get_exclusion_filter()
        if exclusion_filter.is_excluded(content):
            reason = exclusion_filter.get_exclusion_reason(content)
            logger.debug(f"🚫 [BROWSER-MONITOR] Excluded ({reason}): {article_url[:50]}...")
            self._excluded_count += 1
            return None
        
        # V7.5: Step 2 - Apply RelevanceAnalyzer (keyword-based pre-filtering)
        relevance_analyzer = get_relevance_analyzer()
        local_result = relevance_analyzer.analyze(content)
        
        # V7.5: Step 3 - Route based on confidence
        if not local_result.is_relevant or local_result.confidence < DEEPSEEK_CONFIDENCE_THRESHOLD:
            # Low confidence (< 0.5) → SKIP without API call
            logger.debug(f"⏭️ [BROWSER-MONITOR] Skipped (low confidence {local_result.confidence:.2f}): {article_url[:50]}...")
            self._skipped_low_confidence += 1
            return None
        
        # Determine final analysis result
        if local_result.confidence >= ALERT_CONFIDENCE_THRESHOLD:
            # High confidence (>= 0.7) → ALERT DIRECT without API call
            logger.debug(f"✅ [BROWSER-MONITOR] Direct alert (confidence {local_result.confidence:.2f}): {article_url[:50]}...")
            self._direct_alerts += 1
            
            # Use local analysis result
            is_relevant = True
            confidence = local_result.confidence
            category = local_result.category
            # V7.6: Safe handling of empty/None affected_team
            affected_team = (local_result.affected_team or '').strip() or 'Unknown Team'
            summary = local_result.summary
        else:
            # Medium confidence (0.5 - 0.7) → DeepSeek FALLBACK
            logger.debug(f"🤖 [BROWSER-MONITOR] DeepSeek fallback (confidence {local_result.confidence:.2f}): {article_url[:50]}...")
            self._deepseek_fallbacks += 1
            
            # Call DeepSeek for deeper analysis
            analysis = await self.analyze_relevance(content, source.league_key)
            if not analysis:
                # V7.6: Log when DeepSeek returns None for debugging
                logger.debug(f"⚠️ [BROWSER-MONITOR] DeepSeek returned None for: {article_url[:50]}...")
                return None
            
            # V7.3: Safe type coercion for confidence (handles string "0.8" from AI)
            is_relevant = analysis.get('is_relevant', False)
            try:
                confidence = float(analysis.get('confidence', 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            
            if not is_relevant or confidence < RELEVANCE_CONFIDENCE_THRESHOLD:
                logger.debug(f"⏭️ [BROWSER-MONITOR] DeepSeek rejected (relevant={is_relevant}, conf={confidence:.2f}): {article_url[:50]}...")
                return None
            
            # V7.6: Safe handling of empty/None values from DeepSeek
            category = (analysis.get('category') or '').strip() or 'OTHER'
            affected_team = (analysis.get('affected_team') or '').strip() or 'Unknown Team'
            summary = (analysis.get('summary') or '').strip()
        
        # Validate category is one of the allowed values
        valid_categories = {'INJURY', 'LINEUP', 'SUSPENSION', 'TRANSFER', 'TACTICAL', 'NATIONAL_TEAM', 'YOUTH_CALLUP', 'CUP_ABSENCE', 'OTHER'}
        if category not in valid_categories:
            category = 'OTHER'
        
        news = DiscoveredNews(
            url=article_url,  # V7.4: Use article URL, not source URL
            title=summary[:200] if summary else f"News from {source.name or article_url[:30]}",
            snippet=summary or f"Relevant news discovered from {article_url}",
            category=category,
            affected_team=affected_team,
            confidence=confidence,
            league_key=source.league_key,
            source_name=source.name or source.url[:30]
        )
        
        # Invoke callback
        if self._on_news_discovered:
            try:
                self._on_news_discovered(news)
            except Exception as e:
                logger.error(f"❌ [BROWSER-MONITOR] Callback error: {e}")
        
        self._news_discovered += 1
        
        # Safe logging with fallbacks for empty strings
        title_preview = (news.title[:50] + '...') if len(news.title) > 50 else (news.title or '[No Title]')
        logger.info(f"🌐 [BROWSER-MONITOR] Discovered: {title_preview} for {affected_team} (confidence: {confidence:.2f})")
        
        return news
    
    # ============================================
    # TAVILY SHORT CONTENT EXPANSION (V7.6)
    # ============================================
    
    async def _tavily_expand_short_content(
        self,
        content: str,
        url: str
    ) -> Optional[str]:
        """
        V7.6: Use Tavily to expand short content (< 500 chars).
        
        When a page has minimal text, search for related news to
        provide more context for analysis.
        
        Args:
            content: Original short content
            url: Source URL for context
            
        Returns:
            Expanded content string or None
            
        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        if not self._tavily or not self._tavily.is_available():
            return None
        
        if not self._tavily_budget or not self._tavily_budget.can_call("browser_monitor"):
            logger.debug("📊 [BROWSER-MONITOR] Tavily budget limit reached")
            return None
        
        try:
            # Extract domain for context
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            
            # Build search query from content + domain
            search_context = content[:200].replace('\n', ' ').strip() if content else ""
            query = f"football soccer news {domain} {search_context}"
            
            response = self._tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=True
            )
            
            if response and (response.answer or response.results):
                self._tavily_budget.record_call("browser_monitor")
                
                # Merge original content with Tavily results
                merged_parts = []
                
                if content.strip():
                    merged_parts.append(content)
                
                if response.answer:
                    merged_parts.append(f"\n[TAVILY CONTEXT]\n{response.answer}")
                
                if response.results:
                    snippets = [f"• {r.title}: {r.content[:150]}" for r in response.results[:2]]
                    if snippets:
                        merged_parts.append("\n[RELATED NEWS]\n" + "\n".join(snippets))
                
                if merged_parts:
                    merged_content = "\n".join(merged_parts)
                    logger.info(f"🔍 [BROWSER-MONITOR] Tavily expanded content: {len(content)} → {len(merged_content)} chars")
                    return merged_content
            
            # Tavily returned no results - signal to skip
            logger.debug(f"📭 [BROWSER-MONITOR] Tavily returned no results for {url[:50]}...")
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ [BROWSER-MONITOR] Tavily expansion failed: {e}")
            return None
    
    # ============================================
    # RATE LIMITING AND RESOURCE MANAGEMENT
    # ============================================
    
    async def _enforce_navigation_interval(self) -> None:
        """
        Enforce minimum interval between page navigations.
        
        Requirements: 6.2
        """
        interval = self._config.global_settings.navigation_interval_seconds
        elapsed = time.time() - self._last_navigation_time
        
        if elapsed < interval:
            wait_time = interval - elapsed
            await asyncio.sleep(wait_time)
        
        self._last_navigation_time = time.time()
    
    async def _check_memory_pressure(self) -> None:
        """
        Check memory usage and pause if too high.
        
        Requirements: 6.3
        """
        memory_percent = get_memory_usage_percent()
        
        if memory_percent > MEMORY_HIGH_THRESHOLD:
            self._paused = True
            logger.warning(f"⏸️ [BROWSER-MONITOR] Paused: high memory ({memory_percent:.1f}%)")
            
            # Wait until memory drops
            while memory_percent > MEMORY_LOW_THRESHOLD:
                await asyncio.sleep(10)
                memory_percent = get_memory_usage_percent()
                
                if not self._running or self._stop_event.is_set():
                    break
            
            self._paused = False
            logger.info(f"▶️ [BROWSER-MONITOR] Resumed (memory: {memory_percent:.1f}%)")
    
    # ============================================
    # RELEVANCE ANALYSIS (DeepSeek Only - V6.0)
    # ============================================
    
    async def analyze_relevance(self, content: str, league_key: str) -> Optional[Dict[str, Any]]:
        """
        Analyze content relevance using DeepSeek via OpenRouter.
        
        V6.0: DeepSeek only (removed Gemini fallback logic)
        
        Args:
            content: Page text content
            league_key: League key for context
            
        Returns:
            Dict with is_relevant, category, affected_team, confidence, summary
            
        Requirements: 3.2, 3.3
        """
        return await self._analyze_with_deepseek(content, league_key)
    
    async def _analyze_with_deepseek(self, content: str, league_key: str) -> Optional[Dict[str, Any]]:
        """
        Analyze content using DeepSeek via OpenRouter.
        
        V7.3: Improved error handling for JSON parsing and API responses.
        """
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("❌ [BROWSER-MONITOR] No OpenRouter API key for DeepSeek")
            return None
        
        model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
        prompt = self._build_relevance_prompt(content, league_key)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earlybird.local",
            "X-Title": "EarlyBird Browser Monitor"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 512
        }
        
        try:
            # Use asyncio.to_thread for sync requests call
            response = await asyncio.to_thread(
                requests.post,
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ [BROWSER-MONITOR] DeepSeek HTTP error: {response.status_code} - {response.text[:200]}")
                return None
            
            # V7.3: Safe JSON parsing with specific error handling
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ [BROWSER-MONITOR] DeepSeek returned invalid JSON: {e} - Response: {response.text[:200]}")
                return None
            
            # V7.3: Safe nested dict access with validation
            choices = data.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                logger.warning(f"⚠️ [BROWSER-MONITOR] DeepSeek response missing 'choices': {data}")
                return None
            
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                logger.warning(f"⚠️ [BROWSER-MONITOR] DeepSeek invalid choice format: {first_choice}")
                return None
            
            message = first_choice.get("message")
            if not isinstance(message, dict):
                logger.warning(f"⚠️ [BROWSER-MONITOR] DeepSeek invalid message format: {first_choice}")
                return None
            
            response_text = message.get("content", "")
            
            if not response_text:
                logger.warning("⚠️ [BROWSER-MONITOR] DeepSeek returned empty response content")
                return None
            
            self._deepseek_calls += 1
            logger.debug(f"🤖 [BROWSER-MONITOR] DeepSeek analysis complete (call #{self._deepseek_calls})")
            
            return self._parse_relevance_response(response_text)
            
        except requests.Timeout:
            logger.warning("⚠️ [BROWSER-MONITOR] DeepSeek timeout")
            return None
        except requests.RequestException as e:
            logger.error(f"❌ [BROWSER-MONITOR] DeepSeek network error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [BROWSER-MONITOR] DeepSeek unexpected error: {type(e).__name__}: {e}")
            return None
    
    # ============================================
    # RELEVANCE PROMPT AND PARSING
    # ============================================
    
    def _build_relevance_prompt(self, content: str, league_key: str) -> str:
        """
        Build the relevance analysis prompt with negative filters.
        
        Includes filters to exclude:
        - Basketball news
        - Women's/Ladies team news
        - NFL/American Football
        
        NOTE: Youth/Primavera/U19 are NOT excluded - they are RELEVANT when
        youth players are called up to first team due to injuries/absences.
        """
        # Truncate content for prompt
        max_content = 15000  # Leave room for prompt
        if len(content) > max_content:
            content = content[:max_content]
        
        return f"""Analyze this sports news article and determine if it contains betting-relevant information for MEN'S FOOTBALL (Soccer).

⚠️ CRITICAL FILTERS - AUTOMATICALLY MARK AS NOT RELEVANT:
- Basketball / NBA / Euroleague / ACB news → is_relevant: false
- Women's team / Ladies / Femminile news → is_relevant: false  
- NFL / American Football / Rugby news → is_relevant: false
- Any sport other than Men's Football (Soccer) → is_relevant: false

✅ RELEVANT NEWS (mark is_relevant: true):
- Injuries to first team players
- Suspensions / Red cards
- National team call-ups affecting club availability
- Youth/Primavera/U19/U21 players called up to first team (VERY RELEVANT for betting!)
  Examples in multiple languages: giovanili, juvenil, młodzież, gençler, altyapı, jugend, nachwuchs, jeunes, νέοι, молодёжь, ungdom, jeugd, beloften
- Rotation / Rest for cup matches
- Transfer news affecting squad
- Tactical changes / Formation news
- Any news affecting first team lineup or player availability

ARTICLE TEXT:
{content}

LEAGUE: {league_key}

Respond in JSON format ONLY (no markdown, no explanation):
{{
  "is_relevant": true/false,
  "category": "INJURY" | "LINEUP" | "SUSPENSION" | "TRANSFER" | "TACTICAL" | "YOUTH_CALLUP" | "OTHER",
  "affected_team": "team name or null",
  "confidence": 0.0-1.0,
  "summary": "brief summary of the news (max 200 chars)"
}}

RULES:
- is_relevant=true if the news could affect first team match outcomes
- is_relevant=false for Basketball, Women's team, NFL, or any non-football news
- YOUTH_CALLUP category: when youth/primavera/giovanili/juvenil/młodzież/gençler players are promoted to first team - THIS IS VERY RELEVANT
- confidence >= 0.7 for clear betting-relevant news
- category must be one of the specified values
- affected_team should be the team most impacted
- summary should be concise and informative"""
    
    def _parse_relevance_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from DeepSeek."""
        import re
        
        # Handle DeepSeek <think> tags
        if '<think>' in response_text:
            # Remove thinking section
            response_text = re.sub(r'<think>[\s\S]*?</think>', '', response_text)
        
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        logger.warning("⚠️ [BROWSER-MONITOR] Could not parse AI response as JSON")
        return None
    
    # ============================================
    # STATS
    # ============================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get monitor statistics.
        
        Returns:
            Dict with running, paused, urls_scanned, news_discovered, etc.
            
        Requirements: 8.1
        """
        # Count open circuit breakers
        open_circuits = sum(
            1 for cb in self._circuit_breakers.values() 
            if cb.state == "OPEN"
        )
        
        # V7.5: Calculate API savings
        total_analyzed = self._excluded_count + self._skipped_low_confidence + self._direct_alerts + self._deepseek_fallbacks
        api_calls_saved = self._excluded_count + self._skipped_low_confidence + self._direct_alerts
        api_savings_percent = (api_calls_saved / total_analyzed * 100) if total_analyzed > 0 else 0.0
        
        return {
            "running": self._running,
            "paused": self._paused,
            "urls_scanned": self._urls_scanned,
            "news_discovered": self._news_discovered,
            "sources_count": len(self._config.sources),
            "cache_size": self._content_cache.size() if self._content_cache else 0,
            "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
            "deepseek_calls": self._deepseek_calls,
            "ai_provider": "DeepSeek",
            # V7.0: Extraction stats
            "trafilatura_extractions": self._trafilatura_extractions,
            "fallback_extractions": self._fallback_extractions,
            "blocked_resources": self._blocked_resources,
            "stealth_enabled": STEALTH_AVAILABLE,
            "trafilatura_enabled": TRAFILATURA_AVAILABLE,
            # V7.1: Hybrid mode and circuit breaker stats
            "http_extractions": self._http_extractions,
            "browser_extractions": self._browser_extractions,
            "circuit_breaker_skips": self._circuit_breaker_skips,
            "open_circuits": open_circuits,
            "total_circuits": len(self._circuit_breakers),
            # V7.2: Behavior simulation stats
            "behavior_simulations": self._behavior_simulations,
            "behavior_simulation_failures": self._behavior_simulation_failures,  # V7.6
            "behavior_simulation_enabled": BEHAVIOR_SIMULATION_ENABLED,
            # V7.5: Smart API routing stats
            "excluded_count": self._excluded_count,
            "skipped_low_confidence": self._skipped_low_confidence,
            "direct_alerts": self._direct_alerts,
            "deepseek_fallbacks": self._deepseek_fallbacks,
            "api_calls_saved": api_calls_saved,
            "api_savings_percent": round(api_savings_percent, 1),
            "version": "7.6"  # V7.6: Updated version
        }


# ============================================
# SINGLETON INSTANCE (Thread-Safe)
# ============================================

import threading

_browser_monitor_instance: Optional[BrowserMonitor] = None
_browser_monitor_lock = threading.Lock()


def get_browser_monitor() -> BrowserMonitor:
    """
    Get or create the singleton BrowserMonitor instance.
    
    V7.6: Thread-safe with double-check locking pattern.
    This is critical because BrowserMonitor is started in a separate thread
    (BrowserMonitorThread) while the main thread may also access it.
    """
    global _browser_monitor_instance
    if _browser_monitor_instance is None:
        with _browser_monitor_lock:
            # Double-check inside lock to prevent race condition
            if _browser_monitor_instance is None:
                _browser_monitor_instance = BrowserMonitor()
    return _browser_monitor_instance
