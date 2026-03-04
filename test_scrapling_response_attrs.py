#!/usr/bin/env python3
"""Test Scrapling Response attributes."""

import asyncio
from scrapling import AsyncFetcher


async def main():
    print("Testing Scrapling Response attributes...")
    fetcher = AsyncFetcher()

    try:
        response = await fetcher.get(
            "https://httpbin.org/status/200",
            timeout=10,
            impersonate="chrome",
            stealthy_headers=True,
        )

        print(f"\nResponse type: {type(response)}")
        print(f"\nAll non-private attributes:")
        for attr in [a for a in dir(response) if not a.startswith("_")]:
            try:
                val = getattr(response, attr)
                if not callable(val):
                    print(
                        f"  {attr}: {type(val).__name__} = {repr(val)[:100] if len(repr(val)) < 100 else repr(val)[:100] + '...'}"
                    )
            except:
                print(f"  {attr}: <error>")

        print(f"\n\nChecking specific attributes:")
        print(f"  Has 'status': {hasattr(response, 'status')}")
        print(f"  Has 'status_code': {hasattr(response, 'status_code')}")
        print(f"  Has 'ok': {hasattr(response, 'ok')}")
        print(f"  Has 'successful': {hasattr(response, 'successful')}")
        print(f"  Has 'body': {hasattr(response, 'body')}")
        print(f"  Has 'text': {hasattr(response, 'text')}")

        # Try to access body and text
        if hasattr(response, "body"):
            print(f"\n  body type: {type(response.body)}")
            print(f"  body length: {len(response.body)}")
            print(f"  body[:100]: {response.body[:100]}")

        if hasattr(response, "text"):
            print(f"\n  text type: {type(response.text)}")
            print(f"  text length: {len(response.text)}")
            print(f"  text[:100]: {response.text[:100]}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
