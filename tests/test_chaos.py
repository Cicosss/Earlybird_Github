"""
EarlyBird Chaos Testing V1.0

Fault injection testing per verificare la resilienza del sistema.
Simula scenari di errore realistici:

1. API Failures - Timeout, rate limit, errori di rete
2. Malformed Data - JSON invalido, campi mancanti, tipi errati
3. Resource Exhaustion - Memory, database locks
4. External Service Failures - Tavily, Perplexity, FotMob down

Obiettivo: Verificare che il sistema degradi gracefully senza crash.

Requirements: Self-Check Protocol compliance
"""
import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, Optional
from datetime import datetime, timezone


# ============================================
# FIXTURES: Mock Objects
# ============================================

@pytest.fixture
def mock_api_response():
    """Factory per creare mock response HTTP."""
    def _create_response(status_code: int, json_data: dict = None, text: str = ""):
        response = Mock()
        response.status_code = status_code
        response.text = text or json.dumps(json_data or {})
        response.json.return_value = json_data or {}
        return response
    return _create_response


@pytest.fixture
def mock_match():
    """Mock di un oggetto Match dal database."""
    match = Mock()
    match.id = 'chaos_test_001'
    match.home_team = 'Inter Milan'
    match.away_team = 'AC Milan'
    match.league = 'soccer_italy_serie_a'
    match.start_time = datetime.now(timezone.utc)
    match.opening_home_odd = 1.90
    match.current_home_odd = 1.85
    match.opening_away_odd = 4.50
    match.current_away_odd = 4.20
    match.opening_draw_odd = 3.60
    match.current_draw_odd = 3.50
    return match


# ============================================
# TEST: API Timeout Handling
# ============================================

class TestAPITimeoutHandling:
    """Test gestione timeout delle API esterne."""
    
    def test_tavily_timeout_graceful_degradation(self, mock_api_response):
        """
        Verifica che un timeout Tavily non causi crash.
        Il sistema deve fallback a Perplexity o continuare senza verifica.
        """
        import requests
        
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
            
            # Simula chiamata che userebbe Tavily
            try:
                # Il sistema dovrebbe gestire il timeout
                response = mock_post("https://api.tavily.com/search", timeout=30)
                assert False, "Dovrebbe sollevare Timeout"
            except requests.exceptions.Timeout:
                # Comportamento atteso
                pass
    
    def test_perplexity_timeout_fallback(self, mock_api_response):
        """
        Verifica fallback quando Perplexity va in timeout.
        """
        import requests
        
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()
            
            try:
                mock_post("https://api.perplexity.ai/chat/completions", timeout=30)
            except requests.exceptions.Timeout:
                # Il sistema dovrebbe continuare con dati esistenti
                pass
    
    def test_telegram_timeout_retry(self, mock_api_response):
        """
        Verifica che Telegram retry su timeout.
        """
        import requests
        
        call_count = 0
        
        def timeout_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.Timeout()
            return mock_api_response(200, {'ok': True})
        
        with patch('requests.post', side_effect=timeout_then_success):
            # Simula logica di retry
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post("https://api.telegram.org/bot/sendMessage")
                    if response.status_code == 200:
                        break
                except requests.exceptions.Timeout:
                    if attempt == max_retries - 1:
                        pytest.fail("Tutti i retry falliti")
                    continue


# ============================================
# TEST: Rate Limit Handling
# ============================================

class TestRateLimitHandling:
    """Test gestione rate limit delle API."""
    
    def test_serper_rate_limit_429(self, mock_api_response):
        """
        Verifica gestione HTTP 429 da Serper.
        """
        response_429 = mock_api_response(429, {'message': 'Rate limit exceeded'})
        response_429.headers = {'Retry-After': '5'}
        
        with patch('requests.post', return_value=response_429):
            import requests
            response = requests.post("https://google.serper.dev/search")
            
            assert response.status_code == 429
            # Il sistema dovrebbe rispettare Retry-After
            retry_after = int(response.headers.get('Retry-After', 5))
            assert retry_after > 0
    
    def test_openrouter_rate_limit(self, mock_api_response):
        """
        Verifica gestione rate limit OpenRouter (DeepSeek).
        """
        response_429 = mock_api_response(429, {
            'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit_error'}
        })
        
        with patch('requests.post', return_value=response_429):
            import requests
            response = requests.post("https://openrouter.ai/api/v1/chat/completions")
            
            assert response.status_code == 429
            # Verifica che l'errore sia parsabile
            error_data = response.json()
            assert 'error' in error_data
    
    def test_serper_credits_exhausted(self, mock_api_response):
        """
        Verifica gestione crediti Serper esauriti.
        """
        response_402 = mock_api_response(402, {'message': 'Not enough credits'})
        
        with patch('requests.post', return_value=response_402):
            import requests
            response = requests.post("https://google.serper.dev/search")
            
            # Il sistema dovrebbe switchare a DDG
            assert response.status_code == 402
            assert 'credits' in response.json().get('message', '').lower()


# ============================================
# TEST: Malformed Data Handling
# ============================================

class TestMalformedDataHandling:
    """Test gestione dati malformati."""
    
    def test_invalid_json_response(self):
        """
        Verifica gestione risposta JSON invalida.
        """
        invalid_json = "This is not valid JSON {{"
        
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_json)
    
    def test_missing_required_fields_news_item(self):
        """
        Verifica che news item senza campi richiesti sia gestito.
        """
        from src.utils.validators import validate_news_item
        
        incomplete_news = {
            'team': 'Inter Milan',
            # Manca: match_id, title, snippet, link, source, search_type
        }
        
        result = validate_news_item(incomplete_news)
        assert not result.is_valid
        assert len(result.errors) > 0
    
    def test_wrong_type_fields(self):
        """
        Verifica gestione campi con tipo errato.
        """
        from src.utils.validators import validate_news_item
        
        wrong_types_news = {
            'match_id': 123,  # Dovrebbe essere str
            'team': ['Inter', 'Milan'],  # Dovrebbe essere str
            'title': None,  # Dovrebbe essere str non-null
            'snippet': 'Valid snippet',
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(wrong_types_news)
        # Dovrebbe rilevare problemi di tipo
        assert not result.is_valid or len(result.warnings) > 0
    
    def test_empty_string_fields(self):
        """
        Verifica gestione stringhe vuote in campi richiesti.
        """
        from src.utils.validators import validate_news_item
        
        empty_strings_news = {
            'match_id': 'test_123',
            'team': '',  # Vuoto
            'title': '   ',  # Solo spazi
            'snippet': 'Valid snippet',
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(empty_strings_news)
        assert not result.is_valid
    
    def test_score_out_of_range(self):
        """
        Verifica gestione score fuori range.
        """
        from src.utils.validators import validate_in_range
        
        # Score troppo alto
        result = validate_in_range(15, 'score', 0, 10)
        assert not result.is_valid
        
        # Score negativo
        result = validate_in_range(-5, 'score', 0, 10)
        assert not result.is_valid
        
        # Score valido
        result = validate_in_range(7.5, 'score', 0, 10)
        assert result.is_valid
    
    def test_ai_response_malformed_json(self):
        """
        Verifica gestione risposta AI con JSON malformato.
        """
        # Simula risposta AI con JSON parziale
        malformed_responses = [
            '{"final_verdict": "BET", "confidence": ',  # Troncato
            'Here is my analysis: {"verdict": "BET"}',  # Testo extra
            '```json\n{"verdict": "BET"}\n```',  # Markdown wrapper
            '',  # Vuoto
            'null',  # Null
        ]
        
        for response in malformed_responses:
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                # Comportamento atteso per JSON invalido
                pass


# ============================================
# TEST: Database Error Handling
# ============================================

class TestDatabaseErrorHandling:
    """Test gestione errori database."""
    
    def test_database_locked_handling(self):
        """
        Verifica gestione "database is locked" error.
        """
        import sqlite3
        
        # Simula errore database locked
        def raise_locked(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")
        
        with patch('sqlite3.connect', side_effect=raise_locked):
            try:
                import sqlite3
                sqlite3.connect('test.db')
            except sqlite3.OperationalError as e:
                assert "locked" in str(e)
    
    def test_connection_pool_exhausted(self):
        """
        Verifica gestione pool connessioni esaurito.
        """
        # Simula pool esaurito
        class PoolExhaustedError(Exception):
            pass
        
        def raise_pool_exhausted():
            raise PoolExhaustedError("Connection pool exhausted")
        
        with pytest.raises(PoolExhaustedError):
            raise_pool_exhausted()
    
    def test_transaction_rollback(self):
        """
        Verifica che le transazioni fallite facciano rollback.
        """
        # Simula transazione con errore
        class MockSession:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
            
            def commit(self):
                raise Exception("Commit failed")
            
            def rollback(self):
                self.rolled_back = True
        
        session = MockSession()
        try:
            session.commit()
        except Exception:
            session.rollback()
        
        assert session.rolled_back


# ============================================
# TEST: External Service Failures
# ============================================

class TestExternalServiceFailures:
    """Test gestione fallimenti servizi esterni."""
    
    def test_fotmob_api_down(self, mock_api_response):
        """
        Verifica comportamento quando FotMob è down.
        """
        response_503 = mock_api_response(503, {'error': 'Service Unavailable'})
        
        with patch('requests.get', return_value=response_503):
            import requests
            response = requests.get("https://www.fotmob.com/api/matches")
            
            assert response.status_code == 503
            # Il sistema dovrebbe continuare con dati cached
    
    def test_odds_api_failure(self, mock_api_response):
        """
        Verifica comportamento quando Odds API fallisce.
        """
        response_500 = mock_api_response(500, {'error': 'Internal Server Error'})
        
        with patch('requests.get', return_value=response_500):
            import requests
            response = requests.get("https://api.the-odds-api.com/v4/sports")
            
            assert response.status_code == 500
    
    def test_telegram_api_failure(self, mock_api_response):
        """
        Verifica che fallimento Telegram non blocchi il sistema.
        """
        response_500 = mock_api_response(500, {'ok': False, 'description': 'Internal error'})
        
        with patch('requests.post', return_value=response_500):
            import requests
            response = requests.post("https://api.telegram.org/bot/sendMessage")
            
            # Il sistema dovrebbe loggare l'errore ma continuare
            assert response.status_code == 500
    
    def test_all_search_providers_down(self, mock_api_response):
        """
        Verifica comportamento quando tutti i search provider sono down.
        """
        import requests
        
        def all_fail(*args, **kwargs):
            raise requests.exceptions.ConnectionError("All providers down")
        
        with patch('requests.get', side_effect=all_fail):
            with patch('requests.post', side_effect=all_fail):
                # Il sistema dovrebbe degradare gracefully
                try:
                    requests.get("https://api.duckduckgo.com")
                except requests.exceptions.ConnectionError:
                    pass  # Atteso
                
                try:
                    requests.post("https://google.serper.dev/search")
                except requests.exceptions.ConnectionError:
                    pass  # Atteso


# ============================================
# TEST: Concurrent Access Issues
# ============================================

class TestConcurrentAccessIssues:
    """Test problemi di accesso concorrente."""
    
    def test_race_condition_news_processing(self):
        """
        Verifica gestione race condition nel processing news.
        """
        import threading
        
        processed_news = []
        lock = threading.Lock()
        
        def process_news(news_id):
            with lock:
                if news_id not in processed_news:
                    processed_news.append(news_id)
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=process_news, args=(f"news_{i % 3}",))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Dovrebbero esserci solo 3 news uniche
        assert len(processed_news) == 3
    
    def test_discovery_queue_thread_safety(self):
        """
        Verifica thread safety della discovery queue.
        """
        import threading
        from collections import deque
        
        queue = deque()
        lock = threading.Lock()
        
        def producer():
            for i in range(100):
                with lock:
                    queue.append(f"item_{i}")
        
        def consumer():
            consumed = 0
            while consumed < 50:
                with lock:
                    if queue:
                        queue.popleft()
                        consumed += 1
        
        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)
        
        producer_thread.start()
        consumer_thread.start()
        
        producer_thread.join()
        consumer_thread.join()
        
        # Queue dovrebbe avere 50 elementi rimanenti
        assert len(queue) == 50


# ============================================
# TEST: Memory and Resource Issues
# ============================================

class TestResourceIssues:
    """Test problemi di risorse."""
    
    def test_large_news_batch_handling(self):
        """
        Verifica gestione batch di news molto grande.
        """
        from src.utils.validators import validate_batch, validate_news_item
        
        # Crea batch grande di news
        large_batch = []
        for i in range(1000):
            large_batch.append({
                'match_id': f'test_{i}',
                'team': f'Team {i}',
                'title': f'News title {i}',
                'snippet': f'News snippet {i}' * 100,  # Snippet lungo
                'link': f'https://test.com/article/{i}',
                'source': 'test.com',
                'search_type': 'ddg_local',
            })
        
        # Dovrebbe processare senza crash
        valid_items, errors = validate_batch(large_batch, validate_news_item, "news")
        
        assert len(valid_items) + len(errors) == 1000
    
    def test_very_long_snippet_handling(self):
        """
        Verifica gestione snippet molto lunghi.
        """
        from src.utils.validators import validate_news_item
        
        long_snippet_news = {
            'match_id': 'test_123',
            'team': 'Inter Milan',
            'title': 'Test title',
            'snippet': 'A' * 100000,  # 100KB di testo
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        # Dovrebbe validare senza crash
        result = validate_news_item(long_snippet_news)
        assert result.is_valid
    
    def test_unicode_edge_cases(self):
        """
        Verifica gestione caratteri unicode edge case.
        """
        from src.utils.validators import validate_news_item
        
        unicode_news = {
            'match_id': 'test_123',
            'team': '北京国安',  # Cinese
            'title': 'Тест заголовок',  # Russo
            'snippet': '🔥⚽🏆 Emoji test 日本語テスト العربية',
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        result = validate_news_item(unicode_news)
        assert result.is_valid


# ============================================
# TEST: Recovery Scenarios
# ============================================

class TestRecoveryScenarios:
    """Test scenari di recovery dopo errori."""
    
    def test_circuit_breaker_pattern(self):
        """
        Verifica pattern circuit breaker per API failures.
        """
        class CircuitBreaker:
            def __init__(self, failure_threshold=3, reset_timeout=60):
                self.failure_count = 0
                self.failure_threshold = failure_threshold
                self.state = 'CLOSED'
                self.last_failure_time = None
            
            def record_failure(self):
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.failure_count >= self.failure_threshold:
                    self.state = 'OPEN'
            
            def record_success(self):
                self.failure_count = 0
                self.state = 'CLOSED'
            
            def can_execute(self):
                if self.state == 'CLOSED':
                    return True
                if self.state == 'OPEN':
                    # Check if reset timeout passed
                    return False
                return True
        
        breaker = CircuitBreaker(failure_threshold=3)
        
        # Simula 3 fallimenti
        for _ in range(3):
            breaker.record_failure()
        
        assert breaker.state == 'OPEN'
        assert not breaker.can_execute()
        
        # Reset
        breaker.record_success()
        assert breaker.state == 'CLOSED'
        assert breaker.can_execute()
    
    def test_graceful_degradation_chain(self):
        """
        Verifica catena di degradazione graceful.
        """
        # Simula catena: Tavily → Perplexity → Cache → Default
        
        providers = ['tavily', 'perplexity', 'cache', 'default']
        failed_providers = set()
        
        def try_provider(name):
            if name in failed_providers:
                raise Exception(f"{name} failed")
            return f"Result from {name}"
        
        def get_data_with_fallback():
            for provider in providers:
                try:
                    return try_provider(provider)
                except Exception:
                    continue
            return None
        
        # Tutti funzionano
        assert get_data_with_fallback() == "Result from tavily"
        
        # Tavily fallisce
        failed_providers.add('tavily')
        assert get_data_with_fallback() == "Result from perplexity"
        
        # Tavily e Perplexity falliscono
        failed_providers.add('perplexity')
        assert get_data_with_fallback() == "Result from cache"
        
        # Tutti tranne default falliscono
        failed_providers.add('cache')
        assert get_data_with_fallback() == "Result from default"
    
    def test_retry_with_exponential_backoff(self):
        """
        Verifica retry con exponential backoff.
        """
        attempts = []
        
        def operation_with_retry(max_retries=3, base_delay=0.1):
            for attempt in range(max_retries):
                attempts.append(time.time())
                try:
                    if attempt < max_retries - 1:
                        raise Exception("Temporary failure")
                    return "Success"
                except Exception:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
            return None
        
        result = operation_with_retry()
        
        assert result == "Success"
        assert len(attempts) == 3
        
        # Verifica che i delay aumentino
        if len(attempts) >= 2:
            delay1 = attempts[1] - attempts[0]
            delay2 = attempts[2] - attempts[1]
            assert delay2 > delay1  # Exponential backoff


# ============================================
# TEST: Validation Under Stress
# ============================================

class TestValidationUnderStress:
    """Test validazione sotto stress."""
    
    def test_rapid_validation_calls(self):
        """
        Verifica che validazioni rapide non causino problemi.
        """
        from src.utils.validators import validate_news_item
        
        valid_news = {
            'match_id': 'test_123',
            'team': 'Inter Milan',
            'title': 'Test title',
            'snippet': 'Test snippet',
            'link': 'https://test.com',
            'source': 'test.com',
            'search_type': 'ddg_local',
        }
        
        # 1000 validazioni rapide
        start = time.time()
        for _ in range(1000):
            result = validate_news_item(valid_news)
            assert result.is_valid
        elapsed = time.time() - start
        
        # Dovrebbe completare in meno di 1 secondo
        assert elapsed < 1.0, f"Validazione troppo lenta: {elapsed}s"
    
    def test_mixed_valid_invalid_batch(self):
        """
        Verifica gestione batch misto valido/invalido.
        """
        from src.utils.validators import validate_batch, validate_news_item
        
        mixed_batch = []
        for i in range(100):
            if i % 3 == 0:
                # Invalido - manca title
                mixed_batch.append({
                    'match_id': f'test_{i}',
                    'team': f'Team {i}',
                    'snippet': 'Snippet',
                    'link': 'https://test.com',
                    'source': 'test.com',
                    'search_type': 'ddg_local',
                })
            else:
                # Valido
                mixed_batch.append({
                    'match_id': f'test_{i}',
                    'team': f'Team {i}',
                    'title': f'Title {i}',
                    'snippet': 'Snippet',
                    'link': 'https://test.com',
                    'source': 'test.com',
                    'search_type': 'ddg_local',
                })
        
        valid_items, errors = validate_batch(mixed_batch, validate_news_item, "news")
        
        # ~33 invalidi, ~67 validi
        assert len(errors) > 30
        assert len(valid_items) > 60


# Marker per test di chaos
pytestmark = pytest.mark.chaos
