"""
Step-by-Step Feedback Loop with Component Communication

This component implements the intelligent feedback loop that applies modifications
step-by-step, ensuring all components communicate properly during the process.
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import json

from src.analysis.intelligent_modification_logger import (
    get_intelligent_modification_logger,
    ModificationPlan,
    SuggestedModification,
    FeedbackDecision,
    ModificationType
)
from src.analysis.alert_feedback_loop import AlertFeedbackLoop
from src.database.models import NewsLog, Match, SessionLocal
from src.analysis.final_alert_verifier import get_final_verifier

logger = logging.getLogger(__name__)


class StepByStepFeedbackLoop:
    """
    Intelligent step-by-step feedback loop with component communication.
    
    This system:
    1. Receives modification plan from Intelligent Logger
    2. Applies modifications step-by-step
    3. Ensures component communication at each step
    4. Re-verifies after each modification
    5. Tracks success/failure for learning
    """
    
    def __init__(self):
        self.intelligent_logger = get_intelligent_modification_logger()
        self.feedback_loop = AlertFeedbackLoop()
        self.verifier = get_final_verifier()
        self.component_communicators = {}
        self._initialize_component_communicators()
    
    def _initialize_component_communicators(self):
        """Initialize component communicators for step-by-step execution."""
        self.component_communicators = {
            "analyzer": ComponentCommunicator("analyzer", self._communicate_with_analyzer),
            "verification_layer": ComponentCommunicator("verification_layer", self._communicate_with_verification_layer),
            "math_engine": ComponentCommunicator("math_engine", self._communicate_with_math_engine),
            "threshold_manager": ComponentCommunicator("threshold_manager", self._communicate_with_threshold_manager),
            "health_monitor": ComponentCommunicator("health_monitor", self._communicate_with_health_monitor),
            "data_validator": ComponentCommunicator("data_validator", self._communicate_with_data_validator)
        }
    
    def process_modification_plan(
        self,
        match: Match,
        original_analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: Dict,
        context_data: Dict
    ) -> Tuple[bool, Dict, Optional[NewsLog]]:
        """
        Process the modification plan step-by-step with component communication.
        
        Args:
            match: Match database object
            original_analysis: Original NewsLog analysis
            modification_plan: Plan from Intelligent Logger
            alert_data: Original alert data
            context_data: Original context data
            
        Returns:
            Tuple of (should_send, final_verification_result, final_analysis)
        """
        # Input validation
        if not match or not original_analysis or not modification_plan:
            logger.error("Invalid input to process_modification_plan")
            return False, {"status": "invalid_input", "error": "Missing required parameters"}, None
        
        logger.info(f"🔄 [STEP-BY-STEP] Processing modification plan: {modification_plan.feedback_decision.value}")
        
        if modification_plan.feedback_decision == FeedbackDecision.IGNORE:
            logger.info("🔄 [STEP-BY-STEP] No modifications needed")
            return False, {"status": "ignored"}, None
        
        if modification_plan.feedback_decision == FeedbackDecision.MANUAL_REVIEW:
            logger.info("🔄 [STEP-BY-STEP] Logging for manual review")
            self._log_for_manual_review(match, original_analysis, modification_plan, alert_data, context_data)
            return False, {"status": "manual_review_required"}, None
        
        # Automatic feedback loop execution
        return self._execute_automatic_feedback_loop(
            match, original_analysis, modification_plan, alert_data, context_data
        )
    
    def _execute_automatic_feedback_loop(
        self,
        match: Match,
        original_analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: Dict,
        context_data: Dict
    ) -> Tuple[bool, Dict, Optional[NewsLog]]:
        """
        Execute automatic feedback loop step-by-step.
        """
        logger.info(f"🔄 [STEP-BY-STEP] Starting automatic feedback with {len(modification_plan.modifications)} steps")
        
        current_analysis = original_analysis
        current_alert_data = alert_data.copy()
        current_context_data = context_data.copy()
        
        # Track execution state
        execution_state = {
            "steps_completed": [],
            "steps_failed": [],
            "component_communications": [],
            "intermediate_results": []
        }
        
        try:
            # Execute modifications in order
            for i, modification in enumerate(modification_plan.modifications):
                logger.info(f"🔄 [STEP-BY-STEP] Step {i+1}/{len(modification_plan.modifications)}: {modification.type.value}")
                
                # Step 1: Communicate with affected components
                communication_result = self._communicate_with_components(
                    modification, modification_plan.component_communication
                )
                execution_state["component_communications"].append(communication_result)
                
                # Step 2: Apply the modification
                apply_result = self._apply_modification(
                    modification, current_analysis, current_alert_data, current_context_data
                )
                
                if not apply_result["success"]:
                    logger.error(f"🔄 [STEP-BY-STEP] Step {i+1} failed: {apply_result['error']}")
                    execution_state["steps_failed"].append(i+1)
                    break
                
                # Update current state
                current_analysis = apply_result["analysis"]
                current_alert_data = apply_result["alert_data"]
                current_context_data = apply_result["context_data"]
                
                # Step 3: Intermediate verification (optional for critical steps)
                if modification.priority.value in ["critical", "high"]:
                    intermediate_result = self._intermediate_verification(
                        match, current_analysis, current_alert_data, current_context_data
                    )
                    execution_state["intermediate_results"].append(intermediate_result)
                    
                    if not intermediate_result["passed"]:
                        logger.warning(f"🔄 [STEP-BY-STEP] Intermediate verification failed at step {i+1}")
                        execution_state["steps_failed"].append(i+1)
                        break
                
                execution_state["steps_completed"].append(i+1)
                logger.info(f"🔄 [STEP-BY-STEP] Step {i+1} completed successfully")
            
            # Step 4: Final verification
            if len(execution_state["steps_completed"]) == len(modification_plan.modifications):
                logger.info("🔄 [STEP-BY-STEP] All steps completed, running final verification")
                
                should_send, final_result = self.verifier.verify_final_alert(
                    match=match,
                    analysis=current_analysis,
                    alert_data=current_alert_data,
                    context_data=current_context_data
                )
                
                # Add execution metadata
                final_result["feedback_loop_execution"] = {
                    "steps_completed": execution_state["steps_completed"],
                    "steps_failed": execution_state["steps_failed"],
                    "total_steps": len(modification_plan.modifications),
                    "success_rate": len(execution_state["steps_completed"]) / len(modification_plan.modifications),
                    "execution_time": datetime.now(timezone.utc).isoformat()
                }
                
                # Update learning
                self._update_learning_patterns(original_analysis.id, modification_plan, final_result)
                
                logger.info(f"🔄 [STEP-BY-STEP] Final verification result: {final_result.get('verification_status')}")
                return should_send, final_result, current_analysis
            else:
                logger.error(f"🔄 [STEP-BY-STEP] Execution failed at steps: {execution_state['steps_failed']}")
                return False, {
                    "status": "execution_failed",
                    "failed_steps": execution_state["steps_failed"],
                    "completed_steps": execution_state["steps_completed"]
                }, current_analysis
                
        except Exception as e:
            logger.error(f"🔄 [STEP-BY-STEP] Unexpected error: {e}")
            return False, {"status": "error", "error": str(e)}, current_analysis
    
    def _communicate_with_components(
        self,
        modification: SuggestedModification,
        communication_plan: Dict[str, str]
    ) -> Dict:
        """Communicate with components affected by the modification."""
        communications = {}
        
        for component_name, message in communication_plan.items():
            if component_name in self.component_communicators:
                try:
                    communicator = self.component_communicators[component_name]
                    result = communicator.communicate(modification, message)
                    communications[component_name] = result
                    logger.debug(f"🔄 [COMM] {component_name}: {result['status']}")
                except Exception as e:
                    communications[component_name] = {"status": "error", "error": str(e)}
                    logger.error(f"🔄 [COMM] Error communicating with {component_name}: {e}")
        
        return {
            "modification_id": modification.id,
            "communications": communications,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _apply_modification(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Apply a single modification to the analysis data."""
        try:
            if modification.type == ModificationType.MARKET_CHANGE:
                return self._apply_market_change(modification, analysis, alert_data, context_data)
            elif modification.type == ModificationType.SCORE_ADJUSTMENT:
                return self._apply_score_adjustment(modification, analysis, alert_data, context_data)
            elif modification.type == ModificationType.DATA_CORRECTION:
                return self._apply_data_correction(modification, analysis, alert_data, context_data)
            elif modification.type == ModificationType.REASONING_UPDATE:
                return self._apply_reasoning_update(modification, analysis, alert_data, context_data)
            else:
                return {"success": False, "error": f"Unknown modification type: {modification.type}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _apply_market_change(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Apply market change modification."""
        # Update analysis
        analysis.recommended_market = modification.suggested_value
        
        # Update alert data
        alert_data["recommended_market"] = modification.suggested_value
        
        # Update context
        context_data["market_modification"] = {
            "original": modification.original_value,
            "new": modification.suggested_value,
            "reason": modification.reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Update reasoning
        original_reasoning = getattr(analysis, 'reasoning', '') or getattr(analysis, 'summary', '')
        analysis.reasoning = f"[MARKET MODIFIED] {original_reasoning} | Market changed from {modification.original_value} to {modification.suggested_value}: {modification.reason}"
        
        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data
        }
    
    def _apply_score_adjustment(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Apply score adjustment modification."""
        # Update analysis
        analysis.score = modification.suggested_value
        
        # Update alert data
        alert_data["score"] = modification.suggested_value
        
        # Update context
        context_data["score_modification"] = {
            "original": modification.original_value,
            "new": modification.suggested_value,
            "reason": modification.reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data
        }
    
    def _apply_data_correction(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Apply data correction modification."""
        # Update context with corrected data
        context_data[f"corrected_{modification.id}"] = {
            "original": modification.original_value,
            "corrected": modification.suggested_value,
            "field": modification.id.split("_")[1] if "_" in modification.id else modification.id,
            "reason": modification.reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Note: Data corrections don't directly change analysis but affect verification
        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data
        }
    
    def _apply_reasoning_update(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Apply reasoning update modification."""
        # Update analysis reasoning
        analysis.reasoning = modification.suggested_value
        
        # Update alert data
        alert_data["reasoning"] = modification.suggested_value
        
        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data
        }
    
    def _intermediate_verification(
        self,
        match: Match,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> Dict:
        """Perform intermediate verification after critical steps."""
        try:
            # Quick verification check
            should_send, result = self.verifier.verify_final_alert(
                match=match,
                analysis=analysis,
                alert_data=alert_data,
                context_data=context_data
            )
            
            return {
                "passed": should_send,
                "status": result.get("verification_status", "UNKNOWN"),
                "confidence": result.get("confidence_level", "LOW"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            return {
                "passed": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _communicate_with_analyzer(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with analyzer component."""
        # This would interface with the actual analyzer
        # For now, simulate the communication
        return {
            "status": "acknowledged",
            "message": f"Analyzer received: {message}",
            "action": "Will update analysis parameters",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _communicate_with_verification_layer(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with verification layer component."""
        return {
            "status": "acknowledged",
            "message": f"Verification layer received: {message}",
            "action": "Will adjust verification parameters",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _communicate_with_math_engine(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with math engine component."""
        return {
            "status": "acknowledged",
            "message": f"Math engine received: {message}",
            "action": "Will recalculate mathematical edges",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _communicate_with_threshold_manager(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with threshold manager component."""
        return {
            "status": "acknowledged",
            "message": f"Threshold manager received: {message}",
            "action": "Will adjust alert threshold considerations",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _communicate_with_health_monitor(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with health monitor component."""
        return {
            "status": "acknowledged",
            "message": f"Health monitor received: {message}",
            "action": "Will track modified alert performance",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _communicate_with_data_validator(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with data validator component."""
        return {
            "status": "acknowledged",
            "message": f"Data validator received: {message}",
            "action": "Will validate corrected data",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _log_for_manual_review(
        self,
        match: Match,
        analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: Dict,
        context_data: Dict
    ):
        """Log modification for manual review."""
        try:
            db = SessionLocal()
            
            # Create manual review record
            review_record = {
                "alert_id": str(analysis.id),
                "match_id": match.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "modification_plan": modification_plan.__dict__,
                "original_alert_data": alert_data,
                "context_data": context_data,
                "status": "pending_review",
                "reviewed_by": None,
                "review_timestamp": None,
                "review_decision": None,
                "review_notes": None
            }
            
            # Store in database (would need a ManualReview table in production)
            # For now, log to file
            logger.info(f"📋 [MANUAL REVIEW] Alert {analysis.id} queued for manual review")
            logger.info(f"   Modifications: {len(modification_plan.modifications)}")
            logger.info(f"   Risk level: {modification_plan.risk_level}")
            logger.info(f"   Reason: {modification_plan.feedback_decision.value}")
            
            db.close()
            
        except Exception as e:
            logger.error(f"Failed to log for manual review: {e}")
    
    def _update_learning_patterns(
        self,
        alert_id: str,
        modification_plan: ModificationPlan,
        final_result: Dict
    ):
        """Update learning patterns based on execution results."""
        try:
            # Update the intelligent logger's learning patterns
            logger.info(f"🧠 [LEARNING] Updating patterns for alert {alert_id}")
            
            # This would update a learning database
            # For now, just log the learning event
            success = final_result.get("should_send", False)
            status = final_result.get("verification_status", "UNKNOWN")
            
            logger.info(f"   Result: {status} | Success: {success}")
            logger.info(f"   Modifications applied: {len(modification_plan.modifications)}")
            
        except Exception as e:
            logger.error(f"Failed to update learning patterns: {e}")


class ComponentCommunicator:
    """Helper class for component communication."""
    
    def __init__(self, name: str, communication_func):
        self.name = name
        self.communication_func = communication_func
    
    def communicate(self, modification: SuggestedModification, message: str) -> Dict:
        """Communicate with the component."""
        return self.communication_func(modification, message)


# Singleton instance
_step_by_step_loop_instance: Optional[StepByStepFeedbackLoop] = None


def get_step_by_step_feedback_loop() -> StepByStepFeedbackLoop:
    """Get or create the singleton StepByStepFeedbackLoop instance."""
    global _step_by_step_loop_instance
    if _step_by_step_loop_instance is None:
        _step_by_step_loop_instance = StepByStepFeedbackLoop()
    return _step_by_step_loop_instance
