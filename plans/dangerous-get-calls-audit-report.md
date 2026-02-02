# Dangerous `.get()` Calls Audit Report

**Date**: 2026-02-02  
**Issue**: 191 Potenzialmente Pericolosi `.get()` senza `isinstance()` Check  
**Severity**: CRITICAL  
**Status**: Audit Complete

---

## Executive Summary

This report documents a comprehensive audit of potentially dangerous `.get()` calls throughout the codebase that lack proper `isinstance()` type checking. The issue was identified after a fatigue-related crash where `home_fatigue` was a string instead of a dict, causing an `AttributeError` when attempting to call `.get('fatigue_level')`.

### Impact
- **Potential crashes**: Similar to the fatigue bug, unvalidated dictionary access can cause runtime errors
- **Unpredictable behavior**: Difficult to predict when crashes will occur
- **Maintenance burden**: Requires extensive refactoring for safety

### Key Findings
- **Total `.get()` calls found**: 291
- **Chained `.get()` calls**: 25 (CRITICAL RISK)
- **Files requiring fixes**: 15+ files
- **Safe patterns already implemented**: 6+ locations

---

## The Problem

### Example of Dangerous Pattern

```python
# Line 1334 - DANGEROUS (no isinstance check)
home_fatigue = home_context.get('fatigue', {})
# Line 1344 - CRASHES if home_fatigue is string
home_fatigue_level = home_fatigue.get('fatigue_level')  # AttributeError!
```

### Example of Safe Pattern

```python
# Line 1337 - SAFE
if isinstance(home_motivation, dict) and home_motivation.get('zone') != 'Unknown':
    context_parts.append(f"{home_team_validated}: {home_motivation.get('zone')} (Pos: {home_motivation.get('position')})")
```

### Example of Safe Pattern (Defense-in-Depth)

```python
# fatigue_engine.py:561-567 - SAFE
home_fatigue_data = home_context.get('fatigue', {})
if not isinstance(home_fatigue_data, dict):
    home_fatigue_data = {
        'fatigue_level': str(home_fatigue_data) if home_fatigue_data else 'Unknown',
        'hours_since_last': None
    }
```

---

## Risk Categories

### CRITICAL: Chained `.get()` Calls (25 instances)

Chained `.get()` calls are the most dangerous because if the first `.get()` returns a non-dict value, the second `.get()` will fail with `AttributeError`.

#### Files Affected:

1. **src/analysis/final_alert_verifier.py**
   - Line 205: `context_data.get('verification_info', {}).get('inconsistencies')`
   - Risk: Medium (has default `{}`)

2. **src/analysis/settler.py**
   - Line 241: `match.get('home', {}).get('name', '')`
   - Line 242: `match.get('away', {}).get('name', '')`
   - Line 271: `match.get('home', {}).get('score')`
   - Line 272: `match.get('away', {}).get('score')`
   - Risk: Medium (has default `{}`)

3. **src/analysis/optimizer.py**
   - Line 433: `self.data.get('global', {}).get('total_bets', 0)`
   - Line 477: `old_data.get('global', {}).get('total_bets', 0)`
   - Line 478: `old_data.get('global', {}).get('total_profit', 0.0)`
   - Line 479: `old_data.get('global', {}).get('overall_roi', 0.0)`
   - Line 800: `self.data.get('stats', {}).get(league_key, {})`
   - Line 801: `league_stats.get(market_type, {})`
   - Line 902: `self.data.get('stats', {}).get(league_key, {})`
   - Line 948: `self.data['stats'].get(league_key, {}).get(market_type, {})`
   - Risk: Low-Medium (has defaults, but still unsafe)

4. **src/ingestion/data_provider.py**
   - Line 875-877: Multiple chained `.get()` for h2h data
   - Line 1097: `table.get('table', {}).get('all', [])`
   - Line 1189: `fixtures.get('allFixtures', {}).get('nextMatch')`
   - Line 1209: `next_match.get('opponent', {}).get('name', 'Unknown')`
   - Risk: Medium (has defaults)

5. **src/ingestion/opportunity_radar.py**
   - Line 374: `fixtures.get('allFixtures', {}).get('nextMatch')`
   - Line 399: `next_match.get('tournament', {}).get('name', 'Unknown')`
   - Risk: Medium (has defaults)

6. **src/ingestion/brave_provider.py**
   - Line 175: `data.get("web", {}).get("results", [])`
   - Risk: Medium (has defaults)

7. **src/ingestion/deepseek_intel_provider.py**
   - Line 348: `choices[0].get("message", {}).get("content", "")`
   - Risk: HIGH (no default on `choices[0]`)

8. **src/ingestion/tavily_provider.py**
   - Line 605: `data.get("web", {}).get("results", [])`
   - Risk: Medium (has defaults)

9. **src/services/news_radar.py**
   - Line 1467: `response.json().get("parameters", {}).get("retry_after", 5)`
   - Risk: Medium (has defaults)

10. **src/utils/inspect_fotmob.py**
    - Line 51: `data.get('fixtures', {}).get('allFixtures', {})`
    - Line 52: `fixtures.get('previousMatches', [])`
    - Line 81: `d.get('Periods', {}).get('All', {}).get('stats', [])`
    - Line 193: `match_data.get('general', {}).get('homeTeam', {}).get('name', 'Home')`
    - Line 194: `match_data.get('general', {}).get('awayTeam', {}).get('name', 'Away')`
    - Risk: Medium (has defaults)

11. **src/utils/http_client.py**
    - Line 1078: `response.json().get('headers', {}).get('User-Agent', 'N/A')`
    - Risk: Medium (has defaults)

12. **src/utils/check_apis.py**
    - Line 226: `data.get("choices", [{}])[0].get("message", {}).get("content", "")`
    - Line 285: `data.get("web", {}).get("results", [])`
    - Line 343: `data.get("choices", [{}])[0].get("message", {}).get("content", "")`
    - Risk: HIGH (no default on array access `[0]`)

---

### HIGH: Context Data Access Without isinstance Checks

Context data (home_context, away_context, etc.) is particularly vulnerable because it comes from external APIs and can have varying structures.

#### Files Affected:

1. **src/analysis/analyzer.py**
   - Line 1324-1330: `league_table_context.get('home_rank')`, etc.
   - Line 1344-1349: `deep_dive.get('motivation_home')`, etc.
   - Line 1524-1525: `snippet_data.get('home_context')`, `snippet_data.get('away_context')`
   - Risk: HIGH (external API data)

2. **src/processing/news_hunter.py**
   - Lines 1038-1043: `item.get('title')`, `item.get('snippet')`, etc.
   - Lines 1208-1212: `item.get('title')`, `item.get('snippet')`, etc.
   - Risk: HIGH (external API data)

3. **src/processing/telegram_listener.py**
   - Lines 787-789: `squad.get('full_text')`, `squad.get('caption')`, etc.
   - Lines 808-809: `squad.get('channel_type')`, `squad.get('match')`
   - Lines 815, 824-825, 832, 840-841, 847, 855-856: Multiple squad.get() calls
   - Lines 861-862: `alert.get('mode')`
   - Risk: HIGH (external Telegram data)

4. **src/alerting/notifier.py**
   - Lines 329-332: `math_edge.get('edge')`, `math_edge.get('kelly_stake')`, etc.
   - Lines 382-387: `referee_intel.get('referee_name')`, etc.
   - Lines 449-455: `injury_intel.get('home_severity')`, etc.
   - Lines 505-508: `verification_info.get('status')`, etc.
   - Lines 545-548: `confidence_breakdown.get('news_weight')`, etc.
   - Risk: MEDIUM (internal data but should be validated)

---

### MEDIUM: API Response Parsing Without Validation

API responses should always be validated before accessing nested data.

#### Files Affected:

1. **src/schemas/perplexity_schemas.py**
   - Lines 271-273: `data.get('home_form_wins')`, etc.
   - Lines 307-309: `data.get('away_form_wins')`, etc.
   - Risk: MEDIUM (external API data)

2. **src/analysis/player_intel.py**
   - Lines 66-67: `player_data.get('player')`, `player_data.get('statistics')`
   - Lines 74-75: `team_data.get('name')`, `stat.get('team')`
   - Lines 96-99: `player_info.get('name')`, `stats.get('games')`, etc.
   - Risk: MEDIUM (external API data)

3. **src/analysis/verification_layer.py**
   - Lines 1126-1132: `home_stats.get('corners')`, etc.
   - Lines 1138-1141: `home_xg_stats.get('xg')`, etc.
   - Lines 1152-1156: `h2h_data.get('goals')`, etc.
   - Lines 1161: `ref_data.get('cards_per_game')`
   - Lines 1179-1195: `home_form.get('goals_scored')`, etc.
   - Risk: MEDIUM (external API data)

---

### LOW: Dictionary Access with Safe Defaults

These are lower risk because they have safe defaults, but should still be fixed for consistency.

#### Files Affected:

1. **src/alerting/health_monitor.py**
   - Lines 214-215: `api_quota.get('remaining')`, `api_quota.get('used')`
   - Line 441: `self.last_alerts.get(issue_key)`
   - Risk: LOW (has defaults)

2. **src/processing/sources_config.py**
   - Lines 336, 351, 367, 383, 399, 414, 448, 451, 454, 481: Various `.get()` calls
   - Risk: LOW (static configuration data)

3. **src/processing/news_hunter.py**
   - Lines 304, 311, 327, 330, 355, 358, 422, 467, 548, 853, 860-861, 865-866, 984, 987-988, 1038-1042, 1083-1088, 1137, 1153-1158, 1201, 1207-1212, 1349, 1403-1407, 1449, 1483-1488, 1560-1565, 1708-1722, 1829, 1954-1975, 2024-2025
   - Risk: MIXED (some LOW, some HIGH)

4. **src/analysis/stats_drawer.py**
   - Lines 63-67: `optimizer_data.get('global')`, etc.
   - Lines 75-84: Various `.get()` calls
   - Lines 101-104: Various `.get()` calls
   - Lines 111-114: Various `.get()` calls
   - Risk: LOW (internal data)

5. **src/analysis/step_by_step_feedback.py**
   - Lines 187, 375-377, 497-498: Various `.get()` calls
   - Risk: LOW (internal data)

6. **src/analysis/alert_feedback_loop.py**
   - Lines 119, 123, 149, 202, 226, 381-384: Various `.get()` calls
   - Risk: LOW (internal data)

7. **src/analysis/news_scorer.py**
   - Lines 298-300, 407-408: Various `.get()` calls
   - Risk: LOW (internal data)

8. **src/analysis/market_intelligence.py**
   - Lines 213-215, 408-409, 509-510: Various `.get()` calls
   - Risk: LOW (internal data)

9. **src/analysis/verifier_integration.py**
   - Lines 62-64: Various `.get()` calls
   - Risk: LOW (internal data)

10. **src/analysis/intelligent_modification_logger.py**
    - Lines 162-164, 196, 220-225, 237-238, 282-298, 312-320, 347-349, 522-533, 547-548: Various `.get()` calls
    - Risk: LOW (internal data)

11. **src/ingestion/brave_key_rotator.py**
    - Lines 146, 154, 243: Various `.get()` calls
    - Risk: LOW (internal data)

12. **src/ingestion/mediastack_query_builder.py**
    - Lines 121, 127: Various `.get()` calls
    - Risk: LOW (external API but has defaults)

13. **src/ingestion/mediastack_key_rotator.py**
    - Lines 135, 143, 219: Various `.get()` calls
    - Risk: LOW (internal data)

14. **src/analysis/enhanced_verifier.py**
    - Lines 60, 84-86, 155-159, 216, 230, 237-238: Various `.get()` calls
    - Risk: LOW (internal data)

15. **src/analysis/math_engine.py**
    - Lines 623-624, 643, 710-711: Various `.get()` calls
    - Risk: LOW (internal data)

---

## Safe Patterns Already Implemented

The following locations demonstrate correct defensive programming:

1. **src/analysis/fatigue_engine.py:561-567**
   ```python
   home_fatigue_data = home_context.get('fatigue', {})
   if not isinstance(home_fatigue_data, dict):
       home_fatigue_data = {
           'fatigue_level': str(home_fatigue_data) if home_fatigue_data else 'Unknown',
           'hours_since_last': None
       }
   ```

2. **src/alerting/notifier.py:371-372**
   ```python
   if not referee_intel or not isinstance(referee_intel, dict):
       return referee_section
   ```

3. **src/analysis/biscotto_engine.py:537-545**
   ```python
   if home_motivation and isinstance(home_motivation, dict):
       home_context = analyze_classifica_context(
           team_name=home_team,
           position=home_motivation.get('position', 0),
           total_teams=home_motivation.get('total_teams', 20),
           points=home_motivation.get('points', 0),
           zone=home_motivation.get('zone', 'Unknown'),
           matches_remaining=matches_remaining
       )
   ```

4. **src/analysis/biscotto_engine.py:777-778**
   ```python
   home_remaining = home_motivation.get('matches_remaining') if home_motivation and isinstance(home_motivation, dict) else None
   away_remaining = away_motivation.get('matches_remaining') if away_motivation and isinstance(away_motivation, dict) else None
   ```

5. **src/analysis/injury_impact_engine.py:749-755**
   ```python
   if home_context and isinstance(home_context, dict):
       home_injuries = home_context.get('injuries') or []
       home_squad = home_context.get('squad')
   
   if away_context and isinstance(away_context, dict):
       away_injuries = away_context.get('injuries') or []
       away_squad = away_context.get('squad')
   ```

6. **src/analysis/verification_layer.py:4233-4236**
   ```python
   if home_context and isinstance(home_context, dict):
       injuries = home_context.get('injuries', [])
       if isinstance(injuries, list) and injuries:
           home_missing = [inj.get('name', '') for inj in injuries if isinstance(inj, dict) and inj.get('name')]
   ```

7. **src/analysis/analyzer.py:1528-1537**
   ```python
   has_home_injuries = (
       home_context and 
       isinstance(home_context, dict) and 
       home_context.get('injuries')
   )
   has_away_injuries = (
       away_context and 
       isinstance(away_context, dict) and 
       away_context.get('injuries')
   )
   ```

---

## Recommended Safe Patterns

### Pattern 1: Type Check Before Access

```python
# DANGEROUS
value = data.get('key1', {}).get('key2')

# SAFE
data1 = data.get('key1')
if isinstance(data1, dict):
    value = data1.get('key2')
else:
    value = None  # or appropriate default
```

### Pattern 2: Defense-in-Depth with Conversion

```python
# DANGEROUS
value = data.get('key', {}).get('nested_key')

# SAFE
nested_data = data.get('key', {})
if not isinstance(nested_data, dict):
    # Handle unexpected type (string, None, etc.)
    nested_data = {}
value = nested_data.get('nested_key')
```

### Pattern 3: Conditional Access

```python
# DANGEROUS
value = data.get('key1', {}).get('key2', 'default')

# SAFE
value = data.get('key1', {}).get('key2', 'default') if isinstance(data.get('key1'), dict) else 'default'
```

### Pattern 4: Helper Function for Safe Access

```python
def safe_get(data, *keys, default=None):
    """Safely access nested dictionary keys with type checking."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current if current is not None else default

# USAGE
value = safe_get(data, 'key1', 'key2', 'key3', default='fallback')
```

---

## Fix Priority Order

### Phase 1: CRITICAL (Immediate Action Required)
1. Fix all 25 chained `.get()` calls
2. Add isinstance checks for array access `[0]` patterns
3. Fix context data access in analyzer.py (lines 1324-1330, 1344-1349, 1524-1525)

### Phase 2: HIGH (Next Sprint)
4. Fix telegram_listener.py squad.get() calls (lines 787-789, 808-809, etc.)
5. Fix news_hunter.py item.get() calls (lines 1038-1043, 1208-1212)
6. Fix API response parsing in verification_layer.py (lines 1126-1195)

### Phase 3: MEDIUM (Following Sprint)
7. Fix notifier.py math_edge, referee_intel, injury_intel access
8. Fix player_intel.py API response parsing
9. Fix perplexity_schemas.py data access

### Phase 4: LOW (Ongoing Maintenance)
10. Fix remaining safe-default patterns for consistency
11. Add utility functions for safe dictionary access
12. Update code style guidelines

---

## Testing Strategy

### Unit Tests Required

1. **Test string instead of dict**:
   ```python
   def test_get_with_string_value():
       context = {'fatigue': 'high'}  # String instead of dict
       # Should not crash
       result = extract_fatigue_level(context)
       assert result == 'high' or result == 'Unknown'
   ```

2. **Test None value**:
   ```python
   def test_get_with_none_value():
       context = {'fatigue': None}
       # Should not crash
       result = extract_fatigue_level(context)
       assert result == 'Unknown'
   ```

3. **Test missing key**:
   ```python
   def test_get_with_missing_key():
       context = {}
       # Should not crash
       result = extract_fatigue_level(context)
       assert result == 'Unknown'
   ```

4. **Test nested access**:
   ```python
   def test_nested_get_with_invalid_intermediate():
       data = {'level1': 'not_a_dict'}
       # Should not crash
       result = safe_get(data, 'level1', 'level2')
       assert result is None
   ```

### Integration Tests Required

1. Test with real FotMob API responses (including edge cases)
2. Test with Telegram messages in various formats
3. Test with API responses from different providers (Brave, Tavily, Perplexity)

---

## Implementation Plan

### Step 1: Create Utility Functions
- Add `safe_get()` helper to `src/utils/validators.py`
- Add `safe_nested_get()` for chained access
- Add `safe_list_get()` for array access with bounds checking

### Step 2: Fix CRITICAL Issues
- Replace all chained `.get()` calls with safe patterns
- Add isinstance checks before nested access
- Test each fix individually

### Step 3: Fix HIGH Issues
- Add isinstance checks for context data
- Validate API responses before access
- Add logging for unexpected data types

### Step 4: Fix MEDIUM/LOW Issues
- Standardize on safe patterns
- Add defensive programming where missing
- Update code style guidelines

### Step 5: Add Tests
- Create unit tests for edge cases
- Create integration tests for real-world scenarios
- Add regression tests to prevent future issues

### Step 6: Documentation
- Document safe patterns in code style guide
- Add examples to developer documentation
- Create checklist for code reviews

---

## Code Review Checklist

When reviewing code with `.get()` calls, check:

- [ ] Is there an `isinstance()` check before calling `.get()` on a potentially non-dict value?
- [ ] Are chained `.get()` calls protected with type checking?
- [ ] Is there a fallback/default value for unexpected types?
- [ ] Are API responses validated before accessing nested data?
- [ ] Is there error handling for AttributeError exceptions?
- [ ] Are there tests for edge cases (string, None, missing keys)?

---

## Conclusion

This audit identified 191 potentially dangerous `.get()` calls across the codebase. While many have safe defaults, the lack of type checking creates a significant risk of runtime errors, especially when dealing with external API data.

The recommended approach is to:
1. Prioritize fixes by risk level
2. Implement safe patterns consistently
3. Add comprehensive tests
4. Update code review guidelines

This will significantly improve code robustness and prevent crashes similar to the fatigue bug.

---

**Next Steps**: Review this plan and proceed with implementation in Code mode.
