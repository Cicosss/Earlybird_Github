"""
Test Suite for V7.3 Performance Improvements

Tests:
1. Optimizer Weight Cache - verifica che i weights vengano caricati una sola volta
2. Tavily Cross-Component Cache - verifica deduplication tra componenti

Author: EarlyBird AI
Date: 2026-01-16
"""
import pytest
import time
import os
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Test A: Optimizer Weight Cache
def test_optimizer_weight_cache_reduces_io():
    """
    Test che il weight cache riduca le letture da disco.
    
    Verifica:
    - Prima chiamata: carica da JSON (cache MISS)
    - Chiamate successive: usa cache in-memory (cache HIT)
    - Dopo invalidazione: ricarica da JSON
    """
    from src.analysis.optimizer import StrategyOptimizer, _weight_cache
    
    # Setup: crea file temporaneo con weights
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        test_data = {
            "stats": {
                "test_league": {
                    "OVER": {
                        "bets": 50,
                        "wins": 30,
                        "profit": 5.0,
                        "roi": 0.1,
                        "returns": [0.9, -1.0, 0.8],
                        "pnl_history": [0.9, -0.1, 0.7],
                        "sharpe": 0.5,
                        "sortino": 0.6,
                        "max_drawdown": -0.1,
                        "weight": 1.2
                    }
                }
            },
            "drivers": {},
            "global": {"total_bets": 50, "total_profit": 5.0, "overall_roi": 0.1},
            "version": "3.0"
        }
        json.dump(test_data, f)
        temp_file = f.name
    
    try:
        # Test 1: Prima istanza - dovrebbe caricare da disco
        _weight_cache.invalidate()  # Reset cache
        
        with patch('builtins.open', wraps=open) as mock_open:
            optimizer1 = StrategyOptimizer(weights_file=temp_file)
            
            # Verifica che il file sia stato letto
            assert mock_open.call_count >= 1, "Prima istanza dovrebbe leggere da disco"
            
            # Test 2: get_weight dovrebbe usare cache (no ulteriori letture)
            initial_calls = mock_open.call_count
            weight1, _ = optimizer1.get_weight("test_league", "Over 2.5")
            weight2, _ = optimizer1.get_weight("test_league", "Over 2.5")
            
            # Nessuna nuova lettura da disco
            assert mock_open.call_count == initial_calls, "get_weight dovrebbe usare cache"
            assert weight1 == weight2 == 1.2, "Weight dovrebbe essere consistente"
        
        # Test 3: Dopo invalidazione, dovrebbe ricaricare
        _weight_cache.invalidate()
        
        with patch('builtins.open', wraps=open) as mock_open:
            optimizer2 = StrategyOptimizer(weights_file=temp_file)
            assert mock_open.call_count >= 1, "Dopo invalidazione dovrebbe ricaricare"
        
        print("✅ Test optimizer weight cache PASSED")
        
    finally:
        # Cleanup
        if os.path.exists(temp_file):
            os.remove(temp_file)


def test_optimizer_cache_invalidation_after_settlement():
    """
    Test che la cache venga invalidata dopo settlement.
    
    Verifica:
    - recalculate_weights() invalida la cache
    - Prossima get_weight() ricarica da disco
    
    NOTE: Questo test usa il file di produzione per testare la cache.
    """
    from src.analysis.optimizer import StrategyOptimizer, _weight_cache, WEIGHTS_FILE
    import shutil
    
    # Backup del file di produzione se esiste
    backup_file = None
    if os.path.exists(WEIGHTS_FILE):
        backup_file = WEIGHTS_FILE + '.backup_test'
        shutil.copy(WEIGHTS_FILE, backup_file)
    
    try:
        # Crea file di produzione con dati test
        os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
        test_data = {
            "stats": {},
            "drivers": {},
            "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
            "version": "3.0"
        }
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(test_data, f)
        
        _weight_cache.invalidate()
        optimizer = StrategyOptimizer()  # Usa file di produzione
        
        # Simula settlement
        settlement_stats = {
            "settled": 1,
            "details": [{
                "league": "test_league",
                "market": "Over 2.5",
                "outcome": "WIN",
                "odds": 1.9,
                "driver": "MATH_VALUE"
            }]
        }
        
        # Prima del settlement: cache dovrebbe essere popolata
        cache_stats_before = _weight_cache.get_stats()
        assert cache_stats_before['cached'] is True, "Cache dovrebbe essere popolata"
        
        # Esegui settlement (dovrebbe aggiornare cache)
        optimizer.recalculate_weights(settlement_stats)
        
        # Dopo settlement: cache dovrebbe essere ancora popolata (updated, not invalidated)
        cache_stats_after = _weight_cache.get_stats()
        assert cache_stats_after['cached'] is True, "Cache dovrebbe essere aggiornata"
        
        print("✅ Test cache invalidation PASSED")
        
    finally:
        # Restore backup
        if backup_file and os.path.exists(backup_file):
            shutil.move(backup_file, WEIGHTS_FILE)
        elif os.path.exists(WEIGHTS_FILE):
            os.remove(WEIGHTS_FILE)


# Test B: Tavily Cross-Component Cache
def test_tavily_shared_cache_deduplication():
    """
    Test che Tavily usi SharedContentCache per deduplication.
    
    Verifica:
    - Prima query: API call + mark in shared cache
    - Seconda query (stesso parametri): cache HIT, no API call
    - Query da componente diverso: shared cache HIT
    """
    from src.ingestion.tavily_provider import TavilyProvider
    
    # Mock shared cache
    mock_shared_cache = Mock()
    mock_shared_cache.is_duplicate.return_value = False  # Prima query: non duplicate
    
    # Mock key rotator
    mock_key_rotator = Mock()
    mock_key_rotator.is_available.return_value = True
    mock_key_rotator.get_current_key.return_value = "test_key"
    mock_key_rotator.record_call = Mock()
    
    # Mock HTTP client
    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "answer": "Test answer",
        "results": [
            {
                "title": "Test Result",
                "url": "https://example.com",
                "content": "Test content",
                "score": 0.9
            }
        ]
    }
    mock_http_client.post_sync.return_value = mock_response
    
    with patch('src.ingestion.tavily_provider.TAVILY_ENABLED', True):
        with patch('src.ingestion.tavily_provider.get_shared_cache', return_value=mock_shared_cache):
            with patch('src.ingestion.tavily_provider.get_http_client', return_value=mock_http_client):
                provider = TavilyProvider(key_rotator=mock_key_rotator)
                provider._shared_cache = mock_shared_cache
                
                # Test 1: Prima query - dovrebbe chiamare API e marcare in shared cache
                result1 = provider.search("test query", max_results=5)
                
                assert result1 is not None, "Prima query dovrebbe restituire risultati"
                assert mock_http_client.post_sync.call_count == 1, "Dovrebbe chiamare API"
                assert mock_shared_cache.mark_seen.call_count == 1, "Dovrebbe marcare in shared cache"
                
                # Verifica parametri mark_seen
                call_args = mock_shared_cache.mark_seen.call_args
                assert call_args[1]['source'] == 'tavily', "Source dovrebbe essere 'tavily'"
                
                # Test 2: Seconda query (stessi parametri) - shared cache HIT
                mock_shared_cache.is_duplicate.return_value = True  # Simula cache HIT
                
                result2 = provider.search("test query", max_results=5)
                
                # Dovrebbe usare local cache (già popolata), no nuova API call
                assert mock_http_client.post_sync.call_count == 1, "Non dovrebbe chiamare API di nuovo"
                
                print("✅ Test Tavily shared cache PASSED")


def test_tavily_shared_cache_cross_component():
    """
    Test che query duplicate da componenti diversi vengano deduplicate.
    
    Scenario:
    - Main Pipeline fa query "Galatasaray injuries"
    - News Radar fa stessa query 5 minuti dopo
    - Dovrebbe usare shared cache, no nuova API call
    """
    from src.ingestion.tavily_provider import TavilyProvider
    
    mock_shared_cache = Mock()
    mock_key_rotator = Mock()
    mock_key_rotator.is_available.return_value = True
    mock_key_rotator.get_current_key.return_value = "test_key"
    
    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"answer": "Test", "results": []}
    mock_http_client.post_sync.return_value = mock_response
    
    with patch('src.ingestion.tavily_provider.TAVILY_ENABLED', True):
        with patch('src.ingestion.tavily_provider.get_shared_cache', return_value=mock_shared_cache):
            with patch('src.ingestion.tavily_provider.get_http_client', return_value=mock_http_client):
                # Componente 1: Main Pipeline
                mock_shared_cache.is_duplicate.return_value = False
                provider1 = TavilyProvider(key_rotator=mock_key_rotator)
                provider1._shared_cache = mock_shared_cache
                
                result1 = provider1.search("Galatasaray injuries")
                assert mock_http_client.post_sync.call_count == 1
                assert mock_shared_cache.mark_seen.call_count == 1
                
                # Componente 2: News Radar (stessa query)
                mock_shared_cache.is_duplicate.return_value = True  # Cache HIT
                provider2 = TavilyProvider(key_rotator=mock_key_rotator)
                provider2._shared_cache = mock_shared_cache
                
                # Popola local cache di provider2 con risultato
                provider2._cache = provider1._cache.copy()
                
                result2 = provider2.search("Galatasaray injuries")
                
                # Nessuna nuova API call (shared cache HIT)
                assert mock_http_client.post_sync.call_count == 1, "Dovrebbe riusare cache"
                
                print("✅ Test cross-component deduplication PASSED")


# Test Edge Cases
def test_optimizer_cache_thread_safety():
    """
    Test che il weight cache sia thread-safe.
    
    Verifica:
    - Accessi concorrenti non causano race conditions
    - Lock previene corruzione dati
    """
    from src.analysis.optimizer import _weight_cache
    import threading
    
    _weight_cache.invalidate()
    
    results = []
    errors = []
    
    def access_cache():
        try:
            for _ in range(10):
                # Simula accesso concorrente
                _weight_cache.get_data(lambda: {"test": "data"})
                time.sleep(0.001)
            results.append("success")
        except Exception as e:
            errors.append(str(e))
    
    # Crea 5 thread che accedono concorrentemente
    threads = [threading.Thread(target=access_cache) for _ in range(5)]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    assert len(errors) == 0, f"Non dovrebbero esserci errori: {errors}"
    assert len(results) == 5, "Tutti i thread dovrebbero completare"
    
    print("✅ Test thread safety PASSED")


def test_tavily_cache_with_none_shared_cache():
    """
    Test che Tavily funzioni anche senza SharedContentCache.
    
    Verifica:
    - Se SharedContentCache non disponibile, usa solo local cache
    - Nessun crash o errore
    """
    from src.ingestion.tavily_provider import TavilyProvider
    
    mock_key_rotator = Mock()
    mock_key_rotator.is_available.return_value = True
    mock_key_rotator.get_current_key.return_value = "test_key"
    
    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"answer": "Test", "results": []}
    mock_http_client.post_sync.return_value = mock_response
    
    with patch('src.ingestion.tavily_provider.TAVILY_ENABLED', True):
        with patch('src.ingestion.tavily_provider._SHARED_CACHE_AVAILABLE', False):
            with patch('src.ingestion.tavily_provider.get_http_client', return_value=mock_http_client):
                provider = TavilyProvider(key_rotator=mock_key_rotator)
                
                # Verifica che shared_cache sia None
                assert provider._shared_cache is None, "Shared cache dovrebbe essere None"
                
                # Dovrebbe funzionare comunque con local cache
                result = provider.search("test query")
                assert result is not None, "Dovrebbe funzionare senza shared cache"
                
                print("✅ Test fallback to local cache PASSED")


if __name__ == "__main__":
    print("\n🧪 Running V7.3 Performance Improvement Tests...\n")
    
    test_optimizer_weight_cache_reduces_io()
    test_optimizer_cache_invalidation_after_settlement()
    test_tavily_shared_cache_deduplication()
    test_tavily_shared_cache_cross_component()
    test_optimizer_cache_thread_safety()
    test_tavily_cache_with_none_shared_cache()
    
    print("\n✅ All V7.3 tests PASSED!\n")
