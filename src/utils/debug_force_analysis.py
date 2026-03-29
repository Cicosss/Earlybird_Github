#!/usr/bin/env python3
"""
Pipeline Funnel Diagnostic - "Force Ignition" (V11.0)

This script bypasses the Discovery layer (NewsRadar/Scheduler) and manually triggers
a match analysis to verify the "Last Mile" dispatch mechanism (AI -> Notifier).

Usage:
    python src/utils/debug_force_analysis.py
    or
    make run-debug

Author: Diagnostic Tool
Date: 2026-03-22
"""

import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# Add project root to sys.path for direct script execution
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Setup path
env_file = os.path.join(project_root, ".env")
load_dotenv(env_file)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ============================================
# IMPORTS
# ============================================

# Database
# Settings

# Analysis Engine
from src.core.analysis_engine import AnalysisEngine  # noqa: E402
from src.database.models import Match, SessionLocal  # noqa: E402

# FotMob provider (in data_provider.py) - V11.0: Use singleton pattern
from src.ingestion.data_provider import get_data_provider  # noqa: E402

# ============================================
# CONSTANTS
# ============================================

FORCED_NARRATIVE = "DEBUG_SIMULATION: Key striker and captain are OUT due to injury."


# ============================================
# MAIN FUNCTION
# ============================================


def select_upcoming_match(db_session) -> Match | None:
    """
    Select a real match from the database that has odds.

    For DEBUG purposes, we accept any match with odds (past or future).
    The AnalysisEngine will still process it even if the match has already started.

    Returns:
        Match object or None if no suitable match found
    """
    now_utc = datetime.now(timezone.utc)

    # Query for any matches with odds (DEBUG: accept past matches for testing)
    # Priority: future matches first, then fall back to any match with odds
    matches = (
        db_session.query(Match)
        .filter(
            Match.current_home_odd.isnot(None),
            Match.current_away_odd.isnot(None),
        )
        .order_by(Match.start_time.desc())  # Most recent first
        .limit(10)
        .all()
    )

    if not matches:
        logger.warning("⚠️ No matches with odds found in database")
        return None

    # Select the first match (most recent with odds)
    match = matches[0]
    logger.info(f"🎯 Selected match for force-analysis: {match.home_team} vs {match.away_team}")
    logger.info(f"   League: {match.league}")
    logger.info(f"   Kickoff: {match.start_time}")
    logger.info(
        f"   Odds: Home={match.current_home_odd}, Draw={match.current_draw_odd}, Away={match.current_away_odd}"
    )

    return match


def run_force_analysis() -> dict:
    """
    Main function to force-feed a match through the analysis engine.

    Returns:
        Dict with analysis results
    """
    logger.info("=" * 60)
    logger.info("🔧 PIPELINE FUNNEL DIAGNOSTIC - FORCE IGNITION (V11.0)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📋 Objective: Bypass Discovery layer to verify 'Last Mile'")
    logger.info("   (AI -> AnalysisEngine -> Notifier) pipeline health")
    logger.info("")
    logger.info(f"🔍 Forced Narrative: {FORCED_NARRATIVE}")
    logger.info("")

    # Initialize database session
    db = SessionLocal()

    try:
        # Step 1: Select an upcoming match
        logger.info("─" * 40)
        logger.info("STEP 1: Selecting upcoming match from database...")
        match = select_upcoming_match(db)

        if not match:
            logger.error("❌ No suitable match found. Exiting.")
            return {"error": "No match available", "alert_sent": False}

        # Step 2: Initialize AnalysisEngine
        logger.info("─" * 40)
        logger.info("STEP 2: Initializing AnalysisEngine...")
        analysis_engine = AnalysisEngine()
        logger.info("✅ AnalysisEngine initialized")

        # Step 3: Initialize FotMob provider (using singleton pattern)
        logger.info("─" * 40)
        logger.info("STEP 3: Initializing FotMob provider...")
        fotmob = get_data_provider()
        logger.info("✅ FotMob provider initialized (singleton)")

        # Step 4: Call analyze_match with forced narrative
        logger.info("─" * 40)
        logger.info("STEP 4: Calling analyze_match with forced narrative...")
        logger.info(f"   Match: {match.home_team} vs {match.away_team}")
        logger.info(f"   Forced Narrative: {FORCED_NARRATIVE}")

        now_utc = datetime.now(timezone.utc)

        analysis_result = analysis_engine.analyze_match(
            match=match,
            fotmob=fotmob,
            now_utc=now_utc,
            db_session=db,
            context_label="DEBUG_FORCE",
            nitter_intel=None,
            forced_narrative=FORCED_NARRATIVE,
        )

        # Step 5: Report results
        logger.info("─" * 40)
        logger.info("STEP 5: Analysis Results")
        logger.info(f"   Alert Sent: {analysis_result.get('alert_sent', False)}")
        logger.info(f"   Score: {analysis_result.get('score', 0.0):.1f}/10")
        logger.info(f"   Market: {analysis_result.get('market', 'N/A')}")
        logger.info(f"   Error: {analysis_result.get('error', 'None')}")
        logger.info(f"   News Count: {analysis_result.get('news_count', 0)}")

        if analysis_result.get("alert_sent"):
            logger.info("")
            logger.info("=" * 60)
            logger.info("🟢 SUCCESS: Alert was sent via Telegram!")
            logger.info("   The 'Last Mile' (AI -> Notifier) is HEALTHY.")
            logger.info("   Issue is strictly in Discovery layer (NewsRadar filtering).")
            logger.info("=" * 60)
        else:
            logger.info("")
            logger.info("=" * 60)
            logger.info("⚠️ ALERT NOT SENT: Check logs above for stopping point.")
            logger.info("   The issue could be in AnalysisEngine or Notifier.")
            logger.info("=" * 60)

        return analysis_result

    except Exception as e:
        logger.error(f"❌ Fatal error in force analysis: {e}", exc_info=True)
        return {"error": str(e), "alert_sent": False}

    finally:
        db.close()


# ============================================
# ENTRY POINT
# ============================================


if __name__ == "__main__":
    result = run_force_analysis()
    sys.exit(0 if result.get("alert_sent") else 1)
