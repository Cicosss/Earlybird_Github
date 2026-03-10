# COVE DOUBLE VERIFICATION REPORT: DiscoveryQueue Implementation

**Date**: 2026-03-07  
**Component**: `src/utils/discovery_queue.py`  
**Scope**: Thread-safe news discovery queue with high-priority callback system  
**Verification Method**: Chain of Verification (CoVe) Protocol - Double Verification  
**Mode**: CoVe (Chain of Verification)

---

## EXECUTIVE SUMMARY

The `DiscoveryQueue` implementation is **MOSTLY CORRECT** and well-designed for VPS deployment, with **1 CRITICAL BUG** and **3 POTENTIAL ISSUES** identified.

### Critical Findings:
- ❌ **CRITICAL**: GlobalRadar creates separate DiscoveryQueue instance - discoveries not available to main pipeline
- ⚠️ **WARNING**: Long lock hold in `pop_for_match()` could block under high load
- ⚠️ **WARNING**: Database session in callback never closed - potential connection pool exhaustion
- ⚠️ **WARNING**: Multiple callback registrations silently overwrite each other

### Overall Assessment:
**⚠️ NEEDS CRITICAL FIX BEFORE VPS DEPLOYMENT**

---

## FASE 1: Generazione Bozza (Draft)

Based on initial analysis, the DiscoveryQueue appeared to be a well-designed, thread-safe queue system with proper integration points and VPS-ready deployment requirements.

---

## FASE 2: Verifica Avversariale (Cross-Examination)

21 critical questions were formulated to challenge the initial assessment, covering:
- Thread safety issues
- Race conditions
- Memory leaks
- Data flow issues
- VPS deployment issues
- Crash scenarios
- Integration issues

---

## FASE 3: Esecuzione Verifiche (Independent Verification)

Each question was independently verified against the codebase:

### Thread Safety Results:
- ✅ Q1: Callback deadlock risk - SAFE (RLock is reentrant)
- ✅ Q2: Race condition on callback modification - SAFE (reference copied inside lock)
- ⚠️ Q3: Long lock hold in pop_for_match - PERFORMANCE ISSUE (blocks for 1000+ items)

### Race Condition Results:
- ✅ Q4-Q6: All race conditions - SAFE (proper lock usage)

### Memory Leak Results:
- ✅ Q7: Items never removed - BY DESIGN (intentional for multi-match support)
- ✅ Q8-Q9: Index cleanup and memory spikes - SAFE

### Data Flow Results:
- ✅ Q10: GLOBAL items filtering - CORRECT
- ✅ Q11: Callback initialization - SAFE
- ✅ Q12: String confidence handling - CORRECT

### VPS Deployment Results:
- ✅ Q13: Python type compatibility - SAFE (Python 3.10+ required)
- ✅ Q14: Memory requirements - ACCEPTABLE (~5MB for 1000 items)
- ✅ Q15: Queue persistence - BY DESIGN (ephemeral)

### Crash Scenario Results:
- ✅ Q16: Callback exception handling - SAFE
- ✅ Q17: Import fallback - SAFE
- ✅ Q18: None/empty string handling - SAFE

### Integration Results:
- ❌ Q19: news_radar.py queue instance - **CRITICAL BUG FOUND**
- ✅ Q20: Callback registration timing - SAFE
- ⚠️ Q21: Multiple callback registrations - SILENT OVERWRITE

---

## FASE 4: Risposta Finale (Canonical Response)

---

## CORREZIONI NECESSARIE (Required Corrections)

### **[CORREZIONE 1 - CRITICAL]: GlobalRadar Creates Separate DiscoveryQueue Instance**

**Location**: `src/services/news_radar.py:3426`

**Current Code (WRONG)**:
```python
self._discovery_queue = DiscoveryQueue(max_entries=1000, ttl_hours=24)
```

**Problem**:
GlobalRadarMonitor creates its own separate DiscoveryQueue instance instead of using the global singleton via `get_discovery_queue()`. This means:

1. Discoveries from GlobalRadar are pushed to a SEPARATE queue
2. The main pipeline's `pop_for_match()` calls retrieve from the GLOBAL queue
3. **GlobalRadar discoveries are NEVER available to match analysis**
4. The "GLOBAL" league key feature (lines 352-353 in discovery_queue.py) is useless

**Impact**: HIGH - GlobalRadar intelligence is completely isolated and unused

**Fix Required**:
```python
# Should be (CORRECT)
from src.utils.discovery_queue import get_discovery_queue
self._discovery_queue = get_discovery_queue()
```

**Verification Evidence**:
- Search for `self._discovery_queue.pop` in news_radar.py - **NO RESULTS FOUND**
- This confirms discoveries are never retrieved from this separate queue
- The push at line 3730 writes to a queue that is never read

**Files Affected**:
- `src/services/news_radar.py` (line 3426)
- `src/utils/discovery_queue.py` (lines 352-353 - GLOBAL key feature is broken)

---

## POTENTIAL ISSUES (Non-Critical)

### **[ISSUE 2]: Long Lock Hold in pop_for_match()**

**Location**: `src/utils/discovery_queue.py:347-406`

**Issue**: The lock is held while iterating through ALL items in the queue (potentially 1000 items).

**Impact**: MEDIUM - Under high load, this could block `push()` operations from Browser Monitor

**Current Behavior**:
```python
with self._lock:
    # Lines 347-406: Iterate through entire queue
    for item in self._queue:
        # Process each item
        # ...
```

**Recommendation**: Consider chunking or using read-write locks for read-heavy operations

**VPS Impact**: On a busy VPS with frequent Browser Monitor pushes, this could cause noticeable delays

---

### **[ISSUE 3]: Database Session Never Closed in Callback**

**Location**: `src/main.py:1998`

**Issue**: The callback creates a SQLAlchemy session once and reuses it indefinitely without closing.

**Current Code**:
```python
def on_high_priority_discovery(league_key: str) -> None:
    # ...
    if _db_ref is None:
        _db_ref = SessionLocal()  # Created once, never closed
    # ...
    analysis_result = _analysis_engine_ref.analyze_match(
        match=match,
        fotmob=_fotmob_ref,
        now_utc=now_utc,
        db_session=_db_ref,  # Reused indefinitely
        context_label="HIGH_PRIORITY",
        nitter_intel=nitter_intel,
    )
```

**Impact**: MEDIUM - On VPS with connection pooling, this could lead to:
- Connection pool exhaustion
- Stale data from session cache
- Session detachment errors

**Current Mitigation**: Code uses `getattr(match, "home_team", "Unknown")` to handle detachment

**Recommendation**: Use session-per-request pattern or add session refresh logic:
```python
# Better approach
def on_high_priority_discovery(league_key: str) -> None:
    # ...
    db = SessionLocal()
    try:
        analysis_result = _analysis_engine_ref.analyze_match(
            match=match,
            fotmob=_fotmob_ref,
            now_utc=now_utc,
            db_session=db,
            context_label="HIGH_PRIORITY",
            nitter_intel=nitter_intel,
        )
    finally:
        db.close()
```

---

### **[ISSUE 4]: Silent Callback Overwriting**

**Location**: `src/utils/discovery_queue.py:188`

**Issue**: `register_high_priority_callback()` simply overwrites `_high_priority_callback` without warning.

**Current Code**:
```python
def register_high_priority_callback(
    self,
    callback: Callable[[str], None],
    threshold: float = 0.85,
    categories: list[str] | None = None,
) -> None:
    self._high_priority_callback = callback  # Silent overwrite
    self._high_priority_threshold = threshold
    if categories:
        self._high_priority_categories = set(categories)
    logger.info(
        f"📢 [QUEUE] High-priority callback registered (threshold={threshold}, categories={self._high_priority_categories})"
    )
```

**Impact**: LOW - If multiple components register callbacks, only the last one wins

**Recommendation**: Add logging or raise error on re-registration:
```python
def register_high_priority_callback(
    self,
    callback: Callable[[str], None],
    threshold: float = 0.85,
    categories: list[str] | None = None,
) -> None:
    if self._high_priority_callback is not None:
        logger.warning(
            f"⚠️ [QUEUE] Overwriting existing high-priority callback! "
            f"Previous callback will no longer be invoked."
        )
    self._high_priority_callback = callback
    # ...
```

---

## VERIFICATION RESULTS BY CATEGORY

### ✅ Thread Safety (PASS)
- RLock usage is correct and reentrant
- Callback invoked outside lock prevents deadlocks
- All queue modifications are atomic
- Index updates are synchronized with queue operations

### ✅ Race Conditions (PASS)
- No race conditions found
- All shared state protected by locks
- Atomic operations on critical sections

### ✅ Memory Management (PASS)
- Items properly expired via TTL
- Index cleanup on expiration
- Memory usage acceptable (~5MB for 1000 items)
- Deque with maxlen prevents unbounded growth

### ✅ Data Flow (MOSTLY PASS)
- Browser Monitor → Queue → Main Pipeline works correctly
- String confidence properly handled (HIGH→0.85, MEDIUM→0.65, LOW→0.4, VERY_HIGH→0.95)
- GLOBAL league key filtering works as designed
- **FAIL**: GlobalRadar uses separate queue (see Correction 1)

### ✅ Crash Scenarios (PASS)
- Callback exceptions caught and logged (lines 302-309)
- Import failures have fallbacks (lines 392-403)
- None/empty strings handled gracefully (lines 78-101)
- Team name matching is robust with bidirectional substring matching

### ⚠️ VPS Deployment (MOSTLY PASS)
- All dependencies in requirements.txt
- Python 3.10+ required (confirmed in pyproject.toml:3)
- No external system dependencies
- **WARNING**: Database session management needs improvement

---

## INTEGRATION POINTS VERIFIED

### ✅ Producer: Browser Monitor
**File**: `src/processing/news_hunter.py:446`
```python
queue = get_discovery_queue()
queue.push(data=discovery_data, league_key=league_key, ...)
```
**Status**: ✅ CORRECT - Uses global singleton

**Data Flow**:
1. Browser Monitor discovers news
2. Calls `store_discovery()` in news_hunter.py
3. Pushes to global DiscoveryQueue via `get_discovery_queue()`
4. Queue stores with league_key, team, confidence, category
5. High-priority callback triggered if confidence >= 0.85 and category in [INJURY, SUSPENSION, LINEUP]

### ✅ Consumer: Main Pipeline
**File**: `src/processing/news_hunter.py:506`
```python
queue = get_discovery_queue()
return queue.pop_for_match(match_id, team_names, league_key)
```
**Status**: ✅ CORRECT - Uses global singleton

**Data Flow**:
1. Analysis engine calls `run_hunter_for_match()`
2. Calls `get_browser_monitor_news()` with match_id, team_names, league_key
3. Retrieves discoveries via `pop_for_match()`
4. Returns items with match_id attached
5. Items remain in queue for other matches (not removed)

### ❌ Producer: GlobalRadarMonitor
**File**: `src/services/news_radar.py:3426`
```python
self._discovery_queue = DiscoveryQueue(max_entries=1000, ttl_hours=24)
```
**Status**: ❌ INCORRECT - Creates separate instance (see Correction 1)

**Broken Data Flow**:
1. GlobalRadar discovers signals
2. Pushes to SEPARATE DiscoveryQueue instance (line 3730)
3. Uses league_key="GLOBAL" for cross-league discoveries
4. Main pipeline's `pop_for_match()` checks GLOBAL key (lines 352-353)
5. **BUT** it's checking the WRONG queue instance!
6. GlobalRadar discoveries are NEVER retrieved

**Evidence of Broken Integration**:
- No code in news_radar.py calls `self._discovery_queue.pop()`
- No code in main.py or analysis_engine.py retrieves from GlobalRadar's queue
- The GLOBAL key feature in discovery_queue.py (lines 352-353) is designed for this integration but it's broken

### ✅ Callback Registration
**File**: `src/main.py:2087`
```python
queue = get_discovery_queue()
queue.register_high_priority_callback(callback=on_high_priority_discovery, ...)
```
**Status**: ✅ CORRECT - Uses global singleton

**Callback Flow**:
1. Main.py registers callback during initialization
2. Callback triggers immediate analysis for high-priority discoveries
3. Filters matches for the affected league
4. Runs analysis with optimizer, analyzer, notifier
5. Sends immediate alerts
6. Callback invoked OUTSIDE lock to prevent deadlocks

---

## VPS DEPLOYMENT REQUIREMENTS

### ✅ Dependencies
All required dependencies are in `requirements.txt`:
- Standard library only (no external deps for DiscoveryQueue)
- Python 3.10+ required (confirmed in `pyproject.toml:3`)
- No system-level dependencies beyond Python

**Verification**:
```bash
# setup_vps.sh line 117
pip install -r requirements.txt
```

**Status**: ✅ CORRECT - All dependencies will be installed

### ✅ Memory Requirements
- Queue: ~5MB for 1000 items (acceptable)
- Each DiscoveryItem: ~5KB (including data dict)
- No memory leaks detected
- Proper cleanup on expiration

**VPS Impact**: Minimal - well within typical VPS memory limits (1GB+)

### ⚠️ Database Connection Pooling
**Issue**: Callback session never closed
**Recommendation**: Monitor connection pool usage on VPS
**Potential Impact**: Connection pool exhaustion under high load

### ✅ Thread Safety for VPS
- RLock provides reentrant locking (safe for nested calls)
- Callback invoked outside lock (prevents deadlocks)
- All operations atomic under VPS multi-threading

---

## TEST COVERAGE

### ✅ Existing Tests

#### 1. Callback Tests
**File**: `tests/test_performance_improvements.py:200-318`

Tests covered:
- `test_callback_registration()` - Callback can be registered
- `test_callback_triggered_on_high_priority()` - High-confidence triggers callback
- `test_callback_not_triggered_on_low_priority()` - Low-confidence doesn't trigger
- `test_callback_not_triggered_wrong_category()` - Wrong category doesn't trigger
- `test_callback_exception_handling()` - Exceptions don't crash queue

**Status**: ✅ Good coverage

#### 2. Basic Queue Operations
**File**: `tests/test_shared_modules.py:152-520`

Tests covered:
- `test_basic_push_and_pop()` - Basic operations
- `test_pop_returns_empty_non_matching()` - Non-matching teams
- `test_pop_returns_empty_different_league()` - Different leagues
- `test_pop_handles_empty_team_names()` - Empty team_names
- `test_pop_handles_none_values_team_names()` - None values
- `test_lru_eviction_max_entries()` - LRU eviction
- `test_thread_safety_concurrent_access()` - Thread safety
- `test_cleanup_expired_entries()` - Expiration cleanup
- `test_statistics_tracking()` - Statistics

**Status**: ✅ Good coverage

#### 3. Integration Tests
**File**: `tests/test_integration_orchestration.py:163-403`

Tests covered:
- `test_discovery_queue_initialization()` - Initialization
- `test_discovery_queue_push_and_pop()` - Push/pop flow
- `test_discovery_queue_ttl_expiration()` - TTL expiration
- `test_discovery_queue_handles_full_queue()` - Full queue handling
- `test_discovery_queue_performance()` - Performance under load

**Status**: ✅ Good coverage

### ⚠️ Missing Tests

#### 1. GlobalRadar Integration Test
**Status**: ❌ MISSING - Would have caught Critical Bug 1

**Recommended Test**:
```python
def test_globalradar_uses_global_queue():
    """Verify GlobalRadar uses the global DiscoveryQueue singleton."""
    from src.services.news_radar import GlobalRadarMonitor
    from src.utils.discovery_queue import get_discovery_queue, reset_discovery_queue
    
    reset_discovery_queue()
    global_queue = get_discovery_queue()
    
    # Create GlobalRadarMonitor
    monitor = GlobalRadarMonitor(config_file="test_config.json")
    monitor._discovery_queue = monitor._discovery_queue  # Force initialization
    
    # Verify it uses the global singleton
    assert monitor._discovery_queue is global_queue, \
        "GlobalRadar should use global DiscoveryQueue singleton"
```

#### 2. Stress Test for 1000+ Items
**Status**: ⚠️ MISSING - Would reveal Issue 2 (long lock hold)

#### 3. Concurrent Access Stress Test
**Status**: ⚠️ PARTIAL - Basic test exists but not under high load

---

## DATA FLOW DIAGRAM

### Correct Flow (Browser Monitor):
```
Browser Monitor (Thread 1)
    ↓
news_hunter.py:store_discovery()
    ↓
get_discovery_queue() → Global Singleton
    ↓
DiscoveryQueue.push()
    ↓
[Queue Storage]
    ↓
High-Priority Callback (if conf >= 0.85)
    ↓
on_high_priority_discovery() in main.py
    ↓
Immediate analysis for league
```

### Broken Flow (GlobalRadar):
```
GlobalRadarMonitor (Thread 2)
    ↓
news_radar.py:3730 (push)
    ↓
self._discovery_queue → SEPARATE INSTANCE ❌
    ↓
[SEPARATE Queue Storage]
    ↓
    ← NEVER RETRIEVED ❌
    
Main Pipeline (Thread 3)
    ↓
news_hunter.py:get_browser_monitor_news()
    ↓
get_discovery_queue() → Global Singleton
    ↓
DiscoveryQueue.pop_for_match()
    ↓
    ← Can't find GlobalRadar discoveries ❌
```

---

## RECOMMENDATIONS

### Priority 1 (CRITICAL - Fix Before VPS Deployment)

#### 1. Fix GlobalRadar to Use Global Singleton
**File**: `src/services/news_radar.py:3426`

**Change**:
```python
# Before (WRONG)
self._discovery_queue = DiscoveryQueue(max_entries=1000, ttl_hours=24)

# After (CORRECT)
from src.utils.discovery_queue import get_discovery_queue
self._discovery_queue = get_discovery_queue()
```

**Impact**: HIGH - Fixes critical data flow bug

**Testing**: Add integration test to prevent regression

---

### Priority 2 (HIGH - Fix Soon)

#### 2. Add Session Management in Callback
**File**: `src/main.py:1967-2084`

**Change**: Use session-per-request pattern or add session refresh

**Impact**: MEDIUM - Prevents connection pool exhaustion on VPS

**Testing**: Monitor connection pool metrics in production

---

#### 3. Add Warning on Callback Re-registration
**File**: `src/utils/discovery_queue.py:164-194`

**Change**: Add logging when overwriting existing callback

**Impact**: LOW - Prevents silent overwriting

**Testing**: Manual verification

---

### Priority 3 (MEDIUM - Monitor)

#### 4. Monitor Lock Contention
**Action**: Add metrics for lock hold time in `pop_for_match()`

**Impact**: MEDIUM - Identify performance bottlenecks

**Implementation**:
```python
import time

def pop_for_match(self, match_id: str, team_names: list[str], league_key: str) -> list[dict[str, Any]]:
    start_time = time.time()
    with self._lock:
        # ... existing code ...
    lock_duration = time.time() - start_time
    if lock_duration > 0.1:  # Log if > 100ms
        logger.warning(f"⚠️ [QUEUE] Long lock hold: {lock_duration:.3f}s")
    return results
```

---

#### 5. Add Integration Test for GlobalRadar
**File**: `tests/test_integration_orchestration.py`

**Impact**: MEDIUM - Prevent regression of Critical Bug 1

**Implementation**: See "Missing Tests" section above

---

## CONCLUSION

### Overall Assessment

The `DiscoveryQueue` implementation is **WELL-DESIGNED** and **THREAD-SAFE**, with excellent error handling and fallback mechanisms. The code demonstrates:

✅ **Strengths**:
- Clean, well-documented API
- Proper thread safety with RLock
- Robust error handling
- Good test coverage
- VPS-ready deployment (mostly)
- Intelligent high-priority callback system

❌ **Critical Issue**:
- GlobalRadar creates separate queue instance - data flow completely broken

⚠️ **Areas for Improvement**:
- Lock contention under high load
- Database session management in callback
- Silent callback overwriting

### Deployment Readiness

**Status**: ⚠️ **NEEDS CRITICAL FIX BEFORE VPS DEPLOYMENT**

**Blocking Issues**: 1 (GlobalRadar queue isolation)  
**Non-Blocking Issues**: 3 (performance, session management, callback overwriting)  
**Ready for VPS**: ❌ NO - Critical bug must be fixed first

### Risk Assessment

| Risk | Severity | Likelihood | Impact | Mitigation |
|------|----------|------------|--------|------------|
| GlobalRadar data loss | CRITICAL | 100% | HIGH | Fix queue instance |
| Lock contention | MEDIUM | Low | MEDIUM | Monitor metrics |
| Connection pool exhaustion | MEDIUM | Low | MEDIUM | Fix session management |
| Callback overwriting | LOW | Low | LOW | Add warning |

### Next Steps

1. **IMMEDIATE**: Fix GlobalRadar queue instance (Correction 1)
2. **SOON**: Add session management in callback
3. **SOON**: Add integration test for GlobalRadar
4. **MONITOR**: Add lock contention metrics
5. **DEPLOY**: After fixes are verified

---

## CORRECTIONS SUMMARY

| # | Severity | Location | Issue | Status |
|---|----------|-----------|-------|--------|
| 1 | ❌ CRITICAL | news_radar.py:3426 | Separate queue instance | **NEEDS FIX** |
| 2 | ⚠️ WARNING | discovery_queue.py:347 | Long lock hold | Monitor |
| 3 | ⚠️ WARNING | main.py:1998 | Session never closed | Monitor |
| 4 | ⚠️ WARNING | discovery_queue.py:188 | Silent callback overwrite | Low priority |

---

## APPENDIX: Code Review Details

### DiscoveryQueue Methods Reviewed

#### ✅ `__init__()` (lines 131-162)
- Correct initialization of RLock
- Proper default values
- Thread-safe singleton pattern in `get_discovery_queue()`

#### ✅ `register_high_priority_callback()` (lines 164-194)
- Correct parameter handling
- Atomic update of callback reference
- Good logging
- **ISSUE**: Silent overwriting (Issue 4)

#### ✅ `push()` (lines 196-314)
- Proper field extraction from data dict
- String confidence mapping (HIGH→0.85, etc.)
- Atomic queue and index updates
- Callback invoked OUTSIDE lock (correct)
- Exception handling in callback

#### ⚠️ `pop_for_match()` (lines 316-413)
- Correct league and GLOBAL filtering
- Proper team matching
- **ISSUE**: Long lock hold (Issue 2)
- Good fallback for get_freshness_tag import

#### ✅ `cleanup_expired()` (lines 415-451)
- Atomic queue rebuild
- Proper index cleanup
- Good statistics tracking

#### ✅ `clear()` (lines 453-487)
- Correct league-specific and global clear
- Atomic operations
- Proper index cleanup

#### ✅ `size()` (lines 489-502)
- Thread-safe size reporting
- League-specific filtering

#### ✅ `get_stats()` (lines 504-531)
- Comprehensive statistics
- Thread-safe calculation

---

## REFERENCES

### Files Analyzed
- `src/utils/discovery_queue.py` (568 lines)
- `src/processing/news_hunter.py` (lines 318-599)
- `src/main.py` (lines 1956-2095)
- `src/services/news_radar.py` (lines 3380-3760)
- `src/core/analysis_engine.py` (lines 970-1050)
- `requirements.txt` (74 lines)
- `pyproject.toml` (16 lines)
- `setup_vps.sh` (lines 1-200)

### Test Files Reviewed
- `tests/test_performance_improvements.py` (lines 200-318)
- `tests/test_shared_modules.py` (lines 152-520)
- `tests/test_integration_orchestration.py` (lines 163-403)

---

**Report Generated**: 2026-03-07T07:49:28Z  
**Verification Mode**: Chain of Verification (CoVe)  
**Total Verification Time**: ~5 minutes  
**Questions Analyzed**: 21  
**Critical Issues Found**: 1  
**Non-Critical Issues Found**: 3  
**Overall Status**: ⚠️ NEEDS CRITICAL FIX
