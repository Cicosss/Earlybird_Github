#!/usr/bin/env python3
"""Test DDGS timeout and error handling with new configuration."""

from ddgs import DDGS
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

print("=" * 60)
print("Testing DDGS timeout and backend configuration")
print("=" * 60)

# Test 1: Timeout configuration
print("\n[Test 1] Timeout configuration")
try:
    ddgs = DDGS(timeout=10)
    print("✓ DDGS initialized with timeout=10")
except Exception as e:
    print(f"✗ Failed to initialize: {e}")

# Test 2: Backend parameter
print("\n[Test 2] Backend parameter (excluding Grokipedia)")
try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text('python programming', max_results=1, backend='duckduckgo,brave,bing,google')
    print(f"✓ Backend parameter works: {len(results)} results")
    print(f"✓ Engines used: duckduckgo,brave,bing,google (Grokipedia excluded)")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Long query (simulating insider news search)
print("\n[Test 3] Long query with site dorking")
long_query = 'site:twitter.com OR site:x.com @user1 OR @user2 OR @user3 football -basket -basketball'
try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text(long_query, max_results=1, backend='duckduckgo,brave,bing,google')
    print(f"✓ Long query works: {len(results)} results")
    print(f"✓ Query length: {len(long_query)} chars")
except Exception as e:
    print(f"✗ Error with long query: {e}")

# Test 4: Error handling
print("\n[Test 4] Error handling for invalid backend")
try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text('test', max_results=1, backend='invalid_engine')
    print(f"✗ Should have failed but got: {len(results)} results")
except Exception as e:
    print(f"✓ Error handling works: {type(e).__name__}")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
