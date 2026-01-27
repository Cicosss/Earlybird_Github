# Requirements Document

## Introduction

Integrazione di Crawl4AI come alternativa/upgrade al sistema di web scraping esistente in EarlyBird. Crawl4AI è un web crawler open source ottimizzato per LLM che offre:

1. **Architectural Simplification**: Unifica browser automation + content extraction in un'unica libreria
2. **Proxy Rotation**: Gestione automatica dei proxy per scaling (>100 fonti)
3. **fit_markdown Output**: Estrazione markdown ottimizzata per LLM (alternativa a Trafilatura, richiede A/B testing)
4. **magic=True Mode**: Configurazione anti-bot semplificata (usa playwright-stealth internamente)

**SCOPE PRIMARIO**: Integrazione in `browser_monitor.py` (primary) e `news_radar.py` (secondary). Altri scrapers (`aleague_scraper.py`, `nitter_fallback_scraper.py`) sono esclusi perché funzionano bene con architetture esistenti.

**SCOPE ESTESO** (Opzionale): Dopo analisi approfondita, identificate **8 opportunità aggiuntive** di integrazione:
1. 🥇 Tavily AI Search follow-up enhancement (risolve 432 + 403 errors)
2. 🥇 Search Provider fallback chain (bypassa DDG failures)
3. 🥇 DeepSeek Intel Provider content enrichment (full content vs snippet)
4. 🥈 HTTP Client ultimate fallback layer (last resort su 403)
5. 🥈 News Hunter real-time extraction (riduce latency 5 min → 10s)
6. 🥉 FotMob API fallback (web scraping quando API fallisce)
7. 🥉 Weather Provider fallback (resilienza)
8. 🥉 Brave Search content enrichment (full articles vs snippet)

Vedi: `DEEP_ANALYSIS_ADDITIONAL_OPPORTUNITIES.md` per dettagli completi.

**NOTA**: Crawl4AI NON introduce nuove capacità di filtering (BM25ContentFilter è ridondante con ExclusionFilter + RelevanceAnalyzer V7.5) né caching (ContentCache già esiste). Il valore principale è semplificazione architetturale + proxy rotation + fallback intelligente su errors.

## Glossary

- **Crawl4AI**: Web crawler open source con anti-detection avanzato e output markdown LLM-ready
- **Browser_Monitor**: Componente esistente (`src/services/browser_monitor.py`) che monitora fonti web 24/7 usando Playwright + Trafilatura
- **News_Radar**: Componente esistente (`src/services/news_radar.py`) per monitoraggio autonomo di leghe minori
- **Trafilatura**: Libreria Python per estrazione testo pulito da HTML (attualmente usata)
- **Stealth_Mode**: Tecniche anti-detection per evitare blocchi bot (playwright-stealth attuale)
- **Circuit_Breaker**: Pattern per gestire fallimenti temporanei di fonti (già implementato)
- **fit_markdown**: Output Crawl4AI ottimizzato per LLM (alternativa a Trafilatura, richiede validazione)
- **AsyncWebCrawler**: Classe principale Crawl4AI per crawling asincrono
- **Proxy_Rotation**: Gestione automatica dei proxy per evitare rate limits (non implementato in EarlyBird)

## Requirements

### Requirement 1: Crawl4AI Provider Module

**User Story:** As a developer, I want a dedicated Crawl4AI provider module, so that I can use Crawl4AI capabilities without modifying existing components.

#### Acceptance Criteria

1. THE Crawl4AI_Provider SHALL expose an async `extract_content(url)` method compatible with existing interfaces
2. THE Crawl4AI_Provider SHALL use `magic=True` mode for automatic anti-bot handling
3. THE Crawl4AI_Provider SHALL return `fit_markdown` output for LLM-ready content
4. THE Crawl4AI_Provider SHALL implement singleton pattern with lazy initialization
5. WHEN Crawl4AI is not installed, THEN THE Crawl4AI_Provider SHALL return None gracefully without raising exceptions
6. THE Crawl4AI_Provider SHALL support optional proxy rotation via BrowserConfig (for future scaling)

### Requirement 2: Browser Monitor Integration

**User Story:** As a system operator, I want Browser Monitor to use Crawl4AI as primary extractor, so that I can reduce HTTP 403 errors on protected sites.

#### Acceptance Criteria

1. WHEN extracting content, THE Browser_Monitor SHALL try Crawl4AI first before falling back to Playwright
2. WHEN Crawl4AI extraction fails, THE Browser_Monitor SHALL fallback to existing Playwright + Trafilatura pipeline
3. THE Browser_Monitor SHALL track extraction method statistics (crawl4ai_extractions, playwright_fallbacks)
4. WHEN Crawl4AI returns empty content, THE Browser_Monitor SHALL NOT count it as a failure for circuit breaker
5. THE Browser_Monitor SHALL maintain backward compatibility with existing `extract_content()` interface

### Requirement 3: News Radar Integration

**User Story:** As a system operator, I want News Radar to use Crawl4AI for HTTP extraction, so that I can improve success rate on minor league sources.

#### Acceptance Criteria

1. WHEN extracting content via HTTP, THE News_Radar SHALL try Crawl4AI before falling back to requests + Trafilatura
2. THE News_Radar SHALL use Crawl4AI's lightweight mode for HTTP-only extraction when possible
3. WHEN Crawl4AI is unavailable, THE News_Radar SHALL continue using existing HTTP + Trafilatura pipeline
4. THE News_Radar SHALL log extraction method used for monitoring purposes

### Requirement 4: Configuration and Feature Flags

**User Story:** As a system administrator, I want to enable/disable Crawl4AI via configuration, so that I can control rollout and fallback behavior.

#### Acceptance Criteria

1. THE System SHALL read `CRAWL4AI_ENABLED` environment variable to enable/disable Crawl4AI globally
2. WHEN `CRAWL4AI_ENABLED` is false or unset, THE System SHALL use existing Playwright + Trafilatura pipeline
3. THE System SHALL support per-source Crawl4AI override via `browser_sources.json` configuration
4. THE System SHALL log Crawl4AI availability status on startup

### Requirement 5: Error Handling and Resilience

**User Story:** As a system operator, I want robust error handling for Crawl4AI, so that extraction failures don't crash the monitoring loop.

#### Acceptance Criteria

1. WHEN Crawl4AI raises an exception, THE System SHALL catch it and fallback to existing pipeline
2. WHEN Crawl4AI times out, THE System SHALL respect existing `page_timeout_seconds` configuration
3. THE System SHALL NOT retry Crawl4AI extraction more than once per URL per scan cycle
4. IF Crawl4AI fails consistently on a source, THEN THE Circuit_Breaker SHALL track failures normally

### Requirement 6: Performance Monitoring

**User Story:** As a system operator, I want to monitor Crawl4AI performance, so that I can compare it with existing extraction methods.

#### Acceptance Criteria

1. THE System SHALL track `crawl4ai_extractions` count in Browser_Monitor stats
2. THE System SHALL track `crawl4ai_failures` count for monitoring
3. THE System SHALL log extraction time for Crawl4AI vs Playwright comparison
4. WHEN stats are requested, THE System SHALL include Crawl4AI metrics in the response

### Requirement 7: Content Quality Validation

**User Story:** As a developer, I want to validate Crawl4AI output quality, so that I can ensure it meets EarlyBird's content requirements.

#### Acceptance Criteria

1. THE Crawl4AI_Provider SHALL validate extracted content has minimum length (200 chars)
2. THE Crawl4AI_Provider SHALL strip excessive whitespace and normalize line endings
3. WHEN content exceeds MAX_TEXT_LENGTH (30k chars), THE Crawl4AI_Provider SHALL truncate it
4. THE Crawl4AI_Provider SHALL return None for empty or invalid extractions
