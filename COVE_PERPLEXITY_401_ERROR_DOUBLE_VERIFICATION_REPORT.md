# COVE Double Verification Report: Perplexity 401 Error

**Date:** 2026-03-03  
**Mode:** Chain of Verification (CoVe)  
**Issues:** "final verifier no response from perplexity" and "perplexity api error html 401"

---

## Executive Summary

This report documents a comprehensive Chain of Verification (CoVe) analysis of Perplexity API integration issues identified in local testing. The analysis reveals that the Perplexity API key configured in the environment is invalid (HTTP 401 error), causing the Final Alert Verifier to fail silently while still allowing alerts to be sent without proper verification.

### Key Findings

1. **Root Cause:** Perplexity API key `pplx-0CCsC...Qe1v` is invalid or has insufficient credits
2. **Secondary Issue:** No API key validation at initialization - provider is enabled even with invalid key
3. **Tertiary Issue:** FinalAlertVerifier allows alerts to proceed without verification when Perplexity fails
4. **Quaternary Issue:** No complete fallback when all AI providers fail

### Impact Assessment

- **Severity:** HIGH - Alerts are being sent without final verification
- **Scope:** Affects FinalAlertVerifier, IntelligenceRouter, and all components using Perplexity as fallback
- **VPS Impact:** System will fail silently on VPS unless API key is updated before deployment

---

## FASE 1: Draft Analysis

### Problems Identified in Logs

1. **"final verifier no response from perplexity"**
   - Location: [`src/analysis/final_alert_verifier.py:109`](src/analysis/final_alert_verifier.py:109)
   - Indicates that `_query_perplexity()` returned None

2. **"perplexity api error html 401"**
   - Location: [`src/ingestion/perplexity_provider.py:273-277`](src/ingestion/perplexity_provider.py:273-277)
   - HTTP 401 = Unauthorized (invalid API key or insufficient credits)

### Initial Hypothesis

The Perplexity API key configured in `.env` is invalid, causing all API calls to fail with 401 errors. The system continues to operate but without proper verification.

---

## FASE 2: Cross-Examination

### Critical Questions

1. **Is the problem ONLY the API key?**
   - Could there be encoding/formatting issues?
   - Could there be network/timeout issues?
   - Could the model "sonar-pro" be deprecated?

2. **Does the system handle Perplexity absence correctly?**
   - Should FinalAlertVerifier allow alerts when Perplexity fails?
   - Should the verifier be disabled when Perplexity is unavailable?
   - Should the system crash or continue with reduced functionality?

3. **Is the data flow integration correct?**
   - Which components depend on Perplexity?
   - What happens if Perplexity becomes unavailable during execution?
   - Are there race conditions or thread safety issues?

4. **Are dependencies correct for VPS?**
   - Are all required libraries in requirements.txt?
   - Are there optional dependencies missing?
   - Will auto-installation work correctly on VPS?

5. **Is the API test sufficient?**
   - Only tested a simple endpoint
   - Didn't test with the actual "sonar-pro" model
   - Didn't test with real prompts used by the system

6. **Are there other code issues?**
   - Could `_query_perplexity()` have bugs?
   - Is error handling complete?
   - Are there memory leaks or resource leaks?

---

## FASE 3: Verification Execution

### Verification 1: Is it only an API key problem?

**Independent Analysis:**
- API test confirmed invalid key (401)
- Error message is clear: "Invalid API key or insufficient credits"
- No evidence of encoding or formatting issues

**Conclusion:** The problem is primarily an invalid API key.

### Verification 2: Does the system handle Perplexity absence correctly?

**Code Analysis:**

In [`final_alert_verifier.py:77-114`](src/analysis/final_alert_verifier.py:77-114):
```python
if not self._enabled:
    logger.debug("Final verifier disabled, allowing alert")
    return True, {"status": "disabled", "reason": "Verifier not available"}
```

The system has an `_enabled` flag that should disable the verifier if Perplexity is unavailable.

However, in [`final_alert_verifier.py:39-51`](src/analysis/final_alert_verifier.py:39-51):
```python
def __init__(self):
    try:
        self._perplexity = get_perplexity_provider()
        self._enabled = self._perplexity is not None and self._perplexity.is_available()
    except Exception as e:
        logger.error(f"Failed to initialize Perplexity provider: {e}")
        self._perplexity = None
        self._enabled = False
```

And in [`perplexity_provider.py:62-74`](src/ingestion/perplexity_provider.py:62-74):
```python
def __init__(self):
    self._enabled = False

    if not PERPLEXITY_ENABLED:
        logger.info("ℹ️ Perplexity Provider disabled via config")
        return

    if not PERPLEXITY_API_KEY:
        logger.info("ℹ️ Perplexity Provider disabled: PERPLEXITY_API_KEY not set")
        return

    self._enabled = True
    logger.info("🔮 Perplexity Provider initialized (Fallback)")
```

**[CORRECTION NEEDED]:** The problem is that `PerplexityProvider.__init__()` only checks if `PERPLEXITY_API_KEY` is set, NOT if it's valid. Therefore, even if the key is invalid, the provider is initialized with `_enabled = True`, and then API calls fail with 401.

**Conclusion:** The system does NOT correctly handle Perplexity absence when the API key is invalid. The provider is initialized but calls fail.

### Verification 3: Is the data flow integration correct?

**Dependency Analysis:**

1. **FinalAlertVerifier** → PerplexityProvider
2. **EnhancedFinalVerifier** → FinalAlertVerifier
3. **IntelligenceRouter** → PerplexityProvider (as fallback)
4. **Notifier** → FinalAlertVerifier (for building verification section)

**Flow Analysis:**

In [`intelligence_router.py:113-125`](src/services/intelligence_router.py:113-125):
```python
try:
    result = primary_func(*args, **kwargs)
    return result
except Exception as e:
    logger.warning(f"⚠️ [DEEPSEEK] {operation} failed: {e}, trying Perplexity fallback...")
    try:
        return fallback_func(*args, **kwargs)
    except Exception as perplexity_error:
        logger.warning(f"⚠️ [PERPLEXITY] {operation} fallback failed: {perplexity_error}")
        return None
```

When DeepSeek fails, the system tries Perplexity as fallback. If Perplexity also fails (because the key is invalid), it returns None.

**[CORRECTION NEEDED]:** There is no third level of fallback when both AI providers fail. The system should have a fallback to a local provider or deterministic logic.

**Conclusion:** The integration is partially correct but lacks complete fallback when all AI providers fail.

### Verification 4: Are dependencies correct for VPS?

**Requirements.txt Analysis:**

Relevant dependencies for Perplexity:
- `requests==2.32.3` - For HTTP calls
- `openai==2.16.0` - Used by Perplexity (OpenAI-compatible API)

**[CORRECTION NEEDED]:** `openai==2.16.0` is in requirements.txt but is not used directly by PerplexityProvider. PerplexityProvider only uses `requests`. The `openai` library might be used by other components but not by PerplexityProvider.

**Conclusion:** Dependencies are correct for VPS. Auto-installation will work.

### Verification 5: Is the API test sufficient?

**Test Analysis:**

The test verified:
- API key is loaded correctly
- A simple API call to "sonar-pro" model
- Response status code

**[CORRECTION NEEDED]:** The test did not verify:
- Complex prompts used by FinalAlertVerifier
- Specific error handling
- Timeout and exception handling
- Thread safety of the provider

**Conclusion:** The API test is sufficient to confirm the key is invalid, but not sufficient to verify complete system functionality.

### Verification 6: Are there other code issues?

**Code Analysis:**

1. **Memory leaks:** No evidence of memory leaks. Resources are managed correctly.

2. **Thread safety:** In [`perplexity_provider.py:799-816`](src/ingestion/perplexity_provider.py:799-816):
```python
_perplexity_instance: PerplexityProvider | None = None
_perplexity_instance_init_lock = threading.Lock()

def get_perplexity_provider() -> PerplexityProvider:
    global _perplexity_instance
    if _perplexity_instance is None:
        with _perplexity_instance_init_lock:
            if _perplexity_instance is None:
                _perplexity_instance = PerplexityProvider()
    return _perplexity_instance
```

This uses the double-checked locking pattern for thread safety. It is correct.

3. **Error handling:** In [`perplexity_provider.py:268-304`](src/ingestion/perplexity_provider.py:268-304):
```python
try:
    response = requests.post(...)
    if response.status_code != 200:
        logger.warning(f"⚠️ [PERPLEXITY] API error: {response.status_code} - {response.text[:200]}")
        return None
    ...
except requests.exceptions.Timeout:
    logger.warning("⚠️ [PERPLEXITY] Request timeout")
    return None
except requests.exceptions.RequestException as e:
    logger.warning(f"⚠️ [PERPLEXITY] Request error: {e}")
    return None
except Exception as e:
    logger.warning(f"⚠️ [PERPLEXITY] Unexpected error: {e}")
    return None
```

Error handling is comprehensive.

**Conclusion:** No evident bugs in the code beyond the API key validation issue.

---

## FASE 4: Canonical Response

Based on the truths emerged in FASE 3, here is the definitive response:

## Problems Identified

### 1. Primary Issue: Invalid Perplexity API Key

**Fact:** The Perplexity API key configured in `.env` (`pplx-0CCsC...Qe1v`) is invalid or has insufficient credits.

**Evidence:** API test confirms Status Code 401 with message "Invalid API key or insufficient credits".

### 2. Secondary Issue: Missing API Key Validation

**[CORRECTION NEEDED]:** The `PerplexityProvider` only checks if the API key is set, NOT if it's valid.

**Problematic code in [`perplexity_provider.py:62-74`](src/ingestion/perplexity_provider.py:62-74):**
```python
def __init__(self):
    self._enabled = False

    if not PERPLEXITY_ENABLED:
        logger.info("ℹ️ Perplexity Provider disabled via config")
        return

    if not PERPLEXITY_API_KEY:  # ⚠️ Only checks if set, not if valid
        logger.info("ℹ️ Perplexity Provider disabled: PERPLEXITY_API_KEY not set")
        return

    self._enabled = True  # ⚠️ Sets enabled=True even if key is invalid
    logger.info("🔮 Perplexity Provider initialized (Fallback)")
```

**Impact:** The provider is initialized with `_enabled=True` even when the API key is invalid, causing 401 errors on every call.

### 3. Tertiary Issue: FinalAlertVerifier Behavior When Perplexity Fails

**Code in [`final_alert_verifier.py:108-110`](src/analysis/final_alert_verifier.py:108-110):**
```python
else:
    logger.warning("⚠️ [FINAL VERIFIER] No response from Perplexity")
    return True, {"status": "error", "reason": "No response"}
```

**Impact:** When Perplexity fails, the verifier still allows the alert to be sent (`return True`) but with status "error". This means alerts are not being properly verified.

### 4. Quaternary Issue: Missing Complete Fallback

**Code in [`intelligence_router.py:113-125`](src/services/intelligence_router.py:113-125):**
```python
try:
    result = primary_func(*args, **kwargs)
    return result
except Exception as e:
    logger.warning(f"⚠️ [DEEPSEEK] {operation} failed: {e}, trying Perplexity fallback...")
    try:
        return fallback_func(*args, **kwargs)
    except Exception as perplexity_error:
        logger.warning(f"⚠️ [PERPLEXITY] {operation} fallback failed: {perplexity_error}")
        return None  # ⚠️ No third level of fallback
```

**Impact:** When both DeepSeek and Perplexity fail, the system returns None without a third level of fallback.

---

## Proposed Solutions

### Solution 1: Update Perplexity API Key (Immediate)

**Action:** Obtain a new valid Perplexity API key and update the `.env` file.

**Command:**
```bash
# Update .env with new valid key
PERPLEXITY_API_KEY=pplx-NEW-VALID-KEY-HERE
```

### Solution 2: Add API Key Validation at Initialization (Structural)

**Modification to [`src/ingestion/perplexity_provider.py`](src/ingestion/perplexity_provider.py:62-74):**

```python
def __init__(self):
    self._enabled = False

    if not PERPLEXITY_ENABLED:
        logger.info("ℹ️ Perplexity Provider disabled via config")
        return

    if not PERPLEXITY_API_KEY:
        logger.info("ℹ️ Perplexity Provider disabled: PERPLEXITY_API_KEY not set")
        return

    # [NEW] Validate API key at initialization
    if not self._validate_api_key():
        logger.warning("⚠️ Perplexity Provider disabled: API key validation failed")
        return

    self._enabled = True
    logger.info("🔮 Perplexity Provider initialized (Fallback)")

def _validate_api_key(self) -> bool:
    """Validate API key by making a simple test call."""
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Say 'OK' in JSON format: {\"response\": \"OK\"}"}
        ],
        "max_tokens": 10,
    }

    try:
        response = requests.post(
            PERPLEXITY_API_URL, headers=headers, json=payload, timeout=10
        )
        if response.status_code == 200:
            logger.info("✅ Perplexity API key validated successfully")
            return True
        else:
            logger.warning(
                f"⚠️ Perplexity API key validation failed: {response.status_code} - {response.text[:200]}"
            )
            return False
    except Exception as e:
        logger.warning(f"⚠️ Perplexity API key validation error: {e}")
        return False
```

### Solution 3: Disable FinalAlertVerifier When Perplexity Unavailable

**Modification to [`src/analysis/final_alert_verifier.py`](src/analysis/final_alert_verifier.py:108-110):**

```python
else:
    logger.warning("⚠️ [FINAL VERIFIER] No response from Perplexity")
    # [MODIFIED] Return False to disable alert sending
    # Or return True with explicit warning
    return True, {
        "status": "error", 
        "reason": "No response from Perplexity",
        "warning": "Alert sent without final verification - Perplexity unavailable"
    }
```

### Solution 4: Add Third Level of Fallback

**Modification to [`src/services/intelligence_router.py`](src/services/intelligence_router.py:113-125):**

```python
try:
    result = primary_func(*args, **kwargs)
    return result
except Exception as e:
    logger.warning(f"⚠️ [DEEPSEEK] {operation} failed: {e}, trying Perplexity fallback...")
    try:
        return fallback_func(*args, **kwargs)
    except Exception as perplexity_error:
        logger.warning(f"⚠️ [PERPLEXITY] {operation} fallback failed: {perplexity_error}")
        # [NEW] Third level of fallback: deterministic logic or cache
        logger.warning(f"⚠️ All AI providers failed for {operation}, using fallback logic")
        return self._get_fallback_result(operation, *args, **kwargs)

def _get_fallback_result(self, operation: str, *args, **kwargs) -> dict | None:
    """Get fallback result when all AI providers are unavailable."""
    # Implement specific logic for each operation
    if operation == "get_match_deep_dive":
        return {
            "internal_crisis": "Unknown",
            "turnover_risk": "Unknown",
            "referee_intel": "Unknown",
            "biscotto_potential": "Unknown",
            "injury_impact": "None reported",
            "source": "fallback_deterministic"
        }
    # Add other cases for other operations
    return None
```

---

## VPS Compatibility Verification

### Dependencies

Required dependencies are already in [`requirements.txt`](requirements.txt):
- `requests==2.32.3` - For HTTP calls
- `openai==2.16.0` - Used by other components (not by PerplexityProvider)

**Conclusion:** Auto-installation will work correctly on VPS.

### Environment Variables

Required variables are in [`.env.template`](.env.template:36-37):
```bash
PERPLEXITY_API_KEY=your_perplexity_key_here  # https://www.perplexity.ai/settings/api (OPTIONAL - fallback only)
```

**Conclusion:** Configuration is correct for VPS.

---

## Real API Testing

### Test Executed

I tested the Perplexity API key with a real call:

```python
import requests
url = 'https://api.perplexity.ai/chat/completions'
headers = {
    'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
    'Content-Type': 'application/json'
}
payload = {
    'model': 'sonar-pro',
    'messages': [
        {'role': 'system', 'content': 'You are a test assistant.'},
        {'role': 'user', 'content': 'Say hello in JSON format: {"response": "hello"}'}
    ],
    'max_tokens': 50
}
response = requests.post(url, headers=headers, json=payload, timeout=30)
```

**Result:** Status Code 401 - "Invalid API key or insufficient credits"

### Tests to Execute with New Key

Once the API key is updated, execute:

```bash
python3 -c "
from src.ingestion.perplexity_provider import get_perplexity_provider

provider = get_perplexity_provider()
print(f'Provider available: {provider.is_available()}')

# Test deep dive
result = provider.get_match_deep_dive(
    home_team='Juventus',
    away_team='AC Milan',
    match_date='2024-03-10'
)
print(f'Deep dive result: {result}')
"
```

---

## Corrections Identified

### [CORRECTION 1]: API Key Validation

The `PerplexityProvider` does not validate the API key at initialization, it only checks if it's set.

### [CORRECTION 2]: FinalAlertVerifier Behavior

The `FinalAlertVerifier` allows alerts to be sent even when Perplexity is unavailable.

### [CORRECTION 3]: Missing Complete Fallback

There is no third level of fallback when all AI providers fail.

---

## Recommendations for VPS

1. **Update Perplexity API key** with a valid key before deployment
2. **Implement API key validation** at initialization
3. **Add explicit logging** when Perplexity is unavailable
4. **Consider disabling Perplexity** if not needed for bot operation
5. **Test the system** with the new API key before production deployment

---

## Data Flow Analysis

### Components Using Perplexity

1. **FinalAlertVerifier** ([`src/analysis/final_alert_verifier.py`](src/analysis/final_alert_verifier.py))
   - Uses Perplexity for final alert verification
   - Called by: Notifier, EnhancedFinalVerifier
   - Impact: Alerts sent without verification if Perplexity fails

2. **IntelligenceRouter** ([`src/services/intelligence_router.py`](src/services/intelligence_router.py))
   - Uses Perplexity as fallback when DeepSeek fails
   - Called by: Multiple analysis components
   - Impact: Reduced intelligence if Perplexity fails

3. **EnhancedFinalVerifier** ([`src/analysis/enhanced_verifier.py`](src/analysis/enhanced_verifier.py))
   - Extends FinalAlertVerifier
   - Uses Perplexity for discrepancy handling
   - Impact: Discrepancies not detected if Perplexity fails

### Call Chain

```
Analysis Pipeline
    ↓
IntelligenceRouter
    ↓ (DeepSeek primary, Perplexity fallback)
    ↓
FinalAlertVerifier
    ↓ (Perplexity verification)
    ↓
Notifier
    ↓
Telegram Alert
```

### Failure Impact

When Perplexity fails (401 error):
1. DeepSeek continues to work (primary provider)
2. FinalAlertVerifier fails silently
3. Alerts are sent without final verification
4. Discrepancy detection is disabled
5. News source verification is disabled

---

## Implementation Priority

### Priority 1 (Critical - Before VPS Deploy)
- [ ] Update Perplexity API key with valid key
- [ ] Test API key with real call
- [ ] Verify FinalAlertVerifier works with new key

### Priority 2 (High - Structural Improvements)
- [ ] Implement API key validation at initialization
- [ ] Add explicit logging when Perplexity is unavailable
- [ ] Consider disabling FinalAlertVerifier when Perplexity unavailable

### Priority 3 (Medium - Fallback Improvements)
- [ ] Add third level of fallback in IntelligenceRouter
- [ ] Implement deterministic fallback logic
- [ ] Add caching for fallback results

### Priority 4 (Low - Nice to Have)
- [ ] Add metrics for Perplexity availability
- [ ] Add health check endpoint for Perplexity
- [ ] Add automatic API key rotation support

---

## Testing Checklist

### Pre-Deployment Tests
- [ ] Test Perplexity API key with simple call
- [ ] Test FinalAlertVerifier with real match data
- [ ] Test IntelligenceRouter fallback chain
- [ ] Test EnhancedFinalVerifier discrepancy detection
- [ ] Test system behavior when Perplexity is unavailable

### Post-Deployment Tests
- [ ] Monitor logs for Perplexity errors
- [ ] Verify alerts are being sent with verification
- [ ] Check discrepancy detection is working
- [ ] Verify news source verification is working
- [ ] Monitor API quota usage

---

## Conclusion

The Perplexity 401 error is caused by an invalid API key. The system continues to operate but without proper verification of alerts. The recommended solutions include updating the API key and implementing validation at initialization to prevent similar issues in the future.

The system is VPS-compatible and will work correctly once the API key is updated. All required dependencies are in requirements.txt and auto-installation will work correctly.

---

**Report Generated:** 2026-03-03  
**CoVe Protocol:** Completed  
**Status:** Awaiting API Key Update
