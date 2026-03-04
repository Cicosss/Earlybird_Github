#!/usr/bin/env python3
"""Test NitterPool with Scrapling integration."""

import asyncio
import sys


async def main():
    """Test NitterPool integration."""
    print("Testing NitterPool with Scrapling...")
    sys.stdout.flush()

    try:
        from src.services.nitter_pool import NitterPool

        # Initialize NitterPool
        pool = NitterPool()
        print("NitterPool initialized successfully")
        sys.stdout.flush()

        # Test fetching tweets
        username = "BBCSport"
        print(f"Fetching tweets for @{username}...")
        sys.stdout.flush()

        tweets = await pool.fetch_tweets_async(username, max_retries=3)

        if tweets:
            print(f"✅ Successfully fetched {len(tweets)} tweets!")
            print(f"First tweet content: {tweets[0]['content'][:100]}...")
            print("\nSCRAPLING PILOT ACTIVE: Stealth fetch successful! 🎉")
            return True
        else:
            print("⚠️ No tweets fetched")
            print("\nSCRAPLING PILOT FAILED: Stealth fetch unsuccessful. ❌")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        print("\nSCRAPLING PILOT FAILED: Error occurred. ❌")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
