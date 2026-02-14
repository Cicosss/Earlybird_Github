#!/usr/bin/env python3
"""
Test script to verify Twitter Intel Cache Supabase integration.
Tests the handshake between twitter_intel_cache.py and Supabase.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("=" * 80)
print("🧪 TESTING TWITTER INTEL CACHE SUPABASE INTEGRATION")
print("=" * 80)

# Test 1: Import and check Supabase availability
print("\n[TEST 1] Checking Supabase provider availability...")
try:
    from src.services.twitter_intel_cache import (
        _SUPABASE_AVAILABLE,
        _SUPABASE_PROVIDER,
        get_social_sources_from_supabase
    )
    print(f"✅ _SUPABASE_AVAILABLE: {_SUPABASE_AVAILABLE}")
    print(f"✅ _SUPABASE_PROVIDER: {'Initialized' if _SUPABASE_PROVIDER else 'None'}")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Fetch social sources from Supabase
print("\n[TEST 2] Fetching social sources from Supabase...")
try:
    handles = get_social_sources_from_supabase()
    print(f"✅ Fetched {len(handles)} social sources")
    
    if handles:
        print(f"📋 Sample handles (first 5):")
        for i, handle in enumerate(handles[:5]):
            print(f"   {i+1}. {handle}")
        
        # Verify all handles start with @
        invalid_handles = [h for h in handles if not h.startswith('@')]
        if invalid_handles:
            print(f"⚠️  WARNING: Found {len(invalid_handles)} handles without @ prefix")
            print(f"   Examples: {invalid_handles[:3]}")
        else:
            print(f"✅ All {len(handles)} handles have @ prefix")
    else:
        print("⚠️  No handles returned (may be using fallback)")
except Exception as e:
    print(f"❌ Failed to fetch social sources: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Verify fallback mechanism
print("\n[TEST 3] Verifying fallback mechanism...")
try:
    from config.twitter_intel_accounts import get_all_twitter_handles
    local_handles = get_all_twitter_handles()
    print(f"✅ Local config has {len(local_handles)} handles")
    
    # Compare with Supabase
    if _SUPABASE_AVAILABLE and handles:
        print(f"📊 Comparison:")
        print(f"   Supabase: {len(handles)} handles")
        print(f"   Local:    {len(local_handles)} handles")
        
        # Check for overlap
        supabase_set = set(handles)
        local_set = set(local_handles)
        overlap = supabase_set & local_set
        only_supabase = supabase_set - local_set
        only_local = local_set - supabase_set
        
        print(f"   Overlap:  {len(overlap)} handles")
        print(f"   Only Supabase: {len(only_supabase)} handles")
        print(f"   Only Local: {len(only_local)} handles")
except Exception as e:
    print(f"❌ Failed to verify fallback: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Verify no direct calls to get_all_twitter_handles remain
print("\n[TEST 4] Checking for remaining direct calls to local config...")
import re
with open('src/services/twitter_intel_cache.py', 'r') as f:
    content = f.read()
    
# Count occurrences
local_calls = len(re.findall(r'get_all_twitter_handles\(\)', content))
supabase_calls = len(re.findall(r'get_social_sources_from_supabase\(\)', content))

print(f"   Direct calls to get_all_twitter_handles(): {local_calls}")
print(f"   Calls to get_social_sources_from_supabase(): {supabase_calls}")

# We expect 1 remaining call (the import statement) and 2 calls to the new function
if local_calls == 1 and supabase_calls >= 2:
    print("✅ Correct migration - only import statement remains")
else:
    print(f"⚠️  Unexpected call pattern - review needed")

print("\n" + "=" * 80)
print("✅ TWITTER INTEL CACHE SUPABASE INTEGRATION TEST COMPLETE")
print("=" * 80)
