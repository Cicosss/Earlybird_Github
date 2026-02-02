# 🦅 EarlyBird V8.3 - Self-Learning Sports Intelligence Engine

Sistema avanzato di betting intelligence con **Verification Layer**, **Tavily AI Search**, **CLV Tracking**, **Tactical Veto**, **B-Team Detection** e **auto-ottimizzazione quantitativa**. Il sistema impara dai propri risultati, adattando i pesi delle strategie in base a Sortino Ratio e Max Drawdown.

**V8.3**: Learning Loop Integrity Fix + Tactical Veto + B-Team Detection + Intelligence Router V7.0 + Opportunity Radar V2.0

## 🎯 Core Intelligence

### 🤖 AI Engine (DeepSeek V3 via OpenRouter)
- **Primary Provider**: DeepSeek con Brave Search grounding (high rate limits, no cooldown)
- **Reasoning Mode**: Analisi con trace per decisioni trasparenti
- **Triangulation Engine**: Correla 6 fonti dati (FotMob + Odds + News + Weather + Twitter Intel + Tavily)
- **Italian Localization**: Output sempre in italiano per il mercato target
- **Fallback System**: Perplexity Sonar come fallback per errori transitori

### 🔍 Tavily AI Search (V8.0) ⭐ UPDATED
- **7 API Keys Rotation**: 14000 calls/month (2x) con doppio ciclo automatico
- **Doppio Ciclo Intelligente**: Quando tutte le keys sono esaurite, verifica se è passato un mese prima del fallback
  - Se SÌ: Reset keys, riparti da Key 1 (Ciclo 2)
  - Se NO: Attiva fallback a Brave/DDG
- **Circuit Breaker**: Auto-fallback a Brave/DDG dopo 3 failures consecutivi
- **Response Caching**: 30 min TTL per evitare query duplicate
- **Budget Manager**: Allocazione per componente (main_pipeline, news_radar, etc.)
- **Cycle Tracking**: Monitoraggio del numero di cicli completati per analisi e debug
- **Native News Search**: Parametri `topic="news"` e `days` per filtering ottimale
- **File**: `src/ingestion/tavily_provider.py`, `src/ingestion/tavily_key_rotator.py`

### ✅ Verification Layer (V7.0) ⭐ NEW
- **Alert Fact-Checking**: Verifica dati con fonti esterne prima dell'invio
- **Multi-Site Queries**: FootyStats, Transfermarkt, Flashscore, SoccerStats
- **Player Impact Analysis**: Market value → impact score (€80M+ = world class)
- **Score Adjustment**: Penalità automatiche per inconsistenze rilevate
- **Market Change**: Suggerisce mercati alternativi quando appropriato
- **File**: `src/analysis/verification_layer.py`

### 📈 CLV Tracker (V5.0) ⭐ NEW
- **Closing Line Value**: Gold standard per validare edge reale
- **Edge Validation**: CLV > +2% = EXCELLENT, > +0.5% = GOOD
- **Strategy Reports**: Identifica strategie con edge reale vs lucky streaks
- **Optimizer Integration**: Dati CLV usati per weight adjustment
- **File**: `src/analysis/clv_tracker.py`

### ⚡ Fatigue Engine V2.0
- **Exponential Decay Model**: Partite recenti pesano di più (weight = 1/days_ago)
- **Squad Depth Multiplier**: Elite teams = 0.5x, Low-tier = 1.3x fatigue impact
- **21-Day Rolling Window**: Analisi congestione calendario completa
- **Late-Game Risk Prediction**: Probabilità goal subiti dopo 75' (threshold: 40%)
- **File**: `src/analysis/fatigue_engine.py`

### 🍪 Biscotto Engine V2.0
- **Z-Score Analysis**: Anomalia statistica vs media lega (28% draw probability)
- **End-of-Season Detection**: Ultime 5 giornate = alert automatico
- **Mutual Benefit Analysis**: Rileva quando entrambe le squadre beneficiano dal pareggio
- **Pattern Recognition**: DRIFT (graduale) vs CRASH (improvviso) movement
- **File**: `src/analysis/biscotto_engine.py`

### 🔍 Search Engine (V7.0)
- **TIER 0 - Browser Monitor**: Active web monitoring with Playwright + DeepSeek AI
- **TIER 0.5 - Beat Writers**: Twitter Intel Cache per insider accounts (HIGH confidence)
- **TIER 1 - Tavily AI Search**: Primary search con AI-generated answers
- **TIER 1 - Brave Search API**: Fallback (2000/month quota)
- **TIER 1 - DuckDuckGo**: Free fallback (`ddgs` package)
- **TIER 1 - Serper**: Emergency paid fallback
- **Anti-Ban Jitter**: Delay random 3-6s tra ricerche per evitare rate limits
- **DEEP DIVE ON DEMAND** ⭐ V8.0 NEW: Upgrade shallow search results to full article content when high-value keywords detected

> **V8.0**: Reddit monitoring removed - provided no betting edge (rumors arrived too late).

### 📖 Deep Dive on Demand (V8.0) ⭐ NEW

Funzionalità per trasformare risultati di ricerca "Shallow" in contenuto "Deep" quando il contesto suggerisce informazioni ad alto valore.

- **Trigger**: Keywords ad alto valore (injury, squad, turnover, suspension, transfer) nel titolo/snippet
- **Azione**: Visita l'URL ed estrae il testo completo dell'articolo
- **Tecnologia**: Trafilatura + HTTP client centralizzato
- **Configurazione**: `DEEP_DIVE_ENABLED`, `DEEP_DIVE_MAX_ARTICLES` (default: 3)
- **Fallback**: Se il deep dive fallisce, mantiene lo snippet originale
- **File**: `src/utils/article_reader.py`
- **Integrazione**: `src/processing/news_hunter.py` dopo la raccolta dei risultati di ricerca

**Flusso Semplificato**:
```
Search Results (Shallow) → Keyword Check → High-Value? → Deep Dive → Full Content → AI Analysis
```

Questo garantisce che i dettagli critici non vengano persi mantenendo le prestazioni.
### � Twitter Intel Cache (V7.0)
- **Cycle-Start Refresh**: Cache popolata all'inizio di ogni ciclo
- **DeepSeek + Nitter**: Estrazione tweet da insider accounts configurati
- **Relevance Filter**: AI scoring per match-specific relevance
- **Conflict Detection**: Twitter vs FotMob con risoluzione automatica
- **File**: `src/services/twitter_intel_cache.py`

### 📊 Stats Warehousing
- **Granular Match Stats**: Corners, Yellow/Red Cards, xG, Possession, Shots, Big Chances
- **FotMob Integration**: Estrazione automatica stats da match finiti
- **Historical Database**: Tutti gli stats salvati per analisi future
- **Null Safety**: Gestione robusta di stats mancanti (leghe minori)

### 🧠 Self-Learning Optimizer (V5.0)
- **Sample Size Guards**: FROZEN (<30 bets) → WARMING (30-50) → ACTIVE (50+)
- **Sortino Ratio**: Metrica primaria (penalizza solo downside risk)
- **Max Drawdown Protection**: Taglia peso se DD > 20%
- **CLV Integration**: Edge validation per weight adjustment
- **Nightly Recalibration**: Pesi aggiornati ogni notte alle 04:00 UTC

### 🧮 Math Engine (Poisson + Kelly)
- **Dixon-Coles Model**: ρ = -0.07 per correlazione low-scoring
- **League-Specific Home Advantage**: HA dinamico (0.22-0.40 goal boost)
- **Kelly Criterion**: Stake % ottimale con safety cap 5%
- **Value Detection**: Edge matematico vs quote bookmaker

### 🌦️ Weather Intelligence
- **Open-Meteo Integration**: Dati meteo gratuiti per ogni stadio
- **Impact Analysis**: Vento >40km/h o pioggia >5mm → segnale Under/Cards
- **Stadium Coordinates**: Lookup automatico via FotMob

### 💹 Market Intelligence (V1.1)
- **Reverse Line Movement**: Smart money contro il pubblico (65%+ threshold)
- **Steam Move Detection**: Drop >5% in finestre 15 minuti
- **News Decay**: Decadimento esponenziale (λ per tier di lega)
- **Odds Snapshots**: Tracking storico quote per analisi temporale
- **Freshness Tags**: 🔥 FRESH, ⏰ AGING, 📜 STALE

### 🎯 Tactical Veto (V8.0) ⭐ NEW
- **Market vs Tactical Conflict Detection**: Identifies when market signals contradict tactical reality
- **Automatic Veto Application**: Overrides market intelligence when tactical analysis is more reliable
- **Context-Aware Decision Making**: Considers match context, team form, and tactical setup
- **File**: `src/analysis/analyzer.py`

### 👥 B-Team Detection (V2.0) ⭐ NEW
- **Financial Intelligence**: Detects B-Team/Reserves lineups using market value analysis
- **Player Value Thresholds**: Identifies when teams field significantly weakened squads
- **Impact Assessment**: Quantifies betting impact of lineup changes
- **File**: `src/analysis/player_intel.py`

### ⚽ BTTS Intelligence (V4.1)
- **Head-to-Head BTTS Trend Analysis**: Historical both teams to score patterns
- **Team-Specific BTTS Propensity**: Analyzes attacking/defensive styles
- **Contextual Factors**: Considers injuries, fatigue, and tactical changes

### 🏆 Motivation Intelligence (V4.2)
- **Title Race Analysis**: Identifies matches with high motivation for title contenders
- **Relegation Battle Detection**: Highlights crucial matches for survival
- **Dead Rubber Recognition**: Filters out low-stakes matches with reduced motivation

### 📡 Opportunity Radar (V2.0) ⭐ NEW
- **Narrative-First Intelligence Scanner**: Detects betting opportunities from news narratives
- **Autonomous Monitoring**: Scans for emerging stories and market mispricing
- **Multi-League Coverage**: Monitors both major and minor leagues
- **File**: `src/ingestion/opportunity_radar.py`

### 🧠 Intelligence Router (V7.0) ⭐ NEW
- **DeepSeek Primary Routing**: Routes intelligence requests to DeepSeek as primary provider
- **Tavily Pre-Enrichment**: Enriches queries with Tavily search results before AI analysis
- **Smart Fallback**: Automatic fallback to alternative providers when needed
- **File**: `src/services/intelligence_router.py`

## 🌍 League Coverage

### Tier 1 - Gold List (Always Scanned)
| Flag | League | Priority |
|------|--------|----------|
| 🇹🇷 | Turkey Super Lig | 100 |
| 🇦🇷 | Argentina Primera | 98 |
| 🇲🇽 | Mexico Liga MX | 96 |
| 🇬🇷 | Greece Super League | 94 |
| 🏴󠁧󠁢󠁳󠁣󠁴󠁿 | Scotland Premiership | 92 |
| 🇦🇺 | Australia A-League | 90 |
| 🇫🇷 | France Ligue 1 | 88 |
| 🇵🇹 | Portugal Primeira Liga | 86 |
| 🇨🇭 | Switzerland Super League | 85 |

### Tier 2 - Rotation (3 per cycle, Round Robin)
| Flag | League | Priority |
|------|--------|----------|
| 🇳🇴 | Norway Eliteserien | 79 |
| 🇵🇱 | Poland Ekstraklasa | 78 |
| 🇧🇪 | Belgium First Div | 77 |
| 🇦🇹 | Austria Bundesliga | 76 |
| 🇳🇱 | Netherlands Eredivisie | 75 |
| 🇨🇳 | China Super League | 74 |
| 🇯🇵 | Japan J-League | 73 |
| 🇧🇷 | Brazil Serie B | 72 |

## 🔌 Plug & Play VPS Launch (V8.0) ⭐ NEW

Il sistema ora supporta l'avvio "Plug & Play" su VPS senza configurazione manuale:

### Environment Injection
- **Hardcoded Defaults**: Le API keys Brave hanno default hardcoded e funzionano immediatamente
- **os.environ Propagation**: Le default sono iniettate in `os.environ` per compatibilità con librerie esterne
- **Graceful Degradation**: I componenti saltano funzionalità quando le API keys mancano invece di crashare

### API Keys con Defaults
| API Key | Default | Note |
|-----------|---------|------|
| BRAVE_API_KEY_1, _2, _3 | ✅ Attive | 3 keys hardcoded |
| TAVILY_API_KEY_1 through _7 | ⚠️ Vuote | Configura per abilitare |
| MEDIASTACK_API_KEY_1 through _4 | ⚠️ Vuote | Configura per abilitare |
| PERPLEXITY_API_KEY | ⚠️ Vuoto | Configura per abilitare |
| OPENROUTER_API_KEY | ⚠️ Vuoto | Configura per abilitare |
| ODDS_API_KEY | ⚠️ Vuoto | Configura per abilitare |
| TELEGRAM_BOT_TOKEN, _CHAT_ID, _API_ID, _HASH | ⚠️ Vuoti | Configura per abilitare |

### Comportamento senza .env
1. Sistema si avvia con warning informativo
2. Brave Search funziona con default hardcoded
3. Altri provider (Tavily, MediaStack, Perplexity, OpenRouter) disabilitati
4. Telegram Bot rimane in stato "idle" (vivo ma non funzionale)
5. Main pipeline (src/main.py) continua ad operare
6. News Radar continua ad operare
7. Nessun crash-restart loop

### Setup VPS
```bash
# Clona repository
git clone <repo-url>
cd Earlybird_Github

# Esegui setup (installa tutte le dipendenze)
./setup_vps.sh

# Sistema è pronto per l'avvio
./start_system.sh
```

**Nota**: Per funzionalità completa, crea file `.env` con le tue API keys.

## 🔧 Quick Start (Dashboard Experience)

We recommend using the **Unified Dashboard** (Tmux) for all operations. This command launches the Process Orchestrator (Left Panel) and the Health Monitor (Right Panel).

```bash
# 1. Clone & Setup
git clone <repo>
cd earlybird
./setup_vps.sh

# 2. Configure Credentials
cp .env.template .env
nano .env

# 3. 🚀 LAUNCH DASHBOARD (Master Command)
./start_system.sh
```

### Alternative Methods (Legacy/Testing)
```bash
# Headless Mode (No Dashboard)
make run-launcher

# Run specific component
make run-bot
make run-news-radar
```

## 🔒 Security

EarlyBird follows strict security practices to protect your data and credentials:

- **No Backdoors**: All unauthorized access mechanisms have been completely removed (January 2026 security cleanup)
- **API Key Protection**: All credentials stored in `.env` file (excluded from version control)
- **Secure Deployment**: Standard deployment methods with no hidden access points
- **VPS Security**: Comprehensive security best practices documented in [`SECURITY.md`](SECURITY.md)

**Security Status**: ✅ Verified - No unauthorized access mechanisms in codebase

For detailed security information, see [`SECURITY.md`](SECURITY.md).

## 🤖 Componenti del Sistema

EarlyBird è composto da 4 processi gestiti automaticamente dal Launcher V3.7:

| Processo | Script | Descrizione |
|----------|--------|-------------|
| **Pipeline Principale** | `src/main.py` | Odds + News + Analysis (ciclo ogni 120 min) |
| **Telegram Bot** | `src/run_bot.py` | Comandi admin via Telegram |
| **Telegram Monitor** | `run_telegram_monitor.py` | Scraper canali Telegram per insider intel (squad image scraping) |
| **News Radar** | `run_news_radar.py` | Hunter autonomo 24/7 per leghe minori (autonomous news monitoring) |

### 🔔 News Radar (Hunter Autonomo 24/7) ⭐ CRITICAL

Componente di monitoraggio web **completamente autonomo** che opera indipendentemente dal bot principale:

- **Funzione**: Monitora fonti web configurate 24/7 per notizie betting-relevant
- **Target**: Leghe minori NON coperte dal pipeline principale
- **Alert**: Invia notifiche **dirette** su Telegram (🔔 RADAR ALERT)
- **Differenza dal Bot**: Non usa database, non passa per analyzer, alert immediato
- **Config**: `config/news_radar_sources.json`
- **Log**: `news_radar.log`
- **Launcher**: `python run_news_radar.py`

**Flow semplificato**:
```
Source URL → Extract Text → Filter → Analyze → Alert Telegram
```

**Confidence Thresholds**:
- `< 0.5`: Skip (non rilevante)
- `0.5-0.7`: Chiama DeepSeek per analisi approfondita
- `>= 0.7`: Alert diretto su Telegram

**Alert Format**:
```
🔔 RADAR ALERT 🚨
Squadra: Torino
Categoria: MASS_ABSENCE
❌ Assenti: 7 giocatori
📋 Riepilogo: ...
_Impatto betting: CRITICAL | Affidabilità: 85%_
```

## 🔑 API Keys Required (.env)

```bash
# Core APIs (Required)
OPENROUTER_API_KEY=xxx        # openrouter.ai (DeepSeek V3)
ODDS_API_KEY=xxx              # the-odds-api.com (odds tracking)

# Tavily AI Search (Required for V7.0+)
TAVILY_API_KEY_1=xxx          # tavily.com (1000 calls each)
TAVILY_API_KEY_2=xxx          # Up to 7 keys supported
# ... TAVILY_API_KEY_7

# Search Fallbacks (Optional)
BRAVE_API_KEY=xxx             # search.brave.com (2000/month)
SERPER_API_KEY=xxx            # serper.dev (emergency fallback)

# Perplexity (Optional - Fallback)
PERPLEXITY_API_KEY=xxx        # perplexity.ai (sonar-pro)

# Telegram Alerts (Required)
TELEGRAM_TOKEN=xxx            # Bot token from @BotFather
TELEGRAM_CHAT_ID=xxx          # Your chat ID

# Telegram Monitor (Optional - Insider Intel)
TELEGRAM_API_ID=xxx           # my.telegram.org
TELEGRAM_API_HASH=xxx         # my.telegram.org
```

## 🖥️ Usage (Headless Mode)

EarlyBird opera in modalità **headless** (CLI + Telegram). Nessuna dashboard web richiesta.

```bash
# Full System (Recommended)
python go_live.py                    # Launch everything (V3.1 Headless Launcher)

# Launcher V3.7 - Process Orchestrator
python src/launcher.py               # Direct launcher with process orchestration

# Individual Components
python src/main.py                   # Pipeline Principale
python src/run_bot.py                # Telegram Bot
python run_telegram_monitor.py       # Telegram Monitor
python run_news_radar.py             # News Radar

# Shell Scripts
./start_system.sh                    # Sistema Completo con Test Monitor (V7.1)
./run_forever.sh                     # Launcher Script (V3.3)
./run_tests_monitor.sh               # Test Monitor

# VPS Deployment (24/7)
./setup_vps.sh                       # One-time setup
screen -S earlybird ./run_forever.sh # Watchdog with auto-restart
```

### 🤖 Telegram Commands
| Comando | Descrizione |
|---------|-------------|
| `/stat` | Genera grafico Profitti & ROI |
| `/debug` | Mostra ultimi 15 errori/warning dal log |
| `/report` | Scarica CSV storico scommesse |
| `/settle` | Calcola risultati scommesse (72h) |
| `/status` | Stato provider AI e Browser Monitor |
| `/stop` | Pausa il loop di analisi |
| `/resume` | Riprendi il loop di analisi |
| `/ping` | Test risposta rapida |
| `/help` | Lista comandi disponibili |

### 🌙 Nightly Settlement (Automatic)
Ogni notte alle **04:00 UTC**:
- Verifica risultati partite via FotMob
- Calcolo Win/Loss, ROI e CLV
- Aggiornamento pesi Optimizer
- Report su Telegram con statistiche

## 🧪 Testing

Il progetto utilizza **pytest** come framework di testing con marker per categorizzare i test:

### Test Markers
| Marker | Descrizione |
|--------|-------------|
| `unit` | Unit tests per singole funzioni |
| `integration` | Integration tests per componenti |
| `regression` | Regression tests per bug fixes |
| `contract` | Contract tests per API contracts |
| `snapshot` | Snapshot tests per output consistency |
| `chaos` | Chaos tests per resilience testing |
| `slow` | Slow tests (es. network calls) |
| `e2e` | End-to-end tests per flussi completi |
| `performance` | Performance tests per benchmarking |
| `security` | Security tests per vulnerability checks |

### Esecuzione Test
```bash
# Esegui tutti i test
pytest

# Esegui test specifici per marker
pytest -m unit
pytest -m integration
pytest -m regression

# Esegui test con verbose output
pytest -v

# Esegui test con coverage
pytest --cov=src

# Esegui test specifici
pytest tests/test_analyzer_v61_fixes.py
```

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  EARLYBIRD V8.3 - LEARNING LOOP INTEGRITY FIX                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAUNCHER V3.7 - Process Orchestrator                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  4 Processes: main, bot, monitor, news_radar            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│  TIER 0: BROWSER MONITOR (Real-Time AI Analysis)                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Playwright + DeepSeek AI - Active web monitoring       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│  TIER 1: SEARCH ENGINES   ▼                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ TAVILY AI   │  │ BRAVE API   │  │  DUCKDUCKGO │             │
│  │ (Primary)   │  │ (Fallback)  │  │  (Free)     │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         └────────────────┼────────────────┘                     │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  INTELLIGENCE ROUTER (V7.0) ⭐ NEW                       │   │
│  │  • DeepSeek Primary + Tavily Pre-Enrichment             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  NEWS HUNTER (Orchestrator)                              │   │
│  │  • Multi-source correlation                             │   │
│  │  • News Decay (λ per league tier)                       │   │
│  │  • Sport filtering (no basket/women/futsal)             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  DEEPSEEK V3 (AI Reasoning via OpenRouter)               │   │
│  │  • Triangulate 6 data sources                           │   │
│  │  • Tactical Veto (V8.0) ⭐ NEW                           │   │
│  │  • B-Team Detection (V2.0) ⭐ NEW                        │   │
│  │  • Smart Combo Builder                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  VERIFICATION LAYER (V7.0)                              │   │
│  │  • Fact-check with Tavily/Perplexity                    │   │
│  │  • Player impact validation                             │   │
│  │  • Score adjustment / Market change                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  TELEGRAM ALERTS (Score >= 8.6 - Premium Quality)        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 📈 Performance

- **Coverage**: 30+ leagues, tiered scanning
- **Alerts**: ~1-2 premium alerts/day (threshold 8.6 - Premium Quality)
- **Quality**: "Cream of the Crop" signals only (dynamic 7.5-9.0 range)
- **Lookahead**: 96 hours (4 days)
- **Cycle**: Every 120 minutes
- **Self-Learning**: Weights auto-adjust based on CLV + results
- **ROI Accuracy**: Enhanced with `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at` tracking (V8.3)

## 📁 Project Structure

```
earlybird/
├── src/
│   ├── ingestion/              # Data fetching
│   │   ├── data_provider.py    # FotMob integration
│   │   ├── tavily_provider.py  # Tavily AI Search ⭐ V7.0
│   │   ├── tavily_key_rotator.py
│   │   ├── tavily_budget.py
│   │   ├── tavily_query_builder.py
│   │   ├── deepseek_intel_provider.py  # DeepSeek + Brave ⭐ V6.0
│   │   ├── perplexity_provider.py      # Perplexity fallback
│   │   ├── search_provider.py  # Brave + DDG + Serper
│   │   ├── ingest_fixtures.py  # Odds API
│   │   ├── league_manager.py   # Tier system
│   │   ├── weather_provider.py # Open-Meteo
│   │   └── opportunity_radar.py # Opportunity Radar (V2.0) ⭐ NEW
│   ├── processing/             # News orchestration
│   │   ├── news_hunter.py      # Multi-tier aggregator
│   │   ├── telegram_listener.py
│   │   └── sources_config.py
│   ├── analysis/               # AI analysis
│   │   ├── analyzer.py         # DeepSeek triangulation + Tactical Veto (V8.0)
│   │   ├── verification_layer.py  # Alert fact-checking ⭐ V7.0
│   │   ├── clv_tracker.py      # CLV monitoring ⭐ V5.0
│   │   ├── market_intelligence.py  # RLM + Steam Move (V1.1)
│   │   ├── fatigue_engine.py   # Fatigue V2.0
│   │   ├── biscotto_engine.py  # Biscotto V2.0
│   │   ├── math_engine.py      # Poisson + Kelly
│   │   ├── optimizer.py        # Strategy weights
│   │   ├── settler.py          # Result verification
│   │   ├── reporter.py         # CSV export
│   │   ├── player_intel.py     # B-Team Detection (V2.0) ⭐ NEW
│   │   ├── news_scorer.py      # News Intelligence ⭐ NEW
│   │   ├── squad_analyzer.py   # Squad analysis
│   │   └── image_ocr.py        # Telegram Intelligence (OCR) ⭐ NEW
│   ├── services/               # Background services
│   │   ├── intelligence_router.py  # DeepSeek + Tavily routing (V7.0) ⭐ NEW
│   │   ├── browser_monitor.py  # Playwright monitoring
│   │   ├── news_radar.py       # Autonomous hunter
│   │   ├── twitter_intel_cache.py  # Tweet caching ⭐ V7.0
│   │   └── tweet_relevance_filter.py
│   ├── alerting/               # Notifications
│   │   ├── notifier.py         # Telegram alerts
│   │   └── health_monitor.py   # System health
│   ├── database/               # SQLite models
│   │   ├── models.py           # Match, NewsLog, TeamAlias
│   │   ├── db.py               # Connection management
│   │   ├── migration.py        # Auto-migration
│   │   ├── migration_v73.py    # V7.3 temporal reset migration
│   │   └── migration_v83_odds_fix.py  # V8.3 odds tracking migration
│   ├── utils/                  # Utilities
│   │   ├── discovery_queue.py  # Thread-safe queue ⭐ V6.0
│   │   ├── parallel_enrichment.py  # FotMob parallel ⭐ V6.0
│   │   ├── freshness.py        # Centralized freshness tags
│   │   ├── article_reader.py    # Deep Dive on Demand ⭐ V8.0 NEW
│   │   ├── smart_cache.py
│   │   ├── http_client.py
│   │   └── ai_parser.py
│   ├── main.py                 # Pipeline principale
│   ├── run_bot.py              # Telegram bot
│   ├── launcher.py             # Process orchestrator (V3.7)
│   └── deploy_v83_odds_fix.py  # V8.3 odds tracking deployment
├── tests/                      # 75+ test files
├── config/                     # Settings
├── data/                       # SQLite DB + optimizer weights
├── temp/                       # CSV reports (auto-cleaned)
├── go_live.py                  # Main launcher (V3.1)
├── run_telegram_monitor.py     # Telegram scraper
├── run_news_radar.py           # News radar launcher
├── setup_vps.sh                # VPS setup
├── run_forever.sh              # VPS watchdog (V3.3)
└── start_system.sh             # Sistema Completo con Test Monitor (V7.1)
```

## 🔄 Changelog

### V8.3 (Current) - Learning Loop Integrity Fix ⭐ NEW
- **Odds Tracking Columns**: Added `odds_at_alert`, `odds_at_kickoff`, `alert_sent_at` for accurate ROI calculations
- **Database Migration**: `migration_v83_odds_fix.py` for schema updates
- **Tactical Veto (V8.0)**: Applied when market signals contradict tactical reality
- **B-Team Detection (V2.0)**: Financial Intelligence for detecting B-Team/Reserves lineups
- **BTTS Intelligence (V4.1)**: Head-to-Head BTTS Trend Analysis
- **Motivation Intelligence (V4.2)**: Title race, relegation, dead rubber analysis
- **Twitter Intel (V7.0)**: Cached Twitter Intel for search grounding
- **News Intelligence**: News scoring and aggregation
- **Telegram Intelligence**: Squad image scraping and OCR analysis
- **Opportunity Radar (V2.0)**: Narrative-First Intelligence Scanner
- **Intelligence Router (V7.0)**: Routes to DeepSeek (primary) with Tavily pre-enrichment
- **Market Intelligence (V1.1)**: Steam Move, Reverse Line, News Decay
- **V7.3**: Added `last_alert_time` column for temporal reset
- **V5.3**: Odds type conversion and validation fixes
- **V5.2**: Input validation and edge case handling in optimizer
- **V7.2**: Signal handling fixes in news_radar
- **V8.0**: asyncio.run() instead of deprecated get_event_loop()

### V8.0
- **Circuit Breaker**: Auto-fallback Tavily → Brave → DDG dopo failures
- **Native News Parameters**: Tavily `topic="news"` + `days` per filtering ottimale
- **Budget Status API**: Monitoring usage per componente

### V7.0
- **Tavily AI Search**: 7 API keys rotation, caching, budget management
- **Verification Layer**: Alert fact-checking con multi-site queries
- **Intelligence Router V7.0**: DeepSeek + Tavily pre-enrichment
- **Discovery Queue**: Thread-safe communication per Browser Monitor

### V6.0
- **DeepSeek Primary**: Sostituisce Gemini come provider principale
- **Parallel Enrichment**: FotMob calls parallelizzate (~15s → ~4s)
- **Twitter Intel Cache**: Sostituisce broken site:twitter.com search

### V5.0
- **CLV Tracker**: Closing Line Value monitoring e reporting
- **Sample Size Guards**: FROZEN/WARMING/ACTIVE states per optimizer
- **Sortino-Based Optimization**: Penalizza solo downside risk

### V4.3
- **Fatigue Engine V2.0**: Exponential decay + squad depth + late-game prediction
- **Biscotto Engine V2.0**: Z-Score + end-of-season + mutual benefit

### V8.0 (Current) ⭐ NEW
- **Doppio Ciclo API Tavily**: Rotazione intelligente con reset mensile prima del fallback
  - Fino a 14000 chiamate/mese invece di 7000
  - Gestione automatica del cambio mese
  - Tracking dei cicli completati
  - File: `src/ingestion/tavily_key_rotator.py`
  - Test: `tests/test_tavily_double_cycle.py`
- **Deep Dive on Demand**: Upgrade shallow search results to full article content when high-value keywords detected
- **Article Reader Module**: `src/utils/article_reader.py` con Trafilatura per estrazione testo completo
- **Integrazione NewsHunter**: Configurazione `DEEP_DIVE_*` in `src/processing/news_hunter.py`
- **Keyword Trigger**: Multi-language (English, Italian, Spanish, Portuguese, Polish, Turkish)
- **Performance**: Max 3 deep dive per search, timeout 15s, snippet threshold 500 chars
- **League-Specific Home Advantage**: HA dinamico per lega (0.22-0.40)
- **News Decay Adattivo**: λ per tier di lega

### V4.2
- **Reverse Line Movement**: Smart money detection (65%+ threshold)
- **Steam Move Detection**: Drop >5% in 15 minuti
- **Odds Snapshots Table**: Tracking storico quote

### V4.1
- **Browser Monitor**: Playwright + DeepSeek AI monitoring
- **3-Tier Intelligence**: TIER 0 → TIER 1 → TIER 2

### V3.8
- **SQLite WAL Mode**: Write-Ahead Logging per concorrenza
- **DDG Package Rename**: Migrato a `ddgs`

---

*EarlyBird V8.3 - Learning Loop Integrity Fix*
*Powered by DeepSeek V3 + Tavily AI Search + Verification Layer + CLV Tracking + Tactical Veto + B-Team Detection*
