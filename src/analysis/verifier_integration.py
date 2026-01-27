"""
Final Alert Verifier Integration Wrapper

Helper functions to integrate the Final Alert Verifier into the main pipeline.
Provides a clean interface for main.py to call the verifier.
"""
import logging
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from src.analysis.final_alert_verifier import get_final_verifier, is_final_verifier_available
from src.database.models import Match, NewsLog
from src.processing.sources_config import get_source_tier, get_source_weight

logger = logging.getLogger(__name__)


def verify_alert_before_telegram(
    match: Match,
    analysis: NewsLog,
    alert_data: Dict,
    context_data: Optional[Dict] = None
) -> Tuple[bool, Dict]:
    """
    Wrapper function to verify alert before sending to Telegram.
    
    This function should be called right before send_alert() in main.py.
    
    Args:
        match: Match database object
        analysis: NewsLog analysis object  
        alert_data: Complete alert data dictionary with all components
        context_data: Additional context (verification layer, math edge, etc.)
        
    Returns:
        Tuple of (should_send, verification_info)
        - should_send: True if alert should be sent to Telegram
        - verification_info: Verification result for logging/reporting
    """
    # Input validation
    if not match or not analysis:
        logger.warning("Invalid input: match or analysis is None")
        return False, {"status": "invalid_input", "reason": "Missing match or analysis"}
    
    if not is_final_verifier_available():
        logger.debug("Final verifier not available, proceeding with alert")
        return True, {"status": "disabled", "reason": "Final verifier unavailable"}
    
    try:
        verifier = get_final_verifier()
        should_send, verification_result = verifier.verify_final_alert(
            match=match,
            analysis=analysis,
            alert_data=alert_data,
            context_data=context_data or {}
        )
        
        # Add verification info to alert data for Telegram display
        if verification_result:
            verification_info = {
                "status": (verification_result.get("verification_status", "UNKNOWN") or "UNKNOWN").lower(),
                "confidence": verification_result.get("confidence_level", "LOW"),
                "reasoning": (verification_result.get("rejection_reason", "") or "")[:200],
                "final_verifier": True
            }
        else:
            verification_info = {"status": "error", "final_verifier": True}
        
        return should_send, verification_info
        
    except Exception as e:
        logger.error(f"Final verification error: {e}")
        # Fail-safe: allow alert to proceed if verifier fails
        return True, {"status": "error", "reason": str(e), "final_verifier": True}


def build_alert_data_for_verifier(
    match: Match,
    analysis: NewsLog,
    news_summary: str,
    news_url: str,
    score: int,
    recommended_market: str = None,
    combo_suggestion: str = None,
    reasoning: str = None,
    **kwargs
) -> Dict:
    """
    Build the complete alert data structure expected by the verifier.
    
    Collects all alert components into a single dictionary for verification.
    
    Args:
        match: Match database object
        analysis: NewsLog analysis object
        news_summary: Final news summary
        news_url: Source URL
        score: Alert score (0-10)
        recommended_market: Primary market suggestion
        combo_suggestion: Combo bet suggestion
        reasoning: Complete reasoning (if available)
        **kwargs: Additional alert components
        
    Returns:
        Complete alert data dictionary
    """
    alert_data = {
        "news_summary": news_summary,
        "news_url": news_url,
        "score": score,
        "recommended_market": recommended_market,
        "combo_suggestion": combo_suggestion,
        "reasoning": reasoning or news_summary,  # Fallback to summary
        "match": {
            "home_team": match.home_team,
            "away_team": match.away_team,
            "league": match.league,
            "start_time": match.start_time.isoformat() if match.start_time else None,
            "opening_home_odd": match.opening_home_odd,
            "current_home_odd": match.current_home_odd,
            "opening_draw_odd": match.opening_draw_odd,
            "current_draw_odd": match.current_draw_odd,
            "opening_away_odd": match.opening_away_odd,
            "current_away_odd": match.current_away_odd,
        },
        "analysis": {
            "id": analysis.id if analysis else None,
            "home_injuries": getattr(analysis, 'home_injuries', ''),
            "away_injuries": getattr(analysis, 'away_injuries', ''),
            "score": getattr(analysis, 'score', score),
            "recommended_market": getattr(analysis, 'recommended_market', recommended_market),
            "combo_suggestion": getattr(analysis, 'combo_suggestion', combo_suggestion),
            "summary": getattr(analysis, 'summary', news_summary),
            "url": getattr(analysis, 'url', news_url),
        }
    }
    
    # Add any additional components
    alert_data.update(kwargs)
    
    return alert_data


def build_context_data_for_verifier(
    verification_info: Optional[Dict] = None,
    math_edge: Optional[Dict] = None,
    injury_intel: Optional[Dict] = None,
    confidence_breakdown: Optional[Dict] = None,
    news_source_verification: Optional[Dict] = None,
    **kwargs
) -> Dict:
    """
    Build context data structure for the verifier.
    
    Collects all additional context that might be relevant for verification.
    
    Args:
        verification_info: Verification Layer V7.0 results
        math_edge: Mathematical edge data
        injury_intel: Injury intelligence data
        confidence_breakdown: Confidence breakdown data
        news_source_verification: News source verification data (NEW)
        **kwargs: Additional context components
        
    Returns:
        Complete context data dictionary
    """
    context_data = {}
    
    if verification_info:
        context_data["verification_info"] = verification_info
    
    if math_edge:
        context_data["math_edge"] = math_edge
    
    if injury_intel:
        context_data["injury_intel"] = injury_intel
    
    if confidence_breakdown:
        context_data["confidence_breakdown"] = confidence_breakdown
    
    # NEW: Add news source verification data
    if news_source_verification:
        context_data["news_source_verification"] = news_source_verification
    
    # Add any additional context
    context_data.update(kwargs)
    
    return context_data


def extract_domain_from_url(url: str) -> str:
    """
    Extract domain from URL for source verification.
    
    Args:
        url: Full URL string
        
    Returns:
        Domain string (e.g., "dailyrecord.co.uk")
    """
    if not url:
        return "unknown"
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
            
        return domain
    except Exception:
        return "unknown"


def build_news_source_verification(
    news_url: str,
    news_summary: str,
    league_key: Optional[str] = None
) -> Dict:
    """
    Build news source verification data using existing source weighting system.
    
    Leverages the sophisticated source weighting system from sources_config.py
    to provide Perplexity with context about source credibility.
    
    Args:
        news_url: Source URL from the alert
        news_summary: News summary text
        league_key: League key for context (optional)
        
    Returns:
        Dictionary with source verification data
    """
    if not news_url:
        return {
            "source_url": "unknown",
            "source_domain": "unknown",
            "source_tier": 3,
            "source_weight": 0.5,
            "source_type": "unknown",
            "source_reliability": "LOW",
            "cross_source_needed": True,
            "verification_priority": "HIGH"
        }
    
    # Extract domain
    domain = extract_domain_from_url(news_url)
    
    # Get source tier and weight from existing system
    source_tier = get_source_tier(news_url)
    source_weight = get_source_weight(news_url)
    
    # Determine reliability level based on weight
    if source_weight >= 0.9:
        reliability = "VERY_HIGH"
        priority = "LOW"
    elif source_weight >= 0.8:
        reliability = "HIGH"
        priority = "MEDIUM"
    elif source_weight >= 0.6:
        reliability = "MEDIUM"
        priority = "HIGH"
    else:
        reliability = "LOW"
        priority = "HIGH"
    
    # Check if cross-source verification is needed
    cross_source_needed = source_weight < 0.8
    
    # Build verification data
    verification_data = {
        "source_url": news_url,
        "source_domain": domain,
        "source_tier": source_tier.tier,
        "source_weight": source_weight,
        "source_type": source_tier.source_type,
        "source_reliability": reliability,
        "cross_source_needed": cross_source_needed,
        "verification_priority": priority,
        "league_context": league_key,
        "news_summary_length": len(news_summary) if news_summary else 0
    }
    
    # Add source-specific guidance for Perplexity
    if source_tier.source_type == "official":
        verification_data["source_guidance"] = "Official source - high reliability but verify for bias"
    elif source_tier.source_type == "broadcaster":
        verification_data["source_guidance"] = "Major broadcaster - generally reliable, check for sensationalism"
    elif source_tier.source_type == "newspaper":
        verification_data["source_guidance"] = "Established newspaper - good track record, verify for clickbait"
    elif source_tier.source_type == "social":
        verification_data["source_guidance"] = "Social media - verify with multiple sources, high rumor risk"
    else:
        verification_data["source_guidance"] = "Unknown source type - requires thorough verification"
    
    logger.debug(f"🔍 [SOURCE VERIFICATION] {domain}: Tier {source_tier.tier}, Weight {source_weight:.2f}, Reliability {reliability}")
    
    return verification_data
