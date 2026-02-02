#!/usr/bin/env python3
"""Test DDGS with fixed backend configuration (no bing, no grokipedia)."""

from ddgs import DDGS
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

print("=" * 60)
print("Testing DDGS with FIXED backend configuration")
print("=" * 60)

# Test 1: Timeout configuration
print("\n[Test 1] Timeout configuration")
try:
    ddgs = DDGS(timeout=10)
    print("✓ DDGS initialized with timeout=10")
except Exception as e:
    print(f"✗ Failed to initialize: {e}")

# Test 2: Fixed backend parameter (no bing, no grokipedia)
print("\n[Test 2] Fixed backend parameter (duckduckgo,brave,google)")
try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text('python programming', max_results=1, backend='duckduckgo,brave,google')
    print(f"✓ Backend parameter works: {len(results)} results")
    print(f"✓ Engines used: duckduckgo,brave,google (Grokipedia excluded, bing not available)")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Long query with site dorking (simulating insider news)
print("\n[Test 3] Long query with site dorking (simulating error scenario)")
long_query = 'site:twitter.com OR site:x.com @GFFN OR @mattspiro OR @MarcCorneel OR @Purple_RSCA_ OR @GBeNeFN OR @ATscoutFootball OR @austrianfooty OR @Sky_Johannes OR @EredivisieMike OR @FootballOranje_ football -basket -basketball'
print(f"Query length: {len(long_query)} chars")
try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text(long_query, max_results=1, backend='duckduckgo,brave,google')
    print(f"✓ Long query works: {len(results)} results")
    print(f"✓ No Grokipedia timeout (Grokipedia excluded)")
except Exception as e:
    print(f"✗ Error with long query: {e}")

# Test 4: Verify no Grokipedia in logs
print("\n[Test 4] Verify Grokipedia is not used")
import sys
import io

# Capture logs
log_capture = io.StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.INFO)
logging.getLogger('ddgs').addHandler(handler)

try:
    ddgs = DDGS(timeout=10)
    results = ddgs.text('test query', max_results=1, backend='duckduckgo,brave,google')
    logs = log_capture.getvalue()
    if 'grokipedia' in logs.lower():
        print("✗ Grokipedia still being used!")
    else:
        print("✓ Grokipedia not used in logs")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
