"""EarlyBird Processing Package

Orchestration and processing components.
"""

from .news_hunter import run_hunter_for_match
from .continental_orchestrator import ContinentalOrchestrator, get_continental_orchestrator

__all__ = [
    "run_hunter_for_match",
    "ContinentalOrchestrator",
    "get_continental_orchestrator",
]
