"""
EarlyBird Math Engine - Quantitative Analysis Layer

Implements:
- Poisson Distribution Model for match outcome prediction (V4.2: Dixon-Coles correction)
- Kelly Criterion for optimal stake sizing (V4.2: Shrinkage Kelly)
- Edge calculation (Math Probability vs Bookmaker Implied Probability)
- League-specific Home Advantage (V4.3: Deep Research enhancement)

This provides a "Big Data" verification layer to complement qualitative AI analysis.

V4.3 Enhancements:
- League-specific Home Advantage (HA varies from 0.22 to 0.40 by league)
- Dixon-Coles rho tuned to -0.07 (was -0.10, per research recommendations)

V4.2 Enhancements:
- Dixon-Coles correction for low-scoring games (0-0, 1-0, 0-1, 1-1)
- Shrinkage Kelly using confidence intervals
"""
import math
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# League average goals per team per match (typical European leagues)
DEFAULT_LEAGUE_AVG = 1.35

# Minimum matches required for reliable Poisson calculation
MIN_MATCHES_REQUIRED = 5

# V3.7: Money Management Safety Cap
MAX_STAKE_PCT = 5.0  # Maximum 5% of bankroll per bet

# V4.3: Dixon-Coles rho parameter TUNED (was -0.10)
# Research suggests -0.05 to -0.08 is optimal for most leagues
# Using -0.07 as balanced compromise
DIXON_COLES_RHO = -0.07


@dataclass
class PoissonResult:
    """Result of Poisson simulation."""
    home_win_prob: float  # Probability of home win (0-1)
    draw_prob: float      # Probability of draw (0-1)
    away_win_prob: float  # Probability of away win (0-1)
    
    # Expected goals
    home_lambda: float    # Expected home goals
    away_lambda: float    # Expected away goals
    
    # Most likely scorelines
    most_likely_score: str
    over_25_prob: float   # Probability of Over 2.5 goals
    under_25_prob: float  # V7.7: Probability of Under 2.5 goals
    btts_prob: float      # Probability of Both Teams To Score
    
    def __post_init__(self):
        """Ensure probabilities sum to ~1."""
        total = self.home_win_prob + self.draw_prob + self.away_win_prob
        if total > 0:
            self.home_win_prob /= total
            self.draw_prob /= total
            self.away_win_prob /= total


@dataclass
class EdgeResult:
    """Result of edge calculation."""
    market: str           # "HOME", "DRAW", "AWAY", "OVER_25", "BTTS"
    math_prob: float      # Mathematical probability (0-100)
    implied_prob: float   # Bookmaker implied probability (0-100)
    edge: float           # Edge percentage (math - implied)
    fair_odd: float       # Fair odd based on math probability
    actual_odd: float     # Actual bookmaker odd
    kelly_stake: float    # Recommended stake % (Kelly/4)
    has_value: bool       # True if edge > 0


class MathPredictor:
    """
    Quantitative match prediction using Poisson Distribution.
    
    The Poisson model calculates the probability of each team scoring
    0, 1, 2, 3... goals based on their attacking/defensive strength
    relative to league averages.
    
    V4.3: Now supports league-specific Home Advantage for more accurate predictions.
    """
    
    def __init__(self, league_avg: float = DEFAULT_LEAGUE_AVG, league_key: str = None):
        """
        Initialize predictor.
        
        Args:
            league_avg: Average goals per team per match in the league
            league_key: League identifier for league-specific adjustments (V4.3)
        """
        self.league_avg = league_avg
        self.league_key = league_key
        
        # V4.3: Get league-specific home advantage
        self.home_advantage = self._get_home_advantage(league_key)
        
        if league_key and self.home_advantage != 0.30:  # Log only if non-default
            logger.debug(f"MathPredictor initialized for {league_key} with HA={self.home_advantage}")
    
    def _get_home_advantage(self, league_key: str) -> float:
        """
        Get league-specific home advantage.
        
        V4.3: Home Advantage varies significantly by league:
        - High HA (0.35-0.40): Turkey, Greece, Argentina, Brazil
        - Medium HA (0.27-0.32): France, Italy, Spain, Scotland
        - Low HA (0.22-0.25): Bundesliga, Premier League
        
        Args:
            league_key: League identifier
            
        Returns:
            Home advantage value (goal boost for home team)
        """
        try:
            from config.settings import get_home_advantage
            return get_home_advantage(league_key)
        except ImportError:
            # Fallback if settings not available
            return 0.30
    
    @staticmethod
    def poisson_probability(lam: float, k: int) -> float:
        """
        Calculate Poisson probability P(X=k) = (λ^k * e^-λ) / k!
        
        Args:
            lam: Lambda (expected value)
            k: Number of occurrences
            
        Returns:
            Probability of exactly k occurrences
        """
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)
    
    @staticmethod
    def dixon_coles_correction(home_goals: int, away_goals: int, 
                                home_lambda: float, away_lambda: float,
                                rho: float = DIXON_COLES_RHO) -> float:
        """
        V4.2: Dixon-Coles correction factor for low-scoring games.
        V4.6 FIX: Added safety bounds to prevent correction > 2.0 or < 0.01
        
        The standard Poisson model underestimates draws (especially 0-0, 1-1)
        because it assumes independence between home and away goals.
        
        Dixon-Coles introduces a correlation parameter (rho) that adjusts
        probabilities for scores 0-0, 1-0, 0-1, and 1-1.
        
        Note: rho is typically NEGATIVE (-0.05 to -0.13), so:
        - For 0-0: 1.0 - (λh * λa * negative) = 1.0 + positive → INCREASES P(0-0)
        - For 1-1: 1.0 - negative = 1.0 + positive → INCREASES P(1-1)
        
        Args:
            home_goals: Home team goals (0 or 1 for correction)
            away_goals: Away team goals (0 or 1 for correction)
            home_lambda: Expected home goals
            away_lambda: Expected away goals
            rho: Correlation parameter (typically -0.13 to -0.05)
            
        Returns:
            Correction multiplier (clamped to 0.01-2.0 for safety)
        """
        correction = 1.0
        
        if home_goals == 0 and away_goals == 0:
            # 0-0: Increase probability (draws underestimated)
            # With rho=-0.07, λh=1.5, λa=1.2: 1.0 - (1.5*1.2*-0.07) = 1.0 + 0.126 = 1.126
            correction = 1.0 - (home_lambda * away_lambda * rho)
        elif home_goals == 0 and away_goals == 1:
            # 0-1: Slight adjustment
            correction = 1.0 + (home_lambda * rho)
        elif home_goals == 1 and away_goals == 0:
            # 1-0: Slight adjustment
            correction = 1.0 + (away_lambda * rho)
        elif home_goals == 1 and away_goals == 1:
            # 1-1: Increase probability slightly (draws underestimated)
            correction = 1.0 - rho
        else:
            # No correction for higher scores
            return 1.0
        
        # V4.6 FIX: Clamp correction to reasonable bounds
        # Prevents extreme values when λ is high (e.g., λh=4, λa=4 → unclamped could be 2.12)
        # Max 2.0 = double the base probability (reasonable upper bound)
        # Min 0.01 = near-zero but not zero (prevents division issues downstream)
        return max(0.01, min(correction, 2.0))
    
    def calculate_strength(
        self,
        home_scored: float,
        home_conceded: float,
        away_scored: float,
        away_conceded: float
    ) -> Tuple[float, float, float, float]:
        """
        Calculate attack and defense strength for both teams.
        
        Strength = Team Average / League Average
        
        Args:
            home_scored: Home team avg goals scored
            home_conceded: Home team avg goals conceded
            away_scored: Away team avg goals scored
            away_conceded: Away team avg goals conceded
            
        Returns:
            Tuple of (home_attack, home_defense, away_attack, away_defense)
        """
        # Attack strength = goals scored / league avg
        home_attack = home_scored / self.league_avg if self.league_avg > 0 else 1.0
        away_attack = away_scored / self.league_avg if self.league_avg > 0 else 1.0
        
        # Defense strength = goals conceded / league avg (higher = weaker defense)
        home_defense = home_conceded / self.league_avg if self.league_avg > 0 else 1.0
        away_defense = away_conceded / self.league_avg if self.league_avg > 0 else 1.0
        
        return home_attack, home_defense, away_attack, away_defense
    
    def simulate_match(
        self,
        home_scored: float,
        home_conceded: float,
        away_scored: float,
        away_conceded: float,
        max_goals: int = 6,
        use_dixon_coles: bool = True,
        apply_home_advantage: bool = True
    ) -> Optional[PoissonResult]:
        """
        Simulate match using Poisson distribution with Dixon-Coles correction.
        
        V4.3: Added league-specific Home Advantage.
        V4.2: Added Dixon-Coles correction for low-scoring games.
        
        Args:
            home_scored: Home team avg goals scored per match
            home_conceded: Home team avg goals conceded per match
            away_scored: Away team avg goals scored per match
            away_conceded: Away team avg goals conceded per match
            max_goals: Maximum goals to simulate per team (default 6)
            use_dixon_coles: Apply Dixon-Coles correction (default True)
            apply_home_advantage: Apply league-specific HA (default True, V4.3)
            
        Returns:
            PoissonResult with probabilities, or None if invalid inputs
        """
        # Validate inputs
        if any(x is None or x < 0 for x in [home_scored, home_conceded, away_scored, away_conceded]):
            logger.warning("Invalid stats for Poisson simulation")
            return None
        
        # Calculate strength
        home_attack, home_defense, away_attack, away_defense = self.calculate_strength(
            home_scored, home_conceded, away_scored, away_conceded
        )
        
        # Calculate expected goals (lambda)
        # Home Lambda = Home Attack * Away Defense * League Avg
        # Away Lambda = Away Attack * Home Defense * League Avg
        home_lambda = home_attack * away_defense * self.league_avg
        away_lambda = away_attack * home_defense * self.league_avg
        
        # V4.3: Apply league-specific Home Advantage
        # V4.6 FIX: Symmetric application - only boost home, don't penalize away
        # Research shows HA primarily affects home scoring, not away suppression
        # Penalizing away_lambda was causing asymmetric probability distortion
        if apply_home_advantage and self.home_advantage > 0:
            home_lambda += self.home_advantage
            # V4.6: Removed away_lambda penalty - asymmetric adjustment was distorting probabilities
            # The home advantage is already captured by boosting home_lambda
            # away_lambda remains based purely on team strength metrics
        
        # Ensure reasonable bounds
        home_lambda = max(0.1, min(5.0, home_lambda))
        away_lambda = max(0.1, min(5.0, away_lambda))
        
        # Simulate all scorelines from 0-0 to max_goals-max_goals
        scoreline_probs = {}
        home_win_prob = 0.0
        draw_prob = 0.0
        away_win_prob = 0.0
        over_25_prob = 0.0
        under_25_prob = 0.0  # V7.7: Track Under 2.5
        btts_prob = 0.0
        
        for home_goals in range(max_goals + 1):
            for away_goals in range(max_goals + 1):
                # Base Poisson probability
                prob = (
                    self.poisson_probability(home_lambda, home_goals) *
                    self.poisson_probability(away_lambda, away_goals)
                )
                
                # V4.2: Apply Dixon-Coles correction for low scores
                if use_dixon_coles and home_goals <= 1 and away_goals <= 1:
                    correction = self.dixon_coles_correction(
                        home_goals, away_goals, home_lambda, away_lambda
                    )
                    prob *= correction
                
                scoreline = f"{home_goals}-{away_goals}"
                scoreline_probs[scoreline] = prob
                
                # Accumulate outcome probabilities
                if home_goals > away_goals:
                    home_win_prob += prob
                elif home_goals == away_goals:
                    draw_prob += prob
                else:
                    away_win_prob += prob
                
                # Over/Under 2.5 goals
                if home_goals + away_goals > 2.5:
                    over_25_prob += prob
                else:
                    under_25_prob += prob  # V7.7: 0, 1, or 2 total goals
                
                # Both Teams To Score
                if home_goals > 0 and away_goals > 0:
                    btts_prob += prob
        
        # Find most likely scoreline
        most_likely = max(scoreline_probs, key=scoreline_probs.get)
        
        return PoissonResult(
            home_win_prob=home_win_prob,
            draw_prob=draw_prob,
            away_win_prob=away_win_prob,
            home_lambda=home_lambda,
            away_lambda=away_lambda,
            most_likely_score=most_likely,
            over_25_prob=over_25_prob,
            under_25_prob=under_25_prob,  # V7.7
            btts_prob=btts_prob
        )
    
    @staticmethod
    def calculate_edge(math_prob: float, bookmaker_odd: float, 
                       sample_size: int = 10, use_shrinkage: bool = True) -> EdgeResult:
        """
        Calculate edge between mathematical probability and bookmaker odds.
        
        V4.2: Added Shrinkage Kelly - uses lower bound of confidence interval
        instead of point estimate to protect against estimation error.
        
        Args:
            math_prob: Mathematical probability (0-1)
            bookmaker_odd: Decimal bookmaker odd
            sample_size: Number of matches used for probability estimate (default 10)
            use_shrinkage: Apply shrinkage to Kelly based on sample size (default True)
            
        Returns:
            EdgeResult with edge calculation and Kelly stake (capped at MAX_STAKE_PCT)
        """
        # Safety: Reject odds too close to 1.0 (too risky/low reward)
        if bookmaker_odd <= 1.05:
            return EdgeResult(
                market="UNKNOWN",
                math_prob=math_prob * 100,
                implied_prob=100.0,
                edge=0.0,
                fair_odd=1.0,
                actual_odd=bookmaker_odd,
                kelly_stake=0.0,
                has_value=False
            )
        
        # Safety: Clamp probability - no certainty exists in sports
        if math_prob >= 0.99:
            math_prob = 0.99
        
        # V4.2: Shrinkage Kelly - use lower bound of confidence interval
        # The idea: with small samples, our probability estimate is uncertain
        # We bet based on the conservative (lower) end of our estimate
        # V4.5 FIX: Reduced shrinkage from 1.96 (95% CI) to 1.0 (68% CI)
        # V4.6 FIX: Further relaxed shrinkage for small samples
        # - Minimum confidence_factor raised from 0.5 to 0.6
        # - Threshold lowered from n>=20 to n>=15 for full confidence
        # This prevents Kelly always = 0% for matches with limited historical data
        if use_shrinkage and sample_size > 0:
            # Standard error of proportion: SE = sqrt(p*(1-p)/n)
            # 68% CI lower bound: p - 1.0 * SE
            se = math.sqrt(math_prob * (1 - math_prob) / sample_size)
            shrinkage_prob = max(0.01, math_prob - 1.0 * se)
            
            # Blend: more samples = trust point estimate more
            # V4.6 FIX: confidence_factor now goes from 0.6 (n=5) to 1.0 (n>=15)
            # This is more appropriate for sports betting where 10-15 matches is typical
            confidence_factor = min(1.0, max(0.6, sample_size / 15))
            effective_prob = shrinkage_prob + (math_prob - shrinkage_prob) * confidence_factor
        else:
            effective_prob = math_prob
        
        # Implied probability from bookmaker odd
        implied_prob = 1.0 / bookmaker_odd
        
        # Fair odd based on math probability (use original for display)
        fair_odd = 1.0 / math_prob if math_prob > 0 else 999.0
        
        # Edge = Math Probability - Implied Probability (use original for display)
        edge = (math_prob - implied_prob) * 100
        
        # Kelly Criterion: f* = (bp - q) / b
        # where b = odd - 1, p = probability, q = 1 - p
        # V4.2: Use effective_prob (shrunk) for Kelly calculation
        b = bookmaker_odd - 1
        kelly_full = ((b * effective_prob) - (1 - effective_prob)) / b if b > 0 else 0
        
        # Kelly/4 for conservative bankroll management
        kelly_quarter = kelly_full / 4
        stake_pct = max(0, kelly_quarter) * 100  # Convert to percentage
        
        # V3.7: Safety cap - limit max exposure per bet
        if stake_pct > MAX_STAKE_PCT:
            logger.debug(f"Kelly stake capped: {stake_pct:.1f}% -> {MAX_STAKE_PCT}%")
            stake_pct = MAX_STAKE_PCT
        
        return EdgeResult(
            market="",  # Set by caller
            math_prob=math_prob * 100,
            implied_prob=implied_prob * 100,
            edge=edge,
            fair_odd=round(fair_odd, 2),
            actual_odd=bookmaker_odd,
            kelly_stake=round(stake_pct, 2),
            has_value=edge > 0
        )
    
    def analyze_match(
        self,
        home_scored: float,
        home_conceded: float,
        away_scored: float,
        away_conceded: float,
        home_odd: float,
        draw_odd: float,
        away_odd: float,
        over_25_odd: float = None,
        under_25_odd: float = None,
        btts_odd: float = None
    ) -> Dict:
        """
        Full match analysis with edge calculation for all markets.
        
        Args:
            home_scored/conceded: Home team stats
            away_scored/conceded: Away team stats
            home/draw/away_odd: 1X2 market odds
            over_25_odd: Over 2.5 goals odd (optional)
            under_25_odd: Under 2.5 goals odd (optional, V7.7)
            btts_odd: Both Teams To Score odd (optional)
            
        Returns:
            Dict with Poisson result and edge calculations for each market
        """
        # Run Poisson simulation
        poisson = self.simulate_match(
            home_scored, home_conceded,
            away_scored, away_conceded
        )
        
        if not poisson:
            return {"error": "Insufficient data for Poisson simulation"}
        
        # Calculate edges for each market
        edges = {}
        
        # 1X2 Markets
        if home_odd and home_odd > 1:
            edge = MathPredictor.calculate_edge(poisson.home_win_prob, home_odd)
            edge.market = "HOME"
            edges["home"] = edge
        
        if draw_odd and draw_odd > 1:
            edge = MathPredictor.calculate_edge(poisson.draw_prob, draw_odd)
            edge.market = "DRAW"
            edges["draw"] = edge
        
        if away_odd and away_odd > 1:
            edge = MathPredictor.calculate_edge(poisson.away_win_prob, away_odd)
            edge.market = "AWAY"
            edges["away"] = edge
        
        # Over 2.5 Goals
        if over_25_odd and over_25_odd > 1:
            edge = MathPredictor.calculate_edge(poisson.over_25_prob, over_25_odd)
            edge.market = "OVER_25"
            edges["over_25"] = edge
        
        # V7.7: Under 2.5 Goals (calculated from Poisson)
        # Under 2.5 is more valuable when expected goals < 2.3
        if under_25_odd and under_25_odd > 1:
            # Use provided Under 2.5 odd
            edge = MathPredictor.calculate_edge(poisson.under_25_prob, under_25_odd)
            edge.market = "UNDER_25"
            edges["under_25"] = edge
        elif over_25_odd and over_25_odd > 1:
            # Derive Under 2.5 odd from Over 2.5 odd (inverse relationship)
            # Formula: under_odd ≈ 1 / (1/over_odd - margin)
            # Using a simplified approach: under_odd = 1 / (1 - 1/over_odd) for estimation
            # This is an approximation as bookmakers have different margins for each market
            try:
                over_implied_prob = 1.0 / over_25_odd
                # Assuming bookmaker margin is ~5%, distribute it
                # Under implied prob ≈ 1 - over_implied_prob - margin
                margin = 0.05
                under_implied_prob = max(0.01, 1.0 - over_implied_prob - margin)
                derived_under_odd = 1.0 / under_implied_prob if under_implied_prob > 0 else 1.85
                
                edge = MathPredictor.calculate_edge(poisson.under_25_prob, derived_under_odd)
                edge.market = "UNDER_25"
                edges["under_25"] = edge
            except (ZeroDivisionError, ValueError):
                # Fallback to typical market odd if calculation fails
                pass
        
        # BTTS
        if btts_odd and btts_odd > 1:
            edge = MathPredictor.calculate_edge(poisson.btts_prob, btts_odd)
            edge.market = "BTTS"
            edges["btts"] = edge
        
        # V7.7: Double Chance Markets (1X, X2)
        # These are calculated from combined probabilities, not from single odds
        # P(1X) = P(Home) + P(Draw), P(X2) = P(Draw) + P(Away)
        dc_1x_prob = poisson.home_win_prob + poisson.draw_prob
        dc_x2_prob = poisson.draw_prob + poisson.away_win_prob
        
        # Calculate implied market odds for double chance from 1X2 odds
        # Formula: 1X market odd ≈ 1 / (1/home_odd + 1/draw_odd) 
        # This gives the actual market price for the combined outcome
        if home_odd and home_odd > 1 and draw_odd and draw_odd > 1:
            # Implied 1X market odd from bookmaker's 1X2 odds
            dc_1x_implied_prob = (1.0/home_odd) + (1.0/draw_odd)
            dc_1x_market_odd = 1.0 / dc_1x_implied_prob if dc_1x_implied_prob > 0 else 1.01
            # Fair odd from our Poisson probability
            dc_1x_fair_odd = 1.0 / dc_1x_prob if dc_1x_prob > 0 else 99.0
            edge = MathPredictor.calculate_edge(dc_1x_prob, dc_1x_market_odd)
            edge.market = "1X"
            edge.fair_odd = round(dc_1x_fair_odd, 2)
            edges["1x"] = edge
        
        if draw_odd and draw_odd > 1 and away_odd and away_odd > 1:
            # Implied X2 market odd from bookmaker's 1X2 odds
            dc_x2_implied_prob = (1.0/draw_odd) + (1.0/away_odd)
            dc_x2_market_odd = 1.0 / dc_x2_implied_prob if dc_x2_implied_prob > 0 else 1.01
            dc_x2_fair_odd = 1.0 / dc_x2_prob if dc_x2_prob > 0 else 99.0
            edge = MathPredictor.calculate_edge(dc_x2_prob, dc_x2_market_odd)
            edge.market = "X2"
            edge.fair_odd = round(dc_x2_fair_odd, 2)
            edges["x2"] = edge
        
        # Find best value market
        best_edge = None
        best_market = None
        for market, edge in edges.items():
            if edge.has_value and (best_edge is None or edge.edge > best_edge.edge):
                best_edge = edge
                best_market = market
        
        return {
            "poisson": poisson,
            "edges": edges,
            "best_market": best_market,
            "best_edge": best_edge,
            "expected_goals": round(poisson.home_lambda + poisson.away_lambda, 2),
            "most_likely_score": poisson.most_likely_score
        }


def format_math_context(analysis: Dict, market: str = "home") -> str:
    """
    Format math analysis as context string for DeepSeek prompt.
    
    Args:
        analysis: Result from MathPredictor.analyze_match()
        market: Which market to highlight ("home", "draw", "away", "over_25", "btts")
        
    Returns:
        Formatted string for AI prompt
    """
    if "error" in analysis:
        return f"📉 MATH MODEL: {analysis['error']}"
    
    poisson = analysis["poisson"]
    edges = analysis.get("edges", {})
    
    lines = [
        f"📉 **MATH MODEL (Poisson):**",
        f"   Expected Goals: {analysis['expected_goals']} | Most Likely: {poisson.most_likely_score}",
        f"   Home Win: {poisson.home_win_prob*100:.1f}% | Draw: {poisson.draw_prob*100:.1f}% | Away: {poisson.away_win_prob*100:.1f}%",
        f"   Over 2.5: {poisson.over_25_prob*100:.1f}% | BTTS: {poisson.btts_prob*100:.1f}%"
    ]
    
    # Add edge info for requested market
    if market in edges:
        edge = edges[market]
        if edge.has_value:
            lines.append(f"   🎯 **VALUE DETECTED on {edge.market}:** Math {edge.math_prob:.1f}% vs Implied {edge.implied_prob:.1f}% = **+{edge.edge:.1f}% Edge**")
            lines.append(f"   💰 Fair Odd: {edge.fair_odd} | Actual: {edge.actual_odd} | Kelly Stake: {edge.kelly_stake}%")
        else:
            lines.append(f"   ⚠️ No value on {edge.market}: Math {edge.math_prob:.1f}% vs Implied {edge.implied_prob:.1f}% = {edge.edge:.1f}%")
    
    # Highlight best value if different
    best = analysis.get("best_edge")
    if best and best.market.lower() != market:
        lines.append(f"   💡 Best Value: {best.market} (+{best.edge:.1f}% edge)")
    
    return "\n".join(lines)


# Convenience function for quick analysis
def quick_poisson(
    home_scored: float,
    home_conceded: float,
    away_scored: float,
    away_conceded: float,
    league_key: str = None
) -> Optional[PoissonResult]:
    """Quick Poisson simulation without edge calculation.
    
    V4.3: Now supports league_key for league-specific Home Advantage.
    """
    predictor = MathPredictor(league_key=league_key)
    return predictor.simulate_match(home_scored, home_conceded, away_scored, away_conceded)


def calculate_btts_trend(h2h_matches: list) -> dict:
    """
    Calculate BTTS (Both Teams To Score) trend from H2H history.
    
    Analyzes historical head-to-head matches to determine how often
    both teams scored, providing a pattern-based BTTS indicator.
    
    Args:
        h2h_matches: List of dicts with 'home_score' and 'away_score' keys
                     e.g., [{'home_score': 2, 'away_score': 1}, ...]
    
    Returns:
        Dict with:
        - btts_rate: Percentage of games where both teams scored (0-100)
        - btts_hits: Number of BTTS games
        - total_games: Total valid games analyzed
        - trend_signal: "High" (>=60%), "Medium" (40-60%), "Low" (<40%)
    
    Edge Cases:
        - Empty list: Returns 0% rate with "Unknown" signal
        - None values in scores: Skipped safely
        - Invalid data types: Handled via try/except
    """
    result = {
        "btts_rate": 0.0,
        "btts_hits": 0,
        "total_games": 0,
        "trend_signal": "Unknown"
    }
    
    # Safety: Handle None or non-list input
    if not h2h_matches or not isinstance(h2h_matches, list):
        logger.debug(f"calculate_btts_trend: Empty or invalid input (type={type(h2h_matches).__name__})")
        return result
    
    btts_hits = 0
    valid_games = 0
    
    for match in h2h_matches:
        # Safety: Skip non-dict entries
        if not isinstance(match, dict):
            continue
        
        try:
            home_score = match.get('home_score')
            away_score = match.get('away_score')
            
            # Skip if scores are None or invalid
            if home_score is None or away_score is None:
                continue
            
            # Convert to int safely (API might return strings)
            home_score = int(home_score)
            away_score = int(away_score)
            
            # Valid game - count it
            valid_games += 1
            
            # BTTS check: both teams scored at least 1 goal
            if home_score > 0 and away_score > 0:
                btts_hits += 1
                
        except (ValueError, TypeError):
            # Skip malformed entries
            continue
    
    result["total_games"] = valid_games
    result["btts_hits"] = btts_hits
    
    # Calculate rate (avoid division by zero)
    if valid_games > 0:
        rate = (btts_hits / valid_games) * 100
        result["btts_rate"] = round(rate, 1)
        
        # Determine trend signal
        if rate >= 60:
            result["trend_signal"] = "High"
        elif rate >= 40:
            result["trend_signal"] = "Medium"
        else:
            result["trend_signal"] = "Low"
    
    logger.info(f"⚽ H2H BTTS Trend: {btts_hits}/{valid_games} games ({result['btts_rate']}%) - {result['trend_signal']}")
    
    return result


if __name__ == "__main__":
    # Test the math engine
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("EarlyBird Math Engine Test")
    print("=" * 60)
    
    # Example: Strong home team vs weak away team
    predictor = MathPredictor()
    
    result = predictor.analyze_match(
        home_scored=2.1,    # Home scores 2.1 goals/game
        home_conceded=0.8,  # Home concedes 0.8 goals/game
        away_scored=1.2,    # Away scores 1.2 goals/game
        away_conceded=1.9,  # Away concedes 1.9 goals/game
        home_odd=1.65,      # Bookmaker home odd
        draw_odd=3.80,      # Bookmaker draw odd
        away_odd=5.50,      # Bookmaker away odd
        over_25_odd=1.85,   # Over 2.5 odd
        btts_odd=1.75       # BTTS odd
    )
    
    print("\n📊 Poisson Simulation:")
    poisson = result["poisson"]
    print(f"   Home Win: {poisson.home_win_prob*100:.1f}%")
    print(f"   Draw: {poisson.draw_prob*100:.1f}%")
    print(f"   Away Win: {poisson.away_win_prob*100:.1f}%")
    print(f"   Expected Goals: {result['expected_goals']}")
    print(f"   Most Likely Score: {poisson.most_likely_score}")
    print(f"   Over 2.5: {poisson.over_25_prob*100:.1f}%")
    print(f"   BTTS: {poisson.btts_prob*100:.1f}%")
    
    print("\n💰 Edge Analysis:")
    for market, edge in result["edges"].items():
        status = "✅ VALUE" if edge.has_value else "❌ No Value"
        print(f"   {market.upper()}: {status} | Edge: {edge.edge:+.1f}% | Kelly: {edge.kelly_stake}%")
    
    if result["best_edge"]:
        print(f"\n🎯 Best Bet: {result['best_market'].upper()} (+{result['best_edge'].edge:.1f}% edge)")
    
    print("\n" + "=" * 60)
    print("Context for DeepSeek:")
    print(format_math_context(result, "home"))
