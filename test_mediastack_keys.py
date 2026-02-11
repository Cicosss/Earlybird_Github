#!/usr/bin/env python3
"""
Test script to verify MediaStack API keys are correctly loaded and available.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    MEDIASTACK_ENABLED,
    MEDIASTACK_API_KEYS,
    MEDIASTACK_API_URL,
)

from src.ingestion.mediastack_provider import get_mediastack_provider

def test_mediastack_keys():
    """Test that MediaStack keys are loaded correctly."""
    print("=" * 60)
    print("🆘 MEDIASTACK API KEYS TEST")
    print("=" * 60)
    
    # Test 1: Check environment variables
    print("\n1️⃣ Checking environment variables...")
    print(f"   MEDIASTACK_ENABLED: {MEDIASTACK_ENABLED}")
    print(f"   MEDIASTACK_API_URL: {MEDIASTACK_API_URL}")
    print(f"   Number of API keys configured: {len([k for k in MEDIASTACK_API_KEYS if k])}")
    
    # Test 2: Check if keys are non-empty
    print("\n2️⃣ Checking API keys...")
    for i, key in enumerate(MEDIASTACK_API_KEYS, 1):
        if key:
            print(f"   ✅ MEDIASTACK_API_KEY_{i}: {key[:10]}...{key[-4:]}")
        else:
            print(f"   ❌ MEDIASTACK_API_KEY_{i}: EMPTY")
    
    # Test 3: Check provider availability
    print("\n3️⃣ Checking MediaStack provider...")
    provider = get_mediastack_provider()
    print(f"   Provider instance: {provider}")
    print(f"   Provider available: {provider.is_available()}")
    
    # Test 4: Check key rotator
    print("\n4️⃣ Checking key rotator...")
    print(f"   Key rotator available: {provider._key_rotator.is_available()}")
    current_key = provider._key_rotator.get_current_key()
    if current_key:
        print(f"   Current key: {current_key[:10]}...{current_key[-4:]}")
    else:
        print(f"   ❌ No current key available")
    
    # Summary
    print("\n" + "=" * 60)
    if provider.is_available():
        print("✅ SUCCESS: MediaStack is available and ready to use!")
        print("=" * 60)
        return True
    else:
        print("❌ FAILURE: MediaStack is NOT available!")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = test_mediastack_keys()
    sys.exit(0 if success else 1)
