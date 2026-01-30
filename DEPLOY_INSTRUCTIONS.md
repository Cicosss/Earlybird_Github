# 🦅 EarlyBird V7.0 - Deploy Instructions

Guida definitiva per il deploy su Ubuntu VPS.

**Novità V8.7:**
- 🎯 **Elite Quality Filtering**: Soglie alzate (Standard: 9.0, Radar: 7.5) per ridurre volume e aumentare qualità
- Tavily AI Search: 7 API keys con rotazione automatica (7000 chiamate/mese)
- Integrazione Tavily in: Intelligence Router, News Radar, Browser Monitor, Telegram Monitor, Settler, CLV Tracker, Twitter Intel Recovery
- Circuit Breaker e fallback automatico a Brave/DDG

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
- [ ] API keys verificate (`python src/utils/check_apis.py`)

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
zip -r earlybird_v72_YYYYMMDD.zip \
  src/ config/ tests/ .env requirements.txt pytest.ini \
  run_forever.sh run_fullstack.sh run_tests_monitor.sh \
  start_system.sh setup_vps.sh \
  setup_telegram_auth.py show_errors.py \
  README.md ARCHITECTURE.md DEPLOY_INSTRUCTIONS.md \
  -x "*.pyc" -x "*__pycache__*" -x "*.session" -x "*.log" -x "*.db" -x "venv/*" -x ".venv/*"
```

### Upload su VPS
```bash
scp earlybird_v72_YYYYMMDD.zip root@YOUR_VPS_IP:/root/
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
unzip /root/earlybird_v72_YYYYMMDD.zip
chmod +x setup_vps.sh
./setup_vps.sh
```

> ⏱️ **Nota:** Lo script impiega ~3-5 minuti per scaricare Chromium e le dipendenze.

---

## 3️⃣ Configurazione

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

# AI (OpenRouter)
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=deepseek/deepseek-chat-v3-0324

# Tavily AI Search (7 keys - 1000 calls each = 7000/month)
# Keys rotate automatically when quota exhausted
TAVILY_API_KEY_1=tvly-your-key-1
TAVILY_API_KEY_2=tvly-your-key-2
TAVILY_API_KEY_3=tvly-your-key-3
TAVILY_API_KEY_4=tvly-your-key-4
TAVILY_API_KEY_5=tvly-your-key-5
TAVILY_API_KEY_6=tvly-your-key-6
TAVILY_API_KEY_7=tvly-your-key-7
TAVILY_ENABLED=true

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
python src/utils/check_apis.py
```

---

## 4️⃣ Inizializzazione

### Database
```bash
source venv/bin/activate
python3 -c "from src.database.db import init_db; init_db(); print('✅ Database inizializzato')"
```

### Autenticazione Telegram (solo prima volta)
```bash
python3 setup_telegram_auth.py
```
> Segui le istruzioni: inserisci numero di telefono → codice ricevuto su Telegram → (eventuale 2FA)

**Nota:** La session viene salvata come `earlybird_monitor.session` per evitare conflitti con il bot.

---

## 5️⃣ Avvio Sistema

### Metodo consigliato (tmux con Test Monitor) ⭐

```bash
./start_system.sh
```

Questo comando:
1. Esegue test pre-avvio (se falliscono, il bot non parte)
2. Apre tmux con due pannelli affiancati:
   - **Sinistra**: Bot principale (run_forever.sh)
   - **Destra**: Test Monitor (esegue test ogni 5 minuti)

```
┌─────────────────────────────┬─────────────────────────────┐
│                             │                             │
│   🦅 BOT PRINCIPALE         │   🧪 TEST MONITOR           │
│                             │                             │
│   Pipeline + News + Alerts  │   Validatori + Regression   │
│                             │   + E2E ogni 5 minuti       │
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

Il launcher (`src/launcher.py`) gestisce 4 processi con auto-restart:

| Processo | Script | Descrizione |
|----------|--------|-------------|
| Pipeline Principale | `src/main.py` | Odds + News + Analysis |
| Telegram Bot | `src/run_bot.py` | Comandi utente |
| Telegram Monitor | `run_telegram_monitor.py` | Scraper canali insider |
| **News Radar** | `run_news_radar.py` | Hunter autonomo 24/7 |

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

---

## 📋 Checklist Deploy

- [ ] ZIP creato con `.env` incluso
- [ ] Upload su VPS completato
- [ ] `setup_vps.sh` eseguito senza errori
- [ ] API keys verificate (`check_apis.py`)
- [ ] Database inizializzato
- [ ] Telegram autenticato (se necessario)
- [ ] Test pre-avvio passano (`pytest tests/test_validators.py`)
- [ ] Sistema avviato con `./start_system.sh`
- [ ] Entrambi i pannelli tmux funzionanti
- [ ] Heartbeat ricevuto su Telegram

---
