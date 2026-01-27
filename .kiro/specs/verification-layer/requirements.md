# Requirements Document

## Introduction

Il Verification Layer è un componente di validazione che agisce come filtro qualità tra gli alert preliminari generati dal sistema EarlyBird e la decisione finale di invio. Il suo scopo è verificare i dati con fonti esterne (Tavily/Perplexity) per colmare le lacune di FotMob e validare la logica delle scommesse suggerite.

Il problema principale che risolve è il "gap logico" identificato: il sistema attuale può suggerire Over 2.5 Goals per una squadra con 7 assenti CRITICAL, senza considerare che una rosa decimata tipicamente produce meno gol. Il Verification Layer verifica l'impatto reale dei giocatori assenti e suggerisce mercati alternativi quando appropriato.

## Glossary

- **Verification_Layer**: Componente che valida gli alert preliminari con dati esterni prima dell'invio
- **Alert_Preliminare**: Segnale generato dal sistema con score >= soglia, candidato per verifica
- **Player_Impact_Score**: Punteggio 1-10 che indica l'importanza di un giocatore nella rosa
- **Verification_Result**: Esito della verifica: CONFIRM, REJECT, o CHANGE_MARKET
- **H2H_Stats**: Statistiche degli scontri diretti tra le due squadre
- **Form_Stats**: Statistiche delle ultime 5 partite di una squadra
- **Tavily_Provider**: Servizio di ricerca web per ottenere dati aggiornati
- **Confidence_Level**: Livello di affidabilità dei dati ottenuti (HIGH, MEDIUM, LOW)

## Requirements

### Requirement 1

**User Story:** As a betting analyst, I want the system to verify player importance before confirming alerts, so that I can trust the injury impact assessment.

#### Acceptance Criteria

1. WHEN the Verification_Layer receives a list of missing players THEN the system SHALL query external sources to obtain a Player_Impact_Score (1-10) for each player
2. WHEN a player has Player_Impact_Score >= 7 THEN the system SHALL classify that player as "key_player" in the verification result
3. WHEN the total impact of missing key_players exceeds 20 points AND the suggested market is Over goals THEN the system SHALL flag the alert for market reconsideration
4. WHEN external sources return no data for a player THEN the system SHALL assign a default Player_Impact_Score of 5 (neutral)

### Requirement 2

**User Story:** As a betting analyst, I want the system to fetch recent form statistics, so that I can validate if historical averages still apply.

#### Acceptance Criteria

1. WHEN the Verification_Layer processes an alert THEN the system SHALL query the last 5 matches for both teams including goals scored and conceded
2. WHEN a team's last 5 matches show significantly different scoring pattern than season average (>30% deviation) THEN the system SHALL include a form_warning in the result
3. WHEN Form_Stats show both teams scoring below 1.0 goals per game in last 5 THEN the system SHALL recommend Under market instead of Over
4. WHEN Form_Stats are unavailable THEN the system SHALL set form_confidence to LOW and proceed with existing data

### Requirement 3

**User Story:** As a betting analyst, I want the system to verify H2H statistics, so that I can identify patterns specific to this matchup.

#### Acceptance Criteria

1. WHEN the Verification_Layer processes an alert THEN the system SHALL query the last 5 head-to-head matches between the teams
2. WHEN H2H_Stats show average goals per match THEN the system SHALL compare this with the suggested Over/Under line
3. WHEN H2H_Stats show average cards per match >= 4.5 THEN the system SHALL flag Over Cards as a potential market
4. WHEN H2H_Stats show average corners per match >= 10 THEN the system SHALL flag Over Corners as a potential market
5. WHEN H2H data is unavailable or teams have never met THEN the system SHALL skip H2H validation and note this in the result

### Requirement 4

**User Story:** As a betting analyst, I want the system to verify referee statistics, so that I can make informed decisions about cards markets.

#### Acceptance Criteria

1. WHEN the Verification_Layer processes an alert THEN the system SHALL attempt to identify the match referee and obtain cards-per-game average
2. WHEN referee cards average >= 5.0 THEN the system SHALL classify referee as "strict" and boost Over Cards confidence
3. WHEN referee cards average <= 3.0 THEN the system SHALL classify referee as "lenient" and veto Over Cards suggestions
4. WHEN referee data is unavailable THEN the system SHALL set referee_confidence to LOW and not suggest cards markets

### Requirement 5

**User Story:** As a betting analyst, I want the system to verify corner statistics, so that I can identify corner betting opportunities.

#### Acceptance Criteria

1. WHEN the Verification_Layer processes an alert THEN the system SHALL query corner averages for both teams this season
2. WHEN combined corner average >= 10.5 THEN the system SHALL flag Over 9.5 Corners as a potential market
3. WHEN H2H corner average is available AND differs significantly from season average THEN the system SHALL prefer H2H corner data
4. WHEN corner data is unavailable THEN the system SHALL not suggest corner markets

### Requirement 6

**User Story:** As a betting analyst, I want the system to produce a final verification decision, so that alerts are either confirmed, rejected, or modified.

#### Acceptance Criteria

1. WHEN all verification checks complete THEN the system SHALL produce a Verification_Result with status CONFIRM, REJECT, or CHANGE_MARKET
2. WHEN verification finds the suggested market is logically inconsistent with verified data THEN the system SHALL set status to CHANGE_MARKET and provide alternative
3. WHEN verification confidence is LOW across multiple data points THEN the system SHALL set status to REJECT with reason "insufficient_data"
4. WHEN verification confirms the original analysis THEN the system SHALL set status to CONFIRM and optionally adjust the score based on verified data
5. WHEN the system produces a Verification_Result THEN the result SHALL include a human-readable reasoning in Italian explaining the decision

### Requirement 7

**User Story:** As a system operator, I want the Verification Layer to be cost-efficient, so that API costs remain manageable.

#### Acceptance Criteria

1. WHEN an alert has score below 7.5 THEN the system SHALL skip verification and proceed with standard flow
2. WHEN the Verification_Layer makes an API call THEN the system SHALL log the call for cost tracking
3. WHEN Tavily API fails THEN the system SHALL fallback to Perplexity provider if available
4. WHEN both providers fail THEN the system SHALL proceed with CONFIRM status and LOW confidence flag

### Requirement 8

**User Story:** As a betting analyst, I want the system to detect logical inconsistencies, so that obviously wrong suggestions are caught.

#### Acceptance Criteria

1. WHEN a team has injury severity CRITICAL (>= 15 impact points) AND suggested market is Over 2.5 Goals THEN the system SHALL apply a penalty to the Over confidence
2. WHEN both teams have injury severity CRITICAL THEN the system SHALL consider Under market as primary alternative
3. WHEN verified form shows a team on a losing streak (0 wins in last 5) AND system suggests betting on that team THEN the system SHALL flag this inconsistency
4. WHEN the system detects a logical inconsistency THEN the system SHALL include the inconsistency type in the Verification_Result
