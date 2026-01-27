# Requirements Document

## Introduction

This specification defines the upgrade of the EarlyBird sports betting intelligence system from a basic news scraper to a professional intelligence engine. The system will integrate SportMonk API for reliable player and fixture data, and Google Gemini 3.0 for advanced reasoning and analysis. The goal is to create a triangulation system that correlates official injury data, market movements, and news confirmation to generate high-confidence betting alerts.

## Glossary

- **EarlyBird System**: The sports betting alert system that monitors fixtures, odds, news, and player data
- **SportMonk API**: A professional sports data provider offering fixture details, lineups, injuries, suspensions, and squad statistics
- **Gemini 3.0**: Google's generative AI model for advanced reasoning and analysis
- **Data Provider**: The module responsible for fetching and caching data from SportMonk API
- **Analyzer**: The module that uses AI to correlate multiple data sources and generate betting recommendations
- **Triangulation**: The process of correlating three data sources (official data, market movements, news) to validate betting opportunities
- **Importance Score**: A calculated metric representing a player's value to their team based on statistics
- **Market Status**: The current state of betting odds including percentage changes from opening odds
- **Data Truth**: Confirmed information from official sources (SportMonk) about injuries, suspensions, and lineups

## Requirements

### Requirement 1

**User Story:** As a betting analyst, I want to access reliable fixture and player data from SportMonk, so that I can base my analysis on official confirmed information rather than rumors.

#### Acceptance Criteria

1. WHEN the system queries a fixture THEN the Data Provider SHALL retrieve fixture details including lineups, injuries, and suspensions from SportMonk API
2. WHEN fixture data is retrieved THEN the Data Provider SHALL parse and extract confirmed absentees before news analysis begins
3. WHEN the SportMonk API returns an error THEN the Data Provider SHALL log the error and retry with exponential backoff
4. WHEN fixture data is successfully retrieved THEN the Data Provider SHALL cache the response to minimize API calls
5. WHEN the API rate limit is approached THEN the Data Provider SHALL throttle requests to prevent quota exhaustion

### Requirement 2

**User Story:** As a betting analyst, I want to calculate player importance scores based on performance statistics, so that I can quantify the impact of missing players on match outcomes.

#### Acceptance Criteria

1. WHEN the system queries a team squad THEN the Data Provider SHALL retrieve current season squad data with appearances and goals from SportMonk API
2. WHEN squad data is retrieved THEN the Data Provider SHALL calculate an Importance Score for each player using the formula: (goals × 2) + appearances
3. WHEN Importance Scores are calculated THEN the Data Provider SHALL cache the scores locally to avoid repeated API calls
4. WHEN a player name list is provided THEN the Data Provider SHALL sum the Importance Scores of matching players
5. WHEN the total Importance Score is calculated THEN the Data Provider SHALL classify the impact as High (score > 50), Medium (20-50), or Low (< 20)

### Requirement 3

**User Story:** As a betting analyst, I want to use Google Gemini 3.0 for deep reasoning, so that I can correlate multiple data sources and generate high-confidence betting recommendations.

#### Acceptance Criteria

1. WHEN the Analyzer receives news data THEN the Analyzer SHALL send a structured prompt to Gemini 3.0 including news snippet, market status, and official data
2. WHEN Gemini processes the prompt THEN the Analyzer SHALL receive a JSON response containing final verdict, confidence score, and reasoning
3. WHEN the Gemini API returns an error THEN the Analyzer SHALL log the error and fall back to keyword-based analysis
4. WHEN the confidence score is below 60 THEN the Analyzer SHALL not generate a betting alert
5. WHEN the API key is invalid THEN the Analyzer SHALL raise a configuration error with clear instructions

### Requirement 4

**User Story:** As a betting analyst, I want the system to triangulate official data, market movements, and news, so that I can identify betting opportunities with high confidence.

#### Acceptance Criteria

1. WHEN a fixture is ingested THEN the Main Pipeline SHALL query SportMonk for official injury and suspension data
2. WHEN SportMonk confirms key player absences THEN the Main Pipeline SHALL mark the fixture as High Potential
3. WHEN a fixture has High Potential OR odds drop exceeds 5% THEN the Main Pipeline SHALL search for news confirmation
4. WHEN all three data sources are collected THEN the Main Pipeline SHALL pass them to Gemini for synthesis
5. WHEN Gemini returns a BET verdict with confidence above 70 THEN the Main Pipeline SHALL send a Telegram alert with reasoning

### Requirement 5

**User Story:** As a system administrator, I want secure credential management for multiple API services, so that I can easily update keys without modifying code.

#### Acceptance Criteria

1. WHEN the system starts THEN the Configuration Module SHALL load API credentials from environment variables
2. WHEN a required credential is missing THEN the Configuration Module SHALL raise a clear error indicating which key is missing
3. WHEN credentials are loaded THEN the Configuration Module SHALL validate the format of each API key
4. WHEN the system accesses an API THEN the Configuration Module SHALL provide the appropriate credential
5. WHEN credentials are used THEN the Configuration Module SHALL never log or expose the full key values

### Requirement 6

**User Story:** As a betting analyst, I want the system to cache SportMonk data intelligently, so that I can minimize API costs while maintaining data freshness.

#### Acceptance Criteria

1. WHEN squad data is requested THEN the Data Provider SHALL check the local cache before making an API call
2. WHEN cached data is older than 24 hours THEN the Data Provider SHALL refresh the data from SportMonk API
3. WHEN fixture data is requested within 2 hours of kickoff THEN the Data Provider SHALL always fetch fresh data
4. WHEN cache storage exceeds 100MB THEN the Data Provider SHALL purge the oldest entries
5. WHEN the system restarts THEN the Data Provider SHALL load existing cache from disk

### Requirement 7

**User Story:** As a betting analyst, I want detailed reasoning for each betting recommendation, so that I can understand the correlation between data sources and make informed decisions.

#### Acceptance Criteria

1. WHEN Gemini generates a recommendation THEN the Analyzer SHALL extract the reasoning text from the response
2. WHEN a Telegram alert is sent THEN the Notifier SHALL include the full reasoning in the message
3. WHEN the reasoning exceeds 500 characters THEN the Notifier SHALL truncate with an ellipsis
4. WHEN multiple data sources conflict THEN the reasoning SHALL explicitly state the conflict
5. WHEN the verdict is NO BET THEN the reasoning SHALL explain why the opportunity was rejected

### Requirement 8

**User Story:** As a system administrator, I want comprehensive error handling and logging, so that I can diagnose issues with external API integrations.

#### Acceptance Criteria

1. WHEN an API call fails THEN the system SHALL log the error with timestamp, endpoint, and error message
2. WHEN SportMonk returns invalid data THEN the Data Provider SHALL log the raw response and skip processing
3. WHEN Gemini returns malformed JSON THEN the Analyzer SHALL log the response and fall back to keyword analysis
4. WHEN network errors occur THEN the system SHALL retry up to 3 times with exponential backoff
5. WHEN critical errors occur THEN the system SHALL send an admin alert via Telegram
