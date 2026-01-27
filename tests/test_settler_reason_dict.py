"""
Test di regressione per il bug del settler V4.4

Bug: settler.py assumeva che match_status['reason'] fosse una stringa,
ma FotMob restituisce un dict {'short': 'FT', 'long': 'Full-Time'}.

Questo test verifica che il fix gestisca correttamente entrambi i formati.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


def test_reason_as_dict():
    """Test che reason come dict non causi errore."""
    from src.analysis.settler import get_match_result
    
    # Mock FotMob response con reason come dict (formato reale)
    mock_team_data = {
        'fixtures': {
            'allFixtures': {
                'fixtures': [{
                    'home': {'name': 'Team A', 'score': 2},
                    'away': {'name': 'Team B', 'score': 1},
                    'id': 12345,
                    'status': {
                        'cancelled': False,
                        'reason': {'short': 'FT', 'long': 'Full-Time'}  # Dict format
                    }
                }]
            }
        }
    }
    
    with patch('src.analysis.settler.get_data_provider') as mock_provider:
        mock_fotmob = MagicMock()
        mock_fotmob.search_team_id.return_value = (123, 'Team A')
        mock_fotmob.get_team_details.return_value = mock_team_data
        mock_provider.return_value = mock_fotmob
        
        result = get_match_result('Team A', 'Team B', datetime.now())
        
        assert result is not None
        assert result['home_score'] == 2
        assert result['away_score'] == 1
        assert result['status'] == 'FINISHED'


def test_reason_as_string():
    """Test che reason come stringa funzioni ancora (backward compat)."""
    from src.analysis.settler import get_match_result
    
    # Mock con reason come stringa (formato legacy)
    mock_team_data = {
        'fixtures': {
            'allFixtures': {
                'fixtures': [{
                    'home': {'name': 'Team A', 'score': 0},
                    'away': {'name': 'Team B', 'score': 0},
                    'id': 12345,
                    'status': {
                        'cancelled': True,
                        'reason': 'postponed due to weather'  # String format
                    }
                }]
            }
        }
    }
    
    with patch('src.analysis.settler.get_data_provider') as mock_provider:
        mock_fotmob = MagicMock()
        mock_fotmob.search_team_id.return_value = (123, 'Team A')
        mock_fotmob.get_team_details.return_value = mock_team_data
        mock_provider.return_value = mock_fotmob
        
        result = get_match_result('Team A', 'Team B', datetime.now())
        
        assert result is not None
        assert result['status'] == 'POSTPONED'


def test_reason_as_none():
    """Test che reason None non causi errore."""
    from src.analysis.settler import get_match_result
    
    mock_team_data = {
        'fixtures': {
            'allFixtures': {
                'fixtures': [{
                    'home': {'name': 'Team A', 'score': 1},
                    'away': {'name': 'Team B', 'score': 1},
                    'id': 12345,
                    'status': {
                        'cancelled': False,
                        'reason': None  # None
                    }
                }]
            }
        }
    }
    
    with patch('src.analysis.settler.get_data_provider') as mock_provider:
        mock_fotmob = MagicMock()
        mock_fotmob.search_team_id.return_value = (123, 'Team A')
        mock_fotmob.get_team_details.return_value = mock_team_data
        mock_provider.return_value = mock_fotmob
        
        result = get_match_result('Team A', 'Team B', datetime.now())
        
        assert result is not None
        assert result['home_score'] == 1
        assert result['away_score'] == 1


def test_fixtures_key_not_previous_matches():
    """
    Test di regressione per il bug 'previousMatches'.
    
    Bug originale: settler cercava in 'previousMatches' che non esiste.
    Fix: ora cerca in 'fixtures'.
    """
    from src.analysis.settler import get_match_result
    
    # Mock con SOLO 'fixtures', senza 'previousMatches'
    mock_team_data = {
        'fixtures': {
            'allFixtures': {
                'fixtures': [{  # Questo è il campo corretto
                    'home': {'name': 'Dundee United', 'score': 2},
                    'away': {'name': 'Celtic', 'score': 1},
                    'id': 4818816,
                    'status': {
                        'cancelled': False,
                        'reason': {'short': 'FT', 'long': 'Full-Time'}
                    }
                }],
                'nextMatch': {},
                'lastMatch': {}
                # NOTA: 'previousMatches' NON esiste in FotMob API
            }
        }
    }
    
    with patch('src.analysis.settler.get_data_provider') as mock_provider:
        mock_fotmob = MagicMock()
        mock_fotmob.search_team_id.return_value = (9938, 'Dundee United')
        mock_fotmob.get_team_details.return_value = mock_team_data
        mock_provider.return_value = mock_fotmob
        
        result = get_match_result('Dundee United', 'Celtic', datetime.now())
        
        # Prima del fix, questo restituiva None
        # Dopo il fix, deve trovare il match
        assert result is not None, "Fix 'fixtures' vs 'previousMatches' non funziona!"
        assert result['home_score'] == 2
        assert result['away_score'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
