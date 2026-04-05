#!/usr/bin/env python3
"""
Sniper Handshake Validation (V12.6) — End-to-End Dry Run
=========================================================

Diagnostic script that validates the complete Alpha Hunter pipeline
from match selection → Supabase domains → real search → relevance scoring → trigger.

Phases:
  1. INGESTION:  Find a real match in the next 48h, get Supabase domains + language keywords
  2. HUNTING:     Build a targeted dork with team name, execute a REAL search (no mocks)
  3. INTELLIGENCE: Score each snippet, extract team entity, build the trigger object
  4. RETRY:       If 0 results, retry with broader query (league name only + domains)

Usage:
    make run-sniper-handshake
    PYTHONPATH=. python src/utils/test_sniper_handshake.py

Author: Earlybird Diagnostics
Version: V12.6
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup — same pattern as debug_funnel.py / test_intelligence_handshake.py
# ---------------------------------------------------------------------------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

env_file = os.path.join(project_root, ".env")
load_dotenv(env_file)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sniper_handshake")

# ============================================================================
# PHASE 1 — INGESTION
# ============================================================================


def find_match_in_next_48h() -> dict | None:
    """
    Select a real upcoming match from the local SQLite DB occurring
    within the next 48 hours.  Prefers Argentine / Brazilian / Colombian
    matches because they have rich Supabase coverage.
    """
    from src.database.models import Match, SessionLocal

    PREFERRED_LEAGUES = [
        "soccer_argentina_primera_division",
        "soccer_brazil_campeonato",
        "soccer_colombia_primera_a",
        "soccer_turkey_super_league",
        "soccer_mexico_ligamx",
        "soccer_spain_la_liga",
    ]

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        max_time = now + timedelta(hours=48)

        # Make start_time timezone-aware for comparison
        from sqlalchemy import func as sa_func

        # Try preferred leagues first
        for league in PREFERRED_LEAGUES:
            match = (
                db.query(Match)
                .filter(
                    Match.start_time > now.replace(tzinfo=None),
                    Match.start_time < max_time.replace(tzinfo=None),
                    Match.league == league,
                    Match.current_home_odd.isnot(None),
                )
                .order_by(Match.start_time.asc())
                .first()
            )
            if match:
                return _match_to_dict(match)

        # Fallback: any league with odds
        match = (
            db.query(Match)
            .filter(
                Match.start_time > now.replace(tzinfo=None),
                Match.start_time < max_time.replace(tzinfo=None),
                Match.current_home_odd.isnot(None),
            )
            .order_by(Match.start_time.asc())
            .first()
        )
        if match:
            return _match_to_dict(match)

        # Last resort: most recent match with odds
        match = (
            db.query(Match)
            .filter(Match.current_home_odd.isnot(None))
            .order_by(Match.start_time.desc())
            .first()
        )
        if match:
            logger.warning("⚠️ No upcoming match in 48h — using most recent match as fallback")
            return _match_to_dict(match)

    except Exception as e:
        logger.error(f"❌ DB error: {e}")
    finally:
        db.close()

    return None


def _match_to_dict(match) -> dict:
    """Safely extract match attributes to prevent session detachment."""
    return {
        "id": getattr(match, "id", "unknown"),
        "home_team": getattr(match, "home_team", "Unknown"),
        "away_team": getattr(match, "away_team", "Unknown"),
        "league": getattr(match, "league", "unknown"),
        "start_time": getattr(match, "start_time", None),
        "current_home_odd": getattr(match, "current_home_odd", None),
        "current_draw_odd": getattr(match, "current_draw_odd", None),
        "current_away_odd": getattr(match, "current_away_odd", None),
    }


def fetch_supabase_domains(league_key: str) -> list[str]:
    """
    Fetch news source domains from Supabase for a specific league.
    Falls back to local config if Supabase is unavailable.
    """
    # Try Supabase first via news_hunter helper
    try:
        from src.processing.news_hunter import get_news_sources_from_supabase

        domains = get_news_sources_from_supabase(league_key)
        if domains:
            logger.info(f"📡 [SUPABASE] Fetched {len(domains)} domains for {league_key}")
            return domains
    except Exception as e:
        logger.warning(f"⚠️ Supabase fetch failed: {e}")

    # Fallback: search_provider local config
    try:
        from src.ingestion.search_provider import get_news_domains_for_league

        domains = get_news_domains_for_league(league_key)
        if domains:
            logger.info(f"🔄 [FALLBACK] Using local LEAGUE_DOMAINS for {league_key}")
            return domains
    except Exception as e:
        logger.warning(f"⚠️ Local domains fallback failed: {e}")

    return []


def get_language_keywords(league_key: str) -> tuple[str, list[str], list[str]]:
    """
    Get language code and native + English keywords for the league.

    Returns:
        (language_code, native_keywords, english_keywords)
    """
    try:
        from src.ingestion.alpha_hunter import (
            _LANGUAGE_KEYWORDS,
            _LEAGUE_LANGUAGE_MAP,
            TRIGGER_KEYWORDS,
        )

        # Detect language
        language = "en"
        league_lower = league_key.lower() if league_key else ""
        for pattern, lang in _LEAGUE_LANGUAGE_MAP.items():
            if pattern in league_lower:
                language = lang
                break

        native = _LANGUAGE_KEYWORDS.get(language, [])
        english = _LANGUAGE_KEYWORDS.get("en", [])

        # Filter to only TRIGGER-relevant keywords
        all_injury = [kw.lower() for kw in TRIGGER_KEYWORDS.get("injury", [])]
        all_absence = [kw.lower() for kw in TRIGGER_KEYWORDS.get("absence", [])]
        all_squad = [kw.lower() for kw in TRIGGER_KEYWORDS.get("squad", [])]
        all_trigger = all_injury + all_absence + all_squad

        native_filtered = [kw for kw in native if kw.lower() in all_trigger]
        en_filtered = [kw for kw in english if kw.lower() in all_trigger]

        return language, native_filtered, en_filtered

    except ImportError:
        # Fallback: hardcoded Spanish/Portuguese
        if "argentina" in (league_key or "").lower() or "colombia" in (league_key or "").lower():
            return (
                "es",
                ["lesión", "lesiones", "baja", "bajas"],
                ["injury", "injured", "squad", "out"],
            )
        elif "brazil" in (league_key or "").lower():
            return (
                "pt",
                ["lesão", "lesões", "desfalque", "desfalques"],
                ["injury", "injured", "squad", "out"],
            )
        else:
            return "en", [], ["injury", "injured", "squad", "out", "suspended"]


# ============================================================================
# PHASE 2 — HUNTING (Real Search)
# ============================================================================


def build_targeted_dork(
    team_name: str,
    native_keywords: list[str],
    en_keywords: list[str],
    domains: list[str],
) -> str:
    """
    Build the exact search dork sent to the search engine.

    Format:  "Team Name" (native_kw_1 OR native_kw_2) (site:domain1 OR site:domain2)

    Falls back to English keywords if no native keywords available.
    """
    # Pick keywords: native first, English fallback
    keywords = native_keywords[:5] if native_keywords else en_keywords[:5]
    if not keywords:
        keywords = ["injury", "squad", "lineup"]

    kw_string = " OR ".join(keywords[:5])
    site_dork = " OR ".join([f"site:{d}" for d in domains[:4]])

    query = f'"{team_name}" ({kw_string}) ({site_dork})'
    return query


def build_broader_dork(
    league_key: str,
    native_keywords: list[str],
    en_keywords: list[str],
    domains: list[str],
) -> str:
    """
    Build a broader dork using the league name instead of team name.
    Used as fallback when targeted search returns 0 results.
    """
    # Extract a human-readable league name from the key
    league_name = league_key.replace("soccer_", "").replace("_", " ") if league_key else "football"

    keywords = native_keywords[:3] if native_keywords else en_keywords[:3]
    if not keywords:
        keywords = ["injury", "squad"]

    kw_string = " OR ".join(keywords[:3])
    site_dork = " OR ".join([f"site:{d}" for d in domains[:4]])

    query = f'"{league_name}" ({kw_string}) ({site_dork})'
    return query


def execute_real_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Execute a REAL search call to the search engine (Brave → DDG → Mediastack).
    No mocks — this is the actual pipeline.
    """
    try:
        from src.ingestion.search_provider import get_search_provider

        provider = get_search_provider()
        if not provider.is_available():
            logger.error("❌ No search provider available!")
            return []

        logger.info(f"🔍 Executing search: {query[:120]}...")
        results = provider.search(query, num_results=num_results)
        return results

    except Exception as e:
        logger.error(f"❌ Search execution failed: {e}")
        return []


# ============================================================================
# PHASE 3 — INTELLIGENCE (Relevance & Extraction)
# ============================================================================


def score_relevance(item: dict, threshold: float = 0.7) -> dict:
    """
    Score a search result for relevance using NewsScorer + AlphaHunter confidence.

    Returns:
        dict with 'passed', 'relevance_score', 'confidence', 'details'
    """
    result = {
        "passed": False,
        "relevance_score": 0.0,
        "confidence": 0.0,
        "details": {},
    }

    # Method 1: news_scorer (0-10 scale, normalize to 0-1)
    try:
        from src.analysis.news_scorer import score_news_item

        score_result = score_news_item(item)
        normalized = score_result.raw_score / 10.0
        result["relevance_score"] = round(normalized, 3)
        result["details"]["news_scorer"] = {
            "raw": round(score_result.raw_score, 2),
            "tier": score_result.tier,
            "driver": score_result.primary_driver,
            "keywords": score_result.detected_keywords[:5],
        }
    except Exception as e:
        logger.debug(f"NewsScorer unavailable: {e}")
        result["details"]["news_scorer_error"] = str(e)

    # Method 2: AlphaHunter confidence calculation
    try:
        from src.ingestion.alpha_hunter import AlphaHunter, TRIGGER_KEYWORDS

        hunter = AlphaHunter()
        title = item.get("title", "")
        snippet = item.get("snippet", "") or item.get("summary", "")
        matched_kws = []
        text_lower = f"{title} {snippet}".lower()
        for kws in TRIGGER_KEYWORDS.values():
            for kw in kws:
                if kw.lower() in text_lower:
                    matched_kws.append(kw)

        confidence = hunter._calculate_confidence(title, snippet, matched_kws)
        result["confidence"] = round(confidence, 3)
        result["details"]["alpha_confidence"] = {
            "confidence": round(confidence, 3),
            "keywords_matched": matched_kws[:5],
        }
    except Exception as e:
        logger.debug(f"AlphaHunter confidence unavailable: {e}")
        result["details"]["alpha_confidence_error"] = str(e)

    # Combined check: passed if EITHER score >= threshold
    result["passed"] = result["relevance_score"] >= threshold or result["confidence"] >= threshold

    return result


def check_entity_extraction(item: dict, expected_team: str, league_key: str) -> dict:
    """
    Check if the system correctly identifies the team from the snippet.
    """
    result = {
        "expected_team": expected_team,
        "extracted_team": None,
        "match": False,
        "method": None,
    }

    title = item.get("title", "")
    snippet = item.get("snippet", "") or item.get("summary", "")

    # Method 1: AlphaHunter entity extraction
    try:
        from src.ingestion.alpha_hunter import AlphaHunter

        hunter = AlphaHunter()
        extracted = hunter._extract_team_entity(title, snippet, league_key)
        if extracted:
            result["extracted_team"] = extracted
            result["method"] = "alpha_hunter"
    except Exception as e:
        logger.debug(f"AlphaHunter entity extraction failed: {e}")

    # Method 2: Simple string matching (fallback)
    if not result["extracted_team"]:
        text_lower = f"{title} {snippet}".lower()
        team_lower = expected_team.lower()
        if team_lower in text_lower:
            result["extracted_team"] = expected_team
            result["method"] = "string_match"

    # Check if extracted matches expected
    if result["extracted_team"]:
        ext_lower = result["extracted_team"].lower()
        exp_lower = expected_team.lower()
        result["match"] = ext_lower in exp_lower or exp_lower in ext_lower

    return result


def build_trigger_object(
    match_info: dict,
    item: dict,
    relevance: dict,
    entity: dict,
) -> dict:
    """
    Build the PENDING_RADAR_TRIGGER / forced_narrative object
    that would be created in the real pipeline.
    """
    team_name = entity.get("extracted_team") or match_info.get("home_team", "Unknown")

    forced_narrative = f"""🔍 [ALPHA HUNTER SIGNAL]
Source: {item.get("source", "Unknown")}
Team: {team_name}
Confidence: {max(relevance.get("confidence", 0), relevance.get("relevance_score", 0)):.0%}
Keywords: {", ".join(relevance.get("details", {}).get("alpha_confidence", {}).get("keywords_matched", [])[:3])}

Title: {item.get("title", "N/A")}

{item.get("snippet", "")[:500]}
"""

    trigger = {
        "match_id": match_info.get("id"),
        "league": match_info.get("league"),
        "home_team": match_info.get("home_team"),
        "away_team": match_info.get("away_team"),
        "team_identified": team_name,
        "entity_match": entity.get("match", False),
        "relevance_score": relevance.get("relevance_score", 0),
        "confidence": relevance.get("confidence", 0),
        "passed_threshold": relevance.get("passed", False),
        "source_url": item.get("link", "") or item.get("url", ""),
        "source_name": item.get("source", "Unknown"),
        "forced_narrative": forced_narrative,
        "status": "PENDING_RADAR_TRIGGER",
    }

    return trigger


# ============================================================================
# MAIN — Orchestrator
# ============================================================================


def main():
    print("\n" + "=" * 80)
    print("🎯 SNIPER HANDSHAKE VALIDATION (V12.6) — End-to-End Dry Run")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    report = {
        "phase1_ingestion": {"status": "PENDING"},
        "phase2_hunting": {"status": "PENDING"},
        "phase3_intelligence": {"status": "PENDING"},
        "triggers": [],
        "retry_broader": None,
    }

    # ========================================================================
    # PHASE 1: INGESTION
    # ========================================================================
    print("\n" + "=" * 80)
    print("📦 PHASE 1: INGESTION (The Target)")
    print("=" * 80)

    # Step 1: Find a real match
    print("\n  [1/3] Searching local SQLite for match in next 48h...")
    match_info = find_match_in_next_48h()

    if not match_info:
        print("  ❌ ABORT: No matches found in database. Run the bot first.")
        report["phase1_ingestion"] = {"status": "FAILED", "error": "No matches in DB"}
        _print_report(report)
        return

    team_name = match_info["home_team"]
    league_key = match_info["league"]
    print(f"  ✅ Match found: {match_info['home_team']} vs {match_info['away_team']}")
    print(f"     League: {league_key}")
    print(f"     Start:  {match_info['start_time']}")
    print(
        f"     Odds:   H={match_info['current_home_odd']} D={match_info['current_draw_odd']} A={match_info['current_away_odd']}"
    )
    print(f"     Target team: {team_name}")

    # Step 2: Fetch domains from Supabase
    print(f"\n  [2/3] Fetching news domains from Supabase for {league_key}...")
    domains = fetch_supabase_domains(league_key)
    if domains:
        print(f"  ✅ Domains: {', '.join(domains[:6])}")
    else:
        print("  ⚠️ No domains found — will use generic search (no site restriction)")

    # Step 3: Get language-specific keywords
    print(f"\n  [3/3] Detecting language and keywords for {league_key}...")
    language, native_kws, en_kws = get_language_keywords(league_key)
    print(f"  ✅ Language: {language}")
    if native_kws:
        print(f"     Native keywords: {', '.join(native_kws[:6])}")
    print(f"     English keywords: {', '.join(en_kws[:5])}")

    report["phase1_ingestion"] = {
        "status": "OK",
        "match": f"{match_info['home_team']} vs {match_info['away_team']}",
        "league": league_key,
        "language": language,
        "domains_count": len(domains),
        "native_keywords": native_kws[:5],
        "en_keywords": en_kws[:5],
    }

    # ========================================================================
    # PHASE 2: HUNTING (Real Search)
    # ========================================================================
    print("\n" + "=" * 80)
    print("🔍 PHASE 2: HUNTING (Real Search)")
    print("=" * 80)

    # Build the dork
    dork = build_targeted_dork(team_name, native_kws, en_kws, domains)
    print(f"\n  📝 Exact query sent to search engine:")
    print(f"     {dork}")

    # Execute real search
    print(f"\n  🌐 Executing REAL search (Brave → DDG → Mediastack)...")
    results = execute_real_search(dork, num_results=5)
    print(f"  📊 Results received: {len(results)}")

    if not results:
        print("\n  ⚠️ 0 results for specific team — retrying with broader query...")
        broader_dork = build_broader_dork(league_key, native_kws, en_kws, domains)
        print(f"  📝 Broader query: {broader_dork[:120]}...")
        results = execute_real_search(broader_dork, num_results=5)
        print(f"  📊 Broader results: {len(results)}")
        report["retry_broader"] = {
            "query": broader_dork[:150],
            "results": len(results),
        }

    report["phase2_hunting"] = {
        "status": "OK" if results else "NO_RESULTS",
        "query": dork[:150],
        "results_count": len(results),
    }

    # ========================================================================
    # PHASE 3: INTELLIGENCE (Relevance & Extraction)
    # ========================================================================
    print("\n" + "=" * 80)
    print("🧠 PHASE 3: INTELLIGENCE (Relevance & Extraction)")
    print("=" * 80)

    if not results:
        print("  ❌ No results to analyze.")
        report["phase3_intelligence"] = {"status": "SKIPPED", "reason": "No search results"}
        _print_report(report)
        return

    triggers = []
    for i, item in enumerate(results):
        title = item.get("title", "No title")
        snippet = (item.get("snippet", "") or item.get("summary", ""))[:120]
        url = item.get("link", "") or item.get("url", "")
        source = item.get("source", "Unknown")

        print(f"\n  ── Result {i + 1}/{len(results)} ──")
        print(f"  Title:  {title[:80]}")
        print(f"  Source: {source}")
        print(f"  URL:    {url[:80]}")
        print(f"  Snippet: {snippet}...")

        # Score relevance
        print(f"\n  📊 Scoring relevance...")
        relevance = score_relevance(item, threshold=0.7)
        rs = relevance["relevance_score"]
        conf = relevance["confidence"]
        passed = relevance["passed"]
        status_icon = "✅" if passed else "❌"
        print(f"     RelevanceScore: {rs:.3f} (NewsScorer)")
        print(f"     AlphaConfidence: {conf:.3f} (AlphaHunter)")
        print(f"     Threshold: 0.700 → {status_icon} {'PASSED' if passed else 'BELOW'}")

        if relevance.get("details", {}).get("news_scorer"):
            ns = relevance["details"]["news_scorer"]
            print(f"     Driver: {ns.get('driver', 'N/A')}")
            if ns.get("keywords"):
                print(f"     Keywords detected: {', '.join(ns['keywords'][:3])}")

        # Check entity extraction
        print(f"\n  🔎 Checking entity extraction...")
        entity = check_entity_extraction(item, team_name, league_key)
        ext_team = entity.get("extracted_team")
        entity_icon = "✅" if entity.get("match") else "❌"
        print(f"     Expected: {team_name}")
        print(f"     Extracted: {ext_team or 'NOT FOUND'}")
        print(f"     Method: {entity.get('method', 'N/A')}")
        print(f"     Entity Match: {entity_icon} {entity.get('match', False)}")

        # Build trigger
        if passed or entity.get("match"):
            trigger = build_trigger_object(match_info, item, relevance, entity)
            triggers.append(trigger)

            print(f"\n  🚨 TRIGGER CONSTRUCTION:")
            print(f"     ✅ Found relevant news for [{ext_team or team_name}] in [{league_key}]")
            print(f"     → Triggering AI Analysis for Match ID [{match_info['id']}]")
            print(f"     Status: {trigger['status']}")
            print(
                f"     Relevance: {trigger['relevance_score']:.3f} | Confidence: {trigger['confidence']:.3f}"
            )
            print(f"     forced_narrative preview:")
            narrative_preview = trigger["forced_narrative"][:200].replace("\n", "\n     ")
            print(f"     {narrative_preview}...")
        else:
            print(f"\n  ⏭️ No trigger built (relevance below threshold and no entity match)")

    report["phase3_intelligence"] = {
        "status": "OK",
        "results_analyzed": len(results),
        "triggers_built": len(triggers),
    }
    report["triggers"] = triggers

    # ========================================================================
    # SUMMARY
    # ========================================================================
    _print_report(report)


def _print_report(report: dict):
    """Print the final summary report."""
    print("\n" + "=" * 80)
    print("🏁 SNIPER HANDSHAKE VALIDATION REPORT")
    print("=" * 80)

    p1 = report.get("phase1_ingestion", {})
    p2 = report.get("phase2_hunting", {})
    p3 = report.get("phase3_intelligence", {})
    triggers = report.get("triggers", [])

    # Phase 1
    p1_icon = "✅" if p1.get("status") == "OK" else "❌"
    print(f"\n  {p1_icon} PHASE 1 — INGESTION: {p1.get('status', 'N/A')}")
    if p1.get("match"):
        print(f"     Match: {p1['match']}")
        print(f"     League: {p1.get('league', 'N/A')}")
        print(f"     Language: {p1.get('language', 'N/A')}")
        print(f"     Domains: {p1.get('domains_count', 0)}")
        if p1.get("native_keywords"):
            print(f"     Native KW: {', '.join(p1['native_keywords'][:4])}")

    # Phase 2
    p2_icon = "✅" if p2.get("results_count", 0) > 0 else "❌"
    print(f"\n  {p2_icon} PHASE 2 — HUNTING: {p2.get('status', 'N/A')}")
    print(f"     Results: {p2.get('results_count', 0)}")
    if report.get("retry_broader"):
        print(f"     Broader retry: {report['retry_broader'].get('results', 0)} results")

    # Phase 3
    p3_icon = "✅" if p3.get("triggers_built", 0) > 0 else "❌"
    print(f"\n  {p3_icon} PHASE 3 — INTELLIGENCE: {p3.get('status', 'N/A')}")
    print(f"     Analyzed: {p3.get('results_analyzed', 0)}")
    print(f"     Triggers built: {p3.get('triggers_built', 0)}")

    # Triggers
    if triggers:
        print(f"\n  🚨 TRIGGERS ({len(triggers)}):")
        for t in triggers:
            print(
                f"     [{t.get('status')}] {t.get('team_identified')} "
                f"in {t.get('league')} "
                f"| Rel: {t.get('relevance_score', 0):.2f} "
                f"| Conf: {t.get('confidence', 0):.2f} "
                f"| Match: {t.get('entity_match')}"
            )
    else:
        print("\n  📭 No triggers built — pipeline stopped before AI analysis")

    # Final verdict
    print("\n" + "-" * 80)
    if triggers:
        print("  🎯 HANDSHAKE: ✅ VALID — News found → Team matched → Trigger ready for AI")
    elif p2.get("results_count", 0) > 0:
        print("  🎯 HANDSHAKE: ⚠️ PARTIAL — Results found but none passed relevance threshold")
    elif p1.get("status") == "OK":
        print("  🎯 HANDSHAKE: ❌ BROKEN — Match found but search returned 0 results")
    else:
        print("  🎯 HANDSHAKE: ❌ FAILED — Could not find a match to test")

    print("=" * 80)


if __name__ == "__main__":
    main()
