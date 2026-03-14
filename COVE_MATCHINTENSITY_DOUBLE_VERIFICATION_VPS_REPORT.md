# COVE Double Verification Report: MatchIntensity Feature

**Date:** 2026-03-12  
**Mode:** Chain of Verification (CoVe)  
**Focus:** MatchIntensity enum implementation and VPS deployment readiness

---

## Executive Summary

The `MatchIntensity` enum is defined in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:85-91) and used in the [`BettingStatsResponse`](src/schemas/perplexity_schemas.py:199) Pydantic model. However, **2 critical bugs** and **1 integration issue** were identified that must be fixed before VPS deployment.

**Status:** ⚠️ **NOT READY FOR VPS DEPLOYMENT** - Critical fixes required

---

## FASE 1: Generazione Bozza (Draft)

*Preliminary analysis based on immediate knowledge.*

The `MatchIntensity` enum is defined with four values: HIGH, MEDIUM, LOW, and UNKNOWN. It's used in the `BettingStatsResponse` Pydantic model with default value `MatchIntensity.UNKNOWN`. The field has a validator that ensures the value is a valid enum member, falling back to UNKNOWN if invalid.

The enum is exported from `src/schemas/__init__.py` and used in system prompts where it specifies that match_intensity must be "High/Medium/Low" (or "Unknown").

The data flow:
1. AI providers (Perplexity, DeepSeek) call `get_betting_stats()` which returns a dict
2. The dict is validated using `BettingStatsResponse` Pydantic model
3. The `match_intensity` field is validated by validator
4. The validated data is used in verification_layer.py for analysis

Dependencies: Pydantic 2.12.5 is already in requirements.txt, no new dependencies needed for VPS deployment.

---

## FASE 2: Verifica Avversariale (Cross-Examination)

*Critical questions to DISPROVE the draft.*

### 1. Fatti (date, numeri, versioni)

- **Q:** È vero che Pydantic 2.12.5 è in requirements.txt? Verificare la versione esatta.
- **Q:** È vero che MatchIntensity ha solo 4 valori? Verificare se mancano altri valori possibili.

### 2. Codice (sintassi, parametri, import)

- **Q:** È corretto il validator `validate_match_intensity`? Verificare se usa `mode="before"` come altri validatori simili.
- **Q:** L'enum è importato correttamente in `__init__.py`? Verificare se mancano altri import.
- **Q:** Il validator è case-insensitive come altri validatori (es. `cards_signal`, `referee_strictness`)?
- **Q:** Il default `MatchIntensity.UNKNOWN` è corretto o dovrebbe essere diverso?

### 3. Logica

- **Q:** Il validator fallback a UNKNOWN è sufficiente o dovrebbe loggare un warning?
- **Q:** Il campo `match_intensity` viene effettivamente usato nel bot oltre che nella definizione dello schema?
- **Q:** Il valore `match_intensity` viene estratto e usato in `verification_layer.py` come altri campi (corners, cards, form)?
- **Q:** Il sistema di fallback (DeepSeek → Perplexity → OpenRouter) preserva correttamente il campo `match_intensity`?

### 4. Integrazione VPS

- **Q:** Le dipendenze per Pydantic sono già incluse in requirements.txt?
- **Q:** Ci sono script di auto-installazione che potrebbero mancare?
- **Q:** Il campo `match_intensity` viene serializzato/deserializzato correttamente per il database?

---

## FASE 3: Esecuzione Verifiche

*Independent verification based ONLY on pre-trained knowledge and code review.*

### Verifica 1: Fatti (date, numeri, versioni)

**Q:** È vero che Pydantic 2.12.5 è in requirements.txt?

**A:** ✅ YES - Verified in [`requirements.txt`](requirements.txt:9): `pydantic==2.12.5`

**Q:** È vero che MatchIntensity ha solo 4 valori?

**A:** ✅ YES - Verified in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:85-91):
```python
class MatchIntensity(str, Enum):
    """Match intensity levels."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"
```

### Verifica 2: Codice (sintassi, parametri, import)

**Q:** È corretto il validator `validate_match_intensity`? Verificare se usa `mode="before"` come altri validatori simili.

**A:** ❌ **[CRITICAL BUG FOUND]** 

The validator [`validate_match_intensity`](src/schemas/perplexity_schemas.py:340-349) does NOT use `mode="before"`, while similar validators like [`validate_cards_signal`](src/schemas/perplexity_schemas.py:306-321) and [`validate_referee_strictness`](src/schemas/perplexity_schemas.py:323-338) do use it.

**Impact:**
- Without `mode="before"`, Pydantic attempts to convert the string to enum first
- If the string is invalid, it raises ValueError instead of falling back to UNKNOWN
- The try-except in the validator never executes because the error happens before

**Current code (lines 340-349):**
```python
@field_validator("match_intensity")
@classmethod
def validate_match_intensity(cls, v):
    """Validate match intensity is a valid enum."""
    if isinstance(v, str):
        try:
            return MatchIntensity(v)
        except ValueError:
            return MatchIntensity.UNKNOWN
    return v
```

**Correct code should be:**
```python
@field_validator("match_intensity", mode="before")
@classmethod
def validate_match_intensity(cls, v):
    """Validate match intensity is a valid enum (case-insensitive)."""
    if isinstance(v, str):
        v_lower = v.lower()
        for intensity in [
            MatchIntensity.HIGH,
            MatchIntensity.MEDIUM,
            MatchIntensity.LOW,
            MatchIntensity.UNKNOWN,
        ]:
            if v_lower == intensity.value.lower():
                return intensity
        return MatchIntensity.UNKNOWN
    return v
```

**Q:** L'enum è importato correttamente in `__init__.py`?

**A:** ✅ YES - Verified in [`src/schemas/__init__.py`](src/schemas/__init__.py:18): import is present and correct. Also included in `__all__` at line 35.

**Q:** Il validator è case-insensitive come altri validatori?

**A:** ❌ **[CRITICAL BUG FOUND]**

The current validator is NOT case-insensitive. It uses `MatchIntensity(v)` which is case-sensitive. Other validators like `validate_cards_signal` and `validate_referee_strictness` are case-insensitive (see lines 311-320 and 328-336).

**Q:** Il default `MatchIntensity.UNKNOWN` è corretto?

**A:** ✅ YES - The default is appropriate for an optional field that represents information that might not be available.

### Verifica 3: Logica

**Q:** Il validator fallback a UNKNOWN è sufficiente o dovrebbe loggare un warning?

**A:** ⚠️ The validator should log a warning when falling back to UNKNOWN, similar to other validators in the file. However, this is an enhancement, not a critical bug.

**Q:** Il campo `match_intensity` viene effettivamente usato nel bot oltre che nella definizione dello schema?

**A:** ❌ **[INTEGRATION ISSUE FOUND]**

The field `match_intensity` is NOT extracted or used in [`verification_layer.py`](src/analysis/verification_layer.py:3520-3570). Only these fields are extracted:
- corners (home_corners_avg, away_corners_avg, corners_signal)
- cards (home_cards_avg, away_cards_avg, cards_signal)
- form (home_form_wins, home_form_draws, home_form_losses, away_form_wins, away_form_draws, away_form_losses)
- referee (referee_name, referee_cards_avg)

NOT extracted:
- `match_intensity`
- `referee_strictness`
- `is_derby`

**Q:** Il valore `match_intensity` viene estratto e usato in `verification_layer.py` come altri campi (corners, cards, form)?

**A:** ❌ NO - See above.

**Q:** Il sistema di fallback (DeepSeek → Perplexity → OpenRouter) preserva correttamente il campo `match_intensity`?

**A:** ✅ YES - The field is preserved through the fallback system because:
1. All providers use `BettingStatsResponse` for validation
2. Pydantic validation ensures the field is present
3. However, since the field is not extracted in verification_layer.py, the value is lost

### Verifica 4: Integrazione VPS

**Q:** Le dipendenze per Pydantic sono già incluse in requirements.txt?

**A:** ✅ YES - `pydantic==2.12.5` is present in [`requirements.txt`](requirements.txt:9).

**Q:** Ci sono script di auto-installazione che potrebbero mancare?

**A:** ✅ YES - The deployment scripts are present:
- [`setup_vps.sh`](setup_vps.sh:134) - Installs dependencies via `pip install -r requirements.txt`
- [`deploy_to_vps.sh`](deploy_to_vps.sh:62) - Installs dependencies on VPS
- [`deploy_to_vps_v2.sh`](deploy_to_vps_v2.sh) - Enhanced deployment script
- [`run_forever.sh`](run_forever.sh:24) - Auto-install missing dependencies

**Q:** Il campo `match_intensity` viene serializzato/deserializzato correttamente per il database?

**A:** ⚠️ **NOT VERIFIED** - No database tables or models were found that use `match_intensity`. The field appears to be used only in-memory for AI analysis.

---

## FASE 4: Risposta Finale (Canonical)

*Final definitive response, ignoring the draft from FASE 1.*

### COVE Double Verification Report: MatchIntensity Feature

#### Executive Summary

La funzionalità `MatchIntensity` è definita come enum in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:85-91) e utilizzata nel modello [`BettingStatsResponse`](src/schemas/perplexity_schemas.py:199). Tuttavia, sono stati identificati **2 problemi critici** e **1 problema di integrazione** che devono essere risolti prima del deployment su VPS.

**Status:** ⚠️ **NON PRONTO PER DEPLOYMENT VPS** - Correzioni critiche necessarie

#### Problemi Identificati

##### **CRITICO #1: Validator non usa `mode="before"`**

**Posizione:** [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:340-349)

**Problema:** Il validator `validate_match_intensity` non usa `mode="before"`, a differenza di validatori simili (`cards_signal`, `referee_strictness`). Questo causa:
- ValueError quando il valore non è valido invece di fallback a UNKNOWN
- Il try-except nel validator non viene mai eseguito
- Crash potenziale su VPS se l'API restituisce valori non validi

**Codice attuale:**
```python
@field_validator("match_intensity")
@classmethod
def validate_match_intensity(cls, v):
    """Validate match intensity is a valid enum."""
    if isinstance(v, str):
        try:
            return MatchIntensity(v)
        except ValueError:
            return MatchIntensity.UNKNOWN
    return v
```

**Codice corretto:**
```python
@field_validator("match_intensity", mode="before")
@classmethod
def validate_match_intensity(cls, v):
    """Validate match intensity is a valid enum (case-insensitive)."""
    if isinstance(v, str):
        v_lower = v.lower()
        for intensity in [
            MatchIntensity.HIGH,
            MatchIntensity.MEDIUM,
            MatchIntensity.LOW,
            MatchIntensity.UNKNOWN,
        ]:
            if v_lower == intensity.value.lower():
                return intensity
        return MatchIntensity.UNKNOWN
    return v
```

##### **CRITICO #2: Validator non case-insensitive**

**Posizione:** [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:340-349)

**Problema:** Il validator attuale è case-sensitive, mentre tutti gli altri validatori simili sono case-insensitive. Questo può causare:
- Fallimento della validazione se l'API restituisce "high" invece di "High"
- Incoerenza con il resto del sistema

##### **PROBLEMA DI INTEGRAZIONE: Campo non estratto in verification_layer.py**

**Posizione:** [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:3520-3570)

**Problema:** Il campo `match_intensity` viene validato ma NON viene estratto né utilizzato nel layer di verifica. Vengono estratti solo:
- corners (home_corners_avg, away_corners_avg, corners_signal)
- cards (home_cards_avg, away_cards_avg, cards_signal)
- form (home_form_wins, home_form_draws, home_form_losses, away_form_wins, away_form_draws, away_form_losses)
- referee (referee_name, referee_cards_avg)

Mancano:
- `match_intensity`
- `referee_strictness`
- `is_derby`

Questo significa che il valore viene perso dopo la validazione e non viene utilizzato nell'analisi finale.

#### Flusso dei Dati Attuale

```
1. AI Provider (Perplexity/DeepSeek) → get_betting_stats()
   ↓
2. Response dict con match_intensity
   ↓
3. BettingStatsResponse validation (match_intensity viene validato)
   ↓
4. verification_layer.py estrae SOLO corners, cards, form, referee
   ↓
5. match_intensity viene PERSO ❌
```

#### Flusso dei Dati Corretto (Dopo le correzioni)

```
1. AI Provider (Perplexity/DeepSeek) → get_betting_stats()
   ↓
2. Response dict con match_intensity
   ↓
3. BettingStatsResponse validation (match_intensity viene validato correttamente)
   ↓
4. verification_layer.py estrae TUTTI i campi inclusi match_intensity
   ↓
5. match_intensity viene UTILIZZATO nell'analisi ✅
```

#### Dipendenze VPS

**Stato:** ✅ OK

Le dipendenze sono già incluse in [`requirements.txt`](requirements.txt:9):
- `pydantic==2.12.5`

Non sono necessarie nuove dipendenze per queste modifiche.

**Script di auto-installazione:**
- [`setup_vps.sh`](setup_vps.sh:134) - Esegue `pip install -r requirements.txt`
- [`deploy_to_vps.sh`](deploy_to_vps.sh:62) - Installa le dipendenze sulla VPS
- [`run_forever.sh`](run_forever.sh:24) - Auto-installazione delle dipendenze mancanti

#### Test Coverage

**Stato:** ⚠️ PARZIALE

I test in [`tests/test_perplexity_structured_outputs.py`](tests/test_perplexity_structured_outputs.py:156-169) verificano che:
- `match_intensity` può essere impostato a "High"
- Il campo viene serializzato correttamente

MA non testano:
- ❌ Valori non validi (dovrebbero fallback a UNKNOWN)
- ❌ Case-insensitivity ("high" vs "High")
- ❌ Estrazione del campo in verification_layer.py

#### Raccomandazioni per VPS Deployment

1. **CORREGGERE il validator** per usare `mode="before"` e case-insensitivity
2. **AGGIUNGERE estrazione** di `match_intensity` in verification_layer.py
3. **AGGIUNGERE test** per edge cases e case-insensitivity
4. **VALUTARE** se aggiungere `referee_strictness` e `is_derby` all'estrazione

#### Correzioni da Applicare

**File:** [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:340-349)

Sostituire il validator esistente con:
```python
@field_validator("match_intensity", mode="before")
@classmethod
def validate_match_intensity(cls, v):
    """Validate match intensity is a valid enum (case-insensitive)."""
    if isinstance(v, str):
        v_lower = v.lower()
        for intensity in [
            MatchIntensity.HIGH,
            MatchIntensity.MEDIUM,
            MatchIntensity.LOW,
            MatchIntensity.UNKNOWN,
        ]:
            if v_lower == intensity.value.lower():
                return intensity
        return MatchIntensity.UNKNOWN
    return v
```

**File:** [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:3562-3570)

Aggiungere dopo l'estrazione del referee (intorno alla riga 3565):
```python
# Extract match context data
match_intensity = safe_dict_get(betting_stats, "match_intensity", default="Unknown")
referee_strictness = safe_dict_get(betting_stats, "referee_strictness", default="Unknown")
is_derby = safe_dict_get(betting_stats, "is_derby", default=False)

logger.debug(f"🎯 [V2.6] Match context: intensity={match_intensity}, "
            f"referee_strictness={referee_strictness}, is_derby={is_derby}")
```

#### Conclusioni

La funzionalità `MatchIntensity` è definita correttamente ma ha **2 bug critici** nel validator e **1 problema di integrazione** che impedisce l'utilizzo effettivo del campo. Senza queste correzioni, il campo viene validato ma poi perso, e il validator può causare crash su VPS se riceve valori non validi o case-differenti.

**Priorità:** ALTA - Correzioni necessarie prima del deployment su VPS.

---

## Appendice: Dettagli Tecnici

### File Modificati

1. **[`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:340-349)**
   - Aggiungere `mode="before"` al decorator `@field_validator`
   - Implementare case-insensitive validation
   - Allineare con altri validatori simili

2. **[`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:3562-3570)**
   - Estrarre `match_intensity` dalla response
   - Estrarre `referee_strictness` e `is_derby` (opzionale ma raccomandato)
   - Aggiungere logging per debug

### Test da Aggiungere

```python
def test_match_intensity_case_insensitive():
    """Test that match_intensity validation is case-insensitive."""
    data = {
        "corners_signal": "High",
        "match_intensity": "high",  # lowercase
        "is_derby": False,
        "data_confidence": "High",
    }
    response = BettingStatsResponse(**data)
    assert response.match_intensity == MatchIntensity.HIGH

def test_match_intensity_invalid_fallback():
    """Test that invalid match_intensity falls back to UNKNOWN."""
    data = {
        "corners_signal": "High",
        "match_intensity": "InvalidValue",  # invalid
        "is_derby": False,
        "data_confidence": "High",
    }
    response = BettingStatsResponse(**data)
    assert response.match_intensity == MatchIntensity.UNKNOWN
```

### Checklist per VPS Deployment

- [x] Pydantic 2.12.5 in requirements.txt
- [ ] Validator `validate_match_intensity` usa `mode="before"`
- [ ] Validator `validate_match_intensity` è case-insensitive
- [ ] Campo `match_intensity` estratto in verification_layer.py
- [ ] Test per case-insensitivity aggiunti
- [ ] Test per fallback a UNKNOWN aggiunti
- [ ] Logging aggiunto per debug su VPS

---

**Report Generated:** 2026-03-12T22:30:00Z  
**Verification Method:** Chain of Verification (CoVe) - 4 Phase Protocol  
**Status:** CRITICAL BUGS FOUND - NOT READY FOR VPS DEPLOYMENT
