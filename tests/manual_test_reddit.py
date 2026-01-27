#!/usr/bin/env python3
"""
⚠️ DEPRECATED V8.0 - Reddit monitoring removed from EarlyBird.

Reddit provided NO betting edge - rumors arrived too late (already priced in).
This file is kept for backward compatibility and historical reference only.

Original description:
EarlyBird V3.8 - Reddit/Redlib Test Script
Tests the Redlib integration by fetching posts from r/soccer.
Verifies JSON parsing and instance failover.

Usage:
    python tests/manual_test_reddit.py
    
NOTE: This test may still work if reddit_monitor.py exists, but Reddit
is no longer used in the main pipeline.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from src.ingestion.reddit_monitor import (
    get_redlib_client,
    fetch_subreddit_posts,
    REDLIB_INSTANCES
)


def test_redlib():
    """Test Redlib fetch and JSON parsing."""
    print("=" * 60)
    print("🔴 REDLIB/REDDIT TEST")
    print("=" * 60)
    
    # Show configured instances
    print(f"\n📡 Configured Redlib Instances: {len(REDLIB_INSTANCES)}")
    for inst in REDLIB_INSTANCES:
        print(f"   - {inst}")
    
    # Test fetch
    print("\n🔄 Fetching posts from r/soccer...")
    posts = fetch_subreddit_posts("soccer", limit=5)
    
    if posts:
        print(f"\n✅ Fetched {len(posts)} posts from Redlib/Reddit")
        print("-" * 40)
        
        for i, post in enumerate(posts[:3], 1):
            title = post.get("title", "No title")
            author = post.get("author", "unknown")
            score = post.get("ups", 0) or post.get("score", 0)
            
            print(f"\n📌 Post {i}:")
            print(f"   Title: {title[:70]}{'...' if len(title) > 70 else ''}")
            print(f"   Author: {author}")
            print(f"   Score: {score}")
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS - Redlib/Reddit integration working!")
        return True
    else:
        print("\n❌ FAILED - All instances failed, no posts fetched")
        print("   Check network connectivity or instance availability")
        print("\n" + "=" * 60)
        return False


if __name__ == "__main__":
    success = test_redlib()
    sys.exit(0 if success else 1)
