"""
EarlyBird Analysis Engine
========================

This module acts as the "brain" of the EarlyBird system, orchestrating
all match-level analysis and AI triangulation logic.

Extracted from src/main.py as part of the modular refactoring initiative.
This module understands match context and coordinates intelligence gathering
from multiple sources.

Historical Version: V1.0

Author: Refactored by Lead Architect
Date: 2026-02-09
Updated: 2026-02-23 (Centralized Version Tracking)
"""

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any

# Import centralized version tracking
from src.version import get_version_with_module

# Log version on import
logger = logging.getLogger(__name__)
logger.info(f"📦 {get_version_with_module('Analysis Engine')}")

# Configuration
from config.settings import (
    ALERT_THRESHOLD_HIGH,
    ALERT_THRESHOLD_RADAR,
    BISCOTTO_EXTREME_LOW,
    BISCOTTO_SIGNIFICANT_DROP,
    BISCOTTO_SUSPICIOUS_LOW,
)

# Analysis engines
from src.analysis.analyzer import analyze_with_triangulation
from src.analysis.fatigue_engine import get_enhanced_fatigue_context
from src.analysis.injury_impact_engine import TeamInjuryImpact, analyze_match_injuries
from src.analysis.market_intelligence import analyze_market_intelligence
from src.analysis.verification_layer import (
    RefereeStats,
    VerificationResult,
    VerificationStatus,
    create_verification_request_from_match,
    should_verify_alert,
    verify_alert,
)
from src.analysis.verifier_integration import (
    build_alert_data_for_verifier,
    build_context_data_for_verifier,
    verify_alert_before_telegram,
)

# V11.1 FIX: Import BettingQuant for market warning generation
from src.core.betting_quant import BettingQuant

# Import intelligent error tracking from orchestration_metrics
try:
    from src.alerting.orchestration_metrics import record_error_intelligent

    ERROR_TRACKING_AVAILABLE = True
except ImportError:
    ERROR_TRACKING_AVAILABLE = False
    record_error_intelligent = None

# Database
from src.database.models import Match, NewsLog, SessionLocal

# Data providers
from src.ingestion.fotmob_team_mapping import get_fotmob_team_id
from src.ingestion.weather_provider import get_match_weather

# Processing
from src.processing.news_hunter import run_hunter_for_match

# V12.0: Import ValidationResult validators for defense-in-depth validation
try:
    from src.utils.validators import ValidationResult, validate_news_log

    _VALIDATORS_AVAILABLE = True
except ImportError:
    _VALIDATORS_AVAILABLE = False
    logging.debug("Validators module not available for analysis_engine")

# Configure logger
logger = logging.getLogger(__name__)

# ============================================
# ANALYSIS-SPECIFIC CONSTANTS
# ============================================
# These constants are specific to the analysis engine and are defined
# locally to avoid polluting config/settings.py

CASE_CLOSED_COOLDOWN_HOURS = 6  # Hours to wait before re-investigating
FINAL_CHECK_WINDOW_HOURS = 2  # Hours before kickoff when cooldown is ignored

# ============================================
# OPTIONAL IMPORTS (with graceful handling)
# ============================================

# Twitter Intel Cache V4.5
try:
    from src.services.twitter_intel_cache import get_twitter_intel_cache

    _TWITTER_INTEL_AVAILABLE = True
    logger.debug("✅ Twitter Intel Cache loaded")
except ImportError:
    _TWITTER_INTEL_AVAILABLE = False
    logger.debug("⚠️ Twitter Intel Cache not available")

# Tweet Relevance Filter V4.6
try:
    from src.services.tweet_relevance_filter import (
        filter_tweets_for_match,
        resolve_conflict_via_gemini,
    )

    _TWEET_FILTER_AVAILABLE = True
    logger.debug("✅ Tweet Relevance Filter loaded")
except ImportError:
    _TWEET_FILTER_AVAILABLE = False
    logger.debug("⚠️ Tweet Relevance Filter not available")

# Parallel Enrichment V6.0
try:
    from src.utils.parallel_enrichment import EnrichmentResult, enrich_match_parallel

    _PARALLEL_ENRICHMENT_AVAILABLE = True
    logger.debug("✅ Parallel Enrichment loaded")
except ImportError:
    _PARALLEL_ENRICHMENT_AVAILABLE = False
    logger.debug("⚠️ Parallel Enrichment not available")


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
# ANALYSIS ENGINE CLASS
# ============================================


class AnalysisEngine:
    """
    The Analysis Engine orchestrates all match-level analysis logic.

    This class acts as the "brain" that understands match context,
    coordinates intelligence gathering from multiple sources, and
    performs AI triangulation to generate betting insights.
    """

    def __init__(self):
        """Initialize the Analysis Engine."""
        self.logger = logger
        self._availability_flags = {
            "twitter_intel": _TWITTER_INTEL_AVAILABLE,
            "tweet_filter": _TWEET_FILTER_AVAILABLE,
            "parallel_enrichment": _PARALLEL_ENRICHMENT_AVAILABLE,
        }

        # V11.1 FIX: Initialize BettingQuant for market warning generation
        self.betting_quant = BettingQuant()

    def get_availability_flags(self) -> dict[str, bool]:
        """Get availability flags for optional components."""
        return self._availability_flags.copy()

    # ============================================
    # LEAGUE CLASSIFICATION
    # ============================================

    @staticmethod
    def is_intelligence_only_league(league_key: str) -> bool:
        """
        Check if a league is Intelligence-Only (no odds available).

        Args:
            league_key: League identifier

        Returns:
            True if league is intelligence-only, False otherwise
        """
        if not league_key:
            return False
        # Check exact match or partial match for Africa-related leagues
        if league_key in INTELLIGENCE_ONLY_LEAGUES:
            return True
        if "africa" in league_key.lower() or "egypt" in league_key.lower():
            return True
        return False

    # ============================================
    # CASE CLOSED COOLDOWN
    # ============================================

    @staticmethod
    def is_case_closed(match: Match, now: datetime) -> tuple[bool, str]:
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
        last_deep_dive_time = getattr(match, "last_deep_dive_time", None)
        start_time = getattr(match, "start_time", None)

        # No previous investigation - case is open
        if not last_deep_dive_time:
            return False, "First investigation"

        # Calculate time since last investigation
        hours_since_dive = (now - last_deep_dive_time).total_seconds() / 3600

        # Calculate time to kickoff
        hours_to_kickoff = (start_time - now).total_seconds() / 3600

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

    # ============================================
    # BISCOTTO DETECTION
    # ============================================

    @staticmethod
    def is_biscotto_suspect(match: Match) -> dict[str, Any]:
        """
        🍪 BISCOTTO DETECTION: Check if Draw odds indicate a "mutually beneficial draw".

        V6.1: Added edge case protection for invalid odds values.
        V13.0: MIGRATED to Advanced Biscotto Engine V2.0 with multi-factor analysis

        Args:
            match: Match object with current_draw_odd and opening_draw_odd

        Returns:
            dict with 'is_suspect', 'reason', 'draw_odd', 'drop_pct', 'severity',
                 'confidence', 'factors', 'pattern', 'zscore', 'mutual_benefit', 'betting_recommendation'
        """
        # Try to use advanced biscotto engine if available
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

            except Exception:
                # If motivation data fetch fails, continue without it (advanced engine has fallbacks)
                pass

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

        except Exception:
            # If advanced engine fails, fall back to legacy implementation
            pass

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
        current_draw_odd = getattr(match, "current_draw_odd", None)
        opening_draw_odd = getattr(match, "opening_draw_odd", None)

        draw_odd = current_draw_odd
        opening_draw = opening_draw_odd

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
            result["reason"] = (
                f"🍪 SUSPICIOUS: Draw @ {draw_odd:.2f} (below {BISCOTTO_SUSPICIOUS_LOW})"
            )
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

    @staticmethod
    def check_biscotto_suspects() -> list[dict[str, Any]]:
        """
        Scan for Biscotto suspects (suspicious Draw odds).

        This function identifies matches with unusually low Draw odds
        that may indicate a "mutually beneficial draw" scenario.

        Returns:
            List of suspect match dictionaries
        """
        db = SessionLocal()
        try:
            # Get all matches with draw odds data
            matches = (
                db.query(Match)
                .filter(
                    Match.start_time > datetime.now(timezone.utc),
                    Match.current_draw_odd.isnot(None),
                )
                .all()
            )

            suspects = []

            for match in matches:
                result = AnalysisEngine.is_biscotto_suspect(match)
                if result["is_suspect"]:
                    suspects.append(
                        {
                            "match": match,
                            "severity": result["severity"],
                            "reason": result["reason"],
                            "draw_odd": result["draw_odd"],
                            "drop_pct": result["drop_pct"],
                            # Enhanced fields from Advanced Biscotto Engine V2.0
                            "confidence": result.get("confidence", 0),
                            "factors": result.get("factors", []),
                            "pattern": result.get("pattern", "STABLE"),
                            "zscore": result.get("zscore", 0.0),
                            "mutual_benefit": result.get("mutual_benefit", False),
                            "betting_recommendation": result.get("betting_recommendation", "AVOID"),
                        }
                    )

            if suspects:
                logger.info(f"🍪 Found {len(suspects)} Biscotto suspects")
                for suspect in suspects:
                    match = suspect["match"]
                    logger.info(
                        f"   🍪 {match.home_team} vs {match.away_team}: {suspect['reason']}"
                    )

            return suspects

        finally:
            db.close()

    # ============================================
    # ODDS DROP DETECTION
    # ============================================

    @staticmethod
    def check_odds_drops() -> list[dict[str, Any]]:
        """
        Check for significant odds movements in the database.

        This function scans all matches in the database and identifies
        significant odds drops that may indicate market movement or
        insider information.

        VPS FIX: Extract Match attributes safely to prevent session detachment.
        This prevents "Trust validation error" when Match object becomes detached
        from session due to connection pool recycling under high load.

        Returns:
            List of significant drop dictionaries
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
                # VPS FIX: Extract Match attributes safely to prevent session detachment
                # This prevents "Trust validation error" when Match object becomes detached
                # from session due to connection pool recycling under high load
                home_team = getattr(match, "home_team", "Unknown")
                away_team = getattr(match, "away_team", "Unknown")
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
                logger.info(f"💹 Found {len(significant_drops)} significant odds drops")
                for drop in significant_drops:
                    match = drop["match"]
                    # Extract team names safely
                    home_team = getattr(match, "home_team", "Unknown")
                    away_team = getattr(match, "away_team", "Unknown")
                    logger.info(
                        f"   📉 {home_team} vs {away_team}: {drop['type']} {drop['drop_pct']:.1f}% ({drop['opening']:.2f} → {drop['current']:.2f})"
                    )

            return significant_drops

        finally:
            db.close()

    # ============================================
    # TWITTER INTEL HELPERS
    # ============================================

    def get_twitter_intel_for_match(
        self, match: Match, context_label: str = ""
    ) -> dict[str, Any] | None:
        """
        Get Twitter Intel data for a match from cache.

        Centralizes the Twitter Intel enrichment logic to avoid duplication.

        VPS FIX: Extract Match attributes safely to prevent session detachment.
        This prevents "Trust validation error" when Match object becomes detached
        from session due to connection pool recycling under high load.

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

            # VPS FIX: Extract Match attributes safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", "Unknown")
            away_team = getattr(match, "away_team", "Unknown")
            league = getattr(match, "league", "Unknown")

            # V15.0: Get enriched team data from TeamAlias for enhanced context
            home_alias_data = None
            away_alias_data = None
            try:
                from src.database.team_alias_utils import get_match_alias_data

                home_alias_data, away_alias_data = get_match_alias_data(home_team, away_team)

                if home_alias_data:
                    self.logger.debug(
                        f"🏆 [TEAMALIAS] Home team enriched: {home_team} "
                        f"(country={home_alias_data.get('country')}, "
                        f"league={home_alias_data.get('league')})"
                    )

                if away_alias_data:
                    self.logger.debug(
                        f"🏆 [TEAMALIAS] Away team enriched: {away_team} "
                        f"(country={away_alias_data.get('country')}, "
                        f"league={away_alias_data.get('league')})"
                    )
            except ImportError:
                self.logger.debug("⚠️ [TEAMALIAS] team_alias_utils not available")
            except Exception as e:
                self.logger.debug(f"⚠️ [TEAMALIAS] Failed to get TeamAlias data: {e}")

            # Search for relevant tweets about both teams
            relevant_tweets = []
            for team in [home_team, away_team]:
                tweets = cache.search_intel(
                    team, league_key=league, topics=["injury", "lineup", "squad"]
                )
                # V13.1: Add relevance score to each tweet
                for tweet in tweets:
                    relevance = self._calculate_tweet_relevance(tweet, team)
                    relevant_tweets.append({"tweet": tweet, "relevance": relevance, "team": team})

            if not relevant_tweets:
                return None

            # V13.1: Sort by relevance (high > medium > low > none)
            relevance_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
            relevant_tweets.sort(key=lambda x: relevance_order.get(x["relevance"], 3))

            # Take top 5 most relevant tweets (was 3, now 5 for better intelligence)
            twitter_intel_data = {
                "tweets": [
                    {
                        "handle": item["tweet"].handle,
                        "content": item["tweet"].content[:150],  # Truncate for display
                        "topics": item["tweet"].topics,
                    }
                    for item in relevant_tweets[:5]
                ],
                "cache_age_minutes": cache.cache_age_minutes,
            }

            label = f"[{context_label}] " if context_label else ""
            self.logger.info(
                f"   🐦 {label}Twitter Intel: {len(relevant_tweets)} relevant tweets found (top 5 by relevance)"
            )
            return twitter_intel_data

        except Exception as e:
            self.logger.debug(f"Twitter Intel enrichment failed: {e}")
            return None

    def _calculate_tweet_relevance(self, tweet, team: str) -> str:
        """
        V13.1: Calculate relevance of a tweet for a team.

        Args:
            tweet: CachedTweet object
            team: Team name to check relevance for

        Returns:
            Relevance level: "high", "medium", or "low"
        """
        content_lower = tweet.content.lower()
        team_lower = team.lower()

        # HIGH: mentions team + critical topic (injury, lineup, squad)
        if team_lower in content_lower:
            if any(t in tweet.topics for t in ["injury", "lineup", "squad"]):
                return "high"
            return "medium"

        # MEDIUM: related topic
        if any(t in tweet.topics for t in ["injury", "lineup", "transfer"]):
            return "medium"

        # LOW: generic
        return "low"

    def get_twitter_intel_for_ai(
        self, match: Match, official_data: str = "", context_label: str = ""
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
            # VPS FIX: Extract Match attributes safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", "Unknown")
            away_team = getattr(match, "away_team", "Unknown")
            league = getattr(match, "league", "Unknown")

            result = filter_tweets_for_match(
                home_team=home_team,
                away_team=away_team,
                league_key=league,
                fotmob_data=official_data,
            )

            if not result.tweets:
                return ""

            label = f"[{context_label}] " if context_label else ""
            self.logger.info(
                f"   🐦 {label}Twitter Intel for AI: {len(result.tweets)} tweets selected"
            )

            # V13.0: If conflicts detected, resolve via IntelligenceRouter (DeepSeek)
            ai_resolution = None
            if result.has_conflicts and result.conflict_description:
                self.logger.warning(
                    f"   ⚠️ Twitter/FotMob conflict detected: {result.conflict_description}"
                )

                # Extract Twitter claim from first conflicting tweet
                twitter_claim = result.tweets[0].content if result.tweets else "Unknown"

                # Call IntelligenceRouter to resolve conflict (DeepSeek → Tavily → Claude fallback)
                ai_resolution = resolve_conflict_via_gemini(
                    conflict_description=result.conflict_description,
                    home_team=home_team,
                    away_team=away_team,
                    twitter_claim=twitter_claim,
                    fotmob_claim=official_data[:500] if official_data else "No FotMob data",
                )

                if ai_resolution:
                    status = ai_resolution.get("verification_status", "UNKNOWN")
                    confidence = ai_resolution.get("confidence_level", "LOW")
                    self.logger.info(
                        f"   🔍 AI conflict resolution: {status} (confidence: {confidence})"
                    )

                    # Append resolution to formatted output
                    resolution_text = self._format_conflict_resolution(ai_resolution)
                    if resolution_text:
                        return f"{result.formatted_for_ai}\n\n{resolution_text}"

            return result.formatted_for_ai

        except Exception as e:
            self.logger.debug(f"Twitter Intel for AI failed: {e}")
            return ""

    @staticmethod
    def _format_conflict_resolution(resolution: dict[str, Any]) -> str:
        """
        Format AI conflict resolution for AI prompt.

        V13.0 FIX: Renamed from _format_gemini_resolution() to reflect that
        the system now uses IntelligenceRouter (DeepSeek → Tavily → Claude 3 Haiku)
        instead of the deprecated Gemini direct API.

        Args:
            resolution: Dict with verification_status, confidence_level, additional_context

        Returns:
            Formatted string for AI prompt
        """
        if not resolution:
            return ""

        status = resolution.get("verification_status", "UNKNOWN")
        confidence = resolution.get("confidence_level", "LOW")
        additional = resolution.get("additional_context", "")

        lines = ["[🔍 AI CONFLICT RESOLUTION]"]
        lines.append(f"Status: {status} (Confidence: {confidence})")

        if status == "CONFIRMED":
            lines.append("✅ Twitter claim VERIFIED by AI analysis")
        elif status == "DENIED":
            lines.append("❌ Twitter claim DENIED - FotMob data is correct")
        elif status == "OUTDATED":
            lines.append("⚠️ Twitter info is OUTDATED - use FotMob")
        else:
            lines.append("❓ UNVERIFIED - treat with caution, reduce confidence")

        if additional and additional != "Unknown":
            lines.append(f"Additional context: {additional[:200]}")

        return "\n".join(lines)

    # Legacy alias for backward compatibility
    _format_gemini_resolution = _format_conflict_resolution

    # ============================================
    # TACTICAL INJURY PROFILE
    # ============================================

    @staticmethod
    def format_tactical_injury_profile(
        team_name: str, team_context: dict[str, Any], injury_impact: TeamInjuryImpact | None = None
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
        if not team_context or not team_context.get("injuries"):
            return ""

        injuries = team_context.get("injuries", [])
        if not injuries:
            return ""

        # Build player details with tactical metadata
        player_details = []

        if injury_impact and injury_impact.players:
            # Use detailed player data from injury_impact_engine
            for player in injury_impact.players:
                pos = (
                    player.position.value.capitalize()
                    if hasattr(player.position, "value")
                    else "Unknown"
                )
                role = (
                    player.role.value.capitalize() if hasattr(player.role, "value") else "Unknown"
                )
                name = player.name

                # Format: "Forward - Player X - Starter"
                player_details.append(f"{pos} - {name} - {role}")
        else:
            # Fallback: just use names from injuries list
            for injury in injuries[:5]:  # Limit to 5 players
                name = injury.get("name", "Unknown")
                if name and name != "Unknown":
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
    # PARALLEL ENRICHMENT
    # ============================================

    def run_parallel_enrichment(
        self, fotmob, home_team: str, away_team: str, match_start_time=None, weather_provider=None
    ) -> dict[str, Any] | None:
        """
        Run parallel FotMob enrichment and return results in legacy format.

        This helper bridges the new parallel enrichment module with the existing
        code, converting EnrichmentResult to the dict format expected
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
                           weather_impact, tactical, enrichment_time_ms, failed_calls,
                           successful_calls, error_details
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
                # max_workers=4,  # REMOVED - use default (1) to avoid FotMob 403 errors (V6.2 fix)
                timeout=90,  # UPDATED from 45 to 90 for retries and backoff (COVE fix V6.3)
            )

            # Convert EnrichmentResult to legacy dict format
            return {
                "home_context": result.home_context or {},
                "away_context": result.away_context or {},
                "home_turnover": result.home_turnover,
                "away_turnover": result.away_turnover,
                "referee_info": result.referee_info,
                "stadium_coords": result.stadium_coords,
                "home_stats": result.home_stats or {},
                "away_stats": result.away_stats or {},
                "weather_impact": result.weather_impact,
                "tactical": result.tactical or {},
                "enrichment_time_ms": result.enrichment_time_ms,
                "failed_calls": result.failed_calls,
                "successful_calls": result.successful_calls,
                "error_details": result.error_details,  # Added for VPS debugging
            }
        except Exception as e:
            self.logger.warning(f"⚠️ Parallel enrichment failed: {e}, falling back to sequential")
            return None

    # ============================================
    # VERIFICATION LAYER
    # ============================================

    def run_verification_check(
        self,
        match: Match,
        analysis: NewsLog,
        home_stats: dict[str, Any] | None = None,
        away_stats: dict[str, Any] | None = None,
        home_context: dict[str, Any] | None = None,
        away_context: dict[str, Any] | None = None,
        context_label: str = "",
        home_team_injury_impact: Any = None,
        away_team_injury_impact: Any = None,
    ) -> tuple[bool, float, str | None, VerificationResult | None]:
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
            home_team_injury_impact: Optional TeamInjuryImpact with detailed player data
            away_team_injury_impact: Optional TeamInjuryImpact with detailed player data

        Returns:
            Tuple of (should_send, adjusted_score, adjusted_market, verification_result)
            - should_send: True if alert should be sent (CONFIRM or CHANGE_MARKET)
            - adjusted_score: Score after verification adjustments
            - adjusted_market: Market to use (may be changed by verification)
            - verification_result: Full VerificationResult object for logging

        Requirements: 7.1, 7.2, 7.3
        """
        try:
            # Initialize label early to prevent UnboundLocalError
            label = f"[{context_label}] " if context_label else ""

            # Check if verification is needed for this alert
            # COVE FIX: should_verify_alert() only accepts 1 argument (preliminary_score: float)
            # Removed analysis.recommended_market parameter to fix TypeError
            if not should_verify_alert(analysis.score):
                return True, analysis.score, analysis.recommended_market, None

            # Create verification request
            request = create_verification_request_from_match(
                match=match,
                analysis=analysis,
                home_stats=home_stats,
                away_stats=away_stats,
                home_context=home_context,
                away_context=away_context,
                home_team_injury_impact=home_team_injury_impact,
                away_team_injury_impact=away_team_injury_impact,
            )

            # Run verification
            result = verify_alert(request)

            if result.status == VerificationStatus.CONFIRM:
                self.logger.info(f"✅ {label}Alert CONFIRMED by Verification Layer")
                return True, result.adjusted_score, result.original_market, result
            elif result.status == VerificationStatus.CHANGE_MARKET:
                self.logger.info(
                    f"🔄 {label}Verification Layer changed market from {analysis.recommended_market} to {result.recommended_market}"
                )
                return True, result.adjusted_score, result.recommended_market, result
            elif result.status == VerificationStatus.REJECT:
                self.logger.warning(
                    f"❌ {label}Alert DENIED by Verification Layer: {result.rejection_reason}"
                )
                return False, result.adjusted_score, result.recommended_market, result

        except Exception as e:
            self.logger.error(f"❌ {label}Verification Layer error: {e}")
            # On error, allow alert to proceed with original data
            return True, analysis.score, getattr(analysis, "recommended_market", None), None

    # ============================================
    # MAIN MATCH ANALYSIS
    # ============================================

    def analyze_match(
        self,
        match: Match,
        fotmob,
        now_utc: datetime,
        db_session,
        context_label: str = "TIER1",
        nitter_intel: str | None = None,
        forced_narrative: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform complete match analysis with AI triangulation.

        This is the main analysis orchestration function that:
        1. Validates team order using FotMob
        2. Checks case closed cooldown
        3. Runs parallel enrichment
        4. Performs tactical analysis (injury impact)
        5. Performs fatigue analysis
        6. Detects biscotto scenarios
        7. Analyzes market intelligence
        8. Hunts for news articles (SKIP if forced_narrative present)
        9. Gathers Twitter intel
        10. Runs AI triangulation analysis
        11. Verifies alert before sending
        12. Sends alert if threshold met

        BYPASS RULE (RADAR TRIGGER):
        - If forced_narrative is present: SKIP Tavily/Brave searches
        - Trust the Radar's intel and use forced_narrative as primary news source
        - This saves API quota and prevents redundant searches

        Args:
            match: Match database object
            fotmob: FotMob provider instance
            now_utc: Current UTC time
            db_session: Database session for updates
            context_label: Label for logging (e.g., "TIER1", "TIER2", "RADAR")
            nitter_intel: Optional Nitter intel string
            forced_narrative: Optional forced narrative from News Radar (bypasses news hunting)

        Returns:
            Dict with analysis results including:
            - alert_sent: Whether an alert was sent
            - score: Final analysis score
            - market: Recommended market
            - error: Any error that occurred
        """
        result = {"alert_sent": False, "score": 0.0, "market": None, "error": None, "news_count": 0}

        try:
            # VPS FIX: Extract Match attributes safely to prevent session detachment.
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load.
            home_team = getattr(match, "home_team", "Unknown")
            away_team = getattr(match, "away_team", "Unknown")
            league = getattr(match, "league", "Unknown")
            start_time = getattr(match, "start_time", None)

            # --- STEP 0z: ODDS AVAILABILITY CHECK (V14.1) ---
            # V14.1 FIX: Defensive check to prevent "No Odds Black Hole" silent drops
            # This is a defense-in-depth measure. The primary fix is in the database queries
            # in main.py that filter out matches without odds BEFORE calling analyze_match.
            # This check handles the case where analyze_match is called directly.
            current_home_odd = getattr(match, "current_home_odd", None)
            if current_home_odd is None:
                self.logger.info(
                    f"⏭️  Skipping {home_team} vs {away_team}: No odds available (current_home_odd is None)"
                )
                return result

            # --- STEP 0a: HOME/AWAY VALIDATION \(V5.1\) ---
            # Validate home/away order using FotMob as source of truth
            # This prevents alerts with inverted team order (e.g., "FC Porto vs Santa Clara"
            # when the actual match is "Santa Clara vs FC Porto")

            home_team_valid = home_team
            away_team_valid = away_team

            if fotmob:
                try:
                    # Get FotMob team IDs for validation
                    fotmob_home_id = get_fotmob_team_id(home_team)
                    fotmob_away_id = get_fotmob_team_id(away_team)

                    # If we have both IDs, validate the order
                    if fotmob_home_id and fotmob_away_id:
                        # Get FotMob match data to validate order
                        fotmob_match = fotmob.get_match(fotmob_home_id, fotmob_away_id, start_time)

                        if fotmob_match:
                            # Check if FotMob has the teams in the same order
                            fotmob_home_name = fotmob_match.get("home", {}).get("name", "")
                            fotmob_away_name = fotmob_match.get("away", {}).get("name", "")

                            # If FotMob has different order, swap our teams
                            if (
                                fotmob_home_name
                                and fotmob_away_name
                                and home_team != fotmob_home_name
                            ):
                                self.logger.warning(
                                    f"⚠️ Team order mismatch detected: DB has {home_team} vs {away_team}, FotMob has {fotmob_home_name} vs {fotmob_away_name}"
                                )
                                # Swap team names
                                home_team_valid, away_team_valid = away_team_valid, home_team_valid
                                self.logger.info(
                                    f"✅ Corrected team order to: {home_team_valid} vs {away_team_valid}"
                                )
                except Exception as e:
                    self.logger.debug(f"Team order validation skipped: {e}")

            # --- STEP 0b: CASE CLOSED COOLDOWN CHECK (V6.0) ---
            # Skip analysis if match is on cooldown (already investigated recently)
            is_closed, cooldown_reason = self.is_case_closed(match, now_utc)
            if is_closed:
                self.logger.info(f"⏸️  Skipping {home_team} vs {away_team}: {cooldown_reason}")
                return result

            # --- STEP 1: PARALLEL ENRICHMENT (V6.0) ---
            # Fetch all FotMob data in parallel for performance
            self.logger.info(
                f"\n🔍 Investigating {home_team_valid} vs {away_team_valid} ({match.league})..."
            )

            # V11.0 TURBO: Parallel fetch for FotMob, News, and Twitter intel
            # Use ThreadPoolExecutor to run I/O-bound operations concurrently
            from concurrent.futures import ThreadPoolExecutor

            enrichment_data = None
            news_articles = []
            twitter_intel = ""

            def fetch_fotmob():
                if _PARALLEL_ENRICHMENT_AVAILABLE and fotmob:
                    return self.run_parallel_enrichment(
                        fotmob=fotmob,
                        home_team=home_team_valid,
                        away_team=away_team_valid,
                        match_start_time=start_time,
                        weather_provider=get_match_weather,
                    )
                return None

            def fetch_news():
                # BYPASS RULE: Skip if forced_narrative is present (Radar Trigger)
                if forced_narrative:
                    return [{"title": "RADAR INTEL", "snippet": forced_narrative, "url": None}]
                try:
                    return run_hunter_for_match(match=match, include_insiders=True)
                except Exception as e:
                    self.logger.warning(f"⚠️ News hunting failed: {e}")
                    return []

            def fetch_twitter():
                return self.get_twitter_intel_for_match(match, context_label=context_label)

            # Execute all three fetches in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                fotmob_future = executor.submit(fetch_fotmob)
                news_future = executor.submit(fetch_news)
                twitter_future = executor.submit(fetch_twitter)

                # Wait for all futures to complete
                enrichment_data = fotmob_future.result()
                news_articles = news_future.result()
                twitter_intel = twitter_future.result()

            self.logger.info(f"   📰 Found {len(news_articles)} relevant news articles")

            # Extract enrichment results
            home_context = enrichment_data.get("home_context", {}) if enrichment_data else {}
            away_context = enrichment_data.get("away_context", {}) if enrichment_data else {}
            home_stats = enrichment_data.get("home_stats", {}) if enrichment_data else {}
            away_stats = enrichment_data.get("away_stats", {}) if enrichment_data else {}

            # Convert referee_info dict to RefereeStats object
            referee_dict = enrichment_data.get("referee_info") if enrichment_data else None
            referee_info = None
            if referee_dict and isinstance(referee_dict, dict):
                try:
                    referee_info = RefereeStats(
                        name=referee_dict.get("name", "Unknown"),
                        cards_per_game=referee_dict.get("cards_per_game", 0.0) or 0.0,
                        strictness=referee_dict.get("strictness", "unknown"),
                        matches_officiated=referee_dict.get("matches_officiated", 0),
                    )
                    logger.debug(f"✅ Converted referee dict to RefereeStats: {referee_info.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to convert referee dict to RefereeStats: {e}")
                    referee_info = None

            # --- STEP 2: TACTICAL ANALYSIS (V8.0) ---
            # Analyze injuries with tactical intelligence

            injury_differential = None
            home_injury_impact = None
            away_injury_impact = None

            try:
                injury_differential = analyze_match_injuries(
                    home_team=home_team_valid,
                    away_team=away_team_valid,
                    home_context=home_context,
                    away_context=away_context,
                )
                # Extract individual impacts from InjuryDifferential object
                if injury_differential:
                    home_injury_impact = injury_differential.home_impact
                    away_injury_impact = injury_differential.away_impact
            except Exception as e:
                self.logger.warning(f"⚠️ Injury impact analysis failed: {e}")

            # --- STEP 3: FATIGUE ANALYSIS (V2.0) ---
            # Analyze fatigue differential between teams

            fatigue_differential = None
            if home_stats and away_stats:
                try:
                    fatigue_differential, fatigue_context_str = get_enhanced_fatigue_context(
                        home_team=home_team_valid,
                        away_team=away_team_valid,
                        home_context=home_context,
                        away_context=away_context,
                    )
                except Exception as e:
                    self.logger.warning(f"⚠️ Fatigue analysis failed: {e}")

            # --- STEP 4: BISCOTTO DETECTION (V2.0) ---
            # Check for suspicious Draw odds

            biscotto_result = self.is_biscotto_suspect(match)
            if biscotto_result["is_suspect"]:
                self.logger.info(f"   🍪 {biscotto_result['reason']}")

            # --- STEP 5: MARKET INTELLIGENCE (V2.0) ---
            # Analyze market movements (Steam Move, Reverse Line, News Decay)

            market_intel = None
            try:
                market_intel = analyze_market_intelligence(match=match, league_key=league)
            except Exception as e:
                self.logger.warning(f"⚠️ Market intelligence analysis failed: {e}")

            # Track news count for health monitoring
            result["news_count"] = len(news_articles)

            # V11.0 TURBO: NOTE - STEP 6 (News) and STEP 7 (Twitter) are now executed
            # in parallel with FotMob enrichment via ThreadPoolExecutor above

            # --- STEP 8: AI ANALYSIS (V6.0) ---
            # Run triangulation analysis with all available data

            try:
                # Format injury data for AI
                home_injury_str = self.format_tactical_injury_profile(
                    home_team_valid, home_context, home_injury_impact
                )
                away_injury_str = self.format_tactical_injury_profile(
                    away_team_valid, away_context, away_injury_impact
                )

                # Format Twitter intel for AI
                # V10.5: Add Nitter intel to narrative if available
                narrative_parts = []
                if nitter_intel:
                    narrative_parts.append(f"{nitter_intel}\n")
                narrative_parts.append(f"Home: {home_injury_str}\nAway: {away_injury_str}")
                twitter_intel_str = self.get_twitter_intel_for_ai(
                    match,
                    official_data="".join(narrative_parts),
                    context_label=context_label,
                )

                # Run triangulation analysis
                analysis_result = analyze_with_triangulation(
                    match=match,
                    home_context=home_context,
                    away_context=away_context,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    news_articles=news_articles,
                    twitter_intel=twitter_intel,
                    twitter_intel_for_ai=twitter_intel_str,
                    fatigue_differential=fatigue_differential,
                    injury_impact_home=home_injury_impact,
                    injury_impact_away=away_injury_impact,
                    biscotto_result=biscotto_result,
                    market_intel=market_intel,
                    referee_info=referee_info,
                )

                # COVE DEBUG: AI Response trace
                if forced_narrative and analysis_result:
                    self.logger.info(
                        f"🧠 [DEBUG] AI Response: Summary={getattr(analysis_result, 'summary', 'N/A')[:100]}..."
                    )
                    self.logger.info(
                        f"🧠 [DEBUG] AI Response: Confidence={getattr(analysis_result, 'confidence', 'N/A')}, "
                        f"Recommended Market={getattr(analysis_result, 'recommended_market', 'N/A')}"
                    )

                # --- V12.0: Validate analysis_result with ValidationResult ---
                # Defense-in-depth validation layer (complementary to Contract validation)
                if _VALIDATORS_AVAILABLE and analysis_result:
                    try:
                        validation = validate_news_log(analysis_result)
                        if not validation.is_valid:
                            self.logger.warning(
                                f"⚠️ V12.0: NewsLog validation failed: {validation.errors}"
                            )
                            # Log warnings but don't block - let verification layer decide
                        if validation.warnings:
                            for warning in validation.warnings:
                                self.logger.debug(f"V12.0 Validation warning: {warning}")
                    except Exception as e:
                        self.logger.debug(f"V12.0: Validation check failed (non-critical): {e}")

                # --- V11.1 FIX: Generate market warning using BettingQuant ---
                market_warning = None
                if analysis_result and match:
                    try:
                        # Extract team stats for BettingQuant
                        # Use goals_avg from stats, fallback to league default (1.35)
                        home_scored = home_stats.get("goals_avg") if home_stats else 1.35
                        away_scored = away_stats.get("goals_avg") if away_stats else 1.35

                        # FotMob doesn't provide goals_conceded_avg, use goals_avg as fallback
                        home_conceded = home_stats.get("goals_avg") if home_stats else 1.35
                        away_conceded = away_stats.get("goals_avg") if away_stats else 1.35

                        # VPS FIX: Copy odds attributes before using them to prevent session detachment
                        # This prevents "Trust validation error" when Match object becomes detached
                        # from session due to connection pool recycling under high load
                        home_odd = getattr(match, "current_home_odd", None)
                        draw_odd = getattr(match, "current_draw_odd", None)
                        away_odd = getattr(match, "current_away_odd", None)
                        over_25_odd = getattr(match, "current_over_2_5", None)
                        under_25_odd = getattr(match, "current_under_2_5", None)
                        btts_yes_odd = getattr(match, "current_btts_yes", None)  # V12.7: BTTS odds

                        # Build market odds dict from copied attributes
                        market_odds = {
                            "home": home_odd,
                            "draw": draw_odd,
                            "away": away_odd,
                            "over_25": over_25_odd,
                            "under_25": under_25_odd,
                            "btts": btts_yes_odd,  # V12.7: BTTS odds now available from DB
                        }

                        # Call BettingQuant to evaluate bet and generate market warning
                        betting_decision = self.betting_quant.evaluate_bet(
                            match=match,
                            analysis=analysis_result,
                            home_scored=home_scored,
                            home_conceded=home_conceded,
                            away_scored=away_scored,
                            away_conceded=away_conceded,
                            market_odds=market_odds,
                            ai_prob=analysis_result.confidence / 100.0
                            if analysis_result.confidence
                            else None,
                        )

                        # COVE DEBUG: Mathematical Decision trace
                        if forced_narrative:
                            self.logger.info(
                                f"💰 [DEBUG] Mathematical Decision: Verdict={betting_decision.verdict}, "
                                f"Stake={getattr(betting_decision, 'stake', 'N/A')}, "
                                f"Market={getattr(betting_decision, 'market', 'N/A')}"
                            )
                            self.logger.info(
                                f"💰 [DEBUG] Betting Decision details: {betting_decision}"
                            )

                        # Extract market warning from BettingDecision
                        market_warning = betting_decision.market_warning

                        if market_warning:
                            self.logger.info(f"⚠️ V11.1: Market warning generated: {market_warning}")

                    except Exception as e:
                        self.logger.warning(
                            f"⚠️ V11.1: Failed to generate market warning with BettingQuant: {e}"
                        )
                        # Continue without market warning (non-critical)
                        market_warning = None

                # --- V8.3 FIX: Save analysis_result to database BEFORE sending alert ---
                # This creates the NewsLog record with all analysis data
                if analysis_result:
                    try:
                        db_session.add(analysis_result)
                        db_session.flush()  # Get the ID without committing yet
                        self.logger.debug(
                            f"✅ V8.3: Saved analysis_result to database (ID: {analysis_result.id})"
                        )
                    except Exception as e:
                        self.logger.error(f"❌ V8.3: Failed to save analysis_result: {e}")
                        # Intelligent error tracking integration
                        if ERROR_TRACKING_AVAILABLE and record_error_intelligent:
                            record_error_intelligent(
                                error_type="database_errors",
                                error_message=str(e),
                                severity="ERROR",
                                component="analysis_engine",
                            )
                        # Continue anyway - don't block alert sending

                # --- STEP 9: VERIFICATION LAYER (V7.0) ---
                # Verify alert before sending

                should_send, final_score, final_market, verification_result = (
                    self.run_verification_check(
                        match=match,
                        analysis=analysis_result,
                        home_stats=home_stats,
                        away_stats=away_stats,
                        home_context=home_context,
                        away_context=away_context,
                        context_label=context_label,
                        home_team_injury_impact=home_injury_impact,
                        away_team_injury_impact=away_injury_impact,
                    )
                )

                # --- STEP 9.5: FINAL ALERT VERIFIER (EnhancedFinalVerifier) ---
                # Final verification before sending to Telegram
                final_verification_info = None
                if should_send and analysis_result:
                    try:
                        # Build alert data for the final verifier
                        alert_data = build_alert_data_for_verifier(
                            match=match,
                            analysis=analysis_result,
                            news_summary=analysis_result.summary or "",
                            news_url=analysis_result.url or "",
                            score=final_score,
                            recommended_market=final_market,
                            combo_suggestion=analysis_result.combo_suggestion,
                            reasoning=analysis_result.summary,  # Use summary as reasoning (NewsLog doesn't have separate reasoning field)
                        )

                        # Build context data with verification layer results
                        context_data = build_context_data_for_verifier(
                            verification_info=verification_result.to_dict()
                            if verification_result
                            else None,
                        )

                        # Run final verification
                        should_send_final, final_verification_info = verify_alert_before_telegram(
                            match=match,
                            analysis=analysis_result,
                            alert_data=alert_data,
                            context_data=context_data,
                        )

                        # Update should_send based on final verifier result
                        if not should_send_final:
                            self.logger.warning(
                                f"❌ Alert blocked by Final Verifier: {final_verification_info.get('reason', 'Unknown reason')}"
                            )
                            should_send = False
                        else:
                            self.logger.info(
                                f"✅ Alert passed Final Verifier (status: {final_verification_info.get('status', 'unknown')})"
                            )

                    except Exception as e:
                        self.logger.error(f"❌ Enhanced Final Verifier error: {e}")
                        # Fail-safe: allow alert to proceed if verifier fails
                        should_send = should_send  # Keep original decision
                        final_verification_info = {"status": "error", "reason": str(e)}

                    # --- STEP 9.6: INTELLIGENT MODIFICATION LOOP (Feedback Loop Integration) ---
                    # Handle MODIFY recommendations from Final Verifier using intelligent feedback loop
                    # VPS FIX: Use upper().strip() to handle case-insensitive comparison and whitespace
                    # V3.0: Now passes DATA DISCREPANCIES to modification loop for intelligent decisions
                    if (
                        final_verification_info
                        and final_verification_info.get("final_recommendation", "").upper().strip()
                        == "MODIFY"
                    ):
                        try:
                            self.logger.info(
                                "🔄 [INTELLIGENT LOOP] Final Verifier recommends modification"
                            )

                            # V3.0: Log data discrepancies if present
                            data_discrepancies = final_verification_info.get(
                                "data_discrepancies", []
                            )
                            if data_discrepancies:
                                self.logger.info(
                                    f"📊 [INTELLIGENT LOOP] Passing {len(data_discrepancies)} data discrepancies to modification system"
                                )
                                for i, d in enumerate(data_discrepancies, 1):
                                    if isinstance(d, dict):
                                        field = d.get("field", "unknown")
                                        impact = d.get("impact", "LOW")
                                    else:
                                        field = getattr(d, "field", "unknown")
                                        impact = getattr(d, "impact", "LOW")
                                    self.logger.info(f"   {i}. {field.upper()} (impact: {impact})")

                            # Import components
                            from src.analysis.intelligent_modification_logger import (
                                get_intelligent_modification_logger,
                            )
                            from src.analysis.step_by_step_feedback import (
                                get_step_by_step_feedback_loop,
                            )

                            # Get singleton instances
                            intelligent_logger = get_intelligent_modification_logger()
                            feedback_loop = get_step_by_step_feedback_loop()

                            # Step 1: Analyze verifier suggestions and create modification plan
                            # V3.0: Passes data_discrepancies for intelligent modification decisions
                            modification_plan = intelligent_logger.analyze_verifier_suggestions(
                                match=match,
                                analysis=analysis_result,
                                verification_result=final_verification_info,
                                alert_data=alert_data,
                                context_data=context_data,
                            )

                            # Step 2: Process modification plan step-by-step
                            should_send_final, final_result, modified_analysis = (
                                feedback_loop.process_modification_plan(
                                    match=match,
                                    original_analysis=analysis_result,
                                    modification_plan=modification_plan,
                                    alert_data=alert_data,
                                    context_data=context_data,
                                )
                            )

                            # Step 3: Update final verification info with feedback loop results
                            final_verification_info["feedback_loop_used"] = True
                            final_verification_info["feedback_loop_result"] = final_result

                            # Step 4: Update should_send based on feedback loop result
                            # VPS FIX: Check for database errors before using modified analysis
                            if (
                                modified_analysis is not None
                                and final_result.get("status") != "database_error"
                            ):
                                # Use modified analysis for alert sending
                                analysis_result = modified_analysis
                                should_send = should_send_final
                                final_score = getattr(modified_analysis, "score", final_score)
                                final_market = getattr(
                                    modified_analysis, "recommended_market", final_market
                                )

                                self.logger.info(
                                    "✅ [INTELLIGENT LOOP] Feedback loop completed successfully"
                                )
                                self.logger.info(
                                    f"   Modified score: {final_score:.1f}/10 | Market: {final_market}"
                                )
                            else:
                                self.logger.warning(
                                    "⚠️  [INTELLIGENT LOOP] Feedback loop failed or database error, "
                                    "proceeding with original analysis (alert WILL be sent)"
                                )
                                # COVE FIX: Do NOT set should_send = False here
                                # The alert should still be sent with the original analysis
                                # We just log a warning that the intelligent modification was skipped
                                should_send = True  # Explicitly set to True to ensure alert is sent

                        except Exception as e:
                            error_type = type(e).__name__
                            self.logger.error(
                                f"❌ [INTELLIGENT LOOP] Technical error during feedback loop: {error_type}: {e}",
                                exc_info=True,
                            )
                            self.logger.warning(
                                "⚠️  [INTELLIGENT LOOP] Feedback loop crashed, "
                                "proceeding with original analysis (alert WILL be sent)"
                            )
                            # COVE FIX: Consistent with line 1647 — feedback loop failure
                            # (whether graceful or exception) should NOT veto the alert.
                            # The alert has already passed Analyzer + Verification Layer + Final Verifier.
                            should_send = True
                            # VPS FIX: Add error context to final_verification_info
                            final_verification_info["feedback_loop_error"] = {
                                "error_type": error_type,
                                "error_message": str(e),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }

                # --- STEP 10: SEND ALERT (if threshold met AND verification passed) ---
                # V11.1 FIX: Use lower threshold for radar-triggered analyses (forced_narrative present)
                alert_threshold = (
                    ALERT_THRESHOLD_RADAR if forced_narrative else ALERT_THRESHOLD_HIGH
                )
                if should_send and final_score >= alert_threshold:
                    # V10.6 TRACER: Match APPROVED - Sending to Notifier
                    self.logger.info(
                        f"🟢 [TRACER] Match {home_team_valid} vs {away_team_valid} APPROVED. Score: {final_score:.1f}. Sending to Notifier."
                    )
                    self.logger.info(f"🚨 ALERT: {final_score:.1f}/10 - {final_market}")

                    try:
                        from src.alerting.notifier import send_alert_wrapper
                        from src.models import EnhancedMatchAlert

                        # V14.0: Create EnhancedMatchAlert object for type-safe alert handling
                        # V9.5: Pass convergence parameters if available from analysis_result
                        # Extract convergence information from analysis_result
                        is_convergent = getattr(analysis_result, "is_convergent", False)
                        convergence_sources = getattr(analysis_result, "convergence_sources", None)

                        # V14.0: Build EnhancedMatchAlert object with all alert data
                        # This provides type safety and validation at creation time
                        alert = EnhancedMatchAlert(
                            home_team=match.home_team,
                            away_team=match.away_team,
                            league=match.league,
                            score=final_score,
                            news_summary=news_articles[0].get("snippet", "")
                            if news_articles
                            else "",
                            news_url=news_articles[0].get("link", "") if news_articles else None,
                            recommended_market=final_market,
                            combo_suggestion=getattr(analysis_result, "combo_suggestion", None),
                            combo_reasoning=getattr(analysis_result, "combo_reasoning", None),
                            math_edge=getattr(analysis_result, "math_edge", None),
                            is_update=False,
                            financial_risk=getattr(analysis_result, "financial_risk", None),
                            intel_source="web",
                            referee_intel=dataclasses.asdict(referee_info)
                            if referee_info
                            else None,  # Convert RefereeStats to dict
                            twitter_intel=twitter_intel,
                            validated_home_team=None,  # Not available in current scope
                            validated_away_team=None,  # Not available in current scope
                            verification_info=verification_result,
                            final_verification_info=final_verification_info,  # BUG #1 FIX: Pass final verifier results
                            injury_intel=home_injury_impact or away_injury_impact,
                            confidence_breakdown=getattr(
                                analysis_result, "confidence_breakdown", None
                            ),
                            is_convergent=is_convergent,
                            convergence_sources=convergence_sources,
                            market_warning=market_warning,  # V11.1 FIX: Pass market warning to alert
                            match_obj=match,  # COVE FIX: Pass Match ORM object separately from NewsLog
                            analysis_result=analysis_result,  # V8.3: Pass NewsLog object for updating
                            db_session=db_session,  # V8.3: Pass db_session for updating
                        )

                        self.logger.info(
                            f"📊 V14.0: Created EnhancedMatchAlert object - "
                            f"score={final_score}, market={final_market}, "
                            f"home_team={match.home_team}, away_team={match.away_team}"
                        )

                        # COVE DEBUG: Sending to Notifier trace
                        if forced_narrative:
                            self.logger.info(
                                f"📡 [DEBUG] Sending to Notifier... "
                                f"Match: {home_team_valid} vs {away_team_valid}, "
                                f"Score: {final_score:.1f}, Market: {final_market}"
                            )

                        # V14.0: Send alert using EnhancedMatchAlert object
                        alert_delivered = send_alert_wrapper(alert=alert)

                        # COVE FIX: Only update database if alert was actually delivered
                        if alert_delivered:
                            result["alert_sent"] = True
                            result["score"] = final_score
                            result["market"] = final_market

                            # Update match's last_deep_dive_time
                            match.last_deep_dive_time = now_utc
                            db_session.commit()
                        else:
                            result["alert_sent"] = False
                            result["score"] = final_score
                            result["market"] = final_market
                            self.logger.warning(
                                f"⚠️ COVE: Alert delivery failed for match {match.home_team} vs {match.away_team}. "
                                f"Match will NOT enter cooldown and will be retried on next scan."
                            )
                            # Do NOT update last_deep_dive_time or commit - match stays eligible for retry

                    except Exception as e:
                        self.logger.error(f"❌ Failed to send alert: {e}")
                        try:
                            db_session.rollback()
                        except Exception as rollback_error:
                            self.logger.error(f"❌ Rollback failed: {rollback_error}")
                        result["error"] = str(e)
                else:
                    # V11.1: Enhanced veto transparency logging
                    veto_reason = "Unknown"
                    if verification_result and verification_result.score_adjustment_reason:
                        veto_reason = verification_result.score_adjustment_reason

                    # V10.6 TRACER: Match rejected due to score threshold
                    self.logger.info(
                        f"🔴 [TRACER] Match {home_team_valid} vs {away_team_valid} rejected. Reason: Score Threshold. Score: {final_score:.1f}"
                    )
                    self.logger.info(
                        f"🛑 MATCH VETOED: Final Score {final_score:.1f} < {alert_threshold} [Reason: {veto_reason}]"
                    )

                    result["score"] = final_score
                    result["market"] = final_market

                    # Update match's last_deep_dive_time even if no alert
                    match.last_deep_dive_time = now_utc
                    db_session.commit()

            except Exception as e:
                self.logger.error(
                    f"❌ Analysis failed for {home_team_valid} vs {away_team_valid}: {e}"
                )
                try:
                    db_session.rollback()
                except Exception as rollback_error:
                    self.logger.error(f"❌ Rollback failed: {rollback_error}")
                result["error"] = str(e)

            return result

        except Exception as e:
            self.logger.error(f"❌ Match analysis failed: {e}")
            result["error"] = str(e)
            return result


# ============================================
# FACTORY FUNCTION
# ============================================


def get_analysis_engine() -> AnalysisEngine:
    """
    Factory function to get the Analysis Engine instance.

    Returns:
        AnalysisEngine instance
    """
    return AnalysisEngine()
