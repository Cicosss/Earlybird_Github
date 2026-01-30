"""
EarlyBird Article Reader - Deep Dive on Demand

Utility module for fetching and extracting full article content from URLs.
Uses Trafilatura for clean article extraction with fallback to raw text.

This module enables NewsHunter to upgrade shallow search results (metadata only)
into "Deep" content by visiting the URL and extracting the full article text.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Import centralized HTTP client
try:
    from src.utils.http_client import get_http_client
    _HTTP_CLIENT_AVAILABLE = True
except ImportError:
    _HTTP_CLIENT_AVAILABLE = False
    logger.warning("HTTP client not available for article_reader")

# Trafilatura import with fallback
try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False
    logger.warning("⚠️ [ARTICLE-READER] trafilatura not installed, using raw text extraction")


@dataclass
class ArticleResult:
    """
    Result of article fetch operation.
    
    Attributes:
        title: Article title
        content: Full article content (extracted text)
        url: Source URL
        success: Whether the fetch was successful
        error: Error message if success=False
        method: Extraction method used ('trafilatura', 'raw', 'error')
    """
    title: str
    content: str
    url: str
    success: bool
    error: Optional[str] = None
    method: str = "trafilatura"


def fetch_full_article(
    url: str,
    timeout: float = 15.0,
    use_fingerprint: bool = True
) -> ArticleResult:
    """
    Fetch and extract full article content from a URL.
    
    Strategy:
    1. Fetch page content using centralized HTTP client
    2. Extract article text using Trafilatura (clean extraction)
    3. Fallback to raw text extraction if Trafilatura fails
    4. Handle errors gracefully (timeouts, 404s, etc.)
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        use_fingerprint: Whether to use browser fingerprinting
        
    Returns:
        ArticleResult with title, content, and success status
        
    Examples:
        >>> result = fetch_full_article("https://example.com/news/article")
        >>> if result.success:
        ...     print(f"Title: {result.title}")
        ...     print(f"Content: {result.content[:200]}...")
    """
    if not url:
        return ArticleResult(
            title="",
            content="",
            url=url,
            success=False,
            error="Empty URL provided",
            method="error"
        )
    
    # Step 1: Fetch page content
    html_content = None
    try:
        if _HTTP_CLIENT_AVAILABLE:
            # Use centralized HTTP client
            client = get_http_client()
            response = client.get_sync(
                url,
                rate_limit_key="article_reader",
                use_fingerprint=use_fingerprint,
                timeout=timeout
            )
            html_content = response.text
        else:
            # Fallback to requests
            import requests
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            html_content = response.text
            
    except Exception as e:
        error_msg = f"Failed to fetch URL: {e}"
        logger.warning(f"⚠️ [ARTICLE-READER] {error_msg} | URL: {url[:60]}...")
        return ArticleResult(
            title="",
            content="",
            url=url,
            success=False,
            error=error_msg,
            method="error"
        )
    
    if not html_content:
        return ArticleResult(
            title="",
            content="",
            url=url,
            success=False,
            error="Empty HTML content",
            method="error"
        )
    
    # Step 2: Extract article text using Trafilatura
    if _TRAFILATURA_AVAILABLE:
        try:
            # Use Trafilatura for clean article extraction
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                extracted = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False
                )
                
                if extracted and len(extracted.strip()) > 100:
                    # Get title from Trafilatura
                    title = trafilatura.extract_title(downloaded) or ""
                    
                    logger.info(
                        f"✅ [ARTICLE-READER] Trafilatura extracted {len(extracted)} chars "
                        f"from {url[:60]}..."
                    )
                    
                    return ArticleResult(
                        title=title,
                        content=extracted,
                        url=url,
                        success=True,
                        method="trafilatura"
                    )
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")
    
    # Step 3: Fallback to raw text extraction
    try:
        import re
        from html import unescape
        
        # Remove script and style tags
        cleaned_html = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Extract text from HTML
        text = re.sub(r'<[^>]+>', ' ', cleaned_html)
        text = unescape(text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) > 100:
            # Try to extract title from <title> tag
            title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""
            
            logger.info(
                f"✅ [ARTICLE-READER] Raw text extracted {len(text)} chars "
                f"from {url[:60]}..."
            )
            
            return ArticleResult(
                title=title,
                content=text,
                url=url,
                success=True,
                method="raw"
            )
    except Exception as e:
        logger.debug(f"Raw text extraction failed: {e}")
    
    # All extraction methods failed
    error_msg = "All extraction methods failed"
    logger.warning(f"⚠️ [ARTICLE-READER] {error_msg} | URL: {url[:60]}...")
    
    return ArticleResult(
        title="",
        content="",
        url=url,
        success=False,
        error=error_msg,
        method="error"
    )


def should_deep_dive(
    title: str,
    snippet: str,
    triggers: list,
    snippet_threshold: int = 500
) -> bool:
    """
    Determine if a search result should trigger a deep dive.
    
    A deep dive is triggered when:
    1. Title or snippet contains high-value keywords
    2. Snippet is short (incomplete, < threshold chars)
    
    Args:
        title: Article title
        snippet: Article snippet/preview
        triggers: List of keywords that trigger deep dive
        snippet_threshold: Minimum snippet length to skip deep dive
        
    Returns:
        True if deep dive should be performed, False otherwise
        
    Examples:
        >>> triggers = ["injury", "squad", "lineup"]
        >>> should_deep_dive("Player injury update", "Short snippet...", triggers)
        True
        >>> should_deep_dive("Match preview", "Long detailed article content..." * 10, triggers)
        False
    """
    # Check if snippet is long enough (already complete)
    if snippet and len(snippet) >= snippet_threshold:
        return False
    
    # Combine title and snippet for keyword matching
    combined_text = f"{title} {snippet}".lower()
    
    # Check for any trigger keywords
    for trigger in triggers:
        if trigger.lower() in combined_text:
            logger.debug(
                f"🎯 [DEEP-DIVE] Trigger '{trigger}' found in: "
                f"'{title[:50]}...' (snippet: {len(snippet) if snippet else 0} chars)"
            )
            return True
    
    return False


def apply_deep_dive_to_results(
    results: list,
    triggers: list,
    max_articles: int = 3,
    timeout: float = 15.0
) -> list:
    """
    Apply deep dive logic to a list of search results.
    
    For each result:
    1. Check if it contains high-value keywords
    2. If yes and snippet is short, fetch full article
    3. If successful, replace snippet with full content
    4. Mark as 'deep_dive': True
    
    Args:
        results: List of search result dicts with 'title', 'snippet', 'link'
        triggers: List of keywords that trigger deep dive
        max_articles: Maximum articles to deep dive (to limit performance impact)
        timeout: Timeout for article fetch in seconds
        
    Returns:
        Updated list of results with deep dive applied
        
    Examples:
        >>> results = [{'title': 'Injury update', 'snippet': 'Short...', 'link': '...'}]
        >>> triggers = ['injury', 'squad']
        >>> updated = apply_deep_dive_to_results(results, triggers, max_articles=1)
        >>> updated[0].get('deep_dive')
        True
    """
    if not results:
        return results
    
    deep_dive_count = 0
    updated_results = []
    
    for result in results:
        # Copy result to avoid modifying original
        updated_result = result.copy()
        
        # Check if we should deep dive this result
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        link = result.get('link', '')
        
        if (deep_dive_count < max_articles and 
            link and 
            should_deep_dive(title, snippet, triggers)):
            
            # Perform deep dive
            logger.info(f"🔍 [DEEP-DIVE] Fetching full article: {title[:50]}...")
            
            article_result = fetch_full_article(link, timeout=timeout)
            
            if article_result.success:
                # Replace snippet with full content
                updated_result['snippet'] = article_result.content
                updated_result['deep_dive'] = True
                updated_result['deep_dive_method'] = article_result.method
                
                # Update title if we got a better one
                if article_result.title and len(article_result.title) > len(title):
                    updated_result['title'] = article_result.title
                
                deep_dive_count += 1
                
                logger.info(
                    f"✅ [DEEP-DIVE] Upgraded article ({deep_dive_count}/{max_articles}): "
                    f"{len(article_result.content)} chars"
                )
            else:
                # Deep dive failed, keep original shallow result
                updated_result['deep_dive'] = False
                updated_result['deep_dive_error'] = article_result.error
                
                logger.debug(
                    f"⚠️ [DEEP-DIVE] Failed to fetch: {article_result.error}"
                )
        else:
            # No deep dive needed or limit reached
            updated_result['deep_dive'] = False
        
        updated_results.append(updated_result)
    
    if deep_dive_count > 0:
        logger.info(f"📊 [DEEP-DIVE] Summary: {deep_dive_count}/{len(results)} articles upgraded")
    
    return updated_results
