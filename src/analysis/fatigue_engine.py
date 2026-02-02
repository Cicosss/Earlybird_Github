"""
EarlyBird Fatigue Engine V2.0

Advanced fatigue analysis with:
- Exponential decay model (recent matches weight more)
- Squad depth multiplier (deep squads handle congestion better)
- Late-game goal prediction (fatigued teams concede late)
- 21-day rolling window analysis

Based on sports science research:
- Full neuromuscular recovery requires 72-96 hours
- Performance drops 10-15% with <72h rest
- Mid-low tier teams suffer 20-30% xPts drop in congestion

Author: EarlyBird AI
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

# Recovery thresholds (hours)
CRITICAL_REST_HOURS = 72      # Less than 3 days = HIGH fatigue
OPTIMAL_REST_HOURS = 96       # 4 days = full recovery
EXTENDED_REST_HOURS = 168     # 7+ days = FRESH

# Fatigue window
FATIGUE_WINDOW_DAYS = 21      # Analyze matches in last 21 days

# Squad depth multipliers (lower = better squad depth)
SQUAD_DEPTH_ELITE = 0.5       # Man City, Real Madrid, Bayern
SQUAD_DEPTH_TOP = 0.7         # Top 6 clubs in major leagues
SQUAD_DEPTH_MID = 1.0         # Average squad (default)
SQUAD_DEPTH_LOW = 1.3         # Promoted teams, small clubs

# Elite clubs with deep squads (can handle fixture congestion)
ELITE_SQUAD_TEAMS = {
    # Premier League
    "Manchester City", "Man City", "Arsenal", "Liverpool", "Chelsea",
    # La Liga
    "Real Madrid", "Barcelona", "Atletico Madrid",
    # Bundesliga
    "Bayern Munich", "Bayern München", "Borussia Dortmund", "Dortmund",
    # Serie A
    "Inter", "Internazionale", "Juventus", "AC Milan", "Milan", "Napoli",
    # Ligue 1
    "Paris Saint-Germain", "PSG",
    # Other
    "Manchester United", "Man Utd", "Tottenham", "Spurs",
}

# Top tier clubs (good squad depth)
TOP_TIER_TEAMS = {
    # Premier League
    "Newcastle", "Newcastle United", "Aston Villa", "Brighton", "West Ham",
    # La Liga
    "Real Sociedad", "Villarreal", "Athletic Bilbao", "Real Betis",
    # Bundesliga
    "RB Leipzig", "Leipzig", "Bayer Leverkusen", "Leverkusen",
    # Serie A
    "Roma", "AS Roma", "Lazio", "Atalanta", "Fiorentina",
    # Ligue 1
    "Monaco", "AS Monaco", "Lyon", "Olympique Lyonnais", "Marseille",
}

# V4.3: Low tier clubs (shallow squads - suffer more from fatigue)
# Promoted teams, small clubs, teams known for thin squads
LOW_TIER_TEAMS = {
    # Premier League (promoted/struggling)
    "Luton", "Luton Town", "Burnley", "Sheffield United", "Sheffield Utd",
    "Ipswich", "Ipswich Town", "Leicester", "Leicester City",
    "Southampton", "Nottingham Forest", "Nott'm Forest",
    # Serie A
    "Lecce", "Empoli", "Frosinone", "Salernitana", "Verona", "Hellas Verona",
    "Cagliari", "Genoa", "Monza",
    # La Liga
    "Almeria", "Granada", "Cadiz", "Getafe", "Alaves", "Deportivo Alaves",
    "Las Palmas", "Mallorca", "Celta Vigo", "Celta",
    # Bundesliga
    "Heidenheim", "Darmstadt", "Darmstadt 98", "Bochum", "VfL Bochum",
    "Mainz", "Mainz 05", "Augsburg", "FC Augsburg",
    # Ligue 1
    "Clermont", "Clermont Foot", "Metz", "Lorient", "Le Havre",
    "Toulouse", "Nantes", "Strasbourg",
    # Turkey (promoted/small)
    "Istanbulspor", "Pendikspor", "Hatayspor", "Konyaspor",
    "Kayserispor", "Sivasspor", "Ankaragucu", "Rizespor",
    # Argentina (small clubs)
    "Platense", "Barracas Central", "Sarmiento", "Central Cordoba",
    "Belgrano", "Instituto", "Banfield", "Arsenal Sarandi",
    # Greece (small clubs)
    "Lamia", "Volos", "Asteras Tripolis", "Atromitos", "Levadiakos",
    # Poland (small clubs)
    "Warta Poznan", "Korona Kielce", "Puszcza Niepolomice", "Ruch Chorzow",
    # Australia (smaller clubs)
    "Central Coast Mariners", "Newcastle Jets", "Wellington Phoenix",
}


@dataclass
class FatigueAnalysis:
    """Result of fatigue analysis for a team."""
    team_name: str
    fatigue_index: float          # 0.0 (fresh) to 1.0 (exhausted)
    fatigue_level: str            # FRESH, LOW, MEDIUM, HIGH, CRITICAL
    hours_since_last: Optional[float]
    matches_in_window: int        # Matches played in last 21 days
    squad_depth_score: float      # Multiplier applied
    late_game_risk: str           # LOW, MEDIUM, HIGH
    late_game_probability: float  # Probability of conceding after 75'
    reasoning: str


@dataclass
class FatigueDifferential:
    """Comparison of fatigue between two teams."""
    home_fatigue: FatigueAnalysis
    away_fatigue: FatigueAnalysis
    differential: float           # Positive = home more fatigued
    advantage: str                # HOME, AWAY, or NEUTRAL
    late_game_edge: str           # Which team likely to concede late
    betting_signal: Optional[str] # Suggested market if significant


def get_squad_depth_score(team_name: str) -> float:
    """
    Get squad depth multiplier for a team.
    
    Elite teams with deep squads can rotate without losing quality,
    so their fatigue impact is reduced.
    
    V4.3: Added LOW_TIER_TEAMS for promoted/small clubs that suffer more.
    
    Args:
        team_name: Name of the team
        
    Returns:
        Squad depth multiplier (0.5 = elite, 1.0 = average, 1.3 = weak)
    """
    if not team_name:
        return SQUAD_DEPTH_MID
    
    team_lower = team_name.lower().strip()
    
    # Check elite squads (best depth)
    for elite in ELITE_SQUAD_TEAMS:
        if elite.lower() in team_lower or team_lower in elite.lower():
            logger.debug(f"🏆 {team_name}: Elite squad depth (0.5x fatigue)")
            return SQUAD_DEPTH_ELITE
    
    # Check top tier (good depth)
    for top in TOP_TIER_TEAMS:
        if top.lower() in team_lower or team_lower in top.lower():
            logger.debug(f"⭐ {team_name}: Top tier squad depth (0.7x fatigue)")
            return SQUAD_DEPTH_TOP
    
    # V4.3: Check low tier (shallow squads - suffer more)
    for low in LOW_TIER_TEAMS:
        if low.lower() in team_lower or team_lower in low.lower():
            logger.debug(f"⚠️ {team_name}: Low tier squad depth (1.3x fatigue)")
            return SQUAD_DEPTH_LOW
    
    # Default: average squad
    return SQUAD_DEPTH_MID


def calculate_fatigue_index(
    team_schedule: List[datetime],
    match_date: datetime,
    squad_depth_score: float = 1.0
) -> Tuple[float, int]:
    """
    Calculate advanced fatigue index using exponential decay model.
    
    Recent matches contribute more to fatigue than older ones.
    Formula: fatigue += 1.0 / days_ago for each match in window
    
    Args:
        team_schedule: List of datetime objects for recent matches
        match_date: Target match datetime
        squad_depth_score: Multiplier for squad depth (1.0 = average)
        
    Returns:
        Tuple of (normalized_fatigue_index, matches_in_window)
    """
    if not team_schedule:
        return 0.0, 0
    
    # Ensure match_date is timezone-aware
    # V4.6 FIX: Log warning when converting naive datetime to UTC
    # This helps debug timezone-related issues in production
    if match_date.tzinfo is None:
        logger.debug(f"⚠️ match_date is timezone-naive, assuming UTC: {match_date}")
        match_date = match_date.replace(tzinfo=timezone.utc)
    
    # Filter matches in the 21-day window
    window_start = match_date - timedelta(days=FATIGUE_WINDOW_DAYS)
    
    recent_games = []
    naive_datetime_count = 0  # V4.6: Track naive datetimes for debugging
    
    for game_date in team_schedule:
        # Handle timezone
        # V4.6 FIX: Track and log naive datetimes for debugging
        if game_date.tzinfo is None:
            naive_datetime_count += 1
            game_date = game_date.replace(tzinfo=timezone.utc)
        
        # Only include past matches within window
        if window_start <= game_date < match_date:
            recent_games.append(game_date)
    
    # V4.6: Log warning if many naive datetimes found (potential data quality issue)
    if naive_datetime_count > 0:
        logger.debug(
            f"⚠️ Fatigue calculation: {naive_datetime_count}/{len(team_schedule)} "
            f"game dates were timezone-naive (assumed UTC)"
        )
    
    if not recent_games:
        return 0.0, 0
    
    # Calculate fatigue with exponential decay
    fatigue_score = 0.0
    
    for game_date in recent_games:
        days_ago = (match_date - game_date).total_seconds() / 86400  # Convert to days
        
        # Exponential decay: recent matches weight more
        # Weight = 1/days_ago (yesterday = 1.0, 3 days ago = 0.33, 7 days ago = 0.14)
        weight = 1.0 / max(days_ago, 0.5)  # Min 0.5 to avoid division issues
        fatigue_score += weight
    
    # Normalize: 3.0+ is considered critical fatigue
    # This threshold means: 3 matches in quick succession = max fatigue
    normalized_fatigue = min(fatigue_score / 3.0, 1.0)
    
    # Apply squad depth adjustment
    # Elite squads (0.5x) feel half the fatigue impact
    adjusted_fatigue = normalized_fatigue * squad_depth_score
    
    # Cap at 1.0
    final_fatigue = min(adjusted_fatigue, 1.0)
    
    return round(final_fatigue, 3), len(recent_games)


def get_fatigue_level(fatigue_index: float, hours_since_last: Optional[float]) -> str:
    """
    Convert fatigue index to human-readable level.
    
    Combines the exponential decay index with hours since last match
    for a comprehensive assessment.
    """
    # Primary: hours since last match (most important factor)
    if hours_since_last is not None:
        if hours_since_last < CRITICAL_REST_HOURS:
            return "CRITICAL"
        elif hours_since_last < OPTIMAL_REST_HOURS:
            return "HIGH"
    
    # Secondary: fatigue index from match density
    if fatigue_index >= 0.8:
        return "CRITICAL"
    elif fatigue_index >= 0.6:
        return "HIGH"
    elif fatigue_index >= 0.4:
        return "MEDIUM"
    elif fatigue_index >= 0.2:
        return "LOW"
    else:
        return "FRESH"


def calculate_late_game_risk(fatigue_index: float, fatigue_level: str) -> Tuple[str, float]:
    """
    Calculate probability of conceding goals after 75th minute.
    
    Research shows fatigued teams:
    - Defend worse in final 20 minutes
    - Sprint capacity drops significantly
    - Concentration lapses increase
    
    Args:
        fatigue_index: Normalized fatigue (0-1)
        fatigue_level: FRESH/LOW/MEDIUM/HIGH/CRITICAL
        
    Returns:
        Tuple of (risk_level, probability)
    """
    # Base probability of conceding after 75' (league average ~25%)
    base_probability = 0.25
    
    # Fatigue multiplier
    fatigue_multipliers = {
        "FRESH": 0.8,      # 20% less likely
        "LOW": 1.0,        # Average
        "MEDIUM": 1.15,    # 15% more likely
        "HIGH": 1.35,      # 35% more likely
        "CRITICAL": 1.60   # 60% more likely
    }
    
    multiplier = fatigue_multipliers.get(fatigue_level, 1.0)
    
    # Additional boost from fatigue index
    # High density of matches = even more tired in final minutes
    index_boost = 1.0 + (fatigue_index * 0.3)  # Up to 30% extra
    
    final_probability = min(base_probability * multiplier * index_boost, 0.65)
    
    # Determine risk level
    if final_probability >= 0.45:
        risk_level = "HIGH"
    elif final_probability >= 0.35:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    return risk_level, round(final_probability, 2)


def analyze_team_fatigue(
    team_name: str,
    hours_since_last: Optional[float],
    recent_matches: List[datetime] = None,
    target_match_date: datetime = None
) -> FatigueAnalysis:
    """
    Complete fatigue analysis for a single team.
    
    Args:
        team_name: Name of the team
        hours_since_last: Hours since last match (from FotMob)
        recent_matches: List of recent match dates (optional, for advanced analysis)
        target_match_date: Date of the target match
        
    Returns:
        FatigueAnalysis dataclass with all metrics
    """
    # Get squad depth
    squad_depth = get_squad_depth_score(team_name)
    
    # Calculate fatigue index
    if recent_matches and target_match_date:
        fatigue_index, matches_in_window = calculate_fatigue_index(
            recent_matches, 
            target_match_date, 
            squad_depth
        )
    else:
        # Fallback: estimate from hours_since_last only
        if hours_since_last is not None:
            if hours_since_last < 72:
                fatigue_index = 0.8 * squad_depth
            elif hours_since_last < 96:
                fatigue_index = 0.5 * squad_depth
            elif hours_since_last < 168:
                fatigue_index = 0.2 * squad_depth
            else:
                fatigue_index = 0.0
            fatigue_index = min(fatigue_index, 1.0)
        else:
            fatigue_index = 0.0
        matches_in_window = 0
    
    # Get fatigue level
    fatigue_level = get_fatigue_level(fatigue_index, hours_since_last)
    
    # Calculate late-game risk
    late_game_risk, late_game_prob = calculate_late_game_risk(fatigue_index, fatigue_level)
    
    # Build reasoning
    reasoning_parts = []
    
    if hours_since_last is not None:
        if hours_since_last < 72:
            reasoning_parts.append(f"Solo {hours_since_last:.0f}h di riposo (critico)")
        elif hours_since_last < 96:
            reasoning_parts.append(f"{hours_since_last:.0f}h di riposo (sotto ottimale)")
    
    if matches_in_window > 0:
        reasoning_parts.append(f"{matches_in_window} partite negli ultimi 21 giorni")
    
    if squad_depth < 1.0:
        reasoning_parts.append("Rosa profonda (gestisce bene la fatica)")
    elif squad_depth > 1.0:
        reasoning_parts.append("Rosa corta (soffre la congestione)")
    
    if late_game_risk == "HIGH":
        reasoning_parts.append(f"Alto rischio goal subiti dopo 75' ({late_game_prob*100:.0f}%)")
    
    reasoning = " | ".join(reasoning_parts) if reasoning_parts else "Condizione fisica normale"
    
    return FatigueAnalysis(
        team_name=team_name,
        fatigue_index=fatigue_index,
        fatigue_level=fatigue_level,
        hours_since_last=hours_since_last,
        matches_in_window=matches_in_window,
        squad_depth_score=squad_depth,
        late_game_risk=late_game_risk,
        late_game_probability=late_game_prob,
        reasoning=reasoning
    )


def analyze_fatigue_differential(
    home_team: str,
    away_team: str,
    home_hours_since_last: Optional[float],
    away_hours_since_last: Optional[float],
    home_recent_matches: List[datetime] = None,
    away_recent_matches: List[datetime] = None,
    target_match_date: datetime = None
) -> FatigueDifferential:
    """
    Compare fatigue levels between two teams and generate betting signals.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        home_hours_since_last: Hours since home team's last match
        away_hours_since_last: Hours since away team's last match
        home_recent_matches: Home team's recent match dates
        away_recent_matches: Away team's recent match dates
        target_match_date: Date of the target match
        
    Returns:
        FatigueDifferential with comparison and betting signals
    """
    # Analyze both teams
    home_fatigue = analyze_team_fatigue(
        home_team, 
        home_hours_since_last,
        home_recent_matches,
        target_match_date
    )
    
    away_fatigue = analyze_team_fatigue(
        away_team,
        away_hours_since_last,
        away_recent_matches,
        target_match_date
    )
    
    # Calculate differential (positive = home more fatigued)
    differential = home_fatigue.fatigue_index - away_fatigue.fatigue_index
    
    # Determine advantage
    if abs(differential) < 0.15:
        advantage = "NEUTRAL"
    elif differential > 0:
        advantage = "AWAY"  # Away team is fresher
    else:
        advantage = "HOME"  # Home team is fresher
    
    # Determine late-game edge
    if home_fatigue.late_game_probability > away_fatigue.late_game_probability + 0.1:
        late_game_edge = "AWAY"  # Home likely to concede late
    elif away_fatigue.late_game_probability > home_fatigue.late_game_probability + 0.1:
        late_game_edge = "HOME"  # Away likely to concede late
    else:
        late_game_edge = "NEUTRAL"
    
    # Generate betting signal
    betting_signal = None
    
    # Significant fatigue differential
    if abs(differential) >= 0.3:
        fresher_team = away_team if differential > 0 else home_team
        tired_team = home_team if differential > 0 else away_team
        betting_signal = f"⚡ FATIGUE EDGE: {fresher_team} significativamente più fresco di {tired_team}"
    
    # Late-game opportunity
    if late_game_edge != "NEUTRAL":
        tired_team = home_team if late_game_edge == "AWAY" else away_team
        tired_prob = home_fatigue.late_game_probability if late_game_edge == "AWAY" else away_fatigue.late_game_probability
        if tired_prob >= 0.40:
            late_signal = f"⏱️ LATE GOAL: {tired_team} a rischio goal dopo 75' ({tired_prob*100:.0f}%)"
            betting_signal = f"{betting_signal} | {late_signal}" if betting_signal else late_signal
    
    return FatigueDifferential(
        home_fatigue=home_fatigue,
        away_fatigue=away_fatigue,
        differential=round(differential, 3),
        advantage=advantage,
        late_game_edge=late_game_edge,
        betting_signal=betting_signal
    )


def format_fatigue_context(differential: FatigueDifferential) -> str:
    """
    Format fatigue analysis for AI context injection.
    
    Args:
        differential: FatigueDifferential analysis result
        
    Returns:
        Formatted string for AI prompt
    """
    home = differential.home_fatigue
    away = differential.away_fatigue
    
    lines = [
        "⚡ FATIGUE ANALYSIS (V2.0):",
        f"  {home.team_name}: {home.fatigue_level} (Index: {home.fatigue_index:.2f})",
    ]
    
    if home.hours_since_last:
        lines.append(f"    └─ {home.hours_since_last:.0f}h riposo | Late Risk: {home.late_game_risk}")
    
    lines.append(f"  {away.team_name}: {away.fatigue_level} (Index: {away.fatigue_index:.2f})")
    
    if away.hours_since_last:
        lines.append(f"    └─ {away.hours_since_last:.0f}h riposo | Late Risk: {away.late_game_risk}")
    
    if differential.advantage != "NEUTRAL":
        lines.append(f"  📊 Vantaggio: {differential.advantage}")
    
    if differential.betting_signal:
        lines.append(f"  🎯 {differential.betting_signal}")
    
    return "\n".join(lines)


# ============================================
# INTEGRATION HELPER
# ============================================

def get_enhanced_fatigue_context(
    home_team: str,
    away_team: str,
    home_context: Dict,
    away_context: Dict,
    match_start_time: datetime = None
) -> Tuple[FatigueDifferential, str]:
    """
    Integration helper for main.py - extracts fatigue data from FotMob context
    and returns enhanced analysis.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        home_context: FotMob context dict for home team
        away_context: FotMob context dict for away team
        match_start_time: Match start datetime
        
    Returns:
        Tuple of (FatigueDifferential, formatted_context_string)
    """
    # Extract hours since last from FotMob context
    # V5.3: Defense-in-depth - handle case where fatigue is string instead of dict
    home_fatigue_data = home_context.get('fatigue', {})
    if not isinstance(home_fatigue_data, dict):
        home_fatigue_data = {'fatigue_level': str(home_fatigue_data) if home_fatigue_data else 'Unknown', 'hours_since_last': None}
    
    away_fatigue_data = away_context.get('fatigue', {})
    if not isinstance(away_fatigue_data, dict):
        away_fatigue_data = {'fatigue_level': str(away_fatigue_data) if away_fatigue_data else 'Unknown', 'hours_since_last': None}
    
    home_hours = home_fatigue_data.get('hours_since_last')
    away_hours = away_fatigue_data.get('hours_since_last')
    
    # Use match start time or now
    target_date = match_start_time or datetime.now(timezone.utc)
    
    # Run enhanced analysis
    differential = analyze_fatigue_differential(
        home_team=home_team,
        away_team=away_team,
        home_hours_since_last=home_hours,
        away_hours_since_last=away_hours,
        target_match_date=target_date
    )
    
    # Format for AI context
    context_str = format_fatigue_context(differential)
    
    return differential, context_str
