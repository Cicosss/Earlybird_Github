#!/usr/bin/env python3
"""
Test script to verify Playwright version error handling fix.
This script tests the new error handling logic for playwright.__version__ access.
"""


def test_playwright_version_handling():
    """Test the error handling logic for Playwright version access."""
    print("Testing Playwright version error handling...")
    print("-" * 60)

    # Test 1: Try to access playwright.__version__ directly
    print("\n[Test 1] Accessing playwright.__version__ directly:")
    try:
        import playwright

        version = playwright.__version__
        print(f"✅ SUCCESS: Playwright v{version} (has __version__ attribute)")
    except AttributeError as e:
        print(f"⚠️  EXPECTED: {e}")
        print("   This is expected for Playwright 1.58.0+")

    # Test 2: Try to access playwright._repo_version.__version__
    print("\n[Test 2] Accessing playwright._repo_version.__version__:")
    try:
        from playwright._repo_version import __version__

        print(f"✅ SUCCESS: Playwright v{__version__} (from _repo_version)")
    except (ImportError, AttributeError) as e:
        print(f"❌ FAILED: {e}")

    # Test 3: Test the full error handling logic (as in news_radar.py)
    print("\n[Test 3] Full error handling logic:")
    try:
        import playwright

        try:
            version = playwright.__version__
            print(f"✅ SUCCESS: Playwright v{version} installed")
        except AttributeError:
            # Fallback: try to get version from _repo_version
            try:
                from playwright._repo_version import __version__

                print(f"✅ SUCCESS: Playwright v{__version__} installed (fallback)")
            except (ImportError, AttributeError):
                print("✅ SUCCESS: Playwright installed (version unknown)")
    except ImportError:
        print("❌ FAILED: Playwright Python package not installed")

    print("\n" + "-" * 60)
    print("Test completed!")


if __name__ == "__main__":
    test_playwright_version_handling()
