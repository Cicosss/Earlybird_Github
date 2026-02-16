# Phase 3: Enhanced Diagnostics Implementation

**Date:** 2026-02-15
**Status:** ✅ Completed
**Mode:** Chain of Verification (CoVe)

---

## Executive Summary

Phase 3 of the COVE Startup Validation Analysis has been successfully implemented. The Enhanced Diagnostics layer extends the existing startup validator with advanced features including API connectivity testing, quota monitoring, configuration file validation, and comprehensive diagnostic reporting.

---

## Implementation Overview

### Core Components

1. **API Connectivity Testing** - Real-time connectivity tests for all critical APIs
2. **Quota Monitoring** - Automatic extraction and display of API quota information
3. **Configuration File Validation** - Automated validation of all configuration files
4. **Detailed Diagnostic Reports** - Comprehensive reports with actionable recommendations

---

## 1. API Connectivity Tests

### Implemented APIs

#### 1.1 Odds API (The-Odds-API.com)
- **Endpoint:** `https://api.the-odds-api.com/v4/sports`
- **Method:** GET with API key authentication
- **Features:**
  - Connectivity test with response time measurement
  - Quota extraction from response headers (`x-requests-used`, `x-requests-remaining`)
  - Error handling for 401 Unauthorized, timeout, and network errors
- **Example Output:**
  ```
  ✅ Odds API: 531ms | 212 used, 19788 remaining
  ```

#### 1.2 OpenRouter API (DeepSeek AI)
- **Endpoint:** `https://openrouter.ai/api/v1/chat/completions`
- **Method:** POST with Bearer token authentication
- **Features:**
  - Test query with minimal token usage
  - Response time measurement
  - Quota extraction from `x-ratelimit-remaining` header (if available)
  - Timeout handling (30s timeout is acceptable for LLMs)
- **Example Output:**
  ```
  ✅ OpenRouter API: 2220ms
  ```

#### 1.3 Brave Search API
- **Endpoint:** `https://api.search.brave.com/res/v1/web/search`
- **Method:** GET with subscription token authentication
- **Features:**
  - Multi-key testing (supports 3 keys: `BRAVE_API_KEY_1`, `_2`, `_3`)
  - Average response time calculation across working keys
  - Working key count reporting
  - Rate limit detection (429 status)
- **Example Output:**
  ```
  ✅ Brave API: 671ms | 3/3 keys working
  ```

#### 1.4 Supabase Database
- **Endpoint:** `{SUPABASE_URL}/rest/v1/`
- **Method:** GET with API key authentication
- **Features:**
  - Connection test with response time
  - Optional service (warns if not configured)
  - Basic authentication validation
- **Example Output:**
  ```
  ✅ Supabase: 1776ms
  ```

### API Test Implementation Details

All API tests follow a consistent pattern:

```python
def test_api_connectivity(self) -> APIConnectivityResult:
    """Test API connectivity and quota."""
    api_key = os.getenv("API_KEY", "")

    if not api_key or api_key == "YOUR_API_KEY":
        return APIConnectivityResult(
            api_name="API Name",
            status=ValidationStatus.FAIL,
            response_time_ms=None,
            quota_info=None,
            error_message="API key not configured",
        )

    try:
        start_time = datetime.now()
        # Make API request
        response = requests.get(url, timeout=15)
        response_time = (datetime.now() - start_time).total_seconds() * 1000

        # Handle errors
        if response.status_code == 401:
            return APIConnectivityResult(..., error_message="Invalid API key")

        if response.status_code != 200:
            return APIConnectivityResult(..., error_message=f"HTTP {response.status_code}")

        # Extract quota info
        quota_info = extract_quota_info(response.headers)

        return APIConnectivityResult(
            api_name="API Name",
            status=ValidationStatus.READY,
            response_time_ms=response_time,
            quota_info=quota_info,
            error_message=None,
        )

    except requests.exceptions.Timeout:
        return APIConnectivityResult(..., error_message="Connection timeout")
    except Exception as e:
        return APIConnectivityResult(..., error_message=str(e))
```

---

## 2. Quota Monitoring

### Quota Information Extraction

#### 2.1 Odds API
- **Headers:** `x-requests-used`, `x-requests-remaining`
- **Format:** `{used} used, {remaining} remaining`
- **Example:** `212 used, 19788 remaining`

#### 2.2 OpenRouter API
- **Headers:** `x-ratelimit-remaining` (if available)
- **Format:** `{remaining} requests remaining`
- **Example:** `1000 requests remaining`

#### 2.3 Brave API
- **Format:** `{working_keys}/3 keys working`
- **Example:** `3/3 keys working`

### Quota Monitoring Benefits

1. **Proactive Alerting:** Users can see quota status before running out
2. **Cost Management:** Track API usage across multiple keys
3. **Capacity Planning:** Understand remaining quota for operations
4. **Multi-Key Management:** See which keys are working (Brave API)

---

## 3. Configuration File Validation

### Validated Files

| File | Description | Min Size | Critical | JSON Validation |
|------|-------------|----------|----------|-----------------|
| `.env` | Environment variables | 100 bytes | Yes | No |
| `config/settings.py` | System settings | 1000 bytes | Yes | No |
| `config/news_radar_sources.json` | News radar sources | 100 bytes | No | Yes |
| `config/browser_sources.json` | Browser sources | 100 bytes | No | Yes |

### Validation Checks

#### 3.1 File Existence
- Checks if file exists at specified path
- Returns FAIL if critical file is missing
- Returns WARN if optional file is missing

#### 3.2 File Size
- Validates minimum file size requirements
- Warns if file is too small (likely incomplete or corrupted)

#### 3.3 JSON Syntax (for .json files)
- Parses JSON to validate syntax
- Returns FAIL with detailed error message if invalid

#### 3.4 Last Modified Timestamp
- Records file modification time
- Helps identify stale configuration files

### Example Output
```
✅ .env: 3374 bytes | Modified: 2026-02-14 21:52:57
✅ config/settings.py: 25734 bytes | Modified: 2026-02-14 15:28:54
✅ config/news_radar_sources.json: 13330 bytes | Modified: 2026-02-06 22:09:20
✅ config/browser_sources.json: 6171 bytes | Modified: 2026-01-28 22:33:41
```

---

## 4. Detailed Diagnostic Reports

### Report Types

#### 4.1 Handshake Report (Default)
- **Purpose:** Quick startup validation
- **Content:**
  - Overall status summary
  - Critical keys status
  - Optional keys status
  - Disabled features list
  - API connectivity summary
  - Configuration files summary
- **Use Case:** Normal startup sequence

#### 4.2 Detailed Diagnostic Report
- **Purpose:** Comprehensive system diagnostics
- **Content:**
  - All handshake report content
  - Detailed environment variable information (status, criticality, emptiness)
  - Detailed API connectivity results (response times, quota info, errors)
  - Detailed configuration file results (size, modification time, errors)
  - Disabled features list
  - Actionable recommendations
- **Use Case:** Troubleshooting, system health checks

### Report Sections

#### Section 1: Environment Variables
```
🔧 ENVIRONMENT VARIABLES
======================================================================

🔴 CRITICAL KEYS:
----------------------------------------------------------------------
✅ ODDS_API_KEY
   Status: ✅ READY
   Message: ODDS_API_KEY: OK (Odds API (The-Odds-API.com))
   Critical: True
   Empty: False

🟡 OPTIONAL KEYS:
----------------------------------------------------------------------
⚠️ API_FOOTBALL_KEY
   Status: ⚠️ WARN
   Message: API_FOOTBALL_KEY: MISSING from .env
   Critical: False
   Empty: True
```

#### Section 2: API Connectivity Tests
```
🌐 API CONNECTIVITY TESTS
======================================================================
✅ Odds API
   Status: ✅ READY
   Response Time: 530.86ms
   Quota Info: 212 used, 19788 remaining

✅ OpenRouter API
   Status: ✅ READY
   Response Time: 2219.53ms
```

#### Section 3: Configuration Files
```
📁 CONFIGURATION FILES
======================================================================
✅ .env
   Status: ✅ READY
   Size: 3374 bytes
   Last Modified: 2026-02-14 21:52:57
```

#### Section 4: Disabled Features
```
⚙️ DISABLED FEATURES
======================================================================
   • player_intelligence
   • tavily_enrichment
```

#### Section 5: Recommendations
```
💡 RECOMMENDATIONS
======================================================================

🔴 CRITICAL ISSUES (Must Fix):
   • ODDS_API_KEY: MISSING from .env

🟡 OPTIONAL WARNINGS (Can Ignore):
   • API_FOOTBALL_KEY: MISSING from .env

🌐 API CONNECTIVITY ISSUES:
   • OpenRouter API: Connection timeout

📁 CONFIGURATION FILE ISSUES:
   • config/settings.json: Invalid JSON: Expecting ',' delimiter
```

---

## 5. Command-Line Interface

### Usage

```bash
# Basic validation (handshake report with all tests)
python3 -m src.utils.startup_validator

# Detailed diagnostic report
python3 -m src.utils.startup_validator --detailed

# Skip API connectivity tests (faster)
python3 -m src.utils.startup_validator --no-connectivity

# Skip configuration file validation
python3 -m src.utils.startup_validator --no-config-files

# Combine flags
python3 -m src.utils.startup_validator --detailed --no-connectivity
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--help` | Show help message | - |
| `--detailed` | Print detailed diagnostic report | False |
| `--no-connectivity` | Skip API connectivity tests | False |
| `--no-config-files` | Skip configuration file validation | False |

---

## 6. Integration with Entry Points

### 6.1 Launcher Integration

The validator can be integrated into [`launcher.py`](src/entrypoints/launcher.py:333) at the start of the `main()` function:

```python
def main():
    """Entry point dell'orchestrator."""
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
    # ... rest of main() ...
```

### 6.2 Main Pipeline Integration

The validator can be integrated into [`main.py`](src/main.py:1626) at the start of the `__main__` block:

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

---

## 7. Makefile Integration

### New Target

Add the following target to the [`Makefile`](Makefile:1):

```makefile
.PHONY: check-startup

check-startup: check-env
	@echo "$(COLOR_GREEN)Running startup validation...$(COLOR_RESET)"
	@$(PYTHON) -m src.utils.startup_validator
```

### Updated Help Section

Update the help section in the Makefile:

```makefile
help:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Earlybird Project - Available Commands$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BOLD)Diagnostics Commands:$(COLOR_RESET)"
	@echo "  make check-apis        - API Diagnostics"
	@echo "  make check-startup      - Startup Validation (Pre-Flight Guard)"
	@echo "  make check-health      - System health check"
	@echo "  make check-database    - Database integrity check"
```

---

## 8. Testing Results

### Test 1: Basic Validation (No Connectivity/Config Tests)
```bash
python3 -m src.utils.startup_validator --no-connectivity --no-config-files
```

**Result:** ✅ PASSED
- All critical keys validated
- Optional keys with warnings correctly identified
- Disabled features tracked

### Test 2: Configuration File Validation
```bash
python3 -m src.utils.startup_validator --no-connectivity
```

**Result:** ✅ PASSED
- All configuration files validated
- File sizes and modification times displayed
- JSON syntax validation passed

### Test 3: Full Validation with Connectivity Tests
```bash
python3 -m src.utils.startup_validator
```

**Result:** ✅ PASSED
- All API connectivity tests passed
- Response times measured:
  - Odds API: 531ms
  - OpenRouter API: 2220ms
  - Brave API: 671ms
  - Supabase: 1776ms
- Quota information extracted:
  - Odds API: 212 used, 19788 remaining
  - Brave API: 3/3 keys working

### Test 4: Detailed Diagnostic Report
```bash
python3 -m src.utils.startup_validator --detailed --no-connectivity
```

**Result:** ✅ PASSED
- Comprehensive report generated
- All sections displayed correctly
- Recommendations provided
- Actionable error messages

---

## 9. Benefits

### 9.1 Proactive Issue Detection
- **Before:** Issues discovered during runtime (crashes, silent failures)
- **After:** Issues detected at startup with clear error messages

### 9.2 Improved Debugging
- **Before:** Logs scattered across multiple files, hard to diagnose
- **After:** Single comprehensive report with all diagnostic information

### 9.3 Better User Experience
- **Before:** Generic error messages, unclear what to fix
- **After:** Specific, actionable recommendations with context

### 9.4 Operational Visibility
- **Before:** No visibility into API quota or connectivity
- **After:** Real-time quota monitoring and connectivity status

### 9.5 Configuration Integrity
- **Before:** No validation of configuration files
- **After:** Automated validation with syntax checking

### 9.6 Graceful Degradation
- **Before:** All or nothing - system fails if any key missing
- **After:** Optional features auto-disable, system continues with reduced functionality

---

## 10. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Entry Points                              │
│              (launcher.py, main.py)                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌──────────────────────────┐
         │  StartupValidator       │
         │  (Phase 1: Basic)      │
         └────────────┬─────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│  validate_all()  │    │  Phase 3:        │
│  - Critical Keys │    │  Enhanced        │
│  - Optional Keys │    │  Diagnostics    │
└──────────────────┘    └────────┬─────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │ API          │ │ Config       │ │ Detailed     │
        │ Connectivity │ │ File         │ │ Diagnostic   │
        │ Tests        │ │ Validation   │ │ Report       │
        └──────────────┘ └──────────────┘ └──────────────┘
                │                │                │
                ▼                ▼                ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │ Response     │ │ File Size    │ │ Actionable   │
        │ Times       │ │ JSON Syntax  │ │ Recommendations│
        │ Quota Info  │ │ Last Modified│ │              │
        └──────────────┘ └──────────────┘ └──────────────┘
```

---

## 11. Data Structures

### 11.1 APIConnectivityResult
```python
@dataclass
class APIConnectivityResult:
    """Result of API connectivity test."""
    api_name: str
    status: ValidationStatus
    response_time_ms: Optional[float]
    quota_info: Optional[str]
    error_message: Optional[str]
```

### 11.2 ConfigFileValidationResult
```python
@dataclass
class ConfigFileValidationResult:
    """Result of configuration file validation."""
    file_path: str
    status: ValidationStatus
    file_size_bytes: int
    last_modified: Optional[str]
    error_message: Optional[str]
```

### 11.3 StartupValidationReport (Extended)
```python
@dataclass
class StartupValidationReport:
    """Complete startup validation report."""
    critical_results: List[ValidationResult]
    optional_results: List[ValidationResult]
    overall_status: ValidationStatus
    summary: str
    api_connectivity_results: List[APIConnectivityResult]  # NEW
    config_file_results: List[ConfigFileValidationResult]    # NEW
    timestamp: str                                          # NEW
```

---

## 12. Error Handling

### 12.1 API Test Errors

| Error Type | Status | Message | Action |
|------------|--------|---------|--------|
| Missing API Key | FAIL | "API key not configured" | Exit if critical |
| Invalid API Key (401) | FAIL | "Invalid API key (401 Unauthorized)" | Exit if critical |
| Rate Limit (429) | WARN | "Rate limit reached (429)" | Continue with warning |
| Timeout | WARN | "Connection timeout" | Continue with warning |
| Network Error | FAIL | Error details | Exit if critical |
| HTTP Error | FAIL | "HTTP {status_code}" | Exit if critical |

### 12.2 Config File Errors

| Error Type | Status | Message | Action |
|------------|--------|---------|--------|
| File Not Found | FAIL/WARN | "File not found: {path}" | Exit if critical |
| File Too Small | WARN | "File too small ({size} < {min_size} bytes)" | Continue with warning |
| Invalid JSON | FAIL | "Invalid JSON: {error}" | Exit if critical |
| Permission Error | FAIL | Error details | Exit if critical |

---

## 13. Performance Considerations

### 13.1 API Test Timeout Values

| API | Timeout | Rationale |
|-----|---------|-----------|
| Odds API | 15s | Standard API timeout |
| OpenRouter API | 30s | LLM APIs can be slow |
| Brave API | 15s | Standard API timeout |
| Supabase | 10s | Database connection |

### 13.2 Validation Order

1. **Environment Variables** (Fast, < 1ms)
2. **Configuration Files** (Fast, < 10ms)
3. **API Connectivity Tests** (Slow, 5-30s total)

### 13.3 Optimization Options

Users can skip slow tests for faster startup:

```bash
# Fast validation (no API tests)
python3 -m src.utils.startup_validator --no-connectivity

# Medium validation (no config file checks)
python3 -m src.utils.startup_validator --no-config-files
```

---

## 14. Future Enhancements

### Potential Improvements

1. **Historical Tracking**
   - Store validation results over time
   - Track quota usage trends
   - Identify degrading performance

2. **Alert Integration**
   - Send alerts when quota is low
   - Notify when APIs are down
   - Alert on configuration changes

3. **Self-Healing**
   - Automatically rotate API keys on rate limit
   - Fallback to alternative APIs
   - Auto-repair configuration files

4. **Web Dashboard**
   - Real-time validation status
   - Interactive diagnostic reports
   - Historical trend visualization

5. **Integration Tests**
   - Automated testing of all APIs
   - Continuous monitoring
   - Automated recovery procedures

---

## 15. Conclusion

Phase 3 (Enhanced Diagnostics) has been successfully implemented, providing:

✅ **API Connectivity Testing** - Real-time tests for all critical APIs
✅ **Quota Monitoring** - Automatic quota extraction and display
✅ **Configuration File Validation** - Automated validation with syntax checking
✅ **Detailed Diagnostic Reports** - Comprehensive reports with actionable recommendations
✅ **Command-Line Interface** - Flexible options for different use cases
✅ **Error Handling** - Robust error handling with clear messages
✅ **Performance Optimization** - Optional fast/slow validation modes
✅ **Testing** - All features tested and verified

The enhanced validator provides a comprehensive pre-flight guard that prevents startup failures, improves debugging, and gives users clear visibility into system health and configuration.

---

**Implementation Date:** 2026-02-15
**Status:** ✅ Production Ready
**Next Steps:** Integration into launcher.py and main.py entry points
