"""
Test: Kickoff Time Validation in get_match_details

Verifies that FotMob matches are rejected if kickoff time differs
by more than 4 hours from the expected time (Odds API).

This prevents "wrong match" mapping where FotMob returns a different
match than the one we're analyzing.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestKickoffValidation:
    """Test kickoff time validation in get_match_details."""
    
    def test_reject_match_outside_4h_window(self):
        """
        CRITICAL TEST: If FotMob returns a match at 03:00 but Odds API
        expects 14:00, the match should be REJECTED (returns None).
        
        This test would FAIL with the old 36h tolerance.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_fixture_details to return a match at 03:00 UTC
        mock_result = {
            'team_id': 12345,
            'team_name': 'Test Team',
            'opponent': 'Other Team',
            'match_time': '2025-12-26T03:00:00Z',  # 03:00 UTC
            'injuries': [],
            'source': 'FotMob'
        }
        
        with patch.object(provider, 'get_fixture_details', return_value=mock_result):
            # Expected match at 14:00 UTC (11 hours difference)
            expected_time = datetime(2025, 12, 26, 14, 0, 0, tzinfo=timezone.utc)
            
            result = provider.get_match_details(
                team_name='Test Team',
                home_team='Test Team',
                away_team='Other Team',
                match_date=expected_time
            )
            
            # Should return None because 11h > 4h tolerance
            assert result is None, "Match should be rejected when kickoff differs by >4 hours"
    
    def test_accept_match_within_4h_window(self):
        """
        Match within 4h tolerance should be ACCEPTED.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_fixture_details to return a match at 14:30 UTC
        mock_result = {
            'team_id': 12345,
            'team_name': 'Test Team',
            'opponent': 'Other Team',
            'match_time': '2025-12-26T14:30:00Z',  # 14:30 UTC
            'injuries': [],
            'source': 'FotMob'
        }
        
        with patch.object(provider, 'get_fixture_details', return_value=mock_result):
            # Expected match at 14:00 UTC (30 min difference)
            expected_time = datetime(2025, 12, 26, 14, 0, 0, tzinfo=timezone.utc)
            
            result = provider.get_match_details(
                team_name='Test Team',
                home_team='Test Team',
                away_team='Other Team',
                match_date=expected_time
            )
            
            # Should return result because 30min < 4h tolerance
            assert result is not None, "Match should be accepted when kickoff differs by <4 hours"
    
    def test_naive_datetime_handling(self):
        """
        Test that naive datetime (without timezone) is handled correctly
        by assuming UTC.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_fixture_details
        mock_result = {
            'team_id': 12345,
            'team_name': 'Test Team',
            'opponent': 'Other Team',
            'match_time': '2025-12-26T14:00:00',  # No timezone (naive)
            'injuries': [],
            'source': 'FotMob'
        }
        
        with patch.object(provider, 'get_fixture_details', return_value=mock_result):
            # Naive datetime (no tzinfo)
            expected_time = datetime(2025, 12, 26, 14, 0, 0)  # No timezone
            
            result = provider.get_match_details(
                team_name='Test Team',
                home_team='Test Team',
                away_team='Other Team',
                match_date=expected_time
            )
            
            # Should work - both treated as UTC
            assert result is not None, "Naive datetimes should be handled as UTC"
    
    def test_string_date_input(self):
        """
        Test that ISO string date input works correctly.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        mock_result = {
            'team_id': 12345,
            'team_name': 'Test Team',
            'opponent': 'Other Team',
            'match_time': '2025-12-26T14:00:00Z',
            'injuries': [],
            'source': 'FotMob'
        }
        
        with patch.object(provider, 'get_fixture_details', return_value=mock_result):
            # String date input
            result = provider.get_match_details(
                team_name='Test Team',
                home_team='Test Team',
                away_team='Other Team',
                match_date='2025-12-26T14:00:00Z'  # ISO string
            )
            
            assert result is not None, "ISO string date should be parsed correctly"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
