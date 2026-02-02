"""
Tavily Double Cycle Rotation Tests

Tests for V8.0 double cycle rotation with monthly reset before fallback.
Validates that the system attempts a monthly reset when all keys are exhausted
before activating the fallback to Brave/DDG.

Requirements: V8.0
"""
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.ingestion.tavily_key_rotator import TavilyKeyRotator


class TestDoubleCycleRotation:
    """
    **Feature: tavily-double-cycle, V8.0**
    
    Tests for double cycle rotation with monthly reset before fallback.
    When all keys are exhausted, the system should attempt a monthly reset
    before activating fallback, allowing up to 2 full cycles per month.
    """
    
    def test_cycle_count_initialization(self):
        """
        Test: Cycle count initializes to 0.
        
        A newly created rotator should have cycle_count = 0.
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        assert rotator.get_cycle_count() == 0
        assert rotator._last_cycle_month is None
    
    def test_single_cycle_rotation(self):
        """
        Test: First cycle works normally.
        
        During the first cycle, rotation should work as before without
        triggering the double cycle logic.
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Mark first key as exhausted
        rotator.mark_exhausted(0)
        
        # Rotate to next key
        success = rotator.rotate_to_next()
        
        assert success
        assert rotator._current_index == 1
        assert rotator.get_cycle_count() == 0
    
    def test_all_keys_exhausted_no_month_passed(self):
        """
        Test: All keys exhausted without month change returns False.
        
        When all keys are exhausted and no month has passed,
        rotate_to_next() should return False (activating fallback).
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Set last_cycle_month to current month to prevent double cycle
        current_month = datetime.now(timezone.utc).month
        rotator._last_cycle_month = current_month
        
        # Exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Try to rotate - should return False
        success = rotator.rotate_to_next()
        
        assert not success
        assert rotator.get_cycle_count() == 0
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_double_cycle_with_monthly_reset(self, mock_datetime):
        """
        Test: Double cycle activates when month has passed.
        
        When all keys are exhausted and a month has passed,
        rotate_to_next() should reset all keys and start a new cycle.
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Set last_cycle_month to previous month
        rotator._last_cycle_month = 12  # December
        
        # Exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Try to rotate - should succeed with double cycle
        success = rotator.rotate_to_next()
        
        assert success
        assert rotator.get_cycle_count() == 1
        assert rotator._last_cycle_month == 1  # January
        assert len(rotator._exhausted_keys) == 0  # All keys reset
        # V8.0: Advances to next key after reset (Key 1)
        assert rotator._current_index == 1  # Back to first key (index 1 in V8.0 loop)
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_double_cycle_second_cycle_exhaustion(self, mock_datetime):
        """
        Test: Second cycle exhaustion activates fallback.
        
        When all keys are exhausted in the second cycle and no month
        has passed, fallback should be activated.
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # First cycle: exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        assert rotator.rotate_to_next()
        assert rotator.get_cycle_count() == 1
        
        # Second cycle: exhaust all keys again
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Try to rotate - should return False (no more cycles)
        success = rotator.rotate_to_next()
        
        assert not success
        assert rotator.get_cycle_count() == 1
    
    def test_status_includes_cycle_info(self):
        """
        Test: get_status() includes cycle information.
        
        The status dictionary should include cycle_count, current_cycle,
        and last_cycle_month.
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        status = rotator.get_status()
        
        assert "cycle_count" in status
        assert "current_cycle" in status
        assert "last_cycle_month" in status
        assert status["cycle_count"] == 0
        assert status["current_cycle"] == 1
        assert status["last_cycle_month"] is None
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_status_cycle_info_updates(self, mock_datetime):
        """
        Test: Cycle info in status updates after double cycle.
        
        After a double cycle, the status should reflect the new cycle count.
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # First cycle: exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        rotator.rotate_to_next()
        
        # Check status
        status = rotator.get_status()
        
        assert status["cycle_count"] == 1
        assert status["current_cycle"] == 2
        assert status["last_cycle_month"] == 1
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_get_current_key_after_double_cycle(self, mock_datetime):
        """
        Test: get_current_key() works after double cycle.
        
        After a double cycle, get_current_key() should return
        the first key of the new cycle.
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # First cycle: exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        rotator.rotate_to_next()
        
        # Get current key
        current_key = rotator.get_current_key()
        
        # V8.0: Advances to next key after reset (Key 1)
        assert current_key == keys[1]
        assert rotator.get_cycle_count() == 1
    
    def test_usage_tracking_across_cycles(self):
        """
        Test: Usage tracking resets correctly across cycles.
        
        After a double cycle, usage should be reset to 0 for all keys.
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Record some usage
        for i in range(len(keys)):
            rotator._current_index = i
            rotator.record_call()
        
        # Verify usage
        assert all(rotator._key_usage[i] == 1 for i in range(len(keys)))
        
        # Manually trigger reset (simulating double cycle)
        rotator.reset_all()
        rotator._cycle_count = 1
        
        # Verify usage reset
        assert all(rotator._key_usage[i] == 0 for i in range(len(keys)))
        assert rotator.get_cycle_count() == 1
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_double_cycle_with_7_keys(self, mock_datetime):
        """
        Test: Double cycle works with full 7 keys.
        
        Test the double cycle logic with the actual number of keys
        used in production (7 keys).
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(7)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Exhaust all 7 keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        success = rotator.rotate_to_next()
        
        assert success
        assert rotator.get_cycle_count() == 1
        assert len(rotator._exhausted_keys) == 0
        # V8.0: Advances to next key after reset (Key 1)
        assert rotator._current_index == 1
        assert rotator.get_current_key() == keys[1]
    
    def test_is_available_after_double_cycle(self):
        """
        Test: is_available() returns True after double cycle.
        
        After a double cycle reset, is_available() should return True.
        """
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Manually trigger reset (simulating double cycle)
        rotator.reset_all()
        rotator._cycle_count = 1
        
        # Check availability
        assert rotator.is_available()
        assert rotator.get_cycle_count() == 1
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_double_cycle_logs_correct_messages(self, mock_datetime, caplog):
        """
        Test: Double cycle logs appropriate messages.
        
        When double cycle activates, appropriate log messages should be emitted.
        """
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        
        # Exhaust all keys
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        
        with caplog.at_level("INFO"):
            rotator.rotate_to_next()
        
        # Check for double cycle log message
        log_messages = [record.message for record in caplog.records]
        assert any("double cycle" in msg.lower() for msg in log_messages)
        assert any("cycle 1 → 2" in msg or "cycle 2" in msg for msg in log_messages)


class TestDoubleCycleIntegration:
    """
    **Feature: tavily-double-cycle-integration, V8.0**
    
    Integration tests for double cycle rotation with TavilyProvider.
    """
    
    @patch('src.ingestion.tavily_key_rotator.datetime')
    def test_provider_fallback_after_second_cycle(self, mock_datetime):
        """
        Test: Provider activates fallback after second cycle exhaustion.
        
        When TavilyProvider exhausts all keys twice within the same month,
        it should activate the fallback to Brave/DDG.
        """
        from src.ingestion.tavily_provider import TavilyProvider
        from unittest.mock import MagicMock, patch
        
        # Setup mock datetime
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = base_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs, tzinfo=timezone.utc)
        
        # Create provider with test keys
        keys = [f"tvly-test-key-{i}" for i in range(3)]
        rotator = TavilyKeyRotator(keys=keys)
        provider = TavilyProvider(key_rotator=rotator)
        
        # Simulate first cycle exhaustion
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Trigger double cycle
        rotator._last_cycle_month = 12  # Previous month
        rotator.rotate_to_next()
        
        # Simulate second cycle exhaustion
        for i in range(len(keys)):
            rotator.mark_exhausted(i)
        
        # Try to rotate - should return False
        success = rotator.rotate_to_next()
        
        assert not success
        assert rotator.get_cycle_count() == 1
        # The provider's _fallback_active flag is only set if provider.search() is called.
        # Here we only used the rotator, so the flag isn't updated.
        # But the provider should report unavailable because rotator is unavailable.
        assert not provider.is_available()
