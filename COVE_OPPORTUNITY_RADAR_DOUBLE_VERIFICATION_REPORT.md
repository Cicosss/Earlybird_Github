# COVE DOUBLE VERIFICATION REPORT: OpportunityRadar Implementation

**Data:** 2026-03-08  
**Componente:** OpportunityRadar + FotMob Integration  
**Scope:** Verifica completa di implementazione, integrazione, e compatibilità VPS

---

## ESECUZIONE RIASSUNTIVA

### Correzioni Identificate: **3 CRITICHE**

| # | Problema | Severità | File | Linee |
|---|-----------|----------|-------|-------|
| 1 | `get_search_provider()` non esiste | **CRITICO** | `src/ingestion/opportunity_radar.py` | 25, 355 |
| 2 | `fotmob` property non thread-safe | **ALTO** | `src/ingestion/opportunity_radar.py` | 291-298 |
| 3 | `trigger_pipeline()` usa `importlib` fragile | **ALTO** | `src/ingestion/opportunity_radar.py` | 667-675 |
| 4 | Match ID non garantisce unicità | **MEDIO** | `src/ingestion/opportunity_radar.py` | 609-612 |

### Verifiche Passate: **7/11**

| # | Verifica | Esito |
|---|----------|-------|
| 1 | Import `get_search_provider()` | ❌ **FALLITO** |
| 2 | Lazy loading `fotmob` thread-safe | ❌ **FALLITO** |
| 3 | `trigger_pipeline()` con `importlib` | ❌ **FALLITO** |
| 4 | Unicità Match ID | ❌ **FALLITO** |
| 5 | Processed URLs con confidence < 7 | ✅ **PASSATO** |
| 6 | Dipendenze in requirements.txt | ✅ **PASSATO** |
| 7 | API Keys configurate | ✅ **PASSATO** |
| 8 | Creazione automatica file JSON | ✅ **PASSATO** |
| 9 | Forced narrative bypassa news hunting | ✅ **PASSATO** |
| 10 | Timing nel ciclo principale | ✅ **PASSATO** |
| 11 | Error handling in `run_opportunity_radar()` | ✅ **PASSATO** |

---

## DETTAGLIO DELLE CORREZIONI

### 🔴 CORREZIONE 1: `get_search_provider()` Non Esiste

**Posizione:** [`src/ingestion/opportunity_radar.py:25`](src/ingestion/opportunity_radar.py:25)

**Problema:**
```python
# Linea 25 - INCORRETTO
from src.ingestion.search_provider import get_search_provider
```

Questa funzione **NON ESISTE** in [`search_provider.py`](src/ingestion/search_provider.py). La classe [`SearchProvider`](src/ingestion/search_provider.py:415) esiste, ma non c'è una funzione factory.

**Impatto su VPS:**
- Quando [`_search_region()`](src/ingestion/opportunity_radar.py:351) chiama `get_search_provider()` a riga 355, causerà `ImportError` o `AttributeError`
- Il DDG fallback **NON FUNZIONERÀ**
- Il radar dipenderà esclusivamente da Brave Search API

**Soluzione Proposta:**
```python
# Opzione 1: Creare la funzione factory in search_provider.py
def get_search_provider() -> SearchProvider:
    """Get singleton instance of SearchProvider (thread-safe)."""
    global _search_provider_instance
    if _search_provider_instance is None:
        with _search_provider_lock:
            if _search_provider_instance is None:
                _search_provider_instance = SearchProvider()
    return _search_provider_instance

# Opzione 2: Usare direttamente SearchProvider in opportunity_radar.py
from src.ingestion.search_provider import SearchProvider

# In __init__:
self._search_provider = None

@property
def search_provider(self):
    if self._search_provider is None:
        self._search_provider = SearchProvider()
    return self._search_provider
```

---

### 🟠 CORREZIONE 2: `fotmob` Property Non Thread-Safe

**Posizione:** [`src/ingestion/opportunity_radar.py:291-298`](src/ingestion/opportunity_radar.py:291)

**Problema:**
```python
@property
def fotmob(self):
    """Lazy load FotMob provider."""
    if self._fotmob is None:
        from src.ingestion.data_provider import get_data_provider
        self._fotmob = get_data_provider()
    return self._fotmob
```

Se due thread chiamano contemporaneamente `self.fotmob`, entrambi potrebbero vedere `_fotmob is None` e chiamare `get_data_provider()` contemporaneamente.

**Impatto su VPS:**
- Race condition in ambiente multi-threaded
- Possibile creazione di multiple istanze di FotMobProvider
- Anche se `get_data_provider()` è thread-safe, la property non lo è

**Soluzione Proposta:**
```python
import threading

class OpportunityRadar:
    def __init__(self):
        self.processed_urls = self._load_processed_urls()
        self._fotmob = None
        self._fotmob_lock = threading.Lock()  # Aggiungi lock
        logger.info("🎯 Opportunity Radar initialized")

    @property
    def fotmob(self):
        """Lazy load FotMob provider (thread-safe)."""
        if self._fotmob is None:
            with self._fotmob_lock:
                if self._fotmob is None:  # Double-check
                    from src.ingestion.data_provider import get_data_provider
                    self._fotmob = get_data_provider()
        return self._fotmob
```

---

### 🟠 CORREZIONE 3: `trigger_pipeline()` Usa `importlib` Fragile

**Posizione:** [`src/ingestion/opportunity_radar.py:667-675`](src/ingestion/opportunity_radar.py:667)

**Problema:**
```python
try:
    import importlib
    main_module = importlib.import_module("src.main")
    analyze_fn = getattr(main_module, "analyze_single_match", None)
    if analyze_fn and callable(analyze_fn):
        analyze_fn(match_id, forced_narrative=forced_narrative)
```

**Problemi:**
1. **Import circolare potenziale:** Se `opportunity_radar.py` viene importato da `main.py`, e poi `trigger_pipeline()` re-importa `main.py`, può causare problemi
2. **Inefficiente:** Ogni trigger re-importa il modulo `main.py`
3. **Non necessario:** `analyze_single_match` è già definito in `main.py`

**Impatto su VPS:**
- Performance degradata
- Possibili crash con import circolari
- Difficile da testare

**Soluzione Proposta:**
```python
# Opzione 1: Importare direttamente all'inizio
from src.main import analyze_single_match

# In trigger_pipeline():
try:
    analyze_single_match(match_id, forced_narrative=forced_narrative)
    logger.info(f"✅ Pipeline triggered for {canonical_name}")
except ImportError as e:
    logger.warning(f"Could not import analyze_single_match: {e}")
except Exception as e:
    logger.error(f"Pipeline trigger failed: {e}")

# Opzione 2: Passare come callback durante inizializzazione
def __init__(self, analyze_callback=None):
    self.processed_urls = self._load_processed_urls()
    self._fotmob = None
    self._analyze_callback = analyze_callback or self._default_analyze_callback
    logger.info("🎯 Opportunity Radar initialized")

def _default_analyze_callback(self, match_id, forced_narrative):
    """Default callback that imports main.py."""
    import importlib
    main_module = importlib.import_module("src.main")
    analyze_fn = getattr(main_module, "analyze_single_match", None)
    if analyze_fn and callable(analyze_fn):
        analyze_fn(match_id, forced_narrative)
```

---

### 🟡 CORREZIONE 4: Match ID Non Garantisce Unicità

**Posizione:** [`src/ingestion/opportunity_radar.py:609-612`](src/ingestion/opportunity_radar.py:609)

**Problema:**
```python
match_id = (
    f"radar_{home_team}_{away_team}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
)
match_id = match_id.replace(" ", "_").lower()
```

**Problemi:**
1. **Stesso giorno, stessa coppia:** Due match tra le stesse squadre lo stesso giorno generano lo stesso ID
2. **Nessun controllo duplicati:** Il codice cerca match esistenti solo con `home_team` e `away_team`, non con l'ID generato

**Impatto su VPS:**
- Possibili duplicati nel database
- Conflitti se due match tra le stesse squadre avvengono lo stesso giorno (es. coppa)

**Soluzione Proposta:**
```python
# Opzione 1: Includere timestamp più granulare
match_id = (
    f"radar_{home_team}_{away_team}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
)

# Opzione 2: Usare l'ora del match se disponibile
match_time = match_info.get("match_time")
if match_time:
    time_str = match_time.strftime('%Y%m%d_%H%M')
else:
    time_str = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
match_id = f"radar_{home_team}_{away_team}_{time_str}"

# Opzione 3: Aggiungere UUID
import uuid
match_id = f"radar_{home_team}_{away_team}_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
```

---

## VERIFICHE PASSATE (CORRETTE)

### ✅ Verifica 5: Processed URLs con Confidence < 7

**Esito:** CORRETTO

Il codice [`_mark_url_processed()`](src/ingestion/opportunity_radar.py:756) viene chiamato **SOLO** se `confidence >= 7` E se `team` e `narrative_type` sono presenti. Questo è il comportamento desiderato.

### ✅ Verifica 6: Dipendenze in requirements.txt

**Esito:** CORRETTO

Tutte le dipendenze necessarie sono presenti in [`requirements.txt`](requirements.txt):
- `ddgs==9.10.0` per DuckDuckGo
- `httpx[http2]==0.28.1` per Brave Search
- `openai==2.16.0` per OpenRouter/DeepSeek
- `fuzz[speedup]==0.22.1` per fuzzy matching

### ✅ Verifica 7: API Keys Configurate

**Esito:** CORRETTO

Tutte le API keys necessarie sono configurate in [`.env.template`](.env.template):
- `BRAVE_API_KEY`, `BRAVE_API_KEY_1/2/3` per Brave Search
- `OPENROUTER_API_KEY` per DeepSeek AI
- `OPENROUTER_MODEL=deepseek/deepseek-chat-v3-0324`

### ✅ Verifica 8: Creazione Automatica File JSON

**Esito:** CORRETTO

La prima chiamata a [`_save_processed_urls()`](src/ingestion/opportunity_radar.py:324) creerà automaticamente la directory `data/` e il file `radar_processed_urls.json`.

### ✅ Verifica 9: Forced Narrative Bypassa News Hunting

**Esito:** CORRETTO

In [`AnalysisEngine.analyze_match()`](src/core/analysis_engine.py:1163), se `forced_narrative` è presente, viene usato direttamente invece di chiamare `run_hunter_for_match()`, risparmiando API quota.

### ✅ Verifica 10: Timing nel Ciclo Principale

**Esito:** CORRETTO

Il radar viene eseguito ogni 4 ore (0, 4, 8, 12, 16, 20 UTC) prima di `run_pipeline()`. L'ordine è corretto: radar → pipeline.

### ✅ Verifica 11: Error Handling in `run_opportunity_radar()`

**Esito:** CORRETTO

Il codice è wrapped in try-except, quindi se il radar crasha, viene loggato l'errore e il bot continua con `run_pipeline()`.

---

## ANALISI INTEGRAZIONE CON BOT

### Flusso Dati Completo

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Main Loop (ogni 4 ore)                                  │
│    should_run_radar() → run_opportunity_radar()               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. OpportunityRadar.scan(regions)                            │
│    - Per ogni regione in RADAR_SOURCES                        │
│    - _search_region() → DDG/Brave                            │
│    - _extract_narrative_with_ai() → DeepSeek                 │
│    - Filtra confidence >= 7                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. OpportunityRadar.trigger_pipeline()                          │
│    - _resolve_team_name() → FotMob fuzzy match                │
│    - _get_next_match_for_team() → FotMob API                │
│    - _find_or_create_match_in_db() → Database                │
│    - analyze_single_match(match_id, forced_narrative)        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. analyze_single_match()                                    │
│    - Crea NewsLog con forced_narrative                       │
│    - AnalysisEngine.analyze_match(context_label="RADAR")       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. AnalysisEngine.analyze_match()                            │
│    - Bypassa news hunting (usa forced_narrative)             │
│    - Run triangulation analysis                               │
│    - Verify alert before sending                              │
│    - Send alert if threshold met                              │
└─────────────────────────────────────────────────────────────────┘
```

### Punti di Contatto Critici

1. **Search Provider Layer** ([`_search_region()`](src/ingestion/opportunity_radar.py:351))
   - Dipende da: DDG (gratis) o Brave (API key)
   - **PROBLEMA:** `get_search_provider()` non esiste
   - **Rischio:** DDG fallback non funzionerà

2. **AI Extraction Layer** ([`_extract_narrative_with_ai()`](src/ingestion/opportunity_radar.py:463))
   - Dipende da: DeepSeek (OpenRouter API)
   - Confidence threshold: 7/10
   - **OK:** API key configurata

3. **Team Resolution Layer** ([`_resolve_team_name()`](src/ingestion/opportunity_radar.py:527))
   - Dipende da: FotMob fuzzy matching
   - **PROBLEMA:** `fotmob` property non thread-safe
   - **Rischio:** Race condition in multi-threading

4. **Match Creation Layer** ([`_find_or_create_match_in_db()`](src/ingestion/opportunity_radar.py:581))
   - Dipende da: Database Session
   - **PROBLEMA:** Match ID non garantisce unicità
   - **Rischio:** Duplicati in database

5. **Pipeline Trigger Layer** ([`trigger_pipeline()`](src/ingestion/opportunity_radar.py:639))
   - Dipende da: `analyze_single_match()` in main.py
   - **PROBLEMA:** Usa `importlib` fragile
   - **Rischio:** Import circolari, performance degradata

6. **Analysis Engine Layer** ([`AnalysisEngine.analyze_match()`](src/core/analysis_engine.py:977))
   - Usa: `forced_narrative` per bypassare news hunting
   - **OK:** Implementazione corretta

---

## COMPATIBILITÀ VPS

### Requisiti Auto-Installazione

✅ **Tutte le dipendenze sono in requirements.txt:**
```bash
pip install -r requirements.txt
```

✅ **API keys configurabili via .env:**
```bash
cp .env.template .env
# Editare .env con le reali API keys
```

✅ **File creati automaticamente:**
- `data/radar_processed_urls.json` - creato da `_save_processed_urls()`
- Directory `data/` - creata automaticamente se non esiste

### Risorse VPS

**Stima consumo:**
- **RAM:** ~50-100 MB (OpportunityRadar + cache)
- **CPU:** Minimo durante idle, spike durante scan
- **Disk:** ~1-5 MB per `radar_processed_urls.json` (dipende da numero di URL)
- **API Quota:**
  - DeepSeek: ~10-20 calls/scan (dipende da risultati)
  - Brave: ~1 call/regione (10 regioni = 10 calls/scan)
  - Totale/4 ore: ~30 calls = ~220 calls/giorno

**Raccomandazioni VPS:**
- **RAM minima:** 512 MB
- **RAM consigliata:** 1 GB
- **CPU:** 1 core sufficiente
- **Disk:** 1 GB sufficiente

### Crash Recovery

✅ **Error handling presente:**
- [`run_opportunity_radar()`](src/main.py:1824) wrapped in try-except
- Se crasha, bot continua con `run_pipeline()`
- Errori loggati correttamente

⚠️ **Potenziali problemi:**
- Se `get_search_provider()` fallisce, DDG fallback non funziona
- Se `importlib` fallisce, pipeline non viene triggerato

---

## RACCOMANDAZIONI FINALI

### Priorità 1 (CRITICO - Da risolvere prima del deploy VPS)

1. **Creare `get_search_provider()` in [`search_provider.py`](src/ingestion/search_provider.py)**
   - Implementare pattern singleton thread-safe
   - Aggiornare import in [`opportunity_radar.py`](src/ingestion/opportunity_radar.py:25)

2. **Rendere `fotmob` property thread-safe**
   - Aggiungere lock con double-checked locking
   - Prevenire race conditions in multi-threading

### Priorità 2 (ALTO - Fortemente raccomandato)

3. **Rimuovere `importlib` da [`trigger_pipeline()`](src/ingestion/opportunity_radar.py:667)**
   - Importare direttamente `analyze_single_match`
   - Oppure passare come callback

4. **Migliorare unicità Match ID**
   - Includere timestamp più granulare
   - Aggiungere controllo duplicati con ID generato

### Priorità 3 (MEDIO - Miglioramenti)

5. **Aggiungere logging più dettagliato**
   - Loggare confidence score per ogni extraction
   - Loggare team resolution success/failure

6. **Aggiungere metriche**
   - Numero di URL processati per scan
   - Numero di pipeline triggerati
   - Confidence distribution

---

## CONCLUSIONI

### Stato Attuale: **NON PRONTO PER PRODUZIONE VPS**

**Motivi:**
1. `get_search_provider()` non esiste → DDG fallback non funzionerà
2. `fotmob` property non thread-safe → race conditions
3. `trigger_pipeline()` usa `importlib` fragile → potenziali crash

### Azioni Richieste:

1. ✅ **IMMEDIATO:** Implementare le 4 correzioni prioritarie
2. ✅ **TESTING:** Eseguire test suite con `pytest tests/test_chaos_audit_fixes.py`
3. ✅ **VPS DEPLOYMENT:** Testare su VPS con ambiente reale
4. ✅ **MONITORING:** Aggiungere logging e metriche per production

### Dopo le Correzioni:

✅ **OpportunityRadar sarà:**
- Thread-safe
- Integrato correttamente con bot
- Compatibile con VPS
- Robusto contro crash
- Intelligente nel flusso dati

---

**Report generato:** 2026-03-08T21:59:20Z  
**Metodo:** Chain of Verification (CoVe) - Double Verification  
**Severità:** 3 CRITICHE, 7 VERIFICHE PASSATE
