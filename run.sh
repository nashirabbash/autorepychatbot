#!/bin/bash

# AutoReply ChatBot - Startup Script
# Run this script to start the bot: ./run.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   AutoReply ChatBot - Starting Bot     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    echo ""
    echo -e "${YELLOW}Setup steps:${NC}"
    echo "1. Copy .env.example to .env:"
    echo "   cp .env.example .env"
    echo ""
    echo "2. Edit .env and fill with real credentials:"
    echo "   - API_ID from my.telegram.org"
    echo "   - API_HASH from my.telegram.org"
    echo "   - GEMINI_API_KEY from Google AI Studio"
    echo ""
    echo "3. Run this script again: ./run.sh"
    echo ""
    exit 1
fi

# Check if credentials are filled
if grep -q "your_telegram_api_id\|your_api_hash\|your_gemini_api_key" .env; then
    echo -e "${RED}❌ Error: .env has placeholder values!${NC}"
    echo ""
    echo -e "${YELLOW}Please fill .env with real credentials:${NC}"
    echo "  nano .env"
    echo ""
    exit 1
fi

# Set PYTHONPATH for user-installed packages
export PYTHONPATH="$HOME/.local/lib/python3.14/site-packages:$PYTHONPATH"

echo -e "${GREEN}✓${NC} PYTHONPATH configured"
echo -e "${GREEN}✓${NC} .env loaded"
echo ""

# Check if dependencies are installed
echo -e "${BLUE}Checking dependencies...${NC}"
python3 -c "import pyrogram; import google.generativeai" 2>/dev/null && {
    echo -e "${GREEN}✓${NC} All dependencies installed"
} || {
    echo -e "${YELLOW}⚠️  Some dependencies missing${NC}"
    echo "Installing from requirements.txt..."
    pip install -r requirements.txt
}

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${GREEN}🚀 Starting AutoReply ChatBot...${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Bot info:${NC}"
echo "  - Multiple bots: 7 configured"
echo "  - AI Model: Gemini 2.0 Flash"
echo "  - Persona: High Value Man (HVM)"
echo ""
echo -e "${YELLOW}On first run, Telegram will ask for OTP.${NC}"
echo -e "${YELLOW}This is normal - Pyrogram needs to login to your account.${NC}"
echo ""
echo -e "${BLUE}Press Ctrl+C to stop the bot${NC}"
echo ""

# Run the bot
python3 main.py
