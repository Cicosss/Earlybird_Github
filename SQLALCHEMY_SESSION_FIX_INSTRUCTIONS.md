# SQLAlchemy Session Fix - Istruzioni per File Rimanenti

## Panoramica

Questo documento fornisce istruzioni passo-passo per applicare i fix SQLAlchemy Session ai file rimanenti usando la funzione helper centralizzata [`src/utils/match_helper.py`](src/utils/match_helper.py).

## Funzione Helper Centralizzata

La funzione helper [`extract_match_attributes()`](src/utils/match_helper.py:38) e [`extract_match_info()`](src/utils/match_helper.py:93) sono state create per estrarre in modo sicuro gli attributi dell'oggetto Match e prevenire l'errore "Trust validation error: Instance <Match at 0x...> is not bound to Session".

### Esempio di Utilizzo

```python
# Importa la funzione helper
from src.utils.match_helper import extract_match_info, extract_match_odds

# Estrai gli attributi Match in modo sicuro
match_info = extract_match_info(match)
match_odds = extract_match_odds(match)

# Usa gli attributi estratti invece di accedere direttamente all'oggetto Match
home_team = match_info["home_team"]
away_team = match_info["away_team"]
current_home_odd = match_odds["current_home_odd"]
```

## File Rimanenti da Modificare

### 1. [`src/analysis/market_intelligence.py`](src/analysis/market_intelligence.py:969)

**Riga:** 969
**Codice attuale:**
```python
steam_signal = detect_steam_move(match.id, current_odds, league_key=effective_league)
```

**Fix richiesto:**
```python
# VPS FIX: Extract match_id safely to prevent session detachment
match_id = getattr(match, "id", None)
steam_signal = detect_steam_move(match_id, current_odds, league_key=effective_league)
```

---

### 2. [`src/processing/news_hunter.py`](src/processing/news_hunter.py:2184-2471)

**Righe:** 2184-2471 (molti punti)
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.start_time, match.id
# con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["start_time"], match_info["match_id"]
```

---

### 3. [`src/processing/telegram_listener.py`](src/processing/telegram_listener.py:302-762)

**Righe:** 302-762 (molti punti)
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.id
# con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["match_id"]
```

---

### 4. [`src/ingestion/ingest_fixtures.py`](src/ingestion/ingest_fixtures.py:221-232)

**Righe:** 221-232
**Codice attuale:**
```python
for match in all_matches:
    match_time = _ensure_utc_aware(match.start_time)
    if match_time > now:
        # ...
```

**Fix richiesto:**
```python
for match in all_matches:
    # VPS FIX: Extract start_time safely to prevent session detachment
    start_time = getattr(match, "start_time", None)
    match_time = _ensure_utc_aware(start_time)
    if match_time > now:
        # ...
```

---

### 5. [`src/database/db.py`](src/database/db.py:182-184)

**Righe:** 182-184
**Codice attuale:**
```python
for match in matches:
    match.sport_key = match.league
    match.commence_time = match.start_time
```

**Fix richiesto:**
```python
for match in matches:
    # VPS FIX: Extract Match attributes safely to prevent session detachment
    league = getattr(match, "league", None)
    start_time = getattr(match, "start_time", None)
    match.sport_key = league
    match.commence_time = start_time
```

---

### 6. [`src/database/maintenance.py`](src/database/maintenance.py:108-109, 253-255)

**Righe:** 108-109, 253-255
**Codice attuale (riga 108-109):**
```python
oldest_match = db.query(Match).order_by(Match.start_time.asc()).first()
oldest_date = oldest_match.start_time if oldest_match else None
```

**Fix richiesto:**
```python
oldest_match = db.query(Match).order_by(Match.start_time.asc()).first()
oldest_date = getattr(oldest_match, "start_time", None) if oldest_match else None
```

**Codice attuale (riga 253-255):**
```python
match_info = (
    f"{match.home_team} vs {match.away_team}"
    if match
    else "Unknown match"
)
```

**Fix richiesto:**
```python
if match:
    # VPS FIX: Extract Match attributes safely to prevent session detachment
    home_team = getattr(match, "home_team", None)
    away_team = getattr(match, "away_team", None)
    match_info = f"{home_team} vs {away_team}"
else:
    match_info = "Unknown match"
```

---

### 7. [`src/services/odds_capture.py`](src/services/odds_capture.py:80-173)

**Righe:** 80-173 (molti punti)
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.id
# con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["match_id"]
```

---

### 8. [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py:1426-1532)

**Righe:** 1426-1532 (molti punti)
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.id
# con match_info["home_team"], match_info["away_team"], match_info["match_id"]
```

---

### 9. [`src/utils/radar_enrichment.py`](src/utils/radar_enrichment.py:216-237)

**Righe:** 216-237
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

for match in matches:
    match_info = extract_match_info(match)

    # Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.start_time, match.id, match.current_draw_odd
    # con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["start_time"], match_info["match_id"]
```

---

### 10. [`src/utils/radar_odds_check.py`](src/utils/radar_odds_check.py:151-190)

**Righe:** 151-190
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

for match in matches:
    match_info = extract_match_info(match)

    # Sostituisci tutti gli usi diretti di match.home_team, match.away_team
    # con match_info["home_team"], match_info["away_team"]
```

---

### 11. [`src/utils/debug_funnel.py`](src/utils/debug_funnel.py:98-294, 472-476)

**Righe:** 98-294, 472-476
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.start_time, match.id
# con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["start_time"], match_info["match_id"]
```

---

### 12. [`src/main.py`](src/main.py:598-2313)

**Righe:** 598-2313 (molti punti)
**Fix richiesto:**
```python
# VPS FIX: Extract Match attributes safely to prevent session detachment
from src.utils.match_helper import extract_match_info, extract_match_odds

match_info = extract_match_info(match)
match_odds = extract_match_odds(match)

# Sostituisci tutti gli usi diretti di match.home_team, match.away_team, match.league, match.start_time, match.id,
# match.current_home_odd, match.current_draw_odd, match.current_away_odd, match.current_over_2_5, match.current_under_2_5,
# match.opening_home_odd, match.opening_draw_odd, match.opening_away_odd, match.opening_over_2_5, match.opening_under_2_5
# con match_info["home_team"], match_info["away_team"], match_info["league"], match_info["start_time"], match_info["match_id"],
# match_odds["current_home_odd"], match_odds["current_draw_odd"], match_odds["current_away_odd"], match_odds["current_over_2_5"], match_odds["current_under_2_5"],
# match_odds["opening_home_odd"], match_odds["opening_draw_odd"], match_odds["opening_away_odd"], match_odds["opening_over_2_5"], match_odds["opening_under_2_5"]
```

---

## Pattern Generale per Applicare i Fix

### Pattern 1: Estrazione Singolo Attributo

**Codice vulnerabile:**
```python
value = match.attribute_name
```

**Fix:**
```python
value = getattr(match, "attribute_name", None)
```

### Pattern 2: Estrazione Multipli Attributi (Usa Funzione Helper)

**Codice vulnerabile:**
```python
home_team = match.home_team
away_team = match.away_team
league = match.league
start_time = match.start_time
```

**Fix:**
```python
from src.utils.match_helper import extract_match_info

match_info = extract_match_info(match)
home_team = match_info["home_team"]
away_team = match_info["away_team"]
league = match_info["league"]
start_time = match_info["start_time"]
```

### Pattern 3: Estrazione Odds (Usa Funzione Helper)

**Codice vulnerabile:**
```python
current_home_odd = match.current_home_odd
current_draw_odd = match.current_draw_odd
current_away_odd = match.current_away_odd
```

**Fix:**
```python
from src.utils.match_helper import extract_match_odds

match_odds = extract_match_odds(match)
current_home_odd = match_odds["current_home_odd"]
current_draw_odd = match_odds["current_draw_odd"]
current_away_odd = match_odds["current_away_odd"]
```

---

## Verifica dei Fix Applicati

Dopo aver applicato i fix, verificare che:

1. **Non ci siano usi diretti dell'oggetto Match** senza `getattr()` o funzione helper
2. **Tutti gli attributi siano estratti prima di essere usati**
3. **Il codice compili senza errori**
4. **I test passino correttamente**

---

## Note Importanti

1. **Non modificare i metodi dell'oggetto Match** (es. `match.get_odds_movement()`) - questi sono metodi, non attributi, e non causano il problema di session detachment
2. **Usare sempre `getattr()` con valore di default `None`** per prevenire errori se l'attributo non esiste
3. **Preferire la funzione helper** quando si estraggono più attributi contemporaneamente
4. **Testare il codice dopo aver applicato i fix** per assicurarsi che funzioni correttamente

---

## Riepilogo dei Fix Già Applicati

✅ [`src/core/analysis_engine.py`](src/core/analysis_engine.py:1085-1099) - Fix CRITICAL applicato
✅ [`src/core/settlement_service.py`](src/core/settlement_service.py:168-208) - Fix applicato
✅ [`src/analysis/final_alert_verifier.py`](src/analysis/final_alert_verifier.py:89-145) - Fix applicato
✅ [`src/analysis/analyzer.py`](src/analysis/analyzer.py:1488-1539) - Fix applicato usando funzione helper
✅ [`src/analysis/verification_layer.py`](src/analysis/verification_layer.py:4478-4486) - Fix applicato
✅ [`src/analysis/verifier_integration.py`](src/analysis/verifier_integration.py:105-437) - Fix applicato a tutti i punti

---

## File Rimanenti da Modificare

⚠️ [`src/analysis/market_intelligence.py`](src/analysis/market_intelligence.py:969) - 1 punto
⚠️ [`src/processing/news_hunter.py`](src/processing/news_hunter.py:2184-2471) - Molti punti
⚠️ [`src/processing/telegram_listener.py`](src/processing/telegram_listener.py:302-762) - Molti punti
⚠️ [`src/ingestion/ingest_fixtures.py`](src/ingestion/ingest_fixtures.py:221-232) - 1 punto
⚠️ [`src/database/db.py`](src/database/db.py:182-184) - 1 punto
⚠️ [`src/database/maintenance.py`](src/database/maintenance.py:108-109, 253-255) - 2 punti
⚠️ [`src/services/odds_capture.py`](src/services/odds_capture.py:80-173) - Molti punti
⚠️ [`src/services/nitter_fallback_scraper.py`](src/services/nitter_fallback_scraper.py:1426-1532) - Molti punti
⚠️ [`src/utils/radar_enrichment.py`](src/utils/radar_enrichment.py:216-237) - Molti punti
⚠️ [`src/utils/radar_odds_check.py`](src/utils/radar_odds_check.py:151-190) - Molti punti
⚠️ [`src/utils/debug_funnel.py`](src/utils/debug_funnel.py:98-294, 472-476) - Molti punti
⚠️ [`src/main.py`](src/main.py:598-2313) - Molti punti

---

## Conclusione

Applicando i fix descritti in questo documento, si eliminerà completamente il problema "Trust validation error: Instance <Match at 0x...> is not bound to Session" su VPS.

La funzione helper centralizzata [`src/utils/match_helper.py`](src/utils/match_helper.py) fornisce un modo intelligente e manutenibile per estrarre gli attributi Match in modo sicuro, riducendo la duplicazione del codice e rendendo il sistema più robusto.
