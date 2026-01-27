"""
EarlyBird Centralized HTTP Client

Singleton HTTPX client with connection pooling, retry logic, and rate limiting.
Integrates with BrowserFingerprint for anti-detection.

Features:
- Connection pooling (max 10 connections, 5 keepalive)
- HTTP/2 support
- Per-domain rate limiting with configurable jitter
- Exponential backoff retry on 429/503/timeout
- Fingerprint rotation on 403/429
- Both sync and async interfaces
- Fallback to requests library if HTTPX unavailable
- V7.2: Domain-sticky fingerprinting for session consistency

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 6.1, 6.3, 7.1, 7.2, 7.3, 7.4
"""
import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ============================================
# TRY IMPORT HTTPX (with fallback to requests)
# ============================================
try:
    import httpx
    _HTTPX_AVAILABLE = True
    logger.debug("✅ HTTPX library available")
except ImportError:
    _HTTPX_AVAILABLE = False
    httpx = None
    logger.warning("⚠️ HTTPX not installed, falling back to requests")

# Fallback to requests
try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    requests = None

# Import fingerprint manager
from src.utils.browser_fingerprint import get_fingerprint, BrowserFingerprint


# ============================================
# RATE LIMITER
# ============================================
@dataclass
class RateLimiter:
    """
    Per-domain rate limiting with jitter.
    
    Attributes:
        min_interval: Minimum seconds between requests
        jitter_min: Minimum random delay added
        jitter_max: Maximum random delay added
        last_request_time: Timestamp of last request
    
    Thread-safe for sync operations, uses asyncio.Lock for async.
    """
    min_interval: float = 1.0
    jitter_min: float = 0.0
    jitter_max: float = 0.0
    last_request_time: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _async_lock: Optional[asyncio.Lock] = field(default=None, repr=False)
    
    def _get_async_lock(self) -> asyncio.Lock:
        """Lazy-init async lock (must be created in event loop context)."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock
    
    def get_delay(self) -> float:
        """
        Calculate delay needed before next request.
        
        Returns:
            Delay in seconds (0 if no delay needed)
        """
        now = time.time()
        elapsed = now - self.last_request_time
        base_delay = max(0, self.min_interval - elapsed)
        
        # Add jitter
        jitter = 0.0
        if self.jitter_max > self.jitter_min:
            jitter = random.uniform(self.jitter_min, self.jitter_max)
        elif self.jitter_min > 0:
            jitter = self.jitter_min
        
        return base_delay + jitter
    
    def wait_sync(self) -> float:
        """
        Wait for rate limit (synchronous).
        
        Returns:
            Actual delay applied in seconds
        """
        with self._lock:
            delay = self.get_delay()
            if delay > 0:
                logger.debug(f"⏱️ Rate limit: sleeping {delay:.2f}s")
                time.sleep(delay)
            self.last_request_time = time.time()
            return delay
    
    async def wait_async(self) -> float:
        """
        Wait for rate limit (asynchronous).
        
        FIX: Uses asyncio.Lock to properly serialize async requests.
        The lock is held during the entire wait to prevent race conditions.
        
        Returns:
            Actual delay applied in seconds
        """
        async_lock = self._get_async_lock()
        async with async_lock:
            delay = self.get_delay()
            if delay > 0:
                logger.debug(f"⏱️ Rate limit: sleeping {delay:.2f}s (async)")
                await asyncio.sleep(delay)
            self.last_request_time = time.time()
            return delay


# ============================================
# RATE LIMIT CONFIGURATIONS
# ============================================
RATE_LIMIT_CONFIGS: Dict[str, Dict] = {
    "duckduckgo": {"min_interval": 1.0, "jitter_min": 1.0, "jitter_max": 2.0},  # V7.6: Reduced from 3-6s to 1-2s (saves 20-40s per 10 requests)
    "brave": {"min_interval": 2.0, "jitter_min": 0.0, "jitter_max": 0.0},
    "serper": {"min_interval": 0.3, "jitter_min": 0.0, "jitter_max": 0.0},
    "fotmob": {"min_interval": 1.0, "jitter_min": 0.0, "jitter_max": 0.0},
    "default": {"min_interval": 1.0, "jitter_min": 0.0, "jitter_max": 0.0},
}

# HTTP status codes that trigger retry
RETRY_STATUS_CODES = {429, 502, 503, 504}

# HTTP status codes that trigger fingerprint rotation
FINGERPRINT_ROTATE_CODES = {403, 429}


# ============================================
# HTTP CLIENT (HTTPX-based)
# ============================================
class EarlyBirdHTTPClient:
    """
    Centralized HTTP client with connection pooling, retry, and rate limiting.
    
    Singleton pattern ensures all components share the same connection pool.
    
    Features:
    - HTTPX AsyncClient with HTTP/2 and connection pooling
    - Per-domain rate limiting with configurable jitter
    - Exponential backoff retry on transient errors
    - Fingerprint rotation on 403/429
    - Both sync and async interfaces
    - Detailed logging for observability
    """
    
    _instance: Optional['EarlyBirdHTTPClient'] = None
    _lock: threading.Lock = threading.Lock()
    
    # Connection pool settings
    MAX_CONNECTIONS = 10
    MAX_KEEPALIVE = 5
    DEFAULT_TIMEOUT = 15.0
    DEFAULT_MAX_RETRIES = 3
    
    def __init__(self):
        """Initialize HTTP client (called only once via singleton)."""
        self._async_client: Optional['httpx.AsyncClient'] = None
        self._sync_client: Optional['httpx.Client'] = None
        self._fingerprint: BrowserFingerprint = get_fingerprint()
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._request_count: int = 0
        self._initialized = False
        
        # Initialize rate limiters from config
        for key, config in RATE_LIMIT_CONFIGS.items():
            self._rate_limiters[key] = RateLimiter(**config)
        
        logger.info("✅ EarlyBirdHTTPClient initialized (HTTPX mode)")
    
    @classmethod
    def get_instance(cls) -> 'EarlyBirdHTTPClient':
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                # Close clients if open
                if cls._instance._sync_client:
                    try:
                        cls._instance._sync_client.close()
                    except Exception as e:
                        logger.debug(f"Errore chiusura sync_client: {e}")
                cls._instance = None
    
    def _get_rate_limiter(self, key: str) -> RateLimiter:
        """Get rate limiter for a key, creating default if needed."""
        if key not in self._rate_limiters:
            config = RATE_LIMIT_CONFIGS.get(key, RATE_LIMIT_CONFIGS["default"])
            self._rate_limiters[key] = RateLimiter(**config)
        return self._rate_limiters[key]
    
    def configure_rate_limit(
        self,
        key: str,
        min_interval: float,
        jitter_min: float = 0.0,
        jitter_max: float = 0.0
    ):
        """
        Configure rate limiting for a specific domain/service.
        
        Args:
            key: Rate limit key (e.g., "duckduckgo", "brave")
            min_interval: Minimum seconds between requests
            jitter_min: Minimum random delay
            jitter_max: Maximum random delay
        """
        self._rate_limiters[key] = RateLimiter(
            min_interval=min_interval,
            jitter_min=jitter_min,
            jitter_max=jitter_max
        )
        logger.debug(f"⚙️ Rate limit configured: {key} = {min_interval}s + jitter({jitter_min}-{jitter_max}s)")
    
    def _get_sync_client(self) -> 'httpx.Client':
        """Get or create sync HTTPX client."""
        if not _HTTPX_AVAILABLE:
            raise RuntimeError("HTTPX not available")
        
        if self._sync_client is None:
            limits = httpx.Limits(
                max_connections=self.MAX_CONNECTIONS,
                max_keepalive_connections=self.MAX_KEEPALIVE
            )
            self._sync_client = httpx.Client(
                limits=limits,
                http2=True,
                follow_redirects=True,
                timeout=httpx.Timeout(self.DEFAULT_TIMEOUT)
            )
        return self._sync_client

    def _build_headers(
        self, 
        use_fingerprint: bool, 
        extra_headers: Optional[Dict] = None,
        domain: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Build request headers with optional fingerprinting.
        
        Args:
            use_fingerprint: Whether to use browser fingerprinting
            extra_headers: Additional headers to include
            domain: Optional domain for sticky fingerprint (V7.2)
        """
        if use_fingerprint:
            if domain:
                # V7.2: Use domain-sticky fingerprint
                headers = self._fingerprint.get_headers_for_domain(domain)
            else:
                headers = self._fingerprint.get_headers()
        else:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        
        if extra_headers:
            headers.update(extra_headers)
        
        return headers
    
    def _on_error(self, status_code: int, domain: Optional[str] = None):
        """
        Handle error response - triggers fingerprint rotation on 403/429.
        
        Args:
            status_code: HTTP status code
            domain: Optional domain for domain-specific rotation (V7.2)
        """
        if status_code in FINGERPRINT_ROTATE_CODES:
            logger.warning(f"⚠️ HTTP {status_code} - rotating fingerprint")
            if domain:
                self._fingerprint.force_rotate_domain(domain)
            else:
                self._fingerprint.force_rotate()
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        return min(2 ** attempt, 30)  # Cap at 30 seconds
    
    def get_sync(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = None,
        max_retries: int = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> 'httpx.Response':
        """
        Synchronous GET with rate limiting, fingerprinting, and retry.
        
        Args:
            url: URL to request
            rate_limit_key: Key for rate limiter (e.g., "duckduckgo")
            use_fingerprint: Whether to use browser fingerprinting
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            headers: Additional headers to include
            **kwargs: Additional arguments passed to httpx.get()
            
        Returns:
            httpx.Response object
            
        Raises:
            httpx.HTTPError: On request failure after retries
        """
        timeout = timeout or self.DEFAULT_TIMEOUT
        max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        
        # Apply rate limiting
        rate_limiter = self._get_rate_limiter(rate_limit_key)
        delay = rate_limiter.wait_sync()
        
        # Build headers
        request_headers = self._build_headers(use_fingerprint, headers)
        
        # Get client
        client = self._get_sync_client()
        
        start_time = time.time()
        last_error = None
        profile_name = self._fingerprint.get_current_profile_name()
        
        for attempt in range(max_retries + 1):
            try:
                response = client.get(
                    url,
                    headers=request_headers,
                    timeout=timeout,
                    **kwargs
                )
                
                duration_ms = (time.time() - start_time) * 1000
                self._request_count += 1
                
                # Log request completion
                logger.debug(
                    f"📡 GET {url[:60]}... | {response.status_code} | "
                    f"{duration_ms:.0f}ms | profile={profile_name}"
                )
                
                # Handle error status codes
                if response.status_code in RETRY_STATUS_CODES:
                    self._on_error(response.status_code)
                    
                    if attempt < max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"⚠️ HTTP {response.status_code} - retry {attempt + 1}/{max_retries} "
                            f"in {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        # Refresh headers after fingerprint rotation
                        request_headers = self._build_headers(use_fingerprint, headers)
                        profile_name = self._fingerprint.get_current_profile_name()
                        continue
                
                # Handle 403 with fingerprint rotation
                if response.status_code == 403:
                    self._on_error(403)
                    if attempt < max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(f"⚠️ HTTP 403 - rotating fingerprint, retry in {backoff:.1f}s")
                        time.sleep(backoff)
                        request_headers = self._build_headers(use_fingerprint, headers)
                        profile_name = self._fingerprint.get_current_profile_name()
                        continue
                
                return response
                
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Timeout - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except httpx.ConnectError as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Connection error - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except Exception as e:
                last_error = e
                logger.error(f"❌ Request error: {e}")
                break
        
        # All retries exhausted
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ GET {url[:60]}... failed after {max_retries} retries | {duration_ms:.0f}ms")
        raise last_error or httpx.HTTPError(f"Request failed: {url}")
    
    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        """
        V7.2: Extract domain from URL for sticky fingerprinting.
        
        Args:
            url: Full URL (e.g., "https://news.example.com/article/123")
            
        Returns:
            Domain string (e.g., "news.example.com") or None if invalid
        """
        if not url:
            return None
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() if parsed.netloc else None
        except Exception:
            return None
    
    def get_sync_for_domain(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        timeout: float = None,
        max_retries: int = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> 'httpx.Response':
        """
        V7.2: GET with domain-sticky fingerprinting.
        
        Uses consistent browser fingerprint per domain to avoid detection
        by sites that track session consistency.
        
        Args:
            url: URL to request
            rate_limit_key: Key for rate limiter
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            headers: Additional headers to include
            **kwargs: Additional arguments passed to httpx.get()
            
        Returns:
            httpx.Response object
        """
        domain = self._extract_domain(url)
        
        timeout = timeout or self.DEFAULT_TIMEOUT
        max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        
        # Apply rate limiting
        rate_limiter = self._get_rate_limiter(rate_limit_key)
        rate_limiter.wait_sync()
        
        # Build headers with domain-sticky fingerprint
        request_headers = self._build_headers(use_fingerprint=True, extra_headers=headers, domain=domain)
        
        # Get client
        client = self._get_sync_client()
        
        start_time = time.time()
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = client.get(
                    url,
                    headers=request_headers,
                    timeout=timeout,
                    **kwargs
                )
                
                duration_ms = (time.time() - start_time) * 1000
                self._request_count += 1
                
                logger.debug(
                    f"📡 GET {url[:60]}... | {response.status_code} | "
                    f"{duration_ms:.0f}ms | domain={domain}"
                )
                
                # Handle error status codes with domain-specific rotation
                if response.status_code in RETRY_STATUS_CODES:
                    self._on_error(response.status_code, domain=domain)
                    
                    if attempt < max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"⚠️ HTTP {response.status_code} - retry {attempt + 1}/{max_retries} "
                            f"in {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        request_headers = self._build_headers(use_fingerprint=True, extra_headers=headers, domain=domain)
                        continue
                
                if response.status_code == 403:
                    self._on_error(403, domain=domain)
                    if attempt < max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(f"⚠️ HTTP 403 - rotating domain fingerprint, retry in {backoff:.1f}s")
                        time.sleep(backoff)
                        request_headers = self._build_headers(use_fingerprint=True, extra_headers=headers, domain=domain)
                        continue
                
                return response
                
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Timeout - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except httpx.ConnectError as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Connection error - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except Exception as e:
                last_error = e
                logger.error(f"❌ Request error: {e}")
                break
        
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ GET {url[:60]}... failed after {max_retries} retries | {duration_ms:.0f}ms")
        raise last_error or httpx.HTTPError(f"Request failed: {url}")

    def post_sync(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = None,
        max_retries: int = None,
        headers: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> 'httpx.Response':
        """
        Synchronous POST with rate limiting, fingerprinting, and retry.
        
        Args:
            url: URL to request
            rate_limit_key: Key for rate limiter
            use_fingerprint: Whether to use browser fingerprinting
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            headers: Additional headers to include
            json: JSON body to send
            data: Form data to send
            **kwargs: Additional arguments passed to httpx.post()
            
        Returns:
            httpx.Response object
        """
        timeout = timeout or self.DEFAULT_TIMEOUT
        max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        
        # Apply rate limiting
        rate_limiter = self._get_rate_limiter(rate_limit_key)
        delay = rate_limiter.wait_sync()
        
        # Build headers
        request_headers = self._build_headers(use_fingerprint, headers)
        
        # Get client
        client = self._get_sync_client()
        
        start_time = time.time()
        last_error = None
        profile_name = self._fingerprint.get_current_profile_name()
        
        for attempt in range(max_retries + 1):
            try:
                response = client.post(
                    url,
                    headers=request_headers,
                    timeout=timeout,
                    json=json,
                    data=data,
                    **kwargs
                )
                
                duration_ms = (time.time() - start_time) * 1000
                self._request_count += 1
                
                logger.debug(
                    f"📡 POST {url[:60]}... | {response.status_code} | "
                    f"{duration_ms:.0f}ms | profile={profile_name}"
                )
                
                # Handle retry status codes
                if response.status_code in RETRY_STATUS_CODES:
                    self._on_error(response.status_code)
                    
                    if attempt < max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"⚠️ HTTP {response.status_code} - retry {attempt + 1}/{max_retries} "
                            f"in {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        request_headers = self._build_headers(use_fingerprint, headers)
                        profile_name = self._fingerprint.get_current_profile_name()
                        continue
                
                return response
                
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Timeout - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except httpx.ConnectError as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"⚠️ Connection error - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                    
            except Exception as e:
                last_error = e
                logger.error(f"❌ POST error: {e}")
                break
        
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ POST {url[:60]}... failed after {max_retries} retries | {duration_ms:.0f}ms")
        raise last_error or httpx.HTTPError(f"Request failed: {url}")
    
    def get_stats(self) -> Dict:
        """Get client statistics for monitoring."""
        return {
            "request_count": self._request_count,
            "fingerprint_stats": self._fingerprint.get_stats(),
            "rate_limiters": list(self._rate_limiters.keys()),
            "httpx_available": _HTTPX_AVAILABLE,
        }


# ============================================
# FALLBACK CLIENT (requests-based)
# ============================================
class FallbackHTTPClient:
    """
    Fallback HTTP client using requests library.
    
    Used when HTTPX is not available.
    Provides same interface as EarlyBirdHTTPClient.
    """
    
    _instance: Optional['FallbackHTTPClient'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __init__(self):
        self._fingerprint: BrowserFingerprint = get_fingerprint()
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._request_count: int = 0
        self._session = requests.Session() if _REQUESTS_AVAILABLE else None
        
        for key, config in RATE_LIMIT_CONFIGS.items():
            self._rate_limiters[key] = RateLimiter(**config)
        
        logger.info("✅ FallbackHTTPClient initialized (requests mode)")
    
    @classmethod
    def get_instance(cls) -> 'FallbackHTTPClient':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None
    
    def _get_rate_limiter(self, key: str) -> RateLimiter:
        if key not in self._rate_limiters:
            config = RATE_LIMIT_CONFIGS.get(key, RATE_LIMIT_CONFIGS["default"])
            self._rate_limiters[key] = RateLimiter(**config)
        return self._rate_limiters[key]
    
    def configure_rate_limit(self, key: str, min_interval: float, jitter_min: float = 0.0, jitter_max: float = 0.0):
        self._rate_limiters[key] = RateLimiter(min_interval=min_interval, jitter_min=jitter_min, jitter_max=jitter_max)
    
    def get_sync(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = 15.0,
        max_retries: int = 3,
        headers: Optional[Dict] = None,
        **kwargs
    ):
        """GET request using requests library."""
        if not _REQUESTS_AVAILABLE:
            raise RuntimeError("Neither HTTPX nor requests available")
        
        rate_limiter = self._get_rate_limiter(rate_limit_key)
        rate_limiter.wait_sync()
        
        request_headers = self._fingerprint.get_headers() if use_fingerprint else {}
        if headers:
            request_headers.update(headers)
        
        start_time = time.time()
        last_error = None
        
        # FIX: Include 403 in retry logic (was missing, unlike EarlyBirdHTTPClient)
        retry_codes = RETRY_STATUS_CODES | {403}
        
        for attempt in range(max_retries + 1):
            try:
                response = self._session.get(url, headers=request_headers, timeout=timeout, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                self._request_count += 1
                
                logger.debug(f"📡 GET {url[:60]}... | {response.status_code} | {duration_ms:.0f}ms")
                
                if response.status_code in retry_codes and attempt < max_retries:
                    if response.status_code in FINGERPRINT_ROTATE_CODES:
                        self._fingerprint.force_rotate()
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ HTTP {response.status_code} - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    request_headers = self._fingerprint.get_headers() if use_fingerprint else {}
                    if headers:
                        request_headers.update(headers)
                    continue
                
                return response
                
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ Timeout - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ Connection error - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
            except Exception as e:
                last_error = e
                logger.error(f"❌ Request error: {e}")
                break
        
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ GET {url[:60]}... failed after {max_retries} retries | {duration_ms:.0f}ms")
        raise last_error or Exception(f"Request failed: {url}")
    
    def post_sync(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = 15.0,
        max_retries: int = 3,
        headers: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
        **kwargs
    ):
        """POST request using requests library."""
        if not _REQUESTS_AVAILABLE:
            raise RuntimeError("Neither HTTPX nor requests available")
        
        rate_limiter = self._get_rate_limiter(rate_limit_key)
        rate_limiter.wait_sync()
        
        request_headers = self._fingerprint.get_headers() if use_fingerprint else {}
        if headers:
            request_headers.update(headers)
        
        start_time = time.time()
        last_error = None
        
        # FIX: Include 403 in retry logic (consistent with EarlyBirdHTTPClient)
        retry_codes = RETRY_STATUS_CODES | {403}
        
        for attempt in range(max_retries + 1):
            try:
                response = self._session.post(url, headers=request_headers, timeout=timeout, json=json, data=data, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                self._request_count += 1
                
                logger.debug(f"📡 POST {url[:60]}... | {response.status_code} | {duration_ms:.0f}ms")
                
                if response.status_code in retry_codes and attempt < max_retries:
                    if response.status_code in FINGERPRINT_ROTATE_CODES:
                        self._fingerprint.force_rotate()
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ HTTP {response.status_code} - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    request_headers = self._fingerprint.get_headers() if use_fingerprint else {}
                    if headers:
                        request_headers.update(headers)
                    continue
                
                return response
                
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ Timeout - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30)
                    logger.warning(f"⚠️ Connection error - retry {attempt + 1}/{max_retries} in {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
            except Exception as e:
                last_error = e
                logger.error(f"❌ POST error: {e}")
                break
        
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ POST {url[:60]}... failed after {max_retries} retries | {duration_ms:.0f}ms")
        raise last_error or Exception(f"Request failed: {url}")
    
    def get_stats(self) -> Dict:
        return {
            "request_count": self._request_count,
            "fingerprint_stats": self._fingerprint.get_stats(),
            "rate_limiters": list(self._rate_limiters.keys()),
            "httpx_available": False,
            "fallback_mode": True,
        }


# ============================================
# SINGLETON & CONVENIENCE FUNCTIONS
# ============================================
def get_http_client() -> Union[EarlyBirdHTTPClient, FallbackHTTPClient]:
    """
    Get the singleton HTTP client instance.
    
    Returns EarlyBirdHTTPClient if HTTPX is available,
    otherwise returns FallbackHTTPClient using requests.
    """
    if _HTTPX_AVAILABLE:
        return EarlyBirdHTTPClient.get_instance()
    elif _REQUESTS_AVAILABLE:
        return FallbackHTTPClient.get_instance()
    else:
        raise RuntimeError("No HTTP library available (install httpx or requests)")


def reset_http_client():
    """Reset HTTP client singleton (for testing)."""
    EarlyBirdHTTPClient.reset_instance()
    FallbackHTTPClient.reset_instance()


def is_httpx_available() -> bool:
    """Check if HTTPX is available."""
    return _HTTPX_AVAILABLE


# ============================================
# CLI TEST
# ============================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("📡 HTTP CLIENT TEST")
    print("=" * 60)
    
    client = get_http_client()
    
    print(f"\n🔍 Client type: {type(client).__name__}")
    print(f"   HTTPX available: {_HTTPX_AVAILABLE}")
    
    # Test rate limiter
    print("\n⏱️ Testing rate limiter...")
    rl = RateLimiter(min_interval=1.0, jitter_min=0.5, jitter_max=1.0)
    delay1 = rl.get_delay()
    print(f"   First delay: {delay1:.2f}s (should be ~0.5-1.0s jitter)")
    rl.wait_sync()
    delay2 = rl.get_delay()
    print(f"   Second delay: {delay2:.2f}s (should be ~1.5-2.0s)")
    
    # Test GET request
    print("\n📡 Testing GET request...")
    try:
        response = client.get_sync(
            "https://httpbin.org/get",
            rate_limit_key="default",
            use_fingerprint=True,
            timeout=10
        )
        print(f"   Status: {response.status_code}")
        print(f"   Headers sent: {response.json().get('headers', {}).get('User-Agent', 'N/A')[:60]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test stats
    print("\n📊 Client stats:")
    stats = client.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")
    
    print("\n✅ HTTP Client test complete")
