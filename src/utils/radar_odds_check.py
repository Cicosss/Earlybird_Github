"""
EarlyBird Radar Odds Check Module V1.0

Verifica se le quote si sono già mosse PRIMA di inviare un alert.
Questo aiuta a identificare se il mercato ha già prezzato la notizia.

Logica:
- Se le quote sono stabili → EDGE REALE → priorità massima
- Se le quote sono già crollate → mercato sa già → alert meno utile

Integrazione:
- Chiamato da news_radar.py prima di inviare alert
- Usa dati già in database (no API call extra se possibile)
- Fallback leggero a Odds API se necessario

V1.0: Initial implementation
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger(__name__)

# Team abbreviation/alias mapping for intelligent matching
# Maps common abbreviations to full team names
TEAM_ALIASES = {
    # Premier League
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "manchester united": "manchester united",
    "man city": "manchester city",
    "manchester city": "manchester city",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "tottenham": "tottenham",
    "arsenal": "arsenal",
    "the gunners": "arsenal",
    "chelsea": "chelsea",
    "the blues": "chelsea",
    "liverpool": "liverpool",
    "the reds": "liverpool",
    "everton": "everton",
    "the toffees": "everton",
    "newcastle": "newcastle united",
    "newcastle united": "newcastle united",
    "the magpies": "newcastle united",
    "aston villa": "aston villa",
    "villa": "aston villa",
    "the villans": "aston villa",
    "west ham": "west ham united",
    "west ham united": "west ham united",
    "the hammers": "west ham united",
    "brighton": "brighton & hove albion",
    "brighton and hove albion": "brighton & hove albion",
    "the seagulls": "brighton & hove albion",
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",
    "crystal palace": "crystal palace",
    "palace": "crystal palace",
    "the eagles": "crystal palace",
    "brentford": "brentford",
    "the bees": "brentford",
    "fulham": "fulham",
    "the cottagers": "fulham",
    "southampton": "southampton",
    "the saints": "southampton",
    "leeds": "leeds united",
    "leeds united": "leeds united",
    "leicester": "leicester city",
    "leicester city": "leicester city",
    "the foxes": "leicester city",
    "nottingham forest": "nottingham forest",
    "forest": "nottingham forest",
    "the tricky trees": "nottingham forest",
    # La Liga
    "real madrid": "real madrid",
    "real": "real madrid",  # Default to Real Madrid if ambiguous
    "los blancos": "real madrid",
    "barcelona": "barcelona",
    "barca": "barcelona",
    "fc barcelona": "barcelona",
    "culés": "barcelona",
    "atletico madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atleti": "atletico madrid",
    "los colchoneros": "atletico madrid",
    "sevilla": "sevilla",
    "betis": "real betis",
    "real betis": "real betis",
    "real betis balompie": "real betis",
    "valencia": "valencia",
    "valencia cf": "valencia",
    "los che": "valencia",
    "real sociedad": "real sociedad",
    "la real": "real sociedad",
    "athletic bilbao": "athletic bilbao",
    "athletic club": "athletic bilbao",
    "los leones": "athletic bilbao",
    "villarreal": "villarreal",
    "the yellow submarine": "villarreal",
    # Serie A
    "juventus": "juventus",
    "juve": "juventus",
    "the old lady": "juventus",
    "bianconeri": "juventus",
    "ac milan": "ac milan",
    "milan": "ac milan",
    "rossoneri": "ac milan",
    "the devil": "ac milan",
    "inter": "inter milan",
    "inter milan": "inter milan",
    "nerazzurri": "inter milan",
    "napoli": "napoli",
    "the partenopei": "napoli",
    "roma": "as roma",
    "as roma": "as roma",
    "i giallorossi": "as roma",
    "lazio": "lazio",
    "ss lazio": "lazio",
    "i biancocelesti": "lazio",
    "atalanta": "atalanta",
    "la dea": "atalanta",
    "fiorentina": "fiorentina",
    "viola": "fiorentina",
    "i gigliati": "fiorentina",
    # Bundesliga
    "bayern munich": "bayern munich",
    "bayern": "bayern munich",
    "fc bayern": "bayern munich",
    "die roten": "bayern munich",
    "borussia dortmund": "borussia dortmund",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "die schwarzgelben": "borussia dortmund",
    "rb leipzig": "rb leipzig",
    "leipzig": "rb leipzig",
    "die rotbullen": "rb leipzig",
    "bayer leverkusen": "bayer leverkusen",
    "leverkusen": "bayer leverkusen",
    "die werkself": "bayer leverkusen",
    "borussia mönchengladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "die fohlen": "borussia monchengladbach",
    # Ligue 1
    "psg": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "paris": "paris saint germain",
    "les parisiens": "paris saint germain",
    "monaco": "as monaco",
    "as monaco": "as monaco",
    "les rouge et blanc": "as monaco",
    "marseille": "olympique marseille",
    "olympique marseille": "olympique marseille",
    "les phocéens": "olympique marseille",
    "lyon": "olympique lyon",
    "olympique lyon": "olympique lyon",
    "les gones": "olympique lyon",
    "lille": "lille",
    "losc": "lille",
    "les dogues": "lille",
    "nice": "nice",
    "les aiglons": "nice",
    "rennes": "rennes",
    "stade rennais": "rennes",
    "les rouges et noirs": "rennes",
    # Common abbreviations
    "fc": "fc",  # Will be handled in context
    "united": "united",  # Will be handled in context
    "city": "city",  # Will be handled in context
}


def _normalize_team_name(team_name: str) -> str:
    """
    Normalize team name using alias mapping.

    Args:
        team_name: Original team name

    Returns:
        Normalized team name (lowercase, with aliases expanded)
    """
    if not team_name:
        return ""

    normalized = team_name.lower().strip()

    # Check for exact alias match
    if normalized in TEAM_ALIASES:
        return TEAM_ALIASES[normalized]

    # Check if the normalized name contains an alias
    for alias, full_name in TEAM_ALIASES.items():
        if alias in normalized:
            # Replace the alias with the full name
            normalized = normalized.replace(alias, full_name)
            break

    return normalized


def _calculate_match_confidence(team_name: str, db_team_name: str) -> tuple[float, str]:
    """
    Calculate confidence score for team name match.

    Uses multiple matching strategies with different confidence levels:
    - Exact match: 100% confidence
    - Team name is substring of DB name: 90% confidence
    - DB name is substring of team name: 70% confidence
    - Token-based matching: 60% confidence
    - Partial overlap: 40% confidence

    Args:
        team_name: Normalized team name from alert
        db_team_name: Normalized team name from database

    Returns:
        Tuple of (confidence_score, match_reason)
    """
    if not team_name or not db_team_name:
        return 0.0, "Empty name"

    # Exact match
    if team_name == db_team_name:
        return 1.0, "Exact match"

    # Team name is substring of DB name (e.g., "manchester" matches "manchester united")
    if team_name in db_team_name:
        # Higher confidence if team_name is a significant portion
        ratio = len(team_name) / len(db_team_name)
        confidence = 0.8 + (ratio * 0.1)  # 0.8-0.9 range
        return confidence, f"Team is substring of DB name ({ratio:.0%} coverage)"

    # DB name is substring of team name (e.g., "manchester united" matches "manchester united fc")
    if db_team_name in team_name:
        # Higher confidence if db_team_name is a significant portion
        ratio = len(db_team_name) / len(team_name)
        confidence = 0.6 + (ratio * 0.1)  # 0.6-0.7 range
        return confidence, f"DB name is substring of team name ({ratio:.0%} coverage)"

    # Token-based matching (check individual words)
    team_tokens = set(team_name.split())
    db_tokens = set(db_team_name.split())

    # Calculate token overlap
    common_tokens = team_tokens & db_tokens
    if common_tokens:
        # Use Jaccard similarity
        union_tokens = team_tokens | db_tokens
        similarity = len(common_tokens) / len(union_tokens)

        # Higher confidence if significant overlap
        if similarity >= 0.6:
            confidence = 0.5 + (similarity * 0.1)  # 0.5-0.6 range
            return confidence, f"Token-based match (Jaccard: {similarity:.0%})"
        elif similarity >= 0.3:
            confidence = 0.4 + (similarity * 0.1)  # 0.4-0.5 range
            return confidence, f"Partial token overlap (Jaccard: {similarity:.0%})"

    # Check for any character overlap (lowest confidence)
    common_chars = set(team_name) & set(db_team_name)
    if common_chars:
        overlap_ratio = len(common_chars) / min(len(set(team_name)), len(set(db_team_name)))
        if overlap_ratio >= 0.5:
            confidence = 0.3 + (overlap_ratio * 0.1)  # 0.3-0.4 range
            return confidence, f"Partial character overlap ({overlap_ratio:.0%})"

    return 0.0, "No match"


# Configuration
SIGNIFICANT_MOVE_THRESHOLD = 0.05  # 5% movement = significant
MAJOR_MOVE_THRESHOLD = 0.10  # 10% movement = major (market knows)


class OddsMovementStatus(Enum):
    """Status of odds movement for a team."""

    STABLE = "STABLE"  # No significant movement - EDGE LIKELY
    MINOR_MOVE = "MINOR_MOVE"  # Small movement - edge possible
    SIGNIFICANT_MOVE = "SIGNIFICANT_MOVE"  # Market reacting - edge uncertain
    MAJOR_MOVE = "MAJOR_MOVE"  # Market already knows - low edge
    UNKNOWN = "UNKNOWN"  # No data available


@dataclass
class OddsCheckResult:
    """
    Result of odds movement check.

    Attributes:
        status: Movement status enum
        movement_percent: Percentage change (negative = odds dropped)
        opening_odds: Opening odds for the team
        current_odds: Current odds for the team
        hours_since_open: Hours since opening odds were set
        edge_assessment: Human-readable edge assessment
        should_boost_priority: True if stable odds suggest real edge
        should_reduce_priority: True if major move suggests no edge
    """

    status: OddsMovementStatus
    movement_percent: float
    opening_odds: float | None
    current_odds: float | None
    hours_since_open: float | None
    edge_assessment: str
    should_boost_priority: bool
    should_reduce_priority: bool

    def to_alert_suffix(self) -> str:
        """
        Generate suffix for alert message based on odds status.

        Returns:
            String to append to alert (e.g., "💎 EDGE INTATTO" or "⚠️ Quote già mosse")
        """
        if self.status == OddsMovementStatus.STABLE:
            return "💎 EDGE INTATTO (quote stabili)"
        elif self.status == OddsMovementStatus.MINOR_MOVE:
            return f"📊 Quote in movimento ({self.movement_percent:+.1%})"
        elif self.status == OddsMovementStatus.SIGNIFICANT_MOVE:
            return f"⚠️ Quote già mosse ({self.movement_percent:+.1%})"
        elif self.status == OddsMovementStatus.MAJOR_MOVE:
            return f"🔴 Mercato già informato ({self.movement_percent:+.1%})"
        else:
            return ""

    def to_dict(self) -> dict[str, float]:
        """
        Convert to simple dict with movement percentage.

        Returns:
            Dict with movement percentage (for compatibility with legacy code)
        """
        return {"movement_percent": self.movement_percent}


@dataclass
class MatchOddsMovement:
    """
    Comprehensive odds movement analysis for all match outcomes.

    This provides intelligent analysis of odds movement for home, away, and draw,
    allowing components like Analyzer to understand market dynamics comprehensively.

    Attributes:
        home: OddsCheckResult for home team
        away: OddsCheckResult for away team
        draw: OddsCheckResult for draw (may be None if draw odds not available)
        most_significant_move: Which outcome has the largest movement
        market_assessment: Overall market intelligence summary
    """

    home: OddsCheckResult
    away: OddsCheckResult
    draw: OddsCheckResult | None
    most_significant_move: str  # "home", "away", "draw", or "none"
    market_assessment: str

    def to_dict(self) -> dict[str, float]:
        """
        Convert to simple dict with movement percentages.

        Returns:
            Dict with movement percentages for home/away/draw (for backward compatibility)
        """
        result = {
            "home": self.home.movement_percent,
            "away": self.away.movement_percent,
        }
        if self.draw:
            result["draw"] = self.draw.movement_percent
        return result

    def to_market_status_string(self) -> str:
        """
        Generate a human-readable market status string.

        Returns:
            String describing market movement (e.g., "Home odds moved -5.2% | Away odds moved +4.8%")
        """
        parts = []
        if self.home.status != OddsMovementStatus.UNKNOWN:
            parts.append(f"Home odds moved {self.home.movement_percent:+.1f}%")
        if self.away.status != OddsMovementStatus.UNKNOWN:
            parts.append(f"Away odds moved {self.away.movement_percent:+.1f}%")
        if self.draw and self.draw.status != OddsMovementStatus.UNKNOWN:
            parts.append(f"Draw odds moved {self.draw.movement_percent:+.1f}%")

        if parts:
            return " | ".join(parts)
        elif self.market_assessment:
            return self.market_assessment
        else:
            return "No market movement detected"


class RadarOddsChecker:
    """
    Checks odds movement for radar alerts.

    Uses database data when available, minimizing API calls.
    """

    def __init__(self):
        """Initialize checker."""
        self._db_available = False
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check if database is available."""
        try:
            from src.database.models import Match, SessionLocal

            self._db_available = True
        except ImportError:
            logger.warning("⚠️ [RADAR-ODDS] Database not available")

    def check_odds_movement(
        self, team_name: str, is_home_team: bool = True, match_id: str | None = None
    ) -> OddsCheckResult:
        """
        Check if odds have moved for a team.

        Args:
            team_name: Name of the team to check
            is_home_team: True if checking home team odds
            match_id: Optional match ID for direct lookup

        Returns:
            OddsCheckResult with movement analysis
        """
        # Default result for when we can't check
        default_result = OddsCheckResult(
            status=OddsMovementStatus.UNKNOWN,
            movement_percent=0.0,
            opening_odds=None,
            current_odds=None,
            hours_since_open=None,
            edge_assessment="Dati quote non disponibili",
            should_boost_priority=False,
            should_reduce_priority=False,
        )

        if not self._db_available:
            return default_result

        if not team_name:
            return default_result

        try:
            from src.database.models import SessionLocal

            db = SessionLocal()
            try:
                match = self._find_match(db, team_name, match_id)

                if not match:
                    logger.debug(f"[RADAR-ODDS] No match found for {team_name}")
                    return default_result

                # Determine which odds to check based on team position
                # VPS FIX: Extract Match attributes safely to prevent session detachment
                # This prevents "Trust validation error" when Match object becomes detached
                # from session due to connection pool recycling under high load
                home_team = getattr(match, "home_team", None)
                away_team = getattr(match, "away_team", None)
                opening_home_odd = getattr(match, "opening_home_odd", None)
                current_home_odd = getattr(match, "current_home_odd", None)
                opening_away_odd = getattr(match, "opening_away_odd", None)
                current_away_odd = getattr(match, "current_away_odd", None)

                if is_home_team or (home_team and team_name.lower() in home_team.lower()):
                    opening = opening_home_odd
                    current = current_home_odd
                else:
                    opening = opening_away_odd
                    current = current_away_odd

                return self._analyze_movement(opening, current, match)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ [RADAR-ODDS] Error checking odds: {e}")
            return default_result

    def _find_match(self, db, team_name: str, match_id: str | None = None):
        """
        Find match in database with intelligent confidence-based matching.

        Uses a multi-strategy matching approach:
        1. Direct lookup if match_id provided
        2. SQL LIKE filtering for initial candidate set
        3. Confidence scoring for each candidate
        4. Selection of best match based on confidence and timing

        This prevents false positives when multiple teams have similar names
        (e.g., "Real" matching both "Real Madrid" and "Real Betis").
        """
        from src.database.models import Match

        # Direct lookup if match_id provided
        if match_id:
            return db.query(Match).filter(Match.id == match_id).first()

        # Normalize team name using alias mapping
        normalized_team = _normalize_team_name(team_name)

        # Search by team name in upcoming matches
        # VPS PERFORMANCE FIX: Use SQL filtering to reduce memory usage
        # Instead of loading all matches and filtering in Python, we use SQL LIKE
        # for the most common case (team name is substring of database team name)
        # This dramatically reduces memory usage on VPS with limited resources
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        end_window = now + timedelta(hours=72)

        # Use SQL LIKE for efficient filtering (case-insensitive)
        # This handles cases where "Manchester" matches "Manchester United"
        # We search with both original and normalized team name
        matches = (
            db.query(Match)
            .filter(
                Match.start_time >= now,
                Match.start_time <= end_window,
                (Match.home_team.ilike(f"%{team_name}%"))
                | (Match.away_team.ilike(f"%{team_name}%"))
                | (Match.home_team.ilike(f"%{normalized_team}%"))
                | (Match.away_team.ilike(f"%{normalized_team}%")),
            )
            .all()
        )

        # If no matches found, return None
        if not matches:
            logger.debug(
                f"[RADAR-ODDS] No matches found for {team_name} (normalized: {normalized_team})"
            )
            return None

        # If only one match found, return it
        if len(matches) == 1:
            return matches[0]

        # Multiple matches found - use intelligent selection
        # Calculate confidence score for each match and select the best one
        best_match = None
        best_confidence = 0.0
        best_reason = ""

        for match in matches:
            # VPS FIX: Extract Match attributes safely to prevent session detachment
            # This prevents "Trust validation error" when Match object becomes detached
            # from session due to connection pool recycling under high load
            home_team = getattr(match, "home_team", None)
            away_team = getattr(match, "away_team", None)

            # Normalize database team names
            home_normalized = _normalize_team_name(home_team or "")
            away_normalized = _normalize_team_name(away_team or "")

            # Calculate confidence for both home and away teams
            home_confidence, home_reason = _calculate_match_confidence(
                normalized_team, home_normalized
            )
            away_confidence, away_reason = _calculate_match_confidence(
                normalized_team, away_normalized
            )

            # Use the higher confidence
            match_confidence = max(home_confidence, away_confidence)
            match_reason = home_reason if home_confidence > away_confidence else away_reason

            # Calculate time-based bonus (closer matches get slight boost)
            time_bonus = 0.0
            if match.start_time:
                hours_until_match = (match.start_time - now).total_seconds() / 3600
                # Slight bonus for matches sooner (0-5% boost, max for matches within 24h)
                if hours_until_match <= 24:
                    time_bonus = 0.05 * (1 - hours_until_match / 24)

            total_score = match_confidence + time_bonus

            # Log for debugging
            if match_confidence > 0.3:
                logger.debug(
                    f"[RADAR-ODDS] Match candidate: {home_team} vs {away_team} - "
                    f"Confidence: {match_confidence:.2%} ({match_reason}) - "
                    f"Time bonus: {time_bonus:.2%} - Total: {total_score:.2%}"
                )

            # Update best match if this one has higher confidence
            if total_score > best_confidence:
                best_confidence = total_score
                best_match = match
                best_reason = match_reason

        # Only return if we have reasonable confidence
        if best_match and best_confidence >= 0.4:
            logger.info(
                f"[RADAR-ODDS] Selected best match for {team_name}: "
                f"{getattr(best_match, 'home_team', 'Unknown')} vs "
                f"{getattr(best_match, 'away_team', 'Unknown')} - "
                f"Confidence: {best_confidence:.2%} ({best_reason})"
            )
            return best_match
        elif best_match:
            logger.warning(
                f"[RADAR-ODDS] Low confidence match for {team_name}: "
                f"{getattr(best_match, 'home_team', 'Unknown')} vs "
                f"{getattr(best_match, 'away_team', 'Unknown')} - "
                f"Confidence: {best_confidence:.2%} - Skipping to avoid false positive"
            )

        return None

    def _analyze_movement(
        self, opening: float | None, current: float | None, match
    ) -> OddsCheckResult:
        """Analyze odds movement and return result."""

        # Can't analyze without both values
        if opening is None or current is None:
            return OddsCheckResult(
                status=OddsMovementStatus.UNKNOWN,
                movement_percent=0.0,
                opening_odds=opening,
                current_odds=current,
                hours_since_open=None,
                edge_assessment="Quote incomplete",
                should_boost_priority=False,
                should_reduce_priority=False,
            )

        # Avoid division by zero and handle negative/invalid odds
        # Decimal odds should always be positive (typically 1.01+)
        # Zero or negative values indicate data corruption or invalid data
        if opening <= 0:
            return OddsCheckResult(
                status=OddsMovementStatus.UNKNOWN,
                movement_percent=0.0,
                opening_odds=opening,
                current_odds=current,
                hours_since_open=None,
                edge_assessment="Quote opening invalide (valore non positivo)",
                should_boost_priority=False,
                should_reduce_priority=False,
            )

        # Calculate movement percentage
        # Negative = odds dropped (team more likely to win = money coming in)
        movement = (current - opening) / opening

        # Calculate hours since match was added
        hours_since_open = None
        if match.last_updated:
            # Approximate - use last_updated as proxy
            now = datetime.now(timezone.utc)
            last_updated = match.last_updated
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            hours_since_open = (now - last_updated).total_seconds() / 3600

        # Determine status based on movement
        abs_movement = abs(movement)

        if abs_movement < 0.02:  # < 2%
            status = OddsMovementStatus.STABLE
            edge_assessment = "Quote stabili - edge probabile"
            should_boost = True
            should_reduce = False
        elif abs_movement < SIGNIFICANT_MOVE_THRESHOLD:  # 2-5%
            status = OddsMovementStatus.MINOR_MOVE
            edge_assessment = "Movimento minore - edge possibile"
            should_boost = False
            should_reduce = False
        elif abs_movement < MAJOR_MOVE_THRESHOLD:  # 5-10%
            status = OddsMovementStatus.SIGNIFICANT_MOVE
            edge_assessment = "Movimento significativo - edge incerto"
            should_boost = False
            should_reduce = False
        else:  # > 10%
            status = OddsMovementStatus.MAJOR_MOVE
            edge_assessment = "Movimento maggiore - mercato già informato"
            should_boost = False
            should_reduce = True

        return OddsCheckResult(
            status=status,
            movement_percent=movement,
            opening_odds=opening,
            current_odds=current,
            hours_since_open=hours_since_open,
            edge_assessment=edge_assessment,
            should_boost_priority=should_boost,
            should_reduce_priority=should_reduce,
        )

    def check_for_alert(
        self, team_name: str, match_id: str | None = None
    ) -> tuple[OddsCheckResult, str]:
        """
        Convenience method for radar alerts.

        Returns:
            Tuple of (OddsCheckResult, alert_suffix_string)
        """
        result = self.check_odds_movement(team_name, match_id=match_id)
        suffix = result.to_alert_suffix()
        return result, suffix

    def check_match_movement(
        self, match_id: str | None = None, team_name: str | None = None
    ) -> MatchOddsMovement:
        """
        Check odds movement for all match outcomes (home, away, draw).

        This provides comprehensive market intelligence for components like Analyzer
        that need to understand the full market dynamics, not just a single team.

        Args:
            match_id: Direct match ID for lookup (preferred)
            team_name: Team name to find match (fallback if match_id not provided)

        Returns:
            MatchOddsMovement with analysis for all outcomes
        """
        from src.database.models import SessionLocal

        # Default result when we can't check
        default_result = OddsCheckResult(
            status=OddsMovementStatus.UNKNOWN,
            movement_percent=0.0,
            opening_odds=None,
            current_odds=None,
            hours_since_open=None,
            edge_assessment="Dati quote non disponibili",
            should_boost_priority=False,
            should_reduce_priority=False,
        )

        if not self._db_available:
            return MatchOddsMovement(
                home=default_result,
                away=default_result,
                draw=None,
                most_significant_move="none",
                market_assessment="Database non disponibile",
            )

        try:
            db = SessionLocal()
            try:
                match = self._find_match(db, team_name or "", match_id)

                if not match:
                    return MatchOddsMovement(
                        home=default_result,
                        away=default_result,
                        draw=None,
                        most_significant_move="none",
                        market_assessment="Match non trovato",
                    )

                # Analyze all three outcomes
                home_result = self._analyze_movement(
                    getattr(match, "opening_home_odd", None),
                    getattr(match, "current_home_odd", None),
                    match,
                )

                away_result = self._analyze_movement(
                    getattr(match, "opening_away_odd", None),
                    getattr(match, "current_away_odd", None),
                    match,
                )

                draw_result = None
                opening_draw = getattr(match, "opening_draw_odd", None)
                current_draw = getattr(match, "current_draw_odd", None)
                if opening_draw is not None and current_draw is not None:
                    draw_result = self._analyze_movement(opening_draw, current_draw, match)

                # Determine most significant movement
                movements = [
                    ("home", abs(home_result.movement_percent)),
                    ("away", abs(away_result.movement_percent)),
                ]
                if draw_result:
                    movements.append(("draw", abs(draw_result.movement_percent)))

                most_significant = max(movements, key=lambda x: x[1])[0]

                # Generate market assessment
                if most_significant == "none":
                    market_assessment = "No market movement detected"
                else:
                    result_map = {"home": home_result, "away": away_result, "draw": draw_result}
                    significant_result = result_map[most_significant]
                    market_assessment = significant_result.edge_assessment

                return MatchOddsMovement(
                    home=home_result,
                    away=away_result,
                    draw=draw_result,
                    most_significant_move=most_significant,
                    market_assessment=market_assessment,
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ [RADAR-ODDS] Error checking match movement: {e}")
            return MatchOddsMovement(
                home=default_result,
                away=default_result,
                draw=None,
                most_significant_move="none",
                market_assessment=f"Errore: {e}",
            )


# Singleton instance with thread-safe initialization
_odds_checker: RadarOddsChecker | None = None
_odds_checker_lock = threading.Lock()


def get_radar_odds_checker() -> RadarOddsChecker:
    """
    Get singleton instance of RadarOddsChecker with thread-safe initialization.

    Uses double-check locking pattern to prevent race conditions when
    multiple threads try to initialize the checker simultaneously.
    """
    global _odds_checker

    # First check (fast path, no lock)
    if _odds_checker is None:
        # Second check with lock (only executed if first check fails)
        with _odds_checker_lock:
            if _odds_checker is None:
                _odds_checker = RadarOddsChecker()
                logger.info("✅ [RADAR-ODDS] Odds checker initialized")

    return _odds_checker


async def check_odds_for_alert_async(
    team_name: str, match_id: str | None = None
) -> tuple[OddsCheckResult, str]:
    """
    Async wrapper for odds check (for compatibility with news_radar async).

    Args:
        team_name: Team name from alert
        match_id: Optional match ID

    Returns:
        Tuple of (OddsCheckResult, alert_suffix_string)
    """
    import asyncio

    checker = get_radar_odds_checker()

    # Run in thread pool to not block event loop
    # Use get_running_loop() instead of deprecated get_event_loop()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: checker.check_for_alert(team_name, match_id))

    return result
