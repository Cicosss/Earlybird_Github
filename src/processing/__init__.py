"""EarlyBird Processing Package

Orchestration and processing components.
"""

# NOTE: Package-level exports removed to avoid loading heavy modules when importing from submodules.
# All imports should be done directly from modules:
# - from src.processing.global_orchestrator import GlobalOrchestrator (not from src.processing import GlobalOrchestrator)
# - from src.processing.news_hunter import run_hunter_for_match (not from src.processing import run_hunter_for_match)

__all__: list[str] = []
