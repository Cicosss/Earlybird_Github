#!/bin/bash
# ============================================
# EarlyBird VPS Deployment Script V2 (Optimized)
# Single SSH connection for all operations
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
LOCAL_DIR="/home/linux/Earlybird_Github"

echo -e "${CYAN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 EarlyBird VPS Deployment Script V2"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# Step 1: Check if zip file exists
echo -e "${YELLOW}[1/7] Verificando file zip...${NC}"
if [ ! -f "$ZIP_FILE" ]; then
    echo -e "${RED}❌ File $ZIP_FILE non trovato!${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ File $ZIP_FILE trovato ($(ls -lh $ZIP_FILE | awk '{print $5}'))${NC}"
echo ""

# Step 2: Create deployment script on VPS
echo -e "${YELLOW}[2/7] Creazione script di deployment sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"

ssh "$VPS_USER@$VPS_IP" "cat > /tmp/deploy_remote.sh << 'EOFSCRIPT'
#!/bin/bash
set -e

VPS_DIR=\"$VPS_DIR\"
ZIP_FILE=\"$ZIP_FILE\"

echo '🔧 Preparazione directory...'
mkdir -p \$VPS_DIR
cd \$VPS_DIR

echo '📦 Estrazione file...'
unzip -o \$ZIP_FILE
rm \$ZIP_FILE

echo '⚙️  Verifica file .env...'
if [ ! -f .env ]; then
    cp .env.template .env
    echo 'File .env creato da template'
else
    echo 'File .env esistente'
fi

echo '✅ Preparazione completata!'
EOFSCRIPT
chmod +x /tmp/deploy_remote.sh
echo 'Script remoto creato con successo'
"

echo -e "${GREEN}   ✅ Script remoto creato${NC}"
echo ""

# Step 3: Transfer zip file to VPS
echo -e "${YELLOW}[3/7] Trasferimento file zip sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
scp "$ZIP_FILE" "$VPS_USER@$VPS_IP:/tmp/"
echo -e "${GREEN}   ✅ File trasferito${NC}"
echo ""

# Step 4: Execute deployment script on VPS
echo -e "${YELLOW}[4/7] Esecuzione deployment sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
ssh "$VPS_USER@$VPS_IP" "mv /tmp/$ZIP_FILE $VPS_DIR/ && /tmp/deploy_remote.sh && rm /tmp/deploy_remote.sh"
echo -e "${GREEN}   ✅ Deployment completato${NC}"
echo ""

# Step 5: Setup Telegram session (optional)
echo -e "${YELLOW}[5/7] Setup sessione Telegram (opzionale)...${NC}"
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

# Step 6: Run setup script on VPS
echo -e "${YELLOW}[6/7] Setup dipendenze sulla VPS...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${YELLOW}   Questo potrebbe richiedere alcuni minuti...${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && bash setup_vps.sh"
echo -e "${GREEN}   ✅ Setup completato${NC}"
echo ""

# Step 7: Start the bot
echo -e "${YELLOW}[7/7] Avvio del bot...${NC}"
echo -e "${CYAN}   Inserisci la password SSH quando richiesto${NC}"
echo -e "${CYAN}   Il bot verrà avviato in tmux${NC}"
ssh "$VPS_USER@$VPS_IP" "cd $VPS_DIR && bash start_system.sh"
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
