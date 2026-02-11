# 🦅 EarlyBird V9.5 - Deploy Instructions

Guida definitiva per il deploy su Ubuntu VPS.

**Version History:**
- **V9.5** (Current) - Supabase Database Integration
  - Added Supabase database connection for continental orchestration
  - Integrated ContinentalOrchestrator for time-based league scheduling
  - Added API Handshake validation (make check-apis) as mandatory pre-deploy step
- **V8.3** - Learning Loop Integrity Fix
  - Added `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at` columns for accurate ROI calculations
  - Fixed learning loop data integrity issues
- **V8.0** - Tactical Brain Integration
  - asyncio.run() instead of deprecated get_event_loop()
  - Tactical Veto (V8.0) - Applied when market signals contradict tactical reality
- **V7.3** - Added `last_alert_time` column for temporal reset
- **V7.2** - Signal handling fixes in news_radar
- **V7.1** - Test Monitor integration
- **V7.0** - Intelligence Router with DeepSeek primary + Tavily pre-enrichment
- **V5.3** - Odds type conversion and validation fixes
- **V5.2** - Input validation and edge case handling in optimizer

**Novità V9.5:**
- 🗄️ **Supabase Integration**: Added cloud database for continental orchestration
- 🌍 **Continental Orchestrator**: Time-based league scheduling across continents
- 🚨 **API Handshake**: Mandatory pre-deploy validation of all API credentials (make check-apis)
- 🔄 **Mirror Fallback**: Local mirror file for resilience during Supabase outages
- 🚪 **3-Level Intelligence Gate**: Zero-cost keyword filtering (95% token savings)
  - Level 1: 147 native keywords in 9 languages (FREE)
  - Level 2: DeepSeek V3 translation and classification
  - Level 3: DeepSeek R1 deep reasoning for BET/NO BET verdict
- 🤖 **Dual-Model Hierarchy**: Model A (Standard) + Model B (Reasoner)
- 🔴 **Cross-Source Convergence**: Detects signals in both Web and Social sources

**Novità V8.3:**
- 🎯 **Learning Loop Integrity**: Fixed ROI calculation accuracy with proper odds tracking
- 📊 **New Database Columns**: `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at` for precise performance metrics
- 🔧 **Data Type Fixes**: Improved odds type conversion and validation (V5.3)
- 🛡️ **Session Handling**: Fixed signal handling in news_radar (V7.2) and asyncio migration (V8.0)

---

## 🏗️ System Architecture Overview

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EARLYBIRD V9.5                            │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │  MAIN   │          │   BOT   │          │ MONITOR │
   │ (main)  │          │  (bot)  │          │(monitor)│
   └────┬────┘          └────┬────┘          └────┬────┘
        │                     │                     │
        │                     │                     │
   ┌────▼─────────────────────▼─────────────────────▼────┐
   │              INTELLIGENCE ROUTER (V7.0)              │
   │         DeepSeek (Primary) + Tavily (Pre-enrich)    │
   └────┬────────────────────────────────────────────────┘
        │
   ┌────▼────────────────────────────────────────────────┐
   │           INTELLIGENCE FEATURES (10+)               │
   │  Market, Tactical Veto, B-Team, BTTS, Motivation,  │
   │  Twitter Intel, News Intel, Telegram Intel, Radar   │
   └────┬────────────────────────────────────────────────┘
        │
   ┌────▼────────────────────────────────────────────────┐
   │              DATA PROVIDERS                          │
   │  Tavily, Perplexity, Brave, DDG, DeepSeek, Odds API │
   └─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    NEWS RADAR (news_radar)                        │
│              Autonomous 24/7 News Monitoring                      │
│              Opportunity Radar (V2.0)                             │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

1. **Launcher V3.7** ([`src/launcher.py`](src/launcher.py:36)) - Process Orchestrator
   - Manages 4 processes with auto-restart
   - Exponential backoff for crash recovery
   - CPU protection and graceful shutdown

2. **Intelligence Router V7.0** ([`src/services/intelligence_router.py`](src/services/intelligence_router.py))
   - Routes to DeepSeek (primary AI)
   - Tavily pre-enrichment for context
   - Fallback chain: Tavily → Perplexity → Cache → Default

3. **10+ Intelligence Features**
   - Market Intelligence (V1.1): Steam Move, Reverse Line, News Decay
   - Tactical Veto (V8.0): Market vs tactical reality check
   - B-Team Detection (V2.0): Financial Intelligence for lineups
   - BTTS Intelligence (V4.1): Head-to-head BTTS trends
   - Motivation Intelligence (V4.2): Title race, relegation analysis
   - Twitter Intel (V7.0): Cached Twitter for grounding
   - News Intelligence: Scoring and aggregation
   - Telegram Intelligence: Squad image OCR
   - Opportunity Radar (V2.0): Narrative-first scanner

4. **Test Framework**
    - pytest with 11 markers (unit, integration, regression, contract, snapshot, chaos, slow, e2e, performance, security)
    - Contract testing for interface validation
    - Snapshot testing for regression detection
    - Chaos testing for resilience verification

---

## 📡 Telegram Session Setup (One-Time)

Per abilitare l'accesso completo ai canali Telegram (inclusi canali privati per insider intel), è necessario creare una sessione utente Telegram.

### Funzionalità

| Modalità | Funzionalità | Canali Accessibili |
|----------|--------------|-------------------|
| **Senza Sessione** | 50% | Solo canali pubblici |
| **Con Sessione** | 100% | Pubblici + Privati |

### Setup (One-Time)

```bash
# Metodo 1: Usando make (raccomandato)
make setup-telegram-auth

# Metodo 2: Esecuzione diretta
python setup_telegram_auth.py
```

Quando richiesto:
1. Inserisci il numero: `+393703342314`
2. Inserisci il codice OTP ricevuto su Telegram
3. Se richiesto, inserisci la password 2FA

Il file `data/earlybird_monitor.session` verrà creato automaticamente.

### Fallback Automatico

Il sistema [`run_telegram_monitor.py`](run_telegram_monitor.py:266) implementa un sistema di fallback a 3 livelli:

1. **Priorità 1**: Sessione Utente (100% - canali privati + pubblici)
2. **Priorità 2**: Bot Token (50% - solo canali pubblici)
3. **Priorità 3**: Modalità IDLE con retry ogni 5 minuti

Questo significa che anche senza la sessione utente, il monitor funziona al 50% e non crasha.

### Note Importanti

- ⚠️ **Non condividere il file sessione**: Contiene token di autenticazione sensibili
- 💾 **Backup della sessione**: Mantieni una copia del file sessione localmente
- 🔄 **Session expiration**: Le sessioni Telegram possono scadere dopo inattività prolungata
- 📱 **Multi-device**: Se usi Telegram su altri dispositivi, la sessione potrebbe invalidarsi

### Deploy su VPS

Per il deploy su VPS:

1. Esegui `make setup-telegram-auth` localmente per creare la sessione
2. Copia il file `data/earlybird_monitor.session` sulla VPS
3. Assicurati che le credenziali TELEGRAM_API_ID e TELEGRAM_API_HASH siano nel file `.env` della VPS

Per dettagli completi, vedi [`TELEGRAM_SESSION_SETUP.md`](TELEGRAM_SESSION_SETUP.md:1).

---

## 🧪 TEST & DEBUG TOOLKIT (V7.1)

Prima del deploy, verifica che i componenti funzionino correttamente usando il nuovo toolkit di debug.

### Validatori Centralizzati

I validatori in `src/utils/validators.py` permettono di verificare la correttezza dei dati in transito tra componenti:

```python
# Verifica news item da news_hunter
from src.utils.validators import validate_news_item, assert_valid_news_item

result = validate_news_item(news_data)
if not result.is_valid:
    print(f"❌ News invalida: {result.errors}")

# Nei test, usa assertion helper
assert_valid_news_item(news_data, "Browser monitor output")
```

**Componenti validabili:**
- `validate_news_item()` - Output di news_hunter
- `validate_verification_request()` - Input del Verification Layer
- `validate_verification_result()` - Output del Verification Layer
- `validate_analysis_result()` - Output dell'Analyzer
- `validate_alert_payload()` - Payload per Telegram

### Log Capture per Test

La fixture `log_capture` permette di verificare che eventi critici siano loggati:

```python
def test_fallback_logged(log_capture):
    # Trigger fallback
    trigger_tavily_failure()
    
    # Verifica che il fallback sia stato loggato
    log_capture.assert_logged("Tavily fallback", level="WARNING")
    assert log_capture.contains_pattern(r"Perplexity.*activated")
```

### Esecuzione Test Pre-Deploy

```bash
# Attiva venv
source venv/bin/activate

# Test rapidi (unit test)
pytest tests/ -m unit -v

# Test di regressione
pytest tests/ -m regression -v

# Test completi (include integration)
pytest tests/ -v --tb=short

# Test specifici per validatori
pytest tests/test_validators.py -v
```

### Checklist Pre-Deploy

- [ ] `pytest tests/ -m unit` passa senza errori
- [ ] `pytest tests/test_validators.py` passa
- [ ] Verificato che i log critici siano presenti (usa `log_capture`)
- [ ] API keys verificate (`make check-apis`)

---

## 🧠 INTELLIGENCE FEATURES (V9.5)

Il sistema include 12+ modelli di intelligence per l'analisi predittiva e decisionale.

### Core Intelligence Features

| Feature | Version | Location | Description |
|---------|---------|----------|-------------|
| **🚪 Intelligence Gate** | V9.5 ⭐ NEW | `src/utils/intelligence_gate.py` | 3-level gating for 95% token savings |
| **🤖 Dual-Model Hierarchy** | V9.5 ⭐ NEW | `src/utils/intelligence_gate.py` | Model A (Standard) + Model B (Reasoner) |
| **🔴 Cross-Source Convergence** | V9.5 ⭐ NEW | `src/analysis/analyzer.py` | Web + Social signal matching |
| **Intelligence Router** | V7.0 | `src/services/intelligence_router.py` | Routes to DeepSeek (primary) with Tavily pre-enrichment |
| **Market Intelligence** | V1.1 | `src/analysis/market_intelligence.py` | Steam Move, Reverse Line, News Decay analysis |
| **Tactical Veto** | V8.0 | `src/analysis/` | Applied when market signals contradict tactical reality |
| **B-Team Detection** | V2.0 | `src/analysis/` | Financial Intelligence for detecting B-Team/Reserves lineups |
| **BTTS Intelligence** | V4.1 | `src/analysis/` | Head-to-Head BTTS Trend Analysis |
| **Motivation Intelligence** | V4.2 | `src/analysis/` | Title race, relegation, dead rubber analysis |
| **Twitter Intel** | V7.0 | `src/services/twitter_intel_cache.py` | Cached Twitter Intel for search grounding |
| **News Intelligence** | - | `src/analysis/news_scorer.py` | News scoring and aggregation |
| **Telegram Intelligence** | - | `src/analysis/image_ocr.py` | Squad image scraping and OCR analysis |
| **Opportunity Radar** | V2.0 | `src/ingestion/opportunity_radar.py` | Narrative-First Intelligence Scanner |

### V9.5 New Features

#### 🚪 Intelligence Gate (V9.5) ⭐ NEW
3-level tiered gating system for processing global intelligence at 5% of current cost:

| Level | Type | Model | Cost |
|-------|------|-------|------|
| **Level 1** | Zero-Cost Keyword Check | Python locale | FREE |
| **Level 2** | Economic AI Translation | DeepSeek V3 | ~$0.001/call |
| **Level 3** | Deep R1 Reasoning | DeepSeek R1 | ~$0.01/call |

**Keywords:** 147 total (75 injury + 72 team) in 9 languages:
- Spanish, Arabic, French, German, Portuguese, Polish, Turkish, Russian, Dutch

**Expected Savings:** 95% reduction in token costs

**Usage:**
```python
from src.utils.intelligence_gate import (
    level_1_keyword_check,
    level_2_translate_and_classify,
    level_3_deep_reasoning,
    apply_intelligence_gate
)

# Level 1 - Zero cost (local Python)
passed, keyword = level_1_keyword_check("El jugador tiene una lesión")

# Level 2 - Economic ($0.001/call)
result = await level_2_translate_and_classify(text)

# Level 3 - Deep reasoning ($0.01/call)
verdict = await level_3_deep_reasoning(intel_package)

# Combined gate (Level 1 + 2)
gate_result = await apply_intelligence_gate(text)
```

#### 🤖 Dual-Model Hierarchy (V9.5) ⭐ NEW

| Model | ID | Purpose |
|-------|-----|---------|
| **Model A (Standard)** | `deepseek/deepseek-chat` | Translation, metadata extraction, low-priority tasks |
| **Model B (Reasoner)** | `deepseek/deepseek-r1-0528:free` | Triangulation, Verification, BET/NO BET verdict |

#### 🔴 Cross-Source Convergence (V9.5) ⭐ NEW
- Detects when the same signal appears in both Web (Brave) and Social (Nitter)
- High-priority tag: 🔴 CONFERMA MULTIPLA: WEB + SOCIAL
- Signal matching criteria: type, team reference, time window (24h), confidence > 0.6

### Feature Details

#### Intelligence Router (V7.0)
- Primary: DeepSeek AI for deep analysis
- Pre-enrichment: Tavily search for context gathering
- Fallback chain: Tavily → Perplexity → Cache → Default
- Used by: News Radar, Browser Monitor, Telegram Monitor, Settler, CLV Tracker

#### Market Intelligence (V1.1)
- **Steam Move**: Detects sudden odds movements
- **Reverse Line**: Identifies reverse line movements
- **News Decay**: Analyzes news impact over time

#### Tactical Veto (V8.0)
- Activates when market signals contradict tactical reality
- Prevents false positives from market manipulation
- Integrates with Tactical Brain decision logic

#### B-Team Detection (V2.0)
- Financial Intelligence for lineup analysis
- Detects B-Team/Reserves lineups before kickoff
- Uses financial data and squad rotation patterns

#### BTTS Intelligence (V4.1)
- Head-to-Head BTTS (Both Teams To Score) trend analysis
- Historical match data for BTTS prediction
- Team-specific BTTS patterns

#### Motivation Intelligence (V4.2)
- Title race motivation analysis
- Relegation battle detection
- Dead rubber (meaningless match) identification

#### Twitter Intel (V7.0)
- Cached Twitter Intelligence for search grounding
- Reduces API calls through intelligent caching
- Integrates with Nitter fallback scraper

#### News Intelligence
- News scoring algorithm for relevance
- Aggregates multiple news sources
- Filters noise and prioritizes high-value information

#### Telegram Intelligence
- Squad image scraping from Telegram channels
- OCR analysis for lineup detection
- Insider channel monitoring

#### Opportunity Radar (V2.0)
- Narrative-First Intelligence Scanner
- Autonomous news monitoring for minor leagues
- 24/7 monitoring of configured sources

---

## 🔧 RECENT FIXES (V8.3)

### V8.3 - Learning Loop Integrity Fix

**Problem:** The learning loop had data integrity issues affecting ROI calculation accuracy.

**Solution:** Added three new database columns for precise performance tracking:

| Column | Type | Purpose |
|--------|------|---------|
| `odds_at_alert` | REAL | Stores odds value when alert was sent |
| `odds_at_kickoff` | REAL | Stores odds value at kickoff time |
| `alert_sent_at` | TIMESTAMP | Records exact time when alert was sent |

**Impact:** Enables accurate ROI calculations by tracking odds movement from alert to kickoff.

**Migration:** `src/database/migration_v83_odds_fix.py` and `src/deploy_v83_odds_fix.py`

### V8.0 - asyncio Migration

**Problem:** Deprecated `get_event_loop()` causing compatibility issues.

**Solution:** Migrated to `asyncio.run()` for async event loop management.

**Impact:** Improved compatibility with Python 3.10+ and removed deprecation warnings.

### V7.3 - Temporal Reset Column

**Problem:** No tracking of last alert time for temporal reset logic.

**Solution:** Added `last_alert_time` column to database.

**Impact:** Enables proper temporal reset for alert frequency control.

### V7.2 - Signal Handling Fixes

**Problem:** News radar process had improper signal handling causing graceful shutdown issues.

**Solution:** Fixed signal handling in `run_news_radar.py`.

**Impact:** Proper graceful shutdown of news radar process.

### V5.3 - Odds Type Conversion

**Problem:** Odds type conversion and validation issues causing data errors.

**Solution:** Improved odds type conversion and validation logic.

**Impact:** Reduced data errors and improved odds accuracy.

### V5.2 - Input Validation

**Problem:** Edge cases in optimizer causing unexpected behavior.

**Solution:** Added comprehensive input validation and edge case handling.

**Impact:** More robust optimizer with fewer edge case failures.

### V4.6 - Data Type Fixes

**Problem:** Data type inconsistencies in database operations.

**Solution:** Standardized data types across database operations.

**Impact:** Reduced type-related errors and improved data consistency.

---

## 🔬 TEST AVANZATI (V7.2)

Tre nuovi tipi di test per garantire qualità e resilienza del sistema.

### Contract Testing (`tests/test_contracts.py`)

Verifica che le interfacce tra componenti siano rispettate:

```python
# I contratti definiscono cosa passa tra componenti
# news_hunter → main.py → analyzer → verification_layer → notifier

from src.utils.contracts import NEWS_ITEM_CONTRACT, assert_contract

# Valida che un news item rispetti il contratto
is_valid, errors = NEWS_ITEM_CONTRACT.validate(news_data)

# Nei test, usa assert_contract per fallire su violazioni
assert_contract('news_item', news_data, context="Browser monitor output")
```

**Contratti disponibili:**
- `NEWS_ITEM_CONTRACT` - news_hunter → main.py
- `SNIPPET_DATA_CONTRACT` - main.py → analyzer
- `ANALYSIS_RESULT_CONTRACT` - analyzer → main.py
- `VERIFICATION_RESULT_CONTRACT` - verification_layer → main.py
- `ALERT_PAYLOAD_CONTRACT` - main.py → notifier

### Snapshot Testing (`tests/test_snapshots.py`)

Rileva regressioni nell'output dei componenti:

```python
# Gli snapshot salvano l'output atteso e lo confrontano con l'attuale
# Se l'output cambia, il test fallisce

# Prima esecuzione: crea lo snapshot
# Esecuzioni successive: confronta con lo snapshot salvato

# Per aggiornare gli snapshot intenzionalmente:
UPDATE_SNAPSHOTS=1 pytest tests/test_snapshots.py -v
```

**Snapshot salvati in:** `tests/snapshots/`

### Chaos Testing (`tests/test_chaos.py`)

Verifica la resilienza del sistema sotto stress:

```python
# Simula scenari di errore realistici:
# - API timeout (Tavily, Perplexity, Telegram)
# - Rate limit (429 errors)
# - Dati malformati (JSON invalido, campi mancanti)
# - Database locked
# - Servizi esterni down
```

**Scenari testati:**
- Timeout API con retry e backoff
- Rate limit con rispetto di Retry-After
- Fallback chain (Tavily → Perplexity → Cache → Default)
- Circuit breaker pattern
- Thread safety della discovery queue

### Esecuzione Test Avanzati

```bash
# Tutti i test avanzati
pytest tests/test_contracts.py tests/test_snapshots.py tests/test_chaos.py -v

# Solo contract testing
pytest tests/test_contracts.py -v

# Solo chaos testing (resilienza)
pytest tests/test_chaos.py -v

# Test completi con marker
pytest tests/ -m "contract or snapshot or chaos" -v
```

### Pytest Framework & Markers

Il sistema usa pytest con marker per categorizzare i test:

| Marker | Description | Command |
|--------|-------------|---------|
| `unit` | Unit tests (isolated, fast) | `pytest tests/ -m unit -v` |
| `integration` | Integration tests (component interaction) | `pytest tests/ -m integration -v` |
| `regression` | Regression tests (bug fix verification) | `pytest tests/ -m regression -v` |
| `contract` | Contract tests (interface validation) | `pytest tests/ -m contract -v` |
| `snapshot` | Snapshot tests (output regression detection) | `pytest tests/ -m snapshot -v` |
| `chaos` | Chaos tests (resilience under stress) | `pytest tests/ -m chaos -v` |
| `slow` | Slow tests (long-running) | `pytest tests/ -m slow -v` |
| `e2e` | End-to-end tests (full workflow) | `pytest tests/ -m e2e -v` |
| `performance` | Performance tests (benchmarking) | `pytest tests/ -m performance -v` |
| `security` | Security tests (vulnerability scanning) | `pytest tests/ -m security -v` |

### Test Execution Commands

```bash
# Unit tests only (fast)
pytest tests/ -m unit -v

# Integration tests
pytest tests/ -m integration -v

# Regression tests
pytest tests/ -m regression -v

# All advanced tests
pytest tests/ -m "contract or snapshot or chaos" -v

# Full test suite (includes slow tests)
pytest tests/ -v --tb=short

# E2E tests only
pytest tests/ -m e2e -v

# Performance tests
pytest tests/ -m performance -v

# Security tests
pytest tests/ -m security -v

# Skip slow tests
pytest tests/ -v -m "not slow"

# Run specific test file
pytest tests/test_contracts.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Checklist Test Avanzati

- [ ] `pytest tests/test_contracts.py` - Interfacce componenti OK
- [ ] `pytest tests/test_snapshots.py` - Nessuna regressione output
- [ ] `pytest tests/test_chaos.py` - Sistema resiliente a errori

---

## 🖥️ Specifiche VPS di Produzione

| Risorsa | Valore |
|---------|--------|
| **CPU** | 4 core vCPU |
| **RAM** | 8 GB |
| **Storage** | 150 GB SSD |
| **Snapshot** | 1 inclusa |
| **Banda** | 200 Mbit/s |
| **OS** | Ubuntu Linux |

---

## 1️⃣ Preparazione Locale

### Crea lo ZIP (escludendo file non necessari)
```bash
zip -r earlybird_v83_YYYYMMDD.zip \
  src/ config/ tests/ .env requirements.txt pytest.ini \
  run_forever.sh run_tests_monitor.sh \
  start_system.sh setup_vps.sh \
  setup_telegram_auth.py show_errors.py \
  go_live.py run_news_radar.py run_telegram_monitor.py \
  README.md ARCHITECTURE.md DEPLOY_INSTRUCTIONS.md \
  -x "*.pyc" -x "*__pycache__*" -x "*.session" -x "*.log" -x "*.db" -x "venv/*" -x ".venv/*"
```

### Upload su VPS
```bash
scp earlybird_v83_YYYYMMDD.zip root@YOUR_VPS_IP:/root/
```

---

## 2️⃣ Setup VPS (Clean Install)

### Ferma processi esistenti
```bash
screen -X -S earlybird quit 2>/dev/null
screen -X -S bot quit 2>/dev/null
pkill -9 -f python
```

### Rimuovi vecchia installazione (opzionale)
```bash
cd /root
rm -rf earlybird
```

### Estrai e installa
```bash
mkdir -p earlybird
cd earlybird
unzip /root/earlybird_v83_YYYYMMDD.zip
chmod +x setup_vps.sh
./setup_vps.sh
```

> ⏱️ **Nota:** Lo script impiega ~3-5 minuti per scaricare Chromium e le dipendenze.

---

## 3️⃣ Procedura Operativa di Lancio (Dashboard Experience)

Per l'ultima volta, segui questi passaggi per fare tabula rasa e far partire il nuovo "Mostro" V8.3 con il **Unified Dashboard**:

### Dal terminale dell'IDE:

**Crea lo ZIP pulito (escludendo file temporanei):**

```bash
zip -r earlybird_v83_FINAL.zip \
  src/ config/ tests/ .env requirements.txt pytest.ini Makefile \
  start_system.sh setup_vps.sh run_tests_monitor.sh \
  README.md ARCHITECTURE.md DEPLOY_INSTRUCTIONS.md \
  -x "*.pyc" -x "*__pycache__*" -x "*.session" -x "*.log" -x "*.db" -x "venv/*" -x ".venv/*"
```

**Invia alla VPS:**

```bash
scp earlybird_v83_FINAL.zip root@YOUR_VPS_IP:/root/
```

### Sulla VPS (Wipe & Start):

```bash
# 1. Kill totale (Reset ambiente)
tmux kill-session -t earlybird 2>/dev/null
pkill -9 -f python
rm -rf earlybird

# 2. Installazione
unzip earlybird_v83_FINAL.zip -d earlybird
cd earlybird
./setup_vps.sh

# 3. Inizializzazione
cp .env.template .env  # O ripristina il tuo .env salvato
make check-apis        # 🚨 CRITICAL: API Handshake - MUST PASS before proceeding
make migrate

# 4. 🚀 GO LIVE (Dashboard Mode)
./start_system.sh
```

> **Nota:** Il comando `./start_system.sh` aprirà automaticamente una sessione Tmux chiamata `earlybird` con:
> - **Left Panel**: Launcher (Bot + News Radar)
> - **Right Panel**: Test Monitor (Health Checks ogni 5 min)


---

## 4️⃣ Configurazione

### File `.env` (API Keys)

Se non presente, crea da template:
```bash
cp .env.example .env
nano .env
```

**Chiavi richieste:**
```env
# Core APIs
ODDS_API_KEY=your_key
BRAVE_API_KEY=your_key
SERPER_API_KEY=your_key

# AI (DeepSeek - Primary for Intelligence Router V7.0)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek/deepseek-chat

# OpenRouter (fallback)
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=deepseek/deepseek-chat-v3-0324

# Tavily AI Search (7 keys - 1000 calls each = 7000/month)
# Keys rotate automatically when quota exhausted
# Used by: Intelligence Router, News Radar, Browser Monitor, Telegram Monitor, Settler, CLV Tracker
TAVILY_API_KEY_1=tvly-your-key-1
TAVILY_API_KEY_2=tvly-your-key-2
TAVILY_API_KEY_3=tvly-your-key-3
TAVILY_API_KEY_4=tvly-your-key-4
TAVILY_API_KEY_5=tvly-your-key-5
TAVILY_API_KEY_6=tvly-your-key-6
TAVILY_API_KEY_7=tvly-your-key-7
TAVILY_ENABLED=true

# Perplexity (fallback for Tavily)
PERPLEXITY_API_KEY=your_key

# Telegram Bot (per alert)
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Telegram Client (per monitoring canali)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

### Verifica API Keys
```bash
source venv/bin/activate
make check-apis
```

> 🚨 **CRITICAL STEP - API HANDSHAKE:** This command validates all API credentials (Odds, Brave, OpenRouter, Tavily, Perplexity, Supabase, etc.) before starting the bot. **DO NOT PROCEED** until all checks pass successfully.

---

## 4️⃣ Inizializzazione

### ⚡ CRITICAL: API Handshake (MANDATORY - Run BEFORE starting the bot)
```bash
source venv/bin/activate
make check-apis
```

> 🚨 **STOP:** Do NOT proceed with database initialization or bot startup until `make check-apis` passes successfully. This command verifies:
> - **Odds API** - Authentication and league discovery
> - **Brave API** - Search functionality (3 keys)
> - **OpenRouter API** - AI model access
> - **Tavily API** - Search capabilities (7 keys)
> - **Perplexity API** - Fallback search
> - **Supabase Database** - Connection and data access (V9.0)
> - **Continental Orchestrator** - League scheduling (V9.0)
>
> This prevents "Blind Start" on the VPS. Every deploy must begin with a successful API Handshake.

### Database
```bash
source venv/bin/activate
python3 -c "from src.database.db import init_db; init_db(); print('✅ Database inizializzato')"
```

### Database Migrations (V8.3)
Se stai aggiornando da una versione precedente, esegui le migrazioni:

```bash
# V8.3 Learning Loop Integrity Fix
python3 src/deploy_v83_odds_fix.py

# Oppure manualmente:
python3 -c "from src.database.migration_v83_odds_fix import migrate; migrate()"
```

**V8.3 Migration adds:**
- `odds_at_alert` column (REAL)
- `odds_at_kickoff` column (REAL)
- `alert_sent_at` column (TIMESTAMP)

### Migration Paths

#### From V8.0 to V8.3
```bash
# 1. Stop all processes
tmux kill-session -t earlybird
pkill -f python

# 2. Backup database
cp data/earlybird.db data/earlybird.db.backup_v80

# 3. Run V8.3 migration
source venv/bin/activate
python3 src/deploy_v83_odds_fix.py

# 4. Verify migration
sqlite3 data/earlybird.db "PRAGMA table_info(matches);" | grep -E "odds_at_alert|odds_at_kickoff|alert_sent_at"

# 5. Restart system
./start_system.sh
```

#### From V7.x to V8.3
```bash
# 1. Stop all processes
tmux kill-session -t earlybird
pkill -f python

# 2. Backup database
cp data/earlybird.db data/earlybird.db.backup_v7x

# 3. Run migrations in order
source venv/bin/activate
python3 -c "from src.database.migration import migrate; migrate()"  # V7.3
python3 src/deploy_v83_odds_fix.py  # V8.3

# 4. Verify migrations
sqlite3 data/earlybird.db "PRAGMA table_info(matches);" | grep -E "last_alert_time|odds_at_alert|odds_at_kickoff|alert_sent_at"

# 5. Restart system
./start_system.sh
```

#### From V5.x to V8.3
```bash
# 1. Stop all processes
tmux kill-session -t earlybird
pkill -f python

# 2. Backup database
cp data/earlybird.db data/earlybird.db.backup_v5x

# 3. Run all migrations
source venv/bin/activate
python3 -c "from src.database.migration import migrate; migrate()"  # V7.3
python3 src/deploy_v83_odds_fix.py  # V8.3

# 4. Verify migrations
sqlite3 data/earlybird.db "PRAGMA table_info(matches);" | grep -E "last_alert_time|odds_at_alert|odds_at_kickoff|alert_sent_at"

# 5. Restart system
./start_system.sh
```

### Autenticazione Telegram (solo prima volta)
```bash
python3 setup_telegram_auth.py
```
> Segui le istruzioni: inserisci numero di telefono → codice ricevuto su Telegram → (eventuale 2FA)

**Nota:** La session viene salvata come `earlybird_monitor.session` per evitare conflitti con il bot.

---

## 5️⃣ Avvio Sistema

### Metodo consigliato (Dashboard Experience) ⭐

```bash
./start_system.sh
```

Questo comando (V8.3):
1. Esegue **Pre-Flight Checks** (`make check-env`, `make test-unit`)
2. Apre tmux con due pannelli affiancati:
   - **Sinistra**: Process Orchestrator (`make run-launcher`)
   - **Destra**: Health Monitor (`make run-monitor`)

```
┌─────────────────────────────┬─────────────────────────────┐
│                             │                             │
│   🦅 MAIN ORCHESTRATOR      │   🧪 HEALTH MONITOR         │
│   (src/launcher.py)         │   (run_tests_monitor.sh)    │
│                             │                             │
│   • Pipeline (main)         │   • Validatori Data         │
│   • Bot Telegram            │   • DB Checks               │
│   • News Radar              │   • API Validations         │
│   • Telegram Monitor        │   • 5 min loop              │
│                             │                             │
└─────────────────────────────┴─────────────────────────────┘
```

### 🎮 Navigazione Tmux

| Comando | Azione |
|---------|--------|
| `Ctrl+B` poi `←` o `→` | Sposta tra pannelli |
| `Ctrl+B` poi `d` | Detach (esci senza fermare) |
| `Ctrl+B` poi `z` | Zoom pannello corrente (toggle) |
| `Ctrl+B` poi `x` | Chiudi pannello corrente |
| `Ctrl+B` poi `[` | Scroll mode (q per uscire) |

### Rientrare nella sessione
```bash
tmux attach -t earlybird
```

### Fermare tutto
```bash
tmux kill-session -t earlybird
```

### Metodo alternativo (screen - legacy)
```bash
screen -S earlybird ./run_forever.sh
```

Per uscire dalla screen: `Ctrl+A` poi `D`

### Rientrare nella screen
```bash
screen -r earlybird
```

### 🤖 Processi Avviati Automaticamente

Il launcher ([`src/launcher.py`](src/launcher.py:36)) gestisce 4 processi con auto-restart:

| Process Name | Script | Purpose | Location |
|--------------|--------|---------|----------|
| `main` | [`src/main.py`](src/launcher.py:36) | Pipeline Principale (Odds + News + Analysis) | Main Application |
| `bot` | [`src/run_bot.py`](src/launcher.py:41) | Telegram Bot (User commands interface) | User Commands |
| `monitor` | `run_telegram_monitor.py` | Telegram Monitor (Squad image scraping) | Insider Channel Monitoring |
| `news_radar` | `run_news_radar.py` | News Radar (Autonomous news monitoring for minor leagues) | 24/7 News Hunter |

### Process Management Logic

Il launcher implementa robusto process management con:

- **Auto-Restart**: Processi vengono riavviati automaticamente in caso di crash
- **Exponential Backoff**: Retry con backoff esponenziale per evitare loop infiniti
- **CPU Protection**: Monitoraggio CPU per prevenire runaway processes
- **Graceful Shutdown**: Segnali SIGTERM/SIGINT gestiti correttamente
- **Health Monitoring**: Ogni processo monitora la propria salute

### Entry Points & Scripts

| Script | Version | Purpose |
|--------|---------|---------|
| `go_live.py` | V3.1 | Headless Launcher (avvia sistema senza UI) |
| `run_news_radar.py` | - | News Radar Monitor (autonomo 24/7) |
| `run_telegram_monitor.py` | - | Telegram Monitor (squad image scraping) |
| `src/main.py` | - | Main Application (pipeline principale) |
| `src/launcher.py` | V3.7 | Process Orchestrator (gestisce 4 processi) |
| `src/run_bot.py` | - | Telegram Bot (interfaccia comandi utente) |

### Shell Scripts

| Script | Version | Purpose |
|--------|---------|---------|
| `start_system.sh` | V7.1 | Sistema Completo con Test Monitor (tmux + 2 pannelli) |
| `run_forever.sh` | V3.3 | Launcher Script (avvia launcher.py con auto-restart) |
| `run_tests_monitor.sh` | - | Test Monitor (esegue test ogni 5 minuti) |

> **News Radar** è un componente autonomo che monitora fonti web configurate in `config/news_radar_sources.json` e invia alert diretti su Telegram per leghe minori.

---

## 6️⃣ Comandi Utili

### Monitoraggio
```bash
# Ultimi 50 errori/warning
python show_errors.py

# Follow errori in tempo reale
python show_errors.py -f

# Log bot principale
tail -f earlybird.log

# Log test monitor
tail -f test_monitor.log
```

### Gestione processi
```bash
# Lista sessioni tmux
tmux ls

# Ferma tutto (tmux)
tmux kill-session -t earlybird

# Lista screen attive (legacy)
screen -ls

# Ferma tutto (legacy)
pkill -f python
```

### Database
```bash
# Reset completo DB
rm data/earlybird.db*
python3 -c "from src.database.db import init_db; init_db()"
```

---

## 🔧 Troubleshooting

### V8.3 Specific Issues

#### Missing V8.3 Database Columns
If you see errors about missing columns after upgrade:

```bash
# Run V8.3 migration
source venv/bin/activate
python3 src/deploy_v83_odds_fix.py

# Verify columns exist
sqlite3 data/earlybird.db "PRAGMA table_info(matches);" | grep -E "odds_at_alert|odds_at_kickoff|alert_sent_at"
```

#### ROI Calculation Errors
If ROI calculations seem incorrect:

```bash
# Check that odds_at_alert and odds_at_kickoff are being populated
sqlite3 data/earlybird.db "SELECT id, odds_at_alert, odds_at_kickoff, alert_sent_at FROM matches WHERE odds_at_alert IS NOT NULL LIMIT 10;"

# If null values, check logs for errors
tail -f earlybird.log | grep -i "odds_at"
```

### General Issues

### "database is locked"
```bash
pkill -f python
sleep 2
./run_forever.sh
```

### "no such table: matches"
```bash
rm data/earlybird.db*
source venv/bin/activate
python3 -c "from src.database.db import init_db; init_db()"
./run_forever.sh
```

### Tesseract OCR errors
```bash
# Reinstall tesseract if OCR fails
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng libtesseract-dev
```

### Telegram session expired
```bash
rm earlybird_monitor.session
python3 setup_telegram_auth.py
```

### "database is locked" persistente
Il sistema usa WAL mode con busy_timeout=30s. Se il problema persiste:
```bash
pkill -f python
sqlite3 data/earlybird.db "PRAGMA wal_checkpoint(TRUNCATE);"
./run_forever.sh
```

### Intelligence Router Not Responding
Check if DeepSeek API is configured:

```bash
# Verify DeepSeek API key
grep DEEPSEEK_API_KEY .env

# Test Intelligence Router
python3 -c "from src.services.intelligence_router import IntelligenceRouter; router = IntelligenceRouter(); print('✅ Router OK')"
```

### News Radar Not Running
Check news_radar process:

```bash
# Check if news_radar process is running
ps aux | grep news_radar

# Check news_radar logs
tail -f news_radar.log

# Restart news_radar manually
python3 run_news_radar.py
```

---

## 📋 Checklist Deploy

- [ ] ZIP creato con `.env` incluso (V8.3)
- [ ] Upload su VPS completato
- [ ] `setup_vps.sh` eseguito senza errori
- [ ] API keys verificate (`make check-apis`) - **CRITICAL: Must pass before proceeding**
- [ ] Database inizializzato
- [ ] **V8.3 Migration eseguita** (`python3 src/deploy_v83_odds_fix.py`)
- [ ] Telegram autenticato (se necessario)
- [ ] Test pre-avvio passano (`pytest tests/test_validators.py`)
- [ ] Sistema avviato con `./start_system.sh` (V7.1)
- [ ] Entrambi i pannelli tmux funzionanti
- [ ] 4 processi attivi: main, bot, monitor, news_radar
- [ ] Heartbeat ricevuto su Telegram

### V8.3 Verification

Verifica che le nuove colonne siano presenti nel database:

```bash
sqlite3 data/earlybird.db "PRAGMA table_info(matches);" | grep -E "odds_at_alert|odds_at_kickoff|alert_sent_at"
```

Output atteso:
```
odds_at_alert|REAL|0||0
odds_at_kickoff|REAL|0||0
alert_sent_at|TIMESTAMP|0||0
```

---
