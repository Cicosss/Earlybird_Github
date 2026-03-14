# COVE DOUBLE VERIFICATION REPORT: NitterFallbackScraper
## VPS Deployment & Data Flow Analysis

**Date:** 2026-03-10
**Component:** NitterFallbackScraper
**Methods Verified:**
- [`close()`](src/services/nitter_fallback_scraper.py:547-561)
- [`get_stats()`](src/services/nitter_fallback_scraper.py:1382-1414)
- [`health_check()`](src/services/nitter_fallback_scraper.py:858-971)
- [`run_cycle(continent: str | None)`](src/services/nitter_fallback_scraper.py:1420-1539)
- [`scrape_accounts(handles: list[str], max_posts_per_account: int)`](src/services/nitter_fallback_scraper.py:1301-1380)

---

## EXECUTIVE SUMMARY

**Overall Assessment:** ⚠️ **MODERATE RISK - 3 CRITICAL ISSUES FOUND**

The NitterFallbackScraper component has solid integration with the bot's data flow but contains **3 critical thread safety issues** that could cause crashes or data corruption on VPS deployment. All other aspects (method signatures, error handling, dependencies, data flow) are correctly implemented.

### Critical Issues (Must Fix for VPS):
1. **Race condition in `_nitter_intel_cache`** - Module-level dict accessed without locks
2. **Race condition in `_ensure_browser()`** - Browser initialization not thread-safe
3. **Race condition in `NitterCache`** - Cache operations not thread-safe

### Non-Critical Issues (Should Fix):
4. **Playwright browser binaries not in requirements.txt** - Requires manual `playwright install` command
5. **Fallback keyword gate less comprehensive** - When intelligence_gate unavailable, filtering is weaker

---

## DETAILED FINDINGS

### 1. Method Signatures and Return Types ✅ CORRECT

#### [`close()`](src/services/nitter_fallback_scraper.py:547-561)
- **Status:** ✅ CORRECT
- **Finding:** Method properly closes Playwright browser and playwright instances with exception handling
- **VPS Impact:** None - Graceful error handling prevents resource leaks

#### [`get_stats()`](src/services/nitter_fallback_scraper.py:1382-1414)
- **Status:** ✅ CORRECT
- **Finding:** Returns comprehensive statistics including:
  - Total scraped tweets
  - Cache hits
  - Instance switches
  - Instance health details (healthy status, failures, success rate, timestamps)
- **VPS Impact:** None - Thread-safe read operations only

#### [`health_check()`](src/services/nitter_fallback_scraper.py:858-971)
- **Status:** ✅ CORRECT
- **Finding:** Async method properly tests all Nitter instances:
  - Detects Cloudflare challenges/captchas
  - Verifies tweet containers are present
  - Checks for valid Nitter page content
  - Uses stealth mode for anti-bot detection
- **VPS Impact:** None - Properly handles browser initialization failures

#### [`scrape_accounts()`](src/services/nitter_fallback_scraper.py:1301-1380)
- **Status:** ✅ CORRECT
- **Finding:** Main entry point correctly:
  - Validates handles (returns None if empty)
  - Scrapes accounts with retry logic
  - Applies Layer 1 (keyword gate) and Layer 2 (AI translation) filtering
  - Caches results
  - Returns data in DeepSeek format
- **VPS Impact:** None - Proper None handling for edge cases

#### [`run_cycle(continent: str | None)`](src/services/nitter_fallback_scraper.py:1420-1539)
- **Status:** ✅ CORRECT
- **Finding:** Async method properly:
  - Fetches handles from Supabase (social_sources table)
  - Scrapes tweets via NitterPool
  - Filters via TweetRelevanceFilter
  - Links relevant tweets to upcoming matches
  - Triggers analysis if 90% confident
- **VPS Impact:** ⚠️ **CRITICAL** - Race condition in `_nitter_intel_cache` (see Issue #1 below)

---

### 2. Thread Safety and VPS Deployment

#### InstanceHealth Modifications ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** All InstanceHealth modifications are properly protected with locks:
  - Line 497: `self._health_lock = threading.Lock()` defined
  - Line 791: `with self._health_lock:` in [`_mark_instance_success()`](src/services/nitter_fallback_scraper.py:785)
  - Line 816: `with self._health_lock:` in [`_mark_instance_failure()`](src/services/nitter_fallback_scraper.py:803)
  - Line 1843: `_nitter_scraper_instance_init_lock = threading.Lock()` for singleton
- **VPS Impact:** None - Thread-safe operations

#### ⚠️ CRITICAL ISSUE #1: Race Condition in `_nitter_intel_cache`
- **Status:** ❌ **CRITICAL**
- **Location:** Lines 1797, 1777, 1800
- **Problem:** Module-level dict `_nitter_intel_cache` is accessed without locks
  - Line 1797: `_nitter_intel_cache: dict[str, dict[str, Any]] = {}` (no lock)
  - Line 1777: `_nitter_intel_cache[match_id] = {...}` (write without lock)
  - Line 1800: `return _nitter_intel_cache.get(match_id)` (read without lock)
- **VPS Impact:** **HIGH** - Multiple concurrent calls to [`run_cycle()`](src/services/nitter_fallback_scraper.py:1420) could cause:
  - Race conditions when writing to shared cache
  - Data corruption
  - Lost intel updates
  - Potential crashes from concurrent dict modifications
- **Fix Required:** Add threading.Lock for `_nitter_intel_cache` operations

#### ⚠️ CRITICAL ISSUE #2: Race Condition in `_ensure_browser()`
- **Status:** ❌ **CRITICAL**
- **Location:** Lines 521-545
- **Problem:** Browser initialization uses double-checked locking pattern WITHOUT a lock
  ```python
  async def _ensure_browser(self) -> bool:
      if self._browser and self._browser.is_connected():
          return True
      try:
          if not self._playwright:
              self._playwright = await async_playwright().start()  # NO LOCK!
          if not self._browser:
              self._browser = await self._playwright.chromium.launch(...)  # NO LOCK!
  ```
- **VPS Impact:** **HIGH** - Two async tasks calling [`_ensure_browser()`](src/services/nitter_fallback_scraper.py:521) concurrently could:
  - Both initialize playwright/browser
  - Cause resource leaks (multiple browser instances)
  - Cause crashes from concurrent browser operations
- **Fix Required:** Add asyncio.Lock for browser initialization

---

### 3. Data Flow and Integration

#### Continent Parameter Handling ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** [`_get_handles_from_supabase()`](src/services/nitter_fallback_scraper.py:1541) properly handles continent:
  - Line 1559-1570: If continent provided, calls [`get_active_leagues_for_continent()`](src/database/supabase_provider.py:1155) then [`get_social_sources_for_league()`](src/database/supabase_provider.py:1251)
  - Line 1569-1570: If continent is None, calls [`get_social_sources()`](src/database/supabase_provider.py:1241)
  - All methods exist in SupabaseProvider
- **VPS Impact:** None - Proper integration

#### Intel Cache Integration ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** [`get_nitter_intel_for_match()`](src/services/nitter_fallback_scraper.py:1800) is properly integrated with main.py:
  - Called in main.py at lines 1462, 1534, 2144
  - Stores intel with match_id as key (line 1777)
  - Retrieves intel for specific match (line 1800)
  - Cache cleared at start of each cycle (line 1452)
- **VPS Impact:** ⚠️ **CRITICAL** - Race condition in cache access (see Issue #1)

#### Database Queries ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** [`_link_and_trigger_matches()`](src/services/nitter_fallback_scraper.py:1605) properly handles database:
  - Line 1639: Uses `with get_db_session() as db_session:`
  - Line 1640-1648: Queries for upcoming matches
  - [`get_db_session()`](src/database/models.py:657) handles lock errors with retry logic (lines 686-692)
- **VPS Impact:** None - Database lock errors properly handled with exponential backoff

---

### 4. Error Handling and VPS Resilience

#### [`close()`] Error Handling ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** Method properly handles all error cases:
  - Line 549-553: Closes browser with exception handling
  - Line 556-560: Closes playwright with exception handling
  - Both check for None before closing
- **VPS Impact:** None - Graceful error handling prevents resource leaks

#### [`health_check()`] Browser Initialization Failure Handling ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** Method properly handles browser initialization failures:
  - Line 871-872: If browser init fails, returns all False
  - Line 876-964: For each instance, creates new page and closes it in try-finally
  - Line 958: `await page.close()` is in finally block
- **VPS Impact:** None - Resources properly cleaned up even if browser init fails mid-way

#### Timeout Configuration ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** Timeouts are appropriate for VPS deployment:
  - Line 124: `PAGE_TIMEOUT_SECONDS = 30`
  - Line 639: `timeout=30` for OpenRouter API call
  - Line 886: `await page.goto(url, timeout=PAGE_TIMEOUT_SECONDS * 1000)` = 30 seconds
- **VPS Impact:** None - 30 seconds is reasonable for most network conditions

---

### 5. Dependencies and Auto-Installation

#### ⚠️ ISSUE #4: Playwright Browser Binaries Not in requirements.txt
- **Status:** ❌ **MISSING**
- **Location:** requirements.txt
- **Problem:** requirements.txt only includes Playwright Python package, NOT actual browser binaries:
  - Line 48: `playwright==1.58.0` ✅
  - Line 49: `playwright-stealth==2.0.1` ✅
  - **MISSING:** chromium, firefox, webkit browser binaries
- **VPS Impact:** **MEDIUM** - On VPS deployment:
  - `pip install -r requirements.txt` will NOT install browser binaries
  - Bot will crash with "Executable doesn't exist" error
  - Requires manual `playwright install` command after pip install
- **Fix Required:** Add post-install script or documentation for `playwright install` command

#### Environment Variables ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** All environment variables are documented in .env.template:
  - Line 116: `NITTER_MAX_RETRIES=3`
  - Line 117: `MAX_NITTER_RECOVERY_ACCOUNTS=10`
  - Line 24: `OPENROUTER_API_KEY=your_openrouter_key_here`
- **VPS Impact:** None - All variables properly documented

---

### 6. Intelligence Gate Integration

#### ⚠️ ISSUE #5: Fallback Keyword Gate Less Comprehensive
- **Status:** ❌ **INCONSISTENT**
- **Location:** Lines 1037-1041
- **Problem:** When `_INTELLIGENCE_GATE_AVAILABLE` is False, fallback `passes_native_gate()` is NOT equivalent to `level_1_keyword_check()`:
  - **Intelligence Gate version** ([`level_1_keyword_check()`](src/utils/intelligence_gate.py:276)):
    - Checks `ALL_KEYWORDS` = `ALL_INJURY_KEYWORDS + ALL_TEAM_KEYWORDS`
    - Covers 9 languages (english, spanish, arabic, french, german, portuguese, polish, turkish, russian, dutch)
    - ~100+ keywords
  - **Fallback version** ([`passes_native_gate()`](src/services/nitter_fallback_scraper.py:256)):
    - Checks `ALL_NATIVE_KEYWORDS` from `NATIVE_KEYWORDS` dict
    - Covers only 3 languages (spanish, arabic, french)
    - ~30 keywords
- **VPS Impact:** **LOW** - When intelligence_gate module is unavailable:
  - Filtering is less comprehensive (3 languages vs 9)
  - May miss relevant tweets in other languages
  - Reduces effectiveness of Nitter fallback
- **Fix Required:** Either:
  1. Make intelligence_gate a hard dependency (remove fallback)
  2. Update `passes_native_gate()` to use same keywords as `level_1_keyword_check()`

#### Layer 2 AI Failure Handling ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** Downstream code properly handles None values:
  - Lines 718-719, 738-739: Sets `translation = None` and `is_betting_relevant = None` when AI fails
  - Lines 1349-1350: Includes these fields in output dict
  - These fields are informational only, not used by other components
- **VPS Impact:** None - None values handled gracefully

---

### 7. Cache and Performance

#### ⚠️ CRITICAL ISSUE #3: Race Condition in NitterCache
- **Status:** ❌ **CRITICAL**
- **Location:** Lines 390-466
- **Problem:** [`NitterCache`](src/services/nitter_fallback_scraper.py:390) class has NO thread safety:
  - Line 401: `self._cache: dict[str, dict] = {}` (shared dict, no lock)
  - Line 449-456: [`set()`](src/services/nitter_fallback_scraper.py:449) modifies cache and calls [`_save_cache()`](src/services/nitter_fallback_scraper.py:431)
  - Line 441-447: [`get()`](src/services/nitter_fallback_scraper.py:441) reads from cache
  - Line 431-439: [`_save_cache()`](src/services/nitter_fallback_scraper.py:431) writes to file without any locking
- **VPS Impact:** **HIGH** - Multiple threads calling [`scrape_accounts()`](src/services/nitter_fallback_scraper.py:1301) concurrently could:
  - Corrupt cache dict (concurrent modifications)
  - Corrupt cache file (concurrent writes)
  - Lose cached data
  - Cause JSON parsing errors
- **Fix Required:** Add threading.Lock for all cache operations

#### Cache Expiration ✅ CORRECT
- **Status:** ✅ CORRECT
- **Finding:** [`_is_valid_entry()`](src/services/nitter_fallback_scraper.py:421) properly handles timezone:
  - Line 426: `cached_at = datetime.fromisoformat(entry["cached_at"].replace("Z", "+00:00"))`
  - Line 427: `return (now - cached_at) < timedelta(hours=self._ttl_hours)`
  - Line 415: `now = datetime.now(timezone.utc)`
- **VPS Impact:** None - Both cached_at and now use UTC timezone, clock drift not an issue

---

## CRITICAL FIXES REQUIRED FOR VPS DEPLOYMENT

### Fix #1: Add Thread Safety to `_nitter_intel_cache`

**File:** [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py:1797)

**Current Code:**
```python
# Cache for storing Nitter intel that main.py can access
# Format: {match_id: {"handle": str, "intel": str, "timestamp": datetime}}
_nitter_intel_cache: dict[str, dict[str, Any]] = {}
```

**Fixed Code:**
```python
# Cache for storing Nitter intel that main.py can access
# Format: {match_id: {"handle": str, "intel": str, "timestamp": datetime}}
_nitter_intel_cache: dict[str, dict[str, Any]] = {}
_nitter_intel_cache_lock = threading.Lock()  # ADD THIS LINE
```

**Then update [`_trigger_analysis()`](src/services/nitter_fallback_scraper.py:1745):**
```python
async def _trigger_analysis(self, match: Any, handle: str, tweet_text: str) -> None:
    try:
        # ... existing code ...
        
        # V10.5 FIX: Store intel in shared cache for main.py to access
        with _nitter_intel_cache_lock:  # ADD THIS LINE
            _nitter_intel_cache[match_id] = {
                "handle": handle,
                "intel": forced_narrative,
                "timestamp": datetime.now(timezone.utc),
            }
        
        logger.info(
            f"✅ [NITTER-CYCLE] Intel cached for match {match_id}: {forced_narrative[:100]}..."
        )
    except Exception as e:
        logger.error(f"❌ [NITTER-CYCLE] Error triggering analysis: {e}")
```

**Then update [`get_nitter_intel_for_match()`](src/services/nitter_fallback_scraper.py:1800):**
```python
def get_nitter_intel_for_match(match_id: str) -> dict[str, Any] | None:
    """
    Get cached Nitter intel for a specific match.

    This allows main.py to access insider intel gathered by Nitter cycle.

    Args:
        match_id: Match ID from database

    Returns:
        Dict with 'handle', 'intel', 'timestamp' keys, or None if no intel exists
    """
    with _nitter_intel_cache_lock:  # ADD THIS LINE
        return _nitter_intel_cache.get(match_id)
```

**Then update [`clear_nitter_intel_cache()`](src/services/nitter_fallback_scraper.py:1815):**
```python
def clear_nitter_intel_cache() -> None:
    """
    Clear expired Nitter intel cache entries.

    Removes entries older than 24 hours to prevent stale intel.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    expired_keys = []

    with _nitter_intel_cache_lock:  # ADD THIS LINE
        for match_id, intel_data in _nitter_intel_cache.items():
            intel_time = intel_data.get("timestamp")
            if intel_time and (now - intel_time).total_seconds() > 86400:  # 24 hours
                expired_keys.append(match_id)

        for key in expired_keys:
            del _nitter_intel_cache[key]

    if expired_keys:
        logger.debug(f"🗑️ [NITTER-CACHE] Cleared {len(expired_keys)} expired entries")
```

---

### Fix #2: Add Thread Safety to `_ensure_browser()`

**File:** [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py:489)

**Current Code:**
```python
def __init__(self):
    """Initialize the scraper."""
    self._instances = list(NITTER_INSTANCES)
    self._fallback_instances = list(NITTER_FALLBACK_INSTANCES)
    self._instance_index = 0
    self._instance_health: dict[str, InstanceHealth] = {}

    # Thread safety: Add lock for protecting InstanceHealth modifications
    self._health_lock = threading.Lock()

    # Initialize health tracking
    for url in self._instances + self._fallback_instances:
        self._instance_health[url] = InstanceHealth(url=url)

    # Cache
    self._cache = NitterCache()

    # Filters
    self._exclusion_filter = get_exclusion_filter()
    self._relevance_analyzer = get_relevance_analyzer()

    # Playwright resources (lazy init)
    self._playwright = None
    self._browser = None
```

**Fixed Code:**
```python
def __init__(self):
    """Initialize the scraper."""
    self._instances = list(NITTER_INSTANCES)
    self._fallback_instances = list(NITTER_FALLBACK_INSTANCES)
    self._instance_index = 0
    self._instance_health: dict[str, InstanceHealth] = {}

    # Thread safety: Add lock for protecting InstanceHealth modifications
    self._health_lock = threading.Lock()

    # Initialize health tracking
    for url in self._instances + self._fallback_instances:
        self._instance_health[url] = InstanceHealth(url=url)

    # Cache
    self._cache = NitterCache()

    # Filters
    self._exclusion_filter = get_exclusion_filter()
    self._relevance_analyzer = get_relevance_analyzer()

    # Playwright resources (lazy init)
    self._playwright = None
    self._browser = None
    
    # ADD THIS: Lock for thread-safe browser initialization
    self._browser_lock = asyncio.Lock()
```

**Then update [`_ensure_browser()`](src/services/nitter_fallback_scraper.py:521):**
```python
async def _ensure_browser(self) -> bool:
    """Ensure Playwright browser is initialized."""
    if self._browser and self._browser.is_connected():
        return True

    async with self._browser_lock:  # ADD THIS LINE
        # Double-check after acquiring lock
        if self._browser and self._browser.is_connected():
            return True
        
        try:
            from playwright.async_api import async_playwright

            if not self._playwright:
                self._playwright = await async_playwright().start()

            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-extensions",
                ],
            )
            logger.info("✅ [NITTER-FALLBACK] Browser initialized")
            return True
        except Exception as e:
            logger.error(f"❌ [NITTER-FALLBACK] Failed to init browser: {e}")
            return False
```

---

### Fix #3: Add Thread Safety to NitterCache

**File:** [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py:390)

**Current Code:**
```python
class NitterCache:
    """
    Persistent cache for scraped tweets.

    Saves to JSON file to avoid re-scraping same content.
    Implements TTL-based expiration.
    """

    def __init__(self, cache_file: str = CACHE_FILE, ttl_hours: int = CACHE_TTL_HOURS):
        self._cache_file = Path(cache_file)
        self._ttl_hours = ttl_hours
        self._cache: dict[str, dict] = {}
        self._load_cache()
```

**Fixed Code:**
```python
class NitterCache:
    """
    Persistent cache for scraped tweets.

    Saves to JSON file to avoid re-scraping same content.
    Implements TTL-based expiration.
    """

    def __init__(self, cache_file: str = CACHE_FILE, ttl_hours: int = CACHE_TTL_HOURS):
        self._cache_file = Path(cache_file)
        self._ttl_hours = ttl_hours
        self._cache: dict[str, dict] = {}
        self._cache_lock = threading.Lock()  # ADD THIS LINE
        self._load_cache()
```

**Then update [`get()`](src/services/nitter_fallback_scraper.py:441):**
```python
def get(self, handle: str) -> list[dict] | None:
    """Get cached tweets for a handle."""
    with self._cache_lock:  # ADD THIS LINE
        handle_key = handle.lower().replace("@", "")
        entry = self._cache.get(handle_key)
        if entry and self._is_valid_entry(entry, datetime.now(timezone.utc)):
            return entry.get("tweets", [])
    return None
```

**Then update [`set()`](src/services/nitter_fallback_scraper.py:449):**
```python
def set(self, handle: str, tweets: list[dict]) -> None:
    """Cache tweets for a handle."""
    with self._cache_lock:  # ADD THIS LINE
        handle_key = handle.lower().replace("@", "")
        self._cache[handle_key] = {
            "tweets": tweets,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_cache()  # This is already inside the lock
```

**Then update [`clear_expired()`](src/services/nitter_fallback_scraper.py:458):**
```python
def clear_expired(self) -> int:
    """Remove expired entries. Returns count removed."""
    with self._cache_lock:  # ADD THIS LINE
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._cache.items() if not self._is_valid_entry(v, now)]
        for k in expired:
            del self._cache[k]
        if expired:
            self._save_cache()  # This is already inside the lock
        return len(expired)
```

**Then update [`_load_cache()`](src/services/nitter_fallback_scraper.py:404):**
```python
def _load_cache(self) -> None:
    """Load cache from file."""
    if not self._cache_file.exists():
        with self._cache_lock:  # ADD THIS LINE
            self._cache = {}
        return

    try:
        with open(self._cache_file, encoding="utf-8") as f:
            data = json.load(f)
            # Filter expired entries
            now = datetime.now(timezone.utc)
            with self._cache_lock:  # ADD THIS LINE
                self._cache = {k: v for k, v in data.items() if self._is_valid_entry(v, now)}
        logger.debug(f"🐦 [NITTER-CACHE] Loaded {len(self._cache)} entries")
    except Exception as e:
        logger.warning(f"⚠️ [NITTER-CACHE] Failed to load cache: {e}")
        with self._cache_lock:  # ADD THIS LINE
            self._cache = {}
```

---

### Fix #4: Add Playwright Browser Binaries Installation

**Option A: Add to requirements.txt**
```txt
# Add these lines to requirements.txt:

# Playwright Browsers (V12.5 - Required for VPS deployment)
# Note: These are NOT installed by pip, require separate installation
# Run: playwright install chromium
# Or add to setup script
```

**Option B: Create setup script**
Create file `scripts/install_playwright_browsers.sh`:
```bash
#!/bin/bash
# Install Playwright browser binaries for VPS deployment

echo "📦 Installing Playwright browser binaries..."
playwright install chromium

echo "✅ Playwright browser binaries installed successfully"
```

**Option C: Update .env.template documentation**
Add to `.env.template`:
```bash
# ============================================
# PLAYWRIGHT BROWSER INSTALLATION (V12.5)
# ============================================
# After running: pip install -r requirements.txt
# You must also run: playwright install chromium
# This installs the actual browser binaries required by Playwright
```

---

### Fix #5: Make Intelligence Gate a Hard Dependency or Update Fallback

**Option A: Make intelligence_gate a hard dependency (RECOMMENDED)**
Remove fallback logic from [`_extract_tweets_from_html()`](src/services/nitter_fallback_scraper.py:997):
```python
def _extract_tweets_from_html(self, html: str, handle: str) -> list[ScrapedTweet]:
    """
    Extract tweets from Nitter HTML with V10.0 three-layer filtering.

    V10.0 Layer 1: Zero-cost keyword check (via intelligence_gate module)
    V10.0 Layer 2: AI translation and classification (via intelligence_gate module)
    V10.0 Layer 3: R1 reasoning (handled separately in Task 2)

    Args:
        html: Page HTML content
        handle: Twitter handle being scraped

    Returns:
        List of extracted tweets with Layer 2 analysis results
    """
    if not BS4_AVAILABLE or not html:
        return []

    tweets = []
    soup = BeautifulSoup(html, "html.parser")

    # Nitter tweet selectors (may vary by instance)
    tweet_containers = soup.select(".timeline-item, .tweet-body, .main-tweet")

    for container in tweet_containers[:MAX_TWEETS_PER_ACCOUNT]:
        try:
            # Extract content
            content_elem = container.select_one(".tweet-content, .tweet-text, .content")
            if not content_elem:
                continue

            content = content_elem.get_text(strip=True)
            if not content or len(content) < 10:
                continue

            # Apply exclusion filter
            if self._exclusion_filter.is_excluded(content):
                continue

            # V10.0 Layer 1: Zero-cost keyword check (via intelligence_gate module)
            # REMOVE FALLBACK - Make intelligence_gate a hard dependency
            passes_gate, triggered_keyword = level_1_keyword_check(content)

            if not passes_gate:
                logger.info(
                    f"🚪 [INTEL-GATE-L1] DISCARDED - No native keywords found in tweet from {handle}"
                )
                continue  # Skip tweet - gate discarded it

            logger.info(
                f"🚪 [INTEL-GATE-L1] PASSED - Keyword '{triggered_keyword}' found in tweet from {handle}"
            )

            # ... rest of method ...
```

**Option B: Update fallback to use same keywords**
Update [`NATIVE_KEYWORDS`](src/services/nitter_fallback_scraper.py:178) to match intelligence_gate:
```python
# V9.5: NATIVE KEYWORD GATE (Layer 1 - Zero Cost)

# Native language keywords for pre-AI filtering
# These are betting-relevant terms in non-English/Italian languages
# UPDATED: Now matches intelligence_gate.py keywords for consistency
NATIVE_KEYWORDS = {
    "spanish": [
        "lesión",  # injury
        "bajas",  # absences/misses
        "reserva",  # reserve/bench
        "equipo alternativo",  # alternative team/bench
        "sueldos",  # salaries (contract news)
        "huelga",  # strike
        "convocatoria",  # call-up/squad announcement
        "lesionado",  # injured
        "descartado",  # ruled out
        "duda",  # doubtful
        "alineación",  # lineup
        "once titular",  # starting eleven
        "banquillo",  # bench
    ],
    "arabic": [
        "إصابة",  # injury
        "تشكيلة",  # lineup/formation
        "بدلاء",  # substitutes/bench
        "أزمة",  # crisis
        "إضراب",  # strike
        "مصاب",  # injured
        "غياب",  # absence
        "الاحتياط",  # reserve/bench
        "الفريق الأساسي",  # starting team
        "المعسكر",  # training camp
        "القائمة",  # squad list
    ],
    "french": [
        "blessure",  # injury
        "forfait",  # ruled out
        "réserve",  # reserve/bench
        "grève",  # strike
        "équipe B",  # B team
        "blessé",  # injured
        "absence",  # absence
        "titulaire",  # starter
        "remplaçant",  # substitute
        "composition",  # lineup/formation
        "effectif",  # squad
    ],
    # ADD MORE LANGUAGES TO MATCH intelligence_gate.py
    "german": [
        "verletzung",  # injury
        "streik",  # strike
        "schmerz",  # pain
        "körperliches problem",  # physical problem
        "abwesenheit",  # absence
        "verletzt",  # injured
        "reservist",  # reserve/bench
        "aufstellung",  # lineup/formation
    ],
    "portuguese": [
        "lesão",  # injury
        "greve",  # strike
        "dor",  # pain
        "problema físico",  # physical problem
        "ausência",  # absence
        "lesionado",  # injured
        "reserva",  # reserve/bench
        "escalação",  # lineup/formation
    ],
    "polish": [
        "kontuzja",  # injury
        "strajk",  # strike
        "ból",  # pain
        "problem fizyczny",  # physical problem
        "nieobecność",  # absence
        "kontuzjowany",  # injured
        "rezerwowy",  # reserve/bench
        "skład",  # lineup/formation
    ],
    "turkish": [
        "sakatlık",  # injury
        "grev",  # strike
        "ağrı",  # pain
        "fiziksel sorun",  # physical problem
        "yokluk",  # absence
        "sakat",  # injured
        "yedek",  # reserve/bench
        "kadro",  # lineup/formation
    ],
    "russian": [
        "травма",  # injury
        "забастовка",  # strike
        "боль",  # pain
        "физическая проблема",  # physical problem
        "отсутствие",  # absence
        "травмирован",  # injured
        "запасной",  # reserve/bench
        "состав",  # lineup/formation
    ],
    "dutch": [
        "blessure",  # injury
        "staking",  # strike
        "pijn",  # pain
        "fysiek probleem",  # physical problem
        "afwezigheid",  # absence
        "geblesseerd",  # injured
        "reservespeler",  # reserve/bench
        "opstelling",  # lineup/formation
    ],
}
```

---

## DATA FLOW VERIFICATION

### Complete Data Flow Trace

```
1. main.py calls run_cycle(continent)
   ↓
2. run_cycle() calls _get_handles_from_supabase(continent)
   ↓
3. SupabaseProvider.get_active_leagues_for_continent() or get_social_sources()
   ↓
4. run_cycle() calls scrape_accounts(handles_list)
   ↓
5. scrape_accounts() calls _scrape_account(handle) for each handle
   ↓
6. _scrape_account() checks cache -> if hit, returns cached tweets
   ↓
7. _scrape_account() calls _ensure_browser() -> initializes Playwright browser
   ↓
8. _scrape_account() navigates to Nitter instance -> gets HTML
   ↓
9. _scrape_account() calls _extract_tweets_from_html(html, handle)
   ↓
10. _extract_tweets_from_html() applies Layer 1: level_1_keyword_check()
    ↓
11. If passes, _process_tweets_layer2() applies Layer 2: level_2_translate_and_classify()
    ↓
12. scrape_accounts() caches results via NitterCache.set()
    ↓
13. run_cycle() applies TweetRelevanceFilter to tweets
    ↓
14. run_cycle() calls _link_and_trigger_matches(relevant_tweets)
    ↓
15. _link_and_trigger_matches() queries database for upcoming matches
    ↓
16. _check_team_match() checks if tweet matches team names (fuzzy matching)
    ↓
17. _trigger_analysis() stores intel in _nitter_intel_cache[match_id]
    ↓
18. main.py calls get_nitter_intel_for_match(match_id) to retrieve intel
```

### Integration Points Verified ✅

| Integration Point | Status | Notes |
|-----------------|---------|---------|
| SupabaseProvider | ✅ CORRECT | All methods exist and properly called |
| TweetRelevanceFilter | ✅ CORRECT | Properly filters tweets by relevance |
| IntelligenceGate | ⚠️ ISSUE #5 | Fallback less comprehensive |
| Database (get_db_session) | ✅ CORRECT | Lock errors handled with retry |
| main.py (get_nitter_intel_for_match) | ✅ CORRECT | Called at lines 1462, 1534, 2144 |
| InstanceHealth (nitter_pool.py) | ✅ CORRECT | Thread-safe modifications |

---

## VPS DEPLOYMENT CHECKLIST

### Pre-Deployment Requirements

- [ ] **Apply Fix #1:** Add thread safety to `_nitter_intel_cache`
- [ ] **Apply Fix #2:** Add thread safety to `_ensure_browser()`
- [ ] **Apply Fix #3:** Add thread safety to `NitterCache`
- [ ] **Apply Fix #4:** Install Playwright browser binaries (`playwright install chromium`)
- [ ] **Apply Fix #5:** Update fallback keywords OR make intelligence_gate hard dependency

### Environment Variables Required

All required environment variables are documented in [`.env.template`](.env.template):

```bash
# NITTER FALLBACK SCRAPER CONFIGURATION
NITTER_MAX_RETRIES=3            # Maximum retry attempts per account
MAX_NITTER_RECOVERY_ACCOUNTS=10 # Maximum accounts to recover via Nitter

# AI Analysis (OpenRouter - DeepSeek V3.2)
OPENROUTER_API_KEY=your_openrouter_key_here

# Supabase Database
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here
```

### Dependencies Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser binaries (REQUIRED for VPS)
playwright install chromium
```

### VPS-Specific Considerations

1. **Thread Safety:** All 3 critical fixes must be applied before VPS deployment
2. **Browser Resources:** Playwright requires ~200MB RAM per browser instance
3. **Timeouts:** 30-second timeouts are appropriate for VPS network conditions
4. **Cache TTL:** 6-hour cache reduces API usage and improves performance
5. **Retry Logic:** Exponential backoff handles transient network errors

---

## CONCLUSION

The NitterFallbackScraper component is well-integrated with the bot's data flow and has solid error handling. However, **3 critical thread safety issues** must be fixed before VPS deployment to prevent crashes and data corruption.

### Priority Order for Fixes:

1. **HIGH PRIORITY:** Fix #1, #2, #3 (Thread safety - CRITICAL for VPS)
2. **MEDIUM PRIORITY:** Fix #4 (Playwright browser installation - Required for VPS)
3. **LOW PRIORITY:** Fix #5 (Keyword gate consistency - Improves filtering when intelligence_gate unavailable)

### Risk Assessment:

- **Without Fixes:** HIGH RISK - Crashes, data corruption, lost intel
- **With Critical Fixes (#1-3):** LOW RISK - Stable VPS deployment
- **With All Fixes:** VERY LOW RISK - Production-ready

---

**Report Generated:** 2026-03-10T20:43:00Z
**Verification Method:** COVE (Chain of Verification) - Double Verification
**Environment:** VPS Deployment Focus
