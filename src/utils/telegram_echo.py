#!/usr/bin/env python3
"""
Telegram Echo Test Script
==========================
This script performs a live handshake with Telegram to verify:
1. The new Bot Token is valid
2. The Chat ID is still correct after the reset

If the test message fails, it enters Listening Mode to capture the new Chat ID.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in .env file")
    sys.exit(1)

if not TELEGRAM_CHAT_ID:
    print("❌ ERROR: TELEGRAM_CHAT_ID not found in .env file")
    sys.exit(1)

print("=" * 60)
print("TELEGRAM ECHO TEST")
print("=" * 60)
print(f"Bot Token: {TELEGRAM_BOT_TOKEN[:15]}...{TELEGRAM_BOT_TOKEN[-6:]}")
print(f"Chat ID: {TELEGRAM_CHAT_ID}")
print("=" * 60)


def send_message(chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            return True
        else:
            print(f"❌ API Error: {data.get('description', 'Unknown error')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: {e}")
        return False


def get_updates(offset: int = 0, timeout: int = 30) -> dict:
    """Get updates from Telegram Bot API (long polling)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {
        "offset": offset,
        "timeout": timeout
    }
    
    try:
        response = requests.get(url, params=params, timeout=timeout + 5)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            return data
        else:
            print(f"❌ API Error: {data.get('description', 'Unknown error')}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: {e}")
        return {}


def listening_mode():
    """
    Enter Listening Mode to capture the new Chat ID.
    User should send /start to the bot from their phone.
    """
    print("\n" + "=" * 60)
    print("🔊 LISTENING MODE ACTIVATED")
    print("=" * 60)
    print("Please send /start to your bot from your phone.")
    print("Waiting for message...")
    print("=" * 60 + "\n")
    
    offset = 0
    last_update_id = 0
    
    print("Press Ctrl+C to stop listening...\n")
    
    try:
        while True:
            data = get_updates(offset, timeout=30)
            
            if data and data.get("result"):
                for update in data["result"]:
                    update_id = update.get("update_id")
                    message = update.get("message", {})
                    
                    if update_id > last_update_id:
                        last_update_id = update_id
                        offset = update_id + 1
                        
                        chat = message.get("chat", {})
                        chat_id = chat.get("id")
                        chat_type = chat.get("type")
                        chat_username = chat.get("username", "N/A")
                        chat_first_name = chat.get("first_name", "N/A")
                        
                        text = message.get("text", "")
                        
                        print("\n" + "=" * 60)
                        print("✅ NEW MESSAGE RECEIVED!")
                        print("=" * 60)
                        print(f"Chat ID: {chat_id}")
                        print(f"Chat Type: {chat_type}")
                        print(f"Username: @{chat_username}")
                        print(f"First Name: {chat_first_name}")
                        print(f"Message: {text}")
                        print("=" * 60)
                        
                        # Send confirmation message
                        send_message(
                            str(chat_id),
                            f"✅ <b>Chat ID Captured!</b>\n\n"
                            f"Your Chat ID is: <code>{chat_id}</code>\n\n"
                            f"Please update your .env file:\n"
                            f"<code>TELEGRAM_CHAT_ID={chat_id}</code>"
                        )
                        
                        print(f"\n🎯 NEW CHAT ID: {chat_id}")
                        print(f"Please update your .env file:")
                        print(f"   TELEGRAM_CHAT_ID={chat_id}")
                        print("=" * 60 + "\n")
                        
                        return chat_id
            
            # Small delay to avoid excessive polling
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Listening stopped by user.")
        return None


def main():
    """Main execution flow."""
    
    # Step 1: Send test message to existing Chat ID
    print("\n📤 Step 1: Sending test message to existing Chat ID...")
    test_message = "🦅 INITIAL PING. If you see this, the Bot Token works."
    
    success = send_message(TELEGRAM_CHAT_ID, test_message)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ TOKEN OK. CHAT ID UNCHANGED.")
        print("=" * 60)
        print(f"The test message was successfully sent to Chat ID: {TELEGRAM_CHAT_ID}")
        print("Your Telegram connection is working correctly!")
        print("=" * 60 + "\n")
        return 0
    
    # Step 2: If message failed, enter Listening Mode
    print("\n" + "=" * 60)
    print("⚠️  TEST MESSAGE FAILED")
    print("=" * 60)
    print("Possible reasons:")
    print("  1. Chat ID has changed after the reset")
    print("  2. User hasn't started a conversation with the bot")
    print("  3. Bot token is invalid")
    print("=" * 60)
    
    # Verify bot token is valid
    print("\n🔍 Verifying Bot Token validity...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("ok"):
            bot_info = data.get("result", {})
            print(f"✅ Bot Token is valid!")
            print(f"   Bot Name: @{bot_info.get('username', 'N/A')}")
            print(f"   Bot ID: {bot_info.get('id', 'N/A')}")
        else:
            print(f"❌ Bot Token is INVALID: {data.get('description', 'Unknown error')}")
            return 1
    except Exception as e:
        print(f"❌ Error verifying token: {e}")
        return 1
    
    # Step 3: Enter Listening Mode
    print("\n" + "=" * 60)
    print("LISTENING FOR NEW CHAT ID... Please send /start to the bot.")
    print("=" * 60 + "\n")
    
    new_chat_id = listening_mode()
    
    if new_chat_id:
        print("\n" + "=" * 60)
        print("✅ SUCCESS! New Chat ID captured.")
        print("=" * 60)
        print(f"Please update your .env file:")
        print(f"   TELEGRAM_CHAT_ID={new_chat_id}")
        print("=" * 60 + "\n")
        return 0
    else:
        print("\n" + "=" * 60)
        print("⚠️  Listening stopped without capturing a Chat ID.")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
