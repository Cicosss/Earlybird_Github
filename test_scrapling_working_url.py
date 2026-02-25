#!/usr/bin/env python3
"""Test Scrapling with a known working URL."""

import asyncio

from scrapling import AsyncFetcher


async def main():
    """Test Scrapling with different URLs."""
    print("Testing Scrapling with various URLs...")

    fetcher = AsyncFetcher()

    # Test 1: httpbin.org (should always work)
    print("\n1. Testing httpbin.org...")
    try:
        response = await fetcher.get(
            "https://httpbin.org/user-agent",
            timeout=10,
            impersonate="chrome",
            stealthy_headers=True,
        )
        print(f"   Status: {response.status}")
        print(f"   Length: {len(response.text)}")
        print(f"   First 200 chars: {response.text[:200]}")
        if response.status == 200:
            print("   ✅ SUCCESS - Scrapling is working!")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 2: example.com (should always work)
    print("\n2. Testing example.com...")
    try:
        response = await fetcher.get(
            "https://example.com", timeout=10, impersonate="chrome", stealthy_headers=True
        )
        print(f"   Status: {response.status}")
        print(f"   Length: {len(response.text)}")
        if response.status == 200:
            print("   ✅ SUCCESS - Scrapling is working!")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 3: Try a different Nitter instance with a different username
    print("\n3. Testing nitter.net with a different username...")
    try:
        response = await fetcher.get(
            "https://nitter.net/elonmusk", timeout=10, impersonate="chrome", stealthy_headers=True
        )
        print(f"   Status: {response.status}")
        print(f"   Length: {len(response.text)}")
        if response.status == 200:
            print("   ✅ SUCCESS - Scrapling can fetch from Nitter!")
        elif response.status == 403:
            print("   ⚠️ 403 Forbidden - Scrapling stealth may need adjustment")
        else:
            print(f"   ⚠️ Unexpected status: {response.status}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("If Test 1 and 2 succeeded, Scrapling is working correctly.")
    print("If Test 3 failed, the issue is with the Nitter instances, not Scrapling.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
