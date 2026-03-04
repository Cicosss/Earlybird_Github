# Guida Implementazione: Referee Intelligence Boost System

**Versione:** 1.0  
**Data:** 2026-02-26  
**Stato:** TEMPORANEO - DA IMPLEMENTARE  
**Autore:** COVE Analysis

---

## 📋 Executive Summary

Questo documento guida l'implementazione delle funzionalità di **Referee Intelligence Boost** mancanti nel sistema Earlybird. L'obiettivo è trasformare il sistema di referee da **solo negativo** (veto) a **bidirezionale** (veto + boost positivo).

---

## 🎯 Obiettivi di Implementazione

### Obiettivo #1: Referee Boost Logic (CRITICAL)
**Descrizione:** Implementare logica che sovrascrive "No bet" → "Over Cards" per arbitri severi

**Requisiti:**
- Se arbitro è severo (≥4.0 cards/game) e AI dice "No bet" → Override a "Over 3.5 Cards"
- Se arbitro è severo E partita è derby/high intensity → Override a "Over 3.5 Cards"
- Se arbitro è molto severo (≥5.0 cards/game) e AI dice "Over 3.5" → Upgrade a "Over 4.5"

### Obiettivo #2: Estensione ad Altri Mercati
**Descrizione:** Far influenzare l'arbitro anche Goals, Corners, Winner markets

**Requisiti:**
- Goals Market: Arbitro severo può influenzare Over/Under Goals decisioni
- Corners Market: Arbitro severo può suggerire Over Corners
- Winner Market: Arbitro può influenzare confidenza su 1X2

### Obiettivo #3: Arbitro Obbligatorio per Cards Market
**Descrizione:** Richiedere dati dell'arbitro per decisioni Cards Market

**Requisiti:**
- Se referee_stats non disponibili → Skip Cards Market (non suggerire)
- Ridurre confidenza se referee_stats = "Unknown"

### Obgetto #4: Cache per Statistiche Arbitro
**Descrizione:** Ridurre dipendenza da provider esterni (Tavily/Perplexity)

**Requisiti:**
- Implementare cache locale per statistiche arbitro
- TTL: 7 giorni (le statistiche dell'arbitro cambiano lentamente)
- Fallback: Se cache miss → Query provider esterni

---

## 🏗️ Architettura Esistente (DA RIUTILIZZARE)

### Componenti Esistenti

#### 1. Classe RefereeStats
**File:** [`src/analysis/verification_layer.py:382-431`](src/analysis/verification_layer.py:382-431)

**Metodi Utili:**
```python
@dataclass
class RefereeStats:
    name: str
    cards_per_game: float = 0.0
    strictness: str = "unknown"  # "strict", "average", "lenient", "unknown"
    matches_officiated: int = 0
    
    def is_strict(self) -> bool:
        """Check if referee is classified as strict."""
        return self.strictness == "strict"
    
    def is_lenient(self) -> bool:
        """Check if referee is classified as lenient."""
        return self.strictness == "lenient"
    
    def should_veto_cards(self) -> bool:
        """Check if referee should veto Over Cards suggestions."""
        return self.is_lenient()
```

**Thresholds Definiti:**
```python
REFEREE_STRICT_THRESHOLD = 5.0    # cards/game >= 5 = strict
REFEREE_LENIENT_THRESHOLD = 3.0   # cards/game <= 3 = lenient
```

#### 2. Sistema di Verification
**File:** [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)

**Funzioni Utili:**
- `_check_referee_suitability()` - Già implementa veto per arbitri lenient
- `_detect_inconsistencies()` - Già calcola adjusted_score e inconsistencies
- `_determine_status()` - Già decide CONFIRM/CHANGE_MARKET/REJECT

#### 3. AI Analysis System
**File:** [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Componenti:**
- `analyze_with_triangulation()` - Funzione principale di analisi AI
- `TRIANGULATION_SYSTEM_PROMPT` - Prompt per AI (contiene già logica veto V2.8)
- `USER_MESSAGE_TEMPLATE` - Template per messaggio utente

#### 4. Analysis Engine
**File:** [`src/core/analysis_engine.py`](src/core/analysis_engine.py)

**Flusso Esistente:**
```
1. Parallel Enrichment → referee_info
2. AI Analysis → analyze_with_triangulation()
3. Verification → run_verification_check()
4. Final Verifier → build_alert_data_for_verifier()
```

#### 5. Programmatic Market Veto (ESEMPIO DA SEGUIRE)
**File:** [`src/analysis/analyzer.py:2045-2065`](src/analysis/analyzer.py:2045-2065)

**Pattern da Riutilizzare:**
```python
# V5.1: Programmatic Market Veto - Hard rule for market crashes
# If odds have dropped >= 15%, override verdict to NO BET
odds_drop = 0.0
try:
    drop_match = re.search(r"dropped\s+(\d+(?:\.\d+)?)\s*%", market_status, re.IGNORECASE)
    if drop_match:
        odds_drop = float(drop_match.group(1)) / 100.0
except (ValueError, AttributeError, TypeError):
    pass

# Apply market veto if drop >= 15%
if odds_drop >= 0.15 and verdict == "BET":
    verdict = "NO BET"
    reasoning = f"⚠️ VALUE GONE: Market already crashed (>15% drop). News is fully priced in.\n\n{reasoning}"
    logging.info(
        f"🛑 PROGRAMMATIC MARKET VETO: Odds dropped {odds_drop * 100:.1f}% (>=15%), overriding verdict to NO BET"
    )
```

---

## 📝 Piano di Implementazione

### STEP #1: Estendere Classe RefereeStats

**File:** [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py)

**Modifiche:**
```python
@dataclass
class RefereeStats:
    name: str
    cards_per_game: float = 0.0
    strictness: str = "unknown"  # "strict", "average", "lenient", "unknown"
    matches_officiated: int = 0
    
    # Nuovi metodi per boost positivo
    def should_boost_cards(self) -> bool:
        """
        Check if referee should boost Over Cards suggestions.
        
        Returns:
            True if referee is strict enough to justify Over Cards bet
        """
        return self.is_strict() and self.cards_per_game >= 4.0
    
    def should_upgrade_cards_line(self) -> bool:
        """
        Check if referee is very strict and should upgrade cards line.
        
        Returns:
            True if referee is very strict (>=5.0 cards/game)
        """
        return self.cards_per_game >= 5.0
    
    def get_boost_multiplier(self) -> float:
        """
        Get boost multiplier based on referee strictness.
        
        Returns:
            Multiplier: 1.0 (no boost), 1.2 (moderate), 1.5 (strong)
        """
        if self.cards_per_game >= 5.0:
            return 1.5  # Strong boost
        elif self.cards_per_game >= 4.0:
            return 1.2  # Moderate boost
        else:
            return 1.0  # No boost
```

**Perché qui?**
- La classe RefereeStats è il luogo naturale per aggiungere metodi relativi all'arbitro
- Mantiene la coerenza con l'architettura esistente
- Facile da testare in isolamento

---

### STEP #2: Implementare Referee Boost Logic

**File:** [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Posizione:** Dopo "Programmatic Market Veto" (linea 2065), prima di costruire il NewsLog

**Codice da Aggiungere:**
```python
# V9.0: REFEREE INTELLIGENCE BOOST
# Apply positive boost for strict referees on Cards Market
referee_boost_applied = False
referee_boost_reason = ""

try:
    # Check if we have referee data
    if referee_info and isinstance(referee_info, RefereeStats):
        # Only apply to Cards Market
        is_cards_market = (
            (recommended_market and "card" in recommended_market.lower()) or
            (combo_suggestion and "card" in combo_suggestion.lower())
        )
        
        if is_cards_market:
            # CASE 1: Strict referee + "No bet" → Override to "Over 3.5 Cards"
            if verdict == "NO BET" and referee_info.should_boost_cards():
                # Check for high intensity context
                is_high_intensity = (
                    "derby" in tactical_context.lower() or
                    "rivalry" in tactical_context.lower() or
                    "relegation" in tactical_context.lower() or
                    "title decider" in tactical_context.lower()
                )
                
                if is_high_intensity or referee_info.cards_per_game >= 4.5:
                    verdict = "BET"
                    if not recommended_market or recommended_market == "NONE":
                        recommended_market = "Over 3.5 Cards"
                    referee_boost_applied = True
                    referee_boost_reason = (
                        f"⚖️ REFEREE BOOST: Arbitro severo ({referee_info.name}: "
                        f"{referee_info.cards_per_game:.1f} cards/game) "
                        f"+ {'Derby/High Intensity' if is_high_intensity else 'Strict Referee'}"
                    )
                    logging.info(f"   {referee_boost_reason} → suggesting {recommended_market}")
            
            # CASE 2: Very strict referee + "Over 3.5" → Upgrade to "Over 4.5"
            elif (recommended_market == "Over 3.5 Cards" and 
                  referee_info.should_upgrade_cards_line()):
                recommended_market = "Over 4.5 Cards"
                referee_boost_applied = True
                referee_boost_reason = (
                    f"⚖️ REFEREE UPGRADE: Arbitro molto severo ({referee_info.name}: "
                    f"{referee_info.cards_per_game:.1f} cards/game) "
                    f"→ upgrading to {recommended_market}"
                )
                logging.info(f"   {referee_boost_reason}")
            
            # CASE 3: Add boost to reasoning
            if referee_boost_applied:
                reasoning = f"{referee_boost_reason}\n\n{reasoning}"
                # Increase confidence for referee boost
                confidence = min(95, confidence + 10)  # Cap at 95%
except Exception as e:
    logging.warning(f"⚠️ Referee boost logic failed: {e}")
```

**Perché qui?**
- Dopo "Programmatic Market Veto" → pattern esistente da seguire
- Prima di costruire il NewsLog → può modificare verdict, recommended_market
- Ha accesso a tutte le variabili necessarie (referee_info, verdict, recommended_market, tactical_context)

---

### STEP #3: Estendere Referee Influence ad Altri Mercati

**File:** [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Posizione:** Dopo STEP #2 (Referee Boost Logic)

**Codice da Aggiungere:**
```python
# V9.1: REFEREE INFLUENCE ON OTHER MARKETS
# Extend referee influence to Goals, Corners, Winner markets
try:
    if referee_info and isinstance(referee_info, RefereeStats):
        boost_multiplier = referee_info.get_boost_multiplier()
        
        # Goals Market: Strict referee → More cards → More stoppages → Fewer goals
        if (recommended_market and "goal" in recommended_market.lower()):
            if referee_info.is_strict():
                # Strict referee → Reduce confidence for Over Goals
                if "over" in recommended_market.lower():
                    confidence = max(50, confidence - 15 * (boost_multiplier - 1.0))
                    reasoning = (
                        f"⚖️ REFEREE IMPACT: Arbitro severo ({referee_info.cards_per_game:.1f} cards/game) "
                        f"→ ridotta confidenza Over Goals (più interruzioni)\n\n{reasoning}"
                    )
        
        # Corners Market: Strict referee → More fouls → More corners
        elif (recommended_market and "corner" in recommended_market.lower()):
            if referee_info.is_strict():
                # Strict referee → Increase confidence for Over Corners
                if "over" in recommended_market.lower():
                    confidence = min(95, confidence + 10 * (boost_multiplier - 1.0))
                    reasoning = (
                        f"⚖️ REFEREE IMPACT: Arbitro severo ({referee_info.cards_per_game:.1f} cards/game) "
                        f"→ aumentata confidenza Over Corners (più falli)\n\n{reasoning}"
                    )
        
        # Winner Market: Strict referee → More unpredictable
        elif (recommended_market and recommended_market in ["1", "X", "2", "1X", "X2", "12"]):
            if referee_info.is_strict():
                # Strict referee → Slightly reduce confidence (more unpredictable)
                confidence = max(50, confidence - 5 * (boost_multiplier - 1.0))
                reasoning = (
                    f"⚖️ REFEREE IMPACT: Arbitro severo ({referee_info.cards_per_game:.1f} cards/game) "
                    f"→ leggermente ridotta confidenza (più imprevedibile)\n\n{reasoning}"
                )
except Exception as e:
    logging.warning(f"⚠️ Referee influence on other markets failed: {e}")
```

**Perché qui?**
- Dopo STEP #2 → può estendere la logica dell'arbitro
- Stesso pattern di STEP #2 → facile da mantenere
- Ha accesso a tutte le variabili necessarie

---

### STEP #4: Rendere Arbitro Obbligatorio per Cards Market

**File:** [`src/analysis/analyzer.py`](src/analysis/analyzer.py)

**Posizione:** Nel prompt AI `TRIANGULATION_SYSTEM_PROMPT` (linea 242-263)

**Modifiche al Prompt Esistente:**
```python
# Modifica la sezione "CARDS MARKET (V2.8 - REFEREE VETO SYSTEM)"

2. **CARDS MARKET (V9.0 - ENHANCED REFEREE SYSTEM):**
   
   **STEP 1: Check Referee Data Availability (HARD REQUIREMENT)**
   - If Referee Stats are UNKNOWN or MISSING → **SKIP Cards Market** (Reason: "Dati arbitro insufficienti")
   - Only proceed with Cards analysis if referee data is available
   
   **STEP 2: Check Referee Stats (HARD FILTER)**
   - If Referee Cards/Game < 3.5 → **VETO: FORBID Over Cards** (Reason: "Arbitro troppo permissivo")
   - If Referee Cards/Game >= 3.5 AND < 5.5 → Proceed to Step 3
   - If Referee Cards/Game >= 5.5 → **OVERRIDE: Suggest Over Cards** even without Derby context
   
   **STEP 3: Check Match Context (only if Referee allows)**
   - High Intensity Context: Derby, Rivalry, Relegation Battle, Title Decider
   - If High Intensity + Referee >= 3.5 → Suggest **OVER CARDS**
   - If BOTH teams Aggressive (Cards > 2.5) + Referee >= 3.5 → Suggest **OVER CARDS**
   
   **DECISION MATRIX:**
   | Referee Data | Referee Avg | Context | Decision |
   |--------------|-------------|---------|----------|
   | Unknown/Missing | Any | Any | ❌ SKIP - No Cards bet |
   | Available | < 3.5 | Any | ❌ VETO - No Cards bet |
   | Available | 3.5 - 5.5 | Derby/Aggressive | ✅ Over Cards |
   | Available | 3.5 - 5.5 | Normal | ❌ Skip Cards |
   | Available | > 5.5 | Any | ✅ Over Cards (Ref Override) |
```

**Perché qui?**
- Il prompt AI è il luogo naturale per definire i requisiti per il mercato Cards
- L'AI deve sapere che i dati dell'arbitro sono obbligatori
- Coerente con l'architettura esistente (il prompt guida le decisioni dell'AI)

---

### STEP #5: Implementare Cache per Statistiche Arbitro

**File:** Nuovo file `src/analysis/referee_cache.py`

**Codice da Creare:**
```python
"""
Referee Statistics Cache

Caches referee statistics to reduce dependency on external providers (Tavily/Perplexity).
Referee statistics change slowly, so a 7-day TTL is appropriate.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Cache file location
CACHE_DIR = Path("data/cache")
CACHE_FILE = CACHE_DIR / "referee_stats.json"

# TTL: 7 days (referee stats change slowly)
CACHE_TTL_DAYS = 7

class RefereeCache:
    """Cache for referee statistics."""
    
    def __init__(self, cache_file: Path = CACHE_FILE, ttl_days: int = CACHE_TTL_DAYS):
        self.cache_file = cache_file
        self.ttl_days = ttl_days
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> dict:
        """Load cache from file."""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load referee cache: {e}")
            return {}
    
    def _save_cache(self, cache: dict):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save referee cache: {e}")
    
    def get(self, referee_name: str) -> Optional[dict]:
        """
        Get referee stats from cache.
        
        Args:
            referee_name: Name of the referee
            
        Returns:
            Dict with referee stats or None if not found/expired
        """
        cache = self._load_cache()
        
        if referee_name not in cache:
            return None
        
        entry = cache[referee_name]
        
        # Check if entry is expired
        cached_at = entry.get("cached_at")
        if not cached_at:
            return None
        
        cached_date = datetime.fromisoformat(cached_at)
        expiry_date = cached_date + timedelta(days=self.ttl_days)
        
        if datetime.now() > expiry_date:
            logger.info(f"Referee cache expired for {referee_name}")
            return None
        
        logger.debug(f"Referee cache hit for {referee_name}")
        return entry.get("stats")
    
    def set(self, referee_name: str, stats: dict):
        """
        Set referee stats in cache.
        
        Args:
            referee_name: Name of the referee
            stats: Dict with referee stats (cards_per_game, strictness, etc.)
        """
        cache = self._load_cache()
        
        cache[referee_name] = {
            "cached_at": datetime.now().isoformat(),
            "stats": stats
        }
        
        self._save_cache(cache)
        logger.info(f"Referee cache updated for {referee_name}")
    
    def clear(self):
        """Clear all cache entries."""
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.info("Referee cache cleared")
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats (total_entries, expired_entries, etc.)
        """
        cache = self._load_cache()
        
        total_entries = len(cache)
        expired_entries = 0
        
        for entry in cache.values():
            cached_at = entry.get("cached_at")
            if cached_at:
                cached_date = datetime.fromisoformat(cached_at)
                expiry_date = cached_date + timedelta(days=self.ttl_days)
                if datetime.now() > expiry_date:
                    expired_entries += 1
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "valid_entries": total_entries - expired_entries
        }

# Global cache instance
_referee_cache = None

def get_referee_cache() -> RefereeCache:
    """Get global referee cache instance."""
    global _referee_cache
    if _referee_cache is None:
        _referee_cache = RefereeCache()
    return _referee_cache
```

**Integrazione in `verification_layer.py`:**

**Modifiche alla funzione `_parse_referee_stats()`:**
```python
def _parse_referee_stats(self, text: str, referee_name: str | None) -> RefereeStats | None:
    """
    Parse referee statistics from text with cache support.
    
    V7.2: Enhanced with referee cache to reduce external API calls.
    
    Args:
        text: Combined text from Tavily response
        referee_name: Known referee name (optional)
    
    Returns:
        RefereeStats or None if not found
    """
    import re
    from src.analysis.referee_cache import get_referee_cache
    
    # STEP 1: Try cache first
    if referee_name and referee_name.strip():
        cache = get_referee_cache()
        cached_stats = cache.get(referee_name)
        if cached_stats:
            # Return cached stats
            return RefereeStats(
                name=referee_name,
                cards_per_game=cached_stats.get("cards_per_game", 0.0),
                matches_officiated=cached_stats.get("matches_officiated", 0)
            )
    
    # STEP 2: Parse from text (cache miss)
    # ... (existing parsing logic) ...
    
    # STEP 3: Update cache if we found stats
    if referee_stats:
        cache = get_referee_cache()
        cache.set(referee_name or "Unknown", {
            "cards_per_game": referee_stats.cards_per_game,
            "strictness": referee_stats.strictness,
            "matches_officiated": referee_stats.matches_officiated
        })
    
    return referee_stats
```

**Perché qui?**
- Nuovo file dedicato → separazione delle responsabilità
- Facile da testare in isolamento
- Si integra facilmente con il codice esistente in `verification_layer.py`
- Riduce la dipendenza da provider esterni (obiettivo #4)

---

## 🧪 Piano di Test

### Test Unitari

#### Test #1: RefereeStats.should_boost_cards()
```python
def test_should_boost_cards():
    # Test strict referee
    ref = RefereeStats(name="Test Ref", cards_per_game=4.5, strictness="strict")
    assert ref.should_boost_cards() == True
    
    # Test lenient referee
    ref = RefereeStats(name="Test Ref", cards_per_game=2.5, strictness="lenient")
    assert ref.should_boost_cards() == False
    
    # Test average referee
    ref = RefereeStats(name="Test Ref", cards_per_game=4.0, strictness="average")
    assert ref.should_boost_cards() == False
```

#### Test #2: RefereeBoost Logic
```python
def test_referee_boost_no_bet_to_over():
    # Mock referee info
    referee_info = RefereeStats(name="Strict Ref", cards_per_game=4.5, strictness="strict")
    
    # Mock AI response
    verdict = "NO BET"
    recommended_market = "NONE"
    tactical_context = "High intensity derby"
    
    # Apply boost logic
    # ... (call boost logic) ...
    
    # Assert override happened
    assert verdict == "BET"
    assert recommended_market == "Over 3.5 Cards"
```

#### Test #3: RefereeCache
```python
def test_referee_cache():
    cache = RefereeCache()
    
    # Test cache miss
    assert cache.get("Unknown Ref") is None
    
    # Test cache set
    stats = {"cards_per_game": 4.5, "strictness": "strict"}
    cache.set("Test Ref", stats)
    
    # Test cache hit
    cached = cache.get("Test Ref")
    assert cached == stats
    
    # Test cache expiry (mock time)
    # ... (test expiry logic) ...
```

### Test di Integrazione

#### Test #4: End-to-End Referee Boost
```python
def test_e2e_referee_boost():
    # Setup: Create match with strict referee
    match = create_test_match(referee="Strict Ref", cards_avg=4.5)
    
    # Run analysis
    result = analysis_engine.analyze_match(match=match, ...)
    
    # Assert boost was applied
    assert "REFEREE BOOST" in result.reasoning
    assert result.recommended_market == "Over 3.5 Cards"
```

---

## 📊 Metriche di Successo

### Metriche Quantitative
1. **Cache Hit Rate**: Target >70% (riduce chiamate API esterne)
2. **Referee Boost Rate**: Target 10-15% delle raccomandazioni Cards
3. **Referee Veto Rate**: Target 5-10% delle raccomandazioni Cards
4. **Cards Market Accuracy**: Miglioramento del 5-10% rispetto a baseline

### Metriche Qualitative
1. **Transparency**: Tutte le modifiche dell'arbitro sono loggate e mostrate in reasoning
2. **Consistency**: La logica dell'arbitro è coerente tra AI e verification layer
3. **Maintainability**: Il codice è facile da testare e mantenere
4. **Performance**: Nessun impatto significativo sul tempo di analisi

---

## 🚀 Ordine di Implementazione Raccomandato

1. **STEP #1** (Estendere RefereeStats) - 2 ore
   - Priorità: Alta
   - Rischio: Basso
   - Dipendenze: Nessuna

2. **STEP #2** (Referee Boost Logic) - 4 ore
   - Priorità: CRITICA
   - Rischio: Medio
   - Dipendenze: STEP #1

3. **STEP #4** (Arbitro Obbligatorio) - 1 ora
   - Priorità: Alta
   - Rischio: Basso
   - Dipendenze: Nessuna

4. **STEP #3** (Estensione Altri Mercati) - 3 ore
   - Priorità: Media
   - Rischio: Medio
   - Dipendenze: STEP #2

5. **STEP #5** (Referee Cache) - 4 ore
   - Priorità: Alta
   - Rischio: Basso
   - Dipendenze: Nessuna

**Totale Stimato**: 14 ore di sviluppo

---

## ⚠️ Note Importanti

### 1. Compatibilità con Codice Esistente
- Tutte le modifiche sono **non-breaking**
- Il sistema di veto esistente rimane invariato
- Il boost è **additivo**, non sostituisce il veto

### 2. Logging e Monitoring
- Tutte le modifiche dell'arbitro devono essere loggate
- Aggiungere metriche per monitorare:
  - Cache hit rate
  - Referee boost rate
  - Referee veto rate

### 3. Testing
- Implementare test unitari per ogni nuova funzione
- Implementare test di integrazione per il flusso completo
- Testare con dati reali prima del deployment

### 4. Rollback Plan
- Se il boost causa problemi, può essere disabilitato con una feature flag
- La cache può essere disabilitata senza impattare il resto del sistema

---

## 📚 Riferimenti

### Documentazione Esistente
- [`plans/referee-intelligence-audit-report.md`](plans/referee-intelligence-audit-report.md) - Audit completo del sistema referee
- [`src/analysis/analyzer.py`](src/analysis/analyzer.py) - AI analysis system
- [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py) - Verification layer
- [`src/core/analysis_engine.py`](src/core/analysis_engine.py) - Analysis engine orchestration

### Pattern da Seguire
- Programmatic Market Veto ([`analyzer.py:2045-2065`](src/analysis/analyzer.py:2045-2065))
- Referee Veto System ([`analyzer.py:242-263`](src/analysis/analyzer.py:242-263))
- Cache Implementation (es. cache esistente per altri componenti)

---

## ✅ Checklist di Implementazione

- [ ] STEP #1: Estendere RefereeStats con metodi boost
- [ ] STEP #2: Implementare Referee Boost Logic in analyzer.py
- [ ] STEP #3: Estendere referee influence ad altri mercati
- [ ] STEP #4: Aggiornare prompt AI per rendere arbitro obbligatorio
- [ ] STEP #5: Implementare RefereeCache
- [ ] Integrare cache in verification_layer.py
- [ ] Scrivere test unitari per RefereeStats
- [ ] Scrivere test unitari per RefereeBoost Logic
- [ ] Scrivere test unitari per RefereeCache
- [ ] Scrivere test di integrazione end-to-end
- [ ] Aggiungere logging per monitorare boost/veto rate
- [ ] Aggiungere metriche per cache hit rate
- [ ] Testare con dati reali
- [ ] Documentare le modifiche
- [ ] Deploy in staging
- [ ] Monitorare per 1 settimana
- [ ] Deploy in produzione

---

**Fine del Documento**
