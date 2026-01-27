"""
Test per il modulo validators.py

Verifica che i validatori centralizzati funzionino correttamente
e gestiscano tutti gli edge case.

Ogni test segue il pattern:
1. Setup dati validi/invalidi
2. Chiama validatore
3. Verifica risultato

Requirements: Self-Check Protocol compliance
"""
import pytest
from datetime import datetime, timezone


class TestValidationResult:
    """Test per ValidationResult dataclass."""
    
    def test_valid_result_is_truthy(self):
        """ValidationResult valido deve essere truthy."""
        from src.utils.validators import ok
        
        result = ok()
        assert result.is_valid is True
        assert bool(result) is True
        assert len(result.errors) == 0
    
    def test_invalid_result_is_falsy(self):
        """ValidationResult invalido deve essere falsy."""
        from src.utils.validators import fail
        
        result = fail("Test error")
        assert result.is_valid is False
        assert bool(result) is False
        assert "Test error" in result.errors
    
    def test_add_error_marks_invalid(self):
        """add_error deve marcare il risultato come invalido."""
        from src.utils.validators import ok
        
        result = ok()
        assert result.is_valid is True
        
        result.add_error("Something went wrong")
        assert result.is_valid is False
        assert "Something went wrong" in result.errors
    
    def test_add_warning_preserves_validity(self):
        """add_warning non deve cambiare la validità."""
        from src.utils.validators import ok
        
        result = ok()
        result.add_warning("Minor issue")
        
        assert result.is_valid is True
        assert "Minor issue" in result.warnings
    
    def test_merge_combines_results(self):
        """merge deve combinare errori e warning."""
        from src.utils.validators import ok, fail
        
        result1 = ok()
        result1.add_warning("Warning 1")
        
        result2 = fail("Error 1")
        result2.add_warning("Warning 2")
        
        result1.merge(result2)
        
        assert result1.is_valid is False
        assert "Error 1" in result1.errors
        assert "Warning 1" in result1.warnings
        assert "Warning 2" in result1.warnings
    
    def test_format_report_readable(self):
        """format_report deve produrre output leggibile."""
        from src.utils.validators import fail
        
        result = fail("Test error")
        result.add_warning("Test warning")
        
        report = result.format_report()
        
        assert "INVALID" in report
        assert "Test error" in report
        assert "Test warning" in report


class TestPrimitiveValidators:
    """Test per validatori primitivi."""
    
    def test_validate_non_empty_string_valid(self):
        """Stringa non vuota deve essere valida."""
        from src.utils.validators import validate_non_empty_string
        
        result = validate_non_empty_string("hello", "test_field")
        assert result.is_valid is True
    
    def test_validate_non_empty_string_none(self):
        """None deve essere invalido."""
        from src.utils.validators import validate_non_empty_string
        
        result = validate_non_empty_string(None, "test_field")
        assert result.is_valid is False
        assert "None" in result.errors[0]
    
    def test_validate_non_empty_string_empty(self):
        """Stringa vuota deve essere invalida."""
        from src.utils.validators import validate_non_empty_string
        
        result = validate_non_empty_string("", "test_field")
        assert result.is_valid is False
        assert "vuota" in result.errors[0]
    
    def test_validate_non_empty_string_whitespace(self):
        """Stringa con solo spazi deve essere invalida."""
        from src.utils.validators import validate_non_empty_string
        
        result = validate_non_empty_string("   ", "test_field")
        assert result.is_valid is False
    
    def test_validate_non_empty_string_wrong_type(self):
        """Tipo sbagliato deve essere invalido."""
        from src.utils.validators import validate_non_empty_string
        
        result = validate_non_empty_string(123, "test_field")
        assert result.is_valid is False
        assert "int" in result.errors[0]
    
    def test_validate_positive_number_valid(self):
        """Numero positivo deve essere valido."""
        from src.utils.validators import validate_positive_number
        
        result = validate_positive_number(5, "test_field")
        assert result.is_valid is True
        
        result = validate_positive_number(3.14, "test_field")
        assert result.is_valid is True
    
    def test_validate_positive_number_zero(self):
        """Zero deve essere invalido di default, valido con allow_zero."""
        from src.utils.validators import validate_positive_number
        
        result = validate_positive_number(0, "test_field")
        assert result.is_valid is False
        
        result = validate_positive_number(0, "test_field", allow_zero=True)
        assert result.is_valid is True
    
    def test_validate_positive_number_negative(self):
        """Numero negativo deve essere invalido."""
        from src.utils.validators import validate_positive_number
        
        result = validate_positive_number(-5, "test_field")
        assert result.is_valid is False
    
    def test_validate_in_range_valid(self):
        """Numero nel range deve essere valido."""
        from src.utils.validators import validate_in_range
        
        result = validate_in_range(5, "score", 0, 10)
        assert result.is_valid is True
        
        # Boundary values
        result = validate_in_range(0, "score", 0, 10)
        assert result.is_valid is True
        
        result = validate_in_range(10, "score", 0, 10)
        assert result.is_valid is True
    
    def test_validate_in_range_out_of_bounds(self):
        """Numero fuori range deve essere invalido."""
        from src.utils.validators import validate_in_range
        
        result = validate_in_range(-1, "score", 0, 10)
        assert result.is_valid is False
        
        result = validate_in_range(11, "score", 0, 10)
        assert result.is_valid is False
    
    def test_validate_in_list_valid(self):
        """Valore nella lista deve essere valido."""
        from src.utils.validators import validate_in_list
        
        result = validate_in_list("BET", "verdict", ["BET", "NO BET", "MONITOR"])
        assert result.is_valid is True
    
    def test_validate_in_list_invalid(self):
        """Valore non nella lista deve essere invalido."""
        from src.utils.validators import validate_in_list
        
        result = validate_in_list("INVALID", "verdict", ["BET", "NO BET"])
        assert result.is_valid is False
    
    def test_validate_dict_has_keys_valid(self):
        """Dict con tutte le chiavi deve essere valido."""
        from src.utils.validators import validate_dict_has_keys
        
        data = {'a': 1, 'b': 2, 'c': 3}
        result = validate_dict_has_keys(data, "test", ['a', 'b'])
        assert result.is_valid is True
    
    def test_validate_dict_has_keys_missing(self):
        """Dict con chiavi mancanti deve essere invalido."""
        from src.utils.validators import validate_dict_has_keys
        
        data = {'a': 1}
        result = validate_dict_has_keys(data, "test", ['a', 'b', 'c'])
        assert result.is_valid is False
        assert "b" in str(result.errors) or "c" in str(result.errors)


class TestNewsItemValidator:
    """Test per validate_news_item."""
    
    def test_valid_news_item(self, mock_news_item):
        """News item valido deve passare."""
        from src.utils.validators import validate_news_item
        
        result = validate_news_item(mock_news_item)
        assert result.is_valid is True
    
    def test_news_item_none(self):
        """None deve essere invalido."""
        from src.utils.validators import validate_news_item
        
        result = validate_news_item(None)
        assert result.is_valid is False
        assert "None" in result.errors[0]
    
    def test_news_item_missing_required_field(self, mock_news_item):
        """News item senza campo richiesto deve essere invalido."""
        from src.utils.validators import validate_news_item
        
        del mock_news_item['title']
        result = validate_news_item(mock_news_item)
        assert result.is_valid is False
        assert "title" in str(result.errors)
    
    def test_news_item_empty_title(self, mock_news_item):
        """News item con titolo vuoto deve essere invalido."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['title'] = ""
        result = validate_news_item(mock_news_item)
        assert result.is_valid is False
    
    def test_news_item_unknown_search_type_warning(self, mock_news_item):
        """search_type sconosciuto deve generare warning, non errore."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['search_type'] = 'unknown_type'
        result = validate_news_item(mock_news_item)
        
        # Deve essere valido ma con warning
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert "search_type" in result.warnings[0]
    
    def test_news_item_exotic_search_type_no_warning(self, mock_news_item):
        """search_type exotic_* dinamico non deve generare warning."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['search_type'] = 'exotic_custom_source'
        result = validate_news_item(mock_news_item)
        
        # Deve essere valido senza warning per exotic_*
        assert result.is_valid is True
        # Nessun warning per search_type exotic
        search_type_warnings = [w for w in result.warnings if 'search_type' in w]
        assert len(search_type_warnings) == 0
    
    def test_news_item_null_match_id_warning(self, mock_news_item):
        """match_id None deve generare warning (pre-matching)."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['match_id'] = None
        result = validate_news_item(mock_news_item)
        
        # Valido ma con warning
        assert result.is_valid is True
        assert any('match_id' in w for w in result.warnings)
    
    def test_news_item_null_match_id_allowed(self, mock_news_item):
        """match_id None con allow_null_match_id=True non deve generare warning."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['match_id'] = None
        result = validate_news_item(mock_news_item, allow_null_match_id=True)
        
        # Valido senza warning per match_id
        assert result.is_valid is True
        match_id_warnings = [w for w in result.warnings if 'match_id' in w]
        assert len(match_id_warnings) == 0
    
    def test_news_item_confidence_float(self, mock_news_item):
        """confidence come float [0,1] deve essere valido."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['confidence'] = 0.85
        result = validate_news_item(mock_news_item)
        
        assert result.is_valid is True
        # Nessun warning per confidence valido
        conf_warnings = [w for w in result.warnings if 'confidence' in w]
        assert len(conf_warnings) == 0
    
    def test_news_item_confidence_float_out_of_range(self, mock_news_item):
        """confidence float fuori [0,1] deve generare warning."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['confidence'] = 1.5  # > 1
        result = validate_news_item(mock_news_item)
        
        assert result.is_valid is True  # Warning, non errore
        assert any('confidence' in w for w in result.warnings)
    
    def test_news_item_strict_mode(self, mock_news_item):
        """Strict mode deve validare anche campi opzionali."""
        from src.utils.validators import validate_news_item
        
        mock_news_item['priority_boost'] = -1  # Invalid
        
        # Normal mode: valid
        result = validate_news_item(mock_news_item, strict=False)
        assert result.is_valid is True
        
        # Strict mode: invalid
        result = validate_news_item(mock_news_item, strict=True)
        assert result.is_valid is False


class TestVerificationRequestValidator:
    """Test per validate_verification_request."""
    
    def test_valid_request(self, mock_verification_request):
        """Request valido deve passare."""
        from src.utils.validators import validate_verification_request
        
        result = validate_verification_request(mock_verification_request)
        assert result.is_valid is True
    
    def test_request_none(self):
        """None deve essere invalido."""
        from src.utils.validators import validate_verification_request
        
        result = validate_verification_request(None)
        assert result.is_valid is False
    
    def test_request_missing_match_id(self, mock_verification_request):
        """Request senza match_id deve essere invalido."""
        from src.utils.validators import validate_verification_request
        
        del mock_verification_request['match_id']
        result = validate_verification_request(mock_verification_request)
        assert result.is_valid is False
        assert "match_id" in str(result.errors)
    
    def test_request_score_out_of_range(self, mock_verification_request):
        """Score fuori range deve essere invalido."""
        from src.utils.validators import validate_verification_request
        
        mock_verification_request['preliminary_score'] = 15  # > 10
        result = validate_verification_request(mock_verification_request)
        assert result.is_valid is False
        assert "preliminary_score" in str(result.errors)
    
    def test_request_invalid_severity_warning(self, mock_verification_request):
        """Severity non standard deve generare warning."""
        from src.utils.validators import validate_verification_request
        
        mock_verification_request['home_injury_severity'] = 'UNKNOWN'
        result = validate_verification_request(mock_verification_request)
        
        # Warning, not error
        assert len(result.warnings) > 0


class TestVerificationResultValidator:
    """Test per validate_verification_result."""
    
    def test_valid_confirm_result(self):
        """Result CONFIRM valido deve passare."""
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'confirm',
            'original_score': 8.0,
            'adjusted_score': 8.0,
            'original_market': 'Over 2.5 Goals',
            'overall_confidence': 'HIGH',
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid is True
    
    def test_reject_without_reason(self):
        """REJECT senza rejection_reason deve essere invalido."""
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'reject',
            'original_score': 8.0,
            'adjusted_score': 0.0,
            # Missing rejection_reason
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid is False
        assert "rejection_reason" in str(result.errors)
    
    def test_change_market_without_recommended(self):
        """CHANGE_MARKET senza recommended_market deve essere invalido."""
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'change_market',
            'original_score': 8.0,
            'adjusted_score': 7.5,
            # Missing recommended_market
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid is False
        assert "recommended_market" in str(result.errors)
    
    def test_invalid_status(self):
        """Status invalido deve essere errore."""
        from src.utils.validators import validate_verification_result
        
        result_data = {
            'status': 'invalid_status',
            'original_score': 8.0,
            'adjusted_score': 8.0,
        }
        
        result = validate_verification_result(result_data)
        assert result.is_valid is False


class TestAnalysisResultValidator:
    """Test per validate_analysis_result."""
    
    def test_valid_analysis(self, mock_analysis_result):
        """Analysis valido deve passare."""
        from src.utils.validators import validate_analysis_result
        
        result = validate_analysis_result(mock_analysis_result)
        assert result.is_valid is True
    
    def test_analysis_none(self):
        """None deve essere invalido."""
        from src.utils.validators import validate_analysis_result
        
        result = validate_analysis_result(None)
        assert result.is_valid is False
    
    def test_analysis_invalid_verdict(self, mock_analysis_result):
        """Verdict invalido deve essere errore."""
        from src.utils.validators import validate_analysis_result
        
        mock_analysis_result['final_verdict'] = 'INVALID'
        result = validate_analysis_result(mock_analysis_result)
        assert result.is_valid is False
    
    def test_analysis_confidence_out_of_range(self, mock_analysis_result):
        """Confidence fuori range deve essere errore."""
        from src.utils.validators import validate_analysis_result
        
        mock_analysis_result['confidence'] = 150  # > 100
        result = validate_analysis_result(mock_analysis_result)
        assert result.is_valid is False
    
    def test_analysis_bet_without_market_warning(self, mock_analysis_result):
        """BET senza recommended_market deve generare warning."""
        from src.utils.validators import validate_analysis_result
        
        mock_analysis_result['final_verdict'] = 'BET'
        mock_analysis_result['recommended_market'] = None
        
        result = validate_analysis_result(mock_analysis_result)
        # Warning, not error
        assert len(result.warnings) > 0


class TestBatchValidation:
    """Test per validate_batch."""
    
    def test_batch_all_valid(self, mock_news_items):
        """Batch con tutti item validi deve restituire tutti."""
        from src.utils.validators import validate_batch, validate_news_item
        
        valid, errors = validate_batch(mock_news_items, validate_news_item, "news")
        
        assert len(valid) == len(mock_news_items)
        assert len(errors) == 0
    
    def test_batch_some_invalid(self, mock_news_items):
        """Batch con alcuni item invalidi deve filtrarli."""
        from src.utils.validators import validate_batch, validate_news_item
        
        # Rendi uno invalido
        mock_news_items[0]['title'] = ""
        
        valid, errors = validate_batch(mock_news_items, validate_news_item, "news")
        
        assert len(valid) == 1
        assert len(errors) == 1
        assert errors[0][0] == 0  # Index of invalid item
    
    def test_batch_none_input(self):
        """Batch con None deve restituire errore."""
        from src.utils.validators import validate_batch, validate_news_item
        
        valid, errors = validate_batch(None, validate_news_item, "news")
        
        assert len(valid) == 0
        assert len(errors) == 1


class TestAssertionHelpers:
    """Test per assertion helpers."""
    
    def test_assert_valid_news_item_passes(self, mock_news_item):
        """assert_valid_news_item non deve sollevare eccezione per item valido."""
        from src.utils.validators import assert_valid_news_item
        
        # Non deve sollevare eccezione
        assert_valid_news_item(mock_news_item)
    
    def test_assert_valid_news_item_fails(self, mock_news_item):
        """assert_valid_news_item deve sollevare AssertionError per item invalido."""
        from src.utils.validators import assert_valid_news_item
        
        mock_news_item['title'] = ""
        
        with pytest.raises(AssertionError) as exc_info:
            assert_valid_news_item(mock_news_item, "Test context")
        
        assert "Test context" in str(exc_info.value)
        assert "INVALID" in str(exc_info.value)


class TestLogCapture:
    """Test per la fixture log_capture."""
    
    def test_log_capture_contains(self, log_capture):
        """log_capture.contains deve trovare messaggi."""
        import logging
        
        logging.info("Test message for capture")
        
        assert log_capture.contains("Test message")
        assert log_capture.contains("test message")  # Case insensitive
        assert not log_capture.contains("nonexistent")
    
    def test_log_capture_level_filter(self, log_capture):
        """log_capture deve filtrare per livello."""
        import logging
        
        logging.info("Info message")
        logging.warning("Warning message")
        
        assert log_capture.contains("Info", level="INFO")
        assert not log_capture.contains("Info", level="WARNING")
        assert log_capture.contains("Warning", level="WARNING")
    
    def test_log_capture_pattern(self, log_capture):
        """log_capture.contains_pattern deve supportare regex."""
        import logging
        
        logging.info("Tavily fallback activated for match_123")
        
        assert log_capture.contains_pattern(r"Tavily.*fallback")
        assert log_capture.contains_pattern(r"match_\d+")
        assert not log_capture.contains_pattern(r"Perplexity.*fallback")
    
    def test_log_capture_assert_logged(self, log_capture):
        """assert_logged deve sollevare AssertionError se non trovato."""
        import logging
        
        logging.warning("Expected warning")
        
        # Non deve sollevare
        log_capture.assert_logged("Expected warning")
        
        # Deve sollevare
        with pytest.raises(AssertionError):
            log_capture.assert_logged("Nonexistent message")
    
    def test_log_capture_get_by_level(self, log_capture):
        """get_by_level deve restituire solo log del livello specificato."""
        import logging
        
        logging.info("Info 1")
        logging.info("Info 2")
        logging.warning("Warning 1")
        
        infos = log_capture.get_by_level("INFO")
        warnings = log_capture.get_by_level("WARNING")
        
        assert len(infos) == 2
        assert len(warnings) == 1


# Marker per esecuzione rapida
pytestmark = pytest.mark.unit
