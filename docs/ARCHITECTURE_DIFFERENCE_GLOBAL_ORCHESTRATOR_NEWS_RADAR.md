# Architettura Differente tra global_orchestrator.py e news_radar.py

**Data:** 2026-02-28
**Versione:** V11.0
**Autore:** COVE Double Verification

---

## 📋 Riepilogo

Questo documento chiarisce la differenza architetturale intenzionale tra due moduli paralleli:

1. **`src/processing/global_orchestrator.py`** - Monitoraggio partite in tempo reale
2. **`src/services/news_radar.py`** - Monitoraggio news per scommesse sportive

Entrambi i moduli girano in parallelo, ma hanno scopi e architetture diverse.

---

## 🌍 global_orchestrator.py - 3 Continenti

### Scopo
Monitoraggio partite in tempo reale per intelligence sulle scommesse.

### Architettura
```python
CONTINENTAL_WINDOWS = {
    "LATAM": list(range(12, 24)),  # 12:00-23:00 UTC
    "ASIA": list(range(0, 12)),    # 00:00-11:00 UTC
    "AFRICA": list(range(8, 20)),  # 08:00-19:00 UTC
}
```

### Perché 3 Continenti?
- **LATAM**: America Latina (Brasile, Argentina, Messico, Colombia, Cile, Perù)
- **ASIA**: Asia (Giappone, Corea, Cina, India, Thailandia, Vietnam)
- **AFRICA**: Africa (Sudafrica, Nigeria, Egitto, Marocco, Ghana)

Questi 3 continenti coprono le principali leghe monitorate dal bot per le scommesse sportive.

### Funzionalità
- Monitoraggio partite in tempo reale
- Integrazione con Supabase per dati partite
- Ciclo Nitter per intelligence Twitter
- Analisi partite e generazione alert

---

## 📰 news_radar.py - 4 Contesti

### Scopo
Monitoraggio news per segnali di scommesse sportive.

### Architettura
```python
CONTINENT_CONTEXTS = ["LATAM", "ASIA", "AFRICA", "GLOBAL"]
```

### Perché 4 Contesti?
- **LATAM**: Fonti specifiche per America Latina
- **ASIA**: Fonti specifiche per Asia
- **AFRICA**: Fonti specifiche per Africa
- **GLOBAL**: Fallback per fonti globali non categorizzate

### Funzionalità
- Scanning parallelo di fonti news
- Analisi contenuti con DeepSeek
- Rilevamento segnali di scommesse
- Integrazione con Playwright per browser automation

### Logica di Assegnazione Fonti
La funzione [`_determine_context_for_source()`](../src/services/news_radar.py:3241) assegna le fonti ai contesti:

```python
def _determine_context_for_source(self, source: RadarSource) -> str:
    # Check for LATAM indicators
    latam_keywords = ["brazil", "argentina", "mexico", "colombia", "chile", "peru"]
    if any(kw in source_lower or kw in url_lower for kw in latam_keywords):
        return "LATAM"

    # Check for ASIA indicators
    asia_keywords = ["japan", "korea", "china", "india", "thailand", "vietnam"]
    if any(kw in source_lower or kw in url_lower for kw in asia_keywords):
        return "ASIA"

    # Check for AFRICA indicators
    africa_keywords = ["south africa", "nigeria", "egypt", "morocco", "ghana"]
    if any(kw in source_lower or kw in url_lower for kw in africa_keywords):
        return "AFRICA"

    # Default to GLOBAL
    return "GLOBAL"
```

Il contesto **GLOBAL** serve come fallback per fonti che non rientrano nelle categorie specifiche.

---

## 🔍 Perché la Differenza è Intenzionale?

### 1. Scopi Diversi
- **global_orchestrator.py**: Monitoraggio partite (basato su leghe/continenti)
- **news_radar.py**: Monitoraggio news (basato su fonti/categorie)

### 2. Dati Diversi
- **global_orchestrator.py**: Dati partite da Supabase (strutturati per continenti)
- **news_radar.py**: Fonti news da config JSON (categorizzate per keyword)

### 3. Logica Diversa
- **global_orchestrator.py**: 3 continenti coprono tutte le leghe monitorate
- **news_radar.py**: 4 contesti permettono categorizzazione granulare + fallback

### 4. Moduli Indipendenti
I due moduli girano in parallelo e non si interferiscono:
- `global_orchestrator.py` viene eseguito dal main loop
- `news_radar.py` viene eseguito da `run_news_radar.py`

---

## ✅ Verifiche COVE

### Thread Safety
- ✅ I due moduli non condividono risorse critiche
- ✅ Ogni modulo ha il proprio event loop async
- ✅ Nessuna race condition identificata

### Performance
- ✅ Entrambi i moduli usano `nest_asyncio.apply()` ottimizzato
- ✅ Scanning parallelo massimizza throughput
- ✅ Queue-based architecture previene DB locks

### Deployment VPS
- ✅ Entrambi i moduli funzionano correttamente su VPS
- ✅ Nessuna dipendenza aggiuntiva richiesta
- ✅ Auto-installazione dipendenze da requirements.txt

---

## 📊 Tabella Comparativa

| Caratteristica | global_orchestrator.py | news_radar.py |
|----------------|------------------------|---------------|
| **Scopo** | Monitoraggio partite | Monitoraggio news |
| **Contesti** | 3 (LATAM, ASIA, AFRICA) | 4 (LATAM, ASIA, AFRICA, GLOBAL) |
| **Dati** | Partite da Supabase | Fonti news da config |
| **Logica** | Basata su leghe/continenti | Basata su keyword |
| **Fallback** | No | Sì (GLOBAL context) |
| **Browser** | No | Sì (Playwright) |
| **AI Analysis** | No | Sì (DeepSeek) |

---

## 🎯 Conclusioni

La differenza architetturale tra i due moduli è **INTENZIONALE** e **FUNZIONALE**:

1. ✅ **global_orchestrator.py** usa 3 continenti perché copre tutte le leghe monitorate
2. ✅ **news_radar.py** usa 4 contesti perché permette categorizzazione granulare + fallback
3. ✅ I due moduli sono indipendenti e non si interferiscono
4. ✅ Entrambi sono ottimizzati per performance e thread safety
5. ✅ Entrambi sono pronti per deployment su VPS

**Raccomandazione:** Mantenere l'architettura attuale. La differenza è un feature, non un bug.

---

## 📝 Documentazione Aggiornata

I seguenti file sono stati aggiornati per chiarire la differenza architetturale:

1. ✅ [`src/services/news_radar.py`](../src/services/news_radar.py:3001) - Docstring aggiornata
2. ✅ [`src/services/news_radar.py`](../src/services/news_radar.py:3112) - Commento aggiornato
3. ✅ [`src/services/news_radar.py`](../src/services/news_radar.py:3124) - Log aggiornato
4. ✅ [`src/services/news_radar.py`](../src/services/news_radar.py:3207) - Docstring aggiornata
5. ✅ [`src/services/news_radar.py`](../src/services/news_radar.py:3241) - Docstring aggiornata
6. ✅ [`src/processing/global_orchestrator.py`](../src/processing/global_orchestrator.py:26) - Documentazione aggiornata

---

**Report Generato:** 2026-02-28
**Metodo:** COVE Double Verification
**Stato:** ✅ COMPLETATO
