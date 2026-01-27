#!/bin/bash
# ============================================
# EarlyBird VPS Backdoor Setup Script
# Ubuntu 24.04 LTS - SSH Reverse Tunnel + Security
# Author: EarlyBird Team
# ============================================

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration - AUTO-SET
VPS_IP="31.220.73.226"
LOCAL_IP="93.40.209.20"
LOCAL_IPV6="2001:b07:6456:fb49:a52c:ae39:6783:52ce"
LOCAL_PORT="2222"
SSH_KEY="${SSH_KEY:-/root/.ssh/id_rsa}"

echo -e "${GREEN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 EarlyBird Backdoor Setup - Ubuntu 24.04"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo -e "${BLUE}VPS Target: ${VPS_IP}${NC}"
echo -e "${BLUE}Local IP: ${LOCAL_IP}${NC}"
echo -e "${BLUE}Local Port: ${LOCAL_PORT}${NC}"
echo ""

# Step 1: System Update & Dependeies
echo -e "${GREEN}🔧 [1/6] Installing System Dependeies...${NC}"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y \
    openssh-server \
    ufw \
    curl \
    wget \
    htop \
    net-tools \
    telnet \
     \
    jq

# Step 2: SSH Security Configuration
echo ""
echo -e "${GREEN}🔑 [2/6] Configuring SSH Security...${NC}"

# Backup original SSH config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

# SSH Security Hardening
sudo tee -a /etc/ssh/sshd_config > /dev/null << 'EOF'

# EarlyBird Backdoor Security Configuration
ClientAliveInterval 60
ClientAliveCountMax 3
MaxAuthTries 3
MaxSessions 10
AllowTcpForwarding yes
GatewayPorts yes
PermitTunnel yes
EOF

# Restart SSH service
sudo systemctl restart ssh
echo -e "${GREEN}   ✅ SSH security configured${NC}"

# Step 3: UFW Firewall Configuration
echo ""
echo -e "${GREEN}🛡️ [3/6] Configuring UFW Firewall...${NC}"

# Reset UFW to default
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH from your IP only
sudo ufw allow from ${LOCAL_IP} to any port 22 comment "SSH from Local IP"
sudo ufw allow from ${LOCAL_IPV6} to any port 22 comment "SSH from Local IPv6"

# Allow established connections
sudo ufw allow in from any to any port 1024:65535 proto tcp

# Enable UFW
sudo ufw --force enable
echo -e "${GREEN}   ✅ UFW firewall configured${NC}"

# Step 4: Create Backdoor User & SSH Key
echo ""
echo -e "${GREEN}👤 [4/6] Setting up Backdoor Authentication...${NC}"

# Create dedicated backdoor user (optional - using root as requested)
# sudo useradd -m -s /bin/bash earlybird-admin
# sudo usermod -aG sudo earlybird-admin

# Generate SSH key for backdoor if not exists
if [ ! -f "${SSH_KEY}" ]; then
    echo -e "${YELLOW}   ⚠️ SSH key not found at ${SSH_KEY}${NC}"
    echo -e "${YELLOW}   📝 Generating new SSH key...${NC}"
    ssh-keygen -t ed25519 -f "${SSH_KEY}" -N "" -C "earlybird-backdoor@$(date +%Y%m%d)"
    echo -e "${GREEN}   ✅ SSH key generated${NC}"
else
    echo -e "${GREEN}   ✅ SSH key found at ${SSH_KEY}${NC}"
fi

# Display public key for manual addition if needed
echo -e "${BLUE}   📋 Public key for authorized_keys:${NC}"
cat "${SSH_KEY}.pub"
echo ""

# Step 5: Create Systemd Service
echo ""
echo -e "${GREEN}⚙️ [5/6] Creating Systemd Backdoor Service...${NC}"

# Create systemd service file
sudo tee /etc/systemd/system/earlybird-backdoor.service > /dev/null << EOF
[Unit]
Description=EarlyBird Secure Backdoor - Reverse SSH Tunnel
After=network.target ssh.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -R ${LOCAL_PORT}:localhost:22 -N -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${LOCAL_IP}
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=earlybird-backdoor

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log

[Install]
WantedBy=multi-user.target
EOF

# Create audit log directory
sudo mkdir -p /var/log/earlybird
sudo touch /var/log/earlybird/backdoor.log
sudo chmod 640 /var/log/earlybird/backdoor.log

# Step 6: Enable and Start Service
echo ""
echo -e "${GREEN}🚀 [6/6] Enabling Backdoor Service...${NC}"

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable earlybird-backdoor.service
sudo systemctl start earlybird-backdoor.service

# Check service status
sleep 2
if systemctl is-active --quiet earlybird-backdoor; then
    echo -e "${GREEN}   ✅ Backdoor service started successfully${NC}"
else
    echo -e "${RED}   ❌ Backdoor service failed to start${NC}"
    echo -e "${YELLOW}   📋 Check logs: journalctl -u earlybird-backdoor${NC}"
fi

# Step 7: Setup Monitoring Script
echo ""
echo -e "${GREEN}📊 [7/7] Setting up Monitoring...${NC}"

# Create monitoring script
sudo tee /usr/local/bin/backdoor-monitor.sh > /dev/null << 'EOF'
#!/bin/bash
# EarlyBird Backdoor Monitor Script

LOG_FILE="/var/log/earlybird/backdoor.log"
SERVICE_NAME="earlybird-backdoor"

# Fution to log with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | sudo tee -a "$LOG_FILE"
}

# Check service status
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_message "INFO: Backdoor service is running"
else
    log_message "ERROR: Backdoor service is not running"
    log_message "ACTION: Attempting to restart service"
    sudo systemctl restart "$SERVICE_NAME"
fi

# Check network connectivity
if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    log_message "INFO: Network connectivity OK"
else
    log_message "ERROR: Network connectivity failed"
fi

# Check SSH tunnel status
TUNNEL_PID=$(pgrep -f "ssh -R 2222:localhost:22")
if [ -n "$TUNNEL_PID" ]; then
    log_message "INFO: SSH tunnel process running (PID: $TUNNEL_PID)"
else
    log_message "ERROR: SSH tunnel process not found"
fi
EOF

# Make monitor script executable
sudo chmod +x /usr/local/bin/backdoor-monitor.sh

# Create cron job for monitoring (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/backdoor-monitor.sh") | crontab -

echo -e "${GREEN}   ✅ Monitoring setup complete${NC}"

# Final Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Backdoor Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📋 Configuration Summary:${NC}"
echo -e "${BLUE}   VPS IP: ${VPS_IP}${NC}"
echo -e "${BLUE}   Local IP: ${LOCAL_IP}${NC}"
echo -e "${BLUE}   Local Port: ${LOCAL_PORT}${NC}"
echo -e "${BLUE}   SSH Key: ${SSH_KEY}${NC}"
echo ""
echo -e "${YELLOW}🔧 Service Commands:${NC}"
echo -e "${GREEN}   Status:     sudo systemctl status earlybird-backdoor${NC}"
echo -e "${GREEN}   Restart:    sudo systemctl restart earlybird-backdoor${NC}"
echo -e "${GREEN}   Logs:       sudo journalctl -u earlybird-backdoor -f${NC}"
echo -e "${GREEN}   Monitor:    sudo cat /var/log/earlybird/backdoor.log${NC}"
echo ""
echo -e "${YELLOW}🔗 Connection from Local:${NC}"
echo -e "${GREEN}   ssh -p ${LOCAL_PORT} root@localhost${NC}"
echo ""
echo -e "${YELLOW}🛡️ Security Status:${NC}"
echo -e "${GREEN}   UFW:        sudo ufw status verbose${NC}"
echo -e "${GREEN}   SSH Config:  sudo ssh -t${NC}"
echo ""
echo -e "${RED}⚠️  IMPORTANT: Test connection from your local machine!${NC}"
echo ""
