# REMOVED CODE BACKUP - CACHEDTWEET & CARDSIGNAL

**Date**: 2026-03-09  
**Purpose**: Backup di tutto il codice rimosso durante i fix COVE  
**Status**: Codice rimosso ma disponibile per reintegrazione futura

---

## 1. enrich_alert_with_twitter_intel() Method

**Location**: [`src/services/twitter_intel_cache.py`](src/services/twitter_intel_cache.py:697-797)  
**Status**: RIMOSSO - Codice morto (mai chiamato nel flusso principale)

### Codice Completo

```python
def enrich_alert_with_twitter_intel(
    self, alert: dict, home_team: str, away_team: str, league_key: str
) -> dict:
    """
    Arricchisce un alert con intel Twitter rilevanti.

    Args:
        alert: Alert da arricchire
        home_team: Nome team casa
        away_team: Nome team trasferta
        league_key: Chiave lega

    Returns:
        Alert arricchito con campo 'twitter_intel'
    """
    relevant_tweets = []

    # Cerca menzioni dei team
    for team in [home_team, away_team]:
        tweets = self.search_intel(team, league_key)
        for tweet in tweets:
            relevant_tweets.append(
                {
                    "handle": tweet.handle,
                    "content": tweet.content[:200],  # Tronca per brevità
                    "date": tweet.date,
                    "topics": tweet.topics,
                    "relevance": self._calculate_relevance(tweet, team, alert),
                }
            )

    # Ordina per rilevanza
    relevant_tweets.sort(
        key=lambda x: {"high": 0, "medium": 1, "low": 2, "none": 3}.get(x["relevance"], 3)
    )

    # Aggiungi all'alert
    alert["twitter_intel"] = {
        "tweets": relevant_tweets[:5],  # Max 5 tweet più rilevanti
        "cache_age_minutes": self.cache_age_minutes,
        "cycle_id": self._cycle_id,
    }

    return alert
```

### Note
- Questa funzione era documentata nel FLUSSO ma mai chiamata
- Solo usata nei test: test_enrich_alert_with_empty_cache(), test_enrich_alert_preserves_original_data()
- Se reintegrata, aggiorna anche la documentazione nel FLUSSO

---

## 2. _calculate_relevance() Helper Method

**Location**: [`src/services/twitter_intel_cache.py`](src/services/twitter_intel_cache.py:799-815)  
**Status**: RIMOSSO - Helper method per enrich_alert_with_twitter_intel()

### Codice Completo

```python
def _calculate_relevance(self, tweet: CachedTweet, team: str, alert: dict) -> str:
    """Calcola rilevanza di un tweet per un alert"""
    content_lower = tweet.content.lower()
    team_lower = team.lower()

    # HIGH: menziona team + topic critico (injury, lineup)
    if team_lower in content_lower:
        if any(t in tweet.topics for t in ["injury", "lineup", "squad"]):
            return "high"
        return "medium"

    # MEDIUM: topic correlato
    if any(t in tweet.topics for t in ["injury", "lineup", "transfer"]):
        return "medium"

    # LOW: generico
    return "low"
```

### Note
- Helper method usato solo da enrich_alert_with_twitter_intel()
- Se reintegrata, deve essere inclusa insieme a enrich_alert_with_twitter_intel()

---

## 3. CardsSignal Enum

**Location**: [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:67-73)  
**Status**: RIMOSSO - Codice morto (mai usato per decisioni di betting)

### Codice Completo

```python
class CardsSignal(str, Enum):
    """Cards signal levels."""

    AGGRESSIVE = "Aggressive"
    MEDIUM = "Medium"
    DISCIPLINED = "Disciplined"
    UNKNOWN = "Unknown"
```

### Note
- Era definito come str, Enum
- Usato in BettingStatsResponse ma mai estratto nel verification_layer
- Se reintegrata, aggiungi anche i campi correlati in BettingStatsResponse

---

## 4. validate_cards_signal() Validator

**Location**: [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:308-323)  
**Status**: RIMOSSO - Validator per CardsSignal (mai usato)

### Codice Completo

```python
@field_validator("cards_signal")
@classmethod
def validate_cards_signal(cls, v):
    """Validate cards signal is a valid enum (case-insensitive)."""
    if isinstance(v, str):
        v_lower = v.lower()
        for signal in [
            CardsSignal.AGGRESSIVE,
            CardsSignal.MEDIUM,
            CardsSignal.DISCIPLINED,
            CardsSignal.UNKNOWN,
        ]:
            if v_lower == signal.value.lower():
                return signal.value
        return CardsSignal.UNKNOWN
    return v
```

### Note
- Questa versione era già case-insensitive (fix applicato prima della rimozione)
- Se reintegrata, deve essere inserita dopo la definizione di CardsSignal

---

## 5. Cards Fields in BettingStatsResponse

**Location**: [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py:257-266)  
**Status**: RIMOSSI - Campi mai usati per decisioni di betting

### Codice Completo

```python
# Cards Statistics
home_cards_avg: float | None = Field(
    default=None, ge=0, description="Home team average cards per game"
)
away_cards_avg: float | None = Field(
    default=None, ge=0, description="Away team average cards per game"
)
cards_total_avg: float | None = Field(default=None, ge=0, description="Combined average cards")
cards_signal: CardsSignal = Field(default=CardsSignal.UNKNOWN, description="Cards signal level")
cards_reasoning: str = Field(default="", description="Explanation of card potential")
```

### Note
- Questi campi erano validati ma mai usati nel verification_layer
- Se reintegrati, inseriscili dopo "Corners Statistics" e prima di "Referee Information"
- Aggiorna anche i prompt in system_prompts.py

---

## 6. Cards References in Logging

**Location**: [`src/ingestion/perplexity_provider.py`](src/ingestion/perplexity_provider.py:646-647)  
**Status**: RIMOSSO - Logging mai usato per decisioni

### Codice Completo

```python
# In perplexity_provider.py
logger.info(
    f"✅ [PERPLEXITY] Betting stats retrieved: corners={result.get('corners_signal')}, cards={result.get('cards_signal')}"
)
```

**Location**: [`src/ingestion/openrouter_fallback_provider.py`](src/ingestion/openrouter_fallback_provider.py:241-242)  
**Status**: RIMOSSO - Logging mai usato per decisioni

### Codice Completo

```python
# In openrouter_fallback_provider.py
logger.info(
    f"✅ [CLAUDE] Betting stats retrieved: corners={result.get('corners_signal')}, cards={result.get('cards_signal')}"
)
```

### Note
- Se reintegrati, ripristina il logging completo con cards_signal

---

## 7. Cards Fields in System Prompts

**Location**: [`src/prompts/system_prompts.py`](src/prompts/system_prompts.py:75-110)  
**Status**: RIMOSSI - Campi nel prompt per l'API

### Codice Completo

```python
# Nel dict JSON SCHEMA:
"home_cards_avg": float,
"away_cards_avg": float,
"cards_total_avg": float,
"cards_signal": "Aggressive/Medium/Disciplined",
"cards_reasoning": "Short explanation",

# Nel FIELD REQUIREMENTS:
- cards_signal: Must be "Aggressive", "Medium", "Disciplined", or "Unknown"

# Nel JSON SCHEMA:
"recommended_cards_line": "Over/Under/No bet + line",
```

### Note
- Se reintegrati, inseriscili dopo "corners_reasoning" e prima di "referee_name"
- Aggiorna anche le descrizioni nel prompt

---

## 8. Tests for enrich_alert_with_twitter_intel()

**Location**: [`tests/test_twitter_intel_cache.py`](tests/test_twitter_intel_cache.py:373-415)  
**Status**: RIMOSSI - Test per codice morto

### Codice Completo

```python
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_enrich_alert_with_empty_cache(self):
        """Enriching alert with empty cache should not crash."""
        from src.services.twitter_intel_cache import TwitterIntelCache

        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        cache._cycle_id = "test"
        cache._last_full_refresh = datetime.now()

        alert = {"score": 8, "market": "Home Win"}

        enriched = cache.enrich_alert_with_twitter_intel(
            alert=alert,
            home_team="Galatasaray",
            away_team="Fenerbahce",
            league_key="soccer_turkey_super_league",
        )

        assert "twitter_intel" in enriched
        assert enriched["twitter_intel"]["tweets"] == []

    def test_enrich_alert_preserves_original_data(self):
        """Enriching alert should preserve original alert data."""
        from src.services.twitter_intel_cache import TwitterIntelCache

        cache = TwitterIntelCache.__new__(TwitterIntelCache)
        cache._initialized = False
        cache.__init__()
        cache._cache = {}
        cache._cycle_id = "test"
        cache._last_full_refresh = datetime.now()

        alert = {"score": 8, "market": "Home Win", "custom_field": "should_be_preserved"}

        enriched = cache.enrich_alert_with_twitter_intel(
            alert=alert, home_team="Test", away_team="Test2", league_key="test"
        )

        assert enriched["score"] == 8
        assert enriched["market"] == "Home Win"
        assert enriched["custom_field"] == "should_be_preserved"
```

### Note
- Questi test erano nella classe TestEdgeCases
- Se reintegrati, inseriscili dopo test_cache_is_fresh_after_refresh()

---

## 9. Cards Signal References in Tests

**Location**: [`tests/test_perplexity_structured_outputs.py`](tests/test_perplexity_structured_outputs.py)  
**Status**: RIMOSSI - Riferimenti a cards_signal nei test

### Codice Rimosso

```python
# In test_valid_betting_stats_response():
"home_cards_avg": 1.8,
"away_cards_avg": 2.1,
"cards_total_avg": 3.9,
"cards_signal": "Medium",
"cards_reasoning": "Away team more aggressive, home disciplined",

assert response.cards_signal == "Medium"

# In test_optional_fields_can_be_null():
"cards_signal": "Unknown",
"recommended_cards_line": "No bet",

# In test_invalid_form_values():
"cards_signal": "Medium",
"recommended_cards_line": "No bet",

# In test_enum_validation():
"cards_signal": "Medium",
"recommended_cards_line": "No bet",

# In test_json_schema_structure():
assert "cards_signal" in schema["properties"]

# In test_betting_stats_serialization_roundtrip():
"cards_signal": "Medium",

# In test_deep_dive_response():
"cards_signal": "Disciplined",
```

**Location**: [`test_three_level_fallback.py`](test_three_level_fallback.py:86-92)  
**Status**: RIMOSSI - Riferimenti a cards_signal nei test

### Codice Rimosso

```python
assert result is not None, "Betting stats should return a result"
assert "corners_signal" in result, "Result should contain corners_signal"
assert "cards_signal" in result, "Result should contain cards_signal"

logger.info("✅ Betting stats retrieval successful")
logger.info(f"   Corners signal: {result.get('corners_signal')}")
logger.info(f"   Cards signal: {result.get('cards_signal')}")
```

### Note
- Se reintegrati, ripristina tutti i riferimenti a cards_signal nei test
- Verifica che i test passino correttamente dopo la reintegrazione

---

## Istruzioni per Reintegrazione

### Passo 1: Reintegri CardsSignal Enum
1. Inserisci il codice di CardsSignal in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py) dopo la definizione di RefereeStrictness
2. Verifica che non ci siano conflitti con altri enum

### Passo 2: Reintegri Campi in BettingStatsResponse
1. Inserisci i campi cards in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py) dopo "Corners Statistics" e prima di "Referee Information"
2. Verifica che i tipi siano corretti

### Passo 3: Reintegri Validator
1. Inserisci validate_cards_signal() in [`src/schemas/perplexity_schemas.py`](src/schemas/perplexity_schemas.py) dopo validate_corners_signal()
2. Verifica che sia case-insensitive

### Passo 4: Reintegri Logging
1. Ripristina il logging completo in [`src/ingestion/perplexity_provider.py`](src/ingestion/perplexity_provider.py)
2. Ripristina il logging completo in [`src/ingestion/openrouter_fallback_provider.py`](src/ingestion/openrouter_fallback_provider.py)

### Passo 5: Reintegri System Prompts
1. Inserisci i campi cards in [`src/prompts/system_prompts.py`](src/prompts/system_prompts.py)
2. Aggiorna le descrizioni nel prompt

### Passo 6: Reintegri enrich_alert_with_twitter_intel()
1. Inserisci il metodo in [`src/services/twitter_intel_cache.py`](src/services/twitter_intel_cache.py)
2. Inserisci _calculate_relevance() helper method
3. Aggiorna la documentazione nel FLUSSO (aggiungi punto 3)

### Passo 7: Reintegri Tests
1. Ripristina i test in [`tests/test_twitter_intel_cache.py`](tests/test_twitter_intel_cache.py)
2. Ripristina i riferimenti a cards_signal in [`tests/test_perplexity_structured_outputs.py`](tests/test_perplexity_structured_outputs.py)
3. Ripristina i riferimenti a cards_signal in [`test_three_level_fallback.py`](test_three_level_fallback.py)

### Passo 8: Verifica
1. Esegui i test per verificare che tutto funzioni correttamente
2. Verifica il logging per confermare che i dati vengono raccolti

---

**Backup Created**: 2026-03-09T06:40:00Z  
**Purpose**: Permettere reintegrazione futura del codice rimosso  
**Status**: ✅ COMPLETED
