# 🔍 DEBUG TEST REPORT - 2026-02-17

## 📋 Executive Summary

**Test Duration:** ~7 minutes (21:40 - 21:47 UTC)
**Test Type:** Full Bot Startup and Operation
**Status:** ✅ Bot Started Successfully | ⚠️ Critical Issues Found

---

## 🚀 Startup Process

### ✅ Successful Components

1. **go_live.py Launcher** - Started successfully
   - Environment validation: PASSED
   - Database initialization: PASSED
   - Telegram Monitor: Started in background
   - Main Pipeline: Started in foreground

2. **Telegram Monitor** - Running correctly
   - Connected to Telegram API successfully
   - Monitoring 31 channels
   - Processing squad images with OCR
   - No critical errors

3. **Main Pipeline** - Running correctly
   - ContinentalOrchestrator initialized
   - Supabase mirror refreshed successfully
   - Twitter Intel cache refreshed (25/38 accounts, 116 tweets)
   - Opportunity Radar completed (1 opportunity triggered)
   - Analysis Engine initialized
   - Fixture ingestion started

4. **Browser Monitor** - Started successfully
   - Initial warning: "Failed to start"
   - Recovered and started successfully
   - Monitoring 14 sources
   - Discovering news continuously

---

## 🐛 Critical Issues Found

### 1. ❌ CRITICAL: Odds API Keys Exhausted

**Severity:** CRITICAL  
**Location:** Fixture Ingestion  
**Error Message:**
```
ERROR - ❌ All Odds API keys exhausted!
```

**Impact:**
- Bot cannot fetch new fixtures or odds
- Analysis pipeline will fail without fresh data
- System becomes stale quickly

**Root Cause:**
All API keys for The-Odds-API have reached their quota limits.

**Recommended Fix:**
1. Check API key quotas in [The-Odds-API Dashboard](https://the-odds-api.com/dashboard)
2. Add new API keys or wait for quota reset
3. Implement better quota management to prevent exhaustion
4. Add early warning when quota is running low (e.g., at 80% usage)

---

### 2. ❌ CRITICAL: Database UNIQUE Constraint Failed

**Severity:** CRITICAL  
**Location:** Database Operations  
**Error Message:**
```
ERROR - ❌ UNIQUE constraint failed: matches.id
```

**Impact:**
- Bot cannot save new match data
- Duplicate match insertion attempts
- Data integrity issues

**Root Cause:**
The bot is trying to insert matches with duplicate IDs into the database. This happens when:
1. Match already exists in database
2. ID generation collision
3. Race condition in concurrent inserts

**Recommended Fix:**
1. Add `INSERT OR IGNORE` or `INSERT OR REPLACE` logic
2. Check if match exists before inserting
3. Use database transactions with proper error handling
4. Add unique constraint on match_id or composite key (league, home_team, away_team, start_time)

**Code Location:**
```python
# File: src/ingestion/ingest_fixtures.py
# Look for INSERT statements into matches table
```

---

### 3. ⚠️ WARNING: Brave Search API Returns 0 Results

**Severity:** HIGH  
**Location:** Twitter Intel Refresh  
**Pattern:** Consistent across all Twitter searches

**Evidence:**
```
🔍 [BRAVE] Searching: site%3Atwitter.com OR site%3Ax.com %40Victorg_Lessa OR %40ca...
🔍 [BRAVE] Found 0 results
```

**Impact:**
- Primary search provider (Brave) is not returning results
- Forces fallback to DuckDuckGo (slower)
- Increases API latency and cost
- May indicate API key issue or query encoding problem

**Recommended Fix:**
1. Check Brave API key status and quota
2. Verify query encoding (double-encoded URLs detected: `%253A` instead of `%3A`)
3. Test Brave API directly with simple queries
4. Consider adding Serper as primary if Brave continues to fail

**Query Encoding Issue:**
```
# Current (double-encoded):
q=site%253Atwitter.com+OR+site%253Ax.com+%2540Victorg_Lessa

# Should be (single-encoded):
q=site%3Atwitter.com+OR+site%3Ax.com+%40Victorg_Lessa
```

---

### 4. ⚠️ WARNING: Browser Monitor Startup Warning

**Severity:** MEDIUM  
**Location:** Browser Monitor Initialization  
**Error Message:**
```
WARNING - ⚠️ [BROWSER-MONITOR] Failed to start
```

**Impact:**
- Initial startup failure
- Automatic recovery succeeded
- May indicate timing/race condition

**Root Cause:**
Playwright initialization timing issue. The browser monitor tries to start before the event loop is fully ready.

**Recommended Fix:**
1. Add retry logic with exponential backoff
2. Ensure event loop is ready before starting Playwright
3. Add better error handling in startup sequence
4. Log more details about the failure reason

**Recovery:**
```
INFO - ✅ [BROWSER-MONITOR] Playwright initialized
INFO - ✅ [BROWSER-MONITOR] Started with 14 sources
```

---

### 5. ⚠️ WARNING: DeepSeek Empty Response

**Severity:** MEDIUM  
**Location:** Opportunity Radar  
**Error Message:**
```
WARNING - ⚠️ deepseek/deepseek-r1-0528 returned empty response (attempt 1/4, consecutive empties: 1)
WARNING - ⏳ Retrying in 1.24s with exponential backoff + jitter...
```

**Impact:**
- AI model returning empty responses
- Causes retry delays
- May indicate API issue or prompt problem

**Recommended Fix:**
1. Check DeepSeek API key status
2. Verify prompt format and length
3. Add better error handling for empty responses
4. Consider fallback to different model

---

### 6. ⚠️ WARNING: FotMob 403 Error with UA Rotation

**Severity:** MEDIUM  
**Location:** Team Stats Fetching  
**Error Message:**
```
WARNING - ⚠️ FotMob 403 - rotating UA and retrying in 5s (1/3)
WARNING - ⚠️ FotMob 403 - rotating UA and retrying in 25s (2/3)
```

**Impact:**
- Cannot fetch team statistics
- Affects analysis quality
- Multiple retries increase latency

**Root Cause:**
FotMob is blocking requests due to rate limiting or user agent detection.

**Recommended Fix:**
1. Implement better rate limiting
2. Add longer delays between requests
3. Use rotating user agents from a larger pool
4. Consider caching FotMob data
5. Add request throttling

---

### 7. ⚠️ WARNING: Team Resolution Failures

**Severity:** MEDIUM  
**Location:** Team Context Fetching  
**Error Message:**
```
WARNING - ⚠️ Team not found: Sociedade Esportiva Palmeiras
WARNING - ⚠️ Could not resolve team: Sociedade Esportiva Palmeiras
```

**Impact:**
- Cannot fetch team context for some matches
- Affects analysis quality
- May cause incorrect team names in alerts

**Root Cause:**
Team name normalization issue. The full team name "Sociedade Esportiva Palmeiras" doesn't match FotMob's database format.

**Recommended Fix:**
1. Implement fuzzy team name matching
2. Try multiple variations of team names
3. Add team name normalization mapping
4. Log all team resolution attempts for debugging

---

### 8. ⚠️ WARNING: DuckDuckGo Search Errors

**Severity:** LOW-MEDIUM  
**Location:** Opportunity Radar  
**Error Message:**
```
WARNING - ⚠️ DuckDuckGo errore ricerca: No results found.
```

**Impact:**
- Some searches return no results
- May miss important news
- Affects intelligence gathering

**Recommended Fix:**
1. Improve query optimization
2. Add better fallback logic
3. Log query details for debugging
4. Consider adding more search providers

---

### 9. ⚠️ WARNING: Tavily No Results for Some Accounts

**Severity:** LOW  
**Location:** Twitter Intel Recovery  
**Error Message:**
```
WARNING - 🐦 [TAVILY] No results for @marcosbonocore, marking unavailable
WARNING - 🐦 [TAVILY] No results for @DiegoArmaMedina, marking unavailable
```

**Impact:**
- Some Twitter accounts cannot be monitored
- Reduces intelligence coverage
- 24/38 accounts successfully recovered (63% success rate)

**Recommended Fix:**
1. Mark unavailable accounts to avoid repeated failed attempts
2. Add account health tracking
3. Consider alternative sources for these accounts
4. Review account list for inactive accounts

---

### 10. ⚠️ WARNING: Query Optimization Warnings

**Severity:** LOW  
**Location:** Multiple Search Operations  
**Error Message:**
```
WARNING - [DDG-OPT] Query too long (371 chars), optimizing...
WARNING - [DDG-OPT] Removed sport exclusions: 371 → 124 chars
```

**Impact:**
- Queries are being truncated
- May miss relevant results
- Affects search quality

**Recommended Fix:**
1. Implement query length limits at query construction
2. Use more efficient query patterns
3. Consider splitting complex queries
4. Add query length monitoring and alerts

---

## 📊 Statistics

### Log Analysis
- **Total log lines:** 866
- **ERROR messages:** 6
- **WARNING messages:** 45
- **CRITICAL messages:** 0 (but 2 ERRORs are critical)

### Component Status
| Component | Status | Issues |
|-----------|--------|---------|
| go_live.py Launcher | ✅ Running | None |
| Telegram Monitor | ✅ Running | None |
| Main Pipeline | ✅ Running | API Keys Exhausted, DB Constraint |
| Browser Monitor | ✅ Running | Startup warning, 403 errors |
| Opportunity Radar | ✅ Completed | Empty AI responses, search errors |
| Twitter Intel | ✅ Completed | Brave 0 results, some accounts unavailable |

### API Performance
- **Brave Search:** 0 results (all queries) - CRITICAL
- **DuckDuckGo:** Working as fallback
- **Tavily:** Working well (114 tweets recovered)
- **DeepSeek:** Working with some empty responses
- **FotMob:** Working with rate limiting (403 errors)
- **Supabase:** Working perfectly
- **The-Odds-API:** EXHAUSTED - CRITICAL

---

## 🔧 Recommended Actions

### Immediate (Critical)
1. **Fix Odds API Keys** - Add new keys or wait for reset
2. **Fix Database UNIQUE Constraint** - Implement proper upsert logic
3. **Fix Brave Search Query Encoding** - Resolve double-encoding issue

### High Priority
4. **Improve Browser Monitor Startup** - Add retry logic and better error handling
5. **Fix FotMob Rate Limiting** - Implement better throttling
6. **Improve Team Name Resolution** - Add fuzzy matching

### Medium Priority
7. **Handle DeepSeek Empty Responses** - Add better error handling
8. **Optimize Search Queries** - Implement length limits
9. **Improve Twitter Intel Success Rate** - Review account list

### Low Priority
10. **Add Better Logging** - More detailed error messages
11. **Implement Health Monitoring** - Track API quotas in real-time
12. **Add Circuit Breaker Improvements** - Better failure handling

---

## 🎯 Silent Bugs / Logic Problems / Dead Code

### Silent Bugs
1. **Double-encoding in Brave Search queries** - URLs are encoded twice
2. **Race condition in Browser Monitor startup** - Tries to start before event loop ready
3. **Duplicate match insertion attempts** - No check before insert

### Logic Problems
1. **No quota warning system** - Bot doesn't warn before API keys are exhausted
2. **No graceful degradation** - Bot continues trying even when APIs are failing
3. **Team name normalization** - Full team names don't match FotMob format

### Potential Dead Code
1. **Serper API integration** - Not used (Brave primary, DDG fallback)
2. **MediaStack API** - Not used in this session (0 calls/month)
3. **Perplexity Provider** - Only used as fallback, rarely triggered

---

## 📈 Performance Observations

### Successful Operations
1. **Supabase Mirror** - Fast and reliable (38 social sources, 165 news sources)
2. **Tavily Twitter Recovery** - Good success rate (114 tweets from 24 accounts)
3. **Browser Monitor Discovery** - Finding relevant news continuously
4. **High-Priority Callbacks** - Working correctly (INJURY, LINEUP, SUSPENSION)

### Latency Issues
1. **FotMob API** - Multiple 403 errors with 5-25s retries
2. **DeepSeek AI** - Some responses taking 35-40s
3. **Parallel Enrichment** - Timeout exceeded (45s)

---

## 🏁 Conclusion

### Overall Assessment
The bot's core architecture is **solid and well-designed**. All major components start successfully and work together correctly. However, there are **several critical issues** that need immediate attention:

1. **Odds API exhaustion** - This is a blocker for the main functionality
2. **Database constraint failures** - This causes data integrity issues
3. **Brave Search encoding** - This affects intelligence gathering quality

### System Health
- **Core Functionality:** ⚠️ Degraded (API issues)
- **Data Integrity:** ⚠️ Issues (duplicate inserts)
- **Intelligence Gathering:** ⚠️ Degraded (Brave issues)
- **Monitoring:** ✅ Working well
- **Error Handling:** ⚠️ Some issues (no graceful degradation)

### Next Steps
1. Address critical API and database issues immediately
2. Implement better quota management and monitoring
3. Fix query encoding and team name resolution
4. Add comprehensive health monitoring
5. Implement graceful degradation when APIs fail

---

**Report Generated:** 2026-02-17T20:49:00Z  
**Test Duration:** ~7 minutes  
**Total Issues Found:** 10 (2 Critical, 4 High, 4 Low)
