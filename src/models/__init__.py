"""EarlyBird Models Package

Contains Pydantic schemas for data validation and type safety.
"""

from .schemas import GeminiResponse, OddsMovement, MatchAlert

__all__ = [
    "GeminiResponse",
    "OddsMovement",
    "MatchAlert",
]
