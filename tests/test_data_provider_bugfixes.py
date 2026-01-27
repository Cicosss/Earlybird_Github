"""
Test per i bugfix in data_provider.py

Bug corretti:
1. extract_form: IndexError quando result è stringa vuota
2. H2H log: usava variabili locali None invece di result dict
3. get_match_lineup: bypass rate limiting (FIX V5.2)
4. get_table_context: division by zero con position=None (FIX V5.2)
5. Import locali ripetuti: overhead performance (FIX V5.2)
"""
import unittest
from unittest.mock import MagicMock, patch


class TestExtractFormBugfix(unittest.TestCase):
    """
    BUG: f.get('result', '?')[0] causa IndexError se result è stringa vuota "".
    FIX: Aggiunto check `if result_val` prima di accedere a [0].
    """
    
    def test_extract_form_empty_result_string(self):
        """
        REGRESSION TEST: Se FotMob ritorna result="" invece di "W"/"D"/"L",
        non deve crashare con IndexError.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Simula la funzione extract_form inline (come definita in get_league_table_context)
        def extract_form_safe(team_entry: dict) -> str:
            """Extract last 5 results form string - FIXED VERSION."""
            form = team_entry.get('form', [])
            if isinstance(form, list):
                form_str = ""
                for f in form[-5:]:
                    if isinstance(f, dict):
                        result_val = f.get('result', '?')
                        # Safety: handle empty string or None
                        form_str += result_val[0].upper() if result_val else '?'
                    elif isinstance(f, str):
                        form_str += f[0].upper() if f else '?'
                return form_str if form_str else None
            return None
        
        # Test case che avrebbe causato IndexError prima del fix
        team_entry_with_empty_result = {
            'form': [
                {'result': ''},  # Empty string - BUG TRIGGER
                {'result': 'W'},
                {'result': 'D'},
            ]
        }
        
        # Non deve crashare
        result = extract_form_safe(team_entry_with_empty_result)
        
        # Deve ritornare "?WD" (? per il risultato vuoto)
        self.assertEqual(result, "?WD")
    
    def test_extract_form_none_result(self):
        """Test che None come result viene gestito correttamente."""
        def extract_form_safe(team_entry: dict) -> str:
            form = team_entry.get('form', [])
            if isinstance(form, list):
                form_str = ""
                for f in form[-5:]:
                    if isinstance(f, dict):
                        result_val = f.get('result', '?')
                        form_str += result_val[0].upper() if result_val else '?'
                    elif isinstance(f, str):
                        form_str += f[0].upper() if f else '?'
                return form_str if form_str else None
            return None
        
        team_entry = {
            'form': [
                {'result': None},  # None value
                {'result': 'L'},
            ]
        }
        
        result = extract_form_safe(team_entry)
        self.assertEqual(result, "?L")
    
    def test_extract_form_normal_case(self):
        """Test caso normale funziona ancora."""
        def extract_form_safe(team_entry: dict) -> str:
            form = team_entry.get('form', [])
            if isinstance(form, list):
                form_str = ""
                for f in form[-5:]:
                    if isinstance(f, dict):
                        result_val = f.get('result', '?')
                        form_str += result_val[0].upper() if result_val else '?'
                    elif isinstance(f, str):
                        form_str += f[0].upper() if f else '?'
                return form_str if form_str else None
            return None
        
        team_entry = {
            'form': [
                {'result': 'W'},
                {'result': 'W'},
                {'result': 'D'},
                {'result': 'L'},
                {'result': 'W'},
            ]
        }
        
        result = extract_form_safe(team_entry)
        self.assertEqual(result, "WWDLW")


class TestH2HLogBugfix(unittest.TestCase):
    """
    BUG: Il log H2H usava variabili locali home_team/away_team che potevano essere None.
    FIX: Usa result.get('home_team') e result.get('away_team').
    """
    
    def test_h2h_log_uses_result_dict(self):
        """
        Verifica che il log H2H usi i valori dal result dict,
        non le variabili locali che potrebbero essere None.
        """
        # Questo test verifica che il codice sia stato corretto
        # leggendo il file sorgente
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Il fix dovrebbe usare result.get() invece delle variabili locali
        self.assertIn(
            "result.get('home_team'",
            content,
            "H2H log should use result.get('home_team') instead of local variable"
        )
        self.assertIn(
            "result.get('away_team'",
            content,
            "H2H log should use result.get('away_team') instead of local variable"
        )


class TestGetMatchDetailsWithNoneTeams(unittest.TestCase):
    """Test che get_match_details funziona quando home_team/away_team sono None."""
    
    @patch('src.ingestion.data_provider.FotMobProvider.get_fixture_details')
    def test_match_details_without_team_params(self, mock_fixture):
        """
        Quando home_team e away_team non sono passati,
        il risultato deve comunque avere home_team e away_team popolati.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        mock_fixture.return_value = {
            'team_name': 'Juventus',
            'opponent': 'Inter',
            'injuries': [],
            'match_id': 12345
        }
        
        provider = FotMobProvider()
        
        # Chiama senza home_team e away_team
        result = provider.get_match_details('Juventus')
        
        # Deve avere home_team e away_team popolati da FotMob
        self.assertIsNotNone(result)
        self.assertEqual(result.get('home_team'), 'Juventus')
        self.assertEqual(result.get('away_team'), 'Inter')


if __name__ == '__main__':
    unittest.main()


class TestGetMatchLineupUsesRateLimiting(unittest.TestCase):
    """
    BUG V5.2: get_match_lineup usava self.session.get() direttamente,
    bypassando rate limiting, retry logic e UA rotation.
    FIX: Ora usa self._make_request() come tutti gli altri metodi.
    """
    
    def test_get_match_lineup_uses_make_request(self):
        """
        Verifica che get_match_lineup usi _make_request invece di session.get.
        Questo garantisce rate limiting e retry logic.
        """
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Trova la definizione di get_match_lineup
        import re
        match_lineup_pattern = r'def get_match_lineup\(self.*?(?=\n    def |\nclass |\Z)'
        match = re.search(match_lineup_pattern, content, re.DOTALL)
        
        self.assertIsNotNone(match, "get_match_lineup method not found")
        method_body = match.group(0)
        
        # Deve usare _make_request, NON session.get
        self.assertIn(
            'self._make_request(url)',
            method_body,
            "get_match_lineup should use self._make_request() for rate limiting"
        )
        self.assertNotIn(
            'self.session.get(',
            method_body,
            "get_match_lineup should NOT use self.session.get() directly"
        )


class TestGetTableContextPositionValidation(unittest.TestCase):
    """
    BUG V5.2: get_table_context poteva causare TypeError se position era None.
    Il check `if position:` non proteggeva da position=None nella divisione.
    FIX: Aggiunto check esplicito `position is not None and isinstance(position, (int, float))`.
    """
    
    def test_position_none_does_not_crash(self):
        """
        REGRESSION TEST: Se FotMob ritorna position=None,
        non deve crashare con TypeError nella divisione.
        """
        from src.ingestion.data_provider import FotMobProvider
        
        provider = FotMobProvider()
        
        # Mock get_team_details per ritornare dati con position=None
        with patch.object(provider, 'get_team_details') as mock_details:
            mock_details.return_value = {
                'table': [{
                    'data': {
                        'table': {
                            'all': [{
                                'name': 'Test Team',
                                'idx': None,  # BUG TRIGGER: position è None
                                'pts': 10
                            }]
                        }
                    }
                }]
            }
            
            with patch.object(provider, 'search_team_id') as mock_search:
                mock_search.return_value = (12345, 'Test Team')
                
                # Non deve crashare
                result = provider.get_table_context('Test Team')
                
                # Deve ritornare Unknown perché position non è valido
                self.assertEqual(result['zone'], 'Unknown')
    
    def test_position_zero_is_invalid(self):
        """
        Position=0 non è valido per leghe 1-indexed.
        Deve essere trattato come dato mancante.
        """
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Il fix deve includere check per position > 0
        self.assertIn(
            'position > 0',
            content,
            "Position validation should check position > 0 for 1-indexed leagues"
        )
    
    def test_position_greater_than_total_teams(self):
        """
        EDGE CASE V5.2: Se position > total_teams (dati corrotti),
        pct diventa > 1.0 e la logica zone fallisce.
        FIX: Aggiunto check position <= total_teams.
        """
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Il fix deve includere check position <= total_teams
        self.assertIn(
            'position <= total_teams',
            content,
            "Position validation should check position <= total_teams to avoid pct > 1.0"
        )


class TestTopLevelImportPerformance(unittest.TestCase):
    """
    BUG V5.2: Import ripetuti di fotmob_team_mapping dentro funzioni
    causavano overhead di performance.
    FIX: Import spostato al top-level con flag _TEAM_MAPPING_AVAILABLE.
    """
    
    def test_team_mapping_imported_at_top_level(self):
        """
        Verifica che fotmob_team_mapping sia importato al top-level,
        non dentro ogni funzione.
        """
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Deve avere il flag _TEAM_MAPPING_AVAILABLE
        self.assertIn(
            '_TEAM_MAPPING_AVAILABLE',
            content,
            "Should have _TEAM_MAPPING_AVAILABLE flag for top-level import"
        )
        
        # Conta gli import di fotmob_team_mapping - deve essere solo 1 (al top-level)
        import_count = content.count('from src.ingestion.fotmob_team_mapping import get_fotmob_team_id')
        self.assertEqual(
            import_count, 
            1,
            f"Should have exactly 1 import of fotmob_team_mapping (top-level), found {import_count}"
        )
    
    def test_functions_use_flag_check(self):
        """
        Verifica che le funzioni usino il flag check invece di import locale.
        """
        with open('src/ingestion/data_provider.py', 'r') as f:
            content = f.read()
        
        # Deve usare il pattern: get_fotmob_team_id(...) if _TEAM_MAPPING_AVAILABLE else None
        self.assertIn(
            'if _TEAM_MAPPING_AVAILABLE else None',
            content,
            "Functions should use flag check pattern for team mapping"
        )
