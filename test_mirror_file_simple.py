#!/usr/bin/env python3
"""
Simple test to verify the mirror file exists and can be loaded.
"""

import json
import sys
from pathlib import Path


def main():
    """Test that the mirror file exists and can be loaded."""
    print("=" * 60)
    print("MIRROR FILE VERIFICATION TEST")
    print("=" * 60)

    mirror_path = Path("data/supabase_mirror.json")

    if not mirror_path.exists():
        print(f"\n❌ Mirror file not found at {mirror_path}")
        return False

    print(f"\n✅ Mirror file exists at {mirror_path}")

    # Load and validate the mirror file
    try:
        with open(mirror_path, "r", encoding="utf-8") as f:
            mirror_data = json.load(f)

        print("\n📊 Mirror file contents:")
        for key, value in mirror_data.items():
            if isinstance(value, list):
                print(f"  - {key}: {len(value)} records")
            elif isinstance(value, dict):
                if "tweets" in value:
                    print(f"  - {key}: {len(value.get('tweets', []))} tweets")
                else:
                    print(f"  - {key}: {len(value)} keys")
            else:
                print(f"  - {key}: {type(value).__name__}")

        # Check for news_sources
        if "news_sources" in mirror_data:
            news_sources = mirror_data["news_sources"]
            print(f"\n✅ News sources found: {len(news_sources)} sources")

            # Show first few sources
            print(f"\n📰 First {min(3, len(news_sources))} news sources:")
            for i, source in enumerate(news_sources[:3]):
                print(f"  {i + 1}. {source.get('name', 'Unknown')}")
                print(f"     URL: {source.get('url', 'No URL')}")
                print(f"     Domain: {source.get('domain', 'No domain')}")

            return True
        else:
            print("\n❌ No news_sources found in mirror file")
            return False

    except Exception as e:
        print(f"\n❌ Error loading mirror file: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASSED")
    else:
        print("❌ TEST FAILED")
    print("=" * 60)
    sys.exit(0 if success else 1)
