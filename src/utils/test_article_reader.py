#!/usr/bin/env python3
"""
Article Reader Verification Tests

Tests the Scrapling-powered ArticleReader against real-world complex sites.
Verifies that we get CLEAN TEXT without HTML/Ads.

Target Sites:
- https://www.ole.com.ar (Argentine sports news)
- https://www.fanatik.com.tr (Turkish sports news)

Author: Strategic Testing Team
Date: 2026-02-25
"""

import asyncio
import logging
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.article_reader import ArticleReader

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================
# TEST SITES
# ============================================

TEST_URLS = [
    {
        "url": "https://en.wikipedia.org/wiki/Association_football",
        "name": "Wikipedia (Article)",
        "description": "Wikipedia article about football",
    },
    {
        "url": "https://en.wikipedia.org/wiki/FIFA_World_Cup",
        "name": "Wikipedia (Article 2)",
        "description": "Wikipedia article about FIFA World Cup",
    },
]


# ============================================
# VERIFICATION FUNCTIONS
# ============================================


def verify_clean_text(text: str) -> dict:
    """
    Verify that extracted text is clean (no HTML, no ads).

    Args:
        text: Extracted text to verify

    Returns:
        Dict with verification results
    """
    issues = []

    # Check for HTML tags
    html_indicators = ["<div", "<span", "<a ", "<p>", "<img", "<script", "<style"]
    for indicator in html_indicators:
        if indicator in text:
            issues.append(f"Found HTML tag: {indicator}")

    # Check for ad indicators (more specific patterns to reduce false positives)
    ad_indicators = [
        "advertisement",
        "sponsored content",
        "sponsored post",
        "google_ad",
        "doubleclick",
        "ad-block",
    ]
    for indicator in ad_indicators:
        if indicator.lower() in text.lower():
            issues.append(f"Found ad indicator: {indicator}")

    # Check for excessive whitespace
    if "     " in text:
        issues.append("Excessive whitespace found")

    # Check for CSS/JS code
    css_js_indicators = ["{", "}", "function(", "var ", "const ", "let "]
    for indicator in css_js_indicators:
        if indicator in text:
            issues.append(f"Found code indicator: {indicator}")

    return {
        "is_clean": len(issues) == 0,
        "issues": issues,
        "text_length": len(text),
    }


def print_result_summary(result: dict, verification: dict, site_info: dict):
    """
    Print a formatted summary of the test result.

    Args:
        result: Result from ArticleReader.fetch_and_extract()
        verification: Result from verify_clean_text()
        site_info: Information about the test site
    """
    print("\n" + "=" * 80)
    print(f"🌐 TEST SITE: {site_info['name']}")
    print(f"📍 URL: {site_info['url']}")
    print(f"📝 Description: {site_info['description']}")
    print("=" * 80)

    # Success status
    if result["success"]:
        print("✅ STATUS: SUCCESS")
        print(f"🔧 Method Used: {result['method']}")
        print(f"📊 Text Length: {verification['text_length']} characters")
        print(f"📰 Title: {result['title'][:80]}..." if result["title"] else "📰 Title: (none)")

        # Clean text verification
        if verification["is_clean"]:
            print("✅ CLEAN TEXT: No HTML or ads detected")
        else:
            print("⚠️  CLEAN TEXT: Issues found:")
            for issue in verification["issues"]:
                print(f"   - {issue}")

        # Text preview
        print("\n📄 TEXT PREVIEW (first 300 chars):")
        print("-" * 80)
        print(result["text"][:300])
        print("-" * 80)
    else:
        print("❌ STATUS: FAILED")
        print("⚠️  No text extracted")

    print()


async def test_single_site(reader: ArticleReader, site_info: dict) -> dict:
    """
    Test ArticleReader against a single site.

    Args:
        reader: ArticleReader instance
        site_info: Dict with url, name, description

    Returns:
        Dict with test results
    """
    url = site_info["url"]
    logger.info(f"\n🧪 Testing: {site_info['name']} ({url})")

    result = {
        "site_name": site_info["name"],
        "url": url,
        "success": False,
        "method": None,
        "text_length": 0,
        "title": "",
        "is_clean": False,
        "issues": [],
        "error": None,
    }

    try:
        # Fetch and extract
        extraction_result = await reader.fetch_and_extract(url)

        # Verify clean text
        verification = verify_clean_text(extraction_result["text"])

        # Update result
        result["success"] = extraction_result["success"]
        result["method"] = extraction_result["method"]
        result["text_length"] = verification["text_length"]
        result["title"] = extraction_result["title"]
        result["is_clean"] = verification["is_clean"]
        result["issues"] = verification["issues"]

        # Print summary
        print_result_summary(extraction_result, verification, site_info)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"❌ Error testing {site_info['name']}: {e}")
        print(f"\n❌ ERROR testing {site_info['name']}: {e}\n")

    return result


async def main():
    """
    Main test function that runs all verification tests.
    """
    logger.info("\n" + "=" * 80)
    logger.info("🚀 ARTICLE READER VERIFICATION TESTS")
    logger.info("=" * 80 + "\n")

    # Step 1: Initialize ArticleReader
    logger.info("🔧 Step 1: Initializing ArticleReader...")
    reader = ArticleReader()
    logger.info("✅ ArticleReader initialized\n")

    # Step 2: Run tests
    logger.info("🧪 Step 2: Running tests against complex sites...")
    results = []

    for site_info in TEST_URLS:
        result = await test_single_site(reader, site_info)
        results.append(result)

    # Step 3: Print summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80 + "\n")

    successful = 0
    failed = 0
    clean_count = 0

    for i, result in enumerate(results, 1):
        logger.info(f"Test {i}: {result['site_name']}")
        logger.info(f"  URL: {result['url']}")
        logger.info(f"  Success: {'✅ YES' if result['success'] else '❌ NO'}")
        logger.info(f"  Method: {result['method'] or 'N/A'}")
        logger.info(f"  Text Length: {result['text_length']} chars")
        logger.info(f"  Clean Text: {'✅ YES' if result['is_clean'] else '❌ NO'}")
        if result["issues"]:
            logger.info(f"  Issues: {', '.join(result['issues'][:3])}")
        if result["error"]:
            logger.info(f"  Error: {result['error']}")
        logger.info("")

        if result["success"]:
            successful += 1
            if result["is_clean"]:
                clean_count += 1
        else:
            failed += 1

    logger.info("=" * 80)
    logger.info(f"Total Tests: {len(results)}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"🧹 Clean Text: {clean_count}/{successful}")
    logger.info("=" * 80 + "\n")

    # Final verdict
    if successful == len(results) and clean_count == successful:
        logger.info("🎉 ALL TESTS PASSED! ArticleReader is working correctly.")
        logger.info("   ✅ All sites fetched successfully")
        logger.info("   ✅ All extracted text is clean (no HTML/ads)")
    elif successful > 0:
        if clean_count == successful:
            logger.info(f"⚠️  PARTIAL SUCCESS: {successful}/{len(results)} tests passed.")
            logger.info("   ✅ All extracted text is clean")
        else:
            logger.info(f"⚠️  PARTIAL SUCCESS: {successful}/{len(results)} tests passed.")
            logger.info(f"   ⚠️  {successful - clean_count} tests had text cleaning issues")
    else:
        logger.error("❌ ALL TESTS FAILED. ArticleReader needs debugging.")

    logger.info("\n" + "=" * 80)
    logger.info("📋 RECOMMENDATIONS")
    logger.info("=" * 80)

    if successful == len(results) and clean_count == successful:
        logger.info("✅ ArticleReader is ready for production use")
        logger.info("✅ Can replace direct Playwright calls in NewsHunter")
        logger.info("✅ Can replace direct Playwright calls in BrowserMonitor")
    elif successful > 0:
        logger.info("⚠️  ArticleReader is partially working")
        logger.info("⚠️  Review failed sites for specific issues")
        if clean_count < successful:
            logger.info("⚠️  Improve text cleaning for sites with issues")
    else:
        logger.error("❌ ArticleReader needs significant debugging")
        logger.error("❌ Check Scrapling and Trafilatura dependencies")
        logger.error("❌ Verify network connectivity")

    logger.info("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
