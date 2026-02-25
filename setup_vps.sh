#!/bin/bash
# ============================================
# EarlyBird VPS Setup Script V4.1
# One-time setup for fresh Linux VPS
# Stack: OCR + Google GenAI SDK + uv (Fast)
# ============================================

set -e  # Exit on error

# Non-interactive mode for apt
export DEBIAN_FRONTEND=noninteractive

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🦅 EarlyBird VPS Setup Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}⚠️ Running as root. Consider using a non-root user.${NC}"
fi

# Step 1: System Dependeies
echo ""
echo -e "${GREEN}🔧 [1/6] Installing System Dependeies...${NC}"
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-tur \
    tesseract-ocr-ita \
    tesseract-ocr-pol \
    libtesseract-dev \
    libxml2-dev \
    libxml2-dev \
    libxslt-dev \
    screen \
    tmux \
    git \
    curl \
    htop \
    net-tools \
    telnet \
     \
    jq \
    openssh-server \
    ufw

# Step 1b: Install Docker (for Redlib Reddit Proxy)
echo ""
echo -e "${GREEN}🐳 [1b/6] Installing Docker...${NC}"
if command -v docker &> /dev/null; then
    echo -e "${YELLOW}   ⚠️ Docker already installed${NC}"
else
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo -e "${GREEN}   ✅ Docker installed${NC}"
fi

# Ensure Docker daemon is running
echo -e "${YELLOW}   🔄 Starting Docker service...${NC}"
sudo systemctl start docker
sudo systemctl enable docker
echo -e "${GREEN}   ✅ Docker service started and enabled${NC}"

# Step 2: Python Virtual Environment (always use python3 -m venv for reliability)
echo ""
echo -e "${GREEN}📦 [2/6] Setting up Python Virtual Environment...${NC}"
if [ -d "venv" ]; then
    # Check if venv is valid
    if [ -f "venv/bin/pip" ]; then
        echo -e "${YELLOW}   ⚠️ venv already exists, skipping creation${NC}"
    else
        echo -e "${YELLOW}   ⚠️ venv exists but is corrupted, recreating...${NC}"
        rm -rf venv
        python3 -m venv venv
        echo -e "${GREEN}   ✅ Virtual environment recreated${NC}"
    fi
else
    python3 -m venv venv
    echo -e "${GREEN}   ✅ Virtual environment created${NC}"
fi

# Activate venv
source venv/bin/activate

# Verify we're in the venv
if [[ "$(which pip)" != *"venv"* ]]; then
    echo -e "${RED}   ❌ Failed to activate venv!${NC}"
    exit 1
fi

# Step 3: Python Dependeies
echo ""
echo -e "${GREEN}📚 [3/6] Installing Python Dependeies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}   ✅ Dependeies installed${NC}"

# Step 3b: Google GenAI SDK for Gemini Agent
echo ""
echo -e "${GREEN}🤖 [3b/6] Installing Google GenAI SDK (Gemini Agent)...${NC}"
pip install google-genai
echo -e "${GREEN}   ✅ Google GenAI SDK installed${NC}"

# Step 3c: Playwright Browser Automation (V7.0 - Stealth + Trafilatura)
echo ""
echo -e "${GREEN}🌐 [3c/6] Installing Playwright Browser Automation (V7.0)...${NC}"
pip install playwright playwright-stealth trafilatura
# Install Chromium browser for Playwright (headless) - V7.2: use python -m for reliability
python -m playwright install chromium
# Install system dependencies for Playwright
# V11.2 FIX: Capture stderr to show errors only if command fails (Bug #2 fix)
if ! install_output=$(python -m playwright install-deps chromium 2>&1); then
    echo -e "${YELLOW}   ⚠️ install-deps failed (may require sudo on some systems)${NC}"
    echo -e "${YELLOW}   Error output:${NC}"
    echo -e "${YELLOW}   $install_output${NC}"
    echo -e "${YELLOW}   Note: Playwright may still work if system dependencies are already installed${NC}"
else
    echo -e "${GREEN}   ✅ System dependencies installed${NC}"
fi
echo -e "${GREEN}   ✅ Playwright + Chromium + Stealth + Trafilatura installed${NC}"

# Step 4: Permissions
echo ""
echo -e "${GREEN}🔑 [4/6] Setting Permissions...${NC}"

# CRITICAL FILES: Must be executable for bot to work
CRITICAL_FILES=("run_forever.sh" "start_system.sh" "go_live.py")
for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        if chmod +x "$file"; then
            echo -e "${GREEN}   ✅ $file is now executable${NC}"
        else
            echo -e "${RED}   ❌ CRITICAL: Failed to set executable permission on $file${NC}"
            echo -e "${RED}   ❌ Bot cannot start without this file${NC}"
            exit 1
        fi
    else
        echo -e "${RED}   ❌ CRITICAL: $file not found${NC}"
        echo -e "${RED}   ❌ Bot cannot start without this file${NC}"
        exit 1
    fi
done

# OPTIONAL FILES: Nice to have but not critical
OPTIONAL_FILES=("run_tests_monitor.sh" "start_api.sh" "run_fullstack.sh")
for file in "${OPTIONAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        if chmod +x "$file"; then
            echo -e "${GREEN}   ✅ $file is now executable${NC}"
        else
            echo -e "${YELLOW}   ⚠️ Warning: Failed to set executable permission on $file${NC}"
        fi
    else
        echo -e "${YELLOW}   ⚠️ $file not found (skipping - optional)${NC}"
    fi
done

# Step 5: Search Engine Info (SearXNG deprecated in V3.3, DDG is primary search)
echo ""
echo -e "${GREEN}🔍 [5/6] Search Engine Info...${NC}"
echo -e "${YELLOW}   ℹ️  DuckDuckGo is the primary search engine (no setup needed)${NC}"
echo -e "${YELLOW}   ℹ️  Serper API is the paid fallback (configure in .env)${NC}"
echo -e "${YELLOW}   ℹ️  Browser Monitor provides TIER 0 real-time monitoring${NC}"

# Step 5b: Deploy Redlib (Self-hosted Reddit Proxy)
echo ""
echo -e "${GREEN}🔴 [5b/6] Deploying Redlib (Reddit Proxy)...${NC}"
if command -v docker &> /dev/null; then
    echo "🚀 Deploying Redlib..."
    if [ "$(docker ps -a -q -f name=redlib)" ]; then
        echo -e "${YELLOW}   ⚠️ Removing existing Redlib container...${NC}"
        docker rm -f redlib
    fi
    docker run -d \
        --name redlib \
        --restart unless-stopped \
        -p 127.0.0.1:8888:8080 \
        quay.io/redlib/redlib:latest
    echo -e "${GREEN}   ✅ Redlib deployed on localhost:8888${NC}"
else
    echo -e "${RED}   ❌ Docker not available, skipping Redlib${NC}"
fi

# Step 6: Environment Check
echo ""
echo -e "${GREEN}🔍 [6/6] Checking Environment...${NC}"

# Check .env file
if [ -f ".env" ]; then
    echo -e "${GREEN}   ✅ .env file found${NC}"
    
    # Check if it's a real config or just the example
    if grep -q "your_odds_api_key_here" .env 2>/dev/null || grep -q "YOUR_" .env 2>/dev/null; then
        echo -e "${YELLOW}   ⚠️ .env contains placeholder values - needs configuration${NC}"
    fi
    
    # Check required keys (without exposing values)
    # V6.0: GEMINI_API_KEY is now optional (DeepSeek is primary)
    # BRAVE_API_KEY is required for DeepSeek Intel Provider
    REQUIRED_KEYS=("ODDS_API_KEY" "OPENROUTER_API_KEY" "BRAVE_API_KEY" "TELEGRAM_TOKEN" "TELEGRAM_CHAT_ID")
    OPTIONAL_KEYS=("GEMINI_API_KEY" "SERPER_API_KEY" "PERPLEXITY_API_KEY")
    MISSING_KEYS=()
    
    for key in "${REQUIRED_KEYS[@]}"; do
        if grep -q "^${key}=" .env && ! grep -q "^${key}=$" .env && ! grep -q "^${key}=YOUR_" .env && ! grep -q "^${key}=your_" .env; then
            echo -e "${GREEN}   ✅ ${key} is set${NC}"
        else
            echo -e "${RED}   ❌ ${key} is missing or not configured${NC}"
            MISSING_KEYS+=("$key")
        fi
    done
    
    if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}⚠️ Please configure the missing API keys in .env file${NC}"
    fi
else
    echo -e "${RED}   ❌ .env file not found!${NC}"
    echo -e "${YELLOW}   📝 Creating from template...${NC}"
    cp .env.example .env
    echo -e "${RED}   ⚠️ IMPORTANT: Edit .env and add your REAL API keys before starting!${NC}"
    echo -e "${RED}   ⚠️ Or copy .env from your backup: cp ../earlybird_backup_*/.env .${NC}"
fi

# Check Tesseract
if command -v tesseract &> /dev/null; then
    echo -e "${GREEN}   ✅ Tesseract OCR installed: $(tesseract --version 2>&1 | head -1)${NC}"
else
    echo -e "${RED}   ❌ Tesseract OCR not found${NC}"
fi

# Verify required Tesseract language packs
echo ""
echo -e "${GREEN}🔍 [6b/6] Verifying Tesseract Language Packs...${NC}"
REQUIRED_LANGS=("eng" "tur" "ita" "pol")
MISSING_LANGS=()

for lang in "${REQUIRED_LANGS[@]}"; do
    if tesseract --list-langs 2>/dev/null | grep -q "^${lang}$"; then
        echo -e "${GREEN}   ✅ Language pack '${lang}' installed${NC}"
    else
        echo -e "${RED}   ❌ Language pack '${lang}' NOT installed${NC}"
        MISSING_LANGS+=("$lang")
    fi
done

if [ ${#MISSING_LANGS[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ CRITICAL: Missing required Tesseract language packs: ${MISSING_LANGS[*]}${NC}"
    echo -e "${YELLOW}Install them with: sudo apt-get install tesseract-ocr-${MISSING_LANGS[0]} tesseract-ocr-${MISSING_LANGS[1]} tesseract-ocr-${MISSING_LANGS[2]} tesseract-ocr-${MISSING_LANGS[3]}${NC}"
    echo -e "${RED}OCR functionality will be limited without these language packs!${NC}"
    exit 1
else
    echo -e "${GREEN}   ✅ All required language packs installed${NC}"
fi

# Create data directory if needed
mkdir -p data

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}📋 Next Steps:${NC}"
echo "   1. Edit .env file with your API keys (if not done)"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Telegram Session Setup (One-Time)${NC}"
echo -e "${YELLOW}   For FULL functionality (access to private channels):${NC}"
echo -e "${YELLOW}   • Run: python setup_telegram_auth.py${NC}"
echo -e "${YELLOW}   • Enter phone: +393703342314${NC}"
echo -e "${YELLOW}   • Enter OTP code from Telegram${NC}"
echo -e "${YELLOW}   • This creates data/earlybird_monitor.session${NC}"
echo ""
echo -e "${YELLOW}   Without session: 50% functionality (public channels only)${NC}"
echo -e "${YELLOW}   With session:    100% functionality (private + public)${NC}"
echo ""
echo "   2. Start the system with tmux (recommended):"
echo ""
echo -e "${GREEN}      ./start_system.sh${NC}"
echo ""
echo "   3. Or use legacy screen mode:"
echo ""
echo -e "${YELLOW}      screen -S earlybird ./run_forever.sh${NC}"
echo ""
echo "   4. Detach from tmux: Ctrl+B, then d"
echo "   5. Reattach later: tmux attach -t earlybird"
echo ""
echo -e "${YELLOW}📊 Useful Commands:${NC}"
echo "   • View logs:        tail -f earlybird.log"
echo "   • View test logs:   tail -f test_monitor.log"
echo "   • Check tmux:       tmux ls"
echo "   • Stop system:      tmux kill-session -t earlybird"
echo ""

# Step 7: End-to-End Verification (Bug #7 fix)
echo ""
echo -e "${GREEN}🧪 [7/7] Running End-to-End Verification...${NC}"
echo ""

# Run the verification script
if python scripts/verify_setup.py; then
    echo ""
    echo -e "${GREEN}   ✅ End-to-end verification PASSED${NC}"
    echo -e "${GREEN}   ✅ Bot is ready to start!${NC}"
else
    exit_code=$?
    echo ""
    if [ $exit_code -eq 1 ]; then
        echo -e "${RED}   ❌ CRITICAL: End-to-end verification FAILED${NC}"
        echo -e "${RED}   ❌ Bot cannot start with critical failures${NC}"
        echo -e "${YELLOW}   ⚠️  Please fix the issues above before starting the bot${NC}"
        exit 1
    elif [ $exit_code -eq 2 ]; then
        echo -e "${YELLOW}   ⚠️  WARNING: End-to-end verification found non-critical issues${NC}"
        echo -e "${YELLOW}   ⚠️  Bot can start but with reduced functionality${NC}"
        echo -e "${YELLOW}   ⚠️  Please fix the issues above for full functionality${NC}"
    else
        echo -e "${RED}   ❌ UNKNOWN ERROR: End-to-end verification failed with exit code $exit_code${NC}"
        exit 1
    fi
fi

echo ""
