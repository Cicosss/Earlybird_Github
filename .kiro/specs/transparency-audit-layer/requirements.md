# Requirements Document

## Introduzione

Questo documento definisce i requisiti per il **Transparency Audit Layer** - un refactoring del sistema EarlyBird per garantire che tutti i dati raccolti e analizzati siano:
1. **Persistiti nel database** - per audit trail completo
2. **Visibili negli alert Telegram** - per trasparenza verso l'utente
3. **Accessibili al futuro Controller** - un modulo che verificherà il lavoro di DeepSeek

Il problema attuale: il sistema raccoglie molti dati (form, H2H, arbitro, nomi giocatori assenti, classifica) ma questi dati vengono usati internamente senza essere salvati o mostrati. Un "controllore" futuro non può verificare se DeepSeek ha considerato tutti i dati disponibili.

## Glossario

- **Alert_System**: Il modulo `src/alerting/notifier.py` che invia alert Telegram
- **Verification_Layer**: Il modulo `src/analysis/verification_layer.py` che verifica i dati con fonti esterne
- **Injury_Impact_Engine**: Il modulo `src/analysis/injury_impact_engine.py` che calcola l'impatto degli infortuni
- **Analyzer**: Il modulo `src/analysis/analyzer.py` che chiama DeepSeek per l'analisi
- **Match_Context**: Nuovo concetto - tutti i dati contestuali raccolti per una partita
- **Controller**: Futuro modulo che auditerà le decisioni di DeepSeek
- **VerifiedData**: Dataclass esistente in verification_layer.py con FormStats, H2HStats, RefereeStats
- **PlayerImpact**: Dataclass esistente in injury_impact_engine.py con nome, ruolo, posizione, impact_score
- **NewsLog**: Tabella esistente nel DB che memorizza gli alert inviati

## Requirements

### Requirement 1: Persistenza Nomi Giocatori Assenti

**User Story:** Come auditor, voglio vedere i nomi specifici dei giocatori assenti e il loro ruolo, così posso verificare che DeepSeek abbia considerato l'impatto reale.

#### Acceptance Criteria

1. WHEN il sistema calcola l'impatto infortuni, THE Injury_Impact_Engine SHALL salvare nel Match_Context i nomi dei giocatori assenti con ruolo (titolare/riserva) e posizione (portiere/difensore/centrocampista/attaccante)
2. WHEN un alert viene generato, THE Alert_System SHALL mostrare i nomi dei giocatori assenti più impattanti (max 3 per squadra) con il loro ruolo
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare la lista completa dei giocatori assenti in formato JSON nella tabella NewsLog o in una nuova colonna dedicata
4. IF un giocatore assente è classificato come "key_player", THEN THE Alert_System SHALL evidenziarlo con un'icona speciale (⭐)

### Requirement 2: Persistenza e Visualizzazione Form (Ultime 5 Partite)

**User Story:** Come scommettitore, voglio vedere il form recente di entrambe le squadre, così posso valutare se la raccomandazione è coerente con le prestazioni recenti.

#### Acceptance Criteria

1. WHEN il Verification_Layer raccoglie i dati form, THE System SHALL salvare nel Match_Context: vittorie, pareggi, sconfitte, gol fatti, gol subiti per entrambe le squadre
2. WHEN un alert viene generato, THE Alert_System SHALL mostrare il form in formato compatto (es. "WWDLL - 8GF/4GS")
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare i FormStats in formato JSON
4. IF il form mostra una squadra in crisi (0 vittorie in 5 partite), THEN THE Alert_System SHALL evidenziarlo con un warning (⚠️)

### Requirement 3: Persistenza e Visualizzazione Head-to-Head

**User Story:** Come scommettitore, voglio vedere lo storico degli scontri diretti, così posso valutare pattern ricorrenti tra le due squadre.

#### Acceptance Criteria

1. WHEN il Verification_Layer raccoglie i dati H2H, THE System SHALL salvare nel Match_Context: numero partite analizzate, media gol, media cartellini, media corner, vittorie casa/trasferta/pareggi
2. WHEN un alert viene generato, THE Alert_System SHALL mostrare i dati H2H più rilevanti per il mercato suggerito (es. se suggerisce Over 2.5, mostra media gol H2H)
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare gli H2HStats in formato JSON
4. IF i dati H2H supportano fortemente il mercato suggerito (es. 5/5 Over 2.5), THEN THE Alert_System SHALL evidenziarlo con un'icona (🎯)

### Requirement 4: Persistenza e Visualizzazione Dati Arbitro

**User Story:** Come scommettitore, voglio vedere le statistiche dell'arbitro, così posso valutare se le raccomandazioni sui cartellini sono fondate.

#### Acceptance Criteria

1. WHEN il Verification_Layer raccoglie i dati arbitro, THE System SHALL salvare nel Match_Context: nome arbitro, media cartellini per partita, classificazione (strict/average/lenient)
2. WHEN un alert viene generato, THE Alert_System SHALL mostrare nome arbitro e media cartellini
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare i RefereeStats in formato JSON
4. IF l'arbitro è classificato come "strict" (>5 cartellini/partita), THEN THE Alert_System SHALL evidenziarlo con un'icona (🟨)
5. IF l'arbitro è classificato come "lenient" (<3 cartellini/partita) E viene suggerito Over Cards, THEN THE Alert_System SHALL mostrare un warning di incongruenza

### Requirement 5: Persistenza e Visualizzazione Classifica/Motivazione

**User Story:** Come scommettitore, voglio vedere la posizione in classifica e il contesto motivazionale, così posso valutare fattori come lotta salvezza o corsa al titolo.

#### Acceptance Criteria

1. WHEN il sistema analizza una partita, THE System SHALL raccogliere e salvare nel Match_Context: posizione in classifica di entrambe le squadre, distanza dalla zona retrocessione/Europa, contesto motivazionale (title_race, relegation_battle, mid_table, etc.)
2. WHEN un alert viene generato, THE Alert_System SHALL mostrare la posizione in classifica di entrambe le squadre
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare i dati classifica in formato JSON
4. IF una squadra è in lotta salvezza (ultimi 3 posti), THEN THE Alert_System SHALL evidenziarlo con un'icona (🔻)
5. IF una squadra è in corsa per il titolo (primi 3 posti), THEN THE Alert_System SHALL evidenziarlo con un'icona (🏆)

### Requirement 6: Nuovo Schema Database per Match_Context

**User Story:** Come sviluppatore, voglio una struttura dati chiara per memorizzare tutti i dati contestuali, così il Controller futuro può accedervi facilmente.

#### Acceptance Criteria

1. THE Database SHALL avere una nuova colonna `match_context_json` nella tabella NewsLog per memorizzare tutti i dati contestuali in formato JSON strutturato
2. THE match_context_json SHALL contenere le seguenti sezioni: `injuries`, `form`, `h2h`, `referee`, `standings`, `fatigue`, `twitter_intel`, `verification_result`, `ai_audit`
3. WHEN un alert viene salvato, THE System SHALL popolare match_context_json con tutti i dati disponibili
4. IF alcuni dati non sono disponibili, THEN THE System SHALL salvare `null` per quella sezione invece di omettere il campo

#### Schema JSON Match_Context

```json
{
  "injuries": {
    "home": [
      {"name": "string", "role": "starter|rotation|backup", "position": "GK|DEF|MID|FWD", "impact_score": 0-10, "reason": "string"}
    ],
    "away": [...],
    "home_total_impact": 0.0,
    "away_total_impact": 0.0,
    "home_severity": "CRITICAL|HIGH|MEDIUM|LOW",
    "away_severity": "CRITICAL|HIGH|MEDIUM|LOW"
  },
  "form": {
    "home": {"wins": 0, "draws": 0, "losses": 0, "goals_scored": 0, "goals_conceded": 0, "form_string": "WWDLL"},
    "away": {...},
    "confidence": "HIGH|MEDIUM|LOW"
  },
  "h2h": {
    "matches_analyzed": 0,
    "avg_goals": 0.0,
    "avg_cards": 0.0,
    "avg_corners": 0.0,
    "home_wins": 0,
    "away_wins": 0,
    "draws": 0,
    "confidence": "HIGH|MEDIUM|LOW"
  },
  "referee": {
    "name": "string",
    "cards_per_game": 0.0,
    "strictness": "strict|average|lenient|unknown",
    "matches_officiated": 0,
    "confidence": "HIGH|MEDIUM|LOW"
  },
  "standings": {
    "home": {"position": 0, "zone": "string", "points": 0, "goal_diff": 0},
    "away": {...}
  },
  "fatigue": {
    "home": {"level": "HIGH|MEDIUM|LOW", "days_since_last": 0, "matches_last_14d": 0},
    "away": {...}
  },
  "twitter_intel": {
    "tweets": [
      {"handle": "string", "content": "string", "freshness": "FRESH|AGING|STALE", "topics": ["injury", "lineup"]}
    ],
    "cache_age_minutes": 0
  },
  "verification_result": {
    "status": "confirm|reject|change_market",
    "confidence": "HIGH|MEDIUM|LOW",
    "original_market": "string",
    "recommended_market": "string",
    "inconsistencies": ["string"],
    "reasoning": "string"
  },
  "ai_audit": {
    "prompt_hash": "string",
    "response_hash": "string",
    "model_used": "string",
    "timestamp": "ISO8601",
    "reasoning_trace": "string",
    "confidence": 0-100
  }
}
```

### Requirement 7: Formato Alert Telegram Ristrutturato

**User Story:** Come utente, voglio un alert Telegram che mostri tutti i dati in modo organizzato e non spammoso, così posso prendere decisioni informate rapidamente.

#### Acceptance Criteria

1. THE Alert_System SHALL organizzare l'alert in sezioni logiche: Header, Match Info, Infortuni, Form, H2H, Arbitro, Classifica, Analisi AI, Verifica
2. THE Alert_System SHALL usare emoji consistenti per ogni sezione per facilitare la lettura rapida
3. THE Alert_System SHALL troncare i dati lunghi con "..." e indicare che ci sono più dettagli disponibili
4. WHEN il messaggio supera 4000 caratteri, THE Alert_System SHALL prioritizzare le informazioni più rilevanti per il mercato suggerito
5. THE Alert_System SHALL mantenere il formato HTML esistente per compatibilità Telegram

### Requirement 8: Audit Trail per Controller

**User Story:** Come futuro Controller, voglio poter ricostruire esattamente quali dati DeepSeek ha ricevuto e come ha deciso, così posso verificare la qualità delle analisi.

#### Acceptance Criteria

1. WHEN DeepSeek viene chiamato, THE Analyzer SHALL salvare nel Match_Context il prompt completo inviato (con tutti i 6 data sources)
2. WHEN DeepSeek risponde, THE Analyzer SHALL salvare nel Match_Context la risposta completa (JSON + reasoning trace se presente)
3. THE match_context_json SHALL contenere una sezione `ai_audit` con: `prompt_hash`, `response_hash`, `model_used`, `timestamp`, `reasoning_trace`
4. IF il Verification_Layer modifica il mercato suggerito, THEN THE System SHALL salvare sia il mercato originale che quello modificato con la motivazione

### Requirement 9: Retrocompatibilità

**User Story:** Come sviluppatore, voglio che le modifiche siano retrocompatibili, così il sistema continua a funzionare durante la migrazione.

#### Acceptance Criteria

1. THE Database migration SHALL essere non-distruttiva (aggiunge colonne, non modifica quelle esistenti)
2. THE Alert_System SHALL continuare a funzionare anche se match_context_json è vuoto o null
3. THE System SHALL popolare gradualmente i nuovi campi senza richiedere un reset del database
4. IF un campo del Match_Context è null, THEN THE Alert_System SHALL semplicemente non mostrare quella sezione

### Requirement 10: Integrazione con Flusso Dati Esistente

**User Story:** Come sviluppatore, voglio che i nuovi dati si integrino con il flusso esistente senza duplicare logica, così il codice rimane manutenibile.

#### Acceptance Criteria

1. WHEN il main.py chiama run_verification_check(), THE System SHALL passare il Match_Context popolato al Verification_Layer
2. WHEN il Verification_Layer restituisce VerifiedData, THE System SHALL estrarre i dati e aggiungerli al Match_Context
3. THE System SHALL riutilizzare le dataclass esistenti (FormStats, H2HStats, RefereeStats, PlayerImpact) invece di creare nuove strutture
4. WHEN i dati FotMob sono già disponibili (home_context, away_context), THE System SHALL usarli come fonte primaria invece di ri-fetchare
5. THE System SHALL loggare quando un dato viene sovrascritto da una fonte più affidabile (es. Tavily sovrascrive FotMob per form)

### Requirement 11: Visualizzazione Dati Fatica e Turnover

**User Story:** Come scommettitore, voglio vedere i dati di fatica e turnover delle squadre, così posso valutare se una squadra potrebbe essere stanca o ruotare i titolari.

#### Acceptance Criteria

1. WHEN il sistema rileva fatica alta (HIGH FATIGUE), THE Alert_System SHALL mostrare un indicatore (🔋) con il livello di fatica
2. WHEN il sistema rileva turnover probabile, THE Alert_System SHALL mostrare un warning (🔄) con la percentuale di turnover prevista
3. WHEN i dati vengono persistiti, THE Database SHALL memorizzare i dati fatica/turnover nel Match_Context
4. IF entrambe le squadre hanno fatica alta, THEN THE Alert_System SHALL suggerire che potrebbe essere una partita a basso ritmo

### Requirement 12: Visualizzazione Twitter Intel

**User Story:** Come scommettitore, voglio vedere le fonti Twitter che hanno contribuito all'analisi, così posso valutare la credibilità delle informazioni.

#### Acceptance Criteria

1. WHEN Twitter Intel è disponibile, THE Alert_System SHALL mostrare max 2 tweet rilevanti con handle e contenuto troncato
2. WHEN i dati vengono persistiti, THE Database SHALL memorizzare i tweet nel Match_Context con: handle, contenuto, freshness_tag, topics
3. IF un tweet è marcato come STALE (>24h), THEN THE Alert_System SHALL mostrarlo con un indicatore di età (⏰)
4. IF Twitter Intel conferma dati FotMob, THEN THE Alert_System SHALL mostrare un badge di conferma (✓)

