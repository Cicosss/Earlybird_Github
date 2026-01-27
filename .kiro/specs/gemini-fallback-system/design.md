# Design Document: Gemini Fallback System V5.0

## Overview

Il Gemini Fallback System V5.0 è un sistema di resilienza intelligente che gestisce gli errori 429 (rate limit) di Gemini Direct API. Il sistema implementa tre strategie coordinate:

1. **Immediate Cooldown**: Al primo errore 429, il sistema entra in cooldown per 24 ore
2. **Perplexity Fallback**: Durante il cooldown, Perplexity sostituisce Gemini per tutte le funzioni real-time
3. **Browser Automation**: Durante il cooldown, Playwright estrae testo dalle news e lo invia a Gemini API (crediti free) per arricchimento

**Integrazione con EarlyBird:**
- Il sistema si integra con il flusso esistente attraverso un nuovo `Intelligence_Router`
- I componenti esistenti (`GeminiAgentProvider`, `PerplexityProvider`) vengono orchestrati dal router
- Il `Browser_Automation_Provider` è un nuovo componente che opera in parallelo durante il cooldown

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTELLIGENCE LAYER V5.0                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      INTELLIGENCE ROUTER                             │   │
│  │  • Routes requests based on cooldown state                          │   │
│  │  • Singleton pattern (shared across all callers)                    │   │
│  │  • Exposes same interface as GeminiAgentProvider                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┼───────────────┐                       │
│                    │               │               │                        │
│                    ▼               ▼               ▼                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │ COOLDOWN MANAGER │  │ GEMINI DIRECT    │  │ PERPLEXITY       │         │
│  │                  │  │ (Primary)        │  │ (Fallback)       │         │
│  │ • State machine  │  │                  │  │                  │         │
│  │ • 24h timer      │  │ • Deep Dive      │  │ • Deep Dive      │         │
│  │ • Persistence    │  │ • News Verify    │  │ • News Verify    │         │
│  │ • Recovery test  │  │ • Betting Stats  │  │ • Betting Stats  │         │
│  └────────┬─────────┘  │ • Biscotto       │  │ • Biscotto       │         │
│           │            └──────────────────┘  └──────────────────┘         │
│           │                                                                │
│           │  WHEN COOLDOWN ACTIVE                                         │
│           ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   BROWSER AUTOMATION LAYER                           │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐ │   │
│  │  │ ENRICHMENT QUEUE │───▶│ PLAYWRIGHT       │───▶│ GEMINI API     │ │   │
│  │  │                  │    │ (Headless)       │    │ (Free Credits) │ │   │
│  │  │ • Priority queue │    │                  │    │                │ │   │
│  │  │ • Elite 7 first  │    │ • Max 4 parallel │    │ • Text analysis│ │   │
│  │  │ • Persistence    │    │ • 30s timeout    │    │ • JSON output  │ │   │
│  │  └──────────────────┘    │ • 5s interval    │    └────────────────┘ │   │
│  │                          └──────────────────┘                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. CooldownManager

**File**: `src/services/cooldown_manager.py`

**Responsibilities**:
- Gestisce lo stato del cooldown (NORMAL, ACTIVE, RECOVERY)
- Persiste lo stato su file JSON per crash recovery
- Esegue test di recovery dopo 24 ore
- Notifica via Telegram i cambi di stato

**Interface**:
```python
class CooldownState(Enum):
    NORMAL = "normal"       # Gemini Direct API available
    ACTIVE = "active"       # Cooldown in progress, use Perplexity
    RECOVERY = "recovery"   # Testing if Gemini recovered

@dataclass
class CooldownStatus:
    state: CooldownState
    activated_at: Optional[datetime]
    expires_at: Optional[datetime]
    extension_count: int
    last_error: Optional[str]

class CooldownManager:
    def __init__(self, state_file: str = "data/cooldown_state.json")
    
    def activate_cooldown(self, error_message: str) -> None
    def is_cooldown_active(self) -> bool
    def get_status(self) -> CooldownStatus
    def check_and_transition(self) -> CooldownState
    def test_recovery(self) -> bool
    def extend_cooldown(self) -> None
    def reset_to_normal(self) -> None
    
    # Persistence
    def _persist_state(self) -> None
    def _load_state(self) -> None
```

### 2. IntelligenceRouter

**File**: `src/services/intelligence_router.py`

**Responsibilities**:
- Instrada le richieste al provider corretto basandosi sullo stato del cooldown
- Espone la stessa interfaccia di GeminiAgentProvider per compatibilità
- Gestisce il fallback graceful quando Perplexity fallisce

**Interface**:
```python
class IntelligenceRouter:
    def __init__(self):
        self._cooldown_manager = CooldownManager()
        self._gemini_provider = get_gemini_provider()
        self._perplexity_provider = get_perplexity_provider()
    
    def is_available(self) -> bool
    def get_active_provider_name(self) -> str
    
    # Proxied methods (same signature as GeminiAgentProvider)
    def get_match_deep_dive(self, home_team, away_team, ...) -> Optional[Dict]
    def verify_news_item(self, news_title, news_snippet, ...) -> Optional[Dict]
    def verify_news_batch(self, news_items, team_name, ...) -> List[Dict]
    def get_betting_stats(self, home_team, away_team, ...) -> Optional[Dict]
    def confirm_biscotto(self, ...) -> Optional[Dict]
    def format_for_prompt(self, deep_dive: Dict) -> str
    
    # Internal routing
    def _route_request(self, operation: str, func: Callable, *args, **kwargs) -> Any
    def _handle_429_error(self, error: Exception) -> None
```

### 3. BrowserAutomationProvider

**File**: `src/services/browser_automation_provider.py`

**Responsibilities**:
- Gestisce Playwright per l'estrazione di testo dalle pagine web
- Invia il testo estratto a Gemini API per analisi
- Aggiorna NewsLog con i dati arricchiti

**Interface**:
```python
@dataclass
class EnrichmentResult:
    success: bool
    extracted_text: Optional[str]
    analysis: Optional[Dict]
    error: Optional[str]
    processing_time_ms: int

class BrowserAutomationProvider:
    def __init__(self, max_concurrent: int = 4, page_timeout: int = 30):
        self._playwright = None
        self._browser = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def initialize(self) -> None
    async def shutdown(self) -> None
    
    async def extract_and_analyze(self, url: str, context: str) -> EnrichmentResult
    async def enrich_news_item(self, news_log: NewsLog) -> bool
    
    # Internal methods
    async def _extract_page_text(self, url: str) -> Optional[str]
    async def _analyze_with_gemini(self, text: str, context: str) -> Optional[Dict]
    def _build_analysis_prompt(self, text: str, context: str) -> str
```

### 4. EnrichmentQueue

**File**: `src/services/enrichment_queue.py`

**Responsibilities**:
- Gestisce la coda di URL da arricchire con priorità (Elite 7 > Tier 2)
- Persiste la coda su file JSON per crash recovery
- Rispetta i limiti di risorse VPS

**Interface**:
```python
@dataclass
class QueueItem:
    news_log_id: int
    url: str
    league: str
    priority: int  # 1 = Elite 7, 2 = Tier 2
    added_at: datetime
    attempts: int = 0

class EnrichmentQueue:
    def __init__(self, queue_file: str = "data/enrichment_queue.json"):
        self._queue: List[QueueItem] = []
        self._processing: Set[int] = set()
    
    def add(self, news_log: NewsLog, league: str) -> None
    def get_next(self) -> Optional[QueueItem]
    def mark_complete(self, news_log_id: int) -> None
    def mark_failed(self, news_log_id: int) -> None
    def get_queue_size(self) -> int
    def get_pending_count(self) -> Tuple[int, int]  # (elite7, tier2)
    
    # Persistence
    def _persist(self) -> None
    def _load(self) -> None
    
    # Priority management
    def _reorder_queue(self) -> None
```

### 5. EnrichmentWorker

**File**: `src/services/enrichment_worker.py`

**Responsibilities**:
- Worker asincrono che processa la coda di enrichment
- Monitora le risorse VPS e pausa se necessario
- Gestisce il rate limiting (5s tra richieste)

**Interface**:
```python
class EnrichmentWorker:
    def __init__(self, 
                 queue: EnrichmentQueue,
                 browser_provider: BrowserAutomationProvider,
                 min_interval: float = 5.0):
        self._running = False
        self._last_process_time = 0.0
    
    async def start(self) -> None
    async def stop(self) -> None
    def is_running(self) -> bool
    
    # Internal
    async def _process_loop(self) -> None
    async def _process_item(self, item: QueueItem) -> bool
    def _check_memory_usage(self) -> bool
    def _should_pause(self) -> bool
```

## Data Models

### CooldownState JSON Schema

**File**: `data/cooldown_state.json`

```json
{
  "state": "active",
  "activated_at": "2026-01-03T10:30:00Z",
  "expires_at": "2026-01-04T10:30:00Z",
  "extension_count": 0,
  "last_error": "429 RESOURCE_EXHAUSTED",
  "total_429_count": 5,
  "last_successful_call": "2026-01-03T10:25:00Z"
}
```

### EnrichmentQueue JSON Schema

**File**: `data/enrichment_queue.json`

```json
{
  "queue": [
    {
      "news_log_id": 1234,
      "url": "https://example.com/news/injury",
      "league": "soccer_turkey_super_league",
      "priority": 1,
      "added_at": "2026-01-03T10:35:00Z",
      "attempts": 0
    }
  ],
  "processing": [],
  "stats": {
    "total_processed": 150,
    "total_failed": 5,
    "last_processed_at": "2026-01-03T10:34:00Z"
  }
}
```

### NewsLog Updates

Utilizziamo i campi esistenti senza aggiungere nuove colonne:

| Campo | Uso Originale | Uso con Browser Enrichment |
|-------|---------------|---------------------------|
| `summary` | Snippet news | Arricchito con dettagli estratti |
| `source` | 'web', 'telegram_ocr', 'telegram_channel' | + 'browser_enriched' |
| `category` | INJURY, TURNOVER, etc. | Confermata/aggiornata da analisi |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Cooldown State Persistence Round-Trip
*For any* cooldown state (NORMAL, ACTIVE, RECOVERY) with any valid timestamp, persisting to JSON and then loading should produce an equivalent state object.
**Validates: Requirements 1.3, 1.4, 6.1, 6.3**

### Property 2: Cooldown Activation on 429
*For any* API call that returns a 429 error, the CooldownManager should transition to ACTIVE state with a 24-hour expiration.
**Validates: Requirements 1.1, 1.2**

### Property 3: Provider Availability During Cooldown
*For any* cooldown state, `is_available()` should return False for GeminiAgentProvider and True for PerplexityProvider (if configured).
**Validates: Requirements 1.2, 2.1-2.4**

### Property 4: Request Routing Consistency
*For any* intelligence request during ACTIVE cooldown, the IntelligenceRouter should route to PerplexityProvider and never to GeminiAgentProvider.
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 5: Response Format Compatibility
*For any* valid input, PerplexityProvider response structure should be identical to GeminiAgentProvider response structure (same keys, same types).
**Validates: Requirements 2.5**

### Property 6: Queue Priority Ordering
*For any* enrichment queue with mixed Elite 7 and Tier 2 items, `get_next()` should always return Elite 7 items before Tier 2 items when queue size exceeds 100.
**Validates: Requirements 4.5**

### Property 7: Enrichment Queue Persistence Round-Trip
*For any* queue state with pending items, persisting to JSON and loading should produce an equivalent queue with same items in same order.
**Validates: Requirements 6.2, 6.4**

### Property 8: Concurrent Browser Limit
*For any* number of queued URLs, the number of concurrent browser instances should never exceed 4.
**Validates: Requirements 4.1**

### Property 9: Rate Limiting Interval
*For any* sequence of page navigations, the time between consecutive navigations should be at least 5 seconds.
**Validates: Requirements 4.2**

### Property 10: Graceful Error Handling
*For any* provider failure (Perplexity or Browser Automation), the system should return None without raising an exception.
**Validates: Requirements 2.6, 4.4**

### Property 11: Cooldown Time Transition
*For any* cooldown that has been active for 24+ hours, `check_and_transition()` should transition state to RECOVERY.
**Validates: Requirements 1.5, 5.4**

### Property 12: NewsLog Source Update
*For any* successfully enriched NewsLog, the `source` field should be set to 'browser_enriched'.
**Validates: Requirements 3.5**

## Error Handling

### 429 Error Handling Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    429 ERROR FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Gemini Direct API Call                                         │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 429 Response?   │──── No ────▶ Return Result                │
│  └────────┬────────┘                                           │
│           │ Yes                                                 │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ First 429?      │──── No ────▶ Already in Cooldown          │
│  └────────┬────────┘                                           │
│           │ Yes                                                 │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. CooldownManager.activate_cooldown()                   │   │
│  │ 2. Persist state to JSON                                 │   │
│  │ 3. Send Telegram notification                            │   │
│  │ 4. Start EnrichmentWorker (if not running)              │   │
│  │ 5. Return None (caller will retry with Perplexity)      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Browser Automation Error Handling

| Error Type | Action |
|------------|--------|
| Page timeout (>30s) | Skip URL, mark as failed, continue |
| Browser crash | Log error, restart browser, continue |
| Gemini 429 | Pause 60s, retry once, then skip |
| Network error | Retry 3 times with exponential backoff |
| Invalid URL | Skip, mark as failed |
| Memory >80% | Pause processing until <70% |

## Testing Strategy

### Dual Testing Approach

Il sistema utilizza sia unit test che property-based test per garantire correttezza:

**Unit Tests**: Verificano comportamenti specifici e edge cases
**Property-Based Tests**: Verificano proprietà universali su input generati

### Property-Based Testing Framework

**Library**: `hypothesis` (Python)

**Configuration**:
```python
from hypothesis import settings, given, strategies as st

# Minimum 100 iterations per property
settings.default.max_examples = 100
```

### Test Categories

1. **State Machine Tests**: Verificano transizioni di stato del CooldownManager
2. **Routing Tests**: Verificano che IntelligenceRouter instrada correttamente
3. **Persistence Tests**: Verificano round-trip JSON per tutti i componenti
4. **Concurrency Tests**: Verificano limiti di browser paralleli
5. **Integration Tests**: Verificano flusso end-to-end con mock providers

### Test File Structure

```
tests/
├── test_cooldown_manager.py      # Unit + Property tests
├── test_intelligence_router.py   # Unit + Property tests
├── test_browser_automation.py    # Unit + Integration tests
├── test_enrichment_queue.py      # Unit + Property tests
├── test_enrichment_worker.py     # Unit + Integration tests
└── test_fallback_integration.py  # End-to-end tests
```
