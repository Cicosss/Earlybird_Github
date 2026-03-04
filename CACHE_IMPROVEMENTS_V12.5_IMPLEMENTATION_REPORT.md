# Cache Improvements V12.5 Implementation Report

**Date:** 2026-03-03
**Version:** V12.5
**Author:** CoVe Verification
**Status:** ✅ COMPLETED AND TESTED

---

## Executive Summary

This report documents the implementation of comprehensive cache improvements to the SupabaseProvider class to address critical cache staleness issues identified in the verification report. The cache was causing inconsistent behavior where direct database queries showed correct data (LATAM:5, ASIA:4, AFRICA:4 leagues) but cached queries showed stale data (LATAM:5, ASIA:0, AFRICA:0 leagues).

**Root Cause Identified:**
1. Cache TTL was too long (1 hour), causing stale data
2. Cache key conflict between raw data and enriched data
3. No cache hit/miss logging for observability
4. No cache metrics tracking for monitoring
5. No bypass cache option for critical operations
6. No cache invalidation mechanism

**Solution Implemented:**
1. ✅ Reduced cache TTL from 1 hour to 5 minutes (configurable via environment variable)
2. ✅ Added cache hit/miss logging with detailed information (age, TTL)
3. ✅ Added cache metrics tracking (hit_count, miss_count, bypass_count, hit_ratio)
4. ✅ Added bypass cache option for critical operations
5. ✅ Implemented cache invalidation mechanism
6. ✅ Fixed cache key conflict between raw data and enriched data

---

## Changes Made

### 1. Environment Variable Configuration

**File:** `.env.template`

**Change:** Added `SUPABASE_CACHE_TTL_SECONDS` environment variable

```bash
# SUPABASE DATABASE (V9.0 - News Radar Dynamic Sources)
# ============================================
SUPABASE_URL=your_supabase_url_here      # https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key_here      # anon/public key from Supabase dashboard
SUPABASE_CACHE_TTL_SECONDS=300            # Cache TTL in seconds (default: 300 = 5 minutes)
```

**Rationale:** Making cache TTL configurable allows tuning without code changes. The default of 300 seconds (5 minutes) provides a good balance between data freshness and caching benefits.

---

### 2. Cache TTL Configuration

**File:** `src/database/supabase_provider.py`

**Change:** Updated `CACHE_TTL_SECONDS` constant to read from environment variable

```python
# Constants
# V12.5: Cache TTL is now configurable via environment variable (default: 300 seconds = 5 minutes)
# This reduces cache staleness while still providing caching benefits
CACHE_TTL_SECONDS = int(os.getenv("SUPABASE_CACHE_TTL_SECONDS", "300"))
SUPABASE_QUERY_TIMEOUT = 10.0  # 10 second timeout for queries (V11.1)
CACHE_LOCK_TIMEOUT = 10.0  # V12.2: Increased from 5.0s for VPS with slow I/O
CACHE_LOCK_RETRIES = 2  # V12.2: Retry lock acquisition on timeout
MIRROR_FILE_PATH = Path("data/supabase_mirror.json")
DATA_DIR = Path("data")
```

**Rationale:** Reading from environment variable provides flexibility for different deployment scenarios (development, staging, production).

---

### 3. Cache Metrics Tracking

**File:** `src/database/supabase_provider.py`

**Change:** Added cache metrics tracking to `__init__` method

```python
def __init__(self):
    """Initialize the Supabase provider (only once)."""
    if self._initialized:
        return

    self._initialized = True
    self._cache: dict[str, Any] = {}
    self._cache_timestamps: dict[str, float] = {}
    self._cache_lock = threading.Lock()  # V11.1: Thread-safe cache operations
    self._connected = False
    self._connection_error: str | None = None

    # V12.1: Lock contention monitoring for production observability
    self._cache_lock_wait_time = 0.0
    self._cache_lock_wait_count = 0
    self._cache_lock_timeout_count = 0

    # V12.5: Cache metrics tracking for observability
    self._cache_hit_count = 0
    self._cache_miss_count = 0
    self._cache_bypass_count = 0
```

**Rationale:** Tracking cache metrics provides visibility into cache performance and helps identify issues.

---

### 4. Cache Metrics Exposure

**File:** `src/database/supabase_provider.py`

**Change:** Added `get_cache_metrics()` method

```python
def get_cache_metrics(self) -> dict:
    """
    Get cache performance metrics for monitoring.

    V12.5: Expose cache hit/miss metrics for production observability.

    Returns:
        Dict with cache metrics (hit_count, miss_count, hit_ratio, etc.)
    """
    total_requests = self._cache_hit_count + self._cache_miss_count
    hit_ratio = (
        round(self._cache_hit_count / total_requests * 100, 2) if total_requests > 0 else 0.0
    )

    return {
        "hit_count": self._cache_hit_count,
        "miss_count": self._cache_miss_count,
        "bypass_count": self._cache_bypass_count,
        "total_requests": total_requests,
        "hit_ratio_percent": hit_ratio,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cached_keys_count": len(self._cache),
    }
```

**Rationale:** Exposing metrics allows monitoring and debugging of cache behavior.

---

### 5. Enhanced Cache Hit/Miss Logging

**File:** `src/database/supabase_provider.py`

**Change:** Enhanced `_get_from_cache()` method with detailed logging

```python
def _get_from_cache(self, cache_key: str, bypass_cache: bool = False) -> Any | None:
    """
    Retrieve data from cache if valid (thread-safe).

    V12.2: Added retry logic for lock acquisition.
    V12.5: Added bypass_cache parameter, cache miss logging, and cache age information.

    Args:
        cache_key: Cache key to retrieve
        bypass_cache: If True, skip cache and return None (forces fresh data fetch)

    Returns:
        Cached data if valid, None otherwise
    """
    # V12.5: Track bypass operations
    if bypass_cache:
        self._cache_bypass_count += 1
        logger.debug(f"🔄 Cache bypassed for key: {cache_key}")
        return None

    # V12.0: Fixed deadlock - use _is_cache_valid_unlocked() instead of _is_cache_valid()
    # V12.1: Use lock acquisition with monitoring
    # V12.2: Added retry logic for improved VPS compatibility
    for attempt in range(CACHE_LOCK_RETRIES):
        if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
            try:
                if self._is_cache_valid_unlocked(cache_key):
                    # V12.5: Track cache hit and log with age information
                    self._cache_hit_count += 1
                    cache_age = time.time() - self._cache_timestamps[cache_key]
                    logger.debug(
                        f"✅ Cache HIT for key: {cache_key} (age: {cache_age:.1f}s, TTL: {CACHE_TTL_SECONDS}s)"
                    )
                    return self._cache[cache_key]
                else:
                    # V12.5: Track cache miss and log reason
                    self._cache_miss_count += 1
                    if cache_key in self._cache_timestamps:
                        cache_age = time.time() - self._cache_timestamps[cache_key]
                        logger.debug(
                            f"❌ Cache MISS for key: {cache_key} (expired: {cache_age:.1f}s > TTL: {CACHE_TTL_SECONDS}s)"
                        )
                    else:
                        logger.debug(f"❌ Cache MISS for key: {cache_key} (not found)")
                    return None
            finally:
                self._cache_lock.release()
        else:
            if attempt < CACHE_LOCK_RETRIES - 1:
                logger.warning(
                    f"Retry {attempt + 1}/{CACHE_LOCK_RETRIES} for cache lock: {cache_key}"
                )
            else:
                logger.warning(
                    f"Failed to acquire cache lock after {CACHE_LOCK_RETRIES} retries: {cache_key}"
                )
                return None
    return None
```

**Rationale:** Detailed logging helps understand cache behavior and identify issues.

---

### 6. Bypass Cache Parameter

**File:** `src/database/supabase_provider.py`

**Change:** Added `bypass_cache` parameter to `_execute_query()` and `get_active_leagues()`

```python
def _execute_query(
    self,
    table_name: str,
    cache_key: str,
    select: str = "*",
    filters: dict[str, Any] | None = None,
    bypass_cache: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute Supabase query with caching and fail-safe mirror.

    V11.1: Added explicit timeout to prevent indefinite hangs on VPS.
    V11.2: Added detailed timing logs for debugging timeout issues.
    V11.3: Fixed potential deadlock by releasing cache lock before query.
    V12.5: Added bypass_cache parameter and enhanced logging for cache behavior.

    Args:
        table_name: Name of the table to query
        cache_key: Unique key for caching
        select: Select clause (default: "*")
        filters: Optional dictionary of filters
        bypass_cache: If True, skip cache and fetch fresh data (default: False)

    Returns:
        List of records from the table
    """
    # Try cache first (with lock)
    cached_data = self._get_from_cache(cache_key, bypass_cache=bypass_cache)
    if cached_data is not None:
        logger.debug(f"✅ Cache hit for {table_name} (key: {cache_key})")
        return cached_data

    # V12.5: Log that we're fetching fresh data
    if bypass_cache:
        logger.info(f"🔄 Bypassing cache for {table_name} (key: {cache_key})")
    else:
        logger.debug(f"🔄 Cache miss for {table_name} (key: {cache_key}), fetching fresh data")

    # Try Supabase connection
    if self._connected and self._client:
        try:
            logger.debug(
                f"🔄 Executing query for {table_name} (timeout: {SUPABASE_QUERY_TIMEOUT}s)..."
            )
            query_start = time.time()

            query = self._client.table(table_name).select(select)

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            # V11.1: Execute query (timeout configured at client creation)
            logger.debug(f"🔄 Calling query.execute() for {table_name}...")
            execute_start = time.time()
            response = query.execute()
            execute_time = time.time() - execute_start
            logger.debug(
                f"✅ query.execute() completed in {execute_time:.2f}s for {table_name}"
            )

            data = response.data if hasattr(response, "data") else []

            total_time = time.time() - query_start
            logger.info(
                f"✅ Supabase query for {table_name} completed in {total_time:.2f}s (returned {len(data)} records)"
            )

            # Cache the result (with lock)
            self._set_cache(cache_key, data)

            return data

        except Exception as e:
            # V11.1: Enhanced error logging with timeout detection
            error_type = type(e).__name__
            error_msg = str(e)

            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.error(
                    f"⏱️ Supabase query timeout for {table_name} (>{SUPABASE_QUERY_TIMEOUT}s)"
                )
            else:
                logger.warning(
                    f"Supabase query failed for {table_name}: {error_type}: {error_msg}"
                )
            # Fall through to mirror

    # Fallback to mirror
    logger.info(f"🔄 Falling back to mirror for {table_name}")
    mirror_start = time.time()
    mirror_data = self._load_from_mirror()
    mirror_time = time.time() - mirror_start

    if mirror_data and table_name in mirror_data:
        logger.info(
            f"✅ Mirror fallback for {table_name} completed in {mirror_time:.2f}s (returned {len(mirror_data[table_name])} records)"
        )
        return mirror_data[table_name]

    logger.error(f"❌ No data available for {table_name} (Supabase and mirror failed)")
    return []
```

```python
def get_active_leagues(self, bypass_cache: bool = False) -> list[dict[str, Any]]:
    """
    Fetch all active leagues with country and continent information.

    V12.5: Added bypass_cache parameter for critical operations.

    Args:
        bypass_cache: If True, skip cache and fetch fresh data (default: False)

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
    cached_data = self._get_from_cache(cache_key, bypass_cache=bypass_cache)
    if cached_data is not None:
        return cached_data

    # Fetch active leagues (use different cache key to avoid conflict)
    leagues = self._execute_query("leagues", "leagues_active", filters={"is_active": True}, bypass_cache=bypass_cache)

    if not leagues:
        logger.warning("No active leagues found in database")
        return []

    # Collect unique country_ids and continent_ids from active leagues
    country_ids = set()
    continent_ids = set()
    for league in leagues:
        country_id = league.get("country_id")
        if country_id:
            country_ids.add(country_id)
        continent_id = league.get("country_id")  # Use country_id to get continent
        # Note: We'll fetch continent info through countries

    # Fetch only the countries and continents needed for active leagues
    # This is much more efficient than fetching all countries/continents
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

    if continents_to_fetch:
        logger.debug(f"Fetching {len(continents_to_fetch)} continents for active leagues")
        continents = self.fetch_continents()
        for continent in continents:
            continent_map[continent["id"]] = continent

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
                "iso_code": country.get("iso_code"),
            },
            "continent": {
                "id": continent["id"],
                "name": continent["name"],
                "active_hours_utc": continent.get("active_hours_utc", []),
            },
        }
        enriched_leagues.append(enriched_league)

    # Cache the enriched result (use different cache key to avoid conflict)
    self._set_cache(cache_key, enriched_leagues)

    logger.info(f"Found {len(enriched_leagues)} active leagues")
    return enriched_leagues
```

```python
def get_active_leagues_for_continent(self, continent_name: str, bypass_cache: bool = False) -> list[dict[str, Any]]:
    """
    Fetch active leagues for a specific continent.

    V12.5: Added bypass_cache parameter for critical operations.

    Args:
        continent_name: Continent name (e.g., "LATAM", "ASIA", "AFRICA")
        bypass_cache: If True, skip cache and fetch fresh data (default: False)

    Returns:
        List of active league records for the continent
    """
    all_active = self.get_active_leagues(bypass_cache=bypass_cache)

    filtered = [
        league
        for league in all_active
        if league.get("continent", {}).get("name") == continent_name
    ]

    logger.info(f"Found {len(filtered)} active leagues for continent {continent_name}")
    return filtered
```

**Rationale:** Bypass cache option allows forcing fresh data fetch for critical operations.

---

### 7. Cache Invalidation Mechanism

**File:** `src/database/supabase_provider.py`

**Change:** Added `invalidate_cache()` and `invalidate_leagues_cache()` methods

```python
def invalidate_cache(self, cache_key: str | None = None) -> None:
    """
    Invalidate cache for a specific key or all cache entries.

    V12.5: Add cache invalidation mechanism for manual cache clearing.

    Args:
        cache_key: Specific cache key to invalidate. If None, clears all cache.
    """
    if self._acquire_cache_lock_with_monitoring(timeout=CACHE_LOCK_TIMEOUT):
        try:
            if cache_key:
                # Invalidate specific cache key
                if cache_key in self._cache:
                    del self._cache[cache_key]
                    del self._cache_timestamps[cache_key]
                    logger.info(f"🗑️ Cache invalidated for key: {cache_key}")
                else:
                    logger.debug(f"Cache key not found: {cache_key}")
            else:
                # Invalidate all cache
                cleared_count = len(self._cache)
                self._cache.clear()
                self._cache_timestamps.clear()
                logger.info(f"🗑️ All cache cleared ({cleared_count} entries)")
        finally:
            self._cache_lock.release()
    else:
        logger.warning("Failed to acquire cache lock for invalidation")

def invalidate_leagues_cache(self) -> None:
    """
    Invalidate all league-related cache entries.

    V12.5: Convenience method to clear league cache when leagues are modified.

    This clears cache for:
    - active_leagues_full
    - leagues table queries
    - countries table queries
    - continents table queries
    """
    league_related_keys = [
        "active_leagues_full",
        "leagues",
        "countries",
        "continents",
    ]

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
            self.invalidate_cache(key)
            cleared_count += 1

    logger.info(f"🗑️ League cache invalidated ({cleared_count} entries)")
```

**Rationale:** Cache invalidation allows manual cache clearing when data is modified.

---

## Testing

### Test 1: Cache Improvements Test

**File:** `test_cache_improvements.py`

**Result:** ✅ PASSED

```
================================================================================
🔍 CACHE IMPROVEMENTS TEST
================================================================================

[1/6] Testing cache TTL configuration...
   SUPABASE_CACHE_TTL_SECONDS: 300
   Expected: 300 (5 minutes)
   ✅ Cache TTL is correctly configured to 5 minutes

[2/6] Importing SupabaseProvider...
   ✅ SupabaseProvider imported successfully
   CACHE_TTL_SECONDS constant: 300
   ✅ CACHE_TTL_SECONDS is correctly set to 300

[3/6] Creating SupabaseProvider instance...
   ✅ SupabaseProvider instance created successfully

[4/6] Testing cache metrics method...
   ✅ get_cache_metrics() method exists
   Metrics: {'hit_count': 0, 'miss_count': 0, 'bypass_count': 0, 'total_requests': 0, 'hit_ratio_percent': 0.0, 'cache_ttl_seconds': 300, 'cached_keys_count': 0}
      ✅ hit_count: 0
      ✅ miss_count: 0
      ✅ bypass_count: 0
      ✅ total_requests: 0
      ✅ hit_ratio_percent: 0.0
      ✅ cache_ttl_seconds: 300
      ✅ cached_keys_count: 0

[5/6] Testing cache invalidation methods...
   ✅ invalidate_cache() method exists
   ✅ invalidate_cache(None) works (clears all cache)
   ✅ invalidate_leagues_cache() method exists

[6/6] Testing bypass_cache parameter...
   Testing get_active_leagues(bypass_cache=True)...
   ✅ get_active_leagues(bypass_cache=True) returned 13 leagues
   ✅ Bypass count tracked: 2

================================================================================
📊 SUMMARY
================================================================================
✅ All cache improvements tests PASSED

Cache improvements implemented:
   ✅ Cache TTL is configurable via SUPABASE_CACHE_TTL_SECONDS environment variable
   ✅ Cache hit/miss logging with detailed information (age, TTL)
   ✅ Cache metrics tracking (hit_count, miss_count, bypass_count, hit_ratio)
   ✅ Bypass cache option for critical operations (bypass_cache parameter)
   ✅ Cache invalidation mechanism (invalidate_cache, invalidate_leagues_cache)

✅ Cache improvements test PASSED
```

### Test 2: Nitter Continent Leagues Test

**File:** `test_nitter_continent_leagues_v2.py`

**Result:** ✅ PASSED

```
================================================================================
📊 ACTIVE LEAGUES BY CONTINENT
================================================================================

✅ AFRICA:
   Active leagues: 4
   Active leagues:
      - Botola Pro 1 (Morocco) (id: 0ca757e7-0aba-4530-8fef-d73437e3469f)
      - Ligue Professionnelle 1 (Algeria) (id: 34bf5f07-8ef0-46ff-9189-97d3f7578efd)
      - Second Division A (Egypt) (id: f20267a6-003a-424a-9706-3f1f4238e027)
      - Ligue Professionnelle 1 (Tunisia) (id: 60c0d42f-09f1-4ace-9b86-638aaa28bdaa)

✅ ASIA:
   Active leagues: 4
   Active leagues:
      - Turkey Super League (Turkey) (id: 0bc57930-a2ab-4bad-81b7-f9a7764534a5)
      - J League (Japan) (id: 423fe13e-a0ca-4618-a2e2-6b8ed1912f76)
      - A-League (Australia) (id: 889b4134-6f2c-4ef4-a016-2e983b07877f)
      - ADNOC Pro League (United Arab Emirates) (id: 69da76b2-c0ae-4617-8ea5-b2abb9616c77)

✅ LATAM:
   Active leagues: 5
   Active leagues:
      - Brazil Série A (Brazil) (id: 48acf624-4442-466d-9604-3bbf2c116d7a)
      - Primera División - Argentina (Argentina) (id: e3224ce0-6536-4bc3-aaef-66045d64e42b)
      - Liga MX (Mexico) (id: 4b6f37db-d1f3-42b5-9495-987ef260fb2f)
      - Primera División - Chile (Chile) (id: b54ad0f1-9bda-43d8-81f0-a7e7657e1ea7)
      - Primera División (Uruguay) (id: 48d022ab-8f81-4b06-a653-4a6deb097b03)

================================================================================
📊 SUMMARY
================================================================================

✅ Continents with active leagues: 3
   - LATAM: 5 active leagues
   - ASIA: 4 active leagues
   - AFRICA: 4 active leagues
✅ All continents have active leagues

✅ Supabase leagues verification PASSED
```

### Test 3: Nitter Cycle Flow Test

**File:** `test_nitter_cycle_flow.py`

**Result:** ✅ PASSED

```
================================================================================
🔍 NITTER CYCLE FLOW TEST (REAL SUPABASE CALLS)
================================================================================

[1/6] Importing SupabaseProvider...
✅ SupabaseProvider imported successfully

[2/6] Getting Supabase instance...
✅ Supabase instance obtained

[3/6] Checking connection status...
   Connected: True
✅ Supabase is connected

[4/6] Testing get_social_sources() (no continent filter)...
✅ Query executed successfully
   Total sources returned: 38
   Sample source: Victorg_Lessa

[5/6] Filtering for active sources...
✅ Filter applied successfully
   Active sources: 38
   Sample active source: Victorg_Lessa

[6/6] Testing get_active_leagues_for_continent()...
   LATAM: 5 active leagues
      Total sources: 7, Active: 7
   ASIA: 4 active leagues
      Total sources: 6, Active: 6
   AFRICA: 4 active leagues
      Total sources: 5, Active: 5

================================================================================
📊 SUMMARY
================================================================================

✅ SUCCESS: Active social sources found
   The nitter cycle should work correctly
   If you still see the warning, check:
   1. Cache expiration (TTL: 5 minutes)
   2. Mirror file data
   3. Logs for other errors

✅ Nitter cycle flow test PASSED
```

### Test 4: Debug Leagues Test

**File:** `test_debug_leagues.py`

**Result:** ✅ PASSED

```
================================================================================
🔍 DEBUG LEAGUES TEST
================================================================================

[1/5] Importing SupabaseProvider...
   ✅ SupabaseProvider imported successfully

[2/5] Getting all active leagues...
   ✅ Got 13 active leagues

[3/5] Grouping leagues by continent...

[4/5] Printing results...

   AFRICA: 4 leagues
      - Botola Pro 1 (Morocco) (id: 0ca757e7-0aba-4530-8fef-d73437e3469f)
      - Ligue Professionnelle 1 (Algeria) (id: 34bf5f07-8ef0-46ff-9189-97d3f7578efd)
      - Second Division A (Egypt) (id: f20267a6-003a-424a-9706-3f1f4238e027)
      - Ligue Professionnelle 1 (Tunisia) (id: 60c0d42f-09f1-4ace-9b86-638aaa28bdaa)

   ASIA: 4 leagues
      - Turkey Super League (Turkey) (id: 0bc57930-a2ab-4bad-81b7-f9a7764534a5)
      - J League (Japan) (id: 423fe13e-a0ca-4618-a2e2-6b8ed1912f76)
      - A-League (Australia) (id: 889b4134-6f2c-4ef4-a016-2e983b07877f)
      - ADNOC Pro League (United Arab Emirates) (id: 69da76b2-c0ae-4617-8ea5-b2abb9616c77)

   LATAM: 5 leagues
      - Brazil Série A (Brazil) (id: 48acf624-4442-466d-9604-3bbf2c116d7a)
      - Primera División - Argentina (Argentina) (id: e3224ce0-6536-4bc3-aaef-66045d64e42b)
      - Liga MX (Mexico) (id: 4b6f37db-d1f3-42b5-9495-987ef260fb2f)
      - Primera División - Chile (Chile) (id: b54ad0f1-9bda-43d8-81f0-a7e7657e1ea7)
      - Primera División (Uruguay) (id: 48d022ab-8f81-4b06-a653-4a6deb097b03)

[5/5] Testing get_active_leagues_for_continent()...
   LATAM: 5 leagues
   ASIA: 4 leagues
   AFRICA: 4 leagues

================================================================================
📊 SUMMARY
================================================================================
   Total active leagues: 13
   Continents with leagues: ['AFRICA', 'ASIA', 'LATAM']
✅ Debug leagues test PASSED
```

---

## Summary of Changes

### Files Modified

1. **`.env.template`**
   - Added `SUPABASE_CACHE_TTL_SECONDS` environment variable

2. **`src/database/supabase_provider.py`**
   - Updated `CACHE_TTL_SECONDS` to read from environment variable
   - Added cache metrics tracking to `__init__` method
   - Added `get_cache_metrics()` method
   - Enhanced `_get_from_cache()` with detailed logging
   - Added `bypass_cache` parameter to `_execute_query()`
   - Added `bypass_cache` parameter to `get_active_leagues()`
   - Added `bypass_cache` parameter to `get_active_leagues_for_continent()`
   - Added `invalidate_cache()` method
   - Added `invalidate_leagues_cache()` method
   - Fixed cache key conflict between raw data and enriched data

### Files Created

1. **`test_cache_improvements.py`**
   - Test script to verify cache improvements

2. **`test_debug_leagues.py`**
   - Debug script to understand league data enrichment

---

## Benefits

1. **Reduced Cache Staleness:** TTL reduced from 1 hour to 5 minutes (configurable)
2. **Improved Observability:** Cache hit/miss logging with detailed information (age, TTL)
3. **Enhanced Monitoring:** Cache metrics tracking (hit_count, miss_count, bypass_count, hit_ratio)
4. **Critical Operations Support:** Bypass cache option for forcing fresh data
5. **Manual Cache Control:** Cache invalidation mechanism for manual cache clearing
6. **Fixed Cache Key Conflict:** Resolved issue where raw data and enriched data used same cache key

---

## Recommendations for VPS Deployment

### Before Deploy

1. ✅ **Set Environment Variable:** Ensure `SUPABASE_CACHE_TTL_SECONDS` is set to `300` in `.env` file
2. ✅ **Monitor Cache Metrics:** Use `get_cache_metrics()` to monitor cache performance
3. ✅ **Use Bypass Cache for Critical Operations:** Use `bypass_cache=True` for operations that require fresh data
4. ✅ **Invalidate Cache When Needed:** Use `invalidate_leagues_cache()` when leagues are modified

### After Deploy

1. ⚠️ **Monitor Cache Hit Ratio:** If hit ratio is too low (< 50%), consider increasing TTL
2. ⚠️ **Monitor Cache Miss Count:** If miss count is too high, consider increasing TTL
3. ⚠️ **Monitor Bypass Count:** If bypass count is too high, consider reducing TTL or implementing automatic cache invalidation
4. ⚠️ **Monitor Cache Lock Contention:** If lock contention is high, consider increasing `CACHE_LOCK_TIMEOUT`

---

## Conclusion

The cache improvements have been successfully implemented and tested. All tests pass, and the cache now provides:

1. ✅ Configurable TTL (default: 5 minutes)
2. ✅ Detailed logging (hit/miss with age information)
3. ✅ Metrics tracking (hit_count, miss_count, bypass_count, hit_ratio)
4. ✅ Bypass cache option for critical operations
5. ✅ Cache invalidation mechanism
6. ✅ Fixed cache key conflict between raw data and enriched data

The system is now ready for production deployment with improved cache behavior and observability.

---

## Verification Status

- ✅ Cache TTL reduction implemented
- ✅ Cache hit/miss logging enhanced
- ✅ Cache metrics tracking added
- ✅ Bypass cache option implemented
- ✅ Cache invalidation mechanism implemented
- ✅ Cache key conflict fixed
- ✅ All tests passed

**Overall Status:** ✅ READY FOR PRODUCTION
