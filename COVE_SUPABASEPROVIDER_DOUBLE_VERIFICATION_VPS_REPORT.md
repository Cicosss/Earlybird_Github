# COVE Double Verification Report: SupabaseProvider (VPS Deployment)

**Date:** 2026-03-11  
**Mode:** Chain of Verification (CoVe)  
**Scope:** SupabaseProvider class methods and VPS deployment readiness  
**Focus:** Thread safety, cache consistency, data flow, and VPS compatibility

---

## Executive Summary

This report documents a comprehensive Chain of Verification (CoVe) analysis of the [`SupabaseProvider`](src/database/supabase_provider.py:65) class, focusing on the methods specified in the task. The verification identified **5 issues** ranging from critical race conditions to dead code and data inconsistencies.

### Severity Breakdown
- **CRITICAL:** 1 issue (Race condition)
- **HIGH:** 1 issue (Inconsistency)
- **MEDIUM:** 2 issues (Inefficiency, Bug)
- **LOW:** 1 issue (Dead code)

---

## Phase 1: Draft Analysis

The SupabaseProvider class provides:
- Singleton pattern for database connection
- Caching with configurable TTL (default 300s)
- Local mirror fallback for offline scenarios
- Thread-safe operations with locks
- Methods for fetching hierarchical data (continents, countries, leagues, sources)
- Active league filtering based on UTC time
- Cache invalidation methods
- Connection management (reconnect, test_connection)

**Methods Analyzed:**
- [`create_local_mirror()`](src/database/supabase_provider.py:1397)
- [`fetch_all_news_sources()`](src/database/supabase_provider.py:1231)
- [`fetch_continents()`](src/database/supabase_provider.py:888)
- [`fetch_countries()`](src/database/supabase_provider.py:900)
- [`fetch_hierarchical_map()`](src/database/supabase_provider.py:951)
- [`fetch_leagues()`](src/database/supabase_provider.py:916)
- [`fetch_sources()`](src/database/supabase_provider.py:932)
- [`get_active_continent_blocks()`](src/database/supabase_provider.py:1181)
- [`get_active_leagues()`](src/database/supabase_provider.py:1035)
- [`get_active_leagues_for_continent()`](src/database/supabase_provider.py:1155)
- [`get_cache_lock_stats()`](src/database/supabase_provider.py:222)
- [`get_cache_metrics()`](src/database/supabase_provider.py:240)
- [`get_cache_stats()`](src/database/supabase_provider.py:1598)
- [`get_connection_error()`](src/database/supabase_provider.py:218)
- [`get_continental_sources()`](src/database/supabase_provider.py:1264)
- [`get_news_sources()`](src/database/supabase_provider.py:1218)
- [`get_social_sources()`](src/database/supabase_provider.py:1241)
- [`get_social_sources_for_league()`](src/database/supabase_provider.py:1251)
- [`invalidate_cache()`](src/database/supabase_provider.py:264)
- [`invalidate_leagues_cache()`](src/database/supabase_provider.py:294)
- [`is_connected()`](src/database/supabase_provider.py:214)
- [`reconnect()`](src/database/supabase_provider.py:199)
- [`refresh_mirror()`](src/database/supabase_provider.py:1546)
- [`test_connection()`](src/database/supabase_provider.py:1613)
- [`update_mirror()`](src/database/supabase_provider.py:1355)
- [`validate_api_keys()`](src/database/supabase_provider.py:1292)

---

## Phase 2: Adversarial Verification Questions

### Thread Safety Issues
1. Is the singleton pattern truly thread-safe?
2. Are all cache operations properly locked?
3. Is there potential for deadlock with nested lock acquisitions?

### Cache Consistency Issues
4. Does [`invalidate_cache()`](src/database/supabase_provider.py:264) properly clear all related entries?
5. Are cache keys consistent across methods?
6. Is there stale cache risk after updates?

### Data Flow Issues
7. Do callers handle empty returns correctly?
8. Are fallback mechanisms working properly?
9. Is error handling comprehensive?

### VPS Deployment Issues
10. Are all dependencies listed in requirements.txt?
11. Are environment variables properly documented?
12. Are timeouts appropriate for VPS conditions?

### Integration Issues
13. Do callers expect the exact data structure returned?
14. Are method signatures consistent?
15. Is there circular dependency risk?

---

## Phase 3: Verification Results

### Issue #1: CRITICAL RACE CONDITION in `invalidate_leagues_cache()`

**Location:** [`src/database/supabase_provider.py:315`](src/database/supabase_provider.py:315)

**Code:**
```python
def invalidate_leagues_cache(self) -> None:
    league_related_keys = [
        "active_leagues_full",
        "leagues",
        "countries",
        "continents",
    ]

    # Also invalidate any keys that contain "leagues", "countries", or "continents"
    all_keys = list(self._cache.keys())  # ❌ RACE CONDITION: No lock!
    for key in all_keys:
        if any(keyword in key.lower() for keyword in ["leagues", "countries", "continents"]):
            league_related_keys.append(key)

    # Remove duplicates while preserving order
    league_related_keys = list(dict.fromkeys(league_related_keys))

    # Acquire lock AFTER getting keys
    if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
        try:
            cleared_count = 0
            for key in league_related_keys:
                if key in self._cache:
                    del self._cache[key]
                    if key in self._cache_timestamps:
                        del self._cache_timestamps[key]
                    cleared_count += 1
            logger.info(f"🗑️ League cache invalidated ({cleared_count} entries)")
        finally:
            self._cache_lock.release()
```

**Problem:**
- Line 315: `all_keys = list(self._cache.keys())` is called WITHOUT acquiring the lock first
- This creates a race condition where:
  1. Thread A gets list of keys from cache
  2. Thread B modifies cache (adds/removes keys)
  3. Thread A tries to invalidate keys that may no longer exist or miss new keys

**Impact:**
- **VPS Impact:** On a VPS with multiple threads processing different leagues, this race condition can cause:
  - Stale cache entries to remain after invalidation
  - Attempts to delete non-existent keys (harmless but inefficient)
  - New cache keys added during iteration to be missed
- **Data Flow Impact:** Inconsistent cache state can lead to incorrect league data being returned

**Fix Required:**
```python
def invalidate_leagues_cache(self) -> None:
    league_related_keys = [
        "active_leagues_full",
        "leagues",
        "countries",
        "continents",
    ]

    # ✅ FIX: Acquire lock BEFORE getting keys
    if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
        try:
            # Also invalidate any keys that contain "leagues", "countries", or "continents"
            all_keys = list(self._cache.keys())
            for key in all_keys:
                if any(keyword in key.lower() for keyword in ["leagues", "countries", "continents"]):
                    league_related_keys.append(key)

            # Remove duplicates while preserving order
            league_related_keys = list(dict.fromkeys(league_related_keys))

            cleared_count = 0
            for key in league_related_keys:
                if key in self._cache:
                    del self._cache[key]
                    if key in self._cache_timestamps:
                        del self._cache_timestamps[key]
                    cleared_count += 1
            logger.info(f"🗑️ League cache invalidated ({cleared_count} entries)")
        finally:
            self._cache_lock.release()
    else:
        logger.warning("Failed to acquire cache lock for league invalidation")
```

---

### Issue #2: INEFFICIENCY in `fetch_hierarchical_map()`

**Location:** [`src/database/supabase_provider.py:1020-1026`](src/database/supabase_provider.py:1020)

**Code:**
```python
def fetch_hierarchical_map(self) -> dict[str, Any]:
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
            "countries": [],
        }

        countries = self.fetch_countries(continent.get("id"))

        for country in countries:
            country_data = {"id": country.get("id"), "name": country.get("name"), "leagues": []}

            leagues = self.fetch_leagues(country.get("id"))

            for league in leagues:
                league_data = {
                    "id": league.get("id"),
                    "name": league.get("name"),
                    "sources": self.fetch_sources(league.get("id")),
                }
                country_data["leagues"].append(league_data)

            continent_data["countries"].append(country_data)

        hierarchical_data["continents"].append(continent_data)

    # Cache result
    self._set_cache(cache_key, hierarchical_data)

    # Save to mirror
    mirror_data = {
        "continents": continents,  # ✅ Already fetched at line 987
        "countries": self.fetch_countries(),  # ❌ REDUNDANT: Fetches ALL countries again!
        "leagues": self.fetch_leagues(),  # ❌ REDUNDANT: Fetches ALL leagues again!
        "news_sources": self.fetch_sources(),  # ❌ REDUNDANT: Fetches ALL sources again!
    }
    self._save_to_mirror(mirror_data)

    logger.info("Built complete hierarchical map")
    return hierarchical_data
```

**Problem:**
- Lines 1022-1024 fetch ALL countries, leagues, and sources again (redundant!)
- These were already fetched in the loop above (lines 987-1008)
- Could return inconsistent data if database changes between calls

**Impact:**
- **VPS Impact:** On a VPS with limited resources, this inefficiency causes:
  - Unnecessary API calls to Supabase (3x more queries than needed)
  - Increased latency for hierarchical map generation
  - Higher bandwidth usage
- **Data Flow Impact:** Potential inconsistency if database changes between calls

**Fix Required:**
```python
def fetch_hierarchical_map(self) -> dict[str, Any]:
    cache_key = "hierarchical_map_full"

    # Try cache first
    cached_data = self._get_from_cache(cache_key)
    if cached_data is not None:
        return cached_data

    # Build hierarchical structure
    continents = self.fetch_continents()
    hierarchical_data = {"continents": []}

    # ✅ FIX: Collect all data during iteration to avoid redundant fetches
    all_countries = []
    all_leagues = []
    all_sources = []

    for continent in continents:
        continent_data = {
            "id": continent.get("id"),
            "name": continent.get("name"),
            "countries": [],
        }

        countries = self.fetch_countries(continent.get("id"))
        all_countries.extend(countries)

        for country in countries:
            country_data = {"id": country.get("id"), "name": country.get("name"), "leagues": []}

            leagues = self.fetch_leagues(country.get("id"))
            all_leagues.extend(leagues)

            for league in leagues:
                sources = self.fetch_sources(league.get("id"))
                all_sources.extend(sources)

                league_data = {
                    "id": league.get("id"),
                    "name": league.get("name"),
                    "sources": sources,
                }
                country_data["leagues"].append(league_data)

            continent_data["countries"].append(country_data)

        hierarchical_data["continents"].append(continent_data)

    # Cache result
    self._set_cache(cache_key, hierarchical_data)

    # ✅ FIX: Use collected data instead of fetching again
    mirror_data = {
        "continents": continents,
        "countries": all_countries,
        "leagues": all_leagues,
        "news_sources": all_sources,
    }
    self._save_to_mirror(mirror_data)

    logger.info("Built complete hierarchical map")
    return hierarchical_data
```

---

### Issue #3: BUG in `get_active_leagues()`

**Location:** [`src/database/supabase_provider.py:1090`](src/database/supabase_provider.py:1090)

**Code:**
```python
def get_active_leagues(self, bypass_cache: bool = False) -> list[dict[str, Any]]:
    # ...
    
    # Collect unique country_ids and continent_ids from active leagues
    country_ids = set()
    continent_ids = set()
    for league in leagues:
        country_id = league.get("country_id")
        if country_id:
            country_ids.add(country_id)
        continent_id = league.get("country_id")  # ❌ BUG: Assigns country_id to continent_id!
        # Note: We'll fetch continent info through countries
```

**Problem:**
- Line 1090: `continent_id = league.get("country_id")` is WRONG!
- This assigns `country_id` to `continent_id`, which is incorrect
- The continent_id should be fetched from country, not from league directly
- The line is redundant and should be removed

**Impact:**
- **VPS Impact:** Minimal - this bug doesn't cause crashes but creates confusion
- **Data Flow Impact:** The `continent_ids` set will contain country IDs instead of continent IDs, which is semantically wrong

**Fix Required:**
```python
def get_active_leagues(self, bypass_cache: bool = False) -> list[dict[str, Any]]:
    # ...
    
    # Collect unique country_ids from active leagues
    country_ids = set()
    for league in leagues:
        country_id = league.get("country_id")
        if country_id:
            country_ids.add(country_id)
    
    # ✅ FIX: Removed redundant and incorrect line
    # We'll fetch continent info through countries

    # Fetch only the countries and continents needed for active leagues
    countries_to_fetch = list(country_ids)
    continents_to_fetch = set()

    # Build lookup dictionaries
    country_map = {}
    continent_map = {}

    if countries_to_fetch:
        logger.debug(f"Fetching {len(countries_to_fetch)} countries for active leagues")
        countries = self.fetch_countries()
        for country in countries:
            country_map[country["id"]] = country
            continent_id = country.get("continent_id")
            if continent_id:
                continents_to_fetch.add(continent_id)
```

---

### Issue #4: INCONSISTENCY in Mirror Data Validation

**Locations:**
- [`src/database/supabase_provider.py:536`](src/database/supabase_provider.py:536) - `_validate_data_completeness()`
- [`src/database/supabase_provider.py:751`](src/database/supabase_provider.py:751) - `_load_from_mirror()`
- [`src/database/supabase_provider.py:1422-1428`](src/database/supabase_provider.py:1422) - `create_local_mirror()`
- [`src/database/supabase_provider.py:1375-1381`](src/database/supabase_provider.py:1375) - `update_mirror()`

**Code:**
```python
# In _validate_data_completeness() at line 536:
def _validate_data_completeness(self, data: dict[str, Any]) -> bool:
    # V11.1: Check for required top-level keys
    required_keys = ["continents", "countries", "leagues", "news_sources"]  # ❌ Missing "social_sources"!
    missing_keys = [key for key in required_keys if key not in data]

# In _load_from_mirror() at line 751:
def _load_from_mirror(self) -> dict[str, Any] | None:
    # Validate JSON structure - check for required top-level keys
    if isinstance(data, dict) and all(
        k in data
        for k in ["continents", "countries", "leagues", "news_sources"]  # ❌ Missing "social_sources"!
    ):
        # ...

# In create_local_mirror() at lines 1422-1428:
def create_local_mirror(self) -> bool:
    mirror_data = {
        "continents": self.fetch_continents(),
        "countries": self.fetch_countries(),
        "leagues": self.fetch_leagues(),
        "social_sources": self.get_social_sources(),  # ✅ Includes "social_sources"
        "news_sources": self.fetch_all_news_sources(),
    }

# In update_mirror() at lines 1375-1381:
def update_mirror(self, force: bool = False) -> bool:
    mirror_data = {
        "continents": self.fetch_continents(),
        "countries": self.fetch_countries(),
        "leagues": self.fetch_leagues(),
        "social_sources": self.get_social_sources(),  # ✅ Includes "social_sources"
        "news_sources": self.fetch_all_news_sources(),
    }
```

**Problem:**
- `_validate_data_completeness()` at line 536 doesn't check for "social_sources"
- `_load_from_mirror()` at line 751 doesn't check for "social_sources"
- But `create_local_mirror()` and `update_mirror()` save "social_sources" to mirror!
- This creates an inconsistency where mirror data includes "social_sources" but validation doesn't check for it

**Impact:**
- **VPS Impact:** Minimal - validation may still pass because "social_sources" is optional
- **Data Flow Impact:** Inconsistent validation logic could lead to incomplete mirror data being accepted

**Fix Required:**
```python
# In _validate_data_completeness() at line 536:
def _validate_data_completeness(self, data: dict[str, Any]) -> bool:
    # V11.1: Check for required top-level keys
    required_keys = ["continents", "countries", "leagues", "news_sources", "social_sources"]  # ✅ Added "social_sources"
    missing_keys = [key for key in required_keys if key not in data]

# In _load_from_mirror() at line 751:
def _load_from_mirror(self) -> dict[str, Any] | None:
    # Validate JSON structure - check for required top-level keys
    if isinstance(data, dict) and all(
        k in data
        for k in ["continents", "countries", "leagues", "news_sources", "social_sources"]  # ✅ Added "social_sources"
    ):
        # ...
```

---

### Issue #5: DEAD CODE - `get_continental_sources()`

**Location:** [`src/database/supabase_provider.py:1264`](src/database/supabase_provider.py:1264)

**Code:**
```python
def get_continental_sources(self, continent_id: str) -> list[dict[str, Any]]:
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
```

**Problem:**
- This method is defined but NEVER called anywhere in the codebase
- Verified by searching for `get_continental_sources(` across all Python files
- Only found in the definition itself

**Impact:**
- **VPS Impact:** None - dead code doesn't affect runtime
- **Data Flow Impact:** None - dead code doesn't affect data flow
- **Maintainability:** Dead code adds confusion and maintenance burden

**Recommendation:**
- Remove this method if it's not needed
- Or document its intended use case if it's planned for future use

---

## Phase 4: Final Assessment

### VPS Deployment Readiness

#### ✅ Dependencies
All required dependencies are listed in [`requirements.txt`](requirements.txt):
- `supabase==2.27.3` - Official Supabase Python client
- `httpx[http2]==0.28.1` - HTTP client with timeout support
- `postgrest==2.27.3` - PostgREST client for Supabase

**No additional dependencies required.**

#### ✅ Environment Variables
All required environment variables are documented in [`.env.template`](.env.template:66-70):
```
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here
SUPABASE_CACHE_TTL_SECONDS=300
```

#### ✅ Thread Safety
- Singleton pattern uses double-checked locking with `_instance_lock` (line 87)
- All cache operations use `_acquire_cache_lock_with_monitoring()` with timeout
- No nested lock acquisitions detected (deadlock-safe)

**Exception:** The race condition in `invalidate_leagues_cache()` must be fixed.

#### ✅ Cache Consistency
- Cache keys are consistent across methods
- TTL-based invalidation works correctly
- `invalidate_cache()` properly clears all cache entries
- `invalidate_leagues_cache()` clears league-related entries

**Exception:** The race condition in `invalidate_leagues_cache()` must be fixed.

#### ✅ Error Handling
- All methods have try-except blocks
- Fallback to mirror on Supabase failure
- Graceful degradation on connection errors
- Comprehensive logging for debugging

#### ✅ Data Flow Integration
Methods are correctly integrated with the bot's data flow:

1. **Main Loop Integration** ([`src/main.py:2272-2290`](src/main.py:2272)):
   - `refresh_mirror()` called at start of each cycle
   - Connection check and reconnection logic included

2. **League Manager Integration** ([`src/ingestion/league_manager.py:345`](src/ingestion/league_manager.py:345)):
   - `get_active_continent_blocks()` used to determine active continents
   - `get_active_leagues()` used to fetch active leagues

3. **Search Provider Integration** ([`src/ingestion/search_provider.py:72`](src/ingestion/search_provider.py:72)):
   - `get_active_leagues()` used to map league keys to IDs
   - `get_news_sources()` used to fetch news sources for leagues

4. **News Hunter Integration** ([`src/processing/news_hunter.py:170`](src/processing/news_hunter.py:170)):
   - `get_social_sources()` used to fetch Twitter handles
   - `get_news_sources()` used to fetch news domains

5. **Twitter Intel Cache Integration** ([`src/services/twitter_intel_cache.py:139`](src/services/twitter_intel_cache.py:139)):
   - `get_social_sources()` used to fetch social sources

#### ✅ Timeout Configuration
- `SUPABASE_QUERY_TIMEOUT = 10.0` seconds (line 58)
- `CACHE_LOCK_TIMEOUT = 10.0` seconds (line 59)
- Retry logic with exponential backoff for connection (lines 144-197)
- Appropriate for VPS with potentially slow I/O

### Critical Issues Summary

| # | Issue | Severity | Location | VPS Impact | Data Flow Impact |
|---|--------|-----------|-------------|-----------------|
| 1 | Race condition in `invalidate_leagues_cache()` | CRITICAL | Line 315 | High - Inconsistent cache state | High - Stale data |
| 2 | Inefficiency in `fetch_hierarchical_map()` | MEDIUM | Lines 1022-1024 | Medium - Unnecessary API calls | Medium - Potential inconsistency |
| 3 | Bug in `get_active_leagues()` | MEDIUM | Line 1090 | Low - No crash | Low - Semantic error |
| 4 | Inconsistency in mirror validation | HIGH | Lines 536, 751 | Low - Validation still passes | Medium - Incomplete data accepted |
| 5 | Dead code `get_continental_sources()` | LOW | Line 1264 | None | None |

---

## Recommendations

### Immediate Actions (Before VPS Deployment)

1. **Fix CRITICAL race condition** in `invalidate_leagues_cache()`:
   - Move `all_keys = list(self._cache.keys())` inside the lock
   - This is the highest priority issue that could cause data inconsistencies

2. **Fix HIGH inconsistency** in mirror validation:
   - Add "social_sources" to required_keys in `_validate_data_completeness()`
   - Add "social_sources" to validation in `_load_from_mirror()`

### Short-term Actions (Within 1 Week)

3. **Fix MEDIUM inefficiency** in `fetch_hierarchical_map()`:
   - Collect data during iteration instead of fetching again
   - This will reduce API calls and improve performance

4. **Fix MEDIUM bug** in `get_active_leagues()`:
   - Remove the redundant and incorrect line 1090
   - This is a simple cleanup that improves code clarity

### Long-term Actions (Within 1 Month)

5. **Remove dead code** `get_continental_sources()`:
   - Either remove the method or document its intended use case
   - This improves maintainability and reduces confusion

---

## Conclusion

The SupabaseProvider implementation is **mostly ready for VPS deployment** with the following caveats:

1. **CRITICAL ISSUE:** The race condition in `invalidate_leagues_cache()` must be fixed before production deployment. This could cause inconsistent cache state and stale data on a multi-threaded VPS.

2. **HIGH ISSUE:** The inconsistency in mirror validation should be fixed to ensure data integrity.

3. **MEDIUM ISSUES:** The inefficiency in `fetch_hierarchical_map()` and the bug in `get_active_leagues()` should be addressed for optimal performance and code clarity.

4. **LOW ISSUE:** The dead code `get_continental_sources()` should be removed or documented.

All other aspects of the implementation (dependencies, environment variables, thread safety, error handling, data flow integration, timeout configuration) are well-designed and ready for VPS deployment.

**Overall Assessment:** **Ready for deployment after fixing critical and high-severity issues.**

---

## Appendix: Data Flow Verification

### Complete Data Flow Through SupabaseProvider

```
┌─────────────────────────────────────────────────────────────────┐
│                    Main Cycle (src/main.py)                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  refresh_mirror()                                      │ │
│  │    ├─> create_local_mirror()                           │ │
│  │    │    ├─> fetch_continents()                        │ │
│  │    │    ├─> fetch_countries()                         │ │
│  │    │    ├─> fetch_leagues()                           │ │
│  │    │    ├─> get_social_sources()                        │ │
│  │    │    └─> fetch_all_news_sources()                   │ │
│  │    └─> _save_to_mirror()                             │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              League Manager (league_manager.py)                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  get_active_leagues_for_continental_blocks()             │ │
│  │    ├─> get_active_continent_blocks()                   │ │
│  │    │    └─> fetch_continents()                         │ │
│  │    └─> get_active_leagues()                           │ │
│  │         ├─> fetch_leagues() (with is_active filter)      │ │
│  │         ├─> fetch_countries()                           │ │
│  │         └─> fetch_continents()                         │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Search Provider (search_provider.py)               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  _fetch_news_sources_from_supabase()                  │ │
│  │    ├─> get_active_leagues()                           │ │
│  │    └─> get_news_sources(league_id)                     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│               News Hunter (news_hunter.py)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  get_social_sources_from_supabase()                    │ │
│  │    └─> get_social_sources()                           │ │
│  │  get_news_sources_from_supabase()                      │ │
│  │    ├─> fetch_leagues()                                │ │
│  │    └─> get_news_sources(league_id)                     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Cache Invalidation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              Cache Inactivation Triggers                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Manual invalidation:                                  │
│     └─> invalidate_cache(cache_key=None)                    │
│         └─> Clears ALL cache entries                       │
│                                                             │
│  2. League-specific invalidation:                            │
│     └─> invalidate_leagues_cache()                          │
│         └─> Clears league-related cache entries              │
│                                                             │
│  3. Force mirror update:                                    │
│     └─> update_mirror(force=True)                           │
│         └─> invalidate_cache(cache_key=None)                   │
│                                                             │
│  4. Bypass cache:                                         │
│     └─> get_active_leagues(bypass_cache=True)               │
│         └─> Skips cache, fetches fresh data                │
└─────────────────────────────────────────────────────────────────┘
```

---

**Report Generated:** 2026-03-11T20:02:00Z  
**Verification Mode:** Chain of Verification (CoVe)  
**Next Review:** After critical and high-severity issues are fixed
