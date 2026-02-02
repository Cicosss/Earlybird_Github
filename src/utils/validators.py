"""
EarlyBird Validators V1.0

Validatori centralizzati per DTO critici del sistema.
Usabili sia in produzione (fail-fast) che nei test (assertion helpers).

Principi:
- Ogni validatore ritorna (is_valid, errors: List[str])
- Validazioni riutilizzabili tra produzione e test
- Messaggi di errore chiari e actionable
- Edge case gestiti esplicitamente

Componenti validati:
- VerificationRequest/Result (Verification Layer)
- NewsItem (News Hunter output)
- AnalysisResult (Analyzer output)
- AlertPayload (Notifier input)

Usage in tests:
    from src.utils.validators import validate_news_item, ValidationResult
    
    result = validate_news_item(news_data)
    assert result.is_valid, f"Invalid news: {result.errors}"

Usage in production:
    from src.utils.validators import validate_news_item
    
    result = validate_news_item(news_data)
    if not result.is_valid:
        logging.warning(f"Invalid news item: {result.errors}")
        return None  # Skip invalid data

Requirements: Self-Check Protocol compliance
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================
# VALIDATION RESULT
# ============================================

@dataclass
class ValidationResult:
    """
    Result of a validation check.
    
    Attributes:
        is_valid: True if all checks passed
        errors: List of error messages (empty if valid)
        warnings: List of non-fatal warnings
        context: Optional dict with validation context for debugging
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def __bool__(self) -> bool:
        """Allow using ValidationResult in boolean context."""
        return self.is_valid
    
    def add_error(self, msg: str) -> None:
        """Add an error and mark as invalid."""
        self.errors.append(msg)
        self.is_valid = False
    
    def add_warning(self, msg: str) -> None:
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(msg)
    
    def merge(self, other: 'ValidationResult') -> 'ValidationResult':
        """Merge another ValidationResult into this one."""
        self.is_valid = self.is_valid and other.is_valid
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.context.update(other.context)
        return self
    
    def format_report(self) -> str:
        """Format a human-readable validation report."""
        lines = []
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        lines.append(f"Validation: {status}")
        
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            for err in self.errors:
                lines.append(f"  - {err}")
        
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            for warn in self.warnings:
                lines.append(f"  - {warn}")
        
        return "\n".join(lines)


def ok() -> ValidationResult:
    """Create a valid result."""
    return ValidationResult(is_valid=True)


def fail(error: str) -> ValidationResult:
    """Create an invalid result with one error."""
    return ValidationResult(is_valid=False, errors=[error])


# ============================================
# PRIMITIVE VALIDATORS
# ============================================

def validate_non_empty_string(value: Any, field_name: str) -> ValidationResult:
    """Validate that value is a non-empty string."""
    if value is None:
        return fail(f"{field_name}: è None (richiesto stringa non vuota)")
    if not isinstance(value, str):
        return fail(f"{field_name}: tipo {type(value).__name__}, richiesto str")
    if not value.strip():
        return fail(f"{field_name}: stringa vuota o solo spazi")
    return ok()


def validate_positive_number(value: Any, field_name: str, allow_zero: bool = False) -> ValidationResult:
    """Validate that value is a positive number."""
    if value is None:
        return fail(f"{field_name}: è None (richiesto numero)")
    if not isinstance(value, (int, float)):
        return fail(f"{field_name}: tipo {type(value).__name__}, richiesto int/float")
    if allow_zero:
        if value < 0:
            return fail(f"{field_name}: {value} è negativo")
    else:
        if value <= 0:
            return fail(f"{field_name}: {value} non è positivo")
    return ok()


def validate_in_range(value: Any, field_name: str, min_val: float, max_val: float) -> ValidationResult:
    """Validate that value is within a range."""
    if value is None:
        return fail(f"{field_name}: è None")
    if not isinstance(value, (int, float)):
        return fail(f"{field_name}: tipo {type(value).__name__}, richiesto numero")
    if value < min_val or value > max_val:
        return fail(f"{field_name}: {value} fuori range [{min_val}, {max_val}]")
    return ok()


def validate_in_list(value: Any, field_name: str, valid_values: List[Any]) -> ValidationResult:
    """Validate that value is in a list of valid values."""
    if value not in valid_values:
        return fail(f"{field_name}: '{value}' non in {valid_values}")
    return ok()


def validate_list_not_empty(value: Any, field_name: str) -> ValidationResult:
    """Validate that value is a non-empty list."""
    if value is None:
        return fail(f"{field_name}: è None (richiesta lista)")
    if not isinstance(value, list):
        return fail(f"{field_name}: tipo {type(value).__name__}, richiesto list")
    if len(value) == 0:
        return fail(f"{field_name}: lista vuota")
    return ok()


def validate_dict_has_keys(value: Any, field_name: str, required_keys: List[str]) -> ValidationResult:
    """Validate that dict has all required keys."""
    if value is None:
        return fail(f"{field_name}: è None (richiesto dict)")
    if not isinstance(value, dict):
        return fail(f"{field_name}: tipo {type(value).__name__}, richiesto dict")
    
    missing = [k for k in required_keys if k not in value]
    if missing:
        return fail(f"{field_name}: chiavi mancanti {missing}")
    return ok()


# ============================================
# NEWS ITEM VALIDATOR
# ============================================

# Required fields for a news item from news_hunter
NEWS_ITEM_REQUIRED_FIELDS = ['match_id', 'team', 'title', 'snippet', 'link', 'source', 'search_type']

# Valid search types
VALID_SEARCH_TYPES = [
    # TIER 0 - Real-time monitoring
    'browser_monitor', 'aleague_scraper',
    # Beat Writers (priority sources)
    'beat_writer_cache', 'beat_writer_priority', 'insider_beat_writer',
    # TIER 1 - Search engines
    'ddg_local', 'ddg_twitter', 'ddg_generic', 
    'serper_news', 'serper_search',
    'local_site_dork', 'generic', 'dynamic_country',
    # Twitter Intel
    'twitter_intel', 'twitter_intel_cache',
    # Exotic leagues (dynamic)
    'exotic_aleagues_official', 'exotic_keepup', 'exotic_foxsports_au',
    'exotic_twitter_proxy', 'exotic_dongqiudi',
    'exotic_nikkansports', 'exotic_official_releases',
    'exotic_lance_ticker', 'exotic_globo_esporte',
]

# Valid confidence levels
VALID_CONFIDENCE_LEVELS = ['HIGH', 'MEDIUM', 'LOW', None]


def validate_news_item(item: Dict[str, Any], strict: bool = False, allow_null_match_id: bool = False) -> ValidationResult:
    """
    Validate a news item from news_hunter.
    
    Args:
        item: News item dict
        strict: If True, also validate optional fields
        allow_null_match_id: If True, allow match_id to be None (for browser_monitor pre-matching)
        
    Returns:
        ValidationResult with errors if invalid
        
    Edge cases handled:
        - None item
        - Missing required fields
        - Empty strings in required fields
        - Invalid search_type
        - Invalid confidence level
    """
    result = ok()
    
    # Edge case: None or not dict
    if item is None:
        return fail("news_item: è None")
    if not isinstance(item, dict):
        return fail(f"news_item: tipo {type(item).__name__}, richiesto dict")
    
    # Required fields
    for field in NEWS_ITEM_REQUIRED_FIELDS:
        if field not in item:
            result.add_error(f"Campo richiesto mancante: {field}")
        elif field == 'match_id':
            # match_id può essere None per browser_monitor pre-matching
            if item[field] is None and not allow_null_match_id:
                result.add_warning(f"match_id è None (pre-matching)")
        elif field in ['title', 'snippet', 'link', 'source']:
            # These must be non-empty strings
            field_result = validate_non_empty_string(item[field], field)
            if not field_result:
                result.merge(field_result)
    
    # Validate search_type if present
    search_type = item.get('search_type', '')
    if search_type and search_type not in VALID_SEARCH_TYPES:
        # Check for dynamic exotic types (exotic_*)
        if not search_type.startswith('exotic_'):
            result.add_warning(f"search_type sconosciuto: {search_type}")
    
    # Validate confidence if present
    if 'confidence' in item:
        conf = item['confidence']
        # Confidence può essere stringa ('HIGH', 'MEDIUM', 'LOW') o float (0.0-1.0)
        if isinstance(conf, str) and conf not in VALID_CONFIDENCE_LEVELS:
            result.add_warning(f"confidence non standard: {conf}")
        elif isinstance(conf, (int, float)) and not (0 <= conf <= 1):
            result.add_warning(f"confidence fuori range [0,1]: {conf}")
    
    # Strict mode: validate optional fields
    if strict:
        if 'priority_boost' in item:
            boost_result = validate_positive_number(item['priority_boost'], 'priority_boost')
            if not boost_result:
                result.merge(boost_result)
        
        if 'minutes_old' in item:
            age_result = validate_positive_number(item['minutes_old'], 'minutes_old', allow_zero=True)
            if not age_result:
                result.merge(age_result)
    
    return result


# ============================================
# VERIFICATION REQUEST VALIDATOR
# ============================================

VALID_INJURY_SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE']

VALID_MARKETS = [
    'Over 2.5 Goals', 'Under 2.5 Goals', 'Over 1.5 Goals', 'Under 1.5 Goals',
    'Over 3.5 Goals', 'Under 3.5 Goals',
    '1', 'X', '2', '1X', 'X2', '12',
    'BTTS', 'BTTS Yes', 'BTTS No',
    'Over 9.5 Corners', 'Over 10.5 Corners', 'Under 9.5 Corners',
    'Over 4.5 Cards', 'Over 5.5 Cards', 'Under 4.5 Cards',
]


def validate_verification_request(request: Any) -> ValidationResult:
    """
    Validate a VerificationRequest object or dict.
    
    Args:
        request: VerificationRequest instance or dict with same fields
        
    Returns:
        ValidationResult with errors if invalid
        
    Edge cases handled:
        - None request
        - Missing required fields
        - Invalid score range
        - Invalid injury severity
        - Invalid market
    """
    result = ok()
    
    if request is None:
        return fail("VerificationRequest: è None")
    
    # Convert to dict if it's an object
    data = request if isinstance(request, dict) else (
        request.to_dict() if hasattr(request, 'to_dict') else request.__dict__
    )
    
    # Required string fields
    required_strings = ['match_id', 'home_team', 'away_team', 'match_date', 'league', 'suggested_market']
    for field in required_strings:
        if field not in data:
            result.add_error(f"Campo richiesto mancante: {field}")
        else:
            field_result = validate_non_empty_string(data[field], field)
            if not field_result:
                result.merge(field_result)
    
    # Score validation (0-10)
    if 'preliminary_score' in data:
        score_result = validate_in_range(data['preliminary_score'], 'preliminary_score', 0, 10)
        if not score_result:
            result.merge(score_result)
    else:
        result.add_error("Campo richiesto mancante: preliminary_score")
    
    # Injury severity validation
    for severity_field in ['home_injury_severity', 'away_injury_severity']:
        if severity_field in data:
            severity = data[severity_field]
            if severity and severity.upper() not in VALID_INJURY_SEVERITIES:
                result.add_warning(f"{severity_field}: '{severity}' non standard")
    
    # Market validation
    if 'suggested_market' in data:
        market = data['suggested_market']
        if market and market not in VALID_MARKETS:
            # Non-standard market - warning, not error (could be new market type)
            result.add_warning(f"suggested_market: '{market}' non in lista standard")
    
    return result


# ============================================
# VERIFICATION RESULT VALIDATOR
# ============================================

VALID_VERIFICATION_STATUSES = ['confirm', 'reject', 'change_market']


def validate_verification_result(result_obj: Any) -> ValidationResult:
    """
    Validate a VerificationResult object or dict.
    
    Args:
        result_obj: VerificationResult instance or dict
        
    Returns:
        ValidationResult with errors if invalid
        
    Edge cases handled:
        - None result
        - Invalid status
        - Score out of range
        - REJECT without rejection_reason
        - CHANGE_MARKET without recommended_market
    """
    result = ok()
    
    if result_obj is None:
        return fail("VerificationResult: è None")
    
    # Convert to dict
    if hasattr(result_obj, 'to_dict'):
        data = result_obj.to_dict()
    elif hasattr(result_obj, '__dict__'):
        data = result_obj.__dict__
    else:
        data = result_obj
    
    # Status validation
    status = data.get('status')
    if status is None:
        result.add_error("status: è None (richiesto)")
    else:
        # Handle enum or string
        status_str = status.value if hasattr(status, 'value') else str(status)
        if status_str.lower() not in VALID_VERIFICATION_STATUSES:
            result.add_error(f"status: '{status_str}' non valido")
        
        # Cross-field validation
        if status_str.lower() == 'reject':
            if not data.get('rejection_reason'):
                result.add_error("REJECT richiede rejection_reason non vuoto")
        
        if status_str.lower() == 'change_market':
            if not data.get('recommended_market'):
                result.add_error("CHANGE_MARKET richiede recommended_market non vuoto")
    
    # Score validations
    for score_field in ['original_score', 'adjusted_score']:
        if score_field in data and data[score_field] is not None:
            score_result = validate_in_range(data[score_field], score_field, 0, 10)
            if not score_result:
                result.merge(score_result)
    
    # Confidence validation
    if 'overall_confidence' in data:
        conf = data['overall_confidence']
        if conf and conf not in ['HIGH', 'MEDIUM', 'LOW']:
            result.add_warning(f"overall_confidence: '{conf}' non standard")
    
    return result


# ============================================
# ANALYSIS RESULT VALIDATOR
# ============================================

VALID_VERDICTS = ['BET', 'NO BET', 'MONITOR']
VALID_PRIMARY_DRIVERS = ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN']


def validate_analysis_result(analysis: Dict[str, Any]) -> ValidationResult:
    """
    Validate an analysis result from analyzer.py.
    
    Args:
        analysis: Analysis result dict from validate_ai_response
        
    Returns:
        ValidationResult with errors if invalid
        
    Edge cases handled:
        - None analysis
        - Invalid verdict
        - Confidence out of range
        - Invalid primary_driver
        - BET without recommended_market
    """
    result = ok()
    
    if analysis is None:
        return fail("analysis: è None")
    if not isinstance(analysis, dict):
        return fail(f"analysis: tipo {type(analysis).__name__}, richiesto dict")
    
    # Verdict validation
    verdict = analysis.get('final_verdict')
    if verdict is None:
        result.add_error("final_verdict: è None (richiesto)")
    elif verdict not in VALID_VERDICTS:
        result.add_error(f"final_verdict: '{verdict}' non in {VALID_VERDICTS}")
    
    # Confidence validation (0-100)
    confidence = analysis.get('confidence')
    if confidence is not None:
        conf_result = validate_in_range(confidence, 'confidence', 0, 100)
        if not conf_result:
            result.merge(conf_result)
    
    # Primary driver validation
    driver = analysis.get('primary_driver')
    if driver and driver not in VALID_PRIMARY_DRIVERS:
        result.add_warning(f"primary_driver: '{driver}' non standard")
    
    # Cross-field: BET requires recommended_market
    if verdict == 'BET':
        if not analysis.get('recommended_market'):
            result.add_warning("BET senza recommended_market")
    
    return result


# ============================================
# SAFE DICTIONARY ACCESS UTILITIES
# ============================================

def safe_get(data: Any, *keys, default: Any = None) -> Any:
    """
    Safely access nested dictionary keys with type checking.
    
    This function prevents AttributeError crashes when accessing nested dictionaries
    that might contain non-dict values (strings, None, etc.).
    
    Args:
        data: The data structure to access (dict, list, or any type)
        *keys: One or more keys to access in sequence
        default: Default value to return if any access fails
        
    Returns:
        The value at the nested key path, or default if access fails
        
    Examples:
        >>> safe_get({'a': {'b': {'c': 1}}}, 'a', 'b', 'c')
        1
        >>> safe_get({'a': 'not_a_dict'}, 'a', 'b')
        None
        >>> safe_get({'a': {'b': 1}}, 'a', 'missing', default='fallback')
        'fallback'
        >>> safe_get(None, 'a', 'b')
        None
    """
    current = data
    
    for key in keys:
        # Check if current is a dict before accessing
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            # Current is not a dict (could be string, None, list, etc.)
            return default
    
    return current if current is not None else default


def safe_list_get(data: Any, index: int, default: Any = None) -> Any:
    """
    Safely access list elements with bounds checking.
    
    This function prevents IndexError crashes when accessing list elements
    that might not exist or when data is not a list.
    
    Args:
        data: The data structure to access (list or any type)
        index: The index to access
        default: Default value to return if access fails
        
    Returns:
        The element at the index, or default if access fails
        
    Examples:
        >>> safe_list_get([1, 2, 3], 1)
        2
        >>> safe_list_get([1, 2, 3], 10)
        None
        >>> safe_list_get('not_a_list', 0)
        None
        >>> safe_list_get([], 0, default='empty')
        'empty'
    """
    if isinstance(data, list) and 0 <= index < len(data):
        return data[index]
    return default


def safe_dict_get(data: Any, key: Any, default: Any = None) -> Any:
    """
    Safely access a dictionary key with type checking.
    
    This is a single-level version of safe_get for simpler use cases.
    
    Args:
        data: The data structure to access (dict or any type)
        key: The key to access
        default: Default value to return if access fails
        
    Returns:
        The value at the key, or default if access fails
        
    Examples:
        >>> safe_dict_get({'a': 1}, 'a')
        1
        >>> safe_dict_get('not_a_dict', 'a')
        None
        >>> safe_dict_get({'a': 1}, 'missing', default='fallback')
        'fallback'
    """
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def ensure_dict(data: Any, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Ensure that data is a dictionary, converting or defaulting if not.
    
    This is useful for defense-in-depth when you expect a dict but might
    receive a string, None, or other type.
    
    Args:
        data: The data to ensure is a dict
        default: Default dict to return if data is not a dict (defaults to empty dict)
        
    Returns:
        A dictionary (either the original if it's a dict, or the default)
        
    Examples:
        >>> ensure_dict({'a': 1})
        {'a': 1}
        >>> ensure_dict('string_value')
        {}
        >>> ensure_dict(None, default={'fallback': True})
        {'fallback': True}
    """
    if isinstance(data, dict):
        return data
    return default if default is not None else {}


def ensure_list(data: Any, default: Optional[List[Any]] = None) -> List[Any]:
    """
    Ensure that data is a list, converting or defaulting if not.
    
    Args:
        data: The data to ensure is a list
        default: Default list to return if data is not a list (defaults to empty list)
        
    Returns:
        A list (either the original if it's a list, or the default)
        
    Examples:
        >>> ensure_list([1, 2, 3])
        [1, 2, 3]
        >>> ensure_list('not_a_list')
        []
        >>> ensure_list(None, default=['fallback'])
        ['fallback']
    """
    if isinstance(data, list):
        return data
    return default if default is not None else []


# ============================================
# ALERT PAYLOAD VALIDATOR
# ============================================

def validate_alert_payload(payload: Dict[str, Any]) -> ValidationResult:
    """
    Validate an alert payload before sending to Telegram.
    
    Args:
        payload: Alert data dict
        
    Returns:
        ValidationResult with errors if invalid
        
    Edge cases handled:
        - None payload
        - Missing required fields
        - Invalid score
        - Empty news_summary
    """
    result = ok()
    
    if payload is None:
        return fail("alert_payload: è None")
    if not isinstance(payload, dict):
        return fail(f"alert_payload: tipo {type(payload).__name__}, richiesto dict")
    
    # Required fields
    required = ['home_team', 'away_team', 'league', 'score', 'news_summary']
    for field in required:
        if field not in payload:
            result.add_error(f"Campo richiesto mancante: {field}")
    
    # Team names
    for team_field in ['home_team', 'away_team']:
        if team_field in payload:
            team_result = validate_non_empty_string(payload[team_field], team_field)
            if not team_result:
                result.merge(team_result)
    
    # Score (0-10)
    if 'score' in payload:
        score_result = validate_in_range(payload['score'], 'score', 0, 10)
        if not score_result:
            result.merge(score_result)
    
    # News summary
    if 'news_summary' in payload:
        summary_result = validate_non_empty_string(payload['news_summary'], 'news_summary')
        if not summary_result:
            result.merge(summary_result)
    
    return result


# ============================================
# BATCH VALIDATION HELPER
# ============================================

def validate_batch(
    items: List[Any],
    validator: Callable[[Any], ValidationResult],
    item_name: str = "item"
) -> Tuple[List[Any], List[Tuple[int, ValidationResult]]]:
    """
    Validate a batch of items, returning valid items and errors.
    
    Args:
        items: List of items to validate
        validator: Validation function to apply
        item_name: Name for error messages
        
    Returns:
        Tuple of (valid_items, errors) where errors is list of (index, ValidationResult)
        
    Usage:
        valid_news, errors = validate_batch(news_items, validate_news_item, "news")
        if errors:
            for idx, err in errors:
                logging.warning(f"Invalid news at index {idx}: {err.errors}")
    """
    valid_items = []
    errors = []
    
    if items is None:
        return [], [(0, fail(f"{item_name}_list: è None"))]
    
    for idx, item in enumerate(items):
        result = validator(item)
        if result.is_valid:
            valid_items.append(item)
        else:
            errors.append((idx, result))
    
    return valid_items, errors


# ============================================
# ASSERTION HELPERS FOR TESTS
# ============================================

def assert_valid_news_item(item: Dict[str, Any], msg: str = "") -> None:
    """
    Assert that a news item is valid. Raises AssertionError if not.
    
    Usage in tests:
        assert_valid_news_item(news_data, "Browser monitor output")
    """
    result = validate_news_item(item)
    assert result.is_valid, f"{msg}\n{result.format_report()}"


def assert_valid_verification_request(request: Any, msg: str = "") -> None:
    """Assert that a VerificationRequest is valid."""
    result = validate_verification_request(request)
    assert result.is_valid, f"{msg}\n{result.format_report()}"


def assert_valid_verification_result(result_obj: Any, msg: str = "") -> None:
    """Assert that a VerificationResult is valid."""
    result = validate_verification_result(result_obj)
    assert result.is_valid, f"{msg}\n{result.format_report()}"


def assert_valid_analysis(analysis: Dict[str, Any], msg: str = "") -> None:
    """Assert that an analysis result is valid."""
    result = validate_analysis_result(analysis)
    assert result.is_valid, f"{msg}\n{result.format_report()}"


def assert_valid_alert(payload: Dict[str, Any], msg: str = "") -> None:
    """Assert that an alert payload is valid."""
    result = validate_alert_payload(payload)
    assert result.is_valid, f"{msg}\n{result.format_report()}"
