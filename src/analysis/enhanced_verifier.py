"""
Enhanced Final Alert Verifier with Data Discrepancy Handling

This module extends the Final Alert Verifier to handle data discrepancies
between FotMob extraction and Perplexity verification more intelligently.
"""
import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

from src.analysis.final_alert_verifier import FinalAlertVerifier
from src.database.models import Match, NewsLog

logger = logging.getLogger(__name__)


@dataclass
class DataDiscrepancy:
    """Represents a discrepancy between extracted and verified data."""
    field: str
    fotmob_value: any
    perplexity_value: any
    impact: str  # "LOW", "MEDIUM", "HIGH"
    description: str


class EnhancedFinalVerifier(FinalAlertVerifier):
    """
    Enhanced Final Alert Verifier with intelligent discrepancy handling.
    
    Instead of outright rejecting alerts with data differences,
    it evaluates the impact and can suggest modifications or
    adjust confidence scores accordingly.
    """
    
    def verify_final_alert_with_discrepancy_handling(
        self,
        match: Match,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Optional[Dict] = None
    ) -> Tuple[bool, Dict]:
        """
        Enhanced verification that handles data discrepancies intelligently.
        
        Args:
            match: Match database object
            analysis: NewsLog analysis object
            alert_data: Complete alert data
            context_data: Additional context
            
        Returns:
            Tuple of (should_send, enhanced_verification_result)
        """
        # First, run standard verification
        should_send, verification_result = super().verify_final_alert(
            match, analysis, alert_data, context_data
        )
        
        if not should_send and verification_result.get("final_recommendation") == "MODIFY":
            # Handle MODIFY case - check if we can adjust the alert
            return self._handle_modify_case(
                match, analysis, alert_data, context_data, verification_result
            )
        
        # Check for data discrepancies even in confirmed alerts
        if should_send:
            discrepancies = self._detect_data_discrepancies(verification_result)
            if discrepancies:
                verification_result["data_discrepancies"] = discrepancies
                # Adjust confidence based on discrepancies
                verification_result = self._adjust_confidence_for_discrepancies(
                    verification_result, discrepancies
                )
        
        return should_send, verification_result
    
    def _detect_data_discrepancies(self, verification_result: Dict) -> List[DataDiscrepancy]:
        """
        Detect data discrepancies from Perplexity response.
        
        Looks for patterns indicating data differences between sources.
        """
        discrepancies = []
        rejection_reason = verification_result.get("rejection_reason", "")
        key_weaknesses = verification_result.get("key_weaknesses", [])
        
        # Common discrepancy patterns
        discrepancy_patterns = {
            "goals": ["goals scored", "goals conceded", "goal average", "scoring"],
            "corners": ["corners", "corner kicks", "set pieces"],
            "cards": ["cards", "yellow cards", "red cards", "bookings"],
            "injuries": ["injuries", "injured", "unavailable", "suspended"],
            "form": ["form", "last 5", "recent matches", "performance"],
            "position": ["position", "standing", "table", "rank"]
        }
        
        # Analyze rejection reason for discrepancy indicators
        for field, keywords in discrepancy_patterns.items():
            field_discrepancy = self._check_field_discrepancy(
                field, keywords, rejection_reason, key_weaknesses
            )
            if field_discrepancy:
                discrepancies.append(field_discrepancy)
        
        return discrepancies
    
    def _check_field_discrepancy(
        self, field: str, keywords: List[str], rejection_reason: str, weaknesses: List[str]
    ) -> Optional[DataDiscrepancy]:
        """Check if there's a discrepancy for a specific field."""
        combined_text = f"{rejection_reason} {' '.join(weaknesses)}".lower()
        
        # Look for discrepancy indicators
        discrepancy_indicators = [
            "different", "contradicts", "doesn't match", "inconsistent",
            "higher than", "lower than", "shows", "indicates", "suggests"
        ]
        
        for keyword in keywords:
            if keyword in combined_text:
                for indicator in discrepancy_indicators:
                    if indicator in combined_text:
                        # Determine impact based on field importance
                        impact = self._determine_field_impact(field)
                        
                        return DataDiscrepancy(
                            field=field,
                            fotmob_value="extracted_from_fotmob",
                            perplexity_value="found_by_perplexity",
                            impact=impact,
                            description=f"Perplexity found different {field} data"
                        )
        
        return None
    
    def _determine_field_impact(self, field: str) -> str:
        """Determine the impact level of a data discrepancy."""
        high_impact_fields = ["goals", "injuries", "form"]
        medium_impact_fields = ["corners", "cards", "position"]
        
        if field in high_impact_fields:
            return "HIGH"
        elif field in medium_impact_fields:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _adjust_confidence_for_discrepancies(
        self, verification_result: Dict, discrepancies: List[DataDiscrepancy]
    ) -> Dict:
        """
        Adjust confidence scores based on detected discrepancies.
        """
        original_confidence = verification_result.get("confidence_level", "HIGH")
        original_scores = {
            "logic_score": verification_result.get("logic_score", 8),
            "data_accuracy_score": verification_result.get("data_accuracy_score", 8),
            "reasoning_quality_score": verification_result.get("reasoning_quality_score", 8)
        }
        
        # Calculate penalty based on discrepancy impacts
        total_penalty = 0
        for discrepancy in discrepancies:
            if discrepancy.impact == "HIGH":
                total_penalty += 3
            elif discrepancy.impact == "MEDIUM":
                total_penalty += 2
            else:
                total_penalty += 1
        
        # Adjust scores
        adjusted_scores = {}
        for score_type, original_score in original_scores.items():
            adjusted_score = max(1, original_score - total_penalty)
            adjusted_scores[score_type] = adjusted_score
        
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
        verification_result["confidence_adjustment"] = f"-{total_penalty} due to {len(discrepancies)} discrepancies"
        
        # Add discrepancy summary
        verification_result["discrepancy_summary"] = {
            "total_count": len(discrepancies),
            "high_impact": len([d for d in discrepancies if d.impact == "HIGH"]),
            "medium_impact": len([d for d in discrepancies if d.impact == "MEDIUM"]),
            "low_impact": len([d for d in discrepancies if d.impact == "LOW"])
        }
        
        return verification_result
    
    def _handle_modify_case(
        self,
        match: Match,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict,
        verification_result: Dict
    ) -> Tuple[bool, Dict]:
        """
        Handle the MODIFY recommendation case.
        
        Attempts to adjust the alert based on Perplexity suggestions.
        """
        suggested_modifications = verification_result.get("suggested_modifications", "")
        
        if not suggested_modifications:
            logger.warning("MODIFY recommendation without specific suggestions")
            return False, verification_result
        
        logger.info(f"🔧 [ENHANCED VERIFIER] Attempting to modify alert: {suggested_modifications}")
        
        # Try to apply common modifications
        modifications_applied = []
        
        # Check for market change suggestions
        if "over 2.5" in suggested_modifications.lower() and "under 2.5" in suggested_modifications.lower():
            # Suggest market change
            current_market = alert_data.get("recommended_market", "")
            if "over" in current_market.lower():
                new_market = current_market.replace("Over", "Under")
                alert_data["recommended_market"] = new_market
                modifications_applied.append(f"Market changed: {current_market} → {new_market}")
        
        # Check for score adjustment suggestions
        if "lower score" in suggested_modifications.lower():
            original_score = alert_data.get("score", 8)
            new_score = max(5, original_score - 2)
            alert_data["score"] = new_score
            modifications_applied.append(f"Score adjusted: {original_score} → {new_score}")
        
        if modifications_applied:
            verification_result["modifications_applied"] = modifications_applied
            verification_result["verification_status"] = "CONFIRMED"
            verification_result["should_send"] = True
            verification_result["final_recommendation"] = "SEND"
            verification_result["confidence_level"] = "MEDIUM"  # Reduced confidence for modified alerts
            
            logger.info(f"✅ [ENHANCED VERIFIER] Alert modified and approved: {', '.join(modifications_applied)}")
            return True, verification_result
        
        # If we can't apply modifications automatically, reject but provide clear reason
        verification_result["rejection_reason"] = f"Manual review required: {suggested_modifications}"
        return False, verification_result


def get_enhanced_final_verifier() -> EnhancedFinalVerifier:
    """Get or create the singleton EnhancedFinalVerifier instance."""
    from src.analysis.final_alert_verifier import get_final_verifier
    base_verifier = get_final_verifier()
    
    # Convert to enhanced verifier (composition pattern)
    if isinstance(base_verifier, EnhancedFinalVerifier):
        return base_verifier
    
    # Create enhanced verifier wrapping the base one
    enhanced = EnhancedFinalVerifier()
    enhanced._perplexity = base_verifier._perplexity
    enhanced._enabled = base_verifier._enabled
    
    return enhanced
