"""EarlyBird Analysis Package

Analysis engines, verifiers, and optimization components.
"""

from .analyzer import analyze_with_triangulation
from .math_engine import MathPredictor, format_math_context
from .optimizer import get_optimizer, get_dynamic_alert_threshold
from .verification_layer import verify_alert
from .final_alert_verifier import get_final_verifier

__all__ = [
    "analyze_with_triangulation",
    "MathPredictor",
    "format_math_context",
    "get_optimizer",
    "get_dynamic_alert_threshold",
    "verify_alert",
    "get_final_verifier",
]
