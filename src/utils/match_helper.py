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
    Enhanced data class for Match attributes with hybrid access patterns.

    This provides BOTH type-safe attribute access AND flexible dictionary composition
    to support the bot's intelligent component communication architecture.

    HYBRID ACCESS PATTERNS:
    1. Type-safe attribute access: attrs.home_team (IDE autocomplete, type checking)
    2. Dictionary-like access: attrs["home_team"] (flexible composition)
    3. Dictionary conversion: attrs.to_dict() (JSON serialization)
    4. Dictionary merging: attrs.update({"extra_field": value}) (component communication)

    This design enables gradual migration from dicts to type-safe code without breaking
    existing functionality, supporting the bot's flexible data composition needs.
    """

    # Basic match info
    match_id: Optional[str] = (
        None  # COVE FIX: Changed from Optional[int] to match Match.id type (String)
    )
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

    # Internal storage for extra fields (for flexible composition)
    _extra_fields: dict[str, Any] = None

    def __post_init__(self):
        """Initialize internal storage for extra fields."""
        if self._extra_fields is None:
            self._extra_fields = {}

    def __getitem__(self, key: str) -> Any:
        """
        Enable dictionary-like access for flexible composition.

        Supports both dataclass fields and extra fields added dynamically.
        This enables seamless integration with existing dict-based code.

        COVE FIX: Use __dataclass_fields__ to check for dataclass fields
        instead of hasattr() to prevent method names from being accessible
        as dictionary keys.
        """
        if key in self.__dataclass_fields__:
            # Access dataclass field
            return getattr(self, key)
        else:
            # Access extra field
            return self._extra_fields.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Enable dictionary-like assignment for flexible composition.

        Allows components to add custom fields without breaking type safety
        for the core fields.

        COVE FIX: Use __dataclass_fields__ to check for dataclass fields
        instead of hasattr() to prevent method names from being settable
        as dictionary keys.
        """
        if key in self.__dataclass_fields__:
            # Set dataclass field
            setattr(self, key, value)
        else:
            # Store in extra fields
            self._extra_fields[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Dictionary-like get method for safe access.

        Provides compatibility with dict.get() pattern used throughout the codebase.

        COVE FIX: Check if key exists before accessing to properly return
        default value when key is not found.
        """
        if key in self.__dataclass_fields__:
            return getattr(self, key)
        elif key in self._extra_fields:
            return self._extra_fields[key]
        else:
            return default

    def update(self, other: dict[str, Any]) -> None:
        """
        Update from dictionary for flexible composition.

        Enables merging data from multiple components, supporting the bot's
        intelligent component communication pattern.
        """
        for key, value in other.items():
            self[key] = value

    def to_dict(self, include_extra: bool = True) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Args:
            include_extra: Whether to include dynamically added extra fields

        Returns:
            Dictionary representation of this MatchAttributes object

        COVE FIX: Serialize datetime objects in _extra_fields to ISO format
        to ensure JSON serialization works correctly.
        """
        result = {}
        # Add dataclass fields
        for field_name in self.__dataclass_fields__:
            if field_name == "_extra_fields":
                continue
            value = getattr(self, field_name)
            # Handle datetime serialization
            if isinstance(value, datetime):
                result[field_name] = value.isoformat()
            else:
                result[field_name] = value

        # Add extra fields if requested
        if include_extra:
            for key, value in self._extra_fields.items():
                # COVE FIX: Serialize datetime objects in _extra_fields
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                else:
                    result[key] = value

        return result

    def keys(self) -> list[str]:
        """
        Return all available keys (dataclass fields + extra fields).

        Provides compatibility with dict.keys() pattern.
        """
        field_keys = [f for f in self.__dataclass_fields__ if f != "_extra_fields"]
        return field_keys + list(self._extra_fields.keys())

    def values(self) -> list[Any]:
        """
        Return all values (dataclass fields + extra fields).

        Provides compatibility with dict.values() pattern.
        """
        return [self[key] for key in self.keys()]

    def items(self) -> list[tuple[str, Any]]:
        """
        Return all key-value pairs.

        Provides compatibility with dict.items() pattern.
        """
        return [(key, self[key]) for key in self.keys()]

    def __contains__(self, key: str) -> bool:
        """
        Enable 'in' operator for key checking.

        Provides compatibility with 'key in dict' pattern.

        COVE FIX: Use __dataclass_fields__ to check for dataclass fields
        instead of hasattr() to prevent method names from being detected
        as valid keys.
        """
        return key in self.__dataclass_fields__ or key in self._extra_fields


def extract_match_attributes(match: Any, attributes: Optional[list[str]] = None) -> MatchAttributes:
    """
    Safely extract Match attributes to reduce session detachment vulnerability window.

    This function uses getattr() with default values to extract Match attributes
    immediately when needed. Note: getattr() doesn't prevent DetachedInstanceError,
    but extracting attributes immediately reduces the window of vulnerability.
    The current approach works as long as the session is still active.

    ENHANCED: Now returns MatchAttributes with hybrid access patterns:
    - Type-safe: attrs.home_team (IDE autocomplete)
    - Dictionary-like: attrs["home_team"] (flexible composition)
    - Conversion: attrs.to_dict() (JSON serialization)

    Args:
        match: Match database object (or any object with Match-like attributes)
        attributes: List of specific attributes to extract. If None, extracts all common attributes.

    Returns:
        MatchAttributes data class with hybrid access patterns

    Example:
        >>> match_attrs = extract_match_attributes(match)
        >>> # Type-safe access
        >>> print(f"{match_attrs.home_team} vs {match_attrs.away_team}")
        >>> # Dictionary-like access
        >>> print(f"{match_attrs['home_team']} vs {match_attrs['away_team']}")
        >>> # Flexible composition
        >>> match_attrs.update({"custom_field": "value"})
        >>> # JSON serialization
        >>> data = match_attrs.to_dict()

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


def extract_match_odds(match: Any) -> MatchAttributes:
    """
    Safely extract Match odds to prevent session detachment issues.

    ENHANCED: Now returns MatchAttributes with hybrid access patterns for
    better type safety while maintaining backward compatibility.

    Args:
        match: Match database object (or any object with Match-like attributes)

    Returns:
        MatchAttributes object with odds attributes (hybrid access)

    Example:
        >>> odds = extract_match_odds(match)
        >>> # Type-safe access
        >>> home_odd = odds.current_home_odd
        >>> # Dictionary-like access (backward compatible)
        >>> market_odds = {
        ...     "home": odds["current_home_odd"],
        ...     "draw": odds["current_draw_odd"],
        ...     "away": odds["current_away_odd"],
        ... }
        >>> # JSON serialization
        >>> odds_dict = odds.to_dict()
    """
    return MatchAttributes(
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


def extract_match_info(match: Any) -> MatchAttributes:
    """
    Safely extract basic Match information to prevent session detachment issues.

    ENHANCED: Now returns MatchAttributes with hybrid access patterns for
    better type safety while maintaining backward compatibility.

    Args:
        match: Match database object (or any object with Match-like attributes)

    Returns:
        MatchAttributes object with basic match attributes (hybrid access)

    Example:
        >>> info = extract_match_info(match)
        >>> # Type-safe access
        >>> print(f"{info.home_team} vs {info.away_team} ({info.league})")
        >>> # Dictionary-like access (backward compatible)
        >>> print(f"{info['home_team']} vs {info['away_team']} ({info['league']})")
        >>> # JSON serialization
        >>> info_dict = info.to_dict()
    """
    attrs = MatchAttributes(
        match_id=getattr(match, "id", None),
        home_team=getattr(match, "home_team", None),
        away_team=getattr(match, "away_team", None),
        league=getattr(match, "league", None),
        start_time=getattr(match, "start_time", None),
    )
    # Add last_deep_dive_time as extra field (not in core dataclass)
    attrs["last_deep_dive_time"] = getattr(match, "last_deep_dive_time", None)
    return attrs
