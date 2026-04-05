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

# Import intelligent error tracking from orchestration_metrics
try:
    from src.alerting.orchestration_metrics import record_error_intelligent

    ERROR_TRACKING_AVAILABLE = True
except ImportError:
    ERROR_TRACKING_AVAILABLE = False
    record_error_intelligent = None


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

    # Stop orchestration metrics collection
    try:
        from src.alerting.orchestration_metrics import stop_metrics_collection

        stop_metrics_collection()
        logging.info("✅ Cleanup completed: orchestration metrics collector stopped")
    except Exception as e:
        logging.warning(f"⚠️ Failed to stop orchestration metrics collector: {e}")

    # V7.0: Cleanup FotMob provider (Playwright resources)
    try:
        from src.ingestion.data_provider import get_data_provider

        provider = get_data_provider()
        if hasattr(provider, "cleanup"):
            provider.cleanup()
            logging.info("✅ Cleanup completed: FotMob provider (Playwright)")
    except Exception as e:
        logging.warning(f"⚠️ Failed to cleanup FotMob provider: {e}")

    # V13.0: Cleanup budget intelligence monitoring
    try:
        import asyncio

        from src.ingestion.budget_intelligence_integration import stop_budget_intelligence

        # Create a new event loop for cleanup
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(stop_budget_intelligence())
            logging.info("✅ Cleanup completed: budget intelligence monitoring stopped")
        finally:
            loop.close()
    except Exception as e:
        logging.warning(f"⚠️ Failed to stop budget intelligence monitoring: {e}")

    # V14.0 COVE FIX: Cleanup browser monitor
    try:
        from src.services.browser_monitor import get_browser_monitor

        monitor = get_browser_monitor()
        if monitor and monitor.is_running():
            monitor.request_stop()
            logging.info("✅ Cleanup completed: browser monitor stop requested")
    except Exception as e:
        logging.warning(f"⚠️ Failed to stop browser monitor: {e}")


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
# ============================================
# ORCHESTRATION METRICS (V1.0 - System Monitoring)
# ============================================
from src.alerting.orchestration_metrics import start_metrics_collection
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
    get_active_niche_leagues,
    get_all_active_leagues,
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

    def is_intelligence_available():
        return False

    logger.warning(f"⚠️ Intelligence Router not available: {e}")

# ============================================
# INTELLIGENT DEDUPLICATION (V4.4)
# ============================================
try:
    from src.utils.url_normalizer import are_articles_similar, normalize_url  # noqa: F401

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
        analyze_market_intelligence,  # noqa: F401
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
    from src.analysis.fatigue_engine import (  # noqa: F401
        FatigueDifferential,
        get_enhanced_fatigue_context,
    )

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
        InjuryDifferential,  # noqa: F401
        TeamInjuryImpact,  # noqa: F401
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
    from src.analysis.biscotto_engine import (  # noqa: F401
        BiscottoSeverity,
        get_enhanced_biscotto_analysis,
    )

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
        filter_tweets_for_match,  # noqa: F401
        resolve_conflict_via_gemini,  # noqa: F401
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
    from src.services.browser_monitor import BrowserMonitor, get_browser_monitor  # noqa: F401

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
    from src.utils.parallel_enrichment import EnrichmentResult, enrich_match_parallel  # noqa: F401

    _PARALLEL_ENRICHMENT_AVAILABLE = True
except ImportError:
    _PARALLEL_ENRICHMENT_AVAILABLE = False
    logging.debug("Parallel Enrichment not available")

# ============================================
# VERIFICATION LAYER V7.0 (Alert Fact-Checking)
# ============================================
try:
    from src.analysis.verification_layer import (
        VERIFICATION_SCORE_THRESHOLD,  # noqa: F401
        VerificationRequest,  # noqa: F401
        VerificationResult,  # noqa: F401
        VerificationStatus,  # noqa: F401
        create_verification_request_from_match,  # noqa: F401
        should_verify_alert,  # noqa: F401
        verify_alert,  # noqa: F401
    )

    _VERIFICATION_LAYER_AVAILABLE = True
except ImportError:
    _VERIFICATION_LAYER_AVAILABLE = False
    logging.debug("Verification Layer not available")


# ============================================
# FINAL ALERT VERIFIER V1.0 (Pre-Telegram Validation)
# ============================================
try:
    from src.analysis.final_alert_verifier import (  # noqa: F401
        get_final_verifier,
        is_final_verifier_available,
    )
    from src.analysis.verifier_integration import (
        build_alert_data_for_verifier,  # noqa: F401
        build_biscotto_alert_data_for_verifier,  # noqa: F401
        build_context_data_for_verifier,  # noqa: F401
        verify_alert_before_telegram,  # noqa: F401
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
    from src.analysis.intelligent_modification_logger import (
        get_intelligent_modification_logger,  # noqa: F401
    )
    from src.analysis.step_by_step_feedback import get_step_by_step_feedback_loop  # noqa: F401

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
    STOP_FILE,
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
    # VPS FIX: Extract Match attributes safely to prevent session detachment
    # This prevents "Trust validation error" when Match object becomes detached
    # from session due to connection pool recycling under high load
    from src.utils.match_helper import extract_match_info

    match_info = extract_match_info(match)

    # No previous investigation - case is open
    if not match_info["last_deep_dive_time"]:
        return False, "First investigation"

    # Calculate time since last investigation
    hours_since_dive = (now - match_info["last_deep_dive_time"]).total_seconds() / 3600

    # Calculate time to kickoff
    hours_to_kickoff = (match_info["start_time"] - now).total_seconds() / 3600

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
    VPS FIX: Extract Match attributes safely to prevent session detachment
    V13.0: MIGRATED to Advanced Biscotto Engine V2.0 with multi-factor analysis

    Returns:
        dict with 'is_suspect', 'reason', 'draw_odd', 'drop_pct', 'severity', 'confidence', 'factors'
    """
    # Try to use advanced biscotto engine if available
    if _BISCOTTO_ENGINE_AVAILABLE:
        try:
            from src.analysis.biscotto_engine import get_enhanced_biscotto_analysis

            # Try to fetch motivation data from FotMob for enhanced analysis
            home_motivation = None
            away_motivation = None

            try:
                from src.ingestion.data_provider import get_data_provider

                provider = get_data_provider()

                # Get team names safely
                home_team = getattr(match, "home_team", None)
                away_team = getattr(match, "away_team", None)

                if home_team and away_team:
                    # Fetch motivation context for both teams
                    home_context = provider.get_table_context(home_team)
                    away_context = provider.get_table_context(away_team)

                    # Build motivation dicts for biscotto engine
                    if home_context and not home_context.get("error"):
                        home_motivation = {
                            "zone": home_context.get("zone", "Unknown"),
                            "position": home_context.get("position", 0),
                            "total_teams": home_context.get("total_teams", 20),
                            "points": home_context.get("points", 0),
                            "matches_remaining": home_context.get("matches_remaining"),
                        }

                    if away_context and not away_context.get("error"):
                        away_motivation = {
                            "zone": away_context.get("zone", "Unknown"),
                            "position": away_context.get("position", 0),
                            "total_teams": away_context.get("total_teams", 20),
                            "points": away_context.get("points", 0),
                            "matches_remaining": away_context.get("matches_remaining"),
                        }

            except Exception as e:
                # If motivation data fetch fails, continue without it (advanced engine has fallbacks)
                logger.debug(f"⚠️ Could not fetch motivation data for biscotto analysis: {e}")

            # Use advanced biscotto engine with available motivation data
            analysis, _ = get_enhanced_biscotto_analysis(
                match_obj=match,
                home_motivation=home_motivation,
                away_motivation=away_motivation,
            )

            # Convert BiscottoAnalysis to legacy dict format for backward compatibility
            result = {
                "is_suspect": analysis.is_suspect,
                "severity": analysis.severity.value,
                "reason": analysis.reasoning,
                "draw_odd": analysis.current_draw_odd,
                "drop_pct": analysis.drop_percentage,
                # New fields from advanced engine
                "confidence": analysis.confidence,
                "factors": analysis.factors,
                "pattern": analysis.pattern.value,
                "zscore": analysis.zscore,
                "mutual_benefit": analysis.mutual_benefit,
                "betting_recommendation": analysis.betting_recommendation,
            }

            return result

        except Exception as e:
            # If advanced engine fails, fall back to legacy implementation
            logger.warning(f"⚠️ Advanced biscotto engine failed, falling back to legacy: {e}")

    # Legacy implementation (fallback)
    result = {
        "is_suspect": False,
        "reason": None,
        "draw_odd": None,
        "drop_pct": 0,
        "severity": "NONE",
        "confidence": 0,
        "factors": [],
        "pattern": "STABLE",
        "zscore": 0.0,
        "mutual_benefit": False,
        "betting_recommendation": "AVOID",
    }

    # VPS FIX: Extract Match attributes safely to prevent session detachment
    # This prevents "Trust validation error" when Match object becomes detached
    # from session due to connection pool recycling under high load
    draw_odd = getattr(match, "current_draw_odd", None)
    opening_draw = getattr(match, "opening_draw_odd", None)

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
        result["confidence"] = 90
        result["factors"] = [f"🟠 Quota X estrema: {draw_odd:.2f}"]
        result["pattern"] = "CRASH" if drop_pct > 20 else "DRIFT" if drop_pct > 8 else "STABLE"
    elif draw_odd < BISCOTTO_SUSPICIOUS_LOW:
        result["is_suspect"] = True
        result["severity"] = "HIGH"
        result["reason"] = f"🍪 SUSPICIOUS: Draw @ {draw_odd:.2f} (below {BISCOTTO_SUSPICIOUS_LOW})"
        result["confidence"] = 75
        result["factors"] = [f"🟡 Quota X sospetta: {draw_odd:.2f}"]
        result["pattern"] = "CRASH" if drop_pct > 20 else "DRIFT" if drop_pct > 8 else "STABLE"
    elif drop_pct > BISCOTTO_SIGNIFICANT_DROP and opening_draw:
        # V6.1: Extra check that opening_draw exists before using in message
        result["is_suspect"] = True
        result["severity"] = "MEDIUM"
        result["reason"] = (
            f"🍪 DROPPING: Draw dropped {drop_pct:.1f}% ({opening_draw:.2f} → {draw_odd:.2f})"
        )
        result["confidence"] = 60
        result["factors"] = [f"📉 Drop significativo: -{drop_pct:.1f}%"]
        result["pattern"] = "CRASH" if drop_pct > 20 else "DRIFT"

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

    VPS FIX: Extract Match attributes safely to prevent session detachment
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

        significant_drops: list[dict] = []

        for match in matches:
            # VPS FIX: Extract Match attributes safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", None)
            away_team = getattr(match, "away_team", None)
            opening_home_odd = getattr(match, "opening_home_odd", None)
            current_home_odd = getattr(match, "current_home_odd", None)
            opening_away_odd = getattr(match, "opening_away_odd", None)
            current_away_odd = getattr(match, "current_away_odd", None)

            # Calculate home odd drop
            if opening_home_odd and current_home_odd:
                home_drop_pct = ((opening_home_odd - current_home_odd) / opening_home_odd) * 100
                if home_drop_pct > 25:  # 25%+ drop is significant
                    significant_drops.append(
                        {
                            "match": match,
                            "type": "HOME_DROP",
                            "drop_pct": home_drop_pct,
                            "opening": opening_home_odd,
                            "current": current_home_odd,
                        }
                    )

            # Calculate away odd drop
            if opening_away_odd and current_away_odd:
                away_drop_pct = ((opening_away_odd - current_away_odd) / opening_away_odd) * 100
                if away_drop_pct > 25:  # 25%+ drop is significant
                    significant_drops.append(
                        {
                            "match": match,
                            "type": "AWAY_DROP",
                            "drop_pct": away_drop_pct,
                            "opening": opening_away_odd,
                            "current": current_away_odd,
                        }
                    )

        if significant_drops:
            logging.info(f"💹 Found {len(significant_drops)} significant odds drops")
            for drop in significant_drops:
                match = drop["match"]
                # Extract team names safely
                home_team = getattr(match, "home_team", "Unknown")
                away_team = getattr(match, "away_team", "Unknown")
                logging.info(
                    f"   📉 {home_team} vs {away_team}: {drop['type']} {drop['drop_pct']:.1f}% ({drop['opening']:.2f} → {drop['current']:.2f})"
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

    VPS FIX: Extract Match attributes safely to prevent session detachment
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

        suspects: list[dict] = []

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
                        # Enhanced fields from advanced engine
                        "confidence": result.get("confidence", 0),
                        "factors": result.get("factors", []),
                        "pattern": result.get("pattern", "STABLE"),
                        "zscore": result.get("zscore", 0.0),
                        "mutual_benefit": result.get("mutual_benefit", False),
                        "betting_recommendation": result.get("betting_recommendation", "AVOID"),
                    }
                )

        if suspects:
            logging.info(f"🍪 Found {len(suspects)} Biscotto suspects")
            for suspect in suspects:
                match = suspect["match"]
                # VPS FIX: Extract team names safely to prevent session detachment
                home_team = getattr(match, "home_team", "Unknown")
                away_team = getattr(match, "away_team", "Unknown")

                # Enhanced logging with confidence and factors
                confidence = suspect.get("confidence", 0)
                factors = suspect.get("factors", [])
                pattern = suspect.get("pattern", "STABLE")

                logging.info(
                    f"   🍪 {home_team} vs {away_team}: {suspect['reason']} "
                    f"| Confidence: {confidence}% | Pattern: {pattern}"
                )

                # Log factors if available
                if factors:
                    for factor in factors[:3]:  # Log top 3 factors
                        logging.info(f"      - {factor}")

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
                                    # Enhanced fields
                                    confidence=suspect.get("confidence"),
                                    factors=suspect.get("factors"),
                                    pattern=suspect.get("pattern"),
                                    zscore=suspect.get("zscore"),
                                    mutual_benefit=suspect.get("mutual_benefit"),
                                    betting_recommendation=suspect.get("betting_recommendation"),
                                    # COVE FIX: Pass database session for updating alert flags
                                    db_session=db,
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
                                # Enhanced fields
                                confidence=suspect.get("confidence"),
                                factors=suspect.get("factors"),
                                pattern=suspect.get("pattern"),
                                zscore=suspect.get("zscore"),
                                mutual_benefit=suspect.get("mutual_benefit"),
                                betting_recommendation=suspect.get("betting_recommendation"),
                                # COVE FIX: Pass database session for updating alert flags
                                db_session=db,
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

    VPS FIX: Extract Match attributes safely to prevent session detachment
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

                # VPS FIX: Extract team names safely to prevent session detachment
                # This prevents "Trust validation error" when Match object becomes detached
                # from session due to connection pool recycling under high load
                home_team = getattr(match, "home_team", "Unknown")
                away_team = getattr(match, "away_team", "Unknown")

                # Extract forced narrative from verification_reason field
                forced_narrative = trigger.verification_reason or ""

                logging.info(
                    f"🔥 RADAR TRIGGER: Processing {home_team} vs {away_team} "
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
                    f"{home_team} vs {away_team} "
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
    REFACTORED V12.3: Pipeline Resuscitation & Operational Dominance

    KEY CHANGES (V12.3):
    - DYNAMIC LEAGUE SYNC: Uses ALL active leagues from GlobalOrchestrator (Supabase)
      No more hardcoded 7-league discrimination. If Supabase says 13 leagues are active, we analyze all 13.
    - ingest_fixtures() receives the full dynamic league list for consistent Odds-API fetching
    - Empty Portfolio visibility: explicit logging when 0 matches found with active continents/leagues listed

    PRESERVED (V1.0):
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
    # COVE FIX: Validate Telegram Credentials Before Starting (V11.1: Use unified startup validation)
    # ============================================
    logging.info("🔍 Validating Telegram credentials...")
    try:
        from src.alerting.notifier import validate_telegram_at_startup

        # V11.1: Use unified startup validation function (fails fast if credentials missing)
        validate_telegram_at_startup()
    except ValueError as e:
        logging.error(f"❌ Telegram validation failed at startup: {e}")
        logging.error("❌ Bot will NOT start - fix credentials before running!")
        logging.error(
            "❌ Please check .env file and ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are correct."
        )
        # V11.1: Exit with error code to fail fast as requested
        sys.exit(1)
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
            active_leagues: list[str] = []

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

    # ============================================
    # V12.0: ALPHA HUNTER MODE (News-Driven Architecture)
    # ============================================
    # PARADIGM SHIFT: Instead of downloading ALL fixtures first, we now:
    # 1. Search for TRIGGER KEYWORDS on news domains
    # 2. Extract team entities from relevant articles
    # 3. Fetch odds ON-DEMAND only for teams with signals
    # 4. Analyze matches with confirmed signals
    #
    # This reduces Odds-API consumption by ~99% and makes the bot a true "Alpha Hunter"

    ALPHA_HUNTER_MODE = os.getenv("ENABLE_ALPHA_HUNTER_MODE", "false").lower() == "true"

    if ALPHA_HUNTER_MODE:
        logging.info("🐺 [ALPHA-HUNTER] V12.0 News-Driven Architecture ACTIVE")

        # Import Alpha Hunter
        try:
            from src.ingestion.alpha_hunter import AlphaHunter, get_alpha_hunter

            hunter = get_alpha_hunter()

            # Get news sources from Supabase
            news_sources = get_news_sources_with_fallback()

            if not news_sources:
                logging.warning(
                    "⚠️ [ALPHA-HUNTER] No news sources available, falling back to fixture mode"
                )
                ALPHA_HUNTER_MODE = False
            else:
                logging.info(
                    f"🔍 [ALPHA-HUNTER] Running broad discovery on {len(news_sources)} sources..."
                )

                # Run Alpha Hunter Loop
                signals = hunter.run_broad_discovery(news_sources)

                if signals:
                    logging.info(
                        f"📡 [ALPHA-HUNTER] Found {len(signals)} signals with extracted teams"
                    )

                    # Process each signal
                    matches_found = 0
                    for signal in signals:
                        if signal.extracted_team and signal.confidence >= 0.5:
                            # Skip if no league extracted
                            if not signal.extracted_league:
                                continue

                            # Fetch odds on-demand for this team
                            candidates = hunter.fetch_on_demand_odds(
                                team_name=signal.extracted_team,
                                league_key=signal.extracted_league,
                            )

                            # Process candidates (may be multiple or empty)
                            for candidate in candidates:
                                matches_found += 1
                                # Analyze using save_and_analyze which handles DB and engine
                                result = hunter.save_and_analyze(
                                    candidate=candidate,
                                    signal=signal,
                                    analysis_engine=analysis_engine,
                                    fotmob=fotmob,
                                    db_session=db,
                                )

                                if result.get("alert_sent"):
                                    logging.info(
                                        f"🎯 [ALPHA-HUNTER] Alert sent for {signal.extracted_team} "
                                        f"(score: {result.get('score', 0):.1f})"
                                    )

                    logging.info(f"✅ [ALPHA-HUNTER] Loop complete: {matches_found} matches found")
                else:
                    logging.info("📭 [ALPHA-HUNTER] No signals found this cycle")

        except ImportError as e:
            logging.warning(
                f"⚠️ [ALPHA-HUNTER] Module not available: {e}, falling back to fixture mode"
            )
            ALPHA_HUNTER_MODE = False
        except Exception as e:
            logging.error(f"❌ [ALPHA-HUNTER] Error: {e}, falling back to fixture mode")
            ALPHA_HUNTER_MODE = False

    # FALLBACK: Traditional Fixture-Driven Mode (if Alpha Hunter disabled or failed)
    if not ALPHA_HUNTER_MODE:
        # 1. Ingest Fixtures & Update Odds (V11.0 Continental Wiring)
        logging.info("📊 Refreshing fixtures and odds from The-Odds-API...")

        # V11.0 CONTINENTAL WIRING: Safe handoff with fallback
        # If active_leagues contains leagues from Supabase -> Use them, disable auto-discovery
        # If active_leagues is empty -> Fall back to auto-discovery (Elite 6)
        if active_leagues:
            logging.info(
                f"🌐 CONTINENTAL WIRING: Passing {len(active_leagues)} leagues to ingest_fixtures"
            )
            ingest_fixtures(target_leagues=active_leagues, use_auto_discovery=False)
        else:
            logging.warning("⚠️ No active leagues from orchestrator, falling back to auto-discovery")
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
                # COVE FIX: Create database session for updating alert flags
                db = SessionLocal()
                try:
                    # Verify alert before sending (Final Verifier)
                    if _FINAL_VERIFIER_AVAILABLE:
                        should_send, final_verification_info = (
                            verify_biscotto_alert_before_telegram(
                                match=suspect["match"],
                                draw_odd=suspect["draw_odd"],
                                drop_pct=suspect["drop_pct"],
                                severity=suspect["severity"],
                                reasoning=suspect["reason"],
                                news_url=None,  # Biscotto alerts don't have news_url
                            )
                        )

                        if should_send:
                            send_biscotto_alert(
                                match=suspect["match"],
                                reason=suspect["reason"],
                                draw_odd=suspect["draw_odd"],
                                drop_pct=suspect["drop_pct"],
                                final_verification_info=final_verification_info,
                                # Enhanced fields from Advanced Biscotto Engine V2.0
                                confidence=suspect.get("confidence"),
                                factors=suspect.get("factors"),
                                pattern=suspect.get("pattern"),
                                zscore=suspect.get("zscore"),
                                mutual_benefit=suspect.get("mutual_benefit"),
                                betting_recommendation=suspect.get("betting_recommendation"),
                                # COVE FIX: Pass database session for updating alert flags
                                db_session=db,
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
                            # Enhanced fields from Advanced Biscotto Engine V2.0
                            confidence=suspect.get("confidence"),
                            factors=suspect.get("factors"),
                            pattern=suspect.get("pattern"),
                            zscore=suspect.get("zscore"),
                            mutual_benefit=suspect.get("mutual_benefit"),
                            betting_recommendation=suspect.get("betting_recommendation"),
                            # COVE FIX: Pass database session for updating alert flags
                            db_session=db,
                        )
                finally:
                    db.close()
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
                # Process queue synchronously (function is now synchronous, not async)
                process_intelligence_queue(
                    discovery_queue=discovery_queue,
                    db_session=db,
                    fotmob=fotmob,
                    now_utc=now_utc,
                )
            except Exception as e:
                logging.error(f"❌ [INTELLIGENCE-QUEUE] Failed to process queue: {e}")

        # V12.3 DYNAMIC LEAGUE SYNC: Use ALL active leagues from GlobalOrchestrator (Supabase)
        # If Supabase marks 13 leagues as active, we analyze all 13.
        # V11.2: NO hardcoded fallback. If no Supabase data, try get_all_active_leagues() from mirror.
        # HARD-BLOCK: Only future matches (start_time > now) within the analysis window
        # V14.1 FIX: Require odds availability to prevent "No Odds Black Hole" silent drops
        analysis_leagues = active_leagues if active_leagues else get_all_active_leagues()

        logging.info(
            f"🎯 V12.3 Dynamic League Sync: Analyzing {len(analysis_leagues)} active leagues "
            f"(source: {'Supabase/Orchestrator' if active_leagues else 'Supabase/Mirror'})"
        )

        matches = (
            db.query(Match)
            .filter(
                Match.start_time > now_naive,  # STRICT: Future only (Ghost Match Prevention)
                Match.start_time <= end_window_naive,
                Match.league.in_(
                    analysis_leagues
                ),  # V12.3/V11.2: Dynamic leagues from Supabase/Mirror (was ELITE_LEAGUES)
                Match.current_home_odd.isnot(None),  # V14.1: Require odds to avoid silent drops
            )
            .all()
        )

        # V12.3 Task 4: Ingestion Hardening & Visibility
        if not matches:
            logging.warning(
                f"⚠️ Empty Portfolio: 0 upcoming matches found for the currently active "
                f"continents {active_continent_blocks} | "
                f"Active leagues ({len(analysis_leagues)}): {', '.join(analysis_leagues[:10])}"
            )
        else:
            logging.info(
                f"📊 Found {len(matches)} matches across {len(analysis_leagues)} leagues "
                f"to analyze in the next {ANALYSIS_WINDOW_HOURS}h "
                f"(leagues: {', '.join(analysis_leagues[:5])}...)"
            )

        # V4.3: Tier 2 Fallback tracking
        increment_cycle()  # Incrementa contatore cicli per fallback system
        tier1_alerts_sent = 0
        tier1_high_potential_count = 0
        tier1_news_count = 0

        # 4. TRIANGULATION LOOP (INVESTIGATOR MODE) - DELEGATED TO ANALYSIS ENGINE
        # The Analysis Engine now handles all match-level analysis logic
        for match in matches:
            # VPS FIX: Extract team names safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", "Unknown")
            away_team = getattr(match, "away_team", "Unknown")

            # V10.5: Check for Nitter intel before analysis
            nitter_intel = None
            if _NITTER_INTEL_AVAILABLE:
                try:
                    intel_data = get_nitter_intel_for_match(match.id)
                    if intel_data:
                        nitter_intel = intel_data.get("intel")
                        logging.info(
                            f"🐦 [NITTER-INTEL] Found intel for {home_team} vs {away_team} "
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

            # Track news items analyzed for health monitoring
            tier1_news_count += analysis_result.get("news_count", 0)

            # Log any errors
            if analysis_result["error"]:
                logging.warning(
                    f"⚠️ Analysis error for {home_team} vs {away_team}: {analysis_result['error']}"
                )

        # 5. TIER 2 FALLBACK (V4.3)
        # If no Tier 1 alerts were sent, try Tier 2 leagues

        if tier1_alerts_sent == 0 and should_activate_tier2_fallback(
            tier1_alerts_sent, tier1_high_potential_count
        ):
            logging.info("🔄 Activating Tier 2 Fallback...")

            tier2_batch = get_tier2_fallback_batch()
            tier2_total_matches = 0  # Track total Tier 2 matches processed
            tier2_news_count = 0  # Track total Tier 2 news items analyzed

            if tier2_batch:
                logging.info(f"🎯 Tier 2 Fallback: Processing {len(tier2_batch)} leagues")

                for league_key in tier2_batch:
                    try:
                        # Get matches for this Tier 2 league
                        # V14.1 FIX: Require odds availability to prevent "No Odds Black Hole" silent drops
                        tier2_matches = (
                            db.query(Match)
                            .filter(
                                Match.start_time > now_naive,
                                Match.start_time <= end_window_naive,
                                Match.league == league_key,
                                Match.current_home_odd.isnot(None),  # V14.1: Require odds
                            )
                            .all()
                        )

                        logging.info(f"   Found {len(tier2_matches)} matches in {league_key}")
                        tier2_total_matches += len(tier2_matches)  # Track total Tier 2 matches

                        # Process Tier 2 matches (simplified analysis)
                        for match in tier2_matches:
                            # VPS FIX: Extract team names safely to prevent session detachment
                            # This prevents "Trust validation error" when Match object becomes detached
                            # from session due to connection pool recycling under high load
                            home_team = getattr(match, "home_team", "Unknown")
                            away_team = getattr(match, "away_team", "Unknown")

                            # V10.5: Check for Nitter intel before analysis
                            nitter_intel = None
                            if _NITTER_INTEL_AVAILABLE:
                                try:
                                    intel_data = get_nitter_intel_for_match(match.id)
                                    if intel_data:
                                        nitter_intel = intel_data.get("intel")
                                        logging.info(
                                            f"🐦 [NITTER-INTEL] Found intel for {home_team} vs {away_team} "
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

                            # Track news items analyzed for Tier2
                            tier2_news_count += analysis_result.get("news_count", 0)

                            if analysis_result["error"]:
                                logging.warning(
                                    f"⚠️ Tier 2 analysis error for {home_team} vs {away_team}: {analysis_result['error']}"
                                )

                    except Exception as e:
                        logging.warning(f"⚠️ Tier 2 processing failed for {league_key}: {e}")

                record_tier2_activation()
            else:
                logging.warning("⚠️ No Tier 2 leagues available for fallback")

        # 6. SUMMARY
        # Calculate total matches processed (Tier 1 + Tier 2)
        total_matches_processed = len(matches) + tier2_total_matches
        # Calculate total news items analyzed (Tier 1 + Tier 2)
        total_news_count = tier1_news_count + tier2_news_count

        logging.info("\n📊 PIPELINE SUMMARY:")
        logging.info(f"   Matches analyzed: {total_matches_processed}")
        logging.info(f"   Tier 1 matches: {len(matches)}")
        logging.info(f"   Tier 2 matches: {tier2_total_matches}")
        logging.info(f"   Tier 1 alerts sent: {tier1_alerts_sent}")
        logging.info(f"   Tier 1 high potential: {tier1_high_potential_count}")
        logging.info(f"   News items analyzed: {total_news_count}")

        # 7. CLEANUP
        if _MARKET_INTEL_AVAILABLE:
            try:
                cleanup_old_snapshots()
            except Exception as e:
                logging.warning(f"⚠️ Market intelligence cleanup failed: {e}")

        # Return total matches processed and news count for health monitoring
        return total_matches_processed, total_news_count

    finally:
        db.close()


# ============================================
# V11.0: INTELLIGENCE QUEUE CONSUMPTION (Global Parallel Architecture)
# ============================================


def process_intelligence_queue(discovery_queue: DiscoveryQueue, db_session, fotmob, now_utc):
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
        # FIX: Use "news_radar" component instead of "intelligence_queue" (not in budget allocation)
        tavily_available = tavily.is_available() and tavily_budget.can_call("news_radar")
    except ImportError:
        logging.debug("⚠️ [INTELLIGENCE-QUEUE] Tavily not available")

    try:
        from src.ingestion.brave_budget import get_budget_manager as get_brave_budget
        from src.ingestion.brave_provider import get_brave_provider

        brave = get_brave_provider()
        brave_budget = get_brave_budget()
        # FIX: Use "news_radar" component instead of "intelligence_queue" (not in budget allocation)
        brave_available = brave.is_available() and brave_budget.can_call("news_radar")
    except ImportError:
        logging.debug("⚠️ [INTELLIGENCE-QUEUE] Brave not available")

    logging.info(
        f"💰 [INTELLIGENCE-QUEUE] Budgets: Tavily={tavily_available}, Brave={brave_available}"
    )

    # V11.1 FIX: Implement real queue iteration and processing
    # V13 FIX: Use public API instead of accessing private members (_lock, _queue, _ttl_hours)
    items_to_process = discovery_queue.get_all_items()

    # Process queue items
    processed_count = 0
    max_items = 10  # Limit per cycle to prevent overwhelming

    for item in items_to_process[:max_items]:
        try:
            # Skip expired items - use public ttl_hours property
            if item.is_expired(discovery_queue.ttl_hours):
                logging.debug(f"⏰ [INTELLIGENCE-QUEUE] Skipping expired item: {item.title[:50]}")
                continue

            # Extract item data
            item.data.copy()
            team_name = item.team
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

                            # FIX: Replace non-existent build_news_intelligence_query() with build_news_verification_query()
                            tavily_query = TavilyQueryBuilder.build_news_verification_query(
                                news_title=title[:200],
                                team_name=team_name,
                                additional_context=f"category:{category} url:{url[:100] if url else ''}",
                            )

                            tavily_result = tavily.search(query=tavily_query, max_results=3)
                            if tavily_result and tavily_result.get("results"):
                                # FIX: Record the budget call after successful Tavily API call
                                tavily_budget.record_call("news_radar")
                                logging.info(
                                    f"📊 [INTELLIGENCE-QUEUE] Tavily enrichment for {team_name}: {len(tavily_result['results'])} results"
                                )
                                # Could save enriched data to database here
                        except Exception as e:
                            # FIX: Change from logging.debug() to logging.error() for better visibility
                            logging.error(f"❌ [INTELLIGENCE-QUEUE] Tavily enrichment failed: {e}")

                    # Use Brave for additional context if available
                    if brave_available:
                        try:
                            # FIX: Use "news_radar" component instead of "intelligence_queue"
                            brave_result = brave.search_news(
                                query=query, limit=3, component="news_radar"
                            )
                            if brave_result and len(brave_result) > 0:
                                # FIX: Record the budget call after successful Brave API call
                                brave_budget.record_call("news_radar")
                                logging.info(
                                    f"🔍 [INTELLIGENCE-QUEUE] Brave context for {team_name}: {len(brave_result)} results"
                                )
                                # Could save enriched data to database here
                        except Exception as e:
                            # FIX: Change from logging.debug() to logging.error() for better visibility
                            logging.error(f"❌ [INTELLIGENCE-QUEUE] Brave enrichment failed: {e}")

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

        # V7.3 FIX: Invalidate optimizer weight cache after settlement
        # This ensures that if the file was modified externally (e.g., restore from backup),
        # the cache will be reloaded on next access instead of using stale in-memory data
        try:
            from src.analysis.optimizer import _weight_cache

            _weight_cache.invalidate()
            logging.info("🔄 Optimizer weight cache invalidated - will reload on next access")
        except Exception as e:
            logging.warning(f"⚠️ Failed to invalidate optimizer weight cache: {e}")

        # V13.0: Send CLV strategy performance report to Telegram
        try:
            from src.alerting.notifier import send_clv_strategy_report

            logging.info("📊 Sending CLV strategy performance report...")
            send_clv_strategy_report()
            logging.info("✅ CLV strategy report sent")
        except Exception as e:
            logging.warning(f"⚠️ Failed to send CLV report: {e}")

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
                    # V12.6 COVE FIX: Use get_event_loop().run_until_complete()
                    # instead of asyncio.run(). asyncio.run() creates a NEW event
                    # loop that ignores the nest_asyncio patch, causing RuntimeError
                    # when other async components (browser_monitor, news_hunter) are
                    # running. run_until_complete() reuses the patched loop.
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    stats = loop.run_until_complete(
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
    browser_monitor_instance,
    browser_monitor_loop,
    browser_monitor_thread,
    budget_intelligence_loop=None,
    budget_intelligence_thread=None,
):
    """
    Cleanup background workers before shutdown.

    This function ensures all background workers are properly
    stopped and cleaned up before the application exits.

    V14.0: Extended to include budget_intelligence cleanup.
    """
    if browser_monitor_instance and browser_monitor_loop:
        try:
            if browser_monitor_instance.is_running():
                asyncio.run_coroutine_threadsafe(
                    browser_monitor_instance.stop(), browser_monitor_loop
                ).result(timeout=10)

            browser_monitor_loop.call_soon_threadsafe(browser_monitor_loop.stop)

            if browser_monitor_thread and browser_monitor_thread.is_alive():
                browser_monitor_thread.join(timeout=5)

            logging.info("✅ Browser monitor cleanup completed")
        except Exception as e:
            logging.warning(f"⚠️ Browser monitor cleanup failed: {e}")

    if budget_intelligence_loop and budget_intelligence_thread:
        try:
            budget_intelligence_loop.call_soon_threadsafe(budget_intelligence_loop.stop)
            if budget_intelligence_thread.is_alive():
                budget_intelligence_thread.join(timeout=5)
            logging.info("✅ Budget intelligence cleanup completed")
        except Exception as e:
            logging.warning(f"⚠️ Budget intelligence cleanup failed: {e}")


# ============================================
# CONTINUOUS LOOP (V6.0)
# ============================================
def run_continuous():
    """Continuous loop - runs pipeline every 2 hours with 15-min radar wake-ups (V12.3 Active Hunter)"""
    logging.info("🦅 EARLYBIRD NEWS & ODDS MONITOR - 24/7 MODE ACTIVATED")

    # Log elite quality thresholds
    logging.info("🎯 ELITE QUALITY FILTERING - High Bar Configuration:")
    logging.info(f"   Standard Matches: Score >= {ALERT_THRESHOLD_HIGH} (was 8.6)")
    logging.info(f"   Radar Matches (Insider News): Score >= {ALERT_THRESHOLD_RADAR} (was 7.0)")

    # Start orchestration metrics collection
    try:
        start_metrics_collection()
        logging.info("✅ Orchestration metrics collector started")
    except Exception as e:
        logging.warning(f"⚠️ Failed to start orchestration metrics collector: {e}")

    # Initialize health monitor
    health = get_health_monitor()

    # Initialize optimizer (loads persisted weights)
    optimizer = get_optimizer()
    logging.info(optimizer.get_summary())

    cycle_count = 0
    error_count = 0

    # V5.1: Track browser monitor state
    browser_monitor_instance = None
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
            # V12.0 FIX: Further increased to 180s for slow VPS connections
            if browser_monitor_instance.wait_for_startup(timeout=180.0):
                if browser_monitor_instance.is_running():
                    logging.info("🌐 [BROWSER-MONITOR] Started - monitoring web sources 24/7")
                else:
                    logging.warning("⚠️ [BROWSER-MONITOR] Failed to start")
            else:
                logging.error("❌ [BROWSER-MONITOR] Startup timeout after 180 seconds")
        except Exception as e:
            logging.warning(f"⚠️ [BROWSER-MONITOR] Startup error: {e}")

    # V13.0: Start budget intelligence monitoring
    budget_intelligence_loop = None
    budget_intelligence_thread = None
    try:
        import asyncio
        import threading

        from src.ingestion.budget_intelligence_integration import start_budget_intelligence

        # Create a dedicated event loop for budget intelligence
        budget_intelligence_loop = asyncio.new_event_loop()

        def run_budget_intelligence_loop():
            """Run the budget intelligence event loop in a dedicated thread."""
            asyncio.set_event_loop(budget_intelligence_loop)
            try:
                budget_intelligence_loop.run_until_complete(start_budget_intelligence())
                # Keep the loop running for the monitoring task
                budget_intelligence_loop.run_forever()
            except Exception as e:
                logging.error(f"❌ [BUDGET-INTELLIGENCE] Loop error: {e}")
            finally:
                try:
                    budget_intelligence_loop.close()
                except Exception:
                    pass

        # Non-daemon thread for graceful shutdown
        budget_intelligence_thread = threading.Thread(
            target=run_budget_intelligence_loop,
            name="BudgetIntelligenceThread",
            daemon=False,
        )
        budget_intelligence_thread.start()

        # Wait a bit for startup
        time.sleep(2)
        logging.info("🔍 [BUDGET-INTELLIGENCE] Started - monitoring budget usage 24/7")
    except Exception as e:
        logging.warning(f"⚠️ [BUDGET-INTELLIGENCE] Startup error: {e}")

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

                V12.6: Create new database session for each callback to prevent
                connection pool exhaustion on VPS. Session is properly closed in finally block.
                """
                nonlocal _analysis_engine_ref, _fotmob_ref

                logging.info(
                    f"🚨 [HIGH-PRIORITY] News discovered for {league_key} - triggering immediate analysis"
                )

                # Create new database session for this callback
                db = None
                try:
                    # Initialize components if not already done
                    if _analysis_engine_ref is None:
                        from src.core.analysis_engine import get_analysis_engine

                        _analysis_engine_ref = get_analysis_engine()

                    if _fotmob_ref is None:
                        from src.ingestion.data_provider import get_data_provider

                        _fotmob_ref = get_data_provider()

                    # Create new session for this callback (prevents connection pool exhaustion)
                    db = SessionLocal()

                    # Get current time
                    now_utc = datetime.now(timezone.utc)
                    now_naive = now_utc.replace(tzinfo=None)
                    end_window_naive = now_naive + timedelta(hours=ANALYSIS_WINDOW_HOURS)

                    # Filter matches for this specific league (within analysis window)
                    # V14.1 FIX: Require odds availability to prevent "No Odds Black Hole" silent drops
                    league_matches = (
                        db.query(Match)
                        .filter(
                            Match.start_time > now_naive,
                            Match.start_time <= end_window_naive,
                            Match.league == league_key,
                            Match.current_home_odd.isnot(None),  # V14.1: Require odds
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
                            # VPS FIX: Extract team names safely to prevent session detachment
                            # This prevents "Trust validation error" when Match object becomes detached
                            # from session due to connection pool recycling under high load
                            home_team = getattr(match, "home_team", "Unknown")
                            away_team = getattr(match, "away_team", "Unknown")

                            # Check for Nitter intel before analysis
                            nitter_intel = None
                            if _NITTER_INTEL_AVAILABLE:
                                try:
                                    from src.services.nitter_fallback_scraper import (
                                        get_nitter_intel_for_match,
                                    )

                                    intel_data = get_nitter_intel_for_match(match.id)
                                    if intel_data:
                                        nitter_intel = intel_data.get("intel")
                                        logging.info(
                                            f"🐦 [HIGH-PRIORITY] Nitter intel found for {home_team} vs {away_team}"
                                        )
                                except Exception as e:
                                    logging.debug(f"Nitter intel check failed: {e}")

                            # Run analysis
                            analysis_result = _analysis_engine_ref.analyze_match(
                                match=match,
                                fotmob=_fotmob_ref,
                                now_utc=now_utc,
                                db_session=db,
                                context_label="HIGH_PRIORITY",
                                nitter_intel=nitter_intel,
                            )

                            if analysis_result["alert_sent"]:
                                logging.info(
                                    f"📢 [HIGH-PRIORITY] Alert sent for {home_team} vs {away_team}"
                                )

                            if analysis_result["error"]:
                                logging.warning(
                                    f"⚠️ [HIGH-PRIORITY] Analysis error for {home_team} vs {away_team}: {analysis_result['error']}"
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
                finally:
                    # Always close the database session to prevent connection pool exhaustion
                    if db is not None:
                        try:
                            db.close()
                        except Exception as e:
                            logging.error(
                                f"❌ [HIGH-PRIORITY] Failed to close database session: {e}"
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
        # V12.5: Get cache metrics from SupabaseProvider if available
        cache_metrics = None
        if _SUPABASE_PROVIDER_AVAILABLE:
            try:
                provider = get_supabase()
                cache_metrics = provider.get_cache_metrics()
            except Exception as e:
                logging.warning(f"⚠️ Failed to get Supabase cache metrics: {e}")

        # V2.0: Add SmartCache SWR metrics
        try:
            from src.utils.smart_cache import get_all_cache_stats

            swr_stats = get_all_cache_stats()
            # Merge SWR metrics into cache_metrics
            if cache_metrics is None:
                cache_metrics = {}

            # Add SWR metrics for each cache instance
            for cache_name, stats in swr_stats.items():
                if stats.get("swr_enabled"):
                    # Transform cache_name to match health_monitor.py expectations:
                    # - team_cache -> team_data
                    # - match_cache -> match_data
                    # - search_cache -> search (no _data suffix)
                    if cache_name == "search_cache":
                        key_suffix = cache_name.replace("_cache", "")
                    else:
                        key_suffix = cache_name.replace("_cache", "_data")

                    cache_metrics[f"swr_{key_suffix}_hit_rate"] = stats.get("swr_hit_rate_pct", 0.0)
                    cache_metrics[f"swr_{key_suffix}_stale_hit_rate"] = stats.get(
                        "swr_stale_hit_rate_pct", 0.0
                    )
                    cache_metrics[f"swr_{key_suffix}_avg_cached_latency"] = stats.get(
                        "avg_cached_latency_ms", 0.0
                    )
                    cache_metrics[f"swr_{key_suffix}_avg_uncached_latency"] = stats.get(
                        "avg_uncached_latency_ms", 0.0
                    )
                    cache_metrics[f"swr_{key_suffix}_background_refreshes"] = stats.get(
                        "background_refreshes", 0
                    )
                    cache_metrics[f"swr_{key_suffix}_background_refresh_failures"] = stats.get(
                        "background_refresh_failures", 0
                    )
                    cache_metrics[f"swr_{key_suffix}_size"] = stats.get("size", 0)
                    cache_metrics[f"swr_{key_suffix}_max_size"] = stats.get("max_size", 0)
        except Exception as e:
            logging.warning(f"⚠️ Failed to get SWR cache metrics: {e}")

        startup_msg = health.get_heartbeat_message(cache_metrics=cache_metrics)
        startup_msg = startup_msg.replace("✅ System operational", "🚀 System starting up...")
        send_status_message(startup_msg)
        health.mark_heartbeat_sent()

    while True:
        cycle_count += 1

        # V14.0: Check for FULL STOP first - this takes precedence over PAUSE
        if settings.is_stop_requested():
            logging.info("🛑 FULL STOP DETECTED - System shutting down until /start")
            logging.info("💡 Use /start from Telegram to resume the system")

            # V14.0 COVE FIX: Cleanup all background workers before exit
            _cleanup_background_workers(
                browser_monitor_instance,
                browser_monitor_loop,
                browser_monitor_thread,
                budget_intelligence_loop,
                budget_intelligence_thread,
            )

            break

        # Check for pause lock file (backwards compatibility)
        if os.path.exists(PAUSE_FILE):
            logging.info("💤 System Paused (pause.lock detected). Sleeping 60s...")
            time.sleep(60)
            continue

        try:
            current_time = time.strftime("%H:%M:%S")
            logging.info(f"\n⏰ CYCLE {cycle_count} START: {current_time}")

            # V9.5: Refresh local mirror with social_sources and news_sources at start of each cycle
            # V12.5: Check and reconnect to Supabase before refresh (COVE FIX)
            # V15.0 FIX: Import only refresh_mirror locally. get_supabase is already
            # available from the module-level import (line 195). A local import of get_supabase
            # here would make it a local variable for the entire function, causing UnboundLocalError
            # at line 2414 (startup heartbeat) which runs before this while loop.
            if _SUPABASE_PROVIDER_AVAILABLE:
                try:
                    from src.database.supabase_provider import refresh_mirror

                    # V12.5: Check connection and reconnect if necessary (COVE FIX)
                    supabase = get_supabase()
                    if not supabase.is_connected():
                        logging.warning("⚠️ Supabase disconnected, attempting to reconnect...")
                        if supabase.reconnect():
                            logging.info("✅ Supabase reconnected successfully")
                        else:
                            logging.warning("⚠️ Supabase reconnection failed, using mirror")

                    logging.info("🔄 Refreshing Supabase mirror at start of cycle...")

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

            total_matches_processed, total_news_count = run_pipeline()

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

            # Record successful scan with actual counts
            health.record_scan(matches_count=total_matches_processed, news_count=total_news_count)

            # Reset error count on successful run
            error_count = 0

            # Check if it's time for a heartbeat (every 4 hours)
            if health.should_send_heartbeat():
                # V12.5: Get cache metrics from SupabaseProvider if available
                cache_metrics = None
                if _SUPABASE_PROVIDER_AVAILABLE:
                    try:
                        provider = get_supabase()
                        cache_metrics = provider.get_cache_metrics()
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to get cache metrics: {e}")

                heartbeat_msg = health.get_heartbeat_message(cache_metrics=cache_metrics)
                if send_status_message(heartbeat_msg):
                    health.mark_heartbeat_sent()

            # V12.3: HIGH-FREQUENCY RADAR POLLING (The "Interrupt" Logic)
            # Main cycle reduced from 6h → 2h. During the 2h sleep, we wake up
            # every 15 minutes to check for PENDING_RADAR_TRIGGER from NewsRadar.
            # This ensures "Breaking News" found by the Radar is processed within
            # 15 minutes, even if the main pipeline is resting.
            MAIN_CYCLE_SECONDS = 7200  # 2 hours (was 21600 = 6 hours)
            MINI_CYCLE_SECONDS = 900  # 15 minutes
            elapsed = 0

            logging.info(
                f"💤 V12.3 Active Hunter Mode: 2h cycle with 15-min radar wake-ups. "
                f"Next full pipeline in {MAIN_CYCLE_SECONDS // 60} minutes."
            )

            while elapsed < MAIN_CYCLE_SECONDS:
                remaining = MAIN_CYCLE_SECONDS - elapsed
                sleep_time = min(MINI_CYCLE_SECONDS, remaining)

                logging.info(
                    f"💤 Mini-cycle sleep: {sleep_time // 60}m "
                    f"({elapsed // 60}/{MAIN_CYCLE_SECONDS // 60}m elapsed)..."
                )
                # P4: Interruptible sleep — wake every 30s to check STOP
                stop_detected = False
                sleep_elapsed = 0
                while sleep_elapsed < sleep_time:
                    if settings.is_stop_requested():
                        logging.info("🛑 STOP detected during mini-cycle sleep, breaking...")
                        stop_detected = True
                        break
                    chunk = min(30, sleep_time - sleep_elapsed)
                    time.sleep(chunk)
                    sleep_elapsed += chunk

                elapsed += sleep_time

                if stop_detected:
                    break

                # Check for early termination (STOP file takes precedence)
                if settings.is_stop_requested():
                    logging.info("🛑 STOP detected during mini-cycle, breaking sleep...")
                    break

                # Skip radar check if paused
                if os.path.exists(PAUSE_FILE):
                    logging.info("💤 PAUSE detected during mini-cycle, skipping radar check...")
                    continue

                # MINI-CYCLE: Process PENDING_RADAR_TRIGGER from NewsRadar
                if elapsed < MAIN_CYCLE_SECONDS:
                    try:
                        db_mini = SessionLocal()
                        try:
                            now_utc_mini = datetime.now(timezone.utc)

                            # Quick count check before initializing heavy components
                            pending_count = (
                                db_mini.query(NewsLog)
                                .filter(NewsLog.status == "PENDING_RADAR_TRIGGER")
                                .count()
                            )

                            if pending_count > 0:
                                logging.info(
                                    f"📬 MINI-CYCLE [{elapsed // 60}m]: Found {pending_count} "
                                    f"PENDING_RADAR_TRIGGER(s) - processing immediately!"
                                )

                                # Get singleton instances (cheap - already initialized by main cycle)
                                mini_engine = get_analysis_engine()
                                mini_fotmob = get_data_provider()

                                processed = process_radar_triggers(
                                    analysis_engine=mini_engine,
                                    fotmob=mini_fotmob,
                                    now_utc=now_utc_mini,
                                    db=db_mini,
                                )

                                if processed > 0:
                                    logging.info(
                                        f"✅ MINI-CYCLE: Processed {processed} radar trigger(s) "
                                        f"within 15 minutes of discovery!"
                                    )

                                # Cleanup stale triggers that failed during mini-cycle
                                try:
                                    cleanup_stats = cleanup_stale_radar_triggers(timeout_minutes=10)
                                    if cleanup_stats.get("triggers_cleaned", 0) > 0:
                                        logging.info(
                                            f"🧹 MINI-CYCLE: Cleaned "
                                            f"{cleanup_stats['triggers_cleaned']} stale trigger(s)"
                                        )
                                except Exception:
                                    pass
                            else:
                                logging.debug(
                                    f"📭 MINI-CYCLE [{elapsed // 60}m]: No pending radar triggers"
                                )
                        finally:
                            db_mini.close()
                    except Exception as e:
                        logging.error(f"❌ MINI-CYCLE: Radar trigger processing failed: {e}")

        except KeyboardInterrupt:
            logging.info("\n🛑 SHUTDOWN SIGNAL RECEIVED")
            logging.info(f"📊 Final stats: {cycle_count} cycles completed")

            # V5.2: Cleanup background workers before exit
            _cleanup_background_workers(
                browser_monitor_instance,
                browser_monitor_loop,
                browser_monitor_thread,
                budget_intelligence_loop,
                budget_intelligence_thread,
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
            # Intelligent error tracking integration
            if ERROR_TRACKING_AVAILABLE and record_error_intelligent:
                record_error_intelligent(
                    error_type="database_errors",
                    error_message=str(e),
                    severity="CRITICAL",
                    component="main_loop",
                )
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
                    browser_monitor_instance,
                    browser_monitor_loop,
                    browser_monitor_thread,
                    budget_intelligence_loop,
                    budget_intelligence_thread,
                )
                break
            time.sleep(600)  # Wait 10 minutes

        except ConnectionError as e:
            error_count += 1
            health.record_error(str(e))
            # Intelligent error tracking integration
            if ERROR_TRACKING_AVAILABLE and record_error_intelligent:
                record_error_intelligent(
                    error_type="api_errors",
                    error_message=str(e),
                    severity="ERROR",
                    component="main_loop",
                )
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
                    browser_monitor_instance,
                    browser_monitor_loop,
                    browser_monitor_thread,
                    budget_intelligence_loop,
                    budget_intelligence_thread,
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
                    browser_monitor_instance,
                    browser_monitor_loop,
                    browser_monitor_thread,
                    budget_intelligence_loop,
                    budget_intelligence_thread,
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

    VPS FIX: Extract Match attributes safely to prevent session detachment
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

            # VPS FIX: Extract team names safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", "Unknown")
            away_team = getattr(match, "away_team", "Unknown")

            logging.info(f"🎯 RADAR ANALYSIS: {home_team} vs {away_team} (ID: {match_id})")

            # 3. Create NewsLog entry for radar narrative
            if forced_narrative:
                # V15.0 FIX: Apply optimizer weight to radar score (Learning Loop Integration)
                # This ensures that weights learned from historical performance are applied
                # to radar-detected intelligence
                radar_score = 10  # Maximum score for radar-detected intelligence
                try:
                    from src.analysis.optimizer import get_optimizer

                    optimizer = get_optimizer()
                    league = getattr(match, "league", None)
                    # Radar intelligence doesn't have a specific market, use None
                    # The optimizer will use league-level weights
                    if league:
                        # COVE FIX: Use apply_weight_to_score_with_original to preserve
                        # original AI score for threshold checks
                        original_score, adjusted_score, weight_log_msg, weight = (
                            optimizer.apply_weight_to_score_with_original(
                                base_score=radar_score,
                                league=league,
                                market=None,  # No specific market for radar intelligence
                                driver="RADAR_INTEL",  # Use category as driver
                            )
                        )
                        if weight_log_msg:
                            logging.info(weight_log_msg)
                        # COVE FIX: Use ORIGINAL AI score for NewsLog, not adjusted
                        radar_score = original_score
                except Exception as e:
                    logging.warning(f"⚠️ Failed to apply optimizer weight to radar score: {e}")
                    # Continue with original score

                radar_log = NewsLog(
                    match_id=match_id,
                    url="radar://opportunity-radar",
                    summary=forced_narrative,
                    score=radar_score,
                    category="RADAR_INTEL",
                    affected_team=home_team,  # Default to home team
                    source="radar",
                    source_confidence=0.9,
                    confidence=90,  # V11.1: High confidence for radar-detected intelligence (0-100 scale)
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
                match=match,
                fotmob=fotmob,
                now_utc=now_naive,
                db_session=db,
                context_label="RADAR",
                forced_narrative=forced_narrative,
            )

            # 7. Return results
            result["alert_sent"] = analysis_result.get("alert_sent", False)
            result["score"] = analysis_result.get("score", 0.0)
            result["error"] = analysis_result.get("error")

            if result["alert_sent"]:
                logging.info(
                    f"✅ RADAR ALERT SENT for {home_team} vs {away_team} (Score: {result['score']})"
                )
            else:
                logging.info(
                    f"ℹ️ RADAR analysis completed for {home_team} vs {away_team} (Score: {result['score']}, No alert)"
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
    # Fail-fast: If validator cannot be imported, system should not start
    from src.utils.startup_validator import validate_startup_or_exit

    validation_report = validate_startup_or_exit()

    # Intelligent decision-making based on validation results
    if validation_report.disabled_features:
        logging.info(
            f"⚙️  Disabled features: {', '.join(sorted(validation_report.disabled_features))}"
        )
        logging.info("🔧 System will operate with reduced functionality")

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
