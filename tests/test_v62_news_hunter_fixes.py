"""
Test suite for V6.2 news_hunter.py fixes.

Tests cover:
1. get_freshness_tag() - centralized freshness calculation with clock skew handling
2. UUID-based tracking in browser monitor (race condition fix)
3. DDG->Serper fallback in search_news_local (dead fallback fix)

These tests would FAIL on the buggy version and PASS with the patch.
"""
import pytest
import unittest.mock
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import uuid


class TestGetFreshnessTag:
    """Tests for the centralized get_freshness_tag() function."""
    
    def test_fresh_news_under_60_min(self):
        """News under 60 minutes should be tagged as FRESH."""
        from src.processing.news_hunter import get_freshness_tag
        
        assert get_freshness_tag(0) == "🔥 FRESH"
        assert get_freshness_tag(30) == "🔥 FRESH"
        assert get_freshness_tag(59) == "🔥 FRESH"
    
    def test_aging_news_60_to_360_min(self):
        """News between 60-360 minutes should be tagged as AGING."""
        from src.processing.news_hunter import get_freshness_tag
        
        assert get_freshness_tag(60) == "⏰ AGING"
        assert get_freshness_tag(180) == "⏰ AGING"
        assert get_freshness_tag(359) == "⏰ AGING"
    
    def test_stale_news_over_360_min(self):
        """News over 360 minutes should be tagged as STALE."""
        from src.processing.news_hunter import get_freshness_tag
        
        assert get_freshness_tag(360) == "📜 STALE"
        assert get_freshness_tag(720) == "📜 STALE"
        assert get_freshness_tag(1440) == "📜 STALE"
    
    def test_clock_skew_negative_minutes(self):
        """
        REGRESSION TEST: Negative minutes_old (clock skew) should return FRESH.
        
        BUG: Before V6.2, negative values were not handled and could cause
        incorrect categorization or crashes.
        """
        from src.processing.news_hunter import get_freshness_tag
        
        # Clock skew: news appears to be from the future
        assert get_freshness_tag(-5) == "🔥 FRESH"
        assert get_freshness_tag(-60) == "🔥 FRESH"
        assert get_freshness_tag(-1000) == "🔥 FRESH"


class TestBrowserMonitorUUID:
    """Tests for UUID-based tracking in browser monitor functions."""

    def test_register_discovery_adds_uuid(self):
        """
        REGRESSION TEST: Registered discoveries should have a UUID.

        BUG: Before V6.2, discoveries used id() for tracking which is unreliable
        across threads due to Python memory reuse.

        V7.0: Updated to use DiscoveryQueue API instead of legacy dict.
        """
        from src.processing.news_hunter import (
            register_browser_monitor_discovery,
            clear_browser_monitor_discoveries,
        )

        # Skip if browser monitor not available
        try:
            from src.services.browser_monitor import DiscoveredNews
        except ImportError:
            pytest.skip("Browser monitor not available")

        # Check if DiscoveryQueue is available (V7.0+)
        try:
            from src.utils.discovery_queue import get_discovery_queue

            use_queue = True
        except ImportError:
            use_queue = False

        # Clear existing discoveries
        clear_browser_monitor_discoveries()

        # Create a mock discovery
        mock_news = DiscoveredNews(
            url="https://example.com/news",
            title="Test News",
            snippet="Test snippet",
            category="INJURY",
            affected_team="Test Team",
            confidence=0.9,
            league_key="soccer_test_league",
            source_name="Test Source",
            discovered_at=datetime.now(timezone.utc),
        )

        # Register it
        register_browser_monitor_discovery(mock_news)

        if use_queue:
            # V7.0: Use DiscoveryQueue API
            queue = get_discovery_queue()
            # Pop for a fake match to verify registration worked
            discoveries = queue.pop_for_match(
                match_id="test_match",
                team_names=["Test Team"],
                league_key="soccer_test_league",
            )
            assert len(discoveries) == 1, "Discovery should be registered in queue"
            # DiscoveryQueue uses _uuid internally
            assert "_uuid" in discoveries[0], "Discovery should have UUID"
        else:
            # Legacy fallback (pre-V7.0)
            from src.processing.news_hunter import (
                _browser_monitor_discoveries,
                _browser_monitor_lock,
            )

            with _browser_monitor_lock:
                discoveries = _browser_monitor_discoveries.get("soccer_test_league", [])
                assert len(discoveries) == 1
                assert "_uuid" in discoveries[0]
                # UUID should be a valid UUID string
                uuid_str = discoveries[0]["_uuid"]
                assert uuid_str is not None
                # Validate it's a proper UUID format
                parsed_uuid = uuid.UUID(uuid_str)
                assert str(parsed_uuid) == uuid_str

        # Cleanup
        clear_browser_monitor_discoveries()

    def test_uuid_uniqueness_across_discoveries(self):
        """Each discovery should have a unique UUID.

        V7.0: Updated to use DiscoveryQueue API instead of legacy dict.
        """
        from src.processing.news_hunter import (
            register_browser_monitor_discovery,
            clear_browser_monitor_discoveries,
        )

        try:
            from src.services.browser_monitor import DiscoveredNews
        except ImportError:
            pytest.skip("Browser monitor not available")

        # Check if DiscoveryQueue is available (V7.0+)
        try:
            from src.utils.discovery_queue import get_discovery_queue

            use_queue = True
        except ImportError:
            use_queue = False

        clear_browser_monitor_discoveries()

        # Register multiple discoveries
        for i in range(5):
            mock_news = DiscoveredNews(
                url=f"https://example.com/news{i}",
                title=f"Test News {i}",
                snippet="Test snippet",
                category="INJURY",
                affected_team="Test Team",
                confidence=0.9,
                league_key="soccer_test_league",
                source_name="Test Source",
                discovered_at=datetime.now(timezone.utc),
            )
            register_browser_monitor_discovery(mock_news)

        if use_queue:
            # V7.0: Use DiscoveryQueue API
            queue = get_discovery_queue()
            discoveries = queue.pop_for_match(
                match_id="test_match",
                team_names=["Test Team"],
                league_key="soccer_test_league",
            )
            # All 5 should be registered
            assert len(discoveries) == 5, "All discoveries should be registered"
            uuids = [d["_uuid"] for d in discoveries]
            assert len(uuids) == len(set(uuids)), "UUIDs should be unique"
        else:
            # Legacy fallback
            from src.processing.news_hunter import (
                _browser_monitor_discoveries,
                _browser_monitor_lock,
            )

            with _browser_monitor_lock:
                discoveries = _browser_monitor_discoveries.get("soccer_test_league", [])
                uuids = [d["_uuid"] for d in discoveries]
                assert len(uuids) == len(set(uuids)), "UUIDs should be unique"

        clear_browser_monitor_discoveries()


class TestSearchNewsLocalFallback:
    """Tests for DDG->Serper fallback in search_news_local."""
    
    @patch('src.processing.news_hunter._get_search_backend')
    @patch('src.processing.news_hunter.get_search_provider')
    @patch('src.processing.news_hunter._is_serper_available')
    @patch('src.processing.news_hunter.requests.post')
    def test_ddg_failure_falls_through_to_serper(
        self, 
        mock_post, 
        mock_serper_available, 
        mock_get_provider,
        mock_get_backend
    ):
        """
        REGRESSION TEST: When DDG fails, should fall through to Serper.
        
        BUG: Before V6.2, setting backend='serper' after DDG failure did nothing
        because the code had already passed the Serper block.
        """
        from src.processing.news_hunter import search_news_local
        
        # Setup: DDG is primary but will fail
        mock_get_backend.return_value = 'ddg'
        
        # DDG provider raises exception
        mock_provider = MagicMock()
        mock_provider.search_local_news.side_effect = Exception("DDG failed")
        mock_get_provider.return_value = mock_provider
        
        # Serper is available as fallback
        mock_serper_available.return_value = True
        
        # Serper returns results
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'organic': [
                {
                    'title': 'Serper Result',
                    'snippet': 'From Serper',
                    'link': 'https://example.com',
                    'date': '1 hour ago',
                    'source': 'Example'
                }
            ]
        }
        mock_post.return_value = mock_response
        
        # Execute
        results = search_news_local(
            team_alias="Test Team",
            league_key="soccer_argentina_primera_division",
            match_id="test_match_123"
        )
        
        # Verify: Serper was called (fallback worked)
        assert mock_post.called, "Serper should be called when DDG fails"
        
        # Verify: We got results from Serper
        assert len(results) > 0, "Should have results from Serper fallback"
        assert results[0]['title'] == 'Serper Result'
    
    @patch('src.processing.news_hunter._get_search_backend')
    @patch('src.processing.news_hunter.get_search_provider')
    @patch('src.processing.news_hunter._is_serper_available')
    def test_ddg_failure_no_serper_returns_empty(
        self,
        mock_serper_available,
        mock_get_provider,
        mock_get_backend
    ):
        """When DDG fails and Serper unavailable, should return empty list."""
        from src.processing.news_hunter import search_news_local
        
        mock_get_backend.return_value = 'ddg'
        
        mock_provider = MagicMock()
        mock_provider.search_local_news.side_effect = Exception("DDG failed")
        mock_get_provider.return_value = mock_provider
        
        # Serper NOT available
        mock_serper_available.return_value = False
        
        results = search_news_local(
            team_alias="Test Team",
            league_key="soccer_argentina_primera_division",
            match_id="test_match_123"
        )
        
        # Should return empty, not crash
        assert results == []


class TestFreshnessTagConstants:
    """Tests for freshness tag constants consistency."""
    
    def test_constants_match_function_behavior(self):
        """Constants should match the function's threshold behavior."""
        from src.processing.news_hunter import (
            get_freshness_tag,
            FRESHNESS_FRESH_THRESHOLD_MIN,
            FRESHNESS_AGING_THRESHOLD_MIN
        )
        
        # At threshold boundaries
        assert get_freshness_tag(FRESHNESS_FRESH_THRESHOLD_MIN - 1) == "🔥 FRESH"
        assert get_freshness_tag(FRESHNESS_FRESH_THRESHOLD_MIN) == "⏰ AGING"
        
        assert get_freshness_tag(FRESHNESS_AGING_THRESHOLD_MIN - 1) == "⏰ AGING"
        assert get_freshness_tag(FRESHNESS_AGING_THRESHOLD_MIN) == "📜 STALE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================
# V6.3 TESTS: Enhanced Serper Error Logging
# ============================================

class TestV63SerperErrorLogging:
    """
    V6.3 Tests for enhanced Serper HTTP error logging.
    
    CRITICAL BUG: HTTP 400 errors from Serper were logged without
    query context, making it impossible to diagnose the cause.
    """
    
    def test_check_serper_response_accepts_query_param(self):
        """
        REGRESSION TEST: _check_serper_response should accept query parameter.
        
        Before V6.3: Function only accepted response parameter
        After V6.3: Function accepts optional query parameter for diagnostics
        """
        from src.processing.news_hunter import _check_serper_response
        import inspect
        
        sig = inspect.signature(_check_serper_response)
        params = list(sig.parameters.keys())
        
        assert 'response' in params, "Should have response parameter"
        assert 'query' in params, "Should have query parameter for diagnostics"
    
    def test_check_serper_response_query_is_optional(self):
        """Query parameter should be optional for backward compatibility."""
        from src.processing.news_hunter import _check_serper_response
        import inspect
        
        sig = inspect.signature(_check_serper_response)
        query_param = sig.parameters.get('query')
        
        assert query_param is not None, "query parameter should exist"
        assert query_param.default is None, "query should default to None"
    
    def test_check_serper_response_handles_400_with_query(self):
        """
        REGRESSION TEST: HTTP 400 should log query info for diagnostics.
        
        Before V6.3: Only logged "Serper API Error: 400"
        After V6.3: Logs query length and preview for debugging
        """
        from src.processing.news_hunter import _check_serper_response
        from unittest.mock import MagicMock
        import logging
        
        # Create mock 400 response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'message': 'Bad Request - invalid query'}
        
        test_query = '"Galatasaray" injury OR lineup site:twitter.com'
        
        # Capture log output
        with unittest.mock.patch.object(logging, 'warning') as mock_log:
            result = _check_serper_response(mock_response, query=test_query)
        
        assert result is False, "Should return False for 400"
        
        # Verify logging was called with query info
        mock_log.assert_called_once()
        log_message = mock_log.call_args[0][0]
        
        assert '400' in log_message, "Should mention HTTP 400"
        assert 'Query length' in log_message, "Should include query length"
        assert 'Query preview' in log_message, "Should include query preview"
    
    def test_check_serper_response_handles_400_without_query(self):
        """HTTP 400 should work even without query (backward compat)."""
        from src.processing.news_hunter import _check_serper_response
        from unittest.mock import MagicMock
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'message': 'Bad Request'}
        
        # Should not crash without query
        result = _check_serper_response(mock_response)
        assert result is False
    
    def test_check_serper_response_handles_429_rate_limit(self):
        """HTTP 429 should be logged as rate limit."""
        from src.processing.news_hunter import _check_serper_response
        from unittest.mock import MagicMock
        import logging
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {'message': 'Rate limit exceeded'}
        
        with unittest.mock.patch.object(logging, 'warning') as mock_log:
            result = _check_serper_response(mock_response)
        
        assert result is False
        mock_log.assert_called_once()
        assert '429' in mock_log.call_args[0][0]
        assert 'Rate Limit' in mock_log.call_args[0][0]
    
    def test_check_serper_response_truncates_long_query(self):
        """Long queries should be truncated in log preview."""
        from src.processing.news_hunter import _check_serper_response
        from unittest.mock import MagicMock
        import logging
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'message': 'Query too long'}
        
        # Very long query
        long_query = 'A' * 500
        
        with unittest.mock.patch.object(logging, 'warning') as mock_log:
            _check_serper_response(mock_response, query=long_query)
        
        log_message = mock_log.call_args[0][0]
        
        # Should truncate to 100 chars + '...'
        assert '...' in log_message, "Long query should be truncated"
        assert 'Query length: 500' in log_message, "Should show full length"
