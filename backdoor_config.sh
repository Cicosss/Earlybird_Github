#!/bin/bash
# ============================================
# EarlyBird Backdoor Configuration
# Ubuntu 24.04 LTS - SSH Reverse Tunnel
# ============================================

# VPS Configuration
VPS_IP="31.220.73.226"
VPS_IPV6="2a02:c207:2297:1221::1"
VPS_LOCATION="Hub Europe"
VPS_OS="Ubuntu 24.04 LTS"

# Local Client Configuration
LOCAL_IP="93.40.209.20"
LOCAL_IPV6="2001:b07:6456:fb49:a52c:ae39:6783:52ce"
LOCAL_PORT="2222"
SSH_KEY="$HOME/.ssh/id_rsa"

# Security Configuration
FIREWALL_ENABLED=true
WHITELIST_IPS=("$LOCAL_IP" "$LOCAL_IPV6")
ALLOWED_PORTS=(22)
DEFAULT_POLICY="deny"

# SSH Configuration
SSH_CLIENT_ALIVE_INTERVAL=60
SSH_MAX_AUTH_TRIES=3
SSH_MAX_SESSIONS=10
SSH_PERMIT_TUNNEL=true
SSH_ALLOW_TCP_FORWARDING=true
ACCESS_LEVEL="root"
AUDIT_LOGGING=true

# Service Configuration
SERVICE_NAME="earlybird-backdoor"
SERVICE_TYPE="reverse-ssh-tunnel"
AUTO_RESTART=true
RESTART_DELAY=10
HEALTH_CHECK_INTERVAL=300

# Monitoring Configuration
MONITORING_ENABLED=true
LOG_FILE="/var/log/earlybird/backdoor.log"
SYSTEMD_JOURNAL="earlybird-backdoor"
CRON_SCHEDULE="*/5 * * * *"

# Alerts Configuration
ALERT_SERVICE_FAILURE=true
ALERT_NETWORK_FAILURE=true
ALERT_TUNNEL_FAILURE=true

# Allowed Commands
ALLOWED_COMMANDS=(
    "systemctl status earlybird*"
    "systemctl restart earlybird*"
    "docker ps"
    "docker logs redlib"
    "tail -f earlybird.log"
    "ps aux | grep python"
    "df -h"
    "free -h"
    "top -bn1"
    "netstat -tlnp"
    "ufw status"
    "journalctl -u earlybird* --since \"1 hour ago\""
)

# Blocked Commands
BLOCKED_COMMANDS=(
    "rm -rf /"
    "chmod 777"
    "useradd"
    "usermod"
    "passwd"
    "sudo -i"
    "su -"
    "dd if="
    "mkfs"
    "fdisk"
    "reboot"
    "shutdown"
)

# Telegram Notifications
TELEGRAM_NOTIFICATIONS_ENABLED=true
TELEGRAM_ON_CONNECT=true
TELEGRAM_ON_DISCONNECT=true
TELEGRAM_ON_COMMAND=true
TELEGRAM_ON_ERROR=true

# Function to get configuration value
get_config() {
    local key="$1"
    case "$key" in
        "vps_ip") echo "$VPS_IP" ;;
        "local_ip") echo "$LOCAL_IP" ;;
        "local_port") echo "$LOCAL_PORT" ;;
        "ssh_key") echo "$SSH_KEY" ;;
        "service_name") echo "$SERVICE_NAME" ;;
        "log_file") echo "$LOG_FILE" ;;
        *) echo "Unknown config key: $key" ;;
    esac
}

# Function to validate configuration
validate_config() {
    echo "Validating backdoor configuration..."
    
    # Check if SSH key exists
    if [[ ! -f "$SSH_KEY" ]]; then
        echo "WARNING: SSH key not found at $SSH_KEY"
        echo "Run: ssh-keygen -t ed25519 -f $SSH_KEY"
        return 1
    fi
    
    # Check if IP addresses are valid
    if [[ -z "$VPS_IP" || -z "$LOCAL_IP" ]]; then
        echo "ERROR: VPS IP or Local IP not set"
        return 1
    fi
    
    # Check if port is valid
    if [[ "$LOCAL_PORT" -lt 1024 || "$LOCAL_PORT" -gt 65535 ]]; then
        echo "ERROR: Invalid port number: $LOCAL_PORT"
        return 1
    fi
    
    echo "Configuration validation passed"
    return 0
}

# Function to display configuration summary
show_config() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔐 EarlyBird Backdoor Configuration Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "VPS IP:        $VPS_IP"
    echo "Local IP:      $LOCAL_IP"
    echo "Local Port:    $LOCAL_PORT"
    echo "SSH Key:       $SSH_KEY"
    echo "Access Level:  $ACCESS_LEVEL"
    echo "Service Name:  $SERVICE_NAME"
    echo "Log File:      $LOG_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Export all variables for use in other scripts
export VPS_IP VPS_IPV6 VPS_LOCATION VPS_OS
export LOCAL_IP LOCAL_IPV6 LOCAL_PORT SSH_KEY
export FIREWALL_ENABLED ALLOWED_PORTS DEFAULT_POLICY
export SSH_CLIENT_ALIVE_INTERVAL SSH_MAX_AUTH_TRIES SSH_MAX_SESSIONS
export SSH_PERMIT_TUNNEL SSH_ALLOW_TCP_FORWARDING ACCESS_LEVEL AUDIT_LOGGING
export SERVICE_NAME SERVICE_TYPE AUTO_RESTART RESTART_DELAY HEALTH_CHECK_INTERVAL
export MONITORING_ENABLED LOG_FILE SYSTEMD_JOURNAL CRON_SCHEDULE
export ALERT_SERVICE_FAILURE ALERT_NETWORK_FAILURE ALERT_TUNNEL_FAILURE
export TELEGRAM_NOTIFICATIONS_ENABLED TELEGRAM_ON_CONNECT TELEGRAM_ON_DISCONNECT
export TELEGRAM_ON_COMMAND TELEGRAM_ON_ERROR

# Export arrays
export ALLOWED_COMMANDS BLOCKED_COMMANDS WHITELIST_IPS
