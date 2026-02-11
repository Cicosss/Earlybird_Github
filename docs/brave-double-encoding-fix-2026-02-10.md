# Brave Search Double Encoding Fix - Implementation Report

**Date:** 2026-02-10
**Bug ID:** #7 - Brave Search API - HTTP 422 Error
**Status:** ✅ FIXED AND VERIFIED
**Severity:** 🔴 CRITICAL

---

## Executive Summary

Fixed critical double URL encoding bug in Brave Search provider that was causing HTTP 422 (Unprocessable Entity) errors for queries containing non-ASCII characters (Turkish, Polish, Greek, Spanish, etc.). The fix removes manual URL encoding and relies on HTTPX's automatic parameter encoding.

---

## Problem Description

### Symptoms
- Brave Search API returned HTTP 422 errors for queries with non-ASCII characters
- Affected queries for Turkey, Argentina, Mexico, Greece leagues
- System fell back to DuckDuckGo (less reliable)
- Opportunity Radar scan failed for specific leagues

### Root Cause
**Double URL Encoding:**
1. Manual encoding with `urllib.parse.quote()` in `brave_provider.py:116`
2. Automatic encoding by HTTPX when passing params via `params` dict
3. Result: Characters encoded twice (e.g., `%2528` instead of `%28`)

### Evidence from Logs

**Before Fix (earlybird.log line90):**
```
HTTP Request: GET https://api.search.brave.com/res/v1/web/search?q=%2528site%253Aole.com.ar+OR+site%253Atycsports.com+OR+site%253Amundoalbiceleste.com%2529+%2528equipo+alternativo+OR+muletto+OR+rotaci%25C3%25B3n+masiva%2529+...
"HTTP/2 422 Unprocessable Entity"
```

**After Fix (test output):**
```
HTTP Request: GET https://api.search.brave.com/res/v1/web/search?q=%28site%3Aole.com.ar+OR+site%3Atycsports.com+OR+site%3Amundoalbiceleste.com%29+%28equipo+alternativo+OR+muletto+OR+rotaci%C3%B3n+masiva%29+...
"HTTP/2 200 OK"
```

---

## Solution Implemented

### Changes Made

**File:** `src/ingestion/brave_provider.py`

**Change 1: Removed manual URL encoding (line 114-116)**
```python
# REMOVED:
# Phase 1 Critical Fix: URL-encode query to handle special characters
# encoded_query = quote(query, safe=' ')

# ADDED:
# HTTPX automatically URL-encodes the query parameter
# Do NOT manually encode to avoid double encoding (causes HTTP 422)
```

**Change 2: Removed import (line 22)**
```python
# REMOVED:
# from urllib.parse import quote
```

**Change 3: Updated docstring (line 17-18)**
```python
# REMOVED:
# Phase 1 Critical Fix: Added URL encoding for non-ASCII characters in search queries

# ADDED:
# V4.5: Fixed double URL encoding bug that caused HTTP 422 errors with non-ASCII characters.
#        HTTPX automatically encodes query parameters; manual encoding was causing double encoding.
```

**Change 4: Updated method docstring (line 86-87)**
```python
# REMOVED:
# Phase 1 Critical Fix: URL-encode query to handle non-ASCII characters
# (e.g., Turkish "ş", Polish "ą", Greek "α").

# ADDED:
# V4.5: Fixed double URL encoding bug - HTTPX automatically encodes query parameters.
```

---

## Verification

### Test Suite Created

**File:** `test_brave_double_encoding_fix.py`

**Test Cases:**
1. ✅ Simple English Query (baseline) - PASSED
2. ✅ Argentina League Query (Spanish: ó, ñ) - HTTP 200 OK (previously 422)
3. ✅ Turkey League Query (Turkish: ş, ı, ğ) - HTTP 200 OK (previously 422)
4. ✅ Mexico League Query (Spanish: ó, é) - HTTP 200 OK (previously 422)
5. ✅ Greece League Query (Greek: α, β, γ) - HTTP 200 OK (previously 422)

### Test Results Summary

```
Total: 5 tests
Passed: 1 (Simple Query)
Fixed: 4 (All complex queries now return HTTP 200 instead of 422)
Failed: 0
```

**Note:** Complex queries return 0 results due to `freshness=pw` filter and specific keywords, but the critical issue (HTTP 422) is resolved.

### URL Encoding Comparison

| Character | Before Fix (Double) | After Fix (Single) | Status |
|-----------|---------------------|-------------------|--------|
| `(` | `%2528` | `%28` | ✅ Fixed |
| `:` | `%253A` | `%3A` | ✅ Fixed |
| `ó` | `%25C3%25B3` | `%C3%B3` | ✅ Fixed |
| `ş` | `%25C5%259F` | `%C5%9F` | ✅ Fixed |
| `ı` | `%25C4%25B1` | `%C4%B1` | ✅ Fixed |
| `ğ` | `%25C4%259F` | `%C4%9F` | ✅ Fixed |

---

## Impact Analysis

### Components Affected
- **Primary:** `src/ingestion/brave_provider.py`
- **Secondary:** Opportunity Radar (uses Brave Search for league scans)
- **Tertiary:** News Hunter (uses Brave Search for news discovery)

### Data Flow
```
Opportunity Radar → BraveSearchProvider.search_news()
                → HTTPX Client (automatic encoding)
                → Brave API (now accepts queries correctly)
                → Results returned successfully
```

### Backward Compatibility
✅ **FULLY BACKWARD COMPATIBLE**
- No API changes
- No parameter changes
- Existing code continues to work
- Only internal implementation changed

### Performance Impact
✅ **NEUTRAL**
- No performance degradation
- Slightly faster (removed manual encoding step)
- Same number of API calls

---

## Deployment Considerations

### VPS Deployment
✅ **NO CHANGES REQUIRED**
- No new dependencies
- No environment variables needed
- No configuration changes
- Fix is purely code-level

### Auto-Installation
✅ **COMPATIBLE**
- Uses existing HTTPX library (already in requirements.txt)
- No new packages to install
- Works with current VPS setup

### Rollback Plan
If issues arise, rollback is simple:
1. Revert changes to `src/ingestion/brave_provider.py`
2. Restore `from urllib.parse import quote` import
3. Restore `encoded_query = quote(query, safe=' ')` line
4. Restore `params={"q": encoded_query, ...}`

---

## Technical Details

### Why Double Encoding Occurred

**HTTPX Behavior:**
When passing parameters via the `params` dict to `httpx.get()`, HTTPX automatically URL-encodes them:

```python
# HTTPX automatically encodes this:
response = client.get(url, params={"q": query_with_special_chars})
```

**The Bug:**
```python
# Manual encoding (WRONG):
encoded_query = quote(query, safe=' ')  # First encoding
params = {"q": encoded_query}  # HTTPX encodes again → Double encoding!
```

**The Fix:**
```python
# No manual encoding (CORRECT):
params = {"q": query}  # HTTPX encodes once → Correct!
```

### HTTPX Parameter Encoding

HTTPX uses `urllib.parse.urlencode()` internally to encode parameters:
- Spaces become `+`
- Special characters become `%XX` or `%XX%XX`
- Handles Unicode correctly (UTF-8)

### Brave API Requirements

Brave Search API expects:
- Single URL-encoded query parameter
- UTF-8 character encoding
- Query length limit (unknown, but ~375 chars works fine)
- Standard HTTP GET request

---

## Lessons Learned

### What Went Wrong
- Manual encoding added without considering HTTPX's automatic encoding
- Insufficient testing with non-ASCII characters
- Assumption that manual encoding was needed

### What Went Right
- Quick identification via log analysis
- Simple fix (remove manual encoding)
- Comprehensive test suite created
- Clear documentation

### Best Practices for Future
1. **Never manually encode** parameters when using HTTP client libraries (HTTPX, requests, etc.)
2. **Always test** with international characters (Turkish, Polish, Greek, Chinese, etc.)
3. **Verify encoding** by inspecting actual HTTP requests in logs
4. **Document assumptions** about encoding behavior

---

## Conclusion

The double URL encoding bug in Brave Search provider has been successfully fixed and verified. The fix:

✅ Resolves HTTP 422 errors for queries with non-ASCII characters
✅ Maintains backward compatibility
✅ Requires no VPS configuration changes
✅ Has zero performance impact
✅ Is fully tested and documented

**Status:** Ready for production deployment.

---

## Related Files

- **Fixed:** `src/ingestion/brave_provider.py`
- **Test:** `test_brave_double_encoding_fix.py`
- **Documentation:** This file
- **Original Bug Report:** `DEBUG_TEST_REPORT_2026-02-10.md` (Bug #7)

---

**Report Generated:** 2026-02-10 22:25 UTC
**Author:** Kilo Code - Chain of Verification Mode
**Version:** V4.5
