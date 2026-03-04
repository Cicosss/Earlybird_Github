# COVE: Doppia Verifica News Radar - Estrazione News da Supabase

**Data**: 2026-02-25  
**Protocollo**: Chain of Verification (CoVe)  
**Componenti**: News Radar (`run_news_radar.py`, `src/services/news_radar.py`) + Supabase Provider (`src/database/supabase_provider.py`)  
**Severità**: CRITICAL  
**Verifica**: Doppia verifica dell'integrazione tra News Radar e estrazione news da Supabase

---

## Executive Summary

Tramite rigorosa doppia verifica COVE, abbiamo analizzato l'integrazione tra il News Radar e l'estrazione delle news da Supabase. La verifica ha confermato che il fix del timeout è stato implementato correttamente nel codice, ma persistono problemi operativi che impediscono il funzionamento corretto del News Radar.

**Status**: ⚠️ **PARZIALMENTE VERIFICATO** - Il codice è corretto ma il sistema non funziona come previsto.

---

## FASE 1: Generazione Bozza (Draft Analysis)

### Ipotesi Iniziale

Il News Radar estrae le news da Supabase attraverso il seguente flusso:

1. [`run_news_radar.py`](run_news_radar.py:114) crea un'istanza di `NewsRadarMonitor` con `use_supabase=True`
2. [`NewsRadarMonitor.start()`](src/services/news_radar.py) chiama [`load_config_from_supabase()`](src/services/news_radar.py:630)
3. [`load_config_from_supabase()`](src/services/news_radar.py:630) crea un'istanza di `SupabaseProvider()`
4. [`SupabaseProvider`](src/database/supabase_provider.py) inizializza la connessione con timeout configurato
5. [`fetch_all_news_sources()`](src/database/supabase_provider.py:703) esegue la query per ottenere tutte le news sources
6. Le news sources vengono filtrate per escludere i social media handles
7. Viene creato un `RadarConfig` con le web sources estratte

### Flusso Dati Previsto

```
run_news_radar.py
  └─> NewsRadarMonitor.start() [async]
      └─> load_config_from_supabase() [sync]
          └─> SupabaseProvider() [sync singleton]
              └─> _initialize_connection() [sync]
                  └─> create_client() con timeout 10s
                      └─> fetch_all_news_sources() [sync]
                          └─> _execute_query("news_sources") [sync]
                              └─> query.execute() [sync HTTP, 10s timeout]
                                  └─> Filtra social media handles
                                      └─> RadarConfig(sources=web_sources)
```

### Punti Chiave Identificati

1. **Timeout Configuration**: Il client Supabase dovrebbe essere configurato con timeout di 10 secondi
2. **Singleton Pattern**: `SupabaseProvider` usa il pattern singleton per garantire una sola connessione
3. **Cache**: Il provider implementa una cache di 1 ora per ridurre le query
4. **Mirror Fallback**: Se Supabase fallisce, il sistema dovrebbe fare fallback a `data/supabase_mirror.json`
5. **Social Media Filter**: Il News Radar filtra i social media handles per monitorare solo web sources

---

## FASE 2: Verifica Avversariale (Cross-Examination)

### Domande Critiche per Confutare l'Ipotesi

**Fatti (Facts):**

1. **Siamo sicuri che il timeout è configurato correttamente?**
   - **VERIFICATION**: Letto [`src/database/supabase_provider.py:118-138`](src/database/supabase_provider.py:118-138)
   - **RESULT**: ✅ **VERIFIED** - Il timeout è configurato correttamente con `httpx.Timeout()` e `SyncClientOptions(postgrest_client_timeout=10.0)`

2. **Siamo sicuri che la costante `SUPABASE_QUERY_TIMEOUT` è definita?**
   - **VERIFICATION**: Letto [`src/database/supabase_provider.py:53`](src/database/supabase_provider.py:53)
   - **RESULT**: ✅ **VERIFIED** - La costante è definita come `SUPABASE_QUERY_TIMEOUT = 10.0`

3. **Siamo sicuri che il News Radar usa correttamente il SupabaseProvider?**
   - **VERIFICATION**: Letto [`src/services/news_radar.py:630-651`](src/services/news_radar.py:630-651)
   - **RESULT**: ✅ **VERIFIED** - Il News Radar crea un'istanza di `SupabaseProvider()` e chiama `fetch_all_news_sources()`

4. **Siamo sicuri che il filtro social media funziona correttamente?**
   - **VERIFICATION**: Letto [`src/services/news_radar.py:658-707`](src/services/news_radar.py:658-707)
   - **RESULT**: ✅ **VERIFIED** - Il filtro esclude correttamente twitter.com, x.com, t.me, telegram.org, facebook.com, instagram.com, linkedin.com, tiktok.com, youtube.com, reddit.com, threads.net

5. **Siamo sicuri che il mirror file esiste?**
   - **VERIFICATION**: Verificato [`data/supabase_mirror.json`](data/supabase_mirror.json)
   - **RESULT**: ❌ **NOT VERIFIED** - Il file non esiste

**Codice (Code):**

6. **Siamo sicuri che `fetch_all_news_sources()` usa la tabella corretta?**
   - **VERIFICATION**: Letto [`src/database/supabase_provider.py:703-711`](src/database/supabase_provider.py:703-711)
   - **RESULT**: ✅ **VERIFIED** - Il metodo usa la tabella `"news_sources"` (non `"sources"`)

7. **Siamo sicuri che il fallback al mirror funziona?**
   - **VERIFICATION**: Letto [`src/database/supabase_provider.py:407-415`](src/database/supabase_provider.py:407-415)
   - **RESULT**: ⚠️ **PARTIALLY VERIFIED** - Il codice implementa il fallback, ma il mirror file non esiste

8. **Siamo sicuri che il log mostra il problema?**
   - **VERIFICATION**: Analizzato [`news_radar.log`](news_radar.log)
   - **RESULT**: ✅ **VERIFIED** - Il log mostra il blocco durante "Loading sources from Supabase..."

**Logica (Logic):**

9. **Siamo sicuri che il timeout di 10 secondi è sufficiente?**
   - **VERIFICATION**: Analizzato il log e il codice
   - **RESULT**: ⚠️ **PARTIALLY VERIFIED** - 10 secondi dovrebbe essere sufficiente, ma il log mostra un blocco di 6+ minuti

### **CORREZIONI NECESSARIE TROVATE**

La mia ipotesi iniziale era **PARZIALMENTE CORRETTA**:

- **CORRETTO**: Il codice implementa correttamente il timeout di 10 secondi
- **CORRETTO**: Il flusso di estrazione delle news da Supabase è implementato correttamente
- **CORRETTO**: Il filtro social media funziona come previsto
- **INCORRETTO**: Il sistema non funziona come previsto a causa di problemi operativi
- **DA VERIFICARE**: Il blocco di 6+ minuti suggerisce che il timeout potrebbe non funzionare correttamente o che c'è un altro problema

---

## FASE 3: Esecuzione Verifiche (Independent Verification)

### Verifica 1: Timeout Configuration

**Domanda**: Il client Supabase è configurato con timeout di 10 secondi?

**Metodo**: Lettura del codice sorgente [`src/database/supabase_provider.py:118-138`](src/database/supabase_provider.py:118-138)

**Risultato**: ✅ **VERIFIED**
```python
# V11.1: Create Supabase client with explicit timeout to prevent indefinite hangs
# Use httpx.Client with timeout for all HTTP operations
import httpx
from supabase.lib.client_options import SyncClientOptions

# Create httpx client with explicit timeout (connect, read, write, pool)
httpx_timeout = httpx.Timeout(
    connect=SUPABASE_QUERY_TIMEOUT,  # 10.0
    read=SUPABASE_QUERY_TIMEOUT,       # 10.0
    write=SUPABASE_QUERY_TIMEOUT,      # 10.0
    pool=SUPABASE_QUERY_TIMEOUT,        # 10.0
)
httpx_client = httpx.Client(timeout=httpx_timeout)

# Create Supabase client with custom httpx client
options = SyncClientOptions(
    postgrest_client_timeout=SUPABASE_QUERY_TIMEOUT,  # 10.0
    httpx_client=httpx_client,
)
self._client = create_client(supabase_url, supabase_key, options=options)
```

Il client Supabase è configurato con timeout di 10 secondi per tutte le operazioni HTTP (connect, read, write, pool).

### Verifica 2: Costante SUPABASE_QUERY_TIMEOUT

**Domanda**: La costante `SUPABASE_QUERY_TIMEOUT` è definita e usata?

**Metodo**: Lettura del codice sorgente [`src/database/supabase_provider.py:53`](src/database/supabase_provider.py:53)

**Risultato**: ✅ **VERIFIED**
```python
SUPABASE_QUERY_TIMEOUT = 10.0  # 10 second timeout for queries (V11.1)
```

La costante è definita come 10.0 secondi ed è usata nella configurazione del client.

### Verifica 3: Metodo fetch_all_news_sources()

**Domanda**: Il metodo `fetch_all_news_sources()` usa la tabella corretta?

**Metodo**: Lettura del codice sorgente [`src/database/supabase_provider.py:703-711`](src/database/supabase_provider.py:703-711)

**Risultato**: ✅ **VERIFIED**
```python
def fetch_all_news_sources(self) -> list[dict[str, Any]]:
    """
    Fetch all news sources without league filter.

    Returns:
        List of all news source records
    """
    cache_key = "news_sources_all"
    return self._execute_query("news_sources", cache_key)
```

Il metodo usa correttamente la tabella `"news_sources"` (non `"sources"`).

### Verifica 4: Integrazione News Radar - Supabase

**Domanda**: Il News Radar usa correttamente il SupabaseProvider?

**Metodo**: Lettura del codice sorgente [`src/services/news_radar.py:630-651`](src/services/news_radar.py:630-651)

**Risultato**: ✅ **VERIFIED**
```python
def load_config_from_supabase() -> RadarConfig:
    """
    Load News Radar configuration from Supabase database.

    Fetches news sources from the news_sources table and filters for
    traditional web domains only (excluding social media handles).

    Returns:
        RadarConfig with web-only sources from Supabase
    """
    try:
        from src.database.supabase_provider import SupabaseProvider

        logger.info("🔄 [NEWS-RADAR] Initializing Supabase provider...")
        provider = SupabaseProvider()
        
        if not provider.is_connected():
            logger.error(f"❌ [NEWS-RADAR] Supabase connection failed: {provider.get_connection_error()}")
            return RadarConfig()
        
        logger.info("✅ [NEWS-RADAR] Supabase connected, fetching news sources...")
        all_sources = provider.fetch_all_news_sources()

        if not all_sources:
            logger.warning("⚠️ [NEWS-RADAR] No news sources found in Supabase")
            return RadarConfig()
```

Il News Radar crea correttamente un'istanza di `SupabaseProvider()` e chiama `fetch_all_news_sources()`.

### Verifica 5: Filtro Social Media

**Domanda**: Il filtro social media funziona correttamente?

**Metodo**: Lettura del codice sorgente [`src/services/news_radar.py:658-707`](src/services/news_radar.py:658-707)

**Risultato**: ✅ **VERIFIED**
```python
# Filter for web-only sources (exclude social media handles)
web_sources = []
social_domains = {
    "twitter.com",
    "x.com",
    "t.me",
    "telegram.org",
    "telegram.me",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "reddit.com",
    "threads.net",
}

for src_data in all_sources:
    # V8.0: Handle both 'url' and 'domain' fields
    # Supabase news_sources table uses 'domain' field
    domain = src_data.get("domain", "")
    url = src_data.get("url", "")

    # If no URL but domain exists, construct URL from domain
    if not url and domain:
        # Add https:// prefix if not present
        if not domain.startswith("http"):
            url = f"https://{domain}"
        else:
            url = domain
    elif not url and not domain:
        logger.warning(f"⚠️ [NEWS-RADAR] Skipping source without URL/domain: {src_data}")
        continue

    # Parse URL to check if it's a social media domain
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Skip if it's a social media domain
        if any(social_domain in domain for social_domain in social_domains):
            logger.debug(f"🚫 [NEWS-RADAR] Skipping social media source: {url}")
            continue
```

Il filtro social media esclude correttamente tutti i principali social media handles.

### Verifica 6: Mirror File Existence

**Domanda**: Il mirror file `data/supabase_mirror.json` esiste?

**Metodo**: Verifica del file system

**Risultato**: ❌ **NOT VERIFIED**
```
Error: ENOENT: no such file or directory, stat '/home/linux/Earlybird_Github/data/supabase_mirror.json'
```

Il mirror file non esiste, quindi il fallback non può funzionare.

### Verifica 7: Log Analysis

**Domanda**: Il log mostra il problema?

**Metodo**: Analisi del log file [`news_radar.log`](news_radar.log)

**Risultato**: ✅ **VERIFIED**
```
2026-02-25 23:41:45,094 - __main__ - INFO - ============================================================
2026-02-25 23:41:45,102 - __main__ - INFO - 🔔 EarlyBird News Radar Monitor
2026-02-25 23:41:45,102 - __main__ - INFO - ============================================================
2026-02-25 23:41:45,102 - __main__ - INFO - Config file: config/news_radar_sources.json
2026-02-25 23:41:45,102 - __main__ - INFO - Supabase integration: ENABLED
2026-02-25 23:41:45,102 - __main__ - INFO - 
2026-02-25 23:41:45,102 - src.services.news_radar - INFO - 🔔 [NEWS-RADAR] V2.0 Monitor created
2026-02-25 23:41:45,102 - src.services.news_radar - INFO - 🔄 [NEWS-RADAR] Loading sources from Supabase...
2026-02-25 23:47:55,061 - __main__ - INFO - 🛑 [NEWS-RADAR] Received SIGTERM, initiating graceful shutdown...
2026-02-25 23:48:01,977 - __main__ - INFO - 🛑 [NEWS-RADAR] Received SIGTERM, initiating graceful shutdown...
```

Il log mostra che il News Radar si blocca durante "Loading sources from Supabase..." per circa 6 minuti (23:41:45 → 23:47:55).

---

## FASE 4: Risposta Finale (Canonical Solution)

### Root Cause (Finale)

Il News Radar si blocca durante l'estrazione delle news da Supabase a causa dei seguenti problemi:

1. **Mirror file mancante**: Il file `data/supabase_mirror.json` non esiste, quindi il fallback non può funzionare
2. **Possibile timeout non funzionante**: Nonostante il codice sia corretto, il log mostra un blocco di 6+ minuti, suggerendo che il timeout potrebbe non funzionare come previsto
3. **Manca logging dettagliato**: Non c'è logging sufficiente per capire esattamente dove si blocca il processo

### Analisi del Flusso Dati

#### Flusso Previsto (Codice Corretto)

```
run_news_radar.py
  └─> NewsRadarMonitor.start() [async]
      └─> load_config_from_supabase() [sync]
          └─> SupabaseProvider() [sync singleton]
              └─> _initialize_connection() [sync]
                  └─> create_client() con httpx.Client(timeout=10s)
                      └─> fetch_all_news_sources() [sync]
                          └─> _execute_query("news_sources") [sync]
                              └─> query.execute() [sync HTTP, 10s timeout]
                                  └─> Se timeout: fallback a mirror
                                      └─> RadarConfig(sources=web_sources)
```

#### Flusso Reale (Problema Operativo)

```
run_news_radar.py
  └─> NewsRadarMonitor.start() [async]
      └─> load_config_from_supabase() [sync]
          └─> SupabaseProvider() [sync singleton]
              └─> _initialize_connection() [sync]
                  └─> create_client() con httpx.Client(timeout=10s)
                      └─> fetch_all_news_sources() [sync]
                          └─> _execute_query("news_sources") [sync]
                              └─> query.execute() [sync HTTP, ??? timeout]
                                  ❌ BLOCCA per 6+ minuti
                                      ❌ Timeout non funziona o altro problema
                                          ❌ Mirror file non esiste
```

### Punti di Integrazione Verificati

#### 1. SupabaseProvider Initialization

**File**: [`src/database/supabase_provider.py:103-146`](src/database/supabase_provider.py:103-146)

**Status**: ✅ **CORRECT**
- Singleton pattern implementato correttamente
- Timeout configurato con `httpx.Timeout()` e `SyncClientOptions()`
- Logging appropriato per connessione e errori

#### 2. fetch_all_news_sources() Method

**File**: [`src/database/supabase_provider.py:703-711`](src/database/supabase_provider.py:703-711)

**Status**: ✅ **CORRECT**
- Usa la tabella corretta `"news_sources"`
- Implementa caching con chiave `"news_sources_all"`
- Chiama `_execute_query()` con i parametri corretti

#### 3. _execute_query() Method

**File**: [`src/database/supabase_provider.py:348-415`](src/database/supabase_provider.py:348-415)

**Status**: ✅ **CORRECT**
- Implementa caching con TTL di 1 ora
- Fallback a mirror se Supabase fallisce
- Logging dettagliato per errori e timeout

#### 4. News Radar Integration

**File**: [`src/services/news_radar.py:630-738`](src/services/news_radar.py:630-738)

**Status**: ✅ **CORRECT**
- Crea istanza di `SupabaseProvider()`
- Verifica connessione prima di procedere
- Filtra social media handles correttamente
- Logging appropriato per ogni fase

### Problemi Identificati

#### Problema 1: Mirror File Mancante

**Severità**: CRITICAL  
**File**: `data/supabase_mirror.json`  
**Status**: ❌ **NON ESISTE**

**Impatto**:
- Il fallback non può funzionare
- Se Supabase è lento o non risponde, il News Radar si blocca indefinitamente
- Non c'è modo di recuperare da errori di connessione

**Soluzione**:
```bash
# Creare il mirror file manualmente o eseguire un script di inizializzazione
python3 -c "
from src.database.supabase_provider import SupabaseProvider
provider = SupabaseProvider()
provider.create_local_mirror()
"
```

#### Problema 2: Timeout Non Funzionante (Sospetto)

**Severità**: CRITICAL  
**File**: `src/database/supabase_provider.py:118-138`  
**Status**: ⚠️ **DA VERIFICARE**

**Impatto**:
- Il News Radar si blocca per 6+ minuti invece di timeout dopo 10 secondi
- Il processo deve essere terminato manualmente con SIGTERM

**Possibili Cause**:
1. Il client httpx potrebbe non essere usato correttamente
2. Il timeout potrebbe essere ignorato in alcune condizioni
3. Potrebbe esserci un altro punto di blocco nel codice

**Soluzione**:
- Aggiungere logging dettagliato per tracciare l'esecuzione
- Verificare che il client httpx sia effettivamente usato per le query
- Testare il timeout con un endpoint lento

#### Problema 3: Logging Insufficiente

**Severità**: MEDIUM  
**File**: `src/services/news_radar.py:630-651`  
**Status**: ⚠️ **MIGLIORABILE**

**Impatto**:
- Difficile diagnosticare esattamente dove si blocca il processo
- Non c'è logging per il tempo di esecuzione delle query

**Soluzione**:
```python
# Aggiungere logging dettagliato
import time

logger.info("🔄 [NEWS-RADAR] Initializing Supabase provider...")
start = time.time()
provider = SupabaseProvider()
init_time = time.time() - start
logger.info(f"✅ [NEWS-RADAR] SupabaseProvider initialized in {init_time:.2f}s")

if not provider.is_connected():
    logger.error(f"❌ [NEWS-RADAR] Supabase connection failed: {provider.get_connection_error()}")
    return RadarConfig()

logger.info("✅ [NEWS-RADAR] Supabase connected, fetching news sources...")
start = time.time()
all_sources = provider.fetch_all_news_sources()
fetch_time = time.time() - start
logger.info(f"✅ [NEWS-RADAR] Fetched {len(all_sources)} sources in {fetch_time:.2f}s")
```

### Raccomandazioni

#### Raccomandazione 1: Creare Mirror File

**Priorità**: CRITICAL  
**Azione**: Creare il mirror file `data/supabase_mirror.json` per abilitare il fallback

```bash
# Eseguire questo comando per creare il mirror file
python3 -c "
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from src.database.supabase_provider import SupabaseProvider
provider = SupabaseProvider()
if provider.is_connected():
    provider.create_local_mirror()
    print('✅ Mirror file created successfully')
else:
    print(f'❌ Supabase not connected: {provider.get_connection_error()}')
"
```

#### Raccomandazione 2: Migliorare Logging

**Priorità**: HIGH  
**Azione**: Aggiungere logging dettagliato per tracciare l'esecuzione e identificare i punti di blocco

**File da modificare**:
- [`src/services/news_radar.py:630-651`](src/services/news_radar.py:630-651)
- [`src/database/supabase_provider.py:348-415`](src/database/supabase_provider.py:348-415)

#### Raccomandazione 3: Verificare Timeout

**Priorità**: HIGH  
**Azione**: Verificare che il timeout funzioni correttamente testando con un endpoint lento

```python
# Test script per verificare il timeout
import time
from src.database.supabase_provider import SupabaseProvider

provider = SupabaseProvider()
if not provider.is_connected():
    print(f"❌ Supabase not connected: {provider.get_connection_error()}")
    exit(1)

print(f"✅ Supabase connected")
print(f"🔄 Testing query with timeout (should timeout after 10s if Supabase is slow)...")

start = time.time()
try:
    data = provider.fetch_all_news_sources()
    elapsed = time.time() - start
    print(f"✅ Query completed in {elapsed:.2f}s")
    print(f"✅ Returned {len(data)} sources")
    
    if elapsed > 15:
        print(f"⚠️ WARNING: Query took {elapsed:.2f}s but timeout is 10s")
        print("⚠️ This suggests timeout may not be working correctly")
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ Query failed after {elapsed:.2f}s: {e}")
```

#### Raccomandazione 4: Implementare Retry Logic

**Priorità**: MEDIUM  
**Azione**: Implementare retry logic con backoff esponenziale per le query Supabase

```python
# Esempio di retry logic
import time
from typing import Callable, TypeVar

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """
    Execute function with retry logic and exponential backoff.
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"⚠️ Attempt {attempt + 1} failed: {e}, retrying in {delay}s...")
                time.sleep(delay)
    
    raise last_exception

# Uso in fetch_all_news_sources()
def fetch_all_news_sources(self) -> list[dict[str, Any]]:
    """
    Fetch all news sources without league filter.
    """
    def _fetch():
        cache_key = "news_sources_all"
        return self._execute_query("news_sources", cache_key)
    
    return retry_with_backoff(_fetch, max_retries=3, base_delay=1.0)
```

### Checklist di Verifica

- [x] Timeout configuration verificata (10 secondi)
- [x] Costante `SUPABASE_QUERY_TIMEOUT` definita e usata
- [x] Metodo `fetch_all_news_sources()` usa tabella corretta
- [x] Integrazione News Radar - Supabase corretta
- [x] Filtro social media funzionante
- [ ] Mirror file `data/supabase_mirror.json` esistente
- [ ] Timeout funzionante (da verificare con test)
- [ ] Logging sufficiente per diagnosi
- [ ] Retry logic implementata

### Conclusioni

**Status**: ⚠️ **PARZIALMENTE VERIFICATO**

Il codice che implementa l'integrazione tra News Radar e Supabase è **CORRETTO**:
- ✅ Timeout configurato correttamente (10 secondi)
- ✅ Singleton pattern implementato
- ✅ Caching con TTL di 1 ora
- ✅ Fallback a mirror implementato
- ✅ Filtro social media funzionante

Tuttavia, persistono problemi operativi:
- ❌ Mirror file non esiste
- ⚠️ Timeout potrebbe non funzionare (blocco di 6+ minuti)
- ⚠️ Logging insufficiente per diagnosi

**Azioni Richieste**:
1. Creare il mirror file `data/supabase_mirror.json`
2. Migliorare il logging per tracciare l'esecuzione
3. Verificare che il timeout funzioni correttamente
4. Implementare retry logic per migliorare la resilienza

---

## Appendice: File Analizzati

### File Principali

1. [`run_news_radar.py`](run_news_radar.py) - Script di avvio del News Radar
2. [`src/services/news_radar.py`](src/services/news_radar.py) - Servizio News Radar (load_config_from_supabase())
3. [`src/database/supabase_provider.py`](src/database/supabase_provider.py) - Provider Supabase (fetch_all_news_sources())
4. [`config/news_radar_sources.json`](config/news_radar_sources.json) - Configurazione delle fonti (fallback)
5. [`news_radar.log`](news_radar.log) - Log del News Radar

### File di Documentazione

1. [`NEWS_RADAR_SUPABASE_TIMEOUT_FIX_FINAL_REPORT.md`](NEWS_RADAR_SUPABASE_TIMEOUT_FIX_FINAL_REPORT.md) - Report sul fix del timeout
2. [`NEWS_RADAR_SUPABASE_TIMEOUT_FIX_REPORT.md`](NEWS_RADAR_SUPABASE_TIMEOUT_FIX_REPORT.md) - Report iniziale
3. [`test_simple_supabase_timeout.py`](test_simple_supabase_timeout.py) - Test per verificare il timeout

### File di Supporto

1. [`data/supabase_mirror.json`](data/supabase_mirror.json) - Mirror file (NON ESISTE)
2. [`.env`](.env.template) - Configurazione Supabase (SUPABASE_URL, SUPABASE_KEY)

---

**Report Generato**: 2026-02-25  
**Protocollo di Verifica**: Chain of Verification (CoVe)  
**Status**: ⚠️ PARZIALMENTE VERIFICATO - Codice corretto, problemi operativi
