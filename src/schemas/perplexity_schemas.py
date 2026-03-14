"""
EarlyBird Pydantic Schemas V1.0

Structured output models for Perplexity API responses.
Replaces parsing/normalization functions with type-safe validation.

V1.0: Deep Dive and Betting Stats schemas for Perplexity structured outputs.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class RiskLevel(str, Enum):
    """Standard risk levels for analysis."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class RefereeStrictness(str, Enum):
    """Referee strictness levels."""

    STRICT = "Strict"
    MEDIUM = "Medium"
    LENIENT = "Lenient"
    UNKNOWN = "Unknown"


class BiscottoPotential(str, Enum):
    """Biscotto (mutually beneficial draw) potential."""

    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class InjuryImpact(str, Enum):
    """Injury impact assessment."""

    CRITICAL = "Critical"
    MANAGEABLE = "Manageable"
    UNKNOWN = "Unknown"


class BTTSImpact(str, Enum):
    """BTTS (Both Teams To Score) tactical impact."""

    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    NEUTRAL = "Neutral"
    UNKNOWN = "Unknown"


class SignalLevel(str, Enum):
    """Signal levels for betting stats."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class CardsSignal(str, Enum):
    """Cards signal levels."""

    AGGRESSIVE = "Aggressive"
    MEDIUM = "Medium"
    DISCIPLINED = "Disciplined"
    UNKNOWN = "Unknown"


class DataConfidence(str, Enum):
    """Data confidence levels."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class MatchIntensity(str, Enum):
    """Match intensity levels."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class DeepDiveResponse(BaseModel):
    """
    Pydantic model for Deep Dive analysis response.

    Replaces normalize_deep_dive_response() with type-safe validation.
    Used by PerplexityProvider.get_match_deep_dive() and DeepSeekIntelProvider.get_match_deep_dive().
    """

    internal_crisis: str = Field(description="Risk level and explanation for internal crisis")
    turnover_risk: str = Field(description="Risk level and explanation for tactical turnover")
    referee_intel: str = Field(description="Referee strictness and average cards")
    biscotto_potential: str = Field(description="Biscotto potential and reasoning")
    injury_impact: str = Field(description="Injury impact assessment")
    btts_impact: str = Field(description="BTTS tactical impact analysis")
    motivation_home: str = Field(description="Home team motivation level and reason")
    motivation_away: str = Field(description="Away team motivation level and reason")
    table_context: str = Field(description="League table context")

    @field_validator("internal_crisis", "turnover_risk")
    @classmethod
    def validate_risk_levels(cls, v):
        """Ensure risk levels start with valid enum values."""
        for risk in [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.UNKNOWN]:
            if v.startswith(risk.value):
                return v
        raise ValueError(
            f"Must start with valid risk level: {', '.join([r.value for r in RiskLevel])}"
        )

    @field_validator("referee_intel")
    @classmethod
    def validate_referee_intel(cls, v):
        """Ensure referee intel starts with valid strictness."""
        for strictness in [
            RefereeStrictness.STRICT,
            RefereeStrictness.MEDIUM,
            RefereeStrictness.LENIENT,
            RefereeStrictness.UNKNOWN,
        ]:
            if v.startswith(strictness.value):
                return v
        raise ValueError(
            f"Must start with valid referee strictness: {', '.join([s.value for s in RefereeStrictness])}"
        )

    @field_validator("biscotto_potential")
    @classmethod
    def validate_biscotto_potential(cls, v):
        """Ensure biscotto potential starts with valid enum (case-insensitive)."""
        if isinstance(v, str):
            v_lower = v.lower()
            for potential in [
                BiscottoPotential.YES,
                BiscottoPotential.NO,
                BiscottoPotential.UNKNOWN,
            ]:
                if v_lower.startswith(potential.value.lower()):
                    # Normalize the case: preserve the explanation but use correct case for the potential
                    return potential.value + v[len(potential.value) :]
            raise ValueError(
                f"Must start with valid biscotto potential: {', '.join([p.value for p in BiscottoPotential])}"
            )

    @field_validator("injury_impact")
    @classmethod
    def validate_injury_impact(cls, v):
        """Ensure injury impact starts with valid enum."""
        for impact in [InjuryImpact.CRITICAL, InjuryImpact.MANAGEABLE, InjuryImpact.UNKNOWN]:
            if v.startswith(impact.value):
                return v
        raise ValueError(
            f"Must start with valid injury impact: {', '.join([i.value for i in InjuryImpact])}"
        )

    @field_validator("btts_impact")
    @classmethod
    def validate_btts_impact(cls, v):
        """Ensure BTTS impact starts with valid enum (case-insensitive)."""
        if isinstance(v, str):
            v_lower = v.lower()
            for impact in [
                BTTSImpact.POSITIVE,
                BTTSImpact.NEGATIVE,
                BTTSImpact.NEUTRAL,
                BTTSImpact.UNKNOWN,
            ]:
                if v_lower.startswith(impact.value.lower()):
                    # Normalize the case: preserve the explanation but use correct case for the impact
                    return impact.value + v[len(impact.value) :]
            raise ValueError(
                f"Must start with valid BTTS impact: {', '.join([i.value for i in BTTSImpact])}"
            )

    @field_validator("motivation_home", "motivation_away")
    @classmethod
    def validate_motivation(cls, v):
        """Ensure motivation starts with valid enum."""
        for risk in [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.UNKNOWN]:
            if v.startswith(risk.value):
                return v
        raise ValueError(
            f"Must start with valid motivation level: {', '.join([r.value for r in RiskLevel])}"
        )


class BettingStatsResponse(BaseModel):
    """
    Pydantic model for Betting Stats response.

    Replaces _normalize_betting_stats() with type-safe validation.
    Used by PerplexityProvider.get_betting_stats() and DeepSeekIntelProvider.get_betting_stats().
    """

    # Recent Form (Last 5 matches)
    home_form_wins: int | None = Field(
        default=None, ge=0, le=5, description="Home team wins in last 5 matches"
    )
    home_form_draws: int | None = Field(
        default=None, ge=0, le=5, description="Home team draws in last 5 matches"
    )
    home_form_losses: int | None = Field(
        default=None, ge=0, le=5, description="Home team losses in last 5 matches"
    )
    home_goals_scored_last5: int | None = Field(
        default=None, ge=0, description="Home team goals scored in last 5 matches"
    )
    home_goals_conceded_last5: int | None = Field(
        default=None, ge=0, description="Home team goals conceded in last 5 matches"
    )

    away_form_wins: int | None = Field(
        default=None, ge=0, le=5, description="Away team wins in last 5 matches"
    )
    away_form_draws: int | None = Field(
        default=None, ge=0, le=5, description="Away team draws in last 5 matches"
    )
    away_form_losses: int | None = Field(
        default=None, ge=0, le=5, description="Away team losses in last 5 matches"
    )
    away_goals_scored_last5: int | None = Field(
        default=None, ge=0, description="Away team goals scored in last 5 matches"
    )
    away_goals_conceded_last5: int | None = Field(
        default=None, ge=0, description="Away team goals conceded in last 5 matches"
    )

    # Corners Statistics
    home_corners_avg: float | None = Field(
        default=None, ge=0, description="Home team average corners per game"
    )
    away_corners_avg: float | None = Field(
        default=None, ge=0, description="Away team average corners per game"
    )
    corners_total_avg: float | None = Field(
        default=None, ge=0, description="Combined average corners"
    )
    corners_signal: SignalLevel = Field(
        default=SignalLevel.UNKNOWN, description="Corner signal level"
    )
    corners_reasoning: str = Field(default="", description="Explanation of corner potential")

    # Cards Statistics
    home_cards_avg: float | None = Field(
        default=None, ge=0, description="Home team average cards per game"
    )
    away_cards_avg: float | None = Field(
        default=None, ge=0, description="Away team average cards per game"
    )
    cards_total_avg: float | None = Field(default=None, ge=0, description="Combined average cards")
    cards_signal: CardsSignal = Field(default=CardsSignal.UNKNOWN, description="Cards signal level")
    cards_reasoning: str = Field(default="", description="Explanation of card potential")

    # Referee Information
    referee_name: str = Field(default="Unknown", description="Referee name")
    referee_cards_avg: float | None = Field(
        default=None, ge=0, description="Referee average cards per game"
    )
    referee_strictness: RefereeStrictness = Field(
        default=RefereeStrictness.UNKNOWN, description="Referee strictness level"
    )

    # Match Context
    match_intensity: MatchIntensity = Field(
        default=MatchIntensity.UNKNOWN, description="Match intensity level"
    )
    is_derby: bool = Field(default=False, description="Whether this is a derby match")

    # Recommendations
    recommended_corner_line: str = Field(
        default="No bet", description="Recommended corner betting line"
    )
    recommended_cards_line: str = Field(
        default="No bet", description="Recommended cards betting line"
    )

    # Data Quality
    data_confidence: DataConfidence = Field(
        default=DataConfidence.UNKNOWN, description="Confidence in data quality"
    )
    sources_found: str = Field(default="", description="Brief note on data sources")

    @field_validator("corners_signal")
    @classmethod
    def validate_corners_signal(cls, v):
        """Validate corners signal is a valid enum."""
        if isinstance(v, str):
            try:
                return SignalLevel(v)
            except ValueError:
                return SignalLevel.UNKNOWN
        return v

    @field_validator("cards_signal", mode="before")
    @classmethod
    def validate_cards_signal(cls, v):
        """Validate cards signal is a valid enum (case-insensitive)."""
        if isinstance(v, str):
            v_lower = v.lower()
            for signal in [
                CardsSignal.AGGRESSIVE,
                CardsSignal.MEDIUM,
                CardsSignal.DISCIPLINED,
                CardsSignal.UNKNOWN,
            ]:
                if v_lower == signal.value.lower():
                    return signal
            return CardsSignal.UNKNOWN
        return v

    @field_validator("referee_strictness", mode="before")
    @classmethod
    def validate_referee_strictness(cls, v):
        """Validate referee strictness is a valid enum (case-insensitive)."""
        if isinstance(v, str):
            v_lower = v.lower()
            for strictness in [
                RefereeStrictness.STRICT,
                RefereeStrictness.MEDIUM,
                RefereeStrictness.LENIENT,
                RefereeStrictness.UNKNOWN,
            ]:
                if v_lower == strictness.value.lower():
                    return strictness
            return RefereeStrictness.UNKNOWN
        return v

    @field_validator("match_intensity", mode="before")
    @classmethod
    def validate_match_intensity(cls, v):
        """Validate match intensity is a valid enum (case-insensitive)."""
        if isinstance(v, str):
            v_lower = v.lower()
            for intensity in [
                MatchIntensity.HIGH,
                MatchIntensity.MEDIUM,
                MatchIntensity.LOW,
                MatchIntensity.UNKNOWN,
            ]:
                if v_lower == intensity.value.lower():
                    return intensity
            return MatchIntensity.UNKNOWN
        return v

    @field_validator("data_confidence")
    @classmethod
    def validate_data_confidence(cls, v):
        """Validate data confidence is a valid enum."""
        if isinstance(v, str):
            try:
                return DataConfidence(v)
            except ValueError:
                return DataConfidence.UNKNOWN
        return v

    @field_validator("home_form_wins", "home_form_draws", "home_form_losses")
    @classmethod
    def validate_home_form_consistency(cls, v, info):
        """
        Ensure home form values are consistent (max 5 matches total).

        Auto-corrects totals exceeding 5 by reducing the largest field first,
        then the second largest, until total equals exactly 5.

        This approach guarantees the total is exactly 5, avoiding the issues
        with proportional correction that can fail due to rounding.
        """
        import logging

        logger = logging.getLogger(__name__)

        # Get all home form fields for validation
        data = info.data
        home_wins = data.get("home_form_wins")
        home_draws = data.get("home_form_draws")
        home_losses = data.get("home_form_losses")

        # Validate that total matches don't exceed 5
        if home_wins is not None and home_draws is not None and home_losses is not None:
            total_matches = home_wins + home_draws + home_losses
            if total_matches > 5:
                # Calculate excess to remove
                excess = total_matches - 5

                # Create a list of (field_name, current_value) sorted by value (descending)
                # This ensures we reduce the largest values first
                fields = [
                    ("home_form_wins", home_wins),
                    ("home_form_draws", home_draws),
                    ("home_form_losses", home_losses),
                ]
                fields.sort(key=lambda x: x[1], reverse=True)

                # Reduce fields until total equals exactly 5
                remaining_excess = excess
                for field_name, field_value in fields:
                    if remaining_excess <= 0:
                        break

                    # Calculate how much to reduce from this field
                    reduction = min(field_value, remaining_excess)
                    data[field_name] = field_value - reduction
                    remaining_excess -= reduction

                # Verify the correction worked
                corrected_total = (
                    data["home_form_wins"] + data["home_form_draws"] + data["home_form_losses"]
                )
                if corrected_total != 5:
                    logger.error(
                        f"🔧 [FORM_VALIDATION] Home form correction failed: "
                        f"original={total_matches}, expected=5, got={corrected_total}"
                    )
                else:
                    logger.warning(
                        f"🔧 [FORM_VALIDATION] Home form total exceeded 5 ({total_matches} matches). "
                        f"Auto-corrected: W={data['home_form_wins']}, "
                        f"D={data['home_form_draws']}, L={data['home_form_losses']}"
                    )

        return v

    @field_validator("away_form_wins", "away_form_draws", "away_form_losses")
    @classmethod
    def validate_away_form_consistency(cls, v, info):
        """
        Ensure away form values are consistent (max 5 matches total).

        Auto-corrects totals exceeding 5 by reducing the largest field first,
        then the second largest, until total equals exactly 5.

        This approach guarantees total is exactly 5, avoiding issues
        with proportional correction that can fail due to rounding.
        """
        import logging

        logger = logging.getLogger(__name__)

        # Get all away form fields for validation
        data = info.data
        away_wins = data.get("away_form_wins")
        away_draws = data.get("away_form_draws")
        away_losses = data.get("away_form_losses")

        # Validate that total matches don't exceed 5
        if away_wins is not None and away_draws is not None and away_losses is not None:
            total_matches = away_wins + away_draws + away_losses
            if total_matches > 5:
                # Calculate excess to remove
                excess = total_matches - 5

                # Create a list of (field_name, current_value) sorted by value (descending)
                # This ensures we reduce the largest values first
                fields = [
                    ("away_form_wins", away_wins),
                    ("away_form_draws", away_draws),
                    ("away_form_losses", away_losses),
                ]
                fields.sort(key=lambda x: x[1], reverse=True)

                # Reduce fields until total equals exactly 5
                remaining_excess = excess
                for field_name, field_value in fields:
                    if remaining_excess <= 0:
                        break

                    # Calculate how much to reduce from this field
                    reduction = min(field_value, remaining_excess)
                    data[field_name] = field_value - reduction
                    remaining_excess -= reduction

                # Verify the correction worked
                corrected_total = (
                    data["away_form_wins"] + data["away_form_draws"] + data["away_form_losses"]
                )
                if corrected_total != 5:
                    logger.error(
                        f"🔧 [FORM_VALIDATION] Away form correction failed: "
                        f"original={total_matches}, expected=5, got={corrected_total}"
                    )
                else:
                    logger.warning(
                        f"🔧 [FORM_VALIDATION] Away form total exceeded 5 ({total_matches} matches). "
                        f"Auto-corrected: W={data['away_form_wins']}, "
                        f"D={data['away_form_draws']}, L={data['away_form_losses']}"
                    )

        return v

    @model_validator(mode="after")
    @classmethod
    def validate_form_consistency(cls, model):
        """
        Ensure home and away form values are consistent (max 5 matches total).

        Auto-corrects totals exceeding 5 by reducing the largest field first,
        then the second largest, until total equals exactly 5.

        This approach guarantees total is exactly 5, avoiding issues
        with proportional correction that can fail due to rounding.
        """
        import logging

        logger = logging.getLogger(__name__)

        # Validate home form
        home_wins = model.home_form_wins
        home_draws = model.home_form_draws
        home_losses = model.home_form_losses

        if home_wins is not None and home_draws is not None and home_losses is not None:
            home_total = home_wins + home_draws + home_losses
            if home_total > 5:
                # Calculate excess to remove
                excess = home_total - 5

                # Create a list of (field_name, current_value) sorted by value (descending)
                # This ensures we reduce the largest values first
                home_fields = [
                    ("home_form_wins", home_wins),
                    ("home_form_draws", home_draws),
                    ("home_form_losses", home_losses),
                ]
                home_fields.sort(key=lambda x: x[1], reverse=True)

                # Reduce fields until total equals exactly 5
                remaining_excess = excess
                for field_name, field_value in home_fields:
                    if remaining_excess <= 0:
                        break

                    # Calculate how much to reduce from this field
                    reduction = min(field_value, remaining_excess)
                    setattr(model, field_name, field_value - reduction)
                    remaining_excess -= reduction

                # Verify the correction worked
                corrected_total = (
                    model.home_form_wins + model.home_form_draws + model.home_form_losses
                )
                if corrected_total != 5:
                    logger.error(
                        f"🔧 [FORM_VALIDATION] Home form correction failed: "
                        f"original={home_total}, expected=5, got={corrected_total}"
                    )
                else:
                    logger.warning(
                        f"🔧 [FORM_VALIDATION] Home form total exceeded 5 ({home_total} matches). "
                        f"Auto-corrected: W={model.home_form_wins}, "
                        f"D={model.home_form_draws}, L={model.home_form_losses}"
                    )

        # Validate away form
        away_wins = model.away_form_wins
        away_draws = model.away_form_draws
        away_losses = model.away_form_losses

        if away_wins is not None and away_draws is not None and away_losses is not None:
            away_total = away_wins + away_draws + away_losses
            if away_total > 5:
                # Calculate excess to remove
                excess = away_total - 5

                # Create a list of (field_name, current_value) sorted by value (descending)
                # This ensures we reduce the largest values first
                away_fields = [
                    ("away_form_wins", away_wins),
                    ("away_form_draws", away_draws),
                    ("away_form_losses", away_losses),
                ]
                away_fields.sort(key=lambda x: x[1], reverse=True)

                # Reduce fields until total equals exactly 5
                remaining_excess = excess
                for field_name, field_value in away_fields:
                    if remaining_excess <= 0:
                        break

                    # Calculate how much to reduce from this field
                    reduction = min(field_value, remaining_excess)
                    setattr(model, field_name, field_value - reduction)
                    remaining_excess -= reduction

                # Verify the correction worked
                corrected_total = (
                    model.away_form_wins + model.away_form_draws + model.away_form_losses
                )
                if corrected_total != 5:
                    logger.error(
                        f"🔧 [FORM_VALIDATION] Away form correction failed: "
                        f"original={away_total}, expected=5, got={corrected_total}"
                    )
                else:
                    logger.warning(
                        f"🔧 [FORM_VALIDATION] Away form total exceeded 5 ({away_total} matches). "
                        f"Auto-corrected: W={model.away_form_wins}, "
                        f"D={model.away_form_draws}, L={model.away_form_losses}"
                    )

        return model


# JSON Schema exports for Perplexity API
DEEP_DIVE_JSON_SCHEMA = DeepDiveResponse.model_json_schema()
BETTING_STATS_JSON_SCHEMA = BettingStatsResponse.model_json_schema()
