#!/usr/bin/env python3
"""
One-Time Setup Script for Telegram Authentication
This script must be run ONCE to generate the session file.

INSTRUCTIONS:
1. Run: python setup_telegram_auth.py
2. Enter your phone number (with country code, e.g., +393331234567)
3. Check Telegram on your phone/desktop for the login code
4. Enter the code when prompted
5. Done! The earlybird.session file will be created

The session file allows the bot to access Telegram without asking for login again.
"""

import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

# Load credentials from .env
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

if not API_ID or not API_HASH:
    print("❌ ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH not found in .env file")
    sys.exit(1)

API_ID = int(API_ID)

# Session file name
SESSION_NAME = 'earlybird_monitor'

async def main():
    print("🦅 EarlyBird Telegram Authentication Setup")
    print("=" * 50)
    print("This is a ONE-TIME setup to generate your session file.")
    print("You will need to:")
    print("  1. Enter your phone number")
    print("  2. Enter the code Telegram sends you")
    print("=" * 50)
    print()
    
    # Create client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print("📱 Please enter your phone number (with country code):")
        print("   Example: +393331234567")
        phone = input("Phone: ").strip()
        
        await client.send_code_request(phone)
        
        print("\n📬 A code has been sent to your Telegram app.")
        code = input("Enter the code: ").strip()
        
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            print("\n🔐 Two-Step Verification is enabled.")
            password = input("Enter your 2FA password: ").strip()
            await client.sign_in(password=password)
    
    print("\n✅ SUCCESS! Session file created: earlybird.session")
    print("You can now run the EarlyBird monitoring system.")
    print("\nThe bot will automatically use this session to monitor Telegram channels.")
    
    # Test: Get own info
    me = await client.get_me()
    print(f"\n👤 Logged in as: {me.first_name} {me.last_name or ''} (@{me.username or 'no username'})")
    
    await client.disconnect()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
