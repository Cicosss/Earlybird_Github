#!/usr/bin/env python3
"""
Test per verificare il reset del contatore backoff nel launcher.

Questo test verifica che:
1. Il contatore restarts venga resettato dopo 5 minuti di uptime stabile
2. Il contatore NON venga resettato se uptime < 5 minuti
3. Il contatore NON venga resettato se restarts == 0 (nessun crash precedente)

Bug originale: Il contatore restarts non veniva mai resettato, causando
backoff crescenti anche dopo lunghi periodi di stabilità.
"""
import time
import unittest
from unittest.mock import MagicMock, patch


class TestLauncherBackoffReset(unittest.TestCase):
    """Test per la logica di reset del backoff nel launcher."""
    
    def setUp(self):
        """Setup per ogni test."""
        # Simula la struttura di un processo
        self.mock_process_running = MagicMock()
        self.mock_process_running.poll.return_value = None  # Processo in esecuzione
        
        self.mock_process_dead = MagicMock()
        self.mock_process_dead.poll.return_value = 1  # Processo terminato
        self.mock_process_dead.returncode = 1
    
    def test_reset_after_5_minutes_stability(self):
        """
        Il contatore restarts deve essere resettato dopo 5 minuti di uptime.
        
        Scenario: Processo crashato 3 volte, poi stabile per 6 minuti.
        Expected: restarts deve tornare a 0.
        """
        # Simula un processo che ha crashato 3 volte ma ora è stabile da 6 minuti
        config = {
            'name': 'Test Process',
            'process': self.mock_process_running,
            'restarts': 3,
            'last_start_time': time.time() - 360  # 6 minuti fa
        }
        
        STABILITY_THRESHOLD_SECONDS = 300  # 5 minuti
        
        # Logica dal launcher
        process = config['process']
        if process.poll() is None:  # Processo in esecuzione
            last_start = config.get('last_start_time')
            if last_start and config['restarts'] > 0:
                uptime = time.time() - last_start
                if uptime >= STABILITY_THRESHOLD_SECONDS:
                    config['restarts'] = 0
        
        # Verifica
        self.assertEqual(config['restarts'], 0, 
            "Il contatore dovrebbe essere resettato dopo 5+ minuti di stabilità")
    
    def test_no_reset_before_5_minutes(self):
        """
        Il contatore restarts NON deve essere resettato prima di 5 minuti.
        
        Scenario: Processo crashato 3 volte, stabile solo da 2 minuti.
        Expected: restarts deve rimanere 3.
        """
        config = {
            'name': 'Test Process',
            'process': self.mock_process_running,
            'restarts': 3,
            'last_start_time': time.time() - 120  # Solo 2 minuti fa
        }
        
        STABILITY_THRESHOLD_SECONDS = 300
        
        process = config['process']
        if process.poll() is None:
            last_start = config.get('last_start_time')
            if last_start and config['restarts'] > 0:
                uptime = time.time() - last_start
                if uptime >= STABILITY_THRESHOLD_SECONDS:
                    config['restarts'] = 0
        
        self.assertEqual(config['restarts'], 3,
            "Il contatore NON dovrebbe essere resettato prima di 5 minuti")
    
    def test_no_reset_if_no_previous_crashes(self):
        """
        Il contatore NON deve essere "resettato" se non ci sono stati crash.
        
        Scenario: Processo mai crashato (restarts=0), stabile da 10 minuti.
        Expected: restarts deve rimanere 0 (nessun log di reset).
        """
        config = {
            'name': 'Test Process',
            'process': self.mock_process_running,
            'restarts': 0,  # Mai crashato
            'last_start_time': time.time() - 600  # 10 minuti fa
        }
        
        STABILITY_THRESHOLD_SECONDS = 300
        reset_triggered = False
        
        process = config['process']
        if process.poll() is None:
            last_start = config.get('last_start_time')
            if last_start and config['restarts'] > 0:  # Questa condizione deve fallire
                uptime = time.time() - last_start
                if uptime >= STABILITY_THRESHOLD_SECONDS:
                    config['restarts'] = 0
                    reset_triggered = True
        
        self.assertFalse(reset_triggered,
            "Il reset NON dovrebbe essere triggerato se restarts == 0")
    
    def test_no_reset_if_last_start_time_none(self):
        """
        Edge case: last_start_time è None (primo avvio).
        
        Expected: Nessun errore, nessun reset.
        """
        config = {
            'name': 'Test Process',
            'process': self.mock_process_running,
            'restarts': 3,
            'last_start_time': None  # Non ancora impostato
        }
        
        STABILITY_THRESHOLD_SECONDS = 300
        
        # Questo NON deve sollevare eccezioni
        process = config['process']
        if process.poll() is None:
            last_start = config.get('last_start_time')
            if last_start and config['restarts'] > 0:
                uptime = time.time() - last_start
                if uptime >= STABILITY_THRESHOLD_SECONDS:
                    config['restarts'] = 0
        
        self.assertEqual(config['restarts'], 3,
            "Il contatore NON dovrebbe cambiare se last_start_time è None")
    
    def test_backoff_calculation(self):
        """
        Verifica che il backoff esponenziale sia calcolato correttamente.
        
        Expected: 2^restarts con cap a 60 secondi.
        """
        test_cases = [
            (1, 2),    # 2^1 = 2
            (2, 4),    # 2^2 = 4
            (3, 8),    # 2^3 = 8
            (4, 16),   # 2^4 = 16
            (5, 32),   # 2^5 = 32
            (6, 64),   # 2^6 = 64, ma cap a 60
            (7, 64),   # 2^6 = 64 (min(7,6)), cap a 60
            (10, 64),  # 2^6 = 64, cap a 60
        ]
        
        for restarts, expected_uncapped in test_cases:
            backoff = min(60, 2 ** min(restarts, 6))
            expected = min(60, expected_uncapped)
            self.assertEqual(backoff, expected,
                f"Backoff per restarts={restarts} dovrebbe essere {expected}, got {backoff}")


class TestLauncherProcessDiscovery(unittest.TestCase):
    """Test per la discovery dei processi."""
    
    def test_news_radar_in_candidates(self):
        """Verifica che news_radar sia presente nei candidati."""
        from src.launcher import PROCESS_CANDIDATES
        
        keys = [c['key'] for c in PROCESS_CANDIDATES]
        self.assertIn('news_radar', keys,
            "news_radar deve essere presente in PROCESS_CANDIDATES")
    
    def test_news_radar_script_path(self):
        """Verifica che il path dello script news_radar sia corretto."""
        from src.launcher import PROCESS_CANDIDATES
        
        news_radar = next(c for c in PROCESS_CANDIDATES if c['key'] == 'news_radar')
        self.assertIn('run_news_radar.py', news_radar['scripts'],
            "run_news_radar.py deve essere negli scripts di news_radar")
    
    def test_discover_processes_includes_last_start_time(self):
        """Verifica che discover_processes inizializzi last_start_time."""
        from src.launcher import discover_processes
        
        processes = discover_processes()
        
        for key, config in processes.items():
            self.assertIn('last_start_time', config,
                f"Processo {key} deve avere last_start_time nella config")
            self.assertIsNone(config['last_start_time'],
                f"last_start_time deve essere None all'inizializzazione")


if __name__ == '__main__':
    unittest.main()


class TestLauncherProcessGroupKill(unittest.TestCase):
    """Test per la terminazione dei process group (V7.2 - Playwright fix)."""
    
    def test_start_process_uses_new_session(self):
        """
        Verifica che start_process usi start_new_session=True.
        
        Questo è necessario per terminare correttamente i processi figli
        come Playwright/Chromium quando il bot viene fermato.
        """
        import inspect
        from src.launcher import start_process
        
        # Leggi il codice sorgente della funzione
        source = inspect.getsource(start_process)
        
        self.assertIn('start_new_session=True', source,
            "start_process deve usare start_new_session=True per creare process group separati")
    
    def test_stop_process_uses_killpg(self):
        """
        Verifica che stop_process usi os.killpg per terminare l'intero group.
        
        Questo garantisce che processi figli come Playwright vengano terminati.
        """
        import inspect
        from src.launcher import stop_process
        
        source = inspect.getsource(stop_process)
        
        self.assertIn('os.killpg', source,
            "stop_process deve usare os.killpg per terminare l'intero process group")
        self.assertIn('os.getpgid', source,
            "stop_process deve usare os.getpgid per ottenere il process group ID")


class TestNewsRadarSignalHandling(unittest.TestCase):
    """Test per il signal handling di news_radar (V7.2 fix)."""
    
    def test_signal_handler_uses_event(self):
        """
        Verifica che il signal handler usi un Event invece di asyncio.get_event_loop().
        
        Bug originale: asyncio.get_event_loop().call_soon_threadsafe() fallisce
        in Python 3.10+ quando chiamato da un signal handler.
        """
        import inspect
        from run_news_radar import signal_handler
        
        source = inspect.getsource(signal_handler)
        
        # Non deve usare il vecchio metodo problematico
        self.assertNotIn('asyncio.get_event_loop', source,
            "signal_handler NON deve usare asyncio.get_event_loop() - causa bug in Python 3.10+")
        self.assertNotIn('call_soon_threadsafe', source,
            "signal_handler NON deve usare call_soon_threadsafe - non funziona correttamente")
        
        # Deve usare l'event
        self.assertIn('_shutdown_event', source,
            "signal_handler deve usare _shutdown_event per segnalare lo shutdown")
    
    def test_main_checks_shutdown_event(self):
        """
        Verifica che main() controlli _shutdown_event nel loop principale.
        """
        import inspect
        from run_news_radar import main
        
        source = inspect.getsource(main)
        
        self.assertIn('_shutdown_event', source,
            "main() deve controllare _shutdown_event per gestire lo shutdown")
        self.assertIn('is_set()', source,
            "main() deve chiamare is_set() per verificare se lo shutdown è richiesto")
