#!/usr/bin/env python3
"""
Test di regressione per i fix V6.1 di analyzer.py

Questo test verifica:
1. Thread-safety delle variabili globali AI response tracking
2. Costante NEWS_SNIPPET_MAX_CHARS configurabile
3. Logging per fallback silenzioso deep_dive
4. validate_ai_response gestisce correttamente edge cases

Bug originali:
- Race condition su _ai_invalid_response_count/_ai_total_response_count
- Magic number 3000 hardcoded per troncamento news
- Fallback silenzioso quando INTELLIGENCE_ROUTER_AVAILABLE è False
"""
import pytest
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestThreadSafeAIStats:
    """Test suite per la thread-safety delle statistiche AI."""
    
    def test_ai_stats_lock_exists(self):
        """Verifica che il lock per le statistiche AI esista."""
        from src.analysis.analyzer import _ai_stats_lock
        assert isinstance(_ai_stats_lock, type(threading.Lock()))
    
    def test_validate_ai_response_thread_safe(self):
        """
        Verifica che validate_ai_response sia thread-safe.
        
        Questo test avrebbe fallito nella versione buggata dove
        le variabili globali erano modificate senza lock.
        """
        from src.analysis.analyzer import (
            validate_ai_response,
            reset_ai_response_stats,
            get_ai_response_stats
        )
        
        # Reset stats
        reset_ai_response_stats()
        
        # Dati di test
        valid_data = {'final_verdict': 'BET', 'confidence': 75}
        invalid_data = {'final_verdict': 'INVALID', 'confidence': 'not_a_number'}
        
        errors = []
        results = []
        
        def worker(data, iterations):
            """Worker thread che chiama validate_ai_response."""
            try:
                for _ in range(iterations):
                    result = validate_ai_response(data.copy())
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Crea thread concorrenti
        threads = []
        iterations_per_thread = 50
        num_threads = 10
        
        for i in range(num_threads):
            data = valid_data if i % 2 == 0 else invalid_data
            t = threading.Thread(target=worker, args=(data, iterations_per_thread))
            threads.append(t)
        
        # Avvia tutti i thread
        for t in threads:
            t.start()
        
        # Attendi completamento
        for t in threads:
            t.join()
        
        # Verifica nessun errore
        assert len(errors) == 0, f"Thread errors: {errors}"
        
        # Verifica conteggio corretto
        stats = get_ai_response_stats()
        expected_total = num_threads * iterations_per_thread
        assert stats['total_responses'] == expected_total, \
            f"Expected {expected_total} total, got {stats['total_responses']}"
    
    def test_get_ai_response_stats_thread_safe(self):
        """Verifica che get_ai_response_stats sia thread-safe."""
        from src.analysis.analyzer import get_ai_response_stats
        
        errors = []
        
        def reader():
            try:
                for _ in range(100):
                    stats = get_ai_response_stats()
                    # Verifica struttura
                    assert 'total_responses' in stats
                    assert 'invalid_responses' in stats
                    assert 'error_rate_percent' in stats
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Reader errors: {errors}"
    
    def test_reset_ai_response_stats_thread_safe(self):
        """Verifica che reset_ai_response_stats sia thread-safe."""
        from src.analysis.analyzer import (
            reset_ai_response_stats,
            get_ai_response_stats
        )
        
        reset_ai_response_stats()
        stats = get_ai_response_stats()
        
        assert stats['total_responses'] == 0
        assert stats['invalid_responses'] == 0


class TestNewsSnippetMaxChars:
    """Test suite per la costante NEWS_SNIPPET_MAX_CHARS."""
    
    def test_constant_exists_in_settings(self):
        """Verifica che NEWS_SNIPPET_MAX_CHARS sia definita in settings."""
        from config.settings import NEWS_SNIPPET_MAX_CHARS
        assert isinstance(NEWS_SNIPPET_MAX_CHARS, int)
        assert NEWS_SNIPPET_MAX_CHARS > 0
    
    def test_constant_default_value(self):
        """Verifica il valore di default (3000)."""
        from config.settings import NEWS_SNIPPET_MAX_CHARS
        assert NEWS_SNIPPET_MAX_CHARS == 3000
    
    def test_no_hardcoded_3000_in_analyzer(self):
        """
        Verifica che non ci siano magic number 3000 hardcoded.
        
        Questo test avrebbe fallito nella versione buggata.
        """
        analyzer_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'src', 'analysis', 'analyzer.py'
        )
        
        with open(analyzer_path, 'r') as f:
            content = f.read()
        
        # Il pattern "[:3000]" non dovrebbe più esistere
        assert '[:3000]' not in content, \
            "Hardcoded [:3000] should be replaced with NEWS_SNIPPET_MAX_CHARS"
        
        # Verifica che usi la costante
        assert 'NEWS_SNIPPET_MAX_CHARS' in content, \
            "Should use NEWS_SNIPPET_MAX_CHARS constant"


class TestValidateAIResponseEdgeCases:
    """Test suite per edge cases di validate_ai_response."""
    
    def test_empty_dict(self):
        """Verifica gestione dict vuoto."""
        from src.analysis.analyzer import validate_ai_response
        
        result = validate_ai_response({})
        
        # Deve avere tutti i campi con default
        assert result['final_verdict'] == 'NO BET'
        assert result['confidence'] == 0
        assert result['recommended_market'] == 'NONE'
        assert result['primary_market'] == 'NONE'
        assert result['reasoning'] == 'Analisi non disponibile'
    
    def test_none_values(self):
        """Verifica gestione valori None."""
        from src.analysis.analyzer import validate_ai_response
        
        result = validate_ai_response({
            'final_verdict': None,
            'confidence': None,
            'reasoning': None
        })
        
        assert result['final_verdict'] == 'NO BET'
        assert result['confidence'] == 0
        assert result['reasoning'] == 'Analisi non disponibile'
    
    def test_invalid_confidence_type(self):
        """Verifica coercizione tipo confidence."""
        from src.analysis.analyzer import validate_ai_response
        
        # String che può essere convertita
        result = validate_ai_response({'confidence': '75'})
        assert result['confidence'] == 75
        
        # String non convertibile
        result = validate_ai_response({'confidence': 'high'})
        assert result['confidence'] == 0  # Default
    
    def test_confidence_range_clamping(self):
        """Verifica clamping del range confidence."""
        from src.analysis.analyzer import validate_ai_response
        
        # Sopra 100
        result = validate_ai_response({'confidence': 150})
        assert result['confidence'] == 100
        
        # Sotto 0
        result = validate_ai_response({'confidence': -10})
        assert result['confidence'] == 0
    
    def test_invalid_verdict_value(self):
        """Verifica gestione verdict non valido."""
        from src.analysis.analyzer import validate_ai_response
        
        result = validate_ai_response({'final_verdict': 'MAYBE'})
        assert result['final_verdict'] == 'NO BET'  # Default
    
    def test_extra_fields_preserved(self):
        """Verifica che campi extra siano preservati."""
        from src.analysis.analyzer import validate_ai_response
        
        result = validate_ai_response({
            'final_verdict': 'BET',
            'custom_field': 'custom_value',
            'another_field': 123
        })
        
        assert result['custom_field'] == 'custom_value'
        assert result['another_field'] == 123


class TestDeepDiveFallbackLogging:
    """Test per il logging del fallback deep_dive."""
    
    def test_intelligence_router_logging_exists(self):
        """
        Verifica che ci sia logging quando INTELLIGENCE_ROUTER_AVAILABLE è False.
        
        Questo test verifica che il fix per il fallback silenzioso sia presente.
        """
        analyzer_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'src', 'analysis', 'analyzer.py'
        )
        
        with open(analyzer_path, 'r') as f:
            content = f.read()
        
        # Deve esserci un else con logging dopo il blocco if INTELLIGENCE_ROUTER_AVAILABLE
        assert 'Intelligence Router not available' in content or \
               'deep_dive skipped' in content, \
            "Should log when Intelligence Router is not available"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
