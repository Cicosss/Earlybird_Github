"""EarlyBird Schemas Package

API schemas for data validation.
"""

from .perplexity_schemas import (
    BETTING_STATS_JSON_SCHEMA,
    # JSON Schemas
    DEEP_DIVE_JSON_SCHEMA,
    BettingStatsResponse,
    BiscottoPotential,
    BTTSImpact,
    CardsSignal,
    DataConfidence,
    # Models
    DeepDiveResponse,
    InjuryImpact,
    MatchIntensity,
    RefereeStrictness,
    # Enums
    RiskLevel,
    SignalLevel,
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
