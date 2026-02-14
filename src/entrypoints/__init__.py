"""EarlyBird Entry Points Package

Application entry points for different execution modes.
"""

from .launcher import main as launcher_main
from .run_bot import main as run_bot_main

__all__ = [
    "launcher_main",
    "run_bot_main",
]
