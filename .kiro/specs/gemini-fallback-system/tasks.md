# Implementation Plan

Questo piano è diviso in **3 fasi** per permettere l'implementazione incrementale in chat separate. Ogni fase è autocontenuta e può essere eseguita indipendentemente.

---

## 🔴 FASE 1: Cooldown Manager e Persistence Layer

**Obiettivo**: Implementare il sistema di cooldown con persistenza e recovery.

**Contesto per la chat**:
> Stiamo implementando il Gemini Fallback System V5.0 per EarlyBird. In questa fase creiamo il CooldownManager che gestisce lo stato del cooldown (NORMAL/ACTIVE/RECOVERY) con persistenza JSON per crash recovery. Al primo errore 429 di Gemini, il sistema entra in cooldown per 24 ore.

**File da modificare/creare**:
- `src/services/cooldown_manager.py` (nuovo)
- `src/ingestion/gemini_agent_provider.py` (modifica)
- `tests/test_cooldown_manager.py` (nuovo)

---

- [x] 1. Implement CooldownManager core
  - [x] 1.1 Create `src/services/cooldown_manager.py` with CooldownState enum and CooldownStatus dataclass
    - Define states: NORMAL, ACTIVE, RECOVERY
    - Define CooldownStatus with: state, activated_at, expires_at, extension_count, last_error
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Implement state persistence methods
    - `_persist_state()`: Save to `data/cooldown_state.json`
    - `_load_state()`: Load from JSON on init, handle missing file gracefully
    - Use atomic write (write to temp, then rename) for crash safety
    - _Requirements: 1.3, 1.4, 6.1, 6.3_

  - [x] 1.3 Write property test for state persistence round-trip
    - **Property 1: Cooldown State Persistence Round-Trip**
    - **Validates: Requirements 1.3, 1.4, 6.1, 6.3**

  - [x] 1.4 Implement cooldown activation and state transitions
    - `activate_cooldown(error_message)`: Set state to ACTIVE, set 24h expiration
    - `is_cooldown_active()`: Return True if state is ACTIVE
    - `check_and_transition()`: Check if 24h elapsed, transition to RECOVERY
    - `extend_cooldown()`: Add another 24h (for failed recovery)
    - `reset_to_normal()`: Reset to NORMAL state
    - _Requirements: 1.1, 1.5, 5.4, 5.5, 5.6_

  - [x] 1.5 Write property test for cooldown activation
    - **Property 2: Cooldown Activation on 429**
    - **Validates: Requirements 1.1, 1.2**

  - [x] 1.6 Implement recovery test mechanism
    - `test_recovery()`: Make lightweight Gemini API call to test availability
    - If success: transition to NORMAL
    - If 429: call `extend_cooldown()`
    - _Requirements: 5.4, 5.5, 5.6_

  - [x] 1.7 Write property test for time-based transitions
    - **Property 11: Cooldown Time Transition**
    - **Validates: Requirements 1.5, 5.4**

- [x] 2. Integrate CooldownManager with GeminiAgentProvider
  - [x] 2.1 Modify `GeminiAgentProvider._call_with_retry()` to detect first 429
    - Remove existing circuit breaker retry logic (3 consecutive 429s)
    - On first 429: call `CooldownManager.activate_cooldown()`
    - Return None immediately (no retries)
    - _Requirements: 1.1_

  - [x] 2.2 Modify `GeminiAgentProvider.is_available()` to check cooldown state
    - If `CooldownManager.is_cooldown_active()`: return False
    - Keep existing checks (API key, SDK availability)
    - _Requirements: 1.2_

  - [x] 2.3 Write property test for provider availability during cooldown
    - **Property 3: Provider Availability During Cooldown**
    - **Validates: Requirements 1.2, 2.1-2.4**

- [x] 3. Add Telegram notifications for cooldown events
  - [x] 3.1 Add notification methods to CooldownManager
    - `_notify_cooldown_activated()`: Send alert with start/end time
    - `_notify_cooldown_ended()`: Send alert confirming recovery
    - Use existing `send_telegram_message()` from notifier
    - _Requirements: 5.1, 5.2_

  - [x] 3.2 Add /status command handler for cooldown info
    - Return: current state, time remaining, extension count
    - Format: emoji + Italian text
    - _Requirements: 5.3_

- [x] 4. Checkpoint - Phase 1 Complete
  - Ensure all tests pass, ask the user if questions arise.

---

## 🟡 FASE 2: Intelligence Router e Perplexity Integration

**Obiettivo**: Implementare il router che instrada le richieste al provider corretto.

**Contesto per la chat**:
> Continuiamo l'implementazione del Gemini Fallback System V5.0. Nella Fase 1 abbiamo creato il CooldownManager in `src/services/cooldown_manager.py`. Ora creiamo l'IntelligenceRouter che instrada le richieste a Gemini (quando disponibile) o Perplexity (durante cooldown). Il router espone la stessa interfaccia di GeminiAgentProvider per compatibilità.

**File creati in Fase 1**:
- `src/services/cooldown_manager.py` - Gestisce stato cooldown con persistenza JSON

**File da modificare/creare**:
- `src/services/intelligence_router.py` (nuovo)
- `src/ingestion/perplexity_provider.py` (modifica - aggiungere metodi mancanti)
- `src/main.py` (modifica - usare router invece di gemini_provider diretto)
- `src/analysis/analyzer.py` (modifica - usare router)
- `tests/test_intelligence_router.py` (nuovo)

---

- [x] 5. Extend PerplexityProvider with missing methods
  - [x] 5.1 Add `verify_news_item()` method to PerplexityProvider
    - Same signature as GeminiAgentProvider.verify_news_item()
    - Use `build_news_verification_prompt()` from prompts.py
    - Return same response structure
    - _Requirements: 2.2, 2.5_

  - [x] 5.2 Add `verify_news_batch()` method to PerplexityProvider
    - Same signature as GeminiAgentProvider.verify_news_batch()
    - Reuse logic from Gemini version
    - _Requirements: 2.2, 2.5_

  - [x] 5.3 Add `get_betting_stats()` method to PerplexityProvider
    - Same signature as GeminiAgentProvider.get_betting_stats()
    - Use `build_betting_stats_prompt()` from prompts.py
    - _Requirements: 2.3, 2.5_

  - [x] 5.4 Add `confirm_biscotto()` method to PerplexityProvider
    - Same signature as GeminiAgentProvider.confirm_biscotto()
    - Use `build_biscotto_confirmation_prompt()` from prompts.py
    - _Requirements: 2.4, 2.5_

  - [x] 5.5 Write property test for response format compatibility
    - **Property 5: Response Format Compatibility**
    - **Validates: Requirements 2.5**

- [x] 6. Implement IntelligenceRouter
  - [x] 6.1 Create `src/services/intelligence_router.py` with singleton pattern
    - Initialize CooldownManager, GeminiAgentProvider, PerplexityProvider
    - Expose `is_available()` and `get_active_provider_name()`
    - _Requirements: 2.1-2.4_

  - [x] 6.2 Implement request routing logic
    - `_route_request(operation, func, *args, **kwargs)`: Core routing method
    - If cooldown ACTIVE: route to Perplexity
    - If cooldown NORMAL: route to Gemini
    - Handle 429 errors: activate cooldown, retry with Perplexity
    - _Requirements: 2.1-2.4_

  - [x] 6.3 Write property test for request routing consistency
    - **Property 4: Request Routing Consistency**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [x] 6.4 Implement proxied methods (same interface as GeminiAgentProvider)
    - `get_match_deep_dive()`: Route to active provider
    - `verify_news_item()`: Route to active provider
    - `verify_news_batch()`: Route to active provider
    - `get_betting_stats()`: Route to active provider
    - `confirm_biscotto()`: Route to active provider
    - `format_for_prompt()`: Use active provider's formatter
    - _Requirements: 2.1-2.4_

  - [x] 6.5 Implement graceful error handling
    - If Perplexity fails: log error, return None (no crash)
    - If both providers fail: return None with warning log
    - _Requirements: 2.6_

  - [x] 6.6 Write property test for graceful error handling
    - **Property 10: Graceful Error Handling**
    - **Validates: Requirements 2.6, 4.4**

- [x] 7. Update callers to use IntelligenceRouter
  - [x] 7.1 Update `src/main.py` to use IntelligenceRouter
    - Replace `get_gemini_provider()` calls with `get_intelligence_router()`
    - Update imports
    - Keep same logic flow, just change provider source
    - _Requirements: 2.1-2.4_

  - [x] 7.2 Update `src/analysis/analyzer.py` to use IntelligenceRouter
    - Replace `get_gemini_provider()` with `get_intelligence_router()`
    - Update deep dive call in `analyze_with_triangulation()`
    - _Requirements: 2.1_

  - [x] 7.3 Update `src/services/tweet_relevance_filter.py` to use IntelligenceRouter
    - Replace Gemini provider with router
    - _Requirements: 2.1-2.4_

- [x] 8. Checkpoint - Phase 2 Complete
  - Ensure all tests pass, ask the user if questions arise.

---

## 🟢 FASE 3: Browser Automation e News Enrichment

**Obiettivo**: Implementare l'arricchimento delle news via Playwright + Gemini API.

**Contesto per la chat**:
> Completiamo l'implementazione del Gemini Fallback System V5.0. Nella Fase 1 abbiamo creato il CooldownManager (`src/services/cooldown_manager.py`). Nella Fase 2 abbiamo creato l'IntelligenceRouter (`src/services/intelligence_router.py`) che instrada a Perplexity durante il cooldown. Ora implementiamo il Browser Automation che arricchisce le news Elite 7 e Tier 2 durante il cooldown, usando Playwright per estrarre testo e Gemini API (crediti free) per l'analisi.

**File creati in Fase 1**:
- `src/services/cooldown_manager.py` - Gestisce stato cooldown

**File creati in Fase 2**:
- `src/services/intelligence_router.py` - Instrada richieste a Gemini/Perplexity

**File da modificare/creare**:
- `src/services/browser_automation_provider.py` (nuovo)
- `src/services/enrichment_queue.py` (nuovo)
- `src/services/enrichment_worker.py` (nuovo)
- `src/ingestion/prompts.py` (modifica - aggiungere prompt per enrichment)
- `src/main.py` (modifica - integrare enrichment worker)
- `tests/test_browser_automation.py` (nuovo)
- `tests/test_enrichment_queue.py` (nuovo)

---

- [ ] 9. Implement EnrichmentQueue
  - [ ] 9.1 Create `src/services/enrichment_queue.py` with QueueItem dataclass
    - Define QueueItem: news_log_id, url, league, priority, added_at, attempts
    - Priority: 1 = Elite 7, 2 = Tier 2
    - _Requirements: 3.1, 4.5_

  - [ ] 9.2 Implement queue management methods
    - `add(news_log, league)`: Add item with correct priority
    - `get_next()`: Return highest priority item (Elite 7 first when queue > 100)
    - `mark_complete(news_log_id)`: Remove from queue
    - `mark_failed(news_log_id)`: Increment attempts, requeue if < 3 attempts
    - `get_queue_size()`: Return total pending items
    - `get_pending_count()`: Return (elite7_count, tier2_count)
    - _Requirements: 3.1, 4.5_

  - [ ] 9.3 Implement queue persistence
    - `_persist()`: Save to `data/enrichment_queue.json`
    - `_load()`: Load on init, handle missing file
    - Persist after every add/complete/failed operation
    - _Requirements: 6.2, 6.4_

  - [ ] 9.4 Write property test for queue persistence round-trip
    - **Property 7: Enrichment Queue Persistence Round-Trip**
    - **Validates: Requirements 6.2, 6.4**

  - [ ] 9.5 Write property test for queue priority ordering
    - **Property 6: Queue Priority Ordering**
    - **Validates: Requirements 4.5**

- [ ] 10. Implement BrowserAutomationProvider
  - [ ] 10.1 Create `src/services/browser_automation_provider.py` with Playwright integration
    - `initialize()`: Launch Chromium headless
    - `shutdown()`: Close browser and Playwright
    - Use asyncio.Semaphore for concurrency control (max 4)
    - _Requirements: 4.1_

  - [ ] 10.2 Implement page text extraction
    - `_extract_page_text(url)`: Navigate and extract inner_text
    - Timeout: 30 seconds
    - Handle navigation errors gracefully
    - Limit extracted text to 30,000 characters
    - _Requirements: 3.2, 3.6_

  - [ ] 10.3 Implement Gemini API analysis
    - `_analyze_with_gemini(text, context)`: Send text to Gemini API
    - Use `gemini-3-flash-preview` model (same as direct API)
    - NO Google Search grounding (just text analysis)
    - Handle 429: pause 60s, retry once
    - _Requirements: 3.3, 3.7_

  - [ ] 10.4 Add enrichment prompt to `src/ingestion/prompts.py`
    - `build_news_enrichment_prompt(text, team_name, match_context)`
    - Extract: player names, injury severity, timeline, betting impact
    - Output: JSON with structured data
    - _Requirements: 3.3_

  - [ ] 10.5 Implement NewsLog update logic
    - `enrich_news_item(news_log)`: Full enrichment flow
    - Update `summary` with enriched details
    - Set `source` to 'browser_enriched'
    - Update `category` if analysis provides better classification
    - _Requirements: 3.4, 3.5_

  - [ ] 10.6 Write property test for NewsLog source update
    - **Property 12: NewsLog Source Update**
    - **Validates: Requirements 3.5**

- [ ] 11. Implement EnrichmentWorker
  - [ ] 11.1 Create `src/services/enrichment_worker.py` with async worker loop
    - `start()`: Begin processing loop
    - `stop()`: Graceful shutdown
    - `is_running()`: Check worker status
    - _Requirements: 3.1_

  - [ ] 11.2 Implement rate limiting and resource monitoring
    - Enforce 5-second minimum interval between navigations
    - Check memory usage before each item
    - Pause if memory > 80%, resume when < 70%
    - _Requirements: 4.2, 4.3_

  - [ ] 11.3 Write property test for rate limiting interval
    - **Property 9: Rate Limiting Interval**
    - **Validates: Requirements 4.2**

  - [ ] 11.4 Write property test for concurrent browser limit
    - **Property 8: Concurrent Browser Limit**
    - **Validates: Requirements 4.1**

- [ ] 12. Integrate Browser Automation with main flow
  - [ ] 12.1 Update `src/main.py` to start EnrichmentWorker on cooldown
    - When CooldownManager activates: start worker
    - When cooldown ends: stop worker
    - _Requirements: 3.1_

  - [ ] 12.2 Update NewsLog creation to queue for enrichment
    - After creating NewsLog for Elite 7 or Tier 2 league
    - If cooldown is ACTIVE: add to EnrichmentQueue
    - _Requirements: 3.1_

  - [ ] 12.3 Add enrichment stats to /status command
    - Show: queue size, processed count, failed count
    - _Requirements: 5.3_

- [ ] 13. Add comprehensive logging
  - [ ] 13.1 Add logging statements per requirements
    - Cooldown activation: "🚨 [COOLDOWN] Gemini Direct API cooldown activated for 24h"
    - Perplexity routing: "🔮 [FALLBACK] Request routed to Perplexity: {operation}"
    - Browser enrichment: "🌐 [BROWSER] Enriched: {url} ({chars} chars)"
    - Gemini free call: "🤖 [GEMINI-FREE] Analyzing extracted text ({chars} chars)"
    - Cooldown end: "✅ [COOLDOWN] Gemini Direct API recovered"
    - _Requirements: 7.1-7.5_

- [ ] 14. Final Checkpoint - All Phases Complete
  - Ensure all tests pass, ask the user if questions arise.

---

## 📋 Riepilogo File per Fase

### Fase 1 (Cooldown Manager)
| File | Azione |
|------|--------|
| `src/services/cooldown_manager.py` | Nuovo |
| `src/ingestion/gemini_agent_provider.py` | Modifica |
| `tests/test_cooldown_manager.py` | Nuovo |
| `data/cooldown_state.json` | Generato automaticamente |

### Fase 2 (Intelligence Router)
| File | Azione |
|------|--------|
| `src/services/intelligence_router.py` | Nuovo |
| `src/ingestion/perplexity_provider.py` | Modifica |
| `src/main.py` | Modifica |
| `src/analysis/analyzer.py` | Modifica |
| `src/services/tweet_relevance_filter.py` | Modifica |
| `tests/test_intelligence_router.py` | Nuovo |

### Fase 3 (Browser Automation)
| File | Azione |
|------|--------|
| `src/services/browser_automation_provider.py` | Nuovo |
| `src/services/enrichment_queue.py` | Nuovo |
| `src/services/enrichment_worker.py` | Nuovo |
| `src/ingestion/prompts.py` | Modifica |
| `src/main.py` | Modifica |
| `tests/test_browser_automation.py` | Nuovo |
| `tests/test_enrichment_queue.py` | Nuovo |
| `data/enrichment_queue.json` | Generato automaticamente |
