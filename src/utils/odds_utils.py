"""
Odds Utilities Module

Shared utility functions for odds extraction and manipulation.
This module provides common functionality used across multiple files
to avoid code duplication (DRY principle).
"""

import logging

from config.settings import DEFAULT_ODDS_CARDS, DEFAULT_ODDS_CORNERS, DEFAULT_ODDS_GOALS

logger = logging.getLogger(__name__)


def get_market_odds(market: str, match) -> float | None:
    """
    Extract odds for a specific market from match data.

    This function extracts odds for various betting markets including:
    - Home Win, Away Win, Draw
    - Double Chance (1X, X2)
    - Over/Under, BTTS, Corners, Cards

    Args:
        market: The market name (e.g., "home win", "over 2.5 goals", "1x")
        match: Match object containing current odds fields:
            - current_home_odd: Current home win odds
            - current_away_odd: Current away win odds
            - current_draw_odd: Current draw odds

    Returns:
        float: The odds value for specified market, or None if not available
    """
    # VPS FIX: Extract Match attributes safely to prevent session detachment
    # This prevents "Trust validation error" when Match object becomes detached
    # from session due to connection pool recycling under high load
    current_home_odd = getattr(match, "current_home_odd", None)
    current_away_odd = getattr(match, "current_away_odd", None)
    current_draw_odd = getattr(match, "current_draw_odd", None)

    market_lower = market.lower()

    # Home Win
    if "home" in market_lower and "win" in market_lower:
        return current_home_odd if current_home_odd and current_home_odd > 1.0 else None

    # Away Win
    elif "away" in market_lower and "win" in market_lower:
        return current_away_odd if current_away_odd and current_away_odd > 1.0 else None

    # Draw
    elif "draw" in market_lower or market_lower == "x":
        return current_draw_odd if current_draw_odd and current_draw_odd > 1.0 else None

    # Double Chance 1X
    elif "1x" in market_lower:
        h = current_home_odd or 2.0
        d = current_draw_odd or 3.0
        return round(1 / ((1 / h) + (1 / d)), 2) if h > 1 and d > 1 else None

    # Double Chance X2
    elif "x2" in market_lower:
        d = current_draw_odd or 3.0
        a = current_away_odd or 2.5
        return round(1 / ((1 / d) + (1 / a)), 2) if d > 1 and a > 1 else None

    # Over/Under, BTTS, Corners, Cards
    elif "over" in market_lower or "under" in market_lower or "btts" in market_lower:
        if "corner" in market_lower:
            return DEFAULT_ODDS_CORNERS  # Typical corners market odds
        elif "card" in market_lower:
            return DEFAULT_ODDS_CARDS  # Typical cards market odds
        else:
            return DEFAULT_ODDS_GOALS  # Default for goals totals

    # Default fallback
    return None
