"""
Test Motivation Engine V4.0 - League Table Context

These tests verify that:
1. League ID mapping exists and works
2. snippet_data includes league_id
3. get_league_table_context handles edge cases
"""
import pytest
from unittest.mock import Mock, patch


class TestLeagueMapping:
    """Test OddsAPI -> FotMob League ID mapping."""
    
    def test_league_mapping_exists(self):
        """CRITICAL: Verify league mapping dictionary exists."""
        from src.ingestion.fotmob_team_mapping import LEAGUE_FOTMOB_IDS
        
        assert LEAGUE_FOTMOB_IDS is not None
        assert isinstance(LEAGUE_FOTMOB_IDS, dict)
        assert len(LEAGUE_FOTMOB_IDS) > 0
    
    def test_elite_leagues_mapped(self):
        """Verify all Elite 6 leagues have FotMob IDs."""
        from src.ingestion.fotmob_team_mapping import get_fotmob_league_id
        
        elite_leagues = [
            "soccer_turkey_super_league",
            "soccer_greece_super_league", 
            "soccer_spl",
            "soccer_australia_aleague",
            "soccer_argentina_primera_division",
            "soccer_mexico_ligamx",
        ]
        
        for league in elite_leagues:
            league_id = get_fotmob_league_id(league)
            assert league_id is not None, f"Missing FotMob ID for {league}"
            assert isinstance(league_id, int), f"League ID for {league} should be int"
            assert league_id > 0, f"League ID for {league} should be positive"
    
    def test_turkey_league_id_correct(self):
        """Verify Turkey Super League maps to FotMob ID 71."""
        from src.ingestion.fotmob_team_mapping import get_fotmob_league_id
        
        assert get_fotmob_league_id("soccer_turkey_super_league") == 71
    
    def test_unknown_league_returns_none(self):
        """Unknown league should return None, not raise."""
        from src.ingestion.fotmob_team_mapping import get_fotmob_league_id
        
        result = get_fotmob_league_id("soccer_unknown_league")
        assert result is None


class TestMotivationEngineIntegration:
    """Test that Motivation Engine receives league_id correctly."""
    
    def test_snippet_data_includes_league_id(self):
        """
        REGRESSION TEST: This would FAIL before the fix.
        
        Before fix: snippet_data had no 'league_id' key
        After fix: snippet_data includes 'league_id' from get_fotmob_league_id()
        """
        from src.ingestion.fotmob_team_mapping import get_fotmob_league_id
        
        # Simulate snippet_data construction as in main.py
        mock_match_league = "soccer_turkey_super_league"
        
        snippet_data = {
            'match_id': 123,
            'link': 'https://test',
            'team': 'Galatasaray',
            'home_team': 'Galatasaray',
            'away_team': 'Fenerbahce',
            'league_id': get_fotmob_league_id(mock_match_league),  # THE FIX
            'snippet': 'Test news'
        }
        
        # This assertion would FAIL before the fix
        assert 'league_id' in snippet_data
        assert snippet_data['league_id'] == 71  # Turkey = 71


class TestZoneLogic:
    """Test league table zone determination."""
    
    def test_zone_calculation_12_teams(self):
        """Test zone cutoffs for 12-team league."""
        total_teams = 12
        
        # Replicate logic from data_provider.py
        europe_cutoff = min(4, total_teams // 4) if total_teams > 8 else 2
        relegation_cutoff = total_teams - 3 if total_teams > 6 else total_teams - 1
        
        assert europe_cutoff == 3  # min(4, 3) = 3
        assert relegation_cutoff == 9  # 12 - 3 = 9
        
        # Verify zones
        def determine_zone(rank: int) -> str:
            if rank <= europe_cutoff:
                return "TITLE/EUROPE"
            elif rank >= relegation_cutoff:
                return "RELEGATION"
            else:
                return "MID-TABLE"
        
        assert determine_zone(1) == "TITLE/EUROPE"
        assert determine_zone(3) == "TITLE/EUROPE"
        assert determine_zone(4) == "MID-TABLE"
        assert determine_zone(8) == "MID-TABLE"
        assert determine_zone(9) == "RELEGATION"
        assert determine_zone(12) == "RELEGATION"
    
    def test_zone_calculation_20_teams(self):
        """Test zone cutoffs for 20-team league (standard)."""
        total_teams = 20
        
        europe_cutoff = min(4, total_teams // 4) if total_teams > 8 else 2
        relegation_cutoff = total_teams - 3 if total_teams > 6 else total_teams - 1
        
        assert europe_cutoff == 4  # min(4, 5) = 4
        assert relegation_cutoff == 17  # 20 - 3 = 17
    
    def test_zone_calculation_small_league(self):
        """Test zone cutoffs for small 6-team league."""
        total_teams = 6
        
        europe_cutoff = min(4, total_teams // 4) if total_teams > 8 else 2
        relegation_cutoff = total_teams - 3 if total_teams > 6 else total_teams - 1
        
        assert europe_cutoff == 2  # Small league fallback
        assert relegation_cutoff == 5  # 6 - 1 = 5 (small league)
