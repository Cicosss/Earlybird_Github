---
inclusion: manual
---

# 📦 DEPLOY MEMO

## Quando crei lo zip per il deploy VPS:

### ✅ INCLUDI SEMPRE:
- `.env` (contiene le API keys!)
- `src/`
- `config/`
- `requirements.txt`
- `setup_vps.sh`
- `run_forever.sh`
- `run_fullstack.sh`
- `setup_telegram_auth.py`
- `show_errors.py`
- `README.md`
- `ARCHITECTURE.md`

### ❌ ESCLUDI:
- `*.pyc`
- `__pycache__/`
- `*.session`
- `*.log`
- `*.db`
- `venv/`
- `.venv/`

### 🔑 Comando zip completo:
```bash
zip -r earlybird_v42_YYYYMMDD.zip \
  src/ config/ .env requirements.txt \
  run_forever.sh run_fullstack.sh setup_vps.sh \
  setup_telegram_auth.py show_errors.py \
  README.md ARCHITECTURE.md \
  -x "*.pyc" -x "*__pycache__*" -x "*.session" -x "*.log" -x "*.db" -x "venv/*" -x ".venv/*"
```

### 📤 Upload su VPS:
```bash
scp earlybird_v42_YYYYMMDD.zip root@YOUR_VPS_IP:/root/
```
