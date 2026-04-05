#!/usr/bin/env python3
"""
Simple Telegram Alert Test

Tests if Telegram alerts can be sent from the notifier module.
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import after loading env
from src.alerting.notifier import send_alert


def test_simple_alert():
    """Send a simple test alert."""
    print("=" * 60)
    print("🧪 SIMPLE TELEGRAM ALERT TEST")
    print("=" * 60)

    # Check credentials
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        print("❌ TELEGRAM_TOKEN not configured")
        return False
    print(f"✅ Token: {token[:10]}...{token[-5:]}")

    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID not configured")
        return False
    print(f"✅ Chat ID: {chat_id}")

    # Create mock match object
    class TestMatch:
        pass

    match = TestMatch()
    match.home_team = "Test Home"
    match.away_team = "Test Away"
    match.league = "Test League"
    match.start_time = None
    match.opening_home_odd = 2.50
    match.current_home_odd = 2.10
    # Send test alert
    print("\n📤 Sending test alert...")
    try:
        send_alert(
            match_obj=match,
            news_summary="This is a test alert to verify Telegram workflow is working correctly.",
            news_url="https://example.com/test",
            score=9.5,
            league=match.league,
            combo_suggestion=None,
            combo_reasoning=None,
            recommended_market=None,
            math_edge=None,
            is_update=False,
            financial_risk=None,
            intel_source="test",
            referee_intel=None,
            twitter_intel=None,
            validated_home_team=None,
            validated_away_team=None,
            verification_info=None,
            final_verification_info=None,
            injury_intel=None,
            confidence_breakdown=None,
            is_convergent=False,
            convergence_sources=None,
            market_warning=None,  # V11.1 FIX: Explicitly pass market_warning (None for test)
        )
        print("✅ Test alert sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to send test alert: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_simple_alert()
    sys.exit(0 if success else 1)
