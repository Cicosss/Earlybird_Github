"""EarlyBird - Football Betting Intelligence System

A sophisticated betting intelligence system that analyzes football matches,
news, and market movements to identify profitable betting opportunities.
"""

__version__ = "9.5"
__author__ = "EarlyBird Team"

# Core exports
from src.core import AnalysisEngine
from src.core.settlement_service import get_settlement_service

# Database exports
from src.database.models import Match, NewsLog, TeamAlias, Base, init_db, SessionLocal

# Models exports
from src.models.schemas import GeminiResponse, OddsMovement, MatchAlert

__all__ = [
    "__version__",
    "__author__",
    "AnalysisEngine",
    "get_settlement_service",
    "Match",
    "NewsLog",
    "TeamAlias",
    "Base",
    "init_db",
    "SessionLocal",
    "GeminiResponse",
    "OddsMovement",
    "MatchAlert",
]
