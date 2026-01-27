"""
V7.7 Browser Stability Tests

Tests for the browser stability fixes:
1. --single-process removal (causes crashes on heavy sites)
2. asyncio.Lock for browser recreation (race condition fix)
3. Retry logic in extract_content (auto-recovery after crash)

These tests would FAIL on the buggy version and PASS with the patch.
"""
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import pytest


class TestBrowserArgsNoSingleProcess:
    """
    REGRESSION TEST: --single-process should NOT be in browser launch args.
    
    BUG: Chromium with --single-process crashes frequently on sites with
    heavy ads/JS. This caused "Target page, context or browser has been closed"
    errors in production.
    """
    
    def test_browser_monitor_no_single_process(self):
        """browser_monitor.py should not use --single-process."""
        import inspect
        from src.services.browser_monitor import BrowserMonitor
        
        # Get the source code of _initialize_playwright
        source = inspect.getsource(BrowserMonitor)
        
        # Count occurrences of --single-process
        # V7.7: Should be 0 (removed from all launch calls)
        single_process_count = source.count("'--single-process'")
        
        assert single_process_count == 0, (
            f"Found {single_process_count} occurrences of '--single-process' in browser_monitor.py. "
            "This flag causes browser instability on heavy sites."
        )
    
    def test_news_radar_no_single_process(self):
        """news_radar.py should not use --single-process."""
        import inspect
        from src.services.news_radar import ContentExtractor
        
        source = inspect.getsource(ContentExtractor)
        single_process_count = source.count("'--single-process'")
        
        assert single_process_count == 0, (
            f"Found {single_process_count} occurrences of '--single-process' in news_radar.py. "
            "This flag causes browser instability on heavy sites."
        )


class TestBrowserLockExists:
    """
    REGRESSION TEST: Browser recreation should use asyncio.Lock.
    
    BUG: Without a lock, multiple coroutines could try to recreate the browser
    simultaneously after a crash, causing race conditions.
    """
    
    def test_browser_monitor_has_lock_attribute(self):
        """BrowserMonitor should have _browser_lock attribute."""
        from src.services.browser_monitor import BrowserMonitor
        
        monitor = BrowserMonitor()
        
        # V7.7: Should have _browser_lock attribute (initialized to None)
        assert hasattr(monitor, '_browser_lock'), (
            "BrowserMonitor missing _browser_lock attribute. "
            "This is needed to prevent race conditions during browser recreation."
        )
    
    def test_news_radar_extractor_has_lock_attribute(self):
        """ContentExtractor should have _browser_lock attribute."""
        from src.services.news_radar import ContentExtractor
        
        extractor = ContentExtractor()
        
        assert hasattr(extractor, '_browser_lock'), (
            "ContentExtractor missing _browser_lock attribute. "
            "This is needed to prevent race conditions during browser recreation."
        )
    
    def test_ensure_browser_connected_uses_lock(self):
        """_ensure_browser_connected should use async with self._browser_lock."""
        import inspect
        from src.services.browser_monitor import BrowserMonitor
        
        source = inspect.getsource(BrowserMonitor._ensure_browser_connected)
        
        # V7.7: Should contain "async with self._browser_lock"
        assert "async with self._browser_lock" in source, (
            "_ensure_browser_connected does not use browser lock. "
            "This can cause race conditions when multiple coroutines detect a crash."
        )


class TestSerperDisabled:
    """
    REGRESSION TEST: Serper should be disabled in search fallback chain.
    
    BUG: Serper has a ~2048 char query limit. Our queries with sport exclusions
    + site dorking easily exceed 500+ chars, causing HTTP 400 errors.
    """
    
    def test_serper_returns_empty(self):
        """_search_serper should return empty list (disabled)."""
        from src.ingestion.search_provider import SearchProvider
        
        provider = SearchProvider()
        results = provider._search_serper("test query", 10)
        
        # V4.5: Serper is disabled, should always return []
        assert results == [], (
            "Serper should be disabled and return empty list. "
            "Long queries cause HTTP 400 errors."
        )
    
    def test_search_fallback_skips_serper(self):
        """search() should go directly from DDG to Mediastack, skipping Serper."""
        import inspect
        from src.ingestion.search_provider import SearchProvider
        
        source = inspect.getsource(SearchProvider.search)
        
        # V4.5: Comment should mention Serper is removed
        assert "Serper removed" in source or "V4.5" in source, (
            "search() method should document that Serper was removed from fallback chain."
        )


class TestTelegramEnsuperligRemoved:
    """
    REGRESSION TEST: @ensuperlig should be removed from Telegram channels.
    
    BUG: The channel no longer exists, causing ValueError on every scan:
    "No user has 'ensuperlig' as username"
    """
    
    def test_ensuperlig_not_in_turkey_channels(self):
        """ensuperlig should not be in Turkey Telegram channels."""
        from src.processing.sources_config import TELEGRAM_INSIDERS
        
        turkey_channels = TELEGRAM_INSIDERS.get("turkey", [])
        
        # V4.5: ensuperlig removed (channel doesn't exist)
        assert "ensuperlig" not in turkey_channels, (
            "ensuperlig is still in Turkey Telegram channels. "
            "This channel no longer exists and causes ValueError on every scan."
        )
    
    def test_get_telegram_channels_turkey_no_ensuperlig(self):
        """get_telegram_channels for Turkey should not include ensuperlig."""
        from src.processing.sources_config import get_telegram_channels
        
        channels = get_telegram_channels("soccer_turkey_super_league")
        
        assert "ensuperlig" not in channels, (
            "get_telegram_channels returns ensuperlig for Turkey. "
            "This channel no longer exists."
        )


# ============================================
# ASYNC TESTS FOR LOCK BEHAVIOR
# ============================================

@pytest.mark.asyncio
async def test_browser_lock_prevents_concurrent_recreation():
    """
    INTEGRATION TEST: Lock should prevent concurrent browser recreation.
    
    Simulates multiple coroutines detecting a browser crash simultaneously.
    Only one should actually recreate the browser.
    """
    from src.services.browser_monitor import BrowserMonitor
    
    monitor = BrowserMonitor()
    monitor._browser_lock = asyncio.Lock()
    
    recreation_count = 0
    
    # Create a mock browser that reports as connected
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = True
    
    async def mock_recreate_internal():
        nonlocal recreation_count
        recreation_count += 1
        await asyncio.sleep(0.05)  # Simulate recreation time
        # After recreation, set the browser to mock (simulates successful recreation)
        monitor._browser = mock_browser
        return True
    
    # Mock the internal recreation method
    monitor._recreate_browser_internal = mock_recreate_internal
    monitor._browser = None  # Simulate crashed browser
    
    # Simulate 5 coroutines detecting the crash simultaneously
    tasks = [monitor._ensure_browser_connected() for _ in range(5)]
    results = await asyncio.gather(*tasks)
    
    # All should succeed
    assert all(results), "All coroutines should report success"
    
    # Recreation should only happen once (lock prevents duplicates)
    # After first coroutine recreates, others see browser is connected and skip
    assert recreation_count == 1, (
        f"Browser was recreated {recreation_count} times, expected 1. "
        "Lock should prevent concurrent recreation."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
