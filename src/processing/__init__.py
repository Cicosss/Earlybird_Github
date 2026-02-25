"""EarlyBird Processing Package

Orchestration and processing components.
"""

from .global_orchestrator import GlobalOrchestrator, get_global_orchestrator, get_continental_orchestrator
from .news_hunter import run_hunter_for_match

__all__ = [
    "run_hunter_for_match",
    "GlobalOrchestrator",
    "get_global_orchestrator",
    "get_continental_orchestrator",  # Backward compatibility
]
