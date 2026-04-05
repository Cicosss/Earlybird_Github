"""
Intelligent Modification Logger and Step-by-Step Feedback System

This component implements the hybrid approach:
1. Log all modifications suggested by Final Verifier
2. Intelligently decide when to apply automatic feedback loop
3. Apply modifications step-by-step with component communication
4. Track learning and improvement patterns

VPS CRITICAL FIXES (2026-03-05):
- Replaced asyncio.Lock() with threading.Lock() for thread-safe access to in-memory structures
- Added learning patterns loading from database on startup
- Removed in-memory modification_history to prevent unbounded memory growth
- Locks are now properly used to protect learning_patterns and component_registry
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.database.models import LearningPattern, Match, NewsLog, get_db_session

logger = logging.getLogger(__name__)


class ModificationType(Enum):
    """Types of modifications that can be suggested."""

    MARKET_CHANGE = "market_change"
    SCORE_ADJUSTMENT = "score_adjustment"
    DATA_CORRECTION = "data_correction"
    REASONING_UPDATE = "reasoning_update"


class ModificationPriority(Enum):
    """Priority levels for modifications."""

    CRITICAL = "critical"  # Must be applied
    HIGH = "high"  # Should be applied
    MEDIUM = "medium"  # Can be applied
    LOW = "low"  # Optional


class FeedbackDecision(Enum):
    """Decision on feedback loop application.

    Note:
        - AUTO_APPLY: Automatically apply modifications via feedback loop
        - MANUAL_REVIEW: Log for manual human review
        - IGNORE: No modifications needed (early exit, not a decision type)

    IGNORE is returned by analyze_verifier_suggestions() when no modifications
    are needed, before the decision logic is invoked. The decision logic
    (_make_feedback_decision) only returns AUTO_APPLY or MANUAL_REVIEW.
    """

    AUTO_APPLY = "auto_apply"  # Automatic feedback loop
    MANUAL_REVIEW = "manual_review"  # Log for manual review
    IGNORE = "ignore"  # Ignore modification


@dataclass
class SuggestedModification:
    """Represents a modification suggested by the verifier."""

    id: str
    type: ModificationType
    priority: ModificationPriority
    original_value: Any
    suggested_value: Any
    reason: str
    confidence: float  # 0-1
    impact_assessment: str
    verification_context: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModificationPlan:
    """Step-by-step plan for applying modifications."""

    alert_id: str
    modifications: list[SuggestedModification]
    feedback_decision: FeedbackDecision
    estimated_success_rate: float
    risk_level: str
    component_communication: dict[str, str]
    execution_order: list[str]


class IntelligentModificationLogger:
    """
    Intelligent system for logging, evaluating, and applying modifications
    suggested by the Final Verifier with step-by-step execution.

    VPS CRITICAL FIXES:
    - Thread-safe access using threading.Lock() for all in-memory structures
    - Learning patterns loaded from database on startup
    - Removed in-memory modification_history (data persisted in database)
    - Locks are now properly used to protect learning_patterns and component_registry
    """

    def __init__(self):
        # VPS FIX #1: Thread-safe locks for concurrent access
        # Using threading.Lock() because all methods are synchronous
        self._learning_patterns_lock = threading.Lock()
        # Note: _component_registry_lock removed (unused) - component_registry
        # is only modified by StepByStepFeedbackLoop with its own lock

        # VPS FIX #2: Learning patterns loaded from database
        self.learning_patterns = {}
        self._load_learning_patterns_from_db()

        # VPS FIX #3: Removed modification_history (unbounded memory growth)
        # Data is already persisted in ModificationHistory database table

        # Component registry for tracking component communications
        # This is modified by StepByStepFeedbackLoop with its own lock
        self.component_registry = {}

    def _load_learning_patterns_from_db(self):
        """
        VPS FIX #2: Load existing learning patterns from database on startup.

        This ensures that learning persists across restarts and the system
        doesn't start with zero knowledge each time.
        """
        try:
            with get_db_session() as db:
                patterns = db.query(LearningPattern).all()

                # Thread-safe access to learning_patterns
                with self._learning_patterns_lock:
                    for pattern in patterns:
                        # Convert database pattern to in-memory format
                        pattern_key = pattern.pattern_key
                        self.learning_patterns[pattern_key] = {
                            "modification_count": pattern.modification_count,
                            "confidence_level": pattern.confidence_level,
                            "discrepancy_count": pattern.discrepancy_count,
                            "total_occurrences": pattern.total_occurrences,
                            "auto_apply_count": pattern.auto_apply_count,
                            "manual_review_count": pattern.manual_review_count,
                            "ignore_count": pattern.ignore_count,
                            "success_rate": pattern.success_rate,
                            "last_updated": pattern.last_updated.isoformat()
                            if pattern.last_updated
                            else None,
                        }

                logger.info(
                    f"🧠 [INTELLIGENT LOGGER] Loaded {len(patterns)} learning patterns from database"
                )
        except Exception as e:
            logger.error(f"❌ [INTELLIGENT LOGGER] Failed to load learning patterns: {e}")
            # Thread-safe access to learning_patterns
            with self._learning_patterns_lock:
                # Continue with empty patterns - system will learn from scratch
                self.learning_patterns = {}

    def analyze_verifier_suggestions(
        self,
        match: Match,
        analysis: NewsLog,
        verification_result: dict,
        alert_data: dict,
        context_data: dict,
    ) -> ModificationPlan:
        """
        Analyze verifier suggestions and create intelligent modification plan.

        This is the brain of the system that decides:
        1. What modifications are needed
        2. In what order to apply them
        3. Whether to use automatic feedback or manual review
        4. How components should communicate
        """
        # Input validation
        if not match or not analysis or not verification_result:
            logger.warning("Invalid input to analyze_verifier_suggestions")
            return ModificationPlan(
                alert_id="invalid",
                modifications=[],
                feedback_decision=FeedbackDecision.IGNORE,
                estimated_success_rate=0.0,
                risk_level="HIGH",
                component_communication={},
                execution_order=[],
            )

        logger.info(
            f"🧠 [INTELLIGENT LOGGER] Analyzing verifier suggestions for alert {analysis.id}"
        )

        # Step 1: Parse and classify modifications
        modifications = self._parse_modifications(verification_result, alert_data, context_data)

        if not modifications:
            logger.info("🧠 [INTELLIGENT LOGGER] No modifications needed")
            return ModificationPlan(
                alert_id=str(analysis.id),
                modifications=[],
                feedback_decision=FeedbackDecision.IGNORE,
                estimated_success_rate=1.0,
                risk_level="LOW",
                component_communication={},
                execution_order=[],
            )

        # Step 2: Assess overall situation
        situation_assessment = self._assess_situation(
            match, analysis, modifications, verification_result, context_data
        )

        # Step 3: Make feedback decision
        feedback_decision = self._make_feedback_decision(
            modifications, situation_assessment, verification_result
        )

        # Step 4: Create execution plan
        execution_plan = self._create_execution_plan(
            modifications, feedback_decision, situation_assessment, analysis
        )

        # Step 5: Log for learning
        self._log_for_learning(analysis.id, modifications, feedback_decision, situation_assessment)

        logger.info(
            f"🧠 [INTELLIGENT LOGGER] Decision: {feedback_decision.value} | "
            f"Modifications: {len(modifications)} | Risk: {execution_plan.risk_level}"
        )

        return execution_plan

    def _parse_modifications(
        self, verification_result: dict, alert_data: dict, context_data: dict
    ) -> list[SuggestedModification]:
        """Parse and classify modifications from verifier response."""
        modifications: list[dict[str, Any]] = []
        suggestion_text = verification_result.get("suggested_modifications", "")
        discrepancies = verification_result.get("data_discrepancies", [])

        # Parse market changes
        market_mod = self._parse_market_change(suggestion_text, alert_data, verification_result)
        if market_mod:
            modifications.append(market_mod)

        # Parse score adjustments
        score_mod = self._parse_score_adjustment(suggestion_text, alert_data, verification_result)
        if score_mod:
            modifications.append(score_mod)

        # Parse data corrections from discrepancies
        for discrepancy in discrepancies:
            data_mod = self._parse_data_correction(discrepancy, alert_data, verification_result)
            if data_mod:
                modifications.append(data_mod)

        # Parse reasoning updates
        reasoning_mod = self._parse_reasoning_update(verification_result, alert_data)
        if reasoning_mod:
            modifications.append(reasoning_mod)

        return modifications

    def _map_confidence_level(self, confidence_level: str) -> float:
        """Map confidence_level string to float value (0-1 range).

        Args:
            confidence_level: String value "HIGH", "MEDIUM", or "LOW"

        Returns:
            Float value: 1.0 for HIGH, 0.7 for MEDIUM, 0.5 for LOW
        """
        mapping = {
            "HIGH": 1.0,
            "MEDIUM": 0.7,
            "LOW": 0.5,
        }
        return mapping.get(confidence_level, 0.5)

    def _parse_market_change(
        self, suggestion_text: str, alert_data: dict, verification_result: dict
    ) -> SuggestedModification | None:
        """Parse market change suggestions."""
        current_market = alert_data.get("recommended_market", "")

        # Look for market change patterns
        # Expanded pattern set to capture more variations from verifier responses
        market_patterns = [
            # Direct change patterns
            (r"change.*market.*over.*under", "Over to Under"),
            (r"change.*market.*under.*over", "Under to Over"),
            # Switch patterns
            (r"switch.*from.*over.*to.*under", "Over to Under"),
            (r"switch.*from.*under.*to.*over", "Under to Over"),
            # Replace patterns
            (r"replace.*over.*with.*under", "Over to Under"),
            (r"replace.*under.*with.*over", "Under to Over"),
            # Should be patterns
            (r"market.*should be.*over", "Switch to Over"),
            (r"market.*should be.*under", "Switch to Under"),
            # Consider instead patterns
            (r"consider.*under.*instead.*of.*over", "Under instead of Over"),
            (r"consider.*over.*instead.*of.*under", "Over instead of Under"),
            # Use instead patterns
            (r"use.*under.*instead.*of.*over", "Under instead of Over"),
            (r"use.*over.*instead.*of.*under", "Over instead of Under"),
            # Better suited patterns
            (r"better.*suited.*for.*under", "Under instead of Over"),
            (r"better.*suited.*for.*over", "Over instead of Under"),
            # More appropriate patterns
            (r"more.*appropriate.*under", "Under instead of Over"),
            (r"more.*appropriate.*over", "Over instead of Under"),
            # Recommendation patterns
            (r"recommend.*under.*market", "Switch to Under"),
            (r"recommend.*over.*market", "Switch to Over"),
            # Prefer patterns
            (r"prefer.*under.*over.*over", "Under instead of Over"),
            (r"prefer.*over.*over.*under", "Over instead of Under"),
        ]

        import re

        for pattern, description in market_patterns:
            if re.search(pattern, suggestion_text, re.IGNORECASE):
                # Determine new market
                new_market = self._calculate_new_market(current_market, description)
                if new_market and new_market != current_market:
                    return SuggestedModification(
                        id=f"market_change_{datetime.now().timestamp()}",
                        type=ModificationType.MARKET_CHANGE,
                        priority=ModificationPriority.HIGH,
                        original_value=current_market,
                        suggested_value=new_market,
                        reason=f"Market direction corrected: {description}",
                        confidence=self._map_confidence_level(
                            verification_result.get("confidence_level", "LOW")
                        ),
                        impact_assessment="HIGH",
                        verification_context={
                            "original_confidence": verification_result.get("confidence_level"),
                            "discrepancies": verification_result.get("data_discrepancies", []),
                        },
                    )

        return None

    def _parse_score_adjustment(
        self, suggestion_text: str, alert_data: dict, verification_result: dict
    ) -> SuggestedModification | None:
        """Parse score adjustment suggestions."""
        current_score = alert_data.get("score", 8)

        # Look for score adjustment patterns
        score_patterns = [
            (r"reduce.*score", "reduce"),
            (r"lower.*score", "reduce"),
            (r"adjust.*score.*down", "reduce"),
            (r"increase.*score", "increase"),
            (r"adjust.*score.*up", "increase"),
        ]

        import re

        for pattern, action in score_patterns:
            if re.search(pattern, suggestion_text, re.IGNORECASE):
                # Calculate new score
                if action == "reduce":
                    new_score = max(5, current_score - 2)
                else:  # increase
                    new_score = min(10, current_score + 1)

                return SuggestedModification(
                    id=f"score_adjust_{datetime.now().timestamp()}",
                    type=ModificationType.SCORE_ADJUSTMENT,
                    priority=ModificationPriority.MEDIUM,
                    original_value=current_score,
                    suggested_value=new_score,
                    reason=f"Score {action}d based on verification",
                    confidence=0.7,
                    impact_assessment="MEDIUM",
                    verification_context={
                        "original_score": current_score,
                        "adjustment_reason": action,
                    },
                )

        return None

    def _parse_data_correction(
        self, discrepancy: dict | object, alert_data: dict, verification_result: dict
    ) -> SuggestedModification | None:
        """
        Parse data correction from discrepancy.

        V3.0: Handles both dict and DataDiscrepancy objects with REAL values.
        """
        # Handle both dict and DataDiscrepancy objects
        if isinstance(discrepancy, dict):
            field = discrepancy.get("field", "")
            impact = discrepancy.get("impact", "LOW")
            fotmob_value = discrepancy.get("fotmob_value", "N/A")
            intelligence_value = discrepancy.get(
                "perplexity_value", discrepancy.get("intelligence_value", "N/A")
            )
            description = discrepancy.get("description", "")
        else:
            # DataDiscrepancy object
            field = getattr(discrepancy, "field", "")
            impact = getattr(discrepancy, "impact", "LOW")
            fotmob_value = getattr(discrepancy, "fotmob_value", "N/A")
            intelligence_value = getattr(discrepancy, "intelligence_value", "N/A")
            description = getattr(discrepancy, "description", "")

        # Determine priority based on impact
        if impact == "HIGH":
            priority = ModificationPriority.CRITICAL
            confidence = 0.9
        elif impact == "MEDIUM":
            priority = ModificationPriority.HIGH
            confidence = 0.8
        elif impact == "LOW":
            priority = ModificationPriority.LOW
            confidence = 0.6
        else:
            # Unexpected impact level - default to MEDIUM for safety
            priority = ModificationPriority.MEDIUM
            confidence = 0.7

        # Log the data correction with real values
        logger.info(
            f"🔧 [DATA CORRECTION] {field.upper()}: "
            f"FotMob={fotmob_value} → Intelligence={intelligence_value}"
        )

        return SuggestedModification(
            id=f"data_correction_{field}_{datetime.now().timestamp()}",
            type=ModificationType.DATA_CORRECTION,
            priority=priority,
            original_value=fotmob_value,
            suggested_value=intelligence_value,
            reason=description or f"Correct {field} data based on IntelligenceRouter verification",
            confidence=confidence,
            impact_assessment=impact,
            verification_context={
                "discrepancy_type": "data_mismatch",
                "field_importance": field,
                "fotmob_value": fotmob_value,
                "intelligence_value": intelligence_value,
            },
        )

    def _parse_reasoning_update(
        self, verification_result: dict, alert_data: dict
    ) -> SuggestedModification | None:
        """Parse reasoning update suggestions."""
        key_weaknesses = verification_result.get("key_weaknesses", [])

        if key_weaknesses:
            return SuggestedModification(
                id=f"reasoning_update_{datetime.now().timestamp()}",
                type=ModificationType.REASONING_UPDATE,
                priority=ModificationPriority.MEDIUM,
                original_value=alert_data.get("reasoning", ""),
                suggested_value=f"Updated reasoning addressing: {', '.join(key_weaknesses[:2])}",
                reason="Reasoning updated based on verifier feedback",
                confidence=0.6,
                impact_assessment="MEDIUM",
                verification_context={"weaknesses_addressed": key_weaknesses},
            )

        return None

    def _assess_situation(
        self,
        match: Match,
        analysis: NewsLog,
        modifications: list[SuggestedModification],
        verification_result: dict,
        context_data: dict,
    ) -> dict:
        """Assess the overall situation for decision making."""

        # Count modifications by priority
        critical_count = len(
            [m for m in modifications if m.priority == ModificationPriority.CRITICAL]
        )
        high_count = len([m for m in modifications if m.priority == ModificationPriority.HIGH])
        medium_count = len([m for m in modifications if m.priority == ModificationPriority.MEDIUM])
        low_count = len([m for m in modifications if m.priority == ModificationPriority.LOW])

        # Calculate risk factors
        discrepancy_count = len(verification_result.get("data_discrepancies", []))
        confidence_level = verification_result.get("confidence_level", "LOW")
        original_score = analysis.score or 0

        # Assess data quality
        data_quality_score = self._calculate_data_quality(context_data)

        # Component health check
        component_health = self._check_component_health(context_data)

        return {
            "critical_modifications": critical_count,
            "high_modifications": high_count,
            "medium_modifications": medium_count,
            "low_modifications": low_count,
            "total_modifications": len(modifications),
            "discrepancy_count": discrepancy_count,
            "confidence_level": confidence_level,
            "original_score": original_score,
            "data_quality_score": data_quality_score,
            "component_health": component_health,
            "risk_factors": {
                "high_discrepancies": discrepancy_count > 2,
                "low_confidence": confidence_level == "LOW",
                "critical_issues": critical_count > 0,
                "component_stress": component_health < 0.7,
            },
        }

    def _make_feedback_decision(
        self, modifications: list[SuggestedModification], situation: dict, verification_result: dict
    ) -> FeedbackDecision:
        """
        Make intelligent decision about feedback loop application.

        This is the core decision engine that follows the hybrid approach.
        """

        # Rule 1: CRITICAL modifications always need attention
        if situation["critical_modifications"] > 0:
            return FeedbackDecision.MANUAL_REVIEW

        # Rule 2: Too many modifications = manual review
        if situation["total_modifications"] > 3:
            return FeedbackDecision.MANUAL_REVIEW

        # Rule 3: High risk factors = manual review
        risk_factors = situation["risk_factors"]
        if sum(risk_factors.values()) >= 2:
            return FeedbackDecision.MANUAL_REVIEW

        # Rule 4: Low confidence + high discrepancies = manual review
        if situation["confidence_level"] == "LOW" and situation["discrepancy_count"] >= 2:
            return FeedbackDecision.MANUAL_REVIEW

        # Rule 5: Safe cases for automatic feedback
        safe_conditions = [
            situation["total_modifications"] <= 2,
            situation["confidence_level"] in ["HIGH", "MEDIUM"],
            situation["discrepancy_count"] <= 1,
            all(
                m.priority
                in [
                    ModificationPriority.LOW,
                    ModificationPriority.MEDIUM,
                    ModificationPriority.HIGH,
                ]
                for m in modifications
            ),
            situation["data_quality_score"] >= 0.7,
            situation["component_health"] >= 0.8,
        ]

        if all(safe_conditions):
            return FeedbackDecision.AUTO_APPLY

        # Rule 6: Borderline cases = manual review
        return FeedbackDecision.MANUAL_REVIEW

    def _create_execution_plan(
        self,
        modifications: list[SuggestedModification],
        feedback_decision: FeedbackDecision,
        situation: dict,
        analysis: NewsLog,
    ) -> ModificationPlan:
        """Create step-by-step execution plan with component communication.

        Args:
            modifications: List of suggested modifications
            feedback_decision: Whether to auto-apply or manual review
            situation: Situation assessment dictionary
            analysis: Original NewsLog analysis (needed for alert_id)
        """

        # Sort modifications by priority and dependency
        sorted_modifications = self._sort_modifications_by_priority(modifications)

        # Calculate success probability
        success_rate = self._calculate_success_rate(sorted_modifications, situation)

        # Determine risk level
        risk_level = self._determine_risk_level(situation, success_rate)

        # Plan component communication
        component_communication = self._plan_component_communication(sorted_modifications)

        # Create execution order
        execution_order = [mod.id for mod in sorted_modifications]

        return ModificationPlan(
            alert_id=str(analysis.id),  # Use original alert ID for database referential integrity
            modifications=sorted_modifications,
            feedback_decision=feedback_decision,
            estimated_success_rate=success_rate,
            risk_level=risk_level,
            component_communication=component_communication,
            execution_order=execution_order,
        )

    def _sort_modifications_by_priority(
        self, modifications: list[SuggestedModification]
    ) -> list[SuggestedModification]:
        """Sort modifications by priority and logical dependencies."""
        priority_order = {
            ModificationPriority.CRITICAL: 0,
            ModificationPriority.HIGH: 1,
            ModificationPriority.MEDIUM: 2,
            ModificationPriority.LOW: 3,
        }

        # Sort by priority first
        sorted_by_priority = sorted(modifications, key=lambda m: priority_order[m.priority])

        # Then apply logical ordering (data corrections before market changes)
        data_corrections = [
            m for m in sorted_by_priority if m.type == ModificationType.DATA_CORRECTION
        ]
        other_modifications = [
            m for m in sorted_by_priority if m.type != ModificationType.DATA_CORRECTION
        ]

        return data_corrections + other_modifications

    def _calculate_success_rate(
        self, modifications: list[SuggestedModification], situation: dict
    ) -> float:
        """Calculate estimated success rate for the modification plan."""
        base_success = 0.8

        # Reduce success based on risk factors
        if situation["confidence_level"] == "LOW":
            base_success -= 0.2
        elif situation["confidence_level"] == "MEDIUM":
            base_success -= 0.1

        # Reduce based on modification count
        base_success -= min(0.3, len(modifications) * 0.1)

        # Reduce based on component health
        base_success *= situation["component_health"]

        return max(0.1, min(0.95, base_success))

    def _determine_risk_level(self, situation: dict, success_rate: float) -> str:
        """Determine overall risk level."""
        if success_rate >= 0.8 and situation["critical_modifications"] == 0:
            return "LOW"
        elif success_rate >= 0.6 and situation["critical_modifications"] <= 1:
            return "MEDIUM"
        else:
            return "HIGH"

    def _plan_component_communication(
        self, modifications: list[SuggestedModification]
    ) -> dict[str, str]:
        """Plan how components should communicate during modification."""
        communication = {}

        for mod in modifications:
            if mod.type == ModificationType.MARKET_CHANGE:
                communication["analyzer"] = (
                    f"Update market analysis from {mod.original_value} to {mod.suggested_value}"
                )
                communication["math_engine"] = (
                    f"Recalculate edge for new market: {mod.suggested_value}"
                )
            elif mod.type == ModificationType.SCORE_ADJUSTMENT:
                communication["threshold_manager"] = (
                    f"Adjust alert threshold consideration for score {mod.suggested_value}"
                )
                communication["health_monitor"] = "Track modified alert performance with new score"
            elif mod.type == ModificationType.DATA_CORRECTION:
                communication["data_validator"] = (
                    f"Validate corrected {mod.id} data: {mod.suggested_value}"
                )
                communication["verification_layer"] = (
                    f"Re-verify with corrected {mod.original_value} → {mod.suggested_value}"
                )

        return communication

    def _calculate_data_quality(self, context_data: dict) -> float:
        """Calculate overall data quality score."""
        quality_factors: list[dict[str, Any]] = []

        # Check verification layer confidence
        if context_data.get("verification_info"):
            verif_conf = context_data["verification_info"].get("confidence", "LOW")
            quality_factors.append(
                0.9 if verif_conf == "HIGH" else 0.7 if verif_conf == "MEDIUM" else 0.5
            )

        # Check math edge reliability
        if context_data.get("math_edge"):
            edge = context_data["math_edge"].get("edge", 0)
            quality_factors.append(min(1.0, edge / 10.0))

        # Check injury intel completeness
        if context_data.get("injury_intel"):
            injury = context_data["injury_intel"]
            if injury.get("home_severity") and injury.get("away_severity"):
                quality_factors.append(0.8)
            else:
                quality_factors.append(0.6)

        return sum(quality_factors) / len(quality_factors) if quality_factors else 0.5

    def _check_component_health(self, context_data: dict) -> float:
        """Check health of all components."""
        health_scores: list[dict[str, Any]] = []

        # Each component contributes to health
        components = [
            "verification_info",
            "math_edge",
            "injury_intel",
            "referee_intel",
            "twitter_intel",
        ]

        for component in components:
            if context_data.get(component):
                health_scores.append(0.8)  # Component present and functional
            else:
                health_scores.append(0.6)  # Component missing but not critical

        return sum(health_scores) / len(health_scores)

    def _log_for_learning(
        self,
        alert_id: str,
        modifications: list[SuggestedModification],
        decision: FeedbackDecision,
        situation: dict,
    ):
        """
        Log modification patterns for system learning.

        VPS CRITICAL FIXES:
        - Removed modification_history append (unbounded memory growth)
        - Data is persisted in ModificationHistory database table by StepByStepFeedbackLoop
        - Added thread-safe access to learning_patterns using threading.Lock

        DATA STRUCTURE FIX (2026-03-18):
        - learning_patterns now uses consistent dict structure with statistics
        - This matches _load_learning_patterns_from_db() and step_by_step_feedback._update_learning_patterns()
        - The structure is: {modification_count, confidence_level, discrepancy_count,
                            total_occurrences, auto_apply_count, manual_review_count,
                            ignore_count, success_rate, last_updated}
        - StepByStepFeedbackLoop._update_learning_patterns() will persist to database and
          update the in-memory pattern with accurate statistics from the database.
        """

        # VPS FIX #3: Removed modification_history (unbounded memory growth)
        # Data is already persisted in ModificationHistory database table
        # by StepByStepFeedbackLoop._persist_modification()
        # The log_entry below is no longer needed and has been removed

        # Update learning patterns with thread-safe access
        pattern_key = (
            f"{len(modifications)}_{situation['confidence_level']}_{situation['discrepancy_count']}"
        )

        # VPS FIX: Thread-safe access to learning_patterns
        # DATA STRUCTURE FIX: Use dict with statistics (consistent with DB load and step_by_step_feedback)
        with self._learning_patterns_lock:
            if pattern_key not in self.learning_patterns:
                # Initialize new pattern with dict structure (matches LearningPattern model)
                self.learning_patterns[pattern_key] = {
                    "modification_count": len(modifications),
                    "confidence_level": situation.get("confidence_level", "MEDIUM"),
                    "discrepancy_count": situation.get("discrepancy_count", 0),
                    "total_occurrences": 0,
                    "auto_apply_count": 0,
                    "manual_review_count": 0,
                    "ignore_count": 0,
                    "success_rate": None,
                    "last_updated": None,
                }

            # Increment occurrence counters (will be properly updated by StepByStepFeedbackLoop)
            pattern = self.learning_patterns[pattern_key]
            pattern["total_occurrences"] += 1

            # Increment decision-specific counter
            if decision == FeedbackDecision.AUTO_APPLY:
                pattern["auto_apply_count"] += 1
            elif decision == FeedbackDecision.MANUAL_REVIEW:
                pattern["manual_review_count"] += 1
            elif decision == FeedbackDecision.IGNORE:
                pattern["ignore_count"] += 1

            # Update timestamp
            pattern["last_updated"] = datetime.now(timezone.utc).isoformat()

        logger.debug(
            f"🧠 [INTELLIGENT LOGGER] Updated learning pattern '{pattern_key}': "
            f"total={pattern['total_occurrences']}, decision={decision.value}"
        )

    def _calculate_new_market(self, current_market: str, description: str) -> str | None:
        """Calculate the new market based on current market and description."""
        current_lower = current_market.lower()

        if "over to under" in description.lower():
            return current_market.replace("Over", "Under").replace("over", "under")
        elif "under to over" in description.lower():
            return current_market.replace("Under", "Over").replace("under", "over")
        elif "switch to over" in description.lower():
            if "under" in current_lower:
                return current_market.replace("Under", "Over").replace("under", "over")
        elif "switch to under" in description.lower():
            if "over" in current_lower:
                return current_market.replace("Over", "Under").replace("over", "under")
        elif "under instead of over" in description.lower():
            if "over" in current_lower:
                return current_market.replace("Over", "Under").replace("over", "under")
        elif "over instead of under" in description.lower():
            if "under" in current_lower:
                return current_market.replace("Under", "Over").replace("under", "over")

        return None


# Singleton instance
_intelligent_logger_instance: IntelligentModificationLogger | None = None
_intelligent_logger_instance_init_lock = threading.Lock()  # Lock for thread-safe initialization


def get_intelligent_modification_logger() -> IntelligentModificationLogger:
    """Get or create the singleton IntelligentModificationLogger instance.

    VPS FIX: Uses double-checked locking pattern for thread-safe singleton initialization.
    This prevents race conditions when multiple threads call this function simultaneously.
    """
    global _intelligent_logger_instance
    if _intelligent_logger_instance is None:
        with _intelligent_logger_instance_init_lock:
            # Double-check after acquiring lock to prevent race condition
            if _intelligent_logger_instance is None:
                _intelligent_logger_instance = IntelligentModificationLogger()
    return _intelligent_logger_instance
