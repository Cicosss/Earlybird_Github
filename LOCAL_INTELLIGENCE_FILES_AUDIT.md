# Local Intelligence Files Audit Report
**Generated**: 2026-02-12T22:04:00Z
**Purpose**: Identify local files with hardcoded intelligence lists for decommissioning

## Files Identified

### 1. `src/processing/sources_config.py` (26328 bytes)
**Contains**:
- `BEAT_WRITERS_DB` - Beat writers by league (lines 65-107)
- `LOCAL_SOURCES_MAPPING` - Local news sources by league (lines 114-173)
- `NATIVE_KEYWORDS` - Native language keywords (lines 176-190)
- `INSIDER_HANDLES` - Twitter/X handles by league (lines 203-258)
- `TELEGRAM_INSIDERS` - Telegram channels by league (lines 266-307)
- `SOURCE_TIERS_DB` - Source credibility tiers (lines 582-635)

**Functions that access these data structures**:
- `get_sources_for_league()` - accesses `LOCAL_SOURCES_MAPPING`
- `get_keywords_for_league()` - accesses `NATIVE_KEYWORDS`
- `get_insider_handles()` - accesses `INSIDER_HANDLES`
- `get_beat_writers()` - accesses `BEAT_WRITERS_DB`
- `get_all_telegram_channels()` - accesses `TELEGRAM_INSIDERS`
- `get_telegram_channels()` - accesses `TELEGRAM_INSIDERS`
- `get_source_tier()` - accesses `SOURCE_TIERS_DB`
- `get_source_weight()` - accesses `SOURCE_TIERS_DB`

**Imported by**:
- `src/processing/news_hunter.py` - uses `get_sources_for_league()`, `get_keywords_for_league()`, `get_country_from_league()`, `get_insider_handles()`, `get_beat_writers()`, `BeatWriter`
- `src/processing/telegram_listener.py` - uses `get_all_telegram_channels()`, `TELEGRAM_INSIDERS`
- `src/analysis/news_scorer.py` - uses `get_source_tier()`, `SourceTier`, `DEFAULT_SOURCE_TIER`
- `src/analysis/verifier_integration.py` - uses `get_source_tier()`, `get_source_weight()`

**Status**: ⚠️ PARTIALLY REFACTORED - `news_hunter.py` has hybrid implementation for social_sources, but still uses local functions for other data

---

### 2. `config/twitter_intel_accounts.py` (30717 bytes, 903 lines)
**Contains**:
- `TWITTER_INTEL_ELITE_7` - Twitter intel accounts for Elite 7 leagues (lines 75-~400)
- `TWITTER_INTEL_TIER_2` - Twitter intel accounts for Tier 2 leagues (lines ~400-~500)
- `TWITTER_INTEL_GLOBAL` - Global Twitter intel accounts (lines ~500-~600)

**Functions that access these data structures**:
- `get_twitter_intel_accounts()` - accesses all three dictionaries
- `get_all_twitter_handles()` - accesses all three dictionaries
- `get_handles_by_tier()` - accesses specific tier dictionary
- `find_account_by_handle()` - searches all three dictionaries

**Imported by**:
- `src/services/twitter_intel_cache.py` - uses `get_twitter_intel_accounts()`, `get_all_twitter_handles()`, `get_handles_by_tier()`, `LeagueTier`, `TwitterIntelAccount`, `build_gemini_twitter_extraction_prompt`

**Status**: ❌ NOT REFACTORED - Still uses local configuration

---

## Supabase Data Status

### ✅ Available in Supabase
- `news_sources` table: **140 records** (domains for site-dorking)
- `social_sources` table: **38 records** (Twitter/X handles for Nitter monitoring)
- Mirror file: **Up to date** (timestamp: 2026-02-12T21:49:06)

### ❌ NOT Available in Supabase
- `BEAT_WRITERS_DB` - Beat writers data structure
- `NATIVE_KEYWORDS` - Native language keywords for searches
- `TELEGRAM_INSIDERS` - Telegram channels (should remain in SQLite per Hybrid Model)
- `SOURCE_TIERS_DB` - Source credibility scoring system

---

## Refactoring Status Summary

| Component | Target Data | Supabase Available? | Refactoring Status |
|-----------|--------------|---------------------|-------------------|
| `news_hunter.py` | `news_sources`, `social_sources` | ✅ Yes | ⚠️ Partial - Hybrid for social_sources, local for news_sources |
| `telegram_listener.py` | `TELEGRAM_INSIDERS` | ❌ No (SQLite) | ❌ Not refactored (should remain local) |
| `news_scorer.py` | `SOURCE_TIERS_DB` | ❌ No | ❌ Not refactored |
| `verifier_integration.py` | `SOURCE_TIERS_DB` | ❌ No | ❌ Not refactored |
| `twitter_intel_cache.py` | Twitter intel accounts | ❌ No | ❌ Not refactored |

---

## Recommendations

### Immediate Actions Required:

1. **DO NOT comment out lists yet** - Code still depends on them
2. **Create Supabase tables for missing data**:
   - Consider if `SOURCE_TIERS_DB` should be in Supabase or remain local
   - Consider if `NATIVE_KEYWORDS` should be in Supabase or remain local
3. **Refactor code to use Supabase for available data**:
   - `news_hunter.py`: Use Supabase for `news_sources` (not just `social_sources`)
   - `twitter_intel_cache.py`: Use Supabase `social_sources` instead of local `TWITTER_INTEL_*` dictionaries
4. **Keep local data that should remain local**:
   - `TELEGRAM_INSIDERS` - Telegram channels are operational data, should remain in SQLite
   - `SOURCE_TIERS_DB` - This is a scoring system, not intelligence data
   - `NATIVE_KEYWORDS` - This is configuration for search queries, not intelligence data

### Files to Decommission (after refactoring):

1. `src/processing/sources_config.py` - Comment out lists that are migrated to Supabase
2. `config/twitter_intel_accounts.py` - Comment out lists that are migrated to Supabase

### Files to Keep (with local data):

1. `src/processing/sources_config.py` - Keep `TELEGRAM_INSIDERS`, `SOURCE_TIERS_DB`, `NATIVE_KEYWORDS` if not migrated to Supabase

---

## Next Steps

1. ✅ **COMPLETED**: Identify local files with hardcoded intelligence lists
2. ⏳ **PENDING**: Decide which data should be migrated to Supabase
3. ⏳ **PENDING**: Create Supabase tables for missing data (if needed)
4. ⏳ **PENDING**: Refactor code to use Supabase for migrated data
5. ⏳ **PENDING**: Comment out migrated lists with deprecation warnings
6. ⏳ **PENDING**: Run tests to ensure no regressions
7. ⏳ **PENDING**: Update checklist to mark task as completed
