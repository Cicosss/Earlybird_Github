# COVE Double Verification Report - Playwright VPS Error Fix

**Date:** 2026-03-04  
**Verification Mode:** Chain of Verification (CoVe) - Double Verification  
**Task:** Investigate and fix Playwright error on VPS: "AttributeError: module 'playwright' has no attribute '_version_'"  
**Priority:** CRITICAL - Bot running on VPS with Playwright installation issues

---

## Executive Summary

**Status:** ⚠️ **MULTIPLE CRITICAL ISSUES IDENTIFIED**

The error "AttributeError: module 'playwright' has no attribute '_version_'" is caused by **multiple configuration and deployment issues** that prevent Playwright from working correctly on the VPS. These issues must be fixed to ensure the bot runs reliably.

**Root Causes:**
1. ❌ **Version Mismatch**: [`requirements.txt`](requirements.txt:48) specifies `playwright==1.48.0` but installed version is `1.58.0`
2. ❌ **Deploy Script Issue**: [`setup_vps.sh`](setup_vps.sh:122) installs Playwright WITHOUT version pinning
3. ⚠️ **Code Access Error**: [`src/services/news_radar.py`](src/services/news_radar.py:821) accesses `playwright.__version__` which may fail on corrupted installations
4. ✅ **New Features Integrated**: [`radar_odds_check.py`](src/utils/radar_odds_check.py) and [`radar_enrichment.py`](src/utils/radar_enrichment.py) are properly integrated

**Impact Assessment:**
- **Severity:** CRITICAL - News Radar may fail to extract content
- **Crash Risk:** HIGH - AttributeError causes News Radar to crash
- **Data Flow:** PARTIAL - New features work but Playwright extraction fails
- **VPS Deployment:** NOT READY - Version mismatch will cause issues

**Recommendations:**
1. Fix version mismatch in requirements.txt or deploy script
2. Add error handling for `playwright.__version__` access
3. Verify Playwright installation on VPS
4. Update deploy script to respect requirements.txt

---

## FASE 1: Generazione Bozza (Draft)

### Initial Analysis

**Problem Reported:**
- User observed error: "AttributeError: module 'playwright' has no attribute '_version_'" on VPS
- User wants to ensure new features don't crash bot
- User wants to verify data flow integration
- User wants to verify VPS deployment readiness

**Initial Hypothesis:**
1. The error is caused by version mismatch between requirements.txt and installed version
2. Playwright installation on VPS is corrupted or incomplete
3. The deploy script doesn't respect the version specified in requirements.txt
4. New features (radar_odds_check, radar_enrichment) are properly integrated

**Preliminary Findings:**
- CONFIRMED: requirements.txt specifies `playwright==1.48.0`
- CONFIRMED: Installed version in .venv is `1.58.0`
- CONFIRMED: setup_vps.sh installs Playwright without version pinning
- CONFIRMED: Code accesses `playwright.__version__` at line 821
- CONFIRMED: New features are properly integrated and don't use Playwright directly

**Initial Assessment:**
- The error is caused by version mismatch and deployment issues
- New features are properly integrated and work correctly
- Fix is required in requirements.txt, deploy script, and error handling

---

## FASE 2: Verifica Avversariale (Cross-Examination)

### Critical Questions & Skeptical Analysis

#### 1. Facts (dates, numbers, versions)

**Question 1:** Are we sure the version mismatch is the problem?
**Skeptical Check:** What if the installed version is actually correct and requirements.txt is outdated?
**Potential Issue:** The version in requirements.txt might be outdated, not the installed version.

**Question 2:** Are we sure Playwright has the `__version__` attribute?
**Skeptical Check:** What if Playwright 1.58.0 doesn't have `__version__`?
**Potential Issue:** The attribute name might have changed between versions.

**Question 3:** Are we sure the deploy script is the problem?
**Skeptical Check:** What if the deploy script was updated but not committed?
**Potential Issue:** The deploy script might have been fixed locally but not in the repository.

#### 2. Code (syntax, parameters, imports)

**Question 4:** Are we sure the error handling is correct?
**Skeptical Check:** What if the code doesn't handle the case when `__version__` is missing?
**Potential Issue:** The code at line 821 will crash if `__version__` doesn't exist.

**Question 5:** Are we sure the new features don't use Playwright?
**Skeptical Check:** What if radar_odds_check or radar_enrichment use Playwright indirectly?
**Potential Issue:** New features might have hidden dependencies on Playwright.

#### 3. Logic

**Question 6:** Are we sure the data flow is correct?
**Skeptical Check:** What if the new features break the existing flow?
**Potential Issue:** Integration of new features might introduce bugs.

**Question 7:** Are we sure the VPS deployment will work?
**Skeptical Check:** What if the VPS has different Python version or system dependencies?
**Potential Issue:** VPS environment might be incompatible with Playwright.

---

## FASE 3: Esecuzione Verifiche

### Answers to Phase 2 Questions

#### 1. Facts (dates, numbers, versions)

**Answer 1:** Version mismatch is confirmed
- [`requirements.txt`](requirements.txt:48) specifies: `playwright==1.48.0`
- [`.venv/lib/python3.11/site-packages/playwright/_repo_version.py`](.venv/lib/python3.11/site-packages/playwright/_repo_version.py:20) shows: `__version__ = '1.58.0'`
- **[CORREZIONE NECESSARIA: Versione Playwright incoerente]**

**Answer 2:** Playwright DOES have `__version__` attribute
- The file `_repo_version.py` defines `__version__` at line 20
- The attribute is exported in `__all__` at line 4
- **[NO CORREZIONE NECESSARIA: Playwright ha l'attributo __version__]**

**Answer 3:** Deploy script doesn't respect requirements.txt
- [`setup_vps.sh`](setup_vps.sh:122) installs: `pip install playwright playwright-stealth==2.0.1 trafilatura`
- No version is specified for playwright, only for playwright-stealth
- This will install the latest version, not 1.48.0
- **[CORREZIONE NECESSARIA: Script di deploy non rispetta requirements.txt]**

#### 2. Code (syntax, parameters, imports)

**Answer 4:** Error handling is insufficient
- [`src/services/news_radar.py`](src/services/news_radar.py:821) accesses: `playwright.__version__`
- No try-except around this access
- If Playwright is corrupted or missing `__version__`, it will crash
- **[CORREZIONE NECESSARIA: Manca error handling per playwright.__version__]**

**Answer 5:** New features don't use Playwright directly
- [`radar_odds_check.py`](src/utils/radar_odds_check.py) doesn't import Playwright
- [`radar_enrichment.py`](src/utils/radar_enrichment.py) doesn't import Playwright
- Both use database and API calls, not browser automation
- **[NO CORREZIONE NECESSARIA: Nuove feature non usano Playwright]**

#### 3. Logic

**Answer 6:** Data flow is correct
- New features are imported at lines 64-79 in [`news_radar.py`](src/services/news_radar.py:64-79)
- Both have fallback handling if not available
- Integration points are at lines 2710 and 3324
- **[NO CORREZIONE NECESSARIA: Flusso dati corretto]**

**Answer 7:** VPS deployment needs fixes
- Version mismatch will cause issues
- Deploy script doesn't pin Playwright version
- Error handling is insufficient
- **[CORREZIONE NECESSARIA: Deploy VPS richiede correzioni]**

---

## FASE 4: Risposta Finale (Canonical)

### Problem Analysis

#### Root Cause 1: Version Mismatch

**Issue:**
- [`requirements.txt`](requirements.txt:48) specifies `playwright==1.48.0`
- Installed version is `1.58.0` (from [`_repo_version.py`](.venv/lib/python3.11/site-packages/playwright/_repo_version.py:20))
- This is a **10 version difference** which can cause compatibility issues

**Impact:**
- Playwright API may have changed between versions
- Browser binaries may be incompatible
- Error messages may be different than expected

**Solution:**
Update [`requirements.txt`](requirements.txt:48) to match installed version:
```diff
- playwright==1.48.0
+ playwright==1.58.0
```

OR reinstall Playwright with correct version:
```bash
pip uninstall playwright
pip install playwright==1.48.0
python -m playwright install chromium
```

#### Root Cause 2: Deploy Script Issue

**Issue:**
- [`setup_vps.sh`](setup_vps.sh:122) installs Playwright without version pinning
- Command: `pip install playwright playwright-stealth==2.0.1 trafilatura`
- This installs the latest version, not the version specified in requirements.txt

**Impact:**
- VPS will have different Playwright version than development environment
- Inconsistent behavior between environments
- Difficult to reproduce and debug issues

**Solution:**
Update [`setup_vps.sh`](setup_vps.sh:122) to respect requirements.txt:
```diff
- pip install playwright playwright-stealth==2.0.1 trafilatura
+ pip install -r requirements.txt
```

OR pin Playwright version in deploy script:
```diff
- pip install playwright playwright-stealth==2.0.1 trafilatura
+ pip install playwright==1.48.0 playwright-stealth==2.0.1 trafilatura
```

#### Root Cause 3: Insufficient Error Handling

**Issue:**
- [`src/services/news_radar.py`](src/services/news_radar.py:821) accesses `playwright.__version__` without error handling
- Code: `diagnostics["details"].append(f"✅ Playwright v{playwright.__version__} installed")`
- If `__version__` doesn't exist, it will raise AttributeError

**Impact:**
- News Radar will crash during diagnostics
- Users will see cryptic error messages
- Difficult to debug installation issues

**Solution:**
Add error handling in [`src/services/news_radar.py`](src/services/news_radar.py:817-823):
```diff
         # Check Playwright Python package
         try:
             import playwright
 
             diagnostics["playwright_installed"] = True
-            diagnostics["details"].append(f"✅ Playwright v{playwright.__version__} installed")
+            try:
+                version = playwright.__version__
+                diagnostics["details"].append(f"✅ Playwright v{version} installed")
+            except AttributeError:
+                diagnostics["details"].append("✅ Playwright installed (version unknown)")
         except ImportError:
             diagnostics["details"].append("❌ Playwright Python package not installed")
             return diagnostics
```

#### Root Cause 4: Browser Binary Installation

**Issue:**
- Even if Playwright Python package is installed, browser binaries may not be
- [`setup_vps.sh`](setup_vps.sh:126) installs binaries with: `python -m playwright install chromium`
- This step may fail silently or be skipped

**Impact:**
- Playwright will be installed but won't work
- All browser extraction will fail
- News Radar will fall back to HTTP-only mode

**Solution:**
The deploy script already has verification at lines 140-175, but we should add additional checks:
```bash
# Verify browser binaries are installed
if ! python -c "from playwright.sync_api import sync_playwright; print('OK')" 2>/dev/null; then
    echo "❌ CRITICAL: Playwright browser binaries not installed"
    exit 1
fi
```

### New Features Integration Verification

#### Feature 1: Radar Odds Check

**File:** [`src/utils/radar_odds_check.py`](src/utils/radar_odds_check.py)
**Purpose:** Check odds movement before sending alerts
**Integration:** Imported in [`news_radar.py`](src/services/news_radar.py:74)
**Usage:** Called at line 2710 to check odds status

**Verification:**
- ✅ No direct Playwright dependency
- ✅ Uses database and API calls
- ✅ Has fallback handling
- ✅ Properly integrated into alert flow

**Data Flow:**
1. News Radar detects alert
2. Calls `check_odds_for_alert_async()` to check odds
3. Returns `OddsCheckResult` with movement status
4. Alert is modified with odds suffix if applicable
5. Alert is sent to Telegram

**Conclusion:** Feature is properly integrated and doesn't introduce Playwright issues.

#### Feature 2: Radar Enrichment

**File:** [`src/utils/radar_enrichment.py`](src/utils/radar_enrichment.py)
**Purpose:** Add context from database to alerts
**Integration:** Imported in [`news_radar.py`](src/services/news_radar.py:65)
**Usage:** Called at line 3324 to enrich alerts

**Verification:**
- ✅ No direct Playwright dependency
- ✅ Uses database queries only
- ✅ Has fallback handling
- ✅ Properly integrated into alert flow

**Data Flow:**
1. News Radar detects alert
2. Calls `enrich_radar_alert_async()` to get context
3. Returns `EnrichmentContext` with match info
4. Alert is modified with enrichment line if applicable
5. Alert is sent to Telegram

**Conclusion:** Feature is properly integrated and doesn't introduce Playwright issues.

### VPS Deployment Verification

#### Current State

**Issues:**
1. ❌ Version mismatch between requirements.txt and installed version
2. ❌ Deploy script doesn't respect requirements.txt
3. ⚠️ Insufficient error handling for version access
4. ✅ Browser binary installation is verified in deploy script

**Required Fixes:**

1. **Update requirements.txt** to match installed version OR reinstall correct version
2. **Update setup_vps.sh** to respect requirements.txt version
3. **Add error handling** in news_radar.py for version access
4. **Verify browser binaries** are installed on VPS

#### Deployment Steps

After applying fixes, deploy to VPS:

```bash
# 1. Pull latest code
git pull origin main

# 2. Update virtual environment
source venv/bin/activate
pip install -r requirements.txt

# 3. Install Playwright browser binaries
python -m playwright install chromium
python -m playwright install-deps chromium

# 4. Verify installation
python -c "import playwright; print(f'Playwright {playwright.__version__} OK')"

# 5. Restart bot
./start_system.sh
```

---

## Summary of Corrections

| # | Issue | Severity | Status | Fix Required |
|---|--------|----------|--------------|
| 1 | Version mismatch (1.48.0 vs 1.58.0) | CRITICAL | ❌ Not Fixed | Update requirements.txt or reinstall |
| 2 | Deploy script doesn't pin version | CRITICAL | ❌ Not Fixed | Update setup_vps.sh line 122 |
| 3 | Missing error handling for __version__ | HIGH | ❌ Not Fixed | Add try-except in news_radar.py line 821 |
| 4 | New features integration | LOW | ✅ Verified | No changes needed |
| 5 | Browser binary installation | MEDIUM | ✅ Verified | Already in deploy script |

## Recommendations

1. **Immediate Action (Critical):**
   - Fix version mismatch in requirements.txt
   - Update deploy script to respect requirements.txt
   - Add error handling for version access

2. **Short-term (High Priority):**
   - Test Playwright installation on VPS
   - Verify browser binaries are installed
   - Run News Radar with diagnostics enabled

3. **Long-term (Medium Priority):**
   - Add automated version checking in CI/CD
   - Improve error messages for installation issues
   - Add health checks for Playwright in monitoring

---

**Report Generated:** 2026-03-04  
**Verification Mode:** Chain of Verification (CoVe) - Double Verification  
**Status:** ⚠️ **MULTIPLE CRITICAL ISSUES IDENTIFIED - FIXES REQUIRED**
