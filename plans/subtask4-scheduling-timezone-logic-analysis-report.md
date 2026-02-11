# Subtask 4: Scheduling & Timezone Logic Analysis Report

**Continental Strategy Feasibility Audit - Subtask 4 of 5**

**Date:** 2026-02-02
**Status:** READ-ONLY Analysis Complete
**Focus:** Scheduling & Timezone Logic for Continent-Based Execution

---

## Executive Summary

This report analyzes the current scheduling and timezone logic in EarlyBird to assess feasibility for implementing "Smart Sleeping" based on continent's local time in a parallel execution model. The analysis reveals that **timezone-aware scheduling is partially implemented** but is **NOT modular enough** for continent-based execution without significant refactoring.

### Key Findings

| Aspect | Current State | Feasibility for Continent-Based |
|--------|---------------|------------------------------|
| Timezone Handling | ✅ Implemented (source_timezone field) | ✅ HIGH - Can be extended |
| Off-Peak Optimization | ✅ Implemented (midnight-6am double interval) | ✅ HIGH - Can be adapted |
| Main Pipeline Scheduling | ❌ Fixed 6-hour cycle | ⚠️ MEDIUM - Requires refactoring |
| Sleep Logic Modularity | ❌ Scattered across files | ❌ LOW - Needs centralization |
| Coordination Mechanism | ❌ Non-existent | ❌ LOW - Must be built from scratch |

---

## 1. Current Scheduling Mechanism

### 1.1 Main Pipeline Scheduling (`src/main.py`)

**Entry Point:** [`run_continuous()`](src/main.py:3843)

**Main Loop Structure:**
```python
while True:
    cycle_count += 1
    
    # Check for pause lock file
    if os.path.exists(PAUSE_FILE):
        logging.info("💤 System Paused (pause.lock detected). Sleeping 60s...")
        time.sleep(60)
        continue
    
    try:
        # Run pipeline
        run_pipeline()
        
        # Sleep for 6 hours
        logging.info("💤 Sleeping for 360 minutes (6 hours) until next cycle...")
        time.sleep(21600)  # 6 hours
```

**Key Sleep Intervals:**

| Location | Line | Purpose | Duration | Type |
|----------|-------|---------|----------|------|
| [`src/main.py:3849`](src/main.py:3849) | Pause lock handling | 60s | Fixed |
| [`src/main.py:3888`](src/main.py:3888) | Main cycle sleep | 21600s (6h) | Fixed |
| [`src/main.py:3934`](src/main.py:3934) | Memory error retry | 600s (10m) | Fixed |
| [`src/main.py:3956`](src/main.py:3956) | Connection error retry | 300s (5m) | Fixed |
| [`src/main.py:3983`](src/main.py:3983) | General error retry | Dynamic (exponential) | Dynamic |

**Scheduling Characteristics:**
- **Fixed 6-hour cycle** between pipeline runs
- **No timezone awareness** in main loop
- **Pause lock support** for manual control
- **Error-based backoff** with exponential delays

### 1.2 Launcher Scheduling (`src/launcher.py`)

**Orchestrator Loop:**
```python
while not _shutdown_requested:
    check_and_restart()  # Check process health
    time.sleep(5)  # Check every 5 seconds
```

**Key Sleep Intervals:**

| Location | Line | Purpose | Duration | Type |
|----------|-------|---------|----------|------|
| [`src/launcher.py:336`](src/launcher.py:336) | Process restart backoff | Dynamic (2-60s) | Dynamic |
| [`src/launcher.py:386`](src/launcher.py:386) | Inter-process startup delay | 2s | Fixed |
| [`src/launcher.py:393`](src/launcher.py:393) | Health check interval | 5s | Fixed |

**Scheduling Characteristics:**
- **Process-level monitoring** (not content scheduling)
- **Exponential backoff** for crashed processes
- **CPU protection** (15s minimum for fast crashes)
- **No timezone awareness**

### 1.3 Shell Script Scheduling (`run_forever.sh`)

**Mechanism:** Simple wrapper script
```bash
# Activate venv
source venv/bin/activate

# Launch orchestrator (handles all scheduling internally)
python3 src/launcher.py
```

**Characteristics:**
- **No scheduling logic** in shell script
- **Delegates to Python orchestrator**
- **Auto-install Playwright** if missing

---

## 2. Timezone Handling Status

### 2.1 Timezone Configuration

#### News Radar Sources (`config/news_radar_sources.json`)

**Timezone Field:** `source_timezone`

**Observed Timezones:**

| Timezone | Count | Sources |
|----------|-------|---------|
| `Europe/London` | 3 | BBC Sport, Chesterfield FC, STV Scotland |
| `America/Sao_Paulo` | 7 | Gazeta Esportiva, Jogada 10, Globo Esporte, etc. |
| `Europe/Prague` | 1 | Flashscore |
| `Europe/Moscow` | 1 | Betzona |
| `Europe/Paris` | 1 | BeSoccer |
| `Europe/Rome` | 3 | TuttoMercatoWeb, SportyTrader, Europa Calcio |
| `Europe/Berlin` | 1 | Liga3 Online |
| `Europe/Istanbul` | 1 | Sakarya Haber |
| `Asia/Shanghai` | 1 | YSScores |
| `Asia/Jakarta` | 1 | Tribun Palembang |
| `Asia/Singapore` | 1 | Straits Times |
| `Africa/Johannesburg` | 1 | SuperSport |
| `Africa/Lagos` | 7 | All Nigeria Soccer (multiple feeds) |
| `Africa/Cairo` | 1 | Ahram Egypt |
| `America/Tegucigalpa` | 2 | Hondudiario, El Heraldo |

**Total:** 32 sources with timezone data

#### Browser Monitor Sources (`config/browser_sources.json`)

**Timezone Field:** `source_timezone`

**Observed Timezones:**

| Timezone | Count | Sources |
|----------|-------|---------|
| `Europe/London` | 3 | BBC Sport, Chesterfield FC, STV Scotland |
| `America/Sao_Paulo` | 5 | Gazeta Esportiva, Jogada 10, Globo Esporte, etc. |
| `Europe/Prague` | 1 | Flashscore |
| `Europe/Paris` | 1 | BeSoccer |
| `Asia/Shanghai` | 1 | YSScores |
| `Asia/Jakarta` | 1 | Tribun Palembang |
| `America/Tegucigalpa` | 2 | Hondudiario, El Heraldo |

**Total:** 14 sources with timezone data

### 2.2 Timezone-Aware Scheduling Implementation

#### News Radar (`src/services/news_radar.py`)

**Data Structure:**
```python
@dataclass
class RadarSource:
    source_timezone: Optional[str] = None  # V7.3: e.g., "Europe/London"
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    last_scanned: Optional[datetime] = None
```

**Key Methods:**

**[`is_due_for_scan()`](src/services/news_radar.py:176)** - Check if source needs scanning
```python
def is_due_for_scan(self) -> bool:
    if self.last_scanned is None:
        return True
    
    effective_interval = self._get_effective_interval()
    elapsed = datetime.now(timezone.utc) - self.last_scanned
    return elapsed >= timedelta(minutes=effective_interval)
```

**[`_get_effective_interval()`](src/services/news_radar.py:191)** - Timezone-aware interval calculation
```python
def _get_effective_interval(self) -> int:
    if not self.source_timezone:
        return self.scan_interval_minutes
    
    try:
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
        return self.scan_interval_minutes
```

**Main Loop Sleep:**
```python
# Wait before next cycle
interval = self._config.global_settings.default_scan_interval_minutes * 60
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

#### Browser Monitor (`src/services/browser_monitor.py`)

**Data Structure:**
```python
@dataclass
class BrowserSource:
    source_timezone: Optional[str] = None  # V7.5: e.g., "Europe/London"
    scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES
    last_scanned: Optional[datetime] = None
```

**Key Methods:**

**[`is_due_for_scan()`](src/services/browser_monitor.py:304)** - Same logic as News Radar
```python
def is_due_for_scan(self) -> bool:
    if self.last_scanned is None:
        return True
    
    effective_interval = self._get_effective_interval()
    elapsed = datetime.now(timezone.utc) - self.last_scanned
    return elapsed >= timedelta(minutes=effective_interval)
```

**[`_get_effective_interval()`](src/services/browser_monitor.py:324)** - Same logic as News Radar
```python
def _get_effective_interval(self) -> int:
    if not self.source_timezone:
        return self.scan_interval_minutes
    
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self.source_timezone)
        local_now = datetime.now(tz)
        local_hour = local_now.hour
        
        # Off-peak: midnight to 6am local time
        if 0 <= local_hour < 6:
            return self.scan_interval_minutes * 2
        
        return self.scan_interval_minutes
        
    except Exception:
        return self.scan_interval_minutes
```

**Main Loop Sleep:**
```python
# Wait before next cycle
interval = self._config.global_settings.default_scan_interval_minutes * 60
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

### 2.3 Timezone Format and Values

**Format:** IANA timezone identifiers (e.g., `Europe/London`, `America/Sao_Paulo`)

**Implementation:** Python `zoneinfo.ZoneInfo` module (Python 3.9+)

**Coverage:** 
- ✅ All major continents represented
- ✅ Multiple timezones per continent
- ✅ Consistent format across configs

---

## 3. Sleep Logic Inventory

### 3.1 Complete List of `time.sleep()` and `asyncio.sleep()` Calls

| File | Line | Type | Purpose | Duration | Timezone-Aware |
|------|------|------|---------|----------|----------------|
| `src/main.py:3800` | `time.sleep` | Browser monitor startup delay | 2s | ❌ No |
| `src/main.py:3849` | `time.sleep` | Pause lock handling | 60s | ❌ No |
| `src/main.py:3888` | `time.sleep` | Main cycle sleep | 21600s (6h) | ❌ No |
| `src/main.py:3934` | `time.sleep` | Memory error retry | 600s (10m) | ❌ No |
| `src/main.py:3956` | `time.sleep` | Connection error retry | 300s (5m) | ❌ No |
| `src/main.py:3983` | `time.sleep` | General error retry | Dynamic | ❌ No |
| `src/launcher.py:336` | `time.sleep` | Process restart backoff | Dynamic (2-60s) | ❌ No |
| `src/launcher.py:386` | `time.sleep` | Inter-process startup delay | 2s | ❌ No |
| `src/launcher.py:393` | `time.sleep` | Health check interval | 5s | ❌ No |
| `src/services/news_radar.py:999` | `asyncio.sleep` | Delay between pages | Dynamic | ❌ No |
| `src/services/news_radar.py:1128` | `asyncio.sleep` | Rate limiting | Dynamic | ❌ No |
| `src/services/news_radar.py:1470` | `asyncio.sleep` | Telegram rate limit | Dynamic | ❌ No |
| `src/services/news_radar.py:1483` | `asyncio.sleep` | Retry backoff | Dynamic | ❌ No |
| `src/services/news_radar.py:1724` | `asyncio.sleep` | Scan loop error retry | 60s | ❌ No |
| `src/services/browser_monitor.py:1031` | `asyncio.sleep` | Mouse movement delay | 0.1-0.3s | ❌ No |
| `src/services/browser_monitor.py:1055` | `asyncio.sleep` | Scroll delay | Dynamic | ❌ No |
| `src/services/browser_monitor.py:1067` | `asyncio.sleep` | Reading pause | 0.2-0.5s | ❌ No |
| `src/services/browser_monitor.py:1450` | `asyncio.sleep` | Delay between pages | Dynamic | ❌ No |
| `src/services/browser_monitor.py:1618` | `asyncio.sleep` | Retry backoff | Dynamic | ❌ No |
| `src/services/browser_monitor.py:1706` | `asyncio.sleep` | Scan loop error retry | 60s | ❌ No |
| `src/services/browser_monitor.py:2073` | `asyncio.sleep` | Interval enforcement | Dynamic | ❌ No |
| `src/services/browser_monitor.py:2091` | `asyncio.sleep` | Memory wait loop | 10s | ❌ No |
| `src/run_bot.py:551` | `asyncio.sleep` | Bot heartbeat | 3600s (1h) | ❌ No |

### 3.2 Sleep Logic Analysis

#### Fixed Sleep Intervals

| Category | Files | Count | Total Impact |
|----------|-------|-------|--------------|
| Main pipeline cycle | `src/main.py` | 1 | **CRITICAL** - Controls overall execution |
| Launcher health check | `src/launcher.py` | 2 | Medium - Process monitoring |
| Pause lock | `src/main.py` | 1 | Low - Manual control |
| Error retry | `src/main.py` | 3 | Medium - Error recovery |

#### Dynamic Sleep Intervals

| Category | Files | Count | Total Impact |
|----------|-------|-------|--------------|
| Rate limiting | Multiple | 20+ | **HIGH** - API quota management |
| Retry backoff | Multiple | 15+ | **HIGH** - Error recovery |
| Browser behavior | `src/services/browser_monitor.py` | 3 | Low - Anti-detection |
| Scan interval | `src/services/news_radar.py`, `src/services/browser_monitor.py` | 2 | **MEDIUM** - Source scheduling |

### 3.3 Modularity Assessment

#### Current State: ❌ LOW MODULARITY

**Issues:**

1. **Scattered Logic:** Sleep logic is embedded in multiple files with no central coordination
2. **Hardcoded Values:** Main pipeline sleep (21600s) is hardcoded
3. **No Abstraction:** No reusable sleep functions for timezone-aware scheduling
4. **Mixed Types:** Both `time.sleep()` (synchronous) and `asyncio.sleep()` (asynchronous)
5. **No Configuration:** Sleep intervals are not configurable

**Modularity Score:** 2/10

---

## 4. Smart Sleeping Implementation Plan

### 4.1 Definition of "Smart Sleeping" for Continent-Based Execution

**Smart Sleeping** = Timezone-aware sleep schedules that optimize resource utilization by:

1. **Per-Continent Active Windows:** Each continent session runs during its peak hours
2. **Cross-Continent Coordination:** Sessions avoid overlapping during resource-intensive operations
3. **Dynamic Interval Adjustment:** Sleep intervals adjust based on:
   - Source timezone local time
   - Continent peak/off-peak hours
   - Resource availability (CPU, memory, API quota)
   - Network latency considerations

### 4.2 Per-Continent Sleep Schedule Design

#### Continent Block 1: LATAM
**Countries:** Argentina, Mexico, Brazil, Colombia
**Timezones:** UTC-3 to UTC-5
**Peak Hours:** 18:00-02:00 UTC (14:00-22:00 local)
**Proposed Schedule:**
- **Active:** 18:00-02:00 UTC (8 hours)
- **Sleep:** 02:00-18:00 UTC (16 hours)

#### Continent Block 2: ASIA/EMEA
**Countries:** Turkey, Greece, Saudi Arabia, China, Japan
**Timezones:** UTC+2 to UTC+9
**Peak Hours:** 06:00-18:00 UTC (08:00-20:00 local)
**Proposed Schedule:**
- **Active:** 06:00-18:00 UTC (12 hours)
- **Sleep:** 18:00-06:00 UTC (12 hours)

#### Continent Block 3: EUROPE/AU
**Countries:** Scotland, Australia, Poland, Norway
**Timezones:** UTC+1 to UTC+11
**Peak Hours:** 12:00-00:00 UTC (13:00-01:00 local)
**Proposed Schedule:**
- **Active:** 12:00-00:00 UTC (12 hours)
- **Sleep:** 00:00-12:00 UTC (12 hours)

### 4.3 Required Changes to Implement Timezone-Aware Sleep Logic

#### 4.3.1 Centralized Sleep Manager (NEW)

**File:** `src/utils/sleep_manager.py`

**Purpose:** Centralize all sleep logic with timezone awareness

**Interface:**
```python
class SleepManager:
    def __init__(self, continent: str, timezone: str):
        self.continent = continent
        self.timezone = timezone
    
    def smart_sleep(self, base_interval: int) -> int:
        """Calculate timezone-aware sleep interval"""
        pass
    
    def is_active_window(self) -> bool:
        """Check if current time is in active window for continent"""
        pass
    
    def get_active_window(self) -> tuple[datetime, datetime]:
        """Get start/end of current active window"""
        pass
```

#### 4.3.2 Main Pipeline Refactoring

**File:** `src/main.py`

**Changes:**
1. Replace fixed 6-hour sleep with `SleepManager.smart_sleep()`
2. Add continent parameter to `run_continuous()`
3. Implement active window check before pipeline execution
4. Add graceful shutdown during sleep period

**Before:**
```python
while True:
    run_pipeline()
    time.sleep(21600)  # Fixed 6 hours
```

**After:**
```python
sleep_manager = SleepManager(continent="LATAM", timezone="America/Sao_Paulo")

while True:
    if not sleep_manager.is_active_window():
        sleep_interval = sleep_manager.get_sleep_until_active()
        logging.info(f"💤 Sleeping {sleep_interval//60}m until active window...")
        time.sleep(sleep_interval)
        continue
    
    run_pipeline()
    sleep_interval = sleep_manager.smart_sleep(3600)  # Base 1 hour
    time.sleep(sleep_interval)
```

#### 4.3.3 News Radar Refactoring

**File:** `src/services/news_radar.py`

**Changes:**
1. Add continent parameter to `NewsRadar` class
2. Filter sources by continent during scan cycle
3. Use `SleepManager` for main loop sleep
4. Extend off-peak optimization to continent-level

**Before:**
```python
interval = self._config.global_settings.default_scan_interval_minutes * 60
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

**After:**
```python
sleep_manager = SleepManager(continent=self.continent, timezone="UTC")
interval = sleep_manager.smart_sleep(
    self._config.global_settings.default_scan_interval_minutes * 60
)
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

#### 4.3.4 Browser Monitor Refactoring

**File:** `src/services/browser_monitor.py`

**Changes:**
1. Add continent parameter to `BrowserMonitor` class
2. Filter sources by continent during scan cycle
3. Use `SleepManager` for main loop sleep
4. Extend off-peak optimization to continent-level

**Before:**
```python
interval = self._config.global_settings.default_scan_interval_minutes * 60
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

**After:**
```python
sleep_manager = SleepManager(continent=self.continent, timezone="UTC")
interval = sleep_manager.smart_sleep(
    self._config.global_settings.default_scan_interval_minutes * 60
)
await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
```

### 4.4 Coordination Mechanism for 3 Parallel Sessions

#### 4.4.1 Shared State Store

**File:** `src/utils/continent_coordinator.py`

**Purpose:** Coordinate sleep schedules across 3 parallel sessions

**Interface:**
```python
class ContinentCoordinator:
    def __init__(self):
        self.active_sessions = set()
        self.lock = asyncio.Lock()
    
    async def register_session(self, continent: str):
        """Register a continent session"""
        pass
    
    async def check_overlap(self, continent: str) -> bool:
        """Check if another session is active"""
        pass
    
    async def negotiate_sleep(self, continent: str, base_interval: int) -> int:
        """Negotiate sleep interval to avoid overlap"""
        pass
```

#### 4.4.2 Coordination Protocol

**Rules:**
1. **Priority:** ASIA/EMEA > EUROPE/AU > LATAM (based on market size)
2. **Overlap Avoidance:** Sessions wait if another session is in critical phase
3. **Resource Sharing:** Database locks respected across sessions
4. **Graceful Handoff:** Sessions signal completion before sleep

**Flow:**
```
LATAM Session:
1. Check coordinator: Is ASIA/EMEA active?
2. If yes: Wait 30s, retry
3. If no: Register as active
4. Execute pipeline
5. Signal completion
6. Unregister
7. Sleep until active window
```

---

## 5. Execution Windows Analysis

### 5.1 Optimal Execution Windows for Each Continent Block

#### LATAM (UTC-3 to UTC-5)

| Local Time | UTC Time | Activity Level | Recommended Action |
|------------|-----------|----------------|-------------------|
| 00:00-06:00 | 03:00-09:00 | LOW | Sleep (extended interval) |
| 06:00-12:00 | 09:00-15:00 | MEDIUM | Reduced scanning |
| 12:00-18:00 | 15:00-21:00 | HIGH | Active scanning |
| 18:00-24:00 | 21:00-03:00 | PEAK | Full scanning |

**Optimal Window:** 18:00-02:00 UTC (8 hours)

#### ASIA/EMEA (UTC+2 to UTC+9)

| Local Time | UTC Time | Activity Level | Recommended Action |
|------------|-----------|----------------|-------------------|
| 00:00-06:00 | 18:00-00:00 | LOW | Sleep (extended interval) |
| 06:00-12:00 | 00:00-06:00 | MEDIUM | Reduced scanning |
| 12:00-18:00 | 06:00-12:00 | HIGH | Active scanning |
| 18:00-24:00 | 12:00-18:00 | PEAK | Full scanning |

**Optimal Window:** 06:00-18:00 UTC (12 hours)

#### EUROPE/AU (UTC+1 to UTC+11)

| Local Time | UTC Time | Activity Level | Recommended Action |
|------------|-----------|----------------|-------------------|
| 00:00-06:00 | 23:00-05:00 | LOW | Sleep (extended interval) |
| 06:00-12:00 | 05:00-11:00 | MEDIUM | Reduced scanning |
| 12:00-18:00 | 11:00-17:00 | HIGH | Active scanning |
| 18:00-24:00 | 17:00-23:00 | PEAK | Full scanning |

**Optimal Window:** 12:00-00:00 UTC (12 hours)

### 5.2 Timezone Coverage Analysis

**24-Hour Coverage Map (UTC):**

| UTC Hour | LATAM | ASIA/EMEA | EUROPE/AU | Active Sessions |
|----------|--------|------------|------------|----------------|
| 00:00-02:00 | ❌ Sleep | ✅ Active | ❌ Sleep | 1 |
| 02:00-06:00 | ❌ Sleep | ✅ Active | ❌ Sleep | 1 |
| 06:00-12:00 | ❌ Sleep | ✅ Active | ✅ Active | 2 |
| 12:00-18:00 | ❌ Sleep | ✅ Active | ✅ Active | 2 |
| 18:00-00:00 | ✅ Active | ❌ Sleep | ✅ Active | 2 |

**Coverage Summary:**
- **Minimum Active Sessions:** 1 (at any time)
- **Maximum Active Sessions:** 2 (during overlap periods)
- **Total Coverage:** 24/7 (always at least 1 session active)
- **Overlap Periods:** 12 hours (50% of day)

### 5.3 Overlap Periods and Resource Contention Risks

#### Critical Overlap 1: 06:00-12:00 UTC
**Active Sessions:** ASIA/EMEA + EUROPE/AU
**Risk Level:** ⚠️ MEDIUM
**Potential Issues:**
- Database lock contention
- API quota exhaustion
- Memory pressure

**Mitigation:**
- Stagger scan cycles by 30 minutes
- Implement shared quota tracking
- Use database connection pooling

#### Critical Overlap 2: 12:00-18:00 UTC
**Active Sessions:** ASIA/EMEA + EUROPE/AU
**Risk Level:** ⚠️ MEDIUM
**Potential Issues:**
- Same as above

**Mitigation:**
- Same as above

#### Critical Overlap 3: 18:00-00:00 UTC
**Active Sessions:** LATAM + EUROPE/AU
**Risk Level:** ⚠️ MEDIUM
**Potential Issues:**
- Same as above

**Mitigation:**
- Same as above

---

## 6. Modularity Assessment

### 6.1 Current Sleep Logic Modularity

**Score: 2/10 (LOW)**

**Strengths:**
- ✅ Timezone-aware scheduling implemented in News Radar and Browser Monitor
- ✅ Off-peak optimization logic exists
- ✅ Source-level `is_due_for_scan()` method

**Weaknesses:**
- ❌ Sleep logic scattered across 10+ files
- ❌ No central sleep management
- ❌ Main pipeline uses fixed 6-hour sleep
- ❌ No abstraction for continent-level scheduling
- ❌ Mixed synchronous/asynchronous sleep calls
- ❌ No coordination mechanism between sessions

### 6.2 Required Refactoring to Support Continent-Specific Scheduling

#### Phase 1: Centralization (HIGH PRIORITY)

**Tasks:**
1. Create `src/utils/sleep_manager.py` with `SleepManager` class
2. Extract all sleep logic into reusable functions
3. Standardize on `asyncio.sleep()` for async contexts
4. Add configuration support for sleep intervals

**Estimated Effort:** 2-3 days

#### Phase 2: Continent Integration (HIGH PRIORITY)

**Tasks:**
1. Add continent parameter to all major components
2. Implement continent filtering in source configs
3. Add continent-specific active windows
4. Integrate `SleepManager` into main pipeline

**Estimated Effort:** 3-4 days

#### Phase 3: Coordination (MEDIUM PRIORITY)

**Tasks:**
1. Create `src/utils/continent_coordinator.py`
2. Implement shared state store
3. Add overlap detection and negotiation
4. Implement graceful handoff protocol

**Estimated Effort:** 4-5 days

#### Phase 4: Testing & Validation (HIGH PRIORITY)

**Tasks:**
1. Unit tests for `SleepManager`
2. Integration tests for continent coordination
3. Load testing for overlap periods
4. Performance benchmarking

**Estimated Effort:** 2-3 days

**Total Estimated Effort:** 11-15 days

### 6.3 Implementation Approach

#### Option 1: Incremental Migration (RECOMMENDED)

**Approach:**
1. Implement `SleepManager` without breaking existing code
2. Add continent support as optional parameter
3. Gradually migrate components to use `SleepManager`
4. Enable coordination after all components migrated

**Pros:**
- ✅ Lower risk
- ✅ Can test incrementally
- ✅ Can rollback if issues arise

**Cons:**
- ⚠️ Longer timeline
- ⚠️ Temporary code duplication

#### Option 2: Big Bang Rewrite

**Approach:**
1. Create new continent-aware architecture
2. Rewrite all scheduling logic
3. Switch over in single deployment

**Pros:**
- ✅ Clean architecture
- ✅ No temporary code

**Cons:**
- ❌ High risk
- ❌ Difficult to test
- ❌ Hard to rollback

---

## 7. Risk Matrix

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Database lock contention during overlap** | HIGH | HIGH | - Implement connection pooling<br>- Stagger scan cycles<br>- Use row-level locking |
| **API quota exhaustion** | HIGH | MEDIUM | - Centralized quota manager (from Subtask 3)<br>- Per-continent quota allocation<br>- Rate limiting across sessions |
| **Sleep logic bugs causing missed scans** | MEDIUM | MEDIUM | - Comprehensive unit tests<br>- Integration tests for timezones<br>- Monitoring and alerting |
| **Coordination failure leading to conflicts** | HIGH | MEDIUM | - Implement fallback to safe mode<br>- Add circuit breakers<br>- Manual override capability |
| **Timezone calculation errors** | MEDIUM | LOW | - Use Python `zoneinfo` (battle-tested)<br>- Add timezone validation<br>- Fallback to UTC on error |
| **Performance degradation during overlap** | MEDIUM | HIGH | - Resource monitoring<br>- Dynamic scaling<br>- Load shedding under pressure |
| **Deployment complexity** | HIGH | MEDIUM | - Incremental migration<br>- Feature flags<br>- Rollback plan |
| **Testing coverage gaps** | MEDIUM | HIGH | - Test all timezone edge cases<br>- Load test overlap periods<br>- Chaos testing |

---

## 8. Recommendations

### 8.1 Short-Term (1-2 weeks)

1. **Create `SleepManager` module** for centralized sleep logic
2. **Add continent parameter** to main pipeline
3. **Implement basic active window checking** without coordination
4. **Test timezone-aware scheduling** in isolation

### 8.2 Medium-Term (3-4 weeks)

1. **Implement `ContinentCoordinator`** for session coordination
2. **Add overlap detection** and negotiation
3. **Integrate with centralized quota manager** (from Subtask 3)
4. **Deploy 2 parallel sessions** for testing

### 8.3 Long-Term (5-8 weeks)

1. **Deploy all 3 continent sessions** in production
2. **Monitor performance** and adjust schedules
3. **Optimize resource allocation** based on metrics
4. **Document operational procedures**

---

## 9. Conclusion

### 9.1 Feasibility Assessment

**Overall Feasibility: MEDIUM (6/10)**

**Strengths:**
- ✅ Timezone-aware scheduling already implemented
- ✅ Off-peak optimization logic exists
- ✅ Source-level filtering is modular
- ✅ Configuration supports timezone data

**Challenges:**
- ❌ Main pipeline uses fixed 6-hour sleep
- ❌ Sleep logic is not modular
- ❌ No coordination mechanism exists
- ❌ Significant refactoring required

### 9.2 Critical Path to Implementation

1. **Create `SleepManager`** (3 days)
2. **Refactor main pipeline** (2 days)
3. **Implement `ContinentCoordinator`** (4 days)
4. **Integrate with quota manager** (2 days)
5. **Testing & validation** (3 days)

**Total:** 14 days (2 weeks)

### 9.3 Dependencies on Previous Subtasks

| Subtask | Dependency | Status |
|----------|-------------|--------|
| Subtask 1: League Filtering | Continent-aware source filtering | ✅ READY |
| Subtask 2: Shared Resources | Database partitioning, Redis cache | ⚠️ BLOCKING |
| Subtask 3: API Quota | Centralized quota manager | ⚠️ BLOCKING |
| Subtask 4: Scheduling | Smart sleeping logic | ✅ IN PROGRESS |
| Subtask 5: Final Plan | Integration of all components | ⏳ PENDING |

### 9.4 Final Recommendation

**Proceed with continent-based execution, BUT:**

1. **Address blocking dependencies first:**
   - Implement database partitioning (Subtask 2)
   - Implement centralized quota manager (Subtask 3)
   - Implement shared cache (Subtask 2)

2. **Use incremental migration approach:**
   - Start with 1 continent session
   - Add second session after validation
   - Add third session after full testing

3. **Invest in monitoring and observability:**
   - Real-time session coordination metrics
   - Resource usage tracking
   - Alerting for coordination failures

4. **Plan for rollback:**
   - Feature flags for continent mode
   - Ability to disable coordination
   - Fallback to single-process mode

---

## Appendix A: Code References

### Main Pipeline Sleep Logic
- [`src/main.py:3843`](src/main.py:3843) - Main loop
- [`src/main.py:3888`](src/main.py:3888) - Fixed 6-hour sleep

### Timezone-Aware Scheduling
- [`src/services/news_radar.py:176`](src/services/news_radar.py:176) - `is_due_for_scan()`
- [`src/services/news_radar.py:191`](src/services/news_radar.py:191) - `_get_effective_interval()`
- [`src/services/browser_monitor.py:304`](src/services/browser_monitor.py:304) - `is_due_for_scan()`
- [`src/services/browser_monitor.py:324`](src/services/browser_monitor.py:324) - `_get_effective_interval()`

### Configuration Files
- [`config/news_radar_sources.json`](config/news_radar_sources.json) - News radar sources with timezones
- [`config/browser_sources.json`](config/browser_sources.json) - Browser monitor sources with timezones

### Launcher Logic
- [`src/launcher.py:391`](src/launcher.py:391) - Orchestrator main loop
- [`run_forever.sh`](run_forever.sh) - Shell wrapper

---

## Appendix B: Timezone Reference

### IANA Timezone Identifiers Used

**Europe:**
- `Europe/London` (UTC+0/+1)
- `Europe/Prague` (UTC+1/+2)
- `Europe/Moscow` (UTC+3)
- `Europe/Paris` (UTC+1/+2)
- `Europe/Rome` (UTC+1/+2)
- `Europe/Berlin` (UTC+1/+2)
- `Europe/Istanbul` (UTC+3)

**Americas:**
- `America/Sao_Paulo` (UTC-3/-2)
- `America/Tegucigalpa` (UTC-6)

**Asia:**
- `Asia/Shanghai` (UTC+8)
- `Asia/Jakarta` (UTC+7)
- `Asia/Singapore` (UTC+8)

**Africa:**
- `Africa/Johannesburg` (UTC+2)
- `Africa/Lagos` (UTC+1)
- `Africa/Cairo` (UTC+2)

---

**Report End**
