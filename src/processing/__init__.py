"""EarlyBird Processing Package

Orchestration and processing components.
"""

from .continental_orchestrator import ContinentalOrchestrator, get_continental_orchestrator
from .news_hunter import run_hunter_for_match

__all__ = [
    "run_hunter_for_match",
    "ContinentalOrchestrator",
    "get_continental_orchestrator",
]
