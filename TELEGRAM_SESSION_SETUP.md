# 📡 Creazione Sessione Telegram Monitor - Istruzioni Complete

## 🎯 Obiettivo
Attivare il Telegram Monitor al 100% con funzionalità completa (accesso a canali privati per insider intel).

## 📋 Stato Attuale
- ✅ **Bot Token**: Funzionante al 50% (canali pubblici)
- ⚠️ **Sessione Utente**: Mancante (serve per accesso a canali privati)
- ✅ **Fix Crash Loop**: Applicato (il monitor non crasha più)

## 🔑 Credenziali Disponibili
- **TELEGRAM_API_ID**: 36109304
- **TELEGRAM_API_HASH**: 2c1da5478a315902ad4dad5af9577f77
- **TELEGRAM_TOKEN**: 8435443549:AAHcNVXxbpusiISax1RGpGMEyLsS4HQCweo
- **TELEGRAM_CHAT_ID**: 890390162
- **Numero Telefono**: +393703342314

## 📝 Istruzioni per Creare la Sessione (100%)

### Step 1: Esegui Localmente sul Tuo Computer

```bash
# Clona il repository (se non già fatto)
git clone <repository-url>
cd Earlybird_Github

# Attiva l'ambiente virtuale
source venv/bin/activate  # oppure python3 -m venv venv && source venv/bin/activate

# Installa le dipendenze (se necessario)
pip install -r requirements.txt
```

### Step 2: Esegui lo Script di Setup

```bash
python setup_telegram_auth.py
```

### Step 3: Inserisci le Credenziali Quando Richiesto

Lo script ti chiederà:
1. **Phone number**: Inserisci `+393703342314`
2. **Verification code**: Controlla il tuo telefono Telegram e inserisci il codice ricevuto
3. **Two-FA password** (se abilitato): Inserisci la password di verifica

### Step 4: Verifica Creazione Sessione

Se tutto va bene, vedrai:
```
✅ SUCCESS! Session file created: earlybird_monitor.session
👤 Logged in as: [Nome Cognome] (@username)
```

Il file `earlybird_monitor.session` verrà creato nella directory corrente.

### Step 5: Carica la Sessione sulla VPS

```bash
# Copia il file sulla VPS usando SCP
scp earlybird_monitor.session user@vps-ip:/path/to/Earlybird_Github/data/

# Oppure, se hai accesso SSH alla VPS:
# 1. Copia il contenuto del file sessione
cat earlybird_monitor.session

# 2. Crea il file sulla VPS
ssh user@vps-ip
cd /path/to/Earlybird_Github/data/
nano earlybird_monitor.session
# Incolla il contenuto e salva (Ctrl+O, Enter, Ctrl+X)
```

### Step 6: Riavvia il Telegram Monitor sulla VPS

```bash
# Connettiti alla VPS
ssh user@vps-ip
cd /path/to/Earlybird_Github

# Riavvia il sistema (oppure riavvia solo il monitor)
tmux attach -t earlybird
# Ctrl+C sul pannello del monitor per riavviarlo
```

## ✅ Verifica Funzionamento

Una volta caricata la sessione, il log dovrebbe mostrare:
```
✅ Client Telegram connesso (User Session)
```

Invece di:
```
⚠️ File di sessione Telegram mancante o corrotto
🔄 Tentativo fallback a Bot Token...
✅ Client Telegram connesso (Bot Token - funzionalità limitata)
```

## 🔄 Fallback Automatico (Già Implementato)

Il codice [`run_telegram_monitor.py`](run_telegram_monitor.py:266) ha già un sistema di fallback:

1. **Priorità 1**: Sessione Utente (100% - canali privati + pubblici)
2. **Priorità 2**: Bot Token (50% - solo canali pubblici)
3. **Priorità 3**: Modalità IDLE con retry ogni 5 minuti

Questo significa che anche senza la sessione utente, il monitor funziona al 50% e non crasha.

## 📊 Differenze Funzionalità

| Funzionalità | Sessione Utente (100%) | Bot Token (50%) |
|--------------|------------------------|-----------------|
| Canali Pubblici | ✅ | ✅ |
| Canali Privati | ✅ | ❌ |
| Immagini Formazioni | ✅ | ✅ |
| OCR Analysis | ✅ | ✅ |
| Insider Intel Completa | ✅ | ⚠️ Limitata |

## 🚨 Note Importanti

1. **Non condividere il file sessione**: Contiene token di autenticazione sensibili
2. **Backup della sessione**: Mantieni una copia del file sessione localmente
3. **Session expiration**: Le sessioni Telegram possono scadere dopo inattività prolungata
4. **Multi-device**: Se usi Telegram su altri dispositivi, la sessione potrebbe invalidarsi

## 📞 Supporto

Se riscontri problemi:
- Verifica che il numero sia corretto: `+393703342314`
- Verifica che le credenziali API siano corrette nel file `.env`
- Controlla i log: `tail -f logs/telegram_monitor.log`

---

**Documento creato il**: 2026-02-10
**Versione**: V9.5
