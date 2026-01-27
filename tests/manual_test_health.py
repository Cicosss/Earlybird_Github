#!/usr/bin/env python3
"""
Test script for HealthMonitor diagnostics.

Usage:
    python tests/manual_test_health.py          # Mock test (no real alerts)
    python tests/manual_test_health.py --live   # Send real test alert to Telegram
"""
import sys
import os
import argparse
import logging
from unittest import mock
from collections import namedtuple

# Setup path
sys.path.insert(0, os.getcwd())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_mock_test():
    """
    Test HealthMonitor with mocked disk usage (95%).
    Verifies detection and alert triggering without sending real alerts.
    """
    print("\n" + "=" * 50)
    print("🧪 HEALTH MONITOR - MOCK TEST")
    print("=" * 50)
    
    # Import after path setup
    from src.alerting.health_monitor import HealthMonitor, SEVERITY_ERROR
    
    # Create fresh monitor instance (bypass singleton)
    monitor = HealthMonitor()
    
    # Clear cooldown to ensure alert triggers
    monitor.last_alerts.clear()
    print("✅ Monitor initialized, cooldown cleared")
    
    # Mock disk usage to return 95%
    DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free', 'percent'])
    mock_disk = DiskUsage(total=100_000_000_000, used=95_000_000_000, free=5_000_000_000, percent=95.0)
    
    with mock.patch('src.alerting.health_monitor.psutil.disk_usage', return_value=mock_disk):
        print("\n📊 Running diagnostics with mocked 95% disk...")
        issues = monitor.run_diagnostics()
        
        # Check if disk issue was detected
        disk_issues = [i for i in issues if i[0] == "disk_full"]
        
        if disk_issues:
            print(f"✅ Detected Fake Disk Issue: {disk_issues[0][2]}")
        else:
            print("❌ FAILED: Disk issue not detected!")
            print(f"   Issues found: {issues}")
            return False
        
        # Test report_issues with mocked notifier
        print("\n📤 Testing report_issues...")
        
        with mock.patch('src.alerting.notifier.send_status_message') as mock_notifier:
            mock_notifier.return_value = True
            new_issues = monitor.report_issues(issues)
            
            if new_issues:
                print(f"✅ Triggered Notifier ({len(new_issues)} new issues)")
                print(f"   Issue keys: {[i[0] for i in new_issues]}")
                
                if mock_notifier.called:
                    print("✅ send_status_message was called")
                    # Show what would have been sent
                    call_args = mock_notifier.call_args
                    if call_args:
                        msg_preview = call_args[0][0][:100] if call_args[0] else "N/A"
                        print(f"   Message preview: {msg_preview}...")
            else:
                print("⚠️ No new issues (may be in cooldown)")
    
    # Verify cooldown was set
    if "disk_full" in monitor.last_alerts:
        print(f"✅ Cooldown set for 'disk_full'")
    
    print("\n" + "=" * 50)
    print("✅ MOCK TEST COMPLETED")
    print("=" * 50)
    return True


def run_live_test():
    """
    Send a real test alert to Telegram.
    Requires valid TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env
    """
    print("\n" + "=" * 50)
    print("🔴 HEALTH MONITOR - LIVE TEST")
    print("=" * 50)
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not configured in .env")
        return False
    
    print(f"✅ Telegram configured (chat_id: {chat_id[:4]}...)")
    
    # Import notifier
    from src.alerting.notifier import send_status_message
    
    # Send test message
    test_message = (
        "🧪 <b>TEST ALERT - HEALTH MONITOR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🟢 Questo è un test del sistema diagnostico.\n"
        "✅ Se vedi questo messaggio, il sistema funziona!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 EarlyBird V3.7"
    )
    
    print("\n📤 Sending test alert to Telegram...")
    result = send_status_message(test_message)
    
    if result:
        print("✅ Test alert sent successfully!")
        print("   Check your Telegram for the message.")
    else:
        print("❌ Failed to send test alert")
        return False
    
    print("\n" + "=" * 50)
    print("✅ LIVE TEST COMPLETED")
    print("=" * 50)
    return True


def main():
    parser = argparse.ArgumentParser(description="Test HealthMonitor diagnostics")
    parser.add_argument('--live', action='store_true', help="Send real test alert to Telegram")
    args = parser.parse_args()
    
    if args.live:
        success = run_live_test()
    else:
        success = run_mock_test()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
