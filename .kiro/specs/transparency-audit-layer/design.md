# Design Document: Transparency Audit Layer

## Overview

Il Transparency Audit Layer è un refactoring del sistema EarlyBird per garantire che tutti i dati raccolti durante l'analisi di una partita siano:
1. **Persistiti** in una struttura JSON nel database
2. **Visibili** negli alert Telegram in modo organizzato
3. **Auditabili** da un futuro Controller che verificherà le decisioni di DeepSeek

Il design si basa su tre principi:
- **Minimo impatto**: riutilizzare le dataclass esistenti (FormStats, H2HStats, RefereeStats, PlayerImpact)
- **Retrocompatibilità**: aggiungere colonne senza modificare quelle esistenti
- **Incrementalità**: i nuovi campi possono essere null senza causare errori

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MAIN.PY (Orchestrator)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   FotMob    │    │  Analyzer   │    │ Verification│    │   Notifier  │  │
│  │  Provider   │    │  (DeepSeek) │    │    Layer    │    │  (Telegram) │  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘  │
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        MATCH_CONTEXT (New)                           │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │ injuries │ │   form   │ │   h2h    │ │ referee  │ │standings │   │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                             │  │
│  │  │ fatigue  │ │twitter_  │ │ ai_audit │                             │  │
│  │  │          │ │  intel   │ │          │                             │  │
│  │  └──────────┘ └──────────┘ └──────────┘                             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         DATABASE (NewsLog)                           │  │
│  │                    + match_context_json (TEXT)                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. MatchContext (Nuovo Dataclass)

Nuova dataclass in `src/models/match_context.py` che aggrega tutti i dati contestuali:

```python
@dataclass
class MatchContext:
    """Aggregatore di tutti i dati contestuali per una partita."""
    
    # Injuries (from Injury_Impact_Engine)
    injuries: Optional[InjuriesContext] = None
    
    # Form (from Verification_Layer)
    form: Optional[FormContext] = None
    
    # H2H (from Verification_Layer)
    h2h: Optional[H2HContext] = None
    
    # Referee (from Verification_Layer or FotMob)
    referee: Optional[RefereeContext] = None
    
    # Standings (from FotMob motivation)
    standings: Optional[StandingsContext] = None
    
    # Fatigue (from FotMob)
    fatigue: Optional[FatigueContext] = None
    
    # Twitter Intel (from Twitter_Intel_Cache)
    twitter_intel: Optional[TwitterIntelContext] = None
    
    # Verification Result (from Verification_Layer)
    verification_result: Optional[VerificationResultContext] = None
    
    # AI Audit (from Analyzer)
    ai_audit: Optional[AIAuditContext] = None
    
    def to_json(self) -> str:
        """Serializza in JSON per persistenza."""
        
    @classmethod
    def from_json(cls, json_str: str) -> 'MatchContext':
        """Deserializza da JSON."""
        
    def to_dict(self) -> Dict[str, Any]:
        """Converte in dict per passaggio a funzioni."""
```

### 2. Context Sub-Dataclasses

```python
@dataclass
class InjuriesContext:
    home: List[PlayerInjuryInfo]
    away: List[PlayerInjuryInfo]
    home_total_impact: float
    away_total_impact: float
    home_severity: str  # CRITICAL|HIGH|MEDIUM|LOW
    away_severity: str

@dataclass
class PlayerInjuryInfo:
    name: str
    role: str  # starter|rotation|backup
    position: str  # GK|DEF|MID|FWD
    impact_score: float
    reason: str
    is_key_player: bool = False

@dataclass
class FormContext:
    home: FormStats  # Riusa dataclass esistente
    away: FormStats
    confidence: str  # HIGH|MEDIUM|LOW

@dataclass
class H2HContext:
    matches_analyzed: int
    avg_goals: float
    avg_cards: float
    avg_corners: float
    home_wins: int
    away_wins: int
    draws: int
    confidence: str

@dataclass
class RefereeContext:
    name: str
    cards_per_game: float
    strictness: str  # strict|average|lenient|unknown
    matches_officiated: int
    confidence: str

@dataclass
class StandingsContext:
    home: TeamStanding
    away: TeamStanding

@dataclass
class TeamStanding:
    position: int
    zone: str  # title_race|european_spots|mid_table|relegation
    points: int
    goal_diff: int

@dataclass
class FatigueContext:
    home: TeamFatigue
    away: TeamFatigue

@dataclass
class TeamFatigue:
    level: str  # HIGH|MEDIUM|LOW
    days_since_last: int
    matches_last_14d: int

@dataclass
class TwitterIntelContext:
    tweets: List[TweetInfo]
    cache_age_minutes: int

@dataclass
class TweetInfo:
    handle: str
    content: str
    freshness: str  # FRESH|AGING|STALE
    topics: List[str]

@dataclass
class AIAuditContext:
    prompt_hash: str
    response_hash: str
    model_used: str
    timestamp: str  # ISO8601
    reasoning_trace: Optional[str]
    confidence: int
    original_market: Optional[str]
    final_market: Optional[str]
```

### 3. MatchContextBuilder (Nuovo)

Classe builder in `src/models/match_context.py` per costruire il MatchContext incrementalmente:

```python
class MatchContextBuilder:
    """Builder per costruire MatchContext incrementalmente."""
    
    def __init__(self):
        self._context = MatchContext()
    
    def with_injuries(self, home_impacts: List[PlayerImpact], 
                      away_impacts: List[PlayerImpact],
                      home_severity: str, away_severity: str) -> 'MatchContextBuilder':
        """Aggiunge dati infortuni dal Injury_Impact_Engine."""
        
    def with_form(self, home_form: FormStats, away_form: FormStats,
                  confidence: str) -> 'MatchContextBuilder':
        """Aggiunge dati form dal Verification_Layer."""
        
    def with_h2h(self, h2h_stats: H2HStats, confidence: str) -> 'MatchContextBuilder':
        """Aggiunge dati H2H dal Verification_Layer."""
        
    def with_referee(self, referee_stats: RefereeStats, 
                     confidence: str) -> 'MatchContextBuilder':
        """Aggiunge dati arbitro."""
        
    def with_standings(self, home_motivation: Dict, 
                       away_motivation: Dict) -> 'MatchContextBuilder':
        """Aggiunge dati classifica da FotMob motivation."""
        
    def with_fatigue(self, home_fatigue: Dict, 
                     away_fatigue: Dict) -> 'MatchContextBuilder':
        """Aggiunge dati fatica da FotMob."""
        
    def with_twitter_intel(self, tweets: List[Dict], 
                           cache_age: int) -> 'MatchContextBuilder':
        """Aggiunge Twitter Intel."""
        
    def with_ai_audit(self, prompt: str, response: str, 
                      model: str, confidence: int,
                      reasoning_trace: Optional[str] = None) -> 'MatchContextBuilder':
        """Aggiunge audit trail AI."""
        
    def with_verification_result(self, result: VerificationResult) -> 'MatchContextBuilder':
        """Aggiunge risultato verifica."""
        
    def build(self) -> MatchContext:
        """Costruisce il MatchContext finale."""
        return self._context
```

### 4. AlertFormatter (Nuovo)

Classe in `src/alerting/alert_formatter.py` per formattare il MatchContext in messaggio Telegram:

```python
class AlertFormatter:
    """Formatta MatchContext in messaggio Telegram strutturato."""
    
    MAX_MESSAGE_LENGTH = 4000
    MAX_PLAYERS_PER_TEAM = 3
    MAX_TWEETS = 2
    
    def format(self, match_context: MatchContext, 
               match_info: Dict, analysis: NewsLog) -> str:
        """Formatta l'alert completo."""
        
    def _format_injuries_section(self, injuries: InjuriesContext) -> str:
        """Formatta sezione infortuni."""
        
    def _format_form_section(self, form: FormContext) -> str:
        """Formatta sezione form."""
        
    def _format_h2h_section(self, h2h: H2HContext, market: str) -> str:
        """Formatta sezione H2H (mostra dati rilevanti per il mercato)."""
        
    def _format_referee_section(self, referee: RefereeContext, 
                                market: str) -> str:
        """Formatta sezione arbitro con warning incongruenze."""
        
    def _format_standings_section(self, standings: StandingsContext) -> str:
        """Formatta sezione classifica."""
        
    def _format_fatigue_section(self, fatigue: FatigueContext) -> str:
        """Formatta sezione fatica."""
        
    def _format_twitter_section(self, twitter: TwitterIntelContext) -> str:
        """Formatta sezione Twitter Intel."""
        
    def _format_verification_section(self, verification: VerificationResultContext) -> str:
        """Formatta sezione verifica."""
        
    def _truncate_if_needed(self, message: str, market: str) -> str:
        """Tronca messaggio se supera limite, prioritizzando sezioni rilevanti."""
```

### 5. Database Migration

Nuova colonna in `NewsLog`:

```python
# In src/database/models.py
class NewsLog(Base):
    # ... existing columns ...
    
    # NEW: Match Context JSON (V8.0 - Transparency Audit Layer)
    match_context_json = Column(Text, nullable=True)
```

Migration script in `src/database/migration.py`:

```python
def migrate_add_match_context_column():
    """Aggiunge colonna match_context_json a NewsLog."""
    # Non-destructive: ALTER TABLE ADD COLUMN IF NOT EXISTS
```

## Data Models

### Flusso Dati

```
1. FotMob Provider
   ├── home_context (injuries, motivation, fatigue)
   ├── away_context (injuries, motivation, fatigue)
   └── referee_info
         │
         ▼
2. MatchContextBuilder.with_injuries()
   MatchContextBuilder.with_standings()
   MatchContextBuilder.with_fatigue()
         │
         ▼
3. Analyzer (DeepSeek)
   ├── Riceve: 6 DATA SOURCES
   └── Restituisce: NewsLog + reasoning
         │
         ▼
4. MatchContextBuilder.with_ai_audit()
         │
         ▼
5. Verification Layer
   ├── Riceve: VerificationRequest
   └── Restituisce: VerifiedData (form, h2h, referee)
         │
         ▼
6. MatchContextBuilder.with_form()
   MatchContextBuilder.with_h2h()
   MatchContextBuilder.with_referee()
   MatchContextBuilder.with_verification_result()
         │
         ▼
7. Twitter Intel Cache
   └── tweets relevanti
         │
         ▼
8. MatchContextBuilder.with_twitter_intel()
         │
         ▼
9. MatchContextBuilder.build() → MatchContext
         │
         ▼
10. AlertFormatter.format() → Telegram Message
          │
          ▼
11. NewsLog.match_context_json = context.to_json()
          │
          ▼
12. Database.save(NewsLog)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Match_Context JSON Round-Trip

*For any* valid MatchContext object, serializing to JSON and deserializing back SHALL produce an equivalent object.

```python
# Pseudocode
for all match_context in valid_match_contexts:
    json_str = match_context.to_json()
    restored = MatchContext.from_json(json_str)
    assert match_context == restored
```

**Validates: Requirements 1.3, 2.3, 3.3, 4.3, 5.3, 11.3, 12.2**

### Property 2: Player Impact Display Limits

*For any* InjuriesContext with N players per team, the formatted output SHALL show at most 3 players per team, ordered by impact_score descending, and key_players SHALL have the ⭐ icon.

```python
# Pseudocode
for all injuries_context with home_players, away_players:
    output = format_injuries_section(injuries_context)
    assert count_players_in_output(output, "home") <= 3
    assert count_players_in_output(output, "away") <= 3
    assert players_are_ordered_by_impact(output)
    for player in injuries_context.all_players:
        if player.is_key_player:
            assert "⭐" in output near player.name
```

**Validates: Requirements 1.2, 1.4**

### Property 3: Form Display Format and Crisis Warning

*For any* FormContext, the formatted output SHALL follow the format "WWDLL - XGF/YGS" and SHALL show ⚠️ if wins == 0.

```python
# Pseudocode
for all form_context:
    output = format_form_section(form_context)
    assert matches_pattern(output, r"[WDL]{5} - \d+GF/\d+GS")
    if form_context.home.wins == 0:
        assert "⚠️" in output near home_team
    if form_context.away.wins == 0:
        assert "⚠️" in output near away_team
```

**Validates: Requirements 2.2, 2.4**

### Property 4: H2H Market-Relevant Display

*For any* H2HContext and suggested market, the formatted output SHALL show the statistic most relevant to that market.

```python
# Pseudocode
for all h2h_context, market:
    output = format_h2h_section(h2h_context, market)
    if "Over" in market and "Goal" in market:
        assert str(h2h_context.avg_goals) in output
    if "Card" in market:
        assert str(h2h_context.avg_cards) in output
    if "Corner" in market:
        assert str(h2h_context.avg_corners) in output
```

**Validates: Requirements 3.2, 3.4**

### Property 5: Referee Strictness Icons and Incongruence Warning

*For any* RefereeContext and suggested market, the formatted output SHALL show 🟨 if strict, and SHALL show incongruence warning if lenient AND market is Over Cards.

```python
# Pseudocode
for all referee_context, market:
    output = format_referee_section(referee_context, market)
    if referee_context.strictness == "strict":
        assert "🟨" in output
    if referee_context.strictness == "lenient" and "Card" in market:
        assert "⚠️" in output or "incongruenza" in output.lower()
```

**Validates: Requirements 4.4, 4.5**

### Property 6: Standings Zone Icons

*For any* StandingsContext, the formatted output SHALL show 🏆 for top 3 positions and 🔻 for bottom 3 positions.

```python
# Pseudocode
for all standings_context:
    output = format_standings_section(standings_context)
    if standings_context.home.position <= 3:
        assert "🏆" in output near home_team
    if standings_context.home.zone == "relegation":
        assert "🔻" in output near home_team
    # Same for away team
```

**Validates: Requirements 5.4, 5.5**

### Property 7: Alert Truncation Preserves Priority

*For any* MatchContext that produces a message > 4000 chars, the truncated output SHALL preserve Header, Match Info, and the section most relevant to the suggested market.

```python
# Pseudocode
for all match_context, market where len(format(match_context)) > 4000:
    output = format_and_truncate(match_context, market)
    assert len(output) <= 4000
    assert contains_header(output)
    assert contains_match_info(output)
    if "Goal" in market:
        assert contains_form_section(output) or contains_h2h_section(output)
    if "Card" in market:
        assert contains_referee_section(output)
```

**Validates: Requirements 7.3, 7.4**

### Property 8: AI Audit Trail Completeness

*For any* alert that was sent, the ai_audit section SHALL contain prompt_hash, response_hash, model_used, and timestamp.

```python
# Pseudocode
for all news_log where sent == True:
    context = MatchContext.from_json(news_log.match_context_json)
    assert context.ai_audit is not None
    assert context.ai_audit.prompt_hash is not None
    assert context.ai_audit.response_hash is not None
    assert context.ai_audit.model_used is not None
    assert context.ai_audit.timestamp is not None
```

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 9: Null Handling Robustness

*For any* MatchContext with null sections, the AlertFormatter SHALL not raise exceptions and SHALL not display those sections.

```python
# Pseudocode
for all match_context with some_sections_null:
    output = format(match_context)  # Should not raise
    for section_name, section_value in match_context.sections:
        if section_value is None:
            assert section_name not in output
```

**Validates: Requirements 9.2, 9.4**

### Property 10: Fatigue Display with Both Teams High

*For any* FatigueContext where both teams have HIGH fatigue, the formatted output SHALL contain a suggestion about low-tempo match.

```python
# Pseudocode
for all fatigue_context:
    output = format_fatigue_section(fatigue_context)
    if fatigue_context.home.level == "HIGH":
        assert "🔋" in output near home_team
    if fatigue_context.away.level == "HIGH":
        assert "🔋" in output near away_team
    if fatigue_context.home.level == "HIGH" and fatigue_context.away.level == "HIGH":
        assert "basso ritmo" in output.lower() or "low tempo" in output.lower()
```

**Validates: Requirements 11.1, 11.4**

### Property 11: Twitter Intel Freshness Display

*For any* TwitterIntelContext, the formatted output SHALL show max 2 tweets, and STALE tweets SHALL have ⏰ indicator.

```python
# Pseudocode
for all twitter_context:
    output = format_twitter_section(twitter_context)
    assert count_tweets_in_output(output) <= 2
    for tweet in twitter_context.tweets[:2]:
        if tweet.freshness == "STALE":
            assert "⏰" in output near tweet.content
```

**Validates: Requirements 12.1, 12.3**

## Error Handling

### Errori di Serializzazione JSON

```python
def to_json(self) -> str:
    try:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        logger.error(f"MatchContext serialization failed: {e}")
        return "{}"  # Return empty JSON instead of crashing
```

### Errori di Deserializzazione JSON

```python
@classmethod
def from_json(cls, json_str: str) -> 'MatchContext':
    if not json_str:
        return cls()  # Return empty context
    try:
        data = json.loads(json_str)
        return cls.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"MatchContext deserialization failed: {e}")
        return cls()  # Return empty context instead of crashing
```

### Errori di Formattazione Alert

```python
def format(self, match_context: MatchContext, ...) -> str:
    sections = []
    
    # Each section is wrapped in try/except
    if match_context.injuries:
        try:
            sections.append(self._format_injuries_section(match_context.injuries))
        except Exception as e:
            logger.warning(f"Injuries section formatting failed: {e}")
            # Skip section, don't crash
    
    # ... same for other sections
    
    return "\n".join(sections)
```

### Errori di Database Migration

```python
def migrate_add_match_context_column():
    try:
        with engine.connect() as conn:
            # Check if column exists first
            result = conn.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('news_logs') WHERE name='match_context_json'"
            ))
            if result.scalar() == 0:
                conn.execute(text(
                    "ALTER TABLE news_logs ADD COLUMN match_context_json TEXT"
                ))
                conn.commit()
                logger.info("✅ Added match_context_json column")
            else:
                logger.info("✅ match_context_json column already exists")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # Don't crash - system can work without the new column
```

## Testing Strategy

### Unit Tests

1. **MatchContext Serialization**
   - Test to_json() produces valid JSON
   - Test from_json() restores equivalent object
   - Test handling of None values
   - Test handling of special characters (emoji, unicode)

2. **AlertFormatter Sections**
   - Test each _format_*_section() method independently
   - Test truncation logic
   - Test priority ordering during truncation

3. **MatchContextBuilder**
   - Test each with_*() method
   - Test build() produces valid MatchContext
   - Test incremental building (not all sections required)

### Property-Based Tests

Usando `hypothesis` per Python:

1. **Round-Trip Property** (Property 1)
   - Generate random MatchContext objects
   - Verify to_json() → from_json() produces equivalent object

2. **Player Limit Property** (Property 2)
   - Generate InjuriesContext with 0-20 players per team
   - Verify output never shows more than 3 per team

3. **Null Robustness Property** (Property 9)
   - Generate MatchContext with random null sections
   - Verify no exceptions raised during formatting

### Integration Tests

1. **End-to-End Alert Flow**
   - Create match with all data available
   - Run through full pipeline
   - Verify NewsLog.match_context_json is populated
   - Verify Telegram message contains all sections

2. **Partial Data Flow**
   - Create match with only some data available
   - Verify system handles missing data gracefully
   - Verify only available sections are shown

### Test Configuration

```python
# pytest.ini
[pytest]
markers =
    property: Property-based tests (may take longer)
    integration: Integration tests requiring database

# conftest.py
@pytest.fixture
def sample_match_context():
    """Fixture for a fully populated MatchContext."""
    return MatchContext(
        injuries=InjuriesContext(...),
        form=FormContext(...),
        # ... etc
    )

@pytest.fixture
def empty_match_context():
    """Fixture for an empty MatchContext (all None)."""
    return MatchContext()
```

