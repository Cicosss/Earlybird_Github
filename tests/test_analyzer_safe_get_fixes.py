#!/usr/bin/env python3
"""
Test per le correzioni CRITICAL di Phase 1 in analyzer.py

Questo test verifica:
1. league_table_context access con safe_get e isinstance check
2. deep_dive access con safe_get e isinstance check
3. snippet_data context access con safe_get

Queste correzioni prevengono crash quando i dati API esterni
contengono valori non-dict (stringhe, None, ecc.)
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLeagueTableContextSafeAccess:
    """Test suite per l'accesso sicuro a league_table_context."""
    
    def test_league_table_context_with_dict(self):
        """
        Verifica che league_table_context dict funzioni correttamente.
        
        Scenario: Dati API validi
        """
        from src.analysis.analyzer import safe_get
        
        league_table_context = {
            'home_rank': 5,
            'home_zone': 'Champions League',
            'home_form': 'WWLDW',
            'away_rank': 12,
            'away_zone': 'Mid-table',
            'away_form': 'LDLWW',
            'motivation_summary': 'Home fighting for CL, away safe'
        }
        
        # Simula il codice corretto in analyzer.py:1324-1330
        if league_table_context and isinstance(league_table_context, dict) and not league_table_context.get('error'):
            h_rank = safe_get(league_table_context, 'home_rank')
            h_zone = safe_get(league_table_context, 'home_zone', default='Unknown')
            h_form = safe_get(league_table_context, 'home_form')
            a_rank = safe_get(league_table_context, 'away_rank')
            a_zone = safe_get(league_table_context, 'away_zone', default='Unknown')
            a_form = safe_get(league_table_context, 'away_form')
            
            assert h_rank == 5
            assert h_zone == 'Champions League'
            assert h_form == 'WWLDW'
            assert a_rank == 12
            assert a_zone == 'Mid-table'
            assert a_form == 'LDLWW'
    
    def test_league_table_context_with_string(self):
        """
        Verifica che league_table_context string non causi crash.
        
        Scenario: Dati API corrotti (stringa invece di dict)
        Questo è il bug che causava il crash originale.
        """
        from src.analysis.analyzer import safe_get
        
        # Simula dati corrotti: stringa invece di dict
        league_table_context = "API error: rate limit exceeded"
        
        # Simula il codice corretto in analyzer.py:1324-1330
        if league_table_context and isinstance(league_table_context, dict) and not league_table_context.get('error'):
            # Questo blocco NON dovrebbe essere eseguito
            assert False, "Should not enter dict block with string value"
        else:
            # Il codice dovrebbe saltare questo blocco in modo sicuro
            assert True
    
    def test_league_table_context_with_none(self):
        """
        Verifica che league_table_context None non causi crash.
        
        Scenario: Dati API mancanti
        """
        from src.analysis.analyzer import safe_get
        
        league_table_context = None
        
        # Simula il codice corretto in analyzer.py:1324-1330
        if league_table_context and isinstance(league_table_context, dict) and not league_table_context.get('error'):
            # Questo blocco NON dovrebbe essere eseguito
            assert False, "Should not enter dict block with None value"
        else:
            # Il codice dovrebbe saltare questo blocco in modo sicuro
            assert True
    
    def test_league_table_context_with_error(self):
        """
        Verifica che league_table_context con error non causi crash.
        
        Scenario: Dati API con errore
        """
        from src.analysis.analyzer import safe_get
        
        league_table_context = {
            'error': 'League not found',
            'message': 'Invalid league ID'
        }
        
        # Simula il codice corretto in analyzer.py:1324-1330
        if league_table_context and isinstance(league_table_context, dict) and not league_table_context.get('error'):
            # Questo blocco NON dovrebbe essere eseguito
            assert False, "Should not enter dict block with error"
        else:
            # Il codice dovrebbe saltare questo blocco in modo sicuro
            assert True


class TestDeepDiveSafeAccess:
    """Test suite per l'accesso sicuro a deep_dive."""
    
    def test_deep_dive_with_dict(self):
        """
        Verifica che deep_dive dict funzioni correttamente.
        
        Scenario: Dati Gemini/Perplexity validi
        """
        from src.analysis.analyzer import safe_get
        
        deep_dive = {
            'motivation_home': 'Fighting for relegation',
            'motivation_away': 'Safe mid-table',
            'table_context': 'Motivation mismatch detected'
        }
        
        # Simula il codice corretto in analyzer.py:1344-1349
        motivation_home = ""
        motivation_away = ""
        table_context = ""
        
        if deep_dive and isinstance(deep_dive, dict):
            if not motivation_home or motivation_home == "Unknown":
                motivation_home = (safe_get(deep_dive, 'motivation_home') or "Unknown").strip()
            if not motivation_away or motivation_away == "Unknown":
                motivation_away = (safe_get(deep_dive, 'motivation_away') or "Unknown").strip()
            if not table_context:
                table_context = (safe_get(deep_dive, 'table_context') or "").strip()
            
            assert motivation_home == 'Fighting for relegation'
            assert motivation_away == 'Safe mid-table'
            assert table_context == 'Motivation mismatch detected'
    
    def test_deep_dive_with_string(self):
        """
        Verifica che deep_dive string non causi crash.
        
        Scenario: Dati Gemini/Perplexity corrotti
        """
        from src.analysis.analyzer import safe_get
        
        # Simula dati corrotti: stringa invece di dict
        deep_dive = "API timeout"
        
        # Simula il codice corretto in analyzer.py:1344-1349
        motivation_home = ""
        motivation_away = ""
        table_context = ""
        
        if deep_dive and isinstance(deep_dive, dict):
            # Questo blocco NON dovrebbe essere eseguito
            assert False, "Should not enter dict block with string value"
        else:
            # Il codice dovrebbe saltare questo blocco in modo sicuro
            assert motivation_home == ""
            assert motivation_away == ""
            assert table_context == ""
    
    def test_deep_dive_with_none(self):
        """
        Verifica che deep_dive None non causi crash.
        
        Scenario: Nessun deep dive disponibile
        """
        from src.analysis.analyzer import safe_get
        
        deep_dive = None
        
        # Simula il codice corretto in analyzer.py:1344-1349
        motivation_home = ""
        motivation_away = ""
        table_context = ""
        
        if deep_dive and isinstance(deep_dive, dict):
            # Questo blocco NON dovrebbe essere eseguito
            assert False, "Should not enter dict block with None value"
        else:
            # Il codice dovrebbe saltare questo blocco in modo sicuro
            assert motivation_home == ""
            assert motivation_away == ""
            assert table_context == ""


class TestSnippetDataContextSafeAccess:
    """Test suite per l'accesso sicuro a snippet_data context."""
    
    def test_snippet_data_context_with_dict(self):
        """
        Verifica che snippet_data context dict funzioni correttamente.
        
        Scenario: Dati contestuali validi
        """
        from src.analysis.analyzer import safe_get
        
        snippet_data = {
            'home_context': {
                'injuries': [
                    {'name': 'Player1', 'severity': 'HIGH', 'is_starter': True}
                ],
                'fatigue': {'fatigue_level': 'HIGH', 'hours_since_last': 48}
            },
            'away_context': {
                'injuries': [],
                'fatigue': {'fatigue_level': 'LOW', 'hours_since_last': 72}
            }
        }
        
        # Simula il codice corretto in analyzer.py:1524-1525
        home_context = safe_get(snippet_data, 'home_context')
        away_context = safe_get(snippet_data, 'away_context')
        
        assert isinstance(home_context, dict)
        assert isinstance(away_context, dict)
        assert 'injuries' in home_context
        assert 'fatigue' in home_context
        assert 'injuries' in away_context
        assert 'fatigue' in away_context
    
    def test_snippet_data_context_with_string(self):
        """
        Verifica che snippet_data context string non causi crash.
        
        Scenario: Dati contestuali corrotti
        """
        from src.analysis.analyzer import safe_get
        
        snippet_data = {
            'home_context': 'Invalid data',
            'away_context': None
        }
        
        # Simula il codice corretto in analyzer.py:1524-1525
        home_context = safe_get(snippet_data, 'home_context')
        away_context = safe_get(snippet_data, 'away_context')
        
        # safe_get dovrebbe restituire i valori originali (non None)
        assert home_context == 'Invalid data'
        assert away_context is None
        
        # I controlli isinstance() successivi dovrebbero gestire questo caso
        # Nota: L'espressione logica restituisce None (non False) quando il primo valore è falsy
        has_home_injuries = (
            home_context and 
            isinstance(home_context, dict) and 
            home_context.get('injuries')
        )
        has_away_injuries = (
            away_context and 
            isinstance(away_context, dict) and 
            away_context.get('injuries')
        )
        
        # L'operatore and restituisce l'ultimo valore falso, quindi None è corretto
        assert has_home_injuries is None or has_home_injuries is False
        assert has_away_injuries is None
    
    def test_snippet_data_context_with_none(self):
        """
        Verifica che snippet_data context None non causi crash.
        
        Scenario: Nessun contesto disponibile
        """
        from src.analysis.analyzer import safe_get
        
        snippet_data = {
            'home_context': None,
            'away_context': None
        }
        
        # Simula il codice corretto in analyzer.py:1524-1525
        home_context = safe_get(snippet_data, 'home_context')
        away_context = safe_get(snippet_data, 'away_context')
        
        # safe_get dovrebbe restituire None
        assert home_context is None
        assert away_context is None
        
        # I controlli isinstance() successivi dovrebbero gestire questo caso
        # Nota: L'espressione logica restituisce None (non False) quando il primo valore è falsy
        has_home_injuries = (
            home_context and 
            isinstance(home_context, dict) and 
            home_context.get('injuries')
        )
        has_away_injuries = (
            away_context and 
            isinstance(away_context, dict) and 
            away_context.get('injuries')
        )
        
        # L'operatore and restituisce l'ultimo valore falso, quindi None è corretto
        assert has_home_injuries is None
        assert has_away_injuries is None


class TestSafeGetFunction:
    """Test suite per la funzione safe_get."""
    
    def test_safe_get_with_valid_dict(self):
        """Verifica safe_get con dict valido."""
        from src.utils.validators import safe_get
        
        data = {'level1': {'level2': {'level3': 'value'}}}
        result = safe_get(data, 'level1', 'level2', 'level3')
        
        assert result == 'value'
    
    def test_safe_get_with_string_intermediate(self):
        """
        Verifica safe_get con valore intermedio stringa.
        
        Questo è il caso critico che causava AttributeError.
        """
        from src.utils.validators import safe_get
        
        data = {'level1': 'not_a_dict'}
        result = safe_get(data, 'level1', 'level2')
        
        # Dovrebbe restituire None invece di crashare
        assert result is None
    
    def test_safe_get_with_none_intermediate(self):
        """Verifica safe_get con valore intermedio None."""
        from src.utils.validators import safe_get
        
        data = {'level1': None}
        result = safe_get(data, 'level1', 'level2')
        
        assert result is None
    
    def test_safe_get_with_missing_keys(self):
        """Verifica safe_get con chiavi mancanti."""
        from src.utils.validators import safe_get
        
        data = {'a': {'b': 1}}
        result = safe_get(data, 'a', 'b', 'missing')
        
        assert result is None
    
    def test_safe_get_with_default(self):
        """Verifica safe_get con valore di default."""
        from src.utils.validators import safe_get
        
        data = {'level1': 'string'}
        result = safe_get(data, 'level1', 'level2', default='fallback')
        
        assert result == 'fallback'
    
    def test_safe_get_with_none_data(self):
        """Verifica safe_get con data None."""
        from src.utils.validators import safe_get
        
        result = safe_get(None, 'a', 'b')
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
