"""
EarlyBird Component Contracts V1.0

Definisce i "contratti" tra componenti del sistema.
Un contratto specifica:
- Campi richiesti in input/output
- Tipi attesi
- Invarianti che devono essere rispettati

Usato per:
1. Contract Testing - verificare che producer e consumer rispettino il contratto
2. Runtime Validation - validare dati in produzione (opzionale)
3. Documentazione - specifica formale delle interfacce

Flusso dati EarlyBird:
    Browser Monitor ─┐
    Beat Writers ────┼─→ news_hunter ─→ main.py ─→ analyzer ─→ verification_layer ─→ notifier
    DDG/Serper ──────┘                    │                           │
                                          └─── snippet_data ──────────┘

Requirements: Self-Check Protocol compliance
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Callable
from enum import Enum


class ContractViolation(Exception):
    """Raised when a contract is violated."""
    pass


@dataclass
class FieldSpec:
    """Specification for a single field in a contract."""
    name: str
    required: bool = True
    field_type: type = str
    allowed_values: Optional[List[Any]] = None
    validator: Optional[Callable[[Any], bool]] = None
    description: str = ""
    
    def validate(self, value: Any) -> tuple:
        """
        Validate a value against this field spec.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check type
        if value is not None and not isinstance(value, self.field_type):
            # Allow int for float fields
            if self.field_type == float and isinstance(value, int):
                pass
            else:
                return False, f"{self.name}: tipo {type(value).__name__}, atteso {self.field_type.__name__}"
        
        # Check allowed values
        if self.allowed_values is not None and value not in self.allowed_values:
            return False, f"{self.name}: '{value}' non in {self.allowed_values}"
        
        # Custom validator
        if self.validator is not None and value is not None:
            if not self.validator(value):
                return False, f"{self.name}: validazione custom fallita"
        
        return True, ""


@dataclass
class Contract:
    """
    Contract between two components.
    
    Defines what fields must be present and their constraints.
    """
    name: str
    producer: str  # Component that produces the data
    consumer: str  # Component that consumes the data
    fields: List[FieldSpec] = field(default_factory=list)
    description: str = ""
    
    def validate(self, data: Dict[str, Any]) -> tuple:
        """
        Validate data against this contract.
        
        Returns:
            Tuple of (is_valid, errors: List[str])
        """
        if data is None:
            return False, [f"Contract '{self.name}': data è None"]
        
        if not isinstance(data, dict):
            return False, [f"Contract '{self.name}': data non è dict"]
        
        errors = []
        
        for field_spec in self.fields:
            # Check required fields
            if field_spec.required and field_spec.name not in data:
                errors.append(f"Campo richiesto mancante: {field_spec.name}")
                continue
            
            # Skip validation if field not present and not required
            if field_spec.name not in data:
                continue
            
            value = data[field_spec.name]
            
            # None is allowed for non-required fields
            if value is None and not field_spec.required:
                continue
            
            # Validate field
            is_valid, error = field_spec.validate(value)
            if not is_valid:
                errors.append(error)
        
        return len(errors) == 0, errors
    
    def assert_valid(self, data: Dict[str, Any], context: str = "") -> None:
        """
        Assert that data is valid. Raises ContractViolation if not.
        """
        is_valid, errors = self.validate(data)
        if not is_valid:
            ctx = f" ({context})" if context else ""
            raise ContractViolation(
                f"Contract '{self.name}'{ctx} violated:\n" + 
                "\n".join(f"  - {e}" for e in errors)
            )


# ============================================
# CONTRACT: news_hunter → main.py (news_item)
# ============================================

def _is_valid_url(url: str) -> bool:
    """Validate URL format."""
    if not url:
        return True  # Empty is allowed
    return url.startswith('http://') or url.startswith('https://')


NEWS_ITEM_CONTRACT = Contract(
    name="NewsItem",
    producer="news_hunter",
    consumer="main.py",
    description="Output di run_hunter_for_match(), input per aggregazione dossier",
    fields=[
        FieldSpec("match_id", required=False, field_type=str, 
                  description="ID match, può essere None per browser_monitor pre-matching"),
        FieldSpec("team", required=True, field_type=str,
                  description="Nome team a cui si riferisce la news"),
        FieldSpec("title", required=True, field_type=str,
                  description="Titolo della news"),
        FieldSpec("snippet", required=True, field_type=str,
                  description="Contenuto/riassunto della news"),
        FieldSpec("link", required=True, field_type=str, validator=_is_valid_url,
                  description="URL della fonte"),
        FieldSpec("source", required=True, field_type=str,
                  description="Nome della fonte (es. 'fanatik.com.tr')"),
        FieldSpec("search_type", required=True, field_type=str,
                  description="Tipo di ricerca (es. 'browser_monitor', 'ddg_local')"),
        FieldSpec("date", required=False, field_type=str,
                  description="Data della news (ISO format)"),
        FieldSpec("confidence", required=False,
                  description="Livello confidenza: 'HIGH', 'MEDIUM', 'LOW' o float 0-1"),
        FieldSpec("priority_boost", required=False, field_type=(int, float),
                  description="Boost priorità per sorting"),
        FieldSpec("freshness_tag", required=False, field_type=str,
                  description="Tag freschezza: '🔥 FRESH', '⏰ AGING', '📜 STALE'"),
        FieldSpec("minutes_old", required=False, field_type=(int, float),
                  description="Età della news in minuti"),
    ]
)


# ============================================
# CONTRACT: main.py → analyzer (snippet_data)
# ============================================

SNIPPET_DATA_CONTRACT = Contract(
    name="SnippetData",
    producer="main.py",
    consumer="analyzer",
    description="Metadata passato ad analyze_with_triangulation()",
    fields=[
        FieldSpec("match_id", required=True, field_type=str,
                  description="ID univoco del match"),
        FieldSpec("link", required=False, field_type=str, validator=_is_valid_url,
                  description="URL primario della news"),
        FieldSpec("team", required=True, field_type=str,
                  description="Team principale (solitamente home)"),
        FieldSpec("home_team", required=True, field_type=str,
                  description="Nome team casa"),
        FieldSpec("away_team", required=True, field_type=str,
                  description="Nome team trasferta"),
        FieldSpec("snippet", required=False, field_type=str,
                  description="Snippet troncato per DB"),
        FieldSpec("league_id", required=False, field_type=(int, str),
                  description="ID lega FotMob"),
        FieldSpec("current_home_odd", required=False, field_type=(int, float),
                  description="Quota attuale home"),
        FieldSpec("current_away_odd", required=False, field_type=(int, float),
                  description="Quota attuale away"),
        FieldSpec("current_draw_odd", required=False, field_type=(int, float),
                  description="Quota attuale draw"),
        FieldSpec("home_context", required=False, field_type=dict,
                  description="Contesto FotMob home team"),
        FieldSpec("away_context", required=False, field_type=dict,
                  description="Contesto FotMob away team"),
    ]
)


# ============================================
# CONTRACT: analyzer → main.py (NewsLog)
# ============================================

VALID_VERDICTS = ['BET', 'NO BET', 'MONITOR']
VALID_DRIVERS = ['INJURY_INTEL', 'SHARP_MONEY', 'MATH_VALUE', 'CONTEXT_PLAY', 'CONTRARIAN']


def _is_valid_score(score: Any) -> bool:
    """Validate score is in range 0-10."""
    if score is None:
        return True
    try:
        return 0 <= float(score) <= 10
    except (TypeError, ValueError):
        return False


ANALYSIS_RESULT_CONTRACT = Contract(
    name="AnalysisResult",
    producer="analyzer",
    consumer="main.py",
    description="Output di analyze_with_triangulation() (attributi NewsLog)",
    fields=[
        FieldSpec("score", required=True, field_type=(int, float), validator=_is_valid_score,
                  description="Score 0-10"),
        FieldSpec("summary", required=True, field_type=str,
                  description="Riassunto analisi"),
        FieldSpec("category", required=False, field_type=str,
                  description="Categoria: INJURY, TURNOVER, etc."),
        FieldSpec("recommended_market", required=False, field_type=str,
                  description="Mercato consigliato"),
        FieldSpec("combo_suggestion", required=False, field_type=str,
                  description="Suggerimento combo"),
        FieldSpec("combo_reasoning", required=False, field_type=str,
                  description="Motivazione combo"),
        FieldSpec("primary_driver", required=False, field_type=str,
                  allowed_values=VALID_DRIVERS + [None],
                  description="Driver principale della scommessa"),
    ]
)


# ============================================
# CONTRACT: verification_layer → main.py
# ============================================

VALID_STATUSES = ['confirm', 'reject', 'change_market']
VALID_CONFIDENCES = ['HIGH', 'MEDIUM', 'LOW']


VERIFICATION_RESULT_CONTRACT = Contract(
    name="VerificationResult",
    producer="verification_layer",
    consumer="main.py",
    description="Output di verify_alert()",
    fields=[
        FieldSpec("status", required=True, field_type=str,
                  allowed_values=VALID_STATUSES,
                  description="Esito verifica"),
        FieldSpec("original_score", required=True, field_type=(int, float),
                  validator=_is_valid_score,
                  description="Score originale"),
        FieldSpec("adjusted_score", required=True, field_type=(int, float),
                  validator=_is_valid_score,
                  description="Score aggiustato"),
        FieldSpec("original_market", required=False, field_type=str,
                  description="Mercato originale"),
        FieldSpec("recommended_market", required=False, field_type=str,
                  description="Mercato consigliato (se change_market)"),
        FieldSpec("overall_confidence", required=False, field_type=str,
                  allowed_values=VALID_CONFIDENCES + [None],
                  description="Confidenza verifica"),
        FieldSpec("reasoning", required=False, field_type=str,
                  description="Motivazione in italiano"),
        FieldSpec("rejection_reason", required=False, field_type=str,
                  description="Motivo rifiuto (se reject)"),
        FieldSpec("inconsistencies", required=False, field_type=list,
                  description="Lista incongruenze rilevate"),
    ]
)


# ============================================
# CONTRACT: main.py → notifier (alert_payload)
# ============================================

ALERT_PAYLOAD_CONTRACT = Contract(
    name="AlertPayload",
    producer="main.py",
    consumer="notifier",
    description="Parametri per send_alert()",
    fields=[
        FieldSpec("match_obj", required=True, field_type=object,
                  description="Oggetto Match dal database"),
        FieldSpec("news_summary", required=True, field_type=str,
                  description="Riassunto news"),
        FieldSpec("news_url", required=True, field_type=str,
                  description="URL fonte"),
        FieldSpec("score", required=True, field_type=(int, float),
                  validator=_is_valid_score,
                  description="Score 0-10"),
        FieldSpec("league", required=True, field_type=str,
                  description="Chiave lega"),
        FieldSpec("combo_suggestion", required=False, field_type=str,
                  description="Suggerimento combo"),
        FieldSpec("recommended_market", required=False, field_type=str,
                  description="Mercato consigliato"),
        FieldSpec("verification_info", required=False, field_type=dict,
                  description="Info verifica V7.0"),
        FieldSpec("is_convergent", required=False, field_type=bool,
                  description="V9.5: True se segnale confermato da Web e Social"),
        FieldSpec("convergence_sources", required=False, field_type=dict,
                  description="V9.5: Dettagli fonti convergenti (web/social)"),
    ]
)


# ============================================
# CONTRACT REGISTRY
# ============================================

ALL_CONTRACTS = {
    'news_item': NEWS_ITEM_CONTRACT,
    'snippet_data': SNIPPET_DATA_CONTRACT,
    'analysis_result': ANALYSIS_RESULT_CONTRACT,
    'verification_result': VERIFICATION_RESULT_CONTRACT,
    'alert_payload': ALERT_PAYLOAD_CONTRACT,
}


def get_contract(name: str) -> Contract:
    """Get a contract by name."""
    if name not in ALL_CONTRACTS:
        raise ValueError(f"Contract '{name}' not found. Available: {list(ALL_CONTRACTS.keys())}")
    return ALL_CONTRACTS[name]


def validate_contract(name: str, data: Dict[str, Any]) -> tuple:
    """
    Validate data against a named contract.
    
    Returns:
        Tuple of (is_valid, errors)
    """
    contract = get_contract(name)
    return contract.validate(data)


def assert_contract(name: str, data: Dict[str, Any], context: str = "") -> None:
    """
    Assert data is valid against a named contract.
    Raises ContractViolation if not.
    """
    contract = get_contract(name)
    contract.assert_valid(data, context)
