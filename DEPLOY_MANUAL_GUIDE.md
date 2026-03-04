# 🦅 EarlyBird VPS Deployment - Guida Manuale

## 📋 Panoramica

Questa guida ti guiderà attraverso il processo di deploy del bot EarlyBird sulla VPS `31.220.73.226`.

## ✅ Prerequisiti

- File `earlybird_deploy.zip` creato (294MB)
- Accesso SSH alla VPS come root
- Password SSH per l'utente root

---

## 🚀 Passo 1: Connessione alla VPS

Apri un terminale e connettiti alla VPS:

```bash
ssh root@31.220.73.226
```

Inserisci la password quando richiesto.

---

## 📦 Passo 2: Preparazione Directory

Una volta connesso alla VPS, crea la directory per il bot:

```bash
mkdir -p /root/earlybird
cd /root/earlybird
```

---

## 📤 Passo 3: Trasferimento File Zip

In un **NUOVO terminale** (sul tuo computer locale), trasferisci il file zip sulla VPS:

```bash
scp earlybird_deploy.zip root@31.220.73.226:/root/earlybird/
```

Inserisci la password quando richiesto.

---

## 📂 Passo 4: Estrazione File

Torna al terminale della VPS ed estrai il file zip:

```bash
cd /root/earlybird
unzip -o earlybird_deploy.zip
rm earlybird_deploy.zip
```

---

## ⚙️ Passo 5: Configurazione File .env

Verifica se il file `.env` esiste:

```bash
cd /root/earlybird
ls -la .env
```

Se non esiste, crealo dal template:

```bash
cp .env.template .env
nano .env  # o usa vim
```

Aggiungi le tue API keys nel file `.env`:
- `ODDS_API_KEY`
- `OPENROUTER_API_KEY`
- `BRAVE_API_KEY`
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SUPABASE_URL` (opzionale)
- `SUPABASE_KEY` (opzionale)

Salva e esci dall'editor (Ctrl+O, Enter, Ctrl+X per nano).

---

## 🔐 Passo 6: Setup Sessione Telegram (Opzionale ma Raccomandato)

Per il 100% di funzionalità (accesso ai canali privati):

```bash
cd /root/earlybird
python3 setup_telegram_auth.py
```

Quando richiesto:
1. Inserisci il numero: `+393703342314`
2. Inserisci il codice OTP ricevuto su Telegram
3. Se richiesto, inserisci la password 2FA

Il file `data/earlybird_monitor.session` verrà creato automaticamente.

**Nota:** Senza la sessione Telegram, il monitor funzionerà al 50% (solo canali pubblici).

---

## 🛠️ Passo 7: Setup Dipendenze di Sistema

Esegui lo script di setup:

```bash
cd /root/earlybird
bash setup_vps.sh
```

Questo script installerà:
- Python3 e venv
- Tesseract OCR
- Playwright e Chromium
- Docker (per Redlib)
- Altre dipendenze di sistema

**Nota:** Questo processo potrebbe richiedere 10-15 minuti.

---

## 🚀 Passo 8: Avvio del Bot

Esegui lo script di avvio:

```bash
cd /root/earlybird
bash start_system.sh
```

Questo script:
1. Esegue un pre-flight check
2. Sincronizza la memoria AI
3. Avvia il bot in tmux con dashboard split-screen

Il bot è ora in esecuzione!

---

## 📊 Passo 9: Verifica Funzionamento

Per verificare che il bot sia in esecuzione:

```bash
# Controlla i processi
ps aux | grep python

# Visualizza i log
tail -f /root/earlybird/earlybird.log
```

Premi `Ctrl+C` per uscire dal log viewer.

---

## 🖥️ Gestione del Bot

### Visualizzare la Dashboard tmux

```bash
tmux attach -t earlybird
```

### Uscire dalla Dashboard tmux

Premi `Ctrl+B`, poi `d`

### Arrestare il Bot

```bash
tmux kill-session -t earlybird
```

### Riavviare il Bot

```bash
cd /root/earlybird
bash start_system.sh
```

---

## 📝 Comandi Utili

### Connessione VPS
```bash
ssh root@31.220.73.226
```

### Directory del Bot
```bash
cd /root/earlybird
```

### Visualizzare Log
```bash
tail -f /root/earlybird/earlybird.log
tail -f /root/earlybird/logs/telegram_monitor.log
```

### Eseguire Test
```bash
cd /root/earlybird
make test-unit
```

### Verificare API
```bash
cd /root/earlybird
make check-apis
```

### Pulizia Log
```bash
cd /root/earlybird
make clean
```

---

## 🔧 Troubleshooting

### Il bot non parte

1. Verifica che il file `.env` sia configurato correttamente:
   ```bash
   cat /root/earlybird/.env
   ```

2. Verifica le API keys:
   ```bash
   cd /root/earlybird
   make check-apis
   ```

3. Controlla i log per errori:
   ```bash
   tail -100 /root/earlybird/earlybird.log
   ```

### Errori di permessi

Assicurati che gli script siano eseguibili:
```bash
cd /root/earlybird
chmod +x start_system.sh run_forever.sh go_live.py
```

### Sessione Telegram scaduta

Se ricevi errori di sessione Telegram:
```bash
cd /root/earlybird
rm data/earlybird_monitor.session
python3 setup_telegram_auth.py
```

### Problemi con Playwright

Reinstalla Playwright:
```bash
cd /root/earlybird
source venv/bin/activate
python -m playwright install chromium
python -m playwright install-deps chromium
```

---

## 📚 Architettura del Sistema

Il bot è composto da 4 processi principali gestiti dal Launcher:

1. **Main Pipeline** - Analisi delle partite e generazione di alert
2. **News Radar** - Monitoraggio autonomo 24/7 delle news
3. **Telegram Monitor** - Monitoraggio canali Telegram con OCR
4. **Test Monitor** - Monitoraggio dello stato del sistema

Tutti i processi sono gestiti con auto-restart e backoff esponenziale.

---

## 🎯 Componenti Principali

### Intelligence Router
- Primary: DeepSeek AI
- Pre-enrichment: Tavily search
- Fallback: Perplexity → Cache → Default

### 12+ Intelligence Features
- Market Intelligence (Steam Move, Reverse Line, News Decay)
- Tactical Veto
- B-Team Detection
- BTTS Intelligence
- Motivation Intelligence
- Twitter Intel
- News Intelligence
- Telegram Intelligence (OCR)
- Opportunity Radar
- E altro...

### Data Providers
- Tavily, Perplexity, Brave, DDG, DeepSeek
- Odds API
- FotMob, Sporting
- Supabase (continental orchestration)

---

## ✨ Note Importanti

1. **File .env**: Non condividere mai il file `.env` con chiunque. Contiene API keys sensibili.

2. **Sessione Telegram**: Mantieni una copia di backup del file `data/earlybird_monitor.session`.

3. **Log Files**: I log possono diventare grandi. Esegui regolarmente `make clean` per pulirli.

4. **Aggiornamenti**: Per aggiornare il bot, ripeti i passi 3-4 con il nuovo file zip.

5. **Backup**: Fai regolarmente backup del database e del file `.env`.

---

## 🆘 Supporto

Se riscontri problemi:
1. Controlla i log: `tail -f /root/earlybird/earlybird.log`
2. Esegui i test: `cd /root/earlybird && make test-unit`
3. Verifica le API: `cd /root/earlybird && make check-apis`

---

**🎉 Deploy completato! Il bot EarlyBird è ora in esecuzione sulla VPS.**
