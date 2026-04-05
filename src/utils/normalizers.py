"""
EarlyBird Shared Response Normalizers - V1.0

Centralized normalization functions for AI provider responses.
Eliminates code duplication between DeepSeekIntelProvider and OpenRouterFallbackProvider.

Both providers must return identical response structures to ensure the
IntelligenceRouter fallback chain produces consistent output regardless
of which provider handles the request.

Usage:
    from src.utils.normalizers import (
        normalize_verification_result,
        normalize_biscotto_confirmation,
        normalize_final_alert_verification,
        normalize_match_enrichment,
    )

Requirements: DRY principle - single source of truth for response schemas
"""


# ============================================
# PRIMITIVE HELPERS (used by all normalizers)
# ============================================

def safe_bool(val, default=False) -> bool:
    """Convert value to bool with safe fallback."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "si", "1", "confirmed")
    return default


def safe_int(val, default=0, min_val=0, max_val=10) -> int:
    """Convert value to int with clamping and safe fallback."""
    if val is None:
        return default
    try:
        result = int(val)
        return max(min_val, min(max_val, result))
    except (ValueError, TypeError):
        return default


def safe_str(val, default="Unknown") -> str:
    """Convert value to str with safe fallback."""
    if val is None or val == "":
        return default
    return str(val)


def safe_list(val, default=None) -> list[str]:
    """Convert value to list[str] with safe fallback."""
    if default is None:
        default: list[str] = []
    if val is None:
        return default
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str):
        return [val]
    return default


# ============================================
# RESPONSE NORMALIZERS
# ============================================

def normalize_verification_result(data: dict) -> dict:
    """
    Normalize news verification response with safe defaults.

    Ensures identical structure across DeepSeek and Claude 3 Haiku responses.

    Args:
        data: Raw parsed JSON from any AI provider

    Returns:
        Normalized dict with all expected fields
    """
    return {
        "verified": safe_bool(data.get("verified")),
        "verification_status": safe_str(data.get("verification_status"), "UNVERIFIED"),
        "confidence_level": safe_str(data.get("confidence_level"), "LOW"),
        "verification_sources": safe_list(data.get("verification_sources")),
        "additional_context": safe_str(data.get("additional_context"), ""),
        "betting_impact": safe_str(data.get("betting_impact"), "Unknown"),
        "is_current": safe_bool(data.get("is_current"), True),
        "notes": safe_str(data.get("notes"), ""),
    }


def normalize_biscotto_confirmation(data: dict) -> dict:
    """
    Normalize biscotto confirmation response with safe defaults.

    Ensures identical structure across DeepSeek and Claude 3 Haiku responses.

    Args:
        data: Raw parsed JSON from any AI provider

    Returns:
        Normalized dict with all expected fields
    """
    return {
        "biscotto_confirmed": safe_bool(data.get("biscotto_confirmed")),
        "confidence_boost": safe_int(data.get("confidence_boost"), 0, 0, 30),
        "home_team_objective": safe_str(data.get("home_team_objective")),
        "away_team_objective": safe_str(data.get("away_team_objective")),
        "mutual_benefit_found": safe_bool(data.get("mutual_benefit_found")),
        "mutual_benefit_reason": safe_str(
            data.get("mutual_benefit_reason"), "No clear mutual benefit"
        ),
        "h2h_pattern": safe_str(data.get("h2h_pattern"), "No data"),
        "club_relationship": safe_str(data.get("club_relationship"), "None found"),
        "manager_hints": safe_str(data.get("manager_hints"), "None found"),
        "market_sentiment": safe_str(data.get("market_sentiment"), "Unknown"),
        "additional_context": safe_str(data.get("additional_context"), ""),
        "final_recommendation": safe_str(data.get("final_recommendation"), "MONITOR LIVE"),
    }


def normalize_final_alert_verification(data: dict) -> dict:
    """
    Normalize final alert verification response with safe defaults.

    Ensures identical structure across DeepSeek and Claude 3 Haiku responses.
    Used by FinalAlertVerifier to validate alerts before Telegram delivery.

    Args:
        data: Raw parsed JSON from any AI provider

    Returns:
        Normalized dict with all expected fields
    """
    return {
        "verification_status": safe_str(data.get("verification_status"), "NEEDS_REVIEW"),
        "confidence_level": safe_str(data.get("confidence_level"), "LOW"),
        "should_send": safe_bool(data.get("should_send"), False),
        "logic_score": safe_int(data.get("logic_score"), 5, 0, 10),
        "data_accuracy_score": safe_int(data.get("data_accuracy_score"), 5, 0, 10),
        "reasoning_quality_score": safe_int(data.get("reasoning_quality_score"), 5, 0, 10),
        "market_validation": safe_str(data.get("market_validation"), "QUESTIONABLE"),
        "key_strengths": safe_list(data.get("key_strengths")),
        "key_weaknesses": safe_list(data.get("key_weaknesses")),
        "missing_information": safe_list(data.get("missing_information")),
        "rejection_reason": safe_str(data.get("rejection_reason"), ""),
        "final_recommendation": safe_str(data.get("final_recommendation"), "NO_BET"),
        "suggested_modifications": safe_str(data.get("suggested_modifications"), ""),
        "data_discrepancies": safe_list(data.get("data_discrepancies")),
        "discrepancy_impact": safe_str(data.get("discrepancy_impact"), "MINOR"),
        "adjusted_score_if_discrepancy": safe_int(
            data.get("adjusted_score_if_discrepancy"), 5, 0, 10
        ),
        "source_verification": {
            "source_confirmed": safe_bool(data.get("source_confirmed"), False),
            "cross_source_found": safe_bool(data.get("cross_source_found"), False),
            "source_bias_detected": safe_bool(data.get("source_bias_detected"), False),
            "source_reliability_adjusted": safe_str(
                data.get("source_reliability_adjusted"), "LOW"
            ),
            "verification_issues": safe_list(data.get("verification_issues")),
        },
    }


def normalize_match_enrichment(data: dict) -> dict:
    """
    Normalize match enrichment response with safe defaults.

    Args:
        data: Raw parsed JSON from any AI provider

    Returns:
        Normalized dict with all expected fields
    """
    return {
        "home_form": safe_str(data.get("home_form")),
        "home_form_trend": safe_str(data.get("home_form_trend")),
        "away_form": safe_str(data.get("away_form")),
        "away_form_trend": safe_str(data.get("away_form_trend")),
        "home_recent_news": safe_str(data.get("home_recent_news")),
        "away_recent_news": safe_str(data.get("away_recent_news")),
        "h2h_recent": safe_str(data.get("h2h_recent")),
        "h2h_goals_pattern": safe_str(data.get("h2h_goals_pattern")),
        "match_importance": safe_str(data.get("match_importance")),
        "home_motivation": safe_str(data.get("home_motivation")),
        "away_motivation": safe_str(data.get("away_motivation")),
        "weather_forecast": safe_str(data.get("weather_forecast")),
        "weather_impact": safe_str(data.get("weather_impact")),
        "additional_context": safe_str(data.get("additional_context"), ""),
        "data_freshness": safe_str(data.get("data_freshness"), "Unknown"),
    }
