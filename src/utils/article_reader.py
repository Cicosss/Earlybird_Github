"""
EarlyBird Article Reader - Scrapling Powered Deep Extraction

Centralized, stealthy article fetcher using Scrapling Hybrid Mode + Trafilatura.
Replaces direct Playwright calls with a robust, reusable extraction engine.

Strategy:
1. Fast Path: AsyncFetcher (HTTP) - Check status 200
2. Stealth Path: If 403/WAF detected, switch to Fetcher (Browser) in asyncio.to_thread
3. Cleanup: Pass HTML to Trafilatura for clean text extraction

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


# ============================================
# CORE CLASS
# ============================================


class ArticleReader:
    """
    Centralized article reader using Scrapling Hybrid Mode.

    This class provides a stealthy way to fetch full article text from URLs.
    It implements a hybrid strategy:

    1. Fast Path: AsyncFetcher (HTTP) - Try first for speed
    2. Stealth Path: If 403/WAF detected, use Fetcher (Browser) in asyncio.to_thread
    3. Cleanup: Trafilatura for clean text extraction

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

        Creates an AsyncFetcher instance for the fast HTTP path.
        Browser fetcher is created on-demand to avoid blocking initialization.
        """
        self.async_fetcher: Optional[AsyncFetcher] = None
        if _SCRAPLING_AVAILABLE and AsyncFetcher is not None:
            try:
                self.async_fetcher = AsyncFetcher()
                logger.debug("✅ [ARTICLE-READER] AsyncFetcher initialized")
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

        fetcher = Fetcher()
        response = fetcher.get(url, timeout=timeout, impersonate="chrome", stealthy_headers=True)
        return response.text

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
                logger.debug(f"✅ [ARTICLE-READER] Browser fetch successful: {url[:60]}...")
            except Exception as e:
                logger.warning(f"⚠️ [ARTICLE-READER] Browser fetch failed: {e}")

        # ============================================================
        # STEP 3: EXTRACT WITH TRAFILATURA
        # ============================================================
        if html_content and trafilatura is not None:
            logger.debug(f"🔍 [ARTICLE-READER] HTML content length: {len(html_content)} chars")
            try:
                # Extract clean text (no comments, no tables for cleaner output)
                text = trafilatura.extract(
                    html_content, include_comments=False, include_tables=False, no_fallback=False
                )

                # Extract title using regex (trafilatura.extract_title doesn't exist in this version)
                import re

                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL
                )
                title = title_match.group(1).strip() if title_match else ""

                logger.debug(
                    f"🔍 [ARTICLE-READER] Trafilatura returned: {len(text) if text else 0} chars"
                )
                logger.debug(
                    f"🔍 [ARTICLE-READER] Title extracted: {title[:50] if title else '(none)'}..."
                )

                # Validate extracted text
                if text and len(text.strip()) >= MIN_TEXT_LENGTH:
                    result["text"] = text.strip()
                    result["title"] = title
                    result["method"] = method_used
                    result["success"] = True

                    logger.info(
                        f"✅ [ARTICLE-READER] Successfully extracted {len(text)} chars "
                        f"using {method_used} method from {url[:60]}..."
                    )
                else:
                    logger.debug(
                        f"⚠️ [ARTICLE-READER] Extracted text too short "
                        f"({len(text) if text else 0} chars) from {url[:60]}..."
                    )
                    # Log a sample of what we got
                    if text:
                        logger.debug(f"🔍 [ARTICLE-READER] Text sample: {text[:200]}...")

            except Exception as e:
                logger.debug(f"⚠️ [ARTICLE-READER] Trafilatura extraction failed: {e}")
        else:
            logger.debug(f"⚠️ [ARTICLE-READER] No HTML content to extract from {url[:60]}...")

        return result


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
    candidates = []
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
