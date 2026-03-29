#!/usr/bin/env python3
"""
Pipeline Funnel Diagnostic - "Uncovering the Silence"

This script performs a "Trace" on the next 5 upcoming matches in the active continent.
For each match, it prints a Step-by-Step Report showing exactly where the pipeline stops.

Usage:
    python src/utils/debug_funnel.py
    or
    make run-funnel

Author: Diagnostic Tool
Date: 2026-02-19
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# Add project root to sys.path for direct script execution
# This allows imports like 'from config.settings import ...' to work when running:
# python src/utils/debug_funnel.py
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
from config.settings import ALERT_THRESHOLD_HIGH  # noqa: E402

# Analyzer
from src.analysis.analyzer import analyze_with_triangulation  # noqa: E402

# Analysis Engine
from src.core.analysis_engine import AnalysisEngine  # noqa: E402
from src.database.models import Match, SessionLocal  # noqa: E402

# Data Provider
from src.ingestion.data_provider import get_data_provider  # noqa: E402

# FotMob team mapping
from src.ingestion.fotmob_team_mapping import get_fotmob_team_id  # noqa: E402

# Global Orchestrator (V11.0: continental_orchestrator.py replaced by global_orchestrator.py)
from src.processing.global_orchestrator import (  # noqa: E402
    get_continental_orchestrator,  # Backward compatibility alias
)

# News Hunter
from src.processing.news_hunter import run_hunter_for_match  # noqa: E402

# ============================================
# CONSTANTS
# ============================================

# Thresholds from settings
MARKET_VETO_DROP_THRESHOLD = 25.0  # 25% drop triggers veto (V11.1: Relaxed from 15%)
ALERT_THRESHOLD = ALERT_THRESHOLD_HIGH  # 8.0 from settings (V11.1: Relaxed from 9.0)

# ============================================
# HELPER FUNCTIONS
# ============================================


def check_active_continent(match: Match) -> tuple[bool, str]:
    """
    Check if match is in the active continent based on current UTC time.

    Returns:
        Tuple of (is_active, continent_name)
    """
    try:
        orchestrator = get_continental_orchestrator()
        result = orchestrator.get_active_leagues_for_current_time()

        active_leagues = result.get("leagues", [])

        # Check if match's league is in active leagues
        # VPS FIX: Extract Match attributes safely to prevent session detachment
        # This prevents "Trust validation error" when Match object becomes detached
        # from session due to connection pool recycling under high load
        league = getattr(match, "league", None)

        if league and league in active_leagues:
            # Determine continent from league
            if "africa" in league.lower():
                return True, "AFRICA"
            elif any(
                x in league.lower() for x in ["argentina", "brazil", "mexico", "colombia", "usa"]
            ):
                return True, "LATAM"
            elif any(x in league.lower() for x in ["japan", "china", "korea", "australia"]):
                return True, "ASIA"
            else:
                return True, "UNKNOWN"
        else:
            return False, "NONE"
    except Exception as e:
        logger.warning(f"Failed to check active continent: {e}")
        return False, "ERROR"


def check_market_veto(match: Match) -> tuple[bool, float]:
    """
    Check if market veto should be triggered (25%+ odds drop).

    Returns:
        Tuple of (is_vetoed, drop_percentage)
    """
    max_drop_pct = 0.0

    # VPS FIX: Extract Match attributes safely to prevent session detachment
    # This prevents "Trust validation error" when Match object becomes detached
    # from session due to connection pool recycling under high load
    opening_home_odd = getattr(match, "opening_home_odd", None)
    current_home_odd = getattr(match, "current_home_odd", None)
    opening_away_odd = getattr(match, "opening_away_odd", None)
    current_away_odd = getattr(match, "current_away_odd", None)
    opening_draw_odd = getattr(match, "opening_draw_odd", None)
    current_draw_odd = getattr(match, "current_draw_odd", None)

    # Check home odd drop
    if opening_home_odd and current_home_odd:
        home_drop_pct = ((opening_home_odd - current_home_odd) / opening_home_odd) * 100
        max_drop_pct = max(max_drop_pct, home_drop_pct)

    # Check away odd drop
    if opening_away_odd and current_away_odd:
        away_drop_pct = ((opening_away_odd - current_away_odd) / opening_away_odd) * 100
        max_drop_pct = max(max_drop_pct, away_drop_pct)

    # Check draw odd drop
    if opening_draw_odd and current_draw_odd:
        draw_drop_pct = ((opening_draw_odd - current_draw_odd) / opening_draw_odd) * 100
        max_drop_pct = max(max_drop_pct, draw_drop_pct)

    is_vetoed = max_drop_pct >= MARKET_VETO_DROP_THRESHOLD
    return is_vetoed, max_drop_pct


def calculate_kelly_criterion(match: Match, score: float) -> float:
    """
    Calculate Kelly Criterion stake percentage.

    Simplified calculation: Kelly = (Score - 5.0) / 10.0
    (Score 5.0 = 0% Kelly, Score 10.0 = 50% Kelly)

    Args:
        match: Match object
        score: AI analysis score (0-10)

    Returns:
        Kelly stake percentage (0-50%)
    """
    if score < 5.0:
        return 0.0
    return min(50.0, (score - 5.0) / 10.0 * 100)


# ============================================
# MAIN DIAGNOSTIC FUNCTION
# ============================================


def trace_match_pipeline(match: Match, analysis_engine: AnalysisEngine, fotmob) -> dict:
    """
    Trace a single match through entire pipeline.

    Returns:
        Dict with trace results
    """
    # VPS FIX: Extract Match attributes safely to prevent session detachment
    # This prevents "Trust validation error" when Match object becomes detached
    # from session due to connection pool recycling under high load
    match_id = getattr(match, "id", None)
    home_team = getattr(match, "home_team", None)
    away_team = getattr(match, "away_team", None)
    league = getattr(match, "league", None)
    start_time = getattr(match, "start_time", None)

    trace_result = {
        "match_id": match_id,
        "home_team": home_team,
        "away_team": away_team,
        "league": league,
        "start_time": start_time,
        "steps": [],
        "stop_reason": None,
        "final_score": 0.0,
        "alert_sent": False,
    }

    # ============================================
    # STEP 1: INGESTION
    # ============================================
    is_active, continent = check_active_continent(match)
    step1_result = {
        "step": 1,
        "name": "Ingestion",
        "match": f"{home_team} vs {away_team}",
        "league": league,
        "active_continent": is_active,
        "continent_name": continent,
        "status": "PASS" if is_active else "FAIL",
    }
    trace_result["steps"].append(step1_result)

    if not is_active:
        trace_result["stop_reason"] = f"Step 1: Match not in active continent ({continent})"
        return trace_result

    # ============================================
    # STEP 2: SEARCH (News Hunting)
    # ============================================
    try:
        news_articles = run_hunter_for_match(match, include_insiders=True)
        news_count = len(news_articles)

        # Get dork used (from first article if available)
        dork_used = "Unknown"
        if news_articles:
            first_article = news_articles[0]
            dork_used = first_article.get("keyword", "Unknown")

        step2_result = {
            "step": 2,
            "name": "Search",
            "news_count": news_count,
            "dork_used": dork_used,
            "status": "PASS" if news_count > 0 else "FAIL",
        }
        trace_result["steps"].append(step2_result)

        if news_count == 0:
            trace_result["stop_reason"] = "Step 2: No news articles found"
            return trace_result
    except Exception as e:
        step2_result = {
            "step": 2,
            "name": "Search",
            "news_count": 0,
            "dork_used": "ERROR",
            "status": "ERROR",
            "error": str(e),
        }
        trace_result["steps"].append(step2_result)
        trace_result["stop_reason"] = f"Step 2: Search error - {e}"
        return trace_result

    # ============================================
    # STEP 3: AI ANALYSIS
    # ============================================
    try:
        # Validate team order using FotMob
        home_team_valid = home_team
        away_team_valid = away_team

        if fotmob:
            try:
                fotmob_home_id = get_fotmob_team_id(home_team)
                fotmob_away_id = get_fotmob_team_id(away_team)

                if fotmob_home_id and fotmob_away_id:
                    fotmob_match = fotmob.get_match(fotmob_home_id, fotmob_away_id, start_time)

                    if fotmob_match:
                        fotmob_home_name = fotmob_match.get("home", {}).get("name", "")
                        fotmob_away_name = fotmob_match.get("away", {}).get("name", "")

                        if fotmob_home_name and fotmob_away_name and home_team != fotmob_home_name:
                            home_team_valid, away_team_valid = away_team_valid, home_team_valid
            except Exception as e:
                logger.debug(f"Team order validation skipped: {e}")

        # Run parallel enrichment
        enrichment_data = None
        try:
            from src.utils.parallel_enrichment import enrich_match_parallel

            enrichment_data = enrich_match_parallel(
                fotmob=fotmob,
                home_team=home_team_valid,
                away_team=away_team_valid,
                match_start_time=start_time,
                weather_provider=None,
                # max_workers=4,  # REMOVED - use default (1) to avoid FotMob 403 errors (V6.2 fix)
                timeout=90,  # UPDATED from 45 to 90 for retries and backoff (COVE fix V6.3)
            )
        except Exception as e:
            logger.debug(f"Parallel enrichment failed: {e}")

        # Extract enrichment results
        home_context = enrichment_data.home_context if enrichment_data else {}
        away_context = enrichment_data.away_context if enrichment_data else {}
        home_stats = enrichment_data.home_stats if enrichment_data else {}
        away_stats = enrichment_data.away_stats if enrichment_data else {}

        # Run AI triangulation analysis
        analysis_result = analyze_with_triangulation(
            match=match,
            home_context=home_context,
            away_context=away_context,
            home_stats=home_stats,
            away_stats=away_stats,
            news_articles=news_articles,
            twitter_intel=None,
            twitter_intel_for_ai="",
            fatigue_differential=None,
            injury_impact_home=None,
            injury_impact_away=None,
            biscotto_result={"is_suspect": False},
            market_intel=None,
            referee_info=None,
        )

        # Extract score and driver
        ai_score = analysis_result.score if hasattr(analysis_result, "score") else 0.0
        driver = analysis_result.reason if hasattr(analysis_result, "reason") else "Unknown"

        step3_result = {
            "step": 3,
            "name": "AI Analysis",
            "ai_score": ai_score,
            "driver": driver,
            "status": "PASS" if ai_score > 0 else "FAIL",
        }
        trace_result["steps"].append(step3_result)
        trace_result["final_score"] = ai_score

        if ai_score == 0:
            trace_result["stop_reason"] = "Step 3: AI analysis returned 0 score"
            return trace_result
    except Exception as e:
        step3_result = {
            "step": 3,
            "name": "AI Analysis",
            "ai_score": 0.0,
            "driver": "ERROR",
            "status": "ERROR",
            "error": str(e),
        }
        trace_result["steps"].append(step3_result)
        trace_result["stop_reason"] = f"Step 3: AI analysis error - {e}"
        return trace_result

    # ============================================
    # STEP 4: QUANT FILTER
    # ============================================

    # 4a: Market Veto Check
    is_vetoed, drop_pct = check_market_veto(match)
    veto_status = "Triggered" if is_vetoed else "Pass"

    # 4b: Kelly Stake Calculation
    kelly_stake = calculate_kelly_criterion(match, trace_result["final_score"])

    # 4c: Final Score vs Threshold Check
    threshold_pass = trace_result["final_score"] >= ALERT_THRESHOLD
    threshold_status = "Pass" if threshold_pass else "Fail"

    step4_result = {
        "step": 4,
        "name": "Quant Filter",
        "market_veto": {
            "status": veto_status,
            "drop_pct": drop_pct,
            "threshold": MARKET_VETO_DROP_THRESHOLD,
        },
        "kelly_stake": kelly_stake,
        "threshold_check": {
            "status": threshold_status,
            "score": trace_result["final_score"],
            "threshold": ALERT_THRESHOLD,
        },
        "status": "PASS" if threshold_pass and not is_vetoed else "FAIL",
    }
    trace_result["steps"].append(step4_result)

    # Determine stop reason
    if is_vetoed:
        trace_result["stop_reason"] = f"Step 4: Market Veto triggered ({drop_pct:.1f}% drop)"
    elif not threshold_pass:
        trace_result["stop_reason"] = (
            f"Step 4: Score {trace_result['final_score']:.1f} below threshold {ALERT_THRESHOLD}"
        )
    else:
        trace_result["stop_reason"] = None
        trace_result["alert_sent"] = True

    return trace_result


# ============================================
# MAIN ENTRY POINT
# ============================================


def main():
    """Main diagnostic entry point."""
    logger.info("=" * 80)
    logger.info("PIPELINE FUNNEL DIAGNOSTIC - Uncovering the Silence")
    logger.info("=" * 80)

    # Initialize database
    db = SessionLocal()

    try:
        # Get current UTC time
        now_utc = datetime.now(timezone.utc)
        now_naive = now_utc.replace(tzinfo=None)  # DB stores naive datetimes
        end_window_naive = now_naive + timedelta(hours=72)

        logger.info(f"Current UTC time: {now_utc.isoformat()}")
        logger.info("Analysis window: Next 72 hours")
        logger.info(f"Alert threshold: {ALERT_THRESHOLD}")
        logger.info("")

        # For diagnostic tool, skip active continent check to avoid blocking operations
        # Just trace all upcoming matches regardless of continent
        logger.info("Skipping active continent check (diagnostic mode)")
        logger.info("")

        # Fetch next 5 upcoming matches (any league, not just Elite)
        matches = (
            db.query(Match)
            .filter(
                Match.start_time > now_naive,
                Match.start_time <= end_window_naive,
            )
            .order_by(Match.start_time.asc())
            .limit(5)
            .all()
        )

        logger.info(f"Found {len(matches)} upcoming matches to trace")
        logger.info("")

        if not matches:
            logger.warning("No upcoming matches found in the next 72 hours")
            return

        # Initialize components
        logger.info("Initializing components...")
        try:
            analysis_engine = AnalysisEngine()
            logger.info("✅ Analysis Engine initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Analysis Engine: {e}")
            return

        try:
            fotmob = get_data_provider()
            logger.info("✅ FotMob provider initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize FotMob provider: {e}")
            fotmob = None

        logger.info("")

        # Trace each match and save results
        trace_results = []
        for i, match in enumerate(matches, 1):
            logger.info("=" * 80)
            logger.info(f"TRACE #{i}: {match.home_team} vs {match.away_team}")
            logger.info(f"League: {match.league}")
            logger.info(f"Start Time (UTC): {match.start_time}")
            logger.info("=" * 80)

            # Trace match
            trace_result = trace_match_pipeline(match, analysis_engine, fotmob)
            trace_results.append(trace_result)

            # Print step-by-step report
            for step in trace_result["steps"]:
                step_num = step["step"]
                step_name = step["name"]
                status = step["status"]

                logger.info("")
                logger.info(f"STEP {step_num}: {step_name.upper()}")
                logger.info("-" * 40)

                if step_num == 1:  # Ingestion
                    logger.info(f"Match found: {step['match']}")
                    logger.info(f"League: {step['league']}")
                    logger.info(
                        f"Active Continent? {step['active_continent']} ({step['continent_name']})"
                    )
                    logger.info(f"Status: {status}")

                elif step_num == 2:  # Search
                    logger.info(f"Fetching news... Found {step['news_count']} articles")
                    logger.info(f"Dork used: {step['dork_used']}")
                    if "error" in step:
                        logger.error(f"Error: {step['error']}")
                    logger.info(f"Status: {status}")

                elif step_num == 3:  # AI Analysis
                    logger.info(f"AI Raw Score: {step['ai_score']:.1f}")
                    logger.info(f"Driver: {step['driver']}")
                    if "error" in step:
                        logger.error(f"Error: {step['error']}")
                    logger.info(f"Status: {status}")

                elif step_num == 4:  # Quant Filter
                    logger.info(f"Market Veto (15% drop): {step['market_veto']['status']}")
                    logger.info(f"  Drop: {step['market_veto']['drop_pct']:.1f}%")
                    logger.info(f"Kelly Stake: {step['kelly_stake']:.1f}%")
                    threshold_v = step["threshold_check"]["threshold"]
                    threshold_status = step["threshold_check"]["status"]
                    logger.info(f"Final Score vs Threshold ({threshold_v}): {threshold_status}")
                    logger.info(f"  Score: {step['threshold_check']['score']:.1f}")
                    logger.info(f"Status: {status}")

            # Print stop reason
            logger.info("")
            logger.info("=" * 80)
            if trace_result["stop_reason"]:
                logger.warning(f"🛑 STOP: {trace_result['stop_reason']}")
            else:
                logger.info(f"✅ ALERT WOULD BE SENT: Score {trace_result['final_score']:.1f}/10")
            logger.info("=" * 80)
            logger.info("")

        # Summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("DIAGNOSTIC SUMMARY")
        logger.info("=" * 80)

        total_matches = len(trace_results)
        alerts_sent = sum(1 for t in trace_results if t["alert_sent"])

        # Count stop reasons
        stop_reasons = {}
        for trace in trace_results:
            reason = trace["stop_reason"] or "ALERT SENT"
            stop_reasons[reason] = stop_reasons.get(reason, 0) + 1

        logger.info(f"Total matches traced: {total_matches}")
        logger.info(f"Alerts would be sent: {alerts_sent}")
        logger.info("")
        logger.info("Stop reasons:")
        for reason, count in stop_reasons.items():
            logger.info(f"  {reason}: {count}")

        logger.info("")
        logger.info("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
