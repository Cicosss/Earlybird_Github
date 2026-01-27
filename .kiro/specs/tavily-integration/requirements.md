# Requirements Document

## Introduction

Questo documento definisce i requisiti per l'integrazione di Tavily AI Search API nel sistema EarlyBird. Tavily è un motore di ricerca ottimizzato per AI che fornisce risultati strutturati e rilevanti, ideale per arricchire l'intelligence del sistema di betting.

L'integrazione sfrutterà il budget di 7000 chiamate API/mese (7 API keys da 1000 chiamate ciascuna) distribuendole strategicamente su 6 punti di integrazione: Main Pipeline (30%), News Radar (21%), Browser Monitor (11%), Telegram Monitor (6%), Settlement/CLV (3%), e Twitter Intel Recovery (buffer).

Il sistema implementa una **rotazione automatica delle API keys**: quando una key esaurisce i crediti, passa automaticamente alla successiva in ordine (1→2→3→4→5→6→7).

La caratteristica chiave di Tavily è la capacità di rispondere a query complesse con multiple domande in una singola chiamata (simile a Perplexity), permettendo ottimizzazione del budget API tramite "Query Batching".

## Glossary

- **Tavily**: AI-optimized search API che fornisce risultati strutturati con snippet rilevanti
- **Query Batching**: Tecnica di combinare multiple domande in una singola query API per ottimizzare il budget
- **EarlyBird**: Sistema di betting intelligence con triangolazione multi-fonte
- **Intelligence Router**: Componente che instrada le richieste AI tra provider (DeepSeek/Perplexity)
- **News Radar**: Monitor autonomo che scansiona fonti web per news betting-relevant
- **Browser Monitor**: Componente che monitora pagine web configurate con Playwright
- **Telegram Monitor**: Listener per canali Telegram con intel insider
- **Settler**: Componente che valuta i risultati delle scommesse post-match
- **CLV Tracker**: Closing Line Value tracker per validazione edge
- **Twitter Intel Cache**: Cache per intel Twitter con fallback Nitter
- **Rate Limiter**: Meccanismo per rispettare i limiti API (1 req/sec per Tavily)
- **TTL**: Time-To-Live per cache entries (30 minuti default per Tavily)
- **API Key Rotation**: Sistema di rotazione automatica tra 7 API keys (1000 chiamate ciascuna)
- **Key Pool**: Lista ordinata di API keys da utilizzare in sequenza

## Requirements

### Requirement 1: Tavily Provider Core

**User Story:** As a system developer, I want a dedicated Tavily provider module, so that I can integrate Tavily search capabilities across the EarlyBird system.

#### Acceptance Criteria

1. WHEN the system initializes the Tavily provider THEN the Tavily_Provider SHALL load all 7 API keys from environment/config and validate each one
2. WHEN a search query is submitted THEN the Tavily_Provider SHALL enforce rate limiting of maximum 1 request per second
3. WHEN search results are received THEN the Tavily_Provider SHALL cache results with 30-minute TTL to avoid duplicate queries
4. WHEN the current API key returns 429 (quota exceeded) THEN the Tavily_Provider SHALL automatically rotate to the next available key in sequence
5. IF all 7 API keys are exhausted THEN the Tavily_Provider SHALL switch to degraded mode and use Brave/DDG fallback
6. IF the API returns an error other than 429 THEN the Tavily_Provider SHALL return None and log the error without crashing

### Requirement 11: API Key Rotation System

**User Story:** As a system administrator, I want automatic rotation between 7 Tavily API keys, so that I can maximize the total available quota of 7000 calls/month.

#### Acceptance Criteria

1. WHEN the Tavily_Provider initializes THEN the Key_Rotator SHALL load keys in order from TAVILY_API_KEY_1 through TAVILY_API_KEY_7
2. WHEN the current key returns 429 error THEN the Key_Rotator SHALL mark the key as exhausted and switch to the next key in sequence
3. WHEN switching to a new key THEN the Key_Rotator SHALL log the rotation event with key index and remaining keys count
4. WHEN all 7 keys are exhausted THEN the Key_Rotator SHALL set provider to unavailable and trigger fallback mode
5. WHEN a new month starts THEN the Key_Rotator SHALL reset all keys to available status and restart from key 1

### Requirement 2: Query Batching System

**User Story:** As a system architect, I want to combine multiple questions into single Tavily queries, so that I can maximize the value from each API call.

#### Acceptance Criteria

1. WHEN multiple questions are needed for the same match context THEN the Query_Builder SHALL combine them into a single structured query
2. WHEN building a batched query THEN the Query_Builder SHALL format questions with clear separators for AI parsing
3. WHEN parsing batched responses THEN the Query_Builder SHALL extract individual answers mapped to original questions
4. WHEN a batched query exceeds 500 characters THEN the Query_Builder SHALL split into multiple queries

### Requirement 3: Main Pipeline Integration

**User Story:** As a betting analyst, I want Tavily to enrich match analysis in the main pipeline, so that I get higher quality intelligence for betting decisions.

#### Acceptance Criteria

1. WHEN a match requires deep enrichment THEN the Intelligence_Router SHALL call Tavily for match context before DeepSeek analysis
2. WHEN Tavily returns match intelligence THEN the Intelligence_Router SHALL merge results with existing FotMob/news data
3. WHEN confirming a biscotto signal THEN the Intelligence_Router SHALL use Tavily to search for mutual benefit evidence
4. WHEN verifying news batch THEN the Intelligence_Router SHALL use Tavily as pre-filter before DeepSeek verification

### Requirement 4: News Radar Integration

**User Story:** As a news monitor operator, I want Tavily to pre-enrich ambiguous content, so that DeepSeek receives better context for analysis.

#### Acceptance Criteria

1. WHEN News_Radar detects content with confidence between 0.5 and 0.7 THEN the News_Radar SHALL call Tavily for additional context
2. WHEN Tavily returns enrichment THEN the News_Radar SHALL append context to content before DeepSeek analysis
3. WHEN Tavily enrichment confirms relevance THEN the News_Radar SHALL boost confidence by 0.15
4. IF Tavily is unavailable THEN the News_Radar SHALL proceed with DeepSeek analysis without pre-enrichment

### Requirement 5: Browser Monitor Integration

**User Story:** As a web monitor operator, I want Tavily as fallback for short content analysis, so that I can still extract value from pages with minimal text.

#### Acceptance Criteria

1. WHEN Browser_Monitor extracts content shorter than 500 characters THEN the Browser_Monitor SHALL call Tavily to search for related news
2. WHEN Tavily returns related articles THEN the Browser_Monitor SHALL merge snippets with original content
3. WHEN merged content exceeds relevance threshold THEN the Browser_Monitor SHALL proceed with alert generation
4. IF Tavily returns no results THEN the Browser_Monitor SHALL skip the source for current cycle

### Requirement 6: Telegram Monitor Integration

**User Story:** As a Telegram intel analyst, I want to verify intel from medium-trust channels with Tavily, so that I can filter out false rumors.

#### Acceptance Criteria

1. WHEN Telegram_Monitor receives intel from channels with trust score between 0.4 and 0.7 THEN the Telegram_Monitor SHALL call Tavily for verification
2. WHEN Tavily confirms the intel THEN the Telegram_Monitor SHALL boost trust score by 0.2
3. WHEN Tavily contradicts the intel THEN the Telegram_Monitor SHALL reduce trust score by 0.1 and add warning flag
4. IF Tavily returns inconclusive results THEN the Telegram_Monitor SHALL maintain original trust score

### Requirement 7: Settlement and CLV Integration

**User Story:** As a performance analyst, I want Tavily to enrich post-match analysis, so that I can understand why bets won or lost.

#### Acceptance Criteria

1. WHEN Settler processes a completed match THEN the Settler SHALL call Tavily to search for post-match reports
2. WHEN post-match intel is found THEN the Settler SHALL store key factors in settlement reason field
3. WHEN CLV analysis runs THEN the CLV_Tracker SHALL use Tavily to verify line movement causes
4. WHEN settlement report is generated THEN the Settler SHALL include Tavily-sourced insights

### Requirement 8: Twitter Intel Recovery

**User Story:** As a Twitter intel operator, I want Tavily as fallback when Nitter fails, so that I can maintain Twitter coverage.

#### Acceptance Criteria

1. WHEN Twitter_Intel_Cache fails to retrieve tweets via Nitter THEN the Twitter_Intel_Cache SHALL call Tavily with Twitter-specific query
2. WHEN Tavily returns Twitter-related results THEN the Twitter_Intel_Cache SHALL parse and normalize to tweet format
3. WHEN recovered tweets are older than 24 hours THEN the Twitter_Intel_Cache SHALL apply freshness decay penalty
4. IF Tavily returns no Twitter results THEN the Twitter_Intel_Cache SHALL mark account as temporarily unavailable

### Requirement 9: Budget Management

**User Story:** As a system administrator, I want automatic budget tracking and allocation, so that I never exceed the monthly API quota.

#### Acceptance Criteria

1. WHEN a Tavily call is made THEN the Budget_Manager SHALL increment the counter for the current API key and log usage
2. WHEN the current key's usage reaches 1000 calls THEN the Budget_Manager SHALL trigger key rotation to the next available key
3. WHEN total usage across all keys reaches 6650 (95%) THEN the Budget_Manager SHALL disable non-essential Tavily calls
4. WHEN a new month starts THEN the Budget_Manager SHALL reset all counters and restore all keys to available status

### Requirement 10: Fallback and Resilience

**User Story:** As a system operator, I want graceful degradation when Tavily is unavailable, so that the system continues functioning.

#### Acceptance Criteria

1. WHEN Tavily API returns 429 (rate limit) THEN the Tavily_Provider SHALL wait and retry with exponential backoff
2. WHEN Tavily is unavailable for more than 5 minutes THEN the Tavily_Provider SHALL switch to Brave/DDG fallback
3. WHEN fallback is active THEN the Tavily_Provider SHALL attempt Tavily recovery every 60 seconds
4. IF all search providers fail THEN the system SHALL continue with cached data and log degraded status
