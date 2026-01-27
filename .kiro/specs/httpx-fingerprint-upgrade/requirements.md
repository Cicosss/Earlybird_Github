# Requirements Document

## Introduction

Questo documento definisce i requisiti per l'upgrade del layer HTTP di EarlyBird, migrando da `requests` sincrono a `httpx` async con connection pooling, e implementando un sistema avanzato di fingerprinting browser per evitare rate limiting e ban da parte dei motori di ricerca (DDG, Brave, Serper).

L'obiettivo è migliorare:
1. **Performance**: 3-5x speedup tramite connection pooling e HTTP/2
2. **Resilienza**: Riduzione dei 429 errors tramite fingerprint rotation sofisticata
3. **Manutenibilità**: Centralizzazione della logica HTTP in un unico modulo riutilizzabile

## Glossary

- **HTTPX**: Libreria Python async/sync per HTTP con supporto HTTP/2 e connection pooling
- **Connection Pooling**: Riutilizzo delle connessioni TCP tra richieste successive
- **Fingerprint**: Combinazione di User-Agent + headers che identifica un browser
- **Rate Limiting**: Blocco temporaneo da parte di un servizio dopo troppe richieste
- **Jitter**: Delay randomico tra richieste per evitare pattern detection
- **SearchProvider**: Modulo EarlyBird che orchestra Brave → DDG → Serper
- **BraveProvider**: Modulo EarlyBird per Brave Search API
- **RSSHubProvider**: Modulo EarlyBird per RSS feed aggregation

## Requirements

### Requirement 1: HTTP Client Centralizzato

**User Story:** As a developer, I want a centralized HTTP client module, so that all network requests use consistent configuration, retry logic, and fingerprinting.

#### Acceptance Criteria

1. WHEN the system initializes THEN the HTTP_Client module SHALL create a singleton HTTPX AsyncClient with connection pooling (max 10 connections, 5 keepalive)
2. WHEN a component makes an HTTP request THEN the HTTP_Client SHALL apply rate limiting with configurable jitter (default 3-6 seconds for search engines)
3. WHEN a request fails with status 429 or 503 THEN the HTTP_Client SHALL retry with exponential backoff (2^attempt seconds, max 3 retries)
4. WHEN a request times out THEN the HTTP_Client SHALL retry with exponential backoff before failing
5. WHEN the HTTP_Client is used THEN the HTTP_Client SHALL support both sync and async interfaces for backward compatibility

### Requirement 2: Browser Fingerprint Rotation

**User Story:** As a system operator, I want sophisticated browser fingerprinting, so that search engines cannot detect automated requests and block the system.

#### Acceptance Criteria

1. WHEN the fingerprint module initializes THEN the Fingerprint_Manager SHALL load at least 5 distinct browser profiles (Chrome, Firefox, Safari, Edge)
2. WHEN a request is made THEN the Fingerprint_Manager SHALL provide a complete set of correlated headers (User-Agent, Accept-Language, Sec-Fetch-*, DNT)
3. WHEN the request count exceeds a random threshold (8-25 requests) THEN the Fingerprint_Manager SHALL rotate to a different browser profile
4. WHEN a 403 or 429 error occurs THEN the Fingerprint_Manager SHALL immediately rotate to a new profile
5. WHEN headers are generated THEN the Fingerprint_Manager SHALL ensure User-Agent and Sec-Fetch headers are internally consistent (Chrome UA with Chrome Sec-Fetch values)

### Requirement 3: SearchProvider Migration

**User Story:** As a developer, I want the SearchProvider to use the new HTTP client, so that search requests benefit from connection pooling and fingerprinting.

#### Acceptance Criteria

1. WHEN SearchProvider makes a request to DuckDuckGo THEN the SearchProvider SHALL use the centralized HTTP_Client with fingerprint rotation
2. WHEN SearchProvider makes a request to Serper API THEN the SearchProvider SHALL use the centralized HTTP_Client (fingerprinting optional for API calls)
3. WHEN SearchProvider falls back between engines THEN the SearchProvider SHALL maintain the same HTTP session for connection reuse
4. WHEN the existing jitter logic (3-6s) is applied THEN the SearchProvider SHALL delegate to HTTP_Client's rate limiting instead of local sleep()

### Requirement 4: BraveProvider Migration

**User Story:** As a developer, I want the BraveProvider to use the new HTTP client, so that Brave API requests benefit from connection pooling and proper retry logic.

#### Acceptance Criteria

1. WHEN BraveProvider makes a request THEN the BraveProvider SHALL use the centralized HTTP_Client
2. WHEN BraveProvider enforces rate limiting (1.1s) THEN the BraveProvider SHALL use HTTP_Client's rate limiting with custom interval
3. WHEN Brave API returns 429 THEN the BraveProvider SHALL use HTTP_Client's retry logic before marking as rate limited

### Requirement 5: RSSHubProvider Migration

**User Story:** As a developer, I want the RSSHubProvider to use the new HTTP client, so that RSS feed fetching benefits from connection pooling.

#### Acceptance Criteria

1. WHEN RSSHubProvider fetches a feed THEN the RSSHubProvider SHALL use the centralized HTTP_Client
2. WHEN RSSHubProvider checks service availability THEN the RSSHubProvider SHALL use HTTP_Client with short timeout (5s)
3. WHEN multiple domains are fetched sequentially THEN the RSSHubProvider SHALL reuse the same HTTP session

### Requirement 6: Backward Compatibility

**User Story:** As a system operator, I want the upgrade to be backward compatible, so that existing functionality continues to work without breaking changes.

#### Acceptance Criteria

1. WHEN the HTTP_Client is imported THEN the HTTP_Client SHALL provide a sync wrapper for components that cannot use async
2. WHEN existing provider interfaces are called THEN the existing provider interfaces SHALL maintain the same return types and signatures
3. WHEN the system starts THEN the system SHALL gracefully fall back to requests library if HTTPX is not installed
4. WHEN tests are run THEN all existing tests SHALL pass without modification

### Requirement 7: Observability

**User Story:** As a system operator, I want visibility into HTTP client performance, so that I can monitor and debug network issues.

#### Acceptance Criteria

1. WHEN a request completes THEN the HTTP_Client SHALL log the request duration, status code, and fingerprint profile used
2. WHEN a retry occurs THEN the HTTP_Client SHALL log the retry attempt number and reason
3. WHEN fingerprint rotation occurs THEN the Fingerprint_Manager SHALL log the old and new profile names
4. WHEN rate limiting is applied THEN the HTTP_Client SHALL log the delay duration
