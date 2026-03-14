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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Import settings for contract validation control
try:
    from config.settings import CONTRACT_VALIDATION_ENABLED
except ImportError:
    # Fallback if settings module not available (e.g., during testing)
    CONTRACT_VALIDATION_ENABLED = True


class ContractViolation(Exception):
    """Raised when a contract is violated."""

    pass


@dataclass
class FieldSpec:
    """
    Specification for a single field in a contract.

    Attributes:
        name: Field name (required)
        required: Whether the field is required (default: True)
        field_type: Expected type (default: str). Can be a single type or tuple of types (e.g., (int, float))
        allowed_values: List of allowed values (optional)
        validator: Custom validation function (optional). Must accept value and return bool.
        description: Field description (default: empty string)

    Example:
        FieldSpec("score", required=True, field_type=(int, float), validator=lambda x: 0 <= x <= 10)
    """

    name: str
    required: bool = True
    field_type: type = str
    allowed_values: list[Any] | None = None
    validator: Callable[[Any], bool] | None = None
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
                # Format field_type for error message
                if isinstance(self.field_type, tuple):
                    type_str = ", ".join(t.__name__ for t in self.field_type)
                else:
                    type_str = self.field_type.__name__

                return (
                    False,
                    f"{self.name}: type mismatch - got {type(value).__name__}, expected {type_str}",
                )

        # Check allowed values (None is always allowed for non-required fields)
        if (
            self.allowed_values is not None
            and value is not None
            and value not in self.allowed_values
        ):
            return (
                False,
                f"{self.name}: value '{value}' not in allowed values {self.allowed_values}",
            )

        # Custom validator with exception handling
        if self.validator is not None and value is not None:
            try:
                if not self.validator(value):
                    return False, f"{self.name}: custom validation failed for value '{value}'"
            except Exception as e:
                return (
                    False,
                    f"{self.name}: custom validation error: {type(e).__name__}: {str(e)}",
                )

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
    fields: list[FieldSpec] = field(default_factory=list)
    description: str = ""

    def validate(self, data: dict[str, Any]) -> tuple:
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

    def assert_valid(self, data: dict[str, Any], context: str = "") -> None:
        """
        Assert that data is valid. Raises ContractViolation if not.

        V14.0 FIX: Refined performance optimization - Skip only expensive operations when disabled
        When CONTRACT_VALIDATION_ENABLED is False:
        - Skip field validation (expensive)
        - Skip logging (expensive)
        - Still check for None data and non-dict data (cheap, prevents crashes)
        """
        # V14.0 FIX: Cheap checks always run (prevent crashes)
        if data is None:
            raise ContractViolation(f"Contract '{self.name}': data is None")

        if not isinstance(data, dict):
            raise ContractViolation(f"Contract '{self.name}': data is not a dict")

        # V14.0 FIX: Skip expensive validation when disabled
        if not CONTRACT_VALIDATION_ENABLED:
            return

        is_valid, errors = self.validate(data)
        if not is_valid:
            ctx = f" ({context})" if context else ""
            raise ContractViolation(
                f"Contract '{self.name}'{ctx} violated:\n" + "\n".join(f"  - {e}" for e in errors)
            )


# ============================================
# CONTRACT: news_hunter → main.py (news_item)
# ============================================


def _is_valid_url(url: str) -> bool:
    """Validate URL format."""
    if not url:
        return True  # Empty is allowed
    return url.startswith("http://") or url.startswith("https://")


NEWS_ITEM_CONTRACT = Contract(
    name="NewsItem",
    producer="news_hunter",
    consumer="main.py",
    description="Output di run_hunter_for_match(), input per aggregazione dossier",
    fields=[
        FieldSpec(
            "match_id",
            required=False,
            field_type=str,
            description="ID match, può essere None per browser_monitor pre-matching",
        ),
        FieldSpec(
            "team",
            required=True,
            field_type=str,
            description="Nome team a cui si riferisce la news",
        ),
        FieldSpec("title", required=True, field_type=str, description="Titolo della news"),
        FieldSpec(
            "snippet", required=True, field_type=str, description="Contenuto/riassunto della news"
        ),
        FieldSpec(
            "link",
            required=True,
            field_type=str,
            validator=_is_valid_url,
            description="URL della fonte",
        ),
        FieldSpec(
            "source",
            required=True,
            field_type=str,
            description="Nome della fonte (es. 'fanatik.com.tr')",
        ),
        FieldSpec(
            "search_type",
            required=True,
            field_type=str,
            description="Tipo di ricerca (es. 'browser_monitor', 'ddg_local')",
        ),
        FieldSpec(
            "date", required=False, field_type=str, description="Data della news (ISO format)"
        ),
        FieldSpec(
            "confidence",
            required=False,
            description="Livello confidenza: 'HIGH', 'MEDIUM', 'LOW' o float 0-1",
        ),
        FieldSpec(
            "priority_boost",
            required=False,
            field_type=(int, float),
            description="Boost priorità per sorting",
        ),
        FieldSpec(
            "freshness_tag",
            required=False,
            field_type=str,
            description="Tag freschezza: '🔥 FRESH', '⏰ AGING', '📜 STALE'",
        ),
        FieldSpec(
            "minutes_old",
            required=False,
            field_type=(int, float),
            description="Età della news in minuti",
        ),
        # V14.0 FIX: Added missing fields used by news_hunter
        FieldSpec(
            "keyword",
            required=False,
            field_type=str,
            description="Keyword usato per la ricerca (es. 'browser_monitor', 'beat_writer_priority')",
        ),
        FieldSpec(
            "category",
            required=False,
            field_type=str,
            description="Categoria della news (es. 'INJURY', 'SUSPENSION')",
        ),
        FieldSpec(
            "source_type",
            required=False,
            field_type=str,
            description="Tipo di fonte (es. 'beat_writer', 'twitter_intel', 'browser_monitor')",
        ),
        FieldSpec(
            "league_key",
            required=False,
            field_type=str,
            description="API league key (es. 'soccer_turkey_super_league')",
        ),
        FieldSpec(
            "gemini_confidence",
            required=False,
            field_type=(int, float),
            description="Confidenza Gemini (0-1) per Browser Monitor",
        ),
        FieldSpec(
            "discovered_at",
            required=False,
            field_type=str,
            description="Timestamp di scoperta (ISO format)",
        ),
        FieldSpec(
            "topics",
            required=False,
            field_type=list,
            description="Lista di topic rilevati (es. ['injury', 'lineup'])",
        ),
        # Beat writer metadata (optional)
        FieldSpec(
            "beat_writer_name",
            required=False,
            field_type=str,
            description="Nome del beat writer",
        ),
        FieldSpec(
            "beat_writer_outlet",
            required=False,
            field_type=str,
            description="Outlet del beat writer",
        ),
        FieldSpec(
            "beat_writer_specialty",
            required=False,
            field_type=str,
            description="Specialità del beat writer",
        ),
        FieldSpec(
            "beat_writer_reliability",
            required=False,
            field_type=(int, float),
            description="Affidabilità del beat writer (0-1)",
        ),
        FieldSpec(
            "avg_lead_time_min",
            required=False,
            field_type=(int, float),
            description="Tempo medio di anticipo rispetto ai media mainstream (minuti)",
        ),
    ],
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
        FieldSpec("match_id", required=True, field_type=str, description="ID univoco del match"),
        FieldSpec(
            "link",
            required=False,
            field_type=str,
            validator=_is_valid_url,
            description="URL primario della news",
        ),
        FieldSpec(
            "team", required=True, field_type=str, description="Team principale (solitamente home)"
        ),
        FieldSpec("home_team", required=True, field_type=str, description="Nome team casa"),
        FieldSpec("away_team", required=True, field_type=str, description="Nome team trasferta"),
        FieldSpec("snippet", required=False, field_type=str, description="Snippet troncato per DB"),
        FieldSpec("league_id", required=False, field_type=(int, str), description="ID lega FotMob"),
        FieldSpec(
            "current_home_odd",
            required=False,
            field_type=(int, float),
            description="Quota attuale home",
        ),
        FieldSpec(
            "current_away_odd",
            required=False,
            field_type=(int, float),
            description="Quota attuale away",
        ),
        FieldSpec(
            "current_draw_odd",
            required=False,
            field_type=(int, float),
            description="Quota attuale draw",
        ),
        FieldSpec(
            "home_context", required=False, field_type=dict, description="Contesto FotMob home team"
        ),
        FieldSpec(
            "away_context", required=False, field_type=dict, description="Contesto FotMob away team"
        ),
    ],
)


# ============================================
# CONTRACT: analyzer → main.py (NewsLog)
# ============================================

VALID_VERDICTS = ["BET", "NO BET", "MONITOR"]
VALID_DRIVERS = ["INJURY_INTEL", "SHARP_MONEY", "MATH_VALUE", "CONTEXT_PLAY", "CONTRARIAN"]


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
        FieldSpec(
            "score",
            required=True,
            field_type=(int, float),
            validator=_is_valid_score,
            description="Score 0-10",
        ),
        FieldSpec("summary", required=True, field_type=str, description="Riassunto analisi"),
        FieldSpec(
            "category",
            required=False,
            field_type=str,
            description="Categoria: INJURY, TURNOVER, etc.",
        ),
        FieldSpec(
            "recommended_market", required=False, field_type=str, description="Mercato consigliato"
        ),
        FieldSpec(
            "combo_suggestion", required=False, field_type=str, description="Suggerimento combo"
        ),
        FieldSpec(
            "combo_reasoning", required=False, field_type=str, description="Motivazione combo"
        ),
        FieldSpec(
            "primary_driver",
            required=False,
            field_type=str,
            allowed_values=VALID_DRIVERS + [None],
            description="Driver principale della scommessa",
        ),
        # V14.0 FIX: Added missing fields used by analyzer
        FieldSpec(
            "match_id",
            required=False,
            field_type=str,
            description="ID del match",
        ),
        FieldSpec(
            "url",
            required=False,
            field_type=str,
            validator=_is_valid_url,
            description="URL della fonte della news",
        ),
        FieldSpec(
            "affected_team",
            required=False,
            field_type=str,
            description="Team interessato dalla news",
        ),
        FieldSpec(
            "confidence",
            required=False,
            field_type=(int, float),
            description="Confidenza AI (0-100) per BettingQuant",
        ),
        FieldSpec(
            "odds_taken",
            required=False,
            field_type=(int, float),
            description="Quota presa per CLV tracking",
        ),
        FieldSpec(
            "confidence_breakdown",
            required=False,
            field_type=str,
            description="Breakdown della confidenza (stringa JSON)",
        ),
        FieldSpec(
            "is_convergent",
            required=False,
            field_type=bool,
            description="V9.5: True se segnale confermato da Web e Social",
        ),
        FieldSpec(
            "convergence_sources",
            required=False,
            field_type=str,
            description="V9.5: Dettagli fonti convergenti (stringa JSON)",
        ),
    ],
)


# ============================================
# CONTRACT: content_analyzer → news_radar (News Radar AnalysisResult)
# ============================================

VALID_CATEGORIES = [
    "INJURY",
    "SUSPENSION",
    "NATIONAL_TEAM",
    "CUP_ABSENCE",
    "YOUTH_CALLUP",
    "OTHER",
]
VALID_BETTING_IMPACTS = ["HIGH", "MEDIUM", "LOW", "CRITICAL"]


def _is_valid_confidence(confidence: Any) -> bool:
    """Validate confidence is in range 0.0-1.0."""
    if confidence is None:
        return True
    try:
        return 0.0 <= float(confidence) <= 1.0
    except (TypeError, ValueError):
        return False


NEWS_RADAR_ANALYSIS_RESULT_CONTRACT = Contract(
    name="NewsRadarAnalysisResult",
    producer="content_analyzer",
    consumer="news_radar",
    description="Output di RelevanceAnalyzer.analyze() e DeepSeekAnalyzer._parse_response() (COVE FIX 2026-03-07)",
    fields=[
        FieldSpec(
            "is_relevant",
            required=True,
            field_type=bool,
            description="True se il contenuto è rilevante per le scommesse",
        ),
        FieldSpec(
            "category",
            required=True,
            field_type=str,
            allowed_values=VALID_CATEGORIES,
            description="Categoria: INJURY, SUSPENSION, NATIONAL_TEAM, CUP_ABSENCE, YOUTH_CALLUP, OTHER",
        ),
        FieldSpec(
            "affected_team",
            required=False,
            field_type=str,
            description="Nome della squadra interessata (può essere None)",
        ),
        FieldSpec(
            "confidence",
            required=True,
            field_type=(int, float),
            validator=_is_valid_confidence,
            description="Confidenza 0.0-1.0",
        ),
        FieldSpec(
            "summary",
            required=True,
            field_type=str,
            description="Breve riassunto del contenuto",
        ),
        FieldSpec(
            "betting_impact",
            required=False,
            field_type=str,
            allowed_values=VALID_BETTING_IMPACTS + [None],
            description="V1.4: HIGH, MEDIUM, LOW, CRITICAL (opzionale, da DeepSeek)",
        ),
    ],
)


# ============================================
# CONTRACT: verification_layer → main.py
# ============================================

VALID_STATUSES = ["confirm", "reject", "change_market"]
VALID_CONFIDENCES = ["HIGH", "MEDIUM", "LOW"]


VERIFICATION_RESULT_CONTRACT = Contract(
    name="VerificationResult",
    producer="verification_layer",
    consumer="main.py",
    description="Output di verify_alert()",
    fields=[
        FieldSpec(
            "status",
            required=True,
            field_type=str,
            allowed_values=VALID_STATUSES,
            description="Esito verifica",
        ),
        FieldSpec(
            "original_score",
            required=True,
            field_type=(int, float),
            validator=_is_valid_score,
            description="Score originale",
        ),
        FieldSpec(
            "adjusted_score",
            required=True,
            field_type=(int, float),
            validator=_is_valid_score,
            description="Score aggiustato",
        ),
        FieldSpec(
            "original_market", required=False, field_type=str, description="Mercato originale"
        ),
        FieldSpec(
            "recommended_market",
            required=False,
            field_type=str,
            description="Mercato consigliato (se change_market)",
        ),
        FieldSpec(
            "overall_confidence",
            required=False,
            field_type=str,
            allowed_values=VALID_CONFIDENCES + [None],
            description="Confidenza verifica",
        ),
        FieldSpec(
            "reasoning", required=False, field_type=str, description="Motivazione in italiano"
        ),
        FieldSpec(
            "rejection_reason",
            required=False,
            field_type=str,
            description="Motivo rifiuto (se reject)",
        ),
        FieldSpec(
            "inconsistencies",
            required=False,
            field_type=list,
            description="Lista incongruenze rilevate",
        ),
        # V14.0 FIX: Added missing fields from VerificationResult.to_dict()
        FieldSpec(
            "score_adjustment_reason",
            required=False,
            field_type=str,
            description="Motivazione dell'aggiustamento dello score",
        ),
        FieldSpec(
            "alternative_markets",
            required=False,
            field_type=list,
            description="Lista di mercati alternativi suggeriti",
        ),
        # V14.0 FIX: Added verified_data field (complex nested structure)
        FieldSpec(
            "verified_data",
            required=False,
            field_type=dict,
            description="VerifiedData object con statistiche verificate (form, H2H, referee, etc.)",
        ),
    ],
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
        FieldSpec(
            "match_obj", required=True, field_type=object, description="Oggetto Match dal database"
        ),
        FieldSpec("news_summary", required=True, field_type=str, description="Riassunto news"),
        FieldSpec("news_url", required=True, field_type=str, description="URL fonte"),
        FieldSpec(
            "score",
            required=True,
            field_type=(int, float),
            validator=_is_valid_score,
            description="Score 0-10",
        ),
        FieldSpec("league", required=True, field_type=str, description="Chiave lega"),
        FieldSpec(
            "combo_suggestion", required=False, field_type=str, description="Suggerimento combo"
        ),
        FieldSpec(
            "recommended_market", required=False, field_type=str, description="Mercato consigliato"
        ),
        FieldSpec(
            "verification_info", required=False, field_type=dict, description="Info verifica V7.0"
        ),
        FieldSpec(
            "is_convergent",
            required=False,
            field_type=bool,
            description="V9.5: True se segnale confermato da Web e Social",
        ),
        FieldSpec(
            "convergence_sources",
            required=False,
            field_type=dict,
            description="V9.5: Dettagli fonti convergenti (web/social)",
        ),
        # V14.0 FIX: Added missing fields from notifier.send_alert()
        FieldSpec(
            "math_edge",
            required=False,
            field_type=dict,
            description="Dict con 'market', 'edge', 'kelly_stake' dal Poisson model",
        ),
        FieldSpec(
            "is_update",
            required=False,
            field_type=bool,
            description="True se questo è un aggiornamento a un alert precedente",
        ),
        FieldSpec(
            "financial_risk",
            required=False,
            field_type=str,
            description="Livello rischio finanziario da Financial Intelligence",
        ),
        FieldSpec(
            "intel_source",
            required=False,
            field_type=str,
            description="Sorgente intelligence - 'web', 'telegram', 'ocr'",
        ),
        FieldSpec(
            "referee_intel",
            required=False,
            field_type=dict,
            description="Dict con statistiche arbitro per mercato cards",
        ),
        FieldSpec(
            "twitter_intel",
            required=False,
            field_type=dict,
            description="Dict con Twitter insider intel",
        ),
        FieldSpec(
            "validated_home_team",
            required=False,
            field_type=str,
            description="Nome team casa corretto se FotMob ha rilevato inversione",
        ),
        FieldSpec(
            "validated_away_team",
            required=False,
            field_type=str,
            description="Nome team trasferta corretto se FotMob ha rilevato inversione",
        ),
        FieldSpec(
            "final_verification_info",
            required=False,
            field_type=dict,
            description="V11.1: Risultati Final Alert Verifier da Perplexity API",
        ),
        FieldSpec(
            "injury_intel",
            required=False,
            field_type=dict,
            description="Analisi impatto infortuni",
        ),
        FieldSpec(
            "confidence_breakdown",
            required=False,
            field_type=dict,
            description="Breakdown confidenza (news_weight, odds_weight, form_weight, injuries_weight)",
        ),
        FieldSpec(
            "market_warning",
            required=False,
            field_type=str,
            description="V11.1: Warning message per alert late-to-market",
        ),
    ],
)


# ============================================
# CONTRACT REGISTRY
# ============================================

ALL_CONTRACTS = {
    "news_item": NEWS_ITEM_CONTRACT,
    "snippet_data": SNIPPET_DATA_CONTRACT,
    "analysis_result": ANALYSIS_RESULT_CONTRACT,
    "news_radar_analysis_result": NEWS_RADAR_ANALYSIS_RESULT_CONTRACT,
    "verification_result": VERIFICATION_RESULT_CONTRACT,
    "alert_payload": ALERT_PAYLOAD_CONTRACT,
}


def get_contract(name: str) -> Contract:
    """Get a contract by name."""
    if name not in ALL_CONTRACTS:
        raise ValueError(f"Contract '{name}' not found. Available: {list(ALL_CONTRACTS.keys())}")
    return ALL_CONTRACTS[name]


def validate_contract(name: str, data: dict[str, Any]) -> tuple:
    """
    Validate data against a named contract.

    Returns:
        Tuple of (is_valid, errors)
    """
    contract = get_contract(name)
    return contract.validate(data)


def assert_contract(name: str, data: dict[str, Any], context: str = "") -> None:
    """
    Assert data is valid against a named contract.
    Raises ContractViolation if not.
    """
    contract = get_contract(name)
    contract.assert_valid(data, context)
