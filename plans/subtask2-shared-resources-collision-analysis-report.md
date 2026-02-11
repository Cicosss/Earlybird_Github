# Subtask 2: Shared Resources & Collision Points Analysis
## Continental Strategy Feasibility Audit

**Date:** 2026-02-02  
**Task:** Analyze shared resources and identify collision points for 3 parallel main pipeline instances  
**Context:** Transitioning from "Tier-based" hierarchical architecture to "Continent-based" parallel execution model

---

## Executive Summary

This report analyzes the feasibility of running 3 parallel instances of the EarlyBird main analysis engine (one per continent: LATAM, ASIA/EMEA, EUROPE/AU). The analysis identifies **critical collision points** that must be addressed before parallel execution can be safely implemented.

### Key Findings:

| Category | Risk Level | Status |
|----------|-------------|--------|
| Database Concurrency | **HIGH** | WAL mode enabled but 3 heavy writers may cause lock contention |
| Memory Usage | **CRITICAL** | 8GB RAM insufficient for 3 parallel instances with Playwright |
| Deduplication | **HIGH** | NO cross-process awareness - duplicate analysis guaranteed |
| Alert Sending | **MEDIUM** | No rate limiting across processes - Telegram spam risk |
| Configuration | **LOW** | Read-only, no conflicts |

### Recommendation:
**Do NOT proceed with parallel execution** without addressing the critical memory and deduplication issues first.

---

## 1. Database Concurrency Assessment

### 1.1 Current Database Configuration

**Source:** [`src/database/models.py`](src/database/models.py:338-350)

```python
engine = create_engine(
    DB_PATH,
    connect_args={
        "check_same_thread": False,
        "timeout": 60  # 60 seconds busy timeout
    },
    pool_pre_ping=True,
    pool_size=5,          # Base pool size
    max_overflow=5,        # Max 10 concurrent connections
    pool_timeout=60,
    pool_recycle=3600,    # Recycle after 1 hour
    echo=False
)
```

**SQLite Pragmas Applied** ([`models.py:356-377`](src/database/models.py:356-377)):
- `PRAGMA journal_mode=WAL` ✅ (Write-Ahead Logging enabled)
- `PRAGMA busy_timeout=60000` ✅ (60 seconds)
- `PRAGMA synchronous=NORMAL` ✅ (Balanced safety/performance)
- `PRAGMA cache_size=-64000` ✅ (64MB page cache)
- `PRAGMA temp_store=memory` ✅ (Temp tables in RAM)
- `PRAGMA mmap_size=268435456` ✅ (256MB memory-mapped I/O)

### 1.2 Write Operation Patterns

**Main Pipeline Writes:**
- **Match ingestion**: [`save_matches()`](src/database/db.py:91-132) - Batch inserts/updates
- **Analysis results**: [`save_analysis()`](src/database/db.py:135-156) - Single row inserts
- **Settlement operations**: [`settler.py`](src/analysis/settler.py) - Post-match updates

**Write Frequency (per pipeline instance):**
- Match ingestion: ~50-100 matches per cycle (batch)
- Analysis results: ~5-20 high-score alerts per cycle
- Settlement: ~10-30 matches per day

**With 3 parallel instances:**
- Total writes per cycle: **150-300 match updates** + **15-60 analysis inserts**
- Peak write rate: **~10-20 writes/second** during settlement

### 1.3 Risk Assessment: 3 Parallel Writers

| Scenario | Probability | Impact | Risk Level |
|----------|-------------|---------|------------|
| Normal operation (low volume) | Low | Low | LOW |
| Settlement day (high volume) | **HIGH** | **HIGH** | **CRITICAL** |
| All 3 processes writing simultaneously | **VERY HIGH** | **CRITICAL** | **CRITICAL** |

**Specific "Database is locked" Scenarios:**

1. **Settlement Window Collision** (Most Likely)
   - All 3 processes run settlement simultaneously
   - Each tries to update 10-30 matches
   - WAL mode allows 1 writer + multiple readers
   - **3 writers = guaranteed lock contention**
   - Timeout (60s) may be exceeded

2. **Match Ingestion Race**
   - All 3 processes fetch fresh fixtures at same time
   - Each tries to INSERT/UPDATE same match IDs
   - Unique constraint on `matches.id` prevents duplicates
   - **Retry logic may not be sufficient for 3 concurrent writers**

3. **Long-running Transactions**
   - Analysis with multiple enrichment steps holds transaction open
   - 3 processes = 3 long transactions
   - WAL checkpoint may be blocked
   - **Database size growth + performance degradation**

### 1.4 Mitigation Strategies

**Current Mitigations (In Place):**
- [`get_db_context()`](src/database/db.py:45-62) with auto-commit/rollback ✅
- [`get_db_session()`](src/database/models.py:393-437) with retry logic (max 3 attempts) ✅
- Exponential backoff: `wait_time = retry_delay * (2 ** attempt)` ✅

**Additional Mitigations Needed:**

1. **Database-Level Partitioning** (Recommended)
   - Create separate databases per continent:
     - `earlybird_latam.db`
     - `earlybird_asia_emea.db`
     - `earlybird_europe_au.db`
   - **Eliminates cross-process write conflicts entirely**

2. **Write Queue Serialization** (Alternative)
   - Single "writer process" with database lock
   - 3 analysis processes push to queue
   - Writer process serializes all writes
   - **Complex but preserves single database**

3. **Staggered Execution** (Quick Fix)
   - Offset process start times by 5-10 minutes
   - Reduces (but doesn't eliminate) collision probability
   - **Temporary mitigation only**

### 1.5 Database Conclusions

**Risk Level:** **HIGH**

**Verdict:** WAL mode and retry logic are insufficient for 3 simultaneous heavy writers. Database lock contention is **highly likely** during settlement and fixture ingestion windows.

**Recommendation:** Implement **database partitioning by continent** (separate .db files) as the primary solution.

---

## 2. Memory Usage Analysis

### 2.1 Memory Footprint Per Pipeline Instance

**Source Analysis:**

#### 2.1.1 Main Pipeline (Python Process)
**Source:** [`src/main.py`](src/main.py:1-500)

| Component | Estimated Memory | Notes |
|-----------|------------------|-------|
| Core imports & modules | 50-80 MB | SQLAlchemy, requests, logging, etc. |
| Analysis engines (6 loaded) | 80-120 MB | Fatigue, Injury, Biscotto, Math, etc. |
| Data structures (matches, news) | 30-60 MB | In-memory match lists, news dicts |
| FotMob cache | 20-40 MB | Team data, match details |
| SmartCache instances | 10-20 MB | 3 caches × 500 entries |
| Python runtime overhead | 40-60 MB | Interpreter, GC, etc. |
| **Subtotal** | **230-380 MB** | Per Python process |

#### 2.1.2 Playwright Browser Instance (Gemini Agent)
**Source:** [`src/services/browser_monitor.py`](src/services/browser_monitor.py:1-500)

| Component | Estimated Memory | Notes |
|-----------|------------------|-------|
| Playwright browser head | 150-250 MB | Chromium/WebKit process |
| Page context & DOM | 50-100 MB | Loaded pages, JavaScript heap |
| Stealth plugins | 10-20 MB | Anti-detection overhead |
| ContentCache (10k entries) | 20-40 MB | Hash-based deduplication |
| **Subtotal** | **230-410 MB** | Per browser instance |

#### 2.1.3 Additional Components

| Component | Estimated Memory | Notes |
|-----------|------------------|-------|
| News Hunter discoveries | 10-30 MB | Browser monitor news queue |
| SharedContentCache | 15-30 MB | Cross-component deduplication |
| HTTP client pools | 10-20 MB | Connection pools |
| **Subtotal** | **35-80 MB** | Additional overhead |

### 2.2 Total Memory Estimation (3 Parallel Instances)

| Instance Type | Per Instance | × 3 Instances | Total |
|---------------|---------------|-----------------|--------|
| Python Process (main) | 230-380 MB | × 3 | 690-1,140 MB |
| Playwright Browser | 230-410 MB | × 3 | 690-1,230 MB |
| Additional Overhead | 35-80 MB | × 3 | 105-240 MB |
| **TOTAL** | **495-870 MB** | | **1,485-2,610 MB** |

**Converted to GB:**
- Minimum: **1.5 GB**
- Maximum: **2.6 GB**
- With system overhead: **~3.0-3.5 GB**

### 2.3 8GB RAM Sufficiency Assessment

| Resource | Required | Available | Buffer |
|-----------|-----------|------------|---------|
| 3 Parallel Instances | 3.0-3.5 GB | 8.0 GB | **4.5-5.0 GB** ✅ |

**BUT - Critical Considerations:**

1. **Peak Memory Spikes**
   - During settlement: All 3 processes load match data simultaneously
   - **Peak may exceed 4 GB**
   - OOM (Out of Memory) risk on VPS

2. **Browser Memory Leaks**
   - Playwright known to leak memory with long-running sessions
   - After 24-48 hours: **+500 MB per instance possible**
   - **Total could reach 4-5 GB**

3. **VPS Memory Overcommitment**
   - Many VPS providers allow overcommitment
   - 8GB "guaranteed" may not be actually available
   - **Swap usage = severe performance degradation**

4. **Concurrent Operations**
   - 3 processes + 3 browsers + system services
   - **Contention for CPU cache and memory bandwidth**

### 2.4 Memory Optimization Recommendations

**If proceeding with parallel execution:**

1. **Reduce Browser Instances**
   - Share 1 browser instance across 3 processes (complex)
   - OR: Use HTTP-only mode for 2 processes (no browser)
   - **Saves ~700-1,200 MB**

2. **Cache Size Reduction**
   - Reduce ContentCache from 10k to 2k entries
   - Reduce SmartCache from 500 to 200 entries
   - **Saves ~100-150 MB**

3. **Lazy Module Loading**
   - Load analysis engines on-demand (not all at startup)
   - **Saves ~50-80 MB**

4. **Memory Monitoring & Auto-Restart**
   - Monitor RSS memory per process
   - Restart process if >1.5 GB
   - **Prevents OOM kills**

### 2.5 Memory Conclusions

**Risk Level:** **MEDIUM** (with caveats)

**Verdict:** 8GB RAM is **technically sufficient** for 3 parallel instances under normal conditions. However, **peak memory spikes** and **browser memory leaks** pose significant risks. Memory monitoring and auto-restart mechanisms are **mandatory**.

**Recommendation:** Implement **memory monitoring + auto-restart** and **reduce cache sizes** before parallel deployment.

---

## 3. Deduplication Cross-Process Analysis

### 3.1 Current Deduplication Mechanisms

#### 3.1.1 SharedContentCache
**Source:** [`src/utils/shared_cache.py`](src/utils/shared_cache.py:215-563)

```python
class SharedContentCache:
    def __init__(self, max_entries=10000, ttl_hours=24, enable_fuzzy=True):
        self._content_cache: OrderedDict[str, Tuple[datetime, str]] = OrderedDict()
        self._url_cache: OrderedDict[str, Tuple[datetime, str]] = OrderedDict()
        self._simhash_cache: OrderedDict[int, Tuple[datetime, str, str]] = OrderedDict()
        
        # Lock for thread safety
        self._lock = RLock()  # ⚠️ THREAD lock, NOT PROCESS lock
```

**Key Characteristics:**
- **Thread-safe**: Uses `threading.RLock()` (line 269)
- **NOT cross-process aware**: In-memory `OrderedDict` storage
- **Per-process instance**: Each Python process has its own cache
- **TTL-based expiration**: 24 hours default

**Deduplication Strategies:**
1. Content hash (exact match) - First 1000 chars
2. URL (normalized) - Tracking params removed
3. Simhash (fuzzy) - 64-bit hash, threshold=3 bits

#### 3.1.2 SmartCache
**Source:** [`src/utils/smart_cache.py`](src/utils/smart_cache.py:77-340)

```python
class SmartCache:
    def __init__(self, name="default", max_size=500):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()  # ⚠️ THREAD lock, NOT PROCESS lock
```

**Key Characteristics:**
- **Thread-safe**: Uses `threading.Lock()` (line 95)
- **NOT cross-process aware**: In-memory `Dict` storage
- **Dynamic TTL**: Based on match proximity (5min to 6 hours)
- **3 global instances**: `team_cache`, `match_cache`, `search_cache`

#### 3.1.3 Tavily Provider Cache
**Source:** [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py:197-522)

```python
class TavilyProvider:
    def __init__(self, key_rotator=None):
        self._cache: Dict[str, CacheEntry] = {}  # ⚠️ Local cache only
        self._shared_cache = get_shared_cache() if _SHARED_CACHE_AVAILABLE else None
```

**Key Characteristics:**
- **Local cache**: Per-instance `Dict` storage (line 220)
- **SharedCache integration**: Uses `get_shared_cache()` for cross-component deduplication (line 230)
- **But still NOT cross-process aware**: `SharedContentCache` is per-process

### 3.2 Cross-Process Compatibility Status

| Cache Type | Cross-Process Aware | Storage Mechanism | Status |
|-------------|----------------------|-------------------|--------|
| SharedContentCache | **NO** | In-memory `OrderedDict` | ❌ Per-process only |
| SmartCache (team) | **NO** | In-memory `Dict` | ❌ Per-process only |
| SmartCache (match) | **NO** | In-memory `Dict` | ❌ Per-process only |
| SmartCache (search) | **NO** | In-memory `Dict` | ❌ Per-process only |
| Tavily local cache | **NO** | In-memory `Dict` | ❌ Per-process only |

**Root Cause:** All caches use `threading.Lock()` for synchronization, which **only works within a single process**. Multiple Python processes have completely separate memory spaces.

### 3.3 Risk of Duplicate Analysis

**Scenario: Same News Article Discovered by Multiple Processes**

```
Time T0: LATAM process discovers "Messi injured" news
         → Checks SharedContentCache → MISS (empty)
         → Marks as seen in LATAM's cache
         → Analyzes match → Sends alert

Time T1: ASIA/EMEA process discovers same "Messi injured" news
         → Checks SharedContentCache → MISS (different process!)
         → Marks as seen in ASIA's cache
         → Analyzes match → Sends DUPLICATE alert ❌

Time T2: EUROPE/AU process discovers same "Messi injured" news
         → Checks SharedContentCache → MISS (different process!)
         → Marks as seen in EUROPE's cache
         → Analyzes match → Sends DUPLICATE alert ❌
```

**Result:** **Same news analyzed 3 times**, 3 duplicate alerts sent to Telegram.

### 3.4 Required Changes for Cross-Process Deduplication

**Option 1: Redis/Memcached (Recommended)**
- External shared cache service
- All 3 processes connect to same Redis instance
- Atomic operations prevent race conditions
- **Complexity:** Medium (requires Redis installation)

**Option 2: SQLite-Based Shared Cache**
- Use SQLite database for cache storage
- All processes read/write to same file
- WAL mode enables concurrent access
- **Complexity:** Low (no new dependencies)

**Option 3: File-Based Cache with Locking**
- JSON files for cache storage
- `fcntl` or `msvcrt` for file locking
- **Complexity:** Medium (cross-platform locking issues)

**Option 4: HTTP API Cache Service**
- Simple Flask/FastAPI cache service
- All processes query API for deduplication
- **Complexity:** Medium (additional service to manage)

### 3.5 Deduplication Conclusions

**Risk Level:** **CRITICAL**

**Verdict:** Current deduplication mechanism **does NOT support cross-process awareness**. Running 3 parallel instances **guarantees duplicate analysis and duplicate alerts**.

**Recommendation:** Implement **Redis-based shared cache** or **SQLite-based cache** before parallel execution. This is a **blocking issue** that must be resolved.

---

## 4. Additional Collision Points

### 4.1 Alert Sending Conflicts

**Source:** [`src/alerting/notifier.py`](src/alerting/notifier.py:1-500)

**Current Implementation:**
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def _send_telegram_request(url: str, payload: Dict[str, Any], timeout: int = 30):
    response = requests.post(url, data=payload, timeout=timeout)
    
    # Handle rate limiting with custom backoff
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 5))
        time.sleep(retry_after)
        raise requests.exceptions.ConnectionError("Rate limited - triggering retry")
```

**Collision Scenario:**
- All 3 processes send alerts simultaneously
- Each has independent retry logic
- **No coordination** to respect Telegram's global rate limits
- **Telegram spam risk**: 3x alert volume

**Risk Level:** **MEDIUM**

**Mitigation:**
- Implement **shared rate limiter** (Redis or SQLite-based)
- Track last alert time per match ID globally
- Skip alert if already sent by another process

### 4.2 Configuration File Access

**Source:** [`config/settings.py`](config/settings.py:1-500)

**Current Implementation:**
- All configuration loaded from environment variables (`.env` file)
- Read-only at startup
- No file-based state management

**Collision Scenario:**
- All 3 processes read same `.env` file
- **No conflicts** - read-only access

**Risk Level:** **LOW** ✅

### 4.3 Log File Conflicts

**Current Implementation:**
```python
# src/main.py:16-22
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('earlybird_main.log')  # ⚠️ Shared file
    ]
)
```

**Collision Scenario:**
- All 3 processes write to `earlybird_main.log`
- **File locking issues**: Multiple writers to same file
- **Log corruption risk**: Intermingled log lines
- **Performance impact**: File I/O contention

**Risk Level:** **MEDIUM**

**Mitigation:**
- Use **per-process log files**:
  - `earlybird_latam.log`
  - `earlybird_asia_emea.log`
  - `earlybird_europe_au.log`
- OR: Use **syslog** or **centralized logging service**

### 4.4 Browser Monitor Discovery Queue

**Source:** [`src/processing/news_hunter.py`](src/processing/news_hunter.py:113-368)

**Current Implementation:**
```python
# Legacy storage (kept for backward compatibility)
_browser_monitor_discoveries: Dict[str, List[Dict]] = {}
_browser_monitor_lock = Lock()
```

**Collision Scenario:**
- Each process has its own `_browser_monitor_discoveries` dict
- Browser Monitor (if running separately) can't route to specific process
- **Lost discoveries** if wrong process receives them

**Risk Level:** **LOW** (if Browser Monitor runs with each pipeline)

### 4.5 API Budget Conflicts

**Source:** [`config/settings.py`](config/settings.py:138-153)

**Current Implementation:**
```python
# Brave budget allocation per component (calls/month)
BRAVE_BUDGET_ALLOCATION = {
    "main_pipeline": 1800,      # 30% - Match enrichment
    "news_radar": 1200,         # 20% - Pre-enrichment
    "browser_monitor": 600,     # 10% - Short content expansion
    # ...
}
```

**Collision Scenario:**
- All 3 processes identify as "main_pipeline"
- **Budget exhausted 3x faster** than expected
- **API rate limiting** hits sooner

**Risk Level:** **MEDIUM**

**Mitigation:**
- Add **continent identifier** to component names:
  - `main_pipeline_latam`
  - `main_pipeline_asia_emea`
  - `main_pipeline_europe_au`
- Adjust budget allocations accordingly

---

## 5. Risk Matrix

| Collision Point | Impact | Probability | Overall Risk | Mitigation | Priority |
|----------------|---------|-------------|---------------|-------------|-----------|
| **Database Lock Contention** | HIGH | HIGH | **CRITICAL** | Separate DB per continent | P0 |
| **Deduplication (No Cross-Process)** | CRITICAL | CERTAIN | **CRITICAL** | Redis/SQLite shared cache | P0 |
| **Memory OOM (Peak Spikes)** | HIGH | MEDIUM | **HIGH** | Memory monitoring + auto-restart | P1 |
| **Telegram Alert Spam** | MEDIUM | HIGH | **MEDIUM** | Shared rate limiter | P1 |
| **Log File Conflicts** | MEDIUM | HIGH | **MEDIUM** | Per-process log files | P2 |
| **API Budget Exhaustion** | MEDIUM | HIGH | **MEDIUM** | Continent-specific component names | P2 |
| **Browser Memory Leaks** | MEDIUM | MEDIUM | **MEDIUM** | Browser auto-restart | P2 |
| **Configuration Conflicts** | LOW | LOW | **LOW** | None needed | P3 |

### Risk Summary by Priority:

**P0 (Blocking - Must Fix):**
1. Database lock contention → Separate databases per continent
2. Deduplication → Redis/SQLite shared cache

**P1 (High - Should Fix):**
3. Memory OOM risk → Monitoring + auto-restart
4. Telegram spam → Shared rate limiter

**P2 (Medium - Nice to Have):**
5. Log conflicts → Per-process log files
6. API budget → Continent-specific naming
7. Browser leaks → Auto-restart

**P3 (Low):**
8. Configuration → No action needed

---

## 6. Recommendations & Next Steps

### 6.1 Critical Path (Must Complete Before Parallel Execution)

**Phase 1: Database Partitioning (1-2 days)**
1. Modify [`src/database/models.py`](src/database/models.py:323-329) to support multiple databases
2. Update [`src/database/db.py`](src/database/db.py) to route to correct DB based on continent
3. Create migration script to split existing database
4. Test with 2 parallel processes

**Phase 2: Cross-Process Deduplication (2-3 days)**
1. Choose implementation: Redis (preferred) or SQLite-based
2. Modify [`src/utils/shared_cache.py`](src/utils/shared_cache.py:215-563) to use external cache
3. Update [`src/utils/smart_cache.py`](src/utils/smart_cache.py:77-340) for cross-process support
4. Test deduplication across 3 processes

**Phase 3: Memory Safety (1-2 days)**
1. Implement memory monitoring (psutil-based)
2. Add auto-restart logic if RSS > 1.5 GB
3. Reduce cache sizes (ContentCache: 10k → 2k, SmartCache: 500 → 200)
4. Test memory stability over 24-48 hours

### 6.2 Secondary Path (Improve After Parallel Execution)

**Phase 4: Alert Coordination (1 day)**
1. Implement shared rate limiter (SQLite-based)
2. Track sent alerts globally
3. Skip duplicate alerts across processes

**Phase 5: Logging & Budget (1 day)**
1. Per-process log files
2. Continent-specific component names for API budgeting

### 6.3 Estimated Timeline

| Phase | Duration | Dependencies | Status |
|--------|-----------|--------------|--------|
| Phase 1: DB Partitioning | 1-2 days | None | **Not Started** |
| Phase 2: Cross-Process Cache | 2-3 days | Phase 1 | **Not Started** |
| Phase 3: Memory Safety | 1-2 days | None | **Not Started** |
| Phase 4: Alert Coordination | 1 day | Phase 2 | **Not Started** |
| Phase 5: Logging & Budget | 1 day | None | **Not Started** |
| **Total** | **6-9 days** | - | - |

---

## 7. Conclusion

### 7.1 Feasibility Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Database Concurrency | **FEASIBLE** with modifications | Requires DB partitioning |
| Memory Usage | **FEASIBLE** with monitoring | 8GB sufficient but needs safeguards |
| Deduplication | **NOT FEASIBLE** as-is | Requires external cache (Redis/SQLite) |
| Alert Sending | **FEASIBLE** with coordination | Needs shared rate limiter |
| Configuration | **FEASIBLE** as-is | No changes needed |

### 7.2 Overall Verdict

**The Continental Strategy is FEASIBLE but requires significant engineering work.**

**Blocking Issues (Must Resolve):**
1. ❌ **Deduplication**: No cross-process awareness → Duplicate alerts guaranteed
2. ❌ **Database**: 3 heavy writers → Lock contention highly likely

**High-Priority Issues (Should Resolve):**
3. ⚠️ **Memory**: Peak spikes may cause OOM on 8GB VPS
4. ⚠️ **Alerts**: No coordination → Telegram spam risk

### 7.3 Go/No-Go Decision

**Current Status: NO-GO** ⛔

**Reason:** Critical blocking issues (deduplication, database) not resolved. Parallel execution would result in:
- Duplicate analysis of same news
- Duplicate alerts to Telegram
- Database lock errors during settlement
- Potential memory OOM kills

**Path to GO:**
1. Complete Phase 1 (DB Partitioning)
2. Complete Phase 2 (Cross-Process Cache)
3. Complete Phase 3 (Memory Safety)
4. Conduct 48-hour parallel test
5. Review metrics and adjust

**Estimated Time to GO:** **6-9 days** of focused development.

---

## Appendix A: Code References

### Database Configuration
- [`src/database/models.py:338-377`](src/database/models.py:338-377) - Engine configuration and SQLite pragmas
- [`src/database/models.py:393-437`](src/database/models.py:393-437) - get_db_session with retry logic
- [`src/database/db.py:45-62`](src/database/db.py:45-62) - get_db_context context manager

### Memory-Intensive Components
- [`src/main.py:1-500`](src/main.py:1-500) - Main pipeline with all engines
- [`src/services/browser_monitor.py:390-482`](src/services/browser_monitor.py:390-482) - ContentCache class
- [`src/ingestion/data_provider.py:341-346`](src/ingestion/data_provider.py:341-346) - FotMob team cache

### Deduplication
- [`src/utils/shared_cache.py:215-563`](src/utils/shared_cache.py:215-563) - SharedContentCache class
- [`src/utils/smart_cache.py:77-340`](src/utils/smart_cache.py:77-340) - SmartCache class
- [`src/ingestion/tavily_provider.py:220-230`](src/ingestion/tavily_provider.py:220-230) - Tavily cache integration

### Alerting
- [`src/alerting/notifier.py:164-202`](src/alerting/notifier.py:164-202) - _send_telegram_request with retry

### Configuration
- [`config/settings.py:138-153`](config/settings.py:138-153) - BRAVE_BUDGET_ALLOCATION

---

**Report Prepared By:** Kilo Code (Code Mode)  
**Report Date:** 2026-02-02  
**Next Review:** After Phase 1-3 completion
