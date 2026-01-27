# Design Document: Browser Automation Always-On

## Overview

Il Browser Monitor è un nuovo componente indipendente che monitora attivamente fonti web h24 per scoprire breaking news prima che appaiano sui motori di ricerca. A differenza dell'Enrichment Worker esistente (che arricchisce news già trovate), il Browser Monitor è una **fonte attiva** che scopre news navigando direttamente sui siti.

**Differenze chiave rispetto all'Enrichment Worker:**

| Aspetto | Enrichment Worker | Browser Monitor |
|---------|-------------------|-----------------|
| Scopo | Arricchisce news esistenti | Scopre nuove news |
| Trigger | Coda di news da arricchire | Ciclo continuo su URL configurati |
| Output | Aggiorna NewsLog esistente | Crea nuovi news items per news_hunter |
| Priorità | Fallback durante cooldown | Fonte TIER 0 sempre attiva |
| Concorrenza | 4 browser pages | 2 browser pages |
| Intervallo | 5s tra navigazioni | 10s tra navigazioni |

**Integrazione con EarlyBird:**
- Il Browser Monitor gira come processo asincrono separato
- Quando trova news rilevanti, le passa a `news_hunter.py` tramite callback
- Le news entrano nel flusso come fonte TIER 0 (massima priorità)
- Non interferisce con il sistema di cooldown esistente

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEWS HUNTING LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      NEWS HUNTER (news_hunter.py)                    │   │
│  │  • Aggregates news from all sources                                 │   │
│  │  • Passes to analyzer for triangulation                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ▲                                        │
│                    ┌───────────────┼───────────────┐                       │
│                    │               │               │                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │ TIER 0: Browser  │  │ TIER 0: RSSHub   │  │ TIER 0: A-League │         │
│  │ Monitor (NEW)    │  │ (existing)       │  │ Scraper          │         │
│  │                  │  │                  │  │ (existing)       │         │
│  │ • Active scan    │  │ • RSS feeds      │  │ • Direct scrape  │         │
│  │ • Gemini analysis│  │ • 15min interval │  │ • Ins & Outs     │         │
│  │ • HIGH confidence│  │                  │  │                  │         │
│  └────────┬─────────┘  └──────────────────┘  └──────────────────┘         │
│           │                                                                │
│           │                                                                │
│  ┌────────▼─────────────────────────────────────────────────────────────┐  │
│  │                   BROWSER MONITOR INTERNALS                          │  │
│  │                                                                      │  │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐ │  │
│  │  │ SOURCE CONFIG    │───▶│ PLAYWRIGHT       │───▶│ GEMINI FREE    │ │  │
│  │  │                  │    │ (Headless)       │    │ (Relevance)    │ │  │
│  │  │ • URL patterns   │    │                  │    │                │ │  │
│  │  │ • League mapping │    │ • Max 2 pages    │    │ • is_relevant  │ │  │
│  │  │ • Scan intervals │    │ • 30s timeout    │    │ • category     │ │  │
│  │  │ • Hot reload     │    │ • 10s interval   │    │ • confidence   │ │  │
│  │  └──────────────────┘    └──────────────────┘    └────────────────┘ │  │
│  │                                                                      │  │
│  │  ┌──────────────────┐    ┌──────────────────┐                       │  │
│  │  │ CONTENT CACHE    │    │ RATE LIMITER     │                       │  │
│  │  │                  │    │                  │                       │  │
│  │  │ • Hash-based     │    │ • 60s on 429     │                       │  │
│  │  │ • 24h TTL        │    │ • 10min on 3x429 │                       │  │
│  │  │ • 10k max entries│    │ • Memory monitor │                       │  │
│  │  └──────────────────┘    └──────────────────┘                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. BrowserMonitor

**File**: `src/services/browser_monitor.py`

**Responsibilities**:
- Gestisce il ciclo di scan continuo su URL configurati
- Coordina Playwright per l'estrazione di contenuti
- Invia contenuti a Gemini Free API per analisi di rilevanza
- Notifica news_hunter quando trova news rilevanti

**Interface**:
```python
from dataclasses import dataclass
from typing import Optional, Callable, List
from datetime import datetime

@dataclass
class MonitoredSource:
    """Configuration for a monitored source."""
    url: str
    league_key: str
    scan_interval_minutes: int = 5
    priority: int = 1
    last_scanned: Optional[datetime] = None

@dataclass
class DiscoveredNews:
    """News item discovered by the monitor."""
    url: str
    title: str
    snippet: str
    category: str  # INJURY, LINEUP, SUSPENSION, etc.
    affected_team: str
    confidence: float
    league_key: str
    source_name: str

class BrowserMonitor:
    def __init__(
        self,
        config_file: str = "config/browser_sources.json",
        on_news_discovered: Optional[Callable[[DiscoveredNews], None]] = None
    ):
        self._sources: List[MonitoredSource] = []
        self._running = False
        self._paused = False
        self._on_news_discovered = on_news_discovered
        self._content_cache: Dict[str, datetime] = {}  # hash -> timestamp
        self._consecutive_429s = 0
    
    # Lifecycle
    async def start(self) -> bool
    async def stop(self) -> bool
    def is_running(self) -> bool
    def is_paused(self) -> bool
    
    # Configuration
    def load_sources(self) -> None
    def reload_sources(self) -> None
    def get_sources_for_league(self, league_key: str) -> List[MonitoredSource]
    
    # Scanning
    async def scan_cycle(self) -> int  # Returns number of news found
    async def scan_source(self, source: MonitoredSource) -> Optional[DiscoveredNews]
    
    # Content processing
    async def extract_content(self, url: str) -> Optional[str]
    async def analyze_relevance(self, content: str, league_key: str) -> Optional[dict]
    def is_content_cached(self, content: str) -> bool
    def cache_content(self, content: str) -> None
    
    # Stats
    def get_stats(self) -> dict
```

### 2. MonitorSourceConfig

**File**: `config/browser_sources.json`

**Responsibilities**:
- Definisce quali URL monitorare per ogni lega
- Configurazione hot-reloadable

**Schema**:
```json
{
  "sources": [
    {
      "url": "https://www.fanatik.com.tr/spor/futbol",
      "league_key": "soccer_turkey_super_league",
      "scan_interval_minutes": 5,
      "priority": 1,
      "name": "Fanatik Turkey"
    },
    {
      "url": "https://www.ole.com.ar/futbol-primera",
      "league_key": "soccer_argentina_primera_division",
      "scan_interval_minutes": 5,
      "priority": 1,
      "name": "Ole Argentina"
    }
  ],
  "global_settings": {
    "default_scan_interval_minutes": 5,
    "max_concurrent_pages": 2,
    "navigation_interval_seconds": 10,
    "page_timeout_seconds": 30,
    "cache_ttl_hours": 24,
    "cache_max_entries": 10000
  }
}
```

### 3. RelevanceAnalyzer

**File**: `src/services/browser_monitor.py` (internal class)

**Responsibilities**:
- Costruisce prompt per Gemini Free API
- Parsa risposta JSON di rilevanza
- Gestisce rate limiting di Gemini Free

**Prompt Template**:
```
Analyze this sports news article and determine if it contains betting-relevant information.

ARTICLE TEXT:
{content}

LEAGUE: {league_key}

Respond in JSON format:
{
  "is_relevant": true/false,
  "category": "INJURY" | "LINEUP" | "SUSPENSION" | "TRANSFER" | "TACTICAL" | "OTHER",
  "affected_team": "team name or null",
  "confidence": 0.0-1.0,
  "summary": "brief summary of the news"
}

RULES:
- is_relevant=true only if the news could affect match outcomes
- confidence >= 0.7 for clear betting-relevant news
- category must be one of the specified values
- affected_team should be the team most impacted
```

### 4. NewsHunterIntegration

**File**: `src/processing/news_hunter.py` (modifications)

**Responsibilities**:
- Riceve notifiche dal BrowserMonitor
- Aggiunge news items alla lista del match
- Integra risultati come TIER 0

**New Functions**:
```python
# Global storage for browser monitor discoveries
_browser_monitor_discoveries: Dict[str, List[Dict]] = {}

def register_browser_monitor_discovery(news: 'DiscoveredNews') -> None:
    """
    Callback called by BrowserMonitor when relevant news is found.
    Stores the discovery for later retrieval by run_hunter_for_match.
    """
    pass

def get_browser_monitor_news(match_id: str, team_names: List[str]) -> List[Dict]:
    """
    Get browser monitor discoveries relevant to a match.
    Called by run_hunter_for_match as TIER 0 source.
    """
    pass
```

## Data Models

### MonitoredSource JSON Schema

**File**: `config/browser_sources.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["url", "league_key"],
        "properties": {
          "url": {"type": "string", "format": "uri"},
          "league_key": {"type": "string"},
          "scan_interval_minutes": {"type": "integer", "default": 5},
          "priority": {"type": "integer", "default": 1},
          "name": {"type": "string"}
        }
      }
    },
    "global_settings": {
      "type": "object",
      "properties": {
        "default_scan_interval_minutes": {"type": "integer", "default": 5},
        "max_concurrent_pages": {"type": "integer", "default": 2},
        "navigation_interval_seconds": {"type": "integer", "default": 10},
        "page_timeout_seconds": {"type": "integer", "default": 30},
        "cache_ttl_hours": {"type": "integer", "default": 24},
        "cache_max_entries": {"type": "integer", "default": 10000}
      }
    }
  }
}
```

### DiscoveredNews Structure

```python
{
    "match_id": str,           # Matched from league_key + team
    "team": str,               # affected_team from Gemini
    "keyword": "browser_monitor",
    "title": str,              # From Gemini summary
    "snippet": str,            # From Gemini summary
    "link": str,               # Source URL
    "date": str,               # ISO timestamp
    "source": str,             # Source name from config
    "search_type": "browser_monitor",
    "confidence": "HIGH",      # Always HIGH for browser monitor
    "category": str,           # INJURY, LINEUP, etc.
    "priority_boost": 2.0      # Higher than beat writers
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Configuration Schema Validity
*For any* source configuration loaded from file, the configuration SHALL contain all required fields (url, league_key) and optional fields SHALL have valid default values.
**Validates: Requirements 2.2**

### Property 2: Content Extraction Length Limit
*For any* page content extracted by Playwright, the extracted text length SHALL NOT exceed 30,000 characters.
**Validates: Requirements 3.1**

### Property 3: Gemini Response Schema Validity
*For any* Gemini relevance analysis response, the response SHALL contain all required fields (is_relevant, category, affected_team, confidence, summary) with valid types.
**Validates: Requirements 3.3**

### Property 4: Relevant Content Triggers Callback
*For any* content analyzed by Gemini where is_relevant=true AND confidence >= 0.7, the BrowserMonitor SHALL invoke the on_news_discovered callback with a valid DiscoveredNews object.
**Validates: Requirements 3.4, 4.1**

### Property 5: Non-Relevant Content Skipped
*For any* content analyzed by Gemini where is_relevant=false OR confidence < 0.7, the BrowserMonitor SHALL NOT invoke the on_news_discovered callback.
**Validates: Requirements 3.5**

### Property 6: Content Deduplication
*For any* page content, if the content hash has been seen within the last 24 hours, the BrowserMonitor SHALL skip Gemini analysis and NOT invoke the callback.
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 7: Cache Size Limit
*For any* state of the content cache, the number of entries SHALL NOT exceed 10,000.
**Validates: Requirements 5.4**

### Property 8: Concurrent Page Limit
*For any* point during scanning, the number of concurrent browser pages SHALL NOT exceed 2.
**Validates: Requirements 6.1**

### Property 9: Navigation Rate Limit
*For any* sequence of page navigations, the time between consecutive navigations SHALL be at least 10 seconds.
**Validates: Requirements 6.2**

### Property 10: Memory Pause Behavior
*For any* memory usage above 80%, the BrowserMonitor SHALL pause scanning until memory drops below 70%.
**Validates: Requirements 6.3**

### Property 11: Rate Limit Backoff
*For any* Gemini Free API 429 response, the BrowserMonitor SHALL pause for at least 60 seconds. After 3 consecutive 429s, the pause SHALL be at least 10 minutes.
**Validates: Requirements 7.1, 7.2**

### Property 12: Cooldown Isolation
*For any* Gemini Free API 429 error, the Gemini Direct API cooldown state SHALL remain unchanged.
**Validates: Requirements 7.4**

### Property 13: News Item Schema Validity
*For any* news item added to news_hunter from BrowserMonitor, the item SHALL contain all required fields (match_id, team, title, snippet, link, source, confidence, search_type).
**Validates: Requirements 4.3**

### Property 14: TIER 0 Priority
*For any* execution of run_hunter_for_match(), BrowserMonitor results SHALL appear before TIER 1 and TIER 2 results in the aggregated news list.
**Validates: Requirements 4.4**

## Error Handling

### Page Navigation Errors

| Error Type | Action |
|------------|--------|
| Timeout (>30s) | Skip URL, log warning, continue to next |
| Network error | Retry once after 5s, then skip |
| Invalid URL | Skip, log error |
| Browser crash | Restart browser, continue |

### Gemini API Errors

| Error Type | Action |
|------------|--------|
| 429 (rate limit) | Pause 60s, retry. After 3x: pause 10min |
| 500 (server error) | Retry once after 10s, then skip |
| Invalid response | Log error, skip content |
| Timeout | Skip content, continue |

### Memory Management

```
┌─────────────────────────────────────────────────────────────────┐
│                    MEMORY MONITORING FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Before each navigation:                                        │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ Memory > 80%?   │──── No ────▶ Continue scanning            │
│  └────────┬────────┘                                           │
│           │ Yes                                                 │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Set _paused = True                                    │   │
│  │ 2. Log "⏸️ [BROWSER-MONITOR] Paused: high memory"       │   │
│  │ 3. Wait until memory < 70%                               │   │
│  │ 4. Set _paused = False                                   │   │
│  │ 5. Log "▶️ [BROWSER-MONITOR] Resumed"                   │   │
│  │ 6. Continue scanning                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

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

1. **Configuration Tests**: Verificano caricamento e validazione config
2. **Content Processing Tests**: Verificano estrazione e caching
3. **Gemini Integration Tests**: Verificano analisi di rilevanza
4. **Rate Limiting Tests**: Verificano backoff e pause
5. **Integration Tests**: Verificano flusso end-to-end con news_hunter

### Test File Structure

```
tests/
├── test_browser_monitor.py           # Unit + Property tests
├── test_browser_monitor_config.py    # Configuration tests
├── test_browser_monitor_cache.py     # Caching tests
└── test_browser_monitor_integration.py  # Integration with news_hunter
```

### Key Test Scenarios

1. **Happy Path**: Source configured → Content extracted → Gemini says relevant → Callback invoked
2. **Deduplication**: Same content twice → Second time skipped
3. **Rate Limit**: Gemini 429 → Pause → Resume → Continue
4. **Memory Pressure**: Memory > 80% → Pause → Memory < 70% → Resume
5. **Invalid Content**: Gemini says not relevant → No callback
