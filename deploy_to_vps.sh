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

# Step 5: Check Python version on VPS (CRITICAL: requires Python 3.10+)
echo -e "${YELLOW}[5/10] Verifica versione Python sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
PYTHON_VERSION=$(ssh "$VPS_USER@$VPS_IP" "python3 --version 2>&1" | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}❌ Python 3.10+ richiesto sulla VPS, trovato: $PYTHON_VERSION${NC}"
    echo -e "${RED}Il codice usa 'str | None' che richiede Python 3.10+${NC}"
    echo -e "${RED}Installare Python 3.10 o superiore sulla VPS:${NC}"
    echo -e "${RED}  sudo apt-get install -y python3.10 python3.10-venv${NC}"
    exit 1
fi

echo -e "${GREEN}   ✅ Versione Python OK: $PYTHON_VERSION${NC}"
echo ""

# Step 6: Install Python dependencies
echo -e "${YELLOW}[6/10] Installazione dipendenze Python...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Questo potrebbe richiedere alcuni minuti...${NC}"

# Install dependencies and capture exit code
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && pip3 install -r requirements.txt"
INSTALL_EXIT_CODE=$?

# Verify installation succeeded
if [ $INSTALL_EXIT_CODE -ne 0 ]; then
    echo -e "${RED}   ❌ ERRORE: Installazione dipendenze fallita (exit code: $INSTALL_EXIT_CODE)${NC}"
    echo -e "${RED}   Il bot potrebbe non avviarsi correttamente sulla VPS${NC}"
    echo -e "${YELLOW}   Controlla i log sopra per dettagli sull'errore${NC}"
    exit 1
fi

# Verify critical dependencies are installed
echo -e "${CYAN}   Verifica dipendenze critiche...${NC}"
PYDANTIC_CHECK=$(ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 -c 'import pydantic; print(pydantic.__version__)' 2>&1")
if [ $? -ne 0 ]; then
    echo -e "${RED}   ❌ ERRORE CRITICO: Pydantic non installato correttamente${NC}"
    echo -e "${RED}   Il bot crasherà all'avvio con ModuleNotFoundError${NC}"
    echo -e "${RED}   Output verifica: $PYDANTIC_CHECK${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ Pydantic installato (version: $PYDANTIC_CHECK)${NC}"

echo -e "${GREEN}   ✅ Dipendenze Python installate e verificate${NC}"
echo ""

# Step 7: Install Playwright browsers
echo -e "${YELLOW}[7/11] Installazione browser Playwright...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Questo potrebbe richiedere alcuni minuti...${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 -m playwright install chromium --with-deps"
echo -e "${GREEN}   ✅ Browser Playwright installati${NC}"
echo ""

# Step 8: Create .env file if not exists
echo -e "${YELLOW}[8/11] Verifica file .env...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && if [ ! -f .env ]; then cp .env.template .env && echo 'File .env creato da template'; else echo 'File .env esistente'; fi"
echo -e "${GREEN}   ✅ File .env verificato${NC}"
echo ""

# Step 9: Run database migration
echo -e "${YELLOW}[9/11] Esecuzione migration database...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 -m src.database.migration_v13_complete_schema"
echo -e "${GREEN}   ✅ Migration database completata${NC}"
echo ""

# Step 10: Setup Telegram session (optional)
echo -e "${YELLOW}[10/11] Setup sessione Telegram (opzionale)...${NC}"
echo -e "${CYAN}   Vuoi configurare la sessione Telegram ora? (y/n)${NC}"
read -r SETUP_TELEGRAM
if [ "$SETUP_TELEGRAM" = "y" ] || [ "$SETUP_TELEGRAM" = "Y" ]; then
    echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
    echo -e "${CYAN}   Il flag -t è richiesto per l'input interattivo (codice OTP)${NC}"
    ssh -t "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 setup_telegram_auth.py"
    echo -e "${GREEN}   ✅ Sessione Telegram configurata${NC}"
else
    echo -e "${YELLOW}   ⚠️  Sessione Telegram non configurata (50% funzionalità)${NC}"
fi
echo ""

# Step 11: Start bot
echo -e "${YELLOW}[11/11] Avvio del bot...${NC}"
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
