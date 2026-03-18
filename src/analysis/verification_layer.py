"""
EarlyBird Verification Layer V1.0

Validation component that acts as a quality filter between preliminary alerts
and the final send decision. Verifies data with external sources (Tavily/Perplexity)
to fill FotMob gaps and validate betting logic.

Key Problem Solved: The system may suggest Over 2.5 Goals for a team with 7 CRITICAL
absences without considering that a decimated squad typically produces fewer goals.
The Verification Layer verifies the real impact of missing players and suggests
alternative markets when appropriate.

Flow:
    Alert (score >= 7.5) -> VerificationLayer -> CONFIRM/REJECT/CHANGE_MARKET

Requirements: 1.1-1.4, 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.4, 6.1-6.5, 7.1-7.4, 8.1-8.4
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# Import safe dictionary access utilities
from src.utils.validators import safe_dict_get

# V11.0: Import Contract Validation
try:
    from src.utils.contracts import VERIFICATION_RESULT_CONTRACT, ContractViolation

    _CONTRACTS_AVAILABLE = True
except ImportError:
    _CONTRACTS_AVAILABLE = False
    logging.debug("Contracts module not available for verification_layer")

logger = logging.getLogger(__name__)

# Import CardsSignal and SignalLevel enums for type consistency
try:
    from src.schemas.perplexity_schemas import CardsSignal, RefereeStrictness, SignalLevel

    CARDS_SIGNAL_AVAILABLE = True
    REFEREE_STRICTNESS_AVAILABLE = True
    SIGNAL_LEVEL_AVAILABLE = True
except ImportError:
    CARDS_SIGNAL_AVAILABLE = False
    REFEREE_STRICTNESS_AVAILABLE = False
    SIGNAL_LEVEL_AVAILABLE = False
    logger.warning("⚠️ CardsSignal enum not available")
    logger.warning("⚠️ RefereeStrictness enum not available")
    logger.warning("⚠️ SignalLevel enum not available")

# Import DataConfidence enum for type consistency
try:
    from src.schemas.perplexity_schemas import DataConfidence

    DATA_CONFIDENCE_AVAILABLE = True
except ImportError:
    DATA_CONFIDENCE_AVAILABLE = False
    logger.warning("⚠️ DataConfidence enum not available")

# Import referee cache for V9.0
try:
    from src.analysis.referee_cache import get_referee_cache

    REFEREE_CACHE_AVAILABLE = True
except ImportError:
    REFEREE_CACHE_AVAILABLE = False
    logger.warning("⚠️ Referee cache not available")

# Import referee cache monitor for V9.0
try:
    from src.analysis.referee_cache_monitor import get_referee_cache_monitor

    REFEREE_CACHE_MONITOR_AVAILABLE = True
except ImportError:
    REFEREE_CACHE_MONITOR_AVAILABLE = False
    logger.warning("⚠️ Referee cache monitor not available")

# Import referee boost logger for V9.0
try:
    from src.analysis.referee_boost_logger import (
        BoostType,
        get_referee_boost_logger,
    )

    REFEREE_BOOST_LOGGER_AVAILABLE = True
except ImportError:
    REFEREE_BOOST_LOGGER_AVAILABLE = False
    logger.warning("⚠️ Referee boost logger not available")


# ============================================
# CONFIGURATION CONSTANTS
# V7.0.2: Import from settings.py for centralized configuration
# ============================================

try:
    from config.settings import (
        COMBINED_CORNERS_THRESHOLD,
        CRITICAL_IMPACT_THRESHOLD,
        FORM_DEVIATION_THRESHOLD,
        H2H_CARDS_THRESHOLD,
        H2H_CORNERS_THRESHOLD,
        H2H_MAX_CARDS,
        H2H_MAX_CORNERS,
        H2H_MAX_GOALS,
        H2H_MIN_MATCHES,
        LOW_SCORING_THRESHOLD,
        PLAYER_KEY_IMPACT_THRESHOLD,
        REFEREE_CARDS_BOOST_THRESHOLD,
        REFEREE_LENIENT_THRESHOLD,
        REFEREE_STRICT_THRESHOLD,
        VERIFICATION_SCORE_THRESHOLD,
    )
except ImportError:
    # Fallback defaults if settings not available (e.g., in isolated tests)
    PLAYER_KEY_IMPACT_THRESHOLD = 7  # Score >= 7 = key player
    CRITICAL_IMPACT_THRESHOLD = 20  # Total impact >= 20 = critical
    FORM_DEVIATION_THRESHOLD = 0.30  # 30% deviation = warning
    H2H_CARDS_THRESHOLD = 4.5  # Avg cards >= 4.5 = suggest Over Cards
    H2H_CORNERS_THRESHOLD = 10  # Avg corners >= 10 = suggest Over Corners
    H2H_MIN_MATCHES = 3  # Minimum matches required for reliable H2H analysis
    H2H_MAX_CARDS = 12  # Maximum realistic cards per match (sanity check)
    H2H_MAX_CORNERS = 25  # Maximum realistic corners per match (sanity check)
    H2H_MAX_GOALS = 10  # Maximum realistic goals per match (sanity check)
    COMBINED_CORNERS_THRESHOLD = 10.5  # Combined avg >= 10.5 = Over 9.5 Corners
    REFEREE_STRICT_THRESHOLD = 5.0  # Cards/game >= 5 = strict
    REFEREE_LENIENT_THRESHOLD = 3.0  # Cards/game <= 3 = lenient
    REFEREE_CARDS_BOOST_THRESHOLD = 4.0  # Cards/game >= 4 = boost Over Cards
    VERIFICATION_SCORE_THRESHOLD = 7.5  # Minimum score to trigger verification
    LOW_SCORING_THRESHOLD = 1.0  # Goals/game < 1.0 = low scoring


# ============================================
# MARKET VALUE TO IMPACT MAPPING (V2.0)
# ============================================

MARKET_VALUE_IMPACT_MAP = {
    # €M threshold -> impact score
    80: 10,  # €80M+ = world class
    60: 9,  # €60-80M = elite
    40: 8,  # €40-60M = key player
    25: 7,  # €25-40M = important
    15: 6,  # €15-25M = regular starter
    8: 5,  # €8-15M = rotation
    3: 4,  # €3-8M = squad player
    0: 3,  # <€3M = backup
}


def market_value_to_impact(value_millions: float) -> int:
    """
    Convert market value to impact score.

    Uses Transfermarkt market value as proxy for player importance.
    Higher value = more important player = higher impact when missing.

    Args:
        value_millions: Market value in millions of euros

    Returns:
        Impact score 1-10

    Requirements: 1.2, 1.4
    """
    if value_millions is None or value_millions < 0:
        return 5  # Default neutral

    for threshold, impact in sorted(MARKET_VALUE_IMPACT_MAP.items(), reverse=True):
        if value_millions >= threshold:
            return impact
    return 3  # Minimum


# ============================================
# ENUMS
# ============================================


class VerificationStatus(Enum):
    """Possible outcomes of verification."""

    CONFIRM = "confirm"
    REJECT = "reject"
    CHANGE_MARKET = "change_market"


class ConfidenceLevel(Enum):
    """Data confidence levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class InjurySeverity(Enum):
    """Injury severity classification."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


# ============================================
# INPUT DTO: VerificationRequest
# Requirements: 1.1, 6.1
# ============================================


@dataclass
class VerificationRequest:
    """
    Input data for the Verification Layer.

    Contains all information needed to verify an alert:
    - Match identification
    - Preliminary alert data
    - Injury data from FotMob
    - Optional existing data for comparison

    Requirements: 1.1, 6.1
    """

    # Match identification (required)
    match_id: str
    home_team: str
    away_team: str
    match_date: str  # YYYY-MM-DD format
    league: str

    # Preliminary alert data (required)
    suggested_market: str  # "Over 2.5 Goals", "1", "X2", etc.
    preliminary_score: float | None = None

    # Injury data from FotMob (required)
    home_missing_players: list[str] = field(default_factory=list)
    away_missing_players: list[str] = field(default_factory=list)
    home_injury_severity: str = "LOW"  # CRITICAL, HIGH, MEDIUM, LOW
    away_injury_severity: str = "LOW"
    home_injury_impact: float = 0.0  # Total impact score
    away_injury_impact: float = 0.0

    # V13.0: Detailed injury impact data from injury_impact_engine
    # This provides position, role, and reason for each missing player
    home_team_injury_impact: Any = None  # TeamInjuryImpact object
    away_team_injury_impact: Any = None  # TeamInjuryImpact object

    # Optional FotMob data for comparison
    fotmob_home_goals_avg: float | None = None
    fotmob_away_goals_avg: float | None = None
    fotmob_referee_name: str | None = None

    # Optional additional context
    home_form_last5: str | None = None  # e.g., "WWDLL"
    away_form_last5: str | None = None

    def __post_init__(self):
        """Validate required fields after initialization."""
        if not self.match_id:
            raise ValueError("match_id is required")
        if not self.home_team:
            raise ValueError("home_team is required")
        if not self.away_team:
            raise ValueError("away_team is required")
        if not self.match_date:
            raise ValueError("match_date is required")
        if not self.league:
            raise ValueError("league is required")
        # Ensure preliminary_score is not None before comparison
        if self.preliminary_score is None:
            self.preliminary_score = 0.0
        if self.preliminary_score < 0:
            raise ValueError("preliminary_score must be non-negative")
        if not self.suggested_market:
            raise ValueError("suggested_market is required")

        # Normalize injury severity to uppercase
        self.home_injury_severity = self.home_injury_severity.upper()
        self.away_injury_severity = self.away_injury_severity.upper()

    def has_critical_injuries(self, team: str = "any") -> bool:
        """
        Check if team has critical injury severity.

        Args:
            team: "home", "away", or "any" (default)

        Returns:
            True if specified team(s) have CRITICAL severity
        """
        if team == "home":
            return self.home_injury_severity == "CRITICAL"
        elif team == "away":
            return self.away_injury_severity == "CRITICAL"
        else:
            return (
                self.home_injury_severity == "CRITICAL" or self.away_injury_severity == "CRITICAL"
            )

    def both_teams_critical(self) -> bool:
        """Check if both teams have CRITICAL injury severity."""
        return self.home_injury_severity == "CRITICAL" and self.away_injury_severity == "CRITICAL"

    def is_over_market(self) -> bool:
        """Check if suggested market is an Over goals market."""
        market_lower = self.suggested_market.lower()
        return "over" in market_lower and "goal" in market_lower

    def is_cards_market(self) -> bool:
        """Check if suggested market involves cards."""
        market_lower = self.suggested_market.lower()
        return "card" in market_lower

    def is_corners_market(self) -> bool:
        """Check if suggested market involves corners."""
        market_lower = self.suggested_market.lower()
        return "corner" in market_lower

    def get_total_missing_players(self) -> int:
        """Get total number of missing players across both teams."""
        return len(self.home_missing_players) + len(self.away_missing_players)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""

        # Helper to serialize TeamInjuryImpact objects
        def serialize_injury_impact(impact: Any) -> Any:
            if impact is None:
                return None
            if hasattr(impact, "to_dict"):
                return impact.to_dict()
            return impact  # Fallback for primitive types

        return {
            "match_id": self.match_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match_date": self.match_date,
            "league": self.league,
            "preliminary_score": self.preliminary_score,
            "suggested_market": self.suggested_market,
            "home_missing_players": self.home_missing_players,
            "away_missing_players": self.away_missing_players,
            "home_injury_severity": self.home_injury_severity,
            "away_injury_severity": self.away_injury_severity,
            "home_injury_impact": self.home_injury_impact,
            "away_injury_impact": self.away_injury_impact,
            "home_team_injury_impact": serialize_injury_impact(self.home_team_injury_impact),
            "away_team_injury_impact": serialize_injury_impact(self.away_team_injury_impact),
            "fotmob_home_goals_avg": self.fotmob_home_goals_avg,
            "fotmob_away_goals_avg": self.fotmob_away_goals_avg,
            "fotmob_referee_name": self.fotmob_referee_name,
            "home_form_last5": self.home_form_last5,
            "away_form_last5": self.away_form_last5,
        }


# ============================================
# VERIFIED DATA STRUCTURES
# Requirements: 1.1, 2.1, 3.1, 4.1, 5.1
# ============================================


@dataclass
class PlayerImpact:
    """
    Impact assessment for a single player.

    Requirements: 1.1, 1.2
    """

    name: str
    impact_score: int  # 1-10 scale
    is_key_player: bool = False  # True if score >= 7
    role: str | None = None  # "starter", "backup", "unknown"
    position: str | None = None  # "goalkeeper", "defender", "midfielder", "forward"
    reason: str | None = None  # "injury", "suspension", etc.

    def __post_init__(self):
        """Auto-classify as key player based on threshold."""
        if self.impact_score >= PLAYER_KEY_IMPACT_THRESHOLD:
            self.is_key_player = True


@dataclass
class FormStats:
    """
    Team form statistics from last 5 matches.

    Requirements: 2.1, 2.2, 2.3
    """

    goals_scored: int = 0
    goals_conceded: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0

    def __post_init__(self):
        """
        Validate form statistics after initialization.

        Ensures:
        - Non-negative values for all fields
        - Individual match counts capped at 5
        - Total matches (wins + draws + losses) does not exceed 5

        This prevents edge cases where external data sources provide
        invalid or out-of-range values that could corrupt betting decisions.
        """
        # Ensure non-negative values
        self.goals_scored = max(0, self.goals_scored)
        self.goals_conceded = max(0, self.goals_conceded)
        self.wins = max(0, min(5, self.wins))
        self.draws = max(0, min(5, self.draws))
        self.losses = max(0, min(5, self.losses))

        # Ensure total matches doesn't exceed 5 (last 5 matches concept)
        total = self.wins + self.draws + self.losses
        if total > 5:
            # Reduce the largest category first to preserve data integrity
            while total > 5:
                if self.wins >= self.draws and self.wins >= self.losses:
                    self.wins -= 1
                elif self.draws >= self.wins and self.draws >= self.losses:
                    self.draws -= 1
                else:
                    self.losses -= 1
                total -= 1

    @property
    def avg_goals_scored(self) -> float:
        """
        Average goals scored per game.

        Uses matches_played instead of hardcoded 5.0 to handle
        incomplete data correctly (e.g., only 3 matches available).
        """
        if self.matches_played > 0 and self.goals_scored >= 0:
            return self.goals_scored / self.matches_played
        return 0.0

    @property
    def avg_goals_conceded(self) -> float:
        """
        Average goals conceded per game.

        Uses matches_played instead of hardcoded 5.0 to handle
        incomplete data correctly (e.g., only 3 matches available).
        """
        if self.matches_played > 0 and self.goals_conceded >= 0:
            return self.goals_conceded / self.matches_played
        return 0.0

    @property
    def matches_played(self) -> int:
        """Total matches in form calculation."""
        return self.wins + self.draws + self.losses

    def is_low_scoring(self) -> bool:
        """Check if team is low scoring (< 1.0 goals/game)."""
        return self.avg_goals_scored < LOW_SCORING_THRESHOLD

    def is_on_losing_streak(self) -> bool:
        """
        Check if team has 0 wins in last 5 matches.

        Note: Returns False if matches_played < 5 (incomplete data).
        This is intentional to avoid false positives when form data
        is partially available from external sources.
        """
        return self.wins == 0 and self.matches_played >= 5

    def get_form_string(self) -> str:
        """
        Get form as string like 'WWDLL' (max 5 chars).

        Capped at 5 characters to match the "last 5 matches" concept.
        Defensive programming to prevent edge cases from producing
        invalid output.
        """
        form_str = "W" * self.wins + "D" * self.draws + "L" * self.losses
        return form_str[:5]  # Cap at 5 characters


@dataclass
class H2HStats:
    """
    Head-to-head statistics between teams.

    Requirements: 3.1, 3.2, 3.3, 3.4

    V15.0 Enhanced:
    - Added parsing for home_wins, away_wins, draws
    - Added sanity checks on parsed values
    - Added sample size consideration in suggestion methods
    - Improved regex to handle comma-separated numbers
    """

    matches_analyzed: int = 0
    avg_goals: float = 0.0
    avg_cards: float = 0.0
    avg_corners: float = 0.0
    home_wins: int = 0
    away_wins: int = 0
    draws: int = 0

    def suggests_over_cards(self) -> bool:
        """
        Check if H2H suggests Over Cards market.

        V15.0: Now considers sample size reliability.
        Only suggests if we have sufficient matches for statistical significance.
        """
        if not self._has_reliable_sample():
            return False
        return self.avg_cards >= H2H_CARDS_THRESHOLD

    def suggests_over_corners(self) -> bool:
        """
        Check if H2H suggests Over Corners market.

        V15.0: Now considers sample size reliability.
        Only suggests if we have sufficient matches for statistical significance.
        """
        if not self._has_reliable_sample():
            return False
        return self.avg_corners >= H2H_CORNERS_THRESHOLD

    def has_data(self) -> bool:
        """
        Check if H2H data is available.

        V15.0: Added defensive None check for robustness.
        """
        if self.matches_analyzed is None:
            return False
        return self.matches_analyzed > 0

    def _has_reliable_sample(self) -> bool:
        """
        Check if the sample size is reliable for statistical analysis.

        V15.0: New method to prevent false positives from small sample sizes.
        Returns False if we have fewer than H2H_MIN_MATCHES.
        """
        if self.matches_analyzed is None:
            return False
        return self.matches_analyzed >= H2H_MIN_MATCHES

    def _validate_values(self) -> bool:
        """
        Validate that parsed values are within realistic ranges.

        V15.0: New method to detect and reject suspicious/invalid values.
        Returns False if any value exceeds realistic maximums.
        """
        # Check for None values
        if self.avg_cards is None or self.avg_corners is None or self.avg_goals is None:
            return False

        # Check for negative values
        if self.avg_cards < 0 or self.avg_corners < 0 or self.avg_goals < 0:
            return False

        # Check for unrealistic maximums
        if self.avg_cards > H2H_MAX_CARDS:
            logger.warning(
                f"⚠️ H2HStats: Suspicious avg_cards value {self.avg_cards} > {H2H_MAX_CARDS}"
            )
            return False

        if self.avg_corners > H2H_MAX_CORNERS:
            logger.warning(
                f"⚠️ H2HStats: Suspicious avg_corners value {self.avg_corners} > {H2H_MAX_CORNERS}"
            )
            return False

        if self.avg_goals > H2H_MAX_GOALS:
            logger.warning(
                f"⚠️ H2HStats: Suspicious avg_goals value {self.avg_goals} > {H2H_MAX_GOALS}"
            )
            return False

        # Validate win/draw counts don't exceed matches_analyzed
        total_results = self.home_wins + self.away_wins + self.draws
        if total_results > self.matches_analyzed:
            logger.warning(
                f"⚠️ H2HStats: Total results ({total_results}) > matches_analyzed ({self.matches_analyzed})"
            )
            return False

        return True


@dataclass
class RefereeStats:
    """
    Referee statistics for cards analysis.

    Requirements: 4.1, 4.2, 4.3
    """

    name: str
    cards_per_game: float = 0.0
    strictness: RefereeStrictness = RefereeStrictness.UNKNOWN
    matches_officiated: int = 0

    def __post_init__(self):
        """Auto-classify strictness based on cards per game."""
        # Handle backward compatibility: convert string strictness to RefereeStrictness enum
        if isinstance(self.strictness, str):
            strictness_lower = self.strictness.lower()
            if strictness_lower == "strict":
                self.strictness = RefereeStrictness.STRICT
            elif strictness_lower == "lenient":
                self.strictness = RefereeStrictness.LENIENT
            elif strictness_lower in ("average", "medium"):
                self.strictness = RefereeStrictness.MEDIUM
            else:
                self.strictness = RefereeStrictness.UNKNOWN

        # Auto-classify strictness based on cards per game if not explicitly set
        # Keep "unknown" only for negative values (0.0 means very lenient)
        if self.cards_per_game < 0:
            self.strictness = RefereeStrictness.UNKNOWN
        elif self.cards_per_game >= REFEREE_STRICT_THRESHOLD:
            self.strictness = RefereeStrictness.STRICT
        elif self.cards_per_game <= REFEREE_LENIENT_THRESHOLD:
            self.strictness = RefereeStrictness.LENIENT
        else:
            self.strictness = RefereeStrictness.MEDIUM

    def is_strict(self) -> bool:
        """Check if referee is classified as strict."""
        return self.strictness == RefereeStrictness.STRICT

    def is_lenient(self) -> bool:
        """Check if referee is classified as lenient."""
        return self.strictness == RefereeStrictness.LENIENT

    def should_veto_cards(self) -> bool:
        """Check if referee should veto Over Cards suggestions."""
        return self.is_lenient()

    def should_boost_cards(self) -> bool:
        """
        Check if referee should boost Over Cards suggestions.

        Returns:
            True if referee has enough cards per game to justify Over Cards bet
            (>= REFEREE_CARDS_BOOST_THRESHOLD cards/game, regardless of strictness classification)
        """
        return self.cards_per_game >= REFEREE_CARDS_BOOST_THRESHOLD

    def should_upgrade_cards_line(self) -> bool:
        """
        Check if referee is very strict and should upgrade cards line.

        Returns:
            True if referee is very strict (>= REFEREE_STRICT_THRESHOLD cards/game)
        """
        return self.cards_per_game >= REFEREE_STRICT_THRESHOLD

    def get_boost_multiplier(self) -> float:
        """
        Get boost multiplier based on referee strictness.

        Returns:
            Multiplier: 1.0 (no boost), 1.2 (moderate), 1.5 (strong)
        """
        if self.cards_per_game >= 5.0:
            return 1.5  # Strong boost
        elif self.cards_per_game >= 4.0:
            return 1.2  # Moderate boost
        else:
            return 1.0  # No boost


@dataclass
class VerifiedData:
    """
    All verified data from external sources.

    Requirements: 1.1, 2.1, 3.1, 4.1, 5.1
    """

    # Player impacts
    home_player_impacts: list[PlayerImpact] = field(default_factory=list)
    away_player_impacts: list[PlayerImpact] = field(default_factory=list)
    home_total_impact: float = 0.0
    away_total_impact: float = 0.0

    # Form stats
    home_form: FormStats | None = None
    away_form: FormStats | None = None
    form_confidence: str = "Low"  # Title Case: High, Medium, Low

    # H2H stats
    h2h: H2HStats | None = None
    h2h_confidence: str = "Low"

    # Referee stats
    referee: RefereeStats | None = None
    referee_confidence: str = "Low"

    # Corner stats
    home_corner_avg: float | None = None
    away_corner_avg: float | None = None
    h2h_corner_avg: float | None = None
    corners_signal: SignalLevel = SignalLevel.UNKNOWN  # Signal level from Perplexity
    corners_reasoning: str = ""  # Reasoning from Perplexity
    corner_confidence: str = "Low"

    # Cards stats (V13.1: Added for intelligent cards market decisions)
    home_cards_avg: float | None = None
    away_cards_avg: float | None = None
    cards_total_avg: float | None = None
    cards_signal: CardsSignal = CardsSignal.UNKNOWN  # Type-consistent enum usage
    cards_reasoning: str = ""
    cards_confidence: str = "Low"

    # V7.2: Goals per game (season average from team stats)
    # Separate from FormStats.goals_scored which is total in last 5 matches
    home_goals_per_game: float | None = None
    away_goals_per_game: float | None = None

    # V7.7: Expected Goals (xG) pre-match data
    home_xg: float | None = None  # Expected goals scored per game
    away_xg: float | None = None
    home_xga: float | None = None  # Expected goals against per game
    away_xga: float | None = None
    xg_confidence: str = "Low"

    # Overall metadata
    # Type annotation uses Union to handle both Enum and str for backward compatibility
    # When DATA_CONFIDENCE_AVAILABLE is True, DataConfidence enum is preferred
    data_confidence: str = "Low"  # Aggregated confidence (Title Case to match DataConfidence enum)
    source: str = "unknown"  # "tavily" or "perplexity"

    def get_home_key_players(self) -> list[PlayerImpact]:
        """Get list of key players missing from home team."""
        return [p for p in self.home_player_impacts if p.is_key_player]

    def get_away_key_players(self) -> list[PlayerImpact]:
        """Get list of key players missing from away team."""
        return [p for p in self.away_player_impacts if p.is_key_player]

    def get_total_key_player_impact(self, team: str = "any") -> float:
        """
        Get total impact score of key players.

        Args:
            team: "home", "away", or "any"
        """
        if team == "home":
            return sum(p.impact_score for p in self.get_home_key_players())
        elif team == "away":
            return sum(p.impact_score for p in self.get_away_key_players())
        else:
            return sum(p.impact_score for p in self.get_home_key_players()) + sum(
                p.impact_score for p in self.get_away_key_players()
            )

    def has_critical_key_player_impact(self) -> bool:
        """Check if total key player impact exceeds critical threshold."""
        return self.get_total_key_player_impact() > CRITICAL_IMPACT_THRESHOLD

    def get_players_by_position(self, team: str, position: str) -> list[PlayerImpact]:
        """
        Get missing players by position for a specific team.

        Args:
            team: "home" or "away"
            position: "goalkeeper", "defender", "midfielder", "forward", or None for all

        Returns:
            List of PlayerImpact objects matching the criteria
        """
        players = self.home_player_impacts if team == "home" else self.away_player_impacts
        if position is None:
            return players
        return [p for p in players if p.position == position]

    def has_critical_goalkeeper_missing(self, team: str) -> bool:
        """
        Check if team has a missing goalkeeper with critical impact.

        Goalkeepers are critical for defensive stability. A missing goalkeeper
        with high impact score significantly increases defensive vulnerability.

        Args:
            team: "home" or "away"

        Returns:
            True if a goalkeeper with impact >= 7 is missing
        """
        goalkeepers = self.get_players_by_position(team, "goalkeeper")
        return any(p.impact_score >= 7 for p in goalkeepers)

    def has_critical_defense_missing(self, team: str) -> bool:
        """
        Check if team has multiple missing defenders with significant impact.

        Missing multiple defenders creates defensive gaps that can be exploited.

        Args:
            team: "home" or "away"

        Returns:
            True if 2+ defenders with impact >= 6 are missing
        """
        defenders = self.get_players_by_position(team, "defender")
        critical_defenders = [p for p in defenders if p.impact_score >= 6]
        return len(critical_defenders) >= 2

    def get_position_impact_summary(self, team: str) -> dict[str, float]:
        """
        Get summary of impact scores by position for a team.

        Args:
            team: "home" or "away"

        Returns:
            Dictionary with position as key and total impact as value
        """
        players = self.home_player_impacts if team == "home" else self.away_player_impacts
        summary = {}
        for player in players:
            pos = player.position or "unknown"
            if pos not in summary:
                summary[pos] = 0.0
            summary[pos] += player.impact_score
        return summary

    def get_reason_impact_summary(self, team: str) -> dict[str, float]:
        """
        Get summary of impact scores by reason for a team.

        Args:
            team: "home" or "away"

        Returns:
            Dictionary with reason as key and total impact as value
        """
        players = self.home_player_impacts if team == "home" else self.away_player_impacts
        summary = {}
        for player in players:
            reason = player.reason or "unknown"
            if reason not in summary:
                summary[reason] = 0.0
            summary[reason] += player.impact_score
        return summary

    def get_combined_corner_avg(self) -> float | None:
        """Get combined corner average for both teams."""
        if self.home_corner_avg is not None and self.away_corner_avg is not None:
            return self.home_corner_avg + self.away_corner_avg
        return None

    def suggests_over_corners(self) -> bool:
        """
        Check if corner data suggests Over 9.5 Corners.

        V2.6: Now considers corners_signal from Perplexity for intelligent decisions.
        - If corners_signal is HIGH, suggests Over Corners regardless of combined avg
        - If corners_signal is MEDIUM, uses combined avg threshold
        - If corners_signal is LOW or UNKNOWN, relies on combined avg only
        """
        # First check if corners_signal is HIGH (strong signal from Perplexity)
        if SIGNAL_LEVEL_AVAILABLE and self.corners_signal == SignalLevel.HIGH:
            return True

        # Fallback to combined average calculation
        combined = self.get_combined_corner_avg()
        if combined is not None:
            # If corners_signal is MEDIUM, use a slightly lower threshold
            if SIGNAL_LEVEL_AVAILABLE and self.corners_signal == SignalLevel.MEDIUM:
                return combined >= (COMBINED_CORNERS_THRESHOLD - 0.5)  # 10.0 instead of 10.5
            # Otherwise use standard threshold
            return combined >= COMBINED_CORNERS_THRESHOLD
        return False

    def both_teams_low_scoring(self) -> bool:
        """Check if both teams are low scoring in recent form."""
        if self.home_form and self.away_form:
            return self.home_form.is_low_scoring() and self.away_form.is_low_scoring()
        return False

    # V13.1: Cards-related helper methods for intelligent market decisions
    def get_combined_cards_avg(self) -> float | None:
        """Get combined cards average for both teams."""
        if self.home_cards_avg is not None and self.away_cards_avg is not None:
            return self.home_cards_avg + self.away_cards_avg
        return None

    def suggests_over_cards(self) -> bool:
        """Check if cards data suggests Over 4.5 Cards market."""
        combined = self.get_combined_cards_avg()
        if combined is not None:
            return combined >= 4.5
        return False

    def is_cards_aggressive(self) -> bool:
        """Check if cards signal indicates aggressive play."""
        return self.cards_signal == CardsSignal.AGGRESSIVE

    def is_cards_disciplined(self) -> bool:
        """Check if cards signal indicates disciplined play."""
        return self.cards_signal == CardsSignal.DISCIPLINED

    def to_dict(self) -> dict[str, Any]:
        """
        Convert VerifiedData to dictionary for serialization.

        Handles nested dataclasses and enums properly for logging/contracts.
        V14.0 FIX: Complete serialization of all nested structures.
        """

        # Helper to serialize individual dataclass instances
        def serialize_dataclass(obj: Any) -> Any:
            if obj is None:
                return None
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            # Fallback: use __dict__ for dataclasses without to_dict
            if hasattr(obj, "__dict__"):
                result = {}
                for key, value in obj.__dict__.items():
                    result[key] = _serialize_value(value)
                return result
            return obj

        # Helper to serialize any value (handles enums, lists, dataclasses)
        def _serialize_value(value: Any) -> Any:
            if value is None:
                return None
            # Handle enums (convert to their value)
            if hasattr(value, "value"):
                return value.value
            # Handle lists (including lists of dataclasses)
            if isinstance(value, list):
                return [
                    serialize_dataclass(item) if hasattr(item, "__dict__") else item
                    for item in value
                ]
            # Handle dataclasses
            if hasattr(value, "__dict__"):
                return serialize_dataclass(value)
            return value

        return {
            # Player impacts
            "home_player_impacts": [serialize_dataclass(p) for p in self.home_player_impacts],
            "away_player_impacts": [serialize_dataclass(p) for p in self.away_player_impacts],
            "home_total_impact": self.home_total_impact,
            "away_total_impact": self.away_total_impact,
            # Form stats
            "home_form": serialize_dataclass(self.home_form),
            "away_form": serialize_dataclass(self.away_form),
            "form_confidence": self.form_confidence,
            # H2H stats
            "h2h": serialize_dataclass(self.h2h),
            "h2h_confidence": self.h2h_confidence,
            # Referee stats
            "referee": serialize_dataclass(self.referee),
            "referee_confidence": self.referee_confidence,
            # Corner stats
            "home_corner_avg": self.home_corner_avg,
            "away_corner_avg": self.away_corner_avg,
            "h2h_corner_avg": self.h2h_corner_avg,
            "corners_signal": self.corners_signal.value
            if hasattr(self.corners_signal, "value")
            else self.corners_signal,
            "corners_reasoning": self.corners_reasoning,
            "corner_confidence": self.corner_confidence,
            # Cards stats
            "home_cards_avg": self.home_cards_avg,
            "away_cards_avg": self.away_cards_avg,
            "cards_total_avg": self.cards_total_avg,
            "cards_signal": self.cards_signal.value
            if hasattr(self.cards_signal, "value")
            else self.cards_signal,
            "cards_reasoning": self.cards_reasoning,
            "cards_confidence": self.cards_confidence,
            # Goals per game
            "home_goals_per_game": self.home_goals_per_game,
            "away_goals_per_game": self.away_goals_per_game,
            # Expected Goals
            "home_xg": self.home_xg,
            "away_xg": self.away_xg,
            "home_xga": self.home_xga,
            "away_xga": self.away_xga,
            "xg_confidence": self.xg_confidence,
            # Metadata
            "data_confidence": self.data_confidence,
            "source": self.source,
        }


# ============================================
# OUTPUT DTO: VerificationResult
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
# ============================================


@dataclass
class VerificationResult:
    """
    Result of the verification process.

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """

    status: VerificationStatus

    # Score adjustment
    original_score: float
    adjusted_score: float
    score_adjustment_reason: str | None = None

    # Market recommendation
    original_market: str = ""
    recommended_market: str | None = None  # Set if status == CHANGE_MARKET
    alternative_markets: list[str] = field(default_factory=list)

    # Inconsistencies detected
    inconsistencies: list[str] = field(default_factory=list)

    # Confidence
    overall_confidence: str = "Low"  # Title Case: High, Medium, Low

    # Human-readable reasoning (in Italian)
    reasoning: str = ""

    # Raw verified data for logging
    verified_data: VerifiedData | None = None

    # Rejection reason (if status == REJECT)
    rejection_reason: str | None = None

    def is_confirmed(self) -> bool:
        """Check if verification confirmed the alert."""
        return self.status == VerificationStatus.CONFIRM

    def is_rejected(self) -> bool:
        """Check if verification rejected the alert."""
        return self.status == VerificationStatus.REJECT

    def should_change_market(self) -> bool:
        """Check if verification suggests changing market."""
        return self.status == VerificationStatus.CHANGE_MARKET

    def has_inconsistencies(self) -> bool:
        """Check if any inconsistencies were detected."""
        return len(self.inconsistencies) > 0

    def get_final_market(self) -> str:
        """Get the final market to use (recommended or original)."""
        if self.should_change_market() and self.recommended_market:
            return self.recommended_market
        return self.original_market

    def get_final_score(self) -> float:
        """Get the final score to use (adjusted or original)."""
        return self.adjusted_score

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization/logging.

        V14.0 FIX: Now includes verified_data with proper serialization
        of nested dataclasses and enums for complete logging/contracts.
        """
        return {
            "status": self.status.value,
            "original_score": self.original_score,
            "adjusted_score": self.adjusted_score,
            "score_adjustment_reason": self.score_adjustment_reason,
            "original_market": self.original_market,
            "recommended_market": self.recommended_market,
            "alternative_markets": self.alternative_markets,
            "inconsistencies": self.inconsistencies,
            "overall_confidence": self.overall_confidence,
            "reasoning": self.reasoning,
            "rejection_reason": self.rejection_reason,
            # V14.0 FIX: Include verified_data with proper serialization
            "verified_data": self.verified_data.to_dict() if self.verified_data else None,
        }

    def format_for_alert(self) -> str:
        """
        Format verification result for inclusion in alert message.

        Returns Italian-language summary suitable for Telegram alert.
        """
        lines = []

        if self.status == VerificationStatus.CONFIRM:
            lines.append("✅ VERIFICATO")
        elif self.status == VerificationStatus.REJECT:
            lines.append("❌ RESPINTO")
        elif self.status == VerificationStatus.CHANGE_MARKET:
            lines.append("🔄 MERCATO MODIFICATO")

        if self.score_adjustment_reason:
            lines.append(f"📊 {self.score_adjustment_reason}")

        if self.recommended_market and self.recommended_market != self.original_market:
            lines.append(f"🎯 Mercato: {self.original_market} → {self.recommended_market}")

        if self.inconsistencies:
            lines.append(f"⚠️ Incongruenze: {len(self.inconsistencies)}")

        lines.append(f"🔍 Confidenza: {self.overall_confidence}")

        return "\n".join(lines)


# ============================================
# FACTORY FUNCTIONS
# ============================================


def create_skip_result(request: VerificationRequest, reason: str) -> VerificationResult:
    """
    Create a result for skipped verification (score below threshold).

    Requirements: 7.1
    """
    return VerificationResult(
        status=VerificationStatus.CONFIRM,
        original_score=request.preliminary_score,
        adjusted_score=request.preliminary_score,
        score_adjustment_reason=None,
        original_market=request.suggested_market,
        recommended_market=None,
        alternative_markets=[],
        inconsistencies=[],
        overall_confidence="Low",
        reasoning=f"Verifica saltata: {reason}",
        verified_data=None,
        rejection_reason=None,
    )


def create_fallback_result(
    request: VerificationRequest, reason: str = "Provider non disponibili"
) -> VerificationResult:
    """
    Create a result when all providers fail.

    V7.3 FIX: Conservative approach for high-score alerts.
    If verification fails for alerts with score >= 9.0, REJECT them.
    This prevents false positives on critical alerts when we can't verify data.

    Requirements: 7.4
    """
    # V7.3 FIX: Conservative rejection for high-score alerts without verification
    if request.preliminary_score >= 9.0:
        return VerificationResult(
            status=VerificationStatus.REJECT,
            original_score=request.preliminary_score,
            adjusted_score=0.0,
            score_adjustment_reason=f"Verifica fallita per alert critico (score {request.preliminary_score})",
            original_market=request.suggested_market,
            recommended_market=None,
            alternative_markets=[],
            inconsistencies=["Verification timeout - troppo rischioso procedere senza conferma"],
            overall_confidence="Low",
            reasoning=f"Alert respinto: {reason}. Score troppo alto ({request.preliminary_score}) per procedere senza verifica.",
            verified_data=None,
            rejection_reason=f"Verification failed for critical alert (score >= 9.0): {reason}",
        )

    # For lower scores (< 9.0), proceed with caution but allow alert
    return VerificationResult(
        status=VerificationStatus.CONFIRM,
        original_score=request.preliminary_score,
        adjusted_score=request.preliminary_score,
        score_adjustment_reason=None,
        original_market=request.suggested_market,
        recommended_market=None,
        alternative_markets=[],
        inconsistencies=[],
        overall_confidence="Low",
        reasoning=f"Verifica non completata: {reason}. Procedo con dati esistenti (score < 9.0).",
        verified_data=None,
        rejection_reason=None,
    )


def create_rejection_result(
    request: VerificationRequest, reason: str, inconsistencies: list[str] = None
) -> VerificationResult:
    """
    Create a rejection result.

    Requirements: 6.3
    """
    return VerificationResult(
        status=VerificationStatus.REJECT,
        original_score=request.preliminary_score,
        adjusted_score=0.0,
        score_adjustment_reason=f"Respinto: {reason}",
        original_market=request.suggested_market,
        recommended_market=None,
        alternative_markets=[],
        inconsistencies=inconsistencies or [],
        overall_confidence="High",
        reasoning=f"Alert respinto: {reason}",
        verified_data=None,
        rejection_reason=reason,
    )


# ============================================
# TAVILY VERIFIER (API Client)
# Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 7.2, 7.3
# ============================================

import time

# Import Tavily provider
try:
    from src.ingestion.tavily_provider import TavilyProvider, get_tavily_provider

    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    TavilyProvider = None  # Type stub for annotations
    get_tavily_provider = None
    logger.warning("⚠️ Tavily provider not available")

# Import Perplexity provider for fallback
try:
    from src.ingestion.perplexity_provider import PerplexityProvider, get_perplexity_provider

    PERPLEXITY_AVAILABLE = True
except ImportError:
    PERPLEXITY_AVAILABLE = False
    PerplexityProvider = None  # Type stub for annotations
    get_perplexity_provider = None
    logger.warning("⚠️ Perplexity provider not available")

# V12.0: Import startup validator for intelligent feature detection
try:
    from src.utils.startup_validator import is_feature_disabled

    _STARTUP_VALIDATOR_AVAILABLE = True
except ImportError:
    _STARTUP_VALIDATOR_AVAILABLE = False
    logger.debug("Startup validator not available - all features enabled by default")

    def is_feature_disabled(feature: str) -> bool:
        """Fallback: no features are disabled if validator unavailable."""
        return False


# Import AI parser for response parsing
try:
    from src.utils.ai_parser import parse_ai_json

    AI_PARSER_AVAILABLE = True
except ImportError:
    AI_PARSER_AVAILABLE = False
    import json

    def parse_ai_json(text: str) -> dict:
        """Fallback JSON parser."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


# ============================================
# MULTI-SITE CONFIGURATION (V2.4)
# Priority order for each data type
# ============================================

SITE_PRIORITY = {
    # Team stats (corners, cards, goals per game)
    "team_stats": [
        "footystats.org",
        "soccerstats.com",
        "flashscore.com",
        "sofascore.com",
    ],
    # Player market values
    "player_values": [
        "transfermarkt.com",
        "sofifa.com",
    ],
    # Form last 5 matches
    "form": [
        "flashscore.com",
        "soccerway.com",
        "sofascore.com",
    ],
    # Referee stats
    "referee": [
        "transfermarkt.com",
        "soccerway.com",
    ],
    # H2H stats
    "h2h": [
        "footystats.org",
        "soccerstats.com",
        "flashscore.com",
    ],
}


# ============================================
# OPTIMIZED QUERY BUILDER (V2.4)
# Requirements: 1.1, 2.1, 3.1, 4.1, 5.1
# ============================================


class OptimizedQueryBuilder:
    """
    Builds optimized site-specific queries for Tavily.

    V2.4 Strategy: Multi-site fallback with progressive queries:
    1. Primary query on best site for each data type
    2. If data incomplete, fallback to secondary sites
    3. Combine results from multiple sources

    Site priority per data type:
    - Team stats: footystats.org > soccerstats.com > flashscore.com
    - Player values: transfermarkt.com > sofifa.com
    - Form: flashscore.com > soccerway.com > sofascore.com
    - Referee: transfermarkt.com > soccerway.com

    Requirements: 1.1, 2.1, 3.1, 4.1, 5.1
    """

    def __init__(
        self,
        home_team: str,
        away_team: str,
        players: list[str],
        referee_name: str | None = None,
        league: str = "Serie A",
    ):
        """
        Initialize query builder.

        Args:
            home_team: Home team name
            away_team: Away team name
            players: List of player names to get values for
            referee_name: Referee name (optional)
            league: League name for context
        """
        self.home = home_team
        self.away = away_team
        self.players = players or []
        self.referee = referee_name
        self.league = league

    def build_team_stats_query(self) -> str:
        """
        Q1: Team stats + H2H from FootyStats.

        Returns goals, corners, cards per game for both teams + H2H averages.
        """
        return f"""site:footystats.org {self.league} 2024-25:
{self.home} statistics: goals per game, corners per game, yellow cards per game
{self.away} statistics: goals per game, corners per game, yellow cards per game
{self.home} vs {self.away} head to head average goals cards corners"""

    def build_player_values_query(self) -> str:
        """
        Q2: Player market values from Transfermarkt.

        Returns market value in EUR millions for each player.
        """
        if not self.players:
            return f"""site:transfermarkt.com {self.home} {self.away} key players market value millions 2025"""

        players_str = ", ".join(self.players[:10])  # Limit to 10 players
        return f"""site:transfermarkt.com {players_str} market value millions 2025"""

    def build_referee_query(self) -> str:
        """
        Q3: Referee stats dedicated query.

        V2.3: No site restriction for better coverage across leagues.
        Returns yellow/red cards per game average.
        """
        ref_name = self.referee or f"{self.league} referee"
        return f"""{ref_name} referee {self.league} 2024-25 statistics yellow cards per game average red cards"""

    def build_form_query(self) -> str:
        """
        Q4: Form last 5 matches.

        V2.3: No site restriction for better coverage across leagues.
        V7.7: Enhanced with explicit W-D-L format request and site suggestions.
        Returns W/D/L, goals scored/conceded for both teams.
        """
        return f"""site:flashscore.com OR site:sofascore.com {self.home} {self.away} {self.league} last 5 matches form 2024-25:
{self.home}: recent form W-D-L, goals scored, goals conceded
{self.away}: recent form W-D-L, goals scored, goals conceded
Include: wins draws losses in last 5 games"""

    def build_xg_query(self) -> str:
        """
        V7.7: Q5: Expected Goals (xG) pre-match data.

        Fetches xG data from Understat or FBref for more accurate goal predictions.
        Returns xG, xGA (expected goals against) for both teams.
        """
        return f"""site:understat.com OR site:fbref.com {self.home} {self.away} {self.league} 2024-25:
{self.home} expected goals xG xGA statistics
{self.away} expected goals xG xGA statistics"""

    def get_all_queries(self) -> list[tuple]:
        """
        Get all queries with labels.

        Returns:
            List of tuples (label, query)
        """
        return [
            ("team_stats", self.build_team_stats_query()),
            ("player_values", self.build_player_values_query()),
            ("referee", self.build_referee_query()),
            ("form", self.build_form_query()),
            ("xg", self.build_xg_query()),  # V7.7: Add xG query
        ]

    # ============================================
    # V2.4: MULTI-SITE FALLBACK QUERIES
    # ============================================

    def build_team_stats_query_for_site(self, site: str) -> str:
        """
        Build team stats query for a specific site.

        Args:
            site: Target site (e.g., 'soccerstats.com', 'flashscore.com')

        Returns:
            Query string targeting the specified site
        """
        return f"""site:{site} {self.league} 2024-25:
{self.home} statistics: goals per game, corners per game, yellow cards per game
{self.away} statistics: goals per game, corners per game, yellow cards per game
{self.home} vs {self.away} head to head average goals cards corners"""

    def build_form_query_for_site(self, site: str) -> str:
        """
        Build form query for a specific site.

        Args:
            site: Target site (e.g., 'flashscore.com', 'soccerway.com')

        Returns:
            Query string targeting the specified site
        """
        return f"""site:{site} {self.home} {self.away} {self.league} last 5 matches:
{self.home}: goals scored, goals conceded, wins draws losses form
{self.away}: goals scored, goals conceded, wins draws losses form"""

    def build_h2h_query_for_site(self, site: str) -> str:
        """
        Build H2H query for a specific site.

        Args:
            site: Target site

        Returns:
            Query string targeting the specified site
        """
        return f"""site:{site} {self.home} vs {self.away} head to head history:
last 5 meetings average goals corners cards results"""

    def get_fallback_queries(self, missing_data: list[str]) -> list[tuple]:
        """
        Get fallback queries for missing data types.

        Args:
            missing_data: List of data types that are missing
                         ('team_stats', 'form', 'h2h', 'corners')

        Returns:
            List of tuples (label, query) for fallback queries
        """
        queries = []

        for data_type in missing_data:
            if data_type == "team_stats" or data_type == "corners":
                # Try secondary sites for team stats
                for site in SITE_PRIORITY.get("team_stats", [])[
                    1:3
                ]:  # Skip primary, try 2 fallbacks
                    queries.append(
                        (
                            f"team_stats_{site.split('.')[0]}",
                            self.build_team_stats_query_for_site(site),
                        )
                    )
                    break  # Only one fallback per type

            elif data_type == "form":
                # Try secondary sites for form
                for site in SITE_PRIORITY.get("form", [])[:2]:
                    queries.append(
                        (f"form_{site.split('.')[0]}", self.build_form_query_for_site(site))
                    )
                    break

            elif data_type == "h2h":
                # Try secondary sites for H2H
                for site in SITE_PRIORITY.get("h2h", [])[1:3]:
                    queries.append(
                        (f"h2h_{site.split('.')[0]}", self.build_h2h_query_for_site(site))
                    )
                    break

        return queries


# ============================================
# OPTIMIZED RESPONSE PARSER (V2.2)
# Requirements: 1.4, 2.4, 3.5, 4.4, 5.4
# ============================================

# Import text normalizer for multi-language support
try:
    from src.utils.text_normalizer import (
        FUZZY_AVAILABLE,
        REFEREE_CARD_PATTERNS,
        find_team_in_text,
        fuzzy_match_player,
        fuzzy_match_team,
        get_multilang_form_pattern,
        get_value_patterns,
        normalize_for_matching,
    )

    TEXT_NORMALIZER_AVAILABLE = True
except ImportError:
    TEXT_NORMALIZER_AVAILABLE = False
    FUZZY_AVAILABLE = False


class OptimizedResponseParser:
    """
    Intelligent parser for extracting data from Tavily responses.

    V2.2 Features:
    - Multi-language support (EN, ES, PT, DE, FR, IT, TR, NL, PL)
    - Fuzzy matching for team/player names (handles typos, accents)
    - Unicode normalization (Turkish ç, German ü, Greek letters)
    - Multiple currency support (€, £, $)
    - Team aliases (Galatasaray = Cimbom = Aslan)

    Supports all leagues:
    - Turkey, Greece, Argentina, Mexico, Brazil
    - Japan, China, Saudi Arabia, Australia
    - All European leagues

    Requirements: 1.4, 2.4, 3.5, 4.4, 5.4
    """

    def __init__(
        self,
        home_team: str,
        away_team: str,
        referee_name: str | None,
        players: list[str],
        home_team_injury_impact: Any = None,
        away_team_injury_impact: Any = None,
    ):
        """
        Initialize parser.

        Args:
            home_team: Home team name
            away_team: Away team name
            referee_name: Referee name (optional)
            players: List of player names
            home_team_injury_impact: Optional TeamInjuryImpact with detailed player data
            away_team_injury_impact: Optional TeamInjuryImpact with detailed player data
        """
        self.home_original = home_team
        self.away_original = away_team
        self.referee_original = referee_name or ""
        self.home_team_injury_impact = home_team_injury_impact
        self.away_team_injury_impact = away_team_injury_impact

        # Intelligent type validation for players
        # Handle edge cases: None, string, or other types
        if players is None:
            self.players_original = []
            logger.warning("⚠️ [OptimizedResponseParser] players is None, using empty list")
        elif isinstance(players, str):
            # If a string was passed instead of a list, log warning and convert
            logger.warning(
                f"⚠️ [OptimizedResponseParser] players is a string, not a list: '{players}'. Converting to list with single element."
            )
            self.players_original = [players]
        elif not isinstance(players, list):
            # If another type was passed, log warning and convert to list
            logger.warning(
                f"⚠️ [OptimizedResponseParser] players has unexpected type {type(players).__name__}, converting to list."
            )
            self.players_original = list(players) if hasattr(players, "__iter__") else []
        else:
            self.players_original = players

        # Normalized versions for matching
        if TEXT_NORMALIZER_AVAILABLE:
            self.home = normalize_for_matching(home_team)
            self.away = normalize_for_matching(away_team)
            self.referee = normalize_for_matching(referee_name or "")
            self.players = [normalize_for_matching(p) for p in self.players_original]
        else:
            self.home = home_team.lower()
            self.away = away_team.lower()
            self.referee = (referee_name or "").lower()
            self.players = [p.lower() for p in self.players_original]

    def parse_to_verified_data(
        self, combined_text: str, request: "VerificationRequest"
    ) -> "VerifiedData":
        """
        Parse combined text into VerifiedData structure.

        Args:
            combined_text: Combined text from all query responses
            request: Original verification request

        Returns:
            VerifiedData populated with extracted data
        """

        # Normalize text for matching
        if TEXT_NORMALIZER_AVAILABLE:
            text = normalize_for_matching(combined_text)
        else:
            text = combined_text.lower()

        verified = VerifiedData(source="tavily_v2")

        # 1. Parse player values and convert to impacts
        player_values = self._parse_player_values(combined_text)

        # Convert market values to PlayerImpact objects
        # V13.0: Use injury_impact data when available for position, role, reason
        for name in request.home_missing_players:
            value = self._find_player_value(name, player_values)
            impact_score = market_value_to_impact(value) if value else 5

            # Try to get detailed data from injury_impact_engine
            player_details = self._get_player_details_from_injury_impact(
                name, self.home_team_injury_impact
            )

            verified.home_player_impacts.append(
                PlayerImpact(
                    name=name,
                    impact_score=impact_score,
                    role=player_details.get("role")
                    if player_details
                    else ("starter" if impact_score >= 7 else "unknown"),
                    position=player_details.get("position") if player_details else None,
                    reason=player_details.get("reason") if player_details else None,
                )
            )

        for name in request.away_missing_players:
            value = self._find_player_value(name, player_values)
            impact_score = market_value_to_impact(value) if value else 5

            # Try to get detailed data from injury_impact_engine
            player_details = self._get_player_details_from_injury_impact(
                name, self.away_team_injury_impact
            )

            verified.away_player_impacts.append(
                PlayerImpact(
                    name=name,
                    impact_score=impact_score,
                    role=player_details.get("role")
                    if player_details
                    else ("starter" if impact_score >= 7 else "unknown"),
                    position=player_details.get("position") if player_details else None,
                    reason=player_details.get("reason") if player_details else None,
                )
            )

        # Calculate totals
        verified.home_total_impact = sum(p.impact_score for p in verified.home_player_impacts)
        verified.away_total_impact = sum(p.impact_score for p in verified.away_player_impacts)

        # 2. Parse team season stats
        home_stats = self._parse_team_stats(text, self.home_original)
        away_stats = self._parse_team_stats(text, self.away_original)

        # Set corner averages
        verified.home_corner_avg = safe_dict_get(home_stats, "corners", default=None)
        verified.away_corner_avg = safe_dict_get(away_stats, "corners", default=None)
        verified.corner_confidence = (
            "Medium" if verified.home_corner_avg or verified.away_corner_avg else "Low"
        )

        # V7.2: Set goals per game (season average) - separate from form goals_scored
        verified.home_goals_per_game = safe_dict_get(home_stats, "goals", default=None)
        verified.away_goals_per_game = safe_dict_get(away_stats, "goals", default=None)

        # V7.7: Parse xG stats
        home_xg_stats = self._parse_xg_stats(text, self.home_original)
        away_xg_stats = self._parse_xg_stats(text, self.away_original)

        verified.home_xg = safe_dict_get(home_xg_stats, "xg", default=None)
        verified.away_xg = safe_dict_get(away_xg_stats, "xg", default=None)
        verified.home_xga = safe_dict_get(home_xg_stats, "xga", default=None)
        verified.away_xga = safe_dict_get(away_xg_stats, "xga", default=None)
        verified.xg_confidence = "Medium" if (verified.home_xg or verified.away_xg) else "Low"

        if verified.home_xg or verified.away_xg:
            logger.info(f"   📊 xG extracted: Home={verified.home_xg}, Away={verified.away_xg}")

        # 3. Parse H2H stats
        h2h_data = self._parse_h2h_stats(text)
        if h2h_data:
            verified.h2h = H2HStats(
                matches_analyzed=5,
                avg_goals=safe_dict_get(h2h_data, "goals", default=0.0),
                avg_cards=safe_dict_get(h2h_data, "cards", default=0.0),
                avg_corners=safe_dict_get(h2h_data, "corners", default=0.0),
            )
            verified.h2h_corner_avg = safe_dict_get(h2h_data, "corners", default=None)
            verified.h2h_confidence = "Medium" if verified.h2h.has_data() else "Low"

        # 4. Parse referee stats
        ref_data = self._parse_referee_stats(text, combined_text)
        cards_per_game = safe_dict_get(ref_data, "cards_per_game", default=None)
        if ref_data and cards_per_game:
            verified.referee = RefereeStats(
                name=request.fotmob_referee_name or self.referee_original,
                cards_per_game=cards_per_game,
            )
            verified.referee_confidence = "Medium"

        # 5. Parse form stats (multi-language)
        # V7.1: First try FotMob form data if available (most reliable)
        verified.home_form = self._parse_fotmob_form(request.home_form_last5)
        verified.away_form = self._parse_fotmob_form(request.away_form_last5)

        # Fallback to Tavily text parsing if FotMob form not available
        if verified.home_form is None:
            home_form = self._parse_form_stats(text, combined_text, self.home_original)
            if home_form:
                verified.home_form = FormStats(
                    # V7.2: goals_scored is now total (not per-game), no multiplication needed
                    goals_scored=int(safe_dict_get(home_form, "goals_scored", default=0)),
                    goals_conceded=int(safe_dict_get(home_form, "goals_conceded", default=0)),
                    wins=safe_dict_get(home_form, "wins", default=0),
                    draws=safe_dict_get(home_form, "draws", default=0),
                    losses=safe_dict_get(home_form, "losses", default=0),
                )

        if verified.away_form is None:
            away_form = self._parse_form_stats(text, combined_text, self.away_original)
            if away_form:
                verified.away_form = FormStats(
                    # V7.2: goals_scored is now total (not per-game), no multiplication needed
                    goals_scored=int(safe_dict_get(away_form, "goals_scored", default=0)),
                    goals_conceded=int(safe_dict_get(away_form, "goals_conceded", default=0)),
                    wins=safe_dict_get(away_form, "wins", default=0),
                    draws=safe_dict_get(away_form, "draws", default=0),
                    losses=safe_dict_get(away_form, "losses", default=0),
                )

        # V7.1: High confidence if FotMob form available, Medium if parsed from text
        has_fotmob_form = request.home_form_last5 or request.away_form_last5
        verified.form_confidence = (
            "High"
            if has_fotmob_form
            else ("Medium" if verified.home_form or verified.away_form else "Low")
        )

        # Calculate overall confidence (unified algorithm across all providers)
        confidence_scores = [
            verified.form_confidence,
            verified.h2h_confidence,
            verified.referee_confidence,
            verified.corner_confidence,
        ]
        high_count = sum(1 for c in confidence_scores if c == "High")
        medium_count = sum(1 for c in confidence_scores if c == "Medium")

        if high_count >= 2:
            verified.data_confidence = "High"
        elif high_count >= 1 or medium_count >= 2:
            verified.data_confidence = "Medium"
        else:
            verified.data_confidence = "Low"

        return verified

    def _find_player_value(self, player_name: str, values: dict[str, float]) -> float | None:
        """
        Find player value using fuzzy matching.

        Args:
            player_name: Player name to find
            values: Dict of extracted values

        Returns:
            Value in millions or None

        Performance optimization: Early exit on exact match, limits fuzzy matching
        to reasonable number of candidates.
        """
        if not values:
            return None

        if TEXT_NORMALIZER_AVAILABLE:
            player_norm = normalize_for_matching(player_name)
        else:
            player_norm = player_name.lower()

        # Exact match first - fastest path
        if player_norm in values:
            return values[player_norm]

        # Try partial match on name parts - second fastest path
        name_parts = player_norm.split()
        for part in name_parts:
            if len(part) >= 4:  # Minimum 4 chars
                for key, val in values.items():
                    if part in key or key in part:
                        return val

        # Fuzzy match if available - most expensive, optimize it
        if TEXT_NORMALIZER_AVAILABLE and FUZZY_AVAILABLE:
            from thefuzz import fuzz

            # Performance optimization: Limit fuzzy matching to reasonable number of candidates
            # If values dict is very large (>50), limit to first 50 to avoid O(n) slowdown
            values_items = list(values.items())
            if len(values_items) > 50:
                logger.warning(
                    f"⚡ [OptimizedResponseParser] Too many values ({len(values_items)}), limiting fuzzy matching to first 50"
                )
                values_items = values_items[:50]

            best_score = 0
            best_value = None

            for key, val in values_items:
                score = fuzz.token_set_ratio(player_norm, key)
                if score > best_score and score >= 70:
                    best_score = score
                    best_value = val
                    # Early exit if we find a very high confidence match
                    if score >= 90:
                        break

            return best_value

        return None

    def _parse_player_values(self, text: str) -> dict[str, float]:
        """
        Extract player market values with multi-currency support.

        Supports: €, £, $ in millions and thousands

        Performance optimization: Uses set-based lookup for O(1) matching
        instead of O(n) loop when possible.
        """
        import re

        values = {}

        # Performance optimization: If many players, use set-based lookup
        # This reduces complexity from O(n*m) to O(n) where n=matches, m=players
        use_set_lookup = len(self.players) > 15
        if use_set_lookup:
            logger.info(
                f"⚡ [OptimizedResponseParser] Using set-based lookup for {len(self.players)} players"
            )
            players_set = set(self.players)

        if TEXT_NORMALIZER_AVAILABLE:
            # Use comprehensive patterns from text_normalizer
            for pattern, multiplier in get_value_patterns():
                matches = re.findall(pattern, text, re.I)
                for match in matches:
                    if len(match) == 2:
                        name, value = match
                        if not name.isdigit():
                            name_norm = normalize_for_matching(name)
                            value_float = float(value) * multiplier

                            # Match against known players - optimized approach
                            if use_set_lookup:
                                # Fast path: Direct set lookup for exact matches
                                if name_norm in players_set:
                                    values[name_norm] = value_float
                                else:
                                    # Fallback to fuzzy matching only if needed
                                    for player in self.players:
                                        if self._names_match(name_norm, player):
                                            values[player] = value_float
                                            break
                            else:
                                # Standard path: Loop through all players
                                for player in self.players:
                                    if self._names_match(name_norm, player):
                                        values[player] = value_float
                                        break
        else:
            # Fallback to basic patterns
            patterns = [
                (r"(\w+(?:\s+\w+)?)'?s?\s*(?:market\s*)?value\s*(?:is\s*)?[€£$](\d+)\s*m", 1.0),
                (r"(\w+(?:\s+\w+)?)'?s?\s*(?:market\s*)?value\s*(?:is\s*)?[€£$](\d+)\s*k", 0.001),
            ]

            for pattern, multiplier in patterns:
                matches = re.findall(pattern, text, re.I)
                for match in matches:
                    if len(match) == 2:
                        name, value = match
                        name_lower = name.lower()
                        value_float = float(value) * multiplier

                        if use_set_lookup:
                            # Fast path: Check if any player name is in the extracted name
                            for player in self.players:
                                if player in name_lower or name_lower in player:
                                    values[player] = value_float
                                    break
                        else:
                            # Standard path
                            for player in self.players:
                                if any(part in name_lower for part in player.split()):
                                    values[player] = value_float
                                    break

        return values

    def _get_player_details_from_injury_impact(
        self, player_name: str, team_injury_impact: Any
    ) -> dict[str, Any] | None:
        """
        Extract player details (position, role, reason) from TeamInjuryImpact data.

        V13.0: This method bridges the gap between injury_impact_engine and verification_layer
        by providing detailed player information that was previously lost.

        ROOT CAUSE FIX: InjuryPlayerImpact now validates that position and role are never None
        during initialization (via __post_init__), so we can safely extract .value without
        None checks for valid objects. However, we still add defensive programming to handle
        edge cases (e.g., non-InjuryPlayerImpact objects passed by mistake).

        Args:
            player_name: Name of the player to look up
            team_injury_impact: TeamInjuryImpact object with detailed player data

        Returns:
            Dictionary with position, role, and reason if found, None otherwise
        """
        if not team_injury_impact or not player_name:
            return None

        # Check if team_injury_impact has players attribute
        if not hasattr(team_injury_impact, "players"):
            return None

        # Normalize player name for matching
        # Remove punctuation for better matching (e.g., "Lee," vs "Lee")
        player_name_normalized = re.sub(r"[,\.\']", "", player_name.lower().strip())

        # Search for matching player in injury_impact data
        for player in team_injury_impact.players:
            if not hasattr(player, "name"):
                continue

            # Normalize stored player name
            # Remove punctuation for better matching (e.g., "Lee," vs "Lee")
            stored_name = re.sub(r"[,\.\']", "", player.name.lower().strip())

            # Check for exact match
            if player_name_normalized == stored_name:
                # ROOT CAUSE FIX: Extract position and role once, validate they're not None
                position_attr = getattr(player, "position", None)
                role_attr = getattr(player, "role", None)

                # Defensive programming: Handle edge cases where position/role might be None
                # (e.g., if someone passes a non-InjuryPlayerImpact object)
                position_value = (
                    position_attr.value
                    if position_attr and hasattr(position_attr, "value")
                    else "unknown"
                )
                role_value = (
                    role_attr.value if role_attr and hasattr(role_attr, "value") else "unknown"
                )

                return {
                    "position": position_value,
                    "role": role_value,
                    "reason": getattr(player, "reason", None),
                }

            # Check for partial match (handle different name formats)
            # e.g., "John Smith" vs "Smith, John"
            name_parts = set(player_name_normalized.split())
            stored_parts = set(stored_name.split())

            # If names share significant parts, consider it a match
            # This handles different name formats (e.g., "John Smith" vs "Smith, John")
            # and short names (e.g., "Lee" vs "Lee, Min")
            if name_parts & stored_parts:  # Intersection
                # ROOT CAUSE FIX: Extract position and role once, validate they're not None
                position_attr = getattr(player, "position", None)
                role_attr = getattr(player, "role", None)

                # Defensive programming: Handle edge cases where position/role might be None
                # (e.g., if someone passes a non-InjuryPlayerImpact object)
                position_value = (
                    position_attr.value
                    if position_attr and hasattr(position_attr, "value")
                    else "unknown"
                )
                role_value = (
                    role_attr.value if role_attr and hasattr(role_attr, "value") else "unknown"
                )

                return {
                    "position": position_value,
                    "role": role_value,
                    "reason": getattr(player, "reason", None),
                }

        return None

    def _names_match(self, name1: str, name2: str, threshold: int = 70) -> bool:
        """Check if two names match using fuzzy logic."""
        if not name1 or not name2:
            return False

        # Exact match
        if name1 == name2:
            return True

        # Partial match on parts
        parts1 = set(name1.split())
        parts2 = set(name2.split())

        # If any significant part matches
        for p1 in parts1:
            if len(p1) >= 4:
                for p2 in parts2:
                    if len(p2) >= 4 and (p1 in p2 or p2 in p1):
                        return True

        # Fuzzy match
        if TEXT_NORMALIZER_AVAILABLE and FUZZY_AVAILABLE:
            from thefuzz import fuzz

            return fuzz.token_set_ratio(name1, name2) >= threshold

        return False

    def _parse_team_stats(self, text: str, team: str) -> dict[str, float]:
        """Extract team season stats with fuzzy team matching."""
        import re

        stats = {}

        # Find team in text using fuzzy matching
        if TEXT_NORMALIZER_AVAILABLE:
            found, _ = find_team_in_text(team, text)
            if not found:
                return stats
            team_pattern = re.escape(normalize_for_matching(team))
        else:
            team_pattern = re.escape(team.lower())

        # Goals per game
        goals_patterns = [
            rf"{team_pattern}[^.]*?(\d+\.?\d*)\s*goals?\s*per\s*(?:game|match)",
            rf"{team_pattern}[^.]*?averag\w*\s*(\d+\.?\d*)\s*goals?",
        ]
        for pattern in goals_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                stats["goals"] = float(match.group(1))
                break

        # Corners per game - V2.3: Fixed decimal pattern
        # Handles: "Team average 5.7 corners per game"
        corners_patterns = [
            # Direct pattern with decimals: "X.Y corners per game" after team name
            rf"{team_pattern}.*?(\d+\.?\d*)\s*corners?\s*per\s*(?:game|match)",
            rf"{team_pattern}.*?averag\w*\s*(\d+\.?\d*)\s*corners?",
        ]
        for pattern in corners_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                val = float(match.group(1))
                # Sanity check: corners per game typically 3-12
                if 0 < val <= 15:
                    stats["corners"] = val
                    break

        # Fallback: sentence-based extraction
        if "corners" not in stats:
            # Find sentence containing team
            sentences = text.split(".")
            for sentence in sentences:
                if team_pattern in sentence.lower() or (
                    TEXT_NORMALIZER_AVAILABLE
                    and normalize_for_matching(team) in normalize_for_matching(sentence)
                ):
                    corner_match = re.search(
                        r"(\d+)\s*corners?\s*per\s*(?:game|match)", sentence, re.I
                    )
                    if corner_match:
                        val = float(corner_match.group(1))
                        if 0 < val <= 15:
                            stats["corners"] = val
                            break

        # Cards per game
        cards_patterns = [
            rf"{team_pattern}[^.]*?(\d+\.?\d*)\s*(?:yellow\s*)?cards?\s*per\s*(?:game|match)",
            rf"{team_pattern}[^.]*?averag\w*\s*(\d+\.?\d*)\s*(?:yellow\s*)?cards?",
        ]
        for pattern in cards_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                stats["cards"] = float(match.group(1))
                break

        return stats

    def _parse_xg_stats(self, text: str, team: str) -> dict[str, float]:
        """
        V7.7: Extract Expected Goals (xG) stats for a team.

        Looks for patterns like:
        - "Team xG: 1.45"
        - "Team expected goals 1.8 per game"
        - "xG 1.5 | xGA 1.2"

        Args:
            text: Text to search in
            team: Team name

        Returns:
            Dict with 'xg' and 'xga' keys if found
        """
        import re

        stats = {}

        # Normalize team name for matching
        if TEXT_NORMALIZER_AVAILABLE:
            found, _ = find_team_in_text(team, text)
            if not found:
                return stats
            team_pattern = re.escape(normalize_for_matching(team))
        else:
            team_pattern = re.escape(team.lower())

        text_lower = text.lower()

        # xG patterns (expected goals scored)
        xg_patterns = [
            rf"{team_pattern}[^.]*?xg[:\s]+(\d+\.?\d*)",
            rf"{team_pattern}[^.]*?expected\s*goals?\s*\(?xg\)?[:\s]+(\d+\.?\d*)",
            rf"{team_pattern}[^.]*?expected\s*goals?[:\s]+(\d+\.?\d*)",
            rf"{team_pattern}[^.]*?(\d+\.?\d*)\s*xg\s*per\s*(?:game|match)",
            rf"xg[:\s]+(\d+\.?\d*).*?{team_pattern}",
        ]
        for pattern in xg_patterns:
            match = re.search(pattern, text_lower, re.I)
            if match:
                val = float(match.group(1))
                # Sanity check: xG per game typically 0.5-3.5
                if 0.1 < val <= 4.0:
                    stats["xg"] = val
                    break

        # xGA patterns (expected goals against)
        xga_patterns = [
            rf"{team_pattern}[^.]*?xga[:\s]+(\d+\.?\d*)",
            rf"{team_pattern}[^.]*?expected\s*goals?\s*against[:\s]+(\d+\.?\d*)",
            rf"{team_pattern}[^.]*?(\d+\.?\d*)\s*xga\s*per\s*(?:game|match)",
            rf"xga[:\s]+(\d+\.?\d*).*?{team_pattern}",
        ]
        for pattern in xga_patterns:
            match = re.search(pattern, text_lower, re.I)
            if match:
                val = float(match.group(1))
                if 0.1 < val <= 4.0:
                    stats["xga"] = val
                    break

        return stats

    def _parse_h2h_stats(self, text: str) -> dict[str, float] | None:
        """Extract H2H stats."""
        import re

        h2h = {}

        # H2H goals
        h2h_goals_patterns = [
            r"(?:head[- ]to[- ]head|h2h)[^.]*?(\d+\.?\d*)\s*goals?",
            r"(?:average|avg)[^.]*?(\d+\.?\d*)\s*goals?\s*(?:per\s*)?(?:match|game)",
        ]
        for pattern in h2h_goals_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                h2h["goals"] = float(match.group(1))
                break

        # H2H corners
        h2h_corners = re.search(
            r"(?:head[- ]to[- ]head|h2h)[^.]*?(\d+\.?\d*)\s*corners?", text, re.I
        )
        if h2h_corners:
            h2h["corners"] = float(h2h_corners.group(1))

        # H2H cards
        h2h_cards = re.search(
            r"(?:head[- ]to[- ]head|h2h)[^.]*?(\d+\.?\d*)\s*(?:yellow\s*)?cards?", text, re.I
        )
        if h2h_cards:
            h2h["cards"] = float(h2h_cards.group(1))

        return h2h if h2h else None

    def _parse_referee_stats(self, text_norm: str, text_original: str) -> dict[str, float] | None:
        """
        Extract referee stats with multi-language support.

        V7.1: Enhanced to find referee even without known name.
        """
        import re

        # CASE 1: We have a known referee name - search for it
        if self.referee:
            # Try to find referee name in text
            ref_parts = self.referee.split()

            # Search patterns in both normalized and original text
            for search_text in [text_norm, text_original.lower()]:
                for ref_pattern in [self.referee] + [p for p in ref_parts if len(p) > 3]:
                    # Try multi-language patterns
                    if TEXT_NORMALIZER_AVAILABLE:
                        for pattern in REFEREE_CARD_PATTERNS:
                            full_pattern = rf"{re.escape(ref_pattern)}[^.]*?{pattern}"
                            match = re.search(full_pattern, search_text, re.I)
                            if match:
                                return {"cards_per_game": float(match.group(1))}
                    else:
                        # Basic English patterns
                        patterns = [
                            rf"{re.escape(ref_pattern)}[^.]*?(\d+\.?\d*)\s*(?:yellow\s*)?cards?\s*(?:per\s*(?:game|match)|average)",
                            rf"{re.escape(ref_pattern)}[^.]*?average[^.]*?(\d+\.?\d*)\s*(?:yellow\s*)?cards?",
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, search_text, re.I)
                            if match:
                                return {"cards_per_game": float(match.group(1))}

        # CASE 2: V7.1 - No known referee name, search for generic referee patterns
        referee_patterns = [
            r"(?:the\s+)?referee\s+averages?\s+(\d+\.?\d*)\s*(?:yellow\s*)?cards?",
            r"referee[:\s]+[^.]{0,30}?(\d+\.?\d*)\s*(?:cards?|yellow|bookings?)\s*(?:per|/)\s*(?:game|match)",
            r"(?:match\s+)?official[:\s]+[^.]*?(\d+\.?\d*)\s*cards?\s*(?:per|average|avg)",
            r"(\d+\.?\d*)\s*(?:yellow\s*)?cards?\s*per\s*(?:game|match)",
            r"referee[^.]{0,50}averages?\s+(\d+\.?\d*)\s*(?:bookings?|cards?)",
            r"(?:yellow\s*)?cards?\s*(?:per\s*(?:game|match)|average)[:\s]+(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*cards?/(?:game|match)",
            r"booking[s]?\s*(?:average|rate)[:\s]+(\d+\.?\d*)",
        ]

        for search_text in [text_norm, text_original.lower()]:
            for pattern in referee_patterns:
                match = re.search(pattern, search_text, re.I)
                if match:
                    try:
                        cards_per_game = float(match.group(1))
                        if 0.5 <= cards_per_game <= 10:
                            return {"cards_per_game": cards_per_game}
                    except (ValueError, TypeError):
                        continue

        return None

    def _parse_fotmob_form(self, form_string: str | None) -> FormStats | None:
        """
        V7.1: Parse form from FotMob format (e.g., "WWDLL" or "W-W-D-L-L").

        FotMob provides form as a string of W/D/L characters.
        This is more reliable than parsing from Tavily text.

        Args:
            form_string: Form string from FotMob (e.g., "WWDLL")

        Returns:
            FormStats or None if form_string is empty/invalid
        """
        if not form_string or not form_string.strip():
            return None

        # Normalize: remove dashes, spaces, convert to uppercase
        form_clean = form_string.upper().replace("-", "").replace(" ", "")

        # Count W/D/L
        wins = form_clean.count("W")
        draws = form_clean.count("D")
        losses = form_clean.count("L")

        # Validate we have at least some results
        if wins + draws + losses == 0:
            return None

        return FormStats(
            goals_scored=0,  # FotMob form string doesn't include goals
            goals_conceded=0,
            wins=wins,
            draws=draws,
            losses=losses,
        )

    def _parse_form_stats(
        self, text_norm: str, text_original: str, team: str
    ) -> dict[str, Any] | None:
        """
        Extract form stats with multi-language support.

        Supports: English, Spanish, Portuguese, German, French, Italian, Turkish, Dutch, Polish
        V2.2.1: Added support for written numbers (one, two, three, etc.)
        V2.2.2: Added flexible pattern for combined team sentences
        """
        import re

        # Word to number mapping
        WORD_TO_NUM = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            # Spanish
            "cero": 0,
            "uno": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
            "cinco": 5,
            # Portuguese
            "um": 1,
            "dois": 2,
            "três": 3,
            "quatro": 4,
        }

        def parse_number(s: str) -> int | None:
            """Parse number from digit or word."""
            if not s:
                return None
            s = s.strip().lower()
            if s.isdigit():
                return int(s)
            return WORD_TO_NUM.get(s)

        if TEXT_NORMALIZER_AVAILABLE:
            team_norm = normalize_for_matching(team)
        else:
            team_norm = team.lower()

        team_pattern = re.escape(team_norm)

        # Try multi-language pattern first
        if TEXT_NORMALIZER_AVAILABLE:
            multilang_pattern = get_multilang_form_pattern()

            # Search for team followed by form stats
            for search_text in [text_norm, text_original.lower()]:
                # Find team position
                team_match = re.search(team_pattern, search_text, re.I)
                if team_match:
                    # Search for form pattern after team name
                    remaining_text = search_text[team_match.start() :]
                    form_match = re.search(multilang_pattern, remaining_text, re.I)

                    if form_match:
                        # Groups: won_word, wins, drew_word, draws, lost_word, losses
                        wins = int(form_match.group(2))
                        draws = int(form_match.group(4))
                        losses = int(form_match.group(6))

                        # V7.2: Try to find goals in the same context
                        goals_scored = 0.0
                        goals_conceded = 0.0

                        # Try combined pattern first
                        goals_pattern = rf"{team_pattern}[^.]*?scor(?:ed|ing)\s*(\d+\.?\d*)[^.]*?conced(?:ed|ing)\s*(\d+\.?\d*)"
                        goals_match = re.search(goals_pattern, search_text, re.I)

                        if goals_match:
                            goals_scored = float(goals_match.group(1))
                            goals_conceded = float(goals_match.group(2))
                        else:
                            # Fallback: try separate patterns
                            scored_pattern = rf"{team_pattern}[^.]*?scor(?:ed|ing)\s*(\d+\.?\d*)"
                            conceded_pattern = (
                                rf"{team_pattern}[^.]*?conced(?:ed|ing)\s*(\d+\.?\d*)"
                            )

                            scored_match = re.search(scored_pattern, search_text, re.I)
                            conceded_match = re.search(conceded_pattern, search_text, re.I)

                            if scored_match:
                                goals_scored = float(scored_match.group(1))
                            if conceded_match:
                                goals_conceded = float(conceded_match.group(1))

                        return {
                            "wins": wins,
                            "draws": draws,
                            "losses": losses,
                            "goals_scored": goals_scored,
                            "goals_conceded": goals_conceded,
                        }

        # V2.2.1: Pattern for written numbers (won two, drew one, lost zero)
        word_num_pattern = r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)"

        # Fallback to English patterns - now supports both digits and words
        patterns = [
            # Standard: "Team won 4, drew 0, lost 1"
            rf"{team_pattern}\s*won\s*({word_num_pattern})[^.]*?drew\s*({word_num_pattern})[^.]*?lost\s*({word_num_pattern})",
            # V2.5: "Team has won 4, drawn 1, and lost 0" (with "has" and past participle)
            rf"{team_pattern}\s*(?:has\s+)?won\s*({word_num_pattern})[^.]*?(?:has\s+)?(?:drew|drawn)\s*({word_num_pattern})[^.]*?(?:has\s+)?(?:lost|and\s+lost)\s*({word_num_pattern})",
            # Compact: "Team: W4 D0 L1"
            rf"{team_pattern}[:\s-]*(?:W|wins?)?\s*(\d+)[^.]*?(?:D|draws?)?\s*(\d+)[^.]*?(?:L|loss(?:es)?)?\s*(\d+)",
            # Reverse order: "Team lost 1, drew 0, won 4"
            rf"{team_pattern}\s*lost\s*({word_num_pattern})[^.]*?drew\s*({word_num_pattern})[^.]*?won\s*({word_num_pattern})",
        ]

        # V2.5: Also normalize text_original for accent-insensitive matching
        if TEXT_NORMALIZER_AVAILABLE:
            text_original_norm = normalize_for_matching(text_original)
        else:
            text_original_norm = text_original.lower()

        for search_text in [text_norm, text_original.lower(), text_original_norm]:
            for i, pattern in enumerate(patterns):
                match = re.search(pattern, search_text, re.I)
                if match:
                    if i == 3:  # Reverse order pattern (now index 3)
                        losses = parse_number(match.group(1))
                        draws = parse_number(match.group(2))
                        wins = parse_number(match.group(3))
                    else:
                        wins = parse_number(match.group(1))
                        draws = parse_number(match.group(2))
                        losses = parse_number(match.group(3))

                    if wins is None or draws is None or losses is None:
                        continue

                    # V7.2: Try to find goals with flexible patterns
                    # First try combined pattern (scored X ... conceded Y)
                    goals_pattern = rf"{team_pattern}[^.]*?scor(?:ed|ing)\s*(\d+\.?\d*)[^.]*?conced(?:ed|ing)\s*(\d+\.?\d*)"
                    goals_match = re.search(goals_pattern, search_text, re.I)

                    goals_scored = 0.0
                    goals_conceded = 0.0

                    if goals_match:
                        goals_scored = float(goals_match.group(1))
                        goals_conceded = float(goals_match.group(2))
                    else:
                        # V7.2: Fallback - try separate patterns for scored and conceded
                        scored_only = (
                            rf"{team_pattern}[^.]*?scor(?:ed|ing)\s*(\d+\.?\d*)\s*(?:goals?)?"
                        )
                        conceded_only = (
                            rf"{team_pattern}[^.]*?conced(?:ed|ing)\s*(\d+\.?\d*)\s*(?:goals?)?"
                        )

                        scored_match = re.search(scored_only, search_text, re.I)
                        conceded_match = re.search(conceded_only, search_text, re.I)

                        if scored_match:
                            goals_scored = float(scored_match.group(1))
                        if conceded_match:
                            goals_conceded = float(conceded_match.group(1))

                    return {
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "goals_scored": goals_scored,
                        "goals_conceded": goals_conceded,
                    }

        # V2.5: Pattern for incomplete form data (only wins and draws, no losses)
        # Handles: "Team has won 4, drawn 1, and conceded..." (losses not mentioned)
        for search_text in [text_norm, text_original.lower()]:
            # Pattern: "Team (has) won X, (has) drawn Y" without losses
            incomplete_pattern = rf"{team_pattern}\s*(?:has\s+)?won\s*({word_num_pattern})[^.]*?(?:has\s+)?(?:drew|drawn)\s*({word_num_pattern})"
            incomplete_match = re.search(incomplete_pattern, search_text, re.I)

            if incomplete_match:
                wins = parse_number(incomplete_match.group(1))
                draws = parse_number(incomplete_match.group(2))

                if wins is not None and draws is not None:
                    # Calculate losses: 5 matches - wins - draws
                    losses = max(0, 5 - wins - draws)

                    return {
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "goals_scored": 0,
                        "goals_conceded": 0,
                    }

        # V2.2.2: Flexible pattern for combined sentences like:
        # "Galatasaray won two, Fenerbahçe won one, and there were two draws"
        for search_text in [text_norm, text_original.lower()]:
            # Pattern: "Team won X" (extract wins separately)
            won_pattern = rf"{team_pattern}\s+won\s+({word_num_pattern})"
            won_match = re.search(won_pattern, search_text, re.I)

            if won_match:
                wins = parse_number(won_match.group(1))
                if wins is None:
                    continue

                # Look for global draws: "there were X draws" or "X draws"
                draws_patterns = [
                    r"(?:there\s+were|with)\s+({word_num})\s+draws?".replace(
                        "{word_num}", word_num_pattern
                    ),
                    r"({word_num})\s+draws?(?:\s+(?:in|between|total))".replace(
                        "{word_num}", word_num_pattern
                    ),
                ]

                draws = 0
                for dp in draws_patterns:
                    draws_match = re.search(dp, search_text, re.I)
                    if draws_match:
                        draws = parse_number(draws_match.group(1)) or 0
                        break

                # Calculate losses: 5 matches - wins - draws (assuming last 5)
                losses = max(0, 5 - wins - draws)

                return {
                    "wins": wins,
                    "draws": draws,
                    "losses": losses,
                    "goals_scored": 0,
                    "goals_conceded": 0,
                }

        return None


class TavilyVerifier:
    """
    Client for structured Tavily queries to verify match data.

    Builds specialized queries for:
    - Player importance ratings
    - Recent form statistics
    - Head-to-head data
    - Referee statistics
    - Corner averages

    Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 7.2
    """

    def __init__(self, tavily_provider: TavilyProvider | None = None):
        """
        Initialize TavilyVerifier.

        Args:
            tavily_provider: Optional Tavily provider instance (uses singleton if not provided)
        """
        self._provider = tavily_provider
        self._call_count = 0
        self._last_call_time: float | None = None
        self._call_count_lock = threading.Lock()  # Thread safety for counter

    @property
    def provider(self) -> TavilyProvider | None:
        """Get Tavily provider (lazy initialization)."""
        if self._provider is None and TAVILY_AVAILABLE:
            self._provider = get_tavily_provider()
        return self._provider

    def is_available(self) -> bool:
        """Check if Tavily is available for queries."""
        if not TAVILY_AVAILABLE:
            return False
        provider = self.provider
        return provider is not None and provider.is_available()

    def build_verification_query(self, request: VerificationRequest) -> str:
        """
        Build a structured Tavily query for match verification.

        The query is designed to retrieve:
        - Player importance ratings for missing players
        - Last 5 matches form for both teams
        - H2H statistics (goals, cards, corners)
        - Referee cards average
        - Team corner averages

        Args:
            request: VerificationRequest with match data

        Returns:
            Structured query string for Tavily

        Requirements: 1.1, 2.1, 3.1, 4.1, 5.1
        """
        parts = []

        # Match identification
        parts.append(f"{request.home_team} vs {request.away_team}")
        parts.append(f"Date: {request.match_date}")
        parts.append(f"League: {request.league}")

        # Player importance (if missing players)
        all_missing = request.home_missing_players + request.away_missing_players
        if all_missing:
            players_str = ", ".join(all_missing[:10])  # Limit to 10 players
            parts.append(f"Player importance ratings for: {players_str}")

        # Form stats request
        parts.append(f"Last 5 matches goals scored/conceded for {request.home_team}")
        parts.append(f"Last 5 matches goals scored/conceded for {request.away_team}")

        # H2H request
        parts.append("Head to head last 5 matches: goals, cards, corners")

        # Referee request (if known)
        if request.fotmob_referee_name:
            parts.append(f"Referee {request.fotmob_referee_name} cards per game average")
        else:
            parts.append("Match referee cards per game average")

        # Corner stats
        parts.append(f"{request.home_team} corners per game this season")
        parts.append(f"{request.away_team} corners per game this season")

        return " | ".join(parts)

    def query(self, request: VerificationRequest) -> dict[str, Any] | None:
        """
        Execute Tavily query and return raw response.

        Args:
            request: VerificationRequest with match data

        Returns:
            Raw Tavily response dict or None on failure

        Requirements: 7.2
        """
        # V12.0: Check if Tavily enrichment is disabled by startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("tavily_enrichment"):
            logger.debug(
                "⏭️ [VERIFICATION] Tavily query disabled by startup validator (TAVILY_API_KEY not configured)"
            )
            return None

        if not self.is_available():
            logger.warning("⚠️ [VERIFICATION] Tavily not available")
            return None

        query = self.build_verification_query(request)

        logger.info(f"🔍 [VERIFICATION] Tavily query for {request.match_id}")
        start_time = time.time()

        try:
            response = self.provider.search(
                query=query,
                search_depth="advanced",
                max_results=10,
                include_answer=True,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            with self._call_count_lock:
                self._call_count += 1
            self._last_call_time = time.time()

            logger.info(f"🔍 [VERIFICATION] Tavily response in {latency_ms}ms")

            if response is None:
                return None

            # Convert TavilyResponse to dict
            return {
                "query": response.query,
                "answer": response.answer,
                "results": [
                    {
                        "title": r.title,
                        "url": r.url,
                        "content": r.content,
                        "score": r.score,
                    }
                    for r in response.results
                ],
                "response_time": response.response_time,
                "provider": "tavily",
            }

        except Exception as e:
            logger.error(f"❌ [VERIFICATION] Tavily query failed: {e}")
            return None

    def parse_response(
        self, response: dict[str, Any], request: VerificationRequest
    ) -> VerifiedData:
        """
        Parse Tavily response into structured VerifiedData.

        Extracts:
        - Player impact scores from answer/results
        - Form statistics
        - H2H data
        - Referee info
        - Corner averages

        Args:
            response: Raw Tavily response dict
            request: Original verification request

        Returns:
            VerifiedData with parsed statistics

        Requirements: 1.1, 1.4, 2.4, 3.5, 4.4, 5.4
        """
        verified = VerifiedData(source="tavily")

        if not response:
            verified.data_confidence = "Low"
            return verified

        # Get AI answer and search results
        answer = safe_dict_get(response, "answer", default="")
        results = safe_dict_get(response, "results", default=[])

        # Combine all text for parsing
        all_text = answer
        if isinstance(results, list):
            for r in results[:5]:  # Top 5 results
                all_text += " " + safe_dict_get(r, "content", default="")

        # Parse player impacts
        verified.home_player_impacts = self._parse_player_impacts(
            all_text, request.home_missing_players, request.home_team
        )
        verified.away_player_impacts = self._parse_player_impacts(
            all_text, request.away_missing_players, request.away_team
        )

        # Calculate total impacts
        verified.home_total_impact = sum(p.impact_score for p in verified.home_player_impacts)
        verified.away_total_impact = sum(p.impact_score for p in verified.away_player_impacts)

        # Parse form stats
        # V7.1: First try to use FotMob form data if available
        verified.home_form = self._parse_fotmob_form(
            request.home_form_last5
        ) or self._parse_form_stats(all_text, request.home_team)
        verified.away_form = self._parse_fotmob_form(
            request.away_form_last5
        ) or self._parse_form_stats(all_text, request.away_team)
        verified.form_confidence = (
            "High"
            if (request.home_form_last5 or request.away_form_last5)
            else ("Medium" if verified.home_form or verified.away_form else "Low")
        )

        # Parse H2H stats
        verified.h2h = self._parse_h2h_stats(all_text)
        verified.h2h_confidence = "Medium" if verified.h2h and verified.h2h.has_data() else "Low"

        # Parse referee stats with cache integration (V9.0)
        referee_name = request.fotmob_referee_name or "Unknown"

        # Try cache first if available
        if REFEREE_CACHE_AVAILABLE:
            cache = get_referee_cache()
            cached_stats = cache.get(referee_name)
            if cached_stats:
                logger.debug(f"✅ Cache hit for referee: {referee_name}")
                verified.referee = RefereeStats(**cached_stats)
                verified.referee_confidence = "High"  # Cached data is trusted

                # Record cache hit if monitor is available
                if REFEREE_CACHE_MONITOR_AVAILABLE:
                    try:
                        monitor = get_referee_cache_monitor()
                        monitor.record_hit(referee_name)
                        logger.debug(f"📊 Cache hit recorded for referee: {referee_name}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to record cache hit: {e}")

                # Log referee stats used in referee boost logger
                if REFEREE_BOOST_LOGGER_AVAILABLE:
                    try:
                        logger_module = get_referee_boost_logger()
                        logger_module.log_referee_stats_used(
                            referee_name=referee_name,
                            cards_per_game=cached_stats.get("cards_per_game", 0.0),
                            strictness=cached_stats.get("strictness", "unknown"),
                            matches_officiated=cached_stats.get("matches_officiated", 0),
                            source="cache",
                            match_id=request.match_id if request else None,
                            league=request.league if request else None,
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to log referee stats used: {e}")
            else:
                logger.debug(
                    f"❌ Cache miss for referee: {referee_name}, fetching from Tavily/Perplexity"
                )
                verified.referee = self._parse_referee_stats(all_text, referee_name)
                verified.referee_confidence = "Medium" if verified.referee else "Low"

                # Record cache miss if monitor is available
                if REFEREE_CACHE_MONITOR_AVAILABLE:
                    try:
                        monitor = get_referee_cache_monitor()
                        monitor.record_miss(referee_name)
                        logger.debug(f"📊 Cache miss recorded for referee: {referee_name}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to record cache miss: {e}")

                # Log cache miss in referee boost logger
                if REFEREE_BOOST_LOGGER_AVAILABLE:
                    try:
                        logger_module = get_referee_boost_logger()
                        logger_module.log_cache_miss(
                            referee_name=referee_name, reason="not_in_cache"
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to log cache miss: {e}")

                # Cache the fetched stats
                if verified.referee:
                    stats_dict = {
                        "name": verified.referee.name,
                        "cards_per_game": verified.referee.cards_per_game,
                        "strictness": verified.referee.strictness,
                        "matches_officiated": verified.referee.matches_officiated,
                    }
                    cache.set(referee_name, stats_dict)
                    logger.debug(f"💾 Cached referee stats for: {referee_name}")
        else:
            # Fallback to parsing without cache
            verified.referee = self._parse_referee_stats(all_text, referee_name)
            verified.referee_confidence = "Medium" if verified.referee else "Low"

        # Parse corner stats
        verified.home_corner_avg = self._parse_corner_avg(all_text, request.home_team)
        verified.away_corner_avg = self._parse_corner_avg(all_text, request.away_team)
        verified.h2h_corner_avg = verified.h2h.avg_corners if verified.h2h else None
        verified.corner_confidence = (
            "Medium" if verified.home_corner_avg or verified.away_corner_avg else "Low"
        )

        # Calculate overall confidence (unified algorithm across all providers)
        confidence_scores = [
            verified.form_confidence,
            verified.h2h_confidence,
            verified.referee_confidence,
            verified.corner_confidence,
        ]
        high_count = sum(1 for c in confidence_scores if c == "High")
        medium_count = sum(1 for c in confidence_scores if c == "Medium")

        if high_count >= 2:
            verified.data_confidence = "High"
        elif high_count >= 1 or medium_count >= 2:
            verified.data_confidence = "Medium"
        else:
            verified.data_confidence = "Low"

        return verified

    def _parse_player_impacts(
        self, text: str, player_names: list[str], team_name: str
    ) -> list[PlayerImpact]:
        """
        Parse player impact scores from text.

        Uses heuristics to estimate player importance:
        - Keywords like "key", "star", "captain", "top scorer" = high impact
        - Keywords like "backup", "reserve", "youth" = low impact
        - Default to 5 (neutral) if no info found

        Args:
            text: Combined text from Tavily response
            player_names: List of player names to look for
            team_name: Team name for context

        Returns:
            List of PlayerImpact objects

        Requirements: 1.4
        """
        impacts = []
        text_lower = text.lower()

        # High impact keywords
        high_keywords = [
            "key player",
            "star",
            "captain",
            "top scorer",
            "leading scorer",
            "best player",
            "crucial",
            "essential",
            "irreplaceable",
            "main",
            "first choice",
            "starter",
            "regular",
            "important",
        ]

        # Low impact keywords
        low_keywords = [
            "backup",
            "reserve",
            "youth",
            "academy",
            "substitute",
            "bench",
            "rotation",
            "squad player",
            "fringe",
            "third choice",
        ]

        for name in player_names:
            name_lower = name.lower()

            # Check if player is mentioned
            if name_lower not in text_lower:
                # Default impact for unknown players
                impacts.append(
                    PlayerImpact(
                        name=name,
                        impact_score=5,  # Neutral default per Requirement 1.4
                        role="unknown",
                    )
                )
                continue

            # Find context around player name
            idx = text_lower.find(name_lower)
            context_start = max(0, idx - 100)
            context_end = min(len(text_lower), idx + len(name_lower) + 100)
            context = text_lower[context_start:context_end]

            # Score based on keywords
            score = 5  # Default neutral
            role = "unknown"

            # Check high impact keywords
            for kw in high_keywords:
                if kw in context:
                    score = max(score, 8)
                    role = "starter"
                    break

            # Check low impact keywords (only if not already high)
            if score < 7:
                for kw in low_keywords:
                    if kw in context:
                        score = min(score, 3)
                        role = "backup"
                        break

            # Check for specific role indicators
            if "goalkeeper" in context or "keeper" in context:
                score = max(score, 7)  # Goalkeepers are usually important
                role = "starter"
            elif "captain" in context:
                score = 9
                role = "starter"
            elif "top scorer" in context or "leading scorer" in context:
                score = 9
                role = "starter"

            impacts.append(PlayerImpact(name=name, impact_score=score, role=role))

        return impacts

    def _parse_form_stats(self, text: str, team_name: str) -> FormStats | None:
        """
        Parse form statistics from text.

        V7.1: Enhanced with more flexible patterns.

        Looks for patterns like:
        - "last 5 matches: W-W-D-L-L"
        - "scored 8 goals in last 5"
        - "conceded 6 goals in last 5"
        - "won 3, drew 1, lost 1"
        - "3 wins, 2 draws, 0 losses"

        Args:
            text: Combined text from Tavily response
            team_name: Team name to look for

        Returns:
            FormStats or None if not found
        """
        import re

        text_lower = text.lower()
        team_lower = team_name.lower()

        # Find team context - try multiple variations
        team_idx = text_lower.find(team_lower)
        if team_idx == -1:
            # Try first word of team name
            first_word = team_lower.split()[0]
            if len(first_word) > 3:
                team_idx = text_lower.find(first_word)

        if team_idx == -1:
            return None

        # Look for form in context around team name
        context_start = max(0, team_idx - 200)
        context_end = min(len(text), team_idx + 600)
        context = text[context_start:context_end]
        context_lower = context.lower()

        # Try to extract goals scored/conceded
        goals_scored = 0
        goals_conceded = 0
        wins = 0
        draws = 0
        losses = 0

        # Pattern: "scored X goals in last 5"
        scored_match = re.search(r"scored\s+(\d+)\s+goals?\s+(?:in\s+)?last\s*5", context, re.I)
        if scored_match:
            goals_scored = int(scored_match.group(1))

        # Pattern: "conceded X goals in last 5"
        conceded_match = re.search(r"conceded\s+(\d+)\s+goals?\s+(?:in\s+)?last\s*5", context, re.I)
        if conceded_match:
            goals_conceded = int(conceded_match.group(1))

        # Pattern 1: form string like "WWDLL" or "W-W-D-L-L"
        form_match = re.search(r"([WDL][-\s]*){5}", context, re.I)
        if form_match:
            form_str = form_match.group(0).upper().replace("-", "").replace(" ", "")
            wins = form_str.count("W")
            draws = form_str.count("D")
            losses = form_str.count("L")

        # Pattern 2: "won X, drew Y, lost Z" or "won X drew Y lost Z"
        if wins == 0 and draws == 0 and losses == 0:
            wdl_match = re.search(
                r"won\s+(\d+)[,\s]+(?:and\s+)?drew\s+(\d+)[,\s]+(?:and\s+)?lost\s+(\d+)",
                context_lower,
            )
            if wdl_match:
                wins = int(wdl_match.group(1))
                draws = int(wdl_match.group(2))
                losses = int(wdl_match.group(3))

        # Pattern 3: "X wins, Y draws, Z losses" or "X wins Y draws Z losses"
        if wins == 0 and draws == 0 and losses == 0:
            wdl_match = re.search(
                r"(\d+)\s*wins?[,\s]+(\d+)\s*draws?[,\s]+(\d+)\s*loss", context_lower
            )
            if wdl_match:
                wins = int(wdl_match.group(1))
                draws = int(wdl_match.group(2))
                losses = int(wdl_match.group(3))

        # Pattern 4: "W3 D1 L1" or "W:3 D:1 L:1"
        if wins == 0 and draws == 0 and losses == 0:
            w_match = re.search(r"\bW[:\s]*(\d+)", context, re.I)
            d_match = re.search(r"\bD[:\s]*(\d+)", context, re.I)
            l_match = re.search(r"\bL[:\s]*(\d+)", context, re.I)
            if w_match and d_match and l_match:
                wins = int(w_match.group(1))
                draws = int(d_match.group(1))
                losses = int(l_match.group(1))

        # Pattern 5: "in the last 5 matches, X won Y" (flexible)
        if wins == 0 and draws == 0 and losses == 0:
            last5_match = re.search(
                r"last\s*(?:5|five)\s*(?:matches?|games?)[^.]*?won\s+(\d+)", context_lower
            )
            if last5_match:
                wins = int(last5_match.group(1))
                # Look for draws and losses nearby
                draws_match = re.search(r"drew\s+(\d+)", context_lower)
                losses_match = re.search(r"lost\s+(\d+)", context_lower)
                if draws_match:
                    draws = int(draws_match.group(1))
                if losses_match:
                    losses = int(losses_match.group(1))
                # If we only have wins, estimate the rest
                if draws == 0 and losses == 0:
                    losses = max(0, 5 - wins)

        # Pattern 6: Tabular format "| 68% (23) | Wons |" - extract from percentage
        if wins == 0 and draws == 0 and losses == 0:
            # Look for wins percentage with count
            wins_pct_match = re.search(r"(\d+)%\s*\((\d+)\)\s*\|\s*won", context_lower)
            if wins_pct_match:
                wins = int(wins_pct_match.group(2))
            draws_pct_match = re.search(r"(\d+)%\s*\((\d+)\)\s*\|\s*draw", context_lower)
            if draws_pct_match:
                draws = int(draws_pct_match.group(2))
            losses_pct_match = re.search(
                r"(\d+)%\s*\((\d+)\)\s*\|\s*(?:defeat|loss)", context_lower
            )
            if losses_pct_match:
                losses = int(losses_pct_match.group(2))

        # Only return if we found some data
        if goals_scored > 0 or goals_conceded > 0 or wins + draws + losses > 0:
            return FormStats(
                goals_scored=goals_scored,
                goals_conceded=goals_conceded,
                wins=wins,
                draws=draws,
                losses=losses,
            )

        return None

    def _parse_fotmob_form(self, form_string: str | None) -> FormStats | None:
        """
        V7.1: Parse form from FotMob format (e.g., "WWDLL" or "W-W-D-L-L").

        FotMob provides form as a string of W/D/L characters.
        This is more reliable than parsing from Tavily text.

        Args:
            form_string: Form string from FotMob (e.g., "WWDLL")

        Returns:
            FormStats or None if form_string is empty/invalid
        """
        if not form_string or not form_string.strip():
            return None

        # Normalize: remove dashes, spaces, convert to uppercase
        form_clean = form_string.upper().replace("-", "").replace(" ", "")

        # Count W/D/L
        wins = form_clean.count("W")
        draws = form_clean.count("D")
        losses = form_clean.count("L")

        # Validate we have at least some results
        if wins + draws + losses == 0:
            return None

        return FormStats(
            goals_scored=0,  # FotMob form string doesn't include goals
            goals_conceded=0,
            wins=wins,
            draws=draws,
            losses=losses,
        )

    def _parse_h2h_stats(self, text: str) -> H2HStats | None:
        """
        Parse head-to-head statistics from text.

        V15.0 Enhanced:
        - Added parsing for home_wins, away_wins, draws
        - Improved regex to handle comma-separated numbers
        - Added validation using _validate_values()

        Looks for patterns like:
        - "last 5 meetings: 3.2 goals per game"
        - "H2H: 4.5 cards average"
        - "10.2 corners per match in H2H"
        - "Home team won 3, away team won 1, 1 draw"
        - "3-1-1" (home wins, away wins, draws)

        Args:
            text: Combined text from Tavily response

        Returns:
            H2HStats or None if not found
        """
        import re

        text_lower = text.lower()

        # Look for H2H section
        h2h_keywords = ["head to head", "h2h", "previous meetings", "last meetings"]
        h2h_context = ""

        for kw in h2h_keywords:
            idx = text_lower.find(kw)
            if idx != -1:
                h2h_context = text[max(0, idx - 50) : min(len(text), idx + 500)]
                break

        if not h2h_context:
            return None

        h2h = H2HStats()

        # Helper function to parse numbers with optional commas
        def parse_number(num_str: str) -> int | float | None:
            """Parse a number string, handling commas."""
            if not num_str:
                return None
            # Remove commas from the number string
            cleaned = num_str.replace(",", "")
            try:
                # Try to parse as float first (for decimals)
                if "." in cleaned:
                    return float(cleaned)
                else:
                    return int(cleaned)
            except (ValueError, TypeError):
                return None

        # Parse number of matches (with comma support)
        matches_match = re.search(r"(\d+,?\d*)\s*(?:matches?|meetings?|games?)", h2h_context, re.I)
        if matches_match:
            parsed = parse_number(matches_match.group(1))
            if parsed is not None:
                h2h.matches_analyzed = int(parsed)

        # Parse average goals (with comma support)
        goals_match = re.search(
            r"(\d+,?\d*\.?\d*)\s*goals?\s*(?:per|average|avg)", h2h_context, re.I
        )
        if goals_match:
            parsed = parse_number(goals_match.group(1))
            if parsed is not None:
                h2h.avg_goals = float(parsed)

        # Parse average cards (with comma support)
        cards_match = re.search(
            r"(\d+,?\d*\.?\d*)\s*cards?\s*(?:per|average|avg)", h2h_context, re.I
        )
        if cards_match:
            parsed = parse_number(cards_match.group(1))
            if parsed is not None:
                h2h.avg_cards = float(parsed)

        # Parse average corners (with comma support)
        corners_match = re.search(
            r"(\d+,?\d*\.?\d*)\s*corners?\s*(?:per|average|avg)", h2h_context, re.I
        )
        if corners_match:
            parsed = parse_number(corners_match.group(1))
            if parsed is not None:
                h2h.avg_corners = float(parsed)

        # V15.0: Parse home_wins, away_wins, draws
        # Pattern 1: "Home team won 3, away team won 1, 1 draw"
        # Pattern 2: "Team A: 3 wins, Team B: 1 win, 1 draw"
        # Pattern 3: "3-1-1" format (home wins, away wins, draws)
        # Pattern 4: "won 3, lost 1, drew 1"

        # Try pattern 1: "won X, won Y, Z draw(s)"
        wdl_pattern = re.search(
            r"(?:won|wins?)\s+(\d+).*?(?:won|wins?)\s+(\d+).*?(?:drew?|draws?)\s+(\d+)",
            h2h_context,
            re.I,
        )
        if wdl_pattern:
            h2h.home_wins = int(wdl_pattern.group(1))
            h2h.away_wins = int(wdl_pattern.group(2))
            h2h.draws = int(wdl_pattern.group(3))

        # Try pattern 2: "X-Y-Z" format (home wins, away wins, draws)
        # This is a common shorthand format
        if h2h.home_wins == 0 and h2h.away_wins == 0 and h2h.draws == 0:
            xyz_pattern = re.search(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", h2h_context)
            if xyz_pattern:
                h2h.home_wins = int(xyz_pattern.group(1))
                h2h.away_wins = int(xyz_pattern.group(2))
                h2h.draws = int(xyz_pattern.group(3))

        # Try pattern 3: "Team A: X wins, Team B: Y wins, Z draws"
        if h2h.home_wins == 0 and h2h.away_wins == 0 and h2h.draws == 0:
            team_wins_pattern = re.search(
                r"(\w+):\s*(\d+)\s*wins?.*?(\w+):\s*(\d+)\s*wins?.*?(\d+)\s*draws?",
                h2h_context,
                re.I,
            )
            if team_wins_pattern:
                # Determine which team is home/away based on context
                # For simplicity, we'll assign first to home, second to away
                h2h.home_wins = int(team_wins_pattern.group(2))
                h2h.away_wins = int(team_wins_pattern.group(4))
                h2h.draws = int(team_wins_pattern.group(5))

        # Try pattern 4: "won X, lost Y, drew Z" (combined format)
        if h2h.home_wins == 0 and h2h.away_wins == 0 and h2h.draws == 0:
            combined_pattern = re.search(
                r"won\s+(\d+).*?lost\s+(\d+).*?drew?\s+(\d+)", h2h_context, re.I
            )
            if combined_pattern:
                # This pattern is ambiguous - we'll assign to home_wins, away_wins, draws
                # In practice, this might need context to determine which team
                h2h.home_wins = int(combined_pattern.group(1))
                h2h.away_wins = int(combined_pattern.group(2))
                h2h.draws = int(combined_pattern.group(3))

        # V15.0: Validate parsed values before returning
        if not h2h._validate_values():
            logger.warning("⚠️ H2HStats: Parsed values failed validation")
            return None

        return h2h if h2h.has_data() else None

    def _parse_referee_stats(self, text: str, referee_name: str | None) -> RefereeStats | None:
        """
        Parse referee statistics from text.

        V7.1: Enhanced to find referee even without known name.

        Looks for patterns like:
        - "Referee X: 4.5 cards per game"
        - "averages 5.2 yellow cards"
        - "Referee: John Smith averages 4.2 cards"

        Args:
            text: Combined text from Tavily response
            referee_name: Known referee name (optional)

        Returns:
            RefereeStats or None if not found
        """
        import re

        text_lower = text.lower()

        # CASE 1: We have a known referee name - search for it
        if referee_name and referee_name.strip():
            ref_lower = referee_name.strip().lower()

            # Find referee context
            ref_idx = text_lower.find(ref_lower)
            if ref_idx == -1:
                # Try partial match
                ref_parts = ref_lower.split()
                for part in ref_parts:
                    if len(part) > 3:
                        ref_idx = text_lower.find(part)
                        if ref_idx != -1:
                            break

            if ref_idx != -1:
                # Get context around referee name
                context_start = max(0, ref_idx - 100)
                context_end = min(len(text), ref_idx + 300)
                context = text[context_start:context_end]

                # Parse cards per game
                cards_match = re.search(
                    r"(\d+\.?\d*)\s*(?:cards?|yellow|bookings?)\s*(?:per|average|avg)",
                    context,
                    re.I,
                )
                if cards_match:
                    cards_per_game = float(cards_match.group(1))
                    return RefereeStats(name=referee_name, cards_per_game=cards_per_game)

        # CASE 2: V7.1 - No known referee name, search for generic referee patterns
        # All patterns work on lowercase text (text_lower)
        referee_patterns = [
            # "The referee averages 4.2 yellow cards" or "referee averages 4.2 cards"
            r"(?:the\s+)?referee\s+averages?\s+(\d+\.?\d*)\s*(?:yellow\s*)?cards?",
            # "referee: 4.5 cards per game" or "referee 4.5 cards per game"
            r"referee[:\s]+[^.]{0,30}?(\d+\.?\d*)\s*(?:cards?|yellow|bookings?)\s*(?:per|/)\s*(?:game|match)",
            # "Match official: 4.5 cards per game average"
            r"(?:match\s+)?official[:\s]+[^.]*?(\d+\.?\d*)\s*cards?\s*(?:per|average|avg)",
            # "X.X cards per game (referee)" or "X.X yellow cards per match"
            r"(\d+\.?\d*)\s*(?:yellow\s*)?cards?\s*per\s*(?:game|match)",
            # "averages X.X bookings per match" in referee context
            r"referee[^.]{0,50}averages?\s+(\d+\.?\d*)\s*(?:bookings?|cards?)",
            # "cards per game: 4.5" or "yellow cards: 4.2"
            r"(?:yellow\s*)?cards?\s*(?:per\s*(?:game|match)|average)[:\s]+(\d+\.?\d*)",
            # "4.5 cards/game" format
            r"(\d+\.?\d*)\s*cards?/(?:game|match)",
            # "booking average: 4.5" or "booking rate: 4.2"
            r"booking[s]?\s*(?:average|rate)[:\s]+(\d+\.?\d*)",
        ]

        for pattern in referee_patterns:
            match = re.search(pattern, text_lower, re.I)
            if match:
                try:
                    cards_per_game = float(match.group(1))
                    # Sanity check: cards per game should be between 0.5 and 10
                    if 0.5 <= cards_per_game <= 10:
                        return RefereeStats(name="Unknown", cards_per_game=cards_per_game)
                except (ValueError, TypeError):
                    continue

        return None

    def _parse_corner_avg(self, text: str, team_name: str) -> float | None:
        """
        Parse corner average for a team from text.

        Looks for patterns like:
        - "Team X: 5.5 corners per game"
        - "averages 6.2 corners"

        Args:
            text: Combined text from Tavily response
            team_name: Team name to look for

        Returns:
            Corner average or None if not found
        """
        import re

        text_lower = text.lower()
        team_lower = team_name.lower()

        # Find team context
        team_idx = text_lower.find(team_lower)
        if team_idx == -1:
            return None

        # Get context around team name
        context_start = max(0, team_idx - 50)
        context_end = min(len(text), team_idx + 200)
        context = text[context_start:context_end]

        # Parse corners per game
        corners_match = re.search(r"(\d+\.?\d*)\s*corners?\s*(?:per|average|avg)", context, re.I)
        if corners_match:
            return float(corners_match.group(1))

        return None

    def get_call_count(self) -> int:
        """Get number of API calls made."""
        return self._call_count

    # ============================================
    # OPTIMIZED QUERY METHODS (V2.0)
    # ============================================

    def query_optimized(self, request: VerificationRequest) -> dict[str, Any] | None:
        """
        Execute optimized multi-query verification.

        Uses 4 targeted site-specific queries for 100% data completeness:
        1. FootyStats: team stats + H2H
        2. Transfermarkt: player values
        3. Referee stats
        4. Form last 5

        Args:
            request: VerificationRequest with match data

        Returns:
            Dict with combined answers and metadata, or None on failure

        Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 7.2
        """
        if not self.is_available():
            logger.warning("⚠️ [VERIFICATION] Tavily not available")
            return None

        # Build optimized queries
        all_missing = request.home_missing_players + request.away_missing_players

        query_builder = OptimizedQueryBuilder(
            home_team=request.home_team,
            away_team=request.away_team,
            players=all_missing,
            referee_name=request.fotmob_referee_name,
            league=self._extract_league_name(request.league),
        )

        logger.info(f"🔍 [VERIFICATION] Starting optimized queries for {request.match_id}")
        start_time = time.time()

        all_answers = []
        all_results = []
        query_times = {}

        # Execute all queries
        for label, query in query_builder.get_all_queries():
            try:
                query_start = time.time()
                response = self.provider.search(
                    query=query,
                    search_depth="advanced",
                    max_results=8,
                    include_answer=True,
                )
                query_time = time.time() - query_start
                query_times[label] = query_time
                self._call_count += 1

                if response and response.answer:
                    all_answers.append(response.answer)
                    logger.debug(
                        f"🔍 [VERIFICATION] {label}: {len(response.answer)} chars in {query_time:.2f}s"
                    )

                if response and response.results:
                    all_results.extend(
                        [
                            {
                                "title": r.title,
                                "url": r.url,
                                "content": r.content,
                                "score": r.score,
                                "query_type": label,
                            }
                            for r in response.results[:3]  # Top 3 per query
                        ]
                    )

            except Exception as e:
                logger.warning(f"⚠️ [VERIFICATION] Query {label} failed: {e}")
                continue

        total_time = time.time() - start_time
        self._last_call_time = time.time()

        if not all_answers:
            logger.error("❌ [VERIFICATION] All optimized queries failed")
            return None

        logger.info(
            f"🔍 [VERIFICATION] Optimized queries completed in {total_time:.2f}s ({len(all_answers)} answers)"
        )

        return {
            "query": "optimized_multi_query",
            "answer": " ".join(all_answers),
            "results": all_results,
            "response_time": total_time,
            "query_times": query_times,
            "provider": "tavily_v2",
            "queries_executed": len(all_answers),
        }

    def parse_optimized_response(
        self, response: dict[str, Any], request: VerificationRequest
    ) -> VerifiedData:
        """
        Parse optimized query response into VerifiedData.

        Uses OptimizedResponseParser for 100% data extraction.

        Args:
            response: Response from query_optimized()
            request: Original verification request

        Returns:
            VerifiedData with all extracted data

        Requirements: 1.4, 2.4, 3.5, 4.4, 5.4
        """
        if not response:
            return VerifiedData(source="tavily_v2", data_confidence="Low")

        combined_text = safe_dict_get(response, "answer", default="")

        if not combined_text:
            return VerifiedData(source="tavily_v2", data_confidence="Low")

        # Use optimized parser
        all_missing = request.home_missing_players + request.away_missing_players

        parser = OptimizedResponseParser(
            home_team=request.home_team,
            away_team=request.away_team,
            referee_name=request.fotmob_referee_name,
            players=all_missing,
            home_team_injury_impact=request.home_team_injury_impact,
            away_team_injury_impact=request.away_team_injury_impact,
        )

        return parser.parse_to_verified_data(combined_text, request)

    def _extract_league_name(self, league_key: str) -> str:
        """
        Extract readable league name from key.

        Args:
            league_key: League key like "soccer_italy_serie_a"

        Returns:
            Readable name like "Serie A"
        """
        league_map = {
            "soccer_italy_serie_a": "Serie A",
            "soccer_england_premier_league": "Premier League",
            "soccer_spain_la_liga": "La Liga",
            "soccer_germany_bundesliga": "Bundesliga",
            "soccer_france_ligue_one": "Ligue 1",
            "soccer_turkey_super_league": "Super Lig",
            "soccer_greece_super_league": "Super League Greece",
            "soccer_argentina_primera_division": "Primera División",
            "soccer_mexico_liga_mx": "Liga MX",
            "soccer_scotland_premiership": "Scottish Premiership",
            "soccer_australia_a_league": "A-League",
            "soccer_poland_ekstraklasa": "Ekstraklasa",
            "soccer_japan_j_league": "J-League",
            "soccer_brazil_serie_b": "Serie B Brazil",
        }
        return league_map.get(
            league_key, league_key.replace("soccer_", "").replace("_", " ").title()
        )

    # ============================================
    # V2.4: MULTI-SITE FALLBACK QUERY
    # ============================================

    def query_with_fallback(self, request: VerificationRequest) -> dict[str, Any] | None:
        """
        Execute optimized queries with intelligent multi-site fallback.

        V2.4 Strategy:
        1. Execute primary queries on best sites
        2. Parse response and identify missing data
        3. If data incomplete (< 75% extraction), execute fallback queries
        4. Combine all results for maximum data coverage

        This approach is more intelligent than OR queries because:
        - Doesn't confuse Tavily with complex OR syntax
        - Only executes fallback queries when needed
        - Combines data from multiple authoritative sources

        Args:
            request: VerificationRequest with match data

        Returns:
            Dict with combined answers and metadata, or None on failure
        """
        if not self.is_available():
            logger.warning("⚠️ [VERIFICATION] Tavily not available")
            return None

        # Step 1: Execute primary queries
        logger.info(f"🔍 [VERIFICATION V2.4] Starting multi-site fallback for {request.match_id}")
        start_time = time.time()

        primary_response = self.query_optimized(request)

        if not primary_response:
            logger.warning(
                "⚠️ [VERIFICATION V2.4] Primary queries failed, trying Perplexity directly..."
            )

            # V2.6: Try Perplexity as last resort when Tavily completely fails
            # Create empty verified data to trigger Perplexity fallback
            empty_verified = VerifiedData(source="tavily_failed", data_confidence="Low")
            perplexity_data = self._execute_perplexity_fallback(request, empty_verified)

            if perplexity_data:
                total_time = time.time() - start_time
            logger.info("✅ [V2.6] Perplexity rescued data after Tavily failure")
            return {
                "query": "perplexity_rescue_v2.6",
                "answer": f"Perplexity corner data: home={safe_dict_get(perplexity_data, 'home_corners_avg', default='Unknown')}, away={safe_dict_get(perplexity_data, 'away_corners_avg', default='Unknown')}",
                "results": [],
                "response_time": total_time,
                "provider": "perplexity_v2.6_rescue",
                "queries_executed": 1,
                "primary_extraction_rate": 0,
                "fallback_executed": False,
                "perplexity_corners": perplexity_data,
                "perplexity_fallback_executed": True,
            }

            logger.error("❌ [VERIFICATION V2.4] Primary queries failed and Perplexity unavailable")
            return None

        # Step 2: Parse and check completeness
        verified = self.parse_optimized_response(primary_response, request)
        missing_data = self._identify_missing_data(verified)

        # Calculate extraction rate
        total_checks = 8  # player_home, player_away, form_home, form_away, h2h, referee, corner_home, corner_away
        passed_checks = total_checks - len(missing_data)
        extraction_rate = (passed_checks / total_checks) * 100

        logger.info(
            f"🔍 [VERIFICATION V2.4] Primary extraction: {extraction_rate:.0f}% ({passed_checks}/{total_checks})"
        )

        # Step 3: If extraction rate <= 75%, execute fallback queries
        if extraction_rate <= 75 and missing_data:
            logger.info(f"🔄 [VERIFICATION V2.4] Executing fallback for: {missing_data}")

            fallback_response = self._execute_fallback_queries(request, missing_data)

            if fallback_response:
                # Combine primary and fallback answers
                combined_answer = (
                    safe_dict_get(primary_response, "answer", default="")
                    + " "
                    + safe_dict_get(fallback_response, "answer", default="")
                )
                combined_results = safe_dict_get(
                    primary_response, "results", default=[]
                ) + safe_dict_get(fallback_response, "results", default=[])

                # V2.6: Check if corners still missing after Tavily fallback
                # V7.1: Also check if form is missing
                # Re-parse combined response to check extraction
                temp_response = {
                    "answer": combined_answer,
                    "results": combined_results,
                }
                verified_after_fallback = self.parse_optimized_response(temp_response, request)
                corners_still_missing = (
                    verified_after_fallback.home_corner_avg is None
                    and verified_after_fallback.away_corner_avg is None
                )
                form_still_missing = (
                    verified_after_fallback.home_form is None
                    and verified_after_fallback.away_form is None
                )

                perplexity_data = None
                # V7.1: Call Perplexity if corners OR form are missing
                if (corners_still_missing and "corners" in missing_data) or (
                    form_still_missing and "form" in missing_data
                ):
                    missing_types = []
                    if corners_still_missing:
                        missing_types.append("corners")
                    if form_still_missing:
                        missing_types.append("form")
                    logger.info(
                        f"🔮 [V2.6] {', '.join(missing_types)} still missing after Tavily fallback, trying Perplexity..."
                    )
                    perplexity_data = self._execute_perplexity_fallback(
                        request, verified_after_fallback
                    )

                total_time = time.time() - start_time

                result = {
                    "query": "multi_site_fallback_v2.4",
                    "answer": combined_answer,
                    "results": combined_results,
                    "response_time": total_time,
                    "query_times": {
                        **safe_dict_get(primary_response, "query_times", default={}),
                        **safe_dict_get(fallback_response, "query_times", default={}),
                    },
                    "provider": "tavily_v2.4_fallback",
                    "queries_executed": safe_dict_get(
                        primary_response, "queries_executed", default=0
                    )
                    + safe_dict_get(fallback_response, "queries_executed", default=0),
                    "primary_extraction_rate": extraction_rate,
                    "fallback_executed": True,
                    "missing_data_types": missing_data,
                }

                # V2.6: Add Perplexity corner data if found
                if perplexity_data:
                    result["perplexity_corners"] = perplexity_data
                    result["perplexity_fallback_executed"] = True
                    logger.info("✅ [V2.6] Perplexity corner data added to response")
                else:
                    result["perplexity_fallback_executed"] = False

                return result

        # V2.6: Even if Tavily extraction >= 75%, check if corners specifically are missing
        # V7.1: Also check if form is missing
        # This handles cases where form/h2h are good but corners are missing (or vice versa)
        corners_missing = verified.home_corner_avg is None and verified.away_corner_avg is None
        form_missing = verified.home_form is None and verified.away_form is None
        perplexity_data = None

        if corners_missing or form_missing:
            missing_types = []
            if corners_missing:
                missing_types.append("corners")
            if form_missing:
                missing_types.append("form")
            logger.info(
                f"🔮 [V2.6] {', '.join(missing_types)} missing (extraction >= 75%), trying Perplexity..."
            )
            perplexity_data = self._execute_perplexity_fallback(request, verified)

        # No Tavily fallback needed (or already handled above)
        total_time = time.time() - start_time
        primary_response["response_time"] = total_time
        primary_response["primary_extraction_rate"] = extraction_rate
        primary_response["fallback_executed"] = False

        # V2.6: Add Perplexity corner data if found
        if perplexity_data:
            primary_response["perplexity_corners"] = perplexity_data
            primary_response["perplexity_fallback_executed"] = True
            logger.info("✅ [V2.6] Perplexity corner data added to response")
        else:
            primary_response["perplexity_fallback_executed"] = False

        return primary_response

    def _identify_missing_data(self, verified: VerifiedData) -> list[str]:
        """
        Identify which data types are missing from verified data.

        Args:
            verified: VerifiedData from primary queries

        Returns:
            List of missing data type labels
        """
        missing = []

        # Check corners (most commonly missing)
        if verified.home_corner_avg is None and verified.away_corner_avg is None:
            missing.append("corners")

        # Check form stats
        if verified.home_form is None and verified.away_form is None:
            missing.append("form")

        # Check H2H
        if verified.h2h is None or not verified.h2h.has_data():
            missing.append("h2h")

        # Check team stats (goals, cards)
        # If we have corners but no other team stats, we might need more
        if verified.corner_confidence == "Low":
            missing.append("team_stats")

        return missing

    def _execute_fallback_queries(
        self, request: VerificationRequest, missing_data: list[str]
    ) -> dict[str, Any] | None:
        """
        Execute fallback queries for missing data types.

        Args:
            request: Original verification request
            missing_data: List of missing data types

        Returns:
            Dict with fallback query results, or None on failure
        """
        all_missing = request.home_missing_players + request.away_missing_players

        query_builder = OptimizedQueryBuilder(
            home_team=request.home_team,
            away_team=request.away_team,
            players=all_missing,
            referee_name=request.fotmob_referee_name,
            league=self._extract_league_name(request.league),
        )

        fallback_queries = query_builder.get_fallback_queries(missing_data)

        if not fallback_queries:
            return None

        all_answers = []
        all_results = []
        query_times = {}

        for label, query in fallback_queries:
            try:
                query_start = time.time()
                response = self.provider.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5,
                    include_answer=True,
                )
                query_time = time.time() - query_start
                query_times[label] = query_time
                self._call_count += 1

                if response and response.answer:
                    all_answers.append(response.answer)
                    logger.debug(
                        f"🔄 [FALLBACK] {label}: {len(response.answer)} chars in {query_time:.2f}s"
                    )

                if response and response.results:
                    all_results.extend(
                        [
                            {
                                "title": r.title,
                                "url": r.url,
                                "content": r.content,
                                "score": r.score,
                                "query_type": label,
                            }
                            for r in response.results[:3]
                        ]
                    )

            except Exception as e:
                logger.warning(f"⚠️ [FALLBACK] Query {label} failed: {e}")
                continue

        if not all_answers:
            return None

        return {
            "answer": " ".join(all_answers),
            "results": all_results,
            "query_times": query_times,
            "queries_executed": len(all_answers),
        }

    # ============================================
    # V2.6: PERPLEXITY FALLBACK FOR CORNERS
    # ============================================

    def _execute_perplexity_fallback(
        self, request: VerificationRequest, verified: "VerifiedData"
    ) -> dict[str, Any] | None:
        """
        V2.6: Execute Perplexity fallback for missing corner/form data.

        V7.1: Extended to also return form data when available.

        Called when Tavily (primary + secondary sites) cannot find corner stats.
        Perplexity searches freely without site restrictions for better coverage.

        Args:
            request: Original verification request
            verified: VerifiedData from Tavily (may have missing corners/form)

        Returns:
            Dict with corner/form data from Perplexity, or None on failure
        """
        # V12.0: Check if Perplexity fallback is disabled by startup validator
        if _STARTUP_VALIDATOR_AVAILABLE and is_feature_disabled("perplexity_fallback"):
            logger.debug(
                "⏭️ [V2.6] Perplexity fallback disabled by startup validator (PERPLEXITY_API_KEY not configured)"
            )
            return None

        # Check if Perplexity is available
        if not PERPLEXITY_AVAILABLE:
            logger.debug("⚠️ [V2.6] Perplexity not available for corner fallback")
            return None

        try:
            perplexity = get_perplexity_provider()
            if not perplexity or not perplexity.is_available():
                logger.debug("⚠️ [V2.6] Perplexity provider not initialized")
                return None
        except Exception as e:
            logger.warning(f"⚠️ [V2.6] Failed to get Perplexity provider: {e}")
            return None

        # Extract league name for context
        league_name = self._extract_league_name(request.league) if request.league else "Unknown"

        logger.info(
            f"🔮 [V2.6] Executing Perplexity fallback for corners: {request.home_team} vs {request.away_team}"
        )

        try:
            start_time = time.time()

            # Call Perplexity get_betting_stats (searches freely, no site restrictions)
            betting_stats = perplexity.get_betting_stats(
                home_team=request.home_team,
                away_team=request.away_team,
                match_date=request.match_date or "upcoming",
                league=league_name,
            )

            elapsed = time.time() - start_time

            if not betting_stats:
                logger.warning(f"⚠️ [V2.6] Perplexity returned no betting stats ({elapsed:.2f}s)")
                return None

            # Extract corner data
            home_corners = safe_dict_get(betting_stats, "home_corners_avg", default=None)
            away_corners = safe_dict_get(betting_stats, "away_corners_avg", default=None)
            corners_signal = safe_dict_get(betting_stats, "corners_signal", default="Unknown")
            data_confidence = safe_dict_get(betting_stats, "data_confidence", default="Low")

            # Extract cards data
            home_cards = safe_dict_get(betting_stats, "home_cards_avg", default=None)
            away_cards = safe_dict_get(betting_stats, "away_cards_avg", default=None)
            cards_signal = safe_dict_get(betting_stats, "cards_signal", default=CardsSignal.UNKNOWN)

            # V7.1: Extract form data
            home_form_wins = safe_dict_get(betting_stats, "home_form_wins", default=None)
            home_form_draws = safe_dict_get(betting_stats, "home_form_draws", default=None)
            home_form_losses = safe_dict_get(betting_stats, "home_form_losses", default=None)
            away_form_wins = safe_dict_get(betting_stats, "away_form_wins", default=None)
            away_form_draws = safe_dict_get(betting_stats, "away_form_draws", default=None)
            away_form_losses = safe_dict_get(betting_stats, "away_form_losses", default=None)

            # V7.1: Extract referee data
            referee_name = safe_dict_get(betting_stats, "referee_name", default=None)
            referee_cards_avg = safe_dict_get(betting_stats, "referee_cards_avg", default=None)

            # V7.2: Extract match context data
            match_intensity = safe_dict_get(betting_stats, "match_intensity", default="Unknown")
            referee_strictness = safe_dict_get(
                betting_stats, "referee_strictness", default="Unknown"
            )
            is_derby = safe_dict_get(betting_stats, "is_derby", default=False)

            logger.debug(
                f"🎯 [V7.2] Match context: intensity={match_intensity}, "
                f"referee_strictness={referee_strictness}, is_derby={is_derby}"
            )

            # Validate we got actual corner data
            if home_corners is None and away_corners is None:
                logger.warning(f"⚠️ [V2.6] Perplexity found no corner averages ({elapsed:.2f}s)")
                # Still return form data if available
                if home_form_wins is not None or away_form_wins is not None:
                    logger.info("✅ [V7.1] Perplexity found form data (no corners)")
                else:
                    return None
            else:
                logger.info(
                    f"✅ [V2.6] Perplexity corners: home={home_corners}, away={away_corners}, "
                    f"signal={corners_signal}, cards={cards_signal.value if isinstance(cards_signal, Enum) else cards_signal}, confidence={data_confidence} ({elapsed:.2f}s)"
                )

            result = {
                "home_corners_avg": home_corners,
                "away_corners_avg": away_corners,
                "corners_total_avg": safe_dict_get(
                    betting_stats, "corners_total_avg", default=None
                ),
                "corners_signal": corners_signal,
                "corners_reasoning": safe_dict_get(betting_stats, "corners_reasoning", default=""),
                "home_cards_avg": home_cards,
                "away_cards_avg": away_cards,
                "cards_total_avg": safe_dict_get(betting_stats, "cards_total_avg", default=None),
                "cards_signal": cards_signal,
                "cards_reasoning": safe_dict_get(betting_stats, "cards_reasoning", default=""),
                "data_confidence": data_confidence,
                "sources_found": safe_dict_get(
                    betting_stats, "sources_found", default="Perplexity search"
                ),
                "response_time": elapsed,
                "provider": "perplexity_v2.6",
            }

            # V7.1: Add form data if available
            if home_form_wins is not None:
                result["home_form_wins"] = home_form_wins
                result["home_form_draws"] = home_form_draws
                result["home_form_losses"] = home_form_losses
                result["home_goals_scored_last5"] = safe_dict_get(
                    betting_stats, "home_goals_scored_last5", default=None
                )
                result["home_goals_conceded_last5"] = safe_dict_get(
                    betting_stats, "home_goals_conceded_last5", default=None
                )

            if away_form_wins is not None:
                result["away_form_wins"] = away_form_wins
                result["away_form_draws"] = away_form_draws
                result["away_form_losses"] = away_form_losses
                result["away_goals_scored_last5"] = safe_dict_get(
                    betting_stats, "away_goals_scored_last5", default=None
                )
                result["away_goals_conceded_last5"] = safe_dict_get(
                    betting_stats, "away_goals_conceded_last5", default=None
                )

            # V7.1: Add referee data if available
            if referee_name and referee_name != "Unknown" and referee_cards_avg:
                result["referee_name"] = referee_name
                result["referee_cards_avg"] = referee_cards_avg

            # V7.2: Add match context data (always included)
            result["match_intensity"] = match_intensity
            result["referee_strictness"] = referee_strictness
            result["is_derby"] = is_derby

            return result

        except Exception as e:
            logger.warning(f"⚠️ [V2.6] Perplexity fallback failed: {e}")
            return None

        except Exception as e:
            logger.warning(f"⚠️ [V2.6] Perplexity fallback failed: {e}")
            return None


# ============================================
# PERPLEXITY VERIFIER (Fallback Provider)
# Requirements: 7.3, 7.4
# ============================================


class PerplexityVerifier:
    """
    Fallback verifier using Perplexity API.

    Used when Tavily is unavailable or fails.
    Provides identical interface to TavilyVerifier.

    Requirements: 7.3
    """

    def __init__(self, perplexity_provider: Optional["PerplexityProvider"] = None):
        """
        Initialize PerplexityVerifier.

        Args:
            perplexity_provider: Optional Perplexity provider instance
        """
        self._provider = perplexity_provider
        self._call_count = 0
        self._call_count_lock = threading.Lock()  # Thread safety for counter

    @property
    def provider(self) -> Optional["PerplexityProvider"]:
        """Get Perplexity provider (lazy initialization)."""
        if self._provider is None and PERPLEXITY_AVAILABLE:
            self._provider = get_perplexity_provider()
        return self._provider

    def is_available(self) -> bool:
        """Check if Perplexity is available for queries."""
        if not PERPLEXITY_AVAILABLE:
            return False
        provider = self.provider
        return provider is not None and provider.is_available()

    def build_verification_prompt(self, request: VerificationRequest) -> str:
        """
        Build a verification prompt for Perplexity.

        Args:
            request: VerificationRequest with match data

        Returns:
            Prompt string for Perplexity
        """
        parts = []

        parts.append(f"Match: {request.home_team} vs {request.away_team}")
        parts.append(f"Date: {request.match_date}")
        parts.append(f"League: {request.league}")
        parts.append("")
        parts.append("Please provide the following information in JSON format:")
        parts.append("")

        # Player importance
        all_missing = request.home_missing_players + request.away_missing_players
        if all_missing:
            parts.append(f"1. Player importance ratings (1-10) for: {', '.join(all_missing[:10])}")

        parts.append(
            f"2. Last 5 matches form for {request.home_team} (goals scored/conceded, W/D/L)"
        )
        parts.append(
            f"3. Last 5 matches form for {request.away_team} (goals scored/conceded, W/D/L)"
        )
        parts.append("4. Head-to-head last 5 matches: average goals, cards, corners")

        if request.fotmob_referee_name:
            parts.append(f"5. Referee {request.fotmob_referee_name} cards per game average")

        parts.append(f"6. {request.home_team} corners per game this season")
        parts.append(f"7. {request.away_team} corners per game this season")
        parts.append("")
        parts.append(
            "Return JSON with keys: player_impacts, home_form, away_form, h2h, referee, corners"
        )

        return "\n".join(parts)

    def query(self, request: VerificationRequest) -> dict[str, Any] | None:
        """
        Execute Perplexity query and return raw response.

        Args:
            request: VerificationRequest with match data

        Returns:
            Raw response dict or None on failure

        Requirements: 7.3
        """
        if not self.is_available():
            logger.warning("⚠️ [VERIFICATION] Perplexity not available")
            return None

        prompt = self.build_verification_prompt(request)

        logger.info(f"🔮 [VERIFICATION] Perplexity fallback query for {request.match_id}")
        start_time = time.time()

        try:
            # Use Perplexity's deep dive method with custom prompt
            result = self.provider._query_api(prompt)

            latency_ms = int((time.time() - start_time) * 1000)
            with self._call_count_lock:
                self._call_count += 1

            logger.info(f"🔮 [VERIFICATION] Perplexity response in {latency_ms}ms")

            if result:
                result["provider"] = "perplexity"
                result["response_time"] = latency_ms / 1000.0

            return result

        except Exception as e:
            logger.error(f"❌ [VERIFICATION] Perplexity query failed: {e}")
            return None

    def parse_response(
        self, response: dict[str, Any], request: VerificationRequest
    ) -> VerifiedData:
        """
        Parse Perplexity response into structured VerifiedData.

        Args:
            response: Raw Perplexity response dict
            request: Original verification request

        Returns:
            VerifiedData with parsed statistics
        """
        verified = VerifiedData(source="perplexity")

        if not response:
            verified.data_confidence = "Low"
            return verified

        # Parse player impacts from response
        player_impacts = safe_dict_get(response, "player_impacts", default={})
        if isinstance(player_impacts, dict):
            for name in request.home_missing_players:
                score = player_impacts.get(name, 5)
                if isinstance(score, (int, float)):
                    verified.home_player_impacts.append(
                        PlayerImpact(name=name, impact_score=int(round(score)))
                    )

            for name in request.away_missing_players:
                score = player_impacts.get(name, 5)
                if isinstance(score, (int, float)):
                    verified.away_player_impacts.append(
                        PlayerImpact(name=name, impact_score=int(round(score)))
                    )

        # Calculate totals
        verified.home_total_impact = sum(p.impact_score for p in verified.home_player_impacts)
        verified.away_total_impact = sum(p.impact_score for p in verified.away_player_impacts)

        # Parse form stats
        home_form_data = safe_dict_get(response, "home_form", default={})
        if isinstance(home_form_data, dict):
            verified.home_form = FormStats(
                goals_scored=home_form_data.get("goals_scored", 0),
                goals_conceded=home_form_data.get("goals_conceded", 0),
                wins=home_form_data.get("wins", 0),
                draws=home_form_data.get("draws", 0),
                losses=home_form_data.get("losses", 0),
            )

        away_form_data = safe_dict_get(response, "away_form", default={})
        if isinstance(away_form_data, dict):
            verified.away_form = FormStats(
                goals_scored=away_form_data.get("goals_scored", 0),
                goals_conceded=away_form_data.get("goals_conceded", 0),
                wins=away_form_data.get("wins", 0),
                draws=away_form_data.get("draws", 0),
                losses=away_form_data.get("losses", 0),
            )

        verified.form_confidence = "Medium" if verified.home_form or verified.away_form else "Low"

        # Parse H2H stats
        h2h_data = safe_dict_get(response, "h2h", default={})
        if isinstance(h2h_data, dict):
            verified.h2h = H2HStats(
                matches_analyzed=h2h_data.get("matches", 0),
                avg_goals=h2h_data.get("avg_goals", 0.0),
                avg_cards=h2h_data.get("avg_cards", 0.0),
                avg_corners=h2h_data.get("avg_corners", 0.0),
            )
            verified.h2h_confidence = "Medium" if verified.h2h.has_data() else "Low"

        # Parse referee stats
        referee_data = safe_dict_get(response, "referee", default={})
        if isinstance(referee_data, dict) and request.fotmob_referee_name:
            cards_avg = referee_data.get("cards_per_game", 0.0)
            if cards_avg > 0:
                verified.referee = RefereeStats(
                    name=request.fotmob_referee_name, cards_per_game=cards_avg
                )
                verified.referee_confidence = "Medium"

        # Parse corner stats
        corners_data = safe_dict_get(response, "corners", default={})
        if isinstance(corners_data, dict):
            verified.home_corner_avg = corners_data.get("home", None)
            verified.away_corner_avg = corners_data.get("away", None)
            verified.corner_confidence = "Medium" if verified.home_corner_avg else "Low"

        # V13.1: Parse cards stats for intelligent market decisions
        cards_data = safe_dict_get(response, "cards", default={})
        if isinstance(cards_data, dict):
            verified.home_cards_avg = cards_data.get("home_cards_avg", None)
            verified.away_cards_avg = cards_data.get("away_cards_avg", None)
            verified.cards_total_avg = cards_data.get("cards_total_avg", None)
            verified.cards_signal = cards_data.get("cards_signal", CardsSignal.UNKNOWN)
            verified.cards_reasoning = cards_data.get("cards_reasoning", "")
            verified.cards_confidence = "Medium" if verified.home_cards_avg else "Low"

        # Calculate overall confidence (unified algorithm across all providers)
        confidence_scores = [
            verified.form_confidence,
            verified.h2h_confidence,
            verified.referee_confidence,
            verified.corner_confidence,
        ]
        high_count = sum(1 for c in confidence_scores if c == "High")
        medium_count = sum(1 for c in confidence_scores if c == "Medium")

        if high_count >= 2:
            verified.data_confidence = "High"
        elif high_count >= 1 or medium_count >= 2:
            verified.data_confidence = "Medium"
        else:
            verified.data_confidence = "Low"

        return verified

    def get_call_count(self) -> int:
        """Get number of API calls made."""
        return self._call_count


# ============================================
# VERIFICATION ORCHESTRATOR
# Requirements: 7.1, 7.3, 7.4
# ============================================


class VerificationOrchestrator:
    """
    Orchestrates the verification process with fallback logic.

    Flow:
    1. Check if verification should be skipped (score < threshold)
    2. Try Tavily optimized queries first (V2.0)
    3. Fallback to legacy Tavily query
    4. Fallback to Perplexity if Tavily fails
    5. Return CONFIRM with LOW confidence if all fail

    Requirements: 7.1, 7.3, 7.4
    """

    def __init__(
        self,
        tavily_verifier: TavilyVerifier | None = None,
        perplexity_verifier: PerplexityVerifier | None = None,
        use_optimized_queries: bool = True,
    ):
        """
        Initialize VerificationOrchestrator.

        Args:
            tavily_verifier: Optional TavilyVerifier instance
            perplexity_verifier: Optional PerplexityVerifier instance
            use_optimized_queries: Use V2.0 optimized queries (default True)
        """
        self._tavily = tavily_verifier or TavilyVerifier()
        self._perplexity = perplexity_verifier or PerplexityVerifier()
        self._tavily_failures = 0
        self._perplexity_failures = 0
        self._use_optimized = use_optimized_queries
        # Thread safety for counters
        self._tavily_failures_lock = threading.Lock()
        self._perplexity_failures_lock = threading.Lock()

    def should_skip_verification(self, request: VerificationRequest) -> bool:
        """
        Check if verification should be skipped.

        Requirements: 7.1

        Args:
            request: VerificationRequest to check

        Returns:
            True if verification should be skipped
        """
        return request.preliminary_score < VERIFICATION_SCORE_THRESHOLD

    def get_verified_data(self, request: VerificationRequest) -> VerifiedData:
        """
        Get verified data using Tavily with Perplexity fallback.

        V2.0: Uses optimized multi-query approach for better data completeness.

        Requirements: 7.3, 7.4

        Args:
            request: VerificationRequest with match data

        Returns:
            VerifiedData from successful provider or empty with LOW confidence
        """
        # Try Tavily first
        if self._tavily.is_available():
            logger.info(f"🔍 [VERIFICATION] Trying Tavily for {request.match_id}")

            # V2.4: Try multi-site fallback queries first
            if self._use_optimized:
                response = self._tavily.query_with_fallback(request)

                if response:
                    self._tavily_failures = 0
                    verified = self._tavily.parse_optimized_response(response, request)

                    # Log fallback status
                    if safe_dict_get(response, "fallback_executed", default=False):
                        logger.info(
                            f"🔄 [VERIFICATION] Fallback executed for: {safe_dict_get(response, 'missing_data_types', default=[])}"
                        )

                    # V2.6: Integrate Perplexity corner data if available
                    # V7.1: Also integrate form and referee data
                    perplexity_data = response.get("perplexity_corners")
                    if perplexity_data and response.get("perplexity_fallback_executed"):
                        # Only update if corners were missing from Tavily
                        if verified.home_corner_avg is None:
                            verified.home_corner_avg = safe_dict_get(
                                perplexity_data, "home_corners_avg", default=None
                            )
                        if verified.away_corner_avg is None:
                            verified.away_corner_avg = safe_dict_get(
                                perplexity_data, "away_corners_avg", default=None
                            )

                        # Update confidence if we got corner data
                        if (
                            verified.home_corner_avg is not None
                            or verified.away_corner_avg is not None
                        ):
                            perplexity_confidence = safe_dict_get(
                                perplexity_data, "data_confidence", default="Low"
                            )
                            verified.corner_confidence = (
                                "Medium" if perplexity_confidence in ["High", "Medium"] else "Low"
                            )
                            verified.source = f"{verified.source}+perplexity_v2.6"
                            logger.info(
                                f"✅ [V2.6] Perplexity corners integrated: home={verified.home_corner_avg}, away={verified.away_corner_avg}"
                            )

                        # Extract corners_signal from Perplexity
                        corners_signal = safe_dict_get(
                            perplexity_data, "corners_signal", default="Unknown"
                        )
                        if SIGNAL_LEVEL_AVAILABLE:
                            try:
                                # Convert string to SignalLevel enum if needed
                                if isinstance(corners_signal, str):
                                    verified.corners_signal = SignalLevel(corners_signal)
                                else:
                                    verified.corners_signal = corners_signal
                            except (ValueError, TypeError):
                                verified.corners_signal = SignalLevel.UNKNOWN
                        else:
                            # Fallback if SignalLevel enum not available
                            verified.corners_signal = corners_signal

                        # Extract corners_reasoning from Perplexity
                        verified.corners_reasoning = safe_dict_get(
                            perplexity_data, "corners_reasoning", default=""
                        )

                        if (
                            verified.corners_signal != SignalLevel.UNKNOWN
                            if SIGNAL_LEVEL_AVAILABLE
                            else verified.corners_signal != "Unknown"
                        ):
                            logger.info(
                                f"✅ [V2.6] Perplexity corners_signal integrated: {verified.corners_signal.value if hasattr(verified.corners_signal, 'value') else verified.corners_signal}"
                            )

                        # V7.1: Integrate form data if missing from Tavily
                        if (
                            verified.home_form is None
                            and safe_dict_get(perplexity_data, "home_form_wins", default=None)
                            is not None
                        ):
                            verified.home_form = FormStats(
                                goals_scored=safe_dict_get(
                                    perplexity_data, "home_goals_scored_last5", default=0
                                )
                                or 0,
                                goals_conceded=safe_dict_get(
                                    perplexity_data, "home_goals_conceded_last5", default=0
                                )
                                or 0,
                                wins=safe_dict_get(perplexity_data, "home_form_wins", default=0)
                                or 0,
                                draws=safe_dict_get(perplexity_data, "home_form_draws", default=0)
                                or 0,
                                losses=safe_dict_get(perplexity_data, "home_form_losses", default=0)
                                or 0,
                            )
                            verified.form_confidence = "Medium"
                            logger.info(
                                f"✅ [V7.1] Perplexity home form integrated: W{verified.home_form.wins} D{verified.home_form.draws} L{verified.home_form.losses}"
                            )

                        if (
                            verified.away_form is None
                            and safe_dict_get(perplexity_data, "away_form_wins", default=None)
                            is not None
                        ):
                            verified.away_form = FormStats(
                                goals_scored=safe_dict_get(
                                    perplexity_data, "away_goals_scored_last5", default=0
                                )
                                or 0,
                                goals_conceded=safe_dict_get(
                                    perplexity_data, "away_goals_conceded_last5", default=0
                                )
                                or 0,
                                wins=safe_dict_get(perplexity_data, "away_form_wins", default=0)
                                or 0,
                                draws=safe_dict_get(perplexity_data, "away_form_draws", default=0)
                                or 0,
                                losses=safe_dict_get(perplexity_data, "away_form_losses", default=0)
                                or 0,
                            )
                            verified.form_confidence = "Medium"
                            logger.info(
                                f"✅ [V7.1] Perplexity away form integrated: W{verified.away_form.wins} D{verified.away_form.draws} L{verified.away_form.losses}"
                            )

                        # V7.1: Integrate referee data if missing from Tavily
                        if verified.referee is None and safe_dict_get(
                            perplexity_data, "referee_cards_avg", default=None
                        ):
                            referee_name = safe_dict_get(
                                perplexity_data, "referee_name", default="Unknown"
                            )
                            if referee_name and referee_name != "Unknown":
                                verified.referee = RefereeStats(
                                    name=referee_name,
                                    cards_per_game=safe_dict_get(
                                        perplexity_data, "referee_cards_avg", default=0.0
                                    )
                                    or 0.0,
                                )
                                verified.referee_confidence = "Medium"
                                logger.info(
                                    f"✅ [V7.1] Perplexity referee integrated: {referee_name} ({verified.referee.cards_per_game} cards/game)"
                                )

                    # Check if we got good data
                    # V2.6: If Perplexity found corners, return even with LOW confidence
                    # (corner data is valuable for combo suggestions)
                    has_perplexity_corners = safe_dict_get(
                        response, "perplexity_fallback_executed", default=False
                    ) and (
                        verified.home_corner_avg is not None or verified.away_corner_avg is not None
                    )

                    if verified.data_confidence in ["High", "Medium"]:
                        logger.info(
                            f"✅ [VERIFICATION] V2.4 queries successful: {verified.data_confidence} confidence"
                        )
                        return verified
                    elif has_perplexity_corners:
                        # V2.6: Return with Perplexity corners even if overall confidence is LOW
                        logger.info(
                            f"✅ [VERIFICATION V2.6] Returning with Perplexity corners (overall confidence: {verified.data_confidence})"
                        )
                        return verified
                    else:
                        logger.warning(
                            "⚠️ [VERIFICATION] V2.4 queries returned LOW confidence, trying legacy"
                        )

            # Fallback to legacy query
            response = self._tavily.query(request)

            if response:
                with self._tavily_failures_lock:
                    self._tavily_failures = 0
                return self._tavily.parse_response(response, request)
            else:
                with self._tavily_failures_lock:
                    self._tavily_failures += 1
                logger.warning(f"⚠️ [VERIFICATION] Tavily failed (attempt {self._tavily_failures})")

        # Fallback to Perplexity
        if self._perplexity.is_available():
            logger.info(f"🔮 [VERIFICATION] Falling back to Perplexity for {request.match_id}")
            response = self._perplexity.query(request)

            if response:
                with self._perplexity_failures_lock:
                    self._perplexity_failures = 0
                return self._perplexity.parse_response(response, request)
            else:
                with self._perplexity_failures_lock:
                    self._perplexity_failures += 1
                logger.warning(
                    f"⚠️ [VERIFICATION] Perplexity failed (attempt {self._perplexity_failures})"
                )

        # Both providers failed
        logger.error("❌ [VERIFICATION] All providers failed, returning empty data")
        return VerifiedData(source="none", data_confidence="Low")

    def get_provider_status(self) -> dict[str, Any]:
        """Get status of verification providers."""
        return {
            "tavily_available": self._tavily.is_available(),
            "tavily_failures": self._tavily_failures,
            "tavily_calls": self._tavily.get_call_count(),
            "perplexity_available": self._perplexity.is_available(),
            "perplexity_failures": self._perplexity_failures,
            "perplexity_calls": self._perplexity.get_call_count(),
            "optimized_queries_enabled": self._use_optimized,
        }


# ============================================
# LOGIC VALIDATOR
# Requirements: 8.1, 8.2, 8.3, 8.4, 2.2, 2.3, 3.2, 3.3, 3.4, 4.2, 4.3, 5.2, 5.3
# ============================================

# Score adjustment constants
CRITICAL_INJURY_OVER_PENALTY = 1.5  # Points to subtract from score
FORM_WARNING_PENALTY = 0.5
INCONSISTENCY_PENALTY = 0.3


class LogicValidator:
    """
    Validates the logic of alerts against verified data.

    Detects inconsistencies between:
    - Injury severity and suggested market
    - Recent form and suggested market
    - H2H data and suggested market
    - Referee stats and cards market
    - Corner data and corners market

    Requirements: 8.1, 8.2, 8.3, 8.4
    """

    def validate(self, request: VerificationRequest, verified: VerifiedData) -> VerificationResult:
        """
        Execute all validation checks and produce final result.

        Args:
            request: Original verification request
            verified: Verified data from external sources

        Returns:
            VerificationResult with status, adjustments, and reasoning
        """
        inconsistencies = []
        alternative_markets = []
        score_adjustments = []

        # 1. Check injury-market consistency
        injury_issues = self._check_injury_market_consistency(request, verified)
        inconsistencies.extend(injury_issues)

        # 2. Check form consistency
        form_issues = self._check_form_consistency(request, verified)
        inconsistencies.extend(form_issues)

        # 3. Check H2H alignment
        h2h_issues, h2h_alternatives = self._check_h2h_alignment(request, verified)
        inconsistencies.extend(h2h_issues)
        alternative_markets.extend(h2h_alternatives)

        # 4. Check referee suitability for cards market
        referee_issues = self._check_referee_suitability(request, verified)
        inconsistencies.extend(referee_issues)

        # 5. Check corner data for corner market
        corner_issues, corner_alternatives = self._check_corner_data(request, verified)
        inconsistencies.extend(corner_issues)
        alternative_markets.extend(corner_alternatives)

        # 6. V7.7: Check xG consistency for Over/Under markets
        xg_issues, xg_alternatives = self._check_xg_consistency(request, verified)
        inconsistencies.extend(xg_issues)
        alternative_markets.extend(xg_alternatives)

        # 7. Suggest alternative markets based on verified data
        suggested_alternatives = self._suggest_alternative_markets(request, verified)
        for alt in suggested_alternatives:
            if alt not in alternative_markets:
                alternative_markets.append(alt)

        # Calculate score adjustment
        adjusted_score = request.preliminary_score
        adjustment_reasons = []

        # Apply penalty for critical injury + Over market
        if self._should_apply_injury_penalty(request, verified):
            adjusted_score -= CRITICAL_INJURY_OVER_PENALTY
            adjustment_reasons.append(
                f"Penalità infortuni critici: -{CRITICAL_INJURY_OVER_PENALTY}"
            )

        # Apply penalty for form warnings
        if verified.home_form and verified.away_form:
            if verified.both_teams_low_scoring() and request.is_over_market():
                adjusted_score -= FORM_WARNING_PENALTY
                adjustment_reasons.append(f"Penalità forma bassa: -{FORM_WARNING_PENALTY}")

        # Apply penalty for each inconsistency
        if inconsistencies:
            penalty = len(inconsistencies) * INCONSISTENCY_PENALTY
            adjusted_score -= penalty
            adjustment_reasons.append(
                f"Penalità incongruenze ({len(inconsistencies)}): -{penalty:.1f}"
            )

        # Ensure score doesn't go below 0
        adjusted_score = max(0.0, adjusted_score)

        # Determine status
        status = self._determine_status(request, verified, inconsistencies, adjusted_score)

        # Determine recommended market if status is CHANGE_MARKET
        recommended_market = None
        if status == VerificationStatus.CHANGE_MARKET and alternative_markets:
            recommended_market = alternative_markets[0]

        # Build reasoning in Italian
        reasoning = self._build_reasoning(
            request, verified, inconsistencies, adjustment_reasons, status, recommended_market
        )

        # Determine overall confidence
        overall_confidence = self._calculate_confidence(verified, inconsistencies)

        # Build rejection reason if applicable
        rejection_reason = None
        if status == VerificationStatus.REJECT:
            if verified.data_confidence == "Low" and len(inconsistencies) >= 2:
                rejection_reason = "insufficient_data"
            elif len(inconsistencies) >= 3:
                rejection_reason = "multiple_inconsistencies"
            else:
                rejection_reason = "logic_inconsistency"

        return VerificationResult(
            status=status,
            original_score=request.preliminary_score,
            adjusted_score=adjusted_score,
            score_adjustment_reason="; ".join(adjustment_reasons) if adjustment_reasons else None,
            original_market=request.suggested_market,
            recommended_market=recommended_market,
            alternative_markets=alternative_markets,
            inconsistencies=inconsistencies,
            overall_confidence=overall_confidence,
            reasoning=reasoning,
            verified_data=verified,
            rejection_reason=rejection_reason,
        )

    def _check_injury_market_consistency(
        self, request: VerificationRequest, verified: VerifiedData
    ) -> list[str]:
        """
        Check if suggested market is consistent with injury data.

        Requirements: 8.1, 8.2

        Key rule: CRITICAL injury + Over market = inconsistency
        """
        issues = []

        # Check for CRITICAL injury + Over market inconsistency
        if request.has_critical_injuries() and request.is_over_market():
            if request.has_critical_injuries("home"):
                issues.append(
                    f"Infortuni CRITICI per {request.home_team} incompatibili con mercato Over"
                )
            if request.has_critical_injuries("away"):
                issues.append(
                    f"Infortuni CRITICI per {request.away_team} incompatibili con mercato Over"
                )

        # Check for high key player impact
        if verified.has_critical_key_player_impact() and request.is_over_market():
            total_impact = verified.get_total_key_player_impact()
            issues.append(
                f"Impatto giocatori chiave ({total_impact:.0f}) supera soglia critica ({CRITICAL_IMPACT_THRESHOLD})"
            )

        # V13.0: Check for critical goalkeeper missing - tactical intelligence
        # Missing goalkeeper significantly increases defensive vulnerability
        if request.is_over_market():
            if verified.has_critical_goalkeeper_missing("home"):
                issues.append(
                    f"Portiere critico mancante per {request.home_team} - vulnerabilità difensiva elevata"
                )
            if verified.has_critical_goalkeeper_missing("away"):
                issues.append(
                    f"Portiere critico mancante per {request.away_team} - vulnerabilità difensiva elevata"
                )

        # V13.0: Check for critical defense missing - tactical intelligence
        # Missing multiple defenders creates defensive gaps that can be exploited
        if request.is_over_market():
            if verified.has_critical_defense_missing("home"):
                issues.append(
                    f"Più difensori critici mancanti per {request.home_team} - gaps difensivi significativi"
                )
            if verified.has_critical_defense_missing("away"):
                issues.append(
                    f"Più difensori critici mancanti per {request.away_team} - gaps difensivi significativi"
                )

        # V13.0: Check position-based impact summary for tactical insights
        # This provides detailed analysis of which positions are most affected
        if request.is_over_market() and (
            verified.home_player_impacts or verified.away_player_impacts
        ):
            home_pos_summary = verified.get_position_impact_summary("home")
            away_pos_summary = verified.get_position_impact_summary("away")

            # Check if defensive positions are heavily impacted
            home_defense_impact = home_pos_summary.get("defender", 0) + home_pos_summary.get(
                "goalkeeper", 0
            )
            away_defense_impact = away_pos_summary.get("defender", 0) + away_pos_summary.get(
                "goalkeeper", 0
            )

            if home_defense_impact >= 15:
                issues.append(
                    f"Impatto difensivo elevato per {request.home_team} ({home_defense_impact:.0f}) - rischio gol subiti"
                )
            if away_defense_impact >= 15:
                issues.append(
                    f"Impatto difensivo elevato per {request.away_team} ({away_defense_impact:.0f}) - rischio gol subiti"
                )

        # V13.0: Check reason-based impact summary for tactical insights
        # Different reasons (injury vs suspension) may have different tactical implications
        if request.is_over_market() and (
            verified.home_player_impacts or verified.away_player_impacts
        ):
            home_reason_summary = verified.get_reason_impact_summary("home")
            away_reason_summary = verified.get_reason_impact_summary("away")

            # Suspensions may be more predictable than injuries
            home_suspension_impact = home_reason_summary.get("suspension", 0)
            away_suspension_impact = away_reason_summary.get("suspension", 0)

            if home_suspension_impact >= 10:
                issues.append(
                    f"Squalifiche multiple per {request.home_team} (impatto {home_suspension_impact:.0f}) - formazione nota ma ridotta"
                )
            if away_suspension_impact >= 10:
                issues.append(
                    f"Squalifiche multiple per {request.away_team} (impatto {away_suspension_impact:.0f}) - formazione nota ma ridotta"
                )

        return issues

    def _check_form_consistency(
        self, request: VerificationRequest, verified: VerifiedData
    ) -> list[str]:
        """
        Check if suggested market is consistent with recent form.

        Requirements: 2.2, 2.3, 8.3
        """
        issues = []

        # Check for both teams low scoring + Over market
        if verified.both_teams_low_scoring() and request.is_over_market():
            home_avg = verified.home_form.avg_goals_scored if verified.home_form else 0
            away_avg = verified.away_form.avg_goals_scored if verified.away_form else 0
            issues.append(
                f"Entrambe le squadre a basso punteggio (casa: {home_avg:.1f}, trasferta: {away_avg:.1f}) "
                f"incompatibili con mercato Over"
            )

        # Check for losing streak
        if verified.home_form and verified.home_form.is_on_losing_streak():
            # Check if we're betting on home team
            if request.suggested_market in ["1", "1X"]:
                issues.append(
                    f"{request.home_team} in serie negativa (0 vittorie ultime 5) - "
                    f"scommessa su vittoria casa rischiosa"
                )

        if verified.away_form and verified.away_form.is_on_losing_streak():
            if request.suggested_market in ["2", "X2"]:
                issues.append(
                    f"{request.away_team} in serie negativa (0 vittorie ultime 5) - "
                    f"scommessa su vittoria trasferta rischiosa"
                )

        return issues

    def _check_h2h_alignment(self, request: VerificationRequest, verified: VerifiedData) -> tuple:
        """
        Check if suggested market aligns with H2H data.

        Requirements: 3.2, 3.3, 3.4

        Returns:
            Tuple of (issues, alternative_markets)
        """
        issues = []
        alternatives = []

        if not verified.h2h or not verified.h2h.has_data():
            return issues, alternatives

        # Check H2H cards for Over Cards suggestion
        if verified.h2h.suggests_over_cards():
            if not request.is_cards_market():
                alternatives.append("Over 4.5 Cards")

        # Check H2H corners for Over Corners suggestion
        if verified.h2h.suggests_over_corners():
            if not request.is_corners_market():
                alternatives.append("Over 9.5 Corners")

        # V2.6: Check corners_signal from Perplexity for Over Corners suggestion
        if SIGNAL_LEVEL_AVAILABLE and verified.corners_signal == SignalLevel.HIGH:
            if not request.is_corners_market():
                alternatives.append("Over 9.5 Corners (Perplexity Signal: High)")
        elif SIGNAL_LEVEL_AVAILABLE and verified.corners_signal == SignalLevel.MEDIUM:
            if not request.is_corners_market():
                alternatives.append("Over 9.5 Corners (Perplexity Signal: Medium)")

        # Check H2H goals vs suggested Over/Under
        if request.is_over_market():
            # If H2H shows low goals, flag inconsistency
            if verified.h2h.avg_goals < 2.0:
                issues.append(
                    f"H2H mostra media gol bassa ({verified.h2h.avg_goals:.1f}) - "
                    f"mercato Over potrebbe essere rischioso"
                )

        return issues, alternatives

    def _check_referee_suitability(
        self, request: VerificationRequest, verified: VerifiedData
    ) -> list[str]:
        """
        Check if referee is suitable for cards market.

        Requirements: 4.2, 4.3
        """
        issues = []

        if not verified.referee:
            return issues

        # Check for lenient referee + Over Cards suggestion
        if verified.referee.should_veto_cards() and request.is_cards_market():
            veto_reason = (
                f"Arbitro {verified.referee.name} troppo permissivo "
                f"({verified.referee.cards_per_game:.1f} cartellini/partita) - "
                f"veto su mercato Over Cards"
            )
            issues.append(veto_reason)

            # Log veto applied in referee boost logger
            if REFEREE_BOOST_LOGGER_AVAILABLE:
                try:
                    logger_module = get_referee_boost_logger()
                    logger_module.log_veto_applied(
                        referee_name=verified.referee.name,
                        cards_per_game=verified.referee.cards_per_game,
                        strictness=verified.referee.strictness,
                        recommended_market=request.recommended_market
                        if hasattr(request, "recommended_market")
                        else "Over Cards",
                        reason=veto_reason,
                        match_id=request.match_id if hasattr(request, "match_id") else None,
                        home_team=request.home_team if hasattr(request, "home_team") else None,
                        away_team=request.away_team if hasattr(request, "away_team") else None,
                        league=request.league if hasattr(request, "league") else None,
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log veto applied: {e}")

        return issues

    def _check_corner_data(self, request: VerificationRequest, verified: VerifiedData) -> tuple:
        """
        Check corner data for corner market suggestions.

        Requirements: 5.2, 5.3

        Returns:
            Tuple of (issues, alternative_markets)
        """
        issues = []
        alternatives = []

        # Check if combined corners suggest Over 9.5
        # V7.0.2: Removed unused 'combined' variable
        if verified.suggests_over_corners():
            if not request.is_corners_market():
                alternatives.append("Over 9.5 Corners")

        # Check if H2H corners differ significantly from season average
        if verified.h2h_corner_avg and verified.home_corner_avg and verified.away_corner_avg:
            season_avg = verified.home_corner_avg + verified.away_corner_avg
            h2h_avg = verified.h2h_corner_avg

            if abs(h2h_avg - season_avg) > 3.0:  # Significant difference
                issues.append(
                    f"Media corner H2H ({h2h_avg:.1f}) differisce significativamente "
                    f"dalla media stagionale ({season_avg:.1f})"
                )

        return issues, alternatives

    def _check_xg_consistency(self, request: VerificationRequest, verified: VerifiedData) -> tuple:
        """
        V7.7: Check xG data consistency with Over/Under market suggestions.

        If xG data is available, verify that:
        - Over 2.5 suggestion aligns with combined xG > 2.3
        - Under 2.5 suggestion aligns with combined xG < 2.3

        Returns:
            Tuple of (issues, alternative_markets)
        """
        issues = []
        alternatives = []

        # Skip if no xG data available
        if not verified.home_xg and not verified.away_xg:
            return issues, alternatives

        # Calculate combined xG (use available data)
        home_xg = verified.home_xg or 1.2  # Default if missing
        away_xg = verified.away_xg or 1.0
        combined_xg = home_xg + away_xg

        market = request.suggested_market.lower() if request.suggested_market else ""

        # Check Over 2.5 consistency
        if "over 2.5" in market or "over2.5" in market:
            if combined_xg < 2.0:
                issues.append(f"Over 2.5 suggerito ma xG combinato basso ({combined_xg:.2f})")
                alternatives.append("Under 2.5 Goals")

        # Check Under 2.5 consistency
        if "under 2.5" in market or "under2.5" in market:
            if combined_xg > 3.0:
                issues.append(f"Under 2.5 suggerito ma xG combinato alto ({combined_xg:.2f})")
                alternatives.append("Over 2.5 Goals")

        # Suggest Under 2.5 if xG is very low and not already suggested
        if combined_xg < 2.0 and "under" not in market:
            if verified.xg_confidence in ("Medium", "High"):
                if "Under 2.5 Goals" not in alternatives:
                    alternatives.append("Under 2.5 Goals")

        return issues, alternatives

    def _suggest_alternative_markets(
        self, request: VerificationRequest, verified: VerifiedData
    ) -> list[str]:
        """
        Suggest alternative markets based on verified data.

        Requirements: 8.2
        V13.1: Enhanced with intelligent cards market suggestions
        """
        alternatives = []

        # If both teams have CRITICAL injuries, suggest Under
        if request.both_teams_critical():
            if "Under" not in request.suggested_market:
                alternatives.append("Under 2.5 Goals")

        # If both teams low scoring, suggest Under
        if verified.both_teams_low_scoring():
            if "Under" not in request.suggested_market:
                alternatives.append("Under 2.5 Goals")

        # If referee is strict, suggest Over Cards
        if verified.referee and verified.referee.is_strict():
            if not request.is_cards_market():
                alternatives.append("Over 4.5 Cards")

        # V13.1: Intelligent cards market suggestions based on cards_signal
        # Suggest Over 4.5 Cards if signal is Aggressive and combined average supports it
        if verified.is_cards_aggressive() and verified.suggests_over_cards():
            if not request.is_cards_market():
                alternatives.append("Over 4.5 Cards")

        # Suggest Under 4.5 Cards if signal is Disciplined and not already a cards market
        if verified.is_cards_disciplined():
            if not request.is_cards_market():
                alternatives.append("Under 4.5 Cards")

        # Suggest Over 4.5 Cards if combined average is high (>5.0) regardless of signal
        if verified.cards_total_avg and verified.cards_total_avg > 5.0:
            if not request.is_cards_market():
                alternatives.append("Over 4.5 Cards")

        return alternatives

    def _should_apply_injury_penalty(
        self, request: VerificationRequest, verified: VerifiedData
    ) -> bool:
        """
        Check if injury penalty should be applied.

        Requirements: 8.1

        Penalty applies when:
        - Team has CRITICAL injury severity AND
        - Suggested market is Over 2.5 Goals
        """
        if not request.is_over_market():
            return False

        # Check for CRITICAL severity
        if request.has_critical_injuries():
            return True

        # Check for high key player impact
        if verified.has_critical_key_player_impact():
            return True

        return False

    def _determine_status(
        self,
        request: VerificationRequest,
        verified: VerifiedData,
        inconsistencies: list[str],
        adjusted_score: float,
    ) -> VerificationStatus:
        """
        Determine the final verification status.

        Requirements: 6.1, 6.2, 6.3
        """
        # REJECT if confidence is Low and multiple inconsistencies
        if verified.data_confidence == "Low" and len(inconsistencies) >= 2:
            return VerificationStatus.REJECT

        # REJECT if too many inconsistencies
        if len(inconsistencies) >= 3:
            return VerificationStatus.REJECT

        # REJECT if adjusted score dropped too much
        score_drop = request.preliminary_score - adjusted_score
        if score_drop >= 2.0:
            return VerificationStatus.REJECT

        # CHANGE_MARKET if significant inconsistency with market
        if len(inconsistencies) >= 1:
            # Check if inconsistency is market-specific
            market_inconsistencies = [
                i
                for i in inconsistencies
                if "mercato" in i.lower() or "over" in i.lower() or "under" in i.lower()
            ]
            if market_inconsistencies:
                return VerificationStatus.CHANGE_MARKET

        # CONFIRM if no major issues
        return VerificationStatus.CONFIRM

    def _calculate_confidence(self, verified: VerifiedData, inconsistencies: list[str]) -> str:
        """
        Calculate overall confidence level.
        """
        # Start with data confidence
        if verified.data_confidence == "High":
            base = 3
        elif verified.data_confidence == "Medium":
            base = 2
        else:
            base = 1

        # Reduce for inconsistencies
        base -= len(inconsistencies) * 0.5

        if base >= 2.5:
            return "HIGH"
        elif base >= 1.5:
            return "MEDIUM"
        else:
            return "LOW"

    def _build_reasoning(
        self,
        request: VerificationRequest,
        verified: VerifiedData,
        inconsistencies: list[str],
        adjustment_reasons: list[str],
        status: VerificationStatus,
        recommended_market: str | None,
    ) -> str:
        """
        Build human-readable reasoning in Italian.

        Requirements: 6.5
        """
        parts = []

        # Status summary
        if status == VerificationStatus.CONFIRM:
            parts.append("✅ Verifica completata: alert confermato.")
        elif status == VerificationStatus.REJECT:
            parts.append("❌ Verifica completata: alert respinto.")
        else:
            parts.append("🔄 Verifica completata: mercato da modificare.")

        # Data confidence
        parts.append(f"Confidenza dati: {verified.data_confidence}.")

        # Key findings
        if verified.home_form or verified.away_form:
            if verified.both_teams_low_scoring():
                parts.append("⚠️ Entrambe le squadre a basso punteggio nelle ultime 5 partite.")

        if verified.has_critical_key_player_impact():
            total = verified.get_total_key_player_impact()
            parts.append(f"⚠️ Impatto giocatori chiave elevato: {total:.0f} punti.")

        if verified.referee and verified.referee.is_strict():
            parts.append(
                f"⚖️ Arbitro severo: {verified.referee.name} ({verified.referee.cards_per_game:.1f} cartellini/partita)."
            )
        elif verified.referee and verified.referee.is_lenient():
            parts.append(
                f"⚖️ Arbitro permissivo: {verified.referee.name} ({verified.referee.cards_per_game:.1f} cartellini/partita)."
            )

        if verified.suggests_over_corners():
            combined = verified.get_combined_corner_avg()
            parts.append(f"🚩 Media corner combinata alta: {combined:.1f}.")

        # V2.6: Include corners_signal from Perplexity in summary
        if SIGNAL_LEVEL_AVAILABLE and verified.corners_signal != SignalLevel.UNKNOWN:
            signal_value = (
                verified.corners_signal.value
                if hasattr(verified.corners_signal, "value")
                else verified.corners_signal
            )
            parts.append(f"🎯 Segnale corner Perplexity: {signal_value}.")
            if verified.corners_reasoning:
                parts.append(
                    f"📝 Ragionamento corner: {verified.corners_reasoning[:100]}..."
                )  # Limit to 100 chars

        # Inconsistencies
        if inconsistencies:
            parts.append(f"⚠️ Incongruenze rilevate ({len(inconsistencies)}):")
            for issue in inconsistencies[:3]:  # Limit to 3
                parts.append(f"  - {issue}")

        # Score adjustment
        if adjustment_reasons:
            parts.append(f"📊 Aggiustamento score: {'; '.join(adjustment_reasons)}")

        # Recommendation
        if recommended_market:
            parts.append(f"🎯 Mercato consigliato: {recommended_market}")

        return " ".join(parts)


# ============================================
# MAIN VERIFICATION FLOW
# Requirements: 6.1, 7.1
# ============================================

# Singleton instances
_orchestrator: VerificationOrchestrator | None = None
_validator: LogicValidator | None = None
# Thread safety for singleton creation
_orchestrator_lock = threading.Lock()
_validator_lock = threading.Lock()


def get_verification_orchestrator() -> VerificationOrchestrator:
    """Get or create singleton VerificationOrchestrator (thread-safe)."""
    global _orchestrator
    # Double-checked locking pattern for thread safety
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = VerificationOrchestrator()
    return _orchestrator


def get_logic_validator() -> LogicValidator:
    """Get or create singleton LogicValidator (thread-safe)."""
    global _validator
    # Double-checked locking pattern for thread safety
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = LogicValidator()
    return _validator


def verify_alert(request: VerificationRequest) -> VerificationResult:
    """
    Main entry point for alert verification.

    This function orchestrates the entire verification process:
    1. Check if verification should be skipped (score < threshold)
    2. Query external sources (Tavily with Perplexity fallback)
    3. Parse and validate the response
    4. Apply logic validation
    5. Return final result

    Args:
        request: VerificationRequest with all match and alert data

    Returns:
        VerificationResult with status, adjustments, and reasoning

    Requirements: 6.1, 7.1
    """
    orchestrator = get_verification_orchestrator()
    validator = get_logic_validator()

    logger.info(f"🔍 [VERIFICATION] Starting verification for {request.match_id}")
    logger.info(f"   Match: {request.home_team} vs {request.away_team}")
    logger.info(f"   Score: {request.preliminary_score}, Market: {request.suggested_market}")

    # Step 1: Check if verification should be skipped
    if orchestrator.should_skip_verification(request):
        logger.info(
            f"⏭️ [VERIFICATION] Skipped - score {request.preliminary_score} < {VERIFICATION_SCORE_THRESHOLD}"
        )
        return create_skip_result(
            request,
            f"Score {request.preliminary_score} sotto soglia {VERIFICATION_SCORE_THRESHOLD}",
        )

    # Step 2: Get verified data from external sources
    try:
        verified_data = orchestrator.get_verified_data(request)
        logger.info(f"📊 [VERIFICATION] Data confidence: {verified_data.data_confidence}")
        logger.info(f"   Source: {verified_data.source}")
    except Exception as e:
        logger.error(f"❌ [VERIFICATION] Failed to get verified data: {e}")
        return create_fallback_result(request, f"Errore recupero dati: {str(e)}")

    # Step 3: Validate logic
    try:
        result = validator.validate(request, verified_data)

        logger.info(f"✅ [VERIFICATION] Complete - Status: {result.status.value}")
        logger.info(
            f"   Original score: {result.original_score}, Adjusted: {result.adjusted_score}"
        )
        if result.inconsistencies:
            logger.info(f"   Inconsistencies: {len(result.inconsistencies)}")
        if result.recommended_market:
            logger.info(f"   Recommended market: {result.recommended_market}")

        # V11.0: Validate against contract
        if _CONTRACTS_AVAILABLE:
            try:
                # Convert VerificationResult to dict for validation
                result_dict = result.to_dict()
                VERIFICATION_RESULT_CONTRACT.assert_valid(
                    result_dict,
                    context=f"verify_alert(match_id={request.match_id})",
                )
            except ContractViolation as e:
                logging.warning(f"⚠️ Contract violation in VerificationResult: {e}")
                # Return result anyway to avoid breaking the verification flow
                # The violation is logged for debugging purposes

        return result

    except Exception as e:
        logger.error(f"❌ [VERIFICATION] Validation failed: {e}")
        return create_fallback_result(request, f"Errore validazione: {str(e)}")


def should_verify_alert(preliminary_score: float) -> bool:
    """
    Quick check if an alert should be verified.

    Use this before constructing a full VerificationRequest
    to avoid unnecessary work.

    Args:
        preliminary_score: The alert's preliminary score

    Returns:
        True if verification should be performed

    Requirements: 7.1
    """
    return preliminary_score >= VERIFICATION_SCORE_THRESHOLD


def create_verification_request_from_match(
    match,  # Match database object
    analysis,  # NewsLog analysis object
    home_stats: dict = None,
    away_stats: dict = None,
    home_context: dict = None,
    away_context: dict = None,
    home_team_injury_impact: Any = None,  # TeamInjuryImpact object
    away_team_injury_impact: Any = None,  # TeamInjuryImpact object
) -> VerificationRequest:
    """
    Create a VerificationRequest from existing match and analysis objects.

    This is a convenience function for integration with main.py.

    Args:
        match: Match database object with team names, date, league
        analysis: NewsLog object with score, market, injury data
        home_stats: Optional FotMob stats for home team
        away_stats: Optional FotMob stats for away team
        home_context: Optional FotMob full context for home team (injuries, motivation, fatigue)
        away_context: Optional FotMob full context for away team (injuries, motivation, fatigue)
        home_team_injury_impact: Optional TeamInjuryImpact object with detailed player data
        away_team_injury_impact: Optional TeamInjuryImpact object with detailed player data

    Returns:
        VerificationRequest ready for verification
    """
    # Extract match info
    match_id = str(getattr(match, "id", "unknown"))
    home_team = getattr(match, "home_team", "Unknown")
    away_team = getattr(match, "away_team", "Unknown")
    league = getattr(match, "league", "unknown")

    # VPS FIX: Extract match start_time safely to prevent session detachment
    start_time = getattr(match, "start_time", None)

    # Extract match date
    match_date = "unknown"
    if start_time:
        match_date = start_time.strftime("%Y-%m-%d")

    # Extract analysis info
    analysis_score = getattr(analysis, "score", None)
    preliminary_score = float(analysis_score or 0) if analysis_score is not None else 0.0
    suggested_market = getattr(analysis, "recommended_market", "") or getattr(
        analysis, "primary_market", "Unknown"
    )

    # Extract injury info - prioritize FotMob context, fallback to analysis object
    home_missing = []
    away_missing = []
    home_severity = "LOW"
    away_severity = "LOW"
    home_impact = 0.0
    away_impact = 0.0

    # V7.0.1: Extract injury data from FotMob context (primary source)
    if home_context and isinstance(home_context, dict):
        injuries = home_context.get("injuries", [])
        if isinstance(injuries, list) and injuries:
            home_missing = [
                inj.get("name", "") for inj in injuries if isinstance(inj, dict) and inj.get("name")
            ]
            # Calculate severity based on number of injuries
            home_severity = _calculate_injury_severity(len(home_missing))
            home_impact = len(home_missing) * 3.0  # Rough impact estimate

    if away_context and isinstance(away_context, dict):
        injuries = away_context.get("injuries", [])
        if isinstance(injuries, list) and injuries:
            away_missing = [
                inj.get("name", "") for inj in injuries if isinstance(inj, dict) and inj.get("name")
            ]
            away_severity = _calculate_injury_severity(len(away_missing))
            away_impact = len(away_missing) * 3.0

    # Fallback: Try to extract from analysis object if FotMob context not available
    if not home_missing and hasattr(analysis, "home_missing_players"):
        home_missing = analysis.home_missing_players or []
    if not away_missing and hasattr(analysis, "away_missing_players"):
        away_missing = analysis.away_missing_players or []
    if home_severity == "LOW" and hasattr(analysis, "home_injury_severity"):
        home_severity = analysis.home_injury_severity or "LOW"
    if away_severity == "LOW" and hasattr(analysis, "away_injury_severity"):
        away_severity = analysis.away_injury_severity or "LOW"
    if home_impact == 0.0 and hasattr(analysis, "home_injury_impact"):
        home_impact = float(analysis.home_injury_impact or 0)
    if away_impact == 0.0 and hasattr(analysis, "away_injury_impact"):
        away_impact = float(analysis.away_injury_impact or 0)

    # Extract FotMob data
    fotmob_home_goals = None
    fotmob_away_goals = None
    fotmob_referee = None

    if home_stats:
        fotmob_home_goals = home_stats.get("goals_avg")
    if away_stats:
        fotmob_away_goals = away_stats.get("goals_avg")

    # Try to get referee from match
    if hasattr(match, "referee_name"):
        fotmob_referee = match.referee_name

    return VerificationRequest(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        league=league,
        preliminary_score=preliminary_score,
        suggested_market=suggested_market,
        home_missing_players=home_missing,
        away_missing_players=away_missing,
        home_injury_severity=home_severity,
        away_injury_severity=away_severity,
        home_injury_impact=home_impact,
        away_injury_impact=away_impact,
        fotmob_home_goals_avg=fotmob_home_goals,
        fotmob_away_goals_avg=fotmob_away_goals,
        fotmob_referee_name=fotmob_referee,
        home_team_injury_impact=home_team_injury_impact,
        away_team_injury_impact=away_team_injury_impact,
    )


def _calculate_injury_severity(num_injuries: int) -> str:
    """
    Calculate injury severity based on number of missing players.

    Args:
        num_injuries: Number of injured/unavailable players

    Returns:
        Severity level: CRITICAL, HIGH, MEDIUM, or LOW
    """
    if num_injuries >= 5:
        return "CRITICAL"
    elif num_injuries >= 3:
        return "HIGH"
    elif num_injuries >= 1:
        return "MEDIUM"
    return "LOW"


# ============================================
# ITALIAN REASONING BUILDER
# Requirements: 6.5
# ============================================


def build_italian_reasoning(
    status: VerificationStatus,
    verified: VerifiedData,
    inconsistencies: list[str],
    recommended_market: str | None = None,
) -> str:
    """
    Build human-readable reasoning in Italian.

    This is a standalone function that can be used to generate
    reasoning for any verification result.

    Args:
        status: Verification status
        verified: Verified data
        inconsistencies: List of detected inconsistencies
        recommended_market: Recommended alternative market

    Returns:
        Italian-language reasoning string

    Requirements: 6.5
    """
    parts = []

    # Status header
    if status == VerificationStatus.CONFIRM:
        parts.append("✅ Alert confermato dalla verifica.")
    elif status == VerificationStatus.REJECT:
        parts.append("❌ Alert respinto dalla verifica.")
    elif status == VerificationStatus.CHANGE_MARKET:
        parts.append("🔄 Mercato da modificare.")

    # Data quality
    if verified.data_confidence == "High":
        parts.append("Dati verificati con alta confidenza.")
    elif verified.data_confidence == "Medium":
        parts.append("Dati verificati con confidenza media.")
    else:
        parts.append("⚠️ Dati verificati con bassa confidenza.")

    # Key findings
    findings = []

    if verified.home_form and verified.away_form:
        if verified.both_teams_low_scoring():
            findings.append("entrambe le squadre a basso punteggio")

    if verified.has_critical_key_player_impact():
        total = verified.get_total_key_player_impact()
        findings.append(f"impatto giocatori chiave elevato ({total:.0f} punti)")

    if verified.referee:
        if verified.referee.is_strict():
            findings.append(
                f"arbitro severo ({verified.referee.cards_per_game:.1f} cartellini/partita)"
            )
        elif verified.referee.is_lenient():
            findings.append(
                f"arbitro permissivo ({verified.referee.cards_per_game:.1f} cartellini/partita)"
            )

    if verified.suggests_over_corners():
        combined = verified.get_combined_corner_avg()
        findings.append(f"media corner alta ({combined:.1f})")

    # V2.6: Include corners_signal from Perplexity in findings
    if SIGNAL_LEVEL_AVAILABLE and verified.corners_signal != SignalLevel.UNKNOWN:
        signal_value = (
            verified.corners_signal.value
            if hasattr(verified.corners_signal, "value")
            else verified.corners_signal
        )
        findings.append(f"segnale corner Perplexity: {signal_value}")

    if findings:
        parts.append("Rilevato: " + ", ".join(findings) + ".")

    # Inconsistencies
    if inconsistencies:
        parts.append(f"⚠️ {len(inconsistencies)} incongruenze rilevate.")

    # Recommendation
    if recommended_market:
        parts.append(f"🎯 Mercato consigliato: {recommended_market}")

    return " ".join(parts)


# ============================================
# EXPORTS
# ============================================

__all__ = [
    # Data classes
    "VerificationRequest",
    "VerifiedData",
    "VerificationResult",
    "PlayerImpact",
    "FormStats",
    "H2HStats",
    "RefereeStats",
    # Enums
    "VerificationStatus",
    "ConfidenceLevel",
    "InjurySeverity",
    # Verifiers
    "TavilyVerifier",
    "PerplexityVerifier",
    "VerificationOrchestrator",
    "LogicValidator",
    # Main functions
    "verify_alert",
    "should_verify_alert",
    "create_verification_request_from_match",
    # Factory functions
    "create_skip_result",
    "create_fallback_result",
    "create_rejection_result",
    # Helpers
    "build_italian_reasoning",
    # Constants
    "VERIFICATION_SCORE_THRESHOLD",
    "PLAYER_KEY_IMPACT_THRESHOLD",
    "CRITICAL_IMPACT_THRESHOLD",
    "H2H_CARDS_THRESHOLD",
    "H2H_CORNERS_THRESHOLD",
    "H2H_MIN_MATCHES",
    "H2H_MAX_CARDS",
    "H2H_MAX_CORNERS",
    "H2H_MAX_GOALS",
    "COMBINED_CORNERS_THRESHOLD",
    "REFEREE_STRICT_THRESHOLD",
    "REFEREE_LENIENT_THRESHOLD",
    "REFEREE_CARDS_BOOST_THRESHOLD",
    "FORM_DEVIATION_THRESHOLD",
    "LOW_SCORING_THRESHOLD",
]
