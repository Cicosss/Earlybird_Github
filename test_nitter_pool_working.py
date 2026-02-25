#!/usr/bin/env python3
"""Test NitterPool with a known working username."""

import asyncio
import sys


async def main():
    """Test NitterPool integration with a known working username."""
    print("Testing NitterPool with Scrapling...")
    print("Using known working username: elonmusk")
    sys.stdout.flush()

    try:
        from src.services.nitter_pool import NitterPool

        # Initialize NitterPool
        pool = NitterPool()
        print("NitterPool initialized successfully")
        sys.stdout.flush()

        # Test fetching tweets with a known working username
        username = "elonmusk"
        print(f"Fetching tweets for @{username}...")
        sys.stdout.flush()

        tweets = await pool.fetch_tweets_async(username, max_retries=5)

        if tweets:
            print(f"\n✅ Successfully fetched {len(tweets)} tweets!")
            print(f"First tweet content: {tweets[0]['content'][:100]}...")
            print("\nSCRAPLING PILOT ACTIVE: Stealth fetch successful! 🎉")
            return True
        else:
            print("\n⚠️ No tweets fetched")
            print("This may be due to Nitter instance issues, not Scrapling.")
            print("\nSCRAPLING PILOT STATUS: Inconclusive - Nitter instances may be down.")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        print("\nSCRAPLING PILOT FAILED: Error occurred. ❌")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
