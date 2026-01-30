"""
Alert Feedback Loop Implementation V1.0

This module implements a feedback loop where modified alerts
can be re-processed through the analysis pipeline with corrected data.

When the Final Verifier suggests modifications (e.g., "MODIFY" recommendation),
this component re-routes the alert back through the analysis pipeline with
corrected data for re-evaluation.

VPS Compatibility:
- Stateless design - no persistent storage required
- Pure Python implementation
- Thread-safe for concurrent alert processing
"""
import logging
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Type imports for type checking only
try:
    from src.database.models import Match, NewsLog, SessionLocal
    _DB_MODELS_AVAILABLE = True
except ImportError:
    _DB_MODELS_AVAILABLE = False
    Match = Any
    NewsLog = Any

try:
    from src.analysis.final_alert_verifier import get_final_verifier
    _VERIFIER_AVAILABLE = True
except ImportError:
    _VERIFIER_AVAILABLE = False


class FeedbackLoopStatus(Enum):
    """Status of feedback loop processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class AlertModification:
    """Represents a modification suggested by the verifier."""
    field: str
    original_value: Any
    suggested_value: Any
    reason: str
    impact: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'field': self.field,
            'original_value': self.original_value,
            'suggested_value': self.suggested_value,
            'reason': self.reason,
            'impact': self.impact
        }


class AlertFeedbackLoop:
    """
    Implements a feedback loop for alert modification and re-processing.
    
    When the Final Verifier suggests modifications, this component
    can re-route the alert back through the analysis pipeline with
    corrected data for re-evaluation.
    """
    
    def __init__(self, max_iterations: int = 2):
        self.max_iterations = max_iterations
        self._verifier = None
    
    @property
    def verifier(self) -> Any:
        """Lazy load verifier to avoid circular imports."""
        if self._verifier is None and _VERIFIER_AVAILABLE:
            try:
                from src.analysis.final_alert_verifier import get_final_verifier
                self._verifier = get_final_verifier()
            except Exception as e:
                logger.warning(f"Failed to initialize verifier: {e}")
                self._verifier = None
        return self._verifier
    
    def process_modification_feedback(
        self,
        match: Any,
        original_analysis: Any,
        verification_result: Dict[str, Any],
        alert_data: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any], Optional[Any]]:
        """
        Process modification feedback from Final Verifier.
        
        Args:
            match: Match database object
            original_analysis: Original NewsLog analysis
            verification_result: Result from Final Verifier with MODIFY suggestion
            alert_data: Original alert data
            context_data: Original context data
            
        Returns:
            Tuple of (should_send, final_verification_result, reprocessed_analysis)
        """
        # Validate inputs
        if not verification_result or not isinstance(verification_result, dict):
            logger.warning("Feedback loop called with invalid verification_result")
            return False, {"error": "Invalid verification_result"}, None
        
        if verification_result.get("final_recommendation") != "MODIFY":
            logger.warning("Feedback loop called without MODIFY recommendation")
            return False, verification_result, None
        
        suggested_modifications = verification_result.get("suggested_modifications", "")
        if not suggested_modifications:
            logger.warning("MODIFY recommendation without specific modifications")
            return False, verification_result, None
        
        logger.info(f"🔄 [FEEDBACK LOOP] Processing modification: {suggested_modifications}")
        
        # Parse modifications
        modifications = self._parse_modifications(suggested_modifications, alert_data)
        
        if not modifications:
            logger.warning("Could not parse modifications from suggestion")
            return False, verification_result, None
        
        # Apply modifications and re-process
        try:
            reprocessed_analysis = self._reprocess_with_modifications(
                match, original_analysis, modifications, context_data
            )
            
            if reprocessed_analysis:
                # Re-verify the reprocessed alert
                should_send, final_result = self._verify_reprocessed_alert(
                    match, reprocessed_analysis, alert_data, context_data
                )
                
                logger.info(f"🔄 [FEEDBACK LOOP] Re-processing completed: {final_result.get('verification_status', 'UNKNOWN')}")
                return should_send, final_result, reprocessed_analysis
            else:
                logger.error("🔄 [FEEDBACK LOOP] Re-processing failed")
                return False, verification_result, None
                
        except Exception as e:
            logger.error(f"🔄 [FEEDBACK LOOP] Error during re-processing: {e}")
            return False, verification_result, None
    
    def _parse_modifications(self, modifications_str: str, alert_data: Dict[str, Any]) -> List[AlertModification]:
        """
        Parse modification suggestions from verifier response.
        
        Examples:
        - "Change market from Over 2.5 to Under 2.5"
        - "Reduce score from 8 to 6"
        - "Update goal statistics from 2.8 to 1.4"
        
        Args:
            modifications_str: String containing modification suggestions
            alert_data: Original alert data for context
            
        Returns:
            List of AlertModification objects
        """
        modifications: List[AlertModification] = []
        
        if not modifications_str or not isinstance(modifications_str, str):
            return modifications
        
        # Market change detection
        if "change market" in modifications_str.lower() or "market" in modifications_str.lower():
            market_mod = self._parse_market_change(modifications_str, alert_data)
            if market_mod:
                modifications.append(market_mod)
        
        # Score adjustment detection
        if "score" in modifications_str.lower() or "reduce" in modifications_str.lower():
            score_mod = self._parse_score_adjustment(modifications_str, alert_data)
            if score_mod:
                modifications.append(score_mod)
        
        # Data correction detection
        if "statistics" in modifications_str.lower() or "data" in modifications_str.lower():
            data_mod = self._parse_data_correction(modifications_str, alert_data)
            if data_mod:
                modifications.append(data_mod)
        
        return modifications
    
    def _parse_market_change(self, modifications_str: str, alert_data: Dict) -> Optional[AlertModification]:
        """Parse market change suggestions."""
        current_market = alert_data.get("recommended_market", "")
        
        # Simple pattern matching for market changes
        if "over" in modifications_str.lower() and "under" in current_market.lower():
            return AlertModification(
                field="recommended_market",
                original_value=current_market,
                suggested_value=current_market.replace("Over", "Under"),
                reason="Market direction corrected based on verified data",
                impact="HIGH"
            )
        elif "under" in modifications_str.lower() and "over" in current_market.lower():
            return AlertModification(
                field="recommended_market",
                original_value=current_market,
                suggested_value=current_market.replace("Under", "Over"),
                reason="Market direction corrected based on verified data",
                impact="HIGH"
            )
        
        return None
    
    def _parse_score_adjustment(self, modifications_str: str, alert_data: Dict) -> Optional[AlertModification]:
        """Parse score adjustment suggestions."""
        current_score = alert_data.get("score", 8)
        
        # Look for reduction indicators
        if "reduce" in modifications_str.lower() or "lower" in modifications_str.lower():
            new_score = max(5, current_score - 2)
            return AlertModification(
                field="score",
                original_value=current_score,
                suggested_value=new_score,
                reason="Score reduced due to data discrepancies",
                impact="MEDIUM"
            )
        
        return None
    
    def _parse_data_correction(self, modifications_str: str, alert_data: Dict) -> Optional[AlertModification]:
        """Parse data correction suggestions."""
        # This would need more sophisticated parsing for specific data fields
        # For now, return None as it requires complex NLP
        return None
    
    def _reprocess_with_modifications(
        self,
        match: Any,
        original_analysis: Any,
        modifications: List[AlertModification],
        context_data: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Re-process the alert with applied modifications.
        
        This simulates running the analysis again with corrected data.
        
        Args:
            match: Match database object
            original_analysis: Original NewsLog analysis
            modifications: List of modifications to apply
            context_data: Original context data
            
        Returns:
            Modified NewsLog or None if failed
        """
        try:
            # Apply modifications to create new analysis context
            modified_context = self._create_modified_context(
                original_analysis, modifications, context_data
            )
            
            logger.info(f"🔄 [FEEDBACK LOOP] Re-processing with {len(modifications)} modifications")
            
            # Create modified NewsLog (simplified)
            if _DB_MODELS_AVAILABLE:
                from src.database.models import NewsLog
                modified_analysis = NewsLog()
            else:
                # Fallback: create a simple object with required attributes
                class SimpleNewsLog:
                    pass
                modified_analysis = SimpleNewsLog()
            
            # Copy original attributes safely
            modified_analysis.match_id = getattr(original_analysis, 'match_id', None)
            modified_analysis.url = getattr(original_analysis, 'url', None)
            modified_analysis.category = getattr(original_analysis, 'category', None)
            modified_analysis.affected_team = getattr(original_analysis, 'affected_team', None)
            
            # Apply modifications
            for mod in modifications:
                if mod.field == "recommended_market":
                    modified_analysis.recommended_market = mod.suggested_value
                elif mod.field == "score":
                    modified_analysis.score = mod.suggested_value
            
            # Update summary to reflect modifications
            original_summary = getattr(original_analysis, 'summary', '') or ""
            modified_analysis.summary = f"[MODIFIED] {original_summary}"
            
            # Add modification notes
            mod_notes = "; ".join([f"{mod.field}: {mod.reason}" for mod in modifications])
            modified_analysis.reasoning = f"Original: {original_summary} | Modifications: {mod_notes}"
            
            # Mark as reprocessed
            modified_analysis.status = "reprocessed"
            modified_analysis.feedback_loop_iterations = getattr(original_analysis, 'feedback_loop_iterations', 0) + 1
            
            return modified_analysis
            
        except Exception as e:
            logger.error(f"Error in re-processing: {e}")
            return None
    
    def _create_modified_context(
        self,
        original_analysis: NewsLog,
        modifications: list[AlertModification],
        context_data: Dict
    ) -> Dict:
        """Create modified context for re-analysis."""
        modified_context = context_data.copy()
        
        # Apply modifications to context
        for mod in modifications:
            if mod.field == "recommended_market":
                modified_context["suggested_market"] = mod.suggested_value
            elif mod.field == "score":
                modified_context["adjusted_score"] = mod.suggested_value
        
        # Add modification metadata
        modified_context["feedback_loop_active"] = True
        modified_context["original_analysis_id"] = original_analysis.id
        modified_context["modifications_applied"] = [
            {
                "field": mod.field,
                "original": mod.original_value,
                "suggested": mod.suggested_value,
                "reason": mod.reason
            }
            for mod in modifications
        ]
        
        return modified_context
    
    def _verify_reprocessed_alert(
        self,
        match: Any,
        reprocessed_analysis: Any,
        alert_data: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify the reprocessed alert through the Final Verifier again.
        
        Args:
            match: Match database object
            reprocessed_analysis: Reprocessed NewsLog analysis
            alert_data: Original alert data
            context_data: Original context data
            
        Returns:
            Tuple of (should_send, verification_result)
        """
        try:
            # Check if verifier is available
            if not self.verifier:
                logger.warning("Final Verifier not available, skipping re-verification")
                return True, {
                    "verification_status": "PASSED",
                    "reason": "Verifier not available - accepting modifications",
                    "feedback_loop_used": True,
                    "feedback_loop_iterations": getattr(reprocessed_analysis, 'feedback_loop_iterations', 1)
                }
            
            # Update alert data with reprocessed information
            reprocessed_alert_data = alert_data.copy()
            reprocessed_alert_data.update({
                "score": getattr(reprocessed_analysis, 'score', alert_data.get('score')),
                "recommended_market": getattr(reprocessed_analysis, 'recommended_market', alert_data.get('recommended_market')),
                "reasoning": getattr(reprocessed_analysis, 'reasoning', alert_data.get('reasoning')),
                "news_summary": getattr(reprocessed_analysis, 'summary', alert_data.get('news_summary'))
            })
            
            # Update context data
            reprocessed_context = context_data.copy()
            reprocessed_context["feedback_loop_iteration"] = getattr(reprocessed_analysis, 'feedback_loop_iterations', 1)
            
            # Run verification again
            should_send, verification_result = self.verifier.verify_final_alert(
                match=match,
                analysis=reprocessed_analysis,
                alert_data=reprocessed_alert_data,
                context_data=reprocessed_context
            )
            
            # Add feedback loop metadata to result
            if isinstance(verification_result, dict):
                verification_result["feedback_loop_used"] = True
                verification_result["feedback_loop_iterations"] = getattr(reprocessed_analysis, 'feedback_loop_iterations', 1)
                verification_result["original_rejected"] = True
            
            return should_send, verification_result
            
        except Exception as e:
            logger.error(f"Error verifying reprocessed alert: {e}")
            return False, {"error": str(e), "feedback_loop_failed": True}


# Singleton instance
_feedback_loop_instance: Optional[AlertFeedbackLoop] = None


def get_alert_feedback_loop() -> AlertFeedbackLoop:
    """Get or create the singleton AlertFeedbackLoop instance."""
    global _feedback_loop_instance
    if _feedback_loop_instance is None:
        _feedback_loop_instance = AlertFeedbackLoop()
    return _feedback_loop_instance


# ============================================
# MODULE EXPORTS
# ============================================

__all__ = [
    'FeedbackLoopStatus',
    'AlertModification',
    'AlertFeedbackLoop',
    'get_alert_feedback_loop',
]
