import json
import os

# --- 1. CONFIGURAZIONE CARTELLE ---
os.makedirs("scripts/ralph", exist_ok=True)

# --- 2. IL TUO MEGA PROMPT (BMad Framework) ---
prompt_content = """Agisci come un Senior AI Developer esperto in BMad Framework.
Il file target è: [NOME_FILE_APERTO_ORA]

Esegui queste 4 fasi rigorosamente:

FASE 1: ANALISI PROFONDA
Analizza il codice di [NOME_FILE_APERTO_ORA] cercando:
- Errori di logica e codice troncato/incompleto.
- Formattazione illeggibile o incoerente.
- Duplicazioni e bug silenziosi.
- Controlla se le funzioni chiamate esistono e sono usate correttamente.

FASE 2: PIANIFICAZIONE E CONTESTO
- Ragiona su come questo file comunica con gli altri componenti del progetto (@Codebase).
- Prenditi il tempo per capire il flusso dei dati: Input -> Elaborazione -> Output.
- Assicurati che le modifiche siano compatibili con un ambiente VPS Linux (gestione percorsi, permessi).

FASE 3: RISCRITTURA INTELLIGENTE
- Riscrivi il codice completo del file. NON usare placeholder (es: "// code here").
- Il codice deve essere pronto per la produzione.

FASE 4: VERIFICA E DIPENDENZE (VPS)
- Controlla se hai introdotto nuove librerie. Se sì, dimmi esplicitamente quale comando lanciare (pip install / npm install) per aggiornare la VPS.
- Verifica mentalmente: se questo codice gira sulla VPS, crasherà per mancanza di var d'ambiente o percorsi errati? Correggi se necessario.

Procedi con l'output del codice corretto e applicalo al file.
"""

# --- 3. LA TUA LISTA FILE COMPLETA ---
raw_list = """
src/main.py - Punto di ingresso principale
src/analysis/analyzer.py - Motore di analisi core
src/database/models.py - Schemi e modelli dati
src/database/db.py - Connessione database
src/processing/telegram_listener.py - Integrazione Telegram
src/services/intelligence_router.py - Logica di decisione
src/analysis/settler.py - Motore di decisione finale
src/analysis/final_alert_verifier.py - Verifica alert
src/analysis/market_intelligence.py - Analisi mercato
src/analysis/injury_impact_engine.py - Impatto infortuni
src/ingestion/data_provider.py - Interfaccia provider
src/ingestion/opportunity_radar.py - Scoperta opportunita
src/processing/news_hunter.py - Raccolta notizie
src/ingestion/tavily_provider.py - API Tavily
src/ingestion/deepseek_intel_provider.py - Provider AI Deepseek
src/analysis/verification_layer.py - Verifica multi-livello
src/analysis/enhanced_verifier.py - Verifica avanzata
src/analysis/telegram_trust_score.py - Trust score
src/utils/validators.py - Validatori
src/analysis/alert_feedback_loop.py - Feedback loop
src/alerting/notifier.py - Notifiche
src/alerting/health_monitor.py - Monitor salute
src/analysis/reporter.py - Report
config/settings.py - Configurazione
requirements.txt - Dipendenze
pytest.ini - Test config
config/browser_sources.json - Sorgenti browser
config/news_radar_sources.json - Sorgenti news
src/utils/shared_cache.py - Cache
src/utils/smart_cache.py - Smart Cache
src/utils/http_client.py - HTTP Client
src/utils/text_normalizer.py - Normalizer
src/utils/url_normalizer.py - URL Normalizer
src/services/news_radar.py - News Radar
src/services/twitter_intel_cache.py - Twitter Cache
src/ingestion/league_manager.py - League Manager
src/ingestion/ingest_fixtures.py - Fixtures
src/analysis/math_engine.py - Math Engine
go_live.py - Deploy
run_telegram_monitor.py - Monitor
run_news_radar.py - Runner News
start_system.sh - Script avvio
show_errors.py - Debug errori
README.md - Docs
ARCHITECTURE.md - Docs
DEPLOY_INSTRUCTIONS.md - Docs
"""

# --- 4. CREAZIONE PRD.JSON ---
stories = []
lines = raw_list.strip().split('\n')
for idx, line in enumerate(lines):
    if " - " in line:
        parts = line.split(" - ")
        file_path = parts[0].strip()
        desc = parts[1].strip()
        stories.append({
            "id": str(idx + 1),
            "title": f"Refactoring BMad di {file_path}",
            "file": file_path,
            "passes": False
        })

prd_data = {"branchName": "feature/ai-refactoring", "userStories": stories}

# --- 5. SCRIPT BASH PER VS CODE ---
ralph_script = """#!/bin/bash
PRD_FILE="prd.json"
TEMPLATE="scripts/ralph/CLAUDE.md"
PROMPT_FILE="current_prompt.md"

echo "🚀 Ralph avviato in VS Code. Inizio ciclo di refactoring..."

# Loop infinito finché ci sono task
while true; do
    # 1. Cerca il primo task non completato
    NEXT_TASK_JSON=$(jq -r '.userStories[] | select(.passes == false) | {id, title, file} | tojson' $PRD_FILE | head -n 1)

    if [ -z "$NEXT_TASK_JSON" ]; then
        echo "✅ TUTTI I COMPONENTI COMPLETATI! Procedura terminata."
        break
    fi

    # 2. Estrai variabili
    TASK_ID=$(echo $NEXT_TASK_JSON | jq -r '.id')
    TASK_TITLE=$(echo $NEXT_TASK_JSON | jq -r '.title')
    TASK_FILE=$(echo $NEXT_TASK_JSON | jq -r '.file')

    echo "---------------------------------------------------"
    echo "🔨 Lavoro su: $TASK_FILE"
    echo "---------------------------------------------------"

    # 3. Prepara il Prompt
    cat $TEMPLATE | sed "s|\[NOME_FILE_APERTO_ORA\]|$TASK_FILE|g" > $PROMPT_FILE

    # 4. Chiama Claude Code (Modalità non interattiva per automazione)
    # L'opzione --print forza l'output nel terminale
    claude -p "$TASK_TITLE" --print < $PROMPT_FILE

    # 5. Segna come fatto (Passes: True)
    tmp=$(mktemp)
    jq "(.userStories[] | select(.id == \\"$TASK_ID\\") | .passes) |= true" $PRD_FILE > "$tmp" && mv "$tmp" $PRD_FILE
    
    # 6. Git Snapshot
    git add .
    git commit -m "Ralph: Refactoring $TASK_FILE" > /dev/null 2>&1
    
    echo "✅ Completato $TASK_FILE. Commit effettuato."
    sleep 2
done

rm $PROMPT_FILE
"""

# --- SCRITTURA FILE ---
with open("scripts/ralph/CLAUDE.md", "w") as f: f.write(prompt_content)
with open("prd.json", "w") as f: json.dump(prd_data, f, indent=2)
with open("scripts/ralph/ralph.sh", "w") as f: f.write(ralph_script)

print("✅ Setup VS Code completato. Esegui nel terminale: python3 setup_vs_ralph.py")   