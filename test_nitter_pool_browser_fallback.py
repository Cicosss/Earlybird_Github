#!/usr/bin/env python3
"""Test NitterPool browser fallback logic."""

import asyncio
from src.services.nitter_pool import NitterPool


async def main():
    print("Testing NitterPool browser fallback logic...\n")

    # Create NitterPool instance
    pool = NitterPool()

    # Test 1: Normal fetch (should work)
    print("Test 1: Normal fetch with a known handle...")
    try:
        tweets = await pool.fetch_tweets_async("elonmusk", max_retries=1)
        print(f"  ✅ Fetched {len(tweets)} tweets")
        if tweets:
            print(f"  First tweet: {tweets[0]['content'][:100]}...")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 2: Check pool stats
    print("\nTest 2: Pool statistics...")
    stats = pool.get_pool_stats()
    print(f"  Total instances: {stats['total_instances']}")
    print(f"  Healthy instances: {stats['healthy_instances']}")
    print(f"  Total calls: {stats['total_calls']}")
    print(f"  Successful calls: {stats['successful_calls']}")
    print(f"  Failed calls: {stats['failed_calls']}")

    # Test 3: Check instance health
    print("\nTest 3: Instance health...")
    all_health = pool.get_all_health()
    for instance, health in all_health.items():
        print(f"  {instance}:")
        print(f"    State: {health.state.value}")
        print(f"    Consecutive failures: {health.consecutive_failures}")
        print(f"    Total calls: {health.total_calls}")
        print(f"    Successful calls: {health.successful_calls}")


if __name__ == "__main__":
    asyncio.run(main())
