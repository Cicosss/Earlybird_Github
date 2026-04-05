"""EarlyBird Analysis Package

Analysis engines, verifiers, and optimization components.
"""

# NOTE: Package-level export removed to avoid loading heavy modules (analyzer, etc.)
# when importing from submodules. All imports should be done directly from modules:
# - from src.analysis.analyzer import analyze_with_triangulation
#     (instead of from src.analysis import analyze_with_triangulation)
# - from src.analysis.math_engine import MathPredictor
#     (instead of from src.analysis import MathPredictor)
# - from src.analysis.optimizer import get_optimizer
#     (instead of from src.analysis import get_optimizer)
# - from src.analysis.verification_layer import verify_alert
#     (instead of from src.analysis import verify_alert)
# - from src.analysis.final_alert_verifier import get_final_verifier
#     (instead of from src.analysis import get_final_verifier)

__all__: list[str] = []
