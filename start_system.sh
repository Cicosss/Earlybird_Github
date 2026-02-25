#!/bin/bash
# ============================================
# EarlyBird V8.3 - Dashboard Unificato (Official)
# " The Master Command"
# Avvia bot (Launcher) + test monitor in split-screen tmux
# ============================================

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SESSION_NAME="earlybird"

echo -e "${CYAN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 EARLYBIRD V8.3 - DASHBOARD UNIFICATO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# ============================================
# STEP 0: Verifica dipendenze
# ============================================
echo -e "${YELLOW}🔍 [0/4] Verifica dipendenze...${NC}"

if ! command -v tmux &> /dev/null; then
    echo -e "${RED}❌ tmux non installato!${NC}"
    echo -e "${YELLOW}   Installa con: sudo apt install tmux${NC}"
    exit 1
fi

if ! command -v make &> /dev/null; then
    echo -e "${RED}❌ make non installato!${NC}"
    echo -e "${YELLOW}   Installa con: sudo apt install make${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ Dipendenze di sistema OK${NC}"

# ============================================
# STEP 1: Pre-Flight Check
# ============================================
echo -e "${YELLOW}🧪 [1/4] System Pre-Flight Check...${NC}"
echo ""

# Usa Makefile per i check (astrazione standard)
# Eseguiamo check-env e check-health (se disponibile) o fallback a test-unit veloci
if make check-env > /dev/null; then
    echo -e "${GREEN}   ✅ Environment Check Passed${NC}"
else
    echo -e "${RED}❌ .env file mancante o invalido!${NC}"
    exit 1
fi

echo -e "${CYAN}   Esecuzione Health Check rapido...${NC}"
# Usiamo test-unit come sanity check rapido per garantire che il codice sia importabile
if make test-unit > /dev/null 2>&1; then
     echo -e "${GREEN}   ✅ Unit Tests Passed (Codebase Healthy)${NC}"
else
    echo -e "${RED}❌ Pre-flight sanity check fallito!${NC}"
    echo -e "${YELLOW}   Esegui 'make test-unit' per dettagli.${NC}"
    exit 1
fi

echo ""

# ============================================
# STEP 1.5: Memory Sync Pre-Flight Check
# ============================================
echo -e "${YELLOW}🧠 [1.5/4] Syncing AI Memory with Codebase...${NC}"
if make sync-memory > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ AI Memory Synced Successfully${NC}"
else
    echo -e "${RED}❌ Memory sync failed!${NC}"
    echo -e "${YELLOW}   Esegui 'make sync-memory' per dettagli.${NC}"
    exit 1
fi
echo ""

# ============================================
# STEP 2: Gestione Sessione
# ============================================
echo -e "${YELLOW}🔄 [2/4] Preparazione Tmux Dashboard...${NC}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}   ⚠️ Sessione '$SESSION_NAME' attiva, riavvio in corso...${NC}"
    tmux kill-session -t "$SESSION_NAME"
    sleep 1
fi

# ============================================
# STEP 3: Avvio Dashboard Split-Screen
# ============================================
echo -e "${YELLOW}🖥️ [3/4] Lancio Composizione Dashboard...${NC}"

# 1. Crea Sessione (Left Panel: Main Launcher)
# Usiamo 'make run-launcher' che gestisce internamente venv e paths
tmux new-session -d -s "$SESSION_NAME" -n "dashboard" "make run-launcher"

# 2. Split Orizzontale (Right Panel: Monitor)
# Usiamo 'make run-monitor' per il loop di test
tmux split-window -h -t "$SESSION_NAME:dashboard" "sleep 5 && make run-monitor"

# 3. Layout Equalizzato
tmux select-layout -t "$SESSION_NAME:dashboard" even-horizontal

# 4. Focus su Main Panel
tmux select-pane -t "$SESSION_NAME:dashboard.0"

echo -e "${GREEN}   ✅ Dashboard Attiva${NC}"
echo ""

# ============================================
# STEP 4: Handover all'Utente
# ============================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ SISTEMA ONLINE!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📖 DASHBOARD CONTROLS:${NC}"
echo "   ┌─────────────────────┬─────────────────────┐"
echo "   │  🦅 MAIN LAUNCHER   │  🧪 TEST MONITOR    │"
echo "   │  (make run-launcher)│  (make run-monitor) │"
echo "   └─────────────────────┴─────────────────────┘"
echo ""
echo "   • Attach:   tmux attach -t $SESSION_NAME"
echo "   • Detach:   Ctrl+B poi d"
echo "   • Stop:     Ctrl+C nei pannelli o tmux kill-session -t $SESSION_NAME"
echo ""
echo -e "${YELLOW}🚀 Connessione tra 2 secondi...${NC}"
sleep 2

tmux attach -t "$SESSION_NAME"
