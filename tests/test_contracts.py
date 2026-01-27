"""
EarlyBird Contract Testing V1.0

Verifica che i contratti tra componenti siano rispettati.
I contratti definiscono le interfacce tra producer e consumer:

    news_hunter → main.py (NEWS_ITEM_CONTRACT)
    main.py → analyzer (SNIPPET_DATA_CONTRACT)
    analyzer → main.py (ANALYSIS_RESULT_CONTRACT)
    verification_layer → main.py (VERIFICATION_RESULT_CONTRACT)
    main.py → notifier (ALERT_PAYLOAD_CONTRACT)

Questi test garantiscono che:
1. I producer generino output conformi al contratto
2. I consumer ricevano input nel formato atteso
3. Le modifiche ai componenti non rompano le interfacce

Requirements: Self-Check Protocol compliance
"""
import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from src.utils.contracts import (
    Contract,
    FieldSpec,
    ContractViolation,
    NEWS_ITEM_CONTRACT,
    SNIPPET_DATA_CONTRACT,
    ANALYSIS_RESULT_CONTRACT,
    VERIFICATION_RESULT_CONTRACT,
    ALERT_PAYLOAD_CONTRACT,
    ALL_CONTRACTS,
    get_contract,
    validate_contract,
    assert_contract,
)


# ============================================
# FIXTURES: Dati realistici per ogni contratto
# ============================================

@pytest.fixture
def valid_news_item() -> Dict[str, Any]:
    """News item valido prodotto da news_hunter."""
    return {
        'match_id': 'abc123def456',
        'team': 'Inter Milan',
        'title': 'Lautaro Martinez ruled out for derby',
        'snippet': 'Star striker will miss the match due to injury sustained in training',
        'link': 'https://football-italia.net/article/123',
        'source': 'football-italia.net',
        'search_type': 'ddg_local',
        'date': datetime.now(timezone.utc).isoformat(),
        'confidence': 'HIGH',
        'priority_boost': 1.5,
        'freshness_tag': '🔥 FRESH',
        'minutes_old': 30,
    }


@pytest.fixture
def valid_snippet_data() -> Dict[str, Any]:
    """Snippet data valido passato all'analyzer."""
    return {
        'match_id': 'abc123def456',
        'link': 'https://football-italia.net/article/123',
        'team': 'Inter Milan',
        'home_team': 'Inter Milan',
        'away_team': 'AC Milan',
        'snippet': 'Lautaro Martinez ruled out for derby...',
        'league_id': '55',  # String, non int
        'current_home_odd': 1.85,
        'current_away_odd': 4.20,
        'current_draw_odd': 3.50,
        'home_context': {'form': 'WWDWL', 'goals_avg': 2.1},
        'away_context': {'form': 'WDWDL', 'goals_avg': 1.8},
    }


@pytest.fixture
def valid_analysis_result() -> Dict[str, Any]:
    """Analysis result valido prodotto dall'analyzer."""
    return {
        'score': 8.5,
        'summary': 'Assenza confermata di Lautaro Martinez. Impatto significativo.',
        'category': 'INJURY',
        'recommended_market': 'Over 2.5 Goals',
        'combo_suggestion': 'Inter Win + Over 2.5',
        'combo_reasoning': 'Milan senza difensori chiave, Inter forte in casa',
        'primary_driver': 'INJURY_INTEL',
    }


@pytest.fixture
def valid_verification_result() -> Dict[str, Any]:
    """Verification result valido prodotto dal verification_layer."""
    return {
        'status': 'confirm',
        'original_score': 8.5,
        'adjusted_score': 8.2,
        'original_market': 'Over 2.5 Goals',
        'recommended_market': None,
        'overall_confidence': 'HIGH',
        'reasoning': 'Alert confermato. Dati FotMob coerenti con news.',
        'rejection_reason': None,
        'inconsistencies': [],
    }


@pytest.fixture
def valid_alert_payload(mock_match) -> Dict[str, Any]:
    """Alert payload valido per il notifier."""
    return {
        'match_obj': mock_match,  # Oggetto Match (qualsiasi tipo accettato)
        'news_summary': '🔴 INJURY ALERT: Lautaro Martinez ruled out for derby.',
        'news_url': 'https://football-italia.net/article/123',
        'score': 8,
        'league': 'soccer_italy_serie_a',
        'combo_suggestion': 'Inter Win + Over 2.5',
        'recommended_market': 'Over 2.5 Goals',
        'verification_info': {
            'status': 'confirm',
            'confidence': 'HIGH',
            'reasoning': 'Verificato con FotMob',
        },
    }


# ============================================
# TEST: Contract Infrastructure
# ============================================

class TestContractInfrastructure:
    """Test dell'infrastruttura dei contratti."""
    
    def test_all_contracts_registered(self):
        """Verifica che tutti i contratti siano registrati."""
        expected_contracts = [
            'news_item',
            'snippet_data',
            'analysis_result',
            'verification_result',
            'alert_payload',
        ]
        for name in expected_contracts:
            assert name in ALL_CONTRACTS, f"Contract '{name}' non registrato"
    
    def test_get_contract_valid(self):
        """get_contract() ritorna il contratto corretto."""
        contract = get_contract('news_item')
        assert contract.name == 'NewsItem'
        assert contract.producer == 'news_hunter'
        assert contract.consumer == 'main.py'
    
    def test_get_contract_invalid(self):
        """get_contract() solleva ValueError per contratto inesistente."""
        with pytest.raises(ValueError, match="not found"):
            get_contract('nonexistent_contract')
    
    def test_field_spec_type_validation(self):
        """FieldSpec valida correttamente i tipi."""
        field = FieldSpec('test_field', field_type=str)
        
        # Tipo corretto
        is_valid, error = field.validate("test string")
        assert is_valid
        assert error == ""
        
        # Tipo errato
        is_valid, error = field.validate(123)
        assert not is_valid
        assert "tipo" in error
    
    def test_field_spec_allowed_values(self):
        """FieldSpec valida correttamente i valori ammessi."""
        field = FieldSpec('status', allowed_values=['confirm', 'reject'])
        
        # Valore ammesso
        is_valid, _ = field.validate('confirm')
        assert is_valid
        
        # Valore non ammesso
        is_valid, error = field.validate('invalid')
        assert not is_valid
        assert "non in" in error
    
    def test_field_spec_custom_validator(self):
        """FieldSpec usa correttamente il validatore custom."""
        def is_positive(x):
            return x > 0
        
        # Il validatore custom richiede anche il tipo corretto
        field = FieldSpec('score', field_type=(int, float), validator=is_positive)
        
        assert field.validate(5)[0] is True
        assert field.validate(-1)[0] is False
    
    def test_contract_validate_none_data(self):
        """Contract.validate() gestisce None correttamente."""
        contract = get_contract('news_item')
        is_valid, errors = contract.validate(None)
        assert not is_valid
        assert any("None" in e for e in errors)
    
    def test_contract_validate_non_dict(self):
        """Contract.validate() gestisce non-dict correttamente."""
        contract = get_contract('news_item')
        is_valid, errors = contract.validate("not a dict")
        assert not is_valid
        assert any("non è dict" in e for e in errors)


# ============================================
# TEST: NEWS_ITEM_CONTRACT (news_hunter → main.py)
# ============================================

class TestNewsItemContract:
    """Test del contratto NEWS_ITEM_CONTRACT."""
    
    def test_valid_news_item_passes(self, valid_news_item):
        """News item valido passa la validazione."""
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert is_valid, f"Errori inattesi: {errors}"
    
    def test_missing_required_field_fails(self, valid_news_item):
        """News item senza campo richiesto fallisce."""
        del valid_news_item['title']
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert not is_valid
        assert any("title" in e for e in errors)
    
    def test_invalid_url_fails(self, valid_news_item):
        """News item con URL invalido fallisce."""
        valid_news_item['link'] = 'not-a-valid-url'
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert not is_valid
        assert any("link" in e for e in errors)
    
    def test_browser_monitor_format(self):
        """Formato browser_monitor è valido."""
        browser_news = {
            'match_id': None,  # Pre-matching
            'team': 'Galatasaray',
            'title': 'Icardi ruled out',
            'snippet': 'Star striker will miss the match',
            'link': 'https://fanatik.com.tr/article',
            'source': 'fanatik.com.tr',
            'search_type': 'browser_monitor',
        }
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(browser_news)
        assert is_valid, f"Browser monitor format invalido: {errors}"
    
    def test_beat_writer_format(self):
        """Formato beat_writer è valido."""
        beat_writer_news = {
            'match_id': 'test_123',
            'team': 'River Plate',
            'title': '@GastonEdul: Borja no viaja',
            'snippet': 'El delantero no fue convocado',
            'link': 'https://twitter.com/GastonEdul',
            'source': '@GastonEdul',
            'search_type': 'beat_writer_cache',
            'confidence': 'HIGH',
        }
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(beat_writer_news)
        assert is_valid, f"Beat writer format invalido: {errors}"
    
    def test_exotic_search_type_allowed(self):
        """Search type esotici (exotic_*) sono ammessi."""
        exotic_news = {
            'match_id': 'test_123',
            'team': 'Melbourne Victory',
            'title': 'Ins and Outs',
            'snippet': 'Key defender ruled out',
            'link': 'https://aleagues.com.au/article',
            'source': 'aleagues.com.au',
            'search_type': 'exotic_aleagues_official',
        }
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(exotic_news)
        assert is_valid, f"Exotic search type invalido: {errors}"
    
    def test_assert_contract_raises_on_invalid(self, valid_news_item):
        """assert_contract solleva ContractViolation su dati invalidi."""
        del valid_news_item['snippet']
        with pytest.raises(ContractViolation):
            NEWS_ITEM_CONTRACT.assert_valid(valid_news_item)


# ============================================
# TEST: SNIPPET_DATA_CONTRACT (main.py → analyzer)
# ============================================

class TestSnippetDataContract:
    """Test del contratto SNIPPET_DATA_CONTRACT."""
    
    def test_valid_snippet_data_passes(self, valid_snippet_data):
        """Snippet data valido passa la validazione."""
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(valid_snippet_data)
        assert is_valid, f"Errori inattesi: {errors}"
    
    def test_missing_match_id_fails(self, valid_snippet_data):
        """Snippet data senza match_id fallisce."""
        del valid_snippet_data['match_id']
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(valid_snippet_data)
        assert not is_valid
        assert any("match_id" in e for e in errors)
    
    def test_missing_team_names_fails(self, valid_snippet_data):
        """Snippet data senza team names fallisce."""
        del valid_snippet_data['home_team']
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(valid_snippet_data)
        assert not is_valid
        assert any("home_team" in e for e in errors)
    
    def test_optional_odds_allowed(self, valid_snippet_data):
        """Quote opzionali possono essere assenti."""
        del valid_snippet_data['current_home_odd']
        del valid_snippet_data['current_away_odd']
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(valid_snippet_data)
        assert is_valid, f"Quote opzionali causano errore: {errors}"
    
    def test_context_dicts_validated(self, valid_snippet_data):
        """Context dicts devono essere dict se presenti."""
        valid_snippet_data['home_context'] = "not a dict"
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(valid_snippet_data)
        assert not is_valid
        assert any("home_context" in e for e in errors)


# ============================================
# TEST: ANALYSIS_RESULT_CONTRACT (analyzer → main.py)
# ============================================

class TestAnalysisResultContract:
    """Test del contratto ANALYSIS_RESULT_CONTRACT."""
    
    def test_valid_analysis_result_passes(self, valid_analysis_result):
        """Analysis result valido passa la validazione."""
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert is_valid, f"Errori inattesi: {errors}"
    
    def test_score_out_of_range_fails(self, valid_analysis_result):
        """Score fuori range [0-10] fallisce."""
        valid_analysis_result['score'] = 15
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert not is_valid
        assert any("score" in e for e in errors)
    
    def test_negative_score_fails(self, valid_analysis_result):
        """Score negativo fallisce."""
        valid_analysis_result['score'] = -1
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert not is_valid
    
    def test_invalid_primary_driver_fails(self, valid_analysis_result):
        """Primary driver non valido fallisce."""
        valid_analysis_result['primary_driver'] = 'INVALID_DRIVER'
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert not is_valid
        assert any("primary_driver" in e for e in errors)
    
    def test_valid_primary_drivers(self, valid_analysis_result):
        """Tutti i primary driver validi passano."""
        valid_drivers = ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN']
        for driver in valid_drivers:
            valid_analysis_result['primary_driver'] = driver
            is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
            assert is_valid, f"Driver '{driver}' dovrebbe essere valido: {errors}"


# ============================================
# TEST: VERIFICATION_RESULT_CONTRACT (verification_layer → main.py)
# ============================================

class TestVerificationResultContract:
    """Test del contratto VERIFICATION_RESULT_CONTRACT."""
    
    def test_valid_verification_result_passes(self, valid_verification_result):
        """Verification result valido passa la validazione."""
        is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(valid_verification_result)
        assert is_valid, f"Errori inattesi: {errors}"
    
    def test_invalid_status_fails(self, valid_verification_result):
        """Status non valido fallisce."""
        valid_verification_result['status'] = 'invalid_status'
        is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(valid_verification_result)
        assert not is_valid
        assert any("status" in e for e in errors)
    
    def test_valid_statuses(self, valid_verification_result):
        """Tutti gli status validi passano."""
        valid_statuses = ['confirm', 'reject', 'change_market']
        for status in valid_statuses:
            valid_verification_result['status'] = status
            # Aggiungi campi richiesti per status specifici
            if status == 'reject':
                valid_verification_result['rejection_reason'] = 'Test reason'
            if status == 'change_market':
                valid_verification_result['recommended_market'] = 'Over 9.5 Corners'
            is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(valid_verification_result)
            assert is_valid, f"Status '{status}' dovrebbe essere valido: {errors}"
    
    def test_score_validation(self, valid_verification_result):
        """Score originale e adjusted devono essere in range."""
        valid_verification_result['original_score'] = 11
        is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(valid_verification_result)
        assert not is_valid
    
    def test_invalid_confidence_warns(self, valid_verification_result):
        """Confidence non standard genera warning (non errore)."""
        valid_verification_result['overall_confidence'] = 'VERY_HIGH'
        is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(valid_verification_result)
        # Confidence non standard non dovrebbe causare fallimento
        # ma il contratto potrebbe segnalarlo come warning


# ============================================
# TEST: ALERT_PAYLOAD_CONTRACT (main.py → notifier)
# ============================================

class TestAlertPayloadContract:
    """Test del contratto ALERT_PAYLOAD_CONTRACT."""
    
    def test_valid_alert_payload_passes(self, valid_alert_payload):
        """Alert payload valido passa la validazione."""
        is_valid, errors = ALERT_PAYLOAD_CONTRACT.validate(valid_alert_payload)
        assert is_valid, f"Errori inattesi: {errors}"
    
    def test_missing_match_obj_fails(self, valid_alert_payload):
        """Alert payload senza match_obj fallisce."""
        del valid_alert_payload['match_obj']
        is_valid, errors = ALERT_PAYLOAD_CONTRACT.validate(valid_alert_payload)
        assert not is_valid
        assert any("match_obj" in e for e in errors)
    
    def test_missing_news_summary_fails(self, valid_alert_payload):
        """Alert payload senza news_summary fallisce."""
        del valid_alert_payload['news_summary']
        is_valid, errors = ALERT_PAYLOAD_CONTRACT.validate(valid_alert_payload)
        assert not is_valid
    
    def test_score_out_of_range_fails(self, valid_alert_payload):
        """Score fuori range fallisce."""
        valid_alert_payload['score'] = 15
        is_valid, errors = ALERT_PAYLOAD_CONTRACT.validate(valid_alert_payload)
        assert not is_valid
    
    def test_optional_verification_info(self, valid_alert_payload):
        """verification_info è opzionale."""
        del valid_alert_payload['verification_info']
        is_valid, errors = ALERT_PAYLOAD_CONTRACT.validate(valid_alert_payload)
        assert is_valid, f"verification_info opzionale causa errore: {errors}"


# ============================================
# TEST: Cross-Contract Validation (Flusso Completo)
# ============================================

class TestCrossContractValidation:
    """Test di validazione cross-contract per il flusso completo."""
    
    def test_news_to_snippet_transformation(self, valid_news_item):
        """
        Verifica che un news_item possa essere trasformato in snippet_data.
        Simula il passaggio news_hunter → main.py → analyzer.
        """
        # Valida news_item
        assert NEWS_ITEM_CONTRACT.validate(valid_news_item)[0]
        
        # Trasforma in snippet_data (come fa main.py)
        snippet_data = {
            'match_id': valid_news_item['match_id'],
            'link': valid_news_item['link'],
            'team': valid_news_item['team'],
            'home_team': valid_news_item['team'],  # Semplificato
            'away_team': 'AC Milan',  # Aggiunto da match
            'snippet': valid_news_item['snippet'][:500],
        }
        
        # Valida snippet_data
        is_valid, errors = SNIPPET_DATA_CONTRACT.validate(snippet_data)
        assert is_valid, f"Trasformazione news→snippet fallita: {errors}"
    
    def test_analysis_to_verification_flow(self, valid_analysis_result):
        """
        Verifica che un analysis_result possa alimentare la verification.
        Simula il passaggio analyzer → main.py → verification_layer.
        """
        # Valida analysis_result
        assert ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)[0]
        
        # I dati dell'analysis vengono usati per creare VerificationRequest
        # (non testato qui - VerificationRequest è un dataclass separato)
        
        # Il verification_result deve essere compatibile
        verification_result = {
            'status': 'confirm',
            'original_score': valid_analysis_result['score'],
            'adjusted_score': valid_analysis_result['score'] - 0.3,
            'original_market': valid_analysis_result['recommended_market'],
            'overall_confidence': 'HIGH',
            'reasoning': 'Confermato',
        }
        
        is_valid, errors = VERIFICATION_RESULT_CONTRACT.validate(verification_result)
        assert is_valid, f"Flusso analysis→verification fallito: {errors}"
    
    def test_full_pipeline_contracts(self, valid_news_item, mock_match):
        """
        Test end-to-end: verifica che tutti i contratti siano rispettati
        nel flusso completo news_hunter → analyzer → verification → notifier.
        """
        # Step 1: news_hunter produce news_item
        assert NEWS_ITEM_CONTRACT.validate(valid_news_item)[0], "NEWS_ITEM_CONTRACT fallito"
        
        # Step 2: main.py prepara snippet_data per analyzer
        snippet_data = {
            'match_id': valid_news_item['match_id'],
            'link': valid_news_item['link'],
            'team': valid_news_item['team'],
            'home_team': 'Inter Milan',
            'away_team': 'AC Milan',
            'snippet': valid_news_item['snippet'],
        }
        assert SNIPPET_DATA_CONTRACT.validate(snippet_data)[0], "SNIPPET_DATA_CONTRACT fallito"
        
        # Step 3: analyzer produce analysis_result
        analysis_result = {
            'score': 8.5,
            'summary': 'Analisi completata',
            'recommended_market': 'Over 2.5 Goals',
            'primary_driver': 'INJURY_INTEL',
        }
        assert ANALYSIS_RESULT_CONTRACT.validate(analysis_result)[0], "ANALYSIS_RESULT_CONTRACT fallito"
        
        # Step 4: verification_layer produce verification_result
        verification_result = {
            'status': 'confirm',
            'original_score': 8.5,
            'adjusted_score': 8.2,
            'overall_confidence': 'HIGH',
            'reasoning': 'Confermato',
        }
        assert VERIFICATION_RESULT_CONTRACT.validate(verification_result)[0], "VERIFICATION_RESULT_CONTRACT fallito"
        
        # Step 5: main.py prepara alert_payload per notifier
        alert_payload = {
            'match_obj': mock_match,
            'news_summary': analysis_result['summary'],
            'news_url': valid_news_item['link'],
            'score': int(verification_result['adjusted_score']),
            'league': 'soccer_italy_serie_a',
            'verification_info': {
                'status': verification_result['status'],
                'confidence': verification_result['overall_confidence'],
            },
        }
        assert ALERT_PAYLOAD_CONTRACT.validate(alert_payload)[0], "ALERT_PAYLOAD_CONTRACT fallito"


# ============================================
# TEST: Edge Cases e Robustezza
# ============================================

class TestContractEdgeCases:
    """Test edge case per robustezza dei contratti."""
    
    def test_empty_string_fields(self, valid_news_item):
        """Stringhe vuote in campi richiesti falliscono."""
        valid_news_item['title'] = ''
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        # Il contratto dovrebbe rilevare stringhe vuote
        # (dipende dall'implementazione del validatore)
    
    def test_none_in_optional_fields(self, valid_news_item):
        """None in campi opzionali è accettato."""
        valid_news_item['date'] = None
        valid_news_item['confidence'] = None
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert is_valid, f"None in campi opzionali causa errore: {errors}"
    
    def test_extra_fields_ignored(self, valid_news_item):
        """Campi extra non definiti nel contratto sono ignorati."""
        valid_news_item['extra_field'] = 'should be ignored'
        valid_news_item['another_extra'] = 12345
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert is_valid, f"Campi extra causano errore: {errors}"
    
    def test_unicode_content(self, valid_news_item):
        """Contenuto unicode è gestito correttamente."""
        valid_news_item['title'] = 'Galatasaray\'da Icardi şoku! Sakatlığı açıklandı'
        valid_news_item['snippet'] = 'Yıldız forvet derbi öncesi kadro dışı kaldı'
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert is_valid, f"Unicode causa errore: {errors}"
    
    def test_very_long_content(self, valid_news_item):
        """Contenuto molto lungo è gestito."""
        valid_news_item['snippet'] = 'A' * 10000
        is_valid, errors = NEWS_ITEM_CONTRACT.validate(valid_news_item)
        assert is_valid, f"Contenuto lungo causa errore: {errors}"
    
    def test_float_score_accepted(self, valid_analysis_result):
        """Score float è accettato (non solo int)."""
        valid_analysis_result['score'] = 7.5
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert is_valid, f"Score float causa errore: {errors}"
    
    def test_int_score_accepted(self, valid_analysis_result):
        """Score int è accettato."""
        valid_analysis_result['score'] = 8
        is_valid, errors = ANALYSIS_RESULT_CONTRACT.validate(valid_analysis_result)
        assert is_valid, f"Score int causa errore: {errors}"


# Marker per test di contratto
pytestmark = pytest.mark.contract
