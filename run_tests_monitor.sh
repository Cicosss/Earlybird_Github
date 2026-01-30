#!/bin/bash
# ============================================
# EarlyBird Test Monitor - Continuous Test Runner
# Runs critical tests periodically to monitor system health
# ============================================

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 EARLYBIRD TEST MONITOR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"
echo "📅 $(date)"
echo ""

# Verifica venv
if [ -d "venv" ]; then
    VENV_PATH="venv"
elif [ -d ".venv" ]; then
    VENV_PATH=".venv"
else
    echo -e "${RED}❌ Virtual environment non trovato!${NC}"
    exit 1
fi

source "${VENV_PATH}/bin/activate"
export PYTHONPATH="${PYTHONPATH}:."

# Test da eseguire (critici per il funzionamento)
CRITICAL_TESTS=(
    "tests/test_validators.py"
    "tests/test_database_full.py"
    "tests/test_intelligence_router.py"
)

# Loop infinito con test periodici
while true; do
    echo -e "${YELLOW}🔄 [$(date '+%H:%M:%S')] Esecuzione test critici...${NC}"
    
    FAILED=0
    PASSED=0
    
    for test_file in "${CRITICAL_TESTS[@]}"; do
        if [ -f "$test_file" ]; then
            echo -e "${CYAN}   Esecuzione: $test_file${NC}"
            if pytest "$test_file" -v --tb=short -q 2>&1 | tail -5; then
                ((PASSED++))
                echo -e "${GREEN}   ✅ PASS${NC}"
            else
                ((FAILED++))
                echo -e "${RED}   ❌ FAIL${NC}"
            fi
        else
            echo -e "${YELLOW}   ⚠️ File non trovato: $test_file${NC}"
        fi
    done
    
    echo ""
    echo -e "${GREEN}✅ Test passati: $PASSED${NC}"
    if [ $FAILED -gt 0 ]; then
        echo -e "${RED}❌ Test falliti: $FAILED${NC}"
    fi
    echo ""
    
    # Attendi 5 minuti prima del prossimo ciclo
    echo -e "${YELLOW}⏳ Prossimo ciclo tra 5 minuti...${NC}"
    sleep 300
done
