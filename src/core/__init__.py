"""
Core module for EarlyBird system.

This module contains core orchestration components that coordinate
the overall system behavior.
"""

# NOTE: Package-level export removed to avoid loading heavy modules (analyzer, etc.)
# when importing from submodules. All imports should be done directly from modules:
# - from src.core.analysis_engine import AnalysisEngine (not from src.core import AnalysisEngine)

__all__: list[str] = []
