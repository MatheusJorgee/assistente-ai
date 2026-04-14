#!/bin/bash
# 🚀 START_QUINTA_FEIRA.sh - Script para iniciar Quinta-Feira v2.1
# Windows: Use PowerShell ou Git Bash
# Linux/Mac: chmod +x start_quinta_feira.sh && ./start_quinta_feira.sh

set -e  # Exit on error

echo "🚀 Iniciando Quinta-Feira v2.1..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. Verificar ambiente
echo -e "${YELLOW}📋 Verificando ambiente...${NC}"
cd backend
python diagnose_system.py

# 2. Iniciar Backend
echo ""
echo -e "${YELLOW}🔌 Iniciando Backend (porta 8000)...${NC}"
echo "Pressione Ctrl+C para parar"
echo ""

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

sleep 3

# 3. Iniciar Frontend (em outra aba/terminal)
echo ""
echo -e "${GREEN}✓ Backend iniciado (PID: $BACKEND_PID)${NC}"
echo ""
echo -e "${YELLOW}🎨 Iniciando Frontend (porta 3000)...${NC}"

cd ../frontend
npm run dev

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null || true" EXIT
