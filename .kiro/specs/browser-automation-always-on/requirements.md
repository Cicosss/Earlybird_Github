# Requirements Document

## Introduction

Questo documento definisce i requisiti per **Browser Automation Always-On**, un nuovo componente indipendente che monitora attivamente fonti web per scoprire notizie rilevanti e le segnala al sistema di hunting esistente.

**Contesto Attuale:**
- Il `BrowserAutomationProvider` usa Playwright headless + Gemini Free API per arricchire le news
- Attualmente si attiva SOLO come fallback durante il cooldown di Gemini
- Il `news_hunter.py` è il componente centrale che aggrega news da varie fonti (DDG, Serper, Twitter, RSSHub)

**Obiettivo:**
- Creare un **Browser Monitor** indipendente che gira h24
- Il monitor naviga attivamente su fonti web configurate (siti di news sportive)
- Estrae contenuti con Playwright e li analizza con Gemini Free API
- Quando trova notizie rilevanti, le **segnala a news_hunter** come nuova fonte TIER 0
- Funziona in parallelo al sistema esistente, non lo sostituisce

## Glossary

- **Browser Monitor**: Nuovo componente indipendente che monitora attivamente fonti web h24
- **Browser Automation Provider**: Componente esistente che usa Playwright headless per estrarre testo da pagine web
- **News Hunter**: Componente centrale (`src/processing/news_hunter.py`) che aggrega news da tutte le fonti
- **Monitor Sources**: Lista configurabile di URL/domini da monitorare per ogni lega
- **Relevance Analysis**: Analisi Gemini Free API per determinare se un articolo è rilevante per betting
- **Elite 7 (Tier 1)**: Turkey, Argentina, Mexico, Greece, Scotland, Australia, Poland
- **Tier 2**: Norway, France, Belgium, Austria, Netherlands, China, Japan, Brazil Serie B
- **NewsLog**: Tabella database che contiene le news raccolte per ogni match
- **Gemini Free API**: API Google GenAI con crediti gratuiti (rate limit più basso di Direct API)
- **TIER 0 Source**: Fonte ad alta priorità nel sistema di hunting (come RSSHub, A-League scraper)

## Requirements

### Requirement 1: Independent Browser Monitor Service

**User Story:** As a system operator, I want a Browser Monitor that runs independently h24, so that I can discover breaking news from web sources before they appear on search engines.

#### Acceptance Criteria

1. WHEN the system starts THEN the Browser_Monitor SHALL start automatically as a separate async process
2. WHILE the Browser_Monitor is running THEN the monitor SHALL continuously scan configured source URLs in a loop
3. WHEN the Browser_Monitor completes a scan cycle THEN the monitor SHALL wait a configurable interval (default 5 minutes) before the next cycle
4. WHEN the system shuts down THEN the Browser_Monitor SHALL stop gracefully and release browser resources

### Requirement 2: Configurable Monitor Sources

**User Story:** As a developer, I want to configure which URLs the Browser Monitor scans for each league, so that I can target the most valuable news sources.

#### Acceptance Criteria

1. WHEN the Browser_Monitor initializes THEN the monitor SHALL load source URLs from a configuration file (`config/browser_sources.json`)
2. WHEN a source URL is configured THEN the configuration SHALL include: URL pattern, league_key, scan_interval_minutes, and priority
3. WHEN the configuration file is updated THEN the Browser_Monitor SHALL reload sources without restart (hot reload)
4. WHEN no sources are configured for a league THEN the Browser_Monitor SHALL skip that league silently

### Requirement 3: Content Extraction and Analysis

**User Story:** As a system operator, I want the Browser Monitor to extract and analyze web content, so that only relevant betting news is reported.

#### Acceptance Criteria

1. WHEN the Browser_Monitor visits a source URL THEN Playwright SHALL extract the page text content (max 30k chars)
2. WHEN page text is extracted THEN the Browser_Monitor SHALL send the text to Gemini Free API for relevance analysis
3. WHEN Gemini analyzes the content THEN the response SHALL include: is_relevant (bool), category (INJURY/LINEUP/SUSPENSION/etc), affected_team, confidence, summary
4. WHEN Gemini determines content is relevant (is_relevant=true AND confidence >= 0.7) THEN the Browser_Monitor SHALL create a news item for news_hunter
5. WHEN content is not relevant THEN the Browser_Monitor SHALL skip the item and continue scanning

### Requirement 4: Integration with News Hunter

**User Story:** As a developer, I want the Browser Monitor to feed discovered news into news_hunter, so that the existing analysis pipeline processes them.

#### Acceptance Criteria

1. WHEN the Browser_Monitor discovers relevant news THEN the monitor SHALL call a callback function to notify news_hunter
2. WHEN news_hunter receives a Browser_Monitor notification THEN news_hunter SHALL add the item to the match's news list with search_type='browser_monitor'
3. WHEN a Browser_Monitor news item is added THEN the item SHALL include: match_id, team, title, snippet, link, source, confidence='HIGH', search_type='browser_monitor'
4. WHEN news_hunter runs `run_hunter_for_match()` THEN the function SHALL include Browser_Monitor results as TIER 0 source (highest priority)

### Requirement 5: Deduplication and Caching

**User Story:** As a system operator, I want the Browser Monitor to avoid processing the same content twice, so that resources are used efficiently.

#### Acceptance Criteria

1. WHEN the Browser_Monitor extracts page content THEN the monitor SHALL compute a content hash (first 1000 chars)
2. WHEN the content hash matches a previously seen hash THEN the Browser_Monitor SHALL skip analysis and continue
3. WHEN a content hash is stored THEN the cache SHALL expire after 24 hours
4. WHEN the cache exceeds 10000 entries THEN the Browser_Monitor SHALL evict oldest entries (LRU)

### Requirement 6: Resource Management

**User Story:** As a system operator, I want the Browser Monitor to respect VPS resource limits, so that the system remains stable.

#### Acceptance Criteria

1. WHILE the Browser_Monitor is scanning THEN the system SHALL limit concurrent browser pages to 2 maximum
2. WHILE scanning URLs THEN the Browser_Monitor SHALL enforce a minimum 10-second interval between page navigations
3. WHEN VPS memory usage exceeds 80% THEN the Browser_Monitor SHALL pause scanning until memory drops below 70%
4. WHEN a page navigation exceeds 30 seconds THEN Playwright SHALL timeout and skip to the next URL

### Requirement 7: Gemini Free API Rate Limit Handling

**User Story:** As a system operator, I want the Browser Monitor to handle Gemini Free API rate limits gracefully, so that monitoring continues without disruption.

#### Acceptance Criteria

1. WHEN Gemini Free API returns 429 THEN the Browser_Monitor SHALL pause for 60 seconds before retrying
2. WHEN Gemini Free API returns 429 three consecutive times THEN the Browser_Monitor SHALL pause for 10 minutes
3. WHEN Gemini Free API recovers after pause THEN the Browser_Monitor SHALL resume normal scanning
4. WHEN Gemini Free API rate limit is hit THEN the system SHALL NOT affect Gemini Direct API cooldown state (separate tracking)

### Requirement 8: Monitoring and Observability

**User Story:** As a system operator, I want to monitor the Browser Monitor status, so that I can track its performance.

#### Acceptance Criteria

1. WHEN /status command is received THEN the Telegram_Bot SHALL include Browser_Monitor status (running/paused, URLs scanned, news discovered)
2. WHEN the Browser_Monitor discovers a HIGH confidence news item THEN the system SHALL log "🌐 [BROWSER-MONITOR] Discovered: {title} for {team} (confidence: {conf})"
3. WHEN the Browser_Monitor completes a scan cycle THEN the system SHALL log "🌐 [BROWSER-MONITOR] Cycle complete: {urls_scanned} URLs, {news_found} relevant items"
4. WHEN the Browser_Monitor pauses due to rate limit THEN the system SHALL log "⏸️ [BROWSER-MONITOR] Paused: Gemini rate limit, resuming in {seconds}s"

