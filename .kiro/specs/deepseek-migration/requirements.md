# Requirements Document

## Introduction

Questo documento definisce i requisiti per la migrazione del sistema di intelligence da Gemini (con Google Search Grounding) a DeepSeek via OpenRouter, utilizzando Brave Search come fonte di dati web. L'obiettivo è creare un provider drop-in replacement che mantenga la stessa interfaccia di `GeminiAgentProvider` ma utilizzi DeepSeek per l'analisi AI e Brave Search per la ricerca web.

## Glossary

- **DeepSeekIntelProvider**: Nuovo provider AI che sostituisce GeminiAgentProvider
- **OpenRouter**: Gateway API che fornisce accesso a modelli AI multipli, incluso DeepSeek
- **Brave Search**: API di ricerca web utilizzata per ottenere risultati in tempo reale
- **Google Search Grounding**: Funzionalità di Gemini che permette ricerche web integrate (da sostituire)
- **Drop-in Replacement**: Componente che può sostituire un altro senza modifiche all'interfaccia
- **Rate Limiter**: Meccanismo che limita la frequenza delle chiamate API
- **Circuit Breaker**: Pattern che blocca le chiamate quando un servizio è degradato
- **CooldownManager**: Sistema esistente per gestire cooldown dopo errori 429

## Requirements

### Requirement 1

**User Story:** As a system operator, I want to use DeepSeek via OpenRouter instead of Gemini, so that I can avoid Gemini's rate limits and reduce costs.

#### Acceptance Criteria

1. WHEN the system initializes DeepSeekIntelProvider THEN the system SHALL connect to OpenRouter API using the OPENROUTER_API_KEY environment variable
2. WHEN OPENROUTER_API_KEY is not set THEN the system SHALL log a warning and disable the provider gracefully
3. WHEN the provider is disabled THEN the system SHALL return None from all methods without throwing exceptions
4. WHEN checking availability via is_available() THEN the system SHALL return True only if API key is configured and no cooldown is active

### Requirement 2

**User Story:** As a system operator, I want DeepSeekIntelProvider to have the same interface as GeminiAgentProvider, so that I can swap providers without code changes.

#### Acceptance Criteria

1. WHEN calling get_match_deep_dive() THEN the system SHALL accept the same parameters as GeminiAgentProvider (home_team, away_team, match_date, referee, missing_players)
2. WHEN calling get_betting_stats() THEN the system SHALL accept the same parameters as GeminiAgentProvider (home_team, away_team, match_date, league)
3. WHEN calling verify_news_item() THEN the system SHALL accept the same parameters as GeminiAgentProvider (news_title, news_snippet, team_name, news_source, match_context)
4. WHEN calling verify_news_batch() THEN the system SHALL accept the same parameters as GeminiAgentProvider (news_items, team_name, match_context, max_items)
5. WHEN calling confirm_biscotto() THEN the system SHALL accept the same parameters as GeminiAgentProvider (home_team, away_team, match_date, league, draw_odds, implied_prob, odds_pattern, season_context, detected_factors)
6. WHEN calling enrich_match_context() THEN the system SHALL accept the same parameters as GeminiAgentProvider (home_team, away_team, match_date, league, existing_context)
7. WHEN calling extract_twitter_intel() THEN the system SHALL accept the same parameters as GeminiAgentProvider (handles, max_posts_per_account)
8. WHEN any method returns data THEN the system SHALL return the same Dict structure as GeminiAgentProvider

### Requirement 3

**User Story:** As a system operator, I want the provider to use Brave Search for web data, so that I can get real-time information without Google Search Grounding.

#### Acceptance Criteria

1. WHEN a method requires web search THEN the system SHALL first call Brave Search API to obtain relevant results
2. WHEN Brave Search returns results THEN the system SHALL format the results as context for DeepSeek analysis
3. WHEN Brave Search returns no results THEN the system SHALL proceed with DeepSeek analysis using only the prompt context
4. WHEN Brave Search fails with an error THEN the system SHALL log the error and proceed with DeepSeek analysis without web context
5. WHEN formatting Brave results for DeepSeek THEN the system SHALL include title, URL, and snippet for each result

### Requirement 4

**User Story:** As a system operator, I want proper rate limiting, so that I don't exceed API quotas.

#### Acceptance Criteria

1. WHEN making Brave Search requests THEN the system SHALL use the existing Brave rate limiter (2s interval)
2. WHEN making OpenRouter/DeepSeek requests THEN the system SHALL enforce a minimum interval of 2 seconds between requests
3. WHEN a 429 error occurs from OpenRouter THEN the system SHALL activate CooldownManager for 24 hours
4. WHEN CooldownManager cooldown is active THEN the system SHALL return None from all methods without making API calls

### Requirement 5

**User Story:** As a system operator, I want the prompts adapted for DeepSeek, so that the AI understands it should analyze provided search results instead of searching itself.

#### Acceptance Criteria

1. WHEN building prompts for DeepSeek THEN the system SHALL remove references to "Google Search" and "search grounding"
2. WHEN building prompts for DeepSeek THEN the system SHALL include a section with Brave Search results as context
3. WHEN Brave Search results are provided THEN the system SHALL instruct DeepSeek to analyze the provided sources
4. WHEN no Brave Search results are available THEN the system SHALL instruct DeepSeek to use its training knowledge only

### Requirement 6

**User Story:** As a system operator, I want comprehensive logging, so that I can monitor the provider's behavior.

#### Acceptance Criteria

1. WHEN the provider initializes THEN the system SHALL log the initialization status with emoji prefix
2. WHEN making a Brave Search request THEN the system SHALL log the query being searched
3. WHEN making a DeepSeek request THEN the system SHALL log the operation name and key parameters
4. WHEN a request succeeds THEN the system SHALL log success with relevant metrics
5. WHEN a request fails THEN the system SHALL log the error with sufficient detail for debugging

### Requirement 7

**User Story:** As a system operator, I want the provider to handle edge cases gracefully, so that the system remains stable.

#### Acceptance Criteria

1. WHEN input parameters are None or empty THEN the system SHALL return None without making API calls
2. WHEN DeepSeek returns invalid JSON THEN the system SHALL use the existing parse_ai_json fallback parser
3. WHEN DeepSeek returns empty response THEN the system SHALL log a warning and return None
4. WHEN network timeout occurs THEN the system SHALL log the error and return None
5. WHEN any unexpected exception occurs THEN the system SHALL catch it, log it, and return None

### Requirement 8

**User Story:** As a developer, I want a singleton pattern for the provider, so that I can easily access it from anywhere in the codebase.

#### Acceptance Criteria

1. WHEN calling get_deepseek_provider() THEN the system SHALL return the same instance on subsequent calls
2. WHEN the singleton is first created THEN the system SHALL initialize the provider with environment configuration
3. WHEN importing the module THEN the system SHALL expose get_deepseek_provider() as a public function
