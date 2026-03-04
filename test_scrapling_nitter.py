#!/usr/bin/env python3
"""
Test script for Scrapling integration with Nitter instances.

This script tests the stealth fetching capabilities of Scrapling by attempting
to fetch tweets from a strict Nitter instance (xcancel.com).
"""

import asyncio
import logging
from scrapling import AsyncFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_scrapling_fetch():
    """
    Test Scrapling's stealth fetching capabilities with a strict Nitter instance.
    """
    # Test with a known Twitter username
    username = "BBCSport"  # A popular sports account

    # Test with strict Nitter instance
    instance = "https://xcancel.com"

    logger.info(f"🧪 Testing Scrapling integration...")
    logger.info(f"📍 Target: {instance}/{username}")

    try:
        # Initialize Scrapling fetcher with stealth capabilities
        fetcher = AsyncFetcher()

        # Attempt 1: Try RSS feed first
        rss_url = f"{instance}/{username}/rss"
        logger.info(f"📡 Attempting RSS fetch from: {rss_url}")

        response = await fetcher.get(
            rss_url, timeout=10, impersonate="chrome", stealthy_headers=True
        )

        logger.info(f"📊 Response Status: {response.status}")

        if response.status == 200:
            logger.info(f"✅ RSS fetch successful!")
            logger.info(f"📄 Content length: {len(response.text)} characters")

            # Check if we got valid RSS content
            if "<?xml" in response.text or "<rss" in response.text:
                logger.info(f"✅ Valid RSS content detected")
                logger.info(f"📝 First 200 characters:\n{response.text[:200]}")
                return True
            else:
                logger.warning(f"⚠️ Response received but doesn't look like RSS")
                logger.warning(f"📝 First 200 characters:\n{response.text[:200]}")
        elif response.status == 403:
            logger.error(f"❌ 403 Forbidden - Scrapling stealth may not be working")
            return False
        elif response.status == 404:
            logger.warning(f"⚠️ 404 Not Found - User may not exist")
            return False
        else:
            logger.warning(f"⚠️ Unexpected status code: {response.status}")
            return False

    except Exception as e:
        logger.error(f"❌ Error during fetch: {e}")
        return False

    # Attempt 2: Fallback to HTML parsing
    try:
        html_url = f"{instance}/{username}"
        logger.info(f"🌐 Attempting HTML fetch from: {html_url}")

        response = await fetcher.get(
            html_url, timeout=10, impersonate="chrome", stealthy_headers=True
        )

        logger.info(f"📊 Response Status: {response.status}")

        if response.status == 200:
            logger.info(f"✅ HTML fetch successful!")
            logger.info(f"📄 Content length: {len(response.text)} characters")

            # Check if we got valid HTML content
            if "<html" in response.text or "<!DOCTYPE" in response.text:
                logger.info(f"✅ Valid HTML content detected")
                logger.info(f"📝 First 200 characters:\n{response.text[:200]}")
                return True
            else:
                logger.warning(f"⚠️ Response received but doesn't look like HTML")
                logger.warning(f"📝 First 200 characters:\n{response.text[:200]}")
        elif response.status == 403:
            logger.error(f"❌ 403 Forbidden - Scrapling stealth may not be working")
            return False
        elif response.status == 404:
            logger.warning(f"⚠️ 404 Not Found - User may not exist")
            return False
        else:
            logger.warning(f"⚠️ Unexpected status code: {response.status}")
            return False

    except Exception as e:
        logger.error(f"❌ Error during HTML fetch: {e}")
        return False

    return False


async def test_nitter_pool_integration():
    """
    Test the full NitterPool integration with Scrapling.
    """
    logger.info(f"🔄 Testing NitterPool integration...")

    try:
        from src.services.nitter_pool import NitterPool

        # Initialize NitterPool
        pool = NitterPool()

        # Test fetching tweets
        username = "BBCSport"
        logger.info(f"📍 Fetching tweets for @{username}...")

        tweets = await pool.fetch_tweets_async(username, max_retries=3)

        if tweets:
            logger.info(f"✅ Successfully fetched {len(tweets)} tweets!")
            logger.info(f"📝 First tweet content: {tweets[0]['content'][:100]}...")
            return True
        else:
            logger.warning(f"⚠️ No tweets fetched")
            return False

    except Exception as e:
        logger.error(f"❌ Error during NitterPool test: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """
    Main test function.
    """
    print("\n" + "=" * 80)
    print("SCRAPLING INTEGRATION TEST")
    print("=" * 80 + "\n")

    # Test 1: Direct Scrapling fetch
    print("\n" + "-" * 80)
    print("TEST 1: Direct Scrapling Fetch")
    print("-" * 80 + "\n")
    result1 = await test_scrapling_fetch()

    # Test 2: NitterPool integration
    print("\n" + "-" * 80)
    print("TEST 2: NitterPool Integration")
    print("-" * 80 + "\n")
    result2 = await test_nitter_pool_integration()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Test 1 (Direct Scrapling Fetch): {'✅ PASSED' if result1 else '❌ FAILED'}")
    print(f"Test 2 (NitterPool Integration): {'✅ PASSED' if result2 else '❌ FAILED'}")
    print("=" * 80 + "\n")

    if result1 or result2:
        print("SCRAPLING PILOT ACTIVE: Stealth fetch successful! 🎉\n")
    else:
        print("SCRAPLING PILOT FAILED: Stealth fetch unsuccessful. ❌\n")


if __name__ == "__main__":
    asyncio.run(main())
