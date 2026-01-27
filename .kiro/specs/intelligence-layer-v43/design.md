# Design Document: Intelligence Layer V4.3

## Overview

Questo documento descrive il design tecnico per il potenziamento dell'Intelligence Layer di EarlyBird V4.3. L'obiettivo è trasformare il sistema da puramente reattivo a predittivo, migliorando la qualità delle informazioni raccolte attraverso:

1. **Validazione algoritmica** dei canali Telegram (Trust Score V2)
2. **Prioritizzazione** delle fonti tier-1 (Beat Writer System)
3. **Rilevamento avanzato** di smart money (RLM Enhancement)
4. **Decadimento adattivo** delle news (Dynamic Decay)

Il design si integra con l'architettura esistente senza breaking changes, seguendo il principio di "additive layers" già presente nel sistema.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER V4.3 ARCHITECTURE                   │
└──────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   MAIN PIPELINE │
                              │    (main.py)    │
                              └────────┬────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
         ▼                             ▼                             ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   TELEGRAM      │         │   NEWS HUNTER   │         │    MARKET       │
│   LISTENER      │         │   (news_hunter) │         │  INTELLIGENCE   │
│                 │         │                 │         │                 │
│ ┌─────────────┐ │         │ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │ Trust Score │ │         │ │ Beat Writer │ │         │ │     RLM     │ │
│ │    V2.0     │ │         │ │   Priority  │ │         │ │  Enhanced   │ │
│ └─────────────┘ │         │ └─────────────┘ │         │ └─────────────┘ │
│                 │         │                 │         │                 │
│ ┌─────────────┐ │         │ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │   Channel   │ │         │ │   Dynamic   │ │         │ │    Steam    │ │
│ │   Metrics   │ │         │ │ News Decay  │ │         │ │    Move     │ │
│ └─────────────┘ │         │ └─────────────┘ │         │ └─────────────┘ │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │    AI ANALYZER      │
                          │   (DeepSeek V3.2)   │
                          │                     │
                          │  Receives enriched  │
                          │  dossier with:      │
                          │  - Trust scores     │
                          │  - Source priority  │
                          │  - RLM signals      │
                          │  - Freshness tags   │
                          └─────────────────────┘
```

## Components and Interfaces

### 1. Telegram Trust Score V2 Module

**File**: `src/analysis/telegram_trust_score.py` (existing, to be enhanced)

**New Functions**:

```python
def calculate_trust_score_v2(metrics: ChannelMetrics) -> Tuple[float, TrustLevel]:
    """
    Enhanced trust score calculation with weighted components.
    
    Weights:
    - Timestamp Lag Score: 40%
    - Edit/Delete Score: 25%
    - Accuracy Score: 25%
    - Red Flag Penalty: 10%
    
    Returns:
        Tuple of (trust_score 0-1, trust_level enum)
    """

def track_odds_correlation(
    channel_id: str,
    message_time: datetime,
    match_id: str
) -> Optional[float]:
    """
    Track correlation between message timing and odds movement.
    
    Queries odds_snapshots to find first significant drop after message.
    Returns lag in minutes (negative = insider, positive = follower).
    """

def update_channel_accuracy(
    channel_id: str,
    prediction_correct: bool
) -> None:
    """
    Update channel accuracy metrics after match settlement.
    Called by settler.py during nightly settlement.
    """
```

**Interface with telegram_listener.py**:
```python
# In telegram_listener.py, after message validation:
validation = validate_telegram_message_v2(
    channel_id=channel,
    message_text=full_text,
    message_time=msg.date,
    match_id=match.id if match else None
)

# Apply trust multiplier to news impact
news_impact = base_impact * validation.trust_multiplier
```

### 2. Beat Writer Priority System

**File**: `src/processing/sources_config.py` (existing, to be enhanced)

**New Data Structure**:

```python
@dataclass
class BeatWriter:
    handle: str           # Twitter handle (e.g., "@gastaboricua")
    name: str             # Full name
    outlet: str           # Media outlet
    specialty: str        # "injuries", "transfers", "lineups"
    reliability: float    # 0.0-1.0 historical accuracy
    avg_lead_time_min: int  # Average minutes before mainstream

BEAT_WRITERS_DB = {
    "turkey": [
        BeatWriter("@yaboricuaoglu", "Yağız Sabuncuoğlu", "A Spor", "injuries", 0.85, 15),
        BeatWriter("@ragipsoylu", "Ragıp Soylu", "Fanatik", "lineups", 0.80, 10),
    ],
    "argentina": [
        BeatWriter("@gastaboricua", "Gastón Edul", "TyC Sports", "injuries", 0.90, 20),
        BeatWriter("@aboricua", "Augusto César", "Olé", "transfers", 0.75, 12),
    ],
    # ... other leagues
}
```

**New Function in news_hunter.py**:

```python
def search_beat_writers_priority(
    team_alias: str,
    league_key: str,
    match_id: str
) -> List[Dict]:
    """
    Priority search for beat writer content.
    
    Called BEFORE generic search to catch breaking news early.
    Results are tagged with 'confidence': 'HIGH' and 'priority_boost': 1.5
    """
```

### 3. RLM Detector Enhancement

**File**: `src/analysis/market_intelligence.py` (existing, to be enhanced)

**Enhanced RLM Detection**:

```python
@dataclass
class RLMSignalV2:
    detected: bool
    market: str                    # 'HOME', 'AWAY'
    public_side: str               # Where public money is going
    sharp_side: str                # Where sharp money is going
    public_percentage: float       # e.g., 0.72 = 72% on public side
    odds_movement_pct: float       # How much odds moved against public
    confidence: str                # 'HIGH', 'MEDIUM', 'LOW'
    time_window_min: int           # How long the pattern developed
    recommendation: str            # "Consider AWAY" or similar
    message: str

def detect_rlm_v2(
    match: Match,
    public_bet_distribution: Optional[Dict[str, float]] = None,
    min_public_threshold: float = 0.65,
    min_odds_increase: float = 0.03
) -> Optional[RLMSignalV2]:
    """
    Enhanced RLM detection with configurable thresholds.
    
    New features:
    - Confidence levels based on movement magnitude
    - Time window analysis
    - Sharp side recommendation
    """
```

### 4. Dynamic News Decay Module

**File**: `src/analysis/market_intelligence.py` (existing, to be enhanced)

**New Configuration**:

```python
# League-specific decay rates
DECAY_RATES = {
    # Elite leagues (slower markets) - half-life ~30 min
    "elite": {
        "lambda": 0.023,
        "half_life_min": 30,
        "leagues": ["soccer_turkey_super_league", "soccer_argentina_primera_division", ...]
    },
    # Tier 1 leagues (fast markets) - half-life ~5 min
    "tier1": {
        "lambda": 0.14,
        "half_life_min": 5,
        "leagues": ["soccer_epl", "soccer_spain_la_liga", ...]
    }
}

# Source-based decay modifiers
SOURCE_DECAY_MODIFIERS = {
    "insider_verified": 0.5,    # Decay 50% slower
    "beat_writer": 0.7,         # Decay 30% slower
    "mainstream": 1.0,          # Normal decay
    "reddit": 1.2,              # Decay 20% faster
    "unknown": 1.5              # Decay 50% faster
}
```

**Enhanced Decay Function**:

```python
def apply_news_decay_v2(
    impact_score: float,
    minutes_since_publish: int,
    league_key: str,
    source_type: str = "mainstream",
    minutes_to_kickoff: Optional[int] = None
) -> Tuple[float, str]:
    """
    Enhanced news decay with league, source, and kickoff awareness.
    
    Args:
        impact_score: Original impact (0-10)
        minutes_since_publish: Age of news
        league_key: For league-specific decay rate
        source_type: For source-based modifier
        minutes_to_kickoff: For kickoff proximity acceleration
        
    Returns:
        Tuple of (decayed_score, freshness_tag)
    """
```

## Data Models

### Enhanced Channel Metrics Table

```sql
-- Existing table: telegram_channels (enhanced)
ALTER TABLE telegram_channels ADD COLUMN IF NOT EXISTS
    odds_correlation_count INTEGER DEFAULT 0;
ALTER TABLE telegram_channels ADD COLUMN IF NOT EXISTS
    avg_timestamp_lag_minutes FLOAT DEFAULT 0.0;
ALTER TABLE telegram_channels ADD COLUMN IF NOT EXISTS
    predictions_made INTEGER DEFAULT 0;
ALTER TABLE telegram_channels ADD COLUMN IF NOT EXISTS
    predictions_correct INTEGER DEFAULT 0;
ALTER TABLE telegram_channels ADD COLUMN IF NOT EXISTS
    last_accuracy_update DATETIME;
```

### Beat Writer Tracking Table (New)

```sql
CREATE TABLE IF NOT EXISTS beat_writer_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT NOT NULL,
    league_key TEXT NOT NULL,
    match_id TEXT,
    message_time DATETIME NOT NULL,
    first_mainstream_time DATETIME,  -- When mainstream picked it up
    lead_time_minutes INTEGER,       -- How much earlier than mainstream
    was_accurate BOOLEAN,            -- Verified after match
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bw_handle_league ON beat_writer_hits (handle, league_key);
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Trust Multiplier Range Invariant
*For any* Telegram message with any timestamp and any odds drop time, the calculated trust multiplier SHALL always be in the range [0.0, 1.0].
**Validates: Requirements 1.1**

### Property 2: Timestamp Lag Classification Consistency
*For any* (message_time, odds_drop_time) pair, if message_time precedes odds_drop_time by more than 3 minutes, the classification SHALL be "insider_hit"; if message_time follows odds_drop_time by more than 30 minutes, the classification SHALL be "late".
**Validates: Requirements 1.2, 1.3**

### Property 3: Blacklist Threshold Consistency
*For any* channel with trust_score < 0.20, the channel's trust_level SHALL be TrustLevel.BLACKLISTED.
**Validates: Requirements 1.4**

### Property 4: Echo Detection Symmetry
*For any* two messages with identical normalized content posted within 2 minutes, the second message SHALL be flagged as echo regardless of which channel posted first.
**Validates: Requirements 1.5**

### Property 5: Trust Score Weight Sum
*For any* trust score calculation, the sum of weights (timestamp_lag + edit_ratio + accuracy + red_flags) SHALL equal 1.0 (100%).
**Validates: Requirements 1.7**

### Property 6: Beat Writer Confidence Assignment
*For any* search result originating from a configured beat writer handle, the result SHALL have confidence="HIGH" and priority_boost >= 1.5.
**Validates: Requirements 2.2**

### Property 7: RLM Signal Generation Threshold
*For any* match where public_percentage >= 0.65 on one side AND odds for that side increased by >= 3%, an RLM signal SHALL be generated.
**Validates: Requirements 3.1, 3.2**

### Property 8: RLM Output Completeness
*For any* generated RLM signal, the signal SHALL include a non-empty sharp_side field indicating the recommended betting side.
**Validates: Requirements 3.3**

### Property 9: RLM High Confidence Threshold
*For any* RLM signal where odds_movement_pct > 5%, the confidence SHALL be "HIGH".
**Validates: Requirements 3.5**

### Property 10: League-Specific Decay Rate Selection
*For any* news item from an Elite league, the decay lambda SHALL be approximately 0.023; for Tier 1 leagues, the lambda SHALL be approximately 0.14.
**Validates: Requirements 4.1, 4.2**

### Property 11: Kickoff Proximity Decay Acceleration
*For any* news item where minutes_to_kickoff <= 30, the effective decay rate SHALL be at least 2x the base rate.
**Validates: Requirements 4.3**

### Property 12: Insider Source Decay Reduction
*For any* news item from a verified insider source, the effective decay rate SHALL be at most 0.5x the base rate.
**Validates: Requirements 4.4**

### Property 13: Maximum Age Cap
*For any* news item older than 24 hours (1440 minutes), the residual impact SHALL be at most 1% of the original impact.
**Validates: Requirements 4.5**

### Property 14: Freshness Tag Assignment
*For any* news item after decay calculation, the freshness_tag SHALL be one of ["🔥 FRESH", "⏰ AGING", "📜 STALE"] based on the decay multiplier (>0.7, 0.3-0.7, <0.3 respectively).
**Validates: Requirements 4.6**

### Property 15: Dossier Output Completeness
*For any* AI dossier generated by the orchestrator, the dossier SHALL include fields for trust_scores, source_attribution, rlm_signals, and freshness_tags.
**Validates: Requirements 5.3, 5.4**

## Error Handling

### Graceful Degradation Strategy

```python
# In main.py pipeline:
def run_intelligence_layer(match: Match) -> IntelligenceResult:
    result = IntelligenceResult()
    
    # Each module wrapped in try/except for graceful degradation
    try:
        result.telegram_intel = process_telegram_intel(match)
    except Exception as e:
        logging.warning(f"Telegram intel failed: {e}")
        result.telegram_intel = None  # Continue without
    
    try:
        result.beat_writer_intel = search_beat_writers_priority(...)
    except Exception as e:
        logging.warning(f"Beat writer search failed: {e}")
        result.beat_writer_intel = []  # Empty list, fallback to standard
    
    try:
        result.rlm_signal = detect_rlm_v2(match)
    except Exception as e:
        logging.warning(f"RLM detection failed: {e}")
        result.rlm_signal = None
    
    # News decay is applied inline, errors logged but don't block
    return result
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| No odds_snapshots for match | Skip RLM detection, log reason |
| Channel not in database | Create new record with neutral trust (0.5) |
| Beat writer handle not found | Fall back to standard search |
| News date unparseable | Assume 30 min old (moderate decay) |
| Division by zero in decay | Return 0.01 (minimum residual) |
| Telegram API timeout | Skip channel, continue with others |

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests:

1. **Unit Tests**: Verify specific examples, edge cases, and integration points
2. **Property-Based Tests**: Verify universal properties hold across all valid inputs

### Property-Based Testing Framework

**Library**: `hypothesis` (Python PBT library)

**Configuration**:
```python
from hypothesis import given, strategies as st, settings

@settings(max_examples=100)  # Minimum 100 iterations per property
```

### Test File Structure

```
tests/
├── test_telegram_trust_score.py      # Unit + PBT for Trust Score V2
├── test_beat_writer_priority.py      # Unit + PBT for Beat Writer System
├── test_rlm_detector.py              # Unit + PBT for RLM Enhancement
├── test_news_decay.py                # Unit + PBT for Dynamic Decay
└── test_intelligence_integration.py  # Integration tests
```

### Property Test Annotations

Each property-based test MUST be annotated with:
```python
# **Feature: intelligence-layer-v43, Property 1: Trust Multiplier Range Invariant**
# **Validates: Requirements 1.1**
@given(...)
def test_trust_multiplier_range(self, ...):
    ...
```
