#!/bin/bash
# EarlyBird Master Deploy V12.4
# Automated VPS Deployment & Restoration
set -e

VPS_IP="31.220.73.226"
VPS_USER="root"
ZIP_FILE="earlybird_deploy.zip"

echo "========================================="
echo " 🦅 EARLYBIRD BOT - DEPLOYMENT AUTOMATICO "
echo "========================================="

echo "[1/4] Trasferimento del file $ZIP_FILE alla VPS..."
echo "--> Preparati ad inserire la password della VPS:"
scp $ZIP_FILE $VPS_USER@$VPS_IP:/root/

echo ""
echo "[2/4] Connessione alla VPS per eseguire il setup (Reset ambiente, Backup, Avvio)..."
echo "--> Preparati ad inserire la password della VPS di nuovo:"

ssh -t $VPS_USER@$VPS_IP << 'EOF'
  echo "[VPS] Inizio operazioni..."
  
  echo "[VPS] 1. Backup file critici (.env e sessione Telegram)..."
  cp earlybird/.env ~/.env_backup 2>/dev/null || echo "Nessun .env da backuppare."
  cp earlybird/data/earlybird_monitor.session ~/earlybird_monitor.session_backup 2>/dev/null || echo "Nessuna sessione Telegram trovata."

  echo "[VPS] 2. Stop processi e rimozione vecchia repository..."
  tmux kill-session -t earlybird 2>/dev/null || true
  pkill -9 -f python || true
  rm -rf earlybird

  echo "[VPS] 3. Estrazione nuova versione..."
  unzip -q earlybird_deploy.zip -d earlybird
  cd earlybird

  echo "[VPS] 4. Esecuzione Setup VPS (installazione dipendenze)..."
  chmod +x setup_vps.sh
  ./setup_vps.sh

  echo "[VPS] 5. Ripristino dei file critici (.env e data)..."
  if [ -f ~/.env_backup ]; then
      cp ~/.env_backup .env
      echo "✅ .env ripristinato."
  else
      echo "⚠️ Attenzione: Nessun file .env ripristinato!"
  fi
  
  mkdir -p data
  if [ -f ~/earlybird_monitor.session_backup ]; then
      cp ~/earlybird_monitor.session_backup data/earlybird_monitor.session
      echo "✅ Sessione Telegram ripristinata."
  fi

  echo "[VPS] 6. Attivazione environment e Check APIs..."
  source venv/bin/activate
  make check-apis

  echo "[VPS] 7. Esecuzione Migrazioni..."
  make migrate

  echo "[VPS] 8. Avvio definitivo del sistema..."
  chmod +x start_system.sh
  ./start_system.sh || true
EOF

echo ""
echo "====================================="
echo "✅ DEPLOY E AVVIO COMPLETATI!"
echo "====================================="
echo "[3/4] Ora ti collegherai alla console per vedere il bot in azione."
echo "--> Preparati ad inserire la password per visualizzare TMUX:"
sleep 2

ssh -t $VPS_USER@$VPS_IP "tmux attach-session -t earlybird"

echo "Sessione conclusa, premi INVIO per uscire..."
read
