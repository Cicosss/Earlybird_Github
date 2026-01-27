#!/bin/bash
# ============================================
# EarlyBird V7.1 - Sistema Completo con Test Monitor
# Avvia bot + test monitor in tmux con doppio pannello
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
echo "🦅 EARLYBIRD V7.1 - AVVIO SISTEMA COMPLETO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# ============================================
# STEP 0: Verifica dipendenze
# ============================================
echo -e "${YELLOW}🔍 [0/4] Verifica dipendenze...${NC}"

# Verifica tmux
if ! command -v tmux &> /dev/null; then
    echo -e "${RED}❌ tmux non installato!${NC}"
    echo -e "${YELLOW}   Installa con: sudo apt install tmux${NC}"
    echo ""
    echo -e "${YELLOW}⚠️ Fallback: avvio senza test monitor (modalità legacy)${NC}"
    echo -e "${YELLOW}   Eseguo: ./run_forever.sh${NC}"
    exec ./run_forever.sh
    exit 0
fi
echo -e "${GREEN}   ✅ tmux disponibile${NC}"

# Verifica venv
if [ -d "venv" ]; then
    VENV_PATH="venv"
elif [ -d ".venv" ]; then
    VENV_PATH=".venv"
else
    echo -e "${RED}❌ Virtual environment non trovato!${NC}"
    echo -e "${YELLOW}   Esegui prima: python3 -m venv venv${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ venv trovato: ${VENV_PATH}${NC}"

# Verifica Playwright (V7.2 - auto-install se manca)
source "${VENV_PATH}/bin/activate"
echo -e "${YELLOW}   🌐 Verifica Playwright...${NC}"
if ! python -c "from playwright.async_api import async_playwright" 2>/dev/null; then
    echo -e "${YELLOW}   ⚠️ Playwright non installato, installazione...${NC}"
    pip install playwright playwright-stealth trafilatura --quiet
fi
# Verifica browser Chromium
if ! python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()" 2>/dev/null; then
    echo -e "${YELLOW}   ⚠️ Browser Chromium mancante, installazione...${NC}"
    python -m playwright install chromium
    python -m playwright install-deps chromium 2>/dev/null || true
fi
echo -e "${GREEN}   ✅ Playwright pronto${NC}"
deactivate
echo ""

# ============================================
# STEP 1: Test Pre-Avvio (bloccanti)
# ============================================
echo -e "${YELLOW}🧪 [1/4] Test Pre-Avvio (bloccanti)...${NC}"
echo ""

source "${VENV_PATH}/bin/activate"
export PYTHONPATH="${PYTHONPATH}:."

# Test critici - se falliscono, il bot non parte
echo -e "${CYAN}   Esecuzione test validatori...${NC}"
if ! pytest tests/test_validators.py -v --tb=short -q; then
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}❌ TEST PRE-AVVIO FALLITI!${NC}"
    echo -e "${RED}   Il bot NON verrà avviato.${NC}"
    echo -e "${RED}   Correggi i test prima di procedere.${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}   ✅ Test pre-avvio superati${NC}"
echo ""

# ============================================
# STEP 2: Chiudi sessione esistente (se presente)
# ============================================
echo -e "${YELLOW}🔄 [2/4] Pulizia sessioni precedenti...${NC}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}   ⚠️ Sessione '$SESSION_NAME' esistente, chiusura...${NC}"
    tmux kill-session -t "$SESSION_NAME"
    sleep 1
fi
echo -e "${GREEN}   ✅ Pronto per nuova sessione${NC}"
echo ""

# ============================================
# STEP 3: Crea sessione tmux con doppio pannello
# ============================================
echo -e "${YELLOW}🖥️ [3/4] Creazione sessione tmux...${NC}"

# Crea nuova sessione con il bot nel pannello sinistro
tmux new-session -d -s "$SESSION_NAME" -n "main"

# Pannello sinistro: Bot principale
tmux send-keys -t "$SESSION_NAME:main" "source ${VENV_PATH}/bin/activate && export PYTHONPATH=\${PYTHONPATH}:. && ./run_forever.sh" C-m

# Dividi orizzontalmente (pannello destro)
tmux split-window -h -t "$SESSION_NAME:main"

# Pannello destro: Test Monitor
tmux send-keys -t "$SESSION_NAME:main.1" "source ${VENV_PATH}/bin/activate && export PYTHONPATH=\${PYTHONPATH}:. && sleep 10 && ./run_tests_monitor.sh" C-m

# Imposta layout 50/50
tmux select-layout -t "$SESSION_NAME:main" even-horizontal

# Torna al pannello sinistro (bot)
tmux select-pane -t "$SESSION_NAME:main.0"

echo -e "${GREEN}   ✅ Sessione tmux creata${NC}"
echo ""

# ============================================
# STEP 4: Mostra guida e attach
# ============================================
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ SISTEMA AVVIATO!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📖 GUIDA NAVIGAZIONE TMUX:${NC}"
echo ""
echo "   ┌─────────────────────┬─────────────────────┐"
echo "   │  🦅 BOT PRINCIPALE  │  🧪 TEST MONITOR    │"
echo "   │  (pannello 0)       │  (pannello 1)       │"
echo "   └─────────────────────┴─────────────────────┘"
echo ""
echo -e "${CYAN}   Comandi base:${NC}"
echo "   • Ctrl+B poi ←/→    Sposta tra pannelli"
echo "   • Ctrl+B poi d      Detach (esci senza fermare)"
echo "   • Ctrl+B poi z      Zoom pannello corrente"
echo "   • Ctrl+B poi x      Chiudi pannello corrente"
echo ""
echo -e "${CYAN}   Rientrare nella sessione:${NC}"
echo "   • tmux attach -t $SESSION_NAME"
echo ""
echo -e "${CYAN}   Fermare tutto:${NC}"
echo "   • tmux kill-session -t $SESSION_NAME"
echo ""
echo -e "${YELLOW}🚀 Connessione alla sessione in corso...${NC}"
echo ""

# Attach alla sessione
sleep 2
tmux attach -t "$SESSION_NAME"
