# Bug #20 Fix: Team Stats - None Values

**Date:** 2026-02-11  
**Bug ID:** #20  
**Type:** DATA QUALITY ISSUE  
**Priority:** 🟢 BASSA (Low)  
**Status:** ✅ RESOLVED

---

## Problem Description

During parallel enrichment, the system attempted to retrieve team statistics (goals, cards) from FotMob, but received `None` for all values. This was logged as:

```
Team stats for Hearts: goals=None, cards=None
Team stats for Hibernian: goals=None, cards=None
```

### Impact
- Team stats not available → incomplete analysis → reduced prediction quality
- The bot was making invalid API calls to FotMob

---

## Root Cause Analysis

### Primary Issue: Type Mismatch Bug

The `get_team_details` function in [`src/ingestion/data_provider.py`](src/ingestion/data_provider.py:637) expects a `team_id: int` parameter:

```python
def get_team_details(self, team_id: int, match_time: datetime = None) -> Optional[Dict]:
    """Get team details including squad and next match."""
    url = f"{self.BASE_URL}/teams?id={team_id}"
```

However, multiple functions were calling it with a `team_name: str` instead:

1. [`get_team_stats`](src/ingestion/data_provider.py:1533) - line 1533
2. [`get_full_team_context`](src/ingestion/data_provider.py:1341) - line 1341
3. [`get_turnover_risk`](src/ingestion/data_provider.py:1407) - line 1407
4. [`get_stadium_coordinates`](src/ingestion/data_provider.py:1474) - line 1474

### Secondary Issue: FotMob API Limitation

Even after fixing the type mismatch, FotMob API does not provide team statistics (goals per game, cards per game, corners per game). The API endpoint `/teams?id={id}` returns team details, squad information, and fixtures, but **not** seasonal statistics.

---

## Solution Implemented

### 1. Created Wrapper Function

Added a new wrapper function [`get_team_details_by_name`](src/ingestion/data_provider.py:695) that converts team names to team IDs before calling the API:

```python
def get_team_details_by_name(self, team_name: str, match_time: datetime = None) -> Optional[Dict]:
    """
    Get team details by team name (wrapper that converts name to ID).
    
    This is a convenience wrapper that converts a team name to a FotMob ID
    and then calls get_team_details with the ID.
    """
    try:
        # Convert team name to team ID
        team_id, fotmob_name = self.search_team_id(team_name)
        
        if team_id is None:
            logger.warning(f"⚠️ Team ID not found for: {team_name}")
            return {
                "_error": True,
                "_error_msg": f"Team not found: {team_name}",
                "team_id": None,
                "squad": {},
                "fixtures": {}
            }
        
        # Get team details using the ID
        return self.get_team_details(team_id, match_time)
    except Exception as e:
        logger.error(f"❌ Error getting team details by name for {team_name}: {e}")
        return {
            "_error": True,
            "_error_msg": str(e),
            "team_id": None,
            "squad": {},
            "fixtures": {}
        }
```

### 2. Updated Affected Functions

Updated all affected functions to use the wrapper:

- **[`get_team_stats`](src/ingestion/data_provider.py:1525)**: Now uses `get_team_details_by_name` and returns proper structure with helpful note
- **[`get_full_team_context`](src/ingestion/data_provider.py:1339)**: Now uses `get_team_details_by_name`
- **[`get_turnover_risk`](src/ingestion/data_provider.py:1405)**: Now uses `get_team_details_by_name`
- **[`get_stadium_coordinates`](src/ingestion/data_provider.py:1479)**: Now uses `get_team_details_by_name`

### 3. Enhanced Error Handling

Updated [`get_team_stats`](src/ingestion/data_provider.py:1525) to:

1. Return a consistent structure with all expected fields
2. Include a `source` field indicating data source
3. Include a `note` field explaining that FotMob doesn't provide statistics
4. Handle errors gracefully without crashing

```python
result = {
    'team_name': team_name,
    'goals_avg': None,
    'cards_avg': None,
    'corners_avg': None,
    'shots_avg': None,
    'possession_avg': None,
    'error': None,
    'source': 'fotmob',
    'note': 'FotMob does not provide team statistics. Use search providers (Tavily/Perplexity) for stats from footystats.org, soccerstats.com, or flashscore.com'
}
```

### 4. Fallback Mechanism

The system already has a fallback mechanism for team statistics through search providers:

- **Primary source:** [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:758) queries footystats.org
- **Secondary sources:** soccerstats.com, flashscore.com
- **Implementation:** The [`verification_layer`](src/analysis/verification_layer.py) uses Tavily/Perplexity search providers to query these sites

The fix ensures that:
1. FotMob provider returns `None` values gracefully with a helpful note
2. The search providers (Tavily/Perplexity) can be used to get team statistics from alternative sources
3. The system doesn't crash when FotMob doesn't have the data

---

## Testing

### Test Script

Created [`test_team_stats_fix.py`](test_team_stats_fix.py) with comprehensive tests:

1. **Test 1:** Verify `get_team_details_by_name` correctly converts team_name to team_id
2. **Test 2:** Verify `get_team_stats` returns proper structure with None values
3. **Test 3:** Verify `get_team_stats` handles errors gracefully
4. **Test 4:** Verify `get_full_team_context` uses the wrapper correctly
5. **Test 5:** Verify `get_stadium_coordinates` uses the wrapper correctly
6. **Test 6:** Verify `get_turnover_risk` uses the wrapper correctly

### Test Results

```
============================================================
Testing Bug #20 Fix: Team Stats - None Values
============================================================

=== Test 1: get_team_details_by_name ===
✅ get_team_details_by_name correctly converts team_name to team_id

=== Test 2: get_team_stats ===
✅ get_team_stats returns proper structure

=== Test 3: get_team_stats with error ===
✅ get_team_stats handles errors gracefully

=== Test 4: get_full_team_context ===
✅ get_full_team_context uses wrapper correctly

=== Test 5: get_stadium_coordinates ===
✅ get_stadium_coordinates uses wrapper correctly

=== Test 6: get_turnover_risk ===
✅ get_turnover_risk uses wrapper correctly

============================================================
Test Results: 6 passed, 0 failed
============================================================
```

---

## Files Modified

1. **[`src/ingestion/data_provider.py`](src/ingestion/data_provider.py)**
   - Added `get_team_details_by_name` wrapper function (lines 695-727)
   - Updated `get_team_stats` to use wrapper and enhanced error handling (lines 1525-1598)
   - Updated `get_full_team_context` to use wrapper (line 1341)
   - Updated `get_turnover_risk` to use wrapper (line 1407)
   - Updated `get_stadium_coordinates` to use wrapper (line 1474)

2. **[`test_team_stats_fix.py`](test_team_stats_fix.py)** (new file)
   - Comprehensive test suite for the fix

---

## Integration with Existing Data Flow

### Before Fix

```
get_team_stats("Hearts")
  └─> get_team_details("Hearts")  ❌ Type mismatch!
       └─> URL: https://api.fotmob.com/v1/teams?id=Hearts  ❌ Invalid API call!
            └─> Returns error or empty response
                 └─> stats = {}  ❌ Empty stats!
                      └─> goals_avg = None, cards_avg = None
```

### After Fix

```
get_team_stats("Hearts")
  └─> get_team_details_by_name("Hearts")  ✅ Correct!
       └─> search_team_id("Hearts")
            └─> Returns (12345, "Hearts")
                 └─> get_team_details(12345)  ✅ Valid API call!
                      └─> URL: https://api.fotmob.com/v1/teams?id=12345  ✅ Valid!
                           └─> Returns team details (no stats)
                                └─> Returns graceful response with note:
                                     "FotMob does not provide team statistics.
                                      Use search providers (Tavily/Perplexity) 
                                      for stats from footystats.org, 
                                      soccerstats.com, or flashscore.com"
```

### Fallback to Search Providers

When team statistics are needed:

```
Analysis Engine
  └─> verification_layer.build_team_stats_query()
       └─> Queries footystats.org (primary)
            └─> Falls back to soccerstats.com (secondary)
                 └─> Falls back to flashscore.com (tertiary)
                      └─> Returns parsed statistics
```

---

## VPS Compatibility

The fix is fully compatible with VPS deployment:

1. ✅ No new dependencies required
2. ✅ No environment configuration changes needed
3. ✅ No additional libraries to install
4. ✅ Graceful error handling prevents crashes
5. ✅ Works with existing API keys and authentication

---

## Summary

### Root Cause
Type mismatch bug: Functions were calling `get_team_details(team_name)` with a string, but the function expected `team_id: int`. This caused invalid API calls to FotMob.

### Fix Implemented
1. Created wrapper function `get_team_details_by_name` to convert team names to IDs
2. Updated all affected functions to use the wrapper
3. Enhanced error handling to return graceful responses
4. Added documentation explaining FotMob's limitations

### Fallback Mechanism
The system already has a robust fallback mechanism through search providers (Tavily/Perplexity) that query footystats.org, soccerstats.com, and flashscore.com for team statistics.

### Testing
All tests pass successfully. The fix:
- Corrects the type mismatch bug
- Prevents invalid API calls
- Returns graceful responses with helpful notes
- Doesn't crash the system
- Is fully compatible with VPS deployment

---

## Related Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) - System architecture overview
- [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py) - Search provider fallback mechanism
- [`src/utils/parallel_enrichment.py`](src/utils/parallel_enrichment.py) - Parallel enrichment data flow
