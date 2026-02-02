"""
EarlyBird Trafilatura Extractor - Centralized Content Extraction

This module provides a centralized, resilient wrapper around trafilatura
for article content extraction. It addresses the common "discarding data: None"
warnings by:

1. Pre-validating HTML before extraction
2. Silencing trafilatura internal warnings
3. Implementing intelligent fallback extraction
4. Providing consistent logging across all components

Used by: news_radar, browser_monitor, article_reader

Requirements: Centralizes trafilatura usage and prevents data loss
"""

import logging
import re
from typing import Optional, Tuple
from html import unescape

logger = logging.getLogger(__name__)

# ============================================
# TRAFILATURA IMPORT WITH WARNING SUPPRESSION
# ============================================

# Suppress trafilatura internal warnings at import time
# These "discarding data: None" warnings are expected for certain HTML formats
_trafilatura_logger = logging.getLogger('trafilatura')
_trafilatura_logger.setLevel(logging.ERROR)  # Only show errors, not warnings
_trafilatura_core_logger = logging.getLogger('trafilatura.core')
_trafilatura_core_logger.setLevel(logging.ERROR)

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    trafilatura = None  # type: ignore


# ============================================
# CONSTANTS
# ============================================

# Minimum HTML length to attempt extraction
MIN_HTML_LENGTH = 100

# Minimum extracted text length to consider success
MIN_EXTRACTED_LENGTH = 100

# HTML tags that indicate actual content (not just error pages)
CONTENT_INDICATORS = [
    '<article', '<main', '<section', '<div class=', '<p>', '<p ',
    '<body', '<h1', '<h2', '<h3'
]

# HTML patterns that indicate no useful content (error pages, etc.)
# NOTE: These patterns are checked AFTER confirming HTML has content indicators
# The validation flow is: length check -> content indicator check -> error pattern check
EMPTY_CONTENT_PATTERNS = [
    r'^\s*$',                           # Empty or whitespace only
    r'<title>\s*(404|403|500|Error|Not Found|Forbidden|Access Denied)',  # Error pages
    r'<body[^>]*>\s*Access Denied\s*</body>',
    r'<body[^>]*>\s*Page Not Found\s*</body>',
    r'<body[^>]*>\s*Please enable JavaScript[^<]*</body>',  # JS-only pages
    r'<body[^>]*>\s*This page requires JavaScript[^<]*</body>',
    r'<noscript>\s*Please enable JavaScript',  # Page requires JS
]


# ============================================
# VALIDATION FUNCTIONS
# ============================================

def is_valid_html(html: Optional[str]) -> bool:
    """
    Pre-validate HTML before attempting extraction.
    
    Returns False for:
    - Empty or None content
    - Too short content (< MIN_HTML_LENGTH)
    - Error pages (404, 403, etc.)
    - JS-only pages
    
    This prevents trafilatura from processing invalid content
    and generating "discarding data: None" warnings.
    
    Args:
        html: Raw HTML string
        
    Returns:
        True if HTML is worth extracting, False otherwise
    """
    if not html or not isinstance(html, str):
        return False
    
    # Check minimum length
    html_stripped = html.strip()
    if len(html_stripped) < MIN_HTML_LENGTH:
        logger.debug(f"[TRAFILATURA] HTML too short: {len(html_stripped)} chars")
        return False
    
    # Check for content indicators FIRST - if we have real content, likely valid
    has_content = any(indicator.lower() in html_stripped.lower() for indicator in CONTENT_INDICATORS)
    if not has_content:
        logger.debug("[TRAFILATURA] No content indicators found in HTML")
        return False
    
    # Only check error patterns if we have minimal content indicators
    # This prevents false positives from generic patterns
    for pattern in EMPTY_CONTENT_PATTERNS:
        if re.search(pattern, html_stripped, re.IGNORECASE):
            logger.debug(f"[TRAFILATURA] Empty/error content pattern detected")
            return False
    
    return True


def has_article_structure(html: str) -> bool:
    """
    Check if HTML has article-like structure.
    
    Articles typically have:
    - <article> or <main> tags
    - Multiple paragraphs
    - Heading tags (h1, h2, h3)
    
    Args:
        html: Raw HTML string
        
    Returns:
        True if HTML appears to be an article
    """
    html_lower = html.lower()
    
    # Check for article/main container
    has_article = '<article' in html_lower or '<main' in html_lower
    
    # Check for paragraphs (at least 2)
    paragraph_count = html_lower.count('<p>') + html_lower.count('<p ')
    
    # Check for headings
    has_heading = any(f'<h{i}' in html_lower for i in range(1, 4))
    
    return has_article or (paragraph_count >= 2 and has_heading)


# ============================================
# EXTRACTION FUNCTIONS
# ============================================

def extract_with_trafilatura(
    html: str,
    include_comments: bool = False,
    include_tables: bool = False,
    favor_precision: bool = True
) -> Optional[str]:
    """
    Extract article text from HTML using trafilatura.
    
    This is the primary extraction method. It:
    1. Pre-validates HTML to avoid unnecessary processing
    2. Uses trafilatura's extraction with optimized settings
    3. Validates the extracted content length
    
    Args:
        html: Raw HTML content
        include_comments: Include comments (default False)
        include_tables: Include table data (default False)
        favor_precision: Favor precision over recall (default True)
        
    Returns:
        Extracted text if successful, None otherwise
    """
    if not TRAFILATURA_AVAILABLE:
        logger.debug("[TRAFILATURA] Library not available")
        return None
    
    # Pre-validate HTML
    if not is_valid_html(html):
        logger.debug("[TRAFILATURA] HTML validation failed, skipping extraction")
        return None
    
    try:
        text = trafilatura.extract(
            html,
            include_comments=include_comments,
            include_tables=include_tables,
            no_fallback=False,  # Use fallback extractors
            favor_precision=favor_precision,
        )
        
        if text and len(text.strip()) >= MIN_EXTRACTED_LENGTH:
            return text.strip()
        
        logger.debug(f"[TRAFILATURA] Extraction returned insufficient content: {len(text) if text else 0} chars")
        return None
        
    except Exception as e:
        logger.debug(f"[TRAFILATURA] Extraction error: {e}")
        return None


def extract_with_fallback(html: str) -> Tuple[Optional[str], str]:
    """
    Extract content with intelligent fallback chain.
    
    Strategy:
    1. Try trafilatura (best quality, ~90% accuracy)
    2. Fall back to regex-based extraction (70% accuracy)
    3. Return raw text as last resort
    
    Args:
        html: Raw HTML content
        
    Returns:
        Tuple of (extracted_text, method_used)
        method_used is one of: 'trafilatura', 'regex', 'raw', 'failed'
    """
    if not html or not is_valid_html(html):
        return None, 'failed'
    
    # Method 1: Trafilatura (best quality)
    text = extract_with_trafilatura(html)
    if text:
        return text, 'trafilatura'
    
    # Method 2: Regex-based extraction (medium quality)
    text = _extract_with_regex(html)
    if text:
        return text, 'regex'
    
    # Method 3: Raw text extraction (last resort)
    text = _extract_raw_text(html)
    if text:
        return text, 'raw'
    
    return None, 'failed'


def _extract_with_regex(html: str) -> Optional[str]:
    """
    Extract text using regex-based approach.
    
    Targets specific article-related HTML structures:
    - <article> content
    - <main> content
    - <div class="content"> or similar
    - Paragraphs within these containers
    
    Args:
        html: Raw HTML content
        
    Returns:
        Extracted text or None
    """
    try:
        # Try to find article or main content first
        content_patterns = [
            r'<article[^>]*>(.*?)</article>',
            r'<main[^>]*>(.*?)</main>',
            r'<div[^>]*class="[^"]*(?:content|article|post|entry)[^"]*"[^>]*>(.*?)</div>',
        ]
        
        for pattern in content_patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                content_html = match.group(1)
                text = _clean_html_to_text(content_html)
                if text and len(text) >= MIN_EXTRACTED_LENGTH:
                    logger.debug(f"[TRAFILATURA] Regex extraction succeeded with pattern: {pattern[:30]}...")
                    return text
        
        # If no specific container, try extracting all paragraphs
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        if paragraphs:
            text = ' '.join(_clean_html_to_text(p) for p in paragraphs)
            if text and len(text) >= MIN_EXTRACTED_LENGTH:
                logger.debug("[TRAFILATURA] Regex extraction from paragraphs")
                return text
        
        return None
        
    except Exception as e:
        logger.debug(f"[TRAFILATURA] Regex extraction error: {e}")
        return None


def _extract_raw_text(html: str) -> Optional[str]:
    """
    Extract all visible text from HTML (last resort).
    
    Removes:
    - Script and style tags
    - HTML comments
    - All HTML tags
    
    Args:
        html: Raw HTML content
        
    Returns:
        Extracted text or None
    """
    try:
        # Remove script and style tags
        cleaned = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML comments
        cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
        
        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', ' ', cleaned)
        
        # Unescape HTML entities
        text = unescape(text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) >= MIN_EXTRACTED_LENGTH:
            logger.debug(f"[TRAFILATURA] Raw text extraction: {len(text)} chars")
            return text
        
        return None
        
    except Exception as e:
        logger.debug(f"[TRAFILATURA] Raw extraction error: {e}")
        return None


def _clean_html_to_text(html: str) -> str:
    """
    Clean HTML fragment to plain text.
    
    Args:
        html: HTML fragment
        
    Returns:
        Clean text
    """
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Unescape entities
    text = unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================
# FACTORY FUNCTION FOR COMPONENTS
# ============================================

def get_extractor():
    """
    Get the configured trafilatura extractor.
    
    Returns a dict with extraction functions that can be used
    by news_radar, browser_monitor, and article_reader.
    
    Returns:
        Dict with 'extract', 'extract_with_fallback', 'is_available' functions
    """
    return {
        'extract': extract_with_trafilatura,
        'extract_with_fallback': extract_with_fallback,
        'is_available': TRAFILATURA_AVAILABLE,
        'is_valid_html': is_valid_html,
    }


# ============================================
# STATS AND MONITORING
# ============================================

class ExtractionStats:
    """
    Track extraction statistics for monitoring.
    
    Helps identify patterns in extraction failures
    and optimize the extraction pipeline.
    """
    
    def __init__(self):
        self.trafilatura_success = 0
        self.trafilatura_failed = 0
        self.regex_success = 0
        self.regex_failed = 0
        self.raw_success = 0
        self.raw_failed = 0
        self.validation_failed = 0
    
    def record(self, method: str, success: bool) -> None:
        """Record extraction result."""
        attr_name = f"{method}_{'success' if success else 'failed'}"
        if hasattr(self, attr_name):
            setattr(self, attr_name, getattr(self, attr_name) + 1)
        elif not success:
            self.validation_failed += 1
    
    def get_stats(self) -> dict:
        """Get all statistics."""
        return {
            'trafilatura': {
                'success': self.trafilatura_success,
                'failed': self.trafilatura_failed,
            },
            'regex': {
                'success': self.regex_success,
                'failed': self.regex_failed,
            },
            'raw': {
                'success': self.raw_success,
                'failed': self.raw_failed,
            },
            'validation_failed': self.validation_failed,
            'total_attempts': (
                self.trafilatura_success + self.trafilatura_failed +
                self.regex_success + self.regex_failed +
                self.raw_success + self.raw_failed +
                self.validation_failed
            ),
        }


# Global stats instance
_extraction_stats = ExtractionStats()


def get_extraction_stats() -> dict:
    """Get global extraction statistics."""
    return _extraction_stats.get_stats()


def record_extraction(method: str, success: bool) -> None:
    """Record an extraction attempt for stats."""
    _extraction_stats.record(method, success)
