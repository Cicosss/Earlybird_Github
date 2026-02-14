"""EarlyBird Schemas Package

API schemas for data validation.
"""

from .perplexity_schemas import (
    # Enums
    RiskLevel,
    RefereeStrictness,
    BiscottoPotential,
    InjuryImpact,
    BTTSImpact,
    SignalLevel,
    CardsSignal,
    DataConfidence,
    MatchIntensity,
    # Models
    DeepDiveResponse,
    BettingStatsResponse,
    # JSON Schemas
    DEEP_DIVE_JSON_SCHEMA,
    BETTING_STATS_JSON_SCHEMA,
)

__all__ = [
    # Enums
    "RiskLevel",
    "RefereeStrictness",
    "BiscottoPotential",
    "InjuryImpact",
    "BTTSImpact",
    "SignalLevel",
    "CardsSignal",
    "DataConfidence",
    "MatchIntensity",
    # Models
    "DeepDiveResponse",
    "BettingStatsResponse",
    # JSON Schemas
    "DEEP_DIVE_JSON_SCHEMA",
    "BETTING_STATS_JSON_SCHEMA",
]
