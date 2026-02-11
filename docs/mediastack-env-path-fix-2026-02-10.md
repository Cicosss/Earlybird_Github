# MediaStack Environment Path Fix - 2026-02-10

## Summary

Fixed Bug #16: MediaStackKeyRotator not finding valid API keys when the bot is started from a different directory.

## Problem Description

### Symptoms
- **Warning:** `MediaStackKeyRotator: No valid API keys found!`
- **Impact:** MediaStack provider disabled, loss of news source for fallback
- **Frequency:** Occurred every time the bot was started from a directory other than `/home/linux/Earlybird_Github`

### Root Cause
In [`src/main.py`](src/main.py:39), `load_dotenv()` was called without specifying the path to the `.env` file:

```python
# BEFORE (incorrect)
from dotenv import load_dotenv
load_dotenv()  # Looks for .env in current working directory
```

When the bot was started from a different directory (e.g., via `launcher.py` or from a VPS with a different working directory), `load_dotenv()` could not find the `.env` file, and the MediaStack API keys were not loaded into the environment.

### Why It Worked Sometimes
- When running `python3 src/main.py` from `/home/linux/Earlybird_Github`, the current working directory was correct, so `load_dotenv()` found the `.env` file
- When running from a different directory (e.g., `/tmp`), the `.env` file was not found, and keys were not loaded

## Solution

Modified [`src/main.py`](src/main.py:37-40) to explicitly specify the path to the `.env` file:

```python
# AFTER (correct)
from dotenv import load_dotenv
# Calculate .env path relative to this file to ensure it works from any directory
env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_file)
```

### How It Works
1. `__file__` → Path to `src/main.py` (e.g., `/home/linux/Earlybird_Github/src/main.py`)
2. `os.path.abspath(__file__)` → Absolute path to `src/main.py`
3. `os.path.dirname(...)` → Parent directory (`/home/linux/Earlybird_Github/src`)
4. `os.path.dirname(...)` → Grandparent directory (`/home/linux/Earlybird_Github`)
5. `os.path.join(..., '.env')` → Path to `.env` file (`/home/linux/Earlybird_Github/.env`)

This ensures that the `.env` file is always loaded from the correct location, regardless of the current working directory.

## Testing

### Test 1: Load from Different Directory
```bash
cd /tmp
python3 -c "import sys; sys.path.insert(0, '/home/linux/Earlybird_Github'); from src.main import *; import os; print('MEDIASTACK_API_KEY_1:', os.getenv('MEDIASTACK_API_KEY_1', 'NOT SET'))"
```

**Result:** ✅ Keys loaded correctly (`757ba57e51058d48f40f949042506859`)

### Test 2: MediaStackKeyRotator from Different Directory
```bash
cd /tmp
python3 -c "import sys; sys.path.insert(0, '/home/linux/Earlybird_Github'); from src.ingestion.mediastack_key_rotator import get_mediastack_key_rotator; rotator = get_mediastack_key_rotator(); print('Keys loaded:', len(rotator._keys)); print('Available:', rotator.is_available())"
```

**Result:** ✅ 4 keys loaded, `is_available()` returns `True`

## Impact

### Fixed
- ✅ MediaStack provider now works correctly when bot is started from any directory
- ✅ MediaStack fallback chain is fully operational
- ✅ No more "No valid API keys found!" warnings

### Backward Compatibility
- ✅ No changes to API
- ✅ All existing callsites continue to work
- ✅ No changes to configuration format

### Related Bugs
- This fix is separate from Bug #8 (MediaStack API keys configuration), which added the keys to the `.env` file
- Bug #16 was about loading the keys, Bug #8 was about configuring them

## Files Modified

1. [`src/main.py`](src/main.py:37-40) - Added explicit `.env` path calculation
2. [`DEBUG_TEST_REPORT_2026-02-10.md`](DEBUG_TEST_REPORT_2026-02-10.md:375-415) - Marked Bug #16 as resolved

## Verification

To verify the fix is working:

```bash
# Check that MediaStackKeyRotator initializes correctly
python3 -c "from src.ingestion.mediastack_key_rotator import get_mediastack_key_rotator; rotator = get_mediastack_key_rotator(); print('Status:', rotator.get_status())"

# Expected output:
# Status: {'total_keys': 4, 'available_keys': 4, 'current_key_index': 1, 'exhausted_keys': [], 'key_usage': {'key_1': 0, 'key_2': 0, 'key_3': 0, 'key_4': 0}, 'total_usage': 0, 'is_available': True, 'last_reset_month': 2}
```

## Lessons Learned

1. **Always specify absolute paths for configuration files:** When loading environment files, always calculate the path relative to the module location, not the current working directory
2. **Test from different directories:** When fixing configuration loading issues, test from different working directories to ensure robustness
3. **VPS compatibility:** On VPS systems, the working directory may not be what you expect, so always use absolute paths

## Future Improvements

Consider adding a similar fix to other entry points:
- [`src/launcher.py`](src/launcher.py) - Should also load `.env` explicitly
- [`run_news_radar.py`](run_news_radar.py) - Should also load `.env` explicitly
- [`run_telegram_monitor.py`](run_telegram_monitor.py) - Should also load `.env` explicitly

This would ensure consistent behavior across all entry points.
