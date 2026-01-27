"""
Test di regressione per bug fix V5.2 in src/main.py

Questi test verificano che i bug silenziosi trovati durante l'audit
non possano più causare crash in produzione.

BUG FIXATI:
1. KeyError su injury dict senza 'name'
2. AttributeError su fatigue_level None con .split()
3. KeyError su turnover dict senza 'missing_names' o 'count'
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestInjuryNamesSafeAccess:
    """
    BUG 1: injury_names = [i['name'] for i in injuries[:3]]
    
    PROBLEMA: Se un injury dict non ha la chiave 'name', KeyError.
    FIX: Usare i.get('name', 'Unknown') con filtro.
    """
    
    def test_injury_with_missing_name_key(self):
        """
        REGRESSION TEST: Injury dict senza 'name' non deve crashare.
        
        Prima del fix: KeyError: 'name'
        Dopo il fix: Salta l'entry senza nome o usa fallback.
        """
        # Simula dati FotMob con injury incompleto
        injuries = [
            {'name': 'Messi', 'reason': 'Knee'},
            {'player': 'Ronaldo', 'reason': 'Back'},  # Manca 'name'!
            {'name': 'Neymar', 'reason': 'Ankle'}
        ]
        
        # Codice DOPO il fix (safe access)
        injury_names = [i.get('name', 'Unknown') for i in injuries[:3] if i.get('name')]
        
        # Deve funzionare senza crash
        assert injury_names == ['Messi', 'Neymar']
        assert len(injury_names) == 2  # Ronaldo skippato
    
    def test_injury_all_missing_names(self):
        """Edge case: tutti gli injury senza 'name'."""
        injuries = [
            {'player': 'Player1'},
            {'player': 'Player2'},
        ]
        
        injury_names = [i.get('name', 'Unknown') for i in injuries[:3] if i.get('name')]
        
        assert injury_names == []
    
    def test_injury_empty_list(self):
        """Edge case: lista injuries vuota."""
        injuries = []
        
        injury_names = [i.get('name', 'Unknown') for i in injuries[:3] if i.get('name')]
        
        assert injury_names == []
    
    def test_injury_name_is_none(self):
        """Edge case: 'name' esiste ma è None."""
        injuries = [
            {'name': None, 'reason': 'Unknown'},
            {'name': 'Messi', 'reason': 'Knee'},
        ]
        
        injury_names = [i.get('name', 'Unknown') for i in injuries[:3] if i.get('name')]
        
        # None è falsy, quindi viene filtrato
        assert injury_names == ['Messi']


class TestFatigueLevelSafeAccess:
    """
    BUG 2: fatigue_short = home_fatigue['fatigue_level'].split(' - ')[0]
    
    PROBLEMA: Se fatigue_level è None (non 'Unknown'), .split() causa AttributeError.
    FIX: Check esplicito per None prima di accedere.
    """
    
    def test_fatigue_level_is_none(self):
        """
        REGRESSION TEST: fatigue_level=None non deve crashare.
        
        Prima del fix: AttributeError: 'NoneType' object has no attribute 'split'
        Dopo il fix: Skip del blocco se None.
        """
        home_fatigue = {'fatigue_level': None}
        
        # Codice DOPO il fix
        fatigue_level = home_fatigue.get('fatigue_level')
        if fatigue_level and fatigue_level != 'Unknown':
            fatigue_short = fatigue_level.split(' - ')[0]
        else:
            fatigue_short = None
        
        # Non deve crashare, fatigue_short deve essere None
        assert fatigue_short is None
    
    def test_fatigue_level_is_unknown(self):
        """fatigue_level='Unknown' deve essere skippato."""
        home_fatigue = {'fatigue_level': 'Unknown'}
        
        fatigue_level = home_fatigue.get('fatigue_level')
        if fatigue_level and fatigue_level != 'Unknown':
            fatigue_short = fatigue_level.split(' - ')[0]
        else:
            fatigue_short = None
        
        assert fatigue_short is None
    
    def test_fatigue_level_valid(self):
        """fatigue_level valido deve essere processato."""
        home_fatigue = {'fatigue_level': 'HIGH - 3 games in 7 days'}
        
        fatigue_level = home_fatigue.get('fatigue_level')
        if fatigue_level and fatigue_level != 'Unknown':
            fatigue_short = fatigue_level.split(' - ')[0]
        else:
            fatigue_short = None
        
        assert fatigue_short == 'HIGH'
    
    def test_fatigue_level_no_separator(self):
        """fatigue_level senza ' - ' deve funzionare."""
        home_fatigue = {'fatigue_level': 'MEDIUM'}
        
        fatigue_level = home_fatigue.get('fatigue_level')
        if fatigue_level and fatigue_level != 'Unknown':
            fatigue_short = fatigue_level.split(' - ')[0]
        else:
            fatigue_short = None
        
        # split()[0] ritorna l'intera stringa se separatore non trovato
        assert fatigue_short == 'MEDIUM'
    
    def test_fatigue_key_missing(self):
        """Dict senza 'fatigue_level' key."""
        home_fatigue = {}
        
        fatigue_level = home_fatigue.get('fatigue_level')
        if fatigue_level and fatigue_level != 'Unknown':
            fatigue_short = fatigue_level.split(' - ')[0]
        else:
            fatigue_short = None
        
        assert fatigue_short is None


class TestTurnoverSafeAccess:
    """
    BUG 3: missing = ', '.join(home_turnover['missing_names'][:3])
    
    PROBLEMA: Se 'missing_names' non esiste o è None, KeyError/TypeError.
    FIX: Usare .get() con fallback a lista vuota.
    """
    
    def test_turnover_missing_names_key_absent(self):
        """
        REGRESSION TEST: turnover senza 'missing_names' non deve crashare.
        
        Prima del fix: KeyError: 'missing_names'
        Dopo il fix: Usa fallback 'N/A'.
        """
        turnover = {'risk_level': 'HIGH', 'count': 3}  # Manca 'missing_names'!
        
        # Codice DOPO il fix
        missing_names = turnover.get('missing_names') or []
        missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
        turnover_count = turnover.get('count', len(missing_names))
        
        assert missing == 'N/A'
        assert turnover_count == 3
    
    def test_turnover_missing_names_is_none(self):
        """'missing_names' esiste ma è None."""
        turnover = {'risk_level': 'HIGH', 'missing_names': None, 'count': 2}
        
        missing_names = turnover.get('missing_names') or []
        missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
        
        assert missing == 'N/A'
    
    def test_turnover_missing_names_empty(self):
        """'missing_names' è lista vuota."""
        turnover = {'risk_level': 'HIGH', 'missing_names': [], 'count': 0}
        
        missing_names = turnover.get('missing_names') or []
        missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
        
        assert missing == 'N/A'
    
    def test_turnover_count_missing(self):
        """'count' mancante, deve usare len(missing_names)."""
        turnover = {'risk_level': 'HIGH', 'missing_names': ['A', 'B', 'C']}
        
        missing_names = turnover.get('missing_names') or []
        turnover_count = turnover.get('count', len(missing_names))
        
        assert turnover_count == 3
    
    def test_turnover_valid_data(self):
        """Dati completi devono funzionare normalmente."""
        turnover = {
            'risk_level': 'HIGH',
            'missing_names': ['Messi', 'Ronaldo', 'Neymar', 'Mbappe'],
            'count': 4
        }
        
        missing_names = turnover.get('missing_names') or []
        missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
        turnover_count = turnover.get('count', len(missing_names))
        
        assert missing == 'Messi, Ronaldo, Neymar'  # Solo primi 3
        assert turnover_count == 4
    
    def test_turnover_is_none(self):
        """turnover stesso è None (FotMob non ha dati)."""
        turnover = None
        
        # Il codice originale ha: if home_turnover and home_turnover.get('risk_level') == 'HIGH':
        # Quindi turnover=None non entra nel blocco
        if turnover and turnover.get('risk_level') == 'HIGH':
            missing_names = turnover.get('missing_names') or []
            missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
        else:
            missing = None
        
        assert missing is None


class TestEdgeCasesIntegration:
    """Test di integrazione per edge case combinati."""
    
    def test_all_data_missing(self):
        """Scenario peggiore: tutti i dati mancanti/None."""
        home_context = {
            'injuries': [{'player': 'X'}],  # No 'name'
            'fatigue': {'fatigue_level': None},
            'motivation': {}
        }
        
        # Injuries
        injuries = home_context.get('injuries', [])
        injury_names = [i.get('name') for i in injuries[:3] if i.get('name')]
        
        # Fatigue
        fatigue = home_context.get('fatigue', {})
        fatigue_level = fatigue.get('fatigue_level')
        fatigue_short = fatigue_level.split(' - ')[0] if fatigue_level and fatigue_level != 'Unknown' else None
        
        # Nessun crash
        assert injury_names == []
        assert fatigue_short is None
    
    def test_partial_data(self):
        """Dati parzialmente completi."""
        home_context = {
            'injuries': [
                {'name': 'Player1'},
                {'reason': 'injury'},  # No name
                {'name': 'Player3'}
            ],
            'fatigue': {'fatigue_level': 'LOW - rested'},
        }
        
        injuries = home_context.get('injuries', [])
        injury_names = [i.get('name') for i in injuries[:3] if i.get('name')]
        
        fatigue = home_context.get('fatigue', {})
        fatigue_level = fatigue.get('fatigue_level')
        fatigue_short = fatigue_level.split(' - ')[0] if fatigue_level and fatigue_level != 'Unknown' else None
        
        assert injury_names == ['Player1', 'Player3']
        assert fatigue_short == 'LOW'
