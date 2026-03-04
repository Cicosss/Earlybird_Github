#!/usr/bin/env python3
"""Test Scrapling TextHandler behavior."""

import asyncio
from scrapling import AsyncFetcher


async def main():
    print("Testing Scrapling TextHandler...")
    fetcher = AsyncFetcher()

    try:
        response = await fetcher.get(
            "https://httpbin.org/html",
            timeout=10,
            impersonate="chrome",
            stealthy_headers=True,
        )

        print(f"\nResponse status: {response.status}")
        print(f"\nBody type: {type(response.body)}")
        print(f"Body length: {len(response.body)}")
        print(f"Body[:200]: {response.body[:200]}")

        print(f"\nText type: {type(response.text)}")
        print(f"Text length: {len(response.text)}")
        print(f"Text[:200]: {response.text[:200]}")

        # Test if text can be used as string
        print(f"\nIs text a string? {isinstance(response.text, str)}")
        print(
            f"Can use in string operations? {response.text.startswith('<!doctype') if len(response.text) > 0 else 'Empty'}"
        )

        # Test body.decode()
        print(f"\nBody decoded type: {type(response.body.decode('utf-8', errors='ignore'))}")
        print(f"Body decoded length: {len(response.body.decode('utf-8', errors='ignore'))}")
        print(f"Body decoded[:200]: {response.body.decode('utf-8', errors='ignore')[:200]}")

        # Compare
        decoded = response.body.decode("utf-8", errors="ignore")
        print(f"\nAre text and decoded equal? {response.text == decoded}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
