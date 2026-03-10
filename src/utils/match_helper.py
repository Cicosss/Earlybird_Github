"""
Match Helper Utilities

This module provides helper functions for safely extracting Match object attributes
to reduce SQLAlchemy session detachment vulnerability on VPS deployment.

The "Trust validation error: Instance <Match at 0x...> is not bound to Session"
occurs when a Match object becomes detached from its SQLAlchemy session due to:
1. Connection pool recycling (after pool_recycle seconds)
2. Multiple threads accessing the database concurrently

This module provides a centralized solution to extract Match attributes immediately
using getattr() with default values. Note: getattr() doesn't prevent DetachedInstanceError,
but extracting attributes immediately when needed reduces the window of vulnerability.
The current approach works as long as the session is still active.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Try to import Match model, but handle gracefully if not available
try:
    from src.database.models import Match
except ImportError:
    Match = None


@dataclass
class MatchAttributes:
    """
    Data class to hold Match attributes extracted safely.

    This provides a clean interface for accessing Match attributes without
    worrying about session detachment issues.
    """

    # Basic match info
    match_id: Optional[int] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    league: Optional[str] = None
    start_time: Optional[datetime] = None

    # Opening odds
    opening_home_odd: Optional[float] = None
    opening_draw_odd: Optional[float] = None
    opening_away_odd: Optional[float] = None
    opening_over_2_5: Optional[float] = None
    opening_under_2_5: Optional[float] = None

    # Current odds
    current_home_odd: Optional[float] = None
    current_draw_odd: Optional[float] = None
    current_away_odd: Optional[float] = None
    current_over_2_5: Optional[float] = None
    current_under_2_5: Optional[float] = None


def extract_match_attributes(match: Any, attributes: Optional[list[str]] = None) -> MatchAttributes:
    """
    Safely extract Match attributes to reduce session detachment vulnerability window.

    This function uses getattr() with default values to extract Match attributes
    immediately when needed. Note: getattr() doesn't prevent DetachedInstanceError,
    but extracting attributes immediately reduces the window of vulnerability.
    The current approach works as long as the session is still active.

    Args:
        match: Match database object (or any object with Match-like attributes)
        attributes: List of specific attributes to extract. If None, extracts all common attributes.

    Returns:
        MatchAttributes data class with extracted attributes

    Example:
        >>> match_attrs = extract_match_attributes(match)
        >>> print(f"{match_attrs.home_team} vs {match_attrs.away_team}")

        >>> # Extract only specific attributes
        >>> match_attrs = extract_match_attributes(match, ["home_team", "away_team", "current_home_odd"])
    """
    if attributes is None:
        # Extract all common attributes
        return MatchAttributes(
            match_id=getattr(match, "id", None),
            home_team=getattr(match, "home_team", None),
            away_team=getattr(match, "away_team", None),
            league=getattr(match, "league", None),
            start_time=getattr(match, "start_time", None),
            opening_home_odd=getattr(match, "opening_home_odd", None),
            opening_draw_odd=getattr(match, "opening_draw_odd", None),
            opening_away_odd=getattr(match, "opening_away_odd", None),
            opening_over_2_5=getattr(match, "opening_over_2_5", None),
            opening_under_2_5=getattr(match, "opening_under_2_5", None),
            current_home_odd=getattr(match, "current_home_odd", None),
            current_draw_odd=getattr(match, "current_draw_odd", None),
            current_away_odd=getattr(match, "current_away_odd", None),
            current_over_2_5=getattr(match, "current_over_2_5", None),
            current_under_2_5=getattr(match, "current_under_2_5", None),
        )
    else:
        # Extract only specified attributes
        attrs = MatchAttributes()
        for attr in attributes:
            if hasattr(attrs, attr):
                setattr(attrs, attr, getattr(match, attr, None))
        return attrs


def extract_match_odds(match: Any) -> dict[str, Optional[float]]:
    """
    Safely extract Match odds to prevent session detachment issues.

    This is a convenience function for extracting only odds attributes.

    Args:
        match: Match database object (or any object with Match-like attributes)

    Returns:
        Dictionary with odds attributes

    Example:
        >>> odds = extract_match_odds(match)
        >>> market_odds = {
        ...     "home": odds["current_home_odd"],
        ...     "draw": odds["current_draw_odd"],
        ...     "away": odds["current_away_odd"],
        ... }
    """
    return {
        "opening_home_odd": getattr(match, "opening_home_odd", None),
        "opening_draw_odd": getattr(match, "opening_draw_odd", None),
        "opening_away_odd": getattr(match, "opening_away_odd", None),
        "opening_over_2_5": getattr(match, "opening_over_2_5", None),
        "opening_under_2_5": getattr(match, "opening_under_2_5", None),
        "current_home_odd": getattr(match, "current_home_odd", None),
        "current_draw_odd": getattr(match, "current_draw_odd", None),
        "current_away_odd": getattr(match, "current_away_odd", None),
        "current_over_2_5": getattr(match, "current_over_2_5", None),
        "current_under_2_5": getattr(match, "current_under_2_5", None),
    }


def extract_match_info(match: Any) -> dict[str, Any]:
    """
    Safely extract basic Match information to prevent session detachment issues.

    This is a convenience function for extracting only basic match attributes.

    Args:
        match: Match database object (or any object with Match-like attributes)

    Returns:
        Dictionary with basic match attributes

    Example:
        >>> info = extract_match_info(match)
        >>> print(f"{info['home_team']} vs {info['away_team']} ({info['league']})")
    """
    return {
        "match_id": getattr(match, "id", None),
        "home_team": getattr(match, "home_team", None),
        "away_team": getattr(match, "away_team", None),
        "league": getattr(match, "league", None),
        "start_time": getattr(match, "start_time", None),
        "last_deep_dive_time": getattr(match, "last_deep_dive_time", None),
    }
