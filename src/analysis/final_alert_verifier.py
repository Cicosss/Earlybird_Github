"""
EarlyBird Final Alert Verifier - V1.0

Intercepts final alerts before Telegram and performs comprehensive verification
using Perplexity API with structured prompts for maximum accuracy.

Position in pipeline: 
Analysis → Verification Layer → FINAL VERIFIER → Telegram

The verifier acts as a professional betting analyst validating the complete reasoning,
data extracted, news links, and all components that generated the alert.
"""
import logging
import json
from typing import Dict, Optional, Tuple, List
from datetime import datetime

from src.ingestion.perplexity_provider import get_perplexity_provider
from src.database.models import NewsLog, SessionLocal
from src.database.models import Match
from src.utils.validators import safe_get

logger = logging.getLogger(__name__)


class FinalAlertVerifier:
    """
    Final verification layer for alerts before Telegram delivery.
    
    Uses Perplexity API with structured prompts to validate:
    - Complete reasoning and logic
    - Data extraction accuracy
    - News source reliability
    - Betting recommendation validity
    
    If verification fails, alert is marked as "no bet" and all components
    are updated accordingly.
    """
    
    def __init__(self):
        try:
            self._perplexity = get_perplexity_provider()
            self._enabled = self._perplexity is not None and self._perplexity.is_available()
        except Exception as e:
            logger.error(f"Failed to initialize Perplexity provider: {e}")
            self._perplexity = None
            self._enabled = False
        
        if self._enabled:
            logger.info("🔍 Final Alert Verifier initialized (Perplexity)")
        else:
            logger.warning("⚠️ Final Alert Verifier disabled: Perplexity not available")
    
    def verify_final_alert(
        self,
        match: Match,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Optional[Dict] = None
    ) -> Tuple[bool, Dict]:
        """
        Perform final verification of an alert before sending to Telegram.
        
        Args:
            match: Match database object
            analysis: NewsLog analysis object
            alert_data: Complete alert data including:
                - news_summary: Final analysis summary
                - news_url: Source URL
                - score: Alert score (0-10)
                - recommended_market: Primary market suggestion
                - combo_suggestion: Combo bet suggestion
                - reasoning: Complete reasoning
                - all extracted data: injuries, odds, stats, etc.
            context_data: Additional context (verification layer, math edge, etc.)
            
        Returns:
            Tuple of (should_send, verification_result)
            - should_send: True if verified, False if rejected
            - verification_result: Full verification details
        """
        if not self._enabled:
            logger.debug("Final verifier disabled, allowing alert")
            return True, {"status": "disabled", "reason": "Verifier not available"}
        
        prompt = self._build_verification_prompt(
            match=match,
            analysis=analysis,
            alert_data=alert_data,
            context_data=context_data or {}
        )
        
        logger.info(f"🔍 [FINAL VERIFIER] Verifying alert: {match.home_team} vs {match.away_team}")
        
        try:
            response = self._query_perplexity(prompt)
            
            if response:
                result = self._process_verification_response(response)
                
                status = result.get('verification_status', 'UNKNOWN')
                confidence = result.get('confidence_level', 'LOW')
                should_send = result.get('should_send', False)
                
                logger.info(f"🔍 [FINAL VERIFIER] Result: {status} (confidence: {confidence})")
                
                if should_send:
                    logger.info(f"✅ [FINAL VERIFIER] Alert CONFIRMED for Telegram")
                    return True, result
                else:
                    logger.warning(f"❌ [FINAL VERIFIER] Alert REJECTED: {result.get('rejection_reason', 'Unknown')}")
                    self._handle_alert_rejection(match, analysis, result)
                    return False, result
            else:
                logger.warning("⚠️ [FINAL VERIFIER] No response from Perplexity")
                return True, {"status": "error", "reason": "No response"}
                
        except Exception as e:
            logger.error(f"❌ [FINAL VERIFIER] Verification failed: {e}")
            return True, {"status": "error", "reason": str(e)}
    
    def _build_verification_prompt(
        self,
        match: Match,
        analysis: NewsLog,
        alert_data: Dict,
        context_data: Dict
    ) -> str:
        """
        Build comprehensive verification prompt following best practices.
        
        Structure:
        1. Role/Persona: Professional betting analyst
        2. Task: Analyze and validate alert
        3. Context: Complete match and analysis data
        4. Input: All extracted information and sources
        5. Output Format: Structured JSON with clear fields
        """
        
        home_team = match.home_team
        away_team = match.away_team
        league = match.league
        match_date = match.start_time.strftime('%Y-%m-%d') if match.start_time else "Unknown"
        
        context_lines = [
            f"MATCH: {home_team} vs {away_team}",
            f"LEAGUE: {league}",
            f"DATE: {match_date}",
            f"ALERT SCORE: {alert_data.get('score', 0)}/10",
        ]
        
        if match.opening_home_odd and match.current_home_odd:
            context_lines.append(f"HOME ODDS: {match.opening_home_odd:.2f} → {match.current_home_odd:.2f}")
        if match.opening_draw_odd and match.current_draw_odd:
            context_lines.append(f"DRAW ODDS: {match.opening_draw_odd:.2f} → {match.current_draw_odd:.2f}")
        if match.opening_away_odd and match.current_away_odd:
            context_lines.append(f"AWAY ODDS: {match.opening_away_odd:.2f} → {match.current_away_odd:.2f}")
        
        if alert_data.get('recommended_market'):
            context_lines.append(f"PRIMARY MARKET: {alert_data['recommended_market']}")
        if alert_data.get('combo_suggestion'):
            context_lines.append(f"COMBO SUGGESTION: {alert_data['combo_suggestion']}")
        
        if context_data.get('verification_info'):
            ver_info = context_data['verification_info']
            context_lines.append(f"PRELIMINARY VERIFICATION: {ver_info.get('status', 'Unknown')}")
            if ver_info.get('inconsistencies_count', 0) > 0:
                context_lines.append(f"INCONSISTENCIES FOUND: {ver_info['inconsistencies_count']}")
        
        if context_data.get('injury_intel'):
            injury = context_data['injury_intel']
            context_lines.append(f"HOME SEVERITY: {injury.get('home_severity', 'Unknown')}")
            context_lines.append(f"AWAY SEVERITY: {injury.get('away_severity', 'Unknown')}")
            if injury.get('home_missing_starters', 0) > 0:
                context_lines.append(f"HOME MISSING STARTERS: {injury['home_missing_starters']}")
            if injury.get('away_missing_starters', 0) > 0:
                context_lines.append(f"AWAY MISSING STARTERS: {injury['away_missing_starters']}")
        
        analysis_lines = [
            "NEWS SUMMARY:",
            alert_data.get('news_summary', ''),
            "",
            "NEWS SOURCE:",
            alert_data.get('news_url', ''),
            "",
            "COMPLETE REASONING:",
            alert_data.get('reasoning', ''),
        ]
        
        extracted_lines = ["EXTRACTED DATA:"]
        
        if hasattr(analysis, 'home_injuries') and analysis.home_injuries:
            extracted_lines.append(f"HOME INJURIES: {analysis.home_injuries}")
        if hasattr(analysis, 'away_injuries') and analysis.away_injuries:
            extracted_lines.append(f"AWAY INJURIES: {analysis.away_injuries}")
        
        if context_data.get('math_edge'):
            math_edge = context_data['math_edge']
            extracted_lines.append(
                f"MATH EDGE: {math_edge.get('edge', 0):.1f}% on {math_edge.get('market', 'Unknown')}"
            )
            extracted_lines.append(
                f"KELLY STAKE: {math_edge.get('kelly_stake', 0):.1f}%"
            )
        
        inconsistencies = safe_get(context_data, 'verification_info', 'inconsistencies')
        if inconsistencies and isinstance(inconsistencies, list):
            extracted_lines.append("INCONSISTENCIES:")
            for inc in inconsistencies[:3]:
                extracted_lines.append(f"  - {inc}")
        
        source_verification_lines = []
        if context_data.get('news_source_verification'):
            source_ver = context_data['news_source_verification']
            source_verification_lines = [
                "NEWS SOURCE VERIFICATION:",
                f"Source Domain: {source_ver.get('source_domain', 'Unknown')}",
                f"Source Tier: {source_ver.get('source_tier', 3)} (1=Official, 2=Major, 3=Other)",
                f"Source Weight: {source_ver.get('source_weight', 0.5):.2f} (0.0-1.0 reliability)",
                f"Source Type: {source_ver.get('source_type', 'Unknown')}",
                f"Reliability: {source_ver.get('source_reliability', 'LOW')}",
                f"Cross-Source Needed: {source_ver.get('cross_source_needed', True)}",
                f"Verification Priority: {source_ver.get('verification_priority', 'HIGH')}",
                f"Source Guidance: {source_ver.get('source_guidance', 'Verify thoroughly')}",
                ""
            ]
        
        extracted_lines.append("")
        extracted_lines.append("DATA VERIFICATION TASK:")
        extracted_lines.append("Compare the extracted data above with your web search results.")
        extracted_lines.append("Identify any discrepancies in:")
        extracted_lines.append("- Goals scored/conceded statistics")
        extracted_lines.append("- Corner averages")
        extracted_lines.append("- Card statistics") 
        extracted_lines.append("- Team form/position")
        extracted_lines.append("- Injury severity/impact")
        extracted_lines.append("")
        extracted_lines.append("For each discrepancy found, assess:")
        extracted_lines.append("- Impact level (LOW/MEDIUM/HIGH)")
        extracted_lines.append("- Effect on betting recommendation")
        extracted_lines.append("- Whether to REJECT, MODIFY, or CONFIRM with adjusted confidence")
        
        if source_verification_lines:
            extracted_lines.extend([
                "",
                "NEWS SOURCE VERIFICATION TASK:",
                "Verify the news source credibility and cross-source confirmation:",
                f"- Source reliability assessment: {source_ver.get('source_reliability', 'LOW')}",
                f"- Cross-source confirmation required: {source_ver.get('cross_source_needed', True)}",
                f"- Source type guidance: {source_ver.get('source_guidance', 'Verify thoroughly')}",
                "- Check if the news is confirmed by multiple sources",
                "- Assess potential bias or agenda",
                "- Verify the timeline and freshness of the information",
                "- Adjust confidence based on source verification"
            ])
        
        prompt = f"""ROLE: Act as a professional betting analyst and fact-checker with 10+ years of experience in sports betting and football analysis.

TASK: Analyze and validate this betting alert for accuracy, logic, and reliability. Verify that all reasoning is sound, data extraction is correct, and the betting recommendation is justified.

CONTEXT:
{chr(10).join(context_lines)}

ANALYSIS:
{chr(10).join(analysis_lines)}

{chr(10).join(extracted_lines)}

{chr(10).join(source_verification_lines)}

INPUT REQUIREMENTS:
- The news source and URL provided
- All extracted player data and statistics
- The complete reasoning chain
- Odds movements and market context
- Any inconsistencies or red flags
- News source credibility assessment

OUTPUT FORMAT: Respond ONLY with valid JSON in this exact format:
{{
    "verification_status": "CONFIRMED|REJECTED|NEEDS_REVIEW",
    "confidence_level": "HIGH|MEDIUM|LOW",
    "should_send": true/false,
    "logic_score": 0-10,
    "data_accuracy_score": 0-10,
    "reasoning_quality_score": 0-10,
    "market_validation": "VALID|INVALID|QUESTIONABLE",
    "key_strengths": ["strength1", "strength2"],
    "key_weaknesses": ["weakness1", "weakness2"],
    "missing_information": ["missing1", "missing2"],
    "rejection_reason": "Clear explanation if rejected",
    "final_recommendation": "SEND|NO_BET|MODIFY",
    "suggested_modifications": "If MODIFY, specify changes needed",
    "data_discrepancies": [
        {{
            "field": "goals|corners|cards|injuries|form|position|source",
            "fotmob_value": "value from FotMob",
            "perplexity_value": "value from web search",
            "impact": "LOW|MEDIUM|HIGH",
            "description": "description of discrepancy"
        }}
    ],
    "discrepancy_impact": "MINOR|MODERATE|SEVERE",
    "adjusted_score_if_discrepancy": 0-10,
    "source_verification": {{
        "source_confirmed": true/false,
        "cross_source_found": true/false,
        "source_bias_detected": true/false,
        "source_reliability_adjusted": "VERY_HIGH|HIGH|MEDIUM|LOW",
        "verification_issues": ["issue1", "issue2"]
    }}
}}

VALIDATION CRITERIA:
1. Logic: Does the reasoning flow logically from news to betting recommendation?
2. Data: Are all extracted facts accurate and properly contextualized?
3. Market: Is the suggested bet appropriate given the odds and context?
4. Completeness: Has all relevant information been considered?
5. Risk: Are there any red flags or contradictions that invalidate the alert?
6. Discrepancies: How do data differences affect the recommendation?
7. Source: Is the news source reliable and cross-confirmed?

DISCREPANCY HANDLING RULES:
- MINOR discrepancies (stats off by <10%): CONFIRM with reduced confidence
- MODERATE discrepancies (stats off by 10-25%): MODIFY recommendation or adjust score
- SEVERE discrepancies (stats off by >25% or contradictory): REJECT alert
- Goal/Injury discrepancies have higher impact than corners/cards
- Source reliability issues impact confidence levels significantly
- If Perplexity data is more recent/reliable, prefer it over FotMob

SOURCE VERIFICATION RULES:
- VERY_HIGH reliability (Tier 1): Confirm quickly, minimal cross-source needed
- HIGH reliability (Tier 2): Standard verification, cross-source if time-sensitive
- MEDIUM reliability (Tier 3): Thorough verification required, multiple sources
- LOW reliability (Unknown): Extreme caution, extensive cross-source verification
- Social media sources: Always require multiple independent confirmations
- Official sources: Check for potential bias or agenda

Begin your analysis now."""

        return prompt
    
    def _query_perplexity(self, prompt: str) -> Optional[Dict]:
        """Query Perplexity API with verification prompt."""
        try:
            response = self._perplexity._query_api_raw(prompt)
            return response
        except Exception as e:
            logger.error(f"Perplexity query failed: {e}")
            return None
    
    def _process_verification_response(self, response: Dict) -> Dict:
        """
        Process and validate Perplexity response with discrepancy handling.
        
        Ensures all required fields are present and valid.
        """
        processed = {
            "verification_status": "NEEDS_REVIEW",
            "confidence_level": "LOW",
            "should_send": False,
            "logic_score": 5,
            "data_accuracy_score": 5,
            "reasoning_quality_score": 5,
            "market_validation": "QUESTIONABLE",
            "key_strengths": [],
            "key_weaknesses": [],
            "missing_information": [],
            "rejection_reason": "",
            "final_recommendation": "NO_BET",
            "suggested_modifications": "",
            "data_discrepancies": [],
            "discrepancy_impact": "MINOR",
            "adjusted_score_if_discrepancy": 5,
            "raw_response": response
        }
        
        if not response:
            return processed
        
        try:
            processed.update({
                "verification_status": response.get("verification_status", "NEEDS_REVIEW"),
                "confidence_level": response.get("confidence_level", "LOW"),
                "should_send": bool(response.get("should_send", False)),
                "logic_score": max(0, min(10, int(response.get("logic_score", 5)))),
                "data_accuracy_score": max(0, min(10, int(response.get("data_accuracy_score", 5)))),
                "reasoning_quality_score": max(0, min(10, int(response.get("reasoning_quality_score", 5)))),
                "market_validation": response.get("market_validation", "QUESTIONABLE"),
                "key_strengths": response.get("key_strengths", []),
                "key_weaknesses": response.get("key_weaknesses", []),
                "missing_information": response.get("missing_information", []),
                "rejection_reason": response.get("rejection_reason", ""),
                "final_recommendation": response.get("final_recommendation", "NO_BET"),
                "suggested_modifications": response.get("suggested_modifications", ""),
                "data_discrepancies": response.get("data_discrepancies", []),
                "discrepancy_impact": response.get("discrepancy_impact", "MINOR"),
                "adjusted_score_if_discrepancy": max(0, min(10, int(response.get("adjusted_score_if_discrepancy", 5))))
            })
            
            source_verification = response.get("source_verification", {})
            if source_verification:
                processed["source_verification"] = {
                    "source_confirmed": bool(source_verification.get("source_confirmed", False)),
                    "cross_source_found": bool(source_verification.get("cross_source_found", False)),
                    "source_bias_detected": bool(source_verification.get("source_bias_detected", False)),
                    "source_reliability_adjusted": source_verification.get("source_reliability_adjusted", "LOW"),
                    "verification_issues": source_verification.get("verification_issues", [])
                }
                
                logger.info(f"🔍 [SOURCE VERIFICATION] Confirmed: {processed['source_verification']['source_confirmed']}, "
                           f"Cross-source: {processed['source_verification']['cross_source_found']}, "
                           f"Reliability: {processed['source_verification']['source_reliability_adjusted']}")
            else:
                processed["source_verification"] = {
                    "source_confirmed": False,
                    "cross_source_found": False,
                    "source_bias_detected": False,
                    "source_reliability_adjusted": "LOW",
                    "verification_issues": ["No source verification provided"]
                }
            
            valid_statuses = ["CONFIRMED", "REJECTED", "NEEDS_REVIEW"]
            if processed["verification_status"] not in valid_statuses:
                processed["verification_status"] = "NEEDS_REVIEW"
            
            valid_confidences = ["HIGH", "MEDIUM", "LOW"]
            if processed["confidence_level"] not in valid_confidences:
                processed["confidence_level"] = "LOW"
            
            discrepancies = processed["data_discrepancies"]
            if discrepancies:
                processed = self._handle_discrepancies_intelligently(processed, discrepancies)
            
            if source_verification:
                processed = self._adjust_confidence_based_on_source_verification(processed, source_verification)
            
        except Exception as e:
            logger.warning(f"Error processing verification response: {e}")
        
        return processed
    
    def _adjust_confidence_based_on_source_verification(self, processed: Dict, source_verification: Dict) -> Dict:
        """
        Adjust confidence levels based on source verification results.
        
        Args:
            processed: Current processed verification result
            source_verification: Source verification data from Perplexity
            
        Returns:
            Updated processed result with adjusted confidence
        """
        if not source_verification:
            return processed
        
        source_confirmed = source_verification.get("source_confirmed", False)
        cross_source_found = source_verification.get("cross_source_found", False)
        source_bias_detected = source_verification.get("source_bias_detected", False)
        reliability_adjusted = source_verification.get("source_reliability_adjusted", "LOW")
        verification_issues = source_verification.get("verification_issues", [])
        
        logger.info(f"🔍 [CONFIDENCE ADJUSTMENT] Source: {reliability_adjusted}, "
                   f"Confirmed: {source_confirmed}, Cross-source: {cross_source_found}, "
                   f"Bias: {source_bias_detected}")
        
        current_confidence = processed.get("confidence_level", "LOW")
        new_confidence = current_confidence
        
        positive_factors = 0
        negative_factors = 0
        
        if source_confirmed:
            positive_factors += 1
        if cross_source_found:
            positive_factors += 1
        if reliability_adjusted in ["VERY_HIGH", "HIGH"]:
            positive_factors += 1
        
        if not source_confirmed:
            negative_factors += 1
        if source_bias_detected:
            negative_factors += 1
        if len(verification_issues) > 0:
            negative_factors += len(verification_issues)
        
        net_impact = positive_factors - negative_factors
        
        if net_impact >= 2:
            if current_confidence == "LOW":
                new_confidence = "MEDIUM"
            elif current_confidence == "MEDIUM" and reliability_adjusted == "VERY_HIGH":
                new_confidence = "HIGH"
            
            logger.info(f"🔍 [CONFIDENCE ADJUSTMENT] Upgraded {current_confidence} → {new_confidence} "
                       f"due to strong source verification (+{net_impact})")
        
        elif net_impact <= -1:
            if current_confidence == "HIGH":
                new_confidence = "MEDIUM"
            elif current_confidence == "MEDIUM":
                new_confidence = "LOW"
            
            logger.warning(f"🔍 [CONFIDENCE ADJUSTMENT] Downgraded {current_confidence} → {new_confidence} "
                         f"due to source verification issues ({net_impact}): {verification_issues}")
        
        else:
            logger.debug(f"🔍 [CONFIDENCE ADJUSTMENT] Confidence unchanged {current_confidence} "
                         f"(neutral net impact: {net_impact})")
        
        processed["confidence_level"] = new_confidence
        
        if new_confidence != current_confidence:
            impact_reason = f"Confidence adjusted from {current_confidence} to {new_confidence} based on source verification"
            if processed.get("rejection_reason"):
                processed["rejection_reason"] += f" | {impact_reason}"
            else:
                processed["rejection_reason"] = impact_reason
        
        return processed
    
    def _handle_discrepancies_intelligently(self, processed: Dict, discrepancies: List[Dict]) -> Dict:
        """
        Handle data discrepancies intelligently instead of outright rejection.
        
        Args:
            processed: Current processed verification result
            discrepancies: List of detected discrepancies
            
        Returns:
            Updated processed result with intelligent discrepancy handling
        """
        if not discrepancies:
            return processed
        
        high_impact_count = len([d for d in discrepancies if d.get("impact") == "HIGH"])
        medium_impact_count = len([d for d in discrepancies if d.get("impact") == "MEDIUM"])
        low_impact_count = len([d for d in discrepancies if d.get("impact") == "LOW"])
        
        total_discrepancies = len(discrepancies)
        discrepancy_impact = processed.get("discrepancy_impact", "MINOR")
        
        logger.info(f"🔍 [DISCREPANCY HANDLER] Found {total_discrepancies} discrepancies: "
                   f"{high_impact_count} HIGH, {medium_impact_count} MEDIUM, {low_impact_count} LOW")
        
        if discrepancy_impact == "SEVERE" or high_impact_count >= 2:
            processed["should_send"] = False
            processed["verification_status"] = "REJECTED"
            processed["final_recommendation"] = "NO_BET"
            processed["rejection_reason"] = f"Severe data discrepancies detected: {total_discrepancies} issues, including {high_impact_count} high-impact"
        
        elif discrepancy_impact == "MODERATE" or high_impact_count == 1 or medium_impact_count >= 2:
            processed["should_send"] = False
            processed["verification_status"] = "NEEDS_REVIEW"
            processed["final_recommendation"] = "MODIFY"
            
            goal_discrepancies = [d for d in discrepancies if d.get("field") in ["goals", "injuries"]]
            if goal_discrepancies:
                processed["suggested_modifications"] = "Review goal statistics and injury impact - consider adjusting market or score"
            
            if processed["confidence_level"] == "HIGH":
                processed["confidence_level"] = "MEDIUM"
            elif processed["confidence_level"] == "MEDIUM":
                processed["confidence_level"] = "LOW"
        
        else:
            processed["should_send"] = True
            processed["verification_status"] = "CONFIRMED"
            processed["final_recommendation"] = "SEND"
            
            if processed["confidence_level"] == "HIGH":
                processed["confidence_level"] = "MEDIUM"
            
            penalty = low_impact_count * 1 + medium_impact_count * 2
            processed["logic_score"] = max(5, processed["logic_score"] - penalty)
            processed["data_accuracy_score"] = max(3, processed["data_accuracy_score"] - penalty * 2)
        
        processed["discrepancy_summary"] = {
            "total_count": total_discrepancies,
            "high_impact": high_impact_count,
            "medium_impact": medium_impact_count,
            "low_impact": low_impact_count,
            "handling_action": "REJECTED" if not processed["should_send"] else "CONFIRMED_WITH_ADJUSTMENT"
        }
        
        return processed
    
    def _handle_alert_rejection(self, match: Match, analysis: NewsLog, verification_result: Dict):
        """
        Handle alert rejection by updating all components.
        
        Marks the alert as "no bet" and updates database accordingly.
        """
        try:
            db = SessionLocal()
            
            analysis.status = "no_bet"
            analysis.verification_status = verification_result.get("verification_status", "REJECTED")
            analysis.verification_reason = verification_result.get("rejection_reason", "Final verification failed")
            analysis.final_verifier_result = json.dumps(verification_result)
            
            if hasattr(match, 'alert_status'):
                match.alert_status = "rejected"
            
            db.commit()
            logger.info(f"📊 [FINAL VERIFIER] Updated database: alert marked as 'no bet'")
            
        except Exception as e:
            logger.error(f"Failed to update database after rejection: {e}")
        finally:
            db.close()


_final_verifier_instance: Optional[FinalAlertVerifier] = None


def get_final_verifier() -> FinalAlertVerifier:
    """Get or create the singleton FinalAlertVerifier instance."""
    global _final_verifier_instance
    if _final_verifier_instance is None:
        _final_verifier_instance = FinalAlertVerifier()
    return _final_verifier_instance


def is_final_verifier_available() -> bool:
    """Check if Final Verifier is available."""
    try:
        verifier = get_final_verifier()
        return verifier._enabled
    except Exception:
        return False
