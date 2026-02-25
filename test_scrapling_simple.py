#!/usr/bin/env python3
"""Simple test for Scrapling."""

import asyncio

from scrapling import AsyncFetcher


async def main():
    print("Starting Scrapling test...")
    try:
        fetcher = AsyncFetcher()
        print("Fetcher created successfully")

        response = await fetcher.get(
            "https://xcancel.com/BBCSport/rss",
            timeout=10,
            impersonate="chrome",
            stealthy_headers=True,
        )
        print(f"Response status: {response.status}")
        print(f"Response length: {len(response.text)}")
        print(f"First 100 chars: {response.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
