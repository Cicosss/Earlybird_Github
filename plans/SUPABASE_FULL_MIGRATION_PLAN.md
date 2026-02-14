# 🗄️ Piano di Architettura Ibrida: Supabase + SQLite
## EarlyBird V9.5 → V10.0

**Data**: 2026-02-11
**Stato**: AGGIORNATO CON ANALISI COVE (Chain of Verification)
**Autore**: Kilo Code (CoVe Mode)

---

## 🔍 ANALISI COVE - RISULTATI VERIFICA

### Stato Attuale del Database Supabase

**Tabelle Già Presenti (Intelligence & Configurazione):**
- ✅ `continents`: 3 records, 5 colonne (id, name, active_hours_utc, created_at, updated_at)
- ✅ `countries`: 28 records, 6 colonne (id, continent_id, name, iso_code, created_at, updated_at)
- ✅ `leagues`: 56 records, 8 colonne (id, country_id, api_key, tier_name, priority, is_active, created_at, updated_at)
- ✅ `news_sources`: 140 records, 7 colonne (id, league_id, domain, language_iso, is_active, created_at, updated_at)
- ✅ `social_sources`: 38 records, 9 colonne (id, league_id, platform, identifier, source_name, description, is_active, created_at, updated_at) [CORRETTO: 9 colonne, non 7]

### Database SQLite Locale (data/earlybird.db)

**Tabelle Attuali (Dati Operativi & Performance):**
| Tabella | Records | Descrizione |
|----------|----------|-------------|
| `matches` | 48 | Partite con quote e statistiche |
| `team_aliases` | 73 | Mappatura nomi squadre API → search (include twitter_handle) |
| `odds_snapshots` | 0 | Snapshot quote storiche |
| `news_logs` | 1 | Log analisi notizie |
| `telegram_channels` | 0 | Canali Telegram monitorati |
| `telegram_message_logs` | 0 | Log messaggi Telegram |

### Analisi Relazioni tra Tabelle (Foreign Keys)

**[VERIFICATO DIRETTAMENTE] Tutte le relazioni sono CORRETTE al 100%:**
- Continents (3) → Countries (28): **28/28 countries hanno un continent_id valido** ✅
- Countries (28) → Leagues (56): **56/56 leagues hanno un country_id valido** ✅
- Leagues (56) → News Sources (140): **140/140 news sources hanno un league_id valido** ✅
- Leagues (56) → Social Sources (38): **38/38 social sources hanno un league_id valido** ✅

**Conclusione:**
Il database Supabase è configurato correttamente. Tutte le relazioni tra tabelle sono state impostate correttamente tramite le foreign keys.

---

## 📐 ARCHITETTURA IBRIDA (MODELLO CORRETTO)

### Divisione Responsabilità Database

#### 🌐 SUPABASE = Intelligence & Configurazione

**Proposito**: Gestisce l'intelligence geografica e le fonti di dati ("Follow the Sun" strategy)

| Tabella | Records | Scopo | Stato |
|---------|---------|-------|-------|
| `continents` | 3 | Blocchi geografici (LATAM, ASIA, AFRICA) con `active_hours_utc` | ✅ PRESENTE |
| `countries` | 28 | Paesi collegati ai continenti | ✅ PRESENTE |
| `leagues` | 56 | Leghe con `api_key` per The-Odds-API e tiering (priority 1/2) | ✅ PRESENTE |
| `news_sources` | 140 | Domini per Brave/DDG search | ✅ PRESENTE |
| `social_sources` | 38 | Handle X per Nitter monitor | ✅ PRESENTE |

**Caratteristiche:**
- Read-heavy (lettura intensiva)
- Cached con TTL di 1 ora
- Fallback al mirror locale ([`data/supabase_mirror.json`](data/supabase_mirror.json:1))
- Gestito da [`ContinentalOrchestrator`](src/processing/continental_orchestrator.py:1-100)

#### 💾 SQLITE LOCALE = Dati Operativi & Performance

**Proposito**: Master per PnL, ROI tracking, Match History, e dati operativi

| Tabella | Records | Scopo | Stato |
|---------|---------|-------|-------|
| `matches` | 48 | Partite con quote e statistiche | ✅ RIMANE IN SQLITE |
| `news_logs` | 1 | Log analisi notizie | ✅ RIMANE IN SQLITE |
| `team_aliases` | 73 | Mappatura nomi squadre | ✅ RIMANE IN SQLITE |
| `odds_snapshots` | 0 | Snapshot quote storiche | ✅ RIMANE IN SQLITE |
| `telegram_channels` | 0 | Canali Telegram monitorati | ✅ RIMANE IN SQLITE |
| `telegram_message_logs` | 0 | Log messaggi Telegram | ✅ RIMANE IN SQLITE |

**Caratteristiche:**
- Write-heavy (scrittura intensiva)
- Performance ottimizzata per query locali
- Gestito da tutto il codice operativo (74 file usano `SessionLocal`)

---

## 🧠 Logica Operativa "Follow the Sun"

### Phase A: Trigger Geografico
- All'inizio di ogni ciclo di 6 ore, il bot controlla l'ora UTC corrente
- Interroga Supabase per trovare quali Continental Blocks sono "Active" (tramite `active_hours_utc`)
- **Esempio**: Se sono le 18:00 UTC, LATAM è attivo (12-23)

### Phase B: Ingestione Selettiva
- Il bot recupera fixtures e odds SOLO per le leghe dei continenti attivi
- Usa `api_key` dalla tabella `leagues` per interrogare The-Odds-API
- **Esempio**: `soccer_brazil_serie_b` → fetch odds da The-Odds-API

### Phase C: Maintenance Mode (04:00-06:00 UTC)
- Il bot entra in modalità manutenzione
- Salta l'ingestione delle partite
- Focus 100% su **Settlement** (calcolo risultati) e **Optimization** (ajustamento pesi)

### Phase D: Intelligence Injection
- Quando analizza una partita, il bot recupera da Supabase:
  - Domini specifici per costruire "Sniper Dorks" per Brave Search
  - Handle X per il feed RSS di Nitter (dalla tabella `social_sources`)
- **Bridge**: `api_key` collega "Intelligence" (News) → "Finance" (Odds)

---

## 🛡️ Resilienza & Persistenza

### The Mirror (`data/supabase_mirror.json`)
- Ad ogni sync riuscito, il bot aggiorna il mirror
- **Lifeboat**: Se Supabase è irraggiungibile, il bot usa il mirror per rimanere operativo
- Gestito da [`SupabaseProvider`](src/database/supabase_provider.py:1-1059)
- **⚠️ ATTENZIONE**: Il mirror attuale è obsoleto (timestamp: 2026-02-10T22:55:45) e manca `news_sources` e `social_sources`. Deve essere rigenerato dopo aver corretto i bug #1 e #2.

### Modello Ibrido Confermato
- **Supabase**: Intelligence/Config (read-heavy, cached) - continents, countries, leagues, news_sources, social_sources
- **SQLite**: Dati operativi (write-heavy, performance) - matches, news_logs, team_aliases, odds_snapshots, telegram_channels, telegram_message_logs

---

## 📋 Executive Summary

Questo documento descrive l'architettura ibrida di EarlyBird V10.0, che combina:

- ✅ **Supabase Cloud**: Database centralizzato per intelligence e configurazione geografica
- ✅ **SQLite Locale**: Database ad alte prestazioni per dati operativi e tracking performance
- ✅ **ContinentalOrchestrator**: Implementa la logica "Follow the Sun" per scheduling intelligente
- ✅ **Mirror Fallback**: Garantisce resilienza in caso di problemi di connessione a Supabase

---

## 🎯 Obiettivi dell'Architettura Ibrida

### Obiettivi Primari
1. Mantenere Supabase per intelligence e configurazione (continents, countries, leagues, news_sources)
2. Mantenere SQLite per dati operativi (matches, news_logs, team_aliases, odds_snapshots, telegram_channels, telegram_message_logs)
3. Ottimizzare ContinentalOrchestrator per la logica "Follow the Sun"
4. Garantire resilienza con mirror fallback
5. Documentare chiaramente la divisione responsabilità

### Obiettivi Secondari
1. Implementare cache intelligente per Supabase (già implementato con TTL 1 ora)
2. Implementare logging delle operazioni database
3. Ottimizzare le query per entrambi i database
4. Monitorare la performance del modello ibrido

---

## 📊 Analisi delle Tabelle

### Tabelle in Supabase (Intelligence & Configurazione)

| Tabella | Records | Chiave Primaria | Relazioni | Scopo |
|---------|----------|------------------|------------|--------|
| `continents` | 3 | `id` (UUID) | HasMany: countries | Blocchi geografici con finestre orarie |
| `countries` | 28 | `id` (UUID) | BelongsTo: continents, HasMany: leagues | Paesi per continenti |
| `leagues` | 56 | `id` (UUID) | BelongsTo: countries, HasMany: news_sources, social_sources | Leghe con API keys per odds |
| `news_sources` | 140 | `id` (UUID) | BelongsTo: leagues | Domini per Brave/DDG search |
| `social_sources` | 38 | `id` (UUID) | BelongsTo: leagues | Handle X per Nitter monitor |

### Tabelle in SQLite (Dati Operativi & Performance)

| Tabella | Records | Chiave Primaria | Relazioni | Scopo |
|---------|----------|------------------|------------|--------|
| `matches` | 48 | `id` (String) | HasMany: news_logs, odds_snapshots | Partite con quote e statistiche |
| `news_logs` | 1 | `id` (Integer) | BelongsTo: matches | Log analisi notizie |
| `team_aliases` | 73 | `id` (Integer) | None | Mappatura nomi squadre |
| `odds_snapshots` | 0 | `id` (Integer) | BelongsTo: matches | Snapshot quote storiche |
| `telegram_channels` | 0 | `id` (Integer) | HasMany: telegram_message_logs | Canali Telegram monitorati |
| `telegram_message_logs` | 0 | `id` (Integer) | BelongsTo: telegram_channels | Log messaggi Telegram |

---

## 🔍 Componenti Chiave

### ContinentalOrchestrator

**File**: [`src/processing/continental_orchestrator.py`](src/processing/continental_orchestrator.py:1-100)

**Funzionalità:**
- Implementa la logica "Follow the Sun" con finestre orarie continentali
- Interroga Supabase per ottenere le leghe attive
- Gestisce la finestra di manutenzione (04:00-06:00 UTC)
- Fallback al mirror locale se Supabase è irraggiungibile
- Singleton pattern per consistenza

### SupabaseProvider

**File**: [`src/database/supabase_provider.py`](src/database/supabase_provider.py:1-1059)

**Funzionalità:**
- Singleton pattern per connessione Supabase
- Cache intelligente con TTL di 1 ora
- Mirror fallback per resilienza
- Gestisce SOLO le tabelle di configurazione (continents, countries, leagues, news_sources)

**Metodi Principali:**
- `get_active_leagues()`: Ottiene le leghe attive
- `get_active_leagues_for_continent()`: Ottiene le leghe per continente
- `get_active_continent_blocks()`: Ottiene i blocchi continentali attivi
- `get_news_sources()`: Ottiene le fonti di notizie per lega
- `get_social_sources()`: Ottiene le fonti social (Twitter/X handles) per lega
- `get_social_sources_for_league()`: Ottiene le fonti social per una lega specifica

### Database Locale (SQLite)

**File**: [`src/database/models.py`](src/database/models.py:1-569)

**Funzionalità:**
- Definisce i modelli SQLAlchemy per le tabelle operative
- Gestisce SessionLocal per accesso al database
- Fornisce context manager per transazioni
- Usato da 74 file nel codice operativo

---

## 📊 RIEPILOGO VERIFICA COVE

### Errori Identificati nel Piano Precedente

| # | Errore nel Piano Precedente | Verifica Reale | Stato |
|---|---------------------------|----------------|-------|
| 1 | "Migrazione COMPLETA a Supabase" | Modello Ibrido: Supabase per config, SQLite per dati operativi | ❌ **CORRETTO** |
| 2 | Relazioni rotte (10.7%, 50%, 23.6%) | Tutte le relazioni sono corrette al 100% | ❌ **CORRETTO** |
| 3 | Tabelle da migrare: matches, news_logs, team_aliases, etc. | Queste tabelle DEVONO rimanere in SQLite | ❌ **CORRETTO** |
| 4 | SupabaseProvider incompleto | SupabaseProvider NON deve gestire le tabelle operative (sono in SQLite) | ❌ **CORRETTO** |

### Stato Attuale del Sistema

**Modello Ibrido (GIÀ IMPLEMENTATO):**
- ✅ **Supabase**: continents, countries, leagues, news_sources, social_sources (Intelligence & Configurazione)
- ✅ **SQLite**: matches, news_logs, team_aliases, odds_snapshots, telegram_channels, telegram_message_logs (Dati Operativi & Performance)
- ✅ **ContinentalOrchestrator**: Implementa la logica "Follow the Sun" usando Supabase per configurazione
- ✅ **Codice Operativo**: Usa SQLite locale per tutti i dati operativi (74 file)
- ✅ **Relazioni Supabase**: Tutte corrette al 100%

---

## ⚠️ BUG CRITICI IDENTIFICATI (CoVe Double Check)

### BUG #1: Chiave Mirror Errata in `fetch_hierarchical_map()`
- **Location**: [`src/database/supabase_provider.py:457`](src/database/supabase_provider.py:457)
- **Errore**: Il mirror viene salvato con chiave `"sources"` invece di `"news_sources"`
- **Impatto**: Il mirror fallback non funziona per news_sources
- **Severità**: CRITICO
- **Risoluzione**: Cambiare `"sources": self.fetch_sources()` → `"news_sources": self.fetch_sources()`
- **Nota**: Questo bug si ripete anche in `update_mirror()` (linea 748) e `create_local_mirror()` (linea 796)

### BUG #2: Chiavi Mirror Duplicate in `create_local_mirror()` e `update_mirror()`
- **Location**:
  - [`src/database/supabase_provider.py:457`](src/database/supabase_provider.py:457) - `fetch_hierarchical_map()`
  - [`src/database/supabase_provider.py:748`](src/database/supabase_provider.py:748) - `update_mirror()`
  - [`src/database/supabase_provider.py:796`](src/database/supabase_provider.py:796) - `create_local_mirror()`
- **Errore**: Il mirror viene salvato con DUE chiavi: `"sources"` e `"news_sources"` in **3 metodi diversi**
- **Impatto**: Confusione e duplicazione nel mirror in tutti i punti di salvataggio
- **Severità**: CRITICO
- **Risoluzione**: Rimuovere la riga `"sources": self.fetch_sources()` da tutte e 3 le occorrenze (mantenere solo `"news_sources"`)

### ISSUE #1: Mirror Obsoleto
- **Location**: [`data/supabase_mirror.json`](data/supabase_mirror.json:1)
- **Osservazione**: Il mirror ha timestamp 2026-02-10T22:55:45 (ieri)
- **Contenuto Attuale**:
  - continents: ✅ Presente
  - countries: ✅ Presente
  - leagues: ✅ Presente
  - sources: ❌ Presente (chiave errata)
  - news_sources: ❌ MANCANTE (0 nel mirror, 140 in Supabase)
  - social_sources: ❌ MANCANTE (0 nel mirror, 38 in Supabase)
- **Impatto**: Il mirror fallback non funziona per news_sources e social_sources
- **Severità**: ALTA
- **Risoluzione**: Eseguire `refresh_mirror()` dopo aver corretto i bug #1 e #2

---

## 🔍 VALIDAZIONE AGGIUNTIVA (2026-02-11)

### Analisi Approfondita dello Stato di Implementazione

#### 1. Stato Attuale dei Componenti (Verificato via Code Analysis)

| Componente | Claim nel Piano | Stato Reale | Dettagli |
|-----------|------------------|--------------|----------|
| **LeagueManager** | "Deve usare SOLO le leghe recuperate da Supabase" | ❌ **NON IMPLEMENTATO** | Usa liste hardcoded: `TIER_1_LEAGUES` (7 leghe) e `TIER_2_LEAGUES` (8 leghe) in [`src/ingestion/league_manager.py`](src/ingestion/league_manager.py:58-82) |
| **SearchProvider** | "Deve recuperare news_sources direttamente dal database" | ⚠️ **PARZIALMENTE IMPLEMENTATO** | Importa Supabase ma usa ancora `LEAGUE_DOMAINS` hardcoded in [`src/ingestion/search_provider.py`](src/ingestion/search_provider.py:131-211) |
| **NitterMonitor** | "Deve recuperare i target X handles da Supabase" | ⚠️ **PARZIALMENTE IMPLEMENTATO** | Non usa direttamente Supabase, ma `news_hunter.py` fornisce implementazione ibrida con fallback |

#### 2. Implementazione Ibrida Esistente

**File**: [`src/processing/news_hunter.py`](src/processing/news_hunter.py:129-181)

**Funzione**: `get_social_sources_from_supabase(league_key)`

**Logica Implementata**:
```python
# 1. Prova Supabase prima
if _SUPABASE_AVAILABLE and _SUPABASE_PROVIDER:
    all_social_sources = _SUPABASE_PROVIDER.get_social_sources()
    # ... filtra e restituisce handles
    
# 2. Fallback a locale se Supabase fallisce
else:
    handles = get_insider_handles(league_key)  # da sources_config.py
    beat_writers = get_beat_writers(league_key)
    all_handles = list(set(handles + [w.handle for w in beat_writers]))
    return all_handles
```

**Stato**: ✅ **IMPLEMENTATO** - Sistema ibrido con fallback automatico

#### 3. Correzioni al Piano Originale

**Inaccuratezza #1**: "LeagueManager deve essere refattorizzato"
- **Realtà**: LeagueManager NON usa Supabase affatto
- **Azione Richiesta**: ✅ **VALIDA** - Richiede refactoring completo

**Inaccuratezza #2**: "SearchProvider deve recuperare news_sources da Supabase"
- **Realtà**: SearchProvider importa Supabase ma usa ancora `LEAGUE_DOMAINS` hardcoded
- **Azione Richiesta**: ⚠️ **PARZIALMENTE VALIDA** - Codice ibrido esiste per social_sources, non per news_sources

**Inaccuratezza #3**: "NitterMonitor deve recuperare da Supabase"
- **Realtà**: NitterMonitor non usa Supabase direttamente, ma usa implementazione ibrida via news_hunter.py
- **Azione Richiesta**: ⚠️ **PARZIALMENTE VALIDA** - Fallback già implementato

#### 4. Schema Tabella social_sources

**Claim nel Piano**: 7 colonne

**Realtà Verificata**: 9 colonne

**Colonne Effettive**:
- `id`, `league_id`, `platform`, `identifier`, `source_name`, `description`, `is_active`, `created_at`, `updated_at`

**Correzione Necessaria**: Aggiornare documentazione da 7 a 9 colonne

#### 5. Bug #2 - Instance Addizionale

**Bug Identificato**: La chiave `"sources"` duplicata esiste in **3 metodi**, non solo 2 come riportato:

1. [`fetch_hierarchical_map()`](src/database/supabase_provider.py:457) - Linea 457
2. [`update_mirror()`](src/database/supabase_provider.py:748) - Linea 748
3. [`create_local_mirror()`](src/database/supabase_provider.py:796) - Linea 796

**Impatto**: Tutti e 3 i metodi salvano mirror con chiave errata

**Azione Correttiva**: Rimuovere `"sources": self.fetch_sources()` da tutte e 3 le occorrenze

---

## 🎯 Conclusione

L'architettura ibrida di EarlyBird V10.0 è **GIÀ CORRETTAMENTE IMPLEMENTATA**:

1. **Supabase** viene usato per intelligence e configurazione (continents, countries, leagues, news_sources, social_sources)
2. **SQLite** viene usato per dati operativi e performance (matches, news_logs, team_aliases, odds_snapshots, telegram_channels, telegram_message_logs)
3. **ContinentalOrchestrator** implementa la logica "Follow the Sun" usando Supabase
4. **SupabaseProvider** gestisce correttamente solo le tabelle di configurazione
5. **Tutte le relazioni** in Supabase sono corrette al 100%

Non è necessaria alcuna migrazione. Il sistema funziona già secondo l'architettura ibrida corretta.

**⚠️ ATTENZIONE - BUG CRITICI DA CORREGGERE:**
- **Bug #1**: [`fetch_hierarchical_map()`](src/database/supabase_provider.py:457) usa chiave `"sources"` invece di `"news_sources"`
- **Bug #2**: [`create_local_mirror()`](src/database/supabase_provider.py:796) usa DUE chiavi: `"sources"` e `"news_sources"`
- **Issue #1**: Il mirror [`data/supabase_mirror.json`](data/supabase_mirror.json:1) è obsoleto e manca `news_sources` e `social_sources`

**AZIONI NECESSARIE:**
1. Correggere il bug #1 cambiando `"sources"` → `"news_sources"` alla riga 457
2. Correggere il bug #2 rimuovendo la riga 748 in `update_mirror()` (la chiave `"sources"`)
3. Correggere il bug #2 rimuovendo la riga 796 in `create_local_mirror()` (la chiave `"sources"`)
4. Eseguire `refresh_mirror()` per rigenerare il mirror con le chiavi corrette
5. Verificare che il mirror contenga tutte le tabelle attese (continents, countries, leagues, news_sources, social_sources)
6. Refactorizzare [`LeagueManager`](src/ingestion/league_manager.py:58) per usare Supabase invece di liste hardcoded
7. Refactorizzare [`SearchProvider`](src/ingestion/search_provider.py:131) per usare Supabase per `news_sources` invece di `LEAGUE_DOMAINS`
8. Verificare che [`NitterMonitor`](src/services/nitter_fallback_scraper.py:1) usi Supabase o implementazione ibrida esistente
9. Aggiornare documentazione: social_sources ha 9 colonne, non 7

---

## 🎯 Strategic Goal: "Source Unification - Final Transition to DB-Only Intelligence"

### Context

Stiamo finalizzando l'Architettura Ibrida V9.5. Vogliamo stabilire **Supabase** come "Source of Truth" ESCLUSIVA per tutta l'intelligence di scouting (News Domains, X Handles, e Telegram Channels). I file di configurazione locale sono ora considerati technical debt.

**NOTA IMPORTANTE**: La tabella `social_sources` (38 records) è già presente in Supabase e contiene i Twitter/X handles per il monitoraggio Nitter.

### Task: Full Logic Decommissioning

#### 1. The "Switch" Operation

Refactorizzare i seguenti componenti per smettere di leggere dai file locali e dipendere strettamente da `SupabaseProvider`:

- **`LeagueManager`**: Deve usare SOLO le leghe recuperate da Supabase (Continental blocks).
- **`SearchProvider`**: Deve recuperare `news_sources` direttamente dal database per ogni partita specifica.
- **`NitterMonitor`**: Deve recuperare i target X handles dalla tabella `social_sources` di Supabase (già presente con 38 records).

#### 2. Safeguarding the "Lifeboat" (Local Mirror)

**Requirement:** Prima di disabilitare i file locali, verificare che `src/database/supabase_provider.py` implementa un metodo robusto `update_mirror()`.

**Logic:** Questo metodo deve salvare l'INTERA mappa intelligence di Supabase (Continents -> Leagues -> News Sources -> Social Sources) in `data/supabase_mirror.json`.

**Boot Sequence:** Assicurarsi che il bot controlli il Mirror all'avvio. Se Supabase è irraggiungibile, DEVE caricare il Mirror in modo da non essere mai "blind".

**⚠️ BUG CRITICI IDENTIFICATI:**
- Il metodo `fetch_hierarchical_map()` (riga 457) usa la chiave `"sources"` invece di `"news_sources"`
- Il metodo `create_local_mirror()` (riga 796) usa DUE chiavi: `"sources"` e `"news_sources"`
- Il mirror attuale è obsoleto (timestamp: 2026-02-10T22:55:45) e manca `news_sources` e `social_sources`
- **Risoluzione**: Correggere i bug #1 e #2, poi eseguire `refresh_mirror()` per rigenerare il mirror

#### 3. Decommissioning Local Files (Clean Up)

Identificare i file locali che contengono liste di intelligence hardcoded, come:
- `src/processing/sources_config.py`
- `config/twitter_intel_accounts.py` (o simili)

**Action:**
- NON cancellare i file (per prevenire ImportErrors).
- Invece, **Commentare** le vecchie liste e sostituirle con un warning chiaro: `# DEPRECATED: Intelligence now managed via Supabase`.
- Assicurarsi che qualsiasi parte del codice che importa queste variabili sia refactoring per usare il nuovo provider dinamico.

### Strategic Directive

- **Integrity:** Il sistema deve comportarsi esattamente come prima, ma con la flessibilità di un database cloud.
- **Character Support:** Assicurarsi che i nomi con caratteri speciali (UTF-8) siano gestiti correttamente durante il sync da Supabase al mirror locale.
- **Veto Protection:** Il **Tactical Veto V5.0** e il **15% Market Veto** devono rimanere attivi e usare i dati forniti dal nuovo flow DB-driven.

### Verification

- Fornire una lista dei file locali che sono stati decommissionati.
- Eseguire `make test-continental` per confermare che il bot "si sveglia" e identifica correttamente le sue leghe target usando SOLO i dati del database.
- **CRITICO**: Verificare che il mirror (`data/supabase_mirror.json`) contenga tutte le tabelle attese:
  - ✅ continents
  - ✅ countries
  - ✅ leagues
  - ✅ news_sources (NON "sources")
  - ✅ social_sources
- Se il mirror non contiene queste tabelle, eseguire `refresh_mirror()` per rigenerarlo.

---

## 📚 Documentazione di Riferimento

- [`MASTER_SYSTEM_ARCHITECTURE.md`](MASTER_SYSTEM_ARCHITECTURE.md:1) - Architettura completa del sistema
- [`src/processing/continental_orchestrator.py`](src/processing/continental_orchestrator.py:1-100) - Implementazione "Follow the Sun"
- [`src/database/supabase_provider.py`](src/database/supabase_provider.py:1-1059) - Provider Supabase
- [`src/database/models.py`](src/database/models.py:1-569) - Modelli SQLAlchemy per SQLite
- [`docs/INTEGRATION_TEST_REPORT_V9.0.md`](docs/INTEGRATION_TEST_REPORT_V9.0.md:1) - Report integrazione V9.0

---

**Data Aggiornamento**: 2026-02-11
**Versione**: V10.0 (Modello Ibrido Confermato)
