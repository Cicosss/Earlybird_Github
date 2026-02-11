"""
EarlyBird Betting Quant Module (V1.0)
========================================

This module acts as the "expert financial analyst" of the EarlyBird system,
responsible for final market selection, mathematical calculations, and stake
determination following strict money management laws.

Extracted from src/analysis/math_engine.py and src/analysis/analyzer.py
as part of the modular refactoring initiative.

Key Responsibilities:
- Poisson Distribution Model with Dixon-Coles correction
- Kelly Criterion (Quarter Kelly) for optimal stake sizing
- Edge calculation (Math Probability vs Bookmaker Implied Probability)
- Balanced Probability integration (Poisson + AI Confidence)
- Risk Management Filters (Market Veto, Stake Capping, Volatility Guard)
- Final "Go/No-Go" decision logic

Author: Refactored by Lead Architect
Date: 2026-02-09
"""

import logging
import math
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

# Database
from src.database.models import Match, NewsLog

# Math Engine
from src.analysis.math_engine import MathPredictor, PoissonResult, EdgeResult

# Configure logger
logger = logging.getLogger(__name__)


# ============================================
# BETTING QUANT CONSTANTS
# ============================================

# Money Management Safety Caps
MIN_STAKE_PCT = 0.5  # Minimum 0.5% of bankroll per bet
MAX_STAKE_PCT = 5.0  # Maximum 5.0% of bankroll per bet (hard cap)

# Risk Management Thresholds
MARKET_VETO_THRESHOLD = 0.15  # 15% Market Veto (Value Guard)
VOLATILITY_GUARD_ODDS = 4.50  # Odds threshold for volatility guard
SAFETY_MIN_ODDS = 1.05  # Minimum acceptable odds (too risky/low reward)
SAFETY_MAX_PROB = 0.99  # Maximum probability (no certainty in sports)

# Dixon-Coles Parameters
DIXON_COLES_RHO = -0.07  # Correlation parameter for low-scoring games


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class BettingDecision:
    """
    Final betting decision from the Betting Quant.
    
    This represents the complete "Go/No-Go" decision with all
    supporting calculations for transparency and auditability.
    """
    should_bet: bool  # Final Go/No-Go decision
    verdict: str  # "BET" or "NO BET"
    confidence: float  # Overall confidence (0-100)
    
    # Market Selection
    recommended_market: str  # Primary market recommendation
    primary_market: str  # Specific market (e.g., "1", "X", "Over 2.5")
    
    # Mathematical Analysis
    math_prob: float  # Mathematical probability (0-100)
    implied_prob: float  # Bookmaker implied probability (0-100)
    edge: float  # Edge percentage (math - implied)
    fair_odd: float  # Fair odd based on math probability
    actual_odd: float  # Actual bookmaker odd
    
    # Stake Determination
    kelly_stake: float  # Recommended stake % (Quarter Kelly)
    final_stake: float  # Final stake % after all risk filters
    
    # Risk Management
    veto_reason: Optional[str]  # Reason if vetoed
    safety_violation: Optional[str]  # Safety check violation if any
    volatility_adjusted: bool  # Whether volatility guard was applied
    
    # Supporting Data
    poisson_result: Optional[PoissonResult]  # Poisson simulation results
    balanced_prob: float  # Balanced probability (Poisson + AI)
    ai_prob: Optional[float]  # AI confidence probability
    
    def __post_init__(self):
        """Ensure values are within valid ranges."""
        self.confidence = max(0.0, min(100.0, self.confidence))
        self.math_prob = max(0.0, min(100.0, self.math_prob))
        self.implied_prob = max(0.0, min(100.0, self.implied_prob))
        self.kelly_stake = max(0.0, min(100.0, self.kelly_stake))
        self.final_stake = max(0.0, min(100.0, self.final_stake))


class VetoReason(Enum):
    """Enumeration of possible veto reasons."""
    MARKET_CRASHED = "MARKET_CRASHED"  # Odds dropped >= 15%
    ODDS_TOO_LOW = "ODDS_TOO_LOW"  # Odds <= 1.05
    PROBABILITY_TOO_HIGH = "PROBABILITY_TOO_HIGH"  # Probability >= 99%
    NO_VALUE = "NO_VALUE"  # Edge <= 0
    SAFETY_VIOLATION = "SAFETY_VIOLATION"  # General safety violation


# ============================================
# BETTING QUANT CLASS
# ============================================

class BettingQuant:
    """
    The Betting Quant acts as the expert financial analyst of the system,
    ensuring every bet follows strict money management laws.
    
    This class is responsible for:
    1. Translating "Intelligence signals" into "Betting actions"
    2. Applying all risk-management filters
    3. Calculating optimal stakes using Kelly Criterion
    4. Providing the final "Go/No-Go" decision
    
    The Analysis Engine provides the intelligence, but the Betting Quant
    provides the final decision and specific stake.
    """
    
    def __init__(self, league_avg: float = 1.35, league_key: str = None):
        """
        Initialize the Betting Quant.
        
        Args:
            league_avg: Average goals per team per match in the league
            league_key: League identifier for league-specific adjustments
        """
        self.league_avg = league_avg
        self.league_key = league_key
        self.predictor = MathPredictor(league_avg=league_avg, league_key=league_key)
        self.logger = logger
    
    # ============================================
    # PUBLIC INTERFACE
    # ============================================
    
    def evaluate_bet(
        self,
        match: Match,
        analysis: NewsLog,
        home_scored: float,
        home_conceded: float,
        away_scored: float,
        away_conceded: float,
        market_odds: Dict[str, float],
        ai_prob: Optional[float] = None
    ) -> BettingDecision:
        """
        Evaluate a betting opportunity and return the final decision.
        
        This is the main entry point for the Betting Quant. It performs
        the complete analysis pipeline:
        1. Run Poisson simulation
        2. Calculate edges for all markets
        3. Apply safety guards
        4. Apply market veto (15% threshold)
        5. Calculate Kelly stake
        6. Apply stake capping
        7. Apply volatility guard
        8. Return final decision
        
        Args:
            match: Match database object
            analysis: NewsLog analysis object with score, market, reasoning
            home_scored: Home team avg goals scored per match
            home_conceded: Home team avg goals conceded per match
            away_scored: Away team avg goals scored per match
            away_conceded: Away team avg goals conceded per match
            market_odds: Dict with odds for each market (home, draw, away, over_25, etc.)
            ai_prob: AI confidence probability (0-1) from analysis (optional)
            
        Returns:
            BettingDecision with final Go/No-Go decision and all supporting data
        """
        # Step 1: Run Poisson simulation
        poisson_result = self.predictor.simulate_match(
            home_scored=home_scored,
            home_conceded=home_conceded,
            away_scored=away_scored,
            away_conceded=away_conceded
        )
        
        if not poisson_result:
            return self._create_no_bet_decision(
                reason="Insufficient data for Poisson simulation",
                market_odds=market_odds
            )
        
        # Step 2: Calculate edges for all markets
        edges = self._calculate_all_edges(poisson_result, market_odds, ai_prob)
        
        # Step 3: Select best market based on analysis recommendation
        selected_market = self._select_market(
            analysis=analysis,
            edges=edges,
            poisson_result=poisson_result
        )
        
        if not selected_market:
            return self._create_no_bet_decision(
                reason="No suitable market found",
                market_odds=market_odds,
                poisson_result=poisson_result
            )
        
        edge_result = edges[selected_market]
        
        # Step 4: Apply safety guards (FIRST)
        safety_violation = self._check_safety_guards(
            bookmaker_odd=edge_result.actual_odd,
            math_prob=edge_result.math_prob / 100.0
        )
        
        if safety_violation:
            return self._create_vetoed_decision(
                veto_reason=VetoReason.SAFETY_VIOLATION,
                veto_detail=safety_violation,
                edge_result=edge_result,
                poisson_result=poisson_result,
                market_odds=market_odds,
                ai_prob=ai_prob
            )
        
        # Step 5: Apply market veto (15% threshold) - SECOND
        veto_reason = self._apply_market_veto(
            match=match,
            analysis=analysis,
            edge_result=edge_result
        )
        
        if veto_reason:
            return self._create_vetoed_decision(
                veto_reason=veto_reason,
                veto_detail="Market already crashed (>15% drop)",
                edge_result=edge_result,
                poisson_result=poisson_result,
                market_odds=market_odds,
                ai_prob=ai_prob
            )
        
        # Step 6: Check if there's value - THIRD
        if not edge_result.has_value:
            return self._create_no_value_decision(
                edge_result=edge_result,
                poisson_result=poisson_result,
                market_odds=market_odds,
                ai_prob=ai_prob
            )
        
        # Step 7: Apply stake capping - FOURTH
        capped_stake = self._apply_stake_capping(edge_result.kelly_stake)
        
        # Step 8: Apply volatility guard - FIFTH
        volatility_adjusted, final_stake = self._apply_volatility_guard(
            stake=capped_stake,
            bookmaker_odd=edge_result.actual_odd
        )
        
        # Step 9: Calculate balanced probability
        balanced_prob = self._calculate_balanced_probability(
            math_prob=edge_result.math_prob / 100.0,
            ai_prob=ai_prob,
            edge_result=edge_result
        )
        
        # Step 10: Determine final confidence
        confidence = self._calculate_confidence(
            analysis=analysis,
            edge_result=edge_result,
            balanced_prob=balanced_prob
        )
        
        # Return final BET decision
        return BettingDecision(
            should_bet=True,
            verdict="BET",
            confidence=confidence,
            recommended_market=self._get_market_name(selected_market),
            primary_market=self._get_primary_market(selected_market),
            math_prob=edge_result.math_prob,
            implied_prob=edge_result.implied_prob,
            edge=edge_result.edge,
            fair_odd=edge_result.fair_odd,
            actual_odd=edge_result.actual_odd,
            kelly_stake=edge_result.kelly_stake,
            final_stake=final_stake,
            veto_reason=None,
            safety_violation=None,
            volatility_adjusted=volatility_adjusted,
            poisson_result=poisson_result,
            balanced_prob=balanced_prob * 100.0,
            ai_prob=ai_prob * 100.0 if ai_prob else None
        )
    
    def calculate_stake(
        self,
        math_prob: float,
        bookmaker_odd: float,
        sample_size: int = 10,
        ai_prob: Optional[float] = None
    ) -> float:
        """
        Calculate optimal stake using Kelly Criterion with all risk filters.
        
        This method performs the complete stake calculation pipeline:
        1. Calculate Kelly stake (Quarter Kelly)
        2. Apply stake capping (0.5% - 5.0%)
        3. Apply volatility guard (reduce for odds > 4.50)
        
        Args:
            math_prob: Mathematical probability (0-1)
            bookmaker_odd: Decimal bookmaker odd
            sample_size: Number of matches used for probability estimate
            ai_prob: AI confidence probability (0-1) from analysis (optional)
            
        Returns:
            Final stake percentage (0-100)
        """
        # Calculate edge with Kelly stake
        edge_result = MathPredictor.calculate_edge(
            math_prob=math_prob,
            bookmaker_odd=bookmaker_odd,
            sample_size=sample_size,
            use_shrinkage=True,
            ai_prob=ai_prob
        )
        
        # Apply stake capping
        capped_stake = self._apply_stake_capping(edge_result.kelly_stake)
        
        # Apply volatility guard
        _, final_stake = self._apply_volatility_guard(
            stake=capped_stake,
            bookmaker_odd=bookmaker_odd
        )
        
        return final_stake
    
    # ============================================
    # PRIVATE HELPER METHODS
    # ============================================
    
    def _calculate_all_edges(
        self,
        poisson_result: PoissonResult,
        market_odds: Dict[str, float],
        ai_prob: Optional[float]
    ) -> Dict[str, EdgeResult]:
        """Calculate edges for all available markets."""
        edges = {}
        
        # 1X2 Markets
        if 'home' in market_odds and market_odds['home'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.home_win_prob,
                market_odds['home'],
                ai_prob=ai_prob
            )
            edge.market = "HOME"
            edges["home"] = edge
        
        if 'draw' in market_odds and market_odds['draw'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.draw_prob,
                market_odds['draw'],
                ai_prob=ai_prob
            )
            edge.market = "DRAW"
            edges["draw"] = edge
        
        if 'away' in market_odds and market_odds['away'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.away_win_prob,
                market_odds['away'],
                ai_prob=ai_prob
            )
            edge.market = "AWAY"
            edges["away"] = edge
        
        # Over 2.5 Goals
        if 'over_25' in market_odds and market_odds['over_25'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.over_25_prob,
                market_odds['over_25'],
                ai_prob=ai_prob
            )
            edge.market = "OVER_25"
            edges["over_25"] = edge
        
        # Under 2.5 Goals
        if 'under_25' in market_odds and market_odds['under_25'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.under_25_prob,
                market_odds['under_25'],
                ai_prob=ai_prob
            )
            edge.market = "UNDER_25"
            edges["under_25"] = edge
        
        # BTTS
        if 'btts' in market_odds and market_odds['btts'] > 1:
            edge = MathPredictor.calculate_edge(
                poisson_result.btts_prob,
                market_odds['btts'],
                ai_prob=ai_prob
            )
            edge.market = "BTTS"
            edges["btts"] = edge
        
        return edges
    
    def _select_market(
        self,
        analysis: NewsLog,
        edges: Dict[str, EdgeResult],
        poisson_result: PoissonResult
    ) -> Optional[str]:
        """
        Select the best market based on analysis recommendation and value.
        
        Priority:
        1. Use the market recommended by the analysis (if available)
        2. Fall back to the market with the highest positive edge
        3. Return None if no market has value
        """
        # Try to use the recommended market from analysis
        recommended = getattr(analysis, 'recommended_market', None)
        primary = getattr(analysis, 'primary_market', None)
        
        # Map analysis market to our edge keys
        market_map = {
            '1': 'home',
            'X': 'draw',
            '2': 'away',
            '1X': 'home',  # Use home as proxy for 1X
            'X2': 'away',  # Use away as proxy for X2
            'Over 2.5 Goals': 'over_25',
            'Under 2.5 Goals': 'under_25',
            'BTTS': 'btts'
        }
        
        # Try recommended market first
        if recommended and recommended in market_map:
            key = market_map[recommended]
            if key in edges and edges[key].has_value:
                return key
        
        # Try primary market second
        if primary and primary in market_map:
            key = market_map[primary]
            if key in edges and edges[key].has_value:
                return key
        
        # Fall back to best value market
        best_market = None
        best_edge = None
        for key, edge in edges.items():
            if edge.has_value and (best_edge is None or edge.edge > best_edge.edge):
                best_edge = edge
                best_market = key
        
        return best_market
    
    def _check_safety_guards(
        self,
        bookmaker_odd: float,
        math_prob: float
    ) -> Optional[str]:
        """
        Apply safety guards to reject obviously bad bets.
        
        Args:
            bookmaker_odd: Decimal bookmaker odd
            math_prob: Mathematical probability (0-1)
            
        Returns:
            None if safe, otherwise reason for violation
        """
        # Safety: Reject odds too close to 1.0 (too risky/low reward)
        if bookmaker_odd <= SAFETY_MIN_ODDS:
            return f"Odds too low ({bookmaker_odd:.2f} <= {SAFETY_MIN_ODDS})"
        
        # Safety: Clamp probability - no certainty exists in sports
        if math_prob >= SAFETY_MAX_PROB:
            return f"Probability too high ({math_prob:.2f} >= {SAFETY_MAX_PROB})"
        
        return None
    
    def _apply_market_veto(
        self,
        match: Match,
        analysis: NewsLog,
        edge_result: EdgeResult
    ) -> Optional[VetoReason]:
        """
        Apply the 15% Market Veto (Value Guard).
        
        If odds have dropped >= 15%, the market has already priced in
        the news, so there's no value left.
        
        Args:
            match: Match database object
            analysis: NewsLog analysis object
            edge_result: Edge calculation result
            
        Returns:
            VetoReason if vetoed, None otherwise
        """
        # Extract odds drop from analysis summary or match data
        odds_drop = 0.0
        
        # Try to extract from analysis summary
        summary = getattr(analysis, 'summary', '')
        if summary and 'dropped' in summary.lower():
            import re
            drop_match = re.search(r'dropped\s+(\d+(?:\.\d+)?)\s*%', summary, re.IGNORECASE)
            if drop_match:
                odds_drop = float(drop_match.group(1)) / 100.0
        
        # Try to extract from match odds
        if odds_drop == 0.0 and match:
            opening_odd = getattr(match, 'opening_home_odd', None)
            current_odd = getattr(match, 'current_home_odd', None)
            if opening_odd and current_odd and opening_odd > 0:
                odds_drop = (opening_odd - current_odd) / opening_odd
        
        # Apply veto if drop >= 15%
        if odds_drop >= MARKET_VETO_THRESHOLD:
            self.logger.info(
                f"🛑 MARKET VETO: Odds dropped {odds_drop*100:.1f}% "
                f"(>={MARKET_VETO_THRESHOLD*100:.0f}%), value is gone"
            )
            return VetoReason.MARKET_CRASHED
        
        return None
    
    def _apply_stake_capping(self, kelly_stake: float) -> float:
        """
        Apply stake capping rules (0.5% - 5.0%).
        
        Args:
            kelly_stake: Kelly stake percentage
            
        Returns:
            Capped stake percentage
        """
        # Safety caps: Min 0.5%, Max 5.0% (hard caps)
        capped = max(MIN_STAKE_PCT, min(MAX_STAKE_PCT, kelly_stake))
        
        if capped != kelly_stake:
            self.logger.debug(
                f"Stake capped: {kelly_stake:.2f}% -> {capped:.2f}% "
                f"(min={MIN_STAKE_PCT}%, max={MAX_STAKE_PCT}%)"
            )
        
        return capped
    
    def _apply_volatility_guard(
        self,
        stake: float,
        bookmaker_odd: float
    ) -> Tuple[bool, float]:
        """
        Apply volatility guard for high odds (> 4.50).
        
        High odds are more volatile, so we reduce the stake by 50%.
        
        Args:
            stake: Stake percentage
            bookmaker_odd: Decimal bookmaker odd
            
        Returns:
            Tuple of (adjusted: bool, final_stake: float)
        """
        if bookmaker_odd > VOLATILITY_GUARD_ODDS:
            adjusted_stake = stake * 0.5
            self.logger.debug(
                f"Volatility guard: Odds {bookmaker_odd:.2f} > {VOLATILITY_GUARD_ODDS:.2f}, "
                f"reducing stake by 50%: {stake:.2f}% -> {adjusted_stake:.2f}%"
            )
            return True, adjusted_stake
        
        return False, stake
    
    def _calculate_balanced_probability(
        self,
        math_prob: float,
        ai_prob: Optional[float],
        edge_result: EdgeResult
    ) -> float:
        """
        Calculate balanced probability (Poisson + AI Confidence).
        
        This dampens AI over-optimism and balances quantitative
        + qualitative analysis.
        
        Args:
            math_prob: Mathematical probability (0-1)
            ai_prob: AI confidence probability (0-1)
            edge_result: Edge calculation result
            
        Returns:
            Balanced probability (0-1)
        """
        # V5.1 FIX: Correct balanced probability calculation using ai_prob
        # If ai_prob is provided, average math_prob with ai_prob
        # Otherwise, fall back to using effective_prob as proxy
        if ai_prob is not None and math_prob < SAFETY_MAX_PROB:
            return (math_prob + ai_prob) / 2
        elif math_prob < SAFETY_MAX_PROB:
            # Use edge_result's implied prob as proxy for effective_prob
            implied_prob = edge_result.implied_prob / 100.0
            return (math_prob + implied_prob) / 2
        else:
            return math_prob
    
    def _calculate_confidence(
        self,
        analysis: NewsLog,
        edge_result: EdgeResult,
        balanced_prob: float
    ) -> float:
        """
        Calculate overall confidence score.
        
        Combines analysis score, edge magnitude, and balanced probability.
        
        Args:
            analysis: NewsLog analysis object
            edge_result: Edge calculation result
            balanced_prob: Balanced probability (0-1)
            
        Returns:
            Confidence score (0-100)
        """
        # Base confidence from analysis score
        analysis_score = getattr(analysis, 'score', 0.0)
        
        # Boost confidence based on edge magnitude
        edge_boost = min(20.0, edge_result.edge * 2.0)
        
        # Boost confidence based on balanced probability
        prob_boost = min(15.0, balanced_prob * 30.0)
        
        # Calculate final confidence
        confidence = analysis_score + edge_boost + prob_boost
        
        # Cap at 100
        return min(100.0, max(0.0, confidence))
    
    def _get_market_name(self, market_key: str) -> str:
        """Get human-readable market name."""
        names = {
            'home': 'HOME_WIN',
            'draw': 'DRAW',
            'away': 'AWAY_WIN',
            'over_25': 'OVER_2.5_GOALS',
            'under_25': 'UNDER_2.5_GOALS',
            'btts': 'BTTS'
        }
        return names.get(market_key, market_key.upper())
    
    def _get_primary_market(self, market_key: str) -> str:
        """Get primary market identifier."""
        primary = {
            'home': '1',
            'draw': 'X',
            'away': '2',
            'over_25': 'Over 2.5 Goals',
            'under_25': 'Under 2.5 Goals',
            'btts': 'BTTS'
        }
        return primary.get(market_key, market_key.upper())
    
    # ============================================
    # DECISION FACTORY METHODS
    # ============================================
    
    def _create_no_bet_decision(
        self,
        reason: str,
        market_odds: Dict[str, float],
        poisson_result: Optional[PoissonResult] = None
    ) -> BettingDecision:
        """Create a NO BET decision."""
        return BettingDecision(
            should_bet=False,
            verdict="NO BET",
            confidence=0.0,
            recommended_market="NONE",
            primary_market="NONE",
            math_prob=0.0,
            implied_prob=0.0,
            edge=0.0,
            fair_odd=0.0,
            actual_odd=market_odds.get('home', 0.0),
            kelly_stake=0.0,
            final_stake=0.0,
            veto_reason=VetoReason.NO_VALUE,
            safety_violation=reason,
            volatility_adjusted=False,
            poisson_result=poisson_result,
            balanced_prob=0.0,
            ai_prob=None
        )
    
    def _create_vetoed_decision(
        self,
        veto_reason: VetoReason,
        veto_detail: str,
        edge_result: EdgeResult,
        poisson_result: PoissonResult,
        market_odds: Dict[str, float],
        ai_prob: Optional[float]
    ) -> BettingDecision:
        """Create a vetoed NO BET decision."""
        return BettingDecision(
            should_bet=False,
            verdict="NO BET",
            confidence=0.0,
            recommended_market=edge_result.market,
            primary_market=self._get_primary_market(edge_result.market.lower()),
            math_prob=edge_result.math_prob,
            implied_prob=edge_result.implied_prob,
            edge=edge_result.edge,
            fair_odd=edge_result.fair_odd,
            actual_odd=edge_result.actual_odd,
            kelly_stake=0.0,
            final_stake=0.0,
            veto_reason=veto_reason,
            safety_violation=veto_detail,
            volatility_adjusted=False,
            poisson_result=poisson_result,
            balanced_prob=(edge_result.math_prob / 100.0 + ai_prob) / 2 if ai_prob else edge_result.math_prob / 100.0,
            ai_prob=ai_prob * 100.0 if ai_prob else None
        )
    
    def _create_no_value_decision(
        self,
        edge_result: EdgeResult,
        poisson_result: PoissonResult,
        market_odds: Dict[str, float],
        ai_prob: Optional[float]
    ) -> BettingDecision:
        """Create a NO VALUE decision."""
        return BettingDecision(
            should_bet=False,
            verdict="NO BET",
            confidence=0.0,
            recommended_market=edge_result.market,
            primary_market=self._get_primary_market(edge_result.market.lower()),
            math_prob=edge_result.math_prob,
            implied_prob=edge_result.implied_prob,
            edge=edge_result.edge,
            fair_odd=edge_result.fair_odd,
            actual_odd=edge_result.actual_odd,
            kelly_stake=0.0,
            final_stake=0.0,
            veto_reason=VetoReason.NO_VALUE,
            safety_violation="No edge detected",
            volatility_adjusted=False,
            poisson_result=poisson_result,
            balanced_prob=(edge_result.math_prob / 100.0 + ai_prob) / 2 if ai_prob else edge_result.math_prob / 100.0,
            ai_prob=ai_prob * 100.0 if ai_prob else None
        )


# ============================================
# FACTORY FUNCTION
# ============================================

def get_betting_quant(league_avg: float = 1.35, league_key: str = None) -> BettingQuant:
    """
    Factory function to get a Betting Quant instance.
    
    Args:
        league_avg: Average goals per team per match in the league
        league_key: League identifier for league-specific adjustments
        
    Returns:
        BettingQuant instance
    """
    return BettingQuant(league_avg=league_avg, league_key=league_key)
