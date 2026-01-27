#!/bin/bash
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
    jq "(.userStories[] | select(.id == \"$TASK_ID\") | .passes) |= true" $PRD_FILE > "$tmp" && mv "$tmp" $PRD_FILE
    
    # 6. Git Snapshot
    git add .
    git commit -m "Ralph: Refactoring $TASK_FILE" > /dev/null 2>&1
    
    echo "✅ Completato $TASK_FILE. Commit effettuato."
    sleep 2
done

rm $PROMPT_FILE
