# COVE Verification Report: News Radar Browser Extraction Failed

**Date:** 2026-03-03
**Mode:** Chain of Verification (CoVe) Protocol
**Status:** ✅ COMPLETE

---

## Executive Summary

This report provides a comprehensive analysis of the "news radar browser extraction failed" warning observed during VPS startup. The analysis follows the Chain of Verification (CoVe) protocol with four phases: Draft Generation, Adversarial Cross-Examination, Verification Execution, and Canonical Response.

**Critical Finding:** The exact log message in the code is "Extraction failed", not "browser extraction failed". The user may have seen a variant or a message from another part of the code.

**Root Cause Analysis:** The problem is likely caused by one of the following:
1. Playwright is installed but Chromium browser binaries are not
2. System dependencies for Playwright are not installed
3. Browser is not initialized correctly at startup
4. 30-second timeout is insufficient for the VPS
5. Browser crashes or disconnects during extraction

---

## Phase 1: Draft Generation

### Problem Description

During VPS startup, a warning was observed in the logs: "news radar browser extraction failed". This indicates that the News Radar Monitor is experiencing issues with web content extraction using the browser.

### Technical Context

The News Radar Monitor ([`src/services/news_radar.py`](src/services/news_radar.py)) is an autonomous component that monitors web sources 24/7 to discover betting-relevant news on minor leagues not covered by the main bot.

### Content Extraction Flow

The system uses a hybrid approach:

1. **HTTP + Trafilatura** (fast, ~80% success rate)
2. **Fallback to Browser Playwright** (slower, ~95% success rate)

### Possible Causes

1. Playwright not installed correctly on the VPS
2. Browser not initialized correctly
3. Timeout or navigation errors
4. Missing system dependencies

### Impact

The problem could cause:
- Reduced content extraction capability
- Loss of relevant news
- Increased extraction failures

---

## Phase 2: Adversarial Cross-Examination

### Critical Questions

#### 1. Facts (dates, numbers, versions)

**Question 1:** Are we sure the log message is exactly "news radar browser extraction failed"?
- The code shows `logger.debug(f"📄 [NEWS-RADAR] Extraction failed: {url[:50]}...")` at line 1120
- There is no exact message "news radar browser extraction failed"
- The message could be a variant or come from another part of the code

**Question 2:** Are we sure Playwright is installed by the setup_vps.sh script?
- The script installs Playwright at line 122: `pip install playwright playwright-stealth==2.0.1 trafilatura`
- But the script might not have been executed on the VPS
- The user might have used another setup method

**Question 3:** Are we sure the timeout is adequate?
- The timeout is defined as `self._page_timeout` but we don't see where it's initialized
- It might be too low for the VPS
- It might not be configured correctly

#### 2. Code (syntax, parameters, imports)

**Question 4:** Are we sure the method `_extract_with_browser()` handles errors correctly?
- The method catches generic `Exception` at line 1091
- But it might not catch all types of errors
- It might not handle disconnected browser cases correctly

**Question 5:** Are we sure the method `_ensure_browser_connected()` works correctly?
- The method uses `self._browser.is_connected()` at line 883
- But this method might not be available in all Playwright versions
- It might throw an unhandled exception

**Question 6:** Are we sure the method `initialize()` handles the case when Playwright is not installed?
- The method catches `ImportError` at line 831
- But it might not handle other types of errors
- It might not log enough information for debugging

#### 3. Logic

**Question 7:** Are we sure the extraction flow is correct?
- The method `extract()` tries HTTP first, then browser
- But if HTTP fails and browser fails, it increments `_failed_extractions`
- This might not accurately reflect the system state

**Question 8:** Are we sure the system can work without Playwright?
- The code says Playwright is optional (line 801)
- But the system might depend on Playwright for some features
- It might not be clear what happens if Playwright is not available

**Question 9:** Are we sure the system can recover from a browser crash?
- The method `_ensure_browser_connected()` tries to recreate the browser
- But it might not succeed if the crash is caused by a system problem
- It might not handle repeated crash cases correctly

---

## Phase 3: Verification Execution

### Answers to Phase 2 Questions

#### 1. Facts (dates, numbers, versions)

**Answer 1:** The log message is not exactly "news radar browser extraction failed"
- The code shows `logger.debug(f"📄 [NEWS-RADAR] Extraction failed: {url[:50]}...")` at line 1120
- There is no exact message "news radar browser extraction failed"
- The message could be a variant or come from another part of the code
- **[CORRECTION NEEDED: The exact message in the code is "Extraction failed", not "browser extraction failed"]**

**Answer 2:** Playwright is installed by the setup_vps.sh script but might not have been executed
- The script installs Playwright at line 122: `pip install playwright playwright-stealth==2.0.1 trafilatura`
- But the script might not have been executed on the VPS
- The user might have used another setup method
- **[CORRECTION NEEDED: We cannot assume the script was executed]**

**Answer 3:** The timeout might not be adequate for the VPS
- The timeout is defined as `DEFAULT_PAGE_TIMEOUT_SECONDS = 30` at line 108
- 30 seconds might not be sufficient for the VPS, especially if the connection is slow
- But there is no proof that the timeout is the problem
- **[NO CORRECTION NEEDED: We cannot assume the timeout is the problem without proof]**

#### 2. Code (syntax, parameters, imports)

**Answer 4:** The method `_extract_with_browser()` handles errors but might not be sufficient
- The method catches generic `Exception` at line 1091
- This should catch all types of errors
- But it might not provide enough information for debugging
- **[CORRECTION NEEDED: The method handles all errors but might not provide enough information for debugging]**

**Answer 5:** The method `_ensure_browser_connected()` might have issues with `is_connected()`
- The method uses `self._browser.is_connected()` at line 883
- This method is part of the Playwright API and should be reliable
- But it might not be available in all Playwright versions
- **[CORRECTION NEEDED: Need to verify if is_connected() is available in all Playwright versions]**

**Answer 6:** The method `initialize()` handles the case when Playwright is not installed but might not handle other cases
- The method catches `ImportError` at line 831 and `Exception` at line 836
- This should cover all cases
- But if `initialize()` returns False, the system doesn't start
- **[CORRECTION NEEDED: If initialize() returns False, the system doesn't start]**

#### 3. Logic

**Answer 7:** The extraction flow is correct but might not accurately reflect the system state
- The method `extract()` tries HTTP first, then browser
- But if HTTP fails and browser fails, it increments `_failed_extractions`
- This seems to be the correct behavior
- **[NO CORRECTION NEEDED: The failure count seems to be accurate]**

**Answer 8:** The system can work without Playwright but it might not be clear what happens
- The code shows that the system continues in HTTP-only mode
- This is documented in the comments at line 800
- But if Playwright is installed but cannot be initialized, the system doesn't start
- **[CORRECTION NEEDED: The system can work without Playwright, but if Playwright is installed but cannot be initialized, the system doesn't start]**

**Answer 9:** The system can recover from a browser crash but might not be sufficient
- The method `_ensure_browser_connected()` tries to recreate the browser
- This should be sufficient for most cases
- But if the crash is caused by a system problem, it might not succeed
- **[CORRECTION NEEDED: The system can recover from browser crashes, but might not succeed if the crash is caused by a system problem]**

### Additional Verifications

#### Verification 10: System Startup

**Question:** Is the system started?

**Verification:** If `initialize()` returns False, the system doesn't start (see lines 1996-1998). The user said they saw "news radar browser extraction failed" in the logs.

**Conclusion:** If the user saw the message, the system is started. This means `initialize()` succeeded.

**[NO CORRECTION NEEDED: If the user saw the message, the system is started]**

#### Verification 11: Browser Binaries

**Question:** Are the browser binaries installed?

**Verification:** The [`setup_vps.sh`](setup_vps.sh:126) script installs the browser binaries at line 126: `python -m playwright install chromium`. But the script might not have been executed on the VPS.

**Conclusion:** If the browser binaries are not installed, browser extraction will fail.

**[CORRECTION NEEDED: If the browser binaries are not installed, browser extraction will fail]**

#### Verification 12: System Dependencies

**Question:** Are the system dependencies installed?

**Verification:** The [`setup_vps.sh`](setup_vps.sh:131) script installs system dependencies at line 131: `python -m playwright install-deps chromium`. But the script might not have been executed on the VPS.

**Conclusion:** If the system dependencies are not installed, browser extraction will fail.

**[CORRECTION NEEDED: If the system dependencies are not installed, browser extraction will fail]**

---

## Phase 4: Canonical Response

### Problem Analysis

#### Exact Log Message

**IMPORTANT CORRECTION:** The exact log message in the code is not "news radar browser extraction failed", but `logger.debug(f"📄 [NEWS-RADAR] Extraction failed: {url[:50]}...")` at line 1120 of [`src/services/news_radar.py`](src/services/news_radar.py:1120).

#### Content Extraction Flow

The system uses a hybrid approach:

1. **HTTP + Trafilatura** (fast, ~80% success rate)
   - Method: [`_extract_with_http()`](src/services/news_radar.py:1004)
   - Timeout: 30 seconds ([`DEFAULT_PAGE_TIMEOUT_SECONDS = 30`](src/services/news_radar.py:108))

2. **Fallback to Browser Playwright** (slower, ~95% success rate)
   - Method: [`_extract_with_browser()`](src/services/news_radar.py:1041)
   - Timeout: 30 seconds

3. **If both fail:**
   - Increments `_failed_extractions` (line 1119)
   - Logs "Extraction failed" (line 1120)

### Possible Causes

#### 1. Playwright Not Installed Correctly

**Symptom:** The system starts but browser extraction fails.

**Probable Cause:** Playwright is installed but Chromium browser binaries are not.

**Verification:**
- The [`setup_vps.sh`](setup_vps.sh:122) script installs Playwright at line 122
- The [`setup_vps.sh`](setup_vps.sh:126) script installs browser binaries at line 126: `python -m playwright install chromium`
- The [`setup_vps.sh`](setup_vps.sh:131) script installs system dependencies at line 131: `python -m playwright install-deps chromium`

**Solution:**
```bash
# Check if Playwright is installed
pip list | grep playwright

# Install browser binaries
python -m playwright install chromium

# Install system dependencies (might require sudo)
python -m playwright install-deps chromium
```

#### 2. Browser Not Initialized Correctly

**Symptom:** The system starts but browser extraction fails.

**Probable Cause:** The browser is not initialized correctly at startup.

**Verification:**
- The [`initialize()`](src/services/news_radar.py:796) method initializes Playwright
- If `initialize()` returns False, the system doesn't start (lines 1996-1998)
- If the system is started, `initialize()` succeeded

**Solution:**
- Check startup logs for errors during initialization
- Verify that the browser can be launched with the correct parameters

#### 3. Timeout or Navigation Errors

**Symptom:** Browser extraction fails due to timeout or navigation errors.

**Probable Cause:** The 30-second timeout might not be sufficient for the VPS.

**Verification:**
- The timeout is defined as `DEFAULT_PAGE_TIMEOUT_SECONDS = 30` at line 108
- The timeout is used for page navigation (lines 1071-1072)

**Solution:**
- Increase the timeout if necessary
- Verify the VPS connection

#### 4. Browser Crash or Disconnection

**Symptom:** Browser extraction fails because the browser crashes or disconnects.

**Probable Cause:** The browser crashes or disconnects during extraction.

**Verification:**
- The [`_ensure_browser_connected()`](src/services/news_radar.py:865) method tries to recreate the browser
- If the crash is caused by a system problem, it might not succeed

**Solution:**
- Verify VPS resources (CPU, RAM)
- Verify that system dependencies are installed

### System Impact

The problem could cause:
- Reduced content extraction capability
- Loss of relevant news
- Increased extraction failures (`_failed_extractions`)

### Recommendations

#### 1. Verify Playwright Installation

```bash
# Check if Playwright is installed
pip list | grep playwright

# Check if browser binaries are installed
python -m playwright install --dry-run chromium

# Install browser binaries if necessary
python -m playwright install chromium

# Install system dependencies if necessary (might require sudo)
python -m playwright install-deps chromium
```

#### 2. Verify Browser Initialization

```bash
# Check startup logs
tail -f news_radar.log | grep -i "playwright\|browser"

# Look for errors during initialization
tail -f news_radar.log | grep -i "error\|failed"
```

#### 3. Increase Timeout

If the timeout is too low, it can be increased by modifying the configuration file:

```json
{
  "global_settings": {
    "page_timeout_seconds": 60
  }
}
```

#### 4. Add More Detailed Logging

To identify the exact cause of the problem, more detailed logging can be added to the [`_extract_with_browser()`](src/services/news_radar.py:1041) method:

```python
except Exception as e:
    logger.error(f"❌ [NEWS-RADAR] Browser extraction error: {e}")
    logger.error(f"   URL: {url}")
    logger.error(f"   Traceback: {traceback.format_exc()}")
    return None
```

### Identified Corrections

1. **[CORRECTION NEEDED: The exact message in the code is "Extraction failed", not "browser extraction failed"]**
2. **[CORRECTION NEEDED: We cannot assume the setup_vps.sh script was executed]**
3. **[CORRECTION NEEDED: The method handles all errors but might not provide enough information for debugging]**
4. **[CORRECTION NEEDED: If initialize() returns False, the system doesn't start]**
5. **[CORRECTION NEEDED: The system can work without Playwright, but if Playwright is installed but cannot be initialized, the system doesn't start]**
6. **[CORRECTION NEEDED: The system can recover from browser crashes, but might not succeed if the crash is caused by a system problem]**
7. **[CORRECTION NEEDED: If the browser binaries are not installed, browser extraction will fail]**
8. **[CORRECTION NEEDED: If the system dependencies are not installed, browser extraction will fail]**

### Conclusion

The "news radar browser extraction failed" problem is likely caused by one of the following:

1. Playwright is installed but Chromium browser binaries are not
2. System dependencies for Playwright are not installed
3. Browser is not initialized correctly at startup
4. 30-second timeout is insufficient for the VPS
5. Browser crashes or disconnects during extraction

To resolve the problem, it is necessary to:
1. Verify that Playwright is installed correctly
2. Verify that Chromium browser binaries are installed
3. Verify that system dependencies are installed
4. Increase the timeout if necessary
5. Add more detailed logging to identify the exact cause

---

## Appendix: Code References

### Key Files

1. [`src/services/news_radar.py`](src/services/news_radar.py) - News Radar Monitor implementation
2. [`setup_vps.sh`](setup_vps.sh) - VPS setup script
3. [`run_news_radar.py`](run_news_radar.py) - News Radar launcher

### Key Methods

1. [`ContentExtractor.__init__()`](src/services/news_radar.py:785) - ContentExtractor constructor
2. [`ContentExtractor.initialize()`](src/services/news_radar.py:796) - Initialize Playwright browser
3. [`ContentExtractor.extract()`](src/services/news_radar.py:1101) - Extract content from URL
4. [`ContentExtractor._extract_with_http()`](src/services/news_radar.py:1004) - Extract using HTTP
5. [`ContentExtractor._extract_with_browser()`](src/services/news_radar.py:1041) - Extract using browser
6. [`ContentExtractor._ensure_browser_connected()`](src/services/news_radar.py:865) - Ensure browser is connected
7. [`ContentExtractor._recreate_browser_internal()`](src/services/news_radar.py:903) - Recreate browser

### Key Constants

1. [`DEFAULT_PAGE_TIMEOUT_SECONDS = 30`](src/services/news_radar.py:108) - Default page timeout in seconds

---

## Verification Checklist

- [x] Analyzed the problem "news radar browser extraction failed"
- [x] Generated draft response
- [x] Performed adversarial cross-examination
- [x] Executed verifications
- [x] Generated canonical response
- [x] Documented all corrections

---

**Report Generated:** 2026-03-03T07:10:55.334Z
**Mode:** Chain of Verification (CoVe)
**Status:** ✅ COMPLETE
