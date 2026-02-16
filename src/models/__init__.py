"""EarlyBird Models Package

Contains Pydantic schemas for data validation and type safety.
"""

from .schemas import GeminiResponse, MatchAlert, OddsMovement

__all__ = [
    "GeminiResponse",
    "OddsMovement",
    "MatchAlert",
]
