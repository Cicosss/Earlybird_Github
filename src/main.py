"""
EarlyBird Main Application
=========================
Main entry point for the EarlyBird football betting intelligence system.

REFACTORING NOTES:
- This file has been refactored to use ContinentalOrchestrator for "Follow the Sun" scheduling
- The original main.py is backed up as src/main.py.backup
- All league selection and continental filtering logic is now delegated to ContinentalOrchestrator
- All existing functionality is preserved - this is a thin wrapper pattern

Historical Version: V1.0

Author: Refactored by Lead Architect
Date: 2026-02-08
Updated: 2026-02-23 (Centralized Version Tracking)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("earlybird_main.log")],
)
logger = logging.getLogger(__name__)

# CRITICAL: Load .env BEFORE any other imports that read env vars
from dotenv import load_dotenv

# Setup path to import modules (CRITICAL: must be before config import)
sys.path.append(os.getcwd())

# Calculate .env path relative to this file to ensure it works from any directory
env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(env_file)

# Import centralized version tracking
from src.version import get_version_with_module

# Log version on import
logger.info(f"📦 {get_version_with_module('Main Pipeline')}")

# Import settings for service control flags
# ============================================
# CLEANUP HOOKS FOR TERMINATION SIGNALS
# ============================================
import atexit
import signal

import config.settings as settings


def cleanup_on_exit():
    """Cleanup function called on program exit."""
    try:
        from src.ingestion.ingest_fixtures import _close_session

        _close_session()
        logging.info("✅ Cleanup completed: requests session closed")
    except ImportError:
        pass
    except Exception as e:
        logging.warning(f"⚠️ Cleanup failed: {e}")


# Register cleanup hooks
atexit.register(cleanup_on_exit)


# Register signal handlers for SIGTERM and SIGINT
def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    logging.info(f"🛑 Received signal {signum}, cleaning up...")
    cleanup_on_exit()
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ============================================
# CORE IMPORTS
# ============================================
from src.analysis.optimizer import get_optimizer

# ============================================
# ANALYSIS ENGINE (V1.0 - Modular Refactor)
# ============================================
from src.core.analysis_engine import get_analysis_engine

# ============================================
# SETTLEMENT SERVICE (V1.0 - Modular Refactor)
# ============================================
from src.core.settlement_service import get_settlement_service
from src.database.maintenance import cleanup_stale_radar_triggers, emergency_cleanup
from src.database.migration import check_and_migrate
from src.database.models import Match, NewsLog, SessionLocal, init_db
from src.ingestion.data_provider import get_data_provider
from src.ingestion.ingest_fixtures import ingest_fixtures
from src.ingestion.league_manager import (
    ELITE_LEAGUES,
    get_active_niche_leagues,
    get_tier2_fallback_batch,
    increment_cycle,
    record_tier2_activation,
    should_activate_tier2_fallback,
)

# ============================================
# GLOBAL ORCHESTRATOR (V11.0 - Global Parallel Architecture)
# ============================================
from src.processing.global_orchestrator import (
    get_global_orchestrator,
)

# ============================================
# DISCOVERY QUEUE (V11.0 - Global Parallel Architecture)
# ============================================
from src.utils.discovery_queue import DiscoveryQueue

# ============================================
# V9.2: DATABASE-DRIVEN INTELLIGENCE ENGINE
# ============================================
try:
    from src.database.supabase_provider import get_supabase

    _SUPABASE_PROVIDER_AVAILABLE = True
    logger.info("✅ Supabase Provider module loaded")
except ImportError as e:
    _SUPABASE_PROVIDER_AVAILABLE = False
    get_supabase = None
    logger.warning(f"⚠️ Supabase Provider not available: {e}")


# ============================================
# V9.5: LOCAL MIRROR FALLBACK FUNCTIONS
# ============================================
def load_local_mirror(mirror_path: str = "data/supabase_mirror.json") -> dict:
    """
    Load the local mirror file.

    Args:
        mirror_path: Path to the mirror file

    Returns:
        dict: Mirror data or empty dict if file doesn't exist
    """
    try:
        if not os.path.exists(mirror_path):
            logger.warning(f"⚠️ Mirror file not found: {mirror_path}")
            return {}

        with open(mirror_path, encoding="utf-8") as f:
            mirror_data = json.load(f)

        timestamp = mirror_data.get("timestamp", "")
        version = mirror_data.get("version", "UNKNOWN")
        data = mirror_data.get("data", {})

        # FIX: Validate mirror timestamp to prevent using stale data
        if timestamp:
            try:
                from datetime import datetime, timezone

                mirror_time = datetime.fromisoformat(timestamp)
                now = datetime.now(timezone.utc)
                age_hours = (now - mirror_time).total_seconds() / 3600

                if age_hours > 24:
                    logger.warning(
                        f"⚠️ Mirror is {age_hours:.1f} hours old (threshold: 24h). "
                        f"Data may be stale. Consider updating from Supabase."
                    )
                else:
                    logger.info(f"✅ Mirror is {age_hours:.1f} hours old (fresh)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse mirror timestamp '{timestamp}': {e}")

        logger.info(f"✅ Loaded local mirror from: {mirror_path} (v{version}, {timestamp})")
        return data

    except Exception as e:
        logger.error(f"❌ Failed to load local mirror: {e}")
        return {}


def get_social_sources_with_fallback() -> list[dict]:
    """
    Get social sources with fallback to local mirror.

    Tries to load from Supabase API first, then falls back to local mirror
    if the API fails. This ensures the bot continues to operate even when
    Supabase is unavailable.

    Returns:
        List of social source records
    """
    if not _SUPABASE_PROVIDER_AVAILABLE:
        logger.warning("⚠️ Supabase Provider not available, using local mirror fallback")
        mirror = load_local_mirror()
        social_sources = mirror.get("social_sources", [])
        if social_sources:
            logger.info(f"📦 Using {len(social_sources)} social sources from local mirror")
        else:
            logger.error("❌ No social sources available from mirror")
        return social_sources

    try:
        # Try Supabase API first
        supabase = get_supabase()
        sources = supabase.get_social_sources()
        if sources:
            logger.info(f"✅ Loaded {len(sources)} social sources from Supabase API")
            return sources
    except Exception as e:
        logger.warning(f"⚠️ Supabase API failed: {e}")

    # Fallback to local mirror
    mirror = load_local_mirror()
    social_sources = mirror.get("social_sources", [])

    if social_sources:
        logger.info(f"📦 Using {len(social_sources)} social sources from local mirror")
    else:
        logger.error("❌ No social sources available from mirror")

    return social_sources


def get_news_sources_with_fallback() -> list[dict]:
    """
    Get news sources with fallback to local mirror.

    Tries to load from Supabase API first, then falls back to local mirror
    if the API fails. This ensures the bot continues to operate even when
    Supabase is unavailable.

    Returns:
        List of news source records
    """
    if not _SUPABASE_PROVIDER_AVAILABLE:
        logger.warning("⚠️ Supabase Provider not available, using local mirror fallback")
        mirror = load_local_mirror()
        news_sources = mirror.get("news_sources", [])
        if news_sources:
            logger.info(f"📦 Using {len(news_sources)} news sources from local mirror")
        else:
            logger.error("❌ No news sources available from mirror")
        return news_sources

    try:
        # Try Supabase API first
        supabase = get_supabase()
        sources = supabase.fetch_all_news_sources()
        if sources:
            logger.info(f"✅ Loaded {len(sources)} news sources from Supabase API")
            return sources
    except Exception as e:
        logger.warning(f"⚠️ Supabase API failed: {e}")

    # Fallback to local mirror
    mirror = load_local_mirror()
    news_sources = mirror.get("news_sources", [])

    if news_sources:
        logger.info(f"📦 Using {len(news_sources)} news sources from local mirror")
    else:
        logger.error("❌ No news sources available from mirror")

    return news_sources


# ============================================
# INTELLIGENCE ROUTER (V5.0)
# ============================================
try:
    from src.services.intelligence_router import get_intelligence_router, is_intelligence_available

    _INTELLIGENCE_ROUTER_AVAILABLE = True
    logger.info("✅ Intelligence Router module loaded")
except ImportError as e:
    _INTELLIGENCE_ROUTER_AVAILABLE = False
    get_intelligence_router = None
    is_intelligence_available = lambda: False
    logger.warning(f"⚠️ Intelligence Router not available: {e}")

# ============================================
# INTELLIGENT DEDUPLICATION (V4.4)
# ============================================
try:
    from src.utils.url_normalizer import are_articles_similar, normalize_url

    _SMART_DEDUP_AVAILABLE = True
    logger.info("✅ Intelligent Deduplication module loaded")
except ImportError as e:
    _SMART_DEDUP_AVAILABLE = False
    logger.warning(f"⚠️ Intelligent Deduplication not available: {e}")

# ============================================
# MARKET INTELLIGENCE (Steam Move, Reverse Line, News Decay)
# ============================================
try:
    from src.analysis.market_intelligence import (
        analyze_market_intelligence,
        cleanup_old_snapshots,
        init_market_intelligence_db,
    )

    _MARKET_INTEL_AVAILABLE = True
    logger.info("✅ Market Intelligence module loaded")
except ImportError as e:
    _MARKET_INTEL_AVAILABLE = False
    logger.warning(f"⚠️ Market Intelligence not available: {e}")

# ============================================
# FATIGUE ENGINE V2.0 (Advanced Fatigue Analysis)
# ============================================
try:
    from src.analysis.fatigue_engine import FatigueDifferential, get_enhanced_fatigue_context

    _FATIGUE_ENGINE_AVAILABLE = True
    logger.info("✅ Fatigue Engine V2.0 loaded")
except ImportError as e:
    _FATIGUE_ENGINE_AVAILABLE = False
    logger.warning(f"⚠️ Fatigue Engine V2.0 not available: {e}")

# ============================================
# INJURY IMPACT ENGINE V8.0 (Tactical Brain Integration)
# ============================================
try:
    from src.analysis.injury_impact_engine import (
        InjuryDifferential,
        TeamInjuryImpact,
        analyze_match_injuries,
    )

    _INJURY_IMPACT_AVAILABLE = True
    logger.info("✅ Injury Impact Engine V8.0 loaded")
except ImportError as e:
    _INJURY_IMPACT_AVAILABLE = False
    analyze_match_injuries = None
    logger.warning(f"⚠️ Injury Impact Engine not available: {e}")

# ============================================
# BISCOTTO ENGINE V2.0 (Enhanced Detection)
# ============================================
try:
    from src.analysis.biscotto_engine import BiscottoSeverity, get_enhanced_biscotto_analysis

    _BISCOTTO_ENGINE_AVAILABLE = True
    logger.info("✅ Biscotto Engine V2.0 loaded")
except ImportError as e:
    _BISCOTTO_ENGINE_AVAILABLE = False
    logger.warning(f"⚠️ Biscotto Engine V2.0 not available: {e}")

# ============================================
# TWITTER INTEL CACHE V4.5 (Search Grounding)
# ============================================
try:
    from src.ingestion.deepseek_intel_provider import get_deepseek_provider
    from src.services.twitter_intel_cache import get_twitter_intel_cache

    _TWITTER_INTEL_AVAILABLE = True
    _DEEPSEEK_PROVIDER_AVAILABLE = True
    logger.info("✅ Twitter Intel Cache loaded")
except ImportError:
    _TWITTER_INTEL_AVAILABLE = False
    _DEEPSEEK_PROVIDER_AVAILABLE = False
    logging.debug("Twitter Intel Cache not available")

# ============================================
# V10.5: NITTER INTEL CACHE (Import from nitter_fallback_scraper)
# ============================================
try:
    from src.services.nitter_fallback_scraper import get_nitter_intel_for_match

    _NITTER_INTEL_AVAILABLE = True
    logger.info("✅ Nitter Intel Cache module loaded")
except ImportError as e:
    _NITTER_INTEL_AVAILABLE = False
    logger.warning(f"⚠️ Nitter Intel Cache not available: {e}")

# ============================================
# TWEET RELEVANCE FILTER V4.6 (AI Integration)
# ============================================
try:
    from src.services.tweet_relevance_filter import (
        filter_tweets_for_match,
        resolve_conflict_via_gemini,
    )

    _TWEET_FILTER_AVAILABLE = True
except ImportError:
    _TWEET_FILTER_AVAILABLE = False
    logging.debug("Tweet Relevance Filter not available")

# ============================================
# BROWSER MONITOR V5.1 (Always-On Web Monitoring)
# ============================================
try:
    from src.processing.news_hunter import register_browser_monitor_discovery
    from src.services.browser_monitor import BrowserMonitor, get_browser_monitor

    _BROWSER_MONITOR_AVAILABLE = True
except ImportError:
    _BROWSER_MONITOR_AVAILABLE = False
    logging.debug("Browser Monitor not available")

# ============================================
# DISCOVERY QUEUE V6.0 (High-Priority Callback)
# ============================================
try:
    from src.utils.discovery_queue import get_discovery_queue

    _DISCOVERY_QUEUE_AVAILABLE = True
except ImportError:
    _DISCOVERY_QUEUE_AVAILABLE = False
    logging.debug("Discovery Queue not available")

# ============================================
# PARALLEL ENRICHMENT V6.0 (Performance Optimization)
# ============================================
try:
    from src.utils.parallel_enrichment import EnrichmentResult, enrich_match_parallel

    _PARALLEL_ENRICHMENT_AVAILABLE = True
except ImportError:
    _PARALLEL_ENRICHMENT_AVAILABLE = False
    logging.debug("Parallel Enrichment not available")

# ============================================
# VERIFICATION LAYER V7.0 (Alert Fact-Checking)
# ============================================
try:
    from src.analysis.verification_layer import (
        VERIFICATION_SCORE_THRESHOLD,
        VerificationRequest,
        VerificationResult,
        VerificationStatus,
        create_verification_request_from_match,
        should_verify_alert,
        verify_alert,
    )

    _VERIFICATION_LAYER_AVAILABLE = True
except ImportError:
    _VERIFICATION_LAYER_AVAILABLE = False
    logging.debug("Verification Layer not available")


# ============================================
# FINAL ALERT VERIFIER V1.0 (Pre-Telegram Validation)
# ============================================
try:
    from src.analysis.final_alert_verifier import get_final_verifier, is_final_verifier_available
    from src.analysis.verifier_integration import (
        build_alert_data_for_verifier,
        build_biscotto_alert_data_for_verifier,
        build_context_data_for_verifier,
        verify_alert_before_telegram,
        verify_biscotto_alert_before_telegram,
    )

    _FINAL_VERIFIER_AVAILABLE = True
except ImportError:
    _FINAL_VERIFIER_AVAILABLE = False
    logging.debug("Final Alert Verifier not available")

# ============================================
# INTELLIGENT MODIFICATION LOGGER V1.0 (Hybrid Approach)
# ============================================
try:
    from src.analysis.intelligent_modification_logger import get_intelligent_modification_logger
    from src.analysis.step_by_step_feedback import get_step_by_step_feedback_loop

    _INTELLIGENT_LOGGER_AVAILABLE = True
except ImportError:
    _INTELLIGENT_LOGGER_AVAILABLE = False
    logging.debug("Intelligent Modification Logger not available")


# Reporter moved to manual /report command in run_telegram_monitor.py
from config.settings import (
    ALERT_THRESHOLD_HIGH,
    ALERT_THRESHOLD_RADAR,
    ANALYSIS_WINDOW_HOURS,
    BISCOTTO_EXTREME_LOW,
    BISCOTTO_SIGNIFICANT_DROP,
    BISCOTTO_SUSPICIOUS_LOW,
    PAUSE_FILE,
)
from src.alerting.health_monitor import get_health_monitor
from src.alerting.notifier import send_biscotto_alert, send_status_message

# ============================================
# INTELLIGENCE-ONLY LEAGUES (No Odds Available)
# ============================================
# These leagues are analyzed purely on News + Stats (FotMob)
# No odds tracking - alerts marked with "NEWS SIGNAL ONLY"

INTELLIGENCE_ONLY_LEAGUES = {
    "soccer_africa_cup_of_nations",  # AFCON - Radar only
    # Add more as needed
}

# ============================================
# INVESTIGATOR MODE: CASE CLOSED COOLDOWN
# ============================================
# Once a verdict is reached, "Close the Case" for 6 hours to save API credits
# Exception: If match starts in < 2 hours, ignore cooldown (Final Check allowed)

CASE_CLOSED_COOLDOWN_HOURS = 6  # Hours to wait before re-investigating
FINAL_CHECK_WINDOW_HOURS = 2  # Hours before kickoff when cooldown is ignored


def is_intelligence_only_league(league_key: str) -> bool:
    """Check if a league is Intelligence-Only (no odds available)."""
    if not league_key:
        return False
    # Check exact match or partial match for Africa-related leagues
    if league_key in INTELLIGENCE_ONLY_LEAGUES:
        return True
    if "africa" in league_key.lower() or "egypt" in league_key.lower():
        return True
    return False


def is_case_closed(match, now: datetime) -> tuple:
    """
    CASE CLOSED COOLDOWN: Check if match investigation is on cooldown.

    Rules:
    - If last_deep_dive_time > (now - 6 hours) AND time_to_kickoff > 2 hours:
      -> SKIP ANALYSIS (Case Closed - Cooldown Active)
    - Exception: If match starts in < 2 hours, ignore cooldown (Final Check allowed)

    Args:
        match: Match object with last_deep_dive_time
        now: Current UTC time

    Returns:
        Tuple of (is_closed, reason)
    """
    # No previous investigation - case is open
    if not match.last_deep_dive_time:
        return False, "First investigation"

    # Calculate time since last investigation
    hours_since_dive = (now - match.last_deep_dive_time).total_seconds() / 3600

    # Calculate time to kickoff
    hours_to_kickoff = (match.start_time - now).total_seconds() / 3600

    # EXCEPTION: Final Check window - always allow investigation
    if hours_to_kickoff <= FINAL_CHECK_WINDOW_HOURS:
        return False, f"Final Check ({hours_to_kickoff:.1f}h to kickoff)"

    # Check cooldown
    if hours_since_dive < CASE_CLOSED_COOLDOWN_HOURS:
        return (
            True,
            f"Case Closed - Cooldown ({hours_since_dive:.1f}h since last dive, {hours_to_kickoff:.1f}h to kickoff)",
        )

    return False, f"Cooldown expired ({hours_since_dive:.1f}h since last dive)"


# Configure logging - force reconfiguration
from logging.handlers import RotatingFileHandler

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add our handlers
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Console handler with immediate flush
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
console_handler.stream.reconfigure(line_buffering=True) if hasattr(
    console_handler.stream, "reconfigure"
) else None

# File handler with rotation (5MB max, 3 backups = 15MB total max)
file_handler = RotatingFileHandler("earlybird.log", maxBytes=5_000_000, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)


def is_biscotto_suspect(match) -> dict:
    """
    🍪 BISCOTTO DETECTION: Check if Draw odds indicate a "mutually beneficial draw".

    V6.1: Added edge case protection for invalid odds values.

    Returns:
        dict with 'is_suspect', 'reason', 'draw_odd', 'drop_pct'
    """
    result = {
        "is_suspect": False,
        "reason": None,
        "draw_odd": None,
        "drop_pct": 0,
        "severity": "NONE",
    }

    draw_odd = match.current_draw_odd
    opening_draw = match.opening_draw_odd

    # V6.1: Validate draw_odd is a positive number
    if not draw_odd or not isinstance(draw_odd, (int, float)) or draw_odd <= 0:
        return result

    result["draw_odd"] = draw_odd

    # Calculate drop percentage with full validation
    # V6.1: Ensure both values are valid before division
    # V8.3: Initialize drop_pct to avoid UnboundLocalError
    drop_pct = 0
    if (
        opening_draw
        and isinstance(opening_draw, (int, float))
        and opening_draw > 0
        and isinstance(draw_odd, (int, float))
        and draw_odd > 0
    ):
        drop_pct = ((opening_draw - draw_odd) / opening_draw) * 100
        result["drop_pct"] = drop_pct

    # Check thresholds
    if draw_odd < BISCOTTO_EXTREME_LOW:
        result["is_suspect"] = True
        result["severity"] = "EXTREME"
        result["reason"] = f"🍪 EXTREME: Draw @ {draw_odd:.2f} (below {BISCOTTO_EXTREME_LOW})"
    elif draw_odd < BISCOTTO_SUSPICIOUS_LOW:
        result["is_suspect"] = True
        result["severity"] = "HIGH"
        result["reason"] = f"🍪 SUSPICIOUS: Draw @ {draw_odd:.2f} (below {BISCOTTO_SUSPICIOUS_LOW})"
    elif drop_pct > BISCOTTO_SIGNIFICANT_DROP and opening_draw:
        # V6.1: Extra check that opening_draw exists before using in message
        result["is_suspect"] = True
        result["severity"] = "MEDIUM"
        result["reason"] = (
            f"🍪 DROPPING: Draw dropped {drop_pct:.1f}% ({opening_draw:.2f} → {draw_odd:.2f})"
        )

    return result


# ============================================
# ODDS DROP DETECTION (V2.0)
# ============================================
def check_odds_drops():
    """
    Check for significant odds movements in the database.

    This function scans all matches in the database and identifies
    significant odds drops that may indicate market movement or
    insider information.
    """
    db = SessionLocal()
    try:
        # Get all matches with odds data
        matches = (
            db.query(Match)
            .filter(
                Match.start_time > datetime.now(timezone.utc),
                Match.current_home_odd.isnot(None),
                Match.opening_home_odd.isnot(None),
            )
            .all()
        )

        significant_drops = []

        for match in matches:
            # Calculate home odd drop
            if match.opening_home_odd and match.current_home_odd:
                home_drop_pct = (
                    (match.opening_home_odd - match.current_home_odd) / match.opening_home_odd
                ) * 100
                if home_drop_pct > 15:  # 15%+ drop is significant
                    significant_drops.append(
                        {
                            "match": match,
                            "type": "HOME_DROP",
                            "drop_pct": home_drop_pct,
                            "opening": match.opening_home_odd,
                            "current": match.current_home_odd,
                        }
                    )

            # Calculate away odd drop
            if match.opening_away_odd and match.current_away_odd:
                away_drop_pct = (
                    (match.opening_away_odd - match.current_away_odd) / match.opening_away_odd
                ) * 100
                if away_drop_pct > 15:  # 15%+ drop is significant
                    significant_drops.append(
                        {
                            "match": match,
                            "type": "AWAY_DROP",
                            "drop_pct": away_drop_pct,
                            "opening": match.opening_away_odd,
                            "current": match.current_away_odd,
                        }
                    )

        if significant_drops:
            logging.info(f"💹 Found {len(significant_drops)} significant odds drops")
            for drop in significant_drops:
                match = drop["match"]
                logging.info(
                    f"   📉 {match.home_team} vs {match.away_team}: {drop['type']} {drop['drop_pct']:.1f}% ({drop['opening']:.2f} → {drop['current']:.2f})"
                )

        return significant_drops

    finally:
        db.close()


# ============================================
# BISCOTTO SCANNER (V2.0)
# ============================================
def check_biscotto_suspects():
    """
    Scan for Biscotto suspects (suspicious Draw odds).

    This function identifies matches with unusually low Draw odds
    that may indicate a "mutually beneficial draw" scenario.
    """
    db = SessionLocal()
    try:
        # Get all matches with draw odds data
        matches = (
            db.query(Match)
            .filter(
                Match.start_time > datetime.now(timezone.utc), Match.current_draw_odd.isnot(None)
            )
            .all()
        )

        suspects = []

        for match in matches:
            result = is_biscotto_suspect(match)
            if result["is_suspect"]:
                suspects.append(
                    {
                        "match": match,
                        "severity": result["severity"],
                        "reason": result["reason"],
                        "draw_odd": result["draw_odd"],
                        "drop_pct": result["drop_pct"],
                    }
                )

        if suspects:
            logging.info(f"🍪 Found {len(suspects)} Biscotto suspects")
            for suspect in suspects:
                match = suspect["match"]
                logging.info(f"   🍪 {match.home_team} vs {match.away_team}: {suspect['reason']}")

                # Send alert for EXTREME suspects
                if suspect["severity"] == "EXTREME":
                    try:
                        # Verify alert before sending (Final Verifier)
                        if _FINAL_VERIFIER_AVAILABLE:
                            should_send, final_verification_info = (
                                verify_biscotto_alert_before_telegram(
                                    match=match,
                                    draw_odd=suspect["draw_odd"],
                                    drop_pct=suspect["drop_pct"],
                                    severity=suspect["severity"],
                                    reasoning=suspect["reason"],
                                    news_url=None,  # Biscotto alerts don't have news_url
                                )
                            )

                            if should_send:
                                send_biscotto_alert(
                                    match=match,
                                    reason=suspect["reason"],
                                    draw_odd=suspect["draw_odd"],
                                    drop_pct=suspect["drop_pct"],
                                    final_verification_info=final_verification_info,
                                )
                            else:
                                logging.warning(
                                    f"🍪 Biscotto alert blocked by Final Verifier: "
                                    f"{final_verification_info.get('reason', 'Unknown')}"
                                )
                        else:
                            # Final Verifier not available, send without verification
                            send_biscotto_alert(
                                match=match,
                                reason=suspect["reason"],
                                draw_odd=suspect["draw_odd"],
                                drop_pct=suspect["drop_pct"],
                            )
                    except Exception as e:
                        logging.error(f"Failed to send Biscotto alert: {e}")

        return suspects

    finally:
        db.close()


# ============================================
# RADAR TRIGGER INBOX (Cross-Process Handoff)
# ============================================
def process_radar_triggers(analysis_engine, fotmob, now_utc, db):
    """
    Process pending radar triggers from NewsLog inbox.

    CROSS-PROCESS HANDOFF: News Radar drops high-confidence news in DB,
    Main Pipeline picks it up and runs full AI analysis.

    Args:
        analysis_engine: AnalysisEngine instance
        fotmob: FotMob provider
        now_utc: Current UTC time
        db: Database session

    Returns:
        Number of triggers processed
    """
    triggers_processed = 0

    try:
        # Query for pending radar triggers
        pending_triggers = db.query(NewsLog).filter(NewsLog.status == "PENDING_RADAR_TRIGGER").all()

        if not pending_triggers:
            logging.debug("📭 No pending radar triggers in inbox")
            return 0

        logging.info(f"📬 RADAR INBOX: Found {len(pending_triggers)} pending trigger(s)")

        # Process each trigger
        for trigger in pending_triggers:
            try:
                # Get match from trigger
                match = db.query(Match).filter(Match.id == trigger.match_id).first()

                if not match:
                    logging.warning(
                        f"⚠️ RADAR INBOX: Match {trigger.match_id} not found, skipping trigger"
                    )
                    # Update trigger status to indicate failure
                    trigger.status = "FAILED"
                    trigger.summary = f"{trigger.summary} [Match not found]"
                    db.commit()
                    continue

                # Extract forced narrative from verification_reason field
                forced_narrative = trigger.verification_reason or ""

                logging.info(
                    f"🔥 RADAR TRIGGER: Processing {match.home_team} vs {match.away_team} "
                    f"with forced narrative from News Radar"
                )

                # Call analysis with forced narrative (bypasses news hunting)
                analysis_result = analysis_engine.analyze_match(
                    match=match,
                    fotmob=fotmob,
                    now_utc=now_utc,
                    db_session=db,
                    context_label="RADAR_TRIGGER",
                    forced_narrative=forced_narrative,
                )

                # Update trigger status to processed
                trigger.status = "PROCESSED"
                trigger.summary = f"{trigger.summary} [Processed by Main Pipeline]"
                db.commit()

                triggers_processed += 1

                logging.info(
                    f"✅ RADAR TRIGGER: Completed analysis for "
                    f"{match.home_team} vs {match.away_team} "
                    f"(score: {analysis_result.get('score', 0):.1f})"
                )

            except Exception as e:
                logging.error(
                    f"❌ RADAR INBOX: Failed to process trigger for {trigger.match_id}: {e}"
                )
                # Update trigger status to indicate failure
                try:
                    trigger.status = "FAILED"
                    trigger.summary = f"{trigger.summary} [Error: {str(e)[:100]}]"
                    db.commit()
                except Exception as commit_error:
                    logging.error(f"❌ Failed to update trigger status: {commit_error}")
                    db.rollback()

        return triggers_processed

    except Exception as e:
        logging.error(f"❌ RADAR INBOX: Error checking for triggers: {e}")
        return 0


# ============================================
# MAIN PIPELINE (Refactored to use ContinentalOrchestrator)
# ============================================
def run_pipeline():
    """
    REFACTORED V1.0: Triangulation Pipeline with ContinentalOrchestrator

    KEY CHANGES:
    - Uses ContinentalOrchestrator for "Follow the Sun" scheduling
    - Delegates all league selection and continental filtering to the orchestrator
    - Preserves all existing functionality (Tactical Veto, Balanced Probability, etc.)

    QUOTA PROTECTION:
    - Auto-discovers active niche leagues
    - Limits to 5 leagues per run

    AUTO-MIGRATION:
    - Checks and updates DB schema at startup
    """
    logging.info(
        "🚀 STARTING EARLYBIRD V6.1 PIPELINE (ContinentalOrchestrator + DeepSeek Intel + FotMob + Triangulation)"
    )

    # V6.0: Log active intelligence provider
    try:
        router = get_intelligence_router()
        if router.is_available():
            logging.info("🤖 DeepSeek Intel Provider: ATTIVO (Primary)")
        else:
            logging.warning("⚠️ DeepSeek Intel Provider: NON DISPONIBILE")
    except Exception as e:
        logging.warning(f"⚠️ Intelligence Router init failed: {e}")

    # Initialize database tables first (creates if not exist)
    init_db()

    # Initialize Market Intelligence DB (odds_snapshots table)
    if _MARKET_INTEL_AVAILABLE:
        try:
            init_market_intelligence_db()
        except Exception as e:
            logging.warning(f"⚠️ Market Intelligence DB init failed: {e}")

    # Run database migrations (adds new columns if needed)
    check_and_migrate()

    # ============================================
    # COVE FIX: Validate Telegram Credentials Before Starting
    # ============================================
    logging.info("🔍 Validating Telegram credentials...")
    try:
        from src.alerting.notifier import validate_telegram_chat_id, validate_telegram_credentials

        # Validate bot token
        validate_telegram_credentials()

        # Validate chat ID format
        if not validate_telegram_chat_id():
            logging.warning("⚠️ Telegram chat ID validation failed, but continuing...")
    except ValueError as e:
        logging.error(f"❌ Telegram credentials validation failed: {e}")
        logging.error("❌ Bot will start but alerts may not be sent!")
        logging.error(
            "❌ Please check .env file and ensure TELEGRAM_TOKEN and TELEGRAM_CHAT_ID are correct."
        )
    except Exception as e:
        logging.warning(f"⚠️ Telegram validation skipped: {e}")

    # ============================================
    # V11.0: GLOBAL ORCHESTRATOR (Global Parallel Architecture)
    # ============================================
    # This implements GLOBAL EYES: monitors ALL active leagues simultaneously
    # No time restrictions - the bot sees the whole world at once
    logging.info("🌐 Initializing GlobalOrchestrator for Global Parallel Architecture...")

    orchestrator = get_global_orchestrator()
    active_leagues_result = orchestrator.get_all_active_leagues()

    active_leagues = active_leagues_result["leagues"]
    active_continent_blocks = active_leagues_result["continent_blocks"]
    settlement_mode = active_leagues_result["settlement_mode"]
    source = active_leagues_result["source"]
    utc_hour = active_leagues_result["utc_hour"]

    # Log the orchestrator results
    logging.info("🌐 GlobalOrchestrator Results (GLOBAL EYES ACTIVE):")
    logging.info(f"   UTC Hour: {utc_hour}:00")
    logging.info(f"   Source: {source}")
    logging.info(
        f"   Active Continental Blocks: {', '.join(active_continent_blocks) if active_continent_blocks else 'None'}"
    )
    logging.info(f"   Settlement Mode: {settlement_mode}")
    logging.info(f"   Leagues to Scan: {len(active_leagues)}")

    # V11.0: No settlement window in Global mode - always process
    if settlement_mode:
        logging.info("⚠️ Settlement mode detected (should not happen in Global mode)")
        # Continue anyway - Global mode has no maintenance window

    # If no active leagues found, fall back to static discovery
    if not active_leagues:
        logging.warning(
            "⚠️ No active leagues from ContinentalOrchestrator, falling back to static discovery"
        )
        try:
            active_leagues = get_active_niche_leagues(max_leagues=5)
            logging.info(
                f"🎯 Found {len(active_leagues)} active niche leagues (static). Processing top 5 to save quota."
            )
            for league in active_leagues:
                logging.info(f"   📌 {league}")
        except Exception as e:
            logging.warning(f"⚠️ League discovery failed: {e} - using defaults")
            active_leagues = []

    # V11.0: Initialize Intelligence Queue for Global Parallel Architecture
    _discovery_queue = None
    try:
        from src.utils.discovery_queue import DiscoveryQueue

        discovery_queue = DiscoveryQueue(max_entries=1000, ttl_hours=24)
        logging.info("✅ [GLOBAL-EYES] Intelligence Queue initialized")
    except ImportError:
        logging.warning("⚠️ [GLOBAL-EYES] DiscoveryQueue not available")

    # V5.0.2: Cleanup expired browser monitor discoveries to prevent memory leaks
    try:
        from src.processing.news_hunter import cleanup_expired_browser_monitor_discoveries

        cleanup_expired_browser_monitor_discoveries()
    except ImportError:
        pass
    except Exception as e:
        logging.debug(f"Browser monitor cleanup skipped: {e}")

    # V5.0.2: Reset AI response stats for this cycle
    try:
        from src.analysis.analyzer import reset_ai_response_stats

        reset_ai_response_stats()
    except ImportError:
        pass

    # Initialize FotMob provider
    try:
        fotmob = get_data_provider()
    except Exception as e:
        logging.error(f"Failed to initialize FotMob: {e}")
        fotmob = None

    # 1. Ingest Fixtures & Update Odds (uses auto-discovered leagues)
    logging.info("📊 Refreshing fixtures and odds from The-Odds-API...")
    ingest_fixtures(use_auto_discovery=True)

    # 2. Initialize Analysis Engine
    logging.info("🧠 Initializing Analysis Engine...")
    analysis_engine = get_analysis_engine()

    # 3. Check for Odds Drops
    logging.info("💹 Checking for significant odds movements...")
    analysis_engine.check_odds_drops()

    # 3.5. RADAR TRIGGER INBOX (Cross-Process Handoff)
    # Check for pending radar triggers and process them
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        triggers_processed = process_radar_triggers(
            analysis_engine=analysis_engine,
            fotmob=fotmob,
            now_utc=now_utc,
            db=db,
        )
        if triggers_processed > 0:
            logging.info(
                f"✅ RADAR INBOX: Processed {triggers_processed} trigger(s) from News Radar"
            )
    except Exception as e:
        logging.error(f"❌ RADAR INBOX: Failed to process triggers: {e}")
        db.rollback()
    finally:
        db.close()

    # 3.6. CLEANUP STALE RADAR TRIGGERS (Maintenance)
    # Clean up triggers that have been stuck in PENDING_RADAR_TRIGGER for too long
    try:
        cleanup_stats = cleanup_stale_radar_triggers(timeout_minutes=10)
        if cleanup_stats.get("triggers_cleaned", 0) > 0:
            logging.warning(
                f"🧹 STALE TRIGGER CLEANUP: Marked {cleanup_stats['triggers_cleaned']} stale trigger(s) as FAILED"
            )
        if cleanup_stats.get("triggers_failed", 0) > 0:
            logging.error(
                f"❌ STALE TRIGGER CLEANUP: Failed to update {cleanup_stats['triggers_failed']} trigger(s)"
            )
    except Exception as e:
        logging.error(f"❌ STALE TRIGGER CLEANUP: Failed to run cleanup: {e}")

    # 4. BISCOTTO SCANNER
    logging.info("🍪 Scanning for Biscotto suspects (suspicious Draw odds)...")
    biscotto_suspects = analysis_engine.check_biscotto_suspects()

    # Send alerts for EXTREME suspects
    for suspect in biscotto_suspects:
        if suspect["severity"] == "EXTREME":
            try:
                # Verify alert before sending (Final Verifier)
                if _FINAL_VERIFIER_AVAILABLE:
                    should_send, final_verification_info = verify_biscotto_alert_before_telegram(
                        match=suspect["match"],
                        draw_odd=suspect["draw_odd"],
                        drop_pct=suspect["drop_pct"],
                        severity=suspect["severity"],
                        reasoning=suspect["reason"],
                        news_url=None,  # Biscotto alerts don't have news_url
                    )

                    if should_send:
                        send_biscotto_alert(
                            match=suspect["match"],
                            reason=suspect["reason"],
                            draw_odd=suspect["draw_odd"],
                            drop_pct=suspect["drop_pct"],
                            final_verification_info=final_verification_info,
                        )
                    else:
                        logging.warning(
                            f"🍪 Biscotto alert blocked by Final Verifier: "
                            f"{final_verification_info.get('reason', 'Unknown')}"
                        )
                else:
                    # Final Verifier not available, send without verification
                    send_biscotto_alert(
                        match=suspect["match"],
                        reason=suspect["reason"],
                        draw_odd=suspect["draw_odd"],
                        drop_pct=suspect["drop_pct"],
                    )
            except Exception as e:
                logging.error(f"Failed to send Biscotto alert: {e}")

    db = SessionLocal()
    try:
        # 3. Select Matches (Next 72 hours) - ELITE LEAGUES ONLY for AI Analysis
        # GHOST MATCH FIX: Use naive datetime for DB comparison (SQLite stores naive)
        now_utc = datetime.now(timezone.utc)
        now_naive = now_utc.replace(tzinfo=None)  # DB stores naive datetimes
        end_window_naive = now_naive + timedelta(hours=ANALYSIS_WINDOW_HOURS)

        # V11.0: Process Intelligence Queue (Global Parallel Architecture)
        # V11.1 FIX: Queue processing enabled with real iteration implementation
        # Items are processed proactively here and also available via pop_for_match()
        if discovery_queue:
            try:
                # Note: In production, this should be an async task running in parallel
                # For now, we'll call it synchronously
                process_intelligence_queue(
                    discovery_queue=discovery_queue,
                    db_session=db,
                    fotmob=fotmob,
                    now_utc=now_utc,
                )
            except Exception as e:
                logging.error(f"❌ [INTELLIGENCE-QUEUE] Failed to process queue: {e}")

        # Filter to Elite 6 leagues only to save API credits on AI analysis
        # HARD-BLOCK: Only future matches (start_time > now) within the analysis window
        matches = (
            db.query(Match)
            .filter(
                Match.start_time > now_naive,  # STRICT: Future only (Ghost Match Prevention)
                Match.start_time <= end_window_naive,
                Match.league.in_(ELITE_LEAGUES),
            )
            .all()
        )

        logging.info(
            f"Trovate {len(matches)} partite Elite da analizzare nelle prossime {ANALYSIS_WINDOW_HOURS} ore."
        )

        # V4.3: Tier 2 Fallback tracking
        increment_cycle()  # Incrementa contatore cicli per fallback system
        tier1_alerts_sent = 0
        tier1_high_potential_count = 0

        # 4. TRIANGULATION LOOP (INVESTIGATOR MODE) - DELEGATED TO ANALYSIS ENGINE
        # The Analysis Engine now handles all match-level analysis logic
        for match in matches:
            # V10.5: Check for Nitter intel before analysis
            nitter_intel = None
            if _NITTER_INTEL_AVAILABLE:
                try:
                    intel_data = get_nitter_intel_for_match(match.id)
                    if intel_data:
                        nitter_intel = intel_data.get("intel")
                        logging.info(
                            f"🐦 [NITTER-INTEL] Found intel for {match.home_team} vs {match.away_team} "
                            f"via {intel_data.get('handle')}"
                        )
                except Exception as e:
                    logging.debug(f"Nitter intel check failed: {e}")

            # Use Analysis Engine to analyze match
            analysis_result = analysis_engine.analyze_match(
                match=match,
                fotmob=fotmob,
                now_utc=now_utc,
                db_session=db,
                context_label="TIER1",
                nitter_intel=nitter_intel,  # V10.5: Pass Nitter intel to analysis
            )

            # Track alerts sent
            if analysis_result["alert_sent"]:
                tier1_alerts_sent += 1
            if analysis_result["score"] >= ALERT_THRESHOLD_HIGH:
                tier1_high_potential_count += 1

            # Log any errors
            if analysis_result["error"]:
                logging.warning(
                    f"⚠️ Analysis error for {match.home_team} vs {match.away_team}: {analysis_result['error']}"
                )

        # 5. TIER 2 FALLBACK (V4.3)
        # If no Tier 1 alerts were sent, try Tier 2 leagues

        if tier1_alerts_sent == 0 and should_activate_tier2_fallback(
            tier1_alerts_sent, tier1_high_potential_count
        ):
            logging.info("🔄 Activating Tier 2 Fallback...")

            tier2_batch = get_tier2_fallback_batch(max_leagues=3)

            if tier2_batch:
                logging.info(f"🎯 Tier 2 Fallback: Processing {len(tier2_batch)} leagues")

                for league_key in tier2_batch:
                    try:
                        # Get matches for this Tier 2 league
                        tier2_matches = (
                            db.query(Match)
                            .filter(
                                Match.start_time > now_naive,
                                Match.start_time <= end_window_naive,
                                Match.league == league_key,
                            )
                            .all()
                        )

                        logging.info(f"   Found {len(tier2_matches)} matches in {league_key}")

                        # Process Tier 2 matches (simplified analysis)
                        for match in tier2_matches:
                            # V10.5: Check for Nitter intel before analysis
                            nitter_intel = None
                            if _NITTER_INTEL_AVAILABLE:
                                try:
                                    intel_data = get_nitter_intel_for_match(match.id)
                                    if intel_data:
                                        nitter_intel = intel_data.get("intel")
                                        logging.info(
                                            f"🐦 [NITTER-INTEL] Found intel for {match.home_team} vs {match.away_team} "
                                            f"via {intel_data.get('handle')}"
                                        )
                                except Exception as e:
                                    logging.debug(f"Nitter intel check failed: {e}")

                            # Use Analysis Engine for Tier 2 analysis
                            analysis_result = analysis_engine.analyze_match(
                                match=match,
                                fotmob=fotmob,
                                now_utc=now_utc,
                                db_session=db,
                                context_label="TIER2",
                                nitter_intel=nitter_intel,  # V10.5: Pass Nitter intel to analysis
                            )

                            # Log results
                            if analysis_result["alert_sent"]:
                                tier1_alerts_sent += 1

                            if analysis_result["error"]:
                                logging.warning(
                                    f"⚠️ Tier 2 analysis error: {analysis_result['error']}"
                                )

                    except Exception as e:
                        logging.warning(f"⚠️ Tier 2 processing failed for {league_key}: {e}")

                record_tier2_activation()
            else:
                logging.warning("⚠️ No Tier 2 leagues available for fallback")

        # 6. SUMMARY
        logging.info("\n📊 PIPELINE SUMMARY:")
        logging.info(f"   Matches analyzed: {len(matches)}")
        logging.info(f"   Tier 1 alerts sent: {tier1_alerts_sent}")
        logging.info(f"   Tier 1 high potential: {tier1_high_potential_count}")

        # 7. CLEANUP
        if _MARKET_INTEL_AVAILABLE:
            try:
                cleanup_old_snapshots()
            except Exception as e:
                logging.warning(f"⚠️ Market intelligence cleanup failed: {e}")

    finally:
        db.close()


# ============================================
# V11.0: INTELLIGENCE QUEUE CONSUMPTION (Global Parallel Architecture)
# ============================================


async def process_intelligence_queue(discovery_queue: DiscoveryQueue, db_session, fotmob, now_utc):
    """
    Process items from the intelligence queue.

    This is the main consumer for the Global Parallel Architecture.
    It:
    1. Gets items from queue
    2. Checks Tavily and Brave budgets
    3. Runs DeepSeek analysis
    4. Saves to database

    Args:
        discovery_queue: DiscoveryQueue instance
        db_session: Database session
        fotmob: FotMob data provider
        now_utc: Current UTC datetime
    """
    if not discovery_queue:
        logging.warning("⚠️ [INTELLIGENCE-QUEUE] No queue available")
        return

    # Get queue size
    queue_size = discovery_queue.size()
    if queue_size == 0:
        logging.debug("📭 [INTELLIGENCE-QUEUE] Queue is empty")
        return

    logging.info(f"📥 [INTELLIGENCE-QUEUE] Processing {queue_size} queued signals")

    # Check budgets
    tavily_available = False
    brave_available = False

    try:
        from src.ingestion.tavily_budget import get_budget_manager as get_tavily_budget
        from src.ingestion.tavily_provider import get_tavily_provider

        tavily = get_tavily_provider()
        tavily_budget = get_tavily_budget()
        tavily_available = tavily.is_available() and tavily_budget.can_call("intelligence_queue")
    except ImportError:
        logging.debug("⚠️ [INTELLIGENCE-QUEUE] Tavily not available")

    try:
        from src.ingestion.brave_budget import get_budget_manager as get_brave_budget
        from src.ingestion.brave_provider import get_brave_provider

        brave = get_brave_provider()
        brave_budget = get_brave_budget()
        brave_available = brave.is_available() and brave_budget.can_call("intelligence_queue")
    except ImportError:
        logging.debug("⚠️ [INTELLIGENCE-QUEUE] Brave not available")

    logging.info(
        f"💰 [INTELLIGENCE-QUEUE] Budgets: Tavily={tavily_available}, Brave={brave_available}"
    )

    # V11.1 FIX: Implement real queue iteration and processing
    # Get all items from queue (thread-safe access)
    items_to_process = []
    with discovery_queue._lock:
        # Make a copy of the queue for processing
        items_to_process = list(discovery_queue._queue)

    # Process queue items
    processed_count = 0
    max_items = 10  # Limit per cycle to prevent overwhelming

    for item in items_to_process[:max_items]:
        try:
            # Skip expired items
            if item.is_expired(discovery_queue._ttl_hours):
                logging.debug(f"⏰ [INTELLIGENCE-QUEUE] Skipping expired item: {item.title[:50]}")
                continue

            # Extract item data
            item_data = item.data.copy()
            team_name = item.team
            league_key = item.league_key
            title = item.title
            url = item.url
            category = item.category
            confidence = item.confidence

            logging.info(
                f"🔍 [INTELLIGENCE-QUEUE] Processing: {title[:50]} (team={team_name}, conf={confidence:.2f})"
            )

            # V11.1: Process with Tavily/Brave if budgets available
            # This is a proactive processing - items will also be available via pop_for_match()
            if tavily_available or brave_available:
                try:
                    # Build query for intelligence analysis
                    query = f"Analyze this {category.lower()} for {team_name}: {title}"

                    # Use Tavily for enrichment if available
                    if tavily_available:
                        try:
                            from src.ingestion.tavily_query_builder import TavilyQueryBuilder

                            tavily_query = TavilyQueryBuilder.build_news_intelligence_query(
                                team_name=team_name,
                                news_title=title,
                                news_url=url,
                                category=category,
                            )

                            tavily_result = tavily.search(query=tavily_query, max_results=3)
                            if tavily_result and tavily_result.get("results"):
                                logging.info(
                                    f"📊 [INTELLIGENCE-QUEUE] Tavily enrichment for {team_name}: {len(tavily_result['results'])} results"
                                )
                                # Could save enriched data to database here
                        except Exception as e:
                            logging.debug(f"Tavily enrichment failed: {e}")

                    # Use Brave for additional context if available
                    if brave_available:
                        try:
                            brave_result = brave.search_news(
                                query=query, limit=3, component="intelligence_queue"
                            )
                            if brave_result and len(brave_result) > 0:
                                logging.info(
                                    f"🔍 [INTELLIGENCE-QUEUE] Brave context for {team_name}: {len(brave_result)} results"
                                )
                                # Could save enriched data to database here
                        except Exception as e:
                            logging.debug(f"Brave enrichment failed: {e}")

                    # Note: We don't remove items from queue here
                    # Items remain available for pop_for_match() during match analysis
                    # Expired items are cleaned up by cleanup_expired()

                    processed_count += 1

                except Exception as e:
                    logging.error(f"❌ [INTELLIGENCE-QUEUE] Failed to process item: {e}")
            else:
                logging.debug(
                    "⏸️ [INTELLIGENCE-QUEUE] No budget available for proactive processing - item remains in queue"
                )
                # Still count as processed (will be available via pop_for_match)
                processed_count += 1

        except Exception as e:
            logging.error(f"❌ [INTELLIGENCE-QUEUE] Error processing queue item: {e}")

    logging.info(f"✅ [INTELLIGENCE-QUEUE] Processed {processed_count} signals")


# ============================================
# NIGHTLY SETTLEMENT (V4.4 - Settlement Service Integration)
# ============================================
def should_run_settlement() -> bool:
    """
    Check if it's time to run nightly settlement.

    V4.4 FIX: With 2-hour cycles, checking `hour == 4` worked fine.
    With 2-hour cycles, if bot runs at 03:00, next cycle is 05:00 → skips 04:00!

    FIX: Changed to `4 <= hour < 8` so settlement runs on first cycle after 04:00.
    """
    current_hour = datetime.now(timezone.utc).hour
    return 4 <= current_hour < 8


def run_nightly_settlement(optimizer=None):
    """
    Run nightly settlement of pending bets using Settlement Service.

    This function delegates to SettlementService which:
    - Settles all pending bets based on match results
    - Updates the database accordingly
    - Feeds results to Strategy Optimizer (Learning Loop)
    - Generates performance summaries

    Args:
        optimizer: Optional StrategyOptimizer instance for learning loop
    """
    logging.info("🌙 Running nightly settlement...")

    try:
        # Get settlement service and run settlement
        settlement_service = get_settlement_service(optimizer=optimizer)
        settlement_service.run_settlement(lookback_hours=48)
        logging.info("✅ Nightly settlement completed")
    except Exception as e:
        logging.error(f"❌ Nightly settlement failed: {e}")


# ============================================
# OPPORTUNITY RADAR (V5.0)
# ============================================
def should_run_radar() -> bool:
    """
    Check if it's time to run Opportunity Radar.

    Radar runs every 4 hours.
    """
    current_hour = datetime.now(timezone.utc).hour
    return current_hour % 4 == 0


def run_opportunity_radar():
    """
    Run Opportunity Radar scan for high-value opportunities.

    This function scans for undervalued matches and insider news
    that may indicate profitable betting opportunities.
    """
    logging.info("📡 Running Opportunity Radar...")

    try:
        from src.ingestion.opportunity_radar import run_radar_scan

        run_radar_scan()
        logging.info("✅ Opportunity Radar completed")
    except Exception as e:
        logging.error(f"❌ Opportunity Radar failed: {e}")


# ============================================
# TWITTER INTEL REFRESH (V4.5)
# ============================================
def refresh_twitter_intel_sync():
    """
    Refresh Twitter Intel cache synchronously.

    This function ensures the Twitter Intel cache is fresh
    before each analysis cycle.

    V9.5 FIX: Updated to call async refresh_twitter_intel() method
    with DeepSeek provider instead of non-existent refresh() method.
    """
    if not _TWITTER_INTEL_AVAILABLE:
        return

    try:
        cache = get_twitter_intel_cache()
        if not cache.is_fresh:
            logging.info("🐦 Refreshing Twitter Intel cache...")

            # V9.5 FIX: Get DeepSeek provider and call async refresh method
            if _DEEPSEEK_PROVIDER_AVAILABLE:
                try:
                    deepseek_provider = get_deepseek_provider()
                    # Run async method synchronously
                    stats = asyncio.run(
                        cache.refresh_twitter_intel(
                            gemini_service=deepseek_provider, max_posts_per_account=5
                        )
                    )
                    logging.info(
                        f"✅ Twitter Intel cache refreshed: {stats.get('total_tweets_cached', 0)} tweets cached"
                    )
                except Exception as e:
                    logging.warning(f"⚠️ Twitter Intel async refresh failed: {e}")
            else:
                logging.warning(
                    "⚠️ DeepSeek provider not available, cannot refresh Twitter Intel cache"
                )
    except Exception as e:
        logging.warning(f"⚠️ Twitter Intel refresh failed: {e}")


# ============================================
# BACKGROUND WORKERS CLEANUP (V5.2)
# ============================================
def _cleanup_background_workers(
    browser_monitor_instance, browser_monitor_loop, browser_monitor_thread
):
    """
    Cleanup background workers before shutdown.

    This function ensures all background workers are properly
    stopped and cleaned up before the application exits.
    """
    if browser_monitor_instance and browser_monitor_loop:
        try:
            # Stop the browser monitor
            if browser_monitor_instance.is_running():
                asyncio.run_coroutine_threadsafe(
                    browser_monitor_instance.stop(), browser_monitor_loop
                ).result(timeout=10)

            # Stop the event loop
            browser_monitor_loop.call_soon_threadsafe(browser_monitor_loop.stop)

            # Wait for thread to finish
            if browser_monitor_thread and browser_monitor_thread.is_alive():
                browser_monitor_thread.join(timeout=5)

            logging.info("✅ Browser monitor cleanup completed")
        except Exception as e:
            logging.warning(f"⚠️ Browser monitor cleanup failed: {e}")


# ============================================
# CONTINUOUS LOOP (V6.0)
# ============================================
def run_continuous():
    """Continuous loop - runs pipeline every hour"""
    logging.info("🦅 EARLYBIRD NEWS & ODDS MONITOR - 24/7 MODE ACTIVATED")

    # Log elite quality thresholds
    logging.info("🎯 ELITE QUALITY FILTERING - High Bar Configuration:")
    logging.info(f"   Standard Matches: Score >= {ALERT_THRESHOLD_HIGH} (was 8.6)")
    logging.info(f"   Radar Matches (Insider News): Score >= {ALERT_THRESHOLD_RADAR} (was 7.0)")

    # Initialize health monitor
    health = get_health_monitor()

    # Initialize optimizer (loads persisted weights)
    optimizer = get_optimizer()
    logging.info(optimizer.get_summary())

    cycle_count = 0
    error_count = 0

    # V5.1: Track browser monitor state
    browser_monitor_instance = None
    browser_monitor_started = False
    browser_monitor_loop = None  # Keep reference to event loop
    browser_monitor_thread = None  # V5.2: Keep reference for graceful shutdown

    # V5.1: Start Browser Monitor (always-on web monitoring)
    if _BROWSER_MONITOR_AVAILABLE:
        try:
            import asyncio
            import threading

            browser_monitor_instance = get_browser_monitor()
            browser_monitor_instance._on_news_discovered = register_browser_monitor_discovery

            # Create a dedicated event loop for browser monitor
            browser_monitor_loop = asyncio.new_event_loop()

            def run_browser_monitor_loop():
                """Run the browser monitor event loop in a dedicated thread."""
                asyncio.set_event_loop(browser_monitor_loop)
                try:
                    browser_monitor_loop.run_until_complete(browser_monitor_instance.start())
                    # Keep the loop running for the scan task
                    browser_monitor_loop.run_forever()
                except Exception as e:
                    logging.error(f"❌ [BROWSER-MONITOR] Loop error: {e}")
                finally:
                    # V5.2: Ensure Playwright cleanup happens in this loop
                    if browser_monitor_instance and browser_monitor_instance._browser:
                        try:
                            browser_monitor_loop.run_until_complete(
                                browser_monitor_instance._shutdown_playwright()
                            )
                        except Exception as cleanup_err:
                            logging.warning(
                                f"⚠️ [BROWSER-MONITOR] Playwright cleanup error: {cleanup_err}"
                            )
                    try:
                        browser_monitor_loop.close()
                    except Exception:
                        pass

            # V5.2: Non-daemon thread for graceful shutdown
            browser_monitor_thread = threading.Thread(
                target=run_browser_monitor_loop,
                name="BrowserMonitorThread",
                daemon=False,  # V5.2: Allow graceful cleanup
            )
            browser_monitor_thread.start()

            # V7.9: Wait for startup to complete with proper synchronization
            # This eliminates the race condition where main thread checks is_running()
            # before Playwright initialization completes (which can take 2-3+ seconds)
            # V11.1 FIX: Increased timeout from 10s to 90s for VPS deployment (browser binary download)
            if browser_monitor_instance.wait_for_startup(timeout=90.0):
                if browser_monitor_instance.is_running():
                    browser_monitor_started = True
                    logging.info("🌐 [BROWSER-MONITOR] Started - monitoring web sources 24/7")
                else:
                    logging.warning("⚠️ [BROWSER-MONITOR] Failed to start")
            else:
                logging.error("❌ [BROWSER-MONITOR] Startup timeout after 90 seconds")
        except Exception as e:
            logging.warning(f"⚠️ [BROWSER-MONITOR] Startup error: {e}")

    # V6.0: Register high-priority callback for event-driven processing
    # When Browser Monitor discovers high-confidence news (INJURY, SUSPENSION, LINEUP),
    # this callback triggers immediate analysis instead of waiting 120 minutes
    # V11.1 FIX: Implemented immediate trigger for high-priority discoveries
    if _DISCOVERY_QUEUE_AVAILABLE:
        try:
            # Store references for callback closure
            _analysis_engine_ref = None
            _fotmob_ref = None
            _db_ref = None

            def on_high_priority_discovery(league_key: str) -> None:
                """
                Callback invoked when high-priority news is discovered.

                V11.1: Triggers immediate analysis for the affected league instead
                of waiting 120 minutes for the next cycle.

                This runs a mini-pipeline that:
                1. Filters matches for this specific league
                2. Runs analysis with optimizer, analyzer, notifier
                3. Sends immediate alerts
                """
                nonlocal _analysis_engine_ref, _fotmob_ref, _db_ref

                logging.info(
                    f"🚨 [HIGH-PRIORITY] News discovered for {league_key} - triggering immediate analysis"
                )

                try:
                    # Initialize components if not already done
                    if _analysis_engine_ref is None:
                        from src.core.analysis_engine import get_analysis_engine

                        _analysis_engine_ref = get_analysis_engine()

                    if _fotmob_ref is None:
                        from src.ingestion.data_provider import get_data_provider

                        _fotmob_ref = get_data_provider()

                    if _db_ref is None:
                        _db_ref = SessionLocal()

                    # Get current time
                    now_utc = datetime.now(timezone.utc)
                    now_naive = now_utc.replace(tzinfo=None)
                    end_window_naive = now_naive + timedelta(hours=ANALYSIS_WINDOW_HOURS)

                    # Filter matches for this specific league (within analysis window)
                    league_matches = (
                        _db_ref.query(Match)
                        .filter(
                            Match.start_time > now_naive,
                            Match.start_time <= end_window_naive,
                            Match.league == league_key,
                        )
                        .all()
                    )

                    if not league_matches:
                        logging.info(
                            f"📭 [HIGH-PRIORITY] No upcoming matches found for {league_key}"
                        )
                        return

                    logging.info(
                        f"⚡ [HIGH-PRIORITY] Analyzing {len(league_matches)} match(es) for {league_key}"
                    )

                    # Analyze each match in the league
                    for match in league_matches:
                        try:
                            # Check for Nitter intel before analysis
                            nitter_intel = None
                            if _NITTER_INTEL_AVAILABLE:
                                try:
                                    from src.processing.nitter_intel import (
                                        get_nitter_intel_for_match,
                                    )

                                    intel_data = get_nitter_intel_for_match(match.id)
                                    if intel_data:
                                        nitter_intel = intel_data.get("intel")
                                        logging.info(
                                            f"🐦 [HIGH-PRIORITY] Nitter intel found for {match.home_team} vs {match.away_team}"
                                        )
                                except Exception as e:
                                    logging.debug(f"Nitter intel check failed: {e}")

                            # Run analysis
                            analysis_result = _analysis_engine_ref.analyze_match(
                                match=match,
                                fotmob=_fotmob_ref,
                                now_utc=now_utc,
                                db_session=_db_ref,
                                context_label="HIGH_PRIORITY",
                                nitter_intel=nitter_intel,
                            )

                            if analysis_result["alert_sent"]:
                                logging.info(
                                    f"📢 [HIGH-PRIORITY] Alert sent for {match.home_team} vs {match.away_team}"
                                )

                            if analysis_result["error"]:
                                logging.warning(
                                    f"⚠️ [HIGH-PRIORITY] Analysis error for {match.home_team} vs {match.away_team}: {analysis_result['error']}"
                                )

                        except Exception as e:
                            logging.error(
                                f"❌ [HIGH-PRIORITY] Failed to analyze match {match.id}: {e}"
                            )

                    logging.info(
                        f"✅ [HIGH-PRIORITY] Completed immediate analysis for {league_key}"
                    )

                except Exception as e:
                    logging.error(
                        f"❌ [HIGH-PRIORITY] Failed to trigger analysis for {league_key}: {e}"
                    )

            queue = get_discovery_queue()
            queue.register_high_priority_callback(
                callback=on_high_priority_discovery,
                threshold=0.85,
                categories=["INJURY", "SUSPENSION", "LINEUP"],
            )
            logging.info("📢 [QUEUE] High-priority callback registered for event-driven processing")
        except Exception as e:
            logging.warning(f"⚠️ [QUEUE] Failed to register high-priority callback: {e}")

    # Send initial heartbeat on startup
    if health.should_send_heartbeat():
        startup_msg = health.get_heartbeat_message()
        startup_msg = startup_msg.replace("✅ System operational", "🚀 System starting up...")
        send_status_message(startup_msg)
        health.mark_heartbeat_sent()

    while True:
        cycle_count += 1

        # Check for pause lock file
        if os.path.exists(PAUSE_FILE):
            logging.info("💤 System Paused (pause.lock detected). Sleeping 60s...")
            time.sleep(60)
            continue

        try:
            current_time = time.strftime("%H:%M:%S")
            logging.info(f"\n⏰ CYCLE {cycle_count} START: {current_time}")

            # V9.5: Refresh local mirror with social_sources and news_sources at start of each cycle
            if _SUPABASE_PROVIDER_AVAILABLE:
                try:
                    logging.info("🔄 Refreshing Supabase mirror at start of cycle...")
                    from src.database.supabase_provider import refresh_mirror

                    success = refresh_mirror()

                    if success:
                        logging.info("✅ Supabase mirror refreshed successfully")
                    else:
                        logging.warning("⚠️ Mirror refresh failed, using existing mirror")

                except Exception as e:
                    logging.error(f"❌ Mirror refresh failed: {e}")
                    logging.info("📦 Using existing local mirror")

            # V4.5: Refresh Twitter Intel Cache at start of each cycle
            refresh_twitter_intel_sync()

            # Check if it's time for nightly settlement (04:00 UTC)
            if should_run_settlement():
                run_nightly_settlement(optimizer=optimizer)

            # Check if it's time for Opportunity Radar (every 4 hours)
            if should_run_radar():
                run_opportunity_radar()

            run_pipeline()

            # V3.7: Run system diagnostics at end of pipeline (if enabled)
            if settings.HEALTH_MONITOR_ENABLED:
                logging.info("🩺 Running system diagnostics...")
                issues = health.run_diagnostics()
                if issues:
                    health.report_issues(issues)
            else:
                logging.info("⚠️ Service Health Monitor Disabled by config.")

            # V2.0: Log SWR cache metrics periodically
            try:
                from src.ingestion.data_provider import log_fotmob_cache_metrics

                logging.info("📊 Logging SWR cache metrics...")
                log_fotmob_cache_metrics()
            except Exception as e:
                logging.warning(f"⚠️ Failed to log SWR cache metrics: {e}")

            # V11.1: Cleanup expired queue items periodically
            # Items remain in queue for pop_for_match() but expired items should be removed
            if _DISCOVERY_QUEUE_AVAILABLE:
                try:
                    queue = get_discovery_queue()
                    removed = queue.cleanup_expired()
                    if removed > 0:
                        logging.info(f"🧹 [QUEUE] Cleaned up {removed} expired items")
                except Exception as e:
                    logging.error(f"❌ [QUEUE] Cleanup failed: {e}")

            # Record successful scan
            health.record_scan()

            # Reset error count on successful run
            error_count = 0

            # Check if it's time for a heartbeat (every 4 hours)
            if health.should_send_heartbeat():
                heartbeat_msg = health.get_heartbeat_message()
                if send_status_message(heartbeat_msg):
                    health.mark_heartbeat_sent()

            logging.info("💤 Sleeping for 360 minutes (6 hours) until next cycle...")
            time.sleep(21600)

        except KeyboardInterrupt:
            logging.info("\n🛑 SHUTDOWN SIGNAL RECEIVED")
            logging.info(f"📊 Final stats: {cycle_count} cycles completed")

            # V5.2: Cleanup background workers before exit
            _cleanup_background_workers(
                browser_monitor_instance, browser_monitor_loop, browser_monitor_thread
            )

            # Send shutdown notification
            shutdown_msg = (
                "🛑 <b>EARLYBIRD SHUTDOWN</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ Uptime: {health.uptime_str}\n"
                f"🔄 Scans: {health.stats.total_scans}\n"
                f"📤 Alerts: {health.stats.total_alerts_sent}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                "👋 Manual shutdown received"
            )
            send_status_message(shutdown_msg)
            break

        except MemoryError as e:
            error_count += 1
            health.record_error(str(e))
            logging.critical(f"💀 CRITICAL MEMORY ERROR in cycle {cycle_count}: {e}")
            logging.critical("System may be running out of memory. Consider restarting.")

            # Send error alert with spam protection
            if health.should_send_error_alert():
                send_status_message(health.get_error_message(e))
                health.mark_error_alert_sent()

            if error_count >= 3:
                logging.critical("🚨 TOO MANY MEMORY ERRORS - SHUTTING DOWN")
                # V5.2: Cleanup before exit
                _cleanup_background_workers(
                    browser_monitor_instance, browser_monitor_loop, browser_monitor_thread
                )
                break
            time.sleep(600)  # Wait 10 minutes

        except ConnectionError as e:
            error_count += 1
            health.record_error(str(e))
            logging.error(f"🌐 CONNECTION ERROR in cycle {cycle_count}: {e}")
            logging.warning(f"Network issue detected. Retry {error_count}/5")

            # Send error alert with spam protection
            if health.should_send_error_alert():
                send_status_message(health.get_error_message(e))
                health.mark_error_alert_sent()

            if error_count >= 5:
                logging.critical("🚨 TOO MANY CONNECTION ERRORS - SHUTTING DOWN")
                # V5.2: Cleanup before exit
                _cleanup_background_workers(
                    browser_monitor_instance, browser_monitor_loop, browser_monitor_thread
                )
                break
            time.sleep(300)  # Wait 5 minutes

        except Exception as e:
            error_count += 1
            health.record_error(str(e))
            logging.critical(
                f"💥 UNEXPECTED CRITICAL ERROR in cycle {cycle_count}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            logging.warning(f"Error count: {error_count}/5")

            # Send error alert with spam protection
            if health.should_send_error_alert():
                send_status_message(health.get_error_message(e))
                health.mark_error_alert_sent()

            if error_count >= 5:
                logging.critical("🚨 TOO MANY CONSECUTIVE ERRORS - SHUTTING DOWN FOR SAFETY")
                logging.critical("Please check logs and restart manually.")
                # V5.2: Cleanup before exit
                _cleanup_background_workers(
                    browser_monitor_instance, browser_monitor_loop, browser_monitor_thread
                )
                break

            # Exponential backoff
            wait_time = min(300 * error_count, 1800)  # Max 30 minutes
            logging.info(f"⏳ Waiting {wait_time // 60} minutes before retry...")
            time.sleep(wait_time)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EarlyBird News & Odds Monitor - 24/7 Mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Componenti principali:
- Pipeline Odds + News + Analysis
- Browser Monitor per fonti web
- Database tracking e alert
- Auto-restart su errori

Modalità:
- --help   : Mostra questo aiuto
- --test   : Verifica configurazione senza avviare
- --status : Mostra stato sistema corrente
- default : Avvia monitoraggio 24/7

Examples:
    python src/main.py
    python src/main.py --test
    python src/main.py --status
        """,
    )

    parser.add_argument("--test", action="store_true", help="Test configuration without starting")

    parser.add_argument("--status", action="store_true", help="Show current system status")

    return parser.parse_args()


def test_main_configuration():
    """Verifica configurazione main pipeline senza avviare."""
    logging.info("🦅 Verifica configurazione Main Pipeline...")

    # Test database
    try:
        init_db()
        logging.info("✅ Database: OK")
    except Exception as e:
        logging.error(f"❌ Database: {e}")
        return False

    # Test import moduli critici
    try:
        logging.info("✅ Import moduli critici: OK")
    except Exception as e:
        logging.error(f"❌ Import moduli: {e}")
        return False

    # Test services availability
    services_status = {
        "Intelligence Router": _INTELLIGENCE_ROUTER_AVAILABLE,
        "Market Intelligence": _MARKET_INTEL_AVAILABLE,
        "Fatigue Engine": _FATIGUE_ENGINE_AVAILABLE,
        "Biscotto Engine": _BISCOTTO_ENGINE_AVAILABLE,
        "Twitter Intel": _TWITTER_INTEL_AVAILABLE,
        "Browser Monitor": _BROWSER_MONITOR_AVAILABLE,
        "Verification Layer": _VERIFICATION_LAYER_AVAILABLE,
    }

    for service, available in services_status.items():
        status = "✅" if available else "⚠️"
        logging.info(f"{status} {service}: {'Available' if available else 'Not Available'}")

    logging.info("✅ Main Pipeline pronto per l'avvio")
    return True


def show_system_status():
    """Mostra stato corrente del sistema."""
    logging.info("📊 Stato Sistema EarlyBird...")

    try:
        # Check database
        from src.database.models import SessionLocal

        db = SessionLocal()

        # Count matches
        from src.database.models import Match

        match_count = db.query(Match).count()
        logging.info(f"✅ Database: {match_count} partite salvate")

        # Count recent alerts - use only existing columns to avoid migration issues
        try:
            from src.database.models import NewsLog

            recent_alerts = (
                db.query(NewsLog)
                .filter(NewsLog.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24))
                .count()
            )
            logging.info(f"📢 Alert ultime 24h: {recent_alerts}")
        except Exception as db_error:
            logging.warning(f"⚠️ Count alerts non disponibile: {db_error}")
            # Fallback: count total alerts without time filter
            try:
                total_alerts = db.query(NewsLog).count()
                logging.info(f"📢 Alert totali: {total_alerts}")
            except Exception:
                logging.info("📢 Alert: Non disponibili")

        db.close()

    except Exception as e:
        logging.error(f"❌ Errore stato database: {e}")

    # Check services
    services = [
        ("Intelligence Router", _INTELLIGENCE_ROUTER_AVAILABLE),
        ("Browser Monitor", _BROWSER_MONITOR_AVAILABLE),
        ("Verification Layer", _VERIFICATION_LAYER_AVAILABLE),
    ]

    for name, available in services:
        status = "✅" if available else "❌"
        logging.info(f"{status} {name}: {'Active' if available else 'Inactive'}")


# ============================================
# OPPORTUNITY RADAR INTEGRATION (V1.0)
# ============================================
def analyze_single_match(match_id: str, forced_narrative: str = None):
    """
    Analyze a single match triggered by Opportunity Radar.

    This function is called by the Opportunity Radar when it detects
    high-value intelligence (B_TEAM, CRISIS, KEY_RETURN) about a team.
    It creates a NewsLog entry for the radar narrative and triggers
    the full analysis pipeline for the match.

    Args:
        match_id: The match ID from the database
        forced_narrative: Optional narrative text to inject into the analysis

    Returns:
        Dict with analysis results including alert_sent, score, error
    """
    result = {"alert_sent": False, "score": 0.0, "error": None}

    try:
        # 1. Get database session
        db = SessionLocal()

        try:
            # 2. Retrieve the Match object
            match = db.query(Match).filter(Match.id == match_id).first()
            if not match:
                result["error"] = f"Match with ID {match_id} not found in database"
                logging.error(result["error"])
                return result

            logging.info(
                f"🎯 RADAR ANALYSIS: {match.home_team} vs {match.away_team} (ID: {match_id})"
            )

            # 3. Create NewsLog entry for radar narrative
            if forced_narrative:
                radar_log = NewsLog(
                    match_id=match_id,
                    url="radar://opportunity-radar",
                    summary=forced_narrative,
                    score=10,  # Maximum score for radar-detected intelligence
                    category="RADAR_INTEL",
                    affected_team=match.home_team,  # Default to home team
                    source="radar",
                    source_confidence=0.9,
                    status="pending",
                )
                db.add(radar_log)
                db.commit()
                logging.info("✅ Radar narrative logged in NewsLog")

            # 4. Initialize FotMob provider
            try:
                fotmob = get_data_provider()
            except Exception as e:
                logging.error(f"Failed to initialize FotMob: {e}")
                fotmob = None

            # 5. Initialize Analysis Engine
            analysis_engine = get_analysis_engine()

            # 6. Run match analysis with RADAR context
            now_utc = datetime.now(timezone.utc)
            now_naive = now_utc.replace(tzinfo=None)

            analysis_result = analysis_engine.analyze_match(
                match=match, fotmob=fotmob, now_utc=now_naive, db_session=db, context_label="RADAR"
            )

            # 7. Return results
            result["alert_sent"] = analysis_result.get("alert_sent", False)
            result["score"] = analysis_result.get("score", 0.0)
            result["error"] = analysis_result.get("error")

            if result["alert_sent"]:
                logging.info(
                    f"✅ RADAR ALERT SENT for {match.home_team} vs {match.away_team} (Score: {result['score']})"
                )
            else:
                logging.info(
                    f"ℹ️ RADAR analysis completed for {match.home_team} vs {match.away_team} (Score: {result['score']}, No alert)"
                )

            return result

        finally:
            db.close()

    except Exception as e:
        error_msg = f"analyze_single_match failed for match {match_id}: {type(e).__name__}: {e}"
        result["error"] = error_msg
        logging.error(error_msg, exc_info=True)
        return result


if __name__ == "__main__":
    # Parse arguments
    args = parse_args()

    # Handle special modes
    if args.test:
        success = test_main_configuration()
        sys.exit(0 if success else 1)

    if args.status:
        show_system_status()
        sys.exit(0)

    # ✅ NEW: Pre-flight validation BEFORE entering main loop
    try:
        from src.utils.startup_validator import validate_startup_or_exit

        validate_startup_or_exit()
    except ImportError as e:
        logging.warning(f"⚠️ Startup validator not available: {e}")
        logging.warning("⚠️ Proceeding without validation checks")

    # Emergency cleanup BEFORE any DB operation
    try:
        emergency_cleanup()
    except Exception as e:
        logging.warning(f"⚠️ Emergency cleanup failed: {e}")

    # Normal startup
    try:
        run_continuous()
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested by user")
    except Exception as e:
        logging.critical(f"💀 FATAL ERROR - SYSTEM CRASH: {type(e).__name__}: {e}", exc_info=True)
        raise
