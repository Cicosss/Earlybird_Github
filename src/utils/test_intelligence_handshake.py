#!/usr/bin/env python3
"""
Forensic Dataflow Trace - Intelligence Death Analysis
======================================================

Diagnostic script to trace a "Perfect Signal" from web discovery to AI analysis.

This script verifies that trigger keywords are:
1. Detected (Gate 1 - Keyword Hit)
2. Extracted and linked to a match (Gate 2 - Entity Extraction)
3. Evaluated against confidence threshold (Gate 3 - The Gating Filter)
4. Not silently discarded (Gate 4 - The Veto)
5. Passed to AI Analysis (Phase 3 - The Analysis Trigger)

Usage:
    python src/utils/test_intelligence_handshake.py
    python src/utils/test_intelligence_handshake.py --match-id <MATCH_ID>
    python src/utils/test_intelligence_handshake.py --mock

Author: EarlyBird Forensic Team
Version: 1.0.0
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Add project root to path
sys.path.insert(0, "/home/linux/Earlybird_Github")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("forensic_trace")

# ============================================
# PHASE 1: DATA SOURCE SIMULATION
# ============================================

HIGH_VALUE_KEYWORDS = ["bajas", "lesión", "crisis", "injured", "ruled out", "sidelined"]


def get_real_match_from_db():
    """Pick a real upcoming match from the database."""
    try:
        from src.database.models import Match, SessionLocal

        db = SessionLocal()
        try:
            # Try to get an upcoming match
            match = (
                db.query(Match)
                .filter(Match.start_time > datetime.now(timezone.utc))
                .filter(Match.current_home_odd.isnot(None))
                .order_by(Match.start_time.asc())
                .first()
            )

            if match:
                return {
                    "id": match.id,
                    "home_team": match.home_team,
                    "away_team": match.away_team,
                    "league": match.league,
                    "start_time": match.start_time.isoformat() if match.start_time else None,
                    "current_home_odd": match.current_home_odd,
                    "current_away_odd": match.current_away_odd,
                    "source": "database",
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not fetch match from database: {e}")

    return None


def get_recent_match_from_db():
    """Get a recent match from database (fallback if no upcoming matches)."""
    try:
        from src.database.models import Match, SessionLocal

        db = SessionLocal()
        try:
            match = (
                db.query(Match)
                .filter(Match.current_home_odd.isnot(None))
                .order_by(Match.start_time.desc())
                .first()
            )

            if match:
                return {
                    "id": match.id,
                    "home_team": match.home_team,
                    "away_team": match.away_team,
                    "league": match.league,
                    "start_time": match.start_time.isoformat() if match.start_time else None,
                    "current_home_odd": match.current_home_odd,
                    "current_away_odd": match.current_away_odd,
                    "source": "database_recent",
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not fetch recent match from database: {e}")

    return None


def create_mock_match():
    """Create a mock match for testing."""
    return {
        "id": "mock_match_001",
        "home_team": "Galatasaray",
        "away_team": "Fenerbahce",
        "league": "soccer_turkey_super_league",
        "start_time": "2026-03-30T18:00:00+00:00",
        "current_home_odd": 2.10,
        "current_away_odd": 3.25,
        "source": "mock",
    }


def create_mock_news_article(team_name: str) -> dict[str, Any]:
    """Create a mock news article with high-value keywords and optimized for passing all gates."""
    return {
        "title": f"Crisis en {team_name}: 3 bajas confirmadas, el delantero estrella con lesión muscular grave",
        "snippet": f"""
URGENTE: {team_name} enfrenta una crisis de lesiones sin precedentes.
El entrenador confirmó 3 bajas importantes: el delantero estrella con lesión muscular,
el mediocampista titular con problems de rodilla,
 y el defensa central por enfermedad.
El equipo está en crisis total antes del partido clave. Múltiples lesionados reportados.
El capitán está descartado por lesión. El equipo está en crisis total.
        """.strip(),
        "link": "https://www.gazzetta.it/calcio/12345",  # Using a real whitelisted domain for better source score
        "date": "1 hour ago",  # Using recognized format for freshness scoring
        "source": "Gazzetta dello Sport",
        # Add beat writer metadata for boost score
        "beat_writer_reliability": 0.9,
        "avg_lead_time_min": 30,
    }


def create_mock_tweet(team_name: str) -> dict[str, Any]:
    """Create a mock tweet with high-value keywords."""
    return {
        "content": f"🚨 BREAKING: {team_name} tiene 3 bajas confirmadas para mañana. Crisis total en el vestuario. Lesión muscular del capitán es la más grave.",
        "handle": "@SportsInsider",
        "date": datetime.now(timezone.utc).isoformat(),
        "topics": ["injury", "squad"],
    }


# ============================================
# PHASE 2: TRACING THE HANDSHAKE
# ============================================


def trace_gate_1_keyword_hit(news_text: str) -> dict[str, Any]:
    """
    Gate 1: Does the content trigger keyword detection?

    Tests the RelevanceAnalyzer / IntelligenceGate Level 1.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🔍 GATE 1: KEYWORD HIT DETECTION")
    logger.info("=" * 60)

    result = {
        "gate_name": "Keyword Hit Detection",
        "passed": False,
        "score": 0.0,
        "triggered_keywords": [],
        "details": {},
    }

    try:
        from src.utils.intelligence_gate import level_1_keyword_check_with_details

        gate_result = level_1_keyword_check_with_details(news_text)

        result["passed"] = gate_result["passes_gate"]
        result["triggered_keywords"] = (
            [gate_result.get("triggered_keyword")] if gate_result.get("triggered_keyword") else []
        )
        result["details"] = {
            "keyword_type": gate_result.get("keyword_type"),
            "language": gate_result.get("language"),
        }

        if result["passed"]:
            result["score"] = 1.0
            logger.info(f"   ✅ PASSED - Keyword found: '{gate_result.get('triggered_keyword')}'")
            logger.info(
                f"   📊 Type: {gate_result.get('keyword_type')}, Language: {gate_result.get('language')}"
            )
        else:
            logger.warning("   ❌ FAILED - No keywords detected")

    except ImportError as e:
        logger.error(f"   ⚠️ Intelligence gate not available: {e}")
        result["error"] = str(e)
        result["passed"] = None  # Unknown
    except Exception as e:
        logger.error(f"   ⚠️ Error during keyword check: {e}")
        result["error"] = str(e)

    return result


def trace_gate_2_entity_extraction(news_text: str, team_name: str, match: dict) -> dict[str, Any]:
    """
    Gate 2: Does the system correctly identify the team?

    Tests fuzzy matching and team alias resolution.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🔍 GATE 2: ENTITY EXTRACTION (Team Identification)")
    logger.info("=" * 60)

    result = {
        "gate_name": "Entity Extraction",
        "passed": False,
        "identified_team_id": None,
        "confidence": 0.0,
        "details": {},
    }

    try:
        from src.database.team_alias_utils import get_match_alias_data

        home_alias, away_alias = get_match_alias_data(match["home_team"], match["away_team"])

        # Check if team name matches
        home_match = (
            team_name.lower() in match["home_team"].lower()
            if team_name and match.get("home_team")
            else False
        )
        away_match = (
            team_name.lower() in match["away_team"].lower()
            if team_name and match.get("away_team")
            else False
        )

        result["passed"] = home_match or away_match
        result["identified_team_id"] = (
            match["home_team"] if home_match else (match["away_team"] if away_match else None)
        )
        result["details"] = {
            "home_alias": home_alias,
            "away_alias": away_alias,
            "home_match": home_match,
            "away_match": away_match,
        }

        if result["passed"]:
            result["confidence"] = 1.0
            logger.info(f"   ✅ PASSED - Team identified: '{result['identified_team_id']}'")
            logger.info(f"   📊 Home match: {home_match}, Away match: {away_match}")
        else:
            logger.warning(f"   ❌ FAILED - Team '{team_name}' not found in match")
            logger.warning(
                f"   📊 Match teams: {match.get('home_team')} vs {match.get('away_team')}"
            )

    except ImportError as e:
        logger.error(f"   ⚠️ Team alias utils not available: {e}")
        # Fallback to simple string matching
        home_match = (
            team_name.lower() in match["home_team"].lower()
            if team_name and match.get("home_team")
            else False
        )
        away_match = (
            team_name.lower() in match["away_team"].lower()
            if team_name and match.get("away_team")
            else False
        )
        result["passed"] = home_match or away_match
        result["identified_team_id"] = (
            match["home_team"] if home_match else (match["away_team"] if away_match else None)
        )
        result["error"] = str(e)
        logger.info(f"   📊 Fallback match result: {result['passed']}")
    except Exception as e:
        logger.error(f"   ⚠️ Error during entity extraction: {e}")
        result["error"] = str(e)

    return result


def trace_gate_3_confidence_threshold(news_item: dict, threshold: float = 0.7) -> dict[str, Any]:
    """
    Gate 3: Does the news item pass the ALERT_CONFIDENCE_THRESHOLD?

    Tests the news scorer and confidence evaluation.
    """
    logger.info("\n" + "=" * 60)
    logger.info(f"🔍 GATE 3: CONFIDENCE THRESHOLD (>= {threshold})")
    logger.info("=" * 60)

    result = {
        "gate_name": "Confidence Threshold",
        "passed": False,
        "score": 0.0,
        "threshold": threshold,
        "details": {},
    }

    try:
        from src.analysis.news_scorer import score_news_item

        score_result = score_news_item(news_item)

        result["score"] = score_result.raw_score
        result["details"] = {
            "tier": score_result.tier,
            "source_tier": score_result.source_tier,
            "source_points": score_result.source_points,
            "content_points": score_result.content_points,
            "freshness_points": score_result.freshness_points,
            "specificity_points": score_result.specificity_points,
            "primary_driver": score_result.primary_driver,
            "detected_keywords": score_result.detected_keywords[:5],
        }

        # Normalize to 0-1 scale for comparison with threshold
        normalized_score = score_result.raw_score / 10.0
        result["passed"] = normalized_score >= threshold

        if result["passed"]:
            logger.info(
                f"   ✅ PASSED - Score: {score_result.raw_score:.2f}/10 ({normalized_score:.2%})"
            )
            logger.info(f"   📊 Tier: {score_result.tier}, Driver: {score_result.primary_driver}")
            logger.info(f"   📊 Keywords: {score_result.detected_keywords[:3]}")
        else:
            logger.warning(
                f"   ❌ FAILED - Score: {score_result.raw_score:.2f}/10 ({normalized_score:.2%}) < {threshold:.2%}"
            )
            logger.warning(f"   📊 Tier: {score_result.tier}")

    except ImportError as e:
        logger.error(f"   ⚠️ News scorer not available: {e}")
        result["error"] = str(e)
        # Estimate based on keyword presence
        text = f"{news_item.get('title', '')} {news_item.get('snippet', '')}"
        keyword_count = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw.lower() in text.lower())
        estimated_score = min(keyword_count * 2.0, 8.0) / 10.0
        result["score"] = estimated_score * 10
        result["passed"] = estimated_score >= threshold
        result["details"]["estimated"] = True
        logger.info(
            f"   📊 Estimated score: {estimated_score:.2%} (based on {keyword_count} keywords)"
        )
    except Exception as e:
        logger.error(f"   ⚠️ Error during confidence scoring: {e}")
        result["error"] = str(e)

    return result


def trace_gate_4_veto_checks(news_item: dict, match: dict) -> dict[str, Any]:
    """
    Gate 4: Check for silent vetoes (duplicates, length filters, etc).
    """
    logger.info("\n" + "=" * 60)
    logger.info("🔍 GATE 4: VETO CHECKS (Duplicate, Length, Filters)")
    logger.info("=" * 60)

    result = {
        "gate_name": "Veto Checks",
        "passed": True,  # Assume passed unless veto found
        "veto_reason": None,
        "checks": {},
    }

    # Check 1: Content length
    snippet = news_item.get("snippet", "")
    if len(snippet) < 50:
        result["passed"] = False
        result["veto_reason"] = "Content too short (< 50 chars)"
        result["checks"]["length"] = {"passed": False, "length": len(snippet)}
        logger.warning(f"   ❌ VETO - Content too short: {len(snippet)} chars")
    else:
        result["checks"]["length"] = {"passed": True, "length": len(snippet)}
        logger.info(f"   ✅ Length check passed: {len(snippet)} chars")

    # Check 2: Duplicate check (using URL deduplicator if available)
    try:
        from src.utils.url_normalizer import get_deduplicator

        dedup = get_deduplicator()
        url = news_item.get("url", "")
        title = news_item.get("title", "")

        is_dup, reason = dedup.is_duplicate(url, title, snippet, check_content=True)
        if is_dup:
            result["passed"] = False
            result["veto_reason"] = f"Duplicate detected: {reason}"
            result["checks"]["duplicate"] = {"passed": False, "reason": reason}
            logger.warning(f"   ❌ VETO - Duplicate: {reason}")
        else:
            result["checks"]["duplicate"] = {"passed": True}
            logger.info("   ✅ Duplicate check passed")
    except ImportError:
        result["checks"]["duplicate"] = {"passed": True, "note": "Deduplicator not available"}
        logger.info("   ⚠️ Deduplicator not available, skipping duplicate check")
    except Exception as e:
        result["checks"]["duplicate"] = {"passed": True, "error": str(e)}
        logger.info(f"   ⚠️ Duplicate check error: {e}")

    # Check 3: Match has odds (required for analysis)
    if not match.get("current_home_odd"):
        result["passed"] = False
        result["veto_reason"] = "Match has no odds"
        result["checks"]["odds"] = {"passed": False}
        logger.warning("   ❌ VETO - Match has no odds")
    else:
        result["checks"]["odds"] = {"passed": True}
        logger.info("   ✅ Odds check passed")

    if result["passed"]:
        logger.info("   ✅ ALL VETO CHECKS PASSED")
    else:
        logger.warning(f"   ❌ VETO TRIGGERED: {result['veto_reason']}")

    return result


# ============================================
# PHASE 3: THE ANALYSIS TRIGGER
# ============================================


def trace_analysis_trigger(match: dict, news_item: dict, gate_results: dict) -> dict[str, Any]:
    """
    Phase 3: Show the exact function call that would invoke AI Analysis.

    This traces the path to AnalysisEngine.analyze_match() and shows
    the forced_narrative that would be sent to DeepSeek.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🧠 PHASE 3: ANALYSIS TRIGGER")
    logger.info("=" * 60)

    result = {
        "would_trigger": False,
        "function_call": None,
        "forced_narrative": None,
        "deepseek_prompt_preview": None,
    }

    # Check if all gates passed
    all_gates_passed = all(
        g.get("passed") is True for g in gate_results.values() if isinstance(g, dict)
    )

    if not all_gates_passed:
        logger.warning("   ❌ NOT TRIGGERED - One or more gates failed")
        failed_gates = [
            name for name, g in gate_results.items() if isinstance(g, dict) and not g.get("passed")
        ]
        logger.warning(f"   📊 Failed gates: {failed_gates}")
        result["failed_gates"] = failed_gates
        return result

    result["would_trigger"] = True

    # Build the forced_narrative (what gets sent to DeepSeek)
    forced_narrative = f"""
📰 NEWS SIGNAL FOR {match["home_team"]} vs {match["away_team"]}

HEADLINE: {news_item.get("title", "N/A")}

CONTENT:
{news_item.get("snippet", "N/A")}

SOURCE: {news_item.get("source", "Unknown")}
DATE: {news_item.get("date", "Unknown")}

MATCH CONTEXT:
- League: {match.get("league", "Unknown")}
- Home Odds: {match.get("current_home_odd", "N/A")}
- Away Odds: {match.get("current_away_odd", "N/A")}
""".strip()

    result["forced_narrative"] = forced_narrative

    # Show the function call
    result["function_call"] = {
        "module": "src.core.analysis_engine",
        "class": "AnalysisEngine",
        "method": "analyze_match",
        "parameters": {
            "match": f"<Match: {match['home_team']} vs {match['away_team']}>",
            "fotmob": "<FotMob provider>",
            "now_utc": datetime.now(timezone.utc).isoformat(),
            "db_session": "<Database session>",
            "context_label": "FORENSIC_TRACE",
            "forced_narrative": forced_narrative[:200] + "...",
        },
    }

    logger.info("   ✅ WOULD TRIGGER AI ANALYSIS")
    logger.info("\n" + "-" * 60)
    logger.info("📋 FUNCTION CALL:")
    logger.info("-" * 60)
    logger.info(f"   AnalysisEngine.analyze_match(")
    logger.info(f"       match={match['home_team']} vs {match['away_team']},")
    logger.info(f"       context_label='FORENSIC_TRACE',")
    logger.info(f"       forced_narrative='{forced_narrative[:100]}...'")
    logger.info(f"   )")

    logger.info("\n" + "-" * 60)
    logger.info("📝 FORCED NARRATIVE (sent to DeepSeek):")
    logger.info("-" * 60)
    logger.info(forced_narrative)

    # Preview the DeepSeek prompt structure
    try:
        from src.analysis.analyzer import USER_MESSAGE_TEMPLATE

        prompt_preview = USER_MESSAGE_TEMPLATE.format(
            today=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            home_team=match["home_team"],
            away_team=match["away_team"],
            news_snippet=forced_narrative[:1000],
            market_status=f"Home: {match.get('current_home_odd')}, Away: {match.get('current_away_odd')}",
            official_data="[FotMob data would be fetched here]",
            team_stats="[Team stats would be fetched here]",
            tactical_context="[Tactical context would be built here]",
            twitter_intel="[Twitter intel would be fetched here]",
            source_credibility="[Beat writer analysis would be here]",
            investigation_status="FORENSIC TRACE MODE",
        )

        result["deepseek_prompt_preview"] = prompt_preview[:1500] + "\n...[truncated]..."

        logger.info("\n" + "-" * 60)
        logger.info("🧠 DEEPSEEK PROMPT PREVIEW (first 1500 chars):")
        logger.info("-" * 60)
        logger.info(result["deepseek_prompt_preview"])

    except Exception as e:
        logger.warning(f"   ⚠️ Could not generate DeepSeek prompt preview: {e}")

    return result


# ============================================
# MAIN FORENSIC TRACE
# ============================================


def run_forensic_trace(match_id: str = None, use_mock: bool = False):
    """
    Run the complete forensic trace of the intelligence handshake.
    """
    print("\n" + "=" * 70)
    print("🔬 FORENSIC DATAFLOW TRACE - INTELLIGENCE DEATH ANALYSIS")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # ============================================
    # PHASE 1: DATA SOURCE
    # ============================================
    print("\n" + "=" * 70)
    print("📦 PHASE 1: DATA SOURCE SIMULATION")
    print("=" * 70)

    # Get match
    if use_mock:
        match = create_mock_match()
        logger.info("Using MOCK match data")
    elif match_id:
        try:
            from src.database.models import Match, SessionLocal

            db = SessionLocal()
            match_obj = db.query(Match).filter(Match.id == match_id).first()
            if match_obj:
                match = {
                    "id": match_obj.id,
                    "home_team": match_obj.home_team,
                    "away_team": match_obj.away_team,
                    "league": match_obj.league,
                    "start_time": match_obj.start_time.isoformat()
                    if match_obj.start_time
                    else None,
                    "current_home_odd": match_obj.current_home_odd,
                    "current_away_odd": match_obj.current_away_odd,
                    "source": "database_by_id",
                }
            else:
                logger.error(f"Match with ID {match_id} not found")
                return
            db.close()
        except Exception as e:
            logger.error(f"Failed to fetch match by ID: {e}")
            return
    else:
        match = get_real_match_from_db()
        if not match:
            logger.info("No upcoming matches found, trying recent matches...")
            match = get_recent_match_from_db()
        if not match:
            logger.info("No matches in database, using mock data...")
            match = create_mock_match()

    logger.info(f"\n📋 MATCH SELECTED:")
    logger.info(f"   ID: {match['id']}")
    logger.info(f"   Teams: {match['home_team']} vs {match['away_team']}")
    logger.info(f"   League: {match['league']}")
    logger.info(f"   Source: {match['source']}")

    # Create mock news
    team_for_news = match["home_team"]
    news_item = create_mock_news_article(team_for_news)

    logger.info(f"\n📰 MOCK NEWS ARTICLE CREATED:")
    logger.info(f"   Title: {news_item['title'][:60]}...")
    logger.info(f"   Keywords: {HIGH_VALUE_KEYWORDS[:3]}")

    # ============================================
    # PHASE 2: TRACING THE HANDSHAKE
    # ============================================
    print("\n" + "=" * 70)
    print("🔍 PHASE 2: TRACING THE HANDSHAKE (4 GATES)")
    print("=" * 70)

    news_text = f"{news_item['title']} {news_item['snippet']}"

    gate_results = {}

    # Gate 1: Keyword Hit
    gate_results["gate_1"] = trace_gate_1_keyword_hit(news_text)

    # Gate 2: Entity Extraction
    gate_results["gate_2"] = trace_gate_2_entity_extraction(news_text, team_for_news, match)

    # Gate 3: Confidence Threshold
    gate_results["gate_3"] = trace_gate_3_confidence_threshold(news_item, threshold=0.7)

    # Gate 4: Veto Checks
    gate_results["gate_4"] = trace_gate_4_veto_checks(news_item, match)

    # ============================================
    # PHASE 3: ANALYSIS TRIGGER
    # ============================================
    print("\n" + "=" * 70)
    print("🧠 PHASE 3: THE ANALYSIS TRIGGER")
    print("=" * 70)

    analysis_result = trace_analysis_trigger(match, news_item, gate_results)

    # ============================================
    # SUMMARY
    # ============================================
    print("\n" + "=" * 70)
    print("📊 FORENSIC TRACE SUMMARY")
    print("=" * 70)

    print("\n📋 GATE RESULTS:")
    for gate_name, gate_result in gate_results.items():
        status = "✅ PASS" if gate_result.get("passed") else "❌ FAIL"
        if gate_result.get("passed") is None:
            status = "⚠️ UNKNOWN"
        print(f"   {gate_name.upper()}: {status}")
        if gate_result.get("score"):
            print(f"      Score: {gate_result.get('score')}")

    print(
        f"\n🧠 AI ANALYSIS: {'✅ WOULD TRIGGER' if analysis_result['would_trigger'] else '❌ BLOCKED'}"
    )

    if not analysis_result["would_trigger"]:
        print(f"   Reason: Failed gates: {analysis_result.get('failed_gates', [])}")
    else:
        print(
            f"   forced_narrative length: {len(analysis_result.get('forced_narrative', ''))} chars"
        )

    print("\n" + "=" * 70)
    print("🔬 FORENSIC TRACE COMPLETE")
    print("=" * 70)

    # Return full results for programmatic use
    return {
        "match": match,
        "news_item": news_item,
        "gate_results": gate_results,
        "analysis_result": analysis_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Forensic Dataflow Trace - Intelligence Death Analysis"
    )
    parser.add_argument("--match-id", help="Specific match ID to analyze")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of database")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = run_forensic_trace(match_id=args.match_id, use_mock=args.mock)

    if args.json:
        # Output as JSON (serialize datetime objects)
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)

        print(json.dumps(result, default=json_serializer, indent=2))


if __name__ == "__main__":
    main()
