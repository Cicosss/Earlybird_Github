"""
EarlyBird AI Response Parser V4.1

Shared parsing logic for AI provider responses (Gemini, Perplexity).
Handles JSON extraction, Pydantic validation, and safe defaults.
"""

import logging

# ============================================
# ORJSON OPTIMIZATION (Rust-based JSON parser)
# 3-10x faster than stdlib json
# ============================================
try:
    import orjson

    def _json_loads(s):
        """orjson.loads wrapper - returns dict from bytes or str."""
        if isinstance(s, str):
            s = s.encode("utf-8")
        return orjson.loads(s)

    _ORJSON_ENABLED = True
except ImportError:
    import json

    _json_loads = json.loads
    _ORJSON_ENABLED = False

logger = logging.getLogger(__name__)
if _ORJSON_ENABLED:
    logger.debug("⚡ orjson enabled for AI response parsing")

# Try to import Pydantic
try:
    from pydantic import BaseModel

    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False
    BaseModel = None

# Import enums for normalization
try:
    from src.schemas.perplexity_schemas import (
        BiscottoPotential,
        BTTSImpact,
        InjuryImpact,
        RefereeStrictness,
        RiskLevel,
    )

    _ENUMS_AVAILABLE = True
except ImportError:
    _ENUMS_AVAILABLE = False
    BiscottoPotential = None
    BTTSImpact = None
    InjuryImpact = None
    RefereeStrictness = None
    RiskLevel = None


def extract_json(text: str) -> dict:
    """
    Extract JSON object from potentially chatty AI response.

    Strategy: Find the LAST valid JSON block (AI often puts the real answer last).
    Handles multiple JSON objects in response safely.

    Args:
        text: Raw response text (may contain markdown, intro text, etc.)

    Returns:
        Parsed JSON dict

    Raises:
        ValueError: If no valid JSON found
    """
    if not text:
        raise ValueError("Empty response text")

    # Remove markdown code blocks if present
    clean_text = text.strip()
    clean_text = clean_text.replace("```json", "").replace("```", "")

    # Strategy: Try to find valid JSON by iterating backward from each '}'
    # This ensures we get the LAST valid JSON block (usually the real answer)
    last_valid_json = None
    last_valid_end = -1

    for i in range(len(clean_text) - 1, -1, -1):
        if clean_text[i] == "}":
            # Try to find matching '{' and parse
            brace_count = 0
            for j in range(i, -1, -1):
                if clean_text[j] == "}":
                    brace_count += 1
                elif clean_text[j] == "{":
                    brace_count -= 1
                    if brace_count == 0:
                        # Found potential JSON block
                        candidate = clean_text[j : i + 1]
                        try:
                            parsed = _json_loads(candidate)
                            # Valid JSON found - keep the one that ends latest
                            if i > last_valid_end:
                                last_valid_json = parsed
                                last_valid_end = i
                        except Exception:
                            # Expected: JSON parsing fails for non-JSON substrings
                            # This is normal behavior during JSON extraction, no logging needed
                            pass
                        break

    if last_valid_json is not None:
        return last_valid_json

    # Fallback: original simple approach
    first_brace = clean_text.find("{")
    last_brace = clean_text.rfind("}")

    if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
        raise ValueError("No valid JSON object found")

    json_str = clean_text[first_brace : last_brace + 1]
    return _json_loads(json_str)


def parse_ai_json(
    text_response: str, model_class: type = None, default_values: dict = None
) -> dict:
    """
    Parse AI response with Pydantic validation and safe defaults.

    Args:
        text_response: Raw AI response text
        model_class: Pydantic model class for validation (optional)
        default_values: Default values dict if parsing fails (optional)

    Returns:
        Validated dict with safe defaults
    """
    # Default fallback values (aligned with normalize_deep_dive_response)
    # Legacy fields removed (V6.0+): referee_stats, h2h_results, injuries, raw_intel
    if default_values is None:
        default_values = {
            "internal_crisis": "Unknown",
            "turnover_risk": "Unknown",
            "referee_intel": "Unknown",
            "biscotto_potential": "Unknown",
            "injury_impact": "None reported",
            "btts_impact": "Unknown",  # V4.1 - BTTS Tactical Impact
            "motivation_home": "Unknown",
            "motivation_away": "Unknown",
            "table_context": "Unknown",
        }

    try:
        # Extract JSON from response
        data = extract_json(text_response)

        # Validate with Pydantic if available
        if _PYDANTIC_AVAILABLE and model_class is not None:
            try:
                model = model_class(**data)
                return model.model_dump()
            except Exception as e:
                logger.warning(f"Pydantic validation failed: {e}. Using extracted data.")

        # Return extracted data with defaults for missing fields
        result = default_values.copy()
        result.update({k: v for k, v in data.items() if v is not None})
        return result

    except (ValueError, Exception) as e:
        # Catch both orjson.JSONDecodeError and json.JSONDecodeError via base Exception
        if "JSON" in str(type(e).__name__) or isinstance(e, ValueError):
            logger.warning(f"JSON extraction failed: {e}. Using defaults.")
            # Legacy raw_intel fallback removed (V6.0+) - system now uses structured outputs
            return default_values.copy()
        logger.warning(f"AI response parsing failed: {e}. Using defaults.")
        return default_values.copy()


def _normalize_risk_value(value: str, enum_class, default: str) -> str:
    """
    Normalize a risk/impact value to proper case.

    Args:
        value: Raw value from AI (e.g., "high", "HIGH", "High - explanation")
        enum_class: Enum class to validate against (e.g., RiskLevel)
        default: Default value if normalization fails

    Returns:
        Normalized value with proper case (e.g., "High - explanation")
    """
    if not value or not isinstance(value, str):
        return default

    value_lower = value.lower()

    # Check each enum value (case-insensitive)
    for enum_member in enum_class:
        enum_value_lower = enum_member.value.lower()
        if value_lower.startswith(enum_value_lower):
            # Normalize the case: preserve the explanation but use correct case
            return enum_member.value + value[len(enum_member.value) :]

    # If no match, return default
    return default


def normalize_deep_dive_response(data: dict) -> dict:
    """
    Normalize deep dive response to standard format.

    Ensures all expected fields are present with safe defaults and proper normalization.
    This function is used as a fallback when Pydantic validation fails.

    IMPORTANT: This function normalizes values to ensure consistency across the system.
    It handles case-insensitive matching and preserves explanations while normalizing prefixes.

    Args:
        data: Raw response data (can be None or empty dict)

    Returns:
        Normalized dict with standard fields, or empty dict if data is None
    """
    # Edge case: None or empty input
    if not data:
        return {}

    # Check if enums are available for proper normalization
    if _ENUMS_AVAILABLE:
        # Normalize each field with proper enum validation
        internal_crisis = _normalize_risk_value(data.get("internal_crisis"), RiskLevel, "Unknown")
        turnover_risk = _normalize_risk_value(data.get("turnover_risk"), RiskLevel, "Unknown")
        referee_intel = _normalize_risk_value(
            data.get("referee_intel"), RefereeStrictness, "Unknown"
        )
        biscotto_potential = _normalize_risk_value(
            data.get("biscotto_potential"), BiscottoPotential, "Unknown"
        )
        injury_impact = _normalize_risk_value(
            data.get("injury_impact"), InjuryImpact, "None reported"
        )
        btts_impact = _normalize_risk_value(data.get("btts_impact"), BTTSImpact, "Unknown")
        motivation_home = _normalize_risk_value(data.get("motivation_home"), RiskLevel, "Unknown")
        motivation_away = _normalize_risk_value(data.get("motivation_away"), RiskLevel, "Unknown")
    else:
        # Fallback: use raw values with defaults
        logger.warning("Enums not available, using basic fallback normalization")
        internal_crisis = data.get("internal_crisis") or "Unknown"
        turnover_risk = data.get("turnover_risk") or "Unknown"
        referee_intel = data.get("referee_intel") or "Unknown"
        biscotto_potential = data.get("biscotto_potential") or "Unknown"
        injury_impact = data.get("injury_impact") or "None reported"
        btts_impact = data.get("btts_impact") or "Unknown"
        motivation_home = data.get("motivation_home") or "Unknown"
        motivation_away = data.get("motivation_away") or "Unknown"

    return {
        # Core fields (aligned with DeepDiveResponse)
        "internal_crisis": internal_crisis,
        "turnover_risk": turnover_risk,
        "referee_intel": referee_intel,
        "biscotto_potential": biscotto_potential,
        "injury_impact": injury_impact,
        # BTTS Tactical Impact (V4.1)
        "btts_impact": btts_impact,
        # Motivation Intelligence (V4.2)
        "motivation_home": motivation_home,
        "motivation_away": motivation_away,
        "table_context": data.get("table_context") or "Unknown",
        # Legacy fields removed (V6.0+):
        # - referee_stats: Use referee_intel instead
        # - h2h_results: Not used in current analysis
        # - injuries: Use injury_impact instead
        # - raw_intel: Not needed with structured outputs
    }
