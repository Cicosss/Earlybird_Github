#!/usr/bin/env python3
"""Test Scrapling with different Nitter instances."""

import asyncio
from scrapling import AsyncFetcher


async def test_instance(instance_url, username):
    """Test a specific Nitter instance."""
    print(f"\nTesting {instance_url}...")

    try:
        fetcher = AsyncFetcher()

        # Try RSS
        rss_url = f"{instance_url}/{username}/rss"
        print(f"  RSS URL: {rss_url}")

        response = await fetcher.get(
            rss_url, timeout=10, impersonate="chrome", stealthy_headers=True
        )

        print(f"  Status: {response.status}")
        print(f"  Length: {len(response.text)}")

        if response.status == 200 and len(response.text) > 0:
            print(f"  ✅ SUCCESS!")
            return True
        else:
            print(f"  ❌ FAILED")
            return False

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


async def main():
    """Test all Nitter instances."""
    instances = [
        "https://xcancel.com",
        "https://nitter.poast.org",
        "https://nitter.lucabased.xyz",
        "https://nitter.privacydev.net",
        "https://nitter.net",
    ]

    username = "BBCSport"

    print("=" * 80)
    print("SCRAPLING NITTER INSTANCE TEST")
    print("=" * 80)

    results = []
    for instance in instances:
        result = await test_instance(instance, username)
        results.append((instance, result))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for instance, result in results:
        status = "✅ WORKING" if result else "❌ FAILED"
        print(f"{instance}: {status}")

    print("=" * 80)

    # Check if any instance worked
    if any(result for _, result in results):
        print("\n✅ At least one instance is working with Scrapling!")
        print("SCRAPLING PILOT ACTIVE: Stealth fetch successful! 🎉\n")
    else:
        print("\n❌ No instances are working with Scrapling.")
        print("SCRAPLING PILOT FAILED: Stealth fetch unsuccessful. ❌\n")


if __name__ == "__main__":
    asyncio.run(main())
