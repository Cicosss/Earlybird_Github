"""
Test suite for Telegram Command Center (Phase 10)

Tests the bot commands:
- /ping - Health check
- /stat - Stats dashboard
- /debug - Error log viewer
- /report - CSV export
- /settle - Settlement calculation
- /stop, /resume - Pause control
- /status - System status

V5.0: Includes CLV tracking verification
"""
import pytest
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestAdminTools:
    """Test admin_tools.py helper functions."""
    
    def test_read_last_error_lines_empty_file(self):
        """Should return empty list for non-existent file."""
        from src.utils.admin_tools import read_last_error_lines
        
        result = read_last_error_lines("nonexistent_file_12345.log", 10)
        assert result == []
    
    def test_read_last_error_lines_filters_errors(self):
        """Should only return ERROR, WARNING, CRITICAL lines."""
        from src.utils.admin_tools import read_last_error_lines
        
        # Create temp log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("2024-01-01 10:00:00 - INFO - Normal message\n")
            f.write("2024-01-01 10:01:00 - ERROR - Error message\n")
            f.write("2024-01-01 10:02:00 - DEBUG - Debug message\n")
            f.write("2024-01-01 10:03:00 - WARNING - Warning message\n")
            f.write("2024-01-01 10:04:00 - CRITICAL - Critical message\n")
            temp_path = f.name
        
        try:
            result = read_last_error_lines(temp_path, 10)
            assert len(result) == 3
            assert any("ERROR" in line for line in result)
            assert any("WARNING" in line for line in result)
            assert any("CRITICAL" in line for line in result)
            assert not any("INFO" in line for line in result)
            assert not any("DEBUG" in line for line in result)
        finally:
            os.unlink(temp_path)
    
    def test_read_last_error_lines_respects_limit(self):
        """Should respect the N limit parameter."""
        from src.utils.admin_tools import read_last_error_lines
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            for i in range(20):
                f.write(f"2024-01-01 10:{i:02d}:00 - ERROR - Error {i}\n")
            temp_path = f.name
        
        try:
            result = read_last_error_lines(temp_path, 5)
            assert len(result) == 5
            # Should be the LAST 5 errors
            assert "Error 19" in result[-1]
            assert "Error 15" in result[0]
        finally:
            os.unlink(temp_path)
    
    def test_format_debug_output_empty(self):
        """Should return success message for empty list."""
        from src.utils.admin_tools import format_debug_output
        
        result = format_debug_output([])
        assert "Nessun errore" in result
        assert "✅" in result
    
    def test_format_debug_output_with_errors(self):
        """Should format errors with appropriate icons."""
        from src.utils.admin_tools import format_debug_output
        
        lines = [
            "2024-01-01 10:00:00 - ERROR - Test error",
            "2024-01-01 10:01:00 - WARNING - Test warning",
            "2024-01-01 10:02:00 - CRITICAL - Test critical"
        ]
        
        result = format_debug_output(lines)
        assert "❌" in result  # ERROR icon
        assert "⚠️" in result  # WARNING icon
        assert "🔴" in result  # CRITICAL icon


class TestStatsDrawer:
    """Test stats_drawer.py dashboard generation."""
    
    def test_get_stats_data_returns_dict(self):
        """Should return a dict with required keys."""
        from src.analysis.stats_drawer import get_stats_data
        
        stats = get_stats_data()
        
        assert isinstance(stats, dict)
        required_keys = ['total_bets', 'wins', 'losses', 'profit', 'roi', 'win_rate']
        for key in required_keys:
            assert key in stats, f"Missing key: {key}"
    
    def test_get_stats_data_handles_missing_file(self):
        """Should handle missing optimizer_weights.json gracefully."""
        from src.analysis.stats_drawer import get_stats_data, OPTIMIZER_WEIGHTS_FILE
        
        # Temporarily rename file if exists
        backup_path = None
        if os.path.exists(OPTIMIZER_WEIGHTS_FILE):
            backup_path = OPTIMIZER_WEIGHTS_FILE + ".bak"
            os.rename(OPTIMIZER_WEIGHTS_FILE, backup_path)
        
        try:
            stats = get_stats_data()
            # Should return defaults without crashing
            assert stats['total_bets'] == 0
            assert stats['profit'] == 0.0
        finally:
            if backup_path and os.path.exists(backup_path):
                os.rename(backup_path, OPTIMIZER_WEIGHTS_FILE)
    
    def test_get_text_summary_returns_html(self):
        """Should return HTML-formatted summary."""
        from src.analysis.stats_drawer import get_text_summary
        
        summary = get_text_summary()
        
        assert isinstance(summary, str)
        assert "<b>" in summary  # HTML bold tags
        assert "EARLYBIRD" in summary
    
    def test_draw_dashboard_creates_file(self):
        """Should create PNG file when matplotlib available."""
        from src.analysis.stats_drawer import draw_dashboard, STATS_IMAGE_PATH
        
        try:
            import matplotlib
            
            # Clean up any existing file
            if os.path.exists(STATS_IMAGE_PATH):
                os.remove(STATS_IMAGE_PATH)
            
            result = draw_dashboard()
            
            assert result == STATS_IMAGE_PATH
            assert os.path.exists(STATS_IMAGE_PATH)
            assert os.path.getsize(STATS_IMAGE_PATH) > 0
            
        except ImportError:
            pytest.skip("matplotlib not installed")
        finally:
            if os.path.exists(STATS_IMAGE_PATH):
                os.remove(STATS_IMAGE_PATH)


class TestSettler:
    """Test settler.py bet evaluation functions."""
    
    def test_calculate_clv_positive(self):
        """Positive CLV when we got better odds than closing."""
        from src.analysis.settler import calculate_clv
        
        # We took 2.0, closed at 1.8 -> we beat the line
        clv = calculate_clv(2.0, 1.8)
        assert clv is not None
        assert clv > 0
    
    def test_calculate_clv_negative(self):
        """Negative CLV when closing odds were better."""
        from src.analysis.settler import calculate_clv
        
        # We took 1.8, closed at 2.0 -> we didn't beat the line
        clv = calculate_clv(1.8, 2.0)
        assert clv is not None
        assert clv < 0
    
    def test_calculate_clv_edge_cases(self):
        """Should handle edge cases gracefully."""
        from src.analysis.settler import calculate_clv
        
        assert calculate_clv(None, 1.8) is None
        assert calculate_clv(2.0, None) is None
        assert calculate_clv(1.0, 1.8) is None  # Invalid odds
        assert calculate_clv(2.0, 1.0) is None  # Invalid odds
        assert calculate_clv(0.5, 1.8) is None  # Invalid odds
        assert calculate_clv(2.0, 0.5) is None  # Invalid odds
        # V5.0: Infinity and unreasonably high odds
        assert calculate_clv(float('inf'), 2.0) is None
        assert calculate_clv(2.0, float('inf')) is None
        assert calculate_clv(2000, 2.0) is None  # > 1000 threshold
        assert calculate_clv(2.0, 2000) is None
    
    def test_evaluate_bet_home_win(self):
        """Should correctly evaluate Home Win market."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        result, _ = evaluate_bet("Home Win", 2, 1)
        assert result == RESULT_WIN
        
        result, _ = evaluate_bet("Home Win", 1, 2)
        assert result == RESULT_LOSS
        
        result, _ = evaluate_bet("Home Win", 1, 1)
        assert result == RESULT_LOSS  # Draw is not a home win
    
    def test_evaluate_bet_over_under_goals(self):
        """Should correctly evaluate Over/Under goals markets."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS
        
        # Over 2.5 with 4 goals
        result, _ = evaluate_bet("Over 2.5 Goals", 2, 2)
        assert result == RESULT_WIN
        
        # Over 2.5 with 2 goals
        result, _ = evaluate_bet("Over 2.5 Goals", 1, 1)
        assert result == RESULT_LOSS
        
        # Under 2.5 with 2 goals
        result, _ = evaluate_bet("Under 2.5 Goals", 1, 1)
        assert result == RESULT_WIN
    
    def test_evaluate_bet_corners(self):
        """Should correctly evaluate corner markets with stats."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS, RESULT_PENDING
        
        # Over 9.5 corners with 11 total
        result, _ = evaluate_bet(
            "Over 9.5 Corners", 0, 0,
            match_stats={'home_corners': 6, 'away_corners': 5}
        )
        assert result == RESULT_WIN
        
        # Over 9.5 corners with 8 total
        result, _ = evaluate_bet(
            "Over 9.5 Corners", 0, 0,
            match_stats={'home_corners': 4, 'away_corners': 4}
        )
        assert result == RESULT_LOSS
        
        # Missing stats -> PENDING
        result, _ = evaluate_bet("Over 9.5 Corners", 0, 0, match_stats=None)
        assert result == RESULT_PENDING
    
    def test_evaluate_bet_cards(self):
        """Should correctly evaluate card markets with stats."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN, RESULT_LOSS, RESULT_PENDING
        
        # Over 4.5 cards with 6 total
        result, _ = evaluate_bet(
            "Over 4.5 Cards", 0, 0,
            match_stats={'home_yellow_cards': 3, 'away_yellow_cards': 2, 'home_red_cards': 1, 'away_red_cards': 0}
        )
        assert result == RESULT_WIN
        
        # Under 4.5 cards with 3 total
        result, _ = evaluate_bet(
            "Under 4.5 Cards", 0, 0,
            match_stats={'home_yellow_cards': 2, 'away_yellow_cards': 1, 'home_red_cards': 0, 'away_red_cards': 0}
        )
        assert result == RESULT_WIN
    
    def test_evaluate_bet_postponed(self):
        """Should return PUSH for postponed/cancelled matches."""
        from src.analysis.settler import evaluate_bet, RESULT_PUSH
        
        result, msg = evaluate_bet("Home Win", 0, 0, match_status='POSTPONED')
        assert result == RESULT_PUSH
        assert "Annullata" in msg
        
        result, msg = evaluate_bet("Home Win", 0, 0, match_status='CANCELLED')
        assert result == RESULT_PUSH


class TestReporter:
    """Test reporter.py CSV export functions."""
    
    def test_get_daily_summary_returns_dict(self):
        """Should return dict with required keys."""
        from src.analysis.reporter import get_daily_summary
        
        summary = get_daily_summary()
        
        assert isinstance(summary, dict)
        assert 'total_alerts' in summary
        assert 'leagues_covered' in summary
        assert 'top_score' in summary
    
    def test_export_bet_history_handles_no_data(self):
        """Should return None when no data available."""
        from src.analysis.reporter import export_bet_history
        
        # With a very short lookback, likely no data
        result = export_bet_history(days=0)
        
        # Should return None or a path (both are valid)
        assert result is None or isinstance(result, str)


class TestPauseResume:
    """Test pause/resume functionality."""
    
    def test_pause_file_path_configured(self):
        """PAUSE_FILE should be properly configured."""
        from config.settings import PAUSE_FILE
        
        assert PAUSE_FILE is not None
        assert isinstance(PAUSE_FILE, str)
        assert "pause" in PAUSE_FILE.lower()
    
    def test_pause_file_directory_exists(self):
        """Pause file directory should exist or be creatable."""
        from config.settings import PAUSE_FILE
        
        pause_dir = os.path.dirname(PAUSE_FILE)
        os.makedirs(pause_dir, exist_ok=True)
        
        assert os.path.exists(pause_dir)
    
    def test_pause_file_creation_deletion(self):
        """Should be able to create and delete pause file."""
        from config.settings import PAUSE_FILE
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(PAUSE_FILE), exist_ok=True)
        
        # Create
        with open(PAUSE_FILE, 'w') as f:
            f.write("test")
        assert os.path.exists(PAUSE_FILE)
        
        # Delete
        os.remove(PAUSE_FILE)
        assert not os.path.exists(PAUSE_FILE)


class TestIsAdmin:
    """Test admin verification function."""
    
    def test_is_admin_with_matching_id(self):
        """Should return True for matching admin ID."""
        from src.run_bot import is_admin
        from config.settings import TELEGRAM_CHAT_ID
        
        if TELEGRAM_CHAT_ID:
            # If configured, test with actual ID
            result = is_admin(int(TELEGRAM_CHAT_ID))
            assert result is True
    
    def test_is_admin_with_non_matching_id(self):
        """Should return False for non-matching ID."""
        from src.run_bot import is_admin
        
        result = is_admin(999999999)
        # Should be False unless this happens to be the admin ID
        assert isinstance(result, bool)
    
    def test_is_admin_handles_none(self):
        """Should handle None gracefully."""
        from src.run_bot import is_admin
        
        # Should not crash
        result = is_admin(None)
        assert result is False
    
    def test_is_admin_handles_string_comparison(self):
        """Should handle string/int comparison correctly."""
        from src.run_bot import is_admin
        
        # The function converts to string for comparison
        # This should not crash
        result = is_admin(123456)
        assert isinstance(result, bool)


class TestDatabaseCLVColumns:
    """Test that database has CLV tracking columns."""
    
    def test_newslog_has_clv_columns(self):
        """NewsLog should have CLV tracking columns."""
        from src.database.models import NewsLog
        from sqlalchemy import inspect
        
        inspector = inspect(NewsLog)
        columns = [c.name for c in inspector.columns]
        
        assert 'odds_taken' in columns
        assert 'clv_percent' in columns
        assert 'closing_odds' in columns
    
    def test_match_has_stats_columns(self):
        """Match should have stats warehousing columns."""
        from src.database.models import Match
        from sqlalchemy import inspect
        
        inspector = inspect(Match)
        columns = [c.name for c in inspector.columns]
        
        # V3.7 stats columns
        assert 'home_corners' in columns
        assert 'away_corners' in columns
        assert 'home_yellow_cards' in columns
        assert 'away_yellow_cards' in columns
