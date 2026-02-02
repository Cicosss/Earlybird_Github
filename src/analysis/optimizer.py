"""
Quantitative Strategy Optimizer for EarlyBird V3.0
Advanced Portfolio Management with Risk-Adjusted Metrics.

Features:
- League + Market + Driver granular tracking
- Sharpe Ratio calculation for risk-adjusted performance
- Max Drawdown tracking for stability analysis
- Sample Size Shrinkage (confidence grows with data)
- Volatility Penalty (penalize high-variance strategies)
- Drawdown Brake (emergency cut on losing streaks)
- Persistent JSON storage for crash recovery

V6.1 Fixes:
- Regex patterns compiled at module level (performance)
- Driver weights now use State Machine (consistency)
- Weight combination uses signal-strength based logic (not geometric mean)
- PnL aggregation uses weighted average for drawdown (correctness)
- Fallback to global Market weight when League×Market is FROZEN
"""
import json
import logging
import math
import os
import re
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Import safe access utilities
from src.utils.validators import safe_get

# Default weights file path
WEIGHTS_FILE = "data/optimizer_weights.json"

# ============================================
# QUANTITATIVE CONSTRAINTS V5.0 (Sample Size Guards)
# ============================================
# V5.0 CRITICAL FIX: Increased sample sizes to prevent overfitting
# Research shows: n=8 causes severe overfitting, n=30 minimum for stability

MIN_SAMPLE_SIZE = 30          # V5.0: Minimum bets before ANY adaptation (was 8)
WARMING_SAMPLE_SIZE = 50      # V5.0: Full flexibility only after 50 samples
CONFIDENCE_SAMPLE = 50        # V5.0: Full confidence at 50 samples (was 30)
MIN_WEIGHT = 0.2              # Never go to zero (always some chance)
MAX_WEIGHT = 2.0              # Never more than 2x
NEUTRAL_WEIGHT = 1.0          # Default weight
SORTINO_PENALTY_THRESHOLD = 1.5  # V4.3: Penalize if Sortino < 1.5 (was Sharpe < 0.5)
DRAWDOWN_BRAKE_THRESHOLD = -0.20  # Emergency cut at -20% drawdown

# V5.3: History size limits (extracted from magic numbers)
MAX_RETURNS_HISTORY = 100         # Max individual bet returns to keep
MAX_PNL_HISTORY = 100             # Max cumulative PnL points to keep

# V5.0: Optimizer State Machine
# FROZEN: < 30 bets → weights locked at 1.0, no adjustments
# WARMING_UP: 30-50 bets → minor adjustments only (±0.1 max)
# ACTIVE: 50+ bets → full optimization enabled
from enum import Enum

class OptimizerState(Enum):
    FROZEN = "frozen"           # < MIN_SAMPLE_SIZE bets
    WARMING_UP = "warming_up"   # MIN_SAMPLE_SIZE to WARMING_SAMPLE_SIZE
    ACTIVE = "active"           # >= WARMING_SAMPLE_SIZE bets

# Market type categories (order matters - more specific first)
MARKET_CATEGORIES = {
    "OVER": ["over 2.5", "over 1.5", "over 0.5", "over 3.5", "over2.5", "over1.5", "over goals"],
    "UNDER": ["under 2.5", "under 0.5", "under 3.5", "under2.5", "under goals"],
    "BTTS": ["btts", "both teams to score", "both teams"],
    "DOUBLE_CHANCE": ["1x", "x2", "12", "double chance"],
    "CARDS": ["over cards", "cards", "yellow", "booking"],
    "CORNERS": ["over corners", "corners", "corner"],
    "1X2": ["home win", "away win", "draw", "home", "away"],
    # V7.4: Combo expansion types
    "COMBO_OVER_UNDER_GOALS": ["combo_over_under_goals"],
    "COMBO_OVER_UNDER_CORNERS": ["combo_over_under_corners"],
    "COMBO_OVER_UNDER_CARDS": ["combo_over_under_cards"],
    "COMBO_BTTS": ["combo_btts"],
}

# Valid primary drivers
VALID_DRIVERS = ["INJURY_INTEL", "SHARP_MONEY", "MATH_VALUE", "CONTEXT_PLAY", "CONTRARIAN", "UNKNOWN"]

# V6.1 FIX: Compile regex patterns at module level (performance optimization)
# Python caches up to 512 patterns, but explicit compilation is cleaner and faster
_OVER_PATTERN = re.compile(r'\bover\s+\d+\.?\d*\b', re.IGNORECASE)
_UNDER_PATTERN = re.compile(r'\bunder\s+\d+\.?\d*\b', re.IGNORECASE)


def categorize_market(market: str) -> str:
    """Categorize a market recommendation into a standard type.
    
    Uses case-insensitive matching with normalization to handle
    variations like "Over 2.5 Goals" vs "over 2.5".
    
    V5.3 FIX: Improved pattern matching for edge cases like "Over 0.5",
    single character markets ("1", "2", "X"), and combo markets.
    """
    if not market:
        return "UNKNOWN"
    
    # Normalize: lowercase, remove extra spaces, common variations
    market_normalized = market.lower().strip()
    market_normalized = market_normalized.replace(" goals", "")
    market_normalized = market_normalized.replace(" gol", "")
    
    # V5.3 FIX: Handle single character markets first (before removing dots)
    # "1" = Home Win, "2" = Away Win, "X" = Draw
    if market_normalized in ("1", "home"):
        return "1X2"
    if market_normalized in ("2", "away"):
        return "1X2"
    if market_normalized in ("x", "draw"):
        return "1X2"
    
    # V6.1 FIX: Use pre-compiled regex patterns (faster)
    over_match = _OVER_PATTERN.search(market_normalized)
    under_match = _UNDER_PATTERN.search(market_normalized)
    
    # Check for specific market types in the string
    if "corner" in market_normalized:
        return "CORNERS"
    if "card" in market_normalized or "yellow" in market_normalized or "booking" in market_normalized:
        return "CARDS"
    
    # Generic over/under (goals implied if no corner/card)
    if over_match:
        return "OVER"
    if under_match:
        return "UNDER"
    
    # Remove dots for keyword matching
    market_no_dots = market_normalized.replace(".", "")
    
    for category, keywords in MARKET_CATEGORIES.items():
        for keyword in keywords:
            keyword_normalized = keyword.lower().replace(".", "")
            if keyword_normalized in market_no_dots or market_no_dots in keyword_normalized:
                return category
    
    return "OTHER"


# ============================================
# QUANTITATIVE MATH FUNCTIONS
# ============================================

def calc_sharpe(returns: List[float]) -> float:
    """
    Calculate Sharpe Ratio (simplified, assuming risk-free rate = 0).
    
    Formula: mean(returns) / stdev(returns)
    
    Safety:
    - Returns 0.0 if len(returns) < 10
    - If stdev == 0 (perfectly consistent returns):
      - Returns 5.0 if avg_return > 0 (reward consistency!)
      - Returns 0.0 otherwise
    
    Args:
        returns: List of individual bet returns (e.g., [0.85, -1.0, 0.90, ...])
        
    Returns:
        Sharpe ratio (higher = better risk-adjusted return)
    """
    if len(returns) < 10:
        return 0.0
    
    n = len(returns)
    mean_return = sum(returns) / n
    
    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / n
    stdev = math.sqrt(variance)
    
    # Handle zero variance (perfectly consistent returns)
    if stdev == 0:
        # Reward consistent winners, penalize consistent losers
        if mean_return > 0:
            return 5.0  # High Sharpe for consistent profit
        return 0.0
    
    return mean_return / stdev


def calc_sortino(returns: List[float], target_return: float = 0.0) -> float:
    """
    Calculate Sortino Ratio - penalizes only DOWNSIDE volatility.
    
    V4.2 NEW: Superior to Sharpe for betting because winning big is NOT a risk.
    
    Formula: (mean_return - target) / downside_deviation
    
    Downside Deviation = sqrt(mean of squared negative deviations)
    
    Safety:
    - Returns 0.0 if len(returns) < 10
    - Returns 5.0 if no downside (all wins) and mean > 0
    - Returns 0.0 if downside_std == 0 and mean <= 0
    
    Args:
        returns: List of individual bet returns (e.g., [0.85, -1.0, 0.90, ...])
        target_return: Minimum acceptable return (default 0 = break-even)
        
    Returns:
        Sortino ratio (higher = better risk-adjusted return, penalizing only losses)
    """
    if len(returns) < 10:
        return 0.0
    
    n = len(returns)
    mean_return = sum(returns) / n
    
    # Calculate downside deviation (only negative returns below target)
    downside_returns = [r for r in returns if r < target_return]
    
    if not downside_returns:
        # No losses! Perfect strategy (so far)
        if mean_return > 0:
            return 5.0  # High Sortino for consistent profit with no downside
        return 0.0
    
    # Downside deviation = sqrt(mean of squared deviations below target)
    downside_variance = sum((r - target_return) ** 2 for r in downside_returns) / len(downside_returns)
    downside_std = math.sqrt(downside_variance)
    
    if downside_std == 0:
        return 0.0
    
    return (mean_return - target_return) / downside_std


def calc_max_drawdown(pnl_history: List[float]) -> float:
    """
    Calculate Maximum Drawdown from PnL history.
    
    Drawdown = (Peak - Trough) / Peak
    
    Safety:
    - Returns 0.0 if empty list
    - Returns 0.0 if no drawdown (always winning)
    - V5.2 FIX: Handles negative starting PnL correctly
    
    Args:
        pnl_history: Cumulative PnL at each point (e.g., [1.0, 0.5, 1.5, 0.8, ...])
        
    Returns:
        Max drawdown as negative decimal (e.g., -0.25 for 25% drawdown)
    """
    if not pnl_history:
        return 0.0
    
    # V5.2 FIX: Start from -inf to correctly track peak even with negative starts
    peak = float('-inf')
    max_dd = 0.0
    
    for pnl in pnl_history:
        if pnl > peak:
            peak = pnl
        
        # Only calculate drawdown if we have a positive peak
        # (drawdown from negative peak is meaningless in betting context)
        if peak > 0:
            drawdown = (pnl - peak) / peak
            if drawdown < max_dd:
                max_dd = drawdown
    
    return max_dd


def get_optimizer_state(n_samples: int) -> OptimizerState:
    """
    V5.0: Determine optimizer state based on sample size.
    
    State Machine:
    - FROZEN: < 30 bets → NO weight adjustments (prevent overfitting)
    - WARMING_UP: 30-50 bets → minor adjustments only (±0.1 max)
    - ACTIVE: 50+ bets → full optimization enabled
    
    Args:
        n_samples: Number of bets for this strategy/league/market
        
    Returns:
        OptimizerState enum value
    """
    if n_samples < MIN_SAMPLE_SIZE:
        return OptimizerState.FROZEN
    elif n_samples < WARMING_SAMPLE_SIZE:
        return OptimizerState.WARMING_UP
    else:
        return OptimizerState.ACTIVE


def calculate_advanced_weight(
    roi: float,
    sharpe: float,
    max_drawdown: float,
    n_samples: int,
    sortino: float = None,
    previous_weight: float = None
) -> float:
    """
    Calculate weight using advanced quantitative formula.
    
    V5.0 CRITICAL UPDATE: Sample Size Guards
    - FROZEN state (n < 30): Always return 1.0 (no adjustment)
    - WARMING_UP state (30-50): Limit adjustment to ±0.1 from previous
    - ACTIVE state (50+): Full optimization
    
    V4.3: Now uses Sortino Ratio as primary risk metric (better for betting).
    Sortino only penalizes downside volatility, not winning streaks.
    
    Formula (when ACTIVE):
    1. Base: Start at 1.0
    2. Sample Size Shrinkage: confidence_factor = min(1.0, n_samples / 50)
    3. Performance Impact: weight += (roi * 2.0) * confidence_factor
    4. Volatility Penalty: If sortino < 1.5 AND n_samples > 30: weight *= 0.8
    5. Drawdown Brake: If drawdown < -0.20: weight *= 0.5
    6. Clamp: max(0.2, min(2.0, weight))
    
    Args:
        roi: Return on Investment as decimal
        sharpe: Sharpe ratio (kept for backward compatibility)
        max_drawdown: Maximum drawdown (negative decimal)
        n_samples: Number of bets
        sortino: Sortino ratio (V4.3 - preferred metric)
        previous_weight: Previous weight value (for WARMING_UP state limiting)
        
    Returns:
        Calculated weight
    """
    # V5.0: Check optimizer state first
    state = get_optimizer_state(n_samples)
    
    # FROZEN: No adjustments allowed - return neutral weight
    if state == OptimizerState.FROZEN:
        logger.debug(f"🔒 FROZEN state (n={n_samples}): weight locked at 1.0")
        return NEUTRAL_WEIGHT
    
    # Start at neutral
    weight = NEUTRAL_WEIGHT
    
    # Sample Size Shrinkage (confidence grows with data)
    confidence_factor = min(1.0, n_samples / CONFIDENCE_SAMPLE)
    
    # Performance Impact (ROI drives weight)
    weight += (roi * 2.0) * confidence_factor
    
    # V4.3: Volatility Penalty using Sortino (preferred) or Sharpe (fallback)
    # Sortino is better for betting because winning big is NOT a risk
    risk_metric = sortino if sortino is not None else sharpe
    risk_threshold = SORTINO_PENALTY_THRESHOLD if sortino is not None else 0.5
    
    # V5.0: Only apply volatility penalty if we have enough samples
    if risk_metric < risk_threshold and n_samples >= MIN_SAMPLE_SIZE:
        weight *= 0.8
        sortino_str = f"{sortino:.2f}" if sortino is not None else "N/A"
        logger.debug(f"Volatility penalty applied (Sortino={sortino_str}, Sharpe={sharpe:.2f})")
    
    # Drawdown Brake (emergency cut on losing streaks)
    # V5.0: Only activate if we have enough data to trust the drawdown calculation
    if max_drawdown < DRAWDOWN_BRAKE_THRESHOLD and n_samples >= MIN_SAMPLE_SIZE:
        weight *= 0.5
        logger.warning(f"⚠️ Drawdown brake activated (DD={max_drawdown*100:.1f}%)")
    
    # Clamp to valid range
    weight = max(MIN_WEIGHT, min(MAX_WEIGHT, weight))
    
    # V5.0: WARMING_UP state - limit adjustment magnitude
    if state == OptimizerState.WARMING_UP:
        prev = previous_weight if previous_weight is not None else NEUTRAL_WEIGHT
        max_delta = 0.1  # Maximum ±0.1 adjustment in warming state
        
        if weight > prev + max_delta:
            weight = prev + max_delta
            logger.debug(f"🌤️ WARMING_UP: capped increase to +0.1 (n={n_samples})")
        elif weight < prev - max_delta:
            weight = prev - max_delta
            logger.debug(f"🌤️ WARMING_UP: capped decrease to -0.1 (n={n_samples})")
    
    return round(weight, 3)


# ============================================
# STRATEGY OPTIMIZER CLASS
# ============================================

class StrategyOptimizer:
    """
    Quantitative Strategy Optimizer V3.0 with Sharpe & Drawdown.
    
    Tracks three dimensions:
    - League (e.g., soccer_turkey_super_league)
    - Market (e.g., OVER, 1X2, BTTS)
    - Driver (e.g., INJURY_INTEL, SHARP_MONEY)
    
    Data Structure:
    {
        "stats": {
            "soccer_turkey_super_league": {
                "OVER": {
                    "bets": 15, "wins": 10, "profit": 3.2, "roi": 0.21,
                    "returns": [0.85, -1.0, ...],  # Individual bet returns
                    "pnl_history": [0.85, -0.15, ...],  # Cumulative PnL
                    "sharpe": 0.65, "max_drawdown": -0.12, "weight": 1.2
                }
            }
        },
        "drivers": {
            "INJURY_INTEL": {"bets": 50, "wins": 30, "roi": 0.15, "weight": 1.1},
            "SHARP_MONEY": {"bets": 30, "wins": 20, "roi": 0.22, "weight": 1.2}
        },
        "global": {"total_bets": 100, "total_profit": 12.5, "overall_roi": 0.125},
        "version": "3.0"
    }
    """
    
    def __init__(self, weights_file: str = WEIGHTS_FILE):
        self.weights_file = weights_file
        self._data_lock = threading.Lock()  # V5.3: Thread safety for data operations
        
        # V7.3: Use weight cache for performance
        # CRITICAL: Only use cache for default weights file (production)
        # Tests use temp files, so bypass cache to avoid cross-test contamination
        global _weight_cache
        if weights_file == WEIGHTS_FILE:
            self.data = _weight_cache.get_data(self._load_data)
        else:
            # Test mode: load directly without cache
            self.data = self._load_data()
        
        total_bets = self.data.get('global', {}).get('total_bets', 0)
        logger.info(f"📊 Optimizer V3.0 initialized with {total_bets} historical bets")
    
    def _load_data(self) -> Dict:
        """Load data from file or return empty structure."""
        default = {
            "stats": {},
            "drivers": {},
            "global": {
                "total_bets": 0,
                "total_profit": 0.0,
                "overall_roi": 0.0
            },
            "version": "3.0",
            "last_updated": None
        }
        
        try:
            if os.path.exists(self.weights_file):
                with open(self.weights_file, 'r') as f:
                    loaded = json.load(f)
                    
                    # Check version and migrate if needed
                    version = loaded.get('version', '1.0')
                    if version != '3.0':
                        logger.info(f"📦 Migrating optimizer data from V{version} to V3.0")
                        return self._migrate_to_v3(loaded)
                    
                    logger.info(f"✅ Loaded optimizer data from {self.weights_file}")
                    return loaded
            else:
                logger.info("📝 No optimizer data found, starting fresh")
                return default
                
        except Exception as e:
            logger.error(f"Error loading optimizer data: {e}")
            return default
    
    def _migrate_to_v3(self, old_data: Dict) -> Dict:
        """Migrate older formats to V3.0."""
        new_data = {
            "stats": {},
            "drivers": {},
            "global": {
                # V7.0: Safe nested dictionary access with type checking
                "total_bets": safe_get(old_data, 'global', 'total_bets', default=0),
                "total_profit": safe_get(old_data, 'global', 'total_profit', default=0.0),
                "overall_roi": safe_get(old_data, 'global', 'overall_roi', default=0.0)
            },
            "version": "3.0",
            "last_updated": old_data.get('last_updated')
        }
        
        # Migrate stats with new fields
        for league, markets in old_data.get('stats', {}).items():
            new_data['stats'][league] = {}
            for market_type, stats in markets.items():
                new_data['stats'][league][market_type] = {
                    "bets": stats.get('bets', 0),
                    "wins": stats.get('wins', 0),
                    "profit": stats.get('profit', 0.0),
                    "roi": stats.get('roi', 0.0),
                    "returns": [],  # Will be populated going forward
                    "pnl_history": [],
                    "sharpe": 0.0,
                    "max_drawdown": 0.0,
                    "weight": stats.get('weight', NEUTRAL_WEIGHT)
                }
        
        return new_data
    
    def _save_data(self) -> bool:
        """
        Persist data to file using atomic write pattern.
        
        V4.1 FIX: Write to temp file first, then atomic rename.
        V5.3 FIX: Thread-safe with lock to prevent concurrent writes.
        V7.3 FIX: Update weight cache after successful save (only for production file).
        This prevents corruption if process crashes during write.
        """
        with self._data_lock:
            try:
                Path(self.weights_file).parent.mkdir(parents=True, exist_ok=True)
                self.data['last_updated'] = datetime.now(timezone.utc).isoformat()
                
                # Atomic write: temp file + rename
                temp_file = self.weights_file + '.tmp'
                
                with open(temp_file, 'w') as f:
                    json.dump(self.data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                
                # Atomic rename (overwrites existing file safely)
                os.replace(temp_file, self.weights_file)
                
                # V7.3: Update weight cache with new data (only for production file)
                global _weight_cache
                if self.weights_file == WEIGHTS_FILE:
                    _weight_cache.update_data(self.data)
                
                logger.info(f"💾 Saved optimizer data to {self.weights_file}")
                return True
            except Exception as e:
                logger.error(f"Error saving optimizer data: {e}")
                # Clean up temp file if it exists
                temp_file = self.weights_file + '.tmp'
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as cleanup_err:
                        logger.debug(f"Cleanup temp file fallito: {cleanup_err}")
                return False
    
    def _normalize_key(self, key: str) -> str:
        """Normalize string to key format."""
        return key.lower().replace(" ", "_").replace("-", "_")
    
    def _ensure_stats_structure(self, league_key: str, market_type: str) -> Dict:
        """Ensure stats structure exists and return it."""
        if league_key not in self.data['stats']:
            self.data['stats'][league_key] = {}
        
        if market_type not in self.data['stats'][league_key]:
            self.data['stats'][league_key][market_type] = {
                "bets": 0,
                "wins": 0,
                "profit": 0.0,
                "roi": 0.0,
                "returns": [],
                "pnl_history": [],
                "sharpe": 0.0,
                "sortino": 0.0,  # V5.2 FIX: Added to initial structure
                "max_drawdown": 0.0,
                "weight": NEUTRAL_WEIGHT
            }
        
        # Ensure new fields exist (for migrated data)
        stats = self.data['stats'][league_key][market_type]
        if 'returns' not in stats:
            stats['returns'] = []
        if 'pnl_history' not in stats:
            stats['pnl_history'] = []
        if 'sharpe' not in stats:
            stats['sharpe'] = 0.0
        if 'sortino' not in stats:
            stats['sortino'] = 0.0  # V4.2: Sortino Ratio
        if 'max_drawdown' not in stats:
            stats['max_drawdown'] = 0.0
        
        return stats
    
    def _ensure_driver_structure(self, driver: str) -> Dict:
        """Ensure driver structure exists and return it."""
        if driver not in self.data['drivers']:
            self.data['drivers'][driver] = {
                "bets": 0,
                "wins": 0,
                "profit": 0.0,
                "roi": 0.0,
                "returns": [],
                "sharpe": 0.0,
                "weight": NEUTRAL_WEIGHT
            }
        
        # Ensure new fields
        d = self.data['drivers'][driver]
        if 'returns' not in d:
            d['returns'] = []
        if 'sharpe' not in d:
            d['sharpe'] = 0.0
        if 'sortino' not in d:
            d['sortino'] = 0.0  # V4.2: Sortino Ratio
        
        return d
    
    def record_bet_result(
        self,
        league: str,
        market: str,
        outcome: str,
        odds: float = 1.9,
        driver: str = "UNKNOWN",
        expansion_type: str = None  # V7.4: Track combo expansion performance
    ) -> None:
        """
        Record a single bet result for learning.
        
        Args:
            league: League identifier
            market: Market recommendation
            outcome: "WIN", "LOSS", or "PUSH" (void/cancelled)
            odds: Decimal odds for the bet
            driver: Primary driver (INJURY_INTEL, SHARP_MONEY, etc.)
            expansion_type: V7.4 - Type of combo expansion for tracking
        """
        # V5.2 FIX: Validate required fields - skip if None/empty
        if not league or not market:
            logger.warning(f"⚠️ Skipping bet with missing league={league} or market={market}")
            return
        
        # V5.2 FIX: Validate outcome - only WIN/LOSS/PUSH are valid
        valid_outcomes = ("WIN", "LOSS", "PUSH")
        if outcome not in valid_outcomes:
            logger.warning(f"⚠️ Invalid outcome '{outcome}' for {league}/{market}, treating as LOSS")
            outcome = "LOSS"
        
        # V5.1 FIX: Skip PUSH outcomes - cancelled/postponed matches should not affect stats
        if outcome == "PUSH":
            logger.debug(f"⏭️ Skipping PUSH outcome for {league}/{market} (match cancelled/postponed)")
            return
        
        # V5.3 FIX: Convert odds to float if string, then validate
        try:
            odds = float(odds) if odds else 1.9
        except (TypeError, ValueError):
            logger.warning(f"⚠️ Invalid odds type {type(odds).__name__} for {league}/{market}, using default 1.9")
            odds = 1.9
        
        # V5.2 FIX: Validate odds - must be positive and reasonable
        if odds <= 1.0:
            logger.warning(f"⚠️ Invalid odds {odds} for {league}/{market}, using default 1.9")
            odds = 1.9
        elif odds > 100.0:
            logger.warning(f"⚠️ Suspiciously high odds {odds} for {league}/{market}, capping at 100.0")
            odds = 100.0
        
        league_key = self._normalize_key(league)
        market_type = categorize_market(market)
        
        # Validate driver
        if driver not in VALID_DRIVERS:
            driver = "UNKNOWN"
        
        # Get/create stats structures
        stats = self._ensure_stats_structure(league_key, market_type)
        driver_stats = self._ensure_driver_structure(driver)
        
        # Calculate return for this bet
        if outcome == "WIN":
            bet_return = odds - 1  # Net profit
        else:
            bet_return = -1.0  # Lost stake
        
        # Update league/market stats
        stats['bets'] += 1
        stats['returns'].append(bet_return)
        
        # Keep returns list manageable (last MAX_RETURNS_HISTORY)
        if len(stats['returns']) > MAX_RETURNS_HISTORY:
            stats['returns'] = stats['returns'][-MAX_RETURNS_HISTORY:]
        
        if outcome == "WIN":
            stats['wins'] += 1
        
        stats['profit'] += bet_return
        
        # Update PnL history (cumulative)
        last_pnl = stats['pnl_history'][-1] if stats['pnl_history'] else 0
        stats['pnl_history'].append(last_pnl + bet_return)
        
        # Keep PnL history manageable
        if len(stats['pnl_history']) > MAX_PNL_HISTORY:
            stats['pnl_history'] = stats['pnl_history'][-MAX_PNL_HISTORY:]
        
        # Recalculate metrics
        if stats['bets'] > 0:
            stats['roi'] = round(stats['profit'] / stats['bets'], 4)
        
        stats['sharpe'] = round(calc_sharpe(stats['returns']), 3)
        stats['sortino'] = round(calc_sortino(stats['returns']), 3)  # V4.2: Sortino Ratio
        stats['max_drawdown'] = round(calc_max_drawdown(stats['pnl_history']), 3)
        
        # V5.0: Get previous weight for WARMING_UP state limiting
        previous_weight = stats.get('weight', NEUTRAL_WEIGHT)
        
        # Recalculate weight - V5.0: Now with Sample Size Guards
        stats['weight'] = calculate_advanced_weight(
            stats['roi'],
            stats['sharpe'],
            stats['max_drawdown'],
            stats['bets'],
            sortino=stats['sortino'],
            previous_weight=previous_weight  # V5.0: For WARMING_UP state limiting
        )
        
        # V5.0: Log optimizer state for transparency
        state = get_optimizer_state(stats['bets'])
        if state != OptimizerState.ACTIVE:
            logger.info(f"   📊 {league_key}/{market_type}: {state.value} (n={stats['bets']}, weight={stats['weight']:.2f})")
        
        # V7.4: Record combo expansion performance if provided
        if expansion_type:
            self._record_expansion_performance(league_key, expansion_type, outcome, odds)
        
        # Update driver stats
        driver_stats['bets'] += 1
        driver_stats['returns'].append(bet_return)
        if len(driver_stats['returns']) > MAX_RETURNS_HISTORY:
            driver_stats['returns'] = driver_stats['returns'][-MAX_RETURNS_HISTORY:]
        
        if outcome == "WIN":
            driver_stats['wins'] += 1
        
        driver_stats['profit'] = driver_stats.get('profit', 0) + bet_return
        
        if driver_stats['bets'] > 0:
            driver_stats['roi'] = round(driver_stats['profit'] / driver_stats['bets'], 4)
        
        driver_stats['sharpe'] = round(calc_sharpe(driver_stats['returns']), 3)
        driver_stats['sortino'] = round(calc_sortino(driver_stats['returns']), 3)  # V4.2: Sortino
        
        # V6.1 FIX: Driver weights now use State Machine (same as league/market)
        # Previously: jumped directly from FROZEN to full adjustment (inconsistent)
        driver_state = get_optimizer_state(driver_stats['bets'])
        previous_driver_weight = driver_stats.get('weight', NEUTRAL_WEIGHT)
        
        if driver_state == OptimizerState.FROZEN:
            # No adjustment - keep neutral
            driver_stats['weight'] = NEUTRAL_WEIGHT
        elif driver_state == OptimizerState.WARMING_UP:
            # Limited adjustment: ±0.1 max
            raw_weight = NEUTRAL_WEIGHT + driver_stats['roi'] * 2.0
            raw_weight = max(MIN_WEIGHT, min(MAX_WEIGHT, raw_weight))
            max_delta = 0.1
            if raw_weight > previous_driver_weight + max_delta:
                driver_stats['weight'] = round(previous_driver_weight + max_delta, 3)
            elif raw_weight < previous_driver_weight - max_delta:
                driver_stats['weight'] = round(previous_driver_weight - max_delta, 3)
            else:
                driver_stats['weight'] = round(raw_weight, 3)
        else:  # ACTIVE
            # Full adjustment
            driver_stats['weight'] = round(
                max(MIN_WEIGHT, min(MAX_WEIGHT, NEUTRAL_WEIGHT + driver_stats['roi'] * 2.0)),
                3
            )
        
        # Update global stats
        self.data['global']['total_bets'] += 1
        self.data['global']['total_profit'] += bet_return
        
        total_bets = self.data['global']['total_bets']
        if total_bets > 0:
            self.data['global']['overall_roi'] = round(
                self.data['global']['total_profit'] / total_bets, 4
            )
    
    def get_weight(self, league: str, market: str, driver: str = None) -> Tuple[float, Dict]:
        """
        Get combined weight for league + market (+ optional driver).
        
        V6.1 FIX: Improved weight combination logic:
        - If League×Market is FROZEN, fallback to global Market weight
        - Weight combination uses signal-strength logic instead of geometric mean
        - Geometric mean was "annacquando" strong signals (e.g., 0.2 * 2.0 = 0.63)
        
        Args:
            league: League identifier
            market: Market recommendation
            driver: Optional primary driver
            
        Returns:
            Tuple of (combined_weight, stats_dict)
        """
        league_key = self._normalize_key(league)
        market_type = categorize_market(market)
        
        # V7.0: Safe nested dictionary access with type checking
        league_stats = safe_get(self.data, 'stats', league_key, default={})
        market_stats = league_stats.get(market_type, {})
        
        base_weight = market_stats.get('weight', NEUTRAL_WEIGHT)
        base_bets = market_stats.get('bets', 0)
        base_state = get_optimizer_state(base_bets)
        
        # V6.1 FIX: If League×Market is FROZEN, try global Market fallback
        if base_state == OptimizerState.FROZEN:
            global_market_weight, global_market_bets = self._get_global_market_weight(market_type)
            global_state = get_optimizer_state(global_market_bets)
            
            if global_state != OptimizerState.FROZEN:
                # Use global market weight as fallback
                base_weight = global_market_weight
                logger.debug(f"🔄 Fallback to global {market_type} weight: {base_weight:.2f} (n={global_market_bets})")
        
        # Apply driver weight if available
        if driver and driver in self.data.get('drivers', {}):
            driver_stats = self.data['drivers'][driver]
            driver_weight = driver_stats.get('weight', NEUTRAL_WEIGHT)
            driver_bets = driver_stats.get('bets', 0)
            driver_state = get_optimizer_state(driver_bets)
            
            # V6.1 FIX: Signal-strength based combination instead of geometric mean
            # If one weight is neutral (1.0), use the other weight
            # If both are non-neutral, use weighted average based on sample size
            combined = self._combine_weights(
                base_weight, base_bets,
                driver_weight, driver_bets
            )
            combined = max(MIN_WEIGHT, min(MAX_WEIGHT, combined))
            return round(combined, 3), market_stats
        
        return base_weight, market_stats
    
    def _get_global_market_weight(self, market_type: str) -> Tuple[float, int]:
        """
        V6.1: Calculate aggregate weight for a market type across ALL leagues.
        
        Used as fallback when League×Market combination is FROZEN.
        
        Returns:
            Tuple of (weighted_average_weight, total_bets)
        """
        total_bets = 0
        weighted_sum = 0.0
        
        for league, markets in self.data.get('stats', {}).items():
            if market_type in markets:
                stats = markets[market_type]
                bets = stats.get('bets', 0)
                weight = stats.get('weight', NEUTRAL_WEIGHT)
                
                # Only include strategies with enough data
                if bets >= MIN_SAMPLE_SIZE:
                    weighted_sum += weight * bets
                    total_bets += bets
        
        if total_bets == 0:
            return NEUTRAL_WEIGHT, 0
        
        return weighted_sum / total_bets, total_bets
    
    def _combine_weights(
        self,
        weight1: float, bets1: int,
        weight2: float, bets2: int
    ) -> float:
        """
        V6.1: Combine two weights using signal-strength logic.
        
        Logic:
        - If one is neutral (1.0), use the other
        - If both are non-neutral, weighted average by sample size
        - This prevents "annacquamento" of strong signals
        
        Example:
        - Old (geometric): sqrt(0.2 * 2.0) = 0.63 (strong driver signal lost)
        - New: If driver has more data, weight towards driver
        """
        # Check if weights are effectively neutral (within 0.05 of 1.0)
        is_neutral1 = abs(weight1 - NEUTRAL_WEIGHT) < 0.05
        is_neutral2 = abs(weight2 - NEUTRAL_WEIGHT) < 0.05
        
        if is_neutral1 and is_neutral2:
            return NEUTRAL_WEIGHT
        elif is_neutral1:
            return weight2
        elif is_neutral2:
            return weight1
        else:
            # Both non-neutral: weighted average by sample size
            # More data = more trust in that signal
            total_bets = bets1 + bets2
            if total_bets == 0:
                return NEUTRAL_WEIGHT
            return (weight1 * bets1 + weight2 * bets2) / total_bets
    
    def get_league_weight(self, league: str) -> float:
        """Get average weight across all markets for a league."""
        league_key = self._normalize_key(league)
        league_stats = self.data.get('stats', {}).get(league_key, {})
        
        if not league_stats:
            return NEUTRAL_WEIGHT
        
        weights = [m.get('weight', NEUTRAL_WEIGHT) for m in league_stats.values()]
        return sum(weights) / len(weights) if weights else NEUTRAL_WEIGHT
    
    def recalculate_weights(self, settlement_stats: Dict) -> bool:
        """
        Process settlement results and update weights.
        
        V7.3: Invalidates weight cache after recalculation to force reload.
        """
        if not settlement_stats or settlement_stats.get('settled', 0) == 0:
            logger.info("⏭️ No settled bets to learn from")
            return False
        
        logger.info("🧠 PROCESSING SETTLEMENT RESULTS (V3.0 Quant Engine)...")
        
        details = settlement_stats.get('details', [])
        if not details:
            return False
        
        updated_combos = set()
        
        for bet in details:
            league = bet.get('league', 'unknown')
            market = bet.get('market', 'unknown')
            outcome = bet.get('outcome', 'LOSS')
            odds = bet.get('odds', 1.9)
            driver = bet.get('driver', 'UNKNOWN')
            
            # V5.2 FIX: Skip invalid bets before processing
            if not league or not market:
                continue
            
            self.record_bet_result(league, market, outcome, odds, driver)
            
            league_key = self._normalize_key(league)
            market_type = categorize_market(market)
            updated_combos.add((league_key, market_type))
        
        # Log weight changes with Sharpe/Sortino/Drawdown
        logger.info("📊 WEIGHT UPDATES (with Risk Metrics V4.2):")
        for league_key, market_type in updated_combos:
            # V7.0: Safe nested dictionary access with type checking
            stats = safe_get(self.data, 'stats', league_key, market_type, default={})
            n_bets = stats.get('bets', 0)
            roi = stats.get('roi', 0)
            sharpe = stats.get('sharpe', 0)
            sortino = stats.get('sortino', 0)  # V4.2: Sortino
            max_dd = stats.get('max_drawdown', 0)
            weight = stats.get('weight', 1.0)
            
            if n_bets >= MIN_SAMPLE_SIZE:
                direction = "↑" if weight > 1.0 else "↓" if weight < 1.0 else "→"
                logger.info(
                    f"   {direction} {league_key}/{market_type}: "
                    f"W={weight:.2f} | ROI={roi*100:.1f}% | "
                    f"Sharpe={sharpe:.2f} | Sortino={sortino:.2f} | DD={max_dd*100:.1f}% | n={n_bets}"
                )
        
        # Log driver performance
        logger.info("📊 DRIVER PERFORMANCE:")
        for driver, d_stats in self.data.get('drivers', {}).items():
            if d_stats.get('bets', 0) >= 5:
                logger.info(
                    f"   🎯 {driver}: W={d_stats.get('weight', 1.0):.2f} | "
                    f"ROI={d_stats.get('roi', 0)*100:.1f}% | "
                    f"Sortino={d_stats.get('sortino', 0):.2f} | n={d_stats.get('bets', 0)}"
                )
        
        # Save to disk (also updates cache)
        self._save_data()
        
        total = self.data['global']['total_bets']
        overall_roi = self.data['global']['overall_roi']
        logger.info(f"✅ Optimizer V3.0 updated. Total: {total} bets | Overall ROI: {overall_roi*100:.1f}%")
        
        return True
    
    def apply_weight_to_score(
        self,
        base_score: float,
        league: str,
        market: str = None,
        driver: str = None
    ) -> Tuple[float, str]:
        """Apply learned weight to a confidence score.
        
        V5.3 FIX: Added validation for league parameter.
        """
        if not market:
            return base_score, ""
        
        # V5.3 FIX: Validate league parameter
        if not league:
            logger.debug("⚠️ apply_weight_to_score called with empty league")
            return base_score, ""
        
        weight, stats = self.get_weight(league, market, driver)
        
        if weight == NEUTRAL_WEIGHT:
            return base_score, ""
        
        adjusted = base_score * weight
        adjusted = max(0, min(10, adjusted))
        
        n_bets = stats.get('bets', 0)
        roi = stats.get('roi', 0)
        sharpe = stats.get('sharpe', 0)
        market_type = categorize_market(market)
        
        log_msg = (
            f"⚖️ OPTIMIZER: {weight:.2f}x on {market_type}/{league} "
            f"(ROI={roi*100:.1f}%, Sharpe={sharpe:.2f}, n={n_bets})"
        )
        
        return round(adjusted, 1), log_msg
    
    def get_summary(self) -> str:
        """Get human-readable summary with V5.0 Sample Size Guards status."""
        lines = ["📊 OPTIMIZER V5.0 SUMMARY (Sample Size Guards + Sortino)"]
        lines.append(f"Total bets: {self.data['global']['total_bets']}")
        lines.append(f"Overall ROI: {self.data['global']['overall_roi']*100:.1f}%")
        lines.append(f"Last updated: {self.data.get('last_updated', 'Never')}")
        
        # V5.0: Show state distribution
        frozen_count = 0
        warming_count = 0
        active_count = 0
        
        for league, markets in self.data.get('stats', {}).items():
            for market_type, stats in markets.items():
                n_bets = stats.get('bets', 0)
                state = get_optimizer_state(n_bets)
                if state == OptimizerState.FROZEN:
                    frozen_count += 1
                elif state == OptimizerState.WARMING_UP:
                    warming_count += 1
                else:
                    active_count += 1
        
        lines.append(f"\n🔒 State Distribution:")
        lines.append(f"   FROZEN (<{MIN_SAMPLE_SIZE} bets): {frozen_count} strategies")
        lines.append(f"   WARMING ({MIN_SAMPLE_SIZE}-{WARMING_SAMPLE_SIZE} bets): {warming_count} strategies")
        lines.append(f"   ACTIVE (>{WARMING_SAMPLE_SIZE} bets): {active_count} strategies")
        
        # Show adjusted weights (only ACTIVE strategies)
        adjusted = []
        for league, markets in self.data.get('stats', {}).items():
            for market_type, stats in markets.items():
                weight = stats.get('weight', 1.0)
                n_bets = stats.get('bets', 0)
                state = get_optimizer_state(n_bets)
                
                if state == OptimizerState.ACTIVE and weight != NEUTRAL_WEIGHT:
                    direction = "↑" if weight > 1.0 else "↓"
                    adjusted.append(
                        f"  {direction} {league}/{market_type}: "
                        f"W={weight:.2f} (Sortino={stats.get('sortino', 0):.2f}, n={n_bets})"
                    )
        
        if adjusted:
            lines.append("\n✅ Active adjustments (ACTIVE state only):")
            lines.extend(adjusted[:10])  # Limit output
        else:
            lines.append("\n⏳ No active adjustments yet (need more data)")
        
        return "\n".join(lines)
    
    def get_optimizer_state_report(self) -> Dict:
        """
        V5.0: Get detailed state report for all strategies.
        
        Returns:
            Dict with frozen, warming, active lists and counts
        """
        report = {
            'frozen': [],
            'warming': [],
            'active': [],
            'total_strategies': 0
        }
        
        for league, markets in self.data.get('stats', {}).items():
            for market_type, stats in markets.items():
                n_bets = stats.get('bets', 0)
                state = get_optimizer_state(n_bets)
                
                entry = {
                    'league': league,
                    'market': market_type,
                    'bets': n_bets,
                    'weight': stats.get('weight', 1.0),
                    'roi': stats.get('roi', 0),
                    'sortino': stats.get('sortino', 0)
                }
                
                if state == OptimizerState.FROZEN:
                    entry['bets_needed'] = MIN_SAMPLE_SIZE - n_bets
                    report['frozen'].append(entry)
                elif state == OptimizerState.WARMING_UP:
                    entry['bets_to_active'] = WARMING_SAMPLE_SIZE - n_bets
                    report['warming'].append(entry)
                else:
                    report['active'].append(entry)
                
                report['total_strategies'] += 1
        
        return report
    
    def get_risky_combinations(self, threshold: float = -0.1) -> list:
        """Get league/market combinations with negative ROI or high drawdown."""
        risky = []
        for league, markets in self.data.get('stats', {}).items():
            for market_type, stats in markets.items():
                n_bets = stats.get('bets', 0)
                # V5.0: Only flag as risky if we have enough data to trust the metrics
                is_risky = (
                    (stats.get('roi', 0) < threshold and n_bets >= MIN_SAMPLE_SIZE) or
                    (stats.get('max_drawdown', 0) < DRAWDOWN_BRAKE_THRESHOLD and n_bets >= MIN_SAMPLE_SIZE)
                )
                if is_risky:
                    risky.append({
                        'league': league,
                        'market': market_type,
                        'roi': stats['roi'],
                        'sharpe': stats.get('sharpe', 0),
                        'sortino': stats.get('sortino', 0),
                        'max_drawdown': stats.get('max_drawdown', 0),
                        'bets': n_bets,
                        'weight': stats['weight'],
                        'state': get_optimizer_state(n_bets).value
                    })
        return sorted(risky, key=lambda x: x['roi'])
    
    def _record_expansion_performance(self, league_key: str, expansion_type: str, outcome: str, odds: float) -> None:
        """
        V7.4: Record performance for combo expansion types.
        
        This creates a separate performance tracking system for expansion types
        that can be used to inform future combo suggestions.
        """
        if 'expansion_stats' not in self.data:
            self.data['expansion_stats'] = {}
        
        expansion_stats = self.data['expansion_stats']
        
        # Initialize expansion type if not exists
        if expansion_type not in expansion_stats:
            expansion_stats[expansion_type] = self._get_default_expansion_stats()
        
        stats = expansion_stats[expansion_type]
        
        # Skip invalid outcomes
        if outcome not in ("WIN", "LOSS"):
            return
        
        # Update basic stats
        stats['bets'] += 1
        if outcome == "WIN":
            stats['wins'] += 1
        
        # Calculate return
        bet_return = odds - 1.0 if outcome == "WIN" else -1.0
        stats['returns'].append(bet_return)
        
        # Keep returns manageable
        if len(stats['returns']) > MAX_RETURNS_HISTORY:
            stats['returns'] = stats['returns'][-MAX_RETURNS_HISTORY:]
        
        stats['profit'] += bet_return
        
        # Update PnL history
        last_pnl = stats['pnl_history'][-1] if stats['pnl_history'] else 0
        stats['pnl_history'].append(last_pnl + bet_return)
        
        if len(stats['pnl_history']) > MAX_PNL_HISTORY:
            stats['pnl_history'] = stats['pnl_history'][-MAX_PNL_HISTORY:]
        
        # Recalculate metrics
        if stats['bets'] > 0:
            stats['roi'] = round(stats['profit'] / stats['bets'], 4)
            stats['win_rate'] = round(stats['wins'] / stats['bets'], 3)
        
        stats['sharpe'] = round(calc_sharpe(stats['returns']), 3)
        stats['sortino'] = round(calc_sortino(stats['returns']), 3)
        stats['max_drawdown'] = round(calc_max_drawdown(stats['pnl_history']), 3)
        
        # Log significant expansion performance
        if stats['bets'] % 10 == 0:  # Every 10 bets
            logger.info(f"🧩 Expansion {expansion_type}: {stats['wins']}/{stats['bets']} ({stats['win_rate']*100:.1f}%) | ROI: {stats['roi']*100:.1f}%")
    
    def _get_default_expansion_stats(self) -> Dict:
        """V7.4: Default stats structure for expansion types."""
        return {
            'bets': 0,
            'wins': 0,
            'profit': 0.0,
            'roi': 0.0,
            'win_rate': 0.0,
            'sharpe': 0.0,
            'sortino': 0.0,
            'max_drawdown': 0.0,
            'returns': [],
            'pnl_history': []
        }
    
    def get_expansion_performance(self, expansion_type: str = None) -> Dict:
        """
        V7.4: Get performance stats for expansion types.
        
        Args:
            expansion_type: Specific expansion type or None for all
            
        Returns:
            Performance statistics dictionary
        """
        if 'expansion_stats' not in self.data:
            return {}
        
        if expansion_type:
            return self.data['expansion_stats'].get(expansion_type, {})
        
        return self.data['expansion_stats']
    
    def get_best_expansions_for_league(self, league_key: str, top_n: int = 3) -> List[Tuple[str, float]]:
        """
        V7.4: Get best performing expansion types for a specific league.
        
        Returns list of (expansion_type, performance_score) tuples.
        """
        if 'expansion_stats' not in self.data:
            return []
        
        expansion_scores = []
        for exp_type, stats in self.data['expansion_stats'].items():
            if stats['bets'] >= MIN_SAMPLE_SIZE:  # Only consider reliable data
                # Performance score combines ROI, win rate, and Sharpe
                score = (
                    stats['roi'] * 0.4 +  # 40% weight on ROI
                    stats['win_rate'] * 0.3 +  # 30% weight on win rate  
                    (stats['sharpe'] / 10) * 0.3  # 30% weight on risk-adjusted returns
                )
                expansion_scores.append((exp_type, score))
        
        # Sort by score descending and return top N
        expansion_scores.sort(key=lambda x: x[1], reverse=True)
        return expansion_scores[:top_n]


# ============================================
# V7.3: IN-MEMORY WEIGHT CACHE (Performance Optimization)
# ============================================
# Problema: get_weight() legge JSON da disco ogni volta (I/O overhead)
# Soluzione: Cache in-memory con invalidazione post-settlement
# Beneficio: 1-2s risparmiati per ciclo (50+ letture JSON → 1 lettura)

class OptimizerWeightCache:
    """
    In-memory cache for optimizer weights with settlement-based invalidation.
    
    Thread-safe cache that eliminates repeated JSON file reads during analysis cycles.
    Weights are cached until explicitly invalidated after nightly settlement.
    """
    
    def __init__(self):
        self._cached_data: Optional[Dict] = None
        self._cache_timestamp: Optional[datetime] = None
        self._lock = threading.Lock()
        logger.debug("📦 [OPTIMIZER-CACHE] Weight cache initialized")
    
    def get_data(self, loader_func) -> Dict:
        """
        Get cached data or load from disk if cache is empty.
        
        Args:
            loader_func: Function to call if cache miss (loads from JSON)
            
        Returns:
            Optimizer data dict
        """
        with self._lock:
            if self._cached_data is None:
                logger.debug("📦 [OPTIMIZER-CACHE] Cache MISS - loading from disk")
                self._cached_data = loader_func()
                self._cache_timestamp = datetime.now(timezone.utc)
            else:
                logger.debug("📦 [OPTIMIZER-CACHE] Cache HIT - using in-memory data")
            
            return self._cached_data
    
    def invalidate(self) -> None:
        """
        Invalidate cache (called after settlement updates weights).
        
        This forces next get_data() call to reload from disk.
        """
        with self._lock:
            if self._cached_data is not None:
                logger.info("🔄 [OPTIMIZER-CACHE] Cache invalidated (settlement update)")
                self._cached_data = None
                self._cache_timestamp = None
    
    def update_data(self, new_data: Dict) -> None:
        """
        Update cache with new data (called after in-memory modifications).
        
        Args:
            new_data: Updated optimizer data dict
        """
        with self._lock:
            self._cached_data = new_data
            self._cache_timestamp = datetime.now(timezone.utc)
            logger.debug("📦 [OPTIMIZER-CACHE] Cache updated with new data")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            return {
                'cached': self._cached_data is not None,
                'timestamp': self._cache_timestamp.isoformat() if self._cache_timestamp else None,
                'age_seconds': (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds() 
                              if self._cache_timestamp else None
            }


# Global weight cache instance
_weight_cache = OptimizerWeightCache()


# Singleton instance with thread-safe initialization
_optimizer_instance: Optional[StrategyOptimizer] = None
_optimizer_lock = threading.Lock()


def get_optimizer() -> StrategyOptimizer:
    """Get or create the singleton optimizer instance (thread-safe)."""
    global _optimizer_instance
    if _optimizer_instance is None:
        with _optimizer_lock:
            # Double-check locking pattern
            if _optimizer_instance is None:
                _optimizer_instance = StrategyOptimizer()
    return _optimizer_instance


# ============================================
# DYNAMIC THRESHOLD V6.0
# ============================================
# Threshold adattivo basato su performance recente.
# Diventa più conservativo durante drawdown, più aggressivo con buon Sortino.

# Threshold bounds
ALERT_THRESHOLD_BASE = 9.0      # ELITE QUALITY: Base threshold for standard matches (was 8.6)
ALERT_THRESHOLD_MIN = 7.5      # Minimum threshold (Radar/Insider News)
ALERT_THRESHOLD_MAX = 9.0      # Maximum threshold (Elite Quality cap)

# Performance windows
DYNAMIC_THRESHOLD_LOOKBACK_DAYS = 14
DYNAMIC_THRESHOLD_MIN_BETS = 10




def get_dynamic_alert_threshold() -> Tuple[float, str]:
    """
    Calcola threshold dinamico basato su performance recente.
    
    V6.1 FIX: Drawdown calculation now uses weighted average of per-strategy
    drawdowns instead of concatenating PnL histories (which was incorrect).
    
    Logica:
    - Drawdown > 20%: threshold += 0.5 (più conservativo)
    - Drawdown > 10%: threshold += 0.2
    - Sortino > 1.5: threshold -= 0.3 (più aggressivo)
    - Sortino < 0.5: threshold += 0.2
    - Win rate < 40%: threshold += 0.3
    - Win rate > 60%: threshold -= 0.2
    
    Returns:
        Tuple of (threshold, explanation_string)
    """
    optimizer = get_optimizer()
    
    threshold = ALERT_THRESHOLD_BASE
    adjustments = []
    
    # Get global stats
    global_stats = optimizer.data.get('global', {})
    total_bets = global_stats.get('total_bets', 0)
    
    # Not enough data - return base threshold
    if total_bets < DYNAMIC_THRESHOLD_MIN_BETS:
        return threshold, f"Base threshold (n={total_bets} < {DYNAMIC_THRESHOLD_MIN_BETS})"
    
    # Calculate aggregate metrics from all active strategies
    all_returns = []
    total_wins = 0
    total_losses = 0
    
    # V6.1 FIX: Collect per-strategy drawdowns for weighted average
    # Old approach concatenated PnL histories which was mathematically incorrect
    strategy_drawdowns = []  # List of (drawdown, n_bets) tuples
    
    for league, markets in optimizer.data.get('stats', {}).items():
        for market_type, stats in markets.items():
            n_bets = stats.get('bets', 0)
            
            # Only include strategies with enough data
            if n_bets >= MIN_SAMPLE_SIZE:
                returns = stats.get('returns', [])
                all_returns.extend(returns)
                
                # V6.1 FIX: Collect per-strategy drawdown with weight
                strategy_dd = stats.get('max_drawdown', 0.0)
                strategy_drawdowns.append((strategy_dd, n_bets))
                
                total_wins += stats.get('wins', 0)
                total_losses += n_bets - stats.get('wins', 0)
    
    # Not enough aggregate data
    if len(all_returns) < DYNAMIC_THRESHOLD_MIN_BETS:
        return threshold, f"Base threshold (aggregate n={len(all_returns)} < {DYNAMIC_THRESHOLD_MIN_BETS})"
    
    # Calculate aggregate metrics
    aggregate_sortino = calc_sortino(all_returns) if len(all_returns) >= 10 else 0.0
    
    # V6.1 FIX: Weighted average of per-strategy drawdowns
    # This correctly reflects portfolio risk instead of fake sequential drawdown
    if strategy_drawdowns:
        total_weight = sum(bets for _, bets in strategy_drawdowns)
        if total_weight > 0:
            aggregate_drawdown = sum(dd * bets for dd, bets in strategy_drawdowns) / total_weight
        else:
            aggregate_drawdown = 0.0
    else:
        aggregate_drawdown = 0.0
    
    win_rate = total_wins / (total_wins + total_losses) if (total_wins + total_losses) > 0 else 0.5
    
    # Apply adjustments
    
    # 1. Drawdown adjustment (più conservativo durante perdite)
    if aggregate_drawdown < -0.20:
        threshold += 0.5
        adjustments.append(f"DD={aggregate_drawdown*100:.1f}%: +0.5")
    elif aggregate_drawdown < -0.10:
        threshold += 0.2
        adjustments.append(f"DD={aggregate_drawdown*100:.1f}%: +0.2")
    
    # 2. Sortino adjustment (risk-adjusted performance)
    if aggregate_sortino > 1.5:
        threshold -= 0.3
        adjustments.append(f"Sortino={aggregate_sortino:.2f}: -0.3")
    elif aggregate_sortino < 0.5 and len(all_returns) >= 20:
        threshold += 0.2
        adjustments.append(f"Sortino={aggregate_sortino:.2f}: +0.2")
    
    # 3. Win rate adjustment
    if win_rate < 0.40:
        threshold += 0.3
        adjustments.append(f"WR={win_rate*100:.0f}%: +0.3")
    elif win_rate > 0.60:
        threshold -= 0.2
        adjustments.append(f"WR={win_rate*100:.0f}%: -0.2")
    
    # Clamp to bounds
    threshold = max(ALERT_THRESHOLD_MIN, min(ALERT_THRESHOLD_MAX, threshold))
    
    # Build explanation
    if adjustments:
        explanation = f"Dynamic: {ALERT_THRESHOLD_BASE} -> {threshold:.1f} ({', '.join(adjustments)})"
    else:
        explanation = f"Base threshold {threshold:.1f} (no adjustments needed)"
    
    logger.info(f"[THRESHOLD] {explanation}")
    
    return round(threshold, 1), explanation
