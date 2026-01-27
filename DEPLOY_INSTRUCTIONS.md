# 🦅 EarlyBird V7.0 - Deploy Instructions + Backdoor

Guida definitiva per il deploy su Ubuntu VPS con sistema di backdoor sicuro per controllo remoto.

**Novità V7.0:**
- Tavily AI Search: 7 API keys con rotazione automatica (7000 chiamate/mese)
- Integrazione Tavily in: Intelligence Router, News Radar, Browser Monitor, Telegram Monitor, Settler, CLV Tracker, Twitter Intel Recovery
- Circuit Breaker e fallback automatico a Brave/DDG
- **🔐 Backdoor System**: SSH reverse tunnel con controllo remoto sicuro

---

## 🔐 SISTEMA BACKDOOR (V7.1)

Il sistema backdoor fornisce controllo remoto sicuro sulla VPS con privilegi di amministratore.

### Architettura

**Componenti:**
- **SSH Reverse Tunnel**: Connessione persistente VPS → Locale
- **UFW Firewall**: Whitelist IP per sicurezza massima
- **Systemd Service**: Auto-restart e monitoring
- **Audit Logger**: Logging completo attività
- **Command Control**: Whitelist comandi consentiti

### Configurazione

**Target VPS:**
- IP: `31.220.73.226`
- OS: Ubuntu 24.04 LTS
- Location: Hub Europe

**Client Locale:**
- IP: `93.40.209.20` (IPv4) + `2001:b07:6456:fb49:a52c:ae39:6783:52ce` (IPv6)
- Porta: `2222` (default)
- Accesso: `root`

### Deploy con Backdoor

#### 1. Deploy Completo (EarlyBird + Backdoor)
```bash
./deploy_to_vps_with_backdoor.sh --full
```

#### 2. Solo Backdoor (se EarlyBird già installato)
```bash
./deploy_to_vps_with_backdoor.sh --backdoor
```

#### 3. Solo EarlyBird (senza backdoor)
```bash
./deploy_to_vps_with_backdoor.sh
```

### Connessione Backdoor

**Dal tuo locale:**
```bash
ssh -p 2222 root@localhost
```

**Diretto alla VPS (tradizionale):**
```bash
ssh -i ~/.ssh/id_rsa root@31.220.73.226
```

### Comandi Backdoor

#### Status e Monitoring
```bash
# Status servizio backdoor
systemctl status earlybird-backdoor

# Log in tempo reale
journalctl -u earlybird-backdoor -f

# Audit report ultime 24 ore
python3 /root/earlybird/audit_logger.py report 24

# Health check completo
python3 /root/earlybird/audit_logger.py health
```

#### Gestione Servizio
```bash
# Riavvia backdoor
systemctl restart earlybird-backdoor

# Ferma backdoor
systemctl stop earlybird-backdoor

# Abilita auto-start
systemctl enable earlybird-backdoor
```

#### Comandi EarlyBird (via backdoor)
```bash
# Status sistema EarlyBird
systemctl status earlybird*

# Riavvia EarlyBird
systemctl restart earlybird*

# Log principali
tail -f /root/earlybird/earlybird.log

# Docker containers
docker ps
docker logs redlib

# Monitoraggio risorse
df -h
free -h
top -bn1
```

### Sicurezza

#### Firewall UFW
```bash
# Status firewall
ufw status verbose

# IP whitelist (solo i tuoi IP)
ufw status | grep "93.40.209.20"

# Log firewall
ufw logging on
tail -f /var/log/ufw.log
```

#### Controllo Comandi

**Comandi Consentiti:**
- `systemctl status earlybird*`
- `systemctl restart earlybird*`
- `docker ps`, `docker logs redlib`
- `tail -f earlybird.log`
- `ps aux | grep python`
- `df -h`, `free -h`, `top -bn1`
- `netstat -tlnp`, `ufw status`
- `journalctl -u earlybird*`

**Comandi Bloccati:**
- `rm -rf /`, `chmod 777`
- `useradd`, `usermod`, `passwd`
- `sudo -i`, `su -`
- `dd if=`, `mkfs`, `fdisk`
- `reboot`, `shutdown`

### Audit e Logging

**Log Files:**
- `/var/log/earlybird/backdoor.log` - Audit completo
- `/var/log/earlybird/backdoor_audit.log` - Eventi dettagliati
- `journalctl -u earlybird-backdoor` - Systemd logs

**Report Automatici:**
```bash
# Report ultime 24 ore
python3 /root/earlybird/audit_logger.py report 24

# Report ultime 12 ore
python3 /root/earlybird/audit_logger.py report 12

# Report ultima ora
python3 /root/earlybird/audit_logger.py report 1
```

### Troubleshooting Backdoor

#### Connessione Fallita
```bash
# Controlla servizio
systemctl status earlybird-backdoor

# Controlla tunnel
pgrep -f "ssh -R 2222:localhost:22"

# Controlla firewall
ufw status

# Riavvia tutto
systemctl restart earlybird-backdoor
```

#### Tunnel Down
```bash
# Verifica processo SSH
ps aux | grep "ssh -R"

# Controlla log per errori
journalctl -u earlybird-backdoor --since "1 hour ago"

# Riavvia manualmente
systemctl restart earlybird-backdoor
```

#### Firewall Bloccante
```bash
# Verifica regole
ufw status numbered

# Aggiungi IP se mancante
ufw allow from 93.40.209.20 to any port 22
ufw allow from 2001:b07:6456:fb49:a52c:ae39:6783:52ce to any port 22

# Reload firewall
ufw reload
```

### File di Configurazione

**File Principali:**
- `/root/earlybird/setup_backdoor_ubuntu24.sh` - Setup script
- `/root/earlybird/backdoor_config.sh` - Configurazione
- `/root/earlybird/audit_logger.py` - Audit system
- `/etc/systemd/system/earlybird-backdoor.service` - Systemd service

**Modifica Configurazione:**
```bash
# Edit configurazione
nano /root/earlybird/backdoor_config.sh

# Reload dopo modifica
systemctl restart earlybird-backdoor
```

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
unzip /root/earlybird_v42_YYYYMMDD.zip
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

### 🔐 Checklist Backdoor

- [ ] `./deploy_to_vps_with_backdoor.sh --full` eseguito
- [ ] Servizio `earlybird-backdoor` attivo
- [ ] Firewall UFW configurato con whitelist IP
- [ ] Connessione backdoor testata: `ssh -p 2222 root@localhost`
- [ ] Audit logging funzionante
- [ ] Comandi consentiti/bloccati verificati

### 🚀 Quick Start Backdoor

```bash
# 1. Deploy completo
./deploy_to_vps_with_backdoor.sh --full

# 2. Test connessione
ssh -p 2222 root@localhost

# 3. Verifica status
systemctl status earlybird-backdoor
journalctl -u earlybird-backdoor -f
```

---
