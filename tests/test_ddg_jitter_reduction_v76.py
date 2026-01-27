"""
Test DDG Jitter Reduction V7.6

Verifica che la riduzione del jitter DDG (3-6s → 1-2s) funzioni correttamente
senza causare ban o errori di rate limiting.

Requirements:
- Jitter applicato correttamente (1-2s range)
- Rate limiting funziona (min_interval 1.0s)
- Nessun crash su concurrent requests
- Fallback a Brave/Mediastack funziona se DDG banna
"""
import pytest
import time
from unittest.mock import Mock, patch
from src.utils.http_client import get_http_client, RATE_LIMIT_CONFIGS


class TestDDGJitterReduction:
    """Test suite per DDG jitter reduction V7.6."""
    
    def test_ddg_jitter_config_updated(self):
        """
        REGRESSION TEST: Verifica che jitter DDG sia 1-2s (non più 3-6s).
        
        Se questo test fallisce, significa che il jitter è stato ripristinato
        ai valori vecchi per errore.
        """
        config = RATE_LIMIT_CONFIGS.get("duckduckgo")
        
        assert config is not None, "DDG rate limit config missing"
        assert config["min_interval"] == 1.0, "min_interval should be 1.0s"
        assert config["jitter_min"] == 1.0, f"jitter_min should be 1.0s, got {config['jitter_min']}"
        assert config["jitter_max"] == 2.0, f"jitter_max should be 2.0s, got {config['jitter_max']}"
    
    def test_rate_limiter_applies_jitter_correctly(self):
        """
        REGRESSION TEST: Verifica che RateLimiter applichi jitter nel range corretto.
        
        Testa che il delay totale sia tra 1.0s (min_interval) e 3.0s (min_interval + jitter_max).
        """
        http_client = get_http_client()
        rate_limiter = http_client._get_rate_limiter("duckduckgo")
        
        # Reset last_request_time per forzare delay
        rate_limiter.last_request_time = 0.0
        
        # Calcola delay 10 volte per verificare range
        delays = []
        for _ in range(10):
            delay = rate_limiter.get_delay()
            delays.append(delay)
            # Reset per prossima iterazione
            rate_limiter.last_request_time = 0.0
        
        # Verifica che tutti i delay siano nel range atteso
        for delay in delays:
            assert 1.0 <= delay <= 3.0, f"Delay {delay:.2f}s fuori range [1.0, 3.0]"
        
        # Verifica che ci sia variabilità (jitter funziona)
        assert len(set(delays)) > 1, "Jitter non applicato (tutti delay uguali)"
    
    def test_rate_limiter_enforces_min_interval(self):
        """
        REGRESSION TEST: Verifica che min_interval (1.0s) sia rispettato.
        
        Due richieste consecutive devono avere almeno 1.0s di distanza.
        """
        http_client = get_http_client()
        rate_limiter = http_client._get_rate_limiter("duckduckgo")
        
        # Prima richiesta
        start = time.time()
        rate_limiter.wait_sync()
        
        # Seconda richiesta immediata
        rate_limiter.wait_sync()
        elapsed = time.time() - start
        
        # Deve aver aspettato almeno min_interval (1.0s) + jitter (1-2s) = 2-3s
        assert elapsed >= 2.0, f"Rate limit non rispettato: elapsed {elapsed:.2f}s < 2.0s"
    
    def test_rate_limiter_thread_safe(self):
        """
        REGRESSION TEST: Verifica che RateLimiter sia thread-safe.
        
        Concurrent requests non devono causare race conditions.
        """
        import threading
        
        http_client = get_http_client()
        rate_limiter = http_client._get_rate_limiter("duckduckgo")
        rate_limiter.last_request_time = 0.0
        
        results = []
        errors = []
        
        def make_request():
            try:
                delay = rate_limiter.wait_sync()
                results.append(delay)
            except Exception as e:
                errors.append(e)
        
        # Lancia 5 thread concorrenti
        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verifica nessun errore
        assert len(errors) == 0, f"Errors in concurrent requests: {errors}"
        
        # Verifica che tutti i thread abbiano completato
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    
    def test_jitter_reduction_saves_time(self):
        """
        PERFORMANCE TEST: Verifica che jitter ridotto risparmi tempo.
        
        Con jitter 1-2s, 10 richieste dovrebbero richiedere ~20-30s
        (vs ~40-70s con jitter 3-6s vecchio).
        """
        http_client = get_http_client()
        rate_limiter = http_client._get_rate_limiter("duckduckgo")
        rate_limiter.last_request_time = 0.0
        
        # Simula 10 richieste
        start = time.time()
        for _ in range(10):
            rate_limiter.wait_sync()
        elapsed = time.time() - start
        
        # Con jitter 1-2s: 10 * (1.0 + 1.5 avg) = ~25s
        # Tolleranza: 20-35s (per variabilità jitter)
        assert 20.0 <= elapsed <= 35.0, f"Tempo {elapsed:.1f}s fuori range atteso [20, 35]s"
        
        # Verifica saving vs vecchio jitter (3-6s)
        # Vecchio: 10 * (1.0 + 4.5 avg) = ~55s
        # Saving atteso: ~30s (55 - 25)
        old_expected = 55.0
        saving = old_expected - elapsed
        assert saving >= 20.0, f"Saving {saving:.1f}s < 20s atteso"


class TestDDGJitterEdgeCases:
    """Test edge cases per DDG jitter."""
    
    def test_jitter_min_equals_max(self):
        """
        EDGE CASE: Se jitter_min == jitter_max, usa valore fisso.
        
        Verifica che il codice gestisca questo caso senza crash.
        """
        from src.utils.http_client import RateLimiter
        
        limiter = RateLimiter(min_interval=1.0, jitter_min=2.0, jitter_max=2.0)
        limiter.last_request_time = time.time()  # Set to now to force min_interval wait
        
        time.sleep(0.1)  # Small delay to ensure elapsed < min_interval
        delay = limiter.get_delay()
        
        # Deve usare jitter_min fisso (linea 106 http_client.py)
        # base_delay ~= 0.9s (1.0 - 0.1), jitter = 2.0 → total ~= 2.9s
        assert 2.8 <= delay <= 3.1, f"Expected ~3.0s (0.9 + 2.0), got {delay:.2f}s"
    
    def test_first_request_no_wait(self):
        """
        EDGE CASE: Prima richiesta (last_request_time = 0) non deve aspettare min_interval.
        
        Solo jitter viene applicato.
        """
        from src.utils.http_client import RateLimiter
        
        limiter = RateLimiter(min_interval=1.0, jitter_min=1.0, jitter_max=2.0)
        # last_request_time = 0.0 (default)
        
        delay = limiter.get_delay()
        
        # Elapsed molto alto → base_delay = 0, solo jitter
        assert 1.0 <= delay <= 2.0, f"First request delay {delay:.2f}s fuori range [1.0, 2.0]"
    
    def test_zero_jitter_works(self):
        """
        EDGE CASE: jitter_min = jitter_max = 0 (come Brave/Serper).
        
        Verifica che funzioni senza crash.
        """
        from src.utils.http_client import RateLimiter
        
        limiter = RateLimiter(min_interval=2.0, jitter_min=0.0, jitter_max=0.0)
        limiter.last_request_time = 0.0
        
        delay = limiter.get_delay()
        
        # Solo min_interval, no jitter
        assert delay == 0.0, f"Expected 0.0s (first request, no jitter), got {delay:.2f}s"


# ============================================
# INTEGRATION TEST (richiede DDG funzionante)
# ============================================
@pytest.mark.integration
@pytest.mark.skip(reason="Integration test - run manually with: pytest -m integration")
class TestDDGJitterIntegration:
    """Integration test con DDG reale (opzionale)."""
    
    def test_ddg_search_with_reduced_jitter(self):
        """
        INTEGRATION TEST: Verifica che DDG non banni con jitter ridotto.
        
        Esegue 5 ricerche consecutive e verifica che non ci siano ban.
        """
        from src.ingestion.search_provider import get_search_provider
        
        provider = get_search_provider()
        
        # 5 ricerche consecutive
        queries = [
            "football injury news",
            "soccer team lineup",
            "football transfer news",
            "soccer match preview",
            "football squad update"
        ]
        
        results_count = []
        errors = []
        
        for query in queries:
            try:
                results = provider.search(query, num_results=3)
                results_count.append(len(results))
            except Exception as e:
                errors.append(str(e))
        
        # Verifica nessun errore di ban
        ban_errors = [e for e in errors if "403" in e or "ban" in e.lower() or "block" in e.lower()]
        assert len(ban_errors) == 0, f"DDG ban detected: {ban_errors}"
        
        # Verifica che almeno alcune ricerche abbiano ritornato risultati
        successful = sum(1 for c in results_count if c > 0)
        assert successful >= 3, f"Solo {successful}/5 ricerche riuscite (possibile ban)"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
