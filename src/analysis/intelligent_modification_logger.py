"""
Intelligent Modification Logger and Step-by-Step Feedback System

This component implements the hybrid approach:
1. Log all modifications suggested by Final Verifier
2. Intelligently decide when to apply automatic feedback loop
3. Apply modifications step-by-step with component communication
4. Track learning and improvement patterns
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import json

from src.database.models import NewsLog, SessionLocal
from src.database.models import Match

logger = logging.getLogger(__name__)


class ModificationType(Enum):
    """Types of modifications that can be suggested."""
    MARKET_CHANGE = "market_change"
    SCORE_ADJUSTMENT = "score_adjustment"
    DATA_CORRECTION = "data_correction"
    REASONING_UPDATE = "reasoning_update"
    COMBO_MODIFICATION = "combo_modification"


class ModificationPriority(Enum):
    """Priority levels for modifications."""
    CRITICAL = "critical"  # Must be applied
    HIGH = "high"         # Should be applied
    MEDIUM = "medium"     # Can be applied
    LOW = "low"          # Optional


class FeedbackDecision(Enum):
    """Decision on feedback loop application."""
    AUTO_APPLY = "auto_apply"          # Automatic feedback loop
    MANUAL_REVIEW = "manual_review"    # Log for manual review
    IGNORE = "ignore"                  # Ignore modification


@dataclass
class SuggestedModification:
    """Represents a modification suggested by the verifier."""
    id: str
    type: ModificationType
    priority: ModificationPriority
    original_value: any
    suggested_value: any
    reason: str
    confidence: float  # 0-1
    impact_assessment: str
    verification_context: Dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModificationPlan:
    """Step-by-step plan for applying modifications."""
    alert_id: str
    modifications: List[SuggestedModification]
    feedback_decision: FeedbackDecision
    estimated_success_rate: float
    risk_level: str
    component_communication: Dict[str, str]
    execution_order: List[str]


class IntelligentModificationLogger:
    """
    Intelligent system for logging, evaluating, and applying modifications
    suggested by the Final Verifier with step-by-step execution.
    """
    
    def __init__(self):
        self.modification_history = []
        self.learning_patterns = {}
        self.component_registry = {}
        
    def analyze_verifier_suggestions(
        self,
        match: Match,
        analysis: NewsLog,
        verification_result: Dict,
        alert_data: Dict,
        context_data: Dict
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
                execution_order=[]
            )
        
        logger.info(f"🧠 [INTELLIGENT LOGGER] Analyzing verifier suggestions for alert {analysis.id}")
        
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
                execution_order=[]
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
            modifications, feedback_decision, situation_assessment
        )
        
        # Step 5: Log for learning
        self._log_for_learning(analysis.id, modifications, feedback_decision, situation_assessment)
        
        logger.info(f"🧠 [INTELLIGENT LOGGER] Decision: {feedback_decision.value} | "
                   f"Modifications: {len(modifications)} | Risk: {execution_plan.risk_level}")
        
        return execution_plan
    
    def _parse_modifications(
        self,
        verification_result: Dict,
        alert_data: Dict,
        context_data: Dict
    ) -> List[SuggestedModification]:
        """Parse and classify modifications from verifier response."""
        modifications = []
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
    
    def _parse_market_change(
        self,
        suggestion_text: str,
        alert_data: Dict,
        verification_result: Dict
    ) -> Optional[SuggestedModification]:
        """Parse market change suggestions."""
        current_market = alert_data.get("recommended_market", "")
        
        # Look for market change patterns
        market_patterns = [
            (r"change.*market.*over.*under", "Over to Under"),
            (r"change.*market.*under.*over", "Under to Over"),
            (r"market.*should be.*over", "Switch to Over"),
            (r"market.*should be.*under", "Switch to Under"),
            (r"consider.*under.*instead", "Under instead of Over"),
            (r"consider.*over.*instead", "Over instead of Under")
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
                        confidence=verification_result.get("confidence_level", "LOW") == "HIGH",
                        impact_assessment="HIGH",
                        verification_context={
                            "original_confidence": verification_result.get("confidence_level"),
                            "discrepancies": verification_result.get("data_discrepancies", [])
                        }
                    )
        
        return None
    
    def _parse_score_adjustment(
        self,
        suggestion_text: str,
        alert_data: Dict,
        verification_result: Dict
    ) -> Optional[SuggestedModification]:
        """Parse score adjustment suggestions."""
        current_score = alert_data.get("score", 8)
        
        # Look for score adjustment patterns
        score_patterns = [
            (r"reduce.*score", "reduce"),
            (r"lower.*score", "reduce"),
            (r"adjust.*score.*down", "reduce"),
            (r"increase.*score", "increase"),
            (r"adjust.*score.*up", "increase")
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
                        "adjustment_reason": action
                    }
                )
        
        return None
    
    def _parse_data_correction(
        self,
        discrepancy: Dict,
        alert_data: Dict,
        verification_result: Dict
    ) -> Optional[SuggestedModification]:
        """Parse data correction from discrepancy."""
        field = discrepancy.get("field", "")
        impact = discrepancy.get("impact", "LOW")
        
        if impact == "HIGH":
            priority = ModificationPriority.CRITICAL
        elif impact == "MEDIUM":
            priority = ModificationPriority.HIGH
        else:
            priority = ModificationPriority.MEDIUM
        
        return SuggestedModification(
            id=f"data_correction_{field}_{datetime.now().timestamp()}",
            type=ModificationType.DATA_CORRECTION,
            priority=priority,
            original_value=discrepancy.get("fotmob_value"),
            suggested_value=discrepancy.get("perplexity_value"),
            reason=discrepancy.get("description", ""),
            confidence=0.8 if impact == "HIGH" else 0.6,
            impact_assessment=impact,
            verification_context={
                "discrepancy_type": "data_mismatch",
                "field_importance": field
            }
        )
    
    def _parse_reasoning_update(
        self,
        verification_result: Dict,
        alert_data: Dict
    ) -> Optional[SuggestedModification]:
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
                verification_context={
                    "weaknesses_addressed": key_weaknesses
                }
            )
        
        return None
    
    def _assess_situation(
        self,
        match: Match,
        analysis: NewsLog,
        modifications: List[SuggestedModification],
        verification_result: Dict,
        context_data: Dict
    ) -> Dict:
        """Assess the overall situation for decision making."""
        
        # Count modifications by priority
        critical_count = len([m for m in modifications if m.priority == ModificationPriority.CRITICAL])
        high_count = len([m for m in modifications if m.priority == ModificationPriority.HIGH])
        medium_count = len([m for m in modifications if m.priority == ModificationPriority.MEDIUM])
        
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
                "component_stress": component_health < 0.7
            }
        }
    
    def _make_feedback_decision(
        self,
        modifications: List[SuggestedModification],
        situation: Dict,
        verification_result: Dict
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
            all(m.priority in [ModificationPriority.MEDIUM, ModificationPriority.HIGH] for m in modifications),
            situation["data_quality_score"] >= 0.7,
            situation["component_health"] >= 0.8
        ]
        
        if all(safe_conditions):
            return FeedbackDecision.AUTO_APPLY
        
        # Rule 6: Borderline cases = manual review
        return FeedbackDecision.MANUAL_REVIEW
    
    def _create_execution_plan(
        self,
        modifications: List[SuggestedModification],
        feedback_decision: FeedbackDecision,
        situation: Dict
    ) -> ModificationPlan:
        """Create step-by-step execution plan with component communication."""
        
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
            alert_id=f"alert_{datetime.now().timestamp()}",
            modifications=sorted_modifications,
            feedback_decision=feedback_decision,
            estimated_success_rate=success_rate,
            risk_level=risk_level,
            component_communication=component_communication,
            execution_order=execution_order
        )
    
    def _sort_modifications_by_priority(self, modifications: List[SuggestedModification]) -> List[SuggestedModification]:
        """Sort modifications by priority and logical dependencies."""
        priority_order = {
            ModificationPriority.CRITICAL: 0,
            ModificationPriority.HIGH: 1,
            ModificationPriority.MEDIUM: 2,
            ModificationPriority.LOW: 3
        }
        
        # Sort by priority first
        sorted_by_priority = sorted(modifications, key=lambda m: priority_order[m.priority])
        
        # Then apply logical ordering (data corrections before market changes)
        data_corrections = [m for m in sorted_by_priority if m.type == ModificationType.DATA_CORRECTION]
        other_modifications = [m for m in sorted_by_priority if m.type != ModificationType.DATA_CORRECTION]
        
        return data_corrections + other_modifications
    
    def _calculate_success_rate(self, modifications: List[SuggestedModification], situation: Dict) -> float:
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
    
    def _determine_risk_level(self, situation: Dict, success_rate: float) -> str:
        """Determine overall risk level."""
        if success_rate >= 0.8 and situation["critical_modifications"] == 0:
            return "LOW"
        elif success_rate >= 0.6 and situation["critical_modifications"] <= 1:
            return "MEDIUM"
        else:
            return "HIGH"
    
    def _plan_component_communication(self, modifications: List[SuggestedModification]) -> Dict[str, str]:
        """Plan how components should communicate during modification."""
        communication = {}
        
        for mod in modifications:
            if mod.type == ModificationType.MARKET_CHANGE:
                communication["analyzer"] = f"Update market analysis from {mod.original_value} to {mod.suggested_value}"
                communication["math_engine"] = f"Recalculate edge for new market: {mod.suggested_value}"
            elif mod.type == ModificationType.SCORE_ADJUSTMENT:
                communication["threshold_manager"] = f"Adjust alert threshold consideration for score {mod.suggested_value}"
                communication["health_monitor"] = f"Track modified alert performance with new score"
            elif mod.type == ModificationType.DATA_CORRECTION:
                communication["data_validator"] = f"Validate corrected {mod.id} data: {mod.suggested_value}"
                communication["verification_layer"] = f"Re-verify with corrected {mod.original_value} → {mod.suggested_value}"
        
        return communication
    
    def _calculate_data_quality(self, context_data: Dict) -> float:
        """Calculate overall data quality score."""
        quality_factors = []
        
        # Check verification layer confidence
        if context_data.get("verification_info"):
            verif_conf = context_data["verification_info"].get("confidence", "LOW")
            quality_factors.append(0.9 if verif_conf == "HIGH" else 0.7 if verif_conf == "MEDIUM" else 0.5)
        
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
    
    def _check_component_health(self, context_data: Dict) -> float:
        """Check health of all components."""
        health_scores = []
        
        # Each component contributes to health
        components = ["verification_info", "math_edge", "injury_intel", "referee_intel", "twitter_intel"]
        
        for component in components:
            if context_data.get(component):
                health_scores.append(0.8)  # Component present and functional
            else:
                health_scores.append(0.6)  # Component missing but not critical
        
        return sum(health_scores) / len(health_scores)
    
    def _log_for_learning(
        self,
        alert_id: str,
        modifications: List[SuggestedModification],
        decision: FeedbackDecision,
        situation: Dict
    ):
        """Log modification patterns for system learning."""
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_id": alert_id,
            "modification_count": len(modifications),
            "modification_types": [m.type.value for m in modifications],
            "decision": decision.value,
            "situation": situation,
            "success_prediction": None  # Will be updated later
        }
        
        self.modification_history.append(log_entry)
        
        # Update learning patterns
        pattern_key = f"{len(modifications)}_{situation['confidence_level']}_{situation['discrepancy_count']}"
        if pattern_key not in self.learning_patterns:
            self.learning_patterns[pattern_key] = []
        self.learning_patterns[pattern_key].append(decision)
    
    def _calculate_new_market(self, current_market: str, description: str) -> Optional[str]:
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
        
        return None


# Singleton instance
_intelligent_logger_instance: Optional[IntelligentModificationLogger] = None


def get_intelligent_modification_logger() -> IntelligentModificationLogger:
    """Get or create the singleton IntelligentModificationLogger instance."""
    global _intelligent_logger_instance
    if _intelligent_logger_instance is None:
        _intelligent_logger_instance = IntelligentModificationLogger()
    return _intelligent_logger_instance
