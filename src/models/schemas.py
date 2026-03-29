"""
EarlyBird Pydantic Schemas V4.1

Data validation models for API responses and internal data structures.
Provides type safety and default values for robust data handling.
"""

import warnings
from typing import Any

from pydantic import BaseModel, Field


class GeminiResponse(BaseModel):
    """
    Validated response from Gemini Agent deep dive analysis.

    ⚠️ DEPRECATED (V6.0+): This schema is legacy code and is NOT actively instantiated.
    The system has migrated to DeepDiveResponse from src/schemas/perplexity_schemas.py,
    which is used by DeepSeekIntelProvider (primary), PerplexityProvider (fallback),
    and OpenRouterFallbackProvider (Claude 3 Haiku fallback).

    All fields have safe defaults to prevent None propagation.
    """

    internal_crisis: str = Field(default="Unknown")
    turnover_risk: str = Field(default="Unknown")
    referee_intel: str = Field(default="Unknown")
    biscotto_potential: str = Field(default="Unknown")
    injury_impact: str = Field(default="None reported")

    # Motivation Intelligence (V4.2)
    motivation_home: str = Field(default="Unknown")
    motivation_away: str = Field(default="Unknown")
    table_context: str = Field(default="Unknown")

    # Legacy fields for backward compatibility
    referee_stats: str | None = None
    h2h_results: str | None = None
    injuries: list[str] = Field(default_factory=list)
    raw_intel: str | None = None

    def __init__(self, **data):
        """Emit a deprecation warning when this model is instantiated."""
        warnings.warn(
            "GeminiResponse is DEPRECATED (V6.0+). "
            "Use DeepDiveResponse from src.schemas.perplexity_schemas instead. "
            "The system now uses DeepSeek as primary provider with three-level fallback: "
            "DeepSeek → Tavily → Claude 3 Haiku.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**data)


class MatchAlert(BaseModel):
    """
    Structured match alert data - Core alert information.

    This class contains the essential fields required for any alert.
    For full alert functionality with all intelligence parameters, use EnhancedMatchAlert.
    """

    home_team: str
    away_team: str
    league: str
    score: float = Field(ge=0, le=10, description="Relevance score (0-10)")
    news_summary: str
    news_url: str | None = Field(default=None, description="Source URL for the news")
    recommended_market: str | None = Field(
        default=None, description="Primary market recommendation"
    )
    combo_suggestion: str | None = Field(default=None, description="Combo bet suggestion")


class EnhancedMatchAlert(MatchAlert):
    """
    Enhanced match alert with full intelligence parameters.

    V1.0: Complete alert data structure for EarlyBird intelligent bot.
    Extends MatchAlert with all additional intelligence parameters used
    by the alert pipeline.

    This class represents the complete alert payload that flows through
    the intelligent bot's alert system, including all verification,
    intelligence, and context data.
    """

    # Extended intelligence fields
    combo_reasoning: str | None = Field(
        default=None, description="Reasoning behind the combo suggestion"
    )
    math_edge: dict[str, Any] | None = Field(
        default=None, description="Mathematical edge from Poisson model"
    )
    is_update: bool = Field(
        default=False, description="True if this is an update to a previous alert"
    )
    financial_risk: str | None = Field(
        default=None, description="B-Team risk level from Financial Intelligence"
    )
    intel_source: str = Field(
        default="web", description="Source of intelligence: 'web', 'telegram', 'ocr'"
    )
    referee_intel: dict[str, Any] | None = Field(
        default=None, description="Referee stats for cards market"
    )
    twitter_intel: dict[str, Any] | None = Field(
        default=None, description="Twitter insider intelligence"
    )
    validated_home_team: str | None = Field(
        default=None, description="Corrected home team name if FotMob detected inversion"
    )
    validated_away_team: str | None = Field(
        default=None, description="Corrected away team name if FotMob detected inversion"
    )
    verification_info: dict[str, Any] | None = Field(
        default=None, description="Verification Layer result"
    )
    final_verification_info: dict[str, Any] | None = Field(
        default=None, description="Final Alert Verifier result from Perplexity API"
    )
    injury_intel: dict[str, Any] | None = Field(default=None, description="Injury impact analysis")
    confidence_breakdown: dict[str, Any] | None = Field(
        default=None, description="Confidence score breakdown"
    )
    is_convergent: bool = Field(
        default=False, description="V9.5 - True if signal confirmed by both Web and Social sources"
    )
    convergence_sources: dict[str, Any] | None = Field(
        default=None, description="V9.5 - Dict with web and social signal details"
    )
    market_warning: str | None = Field(
        default=None, description="V11.1 - Warning message for late-to-market alerts"
    )

    # Database update fields (not sent to Telegram)
    match_obj: Any | None = Field(
        default=None,
        description="Match ORM object for duplicate checks, odds_alert_sent flag, and team info. "
        "Separate from analysis_result which is the NewsLog for odds_at_alert updates.",
    )
    analysis_result: Any | None = Field(
        default=None, description="NewsLog object to update with odds_at_alert (V8.3)"
    )
    db_session: Any | None = Field(
        default=None, description="Database session for updating NewsLog (V8.3)"
    )

    @classmethod
    def from_kwargs(cls, **kwargs) -> "EnhancedMatchAlert":
        """
        Create EnhancedMatchAlert from kwargs (backward compatibility).

        This factory method allows the alert pipeline to accept both
        EnhancedMatchAlert objects and legacy kwargs, providing a smooth
        migration path.

        Args:
            **kwargs: Alert data as keyword arguments

        Returns:
            EnhancedMatchAlert instance

        Raises:
            ValidationError: If required fields are missing or invalid
        """
        # Extract match object
        match_obj = kwargs.get("match")

        # Build core MatchAlert fields
        core_fields = {
            "home_team": kwargs.get("validated_home_team") or getattr(match_obj, "home_team", None),
            "away_team": kwargs.get("validated_away_team") or getattr(match_obj, "away_team", None),
            "league": kwargs.get("league", "") or getattr(match_obj, "league", ""),
            "score": kwargs.get("score"),
            "news_summary": cls._extract_news_summary(kwargs),
            "news_url": cls._extract_news_url(kwargs),
            "recommended_market": kwargs.get("market") or kwargs.get("recommended_market"),
            "combo_suggestion": kwargs.get("combo_suggestion"),
        }

        # Build extended fields
        extended_fields = {
            "combo_reasoning": kwargs.get("combo_reasoning"),
            "math_edge": kwargs.get("math_edge"),
            "is_update": kwargs.get("is_update", False),
            "financial_risk": kwargs.get("financial_risk"),
            "intel_source": kwargs.get("intel_source", "web"),
            "referee_intel": kwargs.get("referee_intel"),
            "twitter_intel": kwargs.get("twitter_intel"),
            "validated_home_team": kwargs.get("validated_home_team"),
            "validated_away_team": kwargs.get("validated_away_team"),
            "verification_info": kwargs.get("verification_result"),
            "final_verification_info": kwargs.get("final_verification_info"),
            "injury_intel": kwargs.get("injury_impact_home") or kwargs.get("injury_impact_away"),
            "confidence_breakdown": kwargs.get("confidence_breakdown"),
            "is_convergent": kwargs.get("is_convergent", False),
            "convergence_sources": kwargs.get("convergence_sources"),
            "market_warning": kwargs.get("market_warning"),
            "match_obj": kwargs.get("match_obj") or kwargs.get("match"),
            "analysis_result": kwargs.get("analysis_result"),
            "db_session": kwargs.get("db_session"),
        }

        # Merge all fields
        all_fields = {**core_fields, **extended_fields}

        return cls(**all_fields)

    @staticmethod
    def _extract_news_summary(kwargs: dict) -> str:
        """Extract news summary from kwargs."""
        news_articles = kwargs.get("news_articles", [])
        return news_articles[0].get("snippet", "") if news_articles else ""

    @staticmethod
    def _extract_news_url(kwargs: dict) -> str | None:
        """Extract news URL from kwargs."""
        news_articles = kwargs.get("news_articles", [])
        return news_articles[0].get("link", "") if news_articles else None

    def to_send_alert_kwargs(self) -> dict[str, Any]:
        """
        Convert EnhancedMatchAlert to kwargs for send_alert().

        This method provides compatibility with the existing send_alert()
        function signature while allowing gradual migration to use
        EnhancedMatchAlert directly.

        Returns:
            Dictionary of kwargs compatible with send_alert()
        """
        return {
            "match_obj": self.match_obj,  # Match ORM object for duplicate checks
            "news_summary": self.news_summary,
            "news_url": self.news_url,
            "score": self.score,
            "league": self.league,
            "combo_suggestion": self.combo_suggestion,
            "combo_reasoning": self.combo_reasoning,
            "recommended_market": self.recommended_market,
            "math_edge": self.math_edge,
            "is_update": self.is_update,
            "financial_risk": self.financial_risk,
            "intel_source": self.intel_source,
            "referee_intel": self.referee_intel,
            "twitter_intel": self.twitter_intel,
            "validated_home_team": self.validated_home_team,
            "validated_away_team": self.validated_away_team,
            "verification_info": self.verification_info,
            "final_verification_info": self.final_verification_info,
            "injury_intel": self.injury_intel,
            "confidence_breakdown": self.confidence_breakdown,
            "is_convergent": self.is_convergent,
            "convergence_sources": self.convergence_sources,
            "market_warning": self.market_warning,
        }
