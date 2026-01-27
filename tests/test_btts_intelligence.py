"""
Test BTTS Intelligence V4.1

Tests for:
1. calculate_btts_trend() - H2H BTTS frequency calculation
2. Edge cases: empty lists, None values, malformed data
"""
import pytest
from src.analysis.math_engine import calculate_btts_trend


class TestCalculateBttsTrend:
    """Tests for calculate_btts_trend function."""
    
    def test_btts_trend_normal_case(self):
        """Test with valid H2H data - 3 out of 5 games BTTS."""
        h2h_matches = [
            {'home_score': 2, 'away_score': 1},  # BTTS ✓
            {'home_score': 1, 'away_score': 0},  # No BTTS
            {'home_score': 1, 'away_score': 2},  # BTTS ✓
            {'home_score': 0, 'away_score': 0},  # No BTTS
            {'home_score': 3, 'away_score': 1},  # BTTS ✓
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['total_games'] == 5
        assert result['btts_hits'] == 3
        assert result['btts_rate'] == 60.0
        assert result['trend_signal'] == "High"  # >= 60%
    
    def test_btts_trend_all_btts(self):
        """Test when all games have BTTS."""
        h2h_matches = [
            {'home_score': 2, 'away_score': 1},
            {'home_score': 1, 'away_score': 1},
            {'home_score': 3, 'away_score': 2},
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['btts_rate'] == 100.0
        assert result['btts_hits'] == 3
        assert result['trend_signal'] == "High"
    
    def test_btts_trend_no_btts(self):
        """Test when no games have BTTS."""
        h2h_matches = [
            {'home_score': 1, 'away_score': 0},
            {'home_score': 0, 'away_score': 2},
            {'home_score': 0, 'away_score': 0},
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['btts_rate'] == 0.0
        assert result['btts_hits'] == 0
        assert result['trend_signal'] == "Low"  # < 40%
    
    def test_btts_trend_medium_signal(self):
        """Test medium signal (40-60%)."""
        h2h_matches = [
            {'home_score': 2, 'away_score': 1},  # BTTS ✓
            {'home_score': 1, 'away_score': 0},  # No BTTS
            {'home_score': 1, 'away_score': 2},  # BTTS ✓
            {'home_score': 0, 'away_score': 1},  # No BTTS
            {'home_score': 2, 'away_score': 0},  # No BTTS
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['btts_rate'] == 40.0
        assert result['trend_signal'] == "Medium"  # 40-60%
    
    def test_btts_trend_empty_list(self):
        """Test with empty list - should return safe defaults."""
        result = calculate_btts_trend([])
        
        assert result['total_games'] == 0
        assert result['btts_hits'] == 0
        assert result['btts_rate'] == 0.0
        assert result['trend_signal'] == "Unknown"
    
    def test_btts_trend_none_input(self):
        """Test with None input - should not crash."""
        result = calculate_btts_trend(None)
        
        assert result['total_games'] == 0
        assert result['btts_rate'] == 0.0
        assert result['trend_signal'] == "Unknown"
    
    def test_btts_trend_none_scores(self):
        """Test with None scores in matches - should skip them."""
        h2h_matches = [
            {'home_score': 2, 'away_score': 1},  # Valid BTTS
            {'home_score': None, 'away_score': 1},  # Invalid - skip
            {'home_score': 1, 'away_score': None},  # Invalid - skip
            {'home_score': 1, 'away_score': 2},  # Valid BTTS
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['total_games'] == 2  # Only 2 valid games
        assert result['btts_hits'] == 2
        assert result['btts_rate'] == 100.0
    
    def test_btts_trend_string_scores(self):
        """Test with string scores (API might return strings)."""
        h2h_matches = [
            {'home_score': '2', 'away_score': '1'},  # BTTS ✓
            {'home_score': '0', 'away_score': '1'},  # No BTTS
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['total_games'] == 2
        assert result['btts_hits'] == 1
        assert result['btts_rate'] == 50.0
    
    def test_btts_trend_malformed_entries(self):
        """Test with malformed entries - should skip them safely."""
        h2h_matches = [
            {'home_score': 2, 'away_score': 1},  # Valid
            "not a dict",  # Invalid - skip
            {'wrong_key': 1},  # Invalid - skip
            None,  # Invalid - skip
            {'home_score': 1, 'away_score': 1},  # Valid
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        assert result['total_games'] == 2
        assert result['btts_hits'] == 2
    
    def test_btts_trend_division_by_zero_protection(self):
        """Test that division by zero is handled when all entries are invalid."""
        h2h_matches = [
            {'home_score': None, 'away_score': None},
            {'invalid': 'data'},
        ]
        
        result = calculate_btts_trend(h2h_matches)
        
        # Should not crash, should return 0%
        assert result['total_games'] == 0
        assert result['btts_rate'] == 0.0
        assert result['trend_signal'] == "Unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
