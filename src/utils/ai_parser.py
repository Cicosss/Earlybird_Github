"""
EarlyBird AI Response Parser V4.1

Shared parsing logic for AI provider responses (Gemini, Perplexity).
Handles JSON extraction, Pydantic validation, and safe defaults.
"""
import logging
import re
from typing import Dict, Optional, Type

# ============================================
# ORJSON OPTIMIZATION (Rust-based JSON parser)
# 3-10x faster than stdlib json
# ============================================
try:
    import orjson
    def _json_loads(s):
        """orjson.loads wrapper - returns dict from bytes or str."""
        if isinstance(s, str):
            s = s.encode('utf-8')
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


def extract_json(text: str) -> Dict:
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
        if clean_text[i] == '}':
            # Try to find matching '{' and parse
            brace_count = 0
            for j in range(i, -1, -1):
                if clean_text[j] == '}':
                    brace_count += 1
                elif clean_text[j] == '{':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found potential JSON block
                        candidate = clean_text[j:i+1]
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
    first_brace = clean_text.find('{')
    last_brace = clean_text.rfind('}')
    
    if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
        raise ValueError("No valid JSON object found")
    
    json_str = clean_text[first_brace:last_brace + 1]
    return _json_loads(json_str)


def parse_ai_json(
    text_response: str,
    model_class: Type = None,
    default_values: Dict = None
) -> Dict:
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
            "referee_stats": None,
            "h2h_results": None,
            "injuries": [],
            "raw_intel": None
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
            logger.warning(f"JSON extraction failed: {e}. Returning raw intel.")
            result = default_values.copy()
            result["raw_intel"] = text_response[:1000] if text_response else None
            return result
        logger.warning(f"AI response parsing failed: {e}. Using defaults.")
        return default_values.copy()


def normalize_deep_dive_response(data: Dict) -> Dict:
    """
    Normalize deep dive response to standard format.
    
    Ensures all expected fields are present with safe defaults.
    Handles legacy field names for backward compatibility.
    
    Args:
        data: Raw response data (can be None or empty dict)
        
    Returns:
        Normalized dict with standard fields, or empty dict if data is None
    """
    # Edge case: None or empty input
    if not data:
        return {}
    
    return {
        # Core fields
        "internal_crisis": data.get("internal_crisis") or "Unknown",
        "turnover_risk": data.get("turnover_risk") or "Unknown",
        "referee_intel": data.get("referee_intel") or "Unknown",
        "biscotto_potential": data.get("biscotto_potential") or "Unknown",
        "injury_impact": data.get("injury_impact") or "None reported",
        # BTTS Tactical Impact (V4.1)
        "btts_impact": data.get("btts_impact") or "Unknown",
        # Motivation Intelligence (V4.2)
        "motivation_home": data.get("motivation_home") or "Unknown",
        "motivation_away": data.get("motivation_away") or "Unknown",
        "table_context": data.get("table_context") or "Unknown",
        # Legacy fields for backward compatibility
        "referee_stats": data.get("referee_stats") or data.get("referee_intel"),
        "h2h_results": data.get("h2h_results") or data.get("h2h"),
        "injuries": data.get("injuries") or [],
        "raw_intel": data.get("raw_intel") or data.get("raw_response")
    }
