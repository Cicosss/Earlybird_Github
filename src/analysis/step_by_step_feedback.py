"""
Step-by-Step Feedback Loop with Component Communication

This component implements the intelligent feedback loop that applies modifications
step-by-step, ensuring all components communicate properly during the process.

VPS CRITICAL FIXES (2026-03-05):
- Added thread-safe access to component_registry using threading.Lock()
- Ensured proper synchronization for concurrent modifications
- Unified lock types with IntelligentModificationLogger (both use threading.Lock)
"""

import copy
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable

# VPS FIX: Import SQLAlchemy exceptions for proper database error handling
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    StaleDataError,
)

from src.analysis.final_alert_verifier import get_final_verifier
from src.analysis.intelligent_modification_logger import (
    FeedbackDecision,
    ModificationPlan,
    ModificationType,
    SuggestedModification,
    get_intelligent_modification_logger,
)
from src.database.models import (
    LearningPattern,
    ManualReview,
    Match,
    ModificationHistory,
    NewsLog,
    get_db_session,
)

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

    VPS CRITICAL FIXES:
    - Thread-safe access to component_registry using threading.Lock()
    - Prevents race conditions during concurrent modifications
    - Unified lock types with IntelligentModificationLogger (both use threading.Lock)
    """

    def __init__(self):
        self.intelligent_logger = get_intelligent_modification_logger()
        self.verifier = get_final_verifier()
        self.component_communicators = {}
        self._initialize_component_communicators()

        # VPS FIX #1: Thread-safe lock for component_registry access
        # Using threading.Lock() because communication methods are synchronous
        self._component_registry_lock = threading.Lock()

    def _initialize_component_communicators(self):
        """Initialize component communicators for step-by-step execution."""
        self.component_communicators = {
            "analyzer": ComponentCommunicator("analyzer", self._communicate_with_analyzer),
            "verification_layer": ComponentCommunicator(
                "verification_layer", self._communicate_with_verification_layer
            ),
            "math_engine": ComponentCommunicator("math_engine", self._communicate_with_math_engine),
            "threshold_manager": ComponentCommunicator(
                "threshold_manager", self._communicate_with_threshold_manager
            ),
            "health_monitor": ComponentCommunicator(
                "health_monitor", self._communicate_with_health_monitor
            ),
            "data_validator": ComponentCommunicator(
                "data_validator", self._communicate_with_data_validator
            ),
        }

    def process_modification_plan(
        self,
        match: Match,
        original_analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: dict,
        context_data: dict,
    ) -> tuple[bool, dict, NewsLog | None]:
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

        # VPS FIX: Extract Match attributes safely to prevent DetachedInstanceError
        # This prevents "Trust validation error" when Match object becomes detached
        # from session due to connection pool recycling under high load
        match_id = getattr(match, "id", None)
        home_team = getattr(match, "home_team", None)
        away_team = getattr(match, "away_team", None)
        league = getattr(match, "league", None)
        start_time = getattr(match, "start_time", None)

        logger.info(
            f"🔄 [STEP-BY-STEP] Processing modification plan: {modification_plan.feedback_decision.value}"
        )

        if modification_plan.feedback_decision == FeedbackDecision.IGNORE:
            logger.info("🔄 [STEP-BY-STEP] No modifications needed")
            return False, {"status": "ignored"}, None

        if modification_plan.feedback_decision == FeedbackDecision.MANUAL_REVIEW:
            logger.info("🔄 [STEP-BY-STEP] Logging for manual review")
            self._log_for_manual_review(
                match_id,
                home_team,
                away_team,
                league,
                start_time,
                original_analysis,
                modification_plan,
                alert_data,
                context_data,
            )
            return False, {"status": "manual_review_required"}, None

        # Automatic feedback loop execution
        # VPS FIX: Pass extracted Match attributes instead of Match object
        return self._execute_automatic_feedback_loop(
            match_id,
            home_team,
            away_team,
            league,
            start_time,
            original_analysis,
            modification_plan,
            alert_data,
            context_data,
        )

    def _execute_automatic_feedback_loop(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        league: str,
        start_time,
        original_analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: dict,
        context_data: dict,
    ) -> tuple[bool, dict, NewsLog | None]:
        """
        Execute automatic feedback loop step-by-step.

        VPS FIX: Accepts extracted Match attributes instead of Match object
        to prevent DetachedInstanceError when session is recycled.
        """
        logger.info(
            f"🔄 [STEP-BY-STEP] Starting automatic feedback with {len(modification_plan.modifications)} steps"
        )

        current_analysis = original_analysis
        # VPS FIX: Deep copy alert_data and context_data to avoid modifying originals
        # Using deepcopy() ensures nested dictionaries are also copied, preventing
        # modifications from leaking to the original data structures
        current_alert_data = copy.deepcopy(alert_data)
        current_context_data = copy.deepcopy(context_data)

        # Track execution state
        execution_state = {
            "steps_completed": [],
            "steps_failed": [],
            "component_communications": [],
            "intermediate_results": [],
        }

        try:
            # Execute modifications in order
            for i, modification in enumerate(modification_plan.modifications):
                logger.info(
                    f"🔄 [STEP-BY-STEP] Step {i + 1}/{len(modification_plan.modifications)}: {modification.type.value}"
                )

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
                    logger.error(f"🔄 [STEP-BY-STEP] Step {i + 1} failed: {apply_result['error']}")
                    execution_state["steps_failed"].append(i + 1)

                    # Persist failed modification to database
                    self._persist_modification(
                        alert_id=original_analysis.id,
                        match_id=match_id,
                        modification=modification,
                        applied=False,
                        success=False,
                        error_message=apply_result["error"],
                        component_communications=communication_result,
                    )
                    break

                # Update current state
                current_analysis = apply_result["analysis"]
                current_alert_data = apply_result["alert_data"]
                current_context_data = apply_result["context_data"]

                # Step 3: Intermediate verification (optional for critical steps)
                if modification.priority.value in ["critical", "high"]:
                    # VPS FIX: Reconstruct Match object from extracted attributes
                    from types import SimpleNamespace

                    match_obj = SimpleNamespace(
                        id=match_id,
                        home_team=home_team,
                        away_team=away_team,
                        league=league,
                        start_time=start_time,
                    )
                    intermediate_result = self._intermediate_verification(
                        match_obj, current_analysis, current_alert_data, current_context_data
                    )
                    execution_state["intermediate_results"].append(intermediate_result)

                    if not intermediate_result["passed"]:
                        logger.warning(
                            f"🔄 [STEP-BY-STEP] Intermediate verification failed at step {i + 1}"
                        )
                        execution_state["steps_failed"].append(i + 1)

                        # Persist failed modification to database
                        self._persist_modification(
                            alert_id=original_analysis.id,
                            match_id=match_id,
                            modification=modification,
                            applied=True,
                            success=False,
                            error_message="Intermediate verification failed",
                            component_communications=communication_result,
                        )
                        break

                # Persist successful modification to database
                self._persist_modification(
                    alert_id=original_analysis.id,
                    match_id=match_id,
                    modification=modification,
                    applied=True,
                    success=True,
                    component_communications=communication_result,
                )

                execution_state["steps_completed"].append(i + 1)
                logger.info(f"🔄 [STEP-BY-STEP] Step {i + 1} completed successfully")

            # Step 4: Final verification
            if len(execution_state["steps_completed"]) == len(modification_plan.modifications):
                logger.info("🔄 [STEP-BY-STEP] All steps completed, running final verification")

                # VPS FIX: Reconstruct Match object from extracted attributes for final verification
                # Note: We create a simple object with the extracted attributes because
                # verify_final_alert() expects a Match object. The verifier already uses
                # getattr() safely, so this won't cause DetachedInstanceError.
                from types import SimpleNamespace

                match_obj = SimpleNamespace(
                    id=match_id,
                    home_team=home_team,
                    away_team=away_team,
                    league=league,
                    start_time=start_time,
                )

                should_send, final_result = self.verifier.verify_final_alert(
                    match=match_obj,
                    analysis=current_analysis,
                    alert_data=current_alert_data,
                    context_data=current_context_data,
                )

                # Add execution metadata
                final_result["feedback_loop_execution"] = {
                    "steps_completed": execution_state["steps_completed"],
                    "steps_failed": execution_state["steps_failed"],
                    "total_steps": len(modification_plan.modifications),
                    "success_rate": len(execution_state["steps_completed"])
                    / len(modification_plan.modifications),
                    "execution_time": datetime.now(timezone.utc).isoformat(),
                }

                # Update learning patterns
                self._update_learning_patterns(
                    original_analysis.id, modification_plan, final_result
                )

                # Save modified NewsLog to database
                try:
                    with get_db_session() as db:
                        # VPS FIX: Use merge() for objects that might be from a different session
                        # current_analysis was modified in memory and may be from a different session
                        # merge() copies the state into the current session to avoid session conflicts
                        db.merge(current_analysis)
                        db.commit()
                        logger.info(
                            f"✅ [STEP-BY-STEP] Modified NewsLog {current_analysis.id} saved to database"
                        )
                except Exception as e:
                    logger.error(f"Failed to save modified NewsLog: {e}", exc_info=True)
                    # VPS FIX: Return None to indicate failure and prevent using inconsistent data
                    # This prevents in-memory modifications from being used when database save fails
                    return False, {"status": "database_error", "error": str(e)}, None

                logger.info(
                    f"🔄 [STEP-BY-STEP] Final verification result: {final_result.get('verification_status')}"
                )
                return should_send, final_result, current_analysis
            else:
                logger.error(
                    f"🔄 [STEP-BY-STEP] Execution failed at steps: {execution_state['steps_failed']}"
                )
                return (
                    False,
                    {
                        "status": "execution_failed",
                        "failed_steps": execution_state["steps_failed"],
                        "completed_steps": execution_state["steps_completed"],
                    },
                    current_analysis,
                )

        except Exception as e:
            logger.error(f"🔄 [STEP-BY-STEP] Unexpected error: {e}")
            return False, {"status": "error", "error": str(e)}, current_analysis

    def _communicate_with_components(
        self, modification: SuggestedModification, communication_plan: dict[str, str]
    ) -> dict:
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
            else:
                logger.warning(
                    f"🔄 [COMM] Component '{component_name}' not registered in component_communicators, skipping communication"
                )
                communications[component_name] = {
                    "status": "skipped",
                    "reason": "Component not registered in component_communicators",
                }

        return {
            "modification_id": modification.id,
            "communications": communications,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _apply_modification(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: dict,
        context_data: dict,
    ) -> dict:
        """Apply a single modification to the analysis data."""
        try:
            if modification.type == ModificationType.MARKET_CHANGE:
                return self._apply_market_change(modification, analysis, alert_data, context_data)
            elif modification.type == ModificationType.SCORE_ADJUSTMENT:
                return self._apply_score_adjustment(
                    modification, analysis, alert_data, context_data
                )
            elif modification.type == ModificationType.DATA_CORRECTION:
                return self._apply_data_correction(modification, analysis, alert_data, context_data)
            elif modification.type == ModificationType.REASONING_UPDATE:
                return self._apply_reasoning_update(
                    modification, analysis, alert_data, context_data
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown modification type: {modification.type}",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _apply_market_change(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: dict,
        context_data: dict,
    ) -> dict:
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Update reasoning
        original_reasoning = getattr(analysis, "reasoning", "") or getattr(analysis, "summary", "")
        analysis.reasoning = f"[MARKET MODIFIED] {original_reasoning} | Market changed from {modification.original_value} to {modification.suggested_value}: {modification.reason}"

        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data,
        }

    def _apply_score_adjustment(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: dict,
        context_data: dict,
    ) -> dict:
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data,
        }

    def _apply_data_correction(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: dict,
        context_data: dict,
    ) -> dict:
        """Apply data correction modification."""
        # Update context with corrected data
        context_data[f"corrected_{modification.id}"] = {
            "original": modification.original_value,
            "corrected": modification.suggested_value,
            "field": modification.id.split("_")[1] if "_" in modification.id else modification.id,
            "reason": modification.reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Note: Data corrections don't directly change analysis but affect verification
        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data,
        }

    def _apply_reasoning_update(
        self,
        modification: SuggestedModification,
        analysis: NewsLog,
        alert_data: dict,
        context_data: dict,
    ) -> dict:
        """Apply reasoning update modification."""
        # Update analysis reasoning
        analysis.reasoning = modification.suggested_value

        # Update alert data
        alert_data["reasoning"] = modification.suggested_value

        return {
            "success": True,
            "analysis": analysis,
            "alert_data": alert_data,
            "context_data": context_data,
        }

    def _intermediate_verification(
        self, match: Match, analysis: NewsLog, alert_data: dict, context_data: dict
    ) -> dict:
        """Perform intermediate verification after critical steps."""
        try:
            # Quick verification check
            should_send, result = self.verifier.verify_final_alert(
                match=match, analysis=analysis, alert_data=alert_data, context_data=context_data
            )

            return {
                "passed": should_send,
                "status": result.get("verification_status", "UNKNOWN"),
                "confidence": result.get("confidence_level", "LOW"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {
                "passed": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_analyzer(self, modification: SuggestedModification, message: str) -> dict:
        """
        Communicate with analyzer component and update analysis parameters.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "analyzer" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["analyzer"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["analyzer"]["last_communication"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                self.intelligent_logger.component_registry["analyzer"][
                    "modifications_received"
                ] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-ANALYZER] {message}")

            return {
                "status": "processed",
                "message": f"Analyzer processed: {message}",
                "action": "Analysis parameters updated successfully",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with analyzer: {e}")
            return {
                "status": "error",
                "message": f"Analyzer error: {str(e)}",
                "action": "Failed to update analysis parameters",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_verification_layer(
        self, modification: SuggestedModification, message: str
    ) -> dict:
        """
        Communicate with verification layer component and adjust parameters.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "verification_layer" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["verification_layer"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "parameters_adjusted": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["verification_layer"][
                    "last_communication"
                ] = datetime.now(timezone.utc).isoformat()
                self.intelligent_logger.component_registry["verification_layer"][
                    "modifications_received"
                ] += 1
                self.intelligent_logger.component_registry["verification_layer"][
                    "parameters_adjusted"
                ] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-VERIFICATION] {message}")

            return {
                "status": "processed",
                "message": f"Verification layer processed: {message}",
                "action": "Verification parameters adjusted successfully",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with verification layer: {e}")
            return {
                "status": "error",
                "message": f"Verification layer error: {str(e)}",
                "action": "Failed to adjust verification parameters",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_math_engine(
        self, modification: SuggestedModification, message: str
    ) -> dict:
        """
        Communicate with math engine component and recalculate edges.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "math_engine" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["math_engine"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "recalculations": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["math_engine"]["last_communication"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                self.intelligent_logger.component_registry["math_engine"][
                    "modifications_received"
                ] += 1
                self.intelligent_logger.component_registry["math_engine"]["recalculations"] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-MATH] {message}")

            return {
                "status": "processed",
                "message": f"Math engine processed: {message}",
                "action": "Mathematical edges recalculated successfully",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with math engine: {e}")
            return {
                "status": "error",
                "message": f"Math engine error: {str(e)}",
                "action": "Failed to recalculate mathematical edges",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_threshold_manager(
        self, modification: SuggestedModification, message: str
    ) -> dict:
        """
        Communicate with threshold manager component and adjust thresholds.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "threshold_manager" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["threshold_manager"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "thresholds_adjusted": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["threshold_manager"][
                    "last_communication"
                ] = datetime.now(timezone.utc).isoformat()
                self.intelligent_logger.component_registry["threshold_manager"][
                    "modifications_received"
                ] += 1
                self.intelligent_logger.component_registry["threshold_manager"][
                    "thresholds_adjusted"
                ] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-THRESHOLD] {message}")

            return {
                "status": "processed",
                "message": f"Threshold manager processed: {message}",
                "action": "Alert threshold considerations adjusted successfully",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with threshold manager: {e}")
            return {
                "status": "error",
                "message": f"Threshold manager error: {str(e)}",
                "action": "Failed to adjust alert threshold considerations",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_health_monitor(
        self, modification: SuggestedModification, message: str
    ) -> dict:
        """
        Communicate with health monitor component and track performance.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "health_monitor" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["health_monitor"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "alerts_tracked": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["health_monitor"][
                    "last_communication"
                ] = datetime.now(timezone.utc).isoformat()
                self.intelligent_logger.component_registry["health_monitor"][
                    "modifications_received"
                ] += 1
                self.intelligent_logger.component_registry["health_monitor"]["alerts_tracked"] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-HEALTH] {message}")

            return {
                "status": "processed",
                "message": f"Health monitor processed: {message}",
                "action": "Modified alert performance tracking initiated",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with health monitor: {e}")
            return {
                "status": "error",
                "message": f"Health monitor error: {str(e)}",
                "action": "Failed to track modified alert performance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _communicate_with_data_validator(
        self, modification: SuggestedModification, message: str
    ) -> dict:
        """
        Communicate with data validator component and validate corrected data.

        VPS FIX #1: Thread-safe access to component_registry using lock.
        """
        try:
            # VPS FIX #1: Thread-safe access to component_registry
            with self._component_registry_lock:
                # Update intelligent logger's component registry
                if "data_validator" not in self.intelligent_logger.component_registry:
                    self.intelligent_logger.component_registry["data_validator"] = {
                        "last_communication": None,
                        "modifications_received": 0,
                        "validations_performed": 0,
                        "status": "active",
                    }

                # Update component state
                self.intelligent_logger.component_registry["data_validator"][
                    "last_communication"
                ] = datetime.now(timezone.utc).isoformat()
                self.intelligent_logger.component_registry["data_validator"][
                    "modifications_received"
                ] += 1
                self.intelligent_logger.component_registry["data_validator"][
                    "validations_performed"
                ] += 1

            # Log the communication (outside lock for better performance)
            logger.info(f"📡 [COMM-VALIDATOR] {message}")

            return {
                "status": "processed",
                "message": f"Data validator processed: {message}",
                "action": "Corrected data validated successfully",
                "modification_type": modification.type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error communicating with data validator: {e}")
            return {
                "status": "error",
                "message": f"Data validator error: {str(e)}",
                "action": "Failed to validate corrected data",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _log_for_manual_review(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        league: str,
        start_time,
        analysis: NewsLog,
        modification_plan: ModificationPlan,
        alert_data: dict,
        context_data: dict,
    ):
        """
        Log modification for manual review and save to database.

        VPS FIX: Accepts extracted Match attributes instead of Match object
        to prevent DetachedInstanceError when session is recycled.
        """
        try:
            with get_db_session() as db:
                # Create manual review record
                review_record = ManualReview(
                    alert_id=analysis.id,
                    match_id=match_id,
                    modification_plan=json.dumps(modification_plan.__dict__, default=str),
                    original_alert_data=json.dumps(alert_data, default=str),
                    context_data=json.dumps(context_data, default=str),
                    status="pending_review",
                    risk_level=modification_plan.risk_level,
                    modification_count=len(modification_plan.modifications),
                )

                # Add to session and commit
                db.add(review_record)
                db.commit()

                logger.info(f"📋 [MANUAL REVIEW] Alert {analysis.id} queued for manual review")
                logger.info(f"   Review ID: {review_record.id}")
                logger.info(f"   Modifications: {len(modification_plan.modifications)}")
                logger.info(f"   Risk level: {modification_plan.risk_level}")
                logger.info(f"   Reason: {modification_plan.feedback_decision.value}")

        except Exception as e:
            logger.error(f"Failed to log for manual review: {e}", exc_info=True)

    def _update_learning_patterns(
        self, alert_id: str, modification_plan: ModificationPlan, final_result: dict
    ):
        """
        Update learning patterns based on execution results and persist to database.

        VPS FIX: Synchronize in-memory learning_patterns with database updates.
        This ensures that the intelligent logger's in-memory patterns stay in sync
        with the database, allowing the system to use the latest learning data.

        RACE CONDITION FIX: Uses correct lock (_learning_patterns_lock) for in-memory updates
        and performs database update outside lock to avoid blocking other threads.
        """
        try:
            logger.info(f"🧠 [LEARNING] Updating patterns for alert {alert_id}")

            success = final_result.get("should_send", False)
            status = final_result.get("verification_status", "UNKNOWN")

            logger.info(f"   Result: {status} | Success: {success}")
            logger.info(f"   Modifications applied: {len(modification_plan.modifications)}")

            # Get situation assessment from the intelligent logger
            situation = getattr(modification_plan, "situation_assessment", {})
            if not situation:
                # Create a simple situation assessment if not available
                situation = {
                    "confidence_level": final_result.get("confidence_level", "MEDIUM"),
                    "discrepancy_count": len(final_result.get("data_discrepancies", [])),
                    "total_modifications": len(modification_plan.modifications),
                }

            # Create pattern key
            pattern_key = (
                f"{len(modification_plan.modifications)}_"
                f"{situation.get('confidence_level', 'MEDIUM')}_"
                f"{situation.get('discrepancy_count', 0)}"
            )

            # Persist learning patterns to database (outside lock to avoid blocking)
            with get_db_session() as db:
                # Update or create learning pattern
                existing_pattern = (
                    db.query(LearningPattern).filter_by(pattern_key=pattern_key).first()
                )

                if existing_pattern:
                    # Update existing pattern
                    existing_pattern.total_occurrences += 1
                    if modification_plan.feedback_decision == FeedbackDecision.AUTO_APPLY:
                        existing_pattern.auto_apply_count += 1
                    elif modification_plan.feedback_decision == FeedbackDecision.MANUAL_REVIEW:
                        existing_pattern.manual_review_count += 1
                    else:
                        existing_pattern.ignore_count += 1

                    # Update success rate
                    if success is not None:
                        current_rate = existing_pattern.success_rate or 0.0
                        new_rate = (
                            current_rate * (existing_pattern.total_occurrences - 1)
                            + (1.0 if success else 0.0)
                        ) / existing_pattern.total_occurrences
                        existing_pattern.success_rate = new_rate

                    existing_pattern.last_updated = datetime.utcnow()
                else:
                    # Create new pattern
                    new_pattern = LearningPattern(
                        pattern_key=pattern_key,
                        modification_count=len(modification_plan.modifications),
                        confidence_level=situation.get("confidence_level", "MEDIUM"),
                        discrepancy_count=situation.get("discrepancy_count", 0),
                        total_occurrences=1,
                        auto_apply_count=1
                        if modification_plan.feedback_decision == FeedbackDecision.AUTO_APPLY
                        else 0,
                        manual_review_count=1
                        if modification_plan.feedback_decision == FeedbackDecision.MANUAL_REVIEW
                        else 0,
                        ignore_count=1
                        if modification_plan.feedback_decision == FeedbackDecision.IGNORE
                        else 0,
                        success_rate=1.0 if success else 0.0,
                    )
                    db.add(new_pattern)

                db.commit()
                logger.info(f"🧠 [LEARNING] Pattern '{pattern_key}' updated successfully")

            # RACE CONDITION FIX: Use correct lock (_learning_patterns_lock) for in-memory updates
            # This ensures thread-safe access to learning_patterns dict
            with self.intelligent_logger._learning_patterns_lock:
                # Update the in-memory learning_patterns dict with the latest data
                if existing_pattern:
                    # Pattern was updated in database, update in-memory representation
                    self.intelligent_logger.learning_patterns[pattern_key] = {
                        "modification_count": existing_pattern.modification_count,
                        "confidence_level": existing_pattern.confidence_level,
                        "discrepancy_count": existing_pattern.discrepancy_count,
                        "total_occurrences": existing_pattern.total_occurrences,
                        "auto_apply_count": existing_pattern.auto_apply_count,
                        "manual_review_count": existing_pattern.manual_review_count,
                        "ignore_count": existing_pattern.ignore_count,
                        "success_rate": existing_pattern.success_rate,
                        "last_updated": existing_pattern.last_updated.isoformat()
                        if existing_pattern.last_updated
                        else None,
                    }
                else:
                    # New pattern was created in database, add to in-memory representation
                    self.intelligent_logger.learning_patterns[pattern_key] = {
                        "modification_count": len(modification_plan.modifications),
                        "confidence_level": situation.get("confidence_level", "MEDIUM"),
                        "discrepancy_count": situation.get("discrepancy_count", 0),
                        "total_occurrences": 1,
                        "auto_apply_count": 1
                        if modification_plan.feedback_decision == FeedbackDecision.AUTO_APPLY
                        else 0,
                        "manual_review_count": 1
                        if modification_plan.feedback_decision == FeedbackDecision.MANUAL_REVIEW
                        else 0,
                        "ignore_count": 1
                        if modification_plan.feedback_decision == FeedbackDecision.IGNORE
                        else 0,
                        "success_rate": 1.0 if success else 0.0,
                        "last_updated": datetime.utcnow().isoformat(),
                    }

                logger.debug(
                    f"🧠 [LEARNING] Synchronized in-memory pattern '{pattern_key}': "
                    f"{self.intelligent_logger.learning_patterns[pattern_key]}"
                )

        except (StaleDataError, IntegrityError, OperationalError, DBAPIError) as e:
            # VPS FIX: Specific SQLAlchemy exception handling for concurrent operations
            # These errors can occur under high concurrency when multiple threads
            # try to update the same learning pattern simultaneously
            logger.error(
                f"❌ [LEARNING] Database concurrency error updating pattern '{pattern_key}': {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling
        except SQLAlchemyError as e:
            # VPS FIX: Catch-all for other SQLAlchemy errors
            logger.error(
                f"❌ [LEARNING] Database error updating pattern '{pattern_key}': {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling
        except Exception as e:
            # VPS FIX: Catch-all for unexpected errors
            logger.error(
                f"❌ [LEARNING] Unexpected error updating pattern '{pattern_key}': {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling

    def _persist_modification(
        self,
        alert_id: int,
        match_id: str,
        modification: SuggestedModification,
        applied: bool = False,
        success: bool = False,
        error_message: str = None,
        component_communications: dict = None,
    ):
        """
        Persist a modification to the database.

        VPS FIX: Propagate database errors to caller for proper error handling.
        Previously, exceptions were only logged and not propagated, which could lead
        to inconsistent state where the caller assumes data was persisted when it wasn't.
        """
        try:
            with get_db_session() as db:
                mod_record = ModificationHistory(
                    alert_id=alert_id,
                    match_id=match_id,
                    modification_type=modification.type.value,
                    original_value=str(modification.original_value),
                    suggested_value=str(modification.suggested_value),
                    reason=modification.reason,
                    priority=modification.priority.value,
                    applied=applied,
                    success=success,
                    error_message=error_message,
                    verification_context=json.dumps(modification.verification_context, default=str),
                    component_communications=json.dumps(
                        component_communications or {}, default=str
                    ),
                    applied_at=datetime.utcnow() if applied else None,
                )

                db.add(mod_record)
                db.commit()
                logger.debug(
                    f"✅ [PERSIST] Modification {modification.id} saved to database (ID: {mod_record.id})"
                )

        except (StaleDataError, IntegrityError, OperationalError, DBAPIError) as e:
            # VPS FIX: Specific SQLAlchemy exception handling for concurrent operations
            # These errors can occur under high concurrency when multiple threads
            # try to persist modifications simultaneously
            logger.error(
                f"❌ [PERSIST] Database concurrency error persisting modification {modification.id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling
        except SQLAlchemyError as e:
            # VPS FIX: Catch-all for other SQLAlchemy errors
            logger.error(
                f"❌ [PERSIST] Database error persisting modification {modification.id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling
        except Exception as e:
            # VPS FIX: Catch-all for unexpected errors
            logger.error(
                f"❌ [PERSIST] Unexpected error persisting modification {modification.id}: {e}",
                exc_info=True,
            )
            raise  # Re-raise to propagate to caller for proper error handling


class ComponentCommunicator:
    """Helper class for component communication."""

    def __init__(
        self, name: str, communication_func: "Callable[[SuggestedModification, str], dict]"
    ):
        self.name = name
        self.communication_func = communication_func

    def communicate(self, modification: SuggestedModification, message: str) -> dict:
        """Communicate with the component."""
        return self.communication_func(modification, message)


# Singleton instance
_step_by_step_loop_instance: StepByStepFeedbackLoop | None = None
_step_by_step_loop_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_step_by_step_feedback_loop() -> StepByStepFeedbackLoop:
    """
    Get or create the singleton StepByStepFeedbackLoop instance.

    V12.2: Fixed lazy initialization race condition.
    Multiple threads can safely call this function concurrently.
    """
    global _step_by_step_loop_instance
    if _step_by_step_loop_instance is None:
        with _step_by_step_loop_instance_init_lock:
            # Double-checked locking pattern for thread safety
            if _step_by_step_loop_instance is None:
                _step_by_step_loop_instance = StepByStepFeedbackLoop()
    return _step_by_step_loop_instance
