# Subtask 3: API Quota & Throttling Analysis Report

**Date:** 2026-02-02  
**Task:** Continental Strategy Feasibility Audit - Subtask 3  
**Scope:** Analyze how 3 parallel sessions would share API quotas and whether a centralized "Quota Manager" is needed

---

## Executive Summary

This report analyzes the API quota management mechanisms across EarlyBird's external APIs (Odds API, Tavily, Brave, MediaStack, Perplexity) and evaluates their compatibility with a continent-based parallel execution model.

**Key Finding:** **ALL current quota tracking mechanisms are PER-PROCESS singletons**. They are NOT cross-process compatible, which means 3 parallel continent-based sessions would independently track quotas and could collectively exhaust the monthly limits without coordination.

**Recommendation:** A **centralized Quota Manager is REQUIRED** for the continental migration to succeed.

---

## 1. Odds API Quota Analysis

### 1.1 Current API Call Patterns

| Component | File | Function | Calls per Run | Frequency |
|-----------|-------|-----------|---------------|------------|
| Fixture Ingestion | [`ingest_fixtures.py:500`](src/ingestion/ingest_fixtures.py:500) | `ingest_fixtures()` | ~10-15 leagues × 1 call | Every cycle (~1h) |
| League Discovery | [`league_manager.py:150`](src/ingestion/league_manager.py:150) | `fetch_all_sports()` | 1 call (FREE endpoint) | On startup |
| Odds Capture | [`odds_capture.py:31`](src/services/odds_capture.py:31) | `capture_kickoff_odds()` | 1-5 matches × 1 call | Every 5 min |
| Quota Check | [`ingest_fixtures.py:463`](src/ingestion/ingest_fixtures.py:463) | `check_quota_status()` | 1 call | Periodic |

**Estimated API Calls per Day (Single Session):**
- Fixture ingestion: 24 cycles × 10 leagues = ~240 calls
- Odds capture: 288 cycles (5min) × 3 matches = ~864 calls
- Total: **~1,100 calls/day**

**Estimated API Calls per Day (3 Parallel Sessions):**
- Total: **~3,300 calls/day**

### 1.2 Quota Exhaustion Risk Assessment

| Metric | Value | Risk Level |
|--------|--------|------------|
| Monthly Quota | 20,000 credits | - |
| Daily Usage (1 session) | ~1,100 calls | Low (5.5% of monthly) |
| Daily Usage (3 sessions) | ~3,300 calls | Medium (16.5% of monthly) |
| Monthly Usage (3 sessions) | ~99,000 calls | **CRITICAL** (495% of quota) |

**Risk Level:** **HIGH** - 3 parallel sessions would exceed the 20,000 credit limit by 5x within 6 days.

### 1.3 Current Quota Tracking Mechanism

**Implementation:** [`check_quota_status()`](src/ingestion/ingest_fixtures.py:463)

```python
def check_quota_status() -> Dict[str, Any]:
    """Check current API quota from response headers."""
    response = _get_session().get(url, params=params, timeout=10)
    remaining = response.headers.get("x-requests-remaining", "500")
    return {
        "remaining": remaining_int,
        "used": response.headers.get("x-requests-used", "0"),
        "emergency_mode": remaining_int < 50
    }
```

**Key Characteristics:**
- **Per-process:** Each process independently checks quota via API headers
- **No shared state:** No coordination between processes
- **No enforcement:** Only reports status, doesn't block calls

**Cross-Process Compatibility:** **NOT COMPATIBLE**

### 1.4 Smart Frequency Optimization

The system implements intelligent frequency control based on match proximity ([`should_update_league()`](src/ingestion/ingest_fixtures.py:98)):

- **Match < 24h away:** Update every 1 hour (HIGH ALERT)
- **Match > 24h away:** Update every 6 hours (MAINTENANCE)
- **No matches:** Skip (discovery mode)

This optimization reduces API calls but is **not sufficient** for 3 parallel sessions.

---

## 2. Tavily API Quota Analysis

### 2.1 Current API Call Patterns

| Component | File | Function | Calls per Run | Frequency |
|-----------|-------|-----------|---------------|------------|
| Main Pipeline | [`tavily_provider.py:353`](src/ingestion/tavily_provider.py:353) | `search()` | 5-10 calls | Per match |
| News Radar | [`tavily_provider.py:353`](src/ingestion/tavily_provider.py:353) | `search()` | 2-5 calls | Per news item |
| Browser Monitor | [`tavily_provider.py:353`](src/ingestion/tavily_provider.py:353) | `search()` | 1-3 calls | Per short content |
| Telegram Monitor | [`tavily_provider.py:353`](src/ingestion/tavily_provider.py:353) | `search()` | 1-2 calls | Per intel |

**Estimated API Calls per Day (Single Session):**
- Main pipeline: 10 matches × 5 calls = ~50 calls
- News radar: 20 news × 3 calls = ~60 calls
- Browser monitor: 10 items × 2 calls = ~20 calls
- Total: **~130 calls/day**

**Estimated API Calls per Day (3 Parallel Sessions):**
- Total: **~390 calls/day**

### 2.2 Quota Exhaustion Risk Assessment

| Metric | Value | Risk Level |
|--------|--------|------------|
| Monthly Quota | 7,000 calls | - |
| Daily Usage (1 session) | ~130 calls | Low (1.9% of monthly) |
| Daily Usage (3 sessions) | ~390 calls | Medium (5.6% of monthly) |
| Monthly Usage (3 sessions) | ~11,700 calls | **HIGH** (167% of quota) |

**Risk Level:** **HIGH** - 3 parallel sessions would exceed the 7,000 call limit within 18 days.

### 2.3 Current Quota Tracking Mechanism

**Implementation:** [`TavilyBudget`](src/ingestion/tavily_budget.py:38) + [`TavilyKeyRotator`](src/ingestion/tavily_key_rotator.py:19)

**Budget Tracking:**
```python
class BudgetManager:
    def __init__(self):
        self._monthly_limit = monthly_limit  # 7000
        self._monthly_used = 0
        self._component_usage: Dict[str, int] = {...}
```

**Key Rotation:**
```python
class TavilyKeyRotator:
    def __init__(self, keys):
        self._keys: List[str] = keys  # 7 keys
        self._current_index: int = 0
        self._key_usage: Dict[int, int] = {i: 0 for i in range(len(keys))}
        self._exhausted_keys: Set[int] = set()
```

**Key Characteristics:**
- **Singleton pattern:** One instance per process ([`get_budget_manager()`](src/ingestion/tavily_budget.py:257))
- **Per-process state:** Each process tracks usage independently
- **Key rotation:** Automatic rotation on 429/432 errors
- **Double cycle support:** V8.0 allows 2 full cycles per month ([`tavily_key_rotator.py:109`](src/ingestion/tavily_key_rotator.py:109))

**Cross-Process Compatibility:** **NOT COMPATIBLE**

### 2.4 Tiered Throttling

The system implements tiered throttling based on usage thresholds ([`can_call()`](src/ingestion/tavily_budget.py:82)):

| Mode | Threshold | Behavior |
|------|-----------|-----------|
| Normal | < 90% | Full functionality |
| Degraded | 90-95% | Non-critical calls throttled 50% |
| Disabled | > 95% | Only critical calls allowed |

**Critical Components:** `main_pipeline`, `settlement_clv`

---

## 3. Other API Quotas Summary

### 3.1 Brave API Quota Management

| Attribute | Value |
|-----------|--------|
| Monthly Quota | 6,000 calls (3 keys × 2,000) |
| Rate Limit | 1 request/2 seconds |
| Budget Tracking | [`BraveBudget`](src/ingestion/brave_budget.py:38) (singleton) |
| Key Rotation | [`BraveKeyRotator`](src/ingestion/brave_key_rotator.py) (singleton) |
| Cross-Process Compatible | **NO** |

**Budget Allocation ([`settings.py:139`](config/settings.py:139)):**
```python
BRAVE_BUDGET_ALLOCATION = {
    "main_pipeline": 1800,      # 30%
    "news_radar": 1200,         # 20%
    "browser_monitor": 600,     # 10%
    "telegram_monitor": 300,    # 5%
    "settlement_clv": 150,      # 2.5%
    "twitter_recovery": 1950,   # 32.5%
}
```

### 3.2 MediaStack API Quota Management

| Attribute | Value |
|-----------|--------|
| Monthly Quota | **UNLIMITED** (free tier) |
| Rate Limit | 1 request/second (self-imposed) |
| Budget Tracking | [`MediaStackBudget`](src/ingestion/mediastack_budget.py:36) (monitoring only) |
| Key Rotation | [`MediaStackKeyRotator`](src/ingestion/mediastack_key_rotator.py) (4 keys) |
| Cross-Process Compatible | **NO** (but not critical due to unlimited quota) |

**Note:** MediaStack is free unlimited tier, so quota starvation is not a concern.

### 3.3 Perplexity API Quota Management

| Attribute | Value |
|-----------|--------|
| Monthly Quota | **NOT TRACKED** |
| Rate Limit | None specified |
| Budget Tracking | **NONE** |
| Key Rotation | **NONE** |
| Cross-Process Compatible | **N/A** |

**Note:** Perplexity is used as a fallback for DeepSeek. No quota tracking is implemented.

---

## 4. Rate Limiting and Throttling Analysis

### 4.1 HTTP Client Rate Limiting

**Implementation:** [`EarlyBirdHTTPClient`](src/utils/http_client.py:169) with [`RateLimiter`](src/utils/http_client.py:68)

**Rate Limit Configurations ([`settings.py:151`](config/settings.py:151)):**
```python
RATE_LIMIT_CONFIGS: Dict[str, Dict] = {
    "duckduckgo": {"min_interval": 1.0, "jitter_min": 1.0, "jitter_max": 2.0},
    "brave": {"min_interval": 2.0, "jitter_min": 0.0, "jitter_max": 0.0},
    "serper": {"min_interval": 0.3, "jitter_min": 0.0, "jitter_max": 0.0},
    "fotmob": {"min_interval": 1.0, "jitter_min": 0.0, "jitter_max": 0.0},
    "default": {"min_interval": 1.0, "jitter_min": 0.0, "jitter_max": 0.0},
}
```

**Key Characteristics:**
- **Singleton pattern:** One rate limiter per domain per process
- **Per-process state:** Each process maintains independent rate limiting
- **Thread-safe:** Uses `threading.Lock` for sync operations
- **Async support:** Uses `asyncio.Lock` for async operations

**Cross-Process Compatibility:** **NOT COMPATIBLE** - Rate limiting is per-process, not shared across processes.

### 4.2 Retry Logic

**Implementation:** [`get_sync()`](src/utils/http_client.py:354) with exponential backoff

**Retry Status Codes:** {429, 502, 503, 504}

**Backoff Calculation ([`_calculate_backoff()`](src/utils/http_client.py:350)):**
```python
def _calculate_backoff(self, attempt: int) -> float:
    return min(2 ** attempt, 30)  # Cap at 30 seconds
```

**Max Retries:** 3 (configurable)

---

## 5. Quota Manager Requirements

### 5.1 Current State Analysis

| API Provider | Quota Tracking | Key Rotation | Cross-Process Compatible | Starvation Risk |
|--------------|----------------|--------------|-------------------------|-----------------|
| Odds API | Per-process (headers) | No | **NO** | **HIGH** |
| Tavily | Per-process (singleton) | Yes (7 keys) | **NO** | **HIGH** |
| Brave | Per-process (singleton) | Yes (3 keys) | **NO** | **MEDIUM** |
| MediaStack | Per-process (monitoring) | Yes (4 keys) | **NO** | **LOW** (unlimited) |
| Perplexity | **NONE** | No | **N/A** | **UNKNOWN** |

### 5.2 Centralized Quota Manager Requirements

#### 5.2.1 What Needs to Be Tracked

| Metric | Granularity | Storage |
|--------|-------------|---------|
| API calls per provider | Per provider (Odds, Tavily, Brave, etc.) | Shared cache |
| API calls per continent | Per continent (Europe, Americas, Asia-Pacific) | Shared cache |
| API calls per component | Per component (main_pipeline, news_radar, etc.) | Shared cache |
| Key usage | Per key index | Shared cache |
| Daily/monthly counters | Per time period | Shared cache |

#### 5.2.2 Quota Allocation Strategy

**Option 1: Fair Share (Equal Allocation)**
- Each continent gets 1/3 of quota
- Simple to implement
- May not match actual usage patterns

**Option 2: Priority-Based Allocation**
- Priority order: Europe > Americas > Asia-Pacific
- Europe gets 40%, Americas 35%, Asia-Pacific 25%
- Reflects current league distribution
- More complex to implement

**Option 3: Dynamic Allocation**
- Allocate based on real-time demand
- Reclaim unused quota from idle continents
- Most complex but most efficient

**Recommendation:** Start with **Priority-Based** (Option 2) and evolve to **Dynamic** (Option 3) based on operational data.

#### 5.2.3 Starvation Prevention Mechanisms

1. **Minimum Guarantee:** Each continent gets minimum 20% of quota
2. **Borrowing:** Idle continents can lend quota to active continents
3. **Reclaiming:** When borrower becomes idle, reclaim unused quota
4. **Emergency Mode:** If all continents exceed quota, only critical calls allowed

#### 5.2.4 Quota Exhaustion Handling

| Scenario | Behavior |
|----------|----------|
| Single continent exhausted | Borrow from other continents |
| All continents exhausted | Emergency mode (critical only) |
| Monthly quota exhausted | Fallback to free APIs (MediaStack, DDG) |
| API returns 429 | Rotate key and retry |

### 5.3 Architecture Recommendations

#### 5.3.1 Shared State Backend

**Option 1: SQLite (Recommended for VPS)**
- Pros: No additional dependencies, file-based, ACID transactions
- Cons: Slower than Redis, file locking issues
- Use case: Low-to-medium traffic (3 sessions)

**Option 2: Redis (Recommended for production)**
- Pros: Fast, atomic operations, pub/sub support
- Cons: Additional dependency, requires Redis server
- Use case: High traffic (10+ sessions)

**Recommendation:** Start with **SQLite** for VPS deployment, migrate to **Redis** for production scaling.

#### 5.3.2 Quota Manager Interface

```python
class QuotaManager:
    def can_call(self, provider: str, continent: str, component: str) -> bool:
        """Check if component can make API call."""
        
    def record_call(self, provider: str, continent: str, component: str) -> None:
        """Record API call."""
        
    def get_status(self, provider: str) -> QuotaStatus:
        """Get quota status for provider."""
        
    def get_continent_status(self, continent: str) -> ContinentStatus:
        """Get quota status for continent."""
        
    def emergency_mode(self, provider: str) -> bool:
        """Check if provider is in emergency mode."""
```

#### 5.3.3 Integration Points

| Component | Current Implementation | Required Change |
|-----------|---------------------|------------------|
| Odds API | [`check_quota_status()`](src/ingestion/ingest_fixtures.py:463) | Use QuotaManager.can_call() |
| Tavily | [`TavilyBudget.can_call()`](src/ingestion/tavily_budget.py:82) | Use QuotaManager.can_call() |
| Brave | [`BraveBudget.can_call()`](src/ingestion/brave_budget.py:82) | Use QuotaManager.can_call() |
| HTTP Client | [`RateLimiter`](src/utils/http_client.py:68) | Use QuotaManager for cross-process rate limiting |

---

## 6. Risk Matrix

| API Provider | Risk | Impact | Probability | Mitigation |
|--------------|-------|---------|-------------|------------|
| **Odds API** | Quota exhaustion (5x overage) | CRITICAL | HIGH | Centralized Quota Manager, fair share allocation |
| **Tavily** | Quota exhaustion (1.67x overage) | HIGH | HIGH | Centralized Quota Manager, dynamic allocation |
| **Brave** | Quota exhaustion (1.5x overage) | MEDIUM | MEDIUM | Centralized Quota Manager, priority allocation |
| **MediaStack** | Rate limit violations | LOW | LOW | Self-imposed rate limiting is sufficient |
| **Perplexity** | Untracked quota usage | UNKNOWN | UNKNOWN | Implement quota tracking (fallback only) |
| **HTTP Client** | Cross-process rate limit violations | MEDIUM | MEDIUM | Centralized rate limiting via Quota Manager |

---

## 7. Recommendations

### 7.1 Centralized Quota Manager: **REQUIRED**

**Rationale:**
1. All current quota tracking mechanisms are per-process singletons
2. 3 parallel sessions would independently track and exhaust quotas
3. No coordination mechanism exists to prevent quota starvation
4. Odds API would be exhausted within 6 days (5x overage)

### 7.2 Implementation Approach

#### Phase 1: SQLite-Based Quota Manager (VPS Deployment)
1. Create `src/utils/quota_manager.py` with SQLite backend
2. Implement `can_call()`, `record_call()`, `get_status()` methods
3. Modify [`ingest_fixtures.py`](src/ingestion/ingest_fixtures.py:500) to use QuotaManager
4. Modify [`tavily_provider.py`](src/ingestion/tavily_provider.py:353) to use QuotaManager
5. Modify [`brave_provider.py`](src/ingestion/brave_provider.py:79) to use QuotaManager
6. Add continent parameter to all API calls
7. Implement priority-based allocation (Europe 40%, Americas 35%, Asia-Pacific 25%)

#### Phase 2: Redis-Based Quota Manager (Production Scaling)
1. Migrate SQLite backend to Redis
2. Implement atomic operations for thread safety
3. Add pub/sub for real-time quota notifications
4. Implement dynamic allocation based on demand
5. Add quota borrowing/reclaiming mechanism

#### Phase 3: Advanced Features
1. Machine learning-based quota prediction
2. Automatic quota reallocation
3. Multi-region quota management
4. Cost optimization algorithms

### 7.3 Alternative Approaches (If Quota Manager Not Implemented)

**Option 1: Sequential Execution (Not Recommended)**
- Run continents sequentially (Europe → Americas → Asia-Pacific)
- Eliminates quota collision but reduces throughput
- Defeats purpose of parallel execution

**Option 2: Reduced Frequency (Not Recommended)**
- Reduce API call frequency to 1/3 of current
- Reduces quota usage but increases latency
- Degrades system responsiveness

**Option 3: Per-Continent API Keys (Recommended as Temporary Mitigation)**
- Allocate separate API keys per continent
- Requires 3x API key inventory
- Increases cost but provides isolation
- **This is the ONLY viable alternative without Quota Manager**

---

## 8. Conclusion

### 8.1 Summary of Findings

1. **Odds API:** HIGH risk - 3 sessions would exceed 20,000 quota by 5x within 6 days
2. **Tavily:** HIGH risk - 3 sessions would exceed 7,000 quota by 1.67x within 18 days
3. **Brave:** MEDIUM risk - 3 sessions would exceed 6,000 quota by 1.5x within 20 days
4. **MediaStack:** LOW risk - Unlimited quota, rate limiting is sufficient
5. **Perplexity:** UNKNOWN risk - No quota tracking implemented

### 8.2 Critical Blocking Issues

1. **No Cross-Process Quota Tracking:** All quota tracking is per-process
2. **No Centralized Rate Limiting:** HTTP client rate limiting is per-process
3. **No Starvation Prevention:** No mechanism to prevent one continent from exhausting shared quota
4. **No Quota Exhaustion Handling:** No coordinated response to quota exhaustion

### 8.3 Final Recommendation

**A centralized Quota Manager is REQUIRED** for the continental migration to succeed. Without it, 3 parallel sessions will exhaust API quotas within days, causing system failure.

**Implementation Priority:**
1. **P0:** SQLite-based Quota Manager (Phase 1)
2. **P1:** Continent-aware API calls
3. **P2:** Priority-based quota allocation
4. **P3:** Redis-based Quota Manager (Phase 2)
5. **P4:** Dynamic allocation and borrowing (Phase 3)

**Temporary Mitigation:** Allocate separate API keys per continent (3x inventory) until Quota Manager is implemented.

---

## Appendix: Code References

| File | Line | Description |
|------|------|-------------|
| [`src/ingestion/ingest_fixtures.py`](src/ingestion/ingest_fixtures.py) | 463 | Odds API quota check |
| [`src/ingestion/ingest_fixtures.py`](src/ingestion/ingest_fixtures.py) | 500 | Main fixture ingestion |
| [`src/ingestion/league_manager.py`](src/ingestion/league_manager.py) | 150 | League discovery (FREE) |
| [`src/services/odds_capture.py`](src/services/odds_capture.py) | 31 | Odds capture at kickoff |
| [`src/ingestion/tavily_provider.py`](src/ingestion/tavily_provider.py) | 353 | Tavily search with caching |
| [`src/ingestion/tavily_budget.py`](src/ingestion/tavily_budget.py) | 82 | Tavily budget check |
| [`src/ingestion/tavily_key_rotator.py`](src/ingestion/tavily_key_rotator.py) | 58 | Tavily key rotation |
| [`src/ingestion/brave_provider.py`](src/ingestion/brave_provider.py) | 79 | Brave search |
| [`src/ingestion/brave_budget.py`](src/ingestion/brave_budget.py) | 82 | Brave budget check |
| [`src/ingestion/mediastack_provider.py`](src/ingestion/mediastack_provider.py) | 463 | MediaStack search |
| [`src/ingestion/mediastack_budget.py`](src/ingestion/mediastack_budget.py) | 74 | MediaStack budget check |
| [`src/ingestion/perplexity_provider.py`](src/ingestion/perplexity_provider.py) | 82 | Perplexity deep dive |
| [`src/utils/http_client.py`](src/utils/http_client.py) | 68 | Rate limiter implementation |
| [`src/utils/http_client.py`](src/utils/http_client.py) | 169 | HTTP client singleton |
| [`config/settings.py`](config/settings.py) | 139 | Brave budget allocation |
| [`config/settings.py`](config/settings.py) | 490 | Tavily budget allocation |

---

**Report Generated:** 2026-02-02T21:45:00Z  
**Next Subtask:** Subtask 4 - Continental Execution Model Design
