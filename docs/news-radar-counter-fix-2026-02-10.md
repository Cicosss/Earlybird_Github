# News Radar Counter Fix - 2026-02-10

## Summary

Fixed Bug #18: News Radar counter showing "URLs scanned: 0" even though sources were scanned.

## Problem Description

### Symptoms
- **Warning:** `Final Statistics: URLs scanned: 0, Alerts sent: 0, Cache size: 49`
- **Impact:** Counter shows 0 even though 7 sources were scanned
- **Frequency:** Occurred when News Radar process was interrupted (e.g., SIGTERM)

### Root Cause
In [`src/services/news_radar.py`](src/services/news_radar.py:1805-1889), the `scan_cycle()` method uses a LOCAL variable `urls_scanned` (initialized at line 1816) that is only assigned to `self._urls_scanned` at the END of the method (line 1888).

When the process is interrupted (e.g., by SIGTERM) before the method completes, the assignment never happens, so `self._urls_scanned` remains at 0.

### Code Flow

```python
async def scan_cycle(self) -> int:
    """Execute one scan cycle over all due sources."""
    alerts_sent = 0
    urls_scanned = 0  # ← LOCAL variable
    
    # Get sources due for scanning
    due_sources = [s for s in self._config.sources if s.is_due_for_scan()]
    
    # Separate single-page and paginated sources
    single_sources = [s for s in due_sources if s.navigation_mode != "paginated"]
    paginated_sources = [s for s in due_sources if s.navigation_mode == "paginated"]
    
    # Process single sources
    if single_sources:
        for source in single_sources:
            if not self._running or self._stop_event.is_set():
                break
            
            content = contents.get(source.url)
            urls_scanned += 1  # ← Increment LOCAL variable
            
            if content:
                alert = await self._process_content(content, source, source.url)
                if alert:
                    if self._alerter and await self._alerter.send_alert(alert):
                        alerts_sent += 1
                        self._alerts_sent += 1
    
    # Process paginated sources
    for source in paginated_sources:
        if not self._running or self._stop_event.is_set():
                break
            
        alert = await self.scan_source(source)
        urls_scanned += 1  # ← Increment LOCAL variable
            
        if alert:
            if self._alerter and await self._alerter.send_alert(alert):
                alerts_sent += 1
                self._alerts_sent += 1
    
    self._urls_scanned = urls_scanned  # ← Assignment only happens if loop completes
    return alerts_sent
```

### Why It Failed

When SIGTERM is received:
1. Main loop calls `stop()` which sets `self._stop_event`
2. Next iteration of loops checks `if not self._running or self._stop_event.is_set()` and breaks
3. Method returns early without reaching line 1888
4. `self._urls_scanned` remains at 0 (initialized value)

## Solution

Modified [`src/services/news_radar.py`](src/services/news_radar.py) to update `self._urls_scanned` IMMEDIATELY after incrementing the counter in both loops:

### 1. Single Sources Loop (line 1854)
```python
# BEFORE
content = contents.get(source.url)
breaker = self._get_circuit_breaker(source.url)
urls_scanned += 1

if content:
    breaker.record_success()
    alert = await self._process_content(content, source, source.url)
    
    if alert:
        if self._alerter and await self._alerter.send_alert(alert):
            alerts_sent += 1
            self._alerts_sent += 1
else:
    breaker.record_failure()

# Update last scanned time
source.last_scanned = datetime.now(timezone.utc)

# AFTER
content = contents.get(source.url)
breaker = self._get_circuit_breaker(source.url)
urls_scanned += 1

# Update counter immediately to avoid loss on interruption
self._urls_scanned = urls_scanned  # ← ADDED

if content:
    breaker.record_success()
    alert = await self._process_content(content, source, source.url)
    
    if alert:
        if self._alerter and await self._alerter.send_alert(alert):
            alerts_sent += 1
            self._alerts_sent += 1
else:
    breaker.record_failure()

# Update last scanned time
source.last_scanned = datetime.now(timezone.utc)
```

### 2. Paginated Sources Loop (line 1877)
```python
# BEFORE
alert = await self.scan_source(source)
urls_scanned += 1

if alert:
    if self._alerter and await self._alerter.send_alert(alert):
        alerts_sent += 1
        self._alerts_sent += 1

# Update last scanned time
source.last_scanned = datetime.now(timezone.utc)

# AFTER
alert = await self.scan_source(source)
urls_scanned += 1

# Update counter immediately to avoid loss on interruption
self._urls_scanned = urls_scanned  # ← ADDED

if alert:
    if self._alerter and await self._alerter.send_alert(alert):
        alerts_sent += 1
        self._alerts_sent += 1

# Update last scanned time
source.last_scanned = datetime.now(timezone.utc)
```

## Testing

### Test 1: Verify Counter Updates on Interruption
```bash
# Start News Radar
python3 run_news_radar.py &

# Wait for some sources to be scanned
sleep 30

# Send SIGTERM
kill -SIGTERM <pid>

# Check final statistics
tail -20 news_radar.log | grep "URLs scanned"
```

**Expected Result:** `URLs scanned: > 0` (number of sources scanned before interruption)

### Test 2: Verify Counter Updates on Normal Completion
```bash
# Start News Radar and let it complete one cycle
python3 run_news_radar.py

# Check final statistics
tail -20 news_radar.log | grep "URLs scanned"
```

**Expected Result:** `URLs scanned: 35` (or number of due sources)

## Impact

### Fixed
- ✅ Counter `urls_scanned` now updates immediately after each source is scanned
- ✅ Counter is preserved even if process is interrupted (SIGTERM, SIGINT)
- ✅ Final statistics accurately reflect number of sources scanned

### Backward Compatibility
- ✅ No changes to API
- ✅ All existing callsites continue to work
- ✅ Final assignment at line 1888 still happens for normal completion

### Related Issues
- This fix is separate from the "no alerts sent" issue, which is actually CORRECT behavior
- The system found high-value signals but skipped sending alerts because there were no matches within 72 hours
- This is the expected behavior to avoid sending alerts for outdated news

## Files Modified

1. [`src/services/news_radar.py`](src/services/news_radar.py:1854) - Added `self._urls_scanned = urls_scanned` in single sources loop
2. [`src/services/news_radar.py`](src/services/news_radar.py:1877) - Added `self._urls_scanned = urls_scanned` in paginated sources loop
3. [`DEBUG_TEST_REPORT_2026-02-10.md`](DEBUG_TEST_REPORT_2026-02-10.md:418-472) - Marked Bug #18 as resolved

## Verification

To verify the fix is working:

```bash
# Check that counter updates correctly
grep "URLs scanned" news_radar.log | tail -5

# Expected output after interruption:
# URLs scanned: 7 (or number of sources scanned before SIGTERM)

# Expected output after normal completion:
# URLs scanned: 35 (or number of all sources)
```

## Lessons Learned

1. **Update counters immediately:** When tracking progress with counters, update the persistent counter immediately after each operation, not just at the end of the method
2. **Handle interruptions gracefully:** Always consider that async methods can be interrupted at any point, so ensure critical state is preserved
3. **Test interruption scenarios:** When fixing issues related to counters/statistics, test with process interruption (SIGTERM, SIGINT) to ensure counters are preserved
4. **Local vs instance variables:** Be careful with local variables that hold state - they are lost if the method exits early

## Future Improvements

Consider adding similar fixes to other components that track progress:
- Main bot cycle counter
- News hunter statistics
- Other long-running operations with progress counters

This would ensure consistent behavior across all components when processes are interrupted.
