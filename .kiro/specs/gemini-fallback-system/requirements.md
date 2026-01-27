# Requirements Document

## Introduction

Questo documento definisce i requisiti per il **Gemini Fallback System V5.0**, un sistema di resilienza intelligente per EarlyBird che gestisce gli errori 429 (rate limit) di Gemini Direct API. Il sistema implementa un fallback immediato a Perplexity per le funzionalità real-time e attiva Browser Automation per arricchire le news durante il periodo di cooldown, consumando i crediti free di Gemini API.

**Contesto Sistema EarlyBird:**
- EarlyBird è un bot di betting intelligence che utilizza triangolazione multi-fonte
- Gemini Direct API è usato per: Deep Dive Analysis, News Verification, Betting Stats Enrichment, Biscotto Confirmation
- Il sistema processa match da Elite 7 (Tier 1) e Tier 2 leagues (15 leghe totali)
- Ogni componente comunica con gli altri attraverso il database SQLite e singleton providers

## Glossary

- **Gemini Direct API**: API ufficiale Google GenAI con Google Search grounding per analisi real-time
- **Perplexity Provider**: Provider AI alternativo (sonar-pro model) con web search grounding
- **Browser Automation**: Playwright headless che estrae testo da pagine web per analisi Gemini
- **Cooldown Period**: Periodo di 24 ore in cui Gemini Direct API non viene chiamato dopo un errore 429
- **Elite 7 (Tier 1)**: Turkey, Argentina, Mexico, Greece, Scotland, Australia, Poland
- **Tier 2**: Norway, France, Belgium, Austria, Netherlands, China, Japan, Brazil Serie B
- **NewsLog**: Tabella database che contiene le news raccolte per ogni match
- **Circuit Breaker**: Pattern che blocca chiamate API dopo errori consecutivi
- **News Enrichment**: Processo di arricchimento delle news con dettagli estratti dalle pagine web

## Requirements

### Requirement 1: Immediate Cooldown Trigger

**User Story:** As a system operator, I want the system to immediately enter cooldown mode on the first 429 error, so that Gemini API can recover without repeated failed requests.

#### Acceptance Criteria

1. WHEN Gemini Direct API returns a 429 error THEN the Cooldown_Manager SHALL immediately set cooldown state to ACTIVE with a 24-hour duration
2. WHEN cooldown state is ACTIVE THEN the Gemini_Agent_Provider SHALL return `is_available() = False` for all subsequent calls
3. WHEN cooldown is activated THEN the Cooldown_Manager SHALL persist the cooldown start timestamp to a JSON file for crash recovery
4. WHEN the system restarts during an active cooldown THEN the Cooldown_Manager SHALL restore the cooldown state from the persisted file
5. WHEN 24 hours have elapsed since cooldown activation THEN the Cooldown_Manager SHALL automatically transition to RECOVERY state

### Requirement 2: Perplexity Fallback for Real-Time Intelligence

**User Story:** As a betting analyst, I want Perplexity to automatically replace Gemini for all real-time intelligence functions during cooldown, so that the system continues providing accurate analysis.

#### Acceptance Criteria

1. WHEN cooldown is ACTIVE and a Deep Dive Analysis is requested THEN the Intelligence_Router SHALL route the request to Perplexity_Provider
2. WHEN cooldown is ACTIVE and News Verification is requested THEN the Intelligence_Router SHALL route the request to Perplexity_Provider
3. WHEN cooldown is ACTIVE and Betting Stats Enrichment is requested THEN the Intelligence_Router SHALL route the request to Perplexity_Provider
4. WHEN cooldown is ACTIVE and Biscotto Confirmation is requested THEN the Intelligence_Router SHALL route the request to Perplexity_Provider
5. WHEN Perplexity_Provider processes a request THEN the response format SHALL be identical to Gemini_Agent_Provider response format
6. WHEN Perplexity_Provider fails THEN the Intelligence_Router SHALL log the error and return None without crashing

### Requirement 3: Browser Automation for News Enrichment

**User Story:** As a system operator, I want Browser Automation to enrich news articles during cooldown, so that Gemini API free credits are utilized for valuable analysis.

#### Acceptance Criteria

1. WHEN cooldown is ACTIVE and a new NewsLog is created for Elite 7 or Tier 2 leagues THEN the Browser_Enrichment_Queue SHALL add the news URL to the processing queue
2. WHEN Browser_Enrichment_Queue processes a URL THEN Playwright SHALL navigate to the URL in headless mode and extract the page text
3. WHEN page text is extracted THEN the Browser_Automation_Provider SHALL send the text to Gemini API for analysis
4. WHEN Gemini API returns enrichment data THEN the Browser_Automation_Provider SHALL update the NewsLog.summary with enriched details
5. WHEN Gemini API returns enrichment data THEN the Browser_Automation_Provider SHALL set NewsLog.source to 'browser_enriched'
6. WHEN page navigation exceeds 30 seconds THEN Playwright SHALL timeout and skip to the next URL in queue
7. WHEN Gemini API returns 429 during Browser Automation THEN the Browser_Automation_Provider SHALL pause for 60 seconds before retrying

### Requirement 4: VPS Resource Management

**User Story:** As a system operator, I want Browser Automation to respect VPS resource limits, so that the system remains stable during high load.

#### Acceptance Criteria

1. WHEN Browser_Enrichment_Queue is processing THEN the system SHALL limit concurrent browser instances to 4 maximum
2. WHEN processing URLs THEN the Browser_Enrichment_Queue SHALL enforce a minimum 5-second interval between page navigations
3. WHEN VPS memory usage exceeds 80% THEN the Browser_Enrichment_Queue SHALL pause processing until memory drops below 70%
4. WHEN a browser instance crashes THEN the Browser_Automation_Provider SHALL log the error and continue with remaining instances
5. WHEN the enrichment queue exceeds 100 pending URLs THEN the Browser_Enrichment_Queue SHALL prioritize Elite 7 news over Tier 2

### Requirement 5: Cooldown Recovery and Monitoring

**User Story:** As a system operator, I want to monitor cooldown status and receive notifications, so that I can track system health.

#### Acceptance Criteria

1. WHEN cooldown is activated THEN the Notifier SHALL send a Telegram alert with cooldown start time and expected end time
2. WHEN cooldown ends THEN the Notifier SHALL send a Telegram alert confirming Gemini Direct API is available
3. WHEN /status command is received THEN the Telegram_Bot SHALL respond with current cooldown state, time remaining, and enrichment queue size
4. WHEN cooldown transitions to RECOVERY state THEN the Cooldown_Manager SHALL test Gemini API with a single lightweight request
5. IF the recovery test succeeds THEN the Cooldown_Manager SHALL transition to NORMAL state
6. IF the recovery test fails with 429 THEN the Cooldown_Manager SHALL extend cooldown by another 24 hours

### Requirement 6: Data Persistence and Crash Recovery

**User Story:** As a system operator, I want the system to recover gracefully from crashes during cooldown, so that no state is lost.

#### Acceptance Criteria

1. WHEN cooldown state changes THEN the Cooldown_Manager SHALL persist the state to `data/cooldown_state.json`
2. WHEN Browser_Enrichment_Queue adds a URL THEN the queue SHALL persist to `data/enrichment_queue.json`
3. WHEN the system starts THEN the Cooldown_Manager SHALL load state from `data/cooldown_state.json` if it exists
4. WHEN the system starts THEN the Browser_Enrichment_Queue SHALL resume processing from `data/enrichment_queue.json`
5. WHEN a NewsLog is enriched THEN the enrichment timestamp SHALL be stored in the database for audit purposes

### Requirement 7: Logging and Observability

**User Story:** As a developer, I want comprehensive logging of fallback operations, so that I can debug issues and monitor performance.

#### Acceptance Criteria

1. WHEN cooldown is activated THEN the system SHALL log "🚨 [COOLDOWN] Gemini Direct API cooldown activated for 24h"
2. WHEN a request is routed to Perplexity THEN the system SHALL log "🔮 [FALLBACK] Request routed to Perplexity: {operation_name}"
3. WHEN Browser Automation enriches a news item THEN the system SHALL log "🌐 [BROWSER] Enriched: {url} ({chars} chars extracted)"
4. WHEN Gemini API is called during Browser Automation THEN the system SHALL log "🤖 [GEMINI-FREE] Analyzing extracted text ({chars} chars)"
5. WHEN cooldown ends THEN the system SHALL log "✅ [COOLDOWN] Gemini Direct API recovered - normal operations resumed"
