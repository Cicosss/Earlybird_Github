"""
EarlyBird Article Reader - Scrapling Powered Deep Extraction

Centralized, stealthy article fetcher using Scrapling Hybrid Mode + Trafilatura.
Replaces direct Playwright calls with a robust, reusable extraction engine.

Strategy:
1. Fast Path: AsyncFetcher (HTTP) - Check status 200
2. Stealth Path: If 403/WAF detected, switch to Fetcher (Browser) in asyncio.to_thread
3. Cloudflare Path: If browser also fails, use StealthyFetcher (patchright) with solve_cloudflare
4. Cleanup: Pass HTML to Trafilatura for clean text extraction

Requirements: scrapling, trafilatura (both already in requirements.txt)

VPS System Requirements:
    The following system packages are required for VPS deployment:
    - build-essential (gcc, g++, make)
    - python3-dev
    - libxml2-dev (for lxml/Trafilatura)
    - libxslt1-dev (for lxml/Trafilatura)
    - libcurl4-openssl-dev (for curl_cffi/Scrapling)

    Install on Ubuntu/Debian:
        sudo apt-get update
        sudo apt-get install -y build-essential python3-dev libxml2-dev libxslt1-dev libcurl4-openssl-dev
"""

import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ============================================
# IMPORT SCRAPLING
# ============================================
try:
    from scrapling import AsyncFetcher, Fetcher

    _SCRAPLING_AVAILABLE = True
except ImportError:
    _SCRAPLING_AVAILABLE = False
    AsyncFetcher = None  # type: ignore
    Fetcher = None  # type: ignore
    logger.warning("⚠️ [ARTICLE-READER] Scrapling not available, article extraction disabled")

# ============================================
# IMPORT STEALTHY FETCHER (V12.6 Cloudflare Bypass)
# ============================================
try:
    from scrapling.fetchers import StealthyFetcher

    _STEALTHY_AVAILABLE = True
except ImportError:
    _STEALTHY_AVAILABLE = False
    StealthyFetcher = None  # type: ignore
    logger.debug(
        "⏭️ [ARTICLE-READER] StealthyFetcher not available "
        "(install patchright: playwright install chromium)"
    )

# ============================================
# IMPORT TRAFILATURA
# ============================================
try:
    import trafilatura

    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False
    trafilatura = None  # type: ignore
    logger.warning("⚠️ [ARTICLE-READER] Trafilatura not available, article extraction disabled")


# ============================================
# CONSTANTS
# ============================================

# Minimum text length to consider extraction successful
MIN_TEXT_LENGTH = 100

# Status codes that trigger browser fallback
WAF_STATUS_CODES = (403, 429)

# V12.6: Cloudflare challenge detection patterns
# If extracted text matches any of these, it's a challenge page, not real content
CLOUDFLARE_CHALLENGE_PATTERNS = (
    "javascript is disabled",
    "please enable javascript",
    "checking your browser",
    "please complete the security check",
    "attention required",
    "cloudflare",
    "ray id",
    "challenge-platform",
    "cf-browser-verification",
    "enable javascript to proceed",
    "a required part of this site couldn't load",
)


def _is_cloudflare_challenge(text: str) -> bool:
    """
    V12.6: Detect if extracted text is a Cloudflare challenge page.

    Cloudflare challenge pages often contain specific phrases like
    'JavaScript is disabled' or 'Please complete the security check'.
    Trafilatura can extract these as text, making them pass the
    MIN_TEXT_LENGTH check but they are not real content.

    Args:
        text: Extracted text to check

    Returns:
        True if the text appears to be a Cloudflare challenge page
    """
    if not text or len(text) < 50:
        return False
    text_lower = text.lower()
    match_count = sum(1 for pattern in CLOUDFLARE_CHALLENGE_PATTERNS if pattern in text_lower)
    # Require at least 2 pattern matches to avoid false positives
    return match_count >= 2


# ============================================
# CORE CLASS
# ============================================


class ArticleReader:
    """
    Centralized article reader using Scrapling Hybrid Mode.

    This class provides a stealthy way to fetch full article text from URLs.
    It implements a 3-tier hybrid strategy:

    1. Fast Path: AsyncFetcher (HTTP) - Try first for speed
    2. Stealth Path: If 403/WAF detected, use Fetcher (Browser) in asyncio.to_thread
    3. Cloudflare Path: If browser also fails, use StealthyFetcher (patchright) to solve challenges
    4. Cleanup: Trafilatura for clean text extraction

    This module will replace direct Playwright calls in NewsHunter and BrowserMonitor.

    Thread Safety:
        This class is NOT thread-safe. Each thread or concurrent task should create
        its own ArticleReader instance. Do not share instances across concurrent calls.
        The browser fetcher creates new Fetcher instances on each call, which is
        safe only when each ArticleReader instance is used by a single thread/task.

    Resource Management:
        Call the close() method when done to properly clean up resources.
        Use async context manager pattern for automatic cleanup:
            async with ArticleReader() as reader:
                result = await reader.fetch_and_extract(url)

    Example:
        >>> reader = ArticleReader()
        >>> result = await reader.fetch_and_extract("https://example.com/article")
        >>> if result["success"]:
        ...     print(f"Title: {result['title']}")
        ...     print(f"Text: {result['text'][:200]}...")
        >>> await reader.close()
    """

    def __init__(self):
        """
        Initialize the ArticleReader.

        Uses the AsyncFetcher class directly (Scrapling 0.4 pattern).
        In Scrapling 0.4, AsyncFetcher.get is a bound method on a pre-created
        singleton (__AsyncFetcherClientInstance__). Instantiating with AsyncFetcher()
        triggers a deprecation warning and is a no-op.
        """
        self.async_fetcher: Optional[type] = None
        if _SCRAPLING_AVAILABLE and AsyncFetcher is not None:
            try:
                # V15.0 FIX: Use the class directly, not an instance.
                # AsyncFetcher.get is already bound to the internal singleton.
                self.async_fetcher = AsyncFetcher
                logger.debug("✅ [ARTICLE-READER] AsyncFetcher initialized (class-level singleton)")
            except Exception as e:
                logger.warning(f"⚠️ [ARTICLE-READER] Failed to initialize AsyncFetcher: {e}")
                self.async_fetcher = None
        else:
            logger.debug(
                "⏭️ [ARTICLE-READER] AsyncFetcher not available, will use browser-only mode"
            )

    def _browser_fetch(self, url: str, timeout: int = 15) -> str:
        """
        Fetch content using synchronous Fetcher with browser impersonation.

        This is a blocking operation and should be run in asyncio.to_thread().
        Uses Chrome impersonation and stealthy headers to bypass WAFs.

        Args:
            url: URL to fetch
            timeout: Timeout for fetch operation in seconds (default: 15)

        Returns:
            HTML content as string

        Raises:
            Exception: If the fetch fails
        """
        if Fetcher is None:
            raise RuntimeError("Scrapling Fetcher not available")

        # V15.0 FIX: Use Fetcher class directly (no instantiation).
        # Scrapling 0.4: Fetcher.get is already a bound method on a pre-created singleton.
        # Calling Fetcher() triggers a deprecation warning and is a no-op.
        response = Fetcher.get(url, timeout=timeout, impersonate="chrome", stealthy_headers=True)
        return response.text

    def _stealthy_fetch(self, url: str, timeout: int = 60) -> str:
        """
        V12.6: Fetch content using StealthyFetcher (patchright-based Cloudflare solver).

        This is the 3rd-tier fallback for sites that block both HTTP and browser impersonation.
        Uses patchright (undetected Playwright fork) with Cloudflare challenge solving.
        Creates a one-off browser instance that is destroyed immediately after fetch.

        This is a blocking operation and should be run in asyncio.to_thread().

        Args:
            url: URL to fetch
            timeout: Timeout for fetch operation in seconds (default: 60)

        Returns:
            HTML content as string

        Raises:
            Exception: If the fetch fails or StealthyFetcher is not available
        """
        if StealthyFetcher is None:
            raise RuntimeError("StealthyFetcher not available (patchright not installed)")

        page = StealthyFetcher.fetch(
            url,
            headless=True,
            solve_cloudflare=True,
            block_webrtc=True,
            hide_canvas=True,
            timeout=timeout * 1000,  # StealthyFetcher uses milliseconds
        )
        # Scrapling Adaptor/Response exposes HTML via .text attribute
        html = page.text if hasattr(page, "text") else str(page)
        return html

    async def close(self):
        """
        Clean up resources used by the ArticleReader.

        This method should be called when the ArticleReader instance is no longer needed.
        It properly closes the AsyncFetcher connection pool if available.

        Example:
            >>> reader = ArticleReader()
            >>> result = await reader.fetch_and_extract(url)
            >>> await reader.close()
        """
        if self.async_fetcher:
            try:
                # Check if AsyncFetcher has a close method
                if hasattr(self.async_fetcher, "close"):
                    await self.async_fetcher.close()
                    logger.debug("✅ [ARTICLE-READER] AsyncFetcher closed")
                else:
                    logger.debug(
                        "✅ [ARTICLE-READER] AsyncFetcher cleanup completed (no close method)"
                    )
            except Exception as e:
                logger.warning(f"⚠️ [ARTICLE-READER] Failed to close AsyncFetcher: {e}")

    async def __aenter__(self):
        """
        Async context manager entry.

        Returns:
            Self for use in async with statement
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Automatically calls close() when exiting the context.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        await self.close()

    async def fetch_and_extract(self, url: str, timeout: int = 15) -> dict:
        """
        Fetch and extract article content using hybrid strategy.

        Hybrid Scraping Pattern:
        1. Fast Path: Try AsyncFetcher (HTTP) first
           - If status 200, use the content
           - If status 403/429 (WAF), switch to browser
        2. Stealth Path: If HTTP fails, use Fetcher (Browser) in asyncio.to_thread
        3. Cleanup: Extract clean text using Trafilatura

        Args:
            url: URL to fetch and extract
            timeout: Timeout for fetch operations in seconds (default: 15)

        Returns:
            Dict with keys:
                - url: str - The URL that was fetched
                - title: str - Article title (from Trafilatura)
                - text: str - Cleaned article body text
                - method: str - "http" or "browser" (which method succeeded)
                - success: bool - True if extraction succeeded

            If extraction fails, text and title will be empty strings and success=False.
        """
        result = {"url": url, "title": "", "text": "", "method": "http", "success": False}

        # Validate URL
        if not url:
            logger.warning("⚠️ [ARTICLE-READER] Empty URL provided")
            return result

        # Validate URL format
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                logger.warning(f"⚠️ [ARTICLE-READER] Invalid URL format: {url[:60]}...")
                return result
        except Exception as e:
            logger.warning(f"⚠️ [ARTICLE-READER] URL parsing failed: {e}")
            return result

        # Check dependencies
        if not _SCRAPLING_AVAILABLE:
            logger.warning("⚠️ [ARTICLE-READER] Scrapling not available")
            return result

        if not _TRAFILATURA_AVAILABLE:
            logger.warning("⚠️ [ARTICLE-READER] Trafilatura not available")
            return result

        html_content: Optional[str] = None
        method_used = "http"

        # ============================================================
        # STEP 1: FAST PATH - AsyncFetcher (HTTP)
        # ============================================================
        if self.async_fetcher:
            try:
                response = await self.async_fetcher.get(
                    url, timeout=timeout, impersonate="chrome", stealthy_headers=True
                )

                if response.status == 200:
                    # Success - use response.body.decode() (not response.text)
                    # Based on NitterPool pattern (line 673)
                    html_content = response.body.decode("utf-8", errors="ignore")
                    logger.debug(f"✅ [ARTICLE-READER] HTTP fetch successful: {url[:60]}...")
                elif response.status in WAF_STATUS_CODES:
                    # WAF detected - switch to browser
                    logger.warning(
                        f"⚠️ [ARTICLE-READER] WAF detected (status {response.status}), "
                        f"switching to browser: {url[:60]}..."
                    )
                    method_used = "browser"
                else:
                    logger.warning(f"⚠️ [ARTICLE-READER] HTTP {response.status} for {url[:60]}...")
                    # Try browser fallback for other errors too
                    method_used = "browser"

            except Exception as e:
                logger.debug(f"⚠️ [ARTICLE-READER] AsyncFetcher failed: {e}")
                method_used = "browser"

        # ============================================================
        # STEP 2: STEALTH PATH - Browser fetcher (if needed)
        # ============================================================
        if html_content is None and method_used == "browser":
            try:
                html_content = await asyncio.to_thread(self._browser_fetch, url, timeout)
                if html_content:
                    logger.debug(f"✅ [ARTICLE-READER] Browser fetch successful: {url[:60]}...")
                else:
                    # Browser returned empty content (e.g., 403 with empty body)
                    # Reset to None so StealthyFetcher can attempt
                    logger.debug(
                        f"⚠️ [ARTICLE-READER] Browser returned empty content: {url[:60]}..."
                    )
                    html_content = None
            except Exception as e:
                logger.warning(f"⚠️ [ARTICLE-READER] Browser fetch failed: {e}")

        # ============================================================
        # STEP 3: CLOUDFLARE BYPASS - StealthyFetcher (if both HTTP and browser failed)
        # V12.6: Uses patchright (undetected Playwright fork) with solve_cloudflare=True.
        # One-off fetch: browser is created and destroyed within this call.
        # Only triggered when tier 1 (HTTP) and tier 2 (browser) both failed to
        # produce usable content (html_content is None or empty).
        # ============================================================
        stealthy_attempted = False
        if not html_content and _STEALTHY_AVAILABLE:
            try:
                stealthy_attempted = True
                method_used = "stealthy"
                html_content = await asyncio.to_thread(self._stealthy_fetch, url, 60)
                logger.info(
                    f"✅ [ARTICLE-READER] StealthyFetcher bypassed Cloudflare: {url[:60]}..."
                )
            except Exception as e:
                logger.warning(f"⚠️ [ARTICLE-READER] StealthyFetcher failed: {e}")

        # ============================================================
        # STEP 4: EXTRACT WITH TRAFILATURA
        # ============================================================
        if html_content and trafilatura is not None:
            logger.debug(f"🔍 [ARTICLE-READER] HTML content length: {len(html_content)} chars")

            text, title = self._extract_with_trafilatura(html_content)

            # Validate extracted text
            if text and len(text.strip()) >= MIN_TEXT_LENGTH and not _is_cloudflare_challenge(text):
                result["text"] = text.strip()
                result["title"] = title
                result["method"] = method_used
                result["success"] = True

                logger.info(
                    f"✅ [ARTICLE-READER] Successfully extracted {len(text)} chars "
                    f"using {method_used} method from {url[:60]}..."
                )
            else:
                if text and _is_cloudflare_challenge(text):
                    logger.warning(
                        f"🛡️ [ARTICLE-READER] Cloudflare challenge page detected "
                        f"({len(text)} chars) from {url[:60]}..."
                    )
                else:
                    logger.debug(
                        f"⚠️ [ARTICLE-READER] Extracted text too short "
                        f"({len(text) if text else 0} chars) from {url[:60]}..."
                    )
                    if text:
                        logger.debug(f"🔍 [ARTICLE-READER] Text sample: {text[:200]}...")

                # V12.6: Post-Trafilatura StealthyFetcher retry.
                # Handles cases where HTTP returned 200 with a Cloudflare challenge page
                # (e.g., besoccer.com returns 3099 chars of JS, not real content).
                # Only retry if we haven't already tried StealthyFetcher.
                if not stealthy_attempted and _STEALTHY_AVAILABLE:
                    try:
                        method_used = "stealthy"
                        stealthy_html = await asyncio.to_thread(self._stealthy_fetch, url, 60)
                        logger.info(
                            f"✅ [ARTICLE-READER] StealthyFetcher retry (post-trafilatura): "
                            f"{url[:60]}..."
                        )

                        text, title = self._extract_with_trafilatura(stealthy_html)
                        if (
                            text
                            and len(text.strip()) >= MIN_TEXT_LENGTH
                            and not _is_cloudflare_challenge(text)
                        ):
                            result["text"] = text.strip()
                            result["title"] = title
                            result["method"] = method_used
                            result["success"] = True
                            logger.info(
                                f"✅ [ARTICLE-READER] StealthyFetcher retry succeeded: "
                                f"{len(text)} chars from {url[:60]}..."
                            )
                    except Exception as e:
                        logger.warning(f"⚠️ [ARTICLE-READER] StealthyFetcher retry failed: {e}")

        else:
            logger.debug(f"⚠️ [ARTICLE-READER] No HTML content to extract from {url[:60]}...")

        return result

    @staticmethod
    def _extract_with_trafilatura(html_content: str) -> tuple[str, str]:
        """
        Extract clean text and title from HTML using Trafilatura.

        Args:
            html_content: Raw HTML content

        Returns:
            Tuple of (extracted_text, extracted_title). Either may be empty string
            if extraction fails.
        """
        import re

        text = ""
        title = ""

        if trafilatura is not None:
            try:
                text = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                )
                text = text or ""
            except Exception:
                text = ""

            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL
            )
            title = title_match.group(1).strip() if title_match else ""

        return text, title


# ============================================
# PUBLIC API
# ============================================

__all__ = ["ArticleReader", "apply_deep_dive_to_results"]


# ============================================
# DEEP DIVE ON DEMAND
# ============================================


async def apply_deep_dive_to_results(
    results: list[dict], triggers: list[str], max_articles: int = 3, timeout: int = 15
) -> list[dict]:
    """
    Apply deep dive to search results by fetching full article text.

    This function upgrades shallow search results to full article content
    for high-value keywords (injury, squad, transfer, etc.).

    Strategy:
    1. Iterate through search results
    2. Check if snippet contains trigger keywords
    3. Select top N candidates (default: 3)
    4. For each candidate, fetch full article text using ArticleReader
    5. If fetch succeeds, overwrite snippet with full_text (truncated to 2000 chars)
    6. Add [DEEP DIVE] prefix to the summary so the AI knows it's full text
    7. Wrap in try/except to ensure one bad link doesn't crash the whole hunter

    Args:
        results: List of search result dictionaries from NewsHunter
        triggers: List of keywords that trigger deep dive (e.g., ["injury", "squad"])
        max_articles: Maximum number of articles to deep dive (default: 3)
        timeout: Timeout for article fetch in seconds (default: 15)

    Returns:
        Updated list of results with deep-dived content where successful

    Example:
        >>> results = [
        ...     {"title": "Player injured", "snippet": "...", "link": "https://example.com/article1"},
        ...     {"title": "Match preview", "snippet": "...", "link": "https://example.com/article2"},
        ... ]
        >>> triggers = ["injury", "squad"]
        >>> enhanced_results = await apply_deep_dive_to_results(results, triggers, max_articles=2)
    """
    if not results:
        return results

    if not triggers:
        return results

    # Create ArticleReader instance
    reader = ArticleReader()

    # Identify candidates for deep dive
    candidates: list[dict] = []
    for item in results:
        # Skip items that already have deep dive
        if item.get("deep_dive"):
            continue

        # FIX #3: Skip deep dive if snippet is already long enough (>= 500 chars)
        snippet_length = len(item.get("snippet", ""))
        if snippet_length >= 500:
            logger.debug(
                f"⏭️ [DEEP-DIVE] Skipping long snippet ({snippet_length} chars): {item.get('title', '')[:60]}..."
            )
            continue

        # Get text to analyze (title + snippet)
        text_to_analyze = ""
        if item.get("title"):
            text_to_analyze += item["title"] + " "
        if item.get("snippet"):
            text_to_analyze += item["snippet"]

        # Check if any trigger keyword is present (case-insensitive)
        text_lower = text_to_analyze.lower()
        triggered_by = None
        for trigger in triggers:
            if trigger.lower() in text_lower:
                triggered_by = trigger
                break

        if triggered_by:
            candidates.append(
                {
                    "item": item,
                    "trigger": triggered_by,
                    "url": item.get("link", ""),
                }
            )

    # Limit to max_articles
    candidates = candidates[:max_articles]

    if not candidates:
        logger.debug("🔍 [DEEP-DIVE] No candidates found for deep dive")
        return results

    logger.info(f"🔍 [DEEP-DIVE] Found {len(candidates)} candidates, fetching full text...")

    # V11.0 TURBO: Parallel fetch for Deep Dive articles using asyncio.gather
    async def _fetch_single_candidate(candidate: dict) -> dict:
        """Fetch full article text for a single candidate (helper for parallel execution)."""
        item = candidate["item"]
        url = candidate["url"]
        trigger = candidate["trigger"]

        # Skip if no URL
        if not url:
            logger.debug("⚠️ [DEEP-DIVE] Skipping item with no URL")
            return None

        # Skip Twitter URLs (already have full content)
        if "twitter.com" in url or "x.com" in url:
            logger.debug(f"⏭️ [DEEP-DIVE] Skipping Twitter URL: {url[:60]}...")
            return None

        try:
            # Fetch full article text with timeout
            result = await reader.fetch_and_extract(url, timeout=timeout)

            if result["success"]:
                # Truncate to 2000 chars
                full_text = result["text"][:2000]

                # Save original snippet BEFORE overwriting
                original_snippet = item.get("snippet", "")
                item["deep_dive_original_snippet"] = original_snippet[:500]

                # Overwrite snippet with full text
                item["snippet"] = full_text

                # Add deep dive metadata
                item["deep_dive"] = True
                item["deep_dive_trigger"] = trigger
                item["deep_dive_method"] = result["method"]

                # Add [DEEP DIVE] prefix to title for AI visibility
                if item.get("title"):
                    item["title"] = f"[DEEP DIVE] {item['title']}"

                logger.info(
                    f"✅ [DEEP-DIVE] Upgraded article ({trigger}): {item.get('title', '')[:60]}..."
                )
                return {"success": True, "item": item, "url": url}
            else:
                logger.debug(f"⚠️ [DEEP-DIVE] Failed to fetch: {url[:60]}...")
                return None

        except Exception as e:
            logger.warning(f"⚠️ [DEEP-DIVE] Error fetching {url[:60]}...: {e}")
            return None

    # V11.0 TURBO: Execute all fetches in parallel with return_exceptions=True for safety
    fetch_results = await asyncio.gather(
        *[_fetch_single_candidate(c) for c in candidates], return_exceptions=True
    )

    # Log any exceptions that were caught
    for i, result in enumerate(fetch_results):
        if isinstance(result, Exception):
            logger.warning(f"⚠️ [DEEP-DIVE] Exception in parallel fetch {i}: {result}")

    return results
