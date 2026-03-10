#!/usr/bin/env python3
"""
EarlyBird News Radar Monitor - Standalone Launcher

Autonomous web monitoring component that runs independently from the main bot.
Monitors configured web sources 24/7 and sends direct Telegram alerts for
betting-relevant news on minor leagues.

Usage:
    python run_news_radar.py [--config CONFIG_FILE]

Arguments:
    --config    Path to configuration file (default: config/news_radar_sources.json)

Requirements: 10.1, 10.2, 10.3, 10.4
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

# Import settings for service control flags
import config.settings as settings
from src.services.news_radar import NewsRadarMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("news_radar.log", encoding="utf-8", delay=False),
    ],
    force=True,
)

logger = logging.getLogger(__name__)


def flush_all_handlers():
    """Flush all FileHandler instances to ensure logs are written to disk."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()


# Global monitor instance for signal handling
_monitor: NewsRadarMonitor = None
_shutdown_event: asyncio.Event | None = None


def signal_handler(signum, frame):
    """
    Handle SIGINT/SIGTERM for graceful shutdown.

    V7.2: Fixed signal handling - just set the event, don't try to schedule async tasks.
    The main loop will detect the event and call stop() properly.

    Requirements: 10.3
    """
    sig_name = signal.Signals(signum).name
    logger.info(f"🛑 [NEWS-RADAR] Received {sig_name}, initiating graceful shutdown...")

    # Just set the flag - the main loop will handle the actual shutdown
    if _shutdown_event:
        _shutdown_event.set()

    # Flush all handlers to ensure logs are written
    flush_all_handlers()


async def main(config_file: str, use_supabase: bool = True):
    """
    Main entry point for News Radar Monitor.

    V8.0: Added Supabase support for dynamic source fetching.

    Args:
        config_file: Path to config file (fallback if Supabase fails)
        use_supabase: Whether to fetch sources from Supabase (default: True)

    Requirements: 10.1, 10.2
    """
    global _monitor, _shutdown_event

    # V7.2: Create shutdown event for signal handling
    _shutdown_event = asyncio.Event()

    logger.info("=" * 60)
    logger.info("🔔 EarlyBird News Radar Monitor")
    logger.info("=" * 60)
    logger.info(f"Config file: {config_file}")
    logger.info(f"Supabase integration: {'ENABLED' if use_supabase else 'DISABLED'}")
    logger.info("")

    # Verify config file exists (only needed if Supabase is disabled)
    if not use_supabase and not Path(config_file).exists():
        logger.error(f"❌ Configuration file not found: {config_file}")
        logger.error("Please create the config file or specify a valid path with --config")
        return 1

    # Create monitor
    _monitor = NewsRadarMonitor(config_file=config_file, use_supabase=use_supabase)

    # Start monitor
    if not await _monitor.start():
        logger.error("❌ Failed to start News Radar Monitor")
        return 1

    logger.info("✅ News Radar Monitor started successfully")
    logger.info("Press Ctrl+C to stop")
    logger.info("")

    # Run until stopped or shutdown signal received
    try:
        while _monitor.is_running() and not _shutdown_event.is_set():
            # V7.2: Check both monitor state and shutdown event
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=1.0)
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Keep running
    except asyncio.CancelledError:
        pass

    # Ensure clean shutdown
    if _monitor.is_running():
        await _monitor.stop()

    # Print final stats
    stats = _monitor.get_stats()
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 Final Statistics")
    logger.info("=" * 60)
    logger.info(f"URLs scanned: {stats['urls_scanned']}")
    logger.info(f"Alerts sent: {stats['alerts_sent']}")
    logger.info(f"Cache size: {stats['cache_size']}")
    logger.info("")
    logger.info("✅ News Radar Monitor stopped gracefully")

    # Flush all handlers to ensure logs are written to disk
    flush_all_handlers()

    return 0


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EarlyBird News Radar Monitor - Autonomous web monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_news_radar.py
    python run_news_radar.py --config custom_sources.json
    python run_news_radar.py --no-supabase  # Use config file only
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/news_radar_sources.json",
        help="Path to configuration file (default: config/news_radar_sources.json)",
    )

    parser.add_argument(
        "--use-supabase",
        action="store_true",
        default=True,
        help="Fetch sources from Supabase database (default: True)",
    )

    parser.add_argument(
        "--no-supabase",
        action="store_false",
        dest="use_supabase",
        help="Disable Supabase and use config file only",
    )

    return parser.parse_args()


if __name__ == "__main__":
    # Parse arguments
    args = parse_args()

    # Check if News Radar service is enabled
    if not settings.NEWS_RADAR_ENABLED:
        logger.info("⚠️ Service News Radar Disabled by config.")
        sys.exit(0)

    # ✅ NEW: Pre-flight validation BEFORE starting news radar
    # Fail-fast: If validator cannot be imported, system should not start
    from src.utils.startup_validator import validate_startup_or_exit

    validation_report = validate_startup_or_exit()

    # Intelligent decision-making based on validation results
    if validation_report.disabled_features:
        logger.info(
            f"⚙️  Disabled features: {', '.join(sorted(validation_report.disabled_features))}"
        )
        logger.info("🔧 System will operate with reduced functionality")

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    try:
        exit_code = asyncio.run(main(args.config, args.use_supabase))
        flush_all_handlers()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
        flush_all_handlers()
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        flush_all_handlers()
        sys.exit(1)
