# 📋 REPORT: Score-Delta Deduplication - Implementazione Proposta

## Analisi del CRITICAL #5: Deduplication Flags

### Situazione Attuale

Il campo `highest_score_sent` nella tabella `matches` è **CODICE MAI IMPLEMENTATO** per la deduplicazione:
- È dichiarato in `src/database/models.py` con commento "Highest score already alerted for this match"
- È usato SOLO nei settlement services per filtrare match (non per deduplicazione alert)
- **NON viene MAI scritto** quando un alert viene inviato
- **NON viene MAI letto** prima di inviare un nuovo alert

**Nota:** Il campo È usato nel settlement service per determinare quali match includere nei calcoli CLV, ma non per la deduplicazione degli alert come originariamente inteso.

---

## Flusso Attuale degli Alert

```
Analysis Engine (analysis_engine.py:1618-1676)
    ↓
send_alert_wrapper() → send_alert()
    ↓
notifier.py:1378-1388 → UPDATE matches SET odds_alert_sent = 1, last_alert_time = ...
```

**Il problema:** L'`UPDATE` imposta solo `odds_alert_sent = 1` e `last_alert_time`, **MAI** `highest_score_sent`.

---

## Design Proposto: Score-Delta Deduplication Service

### Concetto

Un componente intelligente che implementa la logica:
> "Se abbiamo già inviato un alert con score X per questo match, non inviarne uno con score inferiore. Ma se lo score è significativamente più alto (>1.0 punto), invialo comunque come 'update'."

### Componenti da Modificare

#### 1. Nuovo Componente: `ScoreDeltaDeduplicator`

**File:** `src/alerting/score_delta_deduplicator.py` (nuovo file)

```python
class ScoreDeltaDeduplicator:
    """
    Score-Delta Deduplication Service
    
    Implements intelligent deduplication based on score improvement:
    - If new_score > highest_sent_score + DELTA_THRESHOLD (1.0): Allow alert (update)
    - If new_score <= highest_sent_score: Block as duplicate
    - If DELTA_THRESHOLD > new_score > highest_sent_score: Use existing boolean flags
    
    V14.0: This component was designed but never implemented.
    """
    
    DELTA_THRESHOLD = 1.0  # Minimum score improvement to trigger new alert
    
    def should_send_alert(self, match_id: int, new_score: float, db_session) -> tuple[bool, str]:
        """
        Check if alert should be sent based on score improvement.
        
        Returns:
            tuple: (should_send: bool, reason: str)
        """
        # Read highest_score_sent from match
        # Compare with new_score
        # Return decision with reason
```

#### 2. Modifiche a `notifier.py`

**Punto di integrazione:** Dopo la creazione dell'`EnhancedMatchAlert` ma prima dell'invio a Telegram

```python
# In send_alert_wrapper() - after line 1126
# Check score-delta deduplication BEFORE sending
if alert is not None:
    from src.alerting.score_delta_deduplicator import ScoreDeltaDeduplicator
    deduplicator = ScoreDeltaDeduplicator()
    
    should_send, reason = deduplicator.should_send_alert(
        match_id=getattr(alert.analysis_result, 'match_id', None),
        new_score=alert.score,
        db_session=alert.db_session
    )
    
    if not should_send:
        logger.info(f"🚫 SCORE-DELTA DEDUP: Blocking alert - {reason}")
        return False
```

#### 3. Modifiche a `notifier.py` - UPDATE esistente

**Punto di integrazione:** Dopo l'invio riuscito dell'alert (linea 1378-1391)

```python
# Aggiungere highest_score_sent all'UPDATE esistente
UPDATE matches
SET odds_alert_sent = 1,
    last_alert_time = :alert_time,
    highest_score_sent = :new_score  # <-- AGGIUNGERE
WHERE id = :id
```

---

## Analisi Benefit/Rischio

### ✅ Benefici

1. **Meno alert spam**: Non invia alert ridondanti se lo score cala
2. **Più alert quality**: Solo alert con score significativamente migliorato triggherano nuove notifiche
3. **Backwards compatible**: I flags booleani esistenti continuano a funzionare come fallback
4. **Transparency**: Log dettagliati spiegano perché un alert è stato bloccato

### ⚠️ Rischi

1. **Behavioral change**: Potrebbe bloccare alert che l'utente si aspetterebbe di ricevere
2. **Edge cases**: 
   - Match con multiple news in sequenza rapida (score oscilla 8.0 → 7.5 → 8.2)
   - Situazioni dove il calo di score è dovuto a fattori esterni (odds movement) non a qualità della news
3. **Complexity**: Aggiunge un nuovo componente da manutenere

### 🔧 Mitigazioni

1. **DELTA_THRESHOLD = 1.0**: Permette piccole fluttuazioni senza bloccare
2. **Logging dettagliato**: Ogni decisione documentata
3. **Flag esistenti**: Boolean flags come fallback se score-delta logic fails
4. **Configurabile**: Threshold reso configurable per future tuning

---

## Stima Codice

| Componente | Linee | Complessità |
|------------|-------|-------------|
| Nuovo file `score_delta_deduplicator.py` | ~100 | Media |
| Modifiche a `notifier.py` (integrazione) | ~30 | Bassa |
| Modifiche a `notifier.py` (UPDATE query) | ~5 | Bassa |
| Modifiche a `send_alert_wrapper()` | ~15 | Bassa |
| **Totale** | **~150** | - |

---

## Raccomandazione

**Priorità:** MEDIUM (non urgentissimo)

**Motivazione:**
1. I meccanismi di deduplicazione esistenti funzionano correttamente
2. Questo è un miglioramento di "quality of life", non un bug critico
3. L'implementazione richiede test accurati per validare il behavioral change
4. Rischio di introdurre regressioni se non testato bene

**Se implementato:** Suggerisco di renderlo **opt-in** con feature flag:
```python
SCORE_DELTA_DEDUP_ENABLED = os.getenv("SCORE_DELTA_DEDUP_ENABLED", "false").lower() == "true"
```

---

## Alternativa: Rimuovere il Dead Code

Se il team decide che la score-delta deduplication non è necessaria,可以考虑 rimuovere il campo `highest_score_sent` dalla tabella e dai commenti per evitare confusione futura.

Questa è un'altra opzione valida dato che il campo è mai stato implementato e i meccanismi booleani funzionano.

---

## Ulteriori Investigazioni Future

1. **Valutare se il campo `highest_score_sent` ha senso per il settlement service**: Attualmente il settlement service lo usa per filtrare i match da processare. Ha senso questo uso?
2. **Valutare se serve davvero la score-delta deduplication**: I flag booleani attuali funzionano. La complexity aggiunta vale il beneficio?
3. **Considerare una soluzione ibrida**: Usare il campo solo per logging/tracciamento senza bloccare gli alert.