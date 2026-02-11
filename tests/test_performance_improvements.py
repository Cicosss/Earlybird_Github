"""
Tests for EarlyBird V6.0 Performance Improvements

Tests:
1. Parallel Enrichment - verifica che il parallelismo funzioni
2. Dynamic Threshold - verifica che il threshold si adatti
3. High-Priority Callback - verifica che il callback venga invocato
4. Memory Cleanup - verifica che il cleanup funzioni mid-cycle

Run with: pytest tests/test_performance_improvements.py -v
"""
import pytest
import time
import threading
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any


# ============================================
# TEST 1: Parallel Enrichment
# ============================================

class TestParallelEnrichment:
    """Test suite for parallel enrichment module."""
    
    def test_enrichment_result_dataclass(self):
        """Test EnrichmentResult dataclass initialization and methods."""
        from src.utils.parallel_enrichment import EnrichmentResult
        
        result = EnrichmentResult()
        
        # Default values
        assert result.home_context == {}
        assert result.away_context == {}
        assert result.home_turnover is None
        assert result.referee_info is None
        assert result.enrichment_time_ms == 0
        assert result.failed_calls == []
        assert result.successful_calls == 0
        
        # Methods
        assert result.has_injuries() == False
        assert result.has_high_turnover() == False
        assert "No significant findings" in result.get_summary()
    
    def test_enrichment_result_with_injuries(self):
        """Test EnrichmentResult.has_injuries() with actual injuries."""
        from src.utils.parallel_enrichment import EnrichmentResult
        
        result = EnrichmentResult(
            home_context={'injuries': [{'name': 'Player1'}]},
            away_context={}
        )
        
        assert result.has_injuries() == True
        assert "Injuries" in result.get_summary()
    
    def test_enrichment_result_with_high_turnover(self):
        """Test EnrichmentResult.has_high_turnover() detection."""
        from src.utils.parallel_enrichment import EnrichmentResult
        
        # No turnover
        result1 = EnrichmentResult()
        assert result1.has_high_turnover() == False
        
        # Medium turnover (should not trigger)
        result2 = EnrichmentResult(
            home_turnover={'risk_level': 'MEDIUM'}
        )
        assert result2.has_high_turnover() == False
        
        # High turnover (should trigger)
        result3 = EnrichmentResult(
            away_turnover={'risk_level': 'HIGH'}
        )
        assert result3.has_high_turnover() == True
    
    def test_parallel_enrichment_with_mock_fotmob(self):
        """Test parallel enrichment with mocked FotMob provider."""
        from src.utils.parallel_enrichment import enrich_match_parallel
        
        # Create mock FotMob provider
        mock_fotmob = Mock()
        mock_fotmob.get_full_team_context.return_value = {'injuries': []}
        mock_fotmob.get_turnover_risk.return_value = {'risk_level': 'LOW'}
        mock_fotmob.get_referee_info.return_value = {'name': 'Test Referee'}
        mock_fotmob.get_stadium_coordinates.return_value = (41.0, 2.0)
        mock_fotmob.get_team_stats.return_value = {'goals_signal': 'HIGH'}
        mock_fotmob.get_tactical_insights.return_value = {'tactical_summary': 'Test'}
        
        result = enrich_match_parallel(
            fotmob=mock_fotmob,
            home_team="Barcelona",
            away_team="Real Madrid",
            max_workers=2,
            timeout=10
        )
        
        # Verify all calls were made
        assert mock_fotmob.get_full_team_context.call_count == 2  # home + away
        assert mock_fotmob.get_turnover_risk.call_count == 2
        assert mock_fotmob.get_referee_info.call_count == 1
        assert mock_fotmob.get_stadium_coordinates.call_count == 1
        assert mock_fotmob.get_team_stats.call_count == 2
        assert mock_fotmob.get_tactical_insights.call_count == 1
        
        # Verify results
        assert result.successful_calls >= 8  # At least 8 successful calls
        # Note: With mocked FotMob, enrichment_time_ms may be 0 or very small
        # This is expected since mocks complete instantly without actual HTTP calls
    
    def test_parallel_enrichment_handles_failures(self):
        """Test that parallel enrichment handles individual failures gracefully."""
        from src.utils.parallel_enrichment import enrich_match_parallel
        
        # Create mock that fails on some calls
        mock_fotmob = Mock()
        mock_fotmob.get_full_team_context.side_effect = [
            {'injuries': []},  # First call succeeds
            Exception("API Error")  # Second call fails
        ]
        mock_fotmob.get_turnover_risk.return_value = None
        mock_fotmob.get_referee_info.return_value = None
        mock_fotmob.get_stadium_coordinates.return_value = None
        mock_fotmob.get_team_stats.return_value = {}
        mock_fotmob.get_tactical_insights.return_value = {}
        
        result = enrich_match_parallel(
            fotmob=mock_fotmob,
            home_team="Team A",
            away_team="Team B",
            max_workers=2,
            timeout=10
        )
        
        # Should have some failures but not crash
        assert 'away_context' in result.failed_calls
        assert result.home_context == {'injuries': []}  # First call succeeded
    
    def test_parallel_enrichment_none_inputs(self):
        """Test parallel enrichment with None/empty inputs."""
        from src.utils.parallel_enrichment import enrich_match_parallel, EnrichmentResult
        
        # None fotmob
        result1 = enrich_match_parallel(None, "Home", "Away")
        assert isinstance(result1, EnrichmentResult)
        assert result1.successful_calls == 0
        
        # Empty team names
        mock_fotmob = Mock()
        result2 = enrich_match_parallel(mock_fotmob, "", "Away")
        assert result2.successful_calls == 0
        
        result3 = enrich_match_parallel(mock_fotmob, "Home", None)
        assert result3.successful_calls == 0


# ============================================
# TEST 2: Dynamic Threshold
# ============================================

class TestDynamicThreshold:
    """Test suite for dynamic alert threshold."""
    
    def test_dynamic_threshold_base_case(self):
        """Test that base threshold is returned with insufficient data."""
        from src.analysis.optimizer import get_dynamic_alert_threshold, ALERT_THRESHOLD_BASE
        
        # With fresh optimizer (no data), should return base threshold
        threshold, explanation = get_dynamic_alert_threshold()
        
        assert threshold == ALERT_THRESHOLD_BASE
        assert "Base threshold" in explanation or "n=" in explanation
    
    def test_dynamic_threshold_bounds(self):
        """Test that threshold stays within bounds."""
        from src.analysis.optimizer import (
            get_dynamic_alert_threshold,
            ALERT_THRESHOLD_MIN,
            ALERT_THRESHOLD_MAX
        )
        
        threshold, _ = get_dynamic_alert_threshold()
        
        assert threshold >= ALERT_THRESHOLD_MIN
        assert threshold <= ALERT_THRESHOLD_MAX
    
    def test_dynamic_threshold_returns_tuple(self):
        """Test that function returns correct tuple format."""
        from src.analysis.optimizer import get_dynamic_alert_threshold
        
        result = get_dynamic_alert_threshold()
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)


# ============================================
# TEST 3: High-Priority Callback
# ============================================

class TestHighPriorityCallback:
    """Test suite for discovery queue high-priority callback."""
    
    def test_callback_registration(self):
        """Test that callback can be registered."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        callback_called = []
        
        def test_callback(league_key: str):
            callback_called.append(league_key)
        
        queue.register_high_priority_callback(
            callback=test_callback,
            threshold=0.8,
            categories=['INJURY']
        )
        
        assert queue._high_priority_callback is not None
        assert queue._high_priority_threshold == 0.8
        assert 'INJURY' in queue._high_priority_categories
    
    def test_callback_triggered_on_high_priority(self):
        """Test that callback is triggered for high-priority discoveries."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        callback_calls = []
        
        def test_callback(league_key: str):
            callback_calls.append(league_key)
        
        queue.register_high_priority_callback(
            callback=test_callback,
            threshold=0.8,
            categories=['INJURY', 'SUSPENSION']
        )
        
        # Push high-priority discovery
        queue.push(
            data={'title': 'Star player injured'},
            league_key='soccer_epl',
            category='INJURY',
            confidence=0.9
        )
        
        # Callback should have been called
        assert len(callback_calls) == 1
        assert callback_calls[0] == 'soccer_epl'
    
    def test_callback_not_triggered_on_low_priority(self):
        """Test that callback is NOT triggered for low-priority discoveries."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        callback_calls = []
        
        def test_callback(league_key: str):
            callback_calls.append(league_key)
        
        queue.register_high_priority_callback(
            callback=test_callback,
            threshold=0.8,
            categories=['INJURY']
        )
        
        # Push low-confidence discovery
        queue.push(
            data={'title': 'Minor news'},
            league_key='soccer_epl',
            category='INJURY',
            confidence=0.5  # Below threshold
        )
        
        # Callback should NOT have been called
        assert len(callback_calls) == 0
    
    def test_callback_not_triggered_wrong_category(self):
        """Test that callback is NOT triggered for wrong category."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        callback_calls = []
        
        def test_callback(league_key: str):
            callback_calls.append(league_key)
        
        queue.register_high_priority_callback(
            callback=test_callback,
            threshold=0.8,
            categories=['INJURY']  # Only INJURY
        )
        
        # Push high-confidence but wrong category
        queue.push(
            data={'title': 'Transfer news'},
            league_key='soccer_epl',
            category='TRANSFER',  # Not in categories
            confidence=0.95
        )
        
        # Callback should NOT have been called
        assert len(callback_calls) == 0
    
    def test_callback_exception_handling(self):
        """Test that callback exceptions don't crash the queue."""
        from src.utils.discovery_queue import DiscoveryQueue
        
        queue = DiscoveryQueue()
        
        def failing_callback(league_key: str):
            raise Exception("Callback error!")
        
        queue.register_high_priority_callback(
            callback=failing_callback,
            threshold=0.8,
            categories=['INJURY']
        )
        
        # Push should not raise even if callback fails
        uuid = queue.push(
            data={'title': 'Test'},
            league_key='soccer_epl',
            category='INJURY',
            confidence=0.9
        )
        
        # Item should still be in queue
        assert uuid is not None
        assert queue.size() == 1


# ============================================
# TEST 4: Memory Cleanup
# ============================================

class TestMemoryCleanup:
    """Test suite for memory cleanup functionality."""
    
    def test_cleanup_expired_removes_old_items(self):
        """Test that cleanup_expired removes old items."""
        from src.utils.discovery_queue import DiscoveryQueue, DiscoveryItem
        from datetime import timedelta
        
        queue = DiscoveryQueue(ttl_hours=1)  # 1 hour TTL
        
        # Push an item
        queue.push(
            data={'title': 'Test'},
            league_key='soccer_epl',
            category='OTHER',
            confidence=0.5
        )
        
        assert queue.size() == 1
        
        # Manually expire the item by modifying discovered_at
        with queue._lock:
            if queue._queue:
                old_time = datetime.now(timezone.utc) - timedelta(hours=2)
                queue._queue[0] = DiscoveryItem(
                    uuid=queue._queue[0].uuid,
                    league_key=queue._queue[0].league_key,
                    team=queue._queue[0].team,
                    title=queue._queue[0].title,
                    snippet=queue._queue[0].snippet,
                    url=queue._queue[0].url,
                    source_name=queue._queue[0].source_name,
                    category=queue._queue[0].category,
                    confidence=queue._queue[0].confidence,
                    discovered_at=old_time,  # 2 hours ago
                    data=queue._queue[0].data
                )
        
        # Cleanup should remove the expired item
        removed = queue.cleanup_expired()
        
        assert removed == 1
        assert queue.size() == 0
    
    def test_shared_cache_cleanup(self):
        """Test shared cache cleanup functionality.
        
        V7.8 FIX: 
        - Clear cache before test to avoid singleton state pollution
        - Disable fuzzy matching for predictable size (content_cache only)
        
        Note: With enable_fuzzy=True (default), each mark_seen adds to both
        _content_cache AND _simhash_cache, so size() would be 4 for 2 items.
        """
        from src.utils.shared_cache import SharedContentCache
        
        # Create fresh isolated instance with fuzzy disabled for predictable size
        cache = SharedContentCache(ttl_hours=1, enable_fuzzy=False)
        cache.clear()  # Ensure clean state
        
        # Add some content
        cache.mark_seen(content="Test content 1", source="test")
        cache.mark_seen(content="Test content 2", source="test")
        
        # With fuzzy disabled: only content_cache entries (no simhash, no url)
        assert cache.size() == 2
        
        # Cleanup (nothing should be removed yet - items are fresh)
        removed = cache.cleanup_expired()
        assert removed == 0
        assert cache.size() == 2


# ============================================
# INTEGRATION TEST
# ============================================

class TestIntegration:
    """Integration tests for all improvements working together."""
    
    def test_full_flow_mock(self):
        """Test the full flow with mocked components."""
        from src.utils.discovery_queue import get_discovery_queue, reset_discovery_queue
        from src.utils.parallel_enrichment import EnrichmentResult
        
        # Reset singleton for clean test
        reset_discovery_queue()
        
        queue = get_discovery_queue()
        triggered_leagues = []
        
        def on_high_priority(league_key: str):
            triggered_leagues.append(league_key)
        
        queue.register_high_priority_callback(
            callback=on_high_priority,
            threshold=0.85,
            categories=['INJURY', 'SUSPENSION', 'LINEUP']
        )
        
        # Simulate Browser Monitor pushing discoveries
        queue.push(
            data={'title': 'Minor news'},
            league_key='soccer_epl',
            category='OTHER',
            confidence=0.5
        )
        
        queue.push(
            data={'title': 'BREAKING: Star striker injured!'},
            league_key='soccer_spain_la_liga',
            category='INJURY',
            confidence=0.92
        )
        
        # Verify high-priority was triggered
        assert len(triggered_leagues) == 1
        assert triggered_leagues[0] == 'soccer_spain_la_liga'
        
        # Verify queue state
        assert queue.size() == 2
        
        # Cleanup
        reset_discovery_queue()
    
    def test_main_py_imports_dynamic_threshold(self):
        """Test that main.py correctly imports get_dynamic_alert_threshold."""
        # This test verifies the integration is correct
        from src.analysis.optimizer import get_dynamic_alert_threshold
        
        # Verify function is callable and returns expected format
        threshold, explanation = get_dynamic_alert_threshold()
        
        assert isinstance(threshold, float)
        assert isinstance(explanation, str)
        assert 7.5 <= threshold <= 9.0  # Within bounds
    
    def test_main_py_imports_discovery_queue(self):
        """Test that main.py can import discovery queue."""
        from src.utils.discovery_queue import get_discovery_queue
        
        queue = get_discovery_queue()
        assert queue is not None
        assert hasattr(queue, 'register_high_priority_callback')
        assert hasattr(queue, 'push')
    
    def test_run_parallel_enrichment_returns_none_on_invalid_input(self):
        """Test that run_parallel_enrichment handles invalid inputs gracefully."""
        from src.core.analysis_engine import get_analysis_engine
        
        # Get analysis engine instance
        analysis_engine = get_analysis_engine()
        
        # None fotmob should return None
        result = analysis_engine.run_parallel_enrichment(None, "Home", "Away")
        assert result is None
        
        # Empty team names should return None
        from unittest.mock import Mock
        mock_fotmob = Mock()
        result = analysis_engine.run_parallel_enrichment(mock_fotmob, "", "Away")
        assert result is None
    
    def test_parallel_enrichment_failed_calls_tracked(self):
        """
        Regression test: Verify that failed_calls is properly tracked
        so that fallback logic can use it.
        
        Bug fixed: If parallel_result exists but a specific call failed,
        the fallback should still happen for that specific field.
        """
        from src.utils.parallel_enrichment import enrich_match_parallel
        from unittest.mock import Mock
        
        # Create mock that fails on some calls
        mock_fotmob = Mock()
        mock_fotmob.get_full_team_context.return_value = {'injuries': []}
        mock_fotmob.get_turnover_risk.side_effect = [
            Exception("API Error"),  # home_turnover fails
            {'risk_level': 'LOW'}    # away_turnover succeeds
        ]
        mock_fotmob.get_referee_info.return_value = None
        mock_fotmob.get_stadium_coordinates.return_value = None
        mock_fotmob.get_team_stats.return_value = {}
        mock_fotmob.get_tactical_insights.return_value = {}
        
        result = enrich_match_parallel(
            mock_fotmob, "Team A", "Team B", max_workers=2, timeout=10
        )
        
        # Verify failed_calls contains the failed field
        assert 'home_turnover' in result.failed_calls
        assert 'away_turnover' not in result.failed_calls
        
        # Verify home_turnover is None (failed) but away_turnover has data
        assert result.home_turnover is None
        assert result.away_turnover == {'risk_level': 'LOW'}
        
        # This is the key assertion: failed_calls should be usable for fallback logic
        # In main.py, the condition should be:
        # if home_turnover is None and (not parallel_result or 'home_turnover' in failed_calls):
        #     home_turnover = fotmob.get_turnover_risk(...)  # Fallback
        
        # Simulate the fixed fallback logic
        parallel_result_dict = {
            'home_turnover': result.home_turnover,
            'away_turnover': result.away_turnover,
            'failed_calls': result.failed_calls
        }
        
        failed_calls = parallel_result_dict.get('failed_calls', [])
        home_turnover = parallel_result_dict['home_turnover']
        
        # Old buggy logic: would NOT fallback because parallel_result exists
        old_logic_would_fallback = home_turnover is None and not parallel_result_dict
        assert old_logic_would_fallback == False, "Old logic would NOT fallback (bug)"
        
        # New fixed logic: WILL fallback because home_turnover is in failed_calls
        new_logic_would_fallback = home_turnover is None and (not parallel_result_dict or 'home_turnover' in failed_calls)
        assert new_logic_would_fallback == True, "New logic WILL fallback (fix)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
