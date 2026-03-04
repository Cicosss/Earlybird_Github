"""EarlyBird - Football Betting Intelligence System

A sophisticated betting intelligence system that analyzes football matches,
news, and market movements to identify profitable betting opportunities.
"""

__version__ = "9.5"
__author__ = "EarlyBird Team"

# NOTE: Package-level exports removed to avoid loading heavy modules (analyzer, etc.)
# when importing from submodules. All imports should be done directly from modules:
# - from src.core.analysis_engine import AnalysisEngine (not from src import AnalysisEngine)
# - from src.database.models import Match (not from src import Match)
# - from src.models.schemas import GeminiResponse (not from src import GeminiResponse)

__all__ = [
    "__version__",
    "__author__",
]
