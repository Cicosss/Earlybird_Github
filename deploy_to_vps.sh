#!/bin/bash
# ============================================
# EarlyBird VPS Deployment Script
# ============================================

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

VPS_IP="31.220.73.226"
VPS_USER="root"
VPS_DIR="/root/earlybird"
ZIP_FILE="earlybird_deploy.zip"

echo -e "${CYAN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 EarlyBird VPS Deployment Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# Step 1: Check if zip file exists
echo -e "${YELLOW}[1/10] Verificando file zip...${NC}"
if [ ! -f "$ZIP_FILE" ]; then
    echo -e "${RED}❌ File $ZIP_FILE non trovato!${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ File $ZIP_FILE trovato ($(ls -lh $ZIP_FILE | awk '{print $5}'))${NC}"
echo ""

# Step 2: Connect to VPS and prepare directory
echo -e "${YELLOW}[2/10] Connessione alla VPS e preparazione directory...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "mkdir -p $VPS_DIR && echo 'Directory preparata con successo'"
echo -e "${GREEN}   ✅ Directory preparata${NC}"
echo ""

# Step 3: Transfer zip file to VPS
echo -e "${YELLOW}[3/10] Trasferimento file zip sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
scp "$ZIP_FILE" "$VPS_USER@$VPS_IP:$VPS_DIR/"
echo -e "${GREEN}   ✅ File trasferito${NC}"
echo ""

# Step 4: Extract zip file on VPS
echo -e "${YELLOW}[4/10] Estrazione file zip sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && unzip -o $ZIP_FILE && rm $ZIP_FILE && echo 'File estratto con successo'"
echo -e "${GREEN}   ✅ File estratto${NC}"
echo ""

# Step 5: Install Python dependencies
echo -e "${YELLOW}[5/10] Installazione dipendenze Python...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Questo potrebbe richiedere alcuni minuti...${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && pip3 install -r requirements.txt"
echo -e "${GREEN}   ✅ Dipendenze Python installate${NC}"
echo ""

# Step 6: Install Playwright browsers
echo -e "${YELLOW}[6/10] Installazione browser Playwright...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Questo potrebbe richiedere alcuni minuti...${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 -m playwright install chromium --with-deps"
echo -e "${GREEN}   ✅ Browser Playwright installati${NC}"
echo ""

# Step 7: Create .env file if not exists
echo -e "${YELLOW}[7/10] Verifica file .env...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && if [ ! -f .env ]; then cp .env.template .env && echo 'File .env creato da template'; else echo 'File .env esistente'; fi"
echo -e "${GREEN}   ✅ File .env verificato${NC}"
echo ""

# Step 8: Run database migration
echo -e "${YELLOW}[8/10] Esecuzione migration database...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 -m src.database.migration_v13_complete_schema"
echo -e "${GREEN}   ✅ Migration database completata${NC}"
echo ""

# Step 9: Setup Telegram session (optional)
echo -e "${YELLOW}[9/10] Setup sessione Telegram (opzionale)...${NC}"
echo -e "${CYAN}   Vuoi configurare la sessione Telegram ora? (y/n)${NC}"
read -r SETUP_TELEGRAM
if [ "$SETUP_TELEGRAM" = "y" ] || [ "$SETUP_TELEGRAM" = "Y" ]; then
    echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
    ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 setup_telegram_auth.py"
    echo -e "${GREEN}   ✅ Sessione Telegram configurata${NC}"
else
    echo -e "${YELLOW}   ⚠️  Sessione Telegram non configurata (50% funzionalità)${NC}"
fi
echo ""

# Step 10: Start bot
echo -e "${YELLOW}[10/10] Avvio del bot...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Il bot verrà avviato in tmux${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && ./start_system.sh"
echo ""

echo -e "${GREEN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ DEPLOY COMPLETATO!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo -e "${YELLOW}📖 Comandi utili:${NC}"
echo "   • Connessione VPS:     ssh $VPS_USER@$VPS_IP"
echo "   • Directory bot:       cd $VPS_DIR"
echo "   • View logs:           tail -f $VPS_DIR/earlybird.log"
echo "   • Attach tmux:         tmux attach -t earlybird"
echo "   • Detach tmux:         Ctrl+B poi d"
echo "   • Stop bot:            tmux kill-session -t earlybird"
echo ""
