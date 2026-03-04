#!/usr/bin/env python3
"""Test Scrapling response content access."""

import asyncio
from scrapling import AsyncFetcher


async def main():
    """Test different ways to access response content."""
    print("Testing Scrapling response content access...")

    fetcher = AsyncFetcher()

    # Test with example.com
    print("\nTesting example.com...")
    response = await fetcher.get(
        "https://example.com", timeout=10, impersonate="chrome", stealthy_headers=True
    )

    print(f"Status: {response.status}")
    print(f"Type of response: {type(response)}")

    # Try different attributes
    print(f"\nTrying different attributes:")
    print(f"  response.text: {len(response.text) if hasattr(response, 'text') else 'N/A'} chars")
    print(f"  response.body: {len(response.body) if hasattr(response, 'body') else 'N/A'} bytes")
    print(
        f"  response.html_content: {len(response.html_content) if hasattr(response, 'html_content') else 'N/A'} chars"
    )

    # Check what attributes are available
    print(f"\nAvailable attributes:")
    for attr in dir(response):
        if not attr.startswith("_") and not callable(getattr(response, attr)):
            try:
                value = getattr(response, attr)
                if isinstance(value, (str, bytes)) and len(value) > 0 and len(value) < 500:
                    print(f"  {attr}: {value[:100]}...")
                elif isinstance(value, (str, bytes)):
                    print(f"  {attr}: {len(value)} chars/bytes")
                else:
                    print(f"  {attr}: {type(value)}")
            except:
                pass

    # Try to get content
    if hasattr(response, "body"):
        print(f"\nContent from body (first 200 chars):")
        print(response.body[:200].decode("utf-8", errors="ignore"))


if __name__ == "__main__":
    asyncio.run(main())
