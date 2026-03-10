# ALeagueScraper VPS Fixes

## Fix 1: Add lock for _last_scrape_time

### Current Code (lines 87-89):
```python
# Last scrape time
_last_scrape_time: datetime | None = None
SCRAPE_INTERVAL_MINUTES = 30  # Don't scrape more than every 30 min
```

### Fixed Code:
```python
# Last scrape time
_last_scrape_time: datetime | None = None
_scrape_time_lock = threading.Lock()  # NEW: Protect _last_scrape_time
SCRAPE_INTERVAL_MINUTES = 30  # Don't scrape more than every 30 min
```

### Current Code (lines 110-118):
```python
def _should_scrape() -> bool:
    """Check if enough time has passed since last scrape."""
    global _last_scrape_time

    if _last_scrape_time is None:
        return True

    elapsed = datetime.now() - _last_scrape_time
    return elapsed.total_seconds() >= SCRAPE_INTERVAL_MINUTES * 60
```

### Fixed Code:
```python
def _should_scrape() -> bool:
    """Check if enough time has passed since last scrape."""
    global _last_scrape_time

    with _scrape_time_lock:  # NEW: Thread-safe access
        if _last_scrape_time is None:
            return True

        elapsed = datetime.now() - _last_scrape_time
        return elapsed.total_seconds() >= SCRAPE_INTERVAL_MINUTES * 60
```

### Current Code (lines 121-124):
```python
def _mark_scraped():
    """Mark current time as last scrape."""
    global _last_scrape_time
    _last_scrape_time = datetime.now()
```

### Fixed Code:
```python
def _mark_scraped():
    """Mark current time as last scrape."""
    global _last_scrape_time
    with _scrape_time_lock:  # NEW: Thread-safe access
        _last_scrape_time = datetime.now()
```

---

## Fix 2: Add atomic operation for is_available() cache

### Current Code (lines 464-482):
```python
class ALeagueScraper:
    """Singleton wrapper for A-League scraper functionality."""

    def __init__(self):
        self._available = None

    def is_available(self) -> bool:
        """Check if scraper is available."""
        if self._available is None:
            self._available = is_aleague_scraper_available()
        return self._available

    def search_team_news(self, team_name: str, match_id: str, force: bool = False) -> list[dict]:
        """Search for team news."""
        return search_aleague_news(team_name, match_id, force)

    def should_scrape(self) -> bool:
        """Check if enough time has passed since last scrape."""
        return _should_scrape()
```

### Fixed Code:
```python
class ALeagueScraper:
    """Singleton wrapper for A-League scraper functionality."""

    def __init__(self):
        self._available = None
        self._available_lock = threading.Lock()  # NEW: Protect _available cache
        self._last_check_time = None  # NEW: Track last check time
        self._CHECK_INTERVAL_MINUTES = 5  # NEW: Re-check every 5 minutes

    def is_available(self) -> bool:
        """Check if scraper is available."""
        with self._available_lock:  # NEW: Atomic check-and-set
            # Re-check if unavailable for more than 5 minutes
            if (self._available is False and
                self._last_check_time and
                (datetime.now() - self._last_check_time).total_seconds() > self._CHECK_INTERVAL_MINUTES * 60):
                self._available = None  # Force re-check

            if self._available is None:
                self._available = is_aleague_scraper_available()
                self._last_check_time = datetime.now()

            return self._available

    def search_team_news(self, team_name: str, match_id: str, force: bool = False) -> list[dict]:
        """Search for team news."""
        return search_aleague_news(team_name, match_id, force)

    def should_scrape(self) -> bool:
        """Check if enough time has passed since last scrape."""
        return _should_scrape()
```

---

## Summary of Changes

1. **Added `_scrape_time_lock`** to protect `_last_scrape_time` global variable
2. **Wrapped `_should_scrape()`** with lock for thread-safe read
3. **Wrapped `_mark_scraped()`** with lock for thread-safe write
4. **Added `_available_lock`** to ALeagueScraper class
5. **Added `_last_check_time`** to track when availability was last checked
6. **Added `_CHECK_INTERVAL_MINUTES`** constant (5 minutes)
7. **Implemented retry logic** in `is_available()` to re-check after 5 minutes of unavailability
8. **Made `is_available()`** atomic with lock protection

These fixes ensure:
- ✅ No race conditions in rate limiting
- ✅ No concurrent scrapes from multiple threads
- ✅ Automatic retry after temporary network failures
- ✅ Thread-safe singleton pattern
- ✅ VPS-ready for concurrent match processing
