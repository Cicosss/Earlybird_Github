#!/bin/bash
# ============================================
# EarlyBird VPS Deploy Script with Backdoor
# Enhanced version with automatic backdoor setup
# Usage: ./deploy_to_vps_with_backdoor.sh [--full]
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration - EDIT THESE
VPS_USER="${VPS_USER:-root}"
VPS_HOST="${VPS_HOST:-31.220.73.226}"
VPS_PATH="${VPS_PATH:-/root/earlybird}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"

# Load backdoor configuration
source ./backdoor_config.sh

echo -e "${GREEN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 EarlyBird Deploy Script V7.0 + Backdoor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo -e "${BLUE}Target VPS: ${VPS_HOST}${NC}"
echo -e "${BLUE}Backdoor Port: ${LOCAL_PORT}${NC}"
echo ""

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}❌ SSH key not found at $SSH_KEY${NC}"
    echo -e "${YELLOW}Generating new SSH key...${NC}"
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "earlybird-deploy@$(date +%Y%m%d)"
    echo -e "${GREEN}✅ SSH key generated${NC}"
fi

# Parse arguments
FULL_DEPLOY=false
SETUP_BACKDOOR=false
if [ "$1" == "--full" ]; then
    FULL_DEPLOY=true
    SETUP_BACKDOOR=true
    echo -e "${YELLOW}📦 Full deploy mode (includes setup + backdoor)${NC}"
elif [ "$1" == "--backdoor" ]; then
    SETUP_BACKDOOR=true
    echo -e "${YELLOW}🔐 Backdoor setup mode only${NC}"
fi

# Files/folders to exclude from sync
EXCLUDES=(
    ".git"
    ".venv"
    "venv"
    "__pycache__"
    "*.pyc"
    ".pytest_cache"
    ".hypothesis"
    "*.log"
    "*.session"
    "*.session-journal"
    "data/*.db"
    "temp/*"
    ".env"  # Don't overwrite production .env
    "bot.log"
    "earlybird.log"
    "telegram_monitor.log"
)

# Build exclude arguments
EXCLUDE_ARGS=""
for item in "${EXCLUDES[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude=$item"
done

# Step 1: Test SSH Connection
echo ""
echo -e "${GREEN}🔍 [1/5] Testing SSH Connection...${NC}"
if ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" "echo 'SSH Connection OK'" 2>/dev/null; then
    echo -e "${GREEN}   ✅ SSH connection successful${NC}"
else
    echo -e "${RED}   ❌ SSH connection failed${NC}"
    echo -e "${YELLOW}   Please check:${NC}"
    echo "     - VPS IP: $VPS_HOST"
    echo "     - SSH key: $SSH_KEY"
    echo "     - SSH access for $VPS_USER"
    exit 1
fi

# Step 2: Sync Files (if not backdoor-only)
if [ "$SETUP_BACKDOOR" != true ] || [ "$FULL_DEPLOY" == true ]; then
    echo ""
    echo -e "${GREEN}🔄 [2/5] Syncing files to VPS...${NC}"
    echo "   Target: ${VPS_USER}@${VPS_HOST}:${VPS_PATH}"
    
    # Create directory if it doesn't exist
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "mkdir -p ${VPS_PATH}" 2>/dev/null || true
    
    # Rsync to VPS
    rsync -avz --progress \
        -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
        $EXCLUDE_ARGS \
        ./ \
        "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/"
    
    echo -e "${GREEN}   ✅ Files synced${NC}"
fi

# Step 3: Setup Backdoor
if [ "$SETUP_BACKDOOR" == true ] || [ "$FULL_DEPLOY" == true ]; then
    echo ""
    echo -e "${GREEN}🔐 [3/5] Setting up Backdoor...${NC}"
    
    # Copy backdoor scripts to VPS
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
        ./setup_backdoor_ubuntu24.sh \
        ./backdoor_config.sh \
        ./audit_logger.py \
        "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/"
    
    # Make scripts executable
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd ${VPS_PATH} && chmod +x setup_backdoor_ubuntu24.sh backdoor_config.sh audit_logger.py"
    
    # Run backdoor setup
    echo -e "${YELLOW}   🚀 Running backdoor setup script...${NC}"
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd ${VPS_PATH} && ./setup_backdoor_ubuntu24.sh"
    
    echo -e "${GREEN}   ✅ Backdoor setup complete${NC}"
fi

# Step 4: Setup EarlyBird (if full deploy)
if [ "$FULL_DEPLOY" == true ]; then
    echo ""
    echo -e "${GREEN}🔧 [4/5] Running EarlyBird setup on VPS...${NC}"
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd ${VPS_PATH} && ./setup_vps.sh"
else
    # Just update dependencies
    echo ""
    echo -e "${GREEN}📚 [4/5] Updating Python dependencies...${NC}"
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd ${VPS_PATH} && source venv/bin/activate && pip install -r requirements.txt --quiet"
    
    # Ensure Playwright browsers are installed
    echo -e "${GREEN}🌐 Ensuring Playwright browsers are installed...${NC}"
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "cd ${VPS_PATH} && source venv/bin/activate && python -m playwright install chromium 2>/dev/null || true"
fi

# Step 5: Final Verification
echo ""
echo -e "${GREEN}🔍 [5/5] Final Verification...${NC}"

# Check backdoor service status
BACKDOOR_STATUS=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "systemctl is-active earlybird-backdoor 2>/dev/null || echo 'inactive'")
if [ "$BACKDOOR_STATUS" == "active" ]; then
    echo -e "${GREEN}   ✅ Backdoor service is running${NC}"
else
    echo -e "${YELLOW}   ⚠️ Backdoor service status: $BACKDOOR_STATUS${NC}"
fi

# Check UFW status
UFW_STATUS=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "ufw status | head -1" 2>/dev/null || echo "unknown")
echo -e "${GREEN}   🛡️  Firewall: $UFW_STATUS${NC}"

# Check disk space
DISK_USAGE=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "df -h / | tail -1 | awk '{print \$5}'" 2>/dev/null || echo "unknown")
echo -e "${GREEN}   💾 Disk usage: $DISK_USAGE${NC}"

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Deploy Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📋 Connection Information:${NC}"
echo -e "${GREEN}   SSH to VPS:     ssh -i $SSH_KEY ${VPS_USER}@${VPS_HOST}${NC}"
echo -e "${GREEN}   Backdoor:        ssh -p ${LOCAL_PORT} root@localhost${NC}"
echo ""
echo -e "${YELLOW}📋 Management Commands:${NC}"
echo -e "${GREEN}   Backdoor status: ssh -i $SSH_KEY ${VPS_USER}@${VPS_HOST} 'systemctl status earlybird-backdoor'${NC}"
echo -e "${GREEN}   EarlyBird restart: ssh -i $SSH_KEY ${VPS_USER}@${VPS_HOST} 'cd ${VPS_PATH} && screen -r earlybird'${NC}"
echo -e "${GREEN}   View logs:       ssh -i $SSH_KEY ${VPS_USER}@${VPS_HOST} 'tail -f ${VPS_PATH}/earlybird.log'${NC}"
echo ""
echo -e "${YELLOW}📋 Backdoor Commands (from local):${NC}"
echo -e "${GREEN}   Connect:          ssh -p ${LOCAL_PORT} root@localhost${NC}"
echo -e "${GREEN}   Check service:    systemctl status earlybird-backdoor${NC}"
echo -e "${GREEN}   View logs:        journalctl -u earlybird-backdoor -f${NC}"
echo -e "${GREEN}   Audit report:     python3 ${VPS_PATH}/audit_logger.py report 24${NC}"
echo ""
echo -e "${RED}⚠️  IMPORTANT: Test backdoor connection from your local machine!${NC}"
echo ""
