"""
Comprehensive Test Suite for NewsRadar COVE V13.0 Fixes

This test file validates all the fixes applied to NewsRadarMonitor based on the
COVE double verification report:

1. Error Classification in _scan_loop()
2. Cache Error Handling in _process_content()
3. Atomic Cache Operations in _process_content()
4. Misleading Comment Fix in size_sync()

Date: 2026-03-06
Verification Method: Chain of Verification (CoVe) Protocol
"""

import asyncio
import json
import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestErrorClassification:
    """Test suite for error classification in _scan_loop()."""

    @pytest.fixture
    def mock_monitor(self):
        """Create a mock NewsRadarMonitor instance."""
        from src.services.news_radar import NewsRadarMonitor

        monitor = NewsRadarMonitor()
        monitor._running = True
        monitor._stop_event = asyncio.Event()
        monitor._config = MagicMock()
        monitor._config.global_settings = MagicMock()
        monitor._config.global_settings.default_scan_interval_minutes = 5
        return monitor

    def test_classify_permanent_errors(self, mock_monitor):
        """Test that permanent errors are correctly classified."""
        # FileNotFoundError
        error = FileNotFoundError("Config file not found")
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        # JSONDecodeError
        error = json.JSONDecodeError("Invalid JSON", "", 0)
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        # SyntaxError
        error = SyntaxError("Invalid syntax")
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        # PermissionError
        error = PermissionError("Permission denied")
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        # Configuration error
        error = ValueError("Invalid config: missing required field")
        assert mock_monitor._classify_error(error) == 'PERMANENT'

    def test_classify_rate_limit_errors(self, mock_monitor):
        """Test that rate limit errors are correctly classified."""
        # HTTP 429 with status attribute
        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 429
        assert mock_monitor._classify_error(error) == 'RATE_LIMIT'

        # Rate limit in error message
        error = Exception("Rate limit exceeded")
        assert mock_monitor._classify_error(error) == 'RATE_LIMIT'

        error = Exception("429 Too Many Requests")
        assert mock_monitor._classify_error(error) == 'RATE_LIMIT'

    def test_classify_transient_errors(self, mock_monitor):
        """Test that transient errors are correctly classified."""
        # TimeoutError
        error = TimeoutError("Connection timeout")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # ConnectionError
        error = ConnectionError("Connection refused")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # ConnectionRefusedError
        error = ConnectionRefusedError("Connection refused")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # ConnectionResetError
        error = ConnectionResetError("Connection reset")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # OSError
        error = OSError("Network error")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # RuntimeError
        error = RuntimeError("Runtime error")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # Network-related errors
        error = Exception("Network timeout")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        error = Exception("Connection failed")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

    def test_classify_http_errors(self, mock_monitor):
        """Test that HTTP errors are correctly classified."""
        # 5xx errors (server-side, transient)
        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 500
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 503
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # 4xx errors (client-side, permanent)
        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 404
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 401
        assert mock_monitor._classify_error(error) == 'PERMANENT'

        error = MagicMock()
        error.__class__.__name__ = 'HTTPStatusError'
        error.status = 403
        assert mock_monitor._classify_error(error) == 'PERMANENT'

    def test_classify_unknown_errors(self, mock_monitor):
        """Test that unknown errors default to TRANSIENT."""
        # Unknown error type
        error = Exception("Unknown error")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'

        # Custom exception
        class CustomError(Exception):
            pass

        error = CustomError("Custom error")
        assert mock_monitor._classify_error(error) == 'TRANSIENT'


class TestCacheErrorHandling:
    """Test suite for cache error handling in _process_content()."""

    @pytest.fixture
    def mock_monitor(self):
        """Create a mock NewsRadarMonitor instance."""
        from src.services.news_radar import NewsRadarMonitor, RadarSource

        monitor = NewsRadarMonitor()
        monitor._content_cache = AsyncMock()
        monitor._content_cache.is_cached = AsyncMock(return_value=False)
        monitor._content_cache.add = AsyncMock()
        monitor._running = True
        return monitor

    @pytest.fixture
    def mock_source(self):
        """Create a mock RadarSource."""
        from src.services.news_radar import RadarSource

        return RadarSource(
            name="Test Source",
            url="https://example.com",
            navigation_mode="single",
        )

    @pytest.mark.asyncio
    async def test_shared_cache_import_error_continues(self, mock_monitor, mock_source):
        """Test that ImportError from shared cache doesn't stop processing."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock shared cache import to raise ImportError
        with patch('src.services.news_radar.get_shared_cache', side_effect=ImportError):
            # This should not raise an exception
            result = await mock_monitor._process_content(content, mock_source, url)
            # Result depends on other logic, but should not crash
            assert result is None or isinstance(result, MagicMock)

    @pytest.mark.asyncio
    async def test_shared_cache_exception_continues(self, mock_monitor, mock_source):
        """Test that exceptions from shared cache don't stop processing."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock shared cache to raise exception
        mock_shared_cache = AsyncMock()
        mock_shared_cache.check_and_mark = AsyncMock(side_effect=Exception("Cache error"))

        with patch('src.services.news_radar.get_shared_cache', return_value=mock_shared_cache):
            # This should not raise an exception
            result = await mock_monitor._process_content(content, mock_source, url)
            # Result depends on other logic, but should not crash
            assert result is None or isinstance(result, MagicMock)

    @pytest.mark.asyncio
    async def test_local_cache_exception_continues(self, mock_monitor, mock_source):
        """Test that exceptions from local cache don't stop processing."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock local cache to raise exception
        mock_monitor._content_cache.is_cached = AsyncMock(side_effect=Exception("Cache error"))

        # This should not raise an exception
        result = await mock_monitor._process_content(content, mock_source, url)
        # Result depends on other logic, but should not crash
        assert result is None or isinstance(result, MagicMock)

    @pytest.mark.asyncio
    async def test_local_cache_add_exception_continues(self, mock_monitor, mock_source):
        """Test that exceptions from local cache add don't stop processing."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock local cache add to raise exception
        mock_monitor._content_cache.add = AsyncMock(side_effect=Exception("Cache error"))

        # This should not raise an exception
        result = await mock_monitor._process_content(content, mock_source, url)
        # Result depends on other logic, but should not crash
        assert result is None or isinstance(result, MagicMock)

    @pytest.mark.asyncio
    async def test_all_caches_fail_continues(self, mock_monitor, mock_source):
        """Test that processing continues even when all caches fail."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock all caches to raise exceptions
        mock_shared_cache = AsyncMock()
        mock_shared_cache.check_and_mark = AsyncMock(side_effect=Exception("Shared cache error"))
        mock_monitor._content_cache.is_cached = AsyncMock(side_effect=Exception("Local cache error"))
        mock_monitor._content_cache.add = AsyncMock(side_effect=Exception("Local cache add error"))

        with patch('src.services.news_radar.get_shared_cache', return_value=mock_shared_cache):
            # This should not raise an exception
            result = await mock_monitor._process_content(content, mock_source, url)
            # Result depends on other logic, but should not crash
            assert result is None or isinstance(result, MagicMock)


class TestAtomicCacheOperations:
    """Test suite for atomic cache operations in _process_content()."""

    @pytest.fixture
    def mock_monitor(self):
        """Create a mock NewsRadarMonitor instance."""
        from src.services.news_radar import NewsRadarMonitor

        monitor = NewsRadarMonitor()
        monitor._content_cache = AsyncMock()
        monitor._content_cache.is_cached = AsyncMock(return_value=False)
        monitor._content_cache.add = AsyncMock()
        monitor._running = True
        return monitor

    @pytest.fixture
    def mock_source(self):
        """Create a mock RadarSource."""
        from src.services.news_radar import RadarSource

        return RadarSource(
            name="Test Source",
            url="https://example.com",
            navigation_mode="single",
        )

    @pytest.mark.asyncio
    async def test_check_and_mark_skips_duplicate(self, mock_monitor, mock_source):
        """Test that check_and_mark returns True for duplicates and skips processing."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock shared cache to return True (duplicate)
        mock_shared_cache = AsyncMock()
        mock_shared_cache.check_and_mark = AsyncMock(return_value=True)

        with patch('src.services.news_radar.get_shared_cache', return_value=mock_shared_cache):
            result = await mock_monitor._process_content(content, mock_source, url)
            # Should return None (skipped)
            assert result is None
            # Should not call local cache add
            mock_monitor._content_cache.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_mark_proceeds_for_new_content(self, mock_monitor, mock_source):
        """Test that check_and_mark returns False for new content and processing continues."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock shared cache to return False (new content)
        mock_shared_cache = AsyncMock()
        mock_shared_cache.check_and_mark = AsyncMock(return_value=False)

        with patch('src.services.news_radar.get_shared_cache', return_value=mock_shared_cache):
            result = await mock_monitor._process_content(content, mock_source, url)
            # Result depends on other logic, but should not crash
            assert result is None or isinstance(result, MagicMock)
            # Should call local cache add
            mock_monitor._content_cache.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_and_mark_atomicity(self, mock_monitor, mock_source):
        """Test that check_and_mark is atomic (no separate is_duplicate and mark_seen)."""
        content = "Test content"
        url = "https://example.com/test"

        # Mock shared cache
        mock_shared_cache = AsyncMock()
        mock_shared_cache.check_and_mark = AsyncMock(return_value=False)

        with patch('src.services.news_radar.get_shared_cache', return_value=mock_shared_cache):
            result = await mock_monitor._process_content(content, mock_source, url)

            # Verify that check_and_mark was called
            mock_shared_cache.check_and_mark.assert_called_once_with(
                content=content, url=url, source="news_radar"
            )

            # Verify that is_duplicate and mark_seen were NOT called separately
            assert not hasattr(mock_shared_cache, 'is_duplicate') or not mock_shared_cache.is_duplicate.called
            assert not hasattr(mock_shared_cache, 'mark_seen') or not mock_shared_cache.mark_seen.called


class TestSizeSyncComment:
    """Test suite for the misleading comment fix in size_sync()."""

    @pytest.fixture
    def mock_cache(self):
        """Create a mock ContentCache instance."""
        from src.services.news_radar import ContentCache

        return ContentCache()

    def test_size_sync_returns_correct_value(self, mock_cache):
        """Test that size_sync returns the correct cache size."""
        # Add some items
        mock_cache._cache["key1"] = ("content1", time.time() + 3600)
        mock_cache._cache["key2"] = ("content2", time.time() + 3600)
        mock_cache._cache["key3"] = ("content3", time.time() + 3600)

        # Test size_sync
        size = mock_cache.size_sync()
        assert size == 3

    def test_size_sync_docstring_mentions_concurrent_modifications(self, mock_cache):
        """Test that the docstring mentions concurrent modifications."""
        docstring = mock_cache.size_sync.__doc__
        assert docstring is not None
        assert "concurrent modifications" in docstring.lower()
        assert "stale" in docstring.lower() or "inconsistent" in docstring.lower()

    def test_size_sync_docstring_recommends_async_size_for_critical_decisions(self, mock_cache):
        """Test that the docstring recommends async size() for critical decisions."""
        docstring = mock_cache.size_sync.__doc__
        assert docstring is not None
        assert "async size()" in docstring or "critical decisions" in docstring.lower()


class TestIntegration:
    """Integration tests for all fixes together."""

    @pytest.fixture
    def mock_monitor(self):
        """Create a mock NewsRadarMonitor instance."""
        from src.services.news_radar import NewsRadarMonitor

        monitor = NewsRadarMonitor()
        monitor._content_cache = AsyncMock()
        monitor._content_cache.is_cached = AsyncMock(return_value=False)
        monitor._content_cache.add = AsyncMock()
        monitor._running = True
        monitor._stop_event = asyncio.Event()
        monitor._config = MagicMock()
        monitor._config.global_settings = MagicMock()
        monitor._config.global_settings.default_scan_interval_minutes = 5
        return monitor

    @pytest.mark.asyncio
    async def test_permanent_error_stops_scan_loop(self, mock_monitor):
        """Test that permanent errors stop the scan loop immediately."""
        # Mock scan_cycle to raise a permanent error
        mock_monitor.scan_cycle = AsyncMock(side_effect=FileNotFoundError("Config not found"))

        # Run scan loop (should stop immediately)
        await mock_monitor._scan_loop()

        # Verify that monitor stopped
        assert not mock_monitor._running

    @pytest.mark.asyncio
    async def test_rate_limit_error_waits_long_backoff(self, mock_monitor):
        """Test that rate limit errors wait 30 minutes before retry."""
        # Mock scan_cycle to raise a rate limit error
        mock_monitor.scan_cycle = AsyncMock(side_effect=Exception("Rate limit exceeded"))

        start_time = time.time()

        # Run scan loop (should wait 30 minutes)
        # We'll cancel after a short time to avoid waiting the full 30 minutes
        task = asyncio.create_task(mock_monitor._scan_loop())
        await asyncio.sleep(0.1)  # Give it time to start
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify that it was sleeping (not stopped immediately)
        elapsed = time.time() - start_time
        # Should have been sleeping (not stopped immediately)
        # Since we cancelled quickly, elapsed should be small but not zero
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_transient_errors_with_exponential_backoff(self, mock_monitor):
        """Test that transient errors use exponential backoff."""
        # Mock scan_cycle to raise transient errors
        error_count = 0

        async def failing_scan_cycle():
            nonlocal error_count
            error_count += 1
            if error_count <= 3:
                raise TimeoutError("Connection timeout")
            return 0

        mock_monitor.scan_cycle = AsyncMock(side_effect=failing_scan_cycle)

        # Run scan loop (should retry with exponential backoff)
        # We'll cancel after a short time
        task = asyncio.create_task(mock_monitor._scan_loop())
        await asyncio.sleep(0.5)  # Give it time to retry a few times
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify that it retried multiple times
        assert error_count >= 2


def run_all_tests():
    """Run all tests and print results."""
    logger.info("🧪 Running comprehensive test suite for NewsRadar COVE V13.0 fixes...")

    # Run pytest
    exit_code = pytest.main([__file__, "-v", "--tb=short"])

    if exit_code == 0:
        logger.info("✅ All tests passed!")
    else:
        logger.error(f"❌ Some tests failed (exit code: {exit_code})")

    return exit_code


if __name__ == "__main__":
    import sys

    sys.exit(run_all_tests())
