# Requirements Document

## Introduction

News Radar Monitor è un componente di monitoraggio news autonomo e indipendente dal bot principale EarlyBird. Opera 24/7 per scoprire notizie rilevanti su fonti web specifiche (link configurati manualmente), inviando alert diretti su Telegram quando trova informazioni betting-relevant su squadre di calcio maschile (infortuni titolari, assenze chiave, convocazioni nazionali, ecc.).

A differenza del Browser Monitor esistente (che alimenta il pipeline del bot), News Radar:
- NON comunica con altri componenti del sistema
- Lavora su leghe NON coperte dal bot principale
- Invia alert Telegram separati e autonomi
- Ha un flusso dati semplificato: trova news → alert Telegram (con fallback DeepSeek per contesti ambigui)

## Glossary

- **News_Radar**: Il nuovo componente di monitoraggio autonomo
- **Relevant_News**: Notizia che riguarda calcio maschile prima squadra con impatto betting (infortuni, assenze, squalifiche, convocazioni nazionali)
- **Exclusion_Filter**: Filtro per escludere sport/categorie non rilevanti (basket, femminile, giovanili, NFL, ecc.)
- **DeepSeek_Fallback**: Chiamata API DeepSeek per disambiguare news con contesto poco chiaro
- **Source_URL**: URL di una fonte web da monitorare (es. https://www.bbc.com/sport/football)
- **Scan_Cycle**: Un ciclo completo di scansione di tutte le fonti configurate
- **Content_Hash**: Hash del contenuto per deduplicazione

## Requirements

### Requirement 1

**User Story:** As a betting analyst, I want News Radar to continuously monitor configured web sources, so that I can discover breaking news on minor leagues before the market reacts.

#### Acceptance Criteria

1. WHEN News_Radar starts THEN the system SHALL load source URLs from a dedicated configuration file and begin the scan loop
2. WHEN a Scan_Cycle completes THEN the system SHALL wait a configurable interval (default 5 minutes) before starting the next cycle
3. WHILE News_Radar is running THEN the system SHALL log scan statistics (URLs scanned, news found, errors) at the end of each cycle
4. IF News_Radar encounters a source that fails repeatedly THEN the system SHALL apply circuit breaker pattern to skip that source temporarily

### Requirement 2

**User Story:** As a betting analyst, I want News Radar to extract clean text from multilingual web pages, so that I can monitor sources in any language.

#### Acceptance Criteria

1. WHEN News_Radar navigates to a source URL THEN the system SHALL extract article text using Trafilatura for clean content extraction
2. WHEN HTTP extraction fails THEN the system SHALL fallback to Playwright browser extraction with stealth mode
3. WHEN extracted content is in a non-English language THEN the system SHALL process it without translation (DeepSeek handles multilingual analysis)
4. IF content extraction returns empty or fails THEN the system SHALL log the failure and continue to the next source

### Requirement 3

**User Story:** As a betting analyst, I want News Radar to filter out irrelevant sports and categories, so that I only receive alerts for men's first team football.

#### Acceptance Criteria

1. WHEN analyzing extracted content THEN the system SHALL apply Exclusion_Filter to reject basketball, NBA, Euroleague news
2. WHEN analyzing extracted content THEN the system SHALL apply Exclusion_Filter to reject women's team, ladies, femminile news
3. WHEN analyzing extracted content THEN the system SHALL apply Exclusion_Filter to reject youth team, Primavera, U19, U21, academy news
4. WHEN analyzing extracted content THEN the system SHALL apply Exclusion_Filter to reject NFL, American football, rugby, handball, volleyball, futsal news
5. WHEN content passes Exclusion_Filter THEN the system SHALL proceed to relevance analysis

### Requirement 4

**User Story:** As a betting analyst, I want News Radar to identify betting-relevant news about player availability, so that I can act on market-moving information.

#### Acceptance Criteria

1. WHEN analyzing content THEN the system SHALL identify news about injured key players or starters
2. WHEN analyzing content THEN the system SHALL identify news about players called up for national team duty
3. WHEN analyzing content THEN the system SHALL identify news about suspended players
4. WHEN analyzing content THEN the system SHALL identify news about players unavailable due to cup competitions or other commitments
5. WHEN Relevant_News is identified with confidence >= 0.7 THEN the system SHALL proceed to alert generation

### Requirement 5

**User Story:** As a betting analyst, I want News Radar to use DeepSeek AI for ambiguous content, so that I don't miss relevant news due to unclear context.

#### Acceptance Criteria

1. WHEN content relevance is uncertain (confidence between 0.5 and 0.7) THEN the system SHALL call DeepSeek API for deeper analysis
2. WHEN DeepSeek confirms relevance THEN the system SHALL proceed to alert generation
3. WHEN DeepSeek API is unavailable THEN the system SHALL skip the ambiguous news and log the event
4. WHEN calling DeepSeek THEN the system SHALL respect rate limiting (minimum 2 seconds between calls)

### Requirement 6

**User Story:** As a betting analyst, I want News Radar to send Telegram alerts for relevant news, so that I receive immediate notifications on my phone.

#### Acceptance Criteria

1. WHEN Relevant_News is confirmed THEN the system SHALL send a formatted Telegram alert to the configured channel
2. WHEN sending alert THEN the system SHALL include: source name, affected team, news category, summary, source URL
3. WHEN sending alert THEN the system SHALL use a distinct format/emoji to distinguish from main bot alerts
4. IF Telegram API fails THEN the system SHALL retry with exponential backoff (max 3 attempts)

### Requirement 7

**User Story:** As a betting analyst, I want News Radar to deduplicate news, so that I don't receive multiple alerts for the same story.

#### Acceptance Criteria

1. WHEN processing extracted content THEN the system SHALL compute Content_Hash from the first 1000 characters
2. WHEN Content_Hash exists in cache THEN the system SHALL skip the content as duplicate
3. WHEN new content is processed THEN the system SHALL store Content_Hash with timestamp in cache
4. WHEN cache entry is older than 24 hours THEN the system SHALL consider it expired and allow re-alerting

### Requirement 8

**User Story:** As a system administrator, I want News Radar to be configurable via JSON file, so that I can add/remove sources without code changes.

#### Acceptance Criteria

1. WHEN News_Radar starts THEN the system SHALL load sources from `config/news_radar_sources.json`
2. WHEN configuration file changes THEN the system SHALL hot-reload sources without restart
3. WHEN a source entry lacks required fields (url) THEN the system SHALL skip it and log a warning
4. WHERE source has optional priority field THEN the system SHALL scan higher priority sources first

### Requirement 9

**User Story:** As a betting analyst, I want News Radar to navigate within sites that require clicking through pages, so that I can monitor sites like betzona.ru that list matches on separate pages.

#### Acceptance Criteria

1. WHERE source is configured with `navigation_mode: "paginated"` THEN the system SHALL extract links from the main page and visit each linked page
2. WHEN visiting linked pages THEN the system SHALL apply the same content extraction and relevance analysis
3. WHEN navigating paginated sources THEN the system SHALL respect a configurable delay between page visits (default 3 seconds)
4. IF linked page navigation fails THEN the system SHALL log the error and continue to the next link

### Requirement 10

**User Story:** As a system administrator, I want News Radar to run independently from the main bot, so that failures in one don't affect the other.

#### Acceptance Criteria

1. WHEN News_Radar is started THEN the system SHALL run in its own process/thread without importing main bot components
2. WHEN News_Radar encounters an unhandled exception THEN the system SHALL log the error and continue operation
3. WHEN News_Radar is stopped THEN the system SHALL gracefully shutdown browser resources and save cache state
4. WHILE News_Radar is running THEN the system SHALL NOT write to the main bot's database
