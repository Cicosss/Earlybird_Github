"""
Enhanced Final Alert Verifier with Data Discrepancy Handling

This module extends the Final Alert Verifier to handle data discrepancies
between FotMob extraction and IntelligenceRouter verification more intelligently.

V3.0: COMPLETE REWRITE - Uses real data from IntelligenceRouter instead of placeholders
- Extracts actual fotmob_value and intelligence_value from AI response
- Displays discrepancies in Telegram alerts
- Integrates with intelligent modification loop
- Configurable confidence penalties
- Comprehensive logging
"""

import logging
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any

from src.analysis.final_alert_verifier import FinalAlertVerifier
from src.database.models import Match, NewsLog

logger = logging.getLogger(__name__)


@dataclass
class DataDiscrepancy:
    """Represents a discrepancy between extracted and verified data.

    V3.0: Now uses REAL values from IntelligenceRouter instead of placeholders.
    """

    field: str
    fotmob_value: Any  # Actual value from FotMob extraction
    intelligence_value: Any  # Actual value from IntelligenceRouter web search
    impact: str  # "LOW", "MEDIUM", "HIGH"
    description: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class EnhancedFinalVerifier(FinalAlertVerifier):
    """
    Enhanced Final Alert Verifier with intelligent discrepancy handling.

    V3.0: COMPLETE REWRITE - Uses real data from IntelligenceRouter instead of placeholders.

    Key improvements:
    - Extracts ACTUAL fotmob_value and intelligence_value from AI response
    - Displays discrepancies in Telegram alerts with real values
    - Integrates with intelligent modification loop
    - Configurable confidence penalties via environment variables
    - Comprehensive logging for debugging
    - Semantic understanding of discrepancy impact
    """

    def __init__(self):
        super().__init__()
        # Load configurable confidence penalties from environment
        self._high_impact_penalty = int(os.getenv("DISCREPANCY_HIGH_PENALTY", "3"))
        self._medium_impact_penalty = int(os.getenv("DISCREPANCY_MEDIUM_PENALTY", "2"))
        self._low_impact_penalty = int(os.getenv("DISCREPANCY_LOW_PENALTY", "1"))

        logger.info(
            f"🔧 [ENHANCED VERIFIER] Configured penalties: "
            f"HIGH={self._high_impact_penalty}, MEDIUM={self._medium_impact_penalty}, LOW={self._low_impact_penalty}"
        )

    def verify_final_alert_with_discrepancy_handling(
        self, match: Match, analysis: NewsLog, alert_data: dict, context_data: dict | None = None
    ) -> tuple[bool, dict]:
        """
        Enhanced verification that handles data discrepancies intelligently.

        V3.0: Now uses REAL data from IntelligenceRouter instead of placeholders.

        Args:
            match: Match database object
            analysis: NewsLog analysis object
            alert_data: Complete alert data
            context_data: Additional context

        Returns:
            Tuple of (should_send, enhanced_verification_result)
        """
        # First, run standard verification (which includes IntelligenceRouter)
        should_send, verification_result = super().verify_final_alert(
            match, analysis, alert_data, context_data
        )

        # V3.0: Extract REAL discrepancies from IntelligenceRouter response
        # The parent class already extracts discrepancies with real values from the AI response
        # We just need to convert them to DataDiscrepancy objects for consistency
        raw_discrepancies = verification_result.get("data_discrepancies", [])

        if raw_discrepancies:
            # Convert dict discrepancies to DataDiscrepancy objects with REAL values
            discrepancies = self._convert_discrepancies(raw_discrepancies)

            if discrepancies:
                # Log each discrepancy with real values
                self._log_discrepancies(discrepancies)

                # Store as DataDiscrepancy objects
                verification_result["data_discrepancies"] = discrepancies

                # Adjust confidence based on discrepancies (using configurable penalties)
                verification_result = self._adjust_confidence_for_discrepancies(
                    verification_result, discrepancies
                )

                logger.info(
                    f"✅ [ENHANCED VERIFIER] Processed {len(discrepancies)} discrepancies with REAL values"
                )
        else:
            logger.debug("[ENHANCED VERIFIER] No discrepancies found in verification result")

        return should_send, verification_result

    def _convert_discrepancies(self, raw_discrepancies: list[dict]) -> list[DataDiscrepancy]:
        """
        Convert raw discrepancy dicts from IntelligenceRouter to DataDiscrepancy objects.

        V3.0: Extracts REAL values from AI response instead of using placeholders.

        Args:
            raw_discrepancies: List of discrepancy dicts from IntelligenceRouter

        Returns:
            List of DataDiscrepancy objects with real values
        """
        discrepancies = []

        for raw in raw_discrepancies:
            try:
                # Extract real values from IntelligenceRouter response
                field = raw.get("field", "unknown")
                fotmob_value = raw.get("fotmob_value", "not provided")
                intelligence_value = raw.get(
                    "perplexity_value", raw.get("intelligence_value", "not provided")
                )
                impact = raw.get("impact", "LOW")
                description = raw.get("description", "No description provided")

                # Create DataDiscrepancy with REAL values
                discrepancy = DataDiscrepancy(
                    field=field,
                    fotmob_value=fotmob_value,
                    intelligence_value=intelligence_value,
                    impact=impact,
                    description=description,
                )
                discrepancies.append(discrepancy)

            except Exception as e:
                logger.warning(f"⚠️ [ENHANCED VERIFIER] Failed to convert discrepancy: {e}")

        return discrepancies

    def _log_discrepancies(self, discrepancies: list[DataDiscrepancy]) -> None:
        """
        Log discrepancies with real values for debugging.

        V3.0: Comprehensive logging with actual values.
        """
        logger.info(f"📊 [DISCREPANCY LOG] Found {len(discrepancies)} discrepancies:")

        for i, d in enumerate(discrepancies, 1):
            emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(d.impact, "⚪")
            logger.info(f"   {emoji} Discrepancy #{i}: {d.field.upper()}")
            logger.info(f"      FotMob value:      {d.fotmob_value}")
            logger.info(f"      Intelligence value: {d.intelligence_value}")
            logger.info(f"      Impact:           {d.impact}")
            logger.info(f"      Description:      {d.description}")

    def _adjust_confidence_for_discrepancies(
        self, verification_result: dict, discrepancies: list[DataDiscrepancy]
    ) -> dict:
        """
        Adjust confidence scores based on detected discrepancies.

        V3.0: Uses CONFIGURABLE penalties instead of hardcoded values.
        """
        original_confidence = verification_result.get("confidence_level", "HIGH")
        original_scores = {
            "logic_score": verification_result.get("logic_score", 8),
            "data_accuracy_score": verification_result.get("data_accuracy_score", 8),
            "reasoning_quality_score": verification_result.get("reasoning_quality_score", 8),
        }

        # Calculate penalty using CONFIGURABLE values
        total_penalty = 0
        for discrepancy in discrepancies:
            if discrepancy.impact == "HIGH":
                total_penalty += self._high_impact_penalty
            elif discrepancy.impact == "MEDIUM":
                total_penalty += self._medium_impact_penalty
            else:
                total_penalty += self._low_impact_penalty

        logger.info(
            f"📉 [CONFIDENCE ADJUSTMENT] Total penalty: {total_penalty} "
            f"(HIGH={self._high_impact_penalty}, MEDIUM={self._medium_impact_penalty}, LOW={self._low_impact_penalty})"
        )

        # Adjust scores
        adjusted_scores = {}
        for score_type, original_score in original_scores.items():
            adjusted_score = max(1, original_score - total_penalty)
            adjusted_scores[score_type] = adjusted_score
            logger.debug(f"   {score_type}: {original_score} → {adjusted_score}")

        # Adjust confidence level
        avg_score = sum(adjusted_scores.values()) / len(adjusted_scores)
        if avg_score >= 7:
            new_confidence = "HIGH"
        elif avg_score >= 5:
            new_confidence = "MEDIUM"
        else:
            new_confidence = "LOW"

        # Update verification result
        verification_result.update(adjusted_scores)
        verification_result["confidence_level"] = new_confidence
        verification_result["original_confidence"] = original_confidence
        verification_result["confidence_adjustment"] = (
            f"-{total_penalty} due to {len(discrepancies)} discrepancies"
        )

        # Add discrepancy summary
        verification_result["discrepancy_summary"] = {
            "total_count": len(discrepancies),
            "high_impact": len([d for d in discrepancies if d.impact == "HIGH"]),
            "medium_impact": len([d for d in discrepancies if d.impact == "MEDIUM"]),
            "low_impact": len([d for d in discrepancies if d.impact == "LOW"]),
        }

        logger.info(
            f"📊 [CONFIDENCE ADJUSTMENT] {original_confidence} → {new_confidence} "
            f"(avg score: {avg_score:.1f})"
        )

        return verification_result


# Thread-safe singleton for EnhancedFinalVerifier
_enhanced_verifier_instance: EnhancedFinalVerifier | None = None
_enhanced_verifier_init_lock = threading.Lock()


def get_enhanced_final_verifier() -> EnhancedFinalVerifier:
    """Get or create the singleton EnhancedFinalVerifier instance.

    Uses thread-safe double-checked locking pattern, matching the
    singleton pattern used by get_final_verifier() in the base module.
    """
    global _enhanced_verifier_instance
    if _enhanced_verifier_instance is None:
        with _enhanced_verifier_init_lock:
            # Double-checked locking for thread safety
            if _enhanced_verifier_instance is None:
                _enhanced_verifier_instance = EnhancedFinalVerifier()
    return _enhanced_verifier_instance
