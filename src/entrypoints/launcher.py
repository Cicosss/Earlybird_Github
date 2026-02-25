#!/usr/bin/env python3
"""
EarlyBird - Process Orchestrator (Supervisor)

Gestisce l'avvio e il riavvio automatico di:
1. src/main.py - Pipeline principale (Odds + News + Analysis)
2. src/entrypoints/run_bot.py - Telegram Bot (Comandi)
3. run_telegram_monitor.py - Telegram Monitor (Scraper)
4. run_news_radar.py - News Radar (Hunter Autonomo per leghe minori)

Auto-Restart: Se un processo muore, viene riavviato immediatamente.
Graceful Shutdown: Ctrl+C termina tutti i processi correttamente.
Dynamic Discovery: Verifica l'esistenza dei file prima di avviarli.

Historical Version: V3.7
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

# Setup path to import modules (fix for config module import)
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
sys.path.append(os.getcwd())

# Import orchestration metrics
# Import settings for service control flags
import config.settings as settings
from src.alerting.orchestration_metrics import start_metrics_collection, stop_metrics_collection

# Import centralized version tracking
from src.version import get_version_with_module

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Log version on import
logger.info(f"📦 {get_version_with_module('Launcher')}")

# Candidati per i processi (verifica esistenza dinamica)
PROCESS_CANDIDATES = [
    {"key": "main", "scripts": ["src/main.py"], "name": "Pipeline Principale"},
    {"key": "bot", "scripts": ["src/entrypoints/run_bot.py"], "name": "Telegram Bot (Comandi)"},
    {
        "key": "monitor",
        "scripts": [
            "run_telegram_monitor.py",
        ],  # Telegram Monitor script
        "name": "Telegram Monitor (Scraper)",
    },
    {"key": "news_radar", "scripts": ["run_news_radar.py"], "name": "News Radar (Hunter Autonomo)"},
]


def discover_processes() -> dict:
    """
    Scopre dinamicamente quali script esistono e costruisce la config.
    Supporta fallback per file rinominati (es. run_scraper.py -> run_telegram_monitor.py).
    """
    processes = {}

    for candidate in PROCESS_CANDIDATES:
        script_found = None

        # Cerca il primo script esistente nella lista
        for script in candidate["scripts"]:
            if os.path.exists(script):
                script_found = script
                break

        if script_found:
            processes[candidate["key"]] = {
                "cmd": [sys.executable, script_found],
                "name": candidate["name"],
                "script": script_found,
                "process": None,
                "restarts": 0,
                "last_start_time": None,  # Timestamp ultimo avvio per reset backoff
            }
            logger.info(f"✅ Trovato: {candidate['name']} -> {script_found}")
        else:
            logger.warning(f"⚠️ Non trovato: {candidate['name']} (cercato: {candidate['scripts']})")

    return processes


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=f"EarlyBird {get_version_with_module('Launcher')}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Componenti gestiti:
1. src/main.py - Pipeline principale (Odds + News + Analysis)
2. src/entrypoints/run_bot.py - Telegram Bot (Comandi)
3. run_telegram_monitor.py - Telegram Monitor (Scraper)  
4. run_news_radar.py - News Radar (Hunter Autonomo per leghe minori)

Modalità:
- --help     : Mostra questo aiuto
- --test     : Verifica disponibilità componenti senza avviare
- --status   : Mostra stato processi attivi
- default   : Avvia tutti i processi con monitoraggio

Examples:
    python src/entrypoints/launcher.py
    python src/entrypoints/launcher.py --test
    python src/entrypoints/launcher.py --status
        """,
    )

    parser.add_argument(
        "--test", action="store_true", help="Test component availability without starting"
    )

    parser.add_argument("--status", action="store_true", help="Show status of running processes")

    return parser.parse_args()


def check_component_health():
    """Verifica salute componenti senza avviare."""
    logger.info("🔍 Verifica salute componenti...")

    processes = discover_processes()
    if not processes:
        logger.error("❌ Nessun componente trovato!")
        return False

    logger.info(f"✅ Trovati {len(processes)} componenti:")

    all_ok = True
    for key, config in processes.items():
        script = config["script"]
        name = config["name"]

        # Check esistenza file
        if not os.path.exists(script):
            logger.error(f"❌ {name}: File non trovato ({script})")
            all_ok = False
            continue

        # Check eseguibilità
        if not os.access(script, os.X_OK):
            logger.warning(f"⚠️ {name}: File non eseguibile ({script})")

        # Check dependencies veloce
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f'import sys; sys.path.insert(0, "."); exec(open("{script}").read().split("if __name__")[0])',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"✅ {name}: OK")
            else:
                logger.warning(f"⚠️ {name}: Possibili problemi di import")
        except Exception as e:
            logger.warning(f"⚠️ {name}: Errore verifica - {str(e)[:50]}...")

    return all_ok


def show_process_status():
    """Mostra stato processi attivi."""
    logger.info("📊 Verifica stato processi...")

    # Check se processi EarlyBird sono in esecuzione
    try:
        result = subprocess.run(["pgrep", "-f", "earlybird"], capture_output=True, text=True)

        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            logger.info(f"✅ Trovati {len(pids)} processi EarlyBird attivi:")

            for pid in pids:
                try:
                    cmd_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "pid,cmd"], capture_output=True, text=True
                    )
                    if cmd_result.returncode == 0:
                        lines = cmd_result.stdout.strip().split("\n")
                        if len(lines) > 1:
                            logger.info(f"   PID {pid}: {lines[1].strip()}")
                except:
                    logger.info(f"   PID {pid}: (dettagli non disponibili)")
        else:
            logger.info("ℹ️ Nessun processo EarlyBird attivo")

    except Exception as e:
        logger.error(f"❌ Errore verifica stato: {e}")


# Processi da gestire (popolato dinamicamente)
PROCESSES = {}

# Flag per shutdown graceful
_shutdown_requested = False


def start_process(key: str) -> subprocess.Popen:
    """Avvia un processo e ritorna l'oggetto Popen."""
    config = PROCESSES[key]

    # Check service control flags before starting
    if key == "news_radar" and not settings.NEWS_RADAR_ENABLED:
        logger.info("⚠️ Service News Radar Disabled by config.")
        return None

    logger.info(f"🚀 Avvio {config['name']}...")

    # V7.2: start_new_session=True crea un nuovo process group
    # Questo permette di terminare tutti i processi figli (es. Playwright browser)
    process = subprocess.Popen(
        config["cmd"],
        stdout=sys.stdout,
        stderr=sys.stderr,
        bufsize=1,
        universal_newlines=True,
        start_new_session=True,  # Crea nuovo process group per cleanup completo
    )

    config["process"] = process
    config["last_start_time"] = time.time()  # Registra timestamp avvio
    logger.info(f"✅ {config['name']} avviato (PID: {process.pid})")
    return process


def stop_process(key: str):
    """
    Ferma un processo e tutti i suoi figli (es. Playwright browser) in modo graceful.

    V7.2: Usa os.killpg per terminare l'intero process group,
    garantendo che processi figli come Playwright/Chromium vengano chiusi.
    """
    config = PROCESSES[key]
    process = config["process"]

    if process and process.poll() is None:
        logger.info(f"🛑 Arresto {config['name']} (PID: {process.pid})...")

        try:
            # Invia SIGTERM all'intero process group
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)

            try:
                process.wait(timeout=5)
                logger.info(f"✅ {config['name']} terminato correttamente")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ {config['name']} non risponde, kill forzato...")
                os.killpg(pgid, signal.SIGKILL)
                process.wait()
        except (ProcessLookupError, OSError) as e:
            # Processo già terminato o errore nel trovare il group
            logger.warning(f"⚠️ {config['name']}: {e}")
            # Fallback al metodo standard
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                process.kill()
                process.wait()


def check_and_restart():
    """
    Controlla lo stato dei processi e riavvia quelli morti con exponential backoff.

    Logica backoff:
    - Ogni crash incrementa il contatore restarts
    - Backoff esponenziale: 2s, 4s, 8s, 16s, 32s, 64s (max 60s)
    - Reset del contatore dopo 5 minuti di uptime stabile (processo sano)
    - CPU PROTECTION: Se il processo crasha entro 10 secondi dall'avvio, attendi almeno 15 secondi
    """
    STABILITY_THRESHOLD_SECONDS = 300  # 5 minuti di uptime = processo stabile
    CRASH_DETECTION_WINDOW = 10  # secondi - se crasha prima, è un crash immediato
    MINIMUM_BACKOFF_FOR_FAST_CRASH = 15  # secondi - attesa minima per crash veloci

    for key, config in PROCESSES.items():
        process = config["process"]

        if process is None:
            # Primo avvio
            started_process = start_process(key)
            # If process was disabled and returned None, mark as intentionally skipped
            if started_process is None and key == "news_radar":
                config["process"] = None  # Keep None to prevent restart attempts
                config["restarts"] = 0  # No restarts for disabled services

        elif process.poll() is None:
            # Processo ancora in esecuzione - verifica stabilità per reset backoff
            last_start = config.get("last_start_time")
            if last_start and config["restarts"] > 0:
                uptime = time.time() - last_start
                if uptime >= STABILITY_THRESHOLD_SECONDS:
                    # Processo stabile da 5+ minuti, reset contatore
                    logger.info(
                        f"✅ {config['name']} stabile da {int(uptime / 60)}min, "
                        f"reset contatore restart (era {config['restarts']})"
                    )
                    config["restarts"] = 0

        else:
            # Processo morto - riavvia con backoff
            exit_code = process.returncode
            config["restarts"] += 1
            restarts = config["restarts"]

            # Calcola quanto tempo è rimasto in esecuzione prima del crash
            last_start = config.get("last_start_time")
            uptime_before_crash = time.time() - last_start if last_start else 0

            # CPU PROTECTION: Se il processo crasha entro 10 secondi, forza attesa minima di 15s
            # Questo previene loop infiniti quando il .env è mancante o ci sono errori di configurazione
            if uptime_before_crash < CRASH_DETECTION_WINDOW:
                backoff_seconds = max(
                    MINIMUM_BACKOFF_FOR_FAST_CRASH, min(60, 2 ** min(restarts, 6))
                )
                logger.warning(
                    f"⚠️ {config['name']} crashato in {uptime_before_crash:.1f}s (exit code: {exit_code}). "
                    f"CPU PROTECTION: Riavvio #{restarts} in {backoff_seconds}s..."
                )
            else:
                # Backoff esponenziale normale: 2s, 4s, 8s, 16s, 32s, max 60s
                backoff_seconds = min(60, 2 ** min(restarts, 6))
                logger.warning(
                    f"⚠️ {config['name']} terminato dopo {uptime_before_crash:.1f}s (exit code: {exit_code}). "
                    f"Riavvio #{restarts} in {backoff_seconds}s..."
                )

            # Backoff prima del riavvio
            time.sleep(backoff_seconds)
            started_process = start_process(key)
            # If process was disabled and returned None, mark as intentionally skipped
            if started_process is None and key == "news_radar":
                config["process"] = None  # Keep None to prevent restart attempts
                config["restarts"] = 0  # No restarts for disabled services


def signal_handler(signum, frame):
    """Gestisce i segnali di terminazione."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("\n🛑 Segnale di arresto ricevuto. Chiusura in corso...")


def main():
    """Entry point dell'orchestrator."""
    global _shutdown_requested, PROCESSES

    # Parse arguments
    args = parse_args()

    # Handle special modes
    if args.test:
        return 0 if check_component_health() else 1

    if args.status:
        show_process_status()
        return 0

    # ✅ NEW: Pre-flight validation BEFORE launching any processes
    try:
        from src.utils.startup_validator import validate_startup_or_exit

        validate_startup_or_exit()
    except ImportError as e:
        logger.warning(f"⚠️ Startup validator not available: {e}")
        logger.warning("⚠️ Proceeding without validation checks")

    # Normal startup mode
    logger.info("=" * 60)
    logger.info("🦅 EARLYBIRD V3.7 - ORCHESTRATOR AVVIATO")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Scoperta dinamica dei processi
    logger.info("🔍 Ricerca script disponibili...")
    PROCESSES = discover_processes()

    if not PROCESSES:
        logger.error("❌ Nessun processo trovato! Verifica che i file esistano.")
        sys.exit(1)

    logger.info(f"📋 Processi da gestire: {len(PROCESSES)}")

    # Registra handler per segnali
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Avvio iniziale
        for key in PROCESSES:
            start_process(key)
            time.sleep(2)  # Pausa tra avvii per evitare conflitti

        logger.info("✅ Tutti i processi avviati. Monitoraggio attivo...")

        # Start orchestration metrics collection
        try:
            start_metrics_collection()
            logger.info("✅ Orchestration metrics collector started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start metrics collection: {e}")

        # Loop di monitoraggio
        while not _shutdown_requested:
            check_and_restart()
            time.sleep(5)  # Check ogni 5 secondi

    except KeyboardInterrupt:
        logger.info("\n🛑 Interruzione da tastiera (Ctrl+C)")
    finally:
        # Shutdown graceful
        logger.info("🔄 Arresto di tutti i processi...")

        # Stop orchestration metrics collection
        try:
            stop_metrics_collection()
            logger.info("✅ Orchestration metrics collector stopped")
        except Exception as e:
            logger.warning(f"⚠️ Failed to stop metrics collection: {e}")

        for key in PROCESSES:
            stop_process(key)

        logger.info("=" * 60)
        logger.info("🦅 EARLYBIRD ORCHESTRATOR TERMINATO")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
