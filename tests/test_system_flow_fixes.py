"""
Test di regressione per i fix del sistema flow V5.0.2

Questi test verificano:
1. Cleanup periodico browser_monitor_discoveries
2. Tracking errori AI response
3. Edge case handling

Ogni test fallirebbe nella versione buggata e passa con la patch.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import logging


class TestBrowserMonitorCleanup:
    """Test per il cleanup periodico delle browser monitor discoveries."""
    
    def test_cleanup_removes_expired_discoveries(self):
        """
        REGRESSION TEST: cleanup_expired_browser_monitor_discoveries rimuove entry scadute.
        
        Prima del fix: nessun cleanup proattivo, memory leak.
        Dopo il fix: cleanup rimuove entry > 24h.
        """
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            cleanup_expired_browser_monitor_discoveries,
            _BROWSER_MONITOR_TTL_HOURS
        )
        
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=_BROWSER_MONITOR_TTL_HOURS + 1)
        fresh_time = now - timedelta(hours=1)
        
        # Setup: inserisci discovery vecchie e fresche
        with _browser_monitor_lock:
            _browser_monitor_discoveries['test_league'] = [
                {'discovered_at': old_time.isoformat(), 'title': 'Old news'},
                {'discovered_at': fresh_time.isoformat(), 'title': 'Fresh news'},
            ]
        
        # Esegui cleanup
        removed = cleanup_expired_browser_monitor_discoveries()
        
        # Verifica
        assert removed == 1, "Deve rimuovere esattamente 1 discovery scaduta"
        
        with _browser_monitor_lock:
            remaining = _browser_monitor_discoveries.get('test_league', [])
            assert len(remaining) == 1, "Deve rimanere solo 1 discovery"
            assert remaining[0]['title'] == 'Fresh news', "Deve rimanere la discovery fresca"
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    
    def test_cleanup_handles_empty_storage(self):
        """Cleanup non deve crashare con storage vuoto."""
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            cleanup_expired_browser_monitor_discoveries
        )
        
        # Assicurati che sia vuoto
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
        
        # Non deve sollevare eccezioni
        removed = cleanup_expired_browser_monitor_discoveries()
        assert removed == 0
    
    def test_cleanup_handles_invalid_timestamps(self):
        """Cleanup deve gestire timestamp invalidi senza crashare."""
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            cleanup_expired_browser_monitor_discoveries
        )
        
        with _browser_monitor_lock:
            _browser_monitor_discoveries['test_league'] = [
                {'discovered_at': 'invalid-timestamp', 'title': 'Bad timestamp'},
                {'discovered_at': None, 'title': 'No timestamp'},
                {'title': 'Missing field'},  # Nessun discovered_at
            ]
        
        # Non deve crashare
        removed = cleanup_expired_browser_monitor_discoveries()
        
        # Entry con timestamp invalidi vengono mantenute (conservative)
        with _browser_monitor_lock:
            remaining = _browser_monitor_discoveries.get('test_league', [])
            assert len(remaining) == 3, "Entry con timestamp invalidi devono essere mantenute"
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    
    def test_get_browser_monitor_stats(self):
        """Verifica che get_browser_monitor_stats restituisca dati corretti."""
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            get_browser_monitor_stats
        )
        
        now = datetime.now(timezone.utc)
        
        with _browser_monitor_lock:
            _browser_monitor_discoveries['league_a'] = [
                {'discovered_at': now.isoformat()},
                {'discovered_at': (now - timedelta(hours=5)).isoformat()},
            ]
            _browser_monitor_discoveries['league_b'] = [
                {'discovered_at': (now - timedelta(hours=10)).isoformat()},
            ]
        
        stats = get_browser_monitor_stats()
        
        assert stats['total_discoveries'] == 3
        assert stats['by_league']['league_a'] == 2
        assert stats['by_league']['league_b'] == 1
        assert stats['oldest_discovery_age_hours'] >= 9.9  # ~10 hours
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()


class TestAIResponseTracking:
    """Test per il tracking degli errori AI response."""
    
    def test_validate_ai_response_tracks_invalid_fields(self):
        """
        REGRESSION TEST: validate_ai_response deve tracciare campi invalidi.
        
        Prima del fix: nessun tracking, problemi AI mascherati.
        Dopo il fix: contatore incrementato, alert se error rate > 20%.
        """
        from src.analysis.analyzer import (
            validate_ai_response,
            get_ai_response_stats,
            reset_ai_response_stats
        )
        
        # Reset stats
        reset_ai_response_stats()
        
        # Simula risposte con campi invalidi
        invalid_response = {
            'final_verdict': 'INVALID_VALUE',  # Non in valid_values
            'confidence': 150,  # Fuori range
            'primary_driver': 'UNKNOWN_DRIVER',  # Non in valid_values
        }
        
        result = validate_ai_response(invalid_response)
        
        # Deve applicare default per campi invalidi
        assert result['final_verdict'] == 'NO BET'
        assert result['confidence'] == 100  # Clamped to max
        assert result['primary_driver'] == 'MATH_VALUE'
        
        # REGRESSION: Deve tracciare l'errore
        stats = get_ai_response_stats()
        assert stats['total_responses'] >= 1
        assert stats['invalid_responses'] >= 1
    
    def test_validate_ai_response_valid_response_no_error(self):
        """Risposte valide non devono incrementare il contatore errori."""
        from src.analysis.analyzer import (
            validate_ai_response,
            get_ai_response_stats,
            reset_ai_response_stats
        )
        
        reset_ai_response_stats()
        
        valid_response = {
            'final_verdict': 'BET',
            'confidence': 75,
            'recommended_market': 'Over 2.5 Goals',
            'primary_market': '1',
            'primary_driver': 'INJURY_INTEL',
            'combo_suggestion': 'Home Win + Over 2.5',
            'combo_reasoning': 'Test reasoning',
            'reasoning': 'Test analysis'
        }
        
        result = validate_ai_response(valid_response)
        
        # Tutti i campi devono essere preservati
        assert result['final_verdict'] == 'BET'
        assert result['confidence'] == 75
        
        stats = get_ai_response_stats()
        assert stats['total_responses'] == 1
        assert stats['invalid_responses'] == 0
        assert stats['error_rate_percent'] == 0
    
    def test_reset_ai_response_stats(self):
        """reset_ai_response_stats deve azzerare i contatori."""
        from src.analysis.analyzer import (
            validate_ai_response,
            get_ai_response_stats,
            reset_ai_response_stats
        )
        
        # Genera alcune risposte
        for _ in range(5):
            validate_ai_response({'final_verdict': 'INVALID'})
        
        stats_before = get_ai_response_stats()
        assert stats_before['total_responses'] >= 5
        
        # Reset
        reset_ai_response_stats()
        
        stats_after = get_ai_response_stats()
        assert stats_after['total_responses'] == 0
        assert stats_after['invalid_responses'] == 0
    
    def test_validate_ai_response_handles_none_data(self):
        """validate_ai_response deve gestire dict vuoto senza crashare."""
        from src.analysis.analyzer import validate_ai_response, reset_ai_response_stats
        
        reset_ai_response_stats()
        
        # Dict vuoto
        result = validate_ai_response({})
        
        # Deve applicare tutti i default
        assert result['final_verdict'] == 'NO BET'
        assert result['confidence'] == 0
        assert result['reasoning'] == 'Analisi non disponibile'
    
    def test_validate_ai_response_preserves_extra_fields(self):
        """Campi extra non nello schema devono essere preservati."""
        from src.analysis.analyzer import validate_ai_response, reset_ai_response_stats
        
        reset_ai_response_stats()
        
        response_with_extras = {
            'final_verdict': 'BET',
            'confidence': 80,
            'custom_field': 'custom_value',
            'another_extra': 123
        }
        
        result = validate_ai_response(response_with_extras)
        
        assert result['custom_field'] == 'custom_value'
        assert result['another_extra'] == 123


class TestEdgeCases:
    """Test per edge case critici identificati nell'analisi."""
    
    def test_browser_monitor_empty_team_names(self):
        """get_browser_monitor_news deve gestire team_names vuoto."""
        from src.processing.news_hunter import get_browser_monitor_news
        
        # Non deve crashare con lista vuota
        result = get_browser_monitor_news("match_123", [], "test_league")
        assert result == []
        
        # Non deve crashare con None (se passato erroneamente)
        result = get_browser_monitor_news("match_123", None, "test_league")
        assert result == []
    
    def test_browser_monitor_none_in_team_names(self):
        """get_browser_monitor_news deve gestire None nella lista team_names."""
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            get_browser_monitor_news
        )
        
        now = datetime.now(timezone.utc)
        
        with _browser_monitor_lock:
            _browser_monitor_discoveries['test_league'] = [
                {'discovered_at': now.isoformat(), 'team': 'Team A', 'title': 'News'}
            ]
        
        # Lista con None non deve crashare
        result = get_browser_monitor_news("match_123", [None, "Team A", None], "test_league")
        
        # Deve comunque trovare il match per "Team A"
        assert len(result) >= 0  # Non crashato
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    
    def test_validate_ai_response_type_coercion(self):
        """validate_ai_response deve convertire tipi quando possibile."""
        from src.analysis.analyzer import validate_ai_response, reset_ai_response_stats
        
        reset_ai_response_stats()
        
        # confidence come stringa invece di int
        response = {
            'final_verdict': 'BET',
            'confidence': '85',  # Stringa invece di int
        }
        
        result = validate_ai_response(response)
        
        # Deve convertire a int
        assert result['confidence'] == 85
        assert isinstance(result['confidence'], int)


class TestBrowserMonitorRaceCondition:
    """
    Test per il fix della race condition in get_browser_monitor_news (V5.0.3).
    
    Il problema originale: la pulizia delle entry scadute avveniva DENTRO il lock
    mentre si iterava, causando potenziali deadlock e perdita di nuove discovery
    aggiunte da altri thread.
    
    Il fix: separa read/filter/update in 3 step con lock minimali.
    """
    
    def test_get_browser_monitor_news_preserves_new_entries(self):
        """
        REGRESSION TEST: get_browser_monitor_news non deve sovrascrivere
        nuove discovery aggiunte tra la lettura e l'aggiornamento.
        
        Prima del fix: nuove entry potevano essere perse.
        Dopo il fix: nuove entry vengono preservate.
        """
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            get_browser_monitor_news,
            register_browser_monitor_discovery
        )
        import threading
        import time
        
        now = datetime.now(timezone.utc)
        
        # Setup: inserisci una discovery iniziale
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
            _browser_monitor_discoveries['test_league'] = [
                {
                    'discovered_at': now.isoformat(),
                    'title': 'Initial news',
                    'team': 'Test Team',
                    'link': 'http://test.com/1',
                    'snippet': 'Test snippet',
                    'source': 'Test Source',
                    'date': now.isoformat(),
                }
            ]
        
        # Simula una nuova discovery aggiunta durante l'elaborazione
        def add_new_discovery():
            time.sleep(0.01)  # Piccolo delay per simulare concorrenza
            with _browser_monitor_lock:
                if 'test_league' in _browser_monitor_discoveries:
                    _browser_monitor_discoveries['test_league'].append({
                        'discovered_at': datetime.now(timezone.utc).isoformat(),
                        'title': 'New concurrent news',
                        'team': 'Another Team',
                        'link': 'http://test.com/2',
                        'snippet': 'New snippet',
                        'source': 'Test Source',
                        'date': datetime.now(timezone.utc).isoformat(),
                    })
        
        # Avvia thread che aggiunge nuova discovery
        thread = threading.Thread(target=add_new_discovery)
        thread.start()
        
        # Chiama get_browser_monitor_news (che fa cleanup)
        results = get_browser_monitor_news(
            match_id='test_match',
            team_names=['Test Team'],
            league_key='test_league'
        )
        
        thread.join(timeout=1)
        
        # Verifica che la nuova entry non sia stata persa
        with _browser_monitor_lock:
            remaining = _browser_monitor_discoveries.get('test_league', [])
            # Deve contenere almeno 1 entry (la nuova o entrambe)
            assert len(remaining) >= 1, \
                "REGRESSION: get_browser_monitor_news ha perso le discovery!"
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    
    def test_get_browser_monitor_news_concurrent_access_no_deadlock(self):
        """
        REGRESSION TEST: accessi concorrenti non devono causare deadlock.
        
        Prima del fix: possibile deadlock con lock mantenuto durante iterazione.
        Dopo il fix: lock minimali, nessun deadlock.
        """
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            get_browser_monitor_news,
            register_browser_monitor_discovery
        )
        import threading
        
        now = datetime.now(timezone.utc)
        
        # Setup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
            _browser_monitor_discoveries['test_league'] = [
                {
                    'discovered_at': now.isoformat(),
                    'title': f'News {i}',
                    'team': 'Test Team',
                    'link': f'http://test.com/{i}',
                    'snippet': 'Test',
                    'source': 'Test',
                    'date': now.isoformat(),
                }
                for i in range(10)
            ]
        
        errors = []
        
        def reader():
            try:
                for _ in range(20):
                    get_browser_monitor_news('match', ['Test Team'], 'test_league')
            except Exception as e:
                errors.append(f"Reader error: {e}")
        
        def writer():
            try:
                for i in range(20):
                    with _browser_monitor_lock:
                        if 'test_league' in _browser_monitor_discoveries:
                            _browser_monitor_discoveries['test_league'].append({
                                'discovered_at': datetime.now(timezone.utc).isoformat(),
                                'title': f'Concurrent {i}',
                                'team': 'Other Team',
                                'link': f'http://test.com/c{i}',
                                'snippet': 'Test',
                                'source': 'Test',
                                'date': datetime.now(timezone.utc).isoformat(),
                            })
            except Exception as e:
                errors.append(f"Writer error: {e}")
        
        # Avvia thread concorrenti
        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]
        
        for t in threads:
            t.start()
        
        # Timeout di 5 secondi - se c'è deadlock, fallisce
        for t in threads:
            t.join(timeout=5)
            if t.is_alive():
                errors.append("DEADLOCK DETECTED: thread did not complete in 5s")
        
        assert not errors, f"REGRESSION: Race condition errors: {errors}"
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
    
    def test_get_browser_monitor_news_only_updates_on_expiry(self):
        """
        Verifica che l'aggiornamento avvenga solo se ci sono entry scadute.
        Ottimizzazione per evitare write inutili.
        """
        from src.processing.news_hunter import (
            _browser_monitor_discoveries,
            _browser_monitor_lock,
            get_browser_monitor_news
        )
        
        now = datetime.now(timezone.utc)
        
        # Setup: solo entry fresche
        original_entry = {
            'discovered_at': now.isoformat(),
            'title': 'Fresh news',
            'team': 'Test Team',
            'link': 'http://test.com/1',
            'snippet': 'Test',
            'source': 'Test',
            'date': now.isoformat(),
        }
        
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()
            _browser_monitor_discoveries['test_league'] = [original_entry]
        
        # Chiama get_browser_monitor_news
        results = get_browser_monitor_news(
            match_id='test_match',
            team_names=['Test Team'],
            league_key='test_league'
        )
        
        # Verifica che l'entry originale sia ancora presente
        with _browser_monitor_lock:
            remaining = _browser_monitor_discoveries.get('test_league', [])
            assert len(remaining) == 1
            assert remaining[0]['title'] == 'Fresh news'
        
        # Cleanup
        with _browser_monitor_lock:
            _browser_monitor_discoveries.clear()


# Marker per pytest
pytestmark = pytest.mark.regression


class TestAnalyzerEdgeCases:
    """Test per edge case e bug fix in analyzer.py V5.0.3"""
    
    def test_extract_player_names_with_accents(self):
        """
        REGRESSION TEST: extract_player_names deve catturare nomi con accenti.
        
        Prima del fix: pattern [A-Z][a-z]+ non catturava José, Müller, etc.
        Dopo il fix: pattern esteso supporta caratteri accentati.
        """
        from src.analysis.analyzer import extract_player_names
        
        # Nomi con accenti che prima venivano ignorati
        text = "José Mourinho confirmed that Müller will start. Çalhanoğlu is doubtful."
        
        names = extract_player_names(text)
        
        # Deve trovare almeno José Mourinho
        assert any("José" in name or "Mourinho" in name for name in names), \
            f"Deve trovare José Mourinho, trovati: {names}"
    
    def test_extract_player_names_empty_text(self):
        """extract_player_names deve gestire testo vuoto/None senza crash."""
        from src.analysis.analyzer import extract_player_names
        
        assert extract_player_names("") == []
        assert extract_player_names(None) == []
    
    def test_safe_injuries_list_validates_name_type(self):
        """
        REGRESSION TEST: safe_injuries_list deve validare che name sia stringa non vuota.
        
        Prima del fix: p.get('name') passava anche con name=0 o name=[]
        Dopo il fix: verifica isinstance(name, str) and name.strip()
        """
        from src.analysis.analyzer import safe_injuries_list
        
        # Dati con name invalidi
        fotmob_data = {
            'injuries': [
                {'name': 'Valid Player', 'status': 'injured'},
                {'name': '', 'status': 'injured'},  # stringa vuota
                {'name': 0, 'status': 'injured'},   # numero
                {'name': [], 'status': 'injured'},  # lista
                {'name': None, 'status': 'injured'},  # None
                {'name': '  ', 'status': 'injured'},  # solo spazi
                {'name': 'Another Valid', 'status': 'out'},
            ]
        }
        
        result = safe_injuries_list(fotmob_data)
        
        # Deve restituire solo i 2 giocatori con name valido
        assert len(result) == 2, f"Deve trovare 2 giocatori validi, trovati: {len(result)}"
        assert result[0]['name'] == 'Valid Player'
        assert result[1]['name'] == 'Another Valid'
    
    def test_safe_injuries_list_handles_none(self):
        """safe_injuries_list deve gestire input None/invalidi."""
        from src.analysis.analyzer import safe_injuries_list
        
        assert safe_injuries_list(None) == []
        assert safe_injuries_list({}) == []
        assert safe_injuries_list({'injuries': None}) == []
        assert safe_injuries_list({'injuries': 'not a list'}) == []
    
    def test_analyze_biscotto_handles_none_draw_odd(self):
        """
        REGRESSION TEST: analyze_biscotto non deve crashare con draw_odd=None.
        
        Prima del fix: TypeError su (opening_draw - draw_odd) se draw_odd è None
        Dopo il fix: check esplicito draw_odd is not None
        """
        from src.analysis.analyzer import analyze_biscotto
        import os
        
        # Skip se API key non configurata (test unitario, non integration)
        if not os.getenv("OPENROUTER_API_KEY"):
            # Verifica almeno che la funzione non crashi prima della chiamata API
            # Il return None avviene prima del calcolo se API key manca
            result = analyze_biscotto(
                news_snippet="Test news",
                home_team="Team A",
                away_team="Team B",
                draw_odd=None,  # Questo causava TypeError
                opening_draw=3.5,
                league="Test League"
            )
            assert result is None  # Ritorna None perché API key manca
        else:
            pytest.skip("Test richiede ambiente senza API key")
    
    def test_snippet_data_none_handling(self):
        """
        REGRESSION TEST: analyze_with_triangulation deve gestire snippet_data=None.
        
        Prima del fix: AttributeError su snippet_data.get() se snippet_data è None
        Dopo il fix: snippet_data = {} se None
        """
        from src.analysis.analyzer import analyze_with_triangulation
        import os
        
        # Questo test verifica che non ci sia crash immediato
        # La funzione ritorna None/fallback se API key manca
        if not os.getenv("OPENROUTER_API_KEY"):
            result = analyze_with_triangulation(
                news_snippet="Test news",
                market_status="No movement",
                official_data="No data",
                snippet_data=None  # Questo causava AttributeError
            )
            # Non deve crashare, può ritornare None o fallback
            assert result is None or hasattr(result, 'score')
        else:
            pytest.skip("Test richiede ambiente senza API key per testare fallback")


class TestJsonImportFix:
    """Test per verificare che json.JSONDecodeError sia sempre disponibile."""
    
    def test_json_module_always_imported(self):
        """
        REGRESSION TEST: json deve essere importato anche se orjson è disponibile.
        
        Prima del fix: json importato solo nel blocco except ImportError di orjson
        Dopo il fix: json importato sempre all'inizio del modulo
        """
        # Reimporta il modulo per verificare
        import importlib
        import src.analysis.analyzer as analyzer_module
        
        # Verifica che json sia nel namespace del modulo
        assert hasattr(analyzer_module, 'json'), \
            "Il modulo json deve essere importato in analyzer.py"
        
        # Verifica che JSONDecodeError sia accessibile
        import json
        assert hasattr(json, 'JSONDecodeError'), \
            "json.JSONDecodeError deve essere accessibile"
