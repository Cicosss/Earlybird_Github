#!/usr/bin/env python3
"""
Isolated Scrapling Pilot Test with Live Supabase Data (V2 - Improved)
======================================================================

This script tests the Scrapling integration in NitterPool using real data
from the Supabase social_sources table. Uses local mirror for faster loading.

Output Requirements:
- Target Handle: The account being scraped
- Instance URL Used: The Nitter instance selected by the Circuit Breaker
- Bypass Status: Did Scrapling successfully bypass anti-bot measures (No 403s)?
- Data Yield: Total number of tweets extracted
- Data Sample: Text of the First Tweet to confirm handover from Scrapling to BeautifulSoup

Author: Strategic Testing Team
Date: 2026-02-25
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.services.nitter_pool import NitterPool

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

MIRROR_FILE = Path("data/supabase_mirror.json")


def load_social_sources_from_mirror() -> list:
    """Load social sources from local mirror."""
    if not MIRROR_FILE.exists():
        logger.error(f"❌ Mirror file not found: {MIRROR_FILE}")
        return []

    try:
        with open(MIRROR_FILE, encoding="utf-8") as f:
            mirror_data = json.load(f)

        social_sources = mirror_data.get("data", {}).get("social_sources", [])
        logger.info(f"✅ Loaded {len(social_sources)} social sources from mirror")
        return social_sources
    except Exception as e:
        logger.error(f"❌ Failed to load mirror: {e}")
        return []


async def test_single_handle(nitter_pool: NitterPool, handle: str, source_name: str) -> dict:
    """
    Test fetching tweets for a single handle.

    Args:
        nitter_pool: The NitterPool instance
        handle: Twitter handle to test
        source_name: Name of the source (for display)

    Returns:
        Dictionary containing test results
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"🎯 Testing Handle: @{handle} ({source_name})")
    logger.info(f"{'=' * 80}\n")

    result = {
        "handle": handle,
        "source_name": source_name,
        "instance_used": None,
        "bypass_status": "UNKNOWN",
        "data_yield": 0,
        "first_tweet": None,
        "error": None,
    }

    try:
        # Get the current healthy instance before fetching
        instance = await nitter_pool.get_healthy_instance()
        result["instance_used"] = instance if instance else "None available"

        if not instance:
            result["bypass_status"] = "FAILED - No healthy instances"
            result["error"] = "No healthy Nitter instances available"
            return result

        logger.info(f"📍 Instance Selected: {instance}")

        # Fetch tweets using the new Scrapling-powered method with timeout
        tweets = await asyncio.wait_for(
            nitter_pool.fetch_tweets_async(handle, max_retries=2),
            timeout=60,  # 60 second timeout per handle
        )

        # Determine bypass status based on whether we got data
        if tweets:
            result["bypass_status"] = "✅ SUCCESS - Anti-bot measures bypassed"
            result["data_yield"] = len(tweets)
            result["first_tweet"] = tweets[0].get("content", "") if tweets else None

            logger.info(f"✅ Bypass Status: {result['bypass_status']}")
            logger.info(f"📊 Data Yield: {result['data_yield']} tweets extracted")
            logger.info("\n📝 First Tweet Sample:")
            logger.info(f"{'-' * 80}")
            logger.info(f"{result['first_tweet']}")
            logger.info(f"{'-' * 80}\n")
        else:
            result["bypass_status"] = "⚠️ PARTIAL - No 403 but no data"
            result["error"] = "Request succeeded but no tweets found"
            logger.warning(f"⚠️ Bypass Status: {result['bypass_status']}")
            logger.warning("📊 Data Yield: 0 tweets extracted")

    except asyncio.TimeoutError:
        result["bypass_status"] = "❌ FAILED - Timeout"
        result["error"] = "Request timed out after 60 seconds"
        logger.error(f"❌ Timeout testing handle @{handle}")
    except Exception as e:
        result["bypass_status"] = "❌ FAILED - Exception occurred"
        result["error"] = str(e)
        logger.error(f"❌ Error testing handle @{handle}: {e}")

    return result


async def main():
    """
    Main test function that orchestrates the isolated Scrapling pilot test.
    """
    logger.info("\n" + "=" * 80)
    logger.info("🚀 ISOLATED SCRAPLING PILOT TEST - LIVE SUPABASE DATA (V2)")
    logger.info("=" * 80 + "\n")

    # Step 1: Load social sources from local mirror (faster than querying Supabase)
    logger.info("📦 Step 1: Loading social sources from local mirror...")
    social_sources = load_social_sources_from_mirror()

    if not social_sources:
        logger.error("❌ No social sources found in mirror")
        return

    # Filter for active Twitter handles and take first 2
    active_twitter_handles = [
        source
        for source in social_sources
        if source.get("platform") == "twitter" and source.get("is_active", True)
    ]

    if len(active_twitter_handles) < 2:
        logger.warning(f"⚠️ Only {len(active_twitter_handles)} active Twitter handles found")
        test_handles = active_twitter_handles
    else:
        test_handles = active_twitter_handles[:2]

    logger.info(f"✅ Found {len(test_handles)} handles to test:")
    for i, source in enumerate(test_handles, 1):
        handle = source.get("identifier", "UNKNOWN")
        name = source.get("source_name", "Unknown")
        logger.info(f"   {i}. @{handle} ({name})")

    # Step 2: Initialize NitterPool with Scrapling
    logger.info("\n🔧 Step 2: Initializing NitterPool with Scrapling...")
    nitter_pool = NitterPool()
    logger.info("✅ NitterPool initialized with Scrapling stealth capabilities")

    # Step 3: Test each handle
    logger.info("\n🧪 Step 3: Testing Scrapling against real targets...")
    results = []

    for source in test_handles:
        handle = source.get("identifier", "")
        name = source.get("source_name", "Unknown")

        if not handle:
            logger.warning(f"⚠️ Skipping source with no handle: {name}")
            continue

        result = await test_single_handle(nitter_pool, handle, name)
        results.append(result)

    # Step 4: Print Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80 + "\n")

    successful = 0
    failed = 0

    for i, result in enumerate(results, 1):
        logger.info(f"Test {i}: @{result['handle']} ({result['source_name']})")
        logger.info(f"  Instance Used: {result['instance_used']}")
        logger.info(f"  Bypass Status: {result['bypass_status']}")
        logger.info(f"  Data Yield: {result['data_yield']} tweets")
        if result["error"]:
            logger.info(f"  Error: {result['error']}")
        logger.info("")

        if result["data_yield"] > 0:
            successful += 1
        else:
            failed += 1

    logger.info("=" * 80)
    logger.info(f"Total Tests: {len(results)}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info("=" * 80 + "\n")

    # Step 5: Print Pool Statistics
    logger.info("📈 NitterPool Statistics:")
    pool_stats = nitter_pool.get_pool_stats()
    logger.info(f"  Total Instances: {pool_stats['total_instances']}")
    logger.info(f"  Healthy Instances: {pool_stats['healthy_instances']}")
    logger.info(f"  Total Calls: {pool_stats['total_calls']}")
    logger.info(f"  Successful Calls: {pool_stats['successful_calls']}")
    logger.info(f"  Success Rate: {pool_stats['success_rate']:.2%}")
    logger.info("")

    # Step 6: Print instance health details
    logger.info("🏥 Instance Health Details:")
    all_health = nitter_pool.get_all_health()
    for instance_url, health in all_health.items():
        state = health.state.value
        failures = health.consecutive_failures
        logger.info(f"  {instance_url}:")
        logger.info(f"    State: {state}")
        logger.info(f"    Consecutive Failures: {failures}")
        logger.info(f"    Total Calls: {health.total_calls}")
        logger.info(f"    Successful Calls: {health.successful_calls}")
    logger.info("")

    # Final verdict
    if successful == len(results):
        logger.info("🎉 ALL TESTS PASSED! Scrapling is working correctly with live data.")
    elif successful > 0:
        logger.info(f"⚠️ PARTIAL SUCCESS: {successful}/{len(results)} tests passed.")
    else:
        logger.error("❌ ALL TESTS FAILED. Scrapling integration needs debugging.")


if __name__ == "__main__":
    asyncio.run(main())
