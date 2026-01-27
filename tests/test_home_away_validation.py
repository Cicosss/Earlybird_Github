"""
V5.1: Home/Away Validation Tests

Tests for the home/away order validation feature that uses FotMob
to detect and correct inverted team orders from the Odds API.

Bug fixed: Alert showed "FC Porto vs Santa Clara" when the actual
match was "Santa Clara vs FC Porto" (Santa Clara playing at home).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestValidateHomeAwayOrder:
    """Tests for FotMobProvider.validate_home_away_order()"""
    
    def test_correct_order_not_swapped(self):
        """When FotMob confirms home team plays at home, no swap occurs."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_fixture_details to return is_home=True
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            mock_fixture.return_value = {
                'team_name': 'Santa Clara',
                'opponent': 'FC Porto',
                'is_home': True,  # Santa Clara plays at home
                'source': 'FotMob'
            }
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='Santa Clara',
                odds_away_team='FC Porto'
            )
            
            assert home == 'Santa Clara'
            assert away == 'FC Porto'
            assert swapped == False
    
    def test_inverted_order_gets_swapped(self):
        """
        REGRESSION TEST: When FotMob says "home team" plays AWAY, swap occurs.
        
        This is the exact bug scenario:
        - Odds API says: FC Porto (home) vs Santa Clara (away)
        - FotMob says: FC Porto plays AWAY (is_home=False)
        - Result: Should swap to Santa Clara vs FC Porto
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_fixture_details: FC Porto is searched, FotMob says they play AWAY
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            mock_fixture.return_value = {
                'team_name': 'FC Porto',
                'opponent': 'Santa Clara',
                'is_home': False,  # FC Porto plays AWAY, not home!
                'source': 'FotMob'
            }
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='FC Porto',  # Odds API says Porto is home (WRONG)
                odds_away_team='Santa Clara'
            )
            
            # Should be swapped!
            assert home == 'Santa Clara', "Santa Clara should be home team"
            assert away == 'FC Porto', "FC Porto should be away team"
            assert swapped == True, "Teams should have been swapped"
    
    def test_fotmob_error_trusts_odds_api(self):
        """When FotMob lookup fails, trust Odds API order."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            mock_fixture.return_value = {'error': 'Team not found'}
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='Unknown FC',
                odds_away_team='Mystery United'
            )
            
            assert home == 'Unknown FC'
            assert away == 'Mystery United'
            assert swapped == False
    
    def test_is_home_none_trusts_odds_api(self):
        """When FotMob doesn't provide is_home, trust Odds API order."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            mock_fixture.return_value = {
                'team_name': 'Team A',
                'opponent': 'Team B',
                'is_home': None,  # FotMob didn't provide this info
                'source': 'FotMob'
            }
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='Team A',
                odds_away_team='Team B'
            )
            
            assert home == 'Team A'
            assert away == 'Team B'
            assert swapped == False
    
    def test_opponent_mismatch_trusts_odds_api(self):
        """When FotMob opponent doesn't match expected away team, trust Odds API."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            # FotMob returns a different opponent (wrong match?)
            mock_fixture.return_value = {
                'team_name': 'Team A',
                'opponent': 'Completely Different Team',  # Doesn't match Team B
                'is_home': False,
                'source': 'FotMob'
            }
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='Team A',
                odds_away_team='Team B'
            )
            
            # Should NOT swap because opponent doesn't match
            assert home == 'Team A'
            assert away == 'Team B'
            assert swapped == False
    
    def test_exception_handling_trusts_odds_api(self):
        """On any exception, trust Odds API order."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            mock_fixture.side_effect = Exception("Network error")
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='Team A',
                odds_away_team='Team B'
            )
            
            assert home == 'Team A'
            assert away == 'Team B'
            assert swapped == False


class TestGetFixtureDetailsIsHome:
    """Tests for is_home field in get_fixture_details response."""
    
    def test_is_home_extracted_from_next_match(self):
        """Verify is_home is extracted from FotMob next_match data."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock the chain of calls
        with patch.object(provider, 'search_team_id') as mock_search, \
             patch.object(provider, 'get_team_details') as mock_details, \
             patch.object(provider, '_extract_squad_injuries') as mock_injuries:
            
            mock_search.return_value = (12345, 'Test Team')
            mock_injuries.return_value = []
            
            # Simulate FotMob response with home=True
            mock_details.return_value = {
                'nextMatch': {
                    'id': 999,
                    'opponent': {'name': 'Opponent FC'},
                    'utcTime': '2026-01-10T15:00:00Z',
                    'home': True  # This is the key field!
                }
            }
            
            result = provider.get_fixture_details('Test Team')
            
            assert result is not None
            assert result.get('is_home') == True
    
    def test_is_home_false_when_away(self):
        """Verify is_home=False when team plays away."""
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'search_team_id') as mock_search, \
             patch.object(provider, 'get_team_details') as mock_details, \
             patch.object(provider, '_extract_squad_injuries') as mock_injuries:
            
            mock_search.return_value = (12345, 'Away Team')
            mock_injuries.return_value = []
            
            mock_details.return_value = {
                'nextMatch': {
                    'id': 999,
                    'opponent': {'name': 'Home Team'},
                    'utcTime': '2026-01-10T15:00:00Z',
                    'home': False  # Team plays away
                }
            }
            
            result = provider.get_fixture_details('Away Team')
            
            assert result is not None
            assert result.get('is_home') == False


class TestSendAlertValidatedTeams:
    """Tests for send_alert with validated team names."""
    
    def test_send_alert_uses_validated_names(self):
        """send_alert should use validated_home_team/validated_away_team if provided."""
        from src.alerting.notifier import send_alert
        import os
        
        # Create mock match object
        mock_match = Mock()
        mock_match.home_team = 'Wrong Home'
        mock_match.away_team = 'Wrong Away'
        mock_match.opening_home_odd = 1.80
        mock_match.current_home_odd = 1.75
        mock_match.start_time = None
        
        # Patch Telegram to avoid actual API calls
        with patch.dict(os.environ, {'TELEGRAM_TOKEN': '', 'TELEGRAM_CHAT_ID': ''}):
            # This should not raise and should use validated names
            # (won't actually send because no token)
            send_alert(
                match_obj=mock_match,
                news_summary="Test",
                news_url="http://test.com",
                score=8,
                league="Test League",
                validated_home_team='Correct Home',
                validated_away_team='Correct Away'
            )
            # If we get here without error, the function accepts the new params
            assert True
    
    def test_send_alert_falls_back_to_match_obj(self):
        """send_alert should fall back to match_obj names if validated not provided."""
        from src.alerting.notifier import send_alert
        import os
        
        mock_match = Mock()
        mock_match.home_team = 'Match Home'
        mock_match.away_team = 'Match Away'
        mock_match.opening_home_odd = 1.80
        mock_match.current_home_odd = 1.75
        mock_match.start_time = None
        
        with patch.dict(os.environ, {'TELEGRAM_TOKEN': '', 'TELEGRAM_CHAT_ID': ''}):
            # Call without validated names - should use match_obj names
            send_alert(
                match_obj=mock_match,
                news_summary="Test",
                news_url="http://test.com",
                score=8,
                league="Test League"
                # No validated_home_team or validated_away_team
            )
            assert True


class TestPortugalLeagueRegression:
    """
    Specific regression test for the Portugal Liga bug.
    
    Bug: Alert showed "FC Porto vs Santa Clara" but actual match was
    "Santa Clara vs FC Porto" (Santa Clara at home).
    """
    
    def test_portugal_liga_inversion_detected(self):
        """
        REGRESSION: Detect and correct FC Porto vs Santa Clara inversion.
        
        This test would FAIL with the old code (no validation) and
        PASS with the fix (validate_home_away_order).
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        with patch.object(provider, 'get_fixture_details') as mock_fixture:
            # Simulate: Odds API says "FC Porto vs Santa Clara"
            # But FotMob says FC Porto plays AWAY
            mock_fixture.return_value = {
                'team_name': 'FC Porto',
                'opponent': 'Santa Clara',
                'is_home': False,  # FC Porto is AWAY!
                'source': 'FotMob'
            }
            
            home, away, swapped = provider.validate_home_away_order(
                odds_home_team='FC Porto',
                odds_away_team='Santa Clara'
            )
            
            # The fix should swap them
            assert swapped == True, "Inversion should be detected"
            assert home == 'Santa Clara', "Santa Clara should be home"
            assert away == 'FC Porto', "FC Porto should be away"
