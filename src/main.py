"""
EarlyBird Main Application
==========================
Main entry point for the EarlyBird football betting intelligence system.
"""

import logging
import sys
import os
import time
import argparse
from datetime import datetime, timedelta, timezone
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('earlybird_main.log')
    ]
)
logger = logging.getLogger(__name__)

# CRITICAL: Load .env BEFORE any other imports that read env vars
from dotenv import load_dotenv
load_dotenv()

# Setup path to import modules
sys.path.append(os.getcwd())

# ============================================
# CORE IMPORTS
# ============================================
from src.ingestion.ingest_fixtures import ingest_fixtures
from src.ingestion.data_provider import get_data_provider
from src.ingestion.fotmob_team_mapping import get_fotmob_team_id, get_fotmob_league_id
from src.ingestion.league_manager import (
    get_active_niche_leagues, get_quota_status, is_elite_league, is_tier2_league, 
    ELITE_LEAGUES, TIER_2_LEAGUES,
    should_activate_tier2_fallback, get_tier2_fallback_batch, record_tier2_activation,
    increment_cycle, get_tier2_fallback_status
)
from src.ingestion.weather_provider import get_match_weather
from src.database.models import Match, NewsLog, SessionLocal, init_db
from src.database.migration import check_and_migrate
from src.database.maintenance import emergency_cleanup
from src.processing.news_hunter import run_hunter_for_match
from src.analysis.analyzer import analyze_with_triangulation
from src.analysis.math_engine import MathPredictor, format_math_context
from src.utils.odds_utils import get_market_odds
from src.analysis.settler import settle_pending_bets
from src.analysis.optimizer import get_optimizer, get_dynamic_alert_threshold

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
    from src.utils.url_normalizer import normalize_url, are_articles_similar
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
        init_market_intelligence_db,
        cleanup_old_snapshots
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
    from src.analysis.fatigue_engine import (
        get_enhanced_fatigue_context,
        FatigueDifferential
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
        analyze_match_injuries,
        InjuryDifferential,
        TeamInjuryImpact
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
    from src.analysis.biscotto_engine import (
        get_enhanced_biscotto_analysis,
        BiscottoSeverity
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
    from src.services.twitter_intel_cache import get_twitter_intel_cache
    _TWITTER_INTEL_AVAILABLE = True
    logger.info("✅ Twitter Intel Cache loaded")
except ImportError:
    _TWITTER_INTEL_AVAILABLE = False
    logging.debug("Twitter Intel Cache not available")

# ============================================
# TWEET RELEVANCE FILTER V4.6 (AI Integration)
# ============================================
try:
    from src.services.tweet_relevance_filter import filter_tweets_for_match, resolve_conflict_via_gemini
    _TWEET_FILTER_AVAILABLE = True
except ImportError:
    _TWEET_FILTER_AVAILABLE = False
    logging.debug("Tweet Relevance Filter not available")

# ============================================
# BROWSER MONITOR V5.1 (Always-On Web Monitoring)
# ============================================
try:
    from src.services.browser_monitor import BrowserMonitor, get_browser_monitor
    from src.processing.news_hunter import register_browser_monitor_discovery
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
    from src.utils.parallel_enrichment import enrich_match_parallel, EnrichmentResult
    _PARALLEL_ENRICHMENT_AVAILABLE = True
except ImportError:
    _PARALLEL_ENRICHMENT_AVAILABLE = False
    logging.debug("Parallel Enrichment not available")

# ============================================
# VERIFICATION LAYER V7.0 (Alert Fact-Checking)
# ============================================
try:
    from src.analysis.verification_layer import (
        verify_alert,
        should_verify_alert,
        create_verification_request_from_match,
        VerificationStatus,
        VerificationRequest,
        VerificationResult,
        VERIFICATION_SCORE_THRESHOLD,
    )
    _VERIFICATION_LAYER_AVAILABLE = True
except ImportError:
    _VERIFICATION_LAYER_AVAILABLE = False
    logging.debug("Verification Layer not available")


# ============================================
# TWITTER INTEL HELPER (V4.5 - DRY)
# ============================================
def get_twitter_intel_for_match(match, context_label: str = "") -> dict:
    """
    Get Twitter Intel data for a match from cache.
    
    Centralizes the Twitter Intel enrichment logic to avoid duplication.
    
    Args:
        match: Match object with home_team, away_team, league
        context_label: Optional label for logging (e.g., "TIER2", "RADAR")
        
    Returns:
        Dict with tweets data or None if not available/fresh
    """
    if not _TWITTER_INTEL_AVAILABLE:
        return None
    
    try:
        cache = get_twitter_intel_cache()
        if not cache.is_fresh:
            return None
        
        # Search for relevant tweets about both teams
        relevant_tweets = []
        for team in [match.home_team, match.away_team]:
            tweets = cache.search_intel(
                team, 
                league_key=match.league, 
                topics=['injury', 'lineup', 'squad']
            )
            relevant_tweets.extend(tweets)
        
        if not relevant_tweets:
            return None
        
        # Take top 3 most relevant tweets
        twitter_intel_data = {
            'tweets': [
                {
                    'handle': t.handle,
                    'content': t.content[:150],  # Truncate for display
                    'topics': t.topics
                }
                for t in relevant_tweets[:3]
            ],
            'cache_age_minutes': cache.cache_age_minutes
        }
        
        label = f"[{context_label}] " if context_label else ""
        logging.info(f"   🐦 {label}Twitter Intel: {len(relevant_tweets)} relevant tweets found")
        return twitter_intel_data
        
    except Exception as e:
        logging.debug(f"Twitter Intel enrichment failed: {e}")
        return None


# ============================================
# TWITTER INTEL FOR AI (V4.6 - Analyzer Integration)
# ============================================
def get_twitter_intel_for_ai(
    match,
    official_data: str = "",
    context_label: str = ""
) -> str:
    """
    Get Twitter Intel formatted for AI analysis.
    
    Uses TweetRelevanceFilter to find, score, and format relevant tweets
    for injection into the analyzer prompt.
    
    If conflicts are detected between Twitter and FotMob, calls Gemini
    to verify and resolve the conflict.
    
    Args:
        match: Match object with home_team, away_team, league
        official_data: FotMob data for conflict detection
        context_label: Optional label for logging
        
    Returns:
        Formatted string for AI prompt, or empty string if not available
    """
    if not _TWEET_FILTER_AVAILABLE:
        return ""
    
    try:
        result = filter_tweets_for_match(
            home_team=match.home_team,
            away_team=match.away_team,
            league_key=match.league,
            fotmob_data=official_data
        )
        
        if not result.tweets:
            return ""
        
        label = f"[{context_label}] " if context_label else ""
        logging.info(f"   🐦 {label}Twitter Intel for AI: {len(result.tweets)} tweets selected")
        
        # If conflicts detected, resolve via Gemini
        gemini_resolution = None
        if result.has_conflicts and result.conflict_description:
            logging.warning(f"   ⚠️ Twitter/FotMob conflict detected: {result.conflict_description}")
            
            # Extract Twitter claim from first conflicting tweet
            twitter_claim = result.tweets[0].content if result.tweets else "Unknown"
            
            # Call Gemini to resolve conflict
            gemini_resolution = resolve_conflict_via_gemini(
                conflict_description=result.conflict_description,
                home_team=match.home_team,
                away_team=match.away_team,
                twitter_claim=twitter_claim,
                fotmob_claim=official_data[:500] if official_data else "No FotMob data"
            )
            
            if gemini_resolution:
                status = gemini_resolution.get('verification_status', 'UNKNOWN')
                logging.info(f"   🔍 Gemini conflict resolution: {status}")
                
                # Append Gemini resolution to formatted output
                resolution_text = _format_gemini_resolution(gemini_resolution)
                if resolution_text:
                    return f"{result.formatted_for_ai}\n\n{resolution_text}"
        
        return result.formatted_for_ai
        
    except Exception as e:
        logging.debug(f"Twitter Intel for AI failed: {e}")
        return ""


def _format_gemini_resolution(resolution: dict) -> str:
    """Format Gemini conflict resolution for AI prompt."""
    if not resolution:
        return ""
    
    status = resolution.get('verification_status', 'UNKNOWN')
    confidence = resolution.get('confidence_level', 'LOW')
    additional = resolution.get('additional_context', '')
    
    lines = ["[🔍 GEMINI CONFLICT RESOLUTION]"]
    lines.append(f"Status: {status} (Confidence: {confidence})")
    
    if status == "CONFIRMED":
        lines.append("✅ Twitter claim VERIFIED by Gemini Search")
    elif status == "DENIED":
        lines.append("❌ Twitter claim DENIED - FotMob data is correct")
    elif status == "OUTDATED":
        lines.append("⚠️ Twitter info is OUTDATED - use FotMob")
    else:
        lines.append("❓ UNVERIFIED - treat with caution, reduce confidence")
    
    if additional and additional != "Unknown":
        lines.append(f"Additional context: {additional[:200]}")
    
    return "\n".join(lines)


# ============================================
# TACTICAL INJURY PROFILE HELPER V8.0
# ============================================
def format_tactical_injury_profile(
    team_name: str,
    team_context: dict,
    injury_impact: 'TeamInjuryImpact' = None
) -> str:
    """
    Format injury data with tactical intelligence for AI consumption.
    
    V8.0: Enriches plain injury list with:
    - Player position (Forward, Midfielder, Defender, Goalkeeper)
    - Player role (Starter, Rotation, Backup)
    - Offensive/Defensive impact classification (HIGH, MEDIUM, LOW)
    
    This enables the AI to apply Tactical Veto Rules when market signals
    contradict the tactical reality of missing players.
    
    Args:
        team_name: Team display name
        team_context: FotMob context dict with 'injuries' list
        injury_impact: Optional TeamInjuryImpact from injury_impact_engine
        
    Returns:
        Formatted string like:
        "Team A: 3 missing [OFFENSIVE IMPACT: HIGH] (Forward - Player X - Starter, ...)"
    """
    if not team_context or not team_context.get('injuries'):
        return ""
    
    injuries = team_context.get('injuries', [])
    if not injuries:
        return ""
    
    # Build player details with tactical metadata
    player_details = []
    
    if injury_impact and injury_impact.players:
        # Use detailed player data from injury_impact_engine
        for player in injury_impact.players:
            pos = player.position.value.capitalize() if hasattr(player.position, 'value') else 'Unknown'
            role = player.role.value.capitalize() if hasattr(player.role, 'value') else 'Unknown'
            name = player.name
            
            # Format: "Forward - Player X - Starter"
            player_details.append(f"{pos} - {name} - {role}")
    else:
        # Fallback: just use names from injuries list
        for injury in injuries[:5]:  # Limit to 5 players
            name = injury.get('name', 'Unknown')
            if name and name != 'Unknown':
                player_details.append(name)
    
    if not player_details:
        return f"{team_name}: {len(injuries)} missing"
    
    # Classify offensive/defensive impact levels
    impact_tags = []
    if injury_impact:
        # Offensive impact classification
        if injury_impact.offensive_impact >= 5.0:
            impact_tags.append("OFFENSIVE IMPACT: HIGH")
        elif injury_impact.offensive_impact >= 3.0:
            impact_tags.append("OFFENSIVE IMPACT: MEDIUM")
        
        # Defensive impact classification
        if injury_impact.defensive_impact >= 5.0:
            impact_tags.append("DEFENSIVE IMPACT: HIGH")
        elif injury_impact.defensive_impact >= 3.0:
            impact_tags.append("DEFENSIVE IMPACT: MEDIUM")
    
    # Build final formatted string
    impact_str = f" [{', '.join(impact_tags)}]" if impact_tags else ""
    players_str = ", ".join(player_details[:5])  # Limit to 5 for readability
    
    return f"{team_name}: {len(injuries)} missing{impact_str} ({players_str})"


# ============================================
# PARALLEL ENRICHMENT HELPER V6.0
# ============================================
def run_parallel_enrichment(
    fotmob,
    home_team: str,
    away_team: str,
    match_start_time=None,
    weather_provider=None
) -> dict:
    """
    Run parallel FotMob enrichment and return results in legacy format.
    
    This helper bridges the new parallel enrichment module with the existing
    main.py code, converting EnrichmentResult to the dict format expected
    by downstream code.
    
    Performance: Reduces enrichment time from ~15s to ~3-4s per match.
    
    Args:
        fotmob: FotMob provider instance
        home_team: Validated home team name
        away_team: Validated away team name
        match_start_time: Match start time for weather lookup
        weather_provider: Weather provider function (optional)
        
    Returns:
        Dict with keys: home_context, away_context, home_turnover, away_turnover,
                       referee_info, stadium_coords, home_stats, away_stats,
                       enrichment_time_ms, failed_calls
    """
    if not _PARALLEL_ENRICHMENT_AVAILABLE:
        # Fallback: return empty dict, caller will use sequential approach
        return None
    
    if not fotmob or not home_team or not away_team:
        return None
    
    try:
        result = enrich_match_parallel(
            fotmob=fotmob,
            home_team=home_team,
            away_team=away_team,
            match_start_time=match_start_time,
            weather_provider=weather_provider,
            max_workers=4,
            timeout=45
        )
        
        # Convert EnrichmentResult to legacy dict format
        return {
            'home_context': result.home_context or {},
            'away_context': result.away_context or {},
            'home_turnover': result.home_turnover,
            'away_turnover': result.away_turnover,
            'referee_info': result.referee_info,
            'stadium_coords': result.stadium_coords,
            'home_stats': result.home_stats or {},
            'away_stats': result.away_stats or {},
            'weather_impact': result.weather_impact,
            'tactical': result.tactical or {},
            'enrichment_time_ms': result.enrichment_time_ms,
            'failed_calls': result.failed_calls,
            'successful_calls': result.successful_calls
        }
    except Exception as e:
        logging.warning(f"⚠️ Parallel enrichment failed: {e}, falling back to sequential")
        return None


# ============================================
# FINAL ALERT VERIFIER V1.0 (Pre-Telegram Validation)
# ============================================
try:
    from src.analysis.final_alert_verifier import get_final_verifier, is_final_verifier_available
    from src.analysis.verifier_integration import (
        verify_alert_before_telegram,
        build_alert_data_for_verifier,
        build_context_data_for_verifier
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


# ============================================
# VERIFICATION LAYER HELPER V7.0
# ============================================
def run_verification_check(
    match,
    analysis,
    home_stats: dict = None,
    away_stats: dict = None,
    home_context: dict = None,
    away_context: dict = None,
    context_label: str = ""
) -> tuple:
    """
    Run verification layer check on an alert before sending.
    
    The Verification Layer acts as a fact-checker between preliminary alerts
    and the final send decision. It verifies data with external sources
    (Tavily/Perplexity) to validate betting logic.
    
    Key Problem Solved: Prevents suggesting Over 2.5 Goals for a team with
    7 CRITICAL absences without considering that a decimated squad typically
    produces fewer goals.
    
    Args:
        match: Match database object
        analysis: NewsLog analysis object with score, market, injury data
        home_stats: Optional FotMob stats for home team
        away_stats: Optional FotMob stats for away team
        home_context: Optional FotMob full context for home team (injuries, motivation, fatigue)
        away_context: Optional FotMob full context for away team (injuries, motivation, fatigue)
        context_label: Label for logging (e.g., "TIER1", "TIER2", "RADAR")
        
    Returns:
        Tuple of (should_send, adjusted_score, adjusted_market, verification_result)
        - should_send: True if alert should be sent (CONFIRM or CHANGE_MARKET)
        - adjusted_score: Score after verification adjustments
        - adjusted_market: Market to use (may be changed by verification)
        - verification_result: Full VerificationResult object for logging
        
    Requirements: 7.1, 7.2, 7.3
    """
    if not _VERIFICATION_LAYER_AVAILABLE:
        logging.debug("Verification Layer not available, skipping verification")
        return True, analysis.score, getattr(analysis, 'recommended_market', None), None
    
    # Get preliminary score
    preliminary_score = float(getattr(analysis, 'score', 0))
    
    # Quick check: skip verification if score below threshold
    if not should_verify_alert(preliminary_score):
        logging.debug(f"   ⏭️ Verification skipped (score {preliminary_score} < {VERIFICATION_SCORE_THRESHOLD})")
        return True, preliminary_score, getattr(analysis, 'recommended_market', None), None
    
    label = f"[{context_label}] " if context_label else ""
    logging.info(f"🔍 {label}Starting Verification Layer check...")
    
    try:
        # Create verification request from match and analysis
        # V7.0.1: Pass home_context and away_context for injury data
        request = create_verification_request_from_match(
            match=match,
            analysis=analysis,
            home_stats=home_stats or {},
            away_stats=away_stats or {},
            home_context=home_context or {},
            away_context=away_context or {},
        )
        
        # Run verification
        result = verify_alert(request)
        
        # Log result
        logging.info(f"🔍 {label}Verification complete: {result.status.value}")
        logging.info(f"   Score: {result.original_score} → {result.adjusted_score}")
        if result.inconsistencies:
            logging.info(f"   Inconsistencies: {len(result.inconsistencies)}")
            for inc in result.inconsistencies[:2]:  # Log first 2
                logging.info(f"     - {inc[:80]}...")
        if result.recommended_market:
            logging.info(f"   Recommended market: {result.recommended_market}")
        
        # Determine if alert should be sent
        if result.status == VerificationStatus.REJECT:
            logging.warning(f"❌ {label}Alert REJECTED by Verification Layer: {result.rejection_reason}")
            return False, result.adjusted_score, None, result
        
        elif result.status == VerificationStatus.CHANGE_MARKET:
            logging.info(f"🔄 {label}Market changed: {result.original_market} → {result.recommended_market}")
            return True, result.adjusted_score, result.recommended_market, result
        
        else:  # CONFIRM
            logging.info(f"✅ {label}Alert CONFIRMED by Verification Layer")
            return True, result.adjusted_score, result.original_market, result
        
    except Exception as e:
        logging.error(f"❌ {label}Verification Layer error: {e}")
        # On error, allow alert to proceed with original data
        return True, preliminary_score, getattr(analysis, 'recommended_market', None), None


# Reporter moved to manual /report command in run_telegram_monitor.py
from src.alerting.notifier import send_alert, send_status_message, send_document, send_biscotto_alert
from src.alerting.health_monitor import get_health_monitor
from config.settings import (
    MATCH_LOOKAHEAD_HOURS,
    ANALYSIS_WINDOW_HOURS,
    BISCOTTO_SUSPICIOUS_LOW,
    BISCOTTO_EXTREME_LOW,
    BISCOTTO_SIGNIFICANT_DROP,
    ALERT_THRESHOLD_HIGH,
    ALERT_THRESHOLD_RADAR,
    PAUSE_FILE
)

# ============================================
# INTELLIGENCE-ONLY LEAGUES (No Odds Available)
# ============================================
# These leagues are analyzed purely on News + Stats (FotMob)
# No odds tracking - alerts marked with "NEWS SIGNAL ONLY"

INTELLIGENCE_ONLY_LEAGUES = {
    "soccer_africa_cup_of_nations",     # AFCON - Radar only
    # Add more as needed
}

# ============================================
# INVESTIGATOR MODE: CASE CLOSED COOLDOWN
# ============================================
# Once a verdict is reached, "Close the Case" for 6 hours to save API credits
# Exception: If match starts in < 2 hours, ignore cooldown (Final Check allowed)

CASE_CLOSED_COOLDOWN_HOURS = 6  # Hours to wait before re-investigating
FINAL_CHECK_WINDOW_HOURS = 2   # Hours before kickoff when cooldown is ignored


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
        return True, f"Case Closed - Cooldown ({hours_since_dive:.1f}h since last dive, {hours_to_kickoff:.1f}h to kickoff)"
    
    return False, f"Cooldown expired ({hours_since_dive:.1f}h since last dive)"

# Configure logging - force reconfiguration
from logging.handlers import RotatingFileHandler

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add our handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console handler with immediate flush
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
console_handler.stream.reconfigure(line_buffering=True) if hasattr(console_handler.stream, 'reconfigure') else None

# File handler with rotation (5MB max, 3 backups = 15MB total max)
file_handler = RotatingFileHandler('earlybird.log', maxBytes=5_000_000, backupCount=3)
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
        'is_suspect': False,
        'reason': None,
        'draw_odd': None,
        'drop_pct': 0,
        'severity': 'NONE'
    }
    
    draw_odd = match.current_draw_odd
    opening_draw = match.opening_draw_odd
    
    # V6.1: Validate draw_odd is a positive number
    if not draw_odd or not isinstance(draw_odd, (int, float)) or draw_odd <= 0:
        return result
    
    result['draw_odd'] = draw_odd
    
    # Calculate drop percentage with full validation
    # V6.1: Ensure both values are valid before division
    # V8.3: Initialize drop_pct to avoid UnboundLocalError
    drop_pct = 0
    if (opening_draw and 
        isinstance(opening_draw, (int, float)) and 
        opening_draw > 0 and
        isinstance(draw_odd, (int, float)) and
        draw_odd > 0):
        drop_pct = ((opening_draw - draw_odd) / opening_draw) * 100
        result['drop_pct'] = drop_pct
    
    # Check thresholds
    if draw_odd < BISCOTTO_EXTREME_LOW:
        result['is_suspect'] = True
        result['severity'] = 'EXTREME'
        result['reason'] = f"🍪 EXTREME: Draw @ {draw_odd:.2f} (below {BISCOTTO_EXTREME_LOW})"
    elif draw_odd < BISCOTTO_SUSPICIOUS_LOW:
        result['is_suspect'] = True
        result['severity'] = 'HIGH'
        result['reason'] = f"🍪 SUSPICIOUS: Draw @ {draw_odd:.2f} (below {BISCOTTO_SUSPICIOUS_LOW})"
    elif drop_pct > BISCOTTO_SIGNIFICANT_DROP and opening_draw:
        # V6.1: Extra check that opening_draw exists before using in message
        result['is_suspect'] = True
        result['severity'] = 'MEDIUM'
        result['reason'] = f"🍪 DROPPING: Draw dropped {drop_pct:.1f}% ({opening_draw:.2f} → {draw_odd:.2f})"
    
    return result


def check_odds_drops():
    """
    Check for significant odds drops (market crash detection).
    Send alerts only once per match to prevent spam.
    """
    db = SessionLocal()
    try:
        matches = db.query(Match).filter(
            Match.opening_home_odd.isnot(None),
            Match.current_home_odd.isnot(None),
            Match.odds_alert_sent == False
        ).all()
        
        for match in matches:
            if match.opening_home_odd and match.current_home_odd and match.opening_home_odd > 0:
                drop = ((match.opening_home_odd - match.current_home_odd) / match.opening_home_odd) * 100
                
                if drop > 15:
                    logging.warning(f"📉 MARKET CRASH DETECTED: {match.home_team} vs {match.away_team}")
                    logging.warning(f"   Odds: {match.opening_home_odd:.2f} → {match.current_home_odd:.2f} ({drop:.1f}% drop)")
                    
                    try:
                        send_alert(
                            match_obj=match,
                            news_summary=f"⚠️ MARKET CRASH: Odds dropped {drop:.1f}%. News may already be priced in.",
                            news_url="https://odds-tracker",
                            score=7,
                            league=match.league
                        )
                        match.odds_alert_sent = True
                        db.commit()
                        get_health_monitor().record_alert_sent()
                        logging.info(f"✅ Odds crash alert sent for {match.home_team} vs {match.away_team}")
                    except Exception as e:
                        logging.error(f"Error sending odds alert: {e}")
                        
    except Exception as e:
        logging.error(f"Error checking odds drops: {e}")
    finally:
        db.close()


def check_biscotto_suspects():
    """
    🍪 BISCOTTO SCANNER: Check all upcoming matches for suspicious Draw odds.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        end_window = now + timedelta(hours=MATCH_LOOKAHEAD_HOURS)
        
        matches = db.query(Match).filter(
            Match.start_time >= now,
            Match.start_time <= end_window,
            Match.current_draw_odd.isnot(None),
            Match.biscotto_alert_sent == False
        ).all()
        
        for match in matches:
            biscotto = is_biscotto_suspect(match)
            
            if biscotto['is_suspect']:
                logging.warning(f"🍪 BISCOTTO SUSPECT: {match.home_team} vs {match.away_team}")
                logging.warning(f"   {biscotto['reason']}")
                
                try:
                    send_biscotto_alert(
                        match_obj=match,
                        draw_odd=biscotto['draw_odd'],
                        drop_pct=biscotto['drop_pct'],
                        severity=biscotto['severity'],
                        reasoning=biscotto['reason']
                    )
                    match.biscotto_alert_sent = True
                    db.commit()
                    if _HEALTH_MONITOR_AVAILABLE:
                        get_health_monitor().record_alert_sent()
                    logging.info(f"✅ Biscotto alert sent for {match.home_team} vs {match.away_team}")
                except Exception as e:
                    logging.error(f"Error sending biscotto alert: {e}")
                    
    except Exception as e:
        logging.error(f"Error checking biscotto suspects: {e}")
    finally:
        db.close()


# ============================================
# BETTING STATS ENRICHMENT (V5.0)
# ============================================
# Called when a signal is confirmed (score >= threshold) but
# corner/cards data is missing from FotMob. Uses IntelligenceRouter
# (Gemini or Perplexity) to fetch missing stats for better combo suggestions.

def enrich_betting_stats_if_needed(
    match,
    home_stats: dict,
    away_stats: dict,
    analysis
) -> dict:
    """
    V5.0: Enrich corner/cards stats via IntelligenceRouter when FotMob data is missing.
    
    Called ONLY when:
    1. Signal is confirmed (score >= threshold, about to send alert)
    2. Corner OR cards data is missing/Unknown from FotMob
    
    This enables the AI to suggest corner/cards combos that would
    otherwise be impossible due to missing data.
    
    V5.0: Now uses IntelligenceRouter for automatic Gemini/Perplexity fallback.
    
    Args:
        match: Match database object
        home_stats: FotMob stats for home team (may have Unknown signals)
        away_stats: FotMob stats for away team (may have Unknown signals)
        analysis: NewsLog analysis object (to potentially update combo)
        
    Returns:
        Dict with enriched stats or empty dict if enrichment not needed/failed
    """
    # Check if IntelligenceRouter is available
    if not _INTELLIGENCE_ROUTER_AVAILABLE:
        logging.debug("Intelligence Router not available for betting stats enrichment")
        return {}
    
    # Check if enrichment is needed (corner OR cards data missing)
    home_corners_missing = (
        not home_stats or 
        home_stats.get('corners_signal') in (None, 'Unknown', '')
    )
    away_corners_missing = (
        not away_stats or 
        away_stats.get('corners_signal') in (None, 'Unknown', '')
    )
    home_cards_missing = (
        not home_stats or 
        home_stats.get('cards_signal') in (None, 'Unknown', '')
    )
    away_cards_missing = (
        not away_stats or 
        away_stats.get('cards_signal') in (None, 'Unknown', '')
    )
    
    corners_missing = home_corners_missing or away_corners_missing
    cards_missing = home_cards_missing or away_cards_missing
    
    if not corners_missing and not cards_missing:
        logging.debug("All betting stats available from FotMob, skipping enrichment")
        return {}
    
    # Log what we're fetching
    missing_parts = []
    if corners_missing:
        missing_parts.append("corners")
    if cards_missing:
        missing_parts.append("cards")
    logging.info(f"🎰 [ENRICHMENT] Missing {', '.join(missing_parts)} data - calling Intelligence Router...")
    
    try:
        # Get match date in YYYY-MM-DD format
        match_date = None
        if hasattr(match, 'start_time') and match.start_time:
            match_date = match.start_time.strftime('%Y-%m-%d')
        
        # Get league name
        league = getattr(match, 'league', None) or "Unknown"
        
        # V5.0: Use IntelligenceRouter for automatic Gemini/Perplexity fallback
        router = get_intelligence_router()
        betting_stats = router.get_betting_stats(
            home_team=match.home_team,
            away_team=match.away_team,
            match_date=match_date,
            league=league
        )
        
        if not betting_stats:
            logging.warning("⚠️ [ENRICHMENT] No betting stats returned")
            return {}
        
        # Log what we got
        logging.info(f"✅ [ENRICHMENT] Stats received (via {router.get_active_provider_name()}):")
        logging.info(f"   🚩 Corners: {betting_stats.get('corners_signal')} (avg: {betting_stats.get('corners_total_avg')})")
        logging.info(f"   🟨 Cards: {betting_stats.get('cards_signal')} (avg: {betting_stats.get('cards_total_avg')})")
        logging.info(f"   ⚖️ Referee: {betting_stats.get('referee_name')} ({betting_stats.get('referee_strictness')})")
        logging.info(f"   📊 Confidence: {betting_stats.get('data_confidence')}")
        
        # Check if Gemini suggests a corner/cards bet
        corner_rec = betting_stats.get('recommended_corner_line', 'No bet')
        cards_rec = betting_stats.get('recommended_cards_line', 'No bet')
        confidence = betting_stats.get('data_confidence', 'Low')
        
        # V4.4.1: REFEREE INTELLIGENCE BOOST
        # If referee is strict and cards_rec is "No bet", consider suggesting cards anyway
        referee_strictness = betting_stats.get('referee_strictness', 'Unknown')
        referee_cards_avg = betting_stats.get('referee_cards_avg')
        is_derby = betting_stats.get('is_derby', False)
        match_intensity = betting_stats.get('match_intensity', 'Medium')
        
        # Referee boost logic: strict referee + high intensity = suggest cards
        if cards_rec == 'No bet' and referee_strictness == 'Strict':
            if referee_cards_avg and referee_cards_avg >= 4.0:
                # Strict referee with 4+ cards/game average - suggest Over 3.5 Cards
                cards_rec = "Over 3.5 Cards"
                betting_stats['recommended_cards_line'] = cards_rec
                betting_stats['cards_reasoning'] = f"Arbitro severo ({betting_stats.get('referee_name')}: {referee_cards_avg} cards/game)"
                logging.info(f"   ⚖️ [REFEREE BOOST] Strict referee detected → suggesting {cards_rec}")
            elif is_derby or match_intensity == 'High':
                # Strict referee + derby/high intensity - suggest Over 3.5 Cards
                cards_rec = "Over 3.5 Cards"
                betting_stats['recommended_cards_line'] = cards_rec
                reason = "Derby" if is_derby else "High intensity match"
                betting_stats['cards_reasoning'] = f"Arbitro severo + {reason}"
                logging.info(f"   ⚖️ [REFEREE BOOST] Strict referee + {reason} → suggesting {cards_rec}")
        
        # Upgrade cards line if referee is very strict (5+ cards/game)
        elif cards_rec == 'Over 3.5 Cards' and referee_cards_avg and referee_cards_avg >= 5.0:
            cards_rec = "Over 4.5 Cards"
            betting_stats['recommended_cards_line'] = cards_rec
            betting_stats['cards_reasoning'] = f"Arbitro molto severo ({betting_stats.get('referee_name')}: {referee_cards_avg} cards/game)"
            logging.info(f"   ⚖️ [REFEREE BOOST] Very strict referee → upgrading to {cards_rec}")
        
        # Only consider recommendations if confidence is Medium or High
        if confidence in ('Medium', 'High'):
            # Check if we should update the combo suggestion
            current_combo = getattr(analysis, 'combo_suggestion', None)
            current_market = getattr(analysis, 'recommended_market', None)
            
            # If current combo is None or doesn't include corners/cards, consider adding
            if corner_rec and corner_rec != 'No bet' and 'corner' not in (current_combo or '').lower():
                logging.info(f"   💡 Gemini suggests: {corner_rec}")
                betting_stats['_corner_suggestion'] = corner_rec
            
            if cards_rec and cards_rec != 'No bet' and 'card' not in (current_combo or '').lower():
                logging.info(f"   💡 Gemini suggests: {cards_rec}")
                betting_stats['_cards_suggestion'] = cards_rec
        else:
            logging.info(f"   ⚠️ Low confidence - not suggesting corner/cards bets")
        
        return betting_stats
        
    except Exception as e:
        logging.warning(f"⚠️ [ENRICHMENT] Error fetching betting stats: {e}")
        return {}


def run_pipeline():
    """
    UPGRADED V2: Triangulation Pipeline with FotMob
    Correlates FotMob Official Data + Market Movements + News
    
    QUOTA PROTECTION:
    - Auto-discovers active niche leagues
    - Limits to 5 leagues per run
    
    AUTO-MIGRATION:
    - Checks and updates DB schema at startup
    """
    logging.info("🚀 STARTING EARLYBIRD V6.0 PIPELINE (DeepSeek Intel + FotMob + Triangulation)")
    
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

    # 0. Auto-discover niche leagues (quota protected)
    logging.info("🔍 Auto-discovering active niche leagues...")
    try:
        active_leagues = get_active_niche_leagues(max_leagues=5)
        logging.info(f"🎯 Found {len(active_leagues)} active niche leagues. Processing top 5 to save quota.")
        for league in active_leagues:
            logging.info(f"   📌 {league}")
    except Exception as e:
        logging.warning(f"⚠️ League discovery failed: {e} - using defaults")

    # 1. Ingest Fixtures & Update Odds (uses auto-discovered leagues)
    logging.info("📊 Refreshing fixtures and odds from The-Odds-API...")
    ingest_fixtures(use_auto_discovery=True)
    
    # 2. Check for Odds Drops
    logging.info("💹 Checking for significant odds movements...")
    check_odds_drops()
    
    # 3. BISCOTTO SCANNER
    logging.info("🍪 Scanning for Biscotto suspects (suspicious Draw odds)...")
    check_biscotto_suspects()

    db = SessionLocal()
    try:
        # 3. Select Matches (Next 72 hours) - ELITE LEAGUES ONLY for AI Analysis
        # GHOST MATCH FIX: Use naive datetime for DB comparison (SQLite stores naive)
        now_utc = datetime.now(timezone.utc)
        now_naive = now_utc.replace(tzinfo=None)  # DB stores naive datetimes
        end_window_naive = now_naive + timedelta(hours=ANALYSIS_WINDOW_HOURS)
        
        # Filter to Elite 6 leagues only to save API credits on AI analysis
        # HARD-BLOCK: Only future matches (start_time > now) within the analysis window
        matches = db.query(Match).filter(
            Match.start_time > now_naive,  # STRICT: Future only (Ghost Match Prevention)
            Match.start_time <= end_window_naive,
            Match.league.in_(ELITE_LEAGUES)
        ).all()
        
        logging.info(f"Trovate {len(matches)} partite Elite da analizzare nelle prossime {ANALYSIS_WINDOW_HOURS} ore.")
        
        # V4.3: Tier 2 Fallback tracking
        increment_cycle()  # Incrementa contatore cicli per fallback system
        tier1_alerts_sent = 0
        tier1_high_potential_count = 0
        
        # 4. TRIANGULATION LOOP (INVESTIGATOR MODE)
        for match in matches:
            # --- STEP 0a: HOME/AWAY VALIDATION (V5.1) ---
            # Validate home/away order using FotMob as source of truth
            # This prevents alerts with inverted team order (e.g., "FC Porto vs Santa Clara" 
            # when Santa Clara actually plays at home)
            #
            # IMPORTANT: We use local variables to avoid modifying the DB object
            # The match object stays unchanged, but we use validated names for display/analysis
            home_team_validated = match.home_team
            away_team_validated = match.away_team
            home_away_was_swapped = False
            
            if fotmob:
                try:
                    validated_home, validated_away, was_swapped = fotmob.validate_home_away_order(
                        odds_home_team=match.home_team,
                        odds_away_team=match.away_team
                    )
                    
                    if was_swapped:
                        home_team_validated = validated_home
                        away_team_validated = validated_away
                        home_away_was_swapped = True
                        logging.warning(f"   🔄 HOME/AWAY CORRECTED: {match.home_team} vs {match.away_team} → {validated_home} vs {validated_away}")
                except Exception as e:
                    logging.debug(f"   Home/Away validation skipped: {e}")
            
            match_str = f"{home_team_validated} vs {away_team_validated}"
            logging.info(f"\n{'='*60}")
            logging.info(f"🔎 INVESTIGATING: {match_str} ({match.league})")
            logging.info(f"{'='*60}")
            
            # --- STEP 0: CASE CLOSED COOLDOWN CHECK ---
            case_closed, cooldown_reason = is_case_closed(match, now_naive)
            if case_closed:
                logging.info(f"   🔒 {cooldown_reason}")
                continue
            else:
                logging.info(f"   📂 Case Status: {cooldown_reason}")
            
            # --- STEP 1: FotMob Check (Official Data + Motivation + Fatigue) ---
            official_data = "No official injury data available"
            team_context = ""
            high_potential = False
            team_stats_summary = "No stats available"
            
            # Initialize context variables (used in tier-based gating)
            home_context = {}
            away_context = {}
            home_turnover = None
            away_turnover = None
            home_motivation = {}
            away_motivation = {}
            
            # V4.4: Initialize stats variables (used by enrich_betting_stats_if_needed)
            # These are populated by FotMob if available, otherwise empty dict
            home_stats = {}
            away_stats = {}
            
            # V6.0: Initialize parallel enrichment result
            parallel_result = None
            referee_info = None
            stadium_coords = None
            weather_impact = None
            
            if fotmob:
                logging.info(f"   📊 Checking FotMob for official data...")
                
                # V6.0: Try parallel enrichment first (reduces time from ~15s to ~3-4s)
                parallel_result = run_parallel_enrichment(
                    fotmob=fotmob,
                    home_team=home_team_validated,
                    away_team=away_team_validated,
                    match_start_time=match.start_time,
                    weather_provider=get_match_weather
                )
                
                if parallel_result:
                    # Use parallel results
                    home_context = parallel_result['home_context']
                    away_context = parallel_result['away_context']
                    home_turnover = parallel_result['home_turnover']
                    away_turnover = parallel_result['away_turnover']
                    referee_info = parallel_result['referee_info']
                    stadium_coords = parallel_result['stadium_coords']
                    home_stats = parallel_result['home_stats']
                    away_stats = parallel_result['away_stats']
                    weather_impact = parallel_result['weather_impact']
                    
                    logging.info(f"   ⚡ [PARALLEL] Enrichment completed in {parallel_result['enrichment_time_ms']}ms ({parallel_result['successful_calls']} calls)")
                    if parallel_result['failed_calls']:
                        logging.warning(f"   ⚠️ [PARALLEL] Failed calls: {parallel_result['failed_calls']}")
                else:
                    # Fallback to sequential (original code path)
                    logging.info(f"   🐢 [SEQUENTIAL] Using sequential enrichment...")
                    
                    # Get FULL team context (injuries + motivation + fatigue)
                    # V5.1: Use validated team names to ensure correct home/away assignment
                    home_context = fotmob.get_full_team_context(home_team_validated)
                    away_context = fotmob.get_full_team_context(away_team_validated)
                    
                    # These will be fetched later in sequential mode
                    referee_info = None
                    stadium_coords = None
                    weather_impact = None
                
                # Build official data string (same logic for both paths)
                official_parts = []
                
                # V8.0: Calculate injury differential for tactical profiling
                injury_differential = None
                if _INJURY_IMPACT_AVAILABLE and (home_context.get('injuries') or away_context.get('injuries')):
                    try:
                        injury_differential = analyze_match_injuries(
                            home_team=home_team_validated,
                            away_team=away_team_validated,
                            home_context=home_context,
                            away_context=away_context
                        )
                        logging.debug(f"   🧠 Tactical injury analysis: differential={injury_differential.score_adjustment:+.2f}")
                    except Exception as e:
                        logging.debug(f"   ⚠️ Tactical injury analysis failed: {e}")
                
                # Home team injuries - V8.0: Use tactical profile with position/role/impact
                if home_context.get('injuries'):
                    home_impact_obj = injury_differential.home_impact if injury_differential else None
                    tactical_profile = format_tactical_injury_profile(
                        team_name=home_team_validated,
                        team_context=home_context,
                        injury_impact=home_impact_obj
                    )
                    if tactical_profile:
                        official_parts.append(tactical_profile)
                    else:
                        # Fallback to simple format
                        official_parts.append(f"{home_team_validated}: {len(home_context['injuries'])} missing")
                    if len(home_context['injuries']) >= 2:
                        high_potential = True
                
                # Away team injuries - V8.0: Use tactical profile with position/role/impact
                if away_context.get('injuries'):
                    away_impact_obj = injury_differential.away_impact if injury_differential else None
                    tactical_profile = format_tactical_injury_profile(
                        team_name=away_team_validated,
                        team_context=away_context,
                        injury_impact=away_impact_obj
                    )
                    if tactical_profile:
                        official_parts.append(tactical_profile)
                    else:
                        # Fallback to simple format
                        official_parts.append(f"{away_team_validated}: {len(away_context['injuries'])} missing")
                    if len(away_context['injuries']) >= 2:
                        high_potential = True
                
                if official_parts:
                    official_data = "FotMob confirms: " + " | ".join(official_parts)
                    logging.info(f"   ✅ {official_data}")
                else:
                    official_data = "FotMob: No confirmed absences for either team"
                    logging.info(f"   ✅ FotMob: Clean bill of health")
                
                # LAYER 1 & 2: Build team context string (Motivation + Fatigue)
                context_parts = []
                
                # Home team context
                home_motivation = home_context.get('motivation', {})

                # Safe access: motivation could be a string instead of dict
                if isinstance(home_motivation, dict) and home_motivation.get('zone') != 'Unknown':
                    context_parts.append(f"{home_team_validated}: {home_motivation.get('zone')} (Pos: {home_motivation.get('position')})")
                    # High motivation = high potential
                    if home_motivation.get('zone') in ['Title Race', 'Relegation', 'European Spots']:
                        high_potential = True
                
                # V5.3: Safe access - fatigue could be a string instead of dict (defense-in-depth)
                home_fatigue = home_context.get('fatigue', {})
                if not isinstance(home_fatigue, dict):
                    home_fatigue = {'fatigue_level': str(home_fatigue) if home_fatigue else 'Unknown', 'hours_since_last': None}
                
                home_fatigue_level = home_fatigue.get('fatigue_level')
                if home_fatigue_level and home_fatigue_level != 'Unknown':
                    fatigue_short = home_fatigue_level.split(' - ')[0]
                    context_parts.append(f"Fatigue: {fatigue_short}")
                    # High fatigue = high potential for upset
                    if 'HIGH' in home_fatigue.get('fatigue_level', ''):
                        high_potential = True
                
                # Away team context
                away_motivation = away_context.get('motivation', {})

                # Safe access: motivation could be a string instead of dict
                if isinstance(away_motivation, dict) and away_motivation.get('zone') != 'Unknown':
                    context_parts.append(f"{away_team_validated}: {away_motivation.get('zone')} (Pos: {away_motivation.get('position')})")
                
                # V5.3: Safe access - fatigue could be a string instead of dict (defense-in-depth)
                away_fatigue = away_context.get('fatigue', {})
                if not isinstance(away_fatigue, dict):
                    away_fatigue = {'fatigue_level': str(away_fatigue) if away_fatigue else 'Unknown', 'hours_since_last': None}
                
                away_fatigue_level = away_fatigue.get('fatigue_level')
                if away_fatigue_level and away_fatigue_level != 'Unknown':
                    fatigue_short = away_fatigue_level.split(' - ')[0]
                    context_parts.append(f"Fatigue: {fatigue_short}")
                
                if context_parts:
                    team_context = "TEAM CONTEXT: " + " | ".join(context_parts)
                    logging.info(f"   📈 {team_context}")
                
                # --- STEP 1b: TURNOVER DETECTION (Predicted vs Best XI) ---
                turnover_warning = ""
                
                logging.info(f"   🔄 Checking for lineup turnover...")
                
                # V6.0: Use turnover data from parallel enrichment if available
                # Fallback to sequential if parallel enrichment failed for this specific field
                failed_calls = parallel_result.get('failed_calls', []) if parallel_result else []
                
                if home_turnover is None and (not parallel_result or 'home_turnover' in failed_calls):
                    home_turnover = fotmob.get_turnover_risk(home_team_validated)
                if away_turnover is None and (not parallel_result or 'away_turnover' in failed_calls):
                    away_turnover = fotmob.get_turnover_risk(away_team_validated)
                
                # Check home team turnover
                if home_turnover and home_turnover.get('risk_level') == 'HIGH':
                    # V5.2: Safe access - missing_names may not exist
                    missing_names = home_turnover.get('missing_names') or []
                    missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
                    turnover_count = home_turnover.get('count', len(missing_names))
                    turnover_parts = [
                        f"⚠️ {home_team_validated} MASSIVE TURNOVER: {turnover_count} starters missing ({missing})."
                    ]
                    high_potential = True
                    logging.warning(f"   🔄 HOME TURNOVER [{home_turnover['risk_level']}]: {turnover_count} starters out")
                elif home_turnover and home_turnover.get('risk_level') == 'MEDIUM':
                    turnover_count = home_turnover.get('count', 0)
                    logging.info(f"   🔄 Home turnover: MEDIUM ({turnover_count} starters out)")
                
                # Check away team turnover
                if away_turnover and away_turnover.get('risk_level') == 'HIGH':
                    # V5.2: Safe access - missing_names may not exist
                    missing_names = away_turnover.get('missing_names') or []
                    missing = ', '.join(missing_names[:3]) if missing_names else 'N/A'
                    turnover_count = away_turnover.get('count', len(missing_names))
                    turnover_parts.append(
                        f"⚠️ {away_team_validated} MASSIVE TURNOVER: {turnover_count} starters missing ({missing})."
                    )
                    high_potential = True
                    logging.warning(f"   🔄 AWAY TURNOVER [{away_turnover.get('risk_level')}]: {turnover_count} starters out")
                elif away_turnover and away_turnover.get('risk_level') == 'MEDIUM':
                    turnover_count = away_turnover.get('count', 0)
                    logging.info(f"   🔄 Away turnover: MEDIUM ({turnover_count} starters out)")
                
                # Add turnover warning to official data if detected
                if turnover_parts:
                    turnover_warning = ' '.join(turnover_parts)
                    official_data += f"\n🔄 TURNOVER ALERT: {turnover_warning}"
                
                # --- STEP 1b-bis: FATIGUE ENGINE V2.0 (Advanced Analysis) ---
                fatigue_context_str = ""
                fatigue_differential = None
                
                if _FATIGUE_ENGINE_AVAILABLE:
                    try:
                        logging.info(f"   ⚡ Running Fatigue Engine V2.0...")
                        # V5.1: Use validated team names
                        fatigue_differential, fatigue_context_str = get_enhanced_fatigue_context(
                            home_team=home_team_validated,
                            away_team=away_team_validated,
                            home_context=home_context,
                            away_context=away_context,
                            match_start_time=match.start_time
                        )
                        
                        if fatigue_differential:
                            # Log key findings
                            home_f = fatigue_differential.home_fatigue
                            away_f = fatigue_differential.away_fatigue
                            logging.info(f"   ⚡ FATIGUE: {home_f.team_name} [{home_f.fatigue_level}] vs {away_f.team_name} [{away_f.fatigue_level}]")
                            
                            # Check for significant fatigue differential
                            if fatigue_differential.advantage != "NEUTRAL":
                                logging.info(f"   ⚡ Advantage: {fatigue_differential.advantage}")
                                high_potential = True
                            
                            # Check for late-game risk
                            if home_f.late_game_risk == "HIGH" or away_f.late_game_risk == "HIGH":
                                tired_team = home_f.team_name if home_f.late_game_risk == "HIGH" else away_f.team_name
                                logging.warning(f"   ⏱️ LATE GAME RISK: {tired_team} a rischio goal dopo 75'")
                                high_potential = True
                            
                            # Add to official data
                            if fatigue_context_str:
                                official_data += f"\n{fatigue_context_str}"
                    except Exception as e:
                        logging.warning(f"   ⚠️ Fatigue Engine error: {e}")
                
                # --- STEP 1b-ter: BISCOTTO ENGINE V2.0 (Enhanced Detection) ---
                biscotto_context_str = ""
                biscotto_analysis = None
                
                if _BISCOTTO_ENGINE_AVAILABLE and match.current_draw_odd:
                    try:
                        logging.info(f"   🍪 Running Biscotto Engine V2.0...")
                        biscotto_analysis, biscotto_context_str = get_enhanced_biscotto_analysis(
                            match_obj=match,
                            home_motivation=home_motivation,
                            away_motivation=away_motivation
                        )
                        
                        if biscotto_analysis and biscotto_analysis.is_suspect:
                            logging.warning(f"   🍪 BISCOTTO DETECTED: {biscotto_analysis.severity.value} (conf: {biscotto_analysis.confidence}%)")
                            logging.info(f"   🍪 Factors: {', '.join(biscotto_analysis.factors[:3])}")
                            high_potential = True
                            
                            # V5.0: INTELLIGENCE ROUTER BISCOTTO CONFIRMATION
                            # If severity is MEDIUM (uncertain), ask router to confirm
                            if biscotto_analysis.severity.value == "MEDIUM":
                                try:
                                    router = get_intelligence_router()
                                    if router.is_available():
                                        logging.info(f"   🍪 [ROUTER] Confirming uncertain biscotto signal...")
                                        
                                        # Prepare season context
                                        season_ctx = "End of season" if biscotto_analysis.end_of_season_match else "Mid-season"
                                        
                                        # Get match date
                                        match_date_str = match.start_time.strftime('%Y-%m-%d') if match.start_time else None
                                        
                                        confirmation = router.confirm_biscotto(
                                            home_team=home_team_validated,
                                            away_team=away_team_validated,
                                            match_date=match_date_str,
                                            league=match.league,
                                            draw_odds=biscotto_analysis.current_draw_odd,
                                            implied_prob=biscotto_analysis.implied_probability * 100,
                                            odds_pattern=biscotto_analysis.pattern.value,
                                            season_context=season_ctx,
                                            detected_factors=biscotto_analysis.factors
                                        )
                                        
                                        if confirmation:
                                            if confirmation.get('biscotto_confirmed'):
                                                # Boost confidence and upgrade context
                                                boost = confirmation.get('confidence_boost', 0)
                                                logging.info(f"   🍪 [{router.get_active_provider_name().upper()}] CONFIRMED! Confidence boost: +{boost}")
                                                
                                                # Add findings to context
                                                gemini_biscotto_ctx = f"\n🍪 [AI CONFIRMED] {confirmation.get('mutual_benefit_reason', '')}"
                                                if confirmation.get('h2h_pattern') and confirmation['h2h_pattern'] != "No data":
                                                    gemini_biscotto_ctx += f"\n   H2H: {confirmation['h2h_pattern']}"
                                                if confirmation.get('manager_hints') and confirmation['manager_hints'] != "None found":
                                                    gemini_biscotto_ctx += f"\n   Manager: {confirmation['manager_hints']}"
                                                
                                                biscotto_context_str += gemini_biscotto_ctx
                                            else:
                                                logging.info(f"   🍪 [{router.get_active_provider_name().upper()}] Not confirmed: {confirmation.get('final_recommendation', 'MONITOR')}")
                                except Exception as e:
                                    logging.warning(f"   ⚠️ Biscotto confirmation failed: {e}")
                            
                            # Add to official data
                            if biscotto_context_str:
                                official_data += f"\n{biscotto_context_str}"
                    except Exception as e:
                        logging.warning(f"   ⚠️ Biscotto Engine error: {e}")
                
                # --- STEP 1c: REFEREE ANALYSIS ---
                logging.info(f"   ⚖️ Checking referee info...")
                
                # V6.0: Use referee data from parallel enrichment if available
                # Fallback to sequential if parallel enrichment failed for this specific field
                if referee_info is None and (not parallel_result or 'referee_info' in failed_calls):
                    referee_info = fotmob.get_referee_info(home_team_validated)
                
                if referee_info and referee_info.get('name'):
                    ref_name = referee_info['name']
                    ref_strictness = referee_info.get('strictness', 'Unknown')
                    ref_cpg = referee_info.get('cards_per_game')
                    
                    referee_str = f"⚖️ REFEREE: {ref_name}"
                    if ref_cpg:
                        referee_str += f" (Cards/Game: {ref_cpg}, Strictness: {ref_strictness})"
                    else:
                        referee_str += f" (Strictness: {ref_strictness} - no stats available)"
                    
                    official_data += f"\n{referee_str}"
                    logging.info(f"   {referee_str}")
                else:
                    logging.info(f"   ⚖️ No referee data available")
                
                # --- STEP 1c-bis: WEATHER ANALYSIS ---
                weather_alert = None
                logging.info(f"   🌦️ Checking weather conditions...")
                
                # V6.0: Use weather data from parallel enrichment if available
                # Parallel enrichment already called get_match_weather with stadium_coords
                if parallel_result and weather_impact:
                    # Weather already fetched by parallel enrichment
                    if weather_impact.get('summary'):
                        weather_alert = weather_impact.get('summary', '')
                        official_data += f"\n{weather_alert}"
                        logging.warning(f"   {weather_alert}")
                        
                        if weather_impact.get('status') in ['EXTREME', 'HIGH']:
                            high_potential = True
                    else:
                        logging.info(f"   🌦️ Weather: Good conditions (no impact)")
                elif not parallel_result or 'stadium_coords' in failed_calls or 'weather' in failed_calls:
                    # Fallback: fetch sequentially if no parallel result or if stadium/weather failed
                    if stadium_coords is None and (not parallel_result or 'stadium_coords' in failed_calls):
                        stadium_coords = fotmob.get_stadium_coordinates(home_team_validated)
                    
                    if stadium_coords:
                        lat, lon = stadium_coords
                        weather_impact = get_match_weather(lat, lon, match.start_time)
                        
                        if weather_impact:
                            # Bad weather detected - add to official data
                            weather_alert = weather_impact.get('summary', '')
                            official_data += f"\n{weather_alert}"
                            logging.warning(f"   {weather_alert}")
                            
                            # Weather can be a high potential signal for niche leagues
                            if weather_impact.get('status') in ['EXTREME', 'HIGH']:
                                high_potential = True
                        else:
                            logging.info(f"   🌦️ Weather: Good conditions (no impact)")
                    else:
                        logging.info(f"   🌦️ No stadium coordinates available - skipping weather")
                else:
                    # Parallel result exists but no weather_impact (stadium_coords was None)
                    logging.info(f"   🌦️ No stadium coordinates available - skipping weather")
                
                # --- STEP 1d: TEAM STATS (Goals, Cards, Corners) ---
                logging.info(f"   📈 Fetching team stats for betting markets...")
                
                # V6.0: Use stats from parallel enrichment if available
                # Fallback to sequential if parallel enrichment failed for this specific field
                if not home_stats and (not parallel_result or 'home_stats' in failed_calls):
                    try:
                        # Note: get_team_stats() may not exist in FotMobProvider
                        if hasattr(fotmob, 'get_team_stats'):
                            home_stats = fotmob.get_team_stats(home_team_validated)
                        else:
                            logging.debug("   ℹ️ FotMob.get_team_stats() not available - skipping home_stats")
                    except Exception as e:
                        logging.warning(f"   ⚠️ FotMob home_stats fetch failed: {e}")
                if not away_stats and (not parallel_result or 'away_stats' in failed_calls):
                    try:
                        # Note: get_team_stats() may not exist in FotMobProvider
                        if hasattr(fotmob, 'get_team_stats'):
                            away_stats = fotmob.get_team_stats(away_team_validated)
                        else:
                            logging.debug("   ℹ️ FotMob.get_team_stats() not available - skipping away_stats")
                    except Exception as e:
                        logging.warning(f"   ⚠️ FotMob away_stats fetch failed: {e}")
                
                # Build stats summary for AI
                stats_parts = []
                
                # Home team stats
                if home_stats and not home_stats.get('error'):
                    home_summary = f"{home_team_validated}: {home_stats.get('stats_summary', 'N/A')}"
                    if home_stats.get('goals_signal') and home_stats['goals_signal'] != 'Unknown':
                        home_summary += f" [Goals: {home_stats['goals_signal']}]"
                    if home_stats.get('cards_signal') and home_stats['cards_signal'] != 'Unknown':
                        home_summary += f" [Cards: {home_stats['cards_signal']}]"
                    # V2.6: Include corners signal for Over Corners bets
                    if home_stats.get('corners_signal') and home_stats['corners_signal'] != 'Unknown':
                        corners_src = home_stats.get('corners_source', 'Unknown')
                        corners_val = home_stats.get('avg_corners') or home_stats.get('avg_shots_on_target')
                        if corners_val:
                            home_summary += f" [Corners: {home_stats['corners_signal']} ({corners_val}/game, {corners_src})]"
                        else:
                            home_summary += f" [Corners: {home_stats['corners_signal']}]"
                    stats_parts.append(home_summary)
                
                # Away team stats
                if away_stats and not away_stats.get('error'):
                    away_summary = f"{away_team_validated}: {away_stats.get('stats_summary', 'N/A')}"
                    if away_stats.get('goals_signal') and away_stats['goals_signal'] != 'Unknown':
                        away_summary += f" [Goals: {away_stats['goals_signal']}]"
                    if away_stats.get('cards_signal') and away_stats['cards_signal'] != 'Unknown':
                        away_summary += f" [Cards: {away_stats['cards_signal']}]"
                    # V2.6: Include corners signal for Over Corners bets
                    if away_stats.get('corners_signal') and away_stats['corners_signal'] != 'Unknown':
                        corners_src = away_stats.get('corners_source', 'Unknown')
                        corners_val = away_stats.get('avg_corners') or away_stats.get('avg_shots_on_target')
                        if corners_val:
                            away_summary += f" [Corners: {away_stats['corners_signal']} ({corners_val}/game, {corners_src})]"
                        else:
                            away_summary += f" [Corners: {away_stats['corners_signal']}]"
                    stats_parts.append(away_summary)
                
                team_stats_summary = " | ".join(stats_parts) if stats_parts else "No stats available"
                logging.info(f"   📊 STATS: {team_stats_summary}")
                
                # --- STEP 1e: MATH ENGINE (Poisson Model) ---
                math_context = ""
                math_analysis = None
                
                # Check if we have enough data for Poisson
                home_poisson_ok = (
                    home_stats and 
                    home_stats.get('poisson_reliable') and 
                    home_stats.get('avg_goals_scored') is not None and
                    home_stats.get('avg_goals_conceded') is not None
                )
                away_poisson_ok = (
                    away_stats and 
                    away_stats.get('poisson_reliable') and 
                    away_stats.get('avg_goals_scored') is not None and
                    away_stats.get('avg_goals_conceded') is not None
                )
                
                if home_poisson_ok and away_poisson_ok:
                    logging.info(f"   🧮 Running Poisson Math Model...")
                    try:
                        # V4.3: Pass league_key for league-specific Home Advantage
                        predictor = MathPredictor(league_key=match.league)
                        math_analysis = predictor.analyze_match(
                            home_scored=home_stats['avg_goals_scored'],
                            home_conceded=home_stats['avg_goals_conceded'],
                            away_scored=away_stats['avg_goals_scored'],
                            away_conceded=away_stats['avg_goals_conceded'],
                            home_odd=match.current_home_odd or 0,
                            draw_odd=match.current_draw_odd or 0,
                            away_odd=match.current_away_odd or 0
                        )
                        
                        if math_analysis and 'error' not in math_analysis:
                            math_context = format_math_context(math_analysis, "home")
                            
                            # Log key findings
                            poisson = math_analysis.get('poisson')
                            if poisson:
                                logging.info(f"   📉 POISSON: H {poisson.home_win_prob*100:.0f}% | D {poisson.draw_prob*100:.0f}% | A {poisson.away_win_prob*100:.0f}%")
                                logging.info(f"   📉 Expected Goals: {math_analysis.get('expected_goals')} | Most Likely: {poisson.most_likely_score}")
                            
                            best_edge = math_analysis.get('best_edge')
                            if best_edge and best_edge.has_value:
                                logging.info(f"   💰 VALUE DETECTED: {best_edge.market} +{best_edge.edge:.1f}% edge | Kelly: {best_edge.kelly_stake}%")
                    except Exception as e:
                        logging.warning(f"   ⚠️ Math Engine error: {e}")
                else:
                    reasons = []
                    if not home_poisson_ok:
                        matches = home_stats.get('matches_played', 0) if home_stats else 0
                        reasons.append(f"{home_team_validated}: {matches} matches")
                    if not away_poisson_ok:
                        matches = away_stats.get('matches_played', 0) if away_stats else 0
                        reasons.append(f"{away_team_validated}: {matches} matches")
                    logging.info(f"   ⚠️ Poisson skipped - insufficient data ({', '.join(reasons)})")
            
            # --- STEP 2: Calculate Market Status + Sharp Odds Analysis ---
            market_status = "No significant movement"
            sharp_signal = ""
            odds_drop_pct = 0
            
            # SAFETY: Check if this is an Intelligence-Only league (no odds available)
            is_intel_only = is_intelligence_only_league(match.league)
            is_news_first_mode = match.opening_home_odd is None
            
            if is_intel_only or is_news_first_mode:
                market_status = "⚠️ NO ODDS AVAILABLE - NEWS SIGNAL ONLY"
                logging.info(f"   📰 Intelligence-Only Mode: {match.league} (News + Stats analysis)")
                high_potential = True  # Always search news for intelligence-only leagues
            elif match.opening_home_odd and match.current_home_odd and match.opening_home_odd > 0:
                odds_drop_pct = ((match.opening_home_odd - match.current_home_odd) / match.opening_home_odd) * 100
                
                if odds_drop_pct > 15:
                    market_status = f"📉 MARKET CRASH: Odds dropped {odds_drop_pct:.1f}% ({match.opening_home_odd:.2f} → {match.current_home_odd:.2f})"
                    high_potential = True
                elif odds_drop_pct > 5:
                    market_status = f"↘️ DROPPING: Odds dropped {odds_drop_pct:.1f}% ({match.opening_home_odd:.2f} → {match.current_home_odd:.2f})"
                    high_potential = True
                else:
                    market_status = f"💎 STABLE: Odds {match.opening_home_odd:.2f} → {match.current_home_odd:.2f} ({odds_drop_pct:.1f}% change)"
            
            # LAYER 3: Sharp Odds Signal
            if match.is_sharp_drop:
                sharp_bookie = match.sharp_bookie or 'unknown'
                sharp_signal = f"🎯 SMART MONEY DETECTED ({sharp_bookie}): "
                
                if match.sharp_home_odd and match.avg_home_odd:
                    diff = match.avg_home_odd - match.sharp_home_odd
                    if diff > 0.10:
                        sharp_signal += f"HOME Sharp {match.sharp_home_odd:.2f} vs Avg {match.avg_home_odd:.2f} "
                
                if match.sharp_draw_odd and match.avg_draw_odd:
                    diff = match.avg_draw_odd - match.sharp_draw_odd
                    if diff > 0.10:
                        sharp_signal += f"DRAW Sharp {match.sharp_draw_odd:.2f} vs Avg {match.avg_draw_odd:.2f} "
                
                if match.sharp_away_odd and match.avg_away_odd:
                    diff = match.avg_away_odd - match.sharp_away_odd
                    if diff > 0.10:
                        sharp_signal += f"AWAY Sharp {match.sharp_away_odd:.2f} vs Avg {match.avg_away_odd:.2f}"
                
                high_potential = True
                logging.info(f"   {sharp_signal}")
            
            # --- STEP 2b: ADVANCED MARKET INTELLIGENCE (Steam Move + Reverse Line) ---
            market_intel_signal = ""
            if _MARKET_INTEL_AVAILABLE and not is_intel_only and not is_news_first_mode:
                try:
                    market_intel = analyze_market_intelligence(match)
                    
                    if market_intel.has_signals:
                        market_intel_signal = market_intel.summary
                        logging.info(f"   🔬 {market_intel_signal}")
                        
                        # Steam Move is a HIGH priority signal
                        if market_intel.steam_move and market_intel.steam_move.detected:
                            high_potential = True
                            if market_intel.steam_move.confidence == 'HIGH':
                                logging.warning(f"   🚨 HIGH CONFIDENCE STEAM MOVE DETECTED!")
                        
                        # Reverse Line Movement is a CONTRARIAN signal
                        if market_intel.reverse_line and market_intel.reverse_line.detected:
                            high_potential = True
                            logging.info(f"   🔄 Reverse Line: Sharp money on {market_intel.reverse_line.sharp_side}")
                except Exception as e:
                    logging.debug(f"   Market Intelligence error: {e}")
            
            logging.info(f"   Market Status: {market_status}")
            
            # --- STEP 3: News Hunt (TIER-BASED GATING) ---
            # TIER 1 (Gold List): Search if Drop > 5% OR FotMob Warning
            # TIER 2 (Rotation): Search ONLY if Drop > 15% (Crash) OR FotMob High Risk
            # INTEL-ONLY: Always search (no odds to gate on)
            
            is_tier1 = is_elite_league(match.league)
            is_tier2 = is_tier2_league(match.league)
            
            # Intelligence-Only leagues always get news search
            if is_intel_only or is_news_first_mode:
                should_search_news = True
                tier_label = "INTEL-ONLY"
            elif is_tier1:
                # TIER 1: Standard threshold (5%)
                should_search_news = high_potential or odds_drop_pct > 5
                tier_label = "TIER1"
            elif is_tier2:
                # TIER 2: Strict threshold (15% crash OR high risk from FotMob)
                # V5.1: Added defensive null-checks for context dicts
                fotmob_high_risk = False
                if fotmob:
                    # Safely check home team injuries (context could be empty dict)
                    home_injuries = home_context.get('injuries') if home_context else []
                    away_injuries = away_context.get('injuries') if away_context else []
                    
                    has_home_injury_crisis = isinstance(home_injuries, list) and len(home_injuries) >= 3
                    has_away_injury_crisis = isinstance(away_injuries, list) and len(away_injuries) >= 3
                    has_home_turnover_crisis = home_turnover and home_turnover.get('risk_level') == 'HIGH'
                    has_away_turnover_crisis = away_turnover and away_turnover.get('risk_level') == 'HIGH'
                    
                    fotmob_high_risk = (
                        has_home_injury_crisis or 
                        has_away_injury_crisis or 
                        has_home_turnover_crisis or 
                        has_away_turnover_crisis
                    )
                
                should_search_news = odds_drop_pct > 15 or fotmob_high_risk
                tier_label = "TIER2"
            else:
                # OTHER: Unknown league, skip news search
                should_search_news = False
                tier_label = "OTHER"
            
            # V4.3: Track high_potential per Tier 2 Fallback
            if high_potential:
                tier1_high_potential_count += 1
            
            if not should_search_news:
                logging.info(f"   ⏭️ [{tier_label}] Skipping news search - below threshold (drop: {odds_drop_pct:.1f}%)")
                continue
            
            logging.info(f"   🔍 [{tier_label}] Searching news (drop: {odds_drop_pct:.1f}%, high_potential: {high_potential})...")
            news_items = run_hunter_for_match(match)
            
            if not news_items:
                logging.info(f"   No news found for {match_str}")
                continue
                
            logging.info(f"   Found {len(news_items)} news items.")
            
            # --- STEP 4: BATCH AGGREGATION (V2.6) ---
            # Collect ALL news into a single "Dossier" for ONE AI analysis
            # This saves API costs and prevents duplicate alerts
            
            # V4.5: TIER 0 PRIORITY SORTING
            # Sort news by priority_boost and confidence so TIER 0 sources appear first
            # This gives the AI the most reliable context at the top of the dossier
            def _get_news_priority(item):
                boost = item.get('priority_boost') or 0
                conf_order = {'VERY_HIGH': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
                conf = conf_order.get(item.get('confidence', 'LOW'), 0)
                return (boost, conf)
            
            news_items = sorted(news_items, key=_get_news_priority, reverse=True)
            
            # V4.4: INTELLIGENT DEDUPLICATION
            # Filter out already-processed URLs AND similar content from different sources
            new_items = []
            seen_urls = set()
            seen_titles = []  # For content-based dedup
            
            for item in news_items:
                url = item.get('link', '')
                title = item.get('title', '')
                
                # Skip if no URL
                if not url:
                    continue
                
                # V4.4: Normalize URL (remove tracking params, fragments)
                normalized_url = normalize_url(url) if _SMART_DEDUP_AVAILABLE else url
                
                # Check 1: URL already seen in this batch
                if normalized_url in seen_urls:
                    logging.debug(f"   Skipping duplicate URL (batch): {url[:50]}...")
                    continue
                
                # Check 2: URL already in database
                # Use normalized URL for DB check too
                exists = db.query(NewsLog).filter(
                    NewsLog.match_id == match.id,
                    NewsLog.url == url  # Keep original for exact match
                ).first()
                
                # Also check normalized URL if different
                if not exists and _SMART_DEDUP_AVAILABLE and normalized_url != url:
                    exists = db.query(NewsLog).filter(
                        NewsLog.match_id == match.id,
                        NewsLog.url == normalized_url
                    ).first()
                
                if exists:
                    logging.info(f"   Skipping duplicate URL: {url[:60]}...")
                    continue
                
                # V4.4 Check 3: Content similarity (same news from different sources)
                if _SMART_DEDUP_AVAILABLE and title and seen_titles:
                    is_similar = False
                    for seen_title in seen_titles:
                        if are_articles_similar(title, seen_title):
                            logging.info(f"   🔄 Skipping similar content: {title[:50]}...")
                            is_similar = True
                            break
                    if is_similar:
                        continue
                
                # Item passed all dedup checks
                seen_urls.add(normalized_url)
                if title:
                    seen_titles.append(title)
                new_items.append(item)
            
            if not new_items:
                logging.info(f"   All news already processed for {match_str}")
                continue
            
            # ============================================
            # V5.0: INTELLIGENCE ROUTER NEWS VERIFICATION
            # Verify MEDIUM/LOW confidence news with critical keywords
            # before including in dossier. Uses web search grounding.
            # ============================================
            try:
                router = get_intelligence_router()
                if router.is_available():
                    # V5.1: Use validated team names
                    match_context = f"{home_team_validated} vs {away_team_validated}"
                    if match.start_time:
                        match_context += f" on {match.start_time.strftime('%Y-%m-%d')}"
                    
                    # Verify news for both teams
                    new_items = router.verify_news_batch(
                        news_items=new_items,
                        team_name=home_team_validated,
                        match_context=match_context,
                        max_items=3  # Limit to 3 verifications per match to save quota
                    )
                    
                    # Also verify away team news
                    new_items = router.verify_news_batch(
                        news_items=new_items,
                        team_name=away_team_validated,
                        match_context=match_context,
                        max_items=2  # 2 more for away team
                    )
            except Exception as e:
                logging.warning(f"   ⚠️ News verification failed: {e}")
            
            logging.info(f"   📦 Building DOSSIER with {len(new_items)} new items...")
            
            # Build aggregated dossier from all news
            # Include freshness tags for AI context (News Decay)
            # V4.5: Include Gemini verification status
            # V8.1: Score news items for transparency
            try:
                from src.analysis.news_scorer import score_news_batch, format_batch_score_for_prompt
                news_batch_result = score_news_batch(new_items[:10])
                news_intelligence_summary = format_batch_score_for_prompt(news_batch_result)
                logging.info(f"   📊 News scored: avg={news_batch_result['aggregate']['avg_score']:.1f}/10, high_tier={news_batch_result['aggregate']['high_tier_count']}")
            except Exception as e:
                logging.debug(f"News scoring skipped: {e}")
                news_batch_result = None
                news_intelligence_summary = ""
            
            dossier_parts = []
            all_urls = []
            for idx, item in enumerate(new_items[:10], 1):  # Cap at 10 items to avoid token overflow
                title = item.get('title', 'No title')
                snippet = item.get('snippet', '')
                source = item.get('source', 'Unknown')
                
                # Add freshness tag if available (from News Decay)
                freshness_tag = item.get('freshness_tag', '')
                minutes_old = item.get('minutes_old')
                
                # V4.5: Add Gemini verification indicator
                verification_tag = ''
                if item.get('gemini_verification'):
                    v_status = item['gemini_verification'].get('verification_status', '')
                    if v_status == 'CONFIRMED':
                        verification_tag = '✅ VERIFIED'
                    elif v_status == 'DENIED':
                        verification_tag = '❌ DENIED'
                    elif v_status == 'OUTDATED':
                        verification_tag = '📜 OUTDATED'
                
                # Build dossier line with all tags
                tags = []
                if freshness_tag:
                    age_str = f"{minutes_old}min ago" if minutes_old is not None and minutes_old < 60 else f"{minutes_old//60}h ago" if minutes_old else ""
                    tags.append(f"{freshness_tag} ({age_str})" if age_str else freshness_tag)
                if verification_tag:
                    tags.append(verification_tag)
                
                tag_str = " ".join(tags)
                if tag_str:
                    dossier_parts.append(f"[{idx}] {tag_str} {title} ({source}): {snippet}")
                else:
                    dossier_parts.append(f"[{idx}] {title} ({source}): {snippet}")
                
                # Only add valid URLs (must start with http)
                item_url = item.get('link', '')
                if item_url and isinstance(item_url, str) and item_url.startswith('http'):
                    all_urls.append(item_url)
            
            news_dossier = "\n".join(dossier_parts)
            
            # V8.1: Prepend news intelligence summary for DeepSeek transparency
            if news_intelligence_summary:
                news_dossier = f"{news_intelligence_summary}\n\n{news_dossier}"
            
            # Use first valid URL, or fallback
            primary_url = all_urls[0] if all_urls else None
            
            # --- TELEGRAM SPY INTEL INJECTION ---
            # Fetch Telegram logs for this match and append to news dossier
            try:
                tg_logs = db.query(NewsLog).filter(
                    NewsLog.match_id == match.id,
                    NewsLog.source.in_(['telegram_ocr', 'telegram_channel'])
                ).all()
                
                if tg_logs:
                    # Build spy intel text from Telegram summaries
                    spy_summaries = [log.summary for log in tg_logs if log.summary]
                    if spy_summaries:
                        spy_text = "\n[🕵️ SPY INTEL - Telegram]: " + " | ".join(spy_summaries[:5])  # Cap at 5 to avoid overflow
                        news_dossier = news_dossier + spy_text
                        logging.info(f"   🕵️ Injected {len(spy_summaries)} Telegram intel sources")
            except Exception as e:
                logging.warning(f"   ⚠️ Telegram intel fetch failed: {e}")
            
            # --- V5.0: INTELLIGENCE ROUTER MATCH CONTEXT ENRICHMENT ---
            # Enrich context for high-potential matches before AI analysis
            # This adds fresh intel: recent form, latest news, H2H, weather
            # Note: Only available when Gemini is active (uses Google Search grounding)
            gemini_enrichment_context = ""
            if high_potential:
                try:
                    router = get_intelligence_router()
                    if router.is_available():
                        # Build existing context summary to avoid duplication
                        existing_ctx = f"Official: {official_data[:300]}. Market: {market_status[:200]}"
                        
                        enrichment = router.enrich_match_context(
                            home_team=match.home_team,
                            away_team=match.away_team,
                            match_date=match.start_time.strftime('%Y-%m-%d') if match.start_time else None,
                            league=match.league,
                            existing_context=existing_ctx
                        )
                        
                        if enrichment:
                            # Format enrichment for prompt injection
                            gemini_enrichment_context = router.format_enrichment_for_prompt(enrichment)
                            if gemini_enrichment_context:
                                logging.info(f"   📊 Context enrichment added ({len(gemini_enrichment_context)} chars)")
                except Exception as e:
                    logging.warning(f"   ⚠️ Context enrichment failed: {e}")
            
            # Build enhanced context for AI
            full_market_status = market_status
            if sharp_signal:
                full_market_status += f"\n{sharp_signal}"
            
            # Add Market Intelligence signals (Steam Move, Reverse Line)
            if market_intel_signal:
                full_market_status += f"\n{market_intel_signal}"
            
            full_official_data = official_data
            if team_context:
                full_official_data += f"\n{team_context}"
            
            # Add Math Model context if available
            if math_context:
                full_official_data += f"\n\n{math_context}"
            
            # --- DEEP DIVE: TACTICAL INSIGHTS ---
            tactical_context = "No tactical data available"
            investigation_status = "Standard Analysis"
            
            if fotmob:
                logging.info(f"   🎯 DEEP DIVE: Gathering tactical insights...")
                try:
                    tactical_data = fotmob.get_tactical_insights(match.home_team, match.away_team)
                    if tactical_data and not tactical_data.get('error'):
                        tactical_context = tactical_data.get('tactical_summary', 'No tactical signals')
                        investigation_status = "Full Data Gathered"
                        logging.info(f"   📊 TACTICAL: {tactical_context}")
                except Exception as e:
                    logging.warning(f"   ⚠️ Tactical insights failed: {e}")
            
            # V4.5 Phase 3: Append Gemini enrichment to tactical context
            if gemini_enrichment_context:
                tactical_context = f"{tactical_context}\n\n{gemini_enrichment_context}"
                investigation_status = "Full Data + Gemini Enrichment"
            
            # V4.6: Get Twitter Intel for AI analysis
            twitter_intel_for_ai = get_twitter_intel_for_ai(match, full_official_data, "DEEP_DIVE")
            
            logging.info(f"   🎯 DEEP DIVE ANALYSIS ({len(new_items)} sources)...")
            analysis = analyze_with_triangulation(
                news_snippet=news_dossier,
                market_status=full_market_status,
                official_data=full_official_data,
                snippet_data={
                    'match_id': match.id,
                    'link': primary_url,
                    'team': match.home_team,
                    'home_team': match.home_team,
                    'away_team': match.away_team,
                    'league_id': get_fotmob_league_id(match.league),  # Motivation Engine V4.0
                    'snippet': news_dossier[:500],  # Truncate for DB storage
                    # V4.2: CLV Tracking - pass current odds for odds_taken
                    'current_home_odd': match.current_home_odd,
                    'current_away_odd': match.current_away_odd,
                    'current_draw_odd': match.current_draw_odd,
                    # V5.3: Injury Impact Engine - pass team contexts for balanced assessment
                    'home_context': home_context,
                    'away_context': away_context,
                },
                team_stats=team_stats_summary,
                tactical_context=tactical_context,
                investigation_status=investigation_status,
                twitter_intel=twitter_intel_for_ai
            )
            
            # Mark Deep Dive time (for cooldown)
            match.last_deep_dive_time = datetime.now(timezone.utc)
            
            if not analysis:
                logging.warning("   Analysis returned None")
                continue

            # --- STEP 5: OPTIMIZER WEIGHT APPLICATION (V3.0) ---
            raw_score = analysis.score
            recommended_market = getattr(analysis, 'recommended_market', None)
            primary_driver = getattr(analysis, 'primary_driver', None)
            
            # Apply optimizer weight (includes driver if available)
            optimizer = get_optimizer()
            adjusted_score, optimizer_log = optimizer.apply_weight_to_score(
                raw_score,
                match.league,
                recommended_market,
                primary_driver
            )
            
            if optimizer_log:
                logging.info(f"   {optimizer_log}")
                logging.info(f"   📊 Score: {raw_score} → {adjusted_score} (adjusted)")
            
            current_score = adjusted_score
            
            # --- STEP 6: SCORE-DELTA DEDUPLICATION (V2.6 + V7.3 TEMPORAL RESET) ---
            highest_sent = match.highest_score_sent or 0.0
            
            # V7.3 FIX: Reset highest_sent if 24h passed since last alert (new analysis window)
            if match.last_alert_time:
                # V7.3: Handle timezone-aware vs naive datetime (SQLite stores naive)
                last_alert = match.last_alert_time
                if last_alert.tzinfo is None:
                    last_alert = last_alert.replace(tzinfo=timezone.utc)
                
                time_since_last_alert = datetime.now(timezone.utc) - last_alert
                if time_since_last_alert > timedelta(hours=24):
                    logging.debug(f"   🔄 [DEDUP] Resetting highest_sent (24h passed since last alert)")
                    highest_sent = 0.0
                    match.highest_score_sent = 0.0
            
            score_delta = current_score - highest_sent
            
            # V6.0: Dynamic alert threshold based on recent performance
            # Becomes more conservative during drawdown, more aggressive with good Sortino
            dynamic_threshold, threshold_explanation = get_dynamic_alert_threshold()
            
            # Alert threshold: score >= dynamic_threshold AND (first alert OR score increased by >= 1.5)
            # V3.1: Base 8.2 to reduce alert volume by 60% ("Cream of the Crop" only)
            # V6.0: Now adaptive based on performance metrics
            # V7.3: With temporal reset, old alerts don't block new analysis windows
            should_alert = current_score >= dynamic_threshold and (highest_sent == 0 or score_delta >= 1.5)
            is_update = highest_sent > 0 and should_alert
            
            # Log threshold decision for transparency
            if current_score >= 7.0:
                logging.info(f"   📊 [THRESHOLD] {threshold_explanation}")
            
            if should_alert:
                # --- V4.4: BETTING STATS ENRICHMENT ---
                # If corner/cards data is missing, try to fetch via Gemini
                # This enables better combo suggestions for confirmed signals
                enriched_stats = enrich_betting_stats_if_needed(
                    match=match,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    analysis=analysis
                )
                
                # If Gemini provided corner/cards suggestions and current combo is weak,
                # consider updating the combo_suggestion
                if enriched_stats:
                    current_combo = getattr(analysis, 'combo_suggestion', None)
                    current_market = getattr(analysis, 'recommended_market', None)
                    
                    # Check if we have a corner suggestion from Gemini
                    corner_suggestion = enriched_stats.get('_corner_suggestion')
                    cards_suggestion = enriched_stats.get('_cards_suggestion')
                    
                    # If current combo is None/empty and Gemini has a suggestion, use it
                    if not current_combo or current_combo == 'None':
                        if corner_suggestion and enriched_stats.get('data_confidence') in ('Medium', 'High'):
                            # Build combo with primary market + corner
                            if current_market and current_market != 'NONE':
                                new_combo = f"{current_market} + {corner_suggestion}"
                                analysis.combo_suggestion = new_combo
                                analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('corners_reasoning', '')}"
                                logging.info(f"   🎰 [ENRICHMENT] Updated combo: {new_combo}")
                        elif cards_suggestion and enriched_stats.get('data_confidence') in ('Medium', 'High'):
                            # Build combo with primary market + cards
                            if current_market and current_market != 'NONE':
                                new_combo = f"{current_market} + {cards_suggestion}"
                                analysis.combo_suggestion = new_combo
                                analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('cards_reasoning', '')}"
                                logging.info(f"   🎰 [ENRICHMENT] Updated combo: {new_combo}")
                
                # V4.4.1: Build referee_intel dict for Telegram display
                referee_intel = None
                if enriched_stats and enriched_stats.get('_cards_suggestion'):
                    referee_intel = {
                        'referee_name': enriched_stats.get('referee_name'),
                        'referee_cards_avg': enriched_stats.get('referee_cards_avg'),
                        'referee_strictness': enriched_stats.get('referee_strictness'),
                        'home_cards_avg': enriched_stats.get('home_cards_avg'),
                        'away_cards_avg': enriched_stats.get('away_cards_avg'),
                        'cards_reasoning': enriched_stats.get('cards_reasoning', '')
                    }
                
                # Extract math edge info if available
                # V7.7: Use market-specific edge when recommended market is Double Chance (1X, X2)
                math_edge_info = None
                if math_analysis and math_analysis.get('edges'):
                    edges = math_analysis['edges']
                    recommended_market_lower = (getattr(analysis, 'recommended_market', '') or '').lower().strip()
                    
                    # V7.7: Select edge based on recommended market
                    selected_edge = None
                    if recommended_market_lower == '1x' and '1x' in edges:
                        selected_edge = edges['1x']
                        logging.info(f"   📊 Using 1X edge (P={selected_edge.math_prob:.1f}%) instead of best_edge")
                    elif recommended_market_lower == 'x2' and 'x2' in edges:
                        selected_edge = edges['x2']
                        logging.info(f"   📊 Using X2 edge (P={selected_edge.math_prob:.1f}%) instead of best_edge")
                    else:
                        # Fallback to best_edge for other markets
                        selected_edge = math_analysis.get('best_edge')
                    
                    if selected_edge and selected_edge.has_value and selected_edge.edge > 5:
                        math_edge_info = {
                            'market': selected_edge.market,
                            'edge': selected_edge.edge,
                            'kelly_stake': selected_edge.kelly_stake
                        }
                
                # V4.5: Enrich alert with Twitter Intel from cache (DRY helper)
                twitter_intel_data = get_twitter_intel_for_match(match)
                
                # --- V7.3 FIX: AI CONFIDENCE CHECK ---
                # Reject alerts with low AI confidence unless score is very high
                ai_confidence = getattr(analysis, 'confidence', 0)
                if ai_confidence < 70 and current_score < 9.0:
                    logging.info(f"⏭️ Alert skipped: AI confidence too low ({ai_confidence}%) for score {current_score}")
                    analysis.sent = False
                    db.add(analysis)
                    db.commit()
                    continue
                
                # --- V7.0: VERIFICATION LAYER ---
                # Fact-check the alert before sending
                # Verifies injury impact, form consistency, H2H alignment
                verification_passed, verified_score, verified_market, verification_result = run_verification_check(
                    match=match,
                    analysis=analysis,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_context=home_context,
                    away_context=away_context,
                    context_label="TIER1"
                )
                
                # If verification rejected the alert, skip sending
                if not verification_passed:
                    analysis.sent = False
                    logging.info(f"⏭️ Alert blocked by Verification Layer | Original score: {current_score}")
                    # Still save analysis to DB
                    db.add(analysis)
                    db.commit()
                    continue
                
                # Use verified score and market if available
                final_score = verified_score if verified_score else current_score
                final_market = verified_market if verified_market else getattr(analysis, 'recommended_market', None)
                
                # Build verification info for alert message
                verification_info = None
                if verification_result:
                    verification_info = {
                        'status': verification_result.status.value,
                        'confidence': verification_result.overall_confidence,
                        'reasoning': verification_result.reasoning[:200] if verification_result.reasoning else None,
                        'inconsistencies_count': len(verification_result.inconsistencies),
                    }
                
                # V7.7: Build injury_intel for alert message
                injury_intel = None
                try:
                    from src.analysis.injury_impact_engine import analyze_match_injuries
                    if home_context or away_context:
                        injury_diff = analyze_match_injuries(
                            home_team=home_team_validated,
                            away_team=away_team_validated,
                            home_context=home_context,
                            away_context=away_context
                        )
                        if injury_diff and (injury_diff.home_impact.total_impact_score > 0 or injury_diff.away_impact.total_impact_score > 0):
                            injury_intel = {
                                'home_severity': injury_diff.home_impact.severity,
                                'away_severity': injury_diff.away_impact.severity,
                                'home_missing_starters': injury_diff.home_impact.missing_starters,
                                'away_missing_starters': injury_diff.away_impact.missing_starters,
                                'home_key_players': injury_diff.home_impact.key_players_out,
                                'away_key_players': injury_diff.away_impact.key_players_out,
                                'differential': injury_diff.differential,
                                'favors': 'away' if injury_diff.favors_away else ('home' if injury_diff.favors_home else 'neutral')
                            }
                except Exception as e:
                    logging.debug(f"Could not build injury_intel: {e}")
                
                # V1.0: INTELLIGENT FINAL VERIFICATION - Check before sending to Telegram
                should_send_alert = True
                final_verification_info = None
                
                if _FINAL_VERIFIER_AVAILABLE:
                    try:
                        # Build complete alert data for verifier
                        alert_data = build_alert_data_for_verifier(
                            match=match,
                            analysis=analysis,
                            news_summary=analysis.summary,
                            news_url=analysis.url,
                            score=final_score,
                            recommended_market=final_market,
                            combo_suggestion=getattr(analysis, 'combo_suggestion', None),
                            combo_reasoning=getattr(analysis, 'combo_reasoning', None),
                            reasoning=analysis.summary  # Use summary as reasoning
                        )
                        
                        # NEW: Build news source verification using existing weighting system
                        from src.analysis.verifier_integration import build_news_source_verification
                        news_source_verification = build_news_source_verification(
                            news_url=analysis.url,
                            news_summary=analysis.summary,
                            league_key=match.league
                        )
                        
                        # Build context data with news source verification
                        context_data = build_context_data_for_verifier(
                            verification_info=verification_info,
                            math_edge=math_edge_info,
                            injury_intel=injury_intel,
                            referee_intel=referee_intel,
                            twitter_intel=twitter_intel_data,
                            news_source_verification=news_source_verification  # NEW
                        )
                        
                        # Step 1: Run standard final verification
                        should_send_standard, verification_result = verify_alert_before_telegram(
                            match=match,
                            analysis=analysis,
                            alert_data=alert_data,
                            context_data=context_data
                        )
                        
                        # Step 2: Check if we need intelligent modification handling
                        if not should_send_standard and verification_result.get("final_recommendation") == "MODIFY" and _INTELLIGENT_LOGGER_AVAILABLE:
                            logging.info(f"🧠 [INTELLIGENT LOGGER] Modification suggested, analyzing...")
                            
                            # Get intelligent modification logger
                            intelligent_logger = get_intelligent_modification_logger()
                            
                            # Analyze verifier suggestions and create modification plan
                            modification_plan = intelligent_logger.analyze_verifier_suggestions(
                                match=match,
                                analysis=analysis,
                                verification_result=verification_result,
                                alert_data=alert_data,
                                context_data=context_data
                            )
                            
                            # Step 3: Execute modification plan (hybrid approach)
                            if modification_plan.feedback_decision.value in ["auto_apply", "manual_review"]:
                                step_by_step_loop = get_step_by_step_feedback_loop()
                                
                                should_send_alert, final_verification_info, reprocessed_analysis = step_by_step_loop.process_modification_plan(
                                    match=match,
                                    original_analysis=analysis,
                                    modification_plan=modification_plan,
                                    alert_data=alert_data,
                                    context_data=context_data
                                )
                                
                                if should_send_alert:
                                    # Update analysis with reprocessed data
                                    if reprocessed_analysis:
                                        analysis = reprocessed_analysis
                                        final_score = getattr(reprocessed_analysis, 'score', final_score)
                                        final_market = getattr(reprocessed_analysis, 'recommended_market', final_market)
                                    
                                    logging.info(f"🧠 [INTELLIGENT LOGGER] Alert APPROVED after modifications")
                                else:
                                    logging.info(f"🧠 [INTELLIGENT LOGGER] Alert still REJECTED after modifications")
                            else:
                                # No automatic feedback, use standard result
                                should_send_alert = should_send_standard
                                final_verification_info = verification_result
                                
                        elif should_send_standard:
                            # Standard verification passed
                            should_send_alert = True
                            final_verification_info = verification_result
                            logging.info(f"🔍 [FINAL VERIFIER] Alert CONFIRMED for Telegram")
                        else:
                            # Standard verification rejected without modification suggestion
                            should_send_alert = False
                            final_verification_info = verification_result
                            logging.warning(f"🔍 [FINAL VERIFIER] Alert REJECTED - marking as 'no bet'")
                            
                    except Exception as e:
                        logging.error(f"🔍 [FINAL VERIFIER] Error: {e}")
                        # Fail-safe: proceed with alert if verifier fails
                        should_send_alert = True
                
                # Only send alert if verified (or verifier disabled/failed)
                if should_send_alert:
                    send_alert(
                        match_obj=match,
                        news_summary=analysis.summary,
                        news_url=analysis.url,
                        score=final_score,
                        league=match.league,
                        combo_suggestion=getattr(analysis, 'combo_suggestion', None),
                        combo_reasoning=getattr(analysis, 'combo_reasoning', None),
                        recommended_market=final_market,
                        math_edge=math_edge_info,
                        is_update=is_update,
                        referee_intel=referee_intel,
                        twitter_intel=twitter_intel_data,
                        validated_home_team=home_team_validated,
                        verification_info=final_verification_info or verification_info,  # Use final verification if available
                        injury_intel=injury_intel
                    )
                
                # Update highest_score_sent and database records
                if should_send_alert:
                    # Update highest_score_sent with final (verified) score
                    # V7.3: Also update last_alert_time for temporal reset
                    match.highest_score_sent = final_score
                    match.last_alert_time = datetime.now(timezone.utc)
                    db.commit()
                    
                    analysis.sent = True
                    # Track alert in health monitor
                    get_health_monitor().record_alert_sent()
                    # V4.3: Track per Tier 2 Fallback
                    tier1_alerts_sent += 1
                    alert_type = "UPDATE" if is_update else "NEW"
                    verification_tag = f" [VERIFIED:{verification_result.status.value}]" if verification_result else ""
                    final_tag = " [FINAL:CONFIRMED]" if final_verification_info else ""
                    logging.info(f"✅ ALERT SENT [{alert_type}]{verification_tag}{final_tag} | Score: {final_score} (was {highest_sent}) | {analysis.category}")
                else:
                    # Alert rejected by final verifier - mark as no bet
                    analysis.sent = False
                    analysis.status = "no_bet"
                    if hasattr(analysis, 'final_verifier_result'):
                        # Store verification result for analysis
                        import json
                        analysis.final_verifier_result = json.dumps(final_verification_info)
                    
                    db.commit()
                    logging.warning(f"❌ ALERT REJECTED BY FINAL VERIFIER | Score: {final_score} | {analysis.summary[:100]}...")
            else:
                analysis.sent = False
                if current_score >= 7:
                    logging.info(f"⏭️ Skipping alert (Duplicate/Low Delta) | Score: {current_score} vs Highest: {highest_sent} (delta: {score_delta:.1f})")
                else:
                    logging.info(f"❌ NO BET | Score: {current_score} | {analysis.summary}")
            
            # --- STEP 7: CAPTURE CLOSING ODDS FOR SETTLEMENT ---
            # Map primary_market to the correct odds value for ROI calculation
            if hasattr(analysis, 'recommended_market') and analysis.recommended_market:
                market_lower = analysis.recommended_market.lower()
                closing_odd = 1.90  # Default for complex markets (Over/BTTS/Corners)
                
                if 'home' in market_lower and 'win' in market_lower:
                    closing_odd = match.current_home_odd if match.current_home_odd and match.current_home_odd > 1.0 else 1.90
                elif 'away' in market_lower and 'win' in market_lower:
                    closing_odd = match.current_away_odd if match.current_away_odd and match.current_away_odd > 1.0 else 1.90
                elif 'draw' in market_lower or market_lower == 'x':
                    closing_odd = match.current_draw_odd if match.current_draw_odd and match.current_draw_odd > 1.0 else 1.90
                elif '1x' in market_lower:
                    # Double chance 1X - approximate as average of home and draw
                    h = match.current_home_odd or 2.0
                    d = match.current_draw_odd or 3.0
                    closing_odd = round(1 / ((1/h) + (1/d)), 2) if h > 1 and d > 1 else 1.50
                elif 'x2' in market_lower:
                    # Double chance X2 - approximate as average of draw and away
                    d = match.current_draw_odd or 3.0
                    a = match.current_away_odd or 2.5
                    closing_odd = round(1 / ((1/d) + (1/a)), 2) if d > 1 and a > 1 else 1.50
                
                analysis.closing_odds = closing_odd
                logging.debug(f"📊 Closing odds captured: {closing_odd} for {analysis.recommended_market}")
            
            # Save analysis to DB (regardless of alert status)
            db.add(analysis)
            db.commit()
        
        # ============================================
        # TIER 2 FALLBACK SYSTEM (V4.3)
        # ============================================
        # Dopo il loop Tier 1, verifica se attivare il fallback
        logging.info(f"\n{'='*60}")
        logging.info(f"📊 TIER 1 SUMMARY: {tier1_alerts_sent} alerts, {tier1_high_potential_count} high_potential")
        logging.info(f"{'='*60}")
        
        if should_activate_tier2_fallback(tier1_alerts_sent, tier1_high_potential_count):
            tier2_batch = get_tier2_fallback_batch()
            
            if tier2_batch:
                logging.info(f"🔄 TIER 2 FALLBACK ATTIVATO - Analisi {len(tier2_batch)} leghe: {tier2_batch}")
                
                # Query matches from Tier 2 fallback leagues
                tier2_matches = db.query(Match).filter(
                    Match.start_time > now_naive,
                    Match.start_time <= end_window_naive,
                    Match.league.in_(tier2_batch)
                ).all()
                
                logging.info(f"🔄 Trovate {len(tier2_matches)} partite Tier 2 da analizzare")
                
                tier2_alerts = 0
                tier2_analyzed = 0  # Track how many matches we actually analyzed
                for match in tier2_matches:
                    # V5.1: HOME/AWAY VALIDATION (same as main loop)
                    home_team_validated = match.home_team
                    away_team_validated = match.away_team
                    
                    if fotmob:
                        try:
                            validated_home, validated_away, was_swapped = fotmob.validate_home_away_order(
                                odds_home_team=match.home_team,
                                odds_away_team=match.away_team
                            )
                            if was_swapped:
                                home_team_validated = validated_home
                                away_team_validated = validated_away
                                logging.warning(f"   🔄 [TIER2] HOME/AWAY CORRECTED: {match.home_team} vs {match.away_team} → {validated_home} vs {validated_away}")
                        except Exception as e:
                            logging.debug(f"   [TIER2] Home/Away validation skipped: {e}")
                    
                    match_str = f"{home_team_validated} vs {away_team_validated}"
                    logging.info(f"\n🔄 [TIER2 FALLBACK] {match_str} ({match.league})")
                    
                    # Case Closed check
                    case_closed, cooldown_reason = is_case_closed(match, now_naive)
                    if case_closed:
                        logging.info(f"   🔒 {cooldown_reason}")
                        continue
                    
                    # Simplified analysis for Tier 2 (less aggressive news search)
                    # Only analyze if there's significant odds movement (>10%)
                    odds_drop_pct = 0
                    if match.opening_home_odd and match.current_home_odd and match.opening_home_odd > 0:
                        odds_drop_pct = ((match.opening_home_odd - match.current_home_odd) / match.opening_home_odd) * 100
                    
                    if odds_drop_pct < 10:
                        logging.info(f"   ⏭️ [TIER2] Skipping - odds drop {odds_drop_pct:.1f}% < 10%")
                        continue
                    
                    logging.info(f"   📉 [TIER2] Odds drop {odds_drop_pct:.1f}% - proceeding with analysis")
                    
                    # Run news hunt
                    news_items = run_hunter_for_match(match)
                    if not news_items:
                        logging.info(f"   [TIER2] No news found")
                        continue
                    
                    # V4.5: TIER 0 PRIORITY SORTING (same as main loop)
                    def _get_news_priority_t2(item):
                        boost = item.get('priority_boost') or 0
                        conf_order = {'VERY_HIGH': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
                        conf = conf_order.get(item.get('confidence', 'LOW'), 0)
                        return (boost, conf)
                    
                    news_items = sorted(news_items, key=_get_news_priority_t2, reverse=True)
                    
                    # Build simple dossier
                    dossier_parts = []
                    all_urls = []
                    for idx, item in enumerate(news_items[:5], 1):
                        title = item.get('title', 'No title')
                        snippet = item.get('snippet', '')
                        source = item.get('source', 'Unknown')
                        dossier_parts.append(f"[{idx}] {title} ({source}): {snippet}")
                        item_url = item.get('link', '')
                        if item_url and isinstance(item_url, str) and item_url.startswith('http'):
                            all_urls.append(item_url)
                    
                    news_dossier = "\n".join(dossier_parts)
                    primary_url = all_urls[0] if all_urls else None
                    
                    # Market status
                    market_status = f"📉 TIER2 FALLBACK: Odds dropped {odds_drop_pct:.1f}%"
                    if match.current_home_odd and match.current_draw_odd and match.current_away_odd:
                        market_status += f" (H:{match.current_home_odd:.2f} D:{match.current_draw_odd:.2f} A:{match.current_away_odd:.2f})"
                    
                    # V4.6: Get Twitter Intel for AI analysis
                    official_data_tier2 = "Tier 2 Fallback - Limited data available"
                    twitter_intel_for_ai = get_twitter_intel_for_ai(match, official_data_tier2, "TIER2")
                    
                    # Run AI analysis
                    analysis = analyze_with_triangulation(
                        news_snippet=news_dossier,
                        market_status=market_status,
                        official_data=official_data_tier2,
                        snippet_data={
                            'match_id': match.id,
                            'link': primary_url,
                            'team': match.home_team,
                            'home_team': match.home_team,
                            'away_team': match.away_team,
                            'league_id': get_fotmob_league_id(match.league),
                            'snippet': news_dossier[:500],
                            'current_home_odd': match.current_home_odd,
                            'current_away_odd': match.current_away_odd,
                            'current_draw_odd': match.current_draw_odd,
                            # V5.3: Injury Impact - not available in Tier 2 (no FotMob fetch)
                            'home_context': None,
                            'away_context': None,
                        },
                        team_stats="Tier 2 - Stats not fetched",
                        twitter_intel=twitter_intel_for_ai
                    )
                    
                    if not analysis:
                        continue
                    
                    # Successfully analyzed this match
                    tier2_analyzed += 1
                    
                    # Mark Deep Dive time
                    match.last_deep_dive_time = datetime.now(timezone.utc)
                    
                    # Apply optimizer
                    optimizer = get_optimizer()
                    adjusted_score, _ = optimizer.apply_weight_to_score(
                        analysis.score,
                        match.league,
                        getattr(analysis, 'recommended_market', None),
                        getattr(analysis, 'primary_driver', None)
                    )
                    
                    # Check alert threshold (same as Tier 1)
                    # V6.0: Use dynamic threshold for consistency
                    highest_sent = match.highest_score_sent or 0.0
                    dynamic_threshold, _ = get_dynamic_alert_threshold()
                    should_alert = adjusted_score >= dynamic_threshold and (highest_sent == 0 or adjusted_score - highest_sent >= 1.5)
                    
                    if should_alert:
                        # V4.4: Betting stats enrichment for Tier 2 (stats not fetched from FotMob)
                        # Since Tier 2 doesn't fetch FotMob stats, we always try Gemini enrichment
                        enriched_stats = enrich_betting_stats_if_needed(
                            match=match,
                            home_stats={},  # Empty - Tier 2 doesn't fetch FotMob stats
                            away_stats={},
                            analysis=analysis
                        )
                        
                        # Apply enrichment if available
                        referee_intel = None
                        if enriched_stats:
                            corner_suggestion = enriched_stats.get('_corner_suggestion')
                            cards_suggestion = enriched_stats.get('_cards_suggestion')
                            current_combo = getattr(analysis, 'combo_suggestion', None)
                            current_market = getattr(analysis, 'recommended_market', None)
                            
                            if (not current_combo or current_combo == 'None') and enriched_stats.get('data_confidence') in ('Medium', 'High'):
                                if corner_suggestion and current_market and current_market != 'NONE':
                                    analysis.combo_suggestion = f"{current_market} + {corner_suggestion}"
                                    analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('corners_reasoning', '')}"
                                elif cards_suggestion and current_market and current_market != 'NONE':
                                    analysis.combo_suggestion = f"{current_market} + {cards_suggestion}"
                                    analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('cards_reasoning', '')}"
                            
                            # V4.4.1: Build referee_intel for Telegram display
                            if cards_suggestion:
                                referee_intel = {
                                    'referee_name': enriched_stats.get('referee_name'),
                                    'referee_cards_avg': enriched_stats.get('referee_cards_avg'),
                                    'referee_strictness': enriched_stats.get('referee_strictness'),
                                    'home_cards_avg': enriched_stats.get('home_cards_avg'),
                                    'away_cards_avg': enriched_stats.get('away_cards_avg'),
                                    'cards_reasoning': enriched_stats.get('cards_reasoning', '')
                                }
                        
                        # V4.5: Enrich alert with Twitter Intel from cache (DRY helper)
                        twitter_intel_data = get_twitter_intel_for_match(match, "TIER2")
                        
                        # --- V7.0: VERIFICATION LAYER ---
                        # Fact-check the alert before sending (Tier 2 has no FotMob stats)
                        # Note: Tier 2 doesn't fetch FotMob context, so we pass empty dicts
                        verification_passed, verified_score, verified_market, verification_result = run_verification_check(
                            match=match,
                            analysis=analysis,
                            home_stats={},  # Tier 2 doesn't fetch FotMob stats
                            away_stats={},
                            home_context={},  # Tier 2 doesn't fetch FotMob context
                            away_context={},
                            context_label="TIER2"
                        )
                        
                        # If verification rejected the alert, skip sending
                        if not verification_passed:
                            analysis.sent = False
                            logging.info(f"   ⏭️ [TIER2] Alert blocked by Verification Layer | Original score: {adjusted_score}")
                            db.add(analysis)
                            db.commit()
                            continue
                        
                        # Use verified score and market if available
                        final_score = verified_score if verified_score else adjusted_score
                        final_market = verified_market if verified_market else getattr(analysis, 'recommended_market', None)
                        
                        # Build verification info for alert message
                        verification_info = None
                        if verification_result:
                            verification_info = {
                                'status': verification_result.status.value,
                                'confidence': verification_result.overall_confidence,
                                'reasoning': verification_result.reasoning[:200] if verification_result.reasoning else None,
                                'inconsistencies_count': len(verification_result.inconsistencies),
                            }
                        
                        # V7.7: TIER2 doesn't have FotMob context, so injury_intel is None
                        injury_intel = None
                        
                        send_alert(
                            match_obj=match,
                            news_summary=f"[TIER2 FALLBACK] {analysis.summary}",
                            news_url=analysis.url,
                            score=final_score,
                            league=match.league,
                            combo_suggestion=getattr(analysis, 'combo_suggestion', None),
                            combo_reasoning=getattr(analysis, 'combo_reasoning', None),
                            recommended_market=final_market,
                            is_update=highest_sent > 0,
                            referee_intel=referee_intel,
                            twitter_intel=twitter_intel_data,
                            validated_home_team=home_team_validated,
                            validated_away_team=away_team_validated,
                            verification_info=verification_info,
                            injury_intel=injury_intel
                        )
                        match.highest_score_sent = final_score
                        match.last_alert_time = datetime.now(timezone.utc)
                        analysis.sent = True
                        get_health_monitor().record_alert_sent()
                        tier2_alerts += 1
                        verification_tag = f" [VERIFIED:{verification_result.status.value}]" if verification_result else ""
                        logging.info(f"   ✅ [TIER2] ALERT SENT{verification_tag} | Score: {final_score}")
                    else:
                        analysis.sent = False
                        logging.info(f"   ❌ [TIER2] Below threshold | Score: {adjusted_score}")
                    
                    db.add(analysis)
                    db.commit()
                
                # Record activation ONLY if we actually analyzed at least one match
                if tier2_analyzed > 0:
                    record_tier2_activation()
                    logging.info(f"🔄 TIER 2 FALLBACK COMPLETATO: {tier2_analyzed} analizzati, {tier2_alerts} alerts inviati")
                elif tier2_matches:
                    # Found matches but none passed the odds threshold or all were case-closed
                    logging.info(f"🔄 Tier 2 Fallback: {len(tier2_matches)} match trovati ma nessuno analizzato (attivazione NON registrata)")
                else:
                    logging.info("🔄 Tier 2 Fallback: Nessun match trovato nelle leghe selezionate (attivazione NON registrata)")
            else:
                logging.info("🔄 Tier 2 Fallback: Nessuna lega disponibile")
        else:
            fallback_status = get_tier2_fallback_status()
            logging.info(f"📊 Tier 2 Fallback non attivato (dry_cycles: {fallback_status['consecutive_dry_cycles']}, activations_today: {fallback_status['activations_today']}/{fallback_status['daily_limit']})")
                
    except Exception as e:
        logging.error(f"Pipeline Critical Error: {e}", exc_info=True)
    finally:
        db.close()
        logging.info("🏁 TRIANGULATION CYCLE FINISHED")


def analyze_single_match(match_id: str, forced_narrative: str = None):
    """
    Analyze a single match - used by Opportunity Radar for narrative-triggered analysis.
    
    Args:
        match_id: The match ID to analyze
        forced_narrative: Critical intelligence to inject into AI analysis (from Radar)
    """
    logging.info(f"🎯 SINGLE MATCH ANALYSIS: {match_id}")
    if forced_narrative:
        logging.info(f"   📰 FORCED NARRATIVE INJECTED")
    
    db = SessionLocal()
    try:
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            logging.error(f"Match not found: {match_id}")
            return
        
        # Initialize FotMob
        try:
            fotmob = get_data_provider()
        except Exception as e:
            logging.error(f"FotMob init failed: {e}")
            fotmob = None
        
        # V5.1: HOME/AWAY VALIDATION
        home_team_validated = match.home_team
        away_team_validated = match.away_team
        
        if fotmob:
            try:
                validated_home, validated_away, was_swapped = fotmob.validate_home_away_order(
                    odds_home_team=match.home_team,
                    odds_away_team=match.away_team
                )
                if was_swapped:
                    home_team_validated = validated_home
                    away_team_validated = validated_away
                    logging.warning(f"   🔄 [RADAR] HOME/AWAY CORRECTED: {match.home_team} vs {match.away_team} → {validated_home} vs {validated_away}")
            except Exception as e:
                logging.debug(f"   [RADAR] Home/Away validation skipped: {e}")
        
        match_str = f"{home_team_validated} vs {away_team_validated}"
        logging.info(f"🔎 ANALYZING: {match_str} ({match.league})")
        
        # Collect context (simplified version of run_pipeline logic)
        official_data = "No official data available"
        team_stats_summary = "No stats available"
        market_status = "No market data"
        math_context = ""
        
        # V4.4: Initialize stats variables (used by enrich_betting_stats_if_needed)
        home_stats = {}
        away_stats = {}
        
        if fotmob:
            # Get team context
            # V5.1: Use validated team names
            home_context = fotmob.get_full_team_context(home_team_validated)
            away_context = fotmob.get_full_team_context(away_team_validated)
            
            # Build official data
            official_parts = []
            
            # V8.0: Calculate injury differential for tactical profiling
            injury_differential = None
            if _INJURY_IMPACT_AVAILABLE and (home_context.get('injuries') or away_context.get('injuries')):
                try:
                    injury_differential = analyze_match_injuries(
                        home_team=home_team_validated,
                        away_team=away_team_validated,
                        home_context=home_context,
                        away_context=away_context
                    )
                except Exception as e:
                    logging.debug(f"   ⚠️ [RADAR] Tactical injury analysis failed: {e}")
            
            # Home team injuries - V8.0: Use tactical profile
            if home_context.get('injuries'):
                home_impact_obj = injury_differential.home_impact if injury_differential else None
                tactical_profile = format_tactical_injury_profile(
                    team_name=home_team_validated,
                    team_context=home_context,
                    injury_impact=home_impact_obj
                )
                if tactical_profile:
                    official_parts.append(tactical_profile)
                else:
                    official_parts.append(f"{home_team_validated}: {len(home_context['injuries'])} missing")
            
            # Away team injuries - V8.0: Use tactical profile
            if away_context.get('injuries'):
                away_impact_obj = injury_differential.away_impact if injury_differential else None
                tactical_profile = format_tactical_injury_profile(
                    team_name=away_team_validated,
                    team_context=away_context,
                    injury_impact=away_impact_obj
                )
                if tactical_profile:
                    official_parts.append(tactical_profile)
                else:
                    official_parts.append(f"{away_team_validated}: {len(away_context['injuries'])} missing")
            
            if official_parts:
                official_data = "FotMob confirms: " + " | ".join(official_parts)
            
            # Get team stats
            # V5.1: Use validated team names
            # V6.1: Use Intelligence Router for betting stats (corners/cards signals)
            home_stats = {}
            away_stats = {}
            
            # Try to get betting stats via Intelligence Router (includes corners_signal and cards_signal)
            if _INTELLIGENCE_ROUTER_AVAILABLE:
                try:
                    router = get_intelligence_router()
                    match_date = match.start_time.strftime('%Y-%m-%d') if hasattr(match, 'start_time') and match.start_time else None
                    betting_stats = router.get_betting_stats(
                        home_team=home_team_validated,
                        away_team=away_team_validated,
                        match_date=match_date,
                        league=match.league
                    )
                    if betting_stats:
                        # Extract home/away stats from betting_stats
                        home_stats = betting_stats.get('home_stats', {})
                        away_stats = betting_stats.get('away_stats', {})
                        # Add betting_stats to official_data for AI visibility
                        if betting_stats.get('corners_signal'):
                            official_data += f" [Corners: {betting_stats.get('corners_signal')}]"
                        if betting_stats.get('cards_signal'):
                            official_data += f" [Cards: {betting_stats.get('cards_signal')}]"
                        logging.info(f"   📊 Betting stats via Intelligence Router: corners={betting_stats.get('corners_signal')}, cards={betting_stats.get('cards_signal')}")
                except Exception as e:
                    logging.warning(f"   ⚠️ Intelligence Router betting stats failed: {e}")
            
            # Fallback: Try FotMob stats if available (without corners/cards signals)
            if not home_stats or not away_stats:
                try:
                    # Note: get_team_stats() may not exist in FotMobProvider
                    if hasattr(fotmob, 'get_team_stats'):
                        home_stats = fotmob.get_team_stats(home_team_validated) or {}
                        away_stats = fotmob.get_team_stats(away_team_validated) or {}
                except AttributeError:
                    logging.debug("   ℹ️ FotMob.get_team_stats() not available - using basic data only")
                except Exception as e:
                    logging.warning(f"   ⚠️ FotMob stats fallback failed: {e}")
            
            stats_parts = []
            if home_stats and not home_stats.get('error'):
                stats_parts.append(f"{home_team_validated}: {home_stats.get('stats_summary', 'N/A')}")
            if away_stats and not away_stats.get('error'):
                stats_parts.append(f"{away_team_validated}: {away_stats.get('stats_summary', 'N/A')}")
            team_stats_summary = " | ".join(stats_parts) if stats_parts else "No stats available"
        
        # Market status - handle Intelligence-Only leagues
        is_intel_only = is_intelligence_only_league(match.league)
        
        if is_intel_only or not match.current_home_odd:
            market_status = "⚠️ NO ODDS AVAILABLE - NEWS SIGNAL ONLY"
            logging.info(f"   📰 Intelligence-Only Mode: Analysis based on News + Stats")
        elif match.current_home_odd:
            market_status = f"Odds: H {match.current_home_odd:.2f} | D {match.current_draw_odd:.2f} | A {match.current_away_odd:.2f}"
        
        # INJECT FORCED NARRATIVE (Radar Intelligence)
        if forced_narrative:
            official_data = f"{forced_narrative}\n\n{official_data}"
        
        # --- TELEGRAM SPY INTEL INJECTION (Radar Mode) ---
        radar_news_snippet = forced_narrative or "Radar-triggered analysis - no additional news"
        try:
            tg_logs = db.query(NewsLog).filter(
                NewsLog.match_id == match.id,
                NewsLog.source.in_(['telegram_ocr', 'telegram_channel'])
            ).all()
            
            if tg_logs:
                spy_summaries = [log.summary for log in tg_logs if log.summary]
                if spy_summaries:
                    spy_text = "\n[🕵️ SPY INTEL - Telegram]: " + " | ".join(spy_summaries[:5])
                    radar_news_snippet = radar_news_snippet + spy_text
                    logging.info(f"   🕵️ Injected {len(spy_summaries)} Telegram intel sources (Radar)")
        except Exception as e:
            logging.warning(f"   ⚠️ Telegram intel fetch failed: {e}")
        
        # V4.6: Get Twitter Intel for AI analysis
        twitter_intel_for_ai = get_twitter_intel_for_ai(match, official_data, "RADAR")
        
        # Run AI analysis
        analysis = analyze_with_triangulation(
            news_snippet=radar_news_snippet,
            market_status=market_status,
            official_data=official_data,
            snippet_data={
                'match_id': match.id,
                'link': 'https://earlybird-radar',
                'team': match.home_team,
                'home_team': match.home_team,
                'away_team': match.away_team,
                'league_id': get_fotmob_league_id(match.league),  # Motivation Engine V4.0
                'snippet': forced_narrative[:500] if forced_narrative else '',
                # V4.2: CLV Tracking - pass current odds for odds_taken
                'current_home_odd': match.current_home_odd,
                'current_away_odd': match.current_away_odd,
                'current_draw_odd': match.current_draw_odd,
                # V5.3: Injury Impact Engine - pass team contexts for balanced assessment
                'home_context': home_context,
                'away_context': away_context,
            },
            team_stats=team_stats_summary,
            twitter_intel=twitter_intel_for_ai
        )
        
        if not analysis:
            logging.warning("Analysis returned None")
            return
        
        # Apply optimizer weight
        optimizer = get_optimizer()
        raw_score = analysis.score
        
        # RADAR BOOST: Lower threshold if forced_narrative present (strong qualitative signal)
        alert_threshold = ALERT_THRESHOLD_RADAR if forced_narrative else ALERT_THRESHOLD_HIGH
        
        adjusted_score, optimizer_log = optimizer.apply_weight_to_score(
            raw_score,
            match.league,
            getattr(analysis, 'recommended_market', None),
            getattr(analysis, 'primary_driver', None)
        )
        
        logging.info(f"📊 Score: {raw_score} → {adjusted_score} (threshold: {alert_threshold})")
        
        # Check if should alert
        highest_sent = match.highest_score_sent or 0.0
        should_alert = adjusted_score >= alert_threshold and (highest_sent == 0 or adjusted_score - highest_sent >= 1.5)
        
        if should_alert:
            # V4.4: Betting stats enrichment for Radar/Single match analysis
            enriched_stats = enrich_betting_stats_if_needed(
                match=match,
                home_stats=home_stats if fotmob else {},
                away_stats=away_stats if fotmob else {},
                analysis=analysis
            )
            
            # Apply enrichment if available
            referee_intel = None
            if enriched_stats:
                corner_suggestion = enriched_stats.get('_corner_suggestion')
                cards_suggestion = enriched_stats.get('_cards_suggestion')
                current_combo = getattr(analysis, 'combo_suggestion', None)
                current_market = getattr(analysis, 'recommended_market', None)
                
                if (not current_combo or current_combo == 'None') and enriched_stats.get('data_confidence') in ('Medium', 'High'):
                    if corner_suggestion and current_market and current_market != 'NONE':
                        analysis.combo_suggestion = f"{current_market} + {corner_suggestion}"
                        analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('corners_reasoning', '')}"
                    elif cards_suggestion and current_market and current_market != 'NONE':
                        analysis.combo_suggestion = f"{current_market} + {cards_suggestion}"
                        analysis.combo_reasoning = f"Combo arricchito via Gemini: {enriched_stats.get('cards_reasoning', '')}"
                
                # V4.4.1: Build referee_intel for Telegram display
                if cards_suggestion:
                    referee_intel = {
                        'referee_name': enriched_stats.get('referee_name'),
                        'referee_cards_avg': enriched_stats.get('referee_cards_avg'),
                        'referee_strictness': enriched_stats.get('referee_strictness'),
                        'home_cards_avg': enriched_stats.get('home_cards_avg'),
                        'away_cards_avg': enriched_stats.get('away_cards_avg'),
                        'cards_reasoning': enriched_stats.get('cards_reasoning', '')
                    }
            
            # V4.5: Enrich alert with Twitter Intel from cache (DRY helper)
            twitter_intel_data = get_twitter_intel_for_match(match, "RADAR")
            
            # --- V7.0: VERIFICATION LAYER ---
            # Fact-check the alert before sending
            verification_passed, verified_score, verified_market, verification_result = run_verification_check(
                match=match,
                analysis=analysis,
                home_stats=home_stats if fotmob else {},
                away_stats=away_stats if fotmob else {},
                home_context=home_context if fotmob else {},
                away_context=away_context if fotmob else {},
                context_label="RADAR"
            )
            
            # If verification rejected the alert, skip sending
            if not verification_passed:
                analysis.sent = False
                logging.info(f"⏭️ [RADAR] Alert blocked by Verification Layer | Original score: {adjusted_score}")
                db.add(analysis)
                db.commit()
                return
            
            # Use verified score and market if available
            final_score = verified_score if verified_score else adjusted_score
            final_market = verified_market if verified_market else getattr(analysis, 'recommended_market', None)
            
            # Build verification info for alert message
            verification_info = None
            if verification_result:
                verification_info = {
                    'status': verification_result.status.value,
                    'confidence': verification_result.overall_confidence,
                    'reasoning': verification_result.reasoning[:200] if verification_result.reasoning else None,
                    'inconsistencies_count': len(verification_result.inconsistencies),
                }
            
            # V7.7: Build injury_intel for RADAR alert
            injury_intel = None
            try:
                from src.analysis.injury_impact_engine import analyze_match_injuries
                if fotmob and (home_context or away_context):
                    injury_diff = analyze_match_injuries(
                        home_team=home_team_validated,
                        away_team=away_team_validated,
                        home_context=home_context,
                        away_context=away_context
                    )
                    if injury_diff and (injury_diff.home_impact.total_impact_score > 0 or injury_diff.away_impact.total_impact_score > 0):
                        injury_intel = {
                            'home_severity': injury_diff.home_impact.severity,
                            'away_severity': injury_diff.away_impact.severity,
                            'home_missing_starters': injury_diff.home_impact.missing_starters,
                            'away_missing_starters': injury_diff.away_impact.missing_starters,
                            'home_key_players': injury_diff.home_impact.key_players_out,
                            'away_key_players': injury_diff.away_impact.key_players_out,
                            'differential': injury_diff.differential,
                            'favors': 'away' if injury_diff.favors_away else ('home' if injury_diff.favors_home else 'neutral')
                        }
            except Exception as e:
                logging.debug(f"Could not build injury_intel for RADAR: {e}")
            
            # V8.3 FIX: Capture odds at alert time BEFORE sending alert
            # This ensures we have the actual odds when the alert was sent
            odds_at_alert = None
            if hasattr(analysis, 'recommended_market') and analysis.recommended_market:
                odds_at_alert = get_market_odds(analysis.recommended_market, match)
            
            send_alert(
                match_obj=match,
                news_summary=analysis.summary,
                news_url=analysis.url,
                score=final_score,
                league=match.league,
                combo_suggestion=getattr(analysis, 'combo_suggestion', None),
                combo_reasoning=getattr(analysis, 'combo_reasoning', None),
                recommended_market=final_market,
                is_update=highest_sent > 0,
                referee_intel=referee_intel,
                twitter_intel=twitter_intel_data,
                validated_home_team=home_team_validated,
                validated_away_team=away_team_validated,
                verification_info=verification_info,
                injury_intel=injury_intel
            )
            match.highest_score_sent = final_score
            match.last_alert_time = datetime.now(timezone.utc)
            analysis.sent = True
            
            # V8.3 FIX: Store odds at alert time and alert timestamp
            analysis.odds_at_alert = odds_at_alert
            analysis.alert_sent_at = datetime.now(timezone.utc)
            if odds_at_alert:
                logging.info(f"📊 V8.3: Captured odds at alert time: {odds_at_alert:.2f} for {final_market}")
            else:
                logging.warning(f"⚠️  V8.3: Could not capture odds at alert time for {final_market}")
            get_health_monitor().record_alert_sent()
            verification_tag = f" [VERIFIED:{verification_result.status.value}]" if verification_result else ""
            logging.info(f"✅ RADAR ALERT SENT{verification_tag} | Score: {final_score}")
        else:
            analysis.sent = False
            logging.info(f"⏭️ Below threshold or duplicate | Score: {adjusted_score}")
        
        # Capture closing odds for settlement
        if hasattr(analysis, 'recommended_market') and analysis.recommended_market:
            market_lower = analysis.recommended_market.lower()
            closing_odd = 1.90  # Default for complex markets
            
            if 'home' in market_lower and 'win' in market_lower:
                closing_odd = match.current_home_odd if match.current_home_odd and match.current_home_odd > 1.0 else 1.90
            elif 'away' in market_lower and 'win' in market_lower:
                closing_odd = match.current_away_odd if match.current_away_odd and match.current_away_odd > 1.0 else 1.90
            elif 'draw' in market_lower or market_lower == 'x':
                closing_odd = match.current_draw_odd if match.current_draw_odd and match.current_draw_odd > 1.0 else 1.90
            elif '1x' in market_lower:
                h = match.current_home_odd or 2.0
                d = match.current_draw_odd or 3.0
                closing_odd = round(1 / ((1/h) + (1/d)), 2) if h > 1 and d > 1 else 1.50
            elif 'x2' in market_lower:
                d = match.current_draw_odd or 3.0
                a = match.current_away_odd or 2.5
                closing_odd = round(1 / ((1/d) + (1/a)), 2) if d > 1 and a > 1 else 1.50
            
            analysis.closing_odds = closing_odd
        
        db.add(analysis)
        db.commit()
        
    except Exception as e:
        logging.error(f"Single match analysis error: {e}", exc_info=True)
    finally:
        db.close()


def should_run_settlement() -> bool:
    """
    Check if it's time to run nightly settlement.
    Runs once per day AFTER 04:00 UTC (low activity period).
    
    V4.4: Changed from "exactly at 04:00" to "after 04:00" to handle
    2-hour cycle intervals that might skip the 04:00 window.
    
    Uses a file flag to prevent multiple runs in the same day.
    """
    now = datetime.now(timezone.utc)
    
    # Only run after 04:00 UTC (but before 08:00 to avoid running during peak hours)
    if now.hour < 4 or now.hour >= 8:
        return False
    
    # Check if already ran today
    flag_file = "data/settlement_last_run.txt"
    try:
        if os.path.exists(flag_file):
            with open(flag_file, 'r') as f:
                last_run = f.read().strip()
                if last_run == now.strftime("%Y-%m-%d"):
                    return False  # Already ran today
    except Exception as e:
        logging.error(f"Handled error in should_run_settlement: {e}")
    
    return True


def mark_settlement_done():
    """Mark settlement as completed for today."""
    flag_file = "data/settlement_last_run.txt"
    try:
        with open(flag_file, 'w') as f:
            f.write(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    except Exception as e:
        logging.warning(f"Could not write settlement flag: {e}")


def run_nightly_settlement():
    """
    Run settlement, optimization, and database maintenance.
    Wrapped in safety block - failures don't crash the main bot.
    
    V5.0: Added CLV report generation for edge validation.
    """
    logging.info("🌙 STARTING NIGHTLY SETTLEMENT & OPTIMIZATION...")
    
    try:
        # Step 1: Settle pending bets
        settlement_stats = settle_pending_bets(lookback_hours=48)
        
        if settlement_stats:
            wins = settlement_stats.get('wins', 0)
            losses = settlement_stats.get('losses', 0)
            roi = settlement_stats.get('roi_pct', 0)
            avg_clv = settlement_stats.get('avg_clv', 0)
            clv_positive_rate = settlement_stats.get('clv_positive_rate', 0)
            
            logging.info(f"📊 Settlement: {wins}W / {losses}L | ROI: {roi:.1f}%")
            
            # Step 2: Update optimizer weights
            optimizer = get_optimizer()
            optimizer.recalculate_weights(settlement_stats)
            
            # V5.0: Get optimizer state report
            state_report = optimizer.get_optimizer_state_report()
            frozen_count = len(state_report.get('frozen', []))
            warming_count = len(state_report.get('warming', []))
            active_count = len(state_report.get('active', []))
            
            # V5.0: Generate CLV report
            clv_section = ""
            if avg_clv != 0 or clv_positive_rate > 0:
                clv_emoji = "📈" if avg_clv > 0 else "📉"
                clv_section = (
                    f"\n{clv_emoji} <b>CLV Analysis:</b>\n"
                    f"   Avg CLV: {avg_clv:+.2f}%\n"
                    f"   Positive CLV: {clv_positive_rate:.0f}%\n"
                )
            
            # V5.0: Optimizer state section
            state_section = (
                f"\n🔒 <b>Optimizer V5.0:</b>\n"
                f"   FROZEN: {frozen_count} strategie\n"
                f"   WARMING: {warming_count} strategie\n"
                f"   ACTIVE: {active_count} strategie\n"
            )
            
            # Send summary to Telegram
            summary_msg = (
                "🌙 <b>SETTLEMENT NOTTURNO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Vittorie: {wins}\n"
                f"❌ Sconfitte: {losses}\n"
                f"📈 ROI: {roi:.1f}%\n"
                f"{clv_section}"
                f"{state_section}"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🧠 Pesi strategia aggiornati"
            )
            send_status_message(summary_msg)
        
        # Step 3: Database maintenance (prune old data)
        logging.info("🧹 Avvio manutenzione database...")
        from src.database.maintenance import prune_old_data
        prune_stats = prune_old_data(days=30)
        if prune_stats.get('matches_deleted', 0) > 0:
            logging.info(f"🧹 Pulizia completata: {prune_stats['matches_deleted']} match, {prune_stats['logs_deleted']} log rimossi")
        
        # V5.0: Cleanup old odds snapshots (Market Intelligence)
        if _MARKET_INTEL_AVAILABLE:
            try:
                deleted = cleanup_old_snapshots(days_to_keep=7)
                if deleted > 0:
                    logging.info(f"🧹 Odds snapshots cleanup: {deleted} rimossi")
            except Exception as e:
                logging.debug(f"Odds snapshots cleanup skipped: {e}")
        
        logging.info("☀️ OTTIMIZZAZIONE COMPLETATA. Nuovi pesi strategia applicati.")
        mark_settlement_done()
        
    except Exception as e:
        logging.error(f"⚠️ Settlement failed (will retry tomorrow): {e}")
        # Don't crash - just log and continue





def should_run_radar() -> bool:
    """
    Check if it's time to run the Opportunity Radar.
    Runs every 4 hours (news cycle).
    
    Uses a file flag to track last run time.
    """
    flag_file = "data/radar_last_run.txt"
    try:
        if os.path.exists(flag_file):
            with open(flag_file, 'r') as f:
                last_run_str = f.read().strip()
                last_run = datetime.fromisoformat(last_run_str)
                # Ensure timezone-aware for comparison
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                hours_since = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600
                if hours_since < 4:
                    return False  # Not yet 4 hours
    except Exception as e:
        logging.error(f"Handled error in should_run_radar: {e}")
    
    return True


def mark_radar_done():
    """Mark radar scan as completed."""
    flag_file = "data/radar_last_run.txt"
    try:
        os.makedirs("data", exist_ok=True)
        with open(flag_file, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logging.warning(f"Could not write radar flag: {e}")


# ============================================
# TWITTER INTEL REFRESH (V4.5)
# ============================================

def refresh_twitter_intel_sync():
    """
    Refresh Twitter Intel Cache via DeepSeek/Gemini with Nitter fallback.
    
    Called at the start of each cycle to populate the cache with
    recent tweets from configured insider accounts.
    
    V6.2 FIX: 
    - Attiva Nitter fallback anche per dati parziali (< 50% coverage)
    - Usa helper centralizzato find_account_by_handle
    - Invalida cache se dati incompleti
    
    Wrapped in safety block - failures don't crash the main bot.
    """
    if not _TWITTER_INTEL_AVAILABLE:
        logging.debug("Twitter Intel Cache not available, skipping refresh")
        return
    
    logging.info("🐦 REFRESHING TWITTER INTEL CACHE...")
    
    try:
        # Get cache instance
        cache = get_twitter_intel_cache()
        
        # V6.2 FIX 5: Check cache freshness AND completeness
        # Cache is only "fresh" if it has data for at least 50% of configured accounts
        if cache.is_fresh:
            cache_summary = cache.get_cache_summary()
            from config.twitter_intel_accounts import get_all_twitter_handles
            all_handles_count = len(get_all_twitter_handles())
            cached_accounts = cache_summary.get("total_accounts", 0)
            
            # V6.2: Invalidate cache if less than 50% coverage
            if all_handles_count > 0 and cached_accounts < all_handles_count * 0.5:
                logging.warning(
                    f"⚠️ Twitter Intel cache incomplete: {cached_accounts}/{all_handles_count} accounts "
                    f"({cached_accounts * 100 // all_handles_count}% coverage) - forcing refresh"
                )
            else:
                logging.info(f"🐦 Twitter Intel cache still fresh ({cache.cache_age_minutes}m old), skipping refresh")
                return
        
        # Get all handles from config
        from config.twitter_intel_accounts import get_all_twitter_handles, find_account_by_handle
        all_handles = get_all_twitter_handles()
        
        if not all_handles:
            logging.warning("⚠️ No Twitter handles configured")
            return
        
        logging.info(f"🐦 Extracting tweets from {len(all_handles)} accounts...")
        
        result = None
        source = "unknown"
        missing_handles = []  # V6.2: Track handles not returned by DeepSeek
        
        # Try DeepSeek/Intelligence Router first
        if _INTELLIGENCE_ROUTER_AVAILABLE:
            router = get_intelligence_router()
            if router.is_available():
                result = router.extract_twitter_intel(all_handles, max_posts_per_account=5)
                if result and result.get("accounts"):
                    source = "deepseek"
                    
                    # V6.2 FIX 2: Check if DeepSeek returned data for all handles
                    returned_handles = {
                        a.get("handle", "").lower().replace("@", "") 
                        for a in result.get("accounts", [])
                    }
                    missing_handles = [
                        h for h in all_handles 
                        if h.lower().replace("@", "") not in returned_handles
                    ]
                    
                    # Check metadata for completeness
                    meta = result.get("_meta", {})
                    is_complete = meta.get("is_complete", len(missing_handles) == 0)
                    
                    if missing_handles:
                        logging.warning(
                            f"⚠️ DeepSeek returned partial data: {len(result['accounts'])}/{len(all_handles)} accounts "
                            f"({len(missing_handles)} missing)"
                        )
                    else:
                        logging.info("✅ Twitter Intel extracted via DeepSeek (complete)")
        
        # V6.2 FIX 2: Fallback to Nitter for MISSING handles (not all handles)
        # This is smarter - we only scrape what DeepSeek missed
        if missing_handles and len(missing_handles) > 0:
            logging.info(f"🔄 Trying Nitter fallback for {len(missing_handles)} missing accounts...")
            nitter_result = _try_nitter_fallback(missing_handles)
            
            if nitter_result and nitter_result.get("accounts"):
                # Merge Nitter results with DeepSeek results
                if result and result.get("accounts"):
                    result["accounts"].extend(nitter_result["accounts"])
                    source = "deepseek+nitter"
                    logging.info(f"✅ Merged {len(nitter_result['accounts'])} accounts from Nitter fallback")
                else:
                    result = nitter_result
                    source = "nitter_fallback"
        
        # Original fallback: if DeepSeek completely failed, try Nitter for all
        if not result or not result.get("accounts"):
            logging.info("🔄 DeepSeek failed completely, trying Nitter fallback for all accounts...")
            result = _try_nitter_fallback(all_handles)
            if result and result.get("accounts"):
                source = "nitter_fallback"
                logging.info("✅ Twitter Intel extracted via Nitter fallback")
        
        if not result or not result.get("accounts"):
            logging.warning("⚠️ Twitter Intel extraction failed (both DeepSeek and Nitter)")
            return
        
        # Populate cache manually (since we're not using async)
        from src.services.twitter_intel_cache import CachedTweet, TwitterIntelCacheEntry
        
        accounts_with_data = 0
        total_tweets = 0
        
        for account_data in result.get("accounts", []):
            handle = account_data.get("handle", "")
            tweets = account_data.get("posts", [])
            
            if not handle:
                continue
            
            # V6.2 FIX 4: Use centralized helper instead of duplicated code
            account_info = find_account_by_handle(handle)
            
            # Create cache entry
            entry = TwitterIntelCacheEntry(
                handle=handle,
                account_name=account_info.name if account_info else handle,
                league_focus=account_info.focus if account_info else "unknown",
                tweets=[
                    CachedTweet(
                        handle=handle,
                        date=t.get("date", ""),
                        content=t.get("content", ""),
                        topics=t.get("topics", []),
                        raw_data=t
                    )
                    for t in tweets
                ],
                last_refresh=datetime.now(),
                extraction_success=True
            )
            
            cache._cache[handle.lower()] = entry
            
            if tweets:
                accounts_with_data += 1
                total_tweets += len(tweets)
        
        # Update cache metadata
        cache._last_full_refresh = datetime.now()
        cache._cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # V6.2: Log coverage percentage
        coverage_pct = (len(result.get("accounts", [])) * 100) // len(all_handles) if all_handles else 0
        
        logging.info(
            f"✅ Twitter Intel refresh complete: "
            f"{accounts_with_data} accounts with data, "
            f"{total_tweets} tweets cached, "
            f"{coverage_pct}% coverage (source: {source})"
        )
        
    except Exception as e:
        logging.error(f"⚠️ Twitter Intel refresh failed: {e}", exc_info=True)
        # Don't crash - just log and continue


def _try_nitter_fallback(handles: list) -> dict:
    """
    Try to extract Twitter intel via Nitter fallback scraper.
    
    V6.2 FIX 6: Gestisce race condition con event loop esistenti.
    Usa asyncio.get_event_loop() se disponibile, altrimenti crea nuovo loop.
    
    Args:
        handles: List of Twitter handles
        
    Returns:
        Dict with accounts data or None
    """
    if not handles:
        return None
    
    try:
        import asyncio
        from src.services.nitter_fallback_scraper import scrape_twitter_intel_fallback
        
        # V6.2 FIX 6: Safe event loop handling
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're inside an async context - can't use run_until_complete
            # This shouldn't happen in normal flow, but handle gracefully
            logging.warning("⚠️ [NITTER] Called from async context - using nest_asyncio workaround")
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                logging.warning("⚠️ [NITTER] nest_asyncio not available, skipping fallback")
                return None
        except RuntimeError:
            # No running loop - this is the normal case
            pass
        
        # Create new event loop safely
        try:
            # Try to get existing loop first (might be set but not running)
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No event loop exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                scrape_twitter_intel_fallback(handles, max_posts_per_account=5)
            )
            return result
        finally:
            # V6.2: Don't close the loop if it was pre-existing
            # Only close if we created it
            try:
                if not loop.is_running():
                    loop.close()
            except Exception:
                pass
            
    except ImportError as e:
        logging.debug(f"Nitter fallback not available: {e}")
        return None
    except Exception as e:
        logging.warning(f"⚠️ Nitter fallback failed: {e}")
        return None


def run_opportunity_radar():
    """
    Run the Opportunity Radar scan.
    Wrapped in safety block - failures don't crash the main bot.
    """
    logging.info("🎯 STARTING OPPORTUNITY RADAR SCAN...")
    
    try:
        from src.ingestion.opportunity_radar import run_radar_scan
        
        triggered = run_radar_scan()
        
        if triggered:
            logging.info(f"🎯 Radar triggered {len(triggered)} opportunities")
            
            # Send summary to Telegram
            summary_msg = (
                "🎯 <b>OPPORTUNITY RADAR</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔍 Narratives detected: {len(triggered)}\n"
            )
            for opp in triggered[:5]:  # Max 5 in summary
                summary_msg += f"• {opp['team']}: {opp['type']}\n"
            
            send_status_message(summary_msg)
        else:
            logging.info("🎯 Radar: No new opportunities detected")
        
        mark_radar_done()
        
    except Exception as e:
        logging.error(f"⚠️ Radar scan failed: {e}", exc_info=True)
        # Don't crash - just log and continue


# ============================================
# V5.2: GRACEFUL SHUTDOWN HELPER
# ============================================

def _cleanup_background_workers(
    browser_monitor_instance,
    browser_monitor_loop,
    browser_monitor_thread
) -> None:
    """
    Cleanup all background workers gracefully.
    
    Called on shutdown to ensure:
    1. BrowserMonitor stops, loop exits, thread joins
    
    Args:
        browser_monitor_instance: BrowserMonitor instance or None
        browser_monitor_loop: asyncio event loop or None
        browser_monitor_thread: threading.Thread or None
    """
    import time
    
    logging.info("🔄 [SHUTDOWN] Cleaning up background workers...")
    
    # Stop BrowserMonitor (if running)
    if browser_monitor_instance is not None and _BROWSER_MONITOR_AVAILABLE:
        try:
            if browser_monitor_instance.is_running():
                # Signal stop (thread-safe)
                browser_monitor_instance.request_stop()
                
                # Stop the event loop to unblock run_forever()
                if browser_monitor_loop is not None and browser_monitor_loop.is_running():
                    browser_monitor_loop.call_soon_threadsafe(browser_monitor_loop.stop)
                
                # Wait for thread to finish (with timeout)
                if browser_monitor_thread is not None and browser_monitor_thread.is_alive():
                    browser_monitor_thread.join(timeout=10.0)
                    
                    if browser_monitor_thread.is_alive():
                        logging.warning("⚠️ [SHUTDOWN] BrowserMonitor thread did not stop in time")
                    else:
                        logging.info("✅ [SHUTDOWN] BrowserMonitor stopped gracefully")
                else:
                    logging.info("✅ [SHUTDOWN] BrowserMonitor was not running")
        except Exception as e:
            logging.warning(f"⚠️ [SHUTDOWN] BrowserMonitor cleanup error: {e}")


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
                            logging.warning(f"⚠️ [BROWSER-MONITOR] Playwright cleanup error: {cleanup_err}")
                    try:
                        browser_monitor_loop.close()
                    except Exception:
                        pass
            
            # V5.2: Non-daemon thread for graceful shutdown
            browser_monitor_thread = threading.Thread(
                target=run_browser_monitor_loop,
                name="BrowserMonitorThread",
                daemon=False  # V5.2: Allow graceful cleanup
            )
            browser_monitor_thread.start()
            
            # Give it a moment to start
            import time
            time.sleep(2)
            
            if browser_monitor_instance.is_running():
                browser_monitor_started = True
                logging.info("🌐 [BROWSER-MONITOR] Started - monitoring web sources 24/7")
            else:
                logging.warning("⚠️ [BROWSER-MONITOR] Failed to start")
        except Exception as e:
            logging.warning(f"⚠️ [BROWSER-MONITOR] Startup error: {e}")
    
    # V6.0: Register high-priority callback for event-driven processing
    # When Browser Monitor discovers high-confidence news (INJURY, SUSPENSION, LINEUP),
    # this callback triggers immediate analysis instead of waiting 120 minutes
    if _DISCOVERY_QUEUE_AVAILABLE:
        try:
            def on_high_priority_discovery(league_key: str) -> None:
                """
                Callback invoked when high-priority news is discovered.
                
                For now, just logs the event. Future enhancement: trigger
                immediate mini-pipeline for the affected league.
                """
                logging.info(f"🚨 [HIGH-PRIORITY] News discovered for {league_key} - flagged for priority processing")
                # TODO V6.1: Trigger immediate analysis for this league
                # This would require refactoring run_pipeline() to accept a league filter
            
            queue = get_discovery_queue()
            queue.register_high_priority_callback(
                callback=on_high_priority_discovery,
                threshold=0.85,
                categories=['INJURY', 'SUSPENSION', 'LINEUP']
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
            current_time = time.strftime('%H:%M:%S')
            logging.info(f"\n⏰ CYCLE {cycle_count} START: {current_time}")
            
            # V4.5: Refresh Twitter Intel Cache at start of each cycle
            refresh_twitter_intel_sync()
            
            # Check if it's time for nightly settlement (04:00 UTC)
            if should_run_settlement():
                run_nightly_settlement()
            
            # Check if it's time for Opportunity Radar (every 4 hours)
            if should_run_radar():
                run_opportunity_radar()
            
            run_pipeline()
            
            # V3.7: Run system diagnostics at end of pipeline
            logging.info("🩺 Running system diagnostics...")
            issues = health.run_diagnostics()
            if issues:
                health.report_issues(issues)
            
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
                browser_monitor_instance, 
                browser_monitor_loop, 
                browser_monitor_thread
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
                    browser_monitor_instance, 
                    browser_monitor_loop, 
                    browser_monitor_thread
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
                    browser_monitor_instance, 
                    browser_monitor_loop, 
                    browser_monitor_thread
                )
                break
            time.sleep(300)  # Wait 5 minutes
            
        except Exception as e:
            error_count += 1
            health.record_error(str(e))
            logging.critical(f"💥 UNEXPECTED CRITICAL ERROR in cycle {cycle_count}: {type(e).__name__}: {e}", exc_info=True)
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
                    browser_monitor_thread
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
        """
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test configuration without starting'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current system status'
    )
    
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
        from src.ingestion.ingest_fixtures import ingest_fixtures
        from src.ingestion.data_provider import get_data_provider
        from src.analysis.analyzer import analyze_with_triangulation
        from src.alerting.notifier import send_alert
        logging.info("✅ Import moduli critici: OK")
    except Exception as e:
        logging.error(f"❌ Import moduli: {e}")
        return False
    
    # Test services availability
    services_status = {
        'Intelligence Router': _INTELLIGENCE_ROUTER_AVAILABLE,
        'Market Intelligence': _MARKET_INTEL_AVAILABLE,
        'Fatigue Engine': _FATIGUE_ENGINE_AVAILABLE,
        'Biscotto Engine': _BISCOTTO_ENGINE_AVAILABLE,
        'Twitter Intel': _TWITTER_INTEL_AVAILABLE,
        'Browser Monitor': _BROWSER_MONITOR_AVAILABLE,
        'Verification Layer': _VERIFICATION_LAYER_AVAILABLE
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
            recent_alerts = db.query(NewsLog).filter(
                NewsLog.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24)
            ).count()
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
        ('Intelligence Router', _INTELLIGENCE_ROUTER_AVAILABLE),
        ('Browser Monitor', _BROWSER_MONITOR_AVAILABLE),
        ('Verification Layer', _VERIFICATION_LAYER_AVAILABLE)
    ]
    
    for name, available in services:
        status = "✅" if available else "❌"
        logging.info(f"{status} {name}: {'Active' if available else 'Inactive'}")


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
    finally:
        # V5.2: Fallback cleanup using singletons (in case run_continuous crashed early)
        # The main cleanup happens inside run_continuous() with access to local variables
        try:
            if _BROWSER_MONITOR_AVAILABLE:
                monitor = get_browser_monitor()
                if monitor.is_running():
                    monitor.request_stop()
                    logging.info("✅ [SHUTDOWN-FALLBACK] BrowserMonitor stop requested")
        except Exception as e:
            logging.debug(f"BrowserMonitor fallback cleanup: {e}")
