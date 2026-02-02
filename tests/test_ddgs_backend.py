#!/usr/bin/env python3
"""Test DDGS backend parameter support."""

from ddgs import DDGS

print("Testing DDGS backend parameter...")

try:
    ddgs = DDGS(timeout=10)
    print("✓ DDGS initialized with timeout=10")
    
    # Test backend parameter
    results = ddgs.text('test', max_results=1, backend='duckduckgo,brave')
    print(f"✓ Backend parameter works: {len(results)} results")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
