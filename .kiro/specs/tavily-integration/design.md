# Design Document: Tavily Integration

## Overview

L'integrazione Tavily aggiunge un motore di ricerca AI-optimized al sistema EarlyBird per migliorare la qualità dell'intelligence. Tavily si posiziona come layer intermedio tra le ricerche tradizionali (Brave/DDG) e l'analisi AI (DeepSeek), fornendo risultati pre-strutturati e rilevanti.

### Key Design Decisions

1. **API Key Rotation**: 7 API keys da 1000 chiamate ciascuna, rotazione automatica al 429
2. **Query Batching**: Combinare multiple domande in singole chiamate API (come Perplexity)
3. **Budget Allocation**: Distribuzione strategica delle 7000 chiamate/mese
4. **Caching Aggressivo**: 30 minuti TTL per evitare chiamate duplicate
5. **Graceful Degradation**: Fallback automatico a Brave/DDG se tutte le keys esaurite

### API Keys Configuration

```
TAVILY_API_KEY_1=tvly-xxx...  # Key 1 (1000 calls)
TAVILY_API_KEY_2=tvly-xxx...  # Key 2 (1000 calls)
TAVILY_API_KEY_3=tvly-xxx...  # Key 3 (1000 calls)
TAVILY_API_KEY_4=tvly-xxx...  # Key 4 (1000 calls)
TAVILY_API_KEY_5=tvly-xxx...  # Key 5 (1000 calls)
TAVILY_API_KEY_6=tvly-xxx...  # Key 6 (1000 calls)
TAVILY_API_KEY_7=tvly-xxx...  # Key 7 (1000 calls)
# Total: 7000 calls/month
```

### Budget Allocation (7000 calls/month)

| Component | % Budget | Calls/Month | Calls/Day |
|-----------|----------|-------------|-----------|
| Main Pipeline | 30% | 2100 | ~70 |
| News Radar | 21% | 1500 | ~50 |
| Browser Monitor | 11% | 750 | ~25 |
| Telegram Monitor | 6% | 450 | ~15 |
| Settlement/CLV | 3% | 225 | ~7 |
| Buffer/Recovery | 29% | 1975 | ~65 |

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         TAVILY INTEGRATION LAYER                          │
└──────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │         TAVILY API KEY POOL         │
                    │  Key 1 → Key 2 → ... → Key 7        │
                    │  (1000)   (1000)       (1000)       │
                    │         Total: 7000/month           │
                    └────────────────┬────────────────────┘
                                     │
                              ┌──────▼──────┐
                              │ KEY ROTATOR │
                              │ • Track per │
                              │   key usage │
                              │ • Auto-swap │
                              │   on 429    │
                              └──────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │   TAVILY    │
                              │  PROVIDER   │
                              │ • Rate Lim  │
                              │ • Cache 30m │
                              └──────┬──────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
           ┌────────▼────────┐ ┌─────▼─────┐ ┌───────▼───────┐
           │ QUERY BUILDER   │ │ BUDGET MGR│ │ FALLBACK MGR  │
           │ • Batch queries │ │ • Track   │ │ • Brave/DDG   │
           │ • Parse results │ │ • Throttle│ │ • Recovery    │
           └────────┬────────┘ └───────────┘ └───────────────┘
                    │
    ┌───────────────┼───────────────┬───────────────┬───────────────┐
    │               │               │               │               │
┌───▼───┐     ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
│ MAIN  │     │  NEWS     │   │ BROWSER   │   │ TELEGRAM  │   │ TWITTER   │
│PIPELINE│    │  RADAR    │   │ MONITOR   │   │ MONITOR   │   │ RECOVERY  │
│ 30%   │     │  21%      │   │  11%      │   │   6%      │   │  buffer   │
└───────┘     └───────────┘   └───────────┘   └───────────┘   └───────────┘
```

## Components and Interfaces

### 1. TavilyProvider (`src/ingestion/tavily_provider.py`)

Core provider che gestisce tutte le interazioni con Tavily API.

```python
class TavilyKeyRotator:
    """
    Manages rotation between 7 Tavily API keys.
    
    Each key has 1000 calls/month limit.
    Automatically rotates to next key on 429 error.
    """
    
    def __init__(self):
        self._keys: List[str] = []  # Loaded from env: TAVILY_API_KEY_1..7
        self._current_index: int = 0
        self._key_usage: Dict[int, int] = {}  # key_index -> calls_made
        self._exhausted_keys: Set[int] = set()
    
    def get_current_key(self) -> Optional[str]:
        """Get current active API key, or None if all exhausted."""
    
    def rotate_to_next(self) -> bool:
        """Rotate to next available key. Returns False if all exhausted."""
    
    def mark_exhausted(self, key_index: int) -> None:
        """Mark a key as exhausted (received 429)."""
    
    def record_call(self) -> None:
        """Record a successful API call for current key."""
    
    def reset_all(self) -> None:
        """Reset all keys to available (monthly reset)."""
    
    def get_status(self) -> Dict:
        """Get rotation status for monitoring."""


class TavilyProvider:
    """
    Tavily AI Search Provider with Key Rotation.
    
    Features:
    - 7 API keys rotation (1000 calls each)
    - Rate limiting (1 req/sec)
    - Response caching (30 min TTL)
    - Automatic fallback on exhaustion
    """
    
    def __init__(self):
        self._key_rotator: TavilyKeyRotator
        self._cache: Dict[str, CacheEntry]
        self._rate_limiter: RateLimiter
        self._budget_manager: BudgetManager
        self._last_request_time: float
    
    def is_available(self) -> bool:
        """Check if Tavily is available and within budget."""
    
    def search(
        self,
        query: str,
        search_depth: str = "basic",  # "basic" or "advanced"
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False
    ) -> Optional[TavilyResponse]:
        """Execute search with caching and rate limiting."""
    
    def search_news(
        self,
        query: str,
        days: int = 7,
        max_results: int = 5
    ) -> List[Dict]:
        """Search specifically for news articles."""
    
    def get_budget_status(self) -> BudgetStatus:
        """Get current budget usage statistics."""
```

### 2. TavilyQueryBuilder (`src/ingestion/tavily_query_builder.py`)

Costruisce query ottimizzate per Tavily con supporto batching.

```python
class TavilyQueryBuilder:
    """
    Query builder with batching support.
    
    Combines multiple questions into single queries
    to maximize API efficiency.
    """
    
    @staticmethod
    def build_match_enrichment_query(
        home_team: str,
        away_team: str,
        match_date: str,
        questions: List[str] = None
    ) -> str:
        """Build batched query for match enrichment."""
    
    @staticmethod
    def build_news_verification_query(
        news_title: str,
        team_name: str,
        additional_context: str = ""
    ) -> str:
        """Build query for news verification."""
    
    @staticmethod
    def build_biscotto_query(
        home_team: str,
        away_team: str,
        league: str,
        season_context: str
    ) -> str:
        """Build query for biscotto confirmation."""
    
    @staticmethod
    def build_twitter_recovery_query(
        handle: str,
        keywords: List[str]
    ) -> str:
        """Build query for Twitter intel recovery."""
    
    @staticmethod
    def parse_batched_response(
        response: TavilyResponse,
        question_count: int
    ) -> List[str]:
        """Parse batched response into individual answers."""
```

### 3. BudgetManager (`src/ingestion/tavily_budget.py`)

Gestisce il budget mensile e giornaliero.

```python
@dataclass
class BudgetStatus:
    monthly_used: int
    monthly_limit: int
    daily_used: int
    daily_limit: int
    is_degraded: bool
    is_disabled: bool

class BudgetManager:
    """
    Tracks and manages Tavily API budget.
    
    Implements tiered throttling:
    - Normal: Full functionality
    - Degraded (>90%): Non-critical calls throttled
    - Disabled (>95%): Only critical calls allowed
    """
    
    def __init__(self, monthly_limit: int = 7000):
        self._monthly_limit = monthly_limit
        self._monthly_used = 0
        self._daily_allocations: Dict[str, int]  # component -> daily limit
    
    def can_call(self, component: str, is_critical: bool = False) -> bool:
        """Check if component can make a Tavily call."""
    
    def record_call(self, component: str) -> None:
        """Record a Tavily API call."""
    
    def get_status(self) -> BudgetStatus:
        """Get current budget status."""
    
    def reset_monthly(self) -> None:
        """Reset monthly counters (called on month boundary)."""
```

### 4. Integration Points

#### 4.1 Intelligence Router Integration

```python
# In src/services/intelligence_router.py

class IntelligenceRouter:
    def __init__(self):
        # ... existing code ...
        self._tavily = get_tavily_provider()
    
    def enrich_match_context(
        self,
        home_team: str,
        away_team: str,
        match_date: str,
        league: str,
        existing_context: str = ""
    ) -> Optional[Dict]:
        """
        Enrich match context with Tavily before DeepSeek.
        
        Uses Tavily for:
        1. Recent team news
        2. Injury updates
        3. Tactical changes
        4. H2H context
        """
        if self._tavily.is_available():
            query = TavilyQueryBuilder.build_match_enrichment_query(
                home_team, away_team, match_date
            )
            tavily_result = self._tavily.search(query)
            if tavily_result:
                existing_context = self._merge_tavily_context(
                    existing_context, tavily_result
                )
        
        # Continue with DeepSeek analysis
        return self._primary_provider.enrich_match_context(...)
```

#### 4.2 News Radar Integration

```python
# In src/services/news_radar.py

class NewsRadarMonitor:
    async def _analyze_content(self, content: str, url: str) -> AnalysisResult:
        """
        Analyze content with Tavily pre-enrichment for ambiguous cases.
        """
        # Initial analysis
        initial_result = self._relevance_analyzer.analyze(content)
        
        # If ambiguous (0.5-0.7), use Tavily for enrichment
        if 0.5 <= initial_result.confidence < 0.7:
            if self._tavily.is_available():
                enrichment = await self._tavily_enrich(content, url)
                if enrichment:
                    content = f"{content}\n\n[TAVILY CONTEXT]\n{enrichment}"
                    initial_result.confidence += 0.15
        
        # Continue with DeepSeek if still ambiguous
        if initial_result.confidence < 0.7:
            return await self._deepseek_analyze(content)
        
        return initial_result
```

## Data Models

### TavilyResponse

```python
@dataclass
class TavilyResponse:
    """Response from Tavily API."""
    query: str
    answer: Optional[str]  # AI-generated answer
    results: List[TavilyResult]
    response_time: float
    
@dataclass
class TavilyResult:
    """Individual search result."""
    title: str
    url: str
    content: str  # Snippet
    score: float  # Relevance score
    published_date: Optional[str]

@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    response: TavilyResponse
    cached_at: datetime
    ttl_seconds: int = 1800  # 30 minutes
    
    def is_expired(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: API Key Validation and Loading

*For any* set of environment variables TAVILY_API_KEY_1 through TAVILY_API_KEY_7, the TavilyKeyRotator SHALL load all non-empty keys in order and set is_available() to True only when at least one valid key exists.

**Validates: Requirements 1.1, 11.1**

### Property 2: Key Rotation on 429

*For any* sequence of API calls where the current key returns 429, the TavilyKeyRotator SHALL automatically switch to the next available key in sequence (1→2→3→...→7) without manual intervention.

**Validates: Requirements 1.4, 11.2**

### Property 3: Rate Limiting Enforcement

*For any* sequence of N search requests, the time between consecutive requests SHALL be at least 1 second, ensuring total execution time >= (N-1) seconds.

**Validates: Requirements 1.2**

### Property 4: Cache Round-Trip

*For any* search query, calling search() twice within TTL SHALL return identical results, and the second call SHALL NOT make an API request.

**Validates: Requirements 1.3**

### Property 5: Query Batching Round-Trip

*For any* list of questions, building a batched query and parsing the response SHALL produce answers that map back to the original questions in order.

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 6: Query Splitting

*For any* list of questions that produces a query exceeding 500 characters, the Query_Builder SHALL split into multiple queries each under 500 characters.

**Validates: Requirements 2.4**

### Property 7: Content Merging Preservation

*For any* original content and Tavily enrichment, the merged content SHALL contain all text from both sources without loss.

**Validates: Requirements 3.2, 4.2, 5.2**

### Property 8: Confidence Adjustment Bounds

*For any* confidence value between 0.5 and 0.7, after Tavily enrichment confirms relevance, the new confidence SHALL be original + 0.15, capped at 1.0.

**Validates: Requirements 4.3**

### Property 9: Trust Score Adjustment

*For any* trust score between 0.4 and 0.7, Tavily verification SHALL adjust the score by exactly +0.2 (confirmed), -0.1 (contradicted), or 0 (inconclusive), with result capped between 0.0 and 1.0.

**Validates: Requirements 6.2, 6.3, 6.4**

### Property 10: Budget Tracking Consistency

*For any* sequence of Tavily calls across all keys, the total budget counter SHALL equal the sum of calls made per key, and key rotation SHALL trigger when any key reaches 1000 calls.

**Validates: Requirements 9.1, 9.2, 11.2**

### Property 11: Exponential Backoff Timing

*For any* sequence of N consecutive 429 errors on the same key, the system SHALL rotate to next key immediately rather than retry with backoff.

**Validates: Requirements 10.1, 11.2**

### Property 12: Fallback Activation on Exhaustion

*For any* state where all 7 API keys are exhausted (received 429), the provider SHALL switch to Brave/DDG fallback and set is_available() to False.

**Validates: Requirements 1.5, 10.2, 11.4**

### Property 13: Monthly Reset

*For any* month boundary crossing, the Key_Rotator SHALL reset all keys to available status, reset all usage counters to 0, and restart from key 1.

**Validates: Requirements 9.4, 11.5**

## Error Handling

### API Errors

| Error Code | Handling |
|------------|----------|
| 400 | Log error, return None, don't retry |
| 401 | Log critical, disable provider |
| 429 | Exponential backoff, max 60s wait |
| 500+ | Retry once, then fallback |
| Timeout | Retry once with longer timeout |

### Fallback Chain

```
Tavily (primary)
    ↓ (fail)
Brave Search (secondary)
    ↓ (fail)
DuckDuckGo (tertiary)
    ↓ (fail)
Return cached data or None
```

### Circuit Breaker

```python
class TavilyCircuitBreaker:
    """
    Circuit breaker for Tavily API.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Tavily failing, use fallback
    - HALF_OPEN: Testing recovery
    
    Thresholds:
    - Open after 3 consecutive failures
    - Recovery attempt every 60 seconds
    - Close after 2 consecutive successes
    """
```

## Testing Strategy

### Dual Testing Approach

L'implementazione richiede sia unit test che property-based test:

1. **Unit Tests**: Verificano esempi specifici e edge cases
2. **Property-Based Tests**: Verificano proprietà universali su input generati

### Property-Based Testing Framework

**Framework**: `hypothesis` (Python)
**Minimum iterations**: 100 per property

### Test Categories

#### Unit Tests

- API key validation (valid, empty, None)
- Cache expiration at exact TTL boundary
- Budget threshold transitions (89%→90%, 94%→95%)
- Query builder output format
- Response parsing edge cases

#### Property-Based Tests

Ogni correctness property avrà un corrispondente PBT:

```python
# Example: Property 2 - Rate Limiting
@given(st.integers(min_value=2, max_value=10))
@settings(max_examples=100)
def test_rate_limiting_enforcement(num_requests):
    """
    **Feature: tavily-integration, Property 2: Rate Limiting Enforcement**
    **Validates: Requirements 1.2**
    """
    provider = TavilyProvider()
    start_times = []
    
    for _ in range(num_requests):
        start = time.time()
        provider.search("test query")
        start_times.append(start)
    
    # Verify minimum 1 second between consecutive requests
    for i in range(1, len(start_times)):
        gap = start_times[i] - start_times[i-1]
        assert gap >= 1.0, f"Gap {gap}s < 1s between requests {i-1} and {i}"
```

### Test File Structure

```
tests/
├── test_tavily_provider.py      # Unit tests for provider
├── test_tavily_query_builder.py # Unit tests for query builder
├── test_tavily_budget.py        # Unit tests for budget manager
├── test_tavily_integration.py   # Integration tests
└── test_tavily_properties.py    # Property-based tests
```
