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
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Configuration
SIGNIFICANT_MOVE_THRESHOLD = 0.05  # 5% movement = significant
MAJOR_MOVE_THRESHOLD = 0.10        # 10% movement = major (market knows)
RECENT_WINDOW_HOURS = 6            # Check movements in last 6 hours


class OddsMovementStatus(Enum):
    """Status of odds movement for a team."""
    STABLE = "STABLE"              # No significant movement - EDGE LIKELY
    MINOR_MOVE = "MINOR_MOVE"      # Small movement - edge possible
    SIGNIFICANT_MOVE = "SIGNIFICANT_MOVE"  # Market reacting - edge uncertain
    MAJOR_MOVE = "MAJOR_MOVE"      # Market already knows - low edge
    UNKNOWN = "UNKNOWN"            # No data available


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
    opening_odds: Optional[float]
    current_odds: Optional[float]
    hours_since_open: Optional[float]
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
        self,
        team_name: str,
        is_home_team: bool = True,
        match_id: Optional[str] = None
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
            should_reduce_priority=False
        )
        
        if not self._db_available:
            return default_result
        
        if not team_name:
            return default_result
        
        try:
            from src.database.models import Match, SessionLocal
            
            db = SessionLocal()
            try:
                match = self._find_match(db, team_name, match_id)
                
                if not match:
                    logger.debug(f"[RADAR-ODDS] No match found for {team_name}")
                    return default_result
                
                # Determine which odds to check based on team position
                if is_home_team or (match.home_team and team_name.lower() in match.home_team.lower()):
                    opening = match.opening_home_odd
                    current = match.current_home_odd
                else:
                    opening = match.opening_away_odd
                    current = match.current_away_odd
                
                return self._analyze_movement(opening, current, match)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ [RADAR-ODDS] Error checking odds: {e}")
            return default_result
    
    def _find_match(self, db, team_name: str, match_id: Optional[str] = None):
        """Find match in database."""
        from src.database.models import Match
        
        # Direct lookup if match_id provided
        if match_id:
            return db.query(Match).filter(Match.id == match_id).first()
        
        # Search by team name in upcoming matches
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        end_window = now + timedelta(hours=72)
        
        team_lower = team_name.lower().strip()
        
        matches = db.query(Match).filter(
            Match.start_time >= now,
            Match.start_time <= end_window
        ).all()
        
        for match in matches:
            home_lower = (match.home_team or "").lower()
            away_lower = (match.away_team or "").lower()
            
            if (team_lower in home_lower or home_lower in team_lower or
                team_lower in away_lower or away_lower in team_lower):
                return match
        
        return None
    
    def _analyze_movement(
        self,
        opening: Optional[float],
        current: Optional[float],
        match
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
                should_reduce_priority=False
            )
        
        # Avoid division by zero
        if opening == 0:
            return OddsCheckResult(
                status=OddsMovementStatus.UNKNOWN,
                movement_percent=0.0,
                opening_odds=opening,
                current_odds=current,
                hours_since_open=None,
                edge_assessment="Quote opening invalide",
                should_boost_priority=False,
                should_reduce_priority=False
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
            should_reduce_priority=should_reduce
        )
    
    def check_for_alert(
        self,
        team_name: str,
        match_id: Optional[str] = None
    ) -> Tuple[OddsCheckResult, str]:
        """
        Convenience method for radar alerts.
        
        Returns:
            Tuple of (OddsCheckResult, alert_suffix_string)
        """
        result = self.check_odds_movement(team_name, match_id=match_id)
        suffix = result.to_alert_suffix()
        return result, suffix


# Singleton instance
_odds_checker: Optional[RadarOddsChecker] = None


def get_radar_odds_checker() -> RadarOddsChecker:
    """Get singleton instance of RadarOddsChecker."""
    global _odds_checker
    
    if _odds_checker is None:
        _odds_checker = RadarOddsChecker()
        logger.info("✅ [RADAR-ODDS] Odds checker initialized")
    
    return _odds_checker


async def check_odds_for_alert_async(
    team_name: str,
    match_id: Optional[str] = None
) -> Tuple[OddsCheckResult, str]:
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
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: checker.check_for_alert(team_name, match_id)
    )
    
    return result
