"""
EarlyBird Analysis Engine (V1.0)
=================================

This module acts as the "brain" of the EarlyBird system, orchestrating
all match-level analysis and AI triangulation logic.

Extracted from src/main.py as part of the modular refactoring initiative.
This module understands match context and coordinates intelligence gathering
from multiple sources.

Author: Refactored by Lead Architect
Date: 2026-02-09
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple, Any

# Database
from src.database.models import Match, NewsLog, SessionLocal

# Analysis engines
from src.analysis.analyzer import analyze_with_triangulation
from src.analysis.injury_impact_engine import (
    analyze_match_injuries,
    TeamInjuryImpact
)
from src.analysis.fatigue_engine import (
    get_enhanced_fatigue_context,
    FatigueDifferential
)
from src.analysis.market_intelligence import analyze_market_intelligence
from src.analysis.biscotto_engine import (
    get_enhanced_biscotto_analysis,
    BiscottoSeverity
)
from src.analysis.verification_layer import (
    verify_alert,
    should_verify_alert,
    create_verification_request_from_match,
    VerificationStatus,
    VerificationRequest,
    VerificationResult,
    VERIFICATION_SCORE_THRESHOLD,
)

# Data providers
from src.ingestion.data_provider import get_data_provider
from src.ingestion.fotmob_team_mapping import get_fotmob_team_id
from src.ingestion.weather_provider import get_match_weather

# Processing
from src.processing.news_hunter import run_hunter_for_match

# Configuration
from config.settings import (
    ALERT_THRESHOLD_HIGH,
    BISCOTTO_EXTREME_LOW,
    BISCOTTO_SUSPICIOUS_LOW,
    BISCOTTO_SIGNIFICANT_DROP,
)

# Configure logger
logger = logging.getLogger(__name__)

# ============================================
# ANALYSIS-SPECIFIC CONSTANTS
# ============================================
# These constants are specific to the analysis engine and are defined
# locally to avoid polluting config/settings.py

CASE_CLOSED_COOLDOWN_HOURS = 6  # Hours to wait before re-investigating
FINAL_CHECK_WINDOW_HOURS = 2   # Hours before kickoff when cooldown is ignored

# ============================================
# ANALYSIS-SPECIFIC CONSTANTS
# ============================================
# These constants are specific to the analysis engine and are defined
# locally to avoid polluting config/settings.py

CASE_CLOSED_COOLDOWN_HOURS = 6  # Hours to wait before re-investigating
FINAL_CHECK_WINDOW_HOURS = 2   # Hours before kickoff when cooldown is ignored

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
        resolve_conflict_via_gemini
    )
    _TWEET_FILTER_AVAILABLE = True
    logger.debug("✅ Tweet Relevance Filter loaded")
except ImportError:
    _TWEET_FILTER_AVAILABLE = False
    logger.debug("⚠️ Tweet Relevance Filter not available")

# Parallel Enrichment V6.0
try:
    from src.utils.parallel_enrichment import (
        enrich_match_parallel,
        EnrichmentResult
    )
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
    "soccer_africa_cup_of_nations",     # AFCON - Radar only
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
            'twitter_intel': _TWITTER_INTEL_AVAILABLE,
            'tweet_filter': _TWEET_FILTER_AVAILABLE,
            'parallel_enrichment': _PARALLEL_ENRICHMENT_AVAILABLE,
        }
    
    def get_availability_flags(self) -> Dict[str, bool]:
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
    def is_case_closed(match: Match, now: datetime) -> Tuple[bool, str]:
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
    
    # ============================================
    # BISCOTTO DETECTION
    # ============================================
    
    @staticmethod
    def is_biscotto_suspect(match: Match) -> Dict[str, Any]:
        """
        🍪 BISCOTTO DETECTION: Check if Draw odds indicate a "mutually beneficial draw".
        
        V6.1: Added edge case protection for invalid odds values.
        
        Args:
            match: Match object with current_draw_odd and opening_draw_odd
            
        Returns:
            dict with 'is_suspect', 'reason', 'draw_odd', 'drop_pct', 'severity'
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
    
    @staticmethod
    def check_biscotto_suspects() -> List[Dict[str, Any]]:
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
            matches = db.query(Match).filter(
                Match.start_time > datetime.now(timezone.utc),
                Match.current_draw_odd.isnot(None)
            ).all()
            
            suspects = []
            
            for match in matches:
                result = AnalysisEngine.is_biscotto_suspect(match)
                if result['is_suspect']:
                    suspects.append({
                        'match': match,
                        'severity': result['severity'],
                        'reason': result['reason'],
                        'draw_odd': result['draw_odd'],
                        'drop_pct': result['drop_pct']
                    })
            
            if suspects:
                logger.info(f"🍪 Found {len(suspects)} Biscotto suspects")
                for suspect in suspects:
                    match = suspect['match']
                    logger.info(f"   🍪 {match.home_team} vs {match.away_team}: {suspect['reason']}")
            
            return suspects
            
        finally:
            db.close()
    
    # ============================================
    # ODDS DROP DETECTION
    # ============================================
    
    @staticmethod
    def check_odds_drops() -> List[Dict[str, Any]]:
        """
        Check for significant odds movements in the database.
        
        This function scans all matches in the database and identifies
        significant odds drops that may indicate market movement or
        insider information.
        
        Returns:
            List of significant drop dictionaries
        """
        db = SessionLocal()
        try:
            # Get all matches with odds data
            matches = db.query(Match).filter(
                Match.start_time > datetime.now(timezone.utc),
                Match.current_home_odd.isnot(None),
                Match.opening_home_odd.isnot(None)
            ).all()
            
            significant_drops = []
            
            for match in matches:
                # Calculate home odd drop
                if match.opening_home_odd and match.current_home_odd:
                    home_drop_pct = ((match.opening_home_odd - match.current_home_odd) / match.opening_home_odd) * 100
                    if home_drop_pct > 15:  # 15%+ drop is significant
                        significant_drops.append({
                            'match': match,
                            'type': 'HOME_DROP',
                            'drop_pct': home_drop_pct,
                            'opening': match.opening_home_odd,
                            'current': match.current_home_odd
                        })
                
                # Calculate away odd drop
                if match.opening_away_odd and match.current_away_odd:
                    away_drop_pct = ((match.opening_away_odd - match.current_away_odd) / match.opening_away_odd) * 100
                    if away_drop_pct > 15:  # 15%+ drop is significant
                        significant_drops.append({
                            'match': match,
                            'type': 'AWAY_DROP',
                            'drop_pct': away_drop_pct,
                            'opening': match.opening_away_odd,
                            'current': match.current_away_odd
                        })
            
            if significant_drops:
                logger.info(f"💹 Found {len(significant_drops)} significant odds drops")
                for drop in significant_drops:
                    match = drop['match']
                    logger.info(f"   📉 {match.home_team} vs {match.away_team}: {drop['type']} {drop['drop_pct']:.1f}% ({drop['opening']:.2f} → {drop['current']:.2f})")
            
            return significant_drops
            
        finally:
            db.close()
    
    # ============================================
    # TWITTER INTEL HELPERS
    # ============================================
    
    def get_twitter_intel_for_match(
        self,
        match: Match,
        context_label: str = ""
    ) -> Optional[Dict[str, Any]]:
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
            self.logger.info(f"   🐦 {label}Twitter Intel: {len(relevant_tweets)} relevant tweets found")
            return twitter_intel_data
            
        except Exception as e:
            self.logger.debug(f"Twitter Intel enrichment failed: {e}")
            return None
    
    def get_twitter_intel_for_ai(
        self,
        match: Match,
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
            self.logger.info(f"   🐦 {label}Twitter Intel for AI: {len(result.tweets)} tweets selected")
            
            # If conflicts detected, resolve via Gemini
            gemini_resolution = None
            if result.has_conflicts and result.conflict_description:
                self.logger.warning(f"   ⚠️ Twitter/FotMob conflict detected: {result.conflict_description}")
                
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
                    self.logger.info(f"   🔍 Gemini conflict resolution: {status}")
                    
                    # Append Gemini resolution to formatted output
                    resolution_text = self._format_gemini_resolution(gemini_resolution)
                    if resolution_text:
                        return f"{result.formatted_for_ai}\n\n{resolution_text}"
            
            return result.formatted_for_ai
            
        except Exception as e:
            self.logger.debug(f"Twitter Intel for AI failed: {e}")
            return ""
    
    @staticmethod
    def _format_gemini_resolution(resolution: Dict[str, Any]) -> str:
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
    # TACTICAL INJURY PROFILE
    # ============================================
    
    @staticmethod
    def format_tactical_injury_profile(
        team_name: str,
        team_context: Dict[str, Any],
        injury_impact: Optional[TeamInjuryImpact] = None
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
    # PARALLEL ENRICHMENT
    # ============================================
    
    def run_parallel_enrichment(
        self,
        fotmob,
        home_team: str,
        away_team: str,
        match_start_time=None,
        weather_provider=None
    ) -> Optional[Dict[str, Any]]:
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
            self.logger.warning(f"⚠️ Parallel enrichment failed: {e}, falling back to sequential")
            return None
    
    # ============================================
    # VERIFICATION LAYER
    # ============================================
    
    def run_verification_check(
        self,
        match: Match,
        analysis: NewsLog,
        home_stats: Optional[Dict[str, Any]] = None,
        away_stats: Optional[Dict[str, Any]] = None,
        home_context: Optional[Dict[str, Any]] = None,
        away_context: Optional[Dict[str, Any]] = None,
        context_label: str = ""
    ) -> Tuple[bool, float, Optional[str], Optional[VerificationResult]]:
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
        try:
            # Check if verification is needed for this alert
            if not should_verify_alert(analysis.score, analysis.recommended_market):
                return True, analysis.score, analysis.recommended_market, None
            
            # Create verification request
            request = create_verification_request_from_match(
                match=match,
                analysis=analysis,
                home_stats=home_stats,
                away_stats=away_stats,
                home_context=home_context,
                away_context=away_context
            )
            
            # Run verification
            result = verify_alert(request)
            
            label = f"[{context_label}] " if context_label else ""
            
            if result.status == VerificationStatus.CONFIRMED:
                self.logger.info(f"✅ {label}Alert CONFIRMED by Verification Layer")
                return True, result.adjusted_score, result.original_market, result
            elif result.status == VerificationStatus.CHANGE_MARKET:
                self.logger.info(f"🔄 {label}Verification Layer changed market from {analysis.recommended_market} to {result.suggested_market}")
                return True, result.adjusted_score, result.suggested_market, result
            elif result.status == VerificationStatus.DENIED:
                self.logger.warning(f"❌ {label}Alert DENIED by Verification Layer: {result.reason}")
                return False, result.adjusted_score, result.suggested_market, result
            elif result.status == VerificationStatus.NO_CHANGE:
                self.logger.info(f"✅ {label}Alert CONFIRMED by Verification Layer")
                return True, result.adjusted_score, result.original_market, result
            
        except Exception as e:
            self.logger.error(f"❌ {label}Verification Layer error: {e}")
            # On error, allow alert to proceed with original data
            return True, analysis.score, getattr(analysis, 'recommended_market', None), None
    
    # ============================================
    # MAIN MATCH ANALYSIS
    # ============================================
    
    def analyze_match(
        self,
        match: Match,
        fotmob,
        now_utc: datetime,
        db_session,
        context_label: str = "TIER1"
    ) -> Dict[str, Any]:
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
        8. Hunts for news articles
        9. Gathers Twitter intel
        10. Runs AI triangulation analysis
        11. Verifies alert before sending
        12. Sends alert if threshold met
        
        Args:
            match: Match database object
            fotmob: FotMob provider instance
            now_utc: Current UTC time
            db_session: Database session for updates
            context_label: Label for logging (e.g., "TIER1", "TIER2", "RADAR")
            
        Returns:
            Dict with analysis results including:
            - alert_sent: Whether an alert was sent
            - score: Final analysis score
            - market: Recommended market
            - error: Any error that occurred
        """
        result = {
            'alert_sent': False,
            'score': 0.0,
            'market': None,
            'error': None
        }
        
        try:
            # --- STEP 0a: HOME/AWAY VALIDATION (V5.1) ---
            # Validate home/away order using FotMob as source of truth
            # This prevents alerts with inverted team order (e.g., "FC Porto vs Santa Clara" 
            # when the actual match is "Santa Clara vs FC Porto")
            
            home_team_valid = match.home_team
            away_team_valid = match.away_team
            
            if fotmob:
                try:
                    # Get FotMob team IDs for validation
                    fotmob_home_id = get_fotmob_team_id(match.home_team)
                    fotmob_away_id = get_fotmob_team_id(match.away_team)
                    
                    # If we have both IDs, validate the order
                    if fotmob_home_id and fotmob_away_id:
                        # Get FotMob match data to validate order
                        fotmob_match = fotmob.get_match(fotmob_home_id, fotmob_away_id, match.start_time)
                        
                        if fotmob_match:
                            # Check if FotMob has the teams in the same order
                            fotmob_home_name = fotmob_match.get('home', {}).get('name', '')
                            fotmob_away_name = fotmob_match.get('away', {}).get('name', '')
                            
                            # If FotMob has different order, swap our teams
                            if (fotmob_home_name and fotmob_away_name and
                                match.home_team != fotmob_home_name):
                                self.logger.warning(f"⚠️ Team order mismatch detected: DB has {match.home_team} vs {match.away_team}, FotMob has {fotmob_home_name} vs {fotmob_away_name}")
                                # Swap team names
                                home_team_valid, away_team_valid = away_team_valid, home_team_valid
                                self.logger.info(f"✅ Corrected team order to: {home_team_valid} vs {away_team_valid}")
                except Exception as e:
                    self.logger.debug(f"Team order validation skipped: {e}")
            
            # --- STEP 0b: CASE CLOSED COOLDOWN CHECK (V6.0) ---
            # Skip analysis if match is on cooldown (already investigated recently)
            is_closed, cooldown_reason = self.is_case_closed(match, now_utc)
            if is_closed:
                self.logger.info(f"⏸️  Skipping {match.home_team} vs {match.away_team}: {cooldown_reason}")
                return result
            
            # --- STEP 1: PARALLEL ENRICHMENT (V6.0) ---
            # Fetch all FotMob data in parallel for performance
            self.logger.info(f"\n🔍 Investigating {home_team_valid} vs {away_team_valid} ({match.league})...")
            
            enrichment_data = None
            if _PARALLEL_ENRICHMENT_AVAILABLE and fotmob:
                enrichment_data = self.run_parallel_enrichment(
                    fotmob=fotmob,
                    home_team=home_team_valid,
                    away_team=away_team_valid,
                    match_start_time=match.start_time,
                    weather_provider=get_match_weather
                )
            
            # Extract enrichment results
            home_context = enrichment_data.get('home_context', {}) if enrichment_data else {}
            away_context = enrichment_data.get('away_context', {}) if enrichment_data else {}
            home_stats = enrichment_data.get('home_stats', {}) if enrichment_data else {}
            away_stats = enrichment_data.get('away_stats', {}) if enrichment_data else {}
            referee_info = enrichment_data.get('referee_info') if enrichment_data else None
            
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
                    away_context=away_context
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
                    fatigue_differential = get_enhanced_fatigue_context(
                        home_team=home_team_valid,
                        away_team=away_team_valid,
                        home_context=home_context,
                        away_context=away_context
                    )
                except Exception as e:
                    self.logger.warning(f"⚠️ Fatigue analysis failed: {e}")
            
            # --- STEP 4: BISCOTTO DETECTION (V2.0) ---
            # Check for suspicious Draw odds
            
            biscotto_result = self.is_biscotto_suspect(match)
            if biscotto_result['is_suspect']:
                self.logger.info(f"   🍪 {biscotto_result['reason']}")
            
            # --- STEP 5: MARKET INTELLIGENCE (V2.0) ---
            # Analyze market movements (Steam Move, Reverse Line, News Decay)
            
            market_intel = None
            try:
                market_intel = analyze_market_intelligence(
                    match=match,
                    league_key=match.league
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Market intelligence analysis failed: {e}")
            
            # --- STEP 6: NEWS HUNTING (V4.0) ---
            # Search for relevant news articles
            
            news_articles = []
            try:
                news_articles = run_hunter_for_match(
                    match=match,
                    include_insiders=True
                )
                self.logger.info(f"   📰 Found {len(news_articles)} relevant news articles")
            except Exception as e:
                self.logger.warning(f"⚠️ News hunting failed: {e}")
            
            # --- STEP 7: TWITTER INTEL (V4.5) ---
            # Get Twitter intelligence
            
            twitter_intel = self.get_twitter_intel_for_match(match, context_label=context_label)
            
            # --- STEP 8: AI ANALYSIS (V6.0) ---
            # Run triangulation analysis with all available data
            
            try:
                # Format injury data for AI
                home_injury_str = self.format_tactical_injury_profile(
                    home_team_valid,
                    home_context,
                    home_injury_impact
                )
                away_injury_str = self.format_tactical_injury_profile(
                    away_team_valid,
                    away_context,
                    away_injury_impact
                )
                
                # Format Twitter intel for AI
                twitter_intel_str = self.get_twitter_intel_for_ai(
                    match,
                    official_data=f"Home: {home_injury_str}\nAway: {away_injury_str}",
                    context_label=context_label
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
                    referee_info=referee_info
                )
                
                # --- STEP 9: VERIFICATION LAYER (V7.0) ---
                # Verify alert before sending
                
                should_send, final_score, final_market, verification_result = self.run_verification_check(
                    match=match,
                    analysis=analysis_result,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_context=home_context,
                    away_context=away_context,
                    context_label=context_label
                )
                
                # --- STEP 10: SEND ALERT (if threshold met) ---
                if should_send and final_score >= ALERT_THRESHOLD_HIGH:
                    self.logger.info(f"🚨 ALERT: {final_score:.1f}/10 - {final_market}")
                    
                    try:
                        from src.alerting.notifier import send_alert_wrapper
                        # V9.5: Pass convergence parameters if available from analysis_result
                        # Extract convergence information from analysis_result
                        is_convergent = getattr(analysis_result, 'is_convergent', False)
                        convergence_sources = getattr(analysis_result, 'convergence_sources', None)
                        
                        send_alert_wrapper(
                            match=match,
                            score=final_score,
                            market=final_market,
                            home_context=home_context,
                            away_context=away_context,
                            home_stats=home_stats,
                            away_stats=away_stats,
                            news_articles=news_articles,
                            twitter_intel=twitter_intel,
                            fatigue_differential=fatigue_differential,
                            injury_impact_home=home_injury_impact,
                            injury_impact_away=away_injury_impact,
                            biscotto_result=biscotto_result,
                            market_intel=market_intel,
                            verification_result=verification_result,
                            is_convergent=is_convergent,
                            convergence_sources=convergence_sources
                        )
                        
                        result['alert_sent'] = True
                        result['score'] = final_score
                        result['market'] = final_market
                        
                        # Update match's last_deep_dive_time
                        match.last_deep_dive_time = now_utc
                        db_session.commit()
                        
                    except Exception as e:
                        self.logger.error(f"❌ Failed to send alert: {e}")
                        db_session.rollback()
                        result['error'] = str(e)
                else:
                    self.logger.info(f"   No alert sent (score: {final_score:.1f}, threshold: {ALERT_THRESHOLD_HIGH})")
                    
                    result['score'] = final_score
                    result['market'] = final_market
                    
                    # Update match's last_deep_dive_time even if no alert
                    match.last_deep_dive_time = now_utc
                    db_session.commit()
                    
            except Exception as e:
                self.logger.error(f"❌ Analysis failed for {home_team_valid} vs {away_team_valid}: {e}")
                db_session.rollback()
                result['error'] = str(e)
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Match analysis failed: {e}")
            result['error'] = str(e)
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
