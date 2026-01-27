# Requirements Document

## Introduction

Questo documento definisce i requisiti per il potenziamento dell'Intelligence Layer di EarlyBird V4.3. L'obiettivo è migliorare la qualità e la tempestività delle informazioni raccolte dal sistema, passando da un approccio puramente reattivo a uno più predittivo.

Il potenziamento si concentra su 4 aree chiave identificate dal Deep Research Report:
1. **Telegram Trust Score V2** - Validazione algoritmica dei canali Telegram
2. **Beat Writer Priority System** - Database curato di fonti tier-1 per lega
3. **RLM Detector Enhancement** - Rilevamento Reverse Line Movement migliorato
4. **Dynamic News Decay** - Decadimento news adattivo basato su contesto

## Glossary

- **Trust Score**: Punteggio 0-1 che indica l'affidabilità di un canale Telegram basato su metriche oggettive
- **Timestamp Lag**: Differenza temporale tra quando un messaggio viene postato e quando le quote si muovono
- **Insider Hit**: Messaggio che ANTICIPA un movimento di quote (lag negativo)
- **Echo Chamber**: Canale che copia contenuti da altri canali senza valore aggiunto
- **Beat Writer**: Giornalista specializzato che copre una squadra/lega specifica con accesso privilegiato
- **RLM (Reverse Line Movement)**: Movimento delle quote CONTRO il flusso di scommesse pubbliche
- **Steam Move**: Movimento rapido e coordinato delle quote in finestre temporali brevi
- **News Decay**: Decadimento esponenziale dell'impatto di una notizia nel tempo
- **Half-Life (λ)**: Tempo necessario affinché l'impatto di una news si dimezzi
- **Tier 1 League**: Leghe principali con mercati efficienti (Premier League, La Liga, etc.)
- **Elite League**: Leghe monitorate da EarlyBird (Turkey, Argentina, Greece, etc.)

## Requirements

### Requirement 1: Telegram Trust Score V2

**User Story:** As a betting analyst, I want the system to automatically validate Telegram channel reliability, so that I can filter out scam channels and prioritize genuine insider information.

#### Acceptance Criteria

1. WHEN a Telegram message is received THEN the Telegram_Trust_Score_Module SHALL calculate a trust multiplier (0.0-1.0) based on timestamp lag analysis
2. WHEN a message anticipates odds movement by more than 3 minutes THEN the Telegram_Trust_Score_Module SHALL classify the message as an "insider hit" and boost the channel's trust score
3. WHEN a message follows odds movement by more than 30 minutes THEN the Telegram_Trust_Score_Module SHALL classify the message as "late" and reduce the channel's trust score
4. WHEN a channel's trust score falls below 0.20 THEN the Telegram_Trust_Score_Module SHALL automatically blacklist the channel
5. WHEN a message contains duplicate content from another channel within 2 minutes THEN the Telegram_Trust_Score_Module SHALL flag the message as "echo" and apply a 0.1 trust multiplier
6. WHEN channel metrics are updated THEN the Telegram_Trust_Score_Module SHALL persist the metrics to the database for historical tracking
7. WHEN calculating the final trust score THEN the Telegram_Trust_Score_Module SHALL weight timestamp lag (40%), edit ratio (25%), accuracy (25%), and red flags (10%)

### Requirement 2: Beat Writer Priority System

**User Story:** As a news hunter, I want to prioritize information from verified beat writers, so that I can catch breaking news before mainstream media.

#### Acceptance Criteria

1. WHEN searching for team news THEN the News_Hunter_Module SHALL query beat writer Twitter handles before generic searches
2. WHEN a beat writer result is found THEN the News_Hunter_Module SHALL assign a "HIGH" confidence level and a priority boost of 1.5x
3. WHEN configuring beat writers THEN the Sources_Config_Module SHALL store handles organized by league with metadata (name, outlet, specialty)
4. WHEN a beat writer breaks news THEN the News_Hunter_Module SHALL log the source attribution for accuracy tracking
5. WHEN no beat writer results are found THEN the News_Hunter_Module SHALL fall back to standard search without delay

### Requirement 3: RLM Detector Enhancement

**User Story:** As a market analyst, I want to detect Reverse Line Movement patterns more accurately, so that I can identify sharp money action before the market corrects.

#### Acceptance Criteria

1. WHEN odds move against public betting by more than 3% THEN the Market_Intelligence_Module SHALL generate an RLM signal with confidence level
2. WHEN public betting exceeds 65% on one side AND odds for that side increase THEN the Market_Intelligence_Module SHALL classify this as a confirmed RLM pattern
3. WHEN an RLM signal is detected THEN the Market_Intelligence_Module SHALL include the sharp side recommendation in the analysis output
4. WHEN historical odds data is insufficient (less than 2 snapshots) THEN the Market_Intelligence_Module SHALL skip RLM detection and log the reason
5. WHEN RLM confidence is HIGH (odds movement greater than 5%) THEN the Market_Intelligence_Module SHALL flag the match as "high potential" for AI analysis

### Requirement 4: Dynamic News Decay

**User Story:** As an AI analyst, I want news impact to decay based on league tier and match proximity, so that stale information doesn't pollute my analysis.

#### Acceptance Criteria

1. WHEN calculating news decay for Elite leagues THEN the News_Decay_Module SHALL use a slower decay rate (λ=0.023, half-life ~30 min)
2. WHEN calculating news decay for Tier 1 leagues THEN the News_Decay_Module SHALL use a faster decay rate (λ=0.14, half-life ~5 min)
3. WHEN match kickoff is within 30 minutes THEN the News_Decay_Module SHALL accelerate decay by 2x to filter stale pre-match noise
4. WHEN news is from a verified insider source THEN the News_Decay_Module SHALL apply a 0.5x decay rate (news persists longer)
5. WHEN news age exceeds 24 hours THEN the News_Decay_Module SHALL cap the residual impact at 1% regardless of source
6. WHEN applying decay THEN the News_Decay_Module SHALL tag each news item with freshness indicator (🔥 FRESH, ⏰ AGING, 📜 STALE)

### Requirement 5: Integration and Orchestration

**User Story:** As a system operator, I want all intelligence enhancements to work together seamlessly, so that the overall analysis quality improves without breaking existing functionality.

#### Acceptance Criteria

1. WHEN the main pipeline runs THEN the Orchestrator SHALL call all intelligence modules in the correct order (Trust Score → Beat Writers → RLM → News Decay)
2. WHEN a module fails THEN the Orchestrator SHALL log the error and continue with remaining modules (graceful degradation)
3. WHEN generating the AI dossier THEN the Orchestrator SHALL include trust scores, source attribution, RLM signals, and freshness tags
4. WHEN an alert is sent THEN the Orchestrator SHALL include the primary intelligence driver (INSIDER_INTEL, SHARP_MONEY, etc.)
5. WHEN the system starts THEN the Orchestrator SHALL initialize all required database tables (telegram_channels, odds_snapshots)
