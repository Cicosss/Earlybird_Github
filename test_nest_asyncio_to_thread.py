#!/usr/bin/env python3
"""Test asyncio.to_thread() with nest_asyncio.apply()."""

import asyncio
import nest_asyncio


def blocking_function():
    """A blocking function that simulates a browser fetch."""
    import time

    time.sleep(1)
    return "Result from blocking function"


async def async_with_to_thread():
    """Async function that uses asyncio.to_thread()."""
    print("  Calling blocking function via asyncio.to_thread()...")
    result = await asyncio.to_thread(blocking_function)
    print(f"  Got result: {result}")
    return result


def main_sync():
    """Main function that runs async code with nest_asyncio."""
    print("1. Applying nest_asyncio...")
    nest_asyncio.apply()

    print("2. Running async code with asyncio.run()...")
    result = asyncio.run(async_with_to_thread())
    print(f"3. Final result: {result}")
    return result


if __name__ == "__main__":
    print("Testing asyncio.to_thread() with nest_asyncio.apply()...\n")
    try:
        result = main_sync()
        print("\n✅ SUCCESS: asyncio.to_thread() works with nest_asyncio.apply()")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
