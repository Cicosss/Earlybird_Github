#!/usr/bin/env python3
"""
EarlyBird Telegram Monitor - Squad Image Scraper

Monitora canali Telegram 24/7 per immagini formazioni.
Estrà immagini, analizza con AI, salva in database.

Separato dal Bot (comandi) per evitare conflitti.

V2.0: Intelligent feature detection via startup_validator.is_feature_disabled()
      - Exits gracefully if 'telegram_monitor' feature is disabled
      - Logs clear status messages for disabled features
"""

import argparse
import asyncio
import logging
import os
import sys

# ============================================
# UVLOOP OPTIMIZATION (Rust-based event loop)
# Must be set BEFORE any other asyncio usage
# ============================================
try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _UVLOOP_ENABLED = True
except ImportError:
    _UVLOOP_ENABLED = False

# Setup path
sys.path.append(os.getcwd())

from dotenv import load_dotenv

load_dotenv()

# V2.0: Import startup validator for intelligent feature detection
try:
    from src.utils.startup_validator import is_feature_disabled

    _STARTUP_VALIDATOR_AVAILABLE = True
except ImportError:
    _STARTUP_VALIDATOR_AVAILABLE = False

    def is_feature_disabled(feature: str) -> bool:
        """Fallback: no features are disabled if validator unavailable."""
        return False


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EarlyBird Telegram Monitor - Squad Image Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Funzionalità:
- Monitoraggio canali Telegram 24/7
- Estrazione immagini formazioni
- Analisi AI delle squadre
- Salvataggio database

Modalità:
- --help   : Mostra questo aiuto
- --test   : Verifica configurazione senza avviare
- default : Avvia monitoraggio 24/7

Examples:
    python run_telegram_monitor.py
    python run_telegram_monitor.py --test
        """,
    )

    parser.add_argument(
        "--test", action="store_true", help="Test configuration without starting monitor"
    )

    return parser.parse_args()


def test_monitor_configuration():
    """Verifica configurazione monitor senza avviare."""
    logger.info("📡 Verifica configurazione Telegram Monitor...")

    # Check environment variables
    required_vars = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
    missing_vars = []

    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            logger.info(f"✅ {var}: Configurato")

    if missing_vars:
        logger.error(f"❌ Variabili mancanti: {', '.join(missing_vars)}")
        return False

    # Test import delle dipendenze
    try:
        from src.database.models import init_db

        logger.info("✅ Import dipendenze: OK")

        # Test database
        init_db()
        logger.info("✅ Database connection: OK")

        # Test Telegram client creation (senza connettere)
        telegram_api_id = os.getenv("TELEGRAM_API_ID")
        telegram_api_hash = os.getenv("TELEGRAM_API_HASH")
        if telegram_api_id and telegram_api_hash:
            logger.info("✅ Telegram credentials: Formato valido")
        else:
            logger.error("❌ Telegram credentials: Mancanti")
            return False

    except Exception as e:
        logger.error(f"❌ Errore configurazione: {e}")
        return False

    logger.info("✅ Monitor pronto per l'avvio")
    return True


# Logging
from logging.handlers import RotatingFileHandler

from telethon import TelegramClient

from config.settings import (
    DATA_DIR,
    LOGS_DIR,
    STOP_FILE,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
)
from src.analysis.squad_analyzer import analyze_squad_list
from src.database.models import Match, init_db
from src.processing.telegram_listener import fetch_squad_images

_log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_formatter)
# Use LOGS_DIR from settings for VPS compatibility
_log_file_path = os.path.join(LOGS_DIR, "telegram_monitor.log")
_file_handler = RotatingFileHandler(_log_file_path, maxBytes=5_000_000, backupCount=3)
_file_handler.setFormatter(_log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler], force=True)
logger = logging.getLogger(__name__)

# User session client (for channel scraping) - initialized in main()
client = None


async def monitor_loop():
    """
    Loop continuo di monitoraggio canali Telegram per formazioni.
    Implementa exponential backoff su errori ripetuti.
    """
    logger.info("🦅 EARLYBIRD TELEGRAM SQUAD MONITOR - STARTING")
    logger.info("📡 Monitoraggio canali Telegram per immagini formazioni...")

    # Exponential backoff state
    consecutive_errors = 0
    max_backoff_minutes = 30
    base_backoff_seconds = 120

    while True:
        # V14.0: Check for FULL STOP - exit completely if stopped
        if os.path.exists(STOP_FILE):
            logger.info("🛑 FULL STOP DETECTED - Telegram Monitor shutting down until /start")
            break

        try:
            logger.info("\n⏰ Ciclo Monitor Telegram...")

            # Fetch squad images from configured channels (pass existing client to avoid session lock)
            squad_images = await fetch_squad_images(existing_client=client)

            # Reset error counter on success
            consecutive_errors = 0

            if squad_images:
                logger.info(f"✅ Trovate {len(squad_images)} immagini formazioni da analizzare")

                for squad in squad_images:
                    alert = analyze_squad_list(
                        image_url=squad["image_path"],
                        team_name=squad["team_search_name"],
                        match_id=f"telegram_{squad['channel']}_{int(squad['timestamp'].timestamp())}",
                    )

                    if alert:
                        logger.info(f"🚨 ALERT CRITICO: {alert['summary']}")

                        from src.database.models import NewsLog, get_db_session

                        try:
                            with get_db_session() as db:
                                match = (
                                    db.query(Match)
                                    .filter(
                                        Match.home_team.contains(squad["team"])
                                        | Match.away_team.contains(squad["team"])
                                    )
                                    .first()
                                )

                                if match:
                                    # Save to NewsLog for triangulation
                                    news_log = NewsLog(
                                        match_id=match.id,
                                        url=alert.get("url", f"telegram://{squad['channel']}"),
                                        summary=alert["summary"],
                                        score=alert.get("score", 8),
                                        category="TELEGRAM_OCR_INTEL",
                                        affected_team=squad["team"],
                                        source="telegram_ocr",
                                        confidence=alert.get(
                                            "confidence", None
                                        ),  # V11.1: AI confidence from OCR alert
                                    )
                                    db.add(news_log)
                                    # commit is automatic in context manager
                                    logger.info(
                                        "💾 Intel salvata in DB per triangolazione (alert delegato a main.py)"
                                    )

                                    # NOTE: Alert is NOT sent here - main.py will process the NewsLog
                                    # and send alert after triangulation with other sources.
                                    # This prevents duplicate alerts and ensures proper analysis.
                                else:
                                    logger.warning(f"Nessun match trovato per {squad['team']}")
                        except Exception as db_err:
                            logger.error(f"❌ Errore DB: {db_err}")
                    else:
                        logger.info(f"✅ Tutti i titolari presenti per {squad['team']}")
            else:
                logger.info("Nessuna immagine formazione trovata nei messaggi recenti")

            # Sleep 10 minuti tra i cicli - con controlli STOP intermedi (V14.0 COVE FIX)
            logger.info("💤 Pausa 10 minuti con controlli STOP...")
            for _ in range(20):  # Check ogni 30 secondi
                if os.path.exists(STOP_FILE):
                    logger.info("🛑 STOP rilevato durante pausa - uscita immediata")
                    break
                await asyncio.sleep(30)

        except KeyboardInterrupt:
            logger.info("\n🛑 MONITOR SHUTDOWN")
            break
        except Exception as e:
            consecutive_errors += 1

            backoff_seconds = min(
                base_backoff_seconds * (2 ** (consecutive_errors - 1)), max_backoff_minutes * 60
            )
            backoff_minutes = backoff_seconds / 60

            logger.error(f"⚠️ Errore monitor (tentativo {consecutive_errors}): {e}")
            logger.info(f"Attesa {backoff_minutes:.1f} minuti prima del retry...")

            if consecutive_errors >= 5:
                logger.critical(f"🚨 {consecutive_errors} errori consecutivi nel monitor!")

            await asyncio.sleep(backoff_seconds)


async def main():
    """Entry point del monitor."""
    global client

    logger.info("=" * 50)
    logger.info("📡 EARLYBIRD TELEGRAM MONITOR STARTING...")
    if _UVLOOP_ENABLED:
        logger.info("⚡ uvloop enabled (Rust-powered event loop)")
    logger.info("=" * 50)

    # V2.0: Check if telegram_monitor feature is disabled by startup validator
    if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("telegram_monitor"):
        logger.warning(
            "⏭️ [TELEGRAM_MONITOR] Telegram monitoring disabled by startup validator "
            "(TELEGRAM_API_ID and/or TELEGRAM_API_HASH not configured)"
        )
        logger.info("💡 Telegram channel monitoring requires TELEGRAM_API_ID and TELEGRAM_API_HASH")
        logger.info("💡 The bot will continue without Telegram channel monitoring")
        return  # Exit gracefully

    # Ensure database tables exist
    init_db()
    logger.info("✅ Database initialized")

    # Initialize Telegram client inside async context (uvloop compatibility)
    # Use session file in data directory for VPS compatibility
    session_path = os.path.join(DATA_DIR, "earlybird_monitor")
    if TELEGRAM_API_ID and TELEGRAM_API_HASH:
        client = TelegramClient(session_path, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

    if client:
        try:
            # Try to start the client - this may fail if session file is missing/corrupted
            # and requires interactive authentication
            await client.start()
            logger.info("✅ Client Telegram connesso (User Session)")

            await monitor_loop()

        except EOFError:
            # Session file missing or corrupted - requires interactive authentication
            # which is not possible in background mode
            # CRITICAL FIX: Bot token fallback removed because bots cannot access channel history
            logger.error("❌ File di sessione Telegram mancante o corrotto")
            logger.error(
                "❌ Il monitoraggio dei canali Telegram richiede una sessione utente valida"
            )
            logger.error(
                "❌ I bot Telegram NON possono accedere alla cronologia dei canali (GetHistoryRequest)"
            )
            logger.info("")
            logger.info(
                "💡 SOLUZIONE: Eseguire 'python3 setup_telegram_auth.py' per creare una nuova sessione"
            )
            logger.info(
                "💡 Questo script richiede autenticazione interattiva (inserimento numero telefono e codice)"
            )
            logger.info("💡 Eseguire lo script manualmente in un terminale")
            logger.info("💡 Il monitor si avvierà AUTOMATICAMENTE quando la sessione viene creata")
            logger.info("")

            # Get session file path for watching
            session_file_path = f"{session_path}.session"
            last_session_mtime = 0

            # Enter idle mode: watch for session file changes
            while True:
                try:
                    # Check if session file exists and get modification time
                    if os.path.exists(session_file_path):
                        current_mtime = os.path.getmtime(session_file_path)

                        # If session file was modified, try to reconnect
                        if current_mtime > last_session_mtime:
                            logger.info(
                                "🔄 Rilevata modifica del file di sessione! Tentativo riconnessione..."
                            )
                            try:
                                await client.start()
                                logger.info("✅ Sessione valida trovata! Avvio monitor...")
                                await monitor_loop()
                                break
                            except EOFError:
                                logger.warning("⚠️ Sessione ancora non valida, continuo attesa...")
                                last_session_mtime = current_mtime
                                continue
                            except Exception as e:
                                logger.error(f"Errore riconnessione: {e}")
                                last_session_mtime = current_mtime
                                continue

                    # Wait 10 seconds before next check (more responsive than 5 minutes)
                    await asyncio.sleep(10)

                except Exception as e:
                    logger.error(f"Errore watch session file: {e}")
                    await asyncio.sleep(10)
                    continue
        finally:
            if client and client.is_connected():
                logger.info("🔌 Disconnessione client...")
                await client.disconnect()
                logger.info("✅ Client disconnesso")
    else:
        logger.warning("⚠️ Telegram non configurato - monitor disabilitato")


if __name__ == "__main__":
    # Parse arguments
    args = parse_args()

    # Handle test mode
    if args.test:
        success = test_monitor_configuration()
        sys.exit(0 if success else 1)

    # ✅ NEW: Pre-flight validation BEFORE starting monitor
    # Fail-fast: If validator cannot be imported, system should not start
    from src.utils.startup_validator import validate_startup_or_exit

    validation_report = validate_startup_or_exit()

    # Intelligent decision-making based on validation results
    if validation_report.disabled_features:
        logger.info(
            f"⚙️  Disabled features: {', '.join(sorted(validation_report.disabled_features))}"
        )
        logger.info("🔧 System will operate with reduced functionality")

    # Normal startup
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitor fermato dall'utente")
