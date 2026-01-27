#!/usr/bin/env python3
# ============================================
# EarlyBird Backdoor Audit Logger
# Ubuntu 24.04 LTS - SSH Reverse Tunnel Monitoring
# ============================================

import os
import sys
import json
import time
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

class BackdoorAuditLogger:
    def __init__(self):
        self.setup_logging()
        self.config_file = "/home/linux/earlybird/backdoor_config.sh"
        self.load_config()
        
    def setup_logging(self):
        """Setup comprehensive logging system"""
        self.logger = logging.getLogger('backdoor_audit')
        self.logger.setLevel(logging.INFO)
        
        # File handler for audit log
        log_file = "/var/log/earlybird/backdoor_audit.log"
        
        # Try to create log directory, fallback to temp if permission denied
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
        except PermissionError:
            # Fallback to temp directory for testing
            temp_log = os.path.join(tempfile.gettempdir(), 'earlybird_backdoor_audit.log')
            file_handler = logging.FileHandler(temp_log)
            log_file = temp_log
        
        file_handler.setLevel(logging.INFO)
        
        # Console handler for immediate feedback
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def load_config(self):
        """Load configuration from shell script"""
        try:
            # Source the shell script and extract variables
            result = subprocess.run(
                f"source {self.config_file} && env | grep -E '^(VPS_|LOCAL_|SSH_|SERVICE_)'",
                shell=True,
                capture_output=True,
                text=True
            )
            
            self.config = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    self.config[key] = value
                    
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            self.config = {}
    
    def log_connection(self, event_type, details=None):
        """Log connection events"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "event_type": "connection",
            "action": event_type,
            "details": details or {},
            "vps_ip": self.config.get('VPS_IP', 'unknown'),
            "local_ip": self.config.get('LOCAL_IP', 'unknown')
        }
        
        self.logger.info(f"CONNECTION: {event_type.upper()} - {json.dumps(log_entry)}")
        
        # Send Telegram notification if enabled
        if self.config.get('TELEGRAM_NOTIFICATIONS_ENABLED', 'false') == 'true':
            self.send_telegram_alert(f"🔐 Backdoor {event_type}", log_entry)
    
    def log_command(self, command, user, result=None):
        """Log command execution"""
        timestamp = datetime.now().isoformat()
        
        # Check if command is allowed
        allowed_commands = [
            "systemctl status earlybird*",
            "systemctl restart earlybird*",
            "docker ps",
            "docker logs redlib",
            "tail -f earlybird.log",
            "ps aux | grep python",
            "df -h",
            "free -h",
            "top -bn1",
            "netstat -tlnp",
            "ufw status",
            "journalctl -u earlybird*"
        ]
        
        blocked_commands = [
            "rm -rf /",
            "chmod 777",
            "useradd",
            "usermod",
            "passwd",
            "sudo -i",
            "su -",
            "dd if=",
            "mkfs",
            "fdisk",
            "reboot",
            "shutdown"
        ]
        
        is_allowed = any(pattern in command for pattern in allowed_commands)
        is_blocked = any(pattern in command for pattern in blocked_commands)
        
        log_entry = {
            "timestamp": timestamp,
            "event_type": "command",
            "command": command,
            "user": user,
            "allowed": is_allowed,
            "blocked": is_blocked,
            "result": result,
            "vps_ip": self.config.get('VPS_IP', 'unknown')
        }
        
        if is_blocked:
            self.logger.warning(f"BLOCKED COMMAND: {command} - {json.dumps(log_entry)}")
            self.send_telegram_alert("🚨 BLOCKED COMMAND", log_entry)
        elif is_allowed:
            self.logger.info(f"ALLOWED COMMAND: {command} - {json.dumps(log_entry)}")
        else:
            self.logger.warning(f"UNKNOWN COMMAND: {command} - {json.dumps(log_entry)}")
    
    def log_service_event(self, event_type, details=None):
        """Log service events"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "event_type": "service",
            "action": event_type,
            "details": details or {},
            "service_name": self.config.get('SERVICE_NAME', 'earlybird-backdoor')
        }
        
        self.logger.info(f"SERVICE: {event_type.upper()} - {json.dumps(log_entry)}")
        
        # Send critical alerts for service failures
        if event_type in ['failure', 'restart', 'disconnect']:
            self.send_telegram_alert(f"⚠️ Service {event_type}", log_entry)
    
    def check_service_health(self):
        """Check backdoor service health"""
        try:
            # Check systemd service status
            result = subprocess.run(
                ["systemctl", "is-active", "earlybird-backdoor"],
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip() == "active":
                self.log_service_event("health_check", {"status": "active"})
            else:
                self.log_service_event("failure", {"status": result.stdout.strip()})
                
        except Exception as e:
            self.log_service_event("error", {"error": str(e)})
    
    def check_tunnel_status(self):
        """Check SSH tunnel status"""
        try:
            # Check if SSH tunnel process is running
            result = subprocess.run(
                ["pgrep", "-f", "ssh -R 2222:localhost:22"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                self.log_connection("tunnel_active", {"pids": pids})
            else:
                self.log_connection("tunnel_down", {"error": "No tunnel process found"})
                
        except Exception as e:
            self.log_connection("tunnel_error", {"error": str(e)})
    
    def send_telegram_alert(self, message, details=None):
        """Send Telegram notification (placeholder)"""
        # This would integrate with your existing Telegram bot
        # For now, just log the alert
        self.logger.info(f"TELEGRAM ALERT: {message}")
        
        # TODO: Implement actual Telegram integration
        # Use your existing TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from .env
    
    def generate_report(self, hours=24):
        """Generate audit report for last N hours"""
        try:
            cutoff_time = datetime.now().timestamp() - (hours * 3600)
            
            report = {
                "report_generated": datetime.now().isoformat(),
                "period_hours": hours,
                "vps_ip": self.config.get('VPS_IP', 'unknown'),
                "summary": {
                    "total_events": 0,
                    "connections": 0,
                    "commands": 0,
                    "service_events": 0,
                    "blocked_commands": 0
                }
            }
            
            # Parse audit log file
            audit_log = "/var/log/earlybird/backdoor_audit.log"
            
            # Fallback to temp log if main log not accessible
            if not os.path.exists(audit_log):
                audit_log = os.path.join(tempfile.gettempdir(), 'earlybird_backdoor_audit.log')
            
            if os.path.exists(audit_log):
                with open(audit_log, 'r') as f:
                    for line in f:
                        try:
                            # Extract timestamp from log line
                            if '[' in line and '] ' in line:
                                timestamp_str = line.split('[', 1)[1].split(']', 1)[0]
                                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S').timestamp()
                                
                                if log_time >= cutoff_time:
                                    report["summary"]["total_events"] += 1
                                    
                                    if "CONNECTION:" in line:
                                        report["summary"]["connections"] += 1
                                    elif "COMMAND:" in line:
                                        report["summary"]["commands"] += 1
                                        if "BLOCKED" in line:
                                            report["summary"]["blocked_commands"] += 1
                                    elif "SERVICE:" in line:
                                        report["summary"]["service_events"] += 1
                        except Exception:
                            continue
            
            # Save report
            report_dir = "/var/log/earlybird"
            try:
                os.makedirs(report_dir, exist_ok=True)
                report_file = f"{report_dir}/audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            except PermissionError:
                # Fallback to temp directory
                report_dir = tempfile.gettempdir()
                report_file = f"{report_dir}/earlybird_audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            self.logger.info(f"Audit report generated: {report_file}")
            return report_file
            
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            return None

def main():
    """Main function for standalone execution"""
    logger = BackdoorAuditLogger()
    
    if len(sys.argv) > 1:
        action = sys.argv[1]
        
        if action == "health":
            logger.check_service_health()
            logger.check_tunnel_status()
        elif action == "report":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            report_file = logger.generate_report(hours)
            if report_file:
                print(f"Report generated: {report_file}")
        else:
            print("Usage: audit_logger.py [health|report] [hours]")
    else:
        # Default: perform health check
        logger.check_service_health()
        logger.check_tunnel_status()

if __name__ == "__main__":
    main()
