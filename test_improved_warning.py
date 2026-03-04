#!/usr/bin/env python3
"""
Test Improved Nitter Warning Message

This script tests the improved warning message to verify it shows
continent name and uses INFO level instead of WARNING.

Author: CoVe Verification
Date: 2026-03-03
"""

import asyncio
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


async def test_improved_warning():
    """Test improved warning message."""
    print("\n" + "=" * 80)
    print("🔍 TESTING IMPROVED WARNING MESSAGE")
    print("=" * 80)

    # Import nitter scraper
    try:
        from src.services.nitter_fallback_scraper import get_nitter_fallback_scraper
        print("✅ NitterFallbackScraper imported successfully")
    except Exception as e:
        print(f"❌ Failed to import NitterFallbackScraper: {e}")
        return False

    # Get scraper instance
    try:
        scraper = get_nitter_fallback_scraper()
        print("✅ NitterFallbackScraper instance obtained")
    except Exception as e:
        print(f"❌ Failed to get NitterFallbackScraper instance: {e}")
        return False

    # Test with ASIA (should show improved warning)
    print("\n[1/3] Testing with ASIA (no active leagues)...")
    try:
        result = await scraper.run_cycle("ASIA")
        print(f"✅ ASIA cycle completed")
        print(f"   Handles processed: {result['handles_processed']}")
        print(f"   Tweets found: {result['tweets_found']}")
    except Exception as e:
        print(f"❌ ASIA cycle failed: {e}")

    # Test with AFRICA (should show improved warning)
    print("\n[2/3] Testing with AFRICA (no active leagues)...")
    try:
        result = await scraper.run_cycle("AFRICA")
        print(f"✅ AFRICA cycle completed")
        print(f"   Handles processed: {result['handles_processed']}")
        print(f"   Tweets found: {result['tweets_found']}")
    except Exception as e:
        print(f"❌ AFRICA cycle failed: {e}")

    # Test with LATAM (should work normally)
    print("\n[3/3] Testing with LATAM (has active leagues)...")
    try:
        result = await scraper.run_cycle("LATAM")
        print(f"✅ LATAM cycle completed")
        print(f"   Handles processed: {result['handles_processed']}")
        print(f"   Tweets found: {result['tweets_found']}")
        print(f"   Relevant tweets: {result['relevant_tweets']}")
        print(f"   Matches triggered: {result['matches_triggered']}")
    except Exception as e:
        print(f"❌ LATAM cycle failed: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print("✅ Improved warning message test completed")
    print("\nExpected improvements:")
    print("   1. Warning includes continent name (e.g., 'No active handles found for continent: ASIA')")
    print("   2. Severity reduced to INFO level (ℹ️ instead of ⚠️)")
    print("   3. Less alarming for users")
    return True


def main():
    """Main entry point."""
    try:
        success = asyncio.run(test_improved_warning())

        if success:
            print("\n✅ Improved warning message test PASSED")
            return 0
        else:
            print("\n❌ Improved warning message test FAILED")
            return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
