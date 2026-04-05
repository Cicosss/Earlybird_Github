#!/usr/bin/env python3
"""
Intelligence Funnel Diagnostic - "Trace the Silent Funnel" (V1.0)

This script traces the exact fate of a news item from Search to AI Trigger
to identify where the intelligence bottleneck is occurring.

The diagnostic follows this flow:
1. SELECT: Query DB for a real upcoming match (next 72 hours)
2. SEARCH: Call SearchProvider (Brave) for that team
3. FILTER: Pass raw snippets through RelevanceAnalyzer
4. VERIFY: Check Tavily/Perplexity verification layer
5. TRIGGER: Log what WOULD be sent to AnalysisEngine.analyze_match

Usage:
    python src/utils/debug_intelligence_funnel.py
    or
    make run-intelligence-funnel

Author: Diagnostic Tool
Date: 2026-03-23
"""

import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

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
    format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ============================================
# IMPORTS
# ============================================

# Database
# Exclusion Filters (for bottleneck identification)
from src.config.exclusion_lists import (  # noqa: E402
    EXCLUDED_CATEGORIES,
    EXCLUDED_OTHER_SPORTS,
    EXCLUDED_SPORTS,
)
from src.database.models import Match, SessionLocal  # noqa: E402

# Search Providers
from src.ingestion.brave_provider import BraveSearchProvider  # noqa: E402
from src.ingestion.search_provider import get_search_provider  # noqa: E402

# Verification Layer
from src.services.intelligence_router import IntelligenceRouter  # noqa: E402

# Relevance Analysis
from src.utils.content_analysis import RelevanceAnalyzer  # noqa: E402

# ============================================
# CONSTANTS
# ============================================

# RELEVANCE THRESHOLD - items below this don't trigger analysis
RELEVANCE_THRESHOLD = 0.7

# Search query templates for intelligence gathering
SEARCH_KEYWORDS = [
    "injury",
    "suspension",
    "lineup",
    "absent",
    "out",
    "doubt",
    "fitness",
]


# ============================================
# UTILITY FUNCTIONS
# ============================================


def print_funnel_stage(stage_num: int, stage_name: str, emoji: str = "🔍"):
    """Print a formatted stage header."""
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"{emoji} STAGE {stage_num}: {stage_name}")
    logger.info("=" * 70)


def print_funnel_table(headers: list[str], rows: list[list[str]]):
    """Print a formatted table for the funnel visualization."""
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Print header
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    logger.info(f"┌{'─' * (len(header_line) + 2)}┐")
    logger.info(f"│ {header_line} │")
    logger.info(f"├{'─' * (len(header_line) + 2)}┤")

    # Print rows
    for row in rows:
        row_line = " │ ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        logger.info(f"│ {row_line} │")

    logger.info(f"└{'─' * (len(header_line) + 2)}┘")


# ============================================
# STAGE 1: SELECT LIVE TARGET
# ============================================


def select_upcoming_match(db_session) -> Match | None:
    """
    Query the local SQLite DB (Match table) for ANY match happening in the next 72 hours.

    Returns:
        Match object or None if no suitable match found
    """
    print_funnel_stage(1, "SELECT LIVE TARGET (Database Query)", "🎯")

    now_utc = datetime.now(timezone.utc)
    future_cutoff = now_utc + timedelta(hours=72)

    # Query for upcoming matches with odds
    matches = (
        db_session.query(Match)
        .filter(
            Match.start_time >= now_utc,
            Match.start_time <= future_cutoff,
            Match.current_home_odd.isnot(None),
            Match.current_away_odd.isnot(None),
        )
        .order_by(Match.start_time.asc())  # Soonest first
        .limit(5)
        .all()
    )

    if not matches:
        logger.warning("⚠️ No upcoming matches with odds in the next 72 hours")
        logger.info("   Falling back to any match with odds...")

        # Fallback: any match with odds
        matches = (
            db_session.query(Match)
            .filter(
                Match.current_home_odd.isnot(None),
                Match.current_away_odd.isnot(None),
            )
            .order_by(Match.start_time.desc())
            .limit(5)
            .all()
        )

    if not matches:
        logger.error("❌ No matches with odds found in database")
        return None

    # Select the first match (soonest)
    match = matches[0]

    # Check if this is a test match - if so, try to use a real team name for demo
    test_indicators = ["test", "Test", "TEST", "fake", "Fake", "demo", "Demo"]
    is_test_match = any(indicator in match.home_team for indicator in test_indicators)

    if is_test_match:
        logger.warning("⚠️ Database only contains TEST data - using fallback real team for demo")
        logger.info("   (In production, this would be a real upcoming match)")
        # Use a well-known team for demonstration purposes
        # This simulates what would happen with a real match
        match.home_team = "Arsenal"
        match.away_team = "Liverpool"
        match.league = "soccer_epl"
        match.start_time = now_utc + timedelta(hours=24)

    logger.info(f"✅ Selected match: {match.home_team} vs {match.away_team}")
    logger.info(f"   League: {match.league}")
    logger.info(f"   Kickoff: {match.start_time} (UTC)")
    logger.info(
        f"   Odds: Home={match.current_home_odd}, Draw={match.current_draw_odd}, Away={match.current_away_odd}"
    )

    return match


# ============================================
# STAGE 2: SIMULATE THE HUNT (Search Layer)
# ============================================


def simulate_search_hunt(team_name: str, league_key: str) -> list[dict]:
    """
    Force a call to SearchProvider (Brave) for that team.

    Returns:
        List of raw search results (snippets)
    """
    print_funnel_stage(2, "SIMULATE THE HUNT (Search Layer)", "🔍")

    logger.info(f"🔍 Searching for team: {team_name}")
    logger.info(f"   League: {league_key}")

    raw_results: list[dict[str, Any]] = []

    try:
        # Initialize Brave Search directly (most reliable)
        brave = BraveSearchProvider()

        if not brave.is_available():
            logger.warning("⚠️ Brave Search not available, trying generic SearchProvider...")
            search_provider = get_search_provider()
            if search_provider is None:
                logger.error("❌ No search provider available")
                return []
        else:
            search_provider = brave

        # Build search query with team name + keywords
        search_queries = [
            f"{team_name} injury latest",
            f"{team_name} squad news",
            f"{team_name} lineup update",
        ]

        all_results: list[dict[str, Any]] = []
        for query in search_queries:
            logger.info(f"   📡 Executing query: {query[:60]}...")
            try:
                results = search_provider.search_news(
                    query=query,
                    limit=5,
                    component="news_radar",  # Use news_radar for budget tracking
                )
                logger.info(f"      → Retrieved {len(results)} results")
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"      → Query failed: {e}")

        # Deduplicate by URL
        seen_urls = set()
        for result in all_results:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                raw_results.append(result)

        logger.info("")
        logger.info(f"📊 RAW INTEL COUNT: {len(raw_results)} snippets retrieved for {team_name}")

    except Exception as e:
        logger.error(f"❌ Search failed: {e}", exc_info=True)

    return raw_results


# ============================================
# STAGE 3: THE RELEVANCE FILTER (Bottleneck Detection)
# ============================================


def analyze_relevance_filters(raw_results: list[dict], team_name: str) -> tuple[list[dict], dict]:
    """
    Pass raw snippets through RelevanceAnalyzer and our keyword filters.

    Returns:
        Tuple of (filtered_results, filter_stats)
    """
    print_funnel_stage(3, "THE RELEVANCE FILTER (Bottleneck Detection)", "🔎")

    logger.info(f"🔬 Analyzing {len(raw_results)} raw snippets through relevance filters...")
    logger.info("")

    # Initialize RelevanceAnalyzer
    analyzer = RelevanceAnalyzer()

    # Compile exclusion patterns
    all_excluded = EXCLUDED_SPORTS + EXCLUDED_CATEGORIES + EXCLUDED_OTHER_SPORTS
    exclusion_pattern = re.compile(
        r"\b(" + "|".join(re.escape(kw) for kw in all_excluded) + r")\b",
        re.IGNORECASE,
    )

    # Compile positive keywords (for return detection)
    POSITIVE_KEYWORDS = [
        "return",
        "returning",
        "comeback",
        "recovers",
        "recovered",
        "back from injury",
        " available",
        "ready",
        "fit again",
        "rientra",
        "torna",
        "recupera",
        "disponibile",
    ]
    positive_pattern = re.compile(
        r"\b(" + "|".join(re.escape(kw) for kw in POSITIVE_KEYWORDS) + r")\b",
        re.IGNORECASE,
    )

    filtered_results: list[dict[str, Any]] = []
    filter_stats = {
        "total": len(raw_results),
        "excluded_sports": 0,
        "positive_news": 0,
        "no_keywords": 0,
        "low_confidence": 0,
        "passed": 0,
        "by_category": {},
    }

    # Process each result
    for idx, result in enumerate(raw_results):
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        url = result.get("url", "")
        content = f"{title} {snippet}"

        logger.info("")
        logger.info(f"  [{idx + 1}] Snippet: {title[:70]}...")

        # STEP 3a: Check exclusion filters
        exclusion_match = exclusion_pattern.search(content)
        if exclusion_match:
            filter_stats["excluded_sports"] += 1
            logger.info(f"      ❌ BLOCKED by EXCLUDED_SPORTS: '{exclusion_match.group()}'")
            continue

        # STEP 3b: Check positive news (player returning, not going out)
        positive_match = positive_pattern.search(content)
        # Note: We don't automatically block positive news, we just note it

        # STEP 3c: Run RelevanceAnalyzer
        analysis = analyzer.analyze(content)

        logger.info("      📊 RelevanceAnalyzer Result:")
        logger.info(f"         - is_relevant: {analysis.is_relevant}")
        logger.info(f"         - category: {analysis.category}")
        logger.info(f"         - confidence: {analysis.confidence:.2f}")
        logger.info(f"         - affected_team: {analysis.affected_team}")

        if positive_match:
            logger.info(f"      ⚠️ Contains POSITIVE_KEYWORD: '{positive_match.group()}'")

        # STEP 3d: Apply thresholds
        if not analysis.is_relevant:
            filter_stats["no_keywords"] += 1
            logger.info("      ❌ REJECTED: No relevance keywords found")
            continue

        if analysis.confidence < 0.3:
            filter_stats["low_confidence"] += 1
            logger.info(f"      ❌ REJECTED: Confidence {analysis.confidence:.2f} < 0.3")
            continue

        # Track by category
        category = analysis.category
        if category not in filter_stats["by_category"]:
            filter_stats["by_category"][category] = 0
        filter_stats["by_category"][category] += 1

        # Add to filtered results
        result["_analysis"] = {
            "category": analysis.category,
            "confidence": analysis.confidence,
            "affected_team": analysis.affected_team,
            "summary": analysis.summary,
            "has_positive_keyword": bool(positive_match),
        }
        filtered_results.append(result)
        filter_stats["passed"] += 1
        logger.info("      ✅ PASSED filters")

    # Print summary
    logger.info("")
    logger.info("📊 RELEVANCE FILTER SUMMARY:")
    logger.info(f"   Total raw snippets: {filter_stats['total']}")
    logger.info(f"   Blocked by EXCLUDED_SPORTS: {filter_stats['excluded_sports']}")
    logger.info(f"   No relevance keywords: {filter_stats['no_keywords']}")
    logger.info(f"   Low confidence (<0.3): {filter_stats['low_confidence']}")
    logger.info(f"   Filtered snippets (passed): {filter_stats['passed']}")
    if filter_stats["by_category"]:
        logger.info(f"   By category: {filter_stats['by_category']}")

    return filtered_results, filter_stats


# ============================================
# STAGE 4: VERIFICATION LAYER
# ============================================


def check_verification_layer(
    filtered_results: list[dict], team_name: str
) -> tuple[list[dict], dict]:
    """
    If a snippet passes the Relevance Filter, check if the system attempts to VERIFY it.

    Returns:
        Tuple of (verified_results, verification_stats)
    """
    print_funnel_stage(4, "VERIFICATION LAYER (Tavily/Perplexity Check)", "🔐")

    verification_stats = {
        "total": len(filtered_results),
        "attempted": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
    }

    verified_results: list[dict[str, Any]] = []

    if not filtered_results:
        logger.info("⚠️ No filtered results to verify")
        return verified_results, verification_stats

    logger.info(f"🔍 Checking verification layer for {len(filtered_results)} filtered results...")

    try:
        # Initialize IntelligenceRouter for verification
        router = IntelligenceRouter()
        logger.info("✅ IntelligenceRouter initialized")

        for idx, result in enumerate(filtered_results):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            analysis = result.get("_analysis", {})

            logger.info("")
            logger.info(f"  [{idx + 1}] Verifying: {title[:60]}...")
            logger.info(
                f"      Category: {analysis.get('category')}, Confidence: {analysis.get('confidence'):.2f}"
            )

            # Check if confidence is high enough to warrant verification
            confidence = analysis.get("confidence", 0)
            if confidence < 0.5:
                verification_stats["skipped"] += 1
                logger.info(f"      ⏭️ SKIPPED: Confidence {confidence:.2f} < 0.5 (too low)")
                continue

            # Attempt verification via IntelligenceRouter
            verification_stats["attempted"] += 1
            try:
                verification_result = router.verify_news_item(
                    news_title=title,
                    news_snippet=snippet,
                    team_name=team_name,
                    news_source=result.get("source", "Unknown"),
                    match_context="upcoming match verification",
                )

                if verification_result:
                    verification_stats["passed"] += 1
                    logger.info("      ✅ VERIFICATION PASSED")
                    result["_verification"] = verification_result
                    verified_results.append(result)
                else:
                    verification_stats["failed"] += 1
                    logger.info("      ❌ VERIFICATION FAILED (returned None)")

            except Exception as e:
                verification_stats["failed"] += 1
                logger.warning(f"      ⚠️ VERIFICATION ERROR: {e}")

    except Exception as e:
        logger.error(f"❌ Verification layer failed: {e}", exc_info=True)

    # Print summary
    logger.info("")
    logger.info("📊 VERIFICATION LAYER SUMMARY:")
    logger.info(f"   Total filtered results: {verification_stats['total']}")
    logger.info(f"   Verification attempted: {verification_stats['attempted']}")
    logger.info(f"   Verification passed: {verification_stats['passed']}")
    logger.info(f"   Verification failed: {verification_stats['failed']}")
    logger.info(f"   Skipped (low confidence): {verification_stats['skipped']}")

    return verified_results, verification_stats


# ============================================
# STAGE 5: THE ANALYZER TRIGGER (Handoff)
# ============================================


def check_analyzer_trigger(
    verified_results: list[dict],
    match: Match,
    trigger_threshold: float = 0.7,
) -> dict:
    """
    Log the exact payload that WOULD be sent to AnalysisEngine.analyze_match.

    Returns:
        Dict with trigger stats and payloads
    """
    print_funnel_stage(5, "ANALYZER TRIGGER (The Handoff)", "🚀")

    trigger_stats = {
        "total_verified": len(verified_results),
        "would_trigger": 0,
        "would_not_trigger": 0,
        "threshold": trigger_threshold,
        "payloads": [],
    }

    if not verified_results:
        logger.info("⚠️ No verified results to trigger analysis")
        return trigger_stats

    logger.info("🎯 Checking which verified results would trigger AnalysisEngine...")
    logger.info(f"   Trigger threshold: confidence >= {trigger_threshold}")
    logger.info("")

    for idx, result in enumerate(verified_results):
        analysis = result.get("_analysis", {})
        confidence = analysis.get("confidence", 0)

        logger.info(f"  [{idx + 1}] {result.get('title', '')[:60]}...")
        logger.info(f"      Confidence: {confidence:.2f}")

        if confidence >= trigger_threshold:
            trigger_stats["would_trigger"] += 1

            # Build the payload that would be sent to AnalysisEngine
            payload = {
                "match_id": match.id,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "league": match.league,
                "start_time": match.start_time.isoformat(),
                "news_title": result.get("title"),
                "news_snippet": result.get("snippet"),
                "news_url": result.get("url"),
                "news_category": analysis.get("category"),
                "news_confidence": confidence,
                "affected_team": analysis.get("affected_team"),
                "source": result.get("source", "Unknown"),
            }
            trigger_stats["payloads"].append(payload)

            logger.info("      ✅ WOULD TRIGGER analysis")
            logger.info(f"         Payload: {payload}")
        else:
            trigger_stats["would_not_trigger"] += 1
            logger.info(
                f"      ❌ WOULD NOT TRIGGER (confidence {confidence:.2f} < {trigger_threshold})"
            )

    # Print summary
    logger.info("")
    logger.info("📊 ANALYZER TRIGGER SUMMARY:")
    logger.info(f"   Total verified results: {trigger_stats['total_verified']}")
    logger.info(f"   Would trigger analysis: {trigger_stats['would_trigger']}")
    logger.info(f"   Would NOT trigger: {trigger_stats['would_not_trigger']}")
    logger.info(f"   Threshold: {trigger_stats['threshold']}")

    return trigger_stats


# ============================================
# FINAL FUNNEL SUMMARY
# ============================================


def print_funnel_summary(
    raw_count: int,
    filtered_count: int,
    filter_stats: dict,
    verified_count: int,
    verification_stats: dict,
    triggered_count: int,
    trigger_stats: dict,
):
    """Print the final funnel summary table."""
    print_funnel_stage(0, "FINAL FUNNEL SUMMARY", "📊")

    logger.info("")
    logger.info("╔══════════════════════════════════════════════════════════════════╗")
    logger.info("║              INTELLIGENCE FUNNEL - DIAGNOSTIC SUMMARY            ║")
    logger.info("╠══════════════════════════════════════════════════════════════════╣")
    logger.info(f"║  Raw Intel Search Results          │ {raw_count:>5}                      ║")
    logger.info("║  ───────────────────────────────────────────────────────────────║")
    logger.info(
        f"║  After EXCLUDED_SPORTS filter      │ {raw_count - filter_stats.get('excluded_sports', 0):>5}                      ║"
    )
    logger.info(
        f"║  After relevance keywords filter    │ {raw_count - filter_stats.get('excluded_sports', 0) - filter_stats.get('no_keywords', 0):>5}                      ║"
    )
    logger.info(
        f"║  After confidence threshold filter  │ {filtered_count:>5}                      ║"
    )
    logger.info("║  ───────────────────────────────────────────────────────────────║")
    logger.info(
        f"║  After Verification Layer          │ {verified_count:>5}                      ║"
    )
    logger.info("║  ───────────────────────────────────────────────────────────────║")
    logger.info(
        f"║  Would Trigger AnalysisEngine       │ {triggered_count:>5}                      ║"
    )
    logger.info("╠══════════════════════════════════════════════════════════════════╣")

    # Bottleneck identification
    if raw_count > 0 and filtered_count == 0:
        logger.info("║  🚨 BOTTLENECK IDENTIFIED: 100% blocked by Relevance Filters    ║")
        if filter_stats.get("excluded_sports", 0) == raw_count:
            logger.info("║     → All items blocked by EXCLUDED_SPORTS (basketball, etc.)    ║")
        elif filter_stats.get("no_keywords", 0) == raw_count:
            logger.info("║     → All items blocked by missing INJURY/CRISIS keywords         ║")
    elif filtered_count > 0 and verified_count == 0:
        logger.info("║  🚨 BOTTLENECK IDENTIFIED: Verification Layer failing all items    ║")
    elif verified_count > 0 and triggered_count == 0:
        logger.info("║  🚨 BOTTLENECK IDENTIFIED: Confidence below trigger threshold      ║")
    elif raw_count == 0:
        logger.info("║  🚨 BOTTLENECK IDENTIFIED: Search returned 0 results              ║")
    else:
        logger.info("║  ✅ FUNNEL APPEARS HEALTHY - Items progressing through            ║")

    logger.info("╚══════════════════════════════════════════════════════════════════╝")

    # Print filter breakdown
    logger.info("")
    logger.info("📋 FILTER BREAKDOWN:")
    logger.info(f"   - Total raw snippets: {raw_count}")
    logger.info(f"   - Blocked by EXCLUDED_SPORTS: {filter_stats.get('excluded_sports', 0)}")
    logger.info(f"   - Blocked by no keywords: {filter_stats.get('no_keywords', 0)}")
    logger.info(f"   - Blocked by low confidence: {filter_stats.get('low_confidence', 0)}")
    if filter_stats.get("by_category"):
        logger.info(f"   - Passed by category: {filter_stats['by_category']}")


# ============================================
# MAIN FUNCTION
# ============================================


def run_intelligence_funnel_diagnostic() -> dict:
    """
    Main function to trace the intelligence funnel.

    Returns:
        Dict with diagnostic results
    """
    logger.info("=" * 70)
    logger.info("🔬 INTELLIGENCE FUNNEL DIAGNOSTIC - 'Trace the Silent Funnel' (V1.0)")
    logger.info("=" * 70)
    logger.info("")
    logger.info("📋 Objective: Identify where news items are being discarded before")
    logger.info("   the AI (DeepSeek) gets a chance to analyze them.")
    logger.info("")
    logger.info(f"⏰ Current time: {datetime.now(timezone.utc).isoformat()}")
    logger.info("")

    # Initialize database session
    db = SessionLocal()

    try:
        # STAGE 1: Select a live target
        match = select_upcoming_match(db)
        if not match:
            logger.error("❌ No suitable match found. Exiting.")
            return {"error": "No match available"}

        team_name = match.home_team  # Primary search target
        league_key = match.league

        # STAGE 2: Simulate the hunt (Search Layer)
        raw_results = simulate_search_hunt(team_name, league_key)

        # STAGE 3: The Relevance Filter (Bottleneck Detection)
        filtered_results, filter_stats = analyze_relevance_filters(raw_results, team_name)

        # STAGE 4: Verification Layer
        verified_results, verification_stats = check_verification_layer(filtered_results, team_name)

        # STAGE 5: Analyzer Trigger
        trigger_stats = check_analyzer_trigger(verified_results, match)

        # FINAL: Print Funnel Summary
        print_funnel_summary(
            raw_count=len(raw_results),
            filtered_count=len(filtered_results),
            filter_stats=filter_stats,
            verified_count=len(verified_results),
            verification_stats=verification_stats,
            triggered_count=trigger_stats["would_trigger"],
            trigger_stats=trigger_stats,
        )

        return {
            "match": {
                "id": match.id,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "league": match.league,
                "start_time": match.start_time.isoformat(),
            },
            "raw_count": len(raw_results),
            "filtered_count": len(filtered_results),
            "filter_stats": filter_stats,
            "verified_count": len(verified_results),
            "verification_stats": verification_stats,
            "triggered_count": trigger_stats["would_trigger"],
            "trigger_stats": trigger_stats,
        }

    except Exception as e:
        logger.error(f"❌ Fatal error in intelligence funnel diagnostic: {e}", exc_info=True)
        return {"error": str(e)}

    finally:
        db.close()


# ============================================
# ENTRY POINT
# ============================================


if __name__ == "__main__":
    result = run_intelligence_funnel_diagnostic()

    if result.get("error"):
        logger.error(f"Diagnostic failed: {result['error']}")
        sys.exit(1)
    else:
        logger.info("")
        logger.info("✅ Diagnostic completed successfully")
        triggered = result.get("triggered_count", 0)
        raw = result.get("raw_count", 0)
        if raw > 0 and triggered == 0:
            logger.warning(f"⚠️ WARNING: {raw} items searched, 0 triggered analysis!")
            logger.warning("   The 'Silent Funnel' bottleneck is CONFIRMED.")
            sys.exit(1)
        elif triggered > 0:
            logger.info(f"🟢 SUCCESS: {triggered} items would trigger analysis.")
            sys.exit(0)
        else:
            logger.warning("⚠️ No raw results to analyze")
            sys.exit(1)
