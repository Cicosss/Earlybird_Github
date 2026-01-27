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

from src.services.news_radar import NewsRadarMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('news_radar.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# Global monitor instance for signal handling
_monitor: NewsRadarMonitor = None
_shutdown_event: asyncio.Event = None


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


async def main(config_file: str):
    """
    Main entry point for News Radar Monitor.
    
    Requirements: 10.1, 10.2
    """
    global _monitor, _shutdown_event
    
    # V7.2: Create shutdown event for signal handling
    _shutdown_event = asyncio.Event()
    
    logger.info("=" * 60)
    logger.info("🔔 EarlyBird News Radar Monitor")
    logger.info("=" * 60)
    logger.info(f"Config file: {config_file}")
    logger.info("")
    
    # Verify config file exists
    if not Path(config_file).exists():
        logger.error(f"❌ Configuration file not found: {config_file}")
        logger.error("Please create the config file or specify a valid path with --config")
        return 1
    
    # Create monitor
    _monitor = NewsRadarMonitor(config_file=config_file)
    
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
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/news_radar_sources.json',
        help='Path to configuration file (default: config/news_radar_sources.json)'
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse arguments
    args = parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run
    try:
        exit_code = asyncio.run(main(args.config))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)
