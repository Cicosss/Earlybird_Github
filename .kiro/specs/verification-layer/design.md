# Design Document: Verification Layer

## Overview

Il Verification Layer è un componente di validazione che agisce come "fact-checker" tra gli alert preliminari e la decisione finale di invio. Utilizza Tavily (con fallback su Perplexity) per ottenere dati aggiornati e verificare la logica delle scommesse suggerite.

**Problema risolto**: Il sistema attuale può suggerire Over 2.5 Goals per una squadra con 7 assenti CRITICAL senza considerare che una rosa decimata tipicamente produce meno gol. Il Verification Layer colma questo gap verificando l'impatto reale dei giocatori e suggerendo mercati alternativi.

**Flusso**:
```
Alert Preliminare (score >= 7.5)
         │
         ▼
┌─────────────────────┐
│  VERIFICATION LAYER │
├─────────────────────┤
│ 1. Query Tavily     │
│ 2. Parse Response   │
│ 3. Validate Logic   │
│ 4. Decide           │
└─────────────────────┘
         │
         ▼
   CONFIRM / REJECT / CHANGE_MARKET
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         MAIN.PY                                   │
│  (Existing alert flow)                                           │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ score >= 7.5
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    VERIFICATION LAYER                             │
│  src/analysis/verification_layer.py                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │ VerificationReq │───▶│ TavilyVerifier  │                      │
│  │ (Input DTO)     │    │ (API Client)    │                      │
│  └─────────────────┘    └────────┬────────┘                      │
│                                  │                                │
│                                  │ fallback                       │
│                                  ▼                                │
│                         ┌─────────────────┐                      │
│                         │PerplexityFallback│                     │
│                         └────────┬────────┘                      │
│                                  │                                │
│                                  ▼                                │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │VerifiedData     │◀───│ ResponseParser  │                      │
│  │(Parsed Stats)   │    │ (JSON Extractor)│                      │
│  └────────┬────────┘    └─────────────────┘                      │
│           │                                                       │
│           ▼                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │ LogicValidator  │───▶│VerificationResult│                     │
│  │ (Inconsistency  │    │ (Output DTO)    │                      │
│  │  Detection)     │    └─────────────────┘                      │
│  └─────────────────┘                                             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. VerificationRequest (Input DTO)

```python
@dataclass
class VerificationRequest:
    """Input per il Verification Layer."""
    match_id: str
    home_team: str
    away_team: str
    match_date: str  # YYYY-MM-DD
    league: str
    
    # Alert preliminare
    preliminary_score: float
    suggested_market: str  # "Over 2.5 Goals", "1", "X2", etc.
    
    # Dati infortuni da FotMob
    home_missing_players: List[str]
    away_missing_players: List[str]
    home_injury_severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    away_injury_severity: str
    home_injury_impact: float  # Total impact score
    away_injury_impact: float
    
    # Dati esistenti (opzionali, per confronto)
    fotmob_home_goals_avg: Optional[float] = None
    fotmob_away_goals_avg: Optional[float] = None
    fotmob_referee_name: Optional[str] = None
```

### 2. VerifiedData (Parsed Stats)

```python
@dataclass
class PlayerImpact:
    """Impatto di un singolo giocatore."""
    name: str
    impact_score: int  # 1-10
    is_key_player: bool  # True if score >= 7
    role: Optional[str] = None  # "starter", "rotation", "backup"

@dataclass
class FormStats:
    """Statistiche ultime 5 partite."""
    goals_scored: int
    goals_conceded: int
    wins: int
    draws: int
    losses: int
    avg_goals_scored: float
    avg_goals_conceded: float

@dataclass
class H2HStats:
    """Statistiche scontri diretti."""
    matches_analyzed: int
    avg_goals: float
    avg_cards: float
    avg_corners: float
    home_wins: int
    away_wins: int
    draws: int

@dataclass
class RefereeStats:
    """Statistiche arbitro."""
    name: str
    cards_per_game: float
    strictness: str  # "strict", "average", "lenient"

@dataclass
class VerifiedData:
    """Dati verificati da fonti esterne."""
    # Player impacts
    home_player_impacts: List[PlayerImpact]
    away_player_impacts: List[PlayerImpact]
    home_total_impact: float
    away_total_impact: float
    
    # Form
    home_form: Optional[FormStats]
    away_form: Optional[FormStats]
    form_confidence: str  # "HIGH", "MEDIUM", "LOW"
    
    # H2H
    h2h: Optional[H2HStats]
    h2h_confidence: str
    
    # Referee
    referee: Optional[RefereeStats]
    referee_confidence: str
    
    # Corners
    home_corner_avg: Optional[float]
    away_corner_avg: Optional[float]
    h2h_corner_avg: Optional[float]
    corner_confidence: str
    
    # Overall
    data_confidence: str  # Aggregated confidence
    source: str  # "tavily" or "perplexity"
```

### 3. VerificationResult (Output DTO)

```python
class VerificationStatus(Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    CHANGE_MARKET = "change_market"

@dataclass
class VerificationResult:
    """Risultato della verifica."""
    status: VerificationStatus
    
    # Score adjustment
    original_score: float
    adjusted_score: float
    score_adjustment_reason: Optional[str]
    
    # Market recommendation
    original_market: str
    recommended_market: Optional[str]  # Set if status == CHANGE_MARKET
    alternative_markets: List[str]  # Other viable markets
    
    # Inconsistencies detected
    inconsistencies: List[str]
    
    # Confidence
    overall_confidence: str  # "HIGH", "MEDIUM", "LOW"
    
    # Human-readable reasoning (in Italian)
    reasoning: str
    
    # Raw verified data for logging
    verified_data: VerifiedData
    
    # Rejection reason (if status == REJECT)
    rejection_reason: Optional[str]
```

### 4. TavilyVerifier (API Client)

```python
class TavilyVerifier:
    """Client per query Tavily strutturate."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"
    
    def build_verification_query(self, request: VerificationRequest) -> str:
        """
        Costruisce la query Tavily strutturata.
        
        Esempio output:
        "Panetolikos vs PAOK 2026-01-10 Greece Super League:
         - Player importance ratings for: [Giocatore1, Giocatore2, ...]
         - Last 5 matches goals scored/conceded for both teams
         - Head to head last 5 matches: goals, cards, corners
         - Referee cards per game average
         - Team corner averages this season"
        """
        pass
    
    def query(self, request: VerificationRequest) -> Optional[Dict]:
        """Esegue la query Tavily e ritorna la risposta raw."""
        pass
    
    def parse_response(self, response: Dict, request: VerificationRequest) -> VerifiedData:
        """Parsa la risposta Tavily in VerifiedData strutturato."""
        pass
```

### 5. LogicValidator

```python
class LogicValidator:
    """Valida la logica dell'alert con i dati verificati."""
    
    def validate(
        self, 
        request: VerificationRequest, 
        verified: VerifiedData
    ) -> VerificationResult:
        """
        Esegue tutte le validazioni e produce il risultato finale.
        
        Checks:
        1. Injury impact vs suggested market
        2. Form consistency
        3. H2H alignment
        4. Referee suitability for cards market
        5. Corner data for corner market
        """
        pass
    
    def _check_injury_market_consistency(
        self, 
        request: VerificationRequest, 
        verified: VerifiedData
    ) -> List[str]:
        """
        Verifica se il mercato suggerito è coerente con gli infortuni.
        
        Regola chiave: Se squadra ha CRITICAL injury impact E mercato è Over,
        applica penalità e suggerisci alternativa.
        """
        pass
    
    def _check_form_consistency(
        self,
        request: VerificationRequest,
        verified: VerifiedData
    ) -> List[str]:
        """Verifica coerenza tra forma recente e scommessa."""
        pass
    
    def _suggest_alternative_markets(
        self,
        request: VerificationRequest,
        verified: VerifiedData
    ) -> List[str]:
        """Suggerisce mercati alternativi basati sui dati verificati."""
        pass
```

## Data Models

### Database (Opzionale - per tracking)

```python
class VerificationLog(Base):
    """Log delle verifiche per analisi costi e performance."""
    __tablename__ = 'verification_logs'
    
    id = Column(Integer, primary_key=True)
    match_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Request
    preliminary_score = Column(Float)
    suggested_market = Column(String)
    
    # Result
    status = Column(String)  # confirm, reject, change_market
    adjusted_score = Column(Float)
    recommended_market = Column(String, nullable=True)
    
    # Provider
    provider_used = Column(String)  # tavily, perplexity
    api_latency_ms = Column(Integer)
    
    # Confidence
    overall_confidence = Column(String)
```

### Configuration

```python
# config/settings.py additions

# Verification Layer
VERIFICATION_ENABLED = True
VERIFICATION_SCORE_THRESHOLD = 7.5  # Minimum score to trigger verification
VERIFICATION_TIMEOUT = 30  # Seconds

# Tavily
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_SEARCH_DEPTH = "advanced"  # "basic" or "advanced"

# Thresholds
PLAYER_KEY_IMPACT_THRESHOLD = 7  # Score >= 7 = key player
CRITICAL_IMPACT_THRESHOLD = 20  # Total impact >= 20 = critical
FORM_DEVIATION_THRESHOLD = 0.30  # 30% deviation = warning
H2H_CARDS_THRESHOLD = 4.5  # Avg cards >= 4.5 = suggest Over Cards
H2H_CORNERS_THRESHOLD = 10  # Avg corners >= 10 = suggest Over Corners
REFEREE_STRICT_THRESHOLD = 5.0  # Cards/game >= 5 = strict
REFEREE_LENIENT_THRESHOLD = 3.0  # Cards/game <= 3 = lenient
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Key player classification threshold
*For any* player with impact_score >= 7, that player SHALL be classified as is_key_player = True in the verification result.
**Validates: Requirements 1.2**

### Property 2: Market reconsideration flag
*For any* verification where total key_player impact > 20 AND suggested market contains "Over", the result SHALL include a market reconsideration flag or CHANGE_MARKET status.
**Validates: Requirements 1.3, 8.1**

### Property 3: Form deviation warning
*For any* team where |last5_avg - season_avg| / season_avg > 0.30, the verification result SHALL include a form_warning.
**Validates: Requirements 2.2**

### Property 4: Under market recommendation on low scoring
*For any* verification where both teams have last5_goals_avg < 1.0 AND original market is Over, the recommended_market SHALL be Under or alternative_markets SHALL include Under.
**Validates: Requirements 2.3**

### Property 5: H2H cards market flag
*For any* H2H stats with avg_cards >= 4.5, the alternative_markets SHALL include "Over Cards" variant.
**Validates: Requirements 3.3**

### Property 6: H2H corners market flag
*For any* H2H stats with avg_corners >= 10, the alternative_markets SHALL include "Over Corners" variant.
**Validates: Requirements 3.4**

### Property 7: Referee strict classification
*For any* referee with cards_per_game >= 5.0, the referee SHALL be classified as strictness = "strict".
**Validates: Requirements 4.2**

### Property 8: Referee lenient veto
*For any* referee with cards_per_game <= 3.0 AND suggested market contains "Cards", the result SHALL NOT recommend Over Cards.
**Validates: Requirements 4.3**

### Property 9: Combined corners threshold
*For any* verification where home_corner_avg + away_corner_avg >= 10.5, the alternative_markets SHALL include "Over 9.5 Corners".
**Validates: Requirements 5.2**

### Property 10: Verification result status validity
*For any* completed verification, the status SHALL be exactly one of: CONFIRM, REJECT, or CHANGE_MARKET.
**Validates: Requirements 6.1**

### Property 11: Reasoning presence
*For any* VerificationResult, the reasoning field SHALL be non-empty and contain Italian text.
**Validates: Requirements 6.5**

### Property 12: Score threshold gating
*For any* alert with preliminary_score < 7.5, the verification layer SHALL NOT be invoked (skip verification).
**Validates: Requirements 7.1**

### Property 13: Provider fallback
*For any* Tavily API failure, the system SHALL attempt Perplexity fallback before returning error.
**Validates: Requirements 7.3**

### Property 14: Critical injury Over penalty
*For any* team with injury_severity = "CRITICAL" AND suggested market = "Over 2.5 Goals", the adjusted_score SHALL be less than original_score.
**Validates: Requirements 8.1**

### Property 15: Double critical Under suggestion
*For any* verification where both teams have injury_severity = "CRITICAL", the alternative_markets SHALL include Under variant.
**Validates: Requirements 8.2**

## Error Handling

### API Failures

```python
class VerificationError(Exception):
    """Base exception for verification errors."""
    pass

class TavilyAPIError(VerificationError):
    """Tavily API call failed."""
    pass

class PerplexityAPIError(VerificationError):
    """Perplexity fallback also failed."""
    pass

class InsufficientDataError(VerificationError):
    """Not enough data to make verification decision."""
    pass
```

### Fallback Strategy

1. **Tavily fails** → Try Perplexity
2. **Perplexity fails** → Return CONFIRM with LOW confidence
3. **Parse error** → Log error, return CONFIRM with LOW confidence
4. **Timeout** → Return CONFIRM with LOW confidence

### Logging

```python
# All API calls logged for cost tracking
logger.info(f"🔍 [VERIFICATION] Tavily query for {match_id}")
logger.info(f"🔍 [VERIFICATION] Latency: {latency_ms}ms, Provider: {provider}")
logger.info(f"🔍 [VERIFICATION] Result: {status}, Confidence: {confidence}")
```

## Testing Strategy

### Unit Tests

1. **VerificationRequest validation** - Test DTO construction with various inputs
2. **Query builder** - Test Tavily query construction
3. **Response parser** - Test parsing of various Tavily response formats
4. **Logic validator** - Test each validation rule independently
5. **Result builder** - Test VerificationResult construction

### Property-Based Tests (using Hypothesis)

Property-based tests will use the `hypothesis` library to generate random inputs and verify that properties hold across all valid inputs.

Each property test will be annotated with:
```python
# **Feature: verification-layer, Property {N}: {property_text}**
# **Validates: Requirements X.Y**
```

### Integration Tests

1. **Full flow with mocked Tavily** - Test complete verification flow
2. **Fallback to Perplexity** - Test fallback mechanism
3. **main.py integration** - Test integration with existing alert flow

### Test Data

```python
# Fixtures for common scenarios
DECIMATED_TEAM_FIXTURE = {
    "home_missing_players": ["Player1", "Player2", "Player3", "Player4", "Player5", "Player6", "Player7"],
    "home_injury_severity": "CRITICAL",
    "home_injury_impact": 25.0,
    "suggested_market": "Over 2.5 Goals"
}

STRICT_REFEREE_FIXTURE = {
    "referee_name": "Test Referee",
    "referee_cards_avg": 5.5,
    "expected_strictness": "strict"
}
```
