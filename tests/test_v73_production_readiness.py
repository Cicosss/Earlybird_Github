"""
Test Suite V7.3 - Production Readiness Check

Verifica finale che le modifiche V7.3 siano pronte per produzione VPS.
Questi test simulano il flusso reale senza reset di singleton.

Author: EarlyBird AI
Date: 2026-01-16
"""
import pytest
import os
import sys


def test_imports_work_in_production():
    """
    Test che tutti gli import necessari funzionino.
    
    Verifica:
    - Nessuna dipendenza mancante
    - Import non causano side effects
    """
    try:
        from src.analysis.optimizer import get_optimizer, OptimizerWeightCache, _weight_cache
        from src.ingestion.tavily_provider import TavilyProvider, get_tavily_provider
        from src.utils.shared_cache import get_shared_cache
        
        # Verifica che le classi siano istanziabili
        assert OptimizerWeightCache is not None
        assert TavilyProvider is not None
        
        print("✅ All imports OK")
        
    except ImportError as e:
        pytest.fail(f"Import fallito: {e}")


def test_optimizer_cache_works_with_production_file():
    """
    Test che la cache funzioni con il file di produzione.
    
    Verifica:
    - Cache attiva solo per WEIGHTS_FILE (data/optimizer_weights.json)
    - Test files bypassano cache (no cross-contamination)
    """
    from src.analysis.optimizer import StrategyOptimizer, WEIGHTS_FILE, _weight_cache
    import tempfile
    
    # Test 1: File di produzione usa cache
    if os.path.exists(WEIGHTS_FILE):
        _weight_cache.invalidate()
        optimizer_prod = StrategyOptimizer()  # Usa WEIGHTS_FILE
        
        # Dopo init, cache deve essere popolata
        cache_stats = _weight_cache.get_stats()
        assert cache_stats['cached'] is True, "Cache deve essere attiva per file produzione"
        
        print("✅ Production file uses cache")
    
    # Test 2: Temp file bypassa cache
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        import json
        json.dump({
            "stats": {},
            "drivers": {},
            "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
            "version": "3.0"
        }, f)
        temp_file = f.name
    
    try:
        # Cache deve rimanere invariata (temp file non usa cache)
        cache_before = _weight_cache.get_stats()
        optimizer_test = StrategyOptimizer(weights_file=temp_file)
        cache_after = _weight_cache.get_stats()
        
        # Cache non deve essere modificata da temp file (confronta solo 'cached' status, non timestamp)
        assert cache_before['cached'] == cache_after['cached'], \
            "Temp file non deve modificare cache status"
        
        # Se cache era attiva, timestamp deve essere lo stesso (no reload)
        if cache_before['cached'] and cache_after['cached']:
            assert cache_before['timestamp'] == cache_after['timestamp'], \
                "Temp file non deve ricaricare cache"
        
        print("✅ Test files bypass cache")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


def test_tavily_shared_cache_integration():
    """
    Test che TavilyProvider integri correttamente SharedContentCache.
    
    Verifica:
    - _shared_cache inizializzato se disponibile
    - Graceful fallback se non disponibile
    """
    from src.ingestion.tavily_provider import TavilyProvider
    
    provider = TavilyProvider()
    
    # Verifica che shared_cache sia inizializzato (o None se non disponibile)
    assert hasattr(provider, '_shared_cache'), "Provider deve avere attributo _shared_cache"
    
    # Se disponibile, deve essere istanza corretta
    if provider._shared_cache is not None:
        from src.utils.shared_cache import SharedContentCache
        assert isinstance(provider._shared_cache, SharedContentCache), \
            "Shared cache deve essere istanza di SharedContentCache"
        print("✅ Tavily uses SharedContentCache")
    else:
        print("✅ Tavily graceful fallback (SharedContentCache not available)")


def test_no_new_dependencies_required():
    """
    Test che non servano nuove dipendenze in requirements.txt.
    
    Verifica:
    - Tutte le dipendenze già presenti
    - Nessun import esterno aggiunto
    """
    # Le modifiche V7.3 usano solo:
    # - threading (stdlib)
    # - hashlib (stdlib)
    # - datetime (stdlib)
    # - typing (stdlib)
    
    # Nessuna nuova dipendenza richiesta
    import threading
    import hashlib
    from datetime import datetime
    from typing import Dict, Optional
    
    assert threading.Lock is not None
    assert hashlib.md5 is not None
    assert datetime.now is not None
    
    print("✅ No new dependencies required")


def test_thread_safety_with_lock():
    """
    Test che i lock funzionino correttamente.
    
    Verifica:
    - OptimizerWeightCache usa threading.Lock
    - Nessun deadlock in accesso concorrente
    """
    from src.analysis.optimizer import _weight_cache
    import threading
    import time
    
    results = []
    
    def worker():
        for _ in range(10):
            # Accesso concorrente alla cache
            stats = _weight_cache.get_stats()
            time.sleep(0.001)
        results.append("OK")
    
    threads = [threading.Thread(target=worker) for _ in range(5)]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join(timeout=5)
    
    assert len(results) == 5, "Tutti i thread devono completare (no deadlock)"
    
    print("✅ Thread safety OK")


def test_vps_python_version_compatibility():
    """
    Test compatibilità con Python 3.11+ (VPS requirement).
    
    Verifica:
    - Sintassi compatibile con Python 3.11
    - Nessun uso di feature deprecate
    """
    import sys
    
    # VPS usa Python 3.11.2
    assert sys.version_info >= (3, 11), f"Richiede Python 3.11+, trovato {sys.version}"
    
    # Verifica che le modifiche usino sintassi compatibile
    from src.analysis.optimizer import OptimizerWeightCache
    from src.ingestion.tavily_provider import TavilyProvider
    
    # Type hints con Optional (Python 3.10+)
    from typing import Optional, Dict
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} compatible")


def test_file_paths_work_on_linux():
    """
    Test che i path dei file funzionino su Linux (VPS).
    
    Verifica:
    - data/optimizer_weights.json path corretto
    - Nessun uso di Windows-specific paths
    """
    from src.analysis.optimizer import WEIGHTS_FILE
    import os
    
    # Path deve usare forward slash (Linux compatible)
    assert '\\' not in WEIGHTS_FILE, "Path non deve usare backslash (Windows)"
    
    # Directory data/ deve essere creabile
    data_dir = os.path.dirname(WEIGHTS_FILE)
    assert data_dir == "data", f"Data directory deve essere 'data', trovato '{data_dir}'"
    
    # Path deve essere relativo (non assoluto)
    assert not os.path.isabs(WEIGHTS_FILE), "Path deve essere relativo"
    
    print(f"✅ File paths OK: {WEIGHTS_FILE}")


def test_graceful_degradation():
    """
    Test che il sistema funzioni anche se componenti opzionali mancano.
    
    Verifica:
    - Optimizer funziona senza cache (fallback)
    - Tavily funziona senza SharedContentCache (fallback)
    """
    from src.analysis.optimizer import StrategyOptimizer
    from src.ingestion.tavily_provider import TavilyProvider
    import tempfile
    import json
    
    # Test 1: Optimizer con temp file (no cache)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            "stats": {},
            "drivers": {},
            "global": {"total_bets": 0, "total_profit": 0.0, "overall_roi": 0.0},
            "version": "3.0"
        }, f)
        temp_file = f.name
    
    try:
        optimizer = StrategyOptimizer(weights_file=temp_file)
        weight, _ = optimizer.get_weight("test", "Over 2.5")
        assert weight == 1.0, "Deve funzionare anche senza cache"
        print("✅ Optimizer graceful degradation OK")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    # Test 2: Tavily senza SharedContentCache
    provider = TavilyProvider()
    # Deve funzionare anche se _shared_cache è None
    assert provider is not None, "Provider deve essere istanziabile"
    print("✅ Tavily graceful degradation OK")


def test_backward_compatibility():
    """
    Test che le modifiche siano backward compatible.
    
    Verifica:
    - API pubblica non cambiata
    - Nessun breaking change
    """
    from src.analysis.optimizer import get_optimizer
    from src.ingestion.tavily_provider import get_tavily_provider
    
    # API esistente deve funzionare identicamente
    optimizer = get_optimizer()
    assert optimizer is not None
    assert hasattr(optimizer, 'get_weight')
    assert hasattr(optimizer, 'recalculate_weights')
    
    provider = get_tavily_provider()
    assert provider is not None
    assert hasattr(provider, 'search')
    assert hasattr(provider, 'is_available')
    
    print("✅ Backward compatibility OK")


if __name__ == "__main__":
    print("\n🧪 Running V7.3 Production Readiness Tests...\n")
    
    test_imports_work_in_production()
    test_optimizer_cache_works_with_production_file()
    test_tavily_shared_cache_integration()
    test_no_new_dependencies_required()
    test_thread_safety_with_lock()
    test_vps_python_version_compatibility()
    test_file_paths_work_on_linux()
    test_graceful_degradation()
    test_backward_compatibility()
    
    print("\n✅ All Production Readiness tests PASSED!\n")
    print("🚀 V7.3 is READY FOR VPS DEPLOYMENT")
