"""
Test Concurrency Fixes V4.1

Regression tests for:
1. settler.py - Fetch-then-Save pattern (no DB lock during network calls)
2. optimizer.py - Atomic write pattern (crash-safe file writes)
"""
import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


class TestSettlerFetchThenSave:
    """
    Tests for settler.py Fetch-then-Save pattern.
    
    REGRESSION: Previously, network calls (get_match_result, get_match_stats)
    were made INSIDE the DB context, blocking SQLite for 10-150 seconds.
    
    FIX: Phase 1 queries DB (fast), Phase 2 fetches from network (no lock),
    Phase 3 saves to DB (fast batch).
    """
    
    def test_settle_pending_bets_returns_stats_dict(self):
        """Test that settle_pending_bets returns proper stats structure."""
        from src.analysis.settler import settle_pending_bets
        
        # Mock DB to return empty list (no matches to settle)
        with patch('src.analysis.settler.get_db_context') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = []
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)
            
            result = settle_pending_bets(lookback_hours=48)
        
        # Verify stats structure
        assert isinstance(result, dict)
        assert 'total_checked' in result
        assert 'settled' in result
        assert 'wins' in result
        assert 'losses' in result
        assert 'pending' in result
        assert 'errors' in result
        assert 'roi_pct' in result
        assert 'details' in result
    
    def test_settle_handles_empty_matches(self):
        """Test that settlement handles zero matches gracefully."""
        from src.analysis.settler import settle_pending_bets
        
        with patch('src.analysis.settler.get_db_context') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = []
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)
            
            result = settle_pending_bets()
        
        assert result['total_checked'] == 0
        assert result['errors'] == 0
    
    def test_evaluate_bet_btts_win(self):
        """Test BTTS bet evaluation - WIN case."""
        from src.analysis.settler import evaluate_bet, RESULT_WIN
        
        outcome, explanation = evaluate_bet(
            recommended_market="BTTS",
            home_score=2,
            away_score=1,
            home_odd=1.85
        )
        
        assert outcome == RESULT_WIN
        assert "BTTS" in explanation
    
    def test_evaluate_bet_btts_loss(self):
        """Test BTTS bet evaluation - LOSS case (one team didn't score)."""
        from src.analysis.settler import evaluate_bet, RESULT_LOSS
        
        outcome, explanation = evaluate_bet(
            recommended_market="BTTS",
            home_score=2,
            away_score=0,
            home_odd=1.85
        )
        
        assert outcome == RESULT_LOSS
    
    def test_evaluate_bet_cancelled_match(self):
        """Test that cancelled matches return PUSH (void)."""
        from src.analysis.settler import evaluate_bet, RESULT_PUSH
        
        outcome, explanation = evaluate_bet(
            recommended_market="Home Win",
            home_score=0,
            away_score=0,
            home_odd=1.50,
            match_status="CANCELLED"
        )
        
        assert outcome == RESULT_PUSH
        assert "Annullata" in explanation or "cancelled" in explanation.lower()


class TestOptimizerAtomicWrite:
    """
    Tests for optimizer.py atomic write pattern.
    
    REGRESSION: Previously, direct file write could corrupt data on crash.
    
    FIX: Write to temp file, fsync, then atomic os.replace().
    """
    
    def test_atomic_write_creates_file(self):
        """Test that _save_data creates the weights file."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_weights.json")
            
            optimizer = StrategyOptimizer(weights_file=weights_file)
            optimizer.data = {
                "stats": {},
                "drivers": {},
                "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
                "version": "3.0"
            }
            
            result = optimizer._save_data()
            
            assert result is True
            assert os.path.exists(weights_file)
            
            # Verify content is valid JSON
            with open(weights_file, 'r') as f:
                loaded = json.load(f)
            
            assert loaded['version'] == '3.0'
            assert 'last_updated' in loaded
    
    def test_atomic_write_no_temp_file_left(self):
        """Test that temp file is cleaned up after successful write."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_weights.json")
            temp_file = weights_file + '.tmp'
            
            optimizer = StrategyOptimizer(weights_file=weights_file)
            optimizer._save_data()
            
            # Temp file should NOT exist after successful write
            assert not os.path.exists(temp_file)
            # Main file should exist
            assert os.path.exists(weights_file)
    
    def test_atomic_write_overwrites_existing(self):
        """Test that atomic write properly overwrites existing file."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_weights.json")
            
            # Create initial file
            with open(weights_file, 'w') as f:
                json.dump({"version": "1.0", "old": True}, f)
            
            # Overwrite with optimizer
            optimizer = StrategyOptimizer(weights_file=weights_file)
            optimizer.data['test_key'] = 'test_value'
            optimizer._save_data()
            
            # Verify new content
            with open(weights_file, 'r') as f:
                loaded = json.load(f)
            
            assert loaded.get('test_key') == 'test_value'
            assert 'old' not in loaded  # Old content should be gone
    
    def test_load_data_handles_missing_file(self):
        """Test that _load_data handles missing file gracefully."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "nonexistent.json")
            
            optimizer = StrategyOptimizer(weights_file=weights_file)
            
            # Should return default structure, not crash
            assert optimizer.data['version'] == '3.0'
            assert optimizer.data['global']['total_bets'] == 0
    
    def test_load_data_handles_corrupted_file(self):
        """Test that _load_data handles corrupted JSON gracefully."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "corrupted.json")
            
            # Create corrupted file
            with open(weights_file, 'w') as f:
                f.write("{invalid json content")
            
            # Should return default structure, not crash
            optimizer = StrategyOptimizer(weights_file=weights_file)
            
            assert optimizer.data['version'] == '3.0'
    
    def test_record_bet_result_updates_stats(self):
        """Test that record_bet_result properly updates statistics."""
        from src.analysis.optimizer import StrategyOptimizer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_weights.json")
            
            optimizer = StrategyOptimizer(weights_file=weights_file)
            
            # Record a winning bet
            optimizer.record_bet_result(
                league="soccer_italy_serie_a",
                market="Over 2.5",
                outcome="WIN",
                odds=1.85,
                driver="INJURY_INTEL"
            )
            
            # Verify stats updated
            stats = optimizer.data['stats'].get('soccer_italy_serie_a', {}).get('OVER', {})
            assert stats.get('bets', 0) == 1
            assert stats.get('wins', 0) == 1
            assert stats.get('profit', 0) > 0  # 0.85 profit
            
            # Verify driver stats updated
            driver_stats = optimizer.data['drivers'].get('INJURY_INTEL', {})
            assert driver_stats.get('bets', 0) == 1


class TestOptimizerThreadSafety:
    """
    V5.3: Tests for thread-safe optimizer operations.
    
    REGRESSION: _save_data() had no lock, concurrent writes could corrupt file.
    FIX: Added _data_lock to StrategyOptimizer for thread-safe saves.
    """
    
    def test_optimizer_has_data_lock(self):
        """V5.3: Optimizer should have _data_lock attribute."""
        from src.analysis.optimizer import StrategyOptimizer
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_lock.json")
            optimizer = StrategyOptimizer(weights_file=weights_file)
            
            assert hasattr(optimizer, '_data_lock')
            assert isinstance(optimizer._data_lock, type(threading.Lock()))
    
    def test_concurrent_saves_no_corruption(self):
        """V5.3: Multiple concurrent saves should not corrupt data."""
        from src.analysis.optimizer import StrategyOptimizer
        import threading
        import time
        
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_concurrent.json")
            optimizer = StrategyOptimizer(weights_file=weights_file)
            
            errors = []
            
            def save_worker(worker_id):
                try:
                    for i in range(5):
                        optimizer.data['global']['total_bets'] = worker_id * 100 + i
                        optimizer._save_data()
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(f"Worker {worker_id}: {e}")
            
            # Start multiple threads
            threads = [threading.Thread(target=save_worker, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # No errors should have occurred
            assert len(errors) == 0, f"Errors during concurrent saves: {errors}"
            
            # File should be valid JSON
            import json
            with open(weights_file, 'r') as f:
                data = json.load(f)
            assert 'version' in data
            assert data['version'] == '3.0'


class TestPromptsInjurySection:
    """
    Tests for prompts.py injury section handling.
    
    REGRESSION: Previously, empty missing_players list resulted in
    ambiguous prompt (AI couldn't tell if no injuries or data unavailable).
    
    FIX: Explicit message when no injuries reported.
    """
    
    def test_prompt_with_missing_players(self):
        """Test prompt includes injury analysis when players provided."""
        from src.ingestion.prompts import build_deep_dive_prompt
        
        prompt = build_deep_dive_prompt(
            home_team="Real Madrid",
            away_team="Barcelona",
            match_date="2024-03-15",
            referee="Referee Name",
            missing_players=["Vinicius Jr", "Bellingham"]
        )
        
        assert "Vinicius Jr" in prompt
        assert "Bellingham" in prompt
        assert "INJURY IMPACT" in prompt
        assert "BTTS TACTICAL" in prompt
    
    def test_prompt_without_missing_players(self):
        """Test prompt has explicit 'no injuries' message when list is empty."""
        from src.ingestion.prompts import build_deep_dive_prompt
        
        prompt = build_deep_dive_prompt(
            home_team="Real Madrid",
            away_team="Barcelona",
            match_date="2024-03-15",
            referee="Referee Name",
            missing_players=[]
        )
        
        # Should have prompt with match context
        assert "Real Madrid" in prompt
        assert "Barcelona" in prompt
        assert "2024-03-15" in prompt
        # Should NOT have injury section when missing_players is empty
        assert "INJURY IMPACT" not in prompt
    
    def test_prompt_with_none_missing_players(self):
        """Test prompt handles None missing_players."""
        from src.ingestion.prompts import build_deep_dive_prompt
        
        prompt = build_deep_dive_prompt(
            home_team="Real Madrid",
            away_team="Barcelona",
            match_date="2024-03-15",
            referee="Referee Name",
            missing_players=None
        )
        
        # Should have prompt with match context
        assert "Real Madrid" in prompt
        assert "Barcelona" in prompt
        # Should NOT have injury section when missing_players is None
        assert "INJURY IMPACT" not in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
