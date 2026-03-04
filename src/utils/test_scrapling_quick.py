#!/usr/bin/env python3
"""
Quick diagnostic test for Scrapling integration
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.services.nitter_pool import NitterPool


async def quick_test():
    print("🔧 Initializing NitterPool...")
    nitter_pool = NitterPool()
    print("✅ NitterPool initialized")

    print("\n📍 Getting healthy instance...")
    instance = await nitter_pool.get_healthy_instance()
    print(f"✅ Healthy instance: {instance}")

    print("\n🧪 Testing fetch_tweets_async with a simple handle...")
    try:
        tweets = await asyncio.wait_for(
            nitter_pool.fetch_tweets_async("elonmusk", max_retries=1), timeout=30
        )
        print(f"✅ Fetched {len(tweets)} tweets")
        if tweets:
            print(f"📝 First tweet: {tweets[0].get('content', '')[:100]}...")
    except asyncio.TimeoutError:
        print("❌ Test timed out after 30 seconds")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(quick_test())
