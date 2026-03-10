#!/usr/bin/env python3
"""
EarlyBird Telegram Bot - Command Handler

Gestisce i comandi admin via Telegram:
- /ping - Test connessione
- /stat - Dashboard statistiche
- /debug - Ultimi errori dal log
- /report - Export CSV storico

Separato dal Monitor (scraping canali) per architettura pulita.
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
    _UVLOOP_ENABLED = False  # Windows or uvloop not installed

# Setup path
sys.path.append(os.getcwd())

from dotenv import load_dotenv

load_dotenv()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EarlyBird Telegram Bot - Command Handler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Comandi disponibili via Telegram:
- /ping    : Test connessione bot
- /stat    : Dashboard statistiche sistema
- /debug   : Ultimi errori dai log
- /report  : Export CSV storico dati

Modalità:
- --help   : Mostra questo aiuto
- --test   : Verifica configurazione senza avviare
- default : Avvia bot in modalità ascolto

Examples:
    python src/entrypoints/run_bot.py
    python src/entrypoints/run_bot.py --test
        """,
    )

    parser.add_argument(
        "--test", action="store_true", help="Test configuration without starting bot"
    )

    return parser.parse_args()


def test_bot_configuration():
    """Verifica configurazione bot senza avviare."""
    logger.info("🤖 Verifica configurazione Telegram Bot...")

    # Check environment variables
    required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
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

    # Test import delle dipendenze critiche
    try:
        from config.settings import TELEGRAM_BOT_TOKEN
        from src.database.models import init_db

        logger.info("✅ Import configurazioni: OK")

        # Test database connection
        init_db()
        logger.info("✅ Database connection: OK")

        # Test Telegram client creation (senza connettere)
        if TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_BOT_TOKEN:
            logger.info("✅ Telegram credentials: Formato valido")
        else:
            logger.error("❌ Telegram credentials: Mancanti o invalidi")
            return False

    except Exception as e:
        logger.error(f"❌ Errore configurazione: {e}")
        return False

    logger.info("✅ Bot pronto per l'avvio")
    return True


# Import delle dipendenze principali (dopo argparse)
# Logging
from logging.handlers import RotatingFileHandler

# Telethon
from telethon import TelegramClient, events

from config.settings import (
    PAUSE_FILE,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from src.database.models import init_db
from src.utils.admin_tools import (
    format_debug_output,
    generate_report,
    generate_stats_dashboard,
    get_report_summary,
    get_stats_text_summary,
    read_last_error_lines,
)

_log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_formatter)
_file_handler = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=2)
_file_handler.setFormatter(_log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler], force=True)
logger = logging.getLogger(__name__)

# Admin ID
ADMIN_ID = TELEGRAM_CHAT_ID

# Bot Token
BOT_TOKEN = TELEGRAM_BOT_TOKEN

# Client initialized in main() to avoid uvloop event loop issues
client = None


def is_admin(sender_id: int) -> bool:
    """Verifica se il sender è admin."""
    try:
        return str(sender_id) == str(ADMIN_ID)
    except Exception as e:
        logger.warning(f"Errore verifica admin per sender_id={sender_id}: {e}")
        return False


async def setup_handlers():
    """Registra gli handler per i comandi."""
    if not client:
        return

    @client.on(events.NewMessage(pattern="/ping"))
    async def ping_handler(event):
        sender = await event.get_sender()
        if not is_admin(sender.id if sender else 0):
            return
        await event.reply("🏓 <b>Pong!</b> Bot attivo.", parse_mode="html")
        logger.info(f"✅ /ping da {sender.id if sender else 'unknown'}")

    @client.on(events.NewMessage(pattern="/help"))
    async def help_handler(event):
        sender = await event.get_sender()
        if not is_admin(sender.id if sender else 0):
            return

        help_text = """🦅 <b>EARLYBIRD COMMAND CENTER</b>

📊 <b>/stat</b> - Genera grafico Profitti &amp; ROI.
⚠️ <b>/debug</b> - Mostra gli ultimi errori dal log.
📂 <b>/report</b> - Scarica il CSV storico completo.
💰 <b>/settle</b> - Calcola risultati scommesse (72h).
🔄 <b>/status</b> - Stato Gemini API e cooldown.
🛑 <b>/stop</b> - Pausa il loop di analisi.
▶️ <b>/resume</b> - Riprendi il loop di analisi.
🏓 <b>/ping</b> - Test di risposta rapida.

<i>Il sistema gira in background h24.</i>"""
        await event.reply(help_text, parse_mode="html")

    @client.on(events.NewMessage(pattern="/start"))
    async def start_handler(event):
        sender = await event.get_sender()
        if not is_admin(sender.id if sender else 0):
            return

        welcome_text = """🦅 <b>EARLYBIRD BOT ONLINE</b>

📊 <b>/stat</b> - Dashboard statistiche
⚠️ <b>/debug</b> - Log errori recenti
📂 <b>/report</b> - Export CSV
💰 <b>/settle</b> - Calcola risultati
🏓 <b>/ping</b> - Test connessione

<i>Sistema attivo h24.</i>"""
        await event.reply(welcome_text, parse_mode="html")

    @client.on(events.NewMessage(pattern="/debug"))
    async def debug_handler(event):
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /debug non autorizzato da {sender_id}")
            return

        logger.info(f"🔍 /debug da {sender_id}")

        try:
            # Read log in thread (non-blocking)
            error_lines = await asyncio.to_thread(read_last_error_lines, "earlybird.log", 15)
            output = format_debug_output(error_lines)

            # Overflow protection
            if len(output) > 4000:
                temp_file = "temp/error_log.txt"
                os.makedirs("temp", exist_ok=True)
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(error_lines))

                await client.send_file(
                    event.chat_id, temp_file, caption="🔍 **Log errori (file allegato)**"
                )
            else:
                await event.reply(output, parse_mode="md")

            logger.info("✅ Debug log inviato")

        except Exception as e:
            logger.error(f"Errore /debug: {e}")
            await event.reply(f"❌ Errore: {e}")

    @client.on(events.NewMessage(pattern="/stat"))
    async def stat_handler(event):
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /stat non autorizzato da {sender_id}")
            return

        logger.info(f"📊 /stat da {sender_id}")
        msg = await event.reply("🎨 Generazione dashboard...")

        try:
            # Try image dashboard
            img_path = await asyncio.to_thread(generate_stats_dashboard)

            if img_path and os.path.exists(img_path):
                await client.send_file(
                    event.chat_id,
                    img_path,
                    caption="📊 <b>EarlyBird Performance Stats</b>",
                    parse_mode="html",
                )
                await msg.delete()
                logger.info("✅ Dashboard inviata")
            else:
                # Fallback to text
                text_summary = await asyncio.to_thread(get_stats_text_summary)
                await msg.edit(text_summary, parse_mode="html")
                logger.info("✅ Stats text inviato (fallback)")

        except Exception as e:
            logger.error(f"Errore /stat: {e}")
            await msg.edit(f"❌ Errore: {e}")

    @client.on(events.NewMessage(pattern="/report"))
    async def report_handler(event):
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /report non autorizzato da {sender_id}")
            return

        logger.info(f"📂 /report da {sender_id}")
        msg = await event.reply("📂 Generazione report CSV...")
        csv_path = None

        try:
            csv_path = await asyncio.to_thread(generate_report, 7)

            if not csv_path:
                await msg.edit("📊 Nessun alert negli ultimi 7 giorni.")
                return

            summary = await asyncio.to_thread(get_report_summary)

            caption = (
                f"📊 <b>EARLYBIRD REPORT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📤 Alert totali: {summary['total_alerts']}\n"
                f"🏆 Leghe coperte: {summary['leagues_covered']}\n"
                f"⭐ Top Score: {summary['top_score']}/10"
            )

            await client.send_file(event.chat_id, csv_path, caption=caption, parse_mode="html")
            await msg.delete()
            logger.info("✅ Report CSV inviato")

        except Exception as e:
            logger.error(f"Errore /report: {e}")
            await msg.edit(f"❌ Errore: {e}")
        finally:
            if csv_path and os.path.exists(csv_path):
                try:
                    os.remove(csv_path)
                except Exception as e:
                    logger.debug(f"Cleanup CSV fallito: {e}")

    @client.on(events.NewMessage(pattern="/settle"))
    async def settle_handler(event):
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /settle non autorizzato da {sender_id}")
            return

        logger.info(f"💰 /settle da {sender_id}")
        msg = await event.reply("⏳ Avvio conteggio risultati (ultime 72h)...")

        try:
            # Import settler (blocking FotMob calls)
            from src.analysis.settler import settle_pending_bets

            # Run blocking task in thread to avoid blocking the event loop
            stats = await asyncio.to_thread(settle_pending_bets, 72)

            # Build response message
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            pending = stats.get("pending", 0)
            roi = stats.get("roi_pct", 0.0)
            settled = stats.get("settled", 0)

            # V5.0: CLV section
            avg_clv = stats.get("avg_clv")
            clv_positive_rate = stats.get("clv_positive_rate")
            clv_section = ""
            if avg_clv is not None:
                clv_emoji = "📈" if avg_clv > 0 else "📉"
                clv_section = f"\n{clv_emoji} <b>CLV:</b> {avg_clv:+.2f}%"
                if clv_positive_rate is not None:
                    clv_section += f" ({clv_positive_rate:.0f}% positive)"

            response = (
                f"💰 <b>SETTLEMENT COMPLETATO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Vinte: {wins}\n"
                f"❌ Perse: {losses}\n"
                f"⏳ Pending: {pending}\n"
                f"📊 ROI: {roi:+.1f}%{clv_section}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 Processate: {settled} scommesse"
            )

            await msg.edit(response, parse_mode="html")
            logger.info(f"✅ Settlement completato: {wins}W/{losses}L, ROI {roi:.1f}%")

        except Exception as e:
            logger.error(f"Errore /settle: {e}")
            await msg.edit(f"❌ Errore settlement: {e}")

    @client.on(events.NewMessage(pattern="/stop"))
    async def stop_handler(event):
        """Pause the analysis loop by creating a lock file."""
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /stop non autorizzato da {sender_id}")
            return

        logger.info(f"🛑 /stop da {sender_id}")

        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(PAUSE_FILE), exist_ok=True)
            # Create lock file
            with open(PAUSE_FILE, "w") as f:
                f.write(f"Paused by {sender_id}")

            await event.reply(
                "🛑 <b>Bot Paused.</b>\nIl loop di analisi è in pausa.\nUsa /resume per riprendere.",
                parse_mode="html",
            )
            logger.info("✅ Sistema in pausa (pause.lock creato)")

        except Exception as e:
            logger.error(f"Errore /stop: {e}")
            await event.reply(f"❌ Errore: {e}")

    @client.on(events.NewMessage(pattern="/resume"))
    async def resume_handler(event):
        """Resume the analysis loop by removing the lock file."""
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /resume non autorizzato da {sender_id}")
            return

        logger.info(f"▶️ /resume da {sender_id}")

        try:
            if os.path.exists(PAUSE_FILE):
                os.remove(PAUSE_FILE)
                await event.reply(
                    "▶️ <b>Bot Resumed.</b>\nIl loop di analisi riprenderà al prossimo ciclo.",
                    parse_mode="html",
                )
                logger.info("✅ Sistema ripreso (pause.lock rimosso)")
            else:
                await event.reply("ℹ️ Il sistema non era in pausa.", parse_mode="html")

        except Exception as e:
            logger.error(f"Errore /resume: {e}")
            await event.reply(f"❌ Errore: {e}")

    @client.on(events.NewMessage(pattern="/status"))
    async def status_handler(event):
        """
        V5.0: Show Gemini API cooldown status.

        Requirements: 5.3
        """
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        if not is_admin(sender_id):
            logger.warning(f"⚠️ /status non autorizzato da {sender_id}")
            return

        logger.info(f"🔄 /status da {sender_id}")

        try:
            # Get Intelligence Router status
            status_parts = []

            try:
                from src.services.intelligence_router import get_intelligence_router

                router = get_intelligence_router()
                provider_name = router.get_active_provider_name()
                status_parts.append(f"🤖 <b>AI Provider:</b> {provider_name.capitalize()}")
            except Exception as e:
                logger.debug(f"Router status non disponibile: {e}")

            # V5.1: Get browser monitor stats
            browser_monitor_status = ""
            try:
                from src.services.browser_monitor import get_browser_monitor

                monitor = get_browser_monitor()
                stats = monitor.get_stats()

                if stats.get("running") or stats.get("news_discovered", 0) > 0:
                    status_icon = "🟢" if stats.get("running") else "🔴"
                    paused_text = " (⏸️ Pausa)" if stats.get("paused") else ""

                    # V5.1.1: Show AI provider (Gemini or DeepSeek fallback)
                    ai_provider = stats.get("ai_provider", "Gemini")
                    ai_icon = "🤖" if ai_provider == "DeepSeek" else "✨"

                    browser_monitor_status = (
                        f"\n\n🌐 <b>Browser Monitor:</b>\n"
                        f"⚙️ Stato: {status_icon} {'Attivo' if stats.get('running') else 'Fermo'}{paused_text}\n"
                        f"{ai_icon} AI: {ai_provider}\n"
                        f"🔍 URL scansionati: {stats.get('urls_scanned', 0)}\n"
                        f"📰 News scoperte: {stats.get('news_discovered', 0)}\n"
                        f"📦 Cache: {stats.get('cache_size', 0)} entries\n"
                        f"🔗 Fonti: {stats.get('sources_count', 0)}"
                    )

                    # Show DeepSeek fallback info if active
                    if stats.get("deepseek_fallback_active"):
                        remaining = stats.get("deepseek_remaining_hours")
                        if remaining:
                            browser_monitor_status += (
                                f"\n🔀 DeepSeek fallback: {remaining:.1f}h rimanenti"
                            )
                        browser_monitor_status += (
                            f"\n📊 DeepSeek calls: {stats.get('deepseek_calls', 0)}"
                        )
                    elif stats.get("consecutive_429s", 0) > 0:
                        browser_monitor_status += (
                            f"\n⚠️ Rate limit: {stats.get('consecutive_429s')}x 429"
                        )
            except Exception as e:
                logger.debug(f"Browser Monitor status non disponibile: {e}")

            response = (
                "🔄 <b>EARLYBIRD STATUS</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                + ("\n".join(status_parts) if status_parts else "")
                + f"{browser_monitor_status}"
            )

            await event.reply(response, parse_mode="html")
            logger.info("✅ Status inviato")

        except Exception as e:
            logger.error(f"Errore /status: {e}")
            await event.reply(f"❌ Errore: {e}")

    logger.info("✅ Command handlers registrati")


async def main():
    """Entry point del bot."""
    global client

    logger.info("=" * 50)
    logger.info("🤖 EARLYBIRD TELEGRAM BOT STARTING...")
    if _UVLOOP_ENABLED:
        logger.info("⚡ uvloop enabled (Rust-powered event loop)")
    logger.info("=" * 50)

    # Ensure database tables exist
    init_db()
    logger.info("✅ Database initialized")

    # Initialize client inside async context (uvloop compatibility)
    if BOT_TOKEN and TELEGRAM_API_ID and TELEGRAM_API_HASH:
        client = TelegramClient("earlybird_cmd_bot", int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    else:
        logger.error("❌ TELEGRAM_BOT_TOKEN o API credentials non configurati in .env")
        logger.error("⚠️ Telegram Bot functionality DISABLED. Configure .env to enable.")
        logger.info("ℹ️ Bot will remain in idle state (no crash-restart loop).")
        # Sleep indefinitely to keep process alive but idle
        # This prevents launcher from restarting the bot in a loop
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep 1 hour, then loop
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("🛑 Bot fermato")
        return

    try:
        # Start with bot token
        await client.start(bot_token=BOT_TOKEN)

        await setup_handlers()
        logger.info("✅ Bot connesso e in ascolto...")

        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"❌ Errore bot: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()
            logger.info("🔌 Bot disconnesso")


if __name__ == "__main__":
    # Parse arguments
    args = parse_args()

    # Handle test mode
    if args.test:
        success = test_bot_configuration()
        sys.exit(0 if success else 1)

    # ✅ NEW: Pre-flight validation BEFORE starting bot
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
        logger.info("🛑 Bot fermato dall'utente")
