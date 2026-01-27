# Design Document: HTTPX + Fingerprint Upgrade

## Overview

Questo documento descrive il design per l'upgrade del layer HTTP di EarlyBird, introducendo:

1. **HTTP Client Centralizzato** (`src/utils/http_client.py`) - Singleton HTTPX con connection pooling, retry logic, e rate limiting
2. **Browser Fingerprint Manager** (`src/utils/browser_fingerprint.py`) - Rotazione sofisticata di User-Agent e headers correlati
3. **Migrazione Provider** - Aggiornamento di SearchProvider, BraveProvider, RSSHubProvider per usare il nuovo client

L'architettura è progettata per essere:
- **Incrementale**: Ogni provider può essere migrato indipendentemente
- **Backward Compatible**: Wrapper sync per componenti legacy
- **Observable**: Logging dettagliato per debugging

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     EARLYBIRD HTTP LAYER                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ SearchProvider  │    │  BraveProvider  │                    │
│  │  (DDG/Serper)   │    │  (Brave API)    │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                              │
│           └──────────┬───────────┘                              │
│                      │                                          │
│                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              HTTP_CLIENT (Singleton)                     │   │
│  │  ┌─────────────────┐  ┌─────────────────────────────┐   │   │
│  │  │ HTTPX AsyncClient│  │    Rate Limiter            │   │   │
│  │  │ • Connection Pool│  │    • Per-domain tracking   │   │   │
│  │  │ • HTTP/2 support │  │    • Configurable jitter   │   │   │
│  │  │ • Retry logic    │  │    • Exponential backoff   │   │   │
│  │  └─────────────────┘  └─────────────────────────────┘   │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │           FINGERPRINT MANAGER                       ││   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ││   │
│  │  │  │ Chrome   │ │ Firefox  │ │ Safari   │ │ Edge   │ ││   │
│  │  │  │ Profile  │ │ Profile  │ │ Profile  │ │ Profile│ ││   │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ ││   │
│  │  │  • Correlated headers (UA + Sec-Fetch + Accept)    ││   │
│  │  │  • Auto-rotation every 8-25 requests               ││   │
│  │  │  • Error-triggered rotation on 403/429             ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. HTTP Client (`src/utils/http_client.py`)

```python
class EarlyBirdHTTPClient:
    """
    Centralized HTTP client with connection pooling, retry, and rate limiting.
    
    Singleton pattern ensures all components share the same connection pool.
    """
    
    _instance: Optional['EarlyBirdHTTPClient'] = None
    
    def __init__(self):
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None
        self._fingerprint: BrowserFingerprint = BrowserFingerprint()
        self._rate_limiters: Dict[str, RateLimiter] = {}
    
    @classmethod
    def get_instance(cls) -> 'EarlyBirdHTTPClient':
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def get_async(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = 15.0,
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """Async GET with rate limiting, fingerprinting, and retry."""
        pass
    
    async def post_async(
        self,
        url: str,
        *,
        rate_limit_key: str = "default",
        use_fingerprint: bool = True,
        timeout: float = 15.0,
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """Async POST with rate limiting, fingerprinting, and retry."""
        pass
    
    def get_sync(self, url: str, **kwargs) -> httpx.Response:
        """Sync wrapper for backward compatibility."""
        pass
    
    def post_sync(self, url: str, **kwargs) -> httpx.Response:
        """Sync wrapper for backward compatibility."""
        pass
    
    def configure_rate_limit(
        self,
        key: str,
        min_interval: float,
        jitter_min: float = 0,
        jitter_max: float = 0
    ):
        """Configure rate limiting for a specific domain/service."""
        pass
    
    def on_error(self, status_code: int):
        """Handle error response - triggers fingerprint rotation on 403/429."""
        pass
```

### 2. Browser Fingerprint Manager (`src/utils/browser_fingerprint.py`)

```python
@dataclass
class BrowserProfile:
    """Complete browser fingerprint profile."""
    name: str
    user_agent: str
    accept_language: str
    accept_encoding: str
    sec_fetch_dest: str
    sec_fetch_mode: str
    sec_fetch_site: str
    sec_ch_ua: Optional[str] = None  # Chrome-specific
    sec_ch_ua_mobile: Optional[str] = None
    sec_ch_ua_platform: Optional[str] = None


class BrowserFingerprint:
    """
    Manages browser fingerprint rotation for anti-detection.
    
    Features:
    - 5+ distinct browser profiles with correlated headers
    - Auto-rotation every 8-25 requests (randomized)
    - Immediate rotation on 403/429 errors
    - Thread-safe for concurrent use
    """
    
    PROFILES: List[BrowserProfile] = [...]  # 5+ profiles
    
    def __init__(self):
        self._current_profile: Optional[BrowserProfile] = None
        self._request_count: int = 0
        self._rotation_threshold: int = random.randint(8, 25)
        self._lock: threading.Lock = threading.Lock()
    
    def get_headers(self) -> Dict[str, str]:
        """Get complete headers for current profile, rotating if needed."""
        pass
    
    def force_rotate(self):
        """Force immediate rotation (called on 403/429)."""
        pass
    
    def _should_rotate(self) -> bool:
        """Check if rotation threshold reached."""
        pass
    
    def _select_new_profile(self) -> BrowserProfile:
        """Select a different profile than current."""
        pass
```

### 3. Rate Limiter (`src/utils/http_client.py`)

```python
@dataclass
class RateLimiter:
    """Per-domain rate limiting with jitter."""
    min_interval: float  # Minimum seconds between requests
    jitter_min: float = 0.0  # Minimum random delay
    jitter_max: float = 0.0  # Maximum random delay
    last_request_time: float = 0.0
    
    async def wait(self):
        """Wait for rate limit, applying jitter."""
        pass
    
    def get_delay(self) -> float:
        """Calculate delay needed before next request."""
        pass
```

## Data Models

### Browser Profiles (Hardcoded)

```python
BROWSER_PROFILES = [
    BrowserProfile(
        name="chrome_win_131",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
    ),
    BrowserProfile(
        name="firefox_win_133",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        accept_language="en-US,en;q=0.5",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
    ),
    BrowserProfile(
        name="safari_mac_17",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
    ),
    BrowserProfile(
        name="edge_win_131",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Windows"',
    ),
    BrowserProfile(
        name="chrome_linux_131",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept_language="en-US,en;q=0.9",
        accept_encoding="gzip, deflate, br",
        sec_fetch_dest="document",
        sec_fetch_mode="navigate",
        sec_fetch_site="none",
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"Linux"',
    ),
]
```

### Rate Limit Configurations

```python
RATE_LIMIT_CONFIGS = {
    "duckduckgo": RateLimiter(min_interval=1.0, jitter_min=3.0, jitter_max=6.0),
    "brave": RateLimiter(min_interval=1.1, jitter_min=0.0, jitter_max=0.0),
    "serper": RateLimiter(min_interval=0.3, jitter_min=0.0, jitter_max=0.0),
    "rsshub": RateLimiter(min_interval=0.5, jitter_min=0.0, jitter_max=0.0),
    "default": RateLimiter(min_interval=1.0, jitter_min=0.0, jitter_max=0.0),
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Singleton HTTP Client Instance
*For any* number of calls to `EarlyBirdHTTPClient.get_instance()`, the returned object SHALL be the same instance (identity equality).
**Validates: Requirements 1.1**

### Property 2: Rate Limiting Jitter Range
*For any* sequence of requests with jitter configured (min=3.0, max=6.0), the actual delay between requests SHALL be within the range [min_interval + jitter_min, min_interval + jitter_max].
**Validates: Requirements 1.2**

### Property 3: Retry on Transient Errors
*For any* request that receives status 429 or 503, the HTTP_Client SHALL retry up to max_retries times with exponential backoff before returning failure.
**Validates: Requirements 1.3, 1.4**

### Property 4: Fingerprint Profile Count
*For any* initialization of BrowserFingerprint, the number of available profiles SHALL be at least 5.
**Validates: Requirements 2.1**

### Property 5: Header Completeness
*For any* call to `BrowserFingerprint.get_headers()`, the returned dict SHALL contain all required keys: User-Agent, Accept, Accept-Language, Accept-Encoding, Sec-Fetch-Dest, Sec-Fetch-Mode, Sec-Fetch-Site.
**Validates: Requirements 2.2**

### Property 6: Fingerprint Rotation Threshold
*For any* sequence of N requests where N > 25, the BrowserFingerprint SHALL have rotated at least once.
**Validates: Requirements 2.3**

### Property 7: Error-Triggered Rotation
*For any* call to `BrowserFingerprint.force_rotate()`, the current profile SHALL change to a different profile.
**Validates: Requirements 2.4**

### Property 8: Header Consistency
*For any* generated headers, if User-Agent contains "Chrome" then Sec-Ch-Ua SHALL also contain "Chrome", and if User-Agent contains "Firefox" then Sec-Ch-Ua SHALL be absent.
**Validates: Requirements 2.5**

### Property 9: Session Reuse Across Fallbacks
*For any* SearchProvider fallback sequence (Brave → DDG → Serper), the underlying HTTPX client instance SHALL remain the same.
**Validates: Requirements 3.3, 5.3**

### Property 10: Brave Rate Limit Configuration
*For any* BraveProvider request, the rate limiter SHALL be configured with min_interval=1.1 seconds.
**Validates: Requirements 4.2**

### Property 11: Return Type Compatibility
*For any* provider method (search_news, search, etc.), the return type SHALL be `List[Dict]` matching the existing interface.
**Validates: Requirements 6.2**

### Property 12: Logging on Request Completion
*For any* completed request, the log output SHALL contain: duration (ms), status code, and fingerprint profile name.
**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

## Error Handling

### HTTP Errors

| Status Code | Action |
|-------------|--------|
| 200 | Return response |
| 429 | Rotate fingerprint, retry with backoff |
| 403 | Rotate fingerprint, retry with backoff |
| 502, 503, 504 | Retry with backoff (no fingerprint rotation) |
| 4xx (other) | Return error, no retry |
| 5xx (other) | Retry with backoff |

### Connection Errors

| Error Type | Action |
|------------|--------|
| Timeout | Retry with backoff |
| ConnectionError | Retry with backoff |
| Other | Log and return error |

### Fallback Chain

```
HTTPX AsyncClient (primary)
    ↓ (if import fails)
HTTPX SyncClient (fallback)
    ↓ (if import fails)
requests library (legacy fallback)
```

## Testing Strategy

### Dual Testing Approach

Il testing combina:
1. **Unit Tests**: Verificano comportamenti specifici con mock
2. **Property-Based Tests**: Verificano proprietà universali con input generati

### Unit Testing

- Test singleton pattern
- Test rate limiter delay calculation
- Test fingerprint header generation
- Test retry logic with mocked responses
- Test provider integration

### Property-Based Testing

Utilizzeremo **Hypothesis** come libreria PBT per Python.

Ogni property test:
- Esegue minimo 100 iterazioni
- È annotato con il riferimento alla correctness property
- Genera input randomici per verificare invarianti

```python
from hypothesis import given, strategies as st, settings

@settings(max_examples=100)
@given(st.integers(min_value=1, max_value=100))
def test_singleton_identity(n_calls: int):
    """
    **Feature: httpx-fingerprint-upgrade, Property 1: Singleton HTTP Client Instance**
    **Validates: Requirements 1.1**
    """
    instances = [EarlyBirdHTTPClient.get_instance() for _ in range(n_calls)]
    assert all(inst is instances[0] for inst in instances)
```

### Test File Structure

```
tests/
├── test_http_client.py          # Unit tests for HTTP client
├── test_browser_fingerprint.py  # Unit tests for fingerprint manager
├── test_http_client_pbt.py      # Property-based tests
└── test_provider_migration.py   # Integration tests for migrated providers
```
