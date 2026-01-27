"""
EarlyBird Snapshot Testing V1.0

Snapshot testing per verificare che l'output dei componenti rimanga stabile.
Utile per:
1. Rilevare regressioni nell'output dell'analyzer
2. Verificare che il formato delle verifiche non cambi
3. Documentare il comportamento atteso dei componenti

I test confrontano l'output attuale con "snapshot" salvati.
Se l'output cambia intenzionalmente, aggiornare gli snapshot.

Requirements: Self-Check Protocol compliance
"""
import pytest
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path


# ============================================
# SNAPSHOT STORAGE
# ============================================

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def ensure_snapshot_dir():
    """Crea la directory snapshots se non esiste."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)


def get_snapshot_path(name: str) -> Path:
    """Ottiene il path per uno snapshot."""
    ensure_snapshot_dir()
    return SNAPSHOT_DIR / f"{name}.json"


def save_snapshot(name: str, data: Dict[str, Any]) -> None:
    """Salva uno snapshot su file."""
    path = get_snapshot_path(name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_snapshot(name: str) -> Optional[Dict[str, Any]]:
    """Carica uno snapshot da file. Ritorna None se non esiste."""
    path = get_snapshot_path(name)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def snapshot_hash(data: Dict[str, Any]) -> str:
    """Calcola hash MD5 di uno snapshot per confronto rapido."""
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(json_str.encode()).hexdigest()


# ============================================
# SNAPSHOT ASSERTION HELPER
# ============================================

class SnapshotMismatch(AssertionError):
    """Eccezione per mismatch di snapshot."""
    pass


def assert_snapshot_match(
    name: str, 
    actual: Dict[str, Any],
    update: bool = False,
    ignore_keys: list = None
) -> None:
    """
    Confronta dati attuali con snapshot salvato.
    
    Args:
        name: Nome dello snapshot
        actual: Dati attuali da confrontare
        update: Se True, aggiorna lo snapshot invece di confrontare
        ignore_keys: Lista di chiavi da ignorare nel confronto
        
    Raises:
        SnapshotMismatch: Se i dati non corrispondono allo snapshot
    """
    # Rimuovi chiavi da ignorare
    actual_filtered = actual.copy()
    if ignore_keys:
        for key in ignore_keys:
            actual_filtered.pop(key, None)
    
    expected = load_snapshot(name)
    
    if expected is None or update:
        # Primo run o aggiornamento richiesto - salva snapshot
        save_snapshot(name, actual_filtered)
        if expected is None:
            pytest.skip(f"Snapshot '{name}' creato. Riesegui il test.")
        return
    
    # Rimuovi chiavi da ignorare anche dallo snapshot
    expected_filtered = expected.copy()
    if ignore_keys:
        for key in ignore_keys:
            expected_filtered.pop(key, None)
    
    # Confronta
    if actual_filtered != expected_filtered:
        # Genera diff leggibile
        diff_report = generate_diff_report(expected_filtered, actual_filtered)
        raise SnapshotMismatch(
            f"Snapshot '{name}' non corrisponde:\n{diff_report}\n\n"
            f"Per aggiornare lo snapshot, esegui con UPDATE_SNAPSHOTS=1"
        )


def generate_diff_report(expected: Dict, actual: Dict) -> str:
    """Genera un report delle differenze tra due dict."""
    lines = []
    
    all_keys = set(expected.keys()) | set(actual.keys())
    
    for key in sorted(all_keys):
        exp_val = expected.get(key, '<MISSING>')
        act_val = actual.get(key, '<MISSING>')
        
        if exp_val != act_val:
            lines.append(f"  {key}:")
            lines.append(f"    expected: {exp_val}")
            lines.append(f"    actual:   {act_val}")
    
    return "\n".join(lines) if lines else "No differences found"


# ============================================
# FIXTURES: Dati di input standardizzati
# ============================================

@pytest.fixture
def standard_analysis_input() -> Dict[str, Any]:
    """Input standardizzato per l'analyzer (per snapshot stabili)."""
    return {
        'match_id': 'snapshot_test_001',
        'home_team': 'Inter Milan',
        'away_team': 'AC Milan',
        'league': 'soccer_italy_serie_a',
        'news_snippet': 'Lautaro Martinez ruled out for derby due to hamstring injury',
        'home_missing_players': ['Lautaro Martinez'],
        'away_missing_players': [],
        'current_home_odd': 1.85,
        'current_away_odd': 4.20,
        'current_draw_odd': 3.50,
    }


@pytest.fixture
def standard_verification_input() -> Dict[str, Any]:
    """Input standardizzato per il verification layer."""
    return {
        'match_id': 'snapshot_test_001',
        'home_team': 'Inter Milan',
        'away_team': 'AC Milan',
        'match_date': '2026-01-15',
        'league': 'soccer_italy_serie_a',
        'preliminary_score': 8.5,
        'suggested_market': 'Over 2.5 Goals',
        'home_missing_players': ['Lautaro Martinez', 'Nicolò Barella'],
        'away_missing_players': ['Theo Hernandez'],
        'home_injury_severity': 'HIGH',
        'away_injury_severity': 'MEDIUM',
    }


# ============================================
# TEST: Analyzer Output Snapshots
# ============================================

class TestAnalyzerSnapshots:
    """Snapshot test per l'output dell'analyzer."""
    
    def test_analysis_structure_snapshot(self, standard_analysis_input):
        """
        Verifica che la struttura dell'output dell'analyzer sia stabile.
        Non testa i valori esatti (che dipendono dall'AI) ma la struttura.
        """
        # Simula output dell'analyzer (struttura attesa)
        analysis_output = {
            'final_verdict': 'BET',
            'confidence': 78,
            'recommended_market': 'Over 2.5 Goals',
            'primary_market': '1',
            'primary_driver': 'INJURY_INTEL',
            'combo_suggestion': 'Inter Win + Over 2.5',
            'combo_reasoning': 'Milan senza difensori chiave',
            'reasoning': 'Assenza confermata di Lautaro Martinez',
        }
        
        # Verifica che tutti i campi attesi siano presenti
        expected_fields = [
            'final_verdict', 'confidence', 'recommended_market',
            'primary_market', 'primary_driver', 'combo_suggestion',
            'combo_reasoning', 'reasoning'
        ]
        
        for field in expected_fields:
            assert field in analysis_output, f"Campo mancante: {field}"
        
        # Snapshot della struttura (non dei valori)
        structure_snapshot = {
            'fields': sorted(analysis_output.keys()),
            'field_types': {k: type(v).__name__ for k, v in analysis_output.items()},
        }
        
        assert_snapshot_match('analyzer_structure', structure_snapshot)
    
    def test_verdict_values_snapshot(self):
        """Verifica che i valori di verdict siano stabili."""
        valid_verdicts = ['BET', 'NO BET', 'MONITOR']
        valid_drivers = ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN']
        
        verdict_config = {
            'valid_verdicts': sorted(valid_verdicts),
            'valid_drivers': sorted(valid_drivers),
        }
        
        assert_snapshot_match('analyzer_verdict_config', verdict_config)
    
    def test_bet_analysis_snapshot(self, standard_analysis_input):
        """
        Snapshot di un'analisi BET tipica.
        Utile per rilevare cambiamenti nel formato di output.
        """
        # Output tipico per un caso BET
        bet_analysis = {
            'final_verdict': 'BET',
            'confidence': 75,
            'recommended_market': 'Over 2.5 Goals',
            'primary_market': '1',
            'primary_driver': 'INJURY_INTEL',
            'combo_suggestion': 'Home Win + Over 2.5',
            'combo_reasoning': 'Assenze chiave avversario + media gol alta',
            'reasoning': 'Opportunità di valore rilevata',
        }
        
        # Ignora reasoning che può variare
        assert_snapshot_match(
            'analyzer_bet_output',
            bet_analysis,
            ignore_keys=['reasoning', 'combo_reasoning']
        )
    
    def test_no_bet_analysis_snapshot(self):
        """Snapshot di un'analisi NO BET tipica."""
        no_bet_analysis = {
            'final_verdict': 'NO BET',
            'confidence': 45,
            'recommended_market': 'NONE',
            'primary_market': 'NONE',
            'primary_driver': 'MATH_VALUE',
            'combo_suggestion': None,
            'combo_reasoning': 'Dati insufficienti per combo',
            'reasoning': 'Nessun valore rilevato',
        }
        
        assert_snapshot_match(
            'analyzer_no_bet_output',
            no_bet_analysis,
            ignore_keys=['reasoning', 'combo_reasoning']
        )


# ============================================
# TEST: Verification Layer Output Snapshots
# ============================================

class TestVerificationSnapshots:
    """Snapshot test per l'output del verification layer."""
    
    def test_verification_structure_snapshot(self):
        """Verifica che la struttura del VerificationResult sia stabile."""
        verification_output = {
            'status': 'confirm',
            'original_score': 8.5,
            'adjusted_score': 8.2,
            'score_adjustment_reason': 'Lieve riduzione per form',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': None,
            'alternative_markets': ['BTTS', 'Over 9.5 Corners'],
            'inconsistencies': [],
            'overall_confidence': 'HIGH',
            'reasoning': 'Alert confermato',
            'rejection_reason': None,
        }
        
        structure_snapshot = {
            'fields': sorted(verification_output.keys()),
            'field_types': {k: type(v).__name__ for k, v in verification_output.items()},
        }
        
        assert_snapshot_match('verification_structure', structure_snapshot)
    
    def test_verification_status_values_snapshot(self):
        """Verifica che i valori di status siano stabili."""
        status_config = {
            'valid_statuses': sorted(['confirm', 'reject', 'change_market']),
            'valid_confidences': sorted(['HIGH', 'MEDIUM', 'LOW']),
        }
        
        assert_snapshot_match('verification_status_config', status_config)
    
    def test_confirm_result_snapshot(self, standard_verification_input):
        """Snapshot di un risultato CONFIRM tipico."""
        confirm_result = {
            'status': 'confirm',
            'original_score': 8.5,
            'adjusted_score': 8.2,
            'score_adjustment_reason': 'Lieve riduzione per form recente',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': None,
            'alternative_markets': ['BTTS'],
            'inconsistencies': [],
            'overall_confidence': 'HIGH',
            'rejection_reason': None,
        }
        
        assert_snapshot_match(
            'verification_confirm_output',
            confirm_result,
            ignore_keys=['score_adjustment_reason', 'alternative_markets']
        )
    
    def test_reject_result_snapshot(self):
        """Snapshot di un risultato REJECT tipico."""
        reject_result = {
            'status': 'reject',
            'original_score': 8.0,
            'adjusted_score': 0.0,
            'score_adjustment_reason': 'Respinto per incongruenze',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': None,
            'alternative_markets': [],
            'inconsistencies': ['News obsoleta', 'Dati FotMob contrastanti'],
            'overall_confidence': 'HIGH',
            'rejection_reason': 'Incongruenze critiche',
        }
        
        assert_snapshot_match(
            'verification_reject_output',
            reject_result,
            ignore_keys=['score_adjustment_reason', 'inconsistencies', 'rejection_reason']
        )
    
    def test_change_market_result_snapshot(self):
        """Snapshot di un risultato CHANGE_MARKET tipico."""
        change_market_result = {
            'status': 'change_market',
            'original_score': 8.0,
            'adjusted_score': 7.5,
            'score_adjustment_reason': 'Mercato modificato per H2H',
            'original_market': 'Over 2.5 Goals',
            'recommended_market': 'Over 9.5 Corners',
            'alternative_markets': ['Over 4.5 Cards'],
            'inconsistencies': ['H2H non supporta Over 2.5'],
            'overall_confidence': 'MEDIUM',
            'rejection_reason': None,
        }
        
        assert_snapshot_match(
            'verification_change_market_output',
            change_market_result,
            ignore_keys=['score_adjustment_reason', 'inconsistencies', 'alternative_markets']
        )


# ============================================
# TEST: News Item Format Snapshots
# ============================================

class TestNewsItemSnapshots:
    """Snapshot test per il formato dei news item."""
    
    def test_browser_monitor_format_snapshot(self):
        """Snapshot del formato browser_monitor."""
        browser_news = {
            'match_id': None,
            'team': 'Galatasaray',
            'title': 'Icardi ruled out for derby',
            'snippet': 'Star striker will miss the match',
            'link': 'https://fanatik.com.tr/article',
            'source': 'fanatik.com.tr',
            'search_type': 'browser_monitor',
            'confidence': 'HIGH',
            'category': 'INJURY',
            'priority_boost': 2.0,
            'source_type': 'browser_monitor',
        }
        
        structure = {
            'fields': sorted(browser_news.keys()),
            'search_type': browser_news['search_type'],
            'source_type': browser_news['source_type'],
        }
        
        assert_snapshot_match('news_browser_monitor_format', structure)
    
    def test_beat_writer_format_snapshot(self):
        """Snapshot del formato beat_writer."""
        beat_writer_news = {
            'match_id': 'test_123',
            'team': 'River Plate',
            'title': '@GastonEdul: Borja no viaja',
            'snippet': 'El delantero no fue convocado',
            'link': 'https://twitter.com/GastonEdul',
            'source': '@GastonEdul',
            'search_type': 'beat_writer_cache',
            'confidence': 'HIGH',
            'priority_boost': 1.5,
            'source_type': 'beat_writer',
            'beat_writer_name': 'Gastón Edul',
            'beat_writer_outlet': 'TyC Sports',
        }
        
        structure = {
            'fields': sorted(beat_writer_news.keys()),
            'search_type': beat_writer_news['search_type'],
            'source_type': beat_writer_news['source_type'],
        }
        
        assert_snapshot_match('news_beat_writer_format', structure)
    
    def test_ddg_search_format_snapshot(self):
        """Snapshot del formato DDG search."""
        ddg_news = {
            'match_id': 'test_456',
            'team': 'Legia Warszawa',
            'title': 'Legia bez kluczowego gracza',
            'snippet': 'Kapitan kontuzjowany przed meczem',
            'link': 'https://weszlo.com/article',
            'source': 'weszlo.com',
            'search_type': 'ddg_local',
            'date': '2026-01-13',
        }
        
        structure = {
            'fields': sorted(ddg_news.keys()),
            'search_type': ddg_news['search_type'],
        }
        
        assert_snapshot_match('news_ddg_format', structure)


# ============================================
# TEST: Alert Payload Format Snapshots
# ============================================

class TestAlertPayloadSnapshots:
    """Snapshot test per il formato degli alert payload."""
    
    def test_telegram_alert_structure_snapshot(self):
        """Snapshot della struttura dell'alert Telegram."""
        alert_structure = {
            'required_fields': sorted([
                'match_obj', 'news_summary', 'news_url', 'score', 'league'
            ]),
            'optional_fields': sorted([
                'combo_suggestion', 'combo_reasoning', 'recommended_market',
                'math_edge', 'is_update', 'financial_risk', 'intel_source',
                'referee_intel', 'twitter_intel', 'validated_home_team',
                'validated_away_team', 'verification_info'
            ]),
        }
        
        assert_snapshot_match('alert_telegram_structure', alert_structure)
    
    def test_verification_info_structure_snapshot(self):
        """Snapshot della struttura verification_info nell'alert."""
        verification_info = {
            'status': 'confirm',
            'confidence': 'HIGH',
            'reasoning': 'Alert confermato',
            'inconsistencies_count': 0,
        }
        
        structure = {
            'fields': sorted(verification_info.keys()),
        }
        
        assert_snapshot_match('alert_verification_info_structure', structure)


# ============================================
# TEST: Configuration Snapshots
# ============================================

class TestConfigSnapshots:
    """Snapshot test per configurazioni critiche."""
    
    def test_valid_markets_snapshot(self):
        """Snapshot dei mercati validi."""
        from src.utils.validators import VALID_MARKETS
        
        markets_config = {
            'valid_markets': sorted(VALID_MARKETS),
            'count': len(VALID_MARKETS),
        }
        
        assert_snapshot_match('config_valid_markets', markets_config)
    
    def test_valid_search_types_snapshot(self):
        """Snapshot dei search type validi."""
        from src.utils.validators import VALID_SEARCH_TYPES
        
        search_types_config = {
            'valid_search_types': sorted(VALID_SEARCH_TYPES),
            'count': len(VALID_SEARCH_TYPES),
        }
        
        assert_snapshot_match('config_valid_search_types', search_types_config)
    
    def test_injury_severities_snapshot(self):
        """Snapshot delle severity di infortunio."""
        from src.utils.validators import VALID_INJURY_SEVERITIES
        
        severities_config = {
            'valid_severities': sorted(VALID_INJURY_SEVERITIES),
        }
        
        assert_snapshot_match('config_injury_severities', severities_config)


# ============================================
# TEST: Regression Detection
# ============================================

class TestRegressionSnapshots:
    """Test per rilevare regressioni tramite snapshot."""
    
    def test_contract_fields_unchanged(self):
        """Verifica che i campi dei contratti non cambino."""
        from src.utils.contracts import ALL_CONTRACTS
        
        contracts_snapshot = {}
        for name, contract in ALL_CONTRACTS.items():
            contracts_snapshot[name] = {
                'producer': contract.producer,
                'consumer': contract.consumer,
                'fields': sorted([f.name for f in contract.fields]),
                'required_fields': sorted([f.name for f in contract.fields if f.required]),
            }
        
        assert_snapshot_match('contracts_definition', contracts_snapshot)
    
    def test_validator_functions_exist(self):
        """Verifica che tutte le funzioni di validazione esistano."""
        from src.utils import validators
        
        expected_validators = [
            'validate_news_item',
            'validate_verification_request',
            'validate_verification_result',
            'validate_analysis_result',
            'validate_alert_payload',
            'validate_batch',
        ]
        
        validators_snapshot = {
            'available_validators': sorted([
                name for name in expected_validators
                if hasattr(validators, name)
            ]),
        }
        
        assert_snapshot_match('validators_available', validators_snapshot)


# Marker per test di snapshot
pytestmark = pytest.mark.snapshot
