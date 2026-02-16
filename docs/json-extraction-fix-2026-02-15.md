# JSON Extraction Failure Fix - Implementation Summary

**Date**: 2026-02-15
**Severity**: MEDIUM
**Component**: AI Response Parsing
**Status**: ✅ IMPLEMENTED

---

## Problem Description

The AI (DeepSeek/OpenRouter) was not always returning valid JSON in its responses, causing the JSON parser to fail and fall back to raw text.

**Symptoms**:
- Warning message: `JSON extraction failed: No valid JSON object found. Returning raw intel.`
- 4 failures logged on 2026-02-15 during `deep_dive` operations
- Downstream systems received incomplete intelligence (truncated to 1000 chars)

---

## Root Cause Analysis (COVE Verified)

**Primary Issue**: Missing System Prompts in DeepSeek Calls

The `deepseek_intel_provider.py` was NOT using system prompts with explicit JSON instructions, while:
- `PerplexityProvider` WAS using system prompts ✅
- `analyzer.py` WAS using system prompts ✅
- System prompts existed in `src/prompts/system_prompts.py` but were unused ❌

**Architectural Inconsistency**:

| Component | Uses System Prompts | JSON Instructions | Status |
|------------|-------------------|-------------------|---------|
| PerplexityProvider | ✅ Yes | `DEEP_DIVE_SYSTEM_PROMPT` | Working |
| analyzer.py | ✅ Yes | `TRIANGULATION_SYSTEM_PROMPT` | Working |
| deepseek_intel_provider.py | ❌ No | None | **BROKEN** |

**Evidence**:
- `_call_deepseek()` only sent user messages: `[{"role": "user", "content": prompt}]`
- `DEEP_DIVE_SYSTEM_PROMPT` explicitly states: "Respond ONLY with a single JSON object"
- `DEEP_DIVE_PROMPT_TEMPLATE` intentionally removed JSON instructions (V4.6)
- Comment: "Removed OUTPUT FORMAT blocks - now handled by structured outputs system prompts"

---

## Implementation Details

### Changes Made to `src/ingestion/deepseek_intel_provider.py`

#### 1. Added System Prompts Import (Line 38-39)

```python
from src.prompts.system_prompts import (
    BETTING_STATS_SYSTEM_PROMPT,
    DEEP_DIVE_SYSTEM_PROMPT,
)
```

#### 2. Updated Class Docstring (Line 70-76)

Added V6.3 documentation:
```python
"""
Provider AI che usa DeepSeek via OpenRouter + Brave Search.
Drop-in replacement per GeminiAgentProvider.

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1-2.8

V6.3: Added system prompts for JSON output consistency.
Matches PerplexityProvider and analyzer.py architecture to fix
JSON extraction failures.
"""
```

#### 3. Modified `_call_deepseek()` Method (Line 287-318)

**Before**:
```python
def _call_deepseek(self, prompt: str, operation_name: str) -> str | None:
    messages = [{"role": "user", "content": prompt}]
    return self._call_model(self._model_a, messages, operation_name=operation_name)
```

**After**:
```python
def _call_deepseek(
    self, prompt: str, operation_name: str, task_type: str = None
) -> str | None:
    # V6.3: Select system prompt based on task type
    system_prompt = None
    if task_type == "deep_dive":
        system_prompt = DEEP_DIVE_SYSTEM_PROMPT
    elif task_type == "betting_stats":
        system_prompt = BETTING_STATS_SYSTEM_PROMPT

    # Build messages with system prompt if available
    if system_prompt:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = [{"role": "user", "content": prompt}]

    return self._call_model(self._model_a, messages, operation_name=operation_name)
```

#### 4. Updated `get_deep_dive_intel()` Caller (Line 713)

**Before**:
```python
response_text = self._call_deepseek(final_prompt, "deep_dive")
```

**After**:
```python
response_text = self._call_deepseek(final_prompt, "deep_dive", task_type="deep_dive")
```

#### 5. Updated `get_betting_stats()` Caller (Line 778)

**Before**:
```python
response_text = self._call_deepseek(final_prompt, "betting_stats")
```

**After**:
```python
response_text = self._call_deepseek(final_prompt, "betting_stats", task_type="betting_stats")
```

#### 6. Added Debug Logging (Line 483-485)

```python
# V6.3: Debug logging for response content (first 500 chars)
logger.debug(f"🔍 [DEEPSEEK] Response preview: {content[:500] if content else 'EMPTY'}")
```

---

## Why This Fix Works

### System Prompts Provide Explicit JSON Instructions

The `DEEP_DIVE_SYSTEM_PROMPT` contains:
```
STRICT FORMAT RULES:
- Respond ONLY with a single JSON object.
- The JSON MUST match EXACTLY this schema:
  {
    "internal_crisis": "High/Medium/Low - Explanation",
    "turnover_risk": "High/Medium/Low - Explanation",
    ...
  }

CONSTRAINTS:
- NO markdown, NO prose outside the JSON.
- NO trailing commas, valid UTF-8 JSON only.
```

### Architectural Consistency

Now all three components use the same pattern:
1. **PerplexityProvider**: System prompt + User message ✅
2. **analyzer.py**: System prompt + User message ✅
3. **deepseek_intel_provider.py**: System prompt + User message ✅ (FIXED)

### Debug Logging

Added response preview logging to:
- Aid in future diagnosis
- Verify that responses now contain valid JSON
- Monitor for any remaining issues

---

## Testing Recommendations

### 1. Monitor Logs

Watch for these log messages:
```bash
# Should NO LONGER see:
WARNING - JSON extraction failed: No valid JSON object found. Returning raw intel.

# Should NOW see:
DEBUG - 🔍 [DEEPSEEK] Response preview: {"internal_crisis": "Low - No crisis detected", ...}
```

### 2. Verify JSON Extraction

Check that responses are parsed correctly:
```bash
grep "✅ [DEEPSEEK] deep_dive complete" earlybird.log
```

Should be followed by successful parsing (no warning).

### 3. Verify Data Quality

Check that `raw_intel` field is no longer populated:
```bash
grep "raw_intel" earlybird.log
```

Should show significantly fewer or no entries.

---

## Future Enhancements

### 1. Add System Prompts for Other Operations

Currently only `deep_dive` and `betting_stats` have system prompts. Consider adding for:
- `news_verification`
- `biscotto_confirmation`
- `match_enrichment`
- `twitter_batch`

### 2. Investigate OpenRouter Structured Output

OpenRouter may support `response_format` with `json_schema`:
```python
payload = {
    "model": model,
    "messages": messages,
    "response_format": {
        "type": "json_schema",
        "json_schema": {...}  # Pydantic model schema
    }
}
```

This would provide even stronger JSON guarantees.

### 3. Lower Temperature

Consider reducing temperature from 0.3 to 0.1 for more consistent output:
```python
"temperature": kwargs.get("temperature", 0.1)  # Was 0.3
```

Matches PerplexityProvider's temperature (0.1).

---

## Files Modified

1. `src/ingestion/deepseek_intel_provider.py`
   - Added system prompts import
   - Updated class docstring
   - Modified `_call_deepseek()` to accept and use task_type
   - Updated `get_deep_dive_intel()` to pass task_type="deep_dive"
   - Updated `get_betting_stats()` to pass task_type="betting_stats"
   - Added debug logging for response preview

---

## Verification Checklist

- [x] System prompts imported from `src.prompts.system_prompts`
- [x] `_call_deepseek()` accepts task_type parameter
- [x] System prompts selected based on task type
- [x] Messages built with system + user prompts
- [x] All callers updated to pass task_type
- [x] Debug logging added for response preview
- [x] Documentation updated (class docstring)
- [ ] Monitor logs for JSON extraction failures
- [ ] Verify data quality improvement
- [ ] Consider adding system prompts for other operations

---

## Impact Assessment

**Before Fix**:
- 4 JSON extraction failures on 2026-02-15
- Intelligence truncated to 1000 chars in `raw_intel` field
- Downstream systems received incomplete data

**After Fix** (Expected):
- DeepSeek receives explicit JSON instructions
- Responses should be pure JSON (no conversational text)
- JSON extraction should succeed consistently
- Full intelligence data available to downstream systems

**Risk**: LOW
- System prompts are well-tested in PerplexityProvider and analyzer.py
- Change is additive (doesn't break existing functionality)
- Debug logging provides visibility if issues arise

---

## Related Documentation

- `src/prompts/system_prompts.py` - System prompt definitions
- `src/utils/ai_parser.py` - JSON extraction logic
- `src/ingestion/perplexity_provider.py` - Reference implementation
- `src/analysis/analyzer.py` - Reference implementation

---

**Implementation Complete**: 2026-02-15
**COVE Verification**: ✅ PASSED
**Status**: Ready for testing and deployment
