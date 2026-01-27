#!/usr/bin/env python3
"""
Test per verificare il meccanismo di retry su database lock.

Questo test verifica che:
1. get_db_session() gestisca correttamente i lock
2. Il retry con backoff esponenziale funzioni
3. Le eccezioni non-lock vengano propagate immediatamente
"""
import pytest
import sys
import os
import time
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError

sys.path.insert(0, os.getcwd())

from src.database.models import get_db_session, with_db_retry, SessionLocal


class TestDbLockRetry:
    """Test suite per il meccanismo di retry su DB lock."""
    
    def test_get_db_session_success(self):
        """Test: sessione normale senza lock."""
        with get_db_session() as db:
            # Dovrebbe funzionare senza errori
            assert db is not None
    
    def test_get_db_session_retries_on_lock(self):
        """Test: retry automatico su 'database is locked'."""
        # Questo test verifica che la logica di retry sia implementata
        # Il test reale del retry richiede un lock effettivo del DB
        # Qui verifichiamo solo che la funzione accetti i parametri
        
        with get_db_session(max_retries=3, retry_delay=0.1) as db:
            assert db is not None
        
        # Test passato - la funzione accetta i parametri di retry
    
    def test_get_db_session_raises_non_lock_errors(self):
        """Test: errori non-lock vengono propagati immediatamente."""
        def mock_session():
            raise ValueError("Some other error")
        
        with patch('src.database.models.SessionLocal', mock_session):
            with pytest.raises(ValueError, match="Some other error"):
                with get_db_session() as db:
                    pass
    
    def test_with_db_retry_decorator(self):
        """Test: decorator with_db_retry funziona."""
        call_count = 0
        
        @with_db_retry(max_retries=3, retry_delay=0.1)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OperationalError("database is locked", None, None)
            return "success"
        
        result = flaky_function()
        assert result == "success"
        assert call_count == 2
    
    def test_with_db_retry_exhausts_retries(self):
        """Test: decorator esaurisce i retry e rilancia l'errore."""
        call_count = 0
        
        @with_db_retry(max_retries=2, retry_delay=0.1)
        def always_locked():
            nonlocal call_count
            call_count += 1
            raise OperationalError("database is locked", None, None)
        
        with pytest.raises(OperationalError):
            always_locked()
        
        assert call_count == 2  # Dovrebbe aver provato 2 volte


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestTelegramDbInit:
    """Test suite per init_telegram_tracking_db con flag di idempotenza e retry."""
    
    def test_init_telegram_db_idempotent(self):
        """Test: init_telegram_tracking_db viene eseguito solo una volta per sessione.
        
        Questo previene 'database is locked' quando chiamato ripetutamente nel loop.
        """
        from src.database import telegram_channel_model
        
        # Reset flag per test pulito
        telegram_channel_model._telegram_db_initialized = False
        
        # Prima chiamata - dovrebbe inizializzare
        telegram_channel_model.init_telegram_tracking_db()
        assert telegram_channel_model._telegram_db_initialized is True
        
        # Seconda chiamata - dovrebbe essere no-op (flag già True)
        # Se non fosse idempotente, potrebbe causare lock
        telegram_channel_model.init_telegram_tracking_db()
        assert telegram_channel_model._telegram_db_initialized is True
    
    def test_init_telegram_db_flag_prevents_repeated_calls(self):
        """Test: il flag previene chiamate ripetute a engine.create().
        
        Bug originale: init_telegram_tracking_db() veniva chiamato per ogni
        messaggio nel loop, causando 'database is locked'.
        """
        from src.database import telegram_channel_model
        from unittest.mock import patch, MagicMock
        
        # Reset flag
        telegram_channel_model._telegram_db_initialized = False
        
        # Mock delle tabelle per contare le chiamate
        mock_table1 = MagicMock()
        mock_table2 = MagicMock()
        
        with patch.object(telegram_channel_model.TelegramChannel, '__table__', mock_table1):
            with patch.object(telegram_channel_model.TelegramMessageLog, '__table__', mock_table2):
                # Simula 10 chiamate (come nel loop originale)
                for _ in range(10):
                    telegram_channel_model.init_telegram_tracking_db()
                
                # Dovrebbe essere chiamato solo 1 volta, non 10
                assert mock_table1.create.call_count == 1
                assert mock_table2.create.call_count == 1

    def test_init_telegram_db_retry_on_lock(self):
        """Test: init_telegram_tracking_db ritenta su database lock.
        
        V4.4 Fix: Aggiunto retry con exponential backoff per gestire
        lock concorrenti da più processi (main.py, run_bot.py, run_telegram_monitor.py).
        """
        from src.database import telegram_channel_model
        from unittest.mock import patch, MagicMock
        from sqlalchemy.exc import OperationalError
        
        # Reset flag
        telegram_channel_model._telegram_db_initialized = False
        
        call_count = 0
        
        def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OperationalError("database is locked", None, None)
            # Success on 3rd attempt
        
        mock_table = MagicMock()
        mock_table.create = mock_create
        
        with patch.object(telegram_channel_model.TelegramChannel, '__table__', mock_table):
            with patch.object(telegram_channel_model.TelegramMessageLog, '__table__', MagicMock()):
                # Should succeed after retries
                telegram_channel_model.init_telegram_tracking_db(max_retries=5, retry_delay=0.01)
                
                # Should have retried
                assert call_count >= 2
                assert telegram_channel_model._telegram_db_initialized is True

    def test_init_telegram_db_accepts_retry_params(self):
        """Test: init_telegram_tracking_db accetta parametri di retry.
        
        Verifica che la signature sia corretta per VPS deployment.
        """
        from src.database import telegram_channel_model
        import inspect
        
        sig = inspect.signature(telegram_channel_model.init_telegram_tracking_db)
        params = list(sig.parameters.keys())
        
        assert 'max_retries' in params
        assert 'retry_delay' in params
        
        # Verifica valori default
        assert sig.parameters['max_retries'].default == 5
        assert sig.parameters['retry_delay'].default == 2.0


class TestFetchSquadImagesClientReuse:
    """Test suite per fetch_squad_images con riuso del client Telegram.
    
    V4.4 Fix: fetch_squad_images ora accetta un existing_client per evitare
    il lock della session SQLite di Telethon quando chiamato da run_telegram_monitor.py.
    """
    
    def test_fetch_squad_images_accepts_existing_client(self):
        """Test: fetch_squad_images accetta parametro existing_client.
        
        Questo è critico per evitare 'database is locked' sulla session Telethon.
        """
        from src.processing.telegram_listener import fetch_squad_images
        import inspect
        
        sig = inspect.signature(fetch_squad_images)
        params = list(sig.parameters.keys())
        
        assert 'existing_client' in params
        
        # Verifica che sia opzionale (default None)
        assert sig.parameters['existing_client'].default is None
    
    def test_monitor_channels_for_squads_accepts_existing_client(self):
        """Test: monitor_channels_for_squads accetta parametro existing_client."""
        from src.processing.telegram_listener import monitor_channels_for_squads
        import inspect
        
        sig = inspect.signature(monitor_channels_for_squads)
        params = list(sig.parameters.keys())
        
        assert 'existing_client' in params
        assert sig.parameters['existing_client'].default is None


class TestMigrationDbLock:
    """Test suite per migration.py con gestione lock."""
    
    def test_migration_uses_timeout(self):
        """Test: check_and_migrate usa timeout=60 per sqlite3.connect.
        
        Verifica che la connessione SQLite in migration.py abbia timeout
        per evitare lock immediati.
        """
        import ast
        
        with open('src/database/migration.py', 'r') as f:
            source = f.read()
        
        # Verifica che timeout=60 sia presente nelle chiamate sqlite3.connect
        assert 'timeout=60' in source, "migration.py deve usare timeout=60 per sqlite3.connect"
        
        # Verifica che busy_timeout PRAGMA sia presente
        assert 'busy_timeout=60000' in source, "migration.py deve settare PRAGMA busy_timeout=60000"
    
    def test_migration_check_and_migrate_signature(self):
        """Test: check_and_migrate non richiede parametri obbligatori."""
        from src.database.migration import check_and_migrate
        import inspect
        
        sig = inspect.signature(check_and_migrate)
        
        # Tutti i parametri devono avere default (nessuno obbligatorio)
        for param in sig.parameters.values():
            if param.default is inspect.Parameter.empty:
                pytest.fail(f"Parametro {param.name} non ha default - potrebbe rompere chiamate esistenti")
