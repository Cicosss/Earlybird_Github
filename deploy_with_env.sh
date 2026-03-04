#!/bin/bash
# ============================================
# EarlyBird VPS Deployment Script with Environment Variable
# Usage: export SSH_PASS="your_password" && ./deploy_with_env.sh
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
echo "🦅 EarlyBird VPS Deployment Script (Environment Variable)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# Check if SSH_PASS is set
if [ -z "$SSH_PASS" ]; then
    echo -e "${RED}❌ ERRORE: La variabile d'ambiente SSH_PASS non è impostata!${NC}"
    echo -e "${YELLOW}   Usa: export SSH_PASS=\"tua_password\" && ./deploy_with_env.sh${NC}"
    exit 1
fi

# Step 1: Check if zip file exists
echo -e "${YELLOW}[1/8] Verificando file zip...${NC}"
if [ ! -f "$ZIP_FILE" ]; then
    echo -e "${RED}❌ File $ZIP_FILE non trovato!${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ File $ZIP_FILE trovato ($(ls -lh $ZIP_FILE | awk '{print $5}'))${NC}"
echo ""

# Step 2: Create directory on VPS
echo -e "${YELLOW}[2/8] Creazione directory sulla VPS...${NC}"
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "mkdir -p $VPS_DIR && echo Directory creata con successo"
echo -e "${GREEN}   ✅ Directory creata${NC}"
echo ""

# Step 3: Transfer zip file to VPS
echo -e "${YELLOW}[3/8] Trasferimento file zip sulla VPS...${NC}"
sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no "$ZIP_FILE" "$VPS_USER@$VPS_IP:$VPS_DIR/"
echo -e "${GREEN}   ✅ File trasferito${NC}"
echo ""

# Step 4: Extract zip file on VPS
echo -e "${YELLOW}[4/8] Estrazione file zip sulla VPS...${NC}"
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $VPS_DIR && unzip -o $ZIP_FILE && rm $ZIP_FILE && echo File estratto con successo"
echo -e "${GREEN}   ✅ File estratto${NC}"
echo ""

# Step 5: Create .env file if not exists
echo -e "${YELLOW}[5/8] Verifica file .env...${NC}"
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $VPS_DIR && if [ ! -f .env ]; then cp .env.template .env && echo File .env creato da template; else echo File .env esistente; fi"
echo -e "${GREEN}   ✅ File .env verificato${NC}"
echo ""

# Step 6: Setup Telegram session (optional)
echo -e "${YELLOW}[6/8] Setup sessione Telegram (opzionale)...${NC}"
echo -e "${CYAN}   Vuoi configurare la sessione Telegram ora? (y/n)${NC}"
read -r SETUP_TELEGRAM
if [ "$SETUP_TELEGRAM" = "y" ] || [ "$SETUP_TELEGRAM" = "Y" ]; then
    echo -e "${YELLOW}   ⚠️  La sessione Telegram richiede input interattivo${NC}"
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $VPS_DIR && python3 setup_telegram_auth.py"
    echo -e "${GREEN}   ✅ Sessione Telegram configurata${NC}"
else
    echo -e "${YELLOW}   ⚠️  Sessione Telegram non configurata (50% funzionalità)${NC}"
fi
echo ""

# Step 7: Setup dependencies on VPS
echo -e "${YELLOW}[7/8] Setup dipendenze sulla VPS...${NC}"
echo -e "${YELLOW}   Questo potrebbe richiedere 10-15 minuti...${NC}"
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $VPS_DIR && bash setup_vps.sh"
echo -e "${GREEN}   ✅ Setup completato${NC}"
echo ""

# Step 8: Start bot
echo -e "${YELLOW}[8/8] Avvio del bot...${NC}"
echo -e "${CYAN}   Il bot verrà avviato in tmux${NC}"
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $VPS_DIR && bash start_system.sh"
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
