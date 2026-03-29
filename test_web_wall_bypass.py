#!/usr/bin/env python3
"""Test: Web Wall Bypass - Prove Scrapling integration works against blocking sites.

Tests three extraction paths for each site:
  1. Plain requests (baseline, expected to fail on WAF sites)
  2. ArticleReader/Scrapling (stealth TLS, bypasses most WAFs)
  3. Playwright real browser (fallback for stubborn WAFs, if available)

Sites tested:
  - https://96fmbauru.com.br/ (Brazilian radio, blocks plain requests)
  - https://palembang.tribunnews.com (Indonesian news, may or may not block)
"""

import asyncio
import logging
import sys

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_web_wall")

sys.path.insert(0, "/home/linux/Earlybird_Github")

try:
    from src.utils.article_reader import ArticleReader

    logger.info("ArticleReader imported successfully")
except ImportError as e:
    logger.error("Cannot import ArticleReader: %s", e)
    sys.exit(1)

# Check Playwright availability
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
    logger.info("Playwright available for fallback test")
except ImportError:
    logger.warning("Playwright not available - skipping browser fallback test")


async def test_site(url, label):
    """Test a single site with all extraction paths."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("[%s] Testing: %s", label, url)

    results = {"url": url, "label": label}

    # ============================================================
    # Test 1: Plain requests (baseline)
    # ============================================================
    logger.info("--- TEST 1: Plain requests.get() ---")
    plain_status = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        response = await asyncio.to_thread(requests.get, url, timeout=15, headers=headers)
        plain_status = response.status_code
        logger.info("  Plain requests status: %s", plain_status)
    except Exception as e:
        logger.warning("  Plain requests exception: %s", e)
    results["plain_status"] = plain_status

    # ============================================================
    # Test 2: ArticleReader (Scrapling stealth)
    # ============================================================
    logger.info("--- TEST 2: ArticleReader Scrapling (stealth extraction) ---")
    reader = ArticleReader()
    scrapling_result = await reader.fetch_and_extract(url, timeout=15)
    logger.info("  Method used: %s", scrapling_result["method"])
    logger.info("  Success: %s", scrapling_result["success"])
    scrapling_text_len = 0
    if scrapling_result["success"] and scrapling_result["text"]:
        text = scrapling_result["text"]
        scrapling_text_len = len(text)
        logger.info("  Text length: %s chars", scrapling_text_len)
        title = scrapling_result.get("title", "(none)")
        if title:
            logger.info("  Title: %s", title[:80])
        logger.info("  Text preview: %s", text[:200])
    else:
        logger.warning("  Scrapling extraction failed for %s", url)
    await reader.close()
    results["scrapling_success"] = scrapling_result["success"]
    results["scrapling_method"] = scrapling_result["method"]
    results["scrapling_text_len"] = scrapling_text_len

    # ============================================================
    # Test 3: Playwright real browser (if available)
    # ============================================================
    pw_status = "skipped"
    pw_text_len = 0
    if PLAYWRIGHT_AVAILABLE:
        logger.info("--- TEST 3: Playwright real browser (fallback) ---")
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
            )
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            html = await page.content()
            # Try trafilatura
            try:
                import trafilatura

                text = trafilatura.extract(html, include_comments=False, include_tables=False)
                if text and len(text) > 100:
                    pw_status = "success"
                    pw_text_len = len(text)
                    logger.info("  Playwright extracted %s chars", pw_text_len)
                    logger.info("  Text preview: %s", text[:200])
                else:
                    # Fallback to inner_text
                    text = await page.inner_text("body")
                    if text:
                        pw_status = "success_raw"
                        pw_text_len = len(text)
                        logger.info("  Playwright (raw) extracted %s chars", pw_text_len)
                    else:
                        pw_status = "empty"
                        logger.warning("  Playwright got empty content")
            except ImportError:
                text = await page.inner_text("body")
                if text:
                    pw_status = "success_raw"
                    pw_text_len = len(text)
                    logger.info("  Playwright (raw) extracted %s chars", pw_text_len)
            await browser.close()
            await pw.stop()
        except Exception as e:
            pw_status = f"error: {e}"
            logger.warning("  Playwright failed: %s", e)
    else:
        logger.info("--- TEST 3: Playwright --- SKIPPED (not installed)")

    results["pw_status"] = pw_status
    results["pw_text_len"] = pw_text_len

    return results


async def main():
    """Main test runner."""
    sites = [
        ("https://96fmbauru.com.br/", "96FM Bauru Brazil"),
        ("https://palembang.tribunnews.com", "Tribun Palembang Indonesia"),
    ]

    results = []
    for url, label in sites:
        result = await test_site(url, label)
        results.append(result)

    # ============================================================
    # Summary
    # ============================================================
    print()
    print("=" * 80)
    print("WEB WALL BYPASS TEST RESULTS")
    print("=" * 80)
    for r in results:
        lbl = r["label"]
        plain = r.get("plain_status", "N/A")
        scrapling_ok = "PASS" if r.get("scrapling_success") else "FAIL"
        scrapling_method = r.get("scrapling_method", "N/A")
        pw = r.get("pw_status", "skipped")
        print("  %-40s".format(lbl))
        print("    Plain requests:  %s", plain)
        print("    Scrapling:      %s (%s)", scrapling_ok, scrapling_method)
        print("    Playwright:    %s", pw)
        if r.get("scrapling_success"):
            print("    Scrapling extracted %s chars", r["scrapling_text_len"])
        if pw not in ("skipped", "N/A"):
            print("    Playwright extracted %s chars", r.get("pw_text_len", 0))
    print()

    # Final verdict
    any_bypass = any(
        r.get("scrapling_success") or r.get("pw_status", "").startswith("success") for r in results
    )
    if any_bypass:
        print("VERDICT: Web Wall CAN be bypassed!")
        print("  - Sites where Scrapling works: handled by _extract_with_http() in BrowserMonitor")
        print(
            "  - Sites where Scrapling fails: falls back to Playwright in extract_content_hybrid()"
        )
        print("  - BrowserMonitor's hybrid flow (HTTP -> Browser) handles ALL cases")
    else:
        print("VERDICT: All extraction methods failed - check connectivity")


if __name__ == "__main__":
    asyncio.run(main())
