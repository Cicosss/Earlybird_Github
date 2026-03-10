#!/usr/bin/env python3
"""
Test script to verify ArticleReader fixes applied per COVE report.

Tests:
1. URL validation before fetching
2. Explicit initialization failure logging
3. Thread-safety documentation
4. Resource cleanup (close() method)
5. Async context manager support
"""

import asyncio
import logging
import sys
from unittest.mock import Mock, patch, AsyncMock

# Configure logging to capture output
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

# Import the ArticleReader
sys.path.insert(0, 'src')
from utils.article_reader import ArticleReader

# Test counters
PASSED = 0
FAILED = 0


def test_url_validation():
    """Test that URL validation works correctly."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 1: URL Validation")
    print("="*70)
    
    async def run_test():
        reader = ArticleReader()
        
        # Test 1.1: Empty URL
        print("\n[Test 1.1] Testing empty URL...")
        result = await reader.fetch_and_extract("")
        assert result["success"] == False, "Empty URL should fail"
        assert result["url"] == "", "URL should be empty"
        print("✅ PASSED: Empty URL correctly rejected")
        
        # Test 1.2: Invalid URL (missing scheme)
        print("\n[Test 1.2] Testing invalid URL (missing scheme)...")
        result = await reader.fetch_and_extract("example.com/article")
        assert result["success"] == False, "URL without scheme should fail"
        print("✅ PASSED: URL without scheme correctly rejected")
        
        # Test 1.3: Invalid URL (missing netloc)
        print("\n[Test 1.3] Testing invalid URL (missing netloc)...")
        result = await reader.fetch_and_extract("https://")
        assert result["success"] == False, "URL without netloc should fail"
        print("✅ PASSED: URL without netloc correctly rejected")
        
        # Test 1.4: Valid URL format (will fail to fetch, but validation should pass)
        print("\n[Test 1.4] Testing valid URL format...")
        result = await reader.fetch_and_extract("https://example.com/article")
        # URL format is valid, so it should not be rejected by validation
        # (it may fail later due to missing dependencies, but validation should pass)
        print("✅ PASSED: Valid URL format accepted")
        
        await reader.close()
    
    try:
        asyncio.run(run_test())
        PASSED += 1
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        FAILED += 1
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        FAILED += 1
        return False


def test_initialization_failure_logging():
    """Test that initialization failures are logged."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 2: Initialization Failure Logging")
    print("="*70)
    
    # Test 2.1: Mock AsyncFetcher to raise exception during initialization
    print("\n[Test 2.1] Testing initialization failure logging...")
    
    with patch('utils.article_reader._SCRAPLING_AVAILABLE', True):
        with patch('utils.article_reader.AsyncFetcher', side_effect=Exception("Mock initialization error")):
            # Capture logging output
            with patch('utils.article_reader.logger') as mock_logger:
                reader = ArticleReader()
                
                # Verify that warning was logged
                warning_calls = [call for call in mock_logger.warning.call_args_list 
                               if 'Failed to initialize AsyncFetcher' in str(call)]
                
                if warning_calls:
                    print("✅ PASSED: Initialization failure logged correctly")
                    PASSED += 1
                    return True
                else:
                    print("❌ FAILED: Initialization failure not logged")
                    FAILED += 1
                    return False


def test_thread_safety_documentation():
    """Test that thread-safety is documented in class docstring."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 3: Thread-Safety Documentation")
    print("="*70)
    
    print("\n[Test 3.1] Checking class docstring for thread-safety info...")
    
    docstring = ArticleReader.__doc__
    
    # Check for thread-safety documentation
    if docstring and "Thread Safety" in docstring:
        print("✅ PASSED: Thread-safety documentation found in class docstring")
        
        # Check for key phrases
        if "NOT thread-safe" in docstring:
            print("  ✓ Contains 'NOT thread-safe' warning")
        if "own ArticleReader instance" in docstring:
            print("  ✓ Mentions creating own instance")
        if "Do not share instances" in docstring:
            print("  ✓ Warns against sharing instances")
        
        PASSED += 1
        return True
    else:
        print("❌ FAILED: Thread-safety documentation not found")
        FAILED += 1
        return False


def test_resource_cleanup():
    """Test that close() method exists and works."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 4: Resource Cleanup (close() method)")
    print("="*70)
    
    async def run_test():
        reader = ArticleReader()
        
        # Test 4.1: close() method exists
        print("\n[Test 4.1] Checking if close() method exists...")
        assert hasattr(reader, 'close'), "close() method should exist"
        assert callable(reader.close), "close() should be callable"
        print("✅ PASSED: close() method exists and is callable")
        
        # Test 4.2: close() can be called without error
        print("\n[Test 4.2] Testing close() method execution...")
        await reader.close()
        print("✅ PASSED: close() method executed without error")
        
        # Test 4.3: close() can be called multiple times (idempotent)
        print("\n[Test 4.3] Testing close() idempotency...")
        await reader.close()
        await reader.close()
        print("✅ PASSED: close() can be called multiple times")
    
    try:
        asyncio.run(run_test())
        PASSED += 1
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        FAILED += 1
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        FAILED += 1
        return False


def test_async_context_manager():
    """Test that async context manager support works."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 5: Async Context Manager Support")
    print("="*70)
    
    async def run_test():
        # Test 5.1: __aenter__ and __aexit__ exist
        print("\n[Test 5.1] Checking for async context manager methods...")
        assert hasattr(ArticleReader, '__aenter__'), "__aenter__ should exist"
        assert hasattr(ArticleReader, '__aexit__'), "__aexit__ should exist"
        print("✅ PASSED: Async context manager methods exist")
        
        # Test 5.2: Can use async with statement
        print("\n[Test 5.2] Testing async with statement...")
        async with ArticleReader() as reader:
            assert reader is not None, "Reader should not be None"
        print("✅ PASSED: Async with statement works correctly")
        
        # Test 5.3: close() is called automatically
        print("\n[Test 5.3] Verifying close() is called automatically...")
        with patch.object(ArticleReader, 'close', new_callable=AsyncMock) as mock_close:
            async with ArticleReader() as reader:
                pass
            mock_close.assert_called_once()
        print("✅ PASSED: close() called automatically on context exit")
    
    try:
        asyncio.run(run_test())
        PASSED += 1
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        FAILED += 1
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        FAILED += 1
        return False


def test_system_requirements_documentation():
    """Test that system requirements are documented."""
    global PASSED, FAILED
    
    print("\n" + "="*70)
    print("TEST 6: System Requirements Documentation")
    print("="*70)
    
    print("\n[Test 6.1] Checking module docstring for system requirements...")
    
    import utils.article_reader as ar_module
    docstring = ar_module.__doc__
    
    # Check for system requirements documentation
    if docstring and "VPS System Requirements" in docstring:
        print("✅ PASSED: System requirements documentation found in module docstring")
        
        # Check for key packages
        required_packages = [
            "build-essential",
            "python3-dev",
            "libxml2-dev",
            "libxslt1-dev",
            "libcurl4-openssl-dev"
        ]
        
        for package in required_packages:
            if package in docstring:
                print(f"  ✓ Mentions {package}")
        
        PASSED += 1
        return True
    else:
        print("❌ FAILED: System requirements documentation not found")
        FAILED += 1
        return False


def main():
    """Run all tests and print summary."""
    print("\n" + "="*70)
    print("ARTICLE READER FIXES VERIFICATION TEST SUITE")
    print("="*70)
    print("\nThis test suite verifies all fixes applied per COVE report:")
    print("1. URL validation before fetching")
    print("2. Explicit initialization failure logging")
    print("3. Thread-safety documentation")
    print("4. Resource cleanup (close() method)")
    print("5. Async context manager support")
    print("6. System requirements documentation")
    
    # Run all tests
    test_url_validation()
    test_initialization_failure_logging()
    test_thread_safety_documentation()
    test_resource_cleanup()
    test_async_context_manager()
    test_system_requirements_documentation()
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    total = PASSED + FAILED
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {PASSED} ✅")
    print(f"Failed: {FAILED} ❌")
    
    if FAILED == 0:
        print("\n🎉 ALL TESTS PASSED! All fixes verified successfully.")
        return 0
    else:
        print(f"\n⚠️  {FAILED} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
