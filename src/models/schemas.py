"""
EarlyBird Pydantic Schemas V4.1

Data validation models for API responses and internal data structures.
Provides type safety and default values for robust data handling.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class GeminiResponse(BaseModel):
    """
    Validated response from Gemini Agent deep dive analysis.
    
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
    referee_stats: Optional[str] = None
    h2h_results: Optional[str] = None
    injuries: List[str] = Field(default_factory=list)
    raw_intel: Optional[str] = None


class OddsMovement(BaseModel):
    """Odds movement calculation result."""
    drop_percent: float = Field(default=0.0)
    emoji: str = Field(default="❓")
    message: str = Field(default="Quote non disponibili")


class MatchAlert(BaseModel):
    """Structured match alert data."""
    home_team: str
    away_team: str
    league: str
    score: int = Field(ge=0, le=10)
    news_summary: str
    news_url: Optional[str] = None
    recommended_market: Optional[str] = None
    combo_suggestion: Optional[str] = None
