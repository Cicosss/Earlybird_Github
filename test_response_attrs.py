#!/usr/bin/env python3
import asyncio

from scrapling import AsyncFetcher


async def test():
    f = AsyncFetcher()
    r = await f.get("https://example.com", timeout=10, impersonate="chrome")
    print("Status:", r.status)
    print("Has text:", hasattr(r, "text"))
    print("Has body:", hasattr(r, "body"))
    print("Text len:", len(r.text) if hasattr(r, "text") else "N/A")
    print("Body len:", len(r.body) if hasattr(r, "body") else "N/A")
    print("Body content:", r.body[:200] if hasattr(r, "body") else "N/A")


asyncio.run(test())
