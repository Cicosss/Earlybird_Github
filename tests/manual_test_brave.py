#!/usr/bin/env python3
"""
Brave Search API Diagnostic Tool

Tests:
1. API connectivity
2. Response format validation
3. Field normalization (description -> summary)

Usage: python tests/manual_test_brave.py
"""
import sys
import os

# Setup path for root imports
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv()


def test_brave_search():
    """Test Brave Search API integration."""
    print("=" * 60)
    print("🔍 BRAVE SEARCH API DIAGNOSTIC")
    print("=" * 60)
    
    # Check API key
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        print("❌ BRAVE_API_KEY not found in environment")
        print("   Add BRAVE_API_KEY=your_key to .env file")
        return False
    
    print(f"✅ API Key found: {api_key[:8]}...{api_key[-4:]}")
    
    # Import provider
    try:
        from src.ingestion.brave_provider import BraveSearchProvider
        print("✅ BraveSearchProvider imported successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Initialize provider
    provider = BraveSearchProvider()
    
    if not provider.is_available():
        print("❌ Provider not available (check API key)")
        return False
    
    print("✅ Provider initialized and available")
    
    # Test search
    print("\n📡 Testing search query: 'Manchester United injury news'...")
    
    try:
        results = provider.search_news("Manchester United injury news", limit=3)
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return False
    
    if not results:
        print("⚠️ No results returned (API may be rate limited or query too specific)")
        return False
    
    print(f"✅ Got {len(results)} results")
    
    # Validate format
    print("\n📋 VALIDATING RESULT FORMAT:")
    print("-" * 40)
    
    first_result = results[0]
    keys = list(first_result.keys())
    print(f"Keys in result: {keys}")
    
    # Required keys for analyzer compatibility
    required_keys = ["title", "url", "summary"]
    missing_keys = [k for k in required_keys if k not in first_result]
    
    if missing_keys:
        print(f"❌ MISSING REQUIRED KEYS: {missing_keys}")
        print("   Analyzer expects: title, url, summary")
        return False
    
    print("✅ All required keys present (title, url, summary)")
    
    # Print first result
    print("\n📄 FIRST RESULT:")
    print("-" * 40)
    print(f"Title:   {first_result.get('title', 'N/A')[:60]}...")
    print(f"URL:     {first_result.get('url', 'N/A')[:60]}...")
    print(f"Summary: {first_result.get('summary', 'N/A')[:100]}...")
    print(f"Source:  {first_result.get('source', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("✅ BRAVE SEARCH INTEGRATION: PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_brave_search()
    sys.exit(0 if success else 1)
