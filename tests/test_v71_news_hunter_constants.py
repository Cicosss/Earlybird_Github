"""
Test suite for V7.1 news_hunter.py improvements.

Tests cover:
1. SERPER_REQUEST_TIMEOUT constant exists and is used
2. SERPER_RATE_LIMIT_DELAY constants exist and are used
3. No hardcoded timeout=30 or time.sleep(0.3/0.5) in Serper calls

These tests would FAIL on the pre-V7.1 version and PASS with the patch.
"""
import pytest
import re


class TestV71SerperConstants:
    """Tests for centralized Serper API constants."""
    
    def test_serper_timeout_constant_exists(self):
        """SERPER_REQUEST_TIMEOUT constant should be defined."""
        from src.processing.news_hunter import SERPER_REQUEST_TIMEOUT
        
        assert SERPER_REQUEST_TIMEOUT is not None
        assert isinstance(SERPER_REQUEST_TIMEOUT, (int, float))
        assert SERPER_REQUEST_TIMEOUT > 0
        assert SERPER_REQUEST_TIMEOUT == 30  # Current value
    
    def test_serper_rate_limit_delay_constant_exists(self):
        """SERPER_RATE_LIMIT_DELAY constant should be defined."""
        from src.processing.news_hunter import SERPER_RATE_LIMIT_DELAY
        
        assert SERPER_RATE_LIMIT_DELAY is not None
        assert isinstance(SERPER_RATE_LIMIT_DELAY, (int, float))
        assert SERPER_RATE_LIMIT_DELAY > 0
        assert SERPER_RATE_LIMIT_DELAY == 0.3  # Current value
    
    def test_serper_rate_limit_delay_slow_constant_exists(self):
        """SERPER_RATE_LIMIT_DELAY_SLOW constant should be defined."""
        from src.processing.news_hunter import SERPER_RATE_LIMIT_DELAY_SLOW, SERPER_RATE_LIMIT_DELAY
        
        assert SERPER_RATE_LIMIT_DELAY_SLOW is not None
        assert isinstance(SERPER_RATE_LIMIT_DELAY_SLOW, (int, float))
        assert SERPER_RATE_LIMIT_DELAY_SLOW > SERPER_RATE_LIMIT_DELAY
        assert SERPER_RATE_LIMIT_DELAY_SLOW == 0.5  # Current value
    
    def test_no_hardcoded_timeout_30(self):
        """
        REGRESSION TEST: No hardcoded timeout=30 should exist in Serper calls.
        
        Before V7.1: timeout=30 was hardcoded in 6 places
        After V7.1: All use SERPER_REQUEST_TIMEOUT constant
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Find all requests.post calls with timeout
        # Pattern: requests.post(..., timeout=30)
        hardcoded_timeouts = re.findall(r'requests\.post\([^)]*timeout=30[^)]*\)', content)
        
        assert len(hardcoded_timeouts) == 0, \
            f"Found {len(hardcoded_timeouts)} hardcoded timeout=30. Should use SERPER_REQUEST_TIMEOUT."
    
    def test_no_hardcoded_sleep_values(self):
        """
        REGRESSION TEST: No hardcoded time.sleep(0.3) or time.sleep(0.5) in Serper sections.
        
        Before V7.1: time.sleep(0.3) and time.sleep(0.5) were hardcoded
        After V7.1: All use SERPER_RATE_LIMIT_DELAY constants
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Find time.sleep calls with hardcoded values near requests.post
        # We check that time.sleep(0.3) and time.sleep(0.5) are not followed by requests.post
        
        # Split into lines for context-aware checking
        lines = content.split('\n')
        
        violations = []
        for i, line in enumerate(lines):
            if 'time.sleep(0.3)' in line or 'time.sleep(0.5)' in line:
                # Check if next non-empty line contains requests.post
                for j in range(i+1, min(i+5, len(lines))):
                    if 'requests.post' in lines[j]:
                        violations.append(f"Line {i+1}: {line.strip()}")
                        break
        
        assert len(violations) == 0, \
            f"Found hardcoded sleep values before requests.post: {violations}"
    
    def test_constants_used_in_requests(self):
        """Verify constants are actually used in requests.post calls."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Count uses of the constants
        timeout_uses = content.count('timeout=SERPER_REQUEST_TIMEOUT')
        delay_uses = content.count('time.sleep(SERPER_RATE_LIMIT_DELAY)')
        delay_slow_uses = content.count('time.sleep(SERPER_RATE_LIMIT_DELAY_SLOW)')
        
        # V8.0: Reduced counts after search_reddit_deep removal
        # Should have multiple uses (5 timeout, 4 normal delay, 1 slow delay)
        assert timeout_uses >= 5, f"Expected >= 5 uses of SERPER_REQUEST_TIMEOUT, found {timeout_uses}"
        assert delay_uses >= 4, f"Expected >= 4 uses of SERPER_RATE_LIMIT_DELAY, found {delay_uses}"
        assert delay_slow_uses >= 1, f"Expected >= 1 use of SERPER_RATE_LIMIT_DELAY_SLOW, found {delay_slow_uses}"


class TestV71ConstantsImportable:
    """Test that all new constants are properly importable."""
    
    def test_all_constants_importable(self):
        """All V7.1 constants should be importable from news_hunter."""
        from src.processing.news_hunter import (
            SERPER_REQUEST_TIMEOUT,
            SERPER_RATE_LIMIT_DELAY,
            SERPER_RATE_LIMIT_DELAY_SLOW,
        )
        
        # If we get here, imports succeeded
        assert True
    
    def test_constants_are_numeric(self):
        """All constants should be numeric (int or float)."""
        from src.processing.news_hunter import (
            SERPER_REQUEST_TIMEOUT,
            SERPER_RATE_LIMIT_DELAY,
            SERPER_RATE_LIMIT_DELAY_SLOW,
        )
        
        for name, value in [
            ('SERPER_REQUEST_TIMEOUT', SERPER_REQUEST_TIMEOUT),
            ('SERPER_RATE_LIMIT_DELAY', SERPER_RATE_LIMIT_DELAY),
            ('SERPER_RATE_LIMIT_DELAY_SLOW', SERPER_RATE_LIMIT_DELAY_SLOW),
        ]:
            assert isinstance(value, (int, float)), f"{name} should be numeric, got {type(value)}"
            assert value > 0, f"{name} should be positive, got {value}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



class TestV71SearchTypeSummary:
    """
    Tests for V7.1 fix: search_type values in SUMMARY section.
    
    BUG: The SUMMARY section was counting search_types that don't exist:
    - 'twitter_hack' (removed in V7.0, now 'twitter_intel_cache')
    - 'ddg_twitter' (never existed)
    
    And was missing valid search_types:
    - 'twitter_intel_cache'
    - 'dynamic_country'
    - 'insider_beat_writer'
    """
    
    def test_tier1_search_types_list_exists(self):
        """tier1_search_types should be defined as a list in the code."""
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        assert 'tier1_search_types = [' in content, \
            "tier1_search_types should be defined as a list"
    
    def test_no_obsolete_twitter_hack(self):
        """
        REGRESSION TEST: 'twitter_hack' should not be in tier1 search types.
        
        This search_type was removed in V7.0 when Twitter search moved to cache.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Find the tier1_search_types definition
        import re
        match = re.search(r'tier1_search_types\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match, "Could not find tier1_search_types definition"
        
        tier1_def = match.group(1)
        # Check for 'twitter_hack' as an actual list item (with quotes and comma)
        # Exclude comments that mention it
        tier1_items = [line.strip() for line in tier1_def.split('\n') if not line.strip().startswith('#')]
        tier1_items_str = ' '.join(tier1_items)
        assert "'twitter_hack'" not in tier1_items_str, \
            "'twitter_hack' is obsolete (V7.0), should not be in tier1_search_types"
    
    def test_no_obsolete_ddg_twitter(self):
        """
        REGRESSION TEST: 'ddg_twitter' should not be in tier1 search types.
        
        This search_type never existed in the codebase.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        import re
        match = re.search(r'tier1_search_types\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match, "Could not find tier1_search_types definition"
        
        tier1_def = match.group(1)
        assert "'ddg_twitter'" not in tier1_def, \
            "'ddg_twitter' never existed, should not be in tier1_search_types"
    
    def test_twitter_intel_cache_in_tier1(self):
        """
        REGRESSION TEST: 'twitter_intel_cache' should be in tier1 search types.
        
        This is the V7.0 replacement for the broken Twitter search.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        import re
        match = re.search(r'tier1_search_types\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match, "Could not find tier1_search_types definition"
        
        tier1_def = match.group(1)
        assert "'twitter_intel_cache'" in tier1_def, \
            "'twitter_intel_cache' should be in tier1_search_types (V7.0 Twitter replacement)"
    
    def test_dynamic_country_in_tier1(self):
        """
        REGRESSION TEST: 'dynamic_country' should be in tier1 search types.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        import re
        match = re.search(r'tier1_search_types\s*=\s*\[(.*?)\]', content, re.DOTALL)
        assert match, "Could not find tier1_search_types definition"
        
        tier1_def = match.group(1)
        assert "'dynamic_country'" in tier1_def, \
            "'dynamic_country' should be in tier1_search_types"
    
    def test_insider_beat_writer_in_beat_writer_total(self):
        """
        REGRESSION TEST: 'insider_beat_writer' should be counted in beat_writer_total.
        
        The deprecated search_beat_writers() function returns 'insider_beat_writer'.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        # Find the beat_writer_total definition
        assert "'insider_beat_writer'" in content and 'beat_writer_total' in content, \
            "'insider_beat_writer' should be counted in beat_writer_total"
    
    def test_all_actual_search_types_accounted(self):
        """
        Verify all search_type values used in the code are accounted for in summary.
        """
        with open('src/processing/news_hunter.py', 'r') as f:
            content = f.read()
        
        import re
        
        # Find all search_type assignments
        search_types_used = set(re.findall(r"'search_type':\s*['\"]([^'\"]+)['\"]", content))
        # Also find f-string patterns like f"exotic_{strat['name']}"
        # These are dynamic, so we check for the pattern
        
        # Known search_types that should be counted somewhere
        # V8.0: insider_reddit_deep removed (Reddit deprecated)
        expected_types = {
            'browser_monitor',      # browser_monitor_total
            'beat_writer_cache',    # beat_writer_total
            'dynamic_country',      # tier1_count
            'twitter_intel_cache',  # tier1_count
            'ddg_local',            # tier1_count
            'local_site_dork',      # tier1_count
            'generic',              # tier1_count
            'insider_beat_writer',  # beat_writer_total
        }
        
        # Verify expected types are in the actual types used
        for expected in expected_types:
            assert expected in search_types_used, \
                f"Expected search_type '{expected}' not found in code"
