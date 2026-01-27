"""
Test Interval Change V4.4

Regression tests for:
1. should_run_settlement() - Window expanded from hour==4 to 4<=hour<8
2. Main loop sleep interval changed from 3600s to 7200s

CRITICAL: These tests ensure the bot doesn't skip nightly settlement
when running on 2-hour cycles.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, mock_open
import os


class TestSettlementWindowV44:
    """
    Tests for should_run_settlement() V4.4 changes.
    
    REGRESSION: With 1-hour cycles, checking `hour == 4` worked fine.
    With 2-hour cycles, if bot runs at 03:00, next cycle is 05:00 → skips 04:00!
    
    FIX: Changed to `4 <= hour < 8` so settlement runs on first cycle after 04:00.
    """
    
    def test_settlement_runs_at_04_00(self):
        """Settlement should run at exactly 04:00 UTC."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 4, 0, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is True, "Settlement should run at 04:00 UTC"
    
    def test_settlement_runs_at_05_00(self):
        """Settlement should run at 05:00 UTC (2-hour cycle scenario)."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 5, 30, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is True, "Settlement should run at 05:30 UTC (after skipping 04:00)"
    
    def test_settlement_runs_at_07_59(self):
        """Settlement should still run at 07:59 UTC (edge of window)."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 7, 59, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is True, "Settlement should run at 07:59 UTC"
    
    def test_settlement_blocked_at_08_00(self):
        """Settlement should NOT run at 08:00 UTC (peak hours)."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 8, 0, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is False, "Settlement should NOT run at 08:00 UTC"
    
    def test_settlement_blocked_at_03_00(self):
        """Settlement should NOT run at 03:00 UTC (before window)."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 3, 59, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is False, "Settlement should NOT run at 03:59 UTC"
    
    def test_settlement_blocked_if_already_ran_today(self):
        """Settlement should NOT run twice in the same day."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 6, 0, 0, tzinfo=timezone.utc)
        today_str = "2025-12-29"
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data=today_str)):
                    result = should_run_settlement()
        
        assert result is False, "Settlement should NOT run twice in same day"
    
    def test_settlement_runs_next_day(self):
        """Settlement should run if last run was yesterday."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 5, 0, 0, tzinfo=timezone.utc)
        yesterday_str = "2025-12-28"
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data=yesterday_str)):
                    result = should_run_settlement()
        
        assert result is True, "Settlement should run if last run was yesterday"
    
    def test_settlement_handles_missing_flag_file(self):
        """Settlement should run if flag file doesn't exist (first run)."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 4, 30, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=False):
                result = should_run_settlement()
        
        assert result is True, "Settlement should run on first execution"
    
    def test_settlement_handles_corrupted_flag_file(self):
        """Settlement should handle corrupted flag file gracefully."""
        from src.main import should_run_settlement
        
        mock_time = datetime(2025, 12, 29, 5, 0, 0, tzinfo=timezone.utc)
        
        with patch('src.main.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            with patch('os.path.exists', return_value=True):
                # Simulate file read error
                with patch('builtins.open', side_effect=IOError("Disk error")):
                    result = should_run_settlement()
        
        # Should return True (fail-open) to ensure settlement runs
        assert result is True, "Settlement should run if flag file is corrupted"


class TestSleepIntervalV44:
    """
    Tests to verify sleep interval is correctly set to 7200 seconds.
    
    NOTE: These are documentation tests - the actual sleep is in run_continuous()
    which is hard to unit test. We verify the constant is correct.
    """
    
    def test_sleep_interval_is_7200(self):
        """Verify the sleep interval in main.py is 7200 seconds (2 hours)."""
        import re
        
        with open('src/main.py', 'r') as f:
            content = f.read()
        
        # Find the sleep call in run_continuous
        sleep_match = re.search(r'time\.sleep\((\d+)\)', content)
        
        # Should find at least one sleep call
        assert sleep_match is not None, "Should find time.sleep() call"
        
        # The main loop sleep should be 7200
        # Note: There are other sleeps (600, 300) for error handling
        assert '7200' in content, "Main loop should sleep for 7200 seconds"
        assert 'Sleeping for 120 minutes' in content, "Log message should say 120 minutes"
    
    def test_no_3600_in_main_loop(self):
        """Verify the old 3600 second sleep is removed from main loop."""
        with open('src/main.py', 'r') as f:
            content = f.read()
        
        # The old pattern should NOT exist
        assert 'Sleeping for 60 minutes' not in content, "Old 60 minutes message should be removed"


class TestHealthMonitorCompatibility:
    """
    Tests to verify Health Monitor is compatible with 2-hour cycles.
    """
    
    def test_heartbeat_interval_independent(self):
        """Heartbeat interval (4h) should work with 2h cycles."""
        from src.alerting.health_monitor import HealthMonitor
        
        monitor = HealthMonitor()
        
        # Heartbeat is every 4 hours, cycle is every 2 hours
        # So heartbeat fires every 2 cycles - this is fine
        assert monitor.HEARTBEAT_INTERVAL_HOURS == 4
        
        # With 2h cycles: cycle 1 (0h), cycle 2 (2h), cycle 3 (4h) → heartbeat
        # This is correct behavior
    
    def test_error_cooldown_independent(self):
        """Error cooldown (30min) should work with 2h cycles."""
        from src.alerting.health_monitor import HealthMonitor
        
        monitor = HealthMonitor()
        
        # Error cooldown is 30 minutes, much shorter than 2h cycle
        # This means errors are still rate-limited within a cycle
        assert monitor.ERROR_ALERT_COOLDOWN_MINUTES == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
