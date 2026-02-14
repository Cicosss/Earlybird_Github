#!/bin/bash
# EarlyBird V3.3 - Launcher Script
# Avvia l'orchestratore Python che gestisce tutti i processi

echo "🦅 Starting EarlyBird V3.3 System..."
echo "📅 $(date)"
echo "============================================"

# Attiva virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment non trovato!"
    exit 1
fi

# V7.2: Auto-install Playwright se manca
echo "🌐 Verifica Playwright..."
if ! python -c "from playwright.async_api import async_playwright" 2>/dev/null; then
    echo "⚠️ Playwright non installato, installazione..."
    pip install playwright playwright-stealth trafilatura --quiet
fi
if ! python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()" 2>/dev/null; then
    echo "⚠️ Browser Chromium mancante, installazione..."
    python -m playwright install chromium
    python -m playwright install-deps chromium 2>/dev/null || true
fi
echo "✅ Playwright pronto"

# Esporta PYTHONPATH per import corretti
export PYTHONPATH="${PYTHONPATH}:."

# Avvia l'orchestratore Python
# Gestisce internamente il riavvio dei sotto-processi
python3 src/entrypoints/launcher.py
