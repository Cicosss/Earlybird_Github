# COVE: Forensic Startup Validation Analysis
**Date:** 2026-02-14
**Mode:** Chain of Verification (CoVe)
**Subject:** Pre-Flight Guard - Environment Variable Validation Layer Audit

---

## Executive Summary

This report performs a comprehensive Chain-of-Verification (CoVe) analysis of the EarlyBird system's startup validation layer. The investigation reveals **critical blind spots** in environment variable validation that have caused boot-time failures and infinite crash loops.

**Key Findings:**
- ⚠️ **Partial startup validator exists** in [`go_live.py`](go_live.py:36-71) but is incomplete and not integrated into all entry points
- ❌ **Environment variable validation is decentralized** across multiple entry points
- ❌ **"Present but Empty" keys** (`KEY=""`) are not distinguished from missing keys
- ❌ **Critical keys are missing from validation** (e.g., `BRAVE_API_KEY`)
- ❌ **No graceful degradation** strategy for optional services
- ✅ **Diagnostic tools exist** but are not integrated into startup sequence

---

# PHASE 1: DRAFT (Current State Audit)

## 1.1 Startup Sequence Analysis

### Entry Points Identified

1. **[`go_live.py`](go_live.py:1)** - Headless Launcher (make run)
   - **Has environment validation** in `check_environment()` function (lines 36-71)
   - Validates: `OPENROUTER_API_KEY`, `ODDS_API_KEY`, `SERPER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - **MISSING:** `BRAVE_API_KEY` (critical for DeepSeek Intel)
   - **Problem:** Only used when running via `make run`, NOT integrated into other entry points
   - **Problem:** Doesn't distinguish "Present but Empty" vs "Missing" (line 57)

2. **[`launcher.py`](src/entrypoints/launcher.py:1)** - Process Orchestrator (Supervisor)
   - Starts: [`main.py`](src/main.py:1), [`run_bot.py`](src/entrypoints/run_bot.py:1), [`run_telegram_monitor.py`](run_telegram_monitor.py:1), [`run_news_radar.py`](run_news_radar.py:1)
   - **No environment validation** before launching subprocesses
   - Only checks file existence, not configuration validity

3. **[`main.py`](src/main.py:1)** - Main Pipeline
   - Loads `.env` at line 36-37
   - **No validation of critical keys** before entering `run_continuous()` loop
   - Only checks for `PAUSE_FILE` before each cycle

4. **[`run_bot.py`](src/entrypoints/run_bot.py:1)** - Telegram Bot
   - Has `test_bot_configuration()` function (lines 70-112)
   - **Only runs with `--test` flag**, not on normal startup
   - Checks: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`

### 1.2.0 Partial Implementation in go_live.py

**[`go_live.py:check_environment()`](go_live.py:36-71)** - Environment Validation

```python
def check_environment() -> bool:
    """Verify .env and required variables."""
    print("[1/3] 🔍 ENVIRONMENT CHECK")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("   ❌ .env file not found!")
        return False
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # Required variables for main pipeline
    required = [
        "OPENROUTER_API_KEY",
        "ODDS_API_KEY",
        "SERPER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]
    missing = [v for v in required if not os.getenv(v) or os.getenv(v, "").startswith("your_")]
    
    if missing:
        print(f"   ❌ Missing: {', '.join(missing)}")
        return False
    
    print("   ✅ All required variables configured")
    
    # Check optional Telegram monitoring
    if os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
        print("   ✅ Telegram monitoring enabled (user client)")
    else:
        print("   ⚠️  Telegram monitoring disabled (no API_ID/HASH)")
    
    return True
```

**PROBLEMS:**
1. **Only used in [`go_live.py`](go_live.py:194)** - Not integrated into [`launcher.py`](src/entrypoints/launcher.py:1) or [`main.py`](src/main.py:1)
2. **Missing critical key:** `BRAVE_API_KEY` is NOT in required list (line 50-56)
3. **Doesn't distinguish "Present but Empty" vs "Missing":** Line 57 uses `not os.getenv(v)` which treats both identically
4. **No graceful degradation:** Optional features are only logged, not tracked or disabled

**Called in:** [`go_live.py:main()`](go_live.py:194) at line 207-208 (exits if validation fails)

### Critical Core Keys Identified

Based on code analysis, these are the **Critical Core Keys** without which the bot is functionally dead:

| Key | Purpose | Criticality | Current Validation |
|-----|---------|-------------|-------------------|
| `ODDS_API_KEY` | Odds data ingestion | **CRITICAL** | Only checked in [`ingest_fixtures.py:552`](src/ingestion/ingest_fixtures.py:552) during runtime |
| `OPENROUTER_API_KEY` | DeepSeek AI analysis | **CRITICAL** | No validation at startup |
| `BRAVE_API_KEY` | Web search for intel | **CRITICAL** | No validation at startup |
| `TELEGRAM_BOT_TOKEN` | Alert notifications | **CRITICAL** | Only in `--test` mode |
| `TELEGRAM_CHAT_ID` | Admin notifications | **CRITICAL** | Only in `--test` mode |
| `SUPABASE_URL` | Database connection | **CRITICAL** | Only in `check_apis.py` diagnostic |

### Optional Keys (Should Degrade Gracefully)

| Key | Purpose | Degradation Behavior |
|-----|---------|---------------------|
| `TELEGRAM_API_ID` | Channel monitoring | Disable Telegram Monitor |
| `TELEGRAM_API_HASH` | Channel monitoring | Disable Telegram Monitor |
| `PERPLEXITY_API_KEY` | Fallback AI search | Use DeepSeek only |
| `API_FOOTBALL_KEY` | Player intelligence | Skip player stats |
| `TAVILY_API_KEY_*` | Match enrichment | Use Brave only |

## 1.2 Current Validation Mechanisms

### 1.2.1 Environment Loading

**[`config/settings.py`](config/settings.py:1)** - Central Configuration

```python
# Line 22-31: Load .env with graceful handling
env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_file):
    load_dotenv(env_file)
    logger.info("✅ Loaded environment from .env file")
else:
    logger.warning(f"⚠️ .env file not found at {env_file}")
    logger.warning("⚠️ Using hardcoded default API keys - system will operate with limited functionality")
```

**PROBLEM:** Uses hardcoded defaults (lines 34-90) when `.env` is missing or incomplete:

```python
# Line 43-52: Inject hardcoded defaults
if not os.getenv("BRAVE_API_KEY_1"):
    os.environ["BRAVE_API_KEY_1"] = "BSA8GEZcqohA9G8L3-p6FJbzin4D-OF"
# ... more hardcoded keys
```

**RISK:** Hardcoded keys may be expired, invalid, or have rate limits exhausted.

### 1.2.2 Diagnostic Tools

**[`src/utils/check_apis.py`](src/utils/check_apis.py:1)** - API Diagnostics

Comprehensive validation script that tests:
- Odds API (lines 51-128)
- Serper API (lines 131-188)
- OpenRouter API (lines 191-242)
- Brave API (lines 245-305)
- Perplexity API (lines 308-359)
- Tavily API (lines 362-422)
- Supabase Database (lines 425-485)
- Continental Orchestrator (lines 488-630)

**PROBLEM:** This script exists but is **NOT integrated** into startup sequence. It's only run manually via `make check-apis`.

### 1.2.3 Entry Point Validation

**[`run_bot.py`](src/entrypoints/run_bot.py:70-112)** - Bot Configuration Test

```python
def test_bot_configuration():
    """Verifica configurazione bot senza avviare."""
    logger.info("🤖 Verifica configurazione Telegram Bot...")
    
    required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            logger.info(f"✅ {var}: Configurato")
```

**PROBLEM:** Only runs with `--test` flag, not on normal startup.

---

# PHASE 2: CROSS-EXAMINATION (Gap Identification)

## 2.1 Why Did the Bot Fail to Report Missing Keys?

### Root Cause Analysis

**Observation:** The bot has experienced boot-time failures and infinite crash loops due to missing/empty keys, but never reported them clearly.

**Investigation:**

1. **No Early Exit Strategy**
   - [`launcher.py`](src/entrypoints/launcher.py:200-219) starts processes immediately without validation
   - [`main.py`](src/main.py:1626-1651) enters `run_continuous()` loop without checking critical keys
   - Errors only occur **during runtime** when providers try to use missing keys

2. **Silent Failures in Providers**
   - [`ingest_fixtures.py:552`](src/ingestion/ingest_fixtures.py:552) checks `ODDS_API_KEY` but only logs warning
   - Providers return empty data instead of raising exceptions
   - System continues running in degraded state without clear indication

3. **Hardcoded Defaults Mask Issues**
   - [`config/settings.py:34-90`](config/settings.py:34-90) injects hardcoded values
   - These may be valid keys but could be expired or rate-limited
   - System appears to work but fails later when quotas are exhausted

4. **No "Present but Empty" Detection**
   - Code checks `if not value:` which treats `""` as falsy
   - But many places use `os.getenv("KEY", "")` which returns empty string
   - Empty string is falsy, so validation passes incorrectly

### Example: The "Amnesia" Pattern

**Scenario:** User sets `OPENROUTER_API_KEY=""` in `.env`

**What happens:**
1. [`config/settings.py:71-72`](config/settings.py:71-72) reads: `OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")`
2. Value is `""` (empty string)
3. Provider code checks: `if not OPENROUTER_API_KEY:` → evaluates to `True`
4. **But** this check happens **inside** the provider during API call
5. System has already started, no clear error message
6. Provider fails silently or logs generic error

**Result:** Bot enters infinite crash loop because:
- [`launcher.py`](src/entrypoints/launcher.py:259-323) detects crash and restarts
- Same missing key causes same crash
- Loop repeats forever with 15-second backoff

## 2.2 Decentralized Validation Problem

### Validation Scattered Across Codebase

| Location | What It Validates | When It Runs |
|-----------|-------------------|--------------|
| [`config/settings.py`](config/settings.py:34-90) | Injects defaults | Module import (immediate) |
| [`run_bot.py:test_bot_configuration()`](src/entrypoints/run_bot.py:70-112) | Telegram keys | `--test` flag only |
| [`check_apis.py`](src/utils/check_apis.py:1) | All APIs | Manual execution only |
| [`ingest_fixtures.py:552`](src/ingestion/ingest_fixtures.py:552) | Odds API | Runtime during fixture ingestion |
| Provider-specific | Individual keys | Runtime during API calls |

**PROBLEM:** No single source of truth for validation at startup.

### Missing Orchestrator/Entry Point Validation

**[`launcher.py`](src/entrypoints/launcher.py:333-392)** - Main Orchestrator

```python
def main():
    """Entry point dell'orchestrator."""
    # ... parse args ...
    
    # Normal startup mode
    logger.info("=" * 60)
    logger.info("🦅 EARLYBIRD V3.7 - ORCHESTRATOR AVVIATO")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Scoperta dinamica dei processi
    logger.info("🔍 Ricerca script disponibili...")
    PROCESSES = discover_processes()
    
    # ❌ NO VALIDATION HERE
    # ❌ NO CHECK FOR CRITICAL ENV VARS
    # ❌ NO PRE-FLIGHT GUARD
    
    # Avvio iniziale
    for key in PROCESSES:
        start_process(key)  # Starts blindly
        time.sleep(2)
```

**[`main.py`](src/main.py:1626-1651)** - Main Pipeline Entry

```python
if __name__ == "__main__":
    args = parse_args()
    
    # Handle special modes
    if args.test:
        success = test_main_configuration()  # ✅ Has validation
        sys.exit(0 if success else 1)
    
    if args.status:
        show_system_status()
        sys.exit(0)
    
    # Emergency cleanup BEFORE any DB operation
    try:
        emergency_cleanup()
    except Exception as e:
        logging.warning(f"⚠️ Emergency cleanup failed: {e}")
    
    # ❌ NO VALIDATION BEFORE run_continuous()
    # ❌ NO CHECK FOR CRITICAL ENV VARS
    # ❌ NO PRE-FLIGHT GUARD
    
    # Normal startup
    try:
        run_continuous()  # Enters loop blindly
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested by user")
```

## 2.3 "Present but Empty" vs "Missing" Key Handling

### Current Behavior Analysis

**Missing Key (`None`):**
```python
value = os.getenv("NONEXISTENT_KEY")  # Returns None
if not value:  # Evaluates to True
    # Validation passes (falsy check)
```

**Present but Empty (`""`):**
```python
os.environ["EMPTY_KEY"] = ""
value = os.getenv("EMPTY_KEY")  # Returns ""
if not value:  # Evaluates to True
# Validation passes (empty string is falsy)
```

**PROBLEM:** Both cases are treated identically, but they have different implications:
- **Missing:** User forgot to set the key
- **Empty:** User explicitly set it to empty (intentional or mistake)

### No Distinction in Error Messages

When validation fails, the error message doesn't distinguish:
```python
# Typical validation pattern
if not ODDS_API_KEY:
    logging.error("ODDS_API_KEY not configured")
    # ❌ Doesn't say if it's missing or empty
```

### No Explicit Empty String Check

Code should explicitly check for empty string:
```python
if ODDS_API_KEY is None:
    logging.error("ODDS_API_KEY is missing from .env")
elif ODDS_API_KEY == "":
    logging.error("ODDS_API_KEY is present but empty in .env")
```

---

# PHASE 3: VERIFICATION (Path Tracing)

## 3.1 Execution Path: Launcher → Main Loop

### Step-by-Step Trace

**Step 1: User runs `make run-launcher`**

```bash
make run-launcher
→ python src/entrypoints/launcher.py
```

**Step 2: [`launcher.py:main()`](src/entrypoints/launcher.py:333)** executes

```python
def main():
    args = parse_args()
    
    # Skip test/status modes
    # ...
    
    # ❌ NO VALIDATION HERE
    logger.info("🦅 EARLYBIRD V3.7 - ORCHESTRATOR AVVIATO")
    
    PROCESSES = discover_processes()  # Find scripts
    
    # ❌ NO CHECK FOR CRITICAL ENV VARS
    # ❌ NO PRE-FLIGHT GUARD
```

**Step 3: [`launcher.py:start_process()`](src/entrypoints/launcher.py:200)** launches subprocesses

```python
def start_process(key: str) -> subprocess.Popen:
    config = PROCESSES[key]
    logger.info(f"🚀 Avvio {config['name']}...")
    
    # ❌ NO VALIDATION BEFORE LAUNCH
    process = subprocess.Popen(
        config["cmd"],  # e.g., [sys.executable, "src/main.py"]
        stdout=sys.stdout,
        stderr=sys.stderr,
        bufsize=1,
        universal_newlines=True,
        start_new_session=True,
    )
    
    config["process"] = process
    logger.info(f"✅ {config['name']} avviato (PID: {process.pid})")
    return process
```

**Step 4: [`main.py:__main__`](src/main.py:1626)** executes in subprocess

```python
if __name__ == "__main__":
    args = parse_args()
    
    # Skip test/status modes
    # ...
    
    # ❌ NO VALIDATION BEFORE run_continuous()
    try:
        run_continuous()  # Enters loop blindly
```

**Step 5: [`main.py:run_continuous()`](src/main.py:1132)** enters main loop

```python
def run_continuous():
    """Continuous loop - runs pipeline every hour"""
    logging.info("🦅 EARLYBIRD NEWS & ODDS MONITOR - 24/7 MODE ACTIVATED")
    
    # Initialize services
    health = get_health_monitor()
    optimizer = get_optimizer()
    
    # ❌ NO VALIDATION OF CRITICAL KEYS
    # ❌ NO CHECK BEFORE INITIALIZING SERVICES
    
    while True:
        cycle_count += 1
        
        # Check for pause lock file
        if os.path.exists(PAUSE_FILE):
            # ...
        
        try:
            # Run pipeline
            run_pipeline()  # ❌ Errors occur here when keys are missing
```

**Step 6: [`main.py:run_pipeline()`](src/main.py:717)** executes pipeline

```python
def run_pipeline():
    logging.info("🚀 STARTING EARLYBIRD V6.1 PIPELINE...")
    
    # ❌ NO VALIDATION AT PIPELINE START
    
    # Initialize database
    init_db()  # ✅ Works (SQLite)
    
    # Initialize FotMob provider
    try:
        fotmob = get_data_provider()  # May fail if keys missing
    except Exception as e:
        logging.error(f"Failed to initialize FotMob: {e}")
        fotmob = None  # ❌ Continues with None
    
    # Ingest fixtures
    logging.info("📊 Refreshing fixtures and odds from The-Odds-API...")
    ingest_fixtures(use_auto_discovery=True)  # ❌ FAILS HERE if ODDS_API_KEY missing
```

**Step 7: [`ingest_fixtures.py`](src/ingestion/ingest_fixtures.py:552) checks key

```python
# Line 552
if ODDS_API_KEY == "YOUR_ODDS_API_KEY" or not ODDS_API_KEY:
    if os.getenv("USE_MOCK_DATA") == "true":
        logging.warning("Odds API Key not set (or MOCK flag). Using MOCK data.")
    # ❌ NO EXPLICIT ERROR OR EXIT
    # ❌ CONTINUES WITH EMPTY DATA
```

**Step 8: Crash occurs**

```python
# API call fails with 401 Unauthorized
response = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=15)
# ODDS_API_KEY is "" or invalid → 401 error
```

**Step 9: Process crashes**

```python
# Unhandled exception or caught and logged
logging.error(f"API call failed: {e}")
# Process exits with non-zero code
```

**Step 10: [`launcher.py:check_and_restart()`](src/entrypoints/launcher.py:259)** detects crash

```python
elif process.poll() is not None:  # Process is dead
    exit_code = process.returncode
    config["restarts"] += 1
    
    # CPU PROTECTION: If crash within 10 seconds
    if uptime_before_crash < CRASH_DETECTION_WINDOW:
        backoff_seconds = max(
            MINIMUM_BACKOFF_FOR_FAST_CRASH, 
            min(60, 2 ** min(restarts, 6))
        )
        logger.warning(
            f"⚠️ {config['name']} crashato in {uptime_before_crash:.1f}s "
            f"(exit code: {exit_code}). "
            f"CPU PROTECTION: Riavvio #{restarts} in {backoff_seconds}s..."
        )
    
    # ❌ NO CHECK FOR CONFIGURATION ERRORS
    # ❌ ASSUMES IT'S A TRANSIENT ERROR
    # ❌ RESTARTS WITH SAME MISSING KEYS
    
    time.sleep(backoff_seconds)
    start_process(key)  # ❌ RESTARTS WITH SAME PROBLEM
```

**Result:** Infinite crash loop with 15-second backoff.

## 3.2 Point of No Return

### Critical Decision Points

**Point 1: [`launcher.py:main()`](src/entrypoints/launcher.py:333)** - Orchestrator Start
- **Current:** No validation, launches processes immediately
- **Should be:** Validate critical keys before any process launch
- **Impact:** Prevents all subprocesses from starting with invalid config

**Point 2: [`main.py:__main__`](src/main.py:1626)** - Main Pipeline Start
- **Current:** No validation, enters `run_continuous()` immediately
- **Should be:** Validate critical keys before entering loop
- **Impact:** Prevents main pipeline from running with invalid config

**Point 3: [`main.py:run_continuous()`](src/main.py:1132)** - Loop Entry
- **Current:** No validation, initializes services blindly
- **Should be:** Validate critical keys before initializing services
- **Impact:** Prevents service initialization failures

**Point 4: [`main.py:run_pipeline()`](src/main.py:717)** - Pipeline Start
- **Current:** No validation, starts pipeline immediately
- **Should be:** Validate critical keys before pipeline execution
- **Impact:** Prevents pipeline execution failures

### Recommended Point of No Return

**Best location:** [`launcher.py:main()`](src/entrypoints/launcher.py:333) before `discover_processes()`

**Reasoning:**
1. Single entry point for all processes
2. Prevents ANY process from starting with invalid config
3. Clear error message before any subprocess launches
4. Easy to implement and maintain

**Alternative:** [`main.py:__main__`](src/main.py:1626) before `run_continuous()`

**Reasoning:**
1. Validates each process independently
2. Allows selective startup (e.g., bot without main pipeline)
3. More granular error reporting

## 3.3 Graceful Degradation Analysis

### Features That Should Auto-Disable

Based on code analysis, these features should automatically disable if their keys are missing:

| Feature | Key(s) Required | Current Behavior | Should Behavior |
|---------|-----------------|------------------|-----------------|
| Telegram Monitor | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Fails during startup | Disable monitor, log warning |
| Player Intelligence | `API_FOOTBALL_KEY` | Fails during analysis | Skip player stats, continue |
| Perplexity Fallback | `PERPLEXITY_API_KEY` | Fails during search | Use DeepSeek only |
| Tavily Enrichment | `TAVILY_API_KEY_*` | Fails during enrichment | Use Brave only |
| Supabase Mirror | `SUPABASE_URL`, `SUPABASE_KEY` | Fails during refresh | Use local mirror only |

### Features That Require Hard Stop

These features are **critical** and should prevent startup if missing:

| Feature | Key(s) Required | Reason |
|---------|-----------------|---------|
| Odds Ingestion | `ODDS_API_KEY` | Core data source |
| AI Analysis | `OPENROUTER_API_KEY` | Core intelligence |
| Web Search | `BRAVE_API_KEY` | Required for intel |
| Telegram Alerts | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Core communication |

### Current Degradation Implementation

**No graceful degradation exists.** All services fail hard if keys are missing.

**Example:** [`run_bot.py:test_bot_configuration()`](src/entrypoints/run_bot.py:70-112)

```python
def test_bot_configuration():
    """Verifica configurazione bot senza avviare."""
    # ...
    required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Variabili mancanti: {', '.join(missing_vars)}")
        return False  # ❌ Hard stop, no graceful degradation
    
    # ❌ No distinction between critical and optional keys
```

---

# PHASE 4: FINAL RECOMMENDATION

## 4.1 Centralized Startup Validator Strategy

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINT                            │
│              (launcher.py / main.py)                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────┐
        │  STARTUP VALIDATOR (NEW)   │
        │  src/utils/startup_validator.py │
        └────────────┬───────────────┘
                     │
                     ▼
        ┌──────────────────────────────┐
        │  VALIDATION CHECKS          │
        └────────────┬───────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌───────────────┐       ┌──────────────────┐
│ CRITICAL KEYS │       │ OPTIONAL KEYS   │
│ (Hard Stop)   │       │ (Graceful Deg.) │
└───────────────┘       └──────────────────┘
        │                         │
        ▼                         ▼
┌───────────────┐       ┌──────────────────┐
│ FAIL → EXIT   │       │ WARN → DISABLE  │
└───────────────┘       └──────────────────┘
```

### Implementation Plan

#### Step 1: Create Startup Validator Module

**File:** `src/utils/startup_validator.py`

```python
"""
EarlyBird Startup Validator - Pre-Flight Guard

Validates all environment variables before system startup.
Provides clear, actionable error messages and graceful degradation.
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

class ValidationStatus(Enum):
    """Validation result status."""
    READY = "✅ READY"
    FAIL = "❌ FAIL"
    WARN = "⚠️ WARN"

@dataclass
class ValidationResult:
    """Result of validating a single configuration item."""
    key: str
    status: ValidationStatus
    message: str
    is_critical: bool
    is_empty: bool  # Distinguish missing vs empty

@dataclass
class StartupValidationReport:
    """Complete startup validation report."""
    critical_results: List[ValidationResult]
    optional_results: List[ValidationResult]
    overall_status: ValidationStatus
    summary: str

class StartupValidator:
    """
    Centralized startup validator for EarlyBird system.
    
    Performs pre-flight checks on all environment variables
    and provides clear, actionable error messages.
    """
    
    # Critical keys - system cannot function without these
    CRITICAL_KEYS = {
        "ODDS_API_KEY": {
            "description": "Odds API (The-Odds-API.com)",
            "validation": lambda v: v and v != "YOUR_ODDS_API_KEY",
            "error_msg": "Odds API key is missing or invalid",
        },
        "OPENROUTER_API_KEY": {
            "description": "OpenRouter API (DeepSeek AI)",
            "validation": lambda v: v and v != "YOUR_OPENROUTER_API_KEY",
            "error_msg": "OpenRouter API key is missing or invalid",
        },
        "BRAVE_API_KEY": {
            "description": "Brave Search API",
            "validation": lambda v: v and v != "YOUR_BRAVE_API_KEY",
            "error_msg": "Brave API key is missing or invalid",
        },
        "TELEGRAM_BOT_TOKEN": {
            "description": "Telegram Bot Token",
            "validation": lambda v: v and v != "YOUR_TELEGRAM_BOT_TOKEN",
            "error_msg": "Telegram Bot Token is missing or invalid",
        },
        "TELEGRAM_CHAT_ID": {
            "description": "Telegram Chat ID (Admin)",
            "validation": lambda v: v and v.isdigit(),
            "error_msg": "Telegram Chat ID is missing or invalid",
        },
    }
    
    # Optional keys - system can degrade gracefully
    OPTIONAL_KEYS = {
        "TELEGRAM_API_ID": {
            "description": "Telegram API ID (Channel Monitoring)",
            "validation": lambda v: v and v.isdigit(),
            "error_msg": "Telegram API ID is missing - channel monitoring disabled",
            "disable_feature": "telegram_monitor",
        },
        "TELEGRAM_API_HASH": {
            "description": "Telegram API Hash (Channel Monitoring)",
            "validation": lambda v: v and len(v) > 10,
            "error_msg": "Telegram API Hash is missing - channel monitoring disabled",
            "disable_feature": "telegram_monitor",
        },
        "PERPLEXITY_API_KEY": {
            "description": "Perplexity API (Fallback AI Search)",
            "validation": lambda v: v and v != "YOUR_PERPLEXITY_API_KEY",
            "error_msg": "Perplexity API key is missing - using DeepSeek only",
            "disable_feature": "perplexity_fallback",
        },
        "API_FOOTBALL_KEY": {
            "description": "API-Football (Player Intelligence)",
            "validation": lambda v: v and v != "YOUR_API_FOOTBALL_KEY",
            "error_msg": "API-Football key is missing - player stats disabled",
            "disable_feature": "player_intelligence",
        },
        "SUPABASE_URL": {
            "description": "Supabase Database URL",
            "validation": lambda v: v and v.startswith("https://"),
            "error_msg": "Supabase URL is missing - using local mirror only",
            "disable_feature": "supabase_sync",
        },
        "SUPABASE_KEY": {
            "description": "Supabase Database Key",
            "validation": lambda v: v and len(v) > 20,
            "error_msg": "Supabase key is missing - using local mirror only",
            "disable_feature": "supabase_sync",
        },
    }
    
    def __init__(self):
        """Initialize validator."""
        self.disabled_features = set()
    
    def validate_key(self, key: str, config: dict, is_critical: bool) -> ValidationResult:
        """
        Validate a single environment variable.
        
        Args:
            key: Environment variable name
            config: Configuration dict with validation rules
            is_critical: Whether this is a critical key
            
        Returns:
            ValidationResult with status and message
        """
        value = os.getenv(key, "")
        
        # Check if missing (None) vs empty ("")
        is_empty = value == ""
        is_missing = value is None or value == ""
        
        # Distinguish between missing and empty
        if is_missing:
            status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
            message = f"{key}: MISSING from .env"
            is_empty = True  # Treat missing as empty for reporting
        elif is_empty:
            status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
            message = f"{key}: PRESENT BUT EMPTY in .env"
        else:
            # Run custom validation
            validation_func = config["validation"]
            if validation_func(value):
                status = ValidationStatus.READY
                message = f"{key}: OK ({config['description']})"
                is_empty = False
            else:
                status = ValidationStatus.FAIL if is_critical else ValidationStatus.WARN
                message = f"{key}: {config['error_msg']}"
                is_empty = True
        
        # Track disabled features
        if status in (ValidationStatus.WARN, ValidationStatus.FAIL) and not is_critical:
            feature = config.get("disable_feature")
            if feature:
                self.disabled_features.add(feature)
        
        return ValidationResult(
            key=key,
            status=status,
            message=message,
            is_critical=is_critical,
            is_empty=is_empty,
        )
    
    def validate_all(self) -> StartupValidationReport:
        """
        Validate all environment variables.
        
        Returns:
            StartupValidationReport with complete results
        """
        critical_results = []
        optional_results = []
        
        # Validate critical keys
        for key, config in self.CRITICAL_KEYS.items():
            result = self.validate_key(key, config, is_critical=True)
            critical_results.append(result)
        
        # Validate optional keys
        for key, config in self.OPTIONAL_KEYS.items():
            result = self.validate_key(key, config, is_critical=False)
            optional_results.append(result)
        
        # Determine overall status
        critical_failures = [r for r in critical_results if r.status == ValidationStatus.FAIL]
        if critical_failures:
            overall_status = ValidationStatus.FAIL
            summary = f"❌ CRITICAL FAILURES: {len(critical_failures)} critical keys missing/invalid"
        else:
            overall_status = ValidationStatus.READY
            warnings = [r for r in optional_results if r.status == ValidationStatus.WARN]
            if warnings:
                summary = f"⚠️ READY WITH WARNINGS: {len(warnings)} optional features disabled"
            else:
                summary = "✅ READY: All critical keys configured"
        
        return StartupValidationReport(
            critical_results=critical_results,
            optional_results=optional_results,
            overall_status=overall_status,
            summary=summary,
        )
    
    def print_handshake_report(self, report: StartupValidationReport) -> None:
        """
        Print human-readable "Handshake Report" to terminal.
        
        Args:
            report: StartupValidationReport to display
        """
        print("\n" + "=" * 70)
        print("🦅 EARLYBIRD STARTUP VALIDATION - PRE-FLIGHT HANDSHAKE")
        print("=" * 70)
        
        # Print summary
        print(f"\n{report.summary}\n")
        
        # Print critical keys
        print("🔴 CRITICAL KEYS (Required for Operation):")
        print("-" * 70)
        for result in report.critical_results:
            icon = result.status.value[:2]  # ✅ or ❌
            print(f"{icon} {result.message}")
        
        # Print optional keys
        print("\n🟡 OPTIONAL KEYS (Graceful Degradation):")
        print("-" * 70)
        for result in report.optional_results:
            icon = result.status.value[:2]  # ✅ or ⚠️
            print(f"{icon} {result.message}")
        
        # Print disabled features
        if self.disabled_features:
            print(f"\n⚙️  DISABLED FEATURES: {', '.join(sorted(self.disabled_features))}")
        
        print("\n" + "=" * 70)
    
    def should_exit(self, report: StartupValidationReport) -> bool:
        """
        Determine if system should exit based on validation results.
        
        Args:
            report: StartupValidationReport to evaluate
            
        Returns:
            True if system should exit, False otherwise
        """
        return report.overall_status == ValidationStatus.FAIL


def validate_startup() -> StartupValidationReport:
    """
    Convenience function to validate startup configuration.
    
    Returns:
        StartupValidationReport with validation results
    """
    validator = StartupValidator()
    report = validator.validate_all()
    validator.print_handshake_report(report)
    return report


def validate_startup_or_exit() -> None:
    """
    Validate startup configuration and exit if critical failures found.
    
    This is the main entry point for startup validation.
    Call this at the beginning of main() or launcher.py:main()
    """
    validator = StartupValidator()
    report = validator.validate_all()
    validator.print_handshake_report(report)
    
    if validator.should_exit(report):
        print("\n❌ STARTUP ABORTED: Fix critical configuration errors before retrying")
        print("💡 Run 'make check-apis' for detailed API diagnostics")
        sys.exit(1)
    
    print("\n✅ STARTUP VALIDATION PASSED: System ready to launch")
```

#### Step 2: Integrate into Entry Points

**Modify [`launcher.py:main()`](src/entrypoints/launcher.py:333):**

```python
def main():
    """Entry point dell'orchestrator."""
    global _shutdown_requested, PROCESSES

    # Parse arguments
    args = parse_args()

    # Handle special modes
    if args.test:
        return 0 if check_component_health() else 1

    if args.status:
        show_process_status()
        return 0

    # ✅ NEW: Pre-flight validation BEFORE launching any processes
    try:
        from src.utils.startup_validator import validate_startup_or_exit
        validate_startup_or_exit()
    except ImportError as e:
        logger.warning(f"⚠️ Startup validator not available: {e}")
        logger.warning("⚠️ Proceeding without validation checks")
    
    # Normal startup mode
    logger.info("=" * 60)
    logger.info("🦅 EARLYBIRD V3.7 - ORCHESTRATOR AVVIATO")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # ... rest of main() ...
```

**Modify [`main.py:__main__`](src/main.py:1626):**

```python
if __name__ == "__main__":
    # Parse arguments
    args = parse_args()

    # Handle special modes
    if args.test:
        success = test_main_configuration()
        sys.exit(0 if success else 1)

    if args.status:
        show_system_status()
        sys.exit(0)

    # ✅ NEW: Pre-flight validation BEFORE entering main loop
    try:
        from src.utils.startup_validator import validate_startup_or_exit
        validate_startup_or_exit()
    except ImportError as e:
        logging.warning(f"⚠️ Startup validator not available: {e}")
        logging.warning("⚠️ Proceeding without validation checks")

    # Emergency cleanup BEFORE any DB operation
    try:
        emergency_cleanup()
    except Exception as e:
        logging.warning(f"⚠️ Emergency cleanup failed: {e}")

    # Normal startup
    try:
        run_continuous()
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested by user")
    except Exception as e:
        logging.critical(f"💀 FATAL ERROR - SYSTEM CRASH: {type(e).__name__}: {e}", exc_info=True)
        raise
```

#### Step 3: Implement Graceful Degradation

**Modify [`run_bot.py:main()`](src/entrypoints/run_bot.py:530):**

```python
async def main():
    """Main entry point for Telegram bot."""
    # Parse arguments
    args = parse_args()

    # Handle special modes
    if args.test:
        success = test_bot_configuration()
        sys.exit(0 if success else 1)

    # ✅ NEW: Check if bot should be disabled
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "":
        logger.error("❌ TELEGRAM_BOT_TOKEN not configured - Bot disabled")
        logger.info("💡 Set TELEGRAM_BOT_TOKEN in .env to enable bot")
        sys.exit(1)
    
    # Check if channel monitoring should be disabled
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.warning("⚠️ Telegram API credentials not configured")
        logger.warning("⚠️ Bot commands enabled, but channel monitoring disabled")
        # Continue with bot commands only
    
    # ... rest of main() ...
```

#### Step 4: Update Makefile

**Add new target to [`Makefile`](Makefile:1):**

```makefile
.PHONY: help test test-unit test-integration test-regression test-coverage test-continental
.PHONY: setup setup-python setup-system install setup-telegram-auth
.PHONY: run run-launcher run-main run-bot run-news-radar run-telegram-monitor
.PHONY: check-apis check-health check-database check-startup
.PHONY: clean clean-db clean-all
.PHONY: migrate lint fix format

# ...

help:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Earlybird Project - Available Commands$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BOLD)Test Commands:$(COLOR_RESET)"
	@echo "  make test              - Run all tests"
	# ...
	@echo "$(COLOR_BOLD)Diagnostics Commands:$(COLOR_RESET)"
	@echo "  make check-apis        - API Diagnostics"
	@echo "  make check-startup      - Startup Validation (Pre-Flight Guard)"
	@echo "  make check-health      - System health check"
	@echo "  make check-database    - Database integrity check"
	# ...

check-startup: check-env
	@echo "$(COLOR_GREEN)Running startup validation...$(COLOR_RESET)"
	@$(PYTHON) -c "from src.utils.startup_validator import validate_startup_or_exit; validate_startup_or_exit()"
```

## 4.2 Handshake Report Example

### Example Output: All Systems Go

```
======================================================================
🦅 EARLYBIRD STARTUP VALIDATION - PRE-FLIGHT HANDSHAKE
======================================================================

✅ READY: All critical keys configured

🔴 CRITICAL KEYS (Required for Operation):
----------------------------------------------------------------------
✅ ODDS_API_KEY: OK (Odds API (The-Odds-API.com))
✅ OPENROUTER_API_KEY: OK (OpenRouter API (DeepSeek AI))
✅ BRAVE_API_KEY: OK (Brave Search API)
✅ TELEGRAM_BOT_TOKEN: OK (Telegram Bot Token)
✅ TELEGRAM_CHAT_ID: OK (Telegram Chat ID (Admin))

🟡 OPTIONAL KEYS (Graceful Degradation):
----------------------------------------------------------------------
✅ TELEGRAM_API_ID: OK (Telegram API ID (Channel Monitoring))
✅ TELEGRAM_API_HASH: OK (Telegram API Hash (Channel Monitoring))
✅ PERPLEXITY_API_KEY: OK (Perplexity API (Fallback AI Search))
✅ API_FOOTBALL_KEY: OK (API-Football (Player Intelligence))
✅ SUPABASE_URL: OK (Supabase Database URL)
✅ SUPABASE_KEY: OK (Supabase Database Key)

======================================================================

✅ STARTUP VALIDATION PASSED: System ready to launch
```

### Example Output: Critical Failures

```
======================================================================
🦅 EARLYBIRD STARTUP VALIDATION - PRE-FLIGHT HANDSHAKE
======================================================================

❌ CRITICAL FAILURES: 2 critical keys missing/invalid

🔴 CRITICAL KEYS (Required for Operation):
----------------------------------------------------------------------
❌ ODDS_API_KEY: MISSING from .env
❌ OPENROUTER_API_KEY: PRESENT BUT EMPTY in .env
✅ BRAVE_API_KEY: OK (Brave Search API)
✅ TELEGRAM_BOT_TOKEN: OK (Telegram Bot Token)
✅ TELEGRAM_CHAT_ID: OK (Telegram Chat ID (Admin))

🟡 OPTIONAL KEYS (Graceful Degradation):
----------------------------------------------------------------------
⚠️ TELEGRAM_API_ID: MISSING from .env - channel monitoring disabled
⚠️ TELEGRAM_API_HASH: MISSING from .env - channel monitoring disabled
✅ PERPLEXITY_API_KEY: OK (Perplexity API (Fallback AI Search))
✅ API_FOOTBALL_KEY: OK (API-Football (Player Intelligence))
✅ SUPABASE_URL: OK (Supabase Database URL)
✅ SUPABASE_KEY: OK (Supabase Database Key)

⚙️  DISABLED FEATURES: telegram_monitor

======================================================================

❌ STARTUP ABORTED: Fix critical configuration errors before retrying
💡 Run 'make check-apis' for detailed API diagnostics
```

## 4.3 Benefits of Centralized Validation

### 1. **Prevents Infinite Crash Loops**
- Validation happens **before** any process starts
- Clear error messages at T-0
- No silent failures or ambiguous logs

### 2. **Distinguishes Missing vs Empty Keys**
- Explicit checks for `None` vs `""`
- Clear error messages for each case
- Helps users identify configuration mistakes

### 3. **Graceful Degradation**
- Optional features auto-disable when keys are missing
- System continues with reduced functionality
- Clear indication of which features are disabled

### 4. **Human-Readable Handshake Report**
- Terminal-friendly table format
- Color-coded status indicators
- Actionable error messages

### 5. **Single Source of Truth**
- All validation logic in one module
- Easy to maintain and update
- Consistent behavior across all entry points

### 6. **Integration with Existing Tools**
- Works alongside `make check-apis`
- Can be extended with additional checks
- No breaking changes to existing code

## 4.4 Implementation Priority

### Phase 1: Critical Validation (Week 1)
1. Create `src/utils/startup_validator.py`
2. Integrate into [`launcher.py:main()`](src/entrypoints/launcher.py:333)
3. Integrate into [`main.py:__main__`](src/main.py:1626)
4. Add `make check-startup` target

### Phase 2: Graceful Degradation (Week 2)
1. Implement feature disable flags in providers
2. Update [`run_bot.py`](src/entrypoints/run_bot.py:1) to handle disabled features
3. Update [`main.py`](src/main.py:1) to skip disabled features
4. Test degradation scenarios

### Phase 3: Enhanced Diagnostics (Week 3)
1. Add API connectivity tests to validator
2. Add quota checking for rate-limited APIs
3. Add configuration file validation
4. Generate detailed diagnostic report

---

# CONCLUSION

## Summary of Findings

The EarlyBird system has **partial startup validation** in [`go_live.py`](go_live.py:36-71) but suffers from critical gaps:

**Current State:**
- ⚠️ **Partial validator exists** in [`go_live.py`](go_live.py:36-71) but is incomplete
- ❌ **Not integrated** into [`launcher.py`](src/entrypoints/launcher.py:1) or [`main.py`](src/main.py:1)
- ❌ **Missing critical keys** from validation (e.g., `BRAVE_API_KEY`)
- ❌ **No distinction** between "Present but Empty" vs "Missing" keys
- ❌ **No graceful degradation** strategy for optional features
- ❌ **Validation logic scattered** across multiple files

**Resulting Issues:**
- ❌ Infinite crash loops when critical keys are missing (in launcher.py/main.py)
- ❌ Silent failures when keys are empty or invalid
- ❌ Ambiguous error messages don't guide users to fix configuration

## Recommended Solution

Implement a **centralized Startup Validator** (`src/utils/startup_validator.py`) that:
- ✅ Validates all critical keys before any process starts
- ✅ Distinguishes between missing and empty keys
- ✅ Provides human-readable "Handshake Report" at T-0
- ✅ Implements graceful degradation for optional features
- ✅ Prevents infinite crash loops
- ✅ Integrates seamlessly with existing entry points

## Next Steps

1. **Review this report** and confirm the analysis
2. **Approve the implementation plan** outlined in Phase 4
3. **Create the startup validator module** following the specification
4. **Integrate into entry points** (launcher.py, main.py)
5. **Test with various configuration scenarios**
6. **Deploy and monitor** for improved startup reliability

---

**Report Generated:** 2026-02-14  
**Analysis Mode:** Chain of Verification (CoVe)  
**Status:** Awaiting User Approval for Implementation
