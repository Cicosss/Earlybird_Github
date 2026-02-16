#!/usr/bin/env python3
"""
EarlyBird V3.8 - Telegram Alert Test Script

Tests the notification system by sending a test message to the configured Telegram chat.
Prints the full HTTP response to diagnose issues like "Chat not found".

Usage:
    python tests/manual_test_alert.py
"""

import os
import sys

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def test_telegram_alert():
    """Send a test alert and print the full response."""
    print("=" * 50)
    print("🧪 EarlyBird V3.8 - Telegram Alert Test")
    print("=" * 50)

    # Check credentials
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not found in .env")
        return False
    print(f"✅ TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}")

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID not found in .env")
        return False
    print(f"✅ TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

    # Build test message with HTML link
    message = (
        "🚨 <b>TEST ALERT</b> (EarlyBird V3.8)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Sistema di notifica funzionante!\n"
        "📡 Connessione Telegram OK\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 <a href='https://google.com'>Test Link - Click Me</a>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Questo è un messaggio di test.</i>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    print("\n📤 Sending test message...")
    print(f"   URL: {url[:50]}...")
    print(f"   Chat ID: {TELEGRAM_CHAT_ID}")

    try:
        response = requests.post(url, data=payload, timeout=30)

        print(f"\n📥 Response Status: {response.status_code}")
        print(f"📥 Response Body:\n{response.text}")

        if response.status_code == 200:
            print("\n✅ SUCCESS! Test alert sent to Telegram.")
            return True
        else:
            print("\n❌ FAILED! Check the response above for details.")

            # Common error hints
            resp_json = response.json() if response.text else {}
            error_code = resp_json.get("error_code")
            description = resp_json.get("description", "")

            if error_code == 400 and "chat not found" in description.lower():
                print("\n💡 HINT: Chat ID not found. Possible causes:")
                print("   1. Bot hasn't been started by the user (send /start to bot)")
                print("   2. Chat ID is incorrect (use @userinfobot to get your ID)")
                print("   3. For groups, bot must be added to the group first")
            elif error_code == 401:
                print("\n💡 HINT: Invalid bot token. Check TELEGRAM_TOKEN in .env")
            elif error_code == 403:
                print("\n💡 HINT: Bot was blocked by the user or kicked from group")

            return False

    except requests.exceptions.Timeout:
        print("\n❌ TIMEOUT! Request took longer than 30 seconds.")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        return False


if __name__ == "__main__":
    success = test_telegram_alert()
    sys.exit(0 if success else 1)
