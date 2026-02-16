#!/usr/bin/env python3
"""
One-Time Setup Script for Telegram Authentication
This script must be run ONCE to generate session file.

INSTRUCTIONS:
1. Run: python setup_telegram_auth.py [PHONE_NUMBER]
2. Enter your phone number (with country code, e.g., +393331234567)
   OR use the default number if provided
3. Check Telegram on your phone/desktop for login code
4. Enter code when prompted
5. Done! The data/earlybird_monitor.session file will be created

The session file allows bot to access Telegram without asking for login again.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

# Load credentials from .env
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    print("❌ ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH not found in .env file")
    sys.exit(1)

API_ID = int(API_ID)

# Session file path - use data/ directory for VPS compatibility (matches run_telegram_monitor.py)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_PATH = os.path.join(DATA_DIR, "earlybird_monitor")

# Default phone number (can be overridden via environment variable or command line)
DEFAULT_PHONE_NUMBER = os.getenv("TELEGRAM_DEFAULT_PHONE_NUMBER", "+393703342314")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EarlyBird Telegram Authentication Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python setup_telegram_auth.py
    python setup_telegram_auth.py +393331234567
    python setup_telegram_auth.py --phone +393331234567

Environment Variable:
    TELEGRAM_DEFAULT_PHONE_NUMBER: Set default phone number
        """,
    )

    parser.add_argument(
        "phone",
        nargs="?",
        default=None,
        help="Phone number with country code (e.g., +393331234567)",
    )

    parser.add_argument(
        "--phone",
        dest="phone_alt",
        help="Phone number with country code (alternative syntax)",
    )

    return parser.parse_args()


async def main():
    args = parse_args()

    print("🦅 EarlyBird Telegram Authentication Setup")
    print("=" * 50)
    print("This is a ONE-TIME setup to generate your session file.")
    print("You will need to:")
    print("  1. Enter your phone number")
    print("  2. Enter code Telegram sends you")
    print("=" * 50)
    print()

    # Create client
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

    await client.connect()

    if not await client.is_user_authorized():
        # Get phone number from command line, environment variable, or prompt
        # Post-processing: prioritize positional argument, then --phone flag, then default
        phone = args.phone or args.phone_alt or DEFAULT_PHONE_NUMBER

        if not phone:
            print("📱 Please enter your phone number (with country code):")
            print("   Example: +393331234567")
            phone = input("Phone: ").strip()
        else:
            print(f"📱 Using phone number: {phone}")
            print("   (If incorrect, press Ctrl+C and run again with correct number)")

        await client.send_code_request(phone)

        print("\n📬 A code has been sent to your Telegram app.")
        code = input("Enter code: ").strip()

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            print("\n🔐 Two-Step Verification is enabled.")
            password = input("Enter your 2FA password: ").strip()
            await client.sign_in(password=password)

    print("\n✅ SUCCESS! Session file created: data/earlybird_monitor.session")
    print("You can now run the EarlyBird monitoring system.")
    print("\nThe bot will automatically use this session to monitor Telegram channels.")
    print("\n🚀 The Telegram Monitor will automatically start within 10 seconds...")

    # Test: Get own info
    me = await client.get_me()
    print(
        f"\n👤 Logged in as: {me.first_name} {me.last_name or ''} (@{me.username or 'no username'})"
    )

    await client.disconnect()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
