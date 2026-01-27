"""
EarlyBird Biscotto Engine V2.0

Advanced match-fixing / tacit collusion detection with:
- End-of-Season Effect detection (classifica analysis)
- Z-Score analysis vs league average draw probability
- Draw odds drift pattern recognition
- Multi-factor severity scoring

A "Biscotto" is a mutually beneficial draw where both teams need just 1 point.
This is NOT necessarily illegal match-fixing, but a statistical anomaly worth betting on.

Detection Methods:
1. Draw Odds Analysis: Absolute level + drop percentage
2. End-of-Season Context: Both teams' classifica situation
3. Statistical Anomaly: Z-Score vs league baseline
4. Drift Pattern: Slow vs sudden odds movement

Author: EarlyBird AI
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

# Draw odds thresholds
DRAW_EXTREME_LOW = 2.00       # Below this = EXTREME suspicion
DRAW_SUSPICIOUS_LOW = 2.50    # Below this = HIGH suspicion
DRAW_WATCH_LOW = 3.00         # Below this = worth monitoring

# V4.3: Minor League Biscotto Detection (Deep Research Enhancement)
# Serie B, Turkey 2, and other minor leagues have higher biscotto frequency
# in end-of-season matches. Use stricter threshold for these leagues.
MINOR_LEAGUE_DRAW_THRESHOLD = 2.60  # Stricter threshold for minor leagues

# Minor leagues with historically higher biscotto frequency
MINOR_LEAGUES_BISCOTTO_RISK = {
    "soccer_italy_serie_b",
    "soccer_spain_segunda_division",
    "soccer_germany_bundesliga2",
    "soccer_france_ligue_two",
    "soccer_england_championship",
    "soccer_turkey_1_lig",
    "soccer_brazil_serie_b",
    "soccer_argentina_primera_b",
    "soccer_portugal_segunda_liga",
    "soccer_netherlands_eerste_divisie",
}

# Drop percentage thresholds
DROP_EXTREME = 25.0           # 25%+ drop = EXTREME
DROP_HIGH = 15.0              # 15%+ drop = HIGH
DROP_MEDIUM = 10.0            # 10%+ drop = MEDIUM

# League average draw probability (baseline)
LEAGUE_AVG_DRAW_PROB = 0.28   # ~28% of matches end in draw

# Z-Score thresholds for anomaly detection
ZSCORE_EXTREME = 2.5          # >2.5 standard deviations
ZSCORE_HIGH = 2.0             # >2.0 standard deviations
ZSCORE_MEDIUM = 1.5           # >1.5 standard deviations

# End-of-season detection
END_OF_SEASON_ROUNDS = 5      # Last 5 rounds of season
POINTS_BUFFER_SAFE = 3        # Teams within 3 points of safety


class BiscottoSeverity(Enum):
    """Severity levels for biscotto detection."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class BiscottoPattern(Enum):
    """Pattern types for draw odds movement."""
    STABLE = "STABLE"           # No significant movement
    DRIFT = "DRIFT"             # Slow, steady decline (tacit collusion)
    CRASH = "CRASH"             # Sudden drop (insider info)
    REVERSE = "REVERSE"         # Dropped then recovered (false alarm)


def is_minor_league_biscotto_risk(league_key: str) -> bool:
    """
    V4.3: Check if league has historically higher biscotto risk.
    
    Minor leagues (Serie B, Segunda Division, etc.) have statistically
    higher draw rates in end-of-season matches between mid-table teams.
    
    Args:
        league_key: League identifier
        
    Returns:
        True if league is in high-risk category
    """
    if not league_key:
        return False
    return league_key in MINOR_LEAGUES_BISCOTTO_RISK


def get_draw_threshold_for_league(league_key: str, end_of_season: bool = False) -> float:
    """
    V4.3: Get dynamic draw odds threshold based on league and season context.
    
    Minor leagues in end-of-season get stricter threshold (2.60 vs 2.50).
    This catches more potential biscotto situations in high-risk contexts.
    
    Args:
        league_key: League identifier
        end_of_season: Whether match is in last 5 rounds
        
    Returns:
        Draw odds threshold for HIGH suspicion
    """
    if is_minor_league_biscotto_risk(league_key) and end_of_season:
        return MINOR_LEAGUE_DRAW_THRESHOLD  # 2.60 - stricter
    return DRAW_SUSPICIOUS_LOW  # 2.50 - standard


@dataclass
class ClassificaContext:
    """Team's league table context for end-of-season analysis."""
    team_name: str
    position: int
    total_teams: int
    points: int
    zone: str                   # "Safe", "Danger", "Relegation", "Promotion", "Title"
    points_to_safety: Optional[int]
    points_to_next_zone: Optional[int]
    matches_remaining: Optional[int]
    needs_point: bool           # True if 1 point would secure objective


@dataclass
class BiscottoAnalysis:
    """Complete biscotto analysis result."""
    is_suspect: bool
    severity: BiscottoSeverity
    confidence: int             # 0-100
    
    # Odds analysis
    current_draw_odd: Optional[float]
    opening_draw_odd: Optional[float]
    drop_percentage: float
    implied_probability: float
    
    # Statistical analysis
    zscore: float
    pattern: BiscottoPattern
    
    # Context analysis
    home_context: Optional[ClassificaContext]
    away_context: Optional[ClassificaContext]
    end_of_season_match: bool
    mutual_benefit: bool        # Both teams benefit from draw
    
    # Output
    reasoning: str
    betting_recommendation: str  # "BET X", "MONITOR", "AVOID"
    factors: List[str]          # List of detected factors


def calculate_implied_probability(odds: float) -> float:
    """
    Calculate implied probability from decimal odds.
    
    Args:
        odds: Decimal odds (e.g., 2.50)
        
    Returns:
        Implied probability (0-1)
    """
    if odds is None or odds <= 1.0:
        return 0.0
    return 1.0 / odds


def calculate_zscore(implied_prob: float, league_avg: float = LEAGUE_AVG_DRAW_PROB) -> float:
    """
    Calculate Z-Score of draw probability vs league average.
    
    A high Z-Score indicates the draw is priced significantly
    higher than the league average, suggesting market knows something.
    
    Args:
        implied_prob: Implied probability from current odds
        league_avg: League average draw probability (default 28%)
        
    Returns:
        Z-Score (standard deviations from mean)
    """
    if implied_prob <= 0:
        return 0.0
    
    # Standard deviation of draw probability (empirical ~0.08)
    std_dev = 0.08
    
    # Z-Score = (observed - expected) / std_dev
    zscore = (implied_prob - league_avg) / std_dev
    
    return round(zscore, 2)


def detect_odds_pattern(
    opening_odd: Optional[float],
    current_odd: Optional[float]
) -> BiscottoPattern:
    """
    Detect the pattern of draw odds movement.
    
    - DRIFT: Slow, steady decline (typical biscotto pattern)
    - CRASH: Sudden drop (possible insider info)
    - REVERSE: Dropped then recovered (false alarm)
    - STABLE: No significant movement
    
    Args:
        opening_odd: Opening draw odds
        current_odd: Current draw odds
        
    Returns:
        BiscottoPattern enum
    """
    if opening_odd is None or current_odd is None:
        return BiscottoPattern.STABLE
    
    # Edge case: invalid odds values
    if opening_odd <= 0 or current_odd <= 0:
        return BiscottoPattern.STABLE
    
    drop_pct = ((opening_odd - current_odd) / opening_odd) * 100
    
    # No significant movement
    if abs(drop_pct) < 5:
        return BiscottoPattern.STABLE
    
    # Odds went UP (reverse)
    if drop_pct < -5:
        return BiscottoPattern.REVERSE
    
    # Significant drop
    if drop_pct >= 20:
        return BiscottoPattern.CRASH
    elif drop_pct >= 8:
        return BiscottoPattern.DRIFT
    
    return BiscottoPattern.STABLE


def analyze_classifica_context(
    team_name: str,
    position: int,
    total_teams: int,
    points: int,
    zone: str,
    matches_remaining: int = None
) -> ClassificaContext:
    """
    Analyze a team's league table context for end-of-season scenarios.
    
    Args:
        team_name: Name of the team
        position: Current league position
        total_teams: Total teams in league
        points: Current points
        zone: Zone from FotMob (Title Race, Relegation, etc.)
        matches_remaining: Matches left in season (optional)
        
    Returns:
        ClassificaContext with analysis
    """
    # Determine if team needs just 1 point
    needs_point = False
    points_to_safety = None
    points_to_next_zone = None
    
    # Normalize zone
    zone_lower = zone.lower() if zone else ""
    
    # Relegation zone analysis
    if "relegation" in zone_lower or "danger" in zone_lower:
        # Team fighting relegation - 1 point could be crucial
        if matches_remaining and matches_remaining <= END_OF_SEASON_ROUNDS:
            needs_point = True
    
    # Safe but close to danger
    elif "mid" in zone_lower or "safe" in zone_lower:
        # Check if mathematically safe
        if matches_remaining and matches_remaining <= 3:
            # In final 3 matches, even mid-table teams might settle for draw
            needs_point = True
    
    # Promotion/Title race
    elif "title" in zone_lower or "promotion" in zone_lower or "european" in zone_lower:
        # Teams chasing something usually DON'T want draws
        # Unless they're so far ahead that 1 point clinches it
        needs_point = False
    
    return ClassificaContext(
        team_name=team_name,
        position=position,
        total_teams=total_teams,
        points=points,
        zone=zone,
        points_to_safety=points_to_safety,
        points_to_next_zone=points_to_next_zone,
        matches_remaining=matches_remaining,
        needs_point=needs_point
    )


def check_mutual_benefit(
    home_context: Optional[ClassificaContext],
    away_context: Optional[ClassificaContext]
) -> Tuple[bool, str]:
    """
    Check if both teams would benefit from a draw.
    
    Classic biscotto scenarios:
    - Both teams need 1 point for safety
    - Both teams have nothing to play for (mid-table end of season)
    - One team needs point, other has nothing to lose
    
    Args:
        home_context: Home team's classifica context
        away_context: Away team's classifica context
        
    Returns:
        Tuple of (mutual_benefit, reason)
    """
    if home_context is None or away_context is None:
        return False, "Contesto classifica non disponibile"
    
    # Scenario 1: Both need a point
    if home_context.needs_point and away_context.needs_point:
        return True, "Entrambe le squadre hanno bisogno di 1 punto"
    
    # Scenario 2: Both mid-table with nothing to play for
    home_mid = "mid" in home_context.zone.lower() if home_context.zone else False
    away_mid = "mid" in away_context.zone.lower() if away_context.zone else False
    
    if home_mid and away_mid:
        return True, "Entrambe a metà classifica senza obiettivi"
    
    # Scenario 3: One needs point, other is safe/mid-table
    if home_context.needs_point and (away_mid or "safe" in (away_context.zone or "").lower()):
        return True, f"{home_context.team_name} ha bisogno di punti, {away_context.team_name} senza pressione"
    
    if away_context.needs_point and (home_mid or "safe" in (home_context.zone or "").lower()):
        return True, f"{away_context.team_name} ha bisogno di punti, {home_context.team_name} senza pressione"
    
    return False, "Nessun beneficio reciproco evidente"


def calculate_severity(
    draw_odd: Optional[float],
    drop_pct: float,
    zscore: float,
    pattern: BiscottoPattern,
    mutual_benefit: bool,
    end_of_season: bool,
    suspicious_threshold: float = DRAW_SUSPICIOUS_LOW
) -> Tuple[BiscottoSeverity, int, List[str]]:
    """
    Calculate overall biscotto severity from multiple factors.
    
    V4.3: Now supports dynamic suspicious_threshold for minor leagues.
    
    Args:
        draw_odd: Current draw odds
        drop_pct: Drop percentage from opening
        zscore: Z-Score vs league average
        pattern: Odds movement pattern
        mutual_benefit: Whether both teams benefit
        end_of_season: Whether it's end of season
        suspicious_threshold: Dynamic threshold for HIGH suspicion (V4.3)
        
    Returns:
        Tuple of (severity, confidence, factors_list)
    """
    factors = []
    score = 0  # Accumulate severity score
    
    # Factor 1: Absolute draw odds level (V4.3: uses dynamic threshold)
    if draw_odd is not None:
        if draw_odd < DRAW_EXTREME_LOW:
            factors.append(f"🔴 Quota X estrema: {draw_odd:.2f}")
            score += 40
        elif draw_odd < suspicious_threshold:  # V4.3: Dynamic threshold
            factors.append(f"🟠 Quota X sospetta: {draw_odd:.2f}")
            score += 25
        elif draw_odd < DRAW_WATCH_LOW:
            factors.append(f"🟡 Quota X bassa: {draw_odd:.2f}")
            score += 10
    
    # Factor 2: Drop percentage
    if drop_pct >= DROP_EXTREME:
        factors.append(f"📉 Crollo quote: -{drop_pct:.1f}%")
        score += 30
    elif drop_pct >= DROP_HIGH:
        factors.append(f"📉 Drop significativo: -{drop_pct:.1f}%")
        score += 20
    elif drop_pct >= DROP_MEDIUM:
        factors.append(f"↘️ Drop moderato: -{drop_pct:.1f}%")
        score += 10
    
    # Factor 3: Z-Score (statistical anomaly)
    if zscore >= ZSCORE_EXTREME:
        factors.append(f"📊 Anomalia statistica estrema (Z={zscore:.1f})")
        score += 25
    elif zscore >= ZSCORE_HIGH:
        factors.append(f"📊 Anomalia statistica alta (Z={zscore:.1f})")
        score += 15
    elif zscore >= ZSCORE_MEDIUM:
        factors.append(f"📊 Anomalia statistica (Z={zscore:.1f})")
        score += 8
    
    # Factor 4: Pattern
    if pattern == BiscottoPattern.CRASH:
        factors.append("⚡ Pattern CRASH (movimento improvviso)")
        score += 15
    elif pattern == BiscottoPattern.DRIFT:
        factors.append("📈 Pattern DRIFT (discesa graduale)")
        score += 20  # Drift is more indicative of biscotto
    
    # Factor 5: Mutual benefit
    if mutual_benefit:
        factors.append("🤝 Beneficio reciproco confermato")
        score += 25
    
    # Factor 6: End of season
    if end_of_season:
        factors.append("📅 Fine stagione (ultime giornate)")
        score += 15
    
    # Calculate confidence (capped at 95)
    confidence = min(score, 95)
    
    # Determine severity
    if score >= 70:
        severity = BiscottoSeverity.EXTREME
    elif score >= 50:
        severity = BiscottoSeverity.HIGH
    elif score >= 30:
        severity = BiscottoSeverity.MEDIUM
    elif score >= 15:
        severity = BiscottoSeverity.LOW
    else:
        severity = BiscottoSeverity.NONE
    
    return severity, confidence, factors


def analyze_biscotto(
    home_team: str,
    away_team: str,
    current_draw_odd: Optional[float],
    opening_draw_odd: Optional[float] = None,
    home_motivation: Dict = None,
    away_motivation: Dict = None,
    matches_remaining: int = None,
    league_avg_draw: float = LEAGUE_AVG_DRAW_PROB,
    league_key: str = None
) -> BiscottoAnalysis:
    """
    Complete biscotto analysis for a match.
    
    V4.3: Now supports league_key for dynamic thresholds.
    Minor leagues in end-of-season get stricter detection (2.60 vs 2.50).
    
    Args:
        home_team: Home team name
        away_team: Away team name
        current_draw_odd: Current draw odds
        opening_draw_odd: Opening draw odds (optional)
        home_motivation: FotMob motivation context for home team
        away_motivation: FotMob motivation context for away team
        matches_remaining: Matches left in season (optional)
        league_avg_draw: League average draw probability
        league_key: League identifier for dynamic thresholds (V4.3)
        
    Returns:
        BiscottoAnalysis with complete assessment
    """
    # Check end of season first (needed for dynamic threshold)
    end_of_season = matches_remaining is not None and matches_remaining <= END_OF_SEASON_ROUNDS
    
    # V4.3: Get dynamic threshold based on league and season context
    dynamic_suspicious_threshold = get_draw_threshold_for_league(league_key, end_of_season)
    
    # Handle None/invalid odds
    if current_draw_odd is None or current_draw_odd <= 1.0:
        return BiscottoAnalysis(
            is_suspect=False,
            severity=BiscottoSeverity.NONE,
            confidence=0,
            current_draw_odd=current_draw_odd,
            opening_draw_odd=opening_draw_odd,
            drop_percentage=0.0,
            implied_probability=0.0,
            zscore=0.0,
            pattern=BiscottoPattern.STABLE,
            home_context=None,
            away_context=None,
            end_of_season_match=False,
            mutual_benefit=False,
            reasoning="Quote pareggio non disponibili",
            betting_recommendation="AVOID",
            factors=[]
        )
    
    # Calculate drop percentage
    drop_pct = 0.0
    if opening_draw_odd and opening_draw_odd > 0:
        drop_pct = ((opening_draw_odd - current_draw_odd) / opening_draw_odd) * 100
    
    # Calculate implied probability and Z-Score
    implied_prob = calculate_implied_probability(current_draw_odd)
    zscore = calculate_zscore(implied_prob, league_avg_draw)
    
    # Detect odds pattern
    pattern = detect_odds_pattern(opening_draw_odd, current_draw_odd)
    
    # Analyze classifica context
    home_context = None
    away_context = None
    
    if home_motivation:
        home_context = analyze_classifica_context(
            team_name=home_team,
            position=home_motivation.get('position', 0),
            total_teams=home_motivation.get('total_teams', 20),
            points=home_motivation.get('points', 0),
            zone=home_motivation.get('zone', 'Unknown'),
            matches_remaining=matches_remaining
        )
    
    if away_motivation:
        away_context = analyze_classifica_context(
            team_name=away_team,
            position=away_motivation.get('position', 0),
            total_teams=away_motivation.get('total_teams', 20),
            points=away_motivation.get('points', 0),
            zone=away_motivation.get('zone', 'Unknown'),
            matches_remaining=matches_remaining
        )
    
    # Check mutual benefit
    mutual_benefit, benefit_reason = check_mutual_benefit(home_context, away_context)
    
    # Calculate severity (V4.3: pass dynamic threshold)
    severity, confidence, factors = calculate_severity(
        draw_odd=current_draw_odd,
        drop_pct=drop_pct,
        zscore=zscore,
        pattern=pattern,
        mutual_benefit=mutual_benefit,
        end_of_season=end_of_season,
        suspicious_threshold=dynamic_suspicious_threshold  # V4.3
    )
    
    # Determine if suspect
    is_suspect = severity in [BiscottoSeverity.MEDIUM, BiscottoSeverity.HIGH, BiscottoSeverity.EXTREME]
    
    # Build reasoning (V4.3: use dynamic threshold)
    reasoning_parts = []
    
    if current_draw_odd < dynamic_suspicious_threshold:
        reasoning_parts.append(f"Quota X a {current_draw_odd:.2f} (prob. implicita {implied_prob*100:.0f}%)")
    
    if drop_pct >= DROP_MEDIUM:
        reasoning_parts.append(f"calo del {drop_pct:.1f}% dall'apertura")
    
    if zscore >= ZSCORE_MEDIUM:
        reasoning_parts.append(f"Z-Score {zscore:.1f} (anomalia statistica)")
    
    if mutual_benefit:
        reasoning_parts.append(benefit_reason)
    
    if end_of_season:
        reasoning_parts.append("ultime giornate di campionato")
    
    reasoning = " | ".join(reasoning_parts) if reasoning_parts else "Nessun segnale biscotto rilevato"
    
    # Betting recommendation
    if severity == BiscottoSeverity.EXTREME:
        betting_recommendation = "BET X (Alta fiducia)"
    elif severity == BiscottoSeverity.HIGH:
        betting_recommendation = "BET X (Fiducia moderata)"
    elif severity == BiscottoSeverity.MEDIUM:
        betting_recommendation = "MONITOR (Valutare live)"
    else:
        betting_recommendation = "AVOID"
    
    return BiscottoAnalysis(
        is_suspect=is_suspect,
        severity=severity,
        confidence=confidence,
        current_draw_odd=current_draw_odd,
        opening_draw_odd=opening_draw_odd,
        drop_percentage=drop_pct,
        implied_probability=implied_prob,
        zscore=zscore,
        pattern=pattern,
        home_context=home_context,
        away_context=away_context,
        end_of_season_match=end_of_season,
        mutual_benefit=mutual_benefit,
        reasoning=reasoning,
        betting_recommendation=betting_recommendation,
        factors=factors
    )


def format_biscotto_context(analysis: BiscottoAnalysis) -> str:
    """
    Format biscotto analysis for AI context injection.
    
    Args:
        analysis: BiscottoAnalysis result
        
    Returns:
        Formatted string for AI prompt
    """
    if not analysis.is_suspect:
        return ""
    
    lines = [
        f"🍪 BISCOTTO ANALYSIS (Severity: {analysis.severity.value}):",
        f"  Quota X: {analysis.current_draw_odd:.2f} (prob: {analysis.implied_probability*100:.0f}%)",
    ]
    
    if analysis.drop_percentage > 0:
        lines.append(f"  Drop: -{analysis.drop_percentage:.1f}% | Pattern: {analysis.pattern.value}")
    
    if analysis.zscore >= ZSCORE_MEDIUM:
        lines.append(f"  Z-Score: {analysis.zscore:.1f} (anomalia vs media lega)")
    
    if analysis.mutual_benefit:
        lines.append(f"  🤝 Beneficio reciproco rilevato")
    
    if analysis.end_of_season_match:
        lines.append(f"  📅 Fine stagione")
    
    lines.append(f"  💡 Raccomandazione: {analysis.betting_recommendation}")
    
    return "\n".join(lines)


# ============================================
# INTEGRATION HELPER
# ============================================

def _estimate_matches_remaining_from_date(match_start_time, league_key: str = None) -> int:
    """
    V5.1: Fallback estimation of matches_remaining when FotMob data is unavailable.
    
    Uses heuristics based on typical season calendar:
    - European leagues: End in May (weeks 18-22)
    - MLS: March-October season
    - A-League: October-May season (southern hemisphere)
    - Season has ~38 matches, spread over ~40 weeks
    
    V1.1 Fix #7: Now uses league_key for league-specific season calendars.
    
    This is a FALLBACK - FotMob data is always preferred when available.
    
    Args:
        match_start_time: Match datetime
        league_key: League identifier for season-specific adjustments
        
    Returns:
        Estimated matches remaining (conservative estimate)
    """
    if not match_start_time:
        return None
    
    try:
        from datetime import datetime, timezone
        
        # Ensure timezone-aware
        if match_start_time.tzinfo is None:
            match_start_time = match_start_time.replace(tzinfo=timezone.utc)
        
        month = match_start_time.month
        
        # Fix #7: League-specific season calendars
        # Southern hemisphere leagues (A-League, Brazil) have inverted seasons
        SOUTHERN_HEMISPHERE_LEAGUES = {
            "soccer_australia_aleague",
            "soccer_brazil_campeonato",
            "soccer_brazil_serie_b",
            "soccer_argentina_primera_division",
        }
        
        # MLS has March-October season
        MLS_LEAGUES = {
            "soccer_usa_mls",
        }
        
        if league_key in SOUTHERN_HEMISPHERE_LEAGUES:
            # Southern hemisphere: Season runs Oct-May
            # End of season: March-May
            # Start of season: August-October
            if month in (3, 4, 5):  # March-May: End of season
                return 4
            elif month in (10, 11, 12):  # Oct-Dec: Early season
                return 25
            elif month in (1, 2):  # Jan-Feb: Mid-late season
                return 10
            else:  # June-Sept: Off-season or very early
                return 30
        
        elif league_key in MLS_LEAGUES:
            # MLS: Season runs March-October
            if month in (9, 10):  # Sept-Oct: End of season / playoffs
                return 4
            elif month in (3, 4):  # March-April: Early season
                return 30
            elif month in (5, 6, 7, 8):  # May-Aug: Mid-season
                return 15
            else:  # Nov-Feb: Off-season
                return None  # No matches
        
        else:
            # European leagues (default): Season runs Aug-May
            # End-of-season detection based on month
            if month in (4, 5):  # April-May: End of season
                return 4
            elif month == 3:  # March: Late season
                return 10
            elif month in (12, 1, 2):  # Winter: Mid-season
                return 18
            else:  # August-November: Early-mid season
                return 25
            
    except Exception as e:
        logger.debug(f"Could not estimate matches_remaining: {e}")
        return None


def get_enhanced_biscotto_analysis(
    match_obj,
    home_motivation: Dict = None,
    away_motivation: Dict = None
) -> Tuple[BiscottoAnalysis, str]:
    """
    Integration helper for main.py - analyzes match for biscotto signals.
    
    V4.3: Now extracts league_key from match_obj for dynamic thresholds.
    V4.4: Now extracts matches_remaining from motivation context for end-of-season detection.
    V5.1: Added fallback estimation when FotMob doesn't provide matches_remaining.
    
    Args:
        match_obj: Match database object
        home_motivation: FotMob motivation context for home team
        away_motivation: FotMob motivation context for away team
        
    Returns:
        Tuple of (BiscottoAnalysis, formatted_context_string)
    """
    # V4.3: Extract league_key for dynamic thresholds
    league_key = getattr(match_obj, 'league', None)
    
    # V4.4: Extract matches_remaining from motivation context
    # Use the minimum of both teams (most conservative for end-of-season detection)
    matches_remaining = None
    home_remaining = home_motivation.get('matches_remaining') if home_motivation else None
    away_remaining = away_motivation.get('matches_remaining') if away_motivation else None
    
    if home_remaining is not None and away_remaining is not None:
        matches_remaining = min(home_remaining, away_remaining)
    elif home_remaining is not None:
        matches_remaining = home_remaining
    elif away_remaining is not None:
        matches_remaining = away_remaining
    
    # V5.1: Fallback estimation if FotMob data unavailable
    if matches_remaining is None:
        match_start_time = getattr(match_obj, 'start_time', None)
        matches_remaining = _estimate_matches_remaining_from_date(match_start_time, league_key)
        if matches_remaining is not None:
            logger.debug(f"🍪 matches_remaining estimated from date: {matches_remaining}")
    
    analysis = analyze_biscotto(
        home_team=match_obj.home_team,
        away_team=match_obj.away_team,
        current_draw_odd=match_obj.current_draw_odd,
        opening_draw_odd=match_obj.opening_draw_odd,
        home_motivation=home_motivation,
        away_motivation=away_motivation,
        matches_remaining=matches_remaining,  # V4.4 + V5.1 fallback
        league_key=league_key  # V4.3
    )
    
    context_str = format_biscotto_context(analysis)
    
    return analysis, context_str
